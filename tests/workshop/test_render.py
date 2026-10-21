from utils.workshop.render_html import render_workshop_html, SCOPE_NOTE

WS = [{"uc_id": "u1", "account": "Roche", "name": "Forecast <x>", "skills": ["machine-learning"],
       "brief": "Weekly demand.", "session1": [{"title": "T", "purpose": "P", "prompt": "do x"}] * 3,
       "session2": {"recipe": {"band": "full", "id": "r/1", "title": "Rec", "confidence": 90,
                               "rationale": "fits", "body": "# Steps\nrun it"},
                    "plan": {"architecture": ["a"], "steps": [{"title": "s", "detail": "d", "sql": "SELECT 1"}],
                             "coco_prompts": ["p"], "considerations": [], "docs": []}}}]

EMPTY = [{"uc_id": "u2", "account": "", "name": "", "skills": [], "brief": "", "session1": [],
          "session2": {"recipe": {"band": "none"}, "plan": {}}}]


def test_html_has_sidebar_tabs_and_no_script():
    h = render_workshop_html(WS)
    assert "<script" not in h.lower()
    assert 'type="radio"' in h and "Session 1" in h and "Session 2" in h
    assert "Forecast &lt;x&gt;" in h


def test_html_no_internal_terms():
    h = render_workshop_html(WS).lower()
    for t in ("green", "red light", "restricted", "listed", "stage 7", "deployed"):
        assert t not in h


def test_html_no_event_handlers():
    import re
    assert not re.search(r"\son[a-z]+\s*=", render_workshop_html(WS + EMPTY).lower())


def test_scope_note_wording():
    assert "not yet in production" in SCOPE_NOTE


def test_html_doc_links_https_only_and_conf_int():
    ws = [dict(WS[0], session2={"recipe": dict(WS[0]["session2"]["recipe"], confidence=87.0),
                                "plan": {"resources": {"docs": [{"title": "Good", "url": "https://docs.snowflake.com/x"},
                                                                {"title": "Bad", "url": "javascript:alert(1)"}]}}})]
    h = render_workshop_html(ws)
    assert 'href="https://docs.snowflake.com/x"' in h
    assert "javascript:" not in h
    assert "87% match" in h


def test_html_empty_values_and_body_cap():
    assert render_workshop_html(EMPTY)
    ws = [dict(WS[0], session2={"recipe": dict(WS[0]["session2"]["recipe"], body="z" * 30000), "plan": {}})]
    h = render_workshop_html(ws)
    assert "z" * 20000 + "…" in h and "z" * 20001 not in h


import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.styles import getSampleStyleSheet
from utils.workshop.render_pdf import workshop_pdf_flowables, scope_note_flowable


def _styles():
    ss = getSampleStyleSheet()
    return {"heading2": ss["Heading2"], "body": ss["BodyText"], "cell": ss["BodyText"]}


def _build(ws):
    styles = _styles()
    buf = io.BytesIO()
    story = [scope_note_flowable(styles)] + workshop_pdf_flowables(ws, styles)
    SimpleDocTemplate(buf, pagesize=letter).build(story)
    return buf.getvalue()


def test_pdf_flowables_build():
    assert _build(WS)[:4] == b"%PDF"


def test_pdf_empty_plan_and_markup_chars():
    ws = EMPTY + [dict(WS[0], name="A & B <c>", session2={
        "recipe": dict(WS[0]["session2"]["recipe"], confidence=88.0),
        "plan": {"docs": [{"title": "Good", "url": "https://x.com/?a=1&b=2"},
                          {"title": "Bad <i>", "url": "javascript:alert(1)"}]}})]
    assert _build(ws)[:4] == b"%PDF"


from utils.workshop import filter_not_deployed


def test_filter_not_deployed():
    out = filter_not_deployed({"NoAM": [{"stage_label": "Deployed"}, {"stage_label": "POC"}]})
    assert out == {"NoAM": [{"stage_label": "POC"}]}
