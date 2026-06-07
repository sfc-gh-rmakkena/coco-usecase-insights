import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import urllib.parse
import markdown
from datetime import datetime
from utils.queries import (
    get_summary_stats, get_by_partner, get_by_stage, get_source_breakdown,
    get_by_region, get_email_summary_data, get_use_case_type_patterns,
    get_workload_patterns, get_competitive_landscape, get_comment_narratives,
    get_partner_workload_cross, get_regional_themes, get_regional_comment_narratives,
    get_partner_coco_coverage, get_partner_credit_consumption, get_adoption_overview,
    get_bulk_confidence_scores, get_pipeline_wow, get_gsi_wow, get_noam_si_wow,
    get_coco_adoption_wow,
)
from utils.cortex_helpers import cortex_complete

MANAGED_PARTNERS = [
    # Global SIs
    'Accenture', 'Capgemini Technologies LLC',
    'Cognizant Technology Solutions US Corp', 'Deloitte Consulting', 'EY', 'Ernst & Young (EY)',
    'IBM',
    # Regional Managed Partners
    '7Rivers, Inc', 'Aimpoint Digital', 'BlueCloud Services Inc', 'kipi.ai',
    'evolv Consulting', 'Infostrux Solutions Inc.', 'Infosys', 'KPMG LLP',
    'LTIMindtree', 'NTT DATA Group Corporation', 'phData, Inc.',
    'Slalom, LLC.', 'Squadron Data Inc', 'Tredence Inc.'
]


def name_to_email(name):
    name = name.strip()
    if '@' in name:
        return name
    parts = name.lower().split()
    if len(parts) >= 2:
        return f"{'.'.join(parts)}@snowflake.com"
    elif len(parts) == 1:
        return f"{parts[0]}@snowflake.com"
    return name


def md_to_html(md_text):
    html_body = markdown.markdown(md_text, extensions=['tables'])
    return f"""<html><head><style>
    body {{ font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
    th {{ background-color: #29B5E8; color: white; font-weight: bold; }}
    tr:nth-child(even) {{ background-color: #f9f9f9; }}
    h2 {{ color: #29B5E8; margin-top: 20px; border-bottom: 2px solid #29B5E8; padding-bottom: 4px; }}
    h3 {{ color: #29B5E8; }}
    strong {{ color: #333; }}
    ul {{ padding-left: 20px; }}
    li {{ margin-bottom: 4px; }}
</style></head><body>{html_body}</body></html>"""


conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])

st.title(":material/mail: Executive Email Summary")
filter_label = f"Region: {region}"
if selected_partners:
    filter_label += f" | Partners: {', '.join(selected_partners)}"
st.caption(f"AI-generated weekly summary for CoCo Use Case Intelligence | {filter_label}")

source_toggle = st.segmented_control("Use Case View", ["Overall", "PSE Confirmed", "Feature Flag"], default="Overall", key="email_source")
st.caption(f"Filters active: {source_toggle} use cases • {region} region")

def _apply_partner_filter(df, col='PARTNER_NAME'):
    """Filter DataFrame by sidebar multiselect partners."""
    if selected_partners and col in df.columns:
        from utils import resolve_partner_filter
        names = resolve_partner_filter(selected_partners)
        return df[df[col].isin(names)]
    return df

with st.spinner("Loading data..."):
    stats = get_summary_stats(conn, region=region, source=source_toggle)
    partner_data = get_email_summary_data(conn, region=region, source=source_toggle)
    stage_data = get_by_stage(conn, region=region, source=source_toggle)
    source_data = get_source_breakdown(conn, region=region)
    region_data = get_by_region(conn, source=source_toggle)
    type_patterns = get_use_case_type_patterns(conn, region=region, source=source_toggle)
    workload_data = get_workload_patterns(conn, region=region, source=source_toggle)
    competitive_data = get_competitive_landscape(conn, region=region, source=source_toggle)
    comment_data = get_comment_narratives(conn, region=region, source=source_toggle)
    partner_workloads = get_partner_workload_cross(conn, region=region, source=source_toggle)
    regional_themes = get_regional_themes(conn, source=source_toggle)
    coco_coverage = get_partner_coco_coverage(conn, region=region, include_account_coco=False, confidence=None)
    global_overview = get_adoption_overview(conn, '2026-05-01', '2026-07-31', include_account_coco=True, confidence='High')
    pipeline_wow = get_pipeline_wow(conn)
    gsi_wow = get_gsi_wow(conn)
    noam_si_wow = get_noam_si_wow(conn)
    adoption_wow_data = get_coco_adoption_wow(conn, partners=MANAGED_PARTNERS)

    # Managed partner stage EACV breakdown — Q2 ONLY (May 1 - Jul 31, 2026)
    managed_partners_sql = "','".join(MANAGED_PARTNERS)
    Q2_START = '2026-05-01'
    Q2_END = '2026-07-31'

    # Q2 Credit consumption for managed partners
    credit_data = get_partner_credit_consumption(conn, MANAGED_PARTNERS, Q2_START, Q2_END)

    managed_stage_data = conn.query(f"""
        SELECT 
            CASE 
                WHEN USE_CASE_STAGE IN ('3 - Technical / Business Validation') THEN 'Validation (3)'
                WHEN USE_CASE_STAGE = '4 - Use Case Won / Migration Plan' THEN 'Won (4)'
                WHEN USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete') THEN 'Implementation (5-6)'
                WHEN USE_CASE_STAGE = '7 - Deployed' THEN 'Deployed (7)'
            END AS STAGE_GROUP,
            COUNT(*) AS UC_COUNT,
            COALESCE(SUM(USE_CASE_EACV), 0) AS TOTAL_EACV
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
        WHERE uc.PARTNER_NAME IN ('{managed_partners_sql}')
        AND uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan','5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{Q2_START}' AND uc.DECISION_DATE <= '{Q2_END}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{Q2_START}' AND uc.GO_LIVE_DATE <= '{Q2_END}')
        )
        GROUP BY STAGE_GROUP
        ORDER BY STAGE_GROUP
    """)

    # Fetch per-use-case confidence scores for all managed partners (High confidence = score >= 75)
    # Executive email always uses: account-level CoCo ON, High confidence only
    _EMAIL_BANDS = ['High']
    managed_bulk_conf = get_bulk_confidence_scores(conn, MANAGED_PARTNERS, Q2_START, Q2_END)

    if len(managed_bulk_conf) > 0:
        managed_bulk_conf['IS_COCO_FINAL'] = (
            (managed_bulk_conf['IS_COCO'] == True) |
            (managed_bulk_conf['CONFIDENCE_BAND'].isin(_EMAIL_BANDS))
        )
        managed_bulk_conf['REGION'] = managed_bulk_conf['THEATER_NAME'].map(
            lambda t: 'NoAM' if t in ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec')
                      else 'EMEA' if t == 'EMEA' else 'APJ' if t == 'APJ' else 'Other'
        )
        coco_mask = managed_bulk_conf['IS_COCO_FINAL']

        # Q2 headline stats
        managed_q2_stats = pd.DataFrame([{
            'TOTAL_UCS': len(managed_bulk_conf),
            'COCO_UCS': int(coco_mask.sum()),
            'TOTAL_EACV': managed_bulk_conf['USE_CASE_EACV'].sum() or 0,
            'COCO_EACV': managed_bulk_conf.loc[coco_mask, 'USE_CASE_EACV'].sum() or 0,
            'ACTIVE_PARTNERS': managed_bulk_conf['PARTNER_NAME'].nunique(),
            'COCO_DEPLOYED': int(managed_bulk_conf[
                coco_mask & (managed_bulk_conf['USE_CASE_STAGE'] == '7 - Deployed')
            ].shape[0]),
        }])

        # Q2 CoCo coverage by region
        reg_agg = managed_bulk_conf.groupby('REGION').agg(
            TOTAL_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            PARTNER_COUNT=('PARTNER_NAME', 'nunique'),
        ).reset_index()
        reg_agg['COCO_PCT'] = round(
            reg_agg['COCO_UCS'] * 100.0 / reg_agg['TOTAL_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        managed_q2_regional = reg_agg.sort_values('TOTAL_UCS', ascending=False)

        # Avg CoCo% per partner per region
        pstats = managed_bulk_conf.groupby(['REGION', 'PARTNER_NAME']).agg(
            TOTAL_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
        ).reset_index()
        pstats['COCO_PCT'] = round(
            pstats['COCO_UCS'] * 100.0 / pstats['TOTAL_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        managed_q2_partner_avg = pstats.groupby('REGION').agg(
            AVG_COCO_PCT_PER_PARTNER=('COCO_PCT', 'mean')
        ).reset_index()
        managed_q2_partner_avg['AVG_COCO_PCT_PER_PARTNER'] = managed_q2_partner_avg['AVG_COCO_PCT_PER_PARTNER'].round(1)

        # Per-partner breakdown
        p_coco_eacv = managed_bulk_conf.loc[coco_mask].groupby('PARTNER_NAME')['USE_CASE_EACV'].sum().reset_index()
        p_coco_eacv.columns = ['PARTNER_NAME', 'COCO_EACV']
        managed_q2_partners = managed_bulk_conf.groupby('PARTNER_NAME').agg(
            TOTAL_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
            AI=('TECHNICAL_USE_CASE', lambda x: x.str.contains('AI', case=False, na=False).sum()),
            DE=('TECHNICAL_USE_CASE', lambda x: x.str.contains('DE:', case=False, na=False).sum()),
            ANALYTICS=('TECHNICAL_USE_CASE', lambda x: x.str.contains('Analytics', case=False, na=False).sum()),
        ).reset_index()
        managed_q2_partners = managed_q2_partners.merge(p_coco_eacv, on='PARTNER_NAME', how='left')
        managed_q2_partners['COCO_EACV'] = managed_q2_partners['COCO_EACV'].fillna(0)
        managed_q2_partners['COCO_PCT'] = round(
            managed_q2_partners['COCO_UCS'] * 100.0 / managed_q2_partners['TOTAL_UCS'].replace(0, float('nan')), 0
        ).fillna(0)
        managed_q2_partners = managed_q2_partners.sort_values('TOTAL_EACV', ascending=False)
    else:
        managed_q2_stats = pd.DataFrame([{'TOTAL_UCS': 0, 'COCO_UCS': 0, 'TOTAL_EACV': 0, 'COCO_EACV': 0, 'ACTIVE_PARTNERS': 0, 'COCO_DEPLOYED': 0}])
        managed_q2_regional = pd.DataFrame(columns=['REGION', 'TOTAL_UCS', 'COCO_UCS', 'COCO_PCT', 'PARTNER_COUNT'])
        managed_q2_partner_avg = pd.DataFrame(columns=['REGION', 'AVG_COCO_PCT_PER_PARTNER'])
        managed_q2_partners = pd.DataFrame(columns=['PARTNER_NAME', 'TOTAL_UCS', 'COCO_UCS', 'COCO_PCT', 'TOTAL_EACV', 'AI', 'DE', 'ANALYTICS'])

# Executive email always uses MANAGED_PARTNERS list, ignoring sidebar partner filter
# Filter to managed partners only for executive email context
partner_data = partner_data[partner_data['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
comment_data = comment_data[comment_data['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
partner_workloads = partner_workloads[partner_workloads['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
coco_coverage = coco_coverage[coco_coverage['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
if 'PARTNER_NAME' in regional_themes.columns:
    regional_themes = regional_themes[regional_themes['PARTNER_NAME'].isin(MANAGED_PARTNERS)]

# Override coco_coverage with High-confidence scoring (same logic as OKR Coverage)
if len(coco_coverage) > 0 and len(managed_bulk_conf) > 0:
    bulk_for_cov = managed_bulk_conf[managed_bulk_conf['PARTNER_NAME'].isin(coco_coverage['PARTNER_NAME'])].copy()
    if region and region != 'Global':
        region_theaters = {'NoAM': ['AMSExpansion', 'USMajors', 'AMSAcquisition'], 'EMEA': ['EMEA'], 'APJ': ['APJ']}
        bulk_for_cov = bulk_for_cov[bulk_for_cov['THEATER_NAME'].isin(region_theaters.get(region, []))]
    if len(bulk_for_cov) > 0:
        cov_coco_eacv = bulk_for_cov[bulk_for_cov['IS_COCO_FINAL']].groupby('PARTNER_NAME')['USE_CASE_EACV'].sum().reset_index()
        cov_coco_eacv.columns = ['PARTNER_NAME', 'COCO_EACV']
        cov_summary = bulk_for_cov.groupby('PARTNER_NAME').agg(
            TOTAL_PARTNER_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
        ).reset_index()
        cov_summary = cov_summary.merge(cov_coco_eacv, on='PARTNER_NAME', how='left')
        cov_summary['COCO_EACV'] = cov_summary['COCO_EACV'].fillna(0)
        cov_summary['COCO_PCT'] = round(
            cov_summary['COCO_UCS'] * 100.0 / cov_summary['TOTAL_PARTNER_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        coco_coverage = coco_coverage[['PARTNER_NAME']].merge(cov_summary, on='PARTNER_NAME', how='left').fillna(0)
        coco_coverage['COCO_PCT'] = coco_coverage['COCO_PCT'].astype(float)
        coco_coverage[['TOTAL_PARTNER_UCS', 'COCO_UCS']] = coco_coverage[['TOTAL_PARTNER_UCS', 'COCO_UCS']].astype(int)

if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

# Recompute headline stats from Q2 managed partner data
q2 = managed_q2_stats.iloc[0]
managed_total_ucs = int(q2['TOTAL_UCS'])
managed_coco_ucs = int(q2['COCO_UCS'])
managed_total_eacv = q2['TOTAL_EACV'] or 0
managed_coco_eacv = q2['COCO_EACV'] or 0
managed_total_partners = int(q2['ACTIVE_PARTNERS'])
managed_coco_deployed = int(q2['COCO_DEPLOYED'])
managed_coco_pct = round(managed_coco_ucs * 100.0 / managed_total_ucs, 1) if managed_total_ucs > 0 else 0
managed_inactive_partners = 35 - managed_total_partners
managed_inactive_names = [p for p in MANAGED_PARTNERS if p not in partner_data['PARTNER_NAME'].values]

# Compute full per-partner OKR summary (all managed partners, not capped at 15)
# Used to accurately report partners meeting/below the 50% target
if len(managed_bulk_conf) > 0:
    _full_partner_summary = managed_bulk_conf.groupby('PARTNER_NAME').agg(
        TOTAL_UCS=('USE_CASE_ID', 'count'),
        COCO_UCS=('IS_COCO_FINAL', 'sum'),
    ).reset_index()
    _full_partner_summary['COCO_PCT'] = round(
        _full_partner_summary['COCO_UCS'] * 100.0 / _full_partner_summary['TOTAL_UCS'].replace(0, float('nan')), 1
    ).fillna(0)
    partners_meeting_50 = int((_full_partner_summary['COCO_PCT'] >= 50).sum())
    partners_meeting_list = ', '.join(_full_partner_summary[_full_partner_summary['COCO_PCT'] >= 50]['PARTNER_NAME'].tolist())
    partners_below_50 = int((_full_partner_summary['COCO_PCT'] < 50).sum())
else:
    partners_meeting_50 = 0
    partners_meeting_list = 'N/A'
    partners_below_50 = managed_total_partners

s = stats.iloc[0]
go = global_overview.iloc[0]

st.subheader("Data Summary")
with st.expander("View Raw Metrics", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Use Cases", int(s['TOTAL_USE_CASES']))
    c2.metric("Total EACV", f"${s['TOTAL_EACV']/1_000_000:.1f}M" if s['TOTAL_EACV'] else "$0")
    c3.metric("Partners", int(s['TOTAL_PARTNERS']))
    c4.metric("Accounts", int(s['TOTAL_ACCOUNTS']))

    tab1, tab2, tab3, tab4 = st.tabs(["Pipeline", "Use Case Types", "Workloads", "Competitors"])
    with tab1:
        if len(stage_data) > 0:
            st.dataframe(stage_data, hide_index=True, use_container_width=True)
    with tab2:
        if len(type_patterns) > 0:
            st.dataframe(type_patterns[['TECHNICAL_USE_CASE', 'USE_CASE_COUNT', 'TOTAL_EACV', 'PARTNER_COUNT', 'WON_PLUS']], hide_index=True, use_container_width=True)
    with tab3:
        if len(workload_data) > 0:
            st.dataframe(workload_data, hide_index=True, use_container_width=True)
    with tab4:
        if len(competitive_data) > 0:
            st.dataframe(competitive_data, hide_index=True, use_container_width=True)

coverage_map = {}
if len(coco_coverage) > 0:
    for _, cv in coco_coverage.iterrows():
        coverage_map[cv['PARTNER_NAME']] = {
            'total': int(cv['TOTAL_PARTNER_UCS']),
            'coco': int(cv['COCO_UCS']),
            'pct': float(cv['COCO_PCT'] or 0)
        }

partner_ctx = ""
for _, p in managed_q2_partners.iterrows():
    eacv = p.get('TOTAL_EACV', 0) or 0
    partner_ctx += f"  {p['PARTNER_NAME']}: {int(p['TOTAL_UCS'])} UCs, {int(p['COCO_UCS'])} CoCo ({int(p['COCO_PCT'])}%), ${eacv/1000:.0f}K, AI={int(p['AI'])}, DE={int(p['DE'])}, Analytics={int(p['ANALYTICS'])}\n"

stage_ctx = ""
for _, sg in managed_stage_data.iterrows():
    eacv = sg.get('TOTAL_EACV', 0) or 0
    stage_ctx += f"  {sg['STAGE_GROUP']}: {int(sg['UC_COUNT'])} UCs, ${eacv/1_000_000:.1f}M\n"

region_ctx = ""
for _, rg in region_data.iterrows():
    eacv = rg.get('TOTAL_EACV', 0) or 0
    region_ctx += f"  {rg['REGION']}: {int(rg['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K EACV, {int(rg['PARTNER_COUNT'])} partners\n"

type_ctx = ""
for _, tp in type_patterns.head(10).iterrows():
    eacv = tp.get('TOTAL_EACV', 0) or 0
    type_ctx += f"  {tp['TECHNICAL_USE_CASE']}: {int(tp['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K, {int(tp['PARTNER_COUNT'])} partners, {int(tp['WON_PLUS'])} won+\n"

workload_ctx = ""
for _, wl in workload_data.iterrows():
    eacv = wl.get('TOTAL_EACV', 0) or 0
    workload_ctx += f"  {wl['WORKLOADS']}: {int(wl['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K, {int(wl['PARTNER_COUNT'])} partners\n"

competitive_ctx = ""
for _, comp in competitive_data.head(8).iterrows():
    eacv = comp.get('TOTAL_EACV', 0) or 0
    competitive_ctx += f"  {comp['COMPETITORS']}: {int(comp['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K\n"

partner_wl_ctx = ""
for _, pw in partner_workloads.head(12).iterrows():
    eacv = pw.get('TOTAL_EACV', 0) or 0
    cv = coverage_map.get(pw['PARTNER_NAME'], {})
    total_ucs = cv.get('total', '?')
    coco_pct = cv.get('pct', 0)
    partner_wl_ctx += f"  {pw['PARTNER_NAME']}: CoCo={int(pw['TOTAL_USE_CASES'])}/{total_ucs} ({coco_pct:.0f}%), ${eacv/1000:.0f}K | AI={int(pw['AI_USE_CASES'])}, DE={int(pw['DE_USE_CASES'])}, Analytics={int(pw['ANALYTICS_USE_CASES'])}, Platform={int(pw['PLATFORM_USE_CASES'])}, Apps={int(pw['APPS_USE_CASES'])}\n"

comment_ctx = ""
for _, cm in comment_data.head(10).iterrows():
    eacv = cm.get('USE_CASE_EACV', 0) or 0
    se_snip = str(cm.get('SE_COMMENTS_EXCERPT', '') or '')[:200].replace('\n', ' ')
    partner_snip = str(cm.get('PARTNER_COMMENTS_EXCERPT', '') or '')[:200].replace('\n', ' ')
    entry = f"  [{cm['PARTNER_NAME']} | {cm['ACCOUNT_NAME']} | ${eacv/1000:.0f}K | {cm.get('TECHNICAL_USE_CASE', 'N/A')}]"
    if se_snip:
        entry += f" SE: {se_snip}"
    if partner_snip:
        entry += f" PARTNER: {partner_snip}"
    comment_ctx += entry + "\n"


def _build_region_theme_ctx(df, region_name):
    region_df = df[df['REGION'] == region_name]
    if len(region_df) == 0:
        return f"  No data for {region_name}\n"
    total_ucs = int(region_df['USE_CASE_COUNT'].sum())
    total_eacv = region_df['TOTAL_EACV'].sum() or 0
    ctx = f"  {total_ucs} UCs, ${total_eacv/1_000_000:.1f}M EACV\n"
    type_agg = region_df.groupby('TECHNICAL_USE_CASE').agg({'USE_CASE_COUNT': 'sum', 'TOTAL_EACV': 'sum'}).reset_index().sort_values('TOTAL_EACV', ascending=False).head(5)
    for _, row in type_agg.iterrows():
        if row['TECHNICAL_USE_CASE']:
            ctx += f"    {row['TECHNICAL_USE_CASE']}: {int(row['USE_CASE_COUNT'])} UCs, ${(row.get('TOTAL_EACV', 0) or 0)/1000:.0f}K\n"
    comp_agg = region_df[region_df['COMPETITORS'].notna()].groupby('COMPETITORS').agg({'USE_CASE_COUNT': 'sum'}).reset_index().sort_values('USE_CASE_COUNT', ascending=False).head(3)
    comps = ", ".join([f"{r['COMPETITORS']}({int(r['USE_CASE_COUNT'])})" for _, r in comp_agg.iterrows()])
    if comps:
        ctx += f"    Competitors: {comps}\n"
    return ctx

# Build Q2 regional CoCo coverage context
partner_avg_map = {}
if len(managed_q2_partner_avg) > 0:
    for _, row in managed_q2_partner_avg.iterrows():
        partner_avg_map[row['REGION']] = row['AVG_COCO_PCT_PER_PARTNER']

regional_coco_ctx = ""
for _, rg in managed_q2_regional.iterrows():
    avg_pct = partner_avg_map.get(rg['REGION'], 0)
    regional_coco_ctx += f"  {rg['REGION']}: {int(rg['TOTAL_UCS'])} total UCs, {int(rg['COCO_UCS'])} CoCo, {rg['COCO_PCT']}% overall, {int(rg['PARTNER_COUNT'])} partners, {avg_pct}% avg/partner\n"

# Build credit consumption context
credit_ctx = ""
if len(credit_data) > 0:
    for _, cr in credit_data.head(12).iterrows():
        wow = f"{cr['WOW_PCT']:+.1f}%" if pd.notna(cr['WOW_PCT']) else "N/A"
        credit_ctx += f"  {cr['PARTNER_NAME']}: Q2 Total=${cr['Q2_TOTAL_CREDITS']:,.0f}, Accounts={int(cr['COCO_CUSTOMER_ACCOUNTS'])}, Active Days={int(cr['ACTIVE_DAYS'])}, WoW={wow}\n"

# CoCo adoption WoW context (from OKR_PARTNER_WEEKLY_ADOPTION)
adoption_wow_ctx = ""
adoption_wow_partner_ctx = ""
if len(adoption_wow_data) > 0:
    overall_row = adoption_wow_data[adoption_wow_data['PARTNER_NAME'].isna()]
    partner_rows = adoption_wow_data[adoption_wow_data['PARTNER_NAME'].notna()].sort_values('COCO_PCT', ascending=False)
    if len(overall_row) > 0:
        ow = overall_row.iloc[0]
        wow_pct = f"{float(ow['WOW_COCO_PCT']):+.1f}%" if pd.notna(ow.get('WOW_COCO_PCT')) else "N/A (first week)"
        wow_ucs = f"{int(ow['WOW_COCO_UCS']):+d}" if pd.notna(ow.get('WOW_COCO_UCS')) else "N/A"
        adoption_wow_ctx = (
            f"  Week of {ow['WEEK_START']}:\n"
            f"  Overall CoCo Adoption %: {ow['COCO_PCT']}% (WoW: {wow_pct})\n"
            f"  Overall CoCo UCs: {int(ow['COCO_UCS'])} (WoW: {wow_ucs})\n"
        )
    for _, pr in partner_rows.iterrows():
        if pr['PARTNER_NAME'] not in MANAGED_PARTNERS:
            continue
        wow_pct = f"{float(pr['WOW_COCO_PCT']):+.1f}%" if pd.notna(pr.get('WOW_COCO_PCT')) else "N/A"
        wow_ucs = f"{int(pr['WOW_COCO_UCS']):+d}" if pd.notna(pr.get('WOW_COCO_UCS')) else "N/A"
        adoption_wow_partner_ctx += f"  {pr['PARTNER_NAME']}: {pr['COCO_PCT']}% CoCo ({int(pr['COCO_UCS'])}/{int(pr['TOTAL_UCS'])} UCs), WoW Δ={wow_pct}, Δ UCs={wow_ucs}\n"
else:
    adoption_wow_ctx = "  No adoption WoW data yet (first snapshot seeded, next available after Sunday task run).\n"
    adoption_wow_partner_ctx = adoption_wow_ctx

# Pipeline WoW context (use case count change vs prior week)
def _fmt_wow(val):
    return f"+{int(val)}" if val > 0 else str(int(val))

pipeline_wow_ctx = ""
if len(pipeline_wow) > 0:
    pw = pipeline_wow.iloc[0]
    wow_eacv = pw['WOW_EACV']
    eacv_sign = "+" if wow_eacv >= 0 else ""
    pipeline_wow_ctx = (
        f"  Week of {pw['WEEK_START']} vs {pw['PREV_WEEK_START']} (all CoCo partners, proxy for managed):\n"
        f"  CoCo Use Cases:  {int(pw['TOTAL_UCS'])} ({_fmt_wow(pw['WOW_TOTAL'])} WoW)\n"
        f"  CoCo EACV:       ${pw['TOTAL_EACV']/1_000_000:.1f}M ({eacv_sign}${wow_eacv/1_000_000:.1f}M WoW)\n"
        f"  Deployed (7):    {int(pw['DEPLOYED'])} ({_fmt_wow(pw['WOW_DEPLOYED'])} WoW)\n"
        f"  In Impl (5-6):   {int(pw['IN_IMPL'])} ({_fmt_wow(pw['WOW_IN_IMPL'])} WoW)\n"
        f"  Won (4):         {int(pw['WON'])} ({_fmt_wow(pw['WOW_WON'])} WoW)\n"
        f"  Active (3):      {int(pw['ACTIVE_PIPELINE'])} ({_fmt_wow(pw['WOW_ACTIVE'])} WoW)\n"
    )
else:
    pipeline_wow_ctx = "  No WoW data available.\n"

# GSI WoW context (engagement — CoCo requests, all regions)
gsi_wow_ctx = ""
if len(gsi_wow) > 0:
    for _, g in gsi_wow.iterrows():
        wow = f"{g['WOW_PCT']:+.1f}%" if pd.notna(g['WOW_PCT']) else "N/A"
        gsi_wow_ctx += f"  {g['GSI_GROUP']}: {int(g['TOTAL_REQUESTS']):,} requests (LW={int(g['LW_REQUESTS']):,}, PW={int(g['PW_REQUESTS']):,}), WoW={wow}\n"
else:
    gsi_wow_ctx = "  No GSI WoW data available.\n"

# NoAM SI WoW context (engagement — CoCo requests)
noam_si_wow_ctx = ""
if len(noam_si_wow) > 0:
    for _, s in noam_si_wow.iterrows():
        wow = f"{s['WOW_PCT']:+.1f}%" if pd.notna(s['WOW_PCT']) else "N/A"
        noam_si_wow_ctx += f"  {s['PARTNER_NAME']}: {int(s['TOTAL_REQUESTS']):,} requests (LW={int(s['LW_REQUESTS']):,}, PW={int(s['PW_REQUESTS']):,}), WoW={wow}\n"
else:
    noam_si_wow_ctx = "  No NoAM SI WoW data available.\n"


data_context = f"""
=== Q2 (May-Jul 2026) | MANAGED PARTNERS ONLY (20) | Stages 3-7 ===
NOTE: All numbers are Q2 only (May 1 - Jul 31, 2026) for the 20 managed partners, except REGIONAL BREAKDOWN which shows all partners.

GLOBAL REFERENCE (all partners, Q2, Stages 3-7, with account-level attribution): {int(go['COCO_USE_CASES'])} CoCo UCs | {int(go['TOTAL_PARTNERS'])} partners | ${go['TOTAL_EACV']/1_000_000:.1f}M EACV | {go['COCO_PCT']}% CoCo adoption

MANAGED PARTNERS Q2 HEADLINE:
  CoCo Use Cases: {managed_coco_ucs} (THIS is the CoCo number for the opening sentence)
  Total Pipeline (CoCo + non-CoCo): {managed_total_ucs} use cases
  CoCo Adoption: {managed_coco_pct}%
  Active Partners: {managed_total_partners}
  Total EACV: ${managed_total_eacv/1_000_000:.1f}M
  CoCo EACV: ${managed_coco_eacv/1_000_000:.1f}M
  CoCo Deployed: {managed_coco_deployed}
  Partners Meeting 50% Target: {partners_meeting_50} ({partners_meeting_list})
  Partners Below 50% Target: {partners_below_50}
CoCo Active: {managed_total_partners} of 20 managed partners have Q2 activity
No Q2 Activity ({managed_inactive_partners} partners): {', '.join(managed_inactive_names)}

MANAGED PARTNER COCO COVERAGE (Q2, by region):
  Overall: {managed_total_ucs} total UCs, {managed_coco_ucs} CoCo, {managed_coco_pct}%
{regional_coco_ctx}

PIPELINE (Managed Partners, Q2, all UCs):
{stage_ctx}

PIPELINE WoW (all CoCo partners, use case count change vs prior week):
{pipeline_wow_ctx}

COCO CREDIT CONSUMPTION (Q2, managed partners):
{credit_ctx}

REGIONAL BREAKDOWN (Managed and Unmanaged):
{region_ctx}

PARTNER SCORECARD (all 20 managed partners, by EACV, with CoCo coverage — target 50%):
{partner_ctx}

COCO ADOPTION WoW — OVERALL (from weekly snapshot table):
{adoption_wow_ctx}

COCO ADOPTION WoW — PER MANAGED PARTNER (sorted by CoCo %):
{adoption_wow_partner_ctx}

PARTNER WORKLOAD MIX (managed partners only):
{partner_wl_ctx}

OKR PROGRESS — 6 GSIs WoW (CoCo engagement, all regions combined — LW=last week, PW=prior week):
{gsi_wow_ctx}

OKR PROGRESS — NoAM SIs WoW (CoCo engagement — LW=last week, PW=prior week):
{noam_si_wow_ctx}

COMMENT HIGHLIGHTS (managed partners only, Top 10 by EACV):
{comment_ctx}
"""

st.markdown("---")
st.subheader("Generate Email Summary")

current_user = "rithesh.makkena"
try:
    current_user = conn.query("SELECT CURRENT_USER()").iloc[0][0].lower()
except Exception:
    pass

recipients_input = st.text_area(
    "To (one name per line, e.g. 'John Smith' → john.smith@snowflake.com)",
    value="",
    height=80,
    placeholder="John Smith\nJane Doe\ncustom.email@partner.com",
    key="email_recipients"
)

default_prompt = f"""You are writing a polished executive briefing for Snowflake leadership on CoCo partner use case performance. This will be read by VPs and the CEO — keep it sharp, data-rich, and action-oriented.
Do NOT include a title, heading, or subject line like "Cortex Code (CoCo) Partner Use Case Traction" at the top of the email. Start directly with the Note block.

SCOPE: Focus on the 20 managed partners. Use MANAGED PARTNERS HEADLINE numbers for all sections EXCEPT Regional Breakdown.
- The GLOBAL REFERENCE line is for context only — mention it once in the opening sentence.
- REGIONAL BREAKDOWN uses all-partner data (managed + unmanaged) to show geographic traction.
- ALL other sections (Pipeline, Top Partners, OKR, Patterns, Wins) use managed partners ONLY.

Follow this EXACT structure with 9 sections:

## **Note: 6 GSIs and 14 NoAM Partners are aligned with Q2 OKR, but we are still showing EMEA & APJ adoption pattern.**

## EXECUTIVE SUMMARY
2-3 sentences maximum, then exactly 6 bullets.
- Open with: "[X] CoCo use cases across 20 managed partners **(14 NoAM-focused partners + 6 GSIs)** representing $[Z]M in CoCo EACV, with [W] deployed in production. Global CoCo pipeline: [G] use cases across [A] partners worth $[T]M."
- Second sentence: one crisp insight on the dominant pattern (e.g., what's working, what's accelerating).
- Bullet 1: "**Leading use case types:** [top 3 by count]"
- Bullet 2: "**Region leaders:** NoAM ([top 3 partners]), EMEA ([top 3]), APJ ([top 3])"
- Bullet 3: "**Top Global SIs by EACV:** ([top 3 global partners by EACV])"
- Bullet 4: "**Top Regional SIs by EACV:** ([top 3 regional managed partners by EACV])"
- Bullet 5: "**Competitive displacement:** [top 3 competitors by count]"
- Bullet 6: "**[Detailed Partner CoCo usecase dashboard](https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS)**"

PARTNER CLASSIFICATION:
- Global SIs (6): EY, Deloitte Consulting, Accenture, Cognizant Technology Solutions US Corp, Capgemini Technologies LLC, IBM
- Regional Managed Partners (15): 7Rivers, Aimpoint Digital, BlueCloud, kipi.ai, evolv Consulting, Infostrux, Infosys, KPMG, LTIMindtree, NTT DATA, phData, Slalom, Squadron Data, Tredence

## OKR PROGRESS
| Metric | Current | Target | Gap | WoW Δ |
- Show exactly these 4 rows: CoCo Use Cases, CoCo Adoption %, Partners Meeting 50%, CoCo EACV
- For CoCo EACV row: Target = "-", Gap = "-", WoW Δ = "-"
- For the "Partners meeting 50%" row: Current = count, Target = "20", WoW Δ = "-"
- For CoCo Use Cases row: WoW Δ from "COCO ADOPTION WoW — OVERALL" (Δ UCs field)
- For CoCo Adoption % row: WoW Δ from "COCO ADOPTION WoW — OVERALL" (WoW field for adoption %)
- If WoW data shows "N/A (first week)", put "-" in WoW Δ column with note "(data from next week)"
- After the table: ONE sentence on what it takes to close the gap (how many more CoCo UCs needed, which partners have the biggest gaps)
- Call out partners already meeting 50% target
- Use MANAGED PARTNERS data only

## MANAGED PARTNER PIPELINE OVERVIEW
| Stage | Count | EACV | WoW Δ |
- Use MANAGED PARTNERS pipeline data (stage_ctx) for Count and EACV
- Add "WoW Δ" column using "PIPELINE WoW" data — show +/- integer change in use case count vs prior week for each stage
- Use stage mapping: Active Pipeline (3), Won (4), In Implementation (5-6), Deployed (7), and Total

## MANAGED PARTNER COCO COVERAGE
| Scope | Total UCs | CoCo UCs | CoCo % | Partners | Avg CoCo %/Partner |
- Show overall managed partner CoCo adoption rate and per-region breakdown (NoAM, EMEA, APJ)
- "Total UCs" = all use cases (CoCo + non-CoCo) for managed partners in Q2
- "Avg CoCo %/Partner" = average of each partner's individual CoCo %, not the aggregate
- After table: ONE sentence on which region has strongest/weakest CoCo penetration

## REGIONAL BREAKDOWN (Managed and Unmanaged)
| Region | Use Cases | EACV | Partners |
After the table, ONE sentence per region on its dominant theme.
- This is the ONLY section that uses all-partner data

## PARTNER SCORECARD (all 20 managed partners)
| Partner | Total UCs | CoCo UCs | CoCo% | WoW Δ% | WoW Δ UCs | EACV | AI | DE | Analytics |
- Show ALL 20 managed partners (do not cap or truncate). Sort by EACV descending.
- "Total UCs" = all partner use cases (stages 3-7). "CoCo%" = CoCo/Total.
- WoW Δ% and WoW Δ UCs from "COCO ADOPTION WoW — PER MANAGED PARTNER" — show "-" if N/A
- Our target is **50% CoCo adoption** per partner. After the table, add ONE sentence calling out which partners are closest to 50% and which need enablement focus.

## USE CASE PATTERNS (managed partners only)
3-4 bullets. Each: **Pattern Name** — one sentence with partner names and EACV.

## NOTABLE WINS (managed partners only)
2-3 bullets. Cite specific partner + customer account + what happened. Focus on production deployments, competitive wins, or executive-level engagement.

## DISCLAIMER
"**Disclaimer:** Use case data sourced from SE comments (coco/cortex code mentions), #coco in Partner Comments, and AI-Cortex Code feature flag. Pipeline figures are being confirmed by the PDM team and are subject to change. Detailed stats: http://go/cocopse"

FORMATTING RULES:
- Markdown tables for ALL data — no narrative paragraphs for numbers
- Executive summary: exactly 2-3 sentences + 6 bullets, nothing more
- Section headings: ## format, no numbering
- Currency: $X.XM for millions, $XK for thousands, $0 when zero
- Numbers: use commas (e.g., 1,200)
- Total length: under 600 words
- Tone: confident, data-driven, executive-appropriate
- No greeting, sign-off, subject line, or filler"""

prompt_input = st.text_area(
    "Prompt",
    value=default_prompt,
    height=300,
    help="Edit this prompt to customize the email output. Data summary above will be automatically included."
)

if st.button("Generate Email Summary", type="primary", key="email_generate"):
    full_prompt = f"""{prompt_input}

DATA:
{data_context}

Write the executive briefing:"""

    response_placeholder = st.empty()
    response_placeholder.info("Generating executive briefing with Cortex Complete...")
    full_response = cortex_complete(conn, "claude-sonnet-4-5", full_prompt)
    response_placeholder.markdown(full_response)

    st.success("Email generated successfully!")
    st.markdown("---")

    html_email = md_to_html(full_response)

    to_lines = [l.strip() for l in recipients_input.strip().splitlines() if l.strip()] if recipients_input.strip() else []
    to_emails = [name_to_email(n) for n in to_lines]
    to_str = ','.join(to_emails)
    subject_text = f"Cortex Code Use Case Intelligence - {datetime.now().strftime('%B %d, %Y')}"
    subject = urllib.parse.quote(subject_text)
    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_str}&su={subject}"

    st.info("**How to send:** Click **Copy Rich Text** below, then **Open in Gmail**, and paste (Ctrl+V / Cmd+V) into the email body. Tables will render with full formatting.")

    col1, col2, col3 = st.columns(3)
    with col1:
        escaped_html = html_email.replace('`', '\\`').replace('${', '\\${')
        plain_text = full_response.replace(chr(96), '').replace('${', '')[:8000]
        copy_js = f"""
        <button onclick="copyRich()" id="copyBtn" style="
            background-color: #29B5E8; color: white; border: none; padding: 8px 20px;
            border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600;
            width: 100%;">Copy Rich Text</button>
        <script>
        function copyRich() {{
            const html = `{escaped_html}`;
            const blob = new Blob([html], {{type: 'text/html'}});
            const plainBlob = new Blob([`{plain_text}`], {{type: 'text/plain'}});
            const item = new ClipboardItem({{
                'text/html': blob,
                'text/plain': plainBlob
            }});
            navigator.clipboard.write([item]).then(() => {{
                document.getElementById('copyBtn').textContent = 'Copied!';
                document.getElementById('copyBtn').style.backgroundColor = '#28a745';
                setTimeout(() => {{
                    document.getElementById('copyBtn').textContent = 'Copy Rich Text';
                    document.getElementById('copyBtn').style.backgroundColor = '#29B5E8';
                }}, 2000);
            }});
        }}
        </script>
        """
        components.html(copy_js, height=45)
    with col2:
        st.link_button("Open in Gmail", gmail_url, type="primary")
    with col3:
        st.download_button(
            label="Download as HTML",
            data=html_email,
            file_name=f"coco_usecase_briefing_{datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html"
        )

st.markdown("---")
st.caption("Powered by Snowflake Cortex Complete | Data sourced from CoCo Use Case Intelligence")
