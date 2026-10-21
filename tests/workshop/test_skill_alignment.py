import io
import json
import re

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate

from tests.workshop.test_generator import SRC, UC, s2_payload
from utils.workshop import assets, capabilities, generator, prompts
from utils.workshop.compliance import classify_violations, find_violations
from utils.workshop.deny import private_deny_terms
from utils.workshop.render_html import S2_HEADINGS, render_workshop_html
from utils.workshop.render_pdf import workshop_pdf_flowables

DISNEY_UC = {"uc_id": "aPaVI00000iDZP60AO", "name": "DX - Financial Transformation (Phase 3, Asia Parks + Cruises)",
             "account": "Disney Experiences (DX)", "skills": ["dynamic-tables"], "sanitized_desc": "",
             "stage_label": "Implementation"}
# Synthetic stand-in for the private Salesforce context (strings mirror the leak classes seen in DEV).
DISNEY_CTX = {
    "TECHNICAL_USE_CASE": "Analytics: Applied Analytics;Analytics: Business Intelligence;Analytics: Lakehouse Analytics;"
                          "Apps & Collab: Internal Collaboration;DE: Ingestion;DE: Transformation",
    "DESCRIPTION": "Phase 3 migrates Disney Signature Experiences (DSE), specifically the Disney Cruise Line (DCL), "
                   "into the Helix/Medallion platform. Governed by CAR 3, led by Dave Ramos. Supports doubling the "
                   "fleet by 2031 with integration into the Oracle EPM loop.",
    "MEDDPICC_METRICS": "Fleet Scalability: Support a fleet expansion from 5 to 13 ships by 2031.",
    "MEDDPICC_PAIN": "High data volumes (10B+ records) lead to slow performance in PowerBI, Business Objects.",
    "MEDDPICC_DECISION_PROCESS": "Deloitte provides the design for the 19 identified systems. Meetings with "
                                 "Deloitte (Kam), LTI, and EY. Phase 1 (US) and Phase 2 (Paris).",
    "SE_COMMENTS": "Discussed patterns with Caleb to connect data from China (DL Shanghai and Hongkong). "
                   "Caleb and Brian to meet the team. Compared to Cursor.",
    "NEXT_STEPS": "Roadmap session w/ Dave Ramos and Brian Reif to unblock CAR 3 design.",
    "STAGE": "4 - Use Case Won / Migration Plan", "INDUSTRY": "Travel & Hospitality",
    "BILLING_COUNTRY": "United States", "BILLING_STATE": "Florida", "WEBSITE": "disney.com",
    "CLOUD_REGION": "US East - N. Virginia", "GO_LIVE_DATE": "2027-05-26",
}
MUST_DENY = ["Dave", "Ramos", "Caleb", "Brian", "Reif", "Kam", "Oracle", "EPM", "PowerBI", "Business Objects",
             "Helix", "CAR 3", "LTI", "EY", "Shanghai", "Hongkong", "Paris", "China", "Disney Signature Experiences",
             "Disney Cruise Line", "2031", "10B+", "10B", "13 ships", "19 identified", "Travel & Hospitality",
             "US East", "Florida", "disney.com", "Cursor", "Use Case Won", "fleet expansion",
             "expanding the fleet", "doubling the fleet", "Cruise Line", "Signature Experiences"]


def _llm(s2):
    def llm(p):
        if "Pick the single cookbook recipe" in p:
            return json.dumps({"recipe_id": assets.recipes_index()[0]["id"], "confidence": 72, "rationale": "x"})
        if "starter-prompts" in p:
            return json.dumps({"prompts": [{"title": "t", "purpose": "p", "prompt": "do x"}] * 3})
        llm.s2_prompt = p
        return json.dumps(s2)
    return llm


# 1. Recipe steering only for the full band
def test_reference_band_recipe_not_passed_to_plan():
    llm = _llm(s2_payload())
    out = generator.build_one(UC, "D", None, {}, llm)
    assert out["session2"]["recipe"]["band"] == "reference" and out["session2"]["recipe"]["body"] == ""
    assert "MATCHED_RECIPE" not in llm.s2_prompt


def test_full_band_recipe_passed_to_plan():
    from tests.workshop.test_generator import fake_llm_factory
    seen = []
    base = fake_llm_factory(recipe_conf=90)
    generator.build_one(UC, "D", None, {}, lambda p: (seen.append(p), base(p))[1])
    assert any("MATCHED_RECIPE" in p for p in seen if "pse-uc-implementation-plan" in p)


# 2. Deterministic capability mapping
def test_mapping_has_all_skill_rows():
    assert len(capabilities.MAPPING) == 18
    skill = assets.skill_text("pse-uc-implementation-plan/SKILL.md")
    for tuc, *_ in capabilities.MAPPING:
        assert f"| {tuc} |" in skill


def test_required_capabilities_from_technical_use_case():
    caps = capabilities.required_capabilities("DE: Ingestion;DE: Transformation;Analytics: Business Intelligence")
    assert caps[:4] == ["openflow", "snowpipe", "snowpipe_streaming", "copy_into"]
    assert "dynamic_tables" in caps and "semantic_views" in caps and caps.index("openflow") < caps.index("semantic_views")
    assert {"openflow", "dynamic_tables", "semantic_views"} <= set(capabilities.grounding_for(caps))


def test_unlisted_technical_use_case_falls_back_to_family():
    assert capabilities.required_capabilities("Apps & Collab: Internal Collaboration") == ["collaboration"]


def test_session2_prompt_lists_required_capabilities_and_grounding():
    p = prompts.session2_prompt(DISNEY_UC, "Deloitte Consulting", DISNEY_CTX, None, ["Oracle"])
    req = json.loads(re.search(r"REQUIRED_CAPABILITIES \(in order\): (\[.*?\])", p).group(1))
    assert req[0] == "openflow" and "semantic_views" in req and "collaboration" in req
    assert "GROUNDING" in p and "sql-server-cdc/setup" in p
    assert "verify with" in p and "NEVER_MENTION" in p and '"Oracle"' in p
    assert "general, non-confidential language" in p and "MATCHED_RECIPE" not in p


def test_capability_areas_merge_overlapping_rows():
    areas = prompts.capability_areas(DISNEY_UC, DISNEY_CTX)
    assert [a["area"].split(" + ")[0] for a in areas] == [
        "DE: Ingestion", "DE: Transformation", "Analytics: Applied Analytics", "Analytics: Lakehouse Analytics",
        "Apps & Collab: External Collaboration"]
    assert "Analytics: Business Intelligence" in areas[2]["area"] and areas[0]["capabilities"][0] == "openflow"


def test_session2_prompt_falls_back_to_skills_without_tuc():
    p = prompts.session2_prompt(UC, "D", {}, None)
    assert '"ml"' in re.search(r"REQUIRED_CAPABILITIES \(in order\): (\[.*?\])", p).group(1)


# 3. Grounding corpus integrity
def test_grounding_covers_every_mapped_capability_and_is_allowlisted():
    g = capabilities.grounding()
    keys = {k for r in capabilities.MAPPING for k in r[3]} | set(capabilities.OPTIONAL)
    assert keys <= set(g)
    allow = assets.link_allowlist()
    for k, v in g.items():
        assert v["status_note"] and v["docs"] and v["sql_snippets"], k
        for s in v["sql_snippets"]:
            assert s["source_url"].startswith("https://") and s["source_url"] in allow
            assert find_violations(s["sql"], sql=True) == [], (k, s["title"])
        for d in v["docs"] + v["quickstarts"] + v["github"]:
            assert d["url"] in allow


# 4. Output shape
def test_plan_shape_defaults_on_every_path():
    ok = generator.build_one(UC, "D", None, {}, _llm(s2_payload()))
    bad = generator.build_one(UC, "D", None, {}, _llm({"sections": "nope", "resources": [1]}))
    for out in (ok, bad):
        plan = out["session2"]["plan"]
        assert set(plan) == set(generator.PLAN_DEFAULT)
        assert set(plan["resources"]) == {"quickstarts", "docs", "github"}
    assert ok["_degraded"] is False and bad["_degraded"] is True
    assert generator._shape({})["sections"] == [] and generator._shape(None)["architecture_flow"] == ""


def test_architecture_flow_keeps_spacing_and_drops_leaky_lines():
    flow = "Sources\n   |  Openflow CDC\n   v\nBRONZE   raw\nPowerBI dashboards"
    out = generator.build_one(UC, "D", None, {}, _llm(s2_payload(architecture_flow=flow)), deny=["PowerBI"])
    assert out["session2"]["plan"]["architecture_flow"] == "Sources\n   |  Openflow CDC\n   v\nBRONZE   raw"


# 5. Renderers
FULL_PLAN = dict(s2_payload(architecture_flow="A\n  |\n  v\nB"),
                 executive_summary=[{"topic": "t", "previous_state": "p", "solution": "s", "status": "Recommended"}],
                 decision_criteria_alignment=["one"], architecture_layers=["bronze"],
                 component_status=[{"component": "Dynamic Tables", "status": "GA", "details": "d", "source_url": SRC}],
                 coco_skills=[{"skill": "dynamic-tables", "what_it_does": "w", "steps": "s"}],
                 before_after=[{"task": "t", "without": "a", "with": "b"}],
                 decision_matrix=[{"topic": "t", "verdict": "Adopt", "production_ready": "Yes", "action": "a"}],
                 next_steps=["first", "second"],
                 resources={"quickstarts": [{"title": "Q", "url": SRC}], "docs": [{"title": "D", "url": SRC}],
                            "github": [{"title": "Bad", "url": "javascript:alert(1)"}]})
WS = [{"uc_id": "u", "account": "Roche", "name": "N <x>", "skills": ["dynamic-tables"], "brief": "b",
       "session1": [{"title": "T", "purpose": "P", "prompt": "do"}] * 3,
       "session2": {"recipe": {"band": "reference", "title": "R", "confidence": 72}, "plan": FULL_PLAN}}]


def test_html_session2_follows_skill_order():
    h = render_workshop_html(WS)
    import html as _html
    pos = [h.find(f">{_html.escape(t)}<") for t in S2_HEADINGS]
    assert all(p > 0 for p in pos) and pos == sorted(pos)
    assert "CoCo Prompt:" in h and "Source: <a" in h and "<ol><li>first</li>" in h
    assert "<script" not in h.lower() and "javascript:" not in h
    assert h.find("Closest recipe") < h.find(">Problem Statement<") > 0
    assert not re.search(r"\son[a-z]+\s*=", h.lower())


def test_pdf_session2_builds_with_links_and_tables():
    ss = getSampleStyleSheet()
    styles = {"heading2": ss["Heading2"], "body": ss["BodyText"], "cell": ss["BodyText"]}
    flow = workshop_pdf_flowables(WS, styles)
    names = {type(f).__name__ for f in flow}
    assert {"Table", "Preformatted", "Paragraph"} <= names
    assert any("<link href=" in getattr(f, "text", "") for f in flow)
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter).build(flow)
    assert buf.getvalue()[:4] == b"%PDF"


# 6. Compliance
def test_private_deny_terms_disney_fixture():
    terms = {t.lower() for t in private_deny_terms(DISNEY_CTX, DISNEY_UC["account"])}
    missing = [t for t in MUST_DENY if t.lower() not in terms]
    assert not missing, missing
    # Generic / public terms are not denied.
    for t in ("Business Intelligence", "Data Engineering", "Snowflake", "Medallion", "Disney Experiences",
              "data growth", "Cruises"):
        assert t.lower() not in terms


def test_exemption_uses_use_case_name_and_account_only():
    deny = private_deny_terms(DISNEY_CTX, DISNEY_UC["account"]) + ["Asia"]
    kept = generator._exempt(deny, dict(DISNEY_UC, sanitized_desc="Disney Cruise Line and Shanghai"), "Deloitte")
    assert "Asia" not in kept and "Disney Cruise Line" in kept and "Shanghai" in kept


def test_disney_leaks_scrubbed_end_to_end():
    leak = ("Disney Signature Experiences grows from 5 to 13 ships by 2031 with 10B+ records in Shanghai. "
            "Dave Ramos replaces Oracle EPM and PowerBI. Build a governed medallion layer.")
    payload = s2_payload(leak, architecture_flow="Sources\nOracle EPM feed\nGOLD")
    payload["sections"][0]["sql"] = "CREATE RESOURCE MONITOR m WITH CREDIT_QUOTA = 500;"
    out = generator.build_one(DISNEY_UC, "Deloitte Consulting", None, DISNEY_CTX, _llm(payload))
    text = json.dumps(out)
    for t in MUST_DENY + ["CREDIT_QUOTA", "Travel"]:
        assert t not in text, t
    assert out["brief"] == "Build a governed medallion layer."


def test_short_caps_terms_match_case_sensitively():
    assert find_violations("let us build", ["US"]) == []
    assert find_violations("US East region", ["US"]) != []


def test_industry_words_and_meddpicc_labels_denied():
    ctx = dict(DISNEY_CTX, MEDDPICC_DECISION_CRITERIA="Cross-Site Standard: mirror domestic parks. Ease of Use: fewer sources.")
    terms = {t.lower() for t in private_deny_terms(ctx, DISNEY_UC["account"])}
    assert {"travel", "hospitality", "travel and hospitality", "cross-site standard", "ease of use"} <= terms


def test_invented_identifiers_scrubbed_from_prose():
    p = s2_payload()
    p["next_steps"] = ["Monitor usage with CORTEX_AGENT_USAGE_HISTORY.", "Pilot one subject area."]
    out = generator.build_one(UC, "D", None, {}, _llm(p))
    assert out["session2"]["plan"]["next_steps"] == ["Pilot one subject area."]


def test_judge_summary_marked_internal_in_header():
    assert "internal_summary (understand only" in prompts.session1_prompt(UC, "D", None, ["x"])
    assert "NEVER_MENTION" in prompts.session1_prompt(UC, "D", None, ["x"])


def test_cron_schedule_without_using_cron_is_dropped():
    p = s2_payload(n=4)
    p["sections"][0]["sql"] = "CREATE TASK t\n  WAREHOUSE='wh'\n  SCHEDULE='0 6 * * *'\n  AS SELECT 1;"
    p["sections"][1]["sql"] = "CREATE TASK t\n  SCHEDULE='USING CRON 24 * * * * America/Los_Angeles'\n  AS SELECT 1;"
    secs = generator.build_one(UC, "D", None, {}, _llm(p))["session2"]["plan"]["sections"]
    assert secs[0]["sql"] == "" and secs[1]["sql"]


def test_credit_quota_patterns():
    assert "credits" in classify_violations("CREATE RESOURCE MONITOR m WITH CREDIT_QUOTA = 500")
    assert "credits" in classify_violations("set a credit limit: 200 for the team")
    assert generator._clean_sql("CREATE RESOURCE MONITOR m WITH CREDIT_QUOTA=500;") == ""
    assert generator._clean_sql("CREATE RESOURCE MONITOR m WITH CREDIT_QUOTA = <credit_quota>;") != ""
