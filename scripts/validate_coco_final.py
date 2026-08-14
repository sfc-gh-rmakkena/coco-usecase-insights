"""Validate apply_coco_final: partner-comment tags now require token consumption."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd, snowflake.connector
from utils import PARTNER_GROUPS, resolve_partner_filter, apply_coco_final

C = snowflake.connector.connect(connection_name="snowhouse", role="SALES_ENGINEER",
    warehouse="COCO_PARTNER_ADOPTION_WH", database="TEMP", schema="COCO_PARTNER_ADOPTION")


class S:
    def query(self, sql, **kw):
        cur = C.cursor(); cur.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[c[0] for c in cur.description])


from utils.queries import get_bulk_confidence_scores
partners = resolve_partner_filter(list(PARTNER_GROUPS))
bc = get_bulk_confidence_scores(S(), tuple(partners), "2026-05-01", "2026-08-13")
print("rows:", len(bc))

bands = ["High"]
old = (bc["IS_COCO"] == True) | (bc["CONFIDENCE_BAND"].isin(bands))
new = apply_coco_final(bc, bands)

print(f"\nOLD IS_COCO_FINAL: {int(old.sum())}")
print(f"NEW IS_COCO_FINAL: {int(new.sum())}")
print(f"dropped:           {int((old & ~new).sum())}")

d = bc[old & ~new]
print("\n-- dropped by source (must be PARTNER_COMMENTS only) --")
print(d["COCO_SOURCE"].value_counts().to_string() if len(d) else "(none)")
print("\n-- dropped rows must all have zero tokens and non-High band --")
if len(d):
    print("max Q2_TOKENS among dropped:", d["Q2_TOKENS"].max())
    print("bands among dropped:", sorted(d["CONFIDENCE_BAND"].unique()))
    print("\n-- sample --")
    print(d[["ACCOUNT_NAME", "PARTNER_NAME", "USE_CASE_STAGE", "COCO_SOURCE",
             "Q2_TOKENS", "CONFIDENCE_BAND"]].head(12).to_string(index=False))

print("\n-- safety: nothing ADDED --")
print("added:", int((new & ~old).sum()))
print("\n-- partner-comment rows WITH tokens are retained --")
keep = bc[(bc["COCO_SOURCE"] == "PARTNER_COMMENTS") & (bc["Q2_TOKENS"] > 0)]
print(f"partner-comment rows with tokens: {len(keep)}, still final: {int(new[keep.index].sum())}")
