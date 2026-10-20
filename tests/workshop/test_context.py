import pandas as pd
from utils.workshop.context import fetch_uc_context, NEVER_SENT
from tests.workshop.conftest import FakeConn


def test_fetch_uc_context_maps_fields_and_drops_never_sent():
    uid = "a0X3n00000ABCDEFGH"
    df = pd.DataFrame({"USE_CASE_ID": [uid], "DESCRIPTION": ["Forecast demand"],
                       "SE_COMMENTS": ["Customer on Databricks"], "TECHNICAL_CHAMPION": ["Jane Doe"],
                       "FUTURE_STATE_DIAGRAM": ["https://docs.google.com/x"], "INDUSTRY": ["Pharma"]})
    ctx = fetch_uc_context(FakeConn({"DD_SALESFORCE_USE_CASE": df}), [uid, "bad'id"])
    assert ctx[uid]["DESCRIPTION"] == "Forecast demand"
    assert ctx[uid]["TECHNICAL_CHAMPION"] == "named champion identified"
    assert "FUTURE_STATE_DIAGRAM" not in ctx[uid]
    assert not (NEVER_SENT & set(ctx[uid]))


def test_fetch_uc_context_empty_ids():
    assert fetch_uc_context(FakeConn(), []) == {}
