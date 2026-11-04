import json

import pandas as pd

from tests.workshop.conftest import FakeConn
from tests.workshop.test_generator import UC, fake_llm_factory
from utils.workshop import cache, generator
from utils.workshop.compliance import classify_violations


class QueryRejectsDML(FakeConn):
    """conn.query() fails on non-SELECT, like st.connection's fetch_pandas_all."""

    def query(self, sql, ttl=None):
        if not sql.lstrip().upper().startswith("SELECT"):
            raise RuntimeError("NotSupportedError")
        return super().query(sql, ttl)


def _boom(p):
    raise RuntimeError("down")


def test_insert_and_audit_use_cursor():
    conn = QueryRejectsDML()
    cache.insert(conn, [("h1", "p", "u", {"a": 1})])
    cache.audit(conn, [("p", "u", "listed", False, "s1:parse_empty")])
    assert any("COCO_PSE_WORKSHOP_CACHE" in q for q in conn.queries)
    a = [q for q in conn.queries if "WORKSHOP_GENERATION_AUDIT" in q]
    assert a and "DEGRADED_REASONS" in a[0] and "'s1:parse_empty'" in a[0]


def test_ensure_tables_adds_reasons_column():
    conn = FakeConn()
    cache.ensure_tables(conn)
    assert any("ADD COLUMN IF NOT EXISTS DEGRADED_REASONS STRING" in q for q in conn.queries)


def test_full_run_with_dml_rejecting_query():
    conn = QueryRejectsDML()
    llm = fake_llm_factory()
    out = generator.generate_workshops(conn, [UC], "D", lambda c, m, p: llm(p), diagnostics=[])
    assert len(out) == 1
    assert any("INSERT INTO" in q and "WORKSHOP_GENERATION_AUDIT" in q for q in conn.queries)


class _AllFail(FakeConn):
    def query(self, sql, ttl=None):
        raise ValueError("x")

    def cursor(self):
        raise KeyError("y")


def test_persistence_failures_never_lose_results():
    diags = []
    llm = fake_llm_factory()
    out = generator.generate_workshops(_AllFail(), [UC], "D", lambda c, m, p: llm(p),
                                       data_conn=FakeConn(), diagnostics=diags)
    assert len(out) == 1 and out[0]["session1"]
    for d in ("cache_lookup: ValueError", "cache_insert: KeyError", "audit: KeyError"):
        assert d in diags
    assert "degraded: 0/1" in diags


def test_degraded_reasons_recorded_and_safe():
    out = generator.build_one(UC, "D", None, {}, _boom)
    r = out["_degraded_reasons"]
    assert "s1:llm_error:RuntimeError" in r and "s2:llm_error:RuntimeError" in r
    assert "down" not in json.dumps(r)


def test_reason_codes_parse_truncated_violation():
    def llm(p):
        if "starter-prompts" in p:
            return "no json here}"
        if "candidate build guide" in p:
            return json.dumps({"recipe_id": "nope"})
        return '{"steps": [{"title": "Spend is $2M."'
    # A use case whose area has guides passing the eligibility gate, so the judge is called.
    uc = dict(UC, skills=["data-governance"], name="Access governance")
    r = generator.build_one(uc, "D", None, {}, llm)["_degraded_reasons"]
    assert "s1:parse_empty" in r and "ctx:invalid_shape" in r and not any(x.startswith("recipe:") for x in r) and "s2:truncated" in r

    def llm2(p):
        if "starter-prompts" in p:
            return json.dumps({"prompts": [{"title": "t", "prompt": "Spend is $2M."}] * 3})
        return json.dumps({"recipe_id": "nope"})
    r2 = generator.build_one(UC, "D", None, {}, llm2)["_degraded_reasons"]
    assert "s1:violation:money" in r2 and "$2M" not in ";".join(r2)


def test_classify_violations_categories():
    assert classify_violations("Spend is $2M and 500 credits", ()) == ["money", "credits"]
    assert classify_violations("stage 3 deal, health score, green list", ()) == ["list_terms", "stage", "score"]
    assert classify_violations("Unlike Databricks", ["Databricks"]) == ["deny"]
    assert classify_violations("see https://evil.example/x", (), allowed_links={"https://ok"}) == ["link"]
    assert classify_violations("fine", ()) == []


def test_degraded_summary_and_audit_reasons():
    conn = FakeConn()
    diags = []
    out = generator.generate_workshops(conn, [UC], "D", lambda c, m, p: _boom(p), diagnostics=diags)
    assert "_degraded_reasons" not in out[0]
    assert "degraded: 1/1" in diags
    a = [q for q in conn.queries if "WORKSHOP_GENERATION_AUDIT" in q and "INSERT" in q][0]
    assert "s1:llm_error:RuntimeError" in a
