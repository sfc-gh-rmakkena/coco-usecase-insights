import re
import streamlit as st
from utils.cortex_helpers import cortex_complete
from utils.config import get_schema
from utils import resolve_region_theaters, resolve_partner_filter

SCHEMA = get_schema()

_SCHEMA_CONTEXT = f"""
You are an AI assistant embedded in the CoCo (Cortex Code) Partner Adoption dashboard.

SNOWFLAKE SCHEMA (all tables in {SCHEMA}):
- DT_OKR_USE_CASES: USE_CASE_ID, PARTNER_NAME, ACCOUNT_NAME, USE_CASE_NAME, USE_CASE_STAGE,
  USE_CASE_EACV, IS_COCO (bool), COCO_SOURCE, THEATER_NAME, REGION_NAME, DECISION_DATE, GO_LIVE_DATE
- IS_COCO_FINAL_WEEKLY_SNAPSHOT: WEEK_START, PARTNER_NAME, TOTAL_UCS, COCO_UCS, COCO_PCT, REGION, SAVED_AT
- COCO_OKR_TARGET_WEEKLY: WEEK_START, PARTNERS_AT_TARGET, TOTAL_PARTNERS
- PARTNER_ACCOUNT_DETAILS: PARTNER_NAME, ACCOUNT_NAME, ACCOUNT_LOCATOR, ACTIVE_USERS,
  TOTAL_REQUESTS, CURRENT_WEEK_REQUESTS

EXTERNAL SCHEMA (CoCo credit/token consumption):
- SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT: DS (date), SALESFORCE_ACCOUNT_NAME,
  SNOWFLAKE_ACCOUNT_TYPE ('Customer' or 'Partner'), TOTAL_TOKEN_CREDITS, TOTAL_TOKENS,
  TOTAL_DAILY_REQUESTS, TOTAL_INPUT_TOKENS, TOTAL_OUTPUT_TOKENS

20 MANAGED PARTNERS: Accenture, Capgemini Technologies LLC, Cognizant Technology Solutions US Corp,
Deloitte Consulting, EY, IBM, 7Rivers Inc, Aimpoint Digital, BlueCloud Services Inc, kipi.ai,
evolv Consulting, Infostrux Solutions Inc., Infosys, KPMG LLP, LTM, NTT DATA Group Corporation,
phData Inc., Slalom LLC., Squadron Data Inc, Tredence Inc.

KEY CONCEPTS:
- IS_COCO = TRUE: SE or partner mentioned CoCo in Salesforce notes (keyword detection)
- IS_COCO_FINAL: IS_COCO OR High-confidence AI scoring (higher accuracy, used in heatmap)
- COCO_PCT = COCO_UCS / TOTAL_UCS * 100. OKR target = 50% per partner.
- GSIs (global scope): Accenture, Capgemini, Cognizant, Deloitte, EY, IBM
- RSIs (NoAM scope): remaining 14 partners
- Current period: FY27 Q2 (May 1 – Jul 31, 2026). FY27 Q1 = Feb 1 – Apr 30, 2026.
- USE_CASE_STAGE values are TEXT strings:
    '3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan',
    '5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed'
  NEVER use numeric stage values like 5 or 7 — always use the full string.
- To find CoCo credits/tokens for a partner's accounts: ALWAYS join DT_OKR_USE_CASES
  with CORTEX_CODE_USER_DAY_FACT. Never query the usage table alone for partner-level questions.
  Example pattern:
  ```sql
  WITH partner_accounts AS (
      SELECT DISTINCT UPPER(ACCOUNT_NAME) AS ACCOUNT_NAME_UPPER
      FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES
      WHERE PARTNER_NAME = 'Accenture'  -- or whatever partner
      AND USE_CASE_STAGE IN ('5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
  )
  SELECT u.SALESFORCE_ACCOUNT_NAME,
         SUM(u.TOTAL_TOKENS) AS total_tokens,
         SUM(u.TOTAL_TOKEN_CREDITS) AS total_credits,
         COUNT(DISTINCT u.DS) AS active_days,
         MAX(u.DS) AS last_active
  FROM SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT u
  JOIN partner_accounts pa ON UPPER(u.SALESFORCE_ACCOUNT_NAME) = pa.ACCOUNT_NAME_UPPER
  WHERE u.SNOWFLAKE_ACCOUNT_TYPE = 'Customer'
    AND u.DS >= '2026-05-01'
  GROUP BY 1
  ORDER BY total_tokens DESC
  LIMIT 20
  ```
  Always include PARTNER_NAME or the partner filter in the result so the answer can reference it.
- For trend questions over time, GROUP BY u.DS or DATE_TRUNC('week', u.DS) instead of summing all together.
"""

_SQL_SYSTEM = f"""
{_SCHEMA_CONTEXT}

TASK: The user is on a specific dashboard page with active filters. You must answer ONLY based on the filtered scope shown in CURRENT PAGE DATA and ACTIVE FILTERS.

If the question can be answered from the page context numbers alone, respond with "NO_SQL_NEEDED" and nothing else.

If a SQL query is needed:
- Write ONE read-only SELECT statement
- MANDATORY: apply every filter listed under "ACTIVE FILTERS" — never query data outside the filtered scope
- Only SELECT. No INSERT/UPDATE/DELETE/DROP/CREATE.
- Always use fully qualified table names: {SCHEMA}.TABLE_NAME (or SNOWSCIENCE.LLM.* for usage tables)
- LIMIT 20 rows max
- Wrap the SQL in a ```sql ... ``` block
"""

_ANSWER_SYSTEM = f"""
{_SCHEMA_CONTEXT}

You are a concise assistant answering questions about dashboard data.
IMPORTANT: Answer ONLY based on the filtered scope shown in CURRENT PAGE DATA and ACTIVE FILTERS. Do not reference or speculate about data outside the active filter scope.
Answer in 2-4 sentences. Be specific with numbers. If data is missing, say so clearly.
Do not make up numbers. Respond in plain text, no markdown headers.
"""


def _extract_sql(text: str) -> str | None:
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        sql = match.group(1).strip()
        # Safety: reject any DML
        forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE)\b", re.IGNORECASE)
        if forbidden.search(sql):
            return None
        return sql
    return None


def _run_sql(conn, sql: str) -> str:
    try:
        df = conn.query(sql, ttl=0)
        if df.empty:
            return "Query returned no results."
        return df.to_string(index=False, max_rows=20)
    except Exception as e:
        return f"Query error: {e}"


def build_filter_context() -> str:
    """Build an explicit filter instruction block from current sidebar session state.
    Inject this into ask_ai_context so Ask AI applies the active filters to all SQL.
    """
    region = st.session_state.get("selected_region", "Global")
    selected_partners = st.session_state.get("selected_partners", [])
    start_date = st.session_state.get("okr_start_date")
    end_date = st.session_state.get("okr_end_date")

    lines = ["\nACTIVE FILTERS — apply ALL of these to every SQL query you write:"]

    # Region / theater filter
    theaters = resolve_region_theaters(region)
    if theaters:
        lines.append(f"- Region: {region} → filter: THEATER_NAME IN ({', '.join(repr(t) for t in theaters)})")
    else:
        lines.append(f"- Region: Global (no theater filter needed)")

    # Partner filter
    if selected_partners:
        partner_names = resolve_partner_filter(selected_partners)
        plist = ", ".join(f"'{p}'" for p in sorted(partner_names))
        lines.append(f"- Partners: {', '.join(selected_partners)} → filter: PARTNER_NAME IN ({plist})")
    else:
        lines.append("- Partners: All (no partner filter needed)")

    # Date range
    if start_date and end_date:
        lines.append(f"- Date range: {start_date} to {end_date} (use DECISION_DATE or GO_LIVE_DATE)")

    return "\n".join(lines)


def ask_ai(conn, question: str, page_context: str = "") -> str:
    # Build filter block and prepend it before page data so LLM sees scope first
    filter_block = build_filter_context()
    context_block = f"{filter_block}\n\nCURRENT PAGE DATA:\n{page_context}\n" if page_context else f"{filter_block}\n"

    # Step 1: decide if SQL is needed; generate it if so
    step1_prompt = f"{_SQL_SYSTEM}\n{context_block}\nUSER QUESTION: {question}"
    step1 = cortex_complete(conn, "claude-sonnet-4-5", step1_prompt)

    sql_result = ""
    if "NO_SQL_NEEDED" not in step1:
        sql = _extract_sql(step1)
        if sql:
            sql_result = _run_sql(conn, sql)

    # Step 2: synthesize final answer
    data_block = f"\nSQL RESULT:\n{sql_result}\n" if sql_result else ""
    step2_prompt = (
        f"{_ANSWER_SYSTEM}\n"
        f"{context_block}"
        f"{data_block}"
        f"\nUSER QUESTION: {question}"
    )
    return cortex_complete(conn, "claude-sonnet-4-5", step2_prompt)
