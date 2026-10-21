"""Per-use-case workshop generation. Output dict has identical keys on every path."""
import json
import re
from concurrent.futures import ThreadPoolExecutor

from . import assets, cache, capabilities, diagram, prompts
from .compliance import classify_violations, find_violations, scrub
from .context import fetch_uc_context
from .deny import private_deny_terms
from .gate import fetch_a360_context, is_listed, load_listed_names
from .verify import verify_plan

MODEL = "claude-sonnet-4-5"
MAX_WORKERS = 16
_FENCE = re.compile(r"^```(?:json)?|```$", re.M)


def recipe_band(conf: int) -> str:
    return "full" if conf > 80 else ("reference" if conf >= 50 else "none")


def _parse(raw: str) -> dict:
    s = _FENCE.sub("", raw or "").strip()
    dec = json.JSONDecoder()
    i = s.find("{")
    while i >= 0:
        try:
            obj, _ = dec.raw_decode(s, i)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        i = s.find("{", i + 1)
    return {}


_LINK = {"title": "", "url": ""}
# Field -> default for one row of each list-of-objects field (stable shape on every path).
_ROWS = {
    "executive_summary": {"topic": "", "previous_state": "", "solution": "", "status": ""},
    "component_status": {"component": "", "status": "", "details": "", "source_url": ""},
    "sections": {"title": "", "challenge": "", "explanation": "", "coco_prompt": "", "sql": "",
                 "source_url": "", "notes": []},
    "coco_skills": {"skill": "", "what_it_does": "", "steps": ""},
    "before_after": {"task": "", "without": "", "with": ""},
    "decision_matrix": {"topic": "", "verdict": "", "production_ready": "", "action": ""},
}
# architecture_flow is legacy (old cached payloads); new plans carry the structured `architecture`
# and architecture_layers is derived from it.
PLAN_DEFAULT = {"problem_statement": "", "executive_summary": [], "decision_criteria_alignment": [],
                "architecture": {"sources": [], "layers": [], "consumers": []},
                "architecture_layers": [], "architecture_flow": "", "component_status": [], "sections": [],
                "coco_skills": [], "before_after": [], "decision_matrix": [], "next_steps": [],
                "resources": {"quickstarts": [], "docs": [], "github": []},
                "hands_on": {"intro": "", "sql": "", "source_url": ""}}
_RES_FIELDS = {"quickstarts": ("title", "url"), "docs": ("title", "url", "status"),
               "github": ("title", "url", "description")}
_LAYER_NAMES = ("Ingestion", "Bronze", "Silver", "Gold", "Semantic", "Consumption", "Sharing", "Governance")
RECIPE_DEFAULT = {"band": "none", "id": "", "title": "", "confidence": 0, "rationale": "", "body": ""}
MIN_SQL_SECTIONS = 3
# Identifiers that do not exist in Snowflake but models invent; scrubbed from prose too.
INVENTED_TERMS = ["CORTEX_AGENT_USAGE_HISTORY", "DATA_AGENT_RUN", "INVOKER_ROLE"]
# Constructs the model has invented in the past; SQL containing them is dropped.
_INVENTED = [re.compile(p, re.I | re.S) for p in (
    r"\bDATA_AGENT_RUN\b", r"\bINVOKER_ROLE\b", r"\bCORTEX_AGENT_USAGE_HISTORY\b",
    r"\bSCHEDULE\s*=\s*'(?!\s*USING\s+CRON)[^']*\*",  # cron expression without USING CRON
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?AGENT\b(?:(?!\$\$).)*?\b(?:COMPUTE_POOL|MODEL|TOOLS)\s*=")]


def _str(v):
    return v if isinstance(v, str) else ""


def _strs(v):
    return [x for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []


def _layer_name(name):
    n = _str(name).strip()
    return next((c for c in _LAYER_NAMES if c.lower() in n.lower()), n)


def _shape_arch(arch):
    arch = arch if isinstance(arch, dict) else {}
    layers = [{"name": _layer_name(l.get("name")), "capability": _str(l.get("capability")),
               "detail": _str(l.get("detail"))}
              for l in (arch.get("layers") if isinstance(arch.get("layers"), list) else []) if isinstance(l, dict)]
    return {"sources": _strs(arch.get("sources")), "layers": [l for l in layers if l["name"] or l["capability"]],
            "consumers": _strs(arch.get("consumers"))}


def _shape(plan) -> dict:
    """Coerce a (cleaned) plan to PLAN_DEFAULT's shape: every key present, rows fully keyed."""
    plan = plan if isinstance(plan, dict) else {}
    out = {"problem_statement": _str(plan.get("problem_statement")),
           "architecture_flow": _str(plan.get("architecture_flow"))}
    for k in ("decision_criteria_alignment", "architecture_layers", "next_steps"):
        out[k] = _strs(plan.get(k))
    for k, row in _ROWS.items():
        rows = [r for r in plan.get(k) or [] if isinstance(r, dict)] if isinstance(plan.get(k), list) else []
        out[k] = [{f: (_strs(r.get(f)) if isinstance(d, list) else _str(r.get(f))) for f, d in row.items()}
                  for r in rows]
    res = plan.get("resources") if isinstance(plan.get("resources"), dict) else {}
    out["resources"] = {k: [{f: _str(d.get(f)) for f in fields}
                            for d in (res.get(k) if isinstance(res.get(k), list) else []) if isinstance(d, dict)]
                        for k, fields in _RES_FIELDS.items()}
    out["architecture"] = _shape_arch(plan.get("architecture"))
    if out["architecture"]["layers"]:
        out["architecture_layers"] = diagram.layer_bullets(out["architecture"])
    ho = plan.get("hands_on") if isinstance(plan.get("hands_on"), dict) else {}
    out["hands_on"] = {k: _str(ho.get(k)) for k in ("intro", "sql", "source_url")}
    return out


def _clean_sql(sql, deny=()):
    # SQL is not sentence-scrubbed (would mangle it), but is blanked if it leaks.
    if not isinstance(sql, str):
        return ""
    return "" if find_violations(sql, deny, sql=True) else sql


def _clean_flow(text, deny=()):
    """Diagrams keep their spacing; lines that leak are dropped."""
    if not isinstance(text, str):
        return ""
    return "\n".join(l.rstrip() for l in text.split("\n") if not find_violations(l, deny)).strip("\n")


def _clean(value, allow, deny=()):
    if isinstance(value, str):
        return scrub(value, allow, deny)
    if isinstance(value, list):
        return [v for v in (_clean(x, allow, deny) for x in value) if v not in ("", [], {})]
    if isinstance(value, dict):
        return {k: _clean_sql(v, deny) if k == "sql" else _clean_flow(v, deny) if k == "architecture_flow"
                else _clean(v, allow, deny) for k, v in value.items()}
    return value


def _ground_sections(plan, allow):
    """SQL must cite an allowed source URL and use no known-invented construct."""
    for s in plan["sections"]:
        url = s["source_url"].rstrip("/")
        if url not in {u.rstrip("/") for u in allow}:
            s["source_url"] = ""
        if s["sql"] and (not s["source_url"] or any(p.search(s["sql"]) for p in _INVENTED)):
            s["sql"] = ""
    ok = {u.rstrip("/") for u in allow}
    for r in plan["component_status"]:
        if r["source_url"].rstrip("/") not in ok:
            r["source_url"] = ""
    ho = plan["hands_on"]
    if ho["source_url"].rstrip("/") not in ok:
        ho["source_url"] = ""
    if ho["sql"] and (not ho["source_url"] or any(p.search(ho["sql"]) for p in _INVENTED)):
        ho["sql"] = ""
    plan["resources"] = {k: [d for d in v if d["url"].startswith("https://") and d["url"].rstrip("/") in ok]
                         for k, v in plan["resources"].items()}
    for d in plan["resources"]["docs"]:
        d["status"] = d["status"] or _doc_status(d["url"])
    for d in plan["resources"]["github"]:
        d["description"] = d["description"] or "Companion repository"
    return plan


def _doc_status(url):
    u = url.rstrip("/")
    for v in capabilities.grounding().values():
        if any(d["url"].rstrip("/") == u for d in v.get("docs", [])):
            return capabilities.status_from_note(v.get("status_note"))
    return "See page"


def _fill_architecture(plan, required) -> bool:
    """Inject a layer / component row for each required capability the model left out (deterministic,
    from capabilities.CAPS + grounding). Returns True if anything was added."""
    g, arch, added = capabilities.grounding(), plan["architecture"], False
    if not arch["layers"] and plan["architecture_flow"]:
        return False  # legacy free-text diagram: leave as-is
    for k in required:
        note = g.get(k, {}).get("status_note", "")
        if not any(capabilities.cap_matches(k, l["capability"]) for l in arch["layers"]):
            arch["layers"].append({"name": capabilities.cap_layer(k), "capability": capabilities.cap_label(k),
                                   "detail": ""})
            added = True
        if not any(capabilities.cap_matches(k, r["component"]) for r in plan["component_status"]):
            docs = g.get(k, {}).get("docs") or [{}]
            plan["component_status"].append({"component": capabilities.cap_label(k),
                                             "status": capabilities.status_from_note(note),
                                             "details": note, "source_url": docs[0].get("url", "")})
            added = True
    if added:
        arch["layers"].sort(key=lambda l: _LAYER_NAMES.index(l["name"]) if l["name"] in _LAYER_NAMES else 4.5)
    if arch["layers"]:
        plan["architecture_layers"] = diagram.layer_bullets(arch)
    return added


def _finish_plan(s2, allow, deny, required):
    """Clean, shape, ground and fill one raw response. Returns (plan, arch_filled)."""
    plan = _ground_sections(_shape(_clean(s2, allow, deny) if s2 else {}), allow)
    filled = _fill_architecture(plan, required) if s2 else False
    return plan, filled


def _sql_sections(plan) -> int:
    return sum(1 for s in plan.get("sections") or [] if isinstance(s, dict) and str(s.get("sql") or "").strip())


def _valid_s2(d):
    secs = d.get("sections")
    return (isinstance(secs, list) and bool(secs)
            and sum(1 for s in secs if isinstance(s, dict) and str(s.get("sql") or "").strip()
                    and str(s.get("source_url") or "").startswith("https://")) >= MIN_SQL_SECTIONS)


def _to_conf(v) -> int:
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return 0


def _add(reasons, code):
    if code not in reasons:
        reasons.append(code)


# Scrub-only categories: cleaned out of the text but never a reason to regenerate.
_SCRUB_ONLY = {"credits"}


def _call_json(llm, prompt, validate, deny=(), tag="", strict=False):
    """One call + one regeneration on parse/shape failure (and, if strict, on violations
    outside _SCRUB_ONLY). Returns (data_or_None, reasons, candidate): candidate is the last
    shape-valid response, for scrub-and-accept. Reasons are short codes, never LLM text."""
    reasons, candidate = [], None
    pre = f"{tag}:" if tag else ""
    for _ in range(2):
        try:
            raw = llm(prompt)
        except Exception as e:
            _add(reasons, f"{pre}llm_error:{type(e).__name__}")
            continue
        data = _parse(raw)
        if not data:
            tail = _FENCE.sub("", raw or "").strip()
            _add(reasons, f"{pre}parse_empty" if tail.endswith("}") else f"{pre}truncated")
            continue
        if not validate(data):
            _add(reasons, f"{pre}invalid_shape")
            continue
        candidate = data
        if strict:
            cats = [c for c in classify_violations(json.dumps(data), deny) if c not in _SCRUB_ONLY]
            if cats:
                for c in cats:
                    _add(reasons, f"{pre}violation:{c}")
                continue
        return data, reasons, candidate
    return None, reasons, candidate


def _note_scrubbed(reasons, data, deny, tag):
    """Informational: categories that the scrubber removed (codes only, no text)."""
    for c in classify_violations(json.dumps(data), deny):
        _add(reasons, f"{tag}:scrubbed:{c}")


def _exempt(deny, uc, partner=""):
    """Terms in the use case name are public for it; so are the account and partner names themselves.
    (The judge summary is NOT a public header: it can carry confidential detail.)"""
    name = uc.get("name") or ""
    public = f"{uc.get('account') or ''} {partner or ''}".lower()
    return [t for t in (deny or ()) if t.strip()
            and not re.search(r"(?<!\w)" + re.escape(t.strip()) + r"(?!\w)", name, re.I)
            and t.strip().lower() not in public]


def _brief(plan, uc, allow, deny):
    if plan.get("problem_statement"):
        return plan["problem_statement"]
    fb = scrub(uc.get("sanitized_desc", ""), allow, deny)
    if not fb or find_violations(fb, deny):
        return f"{uc['name']} for {uc['account']}"
    return fb


def _fallback_session1(uc):
    skill = (uc["skills"] or ["cortex-code"])[0]
    return [
        {"title": "Discover the data", "purpose": "Find the objects this use case needs.",
         "prompt": f"List the databases, schemas and tables relevant to: {uc['name']}. Summarize what each contains."},
        {"title": f"Build with {skill}", "purpose": "Create a first working version together.",
         "prompt": f"Using the {skill} skill, build a first version of {uc['name']} on the tables identified above."},
        {"title": "Extend and operationalize", "purpose": "Plan the path to production.",
         "prompt": f"Review what we built for {uc['name']} and propose tests, scheduling and access controls."},
    ]


def _valid_s1(d):
    p = d.get("prompts")
    return (isinstance(p, list) and len(p) == 3
            and all(isinstance(x, dict) and isinstance(x.get("prompt"), str) and x["prompt"].strip() for x in p))


def build_one(uc, partner, account_signals, private_context, llm, deny=()) -> dict:
    """Result carries "_degraded": True when Session 1 fell back or the Session 2 plan failed."""
    allow = assets.link_allowlist()
    deny = _exempt(list(deny or ()) + private_deny_terms(private_context, uc.get("account", "")), uc, partner)
    deny += [t for t in INVENTED_TERMS if t not in deny]
    s1, reasons, cand = _call_json(llm, prompts.session1_prompt(uc, partner, account_signals, deny),
                                   _valid_s1, deny, "s1", strict=True)
    src = s1 or cand
    session1 = _clean(src["prompts"], allow, deny) if src else None
    if src:
        _note_scrubbed(reasons, src, deny, "s1")
    if not (session1 and len(session1) == 3
            and all(isinstance(x, dict) and str(x.get("prompt", "")).strip() for x in session1)):
        if src:
            _add(reasons, "s1:clean_emptied")
        session1 = None
    degraded = session1 is None
    if session1 is None:
        session1 = _fallback_session1(uc)

    rm, why, _ = _call_json(llm, prompts.recipe_match_prompt(uc),
                            lambda d: assets.recipe_meta(d.get("recipe_id", "")) != {}, deny, "recipe")
    reasons += [r for r in why if r not in reasons]
    recipe = dict(RECIPE_DEFAULT)
    if rm:
        _note_scrubbed(reasons, rm, deny, "recipe")
        conf = _to_conf(rm.get("confidence", 0))
        band = recipe_band(conf)
        if band != "none":
            meta = assets.recipe_meta(rm["recipe_id"])
            recipe = {"band": band, "id": meta["id"], "title": meta["title"], "confidence": conf,
                      "rationale": scrub(str(rm.get("rationale", "")), allow, deny),
                      "body": assets.recipe_body(meta["id"]) if band == "full" else ""}

    # Only a full-band recipe steers the plan; a reference match is shown as a one-liner only.
    plan_recipe = {k: recipe[k] for k in ("id", "title")} if recipe["band"] == "full" else None
    base = prompts.session2_prompt(uc, partner, private_context, plan_recipe, deny)
    s2, why, _ = _call_json(llm, base, _valid_s2, deny, "s2")
    if s2:
        _note_scrubbed(why, s2, deny, "s2")
    reasons += [r for r in why if r not in reasons]
    required = prompts.primary_capabilities(uc, private_context)
    plan, filled = _finish_plan(s2, allow, deny, required)
    if s2:
        fails = verify_plan(plan, required, allow, deny)
        if fails:
            # One repair pass: failure codes only (no confidential text) + the already-cleaned plan.
            s2b, why, _ = _call_json(llm, prompts.session2_repair_prompt(base, fails, plan), _valid_s2, deny, "s2r")
            reasons += [r for r in why if r not in reasons]
            if s2b:
                plan_b, filled_b = _finish_plan(s2b, allow, deny, required)
                fails_b = verify_plan(plan_b, required, allow, deny)
                if len(fails_b) < len(fails):
                    plan, filled, fails = plan_b, filled_b, fails_b
                    _note_scrubbed(reasons, s2b, deny, "s2r")
        if filled:
            _add(reasons, "s2:arch_filled")
        for f in fails:
            _add(reasons, f"s2:verify:{f}")
    if s2 and _sql_sections(plan) < MIN_SQL_SECTIONS:
        _add(reasons, "s2:clean_emptied")
    degraded = degraded or _sql_sections(plan) < MIN_SQL_SECTIONS
    brief = _brief(plan, uc, allow, deny)
    return {"_degraded": degraded, "_degraded_reasons": reasons, "uc_id": uc["uc_id"], "account": uc["account"], "name": uc["name"], "skills": uc["skills"],
            "brief": brief, "session1": session1, "session2": {"recipe": recipe, "plan": plan}}


def _safe_read(label, fn, default, diagnostics):
    """Run a context read; on failure return `default` and record only the exception type."""
    try:
        return fn()
    except Exception as e:
        if diagnostics is not None:
            diagnostics.append(f"{label}: {type(e).__name__}")
        return default


def generate_workshops(conn, rows: list, partner: str, complete_fn, call_log=None, log_wrap=None,
                       data_conn=None, diagnostics=None) -> list:
    """rows: gap-table rows already filtered to not-deployed. complete_fn(conn, model, prompt) -> str.
    log_wrap(call_log, label, use_case, fn, *args) is the page's _logged_rest_call (optional).
    data_conn (default conn) serves the account-context reads (caller's rights in DEV); conn (owner)
    serves cache/audit and LLM calls. diagnostics, if given, collects non-sensitive read-failure notes."""
    if not rows:
        return []
    data_conn = data_conn or conn
    _safe_read("cache_tables", lambda: cache.ensure_tables(conn), None, diagnostics)
    listed = _safe_read("listed", lambda: load_listed_names(data_conn), frozenset(), diagnostics)
    listed_accounts = [r["account"] for r in rows if is_listed(r["account"], listed)]
    a360 = _safe_read("a360", lambda: fetch_a360_context(data_conn, listed_accounts), {}, diagnostics)
    sfdc = _safe_read("context", lambda: fetch_uc_context(data_conn, [r["uc_id"] for r in rows]), {}, diagnostics)
    version = assets.asset_version()

    jobs = []
    for r in rows:
        listed_flag = is_listed(r["account"], listed)
        signals = a360.get((r["account"] or "").upper()) if listed_flag else None
        ctx = sfdc.get(r["uc_id"]) or {"llm": {}, "deny": []}
        key = cache.compute_hash({"uc": {k: r.get(k) for k in ("uc_id", "name", "account", "skills", "sanitized_desc")},
                                  "partner": partner, "signals": signals, "ctx": ctx}, version)
        jobs.append((r, signals, ctx, key, "listed" if listed_flag else "unlisted"))

    hits = _safe_read("cache_lookup", lambda: cache.lookup(conn, [j[3] for j in jobs]), {}, diagnostics) or {}

    def _run(job):
        r, signals, ctx, key, _ = job
        if key in hits:
            return hits[key]

        def llm(prompt):
            if log_wrap and call_log is not None:
                return log_wrap(call_log, "workshop", r["name"], complete_fn, conn, MODEL, prompt)
            return complete_fn(conn, MODEL, prompt)
        return build_one(r, partner, signals, ctx["llm"], llm, deny=ctx["deny"])

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(_run, jobs))

    # Cached payloads never carry these keys; pop so they never reach the page.
    degraded = [bool(res.pop("_degraded", False)) for res in results]
    why = [res.pop("_degraded_reasons", None) or [] for res in results]
    # Persistence is best-effort: a failed write must never lose generated results.
    _safe_read("cache_insert", lambda: cache.insert(
        conn, [(j[3], partner, j[0]["uc_id"], res) for j, res, bad in zip(jobs, results, degraded)
               if j[3] not in hits and not bad], asset_version=version), None, diagnostics)
    _safe_read("audit", lambda: cache.audit(
        conn, [(partner, j[0]["uc_id"], j[4], j[3] in hits, ";".join(w))
               for j, w in zip(jobs, why)]), None, diagnostics)
    if diagnostics is not None:
        diagnostics.append(f"degraded: {sum(degraded)}/{len(results)}")
    return results
