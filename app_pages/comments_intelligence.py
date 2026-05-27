import streamlit as st
import pandas as pd
from utils.queries import get_comments_with_context, get_distinct_partners
from utils.cortex_helpers import cortex_complete

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
start_date = str(st.session_state.get("okr_start_date", "2026-05-01"))
end_date = str(st.session_state.get("okr_end_date", "2026-07-31"))

st.title(":material/smart_toy: Comments & AI Insights")
st.caption(f"AI-powered analysis of SE, Partner, and Specialist comments across all use cases | Region: {region}")
st.caption(":material/info: Partner filter not applied on this page — use the page-level dropdown below")

f1, f2, f3 = st.columns(3)
with f1:
    partners = get_distinct_partners(conn, region=region)
    selected_partner = st.selectbox("Partner", partners, key="ci_partner")
with f2:
    source_filter = st.selectbox("Comment Source", ["All", "PSE Confirmed", "Feature Flag"], key="ci_source")
with f3:
    analysis_type = st.selectbox("AI Analysis Mode", [
        "Portfolio Summary",
        "Risk Identification",
        "CoCo Usage Patterns",
        "Partner Engagement Quality",
        "Acceleration Opportunities"
    ], key="ci_analysis_type")

source = source_filter if source_filter != "All" else None
df = get_comments_with_context(conn, region=region, source=source, limit=100, start_date=start_date, end_date=end_date)

if selected_partner and selected_partner != "All":
    df = df[df['PARTNER_NAME'].str.contains(selected_partner, case=False, na=False)]

if len(df) == 0:
    st.info("No use cases with comments found.")
    st.stop()

st.divider()

st.subheader(f"Comments Overview ({len(df)} use cases)")

with_se = df[df['SE_COMMENTS'].notna() & (df['SE_COMMENTS'] != '')]
with_partner = df[df['PARTNER_COMMENTS'].notna() & (df['PARTNER_COMMENTS'] != '')]
with_specialist = df[df['SPECIALIST_COMMENTS'].notna() & (df['SPECIALIST_COMMENTS'] != '')]
with_features = df[df['PRIORITIZED_FEATURES'].notna() & df['PRIORITIZED_FEATURES'].str.contains('Cortex Code', case=False, na=False)]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("SE Comments", len(with_se))
c2.metric("Partner Comments", len(with_partner))
c3.metric("Specialist Comments", len(with_specialist))
c4.metric("Feature Flagged", len(with_features))
c5.metric("Total EACV", f"${df['USE_CASE_EACV'].sum()/1_000_000:.1f}M")

st.divider()

if st.button(f"Generate {analysis_type} Insights", type="primary", key="ci_generate"):
    comments_context = ""
    for _, row in df.head(20).iterrows():
        se = str(row.get('SE_COMMENTS', '') or '')[:400]
        pc = str(row.get('PARTNER_COMMENTS', '') or '')[:400]
        spec = str(row.get('SPECIALIST_COMMENTS', '') or '')[:300]
        feats = str(row.get('PRIORITIZED_FEATURES', '') or '')[:200]
        eacv_val = row.get('USE_CASE_EACV', 0)
        eacv_val = eacv_val if pd.notna(eacv_val) else 0
        comments_context += f"""
---
**{row['USE_CASE_NAME']}** | Partner: {row['PARTNER_NAME']} | Account: {row['ACCOUNT_NAME']}
Stage: {row['USE_CASE_STAGE']} | EACV: ${eacv_val:,.0f} | Days in Stage: {row.get('DAYS_IN_CURRENT_STAGE', 'N/A')} | Source: {row.get('COCO_MENTION_SOURCE', 'N/A')}
Features: {feats}
SE: {se}
Partner: {pc}
Specialist: {spec}
"""

    prompts = {
        "Portfolio Summary": f"""Analyze these {len(df)} CoCo partner use cases and provide:
1. **Executive Summary** (3-4 sentences): Overall portfolio health
2. **Key Themes**: Top 3-5 recurring patterns across use cases
3. **Success Stories**: Which use cases show strongest CoCo value?
4. **Areas of Concern**: Any systemic issues or bottlenecks?
5. **Recommendations**: Top 3 actions to improve overall portfolio velocity

Use Cases:
{comments_context}""",

        "Risk Identification": f"""Analyze these CoCo partner use cases for RISK signals. Look for:
- Use cases stalled too long (>60 days in non-deployed stage)
- Negative sentiment in comments
- Missing partner engagement
- Lack of clear next steps
- Competitor mentions

Provide a risk-ranked list with specific recommendations for each at-risk use case.

Use Cases:
{comments_context}""",

        "CoCo Usage Patterns": f"""Analyze how Cortex Code (CoCo) is being used across these partner use cases.
Look at SE and partner comments for mentions of:
- Specific CoCo features (CLI, skills, notebooks, SQL, agents)
- Migration acceleration patterns
- Code conversion activities
- Development workflows

Provide:
1. **CoCo Feature Distribution**: Which features are most commonly mentioned?
2. **Top Use Patterns**: How partners are leveraging CoCo
3. **Success Accelerators**: What CoCo capabilities drive fastest outcomes?
4. **Gaps**: Where could CoCo be used more effectively?

Use Cases:
{comments_context}""",

        "Partner Engagement Quality": f"""Assess the quality of partner engagement across these CoCo use cases by analyzing comments:

Rate each partner's engagement as: Strong, Moderate, Light, or Disengaged
Consider:
- Frequency and recency of partner comments
- Specificity and actionability of their updates
- Whether they mention #coco proactively
- Evidence of hands-on CoCo usage

Provide:
1. **Engagement Scorecard** by partner
2. **Best Practices**: What do highly-engaged partners do differently?
3. **Intervention Needed**: Partners that need outreach
4. **Enablement Gaps**: What training/support would help?

Use Cases:
{comments_context}""",

        "Acceleration Opportunities": f"""Identify the TOP opportunities to accelerate CoCo use case velocity.

For each opportunity, specify:
- The specific use case or group of use cases
- What's blocking progress
- Concrete action to unblock (who does what by when)
- Expected impact (EACV at risk or potential win)

Prioritize by: Impact (EACV) x Feasibility (ease of intervention)

Provide a prioritized action plan with the top 5-7 acceleration opportunities.

Use Cases:
{comments_context}"""
    }

    prompt = prompts[analysis_type]
    response_placeholder = st.empty()
    full_response = ""
    response_placeholder.info("Generating...")
    full_response = cortex_complete(conn, "claude-sonnet-4-5", prompt)
    response_placeholder.markdown(full_response)

st.divider()

st.subheader("Browse Comments")

for idx, row in df.head(25).iterrows():
    se = row.get('SE_COMMENTS', '') or ''
    pc = row.get('PARTNER_COMMENTS', '') or ''
    eacv = row.get('USE_CASE_EACV', 0) or 0
    days = row.get('DAYS_IN_CURRENT_STAGE', 0) or 0

    header = f"**{row['USE_CASE_NAME']}** | {row['PARTNER_NAME']} | ${eacv:,.0f} | {row['USE_CASE_STAGE']} | {int(days)}d"

    with st.expander(header, expanded=False):
        spec = row.get('SPECIALIST_COMMENTS', '') or ''
        feats = row.get('PRIORITIZED_FEATURES', '') or ''
        source = row.get('COCO_MENTION_SOURCE', '') or ''

        if feats:
            st.markdown(f":material/flag: **Features:** {feats}")
        st.markdown(f"**Source:** {source}")

        tab_se, tab_pc, tab_spec = st.tabs(["SE Comments", "Partner Comments", "Specialist Comments"])
        with tab_se:
            st.markdown(se[:3000] if se else "*No SE comments*")
        with tab_pc:
            st.markdown(pc[:3000] if pc else "*No partner comments*")
        with tab_spec:
            st.markdown(spec[:3000] if spec else "*No specialist comments*")

        if row.get('NEXT_STEPS'):
            st.markdown(f"**Next Steps:** {row['NEXT_STEPS']}")

        if st.button("AI Summary", key=f"ci_ai_{idx}"):
            mini_prompt = f"""In 3 sentences, summarize this use case. What's happening, what's the risk level, and what should happen next?

Use Case: {row['USE_CASE_NAME']}
Partner: {row['PARTNER_NAME']} | Stage: {row['USE_CASE_STAGE']} | EACV: ${eacv:,.0f} | Days: {days}
Source: {source} | Features: {feats[:200]}
SE: {se[:600]}
Partner: {pc[:600]}
Specialist: {spec[:400]}"""
            result = cortex_complete(conn, "claude-sonnet-4-5", mini_prompt)
            st.markdown(f"*{result}*")
