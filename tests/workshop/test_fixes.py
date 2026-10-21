import json

import pandas as pd

from tests.workshop.conftest import FakeConn
from tests.workshop.test_generator import UC, fake_llm_factory, s2_payload
from utils.workshop import cache, generator, prompts
from utils.workshop.compliance import find_violations, scrub, sql_quote
from utils.workshop.context import fetch_uc_context
from utils.workshop.gate import _in_list, usage_tier


def _boom(prompt):
    raise RuntimeError("down")


def test_degraded_not_cached_but_audited():
    conn = FakeConn({"TOP_SNOWFLAKE_COMPANIES": pd.DataFrame({"COMPANY_NAME": ["Roche"]})})
    out = generator.generate_workshops(conn, [UC], "Deloitte", lambda c, m, p: _boom(p))
    assert not any("INSERT INTO" in q and "COCO_PSE_WORKSHOP_CACHE" in q for q in conn.queries)
    assert any("INSERT INTO" in q and "WORKSHOP_GENERATION_AUDIT" in q for q in conn.queries)
    assert "_degraded" not in out[0]


def test_success_not_marked_degraded():
    conn = FakeConn()
    llm = fake_llm_factory()
    out = generator.generate_workshops(conn, [UC], "Deloitte", lambda c, m, p: llm(p))
    assert any("INSERT INTO" in q and "COCO_PSE_WORKSHOP_CACHE" in q for q in conn.queries)
    assert "_degraded" not in out[0]


def test_scrub_deny_competitor_and_person():
    t = "Unlike Databricks, we scale. Jane Doe will lead. Data lands in tables."
    out = scrub(t, set(), deny=["Databricks", "Jane Doe"])
    assert out == "Data lands in tables."
    assert "Databricks" in find_violations("Unlike databricks here", deny=["Databricks"])[0] \
        or find_violations("Unlike databricks here", deny=["Databricks"])
    assert scrub("Databricksy is fine.", set(), deny=["Databricks"]) == "Databricksy is fine."


def test_context_new_shape_and_deny_terms():
    uid = "a0X3n00000ABCDEFGH"
    df = pd.DataFrame({"USE_CASE_ID": [uid], "DESCRIPTION": ["x"], "TECHNICAL_CHAMPION": ["Jane Doe; Bo"],
                       "COMPETITORS": ["Databricks;Other;BigQuery/None"], "INCUMBENT_VENDOR": ["Teradata"]})
    ctx = fetch_uc_context(FakeConn({"DD_SALESFORCE_USE_CASE": df}), [uid])[uid]
    assert ctx["llm"]["TECHNICAL_CHAMPION"] == "named champion identified"
    assert "COMPETITORS" not in ctx["llm"]
    assert sorted(ctx["deny"]) == ["BigQuery", "Databricks",
                                   "Databricks;Other;BigQuery/None", "Jane Doe", "Jane Doe; Bo", "Teradata"]


def test_generator_deny_applied_and_llm_ctx_only():
    seen = []

    def llm(p):
        seen.append(p)
        if "Pick the single cookbook recipe" in p:
            return json.dumps({"recipe_id": "nope", "confidence": 0})
        if "starter-prompts" in p:
            return json.dumps({"prompts": [{"title": "t", "purpose": "p", "prompt": "do x"}] * 3})
        leak = "Unlike Databricks, fast. " if sum("pse-uc-implementation-plan" in x for x in seen) == 1 else ""
        return json.dumps(s2_payload(leak + "Real goal."))
    out = generator.build_one(UC, "D", None, {"DESCRIPTION": "x"}, llm, deny=["Databricks"])
    assert "Databricks" not in json.dumps(out)
    assert out["brief"] == "Real goal."
    assert out["_degraded"] is False
    # leak scrubbed, not regenerated (a verify repair pass may follow; it is not a regeneration for the leak)
    assert sum("pse-uc-implementation-plan" in x and "=== REPAIR ===" not in x for x in seen) == 1


def test_sql_quote_backslash():
    assert sql_quote("a\\") == "a\\\\"
    assert _in_list(["ab\\"]) == "'AB\\\\'"
    assert _in_list(["o'k"]) == "'O''K'"


def test_insert_chunks():
    conn = FakeConn()
    cache.insert(conn, [(f"h{i}", "p", "u", {"i": i}) for i in range(45)])
    assert len([q for q in conn.queries if "INSERT INTO" in q]) == 3


def test_insert_chunks_by_size():
    conn = FakeConn()
    big = "x" * 150_000
    cache.insert(conn, [(f"h{i}", "p", "u", {"b": big}) for i in range(5)])
    ins = [q for q in conn.queries if "INSERT INTO" in q]
    assert len(ins) >= 3 and all(len(q) <= 400_000 + 1000 for q in ins)


def test_usage_tier_nan_none():
    assert usage_tier(float("nan")) == "No"
    assert usage_tier(None) == "No"


def test_parse_skips_non_json_brace():
    assert generator._parse('Note {see below}. {"x":1}') == {"x": 1}
    assert generator._parse("nothing") == {}


def test_s1_validator_requires_prompt():
    bad = json.dumps({"prompts": [{"title": "t", "prompt": ""}] * 3})
    out = generator.build_one(UC, "D", None, {}, lambda p: bad if "starter-prompts" in p else _boom(p))
    assert out["session1"] == generator._fallback_session1(UC)


def test_stable_shapes():
    a = generator.build_one(UC, "D", None, {}, fake_llm_factory())
    b = generator.build_one(UC, "D", None, {}, _boom)
    assert set(a["session2"]["plan"]) == set(b["session2"]["plan"]) == set(generator.PLAN_DEFAULT)
    assert set(a["session2"]["plan"]["resources"]) == {"quickstarts", "docs", "github"}
    assert set(a["session2"]["plan"]["sections"][0]) == set(generator._ROWS["sections"])
    keys = {"band", "id", "title", "confidence", "rationale", "body"}
    assert set(a["session2"]["recipe"]) == set(b["session2"]["recipe"]) == keys
    assert a["_degraded"] is False and b["_degraded"] is True


def test_lookup_dedupes_and_workers_and_schema():
    conn = FakeConn()
    cache.lookup(conn, ["h1"])
    assert "QUALIFY ROW_NUMBER() OVER (PARTITION BY CACHE_KEY_HASH ORDER BY CREATED_AT DESC) = 1" in conn.queries[-1]
    assert generator.MAX_WORKERS == 16
    assert "at most 8" in prompts.S2_SCHEMA
