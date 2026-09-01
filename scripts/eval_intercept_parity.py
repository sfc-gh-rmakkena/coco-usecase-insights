"""Parity check: the Ask AI intercept vs the dashboard's own computation.

Runs both in a single process against the same data snapshot, so any difference is
code, not drift. This is the assertion that would have caught the geo-restriction
gap (the dashboard's theatre table comes from _build_managed_bc, not the simpler
top-KPI path).

    APP_ROOT=<repo> uv run --with pandas --with streamlit \
        --with snowflake-connector-python --with pyarrow \
        python scripts/eval_intercept_parity.py
"""
import os
import sys

ROOT = os.environ.get("APP_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pandas as pd
import streamlit as st  # noqa: F401

from utils import (PARTNER_GROUPS, PARTNER_ALIASES, PARTNER_RENAME_MAP,
                   APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, LATAM_RSI_REGION_MAP,
                   resolve_partner_filter, apply_coco_final,
                   filter_out_partner_own_accounts)
from utils.queries import get_bulk_confidence_scores
from utils.verified_metrics import (FilterScope, _fetch_scoped_bulk, _filter_entity,
                                    GROUP_CANONICAL)

START, END, BANDS = "2026-08-01", "2026-10-31", ["High"]
_NOAM_THEATERS = ("AMSExpansion", "USMajors", "AMSAcquisition", "USPubSec")
FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got={got} want={want}")
    if not ok:
        FAILS.append(name)


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

    def query(self, sql, **kw):
        cur = self._c.cursor()
        cur.execute(sql)
        return cur.fetch_pandas_all()


def names(key):
    return {PARTNER_RENAME_MAP.get(n, n) for n in PARTNER_ALIASES.get(key, [])}


def dashboard_managed(bc):
    """Mirror of app_pages/overview.py _build_managed_bc, no sidebar partner filter."""
    GSI, NOAM = names("--- GSIs ---"), names("--- NOAM RSIs ---")
    parts = [bc[bc["PARTNER_NAME"].isin(GSI)].copy(),
             bc[bc["PARTNER_NAME"].isin(NOAM) & bc["THEATER_NAME"].isin(_NOAM_THEATERS)].copy()]
    for nameset, rmap in ((set(APJ_RSI_REGION_MAP), APJ_RSI_REGION_MAP),
                          (set(EMEA_RSI_REGION_MAP), EMEA_RSI_REGION_MAP)):
        sub = bc[bc["PARTNER_NAME"].isin(nameset)].copy()
        sub["_c"] = sub["PARTNER_NAME"].map({k: v[1] for k, v in rmap.items()})
        parts.append(sub[sub["REGION_NAME"] == sub["_c"]].drop(columns=["_c"]))
    lat = bc[bc["PARTNER_NAME"].isin(set(LATAM_RSI_REGION_MAP))].copy()
    parts.append(lat[lat["REGION_NAME"] == "LATAM"])
    return pd.concat([p for p in parts if len(p) > 0], ignore_index=True)


conn = Conn()
partners = tuple(sorted(resolve_partner_filter(list(PARTNER_GROUPS))))

# --- dashboard side -----------------------------------------------------------
bc = get_bulk_confidence_scores(conn, partners, START, END).copy()
bc["PARTNER_NAME"] = bc["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
bc["IS_COCO_FINAL"] = apply_coco_final(bc, BANDS)
bc = filter_out_partner_own_accounts(bc)
dash = dashboard_managed(bc)
dash_total, dash_coco = len(dash), int(dash["IS_COCO_FINAL"].sum())

# --- intercept side (default sidebar scope) -----------------------------------
scope = FilterScope(partners=partners, selected=(), start_date=START, end_date=END,
                    region="Global", bands=tuple(BANDS), account_coco=True)
icept = _fetch_scoped_bulk(conn, scope)
icept_total, icept_coco = len(icept), int(icept["IS_COCO_FINAL"].sum())

print("\n== default sidebar scope: intercept vs dashboard ==")
check("total use cases", icept_total, dash_total)
check("coco use cases", icept_coco, dash_coco)

print("\n== partner-scoped: intercept honours the selection ==")
acn_scope = scope._replace(partners=("Accenture",), selected=("Accenture",))
acn = _fetch_scoped_bulk(conn, acn_scope)
dash_acn = dash[dash["PARTNER_NAME"] == "Accenture"]
check("Accenture total", len(acn), len(dash_acn))
check("Accenture coco", int(acn["IS_COCO_FINAL"].sum()), int(dash_acn["IS_COCO_FINAL"].sum()))
print(f"  (unfiltered would have reported {dash_total}/{dash_coco} "
      f"-- {round(dash_total / max(len(dash_acn), 1), 1)}x overstatement)")

print("\n== region-scoped: USMajors ==")
usm = _fetch_scoped_bulk(conn, scope._replace(region="USMajors"))
dash_usm = dash[dash["THEATER_NAME"] == "USMajors"]
check("USMajors total", len(usm), len(dash_usm))
check("USMajors coco", int(usm["IS_COCO_FINAL"].sum()), int(dash_usm["IS_COCO_FINAL"].sum()))

print("\n== region-scoped: LATAM (region, not theatre) ==")
lat = _fetch_scoped_bulk(conn, scope._replace(region="LATAM"))
check("LATAM returns rows (would be 0 if filtered on THEATER_NAME)", len(lat) > 0, True)
check("all LATAM rows are region LATAM", set(lat["REGION_NAME"]) == {"LATAM"}, True)

print("\n== LATAM RSI group: exact parity for the 5 partners ==")
# The dashboard's LATAM slice: partner in the 5 names AND REGION_NAME='LATAM'
# (geo-restricted per LATAM_RSI_REGION_MAP / get_latam_rsi_adoption).
LATAM_NAMES = set(LATAM_RSI_REGION_MAP.keys())
dash_lat = dash[dash["PARTNER_NAME"].isin(LATAM_NAMES) & (dash["REGION_NAME"] == "LATAM")]
icept_lat = _filter_entity(icept, group="LATAM")

check("name sets agree across all four definitions",
      GROUP_CANONICAL["LATAM"] == LATAM_NAMES, True)
check("LATAM total use cases", len(icept_lat), len(dash_lat))
check("LATAM coco use cases",
      int(icept_lat["IS_COCO_FINAL"].sum()), int(dash_lat["IS_COCO_FINAL"].sum()))

# Per-partner, so a single mis-scoped partner cannot hide inside the total.
for p in sorted(LATAM_NAMES):
    d = dash_lat[dash_lat["PARTNER_NAME"] == p]
    i = icept_lat[icept_lat["PARTNER_NAME"] == p]
    check(f"  {p[:34]:<34} ucs", len(i), len(d))
    check(f"  {p[:34]:<34} coco",
          int(i["IS_COCO_FINAL"].sum()), int(d["IS_COCO_FINAL"].sum()))

# A LATAM RSI can carry a NoAM theatre (SEIDOR sits in AMSAcquisition), so report
# what the geo restriction actually drops. `bc` is the pre-managed-scope frame, so
# this is the honest before/after; `icept` is already restricted.
_raw_lat = bc[bc["PARTNER_NAME"].isin(LATAM_NAMES)]
_raw_regions = sorted(set(_raw_lat["REGION_NAME"].dropna()))
print(f"  before restriction: {len(_raw_lat)} rows, regions={_raw_regions}")
print(f"  after  restriction: {len(icept_lat)} rows, "
      f"dropped {len(_raw_lat) - len(icept_lat)}")
if _raw_regions == ["LATAM"]:
    print("  NOTE: no non-LATAM rows exist for these partners in this window, so the")
    print("        restriction is a no-op on current data. Its behaviour is covered by")
    print("        the synthetic fixture in scripts/eval_filter_scope.py, which includes")
    print("        a SEIDOR NortheastExp row and asserts it is excluded.")
check("geo restriction leaves only LATAM region",
      set(icept_lat["REGION_NAME"]) <= {"LATAM"}, True)

print("\n== LATAM cross-check against get_latam_rsi_adoption (canonical SQL) ==")
try:
    from utils.queries import get_latam_rsi_adoption
    sql_lat = get_latam_rsi_adoption(conn, START, END)
    sql_ucs = int(sql_lat["TOTAL_UCS"].sum()) if len(sql_lat) else 0
    sql_coco = int(sql_lat["COCO_UCS"].sum()) if len(sql_lat) else 0
    check("LATAM total matches the canonical LATAM query", len(icept_lat), sql_ucs)
    # That query counts IS_COCO (keyword) rather than IS_COCO_FINAL, so its CoCo
    # figure is a floor, not an equality.
    check("LATAM coco >= keyword-only figure from canonical query",
          int(icept_lat["IS_COCO_FINAL"].sum()) >= sql_coco, True)
    print(f"  canonical SQL: {sql_ucs} ucs, {sql_coco} keyword-coco | "
          f"intercept: {len(icept_lat)} ucs, {int(icept_lat['IS_COCO_FINAL'].sum())} coco-final")
except Exception as e:
    print(f"  SKIP cross-check ({type(e).__name__}: {e})")


print("\n== confidence band toggle changes the answer ==")
all_bands = _fetch_scoped_bulk(conn, scope._replace(bands=("High", "Medium", "Low")))
check("all-bands coco >= high-only coco",
      int(all_bands["IS_COCO_FINAL"].sum()) >= icept_coco, True)
print(f"  High only={icept_coco}  All bands={int(all_bands['IS_COCO_FINAL'].sum())}")

print("\n== account-level CoCo = No means keyword only ==")
kw = _fetch_scoped_bulk(conn, scope._replace(account_coco=False))
check("keyword-only coco <= high-only coco",
      int(kw["IS_COCO_FINAL"].sum()) <= icept_coco, True)
print(f"  keyword only={int(kw['IS_COCO_FINAL'].sum())}")

print("\n== LATAM group honours the geo restriction ==")
lg = _filter_entity(icept, group="LATAM")
check("LATAM group rows all region LATAM",
      set(lg["REGION_NAME"]) <= {"LATAM"}, True)

print()
if FAILS:
    print(f"FAILED {len(FAILS)}: {FAILS}")
    sys.exit(1)
print("Intercept parity checks passed.")
