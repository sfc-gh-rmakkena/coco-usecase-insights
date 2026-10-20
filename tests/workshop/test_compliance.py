from utils.workshop.compliance import normalize_company, find_violations, scrub


def test_normalize_strips_suffixes_and_punct():
    assert normalize_company("24 Hour Fitness Usa, Inc.") == "24 hour fitness usa"
    assert normalize_company("The Kroger Co.") == "kroger"
    assert normalize_company("AT&T Inc") == "at and t"
    assert normalize_company("") == ""


def test_normalize_does_not_fuzzy_match():
    assert normalize_company("Roche Bobois") != normalize_company("Roche")


def test_find_violations_flags_money_credits_and_terms():
    text = "EACV is $1.2M and they burn 5,000 credits. Account is on the green list."
    hits = find_violations(text)
    assert any("1.2M" in h for h in hits)
    assert any("credits" in h for h in hits)
    assert any("green list" in h.lower() for h in hits)


def test_find_violations_clean_text():
    assert find_violations("Build a Cortex Search service over product manuals.") == []


def test_scrub_drops_bad_sentences_and_unlisted_links():
    text = ("Use Cortex Search. Spend is $40K per month. "
            "See https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search "
            "and https://evil.example.com/x.")
    allow = {"https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search"}
    out = scrub(text, allow)
    assert "$40K" not in out
    assert "evil.example.com" not in out
    assert "docs.snowflake.com" in out
    assert out.startswith("Use Cortex Search.")


import pytest

A = "https://docs.snowflake.com/en/x"


@pytest.mark.parametrize("t", ["Spend is USD 40,000.", "EUR 40k spend.", "Budget 1.2 million dollars.",
                               "It costs 40K/month.", "Revenue of 2M.", "Pricing ¥10"])
def test_money_variants_flagged(t):
    assert find_violations(t)


def test_tokens_not_money():
    assert find_violations("1.5M tokens per day") == []


@pytest.mark.parametrize("t", ["5k credits", "5,000 Snowflake credits", "credits: 5000"])
def test_credit_variants_flagged(t):
    assert find_violations(t)


def test_credit_card_not_flagged():
    assert find_violations("credit card fraud detection") == []


@pytest.mark.parametrize("t", ["greenlisted", "red-lighted"])
def test_list_variants_flagged(t):
    assert find_violations(t)


@pytest.mark.parametrize("t", ["Load into stage 1 table.", "create a stage"])
def test_data_stage_not_flagged(t):
    assert find_violations(t) == []


def test_sales_stage_flagged():
    assert find_violations("use case stage 7")


def test_arr_lowercase_code_not_flagged():
    assert find_violations("arr[0]") == []
    assert find_violations("ARR grew") and find_violations("Run-Rate")


def test_scrub_preserves_lines():
    out = scrub("Line1\n\n- item $5\n- item2", set())
    assert out == "Line1\n\n- item2"


def test_scrub_link_in_backticks_kept():
    assert A in scrub(f"See `{A}` now.", {A})


def test_scrub_markdown_link_trailing_punct_kept():
    out = scrub(f"[doc]({A}).", {A + "/"})
    assert out == f"[doc]({A})."


def test_scrub_disallowed_link_removed_keeps_punct():
    out = scrub("Go to https://evil.example.com/x.", {A})
    assert "evil" not in out and out.endswith(".")


def test_normalize_unicode_and_dotted():
    assert normalize_company("Nestlé S.A.") == "nestle"


def test_normalize_never_empty_for_nonempty():
    assert normalize_company("The Company") != ""
