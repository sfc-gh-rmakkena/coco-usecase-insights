-- Semantic view for the Partner Consultants tab.
--
-- Design notes (all verified against the dashboard before writing):
--
-- 1. Activity comes from V_PARTNER_CONSULTANT_ACTIVITY, not the raw
--    SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT. A first version declared the raw fact as a
--    table with a RELATIONSHIP to the consultant roster; that relationship resolved as an
--    OUTER join, so asking for tokens without a consultant dimension returned all 180,625
--    Cortex Code users and 29.2B tokens instead of the ~400 partner consultants and ~101M
--    tokens. Pre-joining in the view makes the restriction structural.
--
-- 2. The roster (PARTNER_CONSULTANT_RESOLVED) stays as its own table for bench-size
--    questions ("how many consultants does X have"), which are answerable without any
--    activity. It is deliberately NOT related to activity: a join on PARTNER_NAME is
--    one-to-many and would fan out token sums.
--
-- 3. Skills (PARTNER_CONSULTANT_SKILLS) is partner-week grain, has 69 duplicate rows on
--    (PARTNER_NAME, CONTEXT, WEEK_START, SKILL) so it cannot carry a primary key, and has
--    no user grain. It stays standalone for the same fan-out reason.
--
-- Fidelity check vs the dashboard (Customer context, 2026-08-01..2026-10-31):
--    Spaulding Ridge 63 consultants / 39,857,536 tokens  <- matches UI exactly
--    Deloitte Consulting 123 consultants / 24,665,964 tokens
--    BlueCloud Services Inc 17 consultants / 8,181,923 tokens
--
CREATE OR REPLACE SEMANTIC VIEW TEMP.COCO_PARTNER_ADOPTION.PARTNER_CONSULTANTS_SV

  TABLES (
    activity AS TEMP.COCO_PARTNER_ADOPTION.V_PARTNER_CONSULTANT_ACTIVITY
      WITH SYNONYMS = ('consultant activity', 'cortex code usage', 'token usage', 'daily activity')
      COMMENT = 'Daily Cortex Code usage for identity-resolved partner consultants only, one row per consultant per deployment per day. Already restricted to partner consultants and to days with at least one request.',

    roster AS TEMP.COCO_PARTNER_ADOPTION.PARTNER_CONSULTANT_RESOLVED
      PRIMARY KEY (USER_ID, DEPLOYMENT)
      WITH SYNONYMS = ('consultant roster', 'resolved consultants', 'bench')
      COMMENT = 'One row per identity-resolved partner consultant login, regardless of whether they have any usage. Use for bench size. Tier1 = active in the partner''s own Snowflake account; Tier2 = the same person matched into another account by exact email, or exact name plus same email domain.',

    skills AS TEMP.COCO_PARTNER_ADOPTION.PARTNER_CONSULTANT_SKILLS
      WITH SYNONYMS = ('skill usage', 'skill invocations', 'consultant skills')
      COMMENT = 'Weekly skill invocation counts per partner and context. Partner-week grain, NOT consultant grain, so it cannot be combined with per-consultant token metrics in one aggregation.'
  )

  FACTS (
    activity.daily_tokens AS activity.TOTAL_TOKENS
      COMMENT = 'Cortex Code tokens consumed that day by that consultant.',
    activity.daily_prompts AS activity.TOTAL_DAILY_USER_PROMPTS
      COMMENT = 'User prompts submitted that day.',
    activity.daily_requests AS activity.TOTAL_DAILY_REQUESTS
      COMMENT = 'Requests issued that day.',
    skills.invocation_count AS skills.INVOCATIONS
      COMMENT = 'Times the skill was invoked in that partner-week.'
  )

  DIMENSIONS (
    activity.partner_name AS activity.PARTNER_NAME
      WITH SYNONYMS = ('partner', 'firm', 'SI', 'GSI', 'RSI', 'system integrator')
      COMMENT = 'Partner the consultant belongs to.',
    activity.partner_region AS activity.PARTNER_REGION
      WITH SYNONYMS = ('region', 'geo')
      COMMENT = 'Partner region: NoAM, EMEA or APJ.',
    activity.match_tier AS activity.MATCH_TIER
      WITH SYNONYMS = ('tier', 'resolution tier')
      COMMENT = 'Tier1 or Tier2 identity resolution.',
    activity.usage_date AS activity.DS
      WITH SYNONYMS = ('date', 'day', 'activity date')
      COMMENT = 'Date of the usage.',
    activity.account_type AS activity.SNOWFLAKE_ACCOUNT_TYPE
      WITH SYNONYMS = ('account type', 'context', 'customer or partner account')
      COMMENT = 'Where the usage happened. Customer means the consultant was working inside a customer account (customer engagement). Partner means the partner''s own account (internal adoption). Always set this when the question distinguishes customer work from internal usage.',
    activity.snowflake_account_name AS activity.SNOWFLAKE_ACCOUNT_NAME
      WITH SYNONYMS = ('snowflake account')
      COMMENT = 'Snowflake account where the usage occurred.',
    activity.customer_account_name AS activity.SALESFORCE_ACCOUNT_NAME
      WITH SYNONYMS = ('customer', 'customer account', 'salesforce account', 'end customer')
      COMMENT = 'Salesforce account name of the account the usage occurred in.',
    activity.consultant_name AS activity.USER_NAME
      WITH SYNONYMS = ('consultant', 'user', 'login name')
      COMMENT = 'Login name of the consultant.',

    roster.roster_partner_name AS roster.PARTNER_NAME
      WITH SYNONYMS = ('roster partner')
      COMMENT = 'Partner the rostered consultant belongs to.',
    roster.roster_partner_region AS roster.PARTNER_REGION
      COMMENT = 'Region of the rostered consultant.',
    roster.roster_match_tier AS roster.MATCH_TIER
      COMMENT = 'Tier1 or Tier2 for the rostered consultant.',

    skills.skill_partner_name AS skills.PARTNER_NAME
      WITH SYNONYMS = ('skill partner')
      COMMENT = 'Partner the skill usage belongs to.',
    skills.skill_partner_region AS skills.PARTNER_REGION
      COMMENT = 'Region of the partner for this skill usage.',
    skills.skill_name AS skills.SKILL
      WITH SYNONYMS = ('skill', 'capability', 'tool')
      COMMENT = 'Name of the Cortex Code skill invoked.',
    skills.skill_context AS skills.CONTEXT
      COMMENT = 'Customer or Partner, matching the account type where the skill was used.',
    skills.week_start AS skills.WEEK_START
      WITH SYNONYMS = ('week')
      COMMENT = 'Monday of the week the invocations were counted in.'
  )

  METRICS (
    activity.token_total AS SUM(activity.daily_tokens)
      WITH SYNONYMS = ('tokens', 'token usage', 'token consumption', 'total tokens')
      COMMENT = 'Total Cortex Code tokens for partner consultants.',
    activity.prompt_total AS SUM(activity.daily_prompts)
      WITH SYNONYMS = ('prompts', 'prompt count', 'total prompts')
      COMMENT = 'Total user prompts.',
    activity.request_total AS SUM(activity.daily_requests)
      WITH SYNONYMS = ('requests', 'total requests')
      COMMENT = 'Total requests.',
    activity.active_consultants AS COUNT(DISTINCT activity.USER_ID || '|' || activity.DEPLOYMENT)
      WITH SYNONYMS = ('active consultants', 'consultants with usage', 'number of active consultants')
      COMMENT = 'Distinct consultants with recorded usage. Counted on user plus deployment because the same person can appear in more than one deployment. Use this for "how many consultants are active"; use roster.consultant_total for bench size.',
    activity.active_days AS COUNT(DISTINCT activity.DS)
      COMMENT = 'Distinct days with recorded usage.',
    activity.customer_accounts_touched AS COUNT(DISTINCT activity.SALESFORCE_ACCOUNT_NAME)
      WITH SYNONYMS = ('accounts touched', 'customer reach', 'number of customer accounts')
      COMMENT = 'Distinct customer accounts the consultants were active in.',
    activity.partners_active AS COUNT(DISTINCT activity.PARTNER_NAME)
      WITH SYNONYMS = ('number of partners', 'partner count')
      COMMENT = 'Distinct partners with consultant activity in scope.',

    roster.consultant_total AS COUNT(DISTINCT roster.USER_ID || '|' || roster.DEPLOYMENT)
      WITH SYNONYMS = ('bench size', 'total consultants', 'number of consultants on roster')
      COMMENT = 'Resolved consultant logins on the roster, whether or not they have usage.',
    roster.tier2_consultant_total AS COUNT(CASE WHEN roster.MATCH_TIER = 'Tier2' THEN 1 END)
      COMMENT = 'Roster consultants resolved by identity linking rather than partner-account presence.',

    skills.invocation_total AS SUM(skills.invocation_count)
      WITH SYNONYMS = ('invocations', 'skill usage count', 'total invocations')
      COMMENT = 'Total skill invocations.',
    skills.distinct_skills AS COUNT(DISTINCT skills.SKILL)
      WITH SYNONYMS = ('skill breadth', 'number of skills')
      COMMENT = 'Distinct skills used.'
  )

  COMMENT = 'Partner Consultants: identity-resolved consultants at partners and their Cortex Code (CoCo) usage. Answers who is active, at which partner, inside customer accounts versus the partner''s own account, and which skills they use. Set activity.account_type = ''Customer'' for consultant work inside customer accounts (customer engagements) and ''Partner'' for the partner''s internal adoption. The activity table is already restricted to resolved partner consultants. The roster and skills tables are intentionally unrelated to activity because joining them on partner name is one-to-many and would inflate token sums; answer bench-size questions from roster alone and skill questions from skills alone.'
;
