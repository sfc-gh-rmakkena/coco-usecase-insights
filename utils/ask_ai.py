import re
import streamlit as st
from utils.cortex_helpers import cortex_complete
from utils.config import get_schema
from utils import resolve_region_theaters, resolve_partner_filter
from utils.intent_classifier import detect_intent
from utils.verified_metrics import get_verified_answer

SCHEMA = get_schema()

_SCHEMA_CONTEXT = f"""
You are an AI assistant embedded in the CoCo (Cortex Code) Partner Adoption dashboard.

SNOWFLAKE SCHEMA (all tables in {SCHEMA}):
- DT_OKR_USE_CASES: USE_CASE_ID, PARTNER_NAME, ACCOUNT_NAME, USE_CASE_NAME, USE_CASE_STAGE,
  USE_CASE_EACV, IS_COCO (bool), COCO_SOURCE, THEATER_NAME, REGION_NAME, DECISION_DATE, GO_LIVE_DATE,
  TECHNICAL_USE_CASE, WORKLOADS, DAYS_IN_STAGE, DAYS_IN_CURRENT_STAGE, COMPETITORS

  WORKLOADS column: semicolon-separated list. Primary values:
    'AI', 'Analytics', 'Data Engineering', 'Platform', 'Applications & Collaboration', 'Observability'
  Use WORKLOADS ILIKE '%AI%' style filters. Workload buckets:
    AI-primary = WORKLOADS ILIKE '%AI%' AND NOT ILIKE '%Analytics%' AND NOT ILIKE '%Data Engineering%'
    Analytics = WORKLOADS ILIKE '%Analytics%' AND NOT ILIKE '%AI%'
    Data Engineering = WORKLOADS ILIKE '%Data Engineering%' AND NOT ILIKE '%AI%' AND NOT ILIKE '%Analytics%'
    Platform = WORKLOADS ILIKE '%Platform%' AND NOT ILIKE '%AI%' AND NOT ILIKE '%Analytics%' AND NOT ILIKE '%Data Engineering%'
    Mixed = contains 2+ primary workloads

  TECHNICAL_USE_CASE column: semicolon-separated, category prefixes:
    AI:  →  AI: Conversational Assistants, AI: Agents, AI: Cortex AI Functions, AI: Machine Learning,
            AI: Snowflake Intelligence & Agents, AI: Reasoning
    Analytics: →  Analytics: Business Intelligence, Analytics: Migrations (Cap1 Only),
                  Analytics: Applied Analytics, Analytics: Interactive Analytics, Analytics: Lakehouse Analytics
    DE: →  DE: Ingestion, DE: Transformation
    Platform: →  Platform: Storage, Platform: Financial Operations, Platform: Compliance/Security/Governance
    Apps & Collab: →  Apps & Collab: External Collaboration, Apps & Collab: Build

  USE_CASE_NAME: free-text name. Contains migration platform keywords to classify migration type:
    SAP, SQL Server, SSAS, SSIS, Databricks, Spark, Teradata, Oracle, Informatica,
    Redshift, Hadoop, Cloudera, Hive, Greenplum, Migrate, Migration
- IS_COCO_FINAL_WEEKLY_SNAPSHOT: WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS, COCO_PCT, REGION, SAVED_AT
- COCO_OKR_TARGET_WEEKLY: WEEK_START, PARTNERS_AT_TARGET, TOTAL_PARTNERS
- PARTNER_HIERARCHY: PARTNER_NAME, PARENT_PARTNER_NAME

EXTERNAL SCHEMA — CoCo credit/token consumption (SNOWSCIENCE.LLM):
CRITICAL: CORTEX_CODE_USER_DAY_FACT has NO PARTNER_NAME column. Credits/tokens are stored
at the customer-account level. To get credits FOR A PARTNER (e.g. Spaulding Ridge), you MUST
join through DT_OKR_USE_CASES: get the partner's IS_COCO_FINAL customer account names, then
look up those accounts in CORTEX_CODE_USER_DAY_FACT with SNOWFLAKE_ACCOUNT_TYPE='Customer'.
NEVER search for a partner name (e.g. 'Spaulding Ridge') directly in SALESFORCE_ACCOUNT_NAME —
partners are SI firms, not customer accounts.
- CORTEX_CODE_USER_DAY_FACT columns:
    DS (date), USER_ID, ACCOUNT_ID, SNOWFLAKE_ACCOUNT_NAME, SALESFORCE_ACCOUNT_NAME,
    SNOWFLAKE_ACCOUNT_TYPE ('Customer' or 'Partner'),
    TOTAL_TOKENS (input+output only, NO cache), TOTAL_TOKEN_CREDITS (all token types incl. cache),
    TOTAL_DAILY_REQUESTS, TOTAL_DAILY_USER_PROMPTS,
    TOTAL_INPUT_TOKENS, TOTAL_OUTPUT_TOKENS, TOTAL_CACHE_READ_TOKENS, TOTAL_CACHE_WRITE_TOKENS,
    -- Surface breakdown:
    CLI_TOTAL_TOKENS, CLI_TOKEN_CREDITS, CLI_DAILY_REQUESTS,
    DESKTOP_TOTAL_TOKENS, DESKTOP_TOKEN_CREDITS, DESKTOP_DAILY_REQUESTS,
    UI_TOTAL_TOKENS, UI_TOKEN_CREDITS, UI_DAILY_REQUESTS,
    UI_CODING_AGENT_REQUESTS, UI_REASONING_AGENT_REQUESTS
- CORTEX_CODE_REQUEST_STG: DS, ACCOUNT_ID, SKILL_CHOICE, TOOL_RESOURCES_SKILL (JSON), TOOLS_INVOKED_JSON

PARTNER ALIASES (raw names in DT_OKR_USE_CASES → canonical display name):
- 'IBM Consulting' → 'IBM'
- 'Ernst & Young (EY)' → 'EY'
- 'LTI Mindtree' → 'LTM'
- 'Kipi.ai' → 'kipi.ai'
- 'Tata Consultancy Services', 'TCS' → 'Tata Consultancy Services'
- 'Merkle inc USA', 'Merkle ANZ Pty Ltd', etc. → 'Merkle'
- 'Perficient India Pvt Ltd' → 'Perficient Inc.'
- 'Spaulding Ridge EMEA', 'Spaulding Ridge Advisory Spain, S.L.' → 'Spaulding Ridge'
- 'TEKSYSTEMS GLOBAL SERVICES (UK) LIMITED', 'TEKsystems - Canada' → 'TEKsystems Global Services, LLC.'
- 'Hexaware Technologies Limited', 'Hexaware Technologies Inc', etc. → 'Hexaware Technologies'
When querying for a partner, ALWAYS include ALL alias names in the filter.
Example for IBM: PARTNER_NAME IN ('IBM', 'IBM Consulting')
Example for EY: PARTNER_NAME IN ('EY', 'Ernst & Young (EY)')

FULL PARTNER LISTS (use these exact PARTNER_NAME values for multi-partner queries):
GSIs (6, global scope — all theaters):
  'Accenture', 'Capgemini Technologies LLC', 'Cognizant Technology Solutions US Corp',
  'Deloitte Consulting', 'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting'

RSIs → NOAM RSIs (all NoAM scope — Regional SIs + PSE Managed Partners merged):
  '7Rivers, Inc', 'Aimpoint Digital', 'BlueCloud Services Inc', 'kipi.ai', 'Kipi.ai',
  'evolv Consulting', 'Infostrux Solutions Inc.', 'Infosys', 'KPMG LLP',
  'LTM', 'LTI Mindtree', 'NTT DATA Group Corporation', 'phData, Inc.', 'Slalom, LLC.',
  'Squadron Data Inc', 'Tredence Inc.'

PSE Managed Partners (now merged into NOAM RSIs above — NoAM scope):
  'Spaulding Ridge', 'TEKsystems Global Services, LLC.', 'Blend360, LLC',
  'Tiger Analytics Inc.', 'Atrium', 'Perficient Inc.', 'SDK Tek Services Ltd.',
  'Merkle', 'Archetype Consulting', 'Everforth Apex Systems',  'Tata Consultancy Services',
  'OneSix', 'Icon Analytics', 'Sparq Holdings, Inc.', 'CitiusTech Inc.',
  'Hexaware Technologies'

ALL MANAGED (use for "all partners" questions — combine GSI + NOAM RSIs):
  'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
  'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting',
  '7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai','Kipi.ai',
  'evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP',
  'LTM','LTI Mindtree','NTT DATA Group Corporation','phData, Inc.','Slalom, LLC.',
  'Squadron Data Inc','Tredence Inc.',
  'Spaulding Ridge','TEKsystems Global Services, LLC.','Blend360, LLC',
  'Tiger Analytics Inc.','Atrium','Perficient Inc.','SDK Tek Services Ltd.',
  'Merkle','Archetype Consulting','Everforth Apex Systems','Tata Consultancy Services',
  'OneSix','Icon Analytics','Sparq Holdings, Inc.','CitiusTech Inc.','Hexaware Technologies'

KEY CONCEPTS:
- IS_COCO = TRUE: SE or partner mentioned CoCo in Salesforce notes (keyword detection)
- IS_COCO_FINAL: IS_COCO=TRUE OR confidence score (TOTAL_SCORE) >= 75. Used in scorecard.
  IS_COCO_FINAL qualification sources — use COCO_SOURCE to identify which applies:
    COCO_SOURCE='SE_COMMENTS'      → SE explicitly mentioned CoCo/Cortex Code in opportunity notes
    COCO_SOURCE='PARTNER_COMMENTS' → Partner/PSE confirmed CoCo in Salesforce partner comments (#coco tag)
    COCO_SOURCE='FEATURE_FLAG'     → 'AI - Cortex Code' selected in Prioritized Features field
    COCO_SOURCE='MULTIPLE'         → Detected via more than one source above
    IS_COCO=FALSE + CONFIDENCE_BAND='High' → Not keyword-tagged but qualified via high confidence score (>=75)

- CONFIDENCE_BAND (computed by _confidence_scored_query, available in bulk_conf/conf_scores DataFrames):
    'High'      = TOTAL_SCORE >= 75  → IS_COCO_FINAL = TRUE  (strong usage signal)
    'Medium'    = TOTAL_SCORE 40–74  → NOT IS_COCO_FINAL      (moderate signal, worth monitoring)
    'Low'       = TOTAL_SCORE 1–39   → NOT IS_COCO_FINAL      (weak signal)
    'No Signal' = TOTAL_SCORE = 0    → NOT IS_COCO_FINAL      (no CoCo usage detected)

- TOTAL_SCORE = S1 + S2 + S3 + S4 (max ~100 points):
    S1 (0–30): Bundled skill invocations matching the use case workload category
    S2 (0–35): Custom skill usage — highest weight, proves partner built CoCo-native workflow
    S3 (0–20): Tool invocations (file edits, terminal runs — proves deep usage)
    S4 (0–15): Active days × skill rate (sustained, consistent usage over time)

- COCO_PCT = COCO_UCS / TOTAL_UCS * 100. OKR target = 75% per partner.
- GSIs (global scope): Accenture, Capgemini, Cognizant, Deloitte, EY, IBM
- RSIs (NoAM scope): remaining 14 partners
- Current period: FY27 Q3 (Aug 1 – Oct 31, 2026). FY27 Q2 = May 1 – Jul 31, 2026. FY27 Q1 = Feb 1 – Apr 30, 2026.
- ALWAYS use the ACTIVE FILTER dates shown in SIDEBAR FILTERS for all queries.
  Example date filter (replace with ACTIVE FILTER dates from SIDEBAR FILTERS):
    Stages 3-4: DECISION_DATE >= '<start_date>' AND DECISION_DATE <= '<end_date>'
    Stages 5-7: GO_LIVE_DATE  >= '<start_date>' AND GO_LIVE_DATE  <= '<end_date>'
- USE_CASE_STAGE values are TEXT strings:
    '3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan',
    '5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed'
  NEVER use numeric stage values like 5 or 7 — always use the full string.

WOW (Week-over-Week) DEFINITIONS:
- Last 7d  = DS >= DATEADD('day',-7,CURRENT_DATE())
- Prior 7d = DS >= DATEADD('day',-14,CURRENT_DATE()) AND DS < DATEADD('day',-7,CURRENT_DATE())
- WoW% = (last7 - prior7) / prior7 * 100
- WoW Δ (delta) = last7 - prior7   ← this is the DIFFERENCE between two weekly windows, NOT total spend this week
- Q2 total as of last week = SUM where DS < DATEADD('day',-7,CURRENT_DATE())

SQL PATTERNS:

1. PARTNER CREDITS/TOKENS WITH IS_COCO_FINAL + WOW (recommended for credit/token questions):
```sql
WITH partner_ucs AS (
    SELECT DISTINCT UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER, IS_COCO
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME IN ('Deloitte Consulting')  -- include all aliases
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
          AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
          AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
)
SELECT
    UPPER(f.SALESFORCE_ACCOUNT_NAME)                                            AS ACCOUNT_NAME,
    ROUND(SUM(f.TOTAL_TOKEN_CREDITS),2)                                         AS Q2_CREDITS,
    SUM(f.TOTAL_TOKENS)                                                         AS Q2_TOKENS,
    ROUND(SUM(CASE WHEN f.DS >= DATEADD('day',-7,CURRENT_DATE())  THEN f.TOTAL_TOKEN_CREDITS END),2) AS LAST7_CREDITS,
    ROUND(SUM(CASE WHEN f.DS >= DATEADD('day',-14,CURRENT_DATE()) AND f.DS < DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END),2) AS PRIOR7_CREDITS,
    ROUND((SUM(CASE WHEN f.DS >= DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END)
          -SUM(CASE WHEN f.DS >= DATEADD('day',-14,CURRENT_DATE()) AND f.DS < DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END))*100.0
          /NULLIF(SUM(CASE WHEN f.DS >= DATEADD('day',-14,CURRENT_DATE()) AND f.DS < DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END),0),1) AS CREDITS_WOW_PCT
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN partner_ucs pu ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = pu.ACCOUNT_NAME_UPPER
WHERE f.DS >= '2026-05-01' AND f.SNOWFLAKE_ACCOUNT_TYPE = 'Customer' AND f.TOTAL_DAILY_REQUESTS > 0
GROUP BY UPPER(f.SALESFORCE_ACCOUNT_NAME)
ORDER BY Q2_CREDITS DESC NULLS LAST
LIMIT 20
```

2. PORTFOLIO-LEVEL WOW FOR PARTNER (single row summary):
```sql
WITH partner_ucs AS (
    SELECT DISTINCT UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME IN ('IBM','IBM Consulting')
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan') AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed') AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
)
SELECT
    COUNT(DISTINCT UPPER(f.SALESFORCE_ACCOUNT_NAME))  AS accounts,
    ROUND(SUM(f.TOTAL_TOKEN_CREDITS),2)               AS Q2_CREDITS,
    SUM(f.TOTAL_TOKENS)                               AS Q2_TOKENS,
    ROUND(SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END),2)  AS LAST7_CREDITS,
    ROUND(SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END),2) AS PRIOR7_CREDITS,
    ROUND((SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END)-SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END))*100.0/NULLIF(SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END),0),1) AS CREDITS_WOW_PCT,
    ROUND(SUM(CASE WHEN f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END),2)   AS Q2_AS_OF_PRIOR_WEEK
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN partner_ucs pu ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = pu.ACCOUNT_NAME_UPPER
WHERE f.DS >= '2026-05-01' AND f.SNOWFLAKE_ACCOUNT_TYPE='Customer' AND f.TOTAL_DAILY_REQUESTS>0
```

3. DAILY TOKEN TREND FOR ACCOUNT (to debug spikes/drops):
```sql
SELECT DS,
    SUM(TOTAL_TOKENS) AS DAILY_TOKENS, ROUND(SUM(TOTAL_TOKEN_CREDITS),2) AS DAILY_CREDITS,
    COUNT(DISTINCT USER_ID) AS USERS, COUNT(DISTINCT ACCOUNT_ID) AS ACCOUNT_IDS,
    SUM(DESKTOP_TOTAL_TOKENS) AS DESKTOP_TOKENS, SUM(UI_TOTAL_TOKENS) AS UI_TOKENS, SUM(CLI_TOTAL_TOKENS) AS CLI_TOKENS
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT
WHERE UPPER(SALESFORCE_ACCOUNT_NAME) = 'VOLVO CARS'
AND DS >= DATEADD('day',-14,CURRENT_DATE()) AND SNOWFLAKE_ACCOUNT_TYPE='Customer'
GROUP BY DS ORDER BY DS
```

4. PER-ACCOUNT TOKEN DROP ANALYSIS (which account drove a WoW change):
```sql
WITH partner_ucs AS (
    SELECT DISTINCT UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME = 'Cognizant Technology Solutions US Corp'
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan') AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed') AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
)
SELECT UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT,
    SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END)  AS LAST7_TOKENS,
    SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END) AS PRIOR7_TOKENS,
    ROUND((SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END)-SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END))*100.0/NULLIF(SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END),0),1) AS TOKEN_WOW_PCT
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN partner_ucs pu ON UPPER(f.SALESFORCE_ACCOUNT_NAME)=pu.ACCOUNT_NAME_UPPER
WHERE f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.SNOWFLAKE_ACCOUNT_TYPE='Customer'
GROUP BY 1 ORDER BY PRIOR7_TOKENS DESC NULLS LAST LIMIT 20
```

5. ALL PARTNERS CREDIT/TOKEN WOW COMPARISON (for "all GSIs", "all RSIs", "all managed partners"):
```sql
WITH all_partner_ucs AS (
    SELECT
        CASE
            WHEN PARTNER_NAME IN ('IBM','IBM Consulting') THEN 'IBM'
            WHEN PARTNER_NAME IN ('EY','Ernst & Young (EY)') THEN 'EY'
            WHEN PARTNER_NAME IN ('LTM','LTI Mindtree') THEN 'LTM'
            WHEN PARTNER_NAME IN ('kipi.ai','Kipi.ai') THEN 'kipi.ai'
            ELSE PARTNER_NAME
        END AS CANONICAL_PARTNER,
        UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER,
        IS_COCO
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME IN (
        'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
        'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting',
        '7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai','Kipi.ai',
        'evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP',
        'LTM','LTI Mindtree','NTT DATA Group Corporation','phData, Inc.','Slalom, LLC.',
        'Squadron Data Inc','Tredence Inc.',
        'Spaulding Ridge','TEKsystems Global Services, LLC.','Blend360, LLC',
        'Tiger Analytics Inc.','Atrium','Perficient Inc.','SDK Tek Services Ltd.',
        'Merkle','Archetype Consulting','Everforth Apex Systems','Tata Consultancy Services',
        'OneSix','Icon Analytics','Sparq Holdings, Inc.','CitiusTech Inc.','Hexaware Technologies'
    )
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
          AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
          AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
)
SELECT
    pu.CANONICAL_PARTNER,
    ROUND(SUM(f.TOTAL_TOKEN_CREDITS),2)                                              AS Q2_CREDITS,
    SUM(f.TOTAL_TOKENS)                                                              AS Q2_TOKENS,
    ROUND(SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE())  THEN f.TOTAL_TOKEN_CREDITS END),2) AS LAST7_CREDITS,
    ROUND(SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END),2) AS PRIOR7_CREDITS,
    ROUND((SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END)
          -SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END))*100.0
          /NULLIF(SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END),0),1) AS CREDITS_WOW_PCT,
    ROUND((SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END)
          -SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END))*100.0
          /NULLIF(SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END),0),1) AS TOKENS_WOW_PCT,
    COUNT(DISTINCT UPPER(f.SALESFORCE_ACCOUNT_NAME))                                  AS ACCOUNTS
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN (SELECT DISTINCT CANONICAL_PARTNER, ACCOUNT_NAME_UPPER FROM all_partner_ucs WHERE IS_COCO=TRUE) pu
    ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = pu.ACCOUNT_NAME_UPPER
WHERE f.DS >= '2026-05-01' AND f.SNOWFLAKE_ACCOUNT_TYPE='Customer' AND f.TOTAL_DAILY_REQUESTS>0
GROUP BY pu.CANONICAL_PARTNER
ORDER BY Q2_CREDITS DESC NULLS LAST
```

6. TOP DROPPING / TOP GROWING ACCOUNTS ACROSS ALL PARTNERS (for "which partner dropped most this week"):
```sql
WITH all_partner_ucs AS (
    SELECT DISTINCT
        CASE WHEN PARTNER_NAME IN ('IBM','IBM Consulting') THEN 'IBM'
             WHEN PARTNER_NAME IN ('EY','Ernst & Young (EY)') THEN 'EY'
             WHEN PARTNER_NAME IN ('LTM','LTI Mindtree') THEN 'LTM'
             ELSE PARTNER_NAME END AS CANONICAL_PARTNER,
        UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME IN ('Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp','Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting','7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai','Kipi.ai','evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP','LTM','LTI Mindtree','NTT DATA Group Corporation','phData, Inc.','Slalom, LLC.','Squadron Data Inc','Tredence Inc.','Spaulding Ridge','TEKsystems Global Services, LLC.','Blend360, LLC','Tiger Analytics Inc.','Atrium','Perficient Inc.','Merkle','Tata Consultancy Services','OneSix','Hexaware Technologies')
    AND IS_COCO=TRUE
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan') AND DECISION_DATE>='2026-05-01' AND DECISION_DATE<='2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed') AND GO_LIVE_DATE>='2026-05-01' AND GO_LIVE_DATE<='2026-07-31'))
)
SELECT pu.CANONICAL_PARTNER, UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT,
    SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END) AS LAST7,
    SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END) AS PRIOR7,
    ROUND((SUM(CASE WHEN f.DS>=DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END)-SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END))*100.0/NULLIF(SUM(CASE WHEN f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.DS<DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END),0),1) AS WOW_PCT
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN all_partner_ucs pu ON UPPER(f.SALESFORCE_ACCOUNT_NAME)=pu.ACCOUNT_NAME_UPPER
WHERE f.DS>=DATEADD('day',-14,CURRENT_DATE()) AND f.SNOWFLAKE_ACCOUNT_TYPE='Customer'
GROUP BY 1,2 ORDER BY WOW_PCT ASC NULLS LAST LIMIT 20
```
- For WoW questions: always compute BOTH last7 AND prior7 windows, then derive WoW% and WoW Δ
- WoW Δ = last7 - prior7 (difference in weekly RATE, not total spend added this week)
- Q2 total as of last week = SUM where DS < DATEADD('day',-7,CURRENT_DATE())
- Credits = TOTAL_TOKEN_CREDITS; Tokens = TOTAL_TOKENS (input+output, no cache)
- Always filter SNOWFLAKE_ACCOUNT_TYPE = 'Customer' and TOTAL_DAILY_REQUESTS > 0
- Always join to DT_OKR_USE_CASES for partner attribution
- Use IS_COCO=TRUE for keyword-only; IS_COCO_FINAL requires full scoring (use page context data when available)

14. USE CASES NEWLY ENTERED SCOPE THIS WEEK (moved in last 7 days):
(Use for: "which use cases were added this week?", "what moved into Q2?", "new use cases this week")
```sql
SELECT
    uc.USE_CASE_NAME, uc.ACCOUNT_NAME, uc.PARTNER_NAME,
    uc.USE_CASE_STAGE, uc.USE_CASE_EACV, uc.IS_COCO,
    uc.WORKLOADS, uc.TECHNICAL_USE_CASE,
    uc.DECISION_DATE, uc.GO_LIVE_DATE,
    CASE
        WHEN uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
        THEN uc.DECISION_DATE
        ELSE uc.GO_LIVE_DATE
    END AS SCOPE_ENTRY_DATE
FROM {SCHEMA}.DT_OKR_USE_CASES uc
WHERE (
    (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
     AND uc.DECISION_DATE >= DATEADD('day', -7, CURRENT_DATE())
     AND uc.DECISION_DATE <= '2026-07-31')
  OR
    (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
     AND uc.GO_LIVE_DATE >= DATEADD('day', -7, CURRENT_DATE())
     AND uc.GO_LIVE_DATE <= '2026-07-31')
)
-- Optional: AND uc.PARTNER_NAME IN (...) to scope to a partner
ORDER BY SCOPE_ENTRY_DATE DESC
LIMIT 30
```

15. USE CASES JUST OUTSIDE SCOPE BOUNDARY (likely moved out / would have been in scope last week):
(Use for: "which use cases moved out of Q2?", "what dropped out of scope?", "use cases that left Q2 this week")
```sql
SELECT
    uc.USE_CASE_NAME, uc.ACCOUNT_NAME, uc.PARTNER_NAME,
    uc.USE_CASE_STAGE, uc.USE_CASE_EACV, uc.IS_COCO,
    uc.WORKLOADS, uc.TECHNICAL_USE_CASE,
    uc.DECISION_DATE, uc.GO_LIVE_DATE,
    CASE
        WHEN uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
        THEN uc.DECISION_DATE
        ELSE uc.GO_LIVE_DATE
    END AS BOUNDARY_DATE
FROM {SCHEMA}.DT_OKR_USE_CASES uc
WHERE (
    (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
     AND uc.DECISION_DATE > '2026-07-31'
     AND uc.DECISION_DATE <= DATEADD('day', 14, '2026-07-31'))
  OR
    (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
     AND uc.GO_LIVE_DATE > '2026-07-31'
     AND uc.GO_LIVE_DATE <= DATEADD('day', 14, '2026-07-31'))
  OR
    (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
     AND uc.DECISION_DATE >= DATEADD('day', -7, '2026-05-01')
     AND uc.DECISION_DATE < '2026-05-01')
  OR
    (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
     AND uc.GO_LIVE_DATE >= DATEADD('day', -7, '2026-05-01')
     AND uc.GO_LIVE_DATE < '2026-05-01')
)
-- Optional: AND uc.PARTNER_NAME IN (...) to scope to a partner
ORDER BY BOUNDARY_DATE ASC
LIMIT 30
```

NOTE FOR PATTERNS 14 AND 15:
- Replace '2026-05-01' and '2026-07-31' with the ACTIVE FILTER date range from the sidebar (start_date and end_date).
- "Moved in" = SCOPE_ENTRY_DATE within last 7 days AND still inside the window.
- "Moved out" approximation = date just OUTSIDE the window boundary (within 14 days past end_date, or just before start_date). DT_OKR_USE_CASES has no historical snapshots, so true "removed" UCs are undetectable — Pattern 15 shows the nearest candidates.
- Credit impact of newly entered accounts: combine Pattern 14 account list with a credit lookup using Pattern 13 style join.

13. TOP TOKEN/CREDIT ACCOUNTS WITH USE CASE NAMES FOR A NAMED PARTNER
(Use this for: "which use cases / accounts are driving token usage for [partner]?"):
```sql
WITH partner_ucs AS (
    SELECT
        UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER,
        LISTAGG(DISTINCT USE_CASE_NAME, ' | ') WITHIN GROUP (ORDER BY USE_CASE_NAME) AS USE_CASES,
        LISTAGG(DISTINCT WORKLOADS,    ' | ') WITHIN GROUP (ORDER BY WORKLOADS)      AS WORKLOADS,
        COUNT(*) AS UC_COUNT,
        SUM(CASE WHEN IS_COCO THEN 1 ELSE 0 END) AS COCO_UCS
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME IN ('Cognizant Technology Solutions US Corp')  -- substitute correct partner + all aliases
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
          AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
          AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
    GROUP BY UPPER(ACCOUNT_NAME)
)
SELECT
    pu.ACCOUNT_NAME_UPPER                                                                            AS ACCOUNT,
    pu.USE_CASES,
    pu.WORKLOADS,
    pu.UC_COUNT,
    pu.COCO_UCS,
    ROUND(SUM(f.TOTAL_TOKENS), 0)                                                                    AS Q2_TOKENS,
    ROUND(SUM(f.TOTAL_TOKEN_CREDITS), 2)                                                             AS Q2_CREDITS,
    ROUND(SUM(CASE WHEN f.DS >= DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END), 0)        AS LAST7_TOKENS,
    ROUND(SUM(CASE WHEN f.DS >= DATEADD('day',-14,CURRENT_DATE())
                    AND f.DS <  DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END), 0)        AS PRIOR7_TOKENS,
    ROUND((SUM(CASE WHEN f.DS >= DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END)
          -SUM(CASE WHEN f.DS >= DATEADD('day',-14,CURRENT_DATE())
                     AND f.DS <  DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END))*100.0
          /NULLIF(SUM(CASE WHEN f.DS >= DATEADD('day',-14,CURRENT_DATE())
                            AND f.DS <  DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKENS END),0), 1) AS TOKEN_WOW_PCT,
    ROUND(SUM(CASE WHEN f.DS >= DATEADD('day',-7,CURRENT_DATE()) THEN f.TOTAL_TOKEN_CREDITS END), 2) AS LAST7_CREDITS
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN partner_ucs pu ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = pu.ACCOUNT_NAME_UPPER
WHERE f.DS >= '2026-05-01'
  AND f.SNOWFLAKE_ACCOUNT_TYPE = 'Customer'
  AND f.TOTAL_DAILY_REQUESTS > 0
GROUP BY 1, 2, 3, 4, 5
ORDER BY Q2_TOKENS DESC NULLS LAST
LIMIT 20
```

16. SURFACE BREAKDOWN FOR A NAMED PARTNER (CLI / Desktop / UI split + Maturity tier):
(Use for: "how is [partner] using CoCo?", "CLI vs desktop vs UI for [partner]", "which surface is [partner] using?")
```sql
WITH partner_ucs AS (
    SELECT DISTINCT UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME IN ('Deloitte Consulting')  -- substitute correct partner + all aliases
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
          AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
          AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
)
SELECT
    UPPER(f.SALESFORCE_ACCOUNT_NAME)                                                              AS ACCOUNT,
    ROUND(SUM(f.TOTAL_TOKEN_CREDITS), 2)                                                          AS Q2_CREDITS,
    ROUND(SUM(COALESCE(f.CLI_TOKEN_CREDITS,0))     *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS CLI_PCT,
    ROUND(SUM(COALESCE(f.DESKTOP_TOKEN_CREDITS,0)) *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS DESKTOP_PCT,
    ROUND(SUM(COALESCE(f.UI_TOKEN_CREDITS,0))      *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS UI_PCT,
    ROUND((SUM(COALESCE(f.CLI_TOKEN_CREDITS,0))+SUM(COALESCE(f.DESKTOP_TOKEN_CREDITS,0)))
          *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1)                                         AS DEPTH_SCORE,
    CASE
        WHEN (SUM(COALESCE(f.CLI_TOKEN_CREDITS,0))+SUM(COALESCE(f.DESKTOP_TOKEN_CREDITS,0)))
             *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0) >= 50 THEN 'Production'
        WHEN SUM(COALESCE(f.UI_TOKEN_CREDITS,0))*100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0) >= 70 THEN 'Exploratory'
        ELSE 'Mixed'
    END                                                                                           AS MATURITY,
    SUM(COALESCE(f.UI_CODING_AGENT_REQUESTS,0))                                                  AS AGENT_REQUESTS
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN partner_ucs pu ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = pu.ACCOUNT_NAME_UPPER
WHERE f.DS >= '2026-05-01' AND f.SNOWFLAKE_ACCOUNT_TYPE='Customer' AND f.TOTAL_DAILY_REQUESTS>0
GROUP BY 1 ORDER BY Q2_CREDITS DESC NULLS LAST LIMIT 20
```

17. CROSS-PARTNER SURFACE COMPARISON (which partner has deepest CoCo integration, production vs exploratory):
(Use for: "compare all GSIs on CLI/desktop/UI", "which partner is most production-ready?", "surface maturity across partners")
```sql
WITH all_partner_ucs AS (
    SELECT DISTINCT
        CASE WHEN PARTNER_NAME IN ('IBM','IBM Consulting') THEN 'IBM'
             WHEN PARTNER_NAME IN ('EY','Ernst & Young (EY)') THEN 'EY'
             ELSE PARTNER_NAME END AS CANONICAL_PARTNER,
        UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME IN (
        'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
        'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting',
        '7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai','Kipi.ai',
        'evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP',
        'LTM','LTI Mindtree','NTT DATA Group Corporation','phData, Inc.','Slalom, LLC.',
        'Squadron Data Inc','Tredence Inc.'
    )
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
          AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
          AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
)
SELECT
    pu.CANONICAL_PARTNER,
    ROUND(SUM(f.TOTAL_TOKEN_CREDITS),2)                                                           AS Q2_CREDITS,
    ROUND(SUM(COALESCE(f.CLI_TOKEN_CREDITS,0))     *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS CLI_PCT,
    ROUND(SUM(COALESCE(f.DESKTOP_TOKEN_CREDITS,0)) *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS DESKTOP_PCT,
    ROUND(SUM(COALESCE(f.UI_TOKEN_CREDITS,0))      *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS UI_PCT,
    ROUND((SUM(COALESCE(f.CLI_TOKEN_CREDITS,0))+SUM(COALESCE(f.DESKTOP_TOKEN_CREDITS,0)))
          *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1)                                         AS DEPTH_SCORE,
    CASE
        WHEN (SUM(COALESCE(f.CLI_TOKEN_CREDITS,0))+SUM(COALESCE(f.DESKTOP_TOKEN_CREDITS,0)))
             *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0)>=50 THEN 'Production'
        WHEN SUM(COALESCE(f.UI_TOKEN_CREDITS,0))*100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0)>=70 THEN 'Exploratory'
        ELSE 'Mixed'
    END                                                                                           AS MATURITY,
    SUM(COALESCE(f.UI_CODING_AGENT_REQUESTS,0))                                                  AS TOTAL_AGENT_REQS,
    COUNT(DISTINCT UPPER(f.SALESFORCE_ACCOUNT_NAME))                                             AS ACTIVE_ACCOUNTS
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN (SELECT DISTINCT CANONICAL_PARTNER, ACCOUNT_NAME_UPPER FROM all_partner_ucs) pu
    ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = pu.ACCOUNT_NAME_UPPER
WHERE f.DS>='2026-05-01' AND f.SNOWFLAKE_ACCOUNT_TYPE='Customer' AND f.TOTAL_DAILY_REQUESTS>0
GROUP BY 1 ORDER BY DEPTH_SCORE DESC NULLS LAST
```

18. SURFACE TREND OVER TIME FOR A PARTNER (weekly CLI/Desktop/UI mix evolution):
(Use for: "show [partner] surface trend over Q2", "is [partner] moving from UI to CLI?", "CoCo adoption maturity trajectory")
```sql
WITH partner_ucs AS (
    SELECT DISTINCT UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
    FROM {SCHEMA}.DT_OKR_USE_CASES
    WHERE PARTNER_NAME IN ('Deloitte Consulting')  -- substitute correct partner + aliases
    AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
          AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
      OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
          AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
)
SELECT
    DATE_TRUNC('week', f.DS)                                                                      AS WEEK_START,
    ROUND(SUM(f.TOTAL_TOKEN_CREDITS),2)                                                           AS WEEKLY_CREDITS,
    ROUND(SUM(COALESCE(f.CLI_TOKEN_CREDITS,0))     *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS CLI_PCT,
    ROUND(SUM(COALESCE(f.DESKTOP_TOKEN_CREDITS,0)) *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS DESKTOP_PCT,
    ROUND(SUM(COALESCE(f.UI_TOKEN_CREDITS,0))      *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1) AS UI_PCT,
    ROUND((SUM(COALESCE(f.CLI_TOKEN_CREDITS,0))+SUM(COALESCE(f.DESKTOP_TOKEN_CREDITS,0)))
          *100.0/NULLIF(SUM(f.TOTAL_TOKEN_CREDITS),0),1)                                         AS DEPTH_SCORE,
    COUNT(DISTINCT UPPER(f.SALESFORCE_ACCOUNT_NAME))                                             AS ACTIVE_ACCOUNTS
FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
INNER JOIN partner_ucs pu ON UPPER(f.SALESFORCE_ACCOUNT_NAME) = pu.ACCOUNT_NAME_UPPER
WHERE f.DS >= '2026-05-01' AND f.SNOWFLAKE_ACCOUNT_TYPE='Customer' AND f.TOTAL_DAILY_REQUESTS>0
GROUP BY DATE_TRUNC('week', f.DS) ORDER BY WEEK_START
```

NOTE for patterns 16-18:
- CLI_TOKEN_CREDITS = usage from terminal/shell. DESKTOP_TOKEN_CREDITS = VS Code extension. UI_TOKEN_CREDITS = Snowsight web browser.
- DEPTH_SCORE = CLI% + Desktop% — the higher this is, the more production-ready the integration.
- Maturity: Production (DEPTH>=50%), Mixed (some IDE), Exploratory (UI>=70% — POC/demo stage).
- AGENT_REQUESTS = UI_CODING_AGENT_REQUESTS — agentic CoCo usage within Snowsight.

7. WORKLOAD BREAKDOWN WITH COCO RATE (how many AI vs DE vs Analytics UCs, which workload has most CoCo):
```sql
SELECT
    CASE
        WHEN WORKLOADS ILIKE '%AI%' AND WORKLOADS NOT ILIKE '%Analytics%' AND WORKLOADS NOT ILIKE '%Data Engineering%' THEN 'AI'
        WHEN WORKLOADS ILIKE '%AI%' AND WORKLOADS ILIKE '%Analytics%' AND WORKLOADS NOT ILIKE '%Data Engineering%' THEN 'AI + Analytics'
        WHEN WORKLOADS ILIKE '%AI%' AND WORKLOADS ILIKE '%Data Engineering%' AND WORKLOADS NOT ILIKE '%Analytics%' THEN 'AI + DE'
        WHEN WORKLOADS ILIKE '%AI%' THEN 'AI + Mixed'
        WHEN WORKLOADS ILIKE '%Analytics%' AND WORKLOADS ILIKE '%Data Engineering%' THEN 'Analytics + DE'
        WHEN WORKLOADS ILIKE '%Analytics%' THEN 'Analytics'
        WHEN WORKLOADS ILIKE '%Data Engineering%' THEN 'Data Engineering'
        WHEN WORKLOADS ILIKE '%Platform%' THEN 'Platform'
        ELSE COALESCE(WORKLOADS, 'Unknown')
    END AS WORKLOAD_BUCKET,
    COUNT(*) AS TOTAL_UCS,
    COUNT(CASE WHEN IS_COCO THEN 1 END) AS COCO_UCS,
    ROUND(COUNT(CASE WHEN IS_COCO THEN 1 END)*100.0/NULLIF(COUNT(*),0),1) AS COCO_PCT,
    ROUND(SUM(USE_CASE_EACV)/1e6,2) AS TOTAL_EACV_M,
    ROUND(AVG(USE_CASE_EACV),0) AS AVG_EACV,
    COUNT(CASE WHEN USE_CASE_STAGE = '7 - Deployed' THEN 1 END) AS DEPLOYED_UCS
FROM {SCHEMA}.DT_OKR_USE_CASES
WHERE ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
        AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
    OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
-- Add partner filter if needed: AND PARTNER_NAME IN ('Deloitte Consulting')
GROUP BY 1 ORDER BY TOTAL_UCS DESC
```

8. MIGRATION TYPE BREAKDOWN (how many SQL Server, SAP, Teradata, Databricks etc.):
```sql
SELECT
    CASE
        WHEN USE_CASE_NAME ILIKE '%SAP%' THEN 'SAP'
        WHEN USE_CASE_NAME ILIKE '%SQL Server%' OR USE_CASE_NAME ILIKE '%SSAS%' OR USE_CASE_NAME ILIKE '%SSIS%' THEN 'SQL Server / SSAS / SSIS'
        WHEN USE_CASE_NAME ILIKE '%Databricks%' OR USE_CASE_NAME ILIKE '%Spark%' THEN 'Databricks / Spark'
        WHEN USE_CASE_NAME ILIKE '%Teradata%' THEN 'Teradata'
        WHEN USE_CASE_NAME ILIKE '%Hadoop%' OR USE_CASE_NAME ILIKE '%Cloudera%' OR USE_CASE_NAME ILIKE '%Hive%' THEN 'Hadoop / Cloudera'
        WHEN USE_CASE_NAME ILIKE '%Oracle%' THEN 'Oracle'
        WHEN USE_CASE_NAME ILIKE '%Informatica%' THEN 'Informatica'
        WHEN USE_CASE_NAME ILIKE '%Redshift%' THEN 'Redshift'
        WHEN USE_CASE_NAME ILIKE '%Greenplum%' THEN 'Greenplum'
        WHEN USE_CASE_NAME ILIKE '%Migrat%' THEN 'Generic Migration'
        ELSE 'Non-Migration'
    END AS MIGRATION_TYPE,
    COUNT(*) AS TOTAL_UCS,
    COUNT(CASE WHEN IS_COCO THEN 1 END) AS COCO_UCS,
    ROUND(COUNT(CASE WHEN IS_COCO THEN 1 END)*100.0/NULLIF(COUNT(*),0),1) AS COCO_PCT,
    ROUND(SUM(USE_CASE_EACV)/1e6,2) AS TOTAL_EACV_M,
    COUNT(CASE WHEN USE_CASE_STAGE = '7 - Deployed' THEN 1 END) AS DEPLOYED,
    ROUND(MEDIAN(DATEDIFF('day', DECISION_DATE, COALESCE(GO_LIVE_DATE, CURRENT_DATE()))),0) AS MEDIAN_DAYS
FROM {SCHEMA}.DT_OKR_USE_CASES
WHERE ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
        AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
    OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
GROUP BY 1 ORDER BY TOTAL_UCS DESC
```

9. TECHNICAL USE CASE CATEGORY BREAKDOWN (AI subcategories vs Analytics vs DE):
```sql
SELECT
    CASE
        WHEN TECHNICAL_USE_CASE ILIKE '%AI:%' THEN
            CASE WHEN TECHNICAL_USE_CASE ILIKE '%Conversational%' THEN 'AI: Conversational Assistants'
                 WHEN TECHNICAL_USE_CASE ILIKE '%Agent%' THEN 'AI: Agents'
                 WHEN TECHNICAL_USE_CASE ILIKE '%Machine Learning%' THEN 'AI: Machine Learning'
                 WHEN TECHNICAL_USE_CASE ILIKE '%Cortex AI Functions%' THEN 'AI: Cortex AI Functions'
                 ELSE 'AI: Other'
            END
        WHEN TECHNICAL_USE_CASE ILIKE '%Analytics:%' THEN
            CASE WHEN TECHNICAL_USE_CASE ILIKE '%Business Intelligence%' THEN 'Analytics: BI'
                 WHEN TECHNICAL_USE_CASE ILIKE '%Migration%' THEN 'Analytics: Migrations'
                 WHEN TECHNICAL_USE_CASE ILIKE '%Applied Analytics%' THEN 'Analytics: Applied'
                 ELSE 'Analytics: Other'
            END
        WHEN TECHNICAL_USE_CASE ILIKE '%DE:%' THEN 'Data Engineering'
        WHEN TECHNICAL_USE_CASE ILIKE '%Platform:%' THEN 'Platform'
        WHEN TECHNICAL_USE_CASE ILIKE '%Apps%' THEN 'Apps & Collab'
        ELSE COALESCE(TECHNICAL_USE_CASE, 'Unknown')
    END AS TECH_CATEGORY,
    COUNT(*) AS TOTAL_UCS,
    COUNT(CASE WHEN IS_COCO THEN 1 END) AS COCO_UCS,
    ROUND(COUNT(CASE WHEN IS_COCO THEN 1 END)*100.0/NULLIF(COUNT(*),0),1) AS COCO_PCT,
    ROUND(SUM(USE_CASE_EACV)/1e6,2) AS TOTAL_EACV_M,
    ROUND(AVG(USE_CASE_EACV),0) AS AVG_EACV
FROM {SCHEMA}.DT_OKR_USE_CASES
WHERE ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
        AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
    OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
GROUP BY 1 ORDER BY TOTAL_UCS DESC LIMIT 20
```

10. VELOCITY / TIME-TO-DEPLOY BY WORKLOAD (which workload is fastest to go live):
```sql
SELECT
    CASE
        WHEN WORKLOADS ILIKE '%AI%' AND WORKLOADS NOT ILIKE '%Analytics%' AND WORKLOADS NOT ILIKE '%Data Engineering%' THEN 'AI'
        WHEN WORKLOADS ILIKE '%Analytics%' AND WORKLOADS NOT ILIKE '%AI%' THEN 'Analytics'
        WHEN WORKLOADS ILIKE '%Data Engineering%' AND WORKLOADS NOT ILIKE '%AI%' AND WORKLOADS NOT ILIKE '%Analytics%' THEN 'Data Engineering'
        WHEN WORKLOADS ILIKE '%AI%' THEN 'AI + Mixed'
        WHEN WORKLOADS ILIKE '%Platform%' THEN 'Platform'
        ELSE COALESCE(WORKLOADS, 'Unknown')
    END AS WORKLOAD_BUCKET,
    IS_COCO,
    COUNT(*) AS UCS,
    ROUND(MEDIAN(DATEDIFF('day', DECISION_DATE, GO_LIVE_DATE)),0) AS MEDIAN_DAYS_TO_DEPLOY,
    ROUND(AVG(DATEDIFF('day', DECISION_DATE, GO_LIVE_DATE)),0) AS AVG_DAYS_TO_DEPLOY,
    COUNT(CASE WHEN USE_CASE_STAGE = '7 - Deployed' THEN 1 END) AS DEPLOYED
FROM {SCHEMA}.DT_OKR_USE_CASES
WHERE GO_LIVE_DATE IS NOT NULL
AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
        AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
    OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
GROUP BY 1, 2 ORDER BY WORKLOAD_BUCKET, IS_COCO
```

11. STAGE FUNNEL + AT-RISK PIPELINE (how UCs are distributed across stages, which are stuck):
```sql
SELECT
    USE_CASE_STAGE,
    COUNT(*) AS TOTAL_UCS,
    COUNT(CASE WHEN IS_COCO THEN 1 END) AS COCO_UCS,
    ROUND(COUNT(CASE WHEN IS_COCO THEN 1 END)*100.0/NULLIF(COUNT(*),0),1) AS COCO_PCT,
    ROUND(SUM(USE_CASE_EACV)/1e6,2) AS TOTAL_EACV_M,
    ROUND(AVG(DAYS_IN_CURRENT_STAGE),0) AS AVG_DAYS_IN_STAGE,
    COUNT(CASE WHEN DAYS_IN_CURRENT_STAGE > 90 THEN 1 END) AS AT_RISK_90D
FROM {SCHEMA}.DT_OKR_USE_CASES
WHERE ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
        AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
    OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
-- Add partner filter if needed: AND PARTNER_NAME IN ('Deloitte Consulting')
GROUP BY 1 ORDER BY USE_CASE_STAGE
```

12. PARTNER × WORKLOAD CROSS-TAB (which partners lead which workloads):
```sql
SELECT
    CASE WHEN PARTNER_NAME IN ('IBM','IBM Consulting') THEN 'IBM'
         WHEN PARTNER_NAME IN ('EY','Ernst & Young (EY)') THEN 'EY'
         WHEN PARTNER_NAME IN ('LTM','LTI Mindtree') THEN 'LTM'
         ELSE PARTNER_NAME END AS PARTNER,
    CASE
        WHEN WORKLOADS ILIKE '%AI%' AND WORKLOADS NOT ILIKE '%Analytics%' AND WORKLOADS NOT ILIKE '%Data Engineering%' THEN 'AI'
        WHEN WORKLOADS ILIKE '%Analytics%' AND WORKLOADS NOT ILIKE '%AI%' THEN 'Analytics'
        WHEN WORKLOADS ILIKE '%Data Engineering%' AND WORKLOADS NOT ILIKE '%AI%' AND WORKLOADS NOT ILIKE '%Analytics%' THEN 'DE'
        WHEN WORKLOADS ILIKE '%AI%' THEN 'AI+Mixed'
        WHEN WORKLOADS ILIKE '%Platform%' THEN 'Platform'
        ELSE 'Other'
    END AS WORKLOAD_BUCKET,
    COUNT(*) AS TOTAL_UCS,
    COUNT(CASE WHEN IS_COCO THEN 1 END) AS COCO_UCS,
    ROUND(COUNT(CASE WHEN IS_COCO THEN 1 END)*100.0/NULLIF(COUNT(*),0),1) AS COCO_PCT,
    ROUND(SUM(USE_CASE_EACV)/1e6,2) AS EACV_M
FROM {SCHEMA}.DT_OKR_USE_CASES
WHERE PARTNER_NAME IN (
    'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
    'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting')
AND ((USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
        AND DECISION_DATE >= '2026-05-01' AND DECISION_DATE <= '2026-07-31')
    OR (USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND GO_LIVE_DATE >= '2026-05-01' AND GO_LIVE_DATE <= '2026-07-31'))
GROUP BY 1, 2 ORDER BY PARTNER, TOTAL_UCS DESC
```
"""

_SQL_SYSTEM = f"""
{_SCHEMA_CONTEXT}

TASK: The user is on a specific dashboard page with active filters. You must answer ONLY based on the filtered scope shown in CURRENT PAGE DATA and ACTIVE FILTERS.

If the question can be answered from the page context numbers alone, respond with "NO_SQL_NEEDED" and nothing else.

If a SQL query is needed:
- Write ONE read-only SELECT statement
- Only SELECT. No INSERT/UPDATE/DELETE/DROP/CREATE.
- Always use fully qualified table names: {SCHEMA}.TABLE_NAME (or SNOWSCIENCE.LLM.* for usage tables)
- LIMIT 20 rows max
- Wrap the SQL in a ```sql ... ``` block
- For WoW questions: always compute LAST7, PRIOR7, WoW%, and WoW Δ in a single query
- For token drop investigations: break down by account and by surface (CLI/Desktop/UI)

SCOPE RULES — SIDEBAR FILTERS ARE ENFORCED BY DEFAULT:
The SIDEBAR FILTERS (region, partner, date range) apply to ALL question types — credit/token, WoW, adoption, and use case pattern questions — unless the user explicitly overrides them in their question.

Override examples (user must say one of these to expand scope):
  "compare all partners", "all GSIs", "all RSIs", "all managed partners", "across all partners"
  If none of those phrases appear → ALWAYS apply the sidebar partner filter.

PARTNER FILTER RESOLUTION:
- If sidebar has a specific partner selected → restrict PARTNER_NAME IN (...) to that partner (include all aliases).
- If sidebar has ALL partners (no partner filter) → query all managed partners (GSI + RSI + PSE).
- If user explicitly names a partner in the question → use that partner regardless of sidebar.
- If user says "all GSIs" / "all RSIs" / "all partners" → expand to that segment regardless of sidebar.

PATTERN SELECTION:
- Credit/token/WoW for a single partner → Pattern 1, 2, or 4 (filtered to sidebar partner or named partner)
- Credit/token/WoW across multiple partners → Pattern 5 or 6 (only when sidebar has no partner filter, or user asks for all)
- "which use cases/accounts driving usage for [partner]" → Pattern 13
- "use cases moved into scope this week" → Pattern 14 (use ACTIVE FILTER dates)
- "use cases moved out of scope" → Pattern 15 (use ACTIVE FILTER dates)
- "CLI vs Desktop vs UI breakdown for [partner]", "how is [partner] using CoCo?", "which surface?" → Pattern 16 (single partner) or Pattern 17 (all partners)
- "[partner] surface trend over Q2", "moving from UI to CLI?", "maturity trajectory?" → Pattern 18
- "which partner is most production-ready?", "compare partners on surface maturity?" → Pattern 17
- For GSIs specifically → filter to GSI partner names only
- For RSIs specifically → filter to RSI partner names only

USE CASE PATTERN SCOPE RULES:
- Workload/migration/velocity/stage questions → Patterns 7–12. Apply sidebar partner + date filters.
- If page context already has the breakdown table → answer from it (NO_SQL_NEEDED).
- For UC pattern questions about a SPECIFIC partner → add partner filter to Pattern 7, 8, 9, 10, or 11.
- Always use the ACTIVE FILTER date range for all UC queries.
"""

_ANSWER_SYSTEM = f"""
{_SCHEMA_CONTEXT}

You are a concise assistant answering questions about CoCo partner adoption and credit/token consumption.
Always respect the SIDEBAR FILTERS (region, partner, date range) for ALL question types by default.
Only expand scope beyond the sidebar filter when the user explicitly says "all partners", "all GSIs", "compare all", or names a different partner in their question.
Answer in 2-5 sentences. Be specific with numbers. If data is missing, say so clearly.
Do not make up numbers. Respond in plain text, no markdown headers.

When explaining WoW numbers:
- WoW% = percentage change in weekly spending rate (last 7d vs prior 7d)
- WoW Δ = absolute dollar/token change between the two weekly windows
- These do NOT represent total spend added this week — that is the LAST7 value itself
- Q2 running total as of last week = Q2 total minus last-7d spend

When discussing any use case or list of use cases, ALWAYS include its CoCo qualification status:
- IS_COCO_FINAL via keyword (IS_COCO=TRUE): state the source clearly:
    COCO_SOURCE='SE_COMMENTS'      → say "CoCo-tagged via SE Comments"
    COCO_SOURCE='PARTNER_COMMENTS' → say "CoCo-tagged via PSE/Partner Comments"
    COCO_SOURCE='FEATURE_FLAG'     → say "CoCo-tagged via Feature Flag"
    COCO_SOURCE='MULTIPLE'         → say "CoCo-tagged (multiple sources)"
- IS_COCO_FINAL via confidence score (IS_COCO=FALSE but CONFIDENCE_BAND='High'):
    → say "Confidence-qualified (High band, score=XX/100)"
- NOT IS_COCO_FINAL with Medium band (score 40–74):
    → say "Not IS_COCO_FINAL — Medium confidence (score=XX), not yet qualified"
- NOT IS_COCO_FINAL with Low band (score 1–39):
    → say "Not IS_COCO_FINAL — Low confidence (score=XX), weak usage signal"
- NOT IS_COCO_FINAL with No Signal (score 0):
    → say "Not CoCo — no usage signal detected"
If confidence band data is unavailable in the SQL result, use IS_COCO and COCO_SOURCE from DT_OKR_USE_CASES.
When summarising a partner's use cases, break down the count: X keyword-tagged (SE/PSE/flag) + Y confidence-scored + Z not IS_COCO_FINAL.
"""


def _extract_sql(text: str) -> str | None:
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        sql = match.group(1).strip()
        forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE)\b", re.IGNORECASE)
        if forbidden.search(sql):
            return None
        return sql
    return None


def _run_sql(conn, sql: str) -> str:
    try:
        df = conn.query(sql, ttl=0)
        if df.empty:
            return "Query returned no results."
        return df.to_string(index=False, max_rows=20)
    except Exception as e:
        return f"Query error: {e}"


def build_filter_context() -> str:
    """Build an explicit filter instruction block from current sidebar session state."""
    region = st.session_state.get("selected_region", "Global")
    selected_partners = st.session_state.get("selected_partners", [])
    start_date = st.session_state.get("okr_start_date")
    end_date = st.session_state.get("okr_end_date")

    lines = ["\nSIDEBAR FILTERS (apply ONLY for adoption/CoCo% questions, NOT for credit/token questions):"]

    theaters = resolve_region_theaters(region)
    if region == 'LATAM':
        # LATAM is a REGION_NAME, not a THEATER_NAME — there are zero rows with
        # THEATER_NAME='LATAM'. LATAM RSIs sit under AMSAcquisition and are scoped
        # by REGION_NAME, so emitting a theatre filter here matches nothing.
        lines.append("- Region: LATAM → filter: REGION_NAME = 'LATAM' "
                     "(LATAM is a region under the AMSAcquisition theatre, NOT a theatre; "
                     "never filter THEATER_NAME = 'LATAM')")
    elif theaters:
        lines.append(f"- Region: {region} → filter: THEATER_NAME IN ({', '.join(repr(t) for t in theaters)})")
    else:
        lines.append(f"- Region: Global (no theater filter needed)")

    if selected_partners:
        partner_names = resolve_partner_filter(selected_partners)
        plist = ", ".join(f"'{p}'" for p in sorted(partner_names))
        lines.append(f"- Sidebar partner filter: {', '.join(selected_partners)} → PARTNER_NAME IN ({plist})")
    else:
        lines.append("- Partners: All managed (GSI + RSI + PSE)")

    if start_date and end_date:
        lines.append(f"- Date range: {start_date} to {end_date} (use DECISION_DATE or GO_LIVE_DATE per stage)")

    lines.append("IMPORTANT: These sidebar filters apply to ALL question types (credits, tokens, WoW, use cases, patterns) by default. Only ignore them if the user explicitly asks for 'all partners', 'all GSIs', 'compare all', or names a different partner in their question.")

    return "\n".join(lines)


_GSI_PARTNERS = frozenset({'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
                            'Deloitte Consulting','EY','IBM'})
_NOAM_RSI_PARTNERS = frozenset({
    # Former Regional SIs
    '7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai',
    'evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP',
    'LTM','NTT DATA Group Corporation','phData, Inc.','Slalom, LLC.',
    'Squadron Data Inc','Tredence Inc.',
    # Former PSE Managed Partners
    'Spaulding Ridge','TEKsystems Global Services, LLC.','Blend360, LLC',
    'Tiger Analytics Inc.','Atrium','Perficient Inc.','SDK Tek Services Ltd.',
    'Merkle','Archetype Consulting','Everforth Apex Systems','Tata Consultancy Services',
    'OneSix','Icon Analytics','Sparq Holdings, Inc.','CitiusTech Inc.',
    'Hexaware Technologies',
})


def _partner_segment(name: str) -> str:
    if name in _GSI_PARTNERS: return 'GSI'
    if name in _NOAM_RSI_PARTNERS: return 'NOAM RSI'
    return 'Other'


def build_credit_wow_context(summary_df=None, partner_name: str = None) -> str:
    """Build credit/token WoW context for Ask AI from the partner summary data."""
    if summary_df is None or len(summary_df) == 0:
        return ""

    credit_cols = ['Q2_CREDITS', 'Q2_TOKENS', 'CREDITS_WOW_PCT', 'TOKENS_WOW_PCT',
                   'LAST7_CREDITS', 'PRIOR7_CREDITS', 'LAST7_TOKENS', 'PRIOR7_TOKENS']
    if not any(c in summary_df.columns for c in credit_cols):
        return ""

    import pandas as pd
    df = summary_df if partner_name is None else summary_df[summary_df['PARTNER_NAME'] == partner_name]
    if len(df) == 0:
        return ""

    lines = ["\nCREDIT/TOKEN CONSUMPTION CONTEXT (IS_COCO_FINAL accounts, portfolio-level WoW):"]
    lines.append(f"{'PARTNER':<40} {'SEG':<5} {'Q2 Credits':>12} {'Credits WoW%':>13} {'Credits WoW Δ':>14} {'Q2 Tokens':>12} {'Tokens WoW%':>12}")
    lines.append("-" * 115)

    for _, row in df.sort_values('Q2_CREDITS', ascending=False, na_position='last').iterrows():
        pname = str(row.get('PARTNER_NAME', ''))
        seg = _partner_segment(pname)
        q2c  = f"${float(row['Q2_CREDITS']):>11,.0f}"     if pd.notna(row.get('Q2_CREDITS'))     else "          N/A"
        cwow = f"{float(row['CREDITS_WOW_PCT']):>+12.1f}%" if pd.notna(row.get('CREDITS_WOW_PCT')) else "          N/A"
        l7c  = float(row.get('LAST7_CREDITS') or 0)
        p7c  = float(row.get('PRIOR7_CREDITS') or 0)
        cdelta = f"${l7c-p7c:>+13,.0f}"                   if pd.notna(row.get('LAST7_CREDITS'))  else "           N/A"
        tok  = float(row['Q2_TOKENS'])                     if pd.notna(row.get('Q2_TOKENS'))      else None
        qtok = f"{tok/1e9:>11.2f}B" if tok and tok>=1e9 else (f"{tok/1e6:>11.1f}M" if tok else "         N/A")
        twow = f"{float(row['TOKENS_WOW_PCT']):>+11.1f}%" if pd.notna(row.get('TOKENS_WOW_PCT')) else "         N/A"
        lines.append(f"{pname:<40} {seg:<5} {q2c} {cwow} {cdelta} {qtok} {twow}")

    # Totals by segment
    for seg_label, seg_set in [('GSI', _GSI_PARTNERS), ('NOAM RSI', _NOAM_RSI_PARTNERS), ('ALL', None)]:
        seg_df = df[df['PARTNER_NAME'].isin(seg_set)] if seg_set else df
        if len(seg_df) == 0: continue
        tot_q2c  = seg_df['Q2_CREDITS'].sum()    if 'Q2_CREDITS'  in seg_df.columns else 0
        tot_l7c  = seg_df['LAST7_CREDITS'].sum()  if 'LAST7_CREDITS' in seg_df.columns else 0
        tot_p7c  = seg_df['PRIOR7_CREDITS'].sum() if 'PRIOR7_CREDITS' in seg_df.columns else 0
        tot_tok  = seg_df['Q2_TOKENS'].sum()      if 'Q2_TOKENS'    in seg_df.columns else 0
        wow_c    = (tot_l7c - tot_p7c)*100/tot_p7c if tot_p7c else float('nan')
        tot_l7t  = seg_df['LAST7_TOKENS'].sum()   if 'LAST7_TOKENS'  in seg_df.columns else 0
        tot_p7t  = seg_df['PRIOR7_TOKENS'].sum()  if 'PRIOR7_TOKENS' in seg_df.columns else 0
        wow_t    = (tot_l7t - tot_p7t)*100/tot_p7t if tot_p7t else float('nan')
        lines.append(f"{'── ' + seg_label + ' TOTAL ──':<40} {'':5} ${tot_q2c:>11,.0f} {wow_c:>+12.1f}% ${tot_l7c-tot_p7c:>+13,.0f} {tot_tok/1e9:>11.2f}B {wow_t:>+11.1f}%")

    lines.append("Note: WoW Δ = last7d minus prior7d. Q2 running total as of last week = Q2 Credits minus last-7d credits.")
    return "\n".join(lines)


def build_uc_pattern_context(detail_df=None) -> str:
    """Build use case pattern context (workload + migration type + confidence band breakdowns) from loaded DataFrame."""
    import pandas as pd

    if detail_df is None or len(detail_df) == 0:
        return ""

    required = {'USE_CASE_NAME', 'WORKLOADS', 'IS_COCO', 'USE_CASE_STAGE', 'USE_CASE_EACV'}
    if not required.issubset(set(detail_df.columns)):
        return ""

    df = detail_df.copy()

    # Detect whether full confidence scoring columns are present
    has_confidence = all(c in df.columns for c in ['CONFIDENCE_BAND', 'IS_COCO_FINAL'])
    has_coco_source = 'COCO_SOURCE' in df.columns

    def _workload_bucket(w):
        if not isinstance(w, str):
            return 'Unknown'
        has_ai  = 'AI' in w
        has_an  = 'Analytics' in w
        has_de  = 'Data Engineering' in w
        has_pl  = 'Platform' in w
        has_ap  = 'Applications' in w or 'Collab' in w
        count = sum([has_ai, has_an, has_de, has_pl, has_ap])
        if has_ai and count == 1:  return 'AI'
        if has_ai and has_an and not has_de: return 'AI + Analytics'
        if has_ai and has_de and not has_an: return 'AI + DE'
        if has_ai: return 'AI + Mixed'
        if has_an and has_de: return 'Analytics + DE'
        if has_an: return 'Analytics'
        if has_de: return 'Data Engineering'
        if has_pl: return 'Platform'
        if has_ap: return 'Apps & Collab'
        return w[:30] if w else 'Unknown'

    _MIGRATION_PATTERNS = [
        ('SAP',                    lambda n: 'SAP' in n.upper()),
        ('SQL Server / SSAS',      lambda n: any(k in n.upper() for k in ['SQL SERVER','SSAS','SSIS'])),
        ('Databricks / Spark',     lambda n: any(k in n.upper() for k in ['DATABRICKS','SPARK'])),
        ('Teradata',               lambda n: 'TERADATA' in n.upper()),
        ('Hadoop / Cloudera',      lambda n: any(k in n.upper() for k in ['HADOOP','CLOUDERA','HIVE'])),
        ('Oracle',                 lambda n: 'ORACLE' in n.upper()),
        ('Informatica',            lambda n: 'INFORMATICA' in n.upper()),
        ('Redshift',               lambda n: 'REDSHIFT' in n.upper()),
        ('Greenplum',              lambda n: 'GREENPLUM' in n.upper()),
        ('Generic Migration',      lambda n: 'MIGRAT' in n.upper()),
    ]

    def _migration_type(name):
        if not isinstance(name, str):
            return None
        for label, check in _MIGRATION_PATTERNS:
            if check(name):
                return label
        return None

    df['_WORKLOAD_BUCKET'] = df['WORKLOADS'].apply(_workload_bucket)
    df['_MIGRATION_TYPE'] = df['USE_CASE_NAME'].apply(_migration_type)
    df['_IS_DEPLOYED'] = df['USE_CASE_STAGE'] == '7 - Deployed'
    df['_EACV'] = pd.to_numeric(df['USE_CASE_EACV'], errors='coerce').fillna(0)
    df['_IS_COCO'] = df['IS_COCO'].astype(bool)

    # Determine effective CoCo flag: IS_COCO_FINAL if available, else IS_COCO
    if has_confidence:
        df['_IS_COCO_FINAL'] = df['IS_COCO_FINAL'].astype(bool)
    else:
        df['_IS_COCO_FINAL'] = df['_IS_COCO']

    lines = []
    lines.append("\nUSE CASE PATTERN CONTEXT (current partner/filter scope):")
    conf_note = " [IS_COCO_FINAL]" if has_confidence else " [IS_COCO keyword only — confidence band not available]"
    lines.append(f"CoCo column used:{conf_note}")

    # --- Workload breakdown ---
    coco_col = '_IS_COCO_FINAL'
    wl_grp = df.groupby('_WORKLOAD_BUCKET').agg(
        TOTAL=('_EACV', 'count'),
        COCO=(coco_col, 'sum'),
        EACV_M=('_EACV', lambda x: round(x.sum()/1e6, 2)),
        DEPLOYED=('_IS_DEPLOYED', 'sum'),
    ).reset_index().sort_values('TOTAL', ascending=False)
    wl_grp['COCO_PCT'] = (wl_grp['COCO'] / wl_grp['TOTAL'].replace(0, float('nan')) * 100).round(1)

    coco_hdr = 'IS_COCO_FINAL' if has_confidence else 'CoCo(kw)'
    lines.append(f"\nWORKLOAD BREAKDOWN:")
    lines.append(f"  {'Workload':<22} {'Total':>6} {coco_hdr:>13} {'CoCo%':>7} {'EACV $M':>9} {'Deployed':>9}")
    lines.append("  " + "-"*70)
    for _, r in wl_grp.iterrows():
        lines.append(f"  {r['_WORKLOAD_BUCKET']:<22} {int(r['TOTAL']):>6} {int(r['COCO']):>13} {r['COCO_PCT']:>6.1f}% {r['EACV_M']:>9.2f} {int(r['DEPLOYED']):>9}")

    total_uc = len(df)
    total_coco_final = int(df['_IS_COCO_FINAL'].sum())
    total_eacv = round(df['_EACV'].sum()/1e6, 2)
    total_dep = int(df['_IS_DEPLOYED'].sum())
    lines.append(f"  {'TOTAL':<22} {total_uc:>6} {total_coco_final:>13} {total_coco_final*100.0/total_uc if total_uc else 0:>6.1f}% {total_eacv:>9.2f} {total_dep:>9}")

    # --- Confidence band / qualification breakdown (only when scoring data available) ---
    if has_confidence and has_coco_source:
        lines.append("\nCOCO QUALIFICATION BREAKDOWN:")
        lines.append(f"  {'Qualification Type':<42} {'Count':>6} {'EACV $M':>9}")
        lines.append("  " + "-"*60)

        # IS_COCO_FINAL via keyword — broken down by source
        for src_key, src_label in [
            ('SE_COMMENTS',      'IS_COCO_FINAL: keyword — SE Comments'),
            ('PARTNER_COMMENTS', 'IS_COCO_FINAL: keyword — PSE/Partner Comments'),
            ('FEATURE_FLAG',     'IS_COCO_FINAL: keyword — Feature Flag'),
            ('MULTIPLE',         'IS_COCO_FINAL: keyword — Multiple Sources'),
        ]:
            mask = df['_IS_COCO'].astype(bool) & (df['COCO_SOURCE'] == src_key)
            cnt = int(mask.sum())
            eacv = round(df.loc[mask, '_EACV'].sum()/1e6, 2) if cnt else 0.0
            if cnt > 0:
                lines.append(f"  {src_label:<42} {cnt:>6} {eacv:>9.2f}")

        # IS_COCO_FINAL via confidence score only (not keyword-tagged)
        conf_only_mask = (~df['_IS_COCO'].astype(bool)) & (df['CONFIDENCE_BAND'] == 'High')
        cnt_conf = int(conf_only_mask.sum())
        eacv_conf = round(df.loc[conf_only_mask, '_EACV'].sum()/1e6, 2) if cnt_conf else 0.0
        if cnt_conf > 0:
            lines.append(f"  {'IS_COCO_FINAL: confidence-scored (High band)':<42} {cnt_conf:>6} {eacv_conf:>9.2f}")

        # NOT IS_COCO_FINAL by band
        for band, label in [
            ('Medium',    'NOT IS_COCO_FINAL: Medium confidence (40–74)'),
            ('Low',       'NOT IS_COCO_FINAL: Low confidence (1–39)'),
            ('No Signal', 'NOT IS_COCO_FINAL: No Signal (score=0)'),
        ]:
            mask = (~df['_IS_COCO_FINAL']) & (df['CONFIDENCE_BAND'] == band)
            cnt = int(mask.sum())
            eacv = round(df.loc[mask, '_EACV'].sum()/1e6, 2) if cnt else 0.0
            lines.append(f"  {label:<42} {cnt:>6} {eacv:>9.2f}")

        lines.append(f"  {'TOTAL IS_COCO_FINAL':<42} {total_coco_final:>6} {round(df.loc[df['_IS_COCO_FINAL'],'_EACV'].sum()/1e6,2):>9.2f}")

    elif has_coco_source and not has_confidence:
        # Keyword breakdown only (no confidence band)
        lines.append("\nCOCO KEYWORD SOURCE BREAKDOWN (confidence band not available):")
        for src_key, src_label in [
            ('SE_COMMENTS',      'SE Comments'),
            ('PARTNER_COMMENTS', 'PSE/Partner Comments'),
            ('FEATURE_FLAG',     'Feature Flag'),
            ('MULTIPLE',         'Multiple Sources'),
        ]:
            mask = df['_IS_COCO'] & (df['COCO_SOURCE'] == src_key)
            cnt = int(mask.sum())
            if cnt > 0:
                lines.append(f"  {src_label}: {cnt}")

    # --- Migration type breakdown ---
    mig_df = df[df['_MIGRATION_TYPE'].notna()].copy()
    if len(mig_df) > 0:
        mig_grp = mig_df.groupby('_MIGRATION_TYPE').agg(
            TOTAL=('_EACV', 'count'),
            COCO=(coco_col, 'sum'),
            EACV_M=('_EACV', lambda x: round(x.sum()/1e6, 2)),
            DEPLOYED=('_IS_DEPLOYED', 'sum'),
        ).reset_index().sort_values('TOTAL', ascending=False)
        mig_grp['COCO_PCT'] = (mig_grp['COCO'] / mig_grp['TOTAL'].replace(0, float('nan')) * 100).round(1)

        lines.append(f"\nMIGRATION TYPE BREAKDOWN ({len(mig_df)} migration UCs out of {total_uc} total):")
        lines.append(f"  {'Migration Type':<26} {'Total':>6} {coco_hdr:>13} {'CoCo%':>7} {'EACV $M':>9} {'Deployed':>9}")
        lines.append("  " + "-"*74)
        for _, r in mig_grp.iterrows():
            lines.append(f"  {r['_MIGRATION_TYPE']:<26} {int(r['TOTAL']):>6} {int(r['COCO']):>13} {r['COCO_PCT']:>6.1f}% {r['EACV_M']:>9.2f} {int(r['DEPLOYED']):>9}")

    # --- Stage funnel ---
    stage_order = ['3 - Technical / Business Validation','4 - Use Case Won / Migration Plan',
                   '5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed']
    stg_grp = df.groupby('USE_CASE_STAGE').agg(
        TOTAL=('_EACV', 'count'),
        COCO=(coco_col, 'sum'),
        EACV_M=('_EACV', lambda x: round(x.sum()/1e6, 2)),
    ).reindex(stage_order).fillna(0).reset_index()

    lines.append("\nSTAGE FUNNEL:")
    lines.append(f"  {'Stage':<46} {'Total':>6} {coco_hdr:>13} {'EACV $M':>9}")
    lines.append("  " + "-"*78)
    for _, r in stg_grp.iterrows():
        snum = str(r['USE_CASE_STAGE'])[:45]
        lines.append(f"  {snum:<46} {int(r['TOTAL']):>6} {int(r['COCO']):>13} {r['EACV_M']:>9.2f}")

    lines.append(f"\nKey insight: AI workload has highest CoCo rate; Analytics and DE workloads are biggest CoCo opportunity.")
    lines.append("Migration UCs: SQL Server/SSAS has best CoCo attach (30%+); Databricks/Spark and legacy (Teradata/Hadoop) are lowest.")
    if has_confidence:
        lines.append("CoCo column = IS_COCO_FINAL (IS_COCO keyword OR confidence score High>=75). Use qualification breakdown above to explain WHY a UC is CoCo.")
    else:
        lines.append("CoCo column = IS_COCO keyword only. For confidence band details, select a specific partner in Partner Deep Dive.")

    return "\n".join(lines)


def ask_ai_agent(question: str, chat_history: list = None) -> dict:
    """Call COCO_AGENT via Cortex Agent REST API. Returns {answer, sql, sql_result}.
    Tries programmatic verified answer first; falls through to Cortex Agent if no match."""
    from utils.cortex_helpers import run_cortex_agent

    # ── Programmatic layer: deterministic exact-number answers ──────────────
    intent = detect_intent(question, chat_history)
    if intent["confidence"] == "high":
        try:
            conn = st.connection("snowflake")
            result = get_verified_answer(conn, question, intent)
            if result:
                return result
        except Exception:
            pass  # fall through to agent on any error
    # ────────────────────────────────────────────────────────────────────────

    # Inject active date range into the question for context
    start_date = str(st.session_state.get("okr_start_date", "2026-08-01"))
    end_date   = str(st.session_state.get("okr_end_date",   "2026-10-31"))
    augmented_question = (
        f"{question}\n\n"
        f"[Active date range: {start_date} to {end_date}]"
    )
    return run_cortex_agent(augmented_question, chat_history=chat_history)


def ask_ai(conn, question: str, page_context: str = "", debug: bool = False, chat_history: list = None):
    # ── Programmatic layer: deterministic exact-number answers ──────────────
    if not debug:
        intent = detect_intent(question, chat_history)
        if intent["confidence"] == "high":
            try:
                result = get_verified_answer(conn, question, intent)
                if result:
                    return result
            except Exception:
                pass  # fall through to LLM on any error
    # ────────────────────────────────────────────────────────────────────────

    filter_block = build_filter_context()

    # Inject active date range explicitly so LLM never falls back to hardcoded example dates
    start_date = str(st.session_state.get("okr_start_date", "2026-08-01"))
    end_date   = str(st.session_state.get("okr_end_date",   "2026-10-31"))
    date_override = (
        f"\nACTIVE DATE RANGE (use these in ALL SQL queries — override any example dates in SQL patterns above):"
        f"\n  start_date = '{start_date}'  |  end_date = '{end_date}'"
        f"\n  Stages 3-4 filter: DECISION_DATE >= '{start_date}' AND DECISION_DATE <= '{end_date}'"
        f"\n  Stages 5-7 filter: GO_LIVE_DATE  >= '{start_date}' AND GO_LIVE_DATE  <= '{end_date}'"
    )

    context_block = f"{filter_block}{date_override}\n\nCURRENT PAGE DATA:\n{page_context}\n" if page_context else f"{filter_block}{date_override}\n"

    # Build prior conversation block — include SQL + truncated results for multi-turn accuracy
    # (lets the LLM understand which partners/accounts were discussed in previous turns)
    _history_block = ""
    if chat_history:
        for msg in chat_history[-6:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            _history_block += f"{role}: {msg['content']}\n"
            if msg.get("sql"):
                _history_block += f"[SQL used in previous turn]:\n{msg['sql'][:600]}\n"
            if msg.get("sql_result"):
                _history_block += f"[SQL result (truncated)]:\n{msg['sql_result'][:400]}\n"
    prior_ctx = f"\nPRIOR CONVERSATION (use this to understand follow-up questions):\n{_history_block}\n" if _history_block else ""

    step1_prompt = f"{_SQL_SYSTEM}\n{context_block}{prior_ctx}\nUSER QUESTION: {question}"
    step1 = cortex_complete(conn, "claude-sonnet-4-5", step1_prompt)

    sql = None
    sql_result = ""
    if "NO_SQL_NEEDED" not in step1:
        sql = _extract_sql(step1)
        if sql:
            sql_result = _run_sql(conn, sql)

    data_block = f"\nSQL RESULT:\n{sql_result}\n" if sql_result else ""
    step2_prompt = (
        f"{_ANSWER_SYSTEM}\n"
        f"{context_block}"
        f"{prior_ctx}"
        f"{data_block}"
        f"\nUSER QUESTION: {question}"
    )
    answer = cortex_complete(conn, "claude-sonnet-4-5", step2_prompt)

    if debug:
        return {
            "answer": answer,
            "sql_needed": "NO_SQL_NEEDED" not in step1,
            "generated_sql": sql or "(no SQL extracted — answered from context)",
            "sql_result": sql_result or "(no result)",
            "step1_decision": step1[:800],
            "_sql": sql,
            "_sql_result": sql_result,
        }
    # Return answer + SQL metadata so caller can store in history for multi-turn
    return {"answer": answer, "sql": sql, "sql_result": sql_result}
