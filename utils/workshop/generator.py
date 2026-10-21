"""Per-use-case workshop generation. Output dict has identical keys on every path."""
import json
import re
from concurrent.futures import ThreadPoolExecutor

from . import assets, cache, prompts
from .compliance import classify_violations, find_violations, scrub
from .context import fetch_uc_context
from .gate import fetch_a360_context, is_listed, load_listed_names

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


PLAN_DEFAULT = {"problem_statement": "", "architecture": [], "steps": [], "coco_prompts": [],
                "considerations": [], "docs": []}
RECIPE_DEFAULT = {"band": "none", "id": "", "title": "", "confidence": 0, "rationale": "", "body": ""}


def _clean_sql(sql, deny=()):
    # SQL is not sentence-scrubbed (would mangle it), but is blanked if it leaks.
    if not isinstance(sql, str):
        return ""
    return "" if find_violations(sql, deny) else sql


def _clean(value, allow, deny=()):
    if isinstance(value, str):
        return scrub(value, allow, deny)
    if isinstance(value, list):
        return [v for v in (_clean(x, allow, deny) for x in value) if v not in ("", [], {})]
    if isinstance(value, dict):
        return {k: _clean_sql(v, deny) if k == "sql" else _clean(v, allow, deny) for k, v in value.items()}
    return value


def _to_conf(v) -> int:
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return 0


def _add(reasons, code):
    if code not in reasons:
        reasons.append(code)


def _call_json(llm, prompt, validate, deny=(), tag=""):
    """One call + one regeneration if the result fails validation or still leaks.
    Returns (data_or_None, reasons): short machine codes only, never LLM text or matches."""
    reasons = []
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
        cats = classify_violations(json.dumps(data), deny)
        if cats:
            for c in cats:
                _add(reasons, f"{pre}violation:{c}")
            continue
        return data, reasons
    return None, reasons


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
    s1, reasons = _call_json(llm, prompts.session1_prompt(uc, partner, account_signals), _valid_s1, deny, "s1")
    session1 = _clean(s1["prompts"], allow, deny) if s1 else None
    if not session1 or len(session1) != 3:
        if s1:
            _add(reasons, "s1:clean_emptied")
        session1 = None
    degraded = session1 is None
    if session1 is None:
        session1 = _fallback_session1(uc)

    rm, why = _call_json(llm, prompts.recipe_match_prompt(uc),
                         lambda d: assets.recipe_meta(d.get("recipe_id", "")) != {}, deny, "recipe")
    reasons += [r for r in why if r not in reasons]
    recipe = dict(RECIPE_DEFAULT)
    if rm:
        conf = _to_conf(rm.get("confidence", 0))
        band = recipe_band(conf)
        if band != "none":
            meta = assets.recipe_meta(rm["recipe_id"])
            recipe = {"band": band, "id": meta["id"], "title": meta["title"], "confidence": conf,
                      "rationale": scrub(rm.get("rationale", ""), allow, deny),
                      "body": assets.recipe_body(meta["id"]) if band == "full" else ""}

    plan_recipe = {k: recipe[k] for k in ("id", "title")} if recipe["id"] else None
    s2, why = _call_json(llm, prompts.session2_prompt(uc, partner, private_context, plan_recipe),
                         lambda d: isinstance(d.get("steps"), list) and bool(d["steps"]), deny, "s2")
    reasons += [r for r in why if r not in reasons]
    cleaned = _clean(s2, allow, deny) if s2 else {}
    plan = {**PLAN_DEFAULT, **{k: v for k, v in cleaned.items() if k in PLAN_DEFAULT}}
    if s2 and not plan["steps"]:
        _add(reasons, "s2:clean_emptied")
    degraded = degraded or not plan["steps"]
    brief = plan.get("problem_statement") or scrub(uc.get("sanitized_desc", ""), allow, deny)
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
