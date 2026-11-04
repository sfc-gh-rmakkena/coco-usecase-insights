"""Deny terms derived from private use-case context (never rendered, never sent back to the page).

Conservative extraction of facts that must not appear in partner-facing text: numeric facts
(volumes, counts, years), non-Snowflake vendors, locations, people, sub-brands / business-unit
names and internal code names. Exemptions for terms that are public for a use case (its name,
account and partner) are applied by the generator.
"""
import functools
import json
import re

from .assets import _ASSETS

TEXT_FIELDS = ("DESCRIPTION", "MEDDPICC_PAIN", "MEDDPICC_METRICS", "MEDDPICC_DECISION_CRITERIA",
               "MEDDPICC_DECISION_PROCESS", "SE_COMMENTS", "PARTNER_COMMENTS", "IMPLEMENTATION_COMMENTS",
               "SPECIALIST_COMMENTS", "NEXT_STEPS", "RISK_DESCRIPTION", "LOSS_DESCRIPTION")
# Account/UC attributes that must never be echoed (skill: no industry, location, website, stage).
WHOLE_FIELDS = ("STAGE", "INDUSTRY", "SUB_INDUSTRY", "BILLING_COUNTRY", "BILLING_STATE", "WEBSITE", "CLOUD_REGION")
YEAR_FIELDS = ("DECISION_DATE", "GO_LIVE_DATE", "IMPLEMENTATION_START_DATE", "TECHNICAL_WIN_DATE")

_NUM_UNIT = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?\s?(?:[kKmMbB]\+?(?![\w])|\+|%)")
_YEAR = re.compile(r"(?<![\d.])(?:19|20)\d{2}(?![\d.])")
_COUNT_NOUNS = ("ships|vessels|sources|systems|records|rows|users|sites|parks|locations|stores|countries|regions|"
                "tables|reports|dashboards|employees|customers|accounts|brands|hotels|resorts|applications|apps|"
                "markets|plants|factories|warehouses|entities|teams|developers|analysts")
_COUNT = re.compile(r"\b(\d+(?:[.,]\d+)?)((?:\s+[A-Za-z][\w-]*){0,2}?)\s+(" + _COUNT_NOUNS + r")\b")
_CAP_SEQ = re.compile(r"\b[A-Z][a-zA-Z]+(?:[ \t]+[A-Z][a-zA-Z]+)+")
_PAREN_WORD = re.compile(r"\b[A-Z][\w&.-]*\s\(([A-Z][a-z]{2,12})\)")
_PAREN_ACRO = re.compile(r"\(([A-Z]{2,6})\)")
_CODE_NAME = re.compile(r"\b([A-Z]{2,}[ -]?\d+)\b(?![/.\d])")
_SLASH_LIKE = re.compile(r"\b([A-Z][a-z]{2,})(?=/[A-Z]|-like\b)")
_GROWTH = re.compile(r"\b(?:(\w+)\s+(?:expansion|growth|scalability)|(?:doubling|tripling|expanding|growing)\s+(?:the\s+|its\s+)?(\w+))\b",
                     re.I)
_GROWTH_SAFE = {"data", "query", "user", "workload", "storage", "compute", "the", "its", "their", "and", "of"}
_LEAD_STOP = {"The", "A", "An", "This", "That", "These", "Our", "We", "In", "For", "And", "Or", "To", "Of", "With",
              "On", "At", "By", "From", "As", "If", "When", "Then", "Also", "Per", "Via"}
# Words that never make a term on their own (Snowflake products, tech and generic business words).
_GENERIC = {
    "snowflake", "cortex", "openflow", "snowpipe", "snowpark", "streamlit", "iceberg", "horizon", "medallion",
    "bronze", "silver", "gold", "data", "phase", "partner", "customer", "team", "project", "platform", "cloud",
    "finance", "financial", "analytics", "business", "intelligence", "engineering", "science", "code", "agent",
    "agents", "semantic", "views", "view", "dynamic", "tables", "table", "ai", "ml", "sql", "status", "green",
    "red", "yellow", "amber", "none", "other", "internal", "external", "global", "domestic", "native", "standard",
}
_TECH_ACRONYMS = {
    "AI", "BI", "ML", "SQL", "AWS", "GCP", "CDC", "ETL", "ELT", "API", "UI", "UX", "RBAC", "PII", "SLA", "KPI", "GA",
    "IT", "DDL", "DML", "JSON", "CSV", "XML", "LLM", "RAG", "MCP", "SSO", "SCD", "DMF", "DMFS", "SPCS", "SAR",
    "POC", "POV", "PS", "SE", "PSE", "MVP", "ROI", "QA", "UAT", "DEV", "PROD", "OLTP", "OLAP", "ERP", "CRM",
    "HR", "ADLS", "EC2", "S3", "IAM", "VPC", "SSL", "TLS", "NLP", "OCR", "FAQ", "DX", "COCO",
}


@functools.lru_cache(maxsize=None)
def _terms(name) -> tuple:
    p = _ASSETS / name
    return tuple(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else ()


def _has(term, text) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text) is not None


def _generic(seq) -> bool:
    return all(w.lower() in _GENERIC for w in seq.split())


def _strip_lead(seq) -> str:
    words = seq.split()
    while words and words[0] in _LEAD_STOP:
        words = words[1:]
    return " ".join(words)


def numeric_terms(text) -> list:
    out = []
    for m in _NUM_UNIT.finditer(text):
        t = re.sub(r"\s+", "", m.group(0))
        out.append(t)
        if t.endswith("+") and len(t) > 2 and not t[-2].isdigit():
            out.append(t[:-1])  # "10B+" -> also "10B"
    for m in _COUNT.finditer(text):
        out.append(m.group(0))
        first = (m.group(2) or "").split()
        out.append(f"{m.group(1)} {first[0]}" if first else f"{m.group(1)} {m.group(3)}")
    out += _YEAR.findall(text)
    return out


def growth_terms(text) -> list:
    """Growth / expansion plans ("fleet expansion", "doubling the fleet") as phrases about their object."""
    out = []
    for m in _GROWTH.finditer(text or ""):
        obj = (m.group(1) or m.group(2) or "").lower()
        if len(obj) < 3 or obj in _GROWTH_SAFE or obj in _GENERIC:
            continue
        out += [f"{obj} expansion", f"expanding {obj}", f"expanding the {obj}", f"{obj} growth",
                f"growing {obj}", f"doubling the {obj}", f"{obj} scalability", f"expansion of the {obj}"]
    return out


def text_terms(text, account="") -> list:
    """People, vendors, locations, sub-brands and code names found in one free-text value."""
    out = []
    out += [v for v in _terms("vendor_terms.json") if _has(v, text)]
    out += [c for c in _terms("locations.json") if _has(c, text)]
    names = set(_terms("first_names.json"))
    for m in re.finditer(r"\b([A-Z][a-z]+)(?:[ \t]+([A-Z][a-z]+))?", text):
        first, last = m.group(1), m.group(2)
        if first in names:
            out.append(first)
            if last and last.lower() not in _GENERIC and last not in _LEAD_STOP:
                out += [f"{first} {last}", last]
    acct_words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", account or "")}
    acct = (account or "").lower()
    for line in text.splitlines():
        for m in _CAP_SEQ.finditer(line):
            seq = _strip_lead(m.group(0))
            if len(seq.split()) < 2 or _generic(seq) or seq.lower() in acct:
                continue
            if acct_words & {w.lower() for w in seq.split()}:
                out.append(seq)  # sub-brand / business unit of the account
                words = seq.split()
                rest = [w for w in words if w.lower() not in acct_words]
                for cand in (rest, words[1:] if words[0].lower() in acct_words else []):
                    if len(cand) >= 2 and not _generic(" ".join(cand)):
                        out.append(" ".join(cand))  # "Signature Experiences", "Cruise Line"
    out += [w for w in _PAREN_WORD.findall(text) if w.lower() not in _GENERIC]
    out += [a for a in _PAREN_ACRO.findall(text) if a not in _TECH_ACRONYMS]
    out += [c for c in _CODE_NAME.findall(text) if re.split(r"[ -]?\d", c)[0] not in _TECH_ACRONYMS]
    out += [w for w in _SLASH_LIKE.findall(text) if w.lower() not in _GENERIC]
    return out


def whole_value_terms(value, words=False) -> list:
    v = str(value or "").strip()
    parts = [v, v.replace("&", "and")] + [p.strip() for p in re.split(r"\s+-\s+|/|;|,|\|", v)]
    if words:  # industry values: each distinctive word too ("Travel", "Hospitality")
        parts += [w for w in re.findall(r"[A-Za-z]{5,}", v) if w.lower() not in _GENERIC]
    return [p for p in parts if len(p) >= 3 and not p.isdigit()]


_LABEL = re.compile(r"(?:^|\n|[.;]\s+)([A-Z][\w&/-]*(?:[ \t]+[A-Za-z&/-]+){0,4})\s*:(?!//)")


def meddpicc_labels(text) -> list:
    """Heading labels in MEDDPICC fields ("Fleet Scalability: ...") - never echoed verbatim."""
    return [m.strip() for m in _LABEL.findall(text or "") if len(m.split()) >= 2 and not _generic(m)]


def private_deny_terms(private_context, account="") -> list:
    ctx = {k: (_URL_IN_TEXT.sub(" ", v) if isinstance(v, str) else v)
           for k, v in (private_context or {}).items()}
    out = []
    for k in TEXT_FIELDS:
        v = ctx.get(k)
        if v:
            out += numeric_terms(str(v)) + text_terms(str(v), account) + growth_terms(str(v))
            if k.startswith("MEDDPICC_"):
                out += meddpicc_labels(str(v))
    for k in WHOLE_FIELDS:
        if ctx.get(k):
            out += whole_value_terms(ctx[k], words=k in ("INDUSTRY", "SUB_INDUSTRY"))
            out += text_terms(str(ctx[k]), account)
    for k in YEAR_FIELDS:
        out += re.findall(r"(?:19|20)\d{2}", str(ctx.get(k) or ""))
    seen, uniq = set(), []
    for t in out:
        t = t.strip()
        # URL fragments (e.g. "https:") would blank every link and the SQL that cites it.
        if len(t) >= 2 and t.lower() not in seen and not _URL_FRAGMENT.match(t):
            seen.add(t.lower())
            uniq.append(t)
    return uniq


# URLs pasted into private notes are not confidential vocabulary; drop them before extraction.
_URL_IN_TEXT = re.compile(r"(?:https?://|www\.)\S+", re.I)
_URL_FRAGMENT = re.compile(r"^(?:https?:?/*|www\.?|\.com|:?//)$", re.I)


_BACKSTOP_WORDS = ("recipe", "recipes", "cookbook", "cookbooks", "% match")
_RECIPE_URL = re.compile(r"https?://\S*(?:cookbook|recipe)\S*|\.\./\.\./[\w./-]+", re.I)
_OBJ_NAME = re.compile(r"\bCOOKBOOK_[A-Z0-9_]+\b", re.I)


@functools.lru_cache(maxsize=None)
def recipe_backstop_terms() -> tuple:
    """Terms that would attribute plan content to the bundled build guides: the words, every
    guide title, distinctive (4+ word) sub-headings, guide/cookbook URLs and object names."""
    from .assets import recipes_index
    from .recipes import load_units
    out = list(_BACKSTOP_WORDS)
    out += [r["title"] for r in recipes_index() if r.get("title")]
    for u in load_units():
        h = re.sub(r"[`*?:()]", "", u["heading"]).strip()
        if len(h.split()) >= 4:
            out.append(h)
        blob = u["text"] + "\n" + u["sql"]
        out += [m.rstrip(".,;:)") for m in _RECIPE_URL.findall(blob)]
        out += [m.upper() for m in _OBJ_NAME.findall(blob)]
    seen, uniq = set(), []
    for t in out:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return tuple(uniq)
