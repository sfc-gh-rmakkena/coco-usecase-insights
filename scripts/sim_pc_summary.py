"""Simulate the Partner Consultants SUMMARY narrative against live data."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import snowflake.connector
from utils import PARTNER_GROUPS, resolve_partner_filter, canonical_partner, PARTNER_RENAME_MAP

CONN = snowflake.connector.connect(
    connection_name="snowhouse", role="SALES_ENGINEER",
    warehouse="COCO_PARTNER_ADOPTION_WH", database="TEMP",
    schema="COCO_PARTNER_ADOPTION",
)


class Shim:
    def query(self, sql, **kw):
        cur = CONN.cursor()
        cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


conn = Shim()

from utils.queries import (get_pc_coco_uc_engagements, get_pc_top_skills,
                           get_pc_activity, get_pc_usecase_counts)
from utils.cortex_helpers import cortex_complete

partners = resolve_partner_filter(list(PARTNER_GROUPS))
START, END, REGION = "2026-05-01", "2026-08-13", "Global"

_e = get_pc_coco_uc_engagements(conn, REGION, partners, START, END)
_e["PARTNER_NAME"] = _e["PARTNER_NAME"].map(canonical_partner).replace(PARTNER_RENAME_MAP)
tot_tokens = _e["TOKENS"].sum()
_e["TOKEN_SHARE_PCT"] = (_e["TOKENS"] / tot_tokens * 100).round(1)
_e = _e.sort_values("TOKENS", ascending=False)

print(f"engagements={len(_e)} accounts={_e.ACCOUNT_NAME.nunique()} "
      f"partners={_e.PARTNER_NAME.nunique()} tokens={tot_tokens:,}")

_eng_ctx = _e[["PARTNER_NAME", "ACCOUNT_NAME", "THEATER_NAME", "REGION_NAME",
               "COCO_UCS", "DEPLOYED_UCS", "EACV", "CONSULTANTS", "TOKENS",
               "TOKEN_SHARE_PCT", "ACTIVE_DAYS", "WORKLOADS",
               "TECH_USE_CASE"]].to_string(index=False, max_colwidth=60)

_geo = (_e.groupby("THEATER_NAME", as_index=False)
          .agg(ENGAGEMENTS=("ACCOUNT_NAME", "nunique"), COCO_UCS=("COCO_UCS", "sum"),
               CONSULTANTS=("CONSULTANTS", "sum"), TOKENS=("TOKENS", "sum"))
          .sort_values("TOKENS", ascending=False))
print("\n=== WHERE THE WORK SITS ===")
print(_geo.to_string(index=False))

_sk = get_pc_top_skills(conn, "Customer", region=REGION, partner_names=partners, start_date=START, end_date=END, top=25)
_skills_ctx = _sk.head(25).to_string(index=False) if len(_sk) else "(none)"

totals = (f"CoCo-attached engagements: {len(_e)}\n"
          f"Distinct customer accounts: {_e.ACCOUNT_NAME.nunique()}\n"
          f"Distinct partners: {_e.PARTNER_NAME.nunique()}\n"
          f"CoCo use cases: {int(_e.COCO_UCS.sum())}\n"
          f"Deployed use cases: {int(_e.DEPLOYED_UCS.sum())}\n"
          f"Tokens: {int(tot_tokens):,}\n"
          f"Consultants: {int(_e.CONSULTANTS.sum())}")

# Section 1 (what the page displays) - the PRIMARY basis
act = get_pc_activity(conn, "Customer", REGION, partners, START, END)
act["PARTNER_NAME"] = act["PARTNER_NAME"].map(canonical_partner).replace(PARTNER_RENAME_MAP)
ucc = get_pc_usecase_counts(conn)
ucc["PARTNER_NAME"] = ucc["PARTNER_NAME"].map(canonical_partner).replace(PARTNER_RENAME_MAP)
v1 = act.merge(_sk, on="PARTNER_NAME", how="left")
v1 = v1.merge(ucc.groupby("PARTNER_NAME", as_index=False)["COCO_UCS"].sum(), on="PARTNER_NAME", how="left")
v1["COCO_UCS"] = v1["COCO_UCS"].fillna(0).astype(int)
v1 = v1.sort_values("TOKENS", ascending=False)
_v1_totals = (
    f"Partners active in customer accounts: {v1['PARTNER_NAME'].nunique():,}\n"
    f"Consultants in customer accounts: {int(v1['CONSULTANTS'].sum()):,}\n"
    f"Customer-account tokens: {int(v1['TOKENS'].sum()):,}\n"
    f"Prompts: {int(v1['PROMPTS'].sum()):,}\n"
    f"CoCo-attached use cases across these partners: {int(v1['COCO_UCS'].sum()):,}"
)
print("\n=== SECTION 1 TOTALS (must match page tiles) ===")
print(_v1_totals)
v1["TOP_SKILLS"] = v1["TOP_SKILLS"].fillna("(not captured)")
_v1_ctx = v1.to_string(index=False, max_colwidth=70)
_mom = v1.head(8)[["PARTNER_NAME", "TOKENS", "WOW_PCT"]].dropna(subset=["WOW_PCT"])
_mom_ctx = _mom.sort_values("WOW_PCT", ascending=False).to_string(index=False)
print("\n=== MOMENTUM ELIGIBLE (top 8 by tokens) ===")
print(_mom_ctx)

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "app_pages", "partner_consultants.py")).read()
spec = re.search(r'default_prompt = f?"""(.*?)"""', src, re.S).group(1)

data_context = f"""PRIMARY BASIS - SECTION 1 RESULTS (page figures; headline numbers MUST come from here)

SECTION 1 TOTALS - use verbatim
{_v1_totals}

SECTION 1 PER-PARTNER TABLE
{_v1_ctx}

MOMENTUM - the ONLY partners whose week-over-week change may be quoted (top 8 by tokens)
{_mom_ctx}

SUPPORTING DETAIL - STRICT-ATTRIBUTION SUBSET (smaller; for account names, region, depth only)
SUBSET TOTALS
{totals}

ENGAGEMENT DETAIL
{_eng_ctx}

WHERE THE WORK SITS
{_geo.to_string(index=False)}

COCO SKILLS INVOKED
{_skills_ctx}
"""

out = cortex_complete(conn, "claude-sonnet-4-5", spec + "\n\n" + data_context)
print("\n=== GENERATED ===")
print(out)

print("\n=== SKILLS CTX ===")
print(_skills_ctx[:1200])
