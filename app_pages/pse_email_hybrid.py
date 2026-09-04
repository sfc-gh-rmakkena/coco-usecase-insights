"""PSE CoCo Use Case Insights — DEV only.

Combines two layouts approved via HTML mockups:
  Part 1 (Narrative): an AI-drafted, editable personal letter — copy as rich
                       text only, no download.
  Part 2 (Report):    a dense "executive table" report — anonymized peer
                       benchmark, regional breakdown, restructured non-CoCo
                       gap table (skills + reason + sanitized description,
                       Stage as a column, no consumption data), and a
                       concrete action plan. Copy as rich text, download as
                       HTML, or download as a real PDF (reportlab).

This page uses its own session_state keys (prefixed `_pse_hybrid_`) so it
never collides with the original PSE Email page's cached state.
"""
import io
import re
import html as html_lib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from utils import (
    APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, LATAM_RSI_REGION_MAP,
    PARTNER_RENAME_MAP, apply_coco_final,
)
from utils.queries import (
    get_okr_coco_adoption, get_usecase_confidence_scores, get_bulk_confidence_scores,
)
from utils.config import get_env
from utils.cortex_helpers import cortex_complete
from utils.report import copy_rich_text_button
from utils.coco_skill_map_v2 import (
    map_coco_skills_explained, theater_label as _theater_label, h as _h,
    MANAGED_PARTNERS, GSI_LIST, GSI_NAMES, NOAM_RSI_NAMES,
    build_ai_skill_prompt, parse_ai_skill_response, merge_additional_skills,
    detect_aim_source, apply_aim_override, cap_skills, prioritize_aim_skill,
    AIM_SKILL_NAME, MAX_SKILLS_PER_USE_CASE,
)

SNOWFLAKE_BLUE = "#29b5e8"
NOAM_THEATERS = ("AMSExpansion", "USMajors", "AMSAcquisition", "USPubSec")


def _exec_table_skill_display(skill: str) -> str:
    """Display-only rename for the executive table grid (Part 2): 'Snowflake
    AIM' shows as 'Snowflake AIM (snowflake-migration)' so partners can see
    the underlying CoCo skill tag name, without touching the narrative (Part
    1) or the underlying `skill`/`reasons` dict keys used elsewhere."""
    return f"{AIM_SKILL_NAME} (snowflake-migration)" if skill == AIM_SKILL_NAME else skill


# ─────────────────────────────────────────────────────────────────────────────
# Data / computation helpers — shared by the HTML and PDF renderers so the
# two outputs are always built from identical numbers.
# ─────────────────────────────────────────────────────────────────────────────

def _peer_group_for(partner: str):
    """Return (peer_partner_names, region_filter_kind, region_value, target_pct, group_label)
    for the group `partner` belongs to. region_filter_kind is one of
    'none' (global), 'theater' (NoAM RSIs), 'region' (APJ/EMEA/LATAM RSIs)."""
    if partner in GSI_NAMES:
        return ([p for p in GSI_LIST if p != partner], "none", None, 75, "GSIs")
    if partner in NOAM_RSI_NAMES:
        return ([p for p in NOAM_RSI_NAMES if p != partner], "theater", NOAM_THEATERS, 75, "NoAM RSIs")
    if partner in APJ_RSI_REGION_MAP:
        region = APJ_RSI_REGION_MAP[partner][1]
        peers = [p for p, v in APJ_RSI_REGION_MAP.items() if p != partner and v[1] == region]
        return (peers, "region", region, 50, f"{region} RSIs")
    if partner in EMEA_RSI_REGION_MAP:
        region = EMEA_RSI_REGION_MAP[partner][1]
        peers = [p for p, v in EMEA_RSI_REGION_MAP.items() if p != partner and v[1] == region]
        return (peers, "region", region, 50, f"{region} RSIs")
    if partner in LATAM_RSI_REGION_MAP:
        peers = [p for p in LATAM_RSI_REGION_MAP if p != partner]
        return (peers, "region", "LATAM", 50, "LATAM RSIs")
    return ([], "none", None, 75, "partners")


def _compute_peer_benchmark(conn, partner, q_start, q_end, coco_pct):
    """Anonymized OKR ranking: where `partner`'s attach rate ranks among its
    peer group (no peer identities disclosed), plus the point-gap to the
    group's OKR target. Returns None if there is no peer group."""
    peers, filter_kind, filter_value, target, group_label = _peer_group_for(partner)
    if not peers:
        return None
    conf = get_bulk_confidence_scores(conn, tuple(sorted(peers)), q_start, q_end)
    if len(conf) == 0:
        return None
    if filter_kind == "theater":
        conf = conf[conf["THEATER_NAME"].isin(filter_value)]
    elif filter_kind == "region" and "REGION_NAME" in conf.columns:
        conf = conf[conf["REGION_NAME"] == filter_value]
    if len(conf) == 0:
        return None
    conf = conf.copy()
    conf["IS_COCO_FINAL"] = apply_coco_final(conf, ["High"])
    # Canonicalize aliases (e.g. 'IBM Consulting' -> 'IBM', 'Ernst & Young (EY)' -> 'EY')
    # before grouping, otherwise the same company's use cases split across its alias
    # spellings count as two separate "peers" and inflate the group size / skew rank.
    conf["PARTNER_NAME"] = conf["PARTNER_NAME"].map(lambda p: PARTNER_RENAME_MAP.get(p, p))
    per_partner = conf.groupby("PARTNER_NAME").agg(
        TOTAL=("USE_CASE_ID", "count"), COCO=("IS_COCO_FINAL", "sum"),
    ).reset_index()
    per_partner = per_partner[per_partner["TOTAL"] > 0]
    if len(per_partner) == 0:
        return None
    per_partner["PCT"] = per_partner["COCO"] * 100.0 / per_partner["TOTAL"]
    peer_pcts = per_partner["PCT"].tolist()
    rank = sum(1 for pct in peer_pcts if pct > coco_pct) + 1
    return {
        "rank": rank,
        "total_in_group": len(peer_pcts) + 1,
        "target": target,
        "group_label": group_label,
    }


def _compute_regional_breakdown(detail_df: pd.DataFrame, target: int):
    """Group all UCs (coco + non-coco) by region label, matching
    other_pse_email.pdf's Regional Breakdown table structure exactly.

    GAP is the OKR-target shortfall (clamped to 0 once the partner has hit
    the target% -- it never goes negative). REMAINING is the true count of
    non-CoCo use cases left in the region regardless of the target, i.e.
    how far the partner actually is from 100% attach. A partner can have
    GAP == 0 (target met) while REMAINING > 0 (still short of 100%) -- that
    combination should be framed as a "push to 100%" ask, not hidden just
    because the OKR itself is satisfied."""
    rows = []
    for label in ["AMS", "EMEA", "APJ"]:
        sub = detail_df[detail_df["THEATER_NAME"].apply(_theater_label) == label]
        if len(sub) == 0:
            continue
        total = len(sub)
        coco = int(sub["IS_COCO_ATTACHED"].sum())
        pct = round(coco * 100.0 / total, 1) if total else 0.0
        gap = max(0, int(round(target / 100.0 * total)) - coco)
        rows.append({
            "REGION": "NoAM" if label == "AMS" else label,
            "TOTAL_UCS": total, "COCO_UCS": coco, "COCO_PCT": pct,
            "GAP": gap, "REMAINING": total - coco, "EACV": float(sub["USE_CASE_EACV"].sum()),
        })
    if rows:
        g_total = sum(r["TOTAL_UCS"] for r in rows)
        g_coco = sum(r["COCO_UCS"] for r in rows)
        g_pct = round(g_coco * 100.0 / g_total, 1) if g_total else 0.0
        g_gap = max(0, int(round(target / 100.0 * g_total)) - g_coco)
        rows.append({
            "REGION": "Global", "TOTAL_UCS": g_total, "COCO_UCS": g_coco,
            "COCO_PCT": g_pct, "GAP": g_gap, "REMAINING": g_total - g_coco,
            "EACV": sum(r["EACV"] for r in rows),
        })
    non_global = [r for r in rows if r["REGION"] != "Global"]
    max_gap_region = max(non_global, key=lambda r: r["GAP"]) if non_global else None
    return rows, max_gap_region


_SANITIZE_MAX_WORKERS = 10  # matches the ThreadPoolExecutor pattern in pse-si-qbr's streamlit_app.py
_SANITIZE_MAX_TOKENS = 700  # each call answers exactly ONE use case, so this budget is never shared


def _sanitize_one(conn, uc_id: str, desc: str, se_comments: str, skills: list, partner_comments: str = ""):
    """One Cortex COMPLETE call for exactly one use case, returning a
    partner-safe description summary, a rationale for why the skill set
    accelerates THIS engagement, and (validated) additional catalog-grounded
    skills beyond the deterministic set -- all via the shared prompt/parse
    helpers in coco_skill_map_v2 so this stays a single call, fanned out
    concurrently from a ThreadPoolExecutor with its own dedicated max_tokens
    budget (no batching, no shared budget with any other use case)."""
    prompt = build_ai_skill_prompt(desc, se_comments, skills, partner_comments)
    try:
        raw = cortex_complete(conn, "claude-sonnet-4-5", prompt, max_tokens=_SANITIZE_MAX_TOKENS).strip()
        parsed = parse_ai_skill_response(raw)
    except Exception:
        parsed = {"summary": "", "rationale": "", "additional_skills": {}}
    return (uc_id, desc, se_comments, partner_comments, tuple(skills or []),
            parsed["summary"], parsed["rationale"], parsed["additional_skills"])


def _sanitize_descriptions_batch(conn, items: list) -> dict:
    """AI summary + grounded skill rationale + additional catalog-grounded
    skills for MANY use cases -- one independent Cortex COMPLETE call PER use
    case (own max_tokens budget, never shared with another item), fanned out
    CONCURRENTLY via ThreadPoolExecutor so N independent calls don't turn
    into N sequential round-trips. Cached per (description, se_comments,
    partner_comments, skills) tuple for the session, so regenerating for the
    same partner needs zero new calls.

    items: list of (use_case_id, description, se_comments, partner_comments,
    skills) tuples.
    Returns {use_case_id: {"summary": ..., "rationale": ..., "additional_skills": {...}}}.
    """
    cache = st.session_state.setdefault("_pse_hybrid_sanitize_cache", {})
    result = {}
    to_fetch = []  # (uc_id, desc, se_comments, partner_comments, skills_key) still needing an AI call
    for uc_id, desc, se_comments, partner_comments, skills in items:
        desc = (desc or "").strip()
        se_comments = (se_comments or "").strip()
        partner_comments = (partner_comments or "").strip()
        skills_key = tuple(skills or [])
        cache_key = (desc, se_comments, partner_comments, skills_key)
        if not desc and not se_comments and not partner_comments:
            result[uc_id] = {"summary": "", "rationale": "", "additional_skills": {}}
        elif cache_key in cache:
            result[uc_id] = cache[cache_key]
        else:
            to_fetch.append((uc_id, desc, se_comments, partner_comments, skills_key))

    if to_fetch:
        with ThreadPoolExecutor(max_workers=min(_SANITIZE_MAX_WORKERS, len(to_fetch))) as pool:
            futures = [pool.submit(_sanitize_one, conn, uc_id, desc, se_comments, list(skills_key), partner_comments)
                       for uc_id, desc, se_comments, partner_comments, skills_key in to_fetch]
            for future in as_completed(futures):
                try:
                    (uc_id, desc, se_comments, partner_comments, skills_key,
                     summary, rationale, additional_skills) = future.result()
                except Exception:
                    continue
                entry = {"summary": summary, "rationale": rationale, "additional_skills": additional_skills}
                cache[(desc, se_comments, partner_comments, skills_key)] = entry
                result[uc_id] = entry

    # Anything that failed outright still gets a defined value so downstream
    # rendering never KeyErrors.
    for uc_id, _desc, _se, _partner, _skills_key in to_fetch:
        result.setdefault(uc_id, {"summary": "", "rationale": "", "additional_skills": {}})

    return result


def _group_non_coco_by_region(non_coco_df: pd.DataFrame) -> dict:
    """Fast (no AI) per-region grouping of non-CoCo UCs with name/account/skills/
    eacv, sorted by EACV desc within region. Shared base for the narrative's
    quick NoAM preview (no sanitization needed there) and the full gap table
    used in Part 2, which adds an AI-sanitized description on top.

    Skill selection additionally scans SE_COMMENTS and PARTNER_COMMENTS (not
    just the structured Technical Use Case field) for migration signals --
    SEs and partners often name the actual legacy platform being replaced in
    free text that never makes it into the taxonomy field.

    If the description/SE_COMMENTS/PARTNER_COMMENTS/name mention a Snowflake
    AIM-supported legacy source, the generic CoCo migration skills are
    replaced with a single, prioritized 'Snowflake AIM' recommendation (see
    apply_aim_override), and every use case is capped at
    MAX_SKILLS_PER_USE_CASE total (see cap_skills) -- relevance over
    quantity."""
    sorted_df = non_coco_df.sort_values("USE_CASE_EACV", ascending=False)
    by_region = {}
    for _, row in sorted_df.iterrows():
        label = _theater_label(row.get("THEATER_NAME", ""))
        region = "NoAM" if label == "AMS" else label
        name = row.get("USE_CASE_NAME", "") or ""
        tech = row.get("TECHNICAL_USE_CASE", "") or ""
        se_comments = row.get("SE_COMMENTS", "") or ""
        partner_comments = row.get("PARTNER_COMMENTS", "") or ""
        raw_desc = row.get("USE_CASE_DESCRIPTION", "")
        exp = map_coco_skills_explained(name, tech, se_comments, partner_comments, raw_desc)
        aim_source = detect_aim_source(name, tech, raw_desc, se_comments, partner_comments)
        skills, reasons = apply_aim_override(exp["skills"], exp["reasons"], aim_source)
        skills, reasons = cap_skills(skills, reasons)
        stage = str(row.get("USE_CASE_STAGE", ""))
        sm = re.match(r"^(\d+)", stage)
        stage_num = int(sm.group(1)) if sm else 99
        by_region.setdefault(region, []).append({
            "uc_id": str(row.get("USE_CASE_ID", "")),
            "uc_num": row.get("USE_CASE_NUMBER", row.get("USE_CASE_ID", "")),
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
    return by_region


def _build_gap_table_rows(conn, non_coco_df: pd.DataFrame):
    """Per-region list of UC row dicts for the gap table, each with skill+reason,
    a sanitized description, an AI-grounded skill rationale, and any validated
    AI-added skills merged additively on top of the deterministic set (informed
    by the description, SE_COMMENTS, and PARTNER_COMMENTS), sorted by EACV
    desc within region.
    Snowflake AIM override and the MAX_SKILLS_PER_USE_CASE cap are re-applied
    after the AI merge, since the AI's additional_skills could otherwise push
    a use case over the cap or reintroduce a generic migration skill this use
    case already has a better (AIM) answer for."""
    by_region = _group_non_coco_by_region(non_coco_df)
    all_rows = [row for rows in by_region.values() for row in rows]
    items = [(row["uc_id"], row["raw_desc"], row["raw_se_comments"], row["raw_partner_comments"], row["skills"])
              for row in all_rows]
    sanitized_map = _sanitize_descriptions_batch(conn, items)
    for row in all_rows:
        entry = sanitized_map.get(row["uc_id"], {"summary": "", "rationale": "", "additional_skills": {}})
        row["sanitized_desc"] = entry["summary"]
        row["skill_rationale"] = entry["rationale"]
        row["skills"], row["reasons"] = merge_additional_skills(
            row["skills"], row["reasons"], entry.get("additional_skills", {})
        )
        row["skills"], row["reasons"] = apply_aim_override(row["skills"], row["reasons"], row["aim_source"])
        row["skills"], row["reasons"] = cap_skills(row["skills"], row["reasons"])
        del row["raw_desc"]
        del row["raw_se_comments"]
        del row["raw_partner_comments"]
    return by_region


def _build_action_plan(regional_breakdown, gap_rows_by_region, partner):
    """Numbered action items grounded in the partner's actual regional gaps.

    NoAM is the only region PSE can proactively drive: those items showcase
    the specific CoCo skills that can accelerate the listed use cases via a
    working session with the partner's NoAM Delivery Leads. Every other
    region with a gap (EMEA, APJ, ...) is visibility-only for a NoAM-based
    PSE, so those gaps are folded into a single FYI note instead of separate
    actionable items, and flagged to the regional PSE/account teams rather
    than promising direct follow-up.

    The NoAM ask fires whenever there are real non-CoCo NoAM use cases left
    (REMAINING > 0), not just when the OKR target itself is unmet (GAP > 0)
    -- a partner who already hit the target% should still be pushed toward
    100% attach rather than getting no ask at all once the OKR box is
    checked. The wording adapts to which case applies.
    """
    items = []
    noam_row = next((r for r in regional_breakdown if r["REGION"] == "NoAM"), None)
    other_rows = sorted(
        [r for r in regional_breakdown if r["REGION"] not in ("Global", "NoAM") and r["GAP"] > 0],
        key=lambda r: r["GAP"], reverse=True,
    )

    if noam_row and noam_row["REMAINING"] > 0:
        top_ucs = sorted(gap_rows_by_region.get("NoAM", []),
                          key=lambda x: x["eacv"], reverse=True)[:4]
        accounts = []
        for u in top_ucs:
            acct = u.get("account", "") or u["name"]
            if acct not in accounts:
                accounts.append(acct)
        names = ", ".join(accounts) if accounts else "the accounts below"
        skills = []
        for u in top_ucs:
            for s in u.get("skills", []):
                if s not in skills:
                    skills.append(s)
        skills = prioritize_aim_skill(skills)
        skills_str = ", ".join(skills[:3]) if skills else "relevant CoCo skills"
        aim_uc = next((u for u in top_ucs if u.get("aim_source")), None)
        rationale = (
            aim_uc["reasons"][AIM_SKILL_NAME][0] if aim_uc and AIM_SKILL_NAME in aim_uc.get("reasons", {})
            else next((u.get("skill_rationale") for u in top_ucs if u.get("skill_rationale")), "")
        )
        if noam_row["GAP"] > 0:
            lead_in = f"NoAM is at {noam_row['COCO_PCT']}% with {noam_row['GAP']} UCs needed to reach target."
            title = "NoAM Skill Deep-Dive (priority)"
        else:
            lead_in = (
                f"{partner} has already hit the OKR target in NoAM ({noam_row['COCO_PCT']}%) — let's keep "
                f"pushing toward 100% CoCo attach, with {noam_row['REMAINING']} use case"
                f"{'s' if noam_row['REMAINING'] != 1 else ''} left to fully cover."
            )
            title = "NoAM Push to 100%"
        body = (
            f"{lead_in} "
            f"We'd like to set up working sessions with {partner} NoAM Delivery Leads on {names} "
            f"to showcase {skills_str} and demonstrate how they can accelerate these engagements, "
            "then collaborate on tagging them for attribution."
        )
        if rationale:
            body += f" {rationale}"
        items.append({"title": title, "body": body})

    if other_rows:
        summary = ", ".join(f"{r['REGION']} is at {r['COCO_PCT']}% ({r['GAP']} UCs short)" for r in other_rows)
        items.append({
            "title": "Regional Visibility (FYI only)",
            "body": (
                f"{summary}. These fall outside what our NoAM-based team can drive directly, so we're "
                f"flagging them to the regional PSE/account teams to follow up with {partner}'s local delivery leads."
            ),
        })

    items.append({
        "title": "Attribution Registration",
        "body": (
            f"In order for CoCo usage to register as official attribution, {partner} delivery "
            "teams need to confirm which projects are actively using CoCo and how."
        ),
    })
    return items


def _build_narrative_draft(conn, partner, recipients, coco_pct, coco_count, total_ucs,
                            peer_benchmark, regional_breakdown, max_gap_region, gap_rows_by_region, report_date):
    recipients = recipients.strip() or "team"
    peer_line = ""
    if peer_benchmark:
        gap = round(peer_benchmark["target"] - coco_pct, 1)
        global_row = next((r for r in regional_breakdown if r["REGION"] == "Global"), None)
        ucs_needed = global_row["GAP"] if global_row else 0
        rank_str = (f"{partner} ranks {peer_benchmark['rank']} of {peer_benchmark['total_in_group']} "
                    f"{peer_benchmark['group_label']} on OKR attainment")
        if gap <= 0:
            peer_line = f"{rank_str} and has already hit the {peer_benchmark['target']}% target — great work keeping pace!"
        else:
            peer_line = (f"{rank_str}, sitting {gap} points behind the {peer_benchmark['target']}% target"
                         + (f" — closing this gap requires {ucs_needed} more CoCo-attached use cases this quarter."
                            if ucs_needed else "."))
    # NoAM is the only region PSE can proactively drive, so the narrative
    # always leads with NoAM's own status + ask -- regardless of partner
    # type (GSI/RSI) or which region happens to have the biggest raw gap.
    # All other-region activity is FYI-only and always placed at the end
    # (visibility_line below).
    noam_row = next((r for r in regional_breakdown if r["REGION"] == "NoAM"), None)
    noam_status_line = ""
    if noam_row:
        noam_status_line = f"NoAM is at a {noam_row['COCO_PCT']}% CoCo attach rate."

    # Ask names the specific NoAM accounts still needing CoCo attach, but
    # deliberately no skill names or AIM/skill rationale in the narrative
    # itself -- that detail lives only in the attached report/table.
    noam_line = ""
    if noam_row and noam_row["REMAINING"] > 0:
        top_ucs = sorted(gap_rows_by_region.get("NoAM", []),
                          key=lambda x: x["eacv"], reverse=True)[:4]
        accounts = []
        for u in top_ucs:
            acct = u.get("account", "") or u["name"]
            if acct not in accounts:
                accounts.append(acct)
        names = ", ".join(accounts) if accounts else "the accounts below"
        noam_line = (
            f"We'd like to go deeper into {partner}'s NoAM accounts -- {names} -- with the delivery "
            "teams and showcase how to use the highlighted CoCo skills in the attachment to accelerate those use cases."
        )

    other_gaps = ", ".join(
        f"{r['GAP']} UCs short in {r['REGION']}" for r in regional_breakdown
        if r["REGION"] not in ("Global", "NoAM") and r["GAP"] > 0
    )
    visibility_line = (
        f"For visibility, {other_gaps} — these fall outside what our NoAM-based team can drive "
        "directly, so we're flagging them to the regional PSE/account teams." if other_gaps else ""
    )

    # Unconditional order: NoAM status + ask always first, other-region
    # activity always last as FYI -- no branching on partner type or region.
    help_paragraph = f"{noam_status_line} {noam_line} {visibility_line}"

    _REPORT_LINE = "Full account detail is included in the attached report."
    _SPN_LIVE_LINE = (
        "As a heads-up, we've launched a new SPN Live series, airing every Thursday starting "
        "September 10 at 9:00 AM SGT and 9:00 AM PT. There's an upcoming session on September 24 "
        "-- CoCo Tokenomics, hosted by our NoAM PSE team -- going into agentic data engineering "
        "with CoCo: tokens, routing, and real cost efficiency, which could be helpful. Your delivery "
        "teams can register here: https://www.snowflake.com/en/spn-live/"
    )

    prompt = f"""Draft a short, personal email opening (4 short paragraphs max, plain text,
no markdown headers) for a Snowflake Partner SE sending a biweekly CoCo adoption
update to {recipients} at {partner}, dated {report_date}.

Must include, in this order:
1. "Hi {recipients}" greeting, then one line saying the biweekly CoCo adoption update for {partner} is attached.
2. A "Headline:" sentence stating {partner} is at {coco_pct}% CoCo attach rate ({coco_count} of {total_ucs} use cases). {peer_line}
3. A "Where we need your help:" paragraph. {help_paragraph}
4. A friendly sign-off offering a quick call to walk through details.

Do NOT add any line about the attached report or account detail -- that line is added separately, verbatim, after your draft.

Always refer to the partner as "{partner}" by name (e.g. "{partner} ranks..."), never as "you" or "your company" — the update is being sent to individual reps, not addressed to the partner as a whole.

Return only the email body text, no subject line, no signature block."""
    try:
        draft = cortex_complete(conn, "claude-sonnet-4-5", prompt).strip()
        # Insert the report line and SPN Live announcement deterministically
        # (verbatim, exact wording -- especially the dates/times/URL) as their
        # own paragraphs right before the final sign-off paragraph, instead of
        # trusting the LLM to reproduce them word-for-word -- LLMs reliably
        # paraphrase fixed sentences like this even when told not to.
        paras = [p for p in draft.split("\n\n") if p.strip()]
        if len(paras) >= 2:
            paras.insert(-1, _REPORT_LINE)
            paras.insert(-1, _SPN_LIVE_LINE)
        else:
            paras.append(_REPORT_LINE)
            paras.append(_SPN_LIVE_LINE)
        return "\n\n".join(paras)
    except Exception:
        return (
            f"Hi {recipients}\n\nPlease find attached our biweekly CoCo adoption update for "
            f"{partner} as of {report_date}.\n\nHeadline: {partner} is at {coco_pct}% CoCo attach "
            f"rate ({coco_count} of {total_ucs} use cases). {peer_line}\n\nWhere we need your help: "
            f"{help_paragraph}\n\n"
            f"{_REPORT_LINE}\n\n"
            f"{_SPN_LIVE_LINE}\n\n"
            "Happy to set up a quick call to walk through the details."
        )


# ─────────────────────────────────────────────────────────────────────────────
# HTML renderers — Layout D: Part 1 (Layout C letter) + Part 2 (Layout B table)
# ─────────────────────────────────────────────────────────────────────────────

def _build_narrative_html(narrative_text: str, partner: str) -> str:
    paras = "".join(
        f'<p style="margin:0 0 12px 0;font-size:13.5px;color:#374151;">{_h(p)}</p>'
        for p in narrative_text.strip().split("\n\n") if p.strip()
    )
    return f"""<!DOCTYPE html>
<html><head><meta name="color-scheme" content="light only"></head>
<body style="color-scheme:light;background:#ffffff;font-family:-apple-system,'Hiragino Sans','Yu Gothic',Arial,sans-serif;
  max-width:760px;margin:0 auto;padding:20px;line-height:1.6;color:#1f2430;">
{paras}
</body></html>"""


def _region_bar_html(pct, color):
    return (f'<span style="width:90px;height:8px;background:#f1f5f9;border-radius:4px;'
            f'overflow:hidden;display:inline-block;vertical-align:middle;">'
            f'<span style="display:block;height:100%;width:{pct}%;background:{color};"></span></span>')


def _build_report_html(partner, q_start, q_end, target, coco_count, total_ucs, coco_pct,
                        non_coco_count, non_coco_eacv, peer_benchmark, regional_breakdown,
                        gap_rows_by_region, action_plan) -> str:
    eacv_m = non_coco_eacv / 1_000_000

    tiles = f"""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-bottom:6px;">
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">CoCo attach rate</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;color:{'#dc2626' if coco_pct < target else '#16a34a'};">{coco_pct}%</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">Target: {target}%</div>
  </div>
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">CoCo use cases</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;color:#d97706;">{coco_count}</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">of {total_ucs} total in-scope</div>
  </div>
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">Awaiting confirmation</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;color:#dc2626;">{non_coco_count}</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">non-CoCo use cases</div>
  </div>
  <div style="border:1.5px solid #e5e7eb;border-radius:6px;padding:12px 14px;">
    <div style="font-size:10px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:#6b7280;">EACV awaiting</div>
    <div style="font-size:24px;font-weight:800;margin-top:4px;">${eacv_m:.2f}M</div>
    <div style="font-size:10.5px;color:#9ca3af;margin-top:3px;">across those use cases</div>
  </div>
</div>"""

    peer_html = ""
    if peer_benchmark:
        gap = round(peer_benchmark["target"] - coco_pct, 1)
        global_row = next((r for r in regional_breakdown if r["REGION"] == "Global"), None)
        ucs_needed = global_row["GAP"] if global_row else 0
        rank_str = (f"{_h(partner)} ranks <b>{peer_benchmark['rank']} of {peer_benchmark['total_in_group']}</b> "
                    f"{_h(peer_benchmark['group_label'])} on OKR attainment")
        if gap <= 0:
            detail = f"and has already hit the {peer_benchmark['target']}% target &mdash; great work keeping pace!"
        else:
            detail = (f", sitting <b>{gap} points</b> behind the {peer_benchmark['target']}% target"
                      + (f", closing this gap requires <b>{ucs_needed} more</b> CoCo-attached use cases this quarter."
                         if ucs_needed else "."))
        peer_html = f"""
<div style="border:1px solid #e5e7eb;border-radius:6px;padding:12px 14px;font-size:12.5px;color:#374151;margin-top:16px;">
  <b style="color:#0f172a;">OKR ranking (anonymized):</b> {rank_str} {detail}
  Peer identities are not disclosed.
</div>"""

    region_colors = {"NoAM": "#16a34a", "EMEA": "#f59e0b", "APJ": "#dc2626", "Global": "#7c3aed"}
    region_rows_html = ""
    max_gap_label = ""
    for r in regional_breakdown:
        color = region_colors.get(r["REGION"], "#29b5e8")
        weight = "font-weight:700;background:#f9fafb;" if r["REGION"] == "Global" else ""
        eacv_str = f"${r['EACV']/1_000_000:.2f}M" if r["EACV"] >= 1_000_000 else f"${r['EACV']/1000:.0f}K"
        region_rows_html += f"""
<tr style="{weight}"><td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;">{_h(r['REGION'])}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;text-align:right;">{r['TOTAL_UCS']}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;text-align:right;">{r['COCO_UCS']}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;text-align:right;">{r['COCO_PCT']}%</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;text-align:right;">{r['GAP']} UCs</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;text-align:right;">{eacv_str}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;">{_region_bar_html(r['COCO_PCT'], color)}</td></tr>"""
    non_global = [r for r in regional_breakdown if r["REGION"] != "Global"]
    if non_global:
        biggest = max(non_global, key=lambda r: r["GAP"])
        smallest = min(non_global, key=lambda r: r["GAP"])
        max_gap_label = (f"{biggest['REGION']} is the largest gap ({biggest['GAP']} UCs needed). "
                          f"{smallest['REGION']} is within {smallest['GAP']} UCs of target."
                          if biggest["REGION"] != smallest["REGION"] else
                          f"{biggest['REGION']} is the largest gap ({biggest['GAP']} UCs needed).")

    _STAGE_COLORS = {
        "POC": ("#fef3c7", "#92400e"),
        "Deployed": ("#dcfce7", "#166534"),
        "Implementation": ("#dbeafe", "#1e40af"),
    }

    def _stage_pill(stage_label):
        bg, fg = _STAGE_COLORS.get(stage_label, ("#e5e7eb", "#374151"))
        return (f'<span style="font-size:9px;font-weight:700;padding:1px 6px;border-radius:8px;'
                f'background:{bg};color:{fg};">{stage_label}</span>')

    gap_table_rows = ""
    for region in ["NoAM", "EMEA", "APJ"]:
        rows = gap_rows_by_region.get(region, [])
        if not rows:
            continue
        region_eacv = sum(u["eacv"] for u in rows) / 1_000_000
        gap_table_rows += (
            f'<tr style="background:#eef2ff;"><td colspan="6" style="padding:7px 10px;font-weight:700;'
            f'font-size:11px;color:#312e81;text-transform:uppercase;letter-spacing:.03em;">'
            f'{_h(region)} &mdash; {len(rows)} use case{"s" if len(rows) != 1 else ""} &middot; ${region_eacv:.2f}M EACV</td></tr>'
        )
        for u in rows:
            eacv = u["eacv"]
            eacv_str = f"${eacv/1_000_000:.2f}M" if eacv >= 1_000_000 else f"${eacv/1000:.0f}K"
            if u["skills"]:
                chip_html = "".join(
                    f'<span style="display:inline-block;background:#fff;border:1.3px solid #29b5e8;'
                    f'border-radius:4px;padding:1.5px 6px;font-size:9px;font-family:monospace;'
                    f'color:#0369a1;font-weight:700;margin:1px 2px 1px 0;">{_h(_exec_table_skill_display(s))}</span>'
                    f'<span style="font-size:9.5px;color:#64748b;display:block;margin:1px 0 3px;">'
                    f'{"; ".join(u["reasons"].get(s, []))}</span>'
                    for s in u["skills"]
                )
            else:
                chip_html = ('<span style="color:#9ca3af;font-style:italic;font-size:10.5px;">'
                             'No CoCo skill rule matched this use case&rsquo;s technical category yet</span>')
            desc = u["sanitized_desc"] or "&mdash;"
            gap_table_rows += f"""
<tr><td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{_h(u['name'])}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{_h(u['account'])}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{_stage_pill(u['stage_label'])}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;text-align:right;">{eacv_str}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;">{chip_html}</td>
  <td style="padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top;font-size:11.5px;color:#374151;">{desc if desc == "&mdash;" else _h(desc)}</td></tr>"""

    plan_html = "".join(
        f'<li style="margin-bottom:9px;"><b style="color:#0f172a;">{_h(item["title"])}:</b> {_h(item["body"])}</li>'
        for item in action_plan
    )

    return f"""<!DOCTYPE html>
<html><head><meta name="color-scheme" content="light only"></head>
<body style="color-scheme:light;background:#ffffff;font-family:-apple-system,'Hiragino Sans','Yu Gothic',Arial,sans-serif;
  max-width:860px;margin:0 auto;padding:20px;line-height:1.5;color:#1f2430;">
<div style="border:1px solid #e5e7eb;border-radius:12px;padding:20px 22px;">
  <p style="font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.06em;margin:0 0 6px;">
    {_h(partner)} &amp; Snowflake Partnership</p>
  <h1 style="margin:0 0 4px;font-size:21px;color:#0f172a;">CoCo Adoption Status</h1>
  <p style="color:#6b7280;font-size:12.5px;margin:0 0 4px;">{_h(q_start)} &ndash; {_h(q_end)} &middot; Target: {target}% CoCo Attachment</p>
  <hr style="border:none;border-top:3px solid {SNOWFLAKE_BLUE};margin:14px 0 20px;"/>

  <div style="font-size:14px;font-weight:800;color:#0f172a;margin:0 0 8px;">Adoption at a Glance</div>
  {tiles}
  {peer_html}

  <div style="font-size:14px;font-weight:800;color:#0f172a;margin:26px 0 8px;">Regional Breakdown</div>
  <div style="overflow-x:auto;">
  <table style="border-collapse:collapse;width:100%;font-size:12px;">
    <thead><tr>
      <th style="background:#f8fafc;text-align:left;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Region</th>
      <th style="background:#f8fafc;text-align:right;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Total UCs</th>
      <th style="background:#f8fafc;text-align:right;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">CoCo UCs</th>
      <th style="background:#f8fafc;text-align:right;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">CoCo %</th>
      <th style="background:#f8fafc;text-align:right;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Gap to {target}%</th>
      <th style="background:#f8fafc;text-align:right;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Total EACV</th>
      <th style="background:#f8fafc;text-align:left;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Progress</th>
    </tr></thead>
    <tbody>{region_rows_html}</tbody>
  </table>
  </div>
  <p style="font-size:12.5px;color:#4b5563;margin-top:8px;">{max_gap_label}</p>

  <div style="font-size:14px;font-weight:800;color:#0f172a;margin:26px 0 8px;">Non-CoCo Gap Opportunities</div>
  <p style="font-size:12.5px;color:#4b5563;margin:0 0 12px;">{non_coco_count} use cases &middot; ${eacv_m:.2f}M EACV awaiting CoCo attribution.</p>
  <div style="overflow-x:auto;">
  <table style="border-collapse:collapse;width:100%;font-size:12px;">
    <thead><tr>
      <th style="background:#f8fafc;text-align:left;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Use Case</th>
      <th style="background:#f8fafc;text-align:left;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Account</th>
      <th style="background:#f8fafc;text-align:left;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Stage</th>
      <th style="background:#f8fafc;text-align:right;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">EACV</th>
      <th style="background:#f8fafc;text-align:left;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">CoCo Skills (+ reason)</th>
      <th style="background:#f8fafc;text-align:left;padding:7px 10px;font-size:10.5px;text-transform:uppercase;color:#6b7280;border-bottom:2px solid #e5e7eb;">Description (sanitized)</th>
    </tr></thead>
    <tbody>{gap_table_rows}</tbody>
  </table>
  </div>

  <div style="font-size:14px;font-weight:800;color:#0f172a;margin:26px 0 8px;">Next Steps &amp; Action Plan</div>
  <ol style="padding-left:18px;font-size:12.5px;color:#374151;">{plan_html}</ol>

  <div style="margin-top:26px;padding-top:10px;border-top:1px solid #e5e7eb;font-size:10px;color:#9ca3af;">
    Generated by Snowflake PSE on {_h(datetime.now().strftime('%B %d, %Y'))}.
  </div>
</div>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# PDF renderer — reportlab, ported from coco-partner-adoption's ceo_report.py
# ─────────────────────────────────────────────────────────────────────────────

_CJK_FONT_REGISTERED = False


def _ensure_cjk_font():
    """Register a CJK-capable CID font (built into reportlab, no external
    file needed) so Japanese account/use-case names render instead of blank
    boxes. Safe to call repeatedly."""
    global _CJK_FONT_REGISTERED
    if _CJK_FONT_REGISTERED:
        return
    try:
        pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
    except Exception:
        pass
    _CJK_FONT_REGISTERED = True


def _pdf_styles():
    _ensure_cjk_font()
    styles = getSampleStyleSheet()
    blue = HexColor('#29B5E8')
    dark = HexColor('#1E3A5F')
    font = 'HeiseiKakuGo-W5'
    return {
        'title': ParagraphStyle('CustomTitle', parent=styles['Title'], fontName=font,
                                 fontSize=20, textColor=dark, spaceAfter=4, alignment=TA_LEFT),
        'subtitle': ParagraphStyle('Subtitle', parent=styles['Normal'], fontName=font,
                                    fontSize=10, textColor=HexColor('#666666'), spaceAfter=8),
        'heading2': ParagraphStyle('Heading2Custom', parent=styles['Heading2'], fontName=font,
                                    fontSize=13, textColor=dark, spaceBefore=10, spaceAfter=4),
        'body': ParagraphStyle('BodyCustom', parent=styles['Normal'], fontName=font,
                                fontSize=9.5, leading=13, alignment=TA_JUSTIFY, spaceAfter=4),
        'cell': ParagraphStyle('CellStyle', parent=styles['Normal'], fontName=font,
                                fontSize=8, leading=10, alignment=TA_LEFT),
        'cell_center': ParagraphStyle('CellStyleCenter', parent=styles['Normal'], fontName=font,
                                       fontSize=8, leading=10, alignment=TA_CENTER),
        'cell_header': ParagraphStyle('CellHeader', parent=styles['Normal'], fontName=font,
                                       fontSize=8, leading=10, alignment=TA_CENTER, textColor=white),
        'kpi_number': ParagraphStyle('KPINum', fontName=font, fontSize=22, leading=26,
                                      alignment=TA_CENTER, textColor=blue),
        'kpi_label': ParagraphStyle('KPILbl', fontName=font, fontSize=8.5, leading=11,
                                     alignment=TA_CENTER, textColor=HexColor('#666666')),
    }


def _wrap_cell(text, style):
    return Paragraph(html_lib.escape(str(text if text is not None else "")), style)


def _pdf_table_style(header_color=None):
    header_color = header_color or HexColor('#29B5E8')
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CCCCCC')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#F5F5F5')]),
    ])


def _pdf_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(HexColor('#999999'))
    canvas.drawCentredString(letter[0] / 2, 0.4 * inch,
                              f"Generated by Snowflake PSE on {datetime.now().strftime('%B %d, %Y')}")
    canvas.drawRightString(letter[0] - 0.5 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _build_report_pdf_bytes(partner, q_start, q_end, target, coco_count, total_ucs, coco_pct,
                             non_coco_count, non_coco_eacv, peer_benchmark, regional_breakdown,
                             gap_rows_by_region, action_plan) -> bytes:
    styles = _pdf_styles()
    cell, cell_c, cell_h = styles['cell'], styles['cell_center'], styles['cell_header']

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.5 * inch,
                             leftMargin=0.5 * inch, topMargin=0.5 * inch, bottomMargin=0.6 * inch)
    story = []

    story.append(Paragraph(f"{partner} &amp; Snowflake Partnership", styles['subtitle']))
    story.append(Paragraph("CoCo Adoption Status", styles['title']))
    story.append(Paragraph(f"{q_start} &ndash; {q_end} &middot; Target: {target}% CoCo Attachment", styles['subtitle']))
    story.append(Spacer(1, 0.15 * inch))

    eacv_m = non_coco_eacv / 1_000_000
    kpi_data = [
        [Paragraph(f"{coco_pct}%", styles['kpi_number']), Paragraph(f"{coco_count} of {total_ucs}", styles['kpi_number']),
         Paragraph(str(non_coco_count), styles['kpi_number']), Paragraph(f"${eacv_m:.2f}M", styles['kpi_number'])],
        [Paragraph("CoCo attach rate", styles['kpi_label']), Paragraph("CoCo use cases", styles['kpi_label']),
         Paragraph("Awaiting confirmation", styles['kpi_label']), Paragraph("EACV awaiting", styles['kpi_label'])],
    ]
    kpi_table = Table(kpi_data, colWidths=[1.7 * inch] * 4)
    kpi_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.15 * inch))

    if peer_benchmark:
        gap = round(peer_benchmark["target"] - coco_pct, 1)
        global_row = next((r for r in regional_breakdown if r["REGION"] == "Global"), None)
        ucs_needed = global_row["GAP"] if global_row else 0
        rank_str = (f"{partner} ranks <b>{peer_benchmark['rank']} of {peer_benchmark['total_in_group']}</b> "
                    f"{peer_benchmark['group_label']} on OKR attainment")
        if gap <= 0:
            detail = f"and has already hit the {peer_benchmark['target']}% target &mdash; great work keeping pace!"
        else:
            detail = (f", sitting <b>{gap} points</b> behind the {peer_benchmark['target']}% target"
                      + (f", closing this gap requires <b>{ucs_needed} more</b> CoCo-attached use cases this quarter."
                         if ucs_needed else "."))
        story.append(Paragraph(
            f"<b>OKR ranking (anonymized):</b> {rank_str} {detail} Peer identities are not disclosed.",
            styles['body']))
        story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Regional Breakdown", styles['heading2']))
    region_header = [_wrap_cell(t, cell_h) for t in
                      ["Region", "Total UCs", "CoCo UCs", "CoCo %", f"Gap to {target}%", "Total EACV"]]
    region_data = [region_header]
    for r in regional_breakdown:
        eacv_str = f"${r['EACV']/1_000_000:.2f}M" if r["EACV"] >= 1_000_000 else f"${r['EACV']/1000:.0f}K"
        region_data.append([
            _wrap_cell(r["REGION"], cell), _wrap_cell(r["TOTAL_UCS"], cell_c), _wrap_cell(r["COCO_UCS"], cell_c),
            _wrap_cell(f"{r['COCO_PCT']}%", cell_c), _wrap_cell(f"{r['GAP']} UCs", cell_c), _wrap_cell(eacv_str, cell_c),
        ])
    region_table = Table(region_data, colWidths=[1.1 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 1.1 * inch, 1.1 * inch])
    region_table.setStyle(_pdf_table_style())
    story.append(region_table)
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Non-CoCo Gap Opportunities", styles['heading2']))
    for region in ["NoAM", "EMEA", "APJ"]:
        rows = gap_rows_by_region.get(region, [])
        if not rows:
            continue
        region_eacv = sum(u["eacv"] for u in rows) / 1_000_000
        story.append(Paragraph(
            f"<b>{region}</b> &mdash; {len(rows)} use case{'s' if len(rows) != 1 else ''} &middot; ${region_eacv:.2f}M EACV",
            ParagraphStyle('RegionHead', parent=styles['body'], textColor=HexColor('#312e81'), spaceAfter=3)))
        gap_header = [_wrap_cell(t, cell_h) for t in
                      ["Use Case", "Account", "Stage", "EACV", "CoCo Skills (+ reason)", "Description (sanitized)"]]
        gap_data = [gap_header]
        for u in rows:
            eacv = u["eacv"]
            eacv_str = f"${eacv/1_000_000:.2f}M" if eacv >= 1_000_000 else f"${eacv/1000:.0f}K"
            if u["skills"]:
                skill_txt = "<br/>".join(
                    f"<b>{_exec_table_skill_display(s)}</b>: {'; '.join(u['reasons'].get(s, []))}"
                    for s in u["skills"]
                )
            else:
                skill_txt = "No CoCo skill rule matched yet"
            gap_data.append([
                Paragraph(html_lib.escape(u["name"]), cell), Paragraph(html_lib.escape(u["account"]), cell),
                Paragraph(u["stage_label"], cell_c), Paragraph(eacv_str, cell_c),
                Paragraph(skill_txt, cell), Paragraph(html_lib.escape(u["sanitized_desc"] or "-"), cell),
            ])
        gap_table = Table(gap_data, colWidths=[1.4 * inch, 1.1 * inch, 0.7 * inch, 0.6 * inch, 1.6 * inch, 1.6 * inch],
                           repeatRows=1)
        gap_table.setStyle(_pdf_table_style())
        story.append(gap_table)
        story.append(Spacer(1, 0.1 * inch))

    story.append(PageBreak())
    story.append(Paragraph("Next Steps &amp; Action Plan", styles['heading2']))
    for i, item in enumerate(action_plan, start=1):
        story.append(Paragraph(f"{i}. <b>{item['title']}:</b> {item['body']}", styles['body']))

    doc.build(story, onFirstPage=_pdf_footer, onLaterPages=_pdf_footer)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────

if get_env() not in ("dev",):
    st.warning("This page is only available in the DEV environment.")
    st.stop()

conn = st.session_state.conn

st.title(":material/forward_to_inbox: PSE Email (Hybrid Layout)")
st.caption(
    "Personal narrative (copy as rich text) plus an executive-table CoCo adoption report "
    "(copy as rich text, download as HTML, or download as PDF) for the selected partner."
)

q_start = str(st.session_state.get("okr_start_date", date(2026, 8, 1)))
q_end = str(st.session_state.get("okr_end_date", date(2026, 10, 31)))
include_account_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter = st.session_state.get("confidence_filter", ["High"])
confidence = "High" if confidence_filter == ["High"] else ("Medium" if confidence_filter else None)

_ALIAS_SECONDARIES = {"Ernst & Young (EY)", "IBM Consulting", "Kipi.ai", "LTI Mindtree"}
partner_options = sorted(set(MANAGED_PARTNERS) - _ALIAS_SECONDARIES)

selected_partner = st.selectbox(
    "Select Partner", options=partner_options, index=None,
    placeholder="Choose a managed partner…", key="_pse_hybrid_partner_select",
)

if not selected_partner:
    st.info("Select a partner above to load their use cases.")
    st.stop()

with st.spinner("Loading use cases…"):
    detail = get_okr_coco_adoption(
        conn, q_start, q_end, region=None,
        include_account_coco=include_account_coco, confidence=confidence,
    ).copy()
    detail["PARTNER_NAME"] = detail["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
    detail = detail[detail["PARTNER_NAME"] == selected_partner].copy()

if len(detail) == 0:
    st.warning(f"No use cases found for **{selected_partner}** in this date range.")
    st.stop()

if include_account_coco:
    conf_scores = get_usecase_confidence_scores(conn, selected_partner, q_start, q_end)
    if len(conf_scores) > 0:
        conf_map = conf_scores[["USE_CASE_ID", "CONFIDENCE_BAND"]].set_index("USE_CASE_ID")
        detail["CONFIDENCE_BAND"] = detail["USE_CASE_ID"].map(conf_map["CONFIDENCE_BAND"])
        bands = confidence_filter or ["High", "Medium", "Low"]
        is_flag = detail["COCO_SOURCE"].notna()
        has_conf = detail["CONFIDENCE_BAND"].isin(bands)
        detail["IS_COCO_ATTACHED"] = is_flag | has_conf

non_coco = detail[detail["IS_COCO_ATTACHED"] == False].copy()
coco_ucs = detail[detail["IS_COCO_ATTACHED"] == True].copy()

total_ucs = len(detail)
coco_count = len(coco_ucs)
non_coco_count = len(non_coco)
coco_pct = round(coco_count * 100.0 / total_ucs, 1) if total_ucs > 0 else 0.0
non_coco_eacv = non_coco["USE_CASE_EACV"].sum()

_apj_emea_latam = set(APJ_RSI_REGION_MAP) | set(EMEA_RSI_REGION_MAP) | set(LATAM_RSI_REGION_MAP)
target = 50 if selected_partner in _apj_emea_latam else 75

c1, c2, c3, c4 = st.columns(4)
c1.metric("CoCo Attach Rate", f"{coco_pct}%", f"{'MET' if coco_pct >= target else 'BELOW'} {target}% target")
c2.metric("CoCo Attached", f"{coco_count} of {total_ucs}")
c3.metric("Awaiting Confirmation", non_coco_count)
c4.metric("EACV Awaiting", f"${non_coco_eacv/1_000_000:.2f}M")

st.divider()

# ── Part 1: Narrative ───────────────────────────────────────────────────────
st.subheader(":material/edit_note: Part 1 — Personal Narrative")
recipients = st.text_input("Recipients", placeholder="e.g. Sree / Adnan", key="_pse_hybrid_recipients")

if st.button(":material/auto_awesome: Generate Narrative Draft", key="_pse_hybrid_gen_narrative"):
    with st.spinner("Computing benchmark and drafting narrative…"):
        peer_benchmark = _compute_peer_benchmark(conn, selected_partner, q_start, q_end, coco_pct)
        regional_breakdown, max_gap_region = _compute_regional_breakdown(detail, target)
        noam_preview_rows = _group_non_coco_by_region(non_coco)
        # Ground the NoAM ask with a real skill rationale too -- scoped to just
        # the top 4 NoAM UCs actually referenced in the letter, so this stays
        # cheap even though it's a real AI call (not the fast-only path).
        noam_top = sorted(noam_preview_rows.get("NoAM", []), key=lambda x: x["eacv"], reverse=True)[:4]
        if noam_top:
            noam_items = [(r["uc_id"], r["raw_desc"], r["raw_se_comments"], r["raw_partner_comments"], r["skills"])
                          for r in noam_top]
            noam_sanitized = _sanitize_descriptions_batch(conn, noam_items)
            for r in noam_top:
                entry = noam_sanitized.get(r["uc_id"], {"rationale": "", "additional_skills": {}})
                r["skill_rationale"] = entry.get("rationale", "")
                r["skills"], r["reasons"] = merge_additional_skills(
                    r["skills"], r["reasons"], entry.get("additional_skills", {})
                )
                r["skills"], r["reasons"] = apply_aim_override(r["skills"], r["reasons"], r["aim_source"])
                r["skills"], r["reasons"] = cap_skills(r["skills"], r["reasons"])
        narrative = _build_narrative_draft(
            conn, selected_partner, recipients, coco_pct, coco_count, total_ucs,
            peer_benchmark, regional_breakdown, max_gap_region, noam_preview_rows,
            datetime.now().strftime("%B %d, %Y"),
        )
    st.session_state["_pse_hybrid_narrative_text"] = narrative
    st.session_state["_pse_hybrid_narrative_partner"] = selected_partner

if st.session_state.get("_pse_hybrid_narrative_partner") == selected_partner:
    narrative_text = st.text_area(
        "Edit narrative before sending", value=st.session_state.get("_pse_hybrid_narrative_text", ""),
        height=260, key="_pse_hybrid_narrative_edit",
    )
    st.session_state["_pse_hybrid_narrative_text"] = narrative_text
    if narrative_text.strip():
        narrative_html = _build_narrative_html(narrative_text, selected_partner)
        copy_rich_text_button(narrative_html, narrative_text, button_id="pseHybridNarrativeCopy")
        with st.expander("Preview narrative", expanded=False):
            components.html(narrative_html, height=340, scrolling=True)

st.divider()

# ── Part 2: Report ──────────────────────────────────────────────────────────
st.subheader(":material/table_chart: Part 2 — Executive Table Report")

if non_coco_count == 0:
    st.success(f"All {total_ucs} use cases already have CoCo attached for {selected_partner}!")
else:
    with st.expander(f"Non-CoCo Opportunities ({non_coco_count} use cases)", expanded=False):
        _preview_cols = ["USE_CASE_NUMBER", "USE_CASE_NAME", "ACCOUNT_NAME",
                         "THEATER_NAME", "USE_CASE_STAGE", "USE_CASE_EACV", "TECHNICAL_USE_CASE"]
        _avail = [c for c in _preview_cols if c in non_coco.columns]
        _preview = non_coco[_avail].copy()
        if "USE_CASE_STAGE" in _preview.columns:
            _preview["USE_CASE_STAGE"] = _preview["USE_CASE_STAGE"].str.extract(r"^(\d+)").iloc[:, 0]
        if "USE_CASE_EACV" in _preview.columns:
            _preview["USE_CASE_EACV"] = non_coco["USE_CASE_EACV"].apply(
                lambda x: f"${x/1_000_000:.2f}M" if x >= 1_000_000 else f"${x/1000:.0f}K"
            )
        st.dataframe(_preview, hide_index=True, use_container_width=True,
                     height=38 + 35 * min(non_coco_count, 20))

    if st.button(f":material/auto_awesome: Generate Report for {non_coco_count} Use Cases",
                 type="primary", use_container_width=True, key="_pse_hybrid_gen_report"):
        with st.spinner("Computing peer benchmark and regional breakdown…"):
            peer_benchmark = _compute_peer_benchmark(conn, selected_partner, q_start, q_end, coco_pct)
            regional_breakdown, _ = _compute_regional_breakdown(detail, target)
        with st.spinner(f"Mapping CoCo skills and sanitizing descriptions for {non_coco_count} use cases…"):
            gap_rows_by_region = _build_gap_table_rows(conn, non_coco)
        action_plan = _build_action_plan(regional_breakdown, gap_rows_by_region, selected_partner)

        report_html = _build_report_html(
            selected_partner, q_start, q_end, target, coco_count, total_ucs, coco_pct,
            non_coco_count, non_coco_eacv, peer_benchmark, regional_breakdown,
            gap_rows_by_region, action_plan,
        )
        with st.spinner("Building PDF…"):
            report_pdf = _build_report_pdf_bytes(
                selected_partner, q_start, q_end, target, coco_count, total_ucs, coco_pct,
                non_coco_count, non_coco_eacv, peer_benchmark, regional_breakdown,
                gap_rows_by_region, action_plan,
            )

        st.session_state["_pse_hybrid_report_html"] = report_html
        st.session_state["_pse_hybrid_report_pdf"] = report_pdf
        st.session_state["_pse_hybrid_report_partner"] = selected_partner

    if st.session_state.get("_pse_hybrid_report_partner") == selected_partner:
        _html = st.session_state["_pse_hybrid_report_html"]
        _pdf = st.session_state["_pse_hybrid_report_pdf"]

        col1, col2, col3 = st.columns(3)
        with col1:
            copy_rich_text_button(_html, "", button_id="pseHybridReportCopy")
        with col2:
            st.download_button(
                ":material/download: Download as HTML", data=_html,
                file_name=f"PSE_CoCo_Report_{selected_partner.replace(' ', '_')}.html",
                mime="text/html", use_container_width=True,
            )
        with col3:
            st.download_button(
                ":material/picture_as_pdf: Download as PDF", data=_pdf,
                file_name=f"PSE_CoCo_Report_{selected_partner.replace(' ', '_')}.pdf",
                mime="application/pdf", use_container_width=True,
            )

        st.divider()
        components.html(_html, height=1400, scrolling=True)
