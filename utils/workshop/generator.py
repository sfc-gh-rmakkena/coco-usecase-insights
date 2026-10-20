"""Per-use-case workshop generation. Output dict has identical keys on every path."""
import json
import re
from concurrent.futures import ThreadPoolExecutor

from . import assets, cache, prompts
from .compliance import find_violations, scrub
from .context import fetch_uc_context
from .gate import fetch_a360_context, is_listed, load_listed_names

MODEL = "claude-sonnet-4-5"
MAX_WORKERS = 32
_FENCE = re.compile(r"^```(?:json)?|```$", re.M)


def recipe_band(conf: int) -> str:
    return "full" if conf > 80 else ("reference" if conf >= 50 else "none")


def _parse(raw: str) -> dict:
    s = _FENCE.sub("", raw or "").strip()
    start, end = s.find("{"), s.rfind("}")
    return json.loads(s[start:end + 1]) if start >= 0 else {}


def _clean_sql(sql):
    # SQL is not sentence-scrubbed (would mangle it), but is blanked if it leaks.
    if not isinstance(sql, str):
        return ""
    return "" if find_violations(sql) else sql


def _clean(value, allow):
    if isinstance(value, str):
        return scrub(value, allow)
    if isinstance(value, list):
        return [v for v in (_clean(x, allow) for x in value) if v not in ("", [], {})]
    if isinstance(value, dict):
        return {k: _clean_sql(v) if k == "sql" else _clean(v, allow) for k, v in value.items()}
    return value


def _to_conf(v) -> int:
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return 0


def _call_json(llm, prompt, validate):
    """One call + one regeneration if the result fails validation or still leaks."""
    for _ in range(2):
        try:
            data = _parse(llm(prompt))
        except Exception:
            continue
        if isinstance(data, dict) and validate(data) and not find_violations(json.dumps(data)):
            return data
    return None


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


def build_one(uc, partner, account_signals, private_context, llm) -> dict:
    allow = assets.link_allowlist()
    s1 = _call_json(llm, prompts.session1_prompt(uc, partner, account_signals),
                    lambda d: len(d.get("prompts", [])) == 3)
    session1 = _clean(s1["prompts"], allow) if s1 else _fallback_session1(uc)

    rm = _call_json(llm, prompts.recipe_match_prompt(uc),
                    lambda d: assets.recipe_meta(d.get("recipe_id", "")) != {})
    recipe = {"band": "none"}
    if rm:
        conf = _to_conf(rm.get("confidence", 0))
        band = recipe_band(conf)
        if band != "none":
            meta = assets.recipe_meta(rm["recipe_id"])
            recipe = {"band": band, "id": meta["id"], "title": meta["title"], "confidence": conf,
                      "rationale": scrub(rm.get("rationale", ""), allow),
                      "body": assets.recipe_body(meta["id"]) if band == "full" else ""}

    plan_recipe = {k: recipe[k] for k in ("id", "title") if k in recipe} or None
    s2 = _call_json(llm, prompts.session2_prompt(uc, partner, private_context, plan_recipe),
                    lambda d: bool(d.get("steps")))
    plan = _clean(s2, allow) if s2 else {}
    brief = plan.get("problem_statement") or scrub(uc.get("sanitized_desc", ""), allow)
    return {"uc_id": uc["uc_id"], "account": uc["account"], "name": uc["name"], "skills": uc["skills"],
            "brief": brief, "session1": session1, "session2": {"recipe": recipe, "plan": plan}}


def generate_workshops(conn, rows: list, partner: str, complete_fn, call_log=None, log_wrap=None) -> list:
    """rows: gap-table rows already filtered to not-deployed. complete_fn(conn, model, prompt) -> str.
    log_wrap(call_log, label, use_case, fn, *args) is the page's _logged_rest_call (optional)."""
    if not rows:
        return []
    cache.ensure_tables(conn)
    listed = load_listed_names(conn)
    listed_accounts = [r["account"] for r in rows if is_listed(r["account"], listed)]
    a360 = fetch_a360_context(conn, listed_accounts)
    sfdc = fetch_uc_context(conn, [r["uc_id"] for r in rows])
    version = assets.asset_version()

    jobs = []
    for r in rows:
        listed_flag = is_listed(r["account"], listed)
        signals = a360.get((r["account"] or "").upper()) if listed_flag else None
        ctx = sfdc.get(r["uc_id"], {})
        key = cache.compute_hash({"uc": {k: r.get(k) for k in ("uc_id", "name", "account", "skills", "sanitized_desc")},
                                  "partner": partner, "signals": signals, "ctx": ctx}, version)
        jobs.append((r, signals, ctx, key, "listed" if listed_flag else "unlisted"))

    hits = cache.lookup(conn, [j[3] for j in jobs])

    def _run(job):
        r, signals, ctx, key, _ = job
        if key in hits:
            return hits[key]

        def llm(prompt):
            if log_wrap and call_log is not None:
                return log_wrap(call_log, "workshop", r["name"], complete_fn, conn, MODEL, prompt)
            return complete_fn(conn, MODEL, prompt)
        return build_one(r, partner, signals, ctx, llm)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(_run, jobs))

    cache.insert(conn, [(j[3], partner, j[0]["uc_id"], res) for j, res in zip(jobs, results) if j[3] not in hits],
                 asset_version=version)
    cache.audit(conn, [(partner, j[0]["uc_id"], j[4], j[3] in hits) for j in jobs])
    return results
