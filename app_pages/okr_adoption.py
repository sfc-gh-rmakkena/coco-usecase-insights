import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from utils.queries import get_okr_partner_summary, get_okr_coco_adoption, get_partner_credit_consumption
from utils import resolve_partner_filter

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])
start_date = st.session_state.get("okr_start_date", date(2026, 5, 1))
end_date = st.session_state.get("okr_end_date", date(2026, 7, 31))

st.title(":material/check_circle: OKR: CoCo Adoption per Partner")
st.caption(f"Track 50% CoCo attachment target for partner use cases (Stages 3-7) | Region: {region} | {start_date} to {end_date}")

TARGET_PCT = 50

f1, f2 = st.columns([1, 1])
with f1:
    target = st.number_input("Target %", min_value=10, max_value=100, value=TARGET_PCT, step=5, key="okr_target")
with f2:
    min_use_cases = st.number_input("Min Use Cases", min_value=1, max_value=20, value=2, step=1, key="okr_min_uc")

q_start = str(start_date)
q_end = str(end_date)
summary = get_okr_partner_summary(conn, q_start, q_end, region=region)
credit_data = get_partner_credit_consumption(conn, summary['PARTNER_NAME'].tolist(), q_start)

if len(summary) == 0:
    st.info("No use cases found for the selected date range.")
    st.stop()

# Apply sidebar partner filter
if selected_partners:
    partner_names = resolve_partner_filter(selected_partners)
    summary = summary[summary['PARTNER_NAME'].isin(partner_names)]
    if len(summary) == 0:
        st.info(f"No data for selected partners.")
        st.stop()

summary['MEETS_TARGET'] = summary['COCO_PCT'] >= target
filtered = summary[summary['TOTAL_USE_CASES'] >= min_use_cases].copy()

st.divider()

total_partners = len(filtered)
meeting_target = filtered['MEETS_TARGET'].sum()
not_meeting = total_partners - meeting_target
overall_coco = filtered['COCO_USE_CASES'].sum()
overall_total = filtered['TOTAL_USE_CASES'].sum()
overall_pct = round(overall_coco * 100.0 / overall_total, 1) if overall_total > 0 else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Partners Tracked", total_partners)
c2.metric(f"Meeting {target}%", int(meeting_target), f"{round(meeting_target*100/total_partners)}%" if total_partners else "0%")
c3.metric(f"Below {target}%", int(not_meeting), delta_color="inverse")
c4.metric("Overall CoCo %", f"{overall_pct}%", f"{int(overall_coco)}/{int(overall_total)} UCs")
c5.metric("Total EACV", f"${filtered['TOTAL_EACV'].sum()/1_000_000:.1f}M")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("CoCo Adoption Distribution")
    st.caption("Each bar = number of partners at that CoCo adoption level. Red line = 50% target.")
    
    # Color bars based on target
    colors = ['#2ecc71' if x >= target else '#e74c3c' for x in filtered['COCO_PCT']]
    
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=filtered['COCO_PCT'], nbinsx=10,
        marker_color='#3498db', 
        name='Partners',
        hovertemplate='CoCo %: %{x:.0f}%<br>Partners: %{y}<extra></extra>'
    ))
    fig.add_vline(x=target, line_dash="dash", line_color="red", 
                  annotation_text=f"OKR Target: {target}%",
                  annotation_position="top right",
                  annotation_font_size=12,
                  annotation_font_color="red")
    fig.update_layout(
        height=350, 
        xaxis_title="Partner CoCo Adoption Rate (%)", 
        yaxis_title="Number of Partners",
        xaxis=dict(range=[0, 105], dtick=10, ticksuffix='%'),
        showlegend=False,
        bargap=0.1
    )
    fig.add_annotation(
        x=25, y=0.9, xref='x', yref='paper',
        text="Below Target", showarrow=False,
        font=dict(size=11, color='#e74c3c')
    )
    fig.add_annotation(
        x=75, y=0.9, xref='x', yref='paper',
        text="Meeting Target", showarrow=False,
        font=dict(size=11, color='#2ecc71')
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Target Achievement")
    fig = go.Figure(data=[
        go.Pie(
            labels=[f"Meeting {target}%", f"Below {target}%"],
            values=[int(meeting_target), int(not_meeting)],
            marker_colors=['#2ecc71', '#e74c3c'],
            hole=0.5
        )
    ])
    fig.update_layout(height=350)
    fig.add_annotation(
        text=f"{round(meeting_target*100/total_partners)}%", x=0.5, y=0.5,
        font_size=28, showarrow=False
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Partner Scorecard")

filtered_sorted = filtered.sort_values('COCO_PCT', ascending=False)

display_df = filtered_sorted[['PARTNER_NAME', 'TOTAL_USE_CASES', 'COCO_USE_CASES', 'NON_COCO_USE_CASES', 'TOTAL_EACV', 'COCO_EACV', 'MEETS_TARGET']].copy()
display_df['TOTAL_EACV'] = display_df['TOTAL_EACV'].apply(lambda x: f"${(x or 0)/1000:.0f}K" if (x or 0) < 1_000_000 else f"${(x or 0)/1_000_000:.1f}M")
display_df['COCO_EACV'] = display_df['COCO_EACV'].apply(lambda x: f"${(x or 0)/1000:.0f}K" if (x or 0) < 1_000_000 else f"${(x or 0)/1_000_000:.1f}M")
display_df['GAP'] = filtered_sorted.apply(
    lambda r: max(0, int((target / 100.0 * r['TOTAL_USE_CASES']) - r['COCO_USE_CASES'] + 0.999)), axis=1
)

st.dataframe(
    display_df,
    use_container_width=True,
    height=500,
    column_config={
        "PARTNER_NAME": st.column_config.TextColumn("Partner", width="medium"),
        "TOTAL_USE_CASES": st.column_config.NumberColumn("Total UCs", format="%d"),
        "COCO_USE_CASES": st.column_config.NumberColumn("CoCo UCs", format="%d"),
        "NON_COCO_USE_CASES": st.column_config.NumberColumn("Non-CoCo", format="%d"),
        "TOTAL_EACV": st.column_config.TextColumn("Total EACV"),
        "COCO_EACV": st.column_config.TextColumn("CoCo EACV"),
        "MEETS_TARGET": st.column_config.CheckboxColumn(f">={target}%"),
        "GAP": st.column_config.NumberColumn("UCs to Target", help="Additional CoCo UCs needed to reach target"),
    },
    hide_index=True
)

st.divider()

st.subheader("Partner Deep Dive")
partner_list = filtered_sorted['PARTNER_NAME'].tolist()
selected_partner = st.selectbox("Select Partner", partner_list, key="okr_partner_select")

if selected_partner:
    detail = get_okr_coco_adoption(conn, q_start, q_end, region=region)
    partner_detail = detail[detail['PARTNER_NAME'] == selected_partner]

    if len(partner_detail) > 0:
        p_stats = filtered_sorted[filtered_sorted['PARTNER_NAME'] == selected_partner].iloc[0]
        coco_pct = p_stats['COCO_PCT']

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Use Cases", int(p_stats['TOTAL_USE_CASES']))
        c2.metric("CoCo Attached", int(p_stats['COCO_USE_CASES']))
        c3.metric("CoCo %", f"{coco_pct:.1f}%", f"{'MET' if coco_pct >= target else 'BELOW'} {target}% target")
        gap = max(0, int((target / 100.0 * p_stats['TOTAL_USE_CASES']) - p_stats['COCO_USE_CASES'] + 0.999))
        c4.metric("UCs Needed for Target", gap if gap > 0 else "0 (Met!)")
        # Account-only: CoCo attached but no comments/flag (COCO_SOURCE is NULL)
        account_only = int(partner_detail[(partner_detail['IS_COCO_ATTACHED'] == True) & (partner_detail['COCO_SOURCE'].isna())].shape[0])
        c5.metric("CoCo Attribution- Account Level Usage", account_only, help="CoCo via customer account usage, no SE/PSE comments")

        # Credit consumption for selected partner
        partner_credits = credit_data[credit_data['PARTNER_NAME'] == selected_partner] if len(credit_data) > 0 else pd.DataFrame()
        if len(partner_credits) > 0:
            pc = partner_credits.iloc[0]
            cr1, cr2 = st.columns(2)
            cr1.metric("Q2 Total Credits", f"${pc['Q2_TOTAL_CREDITS']:,.0f}" if pd.notna(pc['Q2_TOTAL_CREDITS']) else "N/A")
            cr2.metric("WoW", f"{pc['WOW_PCT']:+.1f}%" if pd.notna(pc['WOW_PCT']) else "N/A")

        coco_ucs = partner_detail[partner_detail['IS_COCO_ATTACHED'] == True]
        non_coco_ucs = partner_detail[partner_detail['IS_COCO_ATTACHED'] == False]

        tab_coco, tab_noncoco = st.tabs([
            f"CoCo Attached ({len(coco_ucs)})",
            f"Non-CoCo ({len(non_coco_ucs)}) - Opportunities"
        ])

        uc_cols = ['USE_CASE_NAME', 'ACCOUNT_NAME', 'USE_CASE_STAGE', 'USE_CASE_EACV', 'TECHNICAL_USE_CASE', 'ATTRIBUTION_FLAGS']
        uc_config = {
            "USE_CASE_NAME": st.column_config.TextColumn("Use Case", width="large"),
            "ACCOUNT_NAME": st.column_config.TextColumn("Account", width="medium"),
            "USE_CASE_STAGE": st.column_config.TextColumn("Stage", width="small"),
            "USE_CASE_EACV": st.column_config.NumberColumn("EACV", format="$%.0f", width="small"),
            "TECHNICAL_USE_CASE": st.column_config.TextColumn("Technical Type", width="medium"),
            "ATTRIBUTION_FLAGS": st.column_config.TextColumn("CoCo Source", width="medium"),
        }

        with tab_coco:
            if len(coco_ucs) > 0:
                coco_display = coco_ucs[uc_cols].copy()
                coco_display['USE_CASE_STAGE'] = coco_display['USE_CASE_STAGE'].str.extract(r'^(\d+)').iloc[:, 0]
                st.dataframe(coco_display, hide_index=True, use_container_width=True,
                           column_config=uc_config)
            else:
                st.info("No CoCo-attached use cases.")

        with tab_noncoco:
            if len(non_coco_ucs) > 0:
                st.warning(f"These {len(non_coco_ucs)} use cases do NOT have CoCo attached. Adding CoCo to these would help reach the {target}% target.")
                noncoco_display = non_coco_ucs[uc_cols].copy()
                noncoco_display['USE_CASE_STAGE'] = noncoco_display['USE_CASE_STAGE'].str.extract(r'^(\d+)').iloc[:, 0]
                st.dataframe(noncoco_display, hide_index=True, use_container_width=True, column_config=uc_config)
            else:
                st.success("All use cases have CoCo attached!")

st.divider()

st.subheader("Top Partners by CoCo Adoption Gap")
gap_partners = filtered_sorted[~filtered_sorted['MEETS_TARGET']].head(15)
if len(gap_partners) > 0:
    gap_partners = gap_partners.copy()
    gap_partners['GAP'] = gap_partners.apply(
        lambda r: max(0, int((target / 100.0 * r['TOTAL_USE_CASES']) - r['COCO_USE_CASES'] + 0.999)), axis=1
    )
    gap_partners['GAP_EACV'] = gap_partners['TOTAL_EACV'] - gap_partners['COCO_EACV']

    fig = px.bar(
        gap_partners.sort_values('GAP', ascending=True),
        y='PARTNER_NAME', x='GAP', orientation='h',
        color='COCO_PCT', color_continuous_scale='RdYlGn',
        labels={'GAP': 'Additional CoCo UCs Needed', 'PARTNER_NAME': '', 'COCO_PCT': 'Current %'},
        text='GAP'
    )
    fig.update_layout(height=450, yaxis={'categoryorder': 'total ascending'})
    fig.update_traces(textposition='outside')
    st.plotly_chart(fig, use_container_width=True)
else:
    st.success(f"All tracked partners meet the {target}% target!")

st.divider()
st.caption(f"OKR Target: {target}% of use cases in Stages 3-7 should have CoCo attached | {start_date} to {end_date} | Min UCs: {min_use_cases}")
st.caption("CoCo detection: SE Comments (coco/cortex code) OR Partner Comments (#coco) OR Feature Flag (AI - Cortex Code) OR CoCo Account Level Usage")
