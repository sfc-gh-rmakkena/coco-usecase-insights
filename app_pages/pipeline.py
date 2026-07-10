import streamlit as st
import pandas as pd
import plotly.express as px
from utils.queries import get_use_cases, get_by_partner, get_by_stage, get_distinct_partners, get_summary_stats
from utils.cortex_helpers import cortex_complete
from utils.ask_ai import build_filter_context

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
start_date = str(st.session_state.get("okr_start_date", "2026-05-01"))
end_date = str(st.session_state.get("okr_end_date", "2026-07-31"))

st.title(":material/filter_alt: Use Case Pipeline & Funnel")
st.caption(f"Explore the full CoCo use case pipeline with filters | Region: {region} | {start_date} to {end_date}")
st.caption(":material/info: Partner filter not applied on this page — use the page-level dropdown below")

source_toggle = st.segmented_control("Source", ["Overall", "PSE Confirmed", "Feature Flag"], default="Overall", key="pipeline_source")

f1, f2, f3 = st.columns(3)
with f1:
    partners = get_distinct_partners(conn, region=region, source=source_toggle)
    selected_partner = st.selectbox("Partner", partners, key="pipe_partner")
with f2:
    stage_options = [
        "1 - Discovery", "2 - Scoping", "3 - Technical / Business Validation",
        "4 - Use Case Won / Migration Plan", "5 - Implementation In Progress",
        "6 - Implementation Complete", "7 - Deployed"
    ]
    selected_stages = st.multiselect("Stages", stage_options, key="pipe_stages")
with f3:
    sort_by = st.selectbox("Sort by", ["EACV (High to Low)", "Days in Stage (High)", "Partner Name", "Stage"], key="pipe_sort")

stage_filter = selected_stages if selected_stages else None
df = get_use_cases(conn, partner=selected_partner, stage=stage_filter, region=region, source=source_toggle, start_date=start_date, end_date=end_date)

if len(df) == 0:
    st.info("No use cases found with the selected filters.")
    st.stop()

if sort_by == "Days in Stage (High)":
    df = df.sort_values("DAYS_IN_CURRENT_STAGE", ascending=False, na_position='last')
elif sort_by == "Partner Name":
    df = df.sort_values("PARTNER_NAME")
elif sort_by == "Stage":
    df = df.sort_values("USE_CASE_STAGE")

st.divider()

# Inject context for Ask AI
_coco_count = int(df['IS_COCO'].sum()) if 'IS_COCO' in df.columns else 0
_stage_summary = df.groupby('USE_CASE_STAGE').size().to_dict() if len(df) > 0 else {}
_stage_str = '; '.join(f"{s}: {c}" for s, c in sorted(_stage_summary.items()))
st.session_state.ask_ai_context = (
    f"Current page: Pipeline & Funnel. Region: {region}. Period: {start_date} to {end_date}.\n"
    f"Total use cases: {len(df)}. Total EACV: ${df['USE_CASE_EACV'].sum()/1_000_000:.1f}M. CoCo tagged: {_coco_count}.\n"
    f"Stage breakdown: {_stage_str}."
    + build_filter_context()
)

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader(f"Pipeline ({len(df)} use cases, ${df['USE_CASE_EACV'].sum()/1_000_000:.1f}M EACV)")
    stage_data = get_by_stage(conn, region=region, source=source_toggle)
    if len(stage_data) > 0:
        fig = px.bar(
            stage_data, x='USE_CASE_STAGE', y='TOTAL_EACV',
            color='USE_CASE_COUNT', text='USE_CASE_COUNT',
            labels={'TOTAL_EACV': 'EACV ($)', 'USE_CASE_STAGE': 'Stage', 'USE_CASE_COUNT': 'Count'},
            color_continuous_scale='Blues'
        )
        fig.update_layout(height=300, showlegend=False)
        fig.update_yaxes(tickformat="$,.0f")
        fig.update_traces(textposition='outside')
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Partner Breakdown")
    partner_data = get_by_partner(conn, region=region, source=source_toggle)
    if len(partner_data) > 0:
        fig = px.pie(partner_data.head(8), values='USE_CASE_COUNT', names='PARTNER_NAME', hole=0.4)
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Use Case Table")

df['SFDC_LINK'] = df['USE_CASE_ID'].apply(
    lambda x: f"https://snowforce.lightning.force.com/lightning/r/vh__Deliverable__c/{x}/view"
)

display_cols = [
    'SFDC_LINK', 'PARTNER_NAME', 'ACCOUNT_NAME', 'USE_CASE_NAME',
    'USE_CASE_STAGE', 'USE_CASE_EACV', 'TECHNICAL_USE_CASE',
    'DAYS_IN_CURRENT_STAGE', 'COCO_MENTION_SOURCE', 'ACCOUNT_LEAD_SE_NAME', 'IS_WON', 'IS_DEPLOYED'
]

column_config = {
    "SFDC_LINK": st.column_config.LinkColumn("Link", display_text="View"),
    "PARTNER_NAME": st.column_config.TextColumn("Partner"),
    "ACCOUNT_NAME": st.column_config.TextColumn("Account"),
    "USE_CASE_NAME": st.column_config.TextColumn("Use Case", width="large"),
    "USE_CASE_STAGE": st.column_config.TextColumn("Stage"),
    "USE_CASE_EACV": st.column_config.NumberColumn("EACV", format="$%.0f"),
    "TECHNICAL_USE_CASE": st.column_config.TextColumn("Technical Type"),
    "DAYS_IN_CURRENT_STAGE": st.column_config.NumberColumn("Days", format="%d"),
    "COCO_MENTION_SOURCE": st.column_config.TextColumn("CoCo Source"),
    "ACCOUNT_LEAD_SE_NAME": st.column_config.TextColumn("Lead SE"),
    "IS_WON": st.column_config.CheckboxColumn("Won"),
    "IS_DEPLOYED": st.column_config.CheckboxColumn("Deployed"),
}

if "last_pipe_selection" not in st.session_state:
    st.session_state.last_pipe_selection = None

selection = st.dataframe(
    df[display_cols],
    use_container_width=True,
    height=450,
    column_config=column_config,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="pipeline_table"
)

st.caption(f"Showing {len(df)} use cases | Total EACV: ${df['USE_CASE_EACV'].sum():,.0f}")

@st.dialog("Use Case Details", width="large")
def show_use_case_dialog(row):
    st.markdown(f"### {row.get('USE_CASE_NAME', 'Unknown')}")
    st.markdown(f"**Account:** {row.get('ACCOUNT_NAME', 'N/A')} | **Partner:** {row.get('PARTNER_NAME', 'N/A')}")

    c1, c2, c3, c4 = st.columns(4)
    eacv = row.get('USE_CASE_EACV', 0) or 0
    c1.metric("EACV", f"${eacv:,.0f}")
    c2.metric("Stage", row.get('USE_CASE_STAGE', 'N/A'))
    days = row.get('DAYS_IN_CURRENT_STAGE')
    c3.metric("Days in Stage", f"{int(days)}" if days and days != 'N/A' else "N/A")
    c4.metric("CoCo Source", row.get('COCO_MENTION_SOURCE', 'N/A'))

    features = row.get('PRIORITIZED_FEATURES', '') or ''
    if features:
        st.markdown(f"**Prioritized Features:** {features}")

    st.divider()

    tab_se, tab_partner, tab_specialist, tab_next = st.tabs(["SE Comments", "Partner Comments", "Specialist Comments", "Next Steps"])
    with tab_se:
        se = row.get('SE_COMMENTS', '') or ''
        st.markdown(se if se else "*No SE comments*")
    with tab_partner:
        pc = row.get('PARTNER_COMMENTS', '') or ''
        st.markdown(pc if pc else "*No partner comments*")
    with tab_specialist:
        spec = row.get('SPECIALIST_COMMENTS', '') or ''
        st.markdown(spec if spec else "*No specialist comments*")
    with tab_next:
        ns = row.get('NEXT_STEPS', '') or ''
        st.markdown(ns if ns else "*No next steps*")

    st.divider()
    st.markdown("**AI Summary:**")
    se = (row.get('SE_COMMENTS', '') or '')[:800]
    pc = (row.get('PARTNER_COMMENTS', '') or '')[:500]
    spec = (row.get('SPECIALIST_COMMENTS', '') or '')[:500]
    prompt = f"""Summarize this CoCo partner use case in 3-4 sentences. Focus on: what the partner is building, how CoCo is being used, current status, and key risks.

**Use Case:** {row.get('USE_CASE_NAME', 'Unknown')}
**Partner:** {row.get('PARTNER_NAME', 'Unknown')} | **Account:** {row.get('ACCOUNT_NAME', 'Unknown')}
**Stage:** {row.get('USE_CASE_STAGE', 'Unknown')} | **EACV:** ${eacv:,.0f} | **Days in Stage:** {days}
**Technical Type:** {row.get('TECHNICAL_USE_CASE', 'N/A')}
**Features:** {features[:300]}
**SE Comments:** {se}
**Partner Comments:** {pc}
**Specialist Comments:** {spec}"""

    response_placeholder = st.empty()
    full_response = ""
    response_placeholder.info("Generating...")
    full_response = cortex_complete(conn, "claude-sonnet-4-5", prompt)
    response_placeholder.markdown(full_response)

    sfdc_url = f"https://snowforce.lightning.force.com/lightning/r/vh__Deliverable__c/{row.get('USE_CASE_ID', '')}/view"
    st.markdown(f"[Open in Salesforce]({sfdc_url})")

if selection and selection.selection.rows:
    idx = selection.selection.rows[0]
    key = f"pipe_{idx}_{df.iloc[idx]['USE_CASE_NAME']}"
    if key != st.session_state.last_pipe_selection:
        st.session_state.last_pipe_selection = key
        show_use_case_dialog(df.iloc[idx].to_dict())
