import json

import pandas as pd
import pytest

from tests.workshop.conftest import FakeConn
from tests.workshop.test_generator import UC, s2_payload
from utils.workshop import generator, prompts
from utils.workshop.compliance import classify_violations, find_violations, redact_amounts
from utils.workshop.context import fetch_uc_context

S1_OK = json.dumps({"prompts": [{"title": "t", "purpose": "p", "prompt": "do x"}] * 3})


def _llm(s1=S1_OK, s2=None, log=None):
    def llm(p):
        if log is not None:
            log.append(p)
        if "Pick the single cookbook recipe" in p:
            return json.dumps({"recipe_id": "nope", "confidence": 0})
        if "starter-prompts" in p:
            return s1 if isinstance(s1, str) else s1(p)
        return s2
    return llm


# F1: SQL positional refs are not money
@pytest.mark.parametrize("sql", ["SELECT $1:col::string FROM @stg",
                                 "SELECT $1, METADATA$FILENAME FROM @s",
                                 "SELECT PARSE_JSON($1) AS v", "SELECT $2 AS b FROM t",
                                 "SELECT $3 FROM t"])
def test_sql_positional_not_money(sql):
    assert find_violations(sql) == []
    assert classify_violations(sql) == []
    assert generator._clean_sql(sql) == sql


def test_sql_trailing_positional_only_in_sql():
    assert generator._clean_sql("SELECT a, $1\nFROM t") == "SELECT a, $1\nFROM t"
    assert generator._clean_sql("SELECT a, $1;") == "SELECT a, $1;"
    assert find_violations("- item $5") != []


@pytest.mark.parametrize("t", ["Spend is $1.3M.", "About $90K a year", "$5,000 per month"])
def test_real_money_still_flagged(t):
    assert classify_violations(t) == ["money"]
    assert generator._clean_sql(f"-- {t}\nSELECT 1") == ""


# F5
def test_redact_amounts():
    assert redact_amounts("$1.3M spend") == "[amount] spend"
    assert "5,000" not in redact_amounts("burns 5,000 credits monthly")
    assert redact_amounts("no numbers here") == "no numbers here"


def _ctx(**cols):
    uid = "a0X3n00000ABCDEFGH"
    df = pd.DataFrame({"USE_CASE_ID": [uid], **{k: [v] for k, v in cols.items()}})
    return fetch_uc_context(FakeConn({"DD_SALESFORCE_USE_CASE": df}), [uid])[uid]


def test_context_redacts_and_drops_competitors():
    c = _ctx(MEDDPICC_METRICS="$1.3M spend", COMPETITORS="Databricks", INCUMBENT_VENDOR="Teradata")
    assert c["llm"]["MEDDPICC_METRICS"] == "[amount] spend"
    assert "COMPETITORS" not in c["llm"]
    assert c["llm"]["INCUMBENT_VENDOR"] == "Teradata"
    assert set(c["deny"]) == {"Databricks", "Teradata"}


# F3/F6
def test_deny_excludes_picklists_and_splits():
    c = _ctx(POC_LED_BY="Partner Prime + Snowflake SD", IMPLEMENTER="Partner Only",
             TECHNICAL_CHAMPION="Jane Doe", INCUMBENT_VENDOR="AWS: Redshift",
             COMPETITORS="Databricks (including Azure, AWS, and GCP);Other;Customer")
    d = set(c["deny"])
    assert not any("Partner" in t for t in d)
    assert {"Jane Doe", "AWS: Redshift", "AWS", "Redshift", "Databricks"} <= d
    assert not {"Other", "Customer"} & d


def test_deny_exempt_only_when_in_use_case_name():
    # The judge summary (sanitized_desc) is not a public header: it can carry confidential detail.
    uc = dict(UC, name="SAP Finance Migration", sanitized_desc="Unify Oracle EPM and finance data.")
    s2 = json.dumps(s2_payload("Land SAP data. Replace Oracle EPM reports. Unlike Databricks, it scales."))
    out = generator.build_one(uc, "D", None, {}, _llm(s2=s2), deny=["SAP", "Oracle EPM", "Databricks"])
    assert out["brief"] == "Land SAP data."
    assert "Oracle" not in json.dumps(out) and "Databricks" not in json.dumps(out)
    assert out["_degraded"] is False


def test_brief_fallback_scrubbed_or_neutral():
    uc = dict(UC, sanitized_desc="Forecast weekly demand. Uses Oracle EPM.")
    s2 = json.dumps(s2_payload(""))
    out = generator.build_one(uc, "D", None, {}, _llm(s2=s2), deny=["Oracle EPM"])
    assert out["brief"] == "Forecast weekly demand."
    out = generator.build_one(dict(uc, sanitized_desc="Oracle EPM only."), "D", None, {}, _llm(s2=s2),
                              deny=["Oracle EPM"])
    assert out["brief"] == "Demand Forecasting for Roche"


# F4
def test_s2_scrubs_not_rejects():
    log = []
    payload = s2_payload("Budget is $1.3M. Real goal.", sql="SELECT $1:a FROM @s", n=4)
    payload["sections"][0]["explanation"] = "Uses 500 credits. Build it."
    payload["sections"][3]["sql"] = "-- costs $90K\nSELECT 1"
    out = generator.build_one(UC, "D", None, {}, _llm(s2=json.dumps(payload), log=log))
    plan = out["session2"]["plan"]
    assert out["_degraded"] is False
    assert sum("pse-uc-implementation-plan" in p and "=== REPAIR ===" not in p for p in log) == 1
    assert out["brief"] == "Real goal."
    assert plan["sections"][0]["explanation"] == "Build it."
    assert plan["sections"][0]["sql"] == "SELECT $1:a FROM @s"
    assert plan["sections"][3]["sql"] == ""
    assert "s2:scrubbed:money" in out["_degraded_reasons"]
    assert "s2:scrubbed:credits" in out["_degraded_reasons"]
    assert find_violations(json.dumps(out)) == []


def test_s2_clean_emptied_degrades():
    # SQL that leaks is blanked; fewer than 3 grounded SQL sections degrades.
    bad = s2_payload(sql="-- spend $2M\nSELECT 1")
    bad["sections"][0]["sql"] = "SELECT 1"
    out = generator.build_one(UC, "D", None, {}, _llm(s2=json.dumps(bad)))
    assert out["_degraded"] is True and "s2:clean_emptied" in out["_degraded_reasons"]
    assert out["session2"]["plan"]["sections"][0]["sql"] == "SELECT 1"


def test_s2_sql_needs_allowed_source_and_no_invented_constructs():
    p = s2_payload(n=5)
    p["sections"][0]["source_url"] = "https://evil.example/x"
    p["sections"][1]["sql"] = "CREATE AGENT a COMPUTE_POOL = p MODEL = 'm'"
    p["sections"][2]["sql"] = "SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY"
    out = generator.build_one(UC, "D", None, {}, _llm(s2=json.dumps(p)))
    secs = out["session2"]["plan"]["sections"]
    assert [bool(s["sql"]) for s in secs] == [False, False, False, True, True]
    assert secs[0]["source_url"] == ""
    assert out["_degraded"] is True


def test_s1_credits_do_not_reject():
    log = []
    s1 = json.dumps({"prompts": [{"title": "t", "purpose": "Keep under 100 credits.",
                                  "prompt": "do x"}] * 3})
    out = generator.build_one(UC, "D", None, {}, _llm(s1=s1, log=log))
    assert sum("starter-prompts" in p for p in log) == 1
    assert out["session1"][0]["prompt"] == "do x"
    assert "credits" not in json.dumps(out["session1"])


def test_s1_scrub_accept_after_retry():
    s1 = json.dumps({"prompts": [{"title": "t", "purpose": "p",
                                  "prompt": "Find tables. Spend is $2M."}] * 3})
    out = generator.build_one(UC, "D", None, {}, _llm(s1=s1))
    assert out["session1"] != generator._fallback_session1(UC)
    assert out["session1"][0]["prompt"] == "Find tables."
    assert "s1:violation:money" in out["_degraded_reasons"]


def test_session2_prompt_forbids_amounts_and_competitors():
    p = prompts.session2_prompt(UC, "D", {}, None)
    assert "Do not state any monetary amounts, budgets, or credit quantities" in p
    assert "Do not name competitors" in p
