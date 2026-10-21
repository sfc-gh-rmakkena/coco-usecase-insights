"""Deterministic Technical Use Case -> Snowflake capability mapping (pse-uc-implementation-plan skill table)."""
import functools
import json

from .assets import _ASSETS, grounding_links

# (technical use case, primary capabilities, key CoCo skills, grounding keys) — skill table order.
MAPPING = [
    ("DE: Ingestion", "OpenFlow, Snowpipe, Snowpipe Streaming, COPY INTO",
     ["openflow", "snowpipe", "snowpipe-streaming", "copy-load"], ["openflow", "snowpipe", "snowpipe_streaming", "copy_into"]),
    ("DE: Transformation", "Dynamic Tables, Tasks, Snowpark, dbt",
     ["dynamic-tables", "snowflake-tasks", "snowpark-python", "dbt-projects-on-snowflake"], ["dynamic_tables", "tasks", "snowpark", "dbt"]),
    ("DE: Interoperable Storage", "Iceberg Tables, External Tables, Catalog Integrations", ["iceberg"], ["iceberg"]),
    ("Analytics: Applied Analytics", "Semantic Views, Cortex Agent, Cortex Analyst",
     ["agent-studio"], ["semantic_views", "cortex_agents", "cortex_analyst"]),
    ("Analytics: Interactive Analytics", "Interactive Tables, Interactive Warehouses", ["snowflake-interactive"], ["interactive"]),
    ("Analytics: Business Intelligence", "Semantic Views, Cortex Agent, BI Connectors", ["agent-studio"], ["semantic_views", "cortex_agents"]),
    ("Analytics: Migrations", "SnowConvert, Migration Assessment, Spark Migration",
     ["spark-migration", "snowflake-migration"], ["migrations"]),
    ("Analytics: Lakehouse Analytics", "Iceberg, Snowflake Notebooks, Spark on SPCS", ["iceberg", "snowflake-notebooks"], ["iceberg", "notebooks"]),
    ("AI: Machine Learning", "Snowpark ML, Model Registry, Feature Store", ["machine-learning"], ["ml"]),
    ("AI: Conversational Assistants", "Cortex Agent, Semantic Views, Cortex Search",
     ["agent-studio"], ["cortex_agents", "semantic_views", "cortex_search"]),
    ("AI: Cortex AI Functions", "AI_COMPLETE, AI_EXTRACT, AI_CLASSIFY, etc.", ["cortex-ai-function-studio"], ["ai_functions"]),
    ("AI: Agents / Snowflake Intelligence", "Cortex Agent, MCP, Tool Use", ["agent-studio"], ["cortex_agents"]),
    ("AI: Document Intelligence", "AI_PARSE_DOCUMENT, AI_EXTRACT, Pipelines",
     ["document-intelligence", "ai-functions-pipeline-builder"], ["document_ai"]),
    ("Apps & Collab: Build", "Native Apps, Streamlit, SAR Apps",
     ["native-app-provider", "developing-with-streamlit-in-snowflake", "snowflake-apps"], ["apps"]),
    ("Apps & Collab: External Collaboration", "Data Clean Rooms, Secure Sharing", ["data-cleanrooms", "data-sharing"], ["collaboration"]),
    ("Platform: Compliance & Governance", "Tags, Policies, Classification, Access History", ["data-governance"], ["governance"]),
    ("Platform: Financial Operations", "Cost Intelligence, Budgets, Resource Monitors", ["cost-intelligence"], ["cost"]),
    ("Platform: Observability", "Query Perf, Data Quality, DMFs",
     ["workload-performance-analysis", "data-quality"], ["observability", "search_optimization"]),
]
# Platform capabilities the plan may use when the use case warrants it (not required).
OPTIONAL = ["governance", "search_optimization", "observability", "cost"]


def _norm(s):
    return " ".join(str(s or "").lower().replace("&", "and").split())


def _rows_for(tuc):
    n = _norm(tuc)
    exact = [r for r in MAPPING if _norm(r[0]) == n]
    if exact:
        return exact
    # Unlisted values (e.g. "Apps & Collab: Internal Collaboration") match rows sharing the
    # category prefix and the last word of the name.
    cat, _, name = n.partition(":")
    last = name.split()[-1] if name.split() else ""
    return [r for r in MAPPING if last and _norm(r[0]).partition(":")[0] == cat
            and _norm(r[0]).split()[-1] == last]


def matched_rows(technical_use_case) -> list:
    """Mapping rows for a semicolon-separated TECHNICAL_USE_CASE value, in skill-table order."""
    vals = [v for v in str(technical_use_case or "").split(";") if v.strip()]
    hit = {id(r) for v in vals for r in _rows_for(v)}
    return [r for r in MAPPING if id(r) in hit]


def required_capabilities(technical_use_case) -> list:
    """Ordered, de-duplicated grounding keys for the use case's technical use cases."""
    out = []
    for r in matched_rows(technical_use_case):
        out += [k for k in r[3] if k not in out]
    return out


def required_skills(technical_use_case) -> list:
    out = []
    for r in matched_rows(technical_use_case):
        out += [s for s in r[2] if s not in out]
    return out


def capability_table(technical_use_case) -> list:
    return [{"technical_use_case": r[0], "capabilities": r[1], "coco_skills": r[2]} for r in matched_rows(technical_use_case)]


@functools.lru_cache(maxsize=None)
def grounding() -> dict:
    return json.loads((_ASSETS / "grounding.json").read_text(encoding="utf-8"))


def grounding_for(keys) -> dict:
    g = grounding()
    return {k: g[k] for k in keys if k in g}


@functools.lru_cache(maxsize=None)
def grounding_urls() -> frozenset:
    return frozenset(grounding_links(grounding()))
