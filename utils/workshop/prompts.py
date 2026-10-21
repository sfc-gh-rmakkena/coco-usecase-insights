import json

from . import assets, capabilities

S1_SCHEMA = ('{"prompts": [{"title": str, "purpose": str, "prompt": str}] '
             '(exactly 3: 1 discovery of relevant data/objects, 2 build with the proposed CoCo skill, 3 extend)}')
S2_SCHEMA = ('{"problem_statement": str, '
             '"executive_summary": [{"topic": str, "previous_state": str, "solution": str, "status": str}], '
             '"decision_criteria_alignment": [str], '
             '"architecture": {"sources": [str] (generic, e.g. "Source systems (ERP, ticketing)"; no vendor names), '
             '"layers": [{"name": one of Ingestion|Bronze|Silver|Gold|Semantic|Consumption|Sharing|Governance, '
             '"capability": str (the Snowflake feature), "detail": str}], "consumers": [str] (generic)}, '
             '"component_status": [{"component": str, "status": str, "details": str, "source_url": str}], '
             '"sections": [{"title": str, "challenge": str, "explanation": str, "coco_prompt": str, "sql": str, '
             '"source_url": str, "notes": [str]}] (one per capability area, at most 8), '
             '"coco_skills": [{"skill": str, "what_it_does": str, "steps": str}], '
             '"before_after": [{"task": str, "without": str, "with": str}], '
             '"decision_matrix": [{"topic": str, "verdict": str, "production_ready": str, "action": str}], '
             '"next_steps": [str], '
             '"resources": {"quickstarts": [{"title": str, "url": str}], '
             '"docs": [{"title": str, "url": str, "status": str}], '
             '"github": [{"title": str, "url": str, "description": str}]}, '
             '"hands_on": {"intro": str, "sql": str, "source_url": str} (optional; leave fields empty if none)}')

S2_RULES = """RULES (mandatory, in addition to the APP OVERRIDE):
Structure
- Follow the skill's Step 5 report structure and its "Content Order in Each Section": for every section give
  the challenge, a 1-2 sentence explanation, then a CoCo prompt that names the CoCo skill to use, then the SQL.
- Write exactly one section per entry in REQUIRED_CAPABILITY_AREAS, in the order listed. Lead with the area's first
  (primary) capability and cover the others briefly in the explanation or notes.
- Then add a section from OPTIONAL_CAPABILITIES for each need the private context describes: slow BI or
  reporting on large tables -> search_optimization; row-level security, RBAC or access-control problems ->
  governance (row access policies); data quality or monitoring -> observability; cost control -> cost.
  At most 8 sections in total.
- architecture.layers: one entry per layer (at least 4), each naming the Snowflake capability used; include the
  primary capability of every REQUIRED_CAPABILITY_AREA. Do not draw a diagram; it is generated from the layers.
- component_status: one row per primary capability (status from status_note). executive_summary, decision_matrix
  and next_steps: at least 3 rows each; coco_skills: at least 2; resources: at least 1 quickstart and 3 docs.
Grounding
- SQL must follow the syntax of the GROUNDING sql_snippets: copy a snippet and adapt only identifiers to
  <placeholder> or neutral names. Never invent statements, clauses, parameters, functions or views that are not in a
  provided snippet (no COMPUTE_POOL/MODEL/TOOLS clauses on CREATE AGENT, no INVOKER_ROLE, no DATA_AGENT_RUN,
  no *_USAGE_HISTORY views). Keep parameter formats exactly as in the snippet (for example a cron SCHEDULE
  must read 'USING CRON <expr> <time_zone>').
- Every section with SQL must set source_url to the source_url of the snippet it adapted.
- Feature status (component_status.status, decision_matrix.production_ready) comes only from status_note.
- If a needed capability has no snippet, leave sql empty and add the note "Documentation not found - verify with
  your Snowflake SE" instead of guessing syntax.
- resources and component_status.source_url use only URLs from GROUNDING or ALLOWED_LINKS.
External sharing (the output goes to the partner and customer)
- Write the problem statement and all text using only general, non-confidential language.
- Do not name any person. Do not name any vendor, product or tool other than Snowflake (no source-system, BI,
  planning or competitor product names; say "existing BI tools", "the planning system", "source systems").
- Do not state any metric, volume, count, percentage, date, year, timeline, fleet or site size taken from internal
  fields. Do not state monetary amounts, budgets, or credit quantities; describe cost controls qualitatively.
- Do not describe the customer's growth or expansion plans, acquisitions, fleet or footprint, and do not describe
  the customer by industry or vertical (say "the customer" or use the account name).
- Do not reuse the wording or headings of internal fields (for example MEDDPICC labels); restate each point in
  your own words.
- Do not name sub-brands, business units, programs, internal platforms or code names beyond the account name.
- Do not name cities, countries or regions beyond those in the use case name. Do not mention industry, website,
  pipeline stage, status, or dates.
- Do not name competitors or compare against other vendors.
- Never use any term in NEVER_MENTION. Do not mention cookbook recipes."""


def _skill_rows(uc, private_context):
    tuc = (private_context or {}).get("TECHNICAL_USE_CASE")
    if tuc and capabilities.matched_rows(tuc):
        return capabilities.matched_rows(tuc)
    skills = set(uc.get("skills") or [])
    return [r for r in capabilities.MAPPING if skills & set(r[2])]


def required_capabilities(uc, private_context) -> list:
    out = []
    for r in _skill_rows(uc, private_context):
        out += [k for k in r[3] if k not in out]
    return out


def capability_areas(uc, private_context) -> list:
    """Required capabilities grouped by technical-use-case area; rows sharing a capability merge."""
    areas = []
    for r in _skill_rows(uc, private_context):
        hit = next((a for a in areas if set(a["capabilities"]) & set(r[3])), None)
        if hit:
            hit["area"] += f" + {r[0]}"
            hit["capabilities"] += [k for k in r[3] if k not in hit["capabilities"]]
            hit["coco_skills"] += [s for s in r[2] if s not in hit["coco_skills"]]
        else:
            areas.append({"area": r[0], "capabilities": list(r[3]), "coco_skills": list(r[2])})
    return areas


def primary_capabilities(uc, private_context) -> list:
    """First (primary) capability of each required area; these must appear in the diagram and status table."""
    out = []
    for a in capability_areas(uc, private_context):
        if a["capabilities"] and a["capabilities"][0] not in out:
            out.append(a["capabilities"][0])
    return out


def session2_repair_prompt(base_prompt, failure_codes, previous_plan):
    """Second pass: same task, plus the gate codes that failed and the previous (already cleaned) JSON."""
    return (f"{base_prompt}\n\n=== REPAIR ===\nYour previous JSON failed these verification checks: "
            f"{json.dumps(list(failure_codes))}.\nReturn the complete JSON again, fixing ONLY these gaps and keeping "
            f"everything else unchanged. All rules above still apply.\nPREVIOUS_JSON:\n{json.dumps(previous_plan)}")
RECIPE_SCHEMA = '{"recipe_id": str, "confidence": int 0-100, "rationale": str}'


_S1_RULES = ("Write general, non-confidential prompts: no people, no vendors other than Snowflake, no metrics, "
             "dates or growth plans, no sub-brands or business units beyond the account name, no locations "
             "beyond the use case name, and never any term in NEVER_MENTION.")


def _header(uc, partner):
    return json.dumps({"account": uc["account"], "use_case": uc["name"], "partner": partner,
                       "proposed_coco_skills": uc["skills"],
                       "internal_summary (understand only, never quote; may contain confidential detail)":
                           uc.get("sanitized_desc", "")})


def session1_prompt(uc, partner, account_signals, never_mention=()):
    signals = ""
    if account_signals:
        signals = "\nACCOUNT_SIGNALS (tiers only, for tailoring; never state them):\n" + json.dumps(account_signals)
    return (f"{assets.override_text()}\n\n=== SKILL: coco-customer-activation-planner ===\n"
            f"{assets.skill_text('coco-customer-activation-planner/SKILL.md')}\n\n"
            f"=== TASK ===\nProduce ONLY the starter-prompts section of the activation brief for a workshop "
            f"Session 1 delivered by the partner and Snowflake with the customer. {_S1_RULES}\nHEADER:\n{_header(uc, partner)}"
            f"{signals}\nNEVER_MENTION: {json.dumps(sorted(set(never_mention)))}\nReturn JSON: {S1_SCHEMA}")


def recipe_match_prompt(uc):
    idx = [{k: r[k] for k in ("id", "title", "description", "topics", "features")} for r in assets.recipes_index()]
    return (f"{assets.override_text()}\n\nPick the single cookbook recipe that best helps build this use case, "
            f"and score confidence 0-100 that following it would substantially deliver the use case.\n"
            f"USE_CASE:\n{_header(uc, '')}\nRECIPES:\n{json.dumps(idx, indent=0)}\nReturn JSON: {RECIPE_SCHEMA}")


def session2_prompt(uc, partner, private_context, recipe, never_mention=()):
    """recipe is passed only for a full-band match; never_mention are deny terms (model input only)."""
    rec = ""
    if recipe:
        rec = f"\nMATCHED_RECIPE (align the plan with it): {json.dumps(recipe)}"
    rows = _skill_rows(uc, private_context)
    req = required_capabilities(uc, private_context)
    optional = [k for k in capabilities.OPTIONAL if k not in req]
    table = [{"technical_use_case": r[0], "capabilities": r[1], "coco_skills": r[2], "grounding_keys": r[3]} for r in rows]
    return (f"{assets.override_text()}\n\n=== SKILL: pse-uc-implementation-plan ===\n"
            f"{assets.skill_text('pse-uc-implementation-plan/SKILL.md')}\n\n"
            f"=== REPORT TEMPLATE (section structure reference) ===\n"
            f"{assets.skill_text('pse-uc-implementation-plan/templates/report_template.html')[:12000]}\n\n"
            f"=== TASK ===\nProduce the implementation plan content for a co-build workshop Session 2, following the "
            f"skill's report structure. Do not state any monetary amounts, budgets, or credit quantities; describe "
            f"cost controls qualitatively. Do not name competitors or compare against other vendors.\n{S2_RULES}\n"
            f"HEADER:\n{_header(uc, partner)}\n"
            f"CAPABILITY_MAPPING (from the skill table, for this use case):\n{json.dumps(table)}\n"
            f"REQUIRED_CAPABILITIES (in order): {json.dumps(req)}\n"
            f"REQUIRED_CAPABILITY_AREAS (one section each, in order): {json.dumps(capability_areas(uc, private_context))}\n"
            f"OPTIONAL_CAPABILITIES: {json.dumps(optional)}\n"
            f"GROUNDING (offline docs/quickstart research; the only allowed SQL syntax, URLs and feature status):\n"
            f"{json.dumps(capabilities.grounding_for(req + optional))}\n"
            f"PRIVATE_CONTEXT (understand only, never quote):\n{json.dumps(private_context or {})}{rec}\n"
            f"NEVER_MENTION: {json.dumps(sorted(set(never_mention)))}\n"
            f"ALLOWED_LINKS:\n{json.dumps(sorted(assets.link_allowlist()))}\nReturn JSON: {S2_SCHEMA}")
