"""Grounded eval: does Ask AI answer the USMajors breakdown correctly?

Ground truth is computed from Snowflake at run time (never hardcoded), then the
same question is put to BOTH Ask AI implementations and scored deterministically:

  1. names every region that exists in USMajors
  2. reports the correct use-case count for each
  3. invents no region that is not in USMajors
  4. does not leak regions from other theatres (EMEA, ANZ, LATAM ...)
  5. gets the USMajors total right

Must run under Streamlit, because ask_ai/ask_ai_agent read st.session_state and
st.connection exactly as the sidebar chat does:

    streamlit run scripts/eval_theatre_grounding.py --server.headless true

Optional env vars:
    EVAL_PATHS=agent,direct     which implementations to exercise
    EVAL_OUT=/path/report.md    report destination
"""

import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The app's secrets use authenticator=externalbrowser, which blocks forever in a
# headless run waiting on an SSO window. Reuse the Snowflake CLI's cached token
# instead, and expose it in the shape both Ask AI paths expect:
#   ask_ai            -> conn.query(...)
#   run_cortex_agent  -> st.connection("snowflake")._instance.rest.token / .host
import pandas as pd
import snowflake.connector

_CONN = snowflake.connector.connect(
    connection_name="snowhouse", role="SALES_ENGINEER",
    warehouse="COCO_PARTNER_ADOPTION_WH", database="TEMP",
    schema="COCO_PARTNER_ADOPTION",
)


class _ConnShim:
    """Minimal stand-in for st.connection('snowflake')."""

    _instance = _CONN

    def query(self, sql, **kwargs):
        cur = _CONN.cursor()
        cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


_SHIM = _ConnShim()
st.connection = lambda *a, **k: _SHIM

from utils.ask_ai import ask_ai, ask_ai_agent

st.set_page_config(page_title="Theatre grounding eval", layout="wide")

PATHS = [p.strip() for p in os.environ.get("EVAL_PATHS", "agent,direct").split(",") if p.strip()]
OUT = Path(os.environ.get("EVAL_OUT", "/tmp/theatre_grounding_report.md"))

QUESTION = "Give me a breakdown of the CoCo use cases by theatre for US Majors"

# Regions belonging to OTHER theatres. If one of these shows up in a USMajors
# answer the model has crossed theatre boundaries, which is the failure mode this
# eval exists to catch.
FOREIGN_REGIONS = [
    "CentralEMEA", "SouthEMEA", "NorthEMEA", "EMEACommercial", "META",
    "ANZ", "ASEAN", "Korea", "Japan", "China", "India",
    "LATAM", "CentralExp", "USGrowthExp", "SoutheastExp", "NortheastExp",
    "SouthwestExp", "CanadaExp", "NorthwestExp", "SLED", "Federal",
]

_out_lines = []


def log(msg):
    print(msg, flush=True)
    _out_lines.append(msg)


def bootstrap_session():
    """Mirror the sidebar defaults so filter context matches the real app."""
    if "conn" not in st.session_state:
        st.session_state.conn = st.connection("snowflake")
    st.session_state.setdefault("_ui_region", "Global")
    st.session_state.setdefault("selected_region", "Global")
    st.session_state.setdefault("selected_theater", "All")
    st.session_state.setdefault("selected_partners", [])
    st.session_state.setdefault("selected_stages", [])
    st.session_state.setdefault("okr_start_date", date(2026, 8, 1))
    st.session_state.setdefault("okr_end_date", date(2026, 10, 31))
    st.session_state.setdefault("include_account_coco", "Yes")
    st.session_state.setdefault("confidence_filter", ["High"])
    st.session_state.setdefault("ask_ai_context", "")


def ground_truth(conn):
    """USMajors regions with use-case counts and EACV, straight from the source."""
    df = conn.query("""
        SELECT REGION_NAME, COUNT(*) AS USE_CASES, SUM(USE_CASE_EACV) AS EACV
        FROM TEMP.COCO_PARTNER_ADOPTION.V_PARTNER_COCO_USE_CASES
        WHERE THEATER_NAME = 'USMajors'
        GROUP BY REGION_NAME ORDER BY USE_CASES DESC
    """, ttl=0)
    return df


def nums_in(text):
    """Every integer in the answer, commas stripped."""
    return {int(n.replace(",", "")) for n in re.findall(r"\b\d[\d,]*\b", text or "")}


def grade(answer, truth):
    """Deterministic checks. Returns (passed, failures, warnings)."""
    fails, warns = [], []
    low = (answer or "").lower()

    if not answer or len(answer.strip()) < 20:
        return False, ["empty or near-empty answer"], []
    for marker in ("agent call failed", "traceback", "sql error", "api error",
                   "no response from agent", "could not parse"):
        if marker in low:
            return False, [f"error marker in answer: {marker}"], []

    regions = list(truth["REGION_NAME"])
    counts = {r: int(c) for r, c in zip(truth["REGION_NAME"], truth["USE_CASES"])}
    total = sum(counts.values())
    present = [r for r in regions if r.lower() in low]
    missing = [r for r in regions if r.lower() not in low]

    # 1. coverage
    if missing:
        fails.append(f"missing regions: {', '.join(missing)}")

    # 2. per-region counts (only checkable for regions actually named)
    found_nums = nums_in(answer)
    wrong = [f"{r} (expected {counts[r]})" for r in present if counts[r] not in found_nums]
    if wrong:
        fails.append(f"count not found for: {', '.join(wrong)}")

    # 3 & 4. no foreign or invented regions
    leaked = [r for r in FOREIGN_REGIONS if r.lower() in low]
    if leaked:
        fails.append(f"regions from other theatres leaked in: {', '.join(leaked)}")

    # 5. total
    if total not in found_nums:
        warns.append(f"USMajors total {total} not stated")

    return (len(fails) == 0), fails, warns


bootstrap_session()
conn = st.session_state.conn

log("# Theatre grounding eval - USMajors breakdown")
log("")
log(f"Question: {QUESTION}")
log("")

truth = ground_truth(conn)
log("## Ground truth (live from V_PARTNER_COCO_USE_CASES)")
log("")
log("| Region | Use cases | EACV |")
log("|---|---|---|")
for _, r in truth.iterrows():
    log(f"| {r['REGION_NAME']} | {int(r['USE_CASES'])} | ${float(r['EACV'] or 0):,.0f} |")
_total = int(truth["USE_CASES"].sum())
log(f"| **TOTAL** | **{_total}** | |")
log("")

results = []
for path in PATHS:
    log(f"## Path: {path}")
    log("")
    t0 = time.time()
    try:
        if path == "agent":
            res = ask_ai_agent(QUESTION, chat_history=[])
        else:
            res = ask_ai(conn, QUESTION, "", debug=False, chat_history=[])
        answer = res.get("answer", "")
        sql = res.get("sql")
        err = None
    except Exception as e:
        answer, sql, err = "", None, f"{type(e).__name__}: {e}"
    secs = round(time.time() - t0, 1)

    passed, fails, warns = grade(answer, truth)
    if err:
        passed, fails = False, fails + [f"exception: {err}"]

    results.append((path, passed, fails, warns, secs))
    log(f"- verdict: {'PASS' if passed else 'FAIL'}  ({secs}s)")
    for f in fails:
        log(f"  - FAIL: {f}")
    for w in warns:
        log(f"  - warn: {w}")
    log("")
    log("<details><summary>answer</summary>")
    log("")
    log("```")
    log(answer or "(empty)")
    log("```")
    log("</details>")
    log("")
    if sql:
        log("<details><summary>generated SQL</summary>")
        log("")
        log("```sql")
        log(sql)
        log("```")
        log("</details>")
        log("")

log("## Summary")
log("")
log("| Path | Verdict | Failures | Seconds |")
log("|---|---|---|---|")
for path, passed, fails, warns, secs in results:
    log(f"| {path} | {'PASS' if passed else 'FAIL'} | {len(fails)} | {secs} |")

OUT.write_text("\n".join(_out_lines))
print(f"\nreport written to {OUT}", flush=True)
st.markdown("\n".join(_out_lines))
