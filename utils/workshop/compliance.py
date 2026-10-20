"""Deterministic compliance helpers for partner-facing workshop text.

Rules follow the Alliances Data Sharing deck: no contract/consumption numbers,
no internal list/gate terminology, no links outside the bundled allowlist.
"""
import re

_SUFFIXES = {"inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited",
             "plc", "ag", "gmbh", "co", "company", "sa", "nv", "bv", "lp", "llp"}

_PATTERNS = [
    re.compile(r"[$€£]\s?\d[\d,.]*\s?(?:k|m|mm|b|bn)?\b", re.I),
    re.compile(r"\b\d[\d,.]*\s?(?:k|m|mm|bn)?\s?(?:usd|dollars)\b", re.I),
    re.compile(r"\b\d[\d,.]*\s*(?:ai\s+)?credits?\b", re.I),
    re.compile(r"\b(?:eacv|tcv|acv|arr|run[- ]rate)\b", re.I),
    re.compile(r"\b(?:red|green)[ -]?(?:light|list)\b", re.I),
    re.compile(r"\btop[_ ]snowflake[_ ]companies\b", re.I),
    re.compile(r"\b(?:restricted account|not on the list|no (?:usage|a360|account) data"
               r"|data (?:is )?not available|limited data)\b", re.I),
    re.compile(r"\bstage\s*[1-7]\b", re.I),
    re.compile(r"\b(?:health|churn|meddpicc)\s*score\b", re.I),
]
_URL = re.compile(r"https?://[^\s)\"'<>]+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def normalize_company(name: str) -> str:
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).split()
    if s and s[0] == "the":
        s = s[1:]
    while s and s[-1] in _SUFFIXES:
        s = s[:-1]
    return " ".join(s)


def find_violations(text: str) -> list:
    hits = []
    for p in _PATTERNS:
        hits.extend(m.group(0) for m in p.finditer(text or ""))
    return hits


def scrub(text: str, allowed_links: set) -> str:
    def _link(m):
        url = m.group(0).rstrip(".,;")
        return m.group(0) if url in allowed_links else ""
    text = _URL.sub(_link, text or "")
    kept = [s for s in _SENT_SPLIT.split(text) if not find_violations(s)]
    return re.sub(r"\s{2,}", " ", " ".join(kept)).strip()
