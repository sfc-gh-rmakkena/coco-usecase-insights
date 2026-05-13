import streamlit as st
import pandas as pd
from datetime import datetime
from snowflake.cortex import Complete
from utils.queries import get_summary_stats, get_by_partner, get_by_stage, get_source_breakdown, get_by_region, get_email_summary_data

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")

st.title(":material/mail: Executive Email Summary")
st.caption(f"AI-generated use-case-focused executive summary | Region: {region}")

source_toggle = st.segmented_control("Source", ["Overall", "PSE Confirmed", "Feature Flag"], default="Overall", key="email_source")

with st.spinner("Loading data..."):
    stats = get_summary_stats(conn, region=region, source=source_toggle)
    partner_data = get_email_summary_data(conn, region=region, source=source_toggle)
    stage_data = get_by_stage(conn, region=region, source=source_toggle)
    source_data = get_source_breakdown(conn, region=region)
    region_data = get_by_region(conn, source=source_toggle)

if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

s = stats.iloc[0]

st.subheader("Data Summary")
with st.expander("View Metrics", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Use Cases", int(s['TOTAL_USE_CASES']))
    c2.metric("Total EACV", f"${s['TOTAL_EACV']/1_000_000:.1f}M" if s['TOTAL_EACV'] else "$0")
    c3.metric("Partners", int(s['TOTAL_PARTNERS']))
    c4.metric("Accounts", int(s['TOTAL_ACCOUNTS']))

    if len(stage_data) > 0:
        st.dataframe(stage_data, hide_index=True, use_container_width=True)
    if len(partner_data) > 0:
        st.dataframe(partner_data.head(20), hide_index=True, use_container_width=True)

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

data_context = f"""
=== FILTERS: {source_toggle} Use Cases | {region} Region ===

=== HEADLINE METRICS ===
- {int(s['TOTAL_USE_CASES'])} Use Cases | {int(s['TOTAL_PARTNERS'])} Partners | {int(s['TOTAL_ACCOUNTS'])} Accounts | ${s['TOTAL_EACV']/1_000_000:.1f}M EACV
- Active Pipeline (1-3): {int(s['ACTIVE_COUNT'])} (${s['ACTIVE_EACV']/1_000_000:.1f}M)
- Won (4): {int(s['WON_COUNT'])} (${s['WON_EACV']/1_000_000:.1f}M)
- In Implementation (5-6): {int(s['IMPL_COUNT'])} (${s['IMPL_EACV']/1_000_000:.1f}M)
- Deployed (7): {int(s['DEPLOYED_COUNT'])} (${s['DEPLOYED_EACV']/1_000_000:.1f}M)
- PSE Confirmed: {int(s['PARTNER_CONFIRMED_COUNT'])} | Feature Flagged: {int(s['FEATURE_FLAG_COUNT'])}

=== DETECTION SOURCE ===
{source_ctx}

=== REGIONAL BREAKDOWN ===
{region_ctx}

=== PIPELINE BY STAGE ===
{stage_ctx}

=== TOP 20 PARTNERS (by EACV) ===
{partner_ctx}
"""

st.divider()
st.subheader("Generate Email")

default_prompt = """Write a concise executive email summarizing CoCo (Cortex Code) partner use case activity. Follow this format:

**EXECUTIVE SUMMARY** (3-4 sentences)
- Lead with total use case count, EACV, and partner count
- Highlight pipeline stage distribution
- Note detection source mix (SE comments vs Partner confirmed vs Feature Flag)

**USE CASE PIPELINE** (markdown table)
| Stage | Count | EACV | Avg Days |

**TOP PARTNERS** (markdown table)
| Partner | Use Cases | EACV | Active | Won | Impl | Deployed |
Show top 15 partners sorted by EACV.

**REGIONAL BREAKDOWN** (markdown table)
| Region | Use Cases | EACV | Partners |

**KEY HIGHLIGHTS**
- 3-5 bullet points on notable wins, deployments, or acceleration stories

**DISCLAIMER**
"Use case data retrieved by searching coco/cortex code in SE comments, #coco in Partner Comments, or AI-Cortex Code feature flag. Numbers subject to change."

RULES:
- Use markdown tables for all tabular data
- Format currency as $XK or $X.XM
- Keep executive summary to 3-4 sentences
- Do NOT add sign-off or extra sections"""

prompt_input = st.text_area("Prompt", value=default_prompt, height=250, key="email_prompt")

if st.button("Generate Email Summary", type="primary", key="email_generate"):
    full_prompt = f"""{prompt_input}

DATA:
{data_context}

Write the email:"""

    response_placeholder = st.empty()
    full_response = ""
    stream = Complete("claude-sonnet-4-5", full_prompt, stream=True)
    for chunk in stream:
        full_response += chunk
        response_placeholder.markdown(full_response + "▌")
    response_placeholder.markdown(full_response)

    st.divider()
    st.download_button(
        "Download as Markdown",
        data=full_response,
        file_name=f"coco_usecase_summary_{datetime.now().strftime('%Y%m%d')}.md",
        mime="text/markdown"
    )
