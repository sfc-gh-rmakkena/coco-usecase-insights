"""
Shared CoCo skill-mapping logic for the PSE Email pages.

This module deliberately contains NO Streamlit UI calls so it can be imported
from multiple pages without side effects. Page scripts execute their whole body
on import, so shared logic must never live in a page file.

── Ported verbatim from PSE_UC_PORTFOLIO_ANALYSIS skill ──────────────────────
Source: snow://cortex_extension/USER$DSHAVKANI.SKILL_SHARING_89F4D7DE.
        PSE_UC_PORTFOLIO_ANALYSIS/versions/version$3/skills/
        pse-uc-portfolio-analysis/scripts/analyze_use_cases.py
Deterministic dict lookup — no LLM call, no drift from the source skill.
"""

import html as html_lib

from utils import (
    APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, LATAM_RSI_REGION_MAP,
    PARTNER_ALIASES as _PA,
)

MIGRATION_KEYWORDS = [
    "migrat", "hadoop", "dbx", "emr", "spark", "sas replacement",
    "databricks replacement", "mysql", "mongodb", "oracle", "teradata",
    "redshift", "sql server", "netezza", "edw", "hana",
]

SPARK_KEYWORDS = ["spark", "dbx", "emr", "hadoop", "databricks"]

TECH_UC_SKILL_MAP = {
    "DE: Ingestion":                                          ["openflow", "snowpipe-streaming", "snowpark-python"],
    "DE: Transformation":                                     ["snowpark-python", "dynamic-tables", "dbt-data-modeling"],
    "DE: Interoperable Storage":                               ["iceberg", "dynamic-tables"],
    "Analytics: Applied Analytics":                            ["semantic-view", "dashboard"],
    "Analytics: Interactive Analytics":                        ["rec-interactive", "snowflake-interactive"],
    "Analytics: Business Intelligence":                        ["semantic-view", "dashboard", "snowflake-notebooks"],
    "Analytics: Migrations":                                   ["migration-guide", "snowconvert-assessment"],
    "Analytics: Lakehouse Analytics":                          ["iceberg", "snowflake-notebooks"],
    "AI: Machine Learning":                                    ["machine-learning"],
    "AI: Conversational Assistants":                           ["cortex-agent"],
    "AI: Cortex AI Functions":                                 ["cortex-ai-functions"],
    "AI: Agents":                                              ["cortex-agent", "agent-optimization"],
    "AI: Snowflake Intelligence & Agents":                     ["cortex-agent", "agent-optimization"],
    "Apps & Collab: Build":                                    ["native-app-provider", "developing-with-streamlit"],
    "Apps & Collab: External Collaboration":                   ["data-cleanrooms", "data-sharing"],
    "Platform: Storage":                                       ["iceberg", "storage-lifecycle-policy"],
    "Platform: Compliance, Security, Discovery & Governance":  ["data-governance", "trust-center", "lineage"],
    "Platform: Financial Operations":                          ["cost-intelligence"],
    "Platform: Observability":                                 ["workload-performance-analysis", "data-quality"],
    "Platform: Horizon Catalog":                               ["lineage", "data-governance"],
}


def detect_migration(name: str, tech_uc: str, extra_text: str = ""):
    """Return (is_migration, list_of_signals). `extra_text` (e.g. SE_COMMENTS)
    widens the keyword scan beyond the structured name/tech_uc fields, since
    SEs often note the actual legacy platform being replaced in free text
    that never makes it into the Technical Use Case taxonomy field."""
    combined = f"{name} {tech_uc} {extra_text}".lower()
    signals = []
    for kw in MIGRATION_KEYWORDS:
        if kw in combined:
            signals.append(kw)
    if "Analytics: Migrations" in tech_uc:
        if "Analytics:Migrations" not in signals:
            signals.append("Analytics:Migrations")
    return bool(signals), signals


def map_coco_skills(tech_uc: str, is_migration: bool, migration_signals: list) -> list:
    """Map Technical Use Case field to CoCo skills."""
    skills = set()
    for part in (tech_uc or "").split(";"):
        part = part.strip()
        for key, skill_list in TECH_UC_SKILL_MAP.items():
            if key in part:
                skills.update(skill_list)
    if is_migration:
        skills.update(["migration-guide", "snowconvert-assessment"])
        if any(kw in " ".join(migration_signals) for kw in SPARK_KEYWORDS):
            skills.update(["spark-migration", "snowpark-connect"])
    return sorted(skills)


def h(text) -> str:
    """HTML-escape a value."""
    return html_lib.escape(str(text or ""))


def map_coco_skills_explained(name: str, tech_uc: str, se_comments: str = "") -> dict:
    """
    Runs the exact same rules as map_coco_skills() but records the trigger for
    each skill. `se_comments` widens migration detection to free-text SE notes
    (see detect_migration) without affecting the structured TECH_UC_SKILL_MAP
    matching, which stays scoped to the taxonomy field only. Returns:
      {
        "skills":       [sorted skill tags],
        "reasons":      {skill: [reason strings]},
        "is_migration": bool,
        "signals":      [matched migration keywords],
        "matched_cats": [tech UC categories that matched],
        "unmatched":    [tech UC segments with no rule],
      }
    """
    tech_uc = tech_uc or ""
    is_mig, signals = detect_migration(name, tech_uc, se_comments)

    reasons: dict = {}
    matched_cats: list = []
    unmatched: list = []

    for part in tech_uc.split(";"):
        part = part.strip()
        if not part:
            continue
        hit = False
        for key, skill_list in TECH_UC_SKILL_MAP.items():
            if key in part:
                hit = True
                if key not in matched_cats:
                    matched_cats.append(key)
                for s in skill_list:
                    reasons.setdefault(s, []).append(f"Tech UC category &rarr; <b>{h(key)}</b>")
        if not hit:
            unmatched.append(part)

    if is_mig:
        kw_list = ", ".join(signals)
        for s in ("migration-guide", "snowconvert-assessment"):
            reasons.setdefault(s, []).append(
                f"Migration detected &rarr; keyword(s) <b>{h(kw_list)}</b> in UC name / tech field / SE notes"
            )
        joined = " ".join(signals)
        spark_hits = [kw for kw in SPARK_KEYWORDS if kw in joined]
        if spark_hits:
            for s in ("spark-migration", "snowpark-connect"):
                reasons.setdefault(s, []).append(
                    f"Spark-family migration &rarr; matched <b>{h(', '.join(spark_hits))}</b>"
                )

    return {
        "skills":       sorted(reasons.keys()),
        "reasons":      reasons,
        "is_migration": is_mig,
        "signals":      signals,
        "matched_cats": matched_cats,
        "unmatched":    unmatched,
    }


def theater_label(theater: str) -> str:
    t = (theater or "").upper()
    if any(x in t for x in ("AMS", "USM", "USPUB", "MAJORS", "EXPANSION", "ACQUISITION")):
        return "AMS"
    if any(x in t for x in ("EMEA", "UK", "CENTRAL", "SOUTH", "NORTH")):
        return "EMEA"
    if any(x in t for x in ("APJ", "JAPAN", "KOREA", "ASEAN", "ANZ", "INDIA")):
        return "APJ"
    return "AMS"


# Managed partner list, built the same way executive_email.py does
_NOAM_RSI = frozenset(
    p for p in _PA.get('--- NOAM RSIs ---', []) if not p.startswith('---')
) | {'LTI Mindtree', 'Kipi.ai'}

# GSIs report globally (all theaters); NOAM RSIs report NoAM only.
# Aliases: EY=Ernst & Young (EY), IBM=IBM Consulting, kipi.ai=Kipi.ai, LTM=LTI Mindtree
# Same 8-name list used by executive_email.py's GSI_LIST / _GSI_NAMES.
GSI_LIST = [
    'Accenture', 'Capgemini Technologies LLC', 'Cognizant Technology Solutions US Corp',
    'Deloitte Consulting', 'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting',
]
GSI_NAMES = frozenset(GSI_LIST)
NOAM_RSI_NAMES = _NOAM_RSI

MANAGED_PARTNERS = list(
    GSI_NAMES
    | _NOAM_RSI
    | frozenset(APJ_RSI_REGION_MAP.keys())
    | frozenset(EMEA_RSI_REGION_MAP.keys())
    | frozenset(LATAM_RSI_REGION_MAP.keys())
)
