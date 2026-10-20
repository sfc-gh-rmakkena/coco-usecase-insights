import json
import pandas as pd
from utils.workshop import cache
from tests.workshop.conftest import FakeConn


def test_compute_hash_changes_with_inputs():
    a = cache.compute_hash({"x": 1}, "v1")
    assert a == cache.compute_hash({"x": 1}, "v1")
    assert a != cache.compute_hash({"x": 2}, "v1")
    assert a != cache.compute_hash({"x": 1}, "v2")


def test_lookup_parses_payload():
    df = pd.DataFrame({"CACHE_KEY_HASH": ["h1"], "PAYLOAD": [json.dumps({"ok": True})]})
    assert cache.lookup(FakeConn({"COCO_PSE_WORKSHOP_CACHE": df}), ["h1"]) == {"h1": {"ok": True}}


def test_insert_escapes_quotes():
    conn = FakeConn()
    cache.insert(conn, [("h1", "O'Brien LLP", "uc1", {"t": "it's"})])
    assert "O''Brien" in conn.queries[-1]
