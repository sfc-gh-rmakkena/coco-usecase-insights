"""Golden parity: Session 2 HTML follows the pse-uc-implementation-plan report template."""
import html
import json
import re
from pathlib import Path

import pytest

from tests.workshop.test_skill_alignment import DISNEY_CTX, DISNEY_UC
from utils.workshop import assets, capabilities, prompts
from utils.workshop.css_scope import selectors
from utils.workshop.render_html import SCOPE, render_workshop_html, report_css

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "disney_plan.json").read_text())
TEMPLATE = assets.skill_text("pse-uc-implementation-plan/templates/report_template.html")
REFERENCE = Path.home() / "Downloads" / "Disney_Experiences_Financial_Transformation_Phase3_Solution_Guide.html"
# Deliberate exclusions vs the skill reference HTML: the reference also has a "Status" column in
# Executive Summary, Component Status and Documentation, a "Production Ready?" column in the
# Decision Matrix, and a third "GitHub Repositories" resource table. These are dropped on purpose
# (generic status filler, unverifiable repo links) and are not compared.
RESOURCE_HEADERS = [["Name", "Link"], ["Feature", "URL"]]
TABLE_HEADERS = {"Executive Summary": ["Topic", "Previous State", "Snowflake Solution"],
                 "Component Status": ["Component", "Details"]}
DECISION_HEADERS = ["Topic", "Verdict", "Action Required"]
REQUIRED = prompts.primary_capabilities(DISNEY_UC, DISNEY_CTX)


def _h1s(text):
    return [html.unescape(re.sub(r"<[^>]+>", "", t)).strip() for t in re.findall(r"<h1 id=[^>]*>(.*?)</h1>", text, re.S)]


def _resource_headers(text):
    part = text[text.find("7. Quickstart Resources"):]
    return [re.findall(r"<th>(.*?)</th>", t) for t in re.findall(r"<thead>(.*?)</thead>", part, re.S)]


@pytest.fixture(scope="module")
def page():
    return render_workshop_html([FIXTURE, dict(FIXTURE, uc_id="other-uc")], "Deloitte Consulting")


@pytest.fixture(scope="module")
def report(page):
    """The first use case's report (scoped container)."""
    start = page.find('<div class="sgx">')
    return page[start:page.find('<div class="sgx">', start + 1)]


def test_header_band(report):
    assert '<div class="header"><div class="logo">SNOWFLAKE</div>' in report
    assert f"<h1>{html.escape(FIXTURE['account'])}</h1>" in report and f"<h2>{html.escape(FIXTURE['name'])}</h2>" in report
    assert "Recommended Implementation Plan" in report and "Prepared with: Deloitte Consulting" in report
    assert FIXTURE["uc_id"] not in re.sub(r'(id|href)="[^"]*"', "", report)  # no internal id in text
    css = report_css()
    assert ".sgx .header{background:#29B5E8" in css and re.search(r"\.sgx \.header h1\{[^}]*color: ?#FFFFFF", css)


def test_toc_anchors_resolve_to_unique_ids(page, report):
    toc = re.search(r'<div class="toc">.*?</div>', report, re.S).group(0)
    links = re.findall(r'href="#([^"]+)"', toc)
    assert len(links) == 7
    ids = re.findall(r'\sid="([^"]+)"', page)
    assert len(ids) == len(set(ids))  # unique across both use cases
    assert all(l in ids for l in links)


def test_numbered_h1_titles_match_template(report):
    assert _h1s(report) == _h1s(TEMPLATE)


def test_coco_prompts_and_sources(report):
    n = len(FIXTURE["session2"]["plan"]["sections"])
    assert report.count('<div class="coco-prompt">') == n
    tech = report[report.find("3. Detailed Technical Approach"):report.find("4. CoCo Skills Acceleration")]
    for m in re.finditer(r"</pre>", tech):
        assert tech[m.end():].startswith('<p class="source">Source: <a href="https://')


def _headers_after(text, marker):
    part = text[text.find(marker):]
    return re.findall(r"<th>(.*?)</th>", re.search(r"<thead>(.*?)</thead>", part, re.S).group(1))


def test_table_headers_have_no_status_columns(report):
    for h2, cols in TABLE_HEADERS.items():
        assert _headers_after(report, f"<h2>{h2}</h2>") == cols, h2
    assert _headers_after(report, "5. Summary") == DECISION_HEADERS


def test_two_resource_tables(report):
    assert _resource_headers(report) == RESOURCE_HEADERS
    assert "GitHub Repositories" not in report and "github.com" not in report


LEGACY = json.loads(json.dumps(FIXTURE))
LEGACY["session2"]["recipe"] = {"band": "full", "id": "r/1", "title": "Cookbook recipe X", "confidence": 91,
                               "rationale": "cookbook fit", "body": "# Recipe steps"}
_lp = LEGACY["session2"]["plan"]
for _k, _f in (("executive_summary", "status"), ("component_status", "status"),
               ("decision_matrix", "production_ready")):
    for _r in _lp[_k]:
        _r[_f] = "Production Ready"
for _d in _lp["resources"]["docs"]:
    _d["status"] = "GA"
_lp["resources"]["github"] = [{"title": "Repo", "url": "https://github.com/Snowflake-Labs/x",
                               "description": "repo"}]
FORBIDDEN = ("recipe", "Recipe", "cookbook", "% match", "Closest", "github.com", "GitHub Repositories",
             "Production Ready")


def test_legacy_payload_renders_without_dropped_content():
    import io
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, Preformatted, Table
    from utils.workshop.render_pdf import workshop_pdf_flowables

    page = re.sub(r"<style>.*?</style>", "", render_workshop_html([LEGACY], "P"), flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    for t in FORBIDDEN:
        assert t not in page and t not in text, t
    assert "<th>Status</th>" not in page

    ss = getSampleStyleSheet()
    flow = workshop_pdf_flowables([LEGACY], {"heading2": ss["Heading2"], "body": ss["BodyText"],
                                             "cell": ss["BodyText"]})

    def texts(f):
        if isinstance(f, Paragraph):
            yield f.text
        elif isinstance(f, Preformatted):
            yield "\n".join(f.lines)
        elif isinstance(f, Table):
            for row in f._cellvalues:
                for c in row:
                    yield from texts(c)
    pdf_text = "\n".join(t for f in flow for t in texts(f))
    for t in FORBIDDEN:
        assert t not in pdf_text, t
    assert "<b>Status</b>" not in pdf_text


def test_diagram_contains_medallion_and_required_caps(report):
    pre = html.unescape(re.search(r'id="[^"]*-architecture">.*?<pre>(.*?)</pre>', report, re.S).group(1))
    for t in ("Openflow", "BRONZE", "SILVER", "GOLD"):
        assert t in pre
    for k in REQUIRED:
        assert capabilities.cap_matches(k, pre), k


def test_safe_markup(page):
    assert "<script" not in page.lower()
    assert not re.search(r"\son\w+\s*=", page, re.I)
    assert "http://" not in page


def test_css_selectors_all_prefixed():
    for s in selectors(report_css()):
        assert s == SCOPE or s.startswith(SCOPE + " "), s


@pytest.mark.skipif(not REFERENCE.exists(), reason="reference skill HTML not present")
def test_parity_with_reference_skill_html(report):
    ref = REFERENCE.read_text(encoding="utf-8")
    assert _h1s(report) == _h1s(ref)
    # Resource tables: ours must be the reference's minus the deliberate exclusions above.
    drop = {"Status", "Repo", "Description"}
    expected = [[c for c in t if c not in drop] for t in _resource_headers(ref) if "Repo" not in t]
    assert _resource_headers(report) == expected
