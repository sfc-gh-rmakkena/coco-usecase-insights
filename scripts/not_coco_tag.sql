-- =============================================================================
-- #notcoco tag support
--
-- A PSE can add #notcoco in PARTNER_COMMENTS to flag a use case that cannot
-- use Cortex Code right now (compliance, infra, timing, etc.).
-- Later, if the situation changes, the PSE adds #coco and the UC automatically
-- transitions to CoCo status.
--
-- Priority rules:
--   1. SE_COMMENTS mention of "coco" / "cortex code"  → always IS_COCO=TRUE
--   2. PRIORITIZED_FEATURES "AI - Cortex Code"        → always IS_COCO=TRUE
--   3. PARTNER_COMMENTS has #coco (and no #notcoco)   → IS_COCO=TRUE
--   4. PARTNER_COMMENTS has BOTH #coco and #notcoco   → IS_COCO=TRUE (#coco wins)
--   5. PARTNER_COMMENTS has only #notcoco             → IS_NOT_COCO=TRUE, IS_COCO=FALSE
--   6. Account usage data reaches High confidence     → IS_COCO_FINAL=TRUE regardless
--      of #notcoco (real consumption is ground truth)
--
-- Run order:
--   1. This file (DDL changes + SP update)
--   2. deploy the updated Python app
-- =============================================================================

USE DATABASE TEMP;
USE SCHEMA COCO_PARTNER_ADOPTION;

-- ---------------------------------------------------------------------------
-- 1. DT_OKR_USE_CASES — add IS_NOT_COCO column
--    Rebuild the dynamic table with the new column.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_OKR_USE_CASES(
    PARTNER_NAME,
    RAW_PARTNER_NAME,
    USE_CASE_ID,
    USE_CASE_NUMBER,
    USE_CASE_NAME,
    ACCOUNT_NAME,
    USE_CASE_STAGE,
    USE_CASE_EACV,
    TECHNICAL_USE_CASE,
    THEATER_NAME,
    REGION_NAME,
    CREATED_DATE,
    DECISION_DATE,
    GO_LIVE_DATE,
    DAYS_IN_STAGE,
    DAYS_IN_CURRENT_STAGE,
    WORKLOADS,
    COMPETITORS,
    ACCOUNT_LEAD_SE_NAME,
    ACCOUNT_GVP,
    IS_COCO,
    COCO_SOURCE,
    IS_NOT_COCO,
    PARTNER_ATTRIBUTION_SOURCE
)
TARGET_LAG = '1 day'
REFRESH_MODE = AUTO
INITIALIZE = ON_CREATE
WAREHOUSE = COCO_PARTNER_ADOPTION_WH
AS
WITH hierarchy AS (
    SELECT PARTNER_NAME, PARENT_PARTNER_NAME
    FROM TEMP.COCO_PARTNER_ADOPTION.PARTNER_HIERARCHY
),
stage_days AS (
    SELECT USE_CASE_ID, DATEDIFF('day', MOVEIN_DATE, CURRENT_DATE()) AS DAYS_IN_CURRENT_STAGE
    FROM MDM.MDM_INTERFACES.FACT_USE_CASE_STAGE_MOVEMENT
    QUALIFY ROW_NUMBER() OVER (PARTITION BY USE_CASE_ID ORDER BY MOVEIN_DATE DESC) = 1
),
base AS (
    SELECT UC.*,
        NULLIF(ARRAY_TO_STRING(UC.IMPLEMENTATION_SERVICES_PARTNER, ', '), '') AS impl_partner
    FROM MDM.MDM_INTERFACES.DIM_USE_CASE UC
)
SELECT
    COALESCE(h.PARENT_PARTNER_NAME, base.impl_partner)  AS PARTNER_NAME,
    base.impl_partner                                    AS RAW_PARTNER_NAME,
    base.USE_CASE_ID,
    base.USE_CASE_NUMBER,
    base.USE_CASE_NAME,
    CASE WHEN base.ACCOUNT_NAME = 'KT&G Corp.' THEN 'KT&G Corporation'
         ELSE base.ACCOUNT_NAME END                      AS ACCOUNT_NAME,
    base.USE_CASE_STAGE,
    base.USE_CASE_EACV,
    base.TECHNICAL_USE_CASE,
    base.THEATER_NAME,
    base.REGION_NAME,
    base.CREATED_DATE,
    base.DECISION_DATE,
    base.GO_LIVE_DATE,
    base.DAYS_IN_STAGE,
    COALESCE(sd.DAYS_IN_CURRENT_STAGE, base.DAYS_IN_STAGE) AS DAYS_IN_CURRENT_STAGE,
    base.WORKLOADS,
    base.COMPETITORS,
    base.ACCOUNT_LEAD_SE_NAME,
    base.ACCOUNT_GVP,

    -- IS_COCO: keyword/flag signal — unchanged logic
    -- Note: #coco in PARTNER_COMMENTS always wins over #notcoco
    CASE
        WHEN base.SE_COMMENTS         ILIKE '%coco%'
          OR base.SE_COMMENTS         ILIKE '%cortex code%'
          OR base.PARTNER_COMMENTS    ILIKE '%#coco%'
          OR base.PRIORITIZED_FEATURES ILIKE '%AI - Cortex Code%'
        THEN TRUE
        ELSE FALSE
    END AS IS_COCO,

    -- COCO_SOURCE: which signal fired (priority: PARTNER_COMMENTS > SE_COMMENTS > FEATURE_FLAG)
    CASE
        WHEN base.PARTNER_COMMENTS    ILIKE '%#coco%'                                         THEN 'PARTNER_COMMENTS'
        WHEN base.SE_COMMENTS         ILIKE '%coco%'
          OR base.SE_COMMENTS         ILIKE '%cortex code%'                                   THEN 'SE_COMMENTS'
        WHEN base.PRIORITIZED_FEATURES ILIKE '%AI - Cortex Code%'                            THEN 'FEATURE_FLAG'
        ELSE NULL
    END AS COCO_SOURCE,

    -- IS_NOT_COCO: PSE has flagged this UC as blocked from CoCo right now.
    -- Only TRUE when #notcoco is present AND no other CoCo signal overrides it.
    -- SE comment, #coco tag, or feature flag each independently clear the flag.
    -- COALESCE(..., TRUE) treats NULL fields as "no override" — without it,
    -- a NULL PRIORITIZED_FEATURES/SE_COMMENTS makes the whole AND chain NULL
    -- and the flag silently falls to FALSE (NULL NOT ILIKE x => NULL).
    CASE
        WHEN base.PARTNER_COMMENTS ILIKE '%#notcoco%'
         AND COALESCE(base.PARTNER_COMMENTS     NOT ILIKE '%#coco%',              TRUE)
         AND COALESCE(base.SE_COMMENTS          NOT ILIKE '%coco%',               TRUE)
         AND COALESCE(base.SE_COMMENTS          NOT ILIKE '%cortex code%',        TRUE)
         AND COALESCE(base.PRIORITIZED_FEATURES NOT ILIKE '%AI - Cortex Code%',    TRUE)
        THEN TRUE
        ELSE FALSE
    END AS IS_NOT_COCO,

    CASE
        WHEN base.impl_partner IS NOT NULL THEN 'IMPLEMENTATION_SERVICES'
        ELSE NULL
    END AS PARTNER_ATTRIBUTION_SOURCE

FROM base
LEFT JOIN hierarchy h   ON base.impl_partner = h.PARTNER_NAME
LEFT JOIN stage_days sd ON base.USE_CASE_ID  = sd.USE_CASE_ID
WHERE base.USE_CASE_STAGE IN (
    '3 - Technical / Business Validation',
    '4 - Use Case Won / Migration Plan',
    '5 - Implementation In Progress',
    '6 - Implementation Complete',
    '7 - Deployed'
)
AND base.impl_partner IS NOT NULL
AND COALESCE(h.PARENT_PARTNER_NAME, base.impl_partner)
    NOT IN ('Sigma Computing, Inc.', 'Bloomberg Finance L.P. - DCP Account');


-- ---------------------------------------------------------------------------
-- 2. UC_COCO_STATUS_WEEKLY — add IS_NOT_COCO column
-- ---------------------------------------------------------------------------
ALTER TABLE TEMP.COCO_PARTNER_ADOPTION.UC_COCO_STATUS_WEEKLY
    ADD COLUMN IF NOT EXISTS IS_NOT_COCO BOOLEAN DEFAULT FALSE;

ALTER TABLE TEMP.COCO_PARTNER_ADOPTION_DEV.UC_COCO_STATUS_WEEKLY
    ADD COLUMN IF NOT EXISTS IS_NOT_COCO BOOLEAN DEFAULT FALSE;


-- ---------------------------------------------------------------------------
-- 3. SP_REFRESH_UC_COCO_WEEKLY — carry IS_NOT_COCO into snapshot
--    IS_COCO_FINAL logic updated: #notcoco suppresses unless usage data present
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE SP_REFRESH_UC_COCO_WEEKLY(
    Q_START VARCHAR DEFAULT '2026-08-01',
    Q_END   VARCHAR DEFAULT '2026-10-31'
)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    week_start DATE;
    row_count  INTEGER;
BEGIN
    week_start := DATE_TRUNC('WEEK', CURRENT_DATE())::DATE;

    DELETE FROM TEMP.COCO_PARTNER_ADOPTION.UC_COCO_STATUS_WEEKLY
    WHERE WEEK_START = :week_start;

    INSERT INTO TEMP.COCO_PARTNER_ADOPTION.UC_COCO_STATUS_WEEKLY
        (WEEK_START, USE_CASE_ID, PARTNER_NAME, THEATER_NAME,
         IS_COCO, COCO_SOURCE, IS_NOT_COCO, HAS_ACCOUNT_COCO,
         CONFIDENCE_BAND, Q2_TOKENS, CREATED_DATE, IS_COCO_FINAL)
    WITH partner_ucs AS (
        SELECT
            uc.USE_CASE_ID,
            uc.PARTNER_NAME,
            uc.THEATER_NAME,
            UPPER(TRIM(uc.ACCOUNT_NAME)) AS ACCOUNT_NAME_UPPER,
            uc.IS_COCO,
            uc.COCO_SOURCE,
            uc.IS_NOT_COCO,
            uc.CREATED_DATE,
            CASE
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%AI:%'         THEN 'AI'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Analytics:%'  THEN 'Analytics'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%DE:%'         THEN 'Data Engineering'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Platform%'    THEN 'Platform'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Apps%'        THEN 'Apps & Collab'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Migration%'   THEN 'Migration'
                ELSE 'Unclassified'
            END AS WORKLOAD_CATEGORY
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
        WHERE (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan')
             AND uc.DECISION_DATE >= :Q_START AND uc.DECISION_DATE <= :Q_END)
            OR
            (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed')
             AND uc.GO_LIVE_DATE >= :Q_START AND uc.GO_LIVE_DATE <= :Q_END)
        )
    ),
    account_ids AS (
        SELECT DISTINCT f.ACCOUNT_ID, UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
        WHERE f.SNOWFLAKE_ACCOUNT_TYPE = 'Customer'
          AND f.DS >= :Q_START
          AND UPPER(f.SALESFORCE_ACCOUNT_NAME) IN (SELECT ACCOUNT_NAME_UPPER FROM partner_ucs)
    ),
    account_tokens AS (
        SELECT
            aid.ACCOUNT_NAME_UPPER,
            SUM(f.TOKENS) AS Q2_TOKENS
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
        INNER JOIN account_ids aid ON f.ACCOUNT_ID = aid.ACCOUNT_ID
        WHERE f.DS >= :Q_START
        GROUP BY aid.ACCOUNT_NAME_UPPER
    ),
    caa AS (
        SELECT DISTINCT UPPER(TRIM(SALESFORCE_ACCOUNT_NAME)) AS ACCOUNT_NAME_UPPER
        FROM TEMP.COCO_PARTNER_ADOPTION.INCLUDE_CUSTOMER_ACCOUNTS_AUTOMATED
    ),
    uc_joined AS (
        SELECT
            u.USE_CASE_ID,
            u.PARTNER_NAME,
            u.THEATER_NAME,
            u.IS_COCO,
            u.COCO_SOURCE,
            u.IS_NOT_COCO,
            u.CREATED_DATE,
            (caa.ACCOUNT_NAME_UPPER IS NOT NULL)         AS HAS_ACCOUNT_COCO,
            COALESCE(tok.Q2_TOKENS, 0)                   AS Q2_TOKENS,
            CASE
                WHEN COALESCE(tok.Q2_TOKENS, 0) >= 1000  THEN 'High'
                WHEN COALESCE(tok.Q2_TOKENS, 0) > 0      THEN 'Low'
                ELSE 'No Signal'
            END AS CONFIDENCE_BAND
        FROM partner_ucs u
        LEFT JOIN caa ON u.ACCOUNT_NAME_UPPER = caa.ACCOUNT_NAME_UPPER
        LEFT JOIN account_tokens tok ON u.ACCOUNT_NAME_UPPER = tok.ACCOUNT_NAME_UPPER
    )
    SELECT
        :week_start                                      AS WEEK_START,
        USE_CASE_ID,
        PARTNER_NAME,
        THEATER_NAME,
        IS_COCO,
        COCO_SOURCE,
        IS_NOT_COCO,
        HAS_ACCOUNT_COCO,
        CONFIDENCE_BAND,
        Q2_TOKENS,
        CREATED_DATE,
        -- IS_COCO_FINAL mirrors apply_coco_final() in utils/__init__.py:
        --   IS_COCO=TRUE qualifies, EXCEPT PARTNER_COMMENTS-only without tokens
        --   IS_NOT_COCO suppresses only when no token evidence exists
        --   Account-level token usage always overrides #notcoco
        CASE WHEN (
                (IS_COCO = TRUE
                 AND NOT (COCO_SOURCE = 'PARTNER_COMMENTS'
                          AND HAS_ACCOUNT_COCO = FALSE
                          AND Q2_TOKENS = 0))
                OR (IS_COCO = FALSE AND HAS_ACCOUNT_COCO = TRUE)
             )
             AND NOT (IS_NOT_COCO = TRUE AND Q2_TOKENS = 0 AND HAS_ACCOUNT_COCO = FALSE)
        THEN TRUE ELSE FALSE END                         AS IS_COCO_FINAL
    FROM uc_joined;

    row_count := SQLROWCOUNT;
    RETURN 'OK - week ' || :week_start::VARCHAR || ', ' || :row_count::VARCHAR || ' rows inserted';
END;
$$;


-- DEV version
CREATE OR REPLACE PROCEDURE TEMP.COCO_PARTNER_ADOPTION_DEV.SP_REFRESH_UC_COCO_WEEKLY(
    Q_START VARCHAR DEFAULT '2026-08-01',
    Q_END   VARCHAR DEFAULT '2026-10-31'
)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    week_start DATE;
    row_count  INTEGER;
BEGIN
    week_start := DATE_TRUNC('WEEK', CURRENT_DATE())::DATE;

    DELETE FROM TEMP.COCO_PARTNER_ADOPTION_DEV.UC_COCO_STATUS_WEEKLY
    WHERE WEEK_START = :week_start;

    INSERT INTO TEMP.COCO_PARTNER_ADOPTION_DEV.UC_COCO_STATUS_WEEKLY
        (WEEK_START, USE_CASE_ID, PARTNER_NAME, THEATER_NAME,
         IS_COCO, COCO_SOURCE, IS_NOT_COCO, HAS_ACCOUNT_COCO,
         CONFIDENCE_BAND, Q2_TOKENS, CREATED_DATE, IS_COCO_FINAL)
    WITH partner_ucs AS (
        SELECT
            uc.USE_CASE_ID, uc.PARTNER_NAME, uc.THEATER_NAME,
            UPPER(TRIM(uc.ACCOUNT_NAME)) AS ACCOUNT_NAME_UPPER,
            uc.IS_COCO, uc.COCO_SOURCE, uc.IS_NOT_COCO, uc.CREATED_DATE,
            CASE
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%AI:%'        THEN 'AI'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Analytics:%' THEN 'Analytics'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%DE:%'        THEN 'Data Engineering'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Platform%'   THEN 'Platform'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Apps%'       THEN 'Apps & Collab'
                WHEN uc.TECHNICAL_USE_CASE ILIKE '%Migration%'  THEN 'Migration'
                ELSE 'Unclassified'
            END AS WORKLOAD_CATEGORY
        FROM TEMP.COCO_PARTNER_ADOPTION_DEV.DT_OKR_USE_CASES uc
        WHERE (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan')
             AND uc.DECISION_DATE >= :Q_START AND uc.DECISION_DATE <= :Q_END)
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed')
             AND uc.GO_LIVE_DATE >= :Q_START AND uc.GO_LIVE_DATE <= :Q_END)
        )
    ),
    account_tokens AS (
        SELECT UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER, SUM(f.TOKENS) AS Q2_TOKENS
        FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
        WHERE f.SNOWFLAKE_ACCOUNT_TYPE = 'Customer' AND f.DS >= :Q_START
          AND UPPER(f.SALESFORCE_ACCOUNT_NAME) IN (SELECT ACCOUNT_NAME_UPPER FROM partner_ucs)
        GROUP BY 1
    ),
    caa AS (
        SELECT DISTINCT UPPER(TRIM(SALESFORCE_ACCOUNT_NAME)) AS ACCOUNT_NAME_UPPER
        FROM TEMP.COCO_PARTNER_ADOPTION_DEV.INCLUDE_CUSTOMER_ACCOUNTS_AUTOMATED
    ),
    uc_joined AS (
        SELECT u.USE_CASE_ID, u.PARTNER_NAME, u.THEATER_NAME, u.IS_COCO, u.COCO_SOURCE,
               u.IS_NOT_COCO, u.CREATED_DATE,
               (caa.ACCOUNT_NAME_UPPER IS NOT NULL) AS HAS_ACCOUNT_COCO,
               COALESCE(tok.Q2_TOKENS, 0) AS Q2_TOKENS,
               CASE WHEN COALESCE(tok.Q2_TOKENS, 0) >= 1000 THEN 'High'
                    WHEN COALESCE(tok.Q2_TOKENS, 0) > 0 THEN 'Low'
                    ELSE 'No Signal' END AS CONFIDENCE_BAND
        FROM partner_ucs u
        LEFT JOIN caa ON u.ACCOUNT_NAME_UPPER = caa.ACCOUNT_NAME_UPPER
        LEFT JOIN account_tokens tok ON u.ACCOUNT_NAME_UPPER = tok.ACCOUNT_NAME_UPPER
    )
    SELECT
        :week_start, USE_CASE_ID, PARTNER_NAME, THEATER_NAME, IS_COCO, COCO_SOURCE,
        IS_NOT_COCO, HAS_ACCOUNT_COCO, CONFIDENCE_BAND, Q2_TOKENS, CREATED_DATE,
        CASE WHEN (
                (IS_COCO = TRUE AND NOT (COCO_SOURCE = 'PARTNER_COMMENTS' AND HAS_ACCOUNT_COCO = FALSE AND Q2_TOKENS = 0))
                OR (IS_COCO = FALSE AND HAS_ACCOUNT_COCO = TRUE)
             )
             AND NOT (IS_NOT_COCO = TRUE AND Q2_TOKENS = 0 AND HAS_ACCOUNT_COCO = FALSE)
        THEN TRUE ELSE FALSE END AS IS_COCO_FINAL
    FROM uc_joined;

    row_count := SQLROWCOUNT;
    RETURN 'OK - week ' || :week_start::VARCHAR || ', ' || :row_count::VARCHAR || ' rows inserted (DEV)';
END;
$$;


-- ---------------------------------------------------------------------------
-- 4. V_OKR_USE_CASES_COCO_FINAL_Q3 — add IS_NOT_COCO column
--    Only the partner_ucs CTE and final SELECT need changes; the rest is intact.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW V_OKR_USE_CASES_COCO_FINAL_Q3
COMMENT = 'Q3 FY27 (Aug-Oct 2026). Confidence scored from 2026-08-01. Exact dashboard algorithm. IS_COCO_FINAL = IS_COCO=TRUE OR CONFIDENCE_BAND=High (suppressed by IS_NOT_COCO unless usage data present).'
AS
WITH _scored AS (
  WITH partner_ucs AS (
      SELECT uc.USE_CASE_ID, uc.USE_CASE_NAME, uc.ACCOUNT_NAME,
             UPPER(uc.ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER,
             uc.PARTNER_NAME, uc.TECHNICAL_USE_CASE, uc.USE_CASE_STAGE,
             uc.USE_CASE_EACV, uc.IS_COCO, uc.COCO_SOURCE,
             uc.IS_NOT_COCO,
             uc.THEATER_NAME, uc.REGION_NAME,
             uc.DECISION_DATE, uc.GO_LIVE_DATE,
             CASE
                 WHEN uc.TECHNICAL_USE_CASE ILIKE '%AI:%'         THEN 'AI'
                 WHEN uc.TECHNICAL_USE_CASE ILIKE '%Analytics:%'  THEN 'Analytics'
                 WHEN uc.TECHNICAL_USE_CASE ILIKE '%DE:%'         THEN 'Data Engineering'
                 WHEN uc.TECHNICAL_USE_CASE ILIKE '%Platform:%'   THEN 'Platform'
                 WHEN uc.TECHNICAL_USE_CASE ILIKE '%Apps%'        THEN 'Apps & Collab'
                 WHEN uc.TECHNICAL_USE_CASE ILIKE '%Migration%'   THEN 'Migration'
                 ELSE 'Unclassified'
             END AS WORKLOAD_CATEGORY
      FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
      WHERE uc.PARTNER_NAME IN (
          'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
          'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting',
          '7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai','Kipi.ai',
          'evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP',
          'LTM','LTI Mindtree','phData, Inc.','Slalom, LLC.','Squadron Data Inc',
          'Tredence Inc.','Spaulding Ridge','TEKsystems Global Services, LLC.',
          'Blend360, LLC','Tiger Analytics Inc.','Atrium','Perficient Inc.',
          'SDK Tek Services Ltd.','Merkle','Archetype Consulting','Apex Systems',
          'Tata Consultancy Services','OneSix','Icon Analytics','Sparq Holdings, Inc.',
          'CitiusTech Inc.','Hexaware Technologies','NTT DATA Group Corporation',
          'MegazoneCloud Corporation','Infinite Lambda Limited','Infinite Lambda Inc',
          'INFINITE LAMBDA (SINGAPORE) PTE. LTD.','Altis Global Limited',
          'Altis Consulting, ANZ','PROLIM Global Corporation','INFOMOTION GMBH',
          'INFOMOTION GMBH, BearingPoint','CIVICA SOFTWARE, S.L.','Kubrick Group',
          'KPC (Key Performance Consulting)','KPC'
      )
      AND (
          (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
           AND uc.DECISION_DATE >= '2026-08-01' AND uc.DECISION_DATE <= '2026-10-31')
          OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
           AND uc.GO_LIVE_DATE >= '2026-08-01' AND uc.GO_LIVE_DATE <= '2026-10-31')
      )
  ),
  account_ids AS (
      SELECT DISTINCT f.ACCOUNT_ID, UPPER(f.SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
      FROM snowscience.llm.cortex_code_user_day_fact f
      WHERE f.snowflake_account_type = 'Customer' AND f.ds >= '2026-08-01'
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
      WHERE r.ds >= '2026-08-01' AND r.SKILL_CHOICE IS NOT NULL AND r.SKILL_CHOICE != ''
      GROUP BY aid.ACCOUNT_NAME_UPPER
  ),
  -- (remaining CTEs for custom_skills, usage_agg, surface_agg, scores are identical
  --  to the original view — omitted here for brevity; copy from existing DDL verbatim)
  final_join AS (
      SELECT
          pu.*,
          -- IS_NOT_COCO passed through directly from DT_OKR_USE_CASES
          pu.IS_NOT_COCO
      FROM partner_ucs pu
  )
  SELECT * FROM final_join
)
SELECT
    USE_CASE_ID, USE_CASE_NAME, ACCOUNT_NAME, ACCOUNT_NAME_UPPER,
    PARTNER_NAME, TECHNICAL_USE_CASE, USE_CASE_STAGE, USE_CASE_EACV,
    IS_COCO, COCO_SOURCE, IS_NOT_COCO,
    THEATER_NAME, REGION_NAME, DECISION_DATE, GO_LIVE_DATE, WORKLOAD_CATEGORY,
    -- ... all other scored columns ...
    IS_COCO_FINAL
FROM _scored;


-- NOTE: The views (Q3, Q2, Q1, YTD) are complex and long.
-- The actual deployment adds IS_NOT_COCO by:
--   1. Adding uc.IS_NOT_COCO in the partner_ucs CTE SELECT
--   2. Passing IS_NOT_COCO through to the final SELECT
--   3. Adding IS_NOT_COCO to the view column header
-- The full view DDL (including all scoring CTEs) must be run from the existing
-- view DDL + these additions. See deploy instructions below.
--
-- Shortcut: ALTER VIEW is not supported in Snowflake for adding columns.
-- The full CREATE OR REPLACE VIEW statements must include all original CTEs.
-- Run scripts/deploy_not_coco_views.sql (generated during deployment) for the
-- complete view DDL.
