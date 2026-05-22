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
    coco_coverage = get_partner_coco_coverage(conn, region=region)
    global_overview = get_adoption_overview(conn, '2026-05-01', '2026-07-31')

    # Managed partner stage EACV breakdown — Q2 ONLY (May 1 - Jul 31, 2026)
    managed_partners_sql = "','".join(MANAGED_PARTNERS)
    Q2_START = '2026-05-01'
    Q2_END = '2026-07-31'

    # CoCo-active accounts CTE (reusable across queries)
    COCO_ACCOUNTS_CTE = f"""
        coco_active_accounts AS (
            SELECT DISTINCT UPPER(salesforce_account_name) AS ACCOUNT_NAME_UPPER
            FROM snowscience.llm.cortex_code_user_day_fact
            WHERE ds >= '{Q2_START}' AND snowflake_account_type = 'Customer' AND total_daily_requests > 0
        )
    """

    # Q2 Credit consumption for managed partners
    credit_data = get_partner_credit_consumption(conn, MANAGED_PARTNERS, Q2_START, Q2_END)

    managed_stage_data = conn.query(f"""
        WITH {COCO_ACCOUNTS_CTE}
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

    # Q2 headline stats for managed partners (all UCs + CoCo UCs with account-level attribution)
    managed_q2_stats = conn.query(f"""
        WITH {COCO_ACCOUNTS_CTE}
        SELECT 
            COUNT(*) AS TOTAL_UCS,
            SUM(CASE WHEN uc.IS_COCO OR caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN 1 ELSE 0 END) AS COCO_UCS,
            COALESCE(SUM(USE_CASE_EACV), 0) AS TOTAL_EACV,
            COALESCE(SUM(CASE WHEN uc.IS_COCO OR caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN USE_CASE_EACV ELSE 0 END), 0) AS COCO_EACV,
            COUNT(DISTINCT uc.PARTNER_NAME) AS ACTIVE_PARTNERS,
            SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND (uc.IS_COCO OR caa.ACCOUNT_NAME_UPPER IS NOT NULL) THEN 1 ELSE 0 END) AS COCO_DEPLOYED
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
        LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
        WHERE uc.PARTNER_NAME IN ('{managed_partners_sql}')
        AND uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan','5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{Q2_START}' AND uc.DECISION_DATE <= '{Q2_END}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{Q2_START}' AND uc.GO_LIVE_DATE <= '{Q2_END}')
        )
    """)

    # Q2 CoCo coverage by region for managed partners (with account-level attribution)
    managed_q2_regional = conn.query(f"""
        WITH {COCO_ACCOUNTS_CTE}
        SELECT 
            CASE 
                WHEN THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec') THEN 'NoAM'
                WHEN THEATER_NAME = 'EMEA' THEN 'EMEA'
                WHEN THEATER_NAME = 'APJ' THEN 'APJ'
                ELSE 'Other'
            END AS REGION,
            COUNT(*) AS TOTAL_UCS,
            SUM(CASE WHEN uc.IS_COCO OR caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN 1 ELSE 0 END) AS COCO_UCS,
            ROUND(SUM(CASE WHEN uc.IS_COCO OR caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS COCO_PCT,
            COUNT(DISTINCT uc.PARTNER_NAME) AS PARTNER_COUNT
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
        LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
        WHERE uc.PARTNER_NAME IN ('{managed_partners_sql}')
        AND uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan','5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{Q2_START}' AND uc.DECISION_DATE <= '{Q2_END}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{Q2_START}' AND uc.GO_LIVE_DATE <= '{Q2_END}')
        )
        GROUP BY REGION
        ORDER BY TOTAL_UCS DESC
    """)

    # Compute avg CoCo % per partner per region
    managed_q2_partner_avg = conn.query(f"""
        WITH partner_stats AS (
            SELECT 
                CASE 
                    WHEN THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec') THEN 'NoAM'
                    WHEN THEATER_NAME = 'EMEA' THEN 'EMEA'
                    WHEN THEATER_NAME = 'APJ' THEN 'APJ'
                    ELSE 'Other'
                END AS REGION,
                PARTNER_NAME,
                COUNT(*) AS TOTAL_UCS,
                SUM(CASE WHEN IS_COCO THEN 1 ELSE 0 END) AS COCO_UCS,
                ROUND(SUM(CASE WHEN IS_COCO THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS COCO_PCT
            FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES
            WHERE PARTNER_NAME IN ('{managed_partners_sql}')
            AND USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan','5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
            AND (
                (USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND DECISION_DATE >= '{Q2_START}' AND DECISION_DATE <= '{Q2_END}')
                OR (USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND GO_LIVE_DATE >= '{Q2_START}' AND GO_LIVE_DATE <= '{Q2_END}')
            )
            GROUP BY REGION, PARTNER_NAME
        )
        SELECT REGION, ROUND(AVG(COCO_PCT), 1) AS AVG_COCO_PCT_PER_PARTNER
        FROM partner_stats
        GROUP BY REGION
        ORDER BY AVG_COCO_PCT_PER_PARTNER DESC
    """)

    # Q2 Top Partners: per-partner breakdown with workload mix (with account-level attribution)
    managed_q2_partners = conn.query(f"""
        WITH {COCO_ACCOUNTS_CTE}
        SELECT 
            uc.PARTNER_NAME,
            COUNT(*) AS TOTAL_UCS,
            SUM(CASE WHEN uc.IS_COCO OR caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN 1 ELSE 0 END) AS COCO_UCS,
            ROUND(SUM(CASE WHEN uc.IS_COCO OR caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 0) AS COCO_PCT,
            COALESCE(SUM(uc.USE_CASE_EACV), 0) AS TOTAL_EACV,
            SUM(CASE WHEN uc.TECHNICAL_USE_CASE LIKE '%AI%' THEN 1 ELSE 0 END) AS AI,
            SUM(CASE WHEN uc.TECHNICAL_USE_CASE LIKE '%DE:%' THEN 1 ELSE 0 END) AS DE,
            SUM(CASE WHEN uc.TECHNICAL_USE_CASE LIKE '%Analytics%' THEN 1 ELSE 0 END) AS ANALYTICS
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
        LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
        WHERE uc.PARTNER_NAME IN ('{managed_partners_sql}')
        AND uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan','5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{Q2_START}' AND uc.DECISION_DATE <= '{Q2_END}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{Q2_START}' AND uc.GO_LIVE_DATE <= '{Q2_END}')
        )
        GROUP BY uc.PARTNER_NAME
        ORDER BY TOTAL_EACV DESC
        LIMIT 15
    """)

# Executive email always uses MANAGED_PARTNERS list, ignoring sidebar partner filter
# Filter to managed partners only for executive email context
partner_data = partner_data[partner_data['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
comment_data = comment_data[comment_data['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
partner_workloads = partner_workloads[partner_workloads['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
coco_coverage = coco_coverage[coco_coverage['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
if 'PARTNER_NAME' in regional_themes.columns:
    regional_themes = regional_themes[regional_themes['PARTNER_NAME'].isin(MANAGED_PARTNERS)]

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
CoCo Active: {managed_total_partners} of 20 managed partners have Q2 activity
No Q2 Activity ({managed_inactive_partners} partners): {', '.join(managed_inactive_names)}

MANAGED PARTNER COCO COVERAGE (Q2, by region):
  Overall: {managed_total_ucs} total UCs, {managed_coco_ucs} CoCo, {managed_coco_pct}%
{regional_coco_ctx}

PIPELINE (Managed Partners, Q2, all UCs):
{stage_ctx}

COCO CREDIT CONSUMPTION (Q2, managed partners):
{credit_ctx}

REGIONAL BREAKDOWN (Managed and Unmanaged):
{region_ctx}

TOP PARTNERS (by EACV, managed partners only, with CoCo coverage — target 50%):
{partner_ctx}

PARTNER WORKLOAD MIX (managed partners only):
{partner_wl_ctx}

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

default_prompt = f"""You are writing a polished executive briefing for Snowflake leadership on Cortex Code (CoCo) partner use case traction. This will be read by VPs and the CEO — keep it sharp, data-rich, and action-oriented.

SCOPE: Focus on the 20 managed partners. Use MANAGED PARTNERS HEADLINE numbers for all sections EXCEPT Regional Breakdown.
- The GLOBAL REFERENCE line is for context only — mention it once in the opening sentence.
- REGIONAL BREAKDOWN uses all-partner data (managed + unmanaged) to show geographic traction.
- ALL other sections (Pipeline, Top Partners, OKR, Patterns, Wins) use managed partners ONLY.

Follow this EXACT structure with 9 sections:

## EXECUTIVE SUMMARY
2-3 sentences maximum, then exactly 6 bullets.
- Open with: "[X] CoCo use cases across 20 managed partners representing $[Z]M in CoCo EACV, with [W] deployed in production. Global CoCo pipeline: [G] use cases across [A] partners worth $[T]M."
- Second sentence: one crisp insight on the dominant pattern (e.g., what's working, what's accelerating).
- Bullet 1: "**Leading use case types:** [top 3 by count]"
- Bullet 2: "**Region leaders:** NoAM ([top 3 partners]), EMEA ([top 3]), APJ ([top 3])"
- Bullet 3: "**Top Global SIs by EACV:** ([top 3 global partners by EACV])"
- Bullet 4: "**Top Regional SIs by EACV:** ([top 3 regional managed partners by EACV])"
- Bullet 5: "**Competitive displacement:** [top 3 competitors by count]"
- Bullet 6: "**CoCo activity:** [X] of 20 managed partners active; [Y] with no CoCo activity: [list names]"

PARTNER CLASSIFICATION:
- Global SIs (6): EY, Deloitte Consulting, Accenture, Cognizant Technology Solutions US Corp, Capgemini Technologies LLC, IBM
- Regional Managed Partners (15): 7Rivers, Aimpoint Digital, BlueCloud, kipi.ai, evolv Consulting, Infostrux, Infosys, KPMG, LTIMindtree, NTT DATA, phData, Slalom, Squadron Data, Tredence

## OKR PROGRESS
| Metric | Current | Target | Gap |
- Show: CoCo use cases vs 50% target, CoCo adoption %, partners meeting 50%, CoCo EACV
- For CoCo EACV row: put "-" in Target and Gap columns (no target for EACV)
- After the table: ONE sentence on what it takes to close the gap (how many more CoCo UCs needed, which partners have the biggest gaps)
- Call out partners already meeting 50% target
- Use MANAGED PARTNERS data only

## MANAGED PARTNER PIPELINE OVERVIEW
| Stage | Count | EACV |
- Use MANAGED PARTNERS pipeline data only

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

## TOP PARTNERS (managed partners only)
| Partner | Total UCs | CoCo UCs | CoCo% | EACV | AI | DE | Analytics |
- Top 12 by EACV. "Total UCs" = all partner use cases (stages 3-7). "CoCo%" = CoCo/Total.
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
