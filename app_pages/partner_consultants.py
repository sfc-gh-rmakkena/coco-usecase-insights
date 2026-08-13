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

_v1_totals = "(no customer-engagement data)"

if len(act) == 0:
    st.info("No customer-account consultant activity for the current filters.")
else:
    v1 = act.merge(sk, on="PARTNER_NAME", how="left")
    v1 = v1.merge(ucc[["PARTNER_NAME", "COCO_UCS"]], on="PARTNER_NAME", how="left")
    v1["COCO_UCS"] = v1["COCO_UCS"].fillna(0).astype(int)
    v1 = v1.sort_values("TOKENS", ascending=False)

    k = st.columns(3)
    k[0].metric("Partners active in customers", f"{v1['PARTNER_NAME'].nunique():,}")
    k[1].metric("Consultants in customer accts", f"{int(v1['CONSULTANTS'].sum()):,}")
    k[2].metric("Customer-acct tokens", f"{int(v1['TOKENS'].sum())/1e9:.2f}B")

    _v1_totals = (
        f"Partners active in customer accounts: {v1['PARTNER_NAME'].nunique():,}\n"
        f"Consultants in customer accounts: {int(v1['CONSULTANTS'].sum()):,}\n"
        f"Total customer-account tokens: {int(v1['TOKENS'].sum()):,}\n"
        f"Total customer-account prompts: {int(v1['PROMPTS'].sum()):,}"
    )

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

_v2_totals = "(no partner-own-account data)"

if len(act2) == 0:
    st.info("No partner-own-account consultant activity for the current filters.")
else:
    v2 = tot.merge(act2, on="PARTNER_NAME", how="left", suffixes=("", "_act"))
    v2 = v2.merge(sk2, on="PARTNER_NAME", how="left")
    v2 = v2.merge(ucc2[["PARTNER_NAME", "ACTIVE_COCO_UCS"]], on="PARTNER_NAME", how="left")
    for c in ["CONSULTANTS", "TOKENS", "PROMPTS", "ACTIVE_COCO_UCS"]:
        v2[c] = v2[c].fillna(0)
    v2["ACTIVE_COCO_UCS"] = v2["ACTIVE_COCO_UCS"].astype(int)
    v2 = v2.sort_values("TOKENS", ascending=False)

    k = st.columns(3)
    k[0].metric("Partners", f"{v2['PARTNER_NAME'].nunique():,}")
    k[1].metric("Total consultants", f"{int(v2['TOTAL_CONSULTANTS'].sum()):,}")
    k[2].metric("Partner-acct tokens", f"{int(v2['TOKENS'].sum())/1e9:.2f}B")

    _v2_totals = (
        f"Partners with own-account activity: {v2['PARTNER_NAME'].nunique():,}\n"
        f"Total consultants (all resolved): {int(v2['TOTAL_CONSULTANTS'].sum()):,}\n"
        f"Total partner-own-account tokens: {int(v2['TOKENS'].sum()):,}\n"
        f"Total partner-own-account prompts: {int(v2['PROMPTS'].sum()):,}"
    )

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

# ============================ Summary Prompt ===============================
st.divider()
st.subheader("Generate Summary")

_v1_ctx = show1.to_string(index=False) if 'show1' in dir() else "(no customer-engagement data)"
_v2_ctx = show2.to_string(index=False) if 'show2' in dir() else "(no partner-own-account data)"

data_context = f"""SCOPE: Region {region} | Period {start_date} to {end_date}
Partner filter: {', '.join(selected_partners) if selected_partners else 'all managed partners'}

PRE-COMPUTED TOTALS — use these verbatim for any total or count. Do NOT sum the
tables yourself and do NOT compute percentages that are not listed here.
VIEW 1:
{_v1_totals}
VIEW 2:
{_v2_totals}

VIEW 1 - CUSTOMER ENGAGEMENTS (consultant activity inside customer accounts).
Columns: Partner, CoCo-attached UCs, # Consultants, Tokens, Prompts, Key skills, Tokens 7d change %
{_v1_ctx}

VIEW 2 - PARTNER-OWN ACCOUNT USAGE (the partner's internal CoCo adoption).
Columns: Partner, # Total consultants, Active CoCo UCs, Tokens, Prompts, Top skills, Tokens 7d change %
{_v2_ctx}
"""

default_prompt = """You are writing a briefing for Snowflake leadership on PARTNER CONSULTANT activity — the individual consultants at managed partners who are actually using Cortex Code (CoCo).

All numbers MUST come from the data provided below, and every total or count MUST be taken verbatim from the PRE-COMPUTED TOTALS block. Do NOT sum table columns yourself, do NOT compute percentages or shares that are not given to you, and do NOT invent partners, consultants, skills or figures. If something is not in the data, omit it.

Consultants are identity-resolved: Tier-1 = active in the partner's own Snowflake account, Tier-2 = the same person matched into customer accounts. "Customer engagements" = the partner's consultants working inside CUSTOMER accounts. "Partner-own" = usage inside the partner's OWN account.

Follow this EXACT structure:

## SUMMARY
2-3 sentences, then exactly 4 bullets.
- Open with total consultants active in customer accounts and total customer-account tokens, both taken from PRE-COMPUTED TOTALS.
- Second sentence: the dominant pattern — is activity concentrated in a few partners or spread widely? Name the leading partners; do not quote a percentage share.
- Bullet 1: "**Top partners by customer-account tokens:** [top 3 with token counts]"
- Bullet 2: "**Deepest consultant benches:** [top 3 by # consultants]"
- Bullet 3: "**Most used skills:** [top 3 skills across partners]"
- Bullet 4: "**Momentum:** [partners with the largest positive 7d token change, and any notable declines]"

## CUSTOMER ENGAGEMENTS
| Partner | CoCo UCs | Consultants | Tokens | Prompts | Key skills | 7d change |
- Include every partner present in View 1, sorted by tokens descending.
- After the table: one sentence on which partners are converting consultant activity into CoCo use cases, and which have consultants active but few or no use cases.

## PARTNER-OWN ADOPTION
| Partner | Total consultants | Active CoCo UCs | Tokens | Prompts | Top skills | 7d change |
- Include every partner present in View 2, sorted by tokens descending.
- After the table: one sentence contrasting internal adoption with customer-facing activity — flag partners strong internally but absent in customer accounts, and the reverse.

## WHERE TO PUSH
3 bullets, each naming a specific partner and a specific action, justified by a number from the data.

FORMATTING RULES:
- Markdown tables for ALL data — no narrative paragraphs of numbers
- Large numbers with commas (e.g. 1,234,567); tokens may use B/M suffixes
- Percentages signed (e.g. +12.4%, -3.1%)
- Under 500 words
- Confident, data-driven, executive-appropriate
- No greeting, sign-off, or filler"""

prompt_input = st.text_area(
    "Prompt",
    value=default_prompt,
    height=300,
    help="Edit this prompt to customize the summary. The tables above are automatically included.",
    key="pc_prompt",
)

if st.button("Generate Summary", type="primary", key="pc_generate"):
    from utils.cortex_helpers import cortex_complete
    from utils.report import md_to_html, copy_rich_text_button

    full_prompt = f"{prompt_input}\n\nDATA:\n{data_context}\n\nWrite the briefing:"
    placeholder = st.empty()
    placeholder.info("Generating summary with Cortex Complete...")
    summary = cortex_complete(conn, "claude-sonnet-4-5", full_prompt)

    # Escape $ before digits so Streamlit doesn't treat $1.2M as LaTeX math
    import re as _re
    placeholder.markdown(_re.sub(r'\$(\d)', r'\\$\1', summary))

    st.divider()
    st.caption("Click **Copy Rich Text**, then paste into Slack, email or a doc — tables keep their formatting.")
    c1, c2 = st.columns(2)
    with c1:
        copy_rich_text_button(md_to_html(summary), summary, button_id="pcCopyBtn")
    with c2:
        st.download_button(
            "Download as HTML",
            data=md_to_html(summary),
            file_name="partner_consultants_summary.html",
            mime="text/html",
            key="pc_dl_html",
        )
