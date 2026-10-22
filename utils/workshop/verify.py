"""Session 2 plan gates ported from the pse-uc-implementation-plan skill's Step 9 verification.

verify_plan returns short failure codes only (never plan text), in check order.
"""
import json
import re

from . import capabilities, diagram
from .compliance import classify_violations

# A selected guide counts as used only when this many of its distinctive identifiers appear.
CTX_MIN_HITS = 3

MIN = {"executive_summary": 3, "layers": 4, "sql_sections": 3, "coco_skills": 2, "decision_matrix": 3,
       "next_steps": 3, "quickstarts": 1, "docs": 3}


def _d(v):
    return v if isinstance(v, dict) else {}


def _l(v):
    return v if isinstance(v, list) else []


def diagram_text(plan) -> str:
    plan = _d(plan)
    arch = _d(plan.get("architecture"))
    return diagram.render(arch) if _l(arch.get("layers")) else str(plan.get("architecture_flow") or "")


def _links(plan):
    res = _d(plan.get("resources"))
    out = [_d(x).get("url") for k in ("quickstarts", "docs") for x in _l(res.get(k))]
    out += [_d(x).get("source_url") for x in _l(plan.get("sections")) + _l(plan.get("component_status"))]
    out.append(_d(plan.get("hands_on")).get("source_url"))
    return [str(u) for u in out if u]


def attribution_hits(plan, backstop) -> bool:
    text = json.dumps(_d(plan))
    return any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text, re.I) for t in backstop or ())


def verify_plan(plan, required_caps, allow, deny=(), packs=None, backstop=()) -> list:
    """packs: {recipe_id: [distinctive pack tokens]} for the selected guides; backstop: terms
    that would attribute content to them."""
    plan = _d(plan)
    allow = {str(u).rstrip("/") for u in allow or ()}
    fails = []

    def chk(ok, code):
        if not ok and code not in fails:
            fails.append(code)

    secs = [_d(s) for s in _l(plan.get("sections"))]
    sql_secs = [s for s in secs if str(s.get("sql") or "").strip()]
    comps = [_d(r) for r in _l(plan.get("component_status"))]
    res = _d(plan.get("resources"))
    layers = _l(_d(plan.get("architecture")).get("layers")) or _l(plan.get("architecture_layers"))
    chk(str(plan.get("problem_statement") or "").strip(), "problem_statement")
    chk(len(_l(plan.get("executive_summary"))) >= MIN["executive_summary"], "executive_summary")
    chk(len(layers) >= MIN["layers"], "architecture_layers")
    chk(len(comps) >= max(1, len(required_caps or ())), "component_status")
    chk(len(sql_secs) >= MIN["sql_sections"], "sql_sections")
    chk(len(_l(plan.get("coco_skills"))) >= MIN["coco_skills"], "coco_skills")
    chk(len(_l(plan.get("decision_matrix"))) >= MIN["decision_matrix"], "decision_matrix")
    chk(len(_l(plan.get("next_steps"))) >= MIN["next_steps"], "next_steps")
    chk(len(_l(res.get("quickstarts"))) >= MIN["quickstarts"], "quickstarts")
    chk(len(_l(res.get("docs"))) >= MIN["docs"], "docs")
    chk(all(str(s.get("source_url") or "").rstrip("/") in allow for s in sql_secs), "sql_source")
    chk(sum(1 for s in secs if str(s.get("coco_prompt") or "").strip()) == len(secs), "coco_prompt_count")
    flow = diagram_text(plan)
    for k in required_caps or ():
        chk(capabilities.cap_matches(k, flow), f"diagram_missing:{k}")
        chk(any(capabilities.cap_matches(k, r.get("component")) for r in comps), f"component_missing:{k}")
    chk("github.com" not in json.dumps(plan).lower(), "github_link")
    chk(all(u.startswith("https://") and u.rstrip("/") in allow for u in _links(plan)), "link")
    for c in classify_violations(json.dumps(plan), deny):
        if c != "credits":
            chk(False, f"leak:{c}")
    upper = json.dumps(plan).upper()
    for rid, toks in (packs or {}).items():
        if toks:
            hits = sum(bool(re.search(r"(?<![\w])" + re.escape(t) + r"(?![\w])", upper)) for t in toks)
            chk(hits >= min(CTX_MIN_HITS, len(toks)), f"ctx_unused:{rid}")
    chk(not attribution_hits(plan, backstop), "attribution")
    return fails
