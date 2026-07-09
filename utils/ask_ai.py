import re
import streamlit as st
from utils.cortex_helpers import cortex_complete
from utils.config import get_schema

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
- Use case stages: 3=Validation, 4=Won, 5=Implementation, 6=Complete, 7=Deployed
"""

_SQL_SYSTEM = f"""
{_SCHEMA_CONTEXT}

TASK: The user asked a question that may require querying Snowflake.
If the question needs data not in the provided page context, write ONE read-only SQL SELECT statement.
Rules:
- Only SELECT. No INSERT/UPDATE/DELETE/DROP/CREATE.
- Always use fully qualified table names: {SCHEMA}.TABLE_NAME
- LIMIT 20 rows max.
- Wrap the SQL in a ```sql ... ``` block.
- If the question can be answered from page context alone, respond with "NO_SQL_NEEDED" and nothing else.
"""

_ANSWER_SYSTEM = f"""
{_SCHEMA_CONTEXT}

You are a concise, data-driven assistant. Answer the user's question in 2-4 sentences using the
provided data. Be specific with numbers. If data is missing, say so clearly.
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


def ask_ai(conn, question: str, page_context: str = "") -> str:
    context_block = f"\nCURRENT PAGE DATA:\n{page_context}\n" if page_context else ""

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
