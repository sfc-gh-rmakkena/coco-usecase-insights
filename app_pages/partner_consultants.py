"""Partner Consultants (under Use Cases).

Two stacked views built on the Tier-1 (account-anchored) + Tier-2 (identity-linked) resolved
partner-consultant pipeline (SP_REFRESH_PARTNER_CONSULTANTS, refreshed daily):
  1. Customer engagements - activity partner consultants drive in customer accounts (with CoCo-attached UCs).
  2. Partner-own account usage - the partner's internal CoCo adoption.
Honors the sidebar Region / Partner / date filters.
"""
import pandas as pd
import streamlit as st

from utils.queries import (get_pc_activity, get_pc_top_skills, get_pc_totals, get_pc_usecase_counts)
from utils import resolve_partner_filter, PARTNER_RENAME_MAP

conn = st.session_state.conn
_reg = st.session_state.get("selected_region", "Global")
region = _reg if _reg in ("NoAM", "EMEA", "APJ", "Global") else "NoAM"  # theaters roll to NoAM
selected_partners = st.session_state.get("selected_partners", [])
partner_list = resolve_partner_filter(selected_partners) if selected_partners else None
start_date = str(st.session_state.get("okr_start_date", "2026-05-01"))
end_date = str(st.session_state.get("okr_end_date", "2026-07-31"))

st.title(":material/groups: Partner Consultants")
st.caption(f"Identity-resolved partner consultants (Tier-1 account-anchored + Tier-2 email/name-linked). "
           f"Region: {region} | {start_date} to {end_date}")

with st.expander(":material/info: How consultants are identified", expanded=False):
    st.markdown(
        "- **Tier-1**: a user active in a partner's **own** Snowflake account is that partner's consultant.\n"
        "- **Tier-2**: an additional login that is the **same person** (matched by exact email, or exact name + same email domain) as a Tier-1 consultant.\n"
        "- Once resolved, that consultant's activity in **any** customer account counts as the partner's consultant working in a customer engagement.\n"
        "- Tokens/prompts are date-windowed; **7-day change** = last 7 days vs prior 7 days. "
        "Fuzzy name-only matches (different email domains) are held for review and excluded to avoid common-name false positives."
    )


def _wow_bg(val):
    if pd.isna(val) or val == 0:
        return ""
    return "background-color: #d4edda; color: #155724" if val > 0 else "background-color: #f8d7da; color: #721c24"


def _norm_partner(df):
    if len(df) and "PARTNER_NAME" in df.columns:
        df = df.copy()
        df["PARTNER_NAME"] = df["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
    return df


# =============================== View 1 ====================================
st.subheader("1. Customer engagements - activity partner consultants drive")
st.caption("For CoCo-attached use cases, how much CoCo activity the partner's own consultants generate inside customer accounts.")

act = _norm_partner(get_pc_activity(conn, "Customer", region, partner_list, start_date, end_date))
sk = _norm_partner(get_pc_top_skills(conn, "Customer", region, partner_list, start_date, end_date))
ucc = _norm_partner(get_pc_usecase_counts(conn))

if len(act) == 0:
    st.info("No customer-account consultant activity for the current filters.")
else:
    v1 = act.merge(sk, on="PARTNER_NAME", how="left")
    # UC counts use the use-case partner taxonomy; join case-insensitively.
    _ucc1 = ucc[["PARTNER_NAME", "COCO_UCS"]].copy()
    _ucc1["_k"] = _ucc1["PARTNER_NAME"].astype(str).str.upper()
    v1["_k"] = v1["PARTNER_NAME"].astype(str).str.upper()
    v1 = v1.merge(_ucc1[["_k", "COCO_UCS"]], on="_k", how="left").drop(columns="_k")
    v1["COCO_UCS"] = v1["COCO_UCS"].fillna(0).astype(int)
    v1 = v1.sort_values("TOKENS", ascending=False)

    k = st.columns(3)
    k[0].metric("Partners active in customers", f"{v1['PARTNER_NAME'].nunique():,}")
    k[1].metric("Consultants in customer accts", f"{int(v1['CONSULTANTS'].sum()):,}")
    k[2].metric("Customer-acct tokens", f"{int(v1['TOKENS'].sum())/1e9:.2f}B")

    show1 = v1[["PARTNER_NAME", "COCO_UCS", "CONSULTANTS", "TOKENS", "PROMPTS", "TOP_SKILLS", "WOW_PCT"]]
    st.dataframe(
        show1.style.map(_wow_bg, subset=["WOW_PCT"]),
        use_container_width=True, hide_index=True, height=460,
        column_config={
            "PARTNER_NAME": st.column_config.TextColumn("Partner", width="medium"),
            "COCO_UCS": st.column_config.NumberColumn("CoCo-attached UCs", format="%d"),
            "CONSULTANTS": st.column_config.NumberColumn("# Consultants", format="%d"),
            "TOKENS": st.column_config.NumberColumn("Tokens", format="%d"),
            "PROMPTS": st.column_config.NumberColumn("Prompts", format="%d"),
            "TOP_SKILLS": st.column_config.TextColumn("Key skills"),
            "WOW_PCT": st.column_config.NumberColumn("Tokens 7d change", format="%+.1f%%", help="Last 7 days vs prior 7 days."),
        })
    st.download_button("Download (CSV)", show1.to_csv(index=False).encode("utf-8"),
                       file_name="partner_consultants_customer.csv", mime="text/csv", key="pc_dl1")

st.divider()

# =============================== View 2 ====================================
st.subheader("2. Partner-own account usage")
st.caption("The partner's internal CoCo adoption - consultants using CoCo inside the partner's own account.")

act2 = _norm_partner(get_pc_activity(conn, "Partner", region, partner_list, start_date, end_date))
tot = _norm_partner(get_pc_totals(conn, region, partner_list))
sk2 = _norm_partner(get_pc_top_skills(conn, "Partner", region, partner_list, start_date, end_date))
ucc2 = _norm_partner(get_pc_usecase_counts(conn))

if len(act2) == 0:
    st.info("No partner-own-account consultant activity for the current filters.")
else:
    v2 = tot.merge(act2, on="PARTNER_NAME", how="left", suffixes=("", "_act"))
    v2 = v2.merge(sk2, on="PARTNER_NAME", how="left")
    _ucc2 = ucc2[["PARTNER_NAME", "ACTIVE_COCO_UCS"]].copy()
    _ucc2["_k"] = _ucc2["PARTNER_NAME"].astype(str).str.upper()
    v2["_k"] = v2["PARTNER_NAME"].astype(str).str.upper()
    v2 = v2.merge(_ucc2[["_k", "ACTIVE_COCO_UCS"]], on="_k", how="left").drop(columns="_k")
    for c in ["CONSULTANTS", "TOKENS", "PROMPTS", "ACTIVE_COCO_UCS"]:
        v2[c] = v2[c].fillna(0)
    v2["ACTIVE_COCO_UCS"] = v2["ACTIVE_COCO_UCS"].astype(int)
    v2 = v2.sort_values("TOKENS", ascending=False)

    k = st.columns(3)
    k[0].metric("Partners", f"{v2['PARTNER_NAME'].nunique():,}")
    k[1].metric("Total consultants", f"{int(v2['TOTAL_CONSULTANTS'].sum()):,}")
    k[2].metric("Partner-acct tokens", f"{int(v2['TOKENS'].sum())/1e9:.2f}B")

    show2 = v2[["PARTNER_NAME", "TOTAL_CONSULTANTS", "ACTIVE_COCO_UCS",
                "TOKENS", "PROMPTS", "TOP_SKILLS", "WOW_PCT"]]
    st.dataframe(
        show2.style.map(_wow_bg, subset=["WOW_PCT"]),
        use_container_width=True, hide_index=True, height=460,
        column_config={
            "PARTNER_NAME": st.column_config.TextColumn("Partner", width="medium"),
            "TOTAL_CONSULTANTS": st.column_config.NumberColumn("# Total consultants", format="%d"),
            "ACTIVE_COCO_UCS": st.column_config.NumberColumn("Active CoCo UCs", format="%d"),
            "TOKENS": st.column_config.NumberColumn("Tokens", format="%d"),
            "PROMPTS": st.column_config.NumberColumn("Prompts", format="%d"),
            "TOP_SKILLS": st.column_config.TextColumn("Top skills"),
            "WOW_PCT": st.column_config.NumberColumn("Tokens 7d change", format="%+.1f%%", help="Last 7 days vs prior 7 days."),
        })
    st.download_button("Download (CSV)", show2.to_csv(index=False).encode("utf-8"),
                       file_name="partner_consultants_partner.csv", mime="text/csv", key="pc_dl2")

st.session_state.ask_ai_context = (
    f"Current page: Partner Consultants (Tier-1+Tier-2 resolved). Region: {region}. Period: {start_date} to {end_date}.\n"
    "Two views: customer-engagement activity and partner-own-account usage per partner."
)
