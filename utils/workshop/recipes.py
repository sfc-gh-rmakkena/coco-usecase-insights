"""Bundled build guides -> grounding content (internal only; never named in output).

Units are cut at bundle time (scripts/bundle_workshop_assets.py) from each guide's headings.
At run time: deterministic prefilter -> rubric judge (LLM answers, app scores) -> select ->
integration_pack, which turns the selected guides' units into ordinary grounding snippets.
"""
import functools
import hashlib
import json
import re

from . import capabilities
from .assets import _ASSETS

UNITS_FILE = "recipe_units.json"
PREFILTER_K = 6
SELECT_MIN = 80  # strictly greater than
SELECT_MAX = 3
PACK_CHARS = 12000

# ## heading (lower-case substring) -> unit kind; ### headings inherit their parent's kind.
_KINDS = [("when to use", "when_to_use"), ("how it works", "how_it_works"),
          ("prerequisite", "prerequisites"), ("quickstart", "quickstart"),
          ("walkthrough", "step"), ("verify", "verify"), ("gotcha", "gotchas"),
          ("teardown", "teardown"), ("coding agent", "agent_run"),
          ("reference", "references"), ("related skill", "related_skills")]
PACK_KINDS = ("quickstart", "step", "how_it_works", "verify", "gotchas")
_KIND_LABEL = {"quickstart": "setup", "step": "implementation step", "how_it_works": "design",
               "verify": "verification", "gotchas": "operational check"}
_HEAD = re.compile(r"^(#{2,3})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*```(\w*)")
_URL = re.compile(r"https://(?:docs|quickstarts)\.snowflake\.com[^\s)\"'<>`\]*]*")
_NOT_WHEN = re.compile(r"^\s*when not to use", re.I)


# ---------------------------------------------------------------- bundle time

def _kind(heading) -> str:
    h = heading.lower()
    return next((k for s, k in _KINDS if s in h), "other")


def _caps_in(text) -> list:
    return [k for k in capabilities.CAPS if capabilities.cap_matches(k, text)]


def recipe_caps(meta) -> list:
    """Capabilities named by a guide's topics/features/related skills (index metadata)."""
    out = []
    for t in list(meta.get("topics") or []) + list(meta.get("features") or []):
        out += [k for k in _caps_in(str(t).replace("-", " ")) if k not in out]
    for s in meta.get("related_skills") or []:
        for r in capabilities.MAPPING:
            if s in r[2] and r[3][0] not in out:
                out.append(r[3][0])
    return out


def _unit(rid, n, kind, heading, prose, sql, rcaps):
    text = "\n".join(prose).strip()
    sql_text = "\n\n".join(s.strip() for s in sql if s.strip())
    kw = _caps_in(f"{heading}\n{sql_text}")
    urls = []
    for u in _URL.findall(f"{text}\n{sql_text}"):
        u = u.rstrip(".,;:")
        if u not in urls:
            urls.append(u)
    return {"recipe_id": rid, "unit_id": f"{rid}#{n:02d}", "kind": kind, "heading": heading,
            "text": text, "sql": sql_text, "doc_urls": urls,
            "capabilities": kw + [k for k in rcaps if k not in kw]}


def split_units(rid, body, meta=None) -> list:
    """Split one guide on ##/### headings (outside code fences) into tagged units."""
    rcaps = recipe_caps(meta or {})
    units, kind, parent = [], "overview", "overview"
    heading, prose, sql, buf, lang, in_fence = "", [], [], [], "", False

    def flush():
        if not "".join(prose).strip() and not any(s.strip() for s in sql):
            return
        if kind == "when_to_use":
            i = next((j for j, l in enumerate(prose) if _NOT_WHEN.match(l)), None)
            if i is not None:
                units.append(_unit(rid, len(units), "when_to_use", heading, prose[:i], sql, rcaps))
                units.append(_unit(rid, len(units), "when_not_to_use", "When not to use",
                                   prose[i + 1:], [], rcaps))
                return
        units.append(_unit(rid, len(units), kind, heading, prose, sql, rcaps))

    for line in (body or "").splitlines():
        f = _FENCE.match(line)
        if f:
            if in_fence:
                if lang == "sql":
                    sql.append("\n".join(buf))
                in_fence, buf = False, []
            else:
                in_fence, lang, buf = True, f.group(1).lower(), []
            continue
        if in_fence:
            buf.append(line)
            continue
        h = _HEAD.match(line)
        if h:
            flush()
            prose, sql = [], []
            heading = h.group(2).strip()
            if len(h.group(1)) == 2:
                parent = _kind(heading)
            kind = parent
            continue
        if line.startswith("# ") and kind == "overview":
            continue  # the guide title is not unit content
        prose.append(line)
    flush()
    return units


def digest(body) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def build_units(index, body_fn) -> dict:
    """index: recipes_index entries; body_fn(recipe_id) -> markdown."""
    units, digests = [], {}
    for meta in sorted(index, key=lambda m: m["id"]):
        body = body_fn(meta["id"])
        digests[meta["id"]] = digest(body)
        units += split_units(meta["id"], body, meta)
    return {"digests": digests, "units": units}


# ---------------------------------------------------------------- run time

@functools.lru_cache(maxsize=None)
def _bundle() -> dict:
    p = _ASSETS / UNITS_FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"digests": {}, "units": []}


def load_units() -> list:
    return _bundle()["units"]


def _meta(rid):
    from .assets import recipe_meta
    return recipe_meta(rid)


_STOP = {"with", "from", "that", "this", "into", "over", "your", "their", "will", "using",
         "data", "snowflake", "use", "case", "them", "they", "have", "each", "when", "what",
         "which", "about", "build", "need", "needs", "more", "than", "only", "also"}


def _words(text) -> set:
    return {w for w in re.findall(r"[a-z][a-z0-9-]{3,}", str(text or "").lower()) if w not in _STOP}


def _by_recipe(units) -> dict:
    out = {}
    for u in units:
        out.setdefault(u["recipe_id"], []).append(u)
    return out


def prefilter(uc, required_caps, units, k=PREFILTER_K) -> list:
    """Top-k guide ids by capability, skill and when-to-use keyword overlap (deterministic)."""
    req, skills = set(required_caps or ()), set(uc.get("skills") or ())
    words = _words(f"{uc.get('name', '')} {uc.get('sanitized_desc', '')}")
    ranked = []
    for rid, us in _by_recipe(units).items():
        caps = {c for u in us for c in u["capabilities"]}
        rskills = set(_meta(rid).get("related_skills") or ())
        when = " ".join(u["text"] for u in us if u["kind"] == "when_to_use")
        score = 3 * len(caps & req) + 2 * len(rskills & skills) + len(words & _words(when))
        if score > 0:
            ranked.append((-score, rid))
    return [rid for _, rid in sorted(ranked)[:k]]


def candidate_view(rid, units) -> dict:
    """What the judge reads for one guide."""
    us = [u for u in units if u["recipe_id"] == rid]

    def txt(kind):
        return "\n".join(u["text"] for u in us if u["kind"] == kind).strip()[:3000]
    return {"id": rid, "when_to_use": txt("when_to_use"), "when_not_to_use": txt("when_not_to_use"),
            "how_it_works": txt("how_it_works"),
            "steps": [u["heading"] for u in us if u["kind"] in ("step", "quickstart")]}


# Rubric: criterion -> {level: points}; booleans use True.
RUBRIC = {"problem_fit": {"strong": 40, "partial": 20},
          "capability_fit": {"strong": 30, "partial": 15},
          "steps_reusable": {True: 20},
          "audience_fit": {True: 10}}
CONTRA_PENALTY = 50


def _norm(s):
    return " ".join(re.sub(r"[`*_]", "", str(s or "")).lower().split())


def _evidenced(quote, source) -> bool:
    q = _norm(quote)
    return len(q) >= 8 and q in _norm(source)


def _level(v):
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return True if s in ("true", "yes") else s


def score_one(answer, view) -> int:
    """0-100 from the judge's rubric answers. A criterion only scores when its evidence quote
    is found verbatim in the guide text shown to the judge; an evidenced contraindication
    (quoted from when-not-to-use) subtracts CONTRA_PENALTY."""
    ev = answer.get("evidence") if isinstance(answer.get("evidence"), dict) else {}
    source = "\n".join([view["when_to_use"], view["when_not_to_use"], view["how_it_works"]]
                       + list(view["steps"]))
    total = 0
    for crit, pts in RUBRIC.items():
        if _evidenced(ev.get(crit), source):
            total += pts.get(_level(answer.get(crit)), 0)
    if _level(answer.get("contraindicated")) is True and _evidenced(ev.get("contraindicated"),
                                                                   view["when_not_to_use"]):
        total -= CONTRA_PENALTY
    return max(0, min(100, total))


def score_all(judged, candidates, units) -> dict:
    views = {rid: candidate_view(rid, units) for rid in candidates}
    out = {rid: 0 for rid in candidates}
    rows = judged.get("recipes") if isinstance(judged, dict) else None
    for a in rows if isinstance(rows, list) else []:
        if isinstance(a, dict) and a.get("recipe_id") in views:
            out[a["recipe_id"]] = score_one(a, views[a["recipe_id"]])
    return out


def select(scores) -> list:
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [rid for rid, s in ranked if s > SELECT_MIN][:SELECT_MAX]


# ---------------------------------------------------------------- integration pack

_OBJ3 = re.compile(r"\bCOOKBOOK_[A-Z0-9_]+\.[A-Za-z0-9_$]+\.([A-Za-z0-9_$]+)", re.I)
_OBJ2 = re.compile(r"\bCOOKBOOK_[A-Z0-9_]+\.[A-Za-z0-9_$]+", re.I)
_OBJ1 = re.compile(r"\bCOOKBOOK_[A-Z0-9_]+", re.I)
_ATTRIB_LINE = re.compile(r"recipe|cookbook|github", re.I)


def _obj1(m):
    n = m.group(0).upper()
    if n.endswith("_WH"):
        return "<WAREHOUSE>"
    if re.search(r"_(ROLE|USER|ADMIN|ACCESS|READER|OWNER)$", n):
        return "<ROLE>"
    return "<DB>"


def neutral_sql(sql) -> str:
    """Placeholder object names and drop comment lines that attribute the source."""
    lines = [l for l in str(sql or "").splitlines()
             if not (l.strip().startswith("--") and _ATTRIB_LINE.search(l))]
    s = "\n".join(lines)
    s = _OBJ3.sub(lambda m: "<DB>.<SCHEMA>." + m.group(1), s)
    s = _OBJ2.sub("<DB>.<SCHEMA>", s)
    return _OBJ1.sub(_obj1, s).strip()


def _docs_url(unit, cap, allow):
    for u in unit["doc_urls"]:
        if u.rstrip("/") in allow:
            return u
    docs = capabilities.grounding().get(cap, {}).get("docs") or []
    return next((d["url"] for d in docs if "docs.snowflake.com" in d["url"]), "")


def _pack_recipe(rid, units, required_caps, allow):
    req = list(required_caps or ())
    out, used = [], 0
    us = [u for u in units if u["recipe_id"] == rid and u["kind"] in PACK_KINDS and u["sql"]]
    rcaps = {c for u in units if u["recipe_id"] == rid for c in u["capabilities"]}
    fallback = next((c for c in req if c in rcaps), req[0] if req else "")
    for u in us:
        cap = next((c for c in u["capabilities"] if c in req), fallback)
        sql = neutral_sql(u["sql"])
        if not cap or not sql or used + len(sql) > PACK_CHARS:
            continue
        url = _docs_url(u, cap, allow)
        if not url:
            continue
        used += len(sql)
        n = sum(1 for c, _ in out if c == cap) + 1
        title = f"{capabilities.cap_label(cap)} {_KIND_LABEL[u['kind']]} {n}"
        out.append((cap, {"title": title, "sql": sql, "source_url": url}))
    return out


def _allow():
    from .assets import link_allowlist
    return {u.rstrip("/") for u in link_allowlist()}


def packs_by_recipe(selected, units, required_caps, allow=None) -> dict:
    allow = _allow() if allow is None else {u.rstrip("/") for u in allow}
    return {rid: [e for _, e in _pack_recipe(rid, units, required_caps, allow)] for rid in selected}


def integration_pack(selected, units, required_caps, allow=None) -> dict:
    """capability -> [grounding sql_snippet entries {title, sql, source_url}]."""
    allow = _allow() if allow is None else {u.rstrip("/") for u in allow}
    out = {}
    for rid in selected:
        for cap, e in _pack_recipe(rid, units, required_caps, allow):
            out.setdefault(cap, []).append(e)
    return out


def merge_grounding(base, pack) -> dict:
    out = {k: dict(v) for k, v in (base or {}).items()}
    for cap, entries in (pack or {}).items():
        g = out.setdefault(cap, {"docs": [], "quickstarts": [], "sql_snippets": []})
        g["sql_snippets"] = list(g.get("sql_snippets") or []) + list(entries)
    return out


_TOKEN = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]{2,}\b")
# Generic identifiers that ordinary SQL contains; never evidence that a pack was used.
_GENERIC = {"DEFAULT_ROLE", "DEFAULT_WAREHOUSE", "DEFAULT_NAMESPACE", "OBJECT_CONSTRUCT", "ARRAY_AGG",
            "TARGET_SCHEMA", "TARGET_LAG", "RUN_NAME", "RUN_STATUS", "METRIC_NAME", "TABLE_NAME",
            "SCHEMA_NAME", "DATABASE_NAME", "USER_NAME", "ROLE_NAME", "CREATED_AT", "UPDATED_AT",
            "EVALUATED_AT", "IS_ROLE_IN_SESSION", "PARSE_JSON", "TO_VARCHAR", "TRY_CAST", "DATE_TRUNC",
            "SNOWFLAKE_SSE", "INFORMATION_SCHEMA", "ACCOUNT_USAGE", "QUERY_HISTORY", "LAST_VALUE",
            "FIRST_VALUE", "ROW_NUMBER", "DATA_AGENT_RUN"}


def key_tokens(entries, base_grounding=None) -> list:
    """Distinctive identifiers in a pack (absent from the base grounding SQL)."""
    base = " ".join(s.get("sql", "") for v in (base_grounding or {}).values()
                    for s in v.get("sql_snippets") or [])
    common = set(_TOKEN.findall(base.upper()))
    toks = set()
    for e in entries:
        toks |= set(_TOKEN.findall(e["sql"].upper()))
    return sorted(t for t in toks - common - _GENERIC if not t.startswith("CURRENT_"))
