import streamlit as st
import pandas as pd
from utils.queries import get_use_cases, get_distinct_partners, get_by_partner
from utils.cortex_helpers import cortex_complete

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")

st.title(":material/search_insights: Use Case Explorer")
st.caption(f"Deep dive into individual use cases with full comments, specialist notes, and AI insights | Region: {region}")

f1, f2, f3 = st.columns(3)
with f1:
    partners = get_distinct_partners(conn, region=region)
    selected_partner = st.selectbox("Partner", partners, key="dd_partner")
with f2:
    stage_options = [
        "1 - Discovery", "2 - Scoping", "3 - Technical / Business Validation",
        "4 - Use Case Won / Migration Plan", "5 - Implementation In Progress",
        "6 - Implementation Complete", "7 - Deployed"
    ]
    selected_stages = st.multiselect("Stages", stage_options, key="dd_stages")
with f3:
    source_filter = st.selectbox("Source", ["Overall", "PSE Confirmed", "Feature Flag"], key="dd_source")

stage_filter = selected_stages if selected_stages else None
df = get_use_cases(conn, partner=selected_partner, stage=stage_filter, region=region, source=source_filter)

if len(df) == 0:
    st.info("No use cases found.")
    st.stop()

if selected_partner and selected_partner != "All":
    partner_stats = df.agg({
        'USE_CASE_EACV': ['sum', 'count'],
        'IS_WON': 'sum',
        'IS_DEPLOYED': 'sum'
    })
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Use Cases ({selected_partner})", len(df))
    c2.metric("Total EACV", f"${df['USE_CASE_EACV'].sum()/1_000_000:.1f}M")
    c3.metric("Won", int(df['IS_WON'].sum()))
    c4.metric("Deployed", int(df['IS_DEPLOYED'].sum()))
    st.divider()

use_case_options = df.apply(lambda r: f"{r['USE_CASE_NAME']} | {r['PARTNER_NAME']} | ${(r['USE_CASE_EACV'] or 0):,.0f}", axis=1).tolist()
selected_idx = st.selectbox("Select Use Case", range(len(use_case_options)), format_func=lambda i: use_case_options[i], key="dd_uc_select")

row = df.iloc[selected_idx].to_dict()

st.divider()

st.subheader(row.get('USE_CASE_NAME', 'Unknown'))

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Partner", row.get('PARTNER_NAME', 'N/A'))
c2.metric("Account", row.get('ACCOUNT_NAME', 'N/A'))
eacv = row.get('USE_CASE_EACV', 0) or 0
c3.metric("EACV", f"${eacv:,.0f}")
c4.metric("Stage", row.get('USE_CASE_STAGE', 'N/A'))
days = row.get('DAYS_IN_CURRENT_STAGE')
c5.metric("Days in Stage", f"{int(days)}" if days else "N/A")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("CoCo Source", row.get('COCO_MENTION_SOURCE', 'N/A'))
c2.metric("Lead SE", row.get('ACCOUNT_LEAD_SE_NAME', 'N/A'))
tech = row.get('TECHNICAL_USE_CASE', '') or ''
c3.metric("Technical Type", tech[:35] if tech else 'N/A')
c4.metric("GVP", row.get('ACCOUNT_GVP', 'N/A'))
c5.metric("Theater", row.get('THEATER_NAME', 'N/A'))

st.divider()

info_col1, info_col2, info_col3 = st.columns(3)
with info_col1:
    st.markdown("**Workloads:**")
    st.markdown(row.get('WORKLOADS', 'None specified') or 'None specified')
with info_col2:
    st.markdown("**Competitors:**")
    st.markdown(row.get('COMPETITORS', 'None listed') or 'None listed')
with info_col3:
    st.markdown("**Prioritized Features:**")
    features = row.get('PRIORITIZED_FEATURES', '') or ''
    if features:
        for feat in features.split(';'):
            feat = feat.strip()
            if feat:
                badge = ":material/flag:" if 'Cortex Code' in feat else ":material/check:"
                st.markdown(f"{badge} {feat}")
    else:
        st.markdown("None specified")

date_col1, date_col2, date_col3, date_col4 = st.columns(4)
with date_col1:
    st.markdown(f"**Decision Date:** {row.get('DECISION_DATE', 'N/A') or 'N/A'}")
with date_col2:
    st.markdown(f"**Go-Live Date:** {row.get('GO_LIVE_DATE', 'N/A') or 'N/A'}")
with date_col3:
    st.markdown(f"**Created Date:** {row.get('CREATED_DATE', 'N/A') or 'N/A'}")
with date_col4:
    arr = row.get('ACCOUNT_ARR', 0)
    st.markdown(f"**Account ARR:** ${arr:,.0f}" if arr else "**Account ARR:** N/A")

st.divider()

st.subheader("Comments & Notes")

tab_se, tab_partner, tab_specialist, tab_next, tab_pain = st.tabs([
    "SE Comments", "Partner Comments", "Specialist Comments", "Next Steps", "MEDDPICC"
])

with tab_se:
    se_comments = row.get('SE_COMMENTS', '') or ''
    if se_comments:
        st.markdown(se_comments)
    else:
        st.info("No SE comments available.")

with tab_partner:
    partner_comments = row.get('PARTNER_COMMENTS', '') or ''
    if partner_comments:
        st.markdown(partner_comments)
    else:
        st.info("No partner comments available.")

with tab_specialist:
    specialist_comments = row.get('SPECIALIST_COMMENTS', '') or ''
    if specialist_comments:
        st.markdown(specialist_comments)
    else:
        st.info("No specialist comments available.")

with tab_next:
    next_steps = row.get('NEXT_STEPS', '') or ''
    if next_steps:
        st.markdown(next_steps)
    else:
        st.info("No next steps documented.")

with tab_pain:
    pain = row.get('MEDDPICC_IDENTIFY_PAIN', '') or ''
    metrics = row.get('MEDDPICC_METRICS', '') or ''
    if pain:
        st.markdown("**Identified Pain:**")
        st.markdown(pain)
    if metrics:
        st.markdown("**MEDDPICC Metrics:**")
        st.markdown(metrics)
    if not pain and not metrics:
        st.info("No MEDDPICC data available.")

st.divider()

st.subheader(":material/smart_toy: AI Analysis")

ai_mode = st.selectbox("Analysis Type", [
    "Full Analysis (Summary + Risk + Actions)",
    "Quick Summary",
    "Risk & Blockers Only",
    "CoCo Value Assessment",
    "Recommended Next Steps"
], key="dd_ai_mode")

if st.button("Generate AI Insights", type="primary", key="dd_ai_btn"):
    se = (row.get('SE_COMMENTS', '') or '')[:1500]
    pc = (row.get('PARTNER_COMMENTS', '') or '')[:1000]
    spec = (row.get('SPECIALIST_COMMENTS', '') or '')[:800]
    ns = (row.get('NEXT_STEPS', '') or '')[:500]

    base_context = f"""
**Use Case:** {row.get('USE_CASE_NAME', 'Unknown')}
**Partner:** {row.get('PARTNER_NAME', 'Unknown')} | **Account:** {row.get('ACCOUNT_NAME', 'Unknown')}
**Stage:** {row.get('USE_CASE_STAGE', 'Unknown')} | **EACV:** ${eacv:,.0f} | **Days in Stage:** {days}
**Technical Type:** {tech}
**Workloads:** {row.get('WORKLOADS', 'N/A')}
**Prioritized Features:** {features[:300]}
**CoCo Source:** {row.get('COCO_MENTION_SOURCE', 'N/A')}

**SE Comments (latest):** {se}
**Partner Comments:** {pc}
**Specialist Comments:** {spec}
**Next Steps:** {ns}"""

    prompts = {
        "Full Analysis (Summary + Risk + Actions)": f"""You are a Partner Solutions Engineering analyst. Analyze this CoCo (Cortex Code) use case:

1. **Summary** (2-3 sentences): What is the partner building and how is CoCo being used?
2. **Risk Assessment**: Is this use case at risk? Consider days in stage, stage, and comment sentiment. Rate as Low/Medium/High.
3. **Key Insights from Comments**: What are the most important signals from SE, partner, and specialist comments?
4. **Recommended Actions**: 2-3 specific next steps to accelerate this use case.
5. **CoCo Value Proposition**: How is Cortex Code specifically adding value here?
{base_context}""",
        "Quick Summary": f"""In 3-4 sentences, summarize this CoCo use case. What's happening, what stage is it in, and what are the key takeaways?
{base_context}""",
        "Risk & Blockers Only": f"""Analyze this use case for risk factors and blockers. Consider: time in stage vs typical, sentiment in comments, competitive threats, missing engagement, unclear next steps. Provide a risk rating (Low/Medium/High/Critical) with specific evidence.
{base_context}""",
        "CoCo Value Assessment": f"""Analyze how Cortex Code (CoCo) is specifically creating value in this use case. What features/capabilities are being used? What would be different without CoCo? Quantify the acceleration impact if possible.
{base_context}""",
        "Recommended Next Steps": f"""Based on all available context, provide 5 specific, actionable next steps to move this use case forward. For each step, specify WHO should do it, WHAT specifically, and by WHEN.
{base_context}"""
    }

    prompt = prompts[ai_mode]
    response_placeholder = st.empty()
    full_response = ""
    response_placeholder.info("Generating...")
    full_response = cortex_complete(conn, "claude-sonnet-4-5", prompt)
    response_placeholder.markdown(full_response)

st.divider()
sfdc_url = f"https://snowforce.lightning.force.com/lightning/r/vh__Deliverable__c/{row.get('USE_CASE_ID', '')}/view"
st.markdown(f"[Open in Salesforce]({sfdc_url})")
