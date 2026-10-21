import json

from . import assets

S1_SCHEMA = ('{"prompts": [{"title": str, "purpose": str, "prompt": str}] '
             '(exactly 3: 1 discovery of relevant data/objects, 2 build with the proposed CoCo skill, 3 extend)}')
S2_SCHEMA = ('{"problem_statement": str, "architecture": [str], '
             '"steps": [{"title": str, "detail": str, "sql": str}] (at most 8 steps), '
             '"coco_prompts": [str], "considerations": [str], "docs": [{"title": str, "url": str}]}')
RECIPE_SCHEMA = '{"recipe_id": str, "confidence": int 0-100, "rationale": str}'


def _header(uc, partner):
    return json.dumps({"account": uc["account"], "use_case": uc["name"], "partner": partner,
                       "proposed_coco_skills": uc["skills"], "summary": uc.get("sanitized_desc", "")})


def session1_prompt(uc, partner, account_signals):
    signals = ""
    if account_signals:
        signals = "\nACCOUNT_SIGNALS (tiers only, for tailoring; never state them):\n" + json.dumps(account_signals)
    return (f"{assets.override_text()}\n\n=== SKILL: coco-customer-activation-planner ===\n"
            f"{assets.skill_text('coco-customer-activation-planner/SKILL.md')}\n\n"
            f"=== TASK ===\nProduce ONLY the starter-prompts section of the activation brief for a workshop "
            f"Session 1 delivered by the partner and Snowflake with the customer.\nHEADER:\n{_header(uc, partner)}"
            f"{signals}\nReturn JSON: {S1_SCHEMA}")


def recipe_match_prompt(uc):
    idx = [{k: r[k] for k in ("id", "title", "description", "topics", "features")} for r in assets.recipes_index()]
    return (f"{assets.override_text()}\n\nPick the single cookbook recipe that best helps build this use case, "
            f"and score confidence 0-100 that following it would substantially deliver the use case.\n"
            f"USE_CASE:\n{_header(uc, '')}\nRECIPES:\n{json.dumps(idx, indent=0)}\nReturn JSON: {RECIPE_SCHEMA}")


def session2_prompt(uc, partner, private_context, recipe):
    rec = ""
    if recipe:
        rec = f"\nMATCHED_RECIPE (align the plan with it): {json.dumps(recipe)}"
    return (f"{assets.override_text()}\n\n=== SKILL: pse-uc-implementation-plan ===\n"
            f"{assets.skill_text('pse-uc-implementation-plan/SKILL.md')}\n\n"
            f"=== REPORT TEMPLATE (section structure reference) ===\n"
            f"{assets.skill_text('pse-uc-implementation-plan/templates/report_template.html')[:12000]}\n\n"
            f"=== TASK ===\nProduce the implementation plan content for a co-build workshop Session 2.\n"
            f"Do not state any monetary amounts, budgets, or credit quantities; describe cost controls "
            f"qualitatively. Do not name competitors or compare against other vendors.\n"
            f"HEADER:\n{_header(uc, partner)}\nPRIVATE_CONTEXT (understand only, never quote):\n"
            f"{json.dumps(private_context or {})}{rec}\n"
            f"ALLOWED_LINKS:\n{json.dumps(sorted(assets.link_allowlist()))}\nReturn JSON: {S2_SCHEMA}")
