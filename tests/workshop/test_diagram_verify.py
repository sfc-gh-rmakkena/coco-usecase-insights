import json

from tests.workshop.test_generator import SRC, UC, s2_payload
from tests.workshop.test_template_parity import FIXTURE, REQUIRED
from utils.workshop import assets, diagram, generator, prompts
from utils.workshop.css_scope import prefix_css, selectors
from utils.workshop.verify import verify_plan

ARCH = FIXTURE["session2"]["plan"]["architecture"]
ALLOW = assets.link_allowlist()


# diagram.py
def test_diagram_deterministic_bounded_and_complete():
    a, b = diagram.render(ARCH), diagram.render(json.loads(json.dumps(ARCH)))
    assert a == b
    assert max(len(l) for l in a.split("\n")) <= diagram.MAX_WIDTH
    for l in ARCH["layers"]:
        assert l["capability"] in a
    assert a.index("BRONZE") < a.index("SILVER") < a.index("GOLD") < a.index("GOVERNANCE")


def test_diagram_width_bound_on_long_text_and_defaults():
    long = {"sources": ["x" * 300], "layers": [{"name": "Gold", "capability": "C" * 200, "detail": "d" * 300}],
            "consumers": ["y" * 300]}
    out = diagram.render(long)
    assert max(len(l) for l in out.split("\n")) <= diagram.MAX_WIDTH
    empty = diagram.render({})
    assert "BRONZE" in empty and "Dynamic Tables" in empty


def test_diagram_ascii_and_bullets():
    assert all(ord(c) < 128 for c in diagram.to_ascii(diagram.render(ARCH)).replace("&", ""))
    assert diagram.layer_bullets(ARCH)[0] == "Ingestion: Openflow — CDC connectors, incremental replication"


# css_scope.py
def test_css_prefixer():
    css = (":root{--a:1} * {margin:0} body{color:#333} html body p{x:1} h1, .toc a:hover{c:1} /* c */"
           "@media print{.header{b:1} pre{w:1}} @font-face{src:url(x)}")
    out = prefix_css(css, ".sgx")
    assert selectors(out) == [".sgx", ".sgx *", ".sgx", ".sgx body p", ".sgx h1", ".sgx .toc a:hover",
                              ".sgx .header", ".sgx pre"]
    assert "@media print{" in out and "font-face" not in out and "/*" not in out


# verify.py
def _plan():
    return json.loads(json.dumps(FIXTURE["session2"]["plan"]))


def test_verify_fixture_passes():
    assert verify_plan(_plan(), REQUIRED, ALLOW) == []


def test_verify_each_failure_code():
    cases = {
        "problem_statement": lambda p: p.update(problem_statement=""),
        "executive_summary": lambda p: p.update(executive_summary=p["executive_summary"][:2]),
        "architecture_layers": lambda p: p["architecture"].update(layers=p["architecture"]["layers"][:3]),
        "component_status": lambda p: p.update(component_status=p["component_status"][:1]),
        "sql_sections": lambda p: [s.update(sql="") for s in p["sections"][2:]],
        "coco_skills": lambda p: p.update(coco_skills=p["coco_skills"][:1]),
        "decision_matrix": lambda p: p.update(decision_matrix=p["decision_matrix"][:2]),
        "next_steps": lambda p: p.update(next_steps=p["next_steps"][:2]),
        "quickstarts": lambda p: p["resources"].update(quickstarts=[]),
        "docs": lambda p: p["resources"].update(docs=p["resources"]["docs"][:2]),
        "sql_source": lambda p: p["sections"][0].update(source_url="https://example.com/x"),
        "coco_prompt_count": lambda p: p["sections"][0].update(coco_prompt=""),
        "diagram_missing:openflow": lambda p: p["architecture"]["layers"].pop(0),
        "component_missing:openflow": lambda p: p.update(component_status=[
            r for r in p["component_status"] if "openflow" not in r["component"].lower()]),
        "github_link": lambda p: p["resources"]["docs"].append({"title": "x", "url": "https://github.com/x"}),
        "link": lambda p: p["resources"]["docs"].append({"title": "x", "url": "http://example.com/x"}),
        "leak:money": lambda p: p.update(problem_statement="Budget is $2M."),
    }
    for code, mutate in cases.items():
        p = _plan()
        mutate(p)
        assert code in verify_plan(p, REQUIRED, ALLOW), code
    assert "leak:deny" in verify_plan(dict(_plan(), problem_statement="Use Acme."), REQUIRED, ALLOW, ["Acme"])


# generator: deterministic fill + repair pass
def _llm(first, second=None):
    seen = []

    def llm(p):
        seen.append(p)
        if "Pick the single cookbook recipe" in p:
            return json.dumps({"recipe_id": "nope", "confidence": 0})
        if "starter-prompts" in p:
            return json.dumps({"prompts": [{"title": "t", "purpose": "p", "prompt": "do x"}] * 3})
        return json.dumps(second if second is not None and "=== REPAIR ===" in p else first)
    llm.seen = seen
    return llm


def test_missing_required_capability_injected():
    out = generator.build_one(UC, "D", None, {}, _llm(s2_payload()))
    plan, why = out["session2"]["plan"], out["_degraded_reasons"]
    assert any(l["capability"] == "Snowpark ML" for l in plan["architecture"]["layers"])
    assert any(r["component"] == "Snowpark ML" and "status" not in r and r["source_url"] for r in plan["component_status"])
    assert "s2:arch_filled" in why and "Snowpark ML" in diagram.render(plan["architecture"])
    assert plan["architecture_layers"]


def test_repair_pass_sends_codes_and_picks_better():
    good = dict(FIXTURE["session2"]["plan"])
    llm = _llm(s2_payload(), good)
    out = generator.build_one(UC, "D", None, {}, llm)
    repair = [p for p in llm.seen if "=== REPAIR ===" in p]
    assert len(repair) == 1 and '"executive_summary"' in repair[0].split("PREVIOUS_JSON")[0]
    plan = out["session2"]["plan"]
    assert len(plan["executive_summary"]) >= 3 and out["_degraded"] is False
    assert not [r for r in out["_degraded_reasons"] if r.startswith("s2:verify:")]


def test_repair_not_better_keeps_first_and_records_codes():
    llm = _llm(s2_payload(), {"sections": []})
    out = generator.build_one(UC, "D", None, {}, llm)
    assert len(out["session2"]["plan"]["sections"]) == 3 and out["_degraded"] is False
    assert "s2:verify:executive_summary" in out["_degraded_reasons"]


def test_no_repair_when_plan_passes():
    llm = _llm(FIXTURE["session2"]["plan"])
    generator.build_one(dict(UC, skills=["dynamic-tables"]), "D", None,
                        {"TECHNICAL_USE_CASE": "DE: Transformation"}, llm)
    assert not [p for p in llm.seen if "=== REPAIR ===" in p]


def test_legacy_architecture_flow_still_renders():
    from utils.workshop.render_html import render_workshop_html
    plan = generator._shape(s2_payload(architecture_flow="A\n  |\n  v\nB"))
    h = render_workshop_html([dict(FIXTURE, session2={"recipe": {}, "plan": plan})])
    assert "<pre>A\n  |\n  v\nB</pre>" in h


def test_hands_on_optional_section():
    from utils.workshop.render_html import render_workshop_html
    plan = dict(FIXTURE["session2"]["plan"], hands_on={"intro": "Try it", "sql": "SELECT 1", "source_url": SRC})
    h = render_workshop_html([dict(FIXTURE, session2={"recipe": {}, "plan": plan})])
    assert "8. Hands-On Exercise" in h and h.count('href="#sgx0-') == 8
    assert "8. Hands-On Exercise" not in render_workshop_html([FIXTURE])


def test_primary_capabilities():
    from tests.workshop.test_skill_alignment import DISNEY_CTX, DISNEY_UC
    assert prompts.primary_capabilities(DISNEY_UC, DISNEY_CTX) == [
        "openflow", "dynamic_tables", "semantic_views", "iceberg", "collaboration"]
