"""
Classifies natural language questions into structured intents for
programmatic metric resolution. Pure keyword matching — no LLM needed.
"""
import re
from utils import PARTNER_CANONICAL_BY_LOWER

# Short-form names not in PARTNER_ALIASES (common spoken names → canonical)
_SHORT_FORMS = {
    "deloitte":    "Deloitte Consulting",
    "capgemini":   "Capgemini Technologies LLC",
    "cognizant":   "Cognizant Technology Solutions US Corp",
    "ntt data":    "NTT DATA Group Corporation",
    "ntt":         "NTT DATA Group Corporation",
    "megazone":    "MegazoneCloud Corporation",
    "infinite lambda": "Infinite Lambda Limited",
    "altis":       "Altis Consulting, ANZ",
    "prolim":      "PROLIM Global Corporation",
    "infomotion":  "INFOMOTION GMBH",
    "civica":      "CIVICA SOFTWARE, S.L.",
    "kubrick":     "Kubrick Group",
    "kpc":         "KPC (Key Performance Consulting)",
    # LATAM RSIs
    "viewnear":    "Viewnear - Partner",
    "ivcisa":      "IVCISA",
    "keyrus brasil": "Keyrus Brasil Servi\u00e7os de Informatica Ltda.",
    "keyrus":      "Keyrus Brasil Servi\u00e7os de Informatica Ltda.",
    "egos bi":     "EGOS BI SA DE CV",
    "seidor latam": "SEIDOR ANALYTICS NORTH AMERICA CORP",
    "seidor analytics": "SEIDOR ANALYTICS NORTH AMERICA CORP",
    "tcs":         "Tata Consultancy Services",
    "tata":        "Tata Consultancy Services",
    "hexaware":    "Hexaware Technologies",
    "tek systems": "TEKsystems Global Services, LLC.",
    "teksystems":  "TEKsystems Global Services, LLC.",
    "perficient":  "Perficient Inc.",
    "spaulding":   "Spaulding Ridge",
    "tiger analytics": "Tiger Analytics Inc.",
    "citiustech":  "CitiusTech Inc.",
    "sparq":       "Sparq Holdings, Inc.",
}

# ── Quarter keywords ──────────────────────────────────────────────────────────
_COMPARE_RE = re.compile(r'\bcompare\b|vs\.?|versus|\bqoq\b|q2\s+and\s+q3|q2\s+vs\s+q3|both\s+quarter|quarter\s+over\s+quarter', re.I)
_YTD_RE     = re.compile(r'\bytd\b|year\s+to\s+date|full\s+year|all\s+quarter|fy27\s+total', re.I)
_Q1_RE      = re.compile(r'\bq1\b|first\s+quarter|q1\s+fy27|feb[-–]apr|february\s+to\s+april', re.I)
_Q2_RE      = re.compile(r'\bq2\b|last\s+quarter|previous\s+quarter|prior\s+quarter|q2\s+fy27|may[-–]jul', re.I)
_Q3_RE      = re.compile(r'\bq3\b|this\s+quarter|current\s+quarter|q3\s+fy27|aug[-–]oct', re.I)

# ── Metric keywords ───────────────────────────────────────────────────────────
_CREDIT_RE      = re.compile(r'\bcredits?\b|\bcredit\s+spend\b|\bspending\b|\btoken\s+credits?\b', re.I)
_TOKEN_RE       = re.compile(r'\btokens?\b|\btoken\s+usage\b|\btoken\s+consumption\b', re.I)
_EACV_RE        = re.compile(r'\beacv\b|\bacv\b|\bcontract\s+value\b|\brevenue\b|\bworth\b|\$\s*\d|\bdollar', re.I)
_ATTRIBUTION_RE = re.compile(r'\battribution\b|\bsource\b|\bse\s+comment\b|\bpse\s+comment\b|\bpartner\s+comment\b|\bfeature\s+flag\b|\bhow\s+detected\b|\bhow\s+counted\b|\bsignal\b', re.I)
_CONFIDENCE_RE  = re.compile(r'\bconfidence\s+band\b|\bconfidence\s+score\b|\bconfidence\b|\bhigh\s+confidence\b|\bmedium\s+confidence\b', re.I)
_STALLED_RE     = re.compile(r'\bstall(ed)?\b|\bstuck\b|\baging\b|\baged\b|\bat.risk\b|\binactive\b|\bold\s+uc\b', re.I)
_WOW_RE         = re.compile(r'\bwow\b|\bweek\s+over\s+week\b|\bweek-over-week\b|\bweekly\s+change\b|\bchange\s+this\s+week\b|\bthis\s+week\b', re.I)
_STAGE_RE       = re.compile(r'\bstage\s*\d\b|\bdeployed\b|\bgo.live\b|\bimplementation\b|\bvalidation\b|\bstage\s+breakdown\b|\bfunnel\b|\bstage\s+7\b|\bstage\s+5\b', re.I)
_THEATRE_RE     = re.compile(r'\btheatre\b|\btheater\b|\busmajors\b|\bmajors\b|\bamse\b|\bamsexpansion\b|\bamsa\b|\bacquisition\b|\bpubsec\b|\bpublic\s+sector\b', re.I)
_REGION_RE      = re.compile(r'\bregion\b|\bnoam\b|\bapj\b|\bemea\b|\bamericas\b', re.I)
_TARGET_RE      = re.compile(r'\btarget\b|\bgoal\b|\b50%\b|\b75%\b|\bmeet(ing)?\b|\bgap\b|\bneed\s+to\s+hit\b|\bpartners\s+meeting\b|\bpartners\s+above\b|\bpartners\s+below\b|\babove\s+target\b|\bbelow\s+target\b|\bhitting\s+target\b|\bat\s+target\b', re.I)
_COCO_COUNT_RE  = re.compile(r'\bcoco\s+uc\b|\bcoco\s+use\s+case\b|\bcoco\s+count\b|\bhow\s+many\s+coco\b|\bis_coco_final\b|\bcoco\s+attach(ed)?\b|\bcoco\s+adoption\b|\badoption\s+rate\b|\badoption\s*%|\bcoco\s*%|\bcoco\s+percentage\b|\bhow\s+many\s+use\s+case\b|\btotal\s+uc\b|\btotal\s+use\s+case\b', re.I)

# ── Use-case analysis — partner-scoped deep-dive with account/credit context ──
# Intercepts "why" + partner + metric, "which use case is driving", "analyse the UCs"
# These require the full partner UC list + per-account credit linkage.
_UC_ANALYSIS_RE = re.compile(
    r'\bwhy\b.*\b(credit|token|coco|decline|drop|change|decrease|increase)\b'
    r'|\b(decline|drop|decrease|increase)\b.*\b(credit|token|coco)\b'
    r'|\bwhich\s+use\s+case.*driv\w*\b|\bdri\w+.*\buse\s+case\b'
    r'|\buse\s+case.*analy\w+|\banalys[ei]\w*.*use\s+case'
    r'|\buse\s+case.*breakdown\b|\bbreakdown.*use\s+case'
    r'|\buse\s+case.*driver\b|\bdriver.*use\s+case'
    r'|\bwhat.*causing\b|\broot\s+cause\b'
    r'|\buse\s+case.*in\s+scope\b|\bin\s+scope.*use\s+case'
    r'|\buse\s+case.*for\s+partner\b|\bpartner.*use\s+case\s+list\b'
    r'|\bshow\s+(me\s+)?the\s+use\s+cases?\s+(for|of)\b'
    r'|\blist\s+(the\s+)?use\s+cases?\s+(for|of)\b'
    r'|\buse\s+cases?\s+for\s+\w',
    re.I,
)

# ── Row-level questions — always fall through to Cortex Agent ─────────────────
# These ask for specific items (which UC, list, top N) not aggregate counts.
# Intercept would return an aggregate, which doesn't answer the question.
_ROW_LEVEL_RE = re.compile(
    r'\bwhich\s+(use\s+case|uc|one|account|partner)\b'
    r'|\blist\s+(the|all|use|uc)\b'
    r'|\bshow\s+(me\s+)?(the|all|use|uc|which)\b'
    r'|\bname\s+(the|all|each)\b'
    r'|\btop\s+\d+\b'
    r'|\bhighest\s+(eacv|value|token|credit)\b'
    r'|\blowest\s+(eacv|value|token|credit)\b'
    r'|\bfrom\s+these\b'
    r'|\bof\s+these\b'
    r'|\bspecific\s+use\s+case\b'
    r'|\bwhich\s+\d+\b',
    re.I,
)

# ── Group keywords ────────────────────────────────────────────────────────────
_GSI_RE     = re.compile(r'\bgsis?\b|\bglobal\s+si\b|\bglobal\s+system\s+integrator\b', re.I)
_NOAM_RE    = re.compile(r'\bnoam\s+rsi\b|\bnoam\s+si\b|\bregional\s+si\b|\bnoam\s+partner\b|\bnoam\s+rsis?\b', re.I)
_APJ_RE     = re.compile(r'\bapj\s+rsi\b|\bapj\s+partner\b|\bapj\s+rsis?\b', re.I)
_EMEA_RE    = re.compile(r'\bemea\s+rsi\b|\bemea\s+partner\b|\bemea\s+si\b|\bemea\s+rsis?\b', re.I)
_LATAM_RE   = re.compile(r'\blatam\s+rsi\b|\blatam\s+partner\b|\blatam\s+si\b|\blatam\s+rsis?\b', re.I)

# ── Global aggregation phrases ────────────────────────────────────────────────
_GLOBAL_RE  = re.compile(r'\boverall\b|\ball\s+partners?\b|\bmanaged\s+partners?\b|\bevery\s+partner\b|\bhow\s+many\s+partners?\b|\btotal\s+partners?\b|\bacross\s+all\b|\bportfolio\b', re.I)


def _detect_quarter(text: str) -> str | None:
    if _COMPARE_RE.search(text):
        return "both"
    if _YTD_RE.search(text):
        return "ytd"
    if _Q1_RE.search(text):
        return "q1"
    if _Q2_RE.search(text):
        return "q2"
    if _Q3_RE.search(text):
        return "q3"
    return None


def _detect_partner(text: str) -> str | None:
    """Longest-match lookup against all known partner spellings, including short forms."""
    t = text.lower()
    best = None
    best_len = 0
    # Check full alias map first
    for raw, canonical in PARTNER_CANONICAL_BY_LOWER.items():
        if len(raw) > best_len and raw in t:
            best = canonical
            best_len = len(raw)
    # Check short-form supplement (only if longer than current best)
    for short, canonical in _SHORT_FORMS.items():
        if len(short) > best_len and short in t:
            best = canonical
            best_len = len(short)
    return best


def _detect_group(text: str) -> str | None:
    if _GSI_RE.search(text):
        return "GSI"
    if _NOAM_RE.search(text):
        return "NOAM"
    if _APJ_RE.search(text):
        return "APJ"
    if _EMEA_RE.search(text):
        return "EMEA"
    if _LATAM_RE.search(text):
        return "LATAM"
    return None


def _detect_metric(text: str) -> str | None:
    # Order: specific → general. Credits before tokens (both are "token" adjacent).
    # UC analysis must be checked FIRST — it covers WHY/driver questions that
    # would otherwise fall into credits/tokens/coco_count and lose the deep context.
    if _UC_ANALYSIS_RE.search(text):
        return "uc_analysis"
    if _CREDIT_RE.search(text):
        return "credits"
    if _TOKEN_RE.search(text):
        return "tokens"
    if _EACV_RE.search(text):
        return "eacv"
    if _ATTRIBUTION_RE.search(text):
        return "attribution"
    if _CONFIDENCE_RE.search(text):
        return "confidence"
    if _STALLED_RE.search(text):
        return "stalled"
    if _WOW_RE.search(text):
        return "wow"
    if _STAGE_RE.search(text):
        return "stage"
    if _THEATRE_RE.search(text):
        return "theatre"
    if _REGION_RE.search(text) and not _GSI_RE.search(text):
        # "EMEA" alone → region; "EMEA RSI" → group (caught earlier)
        return "region"
    if _TARGET_RE.search(text):
        return "target"
    if _COCO_COUNT_RE.search(text):
        return "coco_count"
    return None


def detect_intent(question: str, chat_history: list = None) -> dict:
    """
    Parse a question into a structured intent dict.

    Returns:
        metric   : str | None   — which metric category to resolve
        quarter  : str          — q1/q2/q3/ytd/both (defaults to "q3")
        partner  : str | None   — canonical partner name if mentioned
        group    : str | None   — GSI/NOAM/APJ/EMEA if mentioned
        global_  : bool         — true for portfolio-wide aggregation phrases
        confidence: "high"|"low"
    """
    q = question or ""

    partner = _detect_partner(q)
    group   = _detect_group(q)
    quarter = _detect_quarter(q)
    metric  = _detect_metric(q)
    global_ = bool(_GLOBAL_RE.search(q))

    # Carry entity forward from recent chat history when pronouns are used
    if chat_history and not partner and not group:
        for msg in reversed(chat_history[-6:]):
            content = msg.get("content", "")
            cp = _detect_partner(content)
            cg = _detect_group(content)
            if cp and not partner:
                partner = cp
            if cg and not group:
                group = cg
            if partner or group:
                break

    has_entity = bool(partner or group or global_)
    has_metric = bool(metric)

    # Row-level questions always fall through — EXCEPT uc_analysis which has its
    # own programmatic path that handles per-UC and per-account detail.
    if _ROW_LEVEL_RE.search(q) and metric != "uc_analysis":
        return {
            "metric": metric, "quarter": quarter or "q3",
            "partner": partner, "group": group, "global_": global_,
            "confidence": "low",
        }

    # High confidence: clear metric AND (known entity OR quarter-explicit OR global aggregation)
    # Exception: tokens/credits need a specific entity — too broad otherwise
    # Dimension metrics (theatre/region/stage) are self-describing — no entity needed
    _DIMENSION_METRICS = {"theatre", "region", "stage", "attribution", "confidence"}
    if metric in ("tokens", "credits") and not (partner or group):
        confidence = "low"
    elif metric == "uc_analysis" and not (partner or group):
        confidence = "low"  # need a specific partner to do UC analysis
    elif has_metric and (has_entity or quarter or metric in _DIMENSION_METRICS):
        confidence = "high"
    elif quarter == "both" and has_entity:
        # "Compare Q2 vs Q3 for Accenture" — default to coco_count comparison
        if not metric:
            metric = "coco_count"
        confidence = "high"
    else:
        confidence = "low"

    return {
        "metric":     metric,
        "quarter":    quarter or "q3",
        "partner":    partner,
        "group":      group,
        "global_":    global_,
        "confidence": confidence,
    }
