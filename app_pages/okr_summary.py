import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.queries import get_partner_coco_coverage, get_okr_stage_breakdown, get_partner_credit_consumption, get_bulk_confidence_scores, get_coco_adoption_wow
from utils import resolve_partner_filter

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])
start_date = st.session_state.get("okr_start_date")
end_date = st.session_state.get("okr_end_date")
include_account_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter = st.session_state.get("confidence_filter", ["High"])
confidence = 'High' if confidence_filter == ['High'] else ('Medium' if confidence_filter else None)

st.title(":material/dashboard: OKR: CoCo Coverage Dashboard")
st.caption(f"Track CoCo adoption toward 50% target across partner use cases (Stages 3-7) | Region: {region} | {start_date} to {end_date}")

TARGET_PCT = 50

with st.spinner("Loading CoCo coverage data..."):
    # Always fetch base coverage without account-level CoCo for partner list/totals
    coverage = get_partner_coco_coverage(conn, region=region, start_date=str(start_date), end_date=str(end_date), include_account_coco=False, confidence=None)
    stage_breakdown = get_okr_stage_breakdown(conn, region=region, start_date=str(start_date), end_date=str(end_date), include_account_coco=False, confidence=None)
    credit_data = get_partner_credit_consumption(conn, coverage['PARTNER_NAME'].tolist(), str(start_date), str(end_date))
    adoption_wow = get_coco_adoption_wow(conn)

if len(coverage) == 0:
    st.warning("No data available for the selected filters.")
    st.stop()

if selected_partners:
    partner_names = resolve_partner_filter(selected_partners)
    coverage = coverage[coverage['PARTNER_NAME'].isin(partner_names)]
    stage_breakdown = stage_breakdown[stage_breakdown['PARTNER_NAME'].isin(partner_names)]
    credit_data = credit_data[credit_data['PARTNER_NAME'].isin(partner_names)] if len(credit_data) > 0 else credit_data

if len(coverage) == 0:
    st.info(f"No data for selected partners.")
    st.stop()

# Recompute CoCo counts using full confidence scoring — same logic as OKR Adoption page
bulk_conf = pd.DataFrame()
if include_account_coco and len(coverage) > 0:
    bulk_conf = get_bulk_confidence_scores(conn, coverage['PARTNER_NAME'].tolist(), str(start_date), str(end_date))
    if len(bulk_conf) > 0:
        if region and region != 'Global':
            region_theaters = {
                'NoAM': ['AMSExpansion', 'USMajors', 'AMSAcquisition'],
                'EMEA': ['EMEA'], 'APJ': ['APJ']
            }
            bulk_conf = bulk_conf[bulk_conf['THEATER_NAME'].isin(region_theaters.get(region, []))]
        bands = confidence_filter if confidence_filter else ['High', 'Medium', 'Low']
        bulk_conf['IS_COCO_FINAL'] = (
            (bulk_conf['IS_COCO'] == True) |
            (bulk_conf['CONFIDENCE_BAND'].isin(bands))
        )
        coco_eacv = bulk_conf[bulk_conf['IS_COCO_FINAL']].groupby('PARTNER_NAME')['USE_CASE_EACV'].sum().reset_index()
        coco_eacv.columns = ['PARTNER_NAME', 'COCO_EACV']
        conf_summary = bulk_conf.groupby('PARTNER_NAME').agg(
            TOTAL_PARTNER_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
        ).reset_index()
        conf_summary = conf_summary.merge(coco_eacv, on='PARTNER_NAME', how='left')
        conf_summary['COCO_EACV'] = conf_summary['COCO_EACV'].fillna(0)
        conf_summary['NON_COCO_UCS'] = conf_summary['TOTAL_PARTNER_UCS'] - conf_summary['COCO_UCS']
        conf_summary['COCO_PCT'] = round(
            conf_summary['COCO_UCS'] * 100.0 / conf_summary['TOTAL_PARTNER_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        coverage = coverage[['PARTNER_NAME']].merge(conf_summary, on='PARTNER_NAME', how='left').fillna(0)
        coverage['COCO_PCT'] = coverage['COCO_PCT'].astype(float)
        coverage[['TOTAL_PARTNER_UCS', 'COCO_UCS', 'NON_COCO_UCS']] = coverage[['TOTAL_PARTNER_UCS', 'COCO_UCS', 'NON_COCO_UCS']].astype(int)

        # Recompute stage breakdown with same IS_COCO_FINAL logic
        stage_coco_eacv = bulk_conf[bulk_conf['IS_COCO_FINAL']].groupby(
            ['PARTNER_NAME', 'USE_CASE_STAGE'])['USE_CASE_EACV'].sum().reset_index()
        stage_coco_eacv.columns = ['PARTNER_NAME', 'USE_CASE_STAGE', 'COCO_EACV']
        stage_from_conf = bulk_conf.groupby(['PARTNER_NAME', 'USE_CASE_STAGE']).agg(
            TOTAL_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
        ).reset_index()
        stage_from_conf = stage_from_conf.merge(stage_coco_eacv, on=['PARTNER_NAME', 'USE_CASE_STAGE'], how='left')
        stage_from_conf['COCO_EACV'] = stage_from_conf['COCO_EACV'].fillna(0)
        stage_from_conf['COCO_PCT'] = round(
            stage_from_conf['COCO_UCS'] * 100.0 / stage_from_conf['TOTAL_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        stage_breakdown = stage_from_conf

tab_summary, tab_detail = st.tabs(["Summary", "Detail"])

with tab_summary:
    total_partners = len(coverage)
    total_all_ucs = int(coverage['TOTAL_PARTNER_UCS'].sum())
    total_coco_ucs = int(coverage['COCO_UCS'].sum())
    overall_pct = round(total_coco_ucs * 100.0 / total_all_ucs, 1) if total_all_ucs > 0 else 0
    meeting_target = int((coverage['COCO_PCT'] >= TARGET_PCT).sum())
    below_target = total_partners - meeting_target

    # Extract overall WoW row (PARTNER_NAME IS NULL)
    wow_overall = adoption_wow[adoption_wow['PARTNER_NAME'].isna()] if len(adoption_wow) > 0 else None
    wow_coco_ucs_delta = None
    wow_coco_pct_delta = None
    if wow_overall is not None and len(wow_overall) > 0:
        row = wow_overall.iloc[0]
        if pd.notna(row.get('WOW_COCO_UCS')):
            wow_coco_ucs_delta = f"{int(row['WOW_COCO_UCS']):+d} WoW"
        if pd.notna(row.get('WOW_COCO_PCT')):
            wow_coco_pct_delta = f"{float(row['WOW_COCO_PCT']):+.1f}% WoW"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Partners", total_partners)
    c2.metric("Total Use Cases", f"{total_all_ucs:,}")
    c3.metric("CoCo Use Cases", f"{total_coco_ucs:,}", wow_coco_ucs_delta)
    c4.metric("Overall CoCo %", f"{overall_pct}%", wow_coco_pct_delta if wow_coco_pct_delta else f"Target: {TARGET_PCT}%")
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
        st.subheader("Use Case Split by Attribution")
        if len(bulk_conf) > 0:
            # Compute attribution from bulk_conf using IS_COCO_FINAL logic
            se = int(((bulk_conf['IS_COCO'] == True) & (bulk_conf['COCO_SOURCE'] == 'SE_COMMENTS')).sum())
            pse = int(((bulk_conf['IS_COCO'] == True) & (bulk_conf['COCO_SOURCE'] == 'PARTNER_COMMENTS')).sum())
            flag = int(((bulk_conf['IS_COCO'] == True) & (bulk_conf['COCO_SOURCE'] == 'FEATURE_FLAG')).sum())
            acct = int(bulk_conf['CONFIDENCE_BAND'].isin(bands).sum())
            not_coco = int((~bulk_conf['IS_COCO_FINAL']).sum())
            conf_desc = 'High' if confidence_filter == ['High'] else 'High + Medium' if confidence_filter else 'All account-level'
            labels = [f'Account ({conf_desc})', 'SE Comments', 'PSE Comments', 'Feature Flag', 'Not CoCo']
            values = [acct, se, pse, flag, not_coco]
            colors = ['#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#e0e0e0']
            filtered_slices = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
            fig = go.Figure(data=[go.Pie(
                labels=[f[0] for f in filtered_slices],
                values=[f[1] for f in filtered_slices],
                marker_colors=[f[2] for f in filtered_slices],
                hole=0.5,
                textinfo='label+value+percent'
            )])
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            # Fallback: SQL-based attribution (IS_COCO flag only, no account-level)
            sd = str(start_date)
            ed = str(end_date)
            tf = ""
            if region == "NoAM":
                tf = " AND uc.THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition')"
            elif region == "EMEA":
                tf = " AND uc.THEATER_NAME = 'EMEA'"
            elif region == "APJ":
                tf = " AND uc.THEATER_NAME = 'APJ'"
            partner_list = coverage['PARTNER_NAME'].tolist()
            pf = f" AND uc.PARTNER_NAME IN ('{chr(39).join(partner_list)}')" if partner_list else ""
            source_query = f"""
            SELECT
                SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'SE_COMMENTS' THEN 1 ELSE 0 END) AS SE_COMMENTS,
                SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'PARTNER_COMMENTS' THEN 1 ELSE 0 END) AS PSE_COMMENTS,
                SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'FEATURE_FLAG' THEN 1 ELSE 0 END) AS FEATURE_FLAG,
                SUM(CASE WHEN NOT uc.IS_COCO THEN 1 ELSE 0 END) AS NOT_COCO
            FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
            WHERE (
                (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{sd}' AND uc.DECISION_DATE <= '{ed}')
                OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{sd}' AND uc.GO_LIVE_DATE <= '{ed}')
            ){tf}{pf}
            """
            source_split = conn.query(source_query)
            if len(source_split) > 0:
                ss = source_split.iloc[0]
                labels = ['SE Comments', 'PSE Comments', 'Feature Flag', 'Not CoCo']
                values = [int(ss['SE_COMMENTS']), int(ss['PSE_COMMENTS']), int(ss['FEATURE_FLAG']), int(ss['NOT_COCO'])]
                colors = ['#2ecc71', '#f39c12', '#9b59b6', '#e0e0e0']
                filtered_slices = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
                fig = go.Figure(data=[go.Pie(
                    labels=[f[0] for f in filtered_slices],
                    values=[f[1] for f in filtered_slices],
                    marker_colors=[f[2] for f in filtered_slices],
                    hole=0.5,
                    textinfo='label+value+percent'
                )])
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("CoCo % by Stage Breakdown")

    if len(stage_breakdown) > 0:
        # Filter stage_breakdown to only partners in coverage (ensures consistency)
        stage_breakdown_filtered = stage_breakdown[stage_breakdown['PARTNER_NAME'].isin(coverage['PARTNER_NAME'].tolist())]
        stage_agg = stage_breakdown_filtered.groupby('USE_CASE_STAGE').agg({
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

    # Get per-partner attribution breakdown
    sd = str(start_date)
    ed = str(end_date)
    partner_list = coverage['PARTNER_NAME'].tolist()
    if partner_list:
        partners_sql = "','".join(partner_list)
        attribution_query = f"""
        WITH coco_active_accounts AS (
            SELECT DISTINCT UPPER(salesforce_account_name) AS ACCOUNT_NAME_UPPER
            FROM snowscience.llm.cortex_code_user_day_fact
            WHERE ds >= '{sd}' AND snowflake_account_type = 'Customer' AND total_daily_requests > 0
        )
        SELECT 
            uc.PARTNER_NAME,
            SUM(CASE WHEN caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN 1 ELSE 0 END) AS ACCOUNT_LEVEL_COCO_USAGE,
            SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'SE_COMMENTS' THEN 1 ELSE 0 END) AS SE_COMMENTS,
            SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'PARTNER_COMMENTS' THEN 1 ELSE 0 END) AS PSE_COMMENTS,
            SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'FEATURE_FLAG' THEN 1 ELSE 0 END) AS FEATURE_FLAG
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
        LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
        WHERE uc.PARTNER_NAME IN ('{partners_sql}')
        AND (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{sd}' AND uc.DECISION_DATE <= '{ed}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{sd}' AND uc.GO_LIVE_DATE <= '{ed}')
        )
        GROUP BY uc.PARTNER_NAME
        """
        attribution_data = conn.query(attribution_query)
    else:
        attribution_data = pd.DataFrame()

    display = coverage.copy()
    display['MEETS_TARGET'] = display['COCO_PCT'] >= TARGET_PCT
    display['GAP'] = display.apply(
        lambda r: max(0, int((TARGET_PCT / 100.0 * r['TOTAL_PARTNER_UCS']) - r['COCO_UCS'] + 0.999)), axis=1
    )

    # Merge attribution columns
    if len(attribution_data) > 0:
        display = display.merge(attribution_data, on='PARTNER_NAME', how='left')
        display[['ACCOUNT_LEVEL_COCO_USAGE', 'SE_COMMENTS', 'PSE_COMMENTS', 'FEATURE_FLAG']] = display[['ACCOUNT_LEVEL_COCO_USAGE', 'SE_COMMENTS', 'PSE_COMMENTS', 'FEATURE_FLAG']].fillna(0).astype(int)
    else:
        display['ACCOUNT_LEVEL_COCO_USAGE'] = 0
        display['SE_COMMENTS'] = 0
        display['PSE_COMMENTS'] = 0
        display['FEATURE_FLAG'] = 0

    display = display.sort_values('COCO_PCT', ascending=False)

    # Fetch WoW engagement delta from PARTNER_WEEKLY_METRICS (latest week, all regions combined)
    if partner_list:
        partners_sql_wow = "','".join(partner_list)
        wow_query = f"""
        WITH latest AS (
            SELECT PARTNER_NAME,
                SUM(TOTAL_REQUESTS)      AS TOTAL_REQUESTS,
                SUM(PREV_WEEK_REQUESTS)  AS PREV_WEEK_REQUESTS,
                SUM(TOTAL_USERS)         AS TOTAL_USERS,
                CASE WHEN SUM(PREV_WEEK_REQUESTS) > 0
                    THEN ROUND((SUM(TOTAL_REQUESTS) - SUM(PREV_WEEK_REQUESTS)) * 100.0 / SUM(PREV_WEEK_REQUESTS), 1)
                END AS WOW_REQUESTS_PCT
            FROM TEMP.COCO_PARTNER_ADOPTION.PARTNER_WEEKLY_METRICS
            WHERE WEEK_START = (SELECT MAX(WEEK_START) FROM TEMP.COCO_PARTNER_ADOPTION.PARTNER_WEEKLY_METRICS)
            AND PARTNER_NAME IN ('{partners_sql_wow}')
            GROUP BY PARTNER_NAME
        )
        SELECT * FROM latest
        """
        wow_data = conn.query(wow_query)
    else:
        wow_data = pd.DataFrame()

    if len(wow_data) > 0:
        display = display.merge(wow_data[['PARTNER_NAME', 'WOW_REQUESTS_PCT', 'TOTAL_REQUESTS', 'TOTAL_USERS']], on='PARTNER_NAME', how='left')
    else:
        display['WOW_REQUESTS_PCT'] = None
        display['TOTAL_REQUESTS'] = 0
        display['TOTAL_USERS'] = 0

    # Merge CoCo adoption WoW (per-partner rows only)
    wow_partners = adoption_wow[adoption_wow['PARTNER_NAME'].notna()][['PARTNER_NAME', 'WOW_COCO_PCT', 'WOW_COCO_UCS']] if len(adoption_wow) > 0 else pd.DataFrame()
    if len(wow_partners) > 0:
        display = display.merge(wow_partners, on='PARTNER_NAME', how='left')
    else:
        display['WOW_COCO_PCT'] = None
        display['WOW_COCO_UCS'] = None

    st.dataframe(
        display[['PARTNER_NAME', 'TOTAL_PARTNER_UCS', 'COCO_UCS', 'COCO_PCT', 'WOW_COCO_PCT', 'WOW_COCO_UCS', 'ACCOUNT_LEVEL_COCO_USAGE', 'SE_COMMENTS', 'PSE_COMMENTS', 'FEATURE_FLAG', 'MEETS_TARGET', 'GAP']],
        column_config={
            'PARTNER_NAME': st.column_config.TextColumn("Partner", width="medium"),
            'TOTAL_PARTNER_UCS': st.column_config.NumberColumn("Total UCs", format="%d"),
            'COCO_UCS': st.column_config.NumberColumn("CoCo UCs", format="%d"),
            'COCO_PCT': st.column_config.ProgressColumn("CoCo %", min_value=0, max_value=100, format="%.1f%%"),
            'WOW_COCO_PCT': st.column_config.NumberColumn("WoW Δ%", format="%+.1f%%", help="Week-over-week change in CoCo adoption % (available after 2nd weekly snapshot)"),
            'WOW_COCO_UCS': st.column_config.NumberColumn("WoW Δ UCs", format="%+d", help="Week-over-week change in CoCo use case count"),
            'ACCOUNT_LEVEL_COCO_USAGE': st.column_config.NumberColumn("Account Level CoCo Usage", format="%d", help="Use cases on accounts with CoCo product consumption"),
            'SE_COMMENTS': st.column_config.NumberColumn("SE Comments", format="%d", help="SE wrote coco/cortex code in comments"),
            'PSE_COMMENTS': st.column_config.NumberColumn("PSE Comments", format="%d", help="Partner wrote #coco in comments"),
            'FEATURE_FLAG': st.column_config.NumberColumn("Feature Flag", format="%d", help="AI - Cortex Code in Prioritized Features"),
            'MEETS_TARGET': st.column_config.CheckboxColumn(f"≥{TARGET_PCT}%"),
            'GAP': st.column_config.NumberColumn("UCs to Target", help="Additional CoCo UCs needed to reach 50%"),
        },
        hide_index=True, use_container_width=True, height=500
    )
    st.caption("Note: Attribution columns may overlap — a use case can have both account-level usage AND comments.")

    st.divider()
    st.subheader("CoCo Credit Consumption (Q2)")
    if len(credit_data) > 0:
        credit_display = credit_data.copy()
        credit_display['Q2_TOTAL_CREDITS'] = credit_display['Q2_TOTAL_CREDITS'].apply(lambda x: f"${x:,.0f}" if x else "$0")
        credit_display['WOW_PCT'] = credit_display['WOW_PCT'].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A")
        st.dataframe(
            credit_display[['PARTNER_NAME', 'COCO_CUSTOMER_ACCOUNTS', 'Q2_TOTAL_CREDITS', 'WOW_PCT', 'ACTIVE_DAYS']],
            column_config={
                'PARTNER_NAME': st.column_config.TextColumn("Partner", width="medium"),
                'COCO_CUSTOMER_ACCOUNTS': st.column_config.NumberColumn("Customer Accounts", format="%d"),
                'Q2_TOTAL_CREDITS': st.column_config.TextColumn("Q2 Total Credits"),
                'WOW_PCT': st.column_config.TextColumn("WoW %"),
                'ACTIVE_DAYS': st.column_config.NumberColumn("Active Days", format="%d"),
            },
            hide_index=True, use_container_width=True
        )
    else:
        st.info("No credit consumption data available.")

with tab_detail:
    st.subheader("Partner-by-Partner CoCo Breakdown")

    if not selected_partners:
        st.info("Select partners from the sidebar to view their CoCo breakdown.")
    else:
        detail_sorted = coverage.sort_values('TOTAL_PARTNER_UCS', ascending=False)
        partner_list = detail_sorted['PARTNER_NAME'].tolist()

        if not partner_list:
            st.info("No partners found for the selected filters.")
        else:
            for partner_name in partner_list:
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
                        st.plotly_chart(fig, use_container_width=True, key=f"detail_chart_{partner_name}")

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
st.caption("CoCo detection: SE Comments (coco/cortex code) OR Partner Comments (#coco) OR Feature Flag (AI - Cortex Code) OR CoCo Account Level Usage")
