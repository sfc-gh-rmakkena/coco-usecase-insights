# Snowflake AIM — Supported Migration Sources

This is the human-readable reference for the source-detection list used by
`app_pages/pse_email_hybrid.py` (via `utils/coco_skill_map_v2.py`) to decide
when a non-CoCo use case should recommend **Snowflake AIM** instead of the
generic CoCo migration skills (`migration-guide`, `snowconvert-assessment`,
`spark-migration`, `snowpark-connect`).

Source: `utils/Migrations Support Matrix (go_migrations-matrix).xlsx`'s
"Main - Matrix" tab (ground-truth capability tracker), cross-checked against
`utils/AI Assisted Migration Delivery for Partners (3).pptx`'s positioning
deck. The code list (`AIM_SOURCE_PATTERNS` in `coco_skill_map_v2.py`) is the
16-source Support Matrix column list, not the narrower 11-source marketing
slide — this was an explicit choice to match actual tracked capability
rather than the headline pitch.

## Behavior

Detection is **fully deterministic** (word-boundary regex, no LLM call). It
scans, for each non-CoCo use case:
- `USE_CASE_NAME`
- `TECHNICAL_USE_CASE`
- the raw use case description
- raw `SE_COMMENTS`

If any pattern below matches, that use case's skill recommendations are
overridden: the 4 generic migration skills are stripped, and a single
`Snowflake AIM` recommendation is inserted first, with the rationale
`"<Source> is a supported source in Snowflake AIM for migration."` This
override is applied twice in the pipeline (once at the deterministic base,
once again after the AI additional-skills merge) so an AI suggestion can
never reintroduce a generic migration skill. See `apply_aim_override()` in
`coco_skill_map_v2.py`.

Only the **first** matching source (by the table order below) is used per
use case — if a description genuinely mentions two legacy sources, only one
gets flagged, to keep the rationale sentence to one clean line.

## Supported sources (detection order)

| # | Canonical name | Matches on (case-insensitive, word-boundary) | Matrix coverage notes |
|---|---|---|---|
| 1 | SQL Server | `sql server`, `ssis` | Most mature — nearly all capability rows ✅ |
| 2 | Redshift | `redshift` | Most mature — nearly all capability rows ✅ |
| 3 | Teradata | `teradata`, `bteq`, `tpt`, `fastload`, `multiload`, `tpump` | Most mature — nearly all capability rows ✅ |
| 4 | Oracle | `oracle` | Most mature — nearly all capability rows ✅ |
| 5 | Azure Synapse | `azure synapse`, `synapse` | Thin — engine support (deterministic code conversion) only |
| 6 | BigQuery | `bigquery`, `big query` | Partial — engine support + some extract/deploy |
| 7 | IBM DB2 | `db2` | Partial — general engine support only |
| 8 | Postgres | `postgres`, `postgresql` | Partial — general engine support + extract/deploy |
| 9 | Hive | `hive` | Thin — engine support only |
| 10 | Vertica | `vertica` | Thin — engine support only |
| 11 | Databricks SQL | `databricks sql` (requires "sql", not bare "databricks") | Thin — engine support only |
| 12 | Spark SQL | `spark sql` (requires "sql", not bare "spark") | Thin — engine support only |
| 13 | Sybase IQ | `sybase`, `sybase iq` | Thin — engine support only |
| 14 | SAS | `sas` | Thin — engine support only (see caveat below) |
| 15 | Netezza | `netezza` | Thin — engine support only |
| 16 | Informatica | `informatica` | ETL tool — Informatica2Dbt / Informatica2Sql conversion |

Note: SSIS is matched under **SQL Server** (its parent platform), not as a
separate row, since the Support Matrix groups `SSIS2Dbt` under the ETL/BI
category but SSIS is SQL Server's own ETL tool.

## Known caveats

- **Short/ambiguous tokens**: `SAS`, `DB2`, and `Hive` are short strings.
  Word-boundary matching (`\b`) prevents them from matching *inside* longer
  words (e.g. `\bhive\b` will not match "archive"), but a use case that
  happens to use "SAS" as an unrelated acronym (e.g. a compliance standard
  or someone's initials) could still false-positive. Accepted tradeoff,
  since the Support Matrix explicitly tracks SAS as a real source.
- **Only the first match wins**: a use case mentioning multiple sources
  only gets flagged for whichever appears first in table order above (e.g.
  Redshift is checked before Teradata, which is checked before Oracle — if
  a description mentions both Redshift and Oracle, only Redshift is used).
- **Databricks SQL / Spark SQL require "sql" explicitly** — bare
  "Databricks" or "Spark" alone do NOT trigger AIM detection, since those
  terms are heavily overloaded (used elsewhere for generic Spark/Databricks
  modernization discussions that aren't necessarily the AIM DW-migration
  flavor tracked in the Support Matrix).
- **No re-ranking when multiple sources are relevant** — this is a
  single-source detector by design, for a single clean rationale sentence,
  not a full migration-portfolio classifier.

## Where this is implemented

- `utils/coco_skill_map_v2.py` — `AIM_SOURCE_PATTERNS`, `detect_aim_source()`,
  `apply_aim_override()`, `cap_skills()`, `prioritize_aim_skill()`.
- `app_pages/pse_email_hybrid.py` — wires detection into
  `_group_non_coco_by_region()` (deterministic base) and re-applies the
  override after the AI additional-skills merge in `_build_gap_table_rows()`
  and the narrative's NoAM top-4 preview block, plus the Action Plan /
  narrative rollup logic that keeps the aggregated skill list and rationale
  consistent with whichever use case is AIM-eligible.

If the Migrations Support Matrix changes (new source added, coverage
matures), update `AIM_SOURCE_PATTERNS` in `coco_skill_map_v2.py` and this
table together.
