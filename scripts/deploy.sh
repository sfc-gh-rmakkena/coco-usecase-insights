#!/usr/bin/env bash
# =============================================================
# deploy.sh — Deploy DEV or PROD Streamlit app
# Usage:
#   ./scripts/deploy.sh dev
#   ./scripts/deploy.sh prod
# =============================================================

set -euo pipefail

ENV=${1:-}

if [[ -z "$ENV" ]]; then
  echo "Usage: $0 [dev|prod]"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$ENV" == "dev" ]]; then
  echo "Deploying DEV app (COCO_USECASE_INSIGHTS_DEV)..."
  snow streamlit deploy \
    --file "$REPO_ROOT/snowflake.dev.yml" \
    --connection snowhouse \
    --role SALES_ENGINEER \
    --warehouse COCO_PARTNER_ADOPTION_WH \
    --database TEMP \
    --schema COCO_PARTNER_ADOPTION_DEV \
    --replace
  echo "DEV deploy complete."

elif [[ "$ENV" == "prod" ]]; then
  echo "Deploying PROD app (COCO_USECASE_INSIGHTS)..."
  snow streamlit deploy \
    --file "$REPO_ROOT/snowflake.yml" \
    --connection snowhouse \
    --role SALES_ENGINEER \
    --warehouse COCO_PARTNER_ADOPTION_WH \
    --database TEMP \
    --schema COCO_PARTNER_ADOPTION \
    --replace
  echo "PROD deploy complete."

else
  echo "Unknown environment: $ENV. Use 'dev' or 'prod'."
  exit 1
fi
