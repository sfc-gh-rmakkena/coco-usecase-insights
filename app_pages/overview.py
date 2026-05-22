import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from utils.queries import get_adoption_overview, get_adoption_by_partner, get_adoption_by_stage, get_adoption_by_region, get_by_technical_type, get_by_account_gvp
from utils import resolve_partner_filter

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])
start_date = str(st.session_state.get("okr_start_date", "2026-05-01"))
end_date = str(st.session_state.get("okr_end_date", "2026-07-31"))

st.title(":material/monitoring: CoCo Use Case Adoption Overview")
st.caption(f"High-level metrics across all partner CoCo use cases | Region: {region} | {start_date} to {end_date}")

with st.expander(":material/info: How Use Cases Are Retrieved", expanded=False):
    st.markdown("""
    Use cases must meet **BOTH** criteria below to be included:
    
    **1. CoCo Attribution Criteria** (at least one must match):
    
    | Method | How It Works |
    |--------|-------------|
    | **SE Comments** | Contains "coco" OR "cortex code" |
    | **Partner Comments** | Contains "#coco" |
    | **Feature Flag** | Prioritized Features includes "AI - Cortex Code" |
    | **Account-Level Usage** | Customer account has actual CoCo credit consumption AND partner is mapped to that account |
    
    **2. Date Criteria** (based on use case stage):
    
    | Stage | Date Field | Requirement |
    |-------|------------|-------------|
    | **1-4** (Discovery to Won) | Decision Date | Within selected date range |
    | **5-7** (Implementation to Deployed) | Go Live Date | Within selected date range |
    
    **CoCo Partner Attribution — How It Works:**
    
    1. **Account-level (Product Usage):** Customer account consuming CoCo credits + partner mapped → partner gets attribution
    2. **Use case-level (Feature Flag):** Use case tagged with "AI - Cortex Code" + partner attached
    3. **Use case-level (Comments):** SE writes "coco"/"cortex code" OR partner writes "#coco"
    """)

stats = get_adoption_overview(conn, start_date=start_date, end_date=end_date, region=region, partners=resolve_partner_filter(selected_partners) if selected_partners else None)
if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

s = stats.iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Use Cases", int(s['TOTAL_USE_CASES']), f"{int(s['TOTAL_PARTNERS'])} partners")
c2.metric("Total EACV", f"${s['TOTAL_EACV']/1_000_000:.1f}M" if s['TOTAL_EACV'] else "$0")
c3.metric("CoCo Use Cases", int(s['COCO_USE_CASES']), f"{s['COCO_PCT']}%")
c4.metric("Avg Days in Stage", f"{s['AVG_DAYS_IN_STAGE']:.0f}" if s['AVG_DAYS_IN_STAGE'] else "N/A")
c5.metric("Accounts Engaged", int(s['TOTAL_ACCOUNTS']))

st.divider()

# OKR Progress Visual
st.subheader("OKR Progress: 50% CoCo Adoption Target")
target_pct = 50
current_pct = float(s['COCO_PCT'] or 0)
coco_ucs = int(s['COCO_USE_CASES'])
total_ucs = int(s['TOTAL_USE_CASES'])
target_ucs = int(total_ucs * 0.5)
gap_ucs = max(0, target_ucs - coco_ucs)

okr_col1, okr_col2 = st.columns([2, 1])
with okr_col1:
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=current_pct,
        delta={'reference': target_pct, 'suffix': '%', 'increasing': {'color': '#2ecc71'}, 'decreasing': {'color': '#e74c3c'}},
        gauge={
            'axis': {'range': [0, 100], 'ticksuffix': '%'},
            'bar': {'color': '#29B5E8'},
            'steps': [
                {'range': [0, 25], 'color': 'rgba(231,76,60,0.15)'},
                {'range': [25, 50], 'color': 'rgba(243,156,18,0.15)'},
                {'range': [50, 75], 'color': 'rgba(241,196,15,0.15)'},
                {'range': [75, 100], 'color': 'rgba(46,204,113,0.15)'},
            ],
            'threshold': {'line': {'color': 'red', 'width': 3}, 'thickness': 0.8, 'value': target_pct}
        },
        number={'suffix': '%'},
        title={'text': f"CoCo Adoption (Target: {target_pct}%)"}
    ))
    fig.update_layout(height=280, margin=dict(t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)
with okr_col2:
    if current_pct >= target_pct:
        st.success(f"TARGET MET: {current_pct}%")
    else:
        st.warning(f"Below target: {current_pct}%")
    st.metric("CoCo UCs", f"{coco_ucs} / {total_ucs}")
    st.metric("Target (50%)", f"{target_ucs} UCs")
    st.metric("Gap", f"{gap_ucs} UCs needed" if gap_ucs > 0 else "Met!")

st.divider()

st.subheader("Pipeline Stages")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Validation (3)", int(s['VALIDATION_COUNT']), f"${s['VALIDATION_EACV']/1_000_000:.1f}M" if s['VALIDATION_EACV'] else "$0")
c2.metric("Won (4)", int(s['WON_COUNT']), f"${s['WON_EACV']/1_000_000:.1f}M" if s['WON_EACV'] else "$0")
c3.metric("In Implementation (5-6)", int(s['IMPL_COUNT']), f"${s['IMPL_EACV']/1_000_000:.1f}M" if s['IMPL_EACV'] else "$0")
c4.metric("Deployed (7)", int(s['DEPLOYED_COUNT']), f"${s['DEPLOYED_EACV']/1_000_000:.1f}M" if s['DEPLOYED_EACV'] else "$0")

st.divider()

st.subheader("CoCo Detection Source Breakdown")
src_col1, src_col2 = st.columns([1, 1])
with src_col1:
    st.metric(":material/chat: SE Comments", int(s['SE_CONFIRMED_COUNT']))
    st.metric(":material/handshake: Partner Comments", int(s['PARTNER_CONFIRMED_COUNT']))
with src_col2:
    st.metric(":material/flag: Feature Flag", int(s['FEATURE_FLAG_COUNT']))
    st.metric(":material/cloud: Account-Level Usage", int(s['ACCOUNT_LEVEL_COUNT']))
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Pipeline by Stage")
    stage_data = get_adoption_by_stage(conn, start_date=start_date, end_date=end_date, region=region)
    if len(stage_data) > 0:
        fig = px.bar(
            stage_data, x='USE_CASE_STAGE', y='TOTAL_EACV',
            color='TOTAL_USE_CASES', text='TOTAL_USE_CASES',
            labels={'TOTAL_EACV': 'EACV ($)', 'USE_CASE_STAGE': 'Stage', 'TOTAL_USE_CASES': 'Count'},
            color_continuous_scale='Blues'
        )
        fig.update_layout(height=380, showlegend=False)
        fig.update_yaxes(tickformat="$,.0f")
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("EACV by Region")
    region_data = get_adoption_by_region(conn, start_date=start_date, end_date=end_date)
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
    partner_data = get_adoption_by_partner(conn, start_date=start_date, end_date=end_date, region=region)
    if selected_partners and 'PARTNER_NAME' in partner_data.columns:
        partner_names = resolve_partner_filter(selected_partners)
        partner_data = partner_data[partner_data['PARTNER_NAME'].isin(partner_names)]
    if len(partner_data) > 0:
        top = partner_data.head(15)
        fig = px.bar(
            top, x='TOTAL_EACV', y='PARTNER_NAME', orientation='h',
            color='COCO_PCT',
            labels={'TOTAL_EACV': 'EACV ($)', 'PARTNER_NAME': '', 'COCO_PCT': 'CoCo %'},
            color_continuous_scale='Blues',
            text=top['TOTAL_USE_CASES'].apply(lambda x: f"{int(x)} UCs")
        )
        fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
        fig.update_xaxes(tickformat="$,.0f")
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Top Technical Use Case Types")
    tech_data = get_by_technical_type(conn, region=region, start_date=start_date, end_date=end_date)
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
