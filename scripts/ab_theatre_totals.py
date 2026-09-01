"""Same-instant A/B of the dashboard's Breakdown by Theatre totals.

Replicates the overview.py pipeline headlessly (get_bulk_confidence_scores ->
apply_coco_final -> filter_out_partner_own_accounts -> _build_managed_bc geo
restrictions -> theatre groupby) so the totals can be compared between two git
worktrees without depending on browser rendering.

Run the SAME script under both trees back to back and diff the output:

    APP_ROOT=/Users/rmakkena/.cortexcode/coco-usecase-insights \
        uv run --with pandas --with streamlit --with snowflake-connector-python \
        --with pyarrow python scripts/ab_theatre_totals.py

    APP_ROOT=/tmp/ab_pre uv run ... python scripts/ab_theatre_totals.py

Only same-instant comparisons are meaningful: DT_OKR_USE_CASES refreshes 1-5x a
day and its definition uses CURRENT_DATE, so absolute values drift on their own.
"""
import os
import sys

ROOT = os.environ.get("APP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pandas as pd
import streamlit as st  # noqa: F401  needed for the cache decorators in queries.py

from utils import (PARTNER_GROUPS, PARTNER_ALIASES, PARTNER_RENAME_MAP,
                   APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, LATAM_RSI_REGION_MAP,
                   resolve_partner_filter, apply_coco_final,
                   filter_out_partner_own_accounts)
from utils.queries import get_bulk_confidence_scores

START = os.environ.get("AB_START", "2026-08-01")
END = os.environ.get("AB_END", "2026-10-31")
BANDS = os.environ.get("AB_BANDS", "High").split(",")
_NOAM_THEATERS = ("AMSExpansion", "USMajors", "AMSAcquisition", "USPubSec")


class Conn:
    """Minimal shim so queries.py's _conn.query() works outside Streamlit."""

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

    def query(self, sql, **kw):
        cur = self._c.cursor()
        cur.execute(sql)
        return cur.fetch_pandas_all()


def names(key):
    return {PARTNER_RENAME_MAP.get(n, n) for n in PARTNER_ALIASES.get(key, [])}


conn = Conn()
partners = tuple(resolve_partner_filter(list(PARTNER_GROUPS)))
bc = get_bulk_confidence_scores(conn, partners, START, END).copy()
bc["PARTNER_NAME"] = bc["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
bc["IS_COCO_FINAL"] = apply_coco_final(bc, BANDS)
bc = filter_out_partner_own_accounts(bc)

GSI = names("--- GSIs ---")
NOAM = names("--- NOAM RSIs ---")
APJ = set(APJ_RSI_REGION_MAP.keys())
EMEA = set(EMEA_RSI_REGION_MAP.keys())
LATAM = set(LATAM_RSI_REGION_MAP.keys())

parts = [bc[bc["PARTNER_NAME"].isin(GSI)].copy(),
         bc[bc["PARTNER_NAME"].isin(NOAM) & bc["THEATER_NAME"].isin(_NOAM_THEATERS)].copy()]
for nameset, region_map in ((APJ, APJ_RSI_REGION_MAP), (EMEA, EMEA_RSI_REGION_MAP)):
    sub = bc[bc["PARTNER_NAME"].isin(nameset)].copy()
    sub["_c"] = sub["PARTNER_NAME"].map({k: v[1] for k, v in region_map.items()})
    parts.append(sub[sub["REGION_NAME"] == sub["_c"]].drop(columns=["_c"]))
_latam = bc[bc["PARTNER_NAME"].isin(LATAM)].copy()
parts.append(_latam[_latam["REGION_NAME"] == "LATAM"])
managed = pd.concat([p for p in parts if len(p) > 0], ignore_index=True)

managed["_dep_coco"] = managed["IS_COCO_FINAL"] & (managed["USE_CASE_STAGE"] == "7 - Deployed")
managed["_dep_all"] = managed["USE_CASE_STAGE"] == "7 - Deployed"
grp = (managed.groupby("THEATER_NAME", dropna=True)
       .agg(TOTAL=("USE_CASE_ID", "count"), COCO=("IS_COCO_FINAL", "sum"),
            DEP_ALL=("_dep_all", "sum"), DEP_COCO=("_dep_coco", "sum"))
       .reset_index())
grp = grp[~grp["THEATER_NAME"].str.strip().str.upper().isin({"ACCTSTODELETE", "AMSPARTNER"})]

print(f"APP_ROOT={ROOT}")
print(f"window={START}..{END} bands={BANDS}")
print(f"{'THEATRE':<18}{'UCS':>6}{'COCO':>7}{'GO_LIVES':>10}{'COCO_GL':>9}")
for _, r in grp.sort_values("TOTAL", ascending=False).iterrows():
    print(f"{r['THEATER_NAME']:<18}{int(r['TOTAL']):>6}{int(r['COCO']):>7}"
          f"{int(r['DEP_ALL']):>10}{int(r['DEP_COCO']):>9}")
T, C = int(grp["TOTAL"].sum()), int(grp["COCO"].sum())
DA, DC = int(grp["DEP_ALL"].sum()), int(grp["DEP_COCO"].sum())
print(f"{'TOTAL':<18}{T:>6}{C:>7}{DA:>10}{DC:>9}")
print(f"TOTALS ucs={T} coco={C} go_lives={DA} coco_go_lives={DC}")
print(f"LATAM_rows={len(_latam[_latam['REGION_NAME'] == 'LATAM'])}")
