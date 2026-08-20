import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date
from utils.queries import get_okr_partner_summary, get_okr_stage_breakdown, get_okr_coco_adoption, get_partner_credit_consumption, get_usecase_confidence_scores, get_bulk_confidence_scores, get_coco_final_wow, get_coco_final_trend_4w, get_partner_coco_trend_4w, get_partner_weekly_credits_4w, get_partner_surface_trend_4w
from utils.ask_ai import build_filter_context, build_credit_wow_context, build_uc_pattern_context
from utils import resolve_partner_filter, resolve_region_theaters, PARTNER_RENAME_MAP, filter_out_partner_own_accounts, apply_coco_final
from utils import APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, PARTNER_ALIASES as _PA_OKR

# Managed partner universe — same as Adoption Metrics default scope
_GSI_OKR = {'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
            'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting'}
_NOAM_OKR = set(p for p in _PA_OKR.get('--- NOAM RSIs ---', []) if not p.startswith('---')) | {'LTI Mindtree','Kipi.ai'}
_ALL_MANAGED_OKR = _GSI_OKR | _NOAM_OKR | set(APJ_RSI_REGION_MAP.keys()) | set(EMEA_RSI_REGION_MAP.keys())

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])
start_date = st.session_state.get("okr_start_date", date(2026, 5, 1))
end_date = st.session_state.get("okr_end_date", date(2026, 7, 31))
include_account_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter = st.session_state.get("confidence_filter", ["High"])
confidence = 'High' if confidence_filter == ['High'] else ('Medium' if confidence_filter else None)

st.title(":material/check_circle: OKR: CoCo Adoption per Partner")

TARGET_PCT = 75

# Auto-set target based on region: EMEA/APJ → 50%, all others → 75%
_apj_emea_regions = {'EMEA', 'APJ', 'Korea', 'Japan', 'ASEAN', 'ANZ', 'India',
                     'CentralEMEA', 'SouthEMEA', 'NorthEMEA', 'UK', 'META', 'EMEACommercial'}
target = 50 if region in _apj_emea_regions else TARGET_PCT
min_use_cases = 1

st.caption(f"Track CoCo attachment target for partner use cases (Stages 3-7) | Region: {region} | {start_date} to {end_date}")

q_start = str(start_date)
q_end = str(end_date)

# Get base summary, stage breakdown and WoW adoption delta (same as Coverage page)
base_summary = get_okr_partner_summary(conn, q_start, q_end, region=region, include_account_coco=False, confidence=None)
stage_breakdown = get_okr_stage_breakdown(conn, region=region, start_date=q_start, end_date=q_end, include_account_coco=False, confidence=None)
adoption_wow = get_coco_final_wow(conn)
credit_data = get_partner_credit_consumption(conn, base_summary['PARTNER_NAME'].tolist(), q_start)

if len(base_summary) == 0:
    st.info("No use cases found for the selected date range.")
    st.stop()

# Apply sidebar partner filter; default to managed partners when none selected
_using_default_managed = not selected_partners
if selected_partners:
    partner_names = resolve_partner_filter(selected_partners)
    base_summary = base_summary[base_summary['PARTNER_NAME'].isin(partner_names)]
    if len(base_summary) == 0:
        st.info(f"No data for selected partners.")
        st.stop()
else:
    # Default: scope to managed partners (GSI + NOAM RSI + APJ RSI + EMEA RSI)
    base_summary = base_summary[base_summary['PARTNER_NAME'].isin(_ALL_MANAGED_OKR)]

def _apply_managed_geo_filter(bc):
    """Apply same geo restrictions as Adoption Metrics _managed_bc:
    NOAM RSI → NoAM theaters, APJ RSI → country, EMEA RSI → region, GSI → global."""
    if bc is None or len(bc) == 0:
        return bc
    _noam_theaters = ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec')
    parts = []
    parts.append(bc[bc['PARTNER_NAME'].isin(_GSI_OKR)])
    parts.append(bc[bc['PARTNER_NAME'].isin(_NOAM_OKR) & bc['THEATER_NAME'].isin(_noam_theaters)])
    if 'REGION_NAME' in bc.columns:
        _apj = bc[bc['PARTNER_NAME'].isin(set(APJ_RSI_REGION_MAP.keys()))].copy()
        _apj['_c'] = _apj['PARTNER_NAME'].map({k: v[1] for k, v in APJ_RSI_REGION_MAP.items()})
        parts.append(_apj[_apj['REGION_NAME'] == _apj['_c']].drop(columns=['_c']))
        _emea = bc[bc['PARTNER_NAME'].isin(set(EMEA_RSI_REGION_MAP.keys()))].copy()
        _emea['_c'] = _emea['PARTNER_NAME'].map({k: v[1] for k, v in EMEA_RSI_REGION_MAP.items()})
        parts.append(_emea[_emea['REGION_NAME'] == _emea['_c']].drop(columns=['_c']))
    else:
        parts.append(bc[bc['PARTNER_NAME'].isin(set(APJ_RSI_REGION_MAP.keys()))])
        parts.append(bc[bc['PARTNER_NAME'].isin(set(EMEA_RSI_REGION_MAP.keys()))])
    return pd.concat([p for p in parts if len(p) > 0], ignore_index=True) if parts else bc

# Compute CoCo using full confidence scoring when account-level is enabled
if include_account_coco:
    bulk_conf = get_bulk_confidence_scores(conn, base_summary['PARTNER_NAME'].tolist(), q_start, q_end)
    if len(bulk_conf) > 0:
        # Always apply APJ/EMEA geo restrictions — country-scoped per partner agreement.
        # For GSI/NOAM the geo filter only applies in the default managed scope
        # (a user who explicitly picks a single NOAM partner doesn't need theater filtering).
        if _using_default_managed:
            bulk_conf = _apply_managed_geo_filter(bulk_conf)
        else:
            # Even in a custom partner selection, APJ/EMEA must stay country-scoped
            _apj_names  = set(APJ_RSI_REGION_MAP.keys())
            _emea_names = set(EMEA_RSI_REGION_MAP.keys())
            if 'REGION_NAME' in bulk_conf.columns:
                _non_rsi = bulk_conf[~bulk_conf['PARTNER_NAME'].isin(_apj_names | _emea_names)]
                _apj  = bulk_conf[bulk_conf['PARTNER_NAME'].isin(_apj_names)].copy()
                _apj['_c']  = _apj['PARTNER_NAME'].map({k: v[1] for k, v in APJ_RSI_REGION_MAP.items()})
                _apj  = _apj[_apj['REGION_NAME'] == _apj['_c']].drop(columns=['_c'])
                _emea = bulk_conf[bulk_conf['PARTNER_NAME'].isin(_emea_names)].copy()
                _emea['_c'] = _emea['PARTNER_NAME'].map({k: v[1] for k, v in EMEA_RSI_REGION_MAP.items()})
                _emea = _emea[_emea['REGION_NAME'] == _emea['_c']].drop(columns=['_c'])
                bulk_conf = pd.concat([p for p in [_non_rsi, _apj, _emea] if len(p) > 0], ignore_index=True)
        # Apply sidebar region filter
        if region and region != 'Global':
            _theaters = resolve_region_theaters(region)
            if _theaters is not None:
                bulk_conf = bulk_conf[bulk_conf['THEATER_NAME'].isin(_theaters)]

        # Merge partner aliases (IBM Consulting→IBM, EY aliases, etc.) before groupby
        bulk_conf['PARTNER_NAME'] = bulk_conf['PARTNER_NAME'].replace(PARTNER_RENAME_MAP)
        # Apply stage filter from sidebar
        _sel_stages = st.session_state.get('selected_stages', [])
        if _sel_stages and 'USE_CASE_STAGE' in bulk_conf.columns:
            bulk_conf = bulk_conf[bulk_conf['USE_CASE_STAGE'].isin(_sel_stages)]
        bands = confidence_filter if confidence_filter else ['High', 'Medium', 'Low']
        bulk_conf['IS_COCO_FINAL'] = apply_coco_final(bulk_conf, bands)

        # Recompute per-partner summary
        coco_eacv = bulk_conf[bulk_conf['IS_COCO_FINAL']].groupby('PARTNER_NAME')['USE_CASE_EACV'].sum().reset_index()
        coco_eacv.columns = ['PARTNER_NAME', 'COCO_EACV']
        summary = bulk_conf.groupby('PARTNER_NAME').agg(
            TOTAL_USE_CASES=('USE_CASE_ID', 'count'),
            COCO_USE_CASES=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
        ).reset_index()
        summary = summary.merge(coco_eacv, on='PARTNER_NAME', how='left')
        summary['COCO_EACV'] = summary['COCO_EACV'].fillna(0)
        summary['NON_COCO_USE_CASES'] = summary['TOTAL_USE_CASES'] - summary['COCO_USE_CASES']
        summary['COCO_PCT'] = round(summary['COCO_USE_CASES'] * 100.0 / summary['TOTAL_USE_CASES'].replace(0, float('nan')), 1).fillna(0)
        # Count account-level use cases at the selected confidence bands
        high_conf_coco = int(bulk_conf['CONFIDENCE_BAND'].isin(bands).sum())

        # Recompute stage breakdown with same IS_COCO_FINAL logic (same as Coverage page)
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

        # Aggregate credits/tokens directly from IS_COCO_FINAL rows in bulk_conf
        # (credits are now embedded in _confidence_scored_query, no separate DB call needed)
        _coco_final_df = bulk_conf[bulk_conf['IS_COCO_FINAL']].copy()
        _coco_final_df = filter_out_partner_own_accounts(_coco_final_df)
        # Deduplicate: each account counted once per partner to avoid double-counting
        _credit_dedup = _coco_final_df.drop_duplicates(subset=['PARTNER_NAME', 'ACCOUNT_NAME_UPPER'])
        _surface_cols = ['Q2_CREDITS','Q2_TOKENS','LAST7_CREDITS','PRIOR7_CREDITS','LAST7_TOKENS','PRIOR7_TOKENS',
                         'CLI_CREDITS','CLI_TOKENS','CLI_REQUESTS',
                         'DESKTOP_CREDITS','DESKTOP_TOKENS','DESKTOP_REQUESTS',
                         'UI_CREDITS','UI_TOKENS','UI_REQUESTS','AGENT_REQUESTS']
        for _c in _surface_cols:
            if _c in _credit_dedup.columns:
                _credit_dedup = _credit_dedup.copy()
                _credit_dedup[_c] = _credit_dedup[_c].apply(lambda x: float(x) if x is not None else 0.0)
        _agg_dict = dict(Q2_CREDITS=('Q2_CREDITS','sum'), Q2_TOKENS=('Q2_TOKENS','sum'),
                         LAST7_CREDITS=('LAST7_CREDITS','sum'), PRIOR7_CREDITS=('PRIOR7_CREDITS','sum'),
                         LAST7_TOKENS=('LAST7_TOKENS','sum'), PRIOR7_TOKENS=('PRIOR7_TOKENS','sum'))
        for _c in ['CLI_CREDITS','CLI_TOKENS','CLI_REQUESTS','DESKTOP_CREDITS','DESKTOP_TOKENS',
                   'DESKTOP_REQUESTS','UI_CREDITS','UI_TOKENS','UI_REQUESTS','AGENT_REQUESTS']:
            if _c in _credit_dedup.columns:
                _agg_dict[_c] = (_c, 'sum')
        _partner_usage = _credit_dedup.groupby('PARTNER_NAME').agg(**_agg_dict).reset_index()
        # Compute surface % and Maturity tier
        _tot = _partner_usage.get('Q2_CREDITS', 0).replace(0, float('nan'))
        for _surf in ['CLI', 'DESKTOP', 'UI']:
            _col = f'{_surf}_CREDITS'
            if _col in _partner_usage.columns:
                _partner_usage[f'{_surf}_PCT'] = (_partner_usage[_col] / _tot * 100).round(1).fillna(0)
        if all(c in _partner_usage.columns for c in ['CLI_PCT','DESKTOP_PCT','UI_PCT']):
            def _maturity(r):
                depth = r['CLI_PCT'] + r['DESKTOP_PCT']
                if depth >= 50: return 'Production'
                if r['UI_PCT'] >= 70: return 'Exploratory'
                if depth > 0: return 'Mixed'
                return 'No Signal'
            _partner_usage['COCO_MATURITY'] = _partner_usage.apply(_maturity, axis=1)
        _accts_usage = _credit_dedup[_credit_dedup['Q2_CREDITS'] > 0].groupby('PARTNER_NAME')['ACCOUNT_NAME_UPPER'].nunique().reset_index(name='ACCTS_WITH_USAGE')
        _partner_usage = _partner_usage.merge(_accts_usage, on='PARTNER_NAME', how='left')
        _partner_usage['ACCTS_WITH_USAGE'] = _partner_usage['ACCTS_WITH_USAGE'].fillna(0).astype(int)
        # Portfolio-level WoW (sum last7 vs sum prior7)
        _partner_usage['CREDITS_WOW_PCT'] = (
            (_partner_usage['LAST7_CREDITS'] - _partner_usage['PRIOR7_CREDITS'])
            * 100.0 / _partner_usage['PRIOR7_CREDITS'].replace(0, float('nan'))
        ).round(1)
        _partner_usage['TOKENS_WOW_PCT'] = (
            (_partner_usage['LAST7_TOKENS'] - _partner_usage['PRIOR7_TOKENS'])
            * 100.0 / _partner_usage['PRIOR7_TOKENS'].replace(0, float('nan'))
        ).round(1)
        summary = summary.merge(_partner_usage, on='PARTNER_NAME', how='left')
    else:
        # Rename aliases in base_summary and re-aggregate so merged partners show as one row
        base_summary = base_summary.copy()
        base_summary['PARTNER_NAME'] = base_summary['PARTNER_NAME'].replace(PARTNER_RENAME_MAP)
        if base_summary['PARTNER_NAME'].duplicated().any():
            _agg = base_summary.groupby('PARTNER_NAME').agg(
                total_use_cases=('total_use_cases', 'sum'),
                coco_use_cases=('coco_use_cases', 'sum'),
                total_eacv=('total_eacv', 'sum'),
                coco_eacv=('coco_eacv', 'sum'),
            ).reset_index()
            _agg['non_coco_use_cases'] = _agg['total_use_cases'] - _agg['coco_use_cases']
            _agg['coco_pct'] = round(_agg['coco_use_cases'] * 100.0 / _agg['total_use_cases'].replace(0, float('nan')), 1).fillna(0)
            _agg['MEETS_TARGET'] = _agg['coco_pct'] >= target
            base_summary = _agg
        summary = base_summary
        bulk_conf = pd.DataFrame()
        high_conf_coco = 0
else:
    summary = base_summary
    bulk_conf = pd.DataFrame()
    high_conf_coco = 0

summary['MEETS_TARGET'] = summary['COCO_PCT'] >= target
filtered = summary[summary['TOTAL_USE_CASES'] >= min_use_cases].copy()

st.divider()

total_partners = len(filtered)
meeting_target = filtered['MEETS_TARGET'].sum()
not_meeting = total_partners - meeting_target
overall_coco = filtered['COCO_USE_CASES'].sum()
overall_total = filtered['TOTAL_USE_CASES'].sum()
overall_pct = round(overall_coco * 100.0 / overall_total, 1) if overall_total > 0 else 0
high_conf_pct = round(high_conf_coco * 100.0 / overall_total, 1) if overall_total > 0 else 0

# Inject context for Ask AI
import streamlit as _st_ctx
_top_partners = filtered.sort_values('COCO_PCT', ascending=False).head(5)
_top_str = "; ".join(f"{r.PARTNER_NAME} {r.COCO_PCT:.1f}%" for _, r in _top_partners.iterrows())
_bot_partners = filtered[~filtered['MEETS_TARGET']].sort_values('COCO_PCT', ascending=False).head(5)
_bot_str = "; ".join(f"{r.PARTNER_NAME} {r.COCO_PCT:.1f}%" for _, r in _bot_partners.iterrows())
_st_ctx.session_state.ask_ai_context = (
    f"Current page: OKR CoCo Adoption. Region: {region}. Period: {start_date} to {end_date}.\n"
    f"Partners tracked: {total_partners}. Meeting {target}% target: {int(meeting_target)}. Below target: {int(not_meeting)}.\n"
    f"Overall CoCo%: {overall_pct}% ({int(overall_coco)}/{int(overall_total)} UCs).\n"
    f"Top partners by CoCo%: {_top_str}.\n"
    f"Partners below target (closest first): {_bot_str}."
    + build_filter_context()
    + (build_credit_wow_context(summary) if 'summary' in dir() and summary is not None and len(summary) > 0 else "")
    + (build_uc_pattern_context(conf_scores if ('conf_scores' in dir() and conf_scores is not None and len(conf_scores) > 0) else (detail if 'detail' in dir() and detail is not None and len(detail) > 0 else None)))
)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Partners Tracked", total_partners)
c2.metric(f"Meeting {target}%", int(meeting_target), f"{round(meeting_target*100/total_partners)}%" if total_partners else "0%")
c3.metric(f"Below {target}%", int(not_meeting), delta_color="inverse")

# WoW deltas from IS_COCO_FINAL weekly snapshot (same as Coverage page)
wow_overall = adoption_wow[adoption_wow['PARTNER_NAME'].isna()] if len(adoption_wow) > 0 else None
wow_coco_ucs_delta = None
wow_coco_pct_delta = None
if wow_overall is not None and len(wow_overall) > 0:
    row = wow_overall.iloc[0]
    if pd.notna(row.get('WOW_COCO_UCS')):
        wow_coco_ucs_delta = f"{int(row['WOW_COCO_UCS']):+d} vs last week"
    if pd.notna(row.get('WOW_COCO_PCT')):
        wow_coco_pct_delta = f"{float(row['WOW_COCO_PCT']):+.1f}% vs last week"

conf_desc = 'High' if confidence_filter == ['High'] else 'High + Medium' if confidence_filter else 'All account-level'
c4.metric("Overall CoCo %", f"{overall_pct}%", wow_coco_pct_delta if wow_coco_pct_delta else f"Target: {target}%",
    help=f"SE/PSE/Flag always + Account Level at {conf_desc} confidence (full scoring)")
c5.metric("CoCo Use Cases", f"{int(overall_coco)}/{int(overall_total)}", wow_coco_ucs_delta,
    help=f"Total IS_COCO_FINAL use cases vs total tracked")
c6.metric("Total EACV", f"${filtered['TOTAL_EACV'].sum()/1_000_000:.1f}M")

st.divider()

# --- Stage Breakdown (from Coverage page) ---
st.subheader("CoCo % by Stage Breakdown")
if len(stage_breakdown) > 0:
    _stage_filtered = stage_breakdown[stage_breakdown['PARTNER_NAME'].isin(filtered['PARTNER_NAME'].tolist())]
    stage_agg = _stage_filtered.groupby('USE_CASE_STAGE').agg({
        'TOTAL_UCS': 'sum', 'COCO_UCS': 'sum', 'TOTAL_EACV': 'sum', 'COCO_EACV': 'sum'
    }).reset_index()
    stage_agg['COCO_PCT'] = (stage_agg['COCO_UCS'] * 100.0 / stage_agg['TOTAL_UCS'].replace(0, pd.NA)).round(1).fillna(0)
    stage_agg['NON_COCO'] = stage_agg['TOTAL_UCS'] - stage_agg['COCO_UCS']
    stage_agg['STAGE_SHORT'] = stage_agg['USE_CASE_STAGE'].str.replace(r'^\d+ - ', '', regex=True)
    stage_agg = stage_agg.sort_values('USE_CASE_STAGE')

    fig = go.Figure()
    fig.add_trace(go.Bar(name='CoCo', x=stage_agg['STAGE_SHORT'], y=stage_agg['COCO_UCS'],
        marker_color='#29B5E8', text=stage_agg['COCO_UCS'], textposition='inside'))
    fig.add_trace(go.Bar(name='Non-CoCo', x=stage_agg['STAGE_SHORT'], y=stage_agg['NON_COCO'],
        marker_color='#e0e0e0', text=stage_agg['NON_COCO'], textposition='inside'))
    fig.update_layout(barmode='stack', height=350, xaxis_title='', yaxis_title='Use Cases',
        legend=dict(orientation='h', y=1.12))
    for _, row in stage_agg.iterrows():
        fig.add_annotation(x=row['STAGE_SHORT'], y=row['TOTAL_UCS'],
            text=f"{row['COCO_PCT']:.0f}%", showarrow=False, yshift=12,
            font=dict(size=13, color='#29B5E8', weight='bold'))
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

st.subheader("Partner Scorecard")

filtered_sorted = filtered.sort_values('COCO_PCT', ascending=False)

# Per-partner attribution (SE/PSE/Feature Flag) — same query as Coverage page
_partner_list = filtered_sorted['PARTNER_NAME'].tolist()
if _partner_list:
    _partners_sql = "','".join(_partner_list)
    _attribution_query = f"""
    WITH coco_active_accounts AS (
        SELECT DISTINCT UPPER(f.salesforce_account_name) AS ACCOUNT_NAME_UPPER
        FROM snowscience.llm.cortex_code_user_day_fact f
        WHERE f.ds >= '{q_start}' AND f.snowflake_account_type = 'Customer' AND f.total_daily_requests > 0
        AND f.ACCOUNT_ID IN (
            SELECT DISTINCT ACCOUNT_ID FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_STG
            WHERE ds >= '{q_start}' AND SKILL_CHOICE IS NOT NULL AND SKILL_CHOICE != ''
        )
    )
    SELECT uc.PARTNER_NAME,
        SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'SE_COMMENTS'      THEN 1 ELSE 0 END) AS SE_COMMENTS,
        SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'PARTNER_COMMENTS' THEN 1 ELSE 0 END) AS PSE_COMMENTS,
        SUM(CASE WHEN uc.IS_COCO AND uc.COCO_SOURCE = 'FEATURE_FLAG'     THEN 1 ELSE 0 END) AS FEATURE_FLAG
    FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
    WHERE uc.PARTNER_NAME IN ('{_partners_sql}')
    AND (
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan')
            AND uc.DECISION_DATE >= '{q_start}' AND uc.DECISION_DATE <= '{q_end}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed')
            AND uc.GO_LIVE_DATE >= '{q_start}' AND uc.GO_LIVE_DATE <= '{q_end}')
    )
    GROUP BY uc.PARTNER_NAME
    """
    attribution_data = conn.query(_attribution_query)
else:
    attribution_data = pd.DataFrame()

# WoW adoption delta per partner (from IS_COCO_FINAL weekly snapshot)
wow_partners = adoption_wow[adoption_wow['PARTNER_NAME'].notna()][['PARTNER_NAME', 'WOW_COCO_PCT', 'WOW_COCO_UCS']] if len(adoption_wow) > 0 else pd.DataFrame()

display_df = filtered_sorted[['PARTNER_NAME', 'TOTAL_USE_CASES', 'COCO_USE_CASES', 'NON_COCO_USE_CASES', 'TOTAL_EACV', 'COCO_EACV', 'MEETS_TARGET']].copy()
display_df['TOTAL_EACV'] = display_df['TOTAL_EACV'].apply(lambda x: f"${(x or 0)/1000:.0f}K" if (x or 0) < 1_000_000 else f"${(x or 0)/1_000_000:.1f}M")
display_df['COCO_EACV'] = display_df['COCO_EACV'].apply(lambda x: f"${(x or 0)/1000:.0f}K" if (x or 0) < 1_000_000 else f"${(x or 0)/1_000_000:.1f}M")
display_df['GAP'] = filtered_sorted.apply(
    lambda r: max(0, int((target / 100.0 * r['TOTAL_USE_CASES']) - r['COCO_USE_CASES'] + 0.999)), axis=1
)
display_df['COCO_PCT'] = filtered_sorted['COCO_PCT']

# Merge attribution
if len(attribution_data) > 0:
    display_df = display_df.merge(attribution_data, on='PARTNER_NAME', how='left')
    display_df[['SE_COMMENTS', 'PSE_COMMENTS', 'FEATURE_FLAG']] = display_df[['SE_COMMENTS', 'PSE_COMMENTS', 'FEATURE_FLAG']].fillna(0).astype(int)
else:
    display_df['SE_COMMENTS'] = 0
    display_df['PSE_COMMENTS'] = 0
    display_df['FEATURE_FLAG'] = 0

# Merge WoW adoption delta
if len(wow_partners) > 0:
    display_df = display_df.merge(wow_partners, on='PARTNER_NAME', how='left')
else:
    display_df['WOW_COCO_PCT'] = None
    display_df['WOW_COCO_UCS'] = None

# Merge Q2 Credits / Tokens (Coverage page approach)
_display_cols = ['PARTNER_NAME', 'TOTAL_USE_CASES', 'COCO_USE_CASES', 'COCO_PCT', 'WOW_COCO_PCT', 'WOW_COCO_UCS',
                 'NON_COCO_USE_CASES', 'TOTAL_EACV', 'COCO_EACV', 'SE_COMMENTS', 'PSE_COMMENTS', 'FEATURE_FLAG']
_col_cfg = {
    'PARTNER_NAME':      st.column_config.TextColumn("Partner", width="medium"),
    'TOTAL_USE_CASES':   st.column_config.NumberColumn("Total UCs", format="%d"),
    'COCO_USE_CASES':    st.column_config.NumberColumn("CoCo UCs", format="%d"),
    'COCO_PCT':          st.column_config.ProgressColumn("CoCo %", min_value=0, max_value=100, format="%.1f%%"),
    'WOW_COCO_PCT':      st.column_config.NumberColumn("WoW Δ%", format="%+.1f%%", help="Week-over-week change in CoCo adoption %"),
    'WOW_COCO_UCS':      st.column_config.NumberColumn("WoW Δ UCs", format="%+d", help="Week-over-week change in CoCo use case count"),
    'NON_COCO_USE_CASES':st.column_config.NumberColumn("Non-CoCo", format="%d"),
    'TOTAL_EACV':        st.column_config.TextColumn("Total EACV"),
    'COCO_EACV':         st.column_config.TextColumn("CoCo EACV"),
    'SE_COMMENTS':       st.column_config.NumberColumn("SE Comments", format="%d"),
    'PSE_COMMENTS':      st.column_config.NumberColumn("PSE Comments", format="%d"),
    'FEATURE_FLAG':      st.column_config.NumberColumn("Feature Flag", format="%d"),
}
if 'Q2_CREDITS' in filtered_sorted.columns:
    _display_cols += ['Q2_CREDITS', 'LAST7_CREDITS', 'CREDITS_WOW_PCT', 'Q2_TOKENS', 'LAST7_TOKENS', 'TOKENS_WOW_PCT', 'ACCTS_WITH_USAGE']
    _display_df_credits = filtered_sorted[['PARTNER_NAME']].merge(
        summary[['PARTNER_NAME', 'Q2_CREDITS', 'LAST7_CREDITS', 'CREDITS_WOW_PCT', 'Q2_TOKENS', 'LAST7_TOKENS', 'TOKENS_WOW_PCT', 'ACCTS_WITH_USAGE']],
        on='PARTNER_NAME', how='left'
    )
    display_df = display_df.merge(_display_df_credits, on='PARTNER_NAME', how='left')
    _col_cfg['Q2_CREDITS']    = st.column_config.NumberColumn("CoCo Credits", format="$%.0f",
        help="Cumulative CoCo credit spend on IS_COCO_FINAL accounts within the date range")
    _col_cfg['LAST7_CREDITS']  = st.column_config.NumberColumn("Last 7d Credits",  format="$%.0f",
        help="Credit spend in the last 7 rolling days — same window as Deep Dive header")
    _col_cfg['CREDITS_WOW_PCT'] = st.column_config.NumberColumn("7D Credits WoW%",     format="%+.1f%%",
        help="Week-over-week % change in credits (last 7d vs prior 7d)")
    _col_cfg['Q2_TOKENS']       = st.column_config.NumberColumn("Tokens",        format="%d",
        help="Cumulative token usage on IS_COCO_FINAL accounts within the date range")
    _col_cfg['LAST7_TOKENS']    = st.column_config.NumberColumn("Last 7d Tokens",   format="%d",
        help="Token usage in the last 7 rolling days")
    _col_cfg['TOKENS_WOW_PCT']  = st.column_config.NumberColumn("7D Tokens WoW%",      format="%+.1f%%",
        help="Week-over-week % change in tokens (last 7d vs prior 7d)")
    _col_cfg['ACCTS_WITH_USAGE'] = st.column_config.NumberColumn("Accts w/ Usage",  format="%d",
        help="IS_COCO_FINAL accounts with actual CoCo credit consumption")

_df_show = display_df[[c for c in _display_cols if c in display_df.columns]].copy()
_wow_cols = [c for c in ['CREDITS_WOW_PCT', 'TOKENS_WOW_PCT'] if c in _df_show.columns]

def _wow_bg(val):
    if pd.isna(val) or val == 0: return ''
    return 'background-color: #d4edda; color: #155724' if val > 0 else 'background-color: #f8d7da; color: #721c24'

_styled_scorecard = _df_show.style.map(_wow_bg, subset=_wow_cols) if _wow_cols else _df_show.style
st.dataframe(
    _styled_scorecard,
    column_config=_col_cfg,
    hide_index=True, use_container_width=True, height=500
)
st.caption("Attribution columns may overlap — a use case can have both account-level usage AND comments.")

# --- Surface Adoption Donut (CLI / Desktop / UI) ---
st.divider()
st.subheader("CoCo Surface Adoption Breakdown")
if 'CLI_CREDITS' in summary.columns and summary['CLI_CREDITS'].notna().any():
    _surf_credits = {
        'CLI':     float(summary['CLI_CREDITS'].fillna(0).sum()),
        'Desktop': float(summary['DESKTOP_CREDITS'].fillna(0).sum()),
        'UI':      float(summary['UI_CREDITS'].fillna(0).sum()),
    }
    _surf_tokens = {
        'CLI':     float(summary['CLI_TOKENS'].fillna(0).sum()) if 'CLI_TOKENS' in summary.columns else 0,
        'Desktop': float(summary['DESKTOP_TOKENS'].fillna(0).sum()) if 'DESKTOP_TOKENS' in summary.columns else 0,
        'UI':      float(summary['UI_TOKENS'].fillna(0).sum()) if 'UI_TOKENS' in summary.columns else 0,
    }
    _surf_colors = ['#29B5E8', '#11567F', '#75C2E2']

    def _make_surface_donut(values_dict, title, center_label):
        labels = list(values_dict.keys())
        values = list(values_dict.values())
        fig = go.Figure(go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker_colors=_surf_colors,
            textinfo='label+percent',
            hovertemplate='%{label}: %{value:,.0f} (%{percent})<extra></extra>',
        ))
        fig.update_layout(
            title=dict(text=title, x=0.5, xanchor='center', font=dict(size=14)),
            annotations=[dict(text=center_label, x=0.5, y=0.5, font_size=15, showarrow=False, font_color='#333')],
            legend=dict(orientation='h', yanchor='bottom', y=-0.2, xanchor='center', x=0.5),
            height=340,
            margin=dict(t=55, b=65, l=20, r=20),
        )
        return fig

    def _fmt_surf_tokens(t):
        if t >= 1_000_000: return f"{t/1_000_000:.1f}M tok"
        if t >= 1_000: return f"{t/1_000:.0f}K tok"
        return f"{t:,.0f} tok"

    _total_cred = sum(_surf_credits.values())
    _total_tok  = sum(_surf_tokens.values())
    _donut_col1, _donut_col2 = st.columns(2)
    with _donut_col1:
        st.plotly_chart(
            _make_surface_donut(_surf_credits, "CoCo Credits by Surface", f"${_total_cred:,.0f}"),
            use_container_width=True
        )
    with _donut_col2:
        st.plotly_chart(
            _make_surface_donut(_surf_tokens, "CoCo Tokens by Surface", _fmt_surf_tokens(_total_tok)),
            use_container_width=True
        )
    st.caption("Surface breakdown across all IS_COCO_FINAL accounts. CLI = terminal, Desktop = VS Code extension, UI = Snowsight web.")
else:
    st.info("Surface breakdown unavailable. Enable 'Account Level CoCo' in the sidebar.")

st.divider()

st.subheader("Partner Deep Dive")
partner_list = filtered_sorted['PARTNER_NAME'].tolist()
selected_partner = st.selectbox("Select Partner", partner_list, key="okr_partner_select")

if selected_partner:
    detail = get_okr_coco_adoption(conn, q_start, q_end, region=region, include_account_coco=include_account_coco, confidence=confidence)
    detail = detail.copy()
    detail['PARTNER_NAME'] = detail['PARTNER_NAME'].replace(PARTNER_RENAME_MAP)
    partner_detail = detail[detail['PARTNER_NAME'] == selected_partner]

    # Apply APJ/EMEA country-level geo scoping in the deep dive —
    # NTT DATA → Japan only, Megazone → Korea only, etc.
    if len(partner_detail) > 0 and 'REGION_NAME' in partner_detail.columns:
        _raw_partner = next((k for k, v in PARTNER_RENAME_MAP.items() if v == selected_partner), selected_partner)
        if _raw_partner in APJ_RSI_REGION_MAP or selected_partner in APJ_RSI_REGION_MAP:
            _country = APJ_RSI_REGION_MAP.get(_raw_partner, APJ_RSI_REGION_MAP.get(selected_partner, (None, None)))[1]
            if _country:
                partner_detail = partner_detail[partner_detail['REGION_NAME'] == _country]
        elif _raw_partner in EMEA_RSI_REGION_MAP or selected_partner in EMEA_RSI_REGION_MAP:
            _country = EMEA_RSI_REGION_MAP.get(_raw_partner, EMEA_RSI_REGION_MAP.get(selected_partner, (None, None)))[1]
            if _country:
                partner_detail = partner_detail[partner_detail['REGION_NAME'] == _country]

    if len(partner_detail) > 0:
        # Override IS_COCO_ATTACHED using full confidence scoring (same as summary metrics)
        conf_scores = pd.DataFrame()
        if include_account_coco:
            conf_scores = get_usecase_confidence_scores(conn, selected_partner, q_start, q_end)
            if len(conf_scores) > 0:
                partner_detail = partner_detail.copy()
                conf_map = conf_scores[['USE_CASE_ID', 'CONFIDENCE_BAND']].set_index('USE_CASE_ID')
                partner_detail['CONFIDENCE_BAND'] = partner_detail['USE_CASE_ID'].map(conf_map['CONFIDENCE_BAND'])
                bands = confidence_filter if confidence_filter else ['High', 'Medium', 'Low']
                is_flag = partner_detail['COCO_SOURCE'].notna()
                has_conf = partner_detail['CONFIDENCE_BAND'].isin(bands)
                partner_detail['IS_COCO_ATTACHED'] = is_flag | has_conf

                def _rebuild_flags(row):
                    parts = []
                    band = row.get('CONFIDENCE_BAND')
                    if pd.notna(band) and band in bands:
                        parts.append(f"Account ({band})")
                    if row['COCO_SOURCE'] == 'SE_COMMENTS':
                        parts.append('SE Comments')
                    elif row['COCO_SOURCE'] == 'PARTNER_COMMENTS':
                        parts.append('PSE Comments')
                    elif row['COCO_SOURCE'] == 'FEATURE_FLAG':
                        parts.append('Feature Flag')
                    return ' | '.join(parts)
                partner_detail['ATTRIBUTION_FLAGS'] = partner_detail.apply(_rebuild_flags, axis=1)

        # Apply stage filter from sidebar to partner detail UCs
        _sel_stages = st.session_state.get('selected_stages', [])
        if _sel_stages and 'USE_CASE_STAGE' in partner_detail.columns:
            partner_detail = partner_detail[partner_detail['USE_CASE_STAGE'].isin(_sel_stages)]

        p_stats = filtered_sorted[filtered_sorted['PARTNER_NAME'] == selected_partner].iloc[0]
        coco_pct = p_stats['COCO_PCT']

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Use Cases", int(p_stats['TOTAL_USE_CASES']))
        c2.metric("CoCo Attached", int(p_stats['COCO_USE_CASES']))
        c3.metric("CoCo Usecase %", f"{coco_pct:.1f}%", f"{'MET' if coco_pct >= target else 'BELOW'} {target}% target")
        gap = max(0, int((target / 100.0 * p_stats['TOTAL_USE_CASES']) - p_stats['COCO_USE_CASES'] + 0.999))
        c4.metric("UCs Needed for Target", gap if gap > 0 else "0 (Met!)")
        # Account-only: CoCo attached but no comments/flag (COCO_SOURCE is NULL)
        account_only = int(partner_detail[(partner_detail['IS_COCO_ATTACHED'] == True) & (partner_detail['COCO_SOURCE'].isna())].shape[0])
        c5.metric("CoCo Attribution- Account Level Usage", account_only, help="CoCo via customer account usage, no SE/PSE comments")

        # Credit & token consumption from IS_COCO_FINAL summary (same as scorecard)
        _p_summary = summary[summary['PARTNER_NAME'] == selected_partner]
        if len(_p_summary) > 0 and 'Q2_CREDITS' in summary.columns:
            _ps = _p_summary.iloc[0]
            def _fmt_tok(n):
                if n is None or (isinstance(n, float) and pd.isna(n)):
                    return "N/A"
                n = float(n)
                if n >= 1_000_000_000: return f"{n/1_000_000_000:.2f}B"
                if n >= 1_000_000:     return f"{n/1_000_000:.1f}M"
                if n >= 1_000:         return f"{n/1_000:.1f}K"
                return f"{int(n)}"
            def _fmt_delta_cred(n):
                if n is None or (isinstance(n, float) and pd.isna(n)): return "N/A"
                return f"${float(n):+,.0f}"
            def _fmt_delta_tok(n):
                if n is None or (isinstance(n, float) and pd.isna(n)): return "N/A"
                n = float(n)
                if abs(n) >= 1_000_000_000: return f"{n/1_000_000_000:+.2f}B"
                if abs(n) >= 1_000_000:     return f"{n/1_000_000:+.1f}M"
                if abs(n) >= 1_000:         return f"{n/1_000:+.1f}K"
                return f"{int(n):+d}"
            _l7c  = float(_ps['LAST7_CREDITS'])  if pd.notna(_ps.get('LAST7_CREDITS'))  else None
            _p7c  = float(_ps['PRIOR7_CREDITS']) if pd.notna(_ps.get('PRIOR7_CREDITS')) else None
            _l7t  = float(_ps['LAST7_TOKENS'])   if pd.notna(_ps.get('LAST7_TOKENS'))   else None
            _p7t  = float(_ps['PRIOR7_TOKENS'])  if pd.notna(_ps.get('PRIOR7_TOKENS'))  else None
            _dcred = (_l7c - _p7c) if (_l7c is not None and _p7c is not None) else None
            _dtok  = (_l7t - _p7t) if (_l7t is not None and _p7t is not None) else None
            _cwow = float(_ps['CREDITS_WOW_PCT']) if pd.notna(_ps.get('CREDITS_WOW_PCT')) else None
            _twow = float(_ps['TOKENS_WOW_PCT'])  if pd.notna(_ps.get('TOKENS_WOW_PCT'))  else None
            _cred_delta = (
                (f"+${_dcred:,.0f} (+{_cwow:.1f}%)" if _dcred >= 0 else f"-${abs(_dcred):,.0f} ({_cwow:.1f}%)")
                if (_dcred is not None and _cwow is not None) else None
            )
            _tok_delta  = (f"{_fmt_delta_tok(_dtok)}  ({_twow:+.1f}%)"
                           if (_dtok is not None and _twow is not None) else None)
            _sep = "\n─────────────────────────────────────────"
            _stage_note = (
                f"\nStage filter: {', '.join([s.split(' - ')[0] for s in _sel_stages])}"
                if _sel_stages else "\nStage filter: All stages"
            )

            cr1, cr2, cr3, cr4 = st.columns(4)

            cr1.metric("CoCo Credits",
                f"${float(_ps['Q2_CREDITS']):,.0f}" if pd.notna(_ps.get('Q2_CREDITS')) else "N/A",
                help=(f"Credit Spend — IS_COCO_FINAL Accounts{_sep}\n"
                      f"Period:   May 1, 2026 – today\n"
                      f"Last 7d:  ${_l7c:,.0f}\n"
                      f"Prior 7d: ${_p7c:,.0f}\n"
                      f"WoW Δ:    {_fmt_delta_cred(_dcred)}\n"
                      f"WoW%:     {_cwow:+.1f}%"
                      f"{_stage_note}") if _l7c else
                     "Cumulative credit spend on IS_COCO_FINAL accounts")

            cr2.metric("Credits This Week",
                f"${_l7c:,.0f}" if _l7c is not None else "N/A",
                delta=_cred_delta,
                help=(f"Credit Spend \u2014 Last 7 Rolling Days{_sep}\n"
                      f"Last 7d:   ${_l7c:,.0f}  \u2190 shown above\n"
                      f"Prior 7d:  ${_p7c:,.0f}\n"
                      f"WoW Delta: {_fmt_delta_cred(_dcred)}\n"
                      f"WoW%:      {_cwow:+.1f}%\n\n"
                      f"Formula: (Last 7d \u2212 Prior 7d) \u00f7 Prior 7d \u00d7 100") if _l7c else
                     "Last 7d credit spend")

            cr3.metric("CoCo Tokens",
                _fmt_tok(_ps.get('Q2_TOKENS')),
                help=(f"Token Usage \u2014 IS_COCO_FINAL Accounts{_sep}\n"
                      f"Period:   May 1, 2026 \u2013 today\n"
                      f"Last 7d:  {_fmt_tok(_l7t)}\n"
                      f"Prior 7d: {_fmt_tok(_p7t)}\n"
                      f"WoW \u0394:    {_fmt_delta_tok(_dtok)}\n"
                      f"WoW%:     {_twow:+.1f}%"
                      f"{_stage_note}") if _l7t else
                     "Cumulative token usage on IS_COCO_FINAL accounts")

            cr4.metric("Tokens This Week",
                _fmt_tok(_l7t) if _l7t is not None else "N/A",
                delta=_tok_delta,
                help=(f"Token Usage \u2014 Last 7 Rolling Days{_sep}\n"
                      f"Last 7d:   {_fmt_tok(_l7t)}  \u2190 shown above\n"
                      f"Prior 7d:  {_fmt_tok(_p7t)}\n"
                      f"WoW Delta: {_fmt_delta_tok(_dtok)}\n"
                      f"WoW%:      {_twow:+.1f}%\n\n"
                      f"Formula: (Last 7d \u2212 Prior 7d) \u00f7 Prior 7d \u00d7 100") if _l7t else
                     "Last 7d token usage")
        elif len(credit_data[credit_data['PARTNER_NAME'] == selected_partner]) > 0:
            pc = credit_data[credit_data['PARTNER_NAME'] == selected_partner].iloc[0]
            cr1, cr2 = st.columns(2)
            cr1.metric("Total Credits", f"${pc['Q2_TOTAL_CREDITS']:,.0f}" if pd.notna(pc['Q2_TOTAL_CREDITS']) else "N/A")
            cr2.metric("WoW", f"{pc['WOW_PCT']:+.1f}%" if pd.notna(pc['WOW_PCT']) else "N/A")

        coco_ucs = partner_detail[partner_detail['IS_COCO_ATTACHED'] == True]
        non_coco_ucs = partner_detail[partner_detail['IS_COCO_ATTACHED'] == False]

        tab_coco, tab_noncoco, tab_confidence = st.tabs([
            f"CoCo Attached ({len(coco_ucs)})",
            f"Non-CoCo ({len(non_coco_ucs)}) - Opportunities",
            "Confidence Scoring"
        ])

        uc_cols = ['USE_CASE_NAME', 'ACCOUNT_NAME', 'THEATER_NAME', 'USE_CASE_STAGE', 'USE_CASE_EACV', 'TECHNICAL_USE_CASE', 'ATTRIBUTION_FLAGS']
        uc_config = {
            "USE_CASE_NAME": st.column_config.TextColumn("Use Case", width=200),
            "ACCOUNT_NAME": st.column_config.TextColumn("Account", width=160),
            "THEATER_NAME": st.column_config.TextColumn("Theater", width=80),
            "USE_CASE_STAGE": st.column_config.TextColumn("Stage", width=50),
            "USE_CASE_EACV": st.column_config.NumberColumn("EACV", format="$%.0f", width=90),
            "TECHNICAL_USE_CASE": st.column_config.TextColumn("Technical Type", width=150),
            "ATTRIBUTION_FLAGS": st.column_config.TextColumn("CoCo Source", width=140),
        }

        with tab_coco:
            if len(coco_ucs) > 0:
                coco_display = coco_ucs[uc_cols].copy()
                coco_display['USE_CASE_STAGE'] = coco_display['USE_CASE_STAGE'].str.extract(r'^(\d+)').iloc[:, 0]

                if len(conf_scores) > 0 and 'Q2_CREDITS' in conf_scores.columns:
                    _cm = conf_scores.drop_duplicates(subset=['ACCOUNT_NAME_UPPER']).set_index('ACCOUNT_NAME_UPPER')
                    _credit_cols = ['Q2_CREDITS', 'Q2_TOKENS', 'ACTIVE_DAYS', 'LAST_ACTIVE',
                                    'LAST7_CREDITS', 'PRIOR7_CREDITS', 'LAST7_TOKENS', 'PRIOR7_TOKENS',
                                    'CLI_CREDITS', 'CLI_TOKENS', 'CLI_REQUESTS',
                                    'DESKTOP_CREDITS', 'DESKTOP_TOKENS', 'DESKTOP_REQUESTS',
                                    'UI_CREDITS', 'UI_TOKENS', 'UI_REQUESTS', 'AGENT_REQUESTS']
                    for col in _credit_cols:
                        if col in _cm.columns:
                            coco_display[col] = coco_display['ACCOUNT_NAME'].str.upper().map(_cm[col])
                    for _c in ['Q2_CREDITS','Q2_TOKENS','LAST7_CREDITS','PRIOR7_CREDITS','LAST7_TOKENS','PRIOR7_TOKENS',
                               'CLI_CREDITS','DESKTOP_CREDITS','UI_CREDITS']:
                        if _c in coco_display.columns:
                            coco_display[_c] = pd.to_numeric(coco_display[_c], errors='coerce')
                    if 'LAST7_CREDITS' in coco_display.columns and 'PRIOR7_CREDITS' in coco_display.columns:
                        _p7c = pd.to_numeric(coco_display['PRIOR7_CREDITS'], errors='coerce').replace(0, float('nan'))
                        coco_display['CREDITS_WOW_PCT'] = ((pd.to_numeric(coco_display['LAST7_CREDITS'], errors='coerce') - pd.to_numeric(coco_display['PRIOR7_CREDITS'], errors='coerce')) / _p7c * 100).round(1)
                    if 'LAST7_TOKENS' in coco_display.columns and 'PRIOR7_TOKENS' in coco_display.columns:
                        _p7t = pd.to_numeric(coco_display['PRIOR7_TOKENS'], errors='coerce').replace(0, float('nan'))
                        coco_display['TOKENS_WOW_PCT'] = ((pd.to_numeric(coco_display['LAST7_TOKENS'], errors='coerce') - pd.to_numeric(coco_display['PRIOR7_TOKENS'], errors='coerce')) / _p7t * 100).round(1)
                    # Surface % per account (CLI/Desktop/UI)
                    if all(c in coco_display.columns for c in ['CLI_CREDITS','DESKTOP_CREDITS','UI_CREDITS']):
                        _tot_c = pd.to_numeric(coco_display['Q2_CREDITS'], errors='coerce').replace(0, float('nan'))
                        coco_display['CLI_%']     = (pd.to_numeric(coco_display['CLI_CREDITS'],     errors='coerce') / _tot_c * 100).round(1)
                        coco_display['DESKTOP_%'] = (pd.to_numeric(coco_display['DESKTOP_CREDITS'], errors='coerce') / _tot_c * 100).round(1)
                        coco_display['UI_%']      = (pd.to_numeric(coco_display['UI_CREDITS'],      errors='coerce') / _tot_c * 100).round(1)

                    _credit_sum_cols = ['Q2_CREDITS', 'LAST7_CREDITS',
                                        'Q2_TOKENS',  'LAST7_TOKENS']
                    _acct_deduped = coco_display.drop_duplicates(subset=['ACCOUNT_NAME'])
                    _total = {'USE_CASE_EACV': coco_display['USE_CASE_EACV'].sum() if 'USE_CASE_EACV' in coco_display.columns else None}
                    for _c in _credit_sum_cols:
                        _total[_c] = pd.to_numeric(_acct_deduped[_c], errors='coerce').sum() if _c in _acct_deduped.columns else None
                    _total_row = pd.DataFrame([{
                        'USE_CASE_NAME': '── TOTAL ──', 'ACCOUNT_NAME': '', 'THEATER_NAME': '',
                        'USE_CASE_STAGE': '', 'TECHNICAL_USE_CASE': '', 'ATTRIBUTION_FLAGS': '',
                        **_total
                    }])
                    coco_display = pd.concat([coco_display, _total_row], ignore_index=True)

                    _ordered_cols = [c for c in (
                        uc_cols + ['Q2_CREDITS', 'LAST7_CREDITS', 'CREDITS_WOW_PCT',
                                   'Q2_TOKENS',  'LAST7_TOKENS',  'TOKENS_WOW_PCT',
                                   'CLI_%', 'DESKTOP_%', 'UI_%', 'ACTIVE_DAYS']
                    ) if c in coco_display.columns]
                    coco_uc_config = {
                        **uc_config,
                        'Q2_CREDITS':        st.column_config.NumberColumn("Credits",      format="$%.0f",    width=110, help="Cumulative credit spend within the date range"),
                        'LAST7_CREDITS':     st.column_config.NumberColumn("Last 7d Credits", format="$%.0f",    width=115, help="Credit spend in last 7 days — same window as Deep Dive header"),
                        'CREDITS_WOW_PCT':   st.column_config.NumberColumn("7D Credits WoW%",    format="%+.1f%%",  width=110, help="Week-over-week % change in credits (last 7d vs prior 7d)"),
                        'Q2_TOKENS':         st.column_config.NumberColumn("Tokens",       format="%d",       width=100, help="Cumulative token usage within the date range"),
                        'LAST7_TOKENS':      st.column_config.NumberColumn("Last 7d Tokens",  format="%d",       width=110, help="Token usage in last 7 days"),
                        'TOKENS_WOW_PCT':    st.column_config.NumberColumn("7D Tokens WoW%",     format="%+.1f%%",  width=110, help="Week-over-week % change in tokens (last 7d vs prior 7d)"),
                        'CLI_%':             st.column_config.NumberColumn("CLI %",            format="%.1f%%",   width=70,  help="% of credits from CLI (terminal)"),
                        'DESKTOP_%':         st.column_config.NumberColumn("Desktop %",        format="%.1f%%",   width=80,  help="% of credits from VS Code extension"),
                        'UI_%':              st.column_config.NumberColumn("UI %",             format="%.1f%%",   width=70,  help="% of credits from Snowsight web UI"),
                        'ACTIVE_DAYS':       st.column_config.NumberColumn("Active Days",      format="%d",       width=90),
                    }
                    _dd_wow_cols = [c for c in ['CREDITS_WOW_PCT', 'TOKENS_WOW_PCT'] if c in coco_display.columns]
                    _dd_styled = coco_display[_ordered_cols].style.map(_wow_bg, subset=_dd_wow_cols) if _dd_wow_cols else coco_display[_ordered_cols].style
                    st.dataframe(_dd_styled, hide_index=True, use_container_width=True,
                                 column_config=coco_uc_config,
                                 height=38 + 35 * len(coco_display))
                    st.caption("EACV totals per use case. Credits/Tokens are account-level — accounts with multiple use cases are counted once in the TOTAL row (matches scorecard).")
                else:
                    # No credits data — still add total for EACV
                    _total_row = pd.DataFrame([{
                        'USE_CASE_NAME': '── TOTAL ──', 'ACCOUNT_NAME': '', 'THEATER_NAME': '',
                        'USE_CASE_STAGE': '', 'TECHNICAL_USE_CASE': '', 'ATTRIBUTION_FLAGS': '',
                        'USE_CASE_EACV': coco_display['USE_CASE_EACV'].sum()
                    }])
                    coco_display = pd.concat([coco_display, _total_row], ignore_index=True)
                    st.dataframe(coco_display, hide_index=True, use_container_width=True,
                                 column_config=uc_config,
                                 height=38 + 35 * len(coco_display))
            else:
                st.info("No CoCo-attached use cases.")

        with tab_noncoco:
            if len(non_coco_ucs) > 0:
                st.warning(f"These {len(non_coco_ucs)} use cases do NOT have CoCo attached. Adding CoCo to these would help reach the {target}% target.")
                noncoco_display = non_coco_ucs[uc_cols].copy()
                noncoco_display['USE_CASE_STAGE'] = noncoco_display['USE_CASE_STAGE'].str.extract(r'^(\d+)').iloc[:, 0]
                _nc_total = pd.DataFrame([{
                    'USE_CASE_NAME': '── TOTAL ──', 'ACCOUNT_NAME': '', 'THEATER_NAME': '',
                    'USE_CASE_STAGE': '', 'TECHNICAL_USE_CASE': '', 'ATTRIBUTION_FLAGS': '',
                    'USE_CASE_EACV': noncoco_display['USE_CASE_EACV'].sum()
                }])
                noncoco_display = pd.concat([noncoco_display, _nc_total], ignore_index=True)
                st.dataframe(noncoco_display, hide_index=True, use_container_width=True,
                             column_config=uc_config,
                             height=38 + 35 * len(noncoco_display))
            else:
                st.success("All use cases have CoCo attached!")

        with tab_confidence:
            confidence_data = get_usecase_confidence_scores(conn, selected_partner, q_start, q_end)
            if len(confidence_data) > 0:
                # Summary metrics (always show ALL bands regardless of sidebar filter)
                high = int((confidence_data['CONFIDENCE_BAND'] == 'High').sum())
                medium = int((confidence_data['CONFIDENCE_BAND'] == 'Medium').sum())
                low = int((confidence_data['CONFIDENCE_BAND'] == 'Low').sum())
                no_signal = int((confidence_data['CONFIDENCE_BAND'] == 'No Signal').sum())
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("High", high, help="Score 75-100")
                m2.metric("Medium", medium, help="Score 40-74")
                m3.metric("Low", low, help="Score 1-39")
                m4.metric("No Signal", no_signal, help="Score 0")

                _base_conf_cols = ['ACCOUNT_NAME', 'THEATER_NAME', 'TECHNICAL_USE_CASE', 'WORKLOAD_CATEGORY', 'RELEVANT_SKILL_INVOCATIONS', 'RELEVANT_CUSTOM_SKILLS', 'TOOLS_INVOKED', 'ACTIVE_DAYS', 'DISTINCT_USERS', 'TOTAL_SCORE', 'CONFIDENCE_BAND']
                conf_cols = (['USE_CASE_NAME'] if 'USE_CASE_NAME' in confidence_data.columns else []) + _base_conf_cols
                st.dataframe(
                    confidence_data[conf_cols],
                    column_config={
                        'USE_CASE_NAME': st.column_config.TextColumn("Use Case", width="large"),
                        'ACCOUNT_NAME': st.column_config.TextColumn("Account", width="medium"),
                        'THEATER_NAME': st.column_config.TextColumn("Theater", width="small"),
                        'TECHNICAL_USE_CASE': st.column_config.TextColumn("Technical Type", width="medium"),
                        'WORKLOAD_CATEGORY': st.column_config.TextColumn("Workload", width="small"),
                        'RELEVANT_SKILL_INVOCATIONS': st.column_config.NumberColumn("Bundled Skills", format="%d", help="Relevant bundled skill invocations for this workload"),
                        'RELEVANT_CUSTOM_SKILLS': st.column_config.NumberColumn("Custom Skills", format="%d", help="Workload-relevant custom skills (keyword matched)"),
                        'TOOLS_INVOKED': st.column_config.NumberColumn("Tools", format="%d", help="Total tool invocations"),
                        'ACTIVE_DAYS': st.column_config.NumberColumn("Active Days", format="%d"),
                        'DISTINCT_USERS': st.column_config.NumberColumn("Users", format="%d"),
                        'TOTAL_SCORE': st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                        'CONFIDENCE_BAND': st.column_config.TextColumn("Band"),
                    },
                    hide_index=True, use_container_width=True,
                    height=38 + 35 * len(confidence_data)
                )
                st.caption("Scoring: S1 Relevant Bundled Skills (30pts) + S2 Relevant Custom Skills (35pts) + S3 Tools (20pts) + S4 Skill Intensity per Day (15pts)")
            else:
                st.info("No confidence scoring data available.")


st.divider()

st.divider()
st.caption(f"OKR Target: {target}% of use cases in Stages 3-7 should have CoCo attached | {start_date} to {end_date} | Min UCs: {min_use_cases}")
st.caption("CoCo detection: SE Comments (coco/cortex code) OR Partner Comments (#coco) OR Feature Flag (AI - Cortex Code) OR CoCo Account Level Usage")

st.divider()
st.subheader("CoCo Detection Source Breakdown")
_conf_desc = 'High' if confidence_filter == ['High'] else 'High + Medium' if confidence_filter else 'All account-level'
if len(bulk_conf) > 0 and 'IS_COCO_FINAL' in bulk_conf.columns:
    _coco_bc = bulk_conf[bulk_conf['IS_COCO_FINAL']]
    _se_count      = int((_coco_bc.get('COCO_SOURCE', pd.Series()) == 'SE_COMMENTS').sum())
    _partner_count = int((_coco_bc.get('COCO_SOURCE', pd.Series()) == 'PARTNER_COMMENTS').sum())
    _ff_count      = int((_coco_bc.get('COCO_SOURCE', pd.Series()) == 'FEATURE_FLAG').sum())
    _acct_bands    = confidence_filter if confidence_filter else ['High', 'Medium', 'Low']
    _acct_count    = int(bulk_conf['CONFIDENCE_BAND'].isin(_acct_bands).sum()) if 'CONFIDENCE_BAND' in bulk_conf.columns else 0
    _src_c1, _src_c2 = st.columns(2)
    with _src_c1:
        st.metric(":material/chat: SE Comments",          _se_count)
        st.metric(":material/handshake: Partner Comments", _partner_count)
    with _src_c2:
        st.metric(":material/flag: Feature Flag",          _ff_count)
        st.metric(f":material/cloud: Account-Level ({_conf_desc})", _acct_count)
else:
    st.info("Detection source data not available.")

# --- 4-Week Per-Partner Heatmap: IS_COCO_FINAL Credits & Tokens ---
st.divider()
st.subheader("CoCo Consumption Trend — Last 4 Weeks (IS_COCO_FINAL)")

# Build IS_COCO_FINAL account list from bulk_conf (avoids re-running scoring)
_hm_pairs = tuple()
if len(bulk_conf) > 0 and 'IS_COCO_FINAL' in bulk_conf.columns and 'ACCOUNT_NAME_UPPER' in bulk_conf.columns:
    _hm_coco_final = (
        bulk_conf[bulk_conf['IS_COCO_FINAL']]
        .pipe(filter_out_partner_own_accounts)
        .drop_duplicates(subset=['PARTNER_NAME', 'ACCOUNT_NAME_UPPER'])
        [['PARTNER_NAME', 'ACCOUNT_NAME_UPPER']]
    )
    # Respect sidebar partner filter
    if len(filtered) > 0:
        _hm_coco_final = _hm_coco_final[_hm_coco_final['PARTNER_NAME'].isin(filtered['PARTNER_NAME'])]
    _hm_pairs = tuple(zip(_hm_coco_final['PARTNER_NAME'], _hm_coco_final['ACCOUNT_NAME_UPPER']))

if len(_hm_pairs) > 0:
    try:
        # --- Build Last7 + Prior7 directly from bulk_conf (same cache as Deep Dive header)
        # This guarantees heatmap Last7/Prior7 = Deep Dive header EXACTLY
        import datetime as _dt
        _today = _dt.date.today()
        _l7_label  = f"{(_today - _dt.timedelta(days=7)).strftime('%m/%d')}-{(_today - _dt.timedelta(days=1)).strftime('%m/%d')}"
        _p7_label  = f"{(_today - _dt.timedelta(days=14)).strftime('%m/%d')}-{(_today - _dt.timedelta(days=8)).strftime('%m/%d')}"

        _hm_bulk = (
            bulk_conf[bulk_conf['IS_COCO_FINAL']]
            .pipe(filter_out_partner_own_accounts)
            .drop_duplicates(subset=['PARTNER_NAME', 'ACCOUNT_NAME_UPPER'])
            .copy()
        )
        if len(filtered) > 0:
            _hm_bulk = _hm_bulk[_hm_bulk['PARTNER_NAME'].isin(filtered['PARTNER_NAME'])]

        for _c in ['LAST7_CREDITS','PRIOR7_CREDITS','LAST7_TOKENS','PRIOR7_TOKENS']:
            if _c in _hm_bulk.columns:
                _hm_bulk[_c] = pd.to_numeric(_hm_bulk[_c], errors='coerce').fillna(0.0)

        _last7_cred  = _hm_bulk.groupby('PARTNER_NAME')['LAST7_CREDITS'].sum().reset_index().rename(columns={'LAST7_CREDITS':  _l7_label})
        _prior7_cred = _hm_bulk.groupby('PARTNER_NAME')['PRIOR7_CREDITS'].sum().reset_index().rename(columns={'PRIOR7_CREDITS': _p7_label})
        _last7_tok   = _hm_bulk.groupby('PARTNER_NAME')['LAST7_TOKENS'].sum().reset_index().rename(columns={'LAST7_TOKENS':   _l7_label})
        _prior7_tok  = _hm_bulk.groupby('PARTNER_NAME')['PRIOR7_TOKENS'].sum().reset_index().rename(columns={'PRIOR7_TOKENS':  _p7_label})

        # --- Older periods (14-28d) from Snowflake query — separate TTL is fine since these don't appear in Deep Dive
        _hm_older = get_partner_surface_trend_4w(conn, _hm_pairs)
        _hm_older_cred = pd.DataFrame({'PARTNER_NAME': pd.Series(dtype=str)})
        _hm_older_tok  = pd.DataFrame({'PARTNER_NAME': pd.Series(dtype=str)})
        _older_labels  = []

        if len(_hm_older) > 0:
            for _c in ['WEEKLY_CREDITS', 'WEEKLY_TOKENS']:
                if _c in _hm_older.columns:
                    _hm_older[_c] = pd.to_numeric(_hm_older[_c], errors='coerce').fillna(0.0)
            # Only keep periods 3 and 4 (older than prior7); skip 1 and 2 (already from bulk_conf)
            _hm_old_only = _hm_older[_hm_older['PERIOD_ORDER'].isin([3, 4])].copy()
            if len(_hm_old_only) > 0:
                _older_labels = (
                    _hm_old_only[['PERIOD_ORDER','PERIOD_LABEL']]
                    .drop_duplicates()
                    .sort_values('PERIOD_ORDER', ascending=False)['PERIOD_LABEL']
                    .tolist()
                )
                _hm_older_cred = _hm_old_only.pivot_table(
                    index='PARTNER_NAME', columns='PERIOD_LABEL',
                    values='WEEKLY_CREDITS', aggfunc='sum', fill_value=0
                ).reset_index()
                _hm_older_tok = _hm_old_only.pivot_table(
                    index='PARTNER_NAME', columns='PERIOD_LABEL',
                    values='WEEKLY_TOKENS', aggfunc='sum', fill_value=0
                ).reset_index()

        # --- Merge all periods into final pivot tables
        _all_partners = sorted(_hm_bulk['PARTNER_NAME'].unique())
        _pbase = pd.DataFrame({'PARTNER_NAME': _all_partners})

        # Column order: oldest left → newest right
        _weeks = _older_labels + [_p7_label, _l7_label]

        def _build_pivot(base_df, older_df, last7_df, prior7_df, older_labels, l7_lbl, p7_lbl):
            df = base_df.copy()
            for lbl in older_labels:
                if len(older_df) > 0 and lbl in older_df.columns:
                    df = df.merge(older_df[['PARTNER_NAME', lbl]], on='PARTNER_NAME', how='left')
                else:
                    df[lbl] = 0.0
            df = df.merge(prior7_df, on='PARTNER_NAME', how='left')
            df = df.merge(last7_df,  on='PARTNER_NAME', how='left')
            df = df.set_index('PARTNER_NAME').fillna(0.0)
            return df[[c for c in (_older_labels + [p7_lbl, l7_lbl]) if c in df.columns]]

        _cred_pivot = _build_pivot(_pbase, _hm_older_cred, _last7_cred, _prior7_cred, _older_labels, _l7_label, _p7_label)
        _tok_pivot  = _build_pivot(_pbase, _hm_older_tok,  _last7_tok,  _prior7_tok,  _older_labels, _l7_label, _p7_label)

        # Sort partners by Last7 credits desc
        _partner_order = _cred_pivot[_l7_label].sort_values(ascending=False).index.tolist() if _l7_label in _cred_pivot.columns else _cred_pivot.sum(axis=1).sort_values(ascending=False).index.tolist()
        _cred_pivot = _cred_pivot.reindex(_partner_order)
        _tok_pivot  = _tok_pivot.reindex(_partner_order)

        if len(_cred_pivot) > 0:

            _n_accts   = len(_hm_pairs)
            _n_partners = len(_partner_order)

            # Build hover text with WoW delta per cell
            def _cred_hover(row_vals, cols):
                texts = []
                for i, col in enumerate(cols):
                    val = float(row_vals[i]) if row_vals[i] == row_vals[i] else 0.0
                    wow_str = ""
                    if i > 0:
                        prev = float(row_vals[i-1]) if row_vals[i-1] == row_vals[i-1] else 0.0
                        if prev > 0:
                            wow_str = f"  WoW: {(val-prev)/prev*100:+.1f}%"
                    texts.append(f"${val:,.0f}{wow_str}")
                return texts

            def _tok_hover(row_vals, cols):
                texts = []
                for i, col in enumerate(cols):
                    val = float(row_vals[i]) if row_vals[i] == row_vals[i] else 0.0
                    wow_str = ""
                    if i > 0:
                        prev = float(row_vals[i-1]) if row_vals[i-1] == row_vals[i-1] else 0.0
                        if prev > 0:
                            wow_str = f"  WoW: {(val-prev)/prev*100:+.1f}%"
                    texts.append(f"{val/1e9:.2f}B{wow_str}")
                return texts

            _cred_text = [_cred_hover(_cred_pivot.iloc[i].tolist(), _weeks) for i in range(len(_cred_pivot))]
            _tok_text  = [_tok_hover(_tok_pivot.iloc[i].tolist(),  _weeks) for i in range(len(_tok_pivot))]

            _col_hm1, _col_hm2 = st.columns(2)

            with _col_hm1:
                st.markdown("**Credits ($)**")
                _fig_hm_c = go.Figure(go.Heatmap(
                    z=_cred_pivot.values.tolist(),
                    x=_weeks,
                    y=_cred_pivot.index.tolist(),
                    text=_cred_text,
                    texttemplate="%{text}",
                    textfont=dict(size=10),
                    colorscale='Blues',
                    showscale=True,
                    colorbar=dict(title='Credits $', x=1.02, len=0.9),
                    hovertemplate='<b>%{y}</b><br>%{x}<br>%{text}<extra></extra>',
                ))
                _fig_hm_c.update_layout(
                    height=max(280, 36 * len(_partner_order) + 60),
                    margin=dict(t=10, b=10, l=10, r=60),
                    xaxis=dict(side='top'),
                    yaxis=dict(autorange='reversed'),
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                )
                st.plotly_chart(_fig_hm_c, use_container_width=True)

            with _col_hm2:
                st.markdown("**Tokens (B)**")
                _tok_display = [[v / 1e9 for v in row] for row in _tok_pivot.values.tolist()]
                _fig_hm_t = go.Figure(go.Heatmap(
                    z=_tok_display,
                    x=_weeks,
                    y=_tok_pivot.index.tolist(),
                    text=_tok_text,
                    texttemplate="%{text}",
                    textfont=dict(size=10),
                    colorscale='Greens',
                    showscale=True,
                    colorbar=dict(title='Tokens B', x=1.02, len=0.9),
                    hovertemplate='<b>%{y}</b><br>%{x}<br>%{text}<extra></extra>',
                ))
                _fig_hm_t.update_layout(
                    height=max(280, 36 * len(_partner_order) + 60),
                    margin=dict(t=10, b=10, l=10, r=60),
                    xaxis=dict(side='top'),
                    yaxis=dict(autorange='reversed'),
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                )
                st.plotly_chart(_fig_hm_t, use_container_width=True)

            st.caption(
                f"IS_COCO_FINAL accounts ({_n_accts} accounts across {_n_partners} partners) | "
                f"Rolling 7-day windows | Rightmost = Last 7d — same value as Deep Dive header tooltip | "
                f"Darker = higher | Hover for WoW Δ"
            )
        else:
            st.info("No consumption data found for IS_COCO_FINAL accounts in the last 4 weeks.")
    except Exception as _e:
        st.info(f"Trend chart unavailable: {_e}")
else:
    st.info("Enable 'Account Level CoCo' and select partners to see IS_COCO_FINAL consumption trend.")
