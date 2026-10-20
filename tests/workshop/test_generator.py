import json

import pandas as pd

from tests.workshop.conftest import FakeConn
from utils.workshop import generator

UC = {"uc_id": "a0X3n00000ABCDEFGH", "name": "Demand Forecasting", "account": "Roche",
      "skills": ["machine-learning"], "sanitized_desc": "Forecast weekly demand.", "stage_label": "POC"}


def fake_llm_factory(recipe_conf=90, leak=False):
    def llm(prompt):
        if "Pick the single cookbook recipe" in prompt:
            from utils.workshop import assets
            return json.dumps({"recipe_id": assets.recipes_index()[0]["id"], "confidence": recipe_conf, "rationale": "fits"})
        if "starter-prompts" in prompt:
            return json.dumps({"prompts": [{"title": f"T{i}", "purpose": "p", "prompt": "do x"} for i in range(3)]})
        stmt = "Spend is $2M." if leak else "Weekly demand forecasting."
        return json.dumps({"problem_statement": stmt, "architecture": ["a"], "steps": [{"title": "s", "detail": "d", "sql": ""}],
                           "coco_prompts": ["p"], "considerations": [], "docs": []})
    return llm


def test_recipe_band_full_reference_none():
    assert generator.recipe_band(81) == "full"
    assert generator.recipe_band(80) == "reference"
    assert generator.recipe_band(50) == "reference"
    assert generator.recipe_band(49) == "none"


def test_build_one_shape_identical_for_both_paths():
    a = generator.build_one(UC, "Deloitte", {"usage_tier": "Low"}, {}, fake_llm_factory())
    b = generator.build_one(UC, "Deloitte", None, {}, fake_llm_factory())
    assert set(a) == set(b) == {"_degraded", "uc_id", "account", "name", "skills", "brief", "session1", "session2"}
    assert len(a["session1"]) == 3
    assert a["session2"]["recipe"]["band"] == "full"


def test_build_one_scrubs_and_falls_back():
    out = generator.build_one(UC, "Deloitte", None, {}, fake_llm_factory(leak=True))
    assert "$2M" not in json.dumps(out)


def test_build_one_survives_llm_failure():
    def boom(prompt):
        raise RuntimeError("down")
    out = generator.build_one(UC, "Deloitte", None, {}, boom)
    assert len(out["session1"]) == 3
    assert out["session2"]["recipe"]["band"] == "none"


def test_generate_workshops_cache_and_audit():
    conn = FakeConn({"TOP_SNOWFLAKE_COMPANIES": pd.DataFrame({"COMPANY_NAME": ["Roche"]})})
    rows = [UC, dict(UC, uc_id="a0X3n00000ZZZZZZZZ", account="Acme Unlisted")]
    llm = fake_llm_factory()
    s1_prompts = {}

    def complete_fn(c, model, prompt):
        if "starter-prompts" in prompt:
            s1_prompts["Roche" if '"account": "Roche"' in prompt else "other"] = prompt
        return llm(prompt)

    out = generator.generate_workshops(conn, rows, "Deloitte", complete_fn)
    assert len(out) == 2 and set(out[0]) == set(out[1])
    assert any("INSERT INTO" in q and "COCO_PSE_WORKSHOP_CACHE" in q for q in conn.queries)
    audit = [q for q in conn.queries if "INSERT INTO" in q and "WORKSHOP_GENERATION_AUDIT" in q]
    assert audit and "'listed'" in audit[0] and "'unlisted'" in audit[0]
    assert "ACCOUNT_SIGNALS" not in s1_prompts["other"]
