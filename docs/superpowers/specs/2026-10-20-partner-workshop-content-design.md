# Partner Workshop Content — Design Spec

Date: 2026-10-20 · Page: `app_pages/pse_email_hybrid_rest.py` · Scope: **DEV only** (`TEMP.COCO_PARTNER_ADOPTION_DEV`)

## Goal
Turn the partner report into an action plan: for every non-CoCo use case not yet in production, generate a ready-to-run workshop (Session 1: get started with CoCo; Session 2: co-build) that the partner and Snowflake PSE deliver together with the customer. Fully automated — no user action beyond generating the report as today.

## Non-goals
- No change in PROD behavior.
- No change to existing report content except: hide Deployed (stage 7) rows in the overview table, add the scope note.
- Headline totals (counts, EACV, attach rate, regional totals) unchanged — still include Deployed.
- Deferred issues list (GPA legend, NoAM mismatch, etc.) handled separately.

## 1. Trigger and caching
- Runs inside the existing report generation when `get_env() == "dev"`.
- Input: rows from `_group_non_coco_by_region` with stage != 7.
- Per use case, parallel on the existing 32-worker REST pool (`cortex_complete_rest`, `claude-sonnet-4-5`), logged via `_RestCallLog`.
- Cache: L1 session (`_pse_hybrid_rest_workshop_*`) + L2 dedicated table `<schema>.COCO_PSE_WORKSHOP_CACHE` (hash, version, partner, uc_id, payload VARIANT), keyed by sha256 of all inputs + bundled-asset versions.
- Failure of any use case's generation degrades that tab to the brief + Session 1 deterministic fallback prompts; report still renders.

## 2. Account gate (internal only — never rendered)
- Normalize account name (lowercase, strip punctuation and legal suffixes: inc, corp, llc, ltd, plc, ag, gmbh, co) and require **exact** match to normalized `SNOWHOUSE.IT.RAW_GOOGLE_SHEETS.TOP_SNOWFLAKE_COMPANIES.COMPANY_NAME`. Any ambiguity → treated as not listed.
- **Listed:** fetch A360 context from `SALES.REPORTING.COCO_ACCOUNT_COCO_USAGE` and `SALES.REPORTING.COCO_USER_MATURITY_SNAPSHOT`, reduced to policy-allowed signals: CoCo usage tier (Big / Low / No), surfaces in use (Snowsight / CLI-Desktop), enablement-needed flag, dominant user maturity. (Neither A360 table carries industry.) Used only to tailor prompts; no numbers rendered.
- **Not listed:** no A360 queries. Session 1 prompts derived solely from the CoCo skills already proposed for the use case in the report.
- Audit: insert `(partner, uc_id, path, generated_at)` into a DEV table `TEMP.COCO_PARTNER_ADOPTION_DEV.WORKSHOP_GENERATION_AUDIT`. Not exported.
- Output structure, headings, and length bands are identical across both paths.

## 2a. Implementation-plan context (all accounts, read-only, never rendered)
Per *PSE_UC_Implementation_Plan_Data_Sources_Reference v3*, the skill reads 61 fields and renders only 4 (account name, use case name, rewritten description, partner name). The app reproduces this: Session 2's implementation-plan call receives the full field set as private context, keyed by `USE_CASE_ID`, from sources verified readable by `SALES_ENGINEER`:
- `SNOW_CERTIFIED.SALESFORCE_USE_CASE.DD_SALESFORCE_USE_CASE` — description, technical UC, workloads, industry UC, stage/status, decision/go-live/impl-start/tech-win dates, SE/partner/implementation/specialist comments, next steps, loss description, MEDDPICC pain/metrics/decision criteria/process, competitors, incumbent, champion, POC led by/stage, implementer, mission critical, PS engagement, cloud provider/region, line of business, risk description, future-state diagram link (dropped before prompt).
- `SNOW_CERTIFIED.SALESFORCE_ACCOUNT.DD_SALESFORCE_ACCOUNT` (join `SALESFORCE_ACCOUNT_ID`) — industry/sub-industry, billing country/state, website, employees, type, segment.
- `SALES.RAVEN.SDA_USE_CASE_VIEW` — fallback/gap fill (EACV deliberately not selected).
- Not available in Snowflake (skipped, logged): Account Description, Manager_Notes, Use_Case_Summary, Win_Summary, Tools, Business_Activity, Primary/Secondary Value Driver, Technical_Campaign, Path_to_Production, Service_Type, Assessment_Folder, Champion_Deck.
- Never sent to the LLM: EACV/credit amounts, internal links, people's names are passed only as "a named champion exists" style flags.
- Applies to both gate paths (the user's direction: Session 2 always uses skill details). The skill's own rule — use internal fields to understand, never to expose — plus §5 scrub enforces non-disclosure. Rendered output limited to the skill's 4 fields plus generated plan content.
- Session 1 still follows §2 (A360 only for listed accounts; skills-only otherwise) and does not receive §2a context.

## 3. Session 1 — Get started with CoCo
LLM call with the full bundled `coco-customer-activation-planner/SKILL.md` as instructions + the override block (§4a), asked to produce only its starter-prompts section. Three starter prompts per use case, following the skill's prompt structure: (1) discovery of relevant data/objects, (2) build step using the proposed CoCo skill, (3) extension/next step. Each with one-line purpose and copyable prompt text.

## 4. Session 2 — Co-build
- **Recipe match:** bundled `recipes_index.json` (title, description, topics, features for the 23 cookbook recipes) + use case brief → one LLM call returning `{recipe_id, confidence 0–100, rationale}`.
  - `> 80`: include recipe walkthrough (bundled markdown).
  - `50–80`: one-line "Closest recipe: <title> · <score>% — reference".
  - `< 50`: omitted.
- **Implementation plan:** one LLM call with the full bundled `pse-uc-implementation-plan/SKILL.md` (+ its `templates/report_template.html` section structure) as instructions + the override block (§4a) → architecture, implementation steps, SQL patterns, CoCo prompts, documentation links. Links restricted to a bundled allowlist (from recipes + skill); no runtime web/MCP access.

## 4a. Skill override block (prepended, takes precedence over skill text)
1. You have no tools (no Salesforce MCP, docs search, web search, SQL). Use only the context supplied; skip steps that require tools.
2. Ignore the skill's "Red Light List" pre-check; the account gate (§2) has already been applied by the app. Never mention lists, gates, or classification.
3. Disclosure rules are those in §5 (Alliances Data Sharing deck); where the skill and §5 differ, §5 wins.
4. Return only the requested section(s) as JSON matching the app's schema; no HTML.
5. Use only links from the supplied allowlist.

## 5. Compliance controls (all generated text)
- Prompt rules forbid: EACV/pricing/contract/renewal, consumption numbers, stage, health/churn/maturity scores as numbers, people's names, competitors, internal links/IDs, verbatim SE/MEDDPICC text, any mention of data availability, lists, tiers, or account classification.
- Post-processing: existing `_judge_sanitize_batch`, then deterministic regex scrub (currency amounts, credit/number-of-credits patterns, `red`/`green`/`light list`/`restricted`/`top snowflake`, URLs not in allowlist). Hits are removed; repeated hits trigger regeneration once, then fallback.

## 6. Rendering
- **Scope note** directly below the top header (HTML and PDF):
  > The summary above reflects all use cases in the selected period. The sections that follow focus only on use cases not yet in production — each with a ready-to-run workshop plan for the partner and Snowflake to co-build with the customer.
- Overview table: Deployed rows hidden; all other content unchanged.
- **HTML workshop section (Option B):** left sidebar listing use cases (account · use case name as shown in the table); right pane with sub-tabs Brief / Session 1 / Session 2. CSS-only (radio inputs + `:checked`), no JavaScript, inline styles consistent with `_build_report_html`.
- **PDF (`_build_report_pdf_bytes`, reportlab):** existing pages, then per use case on a new page: Brief → Session 1 → Session 2.

## 7. Packaging
New package `utils/workshop/` (ships via the existing `utils/` artifact; imported only when `get_env()=="dev"`, so PROD is unaffected):
- `generator.py` — gate, A360 fetch, LLM calls, scrub, caching
- `render.py` — HTML and PDF sections
- `assets/recipes_index.json`, `assets/recipes/<id>.md`
- `assets/skills/coco-customer-activation-planner/SKILL.md` and `assets/skills/pse-uc-implementation-plan/{SKILL.md,templates/report_template.html}` — verbatim copies
- `assets/skill_override.md` — the §4a block
- `assets/skills/VERSIONS.json` — source path + sha256 of each copied file
- `assets/link_allowlist.json`
- A build script `scripts/bundle_workshop_assets.py` regenerates recipe assets from `cortex-ai-cookbook/recipes` and re-copies both skills from their source locations (stage cache / local repo), updating `VERSIONS.json`. Run before each DEV deploy; skill sha changes bump the `workshop` cache version automatically.

## Testing
- Unit: name normalization/gate, scrub regexes, recipe threshold bands, render with fixed fixtures (both gate paths produce identical structure).
- Integration in DEV: Deloitte (11 use cases) end-to-end; verify no forbidden terms in HTML/PDF text, cache hit on rerun, audit rows written.
