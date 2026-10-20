import pandas as pd
from utils.workshop.gate import load_listed_names, is_listed, usage_tier, fetch_a360_context
from tests.workshop.conftest import FakeConn


def test_is_listed_exact_normalized():
    conn = FakeConn({"TOP_SNOWFLAKE_COMPANIES": pd.DataFrame({"COMPANY_NAME": ["Roche", "The Kroger Co."]})})
    listed = load_listed_names(conn)
    assert is_listed("ROCHE", listed)
    assert is_listed("Kroger", listed)
    assert not is_listed("Roche Bobois", listed)
    assert not is_listed("", listed)


def test_usage_tier_buckets():
    assert usage_tier(0) == "No"
    assert usage_tier(3) == "Low"
    assert usage_tier(25) == "Big"


def test_fetch_a360_context_tiers_only():
    conn = FakeConn({
        "COCO_ACCOUNT_COCO_USAGE": pd.DataFrame({"ACCOUNT_UPPER": ["ROCHE"], "ACTIVE_USERS": [40],
                                                 "ANY_UI_USERS": [30], "ANY_CLI_DESKTOP_USERS": [0],
                                                 "IS_COCO_BLOCKED": [False]}),
        "COCO_USER_MATURITY_SNAPSHOT": pd.DataFrame({"ACCOUNT_UPPER": ["ROCHE"], "USER_MATURITY": ["L2 Explorer"]}),
    })
    ctx = fetch_a360_context(conn, ["Roche"])
    assert ctx["ROCHE"] == {"usage_tier": "Big", "surfaces": ["Snowsight"],
                            "enablement_needed": False, "dominant_maturity": "L2 Explorer"}
    assert all("IN ('ROCHE')" in q for q in conn.queries)
