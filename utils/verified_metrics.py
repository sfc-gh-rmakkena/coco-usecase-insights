"""
Programmatic metric resolution for Ask AI.

Fetches exact numbers directly from query functions — bypassing LLM SQL
generation for the most common metric questions (CoCo counts, EACV,
tokens, credits, target, stage, theatre, region, attribution, WoW).

Entry point: get_verified_answer(conn, question, intent)
"""
import pandas as pd
import streamlit as st

from utils import (
    apply_coco_final,
    PARTNER_ALIASES,
    PARTNER_RENAME_MAP,
    resolve_partner_filter,
    PARTNER_GROUPS,
    filter_out_partner_own_accounts,
)

# ── Quarter date boundaries ───────────────────────────────────────────────────
QUARTERS = {
    "q1":  {"start": "2026-02-01", "end": "2026-04-30", "label": "Q1 FY27 (Feb–Apr 2026)"},
    "q2":  {"start": "2026-05-01", "end": "2026-07-31", "label": "Q2 FY27 (May–Jul 2026)"},
    "q3":  {"start": "2026-08-01", "end": "2026-10-31", "label": "Q3 FY27 (Aug–Oct 2026)"},
    "ytd": {"start": "2026-02-01", "end": "2026-10-31", "label": "YTD FY27 (Feb–Oct 2026)"},
}

# ── Group → raw partner names (from PARTNER_ALIASES) ─────────────────────────
_GROUP_KEY_MAP = {
    "GSI":  "--- GSIs ---",
    "NOAM": "--- NOAM RSIs ---",
    "APJ":  "--- APJ RSIs ---",
    "EMEA": "--- EMEA RSIs ---",
}
GROUP_RAW_NAMES = {
    group: set(PARTNER_ALIASES.get(key, []))
    for group, key in _GROUP_KEY_MAP.items()
}

# Canonical names per group (after PARTNER_RENAME_MAP)
GROUP_CANONICAL = {
    group: {PARTNER_RENAME_MAP.get(n, n) for n in raw}
    for group, raw in GROUP_RAW_NAMES.items()
}

GROUP_TARGETS = {"GSI": 75, "NOAM": 75, "APJ": 50, "EMEA": 50}
DEFAULT_TARGET = 50


# ── Quarter bulk cache ────────────────────────────────────────────────────────

def get_quarter_bulk(conn, quarter: str) -> pd.DataFrame:
    """
    Return apply_coco_final(bulk_conf) for the given quarter.
    Cached in st.session_state so the heavy query runs at most once per session.
    """
    cache_key = f"_vmet_bulk_{quarter}"
    if cache_key not in st.session_state:
        from utils.queries import get_bulk_confidence_scores
        q = QUARTERS[quarter]
        partners = tuple(resolve_partner_filter(list(PARTNER_GROUPS)))
        bulk = get_bulk_confidence_scores(conn, partners, q["start"], q["end"])
        if len(bulk) > 0:
            bulk = bulk.copy()
            bulk["PARTNER_NAME"] = bulk["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
            bulk["IS_COCO_FINAL"] = apply_coco_final(bulk, ["High"])
        st.session_state[cache_key] = bulk
    return st.session_state[cache_key]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _filter_entity(df: pd.DataFrame, partner: str = None, group: str = None) -> pd.DataFrame:
    if partner:
        return df[df["PARTNER_NAME"] == partner]
    if group and group in GROUP_CANONICAL:
        return df[df["PARTNER_NAME"].isin(GROUP_CANONICAL[group])]
    return df


def _to_float(series, col):
    if col not in series.columns:
        return pd.Series([0.0] * len(series))
    return pd.to_numeric(series[col], errors="coerce").fillna(0)


def _fmt_num(n, fmt=",.0f") -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "N/A"
    return format(float(n), fmt)


def _fmt_pct(n) -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "N/A"
    return f"{float(n):.1f}%"


def _fmt_money(n) -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "N/A"
    v = float(n)
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def _fmt_tokens(n) -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "N/A"
    v = float(n)
    if abs(v) >= 1e9:
        return f"{v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"{v/1e6:.1f}M"
    return f"{v:,.0f}"


# ── Metric resolvers ──────────────────────────────────────────────────────────

def resolve_coco_count(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub = _filter_entity(df, partner, group)
    if len(sub) == 0:
        return {"text": "No data found for the specified filters."}

    total = len(sub)
    coco  = int(sub["IS_COCO_FINAL"].sum())
    pct   = round(coco * 100.0 / total, 1) if total else 0.0
    eacv  = float(_to_float(sub[sub["IS_COCO_FINAL"]], "USE_CASE_EACV").sum()) if "USE_CASE_EACV" in sub.columns else None

    header = (
        f"Total UCs: {_fmt_num(total)} | CoCo UCs (IS_COCO_FINAL): {coco} ({_fmt_pct(pct)})"
        + (f" | CoCo EACV: {_fmt_money(eacv)}" if eacv is not None else "")
    )

    if partner:
        return {"total_ucs": total, "coco_ucs": coco, "coco_pct": pct, "coco_eacv": eacv, "text": header}

    # Group/global — per-partner breakdown
    by_p = sub.groupby("PARTNER_NAME").agg(
        TOTAL_UCS=("USE_CASE_ID", "count"),
        COCO_UCS=("IS_COCO_FINAL", "sum"),
    ).reset_index()
    if "USE_CASE_EACV" in sub.columns:
        eacv_by = sub[sub["IS_COCO_FINAL"]].groupby("PARTNER_NAME")["USE_CASE_EACV"].sum().reset_index(name="COCO_EACV")
        by_p = by_p.merge(eacv_by, on="PARTNER_NAME", how="left").fillna(0)
    by_p["COCO_PCT"] = (by_p["COCO_UCS"] * 100.0 / by_p["TOTAL_UCS"].replace(0, float("nan"))).round(1).fillna(0)
    by_p = by_p.sort_values("COCO_PCT", ascending=False)

    lines = "\n".join(
        f"  {r['PARTNER_NAME']}: {int(r['COCO_UCS'])}/{int(r['TOTAL_UCS'])} ({r['COCO_PCT']:.1f}%)"
        for _, r in by_p.iterrows()
    )
    return {
        "total_ucs": total, "coco_ucs": coco, "coco_pct": pct, "coco_eacv": eacv,
        "by_partner": by_p,
        "text": f"{header}\n\nPer partner:\n{lines}",
    }


def resolve_eacv(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub = _filter_entity(df, partner, group)
    if len(sub) == 0 or "USE_CASE_EACV" not in sub.columns:
        return {"text": "No EACV data found."}

    total_eacv = float(_to_float(sub, "USE_CASE_EACV").sum())
    coco_eacv  = float(_to_float(sub[sub["IS_COCO_FINAL"]], "USE_CASE_EACV").sum())
    header = f"Total EACV: {_fmt_money(total_eacv)} | CoCo EACV: {_fmt_money(coco_eacv)}"

    if partner:
        return {"total_eacv": total_eacv, "coco_eacv": coco_eacv, "text": header}

    by_p = sub.groupby("PARTNER_NAME").agg(TOTAL_EACV=("USE_CASE_EACV", "sum")).reset_index()
    coco_by = (sub[sub["IS_COCO_FINAL"]].groupby("PARTNER_NAME")["USE_CASE_EACV"].sum()
               .reset_index(name="COCO_EACV"))
    by_p = by_p.merge(coco_by, on="PARTNER_NAME", how="left").fillna(0)
    by_p = by_p.sort_values("COCO_EACV", ascending=False)

    lines = "\n".join(
        f"  {r['PARTNER_NAME']}: CoCo {_fmt_money(r['COCO_EACV'])} / Total {_fmt_money(r['TOTAL_EACV'])}"
        for _, r in by_p.iterrows()
    )
    return {
        "total_eacv": total_eacv, "coco_eacv": coco_eacv, "by_partner": by_p,
        "text": f"{header}\n\nPer partner:\n{lines}",
    }


def resolve_tokens(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub   = _filter_entity(df, partner, group)

    # If partner/group has no rows at all in the dataset
    if len(sub) == 0:
        entity = partner or (f"{group} partners" if group else "all managed partners")
        return {"text": f"No use cases found for {entity} in this quarter's dataset."}

    coco  = sub[sub["IS_COCO_FINAL"]].copy()

    # Partner present but no IS_COCO_FINAL rows → report explicitly
    if len(coco) == 0:
        entity = partner or (f"{group} partners" if group else "managed partners")
        total_ucs = len(sub)
        return {"text": f"{entity} has {total_ucs} total UC(s) in this period but 0 qualify as IS_COCO_FINAL — no token data available."}

    coco  = filter_out_partner_own_accounts(coco) if len(coco) > 0 else coco

    if "Q2_TOKENS" not in coco.columns:
        return {"text": "Token data not available (Q2_TOKENS column missing from dataset)."}

    dedup = coco.drop_duplicates(["PARTNER_NAME", "ACCOUNT_NAME_UPPER"]) if "ACCOUNT_NAME_UPPER" in coco.columns else coco
    for c in ["Q2_TOKENS", "LAST7_TOKENS", "PRIOR7_TOKENS"]:
        if c in dedup.columns:
            dedup = dedup.copy()
            dedup[c] = pd.to_numeric(dedup[c], errors="coerce").fillna(0)

    total_tokens = float(dedup["Q2_TOKENS"].sum())
    l7  = float(dedup["LAST7_TOKENS"].sum())  if "LAST7_TOKENS"  in dedup.columns else None
    p7  = float(dedup["PRIOR7_TOKENS"].sum()) if "PRIOR7_TOKENS" in dedup.columns else None
    wow = round((l7 - p7) / p7 * 100, 1) if (p7 and p7 > 0) else None

    coco_uc_count = len(dedup)
    header = (
        f"IS_COCO_FINAL accounts: {coco_uc_count} | "
        f"Tokens: {_fmt_tokens(total_tokens)}"
        + (f" | Last 7d: {_fmt_tokens(l7)}" if l7 else "")
        + (f" | WoW: {wow:+.1f}%" if wow is not None else "")
    )

    if partner:
        return {"total_tokens": total_tokens, "last7": l7, "prior7": p7, "wow_pct": wow, "text": header}

    by_p = dedup.groupby("PARTNER_NAME").agg(
        TOKENS=("Q2_TOKENS", "sum"),
        LAST7=("LAST7_TOKENS", "sum")  if "LAST7_TOKENS"  in dedup.columns else ("Q2_TOKENS", "count"),
        PRIOR7=("PRIOR7_TOKENS", "sum") if "PRIOR7_TOKENS" in dedup.columns else ("Q2_TOKENS", "count"),
    ).reset_index()
    by_p["WOW_PCT"] = ((by_p["LAST7"] - by_p["PRIOR7"]) / by_p["PRIOR7"].replace(0, float("nan")) * 100).round(1)
    by_p = by_p.sort_values("TOKENS", ascending=False)

    lines = "\n".join(
        f"  {r['PARTNER_NAME']}: {_fmt_tokens(r['TOKENS'])}"
        + (f" (WoW: {r['WOW_PCT']:+.1f}%)" if not pd.isna(r.get("WOW_PCT")) else "")
        for _, r in by_p.iterrows()
    )
    return {
        "total_tokens": total_tokens, "by_partner": by_p,
        "text": f"{header}\n\nPer partner:\n{lines}",
    }


def resolve_credits(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub  = _filter_entity(df, partner, group)

    if len(sub) == 0:
        entity = partner or (f"{group} partners" if group else "all managed partners")
        return {"text": f"No use cases found for {entity} in this quarter's dataset."}

    coco = sub[sub["IS_COCO_FINAL"]].copy()

    if len(coco) == 0:
        entity = partner or (f"{group} partners" if group else "managed partners")
        return {"text": f"{entity} has {len(sub)} total UC(s) but 0 qualify as IS_COCO_FINAL — no credit data available."}

    coco = filter_out_partner_own_accounts(coco) if len(coco) > 0 else coco

    if "Q2_CREDITS" not in coco.columns:
        return {"text": "Credit data not available (Q2_CREDITS column missing)."}

    dedup = coco.drop_duplicates(["PARTNER_NAME", "ACCOUNT_NAME_UPPER"]) if "ACCOUNT_NAME_UPPER" in coco.columns else coco
    for c in ["Q2_CREDITS", "LAST7_CREDITS", "PRIOR7_CREDITS"]:
        if c in dedup.columns:
            dedup = dedup.copy()
            dedup[c] = pd.to_numeric(dedup[c], errors="coerce").fillna(0)

    total_cred = float(dedup["Q2_CREDITS"].sum())
    l7  = float(dedup["LAST7_CREDITS"].sum())  if "LAST7_CREDITS"  in dedup.columns else None
    p7  = float(dedup["PRIOR7_CREDITS"].sum()) if "PRIOR7_CREDITS" in dedup.columns else None
    wow = round((l7 - p7) / p7 * 100, 1) if (p7 and p7 > 0) else None

    coco_uc_count = len(dedup)
    header = (
        f"IS_COCO_FINAL accounts: {coco_uc_count} | "
        f"Credits: {_fmt_money(total_cred)}"
        + (f" | Last 7d: {_fmt_money(l7)}" if l7 else "")
        + (f" | WoW: {wow:+.1f}%" if wow is not None else "")
    )

    if partner:
        return {"total_credits": total_cred, "last7": l7, "prior7": p7, "wow_pct": wow, "text": header}

    by_p = dedup.groupby("PARTNER_NAME").agg(
        CREDITS=("Q2_CREDITS", "sum"),
        LAST7=("LAST7_CREDITS", "sum")  if "LAST7_CREDITS"  in dedup.columns else ("Q2_CREDITS", "count"),
        PRIOR7=("PRIOR7_CREDITS", "sum") if "PRIOR7_CREDITS" in dedup.columns else ("Q2_CREDITS", "count"),
    ).reset_index()
    by_p["WOW_PCT"] = ((by_p["LAST7"] - by_p["PRIOR7"]) / by_p["PRIOR7"].replace(0, float("nan")) * 100).round(1)
    by_p = by_p.sort_values("CREDITS", ascending=False)

    lines = "\n".join(
        f"  {r['PARTNER_NAME']}: {_fmt_money(r['CREDITS'])}"
        + (f" (WoW: {r['WOW_PCT']:+.1f}%)" if not pd.isna(r.get("WOW_PCT")) else "")
        for _, r in by_p.iterrows()
    )
    return {
        "total_credits": total_cred, "by_partner": by_p,
        "text": f"{header}\n\nPer partner:\n{lines}",
    }


def resolve_target(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub = _filter_entity(df, partner, group)
    if len(sub) == 0:
        return {"text": "No data found."}

    target = GROUP_TARGETS.get(group, DEFAULT_TARGET)

    by_p = sub.groupby("PARTNER_NAME").agg(
        TOTAL_UCS=("USE_CASE_ID", "count"),
        COCO_UCS=("IS_COCO_FINAL", "sum"),
    ).reset_index()
    by_p["COCO_PCT"]      = (by_p["COCO_UCS"] * 100.0 / by_p["TOTAL_UCS"].replace(0, float("nan"))).round(1).fillna(0)
    by_p["MEETS_TARGET"]  = by_p["COCO_PCT"] >= target
    by_p["GAP_UCS"]       = ((by_p["TOTAL_UCS"] * target / 100.0) - by_p["COCO_UCS"]).apply(lambda x: max(0, int(x + 0.9999)))

    if partner:
        row = by_p.iloc[0] if len(by_p) > 0 else None
        if row is None:
            return {"text": "No data."}
        meets = bool(row["MEETS_TARGET"])
        gap   = int(row["GAP_UCS"])
        return {
            "meets_target": meets, "coco_pct": float(row["COCO_PCT"]),
            "gap": gap, "target": target,
            "text": (
                f"CoCo %: {row['COCO_PCT']:.1f}% vs {target}% target — "
                + ("MEETING TARGET ✓" if meets else f"BELOW TARGET — needs {gap} more CoCo UC(s)")
            ),
        }

    meeting     = int(by_p["MEETS_TARGET"].sum())
    total_p     = len(by_p)
    not_meeting = total_p - meeting

    below = by_p[~by_p["MEETS_TARGET"]].sort_values("COCO_PCT", ascending=False)
    above = by_p[by_p["MEETS_TARGET"]].sort_values("COCO_PCT", ascending=False)

    below_lines = "\n".join(
        f"  {r['PARTNER_NAME']}: {r['COCO_PCT']:.1f}% (needs {int(r['GAP_UCS'])} more)"
        for _, r in below.iterrows()
    )
    above_lines = "\n".join(
        f"  {r['PARTNER_NAME']}: {r['COCO_PCT']:.1f}%"
        for _, r in above.iterrows()
    )
    text = (
        f"Target: {target}% | Meeting: {meeting}/{total_p} partners | Below: {not_meeting}\n\n"
        + (f"Meeting target:\n{above_lines}\n\n" if above_lines else "")
        + (f"Below target:\n{below_lines}" if below_lines else "All partners meeting target!")
    )
    return {"meeting": meeting, "not_meeting": not_meeting, "total": total_p, "target": target, "text": text}


def resolve_stage(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub = _filter_entity(df, partner, group)
    if len(sub) == 0 or "USE_CASE_STAGE" not in sub.columns:
        return {"text": "No stage data found."}

    by_s = sub.groupby("USE_CASE_STAGE").agg(
        TOTAL=("USE_CASE_ID", "count"),
        COCO=("IS_COCO_FINAL", "sum"),
    ).reset_index().sort_values("USE_CASE_STAGE")
    by_s["COCO_PCT"] = (by_s["COCO"] * 100.0 / by_s["TOTAL"].replace(0, float("nan"))).round(1).fillna(0)

    lines = "\n".join(
        f"  {r['USE_CASE_STAGE']}: {int(r['COCO'])}/{int(r['TOTAL'])} CoCo ({r['COCO_PCT']:.1f}%)"
        for _, r in by_s.iterrows()
    )
    total = len(sub)
    coco  = int(sub["IS_COCO_FINAL"].sum())
    return {"by_stage": by_s, "text": f"Overall: {coco}/{total} CoCo | Stage breakdown:\n{lines}"}


def resolve_theatre(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub = _filter_entity(df, partner, group)
    if len(sub) == 0 or "THEATER_NAME" not in sub.columns:
        return {"text": "Theatre data not available."}

    by_t = sub.groupby("THEATER_NAME").agg(
        TOTAL=("USE_CASE_ID", "count"),
        COCO=("IS_COCO_FINAL", "sum"),
    ).reset_index()
    by_t["COCO_PCT"] = (by_t["COCO"] * 100.0 / by_t["TOTAL"].replace(0, float("nan"))).round(1).fillna(0)

    # Token rollup per theatre (deduplicated)
    coco_sub = sub[sub["IS_COCO_FINAL"]].copy()
    if "ACCOUNT_NAME_UPPER" in coco_sub.columns and "Q2_TOKENS" in coco_sub.columns:
        dedup = coco_sub.drop_duplicates(["THEATER_NAME", "ACCOUNT_NAME_UPPER"])
        dedup["Q2_TOKENS"] = pd.to_numeric(dedup["Q2_TOKENS"], errors="coerce").fillna(0)
        tok = dedup.groupby("THEATER_NAME")["Q2_TOKENS"].sum().reset_index(name="TOKENS")
        by_t = by_t.merge(tok, on="THEATER_NAME", how="left").fillna(0)

    lines = "\n".join(
        f"  {r['THEATER_NAME']}: {int(r['COCO'])}/{int(r['TOTAL'])} CoCo ({r['COCO_PCT']:.1f}%)"
        + (f" | Tokens: {_fmt_tokens(r['TOKENS'])}" if "TOKENS" in r.index else "")
        for _, r in by_t.iterrows()
    )
    return {"by_theatre": by_t, "text": f"Theatre breakdown:\n{lines}"}


def resolve_region(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub = _filter_entity(df, partner, group)
    col = next((c for c in ["REGION_NAME", "THEATER_NAME"] if c in sub.columns), None)
    if col is None or len(sub) == 0:
        return {"text": "Region data not available."}

    by_r = sub.groupby(col).agg(
        TOTAL=("USE_CASE_ID", "count"),
        COCO=("IS_COCO_FINAL", "sum"),
    ).reset_index()
    by_r["COCO_PCT"] = (by_r["COCO"] * 100.0 / by_r["TOTAL"].replace(0, float("nan"))).round(1).fillna(0)

    lines = "\n".join(
        f"  {r[col]}: {int(r['COCO'])}/{int(r['TOTAL'])} CoCo ({r['COCO_PCT']:.1f}%)"
        for _, r in by_r.iterrows()
    )
    return {"by_region": by_r, "text": f"Region breakdown:\n{lines}"}


def resolve_attribution(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub  = _filter_entity(df, partner, group)
    coco = sub[sub["IS_COCO_FINAL"]]
    if len(coco) == 0 or "COCO_SOURCE" not in coco.columns:
        return {"text": "Attribution data not available."}

    counts = coco["COCO_SOURCE"].fillna("Account-Level").value_counts()
    total  = len(coco)
    lines  = "\n".join(f"  {src}: {cnt} ({cnt*100/total:.1f}%)" for src, cnt in counts.items())
    return {"counts": counts, "text": f"CoCo attribution sources ({total} CoCo UCs):\n{lines}"}


def resolve_confidence(df: pd.DataFrame, partner=None, group=None) -> dict:
    sub = _filter_entity(df, partner, group)
    if len(sub) == 0 or "CONFIDENCE_BAND" not in sub.columns:
        return {"text": "Confidence band data not available."}

    counts = sub["CONFIDENCE_BAND"].value_counts()
    total  = len(sub)
    lines  = "\n".join(f"  {band}: {cnt} ({cnt*100/total:.1f}%)" for band, cnt in counts.items())
    return {"counts": counts, "text": f"Confidence bands ({total} UCs):\n{lines}"}


def resolve_wow(conn, df: pd.DataFrame, partner=None, group=None) -> dict:
    """WoW from Q3 snapshot first; falls back to LAST7/PRIOR7 in bulk_conf."""
    try:
        from utils.queries import get_coco_final_wow
        wow_df = get_coco_final_wow(conn)
        if len(wow_df) > 0:
            sub = wow_df
            if partner:
                sub = wow_df[wow_df.get("PARTNER_NAME", wow_df.columns[0]) == partner]
            elif group and group in GROUP_CANONICAL:
                sub = wow_df[wow_df.get("PARTNER_NAME", wow_df.columns[0]).isin(GROUP_CANONICAL[group])]
            if len(sub) > 0:
                uc_wow  = int(sub.get("WOW_COCO_UCS",  sub.iloc[:, 0]).sum()) if "WOW_COCO_UCS"  in sub.columns else None
                pct_wow = round(float(sub["WOW_COCO_PCT"].sum()), 1)         if "WOW_COCO_PCT"  in sub.columns else None
                parts   = []
                if uc_wow  is not None: parts.append(f"CoCo UC WoW: {uc_wow:+d}")
                if pct_wow is not None: parts.append(f"CoCo % WoW: {pct_wow:+.1f}pp")
                if parts:
                    return {"text": " | ".join(parts)}
    except Exception:
        pass

    # Fallback: rolling LAST7/PRIOR7 from bulk_conf
    sub   = _filter_entity(df, partner, group)
    coco  = sub[sub["IS_COCO_FINAL"]].copy()
    coco  = filter_out_partner_own_accounts(coco) if len(coco) > 0 else coco
    if len(coco) == 0:
        return {"text": "WoW data not available."}

    dedup = coco.drop_duplicates(["PARTNER_NAME", "ACCOUNT_NAME_UPPER"]) if "ACCOUNT_NAME_UPPER" in coco.columns else coco
    for c in ["LAST7_TOKENS", "PRIOR7_TOKENS", "LAST7_CREDITS", "PRIOR7_CREDITS"]:
        if c in dedup.columns:
            dedup = dedup.copy()
            dedup[c] = pd.to_numeric(dedup[c], errors="coerce").fillna(0)

    l7t  = float(dedup["LAST7_TOKENS"].sum())   if "LAST7_TOKENS"   in dedup.columns else 0
    p7t  = float(dedup["PRIOR7_TOKENS"].sum())  if "PRIOR7_TOKENS"  in dedup.columns else 0
    l7c  = float(dedup["LAST7_CREDITS"].sum())  if "LAST7_CREDITS"  in dedup.columns else 0
    p7c  = float(dedup["PRIOR7_CREDITS"].sum()) if "PRIOR7_CREDITS" in dedup.columns else 0

    tok_wow  = round((l7t - p7t) / p7t  * 100, 1) if p7t  > 0 else None
    cred_wow = round((l7c - p7c) / p7c  * 100, 1) if p7c  > 0 else None

    parts = []
    if tok_wow  is not None: parts.append(f"Token WoW: {tok_wow:+.1f}%")
    if cred_wow is not None: parts.append(f"Credit WoW: {cred_wow:+.1f}%")
    return {"text": " | ".join(parts) if parts else "WoW data not available."}


def resolve_stalled(conn, partner=None, group=None, quarter="q3") -> dict:
    """Stalled/aging UCs via get_stalled_use_cases."""
    try:
        from utils.queries import get_stalled_use_cases
        q = QUARTERS[quarter]
        df = get_stalled_use_cases(conn, days_threshold=60, start_date=q["start"], end_date=q["end"])
        if partner:
            df = df[df["PARTNER_NAME"] == partner] if "PARTNER_NAME" in df.columns else df
        elif group and group in GROUP_CANONICAL:
            df = df[df["PARTNER_NAME"].isin(GROUP_CANONICAL[group])] if "PARTNER_NAME" in df.columns else df
        if len(df) == 0:
            return {"text": "No stalled use cases found for the specified filters."}
        count   = len(df)
        eacv    = float(df["USE_CASE_EACV"].sum()) if "USE_CASE_EACV" in df.columns else None
        avg_days = round(float(df["DAYS_IN_CURRENT_STAGE"].mean()), 0) if "DAYS_IN_CURRENT_STAGE" in df.columns else None
        return {
            "count": count, "eacv": eacv,
            "text": (
                f"Stalled UCs (>60 days in stage): {count}"
                + (f" | At-risk EACV: {_fmt_money(eacv)}" if eacv else "")
                + (f" | Avg days stalled: {avg_days:.0f}" if avg_days else "")
            ),
        }
    except Exception as e:
        return {"text": f"Could not fetch stalled UC data: {e}"}


# ── Dispatcher ────────────────────────────────────────────────────────────────

_RESOLVERS = {
    "coco_count":  resolve_coco_count,
    "eacv":        resolve_eacv,
    "tokens":      resolve_tokens,
    "credits":     resolve_credits,
    "target":      resolve_target,
    "stage":       resolve_stage,
    "theatre":     resolve_theatre,
    "region":      resolve_region,
    "attribution": resolve_attribution,
    "confidence":  resolve_confidence,
}


def get_verified_answer(conn, question: str, intent: dict) -> dict | None:
    """
    Fetch a programmatic verified answer.

    Returns {"answer": str, "sql": None, "sql_result": str, "verified": True}
    or None if the metric is unrecognised or data fetch fails.
    """
    metric  = intent.get("metric")
    quarter = intent.get("quarter", "q3")
    partner = intent.get("partner")
    group   = intent.get("group")

    if metric not in _RESOLVERS and metric != "wow" and metric != "stalled":
        return None

    quarters_to_run = ["q2", "q3"] if quarter == "both" else [quarter]
    results = {}

    for q in quarters_to_run:
        try:
            if metric == "stalled":
                results[q] = resolve_stalled(conn, partner, group, q)
            elif metric == "wow":
                bulk = get_quarter_bulk(conn, q)
                results[q] = resolve_wow(conn, bulk, partner, group)
            else:
                bulk = get_quarter_bulk(conn, q)
                results[q] = _RESOLVERS[metric](bulk, partner, group)
        except Exception as e:
            results[q] = {"text": f"Data fetch error for {QUARTERS[q]['label']}: {e}"}

    # Build verified context block
    if quarter == "both":
        verified_block = (
            "[VERIFIED DATA]\n"
            f"--- {QUARTERS['q2']['label']} ---\n{results['q2'].get('text', 'N/A')}\n\n"
            f"--- {QUARTERS['q3']['label']} ---\n{results['q3'].get('text', 'N/A')}\n"
            "[END VERIFIED DATA]"
        )
        raw_result = f"{results['q2'].get('text','')}\n\n{results['q3'].get('text','')}"
    else:
        verified_block = (
            f"[VERIFIED DATA — {QUARTERS[quarter]['label']}]\n"
            f"{results[quarter].get('text', 'N/A')}\n"
            "[END VERIFIED DATA]"
        )
        raw_result = results[quarter].get("text", "")

    # Ask LLM to write clean prose around the verified numbers
    from utils.cortex_helpers import cortex_complete
    prompt = (
        "You are a concise data assistant for the CoCo (Cortex Code) partner adoption dashboard.\n\n"
        f"The following numbers are EXACT and verified — do not modify, contradict, or supplement them:\n"
        f"{verified_block}\n\n"
        f"User question: {question}\n\n"
        "Answer in 2-4 sentences using ONLY the verified numbers above. "
        "If the verified block says a value is 0 or unavailable, state that clearly — do not invent alternative numbers. "
        "Do not say 'approximately'. "
        "If the verified block has a per-partner table, extract the most relevant rows for the question."
    )

    try:
        answer = cortex_complete(conn, "claude-sonnet-4-5", prompt)
    except Exception:
        # If LLM call fails, surface the raw verified text directly
        answer = verified_block

    return {
        "answer":     answer,
        "sql":        None,
        "sql_result": raw_result,
        "verified":   True,
    }
