-- Consultant activity, pre-joined to the resolved roster.
--
-- Why this view exists: in PARTNER_CONSULTANTS_SV the relationship from the raw
-- CORTEX_CODE_USER_DAY_FACT to the consultant roster resolved as an OUTER join, so
-- aggregating tokens without a consultant dimension returned all 180k+ Cortex Code
-- users (29B tokens) instead of the ~400 partner consultants. Pre-joining here makes
-- the restriction structural rather than something Cortex Analyst has to remember.
--
-- Matches utils/queries.py get_pc_activity exactly: INNER JOIN on (USER_ID, DEPLOYMENT)
-- and TOTAL_DAILY_REQUESTS > 0.
CREATE OR REPLACE VIEW TEMP.COCO_PARTNER_ADOPTION.V_PARTNER_CONSULTANT_ACTIVITY
  COMMENT = 'Daily Cortex Code usage for identity-resolved partner consultants only. Inner join of PARTNER_CONSULTANT_RESOLVED to SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT on (USER_ID, DEPLOYMENT), restricted to days with at least one request.'
AS
SELECT
    r.PARTNER_NAME,
    r.PARTNER_REGION,
    r.MATCH_TIER,
    f.USER_ID,
    f.DEPLOYMENT,
    f.USER_NAME,
    f.DS,
    f.SNOWFLAKE_ACCOUNT_TYPE,
    f.SNOWFLAKE_ACCOUNT_NAME,
    f.SALESFORCE_ACCOUNT_NAME,
    f.SALESFORCE_ACCOUNT_ID,
    f.TOTAL_TOKENS,
    f.TOTAL_DAILY_USER_PROMPTS,
    f.TOTAL_DAILY_REQUESTS
FROM TEMP.COCO_PARTNER_ADOPTION.PARTNER_CONSULTANT_RESOLVED r
JOIN SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
  ON f.USER_ID = r.USER_ID
 AND f.DEPLOYMENT = r.DEPLOYMENT
WHERE f.TOTAL_DAILY_REQUESTS > 0;
