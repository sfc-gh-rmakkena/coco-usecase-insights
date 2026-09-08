"""
Enhanced, reusable skill-mapping module for PSE Email pages.

Superset of coco_skill_map.py: re-exports everything from it unchanged (the
deterministic Technical-Use-Case -> skill mapping, migration detection, peer
group constants, etc.), then adds an AI-driven catalog-matching layer on top,
grounded in the real 111-skill CoCo catalog (COCO_SKILLS.md) plus the use
case's sanitized description, SE_COMMENTS, and PARTNER_COMMENTS.

Final per-use-case skill selection (see rank_skills_by_gpa()) ranks
deterministic and AI-suggested candidates together on the SAME combined GPA
score (context_relevance * groundedness * answer_relevance) -- origin
doesn't grant priority. Snowflake AIM is the one deliberate exception,
always pinned first when eligible.

Future email tabs should import from THIS module instead of coco_skill_map
to get both layers. coco_skill_map.py itself stays untouched for any other
consumers of the deterministic base layer.
"""
import difflib
import json
import re
from collections import Counter
from pathlib import Path

from utils.coco_skill_map import *  # noqa: F401,F403 -- re-export deterministic base
from utils.coco_skill_map import (  # explicit re-export for static analysis / clarity
    map_coco_skills_explained, detect_migration, h,
)

_SKILLS_MD_PATH = Path(__file__).parent / "COCO_SKILLS.md"


def _parse_skill_catalog() -> list:
    """One-time regex parse of COCO_SKILLS.md into a condensed catalog:
    [{"name": ..., "summary": ..., "surface": ..., "use_cases": [...],
    "accelerates": [...], "caveats": ...}].

    Each skill entry in the source doc is a block starting with a
    `### `skill-name`` header, bounded by the next such header. Blocks are
    also separated by a `---` rule, but bounding on the next header alone is
    sufficient and simpler; the extraction below only pulls specific
    `**Field:**` patterns near the top of each block rather than consuming
    it to the boundary, so it is robust even for the final block (which
    otherwise runs into the Appendix).

    Extracts the 4 highest-matching-value fields in full, untruncated (an
    earlier version capped summary/surface at 200/250 chars and kept only
    the first 2 representative use cases -- verified against all 111 skills
    this dropped 72 truncated summaries, 64 truncated surface lines, and 413
    representative-use-case bullets catalog-wide, plus never read "What it
    accelerates" or "Prerequisites & caveats" at all, even though the
    latter is often exactly where cross-skill disambiguation text lives,
    e.g. openflow's caveats say "For deep connector failure diagnosis use
    `openflow-observability`"). "Example prompts", "Pairs with", and "Depth
    behind it" are deliberately still not extracted -- lower matching value,
    and every additional field further inflates the prompt sent on every
    AI call."""
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
        accel_match = re.search(r"\*\*What it accelerates\*\*\n((?:- .+\n?)+)", block)
        caveats_match = re.search(r"\*\*Prerequisites & caveats:\*\*\s*(.+)", block)
        use_cases = []
        if uc_match:
            use_cases = [
                line.lstrip("- ").strip().strip('"')
                for line in uc_match.group(1).splitlines() if line.strip()
            ]
        accelerates = []
        if accel_match:
            accelerates = [
                line.lstrip("- ").strip()
                for line in accel_match.group(1).splitlines() if line.strip()
            ]
        catalog.append({
            "name": name,
            "summary": summary_match.group(1).strip() if summary_match else "",
            "surface": surface_match.group(1).strip() if surface_match else "",
            "use_cases": use_cases,
            "accelerates": accelerates,
            "caveats": caveats_match.group(1).strip() if caveats_match else "",
        })
    return catalog


COCO_SKILL_CATALOG = _parse_skill_catalog()
COCO_SKILL_NAMES = frozenset(s["name"].lower() for s in COCO_SKILL_CATALOG)


def coco_skill_catalog_prompt_block() -> str:
    """Condensed catalog as prompt-ready text, built once at import time and
    reused verbatim across all per-use-case AI calls. Includes each skill's
    scope-bounded `summary` (not just its bare API `surface`) so the model
    can see WHAT a skill is actually for, not just which functions it
    touches -- without this, a skill's surface line alone (e.g. AI_EXTRACT,
    AI_PARSE_DOCUMENT) invites thematic-association matches on any use case
    that merely mentions a related word, even when the skill's real scope
    (e.g. "a single file or one-time batch on a stage") doesn't apply.

    Also includes `accelerates` (concrete capability statements, "What it
    accelerates" in COCO_SKILLS.md) and `caveats` ("Prerequisites &
    caveats:") -- the latter is where cross-skill disambiguation language
    usually lives (e.g. "for deep connector failure diagnosis use
    openflow-observability"), which the model needs to correctly choose
    between adjacent/overlapping skills rather than defaulting to the
    broader router skill every time."""
    lines = []
    for s in COCO_SKILL_CATALOG:
        ucs = "; ".join(s["use_cases"])
        accel = "; ".join(s["accelerates"])
        parts = [s["name"] + ":"]
        if s["summary"]:
            parts.append(s["summary"])
        if s["surface"]:
            parts.append(f"[drives: {s['surface']}]")
        if ucs:
            parts.append(f"(e.g. {ucs})")
        if accel:
            parts.append(f"[accelerates: {accel}]")
        if s["caveats"]:
            parts.append(f"[caveats: {s['caveats']}]")
        lines.append("- " + " ".join(parts))
    return "\n".join(lines)


_COCO_SKILL_CATALOG_BLOCK = coco_skill_catalog_prompt_block()


def build_summary_prompt(desc: str, se_comments: str, partner_comments: str = "", name: str = "") -> str:
    """Build a small, dedicated prompt for ONLY the partner-facing 1-2
    sentence summary (the report's "Description (sanitized)" column) --
    split out from build_ai_skill_prompt() (2026-09-08) so that call's
    large deterministic_skill_context/additional_skills JSON payload (a
    reason+evidence+3-scores block PER tagged/candidate skill, sometimes
    5+ skills' worth) can never compete for the SAME output-token budget
    and truncate the summary before it's ever written. Deliberately a
    PLAIN-TEXT response, not JSON -- one short field needs no schema, and
    this removes JSON-parse risk from the description pipeline entirely
    (the old failure mode was: truncation happens somewhere LATER in a
    large JSON object -> json.loads() throws -> the whole response,
    including a perfectly good already-written summary, was discarded).
    Caller passes the raw text straight through (.strip() only, no
    parsing) as the summary."""
    context = f"Use case name:\n{name or ''}\n\nUse case description:\n{desc or ''}"
    if se_comments:
        context += (
            f"\n\nInternal SE notes (context only -- may contain sensitive detail):\n"
            f"{se_comments}"
        )
    if partner_comments:
        context += (
            f"\n\nPartner notes (context only -- may contain sensitive detail):\n"
            f"{partner_comments}"
        )
    return (
        "You are helping a Partner SE prep a partner-facing update for one Salesforce use case.\n\n"
        "Write EXACTLY 1-2 short sentences suitable for sharing externally with a partner, focused only "
        "on the business problem or goal. Remove dollar amounts, EACV, competitor names, internal "
        "people/team names, deal-risk commentary, and anything else sensitive, even if it appears in the "
        "SE or partner notes below.\n\n"
        "Return ONLY the sentence(s) themselves -- no preamble, no quotes, no markdown, no JSON, no "
        "label like \"Summary:\".\n\n" + context
    )


def build_ai_skill_prompt(desc: str, se_comments: str, deterministic_skills: list, partner_comments: str = "",
                          name: str = "") -> str:
    """Build the prompt for one use case's AI rationale + candidate-skill-
    discovery call. The caller (page file) is responsible for actually
    invoking the LLM and passing the raw response to
    parse_ai_skill_response().

    Does NOT ask for the partner-facing summary -- that's a separate,
    dedicated small call now (see build_summary_prompt()'s docstring for
    why: this call's per-skill JSON payload can run long enough to get cut
    off, and a shared budget meant that cutoff used to take the summary
    down with it).

    Skill SELECTION beyond the deterministic set is grounded in the real
    111-skill catalog so it can never invent a skill that doesn't exist;
    parse_ai_skill_response() double-checks this with a hard validation
    step regardless of what the prompt asks for. Every use case is capped
    at MAX_SKILLS_PER_USE_CASE total, but that cap is enforced by
    rank_skills_by_gpa() AFTER both layers' candidates are scored -- NOT by
    limiting how many additional_skills the AI may propose here. An earlier
    version subtracted len(deterministic_skills) from this budget, which
    meant a use case with 3+ deterministic tags told the AI it had ZERO
    remaining slots regardless of how well-grounded a 4th skill might be --
    that pre-filtering, not the AI's own judgment, was the main reason AI
    suggestions rarely showed up in the final output (measured: 71% of
    real use cases already had a full deterministic slate before the AI
    was even asked). The AI is now always given the full budget to propose
    against, and lets rank_skills_by_gpa() decide who wins on merit."""
    skills_str = ", ".join(deterministic_skills) if deterministic_skills else "CoCo"
    remaining = MAX_SKILLS_PER_USE_CASE
    # The use case NAME is often the single most explicit signal (e.g. a name
    # like "Semantic Views for X" directly names the CoCo capability needed)
    # -- the structured TECHNICAL_USE_CASE picklist frequently doesn't capture
    # this, and the description alone is often too generic. Lead with it.
    # No truncation on any of these -- SE-comment histories can run to ~11k
    # chars, and the most recent/relevant update is often at the END of a
    # chronological log. A length cap here silently drops exactly the
    # evidence a case most needs, then produces false "not grounded"
    # verdicts downstream for real text that was simply never seen.
    context = f"Use case name:\n{name or ''}\n\nUse case description:\n{desc or ''}"
    if se_comments:
        context += (
            f"\n\nInternal SE notes (context only -- may contain sensitive detail):\n"
            f"{se_comments}"
        )
    if partner_comments:
        context += (
            f"\n\nPartner notes (context only -- may contain sensitive detail):\n"
            f"{partner_comments}"
        )
    return (
        "You are helping a Partner SE prep a partner-facing update for one Salesforce use case.\n\n"
        "Below is the full catalog of Cortex Code (CoCo) skills available to partners. Skills already "
        f"deterministically tagged for this use case ({len(deterministic_skills)} of a "
        f"{MAX_SKILLS_PER_USE_CASE}-skill maximum already used): [{skills_str}].\n\n"
        f"CoCo skill catalog:\n{_COCO_SKILL_CATALOG_BLOCK}\n\n"
        "Return ONLY a JSON object with exactly three keys:\n"
        f"- \"rationale\": one short sentence, grounded in the concrete technical detail below, on why "
        f"the skill(s) [{skills_str}] (plus any additional_skills below) would accelerate THIS engagement.\n"
        f"- \"deterministic_skill_context\": a JSON object mapping EACH already-tagged skill "
        f"[{skills_str}] -> {{\"reason\": a sanitized, one-sentence explanation of WHY this specific skill "
        "matters for THIS use case, \"evidence\": a short phrase copied VERBATIM from the use case name/"
        "description/SE notes/partner notes below, \"context_relevance\": 0.0-1.0, \"groundedness\": 0.0-1.0, "
        "\"answer_relevance\": 0.0-1.0 (see score definitions below)}. If you cannot find a real, specific "
        "quote supporting a tagged skill, use empty strings for both its reason and evidence -- do not "
        "fabricate one -- but still score it honestly (low groundedness).\n"
        f"- \"additional_skills\": a JSON object of AT MOST {remaining} catalog skill names -> "
        "{\"reason\": a sanitized, one-sentence explanation, \"evidence\": a short phrase copied VERBATIM "
        "from the use case name/description/SE notes/partner notes below, \"context_relevance\": 0.0-1.0, "
        "\"groundedness\": 0.0-1.0, \"answer_relevance\": 0.0-1.0}, for skills from the catalog above -- "
        "beyond the ones already tagged -- whose scope is genuinely matched by that exact evidence text. "
        "Use EXACT skill names from the catalog.\n\n"
        "SCORE DEFINITIONS (0.0-1.0 each, apply the SAME rubric to every skill, deterministic or additional):\n"
        "- context_relevance: does the use case's actual text call for this capability, independent of "
        "whether it's already tagged? 0.0 = nothing in the text relates to this skill's domain at all; "
        "1.0 = the text directly describes a need this skill addresses.\n"
        "- groundedness: is there real, specific supporting text for THIS skill (not a fabricated or "
        "generic-thematic claim)? 0.0 = no real quote backs this, or the quote is generic/thematic only; "
        "1.0 = a concrete, specific quote directly names this skill's actual scope.\n"
        "- answer_relevance: how directly would THIS SPECIFIC skill (vs. a more generic sibling skill in the "
        "same category) accelerate the stated problem? 0.0 = a different, more specific skill would clearly "
        "serve better; 1.0 = this is precisely the right skill for what's described.\n\n"
        "For BOTH \"reason\" fields above: never restate the skill's generic catalog capability (e.g. "
        "'extracts structured data from documents') -- instead name the specific thing IN THIS use case "
        "(a technology, workflow step, artifact, or pain point actually mentioned) that the skill would "
        "help with. If the only support you can offer is generic, leave the reason empty rather than "
        "writing boilerplate.\n\n"
        "CRITICAL -- evidence must be a real quote, not a paraphrase or inference: a topical word alone is "
        "NEVER sufficient evidence. Match on a named technology, artifact, or concrete action, never on "
        "thematic vibes. For example: the word \"content\" alone is NOT evidence of file/document "
        "processing (that requires an actual file/PDF/form/stage mention); the word \"insights\" alone is "
        "NOT evidence of machine learning (that requires an actual model/training/prediction mention); the "
        "word \"data\" alone is NOT evidence of data governance (that requires an actual policy/masking/"
        "classification mention). If you cannot copy a real, specific quote that concretely supports a "
        "skill's actual scope, leave that skill's reason/evidence empty (for deterministic_skill_context) "
        "or omit it entirely (for additional_skills) -- do not force matches just to fill the quota.\n\n"
        "ALL text fields must be partner-safe: remove dollar amounts, EACV, competitor names, internal "
        "people/team names, deal-risk commentary, and anything else sensitive, even if it appears in the "
        "SE or partner notes below. No markdown, no preamble, JSON only.\n\n" + context
    )


def _parse_reason_evidence_map(raw_obj, limit: int, valid_names: frozenset) -> dict:
    """Shared parsing for any {skill_name: {"reason":, "evidence":,
    "context_relevance":, "groundedness":, "answer_relevance":}} JSON
    object (also accepts a bare string value as a legacy/non-compliant
    shape, degrading to evidence="" and all 3 scores 0.0). Drops any skill
    name not found in `valid_names` (case-insensitive) -- the anti-
    hallucination guardrail, shared by both deterministic_skill_context
    (validated against the already-tagged deterministic skills, since the
    model can't invent a name there) and additional_skills (validated
    against the full AI catalog).

    The 3 GPA scores are purely additive reporting/ranking signal -- see
    rank_skills_by_gpa() -- and are parsed defensively: any missing,
    non-numeric, or out-of-[0,1]-range value clamps to 0.0 rather than
    crashing or trusting an out-of-spec value. A model that omits scores
    entirely (legacy behavior) degrades to all-zero scores, which
    rank_skills_by_gpa() then falls back to signal-count/coverage-floor
    logic for, same as if the model had explicitly scored everything
    irrelevant."""
    out = {}
    if not isinstance(raw_obj, dict):
        return out
    for k, v in list(raw_obj.items())[:limit]:
        if str(k).strip().lower() not in valid_names:
            continue
        if isinstance(v, dict):
            reason = str(v.get("reason", "")).strip()
            evidence = str(v.get("evidence", "")).strip()
            scores = {
                axis: _clamp_score(v.get(axis))
                for axis in ("context_relevance", "groundedness", "answer_relevance")
            }
        else:
            reason = str(v).strip()
            evidence = ""
            scores = {"context_relevance": 0.0, "groundedness": 0.0, "answer_relevance": 0.0}
        out[str(k).strip()] = {"reason": reason, "evidence": evidence, **scores}
    return out


def _clamp_score(value) -> float:
    """Coerce an AI-returned GPA score to a float in [0.0, 1.0], defaulting
    to 0.0 on anything missing/non-numeric -- never trust an out-of-spec
    value (negative, >1, NaN, a string) at face value."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if f != f:  # NaN
        return 0.0
    return max(0.0, min(1.0, f))


def parse_ai_skill_response(raw_text: str, deterministic_skills: list = None) -> dict:
    """Parse + validate the AI's JSON response.

    `deterministic_skills` (the skills already tagged for this use case,
    the same list passed to build_ai_skill_prompt) is used to validate
    deterministic_skill_context keys -- NOT the AI catalog names, since
    the deterministic layer's skill tags (utils/coco_skill_map.py's
    TECH_UC_SKILL_MAP) can differ from the AI-facing catalog's names due
    to naming drift (e.g. "cortex-ai-functions" vs. the catalog's
    "cortex-ai-function-studio") -- the model never invents this field's
    keys, it only fills in reasons for skills we already handed it, so the
    real anti-hallucination check is "was this skill actually tagged for
    this use case", not "does it match the AI catalog's current name".
    Falls back to COCO_SKILL_NAMES if omitted (legacy/backward-compat).

    additional_skills IS validated against the AI catalog names
    (COCO_SKILL_NAMES) since those ARE model-selected -- any name not
    found in the real 111-skill catalog (case-insensitive) is silently
    dropped, the original anti-hallucination guardrail. additional_skills
    is also hard-capped at MAX_SKILLS_PER_USE_CASE as a safety net (the
    real enforcement of the overall per-use-case cap happens downstream
    via rank_skills_by_gpa(), which ranks deterministic and AI-suggested
    skills together on GPA score rather than treating deterministic as
    already-decided);
    deterministic_skill_context has no such cap since it should map 1:1
    with however many skills were already tagged.

    Each value is expected to be {"reason": ..., "evidence": ...,
    "context_relevance": ..., "groundedness": ..., "answer_relevance": ...}
    per the current prompt, but a bare string is also accepted (legacy
    shape / model non-compliance) and degrades to reason=<string>,
    evidence="", all 3 scores 0.0 --
    which downstream filter_grounded_skills() will then always drop, since
    there's no evidence to check. This never crashes on a malformed shape;
    it just yields no evidence, which is treated as ungrounded.

    Returns {"summary":, "rationale":, "deterministic_skill_context":
    {name: {"reason":, "evidence":}}, "additional_skills": {name:
    {"reason":, "evidence":}}} -- all empty on any parse failure."""
    try:
        # Extract the outermost {...} block rather than only stripping a
        # leading/trailing code fence -- a model occasionally prepends
        # conversational preamble or a leaked internal-thinking comment
        # before the ```json fence (observed once in 56 real responses),
        # which made the old fence-only strip fail json.loads() entirely
        # and silently return an all-empty result via the except-clause
        # fallback below, discarding a perfectly good response.
        match = re.search(r"\{.*\}", raw_text or "", flags=re.DOTALL)
        raw = match.group(0) if match else (raw_text or "").strip()
        parsed = json.loads(raw)
        summary = str(parsed.get("summary", "")).strip()
        rationale = str(parsed.get("rationale", "")).strip()
        det_valid_names = (
            frozenset(s.strip().lower() for s in deterministic_skills)
            if deterministic_skills else COCO_SKILL_NAMES
        )
        deterministic_skill_context = _parse_reason_evidence_map(
            parsed.get("deterministic_skill_context", {}) or {}, limit=20, valid_names=det_valid_names
        )
        additional_skills = _parse_reason_evidence_map(
            parsed.get("additional_skills", {}) or {}, limit=MAX_SKILLS_PER_USE_CASE, valid_names=COCO_SKILL_NAMES
        )
        return {
            "summary": summary, "rationale": rationale,
            "deterministic_skill_context": deterministic_skill_context,
            "additional_skills": additional_skills,
        }
    except Exception:
        # Partial recovery: a response that got cut off mid-JSON (output
        # token budget exhausted before the closing brace -- routine on a
        # use case with several already-tagged skills, each needing a
        # reason+evidence+3-score block) fails json.loads() outright, and
        # until 2026-09-08 that meant EVERYTHING was discarded -- including
        # "summary" (and "rationale"), even though the model had already
        # written them out in full near the start of the response, well
        # before the later per-skill fields ran out of budget. Recover
        # those two fields directly via regex when the structured parse
        # fails, instead of surfacing an empty description on an otherwise
        # perfectly fine response. deterministic_skill_context/
        # additional_skills genuinely can't be salvaged this way (no
        # reliable field boundary once the JSON is malformed), so those
        # stay empty -- callers still get the coverage-floor safety net for
        # skills.
        summary = ""
        rationale = ""
        if raw_text:
            m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_text)
            if m:
                summary = m.group(1).replace('\\"', '"').replace("\\n", " ").strip()
            m = re.search(r'"rationale"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_text)
            if m:
                rationale = m.group(1).replace('\\"', '"').replace("\\n", " ").strip()
        return {"summary": summary, "rationale": rationale, "deterministic_skill_context": {}, "additional_skills": {}}


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize_for_match(text: str) -> str:
    text = _PUNCT_RE.sub(" ", (text or "").strip().lower())
    return _WHITESPACE_RE.sub(" ", text).strip()


def is_evidence_grounded(evidence: str, source_text: str, threshold: float = 0.6) -> bool:
    """Deterministic backstop against fabricated/paraphrased 'evidence'
    quotes -- the structural fix for the Thomson Reuters failure mode,
    where the model's justification shared almost no real text with the
    actual use case. Normalizes both strings (lowercase, collapsed
    whitespace); returns True immediately on an exact substring match.
    Otherwise falls back to difflib.SequenceMatcher.find_longest_match and
    requires the longest common contiguous run to cover >= `threshold` of
    the evidence text -- tolerant of minor reformatting (quote marks,
    punctuation) while still rejecting a quote that isn't really there.
    Empty/missing evidence is never grounded."""
    evidence_n = _normalize_for_match(evidence)
    source_n = _normalize_for_match(source_text)
    if not evidence_n or not source_n:
        return False
    if evidence_n in source_n:
        return True
    matcher = difflib.SequenceMatcher(None, evidence_n, source_n, autojunk=False)
    match = matcher.find_longest_match(0, len(evidence_n), 0, len(source_n))
    return (match.size / len(evidence_n)) >= threshold


_STOPWORDS = frozenset({
    "this", "that", "these", "those", "with", "from", "they", "their", "have",
    "will", "would", "could", "should", "about", "into", "through", "during",
    "before", "after", "while", "when", "where", "which", "what", "there",
    "here", "then", "than", "also", "were", "being", "been", "each", "other",
    "some", "such", "only", "more", "most", "very", "just", "over", "under",
    "between", "across", "within", "still", "even",
})
_TOKEN_RE = re.compile(r"[a-z0-9]{4,}")

# Acronyms that are real, concrete signal (e.g. "ML" in "leveraging ML for
# forecasting" for the machine-learning skill) but are shorter than the
# general 4-char floor above -- caught via a fixed allowlist rather than
# lowering _TOKEN_RE's length threshold globally, which would let in a flood
# of generic short words (has, for, can, etc.). Real-world case that
# motivated this: "ML scope" / "leveraging ML for forecasting" both failed
# to ground the machine-learning skill because "ml" (2 chars) was never
# extracted as a term at all.
_SHORT_ACRONYMS = frozenset({"ml", "ai", "bi", "de", "dw", "etl", "elt", "kpi", "sla", "sso"})
_SHORT_TOKEN_RE = re.compile(r"\b[a-z0-9]{2,3}\b")

# Medallion-architecture layer naming: "bronze/silver/gold" (dynamic-tables'
# own catalog use-case text) is one common convention among several -- e.g.
# "raw/trusted/refined" or "landing/curated/presentation" name the same
# three stages. Canonicalizing known synonyms to their medallion-stage name
# lets evidence written with a different (but equally standard) naming
# convention still match. Real-world case: "Trusted layer ... Refined
# layer ... transformations" should ground dynamic-tables even though it
# never says "bronze"/"silver"/"gold" literally.
_MEDALLION_LAYER_SYNONYMS = {
    "raw": "bronze", "landing": "bronze",
    "trusted": "silver", "cleaned": "silver", "curated": "silver",
    "refined": "gold", "presentation": "gold",
}


def _significant_terms(text: str) -> set:
    normalized = _normalize_for_match(text)
    terms = {t for t in _TOKEN_RE.findall(normalized) if t not in _STOPWORDS}
    terms |= {t for t in _SHORT_TOKEN_RE.findall(normalized) if t in _SHORT_ACRONYMS}
    terms |= {_MEDALLION_LAYER_SYNONYMS[t] for t in terms if t in _MEDALLION_LAYER_SYNONYMS}
    return terms


# Manually curated additions for real, on-topic terms that the condensed
# catalog summary/use-case text (COCO_SKILLS.md, parsed by
# _parse_skill_catalog) doesn't happen to literally contain -- either
# because the term never made it into the condensed summary at all
# ("greenplum", "fulfillment") or because it IS present but too common
# catalog-wide to pass the generic-term-frequency check on its own
# ("cost"/"project" -- see the trusted-bypass use in has_scope_term_overlap).
# Each entry documents the real-world case that motivated it. Keyed by exact
# catalog skill name (lowercase).
_SUPPLEMENTAL_SKILL_TERMS = {
    # "Greenplum takeout" never matched migration-guide -- Greenplum isn't in
    # AIM_SOURCE_PATTERNS (that list is Snowflake AIM's officially supported
    # matrix, a different skill) nor in migration-guide's own condensed
    # summary text, even though migrating off Greenplum is squarely in
    # migration-guide's general-purpose scope.
    "migration-guide": frozenset({"greenplum"}),
    # "Consumption has increased considerably" / "Risk: Platform Costs" both
    # failed to ground cost-intelligence: "consumption" never appears in its
    # condensed summary at all, and "cost" appears but is too common
    # catalog-wide (freq 9) to pass alone despite being this skill's core
    # subject.
    "cost-intelligence": frozenset({"consumption", "cost", "costs"}),
    # "utilize dbt projects in Snowflake" failed to ground
    # data:cosmos-dbt-core: "project"/"projects" matched but is too common
    # catalog-wide (freq 9) to pass alone, despite Astronomer Cosmos
    # operating specifically on dbt "projects".
    "data:cosmos-dbt-core": frozenset({"project", "projects"}),
    # "cross region auto fulfillment" failed to ground listing-observability:
    # its condensed summary covers auto-fulfillment health but the word
    # "fulfillment" itself didn't survive into the parsed summary text.
    "listing-observability": frozenset({"fulfillment"}),
    # "#SAP-BDCConnect" failed to ground manage-zerocopy-sapbdc: the evidence
    # tokenizes to the single fused word "bdcconnect" (no space between BDC
    # and Connect), which only overlaps the skill's own vocabulary via
    # "connect" (freq 8, too common, and not a word-boundary proper-noun
    # match since it's embedded mid-word) -- the AI scored this suggestion
    # 1.0/1.0/1.0 on all 3 GPA axes and was correct; the deterministic
    # grounding gate was wrong.
    "manage-zerocopy-sapbdc": frozenset({"bdcconnect", "sapbdc"}),
    # "ML scope" / "leveraging ML for forecasting" both failed to ground
    # machine-learning: "ml" is the standard abbreviation for the skill's
    # own domain, but its catalog-wide frequency (5, right at the
    # single-term threshold boundary) is shared with unrelated common words
    # like "decision" -- lowering the general threshold to exclude one
    # would exclude the other, so this is handled as an explicit override
    # instead of a threshold tweak.
    "machine-learning": frozenset({"ml"}),
}


def _skill_reference_terms(skill_name: str) -> set:
    """Significant terms drawn from a skill's OWN name, summary,
    representative use cases, "what it accelerates" bullets, and
    "prerequisites & caveats" text -- the vocabulary of concrete
    technologies/artifacts/actions that skill actually covers -- plus any
    manually curated _SUPPLEMENTAL_SKILL_TERMS for that skill. Used as a
    second, still skill-agnostic backstop (see has_scope_term_overlap): a
    REAL quote can still be the wrong evidence for a skill if it shares no
    concrete term with that skill's own scope (e.g. "content" is real text
    but shares nothing with document-intelligence's actual vocabulary of
    file/PDF/stage/scanned/invoice/contract).

    Caveats text is included because it's often where cross-skill
    disambiguation language lives (e.g. openflow's caveats name
    openflow-observability for deep failure diagnosis) -- without it, a
    skill's own vocabulary can look like a false match for an adjacent
    skill's evidence with no way to tell them apart."""
    skill_key = skill_name.strip().lower()
    skill = next((s for s in COCO_SKILL_CATALOG if s["name"].lower() == skill_key), None)
    if not skill:
        return set()
    text = (skill["name"].replace("-", " ").replace(":", " ") + " " + skill["summary"]
            + " " + " ".join(skill["use_cases"]) + " " + " ".join(skill["accelerates"])
            + " " + skill["caveats"])
    return _significant_terms(text) | _SUPPLEMENTAL_SKILL_TERMS.get(skill_key, frozenset())


def _compute_term_doc_freq() -> dict:
    """How many distinct skills' own reference vocabulary
    (_skill_reference_terms) contain each term, computed once at import
    time. Used by has_scope_term_overlap to tell a genuinely distinctive
    match (e.g. "iceberg", "openflow", "document" -- each rare across the
    catalog) from a merely common one (e.g. "connector", "share", "data",
    "layer" -- present in many skills' own summary/use-case text and
    therefore not actually discriminating evidence for any one of them)."""
    freq = Counter()
    for skill in COCO_SKILL_CATALOG:
        for term in _skill_reference_terms(skill["name"]):
            freq[term] += 1
    return dict(freq)


_TERM_DOC_FREQ = _compute_term_doc_freq()

# A single overlapping term is trusted alone only if it's this rare or rarer
# across the catalog's own vocabulary. Calibrated against real-world cases:
# "data cataloging" must still fail to ground `data-governance` (that
# skill's real scope is sensitive-data policy/masking, not generic
# cataloging), while "loaded the ServiceNow connector" (`openflow`) and
# generic bronze/silver/gold "layer"/"transformations" language
# (`dynamic-tables`) are treated as close enough to ground -- reflecting
# that those two skills' own scope is broad enough to cover the generic
# case, unlike data-governance's narrower one.
_GENERIC_TERM_DOC_FREQ_THRESHOLD = 4

# Terms this common catalog-wide (after the COCO_SKILLS.md enrichment added
# "What it accelerates"/"Prerequisites & caveats" text, pulling in a lot of
# generic instructional phrasing -- "requires", "without", "must", "using",
# plus pervasive Snowflake nouns like "data", "table", "schema", "account")
# never count toward the has_scope_term_overlap() 2+-terms quorum: with 111
# skills total, a term above this appears in over a tenth of them, so its
# co-occurrence with anything else is coincidental, not corroborating. Real
# case that set this: "compute resources ... seem to point to enterprise
# reporting" matched "point" (freq 13) and "compute" (freq 11) against
# workload-performance-analysis -- both individually vague, and their
# co-occurrence isn't real corroboration either. Looser than
# _GENERIC_TERM_DOC_FREQ_THRESHOLD (which governs single-term sufficiency)
# -- a term can still count toward a 2-term match even if it wouldn't pass
# alone.
_QUORUM_TERM_DOC_FREQ_THRESHOLD = 12

# Ubiquitous product/platform names that appear in nearly every skill's own
# catalog text -- never trusted as a "distinctive proper noun" on their own,
# unlike a specific named technology (e.g. "Databricks", "Iceberg"). Real-
# world case: "They want to A/B test with Snowflake" matched only
# "Snowflake" against cortex-ai-function-studio's vocabulary -- that's not
# evidence of AI functions specifically (A/B testing plus inference reads
# more like a machine-learning use case than an AI-functions one). NOTE:
# "cortex" is deliberately NOT in this set -- unlike bare "Snowflake",
# "Cortex" specifically naming a Cortex Analyst/Agent/Semantic-View concept
# (e.g. "Cortex for NL queries") is a real, on-topic signal for agent-studio,
# not incidental noise. "cloud" IS included -- real case: "modernizing its
# architecture to Cloud First" capitalizes "Cloud" only because it's part of
# an initiative name/title case, not because it names a specific technology;
# wrongly passed the proper-noun bypass for `warehouse`. This list is a
# known-incomplete, evidence-driven denylist, not an exhaustive filter --
# expect to add more generic-but-sometimes-capitalized words as they surface.
_UBIQUITOUS_PROPER_NOUNS = frozenset({"snowflake", "cloud"})


def _is_skill_name_term(term: str, skill_name: str) -> bool:
    """True if `term` IS (or is a plural/substring variant of) one of the
    words making up the skill's own name (e.g. "iceberg" for the `iceberg`
    skill; "performance" for `workload-performance-analysis`; "internal"
    for `internal-marketplace-org-listing`). Always trusted regardless of
    catalog-wide frequency -- evidence that directly uses a word from the
    skill's OWN name is about as strong a signal as grounding gets, even
    when that word (e.g. "performance", "internal") is also common
    catalog-wide for unrelated reasons. More principled than tuning
    frequency thresholds per case: real cases that motivated this --
    "iceberg tables for their silver and gold layers" must ground `iceberg`
    even though "iceberg"'s catalog-wide frequency rose after the
    COCO_SKILLS.md enrichment (more skills now mention it in their
    caveats/accelerates text); "testing our performance" must ground
    `workload-performance-analysis`; "sharing data across internal business
    units" must ground `internal-marketplace-org-listing`.

    Still gated by _QUORUM_TERM_DOC_FREQ_THRESHOLD: several skill names
    contain a word too generic to trust even as "the skill's own name" --
    e.g. "data" in data-governance/data-quality/data-sharing/etc. Without
    this guard, "data cataloging" wrongly re-grounded data-governance via
    "data" being literally part of its name, even though "data" appears in
    73 of 111 skills and discriminates nothing."""
    if _TERM_DOC_FREQ.get(term, 0) > _QUORUM_TERM_DOC_FREQ_THRESHOLD:
        return False
    name_terms = _significant_terms(skill_name.replace("-", " ").replace(":", " "))
    return any(term in nt or nt in term for nt in name_terms)


def _canonical_matched_roots(ev_terms: set, ref_terms: set) -> set:
    """Distinct overlapping roots between ev_terms and ref_terms, collapsing
    simple plural/stem variants of the SAME word to one entry (e.g.
    "connector"/"connectors" -> "connector"; "share"/"shares"/"reshared" ->
    "share") by keeping the shorter string of each containment pair. Without
    this, a single real-world concept could inflate to 2+ "distinct" matched
    terms purely from its own plural/stem forms, wrongly satisfying the 2+
    -terms rule below on what is actually still just one generic word.

    Short terms (<=3 chars, i.e. the _SHORT_ACRONYMS allowlist) require an
    EXACT match rather than substring containment: Python's plain `in` check
    is a prefix/substring test, so "de" in "decision" is True even though
    that's just an accidental letter collision, not a real match -- this
    wrongly grounded blueprints:blueprint-builder on "The decision has been
    taken" via "de" (matched against blueprint-builder's own unrelated "DE"
    acronym mention) before this guard was added.

    Longer terms still require the length difference to be small (<=4
    chars) even when one contains the other -- a genuine plural/stem
    relationship (document/documents, connector/connectors, catalog/
    cataloging) is always a small edit away, but an arbitrary short word
    can coincidentally appear INSIDE a much longer, unrelated word (e.g.
    "tell" is a literal substring of "intelligence" -- i-n-t-e-l-l-i-gence
    -- with no real semantic relationship at all). Real case: "Marketing
    Mixed Modeling with Campaign Intelligence" wrongly matched agent-
    studio's own "tell" via this coincidence, pairing with a genuine "model"
    match to wrongly satisfy the 2-term quorum."""
    roots = set()
    for et in ev_terms:
        for rt in ref_terms:
            if len(et) <= 3 or len(rt) <= 3:
                matched = et == rt
            else:
                matched = (et in rt or rt in et) and abs(len(et) - len(rt)) <= 4
            if matched:
                roots.add(et if len(et) <= len(rt) else rt)
    return roots


def _is_proper_noun_mention(term: str, evidence: str) -> bool:
    """True if `term` appears capitalized (e.g. "Databricks", "Iceberg") in
    the ORIGINAL (non-lowercased) evidence text -- a signal that it's a
    named product/technology rather than a common English word, even when
    that same word is otherwise common across the catalog's own vocabulary.
    Real-world case: "Databricks TakeOut" must still ground spark-migration
    even though "databricks" (freq 13 -- mentioned by several migration-
    related skills) fails the generic-term-frequency check above; it's a
    specific named source platform, not a vague thematic word like
    "connector" or "share". Excludes _UBIQUITOUS_PROPER_NOUNS ("snowflake")
    -- capitalized but never distinctive, since it's the product's own name
    and appears in nearly every skill's text."""
    if term in _UBIQUITOUS_PROPER_NOUNS:
        return False
    pattern = re.compile(r"\b" + re.escape(term[0].upper() + term[1:]) + r"\b")
    return bool(pattern.search(evidence or ""))


def has_scope_term_overlap(evidence: str, skill_name: str) -> bool:
    """True if `evidence` shares concrete term(s) (allowing for simple
    pluralization via substring containment, e.g. "document" vs.
    "documents") with `skill_name`'s own catalog vocabulary -- AND that
    overlap is actually meaningful, not incidental. This is what catches a
    real, verbatim quote used to justify the WRONG skill -- e.g. Thomson
    Reuters' genuine "content ... through playgrounds, quality checks"
    quote passes is_evidence_grounded() (it's real text) but fails this
    check for document-intelligence (shares no term with that skill's
    file/PDF/stage vocabulary); Onbase's genuine "digital documents for
    customer letters" quote passes both (shares "document").

    A term qualifies on its own (single-term sufficiency) if EITHER:
      - it IS (or is a plural/substring variant of) one of the words making
        up the skill's own name (see _is_skill_name_term) -- e.g. evidence
        mentioning "performance" for workload-performance-analysis, or
        "internal" for internal-marketplace-org-listing -- always trusted
        regardless of catalog-wide frequency, checked first, OR
      - it's a manually curated _SUPPLEMENTAL_SKILL_TERMS entry for this
        specific skill (trusted regardless of catalog-wide frequency, since
        a human has confirmed it's genuinely core vocabulary for THIS
        skill even though the word is common elsewhere -- e.g. "cost" for
        cost-intelligence), OR
      - it's genuinely rare across the catalog (doc frequency <=
        _GENERIC_TERM_DOC_FREQ_THRESHOLD, see _compute_term_doc_freq), OR
      - it's a capitalized proper-noun/technology mention in the evidence
        (see _is_proper_noun_mention) -- e.g. "Databricks", even though that
        word alone is common across several migration-related skills'
        catalog text.
    2+ DISTINCT terms are sufficient together even if neither individually
    qualifies (e.g. "questions" and "answer" both present is a stronger
    signal than either alone) -- BUT only counting terms below
    _QUORUM_TERM_DOC_FREQ_THRESHOLD, a much looser cap than the single-term
    threshold. Terms above it are catalog-wide filler (present in over a
    quarter of all 111 skills' own text -- "data", "requires", "table",
    "account", "schema", "using", etc., after enriching the catalog with
    "What it accelerates"/"Prerequisites & caveats" text pulled in a lot of
    generic instructional phrasing) and their CO-OCCURRENCE is coincidental,
    not corroborating: real case -- "data cataloging" matched both "data"
    (freq 73/111, i.e. two-thirds of all skills) and "catalog" (freq 16) for
    data-governance, wrongly passing the 2-term rule even though "data"
    contributes nothing (data-governance's real scope is sensitive-data
    policy/masking, not generic cataloging).

    No catalog entry for skill_name (e.g. a deterministic-only tag not
    present in the AI catalog) => no overlap required (returns True), since
    that skill's real scope vocabulary isn't available to check against."""
    ref_terms = _skill_reference_terms(skill_name)
    if not ref_terms:
        return True
    ev_terms = _significant_terms(evidence)
    matched_roots = _canonical_matched_roots(ev_terms, ref_terms)
    if not matched_roots:
        return False

    distinctive = {t for t in matched_roots if _TERM_DOC_FREQ.get(t, 0) <= _QUORUM_TERM_DOC_FREQ_THRESHOLD}
    if len(distinctive) >= 2:
        return True

    skill_key = skill_name.strip().lower()
    for term in sorted(matched_roots, key=lambda t: _TERM_DOC_FREQ.get(t, 0)):
        if _is_skill_name_term(term, skill_name):
            return True
        if term in _SUPPLEMENTAL_SKILL_TERMS.get(skill_key, frozenset()):
            return True
        if _TERM_DOC_FREQ.get(term, 0) <= _GENERIC_TERM_DOC_FREQ_THRESHOLD:
            return True
        if _is_proper_noun_mention(term, evidence):
            return True
    return False


def filter_grounded_skills(additional_skills: dict, source_text: str) -> dict:
    """Drops any AI-suggested skill whose evidence quote isn't actually
    grounded in the use case's real text (is_evidence_grounded) OR doesn't
    share a concrete term with that skill's own catalog scope
    (has_scope_term_overlap) -- same anti-hallucination pattern as the
    existing catalog-name check in parse_ai_skill_response(), but checking
    the JUSTIFICATION rather than just the skill name. Returns a flat
    {name: reason} dict, matching the shape merge_additional_skills()
    already expects, so no downstream changes are needed."""
    grounded = {}
    for skill, payload in (additional_skills or {}).items():
        if isinstance(payload, dict):
            reason, evidence = payload.get("reason", ""), payload.get("evidence", "")
        else:
            reason, evidence = str(payload), ""
        if is_evidence_grounded(evidence, source_text) and has_scope_term_overlap(evidence, skill):
            grounded[skill] = reason
    return grounded


def filter_grounded_deterministic_skills(skills: list, source_text: str) -> list:
    """Admission gate for deterministic-origin skills, mirroring
    filter_grounded_skills()'s anti-hallucination role for AI-suggested
    ones -- but checked differently, since a deterministic tag comes from
    a rule match on the structured TECHNICAL_USE_CASE taxonomy field, not a
    quoted phrase. There's no "evidence" to run is_evidence_grounded()
    against; instead this checks has_scope_term_overlap() with the skill's
    own catalog vocabulary against the FULL use-case text (name +
    description + SE notes + partner notes), not just the matched taxonomy
    segment.

    This is what fixes the coarse "one matched category maps to 2-3
    skills at once" over-tagging (e.g. "DE: Ingestion" -> openflow +
    snowpipe-streaming + snowpark-python, all three, regardless of which
    one -- if any -- the real text actually supports): a deterministic
    candidate with zero textual support anywhere in the real use-case text
    is filtered out here, before rank_skills_by_gpa() ever sees it, rather
    than just being out-ranked by a better AI suggestion.

    A skill with no AI-catalog entry (e.g. a deterministic-only tag whose
    name has drifted from the catalog's current naming, or one that was
    never in the AI-facing catalog at all) passes through unfiltered --
    has_scope_term_overlap() returns True when there's no catalog vocabulary
    to check against, same as its existing behavior for AI-suggested
    skills. Returns the filtered skill list, order preserved."""
    return [s for s in skills if has_scope_term_overlap(source_text, s)]


def merge_additional_skills(skills: list, reasons: dict, additional_skills: dict):
    """Additive merge only -- never removes or overrides deterministic tags.
    Appends newly-suggested AI skills after the existing ones; exact final
    ordering/truncation is then handled by cap_skills(), which ranks by
    signal count (reason count) rather than list position, with Snowflake
    AIM always pinned first. `additional_skills` is expected to already be
    a flat {name: reason} dict (post filter_grounded_skills()). Returns
    (new_skills_list, new_reasons_dict)."""
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
    """Hard cap on skill chips per use case, ranking by raw signal count
    only. SUPERSEDED by rank_skills_by_gpa() as of the GPA-based ranking
    redesign -- kept only for any caller that hasn't migrated and for its
    signal-count tiebreak logic, which rank_skills_by_gpa() reuses. Do not
    add new call sites; see rank_skills_by_gpa() instead.

    Snowflake AIM is always kept first if present (it's a single,
    product-specific recommendation, not competing on signal count). Every
    other skill is ranked by len(reasons[skill]) -- the number of
    independent signals that matched it (Tech-UC category hits, migration
    keyword hits, AI-suggested rationale) -- descending, so a skill matched
    by 3 different Tech-UC categories outranks one matched by only 1, rather
    than the two being ordered alphabetically. Ties keep the incoming list
    order (Python's sort is stable), which is deterministic matches before
    AI-suggested ones (see merge_additional_skills). Idempotent -- safe to
    call repeatedly as the list/reasons grow across the pipeline.

    This signal-count-only ranking is exactly what let deterministic skills
    structurally out-rank equally-supported AI suggestions on every tie --
    see rank_skills_by_gpa()'s docstring for the real-world measurement
    (28 of 28 AI suggestions lost to this cap were tied on signal count,
    0 were genuinely outranked on merit)."""
    aim = [s for s in skills if s == AIM_SKILL_NAME]
    rest = sorted(
        (s for s in skills if s != AIM_SKILL_NAME),
        key=lambda s: len(reasons.get(s, [])),
        reverse=True,
    )
    kept = (aim + rest)[:max_skills]
    kept_set = set(kept)
    return kept, {k: v for k, v in reasons.items() if k in kept_set}


# Below this combined-GPA-score, a skill's supporting signal is too weak to
# trust as a genuine top-N pick -- see rank_skills_by_gpa()'s coverage-floor
# fallback, which only kicks in when EVERY candidate falls under this bar.
_GPA_COVERAGE_FLOOR_THRESHOLD = 0.1


def _combined_gpa_score(skill: str, gpa_scores: dict) -> float:
    """Product of the 3 GPA axes (context_relevance * groundedness *
    answer_relevance), each 0.0-1.0. Product, not average or sum, because a
    skill weak on ANY single axis should rank low overall -- a skill that's
    grounded but contextually irrelevant, or relevant but ungrounded,
    shouldn't out-rank one that's solid on all three. Missing/unscored
    entries (e.g. a deterministic-only skill the model omitted from
    deterministic_skill_context) default to 0.0 on all axes, i.e. score 0
    -- never assumed to be well-supported just because it's untested."""
    g = gpa_scores.get(skill) or {}
    return (
        g.get("context_relevance", 0.0)
        * g.get("groundedness", 0.0)
        * g.get("answer_relevance", 0.0)
    )


def rank_skills_by_gpa(skills: list, reasons: dict, gpa_scores: dict,
                        deterministic_origin: frozenset = frozenset(),
                        max_skills: int = MAX_SKILLS_PER_USE_CASE) -> tuple:
    """Replaces cap_skills()'s signal-count-only ranking: every candidate
    skill -- deterministic or AI-origin, already past its respective
    admission gate (filter_grounded_deterministic_skills /
    filter_grounded_skills) -- is ranked by a single combined GPA score
    (see _combined_gpa_score), not by which layer produced it.

    Real-world motivation: measured on the 52-case eval fixture, of 56 raw
    AI suggestions, 41 survived the grounding filter, but cap_skills()'s
    signal-count tie-break (deterministic always listed first, so always
    wins ties) let only 13 through -- all 28 lost suggestions lost on a
    tie, none were genuinely outranked on merit. This function removes
    that structural bias: origin no longer matters for ranking, only the
    GPA score does.

    Snowflake AIM is still pinned first UNCONDITIONALLY and excluded from
    GPA ranking entirely -- an explicit, deliberate carve-out (not a
    ranking outcome): an AIM-eligible migration source is Snowflake's
    authoritative, product-specific answer regardless of how any candidate
    scores.

    Ties (equal combined GPA score) are broken by signal count (same
    tiebreak cap_skills() used as its PRIMARY key -- now genuinely
    secondary), then stable list order.

    Coverage floor: if EVERY non-AIM candidate scores below
    _GPA_COVERAGE_FLOOR_THRESHOLD (common for thin/vague use-case text where
    no candidate has strong support either way), the single highest-scoring
    deterministic-origin candidate is kept anyway rather than returning zero
    skills -- this preserves the ~50% of real use cases measured to rely on
    deterministic tagging with weak/no free-text support (see this
    conversation's earlier coverage analysis). AI-origin candidates get no
    such rescue -- if capacity is exceeded and every candidate (deterministic
    or AI) is weak, an AI candidate is never swapped in over a stronger
    deterministic one just to fill the floor. Note this does NOT mean weak
    AI candidates are dropped outright: same as cap_skills() before it, any
    admitted candidate (it already passed filter_grounded_skills()) still
    fills available capacity if there aren't more candidates than slots --
    the floor only governs which candidate is CHOSEN when candidates
    outnumber slots and everyone is weak, not a minimum score to appear at
    all.

    `gpa_scores`: {skill: {"context_relevance":, "groundedness":,
    "answer_relevance":}}, typically merging parsed["deterministic_skill_context"]
    and parsed["additional_skills"] from parse_ai_skill_response(). Missing
    entries default to all-0.0 scores (see _combined_gpa_score).
    `deterministic_origin`: skill names that came from the deterministic
    layer -- used only to pick the coverage-floor fallback candidate.

    Returns (kept_skills, kept_reasons), same shape as cap_skills()."""
    aim = [s for s in skills if s == AIM_SKILL_NAME]
    rest = [s for s in skills if s != AIM_SKILL_NAME]

    def sort_key(skill):
        return (_combined_gpa_score(skill, gpa_scores), len(reasons.get(skill, [])))

    ranked = sorted(rest, key=sort_key, reverse=True)
    capacity = max(0, max_skills - len(aim))
    top = ranked[:capacity]

    if capacity > 0 and all(_combined_gpa_score(s, gpa_scores) < _GPA_COVERAGE_FLOOR_THRESHOLD for s in rest):
        det_candidates = [s for s in rest if s in deterministic_origin]
        if det_candidates and not any(s in det_candidates for s in top):
            fallback = max(det_candidates, key=sort_key)
            top = ([fallback] + top)[:capacity]

    kept = aim + top
    kept_set = set(kept)
    return kept, {k: v for k, v in reasons.items() if k in kept_set}


_CATALOG_BY_NAME_LOWER = {c["name"].lower(): c for c in COCO_SKILL_CATALOG}


def is_catalog_skill(skill_name: str) -> bool:
    """True iff skill_name is one of the 111 real skills literally present
    in COCO_SKILLS.md (case-insensitive) -- the ONLY trusted skill
    vocabulary per explicit instruction. No aliasing: a handful of legacy
    deterministic-layer names (e.g. "dashboard", "cortex-ai-functions",
    "dbt-data-modeling") that predate the current catalog naming are
    dropped outright by this check rather than mapped to a similar-sounding
    catalog entry -- an earlier LEGACY_ALIASES approach was rejected
    because it silently substituted a DIFFERENT skill than the one a
    deterministic rule actually named."""
    return bool(skill_name) and skill_name.strip().lower() in COCO_SKILL_NAMES


def skill_scope_text(skill_name: str) -> str:
    """One skill's full, untruncated documented scope (summary +
    accelerates + caveats) as prompt-ready text -- the exact real
    documentation the grounding judge checks each candidate against. No
    length caps anywhere: an earlier version capped caveats at 400 chars
    and accelerates at 3 items, which silently cut off the two most
    decision-critical exclusion clauses on 55/111 skills (including
    document-intelligence's own caveats)."""
    c = _CATALOG_BY_NAME_LOWER.get((skill_name or "").strip().lower())
    if not c:
        return f"{skill_name}: (not in COCO_SKILLS.md -- should have been dropped before this point)"
    accel = "; ".join(c["accelerates"]) if c["accelerates"] else ""
    caveats = c["caveats"] if c["caveats"] else ""
    parts = [c["summary"]]
    if accel:
        parts.append(f"Accelerates: {accel}")
    if caveats:
        parts.append(f"Caveats: {caveats}")
    return f"{skill_name}: " + " | ".join(p for p in parts if p)


def build_grounding_judge_prompt(source_text: str, candidates: list) -> str:
    """Approach 2's second, independent grounding pass: given the use
    case's full raw text and a list of (skill_name, evidence) candidate
    tuples (deterministic-origin candidates get evidence="(category-
    derived, no specific text quote)" when no AI evidence exists for
    them), asks the model to fact-check EACH candidate against that
    skill's real documented scope (skill_scope_text) and return a
    per-candidate {"grounded": bool, "reason": str} verdict.

    This REPLACES the bag-of-words has_scope_term_overlap() heuristic gate
    for any caller that wants LLM-judged grounding instead -- the two are
    independent gates; callers choose one or the other, this module does
    not combine them.

    Four named match types (current-state / named-tool replacement /
    greenfield build / stated-outcome match) -- exact wording tested
    across 56 real Deloitte use cases, including the specific counter-
    examples that fixed false negatives (dbt-projects-on-snowflake for an
    MWAA-orchestrated dbt use case; data-quality for a "quality checks"
    stated outcome; ai-functions-pipeline-builder for a greenfield NER
    pipeline) and false positives (document-intelligence over-admitted via
    generic "JSON in a table" modernization framing). Deliberately never
    says "Path N" anywhere, including in its own numbered-list framing or
    the JSON output instruction -- an earlier version leaked "Path 1"/
    "Path 2" phrasing into the judge's own reason text, which the user
    explicitly rejected in favor of the descriptive match-type names
    alone."""
    cand_lines = []
    for i, (skill, evidence) in enumerate(candidates, 1):
        cand_lines.append(f'{i}. skill="{skill}" evidence="{evidence}"\n   scope: {skill_scope_text(skill)}')
    cand_block = "\n".join(cand_lines)
    return f"""You are fact-checking whether specific evidence quotes genuinely support tagging each named CoCo skill as RELEVANT to this partner engagement -- not whether the evidence is real (assume it is), but whether that skill (as scoped below) is a sensible fit. This is opportunity-tagging for a sales/SE engagement tracker, NOT a literal current-state architecture audit.

A skill can be grounded FOUR ways -- read all four carefully, they are NOT interchangeable. Think like an SE pitching complementary skills to extend a deal, not like a narrow compliance auditor -- an SE maps what the customer SAID THEY WANT to whichever skill delivers it, without waiting for the customer to already know Snowflake's internal terminology for it:
- CURRENT-STATE MATCH: the evidence describes the customer already doing something within that skill's actual documented scope.
- NAMED-TOOL REPLACEMENT MATCH: the evidence names a SPECIFIC external tool, platform, or orchestrator (e.g. "Databricks", "MWAA", "Airflow", "Cloudera", "dbt Cloud") that this skill is the well-known Snowflake-native replacement/migration path FOR. Example: a customer on Databricks should ground a Databricks migration skill BECAUSE they are on Databricks, not despite it. A customer running dbt via MWAA should ground a skill for deploying dbt as a native Snowflake object (eliminating the external orchestrator) -- the mismatch between "current tool" and "skill's target state" is exactly the signal here, not a disqualifier.

Named-tool replacement match applies EVEN IF the evidence frames the named external tool as an already-decided or planned destination, not just an existing pain point being reconsidered -- Snowflake's positioning is to preempt unnecessary external-tool adoption proactively, not only react to existing dependencies. Example: a use case that says it is "migrating X to MWAA and dbt" should STILL ground a native-Snowflake-dbt-deployment skill, exactly as if it said the customer already runs dbt on MWAA today -- the fact that MWAA is the stated target rather than the current pain point does not disqualify the replacement skill; the opportunity to avoid the external orchestrator entirely applies before adoption just as much as after it.

- GREENFIELD BUILD MATCH: the evidence describes needing or wanting to build/stand up a NEW capability that IS this skill's own core represented use case (per its "Representative use cases" / "What it accelerates" text), even with nothing existing yet to currently-match and no named external tool being replaced. Most of a skill's own representative use cases are phrased exactly this way (e.g. ai-functions-pipeline-builder's own catalog use cases include "Build a searchable knowledge base over our contract library" and "Build an incremental invoice processing pipeline from my stage" -- forward-looking build requests, not descriptions of existing systems or named replacements). Example: evidence describing "NER (Named Entity Recognition) processing" as part of "the complete lifecycle from content ingestion to production deployment" should ground ai-functions-pipeline-builder via a greenfield build match -- entity/structured extraction as an ongoing pipeline is literally one of that skill's own named templates ("structured extraction") and composable blocks ("entity assembly"), regardless of whether the customer is already using Snowflake Cortex AI functions today or replacing a named tool. Do NOT require a current-state or named-tool-replacement match to also be satisfied when a greenfield build match clearly applies -- greenfield build intent that matches a skill's own documented use case is sufficient on its own.

- STATED-OUTCOME MATCH: the evidence names a plain-English business outcome or need (in the customer's own words, not Snowflake jargon) that IS what a skill's own one-line summary/tagline directly promises to deliver -- ground it even if the customer never mentions the specific Snowflake mechanism (DMFs, AI_EXTRACT, etc.) and even if the same evidence is already grounding a different skill for a different part of the same need. Example: a customer platform that names "quality checks" as one of its explicit capabilities should ground data-quality ("Monitors, investigates, and enforces data quality") via a stated-outcome match -- once the platform's content lands in Snowflake tables (which may itself be grounded via a greenfield build match on a different skill), DMF-based monitoring is the concrete Snowflake-native way to deliver the customer's own literally-stated "quality checks" want, regardless of whether they described that want as validating structured columns or evaluating content. Do not require the customer's phrasing to distinguish "data quality" from "content quality" -- if they used the words "quality check[s]"/"quality control"/"quality validation" as a named capability they want, and a skill's own summary is literally about delivering quality monitoring/enforcement, that is sufficient; a skill's own "Pairs with" list (curated for a narrower internal workflow-sequencing purpose) is NOT a relevance filter and must not be used to reject an otherwise-sound stated-outcome match.

A named-tool replacement match requires a REAL NAMED TOOL/PLATFORM being replaced -- it is NOT a license to admit a skill just because a data format, generic noun, or workflow step is mentioned. Counter-example: evidence describing "JSON files loaded into Snowflake and flattened into tabular data" does NOT ground a skill scoped to "files on a stage" (e.g. document-intelligence) just because JSON is a document-adjacent word and the process is being modernized -- there is no named external tool being replaced here, and the actual technical operation (data already in table rows) is genuinely outside that skill's scope under ANY of the four ways described above. Similarly, a skill for SQL policy objects does not cover unrelated cloud networking terms that merely share a word, modernization framing or not. When in doubt whether a named-tool replacement match applies, ask: does the evidence name a SPECIFIC tool/platform/orchestrator, and is the candidate skill THE recognized Snowflake-native answer to replacing exactly that named thing? A greenfield build match has its own similar discipline: greenfield intent must match a skill's OWN stated use case, not just share a generic theme -- "we're building something new with data" does not by itself ground every data-adjacent skill; the described capability must line up with that skill's specific representative use cases or accelerates list, not merely its general subject area.

If a skill has no catalog scope text, judge only on whether the plain-English skill label is a sensible fit for the evidence -- do not reject solely for lacking a catalog entry.

USE CASE TEXT:
{source_text}

CANDIDATES TO JUDGE:
{cand_block}

For EACH numbered candidate, decide which of the four ways (if any) grounds it. Return ONLY a JSON object, one entry per candidate skill name (use the exact skill name given, not the catalog alias):
{{"<skill_name>": {{"grounded": true or false, "reason": "one sentence -- name which of the four match types grounded it (current-state match / named-tool replacement match naming the specific tool / greenfield build match / stated-outcome match), or why none applies. Never write the word 'path' or a path number -- use only the descriptive match-type name."}}, ...}}"""


def parse_grounding_judge_response(raw_text: str) -> dict:
    """Parse the grounding judge's JSON verdict map. Same robust
    outermost-{...}-block extraction as parse_ai_skill_response() (not a
    fence-anchored strip) -- proven necessary by the Boehringer SIGHT case,
    where a model response prepended non-fence preamble text and a naive
    fence-only strip silently failed json.loads(), discarding a perfectly
    good verdict. Also tolerates one common minor malformation (a trailing
    comma before a closing brace) that a strict json.loads() alone
    rejects. Returns {} on total parse failure -- callers must treat a
    missing verdict as ungrounded, never as an implicit pass."""
    if not raw_text:
        return {}
    match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
    if not match:
        return {}
    raw = match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*\}", "}", raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}


def prioritize_aim_skill(skills: list) -> list:
    """Move AIM_SKILL_NAME to index 0 if present, leaving everything else
    in place. Used where a flat, deduped skill list is assembled across
    multiple use cases (Action Plan / narrative rollups), since per-use-
    case ordering doesn't guarantee the aggregated list keeps AIM first."""
    if AIM_SKILL_NAME in skills:
        skills = [AIM_SKILL_NAME] + [s for s in skills if s != AIM_SKILL_NAME]
    return skills
