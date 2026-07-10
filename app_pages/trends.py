import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.queries import get_aging_analysis, get_stalled_use_cases, get_weekly_use_case_metrics, get_by_partner
from utils.ask_ai import build_filter_context

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
start_date = str(st.session_state.get("okr_start_date", "2026-05-01"))
end_date = str(st.session_state.get("okr_end_date", "2026-07-31"))

st.title(":material/trending_up: Use Case Trends & Aging")
st.caption(f"Track velocity, aging, and stalled use cases | Region: {region} | {start_date} to {end_date}")
st.caption(":material/info: Partner filter not applied on this page — showing all partners")

# Inject context for Ask AI (loaded before tabs so it's available immediately)
st.session_state.ask_ai_context = (
    f"Current page: Trends & Aging. Region: {region}. Period: {start_date} to {end_date}.\n"
    f"Shows weekly use case trends, aging by stage, and stalled use cases."
    + build_filter_context()
)

tab_trends, tab_aging, tab_stalled = st.tabs(["Weekly Trends", "Aging Analysis", "Stalled Use Cases"])

with tab_trends:
    weekly = get_weekly_use_case_metrics(conn, region=region, start_date=start_date, end_date=end_date)
    if len(weekly) > 0:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.line(
                weekly,
                x='WEEK_START', y='USE_CASE_COUNT',
                title="Total Use Cases Over Time",
                labels={'WEEK_START': 'Week', 'USE_CASE_COUNT': 'Use Cases'},
                markers=True
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.line(
                weekly,
                x='WEEK_START', y='TOTAL_EACV',
                title="Total EACV Over Time",
                labels={'WEEK_START': 'Week', 'TOTAL_EACV': 'EACV ($)'},
                markers=True
            )
            fig.update_layout(height=350)
            fig.update_yaxes(tickformat="$,.0f")
            st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(
                weekly,
                x='WEEK_START', y='WON',
                title="Use Cases Won per Week",
                labels={'WEEK_START': 'Week', 'WON': 'Won'},
                color_discrete_sequence=['#2ecc71']
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(
                weekly,
                x='WEEK_START', y='DEPLOYED',
                title="Deployments per Week",
                labels={'WEEK_START': 'Week', 'DEPLOYED': 'Deployed'},
                color_discrete_sequence=['#3498db']
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No weekly trend data available yet.")

with tab_aging:
    aging = get_aging_analysis(conn, region=region, start_date=start_date, end_date=end_date)
    if len(aging) > 0:
        bucket_order = ['0-14 days', '15-30 days', '31-60 days', '61-90 days', '90+ days']
        aging['AGING_BUCKET'] = pd.Categorical(aging['AGING_BUCKET'], categories=bucket_order, ordered=True)
        aging = aging.sort_values(['USE_CASE_STAGE', 'AGING_BUCKET'])

        fig = px.bar(
            aging,
            x='USE_CASE_STAGE', y='USE_CASE_COUNT',
            color='AGING_BUCKET',
            title="Use Case Aging by Stage",
            labels={'USE_CASE_COUNT': 'Count', 'USE_CASE_STAGE': 'Stage', 'AGING_BUCKET': 'Time in Stage'},
            barmode='stack',
            color_discrete_map={
                '0-14 days': '#2ecc71',
                '15-30 days': '#27ae60',
                '31-60 days': '#f39c12',
                '61-90 days': '#e74c3c',
                '90+ days': '#c0392b'
            }
        )
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Aging Heatmap")
        pivot = aging.pivot_table(
            index='USE_CASE_STAGE', columns='AGING_BUCKET',
            values='USE_CASE_COUNT', fill_value=0, aggfunc='sum'
        )
        pivot = pivot.reindex(columns=bucket_order, fill_value=0)
        fig = px.imshow(
            pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            labels=dict(x="Aging Bucket", y="Stage", color="Count"),
            color_continuous_scale='RdYlGn_r',
            aspect='auto'
        )
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No aging data available.")

with tab_stalled:
    threshold = st.slider("Stalled threshold (days)", 30, 120, 60, 10, key="stall_thresh")
    stalled = get_stalled_use_cases(conn, days_threshold=threshold, region=region, start_date=start_date, end_date=end_date)

    if len(stalled) > 0:
        st.warning(f"{len(stalled)} use cases have been in their current stage for {threshold}+ days")

        total_at_risk = stalled['USE_CASE_EACV'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Stalled Use Cases", len(stalled))
        c2.metric("At-Risk EACV", f"${total_at_risk/1_000_000:.1f}M" if total_at_risk else "$0")
        c3.metric("Avg Days Stalled", f"{stalled['DAYS_IN_CURRENT_STAGE'].mean():.0f}")

        stalled['SFDC_LINK'] = stalled['USE_CASE_ID'].apply(
            lambda x: f"https://snowforce.lightning.force.com/lightning/r/vh__Deliverable__c/{x}/view"
        )

        st.dataframe(
            stalled[['SFDC_LINK', 'PARTNER_NAME', 'ACCOUNT_NAME', 'USE_CASE_NAME',
                     'USE_CASE_STAGE', 'USE_CASE_EACV', 'DAYS_IN_CURRENT_STAGE', 'ACCOUNT_LEAD_SE_NAME']],
            use_container_width=True,
            height=400,
            column_config={
                "SFDC_LINK": st.column_config.LinkColumn("Link", display_text="View"),
                "PARTNER_NAME": st.column_config.TextColumn("Partner"),
                "ACCOUNT_NAME": st.column_config.TextColumn("Account"),
                "USE_CASE_NAME": st.column_config.TextColumn("Use Case", width="large"),
                "USE_CASE_STAGE": st.column_config.TextColumn("Stage"),
                "USE_CASE_EACV": st.column_config.NumberColumn("EACV", format="$%.0f"),
                "DAYS_IN_CURRENT_STAGE": st.column_config.NumberColumn("Days", format="%d"),
                "ACCOUNT_LEAD_SE_NAME": st.column_config.TextColumn("Lead SE"),
            },
            hide_index=True
        )
    else:
        st.success(f"No use cases stalled for {threshold}+ days!")

st.divider()

st.subheader("Partner Velocity Comparison")
partner_data = get_by_partner(conn, region=region, start_date=start_date, end_date=end_date)
if len(partner_data) > 0:
    partner_data['WIN_RATE'] = (partner_data['WON_COUNT'] + partner_data['DEPLOYED_COUNT']) / partner_data['USE_CASE_COUNT'] * 100
    fig = px.scatter(
        partner_data[partner_data['USE_CASE_COUNT'] >= 2],
        x='AVG_DAYS', y='WIN_RATE',
        size='TOTAL_EACV', color='PARTNER_NAME',
        hover_name='PARTNER_NAME',
        title="Partner Velocity: Avg Days in Stage vs Win Rate",
        labels={'AVG_DAYS': 'Avg Days in Stage', 'WIN_RATE': 'Win+Deploy Rate (%)', 'TOTAL_EACV': 'EACV'},
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
