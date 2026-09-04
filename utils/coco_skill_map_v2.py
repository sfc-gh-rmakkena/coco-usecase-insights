"""
Enhanced, reusable skill-mapping module for PSE Email pages.

Superset of coco_skill_map.py: re-exports everything from it unchanged (the
deterministic Technical-Use-Case -> skill mapping, migration detection, peer
group constants, etc.), then adds an AI-driven catalog-matching layer on top,
grounded in the real 111-skill CoCo catalog (COCO_SKILLS.md) plus the use
case's sanitized description, SE_COMMENTS, and PARTNER_COMMENTS.

Future email tabs should import from THIS module instead of coco_skill_map
to get both layers. coco_skill_map.py itself stays untouched for any other
consumers of the deterministic base layer.
"""
import json
import re
from pathlib import Path

from utils.coco_skill_map import *  # noqa: F401,F403 -- re-export deterministic base
from utils.coco_skill_map import (  # explicit re-export for static analysis / clarity
    map_coco_skills_explained, detect_migration, h,
)

_SKILLS_MD_PATH = Path(__file__).parent / "COCO_SKILLS.md"


def _parse_skill_catalog() -> list:
    """One-time regex parse of COCO_SKILLS.md into a condensed catalog:
    [{"name": ..., "summary": ..., "surface": ..., "use_cases": [...]}].

    Each skill entry in the source doc is a block starting with a
    `### `skill-name`` header, bounded by the next such header. Blocks are
    also separated by a `---` rule, but bounding on the next header alone is
    sufficient and simpler; the extraction below only pulls specific
    `**Field:**` patterns near the top of each block rather than consuming
    it to the boundary, so it is robust even for the final block (which
    otherwise runs into the Appendix)."""
    text = _SKILLS_MD_PATH.read_text()
    blocks = re.split(r"\n### `", text)[1:]  # drop preamble/index before first skill
    catalog = []
    for block in blocks:
        name_match = re.match(r"([^`]+)`", block)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        summary_match = re.search(r"\n> (.+)", block)
        surface_match = re.search(r"\*\*Snowflake surface it drives:\*\*\s*(.+)", block)
        uc_match = re.search(r"\*\*Representative use cases\*\*\n((?:- .+\n?)+)", block)
        use_cases = []
        if uc_match:
            use_cases = [
                line.lstrip("- ").strip().strip('"')
                for line in uc_match.group(1).splitlines() if line.strip()
            ][:2]
        catalog.append({
            "name": name,
            "summary": (summary_match.group(1).strip() if summary_match else "")[:200],
            "surface": (surface_match.group(1).strip() if surface_match else "")[:250],
            "use_cases": use_cases,
        })
    return catalog


COCO_SKILL_CATALOG = _parse_skill_catalog()
COCO_SKILL_NAMES = frozenset(s["name"].lower() for s in COCO_SKILL_CATALOG)


def coco_skill_catalog_prompt_block() -> str:
    """Condensed catalog as prompt-ready text, built once at import time and
    reused verbatim across all per-use-case AI calls."""
    lines = []
    for s in COCO_SKILL_CATALOG:
        ucs = "; ".join(s["use_cases"])
        lines.append(f"- {s['name']}: {s['surface']}" + (f" (e.g. {ucs})" if ucs else ""))
    return "\n".join(lines)


_COCO_SKILL_CATALOG_BLOCK = coco_skill_catalog_prompt_block()


def build_ai_skill_prompt(desc: str, se_comments: str, deterministic_skills: list, partner_comments: str = "",
                          name: str = "") -> str:
    """Build the prompt for one use case's AI summary + rationale + additional-
    skills call. The caller (page file) is responsible for actually invoking
    the LLM and passing the raw response to parse_ai_skill_response().

    Skill SELECTION beyond the deterministic set is grounded in the real
    111-skill catalog so it can never invent a skill that doesn't exist;
    parse_ai_skill_response() double-checks this with a hard validation
    step regardless of what the prompt asks for. Every use case is capped
    at MAX_SKILLS_PER_USE_CASE total (relevance over quantity, enforced
    downstream by cap_skills()) -- this prompt tells the AI exactly how
    much capacity remains so it doesn't waste effort suggesting skills that
    would just get truncated away."""
    skills_str = ", ".join(deterministic_skills) if deterministic_skills else "CoCo"
    remaining = max(0, MAX_SKILLS_PER_USE_CASE - len(deterministic_skills))
    # The use case NAME is often the single most explicit signal (e.g. a name
    # like "Semantic Views for X" directly names the CoCo capability needed)
    # -- the structured TECHNICAL_USE_CASE picklist frequently doesn't capture
    # this, and the description alone is often too generic. Lead with it.
    context = f"Use case name:\n{(name or '')[:300]}\n\nUse case description:\n{(desc or '')[:1500]}"
    if se_comments:
        context += (
            f"\n\nInternal SE notes (context only -- may contain sensitive detail):\n"
            f"{se_comments[:1500]}"
        )
    if partner_comments:
        context += (
            f"\n\nPartner notes (context only -- may contain sensitive detail):\n"
            f"{partner_comments[:1500]}"
        )
    return (
        "You are helping a Partner SE prep a partner-facing update for one Salesforce use case.\n\n"
        "Below is the full catalog of Cortex Code (CoCo) skills available to partners. Skills already "
        f"deterministically tagged for this use case ({len(deterministic_skills)} of a "
        f"{MAX_SKILLS_PER_USE_CASE}-skill maximum already used): [{skills_str}].\n\n"
        f"CoCo skill catalog:\n{_COCO_SKILL_CATALOG_BLOCK}\n\n"
        "Return ONLY a JSON object with exactly three keys:\n"
        "- \"summary\": 1-2 short sentences suitable for sharing externally with a partner, focused only "
        "on the business problem or goal.\n"
        f"- \"rationale\": one short sentence, grounded in the concrete technical detail below, on why "
        f"the skill(s) [{skills_str}] (plus any additional_skills below) would accelerate THIS engagement.\n"
        f"- \"additional_skills\": a JSON object of AT MOST {remaining} catalog skill names -> one-sentence "
        "reason each, for skills from the catalog above -- beyond the ones already tagged -- that are "
        "genuinely well-supported by the use case name, description, SE notes, or partner notes. Use EXACT skill names from the catalog. "
        "Return an empty object {} if no real capacity remains or nothing else clearly applies -- do not "
        "force matches just to fill the quota.\n\n"
        "ALL text fields must be partner-safe: remove dollar amounts, EACV, competitor names, internal "
        "people/team names, deal-risk commentary, and anything else sensitive, even if it appears in the "
        "SE or partner notes below. No markdown, no preamble, JSON only.\n\n" + context
    )


def parse_ai_skill_response(raw_text: str) -> dict:
    """Parse + validate the AI's JSON response. Any additional_skills name not
    found in the real catalog (case-insensitive) is silently dropped -- the
    anti-hallucination guardrail. Also hard-caps additional_skills at
    MAX_SKILLS_PER_USE_CASE as a safety net (the real enforcement of the
    overall per-use-case cap happens downstream via cap_skills(), which
    accounts for deterministic skills too). Returns {"summary":,
    "rationale":, "additional_skills": {name: reason}} -- all empty on any
    parse failure."""
    try:
        raw = re.sub(r"^```(?:json)?|```$", "", (raw_text or "").strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        summary = str(parsed.get("summary", "")).strip()
        rationale = str(parsed.get("rationale", "")).strip()
        raw_additional = parsed.get("additional_skills", {}) or {}
        additional_skills = {}
        if isinstance(raw_additional, dict):
            for k, v in list(raw_additional.items())[:MAX_SKILLS_PER_USE_CASE]:
                if str(k).strip().lower() in COCO_SKILL_NAMES:
                    additional_skills[str(k).strip()] = str(v).strip()
        return {"summary": summary, "rationale": rationale, "additional_skills": additional_skills}
    except Exception:
        return {"summary": "", "rationale": "", "additional_skills": {}}


def merge_additional_skills(skills: list, reasons: dict, additional_skills: dict):
    """Additive merge only -- never removes or overrides deterministic tags.
    Appends newly-suggested AI skills after the existing ones; exact final
    ordering/truncation is then handled by cap_skills(), which ranks by
    signal count (reason count) rather than list position, with Snowflake
    AIM always pinned first. Returns (new_skills_list, new_reasons_dict)."""
    skills = list(skills)
    reasons = dict(reasons)
    for skill, reason in additional_skills.items():
        if skill not in skills:
            skills.append(skill)
        reasons.setdefault(skill, []).append(f"AI-matched from use case notes &rarr; {h(reason)}")
    return skills, reasons


MAX_SKILLS_PER_USE_CASE = 3

AIM_SKILL_NAME = "Snowflake AIM"
_GENERIC_MIGRATION_SKILLS = {"migration-guide", "snowconvert-assessment", "spark-migration", "snowpark-connect"}

# Ordered by Migrations Support Matrix column order. See utils/AIM_SOURCES.md
# for the human-readable source table, matching rules, and known caveats.
AIM_SOURCE_PATTERNS = [
    ("SQL Server",    re.compile(r"\bsql\s*server\b|\bssis\b", re.I)),
    ("Redshift",       re.compile(r"\bredshift\b", re.I)),
    ("Teradata",       re.compile(r"\bteradata\b|\bbteq\b|\btpt\b|\bfastload\b|\bmultiload\b|\btpump\b", re.I)),
    ("Oracle",         re.compile(r"\boracle\b", re.I)),
    ("Azure Synapse",  re.compile(r"\bazure\s*synapse\b|\bsynapse\b", re.I)),
    ("BigQuery",       re.compile(r"\bbig\s*query\b", re.I)),
    ("IBM DB2",        re.compile(r"\bdb2\b", re.I)),
    ("Postgres",       re.compile(r"\bpostgres(?:ql)?\b", re.I)),
    ("Hive",           re.compile(r"\bhive\b", re.I)),
    ("Vertica",        re.compile(r"\bvertica\b", re.I)),
    ("Databricks SQL", re.compile(r"\bdatabricks\s*sql\b", re.I)),
    ("Spark SQL",      re.compile(r"\bspark\s*sql\b", re.I)),
    ("Sybase IQ",      re.compile(r"\bsybase(?:\s*iq)?\b", re.I)),
    ("SAS",            re.compile(r"\bsas\b", re.I)),
    ("Netezza",        re.compile(r"\bnetezza\b", re.I)),
    ("Informatica",    re.compile(r"\binformatica\b", re.I)),
    # Not part of the official Migrations Support Matrix -- added because these
    # are Hadoop/Spark-family legacy platforms AIM can also target. See
    # utils/AIM_SOURCES.md for details.
    ("Cloudera",       re.compile(r"\bcloudera\b", re.I)),
    ("Hortonworks",    re.compile(r"\bhortonworks\b", re.I)),
]


def detect_aim_source(name: str, tech_uc: str, desc: str, se_comments: str, partner_comments: str = ""):
    """Deterministic scan (word-boundary regex, no LLM) for a source system
    explicitly supported by Snowflake AIM. See utils/AIM_SOURCES.md for the
    full source table, matching rules, and known caveats. Returns the
    canonical source name of the FIRST match (by matrix column order), or
    None."""
    combined = " ".join(str(x or "") for x in (name, tech_uc, desc, se_comments, partner_comments))
    for canonical_name, pattern in AIM_SOURCE_PATTERNS:
        if pattern.search(combined):
            return canonical_name
    return None


# Display-name overrides for the AIM rationale sentence. Cloudera/Hortonworks
# are Hadoop distros, not a query engine/ETL tool in their own right -- the
# actual AIM-supported engines underneath them are Spark and Hive, so the
# rationale should name those rather than the distro/vendor name.
_AIM_SOURCE_DISPLAY_NAME = {
    "Cloudera": "Spark/Hive",
    "Hortonworks": "Spark/Hive",
}


def apply_aim_override(skills: list, reasons: dict, aim_source):
    """If aim_source is set, fully replace the generic CoCo migration skills
    with a single 'Snowflake AIM' entry placed first: Snowflake AIM is the
    authoritative, product-specific migration path for its supported
    sources, not a generic CoCo skill. Idempotent -- safe to call more than
    once across the pipeline (once deterministically, once again after the
    AI additional-skills merge) so an AI suggestion can never reintroduce a
    generic migration skill this use case already has a better answer
    for. Returns (skills, reasons) unchanged if aim_source is falsy."""
    if not aim_source:
        return skills, reasons
    skills = [s for s in skills if s not in _GENERIC_MIGRATION_SKILLS and s != AIM_SKILL_NAME]
    reasons = {k: v for k, v in reasons.items() if k not in _GENERIC_MIGRATION_SKILLS}
    skills = [AIM_SKILL_NAME] + skills
    display_source = _AIM_SOURCE_DISPLAY_NAME.get(aim_source, aim_source)
    reasons[AIM_SKILL_NAME] = [f"{h(display_source)} is a supported source in Snowflake AIM for migration."]
    return skills, reasons


def cap_skills(skills: list, reasons: dict, max_skills: int = MAX_SKILLS_PER_USE_CASE):
    """Hard cap on skill chips per use case (relevance over quantity).
    Snowflake AIM is always kept first if present (it's a single,
    product-specific recommendation, not competing on signal count). Every
    other skill is ranked by len(reasons[skill]) -- the number of
    independent signals that matched it (Tech-UC category hits, migration
    keyword hits, AI-suggested rationale) -- descending, so a skill matched
    by 3 different Tech-UC categories outranks one matched by only 1, rather
    than the two being ordered alphabetically. Ties keep the incoming list
    order (Python's sort is stable), which is deterministic matches before
    AI-suggested ones (see merge_additional_skills). Idempotent -- safe to
    call repeatedly as the list/reasons grow across the pipeline."""
    aim = [s for s in skills if s == AIM_SKILL_NAME]
    rest = sorted(
        (s for s in skills if s != AIM_SKILL_NAME),
        key=lambda s: len(reasons.get(s, [])),
        reverse=True,
    )
    kept = (aim + rest)[:max_skills]
    kept_set = set(kept)
    return kept, {k: v for k, v in reasons.items() if k in kept_set}


def prioritize_aim_skill(skills: list) -> list:
    """Move AIM_SKILL_NAME to index 0 if present, leaving everything else
    in place. Used where a flat, deduped skill list is assembled across
    multiple use cases (Action Plan / narrative rollups), since per-use-
    case ordering doesn't guarantee the aggregated list keeps AIM first."""
    if AIM_SKILL_NAME in skills:
        skills = [AIM_SKILL_NAME] + [s for s in skills if s != AIM_SKILL_NAME]
    return skills
