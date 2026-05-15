import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.queries import get_partner_coco_coverage, get_okr_stage_breakdown

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
partner_filter = st.session_state.get("selected_partner", "All")

st.title(":material/dashboard: OKR: CoCo Coverage Dashboard")
st.caption(f"Track CoCo adoption toward 50% target across partner use cases (Stages 3-7) | Region: {region}")

TARGET_PCT = 50

with st.spinner("Loading CoCo coverage data..."):
    coverage = get_partner_coco_coverage(conn, region=region)
    stage_breakdown = get_okr_stage_breakdown(conn, region=region)

if len(coverage) == 0:
    st.warning("No data available for the selected filters.")
    st.stop()

if partner_filter and partner_filter != "All":
    coverage = coverage[coverage['PARTNER_NAME'].str.contains(partner_filter, case=False, na=False)]
    stage_breakdown = stage_breakdown[stage_breakdown['PARTNER_NAME'].str.contains(partner_filter, case=False, na=False)]

if len(coverage) == 0:
    st.info(f"No data for partner: {partner_filter}")
    st.stop()

tab_summary, tab_detail = st.tabs(["Summary", "Detail"])

with tab_summary:
    total_partners = len(coverage)
    total_all_ucs = int(coverage['TOTAL_PARTNER_UCS'].sum())
    total_coco_ucs = int(coverage['COCO_UCS'].sum())
    overall_pct = round(total_coco_ucs * 100.0 / total_all_ucs, 1) if total_all_ucs > 0 else 0
    meeting_target = int((coverage['COCO_PCT'] >= TARGET_PCT).sum())
    below_target = total_partners - meeting_target

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Partners", total_partners)
    c2.metric("Total Use Cases", f"{total_all_ucs:,}")
    c3.metric("CoCo Use Cases", f"{total_coco_ucs:,}")
    c4.metric("Overall CoCo %", f"{overall_pct}%", f"Target: {TARGET_PCT}%")
    c5.metric(f"Meeting {TARGET_PCT}%", f"{meeting_target}/{total_partners}", f"{round(meeting_target*100/total_partners)}%" if total_partners else "0%")

    st.divider()

    gauge_col, pie_col = st.columns(2)
    with gauge_col:
        st.subheader("Overall CoCo Adoption")
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=overall_pct,
            delta={'reference': TARGET_PCT, 'suffix': '%'},
            gauge={
                'axis': {'range': [0, 100], 'ticksuffix': '%'},
                'bar': {'color': '#29B5E8'},
                'steps': [
                    {'range': [0, 20], 'color': 'rgba(231,76,60,0.2)'},
                    {'range': [20, 40], 'color': 'rgba(243,156,18,0.2)'},
                    {'range': [40, 60], 'color': 'rgba(241,196,15,0.2)'},
                    {'range': [60, 100], 'color': 'rgba(46,204,113,0.2)'},
                ],
                'threshold': {'line': {'color': 'red', 'width': 3}, 'thickness': 0.8, 'value': TARGET_PCT}
            },
            number={'suffix': '%'},
            title={'text': f"CoCo % (Target: {TARGET_PCT}%)"}
        ))
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    with pie_col:
        st.subheader("Use Case Split")
        fig = go.Figure(data=[go.Pie(
            labels=['CoCo Attached', 'Not CoCo'],
            values=[total_coco_ucs, total_all_ucs - total_coco_ucs],
            marker_colors=['#29B5E8', '#e0e0e0'],
            hole=0.5,
            textinfo='label+value+percent'
        )])
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("CoCo % by Stage Breakdown")

    if len(stage_breakdown) > 0:
        stage_agg = stage_breakdown.groupby('USE_CASE_STAGE').agg({
            'TOTAL_UCS': 'sum', 'COCO_UCS': 'sum', 'TOTAL_EACV': 'sum', 'COCO_EACV': 'sum'
        }).reset_index()
        stage_agg['COCO_PCT'] = (stage_agg['COCO_UCS'] * 100.0 / stage_agg['TOTAL_UCS'].replace(0, pd.NA)).round(1).fillna(0)
        stage_agg['NON_COCO'] = stage_agg['TOTAL_UCS'] - stage_agg['COCO_UCS']
        stage_agg['STAGE_SHORT'] = stage_agg['USE_CASE_STAGE'].str.replace(r'^\d+ - ', '', regex=True)
        stage_agg = stage_agg.sort_values('USE_CASE_STAGE')

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='CoCo', x=stage_agg['STAGE_SHORT'], y=stage_agg['COCO_UCS'],
            marker_color='#29B5E8', text=stage_agg['COCO_UCS'], textposition='inside'
        ))
        fig.add_trace(go.Bar(
            name='Non-CoCo', x=stage_agg['STAGE_SHORT'], y=stage_agg['NON_COCO'],
            marker_color='#e0e0e0', text=stage_agg['NON_COCO'], textposition='inside'
        ))
        fig.update_layout(barmode='stack', height=350, xaxis_title='', yaxis_title='Use Cases', legend=dict(orientation='h', y=1.12))
        for i, row in stage_agg.iterrows():
            fig.add_annotation(
                x=row['STAGE_SHORT'], y=row['TOTAL_UCS'], text=f"{row['COCO_PCT']:.0f}%",
                showarrow=False, yshift=12, font=dict(size=13, color='#29B5E8', weight='bold')
            )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            stage_agg[['USE_CASE_STAGE', 'TOTAL_UCS', 'COCO_UCS', 'COCO_PCT', 'TOTAL_EACV', 'COCO_EACV']].rename(columns={
                'USE_CASE_STAGE': 'Stage', 'TOTAL_UCS': 'Total UCs', 'COCO_UCS': 'CoCo UCs',
                'COCO_PCT': 'CoCo %', 'TOTAL_EACV': 'Total EACV', 'COCO_EACV': 'CoCo EACV'
            }),
            column_config={
                'CoCo %': st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                'Total EACV': st.column_config.NumberColumn(format="$%.0f"),
                'CoCo EACV': st.column_config.NumberColumn(format="$%.0f"),
            },
            hide_index=True, use_container_width=True
        )

    st.divider()
    st.subheader("Partner Summary Table")

    display = coverage.copy()
    display['MEETS_TARGET'] = display['COCO_PCT'] >= TARGET_PCT
    display['GAP'] = display.apply(
        lambda r: max(0, int((TARGET_PCT / 100.0 * r['TOTAL_PARTNER_UCS']) - r['COCO_UCS'] + 0.999)), axis=1
    )
    display = display.sort_values('COCO_PCT', ascending=False)

    st.dataframe(
        display[['PARTNER_NAME', 'TOTAL_PARTNER_UCS', 'COCO_UCS', 'COCO_PCT', 'MEETS_TARGET', 'GAP']],
        column_config={
            'PARTNER_NAME': st.column_config.TextColumn("Partner", width="medium"),
            'TOTAL_PARTNER_UCS': st.column_config.NumberColumn("Total UCs", format="%d"),
            'COCO_UCS': st.column_config.NumberColumn("CoCo UCs", format="%d"),
            'COCO_PCT': st.column_config.ProgressColumn("CoCo %", min_value=0, max_value=100, format="%.1f%%"),
            'MEETS_TARGET': st.column_config.CheckboxColumn(f"≥{TARGET_PCT}%"),
            'GAP': st.column_config.NumberColumn("UCs to Target", help="Additional CoCo UCs needed to reach 50%"),
        },
        hide_index=True, use_container_width=True, height=500
    )

with tab_detail:
    st.subheader("Partner-by-Partner CoCo Breakdown")

    detail_sorted = coverage.sort_values('TOTAL_PARTNER_UCS', ascending=False)
    partner_list = detail_sorted['PARTNER_NAME'].tolist()
    partner_options = [f"{p} ({int(detail_sorted[detail_sorted['PARTNER_NAME']==p].iloc[0]['COCO_UCS'])}/{int(detail_sorted[detail_sorted['PARTNER_NAME']==p].iloc[0]['TOTAL_PARTNER_UCS'])} CoCo)" for p in partner_list]

    selected_partners = st.multiselect(
        "Select Partners to View",
        options=partner_list,
        default=partner_list[:10],
        key="okr_detail_partners",
        help="Pick partners to see their stage-by-stage CoCo breakdown"
    )

    if not selected_partners:
        st.info("Select one or more partners above to view their detail.")
    else:
        for partner_name in selected_partners:
            p_row = coverage[coverage['PARTNER_NAME'] == partner_name].iloc[0]
            total = int(p_row['TOTAL_PARTNER_UCS'])
            coco = int(p_row['COCO_UCS'])
            pct = float(p_row['COCO_PCT'] or 0)
            gap = max(0, int((TARGET_PCT / 100.0 * total) - coco + 0.999))

            if pct >= TARGET_PCT:
                status_icon = ":material/check_circle:"
            elif pct >= TARGET_PCT * 0.6:
                status_icon = ":material/warning:"
            else:
                status_icon = ":material/cancel:"

            with st.expander(f"{status_icon} **{partner_name}** — {coco}/{total} CoCo ({pct:.0f}%) | Gap: {gap} UCs", expanded=True):
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Total UCs", total)
                mc2.metric("CoCo UCs", coco)
                mc3.metric("CoCo %", f"{pct:.1f}%", f"{'MET' if pct >= TARGET_PCT else f'{gap} UCs needed'}")
                mc4.metric("Non-CoCo", total - coco)

                p_stages = stage_breakdown[stage_breakdown['PARTNER_NAME'] == partner_name].copy()
                if len(p_stages) > 0:
                    p_stages['STAGE_SHORT'] = p_stages['USE_CASE_STAGE'].str.replace(r'^\d+ - ', '', regex=True)
                    p_stages['NON_COCO'] = p_stages['TOTAL_UCS'] - p_stages['COCO_UCS']
                    p_stages = p_stages.sort_values('USE_CASE_STAGE')

                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        name='CoCo', x=p_stages['STAGE_SHORT'], y=p_stages['COCO_UCS'],
                        marker_color='#29B5E8', text=p_stages['COCO_UCS'], textposition='inside'
                    ))
                    fig.add_trace(go.Bar(
                        name='Non-CoCo', x=p_stages['STAGE_SHORT'], y=p_stages['NON_COCO'],
                        marker_color='#e0e0e0', text=p_stages['NON_COCO'], textposition='inside'
                    ))
                    fig.update_layout(barmode='stack', height=250, showlegend=True, legend=dict(orientation='h', y=1.15))
                    for _, row in p_stages.iterrows():
                        fig.add_annotation(
                            x=row['STAGE_SHORT'], y=row['TOTAL_UCS'], text=f"{row['COCO_PCT']:.0f}%",
                            showarrow=False, yshift=12, font=dict(size=12, color='#29B5E8', weight='bold')
                        )
                    st.plotly_chart(fig, use_container_width=True)

                    st.dataframe(
                        p_stages[['USE_CASE_STAGE', 'TOTAL_UCS', 'COCO_UCS', 'COCO_PCT', 'TOTAL_EACV', 'COCO_EACV']].rename(columns={
                            'USE_CASE_STAGE': 'Stage', 'TOTAL_UCS': 'Total UCs', 'COCO_UCS': 'CoCo UCs',
                            'COCO_PCT': 'CoCo %', 'TOTAL_EACV': 'Total EACV', 'COCO_EACV': 'CoCo EACV'
                        }),
                        column_config={
                            'CoCo %': st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                            'Total EACV': st.column_config.NumberColumn(format="$%.0f"),
                            'CoCo EACV': st.column_config.NumberColumn(format="$%.0f"),
                        },
                        hide_index=True, use_container_width=True
                    )
                else:
                    st.info("No stage-level data available.")

st.divider()
st.caption(f"Target: {TARGET_PCT}% of partner use cases (Stages 3-7) with CoCo attached | Region: {region}")
st.caption("CoCo detection: SE Comments (coco/cortex code) OR Partner Comments (#coco) OR Feature Flag (AI - Cortex Code)")
