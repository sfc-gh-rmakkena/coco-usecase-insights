"""Partner Consultants (under Use Cases).

Two stacked views built on the Tier-1 (account-anchored) + Tier-2 (identity-linked) resolved
partner-consultant pipeline (SP_REFRESH_PARTNER_CONSULTANTS, refreshed daily):
  1. Customer engagements - activity partner consultants drive in customer accounts (with CoCo-attached UCs).
  2. Partner-own account usage - the partner's internal CoCo adoption.
Honors the sidebar Region / Partner / date filters.
"""
import pandas as pd
import streamlit as st

from utils.queries import (get_pc_activity, get_pc_coco_uc_engagements, get_pc_top_skills,
                           get_pc_totals, get_pc_usecase_counts)
from utils import resolve_partner_filter, PARTNER_RENAME_MAP, canonical_partner

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
    """Canonicalise PARTNER_NAME, then collapse rows that just became duplicates.

    PARTNER_COCO_USE_CASES carries both 'EY' and 'Ernst & Young (EY)' (and both 'IBM'
    and 'IBM Consulting'). Renaming after aggregation left two rows with the same
    PARTNER_NAME, which fanned out on merge: EY appeared twice in the tables and its
    consultants and tokens were counted twice in the metric cards (393 vs 343
    consultants, 109.1M vs 101.4M tokens). Collapsing here keeps every caller correct.
    """
    if len(df) == 0 or "PARTNER_NAME" not in df.columns:
        return df
    df = df.copy()
    # canonical_partner also fixes case drift (roster 'accenture' -> 'Accenture'), which
    # otherwise both displays oddly and fails to merge with the use-case counts.
    df["PARTNER_NAME"] = df["PARTNER_NAME"].map(canonical_partner).replace(PARTNER_RENAME_MAP)
    if not df["PARTNER_NAME"].duplicated().any():
        return df

    # WOW_PCT is a ratio — summing it is meaningless, so recompute it from the
    # summed 7-day windows after the collapse.
    agg = {}
    for c in df.columns:
        if c == "PARTNER_NAME":
            continue
        if c == "WOW_PCT":
            agg[c] = "first"
        elif pd.api.types.is_numeric_dtype(df[c]):
            agg[c] = "sum"
        else:
            agg[c] = "first"
    out = df.groupby("PARTNER_NAME", as_index=False).agg(agg)

    if {"LAST7_TOKENS", "PRIOR7_TOKENS"}.issubset(out.columns):
        out["WOW_PCT"] = ((out["LAST7_TOKENS"] - out["PRIOR7_TOKENS"]) /
                          out["PRIOR7_TOKENS"].replace(0, float("nan")) * 100).round(1)
    return out


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
    v1 = v1.merge(ucc[["PARTNER_NAME", "COCO_UCS"]], on="PARTNER_NAME", how="left")
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
    v2 = v2.merge(ucc2[["PARTNER_NAME", "ACTIVE_COCO_UCS"]], on="PARTNER_NAME", how="left")
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

# ============================ Summary Prompt ===============================
st.divider()
st.subheader("Generate Summary")

# Strict attribution: consultant activity in customer accounts where THAT SAME partner
# owns a CoCo-attached UC. Joined on exact account name (no shared account ID exists),
# so coverage is partial and is reported explicitly below.
eng = _norm_partner(get_pc_coco_uc_engagements(conn, region, partner_list, start_date, end_date))

_all_cust_tokens = int(v1["TOKENS"].sum()) if 'v1' in dir() else 0

if len(eng) == 0:
    _eng_totals = "(no consultant activity could be matched to a CoCo-attached use case)"
    _eng_ctx = "(none)"
    _partner_ctx = "(none)"
    _skills_ctx = "(none)"
else:
    _eng_tokens = int(eng["TOKENS"].sum())
    _coverage = (f"{_eng_tokens * 100.0 / _all_cust_tokens:.1f}%"
                 if _all_cust_tokens else "n/a")

    _eng_totals = (
        f"CoCo-attached engagements matched: {len(eng):,}\n"
        f"Partners involved: {eng['PARTNER_NAME'].nunique():,}\n"
        f"Customer accounts involved: {eng['ACCOUNT_NAME'].nunique():,}\n"
        f"CoCo-attached use cases in those accounts: {int(eng['COCO_UCS'].sum()):,}\n"
        f"Of those, already deployed: {int(eng['DEPLOYED_UCS'].sum()):,}\n"
        f"Combined EACV of those use cases: ${int(eng['EACV'].sum()):,}\n"
        f"Tokens consumed in these engagements: {_eng_tokens:,}\n"
        f"All customer-account tokens (this filter): {_all_cust_tokens:,}\n"
        f"Share of customer-account tokens that is matched to a CoCo UC: {_coverage}"
    )

    _e = eng.copy()
    _e["TOKEN_SHARE_PCT"] = (_e["TOKENS"] * 100.0 / _eng_tokens).round(1)
    _eng_ctx = _e[["PARTNER_NAME", "ACCOUNT_NAME", "COCO_UCS", "DEPLOYED_UCS", "EACV",
                   "CONSULTANTS", "TOKENS", "TOKEN_SHARE_PCT", "ACTIVE_DAYS",
                   "WORKLOADS", "TECH_USE_CASE"]].to_string(index=False, max_colwidth=60)

    _p = (_e.groupby("PARTNER_NAME", as_index=False)
            .agg(ENGAGEMENTS=("ACCOUNT_NAME", "nunique"),
                 COCO_UCS=("COCO_UCS", "sum"),
                 DEPLOYED_UCS=("DEPLOYED_UCS", "sum"),
                 EACV=("EACV", "sum"),
                 TOKENS=("TOKENS", "sum"))
            .sort_values("TOKENS", ascending=False))
    _p["TOKEN_SHARE_PCT"] = (_p["TOKENS"] * 100.0 / _eng_tokens).round(1)
    _partner_ctx = _p.to_string(index=False)

    _sk_eng = sk[sk["PARTNER_NAME"].isin(eng["PARTNER_NAME"].unique())] if len(sk) else sk
    _skills_ctx = _sk_eng.to_string(index=False) if len(_sk_eng) else "(no skill data for these partners)"

data_context = f"""SCOPE: Region {region} | Period {start_date} to {end_date}
Partner filter: {', '.join(selected_partners) if selected_partners else 'all partners'}

ATTRIBUTION: strict. A row below means consultants from partner P were active in customer
account A, AND partner P owns at least one CoCo-attached use case in account A. Matching is
by exact account name because no shared account ID exists between the usage and use-case
records, so some genuine engagements will be missing.

PRE-COMPUTED TOTALS — use these verbatim. Do NOT sum columns yourself and do NOT compute
any percentage that is not already given here.
{_eng_totals}

PER-PARTNER ROLLUP (TOKEN_SHARE_PCT = share of the matched engagement tokens above)
{_partner_ctx}

ENGAGEMENT DETAIL — one row per partner + customer account.
WORKLOADS and TECH_USE_CASE describe the KIND OF WORK the use case covers.
{_eng_ctx}

COCO SKILLS INVOKED by these partners' consultants in customer accounts (what they
actually did inside the tool, most used first)
{_skills_ctx}
"""

default_prompt = """You are writing a CEO-level readout on what partner consultants are actually DOING inside Snowflake customer accounts that have Cortex Code (CoCo) attached use cases.

Audience: the CEO and VPs. They have 60 seconds. Be specific and concrete. No hedging, no filler, no restating the methodology.

RULES ON NUMBERS
- Every total, count and percentage MUST be copied verbatim from PRE-COMPUTED TOTALS or from the TOKEN_SHARE_PCT column.
- Do NOT sum columns, do NOT compute your own shares or averages, do NOT invent partners, accounts, consultants, skills or figures.
- Name real partners and real customer accounts from the data. Never invent an account name.

WHAT THE DATA MEANS
- Attribution is strict: the partner whose consultants are active also owns a CoCo-attached use case in that same account.
- WORKLOADS and TECH_USE_CASE = the kind of work the engagement covers (e.g. "DE: Ingestion", "AI: Agents", "Analytics: Business Intelligence").
- The skills list = what the consultants actually invoked inside CoCo.
- Tokens = depth of CoCo usage. TOKEN_SHARE_PCT = that partner's share of the matched engagement tokens.

Follow this EXACT structure.

## THE HEADLINE
Exactly 3 sentences, no bullets.
1. How many CoCo-attached engagements, how many partners, and the token volume in them — verbatim from PRE-COMPUTED TOTALS.
2. What kind of work dominates, based on WORKLOADS and TECH_USE_CASE.
3. The single most important pattern a CEO should take away.

## WHAT THE WORK IS
Exactly 3 bullets. Each bullet = one type of work, not one partner.
- Format: "**[Work type]** — [which partners and accounts, with token figures]"
- Group by WORKLOADS / TECH_USE_CASE (Data Engineering, AI, Analytics, Platform, Applications & Collaboration). Pick the 3 work types with the most tokens behind them.
- Assign each engagement to exactly ONE work type — its dominant one. Never mention the same engagement's tokens under two work types, and never restate a token figure you have already attributed.
- Name at most 3 partner+account pairs per bullet. One short clause each, not a list of skills.
- Where the skills data supports it, name at most 2 skills per bullet to say what they actually did in the tool.

## WHO IS DRIVING IT
| Partner | Engagements | CoCo UCs | Deployed | EACV | Tokens | Share of tokens |
- One row per partner from the PER-PARTNER ROLLUP, sorted by tokens descending. Use TOKEN_SHARE_PCT for the last column.
- After the table, exactly 2 sentences: which partners are concentrated in a few deep engagements versus spread thin across many, and which have high token consumption but nothing deployed yet.

## NOTABLE ENGAGEMENTS
3 bullets, the three highest-token engagements.
- Format: "**[Partner] at [Account]** — [consultants] consultants, [tokens] tokens across [active days] active days, [CoCo UCs] use case(s) worth [EACV], [workload type]"

## SO WHAT
2 bullets maximum. Each names a partner or a work type and the specific action to take, justified by a figure from the data.

## COVERAGE NOTE
One italic sentence stating what share of customer-account tokens could be matched to a CoCo-attached use case, using the figure from PRE-COMPUTED TOTALS, and that unmatched activity is excluded.

FORMATTING RULES
- Markdown table only where specified above; everywhere else use bullets
- Numbers with commas; tokens may use M suffix; EACV as $XK or $X.XM
- HARD LIMIT: 350 words for the entire output. Being under is better than being complete — cut adjectives and cut repeated figures before you cut facts.
- One sentence per bullet. No parentheticals that repeat a number already stated.
- Direct, declarative, executive tone
- No greeting, no sign-off, no methodology paragraph"""

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
