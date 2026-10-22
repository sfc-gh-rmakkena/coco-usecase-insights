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


SEC = "Multi-tenant analytics agent\nServe many tenants from one agent with isolation.\nAI: Agents\nCortex Agents"
FULL = {"goal_match": "strong", "capability_fit": "strong", "steps_reusable": True,
        "audience_fit": True, "contraindicated": False,
        "evidence": {"section_goal": "many tenants from one agent with isolation",
                     "recipe_goal": "Tenants share tables", "capability_fit": "reads a session attribute",
                     "steps_reusable": "The policy", "audience_fit": "need isolation",
                     "contraindicated": ""}}


def test_score_computed_by_app_with_evidence_rule_and_penalty():
    v = _view()
    full = FULL
    assert recipes.score_one(full, v, SEC) == 100
    no_ev = dict(full, evidence=dict(full["evidence"], capability_fit="made up quote not in text"))
    assert recipes.score_one(no_ev, v, SEC) == 75
    contra = dict(full, contraindicated=True,
                  evidence=dict(full["evidence"], contraindicated="have their own Snowflake identities"))
    assert recipes.score_one(contra, v, SEC) == 100 - recipes.CONTRA_PENALTY
    unquoted = dict(full, contraindicated=True)
    assert recipes.score_one(unquoted, v, SEC) == 100
    assert recipes.score_one({"goal_match": "strong"}, v, SEC) == 0


def test_goal_match_needs_both_verbatim_quotes():
    v = _view()
    ev = FULL["evidence"]
    # section quote not in use case / area text -> goal 0 and capped at 80
    bad_sec = dict(FULL, evidence=dict(ev, section_goal="build an executive BI dashboard"))
    assert recipes.score_one(bad_sec, v, SEC) == 55
    # recipe quote must come from when_to_use (how_it_works text does not count)
    bad_rec = dict(FULL, evidence=dict(ev, recipe_goal="The agent reads a session attribute"))
    assert recipes.score_one(bad_rec, v, SEC) == 55
    assert recipes.score_one(FULL, v, "") == 55  # no section text shown -> no goal evidence


def test_goal_match_weights_and_partial_never_selectable():
    v = _view()
    assert recipes.GOAL_POINTS == {"strong": 45, "partial": 15}
    assert recipes.RUBRIC["capability_fit"] == {"strong": 25, "partial": 10}
    partial = dict(FULL, goal_match="partial")
    assert recipes.score_one(partial, v, SEC) == 70
    assert recipes.score_one(dict(partial, capability_fit="partial"), v, SEC) == 55
    # even with inflated criteria a non-strong goal is capped at the bar (not > 80)
    for g in ("partial", "none", ""):
        assert recipes.score_one(dict(FULL, goal_match=g), v, SEC) <= recipes.SELECT_MIN
    assert recipes.select({("t/mt", "X"): recipes.score_one(partial, v, SEC)}) == []


def test_select_ties_by_coverage_then_prefilter_then_id():
    s = {("a", "X"): 100, ("b", "X"): 100, ("c", "X"): 100}
    assert recipes.select(s)[0][0] == "a"  # no tiebreak -> id
    tb = {("a", "X"): (1, 9), ("b", "X"): (2, 1), ("c", "X"): (2, 5)}
    assert recipes.select(s, tiebreak=tb) == [("c", "X", 100)]
    tb2 = {("a", "X"): (1, 9), ("b", "X"): (1, 9), ("c", "X"): (1, 3)}
    assert recipes.select(s, tiebreak=tb2) == [("a", "X", 100)]
    # score still dominates the tiebreak
    assert recipes.select({("a", "X"): 95, ("b", "X"): 90}, tiebreak={("b", "X"): (9, 9)})[0][0] == "a"


def test_aggregate_requires_two_of_three_above_bar():
    p = ("a", "X")
    assert recipes.aggregate([{p: 100}, {p: 100}, {p: 0}], [p]) == {p: 100}
    assert recipes.aggregate([{p: 100}, {p: 70}, {p: 90}], [p]) == {p: 90}
    # median > 80 but only one run above the bar is impossible with 3 runs; with values
    # straddling the bar the 2-of-3 rule still holds
    assert recipes.aggregate([{p: 100}, {p: 80}, {p: 80}], [p]) == {p: 80}
    assert recipes.aggregate([{p: 100}, {}, {}], [p]) == {p: 0}
    # two runs only: both must clear the bar
    assert recipes.aggregate([{p: 100}, {p: 60}], [p]) == {p: 60}
    assert recipes.aggregate([{p: 100}, {p: 90}], [p]) == {p: 90}
    assert recipes.select(recipes.aggregate([{p: 100}, {p: 50}, {p: 80}], [p])) == []


def test_area_coverage_and_prefilter_scores():
    units = recipes.split_units("t/mt", BODY, META)
    assert recipes.own_caps(units, "t/mt") == {"governance"}
    assert recipes.area_coverage("t/mt", {"capabilities": ["governance", "cortex_agents"]}, units) == 1
    ps = recipes.prefilter_scores(UC, [], units, AREAS)
    assert set(ps) == {("t/mt", AREAS[0]["area"]), ("t/mt", AREAS[1]["area"])} and all(v > 0 for v in ps.values())


def test_select_above_80_max_3_one_per_area():
    s = {("a", "X"): 81, ("b", "X"): 95, ("c", "Y"): 90, ("d", "Z"): 85, ("e", "W"): 99, ("f", "V"): 80}
    assert recipes.select(s) == [("e", "W", 99), ("b", "X", 95), ("c", "Y", 90)]
    # one guide per area (highest wins), one area per guide, nothing at or below 80
    assert recipes.select({("a", "X"): 90, ("b", "X"): 85, ("a", "Y"): 88, ("c", "Y"): 82}) == \
        [("a", "X", 90), ("c", "Y", 82)]
    assert recipes.select({("a", "X"): 80, ("b", "Y"): 10}) == []


AREAS = [{"area": "Platform: Compliance & Governance", "capabilities": ["governance"], "coco_skills": []},
         {"area": "AI: Agents", "capabilities": ["cortex_agents"], "coco_skills": []},
         {"area": "DE: Ingestion", "capabilities": ["snowpipe"], "coco_skills": []}]


def test_prefilter_and_pairs_per_area():
    units = recipes.split_units("t/mt", BODY, META)
    assert recipes.prefilter(UC, [], units, areas=AREAS) == ["t/mt"]
    assert recipes.prefilter(UC, [], units, areas=[AREAS[2]]) == []
    # cortex_agents is only inherited from index metadata, not built by the guide's units
    assert recipes.candidate_pairs(["t/mt"], AREAS, units) == [("t/mt", "Platform: Compliance & Governance")]


def test_eligibility_gate_uses_primary_capability_only():
    units = recipes.split_units("t/mt", BODY, META)
    # governance is in the area but not first -> not eligible
    sec_second = {"area": "BI", "capabilities": ["semantic_views", "governance"]}
    assert not recipes.eligible("t/mt", sec_second, units)
    assert recipes.eligible("t/mt", {"area": "G", "capabilities": ["governance", "semantic_views"]}, units)
    assert not recipes.eligible("t/mt", {"area": "E", "capabilities": []}, units)
    assert recipes.candidate_pairs(["t/mt"], [sec_second], units) == []


def test_bundled_gate_drops_agent_guides_from_bi_and_transformation():
    units = recipes.load_units()
    bi = {"area": "Analytics: Business Intelligence", "capabilities": ["semantic_views", "cortex_agents"]}
    tr = {"area": "DE: Transformation", "capabilities": ["dynamic_tables", "tasks", "snowpark", "dbt"]}
    assert not recipes.eligible("cortex-agents/scoping-agentic-implementations", bi, units)
    assert not recipes.eligible("ai-observability/agent-feedback-to-evals", bi, units)
    assert not recipes.eligible("cortex-agents/agent-ci-cd-with-dbt", tr, units)
    assert recipes.eligible("semantic-views/mixed-grain-and-verified-queries", bi, units)


def test_score_all_per_pair():
    units = recipes.split_units("t/mt", BODY, META)
    pairs = [("t/mt", "Platform: Compliance & Governance"), ("t/mt", "AI: Agents")]
    ans = dict(FULL, recipe_id="t/mt", area=pairs[0][1])
    ans["evidence"] = dict(FULL["evidence"], section_goal="Compliance & Governance")
    weak = dict(ans, area=pairs[1][1], goal_match="none")
    got = recipes.score_all({"pairs": [ans, weak, dict(ans, area="unknown")]}, pairs, units, UC, AREAS)
    assert got == {pairs[0]: 100, pairs[1]: 55}
    # the section quote is checked against THAT area's text
    other = dict(ans, area=pairs[1][1])
    assert recipes.score_all({"pairs": [other]}, pairs, units, UC, AREAS)[pairs[1]] == 55


def test_pack_limited_to_area_units():
    body = BODY.replace("## Teardown", "### Load files with Snowpipe\n\n```sql\nCREATE PIPE P AUTO_INGEST = TRUE AS COPY INTO "
                        "COOKBOOK_MT.APP.RAW FROM @S;\n```\n\n## Teardown")
    units = recipes.split_units("t/mt", body, dict(META, features=["row-access", "snowpipe"]))
    allow = {"https://docs.snowflake.com/en/user-guide/security-row-intro"}
    gov = recipes.integration_pack([("t/mt", ["governance"], 90)], units, [], allow)
    assert set(gov) == {"governance"} and "CREATE PIPE" not in json.dumps(gov)
    pipe = recipes.packs_by_recipe([("t/mt", ["snowpipe"], 90)], units, [], allow)["t/mt"]
    assert pipe and all("CREATE PIPE" in e["sql"] for e in pipe)


def test_verify_ctx_unused_section_scoped():
    toks = ["TENANT_POLICY", "GITHUB_SUBJECT", "DEPLOYER_ROLE"]
    sql = "SELECT TENANT_POLICY, GITHUB_SUBJECT, DEPLOYER_ROLE"
    spec = {"a": {"tokens": toks, "capabilities": ["governance"]}}
    right = {"sections": [{"title": "Row access policies for tenants", "sql": sql},
                          {"title": "Snowpipe ingestion", "sql": "SELECT 1"}]}
    wrong = {"sections": [{"title": "Row access policies for tenants", "sql": "SELECT 1"},
                          {"title": "Snowpipe ingestion", "sql": sql}]}
    assert "ctx_unused:a" not in verify_plan(right, [], set(), packs=spec)
    assert "ctx_unused:a" in verify_plan(wrong, [], set(), packs=spec)
    assert "ctx_unused:a" not in verify_plan(wrong, [], set(), packs={"a": toks})  # legacy: whole plan


def test_area_sections_match_title_capability_explanation_and_sql():
    from utils.workshop.verify import area_sections
    secs = [{"title": "Semantic Layer with Natural Language Analytics",
             "explanation": "Define a semantic view over the gold tables.", "sql": "SELECT 1"},
            {"title": "Agent", "explanation": "Cortex Agent on top.", "sql": "CREATE AGENT a"},
            {"title": "Model", "explanation": "x", "sql": "CREATE SEMANTIC VIEW v TABLES (t)"}]
    got = area_sections(secs, ["semantic_views", "cortex_agents"])
    assert [s["title"] for s in got] == ["Semantic Layer with Natural Language Analytics", "Model"]
    # primary absent everywhere -> falls back to the area's other capabilities
    assert [s["title"] for s in area_sections(secs[1:2], ["semantic_views", "cortex_agents"])] == ["Agent"]
    assert area_sections(secs, []) == []
    toks = ["TENANT_POLICY", "GITHUB_SUBJECT", "DEPLOYER_ROLE"]
    plan = {"sections": [{"title": "Semantic Layer", "explanation": "semantic view",
                          "sql": "SELECT TENANT_POLICY, GITHUB_SUBJECT, DEPLOYER_ROLE"}]}
    assert "ctx_unused:a" not in verify_plan(plan, [], set(), packs={"a": {"tokens": toks,
                                                                          "capabilities": ["semantic_views"]}})


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


def test_private_urls_never_become_deny_terms():
    from utils.workshop.deny import private_deny_terms
    from utils.workshop.compliance import scrub
    t = private_deny_terms({"SE_COMMENTS": "Notes at https://acme.example.com/x and www.acme.example.com. 40% growth."}, "Acme")
    assert not any(x.lower().startswith(("http", "www")) for x in t)
    u = "https://docs.snowflake.com/en/sql-reference/sql/create-agent"
    assert scrub(u, {u}, t) == u


def test_tie_prefers_pair_stable_across_runs(monkeypatch):
    a, b = ("r/a", "Area"), ("r/b", "Area")
    runs = [{a: 100, b: 100}, {a: 100, b: 100}, {a: 100, b: 70}]
    scores = recipes.aggregate(runs, [a, b])
    assert scores[a] == scores[b] == 100
    tb = {a: (3, 100.0, 1, 1), b: (2, 90.0, 9, 9)}
    assert recipes.select(scores, tiebreak=tb)[0][0] == "r/a"


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
            return json.dumps({"pairs": [{"recipe_id": "t/mt", "area": "Platform: Compliance & Governance",
                                          "goal_match": "strong",
                                          "capability_fit": "strong", "steps_reusable": True,
                                          "audience_fit": True, "contraindicated": False,
                                          "evidence": {"section_goal": "Tenant isolation",
                                                       "recipe_goal": "Tenants share tables",
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
    assert "PAIRS" in judge and "Platform: Compliance & Governance" in judge
    assert "goal_match" in judge and "area_fit" not in judge and "section_goal" in judge
    s2 = [p for p in seen if "pse-uc-implementation-plan" in p][0]
    assert "<DB>.<SCHEMA>.ORDERS" in s2 and "MATCHED_RECIPE" not in s2
    assert out["_context_sources"] == [{"recipe_id": "t/mt", "area": "Platform: Compliance & Governance",
                                        "score": 100}]
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
