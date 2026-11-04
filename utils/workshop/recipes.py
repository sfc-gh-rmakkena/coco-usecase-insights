"""Bundled build guides -> grounding content (internal only; never named in output).

Units are cut at bundle time (scripts/bundle_workshop_assets.py) from each guide's headings.
At run time, per capability area of the use case: deterministic prefilter -> rubric judge over
(guide, area) pairs (LLM answers, app scores) -> select (one guide per area) -> integration_pack,
which turns the selected guide's units for that area into ordinary grounding snippets.
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


def _areas(uc, required_caps, areas):
    """Capability areas ({area, capabilities, coco_skills}); one catch-all area when none given."""
    if areas:
        return [a for a in areas if a.get("capabilities")]
    return [{"area": "all", "capabilities": list(required_caps or ()), "coco_skills": list(uc.get("skills") or ())}]


def prefilter_scores(uc, required_caps, units, areas=None) -> dict:
    """{(recipe_id, area): overlap score} from capabilities, skills and when-to-use keywords
    (deterministic); only pairs with a capability in common."""
    areas = _areas(uc, required_caps, areas)
    skills = set(uc.get("skills") or ())
    words = _words(f"{uc.get('name', '')} {uc.get('sanitized_desc', '')}")
    out = {}
    for rid, us in _by_recipe(units).items():
        caps = {c for u in us for c in u["capabilities"]}
        rskills = set(_meta(rid).get("related_skills") or ())
        kw = len(words & _words(" ".join(u["text"] for u in us if u["kind"] == "when_to_use")))
        for a in areas:
            hit = caps & set(a["capabilities"])
            if hit:
                out[(rid, a["area"])] = (3 * len(hit) + 2 * len(rskills & (set(a.get("coco_skills") or ()) | skills))
                                         + kw)
    return out


def prefilter(uc, required_caps, units, k=PREFILTER_K, areas=None) -> list:
    """Top-k guide ids overall by their best per-area prefilter score."""
    best = {}
    for (rid, _), s in prefilter_scores(uc, required_caps, units, areas).items():
        best[rid] = max(best.get(rid, 0), s)
    return [rid for _, rid in sorted((-s, rid) for rid, s in best.items() if s > 0)[:k]]


def own_caps(units, rid) -> set:
    """Capabilities a guide's units build themselves (heading + SQL), not inherited from its
    index metadata."""
    return {c for u in units if u["recipe_id"] == rid for c in _caps_in(f"{u['heading']}\n{u['sql']}")}


def eligible(rid, area, units) -> bool:
    """Gate: the guide's own units must cover the area's PRIMARY (first) capability."""
    caps = list(area.get("capabilities") or ())
    return bool(caps) and caps[0] in own_caps(units, rid)


def candidate_pairs(cands, areas, units) -> list:
    """(recipe_id, area name) for each candidate that passes the eligibility gate for the area."""
    return [(rid, a["area"]) for a in areas for rid in cands if eligible(rid, a, units)]


def area_coverage(rid, area, units) -> int:
    """How many of the area's capabilities the guide's own units cover (tie-break)."""
    return len(own_caps(units, rid) & set(area.get("capabilities") or ()))


def candidate_view(rid, units) -> dict:
    """What the judge reads for one guide."""
    us = [u for u in units if u["recipe_id"] == rid]

    def txt(kind):
        return "\n".join(u["text"] for u in us if u["kind"] == kind).strip()[:3000]
    return {"id": rid, "when_to_use": txt("when_to_use"), "when_not_to_use": txt("when_not_to_use"),
            "how_it_works": txt("how_it_works"),
            "steps": [u["heading"] for u in us if u["kind"] in ("step", "quickstart")]}


# Rubric (per recipe x capability area): criterion -> {level: points}; booleans use True.
# goal_match is scored separately (two quotes); the others need one quote from the guide.
GOAL_POINTS = {"strong": 45, "partial": 15}
RUBRIC = {"capability_fit": {"strong": 25, "partial": 10},
          "steps_reusable": {True: 20},
          "audience_fit": {True: 10}}
CONTRA_PENALTY = 50
# Without a strong goal match a pair can never pass SELECT_MIN.
NON_STRONG_CAP = SELECT_MIN


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


def section_text(uc, area) -> str:
    """What the judge is shown about one section's goal: use case name/summary + area."""
    caps = [capabilities.cap_label(k) for k in (area or {}).get("capabilities") or ()]
    return "\n".join([str(uc.get("name") or ""), str(uc.get("sanitized_desc") or ""),
                      str((area or {}).get("area") or ""), ", ".join(caps)])


def score_one(answer, view, section="") -> int:
    """0-100 from the judge's rubric answers. goal_match scores only when BOTH quotes are
    verbatim: section_goal in `section` (use case + area text) and recipe_goal in the guide's
    when-to-use. Other criteria need their quote verbatim in the guide text. An evidenced
    contraindication subtracts CONTRA_PENALTY. Without a strong, evidenced goal match the
    total is capped at NON_STRONG_CAP (never selectable)."""
    ev = answer.get("evidence") if isinstance(answer.get("evidence"), dict) else {}
    source = "\n".join([view["when_to_use"], view["when_not_to_use"], view["how_it_works"]]
                       + list(view["steps"]))
    goal = _level(answer.get("goal_match"))
    goal_ok = _evidenced(ev.get("section_goal"), section) and _evidenced(ev.get("recipe_goal"), view["when_to_use"])
    total = GOAL_POINTS.get(goal, 0) if goal_ok else 0
    for crit, pts in RUBRIC.items():
        if _evidenced(ev.get(crit), source):
            total += pts.get(_level(answer.get(crit)), 0)
    if _level(answer.get("contraindicated")) is True and _evidenced(ev.get("contraindicated"),
                                                                   view["when_not_to_use"]):
        total -= CONTRA_PENALTY
    if not (goal_ok and goal == "strong"):
        total = min(total, NON_STRONG_CAP)
    return max(0, min(100, total))


def score_all(judged, pairs, units, uc=None, areas=None) -> dict:
    """pairs: [(recipe_id, area)] -> {(recipe_id, area): score}; unanswered pairs score 0."""
    views = {rid: candidate_view(rid, units) for rid in {r for r, _ in pairs}}
    by_area = {a["area"]: a for a in areas or ()}
    out = {tuple(p): 0 for p in pairs}
    rows = judged.get("pairs") if isinstance(judged, dict) else None
    for a in rows if isinstance(rows, list) else []:
        key = (a.get("recipe_id"), a.get("area")) if isinstance(a, dict) else None
        if key in out:
            sec = section_text(uc or {}, by_area.get(key[1], {"area": key[1]}))
            out[key] = score_one(a, views[key[0]], sec)
    return out


STABLE_MIN_RUNS = 2


def aggregate(runs, pairs) -> dict:
    """Median score per pair across judge runs; a pair that is above SELECT_MIN in fewer than
    STABLE_MIN_RUNS runs is capped at SELECT_MIN (not selectable)."""
    out = {}
    for p in pairs:
        vals = sorted(r.get(p, 0) for r in runs)
        med = vals[(len(vals) - 1) // 2] if vals else 0
        if sum(v > SELECT_MIN for v in vals) < min(STABLE_MIN_RUNS, len(vals)):
            med = min(med, SELECT_MIN)
        out[p] = med
    return out


def select(scores, max_total=SELECT_MAX, tiebreak=None) -> list:
    """{(recipe_id, area): score} -> [(recipe_id, area, score)]: above SELECT_MIN, highest
    first; at most one guide per area, each guide used once, at most max_total. Ties break by
    tiebreak[pair] (higher first; e.g. (area coverage, prefilter score)), then by id."""
    tb = tiebreak or {}

    def key(kv):
        return (-kv[1], tuple(-x for x in tb.get(kv[0], ())), kv[0])
    out, areas, rids = [], set(), set()
    for (rid, area), s in sorted(scores.items(), key=key):
        if s > SELECT_MIN and area not in areas and rid not in rids and len(out) < max_total:
            out.append((rid, area, s))
            areas.add(area)
            rids.add(rid)
    return out


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


def _unit_caps(u, rcaps):
    """A unit's own capabilities (heading + SQL); a unit naming none inherits the guide's."""
    own = _caps_in(f"{u['heading']}\n{u['sql']}")
    return own or [c for c in u["capabilities"] if c in rcaps]


def _pack_recipe(rid, units, area_caps, allow):
    """Entries from units of `rid` that map to `area_caps` (pack keys are only area capabilities)."""
    req = list(area_caps or ())
    out, used = [], 0
    rcaps = {c for u in units if u["recipe_id"] == rid for c in u["capabilities"]}
    us = [u for u in units if u["recipe_id"] == rid and u["kind"] in PACK_KINDS and u["sql"]
          and set(_unit_caps(u, rcaps)) & set(req)]
    for u in us:
        cap = next(c for c in _unit_caps(u, rcaps) if c in req)
        sql = neutral_sql(u["sql"])
        if not sql or used + len(sql) > PACK_CHARS:
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


def _sel(selected, required_caps):
    """Normalize selections to (recipe_id, area_caps): (rid, caps[, score]) or a bare rid
    (all required capabilities)."""
    for s in selected:
        if isinstance(s, str):
            yield s, list(required_caps or ())
        else:
            yield s[0], list(s[1])


def packs_by_recipe(selected, units, required_caps=(), allow=None) -> dict:
    allow = _allow() if allow is None else {u.rstrip("/") for u in allow}
    return {rid: [e for _, e in _pack_recipe(rid, units, caps, allow)]
            for rid, caps in _sel(selected, required_caps)}


def integration_pack(selected, units, required_caps=(), allow=None) -> dict:
    """capability -> [grounding sql_snippet entries {title, sql, source_url}]; each selected
    guide contributes only to its own area's capabilities."""
    allow = _allow() if allow is None else {u.rstrip("/") for u in allow}
    out = {}
    for rid, caps in _sel(selected, required_caps):
        for cap, e in _pack_recipe(rid, units, caps, allow):
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
