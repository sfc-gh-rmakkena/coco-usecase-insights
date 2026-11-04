"""Deterministic Technical Use Case -> Snowflake capability mapping (pse-uc-implementation-plan skill table)."""
import functools
import json
import re

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


# Grounding key -> (display label, architecture layer, match aliases). Aliases are matched
# case-insensitively as substrings of layer capabilities / component names.
CAPS = {
    "openflow": ("Openflow", "Ingestion", ["openflow"]),
    "snowpipe": ("Snowpipe", "Ingestion", ["snowpipe"]),
    "snowpipe_streaming": ("Snowpipe Streaming", "Ingestion", ["snowpipe streaming"]),
    "copy_into": ("COPY INTO", "Ingestion", ["copy into"]),
    "migrations": ("SnowConvert", "Ingestion", ["snowconvert", "migration"]),
    "iceberg": ("Iceberg Tables", "Bronze", ["iceberg"]),
    "dynamic_tables": ("Dynamic Tables", "Silver", ["dynamic table"]),
    "tasks": ("Tasks", "Silver", ["task"]),
    "snowpark": ("Snowpark", "Silver", ["snowpark"]),
    "dbt": ("dbt Projects on Snowflake", "Silver", ["dbt"]),
    "search_optimization": ("Search Optimization", "Gold", ["search optimization"]),
    "semantic_views": ("Semantic Views", "Semantic", ["semantic view"]),
    "cortex_analyst": ("Cortex Analyst", "Semantic", ["cortex analyst"]),
    "cortex_agents": ("Cortex Agents", "Consumption", ["cortex agent", "snowflake intelligence"]),
    "cortex_search": ("Cortex Search", "Consumption", ["cortex search"]),
    "interactive": ("Interactive Tables", "Consumption", ["interactive"]),
    "notebooks": ("Snowflake Notebooks", "Consumption", ["notebook"]),
    "ml": ("Snowpark ML", "Consumption", ["ml", "model registry", "feature store"]),
    "ai_functions": ("Cortex AI Functions", "Consumption", ["ai function", "ai_complete", "cortex ai"]),
    "document_ai": ("AI_PARSE_DOCUMENT", "Consumption", ["parse_document", "document"]),
    "apps": ("Streamlit in Snowflake", "Consumption", ["streamlit", "native app"]),
    "collaboration": ("Internal Marketplace", "Sharing",
                      ["internal marketplace", "secure data sharing", "secure shar", "clean room", "listing"]),
    "governance": ("Row Access Policies", "Governance", ["row access", "masking", "governance", "tag"]),
    "cost": ("Budgets", "Governance", ["budget", "resource monitor"]),
    "observability": ("Data Metric Functions", "Governance", ["data metric", "data quality", "dmf"]),
}


def cap_label(key) -> str:
    return CAPS.get(key, (str(key), "", []))[0]


def cap_layer(key) -> str:
    return CAPS.get(key, ("", "Consumption", []))[1]


def cap_matches(key, text) -> bool:
    """True if `text` names capability `key` (label or any alias, case-insensitive)."""
    t = str(text or "").lower()
    label, _, aliases = CAPS.get(key, (str(key), "", []))
    return any(a and (a in t if len(a) > 3 else re.search(r"\b" + re.escape(a) + r"\b", t))
               for a in [label.lower()] + aliases)


def status_from_note(note) -> str:
    """Short status label from a grounding status_note."""
    n = str(note or "")
    if re.search(r"generally available|\bGA\b", n, re.I):
        return "Generally Available"
    if re.search(r"private preview|\bPrPr\b", n, re.I):
        return "Private Preview"
    if re.search(r"preview", n, re.I):
        return "Public Preview"
    return "See documentation"


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
