import json

from . import assets, capabilities

S1_SCHEMA = ('{"prompts": [{"title": str, "purpose": str, "prompt": str}] '
             '(exactly 3: 1 discovery of relevant data/objects, 2 build with the proposed CoCo skill, 3 extend)}')
S2_SCHEMA = ('{"problem_statement": str, '
             '"executive_summary": [{"topic": str, "previous_state": str, "solution": str}], '
             '"decision_criteria_alignment": [str], '
             '"architecture": {"sources": [str] (generic, e.g. "Source systems (ERP, ticketing)"; no vendor names), '
             '"layers": [{"name": one of Ingestion|Bronze|Silver|Gold|Semantic|Consumption|Sharing|Governance, '
             '"capability": str (the Snowflake feature), "detail": str}], "consumers": [str] (generic)}, '
             '"component_status": [{"component": str, "details": str, "source_url": str}], '
             '"sections": [{"title": str, "challenge": str, "explanation": str, "coco_prompt": str, "sql": str, '
             '"source_url": str, "notes": [str]}] (one per capability area, at most 8), '
             '"coco_skills": [{"skill": str, "what_it_does": str, "steps": str}], '
             '"before_after": [{"task": str, "without": str, "with": str}], '
             '"decision_matrix": [{"topic": str, "verdict": str, "action": str}], '
             '"next_steps": [str], '
             '"resources": {"quickstarts": [{"title": str, "url": str}], '
             '"docs": [{"title": str, "url": str}]}, '
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
- component_status: one row per primary capability. In details, state only concrete, use-case-specific facts;
  include a hard requirement (for example a minimum Snowflake edition) as plain text when status_note gives one.
  Never write generic filler such as "Documented", "GA" or "confirm availability". executive_summary, decision_matrix
  and next_steps: at least 3 rows each; coco_skills: at least 2; resources: at least 1 quickstart and 3 docs.
Grounding
- SQL must follow the syntax of the GROUNDING sql_snippets: copy a snippet and adapt only identifiers to
  <placeholder> or neutral names. Never invent statements, clauses, parameters, functions or views that are not in a
  provided snippet (no COMPUTE_POOL/MODEL/TOOLS clauses on CREATE AGENT, no INVOKER_ROLE, no DATA_AGENT_RUN,
  no *_USAGE_HISTORY views). Keep parameter formats exactly as in the snippet (for example a cron SCHEDULE
  must read 'USING CRON <expr> <time_zone>').
- All GROUNDING sql_snippets are equally authoritative. Weave each one into the template section of
  its capability (implementation steps, SQL, verification checks, notes); do not add a separate section
  for them and never say where any content came from.
- Every section with SQL must set source_url to the source_url of the snippet it adapted.
- Any statement about feature availability or edition requirements comes only from status_note.
- If a needed capability has no snippet, leave sql empty and add the note "Documentation not found - verify with
  your Snowflake SE" instead of guessing syntax.
- resources and component_status.source_url use only URLs from GROUNDING or ALLOWED_LINKS.
- resources has only quickstarts and docs: no GitHub repositories or github.com links anywhere in the plan.
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
- Never use any term in NEVER_MENTION. Never mention the source of any content, and never use the
  words recipe, cookbook, playbook, match or confidence."""


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
JUDGE_SCHEMA = ('{"recipes": [{"recipe_id": str, "problem_fit": "none|partial|strong", '
                '"capability_fit": "none|partial|strong", "steps_reusable": bool, "audience_fit": bool, '
                '"contraindicated": bool, "evidence": {"problem_fit": str, "capability_fit": str, '
                '"steps_reusable": str, "audience_fit": str, "contraindicated": str}}]}')


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


def recipe_judge_prompt(uc, candidates):
    """candidates: recipes.candidate_view dicts. The app scores the rubric answers."""
    return ("Assess how well each candidate build guide fits this use case. For every candidate answer "
            "the rubric, and for each criterion quote a short verbatim phrase from that candidate's text "
            "as evidence (empty string if none). problem_fit: does when_to_use describe this use case's "
            "problem? capability_fit: do how_it_works and steps use the Snowflake features this use case "
            "needs? steps_reusable: can the steps be followed for this use case with only renaming? "
            "audience_fit: are the end users / operators the same kind? contraindicated: does "
            "when_not_to_use describe this use case (quote it)?\n"
            f"USE_CASE:\n{_header(uc, '')}\nCANDIDATES:\n{json.dumps(candidates, indent=0)}\n"
            f"Return JSON: {JUDGE_SCHEMA}")


def session2_prompt(uc, partner, private_context, extra_grounding=None, never_mention=()):
    """extra_grounding: capability -> additional sql_snippets merged into GROUNDING (same
    authority as the bundled grounding); never_mention are deny terms (model input only)."""
    from .recipes import merge_grounding
    # Snippets flagged must_use carry the most use-case-specific steps; the plan has to build on them.
    extra_grounding = {cap: [dict(e, must_use=True) for e in es] for cap, es in (extra_grounding or {}).items()}
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
            f"GROUNDING (offline docs/quickstart research; the only allowed SQL syntax, URLs and feature status). "
            f"Every sql_snippet marked \"must_use\": true must be adapted into the SQL of the matching section "
            f"(keep its object, function and parameter names; replace placeholders with this use case's names). "
            f"Never mention the must_use flag:\n"
            f"{json.dumps(merge_grounding(capabilities.grounding_for(req + optional), extra_grounding))}\n"
            f"PRIVATE_CONTEXT (understand only, never quote):\n{json.dumps(private_context or {})}\n"
            f"NEVER_MENTION: {json.dumps(sorted(set(never_mention)))}\n"
            f"ALLOWED_LINKS:\n{json.dumps(sorted(assets.link_allowlist()))}\nReturn JSON: {S2_SCHEMA}")
