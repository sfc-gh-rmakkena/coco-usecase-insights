# CoCo Use Case Intelligence

A Streamlit-in-Snowflake (SiS) application for tracking Cortex Code (CoCo) adoption across partner use cases. Built by **#psegoingcoco**.

## Live Apps

| Environment | Link |
|---|---|
| **PROD** | [Open PROD](https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS) |
| **DEV** | [Open DEV](https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/streamlit-apps/TEMP.COCO_PARTNER_ADOPTION_DEV.COCO_USECASE_INSIGHTS_DEV) |

## Environments

| | PROD | DEV |
|---|---|---|
| Schema | `TEMP.COCO_PARTNER_ADOPTION` | `TEMP.COCO_PARTNER_ADOPTION_DEV` |
| App | `COCO_USECASE_INSIGHTS` | `COCO_USECASE_INSIGHTS_DEV` |
| Task | Running (daily) | Suspended (manual only) |
| Data | Live | Cloned from PROD at bootstrap time |

DEV is fully isolated — changes to DEV data, tasks, or the app cannot affect PROD.

## Pages

| Page | Description |
|------|-------------|
| **Adoption Metrics** | High-level KPIs: total use cases, CoCo-attached count, EACV, regional breakdown |
| **Pipeline & Funnel** | Stage funnel visualization, partner pipeline heatmap, stage movement analysis |
| **Use Case Explorer** | Searchable/filterable table of all use cases with drill-down details |
| **Comments & AI Insights** | AI-powered analysis of SE/partner comments using Cortex Complete |
| **Trends & Aging** | Time-series trends, stage aging analysis, days-in-stage distributions |
| **OKR: CoCo Coverage** | Summary + Detail tabs: gauge chart, pie chart, stacked bar by stage, per-partner expandable cards |
| **OKR: CoCo Adoption** | Partner scorecard with date-range filters, dual-date logic (DECISION_DATE for stages 3-4, GO_LIVE_DATE for 5-7) |
| **Executive Email** | AI-generated executive summary email with copy-to-clipboard and Gmail integration |

## Architecture

```
streamlit_app.py          # Entry point: navigation, sidebar filters (Region, Partner)
app_pages/                # One file per page
utils/
  queries.py              # All SQL queries (cached with st.cache_data)
  config.py               # Environment detection (DEV vs PROD schema routing)
  cortex_helpers.py       # Cortex Complete wrapper for AI generation
```

### Data Sources

| Object | Type | Description |
|--------|------|-------------|
| `MDM.MDM_INTERFACES.DIM_USE_CASE` | Table | Master use case dimension table |
| `MDM.MDM_INTERFACES.FACT_USE_CASE_STAGE_MOVEMENT` | Table | Stage movement history for aging calculations |
| `TEMP.COCO_PARTNER_ADOPTION.PARTNER_HIERARCHY` | Table | Maps child partner names to parent partner groups |
| `TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES` | Dynamic Table | Pre-computed OKR data with partner hierarchy, CoCo detection, and stage days. Refreshes daily (`TARGET_LAG = '1 day'`) |
| `TEMP.COCO_PARTNER_ADOPTION.INCLUDE_CUSTOMER_ACCOUNTS_AUTOMATED` | Table | Consumption-based CoCo account detection |

### CoCo Detection Logic

A use case is flagged as CoCo-attached if any of these conditions match:
- `SE_COMMENTS ILIKE '%coco%'` or `'%cortex code%'`
- `PARTNER_COMMENTS ILIKE '%#coco%'`
- `PRIORITIZED_FEATURES ILIKE '%AI - Cortex Code%'`

### OKR Date Filtering

OKR pages use dual-date filtering based on use case stage:
- **Stages 3-4** (Validation/Won): filtered by `DECISION_DATE`
- **Stages 5-7** (Implementation/Deployed): filtered by `GO_LIVE_DATE`

## Snowflake Objects

```
Database:   TEMP
Schema:     COCO_PARTNER_ADOPTION
Warehouse:  COCO_PARTNER_ADOPTION_WH
Role:       SALES_ENGINEER
Stage:      @TEMP.COCO_PARTNER_ADOPTION.STREAMLIT/COCO_USECASE_INSIGHTS/
```

## Deployment

Deploys go through the Snowflake CLI (`snow`), which bundles the artifacts listed
under each entity in `snowflake.yml`, uploads them to the stage, and recreates the
app. Both the PROD and DEV apps are defined as entities in `snowflake.yml`, so the
entity ID is required — without it the CLI errors out because two Streamlits are
defined.

### Deploy to PROD

```bash
snow streamlit deploy coco_usecase_insights \
  --project . \
  --replace \
  --connection snowhouse \
  --role SALES_ENGINEER \
  --warehouse COCO_PARTNER_ADOPTION_WH \
  --database TEMP \
  --schema COCO_PARTNER_ADOPTION
```

### Deploy to DEV

```bash
snow streamlit deploy coco_usecase_insights_dev \
  --project . \
  --replace \
  --connection snowhouse \
  --role SALES_ENGINEER \
  --warehouse COCO_PARTNER_ADOPTION_WH \
  --database TEMP \
  --schema COCO_PARTNER_ADOPTION_DEV
```

### Notes and gotchas

- **Clear `__pycache__` first.** The bundle includes everything under `utils/` and
  `app_pages/`, so locally generated `.pyc` files get uploaded to the stage. They are
  gitignored but not deploy-ignored. Run `find . -name __pycache__ -type d -exec rm -rf {} +`
  before deploying, or pass `--prune` to drop stage files that no longer exist locally.
- **`--replace` only adds and overwrites.** It never deletes stage files. Use `--prune`
  to remove orphans.
- **`scripts/deploy.sh` is currently broken.** It passes `--file`, which Snowflake CLI
  3.x removed, and omits the entity ID. Use the commands above until it is updated.
- **`snowflake.dev.yml` is legacy.** It uses the old top-level `streamlit:` format and was
  only reachable via the removed `--file` flag. The DEV target now lives in `snowflake.yml`
  as the `coco_usecase_insights_dev` entity.
- The app auto-detects its environment from `CURRENT_SCHEMA()` at runtime, so no config
  change is needed — the DEV app automatically routes to `TEMP.COCO_PARTNER_ADOPTION_DEV`.

### Run locally

`.streamlit/secrets.toml` holds the connection config (`authenticator = "externalbrowser"`).
Set `user` to your own Snowflake login or SSO fails with *"the user you were trying to
authenticate as differs from the user currently logged in at the IDP"*.

```bash
streamlit run streamlit_app.py --server.port 8512
```

Imported modules under `utils/` are not hot-reloaded — restart the server after editing them.

## Dependencies

- `streamlit` (Snowflake channel)
- `plotly`
- `pandas`
- `markdown`
