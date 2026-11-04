from utils.workshop import prompts

UC = {"uc_id": "u1", "name": "Demand Forecasting", "account": "Roche",
      "skills": ["machine-learning", "snowflake-notebooks"], "sanitized_desc": "Forecast weekly demand."}


def test_session1_prompt_listed_includes_tiers_not_numbers():
    p = prompts.session1_prompt(UC, "Deloitte", {"usage_tier": "Low", "surfaces": ["Snowsight"],
                                                 "enablement_needed": False, "dominant_maturity": "L2"})
    assert "coco-customer-activation-planner" in p or "Activation" in p
    assert "Low" in p and "APP OVERRIDE" in p


def test_session1_prompt_unlisted_has_no_account_signals():
    p = prompts.session1_prompt(UC, "Deloitte", None)
    assert "usage_tier" not in p and "ACCOUNT_SIGNALS" not in p


def test_recipe_match_prompt_removed():
    assert not hasattr(prompts, "recipe_match_prompt") and not hasattr(prompts, "RECIPE_SCHEMA")


def test_session2_prompt_carries_private_context_and_allowlist():
    p = prompts.session2_prompt(UC, "Deloitte", {"SE_COMMENTS": "x"}, None)
    assert "PRIVATE_CONTEXT" in p and "ALLOWED_LINKS" in p and "Red Light" in p
