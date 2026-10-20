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
