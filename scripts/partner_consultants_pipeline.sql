-- Partner Consultant pipeline (DEV): full leaderboard-style resolution scaled to all partners.
--   Tier-1a (account-anchor): user active in a partner's own account.
--   Tier-1b (email-domain): user whose email domain = a partner's corporate domain (derived from
--            anchored consultants' emails; public domains excluded; dominant-partner per domain).
--   Tier-2 (name-match): leaderboard algorithm - engaged-account scoped, last+first-name blocking,
--            AI_SIMILARITY scoring, ai_sim>=0.90 auto / 0.80-0.90 pending.
-- Then weekly activity/skills per partner x context. Refreshed daily.
CREATE OR REPLACE PROCEDURE TEMP.COCO_PARTNER_ADOPTION_DEV.SP_REFRESH_PARTNER_CONSULTANTS()
RETURNS STRING
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
BEGIN
  -- 1. Tier-1a account anchor (primary partner by partner-own-account activity)
  CREATE OR REPLACE TABLE TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_ANCHOR AS
  WITH partner_accts AS (
    SELECT ACCOUNT_NAME, COALESCE(NULLIF(TRIM(ULTIMATE_PARENT_NAME),''), ACCOUNT_NAME) AS PARTNER_NAME, GEO_NAME
    FROM SALES.PARTNER_BASIC.ACCOUNT
    WHERE ACCOUNT_TYPE='Partner' AND COALESCE(GEO_NAME,'') <> 'AcctsToDelete'
  ),
  usage AS (
    SELECT f.USER_ID, f.DEPLOYMENT, MAX(f.USER_NAME) AS USER_NAME, pa.PARTNER_NAME, MAX(pa.GEO_NAME) AS GEO_NAME,
           SUM(f.TOTAL_DAILY_REQUESTS) AS req, MIN(f.DS) AS first_day, MAX(f.DS) AS last_day
    FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
    JOIN partner_accts pa ON UPPER(TRIM(f.SALESFORCE_ACCOUNT_NAME))=UPPER(TRIM(pa.ACCOUNT_NAME))
    WHERE f.SNOWFLAKE_ACCOUNT_TYPE='Partner' AND f.TOTAL_DAILY_REQUESTS>0
    GROUP BY f.USER_ID, f.DEPLOYMENT, pa.PARTNER_NAME
  ),
  ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY USER_ID, DEPLOYMENT ORDER BY req DESC NULLS LAST, PARTNER_NAME) AS rn FROM usage)
  SELECT USER_ID, DEPLOYMENT, USER_NAME, PARTNER_NAME,
    CASE WHEN GEO_NAME ILIKE 'AMS%' OR GEO_NAME IN ('USMajors','USPubSec') THEN 'NoAM'
         WHEN GEO_NAME ILIKE 'EMEA%' THEN 'EMEA' WHEN GEO_NAME ILIKE 'APJ%' THEN 'APJ' ELSE 'NoAM' END AS PARTNER_REGION,
    req AS partner_own_requests, first_day, last_day
  FROM ranked WHERE rn=1;

  -- 2. Derive partner corporate email domains from anchored consultants (dominant partner per domain)
  CREATE OR REPLACE TABLE TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_DOMAIN_MAP AS
  WITH pd AS (
    SELECT LOWER(SPLIT_PART(u.EMAIL,'@',2)) AS domain, a.PARTNER_NAME, COUNT(*) AS users
    FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_ANCHOR a
    JOIN SNOWHOUSE_IMPORT.PROD.USER_ETL_V u ON u.ID=a.USER_ID AND u.DEPLOYMENT=a.DEPLOYMENT AND u.DELETED_ON IS NULL
    WHERE u.EMAIL IS NOT NULL AND POSITION('@' IN u.EMAIL)>0
      AND LOWER(SPLIT_PART(u.EMAIL,'@',2)) NOT IN
        ('gmail.com','googlemail.com','yahoo.com','hotmail.com','outlook.com','icloud.com','aol.com','protonmail.com',
         'proton.me','live.com','msn.com','me.com','ymail.com','gmx.com','mail.com','qq.com','163.com','126.com')
    GROUP BY 1,2
  ),
  ranked AS (
    SELECT domain, PARTNER_NAME, users,
      ROW_NUMBER() OVER (PARTITION BY domain ORDER BY users DESC) AS rn,
      SUM(users) OVER (PARTITION BY domain) AS domain_total
    FROM pd
  )
  SELECT domain, PARTNER_NAME FROM ranked
  WHERE rn=1 AND users>=2 AND users >= 0.6*domain_total;

  -- 3. Combined Tier-1 = account-anchor (Tier1) + domain-match (Tier1_domain)
  CREATE OR REPLACE TABLE TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_TIER1 AS
  WITH pr AS (SELECT PARTNER_NAME, MAX(PARTNER_REGION) AS PARTNER_REGION FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_ANCHOR GROUP BY 1)
  SELECT USER_ID, DEPLOYMENT, PARTNER_NAME, PARTNER_REGION, 'Tier1' AS match_tier
  FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_ANCHOR
  UNION ALL
  SELECT du.USER_ID, du.DEPLOYMENT, dm.PARTNER_NAME, pr.PARTNER_REGION, 'Tier1_domain' AS match_tier
  FROM (
    SELECT DISTINCT f.USER_ID, f.DEPLOYMENT, LOWER(SPLIT_PART(u.EMAIL,'@',2)) AS domain
    FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f
    JOIN SNOWHOUSE_IMPORT.PROD.USER_ETL_V u ON f.USER_ID=u.ID AND f.DEPLOYMENT=u.DEPLOYMENT AND u.DELETED_ON IS NULL
    WHERE f.SNOWFLAKE_ACCOUNT_TYPE IN ('Partner','Customer') AND f.TOTAL_DAILY_REQUESTS>0 AND u.EMAIL IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_ANCHOR a WHERE a.USER_ID=f.USER_ID AND a.DEPLOYMENT=f.DEPLOYMENT)
  ) du
  JOIN TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_DOMAIN_MAP dm ON du.domain=dm.domain
  JOIN pr ON pr.PARTNER_NAME=dm.PARTNER_NAME;

  -- 4. Tier-2 name matches (leaderboard algorithm) on top of combined Tier-1
  CREATE OR REPLACE TABLE TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_TIER2_MATCHES AS
  WITH pr AS (SELECT PARTNER_NAME, MAX(PARTNER_REGION) AS PARTNER_REGION FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_TIER1 GROUP BY 1),
  roster AS (
    SELECT t.PARTNER_NAME, t.USER_ID||'|'||t.DEPLOYMENT AS matched_person,
      CASE WHEN u.DISPLAY_NAME LIKE '% %' THEN u.DISPLAY_NAME
           ELSE REGEXP_REPLACE(SPLIT_PART(COALESCE(u.EMAIL,u.LOGIN_NAME),'@',1),'[._-]',' ') END AS dn
    FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_TIER1 t
    JOIN SNOWHOUSE_IMPORT.PROD.USER_ETL_V u ON u.ID=t.USER_ID AND u.DEPLOYMENT=t.DEPLOYMENT AND u.DELETED_ON IS NULL
  ),
  roster_b AS (
    SELECT PARTNER_NAME, matched_person, dn,
      TRIM(REGEXP_REPLACE(REGEXP_REPLACE(TRANSLATE(LOWER(dn),'àáâãäåçèéêëìíîïñòóôõöùúûüý','aaaaaaceeeeiiiinooooouuuuy'),'[^a-z ]',''),'^(e|x|c|ext|ic) ','')) AS rn2
    FROM roster
  ),
  roster_n AS (SELECT PARTNER_NAME, matched_person, dn, rn2, SPLIT_PART(rn2,' ',1) AS rfirst, REGEXP_SUBSTR(rn2,'[a-z]+$') AS rlast FROM roster_b),
  engaged AS (
    SELECT DISTINCT t.PARTNER_NAME, f.SALESFORCE_ACCOUNT_NAME
    FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_TIER1 t
    JOIN SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f ON f.USER_ID=t.USER_ID AND f.DEPLOYMENT=t.DEPLOYMENT
    WHERE f.SNOWFLAKE_ACCOUNT_TYPE='Customer' AND f.TOTAL_DAILY_REQUESTS>0 AND f.SALESFORCE_ACCOUNT_NAME IS NOT NULL
  ),
  cand AS (
    SELECT DISTINCT f.USER_ID, f.DEPLOYMENT, f.SALESFORCE_ACCOUNT_NAME, u.EMAIL, u.DISPLAY_NAME, u.LOGIN_NAME,
      LOWER(SPLIT_PART(COALESCE(u.EMAIL,u.LOGIN_NAME),'@',2)) AS cust_domain,
      TRIM(REGEXP_REPLACE(REGEXP_REPLACE(TRANSLATE(LOWER(CASE WHEN u.DISPLAY_NAME LIKE '% %' THEN u.DISPLAY_NAME
           ELSE REGEXP_REPLACE(SPLIT_PART(COALESCE(u.EMAIL,u.LOGIN_NAME),'@',1),'[._-]',' ') END),'àáâãäåçèéêëìíîïñòóôõöùúûüý','aaaaaaceeeeiiiinooooouuuuy'),'[^a-z ]',''),'^(e|x|c|ext|ic) ','')) AS cn2
    FROM SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_FACT f
    JOIN SNOWHOUSE_IMPORT.PROD.USER_ETL_V u ON f.USER_ID=u.ID AND f.DEPLOYMENT=u.DEPLOYMENT AND u.DELETED_ON IS NULL
    WHERE f.IS_HUMAN_PROMPT=TRUE AND f.SNOWFLAKE_ACCOUNT_TYPE NOT IN ('Internal','Trial and other Non-Paying Customers')
      AND f.SALESFORCE_ACCOUNT_NAME IN (SELECT SALESFORCE_ACCOUNT_NAME FROM engaged)
      AND NOT EXISTS (SELECT 1 FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_TIER1 tl WHERE tl.USER_ID=f.USER_ID AND tl.DEPLOYMENT=f.DEPLOYMENT)
      AND LOWER(SPLIT_PART(COALESCE(u.EMAIL,u.LOGIN_NAME),'@',2)) NOT IN
        ('gmail.com','googlemail.com','yahoo.com','hotmail.com','outlook.com','icloud.com','aol.com','protonmail.com',
         'proton.me','live.com','msn.com','me.com','ymail.com','gmx.com','mail.com','qq.com','163.com','126.com')
  ),
  cand_b AS (SELECT c.*, SPLIT_PART(cn2,' ',1) AS cfirst, REGEXP_SUBSTR(cn2,'[a-z]+$') AS clast FROM cand c),
  scored AS (
    SELECT c.USER_ID, c.DEPLOYMENT, c.SALESFORCE_ACCOUNT_NAME, c.EMAIL AS cust_email, c.DISPLAY_NAME AS cust_display_name,
      c.cust_domain, e.PARTNER_NAME, r.matched_person, r.dn AS matched_name, AI_SIMILARITY(r.rn2, c.cn2) AS ai_sim
    FROM cand_b c
    JOIN engaged e ON c.SALESFORCE_ACCOUNT_NAME=e.SALESFORCE_ACCOUNT_NAME
    JOIN roster_n r ON r.PARTNER_NAME=e.PARTNER_NAME AND r.rlast=c.clast AND LENGTH(c.clast)>=4
      AND ( r.rfirst=c.cfirst
            OR (JAROWINKLER_SIMILARITY(r.rfirst,c.cfirst) >= 95 AND EDITDISTANCE(r.rfirst,c.cfirst) <= 1)
            OR ((LENGTH(r.rfirst)<=1 OR LENGTH(c.cfirst)<=1) AND LEFT(r.rfirst,1)=LEFT(c.cfirst,1)) )
    QUALIFY ROW_NUMBER() OVER (PARTITION BY c.USER_ID,c.DEPLOYMENT ORDER BY AI_SIMILARITY(r.rn2,c.cn2) DESC)=1
  )
  SELECT s.PARTNER_NAME, pr.PARTNER_REGION, s.USER_ID, s.DEPLOYMENT, s.SALESFORCE_ACCOUNT_NAME,
    s.cust_email, s.cust_display_name, s.cust_domain, s.matched_person, s.matched_name, ROUND(s.ai_sim,4) AS ai_sim,
    CASE WHEN s.ai_sim>=0.90 THEN 'Tier2_A' ELSE 'Tier2_C' END AS match_method,
    CASE WHEN s.ai_sim>=0.90 THEN 'auto_accepted' ELSE 'pending' END AS review_status
  FROM scored s LEFT JOIN pr ON pr.PARTNER_NAME=s.PARTNER_NAME
  WHERE s.ai_sim >= 0.80;

  -- 5. Resolved = combined Tier-1 + auto-accepted Tier-2
  CREATE OR REPLACE TABLE TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_RESOLVED AS
  SELECT USER_ID, DEPLOYMENT, PARTNER_NAME, PARTNER_REGION, match_tier
  FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_TIER1
  UNION ALL
  SELECT USER_ID, DEPLOYMENT, PARTNER_NAME, PARTNER_REGION, 'Tier2' AS match_tier
  FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_TIER2_MATCHES WHERE review_status='auto_accepted';

  -- 6. Weekly activity per partner x context
  CREATE OR REPLACE TABLE TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_ACTIVITY AS
  SELECT r.PARTNER_NAME, r.PARTNER_REGION,
    CASE WHEN f.SNOWFLAKE_ACCOUNT_TYPE='Partner' THEN 'Partner' ELSE 'Customer' END AS context,
    DATE_TRUNC('WEEK', f.DS) AS week_start,
    COUNT(DISTINCT f.USER_ID||'|'||f.DEPLOYMENT) AS consultants,
    SUM(f.TOTAL_TOKENS) AS tokens, SUM(f.TOTAL_DAILY_USER_PROMPTS) AS prompts,
    SUM(f.TOTAL_DAILY_REQUESTS) AS requests, SUM(f.TOTAL_TOKEN_CREDITS) AS credits
  FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_RESOLVED r
  JOIN SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT f ON f.USER_ID=r.USER_ID AND f.DEPLOYMENT=r.DEPLOYMENT
  WHERE f.SNOWFLAKE_ACCOUNT_TYPE IN ('Partner','Customer') AND f.TOTAL_DAILY_REQUESTS>0
  GROUP BY 1,2,3,4;

  -- 7. Weekly skills per partner x context
  CREATE OR REPLACE TABLE TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_SKILLS AS
  SELECT r.PARTNER_NAME, r.PARTNER_REGION,
    CASE WHEN f.SNOWFLAKE_ACCOUNT_TYPE='Partner' THEN 'Partner' ELSE 'Customer' END AS context,
    DATE_TRUNC('WEEK', f.ds) AS week_start, TRIM(s.value::string) AS skill, COUNT(*) AS invocations
  FROM TEMP.COCO_PARTNER_ADOPTION_DEV.PARTNER_CONSULTANT_RESOLVED r
  JOIN SNOWSCIENCE.LLM.CORTEX_CODE_REQUEST_FACT f ON f.USER_ID=r.USER_ID AND f.DEPLOYMENT=r.DEPLOYMENT,
  LATERAL FLATTEN(input => TRY_PARSE_JSON(f.SKILL_CHOICE)) s
  WHERE f.SNOWFLAKE_ACCOUNT_TYPE IN ('Partner','Customer')
    AND f.SKILL_CHOICE IS NOT NULL AND f.SKILL_CHOICE <> '' AND TRIM(s.value::string) NOT IN ('', 'null')
  GROUP BY 1,2,3,4,5;

  RETURN 'Partner consultants refreshed';
END;
$$;
