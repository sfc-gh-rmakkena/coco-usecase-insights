"""Partner Consultants (under Use Cases).

Two stacked views built on the Tier-1 (account-anchored) + Tier-2 (identity-linked) resolved
partner-consultant pipeline (SP_REFRESH_PARTNER_CONSULTANTS, refreshed daily):
Shows the customer engagements partner consultants drive in customer accounts that have
CoCo-attached use cases.
Honors the sidebar Region / Partner / date filters.
"""
import pandas as pd
import streamlit as st

from utils.queries import (get_pc_activity, get_pc_coco_uc_engagements, get_pc_top_skills,
                           get_pc_usecase_counts)
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

_v1_totals = "(no customer-account consultant activity for this filter)"
_v1_ctx = "(none)"
_mom_ctx = "(no momentum data)"

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

    # Exactly the figures rendered in the three tiles and the table above, so the
    # summary and the page can never disagree.
    _v1_totals = (
        f"Partners active in customer accounts: {v1['PARTNER_NAME'].nunique():,}\n"
        f"Consultants in customer accounts: {int(v1['CONSULTANTS'].sum()):,}\n"
        f"Customer-account tokens: {int(v1['TOKENS'].sum()):,}\n"
        f"Prompts: {int(v1['PROMPTS'].sum()):,}\n"
        f"CoCo-attached use cases across these partners: {int(v1['COCO_UCS'].sum()):,}"
    )
    _v1 = show1.copy()
    _v1["TOKEN_SHARE_PCT"] = (_v1["TOKENS"] * 100.0 / max(int(v1["TOKENS"].sum()), 1)).round(1)
    # Missing skills must read as absent, not as NaN, or the model renders "NaN"
    # in the summary table or invents a skill to fill the gap.
    _v1["TOP_SKILLS"] = _v1["TOP_SKILLS"].fillna("(not captured)")
    _v1_ctx = _v1.to_string(index=False, max_colwidth=70)

    # Momentum is only meaningful on a material token base: a +6,000% swing on
    # 300K tokens is noise. Restrict the eligible set in code, because the model
    # ignores a written "only if material" instruction.
    _mom = _v1.head(8)[["PARTNER_NAME", "TOKENS", "WOW_PCT"]].dropna(subset=["WOW_PCT"])
    _mom_ctx = (_mom.sort_values("WOW_PCT", ascending=False).to_string(index=False)
                if len(_mom) else "(no momentum data)")


st.session_state.ask_ai_context = (
    f"Current page: Partner Consultants (Tier-1+Tier-2 resolved). Region: {region}. Period: {start_date} to {end_date}.\n"
    "Shows customer-engagement activity per partner."
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
    _geo_ctx = "(none)"
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
    _eng_ctx = _e[["PARTNER_NAME", "ACCOUNT_NAME", "THEATER_NAME", "REGION_NAME",
                   "COCO_UCS", "DEPLOYED_UCS", "EACV",
                   "CONSULTANTS", "TOKENS", "TOKEN_SHARE_PCT", "ACTIVE_DAYS",
                   "WORKLOADS", "TECH_USE_CASE"]].to_string(index=False, max_colwidth=60)

    _geo = (_e.groupby("THEATER_NAME", as_index=False)
              .agg(ENGAGEMENTS=("ACCOUNT_NAME", "nunique"), COCO_UCS=("COCO_UCS", "sum"),
                   CONSULTANTS=("CONSULTANTS", "sum"), TOKENS=("TOKENS", "sum"))
              .sort_values("TOKENS", ascending=False))
    _geo_ctx = _geo.to_string(index=False)

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

=======================================================================
PRIMARY BASIS — SECTION 1 RESULTS: "Customer engagements — activity partner
consultants drive". These are the exact figures shown on the page. The exec
summary headline numbers MUST come from here, so the readout and the page agree.
=======================================================================

SECTION 1 TOTALS — use these verbatim for all headline figures.
{_v1_totals}

SECTION 1 PER-PARTNER TABLE (as displayed; TOKEN_SHARE_PCT = share of customer-account
tokens; TOP_SKILLS = what consultants invoked; WOW_PCT = tokens last 7d vs prior 7d)
{_v1_ctx}

MOMENTUM — the ONLY partners whose week-over-week change may be quoted. These are the
top 8 by tokens, so the percentage sits on a material base.
{_mom_ctx}

=======================================================================
SUPPORTING DETAIL — a STRICT-ATTRIBUTION SUBSET of the above, used only for
account names, region and consultant depth. These totals are SMALLER than the
Section 1 totals. Never present a figure from this subset as an overall total.
=======================================================================

ATTRIBUTION: strict. A row below means consultants from partner P were active in customer
account A, AND partner P owns at least one CoCo-attached use case in account A. Accounts are
matched on Salesforce account ID, not name. Coverage is partial: the limit is the strict
partner requirement, because the partner whose consultants work in an account is often not the
partner named on that account's CoCo use case.

SUBSET TOTALS (a subset — not overall totals)
{_eng_totals}

SUBSET PER-PARTNER ROLLUP (TOKEN_SHARE_PCT = share of the matched subset tokens)
{_partner_ctx}

ENGAGEMENT DETAIL — one row per partner + customer account.
THEATER_NAME and REGION_NAME say WHERE the use case sits. CONSULTANTS and ACTIVE_DAYS
show how deep the partner is in that customer. WORKLOADS and TECH_USE_CASE describe the
KIND OF WORK the use case covers.
{_eng_ctx}

WHERE THE WORK SITS — engagements, use cases, consultants and tokens by theatre
{_geo_ctx}

COCO SKILLS INVOKED by these partners' consultants in customer accounts (what they
actually did inside the tool, most used first)
{_skills_ctx}
"""

default_prompt = """You are writing an EXECUTIVE SUMMARY on what partner consultants are actually DOING inside Snowflake customer accounts that have Cortex Code (CoCo) attached use cases.

Audience: the CEO and VPs. They have 60 seconds. Be specific and concrete. No hedging, no filler, no restating the methodology.

RULES ON NUMBERS
- All headline figures (partners, consultants, tokens, prompts, CoCo-attached use cases) MUST be copied verbatim from SECTION 1 TOTALS. These are the numbers on the page, so your summary must match them.
- Use the SUPPORTING DETAIL subset ONLY for customer account names, theatre/region and per-account consultant depth. Its totals are smaller — never present them as overall totals.
- Do NOT sum columns, do NOT compute your own shares or averages, do NOT invent partners, accounts, consultants, skills or figures.
- Name real partners and real customer accounts from the data. Never invent an account name.

WHAT THE DATA MEANS
- Every figure is consultant activity inside CUSTOMER accounts. Say nothing about the partner's own internal adoption or their internal consultant bench — that data is not provided here.
- TOP_SKILLS / the skills list = what the consultants actually invoked inside CoCo.
- WORKLOADS and TECH_USE_CASE = the kind of work the engagement covers (e.g. "DE: Ingestion", "AI: Agents", "Analytics: Business Intelligence").
- Tokens = depth of CoCo usage. WOW_PCT = tokens last 7 days vs prior 7 days, i.e. momentum.

Produce EXACTLY three things, in this order, and nothing else.

## EXECUTIVE SUMMARY
A single paragraph of 3 sentences, or 4 at the absolute maximum. No bullets, no sub-headings, no lists. This is about WHAT THE CONSULTANTS ARE DOING inside customer accounts — not a financial recap. Assign the content as follows:
1. The headline from SECTION 1 TOTALS: how many partners have consultants active in customer accounts, how many consultants, the token volume, and how many CoCo-attached use cases they sit against.
2. What kind of work it is: name the dominant WORKLOADS / TECH_USE_CASE categories, and name at least three specific CoCo skills consultants invoked.
3. Depth: name the two or three customer accounts with the deepest partner presence, quoting consultants and active days for each from the supporting detail. Depth means MANY consultants sustained over MANY active days — rank on those two columns. Never call an account "deep" when it has only a handful of consultants or a couple of active days, however many tokens it burned.
4. Where the work sits: the leading theatres or regions. You may add a momentum call-out, but ONLY using a partner listed in the MOMENTUM block. Quoting a week-over-week percentage for any partner outside that block is a factual error, because the swing sits on an immaterial token base.
Do NOT lead with EACV or dollar figures — mention money only if a sentence has room left. Do not simply restate the table.

## WHO IS DRIVING IT
| Partner | CoCo UCs | Consultants | Tokens | Share of tokens | Key skills | 7d change |
- One row per partner from the SECTION 1 PER-PARTNER TABLE, sorted by tokens descending. Use TOKEN_SHARE_PCT for the share column and WOW_PCT for the 7d change.
- Table only. Write NO narrative sentences after this table.

## COVERAGE NOTE
One italic sentence stating what share of customer-account tokens could be matched to a CoCo-attached use case owned by the same partner, using the figure from the SUBSET TOTALS, and noting that account-level and regional detail is drawn from that matched portion only. Do NOT say the limitation is account-name matching — accounts are matched on Salesforce account ID.

FORMATTING RULES
- HARD LIMIT: the EXECUTIVE SUMMARY paragraph is at most 4 sentences and at most 130 words. Count them before you answer. Being shorter is better than being complete.
- Do NOT add any section that is not listed above. No "What the work is", no "Notable engagements", no "So what", no closing remarks.
- Numbers with commas; tokens may use M or B suffix; EACV as $XK or $X.XM
- If TOP_SKILLS reads "(not captured)" for a partner, leave the skills cell as "n/a". Never write "NaN" and never guess a skill.
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
