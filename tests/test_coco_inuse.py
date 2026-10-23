"""CoCo In-Use Use Cases section (app_pages/pse_email_hybrid_rest.py)."""
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.coco_skill_map_v2 import (  # noqa: E402
    PARTNER_SAFE_REDACTION_RULES, build_coco_inuse_prompt, parse_coco_inuse_response,
    bundled_inuse_skills, build_summary_prompt, build_ai_skill_prompt,
)


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod


@pytest.fixture(scope="module")
def page():
    """Exec only the page's definitions (not its Streamlit script body)."""
    st = mock.MagicMock()
    st.session_state = {}
    stubs = {"streamlit": st, "streamlit.components": _stub("streamlit.components"),
             "streamlit.components.v1": mock.MagicMock()}
    if importlib.util.find_spec("markdown") is None:
        stubs["markdown"] = mock.MagicMock()
    src = (ROOT / "app_pages" / "pse_email_hybrid_rest.py").read_text()
    defs = src.split("\nconn = st.session_state.conn", 1)[0]
    ns = {"__name__": "pse_page_under_test"}
    # Restore only the stubbed keys: patch.dict(sys.modules) would also evict
    # reportlab modules first imported here, breaking later lazy imports.
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        exec(compile(defs, "pse_email_hybrid_rest.py", "exec"), ns)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return types.SimpleNamespace(**ns)


COCO_DF = pd.DataFrame([
    {"USE_CASE_ID": "a", "USE_CASE_NUMBER": 1, "USE_CASE_NAME": "Small EMEA", "ACCOUNT_NAME": "Acme",
     "THEATER_NAME": "EMEA", "USE_CASE_STAGE": "3 - Technical", "USE_CASE_EACV": 100_000,
     "TECHNICAL_USE_CASE": "AI: Agents", "USE_CASE_DESCRIPTION": "Build an agent", "SE_COMMENTS": "",
     "PARTNER_COMMENTS": "", "RELEVANT_SKILL_NAMES": "agent-studio,sql-author,agent-studio",
     "WORKLOAD_CATEGORY": "AI"},
    {"USE_CASE_ID": "b", "USE_CASE_NUMBER": 2, "USE_CASE_NAME": "Big NoAM", "ACCOUNT_NAME": "Beta",
     "THEATER_NAME": "USMajors", "USE_CASE_STAGE": "7 - Deployed", "USE_CASE_EACV": 2_500_000,
     "TECHNICAL_USE_CASE": "DE: Transformation", "USE_CASE_DESCRIPTION": "dbt pipelines", "SE_COMMENTS": "",
     "PARTNER_COMMENTS": "", "RELEVANT_SKILL_NAMES": None, "WORKLOAD_CATEGORY": None},
    {"USE_CASE_ID": "c", "USE_CASE_NUMBER": 3, "USE_CASE_NAME": "Small NoAM", "ACCOUNT_NAME": "Gamma",
     "THEATER_NAME": "USMajors", "USE_CASE_STAGE": "5 - Implementation", "USE_CASE_EACV": 50_000,
     "TECHNICAL_USE_CASE": "Analytics: BI", "USE_CASE_DESCRIPTION": "reports", "SE_COMMENTS": "",
     "PARTNER_COMMENTS": "", "RELEVANT_SKILL_NAMES": "sql-author", "WORKLOAD_CATEGORY": "Analytics"},
])


def _rows(page):
    by_region = page._group_coco_inuse_by_region(COCO_DF)
    for rows in by_region.values():
        for r in rows:
            r["insight"] = f"Insight for {r['name']}."
            r["skills"] = list(r["account_skills"][:2])
    return by_region


def _report_html(page, coco_rows):
    return page._build_report_html(
        "Partner", "2026-08-01", "2026-10-31", 75, 3, 10, 30.0, 7, 1_000_000, None, [],
        {}, [{"title": "Do", "body": "thing"}], workshops=None, coco_rows_by_region=coco_rows)


def test_grouping_by_region_and_eacv(page):
    by_region = page._group_coco_inuse_by_region(COCO_DF)
    assert set(by_region) == {"NoAM", "EMEA"}
    assert [r["name"] for r in by_region["NoAM"]] == ["Big NoAM", "Small NoAM"]
    emea = by_region["EMEA"][0]
    assert emea["account_skills"] == ["agent-studio", "sql-author"]  # deduped, rank order kept
    assert emea["workload"] == "AI"
    assert by_region["NoAM"][0]["account_skills"] == [] and by_region["NoAM"][0]["workload"] == ""
    assert by_region["NoAM"][0]["stage_label"] == "Deployed"


def test_non_coco_grouping_unchanged(page):
    by_region = page._group_non_coco_by_region(COCO_DF)
    row = by_region["EMEA"][0]
    assert "relevant_skill_names" not in row and "workload_category" not in row


def test_html_section_position_and_headers(page):
    html = _report_html(page, _rows(page))
    assert "CoCo In-Use Use Cases" in html
    assert "3 use cases &middot; $2.65M EACV with CoCo in use." in html
    for h in ["CoCo Skills in Use", "Description (sanitized)", "Use Case", "Account", "Stage", "EACV"]:
        assert h in html
    gap = html.index("Description (sanitized)")
    section = html.index("CoCo In-Use Use Cases")
    nxt = html.index("Next Steps &amp; Action Plan")
    assert gap < section < nxt
    assert "NoAM &mdash; 2 use cases" in html and "my-custom-skill" not in html
    assert "Insight for Big NoAM." in html


def test_html_omits_section_without_rows(page):
    assert "CoCo In-Use Use Cases" not in _report_html(page, {})
    assert "CoCo In-Use Use Cases" not in _report_html(page, None)


def test_html_dash_when_no_skills_or_insight(page):
    rows = page._group_coco_inuse_by_region(COCO_DF)
    sec = page._coco_inuse_section_html(rows)
    assert sec.count("&mdash;") >= 6  # 3 empty chip cells + 3 empty insights (+ region bands)


def test_pdf_builds_with_section(page):
    pdf = page._build_report_pdf_bytes(
        "Partner", "2026-08-01", "2026-10-31", 75, 3, 10, 30.0, 7, 1_000_000, None, [],
        {}, [{"title": "Do", "body": "thing"}], workshops=None, coco_rows_by_region=_rows(page))
    assert pdf[:4] == b"%PDF"
    pypdf = pytest.importorskip("pypdf")
    import io
    text = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    assert "CoCo In-Use Use Cases" in text
    assert text.index("CoCo In-Use Use Cases") < text.index("Next Steps")
    assert "Insight for Big NoAM." in text


def test_prompt_rules():
    p = build_coco_inuse_prompt("UC", "desc", "SE says $2M", "partner note", ["sql-author"], "AI")
    assert PARTNER_SAFE_REDACTION_RULES in p
    assert PARTNER_SAFE_REDACTION_RULES in build_summary_prompt("d", "s")
    assert PARTNER_SAFE_REDACTION_RULES in build_ai_skill_prompt("d", "s", [])
    assert "Do not include any metrics" in p and "tokens" in p and "credits" in p
    assert "[sql-author]" in p and "Account workload category: AI" in p
    assert '"insight"' in p and '"skills"' in p


def test_parser_fallback():
    assert parse_coco_inuse_response("not json", ["sql-author"]) == {"insight": "", "skills": []}
    assert parse_coco_inuse_response(None, []) == {"insight": "", "skills": []}
    assert parse_coco_inuse_response('["x"]', ["sql-author"]) == {"insight": "", "skills": []}


def test_parser_filters_skills_to_allowed():
    raw = ('Sure: {"insight": "Goal X.", "skills": ["SQL-Author", "invented-skill", "sql-author", '
           '"agent-studio", "a", "b"]}')
    out = parse_coco_inuse_response(raw, ["sql-author", "agent-studio"])
    assert out == {"insight": "Goal X.", "skills": ["sql-author", "agent-studio"]}


def test_inuse_skills_keep_relevant_custom_and_aim():
    raw = '["$snowflake-migration:migration"],migration-guide,dashboard-json,u:my-custom-skill, SQL-AUTHOR ,sql-author'
    # unprefixed non-catalog names (dashboard-json) dropped; bundled first, then u: customs
    assert bundled_inuse_skills(raw) == ["snowflake-migration", "migration-guide", "sql-author", "my-custom-skill"]
    assert bundled_inuse_skills(None) == [] and bundled_inuse_skills(float("nan")) == []


def test_batch_llm_fallback_and_filter(page):
    page.st.session_state.clear()
    rows = page._group_coco_inuse_by_region(COCO_DF)

    def fake(conn, model, prompt, max_tokens=None):
        if "Small NoAM" in prompt:
            raise RuntimeError("boom")
        return '{"insight": "Applies CoCo.", "skills": ["sql-author", "my-custom-skill"]}'

    with mock.patch.object(page.judge_cache, "ensure_table"), \
            mock.patch.object(page.judge_cache, "batch_lookup", return_value={}), \
            mock.patch.object(page.judge_cache, "batch_insert"):
        orig = page._coco_inuse_one.__globals__["cortex_complete"]
        page._coco_inuse_one.__globals__["cortex_complete"] = fake
        try:
            out = page._build_coco_inuse_rows(None, COCO_DF, partner="P")
        finally:
            page._coco_inuse_one.__globals__["cortex_complete"] = orig
    by_name = {r["name"]: r for rs in out.values() for r in rs}
    assert by_name["Small NoAM"]["insight"] == "" and by_name["Small NoAM"]["skills"] == []
    assert by_name["Small EMEA"]["skills"] == ["sql-author"]
    assert by_name["Big NoAM"]["skills"] == []  # no account skills -> nothing allowed
    assert "raw_desc" not in by_name["Small EMEA"]
    assert rows  # grouping unaffected
