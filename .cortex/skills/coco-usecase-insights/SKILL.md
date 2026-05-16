---
name: coco-usecase-insights
description: "Use for ALL requests related to the CoCo Use Case Intelligence app. ALWAYS invoke this skill for: deploying the app, modifying queries, adding pages, updating OKR dashboards, generating executive emails, refreshing dynamic tables. Triggers: coco usecase insights, use case intelligence, okr coverage, okr adoption, partner scorecard, executive email, coco coverage dashboard, deploy usecase app, partner use cases, coco detection."
---

# CoCo Use Case Intelligence App

## Overview

Streamlit-in-Snowflake app for tracking Cortex Code (CoCo) adoption across partner use cases. 8 pages covering adoption metrics, pipeline analysis, OKR dashboards, and executive email generation.

**App URL:** https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS
**GitHub:** https://github.com/sfc-gh-rmakkena/coco-usecase-insights

---

## Snowflake Environment

| Object | Value |
|--------|-------|
| Database | `TEMP` |
| Schema | `COCO_PARTNER_ADOPTION` |
| Warehouse | `COCO_PARTNER_ADOPTION_WH` |
| Role | `SALES_ENGINEER` |
| Stage | `@TEMP.COCO_PARTNER_ADOPTION.STREAMLIT/COCO_USECASE_INSIGHTS/` |
| App Name | `COCO_USECASE_INSIGHTS` |

---

## Key Data Objects

| Object | Type | Purpose |
|--------|------|---------|
| `MDM.MDM_INTERFACES.DIM_USE_CASE` | Table | Master use case dimension |
| `MDM.MDM_INTERFACES.FACT_USE_CASE_STAGE_MOVEMENT` | Table | Stage movement history |
| `TEMP.COCO_PARTNER_ADOPTION.PARTNER_HIERARCHY` | Table | Child-to-parent partner mapping |
| `TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES` | Dynamic Table | Pre-computed OKR data (refreshes daily, TARGET_LAG = '1 day') |
| `TEMP.COCO_PARTNER_ADOPTION.INCLUDE_CUSTOMER_ACCOUNTS_AUTOMATED` | Table | Consumption-based CoCo accounts |

---

## Project Structure

```
streamlit_app.py              # Entry point, sidebar filters
app_pages/
  overview.py                 # Adoption Metrics KPIs
  pipeline.py                 # Pipeline & Funnel
  deep_dive.py                # Use Case Explorer
  comments_intelligence.py    # Comments & AI Insights
  trends.py                   # Trends & Aging
  okr_summary.py              # OKR: CoCo Coverage (Summary + Detail tabs)
  okr_adoption.py             # OKR: CoCo Adoption (Partner scorecard)
  executive_email.py          # Executive Email generator
utils/
  queries.py                  # All SQL queries (DT_OKR for OKR pages)
  cortex_helpers.py           # Cortex Complete wrapper
  __init__.py
```

---

## CoCo Detection Logic

A use case is CoCo-attached if ANY of these match:
- `SE_COMMENTS ILIKE '%coco%'` or `'%cortex code%'`
- `PARTNER_COMMENTS ILIKE '%#coco%'`
- `PRIORITIZED_FEATURES ILIKE '%AI - Cortex Code%'`

## OKR Date Filtering

- **Stages 3-4** (Validation/Won): filter by `DECISION_DATE`
- **Stages 5-7** (Implementation/Deployed): filter by `GO_LIVE_DATE`

---

## Workflow

### Deploy App

```sql
-- 1. Upload files to stage
PUT 'file:///path/to/file.py' @TEMP.COCO_PARTNER_ADOPTION.STREAMLIT/COCO_USECASE_INSIGHTS/... AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- 2. Recreate Streamlit app
CREATE OR REPLACE STREAMLIT TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS
    FROM '@TEMP.COCO_PARTNER_ADOPTION.STREAMLIT/COCO_USECASE_INSIGHTS/'
    MAIN_FILE = 'streamlit_app.py'
    QUERY_WAREHOUSE = 'COCO_PARTNER_ADOPTION_WH';
```

### Refresh Dynamic Table

```sql
ALTER DYNAMIC TABLE TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES REFRESH;
```

### Check Dynamic Table Status

```sql
SELECT name, refresh_mode, target_lag, last_completed_refresh_time 
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
WHERE name = 'DT_OKR_USE_CASES';
```

### Git Push

```bash
cd /Users/rmakkena/.snowflake/cortex/playground/workspace/usecase-insights-app
git add -A && git commit -m "message" && git push
```

---

## Key Design Decisions

1. **Dynamic Table over Views**: OKR queries use `DT_OKR_USE_CASES` (pre-computed daily) instead of expensive CTE joins on `DIM_USE_CASE` + `PARTNER_HIERARCHY` + `FACT_USE_CASE_STAGE_MOVEMENT`
2. **Partner Hierarchy**: Child partners map to parent groups via `PARTNER_HIERARCHY` table; exclusions: Sigma Computing, Bloomberg Finance
3. **Dual-date OKR filtering**: Different date columns for different stage ranges (DECISION_DATE vs GO_LIVE_DATE)
4. **AI Email**: Uses SQL-based `SNOWFLAKE.CORTEX.COMPLETE('claude-sonnet-4-5', ...)` via `conn.query()` (not Python SDK, which doesn't work in SiS)
5. **Detail tab**: Uses `st.multiselect` (default top 10) to avoid DOM bloat from rendering all 1400+ partners
