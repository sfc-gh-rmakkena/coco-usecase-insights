-- =============================================================================
-- UC_COCO_STATUS_WEEKLY  — weekly per-UC IS_COCO_FINAL snapshot
--
-- Purpose: detect when a use case TRANSITIONS into CoCo status (False → True)
--          rather than using CREATED_DATE, which only tells you when the UC
--          record was logged, not when CoCo evidence first appeared.
--
-- IS_COCO_FINAL logic (mirrors Python apply_coco_final()):
--   TRUE when:
--     (a) IS_COCO = TRUE from DT_OKR (SE_COMMENTS / FEATURE_FLAG / PARTNER_COMMENTS)
--         EXCEPT: PARTNER_COMMENTS-only UCs also need account-level CoCo evidence
--     (b) IS_COCO = FALSE but account is in INCLUDE_CUSTOMER_ACCOUNTS_AUTOMATED
--         (account-level consumption signal, approximates High confidence band)
--
-- Note: CONFIDENCE_BAND here is simplified (account-presence based, not the full
--       4-signal scoring the app uses for display). Transitions are still captured
--       correctly because IS_COCO_FINAL is binary.
--
-- Run: CALL SP_REFRESH_UC_COCO_WEEKLY();  (or let TASK_UC_COCO_WEEKLY fire Monday)
-- =============================================================================

USE DATABASE TEMP;
USE SCHEMA COCO_PARTNER_ADOPTION;

-- ---------------------------------------------------------------------------
-- 1. Snapshot table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS UC_COCO_STATUS_WEEKLY (
    WEEK_START      DATE             NOT NULL,
    USE_CASE_ID     VARCHAR(255)     NOT NULL,
    PARTNER_NAME    VARCHAR(255),
    THEATER_NAME    VARCHAR(100),
    IS_COCO         BOOLEAN          DEFAULT FALSE,
    COCO_SOURCE     VARCHAR(50),
    HAS_ACCOUNT_COCO BOOLEAN         DEFAULT FALSE,  -- from INCLUDE_CUSTOMER_ACCOUNTS_AUTOMATED
    IS_COCO_FINAL   BOOLEAN          DEFAULT FALSE,
    SAVED_AT        TIMESTAMP_NTZ    DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (WEEK_START, USE_CASE_ID)
);

-- DEV version
CREATE TABLE IF NOT EXISTS TEMP.COCO_PARTNER_ADOPTION_DEV.UC_COCO_STATUS_WEEKLY
    LIKE TEMP.COCO_PARTNER_ADOPTION.UC_COCO_STATUS_WEEKLY;

-- ---------------------------------------------------------------------------
-- 2. Stored procedure — run once manually then weekly via Task
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE SP_REFRESH_UC_COCO_WEEKLY(
    Q_START VARCHAR DEFAULT '2026-08-01',   -- Q3 FY27 start
    Q_END   VARCHAR DEFAULT '2026-10-31'    -- Q3 FY27 end
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    week_start DATE;
    row_count  INTEGER;
BEGIN
    week_start := DATE_TRUNC('WEEK', CURRENT_DATE())::DATE;

    -- Idempotent: delete this week's rows before re-inserting
    DELETE FROM TEMP.COCO_PARTNER_ADOPTION.UC_COCO_STATUS_WEEKLY
    WHERE WEEK_START = :week_start;

    INSERT INTO TEMP.COCO_PARTNER_ADOPTION.UC_COCO_STATUS_WEEKLY
        (WEEK_START, USE_CASE_ID, PARTNER_NAME, THEATER_NAME,
         IS_COCO, COCO_SOURCE, HAS_ACCOUNT_COCO, IS_COCO_FINAL)
    WITH uc_base AS (
        -- All Q3-qualifying partner UCs (same dual-date logic as the app)
        SELECT
            uc.USE_CASE_ID,
            uc.PARTNER_NAME,
            uc.THEATER_NAME,
            uc.ACCOUNT_NAME,
            UPPER(TRIM(uc.ACCOUNT_NAME)) AS ACCOUNT_NAME_UPPER,
            uc.IS_COCO,
            uc.COCO_SOURCE
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
        WHERE (
            (uc.USE_CASE_STAGE IN (
                '3 - Technical / Business Validation',
                '4 - Use Case Won / Migration Plan')
             AND uc.DECISION_DATE >= :Q_START
             AND uc.DECISION_DATE <= :Q_END)
            OR
            (uc.USE_CASE_STAGE IN (
                '5 - Implementation In Progress',
                '6 - Implementation Complete',
                '7 - Deployed')
             AND uc.GO_LIVE_DATE >= :Q_START
             AND uc.GO_LIVE_DATE <= :Q_END)
        )
    ),
    caa AS (
        -- Accounts with confirmed account-level CoCo (approximates High confidence band)
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
            (caa.ACCOUNT_NAME_UPPER IS NOT NULL) AS HAS_ACCOUNT_COCO
        FROM uc_base u
        LEFT JOIN caa ON u.ACCOUNT_NAME_UPPER = caa.ACCOUNT_NAME_UPPER
    )
    SELECT
        :week_start                             AS WEEK_START,
        USE_CASE_ID,
        PARTNER_NAME,
        THEATER_NAME,
        IS_COCO,
        COCO_SOURCE,
        HAS_ACCOUNT_COCO,
        -- IS_COCO_FINAL mirrors apply_coco_final() in utils/__init__.py
        CASE WHEN
            -- Keyword/flag tagged AND not the unconfirmed partner-comment case
            (IS_COCO = TRUE
             AND NOT (COCO_SOURCE = 'PARTNER_COMMENTS'
                      AND HAS_ACCOUNT_COCO = FALSE))
            -- OR account-level consumption signal qualifies it
            OR (IS_COCO = FALSE AND HAS_ACCOUNT_COCO = TRUE)
        THEN TRUE ELSE FALSE END                AS IS_COCO_FINAL
    FROM uc_joined;

    row_count := SQLROWCOUNT;
    RETURN 'OK — week ' || :week_start::VARCHAR || ', ' || :row_count::VARCHAR || ' rows inserted';
END;
$$;

-- DEV version of the same SP (points to DEV schema)
CREATE OR REPLACE PROCEDURE TEMP.COCO_PARTNER_ADOPTION_DEV.SP_REFRESH_UC_COCO_WEEKLY(
    Q_START VARCHAR DEFAULT '2026-08-01',
    Q_END   VARCHAR DEFAULT '2026-10-31'
)
RETURNS VARCHAR
LANGUAGE SQL
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
         IS_COCO, COCO_SOURCE, HAS_ACCOUNT_COCO, IS_COCO_FINAL)
    WITH uc_base AS (
        SELECT
            uc.USE_CASE_ID, uc.PARTNER_NAME, uc.THEATER_NAME,
            UPPER(TRIM(uc.ACCOUNT_NAME)) AS ACCOUNT_NAME_UPPER,
            uc.IS_COCO, uc.COCO_SOURCE
        FROM TEMP.COCO_PARTNER_ADOPTION_DEV.DT_OKR_USE_CASES uc
        WHERE (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan')
             AND uc.DECISION_DATE >= :Q_START AND uc.DECISION_DATE <= :Q_END)
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
             AND uc.GO_LIVE_DATE >= :Q_START AND uc.GO_LIVE_DATE <= :Q_END)
        )
    ),
    caa AS (
        SELECT DISTINCT UPPER(TRIM(SALESFORCE_ACCOUNT_NAME)) AS ACCOUNT_NAME_UPPER
        FROM TEMP.COCO_PARTNER_ADOPTION_DEV.INCLUDE_CUSTOMER_ACCOUNTS_AUTOMATED
    ),
    uc_joined AS (
        SELECT u.USE_CASE_ID, u.PARTNER_NAME, u.THEATER_NAME, u.IS_COCO, u.COCO_SOURCE,
               (caa.ACCOUNT_NAME_UPPER IS NOT NULL) AS HAS_ACCOUNT_COCO
        FROM uc_base u
        LEFT JOIN caa ON u.ACCOUNT_NAME_UPPER = caa.ACCOUNT_NAME_UPPER
    )
    SELECT
        :week_start, USE_CASE_ID, PARTNER_NAME, THEATER_NAME, IS_COCO, COCO_SOURCE,
        HAS_ACCOUNT_COCO,
        CASE WHEN
            (IS_COCO = TRUE AND NOT (COCO_SOURCE = 'PARTNER_COMMENTS' AND HAS_ACCOUNT_COCO = FALSE))
            OR (IS_COCO = FALSE AND HAS_ACCOUNT_COCO = TRUE)
        THEN TRUE ELSE FALSE END AS IS_COCO_FINAL
    FROM uc_joined;

    row_count := SQLROWCOUNT;
    RETURN 'OK — week ' || :week_start::VARCHAR || ', ' || :row_count::VARCHAR || ' rows inserted (DEV)';
END;
$$;

-- ---------------------------------------------------------------------------
-- 3. Weekly Task — runs every Monday at 06:00 UTC
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TASK TASK_UC_COCO_WEEKLY
    WAREHOUSE  = COCO_PARTNER_ADOPTION_WH
    SCHEDULE   = 'USING CRON 0 6 * * MON UTC'
    COMMENT    = 'Weekly UC-level IS_COCO_FINAL snapshot for transition detection'
AS
    CALL TEMP.COCO_PARTNER_ADOPTION.SP_REFRESH_UC_COCO_WEEKLY();

ALTER TASK TASK_UC_COCO_WEEKLY RESUME;

-- ---------------------------------------------------------------------------
-- 4. Back-fill: run manually to seed initial data (last 4 weeks)
--    Adjust WEEK_START values as needed before running.
-- ---------------------------------------------------------------------------
-- CALL SP_REFRESH_UC_COCO_WEEKLY();   -- seeds current week
--
-- To back-fill prior weeks, temporarily override CURRENT_DATE() by calling
-- the insert block directly with fixed WEEK_START values, e.g.:
--
-- INSERT INTO UC_COCO_STATUS_WEEKLY ( ... )
-- WITH uc_base AS ( ... same query ... )
-- SELECT '2026-08-24', USE_CASE_ID, ... FROM uc_joined;   -- Aug 24 week
--
-- INSERT INTO UC_COCO_STATUS_WEEKLY ( ... )
-- SELECT '2026-08-17', USE_CASE_ID, ... FROM uc_joined;   -- Aug 17 week
--
-- You need at least 2 weeks for transition detection to work.
