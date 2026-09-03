# Cortex Code Skills Catalog

**111 skills across 9 categories.** Complete inventory of the skills that ship
**by default** with the Cortex Code (CoCo) CLI, generated directly from each skill's own
`SKILL.md`.

> **Scope of this catalog — default install only.** Every skill documented here is part of
> a stock Cortex Code installation: the 78 bundled Snowflake skills, plus the three plugins
> that ship inside the CoCo install (`data`, `blueprints`, `databricks`). Skills that a user
> may have added locally — third-party plugins from GitHub, remote skill repositories, or
> skills published to a Snowflake stage — are **deliberately excluded**, so a partner reading
> this can rely on everything below being available to them the moment they install CoCo.
> See Appendix A for what was excluded and why.

## How to read this document

A **skill** in Cortex Code is not a prompt template. It is a directory containing an
instruction file (`SKILL.md`), plus supporting reference documents, executable scripts,
SQL templates, and often nested **sub-skills** for specific branches of the workflow. When
a user's request matches a skill's trigger vocabulary, CoCo loads that skill's
instructions into context before it acts — so the agent works from Snowflake-authored,
version-matched procedure rather than from model recall.

That distinction is the point of this catalog. The value to a customer is not "the AI knows
Snowflake." It is that for 111 distinct workflows, the correct sequence,
the current syntax, the required privileges, and the known failure modes are already
written down and are loaded automatically.

**Each entry below documents:**

| Field | Purpose |
|-------|---------|
| Summary | One sentence, plain English, for a Solution Engineer |
| Snowflake surface it drives | The concrete features, objects, commands and APIs touched. **This is the field to match use cases against.** |
| What it accelerates | What the skill removes from a task a customer already does manually |
| Representative use cases | Customer-voice statements of need — the matching targets |
| Example prompts | Verbatim text a user types into CoCo to trigger the skill |
| Depth behind it | Supporting file and sub-skill count — evidence the skill is substantive |
| Prerequisites & caveats | Privileges, editions, previews, and explicit scope boundaries |
| Pairs with | Skills commonly used in the same workflow |

## How skills are invoked

| Method | Example |
|--------|---------|
| **Automatic** | User describes a need; CoCo matches trigger vocabulary and loads the skill. This is the normal path. |
| **Explicit `$` trigger** | `$agent-studio` — force a specific skill |
| **Namespaced (plugin skills)** | `data:authoring-dags`, `superpowers:brainstorming` |
| **Slash command** | Some skills register one, e.g. `/automation`, `/guardrails` |
| **Skill management** | `/skill` to list, add, remove, sync; `cortex skill list` from the shell |

Skills marked **[REQUIRED]** in their own description are mandatory entry points: CoCo is
instructed to load them *before* writing any code or SQL in that domain, rather than
attempting the task from general knowledge.

## Positioning note for partner conversations

Three framings that land well:

1. **Compression of ramp time.** A skill encodes what a specialist SE knows about one
   Snowflake surface. A generalist engineer invoking it gets the specialist's sequence.
2. **Guardrails, not just generation.** Many skills exist to *prevent* a wrong move —
   `data-governance`, `guardrails-guide`, `sql-author`, `dynamic-tables` all encode known
   failure modes and refuse the naive approach.
3. **Extensible by the partner.** `skill-development`, `find-skill-and-plugin` and
   `share-skill-and-plugin` mean a partner can author their own skills for their own
   accelerators and IP, and publish them to their account's catalog.

---

## Complete skill index

### AI, Cortex & Machine Learning (8)

| # | Skill | What it does |
|---|-------|--------------|
| 1 | [`agent-studio`](#agent-studio) | Router skill for building, editing, auditing, and optimizing Semantic Views and Cortex Agents in Snowflake, including importing BI tool models and managing Verified Query Representations. |
| 2 | [`cortex-ai-function-studio`](#cortex-ai-function-studio) | Required entry point for all Snowflake built-in and custom AI function operations — running `AI_*` SQL, creating domain-specific custom functions, evaluating their accuracy, and optimizing prompts and model selection for cost/quality tradeoff. |
| 3 | [`ai-functions-pipeline-builder`](#ai-functions-pipeline-builder) | Builds Snowflake-native incremental document and file processing pipelines — turning a plain-language request into a stream → task → dynamic-table architecture using Cortex AI functions, either from a proven use-case template or a custom block composition. |
| 4 | [`document-intelligence`](#document-intelligence) | Applies Snowflake Cortex AI functions (`AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_CLASSIFY`, `AI_COMPLETE`) to a single file or one-time batch on a stage, and fine-tunes the `arctic-extract` model for domain-specific extraction accuracy. |
| 5 | [`cortex-sense`](#cortex-sense) | Builder experience for creating, testing, refining, and deploying Cortex Sense domain contexts — scoped business-data understanding layers that ground Cortex Code and CoWork agents in a customer's specific tables, metrics, and terminology. |
| 6 | [`ai-readiness-score`](#ai-readiness-score) | Measures a Snowflake account's AI readiness by scoring Consumption-Ready tables, Semantic View coverage and quality, and query demand coverage, then generates an HTML scorecard report with prioritized recommendations. |
| 7 | [`machine-learning`](#machine-learning) | Router skill for all Snowflake data science and ML tasks — covers the full lifecycle from training and preprocessing through model registry, SPCS inference, batch inference, distributed training, feature store, experiment tracking, pipeline orchestration, monitoring, and lineage, dispatching to 17 specialized sub-skills. |
| 8 | [`ai-data-share`](#ai-data-share) | Creates a complete AI-ready data product from a Snowflake listing or share — resolves the source, generates a Semantic View, creates and configures a Cortex Agent, and grants all objects to the share. |

### Data Engineering & Pipelines (14)

| # | Skill | What it does |
|---|-------|--------------|
| 9 | [`dynamic-tables`](#dynamic-tables) | Required entry point for all Snowflake Dynamic Table work: creating pipelines, monitoring health, troubleshooting refresh failures, optimizing performance, and converting dbt or streams+tasks pipelines to dynamic tables. |
| 10 | [`dynamic-tables-apply-recommendations`](#dynamic-tables-apply-recommendations) | Reads Snowflake-emitted recommendations from the `RECOMMENDATIONS` column of a specific dynamic table and applies targeted DDL fixes — from refresh-mode changes to zero-downtime Iceberg V2-to-V3 swaps. |
| 11 | [`snowflake-tasks`](#snowflake-tasks) | Covers the full lifecycle of Snowflake Tasks: creating scheduled and stream-triggered tasks, building task graphs (DAGs), managing execution, querying run history, and troubleshooting failures. |
| 12 | [`snowpipe-streaming`](#snowpipe-streaming) | Guides users through setting up, troubleshooting, monitoring, optimizing, and migrating Snowpipe Streaming pipelines using the High-Performance Architecture exclusively. |
| 13 | [`openflow`](#openflow) | Covers the full lifecycle of Openflow (Snowflake's NiFi-based data integration product): deploying connectors, managing flows, configuring parameters, troubleshooting errors, and authoring custom NiFi flows, across both SQL-managed (gen 2) and NiFi-API (gen 1) architectures. |
| 14 | [`openflow-observability`](#openflow-observability) | Diagnoses Openflow connector, runtime, and deployment failures via Snowsight SQL diagnostics, and executes a narrow allowlist of SQL actions on SQL-managed (gen 2) runtimes after explicit confirmation. |
| 15 | [`snowpark-python`](#snowpark-python) | Guides users through writing, deploying, and instrumenting Snowpark Python code — pipelines, UDFs, stored procedures, and ETL — with built-in awareness of Snowflake-specific DataFrame semantics that silently differ from standard Pandas/Python. |
| 16 | [`dbt-projects-on-snowflake`](#dbt-projects-on-snowflake) | Manages dbt projects deployed as native Snowflake objects via `snow dbt`, and authors Snowflake-specific dbt materializations (`semantic_view`) — explicitly not for standard `dbt run` / local dbt CLI workflows. |
| 17 | [`dcm`](#dcm) | Required entry point for all Database Change Management (DCM) work: creating, modifying, deploying, and debugging `snow dcm` projects that manage Snowflake infrastructure as code using a declarative YAML manifest with `DEFINE` primitives. |
| 18 | [`error-tables-ops`](#error-tables-ops) | Assesses, enables, monitors, and manages Snowflake DML Error Logging (Error Tables) — the feature that lets good rows succeed while capturing rejected rows for analysis and repair instead of rolling back the entire DML statement. |
| 19 | [`alert`](#alert) | Router that delegates to `alert-create-alter` for creating/modifying Snowflake Alerts, or to `alert-troubleshoot` for diagnosing why an alert is firing, failing, or not delivering. |
| 20 | [`notification`](#notification) | Router that directs requests to sub-skills for creating/managing notification integrations, formatting notification content for specific platforms, or sending notifications via `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`. |
| 21 | [`integrations`](#integrations) | Router with 23 sub-skills covering every Snowflake integration type — API, catalog, external access, notification, security, and storage — for `CREATE`, `ALTER`, `DROP`, `DESCRIBE`, and `SHOW` operations. |
| 22 | [`event-table`](#event-table) | Router for Snowflake Event Table and telemetry configuration tasks: reading current setup, modifying configuration, and parsing product-specific telemetry event formats from Dynamic Tables, Tasks, Snowpark, and Openflow. |

### Governance, Security & Trust (17)

| # | Skill | What it does |
|---|-------|--------------|
| 23 | [`data-governance`](#data-governance) | Routes governance requests — sensitive-data discovery and classification, protection policies, access evidence, ownership, maturity assessment, and observability — to the correct specialized workflow. |
| 24 | [`intent-driven-governance`](#intent-driven-governance) | Guides the user through a 5-phase commit-based workflow — Observe, Capture Intent, Derive Governance Spec, Generate SQL, Execute — to apply Snowflake governance changes safely with an explicit human approval gate before any mutation runs. |
| 25 | [`data-quality`](#data-quality) | Monitors, investigates, and enforces data quality across Snowflake schemas using Data Metric Functions (DMFs), with separate monitoring paths for tables, schemas, and Cortex Agents, plus prompt quality scoring and table-comparison workflows. |
| 26 | [`lineage`](#lineage) | Traces upstream and downstream object and column lineage in Snowflake using `SNOWFLAKE.CORE.GET_LINEAGE()`, with dedicated workflows for impact analysis, root-cause tracing, data discovery/trust, and column-level lineage. |
| 27 | [`business-ontology`](#business-ontology) | A router and workflow orchestrator for Snowflake Business Ontology: creating, importing (from files, dbt, Semantic Views, stage sources), deleting, and syncing governed business nodes, domains, relationships, and object representations via the `SYSTEM$` draft-activate API. |
| 28 | [`certify-object`](#certify-object) | Applies `SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED'` to a named Snowflake table or view, confirms the tag is live via `SYSTEM$GET_TAG`, and provides the exact `GRANT APPLY ON TAG` SQL if permissions are insufficient. |
| 29 | [`certified-data-product-discovery`](#certified-data-product-discovery) | Searches Snowflake for certified data products relevant to a user's question using Snowscope, classifies results by certification status and Discover-Not-Access (DNA) standing, presents a grouped menu, and executes SQL against the chosen certified object. |
| 30 | [`recommend-object`](#recommend-object) | Scores and ranks already-identified candidate Snowflake objects by trustworthiness using a 105-point rubric covering semantic view backing, human-verified queries, pipeline ownership, Streamlit dependencies, schema governance signals, and data freshness. |
| 31 | [`access-troubleshooter`](#access-troubleshooter) | Debugs Snowflake authorization failures, analyzes required privileges for a SQL statement, finds authorizing roles, and creates least-privilege roles — using `EXPLAIN_PRIVILEGES`, `SYSTEM$ANALYZE_ROLE_ACCESS`, and `SYSTEM$SUGGEST_ROLE_GRANTS`. |
| 32 | [`security-investigation`](#security-investigation) | Routes Snowflake security investigations to three specialized sub-skills — login/IP anomalies, data exfiltration, and privilege escalation — covering MITRE ATT&CK T1078/T1098/T1530/T1537 threat categories, with a full-scan option that sequences all three. |
| 33 | [`trust-center`](#trust-center) | Routes Snowflake Trust Center requests to four sub-skills covering security findings analysis, scanner inventory, scanner configuration (enable/disable/schedule/notify), and step-by-step finding remediation. |
| 34 | [`network-security`](#network-security) | Recommends, evaluates, and migrates Snowflake network policies using built-in stored procedures, automatically checks which IPs are covered by Snowflake-managed SaaS rules, and generates hybrid policies combining custom and SaaS rules. |
| 35 | [`manage-authentication-policy`](#manage-authentication-policy) | Creates, modifies, views, attaches, detaches, drops, and recommends Snowflake authentication policies controlling allowed auth methods (PASSWORD, SAML, OAUTH, KEYPAIR), MFA enforcement, PAT expiry, client types, minimum driver versions, and workload identity federation. |
| 36 | [`setup-snowflake-sso`](#setup-snowflake-sso) | Configures Snowflake Single Sign-On for Microsoft Entra ID, Okta, or any SAML 2.0 provider, supporting manual UI, self-service `curl`, and automated API methods, with additional workflows for Allowed Interfaces, Auto Redirect, and Snowflake Intelligence tile setup. |
| 37 | [`key-and-secret-management`](#key-and-secret-management) | Routes Tri-Secret Secure (TSS) and customer-managed key (CMK) requests to the `tri-secret-secure` sub-skill, and handles periodic data rekeying by directing to Snowflake documentation for the `PERIODIC_DATA_REKEYING` account parameter. |
| 38 | [`cortex-secrets`](#cortex-secrets) | Enforces the Cortex Code credential workflow: silently checks `cortex secret list` before any command requiring a token or API key, injects stored secrets via the `VAR="<key>"` bash syntax, and directs users to `/secrets` as the only user-facing interface for credential storage. |
| 39 | [`guardrails-guide`](#guardrails-guide) | Walks the user through creating, activating, and troubleshooting Restricted Session Scope (RSS) objects via the `/guardrails` panel, to limit which SQL operations and Snowflake roles the Cortex Code agent session may assume. |

### Cost, Performance & Platform Operations (8)

| # | Skill | What it does |
|---|-------|--------------|
| 40 | [`cost-intelligence`](#cost-intelligence) | Answers "what am I spending credits on and why," and lets you create/manage the guardrails (budgets, quotas, anomaly monitors) that keep spend in check — all via `SNOWFLAKE.ACCOUNT_USAGE` and the `SNOWFLAKE.LOCAL`/`SNOWFLAKE.CORE` classes, never semantic views. This is a router that dispatches to six sub-skill groups. |
| 41 | [`billing`](#billing) | Answers "how much am I spending in dollars/currency" at the organization level — contract terms, balances, invoices, and rates — as distinct from credit-based analytics. A router with two sub-skills. |
| 42 | [`organization-management`](#organization-management) | Router for everything at the Snowflake organization (multi-account) control plane: account lifecycle, org users, replication, and executive-level org insights — distinct from single-account cost or billing analytics. |
| 43 | [`warehouse`](#warehouse) | Routes warehouse configuration and DDL questions (Gen2, Adaptive, sizing, performance tuning) to the right sub-skill — explicitly not the place for warehouse cost analytics. |
| 44 | [`workload-performance-analysis`](#workload-performance-analysis) | Diagnoses why SQL queries and warehouses run slow — spilling, pruning, caching, clustering, QAS eligibility — via `ACCOUNT_USAGE`, as a unified single entry point across 11 entity types and 3 depths of analysis. |
| 45 | [`snowflake-interactive`](#snowflake-interactive) | Sets up and troubleshoots Snowflake Interactive Tables and Interactive Warehouses — the low-latency, high-concurrency path for dashboards, APIs, and agentic queries — including zero-copy interactive analytics directly on standard or Iceberg tables. |
| 46 | [`storage-lifecycle-policy`](#storage-lifecycle-policy) | Creates and manages automated data-tiering rules — expire old rows outright, or archive them to cheaper COOL/COLD storage before expiring — to cut storage costs without manual cleanup jobs. |
| 47 | [`automation`](#automation) | Schedules recurring Cortex Code runs as Snowflake `AGENT TASK`s — cron-like unattended jobs that can query Snowflake and, via attached MCP servers, read/write Slack, Jira, Gmail, and Google Drive too. Internal/meta skill: it's about operating Cortex Code itself, not a Snowflake data feature. |

### Sharing, Collaboration & Marketplace (13)

| # | Skill | What it does |
|---|-------|--------------|
| 48 | [`sharing`](#sharing) | Routes an open-ended or comparison sharing request to the right Snowflake sharing construct — Secure Data Sharing, Declarative Sharing, Native Apps, or Data Clean Rooms — by asking up to two questions. |
| 49 | [`data-sharing`](#data-sharing) | Creates and troubleshoots Snowflake Secure Data Sharing constructs — direct shares, external Marketplace listings, organization listings, reshared imported databases, and external (Iceberg/S3) data shares. |
| 50 | [`declarative-sharing`](#declarative-sharing) | Builds and releases `APPLICATION PACKAGE TYPE=DATA` (declarative shares / data apps) that bundle tables, views, agents, semantic views, workspaces, and UDFs into a versioned, consumer-installable product without a setup script. |
| 51 | [`internal-marketplace-org-listing`](#internal-marketplace-org-listing) | Creates and publishes organizational listings on Snowflake's Internal Marketplace to share data products (tables, views, semantic views, agents, Cortex Search) with other accounts inside the same Snowflake organization. |
| 52 | [`marketplace-provider`](#marketplace-provider) | Routes Snowflake Marketplace provider tasks — profile setup, listing creation for all product types (Data Share, Native App, DSNA, Connected App, CKE, Cortex Agent, Semantic View), monetization, and provider success — to the correct sub-skill. |
| 53 | [`marketplace-search`](#marketplace-search) | Searches the Snowflake Marketplace (public, internal, or both) for listings matching a user's data or application need using the `cortex search marketplace` CLI, scoped to the user's current region by default. |
| 54 | [`get-marketplace-listing-details`](#get-marketplace-listing-details) | Produces a fixed four-part recommendation write-up for a single Snowflake Marketplace listing — why it fits the user's need, delivery method, access type, and how it solves the problem — grounded in `SYSTEM$BULK_GET_LISTINGS` and the listing's data dictionary. |
| 55 | [`listing-observability`](#listing-observability) | Monitors listing health, consumption, audit state, cost attribution, and consumer-side data freshness for Snowflake listing providers and consumers by routing to focused workflow files. |
| 56 | [`attach-ai-products-to-share`](#attach-ai-products-to-share) | Grants semantic views, Cortex Agents, and Cortex Search Services to an existing Snowflake share in the correct privilege sequence, enabling AI-Ready Marketplace and org listings. |
| 57 | [`data-cleanrooms`](#data-cleanrooms) | Manages the full Snowflake Data Clean Room (DCR) Collaboration API lifecycle — creating collaborations, registering data offerings and templates, running analyses and activations, managing RBAC, and tearing down — by routing to 14 sub-skills after mandatory database discovery. |
| 58 | [`native-app-provider`](#native-app-provider) | Builds, deploys, versions, publishes, and monitors Snowflake Native Apps — including SPCS containers, Streamlit UIs, agents/MCP servers, restricted caller rights, telemetry, and event sharing — by routing to 17 specialized sub-skills. |
| 59 | [`native-app-consumer`](#native-app-consumer) | Handles all consumer-side Native App tasks — installing from listings, configuring privileges and specs, managing maintenance policies, diagnosing agent/MCP issues, tracking cost, and uninstalling — by routing to 7 sub-skills. |
| 60 | [`manage-zerocopy-sapbdc`](#manage-zerocopy-sapbdc) | Manages the end-to-end lifecycle of the SAP BDC ↔ Snowflake zero-copy integration: creating connectors, consuming SAP data products as catalog-linked databases, publishing Snowflake data back to SAP, analyzing mounted data, and troubleshooting connector states. |

### Application Development & Platform Surfaces (11)

| # | Skill | What it does |
|---|-------|--------------|
| 61 | [`snowflake-apps`](#snowflake-apps) | Scaffolds, builds, deploys, and operates SAR apps (Snowflake App Runtime apps) — web applications backed by an `APPLICATION SERVICE` object, distinct from Streamlit-in-Snowflake and Native Apps. |
| 62 | [`sar-actions-desktop`](#sar-actions-desktop) | Defines how to carry out each SAR-app lifecycle action (scaffold, generate manifest, run locally, deploy, operate) specifically on CoCo Desktop, where a full shell, `snow` CLI, and `npm` are available. |
| 63 | [`developing-with-streamlit-in-snowflake`](#developing-with-streamlit-in-snowflake) | Entry point for all Streamlit work touching Snowflake — routes to a Snowflake-wired scaffolding/deploy/operate sub-skill or, for pure Streamlit authoring with no Snowflake angle, to version-matched OSS Streamlit guidance. |
| 64 | [`deploy-to-spcs`](#deploy-to-spcs) | Deploys any Docker-containerized application (Next.js, Python, Go, etc.) onto Snowpark Container Services, from image build through service creation and consumer role access. |
| 65 | [`snowflake-notebooks`](#snowflake-notebooks) | Creates and edits Snowflake Workspace notebooks (`.ipynb` files) that combine SQL cells and Python for step-by-step, interactive data analysis. |
| 66 | [`snowflake-workspace`](#snowflake-workspace) | Router for all Snowflake Workspace operations — file movement (`cortex ws`), lifecycle DDL, RBAC, publishing, and the hard rules around git-backed workspaces. |
| 67 | [`html-authoring`](#html-authoring) | Required for any `.html` file creation or edit — authors reports to the strict, sandboxed, no-network Content-Security-Policy environment Snowflake uses to render shared reports. |
| 68 | [`snowflake-publish-report`](#snowflake-publish-report) | Publishes a local (or workspace) HTML report as a shareable Snowflake Intelligence (Cowork) report artifact, with lineage back to an editable workspace copy. |
| 69 | [`sql-author`](#sql-author) | Writes, fixes, runs, and debugs Snowflake SQL by grounding every change in the real schema and compile-validating the final statement before presenting it. |
| 70 | [`iceberg`](#iceberg) | Router for every Snowflake Iceberg workflow — table creation, catalog integrations, catalog-linked databases, external volumes, auto-refresh, Horizon IRC, and converting externally managed tables to Snowflake-managed. |
| 71 | [`snowflake-postgres`](#snowflake-postgres) | Router for everything Snowflake Postgres and general PostgreSQL work — instance management, connections, diagnostics, `pg_lake`/Iceberg, managed mirroring, and full migration to Snowflake Postgres from any source. |

### Migration & Cortex Code Itself (7)

| # | Skill | What it does |
|---|-------|--------------|
| 72 | [`migration-guide`](#migration-guide) | Thin installer stub that confirms user approval, then installs the Snowflake AIM for Data Warehouses managed plugin via `cortex plugin install` and hands off to the full `snowflake-migration:migration` skill for the actual migration workflow. |
| 73 | [`spark-migration`](#spark-migration) | Router skill that converts Spark and PySpark workloads to Snowflake via two bundled paths — Snowpark Connect (SCOS, default, preserves the PySpark API surface) and Snowpark API (SMA CLI, explicit opt-in) — and also orchestrates deployment to Snowflake Notebooks, Code Bundles, or dbt projects. |
| 74 | [`skill-development`](#skill-development) | Router skill for creating, auditing, refactoring, compiling, and session-capturing Cortex Code skills, dispatching to five bundled sub-skills based on detected intent. |
| 75 | [`find-skill-and-plugin`](#find-skill-and-plugin) | Discovers and installs Cortex Code catalog skills and plugins from the Snowflake skill catalog, routing by user intent (skill vs. plugin vs. share-URI vs. bare FQN) and always stopping for user confirmation before installing. |
| 76 | [`share-skill-and-plugin`](#share-skill-and-plugin) | Publishes or revokes local Cortex Code skills and plugins to the same-account Snowflake skill catalog via Cortex Extension DDL, handling first-time share, re-share (content and/or audience), and unshare flows with SQL and CLI paths. |
| 77 | [`cortex-code-guide`](#cortex-code-guide) | Comprehensive reference guide for Cortex Code (CoCo) itself — covers every tool, slash command, keyboard shortcut, configuration option, skill/agent system, MCP setup, hook events, and special input syntax, serving as the canonical "how do I use CoCo" lookup. |
| 78 | [`team-workflow`](#team-workflow) | Multi-phase team orchestration skill that coordinates parallel agents through five phases (Research, Revise, Implement, Verify, Ship) with hard phase gates, a 45-agent budget, and claim-loop worker scheduling for feature implementation tasks. |

### Plugin: data — Airflow & Astronomer (18)

| # | Skill | What it does |
|---|-------|--------------|
| 79 | [`data:airflow`](#dataairflow) | Router and operations hub for Apache Airflow — lists, triggers, debugs, and manages DAGs, runs, and tasks via the `af` CLI, and dispatches to sibling skills for authoring, testing, deploying, and migrating. |
| 80 | [`data:airflow-hitl`](#dataairflow-hitl) | Builds human-in-the-loop Airflow workflows — approval gates, option selection, form collection, and human-driven branching — using the HITL operator family introduced in Airflow 3.1. |
| 81 | [`data:analyzing-data`](#dataanalyzing-data) | Answers business questions by running SQL against the data warehouse through a persistent kernel, with a concept/pattern cache that avoids re-discovering table mappings on repeat queries. |
| 82 | [`data:annotating-task-lineage`](#dataannotating-task-lineage) | Adds table-level data lineage to Airflow tasks using `inlets` and `outlets` for operators that have no built-in OpenLineage extraction. |
| 83 | [`data:authoring-dags`](#dataauthoring-dags) | Guides writing new Airflow DAGs or extending existing ones through a structured discover → plan → implement → validate → test workflow with `af` CLI feedback at each step. |
| 84 | [`data:checking-freshness`](#datachecking-freshness) | Quickly determines whether one or more warehouse tables are up to date by querying the most recent timestamp and optionally tracing a stale table to its source Airflow DAG. |
| 85 | [`data:cosmos-dbt-core`](#datacosmos-dbt-core) | Turns a dbt Core project into an Airflow `DbtDag` or `DbtTaskGroup` using Astronomer Cosmos, with step-by-step configuration for project, rendering, execution mode, warehouse connection, and testing behavior. |
| 86 | [`data:cosmos-dbt-fusion`](#datacosmos-dbt-fusion) | Runs a dbt Fusion project with Astronomer Cosmos (Cosmos ≥ 1.11), handling Fusion-specific constraints: binary installation, `ExecutionMode.LOCAL`-only, and limited warehouse support. |
| 87 | [`data:creating-openlineage-extractors`](#datacreating-openlineage-extractors) | Creates custom OpenLineage extractors or adds `get_openlineage_facets_on_*` methods to operators, enabling lineage capture — including column-level lineage — for operators without built-in extraction. |
| 88 | [`data:debugging-dags`](#datadebugging-dags) | Performs structured root-cause analysis of Airflow DAG failures — including import errors, task exceptions, infrastructure issues, and silent dependency drift — and produces a remediation plan with ready-to-run commands. |
| 89 | [`data:managing-astro-local-env`](#datamanaging-astro-local-env) | Manages the local Airflow environment using the Astro CLI in Docker mode or Docker-free Standalone mode, covering start/stop/restart, log viewing, API queries, troubleshooting, and version upgrades. |
| 90 | [`data:migrating-airflow-2-to-3`](#datamigrating-airflow-2-to-3) | Guides migration of Airflow 2.x DAG code to Airflow 3.x, covering automated Ruff-based fixes, manual search patterns for metadata DB access, import changes, scheduling semantics, XCom, Assets, and config renames. |
| 91 | [`data:profiling-tables`](#dataprofiling-tables) | Generates a comprehensive profile of a warehouse table — schema metadata, row counts, column statistics, cardinality, data quality scores, and sample data — structured for a new team member to understand the dataset. |
| 92 | [`data:setting-up-astro-project`](#datasetting-up-astro-project) | Initializes a new Astro/Airflow project with `astro dev init`, configures Python and OS dependencies, sets up connections and variables via `airflow_settings.yaml`, and validates the project structure before first run. |
| 93 | [`data:testing-dags`](#datatesting-dags) | Runs iterative test → debug → fix cycles for Airflow DAGs, starting immediately with `af runs trigger-wait` and only invoking diagnosis commands when a run actually fails. |
| 94 | [`data:tracing-downstream-lineage`](#datatracing-downstream-lineage) | Traces what depends on a given table or DAG — building a dependency tree, categorizing downstream assets by criticality, and producing an impact report with risk assessment before a schema or data change. |
| 95 | [`data:tracing-upstream-lineage`](#datatracing-upstream-lineage) | Traces the origin of a table or column by identifying the producing DAG, its source tables and external systems, and the transformation chain, then checks source health. |
| 96 | [`data:warehouse-init`](#datawarehouse-init) | Generates `.astro/warehouse.md` — a version-controllable warehouse schema reference enriched with codebase context (dbt models, gusty SQL, AGENTS.md) — and pre-populates the concept/pattern cache used by `data:analyzing-data`. |

### Plugins: blueprints & databricks (15)

| # | Skill | What it does |
|---|-------|--------------|
| 97 | [`blueprints:blueprint-builder`](#blueprintsblueprint-builder) | Conversational front-end to Snowflake Blueprint Manager: captures an organization's context, generates a YAML answer file for a chosen blueprint, and renders deployable SQL plus a documentation/PDF deliverable via `render_journey.py`. |
| 98 | [`blueprints:pipeline-plan-generator`](#blueprintspipeline-plan-generator) | Downstream hand-off skill for the Pipeline Planner blueprint: takes a completed answers file, silently profiles the source data in Snowflake, generates a transformation DAG and test plan, and writes an executable implementation plan plus a rendered SQL artifact. |
| 99 | [`blueprints:snowflake-best-practices`](#blueprintssnowflake-best-practices) | Answers "how should I…" Snowflake architecture and configuration questions from the plugin's SME-curated blueprint content first, falling back to official product documentation only for topics the local content does not cover. |
| 100 | [`databricks:databricks-setup`](#databricksdatabricks-setup) | Installs and manages the Databricks AI Dev Kit skill collection (up to 34 skills) inside Cortex Code by running the upstream installer with `--tools claude`, and manages skill/profile selection afterwards. |
| 101 | [`databricks:databricks-cli-install`](#databricksdatabricks-cli-install) | Installs or updates the Databricks CLI binary (v0.205+) across macOS, Linux, WSL, and Windows, then configures and verifies an authentication profile. |
| 102 | [`databricks:databricks-cli`](#databricksdatabricks-cli) | General-purpose driver for day-to-day Databricks workspace operations across every major CLI command group, with a REST API escape hatch for anything the CLI does not cover. |
| 103 | [`databricks:databricks-unity-catalog`](#databricksdatabricks-unity-catalog) | Navigates and manages the Unity Catalog three-level namespace (`catalog.schema.object`) through the Databricks CLI, including grants, volumes, and governed sample-data queries. |
| 104 | [`databricks:databricks-dbsql`](#databricksdatabricks-dbsql) | Router-plus-authoring skill for advanced Databricks SQL features — procedural SQL, materialized views, AI functions, geospatial, collations, pipe syntax, and Lakehouse data modeling — loading one of five topic references based on detected intent. |
| 105 | [`databricks:databricks-automation-bundles`](#databricksdatabricks-automation-bundles) | Manages the full lifecycle of Databricks Declarative Automation Bundles (DAB, formerly Asset Bundles) — infrastructure-as-code projects that define jobs, pipelines, apps, and ML assets in `databricks.yml`. |
| 106 | [`databricks:databricks-etl-pyspark-notebooks`](#databricksdatabricks-etl-pyspark-notebooks) | Builds medallion-architecture ETL pipelines as PySpark `.ipynb` notebooks on Databricks and deploys them as scheduled jobs via Declarative Automation Bundles. |
| 107 | [`databricks:databricks-dbt-pipeline`](#databricksdatabricks-dbt-pipeline) | Builds end-to-end dbt-core pipelines on Databricks — scaffolding, `profiles.yml` connection setup, model authoring, tests, and production deployment as a dbt task inside a Lakeflow Job via DAB. |
| 108 | [`databricks:databricks-notebook-refactor`](#databricksdatabricks-notebook-refactor) | Guided refactoring of monolithic Databricks notebooks into modular Python packages — extracting testable `.py` modules, replacing `%run` chains with imports, parameterizing hardcoded values, and leaving a thin orchestrator notebook. |
| 109 | [`databricks:databricks-local-testing`](#databricksdatabricks-local-testing) | Generates pytest suites that run Databricks PySpark code locally with no cluster — mocking `dbutils`, providing a local `SparkSession` fixture, stubbing `display()`, and asserting on DataFrames. |
| 110 | [`databricks:databricks-spark-performance`](#databricksdatabricks-spark-performance) | Metrics-driven diagnosis and remediation of slow Spark jobs on Databricks — triage the slow stage, read the metrics, classify the bottleneck, apply targeted fixes, validate, estimate the cost impact, and harden. |
| 111 | [`databricks:databricks-cost-optimization`](#databricksdatabricks-cost-optimization) | Router skill for Databricks cost work: detects which cost domain the user cares about and loads one of five sub-skills covering monitoring/governance, cluster compute, SQL warehouses, streaming/workload design, and ML/GPU compute. |


---

## AI, Cortex & Machine Learning

*Turning unstructured data, documents and natural-language questions into governed Snowflake assets.*

### `agent-studio`

> Router skill for building, editing, auditing, and optimizing Semantic Views and Cortex Agents in Snowflake, including importing BI tool models and managing Verified Query Representations.

**Snowflake surface it drives:** `CREATE SEMANTIC VIEW`, `ALTER SEMANTIC VIEW`, `VALIDATE SEMANTIC VIEW`, `SHOW SEMANTIC VIEWS`, `CREATE AGENT`, `ALTER AGENT`, `SHOW AGENTS`, Cortex Analyst YAML, Verified Query Representations (VQRs), Cortex Agent REST API, Tableau `.twb`/`.twbx`/`.tds`/`.tdsx` import, Power BI `.pbit`/`.pbix` import, OSI (Open Semantic Interchange) YAML import, `SNOWFLAKE.CORTEX.ANALYST`

**What it accelerates**
- Creating a Semantic View from scratch — removes manual YAML authoring, schema discovery, and relationship inference by generating a deployable model from a plain-language description.
- Importing an existing Tableau or Power BI workbook — eliminates the translation step from BI semantic model to Snowflake Semantic View DDL.
- Auditing a Semantic View for quality — replaces a manual review with a scored report against best-practice rules (duplicates, inconsistencies, missing relationships).
- Building and optimizing a Cortex Agent — removes the trial-and-error loop for orchestration/response prompts, tool configuration, and eval-dataset curation.
- Suggesting and managing VQRs — automates mining, bulk validation, and lifecycle management of verified queries that anchor Analyst SQL accuracy.

**Representative use cases**
- "Build me a semantic view over our sales and orders tables so Cortex Analyst can answer revenue questions."
- "Import our Tableau workbook and convert it to a Snowflake Semantic View."
- "Audit the finance semantic view and tell me what's missing or inconsistent."
- "Create a Cortex Agent for our support team that answers questions about ticket data."
- "My agent keeps giving wrong totals — optimize its prompts and run an evaluation."
- "Suggest verified queries for the HR semantic view and add the good ones."
- "Import this Power BI .pbit file and generate a semantic view from it."

**Example prompts**
```
Create a semantic view over our customers and orders tables
Import my Tableau workbook and build a semantic view
Audit the sales semantic view for missing relationships
Build a Cortex Agent connected to the finance semantic view
Suggest VQRs for the HR analyst model and add the best ones
```

**Depth behind it:** 84 supporting files, 3 sub-skills (`semantic-view`, `agent`, `debug`). Each sub-skill is itself deeply nested: `semantic-view` contains 15 further sub-skills (creation, edit, upload, download, validate, audit, agentic_optimization, import_tableau, import_powerbi, import_osi, patterns, suggest_relationships, filters_and_metrics_suggestions, vqr_management, vqr_suggestions) and `agent` contains 13 (creation, edit, test, download, upload, optimize, eval, dataset, audit, monitor, permission, connect_cowork).

**Prerequisites & caveats:** Requires an active Snowflake connection with privileges to create/alter semantic views and agents in the target schema. Tableau and Power BI import require the workbook file to be available locally. Agent evaluation and optimization require a labeled eval dataset. The `debug` sub-skill requires Cortex Analyst observability logs to be available for the request being diagnosed.

**Pairs with:** `cortex-sense`, `ai-data-share`, `ai-readiness-score`, `data-governance`

---

### `cortex-ai-function-studio`

> Required entry point for all Snowflake built-in and custom AI function operations — running `AI_*` SQL, creating domain-specific custom functions, evaluating their accuracy, and optimizing prompts and model selection for cost/quality tradeoff.

**Snowflake surface it drives:** `AI_COMPLETE`, `AI_CLASSIFY`, `AI_EXTRACT`, `AI_FILTER`, `AI_SENTIMENT`, `AI_TRANSLATE`, `AI_EMBED`, `AI_SUMMARIZE_AGG`, `AI_AGG`, `AI_REDACT`, `AI_TRANSCRIBE`, `AI_SIMILARITY`, `AI_PARSE_DOCUMENT`, `AI_COUNT_TOKENS`, `SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION` (stored procedure, 9 positional params), `SNOWFLAKE.CORTEX.EVALUATE_AI_FUNCTION` (12 params), `SNOWFLAKE.CORTEX.OPTIMIZE_AI_FUNCTION` (18 params), `SHOW RUN METRICS IN EXPERIMENT`, SPCS model services (BYOM), Snowflake Experiment APIs

**What it accelerates**
- Running a built-in AI function — removes syntax lookup and namespace confusion (`AI_*` not `SNOWFLAKE.CORTEX.*`) and surfaces access checks before SQL is written.
- Creating a custom AI function — replaces manual prompt engineering and UDF authoring with a guided workflow (Direct or Agent Research modes) backed by stored-procedure deployment.
- Evaluating function accuracy — provides a structured evaluate loop with pre-built and custom metrics against labeled data (20–50 rows is enough to start).
- Optimizing prompts and model selection — automates prompt rewrites and parallel model comparison to find the Pareto-optimal cost/quality point without manual iteration.
- Onboarding a BYOM model — guides GPU compute pool selection, Hugging Face model import to Model Registry, SPCS service creation, and exposure via `AI_COMPLETE('<service>', ...)`.

**Representative use cases**
- "Classify these support tickets into categories using AI."
- "Build a custom AI function that extracts risk flags from our legal contracts."
- "Evaluate my claim-routing function against a labeled dataset and show accuracy."
- "Optimize my extraction function — try multiple models and show me cost vs quality."
- "I need to run AI_REDACT on a column of patient notes to remove PII."
- "Set up a Hugging Face model on SPCS and call it as an AI function."

**Example prompts**
```
Use AI_CLASSIFY to categorize my support tickets
Build a custom AI function to extract payment terms from contracts
Evaluate my invoice extraction function against these 30 labeled rows
Optimize my sentiment function for better accuracy at lower cost
Run AI_REDACT on this column to remove PII
```

**Depth behind it:** ~150 supporting files (includes Python packages `snowflake-ai-optimize-core`, `snowflake-ai-optimize-gepa`, `snowflake-ai-optimize-synthetic`, Jinja2 stored-procedure templates, and a full test suite), 14 sub-skills (`built-in-ai-functions`, `create`, `evaluate`, `optimize`, `byom`, `byom/pricing`, `demos`, `demos/classification`, `demos/insurance-claim-routing`, `demos/legal-doc-extraction`, `demos/pdf-field-extraction`, `demos/policy-conditioned-routing`, `demos/redaction`, `synthetic-data`).

**Prerequisites & caveats:** Requires `CORTEX USER` privilege on the Snowflake role for built-in functions. Custom function create/evaluate/optimize requires a target database/schema and the stored-procedure namespace `SNOWFLAKE.CORTEX.*`. Evaluate and Optimize apply only to custom AI functions today — not to built-in `AI_*` functions. BYOM is a research preview requiring GPU compute pools and SPCS access. Personal databases (`USER$<name>`) are not supported for function objects.

**Pairs with:** `document-intelligence`, `ai-functions-pipeline-builder`, `snowpark-python`, `machine-learning`

---

### `ai-functions-pipeline-builder`

> Builds Snowflake-native incremental document and file processing pipelines — turning a plain-language request into a stream → task → dynamic-table architecture using Cortex AI functions, either from a proven use-case template or a custom block composition.

**Snowflake surface it drives:** `AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_CLASSIFY`, `AI_COMPLETE` (vision), `CREATE STREAM ON STAGE`, `CREATE DYNAMIC TABLE ... REFRESH_MODE = INCREMENTAL`, `CREATE TASK`, `CREATE CORTEX SEARCH SERVICE`, `TO_FILE()` stage file wrapper, directory tables (`DIRECTORY(stage)`)

**What it accelerates**
- Standing up an end-to-end document pipeline — removes the architectural design work for the stream → task → incremental dynamic table pattern that keeps outputs fresh as new files land.
- Selecting and customising a use-case template — eliminates blank-canvas paralysis by offering five eval-backed templates (structured extraction, corpus intelligence, enterprise search, customer 360, invoice processing) as starting points.
- Composing multi-stage AI logic — provides a library of reusable blocks (ingest, parse, extract, classify, vision, entity assembly, triage, search, rollup) that snap together without re-inventing each stage.
- Keeping outputs incrementally fresh — enforces the three-law incremental architecture so pipelines never silently stop after the initial backlog.
- Routing one-off file tasks — handles single-file or one-time-batch extract/parse/classify/analyze without building a pipeline, then hands off to the pipeline if scope grows.

**Representative use cases**
- "Our invoice PDFs land in S3 and we need the line items in a table, refreshed as new files arrive."
- "Build a searchable knowledge base over our contract library that gives cited answers."
- "Classify all incoming documents by type, extract the right fields for each type, and route to action lanes."
- "Run themes-and-trends analysis across 10,000 research reports in our stage."
- "Unify our CRM tables with staged customer call transcripts into a customer 360 record."
- "Extract vendor name, amount, and due date from all the invoices in this stage once — no ongoing pipeline."
- "Build an enterprise search layer over our regulatory filings with RAG-style Q&A."

**Example prompts**
```
Build an incremental invoice processing pipeline from my stage
Create an enterprise search layer over our contracts stage
Build a corpus intelligence pipeline to find themes across our research reports
Extract structured fields from all PDFs in this stage and keep the table fresh
Set up a customer 360 pipeline combining our CRM tables with staged call transcripts
```

**Depth behind it:** ~72 supporting files (blocks library with 16 block markdown files, 5 use-case template directories each with examples, 9 reference files, 4 demo sets with SQL and notebooks, 4 demo Python scripts), 10 sub-skills (`templates/structured-extraction`, `templates/corpus-intelligence`, `templates/enterprise-search`, `templates/customer360`, `templates/invoice-processing`, `demos`, `demos/corpus-intelligence`, `demos/customer360`, `demos/enterprise-search`, `demos/structured-extraction`).

**Prerequisites & caveats:** Requires stage with `DIRECTORY = (ENABLE = TRUE)` for stream-based pipelines. Dynamic table `REFRESH_MODE = INCREMENTAL` requires the DT query to satisfy Snowflake incrementality rules. AI function costs apply per token/page — skill warns before execution. For cloud storage sources (S3/Azure/GCS), an external stage or Openflow connector is required. One-off tasks route to this skill if pipeline intent is detected; the `document-intelligence` skill handles cases where no ongoing pipeline is needed.

**Pairs with:** `document-intelligence`, `cortex-ai-function-studio`, `dynamic-tables`, `snowflake-tasks`, `openflow`

---

### `document-intelligence`

> Applies Snowflake Cortex AI functions (`AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_CLASSIFY`, `AI_COMPLETE`) to a single file or one-time batch on a stage, and fine-tunes the `arctic-extract` model for domain-specific extraction accuracy.

**Snowflake surface it drives:** `AI_EXTRACT`, `AI_PARSE_DOCUMENT`, `AI_CLASSIFY`, `AI_COMPLETE` (vision models), `TO_FILE('@stage', 'file.pdf')` wrapper, `FINETUNE` (arctic-extract fine-tuning), Snowflake stage (`@stage`)

**What it accelerates**
- Extracting structured fields from PDFs or forms — removes syntax lookup for `AI_EXTRACT`, the `TO_FILE()` wrapper requirement, and schema design for the JSON output.
- OCR/parsing full document text — provides the correct `AI_PARSE_DOCUMENT` pattern with format-envelope rules (direct for images, parse-first for PDFs and Office formats).
- Classifying documents by type — delivers a working `AI_CLASSIFY` query with the right format envelope per file type (images classified directly; PDFs parsed first).
- Analyzing charts, blueprints, and engineering drawings — routes to `AI_COMPLETE` with a vision model when content interpretation (not field extraction) is needed.
- Fine-tuning arctic-extract — guides the full fine-tuning workflow when built-in extraction accuracy is insufficient for a domain.

**Representative use cases**
- "Extract invoice number, vendor, line items, and total from all PDFs in this stage."
- "Get the full text out of these scanned contract PDFs so I can search them."
- "Classify these 500 documents into invoice, contract, and receipt categories."
- "What dimensions does this engineering drawing show? Analyze the blueprint."
- "Fine-tune arctic-extract on our labeled insurance claim forms to improve extraction."

**Example prompts**
```
Extract the invoice number, date, and total from all PDFs in my stage
Parse the full text from these scanned documents
Classify the files in this stage as invoice, contract, or other
Analyze this engineering blueprint and tell me the dimensions shown
Fine-tune arctic-extract on my labeled form data to improve accuracy
```

**Depth behind it:** 11 supporting files (4 function reference files: `ai-extract.md`, `ai-parse-doc.md`, `ai-classify.md`, `ai-complete.md`; plus `fine-tuning/` with README, 4 references, and SKILL.md), 1 sub-skill (`fine-tuning`).

**Prerequisites & caveats:** Requires `CORTEX USER` privilege. Files must be on a Snowflake stage; local files require a stage path from the user before any SQL is generated. `AI_PARSE_DOCUMENT` requires the `TO_FILE()` wrapper — raw string paths are not valid. TIFF and BMP images must be converted to PNG or PDF before classification. Fine-tuning arctic-extract requires labeled training data. Not for ongoing pipelines or multi-function flows — use `ai-functions-pipeline-builder` for those. Not for AI functions over tabular text columns without files — use `cortex-ai-function-studio` for those.

**Pairs with:** `ai-functions-pipeline-builder`, `cortex-ai-function-studio`

---

### `cortex-sense`

> Builder experience for creating, testing, refining, and deploying Cortex Sense domain contexts — scoped business-data understanding layers that ground Cortex Code and CoWork agents in a customer's specific tables, metrics, and terminology.

**Snowflake surface it drives:** `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER` (list-contexts, put-stage-file, record-feedback, delete-context), Cortex Sense context manifests (YAML persisted to Snowflake stage), `CREATE AGENT` (for agent hand-off), `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` (usage-based table discovery), Business Ontology API (ontology-aware discovery), Cortex Sense `cortex_sense` MCP tool

**What it accelerates**
- Defining a data domain context — removes the manual work of identifying hot tables, dashboards, Streamlit apps, and semantic views relevant to a use case by running parallel account discovery automatically.
- Scoping context in plain English — eliminates the need to know internal manifest YAML structure; the builder writes natural language corrections and CoCo classifies them into concepts/relationships/instructions.
- Testing a built context against real questions — provides an ad-hoc spot-check loop without requiring a full eval suite.
- Generating and running correctness evals — automates question-answer dataset curation, LLM-judge grading, and lift measurement vs. a no-context baseline.
- Deploying a context as a CoWork agent or CoCo skill — handles agent DDL generation, tool provisioning, and smoke-testing in one flow.

**Representative use cases**
- "Set up Cortex Sense for our finance use case so our analyst agent understands revenue metrics."
- "Test the sales context — does it know about our churn definition?"
- "The agent keeps picking the wrong table for DAU — refine the context to fix it."
- "Generate an eval set for the HR context and score how accurate the answers are."
- "Deploy the supply-chain context as a CoWork agent for our operations team."
- "List all the Cortex Sense domains that are set up in this account."
- "Create a CoCo skill from the finance context so developers can use it in CLI sessions."

**Example prompts**
```
Set up Cortex Sense for our sales analytics use case
Test the finance context — does it know about gross margin?
The agent picked the wrong orders table — refine the context
Generate an eval set for the HR context and run it
Deploy the supply-chain context as a CoWork agent
```

**Depth behind it:** 39 supporting files (21 reference files covering vocabulary, discovery contracts, manifest schema, eval formats, grading, feedback records, agent spec, and not-yet-implemented placeholders; 4 Python scripts for discovery, ontology, feedback, and state persistence; `pyproject.toml`, `uv.lock`, `README.md`), 8 sub-skills (`setup`, `test`, `query`, `refine`, `eval`, `feedback`, `agent`, `skill`). The `eval` sub-skill has 3 further nested sub-skills (`generate`, `run`, `diff`).

**Prerequisites & caveats:** Requires a Snowflake stage for manifest persistence and `SNOWFLAKE.ACCOUNT_USAGE` access for table discovery. Build execution is asynchronous — this skill sets up the manifest; the offline build process runs separately. The `check build` status inference is best-effort (no true state field yet). The feedback path is a work in progress: corrections are durable and served at query time, but listing or editing them is not yet supported. `delete-context` is irreversible and gated behind an explicit domain-name confirmation. Content search of BI objects and external tables is not yet implemented.

**Pairs with:** `agent-studio`, `business-ontology`, `ai-readiness-score`

---

### `ai-readiness-score`

> Measures a Snowflake account's AI readiness by scoring Consumption-Ready tables, Semantic View coverage and quality, and query demand coverage, then generates an HTML scorecard report with prioritized recommendations.

**Snowflake surface it drives:** `SNOWFLAKE.ACCOUNT_USAGE.TABLES`, `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY`, `SHOW SEMANTIC VIEWS`, Consumption-Ready table tagging (`SNOWFLAKE.CORE.CERTIFICATION_STATUS`), Snowsight Notebooks (`.ipynb`), HTML report generation, `scripts/cr_tables.sql`, `scripts/sv_quality.sql`

**What it accelerates**
- Baselining AI readiness without manual auditing — runs three scored dimensions (CR tables, SV coverage, demand coverage) in one invocation and caches results for fast reruns.
- Identifying which tables most need Semantic View coverage — surfaces the highest-demand tables without a coverage layer so SE and customer know exactly where to focus.
- Generating a shareable scorecard — produces a self-contained HTML report with scores and recommendations suitable for an executive review or pre-sales proof of concept.
- Adapting to environment — auto-detects Snowsight vs CLI and runs the appropriate path (notebook or direct SQL) without requiring the user to specify.

**Representative use cases**
- "Score our Snowflake account for AI readiness and show me what's missing."
- "How many of our high-query tables have a Semantic View on top of them?"
- "Generate an AI readiness report I can share with the customer before their Cortex Analyst demo."
- "Rerun the readiness score after we added the new semantic views last week."

**Example prompts**
```
How AI-ready is our Snowflake account?
Score my account and show Semantic View coverage
Generate an AI readiness report for this account
Measure demand coverage for our top tables
Rerun the AI readiness score
```

**Depth behind it:** 12 supporting files (`scripts/build_notebook.py`, `scripts/notebook_cells.py`, `scripts/cr_tables.sql`, `scripts/sv_quality.sql`, `scripts/recommendations.py`, `scripts/report.py`, `scripts/run_analysis.py`, `scripts/scoring.py`, `skill-cli.md`, `skill-snowsight.md`, `README.md`), no sub-skills (two execution-mode instruction files: `skill-cli.md` and `skill-snowsight.md`).

**Prerequisites & caveats:** Requires `SNOWFLAKE.ACCOUNT_USAGE` access. Snowsight mode requires a Workspace to create and run the analysis notebook — the skill navigates the user to a Workspace if not already there. CLI mode runs SQL directly and generates the HTML report locally. Results are cached between runs; pass a rerun intent to force a fresh analysis.

**Pairs with:** `agent-studio`, `cortex-sense`, `certify-object`

---

### `machine-learning`

> Router skill for all Snowflake data science and ML tasks — covers the full lifecycle from training and preprocessing through model registry, SPCS inference, batch inference, distributed training, feature store, experiment tracking, pipeline orchestration, monitoring, and lineage, dispatching to 17 specialized sub-skills.

**Snowflake surface it drives:** Snowpark ML (`snowflake.ml`), `CREATE MODEL` / `SHOW MODELS` (Model Registry), `CREATE SERVICE` (SPCS inference), `CREATE COMPUTE POOL`, `CREATE GATEWAY`, `CREATE MODEL MONITOR`, Feature Store (`CREATE FEATURE VIEW`, `CREATE ENTITY`, `generate_training_set`), Snowflake Experiment APIs, ML Jobs (`snowflake.ml.jobs`, `submit_file()`, `submit_directory()`), Snowflake DAG API (`ml-pipeline-orchestration`), `SHOW DATASETS`, `DataConnector`, `GET_LINEAGE` (ML lineage), `INFERENCE_TABLE()`, AutoGluon, XGBEstimator, LightGBMEstimator, PyTorchDistributor, Ray Tune (Tuner API)

**What it accelerates**
- Training and evaluating a model — routes immediately to `ml-development` without upfront deployment questions; training and registration are handled as separate sequential tasks.
- Registering and deploying a serialized model — carries training context (file path, framework, sample schema) automatically into the `model-registry` sub-skill to avoid re-asking.
- Standing up batch or real-time inference — disambiguates native SQL batch (`mv.run()`), job-based batch (`mv.run_batch()`), and SPCS REST endpoint before routing, preventing the common wrong-path mistake.
- Setting up distributed training or many-model-training — covers XGBoost/LightGBM estimators, PyTorchDistributor, DPF, and the Tuner API for HPO under one sub-skill.
- Monitoring model drift and A/B testing — distinguishes gateway model monitors (multi-service comparison) from model version monitors (single-version drift) and routes to the correct DDL.

**Representative use cases**
- "Train a churn classifier on our customer table and register it to Snowflake."
- "Run batch inference on my registered model against the new transactions loaded today."
- "Deploy my model as a real-time REST endpoint on SPCS."
- "Set up distributed XGBoost training across a GPU compute pool."
- "Create a feature store entity and feature views for our fraud detection model."
- "Schedule weekly retraining and inference as a Snowflake task DAG."
- "What data fed into this model? Show me the ML lineage."
- "Monitor my production model for drift and alert me when accuracy drops."

**Example prompts**
```
Train a binary classifier on this customer churn dataset
Register my sklearn model.pkl to the Snowflake Model Registry
Deploy my model as a real-time inference service on SPCS
Set up a feature store with point-in-time correct training datasets
Schedule automated retraining and batch inference as a pipeline DAG
```

**Depth behind it:** 61 supporting files (40 sub-skill `SKILL.md` files plus reference files, Tecton migration examples, compute pool sizing guides, and a shared `snowpark_session.py` script), 17 direct sub-skills (`automl`, `ml-development`, `model-registry`, `experiment-tracking`, `spcs-inference`, `batch-inference-jobs`, `ml-jobs`, `ml-pipeline-orchestration`, `model-monitor`, `distributed-training`, `feature-store`, `inference-logs`, `gateway-ab-testing`, `datasets`, `ml-lineage`, `preprocessing`, `debug-inference`). Several sub-skills contain further nested sub-skills (e.g., `feature-store` has 9, `distributed-training` has 4, `batch-inference-jobs` has 3, `model-registry` has 2).

**Prerequisites & caveats:** Personal databases (`USER$<name>`) are not supported for model registry, tables, or inference services. Distributed training and SPCS inference require compute pools — GPU pools for deep learning. The skill always asks for database/schema before creating objects and never picks one silently. Inference disambiguation (batch vs online) requires a clarifying question when signals are ambiguous. AutoML uses AutoGluon and runs inside ML Jobs or Container Runtime notebooks.

**Pairs with:** `snowpark-python`, `dynamic-tables`, `snowflake-tasks`, `deploy-to-spcs`, `cortex-ai-function-studio`

---

### `ai-data-share`

> Creates a complete AI-ready data product from a Snowflake listing or share — resolves the source, generates a Semantic View, creates and configures a Cortex Agent, and grants all objects to the share.

**Snowflake surface it drives:** `SHOW LISTINGS`, `SHOW SHARES`, `SHOW SHARED DATABASES`, `GRANT SELECT ON TABLE ... TO SHARE`, `GRANT USAGE ON SCHEMA ... TO SHARE`, `GRANT USAGE ON DATABASE ... TO SHARE`, `GRANT SELECT, REFERENCES ON SEMANTIC VIEW ... TO SHARE`, `GRANT USAGE ON AGENT ... TO SHARE`, `SHOW AGENTS IN DATABASE`, Cortex Agent creation via REST API (`FROM SPECIFICATION $$...$$`), Semantic View `FastGen` upload (2-part name `DATABASE.SCHEMA`)

**What it accelerates**
- Making a data share AI-ready — removes the multi-step manual process of finding the share's objects, building a semantic model, creating an agent, and correctly ordering all grants.
- Resolving a listing to its underlying share — handles both listing-path (listing → share → objects) and share-path (direct share → optional listing metadata lookup) automatically.
- Generating semantic view and agent prompts — produces orchestration and response prompts and tool descriptions from schema and user-provided documentation rather than blank-slate authoring.
- Attaching AI objects to shares correctly — enforces the correct grant ordering (database → schema → object) and handles all dependency grants (underlying tables for SVs, tool dependencies for agents).

**Representative use cases**
- "Make this Snowflake Marketplace listing AI-ready with a Cortex Agent."
- "I have a data share — create a semantic view and agent so consumers can ask questions in natural language."
- "My listing already has tables — wire up an AI agent so my customers can query it with Cortex Analyst."
- "Attach a Cortex Agent and semantic view to my share and grant everything correctly."

**Example prompts**
```
Make my Marketplace listing AI-ready
Create a Cortex Agent for this data share
Build a semantic view and agent for my listing
Add an AI agent to my share so consumers can ask natural language questions
```

**Depth behind it:** 3 supporting files (`create_agent.md`, `create_semantic_view.md`, `resolve_source.md`), no sub-skills (the 3 files are sequential workflow phases loaded by the root skill).

**Prerequisites & caveats:** Requires `ACCOUNTADMIN` or `SHARE_ADMIN` role privileges to inspect and grant on shares. The listing must already exist in Snowflake (or the share must be directly accessible). `SHOW AGENTS IN DATABASE` is the correct syntax — `SHOW CORTEX AGENTS` does not exist. FastGen upload requires a 2-part name (`DATABASE.SCHEMA`), not a 3-part name. After skill completion, use the `attach-ai-products-to-share` skill to finalize grants if not already done. Python 3.13+ is incompatible with pyarrow during FastGen; the skill instructs `uv python install 3.11` automatically.

**Pairs with:** `agent-studio`, `attach-ai-products-to-share`, `data-sharing`, `marketplace-provider`

---

## Data Engineering & Pipelines

*Building, scheduling, monitoring and repairing ingestion and transformation pipelines.*

### `dynamic-tables`

> Required entry point for all Snowflake Dynamic Table work: creating pipelines, monitoring health, troubleshooting refresh failures, optimizing performance, and converting dbt or streams+tasks pipelines to dynamic tables.

**Snowflake surface it drives:** `CREATE DYNAMIC TABLE`, `CREATE OR ALTER DYNAMIC TABLE`, `ALTER DYNAMIC TABLE`, `INFORMATION_SCHEMA.DYNAMIC_TABLES()`, `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY()`, `SHOW DYNAMIC TABLES`, `TARGET_LAG`, `REFRESH_MODE`, `FROZEN WHERE`, `CHANGES()`, `REFRESH USING`, OTel pipeline traces

**What it accelerates**
- Creating a new dynamic table with the correct `TARGET_LAG` and `REFRESH_MODE`, removing syntax lookup and constraint research.
- Troubleshooting `UPSTREAM_FAILED`, suspended DTs, or full-refresh-instead-of-incremental failures without trial and error.
- Checking Snowflake-emitted recommendations before routing to general optimization, so targeted fixes are applied first.
- Converting existing streams+tasks or dbt `table` models to dynamic tables, including multi-stage migration workflows.
- Building custom-incrementalization (CI) DTs using `REFRESH USING` for stream-static joins, append-only logs, and conditional MERGE logic.
- Generating pipeline timeline/Gantt charts and tracing critical paths through OTel refresh traces.

**Representative use cases**
- "I want to build a bronze → silver → gold pipeline in Snowflake without writing orchestration code."
- "My dynamic table keeps doing a full refresh instead of incremental — I need to understand why."
- "I have a dbt project with `table` materializations; I want to migrate them to dynamic tables."
- "Set up email alerting when any dynamic table in my schema fails to refresh."
- "My streams+tasks pipeline is hard to maintain — can I replace it with dynamic tables?"
- "I need a dynamic table that only accumulates appended rows from a stream, ignoring deletes."
- "Show me a Gantt chart of my pipeline's last refresh and identify the bottleneck."
- "Add a frozen region to my DT so historical partitions stop changing."

**Example prompts**
```
Create a dynamic table with a 5 minute lag that joins orders and customers
My dynamic table is suspended with UPSTREAM_FAILED — how do I fix it?
Convert my dbt table models to dynamic tables
Set up email alerts when any DT in my schema fails to refresh
Show me the pipeline timeline for my sales pipeline last night
```

**Depth behind it:** 20+ supporting files (dbt-to-dt phase scripts and reference `.md` files; top-level `references/` directory with SQL syntax and monitoring function references), `11` sub-skills (`create`, `create-or-alter`, `monitor`, `troubleshoot`, `optimize`, `dt-alerting`, `permissions`, `task-to-dt`, `custom-incrementalization`, `dbt-to-dt`, `pipeline-diagnostics`); `dbt-to-dt` itself contains 3 nested sub-skills (`advisor`, `stage-1`, `stage-2`).

**Prerequisites & caveats:** Incremental DTs cannot depend on full-refresh DTs. Minimum `TARGET_LAG` is 1 minute; sub-minute latency requires streams+tasks instead. Change tracking must remain enabled on base tables after DT creation. External/directory table sources are not supported as DT sources. `FROZEN WHERE` does not allow subqueries or UDFs. Multi-statement procedural logic (IF/ELSE, loops) remains a blocker for DTs.

**Pairs with:** `dynamic-tables-apply-recommendations`, `snowflake-tasks`, `dbt-projects-on-snowflake`, `alert`, `event-table`

---

### `dynamic-tables-apply-recommendations`

> Reads Snowflake-emitted recommendations from the `RECOMMENDATIONS` column of a specific dynamic table and applies targeted DDL fixes — from refresh-mode changes to zero-downtime Iceberg V2-to-V3 swaps.

**Snowflake surface it drives:** `INFORMATION_SCHEMA.DYNAMIC_TABLES()` `RECOMMENDATIONS` column, `CREATE OR ALTER DYNAMIC TABLE`, `REFRESH_MODE = ADAPTIVE`, per-recommendation DDL recipes for `AUTO_RESOLVED_TO_FULL_REFRESH`, `QUALIFY_RANK_NOT_TOP_LEVEL`, `TOP_LEVEL_AGGREGATE_NOT_TOP_LEVEL`, `QUALIFY_RANK_KEYS_NOT_PERSISTED`, `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED`, `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`, `NON_MONOTONIC_GROUPING_KEY`, `HIGH_BASE_TABLE_CHANGES`, `CHANGED_BASE_TABLES_UNDER_JOIN`, `WAREHOUSE_TOO_SMALL`, `ICEBERG_BASE_TABLE_V2_TO_V3`

**What it accelerates**
- Reading and interpreting 11 distinct Snowflake recommendation codes without needing to understand each one independently.
- Generating the exact `CREATE OR ALTER` DDL to apply a recommendation, including split/decompose recipes for producer + consumer patterns.
- Zero-downtime Iceberg V2-to-V3 table swap when incremental refresh is degraded by V2's lack of change tracking.
- Distinguishing settings-only fixes (safe to auto-apply) from structural DDL changes (require explicit review), then presenting a batched plan before executing.

**Representative use cases**
- "Snowflake says my DT has recommendations — what are they and should I apply them?"
- "My DT keeps auto-resolving to full refresh — apply the recommendation to fix it."
- "The warehouse is too small for my DT's refreshes — apply the recommendation."
- "I have an Iceberg V2 base table making my incremental refresh slow — fix it with zero downtime."
- "Look at the `HIGH_BASE_TABLE_CHANGES` recommendation for my orders table and apply the right fix."

**Example prompts**
```
Apply the recommendations for MY_DB.SALES.ORDERS_DT
Look at the recommendations for my dynamic table and fix what needs fixing
My DT has a QUALIFY_RANK_NOT_TOP_LEVEL recommendation — what does that mean?
The WAREHOUSE_TOO_SMALL recommendation fired on my DT — apply it
Check if there are any Snowflake recommendations for ANALYTICS.PUBLIC.FACT_SALES
```

**Depth behind it:** 14 supporting files (`references/recommendation-codes.md`, `references/frozen-where-guidance.md`, `references/primary-key-rely.md`, 11 per-code handler files under `references/codes/`), no sub-skills.

**Prerequisites & caveats:** Requires a specific fully-qualified dynamic table name — does not support schema-wide scans (use `dynamic-tables/monitor` for that). When no recommendations exist the skill exits and routes to `dynamic-tables/optimize`. Recommendations that add columns (`QUALIFY_RANK_KEYS_NOT_PERSISTED`, `TOP_LEVEL_AGGREGATE_EXPRESSIONS_NOT_PERSISTED`) require explicit schema-change approval and are excluded from headless auto-apply. Split/decompose recipes always require approval of the specific fix regardless of session-level apply intent.

**Pairs with:** `dynamic-tables`

---

### `snowflake-tasks`

> Covers the full lifecycle of Snowflake Tasks: creating scheduled and stream-triggered tasks, building task graphs (DAGs), managing execution, querying run history, and troubleshooting failures.

**Snowflake surface it drives:** `CREATE TASK`, `ALTER TASK`, `DROP TASK`, `EXECUTE TASK`, `SHOW TASKS`, `SYSTEM$STREAM_HAS_DATA`, `SYSTEM$GET_TASK_GRAPH_CONFIG`, `SYSTEM$SET_RETURN_VALUE`, `SYSTEM$GET_PREDECESSOR_RETURN_VALUE`, `SYSTEM$TASK_DEPENDENTS_ENABLE`, `SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY`, `SUSPEND_TASK_AFTER_NUM_FAILURES`, `ERROR_INTEGRATION`, `USER_TASK_TIMEOUT_MS`, serverless task compute parameters (`SERVERLESS_TASK_MIN/MAX_STATEMENT_SIZE`)

**What it accelerates**
- Choosing correct interval vs. CRON schedules (`SCHEDULE = '30 MINUTE'` for intervals, never `*/30 * * * *`) and preventing the common `*/43 * * * *` misfire pattern.
- Building fan-out/fan-in task graphs with correct resume order (children before root) and finalizer tasks.
- Passing typed data between tasks using `SYSTEM$SET_RETURN_VALUE` / `SYSTEM$GET_PREDECESSOR_RETURN_VALUE` inside Snowflake Scripting blocks.
- Querying `TASK_HISTORY` efficiently by pushing filters into table-function arguments to avoid silent `RESULT_LIMIT` truncation.
- Diagnosing auto-suspended tasks and selecting between `ERROR_INTEGRATION` (simple failure alerts) and alert-based monitoring (complex conditions).

**Representative use cases**
- "Run a stored procedure every night at 2 AM US/Eastern timezone."
- "Build a task graph that runs three parallel branches, waits for all of them, then runs a final cleanup step."
- "My task keeps auto-suspending after failures — show me the last 24 hours of error details."
- "Pass the row count from one task to the next task in my graph so it can branch conditionally."
- "Trigger a task whenever new data arrives in a stream, with no fixed schedule."
- "Run the same task graph with different region parameters on demand."

**Example prompts**
```
Create a task that runs every 30 minutes and calls my stored procedure
Build a task DAG with three parallel child tasks and a finalizer
My task is auto-suspended — show me the last 24 hours of failures
Set up email alerting when my root task fails
Create a parameterized task graph I can trigger with different region values
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** `EXECUTE TASK` and `EXECUTE MANAGED TASK` are account-level privileges requiring `ACCOUNTADMIN`. Tasks run as their owner role — interactive SQL success does not guarantee task success. `TASK_HISTORY` covers 7 days; use `ACCOUNT_USAGE.TASK_HISTORY` for up to 365 days (with up to 45-minute lag, and no role-level filtering). Alert delegation requires explicit user consent before routing to the `alert` skill.

**Pairs with:** `dynamic-tables`, `alert`, `event-table`, `snowpark-python`

---

### `snowpipe-streaming`

> Guides users through setting up, troubleshooting, monitoring, optimizing, and migrating Snowpipe Streaming pipelines using the High-Performance Architecture exclusively.

**Snowflake surface it drives:** Snowpipe Streaming High-Performance Architecture, `PIPE` objects, `snowpipe-streaming` Python PyPI package, Java SDK, Snowflake REST API, Kafka Connect Snowflake Connector, `insertRows` / `appendRows` channel operations, `SHOW PIPES`, channel health queries, streaming cost views

**What it accelerates**
- Setting up a new streaming pipeline end-to-end (key-pair auth, PIPE creation, SDK channel open) without piecing together documentation.
- Running the bundled `health_check.py` script to diagnose channel status, offset progress, row errors, and ingestion gaps against a live account.
- Troubleshooting offset gaps, channel errors, and ingestion stalls across Python, Java, REST API, and Kafka Connect integrations.
- Migrating existing classic Snowpipe pipelines to the High-Performance Architecture before the mid-2026 deprecation deadline.
- Optimizing throughput, latency, and cost using architecture-specific tuning patterns for each SDK type.

**Representative use cases**
- "I need to stream IoT sensor data from Python into Snowflake with sub-second latency."
- "My Kafka connector is dropping rows and I need to troubleshoot the channel errors."
- "I'm on classic Snowpipe and need to migrate to the new high-performance architecture."
- "Show me the ingestion health, channel offsets, and streaming costs for my pipeline."
- "Set up Kafka Connect to ingest from my Kafka topic to a Snowflake table with schema evolution."

**Example prompts**
```
Set up a Snowpipe Streaming pipeline from Python to ingest event data
My streaming channel has an offset gap — how do I fix it?
Migrate my classic Snowpipe setup to the High-Performance Architecture
Monitor my streaming pipeline health and show ingestion costs
Set up Kafka Connect to stream from my Kafka topic to Snowflake
```

**Depth behind it:** 9 supporting files (6 reference `.md` files: `python-sdk.md`, `java-sdk.md`, `rest-api.md`, `kafka-connect.md`, `common-patterns.md`, `monitoring-queries.md`; 3 scripts: `health_check.py`, `stream_demo.py`, `pyproject.toml`), 5 sub-skills (`setup`, `troubleshoot`, `monitor`, `optimize`, `migrate`).

**Prerequisites & caveats:** High-Performance Architecture only — classic Snowpipe is not covered beyond migration guidance. Key-pair authentication is required for SDK access (password auth is not supported). Classic Snowpipe is planned for deprecation mid-2026. Default pipes use the naming pattern `<TABLE_NAME>-STREAMING` and are auto-created on first channel open. Schema evolution is supported by default on auto-created pipes (new columns added automatically).

**Pairs with:** `snowflake-tasks`, `event-table`, `openflow`, `openflow-observability`

---

### `openflow`

> Covers the full lifecycle of Openflow (Snowflake's NiFi-based data integration product): deploying connectors, managing flows, configuring parameters, troubleshooting errors, and authoring custom NiFi flows, across both SQL-managed (gen 2) and NiFi-API (gen 1) architectures.

**Snowflake surface it drives:** `SHOW OPENFLOW CONNECTOR DEFINITIONS`, `SHOW OPENFLOW RUNTIME`, `DESCRIBE OPENFLOW RUNTIME`, gen 2 SQL lifecycle (`CREATE/ALTER/DROP OPENFLOW CONNECTOR`, `OPENFLOW` SQL grammar), `ACCOUNT_USAGE.OPENFLOW_*` views, `SYSTEM$MIGRATE_OPENFLOW_DEPLOYMENT`, nipyapi Python library, Openflow REST API, External Access Integrations, CDC connectors (PostgreSQL, MySQL, SQL Server, Oracle, MongoDB), SaaS/API connectors (Salesforce, Shopify, Jira, HubSpot, SharePoint, Google Drive, Kinesis, Kafka, and 15+ others)

**What it accelerates**
- Running the gen 2 probe (`SHOW OPENFLOW CONNECTOR DEFINITIONS`) to detect account capability before routing to the correct SQL or NiFi-API path.
- Deploying a connector end-to-end (prerequisites, credential setup, `config.json`, start/verify) without navigating the NiFi canvas manually.
- Packing multiple CDC connectors onto one runtime declaratively for multi-tenant or fleet deployments.
- Migrating from gen 1 to gen 2 (deployment, runtime, and connector migration) after confirming availability via `SYSTEM$MIGRATE_OPENFLOW_DEPLOYMENT`.
- Authoring custom NiFi flows with expression language, RecordPath transformations, and Snowflake destination type mapping.

**Representative use cases**
- "Set up a PostgreSQL CDC connector to replicate my production database into Snowflake."
- "I need to load data from Shopify into Snowflake and keep it in sync."
- "My Kafka connector is showing errors — diagnose what's wrong."
- "Deploy Openflow from scratch on Snowflake-managed SPCS compute."
- "Migrate my existing Openflow deployment from gen 1 to gen 2."
- "Pack 20 PostgreSQL CDC connectors onto a single runtime using the declarative packing workflow."
- "Build a custom NiFi flow that reads from a REST API and writes to Snowflake."

**Example prompts**
```
Set up a PostgreSQL CDC connector in Openflow
My Openflow connector is unhealthy — what's wrong?
Deploy Openflow on Snowflake-managed SPCS compute
Migrate my Openflow deployment to gen 2
Pack multiple MySQL CDC connectors onto one runtime
```

**Depth behind it:** 100+ supporting files (83+ reference `.md` files covering all connectors, NiFi authoring patterns, deployment, migration, parameter management, and platform diagnostics; connector-specific subdirectories for Oracle and Shopify; Python pack assets and JSON/YAML templates), no sub-skills (routing is done via internal reference file loading).

**Prerequisites & caveats:** Snowsight surface is SQL-only (gen 2 operations); NiFi-canvas and gen 1 connector operations require CLI/Desktop with nipyapi or the Openflow UI. Gen 2 migration is in private preview — requires account team enablement. BYOC deployment requires customer-managed AWS compute. For deep connector failure diagnosis use `openflow-observability`. Never surface the internal term "SOM" to customers — use "gen 2" instead.

**Pairs with:** `openflow-observability`, `alert`, `snowpipe-streaming`, `integrations`

---

### `openflow-observability`

> Diagnoses Openflow connector, runtime, and deployment failures via Snowsight SQL diagnostics, and executes a narrow allowlist of SQL actions on SQL-managed (gen 2) runtimes after explicit confirmation.

**Snowflake surface it drives:** `SHOW OPENFLOW CONNECTOR DEFINITIONS`, `SHOW OPENFLOW RUNTIME`, `DESCRIBE OPENFLOW RUNTIME`, `SHOW VERSIONS`, `SHOW GRANTS ON OPENFLOW RUNTIME`, `ACCOUNT_USAGE.OPENFLOW_*` views, event table SQL queries, gen 2 connector lifecycle actions (`ALTER OPENFLOW CONNECTOR`, `ALTER OPENFLOW RUNTIME`), EAI attachment SQL

**What it accelerates**
- Structured startup sequence (load connector family bundle, parse inputs, validate namespace) before running any diagnostic query — preventing improvised recovery steps.
- Per-family triage routing: CDC connectors (PostgreSQL, MySQL, SQL Server, Oracle) via a shared CDC decision tree and state machine; non-CDC (Kafka, Kinesis, MongoDB); SaaS/API (Salesforce, SharePoint, Jira, HubSpot, 10+ others) via dedicated router files.
- Restart Table Replication procedure for FAILED CDC tables, with safety preamble to prevent data-loss mistakes.
- Gated SQL actions on SQL-managed runtimes (resume/suspend runtime, attach EAI, commit or abort connector config changes) after confirming gen 2 and receiving explicit customer consent.

**Representative use cases**
- "My PostgreSQL CDC connector is UNHEALTHY — diagnose it and tell me how to recover."
- "A table in my Openflow connector is FAILED — how do I restart replication for just that table?"
- "My runtime is running out of memory and crashing — what's the root cause?"
- "Add an External Access Integration to my Openflow runtime so it can reach my on-prem source."
- "My connector is stuck in DRAFT and edits aren't applying — fix it via SQL."

**Example prompts**
```
My Openflow connector is unhealthy — diagnose the issue
A table in my CDC connector shows FAILED status — how do I fix it?
My Openflow runtime keeps running out of memory — what's wrong?
Resume my SQL-managed Openflow runtime
The driver is missing on my connector — can you wire it up via SQL?
```

**Depth behind it:** 41 supporting files (9 core and troubleshoot reference `.md` files; 23 per-connector and router files covering CDC, non-CDC, and SaaS/API families; 9 Openflow SQL action reference files), no sub-skills.

**Prerequisites & caveats:** Default mode is read-only SQL diagnosis; SQL mutations require the target runtime to be confirmed SQL-managed (gen 2) and explicit customer confirmation per action. Node size (`NODE_TYPE`) is fixed at create time — cannot be changed via SQL or UI. Structured input fields (`event_table`, `deployment_id`, `connector_type`) are expected from the Snowsight UI trigger but can be provided manually. Not for deploying new connectors or gen 2 migration — use `openflow` for those.

**Pairs with:** `openflow`, `alert`, `integrations`

---

### `snowpark-python`

> Guides users through writing, deploying, and instrumenting Snowpark Python code — pipelines, UDFs, stored procedures, and ETL — with built-in awareness of Snowflake-specific DataFrame semantics that silently differ from standard Pandas/Python.

**Snowflake surface it drives:** Snowpark Python Client (`snowflake-snowpark-python`), `Session.builder`, `DataFrame` API, `UDF`, `UDTF`, `UDAF`, vectorized UDFs, `CREATE PROCEDURE` / `CREATE FUNCTION`, `snow snowpark deploy`, `snow init`, `uv`, Snowflake Telemetry Python library (`snowflake-telemetry-python`), `ACTIVE_PYTHON_PROFILER`, event table logging/tracing

**What it accelerates**
- Writing correct Snowpark transformations that avoid NULL-handling, division-by-zero, `GREATEST`, `DATEDIFF`, and type-casting pitfalls that silently produce wrong results in Snowflake.
- Deploying Python stored procedures and UDFs via `snow snowpark` CLI without manual packaging steps.
- Adding structured logging, distributed tracing, and profiling to Python UDFs/procedures using the telemetry library and event table queries.
- Setting up a proper local project structure (`uv init`, `uv venv`, `pyproject.toml`) for CLI-based development and testing.

**Representative use cases**
- "Build a Snowpark pipeline that ingests CSVs from a stage, joins with a dimension table, and writes to a gold table."
- "Deploy my Python transformation as a stored procedure I can call from a Snowflake Task."
- "My Python UDF is slow — profile it and identify where the hotspot is."
- "Add logging and error tracing to my stored procedure so I can debug failures from the event table."
- "I need a UDTF that parses JSON payloads and emits one row per array element."

**Example prompts**
```
Write a Snowpark pipeline to join orders and customers and write to a gold table
Deploy my Python function as a UDF using the snow snowpark CLI
Add telemetry logging to my stored procedure so I can query it from the event table
Profile my slow Snowpark UDF and find the performance hotspot
Build a vectorized UDF that normalizes text fields in bulk
```

**Depth behind it:** 3 supporting files (`references/snowpark-authoring.md`, `references/snowpark-deployment.md`, `references/snowpark-observability.md`), no sub-skills.

**Prerequisites & caveats:** `uv` must be installed for CLI/local projects. Workspaces `.py` files use `get_active_session()` — no `snow init` or `uv init` needed there. For event table setup, alert triggers, or notifications from Snowpark, use the `event-table`, `alert`, or `notification` skills instead. Troubleshooting and test-generation sub-flows are listed as "not yet supported" in the skill's routing table.

**Pairs with:** `snowflake-tasks`, `event-table`, `dynamic-tables`, `alert`

---

### `dbt-projects-on-snowflake`

> Manages dbt projects deployed as native Snowflake objects via `snow dbt`, and authors Snowflake-specific dbt materializations (`semantic_view`) — explicitly not for standard `dbt run` / local dbt CLI workflows.

**Snowflake surface it drives:** `snow dbt deploy`, `snow dbt execute`, `snow dbt list`, `EXECUTE DBT PROJECT` SQL, `ALTER/DROP/DESCRIBE/SHOW DBT PROJECT`, `CREATE TASK ... AS EXECUTE DBT PROJECT`, `VERSION$`, `dbt_semantic_view` package, `semantic_view` materialization, external access integrations for dbt network access

**What it accelerates**
- Deploying a dbt Core project into Snowflake as a native object (`snow dbt deploy`) with correct external access integration flags and environment variable mapping.
- Executing specific model subsets using `+target_model` / `target_model+` upstream/downstream dependency syntax inside Snowflake.
- Scheduling a deployed dbt project via `CREATE TASK ... AS EXECUTE DBT PROJECT` without writing a wrapper procedure.
- Authoring `semantic_view` dbt models using the `dbt_semantic_view` package so models surface as Cortex Analyst-ready semantic views.
- Migrating `env_var()` references from local dbt to Snowflake-native format.

**Representative use cases**
- "Deploy my dbt project into Snowflake so I can run it with `EXECUTE DBT PROJECT` SQL."
- "Schedule my deployed dbt project to run every day at 6 AM UTC."
- "Add a `semantic_view` materialization to my dbt model for Cortex Analyst."
- "Download the source files from my deployed dbt project and add a new model."
- "My deployed dbt incremental model has bad historical data — I need to run a full refresh."

**Example prompts**
```
Deploy my dbt project to Snowflake using snow dbt deploy
Schedule my deployed dbt project to run nightly via a Snowflake task
Add a semantic_view materialization to my dbt model
Show me the execution logs for my last deployed dbt project run
Migrate my local dbt env_var references for Snowflake-native execution
```

**Depth behind it:** 5 supporting files (`references/cli-reference.md`, `references/private-git-packages.md`, `references/profiles-yml.md`, `references/semantic-views.md`, `references/troubleshooting.md`), 6 sub-skills (`deploy`, `execute`, `manage`, `schedule`, `monitoring`, `migrate`).

**Prerequisites & caveats:** Explicitly not for standard dbt CLI workflows (`dbt run`, `dbt build`, `dbt test`, model editing, CI/CD). After fixing an incremental model's logic, `--full-refresh` is mandatory — a normal incremental run will not correct existing bad-data rows. For semantic view optimization and Cortex Analyst tuning after creation, use `agent-studio` instead. Requires `snow` CLI.

**Pairs with:** `dynamic-tables`, `snowflake-tasks`, `agent-studio`

---

### `dcm`

> Required entry point for all Database Change Management (DCM) work: creating, modifying, deploying, and debugging `snow dcm` projects that manage Snowflake infrastructure as code using a declarative YAML manifest with `DEFINE` primitives.

**Snowflake surface it drives:** `snow dcm create`, `snow dcm plan`, `snow dcm deploy`, `snow dcm analyze`, `snow dcm download`, `snow dcm list`, `snow dcm purge`, `manifest.yml` with `DEFINE TABLE/VIEW/DYNAMIC TABLE/TASK/WAREHOUSE/SCHEMA/DATABASE/ROLE/GRANT` and 20+ other object types, Jinja templating for multi-environment manifests, `--target` flag for environment selection, three-tier role pattern

**What it accelerates**
- Creating a new DCM project with the correct `manifest.yml` structure and per-object DEFINE syntax, loaded on demand from 22 primitive reference files.
- Running `snow dcm plan` to preview changes before `snow dcm deploy`, without memorizing CLI flag combinations.
- Downloading and modifying an existing deployed DCM project when source code is not locally available.
- Authoring Jinja-templated manifests for multi-environment deployments (DEV/PROD targets with shared `templating.defaults`).
- Setting up roles and grants inside a DCM project following the three-tier role pattern.

**Representative use cases**
- "Set up a DCM project to manage all the tables and views in my analytics schema as code."
- "I want to define my Snowflake warehouse, database, and role grants in a single deployable manifest."
- "Preview what changes DCM would make to my account before I deploy to production."
- "Download the DCM source from my existing deployed project and add a new dynamic table."
- "Create a DCM project with separate DEV and PROD targets using Jinja templating."

**Example prompts**
```
Create a new DCM project for my analytics database
Deploy my DCM project changes to Snowflake
Download the source from my deployed DCM project and add a new table
Set up roles and grants in my DCM project following the three-tier pattern
Analyze dependencies in my DCM project before deploying
```

**Depth behind it:** 26 supporting files (3 core reference `.md` files, 22 primitive reference files under `reference/primitives/` covering every supported object type, 1 `scripts/download_project.py`), 5 sub-skills (`create-project`, `deploy-project`, `modify-project`, `purge-project`, `roles-and-grants`).

**Prerequisites & caveats:** Requires Snowflake CLI (`snow`) version 3.17 or later (`snow dcm purge` requires exactly 3.17+). A DCM project cannot define its own parent database or schema — those containers must already exist before deployment. All `snow dcm` commands require a named connection (`-c <connection>`). Not for ad-hoc DDL execution — DCM is an infrastructure-as-code workflow with explicit plan/deploy cycles.

**Pairs with:** `dynamic-tables`, `snowflake-tasks`, `data-governance`

---

### `error-tables-ops`

> Assesses, enables, monitors, and manages Snowflake DML Error Logging (Error Tables) — the feature that lets good rows succeed while capturing rejected rows for analysis and repair instead of rolling back the entire DML statement.

**Snowflake surface it drives:** `ALTER TABLE ... SET ERROR_LOGGING = TRUE`, `ERROR_TABLE()` table function, `INFORMATION_SCHEMA.TABLES`, `GET_DDL('TABLE', fqn)`, `TRUNCATE ERROR_TABLE()`, `QUERY_HISTORY` error code scanning, `CREATE ALERT`, `CREATE TASK`, error codes (100072 NOT NULL, 100078 string truncation, 100046 numeric overflow, 100320 CHECK constraint, and others)

**What it accelerates**
- Identifying which tables would benefit from error logging by scanning `QUERY_HISTORY` for failed INSERT/UPDATE/MERGE and ranking by failure volume.
- Running a hands-on live demo that enables error logging, inserts bad rows, and queries the error table — showing the feature in action rather than explaining it conceptually.
- Analyzing error breakdowns by type and column, estimating error table storage size, and generating cleanup DDL.
- Setting up alert-based monitoring that fires when error counts spike above a configured threshold.
- Re-inserting corrected rows from the error table after per-error-type triage with user approval.

**Representative use cases**
- "My ETL pipeline keeps failing on bad data — I want good rows to land even when some rows are invalid."
- "Which of my tables would benefit most from enabling error logging, based on recent DML failures?"
- "Show me all the errors in my orders table error table, broken down by error type and column."
- "Alert me when my error table accumulates more than 100 errors in an hour."
- "How much storage are all my error tables using across the account?"

**Example prompts**
```
Walk me through setting up error tables with a live demo
Which of my tables have the most DML failures in the last 30 days?
Show me an error breakdown for my orders table error table
Set up an alert that fires when error counts spike
Enable error logging on my customers table
```

**Depth behind it:** 3 supporting files (`references/notes.md`, `references/queries.md`, `skill_evidence.yaml`), no sub-skills.

**Prerequisites & caveats:** Only the base table owner can `SELECT` from the error table. Supported DML: INSERT, UPDATE, and MERGE only. Supported operations on error tables: `SELECT` and `TRUNCATE` only — no DML against the error table itself. Error logging is a table property; there is no per-statement `ERROR_LOGGING = CONTINUE` clause on DML statements. `ERROR_TABLE()` takes the base table name, not the error table name. Errors originating inside subqueries, CTEs, or expressions still fail the full statement and are not diverted.

**Pairs with:** `alert`, `data-quality`, `snowflake-tasks`

---

### `alert`

> Router that delegates to `alert-create-alter` for creating/modifying Snowflake Alerts, or to `alert-troubleshoot` for diagnosing why an alert is firing, failing, or not delivering.

**Snowflake surface it drives:** `CREATE ALERT`, `ALTER ALERT`, `DROP ALERT`, `SUSPEND ALERT`, `RESUME ALERT`, `SHOW ALERTS`, `EXECUTE ALERT`, alert condition queries, `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`, notification integrations, event table queries, `CONDITION_FAILED` / `ACTION_FAILED` / `ACTION_SKIPPED` alert states

**What it accelerates**
- Creating alerts with correct condition queries, action blocks, and schedules using built-in templates for common patterns (alert on new data, scheduled threshold, error table spike).
- Diagnosing silent alerts (not firing when expected), noisy alerts (firing unexpectedly), and delivery failures (action executes but notification never arrives).
- Selecting the right notification dispatch path (email, Slack, Teams, PagerDuty, webhook) for each integration type.
- Implementing action-level alert muting/throttle logic (send at most once per N minutes) using a tracking table pattern.

**Representative use cases**
- "Create an alert that fires when my error table has more than 100 errors in the last hour."
- "Set up an alert that emails me when any dynamic table refresh fails."
- "My alert is firing but I'm not receiving the Slack notification — why?"
- "My alert keeps triggering even though I think the condition is false — debug it."
- "Create a scheduled alert that checks for stale data every 15 minutes."

**Example prompts**
```
Create an alert that fires when my orders table error count exceeds 50 per hour
My alert is not firing even though the condition is true — debug it
Set up an alert that emails me when any dynamic table in my schema fails
Create an alert on new data arriving in a stream
Why did my alert fire at 2am when there was no data change?
```

**Depth behind it:** 14 supporting files (8 main reference `.md` files including alert templates, dispatch paths, and runtime config; `TROUBLESHOOTING_LANDSCAPE.md`; 5 `alert-troubleshoot/references/` diagnostic files), 2 sub-skills (`alert-create-alter`, `alert-troubleshoot`).

**Prerequisites & caveats:** This skill is a mandatory router — it never handles alert requests directly and always delegates to a sub-skill. Requires a notification integration to exist before alert action delivery (co-route to `notification` to create one). Alert condition queries must be read-only; side-effect logic belongs in the action block. Not for data quality DMF-based alerting (use `data-quality`).

**Pairs with:** `notification`, `event-table`, `dynamic-tables`, `snowflake-tasks`, `error-tables-ops`, `data-quality`

---

### `notification`

> Router that directs requests to sub-skills for creating/managing notification integrations, formatting notification content for specific platforms, or sending notifications via `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`.

**Snowflake surface it drives:** `CREATE NOTIFICATION INTEGRATION`, `ALTER NOTIFICATION INTEGRATION`, `DROP NOTIFICATION INTEGRATION`, `SHOW NOTIFICATION INTEGRATIONS`, `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`, email notifications, webhook integrations (Slack, Teams, PagerDuty), Snowflake Secrets for webhook credentials, notification content blocks (HTML email, Slack Block Kit, Teams Adaptive Cards, PagerDuty payloads)

**What it accelerates**
- Creating email and webhook notification integrations with correct secret handling, grant statements, and integration property syntax.
- Formatting query results as richly structured notification bodies (HTML tables, Slack Block Kit, Teams Adaptive Cards) without looking up each platform's schema.
- Sending one-off or programmatic notifications from SQL using `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` with the correct content wrapper.
- Implementing action-level alert muting/throttle patterns (send at most once per hour) using a tracking table.

**Representative use cases**
- "Create a notification integration that sends emails when my alerts fire."
- "Set up a Slack webhook integration so my alerts post to my #data-ops channel."
- "Format my query results as a nicely structured HTML email to send to stakeholders."
- "Send a PagerDuty alert from SQL when a critical error threshold is breached."
- "Limit my alert notifications to at most one per hour even if the condition stays true."

**Example prompts**
```
Create an email notification integration for my alerts
Set up a Slack webhook notification integration
Format my query results as an HTML email and send it
Send a notification to PagerDuty from SQL
Set up alert muting so I get at most one notification per hour
```

**Depth behind it:** 6 supporting reference files (`alert-muting.md`, `default.md`, `email.md`, `pagerduty.md`, `slack.md`, `teams.md`), 3 sub-skills (`notification-integration`, `notification-content`, `notification-send`).

**Prerequisites & caveats:** This skill is a mandatory router — it never handles notification requests directly and always delegates to a sub-skill. Webhook integrations (Slack, Teams, PagerDuty) require a Snowflake Secret storing the webhook URL. Email notifications require account-level email delivery to be enabled. Cloud message queue integrations (Azure Event Grid, Google Pub/Sub, Amazon SNS) are notification integrations of a different type — use the `integrations` skill for those DDL operations.

**Pairs with:** `alert`, `event-table`, `snowflake-tasks`, `integrations`

---

### `integrations`

> Router with 23 sub-skills covering every Snowflake integration type — API, catalog, external access, notification, security, and storage — for `CREATE`, `ALTER`, `DROP`, `DESCRIBE`, and `SHOW` operations.

**Snowflake surface it drives:** `CREATE/ALTER/DROP/DESCRIBE/SHOW INTEGRATION` (generic); `CREATE/ALTER API INTEGRATION`; `CREATE/ALTER/DROP/SHOW/DESCRIBE CATALOG INTEGRATION`; `CREATE/ALTER EXTERNAL ACCESS INTEGRATION`; `CREATE/ALTER/DESCRIBE/SHOW NOTIFICATION INTEGRATION`; `CREATE/ALTER SECURITY INTEGRATION` (SCIM, SAML2, OAuth, API Authentication); `CREATE/ALTER STORAGE INTEGRATION` (S3, GCS, Azure Blob); `SHOW DELEGATED AUTHORIZATIONS`

**What it accelerates**
- Looking up and generating exact DDL for any integration type without needing to know the correct `TYPE=`, `ENABLED=`, and subtype parameter combinations.
- Creating catalog integrations for Iceberg tables across all supported catalog backends (AWS Glue, Object Store, Snowflake Open Catalog, Apache Iceberg REST, SAP Business Data Cloud).
- Creating external access integrations for UDFs and procedures that call external APIs, with correct network rule and secret references.
- Creating security integrations for SCIM provisioning, SAML2 SSO, OAuth flows, and API authentication with third-party services.

**Representative use cases**
- "Create a storage integration for my S3 bucket so Snowflake can read my external stage."
- "Set up an external access integration for my UDF that calls the OpenAI API."
- "Create a catalog integration for my AWS Glue Iceberg catalog."
- "Set up a SCIM security integration for Okta user provisioning."
- "Show all notification integrations in my account and describe the properties of one."

**Example prompts**
```
Create a storage integration for my S3 bucket
Set up an external access integration for a UDF that calls an external API
Create an API integration for my AWS API Gateway
Create a catalog integration for my Iceberg tables on Glue
Show all notification integrations in my account
```

**Depth behind it:** 0 supporting files (no shared `references/`, `scripts/`, or `assets/` directories), 23 sub-skills (`create-integration`, `alter-integration`, `show-integrations`, `describe-integration`, `drop-integration`, `create-api-integration`, `alter-api-integration`, `create-catalog-integration`, `alter-catalog-integration`, `drop-catalog-integration`, `show-catalog-integrations`, `describe-catalog-integration`, `create-external-access-integration`, `alter-external-access-integration`, `create-notification-integration`, `alter-notification-integration`, `describe-notification-integration`, `show-notification-integrations`, `create-security-integration`, `alter-security-integration`, `show-delegated-authorizations`, `create-storage-integration`, `alter-storage-integration`).

**Prerequisites & caveats:** Creating most integrations requires `ACCOUNTADMIN` or a role granted `CREATE INTEGRATION`. S3 storage integrations require additional AWS IAM configuration after creation (the integration generates an IAM ARN and external ID for the bucket policy). Catalog integrations are handled here at the DDL level — for full Iceberg table lifecycle (external volumes, catalog-linked databases, auto-refresh), use the `iceberg` skill.

**Pairs with:** `iceberg`, `openflow`, `notification`, `snowpark-python`, `deploy-to-spcs`

---

### `event-table`

> Router for Snowflake Event Table and telemetry configuration tasks: reading current setup, modifying configuration, and parsing product-specific telemetry event formats from Dynamic Tables, Tasks, Snowpark, and Openflow.

**Snowflake surface it drives:** `CREATE EVENT TABLE`, `ALTER ACCOUNT SET EVENT_TABLE`, `SHOW EVENT TABLES`, `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT`, `ALTER TABLE ... SET LOG_LEVEL / TRACE_LEVEL / METRIC_LEVEL`, `SYSTEM$GET_LOGGING_CONFIG`, event table schema (`RECORD`, `RESOURCE`, `SCOPE`, `VALUE` columns), product-specific telemetry event formats for dynamic tables, tasks, Snowpark procedures/UDFs, and Openflow connectors

**What it accelerates**
- Quickly determining which event table is configured and at what log/trace/metric levels, without browsing `SHOW PARAMETERS`.
- Creating and associating a new event table with the Snowflake account, and setting per-object telemetry levels, with correct `ALTER` syntax.
- Writing SQL queries against the event table for a specific product's telemetry schema (DT refresh failures, task errors, Python procedure exceptions, Openflow connector events) using the correct column paths and filters.

**Representative use cases**
- "What event table is my Snowflake account using and what logging level is it set to?"
- "Create an event table and associate it with my account."
- "Set the log level on my Python stored procedure to INFO."
- "Show me how to query dynamic table refresh failures from the event table."
- "What's the schema for Snowpark Python procedure logs in the event table?"
- "What events does Openflow emit to the event table and how do I query them?"

**Example prompts**
```
What event table is my account configured to use?
Set up a new event table and configure it for my account
Set the trace level on my stored procedure to ALWAYS
Show me how to query task failure events from the event table
What's the schema for Snowpark Python procedure logs in the event table?
```

**Depth behind it:** 4 supporting reference files (`references/dynamic-table.md`, `references/openflow.md`, `references/snowpark.md`, `references/task.md`), 3 sub-skills (`event-table-get-setup`, `event-table-modify-setup`, `event-table-telemetry-format`).

**Prerequisites & caveats:** Associating an event table with the account requires `ACCOUNTADMIN`. Setting log/trace levels on individual objects requires ownership or the appropriate privilege on that object. This skill covers event table infrastructure and telemetry query patterns only — for triggering notifications or alerts based on event table data, use the `alert` or `notification` skills.

**Pairs with:** `snowpark-python`, `snowflake-tasks`, `dynamic-tables`, `openflow-observability`, `alert`

---

## Governance, Security & Trust

*Classifying, protecting, auditing and proving control over data — and over who can reach it.*

### `data-governance`

> Routes governance requests — sensitive-data discovery and classification, protection policies, access evidence, ownership, maturity assessment, and observability — to the correct specialized workflow.

**Snowflake surface it drives:** `SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE`, `CREATE MASKING POLICY`, `CREATE ROW ACCESS POLICY`, `CREATE AGGREGATION POLICY`, `ALTER TABLE MODIFY COLUMN SET MASKING POLICY`, `ALTER TABLE MODIFY COLUMN SET TAG`, `SYSTEM$GET_TAG`, `ALTER ACCOUNT SET CLASSIFICATION_PROFILE`, `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES`, `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES`, `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY`

**What it accelerates**
- Sensitive-data discovery: removes manual column scanning by generating and attaching `CLASSIFICATION_PROFILE` objects with `auto_tag` options, then running results queries.
- Policy creation and gap remediation: eliminates syntax lookup for multi-type policies; the skill's `policy-recommendations` workflow identifies unprotected hot tables and scores them by remediation impact.
- Access and compliance evidence: replaces iterative `SHOW GRANTS` and `ACCESS_HISTORY` joins with a single horizon-catalog workflow slice (grants, roles, MFA status, query history).
- Governance and observability maturity scoring: assembles scores across masking coverage, classification status, DMF coverage, lineage usage, and BI-tool activity — removing multi-query ACCOUNT_USAGE assembly.
- Ownership and stewardship: generates `SYSTEM$REGISTER_BULK_DATA_METRIC_FUNCTION` and object-contact SQL for assigning and querying data owners.

**Representative use cases**
- "Find all columns in our warehouse that might contain PII or credit card numbers."
- "We need to mask SSN and email for all non-admin roles in the SALES schema."
- "Which tables in PROD are accessed frequently but have no masking or row access policy?"
- "Show me who can access our CUSTOMER table and when they last did."
- "Score our governance maturity and tell me the highest-impact gaps to fix first."
- "Identify policy gaps and recommend remediation actions for my account."
- "Generate an observability maturity report for the ANALYTICS database."

**Example prompts**
```
Classify sensitive data in PROD.CUSTOMER schema
Create a masking policy for email and SSN columns in the analytics database
Which tables in SALES are accessed but have no row access policy?
Identify policy gaps and recommend remediation actions for my account
Show me the governance maturity score for this account
```

**Depth behind it:** ~61 supporting files, no sub-skills. Workflows: `sensitive-data-classification.md`, `data-policy.md` (+ 7-file sub-folder), `horizon-catalog.md` + `horizon-catalog-index.md` (+ 9-file sub-folder), `access-review-and-stewardship.md`, `object-contacts.md`, `governance-maturity-score.md`, `observability-maturity-score.md`, `policy-recommendations.md`. Templates include SQL for classification, masking, policy recommendations, and two `generate_report_pdf.py` scripts.

**Prerequisites & caveats:** `ACCOUNTADMIN` or explicit `CREATE MASKING POLICY` / `APPLY TAG` / `APPLY ROW ACCESS POLICY` grants for mutation; `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` for ACCOUNT_USAGE queries; classification profiles require Enterprise Edition. Route data-value errors and failing DMFs to `data-quality` first; route upstream/downstream dependency questions to `lineage`.

**Pairs with:** `data-quality`, `lineage`, `business-ontology`, `intent-driven-governance`

---

### `intent-driven-governance`

> Guides the user through a 5-phase commit-based workflow — Observe, Capture Intent, Derive Governance Spec, Generate SQL, Execute — to apply Snowflake governance changes safely with an explicit human approval gate before any mutation runs.

**Snowflake surface it drives:** `CREATE MASKING POLICY`, `CREATE TAG`, `ALTER TABLE MODIFY COLUMN SET MASKING POLICY`, `ALTER TABLE MODIFY COLUMN SET TAG`, `SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE`, `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES` (managed stage), `EXECUTE IMMEDIATE ... DRY_RUN = TRUE`, `CREATE TASK`, `SYSTEM$SEND_EMAIL`, `GOVERNANCE_INTENT_WORKSPACE.MONITORING` schema (drift runs, findings tables, stored procedures)

**What it accelerates**
- Safe governance rollouts: removes ad-hoc DDL guesswork by requiring explicit approval of exact SQL before any statement executes; dry-run gating catches errors pre-flight.
- Scheduled drift monitoring: generates a full `TASK` + stored-procedure drift-check package that detects and emails on governance drift without manual re-inspection.
- Handoff preparation: packages governance SQL into a staged artifact so a privileged role can execute without the agent ever having the necessary grants.
- Rollback and revert: immutable versioned snapshots in `versions/vNNN/` let any committed baseline be restored via Revert Mode.
- Deterministic fallback rendering: uses SQL template renderers when the Python kernel is unavailable, keeping the workflow unblocked in restricted runtimes.

**Representative use cases**
- "Walk me through applying masking policies to our finance schema — I want to review everything before it runs."
- "Set up scheduled drift monitoring to email us if someone removes a tag or policy."
- "We need to roll back governance to the v003 snapshot."
- "I only have read access — prepare a handoff package for our admin."
- "Show me whether our governance controls have drifted from last week's committed baseline."

**Example prompts**
```
Start intent-driven governance for the ANALYTICS database
Set up drift monitoring for our governance controls and notify us by email
Revert governance to version v002
Prepare a governance handoff package — I only have SYSADMIN
Check whether governance has drifted from the last committed version
```

**Depth behind it:** ~24 supporting files (8 phase `.md` files, 7 kernel Python modules in `kernel/` and `kernel/phases/`, 2 facility `.md` files, 1 `STATE.md`, 1 `scripts/control_plane.py`, 2 additional), no sub-skills.

**Prerequisites & caveats:** Write access to `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES`; role with governance DDL privileges for full execution (read-only role enters handoff mode automatically). Invoke only when the user explicitly says "intent-driven governance," "IDG," or asks to revert to a committed version; do not use for ordinary governance questions.

**Pairs with:** `data-governance`

---

### `data-quality`

> Monitors, investigates, and enforces data quality across Snowflake schemas using Data Metric Functions (DMFs), with separate monitoring paths for tables, schemas, and Cortex Agents, plus prompt quality scoring and table-comparison workflows.

**Snowflake surface it drives:** `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()`, `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS`, `INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES()`, `SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_EXPECTATIONS`, `SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY`, `CREATE DATA METRIC FUNCTION`, `ALTER TABLE ADD DATA METRIC FUNCTION`, `ALTER SCHEMA ADD DATA METRIC FUNCTION`, `DATA_QUALITY_MONITORING_SETTINGS` (YAML), `CREATE ALERT`, `SNOWFLAKE.LOCAL.AGENT_QUALITY_MONITORING_RESULTS`, `SNOWFLAKE.LOCAL.AGENT_QUALITY_MONITORING_EXPECTATION_STATUS`, `SNOWFLAKE.CORE.GET_LINEAGE()` (pipeline-context template)

**What it accelerates**
- DMF setup and recommendations: auto-profiles columns and recommends the right DMF per type, optionally ranked by upstream/downstream pipeline criticality via lineage.
- Incident investigation: orchestrates `DATA_QUALITY_MONITORING_RESULTS()` → `lineage` skill → `data-governance` skill to deliver a multi-dimensional root-cause report in one pass.
- Cortex Agent quality monitoring: removes boilerplate for attaching `AGENT_ERROR_RATE` and `AGENT_LATENCY_P95` DMFs with version-keyed expectations and wiring on-violation tasks.
- Data quality notifications: generates the full `DATA_QUALITY_MONITORING_SETTINGS` YAML for native email and webhook notifications, removing manual integration wiring.
- Table comparison: provides a structured diff workflow (row count, schema, exact-match, distribution) for migration validation and regression testing.

**Representative use cases**
- "Set up data quality monitoring for our SALES schema — I don't know where to start."
- "Why is the freshness check failing on the ORDERS table?"
- "Alert the team on Slack when any null-count DMF trips an expectation in the CUSTOMER schema."
- "Compare our dev and prod CUSTOMERS tables to validate a migration."
- "Which version of my Cortex Agent is failing its quality expectations?"

**Example prompts**
```
Set up DMFs for the FINANCE.REPORTING schema
Why did quality drop on PROD.SALES.TRANSACTIONS?
Enable data quality notifications and email the data team on violations
Compare STAGING.ORDERS and PROD.ORDERS for migration validation
Show me which Cortex Agent version is failing its error-rate expectation
```

**Depth behind it:** ~67 supporting files (22 workflow `.md` files + 5 compare-tables sub-workflows + ~25 SQL templates + 10 compare-tables SQL templates + 5 reference files), no sub-skills.

**Prerequisites & caveats:** `CREATE DATA METRIC FUNCTION` and `EXECUTE DATA METRIC FUNCTION` for DMF attachment; `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` for `ACCOUNT_USAGE` queries; `NOTIFICATION INTEGRATION` for email/webhook notifications; agent DMF monitoring requires a separate account-level feature flag enabled by ACCOUNTADMIN. Do not use `SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS` — it does not exist; always use the table function `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()`.

**Pairs with:** `lineage`, `data-governance`, `alert`

---

### `lineage`

> Traces upstream and downstream object and column lineage in Snowflake using `SNOWFLAKE.CORE.GET_LINEAGE()`, with dedicated workflows for impact analysis, root-cause tracing, data discovery/trust, and column-level lineage.

**Snowflake surface it drives:** `SNOWFLAKE.CORE.GET_LINEAGE()`, `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES` (fallback), `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.TABLES`, `SNOWFLAKE.ACCOUNT_USAGE.COLUMNS`, `cortex lineage` CLI

**What it accelerates**
- Blast-radius analysis: replaces iterative manual dependency tracing with a single parameterized `GET_LINEAGE` call that returns risk-tiered downstream objects and affected users.
- Root-cause tracing: follows data-movement edges (including CTAS, `COPY INTO`, views) upstream to the source, which `OBJECT_DEPENDENCIES` alone cannot do.
- Column-level lineage: covers the gap `OBJECT_DEPENDENCIES` leaves by tracing individual column flows using `ACCESS_HISTORY`-backed templates.
- External entity lineage: surfaces Power BI, Tableau, dbt, and Airflow entities as additional rows when Horizon Catalog connectors or the OpenLineage API is configured on the account.
- Cortex Agent lineage: anchors `GET_LINEAGE` on `OBJECT_DOMAIN => 'CORTEX_AGENT'` to trace which semantic views and search services an agent depends on.

**Representative use cases**
- "If I drop the RAW_EVENTS table, what pipelines and dashboards will break?"
- "Where does the REVENUE column in our finance report actually come from?"
- "Which users are impacted if I rename this view?"
- "Trace all upstream sources for ANALYTICS.GOLD.CUSTOMER_METRICS."
- "What Snowflake tables does my SALES_AGENT Cortex Agent depend on?"

**Example prompts**
```
What depends on PROD.RAW.EVENTS? Show me the blast radius
Trace upstream from ANALYTICS.REPORTING.REVENUE_SUMMARY
Where does the CUSTOMER_ID column in GOLD.CUSTOMER_METRICS come from?
What will break if I rename STAGING.ORDERS?
Show me the lineage for my Cortex Agent SALES_AGENT
```

**Depth behind it:** 31 supporting files (23 SQL templates, 4 workflow `.md` files, 3 reference `.md` files, 1 `config/schema-patterns.yaml`), no sub-skills.

**Prerequisites & caveats:** Standard `SELECT` on `INFORMATION_SCHEMA` for `GET_LINEAGE`; `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` for `OBJECT_DEPENDENCIES` fallback; Horizon Catalog connector (Private Preview) or OpenLineage API required for external entity rows; `CORTEX_AGENT` domain for agent lineage is actively rolling out per account — attempt the call rather than predicting availability. `GET_LINEAGE` max depth is 5; use `OBJECT_DEPENDENCIES` fallback for deeper chains.

**Pairs with:** `data-quality`, `data-governance`, `recommend-object`

---

### `business-ontology`

> A router and workflow orchestrator for Snowflake Business Ontology: creating, importing (from files, dbt, Semantic Views, stage sources), deleting, and syncing governed business nodes, domains, relationships, and object representations via the `SYSTEM$` draft-activate API.

**Snowflake surface it drives:** `SYSTEM$DRAFT_GLOSSARY_TERM`, `SYSTEM$APPROVE_GLOSSARY_TERM`, `SYSTEM$APPROVE_ALL_GLOSSARY_TERMS`, `SYSTEM$CREATE_GLOSSARY_ASSOCIATION`, `SYSTEM$DRAFT_GLOSSARY_ASSET`, `SYSTEM$GET_GLOSSARY_SUMMARY()`, `SYSTEM$GET_GLOSSARY_GRAPH()`, `SYSTEM$GET_GLOSSARY_TERM()`, `SYSTEM$UPDATE_GLOSSARY_TERM()`, `SYSTEM$DELETE_GLOSSARY_TERM()`, `SHOW SEMANTIC VIEWS`, `DESC SEMANTIC VIEW`

**What it accelerates**
- Ontology bootstrapping from existing assets: automates extraction of business concepts from dbt `manifest.json`, `INFORMATION_SCHEMA` table comments, and Semantic Views — removing manual entry for large estates.
- Draft-activate workflow: enforces the review gate (draft → approve) so no concept reaches the canonical ontology without a human decision; batch approval is supported for reviewed sets.
- SV-to-ontology reverse ingest: derives draft nodes and domain assignments from Semantic View lineage rather than guessing, cutting the most error-prone step in ontology setup.
- Drift detection: compares the live Semantic View estate against ontology nodes and representations to surface missing or stale entries.
- Stage source registration: tracks stage files and prefixes as durable ontology sources for repeated imports as data evolves.

**Representative use cases**
- "Import our dbt manifest.json to bootstrap the ontology with business terms."
- "Scan our Semantic Views and create ontology nodes from the concepts they govern."
- "Add a new 'Revenue' node to the Finance domain and link it to the REVENUE_SUMMARY table."
- "Find drift between our Semantic Views and the business ontology."
- "Register our stage prefix as a recurring ontology source and import from it."

**Example prompts**
```
Import our business glossary from the CSV file on our stage
Bootstrap the ontology from our Semantic Views
Add a glossary term 'Customer Lifetime Value' to the Marketing domain
Find drift between our semantic views and the business ontology
Create a relationship between the Customer and Order nodes
```

**Depth behind it:** ~38 supporting files (12 reference `.md` files, 9 scripts including 5 Python extraction scripts, 1 `README.md`, 1 `pyproject.toml`, 1 `uv.lock`, 2 sub-workflow reference files, 1 example SQL file, 1 `domain_map.example.yaml`), 10 sub-skills (`workflow`, `workflow/create`, `workflow/import`, `workflow/delete`, `workflow/source`, `workflow/sv-ingest`, `workflow/phase-0-bootstrap-from-sv`, `workflow/phase-1-define`, `workflow/phase-2-enrich`, `workflow/phase-3-generate`).

**Prerequisites & caveats:** Business Ontology feature must be enabled on the account (`FEATURE_BUSINESS_GLOSSARY`); all mutations require Business Ontology-enabled role. Scripts use `uv`-managed Python dependencies (pyproject.toml present). Domain is never invented — every node must belong to a user-confirmed domain before drafting; extraction scripts emit placeholder domains (`Default`, `HAMID_PDS`) that must be treated as unresolved.

**Pairs with:** `agent-studio`, `lineage`, `data-governance`

---

### `certify-object`

> Applies `SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED'` to a named Snowflake table or view, confirms the tag is live via `SYSTEM$GET_TAG`, and provides the exact `GRANT APPLY ON TAG` SQL if permissions are insufficient.

**Snowflake surface it drives:** `ALTER TABLE SET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS`, `ALTER VIEW SET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS`, `SYSTEM$GET_TAG`, `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES`, `GRANT APPLY ON TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS`

**What it accelerates**
- Certification execution: removes syntax lookup for `ALTER TABLE SET TAG` with the built-in `SNOWFLAKE.CORE` tag — no need to look up the tag FQN or allowed values.
- Permission troubleshooting: generates the exact `GRANT APPLY ON TAG` statement when the operation fails, instead of blocking.
- Immediate verification: uses `SYSTEM$GET_TAG` (real-time) rather than `ACCOUNT_USAGE.TAG_REFERENCES` (2–3 hr lag) to confirm the tag is live.

**Representative use cases**
- "Mark ANALYTICS.GOLD.REVENUE_SUMMARY as certified."
- "Certify this table as a trusted source for the finance team."
- "Tag our customer metrics view as certified so it appears in governance searches."

**Example prompts**
```
Certify ANALYTICS.GOLD.CUSTOMER_METRICS as a trusted source
Mark PROD.FINANCE.REVENUE_SUMMARY as certified
Tag this view as certified
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** `APPLY TAG` privilege on `SNOWFLAKE.CORE.CERTIFICATION_STATUS`, or `ACCOUNTADMIN`; target object must already exist. `TAG_REFERENCES` has up to 2–3 hour lag; `SYSTEM$GET_TAG` reflects the tag immediately. To remove: `ALTER TABLE ... UNSET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS`.

**Pairs with:** `recommend-object`, `certified-data-product-discovery`, `data-governance`

---

### `certified-data-product-discovery`

> Searches Snowflake for certified data products relevant to a user's question using Snowscope, classifies results by certification status and Discover-Not-Access (DNA) standing, presents a grouped menu, and executes SQL against the chosen certified object.

**Snowflake surface it drives:** `cortex search object` CLI (Snowscope with `includeDiscoverOnly`), `SYSTEM$GET_TAG('SNOWFLAKE.CORE.CERTIFICATION_STATUS', ...)`, `DESCRIBE TABLE`, `SELECT` (on the chosen object), `USE WAREHOUSE`

**What it accelerates**
- Trusted-source discovery: eliminates manual `TAG_REFERENCES` queries by using Snowscope semantic search with a certification boost, returning certified objects ranked by relevance.
- Access triage: surfaces DNA objects so users know what exists but isn't yet accessible, and provides exact language to take to their data platform team to request access.
- End-to-end governed answer: moves from discovery directly to SQL execution on the certified source, with every certified object labelled `[CERTIFIED]` throughout the response.

**Representative use cases**
- "Use certified data only to tell me our monthly revenue by region."
- "Find trusted sources for customer churn metrics in the ANALYTICS database."
- "Which certified tables do we have for marketing campaign analysis?"
- "Answer this question using only governed, certified data — I don't want to use raw tables."

**Example prompts**
```
Who are our top 10 customers by revenue? Use certified data only
Find certified data for monthly recurring revenue
What certified tables exist for supply chain inventory?
Answer using only certified sources in PROD.ANALYTICS
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** `cortex search object` CLI must be available; `SELECT` privilege on any certified object the user queries; account must use `SNOWFLAKE.CORE.CERTIFICATION_STATUS` tag to mark certified objects — if no objects are tagged, the skill still runs but all results are uncertified. Not for publishing data products (`collaboration/data-products`) or cross-account sharing (`data-sharing`).

**Pairs with:** `certify-object`, `recommend-object`, `sql-author`

---

### `recommend-object`

> Scores and ranks already-identified candidate Snowflake objects by trustworthiness using a 105-point rubric covering semantic view backing, human-verified queries, pipeline ownership, Streamlit dependencies, schema governance signals, and data freshness.

**Snowflake surface it drives:** `SHOW TABLES`, `SHOW VIEWS`, `SHOW SEMANTIC VIEWS IN SCHEMA`, `DESC SEMANTIC VIEW`, `DESC TABLE`, `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES`, `SYSTEM$GET_TAG('SNOWFLAKE.CORE.CERTIFICATION_STATUS', ...)`, `SELECT MAX(<date_col>)`

**What it accelerates**
- Trust signal assembly: replaces multi-step manual investigation (semantic views, downstream deps, service-role ownership, freshness) with a structured single-pass scoring workflow.
- Defensible recommendation: applies a documented priority order (verified queries > service role + daily refresh > Streamlit consumers > schema placement) so the rationale is auditable.
- Certification handoff: chains into `certify-object` after scoring so a high-trust winner can be immediately tagged as `CERTIFIED`.

**Representative use cases**
- "We have three REVENUE tables in different schemas — which one should our analysts actually use?"
- "Score these candidate tables and tell me which is most trustworthy for the finance report."
- "Which of these views is backed by a semantic view with human-verified queries?"
- "Rank TEMP.JSMITH.ORDERS vs PROD.SALES.ORDERS vs STAGING.RAW.ORDERS."

**Example prompts**
```
Which table should I use for revenue: PROD.FINANCE.REVENUE or STAGING.FINANCE.REVENUE_STAGE?
Score these three candidate tables and recommend the best one
Rank TEMP.DEV.CUSTOMERS vs PROD.GOLD.CUSTOMERS by trustworthiness
Which of these views is backed by verified semantic view queries?
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` for `OBJECT_DEPENDENCIES`; `SELECT` on candidate tables for freshness queries; candidate objects must already be identified before invoking — this skill scores candidates, it does not search. `OBJECT_DEPENDENCIES` does not track semantic view references; the skill detects SV backing directly via `SHOW SEMANTIC VIEWS` + `DESC SEMANTIC VIEW`.

**Pairs with:** `certify-object`, `certified-data-product-discovery`, `lineage`

---

### `access-troubleshooter`

> Debugs Snowflake authorization failures, analyzes required privileges for a SQL statement, finds authorizing roles, and creates least-privilege roles — using `EXPLAIN_PRIVILEGES`, `SYSTEM$ANALYZE_ROLE_ACCESS`, and `SYSTEM$SUGGEST_ROLE_GRANTS`.

**Snowflake surface it drives:** `EXPLAIN_PRIVILEGES()`, `SYSTEM$ANALYZE_ROLE_ACCESS()`, `SYSTEM$SUGGEST_ROLE_GRANTS()`, `CREATE ROLE`, `GRANT ROLE`, `SHOW GRANTS TO USER`, `SHOW GRANTS TO ROLE`, `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES`

**What it accelerates**
- Permission debugging: replaces manual `SHOW GRANTS` chaining with `EXPLAIN_PRIVILEGES(sql, missing_only => true)` to identify exactly what is missing for a given SQL statement and session.
- Least-privilege role design: generates the minimum `GRANT` set for a specific SQL statement rather than requiring the user to derive permissions from scratch.
- On-behalf-of analysis: supports checking access for a different target user (`forUser` parameter) so admins can debug for service accounts or other users.
- Automated trigger: detects "Insufficient privileges" and "does not exist or not authorized" error patterns in the conversation and proactively offers to debug.

**Representative use cases**
- "I'm getting 'Insufficient privileges to operate on schema' — what is missing?"
- "Create a least-privilege role for running this stored procedure."
- "Which roles in our account can currently run this analytics query?"
- "What grants does the DATA_ANALYST role need for this specific query?"
- "Debug what USER_X is missing to run this pipeline task."

**Example prompts**
```
I got "Insufficient privileges to operate on schema PROD" — debug this
Create a least-privilege role for this SQL: SELECT * FROM FINANCE.ORDERS
Which roles can run this query?
What grants does ANALYST_ROLE need for this query?
Debug access for USER_X on this pipeline query
```

**Depth behind it:** 9 supporting files (5 workflow `.md` files, 1 `references/function-reference.md`, 2 test SQL files, 1 `access-troubleshooter-prompts.md`), no sub-skills.

**Prerequisites & caveats:** `EXPLAIN_PRIVILEGES` may not be available on all account versions — fall back to `SYSTEM$ANALYZE_ROLE_ACCESS`; `ACCOUNTADMIN` or `SECURITYADMIN` required for `CREATE ROLE` / `GRANT` execution; on-behalf-of analysis (`SHOW GRANTS TO USER <other>`) requires elevated privileges. If `requires access on all objects in the statement` is returned, stop and advise ACCOUNTADMIN involvement rather than leaking object existence via `SHOW TABLES`.

**Pairs with:** `data-governance`, `security-investigation`, `manage-authentication-policy`

---

### `security-investigation`

> Routes Snowflake security investigations to three specialized sub-skills — login/IP anomalies, data exfiltration, and privilege escalation — covering MITRE ATT&CK T1078/T1098/T1530/T1537 threat categories, with a full-scan option that sequences all three.

**Snowflake surface it drives:** `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` (query types: `UNLOAD`, `COPY`, `GRANT`, `CREATE_USER`), `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES`, `SNOWFLAKE.ACCOUNT_USAGE.USERS`

**What it accelerates**
- Incident triage: provides a single entry point for any security question and routes to the right detection workflow without requiring knowledge of which ACCOUNT_USAGE view covers which threat.
- Brute-force and impossible-travel detection: wraps IP baseline analysis, new-IP detection, and rapid-IP-change detection behind a simple "Login & Authentication" selection.
- Exfiltration detection: covers UNLOAD/COPY, stage GET commands, presigned URLs, CREATE SHARE, OAuth app changes, and external table activity in one structured workflow.
- Compliance audits: structured output maps directly to SOC 2, PCI, HIPAA audit trail requirements for login, privilege, and data-export history.

**Representative use cases**
- "Check if anyone has been brute-forcing our Snowflake account."
- "Were any large data exports made in the last 7 days?"
- "Has anyone granted themselves ACCOUNTADMIN recently?"
- "Run a full security scan on our Snowflake account."
- "Show me all new user accounts created in the past 30 days."

**Example prompts**
```
Run a full Snowflake security scan
Check for brute-force login attempts in the last 7 days
Were there unusual data exports or COPY commands this week?
Has anyone escalated their own privileges recently?
Show all ACCOUNTADMIN grants in the past 30 days
```

**Depth behind it:** 3 supporting files (3 sub-skill `SKILL.md` files), 3 sub-skills (`login-ip-anomaly`, `exfiltration-detection`, `privilege-escalation`).

**Prerequisites & caveats:** `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` or `ACCOUNTADMIN` for `ACCOUNT_USAGE` access; queries access sensitive audit data. `ACCOUNT_USAGE` views have 45 min–3 hr latency; very recent events may not appear.

**Pairs with:** `trust-center`, `access-troubleshooter`, `data-governance`

---

### `trust-center`

> Routes Snowflake Trust Center requests to four sub-skills covering security findings analysis, scanner inventory, scanner configuration (enable/disable/schedule/notify), and step-by-step finding remediation.

**Snowflake surface it drives:** Snowflake Trust Center stored procedures (`SNOWFLAKE.TRUST_CENTER.*`), Trust Center finding and scanner views, `SNOWFLAKE.ACCOUNT_USAGE` (for remediation queries), CIS Benchmarks scanner, Security Essentials scanner, Threat Intelligence scanner, AI Security scanner; `references/trust-center-api.md` is loaded before any query is written.

**What it accelerates**
- Security posture review: assembles finding counts, severity distribution, and trend data from Trust Center views without manual SQL construction.
- Scanner management: changes schedules, thresholds, notification integrations, and sensitivity parameters via the stored procedure API rather than the Snowsight UI.
- Guided remediation: generates specific SQL for individual findings (e.g. "PUBLIC role has database privileges") rather than requiring the user to interpret the finding and look up the fix.
- Coverage gap analysis: lists disabled scanners and explains which CIS benchmark controls or threat detections they cover.

**Representative use cases**
- "Show me all critical Trust Center security findings."
- "Which scanners are disabled and what coverage am I missing?"
- "Enable the AI Security scanner and send alerts to a webhook."
- "Give me step-by-step remediation for the 'PUBLIC role has database privileges' finding."
- "How has our security posture changed over the past month?"

**Example prompts**
```
Show a summary of our Trust Center security findings
Which CIS benchmark checks are currently failing?
Enable the Threat Intelligence scanner and set up email notifications
How do I fix the finding about excessive PUBLIC role privileges?
Show the trend in new vs resolved security findings this month
```

**Depth behind it:** 8 supporting files (4 sub-skill `SKILL.md` files, 4 reference `.md` files: `trust-center-api.md`, `custom-scanner-api.md`, `programmatic-remediation-api.md`, `verify-enable-extension.md`), 4 sub-skills (`findings-analysis`, `scanner-analysis`, `api-management`, `finding-remediation`).

**Prerequisites & caveats:** Trust Center must be enabled on the account; `ACCOUNTADMIN` or `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` for Trust Center views; specific scanner packages (Threat Intelligence, AI Security) may require higher Snowflake editions or separate enablement.

**Pairs with:** `security-investigation`, `manage-authentication-policy`, `network-security`

---

### `network-security`

> Recommends, evaluates, and migrates Snowflake network policies using built-in stored procedures, automatically checks which IPs are covered by Snowflake-managed SaaS rules, and generates hybrid policies combining custom and SaaS rules.

**Snowflake surface it drives:** `CALL snowflake.network_security.recommend_network_policy()`, `CALL snowflake.network_security.evaluate_candidate_network_policy()`, `CREATE NETWORK RULE`, `CREATE NETWORK POLICY`, `ALTER ACCOUNT SET NETWORK_POLICY`, `ALTER USER SET NETWORK_POLICY`, `SHOW NETWORK POLICIES`, `DESCRIBE NETWORK POLICY`, `DESCRIBE NETWORK RULE`, `SNOWFLAKE.ACCOUNT_USAGE.NETWORK_RULES`, `SNOWFLAKE.NETWORK_SECURITY.*` (pre-built SaaS rules for dbt, Tableau, Power BI, etc.)

**What it accelerates**
- Policy recommendation from access history: calls `recommend_network_policy` to extract real login IPs over a configurable lookback window, removing manual IP extraction and CIDR analysis.
- SaaS coverage analysis: runs an IP-to-CIDR range check against `SNOWFLAKE.ACCOUNT_USAGE.NETWORK_RULES` to identify which IPs are already covered by Snowflake-managed SaaS rules, avoiding over-specification.
- Hybrid policy creation: generates exact DDL for the recommended pattern (custom rule for environment IPs + SaaS rules for vendor IPs), then offers to evaluate the policy before deployment.

**Representative use cases**
- "Generate a network policy recommendation based on our last 90 days of login history."
- "We have an existing network policy — migrate it to use Snowflake SaaS rules where possible."
- "Will this new network policy block any of our current users?"
- "Create a network policy that allows only our VPN and Tableau Cloud IPs."
- "Evaluate our current policy against the last 30 days to check for coverage gaps."

**Example prompts**
```
Recommend a network policy based on the last 90 days of login history
Migrate our existing network policy to use Snowflake-managed SaaS rules
Evaluate PROD_NETWORK_POLICY against all users for the last 30 days
Create a hybrid network policy for our VPN plus dbt Cloud and Tableau IPs
Generate an account-level network policy recommendation
```

**Depth behind it:** 1 supporting file (`references/ddl-reference.md`), no sub-skills.

**Prerequisites & caveats:** `CREATE NETWORK RULE` and `CREATE NETWORK POLICY` grants (or `ACCOUNTADMIN`); `snowflake.network_security.recommend_network_policy` stored procedure must be available on the account. Network rules must be created before the network policy that references them. Internal IPs (`10.x`, `172.16-31.x`, `192.168.x`) will not match SaaS rules and must go into custom rules.

**Pairs with:** `manage-authentication-policy`, `security-investigation`, `trust-center`

---

### `manage-authentication-policy`

> Creates, modifies, views, attaches, detaches, drops, and recommends Snowflake authentication policies controlling allowed auth methods (PASSWORD, SAML, OAUTH, KEYPAIR), MFA enforcement, PAT expiry, client types, minimum driver versions, and workload identity federation.

**Snowflake surface it drives:** `CREATE AUTHENTICATION POLICY`, `ALTER AUTHENTICATION POLICY`, `DROP AUTHENTICATION POLICY`, `DESCRIBE AUTHENTICATION POLICY`, `SHOW AUTHENTICATION POLICIES`, `ALTER ACCOUNT SET AUTHENTICATION POLICY`, `ALTER USER SET AUTHENTICATION POLICY`, `SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.USERS`

**What it accelerates**
- Policy recommendation from LOGIN_HISTORY: analyzes real login-method distribution to propose tailored policies rather than requiring the user to reason about auth methods in the abstract.
- Compatibility validation: enforces the property compatibility matrix (e.g. only `PASSWORD` and `SAML` work for `SNOWFLAKE_UI`) before DDL is generated, preventing silent mis-configurations.
- Precedence explanation: makes the three-level hierarchy (account → account-user-type → user) explicit so admins understand which policy wins without trial and error.
- Role-persistence safety: all DDL is emitted as multi-statement calls to prevent the `USE ROLE` revert bug inherent in sequential `sql_execute` calls.

**Representative use cases**
- "Block password auth for all human users — require SAML only."
- "Enforce MFA for all users in the ANALYST role."
- "Set a 30-day maximum PAT expiry for service accounts."
- "Recommend authentication policies based on our actual LOGIN_HISTORY."
- "Which users don't have an authentication policy applied?"

**Example prompts**
```
Create an authentication policy that requires SAML for all human users
Enforce MFA for our ANALYST role
Set up a PAT policy with 30-day max expiry for service accounts
Recommend authentication policies based on our LOGIN_HISTORY
Show me all authentication policies currently attached in our account
```

**Depth behind it:** 9 supporting files (6 workflow `.md` files: `create`, `modify`, `view`, `attach-detach`, `drop`, `recommend`; 1 `references/property-reference.md`; 2 `skill_metadata` files), no sub-skills.

**Prerequisites & caveats:** `CREATE AUTHENTICATION POLICY` on schema for creation; `APPLY AUTHENTICATION POLICY` on Account for attachment; `OWNERSHIP` on policy for modification/drop; `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` for LOGIN_HISTORY in the recommend workflow. Scoped to authentication policies only — do not use for session policies, password policies, network policies, or RBAC grants (those belong to other skills).

**Pairs with:** `setup-snowflake-sso`, `trust-center`, `network-security`

---

### `setup-snowflake-sso`

> Configures Snowflake Single Sign-On for Microsoft Entra ID, Okta, or any SAML 2.0 provider, supporting manual UI, self-service `curl`, and automated API methods, with additional workflows for Allowed Interfaces, Auto Redirect, and Snowflake Intelligence tile setup.

**Snowflake surface it drives:** `CREATE SECURITY INTEGRATION` (SAML2 and SCIM types), `ALTER SECURITY INTEGRATION`, `SHOW SECURITY INTEGRATIONS`, `ALTER USER SET ALLOWED_INTERFACES`, `ALTER ACCOUNT SET DEFAULT_IDENTITY_PROVIDER`, `SAML2` security integration parameters (`SAML2_SNOWFLAKE_ISSUER_URL`, `SAML2_SSO_URL`, `SAML2_X509_CERT`, etc.), `CURRENT_ORGANIZATION_NAME()`, `CURRENT_ACCOUNT_NAME()`

**What it accelerates**
- End-to-end SSO setup: delivers step-by-step instructions for both the IdP and Snowflake sides in the correct order, removing the coordination overhead that typically spans multiple documentation pages.
- API-driven automation: generates or executes exact `curl` commands against Okta or Entra ID APIs for app creation and SCIM provisioning when the user opts into the automated method.
- Allowed Interfaces configuration: removes the `ALTER USER SET ALLOWED_INTERFACES` syntax lookup for restricting users to Snowflake Intelligence or Streamlit, including SCIM-based provisioning via the IdP.
- Idempotent check: inspects existing `SECURITY INTEGRATIONS` before creating new ones, preventing duplicate setup.

**Representative use cases**
- "Set up Okta SSO for our Snowflake account."
- "Configure Microsoft Entra ID as our identity provider with SCIM user provisioning."
- "We use a generic SAML 2.0 provider — help us set up SSO for Snowflake."
- "Restrict our business users to only access Snowflake Intelligence, not Snowsight."
- "Add a Snowflake Intelligence tile to our Okta app launcher."

**Example prompts**
```
Set up Okta SSO for Snowflake
Configure Microsoft Entra ID as our identity provider with SCIM
Set up generic SAML 2.0 SSO for Snowflake
Restrict business users to only access Snowflake Intelligence
Add the Snowflake Intelligence tile to our Okta app launcher
```

**Depth behind it:** 11 supporting files (9 workflow `.md` files: `okta-sso`, `entra-sso`, `generic-saml`, `advanced-scenarios`, `snowflake-allowed-interfaces`, `okta-allowed-interfaces`, `entra-allowed-interfaces`, `add-snowflake-intelligence-tile`, `okta-api-token-setup`; 2 `skill_metadata` files), no sub-skills.

**Prerequisites & caveats:** `ACCOUNTADMIN` role for creating security integrations; admin access to the IdP admin console; IdP API token stored as a secret for the Automated API method. The agent must not install CLI tools, SDKs, or PowerShell modules, and must not sign in to any IdP on behalf of the user.

**Pairs with:** `manage-authentication-policy`, `cortex-secrets`

---

### `key-and-secret-management`

> Routes Tri-Secret Secure (TSS) and customer-managed key (CMK) requests to the `tri-secret-secure` sub-skill, and handles periodic data rekeying by directing to Snowflake documentation for the `PERIODIC_DATA_REKEYING` account parameter.

**Snowflake surface it drives:** TSS `SYSTEM$` functions (CMK status checks, registration, activation, deactivation, key rotation — exact functions defined in `tri-secret-secure/SKILL.md`), `PERIODIC_DATA_REKEYING` account parameter (Enterprise Edition+)

**What it accelerates**
- TSS lifecycle routing: maps each CMK operation (check status, register, activate standard/Postgres/private-connectivity, deactivate, rotate) to the correct sub-skill workflow without requiring the user to know which `SYSTEM$` function to call.
- Change history review: the `tri-secret-secure/change-history` sub-sub-skill surfaces CMK change history via a dedicated workflow.
- Periodic rekeying disambiguation: immediately separates `PERIODIC_DATA_REKEYING` (a standalone account parameter) from TSS/CMK operations and points to the correct documentation, preventing confusion between the two features.

**Representative use cases**
- "Check the status of our Tri-Secret Secure configuration."
- "Register and activate a customer-managed key for BYOK."
- "We need to rotate our CMK after a key compromise."
- "Enable periodic data rekeying for our Enterprise account."
- "Show me the CMK change history for the past 90 days."

**Example prompts**
```
Check the status of our Tri-Secret Secure configuration
Register and activate a customer-managed key
Rotate our CMK after the key was compromised
Enable periodic data rekeying for Enterprise Edition
Show me the CMK change history
```

**Depth behind it:** 2 supporting files (2 sub-skill `SKILL.md` files), 2 sub-skills (`tri-secret-secure`, `tri-secret-secure/change-history`).

**Prerequisites & caveats:** Enterprise Edition or higher for Tri-Secret Secure; `ACCOUNTADMIN` for all key management operations; an external KMS (AWS KMS, Azure Key Vault, or GCP Cloud KMS) must be configured as the CMK provider before activation. Periodic rekeying is handled by pointing to Snowflake public documentation, not via the TSS sub-skill.

**Pairs with:** `trust-center`, `manage-authentication-policy`

---

### `cortex-secrets`

> Enforces the Cortex Code credential workflow: silently checks `cortex secret list` before any command requiring a token or API key, injects stored secrets via the `VAR="<key>"` bash syntax, and directs users to `/secrets` as the only user-facing interface for credential storage.

**Snowflake surface it drives:** `cortex secret list` CLI, `/secrets` slash command (Cortex Code panel), inline `VAR="<key>" cmd` injection syntax (resolved client-side, value never enters transcript)

**What it accelerates**
- Credential hygiene: intercepts any attempt to paste secrets in chat with an immediate warning and `/wipe-session` recommendation, then routes to `/secrets` for proper storage.
- Secret discovery: checks existing stored secrets before prompting the user to add a new one — reducing redundant setup and friction.
- Auth error resolution: maps 401/403/EACCES errors directly to the check-then-inject workflow rather than asking the user to manually configure environment variables.

**Representative use cases**
- "I need to run a command that requires a GitHub token — how do I provide it securely?"
- "I keep getting 401 errors when this API command runs."
- "How do I store my Snowflake API key in Cortex Code?"
- "What credentials are available in my current session?"

**Example prompts**
```
How do I provide my API key without exposing it in the chat?
I'm getting a 401 error — help me fix the auth for this curl command
Store my GitHub token for use in this session
What secrets are available in my current Cortex Code session?
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** Cortex Code CLI required; user must have stored or be willing to store secrets via `/secrets`. Session-scoped secrets are in-memory and expire when the session ends; user-scoped secrets persist in the OS keychain. This skill never shows the `VAR="<key>"` injection syntax or `cortex secret` commands to the user — those are agent-internal mechanics.

**Pairs with:** `setup-snowflake-sso`, `guardrails-guide`

---

### `guardrails-guide`

> Walks the user through creating, activating, and troubleshooting Restricted Session Scope (RSS) objects via the `/guardrails` panel, to limit which SQL operations and Snowflake roles the Cortex Code agent session may assume.

**Snowflake surface it drives:** `CREATE RESTRICTED SESSION SCOPE`, `ALTER RESTRICTED SESSION SCOPE`, `DROP RESTRICTED SESSION SCOPE`, `USER$<USERNAME>.RSS` schema (personal database), `SYS_CONTEXT('SNOWFLAKE$SESSION', 'ACTIVE_RESTRICTED_SESSION_SCOPES')`, `/guardrails` Cortex Code panel, `cortex --with-restricted-session-scope=<name>` CLI flag

**What it accelerates**
- RSS setup: removes DDL syntax lookup for `CREATE RESTRICTED SESSION SCOPE` YAML, handles the most common errors (`extend` keyword not supported, misidentified role names for read-only intent), and covers the mid-session activation path via `/guardrails`.
- Error diagnosis: recognizes "Restricted session scope" in SQL error messages and immediately routes to scope inspection via `SYS_CONTEXT`, preventing wasted time on role switches and GRANT statements (which cannot bypass RSS).
- Mid-session scope changes: clarifies that `/guardrails` panel is the only correct activation path — not `ALTER SESSION` — and that removing RSS via the panel preserves session variables and temp tables.

**Representative use cases**
- "Make this Cortex Code session read-only so the agent can't modify any tables."
- "Create a scope that prevents the agent from using the SECURITYADMIN role."
- "I'm getting a 'Restricted session scope' error — what does the active scope allow?"
- "Remove the RSS restriction without losing my session variables or temp tables."
- "Start Cortex Code with a read-only scope every time."

**Example prompts**
```
Make this session read-only so the agent only runs SELECT queries
Create a scope that blocks the agent from using SECURITYADMIN
Set up guardrails to prevent the agent from dropping tables
I'm getting "Restricted session scope" errors — what's the active scope blocking?
Remove the RSS restriction while keeping my session variables
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** Cortex Code CLI required; `USER$<USERNAME>.RSS` personal database schema is needed for named scope creation — scopes in other schemas do not auto-appear in the `/guardrails` panel. The agent must never run `ALTER SESSION SET RESTRICTED_SESSION_SCOPE`; the only valid activation paths are the `/guardrails` panel (mid-session) and `--with-restricted-session-scope` (startup). Does not govern non-SQL tool restrictions (file writes, shell execution) — use `/permissions` for those.

**Pairs with:** `cortex-secrets`, `access-troubleshooter`

## Cost, Performance & Platform Operations

*Understanding spend, tuning compute, and running the account day to day.*

### `cost-intelligence`

> Answers "what am I spending credits on and why," and lets you create/manage the guardrails (budgets, quotas, anomaly monitors) that keep spend in check — all via `SNOWFLAKE.ACCOUNT_USAGE` and the `SNOWFLAKE.LOCAL`/`SNOWFLAKE.CORE` classes, never semantic views. This is a router that dispatches to six sub-skill groups.

**Snowflake surface it drives:** `SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY`, `QUERY_ATTRIBUTION_HISTORY`, `TAG_REFERENCES`, `ANOMALIES_DAILY`, `SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS`, `SNOWFLAKE.LOCAL.COST_INSIGHTS`, `SNOWFLAKE.CORE.BUDGET` (incl. `SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET`), `SNOWFLAKE.CORE.QUOTA`, `ALTER USER/WAREHOUSE ... SET TAG`, Cortex AI usage-history views (Snowflake CoCo, CoWork, Cortex Agents, Analyst, Search, AI Functions, REST API, Model Training, Provisioned Throughput, Guardrails).

**What it accelerates**
- Root-causing a cost spike: pulls trend, anomaly, and per-warehouse/user breakdowns instead of hand-built `METERING_HISTORY` joins.
- Setting up chargeback/showback: resolves tag FQNs, checks `allowed_values`, and correctly separates resource-level vs. user-level (fractional) attribution so costs aren't double-counted.
- Standing up spend guardrails: walks the class-instance syntax for budgets, quotas, and anomaly monitors (`SHOW SNOWFLAKE.CORE.BUDGET`, not `SHOW BUDGETS`) that trips up hand-written SQL.
- Attributing Cortex AI spend (CoCo, CoWork, Agents, Analyst, etc.) per product and per user-tag, including which products simply cannot be attributed per-user.
- Surfacing proactive waste-reduction insights (idle warehouses, never-queried tables, cold storage) with quantified credit impact.

**Representative use cases**
- "Why did our bill spike last week — what caused it?"
- "Set up a $5,000/month budget for the finance team's warehouses and alert them at 80%."
- "Which team is driving our Cortex Code / Cortex Analyst spend?"
- "Cap each user's AI credit spend at 50/month and block them if they go over."
- "What's driving our storage costs — anything I can archive or delete?"
- "Show me spend by cost-center tag across compute and AI."
- "Alert me if any account in the org has an unusual cost spike."

**Example prompts**
```
Why did our Snowflake costs go up this week compared to last?
Create a custom budget of 10,000 credits/month for the COST_CENTER=engineering tag with email alerts at 75%.
How much are we spending on Cortex Agents and Snowflake CoWork this month?
Set a per-user quota of 20 credits/day on AI Functions and notify admins at 90%.
What cost optimization insights do you have for unused resources?
```

**Depth behind it:** `37` supporting reference files, `24` sub-skills organized into 6 groups: `anomaly-insights` (plus nested `manage-monitors`, `notify-account-anomalies`, `notify-org-anomalies`, `view-anomalies`), `budget` (plus nested `activate`, `create`, `modify`, `status`), `cortex-ai`, `cost-insights` (plus nested `drill-down`, `overview`), `quota` (plus nested `create`, `custom-actions`, `cycle-start-actions`, `drop`, `notifications`, `status`, `view-exclusions`, `view-shared-resources`), `tag-attribution`.

**Prerequisites & caveats:** Most procedures need the `APP_USAGE_VIEWER`/`APP_USAGE_ADMIN` application role (or `ACCOUNTADMIN`); tag joins additionally need `GOVERNANCE_VIEWER`. `TAG_REFERENCES` has up to 120 min latency; `METERING_HISTORY` up to 180 min (6 hrs for cloud services). Budgets/quotas are class instances, not objects — `SHOW BUDGETS`/`SHOW QUOTAS` fail. Quotas cannot mix AI-credit and compute domains in one instance. `QUERY_ATTRIBUTION_HISTORY` (user-level attribution) excludes AI services, idle time, serverless, storage, and data transfer — never sum it with resource-level totals. Not for native-app cost (use `native-app-consumer`), org-wide dollar spend (use `billing`), or warehouse DDL (use `warehouse`).

**Pairs with:** `billing`, `warehouse`, `storage-lifecycle-policy`, `automation`, `data-governance`.

---

### `billing`

> Answers "how much am I spending in dollars/currency" at the organization level — contract terms, balances, invoices, and rates — as distinct from credit-based analytics. A router with two sub-skills.

**Snowflake surface it drives:** `SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY`, `REMAINING_BALANCE_DAILY`, `CONTRACT_ITEMS`, `RATE_SHEET_DAILY`, `SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS`.

**What it accelerates**
- Dollar spend analysis (by service type, by account, trends) without accidentally querying credit-only `METERING_HISTORY`.
- Contract lifecycle questions (start date, termination date, days remaining) with the correct column (`EXPIRATION_DATE` not `END_DATE`) and the mandatory 30-day renewal disclaimer baked in.
- Billing statement reconciliation ("total consumed") using the exact cumulative-from-contract-start query, avoiding the common mistake of scoping to a single month.
- Consumption invoice lookups, status (overdue/unpaid), and PDF content parsing — kept separate from marketplace invoices.

**Representative use cases**
- "Which services cost the most money this quarter?"
- "When does our Snowflake contract expire?"
- "What's our remaining capacity balance?"
- "Show me our outstanding/overdue invoices."
- "Reconcile this month's billing statement against our usage."
- "What's our effective compute rate compared to last quarter?"

**Example prompts**
```
Which services cost the most money in dollars this month?
When does our Snowflake contract terminate, and how many days are left?
What is our remaining balance broken down by capacity, rollover, and free usage?
Show me all unpaid or overdue consumption invoices.
Reconcile total consumed against our January billing statement.
```

**Depth behind it:** `7` supporting reference files, `2` sub-skills (`billing-queries`, `odss-invoices`).

**Prerequisites & caveats:** `billing-queries` requires the `ORGADMIN` role (falls back to `organization-management` for access troubleshooting). `odss-invoices` requires `ACCOUNTADMIN` and only reads `SNOWFLAKE.BILLING.ODSS_INVOICE_DOCUMENTS` — never `ORGANIZATION_USAGE.ODSS_INVOICE_DOCUMENTS`, which has different columns. Never use `METERING_HISTORY` for any dollar question — it has no currency column. Not for credit-based analysis (use `cost-intelligence`) or warehouse DDL (use `warehouse`).

**Pairs with:** `cost-intelligence`, `organization-management`.

---

### `organization-management`

> Router for everything at the Snowflake organization (multi-account) control plane: account lifecycle, org users, replication, and executive-level org insights — distinct from single-account cost or billing analytics.

**Snowflake surface it drives:** account/org control-plane DDL (`CREATE/ALTER ACCOUNT`, reader accounts, client redirect/failover, replication groups), `ORGANIZATION_USER`/`ORGANIZATION_USER GROUP` DDL, `SNOWFLAKE.ORGANIZATION_USAGE` views, Org Hub insights, `GLOBALORGADMIN` role management.

**What it accelerates**
- Account inventory and lifecycle: creating/altering accounts, edition/region changes, reader accounts, disaster-recovery client redirect, cross-account replication — without hand-tracing the control-plane SQL surface.
- Organization user management: creating org users/groups, importing groups into accounts, and resolving import conflicts (duplicate `login_name`).
- Executive-level org insights (Org Hub): 30-day org summaries spanning cost, security posture, reliability, auth posture, storage growth, and Trust Center coverage in one pass.
- Answering "which `ORGANIZATION_USAGE` view do I need and what role does it require" without guesswork.
- `GLOBALORGADMIN` role auditing (who has it, how to enable/disable it).

**Representative use cases**
- "Create a new Snowflake account in the EU region on Business Critical edition."
- "Give me a 30-day executive summary of my organization."
- "Import this organization user group into our production account — it's showing conflicts."
- "Set up client redirect for disaster recovery failover."
- "How many accounts do we have and what editions are they on?"
- "Who currently holds GLOBALORGADMIN?"

**Example prompts**
```
Give me a 30-day summary of my organization covering cost and security.
List all accounts in my organization with their editions and regions.
Create a reader account for sharing data with a non-Snowflake customer.
Import organization user group SALES_TEAM into account PROD_ACCT — it shows conflicts.
Who has globalorgadmin in my organization?
```

**Depth behind it:** `6` supporting reference files, `15` sub-skills: `account-lifecycle`, `accounts`, `client-redirect`, `globalorgadmin`, `org-db` (plus nested `org-db-discovery`, `org-tags`), `org-hub`, `org-usage-view`, `organization-users` (plus nested `create`, `import`, `troubleshoot`), `reader-accounts`, `replication-setup`, `third-party-accounts`.

**Prerequisites & caveats:** Requires loading `references/global_guardrails.md` before any operation. This router provides no implementation details itself — it never proceeds without loading a matching sub-skill.

**Pairs with:** `billing`, `cost-intelligence`, `security-investigation`, `setup-snowflake-sso`.

---

### `warehouse`

> Routes warehouse configuration and DDL questions (Gen2, Adaptive, sizing, performance tuning) to the right sub-skill — explicitly not the place for warehouse cost analytics.

**Snowflake surface it drives:** `CREATE/ALTER WAREHOUSE`, `GENERATION = '2'`, `WAREHOUSE_TYPE = 'ADAPTIVE'`, `MAX_QUERY_PERFORMANCE_LEVEL`, `QUERY_THROUGHPUT_MULTIPLIER`, `SHOW WAREHOUSES`, `RESOURCE_CONSTRAINT`.

**What it accelerates**
- Deciding and executing Gen1→Gen2 conversion: runs the mandatory region check, generates the `ALTER WAREHOUSE ... SET GENERATION = '2'` live-migration statement, and explains dual-billing during the transition.
- Adaptive warehouse creation/conversion/tuning: explains `MAX_QUERY_PERFORMANCE_LEVEL`/`QUERY_THROUGHPUT_MULTIPLIER` and pre-empts common misconceptions (e.g., "adaptive loses memory mid-query" — false) with an explicit prohibited-speculation list.
- Warehouse-type triage: looks up a named warehouse's actual `type`/`generation`/`size` before giving advice, so an INTERACTIVE or SNOWPARK-OPTIMIZED warehouse never gets Gen2 advice by mistake.
- Correctly separates "should I convert this warehouse" (uses Snowsight recommendations, not blanket eligibility) from actual DDL execution.
- Surfaces authoritative Gen1 vs Gen2 vs Adaptive credit-per-hour rates by cloud provider, citing the Credit Consumption Table.

**Representative use cases**
- "Should I convert my analytics warehouse to Gen2?"
- "My DML operations (MERGE/UPDATE/DELETE) are slow — what can I do?"
- "Create an adaptive warehouse for our ETL workload."
- "Is my X5LARGE warehouse eligible for Gen2?"
- "What's the credit-per-hour rate for a Gen2 XLARGE on Azure vs AWS?"
- "Why is my warehouse resuming slower since converting to Gen2?"

**Example prompts**
```
Convert my ANALYTICS_WH warehouse to Gen2.
Should I use an adaptive warehouse for my ETL pipeline?
What are the Gen2 credit rates for a MEDIUM warehouse on AWS?
My MERGE statements are slow on warehouse REPORTING_WH — what should I do?
Is my Snowpark-optimized warehouse eligible for Gen2?
```

**Depth behind it:** `7` supporting reference files, `2` sub-skills (`adaptive-warehouse`, `gen2-warehouse`).

**Prerequisites & caveats:** Region support for Gen2/Adaptive must be checked via `SELECT CURRENT_REGION()` before any recommendation or conversion — non-negotiable per the skill. Gen2 does not support X5LARGE/X6LARGE or Snowpark-optimized warehouse types; Adaptive is a distinct warehouse type, not a STANDARD generation. Explicitly frames both Gen2 and Adaptive as performance features, not cost-saving features. Interactive-warehouse questions route out to `snowflake-interactive`; warehouse cost/credit-spend questions route out to `cost-intelligence`.

**Pairs with:** `snowflake-interactive`, `cost-intelligence`, `workload-performance-analysis`.

---

### `workload-performance-analysis`

> Diagnoses why SQL queries and warehouses run slow — spilling, pruning, caching, clustering, QAS eligibility — via `ACCOUNT_USAGE`, as a unified single entry point across 11 entity types and 3 depths of analysis.

**Snowflake surface it drives:** `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, `QUERY_ACCELERATION_ELIGIBLE`, plus pruning/spilling/cache/clustering-related account-usage columns, all wrapped in a bundled semantic model (`semantic_model/default.yaml`) of verified queries.

**What it accelerates**
- Diagnosing a specific slow query, warehouse, table, or stored-procedure call tree (including recursive child-query resolution for `CALL` statements) without hand-writing `ACCOUNT_USAGE` joins.
- Cross-cutting bottleneck analysis: spilling (local vs. remote), partition pruning, cache hit rate, clustering-key candidates, Search Optimization Service candidates, and Query Acceleration Service eligibility — each with summary → detection → recommendation phases.
- Multi-query / query-set analysis: accepts 2–1000 query_ids, a `QUERY_HISTORY` WHERE-fragment, or a list of parameterized hashes and analyzes them as one workload.
- Framing recommendations against the workload's actual SLA (speed vs. cost priority) instead of a one-size-fits-all answer.
- Detecting and routing UI-originated context (Query History list, Query Details, Performance Explorer) automatically via system-reminder markers.

**Representative use cases**
- "Why is this query slow?" (with a query ID)
- "Which warehouses are spilling to disk the most?"
- "Is table X a good candidate for a clustering key or search optimization?"
- "What's causing this stored procedure call to take so long?"
- "Give me a health check across all performance dimensions for my account."
- "Analyze these 50 query_ids as one workload."

**Example prompts**
```
Why is query 01b24bb0-0007-9627-0000-0001234abcde slow?
Which warehouses have the worst partition pruning this week?
Recommend clustering keys for SALES.PUBLIC.ORDERS.
Diagnose the stored procedure call in query_id <id> including its child queries.
Run an account-level performance health check.
```

**Depth behind it:** `12` supporting files (11 reference docs + `semantic_model/default.yaml`), `36` sub-skills — an 11-entity × 3-phase (`summary`/`detection`/`recommendation`) matrix for `account`, `cache`, `pruning`, `qas`, `query`, `query-pattern`, `query-set`, `spilling`, `stored-procedure`, `table`, `warehouse`, plus 3 UI-only summary sub-skills (`ui-performance-explorer`, `ui-query-details`, `ui-query-history`).

**Prerequisites & caveats:** Requires `SNOWFLAKE.USAGE_VIEWER` (or `OBJECT_VIEWER`/`GOVERNANCE_VIEWER` depending on view). `ACCOUNT_USAGE` latency: up to 45 min for `QUERY_HISTORY`, up to 4 hours for pruning views. Historical-only — cannot predict future performance or estimate actual clustering/SOS benefit; limited visibility into hybrid tables. Internal `COMPUTE_SERVICE_WH_*` warehouses are excluded from user-facing recommendations. Not for cost/credits (use `cost-intelligence`), access audit (use `data-governance`), or warehouse type/DDL decisions (use `warehouse`).

**Pairs with:** `warehouse`, `cost-intelligence`, `snowflake-interactive`.

---

### `snowflake-interactive`

> Sets up and troubleshoots Snowflake Interactive Tables and Interactive Warehouses — the low-latency, high-concurrency path for dashboards, APIs, and agentic queries — including zero-copy interactive analytics directly on standard or Iceberg tables.

**Snowflake surface it drives:** Interactive tables (static and dynamic with `TARGET_LAG`), `CREATE WAREHOUSE ... WAREHOUSE_TYPE = 'INTERACTIVE'`, fallback-warehouse configuration for mixed workloads, `SHOW WAREHOUSES`/`SHOW TABLES` filtering by `type`, zero-copy querying of standard/Iceberg tables from an interactive warehouse.

**What it accelerates**
- Choosing between zero-copy interactive analytics (query existing tables directly) vs. converting to true interactive tables — presented as two paths in a dedicated getting-started flow.
- Creating and tuning interactive tables/warehouses, including clustering-key selection specific to interactive workloads.
- Working around the lack of native UPDATE/DELETE on interactive tables via the documented standard+dynamic table pattern.
- Diagnosing the hard 5-second query timeout, fallback-warehouse retry behavior, and cache-warming issues specific to this warehouse type.
- Benchmarking and comparing interactive vs. standard query performance.

**Representative use cases**
- "Our Streamlit dashboard is too slow — can interactive tables help?"
- "Set up an interactive warehouse so our API backend responds faster."
- "Can I query my existing Iceberg table with an interactive warehouse without copying it?"
- "How do I do UPDATE/DELETE on an interactive table?"
- "My interactive queries keep timing out at 5 seconds."
- "Which columns should I cluster my interactive table on?"

**Example prompts**
```
How do I make my dashboard queries faster using interactive tables?
Create an interactive warehouse with a fallback warehouse for mixed workloads.
Can I run an interactive warehouse directly on my existing Iceberg table?
My interactive table query keeps hitting the 5-second timeout — why?
What clustering key should I use for my interactive table?
```

**Depth behind it:** `18` supporting files (5 reference docs + a 13-file test harness under `tests/`), `7` sub-skills: `clustering`, `getting-started`, `interactive-table`, `query`, `troubleshoot`, `update-delete`, `warehouse`.

**Prerequisites & caveats:** Interactive tables do not support UPDATE/DELETE directly (use the standard+dynamic table pattern instead). Query timeout is a hard 5 seconds on an interactive warehouse; queries exceeding it are retried on a fallback warehouse if one is configured, otherwise they fail. Performance on Iceberg tables may be lower than on standard tables. Zero-copy interactive analytics on standard/Iceberg tables is Public Preview. All mutations require explicit user approval before execution; read-only queries can run freely.

**Pairs with:** `warehouse`, `workload-performance-analysis`, `dynamic-tables`.

---

### `storage-lifecycle-policy`

> Creates and manages automated data-tiering rules — expire old rows outright, or archive them to cheaper COOL/COLD storage before expiring — to cut storage costs without manual cleanup jobs.

**Snowflake surface it drives:** `CREATE STORAGE LIFECYCLE POLICY`, `ALTER TABLE ... ADD/DROP STORAGE LIFECYCLE POLICY`, `ARCHIVE_TIER` (COOL/COLD), `CREATE TABLE ... FROM ARCHIVE OF`, `SYSTEM$GET_TABLE_ARCHIVE_METADATA`, `INFORMATION_SCHEMA.POLICY_REFERENCES` / `STORAGE_LIFECYCLE_POLICY_HISTORY`, `SNOWFLAKE.ACCOUNT_USAGE.STORAGE_LIFECYCLE_POLICY_HISTORY`.

**What it accelerates**
- Picking expiration-only vs. archive-then-expire and generating the matching `CREATE STORAGE LIFECYCLE POLICY` + `ALTER TABLE ADD` pair in one step (a policy has no effect until attached — the skill enforces both statements together).
- Identifying which tables are worth archiving in the first place, by pulling `COLD_FILE_STORAGE` candidates from `cost-intelligence`'s cost-insights procedure.
- Estimating archive-retrieval cost and time before running `CREATE TABLE ... FROM ARCHIVE OF`, using `EXPLAIN`'s `bytesAssigned` plus per-region, per-tier retrieval-rate tables (AWS/Azure/GCP) and a warehouse-sizing formula so the retrieval finishes in ~30 minutes.
- Monitoring policy execution history and verifying attachment without guessing at `INFORMATION_SCHEMA` function signatures.

**Representative use cases**
- "This table is huge and expensive — can we archive old rows to cheaper storage?"
- "Delete/purge rows older than 2 years from this table automatically."
- "What will it cost to retrieve this archived data back into a queryable table?"
- "Which tables are good candidates for archival?"
- "Show me the execution history of our storage lifecycle policies."

**Example prompts**
```
Create an archival policy on ORDERS that moves rows older than 1 year to COOL tier and expires them after 3 years.
Which of my tables are good candidates for a storage lifecycle policy?
Estimate the cost of retrieving archived data from EVENTS_LOG between 2023-01-01 and 2023-06-30.
Show me the storage lifecycle policy execution history for the last 7 days.
Remove the storage lifecycle policy from CUSTOMER_HISTORY.
```

**Depth behind it:** `0` supporting files, no sub-skills.

**Prerequisites & caveats:** One policy per table; the archive tier (COOL vs COLD) is permanent once assigned and cannot be changed. COOL requires a minimum 90-day archive period (AWS/Azure/GCP); COLD requires a minimum 180-day period and is AWS/GCP only, with retrieval taking up to 48 hours. Archived rows can never be queried directly — always requires `CREATE TABLE ... FROM ARCHIVE OF`. Not supported on Iceberg tables. Policies run on a daily (~24 hr) Snowflake-managed schedule; subqueries in the policy body may cause errors. Candidate discovery depends on `cost-intelligence`'s `APP_USAGE_VIEWER`/`APP_USAGE_ADMIN` access.

**Pairs with:** `cost-intelligence`, `iceberg` (for contrast — not supported there), `warehouse`.

---

### `automation`

> Schedules recurring Cortex Code runs as Snowflake `AGENT TASK`s — cron-like unattended jobs that can query Snowflake and, via attached MCP servers, read/write Slack, Jira, Gmail, and Google Drive too. Internal/meta skill: it's about operating Cortex Code itself, not a Snowflake data feature.

**Snowflake surface it drives:** `CREATE AGENT TASK` (via the `cortex automation` CLI, not hand-written SQL), Restricted Session Scope (`SNOWFLAKE$DATA_READ_WITH_AI` and custom RSS objects), `SYSTEM$SEND_EMAIL` + `NOTIFICATION INTEGRATION`, `SHOW MCP SERVERS IN ACCOUNT` / `SHOW EXTERNAL MCP SERVERS IN ACCOUNT`, Snowflake `SECRET` objects (for GitHub PAT injection).

**What it accelerates**
- Turning a one-off report/check into a scheduled job without hand-authoring `AGENT TASK` SQL or cron syntax — the CLI parses natural-language schedules ("weekdays at 9am", "every 60 minutes") into the right task(s).
- Picking the correct delivery mechanism (transcript, MCP server, or email) and pre-flighting it — e.g., discovering that email requires dropping Restricted Session Scope entirely, and confirming that trade-off with the user before proceeding.
- Resolving real MCP tool names/ids ahead of time so an unattended fire never stalls on "which channel did you mean."
- Authoring prompts with the invariants unattended runs need (no clarifying questions, hardcoded ids, a machine-parseable status line).
- Debugging a fire that "succeeded" but produced no visible side effect, via `cortex automation doctor` + `cortex conversations transcript`.

**Representative use cases**
- "Email me a daily summary of yesterday's warehouse credit spend."
- "Every morning, post a digest of my Slack mentions and DMs to a channel."
- "Alert me automatically if any table hasn't refreshed in 24 hours."
- "Run this SQL report every Monday at 9am and save the results."
- "Watch for pipeline/task failures and summarize them weekly."
- "Give me a weekly review of my own Cortex Code session friction."

**Example prompts**
```
Schedule a daily warehouse cost watch report at 8am ET.
Create an automation that posts a morning Slack digest of my mentions and DMs.
Set up a weekly SQL report on pipeline failures every Monday at 9am.
Automatically check for stale/silent tables every morning and alert me.
Show me the run history for my warehouse-cost-watch automation.
```

**Depth behind it:** `7` supporting template reference files (`daily-coco-usage`, `data-freshness-checker`, `metric-anomaly-tracker`, `morning-slack-digest`, `pipeline-failure-summary`, `scheduled-sql-report`, `warehouse-cost-watch`), no sub-skills.

**Prerequisites & caveats:** Account needs `AGENT TASK` enabled (one-time `ACCOUNTADMIN` step). Fires run in a Snowflake-managed sandbox with no local filesystem and no local MCP servers — only built-in tools plus explicitly attached Snowflake-managed MCP servers. Every fire is read-only by default (bound to `SNOWFLAKE$DATA_READ_WITH_AI`); `SYSTEM$SEND_EMAIL` requires dropping that entirely (`--without-read-only --force`), which must be explicitly confirmed with the user first. Email recipients must be verified Snowflake users in-account, or Gmail MCP is the only path for external addresses. WAREHOUSE, COMMENT, ERROR_INTEGRATION, and ROLE/EXECUTE AS are explicitly not parameters on this surface.

**Pairs with:** `cost-intelligence`, `workload-performance-analysis`, `storage-lifecycle-policy`, `cortex-code-guide`.

## Sharing, Collaboration & Marketplace

*Getting data and AI products out of the account and into partners, customers and the Marketplace.*

### `sharing`

> Routes an open-ended or comparison sharing request to the right Snowflake sharing construct — Secure Data Sharing, Declarative Sharing, Native Apps, or Data Clean Rooms — by asking up to two questions.

**Snowflake surface it drives:** `CREATE SHARE`, `APPLICATION PACKAGE TYPE=DATA`, Native App Framework, DCR Collaboration API, `GRANT USAGE`, `GRANT SELECT`

**What it accelerates**
- Removes decision paralysis when a user doesn't know which construct to use: a two-question guide routes them to the right skill without requiring prior Snowflake knowledge.
- Surfaces the trade-off between SDS, Declarative Sharing, Native Apps, and DCR in plain language, eliminating the need to read four sets of documentation.
- Infers answers from context (e.g., "share with my partner account" skips Q1), reducing friction to a single question in many cases.
- Handles same-account sharing inline with RBAC SQL, so simple grant requests never reach a specialist sub-skill.

**Representative use cases**
- "How do I share my data with another Snowflake account?"
- "What's the best way to share my tables — secure share or native app?"
- "I want to share a notebook and a UDF together — what are my options?"
- "We're running joint analysis with a partner — what should we use?"
- "I'm not sure whether to use manifests or native apps."
- "Share this table with the ANALYST role in my account."

**Example prompts**
```
How do I share data with another Snowflake account?
What are my options for sharing data and applications?
Is declarative sharing better than a native app for distributing a UDF?
We need to do joint analysis with a partner without exposing raw data — what should we use?
Share this table with the SYSADMIN role in my account
```

**Depth behind it:** 3 supporting files, no sub-skills. After routing, invokes `data-sharing`, `declarative-sharing`, `native-app-provider`, or `data-cleanrooms`.

**Prerequisites & caveats:** None stated for the router itself. Cross-account sharing requires appropriate account-level privileges enforced by the target sub-skill. RBAC inline path requires the target role name and object names before generating SQL.

**Pairs with:** `data-sharing`, `declarative-sharing`, `native-app-provider`, `data-cleanrooms`

---

### `data-sharing`

> Creates and troubleshoots Snowflake Secure Data Sharing constructs — direct shares, external Marketplace listings, organization listings, reshared imported databases, and external (Iceberg/S3) data shares.

**Snowflake surface it drives:** `CREATE SHARE`, `CREATE EXTERNAL LISTING`, `CREATE ORGANIZATION LISTING`, `ALTER LISTING ... AS $$...$$`, `GRANT SELECT ON TABLE/VIEW/SEMANTIC VIEW TO SHARE`, `GRANT USAGE ON DATABASE/SCHEMA TO SHARE`, `GET_OBJECT_REFERENCES`, `GRANT REFERENCE_USAGE`, `SHOW SHARES`, `DESCRIBE SHARE`, `SHOW GRANTS TO SHARE`, `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES`

**What it accelerates**
- Enforces mandatory role preflight before every `CREATE SHARE` or `CREATE LISTING`, preventing mid-workflow "insufficient privileges" failures.
- Enforces the correct grant order (database → schema → objects), removing the "Share does not currently have a database" error.
- Runs `GET_OBJECT_REFERENCES` automatically before view grants, preventing silent consumer access failures from missing `REFERENCE_USAGE`.
- Routes resharing of imported databases and ULLs to a dedicated sub-skill with the correct secure-view wrapper, distinguishing it from the `REFERENCE_USAGE` path.
- Surfaces candidate roles via `GRANTS_TO_ROLES` or `SHOW GRANTS ON ACCOUNT` when a privilege check fails, giving a pick-list instead of requiring admin escalation.

**Representative use cases**
- "Share a table with a partner's Snowflake account as a direct share."
- "Publish my dataset as an external listing on the Snowflake Marketplace."
- "Share data across all accounts in my organization via the internal marketplace."
- "Reshare a table I received from a provider's listing."
- "Share an Iceberg table in S3 without copying the data."
- "Debug why my consumers can't query the shared view."

**Example prompts**
```
Create a direct share of my SALES.ORDERS table with account MYPARTNER
Publish my dataset as an external listing on the Snowflake Marketplace
Share data across all accounts in my organization
My consumers can't query the shared view — debug it
Reshare data I received from a listing to another account
```

**Depth behind it:** 13 supporting files, 3 sub-skills (`run-listing-custom-validation`, `create-internal-listing-with-custom-validation`, `create-internal-listing-custom-validation-rules`). Workflow `.md` files cover create, external-listing, org-listing, reshare-imported, external-data, and debug paths.

**Prerequisites & caveats:** `CREATE SHARE` required for all share operations. `CREATE LISTING` required for external listings. `CREATE ORGANIZATION LISTING` for org listings. `MANAGE LISTING AUTO FULFILLMENT` for cross-region auto-fulfillment. `GRANT SELECT ON ALL VIEWS IN SCHEMA` is not supported for shares — views must be granted individually. Reader accounts not supported with org listings. Not for migrating existing shares — use dedicated migration skills.

**Pairs with:** `sharing`, `attach-ai-products-to-share`, `listing-observability`, `internal-marketplace-org-listing`

---

### `declarative-sharing`

> Builds and releases `APPLICATION PACKAGE TYPE=DATA` (declarative shares / data apps) that bundle tables, views, agents, semantic views, workspaces, and UDFs into a versioned, consumer-installable product without a setup script.

**Snowflake surface it drives:** `CREATE APPLICATION PACKAGE ... TYPE = DATA`, `ALTER APPLICATION PACKAGE ... RELEASE LIVE VERSION`, `CREATE APPLICATION ... FROM APPLICATION PACKAGE`, `CREATE AGENT`, `COPY FILES INTO snow://package/`, `PUT file://`, `LIST snow://package/`, `ALTER APPLICATION ... UPGRADE`, `CREATE ORGANIZATION LISTING`, manifest.yml declarative format, `SHOW GRANTS ON ACCOUNT`

**What it accelerates**
- Auto-generates correct manifest.yml, avoiding wrong keys (`app_roles:` instead of `roles:`, `setup_script:`, FQN references in UDFs) that silently break consumer installs.
- Handles all three CoCo environments (Workspaces, CLI, non-Workspaces) with the appropriate `COPY FILES` vs. `PUT` path and correct `FILE_FORMAT` flags.
- Enforces schema separation between shared-by-copy (agents, UDFs) and shared-by-reference (tables, views) objects, preventing `RELEASE LIVE VERSION` failures.
- Guides notebook-to-workspace migration, including role-set grouping decisions and confirmation gates before irreversible file deletions.
- Converts existing traditional data shares to declarative packages via `workflows/manifest-from-share.md`.

**Representative use cases**
- "Bundle my tables, a semantic view, and a Cortex Agent into a single installable data product."
- "Create a versioned share so consumers upgrade automatically."
- "Migrate my existing secure data share to a declarative share."
- "Combine three data shares into one package that consumers install once."
- "Share a next-gen notebook along with my analytics tables."
- "A consumer wants to switch from my old share to my new declarative app with zero downtime."

**Example prompts**
```
Create a data app that bundles my ANALYTICS tables and a Cortex Agent
Migrate my existing data share to a declarative share
Convert my three secure shares into a single installable package
Add a semantic view and a notebook to my existing application package
How does a consumer migrate from my old share to my new declarative app?
```

**Depth behind it:** 7 supporting files, no sub-skills. Workflow files: `manifest-from-share.md`, `consumer-share-migration.md`, `references/create-objects.sql`, `references/manifest.yml`, `references/package-release.sql`, `references/troubleshooting.md`.

**Prerequisites & caveats:** `CREATE APPLICATION PACKAGE` account-level privilege required. Views must be `SECURE`. Agents with cross-database tools, custom warehouses, or `query_timeout` cannot be shared. Application package name and database name share the same namespace — a database named `X` blocks `CREATE APPLICATION PACKAGE X`. `GRANT REFERENCE_USAGE` is never needed for declarative sharing. Legacy notebooks are deprecated; next-gen notebooks via workspaces are the supported path. 1,000-object limit in `shared_content`.

**Pairs with:** `sharing`, `attach-ai-products-to-share`, `agent-studio`, `internal-marketplace-org-listing`

---

### `internal-marketplace-org-listing`

> Creates and publishes organizational listings on Snowflake's Internal Marketplace to share data products (tables, views, semantic views, agents, Cortex Search) with other accounts inside the same Snowflake organization.

**Snowflake surface it drives:** `CREATE SHARE`, `CREATE ORGANIZATION LISTING`, `ALTER LISTING ... AS $$...$$`, `GRANT USAGE ON DATABASE/SCHEMA TO SHARE`, `GRANT SELECT ON TABLE/VIEW/SEMANTIC VIEW TO SHARE`, `SHOW AVAILABLE INTERNAL MARKETPLACE CONFIGS`, `SHOW AVAILABLE ORGANIZATION PROFILES`, `SHOW ACCOUNTS`, `RESULT_SCAN`, `SELECT CURRENT_REGION()`

**What it accelerates**
- Auto-generates listing title, description, and data dictionary from the shared objects, eliminating YAML manifest authoring for standard tables and views.
- Enforces the database → schema → object grant order, preventing the "Share does not currently have a database" failure.
- Queries `SHOW AVAILABLE INTERNAL MARKETPLACE CONFIGS` to surface required custom attributes only when present, avoiding unnecessary prompts.
- Validates account names against `SHOW ACCOUNTS` with `RESULT_SCAN` to handle truncated results in large organizations.
- Configures access scoping (all accounts, specific accounts, role-based, or request-and-approve flow) from a single intent description.

**Representative use cases**
- "Publish my SALES tables to the internal marketplace for all org accounts."
- "Share my Cortex Agent with the DATA_SCIENCE account in our organization."
- "Create an internal data product that requires approval before access is granted."
- "Share my analytics tables with the ACCOUNTADMIN role in our HR account."
- "Set up cross-region auto-fulfillment for my internal listing."

**Example prompts**
```
Share my tables via the internal marketplace to all organization accounts
Create a data product listing for my ANALYTICS.PUBLIC schema
Publish my Cortex Agent to the internal marketplace for the FINANCE account
Create an org listing that requires request-and-approve access
Share my semantic view as a data product with cross-region support
```

**Depth behind it:** 5 supporting files, 1 sub-skill (`certified-object-recommender`). Reference files: `manifest-reference.md`, `templates.md`, `errors.md`.

**Prerequisites & caveats:** `CREATE SHARE` + `CREATE ORGANIZATION LISTING` on account required. `MANAGE LISTING AUTO FULFILLMENT` for cross-region. Reader accounts not supported. Native App listings don't support target roles. Each share can be attached to one listing only. Cortex Agents cannot be shared if they use a custom warehouse, have tools in different databases, use `query_timeout`, or have an invalid spec. Not for migrating existing direct shares, personalized listings, or PDX listings.

**Pairs with:** `data-sharing`, `attach-ai-products-to-share`, `listing-observability`, `agent-studio`

---

### `marketplace-provider`

> Routes Snowflake Marketplace provider tasks — profile setup, listing creation for all product types (Data Share, Native App, DSNA, Connected App, CKE, Cortex Agent, Semantic View), monetization, and provider success — to the correct sub-skill.

**Snowflake surface it drives:** Provider Studio UI, `CREATE LISTING`, `CREATE SHARE`, `APPLICATION PACKAGE`, `ALTER LISTING`, `DISTRIBUTION = EXTERNAL`, `SYSTEM$IS_GLOBAL_DATA_SHARING_ENABLED_FOR_ACCOUNT`, security scan, functional review process, Cortex AI Ready status, SPN validation

**What it accelerates**
- Eliminates routing ambiguity across five listing types (Data Share, Native App, DSNA, Connected App, AI-ready combinations) by detecting product type from the user message and loading the precise sub-skill immediately.
- Provides review-flow timelines (metadata ~1 day, functional up to 14 days for apps, SPN validation for Connected Apps) so providers understand the publication lifecycle.
- Handles the "AI objects are not standalone listings" rule — an "attach an agent" request routes through the data-products parent to the agent sub-skill automatically.
- Prevents the free-to-paid in-place conversion mistake: a new paid listing must be created; the skill confirms this before starting the creation flow.

**Representative use cases**
- "I want to become a Snowflake Marketplace provider — where do I start?"
- "Create a listing for my dataset on the Marketplace."
- "Build a Native App to distribute to Snowflake customers."
- "Add a Cortex Agent to my Marketplace listing to make it AI-Ready."
- "Set up paid listing monetization for my data product."
- "Check my invoice or payout status."

**Example prompts**
```
How do I become a Snowflake Marketplace provider?
Create a Marketplace listing for my dataset
Publish a Native App to the Snowflake Marketplace
Add a semantic view to my existing data share listing
Set up monetization for my Marketplace listing
```

**Depth behind it:** 26 supporting files, 14 sub-skills (`marketplace-provider-profile`, `marketplace-provider-listings`, `marketplace-provider-data-products`, `create-dataset-listing`, `create-native-app-listing`, `create-dsna-listing`, `create-connected-app-listing`, `attach-cortex-agent-to-listing`, `attach-semantic-view-to-listing`, `attach-cortex-knowledge-extension-to-listing`, `provider-monetization`, `marketplace-provider-monetization-offers`, `marketplace-provider-invoice-status`, `marketplace-provider-success`).

**Prerequisites & caveats:** Must be a paid Snowflake account (no trial or Reader accounts). ORGADMIN must accept Provider and Consumer Terms. ACCOUNTADMIN or role with `CREATE LISTING` needed. Provider profile must be created before any listing. All content must be in English. Connected App listings require SPN membership (Select/Premier/Elite tier). Functional review for Native Apps and DSNA can take up to 14 days. A free listing cannot be converted in-place to paid.

**Pairs with:** `data-sharing`, `native-app-provider`, `declarative-sharing`, `attach-ai-products-to-share`, `agent-studio`

---

### `marketplace-search`

> Searches the Snowflake Marketplace (public, internal, or both) for listings matching a user's data or application need using the `cortex search marketplace` CLI, scoped to the user's current region by default.

**Snowflake surface it drives:** `cortex search marketplace` CLI subcommand, `cortex search object` (internal catalog), `SELECT CURRENT_REGION()`, `SELECT SYSTEM$GET_MCD_ELIGIBILITY()`, `--marketplace-type`, `--filter`, `--sort` parameters

**What it accelerates**
- Prevents missed results by running both internal catalog and marketplace searches in a single turn for brand-less data needs, surfacing both what the user already has and what they'd need to acquire.
- Enforces region scoping by default via `CURRENT_REGION()`, preventing out-of-region listings from appearing as immediately installable.
- Applies MCD (Marketplace Capacity Drawdown) eligibility filtering via `SYSTEM$GET_MCD_ELIGIBILITY()` when the user wants to draw against their Snowflake capacity commitment.
- Guards against fabricated attributes — only fields actually returned by the CLI (title, global name, subtitle, description, provider) are used in responses.

**Representative use cases**
- "Find weather data on the Snowflake Marketplace."
- "Is there a Salesforce connector available?"
- "Show me the most popular financial data listings."
- "Search my organization's internal marketplace for HR data."
- "Find HIPAA-compliant healthcare datasets."
- "Find MCD-eligible listings I can apply against my capacity commitment."

**Example prompts**
```
Find weather data on the Snowflake Marketplace
Is there a HubSpot connector available?
Show me free credit risk data in the Marketplace
Search my organization's internal marketplace for HR data
Find MCD-eligible listings for consumer spending data
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** Active Snowflake connection and `cortex` CLI required. Results are region-scoped to `CURRENT_REGION()` by default. Does not assert listing attributes not returned by the search (tables, coverage, pricing, compliance, cadence). For a detailed write-up of a single listing, use `get-marketplace-listing-details`. Not for how-to questions about named integration mechanisms or for formatting results already in hand.

**Pairs with:** `get-marketplace-listing-details`, `marketplace-provider`, `data-sharing`

---

### `get-marketplace-listing-details`

> Produces a fixed four-part recommendation write-up for a single Snowflake Marketplace listing — why it fits the user's need, delivery method, access type, and how it solves the problem — grounded in `SYSTEM$BULK_GET_LISTINGS` and the listing's data dictionary.

**Snowflake surface it drives:** `SYSTEM$BULK_GET_LISTINGS('SNOWFLAKE_DATA_MARKETPLACE', ...)`, `SYSTEM$GET_DATA_DICTIONARY_METADATA`, `marketplace-install-formatting` skill (install card), listing global name (`GZ...` identifier)

**What it accelerates**
- Replaces raw metadata dumps with a structured four-part template: "Why this is a fit" (grounded in the user's account objects), a Delivery/Access table, "How it solves your problem" (real table/column names from the data dictionary presigned URLs), and "Get this listing."
- Derives Delivery and Access labels from the payload fields in the exact precedence Snowsight uses, preventing wrong labels (e.g., personalized listings are always "By Request" + "Paid" regardless of other signals).
- Fetches real column names via `SYSTEM$GET_DATA_DICTIONARY_METADATA` presigned URLs for data-share listings, avoiding fabricated schema in recommendations.

**Representative use cases**
- "Tell me about Marketplace listing GZ2FQZ711TU."
- "Write up the Consumer Pricing listing — should I get it?"
- "What tables does the Knoema Economy Atlas share include?"
- "Give me a recommendation on this listing my colleague shared."
- "I pasted the listing metadata — give me a structured write-up."

**Example prompts**
```
Tell me about listing GZ2FQZ711TU
Give me a detailed write-up of the Tomorrow.io Weather listing
Should I install the Knoema Economy Atlas share?
What does the Accenture risk data listing include?
Write up this listing for me: [pastes SYSTEM$BULK_GET_LISTINGS output]
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** Requires the listing's global name (`GZ...` identifier) and the user's goal — generic overviews are refused. Presigned URLs from `SYSTEM$GET_DATA_DICTIONARY_METADATA` expire within ~1 hour. Private or request-only listings may fail `SYSTEM$BULK_GET_LISTINGS` with insufficient privileges. Not for searching across multiple listings — use `marketplace-search` for that.

**Pairs with:** `marketplace-search`, `data-sharing`

---

### `listing-observability`

> Monitors listing health, consumption, audit state, cost attribution, and consumer-side data freshness for Snowflake listing providers and consumers by routing to focused workflow files.

**Snowflake surface it drives:** `LISTING_REFRESH_HISTORY`, `LISTING_ACCESS_HISTORY`, `AVAILABLE_LISTING_REFRESH_HISTORY`, `SNOWFLAKE.DATA_SHARING_USAGE` views, auto-fulfillment metrics, `SNOWFLAKE.ORGANIZATION_USAGE` cost views

**What it accelerates**
- Routes replication/refresh, consumption, audit, cost, and consumer-freshness questions to the right SQL workflow without requiring the user to know which view covers which scenario.
- Disambiguates provider-side refresh history (`LISTING_REFRESH_HISTORY`) from consumer-side staleness (`AVAILABLE_LISTING_REFRESH_HISTORY`) — the functions differ, require different privileges, and are often confused.
- Surfaces object-to-listing mapping ("which listings use this table") and column-level consumption analytics (which tables and columns consumers are actually querying).

**Representative use cases**
- "Is my listing replicating correctly to all regions?"
- "Which accounts are consuming my listing, and which tables are they querying?"
- "Is my listing live or has it been dropped?"
- "How much is auto-fulfillment costing me per provider?"
- "The data I receive from a listing looks stale — when was it last refreshed?"
- "Which listings reference the table I'm about to change?"

**Example prompts**
```
Is my listing replicating to AWS us-east-1?
Which consumers are querying my listing and which columns are they accessing?
How much is listing auto-fulfillment costing me?
Is the data I received from this listing up to date?
What listings use my SALES.ORDERS table?
```

**Depth behind it:** 5 supporting files, no sub-skills. Workflow files: `replication-status.md`, `consumption.md`, `auditability.md`, `cost-attribution.md`, `staleness-for-consumers.md`.

**Prerequisites & caveats:** Provider operations require ownership or appropriate privileges on the listing. `LISTING_REFRESH_HISTORY` is provider-side only; `AVAILABLE_LISTING_REFRESH_HISTORY` is consumer-side only — the skill asks which side the user is on if ambiguous. Not for creating or modifying shares — use `data-sharing` for that.

**Pairs with:** `data-sharing`, `internal-marketplace-org-listing`, `marketplace-provider`

---

### `attach-ai-products-to-share`

> Grants semantic views, Cortex Agents, and Cortex Search Services to an existing Snowflake share in the correct privilege sequence, enabling AI-Ready Marketplace and org listings.

**Snowflake surface it drives:** `GRANT SELECT ON SEMANTIC VIEW ... TO SHARE`, `GRANT REFERENCES ON SEMANTIC VIEW ... TO SHARE`, `GRANT USAGE ON AGENT ... TO SHARE`, `GRANT USAGE ON CORTEX SEARCH SERVICE ... TO SHARE`, `SHOW SEMANTIC VIEWS`, `SHOW AGENTS`, `SHOW CORTEX SEARCH SERVICES`, `DESC AGENT`, `SHOW GRANTS TO SHARE`, `ALTER SHARE ... ADD ACCOUNTS`

**What it accelerates**
- Enforces the database → schema → object grant order mandatory for all AI products, preventing the "Share does not currently have a database" error.
- Identifies all tools (semantic views, search services, custom functions) a Cortex Agent depends on via `DESC AGENT` and grants each in a single pass.
- Applies the correct privilege per product type: `SELECT + REFERENCES` for semantic views (not `USAGE`), `USAGE` for agents and search services.
- Surfaces the agent cross-database limitation upfront before attempting grants, preventing a confusing failure late in setup.

**Representative use cases**
- "Add a semantic view to my existing share for the Marketplace."
- "Attach my Cortex Agent and all its tools to the share I've set up."
- "Add my Cortex Search Service to share it as a CKE on the Marketplace."
- "Build a full AI stack — semantic view + search service + agent — on my share."
- "Grant my agent and its underlying tables to a share."

**Example prompts**
```
Attach my ANALYTICS.PUBLIC.SALES_VIEW semantic view to my existing share
Add my Cortex Agent to the share for my Marketplace listing
Grant my Cortex Search Service to the AI_SHARE share
Set up a full AI stack on my share: semantic view, search service, and agent
```

**Depth behind it:** 0 supporting files, no sub-skills.

**Prerequisites & caveats:** Share must already exist; current role must have `OWNERSHIP` on the share. All AI objects must reside in the same database (one database per share). Agents with cross-database tools or invalid specs cannot be granted — recreate them in the same database as a workaround. `GRANT SELECT ON ALL VIEWS IN SCHEMA` is not supported for shares; views must be granted individually. Use `SHOW SEMANTIC VIEWS` (not `SHOW VIEWS`) to discover semantic views.

**Pairs with:** `data-sharing`, `internal-marketplace-org-listing`, `marketplace-provider`, `agent-studio`

---

### `data-cleanrooms`

> Manages the full Snowflake Data Clean Room (DCR) Collaboration API lifecycle — creating collaborations, registering data offerings and templates, running analyses and activations, managing RBAC, and tearing down — by routing to 14 sub-skills after mandatory database discovery.

**Snowflake surface it drives:** `SAMOOHA_BY_SNOWFLAKE_LOCAL_DB.COLLABORATION.*` stored procedures, `CALL {DB}.COLLABORATION.VIEW_COLLABORATIONS()`, `CALL {DB}.REGISTRY.*`, `CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_ACCOUNT_TO_ROLE()`, `CALL {DB}.ADMIN.GRANT_PRIVILEGE_ON_OBJECT_TO_ROLE()`, `SHOW DATABASES LIKE 'SAMOOHA_BY_SNOWFLAKE_LOCAL_DB%'`, `RESULT_SCAN`, `USE SECONDARY ROLES NONE`

**What it accelerates**
- Enforces database discovery before any operation, preventing "Object does not exist" errors from wrong database names.
- Routes 12 distinct DCR operations (browse, join, register, run, create, manage templates, link/unlink offerings, RBAC, registries, unregister, leave, teardown) to precise sub-skills with confirmation gates, preventing unintended mutations.
- Blocks direct table queries on DCR internals — all operations go through documented `CALL` procedures, protecting against undocumented API changes.
- Recovers CALL results via `RESULT_SCAN(LAST_QUERY_ID())` when client-side render errors mask a successful server execution.
- Handles the `USE SECONDARY ROLES NONE` requirement for procedures that fail with "Secondary roles must be disabled."

**Representative use cases**
- "Create a data clean room collaboration with our advertising partner."
- "Run an audience overlap analysis on the data our partner shared."
- "Register our customer table as a data offering in the collaboration."
- "Set up DCR roles for our campaign manager and data engineer."
- "Approve a template our partner submitted for the collaboration."
- "Leave a collaboration we no longer use."

**Example prompts**
```
Create a new data clean room with my advertising partner
Run an audience overlap analysis on the shared data
Register my CUSTOMERS table as a data offering
Set up DCR roles and privileges for our data engineers
View all collaborations I'm part of
```

**Depth behind it:** 35 supporting files, 14 sub-skills (`browse`, `review-join`, `register`, `unregister`, `create-template`, `run`, `run-analysis`, `run-activation`, `create`, `manage-templates`, `manage-data-offerings`, `dcr-rbac`, `manage-registries`, `tear-down-leave`).

**Prerequisites & caveats:** DCR must be installed (`SAMOOHA_BY_SNOWFLAKE_LOCAL_DB` database must exist — if absent, contact your administrator). ACCOUNTADMIN required to grant DCR privileges. Only documented `CALL` procedures are supported — direct table queries on DCR internals are forbidden. `USE SECONDARY ROLES NONE` may be required before certain procedure calls. If multiple DCR databases exist, the user must choose one before proceeding.

**Pairs with:** `sharing`, `data-sharing`, `data-governance`

---

### `native-app-provider`

> Builds, deploys, versions, publishes, and monitors Snowflake Native Apps — including SPCS containers, Streamlit UIs, agents/MCP servers, restricted caller rights, telemetry, and event sharing — by routing to 17 specialized sub-skills.

**Snowflake surface it drives:** `CREATE APPLICATION PACKAGE`, `manifest.yml`, setup script, `CREATE APPLICATION`, `ALTER APPLICATION PACKAGE`, `ALTER APPLICATION`, `CREATE STREAMLIT`, `snow app deploy`, `SYSTEM$REFERENCE`, `GRANT CALLER`, `EXECUTE AS RESTRICTED CALLER`, `CREATE AGENT`, `CREATE MCP SERVER`, `SYSTEM$REPORT_HEALTH_STATUS`, `APPLICATION_STATE`, `CREATE EVENT ROUTING TABLE`, `DISTRIBUTION = EXTERNAL`, release channels, release directives, compute pools, SPCS service specs

**What it accelerates**
- A single routing table covers 18 distinct intent patterns and always reads the precise sub-skill before touching code, preventing SQL guessing.
- Surfaces the provider vs. consumer intent check early, redirecting "installed app not working" issues to `native-app-consumer` before any provider SQL runs.
- Requires a task list before execution and a task history summary after, giving users a clear audit trail for multi-step app builds.
- Reads `references/troubleshooting.md` before speculating on any error, covering common privilege failures, object conflicts, and missing grants.
- Supports Snow CLI detection for the `setup-app` and `deploy-test` sub-skills, which offer a CLI path alongside the default SQL path.

**Representative use cases**
- "Build a new Native App from scratch with a Streamlit UI."
- "Add SPCS containers to my existing native app."
- "Configure external API access so my app can call a REST API."
- "Add a Cortex Agent and MCP server to my native app."
- "Publish my app to the Snowflake Marketplace with versioning."
- "Set up telemetry and health reporting for my app."

**Example prompts**
```
Create a new Snowflake Native App with a Streamlit dashboard
Add Snowpark Container Services containers to my native app
Configure external API access integration for my app
Add a Cortex Agent and MCP server to my native app
Publish my native app to the Snowflake Marketplace
```

**Depth behind it:** 44 supporting files, 17 sub-skills (`setup-native-app`, `add-containers`, `shared-data`, `deploy-test-native-app`, `native-app-debug`, `app-version-release`, `request-account-privilege`, `request-external-access-integration`, `request-security-integration`, `add-streamlit-to-native-app`, `request-object-access`, `add-agent-mcp`, `use-rcr`, `native-app-configure-telemetry-event-and-health-update`, `native-app-monitor-app-telemetry-event-and-status`, `native-app-configure-event-sharing`, `request-listing`).

**Prerequisites & caveats:** `CREATE APPLICATION PACKAGE` and `CREATE APPLICATION` account-level privileges required. SPCS apps require a security questionnaire before external distribution security scan. Functional review for Marketplace listings can take up to 14 days. Snow CLI support is only available for `setup-app` and `deploy-test` sub-skills; all others use SQL only. Consumer intent ("I installed the app and it's broken") is redirected to `native-app-consumer`.

**Pairs with:** `native-app-consumer`, `marketplace-provider`, `deploy-to-spcs`, `agent-studio`

---

### `native-app-consumer`

> Handles all consumer-side Native App tasks — installing from listings, configuring privileges and specs, managing maintenance policies, diagnosing agent/MCP issues, tracking cost, and uninstalling — by routing to 7 sub-skills.

**Snowflake surface it drives:** `CREATE APPLICATION FROM LISTING`, `GRANT PRIVILEGE ON ACCOUNT TO APPLICATION`, `SHOW APPLICATIONS`, `ALTER APPLICATION UPGRADE`, `CREATE MAINTENANCE POLICY`, `GRANT CALLER TO APPLICATION`, `SHOW GRANTS TO APPLICATION`, `SNOWFLAKE.ACCOUNT_USAGE` for app cost, `DROP APPLICATION`

**What it accelerates**
- Covers the agent/MCP diagnosis path consumers hit most: deriving required `GRANT CALLER` grants from the app's agent spec, diffing against existing grants, and checking feature policies.
- Routes maintenance policy creation and upgrade scheduling, giving consumers control over when disruptive upgrades happen.
- Connects app spending to `SNOWFLAKE.ACCOUNT_USAGE` and budget objects so teams can track and cap installed-app costs.
- Handles edge cases in app uninstall: apps that own objects, use SPCS resources, or created inbound shares each require different teardown steps.

**Representative use cases**
- "Install a Native App from a Marketplace listing."
- "The agent in the app I installed isn't working — fix it."
- "Set up a maintenance window so the app doesn't upgrade during business hours."
- "How much are my installed native apps costing me?"
- "Uninstall a native app that won't drop cleanly."
- "Grant my role access to the app I just installed."

**Example prompts**
```
Install the Acme Analytics app from the Snowflake Marketplace
The Cortex Agent in my installed app isn't responding — fix it
Create a maintenance policy so upgrades only happen on weekends
How much is my installed native app costing me?
Uninstall my native app cleanly including SPCS resources
```

**Depth behind it:** 7 supporting files, 7 sub-skills (`install-native-app`, `configure-native-app`, `manage-maintenance-policy`, `enable-native-app-logging`, `configure-agent-mcp`, `native-app-cost`, `uninstall-native-app`).

**Prerequisites & caveats:** Requires an active account with the listing accessible. `GRANT CALLER` permissions may require ACCOUNTADMIN or specific role grants. Apps with SPCS resources require additional teardown steps before dropping. Maintenance policies require the appropriate account-level privilege. Not for building or publishing apps — use `native-app-provider` for that.

**Pairs with:** `native-app-provider`, `marketplace-search`, `get-marketplace-listing-details`

---

### `manage-zerocopy-sapbdc`

> Manages the end-to-end lifecycle of the SAP BDC ↔ Snowflake zero-copy integration: creating connectors, consuming SAP data products as catalog-linked databases, publishing Snowflake data back to SAP, analyzing mounted data, and troubleshooting connector states.

**Snowflake surface it drives:** `CREATE ZEROCOPY CONNECTOR ... PARTNER = SAP_BDC`, `ALTER ZEROCOPY CONNECTOR ... CONNECT WITH CONFIG (INVITATION_LINK = ...)`, `ALTER ZEROCOPY CONNECTOR ... SET SHARE_BACK = TRUE`, `ALTER ZEROCOPY CONNECTOR ... ADD SHARE`, `ALTER ZEROCOPY CONNECTOR ... DISCONNECT`, `DESC ZEROCOPY CONNECTOR`, `SHOW ZEROCOPY CONNECTORS`, `SELECT SYSTEM$ZEROCOPY_CONNECTOR_LIST_SHARES(...)`, `SYSTEM$SAP_PUBLISH_DATA_PRODUCT`, `DROP ZEROCOPY CONNECTOR`, catalog-linked database creation, Iceberg V3 table validation, minimal CSN Interop v1.0 generation

**What it accelerates**
- Navigates the connector state machine (NEW → CONNECTING → CONNECTED and error variants) with documented allowed actions per state, preventing invalid operations on the wrong state.
- Generates minimal CSN Interop v1.0 (SDK-compatible) for publishing Snowflake data products back to SAP BDC without extra options, reviews, or validation loops.
- Derives the account URL for SAP for Me registration using `SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME()`, removing a manual lookup step.
- Covers all five lifecycle intents (create, consume, publish, analyze, troubleshoot) from a single entry point.

**Representative use cases**
- "Set up a zero-copy connector between my Snowflake account and SAP BDC."
- "Mount an SAP BDC data product as a catalog-linked database in Snowflake."
- "Publish my Snowflake ANALYTICS_DB to SAP BDC as a data product."
- "Query and join data from a mounted SAP data product."
- "My connector is stuck in CONNECT_ERROR — fix it."

**Example prompts**
```
Create a new zero-copy connector and enroll it with SAP BDC
Mount the SAP BDC Workforce Persons data product in Snowflake
Publish my Snowflake database back to SAP BDC as a data product
My zero-copy connector is stuck in CONNECT_ERROR — how do I fix it?
Query the SAP data I've mounted and join it to my Snowflake tables
```

**Depth behind it:** 9 supporting files, no sub-skills. Routes to `INSTRUCTIONS.md` files in `create-connector/`, `consume/`, `publish/`, `analyze/`, and `troubleshoot/` subdirectories.

**Prerequisites & caveats:** ORGADMIN must accept SAP BDC Connect for Snowflake Terms once per organization (Admin → Terms in Snowsight). `CREATE ZEROCOPY CONNECTOR` privilege on the target schema required. `CREATE SHARE` required for publishing. `OPERATE` privilege on connector required for connecting and publishing. Connector must be in CONNECTED state before creating catalog-linked databases or publishing. Disconnect requires disabling share-back and dropping CLDs first. Not for general Snowflake data sharing (non-SAP), SAP HANA direct connections, or SAP BTP non-BDC services.

**Pairs with:** `data-sharing`, `iceberg`, `data-governance`

## Application Development & Platform Surfaces

*Building things people use: apps, dashboards, notebooks, reports — and the storage engines under them.*

### `snowflake-apps`

> Scaffolds, builds, deploys, and operates SAR apps (Snowflake App Runtime apps) — web
> applications backed by an `APPLICATION SERVICE` object, distinct from Streamlit-in-Snowflake
> and Native Apps.

**Snowflake surface it drives:** `APPLICATION SERVICE`, `CREATE/ALTER/DROP/UPGRADE APPLICATION
SERVICE`, `SHOW APPLICATION SERVICES`, `SYSTEM$GET_APPLICATION_SERVICE_LOGS`,
`SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA`, `snow app deploy/setup/events/open/teardown`,
`app.yml` (v2) / `snowflake.yml` deployment manifests.

**What it accelerates**
- Scaffolding a new Next.js-based app from a self-contained template instead of wiring up
  Snowflake auth, queries, and deployment config from scratch.
- Picking and configuring the right deployment manifest layout (`snowflake.yml` +
  build-only `app.yml`, vs. single `app.yml` v2) without the agent guessing field placement.
- Local dev-loop iteration with an automated watch/fix cycle against the dev server's own output.
- Post-deploy triage — logs, CPU/memory/restart health, crash-loop detection, upgrade/rollback,
  horizontal scaling — via `DESCRIBE`/`SHOW APPLICATION SERVICE` instead of ad hoc SQL.
- Choosing owner's-rights vs. caller's-rights query execution up front, which is hard to retrofit.

**Representative use cases**
- "Build me an internal dashboard app on Snowflake that shows our pipeline metrics."
- "Deploy my Snowflake App to production."
- "My app is down — check the logs and tell me why."
- "Scale my app to handle more traffic."
- "Migrate my project from `snowflake.yml` to `app.yml` v2."
- "Roll back my last deploy."

**Example prompts**
```
Build me a new Snowflake App that shows sales by region
Deploy my app to Snowflake
Why is my app down? Check the logs
Restart my Snowflake app and scale it to 3 instances
Add a prod target to my app.yml
```

**Depth behind it:** `9` reference files (manifests, permissions, lifecycle, logs, monitoring,
debugging, limitations, personal-databases, finding-database-and-schema) plus a full Next.js
starter template, `4` sub-skills (`create`, `deploy`, `develop`, `operate`).

**Prerequisites & caveats:** requires an environment skill loaded alongside it — `sar-actions-desktop`
for CoCo Desktop/CLI or `sar-actions-workspaces` for Snowsight — exactly one applies per
environment. Horizontal scaling requires `ENABLE_APPLICATION_SERVICE_HORIZONTAL_SCALING = TRUE`
and is not supported on serverless (CNG-backed) services. Explicitly not for Streamlit-in-Snowflake
apps (use `developing-with-streamlit-in-snowflake`) or Native Apps.

**Pairs with:** `sar-actions-desktop`, `deploy-to-spcs`, `snowflake-workspace`.

---

### `sar-actions-desktop`

> Defines how to carry out each SAR-app lifecycle action (scaffold, generate manifest, run
> locally, deploy, operate) specifically on CoCo Desktop, where a full shell, `snow` CLI, and
> `npm` are available.

**Snowflake surface it drives:** `snow app setup`, `snow app deploy`, `snow app events`,
`snow app open`, `snow app teardown`, `snow --version`.

**What it accelerates**
- Confirms the `snow` CLI is present and current before any app work starts, avoiding
  mid-workflow tooling failures.
- Runs `snow app setup` correctly (dry-run first, resolve missing warehouse, avoid clobbering
  a template-provided `app.yml`) instead of hand-authoring deployment values.
- Deploys in the background with active log polling and clock-based elapsed-time tracking,
  rather than blocking or guessing how long a deploy took.
- Knows which CLI flag (`--entity-id` vs `--target`) selects the right app/target for a given
  manifest shape, avoiding deploys to the wrong target.
- Gives the exact command for logs, opening the app, and (irreversible) teardown, each scoped
  to the right selector and privilege.

**Representative use cases**
- "I'm on my laptop — set up the Snowflake App CLI and confirm it works."
- "Run `snow app setup` for this project."
- "Deploy this app and show me the live build logs."
- "Open my deployed app in the browser."
- "Tear down this app — I don't need it anymore."

**Example prompts**
```
Check that my snow CLI is up to date
Generate the deployment manifest for this app
Deploy my app and show me progress
Open my Snowflake app
Tear down this app's application service
```

**Depth behind it:** `3` supporting files (`cli-guide.md`, `cli-version-check.md`,
`manifest-setup.md`), no sub-skills — this is a companion environment skill loaded alongside
`snowflake-apps`, which owns the phase logic.

**Prerequisites & caveats:** desktop/CLI environment only (local shell, `snow` CLI, `npm`);
the Snowsight-workspace equivalent is a separate skill (`sar-actions-workspaces`) not covered
here. `snow app deploy` is not idempotent — re-running restarts the deployment. Teardown requires
`OWNERSHIP` and cannot be undone.

**Pairs with:** `snowflake-apps`, `deploy-to-spcs`.

---

### `developing-with-streamlit-in-snowflake`

> Entry point for all Streamlit work touching Snowflake — routes to a Snowflake-wired
> scaffolding/deploy/operate sub-skill or, for pure Streamlit authoring with no Snowflake
> angle, to version-matched OSS Streamlit guidance.

**Snowflake surface it drives:** `st.connection("snowflake")`, `snow streamlit deploy`,
`ALTER/DROP/SHOW/DESCRIBE STREAMLIT`, `snowflake.yml` (SiS manifest), `SNOWFLAKE_DEFAULT_CONNECTION_NAME`,
Streamlit-in-Snowflake (warehouse, SPCS, or Workspaces) deploy targets.

**What it accelerates**
- Routes correctly between "general Streamlit question" and "Snowflake-specific Streamlit
  question" so the agent doesn't apply generic Streamlit advice to a SiS deployment problem
  (or vice versa).
- Ships three Snowflake-wired dashboard scaffolds (metrics, compute/credit monitoring,
  stock-peer comparison) with connection boilerplate and parameterized queries already in place.
- Applies Snowflake-branded theming (colors, fonts) as a drop-in config instead of hand-tuning CSS.
- Diagnoses local `streamlit run` vs. Snowflake auth failures (wrong role/user/database, PAT-bound
  `USE ROLE`, stale `st.connection` cache) that are easy to misdiagnose as app bugs.
- Covers the full post-deploy lifecycle (`ALTER STREAMLIT SET QUERY_WAREHOUSE`, rename, drop,
  grant) without inventing unsupported operations (no `SYSTEM$GET_SERVICE_LOGS`, no restart knob).
- For non-Snowflake Streamlit work, auto-detects the installed Streamlit version and defers to
  version-matched content instead of stale bundled guidance.

**Representative use cases**
- "Build a Streamlit dashboard on our Snowflake compute/credit usage."
- "Deploy this Streamlit app to Snowflake."
- "My deployed Streamlit app is using the wrong warehouse — fix it."
- "Apply Snowflake branding to my existing Streamlit app."
- "My local `streamlit run` says the database isn't authorized, but I can see it in Snowsight."
- "Beautify this Streamlit app" (no Snowflake angle — routed to general authoring guidance).

**Example prompts**
```
Build me a Streamlit dashboard for our warehouse credit usage
Deploy this Streamlit app to Snowflake
Change the query warehouse on my deployed Streamlit app
Why does my local streamlit run say database not authorized?
Apply the Snowflake theme to my app
```

**Depth behind it:** `82` supporting files (dashboard/theme templates, API and best-practice
references, CLI/theming/session-state/performance guides) across `2` sub-skills:
`scaffolding-streamlit-in-snowflake` (`sf/`) and `developing-with-streamlit` (the OSS fallback).

**Prerequisites & caveats:** does not cover general Streamlit authoring with no Snowflake angle
when a Streamlit ≥1.57 install is detected (defers to that install's own version-matched skill
content instead of the bundled snapshot). Workspaces-specific SiS runtime guidance lives in a
separate `streamlit-in-workspaces` skill.

**Pairs with:** `snowflake-workspace`, `deploy-to-spcs`, `html-authoring`.

---

### `deploy-to-spcs`

> Deploys any Docker-containerized application (Next.js, Python, Go, etc.) onto Snowpark
> Container Services, from image build through service creation and consumer role access.

**Snowflake surface it drives:** `CREATE COMPUTE POOL`, `CREATE IMAGE REPOSITORY`,
`CREATE/ALTER SERVICE ... FROM SPECIFICATION`, `SHOW COMPUTE POOLS`, `SHOW IMAGE REPOSITORIES`,
`SHOW ENDPOINTS IN SERVICE`, `SYSTEM$GET_SERVICE_STATUS`, `SYSTEM$GET_SERVICE_LOGS`,
`GRANT SERVICE ROLE ... !ALL_ENDPOINTS_USAGE`, `snow spcs image-registry login`.

**What it accelerates**
- Walks the full SPCS path end to end (Docker build → compute pool/repo prerequisites → service
  spec → push → deploy → consumer grants) instead of leaving each step to be looked up separately.
- Supplies a ready-to-adapt `service-spec.yaml` template with resource limits and a readiness
  probe already wired to the right port.
- Enforces `ALTER SERVICE` for updates instead of drop-and-recreate, which would silently change
  the service URL and break integrations.
- Spells out all three required grants for consumer access (database, schema, service role
  endpoint usage) — a combination that's easy to under-grant.
- Ships a troubleshooting table for the most common image-path, port-mismatch, auth, and
  permission failures.

**Representative use cases**
- "I have a Dockerized app — get it running on Snowflake."
- "Deploy this container as an SPCS service and give me the URL."
- "Grant the ANALYST role access to my SPCS service."
- "Update my running service with a new image without changing its URL."
- "My service failed its readiness probe — why?"

**Example prompts**
```
Deploy my Dockerized app to Snowpark Container Services
Create a compute pool and image repository for this service
Push my image and create the SPCS service
Grant role ANALYST access to this service's endpoints
Get the logs for my SPCS service
```

**Depth behind it:** `0` supporting files beyond `SKILL.md`, no sub-skills — a single
self-contained step-by-step workflow skill.

**Prerequisites & caveats:** requires a working local Docker build and a role with permissions
to create compute pools, image repositories, and services. Mandatory stopping points before
proceeding past app-readiness, prerequisite, deployment, and consumer-access steps. None stated
beyond these approval gates.

**Pairs with:** `snowflake-apps`, `sar-actions-desktop`.

---

### `snowflake-notebooks`

> Creates and edits Snowflake Workspace notebooks (`.ipynb` files) that combine SQL cells and
> Python for step-by-step, interactive data analysis.

**Snowflake surface it drives:** Snowflake Workspace notebook `.ipynb` files (nbformat ≥4.5),
`%%sql` cells with cell referencing, `snowflake.snowpark.context.get_active_session`,
notebook runtime version behavior (`.show()` vs `.head()`), `snow://workspace` upload paths.

**What it accelerates**
- Produces notebooks that are actually valid for Snowflake Workspace on the first try —
  correct nbformat version, unique 8-character cell `id`s — avoiding the "cells[n].id: Required"
  rejection.
- Defaults to SQL-cell-plus-cell-referencing patterns (no connection boilerplate needed) instead
  of over-engineering every notebook for dual local/Snowflake execution.
- Only adds local/Snowflake dual-mode connection fallback code when the user explicitly asks for
  it, and correctly swaps SQL cells for `session.sql()` in that mode.
- Flags unsupported libraries (`streamlit`, `ipywidgets`) up front with concrete alternatives
  instead of producing a notebook that fails at runtime.
- Distinguishes runtime-version-dependent APIs (`.show()` on ≥2.6 vs `.head()` on older runtimes)
  so query previews don't silently pull an entire unfiltered table into the kernel.

**Representative use cases**
- "Build me a notebook that explores this table and charts the trend."
- "Convert this Python script into a Snowflake Workspace notebook."
- "My notebook upload keeps failing with a cell id error — fix it."
- "I need this notebook to also run on my laptop, not just in Snowflake Workspace."
- "Debug why this notebook cell is slow."

**Example prompts**
```
Create a notebook that analyzes customer churn with SQL and a chart
Convert this Python script into a Snowflake notebook
Fix the nbformat error in my notebook
Make this notebook runnable both locally and in Snowflake Workspace
Upload this notebook to my Snowflake Workspace
```

**Depth behind it:** `2` supporting files (`Diagram.md`, `references/notebook-runtime-versions.md`),
no sub-skills.

**Prerequisites & caveats:** explicitly not for static SQL-only dashboards, Streamlit apps,
standalone Python scripts, or stored procedures — those have their own skills. Never creates
Snowsight-native notebooks, only Workspace `.ipynb` files.

**Pairs with:** `snowflake-workspace`, `sql-author`.

---

### `snowflake-workspace`

> Router for all Snowflake Workspace operations — file movement (`cortex ws`), lifecycle DDL,
> RBAC, publishing, and the hard rules around git-backed workspaces.

**Snowflake surface it drives:** `cortex ws cp/ls/rm`, `CREATE/ALTER/DROP/UNDROP WORKSPACE`,
`ALTER WORKSPACE ... COMMIT`, `GRANT/REVOKE READ|WRITE|OWNERSHIP ON WORKSPACE`,
`SHOW TERSE WORKSPACES`, `DESCRIBE WORKSPACE`, `snow://workspace/...` URIs, `USER$`/`DEFAULT$`
personal workspaces, workspace replication.

**What it accelerates**
- Gives the exact `cortex ws cp/ls/rm` scp-style grammar (`DB.SCHEMA.WS:/path`) instead of the
  agent constructing raw `snow://workspace` URIs or guessing sanitized mount names.
- Flags the publish-visibility trap on shared workspaces: uploads sit in `live` until
  `ALTER WORKSPACE ... COMMIT`, while server-side copy auto-publishes and remove is irreversible —
  each with a different blast radius the agent needs to know before acting.
- Draws a hard line around git-backed (git-synced) workspaces: UI-only creation, no RBAC sharing,
  and no reliable SQL/CLI way to detect git-backed status — stopping the agent from inventing
  a `CREATE WORKSPACE ... GIT` command or claiming `DESCRIBE` reports repo state.
- Resolves partial or ambiguous workspace names via `SHOW TERSE WORKSPACES` before a file op fails
  with "does not exist or not authorized."
- Redirects git push/pull, per-file publish, and OAuth setup to Snowsight instead of attempting
  a shell-based workaround that can't actually perform them.

**Representative use cases**
- "Upload this file to my Snowflake workspace."
- "List what's in my personal workspace."
- "Share this workspace with the ANALYST role."
- "Connect my workspace to our git repo."
- "I dropped my old workspace by accident — can I get it back?"
- "Is my workspace git-backed?"

**Example prompts**
```
Upload this report to my Snowflake workspace
List the files in DB.SCHEMA.MY_WS
Grant the ANALYST role read access to this workspace
Commit my shared workspace so others can see the new files
Recover my dropped user's workspace files
```

**Depth behind it:** `4` reference files (`recovery.md`, `snowsight-urls.md`,
`target-resolution.md`, `workspace-types.md`), no sub-skills — a router that dispatches
directly to `cortex ws` (bash) or SQL rather than nested sub-skills.

**Prerequisites & caveats:** git-backed workspace creation, git push/pull, per-file publish,
and OAuth setup are UI-only — explicitly not attempted via SQL, CLI, or `git` shell commands.
A shared workspace cannot be git-backed, and vice versa. `LOCAL`-schema personal workspaces do
not replicate.

**Pairs with:** `snowflake-notebooks`, `snowflake-apps`, `snowflake-publish-report`.

---

### `html-authoring`

> Required for any `.html` file creation or edit — authors reports to the strict, sandboxed,
> no-network Content-Security-Policy environment Snowflake uses to render shared reports.

**Snowflake surface it drives:** Snowflake report-sharing sandbox rules (CSP, `/libs/` vendored
library allowlist), the `snowflake-source` and `snowflake-report-metadata` provenance markers
consumed by downstream report tooling.

**What it accelerates**
- Encodes the sandbox's full allow/deny list (no inline handlers, no `eval`, no CDN scripts, no
  remote images, no `fetch`/`XMLHttpRequest`, no cookies/storage, no iframes) so a report doesn't
  silently break or get blocked after publish.
- Names the exact pinned-version path for every vendored charting/rendering library
  (chart.js, Plotly cartesian, d3, vega/vega-lite/vega-embed, mermaid, katex, highlight.js,
  marked, three.js) instead of the agent guessing a CDN URL that will be stripped.
- Supplies the specific non-obvious settings each library needs in this sandbox (`ast: true` for
  vega-embed, `securityLevel: 'strict'` for mermaid, numeric width instead of `'container'`).
- Bakes in responsive-layout and light/dark theming patterns (fluid containers, `chart-box`
  height pattern, `light-dark()` CSS) so reports don't overflow on mobile or on a narrow panel.
- Defines a machine-readable `<script type="application/json">` metadata block that lets a
  later agent run find and refresh a specific report section by anchor id.

**Representative use cases**
- "Build me an HTML report summarizing Q4 revenue by region."
- "Add a bar chart to this report."
- "This report looks broken on my phone — fix the layout."
- "Refresh the revenue-by-region section of this report with the latest numbers."
- "Add a Mermaid diagram of our pipeline to this report."

**Example prompts**
```
Create an HTML report of Q4 revenue by region with a bar chart
Add a Mermaid flowchart of our deployment pipeline to this report
Make this report's table scroll instead of overflowing on mobile
Add dark-mode support to this report's styling
Update the revenue-by-region section with this new query's results
```

**Depth behind it:** `1` supporting file (`references/runtime-styles.css`), no sub-skills.

**Prerequisites & caveats:** files must be saved to a durable location (current workspace by
default) — never left in transient/scratch storage. Only the fixed `/libs/` library set and
pinned versions listed in the skill are available; anything else is silently dropped or blocked.

**Pairs with:** `snowflake-publish-report`, `snowflake-workspace`.

---

### `snowflake-publish-report`

> Publishes a local (or workspace) HTML report as a shareable Snowflake Intelligence
> (Cowork) report artifact, with lineage back to an editable workspace copy.

**Snowflake surface it drives:** `publish_report` tool (Snowsight/workspace surface) or
`cortex artifact publish-report` CLI (desktop surface), Snowflake Intelligence / Cowork report
artifacts, role-based `GRANT READ` access.

**What it accelerates**
- Replaces a hand-rolled stage upload with a single tool/CLI call that also creates the report
  artifact and wires its "edit" button back to the workspace copy.
- Forces an explicit access decision before publishing — sharing is grant-based (no link sharing)
  and at least one role is required — instead of defaulting to `PUBLIC` and over-exposing data.
- Phrases the access question to match Snowsight's own publish dialog wording, so the CLI/tool
  path and the UI path feel identical to the user.
- Makes re-publishing the same file idempotent (updates the same artifact, no duplicates) rather
  than creating a new artifact each time.
- Standardizes the post-publish report format (shareable link, shared-with roles, title, artifact
  id, workspace copy) so links are always clickable/copyable, never wrapped in a code block.

**Representative use cases**
- "Publish this HTML report to Snowflake Intelligence."
- "Share this report with the FINANCE role only."
- "Make this report visible to everyone in the account."
- "Update the report I already published with the latest version."
- "Give me a shareable link to this Cowork report."

**Example prompts**
```
Publish this report to Snowflake Intelligence
Share this report with the SYSADMIN role only
Publish this HTML report and share it with everyone in the account
Republish this report with my latest edits
```

**Depth behind it:** `2` variant SKILL files (`SKILL.md` for the workspace/tool surface,
`SKILL.desktop.md` for the CLI surface), no sub-skills.

**Prerequisites & caveats:** the file must be inside the open workspace folder (tool surface) or
the current working directory (CLI surface). Publishing with zero granted roles is rejected;
`PUBLIC` must never be used unless the user explicitly asked for account-wide access — if unclear,
the skill must ask and wait rather than assume.

**Pairs with:** `html-authoring`, `snowflake-workspace`.

---

### `sql-author`

> Writes, fixes, runs, and debugs Snowflake SQL by grounding every change in the real schema
> and compile-validating the final statement before presenting it.

**Snowflake surface it drives:** `DESCRIBE TABLE`, `SHOW TABLES`/`SHOW VIEWS`,
`INFORMATION_SCHEMA.COLUMNS`/`TABLES`, `cortex search object`, `cortex semantic-views search`,
`cortex search docs`, `CALL EXPLAIN_PRIVILEGES(...)`, `snowflake_sql_execute(..., only_compile=true)`.

**What it accelerates**
- Replaces "guess a fix for the visible syntax error" with a disciplined sequence: inspect real
  schema → check table size → resolve ambiguous object names via search → fix root cause →
  compile-validate — cutting the number of failed round-trips on a broken query.
- Distinguishes a genuine SQL bug from a privilege error (`EXPLAIN_PRIVILEGES`), so the agent
  doesn't keep rewriting SQL that was never going to run regardless of syntax.
- Checks `ROW_COUNT` before running against an unfamiliar table and pushes for date/partition
  filters, avoiding accidental full-table scans.
- Encodes a checklist of Snowflake-specific dialect gotchas (`!=` vs NULL, `COUNT(col)` vs
  `COUNT(*)`, `QUALIFY`, `ILIKE`, `DIV0NULL`, `VARIANT` casting, `ARRAY_CAT` arity) that commonly
  trip up SQL written against other dialects.
- Requires a clean `only_compile=true` pass on the exact final statement before it's shown to the
  user, so what's handed back is guaranteed to compile.

**Representative use cases**
- "This query is failing with an invalid identifier error — fix it."
- "Write me a query that gets total revenue by region for Q4."
- "Why am I getting a permission denied error on this table?"
- "This join is returning duplicate rows — what's wrong?"
- "I'm not sure of the exact table name — can you find it?"

**Example prompts**
```
Fix this failing SQL query: <paste error and SQL>
Write a query for total revenue by region last quarter
Why does this query say I don't have permission?
Find the table that has our customer churn data
Validate this SQL compiles before I run it
```

**Depth behind it:** `0` supporting files, no sub-skills — a single, dense workflow skill.

**Prerequisites & caveats:** None stated.

**Pairs with:** `snowflake-notebooks`, `iceberg`, `sql-author`-adjacent domain skills like
`data-quality` and `lineage`.

---

### `iceberg`

> Router for every Snowflake Iceberg workflow — table creation, catalog integrations, catalog-linked
> databases, external volumes, auto-refresh, Horizon IRC, and converting externally managed tables
> to Snowflake-managed.

**Snowflake surface it drives:** `CREATE ICEBERG TABLE`, `CATALOG='SNOWFLAKE'` /
`EXTERNAL_VOLUME='SNOWFLAKE_MANAGED'`, `CREATE CATALOG INTEGRATION` (Glue IRC, S3 Tables, Unity
Catalog, OpenCatalog/Polaris, OneLake/Fabric, BigLake, SAP BDC, Delta Sharing), `CREATE DATABASE
LINKED_CATALOG` (catalog-linked databases), `CREATE EXTERNAL VOLUME`, `ALTER ICEBERG TABLE ...
CONVERT TO MANAGED`, Horizon IRC (Snowflake's Polaris-based REST catalog) diagnostics.

**What it accelerates**
- Fast-paths the common case — "just create an Iceberg table" — straight to Snowflake-managed
  storage with zero external-volume/catalog questions, instead of every request going through a
  full catalog-integration interview.
- Disambiguates seven different external catalog types (Glue/S3 Tables, Unity Catalog, OpenCatalog,
  OneLake/Fabric, BigLake, SAP BDC, Delta Sharing) from user language and routes to the
  catalog-specific setup skill instead of one-size-fits-all guidance.
- Sequences multi-step setups correctly (catalog integration → external volume → catalog-linked
  database → Snowflake Intelligence) instead of skipping a dependency and hitting an opaque error later.
- Diagnoses auto-refresh staleness and Horizon IRC connection failures (401/403/404, table not
  visible) with dedicated troubleshooting sub-skills rather than generic advice.
- Knows the exact eligibility rule for `CONVERT TO MANAGED` (only externally managed tables
  created outside a CLD qualify) before attempting a conversion that will fail.

**Representative use cases**
- "Create an Iceberg table for this data."
- "Connect Snowflake to our AWS Glue Data Catalog."
- "Set up a catalog-linked database so new tables show up automatically."
- "I'm getting Access Denied writing to my S3 external volume."
- "My Iceberg table data looks stale — why isn't it refreshing?"
- "Take ownership of this externally managed Iceberg table."
- "Let people query our catalog-linked Iceberg data in natural language."

**Example prompts**
```
Create an Iceberg table named ORDERS with id and amount columns
Set up a catalog integration to our AWS Glue Data Catalog
Create a catalog-linked database for our Unity Catalog tables
My Iceberg table data is stale, diagnose the auto-refresh issue
Convert this externally managed Iceberg table to Snowflake-managed
```

**Depth behind it:** `21` supporting files plus `47` total `SKILL.md` files (`46` sub-skills)
spanning table creation (`snowflake-managed-storage`), seven catalog-integration families
(`glueirc-`, `unitycatalog-`, `opencatalog-`, `onelake-`, `biglake-`, `sapbdc-`,
`deltasharing-catalog-integration-setup`, several with their own `create`/`setup`/`verify`
sub-sub-skills), `catalog-linked-database`, `external-volume`, `auto-refresh`,
`horizon-irc-diagnose` (with 5 error-type sub-skills), `convert-to-managed`, and
`cld-snowflake-intelligence`.

**Prerequisites & caveats:** tables inside a catalog-linked database are **not** eligible for
`CONVERT TO MANAGED` — only externally managed tables created outside a CLD. Routing requires a
confirmation checkpoint before most workflows, except the plain create-table fast path.

**Pairs with:** `snowflake-postgres` (for `pg_lake`-scoped Iceberg), `sql-author`,
`snowflake-notebooks`.

---

### `snowflake-postgres`

> Router for everything Snowflake Postgres and general PostgreSQL work — instance management,
> connections, diagnostics, `pg_lake`/Iceberg, managed mirroring, and full migration to Snowflake
> Postgres from any source.

**Snowflake surface it drives:** `CREATE/ALTER/SHOW/DESCRIBE POSTGRES INSTANCE`,
`CREATE_MIRROR`/`LIST_MIRRORS` (managed CDC), `POSTGRES_EXTERNAL_STORAGE` integration,
`CATALOG_SOURCE = SNOWFLAKE_POSTGRES` catalog integration for `pg_lake`, network policies
(`MODE = POSTGRES_INGRESS`), plus standard `psql`/`~/.pg_service.conf`/`~/.pgpass` tooling for
both Snowflake and non-Snowflake Postgres.

**What it accelerates**
- Draws a hard, table-driven line between Snowflake Postgres and external providers (Neon,
  Supabase, RDS/Aurora, Azure, Crunchy Bridge) so Snowflake-only SQL is never run against an
  external instance.
- Wraps every credential-bearing operation (create, reset, cert fetch) in a script that writes to
  `~/.pg_service.conf`/`~/.pgpass` directly — secrets never pass through chat.
- Runs a 20-second reachability probe immediately after instance creation and tells the agent
  exactly which of four outcomes (reachable/timeout/refused/dns_error) it hit and what to do next.
- Provides one-shot health diagnostics (`pg_doctor.py`: cache hit ratio, bloat, vacuum, locks,
  blocking queries, slow queries, unused indexes) instead of hand-writing `pg_stat_*` queries.
- Owns the full Postgres→Snowflake migration lifecycle — assessment, hybrid plan, replication
  setup, cutover, validation, rollback, resume — as a guided, approval-gated workflow rather than
  a manual runbook.
- Scopes `pg_lake`/Iceberg work correctly: `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` stays here even
  though generic Iceberg belongs to the `iceberg` skill.

**Representative use cases**
- "Spin up a new Snowflake Postgres instance for our app."
- "My Postgres queries are slow — diagnose what's wrong."
- "I can't connect to my Postgres instance from my laptop."
- "Set up continuous CDC replication from Postgres into Snowflake."
- "Migrate our RDS Aurora database into Snowflake Postgres."
- "Expose our `pg_lake` Iceberg tables to Snowflake."

**Example prompts**
```
Create a new Snowflake Postgres instance called app-db
Run a health check on my Postgres instance
Why can't I connect to my Postgres instance — check the network policy
Set up a managed mirror from Postgres to Snowflake
Migrate my Aurora Postgres database to Snowflake Postgres
```

**Depth behind it:** `109` supporting files (scripts, SQL diagnostics, per-source-platform
migration guides, test suites) across `16` sub-skills: `connect`, `diagnose`, `manage`, `mirror`,
`pg-lake`, and `migrate` (itself decomposed into `assess`, `cutover`, `dump-restore`, `large-db`,
`monitor`, `replicate`, `resume`, `rollback`, `security`, `validate`).

**Prerequisites & caveats:** CREATE/RESET operations must go through `pg_connect.py` — never the
raw SQL tool — because the script handles password storage securely. Billable actions (create
instance), suspends, and network-policy/storage-integration changes require explicit approval.
Generic Iceberg/catalog-integration requests not scoped to `pg_lake` belong to the `iceberg`
skill, not here.

**Pairs with:** `iceberg`, `sql-author`.

## Migration & Cortex Code Itself

*Moving workloads onto Snowflake, and extending Cortex Code.*

### `migration-guide`

> Thin installer stub that confirms user approval, then installs the Snowflake AIM for Data Warehouses managed plugin via `cortex plugin install` and hands off to the full `snowflake-migration:migration` skill for the actual migration workflow.

**Snowflake surface it drives:** `cortex plugin install`, `cortex skill` (load `$snowflake-migration:migration`), `scripts/install_plugin.py`, Cortex Code plugin management (`/plugin reload`).

**What it accelerates**
- Removes the manual plugin installation steps for the Snowflake migration toolchain — clone, register, and disable the bundled stub in one script run.
- Gates on explicit user approval before installing, so the user stays in control of what gets added to their environment.
- Detects missing `git` (required for the clone) and stops with a actionable install link instead of failing silently.
- Is idempotent — reports "already installed" without side effects on re-run.
- Hands off to the full migration skill once the user says "migrate," so the stub never duplicates migration logic.

**Representative use cases**
- "We're moving our SQL Server data warehouse to Snowflake and need help converting stored procedures and T-SQL."
- "Migrate our Oracle PL/SQL packages and ETL to Snowflake — where do I start?"
- "We have Redshift SQL and need the Snowflake equivalent, even for simple syntax questions."
- "Sunset our legacy Netezza warehouse and replatform everything onto Snowflake."
- "Convert our Informatica ETL workloads to Snowflake-native patterns."

**Example prompts**
```
migrate my SQL Server database to Snowflake
help converting Oracle PL/SQL to Snowflake
we want to replatform our legacy data warehouse onto Snowflake
convert this T-SQL MERGE statement to Snowflake
snowconvert our Netezza stored procedures
```

**Depth behind it:** 3 supporting files (`scripts/install_plugin.py`, `SKILL.desktop.md`, `SKILL.md`), no sub-skills. This is a deliberate stub — all real migration logic lives in the separately installed `snowflake-migration:migration` plugin skill, not in this bundled skill.

**Prerequisites & caveats:** Requires `git` installed and on `PATH` for the plugin clone. Requires explicit user approval before installation. After install, the user must run `/plugin reload` to hot-reload the plugin runtime. Not for answering source-vendor SQL questions directly — always installs the plugin and routes through `snowflake-migration:migration`.

**Pairs with:** `spark-migration`, `snowflake-migration:migration` (installed plugin).

---

### `spark-migration`

> Router skill that converts Spark and PySpark workloads to Snowflake via two bundled paths — Snowpark Connect (SCOS, default, preserves the PySpark API surface) and Snowpark API (SMA CLI, explicit opt-in) — and also orchestrates deployment to Snowflake Notebooks, Code Bundles, or dbt projects.

**Snowflake surface it drives:** Snowpark Connect (SCOS), `snowflake.snowpark` API, SMA CLI (`sma`), `CREATE NOTEBOOK`, `CREATE CODE BUNDLE`, `snow dbt deploy`, Snowflake stages (`PUT`, `COPY FILES`), compute pools, warehouses, Snowflake Workspace notebooks, `snow` CLI.

**What it accelerates**
- Removes the research of which Spark-to-Snowflake conversion path to take — defaults to SCOS (API-preserving) and only routes to SMA/Snowpark API when explicitly requested.
- Eliminates manual configuration management with a shared `config_manager.py` that persists per-project state (source path, output folder, conversion type, post-conversion pipeline toggles) across sessions.
- Handles the full post-conversion pipeline for the SMA path: EWI fixing, stage conversion, DVP validation orchestration, and SMA dashboard generation — each a bundled sub-skill.
- Deploys converted output directly to Snowflake as a Notebook (`deploy-notebook`) or Code Bundle (`deploy-code-bundle`) without manual stage upload or object creation.
- Converts Spark pipelines to dbt projects (`migrate-to-dbt`) with assess-scaffold-convert-validate phases and hands off deployment to `dbt-projects-on-snowflake`.
- Validates already-migrated output (SMA or SCOS) by detecting the output layout and running the appropriate post-conversion steps.

**Representative use cases**
- "Convert our PySpark ETL scripts to Snowflake — we want to keep the DataFrame API patterns we already know."
- "We already ran SMA on our Databricks notebooks and have the output — help us fix the EWIs and validate the migration."
- "Migrate our Spark Scala jobs to Snowpark and deploy the result as a Snowflake Code Bundle."
- "Assess our PySpark workload for Snowflake readiness before we commit to a migration."
- "Convert our Spark pipeline to dbt models deployed on Snowflake."
- "Deploy the migrated notebook to Snowflake so our team can run it."
- "Fix the SPRKPY EWIs in our SMA-converted Snowpark code."

**Example prompts**
```
migrate pyspark to snowflake
convert our spark scripts to snowpark
we already ran SMA — fix the ewis and run stage conversion
assess our databricks workload for snowflake readiness
deploy the migrated notebook to snowflake
migrate our spark pipeline to dbt on snowflake
```

**Depth behind it:** 1277 supporting files, 28 sub-skills (`snowpark-connect`, `snowpark-api`, `deploy-notebook`, `deploy-code-bundle`, `migrate-to-dbt`, `snowflake-notebook-migration`, `assess-pyspark-workload`, `migrate-pyspark-to-snowpark-connect`, `migrate-spark-scala-to-snowpark-connect`, `migrate-spark-java-to-snowpark-connect`, `validate-pyspark-to-snowpark-connect`, `validate-spark-scala-to-snowpark-connect`, `validate-spark-java-to-snowpark-connect`, `migrate-pyspark-to-snowpark-api`, `validate-pyspark-to-snowpark-api`, `sma-dashboard-generator`, `stage-conversion`, `dvp-orchestrator`, `dvp-asg-generation`, `dvp-entrypoint-identifier`, `dvp-io-schema-identifier`, `dvp-test-setup-generator`, `dvp-synthetic-data-generator`, `dvp-code-adapter`, `dvp-test-runner`, `dvp-migrated-test-fixer`, `dvp-ewi-fixer`, `dvp-notebook-to-script`). Sub-skills are bundled inside the skill directory, not separately installed — the parent owns user-facing triggers to avoid collision.

**Prerequisites & caveats:** Requires `git` (checked at startup, auto-installed per platform). SMA CLI required only for the `snowpark-api` path — the SCOS default path does not need it. Scala/Java migration via the SMA path stops with a switch-to-SCOS prompt (Python only for SMA). The Progress UI is experimental, SCOS-only, and OFF by default — only launched on explicit user request. Not for non-Spark migrations — use `migration-guide` / `snowflake-migration:migration` for SQL/PL/SQL/T-SQL.

**Pairs with:** `migration-guide`, `dbt-projects-on-snowflake`, `snowflake-notebooks`.

---

### `skill-development`

> Router skill for creating, auditing, refactoring, compiling, and session-capturing Cortex Code skills, dispatching to five bundled sub-skills based on detected intent.

**Snowflake surface it drives:** `skill_manage` (create, patch, edit, archive, restore), `skill_view`, `skills_list`, `cortex skill` CLI, Cortex Code skill directory structure (`SKILL.md` frontmatter, `references/`, `scripts/`, `assets/`), `SKILL_BEST_PRACTICES.md`.

**What it accelerates**
- Removes the guesswork of skill structure — `create-from-scratch` generates frontmatter, workflow, stopping points, and output sections following the standard template.
- Eliminates manual best-practices review — `audit-skill` lints skills against `SKILL_BEST_PRACTICES.md` and provides fixes (single or batch).
- Handles large-skill decomposition — `refactor-skill` splits skills exceeding 500 lines or with too many branches into a coordinator/specialist architecture.
- Removes the LLM latency bottleneck for templated skills — `compile-skill` interviews the author and generates a regex-classifier + SQL/script-template fast path with graceful LLM escape.
- Captures completed session work as reusable skills — `summarize-session` extracts a session's workflow into a parameterized, replayable skill.

**Representative use cases**
- "Build a new skill that automates our daily freshness checks."
- "Audit our custom skills for best-practice compliance and fix what's wrong."
- "This skill is 800 lines and has too many branches — refactor it into a coordinator with specialists."
- "Turn today's session into a reusable skill so the team can replay it."
- "Make our report-generation skill deterministic — it runs the same prompts every time and the LLM round-trip is too slow."
- "Create a skill that wraps our internal CI/CD deployment workflow."

**Example prompts**
```
create a new skill for monitoring warehouse credit usage
audit my skills against best practices
refactor this skill — it's too big and has too many branches
summarize this session into a reusable skill
compile this skill to make it deterministic and fast
```

**Depth behind it:** 8 supporting files (`SKILL_BEST_PRACTICES.md`, `compile-skill/references/eval_design.md`, plus sub-skill `SKILL.md` files), 5 sub-skills (`audit-skill`, `compile-skill`, `create-from-scratch`, `refactor-skill`, `summarize-session`). Each sub-skill owns its own intent and workflow; the parent detects intent from triggers and routes.

**Prerequisites & caveats:** None stated. The skill documents strong skill domains where Cortex Code has native tooling (Snowflake SQL execution, Cortex Analyst, semantic views, dbt, data validation) and recommends prioritizing skills in those areas.

**Pairs with:** `find-skill-and-plugin`, `share-skill-and-plugin`, `cortex-code-guide`.

---

### `find-skill-and-plugin`

> Discovers and installs Cortex Code catalog skills and plugins from the Snowflake skill catalog, routing by user intent (skill vs. plugin vs. share-URI vs. bare FQN) and always stopping for user confirmation before installing.

**Snowflake surface it drives:** `cortex skill find`, `cortex skill add`, `cortex plugin find`, `cortex plugin add`, `cortex skill list`, `cortex plugin list`, `cortex skill check`, `cortex plugin check`, `cortex skill update`, `DESCRIBE CORTEX EXTENSION`, `snow://skill_catalog/` URIs, `--plugin-fqn` flag, `CORTEX_HOME` / `SKILL_DIR` env vars (Snowsight sandbox).

**What it accelerates**
- Removes the ambiguity of whether a catalog artifact is a skill or a plugin — uses `DESCRIBE CORTEX EXTENSION` to resolve type from a bare FQN before installing.
- Eliminates trial-and-error install commands — the correct command (`cortex skill add` vs. `cortex plugin add`) is determined by artifact type, never both.
- Handles `snow://skill_catalog/` share URIs directly — skips search and installs the exact artifact the user was shared.
- Falls back across skill and plugin search when one returns no results, so the user does not need to know the artifact type in advance.
- Supports Snowsight sandbox sessions with env-var configuration so installed skills persist in the workspace volume.

**Representative use cases**
- "Find a skill that helps with data governance and install it."
- "Install the skill at snow://skill_catalog/USER$ALICE.SKILL_SHARING.COST_ADVISOR"
- "I need a plugin for Jira integration — search the catalog."
- "Search for anything that can help with CI/CD automation."
- "Check if my installed skills have updates available."
- "Install this Cortex Extension FQN: USER$BOB.SKILL_SHARING.MY_SKILL — is it a skill or a plugin?"

**Example prompts**
```
find a skill for data governance and install it
install snow://skill_catalog/USER$ALICE.SKILL_SHARING.MY_SKILL
search the catalog for a Jira plugin
find a skill or plugin that helps with CI/CD
check for updates on my installed skills
```

**Depth behind it:** 2 supporting files (`SKILL.md`, `SKILL.desktop.md`), no sub-skills. The skill is a self-contained workflow with four paths (Share URI, Skill, Plugin, Bare FQN) and a search-both default.

**Prerequisites & caveats:** Not for public Snowflake Marketplace datasets, Native Apps, or connectors — use `marketplace-search` for those. After `cortex skill find` / `cortex plugin find`, the agent must present top results and wait for user choice before installing — never auto-installs. When the user explicitly says "skill," skip plugin search entirely (and vice versa). Never run both `cortex skill add` and `cortex plugin add` on the same bare FQN — resolve type via `DESCRIBE` first. In Snowsight sandbox, export `CORTEX_HOME` and `SKILL_DIR` before running skill commands.

**Pairs with:** `share-skill-and-plugin`, `skill-development`, `cortex-code-guide`.

---

### `share-skill-and-plugin`

> Publishes or revokes local Cortex Code skills and plugins to the same-account Snowflake skill catalog via Cortex Extension DDL, handling first-time share, re-share (content and/or audience), and unshare flows with SQL and CLI paths.

**Snowflake surface it drives:** `CREATE CORTEX EXTENSION` (`TYPE = SKILL` / `TYPE = PLUGIN`), `ALTER CORTEX EXTENSION` (`ADD LIVE VERSION`, `COMMIT`, `ABORT`), `PUT file://…`, `COPY FILES`, `GRANT READ ON CORTEX EXTENSION`, `DESCRIBE CORTEX EXTENSION`, `DESCRIBE WORKSPACE`, `cortex skill publish`, `cortex plugin publish`, `snow://skill_catalog/` URIs, `snow stage copy`.

**What it accelerates**
- Removes the need to hand-write Cortex Extension DDL — the skill generates `CREATE`, `ALTER … ADD LIVE VERSION`, `COMMIT`, and `GRANT` statements from the artifact's manifest.
- Eliminates the skill-vs-plugin type ambiguity — detects type from explicit statement, directory markers (`SKILL.md` vs `plugin.json`), or `DESCRIBE` output before any SQL is run.
- Handles re-share as two independent halves (content upload + audience options) so the user can update one without touching the other.
- Routes between CLI-first and SQL-fallback paths automatically, preferring `cortex skill publish` / `cortex plugin publish` when available and falling back to raw SQL.
- Detects and surfaces stage file-size/count limits (default 50 files, 2 MB per file, 10 MB total) with actionable guidance instead of silent retries.
- Supports both sandbox/CLI (`PUT file://`) and non-sandbox/SQL-only (`COPY FILES` from workspace) runtime modes.

**Representative use cases**
- "Share my custom data-governance skill with the rest of my team."
- "Publish this plugin to the skill catalog so other users in my account can install it."
- "Re-share this skill — I updated the code and want to push a new version."
- "Update who can see this skill — make it discoverable to everyone in the account."
- "Stop sharing this skill — revoke access from the catalog."
- "Share this plugin publicly to all roles in my account."

**Example prompts**
```
share my skill with the team
publish this plugin to the skill catalog
re-share this skill with updated code
make this skill discoverable to everyone
unshare this skill and revoke access
share my plugin with the ANALYST role
```

**Depth behind it:** 12 supporting files (`step_1_collect_inputs.md`, `step_1_parse_manifest.md`, `step_2_publish.md`, `step_2_publish.desktop.md`, `step_2_fallback_stage_copy.md`, `step_2_upload_skill.md`, `step_2_upload_plugin.md`, `step_3_apply_share_options.md`, `step_4_unshare.md`, `step_5_report_result.md`, `SKILL.desktop.md`, `SKILL.md`), no sub-skills. The step files are loaded sequentially at runtime — the skill tool only loads instructions; the agent executes the workflow in the same turn.

**Prerequisites & caveats:** Same-account sharing only — does not handle cross-account sharing or consumer/install flows. Requires Cortex Extensions feature enabled on the account. Stage limits apply (default 50 files, 2 MB per file, 10 MB total — may differ per account). When `<upload_content>` is false (options-only re-share), do not run `ADD LIVE VERSION`, upload, or `COMMIT`. On stage-limit error, stop immediately — do not fall back to another upload path. For install/consume flows, use `find-skill-and-plugin` instead.

**Pairs with:** `find-skill-and-plugin`, `skill-development`, `cortex-code-guide`.

---

### `cortex-code-guide`

> Comprehensive reference guide for Cortex Code (CoCo) itself — covers every tool, slash command, keyboard shortcut, configuration option, skill/agent system, MCP setup, hook events, and special input syntax, serving as the canonical "how do I use CoCo" lookup.

**Snowflake surface it drives:** `sql_execute`, `snowflake_object_search`, `snowflake_table_lookup`, `snowflake_product_docs`, `semantic_view_search`, `cortex_agent_search`, `snowflake_create_artifact`, `data_diff`, `fdbt`, `notebook_actions`, `data_to_dashboard`, `render_ui`, `skill_manage`, `skill_view`, `skills_list`, `curator`, `cortex` CLI, `cortex ctx`, `cortex memory`, `cortex secret`, `cortex conversations`, `cortex ws`, `cortex automation`.

**What it accelerates**
- Removes the need to memorize CoCo's tool surface — documents every tool with key parameters in categorized tables (File & Code, Shell, Agent & Task, Snowflake Data & SQL, Semantic & Agent Discovery, Notebooks & Dashboards, dbt, Skill Management, Web).
- Eliminates trial-and-error for special input syntax — the `#` table trigger, `@` file trigger, `$` skill trigger, `%` agent trigger, `/` slash command, and `!` bash trigger are all documented with purpose.
- Centralizes all slash commands (session management, skill, configuration, planning, SQL mode, guardrails) so the user does not need to discover them ad hoc.
- Documents keyboard shortcuts (`Ctrl+S` subagent picker, `Ctrl+O` view modes) and configuration options in one place.
- Covers MCP setup, hook events, agent types, and session management (`cortex conversations search/list/transcript/delete`) for advanced workflows.

**Representative use cases**
- "What tools does Cortex Code have for working with Snowflake data?"
- "How do I reference a Snowflake table in my prompt?"
- "What slash commands are available in CoCo?"
- "How do I set up MCP servers in Cortex Code?"
- "What keyboard shortcuts does CoCo support?"
- "How do I configure CoCo settings like autoAcceptPlans or tgrep?"
- "What's the difference between /plan and /compact?"

**Example prompts**
```
what tools does cortex code have?
how do I reference a table in my prompt
what slash commands are available in coco
how do I set up MCP in cortex code
what keyboard shortcuts does coco support
how do I configure tgrep in coco
```

**Depth behind it:** 11 supporting files (`AGENTS.md`, `COMMANDS.md`, `CONFIGURATION.md`, `HOOKS.md`, `MCP.md`, `SESSIONS.md`, `SHORTCUTS.md`, `SKILLS.md`, `SNOWFLAKE.md`, `SKILL.desktop.md`, `SKILL.md`), no sub-skills. The reference `.md` files provide deep-dive detail on each topic area; the main `SKILL.md` is a 792-line comprehensive guide that synthesizes them.

**Prerequisites & caveats:** This is an internal/meta skill — it documents Cortex Code itself rather than Snowflake features. `web_search` requires `ENABLE_CORTEX_WEBSEARCH` to be enabled. `tgrep` requires enabling via `/tgrep on` or `tgrepEnabled: true`. `render_ui` is only available in web UI mode. `monitor` is host-only and unavailable in the cocobox VM sandbox.

**Pairs with:** `skill-development`, `find-skill-and-plugin`, `share-skill-and-plugin`, `team-workflow`.

---

### `team-workflow`

> Multi-phase team orchestration skill that coordinates parallel agents through five phases (Research, Revise, Implement, Verify, Ship) with hard phase gates, a 45-agent budget, and claim-loop worker scheduling for feature implementation tasks.

**Snowflake surface it drives:** `cortex ctx task add/start/done`, `cortex ctx step add/claim/done/list`, `team_create`, `team_delete`, `spawn_teammate`, `list_teammates`, `agent_output`, `cortex ctx discovery`, `EnterPlanMode`, `ExitPlanMode`, `.cortex/plans/plan-<tid>.md`.

**What it accelerates**
- Removes the orchestration burden of multi-agent coordination — manages the full Research → Revise → Implement → Verify → Ship pipeline with role-specific workers.
- Eliminates manual step dependency tracking — steps are added with `--depends-on` flags so workers atomically claim only unblocked work from a shared pool.
- Handles plan-mode constraints automatically — plan mode activates via `team_create`, and the main agent's bash allowlist is restricted to `step add`/`step list` during P1/P2.
- Enforces hard phase gates — no phase advances until all role steps for the current phase are terminal (`completed`/`failed`/`cancelled`), verified via `cortex ctx step list`.
- Manages failure recovery per phase — P3 implementation retries once then asks the user; P4 respawns failed verifiers; P1 accepts partial research.
- Scales team size to task complexity with sizing guidance (small: 1–2 research + 1 implementor + 1 verifier; large: 3–6 research + 1 strategy + 3–5 implementors + 1–2 verifiers + 1 PR).

**Representative use cases**
- "Implement a new authentication middleware feature with tests — use a team."
- "Build a multi-service API change with parallel agents working on different services."
- "Research and implement a data pipeline refactor — I need research, planning, implementation, and verification phases."
- "Ship this feature: research the approach, revise the plan, implement across three services, verify, and open a PR."
- "Our team needs to coordinate a large architectural change across the codebase."
- "Run a team to investigate and fix a complex bug that spans multiple modules."

**Example prompts**
```
implement the auth middleware feature with tests — use a team
/team
research and build the new API endpoints with a team
ship this feature with a PR — coordinate with teammates
cortex --team
```

**Depth behind it:** 7 supporting files (`roles/implementor.md`, `roles/pr.md`, `roles/research.md`, `roles/reviser.md`, `roles/strategy.md`, `roles/verifier.md`, `SKILL.md`), no sub-skills. The role `.md` files define agent-type-specific prompts for each of the five-phase roles.

**Prerequisites & caveats:** Hard budget of 45 agents per workflow (retries count against it). P3+ steps are created lazily — only after `ExitPlanMode` and user plan approval. The main agent must not call `EnterPlanMode` manually (plan mode is activated by `team_create`). The canonical plan path must be `.cortex/plans/plan-<tid>.md`. `ExitPlanMode` is forbidden while any reviser step is non-terminal. Do not start implementation while plan mode is active. Notification-driven flow is the default; stall-recovery probes only after 2 idle minutes.

**Pairs with:** `skill-development`, `cortex-code-guide`.

---

## Plugin: `data` — Airflow & Astronomer

*Orchestration-side skills, shipped as a bundled plugin. Invoke as `data:<skill>`.*

### `data:airflow`

> Router and operations hub for Apache Airflow — lists, triggers, debugs, and manages DAGs, runs, and tasks via the `af` CLI, and dispatches to sibling skills for authoring, testing, deploying, and migrating.

**Snowflake surface it drives:** `af` CLI (`af dags`, `af runs`, `af tasks`, `af config`, `af api`, `af registry`), Airflow REST API, Astro CLI (`astro dev parse`, `astro deploy`), Airflow connections/variables/pools.

**What it accelerates**
- Triggering and monitoring DAG runs without opening the Airflow UI, removing manual polling.
- Diagnosing failed runs in one command (`af runs diagnose`) rather than navigating nested UI pages.
- Discovering operator constructor signatures live from the Airflow Registry before writing code, eliminating guesswork against stale docs.
- Managing multiple Airflow instances (prod, staging, local) with a layered config system that mirrors `git config` scoping.
- Performing daily health checks (`af health`, `af dags errors`, `af config pools`) as a single scripted pass.

**Representative use cases**
- "Trigger my `daily_etl` DAG and wait for it to finish."
- "Why isn't my DAG showing up in the UI? Is there an import error?"
- "What Airflow version is running and which providers are installed?"
- "List all failed runs from the last 24 hours."
- "What are the constructor parameters for `S3ToSnowflakeOperator` right now?"
- "Pause the `legacy_pipeline` DAG without touching the UI."
- "I need to retry just the failed tasks from run `manual__2025-01-14`."

**Example prompts**
```
Trigger the daily_orders DAG and wait for it to finish.
Why did my DAG fail? Show me the logs for the extract_data task.
List all DAGs and tell me which ones are paused.
What connections are configured in my Airflow environment?
Show me what API endpoints are available for managing variables.
```

**Depth behind it:** `2` supporting files (`SKILL.md`, `api-reference.md`), no sub-skills.

**Prerequisites & caveats:** Requires `af` on PATH (install via `uv tool install astro-airflow-mcp` or `astro otto`). `af instance discover` without `--dry-run` creates API tokens in Astro Cloud — the skill explicitly requires user consent before running. Not for warehouse/SQL analytics on Airflow metadata tables (use `data:analyzing-data`); deep root-cause reports route to `data:debugging-dags`.

**Pairs with:** `data:authoring-dags`, `data:testing-dags`, `data:debugging-dags`, `data:managing-astro-local-env`, `data:checking-freshness`, `data:tracing-upstream-lineage`, `data:tracing-downstream-lineage`, `data:migrating-airflow-2-to-3`.

---

### `data:airflow-hitl`

> Builds human-in-the-loop Airflow workflows — approval gates, option selection, form collection, and human-driven branching — using the HITL operator family introduced in Airflow 3.1.

**Snowflake surface it drives:** `airflow.providers.standard.operators.hitl` (`ApprovalOperator`, `HITLOperator`, `HITLBranchOperator`, `HITLEntryOperator`, `HITLTrigger`), Airflow REST API (HITL PATCH endpoints), `af registry parameters standard`, `af api ls --filter hitl`.

**What it accelerates**
- Inserting an approval gate into a DAG without writing custom sensor/deferrable logic, removing the need to implement pause-and-resume from scratch.
- Discovering current operator constructor signatures via `af registry` rather than reading outdated docs, preventing parameter drift bugs.
- Wiring external Slack bots or scripts to respond to pending actions via the REST API, with endpoint discovery baked in.
- Configuring timeout-with-default behavior so a DAG succeeds automatically if no human responds within a deadline.

**Representative use cases**
- "Add an approval step to my pipeline before it writes to production."
- "I need a branching step where a human picks which downstream path to take."
- "Pause the DAG and show the reviewer a markdown summary before proceeding."
- "Let our Slack bot respond to the approval request via the REST API."
- "Automatically approve after 2 hours if no one responds."

**Example prompts**
```
Add an approval gate to my DAG before the load_to_prod task.
Build a DAG that pauses for human sign-off with a 4-hour timeout.
How do I use HITLBranchOperator to let a reviewer pick the next step?
Show me how to respond to a pending HITL task from a Python script.
Add a form-collection step to gather input mid-run.
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Requires Airflow ≥ 3.1 (`af config version`). Constructor parameter names (e.g., `assigned_users`) vary by auth manager and provider release — the skill mandates running `af registry parameters standard` before writing code rather than hardcoding params. Not for AI/LLM task decorators (see `migrating-ai-sdk-to-common-ai`).

**Pairs with:** `data:airflow`, `data:authoring-dags`, `data:testing-dags`.

---

### `data:analyzing-data`

> Answers business questions by running SQL against the data warehouse through a persistent kernel, with a concept/pattern cache that avoids re-discovering table mappings on repeat queries.

**Snowflake surface it drives:** Snowflake SQL (`SELECT`, `INFORMATION_SCHEMA`, `ACCOUNT_USAGE`), Polars/Pandas DataFrames via `run_sql` / `run_sql_many`, `uv run scripts/cli.py exec`, concept cache, pattern cache, table schema cache.

**What it accelerates**
- Running multi-query analysis concurrently with `run_sql_many` instead of sequentially, cutting wall-clock time for exploratory work.
- Caching concept→table mappings so repeated questions about "customers" or "orders" skip warehouse `INFORMATION_SCHEMA` lookups entirely.
- Persisting successful query strategies as patterns, so the same question answered once is answered instantly next time.
- Providing SQL templates for trends, top-N, distributions, and cohorts via `reference/common-patterns.md`, removing boilerplate lookup.

**Representative use cases**
- "How many active customers do we have this month?"
- "Show me the top 10 accounts by revenue for Q3."
- "What's the daily sign-up trend for the last 30 days?"
- "Find all orders where the shipping address is missing."
- "What tables exist in the ANALYTICS schema?"

**Example prompts**
```
How many users signed up last week?
Show me revenue by region for the past quarter.
What are the top 10 products by order count this month?
Find all rows in the orders table where status is NULL.
What tables are in the MART schema?
```

**Depth behind it:** `27` supporting files (`SKILL.md`, `reference/common-patterns.md`, `reference/discovery-warehouse.md`, `scripts/cli.py`, `scripts/kernel.py`, `scripts/cache.py`, `scripts/connectors.py`, `scripts/warehouse.py`, `scripts/config.py`, `scripts/templates.py`, `scripts/pyproject.toml`, `scripts/ty.toml`, `scripts/.gitignore`, and 14 test files), no sub-skills.

**Prerequisites & caveats:** Requires `uv` on PATH. Kernel auto-starts on first `exec` call; idles out after 2 hours (configurable via `ASTRO_KERNEL_IDLE_TIMEOUT`). `run_sql_many` is fail-fast — partial results from a failed batch are discarded. Default query timeout is 120 s; raise with `-t` for long-running queries.

**Pairs with:** `data:checking-freshness`, `data:profiling-tables`, `data:warehouse-init`, `data:tracing-upstream-lineage`.

---

### `data:annotating-task-lineage`

> Adds table-level data lineage to Airflow tasks using `inlets` and `outlets` for operators that have no built-in OpenLineage extraction.

**Snowflake surface it drives:** `openlineage.client.event_v2.Dataset`, `openlineage.client.naming.snowflake.SnowflakeDatasetNaming`, `airflow.sdk.Asset` (Airflow 3+), `airflow.datasets.Dataset` (Airflow 2.4+), Astro Lineage tab.

**What it accelerates**
- Wiring lineage metadata onto any operator in minutes without writing a custom extractor class, removing the need to understand the full OpenLineage extractor API for simple cases.
- Using naming helpers (Snowflake, S3, Postgres, BigQuery) to produce correct namespace/name pairs rather than constructing them manually and risking mismatches.
- Enabling Astro's cross-DAG Lineage tab view with no infrastructure change beyond adding `inlets`/`outlets` to existing operators.

**Representative use cases**
- "My custom `BashOperator` task loads a Snowflake table — track that lineage."
- "Add inlets and outlets to my existing DAG so it shows up in the Astro lineage view."
- "Track that this task reads from S3 and writes to Snowflake staging."
- "Document data flow between three source tables and two output tables."

**Example prompts**
```
Add lineage annotations to my DAG's transform task.
Track that this task reads from raw.orders and writes to staging.orders_clean.
How do I annotate inlets and outlets for a BashOperator?
Use the Snowflake naming helper to create the dataset objects for my task.
Add table-level lineage to my pipeline without writing a custom extractor.
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Inlets/outlets are the lowest-priority lineage source — they are overridden by any existing OpenLineage extractor or `get_openlineage_facets_on_*` method. Table-level only; column-level lineage requires `data:creating-openlineage-extractors`. Dynamic lineage set in `execute()` is lost on deferrable operators; use OL methods for those.

**Pairs with:** `data:creating-openlineage-extractors`, `data:tracing-upstream-lineage`, `data:tracing-downstream-lineage`.

---

### `data:authoring-dags`

> Guides writing new Airflow DAGs or extending existing ones through a structured discover → plan → implement → validate → test workflow with `af` CLI feedback at each step.

**Snowflake surface it drives:** `af config connections`, `af config providers`, `af dags errors`, `af dags get`, `af dags explore`, `af dags warnings`, `astro dev parse`, `astro deploy --dags`, Airflow DAG Python API, `requirements.txt`.

**What it accelerates**
- Discovering available connections, providers, and variables before writing code, eliminating integration failures from missing setup.
- Validating DAG parse errors immediately after saving via `af dags errors`, cutting the feedback loop from minutes (redeploy) to seconds.
- Surfacing deprecation warnings and version-specific behavior via `reference/best-practices.md` before they cause subtle runtime bugs.
- Using `astro dev parse` and `astro deploy --dags` to iterate on DAG code without a full image rebuild.

**Representative use cases**
- "Write a DAG that loads data from S3 into Snowflake on a daily schedule."
- "Add a downstream task to my existing `etl_pipeline` DAG."
- "Create a DAG with a sensor that waits for a file to land in S3."
- "Show me the best-practice structure for a new Airflow pipeline."
- "Write a TaskFlow API DAG that calls an external API and stores results."

**Example prompts**
```
Write a DAG named daily_load that runs at 6am UTC and loads from S3 to Snowflake.
Add a task downstream of transform_data that sends a Slack notification on success.
Create a new Airflow pipeline for ingesting CSV files from SFTP.
What connections are available for me to use in my DAG?
Show me the best-practice way to structure a new DAG.
```

**Depth behind it:** `2` supporting files (`SKILL.md`, `reference/best-practices.md`), no sub-skills.

**Prerequisites & caveats:** For the test → debug → fix loop after authoring, delegates to `data:testing-dags`. Deployment to production is out of scope — use the `deploying-airflow` skill (referenced in the SKILL.md but not included in this plugin set).

**Pairs with:** `data:testing-dags`, `data:debugging-dags`, `data:managing-astro-local-env`, `data:setting-up-astro-project`, `data:migrating-airflow-2-to-3`.

---

### `data:checking-freshness`

> Quickly determines whether one or more warehouse tables are up to date by querying the most recent timestamp and optionally tracing a stale table to its source Airflow DAG.

**Snowflake surface it drives:** `INFORMATION_SCHEMA.COLUMNS`, `MAX(<timestamp_column>)`, `TIMESTAMPDIFF`, `DATEADD`, `DATE_TRUNC`, `af dags get`, `af dags stats`.

**What it accelerates**
- Answering "is the data fresh enough to use in my 9am meeting?" in one pass rather than manually identifying the timestamp column and writing the query from scratch.
- Tracing a stale table directly to its source DAG and triggering `data:debugging-dags` when the DAG has failed, collapsing a multi-step investigation into a single workflow.

**Representative use cases**
- "Is the `orders` table up to date before I run my report?"
- "When was `analytics.daily_sales` last refreshed?"
- "My dashboard looks stale — check the upstream tables."
- "Which of these three tables has data older than 24 hours?"

**Example prompts**
```
Is the customers table fresh?
When was analytics.daily_sales last updated?
Check if the data is current before I present it at 10am.
My dashboard looks off — check all the tables it depends on.
Which tables haven't been updated in the last 24 hours?
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Requires a table with a recognizable timestamp column (`_loaded_at`, `updated_at`, `load_date`, etc.); reports `Unknown` freshness when no such column exists. Freshness thresholds (Fresh < 4 h, Stale 4–24 h, Very Stale > 24 h) are built into the skill's output format.

**Pairs with:** `data:debugging-dags`, `data:tracing-upstream-lineage`, `data:airflow`.

---

### `data:cosmos-dbt-core`

> Turns a dbt Core project into an Airflow `DbtDag` or `DbtTaskGroup` using Astronomer Cosmos, with step-by-step configuration for project, rendering, execution mode, warehouse connection, and testing behavior.

**Snowflake surface it drives:** `astronomer-cosmos` (`DbtDag`, `DbtTaskGroup`, `ProjectConfig`, `RenderConfig`, `ExecutionConfig`, `ProfileConfig`), `SnowflakeUserPasswordProfileMapping`, `LoadMode`, `ExecutionMode`, `TestBehavior`, `astro deploy --dags`.

**What it accelerates**
- Selecting the right Cosmos execution mode (WATCHER, LOCAL, VIRTUALENV, KUBERNETES, AIRFLOW_ASYNC) for the user's constraints without trial-and-error.
- Configuring `ProfileConfig` with Airflow connections rather than plaintext `profiles.yml` secrets.
- Choosing the correct `LoadMode` (manifest, dbt_ls, automatic) for project size and CI/CD pipeline shape.
- Navigating Airflow 2 vs. Airflow 3 import differences and Dataset→Asset URI format changes.

**Representative use cases**
- "Turn my dbt Core project into an Airflow DAG."
- "Embed my dbt models as a TaskGroup inside an existing pipeline."
- "Run dbt tests after each model using Cosmos."
- "Host dbt docs in the Airflow UI."
- "Use a manifest file instead of running `dbt ls` at parse time."

**Example prompts**
```
Create a Cosmos DbtDag from my dbt Core project targeting Snowflake.
Wrap my dbt models in a DbtTaskGroup inside my existing pipeline DAG.
Set up Cosmos to run tests after every model completes.
Configure Cosmos to use a pre-built manifest file for faster parsing.
Show me the VIRTUALENV execution mode setup for dbt Core.
```

**Depth behind it:** `2` supporting files (`SKILL.md`, `reference/cosmos-config.md`), no sub-skills.

**Prerequisites & caveats:** Targets Cosmos 1.11+ and Airflow 3.x (Airflow 2.x import paths documented in Appendix A). `AIRFLOW_ASYNC` execution mode is BigQuery-only. Secrets must use Airflow connections or environment variables — not plaintext `profiles.yml`. For dbt Fusion (not dbt Core), use `data:cosmos-dbt-fusion` instead.

**Pairs with:** `data:cosmos-dbt-fusion`, `data:authoring-dags`, `data:testing-dags`.

---

### `data:cosmos-dbt-fusion`

> Runs a dbt Fusion project with Astronomer Cosmos (Cosmos ≥ 1.11), handling Fusion-specific constraints: binary installation, `ExecutionMode.LOCAL`-only, and limited warehouse support.

**Snowflake surface it drives:** `astronomer-cosmos` (`DbtDag`, `DbtTaskGroup`, `ExecutionConfig`, `ProfileConfig`), `SnowflakeUserPasswordProfileMapping`, dbt Fusion binary (`/home/astro/.local/bin/dbt`), `InvocationMode.SUBPROCESS`.

**What it accelerates**
- Installing the dbt Fusion binary into an Astro Runtime image correctly, avoiding the common mistake of treating Fusion as a pip package.
- Pinning `ExecutionMode.LOCAL` with the right `dbt_executable_path` — the only supported execution mode for Fusion — preventing misconfiguration against Core defaults.
- Identifying unsupported combinations (AIRFLOW_ASYNC, VIRTUALENV) up front so users don't waste time debugging incompatible configs.

**Representative use cases**
- "I'm using dbt Fusion — set up Cosmos to run my dbt project in Airflow."
- "Install the Fusion binary in my Astro Runtime Dockerfile."
- "Create a DbtDag that uses the dbt Fusion engine for Snowflake."
- "Embed my Fusion dbt models as a TaskGroup in an existing DAG."

**Example prompts**
```
Set up Cosmos for my dbt Fusion project targeting Snowflake.
How do I install the dbt Fusion binary in my Astro Runtime image?
Create a DbtDag using dbt Fusion with my Snowflake connection.
Configure Cosmos 1.11 to run dbt Fusion with ExecutionMode LOCAL.
What warehouses does dbt Fusion support with Cosmos?
```

**Depth behind it:** `2` supporting files (`SKILL.md`, `reference/cosmos-config.md`), no sub-skills.

**Prerequisites & caveats:** Requires Cosmos ≥ 1.11.0. dbt Fusion supports Snowflake, Databricks, BigQuery, and Redshift only (while in preview). `AIRFLOW_ASYNC` and `VIRTUALENV` execution modes are not supported — Fusion is a binary, not a Python package. For dbt Core, use `data:cosmos-dbt-core` instead.

**Pairs with:** `data:cosmos-dbt-core`, `data:authoring-dags`, `data:testing-dags`.

---

### `data:creating-openlineage-extractors`

> Creates custom OpenLineage extractors or adds `get_openlineage_facets_on_*` methods to operators, enabling lineage capture — including column-level lineage — for operators without built-in extraction.

**Snowflake surface it drives:** `openlineage.client.event_v2.Dataset`, `openlineage.client.facet_v2`, `airflow.providers.openlineage.extractors.BaseExtractor`, `OperatorLineage`, `AIRFLOW__OPENLINEAGE__EXTRACTORS` env var, `SnowflakeDatasetNaming` naming helper, Astro Lineage tab.

**What it accelerates**
- Implementing lineage for third-party or provider operators the user cannot modify, without reverse-engineering the OpenLineage transport layer.
- Choosing between OpenLineage methods (on owned operators) vs. custom extractors (for third-party operators) — a decision the skill makes explicit to avoid over-engineering.
- Handling common pitfalls: circular imports, wrong module paths, `None` property guards, and dynamic lineage that only resolves after execution.
- Writing unit tests for extractors using mocked operators.

**Representative use cases**
- "My custom operator loads files into Snowflake — add column-level lineage to it."
- "Write an extractor for `S3ToSnowflakeOperator` so it shows up in the lineage graph."
- "Extract lineage from a third-party SQL operator I can't modify."
- "I need runtime-determined outputs captured after execution, not before."

**Example prompts**
```
Add OpenLineage methods to my custom operator to track input and output tables.
Write a custom extractor for S3ToSnowflakeOperator.
How do I capture column-level lineage for my SQL transform task?
Create an extractor for a third-party operator that determines outputs at runtime.
Register my custom extractor in Airflow so it activates automatically.
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Extractor class path must be fully importable from the Airflow worker. OpenLineage extractor precedence: Custom Extractors > OpenLineage Methods > Hook-Level Lineage > Inlets/Outlets. On Astro, no additional transport configuration is needed — lineage is auto-collected. For simple table-level lineage without a custom class, use `data:annotating-task-lineage` instead.

**Pairs with:** `data:annotating-task-lineage`, `data:tracing-upstream-lineage`, `data:tracing-downstream-lineage`.

---

### `data:debugging-dags`

> Performs structured root-cause analysis of Airflow DAG failures — including import errors, task exceptions, infrastructure issues, and silent dependency drift — and produces a remediation plan with ready-to-run commands.

**Snowflake surface it drives:** `af runs diagnose`, `af tasks logs`, `af dags errors`, `af dags stats`, `af runs get`, `af runs clear`, `af tasks clear`, `af config providers`, `af health`.

**What it accelerates**
- Categorizing failures (data, code, infrastructure, dependency) immediately from logs, replacing ad-hoc log reading with a repeatable diagnostic framework.
- Detecting silent dependency drift — a package upgrade between the last green run and the first red run — via Docker image diffing, venv operator inspection, and PyPI/private index release timestamp queries.
- Producing a structured output (Root Cause, Impact Assessment, Immediate Fix, Prevention, Quick Commands) so the diagnosis is actionable, not just descriptive.
- Identifying broken venv-style operators (`@task.virtualenv`, `KubernetesPodOperator`) that bypass the worker image and require separate pin analysis.

**Representative use cases**
- "My `daily_etl` DAG keeps failing — find out why and fix it."
- "A DAG that was working yesterday suddenly fails. What changed?"
- "I think a Python package upgrade broke my pipeline — confirm it."
- "My DAG fails to import — find and fix the parse error."
- "Show me exactly which tasks failed and what SQL to clear them for retry."

**Example prompts**
```
My daily_etl DAG is failing. Diagnose it and tell me how to fix it.
Why did DAG run manual__2025-01-14 fail?
Find the root cause and give me the commands to retry the failed tasks.
A pipeline that worked last week is now failing. What changed?
My DAG won't load — find and fix the import error.
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Requires `af` on PATH. For simple one-off "show me the logs" requests, the `data:airflow` entrypoint handles it directly — this skill is for deep investigation. Astro-specific tools (Astro UI, deployment activity log) are referenced as optional supplements.

**Pairs with:** `data:airflow`, `data:testing-dags`, `data:checking-freshness`, `data:tracing-upstream-lineage`.

---

### `data:managing-astro-local-env`

> Manages the local Airflow environment using the Astro CLI in Docker mode or Docker-free Standalone mode, covering start/stop/restart, log viewing, API queries, troubleshooting, and version upgrades.

**Snowflake surface it drives:** `astro dev start/stop/kill/restart`, `astro dev logs`, `astro dev bash`, `astro dev parse`, `astro dev upgrade-test`, `astro api airflow` (local REST API queries), `astro config set dev.mode standalone`, reverse proxy (`astro dev proxy`).

**What it accelerates**
- Switching between Docker and Standalone (Docker-free, `uv`-managed venv) modes without re-initializing the project, removing the environment setup barrier for local development.
- Running multiple Airflow projects on one machine simultaneously via the reverse proxy, eliminating port-conflict troubleshooting.
- Querying the local Airflow REST API with `astro api airflow` commands using operation IDs instead of raw URL paths, reducing lookup overhead.
- Diagnosing common startup failures (port conflicts, corrupted `.venv`, missing `uv`) with a built-in troubleshooting table.

**Representative use cases**
- "Start my local Airflow environment."
- "Restart just the scheduler without rebuilding the image."
- "Show me the scheduler logs in real time."
- "I have two Airflow projects — run them both locally without a port conflict."
- "Reset my local environment from scratch."
- "Test API compatibility before upgrading to a new Airflow version."

**Example prompts**
```
Start my local Airflow environment.
Restart the Airflow scheduler.
Show me the real-time logs for the webserver.
How do I run Airflow without Docker locally?
My local Airflow won't start — how do I fix it?
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Standalone mode requires Airflow 3 (runtime 3.x) and `uv` on PATH; not supported on Windows. Standalone mode does not support per-component log filtering. After modifying `requirements.txt`, `packages.txt`, or `Dockerfile`, a restart is required. For new project initialization, use `data:setting-up-astro-project` first.

**Pairs with:** `data:setting-up-astro-project`, `data:authoring-dags`, `data:testing-dags`.

---

### `data:migrating-airflow-2-to-3`

> Guides migration of Airflow 2.x DAG code to Airflow 3.x, covering automated Ruff-based fixes, manual search patterns for metadata DB access, import changes, scheduling semantics, XCom, Assets, and config renames.

**Snowflake surface it drives:** `ruff check --select AIR --fix`, `apache-airflow-client` Python SDK, Airflow REST API (`/api/v2/dags`), `airflow.sdk` imports (`dag`, `task`, `Asset`, `chain`), `AIRFLOW__SCHEDULER__CREATE_CRON_DATA_INTERVAL`, `astro dev upgrade-test`.

**What it accelerates**
- Running Ruff's AIR30/AIR301/AIR302/AIR31/AIR311/AIR312 rules to auto-fix the bulk of breaking import and API changes in one command.
- Identifying metadata DB access patterns (`provide_session`, `session.query(DagRun)`) that will raise `RuntimeError` in Airflow 3 and replacing them with the Python client or REST API.
- Navigating scheduling semantic changes (cron `logical_date` alignment, `catchup` default flip, `schedule` default to `None`) that silently alter pipeline behavior.
- Catching shared utility import breakage on Astro (`import common` → `import dags.common`).

**Representative use cases**
- "Migrate my Airflow 2 DAGs to Airflow 3."
- "My DAGs use `execution_date` — update them for Airflow 3 context variables."
- "Update all my `airflow.operators.bash` imports to the new provider paths."
- "My operator queries the metadata DB directly — replace it with the Python client."
- "Check my DAGs for Airflow 3 breaking changes before I upgrade."

**Example prompts**
```
Migrate my Airflow 2 DAG files to Airflow 3.
Fix all the Airflow 3 import errors in my project.
My pipeline uses execution_date — update it for Airflow 3.
Replace the direct metadata DB session access in my custom operator.
What breaking changes do I need to fix before upgrading to Airflow 3?
```

**Depth behind it:** `5` supporting files (`SKILL.md`, `reference/config-changes.md`, `reference/migration-checklist.md`, `reference/migration-patterns.md`, `reference/removed-methods.md`), no sub-skills.

**Prerequisites & caveats:** Strongly recommends upgrading to Airflow 2.11 first, then to Airflow 3.0.11 or higher (ideally 3.1) — other paths make rollback impossible. Early 3.0.x versions have known bugs; 3.1 is the preferred target. `.airflowignore` syntax changed from regexp to glob in Airflow 3 (configurable via `AIRFLOW__CORE__DAG_IGNORE_FILE_SYNTAX`).

**Pairs with:** `data:testing-dags`, `data:debugging-dags`, `data:authoring-dags`.

---

### `data:profiling-tables`

> Generates a comprehensive profile of a warehouse table — schema metadata, row counts, column statistics, cardinality, data quality scores, and sample data — structured for a new team member to understand the dataset.

**Snowflake surface it drives:** `INFORMATION_SCHEMA.COLUMNS`, `INFORMATION_SCHEMA.TABLES`, `COUNT(*)`, `MIN`/`MAX`/`AVG`/`STDDEV`, `PERCENTILE_CONT`, `COUNT(DISTINCT)`, `LEN`, `DATEDIFF`, `DATE_TRUNC`, `run_sql` (from `data:analyzing-data` kernel).

**What it accelerates**
- Running six categories of profiling queries (metadata, size, per-column stats, cardinality, sample data, quality assessment) as a single workflow rather than writing each manually.
- Producing a normalized quality score (completeness, uniqueness, freshness, overall out of 10) that documents data health without custom metric logic.
- Identifying skewed distributions, high/low cardinality columns, NULL patterns, and orphaned foreign keys in one pass.

**Representative use cases**
- "Profile the `fct.orders` table before I build a model on top of it."
- "I inherited this table — give me a full data dictionary and quality report."
- "What's the cardinality of the `status` column in `customers`?"
- "Check how many NULLs are in each column of `raw.events`."
- "What does the data in `analytics.daily_summary` look like?"

**Example prompts**
```
Profile the orders table for me.
Give me a full data quality report on analytics.daily_summary.
What are the statistics for each column in the customers table?
I need to understand this table before using it — profile it.
What's the date range and row count for raw.events?
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Requires a fully qualified or locatable table name. Uses `run_sql` from the `data:analyzing-data` kernel — that kernel must be reachable. SQL syntax in the skill targets Snowflake (`LEN`, `DATEDIFF`, `PERCENTILE_CONT WITHIN GROUP`).

**Pairs with:** `data:analyzing-data`, `data:checking-freshness`, `data:warehouse-init`.

---

### `data:setting-up-astro-project`

> Initializes a new Astro/Airflow project with `astro dev init`, configures Python and OS dependencies, sets up connections and variables via `airflow_settings.yaml`, and validates the project structure before first run.

**Snowflake surface it drives:** `astro dev init`, `astro dev parse`, `astro dev restart`, `astro dev object export/import`, `requirements.txt` (`apache-airflow-providers-snowflake`), `airflow_settings.yaml`, `Dockerfile` (Astro Runtime image).

**What it accelerates**
- Scaffolding the correct project directory structure (dags, include, plugins, tests, Dockerfile, requirements.txt) in one command, removing manual setup.
- Pre-loading connections, variables, and pools from `airflow_settings.yaml` so the environment is ready to use without manual UI configuration.
- Validating DAGs before starting the full environment with `astro dev parse`, catching import errors early.

**Representative use cases**
- "Create a new Airflow project for my data pipeline."
- "Set up a Snowflake connection in my local Airflow."
- "I need to add the Snowflake provider to my requirements."
- "Export my connections to share them with my team."
- "Start a new Astro project — what structure will it create?"

**Example prompts**
```
Initialize a new Astro Airflow project.
Set up a Snowflake connection in my local Airflow project.
Add the Snowflake provider to my project dependencies.
Create a new Airflow project with the standard structure.
Export my connections so I can check them into source control.
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Do not pass `--airflow-version` or `--runtime-version` unless the user explicitly requests a pin — plain `astro dev init` resolves to the latest Astro Runtime. For non-Astro users, the skill references the Apache Airflow Docker Compose quickstart and Helm chart. For running the environment after setup, use `data:managing-astro-local-env`.

**Pairs with:** `data:managing-astro-local-env`, `data:authoring-dags`, `data:testing-dags`.

---

### `data:testing-dags`

> Runs iterative test → debug → fix cycles for Airflow DAGs, starting immediately with `af runs trigger-wait` and only invoking diagnosis commands when a run actually fails.

**Snowflake surface it drives:** `af runs trigger-wait`, `af runs diagnose`, `af tasks logs`, `af dags errors`, `af runs clear`, `astro dev parse`, `astro dev pytest`, `af config connections`, `af config variables`.

**What it accelerates**
- Eliminating pre-flight checks (list DAGs, get DAG, check errors) before a test run — the skill's explicit philosophy is "trigger first, debug on failure," saving multiple round-trips.
- Handling all trigger-wait result shapes (success, failure with `failed_tasks`, timeout with `timed_out: true`) and routing the user to the appropriate next step automatically.
- Covering five concrete testing scenarios (happy path, failure, DAG not found, debug scheduled run, custom config) with ready-to-run command sequences.

**Representative use cases**
- "Test my DAG and fix it if it fails."
- "Run the pipeline and debug any issues."
- "I updated my DAG — verify it works end to end."
- "Test with custom config `{env: staging, batch_size: 100}`."
- "My DAG was working but now it fails after my change — find and fix the issue."

**Example prompts**
```
Test my daily_etl DAG and fix it if it fails.
Run the orders pipeline and troubleshoot any failures.
Test this DAG with config env=staging.
My DAG fails after I changed it — run the test-debug-fix loop.
Run the pipeline and wait for it to complete.
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Requires `af` on PATH. For simple single-trigger requests ("run this DAG"), the `data:airflow` entrypoint handles it directly — this skill is for iterative multi-cycle workflows. On Astro, uses deployment promotion (dev → staging → prod) as the recommended testing structure.

**Pairs with:** `data:authoring-dags`, `data:debugging-dags`, `data:managing-astro-local-env`.

---

### `data:tracing-downstream-lineage`

> Traces what depends on a given table or DAG — building a dependency tree, categorizing downstream assets by criticality, and producing an impact report with risk assessment before a schema or data change.

**Snowflake surface it drives:** `information_schema.view_table_usage`, `SHOW VIEWS`, `af dags list`, `af dags source`, `af tasks list`, Astro Lineage tab.

**What it accelerates**
- Mapping the full blast radius of a column rename, type change, or table deletion before any code is touched, replacing ad-hoc grep searches across DAG files.
- Categorizing downstream assets (Critical / High / Medium / Low) so teams prioritize migration and communication correctly.
- Identifying stakeholders via DAG `owners` fields and dashboard naming patterns.

**Representative use cases**
- "What breaks if I rename this column in `fct.orders`?"
- "I'm deprecating `raw.legacy_table` — what do I need to migrate first?"
- "Which dashboards or reports read from `analytics.daily_sales`?"
- "What's the risk of changing the data type of `amount` in the orders table?"
- "Show me everything downstream of this DAG before I change its schedule."

**Example prompts**
```
What depends on the fct.orders table?
What breaks if I rename the amount column in transactions?
Show me the downstream impact before I delete this table.
Which DAGs consume the daily_sales table?
Map the blast radius of changing the schema of raw.events.
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Source-code search for DAG references requires `af dags source` access to a running Airflow instance. On Astro, the Lineage tab provides a visual graph that reduces the need for manual source searches. None stated for specific Snowflake editions.

**Pairs with:** `data:tracing-upstream-lineage`, `data:checking-freshness`, `data:debugging-dags`, `data:annotating-task-lineage`, `data:creating-openlineage-extractors`.

---

### `data:tracing-upstream-lineage`

> Traces the origin of a table or column by identifying the producing DAG, its source tables and external systems, and the transformation chain, then checks source health.

**Snowflake surface it drives:** `af dags list`, `af dags source`, `af tasks list`, `af dags stats`, `INFORMATION_SCHEMA` (column lookup), Astro Lineage tab.

**What it accelerates**
- Identifying which DAG populates a target table without manually grepping dozens of DAG files, by correlating DAG names with table names and inspecting source code.
- Recursively tracing through multi-hop pipelines (API → raw → staging → mart) to show the full origin chain, not just the immediate source.
- Checking source health (freshness, DAG run status) at each upstream hop in the same workflow.

**Representative use cases**
- "Where does the data in `analytics.revenue` come from?"
- "Which DAG populates `fct.orders` and what does it read from?"
- "Trace the origin of the `customer_lifetime_value` column."
- "My table shows wrong data — find where it's sourced from."
- "What external systems feed into the `raw.events` table?"

**Example prompts**
```
Where does the data in analytics.revenue come from?
Trace the upstream lineage of fct.orders.
Which DAG loads the customers table and what does it read from?
Find the source of the customer_lifetime_value column.
What external systems feed into our Snowflake data warehouse?
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills.

**Prerequisites & caveats:** Requires `af dags source` access to read DAG code. On Astro, the Lineage tab provides a visual upstream graph. Column-level tracing is manual (text search through DAG SQL), not automated. None stated for specific Snowflake editions.

**Pairs with:** `data:checking-freshness`, `data:debugging-dags`, `data:tracing-downstream-lineage`, `data:annotating-task-lineage`, `data:creating-openlineage-extractors`.

---

### `data:warehouse-init`

> Generates `.astro/warehouse.md` — a version-controllable warehouse schema reference enriched with codebase context (dbt models, gusty SQL, AGENTS.md) — and pre-populates the concept/pattern cache used by `data:analyzing-data`.

**Snowflake surface it drives:** `INFORMATION_SCHEMA.SCHEMATA`, `INFORMATION_SCHEMA.TABLES` (`ROW_COUNT`), `INFORMATION_SCHEMA.COLUMNS`, `uv run scripts/cli.py concept import`, `uv run scripts/cli.py concept learn`, `uv run scripts/cli.py cache status`.

**What it accelerates**
- Bootstrapping instant concept→table lookups for `data:analyzing-data` without per-question `INFORMATION_SCHEMA` queries, improving answer accuracy and speed on complex business questions.
- Enriching raw warehouse metadata with business descriptions extracted from dbt model YAML, gusty SQL frontmatter, and `AGENTS.md`/`CLAUDE.md` files — combining schema and documentation in one artifact.
- Flagging large tables (> 100 M rows) with warnings so analysts know to always add date filters.
- Producing a team-shareable, version-controllable `warehouse.md` that survives session restarts.

**Representative use cases**
- "Set up data discovery for my project before I start querying."
- "Generate a schema reference file for my warehouse."
- "My schema changed — refresh the warehouse index."
- "Build a concept cache so future data questions are answered faster."

**Example prompts**
```
/data:warehouse-init
Set up data discovery for my warehouse.
Generate warehouse.md for my Astro project.
Refresh my warehouse schema after the latest deployment.
Initialize warehouse discovery for the HQ and ANALYTICS databases only.
```

**Depth behind it:** `1` supporting file (`SKILL.md`), no sub-skills. Uses `analyzing-data/scripts/` at runtime (scripts live in the sibling skill's directory).

**Prerequisites & caveats:** Requires a warehouse configuration at `~/.astro/agents/warehouse.yml` listing the databases to discover. Cache TTL is 7 days by default. `--refresh` mode preserves user-added HTML comments and Quick Reference entries from the existing file. Spawns parallel subagents per database — requires a Cortex Code environment that supports the Task tool.

**Pairs with:** `data:analyzing-data`, `data:profiling-tables`, `data:checking-freshness`.

## Plugins: `blueprints` & `databricks`

*Bundled with the CoCo install but shipped **disabled** — enable with `/plugin` or `cortex plugin activate <name>` before use.*

### `blueprints:blueprint-builder`

> Conversational front-end to Snowflake Blueprint Manager: captures an organization's context, generates a YAML answer file for a chosen blueprint, and renders deployable SQL plus a documentation/PDF deliverable via `render_journey.py`.

**Snowflake surface it drives:** the five bundled blueprints (`account-creation`, `platform-foundation-setup`, `rbac-hardening`, `data-product-setup`, `pipeline-planner`), `definitions/questions.yaml`, `scripts/render_journey.py` (Jinja2 `code.sql.jinja` / `dynamic.md.jinja` templates), `scripts/migration/migrate_answers.py`, generated account/org SQL covering account strategy, role hierarchy and grants, warehouses, network policies, MFA/SSO/SCIM auth, budgets, resource monitors, tags and cost centers, database/schema zoning; `SELECT CURRENT_ACCOUNT_NAME()`; `cortex ctx remember` for persisted experience level.

**What it accelerates**
- Standing up a greenfield Snowflake account to Snowflake-validated best practice without hand-writing the account, role, warehouse, and policy DDL.
- Turning one open-ended description of a customer's organization into a fully populated answer file, with per-answer inline reasoning comments explaining why each option was chosen.
- Removing the "fake placeholder" failure mode — the skill is explicitly forbidden from inventing account names, emails, domains, IP ranges, or quantities, and marks anything it cannot ground as `null` with guidance on what is needed.
- Adapting delivery depth to the audience via three rendering profiles (Beginner/Verbose, Intermediate/Standard, Advanced/Concise) persisted across blueprints and sessions, with a "show full overview" escape hatch at every level.
- Producing consistent, template-validated SQL — the skill never writes SQL by inference, even for a preview, so output is reproducible across engagements.
- Repairing answer files created before a schema change (41 questions moved from `multi-select` to `single-select`) with a dry-run-first migration script.

**Representative use cases**
- "We just signed with Snowflake and need our first account set up following best practices."
- "Configure my Snowflake organization — single account or multi-account, and get the role hierarchy right."
- "We're SOC 2 and need MFA, network policies, and audit retention configured from day one."
- "Generate the SQL to establish our platform foundation: databases, zones, warehouses, and cost controls."
- "Harden the RBAC on an account we inherited — walk me through the decisions."
- "Set up a data product with the right access model and tagging."
- "I filled out most of the questionnaire last week — resume it and generate the infrastructure code."

**Example prompts**
```
Set up my first Snowflake account following best practices
Create my environment — I want to configure my Snowflake organization
Build a blueprint for our platform foundation and generate the SQL
Fill out the RBAC hardening questionnaire with me
Show me the SQL for the answer file I saved under projects/acme
```

**Depth behind it:** `1` supporting file in the skill directory, `no sub-skills` — but the skill is backed by the plugin root, which ships 5 blueprint definition trees (`blueprints/account-creation`, `platform-foundation-setup`, `rbac-hardening`, `data-product-setup`, `pipeline-planner`), a shared `definitions/questions.yaml`, the `render_journey.py` renderer with its test suite, a `blueprint_pdf` package, an answer-file migration script, and `scripts/TROUBLESHOOTING.md`.

**Prerequisites & caveats:** The `blueprints` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate blueprints` before this skill can be used. Requires the plugin's `blueprints/` and `definitions/` trees (script-relative, not configurable) and a writable `projects/` directory, resolved by `--projects-dir` → `BLUEPRINT_MANAGER_PROJECTS_DIR` → `<cwd>/projects`. PDF output additionally requires `reportlab`, `markdown`, and `beautifulsoup4` from `requirements.txt`. Blueprints declaring a `hand_off_skill` are guidance-only: the skill must **not** run `render_journey.py` for them and instead hands the project name and answer file to the named downstream skill (`pipeline-planner` → `pipeline-plan-generator`). Existing answer files should be run through the migration script before loading.

**Pairs with:** `blueprints:snowflake-best-practices`, `blueprints:pipeline-plan-generator`, `data-governance`, `dcm`.

---

### `blueprints:pipeline-plan-generator`

> Downstream hand-off skill for the Pipeline Planner blueprint: takes a completed answers file, silently profiles the source data in Snowflake, generates a transformation DAG and test plan, and writes an executable implementation plan plus a rendered SQL artifact.

**Snowflake surface it drives:** `DESCRIBE TABLE`, `SHOW TABLES IN SCHEMA`, `SHOW SCHEMAS IN DATABASE`, `LIST <stage>`, `SNOWFLAKE.CORTEX.COMPLETE`, `SNOWFLAKE.CORTEX.AI_GENERATE_TABLE_DESC`, `SYSTEM$CORTEX_ANALYST_FAST_GENERATION`; target technologies Dynamic Tables (`TARGET_LAG`), Streams & Tasks, Snowpark, dbt Projects on Snowflake / dbt Core, and Stored Procedures; DMF attachment DDL via delegation; `scripts/render_journey.py --blueprint pipeline-planner`.

**What it accelerates**
- Converting captured pipeline requirements into a concrete, immediately executable build plan — real table and column names from `DESCRIBE`, never placeholders like `<your_warehouse>`.
- Choosing the right node decomposition for the selected technology, with node count driven by business requirements rather than a capped heuristic.
- Inferring join relationships automatically: Cortex `AI_GENERATE_TABLE_DESC` and `CORTEX_ANALYST_FAST_GENERATION` when available, falling back to `_ID`/`_KEY`/`_CODE` pattern matching when it is not.
- Producing a criticality-tiered test and monitoring plan (Mission-critical / Important / Exploratory) delegated to the `data-quality` skill so DMF coverage is discovered and duplicate tests are deduplicated rather than re-invented.
- Surfacing pre-build ecosystem risk before anything is created — `REFRESH_CONTENTION`, `HIGH_TRAFFIC_SOURCE`, `UNTRUSTED_SOURCE`, `UPSTREAM_INSTABILITY`, and `CRITICAL_CONSUMER_RISK` — each with a mitigation and whether the generated tests cover it.
- Rendering an ASCII DAG in-terminal (explicitly not mermaid) plus a 200–600 line plan document with an ordered implementation sequence.

**Representative use cases**
- "I finished the Pipeline Planner questionnaire — turn my answers into an implementation plan."
- "We picked Dynamic Tables for this pipeline; show me the topology and the DDL before we build anything."
- "Profile our RAW schema and tell me what the staging-to-mart pipeline should look like."
- "This pipeline is mission-critical — what tests and alerts do we need on the output table?"
- "Before we add another Dynamic Table on top of RAW.ORDERS, tell me what else already reads it."
- "Who consumes this source table today, and will our new pipeline break any of them?"
- "Generate the SQL artifact and the plan doc for the invoice aggregation pipeline."

**Example prompts**
```
Generate a plan from my answers file
Run the plan generator — I have my answers file ready
Investigate my sources and create an implementation plan
Create the pipeline plan for the project under projects/acme
```

**Depth behind it:** `2` supporting files (`references/cross-skill-delegation.md`), `no sub-skills`.

**Prerequisites & caveats:** The `blueprints` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate blueprints` before this skill can be used. A completed Pipeline Planner answers file is the **sole input**: this skill never asks blueprint-style questions, and if requirements have not been collected the user must be routed to the Pipeline Planner blueprint first; a technology change requires re-running the blueprint. The `lineage` and `data-quality` skills must both be active in the same session — if either is missing, the corresponding lineage/DQ steps are skipped and the plan document says so explicitly. Requires a connected Snowflake account with privileges to `DESCRIBE` the sources; lineage steps degrade gracefully on "No lineage data available" or "Insufficient privileges". The skill must never write `GET_LINEAGE` or DMF SQL itself — those APIs are owned by the delegated skills. Ecosystem risk thresholds are heuristics, overridable via `ecosystem_risk_thresholds` in the answers file.

**Pairs with:** `blueprints:blueprint-builder`, `lineage`, `data-quality`, `dynamic-tables`, `snowflake-tasks`, `dbt-projects-on-snowflake`, `snowpark-python`.

---

### `blueprints:snowflake-best-practices`

> Answers "how should I…" Snowflake architecture and configuration questions from the plugin's SME-curated blueprint content first, falling back to official product documentation only for topics the local content does not cover.

**Snowflake surface it drives:** the plugin's `blueprints/*/overview.md` and `blueprints/*/step_*/overview.md` guidance corpus, `definitions/questions.yaml`, plus `snowflake_product_docs` and `system_instructions` as secondary sources; topic coverage spans account strategy (single vs multi-account, organization accounts), RBAC and role hierarchy design, grants and privileges, SSO/SAML/SCIM/MFA, network policies and PrivateLink, budgets, resource monitors, tags and chargeback, naming conventions, warehouse sizing/auto-suspend/workload isolation, database and schema zoning, data products, Time Travel and retention.

**What it accelerates**
- Giving a defensible answer to platform design questions without re-deriving them from scratch or reading the whole docs set — local SME content is searched first and is treated as the highest authority.
- Presenting trade-offs in a consistent shape: recommendation, why, options table, explicit "Choose this if…" / "Avoid this if…" decision criteria, concrete example, and a source file citation.
- Preserving the caveats that generic documentation drops — the skill is instructed to read whole overview sections rather than grep snippets, and to keep SME nuance intact.
- Clearly separating SME-curated guidance from general product documentation in the answer, so the customer knows which is which.
- Keeping recommendations situational rather than generic by asking clarifying questions when the customer's context changes the answer.

**Representative use cases**
- "Should we run one Snowflake account or several?"
- "What's the best way to design our role hierarchy before we onboard 200 users?"
- "What naming convention should we use for warehouses, roles, and databases?"
- "How should we set up cost attribution and chargeback across business units?"
- "What's the recommended way to enforce MFA and network restrictions?"
- "How should we lay out databases and schemas for raw, curated, and consumption zones?"
- "How long should we keep Time Travel on, and where do transient tables make sense?"

**Example prompts**
```
What are the Snowflake best practices for account strategy?
How should I design my role hierarchy?
What's the best way to set up cost management and chargeback?
Give me setup recommendations for warehouses and auto-suspend
Snowflake naming convention guidance for roles and databases
```

**Depth behind it:** `1` supporting file, `no sub-skills` — the skill's substance is the plugin-root blueprint corpus it searches (5 blueprint trees plus `definitions/questions.yaml`), discovered dynamically at runtime rather than via hardcoded paths.

**Prerequisites & caveats:** The `blueprints` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate blueprints` before this skill can be used. Depends on the plugin's `blueprints/` and `definitions/` directories being present; guidance quality is bounded by that corpus, and topics outside it fall through to `snowflake_product_docs` / `system_instructions`, which must be labelled as such. This is advisory only — it does not generate or execute SQL; use `blueprints:blueprint-builder` to turn a decision into deployable code.

**Pairs with:** `blueprints:blueprint-builder`, `data-governance`, `cost-intelligence`, `warehouse`, `organization-management`.

---

### `databricks:databricks-setup`

> Installs and manages the Databricks AI Dev Kit skill collection (up to 34 skills) inside Cortex Code by running the upstream installer with `--tools claude`, and manages skill/profile selection afterwards.

**Snowflake surface it drives:** none — this is a Databricks/Cortex Code tooling skill. It drives the `ai-dev-kit` `install.sh` installer (`--tools claude`, `--profile`, `--skills-profile`, `--skills`, `--global`, `--force`, `--silent`, `--list-skills`), `databricks --version`, `databricks auth token`, `databricks auth profiles`, `uv`, `git`, `curl`, and skill installation into `~/.claude/skills/` (global) or `./.claude/skills/` (project).

**What it accelerates**
- Getting the Databricks AI Dev Kit working in Cortex Code at all — the upstream installer does not natively support Cortex Code, and this skill knows to pass `--tools claude` because Cortex Code is compatible with the Claude Code skill format.
- Choosing an install scope and skill profile from named bundles (`all`, `data-engineer`, `analyst`, `ai-ml-engineer`, `app-developer`) or a custom `--skills` list, instead of guessing flags.
- Front-loading the prerequisite gate (`git`, `curl`, `uv`, Databricks CLI ≥ 0.278.0, working auth) and delegating to `databricks-cli-install` when any of it is missing rather than failing mid-install.
- Verifying the result concretely — counting installed `SKILL.md` files and re-checking `databricks auth token` against the chosen profile.
- Re-running the same installer with `--force` for updates and reinstalls, and switching skill profiles without manual file surgery.

**Representative use cases**
- "Install the Databricks skills so Cortex Code can work against our workspace."
- "Set up the Databricks AI Dev Kit for me."
- "I only want the data-engineering Databricks skills, not all 34."
- "Update the Databricks dev kit to the latest version."
- "Install the Databricks skills just for this project, not globally."
- "Which Databricks skills are available to install?"
- "The Databricks skills aren't being detected — check the install."

**Example prompts**
```
Install databricks skills
Set up databricks tools for Cortex Code
Update the AI dev kit
List available databricks skills
Change my databricks skill profile to data-engineer
```

**Depth behind it:** `1` supporting file, `no sub-skills`.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This skill operates against Databricks rather than Snowflake. External dependencies: `git`, `curl`, `uv`, and Databricks CLI ≥ 0.278.0 with configured authentication; it fetches and executes the upstream `databricks-solutions/ai-dev-kit` `install.sh` over the network. Explicit boundary — for the **CLI binary and authentication only**, route to `databricks-cli-install`; this skill installs *skills and MCP tools*. Stops for user input on scope, Databricks profile, and skill profile before installing.

**Pairs with:** `databricks:databricks-cli-install`, `databricks:databricks-cli`, `find-skill-and-plugin`.

---

### `databricks:databricks-cli-install`

> Installs or updates the Databricks CLI binary (v0.205+) across macOS, Linux, WSL, and Windows, then configures and verifies an authentication profile.

**Snowflake surface it drives:** none — Databricks CLI tooling. It drives `brew tap databricks/tap` / `brew install databricks`, the `databricks/setup-cli` curl installer, `winget install Databricks.DatabricksCLI`, `choco install databricks-cli`, GitHub release zips, `databricks -v`, `databricks auth login --host`, `databricks auth token`, `databricks auth profiles`, `databricks clusters list`, `~/.databrickscfg`, and the `DATABRICKS_HOST` / `DATABRICKS_TOKEN` / `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` environment variables.

**What it accelerates**
- Picking the right install path per OS and architecture without hunting through release assets, including the legacy-CLI trap (anything below 0.205.0 is the old `pip`-installed `databricks-cli` and must be uninstalled first).
- Choosing among five auth options with stated trade-offs — OAuth U2M (individuals), OAuth M2M service principals (automation/CI), PAT (legacy/deprecated), environment variables (CI/CD), or skip.
- Catching a specific silent failure the docs gloss over: `databricks auth login` can exit 0 without writing `~/.databrickscfg`, so the skill always verifies with `cat ~/.databrickscfg` and `databricks auth token`, and falls back to PAT if the browser flow keeps failing.
- Appending profiles to `~/.databrickscfg` non-destructively rather than overwriting existing ones.
- Documented update paths per install method, and a troubleshooting table covering PATH misses, non-writable `/usr/local/bin`, existing-binary conflicts, and revoked tokens.

**Representative use cases**
- "Install the Databricks CLI on my Mac."
- "Set up Databricks CLI authentication for a new workspace."
- "We need service-principal auth for our CI pipeline, not a personal token."
- "My `databricks` command isn't found — fix the install."
- "I'm connecting to a second Databricks workspace; add a profile."
- "My Databricks token expired."
- "Update my Databricks CLI, it's on an old version."

**Example prompts**
```
Install databricks cli
Configure databricks authentication
Connect me to a new databricks workspace
brew install databricks and set up auth
Troubleshoot my databricks cli installation
```

**Depth behind it:** `1` supporting file, `no sub-skills`.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This skill targets Databricks, not Snowflake. External dependencies: a package manager (Homebrew, WinGet, or Chocolatey) or `curl`, plus a Databricks workspace URL and credentials — the user supplies the account ID for account-level login. Explicit boundary — for installing Databricks *skills* or *MCP tools* for Cortex Code (the AI Dev Kit), use `databricks-setup` instead; this skill covers the CLI binary and auth only. Personal Access Tokens are noted as legacy/deprecated. The `databricks clusters list` connectivity check requires workspace-level permissions and should be skipped for account-only auth. Mandatory stopping points before choosing an auth method and when a CLI is already installed.

**Pairs with:** `databricks:databricks-setup`, `databricks:databricks-cli`, `cortex-secrets`.

---

### `databricks:databricks-cli`

> General-purpose driver for day-to-day Databricks workspace operations across every major CLI command group, with a REST API escape hatch for anything the CLI does not cover.

**Snowflake surface it drives:** none — Databricks CLI operations. Command groups include `clusters`, `instance-pools`, `cluster-policies`, `libraries`, `jobs`, `pipelines` (Lakeflow/DLT), `warehouses`, `fs` (DBFS/Volumes), `workspace`, `repos`, `secrets`, `users` / `groups` / `service-principals`, `permissions`, `experiments`, `model-registry`, `serving-endpoints`, `account`, and `databricks api` for arbitrary REST calls (e.g. `POST /api/2.0/sql/statements`). Global flags `-p/--profile`, `--host`, `--output json|text`, `--debug`, `--log-level`; `--json` structured input; `jq` post-processing.

**What it accelerates**
- Running the correct command for an intent without CLI reference lookups — an explicit goal→command-group routing table covers compute, jobs, pipelines, SQL, workspace/files, secrets, identity, ML/serving, and account admin.
- Getting machine-readable output by default (`--output json`, with `jq` filtering recipes) so results can be chained into further work.
- Constructing valid `--json` payloads for create/update operations, including quoting rules on Linux/macOS.
- Reaching unsupported endpoints through `databricks api` rather than abandoning the task.
- Guarding destructive operations — `delete`, `permanent-delete`, and `destroy` require user confirmation before running.
- A troubleshooting table mapping the common failures (403, 404, rate limits, cluster not running, unrecognized `--output json` from an old CLI, missing profile, SQL statement timeouts capped at `50s`) to specific fixes.

**Representative use cases**
- "List our Databricks clusters and tell me which are running."
- "Kick off this job and show me the run status."
- "Cancel the job run that's been stuck for an hour."
- "Start our SQL warehouse and run a query against it."
- "Export these notebooks out of the workspace."
- "Add a secret to our scope for the API key."
- "Who's in the data-engineers group, and what can they access?"
- "Check the state of our model serving endpoint."

**Example prompts**
```
List my databricks clusters
Run the ETL job and show me the run output
Manage secrets in my databricks workspace
Show me the SQL warehouses and their state
Call the databricks REST API to get workspace status
```

**Depth behind it:** `1` supporting file, `no sub-skills` — a single 516-line reference organized into Compute, Jobs, Pipelines, SQL, Workspace & Files, Secrets, Identity & Access, ML & Serving, Account, and API Escape Hatch sections.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This skill operates against a Databricks workspace, not Snowflake. Requires Databricks CLI v0.205+ installed and authenticated with a valid profile or environment variables — auth failures route to `databricks-cli-install`. Many operations require workspace or account admin permissions. Explicit boundaries — Declarative Automation Bundles go to `databricks-automation-bundles`, Unity Catalog browsing to `databricks-unity-catalog`, installation to `databricks-cli-install`, and ETL work to the ETL skills.

**Pairs with:** `databricks:databricks-cli-install`, `databricks:databricks-unity-catalog`, `databricks:databricks-automation-bundles`, `databricks:databricks-spark-performance`.

---

### `databricks:databricks-unity-catalog`

> Navigates and manages the Unity Catalog three-level namespace (`catalog.schema.object`) through the Databricks CLI, including grants, volumes, and governed sample-data queries.

**Snowflake surface it drives:** none — this is Databricks Unity Catalog, the counterpart to Snowflake's `DATABASE.SCHEMA.OBJECT` model. It drives `databricks metastores current|list|get`, `catalogs list|get|create|update|delete`, `schemas list|get|create|update|delete`, `tables list|get|exists|delete|list-summaries` (`--omit-columns`, `--include-delta-metadata`, `--schema-name-pattern`, `--table-name-pattern`), `volumes create|list|read|delete` (MANAGED/EXTERNAL), `grants get|get-effective|update`, `external-locations`, `credentials`, `connections`, `registered-models`, `model-versions`, `functions`, and `databricks api post /api/2.0/sql/statements` for sample rows.

**What it accelerates**
- Discovering what data exists in a workspace with a disciplined drill-down (catalogs → schemas → tables → column metadata) that never guesses the catalog or schema — an explicit gate forces the user to choose.
- Detecting up front whether the workspace is actually on Unity Catalog or the legacy Hive Metastore, and adapting to two-level `database.table` naming plus the SQL API when the UC CLI commands will not work.
- Answering access questions without console clicking: direct grants, effective (inherited + direct) grants, and privilege updates via a `changes` payload.
- Producing fully-qualified three-level object references for downstream skills to consume.
- Pulling sample rows safely — finding the cheapest warehouse, respecting the `wait_timeout` 5s–50s bound, backtick-quoting names with hyphens, and reading results from `result.data_array`.
- Flagging governance artifacts when presenting data: column `mask` fields (redacted values) and table `row_filter` fields (incomplete result sets) are called out explicitly.

**Representative use cases**
- "What data do we have in Databricks? Walk me through the catalogs."
- "List the tables in our analytics schema and show me the columns."
- "Who has SELECT on this table, and where does that permission come from?"
- "Grant the data-engineers group SELECT and MODIFY on this schema."
- "Show me 10 sample rows from the sales fact table."
- "Is this table masked or row-filtered? I need to know if what I'm seeing is complete."
- "Create a volume for the raw file drops."
- "Which external locations and connections are registered?"

**Example prompts**
```
List my unity catalog catalogs
Browse the tables in catalog.schema and describe them
Check grants and permissions on main.analytics.sales_fact
Show me sample data from this Unity Catalog table
What volumes exist in this schema?
```

**Depth behind it:** `1` supporting file, `no sub-skills`.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This skill operates against Databricks Unity Catalog rather than Snowflake. Requires Databricks CLI v0.205+ installed and authenticated, and appropriate UC privileges (`USE_CATALOG`, `USE_SCHEMA`, `SELECT`, or `BROWSE`) — `PERMISSION_DENIED` on catalog listing needs a metastore admin grant. On Hive Metastore workspaces, the UC CLI commands, volumes, functions, registered models, and grants CLI are all unavailable. Table creation is out of scope (done via SQL `CREATE TABLE`); the CLI is used for metadata inspection and deletion. Sample-data queries require a running or auto-startable SQL warehouse.

**Pairs with:** `databricks:databricks-cli`, `databricks:databricks-dbsql`, `databricks:databricks-etl-pyspark-notebooks`.

---

### `databricks:databricks-dbsql`

> Router-plus-authoring skill for advanced Databricks SQL features — procedural SQL, materialized views, AI functions, geospatial, collations, pipe syntax, and Lakehouse data modeling — loading one of five topic references based on detected intent.

**Snowflake surface it drives:** none — this is Databricks SQL, the counterpart to Snowflake SQL. It covers `BEGIN...END`, `DECLARE`, `IF`/`WHILE`/`FOR`, `CREATE PROCEDURE` / `CALL`, `WITH RECURSIVE`, `BEGIN ATOMIC...END`, `CREATE MATERIALIZED VIEW ... CLUSTER BY ... SCHEDULE EVERY`, `CREATE TEMPORARY TABLE`, the `|>` pipe operator, `h3_longlatash3()`, `ST_Point()` / `ST_Contains()`, `COLLATE` / `UTF8_LCASE`, `ai_query`, `ai_classify`, `ai_extract`, `ai_gen`, `ai_summarize`, `ai_analyze_sentiment`, `ai_similarity`, `ai_mask`, `ai_fix_grammar`, `ai_forecast`, `ai_parse_document`, `vector_search`, `http_request`, `remote_query`, `read_files`, Lakehouse Federation, Liquid Clustering, Z-ORDER, star schema and SCD Type 2 patterns.

**What it accelerates**
- Getting the runtime gate right before writing anything — a quick-reference table maps every feature to its DBR floor (SQL scripting 16.3+, procedures and recursive CTEs 17.0+, pipe syntax 16.1+, H3 11.2+, ST functions 16.0+, collations 16.1+, AI functions 15.1+) and to whether Serverless is required.
- Detecting Unity Catalog vs Hive Metastore first and switching between three-level and two-level naming, rather than emitting SQL that cannot resolve.
- Loading only the relevant reference (`sql-scripting.md`, `ai-functions.md`, `materialized-views-pipes.md`, `geospatial-collations.md`, `best-practices.md`) instead of carrying all five.
- Cost discipline on AI functions — always adding `LIMIT` during development.
- Ready-made patterns for procedural ETL, AI-powered enrichment, scheduled materialized views, and pipe-syntax aggregation.
- A troubleshooting table that maps each "function not found" / "requires serverless" error to the specific runtime or warehouse-type cause.

**Representative use cases**
- "Write a stored procedure in Databricks SQL that processes new orders."
- "Classify our support tickets and score sentiment directly in SQL."
- "Create a materialized view of daily revenue that refreshes hourly."
- "Rewrite this query using pipe syntax so it reads top-to-bottom."
- "We need H3 indexing and point-in-polygon checks on our location data."
- "Make these string comparisons case-insensitive without lowercasing everything."
- "Review our star schema and tell us where to apply Liquid Clustering."
- "Call an external API from SQL and join the result."

**Example prompts**
```
Write Databricks SQL with a stored procedure and CALL it
Use ai_classify and ai_analyze_sentiment on this table
Create a materialized view with a refresh schedule
Show me pipe syntax for this aggregation query
Data modeling best practices on Databricks with Liquid Clustering
```

**Depth behind it:** `6` supporting files, `no sub-skills` — 5 topic references (`references/sql-scripting.md`, `references/ai-functions.md`, `references/materialized-views-pipes.md`, `references/geospatial-collations.md`, `references/best-practices.md`) loaded on demand.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This skill writes Databricks SQL against Unity Catalog, not Snowflake SQL. Requires Databricks CLI v0.205+ authenticated and a SQL warehouse — **Serverless is required** for AI functions, materialized views, and `http_request`; classic warehouses do not support them. Multi-statement transactions (`BEGIN ATOMIC`) are Preview, and `ST_` functions are Public Preview. On Hive Metastore workspaces, materialized views, AI functions, the grants CLI, Liquid Clustering, and pipe syntax are all unavailable. Mandatory stopping points: clarify intent and target objects before writing SQL, and present any DDL/DML for approval before executing.

**Pairs with:** `databricks:databricks-unity-catalog`, `databricks:databricks-cli`, `databricks:databricks-etl-pyspark-notebooks`, `databricks:databricks-cost-optimization`.

---

### `databricks:databricks-automation-bundles`

> Manages the full lifecycle of Databricks Declarative Automation Bundles (DAB, formerly Asset Bundles) — infrastructure-as-code projects that define jobs, pipelines, apps, and ML assets in `databricks.yml`.

**Snowflake surface it drives:** none — Databricks IaC. It drives `databricks bundle init|validate|deploy|run|summary|generate|deployment bind|destroy`, `databricks.yml` and `resources/*.yml`, and the resource types `jobs`, `pipelines`, `dashboards`, `experiments`, `registered_models`, `model_serving_endpoints`, `schemas`, `volumes`, `clusters`, `apps`, `quality_monitors`, and `alerts`; plus `artifacts` (Python wheel / JAR builds), `variables`, `permissions`, `targets` with development/production modes, custom bundle templates, and CI/CD integration.

**What it accelerates**
- Standing up a bundle project from a template and knowing which resource keys and blocks are valid, instead of trial-and-error against `databricks.yml` schema errors.
- Walking the lifecycle in the right order (`init → develop → validate → deploy → run → destroy`) with validation before deployment.
- Getting target modes right — `development` vs `production` semantics, per-target overrides, and variable substitution.
- Adopting resources that already exist in a workspace via `bundle generate` and `bundle deployment bind`, rather than re-creating them.
- Setting up permissions blocks and CI/CD pipelines for bundle deploys.
- Building custom bundle templates so a team's conventions are reproducible across projects.
- A serverless environment pattern for jobs that should not carry a cluster spec.

**Representative use cases**
- "Turn our ad-hoc Databricks jobs into version-controlled infrastructure as code."
- "Initialize a bundle project for our ETL pipeline and deploy it to dev."
- "We have a job that was created in the UI — generate bundle config from it and bind it."
- "Set up separate dev and prod targets with different catalogs."
- "Package our Python wheel and deploy it as part of the bundle."
- "Wire bundle deploys into our CI/CD pipeline."
- "Create a reusable bundle template for our team's job conventions."
- "Tear down the dev deployment of this bundle."

**Example prompts**
```
Create a databricks asset bundle for this job
Run bundle validate and deploy to our dev target
Generate bundle config from an existing job
Set up CI/CD for databricks bundle deploys
Destroy the dev bundle deployment
```

**Depth behind it:** `1` supporting file, `no sub-skills` — an 810-line reference covering the 8-step lifecycle plus target modes, variables, permissions, custom templates, CI/CD, a CLI command quick reference, global flags, and the serverless environment pattern.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This skill deploys to Databricks workspaces, not Snowflake. Requires Databricks CLI **v0.218.0+** authenticated (v0.283.0+ for pipelines), workspace files enabled on the remote workspace (DBR 11.3 LTS+), Unity Catalog for most templates, `uv` for Python projects, and JDK 17 + sbt + IntelliJ IDEA for Scala projects. `bundle destroy` is destructive and requires confirmation.

**Pairs with:** `databricks:databricks-etl-pyspark-notebooks`, `databricks:databricks-dbt-pipeline`, `databricks:databricks-cli`, `databricks:databricks-notebook-refactor`.

---

### `databricks:databricks-etl-pyspark-notebooks`

> Builds medallion-architecture ETL pipelines as PySpark `.ipynb` notebooks on Databricks and deploys them as scheduled jobs via Declarative Automation Bundles.

**Snowflake surface it drives:** none — Databricks/Unity Catalog ETL. It drives `spark.read.table("catalog.schema.table")`, `.saveAsTable()`, `df.writeTo(...).using("iceberg")`, Delta UniForm (`delta.universalFormat.enabledFormats='iceberg'`, `delta.enableIcebergCompatV2`), `MERGE INTO` for SCD Type 1 and Type 2, Delta Change Data Feed for incremental reads, `dbutils.widgets` parameterization, serverless vs classic `job_clusters` in `databricks.yml` / `resources/*.yml`, and `databricks bundle validate|deploy|run`.

**What it accelerates**
- Structuring a silver/gold pipeline correctly the first time — a layer table defines what belongs in each stage (schema enforcement, null handling, dedup, type casting, joins for silver; aggregations, KPIs, dimensional models for gold).
- Avoiding a specific serverless failure: `spark.conf.get()` on custom non-`spark.*` keys raises `CONFIG_NOT_AVAILABLE` under Spark Connect, so parameters **must** use `dbutils.widgets`, which works on both serverless and classic.
- Choosing the target format deliberately — Delta by default, Iceberg (native or via UniForm) when cross-platform interoperability with Snowflake, Spark OSS, or Trino matters, with the exact `TBLPROPERTIES` to set.
- Ready-made recipes for parameterized notebooks, multi-source joins, incremental merge (SCD Type 1), SCD Type 2, Change Data Feed incremental reads, and retry/alerting.
- Scaffolding a deployable project layout (`databricks.yml`, `resources/`, `src/*.ipynb`, `tests/`) and taking it through validate → deploy → run rather than leaving notebooks unscheduled.
- Optional data quality checks as a distinct pipeline step.

**Representative use cases**
- "Build a silver and gold layer on top of our raw Unity Catalog tables."
- "We need an hourly ETL job that cleans and deduplicates our orders data."
- "Write the merge logic so this dimension keeps history — SCD Type 2."
- "Our downstream tools read Iceberg; make these output tables readable from Snowflake too."
- "Only process rows that changed since the last run."
- "Parameterize this notebook so we can run it against dev and prod catalogs."
- "Deploy this pipeline as a scheduled job with retries and failure alerts."
- "Should this run on serverless or a job cluster?"

**Example prompts**
```
Build an ETL pipeline with medallion architecture on Databricks
Write a PySpark notebook that transforms these Unity Catalog tables
Create a gold layer with aggregates and deploy it as a job
Implement SCD Type 2 with Delta merge
Write this ETL output as an Iceberg table
```

**Depth behind it:** `1` supporting file, `no sub-skills` — a 623-line workflow with 7 steps plus a Patterns and Recipes section (parameterized notebooks, multi-source joins, SCD Type 1 merge, SCD Type 2, Change Data Feed, retry/alerting).

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This skill writes PySpark against Databricks Unity Catalog rather than Snowflake. Requires Databricks CLI installed and authenticated and Unity Catalog enabled with source data already present. Explicitly **scoped to transformation and aggregation only** — the skill assumes source data already exists as UC tables and defers ingestion to future ingestion-focused skills. Mandatory stopping point before writing any code, to establish source tables, target format, silver/gold catalogs and schemas, transformation goals, and write mode.

**Pairs with:** `databricks:databricks-unity-catalog`, `databricks:databricks-automation-bundles`, `databricks:databricks-local-testing`, `databricks:databricks-notebook-refactor`, `databricks:databricks-spark-performance`.

---

### `databricks:databricks-dbt-pipeline`

> Builds end-to-end dbt-core pipelines on Databricks — scaffolding, `profiles.yml` connection setup, model authoring, tests, and production deployment as a dbt task inside a Lakeflow Job via DAB.

**Snowflake surface it drives:** none — this is dbt on Databricks, not `dbt-projects-on-snowflake`. It drives `databricks bundle init dbt-sql`, `dbt init|deps|seed|run|test|build`, `dbt-core` + `dbt-databricks`, `profiles.yml` (`type: databricks`, `method: http`, `http_path: /sql/1.0/warehouses/<id>`, `catalog`, `schema`, `threads`), `dbt_project.yml`, DAB dbt tasks in `resources/*.job.yml`, and `databricks bundle validate|deploy`.

**What it accelerates**
- Getting the two-compute-layer model right, which is the usual source of confusion: the dbt CLI compute runs the Python process (Jinja compilation, graph resolution) on serverless or a job cluster, while a **separate serverless or pro SQL warehouse** executes the generated SQL.
- Scaffolding from the `dbt-sql` DAB template with its personal/shared catalog and default schema prompts, so dev and prod separation exists from the start — or wrapping an existing `dbt init` project in a bundle instead.
- Writing `profiles.yml` correctly for both paths — local development with `env_var('DATABRICKS_TOKEN')`, and production where the DAB dbt task injects the token automatically.
- A stated development/production split: iterate locally with `dbt run` / `dbt test` against a warehouse, then deploy as a scheduled dbt task.
- Multi-task workflow composition (`dbt deps` → `dbt seed` → `dbt run`) and CI/CD wiring through DAB.
- dbt test authoring as an explicit step rather than an afterthought.

**Representative use cases**
- "Set up a dbt project on Databricks and deploy it as a scheduled job."
- "Our dbt runs locally — get it into production on Databricks."
- "Configure `profiles.yml` to point dbt at our serverless SQL warehouse."
- "Build medallion-style dbt models with staging and mart layers."
- "Add dbt tests and make the job fail when they fail."
- "Split our dbt job into deps, seed, run, and test tasks."
- "Wire dbt into our CI/CD so PRs get validated."
- "Use separate dev and prod catalogs for our dbt models."

**Example prompts**
```
Build a dbt pipeline on Databricks
Set up a dbt project with a DAB and deploy it
Configure profiles.yml for dbt on Databricks
Add dbt tests and schedule dbt run as a job
Create a multi-task dbt workflow with deps, seed, and run
```

**Depth behind it:** `1` supporting file, `no sub-skills` — a 545-line 9-step workflow from scaffolding through CI/CD.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This targets dbt on Databricks, not Snowflake — for dbt deployed into Snowflake use `dbt-projects-on-snowflake`. Requires Databricks CLI v0.218.0+ authenticated, Unity Catalog enabled, a **serverless or pro** SQL warehouse (classic will not work for dbt SQL execution), Python 3.8+ with `dbt-core` and `dbt-databricks` installed locally, and a **Git repository — required for dbt job tasks**. Mandatory stopping point to confirm template-vs-manual scaffolding and the target catalog/schema.

**Pairs with:** `databricks:databricks-automation-bundles`, `databricks:databricks-unity-catalog`, `databricks:databricks-dbsql`, `dbt-projects-on-snowflake`.

---

### `databricks:databricks-notebook-refactor`

> Guided refactoring of monolithic Databricks notebooks into modular Python packages — extracting testable `.py` modules, replacing `%run` chains with imports, parameterizing hardcoded values, and leaving a thin orchestrator notebook.

**Snowflake surface it drives:** none — Databricks notebook engineering. It works on `.ipynb` / `.py` notebook source, `%run` / `%sql` / `%scala` / `%r` magics, `dbutils.widgets` / `dbutils.secrets` / `dbutils.fs` / `dbutils.notebook`, `spark.read.table` / `spark.sql` / `MERGE INTO`, `display()`, workspace-file `sys.path` behavior (DBR 11.3+ and 14.0+), Git folders, `__init__.py` packaging, `if __name__ == "__main__"` guards, `%load_ext autoreload` / `%autoreload 2`, and `notebook_task.notebook_path` in `databricks.yml`.

**What it accelerates**
- Naming the actual failure modes of monolithic notebooks (untestable `dbutils`/`spark` globals, copy-paste duplication, `%run` spaghetti, merge conflicts, no IDE/linting support) so the refactor has a stated goal.
- A pattern-by-pattern translation table: `%run ./utils` → `from src.utils import ...`, top-level `dbutils.widgets.get()` → function parameter, inline `spark.read.table()` → an I/O helper, implicit cross-cell globals → explicit return values.
- Getting imports to actually resolve — DBR 14.0+ puts the notebook's directory on `sys.path` automatically, DBR 11.3–13.x may need an explicit `sys.path.insert`, and Git folders add the repo root.
- A clean target layout (`src/` modules, `notebooks/orchestrator.ipynb`, `tests/`, `pyproject.toml`) with one responsibility per module and naming conventions for `transforms.py`, `validators.py`, `io_helpers.py`, `config.py`, `constants.py`.
- The hard rule that makes the result testable: no `spark`, `dbutils`, or `display` as globals in library code — always parameters.
- A verification loop — local pytest, a cluster run of the orchestrator, and an output diff against the original notebook to confirm no regressions.

**Representative use cases**
- "This notebook is 500 lines and nobody can test it — break it up."
- "We have the same transform copy-pasted across five notebooks."
- "Our `%run` chain is three levels deep and impossible to trace."
- "Two people keep hitting merge conflicts on the same notebook."
- "Make this notebook production-ready and CI/CD-friendly."
- "Extract the business logic so we can unit test it without a cluster."
- "Convert the `%sql` cells into Python functions."
- "We refactored and now the bundle deploy fails — fix the paths."

**Example prompts**
```
Refactor this notebook into modules
Modularize my Databricks notebook code
Migrate our %run chain to imports
This notebook is too big — split it into a package
Make this notebook production-ready and testable
```

**Depth behind it:** `1` supporting file, `no sub-skills`.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This refactors Databricks notebooks, not Snowflake code. Requires Databricks CLI installed and authenticated, notebooks in `.ipynb` or `.py` source form, and familiarity with `databricks-local-testing` for post-refactor tests. Two mandatory stopping points: before analyzing anything (notebook paths, goal, DBR version, `%run` structure, deployment method), and before writing any code — the user must approve the proposed module structure. `%autoreload` is a development aid and should be removed for production. Bundle projects need `notebook_task.notebook_path` updated and `src/` added to workspace sync.

**Pairs with:** `databricks:databricks-local-testing`, `databricks:databricks-etl-pyspark-notebooks`, `databricks:databricks-automation-bundles`.

---

### `databricks:databricks-local-testing`

> Generates pytest suites that run Databricks PySpark code locally with no cluster — mocking `dbutils`, providing a local `SparkSession` fixture, stubbing `display()`, and asserting on DataFrames.

**Snowflake surface it drives:** none — local Python/PySpark testing for Databricks code. It produces `tests/conftest.py`, `tests/test_<module>.py`, and `pytest.ini`; uses `pytest`, `unittest.mock.MagicMock`, `SparkSession.builder.master("local[*]")`, `pyspark.testing.utils.assertDataFrameEqual` / `assertSchemaEqual`, `chispa`, optional `databricks-connect`, and mocks `dbutils.fs.ls|cp|mv|rm|mkdirs`, `dbutils.secrets.get`, `dbutils.widgets.get|text`, and `dbutils.notebook.run`.

**What it accelerates**
- Making Databricks code testable at all — `dbutils`, `spark`, and `display()` are cluster-injected globals that do not exist locally, so any code touching them fails outside the workspace until it is refactored to dependency injection.
- A per-API mock strategy table (FileInfo namedtuples for `fs.ls`, `side_effect` dict lookups for `secrets.get` and `widgets.get`, no-op mocks for `widgets.text`, capture-to-list for `display`) instead of guessing at mock shapes.
- A ready `conftest.py` with a session-scoped local Spark fixture tuned for fast startup (`shuffle.partitions=1`, `default.parallelism=1`).
- Scanning the user's code first and reporting exactly which Databricks APIs are in play, so the generated fixtures are populated with real widget and secret names.
- Catching logic errors before cluster round-trips and enabling CI/CD (a GitHub Actions snippet is included).
- A troubleshooting table for the real blockers: missing `JAVA_HOME`, undefined `dbutils`/`spark`/`display`, `CONFIG_NOT_AVAILABLE` from `spark.conf.get()` on serverless, `No module named 'src'`, `assertDataFrameEqual` missing on older PySpark, and local-vs-DBR version drift.

**Representative use cases**
- "Write unit tests for our PySpark transforms that run without a cluster."
- "Our code reads secrets and widgets — how do we test that locally?"
- "Set up pytest for this Databricks project."
- "Add Databricks tests to our CI pipeline."
- "Tests pass locally but fail on the cluster — why?"
- "How do we assert two DataFrames are equal?"
- "Mock `dbutils.fs` so we can test the file-handling code."

**Example prompts**
```
Write unit tests for my Databricks PySpark code
Mock dbutils so I can test locally
Set up pytest for this Databricks project without a cluster
Generate conftest fixtures for spark and dbutils
Add Databricks tests to CI/CD
```

**Depth behind it:** `1` supporting file, `no sub-skills`.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This tests Databricks PySpark code, not Snowflake code. External dependencies: Python 3.10+, `pytest`, and `pyspark` installed locally — **PySpark requires Java 8, 11, or 17 on PATH** with `JAVA_HOME` set. Optional `databricks-connect` for integration tests against a real cluster, and `chispa` or `pyspark.testing.utils` for DataFrame comparison. `assertDataFrameEqual` requires PySpark 3.5+ (DBR 14.2+). Local Spark can behave differently from DBR, so PySpark should be pinned to match the runtime. Mandatory stopping points: before scanning (what code, which APIs, existing tests, unit vs integration scope) and before writing test files to disk.

**Pairs with:** `databricks:databricks-notebook-refactor`, `databricks:databricks-etl-pyspark-notebooks`, `databricks:databricks-automation-bundles`.

---

### `databricks:databricks-spark-performance`

> Metrics-driven diagnosis and remediation of slow Spark jobs on Databricks — triage the slow stage, read the metrics, classify the bottleneck, apply targeted fixes, validate, estimate the cost impact, and harden.

**Snowflake surface it drives:** none — Spark/Databricks performance tuning. It drives `databricks jobs get-run`, `databricks jobs list`, `databricks clusters get` (`spark_version`, `node_type_id`, `num_workers`, `autoscale`, `spark_conf`), the Spark UI, `spark.sql.shuffle.partitions`, `spark.sql.autoBroadcastJoinThreshold`, Adaptive Query Execution (including skew join optimization), Photon, salting/repartition strategies, Kryo serialization, file sizing and Z-ORDER, and `system.billing.usage` for DBU-based savings math.

**What it accelerates**
- Replacing guesswork with thresholds — a bottleneck table gives the key metric and healthy target for each class: shuffle < 1 GB per stage, max task duration < 2× median, spill ratio < 0.1, broadcast candidate < 100 MB, GC < 10% of task time, scan < 30% of stage.
- Sizing shuffle partitions from a formula rather than folklore: `N = ceil(shuffle_data_MB / 128 / total_cores) × total_cores`, with worked examples for both multi-node and single-node (`local[*, N]`) clusters.
- Version-aware defaults, so a fix is not applied that the runtime already does — AQE on by default at DBR 12.2+, Photon available on all-purpose at 13.3+, AQE skew join on at 14.0+, Photon on by default at 15.0+, enhanced AQE coalescing at 16.0+.
- Raising `autoBroadcastJoinThreshold` from its 10 MB default to 100 MB–1 GB when driver memory allows, up to the 8 GB max.
- Closing the loop: a validation phase that re-runs the job and compares before/after metrics with a regression check.
- Translating a speedup into money — pulling run frequency and historical DBU consumption from `system.billing.usage` and presenting a filled-in cost impact summary.
- A hardening phase so the fix survives in configuration rather than living in someone's notebook session.

**Representative use cases**
- "This Spark job used to take 20 minutes and now takes two hours."
- "One task in the stage runs 10× longer than the rest."
- "We're spilling to disk — do we need a bigger cluster or more partitions?"
- "This join is shuffling everything; should it be a broadcast?"
- "Help me read the Spark UI for this run and find the bottleneck."
- "The job keeps OOM-ing on the driver."
- "Is Photon worth enabling for this workload?"
- "We sped the job up 40% — how much does that actually save us per month?"

**Example prompts**
```
Why is my Spark job slow?
Diagnose data skew and spill in this job run
Tune spark.sql.shuffle.partitions for this workload
Help me read the Spark UI and find the bottleneck stage
Should I enable Photon for this job?
```

**Depth behind it:** `1` supporting file, `no sub-skills` — a 656-line 7-phase workflow (Triage, Diagnose, Classify, Apply Fixes, Validate, Estimate Cost Impact, Harden).

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This tunes Spark on Databricks, not Snowflake warehouses. Requires an authenticated Databricks CLI (`databricks auth describe`; failures route to `databricks-cli-install`), permission to view the target cluster's Spark UI, a **specific** slow job run ID / notebook / query to diagnose, and the cluster's DBR version. Cost estimation needs `system.billing.usage`, which requires Unity Catalog and `system` catalog access. Mandatory stopping point: confirm the job run ID or query with the user before pulling metrics — do not guess which job to diagnose.

**Pairs with:** `databricks:databricks-cli`, `databricks:databricks-cost-optimization`, `databricks:databricks-etl-pyspark-notebooks`, `databricks:databricks-dbsql`.

---

### `databricks:databricks-cost-optimization`

> Router skill for Databricks cost work: detects which cost domain the user cares about and loads one of five sub-skills covering monitoring/governance, cluster compute, SQL warehouses, streaming/workload design, and ML/GPU compute.

**Snowflake surface it drives:** none — Databricks cost management. Across its sub-skills it drives `system.billing.usage`, resource tagging and cost attribution, account-level budgets and spending alerts, cost dashboards, compute policies, job vs all-purpose compute, autoscaling and auto-termination, instance type and fleet selection, spot instances, cluster pools, Photon cost-benefit, T-shirt sizing, serverless vs pro vs classic SQL warehouses, Intelligent Workload Management (IWM), warehouse auto-stop, continuous vs triggered vs batch streaming (`availableNow`), Delta maintenance (`OPTIMIZE`, `VACUUM`, `Z-ORDER`, liquid clustering), runtime version selection, GPU audits, ML training compute, and Mosaic AI model serving scaling; verified via `databricks auth describe`.

**What it accelerates**
- Starting a cost engagement in the right place — a trigger-to-sub-skill routing table, with a "full audit" path that begins at cost monitoring to find the biggest drivers and then routes based on findings.
- Grounding the conversation in actual spend from `system.billing.usage` rather than intuition, broken down by SKU, workspace, and tag over 30 days.
- Separating the five genuinely different cost levers so advice is specific: cluster compute right-sizing is not the same problem as warehouse idle time, always-on streaming, or idle GPUs.
- Producing prioritized recommendations with estimated savings and before/after cost projections, not just a list of observations.
- Leaving ongoing control behind — tags, budgets, and dashboards — so the savings do not regress.
- Stating the privilege reality up front: budgets are an **account admin** feature that workspace admin cannot cover, and compute policies need workspace admin.

**Representative use cases**
- "Our Databricks bill jumped last month — find out why."
- "We want a full cost audit with prioritized recommendations."
- "Which clusters are the most expensive, and can we right-size them?"
- "Should these workloads be on job compute instead of all-purpose?"
- "Our SQL warehouses sit idle half the day."
- "This streaming job runs 24/7 — could it be triggered instead?"
- "Audit our GPU clusters; I suspect some don't need GPUs."
- "Set up tagging and budget alerts so each team sees its own spend."

**Example prompts**
```
Reduce our Databricks costs
Run a full Databricks cost audit
Our clusters are too expensive — right-size them
Set up cost attribution tagging and budget alerts
Audit unnecessary GPU usage in our workspace
```

**Depth behind it:** `6` supporting files, `5` sub-skills (`cost-monitoring-governance`, `cluster-compute`, `sql-warehouses`, `streaming-workloads`, `ml-gpu-compute`) — each a standalone `SKILL.md` (214–275 lines) declaring `parent_skill: databricks-cost-optimization`.

**Prerequisites & caveats:** The `databricks` plugin ships bundled with Cortex Code but is **DISABLED by default** — enable it with `/plugin` or `cortex plugin activate databricks` before this skill can be used. This analyzes Databricks spend, not Snowflake credits — for Snowflake use `cost-intelligence` or `billing`. Requires an authenticated Databricks CLI (`databricks auth describe`; failures route to `databricks-cli-install`) and **Unity Catalog enabled** for `system.billing.usage`. Account admin or workspace admin is needed for billing system tables, compute policies, and budgets — budgets specifically require **account** admin, and workspace admin is not sufficient. Some steps work with lesser privileges. Mandatory stopping point: confirm the focus area with the user before loading any sub-skill.

**Pairs with:** `databricks:databricks-spark-performance`, `databricks:databricks-cli`, `databricks:databricks-dbsql`, `cost-intelligence`.


---

## Appendix A — Scope: what is and is not in this catalog

### Included — ships with a default CoCo install

| Source | Count | Status | Location |
|--------|-------|--------|----------|
| Bundled Snowflake skills | 78 | enabled | `<cortex-install>/bundled_skills/` |
| Plugin `data` (Airflow / Astronomer) | 18 | bundled, **enabled** | `<cortex-install>/bundled_plugins/airflow/skills/` |
| Plugin `databricks` | 12 | bundled, **disabled** | `<cortex-install>/bundled_external_plugins/databricks/skills/` |
| Plugin `blueprints` | 3 | bundled, **disabled** | `<cortex-install>/bundled_external_plugins/blueprints/skills/` |
| **Total default skills** | **111** | | |
| Nested sub-skills beneath the above | ~530 | | |

`databricks` and `blueprints` are present in every CoCo install but ship **disabled**.
Enable them with `/plugin` or `cortex plugin activate <name>`. They are included here
because a partner receives them with the product — but do not demo them without enabling
them first.

### Excluded — locally installed, not part of the product

The following were present in the environment this catalog was generated from, but are
**not** documented above, because a partner installing CoCo would not have them:

| Excluded | Why |
|----------|-----|
| Plugin `superpowers` (14 skills) | Third-party, user-installed from `github:obra/superpowers` |
| Plugin `snowflake-migration` (1 skill, 44 nested) | User-installed from `github:Snowflake-Labs/cortex-code-migrations` |
| Plugin `playwright-mcp` | User-installed; contributes an MCP server, no skills |
| Remote skills `xlsx`, `pptx` | Pulled from third-party GitHub repositories |
| Stage skills `coco-pitch`, `google-workspace-install`, `pse-uc-portfolio-analysis` | Published to Snowflake stages by individual users |

**Do not position any of the above as a CoCo capability in a partner conversation.** Several
are genuinely useful — `snowflake-migration` in particular — but they are add-ons the
partner would install separately. If you want to show them, show them as an example of
*extensibility* (see `find-skill-and-plugin` and `share-skill-and-plugin`), not as
out-of-the-box function.

Beyond these, many more skills are published and installable. Search the catalog with
`cortex search object "<query>" --types=skill` or `cortex skill find`, and install with
`cortex skill add`.

## Appendix B — Using this catalog to match customer use cases

The intended workflow for matching an SE's field notes or a customer's stated use case to
the right skills:

1. **Load the use-case text** — Salesforce/Jira/Gong notes, a discovery doc, or a CSV of
   opportunity descriptions — into a Snowflake table.
2. **Load this catalog's index** as reference text. The `Snowflake surface it drives` and
   `Representative use cases` fields are written specifically to be matched against.
3. **Match with Cortex AI functions:**
   - `AI_CLASSIFY` when you want each use case assigned to a fixed category or skill list.
   - `AI_COMPLETE` when you want a ranked recommendation with a stated rationale.
   - `AI_EMBED` + `VECTOR_COSINE_SIMILARITY` for fuzzy top-N retrieval over many rows.
   - `AI_FILTER` to isolate the subset of notes that describe a given problem class.
4. **Review and publish** the matched output as an HTML report or a Streamlit app, so the
   partner sees their *own* pipeline mapped to specific accelerators.

The `cortex-ai-function-studio` skill covers step 3 in detail; `ai-functions-pipeline-builder`
covers making it recurring.

## Appendix C — Regenerating this document

This catalog was generated from the installed skill files. To refresh after a CoCo upgrade:

```
python3 assemble.py     # rebuilds COCO_SKILLS.md from frag/*.md
```

Skill contents change between Cortex Code releases. Regenerate after `/update` before
reusing this document externally, and confirm preview/GA status of any feature you plan to
position in a customer conversation.
