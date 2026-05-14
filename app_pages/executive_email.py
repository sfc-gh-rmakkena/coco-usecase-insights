import streamlit as st
import pandas as pd
from datetime import datetime
from utils.queries import (
    get_summary_stats, get_by_partner, get_by_stage, get_source_breakdown,
    get_by_region, get_email_summary_data, get_use_case_type_patterns,
    get_workload_patterns, get_competitive_landscape, get_comment_narratives,
    get_partner_workload_cross, get_regional_themes, get_regional_comment_narratives,
)
from utils.cortex_helpers import cortex_complete

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
partner_filter = st.session_state.get("selected_partner", "All")

st.title(":material/mail: Executive Email Summary")
filter_label = f"Region: {region}"
if partner_filter and partner_filter != "All":
    filter_label += f" | Partner: {partner_filter}"
st.caption(f"AI-generated narrative with use case patterns, regional themes & partner insights | {filter_label}")

source_toggle = st.segmented_control("Source", ["Overall", "PSE Confirmed", "Feature Flag"], default="Overall", key="email_source")

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
    noam_comments = get_regional_comment_narratives(conn, "NoAM", source=source_toggle)
    emea_comments = get_regional_comment_narratives(conn, "EMEA", source=source_toggle)
    apj_comments = get_regional_comment_narratives(conn, "APJ", source=source_toggle)

if partner_filter and partner_filter != "All":
    partner_data = _apply_partner_filter(partner_data)
    comment_data = _apply_partner_filter(comment_data)
    partner_workloads = _apply_partner_filter(partner_workloads)

if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

s = stats.iloc[0]

st.subheader("Data Summary")
with st.expander("View Metrics & Patterns", expanded=False):
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

partner_ctx = ""
for _, p in partner_data.head(20).iterrows():
    eacv = p.get('TOTAL_EACV', 0) or 0
    partner_ctx += f"  - {p['PARTNER_NAME']}: {int(p['USE_CASE_COUNT'])} use cases, ${eacv/1000:.0f}K EACV, Active: {int(p.get('ACTIVE_PIPELINE', 0))}, Won: {int(p.get('WON', 0))}, Impl: {int(p.get('IN_IMPL', 0))}, Deployed: {int(p.get('DEPLOYED', 0))}\n"

stage_ctx = ""
for _, sg in stage_data.iterrows():
    eacv = sg.get('TOTAL_EACV', 0) or 0
    stage_ctx += f"  - {sg['USE_CASE_STAGE']}: {int(sg['USE_CASE_COUNT'])} use cases, ${eacv/1000:.0f}K EACV, Avg {int(sg.get('AVG_DAYS', 0) or 0)} days\n"

source_ctx = ""
for _, src in source_data.iterrows():
    source_ctx += f"  - {src['COCO_MENTION_SOURCE']}: {int(src['USE_CASE_COUNT'])} use cases, {int(src['PARTNER_COUNT'])} partners\n"

region_ctx = ""
for _, rg in region_data.iterrows():
    eacv = rg.get('TOTAL_EACV', 0) or 0
    region_ctx += f"  - {rg['REGION']}: {int(rg['USE_CASE_COUNT'])} use cases, ${eacv/1000:.0f}K EACV, {int(rg['PARTNER_COUNT'])} partners\n"

type_ctx = ""
for _, tp in type_patterns.iterrows():
    eacv = tp.get('TOTAL_EACV', 0) or 0
    partners_list = str(tp.get('PARTNERS_INVOLVED', ''))[:200]
    type_ctx += f"  - {tp['TECHNICAL_USE_CASE']}: {int(tp['USE_CASE_COUNT'])} use cases, ${eacv/1000:.0f}K EACV, {int(tp['PARTNER_COUNT'])} partners, {int(tp['WON_PLUS'])} won+impl+deployed | Partners: {partners_list}\n"

workload_ctx = ""
for _, wl in workload_data.iterrows():
    eacv = wl.get('TOTAL_EACV', 0) or 0
    workload_ctx += f"  - {wl['WORKLOADS']}: {int(wl['USE_CASE_COUNT'])} use cases, ${eacv/1000:.0f}K EACV, {int(wl['PARTNER_COUNT'])} partners\n"

competitive_ctx = ""
for _, comp in competitive_data.iterrows():
    eacv = comp.get('TOTAL_EACV', 0) or 0
    competitive_ctx += f"  - {comp['COMPETITORS']}: {int(comp['USE_CASE_COUNT'])} use cases, ${eacv/1000:.0f}K EACV, {int(comp['PARTNER_COUNT'])} partners\n"

partner_wl_ctx = ""
for _, pw in partner_workloads.iterrows():
    eacv = pw.get('TOTAL_EACV', 0) or 0
    partner_wl_ctx += f"  - {pw['PARTNER_NAME']} ({int(pw['TOTAL_USE_CASES'])} UCs, ${eacv/1000:.0f}K): AI={int(pw['AI_USE_CASES'])}, DE={int(pw['DE_USE_CASES'])}, Analytics={int(pw['ANALYTICS_USE_CASES'])}, Platform={int(pw['PLATFORM_USE_CASES'])}, Apps={int(pw['APPS_USE_CASES'])}\n"

comment_ctx = ""
for _, cm in comment_data.head(20).iterrows():
    eacv = cm.get('USE_CASE_EACV', 0) or 0
    se_snip = str(cm.get('SE_COMMENTS_EXCERPT', '') or '')[:300].replace('\n', ' ')
    partner_snip = str(cm.get('PARTNER_COMMENTS_EXCERPT', '') or '')[:300].replace('\n', ' ')
    spec_snip = str(cm.get('SPECIALIST_COMMENTS_EXCERPT', '') or '')[:200].replace('\n', ' ')
    pain = str(cm.get('CUSTOMER_PAIN', '') or '')[:200].replace('\n', ' ')
    entry = f"  [{cm['PARTNER_NAME']} | {cm['ACCOUNT_NAME']} | {cm['USE_CASE_STAGE']} | ${eacv/1000:.0f}K | Type: {cm.get('TECHNICAL_USE_CASE', 'N/A')} | Workload: {cm.get('WORKLOADS', 'N/A')} | Competitor: {cm.get('COMPETITORS', 'N/A')} | Source: {cm['COCO_MENTION_SOURCE']}]"
    if se_snip:
        entry += f"\n    SE: {se_snip}"
    if partner_snip:
        entry += f"\n    PARTNER: {partner_snip}"
    if spec_snip:
        entry += f"\n    SPECIALIST: {spec_snip}"
    if pain:
        entry += f"\n    CUSTOMER PAIN: {pain}"
    comment_ctx += entry + "\n\n"


def _build_region_theme_ctx(df, region_name):
    region_df = df[df['REGION'] == region_name]
    if len(region_df) == 0:
        return f"  No data for {region_name}\n"

    total_ucs = int(region_df['USE_CASE_COUNT'].sum())
    total_eacv = region_df['TOTAL_EACV'].sum() or 0
    total_partners = int(region_df['PARTNER_COUNT'].max()) if len(region_df) > 0 else 0

    ctx = f"  Total: {total_ucs} use cases, ${total_eacv/1_000_000:.1f}M EACV\n"

    type_agg = region_df.groupby('TECHNICAL_USE_CASE').agg({'USE_CASE_COUNT': 'sum', 'TOTAL_EACV': 'sum'}).reset_index().sort_values('TOTAL_EACV', ascending=False).head(8)
    ctx += "  Top Use Case Types:\n"
    for _, row in type_agg.iterrows():
        if row['TECHNICAL_USE_CASE']:
            eacv = row.get('TOTAL_EACV', 0) or 0
            ctx += f"    - {row['TECHNICAL_USE_CASE']}: {int(row['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K\n"

    wl_agg = region_df.groupby('WORKLOADS').agg({'USE_CASE_COUNT': 'sum', 'TOTAL_EACV': 'sum'}).reset_index().sort_values('USE_CASE_COUNT', ascending=False).head(5)
    ctx += "  Top Workloads:\n"
    for _, row in wl_agg.iterrows():
        if row['WORKLOADS']:
            eacv = row.get('TOTAL_EACV', 0) or 0
            ctx += f"    - {row['WORKLOADS']}: {int(row['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K\n"

    comp_agg = region_df[region_df['COMPETITORS'].notna()].groupby('COMPETITORS').agg({'USE_CASE_COUNT': 'sum'}).reset_index().sort_values('USE_CASE_COUNT', ascending=False).head(5)
    ctx += "  Top Competitors:\n"
    for _, row in comp_agg.iterrows():
        ctx += f"    - {row['COMPETITORS']}: {int(row['USE_CASE_COUNT'])} UCs\n"

    return ctx


def _build_region_comments_ctx(df, region_name):
    ctx = ""
    for _, cm in df.head(8).iterrows():
        eacv = cm.get('USE_CASE_EACV', 0) or 0
        se_snip = str(cm.get('SE_COMMENTS_EXCERPT', '') or '')[:250].replace('\n', ' ')
        partner_snip = str(cm.get('PARTNER_COMMENTS_EXCERPT', '') or '')[:250].replace('\n', ' ')
        entry = f"  [{cm['PARTNER_NAME']} | {cm['ACCOUNT_NAME']} | {cm['USE_CASE_STAGE']} | ${eacv/1000:.0f}K | {cm.get('TECHNICAL_USE_CASE', 'N/A')}]"
        if se_snip:
            entry += f"\n    SE: {se_snip}"
        if partner_snip:
            entry += f"\n    PARTNER: {partner_snip}"
        ctx += entry + "\n"
    return ctx if ctx else f"  No comments for {region_name}\n"


noam_theme_ctx = _build_region_theme_ctx(regional_themes, "NoAM")
emea_theme_ctx = _build_region_theme_ctx(regional_themes, "EMEA")
apj_theme_ctx = _build_region_theme_ctx(regional_themes, "APJ")

noam_comments_ctx = _build_region_comments_ctx(noam_comments, "NoAM")
emea_comments_ctx = _build_region_comments_ctx(emea_comments, "EMEA")
apj_comments_ctx = _build_region_comments_ctx(apj_comments, "APJ")

partner_filter_ctx = ""
if partner_filter and partner_filter != "All":
    partner_filter_ctx = f"\n=== PARTNER FOCUS: {partner_filter} ===\nAll data below is filtered to show only use cases involving {partner_filter}.\n"

data_context = f"""
=== FILTERS: {source_toggle} Use Cases | {region} Region{' | Partner: ' + partner_filter if partner_filter and partner_filter != 'All' else ''} ===
{partner_filter_ctx}
=== HEADLINE METRICS ===
- {int(s['TOTAL_USE_CASES'])} Use Cases | {int(s['TOTAL_PARTNERS'])} Partners | {int(s['TOTAL_ACCOUNTS'])} Accounts | ${s['TOTAL_EACV']/1_000_000:.1f}M EACV
- Active Pipeline (1-3): {int(s['ACTIVE_COUNT'])} (${s['ACTIVE_EACV']/1_000_000:.1f}M)
- Won (4): {int(s['WON_COUNT'])} (${s['WON_EACV']/1_000_000:.1f}M)
- In Implementation (5-6): {int(s['IMPL_COUNT'])} (${s['IMPL_EACV']/1_000_000:.1f}M)
- Deployed (7): {int(s['DEPLOYED_COUNT'])} (${s['DEPLOYED_EACV']/1_000_000:.1f}M)
- PSE Confirmed: {int(s['PARTNER_CONFIRMED_COUNT'])} | Feature Flagged: {int(s['FEATURE_FLAG_COUNT'])} | SE Confirmed: {int(s['SE_CONFIRMED_COUNT'])}

=== DETECTION SOURCE ===
{source_ctx}

=== REGIONAL SUMMARY ===
{region_ctx}

=== NoAM DEEP DIVE (use case types, workloads, competitors) ===
{noam_theme_ctx}
  Key Narratives:
{noam_comments_ctx}

=== EMEA DEEP DIVE (use case types, workloads, competitors) ===
{emea_theme_ctx}
  Key Narratives:
{emea_comments_ctx}

=== APJ DEEP DIVE (use case types, workloads, competitors) ===
{apj_theme_ctx}
  Key Narratives:
{apj_comments_ctx}

=== PIPELINE BY STAGE ===
{stage_ctx}

=== USE CASE TYPE PATTERNS (Technical Use Case categories with partner breakdown) ===
{type_ctx}

=== WORKLOAD PATTERNS (Which Snowflake workloads are CoCo use cases mapped to) ===
{workload_ctx}

=== COMPETITIVE LANDSCAPE (Who are we displacing in CoCo use cases) ===
{competitive_ctx}

=== PARTNER x WORKLOAD MIX (Top 15 partners broken down by workload type) ===
{partner_wl_ctx}

=== TOP 20 PARTNERS (by EACV) ===
{partner_ctx}

=== USE CASE NARRATIVES (Top 20 by EACV — SE comments, Partner comments, Specialist comments, customer pain) ===
{comment_ctx}
"""

st.divider()
st.subheader("Generate Email")

default_prompt = """Write a rich, narrative-driven executive email summarizing CoCo (Cortex Code) partner use case activity. The email should tell the STORY of what's happening — not just recite numbers. Follow this structure:

**EXECUTIVE SUMMARY** (4-5 sentences)
- Lead with the headline numbers (use cases, EACV, partners)
- Call out the dominant USE CASE PATTERNS (e.g., "BI Analytics and AI Conversational Assistants dominate", "Teradata/legacy migrations are a recurring theme")
- Highlight where CoCo is accelerating outcomes based on the comments

**USE CASE PATTERN ANALYSIS** (narrative paragraphs, not just tables)
- Group use cases into 3-4 dominant themes/patterns you observe (e.g., "Migration Acceleration", "AI-Native Development", "Data Engineering Modernization", "Partner-Led BI Consolidation")
- For each pattern: describe what you're seeing, which partners are driving it, cite specific examples from the comments, and quantify with EACV
- Call out any emerging patterns (new types gaining traction)

**REGIONAL THEMES** (one narrative paragraph per region: NoAM, EMEA, APJ)
- For each region, describe the dominant use case patterns, key partners, competitive dynamics, and notable deals
- Highlight what makes each region unique — different workload mix, competitive landscape, or maturity
- Use specific examples from the regional comments to support the narrative
- Include a markdown summary table per region with columns: Top Use Case Types | Key Partners | EACV

**PARTNER COMMENT HIGHLIGHTS** (3-5 notable excerpts)
- Pull the most insightful quotes from SE comments, Partner comments, and Specialist comments
- Focus on quotes that show CoCo impact, adoption momentum, or customer excitement
- Include the account name and partner for context

**COMPETITIVE DISPLACEMENT NARRATIVE** (1 paragraph)
- Summarize the competitive landscape — which platforms are being displaced, which competitors appear most often
- Tie this to the use case patterns (e.g., "Teradata migrations driving the largest EACV deals")

**PIPELINE & PARTNERS** (markdown tables)

| Stage | Count | EACV | Avg Days |

| Partner | Use Cases | EACV | AI | DE | Analytics | Won+ |
Show top 12 partners with workload mix columns.

**KEY CALLS TO ACTION**
- 3-4 specific, actionable insights (e.g., "Double down on migration acceleration with Accenture and Deloitte", "Enable AI Conversational Assistant workshops for mid-tier partners")

**DISCLAIMER**
"Use case data retrieved by searching coco/cortex code in SE comments, #coco in Partner Comments, or AI-Cortex Code feature flag. Numbers subject to change."

RULES:
- Write in a narrative, storytelling style — connect the dots between data points
- Use specific examples from the comments to support your analysis
- Cite partner names and account names when referencing specific stories
- Dedicate significant depth to the REGIONAL THEMES section — each region should feel like its own mini-analysis
- Use markdown tables only for pipeline/partner/region summaries
- Format currency as $XK or $X.XM
- Keep the tone executive but insightful — this should feel like analyst commentary, not a data dump
- Do NOT add sign-off, greeting, or subject line"""

prompt_input = st.text_area("Prompt", value=default_prompt, height=350, key="email_prompt")

if st.button("Generate Email Summary", type="primary", key="email_generate"):
    full_prompt = f"""{prompt_input}

DATA:
{data_context}

Write the email:"""

    response_placeholder = st.empty()
    response_placeholder.info("Generating narrative... (this takes ~30s)")
    full_response = cortex_complete(conn, "claude-sonnet-4-5", full_prompt)
    response_placeholder.markdown(full_response)

    st.divider()
    st.download_button(
        "Download as Markdown",
        data=full_response,
        file_name=f"coco_usecase_narrative_{datetime.now().strftime('%Y%m%d')}.md",
        mime="text/markdown"
    )
