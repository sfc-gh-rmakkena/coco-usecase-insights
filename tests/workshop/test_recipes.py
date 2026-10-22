import json
import re

from tests.workshop.test_generator import s2_payload
from utils.workshop import assets, cache, generator, prompts, recipes
from utils.workshop.deny import recipe_backstop_terms
from utils.workshop.verify import verify_plan
from utils.cortex_rest_helpers import cortex_complete_rest_stream

BODY = """# Guide title

Intro paragraph.

## When to use this

- Tenants share tables and need isolation.

When not to use it:

- End users have their own Snowflake identities.

## How it works

The agent reads a session attribute.

```sql
CREATE ROW ACCESS POLICY COOKBOOK_MT.APP.TENANT_POLICY AS (t STRING) RETURNS BOOLEAN -> TRUE;
```

## Walkthrough

### The policy

```sql
-- from the cookbook recipe
ALTER TABLE COOKBOOK_MT.APP.ORDERS ADD ROW ACCESS POLICY COOKBOOK_MT.APP.TENANT_POLICY ON (TENANT_ID);
USE WAREHOUSE COOKBOOK_MT_WH;
```

```python
# not a heading
print(1)
```

See https://docs.snowflake.com/en/user-guide/security-row-intro and
https://github.com/x/cortex-ai-cookbook/recipes and https://quickstarts.snowflake.com/guide/x/index.html

## Teardown

```sql
DROP DATABASE COOKBOOK_MT;
```
"""
META = {"id": "t/mt", "topics": ["cortex-agents"], "features": ["row-access"],
        "related_skills": ["data-governance"]}


def test_split_units_kinds_sql_and_urls():
    us = recipes.split_units("t/mt", BODY, META)
    kinds = [u["kind"] for u in us]
    assert kinds == ["overview", "when_to_use", "when_not_to_use", "how_it_works", "step", "teardown"]
    step = us[4]
    assert step["heading"] == "The policy" and "ALTER TABLE" in step["sql"] and "print(1)" not in step["sql"]
    assert step["doc_urls"] == ["https://docs.snowflake.com/en/user-guide/security-row-intro",
                                "https://quickstarts.snowflake.com/guide/x/index.html"]
    assert "Snowflake identities" in us[2]["text"] and "Snowflake identities" not in us[1]["text"]
    assert "governance" in step["capabilities"] and "cortex_agents" in step["capabilities"]
    assert all(u["unit_id"].startswith("t/mt#") for u in us)


def test_bundled_units_docs_only_and_digests_in_version():
    data = json.loads((assets._ASSETS / recipes.UNITS_FILE).read_text())
    assert len(data["digests"]) == len(assets.recipes_index()) == 23
    hosts = {re.match(r"https://([^/]+)", u).group(1) for x in data["units"] for u in x["doc_urls"]}
    assert hosts <= {"docs.snowflake.com", "quickstarts.snowflake.com"}
    assert {"recipe_id", "unit_id", "kind", "heading", "text", "sql", "doc_urls", "capabilities"} \
        <= set(data["units"][0])
    rebuilt = recipes.build_units(assets.recipes_index(), assets.recipe_body)
    assert rebuilt["digests"] == data["digests"]


UC = {"uc_id": "u1", "name": "Multi-tenant analytics agent", "account": "Acme",
      "skills": ["agent-studio"], "sanitized_desc": "Serve many tenants from one agent with isolation."}


def test_prefilter_deterministic_and_capped():
    units = recipes.load_units()
    a = recipes.prefilter(UC, ["cortex_agents", "semantic_views"], units)
    b = recipes.prefilter(dict(UC), ["cortex_agents", "semantic_views"], list(reversed(units)))
    assert a == b and 0 < len(a) <= 6
    assert recipes.prefilter({"name": "", "skills": []}, [], units) == []


def _view():
    return recipes.candidate_view("t/mt", recipes.split_units("t/mt", BODY, META))


def test_score_computed_by_app_with_evidence_rule_and_penalty():
    v = _view()
    full = {"problem_fit": "strong", "capability_fit": "strong", "steps_reusable": True,
            "audience_fit": True, "contraindicated": False,
            "evidence": {"problem_fit": "Tenants share tables", "capability_fit": "reads a session attribute",
                         "steps_reusable": "The policy", "audience_fit": "need isolation",
                         "contraindicated": ""}}
    assert recipes.score_one(full, v) == 100
    no_ev = dict(full, evidence=dict(full["evidence"], problem_fit="made up quote not in text"))
    assert recipes.score_one(no_ev, v) == 60
    partial = dict(full, problem_fit="partial", capability_fit="partial")
    assert recipes.score_one(partial, v) == 65
    contra = dict(full, contraindicated=True,
                  evidence=dict(full["evidence"], contraindicated="have their own Snowflake identities"))
    assert recipes.score_one(contra, v) == 100 - recipes.CONTRA_PENALTY
    unquoted = dict(full, contraindicated=True)
    assert recipes.score_one(unquoted, v) == 100
    assert recipes.score_one({"problem_fit": "strong"}, v) == 0


def test_select_above_80_max_3():
    assert recipes.select({"a": 81, "b": 80, "c": 95, "d": 90, "e": 85}) == ["c", "d", "e"]
    assert recipes.select({"a": 80, "b": 10}) == []


def test_pack_shape_docs_urls_neutral_titles_placeholders():
    units = recipes.split_units("t/mt", BODY, META)
    allow = {"https://docs.snowflake.com/en/user-guide/security-row-intro"}
    pack = recipes.integration_pack(["t/mt"], units, ["governance", "cortex_agents"], allow)
    entries = [e for es in pack.values() for e in es]
    assert entries and all(set(e) == {"title", "sql", "source_url"} for e in entries)
    assert set(pack) <= {"governance", "cortex_agents"}
    blob = json.dumps(pack)
    assert "COOKBOOK" not in blob.upper() and "recipe" not in blob.lower() and "github" not in blob
    assert "<DB>.<SCHEMA>.ORDERS" in blob and "<WAREHOUSE>" in blob and "DROP DATABASE" not in blob
    assert all(e["source_url"].startswith("https://docs.snowflake.com/") for e in entries)
    assert all("Guide" not in e["title"] and "policy" not in e["title"].lower() for e in entries)
    merged = recipes.merge_grounding({"governance": {"sql_snippets": [{"title": "x", "sql": "s", "source_url": "u"}]}}, pack)
    assert len(merged["governance"]["sql_snippets"]) == 1 + len(pack.get("governance", []))


def test_bundled_pack_never_names_source():
    units = recipes.load_units()
    rids = sorted({u["recipe_id"] for u in units})
    pack = recipes.integration_pack(rids, units, ["cortex_agents", "governance", "ai_functions"])
    blob = json.dumps(pack)
    assert pack and not re.search(r"cookbook|recipe|github\.com", blob, re.I)
    titles = [r["title"] for r in assets.recipes_index()]
    assert not any(t in blob for t in titles)


def test_backstop_terms():
    terms = {t.lower() for t in recipe_backstop_terms()}
    assert {"recipe", "cookbook", "% match"} <= terms
    assert assets.recipes_index()[0]["title"].lower() in terms
    assert any(t.startswith("cookbook_") for t in terms)


def test_verify_ctx_unused_and_attribution():
    plan = {"sections": [{"sql": "SELECT AI_REDACT(x) FROM t"}]}
    f = verify_plan(plan, [], set(), packs={"a/b": ["TENANT_POLICY"], "c/d": ["AI_REDACT"]},
                    backstop=("cookbook",))
    assert "ctx_unused:a/b" in f and "ctx_unused:c/d" not in f and "attribution" not in f
    f2 = verify_plan({"problem_statement": "From the Cookbook."}, [], set(), backstop=("cookbook",))
    assert "attribution" in f2


def test_key_tokens_exclude_base():
    es = [{"title": "t", "sql": "SELECT AI_REDACT(x), SNOWFLAKE.CORTEX_USER, CURRENT_ROLE()", "source_url": "u"}]
    base = {"k": {"sql_snippets": [{"sql": "GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER"}]}}
    assert recipes.key_tokens(es, base) == ["AI_REDACT"]


def test_key_tokens_drop_generic_and_min_hits():
    es = [{"title": "t", "sql": "SELECT METRIC_NAME, DEFAULT_ROLE, TENANT_POLICY, GITHUB_SUBJECT, DEPLOYER_ROLE",
           "source_url": "u"}]
    toks = recipes.key_tokens(es, {})
    assert toks == ["DEPLOYER_ROLE", "GITHUB_SUBJECT", "TENANT_POLICY"]
    one = {"sections": [{"sql": "SELECT TENANT_POLICY"}]}
    assert "ctx_unused:a" in verify_plan(one, [], set(), packs={"a": toks})
    three = {"sections": [{"sql": "SELECT TENANT_POLICY, GITHUB_SUBJECT, DEPLOYER_ROLE"}]}
    assert "ctx_unused:a" not in verify_plan(three, [], set(), packs={"a": toks})


def test_pack_entries_flagged_must_use_and_invented_dropped():
    pack = {"row_access": [{"title": "t", "sql": "SELECT TENANT_POLICY", "source_url": "u"},
                           {"title": "x", "sql": "SELECT * FROM DATA_AGENT_RUN", "source_url": "u"}]}
    kept = generator._drop_invented(pack)["row_access"]
    assert [e["title"] for e in kept] == ["t"]
    p = prompts.session2_prompt(UC, "D", {}, {"row_access": kept}, [])
    assert '"must_use": true' in p


def test_judge_prompt_and_generator_flow(monkeypatch):
    units = recipes.split_units("t/mt", BODY, META)
    monkeypatch.setattr(recipes, "load_units", lambda: units)
    monkeypatch.setattr(recipes, "_allow", lambda: {"https://docs.snowflake.com/en/user-guide/security-row-intro"})
    v = _view()
    seen, temps = [], []

    def llm(p, temperature=None):
        seen.append(p)
        if "candidate build guide" in p:
            temps.append(temperature)
            return json.dumps({"recipes": [{"recipe_id": "t/mt", "problem_fit": "strong",
                                            "capability_fit": "strong", "steps_reusable": True,
                                            "audience_fit": True, "contraindicated": False,
                                            "evidence": {"problem_fit": "Tenants share tables",
                                                         "capability_fit": "session attribute",
                                                         "steps_reusable": "The policy",
                                                         "audience_fit": "need isolation"}}]})
        if "starter-prompts" in p:
            return json.dumps({"prompts": [{"title": "t", "purpose": "p", "prompt": "do x"}] * 3})
        return json.dumps(s2_payload(sql="SELECT 1"))
    uc = dict(UC, skills=["data-governance"], name="Tenant isolation")
    out = generator.build_one(uc, "D", None, {}, llm)
    judge = [p for p in seen if "candidate build guide" in p][0]
    assert v["when_not_to_use"][:20] in judge and temps == [0] * generator.JUDGE_RUNS
    s2 = [p for p in seen if "pse-uc-implementation-plan" in p][0]
    assert "<DB>.<SCHEMA>.ORDERS" in s2 and "MATCHED_RECIPE" not in s2
    assert out["_context_sources"] == [{"recipe_id": "t/mt", "score": 100}]
    assert "ctx:selected:1" in out["_degraded_reasons"]
    assert any(r.startswith("s2:verify:ctx_unused:t/mt") for r in out["_degraded_reasons"])
    repair = [p for p in seen if "=== REPAIR ===" in p][0]
    assert "grounding_unused" in repair.split("=== REPAIR ===")[1] and "t/mt" not in repair.split("=== REPAIR ===")[1]
    assert "t/mt" not in json.dumps(out["session2"])


def test_s2_rules_no_attribution():
    r = prompts.S2_RULES
    assert "equally authoritative" in r and "recipe, cookbook, playbook, match or confidence" in r


def test_audit_context_sources_and_alter(monkeypatch):
    from tests.workshop.test_resilience import QueryRejectsDML
    conn = QueryRejectsDML()
    cache.audit(conn, [("p", "u", "listed", False, "x", [{"recipe_id": "a/b", "score": 90}]),
                       ("p", "u2", "listed", True, "")])
    q = [q for q in conn.queries if "WORKSHOP_GENERATION_AUDIT" in q][0]
    assert "CONTEXT_SOURCES" in q and "a/b" in q and "PARSE_JSON('[]')" in q
    from tests.workshop.conftest import FakeConn
    c2 = FakeConn()
    cache.ensure_tables(c2)
    assert any("ADD COLUMN IF NOT EXISTS CONTEXT_SOURCES VARIANT" in x for x in getattr(c2, "executed", []) + getattr(c2, "queries", []))


def test_stream_temperature_passthrough(monkeypatch):
    import utils.cortex_rest_helpers as h
    got = []
    monkeypatch.setattr(h, "_stream_once", lambda conn, payload: got.append(payload) or "ok")
    cortex_complete_rest_stream(None, "m", "p")
    cortex_complete_rest_stream(None, "m", "p", temperature=0)
    assert "temperature" not in got[0] and got[1]["temperature"] == 0
