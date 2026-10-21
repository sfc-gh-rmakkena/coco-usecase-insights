import json

import pandas as pd
import pytest

from tests.workshop.conftest import FakeConn
from tests.workshop.test_generator import UC
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


def test_deny_exempt_when_in_public_header():
    uc = dict(UC, sanitized_desc="Unify SAP and finance data.")
    s2 = json.dumps({"problem_statement": "Land SAP data. Unlike Databricks, it scales.",
                     "steps": [{"title": "Ingest SAP tables", "detail": "d", "sql": ""}]})
    out = generator.build_one(uc, "D", None, {}, _llm(s2=s2), deny=["SAP", "Databricks"])
    assert out["brief"] == "Land SAP data."
    assert out["session2"]["plan"]["steps"][0]["title"] == "Ingest SAP tables"
    assert "Databricks" not in json.dumps(out)
    assert out["_degraded"] is False


# F4
def test_s2_scrubs_not_rejects():
    log = []
    s2 = json.dumps({"problem_statement": "Budget is $1.3M. Real goal.",
                     "steps": [{"title": "s", "detail": "Uses 500 credits. Build it.",
                                "sql": "SELECT $1:a FROM @s"},
                               {"title": "t", "detail": "d", "sql": "-- costs $90K\nSELECT 1"}]})
    out = generator.build_one(UC, "D", None, {}, _llm(s2=s2, log=log))
    plan = out["session2"]["plan"]
    assert out["_degraded"] is False
    assert sum("pse-uc-implementation-plan" in p for p in log) == 1
    assert out["brief"] == "Real goal."
    assert plan["steps"][0]["detail"] == "Build it."
    assert plan["steps"][0]["sql"] == "SELECT $1:a FROM @s"
    assert plan["steps"][1]["sql"] == ""
    assert "s2:scrubbed:money" in out["_degraded_reasons"]
    assert "s2:scrubbed:credits" in out["_degraded_reasons"]
    assert find_violations(json.dumps(out)) == []


def test_s2_clean_emptied_degrades():
    s2 = json.dumps({"steps": [{"title": "Spend $2M.", "detail": "", "sql": ""}]})
    out = generator.build_one(UC, "D", None, {}, _llm(s2=s2))
    # a step dict survives even if its text is scrubbed; empty steps list degrades
    s2b = json.dumps({"steps": ["Spend $2M."]})
    out2 = generator.build_one(UC, "D", None, {}, _llm(s2=s2b))
    assert out["_degraded"] is False
    assert out2["_degraded"] is True and "s2:clean_emptied" in out2["_degraded_reasons"]


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
