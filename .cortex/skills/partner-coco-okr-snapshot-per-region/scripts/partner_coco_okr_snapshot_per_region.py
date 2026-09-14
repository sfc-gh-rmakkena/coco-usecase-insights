"""Standalone local script (NOT a Streamlit page) that runs the full REST-
based LLM-as-judge grounding pipeline -- identical logic to Approach 2 in
app_pages/pse_email_hybrid_rest.py, no shortcuts -- across every non-CoCo-
attached use case in a given theater / industry sub-region for the FY27 Q3
OKR window (2026-08-01 to 2026-10-31), restricted to partners in scope for
that OKR (the same MANAGED_PARTNERS set executive_email.py builds), and
writes a standalone HTML report to disk, grouped by partner.

This script ships inside the `partner-coco-okr-snapshot-per-region` skill
(.cortex/skills/partner-coco-okr-snapshot-per-region/scripts/) but only runs
against the coco-usecase-insights repo it targets -- it imports utils.* from
that repo's root, so it locates the repo root at runtime by walking up from
its own location looking for a utils/queries.py marker (see
_find_repo_root() below), rather than assuming a fixed relative depth.

Run with:
    .venv/bin/python <this_script> --theater USMajors --subregion MFG
    .venv/bin/python <this_script> --theater USMajors --subregion RCG

Why this is a plain script and not `streamlit run` (the convention used by
scripts/eval_*.py): this repo's checked-in .streamlit/secrets.toml hardcodes
ENV="prod" (which utils.config.get_env() checks BEFORE any OS env var
override) and authenticates as a different Snowflake user (NIRASHAH) via
external-browser SSO -- wrong schema, wrong identity for this task. Instead
this script connects directly via snowflake-connector-python using
authenticator="externalbrowser" (SSO, matching the identity used for this
project's `snow streamlit deploy` commands -- resolves to role
SALES_ENGINEER + warehouse COCO_PARTNER_ADOPTION_WH, the same execution
identity the deployed DEV app uses), and wraps that raw connection in a
minimal shim so the existing utils/queries.py, utils/judge_cache.py, and
utils/cortex_rest_helpers.py -- all written against Streamlit's
SnowflakeConnection wrapper -- work completely unchanged.

_JUDGE_PIPELINE_TAG/_JUDGE_PIPELINE_VERSION are kept identical to
pse_email_hybrid_rest.py's so this run's persistent-cache lookups/inserts
share the same COCO_PSE_JUDGE_CACHE table as the deployed app.
"""
import argparse
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """Walk up from this script's location looking for the
    coco-usecase-insights repo root, identified by a utils/queries.py
    marker file. Needed because this script lives inside a skill directory
    (.cortex/skills/<name>/scripts/) rather than at a fixed depth under the
    repo root, so a hardcoded parent.parent won't reliably resolve."""
    for candidate in [start] + list(start.parents):
        if (candidate / "utils" / "queries.py").exists():
            return candidate
    raise RuntimeError(
        f"Could not locate the coco-usecase-insights repo root (no utils/queries.py "
        f"found in any parent of {start}). This script must run from within that repo."
    )


REPO_ROOT = _find_repo_root(Path(__file__).resolve())

# Must be set before importing any utils.* module -- utils.config.get_schema()
# is evaluated at import time in both utils/queries.py and utils/judge_cache.py,
# and this connection's default schema (TEMP.PLAKHANPAL) doesn't contain "DEV",
# so auto-detection would otherwise silently resolve to PROD.
os.environ["APP_ENV"] = "dev"

sys.path.insert(0, str(REPO_ROOT))

import snowflake.connector  # noqa: E402

from utils import PARTNER_RENAME_MAP, apply_coco_final  # noqa: E402
from utils.queries import get_bulk_confidence_scores, get_account_coco_credits  # noqa: E402
from utils.config import get_schema  # noqa: E402
from utils.cortex_rest_helpers import cortex_complete_rest as cortex_complete  # noqa: E402
from utils import judge_cache  # noqa: E402
from utils.coco_skill_map_v2 import (  # noqa: E402
    map_coco_skills_explained, theater_label as _theater_label, h as _h,
    MANAGED_PARTNERS,
    build_ai_skill_prompt, parse_ai_skill_response,
    detect_aim_source, apply_aim_override, rank_skills_by_gpa,
    AIM_SKILL_NAME, is_catalog_skill,
    build_grounding_judge_prompt, parse_grounding_judge_response,
)

Q_START = "2026-08-01"
Q_END = "2026-10-31"
CONFIDENCE_BANDS = ["High"]

REPORTS_DIR = REPO_ROOT / "output" / "reports"

# ── Same judge pipeline tag/version as app_pages/pse_email_hybrid_rest.py --
# keep in sync so this run's persistent-cache lookups/inserts share the same
# COCO_PSE_JUDGE_CACHE table as the deployed app. ──────────────────────────
_JUDGE_PIPELINE_TAG = "rest"
_JUDGE_PIPELINE_VERSION = 7
_JUDGE_MAX_WORKERS = 32
_JUDGE_FIRSTPASS_MAX_TOKENS = 2200
_JUDGE_VERDICT_MAX_TOKENS = 900
_COVERAGE_FLOOR_SENTINEL = "__COVERAGE_FLOOR__"
_COVERAGE_FLOOR_FALLBACK = "Best-supported CoCo skill match identified for this use case based on its technical profile."

_GPA_SCORE_GOOD, _GPA_SCORE_WARN = 0.7, 0.4
_GPA_SCORE_COLORS = {"good": "#16a34a", "warn": "#d97706", "bad": "#dc2626"}
_STAGE_COLORS = {
    "POC": ("#fef3c7", "#92400e"),
    "Deployed": ("#dcfce7", "#166534"),
    "Implementation": ("#dbeafe", "#1e40af"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Connection shim -- a minimal drop-in so utils/queries.py, utils/judge_cache.py,
# and utils/cortex_rest_helpers.py (all written against Streamlit's
# SnowflakeConnection wrapper) work unchanged against a plain
# snowflake-connector-python connection in this standalone script.
# ─────────────────────────────────────────────────────────────────────────────
class _ConnShim:
    def __init__(self, raw):
        self._instance = raw  # used by cortex_rest_helpers.cortex_complete_rest
        self._raw = raw

    def cursor(self):
        return self._raw.cursor()

    def query(self, sql, ttl=0):
        cur = self._raw.cursor()
        try:
            cur.execute(sql)
            try:
                return cur.fetch_pandas_all()
            except snowflake.connector.errors.NotSupportedError:
                # INSERT/UPDATE/DELETE/CREATE statements have no result set to
                # fetch -- judge_cache.batch_insert() calls conn.query() for its
                # INSERT and ignores the return value, so an empty frame is a
                # safe stand-in (mirrors why ensure_table() uses conn.cursor()
                # directly instead of conn.query() for its CREATE TABLE).
                import pandas as pd
                return pd.DataFrame()
        finally:
            cur.close()


# ─────────────────────────────────────────────────────────────────────────────
# Ported from app_pages/pse_email_hybrid_rest.py -- same "Approach 2"
# grounding-judge pipeline, verbatim except: (1) console-printed call log
# instead of a live st.empty() table, (2) a plain local dict instead of
# st.session_state for the L1 cache. _JUDGE_PIPELINE_TAG/_VERSION unchanged
# so this run shares the deployed app's persistent COCO_PSE_JUDGE_CACHE.
# ─────────────────────────────────────────────────────────────────────────────
class _RestCallLog:
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = []
        self._next_id = 1

    def start(self, label, use_case=""):
        entry = {"id": None, "label": label, "use_case": use_case,
                  "status": "in-flight", "started": time.time(), "elapsed": None}
        with self.lock:
            entry["id"] = self._next_id
            self._next_id += 1
            self.entries.append(entry)
        return entry

    def finish(self, entry, ok=True, error=""):
        with self.lock:
            entry["status"] = "success" if ok else "error"
            entry["elapsed"] = round(time.time() - entry["started"], 2)
            if error:
                entry["error"] = error
        print(f"  [{entry['id']}] {entry['label']:12s} {entry['use_case'][:50]:50s} "
              f"{entry['status']:8s} {entry['elapsed']}s")

    def cache_hit(self, label, use_case=""):
        with self.lock:
            entry_id = self._next_id
            self._next_id += 1
            self.entries.append({"id": entry_id, "label": label, "use_case": use_case,
                                  "status": "cached", "started": time.time(), "elapsed": 0.0})
        print(f"  [{entry_id}] {label:12s} {use_case[:50]:50s} cached   0.0s")

    def snapshot(self, last_n: int = 40):
        with self.lock:
            entries = list(self.entries)
        return list(reversed(entries[-last_n:])), len(entries)


def _logged_rest_call(call_log, label, use_case, fn, *args, **kwargs):
    if call_log is None:
        return fn(*args, **kwargs)
    entry = call_log.start(label, use_case)
    try:
        result = fn(*args, **kwargs)
        call_log.finish(entry, ok=True)
        return result
    except Exception as e:
        call_log.finish(entry, ok=False, error=str(e))
        raise


def _combined_gpa(gpa: dict) -> float:
    return (gpa or {}).get("context_relevance", 0.0) * (gpa or {}).get("groundedness", 0.0) * (gpa or {}).get("answer_relevance", 0.0)


def _gpa_score_band(score: float) -> str:
    if score >= _GPA_SCORE_GOOD:
        return "good"
    if score >= _GPA_SCORE_WARN:
        return "warn"
    return "bad"


def _judge_sanitize_one(conn, uc_id, desc, se_comments, skills, partner_comments="", name="", call_log=None):
    """Verbatim port of pse_email_hybrid_rest.py's _judge_sanitize_one -- see
    that file for the full design rationale (two-pass grounding judge,
    coverage-floor safety net)."""
    debug_errors = {"skills": ""}
    prompt = build_ai_skill_prompt(desc, se_comments, skills, partner_comments, name, include_summary=True)
    try:
        raw = _logged_rest_call(call_log, "Skills", name, cortex_complete,
                                conn, "claude-sonnet-4-5", prompt, max_tokens=_JUDGE_FIRSTPASS_MAX_TOKENS).strip()
        parsed = parse_ai_skill_response(raw, deterministic_skills=skills)
    except Exception as e:
        parsed = {"summary": "", "rationale": "", "deterministic_skill_context": {}, "additional_skills": {}}
        debug_errors["skills"] = f"{type(e).__name__}: {e}"

    summary = parsed.get("summary", "")
    det_ctx = parsed.get("deterministic_skill_context", {}) or {}
    add_skills = parsed.get("additional_skills", {}) or {}

    gpa_scores = {
        skill: {axis: v.get(axis, 0.0) for axis in ("context_relevance", "groundedness", "answer_relevance")}
        for source_map in (det_ctx, add_skills)
        for skill, v in (source_map or {}).items() if isinstance(v, dict)
    }

    candidates = []
    for s in skills:
        ev = (det_ctx.get(s) or {}).get("evidence", "") or ""
        candidates.append((s, ev if ev else "(category-derived, no specific text quote)"))
    for s, v in add_skills.items():
        if isinstance(v, dict) and s not in skills:
            candidates.append((s, v.get("evidence", "") or ""))

    verdicts = {}
    if candidates:
        source_text = " ".join(str(x or "") for x in (name, desc, se_comments, partner_comments))
        judge_prompt = build_grounding_judge_prompt(source_text, candidates)
        try:
            judge_raw = _logged_rest_call(call_log, "Judge", name, cortex_complete,
                                          conn, "claude-sonnet-4-5", judge_prompt, max_tokens=_JUDGE_VERDICT_MAX_TOKENS).strip()
            verdicts = parse_grounding_judge_response(judge_raw)
        except Exception:
            verdicts = {}

    det_admitted = [s for s in skills if verdicts.get(s, {}).get("grounded") is True]
    add_admitted = [s for s in add_skills if verdicts.get(s, {}).get("grounded") is True]
    judge_reasons = {s: verdicts.get(s, {}).get("reason", "") for s in det_admitted + add_admitted}

    if not det_admitted and not add_admitted and candidates:
        candidate_names = [s for s, _ in candidates]
        best = max(candidate_names, key=lambda s: _combined_gpa(gpa_scores.get(s, {})))
        det_admitted = [best]
        judge_reasons[best] = _COVERAGE_FLOOR_SENTINEL

    final_skills = det_admitted + [s for s in add_admitted if s not in det_admitted]

    rationale = parsed.get("rationale", "")
    admitted_set = set(final_skills)
    dropped_skills = (set(skills) | set(add_skills)) - admitted_set
    if rationale and any(re.search(re.escape(s), rationale, re.I) for s in dropped_skills):
        rationale = ""

    return (uc_id, desc, se_comments, partner_comments, name, tuple(skills or []),
            summary, rationale, final_skills, judge_reasons, gpa_scores, debug_errors)


def _judge_sanitize_batch(conn, items: list, l1_cache: dict, partner: str = "", call_log=None) -> dict:
    """Verbatim port of pse_email_hybrid_rest.py's _judge_sanitize_batch,
    with a plain local dict (`l1_cache`) instead of st.session_state for
    the L1 cache -- everything else (L2 persistent-cache integration,
    ThreadPoolExecutor fan-out) unchanged."""
    result = {}
    to_fetch = []
    l2_pending = {}
    for uc_id, desc, se_comments, partner_comments, name, skills in items:
        desc = (desc or "").strip()
        se_comments = (se_comments or "").strip()
        partner_comments = (partner_comments or "").strip()
        name = (name or "").strip()
        skills_key = tuple(skills or [])
        cache_key = (name, desc, se_comments, partner_comments, _JUDGE_PIPELINE_VERSION)
        if not desc and not se_comments and not partner_comments and not skills_key:
            result[uc_id] = {"summary": "", "rationale": "", "skills": [], "judge_reasons": {}, "gpa_scores": {}, "debug_errors": {}}
        elif cache_key in l1_cache:
            result[uc_id] = l1_cache[cache_key]
            if call_log is not None:
                call_log.cache_hit("Skills+Judge", name)
        else:
            hash_key = judge_cache.compute_hash(name, desc, se_comments, partner_comments,
                                                 _JUDGE_PIPELINE_TAG, _JUDGE_PIPELINE_VERSION)
            l2_pending[hash_key] = (uc_id, desc, se_comments, partner_comments, name, skills_key)

    if l2_pending:
        judge_cache.ensure_table(conn)
        l2_hits = judge_cache.batch_lookup(conn, list(l2_pending.keys()), _JUDGE_PIPELINE_TAG)
        for hash_key, (uc_id, desc, se_comments, partner_comments, name, skills_key) in l2_pending.items():
            if hash_key in l2_hits:
                entry = dict(l2_hits[hash_key], debug_errors={"summary": "", "skills": ""})
                l1_cache[(name, desc, se_comments, partner_comments, _JUDGE_PIPELINE_VERSION)] = entry
                result[uc_id] = entry
                if call_log is not None:
                    call_log.cache_hit("Skills+Judge", name)
            else:
                to_fetch.append((uc_id, desc, se_comments, partner_comments, name, skills_key))

    l2_to_insert = []
    debug_log = {}
    if to_fetch:
        print(f"\n{len(to_fetch)} use case(s) need fresh judging (cache miss) -- "
              f"running up to {min(_JUDGE_MAX_WORKERS, len(to_fetch))}-way concurrent REST calls...")
        with ThreadPoolExecutor(max_workers=min(_JUDGE_MAX_WORKERS, len(to_fetch))) as pool:
            future_to_uc = {
                pool.submit(_judge_sanitize_one, conn, uc_id, desc, se_comments, list(skills_key), partner_comments, name, call_log): uc_id
                for uc_id, desc, se_comments, partner_comments, name, skills_key in to_fetch
            }
            for future in as_completed(future_to_uc):
                uc_id = future_to_uc[future]
                try:
                    (uc_id, desc, se_comments, partner_comments, name, skills_key,
                     summary, rationale, final_skills, judge_reasons, gpa_scores, debug_errors) = future.result()
                except Exception as e:
                    debug_log[uc_id] = {"summary": f"TOP-LEVEL {type(e).__name__}: {e}", "skills": ""}
                    continue
                entry = {"summary": summary, "rationale": rationale, "skills": final_skills,
                         "judge_reasons": judge_reasons, "gpa_scores": gpa_scores, "debug_errors": debug_errors}
                if debug_errors.get("skills"):
                    debug_log[uc_id] = debug_errors
                else:
                    hash_key = judge_cache.compute_hash(name, desc, se_comments, partner_comments,
                                                         _JUDGE_PIPELINE_TAG, _JUDGE_PIPELINE_VERSION)
                    l2_to_insert.append((hash_key, partner, name, entry))
                l1_cache[(name, desc, se_comments, partner_comments, _JUDGE_PIPELINE_VERSION)] = entry
                result[uc_id] = entry

    if l2_to_insert:
        judge_cache.batch_insert(conn, l2_to_insert, _JUDGE_PIPELINE_TAG, _JUDGE_PIPELINE_VERSION)

    if debug_log:
        print("\nWARNING -- some use cases hit an error during judging:")
        for uc_id, errs in debug_log.items():
            print(f"  {uc_id}: {errs}")

    for uc_id, _desc, _se, _partner, _name, _skills_key in to_fetch:
        result.setdefault(uc_id, {"summary": "", "rationale": "", "skills": [], "judge_reasons": {}, "gpa_scores": {}, "debug_errors": {}})

    return result


def _group_non_coco_by_partner(non_coco_df, catalog_only: bool = True) -> dict:
    """Adapted from pse_email_hybrid_rest.py's _group_non_coco_by_region --
    same deterministic skill-mapping pre-pass, but grouped by PARTNER_NAME
    instead of macro-region, since this report is already scoped to one
    theater+sub-region combination the caller passed in."""
    sorted_df = non_coco_df.sort_values("USE_CASE_EACV", ascending=False)
    by_partner = {}
    for _, row in sorted_df.iterrows():
        partner = row.get("PARTNER_NAME", "") or ""
        name = row.get("USE_CASE_NAME", "") or ""
        tech = row.get("TECHNICAL_USE_CASE", "") or ""
        se_comments = row.get("SE_COMMENTS", "") or ""
        partner_comments = row.get("PARTNER_COMMENTS", "") or ""
        raw_desc = row.get("USE_CASE_DESCRIPTION", "")
        exp = map_coco_skills_explained(name, tech, se_comments, partner_comments, raw_desc)
        aim_source = detect_aim_source(name, tech, raw_desc, se_comments, partner_comments)
        skills, reasons = apply_aim_override(exp["skills"], exp["reasons"], aim_source)
        if catalog_only:
            skills = [s for s in skills if s != AIM_SKILL_NAME and is_catalog_skill(s)]
        reasons = {k: v for k, v in reasons.items() if k in set(skills)}
        stage = str(row.get("USE_CASE_STAGE", ""))
        sm = re.match(r"^(\d+)", stage)
        stage_num = int(sm.group(1)) if sm else 99
        by_partner.setdefault(partner, []).append({
            "uc_id": str(row.get("USE_CASE_ID", "")),
            "name": name,
            "account": row.get("ACCOUNT_NAME", ""),
            "stage_label": "POC" if stage_num == 3 else ("Deployed" if stage_num == 7 else "Implementation"),
            "eacv": row.get("USE_CASE_EACV", 0) or 0,
            "skills": skills,
            "reasons": reasons,
            "aim_source": aim_source,
            "raw_desc": raw_desc,
            "raw_se_comments": se_comments,
            "raw_partner_comments": partner_comments,
        })
    return by_partner


def _build_gap_rows_by_partner(conn, non_coco_df, l1_cache, call_log=None):
    """Adapted from pse_email_hybrid_rest.py's _build_gap_table_rows --
    groups by partner instead of region, otherwise identical merge logic."""
    by_partner = _group_non_coco_by_partner(non_coco_df, catalog_only=True)
    all_rows = [(partner, row) for partner, rows in by_partner.items() for row in rows]
    items = [(row["uc_id"], row["raw_desc"], row["raw_se_comments"], row["raw_partner_comments"], row["name"], row["skills"])
              for _partner, row in all_rows]
    judged_map = _judge_sanitize_batch(conn, items, l1_cache, call_log=call_log)
    for partner, row in all_rows:
        entry = judged_map.get(row["uc_id"], {"summary": "", "rationale": "", "skills": [], "judge_reasons": {}, "gpa_scores": {}, "debug_errors": {}})
        row["sanitized_desc"] = entry["summary"]
        row["skill_rationale"] = entry["rationale"]
        det_origin = frozenset(s for s in entry["skills"] if s in row["skills"])
        det_reasons = row["reasons"]
        row["skills"] = entry["skills"]
        row["reasons"] = {}
        for s in entry["skills"]:
            reason = entry["judge_reasons"].get(s, "")
            if reason == _COVERAGE_FLOOR_SENTINEL:
                row["reasons"][s] = list(det_reasons.get(s) or [_COVERAGE_FLOOR_FALLBACK])
            else:
                row["reasons"][s] = [reason]
        row["skills"], row["reasons"] = apply_aim_override(row["skills"], row["reasons"], row["aim_source"])
        row["skills"], row["reasons"] = rank_skills_by_gpa(
            row["skills"], row["reasons"], entry.get("gpa_scores", {}), deterministic_origin=det_origin
        )
        row["gpa_scores"] = entry.get("gpa_scores", {})
        del row["raw_desc"]
        del row["raw_se_comments"]
        del row["raw_partner_comments"]
    return by_partner


# ─────────────────────────────────────────────────────────────────────────────
# HTML rendering -- reuses the same CSS idioms as pse_email_hybrid_rest.py's
# _build_report_html for visual consistency (GPA legend/badges, skill chips,
# stage pill, EACV formatting), but grouped by partner.
# ─────────────────────────────────────────────────────────────────────────────
def _exec_table_skill_display(skill: str) -> str:
    return f"{AIM_SKILL_NAME} (snowflake-migration)" if skill == AIM_SKILL_NAME else skill


def _gpa_legend_html() -> str:
    good, warn, bad = _GPA_SCORE_COLORS["good"], _GPA_SCORE_COLORS["warn"], _GPA_SCORE_COLORS["bad"]
    return (
        '<div style="font-size:11px;color:#64748b;background:#f8fafc;border:1px solid #e5e7eb;'
        'border-radius:6px;padding:8px 12px;margin:0 0 16px;">'
        '<b style="color:#334155;">GPA score legend</b> (each skill below, 0.0&ndash;1.0, scored by a second, '
        'independent LLM read against its documented catalog scope) &mdash; '
        '<b>CR</b> = Context Relevance (does the use case call for this capability at all), '
        '<b>GR</b> = Groundedness (is there a real, specific quote backing it), '
        '<b>AR</b> = Answer Relevance (is this specific skill the right one, not just a generic sibling). '
        f'<span style="color:{good};font-weight:700;">&#9632; &ge;0.70 strong</span>&nbsp;&nbsp;'
        f'<span style="color:{warn};font-weight:700;">&#9632; 0.40&ndash;0.69 moderate</span>&nbsp;&nbsp;'
        f'<span style="color:{bad};font-weight:700;">&#9632; &lt;0.40 weak</span>'
        '</div>'
    )


def _gpa_badge_html(skill: str, gpa_scores: dict) -> str:
    g = (gpa_scores or {}).get(skill)
    if not g:
        return ""
    spans = []
    for label, axis in (("CR", "context_relevance"), ("GR", "groundedness"), ("AR", "answer_relevance")):
        score = g.get(axis, 0.0)
        color = _GPA_SCORE_COLORS[_gpa_score_band(score)]
        spans.append(f'<span style="font-size:8.5px;font-weight:700;color:{color};margin-right:6px;">{label} {score:.2f}</span>')
    return '<span style="display:block;margin:1px 0 3px;">' + "".join(spans) + '</span>'


def _stage_pill(stage_label):
    bg, fg = _STAGE_COLORS.get(stage_label, ("#e5e7eb", "#374151"))
    return (f'<span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:8px;'
            f'background:{bg};color:{fg};">{stage_label}</span>')


# ─────────────────────────────────────────────────────────────────────────────
# Executive narrative -- reuses app_pages/executive_email.py's pattern: a
# deterministic, fully-precomputed fact block (every number the narrative
# needs is already correct in Python) fed into a tightly-constrained prompt,
# so the LLM's only job is prose/story structure, never arithmetic or
# invention. Credit/token usage is account-grain only (get_account_coco_
# credits sums SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT per account, no
# use-case-level attribution exists) -- the data block and prompt both state
# this explicitly so the narrative doesn't imply false precision.
# ─────────────────────────────────────────────────────────────────────────────
def _build_narrative_data_block(coco_ucs, by_partner_non_coco: dict, credits_lookup: dict) -> str:
    lines = []
    lines.append("=== SCOPE ===")
    total_coco = len(coco_ucs)
    total_non_coco = sum(len(rows) for rows in by_partner_non_coco.values())
    total_ucs = total_coco + total_non_coco
    all_accounts = sorted(set(coco_ucs["ACCOUNT_NAME"].dropna().unique()) |
                           {u["account"] for rows in by_partner_non_coco.values() for u in rows})
    lines.append(f"Total use cases in scope: {total_ucs} across {len(all_accounts)} accounts.")
    lines.append(f"CoCo-attached: {total_coco}. Non-CoCo-attached: {total_non_coco}.")
    lines.append("")

    lines.append("=== COCO-ATTACHED USE CASES (by account, with account-level credit/token usage) ===")
    lines.append("(Credit/token usage is measured at the ACCOUNT level, not per use case -- an "
                  "account with multiple use cases shows the same usage figure for each.)")
    if len(coco_ucs) > 0:
        for _, row in coco_ucs.sort_values("USE_CASE_EACV", ascending=False).iterrows():
            acct = row.get("ACCOUNT_NAME", "") or ""
            acct_key = acct.upper()
            cr = credits_lookup.get(acct_key, {})
            credits_str = f"${cr['Q2_CREDITS']:,.0f} credits, {cr['Q2_TOKENS']:,.0f} tokens, {cr['ACTIVE_DAYS']} active days" if cr else "no measured usage in this window"
            eacv = row.get("USE_CASE_EACV", 0) or 0
            lines.append(
                f"- Partner: {row.get('PARTNER_NAME','')} | Account: {acct} | Use case: {row.get('USE_CASE_NAME','')} "
                f"| Stage: {row.get('USE_CASE_STAGE','')} | EACV: ${eacv:,.0f} | Attached via: {row.get('COCO_SOURCE','') or 'account usage'} "
                f"| Account usage: {credits_str}"
            )
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("=== NON-COCO-ATTACHED USE CASES (by partner, with CoCo skills identified for each) ===")
    for partner in sorted(by_partner_non_coco.keys()):
        for u in by_partner_non_coco[partner]:
            eacv = u["eacv"]
            skills_str = ", ".join(_exec_table_skill_display(s) for s in u["skills"]) if u["skills"] else "no strongly-grounded skill identified yet"
            lines.append(
                f"- Partner: {partner} | Account: {u['account']} | Use case: {u['name']} "
                f"| Stage: {u['stage_label']} | EACV: ${eacv:,.0f} | CoCo skills identified: {skills_str}"
            )
    lines.append("")
    return "\n".join(lines)


def _build_narrative_prompt(data_block: str, q_start: str, q_end: str, scope_label: str) -> str:
    return f"""You are writing an executive narrative for a Snowflake Sales Engineering RVP (Regional Vice President) audience, summarizing CoCo (Cortex Code) adoption within the {scope_label} scope, for the FY27 Q3 window ({q_start} to {q_end}).

Use ONLY the data below. Do not invent, estimate, or round any number that isn't already present in the data -- every figure the narrative needs is already computed correctly. Do not claim credit/token usage is attributed per use case -- it is account-level only, as the data notes.

DATA:
{data_block}

Write ONE tight paragraph of 100-130 words -- no headers, no bullet lists. Cover, in this order, briefly: the overall scope and CoCo attach split, the single strongest proof point of real CoCo momentum (name one account/partner and the corroborating credit or token usage), and a one-sentence call to action naming the accounts/partners still needing skill enablement. The charts below already carry the detailed numbers -- the paragraph should read as a punchy leadership summary, not a data recap. Confident, factual, suitable for a leadership readout."""


def _generate_narrative(conn, coco_ucs, by_partner_non_coco: dict, credits_lookup: dict, q_start: str, q_end: str,
                         scope_label: str) -> str:
    data_block = _build_narrative_data_block(coco_ucs, by_partner_non_coco, credits_lookup)
    prompt = _build_narrative_prompt(data_block, q_start, q_end, scope_label)
    try:
        narrative = cortex_complete(conn, "claude-sonnet-4-5", prompt, max_tokens=500).strip()
        if narrative:
            return narrative
    except Exception as e:
        print(f"  WARNING: narrative generation failed ({type(e).__name__}: {e}) -- using fallback summary.")
    total_coco = len(coco_ucs)
    total_non_coco = sum(len(rows) for rows in by_partner_non_coco.values())
    return (
        f"Across the {scope_label} scope for {q_start} to {q_end}, {total_coco + total_non_coco} use cases "
        f"are in scope, of which {total_coco} are CoCo-attached and {total_non_coco} are not yet attached. "
        f"See the tables below for the full account, partner, and skill-level detail."
    )


def _md_bold_to_html(text: str) -> str:
    """Escapes text then converts markdown **bold** markers (the LLM's
    section-header convention -- see _build_narrative_prompt) into <b>
    tags. Escaping first, then unescaping just the two asterisk-derived
    tags, avoids any HTML injection risk from the model's own text."""
    escaped = _h(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def _build_narrative_html(narrative_text: str) -> str:
    blocks = []
    for para in narrative_text.strip().split("\n\n"):
        para = para.strip()
        if not para:
            continue
        stripped = para.strip("* ").strip()
        if para.startswith("**") and para.rstrip().endswith("**") and len(stripped) < 40:
            # A standalone "**Section Header**" paragraph -- render as a
            # section label, not a body paragraph.
            blocks.append(
                f'<div style="font-size:11px;font-weight:800;letter-spacing:.04em;'
                f'text-transform:uppercase;color:#0369a1;margin:14px 0 6px;">{_h(stripped)}</div>'
            )
        else:
            blocks.append(f'<p style="margin:0 0 12px 0;font-size:12.5px;color:#374151;">{_md_bold_to_html(para)}</p>')
    return f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:18px;background:#fafbfc;">
  <h2 style="font-size:15px;margin:0 0 10px;color:#0f172a;">Executive Narrative</h2>
  {"".join(blocks)}
</div>"""


def _credit_bar_html(value: float, max_value: float, color: str = "#29b5e8") -> str:
    pct = min(100, round(value / max_value * 100, 1)) if max_value else 0
    return (f'<span style="width:140px;height:10px;background:#f1f5f9;border-radius:5px;'
            f'overflow:hidden;display:inline-block;vertical-align:middle;">'
            f'<span style="display:block;height:100%;width:{pct}%;background:{color};"></span></span>')


def _bar_row_html(label: str, value: float, max_value: float, color: str, value_label: str) -> str:
    pct = min(100, round(value / max_value * 100, 1)) if max_value else 0
    return f"""
<div style="display:flex;align-items:center;margin-bottom:7px;">
  <div style="width:190px;font-size:11px;color:#374151;padding-right:8px;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap;" title="{_h(label)}">{_h(label)}</div>
  <div style="flex:1;height:14px;background:#f1f5f9;border-radius:4px;overflow:hidden;">
    <div style="height:100%;width:{pct}%;background:{color};"></div>
  </div>
  <div style="width:64px;text-align:right;font-size:11px;font-weight:700;color:#0f172a;padding-left:8px;">{value_label}</div>
</div>"""


def _attach_split_chart_html(coco_ucs, non_coco) -> str:
    """Two side-by-side stacked bars: CoCo vs non-CoCo attach split, by use
    case count and by EACV. Pure visual complement to the narrative."""
    coco_n, non_n = len(coco_ucs), len(non_coco)
    coco_eacv = float(coco_ucs["USE_CASE_EACV"].fillna(0).sum())
    non_eacv = float(non_coco["USE_CASE_EACV"].fillna(0).sum())
    total_n = coco_n + non_n
    total_eacv = coco_eacv + non_eacv
    coco_n_pct = round(coco_n / total_n * 100, 1) if total_n else 0
    coco_eacv_pct = round(coco_eacv / total_eacv * 100, 1) if total_eacv else 0

    def _stacked(coco_val, non_val, coco_label, non_label):
        total = coco_val + non_val
        coco_w = round(coco_val / total * 100, 1) if total else 0
        non_w = 100 - coco_w
        return f"""
<div style="height:24px;border-radius:5px;overflow:hidden;display:flex;">
  <div style="width:{coco_w}%;background:#16a34a;display:flex;align-items:center;
    justify-content:center;color:#fff;font-size:10.5px;font-weight:700;white-space:nowrap;">
    {coco_label if coco_w > 14 else ''}</div>
  <div style="width:{non_w}%;background:#dc2626;display:flex;align-items:center;
    justify-content:center;color:#fff;font-size:10.5px;font-weight:700;white-space:nowrap;">
    {non_label if non_w > 14 else ''}</div>
</div>"""

    count_bar = _stacked(coco_n, non_n, f"{coco_n} CoCo", f"{non_n} Non-CoCo")
    eacv_bar = _stacked(coco_eacv, non_eacv, f"${coco_eacv/1e6:.1f}M", f"${non_eacv/1e6:.1f}M")
    return f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:18px;">
  <h2 style="font-size:15px;margin:0 0 10px;color:#0f172a;">CoCo Attach Split</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
    <div>
      <div style="font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;
        color:#6b7280;margin-bottom:5px;">By use case count &mdash; {coco_n_pct}% attached</div>
      {count_bar}
    </div>
    <div>
      <div style="font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;
        color:#6b7280;margin-bottom:5px;">By EACV &mdash; {coco_eacv_pct}% attached</div>
      {eacv_bar}
    </div>
  </div>
</div>"""


def _partner_gap_chart_html(by_partner: dict) -> str:
    """Horizontal bar chart of non-CoCo EACV by partner, sorted descending."""
    rows = []
    for partner, items in by_partner.items():
        eacv = sum(u["eacv"] for u in items)
        rows.append((partner, eacv, len(items)))
    rows.sort(key=lambda r: r[1], reverse=True)
    if not rows:
        return ""
    max_eacv = rows[0][1] or 1
    bars = "".join(
        _bar_row_html(f"{p} ({n} UC{'s' if n != 1 else ''})", eacv, max_eacv, "#f59e0b", f"${eacv/1e6:.2f}M")
        for p, eacv, n in rows
    )
    return f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:18px;">
  <h2 style="font-size:15px;margin:0 0 10px;color:#0f172a;">Non-CoCo EACV by Partner</h2>
  {bars}
</div>"""


def _stage_distribution_chart_html(by_partner: dict) -> str:
    """Horizontal bar chart of non-CoCo use case counts by pipeline stage."""
    counts = Counter()
    for items in by_partner.values():
        for u in items:
            counts[u["stage_label"]] += 1
    rows = counts.most_common()
    if not rows:
        return ""
    max_c = rows[0][1]
    bars = "".join(
        _bar_row_html(stage, c, max_c, "#7c3aed", str(c))
        for stage, c in rows
    )
    return f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:18px;">
  <h2 style="font-size:15px;margin:0 0 10px;color:#0f172a;">Non-CoCo Use Cases by Stage</h2>
  {bars}
</div>"""


def _rate_color(rate: float) -> str:
    if rate >= 0.7:
        return "#16a34a"
    if rate >= 0.4:
        return "#f59e0b"
    return "#dc2626"


_CATEGORY_COLORS = {
    "AI": "#0369a1",
    "Analytics": "#16a34a",
    "Data Engineering": "#f59e0b",
    "Platform": "#7c3aed",
    "Apps & Collab": "#dc2626",
    "Observability": "#0891b2",
}
_CATEGORY_COLOR_FALLBACK = "#9ca3af"


def _category_color(cat: str) -> str:
    return _CATEGORY_COLORS.get(cat, _CATEGORY_COLOR_FALLBACK)


def _parse_technical_use_case(raw) -> list:
    """Split TECHNICAL_USE_CASE (semicolon-separated 'Category: Subcategory'
    picklist entries, e.g. 'AI: Machine Learning; Analytics: Business
    Intelligence') into (top_category, sub_category) pairs. A single use
    case row can carry multiple entries, each counted independently in the
    category-level attach-rate stats below."""
    if not raw:
        return []
    pairs = []
    for part in str(raw).split(";"):
        part = part.strip()
        if not part or part.lower().startswith("select value"):
            # Salesforce picklist placeholder for a field left unset
            # (literally "Select value(s) by end of FY26Q2" in the raw
            # data) -- not a real workload category, so it's dropped
            # rather than counted as one.
            continue
        if ":" in part:
            top, sub = part.split(":", 1)
            top, sub = top.strip(), sub.strip()
        else:
            top, sub = part, ""
        if top.upper() == "DE":
            top = "Data Engineering"
        pairs.append((top, sub))
    return pairs


def _compute_partner_attach_stats(detail) -> dict:
    """Returns {partner: {"coco": n, "total": n}} across ALL in-scope use
    cases (CoCo-attached and not), one row per partner -- not just the
    partners with a skill gap (by_partner only covers non-CoCo rows)."""
    stats = {}
    for _, row in detail.iterrows():
        partner = row.get("PARTNER_NAME") or ""
        if not partner:
            continue
        entry = stats.setdefault(partner, {"coco": 0, "total": 0})
        entry["total"] += 1
        if bool(row.get("IS_COCO_ATTACHED")):
            entry["coco"] += 1
    return stats


def _compute_category_stats(detail) -> dict:
    """Returns {top_category: {"coco": n, "total": n, "subs": {sub: {"coco": n, "total": n}}}},
    exploded across every (top, sub) pair found in each row's TECHNICAL_USE_CASE."""
    stats = {}
    for _, row in detail.iterrows():
        is_coco = bool(row.get("IS_COCO_ATTACHED"))
        for top, sub in _parse_technical_use_case(row.get("TECHNICAL_USE_CASE", "")):
            top_entry = stats.setdefault(top, {"coco": 0, "total": 0, "subs": {}})
            top_entry["total"] += 1
            if is_coco:
                top_entry["coco"] += 1
            if sub:
                sub_entry = top_entry["subs"].setdefault(sub, {"coco": 0, "total": 0})
                sub_entry["total"] += 1
                if is_coco:
                    sub_entry["coco"] += 1
    return stats


def _compute_partner_category_stats(detail) -> dict:
    """Returns {partner: {top_category: {"coco": n, "total": n}}} -- each
    (partner, top_category) pair counted once per use case row even if that
    row lists multiple sub-categories under the same top-level category."""
    stats = {}
    for _, row in detail.iterrows():
        partner = row.get("PARTNER_NAME") or ""
        if not partner:
            continue
        is_coco = bool(row.get("IS_COCO_ATTACHED"))
        seen_tops = set()
        for top, _sub in _parse_technical_use_case(row.get("TECHNICAL_USE_CASE", "")):
            if top in seen_tops:
                continue
            seen_tops.add(top)
            entry = stats.setdefault(partner, {}).setdefault(top, {"coco": 0, "total": 0})
            entry["total"] += 1
            if is_coco:
                entry["coco"] += 1
    return stats


def _compute_partner_account_stats(detail) -> dict:
    """Returns {partner: {account: {"coco": n, "total": n}}} -- each
    partner's use cases broken down by the account they belong to."""
    stats = {}
    for _, row in detail.iterrows():
        partner = row.get("PARTNER_NAME") or ""
        account = row.get("ACCOUNT_NAME") or ""
        if not partner or not account:
            continue
        is_coco = bool(row.get("IS_COCO_ATTACHED"))
        entry = stats.setdefault(partner, {}).setdefault(account, {"coco": 0, "total": 0})
        entry["total"] += 1
        if is_coco:
            entry["coco"] += 1
    return stats


_ACCOUNT_PALETTE = [
    "#0369a1", "#16a34a", "#f59e0b", "#7c3aed", "#dc2626",
    "#0891b2", "#be185d", "#65a30d", "#9333ea", "#ea580c",
]


def _account_color(idx: int) -> str:
    return _ACCOUNT_PALETTE[idx % len(_ACCOUNT_PALETTE)]


def _partner_account_split_chart_html(detail) -> str:
    """Stacked horizontal bar chart of each partner's use-case mix, split by
    the account it belongs to (instead of by workload category). Every
    partner's bar is normalized to 100% width so composition is comparable
    regardless of volume (absolute count shown at the end of each row) --
    every partner in scope is included.

    Each account segment is itself split into a filled sub-segment (that
    account's CoCo-attached share) and a hollow, outlined-only sub-segment
    of the same hue (that account's not-yet-attached share) -- filled vs.
    hollow is a much stronger visual signal than a saturation/tint
    difference, with chips below each bar spelling out the exact
    "attached/total" count per account."""
    pa_stats = _compute_partner_account_stats(detail)
    partner_totals = _compute_partner_attach_stats(detail)
    if not pa_stats:
        return ""

    shading_key = ("""
<div style="font-size:10px;color:#9ca3af;margin-bottom:10px;">
  <span style="display:inline-block;width:16px;height:9px;background:#374151;vertical-align:middle;margin-right:4px;border-radius:2px;"></span>filled = CoCo-attached
  &nbsp;&middot;&nbsp;
  <span style="display:inline-block;width:16px;height:9px;vertical-align:middle;margin-right:4px;border-radius:2px;
    background:#fff;border:1.5px solid #374151;box-sizing:border-box;"></span>hollow (outlined) = not yet attached
  &nbsp;&middot;&nbsp; each color is one account &middot; chips below each bar spell out the exact attach count per account
</div>""")

    partners_sorted = sorted(partner_totals.items(), key=lambda kv: kv[1]["total"], reverse=True)
    rows = ""
    for partner, _totals in partners_sorted:
        accounts = pa_stats.get(partner, {})
        acct_total = sum(s["total"] for s in accounts.values())
        if acct_total == 0:
            continue
        accounts_sorted = sorted(accounts.items(), key=lambda kv: kv[1]["total"], reverse=True)
        segments = ""
        chips = ""
        for idx, (account, s) in enumerate(accounts_sorted):
            if not s["total"]:
                continue
            color = _account_color(idx)
            attached_pct = s["coco"] / acct_total * 100
            gap_pct = (s["total"] - s["coco"]) / acct_total * 100
            if attached_pct:
                segments += (
                    f'<div title="{_h(account)}: {s["coco"]}/{s["total"]} CoCo-attached" '
                    f'style="width:{attached_pct}%;height:100%;background:{color};box-sizing:border-box;"></div>'
                )
            if gap_pct:
                segments += (
                    f'<div title="{_h(account)}: {s["coco"]}/{s["total"]} CoCo-attached" '
                    f'style="width:{gap_pct}%;height:100%;background:#fff;border:1.5px solid {color};box-sizing:border-box;"></div>'
                )
            chips += (
                f'<span style="display:inline-flex;align-items:center;margin-right:10px;font-size:10px;'
                f'color:#374151;white-space:nowrap;">'
                f'<span style="width:8px;height:8px;border-radius:2px;background:{color};display:inline-block;'
                f'margin-right:3px;"></span>{_h(account)} <b style="margin-left:3px;">{s["coco"]}/{s["total"]}</b></span>'
            )
        rows += f"""
<div style="margin-bottom:12px;">
  <div style="display:flex;align-items:center;">
    <div style="width:190px;font-size:11px;color:#374151;padding-right:8px;overflow:hidden;
      text-overflow:ellipsis;white-space:nowrap;" title="{_h(partner)}">{_h(partner)}</div>
    <div style="flex:1;height:14px;border-radius:4px;overflow:hidden;display:flex;background:#f1f5f9;">
      {segments}
    </div>
    <div style="width:64px;text-align:right;font-size:11px;font-weight:700;color:#0f172a;padding-left:8px;">{acct_total} UC{"s" if acct_total != 1 else ""}</div>
  </div>
  <div style="margin-left:198px;margin-top:3px;">{chips}</div>
</div>"""

    if not rows:
        return ""
    return f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:18px;">
  <h2 style="font-size:15px;margin:0 0 10px;color:#0f172a;">CoCo Adoption by Partner (Account Split)</h2>
  <p style="font-size:11px;color:#6b7280;margin:0 0 8px;">Each partner's in-scope use cases, split by the account they belong to (each bar is normalized to that partner's total use-case count). A filled block is that account's CoCo-attached share; a hollow (outlined) block is its not-yet-attached share; the chips below each bar spell out the exact "attached/total" count per account.</p>
  {shading_key}
  {rows}
</div>"""



def _partner_workload_mix_chart_html(detail) -> str:
    """Stacked horizontal bar chart of each partner's use-case workload mix
    (AI / Analytics / Data Engineering / Platform / etc., parsed from
    TECHNICAL_USE_CASE). Every partner's bar is normalized to 100% width so
    the *composition* is comparable across partners regardless of volume
    (absolute count shown at the end of each row) -- every partner in scope
    is included, not just the highest-volume ones.

    Each category segment is itself split into a filled sub-segment (that
    category's CoCo-attached share) and a hollow, outlined-only sub-segment
    of the same hue (that category's non-attached share) -- a plain stacked
    bar of category totals alone would hide exactly the CoCo-attached-vs-total
    detail this report exists to surface. A diagonal hatch pattern, and later
    a light pastel-tint fill, were both tried first but proved too subtle to
    read at the ~14px bar height; filled vs. hollow is a much stronger visual
    signal, and each row also gets an explicit "Category X/Y" chip caption
    underneath, spelling out the attach counts in text rather than relying on
    shading alone."""
    pc_stats = _compute_partner_category_stats(detail)
    partner_totals = _compute_partner_attach_stats(detail)
    if not pc_stats:
        return ""

    global_totals = Counter()
    for cats in pc_stats.values():
        for cat, s in cats.items():
            global_totals[cat] += s["total"]
    categories = [c for c, _ in global_totals.most_common()]

    legend = "".join(
        f'<span style="display:inline-flex;align-items:center;margin-right:14px;font-size:10.5px;color:#374151;">'
        f'<span style="width:10px;height:10px;border-radius:2px;background:{_category_color(c)};'
        f'display:inline-block;margin-right:5px;"></span>{_h(c)}</span>'
        for c in categories
    )
    shading_key = ("""
<div style="font-size:10px;color:#9ca3af;margin-bottom:10px;">
  <span style="display:inline-block;width:16px;height:9px;background:#374151;vertical-align:middle;margin-right:4px;border-radius:2px;"></span>filled = CoCo-attached
  &nbsp;&middot;&nbsp;
  <span style="display:inline-block;width:16px;height:9px;vertical-align:middle;margin-right:4px;border-radius:2px;
    background:#fff;border:1.5px solid #374151;box-sizing:border-box;"></span>hollow (outlined) = not yet attached
  &nbsp;&middot;&nbsp; chips below each bar spell out the exact attach count per category
</div>""")

    partners_sorted = sorted(partner_totals.items(), key=lambda kv: kv[1]["total"], reverse=True)
    rows = ""
    for partner, _totals in partners_sorted:
        cats = pc_stats.get(partner, {})
        cat_total = sum(s["total"] for s in cats.values())
        if cat_total == 0:
            continue
        segments = ""
        chips = ""
        for cat in categories:
            s = cats.get(cat)
            if not s or not s["total"]:
                continue
            color = _category_color(cat)
            attached_pct = s["coco"] / cat_total * 100
            gap_pct = (s["total"] - s["coco"]) / cat_total * 100
            if attached_pct:
                segments += (
                    f'<div title="{_h(cat)}: {s["coco"]}/{s["total"]} CoCo-attached" '
                    f'style="width:{attached_pct}%;height:100%;background:{color};box-sizing:border-box;"></div>'
                )
            if gap_pct:
                segments += (
                    f'<div title="{_h(cat)}: {s["coco"]}/{s["total"]} CoCo-attached" '
                    f'style="width:{gap_pct}%;height:100%;background:#fff;border:1.5px solid {color};box-sizing:border-box;"></div>'
                )
            chips += (
                f'<span style="display:inline-flex;align-items:center;margin-right:10px;font-size:10px;'
                f'color:#374151;white-space:nowrap;">'
                f'<span style="width:8px;height:8px;border-radius:2px;background:{color};display:inline-block;'
                f'margin-right:3px;"></span>{_h(cat)} <b style="margin-left:3px;">{s["coco"]}/{s["total"]}</b></span>'
            )
        rows += f"""
<div style="margin-bottom:12px;">
  <div style="display:flex;align-items:center;">
    <div style="width:190px;font-size:11px;color:#374151;padding-right:8px;overflow:hidden;
      text-overflow:ellipsis;white-space:nowrap;" title="{_h(partner)}">{_h(partner)}</div>
    <div style="flex:1;height:14px;border-radius:4px;overflow:hidden;display:flex;background:#f1f5f9;">
      {segments}
    </div>
    <div style="width:64px;text-align:right;font-size:11px;font-weight:700;color:#0f172a;padding-left:8px;">{cat_total} UC{"s" if cat_total != 1 else ""}</div>
  </div>
  <div style="margin-left:198px;margin-top:3px;">{chips}</div>
</div>"""

    if not rows:
        return ""
    return f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:18px;">
  <h2 style="font-size:15px;margin:0 0 10px;color:#0f172a;">CoCo adoption by Workload</h2>
  <p style="font-size:11px;color:#6b7280;margin:0 0 8px;">Category composition of each partner's in-scope use cases (a use case can span multiple categories, so each bar is normalized to that partner's total category tags, not its raw use-case count). Within each category, a filled block is the CoCo-attached share and a hollow (outlined) block is the not-yet-attached share; the chips below each bar spell out the exact "attached/total" count per category.</p>
  <div style="margin-bottom:10px;">{legend}</div>
  {shading_key}
  {rows}
</div>"""


_SFDC_USE_CASE_URL = "https://snowforce.lightning.force.com/lightning/r/vh__Deliverable__c/{}/view"


def _build_credit_usage_html(credits_lookup: dict, detail, top_n: int = None) -> str:
    """Visual section for account-level CoCo credit/token usage -- KPI tiles
    (total credits/tokens/active accounts across the in-scope accounts) plus
    a CSS bar chart ranking ALL in-scope accounts by credit consumption
    (top_n=None means show every account, since an account-level table is
    the whole point of the section). Credits are account-grain only (see
    get_account_coco_credits), so this section is scoped to the accounts
    actually in this report, not per use case.

    `detail` must be the FULL use-case dataframe (both CoCo-attached AND
    non-CoCo), not just coco_ucs -- an account whose only in-scope use
    case(s) are non-CoCo (e.g. Emerson Electric Company, whose sole use
    cases here belong to Squadron Data Inc but aren't CoCo-attached) would
    otherwise show a blank Partner column. It also drives the per-account
    use case list (name + SFDC link), since a single account can carry
    multiple use cases across multiple partners."""
    if not credits_lookup:
        return ""
    account_to_partners = {}
    account_to_use_cases = {}
    for _, row in detail.iterrows():
        acct = (row.get("ACCOUNT_NAME", "") or "").upper()
        partner = row.get("PARTNER_NAME", "") or ""
        if acct and partner:
            account_to_partners.setdefault(acct, [])
            if partner not in account_to_partners[acct]:
                account_to_partners[acct].append(partner)
        uc_name = row.get("USE_CASE_NAME", "") or ""
        uc_id = row.get("USE_CASE_ID", "") or ""
        if acct and uc_name:
            account_to_use_cases.setdefault(acct, [])
            entry = (uc_name, uc_id)
            if entry not in account_to_use_cases[acct]:
                account_to_use_cases[acct].append(entry)

    total_credits = sum(v["Q2_CREDITS"] for v in credits_lookup.values())
    total_tokens = sum(v["Q2_TOKENS"] for v in credits_lookup.values())
    active_accounts = sum(1 for v in credits_lookup.values() if v["Q2_CREDITS"] > 0)

    tiles = f"""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-bottom:12px;">
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">Total CoCo credits</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;color:#0369a1;">${total_credits:,.0f}</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">across {len(credits_lookup)} account(s), FY27 Q3-to-date</div>
  </div>
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">Total tokens</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;color:#0f172a;">{total_tokens/1e9:.2f}B</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">Cortex Code usage, this scope</div>
  </div>
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">Active accounts</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;color:#16a34a;">{active_accounts}</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">of {len(credits_lookup)} with measured usage</div>
  </div>
</div>"""

    ranked = sorted(credits_lookup.items(), key=lambda kv: kv[1]["Q2_CREDITS"], reverse=True)
    if top_n:
        ranked = ranked[:top_n]
    max_credits = ranked[0][1]["Q2_CREDITS"] if ranked else 1
    bar_rows = ""
    for acct, v in ranked:
        partner = ", ".join(account_to_partners.get(acct, []))
        use_cases_html = ", ".join(
            f'<a href="{_SFDC_USE_CASE_URL.format(uc_id)}" style="color:#0369a1;text-decoration:none;" '
            f'target="_blank">{_h(uc_name)}</a>' if uc_id else _h(uc_name)
            for uc_name, uc_id in account_to_use_cases.get(acct, [])
        ) or "&mdash;"
        bar_rows += f"""
<tr>
  <td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;font-size:11.5px;color:#1f2430;vertical-align:top;">{_h(acct.title())}</td>
  <td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;font-size:10.5px;color:#6b7280;vertical-align:top;">{_h(partner)}</td>
  <td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;font-size:10.5px;vertical-align:top;">{use_cases_html}</td>
  <td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{_credit_bar_html(v["Q2_CREDITS"], max_credits)}</td>
  <td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;text-align:right;font-size:11.5px;color:#0369a1;font-weight:700;vertical-align:top;">${v["Q2_CREDITS"]:,.0f}</td>
  <td style="padding:5px 10px;border-bottom:1px solid #f1f5f9;text-align:right;font-size:10.5px;color:#6b7280;vertical-align:top;">{v["Q2_TOKENS"]/1e6:,.0f}M tok &middot; {v["ACTIVE_DAYS"]}d active</td>
</tr>"""

    return f"""
<div style="margin-bottom:18px;">
  <h2 style="font-size:15px;margin:0 0 10px;color:#0f172a;">CoCo Credit &amp; Token Usage (Account-Level)</h2>
  {tiles}
  <table style="width:100%;border-collapse:collapse;">
    <thead><tr style="background:#f8fafc;">
      <th style="padding:5px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;color:#6b7280;">Account</th>
      <th style="padding:5px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;color:#6b7280;">Partner</th>
      <th style="padding:5px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;color:#6b7280;">Use Case(s)</th>
      <th style="padding:5px 10px;text-align:left;font-size:9.5px;text-transform:uppercase;color:#6b7280;">Usage</th>
      <th style="padding:5px 10px;text-align:right;font-size:9.5px;text-transform:uppercase;color:#6b7280;">Credits</th>
      <th style="padding:5px 10px;text-align:right;font-size:9.5px;text-transform:uppercase;color:#6b7280;">Tokens / Days</th>
    </tr></thead>
    <tbody>{bar_rows}</tbody>
  </table>
</div>"""


def _build_mfg_skill_report_html(by_partner: dict, q_start: str, q_end: str, theater: str, subregions: list,
                                  narrative_html: str = "",
                                  credit_usage_html: str = "", attach_split_html: str = "",
                                  partner_gap_chart_html: str = "", stage_chart_html: str = "",
                                  partner_workload_mix_html: str = "",
                                  partner_account_split_html: str = "",
                                  scope_stats: dict = None) -> str:
    total_ucs = sum(len(rows) for rows in by_partner.values())
    total_eacv = sum(u["eacv"] for rows in by_partner.values() for u in rows) / 1_000_000
    n_partners = len(by_partner)
    subregion_label = "+".join(subregions)
    scope_label = f"{theater} / {subregion_label}"

    scope_stats = scope_stats or {}
    scope_tiles = ""
    if scope_stats:
        scope_tiles = f"""
<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin-bottom:16px;background:#fafbfc;">
  <div style="font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:#6b7280;margin-bottom:8px;">
    Full FY27 Q3 OKR Scope &mdash; {_h(scope_label)}
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;">
    <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;background:#fff;">
      <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">OKR partners in scope</div>
      <div style="font-size:24px;font-weight:800;margin-top:4px;color:#0f172a;">{scope_stats['total_partners']}</div>
      <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">FY27 Q3-tracked, {_h(scope_label)}</div>
    </div>
    <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;background:#fff;">
      <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">Total use cases</div>
      <div style="font-size:24px;font-weight:800;margin-top:4px;color:#0f172a;">{scope_stats['total_ucs']}</div>
      <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">across {scope_stats['total_accounts']} account(s)</div>
    </div>
    <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;background:#fff;">
      <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">CoCo-attached</div>
      <div style="font-size:24px;font-weight:800;margin-top:4px;color:#16a34a;">{scope_stats['coco_n']}</div>
      <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">${scope_stats['coco_eacv']:.2f}M EACV</div>
    </div>
    <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;background:#fff;">
      <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">Non-CoCo</div>
      <div style="font-size:24px;font-weight:800;margin-top:4px;color:#dc2626;">{scope_stats['non_coco_n']}</div>
      <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">${scope_stats['non_coco_eacv']:.2f}M EACV</div>
    </div>
  </div>
</div>"""

    tiles = f"""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-bottom:16px;">
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">Partners with a skill gap</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;color:#0f172a;">{n_partners}</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">of {scope_stats.get('total_partners', n_partners)} OKR partners in scope</div>
  </div>
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">Non-CoCo use cases</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;color:#dc2626;">{total_ucs}</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">{_h(theater)} theater &middot; {_h(subregion_label)} industry</div>
  </div>
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">EACV awaiting</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;">${total_eacv:.2f}M</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">across those use cases</div>
  </div>
</div>"""

    partner_sections = ""
    for partner in sorted(by_partner.keys()):
        rows = by_partner[partner]
        partner_eacv = sum(u["eacv"] for u in rows) / 1_000_000
        table_rows = ""
        for seq, u in enumerate(rows, start=1):
            eacv = u["eacv"]
            eacv_str = f"${eacv/1_000_000:.2f}M" if eacv >= 1_000_000 else f"${eacv/1000:.0f}K"
            if u["skills"]:
                chip_html = "".join(
                    f'<span style="display:inline-block;background:#fff;border:1.3px solid #29b5e8;'
                    f'border-radius:4px;padding:1.5px 6px;font-size:9px;font-family:monospace;'
                    f'color:#0369a1;font-weight:700;margin:1px 2px 1px 0;">{_h(_exec_table_skill_display(s))}</span>'
                    f'<span style="font-size:9.5px;color:#64748b;display:block;margin:1px 0 3px;">'
                    f'{"; ".join(u["reasons"].get(s, []))}</span>'
                    f'{_gpa_badge_html(s, u.get("gpa_scores", {}))}'
                    for s in u["skills"]
                )
            else:
                chip_html = ('<span style="color:#9ca3af;font-style:italic;font-size:10.5px;">'
                             'CoCo&rsquo;s AI reviewed this use case and found no skill with strong enough '
                             'grounded support to recommend yet</span>')
            desc = u["sanitized_desc"] or "&mdash;"
            table_rows += f"""
<tr><td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;text-align:right;color:#9ca3af;">{seq}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{_h(u['name'])}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{_h(u['account'])}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{_stage_pill(u['stage_label'])}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;text-align:right;">{eacv_str}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{chip_html}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;font-size:11.5px;color:#374151;">{desc if desc == "&mdash;" else _h(desc)}</td></tr>"""

        partner_sections += f"""
<div style="margin-bottom:22px;">
  <div style="background:#eef2ff;padding:7px 10px;font-weight:700;font-size:12px;color:#312e81;
    text-transform:uppercase;letter-spacing:.03em;border-radius:6px 6px 0 0;">
    {_h(partner)} &mdash; {len(rows)} use case{"s" if len(rows) != 1 else ""} &middot; ${partner_eacv:.2f}M EACV
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:12px;">
    <thead><tr style="background:#f8fafc;">
      <th style="padding:6px 10px;text-align:right;font-size:10px;text-transform:uppercase;color:#6b7280;">#</th>
      <th style="padding:6px 10px;text-align:left;font-size:10px;text-transform:uppercase;color:#6b7280;">Use Case</th>
      <th style="padding:6px 10px;text-align:left;font-size:10px;text-transform:uppercase;color:#6b7280;">Account</th>
      <th style="padding:6px 10px;text-align:left;font-size:10px;text-transform:uppercase;color:#6b7280;">Stage</th>
      <th style="padding:6px 10px;text-align:right;font-size:10px;text-transform:uppercase;color:#6b7280;">EACV</th>
      <th style="padding:6px 10px;text-align:left;font-size:10px;text-transform:uppercase;color:#6b7280;">CoCo Skills (+ reason)</th>
      <th style="padding:6px 10px;text-align:left;font-size:10px;text-transform:uppercase;color:#6b7280;">Description (sanitized)</th>
    </tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>"""

    return f"""<!DOCTYPE html>
<html><head><meta name="color-scheme" content="light only"></head>
<body style="color-scheme:light;background:#ffffff;font-family:-apple-system,'Hiragino Sans','Yu Gothic',Arial,sans-serif;
  max-width:1000px;margin:0 auto;padding:20px;line-height:1.5;color:#1f2430;">
<div style="border:1px solid #e5e7eb;border-radius:12px;padding:20px 22px;">
  <p style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin:0 0 6px;">
    {_h(theater)} Theater &middot; {_h(subregion_label)} Industry &middot; FY27 Q3 OKR Partners
  </p>
  <h1 style="font-size:22px;margin:0 0 6px;color:#0f172a;">{_h(subregion_label)} ({_h(theater)}) FY27 CoCo Q3 OKR Snapshot</h1>
  <p style="font-size:12.5px;color:#6b7280;margin:0 0 16px;">{q_start} &ndash; {q_end}</p>
  {scope_tiles}
  {tiles}
  {attach_split_html}
  {narrative_html}
  {partner_workload_mix_html}
  {partner_account_split_html}
  {credit_usage_html}
  {partner_gap_chart_html}
  {stage_chart_html}
  <h2 style="font-size:15px;margin:20px 0 10px;color:#0f172a;">Non-CoCo Use Cases by Partner</h2>
  <div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;margin-bottom:14px;background:#fafbfc;">
    <p style="font-size:12px;color:#374151;margin:0;">
      The Snowflake PSE (Partner Sales Engineering) team is actively engaged with the partners below on the
      use cases where CoCo is not yet in use. For each use case, PSE has shared a recommended plan of action
      with the partner, along with the specific CoCo skill(s) best suited to close the gap.
    </p>
  </div>
  {_gpa_legend_html()}
  {partner_sections}
  <p style="font-size:10.5px;color:#9ca3af;margin-top:16px;">Generated locally on {time.strftime('%B %d, %Y')}</p>
</div>
</body></html>"""


def _fetch_use_cases(conn, theater, subregions, q_start, q_end):
    """Self-contained copy of utils.queries.get_okr_coco_adoption's query,
    scoped directly to THEATER_NAME=<theater> AND REGION_NAME IN <subregions>
    with explicit uc.-qualified columns throughout.

    Not reusing get_okr_coco_adoption(region=..., subregions=...) directly:
    that function's _theater_filter() helper emits an UNQUALIFIED
    `THEATER_NAME = '...'` filter, which is ambiguous against this query's
    multi-table join (uc + MDM.MDM_INTERFACES.DIM_USE_CASE) and raises
    `SQL compilation error: ambiguous column name 'THEATER_NAME'` -- a
    latent bug in that shared helper (every existing caller either passes
    region=None or hits single-table queries where the column is
    unambiguous). Out of scope to fix here since it's shared production
    code; this local copy sidesteps it entirely by table-qualifying every
    column."""
    schema = get_schema()
    dt_okr = f"{schema}.DT_OKR_USE_CASES"
    query = f"""
    SELECT
        uc.PARTNER_NAME,
        uc.USE_CASE_ID,
        uc.USE_CASE_NUMBER,
        uc.USE_CASE_NAME,
        mdm.USE_CASE_DESCRIPTION,
        mdm.SE_COMMENTS,
        mdm.PARTNER_COMMENTS,
        uc.ACCOUNT_NAME,
        uc.USE_CASE_STAGE,
        uc.USE_CASE_EACV,
        uc.TECHNICAL_USE_CASE,
        uc.THEATER_NAME,
        uc.REGION_NAME,
        uc.DECISION_DATE,
        uc.GO_LIVE_DATE,
        uc.IS_COCO AS IS_COCO_ATTACHED,
        uc.COCO_SOURCE
    FROM {dt_okr} uc
    LEFT JOIN MDM.MDM_INTERFACES.DIM_USE_CASE mdm ON uc.USE_CASE_ID = mdm.USE_CASE_ID
    WHERE uc.THEATER_NAME = '{theater}'
      AND uc.REGION_NAME IN ({", ".join(f"'{r}'" for r in subregions)})
      AND (
          (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{q_start}' AND uc.DECISION_DATE <= '{q_end}')
          OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{q_start}' AND uc.GO_LIVE_DATE <= '{q_end}')
      )
    ORDER BY uc.PARTNER_NAME, IS_COCO_ATTACHED DESC, uc.USE_CASE_EACV DESC NULLS LAST
    """
    return conn.query(query)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Generate the CoCo skill-gap HTML report for a given theater/sub-region, FY27 Q3 OKR window."
    )
    parser.add_argument("--theater", required=True, help="THEATER_NAME value, e.g. USMajors, EMEA, APJ.")
    parser.add_argument("--subregion", required=True, nargs="+",
                         help="One or more REGION_NAME values, e.g. MFG or RCG FSI (space-separated for multiple).")
    parser.add_argument("--output", default=None,
                         help="Output HTML path (default: output/reports/<subregion>_<theater>_skill_report.html).")
    args = parser.parse_args()

    theater = args.theater
    subregions = args.subregion
    subregion_slug = "_".join(s.lower() for s in subregions)
    output_path = Path(args.output) if args.output else REPORTS_DIR / f"{subregion_slug}_{theater.lower()}_skill_report.html"
    scope_label = f"{theater} / {'+'.join(subregions)}"

    print("Connecting to Snowflake (externalbrowser SSO -- a browser window should open)...")
    raw_conn = snowflake.connector.connect(
        account="SFCOGSOPS-SNOWHOUSE_AWS_US_WEST_2",
        user="plakhanpal",
        authenticator="externalbrowser",
        role="sales_engineer",
        warehouse="COCO_PARTNER_ADOPTION_WH",
        database="temp",
        schema="plakhanpal",
    )
    conn = _ConnShim(raw_conn)
    print(f"Connected. Using schema: {get_schema()}")

    print(f"\nFetching use cases for THEATER_NAME='{theater}', REGION_NAME in {subregions}, "
          f"{Q_START} to {Q_END}...")
    detail = _fetch_use_cases(conn, theater, subregions, Q_START, Q_END).copy()
    detail["PARTNER_NAME"] = detail["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
    detail = detail[detail["PARTNER_NAME"].isin(MANAGED_PARTNERS)].copy()
    print(f"  {len(detail)} use cases across {detail['PARTNER_NAME'].nunique()} OKR-tracked partner(s).")

    if len(detail) == 0:
        print("No in-scope use cases found. Exiting.")
        return

    partners = tuple(sorted(detail["PARTNER_NAME"].unique()))
    conf_scores = get_bulk_confidence_scores(conn, partners, Q_START, Q_END)
    if len(conf_scores) > 0:
        conf_map = conf_scores[["USE_CASE_ID", "CONFIDENCE_BAND", "Q2_TOKENS"]].set_index("USE_CASE_ID")
        detail["CONFIDENCE_BAND"] = detail["USE_CASE_ID"].map(conf_map["CONFIDENCE_BAND"])
        detail["Q2_TOKENS"] = detail["USE_CASE_ID"].map(conf_map["Q2_TOKENS"])
        detail["IS_COCO"] = detail["IS_COCO_ATTACHED"]
        detail["IS_COCO_ATTACHED"] = apply_coco_final(detail, CONFIDENCE_BANDS)

    non_coco = detail[detail["IS_COCO_ATTACHED"] == False].copy()  # noqa: E712
    coco_ucs = detail[detail["IS_COCO_ATTACHED"] == True].copy()  # noqa: E712
    print(f"  {len(non_coco)} non-CoCo-attached use case(s), {len(coco_ucs)} CoCo-attached use case(s).")
    if len(non_coco) == 0:
        print("No non-CoCo use cases in scope. Exiting.")
        return

    print("\nFetching account-level CoCo credit/token usage...")
    distinct_accounts = tuple(sorted(detail["ACCOUNT_NAME"].dropna().str.upper().unique()))
    credits_df = get_account_coco_credits(conn, distinct_accounts, Q_START)
    credits_lookup = {
        row["ACCOUNT_NAME_UPPER"]: {
            "Q2_CREDITS": float(row["Q2_CREDITS"] or 0), "Q2_TOKENS": float(row["Q2_TOKENS"] or 0),
            "ACTIVE_DAYS": int(row["ACTIVE_DAYS"] or 0), "LAST_ACTIVE": row["LAST_ACTIVE"],
        }
        for _, row in credits_df.iterrows()
    } if len(credits_df) > 0 else {}
    print(f"  Credit/token usage found for {len(credits_lookup)} of {len(distinct_accounts)} account(s).")

    call_log = _RestCallLog()
    l1_cache = {}
    print("\nRunning REST-based LLM-as-judge grounding pipeline...")
    by_partner = _build_gap_rows_by_partner(conn, non_coco, l1_cache, call_log=call_log)

    entries, total = call_log.snapshot(last_n=1000)
    ok = sum(1 for e in entries if e["status"] == "success")
    err = sum(1 for e in entries if e["status"] == "error")
    cached = sum(1 for e in entries if e["status"] == "cached")
    print(f"\nDone. {total} REST call(s) total -- {ok} succeeded, {err} failed, {cached} served from cache.")

    print("\nGenerating executive narrative...")
    narrative_text = _generate_narrative(conn, coco_ucs, by_partner, credits_lookup, Q_START, Q_END, scope_label)
    narrative_html = _build_narrative_html(narrative_text)
    credit_usage_html = _build_credit_usage_html(credits_lookup, detail)
    attach_split_html = _attach_split_chart_html(coco_ucs, non_coco)
    partner_gap_chart_html = _partner_gap_chart_html(by_partner)
    stage_chart_html = _stage_distribution_chart_html(by_partner)
    partner_workload_mix_html = _partner_workload_mix_chart_html(detail)
    partner_account_split_html = _partner_account_split_chart_html(detail)

    scope_stats = {
        "total_partners": detail["PARTNER_NAME"].nunique(),
        "total_ucs": len(detail),
        "total_accounts": detail["ACCOUNT_NAME"].nunique(),
        "coco_n": len(coco_ucs),
        "coco_eacv": float(coco_ucs["USE_CASE_EACV"].fillna(0).sum()) / 1_000_000,
        "non_coco_n": len(non_coco),
        "non_coco_eacv": float(non_coco["USE_CASE_EACV"].fillna(0).sum()) / 1_000_000,
    }

    print("\nBuilding HTML report...")
    html = _build_mfg_skill_report_html(
        by_partner, Q_START, Q_END, theater, subregions, narrative_html=narrative_html,
        credit_usage_html=credit_usage_html, attach_split_html=attach_split_html,
        partner_gap_chart_html=partner_gap_chart_html, stage_chart_html=stage_chart_html,
        partner_workload_mix_html=partner_workload_mix_html,
        partner_account_split_html=partner_account_split_html,
        scope_stats=scope_stats,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"\nReport written to: {output_path}")


if __name__ == "__main__":
    main()
