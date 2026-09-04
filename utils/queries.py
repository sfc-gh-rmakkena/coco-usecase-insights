import streamlit as st
from datetime import timedelta
from utils.config import get_schema

SCHEMA = get_schema()
DT_OKR = f"{SCHEMA}.DT_OKR_USE_CASES"

# Q3 FY27 snapshot tables (fresh start Aug 1 2026)
_OKR_TARGET_TABLE   = f"{SCHEMA}.COCO_OKR_TARGET_WEEKLY_Q3"
_SNAPSHOT_TABLE     = f"{SCHEMA}.IS_COCO_FINAL_WEEKLY_SNAPSHOT_Q3"

def _use_case_base(start_date=None, end_date=None):
    """Generate USE_CASE_BASE CTE.
    Drives partner resolution + IS_COCO from DT_OKR_USE_CASES; enriches with
    MDM comments/flags via USE_CASE_ID join.
    """
    if start_date and end_date:
        date_filter = f"""(
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan')
             AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed')
             AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
        )"""
    else:
        date_filter = """(
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan')
             AND uc.DECISION_DATE > '2025-11-20')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed')
             AND uc.GO_LIVE_DATE > '2025-11-20')
        )"""
    return f"""
    WITH use_cases AS (
        SELECT
            uc.PARTNER_NAME,
            uc.USE_CASE_ID,
            uc.USE_CASE_NUMBER,
            uc.ACCOUNT_NAME,
            uc.USE_CASE_NAME,
            uc.USE_CASE_STAGE,
            uc.USE_CASE_EACV,
            uc.TECHNICAL_USE_CASE,
            uc.ACCOUNT_LEAD_SE_NAME,
            uc.ACCOUNT_GVP,
            uc.THEATER_NAME,
            uc.REGION_NAME,
            uc.DECISION_DATE,
            uc.GO_LIVE_DATE,
            uc.DAYS_IN_STAGE,
            uc.DAYS_IN_CURRENT_STAGE,
            uc.WORKLOADS,
            uc.COMPETITORS,
            uc.IS_COCO,
            uc.COCO_SOURCE AS COCO_MENTION_SOURCE,
            -- Enrich with MDM for comment/flag fields not in DT_OKR
            mdm.SE_COMMENTS,
            mdm.PARTNER_COMMENTS,
            mdm.SPECIALIST_COMMENTS,
            mdm.NEXT_STEPS,
            mdm.PRIORITIZED_FEATURES,
            mdm.MEDDPICC_METRICS,
            mdm.MEDDPICC_IDENTIFY_PAIN,
            TRY_CAST(mdm.ACCOUNT_BASE_RENEWAL_ACV AS FLOAT) AS ACCOUNT_ARR,
            mdm.IS_WON,
            mdm.IS_DEPLOYED,
            mdm.IS_LOST,
            mdm.CREATED_DATE,
            mdm.ACTUAL_USE_CASE_WON_DATE,
            mdm.ACTUAL_USE_CASE_DEPLOYMENT_DATE,
            mdm.LOSS_DATE
        FROM {DT_OKR} uc
        LEFT JOIN MDM.MDM_INTERFACES.DIM_USE_CASE mdm ON uc.USE_CASE_ID = mdm.USE_CASE_ID
        WHERE {date_filter}
    )
"""

# Keep backward-compatible constant for any remaining direct references
USE_CASE_BASE = _use_case_base()

def _theater_filter(region: str) -> str:
    _noam = ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec')
    if not region or region == "Global":
        return ""
    elif region in _noam:
        # Theater-level filter (effective_region = theater name)
        return f" AND THEATER_NAME = '{region}'"
    elif region == "NoAM":
        return " AND THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec')"
    elif region == "EMEA":
        return " AND THEATER_NAME = 'EMEA'"
    elif region == "APJ":
        return " AND THEATER_NAME = 'APJ'"
    elif region == "LATAM":
        return " AND REGION_NAME = 'LATAM'"
    return ""

def _subregion_filter(subregions) -> str:
    """Additional REGION_NAME filter applied after the theater filter.
    subregions: list/tuple of REGION_NAME values, or empty/None for no restriction."""
    if not subregions:
        return ""
    escaped = "','".join(str(s).replace("'", "''") for s in subregions)
    return f" AND uc.REGION_NAME IN ('{escaped}')"

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

def _coco_accounts_cte(start_date, include_account_coco=True, confidence=None):
    """No-op CTE placeholder. IS_COCO_FINAL is now applied in Python via bulk_conf.
    Kept for SQL structural compatibility only — returns no rows.
    """
    return "coco_active_accounts AS (SELECT NULL::VARCHAR AS ACCOUNT_NAME_UPPER WHERE FALSE)"

def _is_coco_expanded():
    """SQL expression for CoCo detection using the pre-computed DT_OKR flag.
    IS_COCO_FINAL (IS_COCO + High confidence band) is applied in Python via bulk_conf.
    """
    return "uc.IS_COCO"

@st.cache_data(ttl=timedelta(minutes=30))
def get_all_uc_counts(_conn, start_date: str, end_date: str, region: str = None):
    """All use cases (partner + non-partner) total and go-live counts from DIM_USE_CASE."""
    theater_cond = ""
    if region and region not in ("Global", ""):
        region_map = {
            "NoAM": ("AMSExpansion","USMajors","AMSAcquisition","USPubSec"),
            "EMEA": ("EMEA",), "APJ": ("APJ",),
        }
        theaters = region_map.get(region)
        if theaters:
            t = "','".join(theaters)
            theater_cond = f" AND THEATER_NAME IN ('{t}')"
    return _conn.query(f"""
    SELECT
        COUNT(*)                                                        AS ALL_USE_CASES,
        SUM(CASE WHEN IS_PARTNER_ATTACHED THEN 1 ELSE 0 END)           AS PARTNER_ATTACHED,
        SUM(CASE WHEN USE_CASE_STAGE = '7 - Deployed'
                  AND GO_LIVE_DATE >= '{start_date}'
                  AND GO_LIVE_DATE <= '{end_date}' THEN 1 ELSE 0 END)  AS ALL_GO_LIVES
    FROM MDM.MDM_INTERFACES.DIM_USE_CASE
    WHERE USE_CASE_STAGE IN (
        '3 - Technical / Business Validation',
        '4 - Use Case Won / Migration Plan',
        '5 - Implementation In Progress',
        '6 - Implementation Complete',
        '7 - Deployed'
    )
    AND (
        (USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
         AND DECISION_DATE >= '{start_date}' AND DECISION_DATE <= '{end_date}')
        OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
         AND GO_LIVE_DATE >= '{start_date}' AND GO_LIVE_DATE <= '{end_date}')
    )
    {theater_cond}
    """)


@st.cache_data(ttl=timedelta(minutes=30))
def get_all_uc_counts_by_theatre(_conn, start_date: str, end_date: str):
    """Overall UCs and go-live counts from MDM broken down by THEATER_NAME."""
    return _conn.query(f"""
    SELECT
        THEATER_NAME,
        COUNT(*)                                                                  AS ALL_USE_CASES,
        SUM(CASE WHEN USE_CASE_STAGE = '7 - Deployed'
                  AND GO_LIVE_DATE >= '{start_date}'
                  AND GO_LIVE_DATE <= '{end_date}' THEN 1 ELSE 0 END)            AS ALL_GO_LIVES
    FROM MDM.MDM_INTERFACES.DIM_USE_CASE
    WHERE THEATER_NAME IS NOT NULL
      AND USE_CASE_STAGE IN (
          '3 - Technical / Business Validation','4 - Use Case Won / Migration Plan',
          '5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
      AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
            AND DECISION_DATE >= '{start_date}' AND DECISION_DATE <= '{end_date}')
           OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
            AND GO_LIVE_DATE >= '{start_date}' AND GO_LIVE_DATE <= '{end_date}'))
    GROUP BY THEATER_NAME
    ORDER BY ALL_USE_CASES DESC
    """)


@st.cache_data(ttl=timedelta(minutes=30))
def get_partner_metrics_by_theatre(_conn, start_date, end_date, include_account_coco=True, confidence=None):
    """Partner UC counts, CoCo UCs, and go-live % from DT_OKR broken down by THEATER_NAME.
    Uses uc.IS_COCO (pre-computed DT_OKR flag) for consistency with the top-bar metric.
    """
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
         AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
         AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    return _conn.query(f"""
    SELECT
        uc.THEATER_NAME,
        COUNT(*)                                                                                          AS TOTAL_PARTNER_UCS,
        SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END)                                                      AS COCO_UCS,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND uc.IS_COCO THEN 1 ELSE 0 END)               AS DEPLOYED_COCO,
        ROUND(SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND uc.IS_COCO THEN 1 ELSE 0 END)
              * 100.0 / NULLIF(COUNT(*), 0), 1)                                                           AS GO_LIVE_PCT
    FROM {DT_OKR} uc
    WHERE {date_filter}
      AND uc.THEATER_NAME IS NOT NULL
    GROUP BY uc.THEATER_NAME
    ORDER BY TOTAL_PARTNER_UCS DESC
    """)


@st.cache_data(ttl=timedelta(minutes=30))
def get_all_uc_counts_by_region(_conn, start_date: str, end_date: str):
    """Overall UCs and go-live counts from MDM broken down by macro-region (NoAM/EMEA/APJ)."""
    return _conn.query(f"""
    SELECT
        CASE
            WHEN THEATER_NAME IN ('AMSExpansion','USMajors','AMSAcquisition','USPubSec') THEN 'NoAM'
            WHEN THEATER_NAME = 'EMEA' THEN 'EMEA'
            WHEN THEATER_NAME = 'APJ'  THEN 'APJ'
            ELSE 'Other'
        END AS REGION,
        COUNT(*)                                                                  AS ALL_USE_CASES,
        SUM(CASE WHEN USE_CASE_STAGE = '7 - Deployed'
                  AND GO_LIVE_DATE >= '{start_date}'
                  AND GO_LIVE_DATE <= '{end_date}' THEN 1 ELSE 0 END)            AS ALL_GO_LIVES
    FROM MDM.MDM_INTERFACES.DIM_USE_CASE
    WHERE USE_CASE_STAGE IN (
          '3 - Technical / Business Validation','4 - Use Case Won / Migration Plan',
          '5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
      AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
            AND DECISION_DATE >= '{start_date}' AND DECISION_DATE <= '{end_date}')
           OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
            AND GO_LIVE_DATE >= '{start_date}' AND GO_LIVE_DATE <= '{end_date}'))
    GROUP BY REGION
    ORDER BY ALL_USE_CASES DESC
    """)


@st.cache_data(ttl=timedelta(minutes=30))
def get_partner_metrics_by_region(_conn, start_date, end_date, include_account_coco=True, confidence=None):
    """Partner UC counts, CoCo UCs, and go-live % from DT_OKR broken down by macro-region.
    Uses uc.IS_COCO (pre-computed DT_OKR flag) for consistency with the top-bar metric.
    """
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
         AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
         AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    return _conn.query(f"""
    SELECT
        CASE
            WHEN uc.THEATER_NAME IN ('AMSExpansion','USMajors','AMSAcquisition','USPubSec') THEN 'NoAM'
            WHEN uc.THEATER_NAME = 'EMEA' THEN 'EMEA'
            WHEN uc.THEATER_NAME = 'APJ'  THEN 'APJ'
            ELSE 'Other'
        END AS REGION,
        COUNT(*)                                                                                          AS TOTAL_PARTNER_UCS,
        SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END)                                                      AS COCO_UCS,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND uc.IS_COCO THEN 1 ELSE 0 END)               AS DEPLOYED_COCO,
        ROUND(SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND uc.IS_COCO THEN 1 ELSE 0 END)
              * 100.0 / NULLIF(COUNT(*), 0), 1)                                                           AS GO_LIVE_PCT
    FROM {DT_OKR} uc
    WHERE {date_filter}
    GROUP BY REGION
    ORDER BY TOTAL_PARTNER_UCS DESC
    """)


def get_adoption_overview(_conn, start_date, end_date, region=None, partners=None, include_account_coco=True, confidence=None, subregions=None):
    """Get adoption metrics from DT_OKR_USE_CASES for the Overview page."""
    tf = _theater_filter(region)
    srf = _subregion_filter(subregions)
    coco_cte = _coco_accounts_cte(start_date, include_account_coco, confidence)
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
    {tf}{srf}{partner_filter}
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_adoption_by_partner(_conn, start_date, end_date, region=None, include_account_coco=True, confidence=None):
    """Get per-partner metrics from DT_OKR_USE_CASES."""
    tf = _theater_filter(region)
    coco_cte = _coco_accounts_cte(start_date, include_account_coco, confidence)
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
def get_adoption_by_stage(_conn, start_date, end_date, region=None, include_account_coco=True, confidence=None):
    """Get per-stage metrics from DT_OKR_USE_CASES."""
    tf = _theater_filter(region)
    coco_cte = _coco_accounts_cte(start_date, include_account_coco, confidence)
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
def get_adoption_by_region(_conn, start_date, end_date, include_account_coco=True, confidence=None):
    """Get per-region metrics from DT_OKR_USE_CASES."""
    coco_cte = _coco_accounts_cte(start_date, include_account_coco, confidence)
    is_coco = _is_coco_expanded()
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    query = f"""
    WITH {coco_cte}
    SELECT 
        CASE 
            WHEN uc.THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec') THEN 'NoAM'
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

_GSI_PARTNERS_SQL = (
    "'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',"
    "'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting'"
)
_NOAM_RSI_PARTNERS_SQL = (
    "'7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai','Kipi.ai',"
    "'evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP',"
    "'LTM','LTI Mindtree','phData, Inc.','Slalom, LLC.','Squadron Data Inc','Tredence Inc.',"
    "'Spaulding Ridge','TEKsystems Global Services, LLC.','Blend360, LLC',"
    "'Tiger Analytics Inc.','Atrium','Perficient Inc.','SDK Tek Services Ltd.',"
    "'Merkle','Archetype Consulting','Everforth Apex Systems','Tata Consultancy Services',"
    "'OneSix','Icon Analytics','Sparq Holdings, Inc.','CitiusTech Inc.','Hexaware Technologies'"
)

_RSI_STAGE_COLS = """
        COUNT(*)                                                    AS TOTAL_UCS,
        SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END)                AS COCO_UCS,
        ROUND(SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END) * 100.0
              / NULLIF(COUNT(*), 0), 1)                             AS COCO_PCT,
        -- Kept for backward compat (stages 3+4, 5, 6+7)
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan') AND uc.IS_COCO THEN 1 ELSE 0 END) AS VALIDATION_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '5 - Implementation In Progress' AND uc.IS_COCO THEN 1 ELSE 0 END) AS IN_PROGRESS_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('6 - Implementation Complete','7 - Deployed') AND uc.IS_COCO THEN 1 ELSE 0 END) AS IMPL_COMPLETE_DEPLOYED_COCO,
        -- Individual stage CoCo counts for funnel view
        SUM(CASE WHEN uc.USE_CASE_STAGE = '3 - Technical / Business Validation' AND uc.IS_COCO THEN 1 ELSE 0 END) AS S3_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '4 - Use Case Won / Migration Plan'   AND uc.IS_COCO THEN 1 ELSE 0 END) AS S4_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '5 - Implementation In Progress'      AND uc.IS_COCO THEN 1 ELSE 0 END) AS S5_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '6 - Implementation Complete'         AND uc.IS_COCO THEN 1 ELSE 0 END) AS S6_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed'                        AND uc.IS_COCO THEN 1 ELSE 0 END) AS S7_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' THEN 1 ELSE 0 END)       AS DEPLOYED_ALL,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND uc.IS_COCO THEN 1 ELSE 0 END) AS DEPLOYED_COCO,
        COALESCE(SUM(uc.USE_CASE_EACV), 0)                                         AS TOTAL_EACV,
        COALESCE(SUM(CASE WHEN uc.IS_COCO THEN uc.USE_CASE_EACV ELSE 0 END), 0)   AS COCO_EACV"""

@st.cache_data(ttl=timedelta(minutes=30))
def get_gsi_adoption(_conn, start_date: str, end_date: str, theaters: tuple = None):
    """Per-partner CoCo adoption for the 6 GSIs — global scope by default, theater-filtered when region is selected."""
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
         AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
         AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    theater_clause = f"AND uc.THEATER_NAME IN ({','.join(repr(t) for t in theaters)})" if theaters else ""
    return _conn.query(f"""
    SELECT
        CASE
            WHEN uc.PARTNER_NAME IN ('EY','Ernst & Young (EY)')          THEN 'EY'
            WHEN uc.PARTNER_NAME IN ('IBM','IBM Consulting')              THEN 'IBM'
            ELSE uc.PARTNER_NAME
        END                                                         AS PARTNER_LABEL,
        {_RSI_STAGE_COLS}
    FROM {DT_OKR} uc
    WHERE {date_filter}
      AND uc.PARTNER_NAME IN ({_GSI_PARTNERS_SQL})
      {theater_clause}
    GROUP BY PARTNER_LABEL
    ORDER BY PARTNER_LABEL
    """)

@st.cache_data(ttl=timedelta(minutes=30))
def get_noam_rsi_adoption(_conn, start_date: str, end_date: str, theaters: tuple = None):
    """Per-partner CoCo adoption for NOAM RSIs — NoAM theaters only (or subset if theaters provided)."""
    _noam_theaters = theaters if theaters else ('AMSExpansion','USMajors','AMSAcquisition','USPubSec')
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
         AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
         AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    return _conn.query(f"""
    SELECT
        CASE
            WHEN uc.PARTNER_NAME IN ('LTM','LTI Mindtree') THEN 'LTM'
            WHEN uc.PARTNER_NAME IN ('kipi.ai','Kipi.ai')  THEN 'kipi.ai'
            ELSE uc.PARTNER_NAME
        END                                                         AS PARTNER_LABEL,
        {_RSI_STAGE_COLS}
    FROM {DT_OKR} uc
    WHERE {date_filter}
      AND uc.PARTNER_NAME IN ({_NOAM_RSI_PARTNERS_SQL})
      AND uc.THEATER_NAME IN ({','.join(repr(t) for t in _noam_theaters)})
    GROUP BY PARTNER_LABEL
    ORDER BY TOTAL_UCS DESC
    """)

@st.cache_data(ttl=timedelta(minutes=30))
def get_apj_rsi_adoption(_conn, start_date: str, end_date: str):
    """Per-partner CoCo adoption for the 5 APJ RSIs, each restricted to their assigned REGION_NAME.
    Returns one row per canonical partner label with IS_COCO-based counts.
    IS_COCO_FINAL enrichment is applied in Python by the caller via bulk_conf.
    """
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
         AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
         AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    return _conn.query(f"""
    SELECT
        CASE
            WHEN uc.PARTNER_NAME = 'NTT DATA Group Corporation'                         THEN 'NTT Data'
            WHEN uc.PARTNER_NAME = 'MegazoneCloud Corporation'                          THEN 'Megazone'
            WHEN uc.PARTNER_NAME IN ('Infinite Lambda Limited','Infinite Lambda Inc',
                                     'INFINITE LAMBDA (SINGAPORE) PTE. LTD.')           THEN 'Infinite Lambda'
            WHEN uc.PARTNER_NAME IN ('Altis Global Limited','Altis Consulting, ANZ')    THEN 'Altis'
            WHEN uc.PARTNER_NAME = 'PROLIM Global Corporation'                          THEN 'Prolim'
        END                                                         AS PARTNER_LABEL,
        uc.REGION_NAME                                              AS COUNTRY,
        COUNT(*)                                                    AS TOTAL_UCS,
        SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END)                AS COCO_UCS,
        ROUND(SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END) * 100.0
              / NULLIF(COUNT(*), 0), 1)                             AS COCO_PCT,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan') AND uc.IS_COCO THEN 1 ELSE 0 END) AS VALIDATION_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '5 - Implementation In Progress' AND uc.IS_COCO THEN 1 ELSE 0 END) AS IN_PROGRESS_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('6 - Implementation Complete','7 - Deployed') AND uc.IS_COCO THEN 1 ELSE 0 END) AS IMPL_COMPLETE_DEPLOYED_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' THEN 1 ELSE 0 END)       AS DEPLOYED_ALL,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND uc.IS_COCO THEN 1 ELSE 0 END) AS DEPLOYED_COCO,
        COALESCE(SUM(uc.USE_CASE_EACV), 0)                                         AS TOTAL_EACV,
        COALESCE(SUM(CASE WHEN uc.IS_COCO THEN uc.USE_CASE_EACV ELSE 0 END), 0)   AS COCO_EACV
    FROM {DT_OKR} uc
    WHERE {date_filter}
      AND (
          (uc.PARTNER_NAME = 'NTT DATA Group Corporation'                          AND uc.REGION_NAME = 'Japan')
          OR (uc.PARTNER_NAME = 'MegazoneCloud Corporation'                        AND uc.REGION_NAME = 'Korea')
          OR (uc.PARTNER_NAME IN ('Infinite Lambda Limited','Infinite Lambda Inc',
                                  'INFINITE LAMBDA (SINGAPORE) PTE. LTD.')         AND uc.REGION_NAME = 'ASEAN')
          OR (uc.PARTNER_NAME IN ('Altis Global Limited','Altis Consulting, ANZ')  AND uc.REGION_NAME = 'ANZ')
          OR (uc.PARTNER_NAME = 'PROLIM Global Corporation'                        AND uc.REGION_NAME = 'India')
      )
    GROUP BY PARTNER_LABEL, uc.REGION_NAME
    ORDER BY PARTNER_LABEL
    """)

@st.cache_data(ttl=timedelta(minutes=30))
def get_emea_rsi_adoption(_conn, start_date: str, end_date: str):
    """Per-partner CoCo adoption for the 4 EMEA RSIs, each restricted to their assigned REGION_NAME.
    Infomotion→CentralEMEA | Civica→SouthEMEA | Kubrick→UK | KPC→SouthEMEA
    """
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
         AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
         AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    return _conn.query(f"""
    SELECT
        CASE
            WHEN uc.PARTNER_NAME ILIKE '%Infomotion%'  THEN 'Infomotion'
            WHEN uc.PARTNER_NAME ILIKE '%Civica%'      THEN 'Civica'
            WHEN uc.PARTNER_NAME ILIKE '%Kubrick%'     THEN 'Kubrick'
            WHEN uc.PARTNER_NAME ILIKE '%KPC%'         THEN 'KPC'
        END                                                         AS PARTNER_LABEL,
        uc.REGION_NAME                                              AS COUNTRY,
        COUNT(*)                                                    AS TOTAL_UCS,
        SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END)                AS COCO_UCS,
        ROUND(SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END) * 100.0
              / NULLIF(COUNT(*), 0), 1)                             AS COCO_PCT,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan') AND uc.IS_COCO THEN 1 ELSE 0 END) AS VALIDATION_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '5 - Implementation In Progress' AND uc.IS_COCO THEN 1 ELSE 0 END) AS IN_PROGRESS_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('6 - Implementation Complete','7 - Deployed') AND uc.IS_COCO THEN 1 ELSE 0 END) AS IMPL_COMPLETE_DEPLOYED_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' THEN 1 ELSE 0 END)       AS DEPLOYED_ALL,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND uc.IS_COCO THEN 1 ELSE 0 END) AS DEPLOYED_COCO,
        COALESCE(SUM(uc.USE_CASE_EACV), 0)                                         AS TOTAL_EACV,
        COALESCE(SUM(CASE WHEN uc.IS_COCO THEN uc.USE_CASE_EACV ELSE 0 END), 0)   AS COCO_EACV
    FROM {DT_OKR} uc
    WHERE {date_filter}
      AND (
          (uc.PARTNER_NAME ILIKE '%Infomotion%' AND uc.REGION_NAME = 'CentralEMEA')
          OR (uc.PARTNER_NAME ILIKE '%Civica%'  AND uc.REGION_NAME = 'SouthEMEA')
          OR (uc.PARTNER_NAME ILIKE '%Kubrick%' AND uc.REGION_NAME = 'UK')
          OR (uc.PARTNER_NAME ILIKE '%KPC%'     AND uc.REGION_NAME = 'SouthEMEA')
      )
    GROUP BY PARTNER_LABEL, uc.REGION_NAME
    ORDER BY PARTNER_LABEL
    """)

@st.cache_data(ttl=timedelta(minutes=30))
def get_latam_rsi_adoption(_conn, start_date: str, end_date: str):
    """Per-partner CoCo adoption for the 5 LATAM RSIs, all restricted to REGION_NAME = 'LATAM'.
    Viewnear | EgosBi | IVCISA | Seidor | Keyrus
    """
    date_filter = f"""(
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
         AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
         AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
    )"""
    return _conn.query(f"""
    SELECT
        CASE
            WHEN uc.PARTNER_NAME ILIKE '%Viewnear%'                        THEN 'Viewnear'
            WHEN uc.PARTNER_NAME ILIKE '%EGOS BI%'                         THEN 'EgosBi'
            WHEN uc.PARTNER_NAME ILIKE '%IVCISA%'                          THEN 'IVCISA'
            WHEN uc.PARTNER_NAME ILIKE '%SEIDOR ANALYTICS%'                THEN 'Seidor'
            WHEN uc.PARTNER_NAME ILIKE '%Keyrus Brasil%'                   THEN 'Keyrus'
        END                                                         AS PARTNER_LABEL,
        uc.REGION_NAME                                              AS COUNTRY,
        COUNT(*)                                                    AS TOTAL_UCS,
        SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END)                AS COCO_UCS,
        ROUND(SUM(CASE WHEN uc.IS_COCO THEN 1 ELSE 0 END) * 100.0
              / NULLIF(COUNT(*), 0), 1)                             AS COCO_PCT,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan') AND uc.IS_COCO THEN 1 ELSE 0 END) AS VALIDATION_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '5 - Implementation In Progress' AND uc.IS_COCO THEN 1 ELSE 0 END) AS IN_PROGRESS_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE IN ('6 - Implementation Complete','7 - Deployed') AND uc.IS_COCO THEN 1 ELSE 0 END) AS IMPL_COMPLETE_DEPLOYED_COCO,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' THEN 1 ELSE 0 END)       AS DEPLOYED_ALL,
        SUM(CASE WHEN uc.USE_CASE_STAGE = '7 - Deployed' AND uc.IS_COCO THEN 1 ELSE 0 END) AS DEPLOYED_COCO,
        COALESCE(SUM(uc.USE_CASE_EACV), 0)                                         AS TOTAL_EACV,
        COALESCE(SUM(CASE WHEN uc.IS_COCO THEN uc.USE_CASE_EACV ELSE 0 END), 0)   AS COCO_EACV
    FROM {DT_OKR} uc
    WHERE {date_filter}
      AND uc.REGION_NAME = 'LATAM'
      AND (
          uc.PARTNER_NAME ILIKE '%Viewnear%'
          OR uc.PARTNER_NAME ILIKE '%EGOS BI%'
          OR uc.PARTNER_NAME ILIKE '%IVCISA%'
          OR uc.PARTNER_NAME ILIKE '%SEIDOR ANALYTICS%'
          OR uc.PARTNER_NAME ILIKE '%Keyrus Brasil%'
      )
    GROUP BY PARTNER_LABEL, uc.REGION_NAME
    ORDER BY PARTNER_LABEL
    """)

@st.cache_data(ttl=timedelta(minutes=30))
def get_okr_coco_adoption(_conn, quarter_start, quarter_end, region=None, include_account_coco=True, confidence=None, subregions=None):
    tf = _theater_filter(region)
    srf = _subregion_filter(subregions)
    coco_cte = _coco_accounts_cte(quarter_start, include_account_coco, confidence)
    is_coco = _is_coco_expanded()
    query = f"""
    WITH {coco_cte}
    SELECT 
        uc.PARTNER_NAME,
        uc.USE_CASE_ID,
        uc.USE_CASE_NUMBER,
        uc.USE_CASE_NAME,
        mdm.USE_CASE_DESCRIPTION,
        mdm.SE_COMMENTS,
        mdm.PARTNER_COMMENTS,
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
    LEFT JOIN MDM.MDM_INTERFACES.DIM_USE_CASE mdm ON uc.USE_CASE_ID = mdm.USE_CASE_ID
    WHERE (
        (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{quarter_start}' AND uc.DECISION_DATE <= '{quarter_end}')
        OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{quarter_start}' AND uc.GO_LIVE_DATE <= '{quarter_end}')
    )
    {tf}{srf}
    ORDER BY uc.PARTNER_NAME, IS_COCO_ATTACHED DESC, uc.USE_CASE_EACV DESC NULLS LAST
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_okr_partner_summary(_conn, quarter_start, quarter_end, region=None, include_account_coco=True, confidence=None, subregions=None):
    tf = _theater_filter(region)
    srf = _subregion_filter(subregions)
    coco_cte = _coco_accounts_cte(quarter_start, include_account_coco, confidence)
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
    {tf}{srf}
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
def get_distinct_subregions(_conn, region=None, start_date=None, end_date=None):
    """Sub-regions (REGION_NAME) available inside the current theatre/region scope.

    REGION_NAME is the level below THEATER_NAME and its meaning varies by theatre:
    industry for USMajors (HCLS, FSI, TMT...), country for APJ, sub-geography for
    EMEA. Options therefore cascade from whatever theatre/region is selected.
    """
    tf = _theater_filter(region)
    query = f"""{_use_case_base(start_date, end_date)}
    SELECT DISTINCT REGION_NAME
    FROM use_cases
    WHERE REGION_NAME IS NOT NULL AND TRIM(REGION_NAME) <> ''{tf}
    ORDER BY REGION_NAME
    """
    result = _conn.query(query)
    return result['REGION_NAME'].tolist()


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
            WHEN THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec') THEN 'NoAM'
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
            WHEN THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec') THEN 'NoAM'
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
        region_cond = " AND THEATER_NAME IN ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec')"
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
def get_partner_coco_coverage(_conn, region=None, start_date=None, end_date=None, include_account_coco=True, confidence=None):
    tf = _theater_filter(region)
    effective_start = start_date or '2025-11-20'
    coco_cte = _coco_accounts_cte(effective_start, include_account_coco, confidence)
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
def get_okr_stage_breakdown(_conn, region=None, start_date=None, end_date=None, include_account_coco=True, confidence=None, subregions=None):
    tf = _theater_filter(region)
    srf = _subregion_filter(subregions)
    effective_start = start_date or '2025-11-20'
    coco_cte = _coco_accounts_cte(effective_start, include_account_coco, confidence)
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
    {tf}{srf}
    GROUP BY uc.PARTNER_NAME, uc.USE_CASE_STAGE
    ORDER BY uc.PARTNER_NAME, uc.USE_CASE_STAGE
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_account_coco_credits(_conn, accounts: tuple, start_date: str) -> "pd.DataFrame":
    """Q2 CoCo credit consumption per account from CORTEX_CODE_USER_DAY_FACT.
    Returns ACCOUNT_NAME_UPPER, Q2_CREDITS, Q2_TOKENS, ACTIVE_DAYS, LAST_ACTIVE,
    LAST7_CREDITS, PRIOR7_CREDITS, LAST7_TOKENS, PRIOR7_TOKENS, WOW_CREDITS_PCT (per-account).
    Use LAST7/PRIOR7 at partner level for correct portfolio WoW, not the per-account mean.
    """
    if not accounts:
        import pandas as pd
        return pd.DataFrame(columns=['ACCOUNT_NAME_UPPER', 'Q2_CREDITS', 'Q2_TOKENS',
                                     'ACTIVE_DAYS', 'LAST_ACTIVE', 'WOW_CREDITS_PCT',
                                     'LAST7_CREDITS', 'PRIOR7_CREDITS',
                                     'LAST7_TOKENS', 'PRIOR7_TOKENS'])
    accts_sql = "','".join(a.replace("'", "''") for a in accounts)
    query = f"""
    SELECT
        UPPER(SALESFORCE_ACCOUNT_NAME)                                               AS ACCOUNT_NAME_UPPER,
        ROUND(SUM(TOTAL_TOKEN_CREDITS), 2)                                           AS Q2_CREDITS,
        SUM(TOTAL_TOKENS)                                                            AS Q2_TOKENS,
        COUNT(DISTINCT DS)                                                           AS ACTIVE_DAYS,
        MAX(DS)                                                                      AS LAST_ACTIVE,
        -- Per-account WoW (kept for Partner Deep Dive UC-level display)
        CASE
            WHEN SUM(CASE WHEN DS >= DATEADD('day',-14,CURRENT_DATE()) AND DS < DATEADD('day',-7,CURRENT_DATE()) THEN TOTAL_TOKEN_CREDITS END) > 0
            THEN ROUND(
                (SUM(CASE WHEN DS >= DATEADD('day',-7,CURRENT_DATE()) THEN TOTAL_TOKEN_CREDITS END)
                 - SUM(CASE WHEN DS >= DATEADD('day',-14,CURRENT_DATE()) AND DS < DATEADD('day',-7,CURRENT_DATE()) THEN TOTAL_TOKEN_CREDITS END))
                / SUM(CASE WHEN DS >= DATEADD('day',-14,CURRENT_DATE()) AND DS < DATEADD('day',-7,CURRENT_DATE()) THEN TOTAL_TOKEN_CREDITS END) * 100, 1)
            ELSE NULL
        END                                                                         AS WOW_CREDITS_PCT,
        -- Last/prior 7 days for portfolio-level WoW aggregation
        ROUND(SUM(CASE WHEN DS >= DATEADD('day',-7,CURRENT_DATE())
                       THEN TOTAL_TOKEN_CREDITS END), 2)                            AS LAST7_CREDITS,
        ROUND(SUM(CASE WHEN DS >= DATEADD('day',-14,CURRENT_DATE())
                       AND  DS <  DATEADD('day',-7,CURRENT_DATE())
                       THEN TOTAL_TOKEN_CREDITS END), 2)                            AS PRIOR7_CREDITS,
        SUM(CASE WHEN DS >= DATEADD('day',-7,CURRENT_DATE())
                 THEN TOTAL_TOKENS END)                                             AS LAST7_TOKENS,
        SUM(CASE WHEN DS >= DATEADD('day',-14,CURRENT_DATE())
                 AND  DS <  DATEADD('day',-7,CURRENT_DATE())
                 THEN TOTAL_TOKENS END)                                             AS PRIOR7_TOKENS
    FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT
    WHERE DS >= '{start_date}'
    AND SNOWFLAKE_ACCOUNT_TYPE = 'Customer'
    AND TOTAL_DAILY_REQUESTS > 0
    AND UPPER(SALESFORCE_ACCOUNT_NAME) IN ('{accts_sql}')
    GROUP BY UPPER(SALESFORCE_ACCOUNT_NAME)
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

# Workload-to-skill mapping for confidence scoring
WORKLOAD_SKILL_MAP = {
    'AI': ['%cortex-agent%', '%cortex-ai-function%', '%machine-learning%', '%semantic-view%', '%document-intelligence%', '%gdp-cortex-agent%'],
    'Analytics': ['%sql-author%', '%semantic_studio%', '%data:analyzing%', '%dashboard%', '%cortex-context-sql%'],
    'Data Engineering': ['%dbt%', '%dynamic-tables%', '%data:airflow%', '%openflow%', '%data-quality%', '%lineage%', '%iceberg%'],
    'Platform': ['%cost-intelligence%', '%warehouse%', '%data-governance%', '%access-troubleshooter%', '%billing%', '%trust-center%'],
    'Apps & Collab': ['%streamlit%', '%spcs%', '%snowflake-apps%', '%build-app%', '%notebook%'],
    'Migration': ['%migration%', '%spark%', '%databricks%'],
}

def _confidence_scored_query(partner_filter_sql, start_date, end_date):
    """Shared SQL body for confidence scoring - used by both single and bulk functions."""
    return f"""
    WITH partner_ucs AS (
        SELECT uc.USE_CASE_ID, uc.USE_CASE_NAME, uc.ACCOUNT_NAME, UPPER(uc.ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER,
            uc.PARTNER_NAME, uc.TECHNICAL_USE_CASE, uc.USE_CASE_STAGE,
            uc.USE_CASE_EACV, uc.IS_COCO, uc.COCO_SOURCE, uc.THEATER_NAME, uc.REGION_NAME,
            CASE
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%AI:%' THEN 'AI'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Analytics:%' THEN 'Analytics'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%DE:%' THEN 'Data Engineering'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Platform:%' THEN 'Platform'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Apps%' THEN 'Apps & Collab'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Migration%' THEN 'Migration'
                ELSE 'Unclassified'
            END AS WORKLOAD_CATEGORY
        FROM {DT_OKR} uc
        WHERE {partner_filter_sql}
        AND (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
        )
    ),
    account_ids AS (
        SELECT DISTINCT f.ACCOUNT_ID, UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
        FROM snowscience.llm.cortex_code_user_day_fact f
        WHERE f.snowflake_account_type = 'Customer' AND f.ds >= '{start_date}'
        AND UPPER(f.SALESFORCE_ACCOUNT_NAME) IN (SELECT ACCOUNT_NAME_UPPER FROM partner_ucs)
    ),
    relevant_bundled AS (
        SELECT aid.ACCOUNT_NAME_UPPER,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%cortex-agent%' OR r.SKILL_CHOICE ILIKE '%cortex-ai-function%' OR r.SKILL_CHOICE ILIKE '%machine-learning%' OR r.SKILL_CHOICE ILIKE '%semantic-view%' OR r.SKILL_CHOICE ILIKE '%document-intelligence%' THEN 1 ELSE 0 END) AS ai_skill_count,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%sql-author%' OR r.SKILL_CHOICE ILIKE '%semantic_studio%' OR r.SKILL_CHOICE ILIKE '%data:analyzing%' OR r.SKILL_CHOICE ILIKE '%dashboard%' OR r.SKILL_CHOICE ILIKE '%cortex-context-sql%' THEN 1 ELSE 0 END) AS analytics_skill_count,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%dbt%' OR r.SKILL_CHOICE ILIKE '%dynamic-tables%' OR r.SKILL_CHOICE ILIKE '%data:airflow%' OR r.SKILL_CHOICE ILIKE '%openflow%' OR r.SKILL_CHOICE ILIKE '%data-quality%' OR r.SKILL_CHOICE ILIKE '%lineage%' OR r.SKILL_CHOICE ILIKE '%iceberg%' THEN 1 ELSE 0 END) AS de_skill_count,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%cost-intelligence%' OR r.SKILL_CHOICE ILIKE '%warehouse%' OR r.SKILL_CHOICE ILIKE '%data-governance%' OR r.SKILL_CHOICE ILIKE '%access-troubleshooter%' OR r.SKILL_CHOICE ILIKE '%billing%' THEN 1 ELSE 0 END) AS platform_skill_count,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%streamlit%' OR r.SKILL_CHOICE ILIKE '%spcs%' OR r.SKILL_CHOICE ILIKE '%snowflake-apps%' OR r.SKILL_CHOICE ILIKE '%build-app%' OR r.SKILL_CHOICE ILIKE '%notebook%' THEN 1 ELSE 0 END) AS app_skill_count,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%migration%' OR r.SKILL_CHOICE ILIKE '%spark%' OR r.SKILL_CHOICE ILIKE '%databricks%' THEN 1 ELSE 0 END) AS migration_skill_count
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_STG r
        INNER JOIN account_ids aid ON r.ACCOUNT_ID = aid.ACCOUNT_ID
        WHERE r.ds >= '{start_date}' AND r.SKILL_CHOICE IS NOT NULL AND r.SKILL_CHOICE != ''
        GROUP BY aid.ACCOUNT_NAME_UPPER
    ),
    custom_skills AS (
        SELECT flattened.ACCOUNT_NAME_UPPER,
            COUNT(DISTINCT flattened.skill_name) AS custom_skill_count,
            COUNT(DISTINCT CASE
                WHEN LOWER(flattened.skill_name) REGEXP '.*(agent|cortex|llm|ml|model|intent|analyst|ai|chat|rag|embed).*'
                     OR COALESCE(cls.WORKLOAD_CATEGORY, '') = 'AI'
                THEN flattened.skill_name END) AS ai_custom_skills,
            COUNT(DISTINCT CASE
                WHEN LOWER(flattened.skill_name) REGEXP '.*(sql|query|analytics|bi|report|dashboard|semantic|data.analyz|analyzing).*'
                     OR COALESCE(cls.WORKLOAD_CATEGORY, '') = 'Analytics'
                THEN flattened.skill_name END) AS analytics_custom_skills,
            COUNT(DISTINCT CASE
                WHEN LOWER(flattened.skill_name) REGEXP '.*(dbt|airflow|pipeline|ingest|transform|etl|dag|lineage|stream|iceberg|cosmos|openlineage|checking.freshness|profiling|tracing).*'
                     OR COALESCE(cls.WORKLOAD_CATEGORY, '') = 'Data Engineering'
                THEN flattened.skill_name END) AS de_custom_skills,
            COUNT(DISTINCT CASE
                WHEN LOWER(flattened.skill_name) REGEXP '.*(govern|security|access|cost|warehouse|billing|admin|platform|monitor).*'
                     OR COALESCE(cls.WORKLOAD_CATEGORY, '') = 'Platform'
                THEN flattened.skill_name END) AS platform_custom_skills,
            COUNT(DISTINCT CASE
                WHEN LOWER(flattened.skill_name) REGEXP '.*(streamlit|app|frontend|ui|react|spcs|notebook).*'
                     OR COALESCE(cls.WORKLOAD_CATEGORY, '') = 'Apps & Collab'
                THEN flattened.skill_name END) AS app_custom_skills,
            COUNT(DISTINCT CASE
                WHEN LOWER(flattened.skill_name) REGEXP '.*(migrat|spark|databricks|ssis|convert|legacy).*'
                     OR COALESCE(cls.WORKLOAD_CATEGORY, '') = 'Migration'
                THEN flattened.skill_name END) AS migration_custom_skills
        FROM (
            SELECT aid.ACCOUNT_NAME_UPPER, sk.value:name::STRING AS skill_name
            FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_STG r
            INNER JOIN account_ids aid ON r.ACCOUNT_ID = aid.ACCOUNT_ID,
            LATERAL FLATTEN(input => TRY_PARSE_JSON(r.TOOL_RESOURCES_SKILL):skills) sk
            WHERE r.ds >= '{start_date}'
            AND r.TOOL_RESOURCES_SKILL IS NOT NULL AND r.TOOL_RESOURCES_SKILL != '' AND r.TOOL_RESOURCES_SKILL != '[]'
            AND sk.value:skill_source::STRING = 'user'
        ) flattened
        LEFT JOIN {SCHEMA}.SKILL_WORKLOAD_CLASSIFICATION cls
            ON LOWER(flattened.skill_name) = LOWER(cls.SKILL_NAME)
        GROUP BY flattened.ACCOUNT_NAME_UPPER
    ),
    tool_usage AS (
        SELECT aid.ACCOUNT_NAME_UPPER, COUNT(*) AS total_tool_invocations
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_STG r
        INNER JOIN account_ids aid ON r.ACCOUNT_ID = aid.ACCOUNT_ID,
        LATERAL FLATTEN(input => TRY_PARSE_JSON(r.TOOLS_INVOKED_JSON)) f
        WHERE r.ds >= '{start_date}' AND r.TOOLS_INVOKED_JSON IS NOT NULL AND r.TOOLS_INVOKED_JSON != '[]'
        GROUP BY aid.ACCOUNT_NAME_UPPER
    ),
    product_usage AS (
        SELECT UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER,
            COUNT(DISTINCT f.ds) AS active_days,
            COUNT(DISTINCT f.USER_ID) AS distinct_users,
            SUM(f.TOTAL_DAILY_REQUESTS) AS total_requests
        FROM snowscience.llm.cortex_code_user_day_fact f
        WHERE f.snowflake_account_type = 'Customer' AND f.ds >= '{start_date}' AND f.total_daily_requests > 0
        AND UPPER(f.SALESFORCE_ACCOUNT_NAME) IN (SELECT ACCOUNT_NAME_UPPER FROM partner_ucs)
        GROUP BY UPPER(f.SALESFORCE_ACCOUNT_NAME)
    ),
    account_credits AS (
        SELECT
            UPPER(SALESFORCE_ACCOUNT_NAME)                                               AS ACCOUNT_NAME_UPPER,
            ROUND(SUM(TOTAL_TOKEN_CREDITS), 2)                                           AS Q2_CREDITS,
            SUM(TOTAL_TOKENS)                                                            AS Q2_TOKENS,
            MAX(DS)                                                                      AS LAST_ACTIVE,
            ROUND(SUM(CASE WHEN DS >= DATEADD('day',-7,CURRENT_DATE())
                           THEN TOTAL_TOKEN_CREDITS END), 2)                            AS LAST7_CREDITS,
            ROUND(SUM(CASE WHEN DS >= DATEADD('day',-14,CURRENT_DATE())
                           AND  DS <  DATEADD('day',-7,CURRENT_DATE())
                           THEN TOTAL_TOKEN_CREDITS END), 2)                            AS PRIOR7_CREDITS,
            SUM(CASE WHEN DS >= DATEADD('day',-7,CURRENT_DATE())
                     THEN TOTAL_TOKENS END)                                             AS LAST7_TOKENS,
            SUM(CASE WHEN DS >= DATEADD('day',-14,CURRENT_DATE())
                     AND  DS <  DATEADD('day',-7,CURRENT_DATE())
                     THEN TOTAL_TOKENS END)                                             AS PRIOR7_TOKENS,
            -- Surface breakdown: CLI / Desktop / UI
            ROUND(SUM(COALESCE(CLI_TOKEN_CREDITS, 0)), 2)                              AS CLI_CREDITS,
            SUM(COALESCE(CLI_TOTAL_TOKENS, 0))                                         AS CLI_TOKENS,
            SUM(COALESCE(CLI_DAILY_REQUESTS, 0))                                       AS CLI_REQUESTS,
            ROUND(SUM(COALESCE(DESKTOP_TOKEN_CREDITS, 0)), 2)                          AS DESKTOP_CREDITS,
            SUM(COALESCE(DESKTOP_TOTAL_TOKENS, 0))                                     AS DESKTOP_TOKENS,
            SUM(COALESCE(DESKTOP_DAILY_REQUESTS, 0))                                   AS DESKTOP_REQUESTS,
            ROUND(SUM(COALESCE(UI_TOKEN_CREDITS, 0)), 2)                               AS UI_CREDITS,
            SUM(COALESCE(UI_TOTAL_TOKENS, 0))                                          AS UI_TOKENS,
            SUM(COALESCE(UI_DAILY_REQUESTS, 0))                                        AS UI_REQUESTS,
            SUM(COALESCE(UI_CODING_AGENT_REQUESTS, 0))                                 AS AGENT_REQUESTS,
            SUM(COALESCE(UI_REASONING_AGENT_REQUESTS, 0))                              AS REASONING_AGENT_REQUESTS
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT
        WHERE SNOWFLAKE_ACCOUNT_TYPE = 'Customer'
        AND TOTAL_DAILY_REQUESTS > 0
        AND DS >= '{start_date}'
        AND UPPER(SALESFORCE_ACCOUNT_NAME) IN (SELECT ACCOUNT_NAME_UPPER FROM partner_ucs)
        GROUP BY UPPER(SALESFORCE_ACCOUNT_NAME)
    ),
    scored AS (
        SELECT uc.*,
            CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(rb.ai_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(rb.analytics_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(rb.de_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(rb.platform_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(rb.app_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(rb.migration_skill_count, 0) ELSE 0 END AS RELEVANT_SKILL_INVOCATIONS,
            CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(cs.ai_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(cs.analytics_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(cs.de_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(cs.platform_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(cs.app_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(cs.migration_custom_skills, 0) ELSE 0 END AS RELEVANT_CUSTOM_SKILLS,
            COALESCE(cs.custom_skill_count, 0) AS CUSTOM_SKILLS,
            COALESCE(tu.total_tool_invocations, 0) AS TOOLS_INVOKED,
            COALESCE(pu.active_days, 0) AS ACTIVE_DAYS,
            COALESCE(pu.distinct_users, 0) AS DISTINCT_USERS,
            COALESCE(pu.total_requests, 0) AS TOTAL_REQUESTS,
            COALESCE(ac.Q2_CREDITS, 0)    AS Q2_CREDITS,
            COALESCE(ac.Q2_TOKENS, 0)     AS Q2_TOKENS,
            ac.LAST_ACTIVE,
            COALESCE(ac.LAST7_CREDITS, 0) AS LAST7_CREDITS,
            COALESCE(ac.PRIOR7_CREDITS, 0) AS PRIOR7_CREDITS,
            COALESCE(ac.LAST7_TOKENS, 0)  AS LAST7_TOKENS,
            COALESCE(ac.PRIOR7_TOKENS, 0) AS PRIOR7_TOKENS,
            -- Surface breakdown
            COALESCE(ac.CLI_CREDITS, 0)     AS CLI_CREDITS,
            COALESCE(ac.CLI_TOKENS, 0)      AS CLI_TOKENS,
            COALESCE(ac.CLI_REQUESTS, 0)    AS CLI_REQUESTS,
            COALESCE(ac.DESKTOP_CREDITS, 0) AS DESKTOP_CREDITS,
            COALESCE(ac.DESKTOP_TOKENS, 0)  AS DESKTOP_TOKENS,
            COALESCE(ac.DESKTOP_REQUESTS, 0) AS DESKTOP_REQUESTS,
            COALESCE(ac.UI_CREDITS, 0)      AS UI_CREDITS,
            COALESCE(ac.UI_TOKENS, 0)       AS UI_TOKENS,
            COALESCE(ac.UI_REQUESTS, 0)     AS UI_REQUESTS,
            COALESCE(ac.AGENT_REQUESTS, 0)  AS AGENT_REQUESTS,
            COALESCE(ac.REASONING_AGENT_REQUESTS, 0) AS REASONING_AGENT_REQUESTS,
            CASE WHEN CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(rb.ai_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(rb.analytics_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(rb.de_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(rb.platform_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(rb.app_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(rb.migration_skill_count, 0) ELSE 0 END >= 50 THEN 30 WHEN CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(rb.ai_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(rb.analytics_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(rb.de_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(rb.platform_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(rb.app_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(rb.migration_skill_count, 0) ELSE 0 END >= 10 THEN 20 WHEN CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(rb.ai_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(rb.analytics_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(rb.de_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(rb.platform_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(rb.app_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(rb.migration_skill_count, 0) ELSE 0 END >= 1 THEN 10 ELSE 0 END AS S1_SCORE,
            CASE WHEN CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(cs.ai_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(cs.analytics_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(cs.de_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(cs.platform_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(cs.app_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(cs.migration_custom_skills, 0) ELSE 0 END >= 3 THEN 35 WHEN CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(cs.ai_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(cs.analytics_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(cs.de_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(cs.platform_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(cs.app_custom_skills, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(cs.migration_custom_skills, 0) ELSE 0 END >= 1 THEN 25 WHEN COALESCE(cs.custom_skill_count, 0) >= 10 THEN 15 WHEN COALESCE(cs.custom_skill_count, 0) >= 1 THEN 8 ELSE 0 END AS S2_SCORE,
            CASE WHEN COALESCE(tu.total_tool_invocations, 0) >= 50000 THEN 20 WHEN COALESCE(tu.total_tool_invocations, 0) >= 10000 THEN 15 WHEN COALESCE(tu.total_tool_invocations, 0) >= 1000 THEN 10 WHEN COALESCE(tu.total_tool_invocations, 0) >= 1 THEN 5 WHEN COALESCE(pu.total_requests, 0) >= 1000 THEN 5 WHEN COALESCE(pu.total_requests, 0) >= 1 THEN 3 ELSE 0 END AS S3_SCORE,
            CASE WHEN COALESCE(pu.active_days, 0) = 0 THEN 0 WHEN (CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(rb.ai_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(rb.analytics_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(rb.de_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(rb.platform_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(rb.app_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(rb.migration_skill_count, 0) ELSE 0 END) / pu.active_days >= 5 THEN 15 WHEN (CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(rb.ai_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(rb.analytics_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(rb.de_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(rb.platform_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(rb.app_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(rb.migration_skill_count, 0) ELSE 0 END) / pu.active_days >= 1 THEN 10 WHEN (CASE WHEN uc.WORKLOAD_CATEGORY = 'AI' THEN COALESCE(rb.ai_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Analytics' THEN COALESCE(rb.analytics_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Data Engineering' THEN COALESCE(rb.de_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Platform' THEN COALESCE(rb.platform_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Apps & Collab' THEN COALESCE(rb.app_skill_count, 0) WHEN uc.WORKLOAD_CATEGORY = 'Migration' THEN COALESCE(rb.migration_skill_count, 0) ELSE 0 END) > 0 THEN 5 ELSE 0 END AS S4_SCORE
        FROM partner_ucs uc
        LEFT JOIN relevant_bundled rb ON uc.ACCOUNT_NAME_UPPER = rb.ACCOUNT_NAME_UPPER
        LEFT JOIN custom_skills cs ON uc.ACCOUNT_NAME_UPPER = cs.ACCOUNT_NAME_UPPER
        LEFT JOIN tool_usage tu ON uc.ACCOUNT_NAME_UPPER = tu.ACCOUNT_NAME_UPPER
        LEFT JOIN product_usage pu ON uc.ACCOUNT_NAME_UPPER = pu.ACCOUNT_NAME_UPPER
        LEFT JOIN account_credits ac ON uc.ACCOUNT_NAME_UPPER = ac.ACCOUNT_NAME_UPPER
    )
    SELECT *,
        S1_SCORE + S2_SCORE + S3_SCORE + S4_SCORE AS TOTAL_SCORE,
        CASE
            WHEN S1_SCORE + S2_SCORE + S3_SCORE + S4_SCORE >= 75 THEN 'High'
            WHEN S1_SCORE + S2_SCORE + S3_SCORE + S4_SCORE >= 40 THEN 'Medium'
            WHEN S1_SCORE + S2_SCORE + S3_SCORE + S4_SCORE >= 1 THEN 'Low'
            ELSE 'No Signal'
        END AS CONFIDENCE_BAND
    FROM scored"""

@st.cache_data(ttl=timedelta(minutes=30))
def get_usecase_confidence_scores(_conn, partner, start_date, end_date):
    """Compute confidence scores for a single partner's use cases (all aliases included)."""
    from utils import PARTNER_ALIASES
    raw_names = PARTNER_ALIASES.get(partner, [partner])
    names_sql = "','".join(n.replace("'", "''") for n in raw_names)
    partner_filter = f"uc.PARTNER_NAME IN ('{names_sql}')"
    query = _confidence_scored_query(partner_filter, start_date, end_date)
    query += "\n    ORDER BY TOTAL_SCORE DESC, ACCOUNT_NAME"
    return _conn.query(query)

@st.cache_data(ttl=timedelta(hours=5))
def get_bulk_confidence_scores(_conn, partners, start_date, end_date):
    """Compute confidence scores for multiple partners in a single query."""
    partners_sql = "','".join(partners)
    partner_filter = f"uc.PARTNER_NAME IN ('{partners_sql}')"
    query = _confidence_scored_query(partner_filter, start_date, end_date)
    query += "\n    ORDER BY TOTAL_SCORE DESC, PARTNER_NAME, ACCOUNT_NAME"
    return _conn.query(query)

@st.cache_data(ttl=timedelta(hours=5))
def get_segment_by_impl_start(_conn):
    """UC count + EACV by segment and workload for all stages 1-7,
    scoped by IMPLEMENTATION_START_DATE in FY27 YTD (Feb 1 2026 – today).
    No velocity — not all UCs have a go-live date yet.
    """
    query = f"""
    WITH hierarchy AS (
        SELECT PARTNER_NAME, PARENT_PARTNER_NAME FROM {SCHEMA}.PARTNER_HIERARCHY
    ),
    managed_parents AS (
        SELECT VALUE::STRING AS PARENT
        FROM TABLE(FLATTEN(INPUT => ARRAY_CONSTRUCT(
            'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
            'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting',
            '7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc',
            'kipi.ai','Kipi.ai','evolv Consulting','Infostrux Solutions Inc.',
            'Infosys','KPMG LLP','LTM','LTI Mindtree','NTT DATA Group Corporation',
            'phData, Inc.','Slalom, LLC.','Squadron Data Inc','Tredence Inc.',
            'Spaulding Ridge','TEKsystems Global Services, LLC.','Blend360, LLC',
            'Tiger Analytics Inc.','Atrium','Perficient Inc.','SDK Tek Services Ltd.',
            'Merkle','Archetype Consulting','Everforth Apex Systems','Tata Consultancy Services',
            'OneSix','Icon Analytics','Sparq Holdings, Inc.','CitiusTech Inc.',
            'Hexaware Technologies'
        )))
    ),
    managed_raw_names AS (
        SELECT PARENT AS RAW_NAME FROM managed_parents
        UNION
        SELECT h.PARTNER_NAME FROM hierarchy h
        WHERE h.PARENT_PARTNER_NAME IN (SELECT PARENT FROM managed_parents)
    ),
    classified AS (
        SELECT
            CASE
                WHEN COALESCE(
                    NULLIF(ARRAY_TO_STRING(uc.IMPLEMENTATION_SERVICES_PARTNER, ', '), ''),
                    NULLIF(ARRAY_TO_STRING(uc.CO_SELL_SERVICES_PARTNER, ', '), ''),
                    NULLIF(uc.PARTNER_NAME, ''),
                    NULLIF(ARRAY_TO_STRING(uc.USE_CASE_PARTNER, ', '), '')
                ) IS NULL THEN 'Customer-Led'
                WHEN EXISTS (
                    SELECT 1 FROM managed_raw_names m
                    WHERE ARRAY_TO_STRING(uc.IMPLEMENTATION_SERVICES_PARTNER, ', ') ILIKE '%' || m.RAW_NAME || '%'
                ) THEN 'Managed Partner'
                ELSE 'Other Partner'
            END AS SEGMENT,
            CASE
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%AI:%' OR uc.WORKLOADS ILIKE '%AI%' THEN 'AI / ML'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Migration%' OR uc.WORKLOADS ILIKE '%Migration%' THEN 'DWH / Migration'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Apps%' OR uc.WORKLOADS ILIKE '%Applications%' THEN 'Apps / Data Sharing'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Platform%' OR uc.WORKLOADS ILIKE '%Platform%' THEN 'Platform / Governance'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%DE:%' OR uc.WORKLOADS ILIKE '%Data Engineering%' OR uc.TECHNICAL_USE_CASE ILIKE '%Analytics%' THEN 'Data Engineering'
                ELSE 'Other'
            END AS WORKLOAD_CATEGORY,
            uc.USE_CASE_STAGE,
            TRY_CAST(uc.USE_CASE_EACV AS FLOAT) AS EACV
        FROM MDM.MDM_INTERFACES.DIM_USE_CASE uc
        WHERE uc.USE_CASE_STAGE NOT IN ('8 - Use Case Lost', '0 - Not In Pursuit')
        AND uc.IMPLEMENTATION_START_DATE >= '2026-02-01'
        AND uc.IMPLEMENTATION_START_DATE <= CURRENT_DATE()
        AND uc.IS_LOST = FALSE
    )
    SELECT
        SEGMENT,
        WORKLOAD_CATEGORY,
        USE_CASE_STAGE,
        COUNT(*)                              AS UC_COUNT,
        ROUND(SUM(EACV) / 1000000, 2)         AS TOTAL_EACV_M,
        ROUND(AVG(EACV) / 1000, 1)            AS AVG_EACV_K
    FROM classified
    GROUP BY SEGMENT, WORKLOAD_CATEGORY, USE_CASE_STAGE
    ORDER BY SEGMENT, WORKLOAD_CATEGORY, USE_CASE_STAGE
    """
    return _conn.query(query)


@st.cache_data(ttl=timedelta(hours=5))
def get_segment_velocity(_conn):
    """Velocity + EACV breakdown by segment (Customer-Led / Managed Partner / Other Partner)
    and workload category for FY27 YTD deployed use cases.
    Segment is determined by implementation partner field vs managed partner list.
    Excludes UCs with bad cycle times (< 1 day or > 730 days).
    """
    query = f"""
    WITH hierarchy AS (
        SELECT PARTNER_NAME, PARENT_PARTNER_NAME FROM {SCHEMA}.PARTNER_HIERARCHY
    ),
    managed_parents AS (
        SELECT VALUE::STRING AS PARENT
        FROM TABLE(FLATTEN(INPUT => ARRAY_CONSTRUCT(
            'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
            'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting',
            '7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc',
            'kipi.ai','Kipi.ai','evolv Consulting','Infostrux Solutions Inc.',
            'Infosys','KPMG LLP','LTM','LTI Mindtree','NTT DATA Group Corporation',
            'phData, Inc.','Slalom, LLC.','Squadron Data Inc','Tredence Inc.',
            'Spaulding Ridge','TEKsystems Global Services, LLC.','Blend360, LLC',
            'Tiger Analytics Inc.','Atrium','Perficient Inc.','SDK Tek Services Ltd.',
            'Merkle','Archetype Consulting','Everforth Apex Systems','Tata Consultancy Services',
            'OneSix','Icon Analytics','Sparq Holdings, Inc.','CitiusTech Inc.',
            'Hexaware Technologies'
        )))
    ),
    managed_raw_names AS (
        SELECT PARENT AS RAW_NAME FROM managed_parents
        UNION
        SELECT h.PARTNER_NAME FROM hierarchy h
        WHERE h.PARENT_PARTNER_NAME IN (SELECT PARENT FROM managed_parents)
    ),
    classified AS (
        SELECT
            CASE
                WHEN COALESCE(
                    NULLIF(ARRAY_TO_STRING(uc.IMPLEMENTATION_SERVICES_PARTNER, ', '), ''),
                    NULLIF(ARRAY_TO_STRING(uc.CO_SELL_SERVICES_PARTNER, ', '), ''),
                    NULLIF(uc.PARTNER_NAME, ''),
                    NULLIF(ARRAY_TO_STRING(uc.USE_CASE_PARTNER, ', '), '')
                ) IS NULL THEN 'Customer-Led'
                WHEN EXISTS (
                    SELECT 1 FROM managed_raw_names m
                    WHERE ARRAY_TO_STRING(uc.IMPLEMENTATION_SERVICES_PARTNER, ', ') ILIKE '%' || m.RAW_NAME || '%'
                ) THEN 'Managed Partner'
                ELSE 'Other Partner'
            END AS SEGMENT,
            CASE
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%AI:%' OR uc.WORKLOADS ILIKE '%AI%' THEN 'AI / ML'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Migration%' OR uc.WORKLOADS ILIKE '%Migration%' THEN 'DWH / Migration'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Apps%' OR uc.WORKLOADS ILIKE '%Applications%' THEN 'Apps / Data Sharing'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Platform%' OR uc.WORKLOADS ILIKE '%Platform%' THEN 'Platform / Governance'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%DE:%' OR uc.WORKLOADS ILIKE '%Data Engineering%' OR uc.TECHNICAL_USE_CASE ILIKE '%Analytics%' THEN 'Data Engineering'
                ELSE 'Other'
            END AS WORKLOAD_CATEGORY,
            DATEDIFF('day', uc.DECISION_DATE, uc.GO_LIVE_DATE) AS DAYS_FULL_CYCLE,
            TRY_CAST(uc.USE_CASE_EACV AS FLOAT) AS EACV
        FROM MDM.MDM_INTERFACES.DIM_USE_CASE uc
        WHERE uc.USE_CASE_STAGE = '7 - Deployed'
        AND uc.GO_LIVE_DATE >= '2026-02-01' AND uc.GO_LIVE_DATE <= CURRENT_DATE()
        AND uc.IS_LOST = FALSE
        AND uc.DECISION_DATE IS NOT NULL
        AND DATEDIFF('day', uc.DECISION_DATE, uc.GO_LIVE_DATE) BETWEEN 1 AND 730
    )
    SELECT
        SEGMENT,
        WORKLOAD_CATEGORY,
        COUNT(*)                                                                    AS UC_COUNT,
        ROUND(SUM(EACV) / 1000000, 2)                                               AS TOTAL_EACV_M,
        ROUND(AVG(EACV) / 1000, 1)                                                  AS AVG_EACV_K,
        ROUND(AVG(DAYS_FULL_CYCLE), 0)                                              AS AVG_DAYS,
        MEDIAN(DAYS_FULL_CYCLE)                                                     AS MEDIAN_DAYS,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY DAYS_FULL_CYCLE), 0)    AS P25_DAYS,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY DAYS_FULL_CYCLE), 0)    AS P75_DAYS
    FROM classified
    GROUP BY SEGMENT, WORKLOAD_CATEGORY
    ORDER BY SEGMENT, TOTAL_EACV_M DESC
    """
    return _conn.query(query)


@st.cache_data(ttl=timedelta(minutes=30))
def get_pipeline_wow(_conn):
    """WoW use case count and EACV change (current vs prior week) from CEO_USE_CASE_WEEKLY_METRICS."""
    query = f"""
    WITH weeks AS (
        SELECT WEEK_START,
            SUM(USE_CASE_COUNT)  AS TOTAL_UCS,
            SUM(TOTAL_EACV)      AS TOTAL_EACV,
            SUM(DEPLOYED)        AS DEPLOYED,
            SUM(IN_IMPL)         AS IN_IMPL,
            SUM(WON)             AS WON,
            SUM(ACTIVE_PIPELINE) AS ACTIVE_PIPELINE,
            ROW_NUMBER() OVER (ORDER BY WEEK_START DESC) AS rn
        FROM {SCHEMA}.CEO_USE_CASE_WEEKLY_METRICS
        GROUP BY WEEK_START
    )
    SELECT
        cur.WEEK_START,       prev.WEEK_START     AS PREV_WEEK_START,
        cur.TOTAL_UCS,        prev.TOTAL_UCS      AS PREV_TOTAL_UCS,
        cur.TOTAL_EACV,       prev.TOTAL_EACV     AS PREV_TOTAL_EACV,
        cur.DEPLOYED,         prev.DEPLOYED       AS PREV_DEPLOYED,
        cur.IN_IMPL,          prev.IN_IMPL        AS PREV_IN_IMPL,
        cur.WON,              prev.WON            AS PREV_WON,
        cur.ACTIVE_PIPELINE,  prev.ACTIVE_PIPELINE AS PREV_ACTIVE_PIPELINE,
        cur.TOTAL_UCS    - prev.TOTAL_UCS    AS WOW_TOTAL,
        cur.TOTAL_EACV   - prev.TOTAL_EACV   AS WOW_EACV,
        cur.DEPLOYED     - prev.DEPLOYED     AS WOW_DEPLOYED,
        cur.IN_IMPL      - prev.IN_IMPL      AS WOW_IN_IMPL,
        cur.WON          - prev.WON          AS WOW_WON,
        cur.ACTIVE_PIPELINE - prev.ACTIVE_PIPELINE AS WOW_ACTIVE
    FROM weeks cur
    JOIN weeks prev ON cur.rn = 1 AND prev.rn = 2
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_gsi_wow(_conn):
    """WoW engagement (requests) for the 6 GSIs aggregated across all regions."""
    query = f"""
    SELECT
        GSI_GROUP,
        SUM(TOTAL_USERS)    AS TOTAL_USERS,
        SUM(TOTAL_REQUESTS) AS TOTAL_REQUESTS,
        SUM(LW_REQUESTS)    AS LW_REQUESTS,
        SUM(PW_REQUESTS)    AS PW_REQUESTS,
        CASE WHEN SUM(PW_REQUESTS) > 0
            THEN ROUND((SUM(LW_REQUESTS) - SUM(PW_REQUESTS)) * 100.0 / SUM(PW_REQUESTS), 1)
        END AS WOW_PCT
    FROM {SCHEMA}.GSI_REGIONAL_METRICS
    GROUP BY GSI_GROUP
    ORDER BY TOTAL_REQUESTS DESC
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_noam_si_wow(_conn):
    """WoW engagement (requests) for NoAM managed SIs from OTHER_SI_REGIONAL_METRICS."""
    managed_noam_sis = (
        "'BlueCloud Services Inc','LTM','evolv Consulting','Slalom, LLC.',"
        "'Tredence Inc.','phData, Inc.','Squadron Data Inc','7Rivers, Inc',"
        "'Aimpoint Digital','Infostrux Solutions Inc.','Infosys','KPMG LLP',"
        "'NTT DATA Group Corporation'"
    )
    query = f"""
    SELECT PARTNER_NAME, TOTAL_USERS, TOTAL_REQUESTS, LW_REQUESTS, PW_REQUESTS, WOW_PCT, REGION_RANK
    FROM {SCHEMA}.OTHER_SI_REGIONAL_METRICS
    WHERE PARTNER_REGION = 'NoAM'
    AND PARTNER_NAME IN ({managed_noam_sis})
    ORDER BY TOTAL_REQUESTS DESC
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_recent_wins(_conn, partners, start_date, end_date, days_back=7):
    """Fetch recent deployments, competitive wins, and high-EACV CoCo UCs from last N days.
    Used to feed fresh content into the Notable Wins section of the exec email.
    """
    partners_sql = "','".join(partners)
    query = f"""
    WITH coco_active_accounts AS (
        SELECT DISTINCT UPPER(f.salesforce_account_name) AS ACCOUNT_NAME_UPPER
        FROM snowscience.llm.cortex_code_user_day_fact f
        WHERE f.ds >= '{start_date}'
        AND f.snowflake_account_type = 'Customer' AND f.total_daily_requests > 0
        AND f.ACCOUNT_ID IN (
            SELECT DISTINCT ACCOUNT_ID FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_STG
            WHERE ds >= '{start_date}' AND SKILL_CHOICE IS NOT NULL AND SKILL_CHOICE != ''
        )
    ),
    recent AS (
        SELECT
            uc.ACCOUNT_NAME,
            uc.PARTNER_NAME,
            uc.USE_CASE_NAME,
            uc.USE_CASE_STAGE,
            uc.USE_CASE_EACV,
            uc.TECHNICAL_USE_CASE,
            uc.COMPETITORS,
            uc.IS_COCO,
            uc.COCO_SOURCE,
            uc.GO_LIVE_DATE,
            uc.DECISION_DATE,
            CASE
                WHEN uc.USE_CASE_STAGE = '7 - Deployed'
                     AND uc.GO_LIVE_DATE >= DATEADD('day', -{days_back}, CURRENT_DATE())
                    THEN 'New Deployment'
                WHEN uc.COMPETITORS IS NOT NULL AND TRIM(uc.COMPETITORS) != ''
                     AND uc.DECISION_DATE >= DATEADD('day', -{days_back}, CURRENT_DATE())
                    THEN 'Competitive Win'
                WHEN uc.DECISION_DATE >= DATEADD('day', -{days_back}, CURRENT_DATE())
                    THEN 'Pipeline Move'
                ELSE 'Other'
            END AS WIN_TYPE
        FROM {DT_OKR} uc
        LEFT JOIN coco_active_accounts caa ON UPPER(uc.ACCOUNT_NAME) = caa.ACCOUNT_NAME_UPPER
        WHERE uc.PARTNER_NAME IN ('{partners_sql}')
        AND uc.THEATER_NAME IN ('AMSExpansion','USMajors','AMSAcquisition','USPubSec')
        AND (uc.IS_COCO = TRUE OR caa.ACCOUNT_NAME_UPPER IS NOT NULL)
        AND (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
                AND uc.DECISION_DATE >= '{start_date}' AND uc.DECISION_DATE <= '{end_date}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
                AND uc.GO_LIVE_DATE >= '{start_date}' AND uc.GO_LIVE_DATE <= '{end_date}')
        )
        AND (
            uc.GO_LIVE_DATE >= DATEADD('day', -{days_back}, CURRENT_DATE())
            OR uc.DECISION_DATE >= DATEADD('day', -{days_back}, CURRENT_DATE())
        )
    )
    SELECT * FROM recent
    ORDER BY
        CASE WIN_TYPE WHEN 'New Deployment' THEN 1 WHEN 'Competitive Win' THEN 2 ELSE 3 END,
        USE_CASE_EACV DESC NULLS LAST
    LIMIT 15
    """
    return _conn.query(query)

@st.cache_data(ttl=timedelta(minutes=30))
def get_adoption_trend_4w(_conn, partners: tuple, region: str = "NoAM") -> list:
    """Return [(week_label, coco_pct), ...] for last 4 weeks from OKR_PARTNER_WEEKLY_ADOPTION.
    Note: use get_coco_final_trend_4w for Def C (IS_COCO_FINAL) values.
    """
    ps = "','".join(partners)

    if region == "All":
        partner_where = f"w.PARTNER_NAME IN ('{ps}')"
        region_cte = ""
    else:
        region_theaters_sql = {
            "NoAM": "('AMSExpansion','USMajors','AMSAcquisition','USPubSec')",
            "EMEA": "('EMEA')",
            "APJ":  "('APJ')",
        }.get(region, "('AMSExpansion','USMajors','AMSAcquisition','USPubSec')")
        region_cte = f"""partner_theater AS (
            SELECT PARTNER_NAME,
                   CASE
                       WHEN THEATER_NAME IN ('AMSExpansion','USMajors','AMSAcquisition','USPubSec') THEN 'NoAM'
                       WHEN THEATER_NAME = 'EMEA' THEN 'EMEA'
                       WHEN THEATER_NAME = 'APJ'  THEN 'APJ'
                       ELSE 'Other'
                   END AS REGION,
                   COUNT(*) AS UC_CNT
            FROM {DT_OKR}
            WHERE PARTNER_NAME IN ('{ps}')
            GROUP BY 1, 2
            QUALIFY ROW_NUMBER() OVER (PARTITION BY PARTNER_NAME ORDER BY UC_CNT DESC) = 1
        ),"""
        partner_where = (
            f"w.PARTNER_NAME IN ('{ps}') "
            f"AND w.PARTNER_NAME IN (SELECT PARTNER_NAME FROM partner_theater WHERE REGION = '{region}')"
        )

    cte_prefix = f"WITH {region_cte}" if region_cte else "WITH "
    query = f"""
        {cte_prefix}
        weekly_raw AS (
            SELECT w.WEEK_START,
                SUM(w.TOTAL_UCS) AS total,
                SUM(w.COCO_UCS)  AS coco
            FROM {SCHEMA}.OKR_PARTNER_WEEKLY_ADOPTION w
            WHERE {partner_where}
            GROUP BY 1
        ),
        cumulative AS (
            SELECT WEEK_START,
                SUM(coco)  OVER (ORDER BY WEEK_START ROWS UNBOUNDED PRECEDING) AS cum_coco,
                SUM(total) OVER (ORDER BY WEEK_START ROWS UNBOUNDED PRECEDING) AS cum_total,
                ROW_NUMBER() OVER (ORDER BY WEEK_START DESC) AS rn
            FROM weekly_raw
        )
        SELECT WEEK_START, ROUND(cum_coco * 100.0 / NULLIF(cum_total, 0), 1) AS COCO_PCT
        FROM cumulative
        WHERE rn <= 4
        ORDER BY WEEK_START ASC
    """
    import pandas as pd
    df = _conn.query(query)
    result = []
    for _, row in df.iterrows():
        try:
            label = f"{pd.Timestamp(row['WEEK_START']).month}/{pd.Timestamp(row['WEEK_START']).day}"
        except Exception:
            label = str(row['WEEK_START'])[:10]
        result.append((label, float(row['COCO_PCT']) if pd.notna(row['COCO_PCT']) else 0.0))
    return result


@st.cache_data(ttl=timedelta(hours=2))
def get_partner_surface_trend_4w(_conn, account_partner_pairs: tuple):
    """Rolling 7-day credit + token consumption per partner for IS_COCO_FINAL accounts.
    Uses same rolling-window logic as Deep Dive LAST7/PRIOR7 so numbers match exactly.
    Returns DataFrame with PERIOD_LABEL, PERIOD_ORDER, PARTNER_NAME, WEEKLY_CREDITS, WEEKLY_TOKENS.
    """
    if not account_partner_pairs:
        return pd.DataFrame()
    # Build VALUES clause from pre-computed IS_COCO_FINAL account list
    values_rows = ", ".join(
        f"('{p.replace(chr(39), chr(39)+chr(39))}', '{a.replace(chr(39), chr(39)+chr(39))}')"
        for p, a in account_partner_pairs
    )
    query = f"""
    WITH coco_final_accounts AS (
        SELECT column1 AS PARTNER_NAME, column2 AS ACCOUNT_NAME_UPPER
        FROM VALUES {values_rows}
    ),
    raw AS (
        SELECT
            ca.PARTNER_NAME,
            f.TOTAL_TOKEN_CREDITS,
            f.TOTAL_TOKENS,
            CASE
                WHEN f.DS >= DATEADD('day', -7,  CURRENT_DATE()) THEN 1
                WHEN f.DS >= DATEADD('day', -14, CURRENT_DATE()) THEN 2
                WHEN f.DS >= DATEADD('day', -21, CURRENT_DATE()) THEN 3
                WHEN f.DS >= DATEADD('day', -28, CURRENT_DATE()) THEN 4
            END AS PERIOD_ORDER,
            CASE
                WHEN f.DS >= DATEADD('day', -7,  CURRENT_DATE()) THEN
                    TO_VARCHAR(DATEADD('day',-7, CURRENT_DATE()),'MM/DD') || '-' || TO_VARCHAR(DATEADD('day',-1, CURRENT_DATE()),'MM/DD')
                WHEN f.DS >= DATEADD('day', -14, CURRENT_DATE()) THEN
                    TO_VARCHAR(DATEADD('day',-14,CURRENT_DATE()),'MM/DD') || '-' || TO_VARCHAR(DATEADD('day',-8, CURRENT_DATE()),'MM/DD')
                WHEN f.DS >= DATEADD('day', -21, CURRENT_DATE()) THEN
                    TO_VARCHAR(DATEADD('day',-21,CURRENT_DATE()),'MM/DD') || '-' || TO_VARCHAR(DATEADD('day',-15,CURRENT_DATE()),'MM/DD')
                WHEN f.DS >= DATEADD('day', -28, CURRENT_DATE()) THEN
                    TO_VARCHAR(DATEADD('day',-28,CURRENT_DATE()),'MM/DD') || '-' || TO_VARCHAR(DATEADD('day',-22,CURRENT_DATE()),'MM/DD')
            END AS PERIOD_LABEL
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
        INNER JOIN coco_final_accounts ca
            ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = ca.ACCOUNT_NAME_UPPER
        WHERE f.DS >= DATEADD('day', -28, CURRENT_DATE())
          AND f.SNOWFLAKE_ACCOUNT_TYPE = 'Customer'
          AND f.TOTAL_DAILY_REQUESTS > 0
    )
    SELECT
        PERIOD_ORDER,
        PERIOD_LABEL,
        PARTNER_NAME,
        ROUND(SUM(TOTAL_TOKEN_CREDITS), 2) AS WEEKLY_CREDITS,
        SUM(TOTAL_TOKENS)                  AS WEEKLY_TOKENS
    FROM raw
    WHERE PERIOD_ORDER IS NOT NULL
    GROUP BY 1, 2, 3
    ORDER BY PERIOD_ORDER DESC, PARTNER_NAME
    """
    return _conn.query(query)


@st.cache_data(ttl=timedelta(hours=2))
def get_partner_coco_trend_4w(_conn, partners: tuple, region: str = 'All'):
    """Per-partner CoCo% for last 4 weeks from IS_COCO_FINAL_WEEKLY_SNAPSHOT.
    Filters to REGION='Global' to avoid double-counting regional rows.
    Returns DataFrame with WEEK_START, PARTNER_NAME, COCO_PCT, TOTAL_UCS, COCO_UCS.
    """
    if not partners:
        return pd.DataFrame()
    ps = "','".join(partners)
    region_clause = ""
    if region not in ('All', 'Global', ''):
        region_map = {
            'NoAM': ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec'),
            'EMEA': ('EMEA',), 'APJ': ('APJ',),
        }
        _theaters = "','".join(region_map.get(region, ()))
        region_clause = f"AND PARTNER_NAME IN (SELECT PARTNER_NAME FROM {SCHEMA}.DT_OKR_USE_CASES WHERE THEATER_NAME IN ('{_theaters}'))"
    query = f"""
    WITH deduped AS (
        SELECT WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS, COCO_PCT
        FROM {_SNAPSHOT_TABLE}
        WHERE PARTNER_NAME IN ('{ps}')
          AND REGION = 'Global'
          {region_clause}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY WEEK_START, PARTNER_NAME ORDER BY SAVED_AT ASC
        ) = 1
    )
    SELECT WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS, COCO_PCT
    FROM deduped
    WHERE WEEK_START >= DATEADD('week', -4, CURRENT_DATE())
    ORDER BY WEEK_START ASC, PARTNER_NAME
    """
    return _conn.query(query)


@st.cache_data(ttl=timedelta(hours=2))
def get_partner_weekly_credits_4w(_conn, partners: tuple, start_date: str, end_date: str):
    """Weekly credit + token consumption per partner for IS_COCO_FINAL accounts, last 4 weeks.
    Returns DataFrame with WEEK_START, PARTNER_NAME, WEEKLY_CREDITS, WEEKLY_TOKENS.
    """
    if not partners:
        return pd.DataFrame()
    ps = "','".join(partners)
    query = f"""
    WITH partner_coco_accounts AS (
        SELECT DISTINCT
            CASE WHEN PARTNER_NAME IN ('IBM','IBM Consulting') THEN 'IBM'
                 WHEN PARTNER_NAME IN ('EY','Ernst & Young (EY)') THEN 'EY'
                 WHEN PARTNER_NAME IN ('LTM','LTI Mindtree') THEN 'LTM'
                 WHEN PARTNER_NAME IN ('kipi.ai','Kipi.ai') THEN 'kipi.ai'
                 ELSE PARTNER_NAME END AS PARTNER_NAME,
            UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
        FROM {SCHEMA}.DT_OKR_USE_CASES
        WHERE PARTNER_NAME IN ('{ps}')
          AND IS_COCO = TRUE
          AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
                AND DECISION_DATE >= '{start_date}' AND DECISION_DATE <= '{end_date}')
            OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
                AND GO_LIVE_DATE >= '{start_date}' AND GO_LIVE_DATE <= '{end_date}'))
    )
    SELECT
        DATE_TRUNC('week', f.DS)                        AS WEEK_START,
        pc.PARTNER_NAME,
        ROUND(SUM(f.TOTAL_TOKEN_CREDITS), 2)            AS WEEKLY_CREDITS,
        SUM(f.TOTAL_TOKENS)                             AS WEEKLY_TOKENS
    FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
    INNER JOIN partner_coco_accounts pc
        ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = pc.ACCOUNT_NAME_UPPER
    WHERE f.DS >= DATEADD('week', -4, CURRENT_DATE())
      AND f.DS >= '{start_date}'
      AND f.SNOWFLAKE_ACCOUNT_TYPE = 'Customer'
      AND f.TOTAL_DAILY_REQUESTS > 0
    GROUP BY 1, 2
    ORDER BY 1 ASC, 2
    """
    return _conn.query(query)



_GSI_VELOCITY_PARTNERS = (
    "'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',"
    "'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting'"
)
_NOAM_THEATERS = (
    "'AMSExpansion','USMajors','AMSAcquisition','USPubSec'"
)

@st.cache_data(ttl=timedelta(weeks=1))
def get_partner_velocity_data(_conn, partners_sql: str):
    """Load and AI-classify managed partner deployed use cases for FY26-FY27 Q2 velocity analysis.
    GSIs use global (all theaters); RSIs filtered to NoAM theaters only.
    Cached for 1 week — AI_CLASSIFY on ~1700 UCs takes ~2 min on first load.
    """
    return _conn.query(f"""
    SELECT
        d.USE_CASE_ID,
        CASE WHEN d.PARTNER_NAME = 'Ernst & Young (EY)' THEN 'EY'
             WHEN d.PARTNER_NAME = 'IBM Consulting'     THEN 'IBM'
             WHEN d.PARTNER_NAME = 'Kipi.ai'            THEN 'kipi.ai'
             WHEN d.PARTNER_NAME = 'LTI Mindtree'       THEN 'LTM'
             ELSE d.PARTNER_NAME END                                              AS PARTNER_NAME,
        sf.ACTUAL_GO_LIVE_DATE_C                                                  AS GO_LIVE_DATE,
        sf.DECISION_DATE_C                                                        AS DECISION_DATE,
        DATEDIFF('day', sf.DECISION_DATE_C, sf.ACTUAL_GO_LIVE_DATE_C)            AS DAYS_FULL_CYCLE,
        CASE
            WHEN sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2025-02-01' AND '2025-04-30' THEN 'FY26 Q1'
            WHEN sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2025-05-01' AND '2025-07-31' THEN 'FY26 Q2'
            WHEN sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2025-08-01' AND '2025-10-31' THEN 'FY26 Q3'
            WHEN sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2025-11-01' AND '2026-01-31' THEN 'FY26 Q4'
            WHEN sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2026-02-01' AND '2026-04-30' THEN 'FY27 Q1'
            WHEN sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2026-05-01' AND '2026-07-31' THEN 'FY27 Q2'
        END                                                                       AS FISCAL_QUARTER,
        CASE
            WHEN sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2025-02-01' AND '2026-01-31' THEN 'FY26'
            WHEN sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2026-02-01' AND '2026-07-31' THEN 'FY27 Q1+Q2'
        END                                                                       AS COHORT,
        AI_CLASSIFY(
            LEFT(TRIM(COALESCE(sf.DESCRIPTION_C,'') || ' ' || COALESCE(sf.USE_CASE_COMMENTS_C,'')), 1000),
            ARRAY_CONSTRUCT('AI / ML','Data Engineering','DWH / Migration',
                            'Platform / Governance','Apps / Data Sharing')
        ):labels[0]::STRING                                                       AS WORKLOAD_CATEGORY,
        LEFT(COALESCE(sf.DESCRIPTION_C, sf.USE_CASE_COMMENTS_C,''), 180)         AS DESCRIPTION_PREVIEW,
        d.IS_COCO
    FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES d
    JOIN FIVETRAN.SALESFORCE.USE_CASE_C sf ON sf.ID = d.USE_CASE_ID
    WHERE d.PARTNER_NAME IN ({partners_sql})
      AND sf.STAGE_C = '7 - Deployed'
      AND sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2025-02-01' AND '2026-07-31'
      AND sf.DECISION_DATE_C IS NOT NULL
      AND sf._FIVETRAN_DELETED IS DISTINCT FROM TRUE
      AND LEN(TRIM(COALESCE(sf.DESCRIPTION_C,'') || ' ' || COALESCE(sf.USE_CASE_COMMENTS_C,''))) > 30
      AND DATEDIFF('day', sf.DECISION_DATE_C, sf.ACTUAL_GO_LIVE_DATE_C) BETWEEN 1 AND 730
      -- GSIs: all theaters (global); RSIs: NoAM theaters only
      AND (
          d.PARTNER_NAME IN ({_GSI_VELOCITY_PARTNERS})
          OR d.THEATER_NAME IN ({_NOAM_THEATERS})
      )
    """)


@st.cache_data(ttl=timedelta(hours=12))
def get_velocity_coco_final_flags(_conn, partners_sql: str, fy27_start: str = '2026-02-01'):
    """Compute IS_COCO_FINAL (S1+S2+S3+S4 >= 75 OR IS_COCO) for all velocity use cases.
    Returns DataFrame with USE_CASE_ID and IS_COCO_FINAL columns.
    Uses FY27 product usage data for confidence scoring.
    """
    return _conn.query(f"""
    WITH velocity_ucs AS (
        SELECT
            d.USE_CASE_ID,
            UPPER(d.ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER,
            d.IS_COCO,
            CASE
                WHEN d.TECHNICAL_USE_CASE ILIKE '%AI:%'        THEN 'AI'
                WHEN d.TECHNICAL_USE_CASE ILIKE '%Analytics:%' THEN 'Analytics'
                WHEN d.TECHNICAL_USE_CASE ILIKE '%DE:%'        THEN 'Data Engineering'
                WHEN d.TECHNICAL_USE_CASE ILIKE '%Platform:%'  THEN 'Platform'
                WHEN d.TECHNICAL_USE_CASE ILIKE '%Apps%'       THEN 'Apps & Collab'
                WHEN d.TECHNICAL_USE_CASE ILIKE '%Migration%'  THEN 'Migration'
                ELSE 'Unclassified'
            END AS WC
        FROM {DT_OKR} d
        JOIN FIVETRAN.SALESFORCE.USE_CASE_C sf ON sf.ID = d.USE_CASE_ID
        WHERE d.PARTNER_NAME IN ({partners_sql})
          AND sf.STAGE_C = '7 - Deployed'
          AND sf.ACTUAL_GO_LIVE_DATE_C BETWEEN '2025-02-01' AND '2026-07-31'
          AND sf._FIVETRAN_DELETED IS DISTINCT FROM TRUE
          AND (
              d.PARTNER_NAME IN ({_GSI_VELOCITY_PARTNERS})
              OR d.THEATER_NAME IN ({_NOAM_THEATERS})
          )
    ),
    account_ids AS (
        SELECT DISTINCT f.ACCOUNT_ID, UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
        WHERE f.SNOWFLAKE_ACCOUNT_TYPE = 'Customer' AND f.DS >= '{fy27_start}'
        AND UPPER(f.SALESFORCE_ACCOUNT_NAME) IN (SELECT ACCOUNT_NAME_UPPER FROM velocity_ucs)
    ),
    rb AS (
        SELECT a.ACCOUNT_NAME_UPPER,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%cortex-agent%' OR r.SKILL_CHOICE ILIKE '%cortex-ai-function%' OR r.SKILL_CHOICE ILIKE '%machine-learning%' OR r.SKILL_CHOICE ILIKE '%semantic-view%' THEN 1 ELSE 0 END) AS ai,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%sql-author%' OR r.SKILL_CHOICE ILIKE '%dashboard%' THEN 1 ELSE 0 END) AS ana,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%dbt%' OR r.SKILL_CHOICE ILIKE '%dynamic-tables%' OR r.SKILL_CHOICE ILIKE '%iceberg%' THEN 1 ELSE 0 END) AS de,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%cost-intelligence%' OR r.SKILL_CHOICE ILIKE '%data-governance%' THEN 1 ELSE 0 END) AS plt,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%streamlit%' OR r.SKILL_CHOICE ILIKE '%notebook%' THEN 1 ELSE 0 END) AS app,
            SUM(CASE WHEN r.SKILL_CHOICE ILIKE '%migration%' OR r.SKILL_CHOICE ILIKE '%spark%' THEN 1 ELSE 0 END) AS mig
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_STG r
        INNER JOIN account_ids a ON r.ACCOUNT_ID = a.ACCOUNT_ID
        WHERE r.DS >= '{fy27_start}' AND r.SKILL_CHOICE IS NOT NULL AND r.SKILL_CHOICE != ''
        GROUP BY a.ACCOUNT_NAME_UPPER
    ),
    cs AS (
        SELECT fl.ACCOUNT_NAME_UPPER,
            COUNT(DISTINCT fl.sn) AS total_cs,
            COUNT(DISTINCT CASE WHEN LOWER(fl.sn) REGEXP '.*(agent|cortex|llm|ml|model|ai|chat|rag|embed).*'       THEN fl.sn END) AS ai_cs,
            COUNT(DISTINCT CASE WHEN LOWER(fl.sn) REGEXP '.*(sql|query|analytics|bi|report|dashboard|semantic).*'  THEN fl.sn END) AS ana_cs,
            COUNT(DISTINCT CASE WHEN LOWER(fl.sn) REGEXP '.*(dbt|airflow|pipeline|etl|lineage|stream|iceberg).*'   THEN fl.sn END) AS de_cs,
            COUNT(DISTINCT CASE WHEN LOWER(fl.sn) REGEXP '.*(govern|security|access|cost|warehouse|billing|platform).*' THEN fl.sn END) AS plt_cs,
            COUNT(DISTINCT CASE WHEN LOWER(fl.sn) REGEXP '.*(streamlit|app|frontend|ui|react|spcs|notebook).*'     THEN fl.sn END) AS app_cs,
            COUNT(DISTINCT CASE WHEN LOWER(fl.sn) REGEXP '.*(migrat|spark|databricks|ssis|legacy).*'               THEN fl.sn END) AS mig_cs
        FROM (
            SELECT a.ACCOUNT_NAME_UPPER, sk.value:name::STRING AS sn
            FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_STG r
            INNER JOIN account_ids a ON r.ACCOUNT_ID = a.ACCOUNT_ID,
            LATERAL FLATTEN(input => TRY_PARSE_JSON(r.TOOL_RESOURCES_SKILL):skills) sk
            WHERE r.DS >= '{fy27_start}'
            AND r.TOOL_RESOURCES_SKILL IS NOT NULL AND r.TOOL_RESOURCES_SKILL != '' AND r.TOOL_RESOURCES_SKILL != '[]'
            AND sk.value:skill_source::STRING = 'user'
        ) fl
        GROUP BY fl.ACCOUNT_NAME_UPPER
    ),
    tu AS (
        SELECT a.ACCOUNT_NAME_UPPER, COUNT(*) AS ti
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_STG r
        INNER JOIN account_ids a ON r.ACCOUNT_ID = a.ACCOUNT_ID,
        LATERAL FLATTEN(input => TRY_PARSE_JSON(r.TOOLS_INVOKED_JSON)) f
        WHERE r.DS >= '{fy27_start}' AND r.TOOLS_INVOKED_JSON IS NOT NULL AND r.TOOLS_INVOKED_JSON != '[]'
        GROUP BY a.ACCOUNT_NAME_UPPER
    ),
    pu AS (
        SELECT UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER,
            COUNT(DISTINCT f.DS) AS ad, SUM(f.TOTAL_DAILY_REQUESTS) AS tr
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
        WHERE f.SNOWFLAKE_ACCOUNT_TYPE = 'Customer' AND f.DS >= '{fy27_start}' AND f.TOTAL_DAILY_REQUESTS > 0
        AND UPPER(f.SALESFORCE_ACCOUNT_NAME) IN (SELECT ACCOUNT_NAME_UPPER FROM velocity_ucs)
        GROUP BY UPPER(f.SALESFORCE_ACCOUNT_NAME)
    ),
    account_scores AS (
        SELECT u.ACCOUNT_NAME_UPPER,
            CASE WHEN u.WC='AI' THEN COALESCE(rb.ai,0) WHEN u.WC='Analytics' THEN COALESCE(rb.ana,0) WHEN u.WC='Data Engineering' THEN COALESCE(rb.de,0) WHEN u.WC='Platform' THEN COALESCE(rb.plt,0) WHEN u.WC='Apps & Collab' THEN COALESCE(rb.app,0) WHEN u.WC='Migration' THEN COALESCE(rb.mig,0) ELSE 0 END AS rs,
            CASE WHEN u.WC='AI' THEN COALESCE(cs.ai_cs,0) WHEN u.WC='Analytics' THEN COALESCE(cs.ana_cs,0) WHEN u.WC='Data Engineering' THEN COALESCE(cs.de_cs,0) WHEN u.WC='Platform' THEN COALESCE(cs.plt_cs,0) WHEN u.WC='Apps & Collab' THEN COALESCE(cs.app_cs,0) WHEN u.WC='Migration' THEN COALESCE(cs.mig_cs,0) ELSE 0 END AS rcs,
            COALESCE(cs.total_cs,0) AS tcs,
            COALESCE(tu.ti,0)       AS ti,
            COALESCE(pu.ad,0)       AS ad,
            COALESCE(pu.tr,0)       AS tr,
            u.USE_CASE_ID,
            u.IS_COCO
        FROM velocity_ucs u
        LEFT JOIN rb ON u.ACCOUNT_NAME_UPPER = rb.ACCOUNT_NAME_UPPER
        LEFT JOIN cs ON u.ACCOUNT_NAME_UPPER = cs.ACCOUNT_NAME_UPPER
        LEFT JOIN tu ON u.ACCOUNT_NAME_UPPER = tu.ACCOUNT_NAME_UPPER
        LEFT JOIN pu ON u.ACCOUNT_NAME_UPPER = pu.ACCOUNT_NAME_UPPER
    )
    SELECT
        USE_CASE_ID,
        IS_COCO,
        (IS_COCO = TRUE OR (
            CASE WHEN rs>=50 THEN 30 WHEN rs>=10 THEN 20 WHEN rs>=1 THEN 10 ELSE 0 END +
            CASE WHEN rcs>=3 THEN 35 WHEN rcs>=1 THEN 25 WHEN tcs>=10 THEN 15 WHEN tcs>=1 THEN 8 ELSE 0 END +
            CASE WHEN ti>=50000 THEN 20 WHEN ti>=10000 THEN 15 WHEN ti>=1000 THEN 10 WHEN ti>=1 THEN 5 WHEN tr>=1000 THEN 5 WHEN tr>=1 THEN 3 ELSE 0 END +
            CASE WHEN ad=0 THEN 0 WHEN rs/NULLIF(ad,0)>=5 THEN 15 WHEN rs/NULLIF(ad,0)>=1 THEN 10 WHEN rs>0 THEN 5 ELSE 0 END
        >= 75)) AS IS_COCO_FINAL
    FROM account_scores
    """)


@st.cache_data(ttl=timedelta(minutes=30))
def get_partners_at_target_trend_4w(_conn, partners: tuple, target_pct: float = 50.0, gsi_names: tuple = ()) -> list:
    """Return [(week_label, partners_at_target, total_partners), ...] for last 4 weeks.
    Primary source: COCO_OKR_TARGET_WEEKLY (pre-computed, upserted each exec email load for current week).
    Total partners derived from len(partners).
    """
    import pandas as pd
    total_partners = len(partners)

    query = f"""
    SELECT WEEK_START, PARTNERS_AT_TARGET
    FROM {_OKR_TARGET_TABLE}
    ORDER BY WEEK_START DESC
    LIMIT 4
    """
    df = _conn.query(query)
    df = df.sort_values('WEEK_START').reset_index(drop=True)
    result = []
    for _, row in df.iterrows():
        # Return raw week_start string — label formatting done at render time to avoid cache staleness
        result.append((str(row['WEEK_START'])[:10], int(row['PARTNERS_AT_TARGET']), total_partners))
    return result


def save_okr_target_count(_conn, partners_at_target: int, total_partners: int) -> None:
    """Upsert current week's partners_at_target into COCO_OKR_TARGET_WEEKLY.
    Current week is always refreshed (DELETE + INSERT); past weeks are frozen.
    Uses session().sql().collect() to bypass Streamlit query cache.
    """
    import pandas as pd
    week_start = pd.Timestamp.now().to_period('W').start_time.date().strftime('%Y-%m-%d')
    session = _conn.session()
    session.sql(f"DELETE FROM {_OKR_TARGET_TABLE} WHERE WEEK_START = '{week_start}'").collect()
    session.sql(
        f"INSERT INTO {_OKR_TARGET_TABLE} (WEEK_START, PARTNERS_AT_TARGET, TOTAL_PARTNERS) "
        f"VALUES ('{week_start}', {int(partners_at_target)}, {int(total_partners)})"
    ).collect()


# Mapping from _GROUP tag (added in executive_email.py) to REGION stored in snapshot
_GROUP_TO_REGION = {'GSI': 'Global', 'NOAM RSI': 'NoAM', 'APJ RSI': 'APJ', 'EMEA RSI': 'EMEA', 'LATAM RSI': 'LATAM'}


def save_coco_final_snapshot(_conn, bulk_conf_df, region='NoAM') -> bool:
    """Save this week's IS_COCO_FINAL (Def C) snapshot. Idempotent — skips if already saved this week.
    bulk_conf_df must have IS_COCO_FINAL, PARTNER_NAME, USE_CASE_ID, USE_CASE_EACV columns.
    If bulk_conf_df has a _GROUP column, each partner is saved with its correct REGION
    (GSI=Global, NOAM RSI=NoAM, APJ RSI=APJ, EMEA RSI=EMEA). Otherwise falls back to `region` param.
    Returns True if saved, False if already exists for this week.
    """
    import pandas as pd
    week_start = pd.Timestamp.now().to_period('W').start_time.date().strftime('%Y-%m-%d')

    existing = _conn.query(f"""
        SELECT COUNT(*) AS CNT FROM {_SNAPSHOT_TABLE}
        WHERE WEEK_START = '{week_start}'
    """)
    if existing.iloc[0]['CNT'] > 0:
        return False

    has_group = '_GROUP' in bulk_conf_df.columns
    rows = []
    for partner, grp in bulk_conf_df.groupby('PARTNER_NAME'):
        coco = int(grp['IS_COCO_FINAL'].sum())
        total = len(grp)
        pct = round(coco * 100.0 / total, 1) if total > 0 else 0.0
        eacv = float(grp['USE_CASE_EACV'].sum() or 0)
        coco_eacv = float(grp.loc[grp['IS_COCO_FINAL'], 'USE_CASE_EACV'].sum() or 0)
        safe_partner = partner.replace("'", "''")
        if has_group:
            grp_val = grp['_GROUP'].iloc[0] if len(grp) > 0 else None
            partner_region = _GROUP_TO_REGION.get(grp_val, region)
        else:
            partner_region = region
        safe_region = partner_region.replace("'", "''")
        rows.append(f"('{week_start}', '{safe_partner}', {total}, {coco}, {pct}, {eacv}, {coco_eacv}, '{safe_region}')")

    total_all = len(bulk_conf_df)
    coco_all = int(bulk_conf_df['IS_COCO_FINAL'].sum())
    pct_all = round(coco_all * 100.0 / total_all, 1) if total_all > 0 else 0.0
    eacv_all = float(bulk_conf_df['USE_CASE_EACV'].sum() or 0)
    coco_eacv_all = float(bulk_conf_df.loc[bulk_conf_df['IS_COCO_FINAL'], 'USE_CASE_EACV'].sum() or 0)
    # Overall row always saved as 'Global' (spans all partner groups)
    rows.append(f"('{week_start}', NULL, {total_all}, {coco_all}, {pct_all}, {eacv_all}, {coco_eacv_all}, 'Global')")

    _conn.query(f"""
        INSERT INTO {_SNAPSHOT_TABLE}
            (WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS, COCO_PCT, TOTAL_EACV, COCO_EACV, REGION)
        VALUES {', '.join(rows)}
    """)
    return True


@st.cache_data(ttl=timedelta(minutes=30))
def get_coco_final_wow(_conn, partners=None, gsi_global=False, gsi_names=frozenset()):
    """WoW CoCo adoption delta from IS_COCO_FINAL_WEEKLY_SNAPSHOT (Def C).

    gsi_global=False (default, OKR summary):
        All partners use REGION='NoAM'. Backward compatible.

    gsi_global=True (exec email):
        Partners in gsi_names use REGION='Global'; all others use REGION='NoAM'.
        Overall NULL row uses REGION='Global'.

    Deduplicates within each (WEEK_START, PARTNER_NAME, REGION).
    Returns NULL WoW columns until 2 distinct weeks of data exist for a given scope.
    """
    partner_filter = ""
    if partners:
        ps = "','".join(partners)
        partner_filter = f"AND (PARTNER_NAME IN ('{ps}') OR PARTNER_NAME IS NULL)"

    if gsi_global and gsi_names:
        gsi_list = "','".join(gsi_names)
        # GSI=Global, NOAM RSI=NoAM, APJ RSI=APJ, EMEA RSI=EMEA, LATAM RSI=LATAM, overall NULL=Global
        region_filter = f"""AND (
            (PARTNER_NAME IN ('{gsi_list}') AND COALESCE(REGION,'Global') = 'Global')
            OR (PARTNER_NAME NOT IN ('{gsi_list}') AND COALESCE(REGION,'NoAM') IN ('NoAM', 'APJ', 'EMEA', 'LATAM'))
            OR (PARTNER_NAME IS NULL AND COALESCE(REGION,'Global') = 'Global')
        )"""
    else:
        # Non-exec-email callers (OKR pages): return all managed partners across all regions
        region_filter = "AND COALESCE(REGION,'NoAM') IN ('NoAM', 'APJ', 'EMEA', 'LATAM', 'Global')"

    query = f"""
    WITH deduped AS (
        -- Keep one row per (WEEK_START, PARTNER_NAME, REGION), preferring earliest SAVED_AT
        SELECT WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS, COCO_PCT, TOTAL_EACV, COCO_EACV
        FROM {_SNAPSHOT_TABLE}
        WHERE 1=1 {partner_filter} {region_filter}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY WEEK_START, COALESCE(PARTNER_NAME, '__OVERALL__'), COALESCE(REGION,'NoAM')
            ORDER BY SAVED_AT
        ) = 1
    ),
    ranked AS (
        SELECT *,
            ROW_NUMBER() OVER (
                PARTITION BY COALESCE(PARTNER_NAME, '__OVERALL__')
                ORDER BY WEEK_START DESC
            ) AS rn
        FROM deduped
    )
    SELECT
        cur.PARTNER_NAME, cur.WEEK_START,
        prev.WEEK_START                           AS PREV_WEEK,
        cur.TOTAL_UCS, cur.COCO_UCS, cur.COCO_PCT,
        cur.TOTAL_EACV, cur.COCO_EACV,
        cur.COCO_UCS  - prev.COCO_UCS            AS WOW_COCO_UCS,
        ROUND(cur.COCO_PCT - prev.COCO_PCT, 1)   AS WOW_COCO_PCT,
        cur.COCO_EACV - prev.COCO_EACV           AS WOW_COCO_EACV
    FROM ranked cur
    LEFT JOIN ranked prev
        ON COALESCE(cur.PARTNER_NAME, '__OVERALL__') = COALESCE(prev.PARTNER_NAME, '__OVERALL__')
        AND cur.rn = 1 AND prev.rn = 2
    WHERE cur.rn = 1
    ORDER BY cur.PARTNER_NAME NULLS FIRST
    """
    return _conn.query(query)


@st.cache_data(ttl=timedelta(minutes=30))
def get_coco_final_trend_4w(_conn, partners: tuple, region: str = "NoAM") -> list:
    """Return [(week_label, coco_pct), ...] for last 4 weeks.
    Reads IS_COCO_FINAL_WEEKLY_SNAPSHOT (Def C) first; falls back to OKR_PARTNER_WEEKLY_ADOPTION
    for historical weeks not yet in the new table.
    """
    ps = "','".join(partners)

    if region == "All":
        partner_where = f"w.PARTNER_NAME IN ('{ps}')"
        cte_prefix = "WITH "
    else:
        region_theaters_sql = {
            "NoAM": "('AMSExpansion','USMajors','AMSAcquisition','USPubSec')",
            "EMEA": "('EMEA')", "APJ": "('APJ')",
        }.get(region, "('AMSExpansion','USMajors','AMSAcquisition','USPubSec')")
        cte_prefix = f"""WITH partner_theater AS (
            SELECT PARTNER_NAME,
                   CASE WHEN THEATER_NAME IN ('AMSExpansion','USMajors','AMSAcquisition','USPubSec') THEN 'NoAM'
                        WHEN THEATER_NAME = 'EMEA' THEN 'EMEA'
                        WHEN THEATER_NAME = 'APJ' THEN 'APJ' ELSE 'Other' END AS REGION,
                   COUNT(*) AS UC_CNT
            FROM {DT_OKR} WHERE PARTNER_NAME IN ('{ps}')
            GROUP BY 1, 2
            QUALIFY ROW_NUMBER() OVER (PARTITION BY PARTNER_NAME ORDER BY UC_CNT DESC) = 1
        ),"""
        partner_where = (
            f"w.PARTNER_NAME IN ('{ps}') "
            f"AND w.PARTNER_NAME IN (SELECT PARTNER_NAME FROM partner_theater WHERE REGION = '{region}')"
        )

    query = f"""
        {cte_prefix}
        -- IS_COCO_FINAL_WEEKLY_SNAPSHOT (Def C) has priority; OKR_PARTNER_WEEKLY_ADOPTION fills historical gaps
        combined AS (
            SELECT WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS, 1 AS src_priority
            FROM {_SNAPSHOT_TABLE} w
            WHERE {partner_where}
            UNION ALL
            SELECT WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS, 2 AS src_priority
            FROM {SCHEMA}.OKR_PARTNER_WEEKLY_ADOPTION w
            WHERE {partner_where}
        ),
        deduped AS (
            SELECT WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS
            FROM combined
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY WEEK_START, COALESCE(PARTNER_NAME, '__OVERALL__')
                ORDER BY src_priority
            ) = 1
        ),
        weekly_raw AS (
            SELECT WEEK_START, SUM(TOTAL_UCS) AS total, SUM(COCO_UCS) AS coco
            FROM deduped
            GROUP BY 1
        ),
        cumulative AS (
            SELECT WEEK_START,
                SUM(coco)  OVER (ORDER BY WEEK_START ROWS UNBOUNDED PRECEDING) AS cum_coco,
                SUM(total) OVER (ORDER BY WEEK_START ROWS UNBOUNDED PRECEDING) AS cum_total,
                ROW_NUMBER() OVER (ORDER BY WEEK_START DESC) AS rn
            FROM weekly_raw
        )
        SELECT WEEK_START, ROUND(cum_coco * 100.0 / NULLIF(cum_total, 0), 1) AS COCO_PCT
        FROM cumulative WHERE rn <= 4
        ORDER BY WEEK_START ASC
    """
    import pandas as pd
    df = _conn.query(query)
    result = []
    for _, row in df.iterrows():
        try:
            label = f"{pd.Timestamp(row['WEEK_START']).month}/{pd.Timestamp(row['WEEK_START']).day}"
        except Exception:
            label = str(row['WEEK_START'])[:10]
        result.append((label, float(row['COCO_PCT']) if pd.notna(row['COCO_PCT']) else 0.0))
    return result


# ============================================================================
# Partner Consultants subsection (Tier-1 + Tier-2 resolved; account-anchored)
# Reads pipeline tables built daily by SP_REFRESH_PARTNER_CONSULTANTS.
# ============================================================================

def _pc_filters(region, partner_names, alias="r"):
    reg = "" if (not region or region == "Global") else f" AND {alias}.PARTNER_REGION = '{region.replace(chr(39),chr(39)+chr(39))}'"
    pf = ""
    if partner_names:
        # Case-insensitive: the consultant pipeline stores some partners in a different
        # case than the sidebar taxonomy (roster 'accenture' vs sidebar 'Accenture'),
        # which made an exact IN (...) match return zero rows for those partners.
        pl = "','".join(p.replace("'", "''").upper() for p in partner_names)
        pf = f" AND UPPER({alias}.PARTNER_NAME) IN ('{pl}')"
    return reg, pf


@st.cache_data(ttl=timedelta(minutes=30))
def get_pc_activity(_conn, context, region=None, partner_names=None, start_date=None, end_date=None):
    """Per-partner resolved-consultant activity in a context ('Customer' or 'Partner'),
    windowed by DS; includes true rolling 7-day token change. Consultants = distinct resolved logins."""
    reg, pf = _pc_filters(region, partner_names, "r")
    sd = start_date or "2025-12-01"
    ed = end_date or "2100-01-01"
    query = f"""
    WITH r AS (
        SELECT USER_ID, DEPLOYMENT, PARTNER_NAME, MATCH_TIER
        FROM {SCHEMA}.PARTNER_CONSULTANT_RESOLVED r WHERE 1=1{reg}{pf}
    )
    SELECT r.PARTNER_NAME AS PARTNER_NAME,
        COUNT(DISTINCT f.USER_ID || '|' || f.DEPLOYMENT) AS CONSULTANTS,
        COUNT(DISTINCT CASE WHEN r.MATCH_TIER='Tier2' THEN f.USER_ID || '|' || f.DEPLOYMENT END) AS TIER2_CONSULTANTS,
        SUM(f.TOTAL_TOKENS) AS TOKENS,
        SUM(f.TOTAL_DAILY_USER_PROMPTS) AS PROMPTS,
        SUM(f.TOTAL_DAILY_REQUESTS) AS REQUESTS,
        SUM(CASE WHEN f.DS >= DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS ELSE 0 END) AS LAST7_TOKENS,
        SUM(CASE WHEN f.DS >= DATEADD('day',-14,CURRENT_DATE()) AND f.DS < DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS ELSE 0 END) AS PRIOR7_TOKENS
    FROM r
    JOIN SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
      ON f.USER_ID = r.USER_ID AND f.DEPLOYMENT = r.DEPLOYMENT
    WHERE f.SNOWFLAKE_ACCOUNT_TYPE = '{context}' AND f.TOTAL_DAILY_REQUESTS > 0
      AND f.DS BETWEEN '{sd}' AND '{ed}'
    GROUP BY 1
    """
    import pandas as pd
    df = _conn.query(query)
    if len(df) > 0:
        for c in ["CONSULTANTS", "TIER2_CONSULTANTS", "TOKENS", "PROMPTS", "REQUESTS", "LAST7_TOKENS", "PRIOR7_TOKENS"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["WOW_PCT"] = ((df["LAST7_TOKENS"] - df["PRIOR7_TOKENS"]) /
                         df["PRIOR7_TOKENS"].replace(0, float("nan")) * 100).round(1)
    return df


@st.cache_data(ttl=timedelta(minutes=30))
def get_pc_top_skills(_conn, context, region=None, partner_names=None, start_date=None, end_date=None, top=3):
    reg, pf = _pc_filters(region, partner_names, "s")
    sd = start_date or "2025-12-01"
    ed = end_date or "2100-01-01"
    query = f"""
    WITH s AS (
        SELECT PARTNER_NAME, PARTNER_REGION, skill, SUM(invocations) AS inv
        FROM {SCHEMA}.PARTNER_CONSULTANT_SKILLS s
        WHERE context = '{context}' AND week_start BETWEEN '{sd}' AND '{ed}'
          AND skill NOT ILIKE '%student%'{reg}{pf}
        GROUP BY 1,2,3
    ),
    ranked AS (SELECT PARTNER_NAME, skill, ROW_NUMBER() OVER (PARTITION BY PARTNER_NAME ORDER BY inv DESC) AS rn FROM s)
    SELECT PARTNER_NAME, LISTAGG(skill, ', ') WITHIN GROUP (ORDER BY rn) AS TOP_SKILLS
    FROM ranked WHERE rn <= {int(top)} GROUP BY 1
    """
    return _conn.query(query)


@st.cache_data(ttl=timedelta(minutes=30))
def get_coco_uc_weekly_counts(_conn, partners: tuple, region: str = "Global", weeks: int = 6):
    """Weekly CoCo use-case COUNTS for the given partners and region slice.

    IMPORTANT about the source table. IS_COCO_FINAL_WEEKLY_SNAPSHOT stores one row per
    (week, partner, REGION) where REGION is one of NoAM / EMEA / APJ / Global, and
    'Global' is the ROLL-UP of the other three — for Accenture in one week, Global 52
    CoCo equals APJ 7 + EMEA 29 + NoAM 16. Summing all four slices therefore double
    counts every partner, so exactly one slice is selected here. The table also contains
    exact duplicate rows (e.g. Accenture NoAM twice), which SELECT DISTINCT removes.

    Note the snapshot carries no theatre granularity, so any NoAM theatre selection
    (USMajors, AMSExpansion, ...) falls back to the whole NoAM slice.

    Counts are used rather than COCO_PCT because the percentage can fall while the
    number of CoCo use cases still grows.
    """
    if not partners:
        import pandas as pd
        return pd.DataFrame(columns=["WEEK_START", "COCO_UCS", "TOTAL_UCS"])
    ps = "','".join(p.replace("'", "''").upper() for p in partners)
    _named_region = {"NoAM": "NoAM", "EMEA": "EMEA", "APJ": "APJ"}.get(
        region, "NoAM" if region in ("AMSExpansion", "USMajors", "AMSAcquisition", "USPubSec")
        else None)

    if _named_region:
        # A specific geo was selected: use that slice only.
        body = f"""
        SELECT WEEK_START, PARTNER_NAME, COCO_UCS, TOTAL_UCS
        FROM d WHERE REGION = '{_named_region}'
        """
    else:
        # Global: take each partner's Global roll-up when it exists (GSIs), otherwise sum
        # their regional slices (RSIs have no Global row). Never both, or GSIs double count.
        body = """
        SELECT WEEK_START, PARTNER_NAME, COCO_UCS, TOTAL_UCS FROM g
        UNION ALL
        SELECT r.WEEK_START, r.PARTNER_NAME, r.COCO_UCS, r.TOTAL_UCS
        FROM r LEFT JOIN g
          ON g.WEEK_START = r.WEEK_START AND g.PARTNER_NAME = r.PARTNER_NAME
        WHERE g.PARTNER_NAME IS NULL
        """
    query = f"""
    WITH d AS (
        SELECT DISTINCT WEEK_START, PARTNER_NAME, REGION, COCO_UCS, TOTAL_UCS
        FROM {SCHEMA}.IS_COCO_FINAL_WEEKLY_SNAPSHOT
        WHERE UPPER(PARTNER_NAME) IN ('{ps}')
    ),
    g AS (SELECT WEEK_START, PARTNER_NAME, COCO_UCS, TOTAL_UCS FROM d WHERE REGION = 'Global'),
    r AS (SELECT WEEK_START, PARTNER_NAME, SUM(COCO_UCS) AS COCO_UCS, SUM(TOTAL_UCS) AS TOTAL_UCS
          FROM d WHERE REGION <> 'Global' GROUP BY 1, 2),
    scoped AS ({body})
    SELECT WEEK_START,
           SUM(COCO_UCS)  AS COCO_UCS,
           SUM(TOTAL_UCS) AS TOTAL_UCS,
           COUNT(DISTINCT PARTNER_NAME) AS PARTNERS
    FROM scoped
    GROUP BY 1
    ORDER BY 1 DESC
    LIMIT {int(weeks)}
    """
    import pandas as pd
    df = _conn.query(query)
    if len(df) > 0:
        for c in ["COCO_UCS", "TOTAL_UCS", "PARTNERS"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.sort_values("WEEK_START").reset_index(drop=True)
    return df


@st.cache_data(ttl=timedelta(minutes=30))
def get_pc_coco_uc_engagements(_conn, region=None, partner_names=None, start_date=None, end_date=None):
    """Consultant activity in customer accounts where THAT SAME partner owns a
    CoCo-attached use case (strict attribution), with the kind of work attached.

    The join key is exact account name: SALESFORCE_ACCOUNT_NAME on the activity side
    against ACCOUNT_NAME on PARTNER_COCO_USE_CASES. There is no shared account ID, so
    coverage is partial — the caller should report matched tokens as a share of all
    customer-account tokens rather than implying completeness.
    """
    reg, pf = _pc_filters(region, partner_names, "a")
    sd = start_date or "2025-12-01"
    ed = end_date or "2100-01-01"
    from utils import PARTNER_PIPELINE_CROSSWALK
    _xw_rows = ",\n            ".join(
        f"('{p.replace(chr(39), chr(39)*2)}','{c.replace(chr(39), chr(39)*2)}')"
        for c, names in PARTNER_PIPELINE_CROSSWALK.items() for p in names) or "('','')"
    query = f"""
    WITH xw AS (
        SELECT * FROM VALUES
            {_xw_rows}
        AS t(pipeline, canon)
    ),
    a AS (
        SELECT COALESCE(xw.canon, a.PARTNER_NAME) AS PARTNER_NAME,
               a.SALESFORCE_ACCOUNT_ID,
               MAX(a.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_NAME,
               COUNT(DISTINCT a.USER_ID || '|' || a.DEPLOYMENT) AS CONSULTANTS,
               SUM(a.TOTAL_TOKENS) AS TOKENS,
               SUM(a.TOTAL_DAILY_USER_PROMPTS) AS PROMPTS,
               COUNT(DISTINCT a.DS) AS ACTIVE_DAYS
        FROM {SCHEMA}.V_PARTNER_CONSULTANT_ACTIVITY a
        LEFT JOIN xw ON UPPER(a.PARTNER_NAME) = UPPER(xw.pipeline)
        WHERE a.SNOWFLAKE_ACCOUNT_TYPE = 'Customer'
          AND a.DS BETWEEN '{sd}' AND '{ed}'
          AND a.SALESFORCE_ACCOUNT_ID IS NOT NULL{reg}{pf}
        GROUP BY 1,2
    ),
    uc AS (
        SELECT p.PARTNER_NAME, d.ACCOUNT_ID,
               COUNT(DISTINCT p.USE_CASE_ID) AS COCO_UCS,
               SUM(COALESCE(p.USE_CASE_EACV,0)) AS EACV,
               COUNT(DISTINCT CASE WHEN p.IS_DEPLOYED THEN p.USE_CASE_ID END) AS DEPLOYED_UCS,
               LISTAGG(DISTINCT p.TECHNICAL_USE_CASE, ' ; ') AS TECH_USE_CASE,
               LISTAGG(DISTINCT p.WORKLOADS, ' ; ') AS WORKLOADS,
               MAX(p.THEATER_NAME) AS THEATER_NAME,
               MAX(p.REGION_NAME) AS REGION_NAME
        FROM {SCHEMA}.PARTNER_COCO_USE_CASES p
        JOIN MDM.MDM_INTERFACES.DIM_USE_CASE d ON d.USE_CASE_ID = p.USE_CASE_ID
        WHERE d.ACCOUNT_ID IS NOT NULL AND p.PARTNER_NAME IS NOT NULL
        GROUP BY 1,2
    )
    SELECT a.PARTNER_NAME, a.ACCOUNT_NAME,
           uc.COCO_UCS, uc.DEPLOYED_UCS, uc.EACV,
           a.CONSULTANTS, a.TOKENS, a.PROMPTS, a.ACTIVE_DAYS,
           uc.THEATER_NAME, uc.REGION_NAME,
           uc.TECH_USE_CASE, uc.WORKLOADS
    FROM a
    JOIN uc
      ON a.SALESFORCE_ACCOUNT_ID = uc.ACCOUNT_ID
     AND UPPER(a.PARTNER_NAME) = UPPER(uc.PARTNER_NAME)
    ORDER BY a.TOKENS DESC
    """
    import pandas as pd
    df = _conn.query(query)
    if len(df) > 0:
        for c in ["COCO_UCS", "DEPLOYED_UCS", "EACV", "CONSULTANTS", "TOKENS", "PROMPTS", "ACTIVE_DAYS"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@st.cache_data(ttl=timedelta(minutes=30))
def get_pc_totals(_conn, region=None, partner_names=None):
    reg, pf = _pc_filters(region, partner_names, "r")
    query = f"""
    SELECT r.PARTNER_NAME AS PARTNER_NAME, COUNT(*) AS TOTAL_CONSULTANTS,
           COUNT(CASE WHEN r.MATCH_TIER='Tier2' THEN 1 END) AS TIER2_CONSULTANTS
    FROM {SCHEMA}.PARTNER_CONSULTANT_RESOLVED r WHERE 1=1{reg}{pf}
    GROUP BY 1
    """
    import pandas as pd
    df = _conn.query(query)
    for c in ["TOTAL_CONSULTANTS", "TIER2_CONSULTANTS"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@st.cache_data(ttl=timedelta(minutes=30))
def get_pc_usecase_counts(_conn):
    """CoCo-attached use-case counts per partner (all + active/open) from PARTNER_COCO_USE_CASES."""
    query = f"""
    SELECT PARTNER_NAME,
        COUNT(DISTINCT USE_CASE_ID) AS COCO_UCS,
        COUNT(DISTINCT CASE WHEN NOT COALESCE(IS_LOST,FALSE) AND NOT COALESCE(IS_DEPLOYED,FALSE) THEN USE_CASE_ID END) AS ACTIVE_COCO_UCS
    FROM {SCHEMA}.PARTNER_COCO_USE_CASES
    WHERE PARTNER_NAME IS NOT NULL
    GROUP BY 1
    """
    import pandas as pd
    df = _conn.query(query)
    for c in ["COCO_UCS", "ACTIVE_COCO_UCS"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

