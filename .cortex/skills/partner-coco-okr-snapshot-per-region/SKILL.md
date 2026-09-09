---
name: partner-coco-okr-snapshot-per-region
description: "Generate a standalone HTML report of CoCo (Cortex Code) skill-gap opportunities for a given theater/sub-region within the FY27 Q3 OKR window, via the full no-shortcuts REST LLM-as-judge grounding pipeline. Use when the user asks to generate, rerun, or refresh the skill-gap / skill opportunity report for any theater (USMajors, EMEA, APJ, LATAM) and sub-region (MFG, RCG, FSI, etc.), or mentions 'skill gap report', 'CoCo Q3 OKR snapshot', 'non-CoCo skill opportunities report'. Not a Streamlit page -- runs locally and writes an HTML file to disk."
---

# Partner CoCo OKR Snapshot Per Region

## Overview

Runs `scripts/partner_coco_okr_snapshot_per_region.py` (bundled with this skill), a standalone local script (not a Streamlit page) that:

1. Fetches every use case in a given `--theater` / `--subregion` combination for the FY27 Q3 OKR window (2026-08-01 to 2026-10-31), restricted to partners tracked for that OKR (same `MANAGED_PARTNERS` set `app_pages/executive_email.py` builds).
2. Splits them into CoCo-attached vs non-CoCo-attached (via `apply_coco_final`, same logic as the deployed app).
3. Runs the full REST-based LLM-as-judge grounding pipeline (identical to Approach 2 in `app_pages/pse_email_hybrid_rest.py` -- no shortcuts, real Cortex REST calls, real GPA scoring) against every non-CoCo use case to recommend CoCo skills.
4. Pulls account-level CoCo credit/token usage (`get_account_coco_credits`) to corroborate real product engagement.
5. Generates a short (~120-word) grounded executive narrative and several CSS-based charts (no external JS), and writes one self-contained HTML file to `output/reports/`.

Every run shares the same persistent judge cache (`COCO_PSE_JUDGE_CACHE`, `pipeline_tag='rest'`, `pipeline_version=7`) used by the deployed DEV app -- a use case judged once from any tool (this script, the SQL page, the REST page) is cached for all of them.

## When to Use

Invoke this skill whenever the user wants this report for **any** theater/sub-region combination, e.g.:
- "generate the skill gap report for RCG in USMajors"
- "rerun this for EMEA / FSI"
- "give me the CoCo Q3 OKR snapshot for APJ MFG"

Do not create a new Streamlit page or modify the app for this -- it is intentionally a local script the user runs on demand.

## Prerequisites

- The script (`scripts/partner_coco_okr_snapshot_per_region.py`, bundled inside this skill directory) locates the `coco-usecase-insights` repo root itself at runtime by walking up from its own path looking for a `utils/queries.py` marker file -- it does not need to be run from the repo root or copied anywhere, but it does need the `coco-usecase-insights` repo to exist somewhere above it on disk (true as long as this skill stays inside that repo's `.cortex/skills/` directory).
- Uses that repo's `.venv` (already has `snowflake-connector-python`, `pandas`, `requests`, `streamlit` installed) -- invoke the script with `<repo_root>/.venv/bin/python`, not a bare `python3`.
- Connects via `externalbrowser` SSO directly with `snowflake.connector.connect(...)` (bypasses `.streamlit/secrets.toml`, which is pinned to a different prod user) -- **every run requires the user to click through a browser SSO popup**, since `keyring` isn't installed to cache the token. This is expected, not an error.

## Workflow

### Step 1: Confirm scope

Ask the user (if not already stated) which `--theater` and `--subregion`(s) to run. Valid values are free-text `THEATER_NAME`/`REGION_NAME` values from `DT_OKR_USE_CASES` (e.g. theaters: `USMajors`, `EMEA`, `APJ`, `LATAM`; sub-regions: `MFG`, `RCG`, `FSI`, etc.) -- there's no fixed enum, so if unsure, confirm with the user rather than guessing.

### Step 2: Run the script in the background

The script blocks on the SSO popup and takes 1-3 minutes total (longer if there are real cache misses, since each non-CoCo use case runs live REST calls). Always run it with `run_in_background: true` and redirect output to a log file with unbuffered stdout (`python -u`), since piping through other commands block-buffers output and hides progress:

```bash
<repo_root>/.venv/bin/python -u <skill_dir>/scripts/partner_coco_okr_snapshot_per_region.py \
  --theater <THEATER> --subregion <SUBREGION> [<SUBREGION> ...] \
  > /tmp/skill_gap_report.log 2>&1
```

Where `<skill_dir>` is this skill's own directory (`.cortex/skills/partner-coco-okr-snapshot-per-region/`) and `<repo_root>` is the `coco-usecase-insights` checkout containing it -- the script only needs `<repo_root>/.venv` to exist; the output report is always written under `<repo_root>/output/reports/` regardless of where the command is run from.

Multiple `--subregion` values are space-separated (e.g. `--subregion MFG RCG`) and are combined into a single `REGION_NAME IN (...)` filter (not two separate reports).

### Step 3: Wait for the SSO login and poll for completion

Immediately after launching, tell the user a browser SSO window should have opened and ask them to click through it -- the process will sit idle at "Connecting to Snowflake..." until they do. Poll the log file (`bash_output` with `wait: true`, or `tail`) periodically. Known milestones in order:

1. `Connecting to Snowflake...` / `Going to open: https://...okta.com/...` -- waiting on the user's browser login.
2. `Connected. Using schema: ...`
3. `Fetching use cases for THEATER_NAME=... REGION_NAME in [...]` then a use case count.
4. `Running REST-based LLM-as-judge grounding pipeline...` -- per-use-case `cached` or `success` lines.
5. `Generating executive narrative...` → `Building HTML report...` → `Report written to: <path>`.

If the process sits idle for several minutes at step 1 with no new log lines, the popup may have been missed or closed -- kill the stale process (`kill <pid>`) and relaunch to get a fresh popup, rather than waiting indefinitely.

### Step 4: Verify the output

The report is written to `output/reports/<subregion_slug>_<theater_lower>_skill_report.html` (e.g. `mfg_usmajors_skill_report.html`, `rcg_usmajors_skill_report.html`), or to `--output <path>` if the user specified a custom path. Confirm it was written and spot-check the key numbers make sense (e.g. via a quick `grep`/`python3 -re` pass over the "Full FY27 Q3 OKR Scope" tile block) before telling the user it's ready -- don't just trust the "Report written to" log line blindly, since a partially-wrong report is worse than a slow one.

## Tools

### Script: partner_coco_okr_snapshot_per_region.py

**Usage:**
```bash
<repo_root>/.venv/bin/python -u <skill_dir>/scripts/partner_coco_okr_snapshot_per_region.py --theater <THEATER> --subregion <SUBREGION...> [--output <path>]
```

**Arguments:**
- `--theater` (required): `THEATER_NAME` value, e.g. `USMajors`.
- `--subregion` (required, 1+): one or more `REGION_NAME` values, e.g. `MFG` or `RCG FSI`.
- `--output` (optional): output HTML path. Default: `output/reports/<subregion_slug>_<theater_lower>_skill_report.html`.

**When NOT to use:** for a full FY27 Q3 OKR view across *all* theaters/sub-regions at once -- this script scopes to exactly one theater + one set of sub-regions per run. Run it once per scope needed.

## Notes

- The FY27 Q3 window (`Q_START`/`Q_END`, 2026-08-01 to 2026-10-31) is hardcoded at the top of the script, not a CLI flag -- editing those two constants is the only way to point at a different quarter.
- `_fetch_use_cases()` is a deliberately self-contained, table-qualified copy of `utils.queries.get_okr_coco_adoption`'s query rather than a call to that shared function -- `get_okr_coco_adoption`'s `_theater_filter()` helper emits an unqualified `THEATER_NAME = '...'` clause that's ambiguous against this script's multi-table join, a latent bug in the shared helper that's out of scope to fix here.
- `_ConnShim.query()` swallows `NotSupportedError` from `fetch_pandas_all()` and returns an empty DataFrame -- this is intentional, since INSERT/CREATE statements (used by the shared `utils/judge_cache.py`) have no result set to fetch and their return value is unused by the caller.
- The two stacked-bar charts ("CoCo adoption by Workload" and "CoCo Adoption by Partner (Account Split)") encode CoCo-attached-vs-not within each segment as **filled vs. hollow/outlined** blocks, not shading -- a diagonal hatch pattern and later a light color-tint were both tried and rejected as too subtle to read at the ~14px bar height; filled-vs-hollow plus an explicit "X/Y" chip caption under each bar is the current design.

## Output

One self-contained HTML report at `output/reports/<subregion_slug>_<theater_lower>_skill_report.html`, containing, in order: a full-scope KPI summary (OKR partners/use cases/accounts/CoCo split) plus a "partners with a skill gap" summary tile block, a CoCo attach-split chart, a short grounded executive narrative, a "CoCo adoption by Workload" chart (each partner's use-case mix by category -- AI/Analytics/Data Engineering/Platform/etc. -- with a filled block for the CoCo-attached share and a hollow/outlined block for the not-yet-attached share per category, plus an exact-count chip caption under each bar), a "CoCo Adoption by Partner (Account Split)" chart (same filled-vs-hollow encoding, but each partner's bar is split by account instead of by category), an account-level CoCo credit/token usage table (all accounts, with linked, comma-separated use case names), a non-CoCo EACV-by-partner chart, a non-CoCo stage-distribution chart, a static PSE-engagement commentary callout, and per-partner detail tables of every non-CoCo use case with its judged CoCo skill recommendations.

