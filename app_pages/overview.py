import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from utils.queries import get_summary_stats, get_by_partner, get_by_stage, get_by_region, get_by_technical_type, get_source_breakdown, get_by_account_gvp

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")

st.title(":material/monitoring: CoCo Use Case Adoption Overview")
st.caption(f"High-level metrics across all partner CoCo use cases | Region: {region}")

with st.expander(":material/info: How Use Cases Are Retrieved", expanded=False):
    st.markdown("""
    Use cases must meet **BOTH** criteria below to be included:
    
    **1. CoCo Mention Criteria** (at least one must match):
    
    | Field | Search Terms |
    |-------|--------------|
    | **SE Comments** | "coco" OR "cortex code" |
    | **Partner Comments** | "#coco" |
    | **Prioritized Features** | "AI - Cortex Code" (Feature Flag) |
    
    **2. Date Criteria** (based on use case stage):
    
    | Stage | Date Field | Requirement |
    |-------|------------|-------------|
    | **1-4** (Discovery to Won) | Decision Date | > Nov 20, 2025 |
    | **5-7** (Implementation to Deployed) | Go Live Date | > Nov 20, 2025 |
    """)

stats = get_summary_stats(conn, region=region)
if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

s = stats.iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Use Cases", int(s['TOTAL_USE_CASES']), f"{int(s['TOTAL_PARTNERS'])} partners")
c2.metric("Total EACV", f"${s['TOTAL_EACV']/1_000_000:.1f}M" if s['TOTAL_EACV'] else "$0")
c3.metric("Accounts Engaged", int(s['TOTAL_ACCOUNTS']))
c4.metric("Avg Days in Stage", f"{s['AVG_DAYS_IN_STAGE']:.0f}" if s['AVG_DAYS_IN_STAGE'] else "N/A")
c5.metric("PSE Confirmed", int(s['PARTNER_CONFIRMED_COUNT']))

st.divider()

st.subheader("Pipeline Stages")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Active Pipeline (1-3)", int(s['ACTIVE_COUNT']), f"${s['ACTIVE_EACV']/1_000_000:.1f}M" if s['ACTIVE_EACV'] else "$0")
c2.metric("Won (4)", int(s['WON_COUNT']), f"${s['WON_EACV']/1_000_000:.1f}M" if s['WON_EACV'] else "$0")
c3.metric("In Implementation (5-6)", int(s['IMPL_COUNT']), f"${s['IMPL_EACV']/1_000_000:.1f}M" if s['IMPL_EACV'] else "$0")
c4.metric("Deployed (7)", int(s['DEPLOYED_COUNT']), f"${s['DEPLOYED_EACV']/1_000_000:.1f}M" if s['DEPLOYED_EACV'] else "$0")

st.divider()

st.subheader("CoCo Detection Source Breakdown")
source_data = get_source_breakdown(conn, region=region)
if len(source_data) > 0:
    src_col1, src_col2 = st.columns([1, 2])
    with src_col1:
        for _, row in source_data.iterrows():
            label = row['COCO_MENTION_SOURCE']
            icon = {"SE_COMMENTS": ":material/engineering:", "PARTNER_COMMENTS": ":material/handshake:", "FEATURE_FLAG": ":material/flag:", "MULTIPLE": ":material/layers:"}.get(label, ":material/help:")
            st.metric(f"{icon} {label}", int(row['USE_CASE_COUNT']), f"${row['TOTAL_EACV']/1_000_000:.1f}M | {int(row['PARTNER_COUNT'])} partners")
    with src_col2:
        fig = px.pie(
            source_data, values='USE_CASE_COUNT', names='COCO_MENTION_SOURCE',
            hole=0.4, color_discrete_sequence=['#3498db', '#2ecc71', '#e74c3c', '#95a5a6']
        )
        fig.update_layout(height=250, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Pipeline by Stage")
    stage_data = get_by_stage(conn, region=region)
    if len(stage_data) > 0:
        fig = px.bar(
            stage_data, x='USE_CASE_STAGE', y='TOTAL_EACV',
            color='USE_CASE_COUNT', text='USE_CASE_COUNT',
            labels={'TOTAL_EACV': 'EACV ($)', 'USE_CASE_STAGE': 'Stage', 'USE_CASE_COUNT': 'Count'},
            color_continuous_scale='Blues'
        )
        fig.update_layout(height=380, showlegend=False)
        fig.update_yaxes(tickformat="$,.0f")
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("EACV by Region")
    region_data = get_by_region(conn)
    if len(region_data) > 0:
        fig = px.pie(
            region_data, values='TOTAL_EACV', names='REGION', hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Top Partners by EACV")
    partner_data = get_by_partner(conn, region=region)
    if len(partner_data) > 0:
        top = partner_data.head(15)
        fig = px.bar(
            top, x='TOTAL_EACV', y='PARTNER_NAME', orientation='h',
            color='WON_COUNT',
            labels={'TOTAL_EACV': 'EACV ($)', 'PARTNER_NAME': '', 'WON_COUNT': 'Won'},
            color_continuous_scale='Blues',
            text=top['USE_CASE_COUNT'].apply(lambda x: f"{int(x)} UCs")
        )
        fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
        fig.update_xaxes(tickformat="$,.0f")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Top Technical Use Case Types")
    tech_data = get_by_technical_type(conn, region=region)
    if len(tech_data) > 0:
        fig = px.bar(
            tech_data.head(12), x='TOTAL_EACV', y='TECHNICAL_USE_CASE', orientation='h',
            color='USE_CASE_COUNT',
            labels={'TOTAL_EACV': 'EACV ($)', 'TECHNICAL_USE_CASE': '', 'USE_CASE_COUNT': 'Count'},
            color_continuous_scale='Greens'
        )
        fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
        fig.update_xaxes(tickformat="$,.0f")
        st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Top GVP Organizations")
gvp_data = get_by_account_gvp(conn, region=region)
if len(gvp_data) > 0:
    fig = px.bar(
        gvp_data.head(10), x='ACCOUNT_GVP', y='TOTAL_EACV',
        color='USE_CASE_COUNT', text='USE_CASE_COUNT',
        labels={'TOTAL_EACV': 'EACV ($)', 'ACCOUNT_GVP': 'GVP', 'USE_CASE_COUNT': 'Count'}
    )
    fig.update_layout(height=350, showlegend=False)
    fig.update_yaxes(tickformat="$,.0f")
    fig.update_traces(textposition='outside')
    st.plotly_chart(fig, use_container_width=True)
