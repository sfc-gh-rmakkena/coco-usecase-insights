import streamlit as st
import pandas as pd
from datetime import datetime
from utils.queries import (
    get_summary_stats, get_by_partner, get_by_stage, get_source_breakdown,
    get_by_region, get_email_summary_data, get_use_case_type_patterns,
    get_workload_patterns, get_competitive_landscape, get_comment_narratives,
    get_partner_workload_cross, get_regional_themes, get_regional_comment_narratives,
    get_partner_coco_coverage,
)
from utils.cortex_helpers import cortex_complete

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
partner_filter = st.session_state.get("selected_partner", "All")

st.title(":material/mail: Executive Email Summary")
filter_label = f"Region: {region}"
if partner_filter and partner_filter != "All":
    filter_label += f" | Partner: {partner_filter}"
st.caption(f"AI-generated weekly summary for CoCo Use Case Intelligence | {filter_label}")

source_toggle = st.segmented_control("Use Case View", ["Overall", "PSE Confirmed", "Feature Flag"], default="Overall", key="email_source")
st.caption(f"Filters active: {source_toggle} use cases • {region} region")

def _apply_partner_filter(df, col='PARTNER_NAME'):
    if partner_filter and partner_filter != "All" and col in df.columns:
        return df[df[col].str.contains(partner_filter, case=False, na=False)]
    return df

with st.spinner("Loading data..."):
    stats = get_summary_stats(conn, region=region, source=source_toggle)
    partner_data = get_email_summary_data(conn, region=region, source=source_toggle)
    stage_data = get_by_stage(conn, region=region, source=source_toggle)
    source_data = get_source_breakdown(conn, region=region)
    region_data = get_by_region(conn, source=source_toggle)
    type_patterns = get_use_case_type_patterns(conn, region=region, source=source_toggle)
    workload_data = get_workload_patterns(conn, region=region, source=source_toggle)
    competitive_data = get_competitive_landscape(conn, region=region, source=source_toggle)
    comment_data = get_comment_narratives(conn, region=region, source=source_toggle)
    partner_workloads = get_partner_workload_cross(conn, region=region, source=source_toggle)
    regional_themes = get_regional_themes(conn, source=source_toggle)
    coco_coverage = get_partner_coco_coverage(conn, region=region)

if partner_filter and partner_filter != "All":
    partner_data = _apply_partner_filter(partner_data)
    comment_data = _apply_partner_filter(comment_data)
    partner_workloads = _apply_partner_filter(partner_workloads)

if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

s = stats.iloc[0]

st.subheader("Data Summary")
with st.expander("View Raw Metrics", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Use Cases", int(s['TOTAL_USE_CASES']))
    c2.metric("Total EACV", f"${s['TOTAL_EACV']/1_000_000:.1f}M" if s['TOTAL_EACV'] else "$0")
    c3.metric("Partners", int(s['TOTAL_PARTNERS']))
    c4.metric("Accounts", int(s['TOTAL_ACCOUNTS']))

    tab1, tab2, tab3, tab4 = st.tabs(["Pipeline", "Use Case Types", "Workloads", "Competitors"])
    with tab1:
        if len(stage_data) > 0:
            st.dataframe(stage_data, hide_index=True, use_container_width=True)
    with tab2:
        if len(type_patterns) > 0:
            st.dataframe(type_patterns[['TECHNICAL_USE_CASE', 'USE_CASE_COUNT', 'TOTAL_EACV', 'PARTNER_COUNT', 'WON_PLUS']], hide_index=True, use_container_width=True)
    with tab3:
        if len(workload_data) > 0:
            st.dataframe(workload_data, hide_index=True, use_container_width=True)
    with tab4:
        if len(competitive_data) > 0:
            st.dataframe(competitive_data, hide_index=True, use_container_width=True)

coverage_map = {}
if len(coco_coverage) > 0:
    for _, cv in coco_coverage.iterrows():
        coverage_map[cv['PARTNER_NAME']] = {
            'total': int(cv['TOTAL_PARTNER_UCS']),
            'coco': int(cv['COCO_UCS']),
            'pct': float(cv['COCO_PCT'] or 0)
        }

partner_ctx = ""
for _, p in partner_data.head(15).iterrows():
    eacv = p.get('TOTAL_EACV', 0) or 0
    cv = coverage_map.get(p['PARTNER_NAME'], {})
    total_ucs = cv.get('total', '?')
    coco_ucs = cv.get('coco', int(p['USE_CASE_COUNT']))
    coco_pct = cv.get('pct', 0)
    partner_ctx += f"  {p['PARTNER_NAME']}: CoCo={coco_ucs}/{total_ucs} ({coco_pct:.0f}%), ${eacv/1000:.0f}K, Active={int(p.get('ACTIVE_PIPELINE', 0))}, Won={int(p.get('WON', 0))}, Impl={int(p.get('IN_IMPL', 0))}, Deployed={int(p.get('DEPLOYED', 0))}\n"

stage_ctx = ""
for _, sg in stage_data.iterrows():
    eacv = sg.get('TOTAL_EACV', 0) or 0
    stage_ctx += f"  {sg['USE_CASE_STAGE']}: {int(sg['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K, Avg {int(sg.get('AVG_DAYS', 0) or 0)} days\n"

region_ctx = ""
for _, rg in region_data.iterrows():
    eacv = rg.get('TOTAL_EACV', 0) or 0
    region_ctx += f"  {rg['REGION']}: {int(rg['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K EACV, {int(rg['PARTNER_COUNT'])} partners\n"

type_ctx = ""
for _, tp in type_patterns.head(10).iterrows():
    eacv = tp.get('TOTAL_EACV', 0) or 0
    type_ctx += f"  {tp['TECHNICAL_USE_CASE']}: {int(tp['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K, {int(tp['PARTNER_COUNT'])} partners, {int(tp['WON_PLUS'])} won+\n"

workload_ctx = ""
for _, wl in workload_data.iterrows():
    eacv = wl.get('TOTAL_EACV', 0) or 0
    workload_ctx += f"  {wl['WORKLOADS']}: {int(wl['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K, {int(wl['PARTNER_COUNT'])} partners\n"

competitive_ctx = ""
for _, comp in competitive_data.head(8).iterrows():
    eacv = comp.get('TOTAL_EACV', 0) or 0
    competitive_ctx += f"  {comp['COMPETITORS']}: {int(comp['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K\n"

partner_wl_ctx = ""
for _, pw in partner_workloads.head(12).iterrows():
    eacv = pw.get('TOTAL_EACV', 0) or 0
    cv = coverage_map.get(pw['PARTNER_NAME'], {})
    total_ucs = cv.get('total', '?')
    coco_pct = cv.get('pct', 0)
    partner_wl_ctx += f"  {pw['PARTNER_NAME']}: CoCo={int(pw['TOTAL_USE_CASES'])}/{total_ucs} ({coco_pct:.0f}%), ${eacv/1000:.0f}K | AI={int(pw['AI_USE_CASES'])}, DE={int(pw['DE_USE_CASES'])}, Analytics={int(pw['ANALYTICS_USE_CASES'])}, Platform={int(pw['PLATFORM_USE_CASES'])}, Apps={int(pw['APPS_USE_CASES'])}\n"

comment_ctx = ""
for _, cm in comment_data.head(10).iterrows():
    eacv = cm.get('USE_CASE_EACV', 0) or 0
    se_snip = str(cm.get('SE_COMMENTS_EXCERPT', '') or '')[:200].replace('\n', ' ')
    partner_snip = str(cm.get('PARTNER_COMMENTS_EXCERPT', '') or '')[:200].replace('\n', ' ')
    entry = f"  [{cm['PARTNER_NAME']} | {cm['ACCOUNT_NAME']} | ${eacv/1000:.0f}K | {cm.get('TECHNICAL_USE_CASE', 'N/A')}]"
    if se_snip:
        entry += f" SE: {se_snip}"
    if partner_snip:
        entry += f" PARTNER: {partner_snip}"
    comment_ctx += entry + "\n"


def _build_region_theme_ctx(df, region_name):
    region_df = df[df['REGION'] == region_name]
    if len(region_df) == 0:
        return f"  No data for {region_name}\n"
    total_ucs = int(region_df['USE_CASE_COUNT'].sum())
    total_eacv = region_df['TOTAL_EACV'].sum() or 0
    ctx = f"  {total_ucs} UCs, ${total_eacv/1_000_000:.1f}M EACV\n"
    type_agg = region_df.groupby('TECHNICAL_USE_CASE').agg({'USE_CASE_COUNT': 'sum', 'TOTAL_EACV': 'sum'}).reset_index().sort_values('TOTAL_EACV', ascending=False).head(5)
    for _, row in type_agg.iterrows():
        if row['TECHNICAL_USE_CASE']:
            ctx += f"    {row['TECHNICAL_USE_CASE']}: {int(row['USE_CASE_COUNT'])} UCs, ${(row.get('TOTAL_EACV', 0) or 0)/1000:.0f}K\n"
    comp_agg = region_df[region_df['COMPETITORS'].notna()].groupby('COMPETITORS').agg({'USE_CASE_COUNT': 'sum'}).reset_index().sort_values('USE_CASE_COUNT', ascending=False).head(3)
    comps = ", ".join([f"{r['COMPETITORS']}({int(r['USE_CASE_COUNT'])})" for _, r in comp_agg.iterrows()])
    if comps:
        ctx += f"    Competitors: {comps}\n"
    return ctx


data_context = f"""
=== {source_toggle} Use Cases | {region} Region{' | Partner: ' + partner_filter if partner_filter and partner_filter != 'All' else ''} ===

HEADLINE: {int(s['TOTAL_USE_CASES'])} UCs | {int(s['TOTAL_PARTNERS'])} Partners | {int(s['TOTAL_ACCOUNTS'])} Accounts | ${s['TOTAL_EACV']/1_000_000:.1f}M EACV
Active(1-3): {int(s['ACTIVE_COUNT'])} (${s['ACTIVE_EACV']/1_000_000:.1f}M) | Won(4): {int(s['WON_COUNT'])} (${s['WON_EACV']/1_000_000:.1f}M) | Impl(5-6): {int(s['IMPL_COUNT'])} (${s['IMPL_EACV']/1_000_000:.1f}M) | Deployed(7): {int(s['DEPLOYED_COUNT'])} (${s['DEPLOYED_EACV']/1_000_000:.1f}M)
PSE Confirmed: {int(s['PARTNER_CONFIRMED_COUNT'])} | Feature Flag: {int(s['FEATURE_FLAG_COUNT'])} | SE Comments: {int(s['SE_CONFIRMED_COUNT'])}

REGIONAL:
{region_ctx}
NoAM:
{_build_region_theme_ctx(regional_themes, "NoAM")}
EMEA:
{_build_region_theme_ctx(regional_themes, "EMEA")}
APJ:
{_build_region_theme_ctx(regional_themes, "APJ")}

PIPELINE:
{stage_ctx}

USE CASE TYPES:
{type_ctx}

WORKLOADS:
{workload_ctx}

COMPETITORS:
{competitive_ctx}

TOP PARTNERS (by EACV):
{partner_ctx}

PARTNER WORKLOAD MIX:
{partner_wl_ctx}

COMMENT HIGHLIGHTS (Top 10 by EACV):
{comment_ctx}
"""

st.markdown("---")
st.subheader("Generate Email Summary")

default_prompt = f"""Write an executive email for Snowflake's Partner SE team summarizing CoCo (Cortex Code) Use Case Intelligence. Follow this EXACT format with these 7 sections in order:

**EXECUTIVE SUMMARY** (2-3 sentences + bullets)
- Lead with: "[X] use cases across [Y] partners driving $[Z]M pipeline with [W] deployed."
- Second sentence: one-line narrative on dominant use case patterns and competitive displacement themes.
- Bullet: "Top use case types: [top 3 types by count]"
- Bullet: "Top partners by region: NoAM ([top 3]), EMEA ([top 3]), APJ ([top 3])"
- Bullet: "Competitors displaced: [top 3 competitors by count]"

**PIPELINE OVERVIEW** (markdown table)
| Stage | Count | EACV | Avg Days |
One row per stage. Use $XK or $X.XM format.

**REGIONAL BREAKDOWN** (markdown table + 1-sentence theme per region)
| Region | Use Cases | EACV | Partners | Top Types | Key Competitors |
One row each for NoAM, EMEA, APJ. After the table, write ONE sentence per region describing the dominant theme.

**TOP PARTNERS** (markdown table)
| Partner | Total UCs | CoCo UCs | CoCo% | EACV | AI | DE | Analytics | Won+ | Phase |
- Show top 12 partners sorted by EACV
- "Total UCs" = all partner use cases (stages 3-7), "CoCo UCs" = CoCo-attached subset, "CoCo%" = CoCo/Total
- Target is 50% CoCo adoption per partner. Highlight partners above 50% as strong, below 20% as needs attention
- "Phase" must be one of: Discovery, Building Momentum, Deploying at Scale
- Base Phase on: Discovery if mostly stages 1-3, Building Momentum if mix of stages, Deploying at Scale if significant won/impl/deployed

**USE CASE PATTERNS** (3-4 bullets)
- Each bullet: pattern name + 1 sentence describing it with partner names and EACV
- Example: "**Migration Acceleration** — Teradata/Oracle migrations represent $XM EACV led by Accenture and Deloitte."

**NOTABLE HIGHLIGHTS** (2-3 bullets)
- Pull the most impactful quotes or observations from the comment data
- Include partner name and account for context

**DISCLAIMER**
"**Disclaimer:** Use case data retrieved by searching coco/cortex code in SE comments, #coco in Partner Comments, or AI-Cortex Code feature flag. Numbers subject to change."

RULES:
- Use markdown tables for ALL tabular data — no prose paragraphs for data
- Keep executive summary to exactly 2-3 sentences + 3 bullets
- Do NOT add extra sections, commentary, sign-off, greeting, or subject line beyond the 7 sections above
- Do NOT prefix sections with "SECTION 1:", etc. — use only the heading name
- Pipeline values: $0 when none, $XK for thousands, $X.XM for millions
- Keep the ENTIRE email under 600 words
- Format large numbers with commas"""

prompt_input = st.text_area(
    "Prompt",
    value=default_prompt,
    height=300,
    help="Edit this prompt to customize the email output. Data summary above will be automatically included."
)

if st.button("Generate Email Summary", type="primary", key="email_generate"):
    full_prompt = f"""{prompt_input}

DATA:
{data_context}

Write the email:"""

    response_placeholder = st.empty()
    response_placeholder.info("Generating summary with Cortex Complete...")
    full_response = cortex_complete(conn, "claude-sonnet-4-5", full_prompt)
    response_placeholder.markdown(full_response)

    st.markdown("---")
    st.download_button(
        "Download as Markdown",
        data=full_response,
        file_name=f"coco_usecase_email_{datetime.now().strftime('%Y%m%d')}.md",
        mime="text/markdown"
    )

st.markdown("---")
st.caption("Powered by Snowflake Cortex Complete | Data sourced from CoCo Use Case Intelligence")
