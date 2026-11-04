-- =============================================================
-- validate_runtime.sql
-- Read-only checks run after each deploy of the container-runtime apps
-- (cutover test matrix, section B). Run as SALES_ENGINEER.
-- =============================================================

USE ROLE SALES_ENGINEER;

-- B1. PROD and the rehearsal app run on container runtime.
--     Expect runtime_name = SYSTEM$ST_CONTAINER_RUNTIME_PY3_11,
--     compute_pool = STREAMLIT_DEDICATED_POOL_L,
--     external_access_integrations contains PYPI_ACCESS_INTEGRATION.
DESCRIBE STREAMLIT TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS;
DESCRIBE STREAMLIT TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS_CR;

-- B2. DEV is unchanged (same three values as B1).
DESCRIBE STREAMLIT TEMP.COCO_PARTNER_ADOPTION_DEV.COCO_USECASE_INSIGHTS_DEV;

-- B3. Caller grants cover every table read through the caller's-rights
--     connection. The owner role must inherit SNOWHOUSE_CALLER_RL ...
SHOW GRANTS OF ROLE SNOWHOUSE_CALLER_RL;            -- expect a row granted to SALES_ENGINEER
--     ... which must hold account-wide caller SELECT on TABLE and VIEW
--     plus caller USAGE on DATABASE and SCHEMA.
SHOW CALLER GRANTS ON ACCOUNT;                      -- filter grantee_name = SNOWHOUSE_CALLER_RL

-- B4. The compute pool is running and has headroom.
--     Expect state ACTIVE or IDLE and active_nodes < max_nodes.
DESCRIBE COMPUTE POOL STREAMLIT_DEDICATED_POOL_L;

-- B5. Ask AI agent exists (both apps call the PROD agent).
SHOW AGENTS LIKE 'COCO_AGENT' IN SCHEMA TEMP.COCO_PARTNER_ADOPTION;
