# PROD container runtime cutover: manual test matrix

Run every case on the rehearsal app `TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS_CR`
first, then again on PROD `COCO_USECASE_INSIGHTS` right after cutover.

Prerequisites:
- `pytest tests/test_runtime_callers_rights.py` passes (section A).
- `scripts/validate_runtime.sql` matches its expected values (section B).
- Two testers with **different** Salesforce row access, at least one of whom is not on `EXEC_EMAIL_USERS`.

| ID | Scenario | Steps | Expected | Result |
|---|---|---|---|---|
| C1 | Every page loads | Open each page in the nav with default filters | No exception banner, and charts and tables show data | |
| C2 | ACQ Theatre row access | Tester X opens ACQ Theatre and notes the opportunity count. Tester Y does the same | Each sees only their own rows. On the old warehouse-runtime PROD, compare the counts (it may show 0 rows) | |
| C3 | No cross-viewer cache leak | X and Y load ACQ Theatre at the same time in two browsers, then each refreshes | Neither sees the other's rows or count | |
| C4 | Executive Email visibility | Allowlisted tester opens the app, then a non-allowlisted tester does | Page shown only to the allowlisted tester. The default sender is the viewer, not the app owner (`SALES_ENGINEER` owner user) | |
| C5 | Default role differs from Snowsight role | Tester whose default role lacks SALES access opens ACQ Theatre | Data appears through secondary roles. If not, the tester's default role needs fixing, and that is not an app bug | |
| C6 | PSE Insights (REST API) | Generate one partner report | Cortex REST calls succeed. Latency is similar to DEV (no 390112 or auth errors) | |
| C7 | Ask AI | Ask one question with agent mode on, then one with it off | Both answer. Agent mode uses `TEMP.COCO_PARTNER_ADOPTION.COCO_AGENT` | |
| C8 | Caller's-rights token lifetime | Open the app, wait 3 minutes, then go to ACQ Theatre | Still loads as the viewer (the connection was made at session start) | |
| C9 | Deploy without stale modules | With a session open, redeploy a change touching `utils/`, then click to another page | No `ImportError` (the module-reload guard at the top of `streamlit_app.py` works) | |
| C10 | KPI parity | Same filters on old PROD and the `_CR` app: Adoption Metrics and OKR: CoCo Adoption totals | Numbers match exactly | |
| C11 | Cold start | Open the app after it has been idle for 30 minutes or more | First page renders, and record the load time | |
| C12 | Workshop stays DEV-only | In PROD, generate a PSE report | No workshop plans section. DEV still shows it | |

## Cutover
1. All C cases pass on `_CR`.
2. `find . -name __pycache__ -type d -exec rm -rf {} +`
3. `snow streamlit deploy coco_usecase_insights --project . --replace --prune --connection snowhouse --role SALES_ENGINEER --warehouse COCO_PARTNER_ADOPTION_WH --database TEMP --schema COCO_PARTNER_ADOPTION`
4. Re-run section B and cases C1, C2, C4 and C10 on PROD.
5. Drop `COCO_USECASE_INSIGHTS_CR` after a stable period.

## Rollback
Check out the last commit before this change (tag it before cutover), then redeploy `coco_usecase_insights`.
That entity has no `runtime_name`, so it rebuilds on warehouse runtime from `environment.yml`.
