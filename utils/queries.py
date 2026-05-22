import streamlit as st
from datetime import timedelta

SCHEMA = "TEMP.COCO_PARTNER_ADOPTION"

def _use_case_base(start_date=None, end_date=None):
    """Generate USE_CASE_BASE CTE with configurable date filter."""
    if start_date and end_date:
        date_filter = f"""(
            (UC.USE_CASE_STAGE IN ('1 - Discovery', '2 - Scoping', '3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND UC.DECISION_DATE >= '{start_date}' AND UC.DECISION_DATE <= '{end_date}')
            OR (UC.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND UC.GO_LIVE_DATE >= '{start_date}' AND UC.GO_LIVE_DATE <= '{end_date}')
        )"""
    else:
        date_filter = """(
            (UC.USE_CASE_STAGE IN ('1 - Discovery', '2 - Scoping', '3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND UC.DECISION_DATE > '2025-11-20')
            OR (UC.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND UC.GO_LIVE_DATE > '2025-11-20')
        )"""
    return f"""
    WITH hierarchy AS (
        SELECT PARTNER_NAME, PARENT_PARTNER_NAME FROM {SCHEMA}.PARTNER_HIERARCHY
    ),
    stage_days AS (
        SELECT USE_CASE_ID, DATEDIFF('day', MOVEIN_DATE, CURRENT_DATE()) AS DAYS_IN_CURRENT_STAGE
        FROM MDM.MDM_INTERFACES.FACT_USE_CASE_STAGE_MOVEMENT
        QUALIFY ROW_NUMBER() OVER (PARTITION BY USE_CASE_ID ORDER BY MOVEIN_DATE DESC) = 1
    ),
    raw AS (
        SELECT 
            UC.USE_CASE_ID, UC.USE_CASE_NUMBER, UC.ACCOUNT_NAME, UC.USE_CASE_NAME, UC.USE_CASE_STAGE, UC.USE_CASE_EACV,
            TRY_CAST(UC.ACCOUNT_BASE_RENEWAL_ACV AS FLOAT) AS ACCOUNT_ARR, UC.TECHNICAL_USE_CASE, UC.ACCOUNT_LEAD_SE_NAME,
            UC.ACCOUNT_GVP, UC.THEATER_NAME, UC.REGION_NAME, UC.DECISION_DATE, UC.GO_LIVE_DATE, UC.POC_END_DATE, UC.POC_START_DATE,
            UC.SE_COMMENTS, UC.MEDDPICC_METRICS, UC.MEDDPICC_IDENTIFY_PAIN, UC.COMPETITORS, UC.NEXT_STEPS, UC.PRIORITIZED_FEATURES,
            UC.WORKLOADS, UC.SPECIALIST_COMMENTS,
            COALESCE(
                NULLIF(ARRAY_TO_STRING(UC.IMPLEMENTATION_SERVICES_PARTNER, ', '), ''),
                NULLIF(ARRAY_TO_STRING(UC.CO_SELL_SERVICES_PARTNER, ', '), ''),
                NULLIF(UC.PARTNER_NAME, ''),
                ARRAY_TO_STRING(UC.USE_CASE_PARTNER, ', ')
            ) AS RAW_PARTNER_NAME,
            UC.PARTNER_COMMENTS, UC.IS_WON, UC.IS_DEPLOYED, UC.IS_LOST, UC.CREATED_DATE, UC.ACTUAL_USE_CASE_WON_DATE,
            UC.ACTUAL_USE_CASE_DEPLOYMENT_DATE, UC.LOSS_DATE, UC.DAYS_IN_STAGE,
            CASE 
                WHEN UC.PARTNER_COMMENTS ILIKE '%#coco%' THEN 'PARTNER_COMMENTS'
                WHEN UC.SE_COMMENTS ILIKE '%coco%' OR UC.SE_COMMENTS ILIKE '%cortex code%' THEN 'SE_COMMENTS'
                WHEN UC.PRIORITIZED_FEATURES ILIKE '%AI - Cortex Code%' THEN 'FEATURE_FLAG'
                ELSE 'MULTIPLE'
            END AS COCO_MENTION_SOURCE
        FROM MDM.MDM_INTERFACES.DIM_USE_CASE AS UC
        WHERE (UC.SE_COMMENTS ILIKE '%coco%' OR UC.SE_COMMENTS ILIKE '%cortex code%' OR UC.PARTNER_COMMENTS ILIKE '%#coco%' OR UC.PRIORITIZED_FEATURES ILIKE '%AI - Cortex Code%')
        AND {date_filter}
    ),
    use_cases AS (
        SELECT 
            r.USE_CASE_ID, r.USE_CASE_NUMBER, r.ACCOUNT_NAME, r.USE_CASE_NAME, r.USE_CASE_STAGE, r.USE_CASE_EACV,
            r.ACCOUNT_ARR, r.TECHNICAL_USE_CASE, r.ACCOUNT_LEAD_SE_NAME, r.ACCOUNT_GVP, r.THEATER_NAME, r.REGION_NAME,
            r.DECISION_DATE, r.GO_LIVE_DATE, r.POC_END_DATE, r.POC_START_DATE, r.SE_COMMENTS, r.MEDDPICC_METRICS,
            r.MEDDPICC_IDENTIFY_PAIN, r.COMPETITORS, r.NEXT_STEPS, r.PRIORITIZED_FEATURES, r.WORKLOADS, r.SPECIALIST_COMMENTS,
            COALESCE(h.PARENT_PARTNER_NAME, r.RAW_PARTNER_NAME) AS PARTNER_NAME,
            r.PARTNER_COMMENTS, r.IS_WON, r.IS_DEPLOYED, r.IS_LOST, r.CREATED_DATE, r.ACTUAL_USE_CASE_WON_DATE,
            r.ACTUAL_USE_CASE_DEPLOYMENT_DATE, r.LOSS_DATE, r.DAYS_IN_STAGE, r.COCO_MENTION_SOURCE,
            COALESCE(sd.DAYS_IN_CURRENT_STAGE, r.DAYS_IN_STAGE) AS DAYS_IN_CURRENT_STAGE
        FROM raw r
        LEFT JOIN stage_days sd ON r.USE_CASE_ID = sd.USE_CASE_ID
        LEFT JOIN hierarchy h ON r.RAW_PARTNER_NAME = h.PARTNER_NAME
        WHERE r.RAW_PARTNER_NAME IS NOT NULL AND TRIM(r.RAW_PARTNER_NAME) != ''
        AND r.RAW_PARTNER_NAME NOT IN ('Sigma Computing, Inc.', 'Bloomberg Finance L.P. - DCP Account')
    )
"""

# Keep backward-compatible constant for any remaining direct references
USE_CASE_BASE = _use_case_base()

def _theater_filter(region: str) -> str:
    if not region or region == "Global":
        return ""
    elif region == "NoAM":
        return " AND THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition')"
    elif region == "EMEA":
        return " AND THEATER_NAME = 'EMEA'"
    elif region == "APJ":
        return " AND THEATER_NAME = 'APJ'"
    return ""

def _source_filter(source: str) -> str:
    if source == "PSE Confirmed":
        return " AND COCO_MENTION_SOURCE = 'PARTNER_COMMENTS'"
    elif source == "Feature Flag":
        return " AND COCO_MENTION_SOURCE = 'FEATURE_FLAG'"
    return ""

@st.cache_data(ttl=timedelta(minutes=30))
def get_use_cases(_conn, partner=None, stage=None, region=None, source=None, technical_type=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT * FROM use_cases WHERE 1=1{tf}{sf}
    """
    if partner and partner != "All":
        query += f" AND PARTNER_NAME ILIKE '%{partner.replace(chr(39), chr(39)+chr(39))}%'"
    if stage:
        stages_str = "', '".join(stage)
        query += f" AND USE_CASE_STAGE IN ('{stages_str}')"
    if technical_type and technical_type != "All":
        query += f" AND TECHNICAL_USE_CASE ILIKE '%{technical_type.replace(chr(39), chr(39)+chr(39))}%'"
    query += " ORDER BY USE_CASE_EACV DESC NULLS LAST"
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_summary_stats(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        COUNT(*) AS total_use_cases,
        COUNT(DISTINCT PARTNER_NAME) AS total_partners,
        COUNT(DISTINCT ACCOUNT_NAME) AS total_accounts,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(CASE WHEN USE_CASE_STAGE IN ('1 - Discovery', '2 - Scoping', '3 - Technical / Business Validation') THEN 1 END) AS active_count,
        SUM(CASE WHEN USE_CASE_STAGE IN ('1 - Discovery', '2 - Scoping', '3 - Technical / Business Validation') THEN USE_CASE_EACV ELSE 0 END) AS active_eacv,
        COUNT(CASE WHEN USE_CASE_STAGE = '4 - Use Case Won / Migration Plan' THEN 1 END) AS won_count,
        SUM(CASE WHEN USE_CASE_STAGE = '4 - Use Case Won / Migration Plan' THEN USE_CASE_EACV ELSE 0 END) AS won_eacv,
        COUNT(CASE WHEN USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete') THEN 1 END) AS impl_count,
        SUM(CASE WHEN USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete') THEN USE_CASE_EACV ELSE 0 END) AS impl_eacv,
        COUNT(CASE WHEN USE_CASE_STAGE = '7 - Deployed' THEN 1 END) AS deployed_count,
        SUM(CASE WHEN USE_CASE_STAGE = '7 - Deployed' THEN USE_CASE_EACV ELSE 0 END) AS deployed_eacv,
        AVG(DAYS_IN_CURRENT_STAGE) AS avg_days_in_stage,
        COUNT(CASE WHEN COCO_MENTION_SOURCE = 'PARTNER_COMMENTS' THEN 1 END) AS partner_confirmed_count,
        COUNT(CASE WHEN COCO_MENTION_SOURCE = 'FEATURE_FLAG' THEN 1 END) AS feature_flag_count,
        COUNT(CASE WHEN COCO_MENTION_SOURCE = 'SE_COMMENTS' THEN 1 END) AS se_confirmed_count
    FROM use_cases
    WHERE 1=1{tf}{sf}
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_by_partner(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        PARTNER_NAME,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(CASE WHEN IS_WON THEN 1 END) AS won_count,
        COUNT(CASE WHEN IS_DEPLOYED THEN 1 END) AS deployed_count,
        AVG(DAYS_IN_CURRENT_STAGE) AS avg_days,
        COUNT(CASE WHEN COCO_MENTION_SOURCE = 'PARTNER_COMMENTS' THEN 1 END) AS pse_confirmed,
        COUNT(CASE WHEN COCO_MENTION_SOURCE = 'FEATURE_FLAG' THEN 1 END) AS feature_flag
    FROM use_cases
    WHERE 1=1{tf}{sf}
    GROUP BY PARTNER_NAME
    ORDER BY total_eacv DESC NULLS LAST
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_by_stage(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        USE_CASE_STAGE,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        AVG(DAYS_IN_CURRENT_STAGE) AS avg_days
    FROM use_cases
    WHERE 1=1{tf}{sf}
    GROUP BY USE_CASE_STAGE
    ORDER BY USE_CASE_STAGE
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_by_technical_type(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        TECHNICAL_USE_CASE,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv
    FROM use_cases
    WHERE TECHNICAL_USE_CASE IS NOT NULL{tf}{sf}
    GROUP BY TECHNICAL_USE_CASE
    ORDER BY total_eacv DESC NULLS LAST
    LIMIT 15
    """
    return _conn.query(query)

DT_OKR = f"{SCHEMA}.DT_OKR_USE_CASES"

def _coco_accounts_cte(start_date):
    """CTE for customer accounts with actual CoCo product usage since start_date."""
    return f"""coco_active_accounts AS (
        SELECT DISTINCT UPPER(salesforce_account_name) AS ACCOUNT_NAME_UPPER
        FROM snowscience.llm.cortex_code_user_day_fact
        WHERE ds >= '{start_date}' AND snowflake_account_type = 'Customer' AND total_daily_requests > 0
    )"""

def _is_coco_expanded():
    """SQL expression for expanded CoCo detection (IS_COCO OR account has CoCo usage)."""
    return "(uc.IS_COCO OR caa.ACCOUNT_NAME_UPPER IS NOT NULL)"

@st.cache_data(ttl=timedelta(minutes=30))
def get_adoption_overview(_conn, start_date, end_date, region=None, partners=None):
    """Get adoption metrics from DT_OKR_USE_CASES for the Overview page."""
    tf = _theater_filter(region)
    coco_cte = _coco_accounts_cte(start_date)
    is_coco = _is_coco_expanded()
    partner_filter = ""
    if partners:
        partners_sql = "','".join(partners)
        partner_filter = f" AND uc.PARTNER_NAME IN ('{partners_sql}')"
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    query = f"""
    WITH {coco_cte}
    SELECT 
        COUNT(*) AS TOTAL_USE_CASES,
        COUNT(DISTINCT uc.PARTNER_NAME) AS TOTAL_PARTNERS,
        COUNT(DISTINCT uc.ACCOUNT_NAME) AS TOTAL_ACCOUNTS,
        COALESCE(SUM(uc.USE_CASE_EACV), 0) AS TOTAL_EACV,
        ROUND(AVG(uc.DAYS_IN_CURRENT_STAGE), 0) AS AVG_DAYS_IN_STAGE,
        SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) AS COCO_USE_CASES,
        ROUND(SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS COCO_PCT,
        SUM(CASE WHEN {is_coco} AND uc.COCO_SOURCE = 'PARTNER_COMMENTS' THEN 1 ELSE 0 END) AS PARTNER_CONFIRMED_COUNT,
        SUM(CASE WHEN {is_coco} AND uc.COCO_SOURCE = 'FEATURE_FLAG' THEN 1 ELSE 0 END) AS FEATURE_FLAG_COUNT,
        SUM(CASE WHEN {is_coco} AND uc.COCO_SOURCE = 'SE_COMMENTS' THEN 1 ELSE 0 END) AS SE_CONFIRMED_COUNT,
        SUM(CASE WHEN NOT uc.IS_COCO AND caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN 1 ELSE 0 END) AS ACCOUNT_LEVEL_COUNT,
        COUNT(CASE WHEN uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation') THEN 1 END) AS VALIDATION_COUNT,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation') THEN uc.USE_CASE_EACV ELSE 0 END) AS VALIDATION_EACV,
        COUNT(CASE WHEN uc.USE_CASE_STAGE = '4 - Use Case Won / Migration Plan' THEN 1 END) AS WON_COUNT,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '4 - Use Case Won / Migration Plan' THEN uc.USE_CASE_EACV ELSE 0 END) AS WON_EACV,
        COUNT(CASE WHEN uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete') THEN 1 END) AS IMPL_COUNT,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete') THEN uc.USE_CASE_EACV ELSE 0 END) AS IMPL_EACV,
        COUNT(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' THEN 1 END) AS DEPLOYED_COUNT,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' THEN uc.USE_CASE_EACV ELSE 0 END) AS DEPLOYED_EACV
    FROM {DT_OKR} uc
    LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
    WHERE {date_filter}
    {tf}{partner_filter}
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_adoption_by_partner(_conn, start_date, end_date, region=None):
    """Get per-partner metrics from DT_OKR_USE_CASES."""
    tf = _theater_filter(region)
    coco_cte = _coco_accounts_cte(start_date)
    is_coco = _is_coco_expanded()
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    query = f"""
    WITH {coco_cte}
    SELECT 
        uc.PARTNER_NAME,
        COUNT(*) AS TOTAL_USE_CASES,
        SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) AS COCO_USE_CASES,
        ROUND(SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS COCO_PCT,
        COALESCE(SUM(uc.USE_CASE_EACV), 0) AS TOTAL_EACV
    FROM {DT_OKR} uc
    LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
    WHERE {date_filter}
    {tf}
    GROUP BY uc.PARTNER_NAME
    ORDER BY TOTAL_EACV DESC NULLS LAST
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_adoption_by_stage(_conn, start_date, end_date, region=None):
    """Get per-stage metrics from DT_OKR_USE_CASES."""
    tf = _theater_filter(region)
    coco_cte = _coco_accounts_cte(start_date)
    is_coco = _is_coco_expanded()
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    query = f"""
    WITH {coco_cte}
    SELECT 
        uc.USE_CASE_STAGE,
        COUNT(*) AS TOTAL_USE_CASES,
        SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) AS COCO_USE_CASES,
        ROUND(SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS COCO_PCT,
        COALESCE(SUM(uc.USE_CASE_EACV), 0) AS TOTAL_EACV,
        ROUND(AVG(uc.DAYS_IN_CURRENT_STAGE), 0) AS AVG_DAYS
    FROM {DT_OKR} uc
    LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
    WHERE {date_filter}
    {tf}
    GROUP BY uc.USE_CASE_STAGE
    ORDER BY uc.USE_CASE_STAGE
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_adoption_by_region(_conn, start_date, end_date):
    """Get per-region metrics from DT_OKR_USE_CASES."""
    coco_cte = _coco_accounts_cte(start_date)
    is_coco = _is_coco_expanded()
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    query = f"""
    WITH {coco_cte}
    SELECT 
        CASE 
            WHEN uc.THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition') THEN 'NoAM'
            WHEN uc.THEATER_NAME = 'EMEA' THEN 'EMEA'
            WHEN uc.THEATER_NAME = 'APJ' THEN 'APJ'
            ELSE 'Other'
        END AS REGION,
        COUNT(*) AS TOTAL_USE_CASES,
        SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) AS COCO_USE_CASES,
        ROUND(SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS COCO_PCT,
        COALESCE(SUM(uc.USE_CASE_EACV), 0) AS TOTAL_EACV,
        COUNT(DISTINCT uc.PARTNER_NAME) AS PARTNER_COUNT
    FROM {DT_OKR} uc
    LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
    WHERE {date_filter}
    GROUP BY REGION
    ORDER BY TOTAL_EACV DESC NULLS LAST
    """
    return _conn.query(query)
@st.cache_data(ttl=timedelta(minutes=30))
def get_okr_coco_adoption(_conn, quarter_start, quarter_end, region=None):
    tf = _theater_filter(region)
    coco_cte = _coco_accounts_cte(quarter_start)
    is_coco = _is_coco_expanded()
    query = f"""
    WITH {coco_cte}
    SELECT 
        uc.PARTNER_NAME,
        uc.USE_CASE_ID,
        uc.USE_CASE_NAME,
        uc.ACCOUNT_NAME,
        uc.USE_CASE_STAGE,
        uc.USE_CASE_EACV,
        uc.TECHNICAL_USE_CASE,
        uc.THEATER_NAME,
        uc.DECISION_DATE,
        uc.GO_LIVE_DATE,
        uc.DAYS_IN_STAGE,
        CASE WHEN {is_coco} THEN TRUE ELSE FALSE END AS IS_COCO_ATTACHED,
        uc.COCO_SOURCE,
        ARRAY_TO_STRING(ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN caa.ACCOUNT_NAME_UPPER IS NOT NULL THEN 'Account Usage' END,
            CASE WHEN uc.COCO_SOURCE = 'SE_COMMENTS' THEN 'SE Comments' END,
            CASE WHEN uc.COCO_SOURCE = 'PARTNER_COMMENTS' THEN 'PSE Comments' END,
            CASE WHEN uc.COCO_SOURCE = 'FEATURE_FLAG' THEN 'Feature Flag' END
        ), ' | ') AS ATTRIBUTION_FLAGS
    FROM {DT_OKR} uc
    LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
    WHERE (
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{quarter_start}' AND uc.DECISION_DATE <= '{quarter_end}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{quarter_start}' AND uc.GO_LIVE_DATE <= '{quarter_end}')
    )
    {tf}
    ORDER BY uc.PARTNER_NAME, IS_COCO_ATTACHED DESC, uc.USE_CASE_EACV DESC NULLS LAST
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_okr_partner_summary(_conn, quarter_start, quarter_end, region=None):
    tf = _theater_filter(region)
    coco_cte = _coco_accounts_cte(quarter_start)
    is_coco = _is_coco_expanded()
    query = f"""
    WITH {coco_cte}
    SELECT 
        uc.PARTNER_NAME,
        COUNT(*) AS total_use_cases,
        SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) AS coco_use_cases,
        COUNT(*) - SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) AS non_coco_use_cases,
        ROUND(SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS coco_pct,
        SUM(uc.USE_CASE_EACV) AS total_eacv,
        SUM(CASE WHEN {is_coco} THEN uc.USE_CASE_EACV ELSE 0 END) AS coco_eacv,
        CASE WHEN SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) * 100.0 / COUNT(*) >= 50 THEN TRUE ELSE FALSE END AS MEETS_TARGET
    FROM {DT_OKR} uc
    LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
    WHERE (
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{quarter_start}' AND uc.DECISION_DATE <= '{quarter_end}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{quarter_start}' AND uc.GO_LIVE_DATE <= '{quarter_end}')
    )
    {tf}
    GROUP BY uc.PARTNER_NAME
    HAVING COUNT(*) >= 1
    ORDER BY total_use_cases DESC
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_email_summary_data(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        PARTNER_NAME,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(CASE WHEN USE_CASE_STAGE IN ('1 - Discovery', '2 - Scoping', '3 - Technical / Business Validation') THEN 1 END) AS active_pipeline,
        COUNT(CASE WHEN USE_CASE_STAGE = '4 - Use Case Won / Migration Plan' THEN 1 END) AS won,
        COUNT(CASE WHEN USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete') THEN 1 END) AS in_impl,
        COUNT(CASE WHEN USE_CASE_STAGE = '7 - Deployed' THEN 1 END) AS deployed,
        LISTAGG(DISTINCT USE_CASE_STAGE, ', ') WITHIN GROUP (ORDER BY USE_CASE_STAGE) AS stages
    FROM use_cases
    WHERE 1=1{tf}{sf}
    GROUP BY PARTNER_NAME
    ORDER BY total_eacv DESC NULLS LAST
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_distinct_partners(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT DISTINCT PARTNER_NAME 
    FROM use_cases
    WHERE 1=1{tf}{sf}
    ORDER BY PARTNER_NAME
    """
    result = _conn.query(query)
    return ["All"] + result['PARTNER_NAME'].tolist()

@st.cache_data(ttl=timedelta(minutes=30))
def get_aging_analysis(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        USE_CASE_STAGE,
        CASE 
            WHEN DAYS_IN_CURRENT_STAGE <= 14 THEN '0-14 days'
            WHEN DAYS_IN_CURRENT_STAGE <= 30 THEN '15-30 days'
            WHEN DAYS_IN_CURRENT_STAGE <= 60 THEN '31-60 days'
            WHEN DAYS_IN_CURRENT_STAGE <= 90 THEN '61-90 days'
            ELSE '90+ days'
        END AS aging_bucket,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv
    FROM use_cases
    WHERE DAYS_IN_CURRENT_STAGE IS NOT NULL{tf}{sf}
    GROUP BY USE_CASE_STAGE, aging_bucket
    ORDER BY USE_CASE_STAGE, aging_bucket
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_stalled_use_cases(_conn, days_threshold=60, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        USE_CASE_ID, PARTNER_NAME, ACCOUNT_NAME, USE_CASE_NAME, 
        USE_CASE_STAGE, USE_CASE_EACV, DAYS_IN_CURRENT_STAGE,
        ACCOUNT_LEAD_SE_NAME, COCO_MENTION_SOURCE, SE_COMMENTS, PARTNER_COMMENTS, SPECIALIST_COMMENTS
    FROM use_cases
    WHERE DAYS_IN_CURRENT_STAGE >= {days_threshold}
    AND USE_CASE_STAGE NOT IN ('7 - Deployed', '8 - Use Case Lost'){tf}{sf}
    ORDER BY DAYS_IN_CURRENT_STAGE DESC
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_comments_with_context(_conn, region=None, source=None, limit=50, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        USE_CASE_ID, PARTNER_NAME, ACCOUNT_NAME, USE_CASE_NAME,
        USE_CASE_STAGE, USE_CASE_EACV, TECHNICAL_USE_CASE,
        SE_COMMENTS, PARTNER_COMMENTS, SPECIALIST_COMMENTS, NEXT_STEPS,
        WORKLOADS, COCO_MENTION_SOURCE, DAYS_IN_CURRENT_STAGE,
        ACCOUNT_LEAD_SE_NAME, THEATER_NAME, PRIORITIZED_FEATURES
    FROM use_cases
    WHERE (SE_COMMENTS IS NOT NULL OR PARTNER_COMMENTS IS NOT NULL OR SPECIALIST_COMMENTS IS NOT NULL){tf}{sf}
    ORDER BY USE_CASE_EACV DESC NULLS LAST
    LIMIT {limit}
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_weekly_use_case_metrics(_conn, region=None, start_date=None, end_date=None):
    tf = ""
    if region and region != "Global":
        if region == "NoAM":
            tf = "WHERE THEATER_REGION = 'NoAM'"
        elif region == "EMEA":
            tf = "WHERE THEATER_REGION = 'EMEA'"
        elif region == "APJ":
            tf = "WHERE THEATER_REGION = 'APJ'"
    query = f"""
    SELECT 
        WEEK_START,
        SUM(USE_CASE_COUNT) AS USE_CASE_COUNT,
        SUM(TOTAL_EACV) AS TOTAL_EACV,
        SUM(WON) AS WON,
        SUM(DEPLOYED) AS DEPLOYED
    FROM {SCHEMA}.CEO_USE_CASE_WEEKLY_METRICS
    {tf}
    GROUP BY WEEK_START
    ORDER BY WEEK_START
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_by_region(_conn, source=None, start_date=None, end_date=None):
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        CASE 
            WHEN THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition') THEN 'NoAM'
            WHEN THEATER_NAME = 'EMEA' THEN 'EMEA'
            WHEN THEATER_NAME = 'APJ' THEN 'APJ'
            ELSE 'Other'
        END AS REGION,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(DISTINCT PARTNER_NAME) AS partner_count
    FROM use_cases
    WHERE 1=1{sf}
    GROUP BY REGION
    ORDER BY total_eacv DESC NULLS LAST
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_source_breakdown(_conn, region=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        COCO_MENTION_SOURCE,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(DISTINCT PARTNER_NAME) AS partner_count
    FROM use_cases
    WHERE 1=1{tf}
    GROUP BY COCO_MENTION_SOURCE
    ORDER BY use_case_count DESC
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_use_case_type_patterns(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        TECHNICAL_USE_CASE,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(DISTINCT PARTNER_NAME) AS partner_count,
        COUNT(CASE WHEN USE_CASE_STAGE IN ('4 - Use Case Won / Migration Plan', '5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') THEN 1 END) AS won_plus,
        LISTAGG(DISTINCT PARTNER_NAME, ', ') WITHIN GROUP (ORDER BY PARTNER_NAME) AS partners_involved
    FROM use_cases
    WHERE TECHNICAL_USE_CASE IS NOT NULL{tf}{sf}
    GROUP BY TECHNICAL_USE_CASE
    ORDER BY use_case_count DESC
    LIMIT 15
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_workload_patterns(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        WORKLOADS,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(DISTINCT PARTNER_NAME) AS partner_count
    FROM use_cases
    WHERE WORKLOADS IS NOT NULL AND TRIM(WORKLOADS) != ''{tf}{sf}
    GROUP BY WORKLOADS
    ORDER BY use_case_count DESC
    LIMIT 15
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_competitive_landscape(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        COMPETITORS,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(DISTINCT PARTNER_NAME) AS partner_count
    FROM use_cases
    WHERE COMPETITORS IS NOT NULL AND TRIM(COMPETITORS) != ''{tf}{sf}
    GROUP BY COMPETITORS
    ORDER BY use_case_count DESC
    LIMIT 12
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_comment_narratives(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        PARTNER_NAME, ACCOUNT_NAME, USE_CASE_NAME, USE_CASE_STAGE, USE_CASE_EACV,
        TECHNICAL_USE_CASE, WORKLOADS, COMPETITORS,
        SUBSTR(SE_COMMENTS, 1, 600) AS SE_COMMENTS_EXCERPT,
        SUBSTR(PARTNER_COMMENTS, 1, 600) AS PARTNER_COMMENTS_EXCERPT,
        SUBSTR(SPECIALIST_COMMENTS, 1, 400) AS SPECIALIST_COMMENTS_EXCERPT,
        SUBSTR(MEDDPICC_IDENTIFY_PAIN, 1, 300) AS CUSTOMER_PAIN,
        COCO_MENTION_SOURCE, DAYS_IN_CURRENT_STAGE
    FROM use_cases
    WHERE (SE_COMMENTS IS NOT NULL OR PARTNER_COMMENTS IS NOT NULL OR SPECIALIST_COMMENTS IS NOT NULL){tf}{sf}
    ORDER BY USE_CASE_EACV DESC NULLS LAST
    LIMIT 30
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_partner_workload_cross(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        PARTNER_NAME,
        COUNT(CASE WHEN WORKLOADS ILIKE '%AI%' THEN 1 END) AS ai_use_cases,
        COUNT(CASE WHEN WORKLOADS ILIKE '%Data Engineering%' THEN 1 END) AS de_use_cases,
        COUNT(CASE WHEN WORKLOADS ILIKE '%Analytics%' THEN 1 END) AS analytics_use_cases,
        COUNT(CASE WHEN WORKLOADS ILIKE '%Platform%' THEN 1 END) AS platform_use_cases,
        COUNT(CASE WHEN WORKLOADS ILIKE '%Applications%' THEN 1 END) AS apps_use_cases,
        COUNT(*) AS total_use_cases,
        SUM(USE_CASE_EACV) AS total_eacv
    FROM use_cases
    WHERE 1=1{tf}{sf}
    GROUP BY PARTNER_NAME
    ORDER BY total_eacv DESC NULLS LAST
    LIMIT 15
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_regional_themes(_conn, source=None, start_date=None, end_date=None):
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        CASE 
            WHEN THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition') THEN 'NoAM'
            WHEN THEATER_NAME = 'EMEA' THEN 'EMEA'
            WHEN THEATER_NAME = 'APJ' THEN 'APJ'
            ELSE 'Other'
        END AS REGION,
        TECHNICAL_USE_CASE,
        WORKLOADS,
        COMPETITORS,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(DISTINCT PARTNER_NAME) AS partner_count,
        LISTAGG(DISTINCT PARTNER_NAME, ', ') WITHIN GROUP (ORDER BY PARTNER_NAME) AS partners_involved,
        COUNT(CASE WHEN USE_CASE_STAGE IN ('4 - Use Case Won / Migration Plan', '5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') THEN 1 END) AS won_plus,
        COUNT(CASE WHEN USE_CASE_STAGE = '7 - Deployed' THEN 1 END) AS deployed_count
    FROM use_cases
    WHERE 1=1{sf}
    GROUP BY REGION, TECHNICAL_USE_CASE, WORKLOADS, COMPETITORS
    ORDER BY REGION, total_eacv DESC NULLS LAST
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_regional_comment_narratives(_conn, target_region, source=None, start_date=None, end_date=None):
    sf = _source_filter(source or "")
    region_cond = ""
    if target_region == "NoAM":
        region_cond = " AND THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition')"
    elif target_region == "EMEA":
        region_cond = " AND THEATER_NAME = 'EMEA'"
    elif target_region == "APJ":
        region_cond = " AND THEATER_NAME = 'APJ'"
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        PARTNER_NAME, ACCOUNT_NAME, USE_CASE_NAME, USE_CASE_STAGE, USE_CASE_EACV,
        TECHNICAL_USE_CASE, WORKLOADS, COMPETITORS,
        SUBSTR(SE_COMMENTS, 1, 400) AS SE_COMMENTS_EXCERPT,
        SUBSTR(PARTNER_COMMENTS, 1, 400) AS PARTNER_COMMENTS_EXCERPT,
        COCO_MENTION_SOURCE
    FROM use_cases
    WHERE (SE_COMMENTS IS NOT NULL OR PARTNER_COMMENTS IS NOT NULL){sf}{region_cond}
    ORDER BY USE_CASE_EACV DESC NULLS LAST
    LIMIT 10
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_partner_coco_coverage(_conn, region=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    effective_start = start_date or '2025-11-20'
    coco_cte = _coco_accounts_cte(effective_start)
    is_coco = _is_coco_expanded()
    if start_date and end_date:
        date_filter = f"""(
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
        )"""
    else:
        date_filter = """(
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE > '2025-11-20')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE > '2025-11-20')
        )"""
    query = f"""
    WITH {coco_cte}
    SELECT 
        uc.PARTNER_NAME,
        COUNT(*) AS TOTAL_PARTNER_UCS,
        SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) AS COCO_UCS,
        ROUND(SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS COCO_PCT
    FROM {DT_OKR} uc
    LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
    WHERE {date_filter}
    {tf}
    GROUP BY uc.PARTNER_NAME
    HAVING COUNT(*) >= 1
    ORDER BY TOTAL_PARTNER_UCS DESC
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_okr_stage_breakdown(_conn, region=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    effective_start = start_date or '2025-11-20'
    coco_cte = _coco_accounts_cte(effective_start)
    is_coco = _is_coco_expanded()
    if start_date and end_date:
        date_filter = f"""(
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
        )"""
    else:
        date_filter = """(
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE > '2025-11-20')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE > '2025-11-20')
        )"""
    query = f"""
    WITH {coco_cte}
    SELECT 
        uc.PARTNER_NAME,
        uc.USE_CASE_STAGE,
        COUNT(*) AS TOTAL_UCS,
        SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) AS COCO_UCS,
        ROUND(SUM(CASE WHEN {is_coco} THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS COCO_PCT,
        SUM(uc.USE_CASE_EACV) AS TOTAL_EACV,
        SUM(CASE WHEN {is_coco} THEN uc.USE_CASE_EACV ELSE 0 END) AS COCO_EACV
    FROM {DT_OKR} uc
    LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
    WHERE {date_filter}
    {tf}
    GROUP BY uc.PARTNER_NAME, uc.USE_CASE_STAGE
    ORDER BY uc.PARTNER_NAME, uc.USE_CASE_STAGE
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_partner_credit_consumption(_conn, partners, start_date, end_date=None):
    """Get CoCo credit consumption per partner on customer accounts with Q2-dated use cases."""
    partners_sql = "','".join(partners)
    ed = end_date or start_date
    query = f"""
    WITH partner_customer_accounts AS (
        SELECT DISTINCT PARTNER_NAME, UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
        FROM {DT_OKR}
        WHERE PARTNER_NAME IN ('{partners_sql}')
        AND (
            (USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND DECISION_DATE >= '{start_date}' AND DECISION_DATE <= '{ed}')
            OR (USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND GO_LIVE_DATE >= '{start_date}' AND GO_LIVE_DATE <= '{ed}')
        )
    ),
    daily_credits AS (
        SELECT f.ds, pca.PARTNER_NAME, pca.ACCOUNT_NAME_UPPER,
            SUM(f.TOTAL_TOKEN_CREDITS) AS credits
        FROM snowscience.llm.cortex_code_user_day_fact f
        INNER JOIN partner_customer_accounts pca ON UPPER(f.salesforce_account_name) = pca.ACCOUNT_NAME_UPPER
        WHERE f.ds >= '{start_date}' AND f.snowflake_account_type = 'Customer' AND f.total_daily_requests > 0
        GROUP BY f.ds, pca.PARTNER_NAME, pca.ACCOUNT_NAME_UPPER
    )
    SELECT PARTNER_NAME,
        ROUND(SUM(credits), 2) AS Q2_TOTAL_CREDITS,
        COUNT(DISTINCT ACCOUNT_NAME_UPPER) AS COCO_CUSTOMER_ACCOUNTS,
        COUNT(DISTINCT ds) AS ACTIVE_DAYS,
        CASE 
            WHEN AVG(CASE WHEN ds >= DATEADD('day', -14, CURRENT_DATE()) AND ds < DATEADD('day', -7, CURRENT_DATE()) THEN credits END) > 0
            THEN ROUND((AVG(CASE WHEN ds >= DATEADD('day', -7, CURRENT_DATE()) THEN credits END) - AVG(CASE WHEN ds >= DATEADD('day', -14, CURRENT_DATE()) AND ds < DATEADD('day', -7, CURRENT_DATE()) THEN credits END)) / AVG(CASE WHEN ds >= DATEADD('day', -14, CURRENT_DATE()) AND ds < DATEADD('day', -7, CURRENT_DATE()) THEN credits END) * 100, 1)
            ELSE NULL
        END AS WOW_PCT
    FROM daily_credits
    GROUP BY PARTNER_NAME
    ORDER BY Q2_TOTAL_CREDITS DESC NULLS LAST
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_by_account_gvp(_conn, region=None, source=None, start_date=None, end_date=None):
    tf = _theater_filter(region)
    sf = _source_filter(source or "")
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT 
        ACCOUNT_GVP,
        COUNT(*) AS use_case_count,
        SUM(USE_CASE_EACV) AS total_eacv,
        COUNT(DISTINCT PARTNER_NAME) AS partner_count
    FROM use_cases
    WHERE ACCOUNT_GVP IS NOT NULL{tf}{sf}
    GROUP BY ACCOUNT_GVP
    ORDER BY total_eacv DESC NULLS LAST
    LIMIT 15
    """
    return _conn.query(query)
