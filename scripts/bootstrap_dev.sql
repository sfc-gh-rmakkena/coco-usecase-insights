-- =============================================================
-- bootstrap_dev.sql
-- One-time script to clone PROD into DEV.
-- Safe to re-run: uses CREATE ... IF NOT EXISTS where possible.
-- Does NOT touch any PROD objects.
-- =============================================================

USE ROLE SALES_ENGINEER;
USE WAREHOUSE COCO_PARTNER_ADOPTION_WH;

-- 1. Clone entire PROD schema into DEV (zero-copy, instant)
CREATE SCHEMA IF NOT EXISTS TEMP.COCO_PARTNER_ADOPTION_DEV
    CLONE TEMP.COCO_PARTNER_ADOPTION;

-- 2. Create DEV stages (not carried over by schema clone for internal stages)
CREATE STAGE IF NOT EXISTS TEMP.COCO_PARTNER_ADOPTION_DEV.STREAMLIT;
CREATE STAGE IF NOT EXISTS TEMP.COCO_PARTNER_ADOPTION_DEV.SV_STAGE;

-- 3. Suspend DEV task immediately — must never auto-run in DEV
ALTER TASK IF EXISTS TEMP.COCO_PARTNER_ADOPTION_DEV.TASK_REFRESH_TABLES SUSPEND;

-- 4. Confirm DEV task is suspended (verify output shows state = suspended)
SHOW TASKS IN SCHEMA TEMP.COCO_PARTNER_ADOPTION_DEV;

-- 5. Confirm PROD task state is unchanged
SHOW TASKS IN SCHEMA TEMP.COCO_PARTNER_ADOPTION;
