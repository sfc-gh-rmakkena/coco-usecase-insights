"""Deterministic compliance helpers for partner-facing workshop text.

Rules follow the Alliances Data Sharing deck: no contract/consumption numbers,
no internal list/gate terminology, no links outside the bundled allowlist.
"""
import re
import unicodedata

_SUFFIXES = {"inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited",
             "plc", "ag", "gmbh", "co", "company", "sa", "nv", "bv", "lp", "llp"}

_PATTERNS = [
    re.compile(r"[$€£¥₹]\s?\d[\d,.]*\s?(?:k|m|mm|b|bn|million|billion|thousand)?\b", re.I),
    re.compile(r"\b(?:usd|eur|gbp|inr|jpy|aud|cad)\s?\d[\d,.]*\s?(?:k|m|mm|b|bn|million|billion)?\b", re.I),
    re.compile(r"\b\d[\d,.]*\s?(?:k|m|mm|bn)?\s?(?:usd|dollars)\b", re.I),
    re.compile(r"\b\d[\d,.]*\s?(?:million|billion|thousand)\s+(?:usd|dollars|euros?)\b", re.I),
    re.compile(r"\b(?:spend|cost|costs|revenue|budget|bookings?|contract)\b[^.]{0,40}?\b\d[\d,.]*\s?[kmb]\b", re.I),
    re.compile(r"\b\d[\d,.]*\s?[kmb]?\s*(?:\w+\s+){0,2}credits?\b", re.I),
    re.compile(r"\bcredits?\b\s*[:=]?\s*\d", re.I),
    re.compile(r"\b(?:EACV|TCV|ACV|ARR)\b"),
    re.compile(r"\brun[- ]rate\b", re.I),
    re.compile(r"\b(?:red|green)[ -]?(?:light|list)(?:ed|s|ing)?\b", re.I),
    re.compile(r"\btop[_ ]snowflake[_ ]companies\b", re.I),
    re.compile(r"\b(?:restricted account|not on the list|no (?:usage|a360|account) data"
               r"|data (?:is )?not available|limited data)\b", re.I),
    re.compile(r"\b(?:sales|deal|opp(?:ortunity)?|use[- ]case)\s+stage\s*[1-7]\b", re.I),
    re.compile(r"\bstage\s*[1-7]\s*(?:opp|deal|use[- ]case)", re.I),
    re.compile(r"\b(?:health|churn|meddpicc)\s*score\b", re.I),
]
# Category per _PATTERNS index (same order), used for non-sensitive degradation reasons.
_CATEGORIES = ["money"] * 5 + ["credits"] * 2 + ["money"] * 2 + ["list_terms"] * 3 \
    + ["stage"] * 2 + ["score"]
# SQL positional column refs ($1:col, $1, $2 AS x, f($1)) are not currency. In SQL text
# a bare trailing ref ("SELECT a, $1") also counts (sql=True); in prose "$5" at line end is money.
_SQL_POS = re.compile(r"\$\d+(?=:|,(?!\d)|\)|\s+(?:AS|FROM)\b)", re.I)
_SQL_POS_EOT = re.compile(r"\$\d+(?=:|,(?!\d)|\)|\s+(?:AS|FROM)\b|[ \t]*;|[ \t]*$)", re.I | re.M)
# Numeric money/credit patterns (indexes into _PATTERNS) replaced by redact_amounts.
_AMOUNT_IDX = range(7)
_URL = re.compile(r"https?://[^\s)\"'<>`\]]+")
_TRAIL = ".,;:!?*"
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def normalize_company(name: str) -> str:
    if not name:
        return ""
    raw = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = raw.replace("&", " and ").replace(".", "")
    s = re.sub(r"[^a-z0-9]+", " ", s).split()
    if s and s[0] == "the":
        s = s[1:]
    while s and s[-1] in _SUFFIXES:
        s = s[:-1]
    return " ".join(s) or re.sub(r"[^a-z0-9]+", "", raw)


def sql_quote(s) -> str:
    """Escape for a single-quoted Snowflake string literal (backslash first, then quote)."""
    return (s or "").replace("\\", "\\\\").replace("'", "''")


def _deny_patterns(deny):
    terms = sorted({t.strip() for t in (deny or ()) if t and t.strip()}, key=len, reverse=True)
    return [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.I) for t in terms]


def _strip_sql_pos(text, sql=False):
    return (_SQL_POS_EOT if sql else _SQL_POS).sub("", text or "")


def redact_amounts(text: str) -> str:
    """Replace currency amounts and credit counts with "[amount]"."""
    text = text or ""
    for i in _AMOUNT_IDX:
        text = _PATTERNS[i].sub("[amount]", text)
    return text


def find_violations(text: str, deny=(), sql=False) -> list:
    text = _strip_sql_pos(text, sql)
    hits = []
    for p in _PATTERNS + _deny_patterns(deny):
        hits.extend(m.group(0) for m in p.finditer(text))
    return hits


def classify_violations(text: str, deny=(), allowed_links=None) -> list:
    """Category names of the checks that fire (never the matched text), in check order."""
    text = _strip_sql_pos(text)
    cats = []
    for p, c in zip(_PATTERNS, _CATEGORIES):
        if c not in cats and p.search(text):
            cats.append(c)
    if any(p.search(text) for p in _deny_patterns(deny)):
        cats.append("deny")
    if allowed_links is not None:
        allowed = {u.rstrip("/") for u in allowed_links}
        if any(m.group(0).rstrip(_TRAIL).rstrip("/") not in allowed for m in _URL.finditer(text)):
            cats.append("link")
    return cats


def scrub(text: str, allowed_links: set, deny=()) -> str:
    allowed = {u.rstrip("/") for u in (allowed_links or ())}

    def _link(m):
        full = m.group(0)
        url = full.rstrip(_TRAIL)
        tail = full[len(url):]
        return full if url.rstrip("/") in allowed else tail

    text = _URL.sub(_link, text or "")
    lines = []
    for line in text.split("\n"):
        kept = [s for s in _SENT_SPLIT.split(line) if not find_violations(s, deny)]
        lines.append(re.sub(r"[ \t]{2,}", " ", " ".join(kept)).rstrip())
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()
