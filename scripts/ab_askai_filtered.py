"""Drive the real Ask AI intercept with a simulated sidebar filter selection.

Exercises the actual production path — detect_intent -> get_verified_answer ->
resolvers -> Cortex prose — with session_state stubbed to a chosen filter state, so
the answer can be compared against the dashboard's own number for the same filters.

Works against both the pre-change and post-change trees: the older tree has no
_ss_get to stub, which is precisely the defect (it ignores the sidebar entirely).

    APP_ROOT=<tree> AB_PARTNER=Accenture uv run --with pandas --with streamlit \
        --with snowflake-connector-python --with pyarrow \
        python scripts/ab_askai_filtered.py
"""
import os
import sys

ROOT = os.environ.get("APP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pandas as pd
import streamlit as st  # noqa: F401

PARTNER = os.environ.get("AB_PARTNER", "Accenture")
START = os.environ.get("AB_START", "2026-08-01")
END = os.environ.get("AB_END", "2026-10-31")
BANDS = os.environ.get("AB_BANDS", "High").split(",")
REGION = os.environ.get("AB_REGION", "Global")
QUESTION = os.environ.get("AB_QUESTION", "how many coco use cases do we have")


class Conn:
    def __init__(self):
        import snowflake.connector
        import tomllib
        cfg = tomllib.load(open(os.path.join(ROOT, ".streamlit/secrets.toml"), "rb"))
        c = cfg["connections"]["snowflake"]
        self._c = snowflake.connector.connect(
            account=c["account"], user=c["user"],
            authenticator=c.get("authenticator", "externalbrowser"),
            role=c.get("role"), warehouse=c.get("warehouse"),
            database=c.get("database"), schema=c.get("schema"))

    def query(self, sql, **kw):          # kw absorbs ttl=0 from cortex_complete
        cur = self._c.cursor()
        cur.execute(sql)
        return cur.fetch_pandas_all()


conn = Conn()

# ── Simulate the sidebar selection ────────────────────────────────────────────
SIDEBAR = {
    "selected_partners": [PARTNER],
    "okr_start_date": START,
    "okr_end_date": END,
    "selected_region": REGION,
    "confidence_filter": BANDS,
    "include_account_coco": "Yes",
    "selected_theater": "All",
    "selected_subregions": [],
    "selected_stages": [],
}

import utils.verified_metrics as vm

_stubbed = hasattr(vm, "_ss_get")
if _stubbed:
    vm._ss_get = lambda k, d: SIDEBAR.get(k, d)

# ── Dashboard-side number for the same filters ────────────────────────────────
from utils import (PARTNER_RENAME_MAP, apply_coco_final,
                   filter_out_partner_own_accounts, resolve_partner_filter)
from utils.queries import get_bulk_confidence_scores

_names = tuple(sorted(resolve_partner_filter([PARTNER])))
bc = get_bulk_confidence_scores(conn, _names, START, END).copy()
bc["PARTNER_NAME"] = bc["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
bc["IS_COCO_FINAL"] = apply_coco_final(bc, BANDS)
bc = filter_out_partner_own_accounts(bc)
dash_total, dash_coco = len(bc), int(bc["IS_COCO_FINAL"].sum())
dash_pct = round(dash_coco * 100.0 / dash_total, 1) if dash_total else 0.0

# ── Ask AI, real code path ────────────────────────────────────────────────────
from utils.intent_classifier import detect_intent
from utils.verified_metrics import get_verified_answer

intent = detect_intent(QUESTION)
res = get_verified_answer(conn, QUESTION, intent)

print("=" * 78)
print(f"APP_ROOT      : {ROOT}")
print(f"sidebar stub  : {'APPLIED' if _stubbed else 'NOT AVAILABLE (build ignores sidebar filters)'}")
print(f"filters       : partner={PARTNER} region={REGION} {START}..{END} bands={BANDS}")
print(f"question      : {QUESTION}")
print("-" * 78)
print(f"DASHBOARD     : {dash_coco} CoCo of {dash_total} use cases ({dash_pct}%)")
print("-" * 78)
print(f"intent        : metric={intent.get('metric')} quarter={intent.get('quarter')} "
      f"explicit={intent.get('quarter_explicit')} partner={intent.get('partner')}")
if res:
    print("ASK AI ANSWER :")
    print(res.get("answer", "(none)"))
    print("-" * 78)
    print("RAW VERIFIED BLOCK (what the model was given):")
    print(res.get("sql_result") or "(none)")
else:
    print("ASK AI        : no verified answer (would fall through to the agent)")
print("=" * 78)
