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


def find_violations(text: str, deny=()) -> list:
    hits = []
    for p in _PATTERNS + _deny_patterns(deny):
        hits.extend(m.group(0) for m in p.finditer(text or ""))
    return hits


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
