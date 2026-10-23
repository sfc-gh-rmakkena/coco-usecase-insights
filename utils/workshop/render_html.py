import datetime
import functools
import html
import re
_NUM_PREFIX = re.compile(r"^\d+\.\s*")

from . import assets, diagram
from .css_scope import prefix_css

SCOPE_NOTE = ("The summary above reflects all use cases in the selected period. The sections that follow "
              "focus only on use cases not yet in production — each with a ready-to-run workshop plan for "
              "the partner and Snowflake to co-build with the customer.")

def _h(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _dict(v) -> dict:
    return v if isinstance(v, dict) else {}


def scope_note_html() -> str:
    return (f'<div style="border-left:3px solid #29b5e8;background:#f0f9ff;padding:10px 14px;'
            f'font-size:12.5px;color:#0f172a;margin:22px 0 6px;">{_h(SCOPE_NOTE)}</div>')


def _md_block(text):
    return (f'<pre style="white-space:pre-wrap;font-size:11.5px;background:#f8fafc;padding:10px;'
            f'border-radius:4px;">{_h(text)}</pre>')


def _session1(items):
    out = ""
    for i, p in enumerate(_list(items), 1):
        p = _dict(p)
        out += (f'<div style="margin:0 0 12px;"><b>{i}. {_h(p.get("title"))}</b>'
                f'<div style="color:#6b7280;font-size:12px;">{_h(p.get("purpose"))}</div>'
                f'{_md_block(p.get("prompt"))}</div>')
    return out



_TEMPLATE = "pse-uc-implementation-plan/templates/report_template.html"
SCOPE = ".sgx"
# Host-page adjustments layered on the template: Snowflake-blue band, page-embedded spacing.
_OVERRIDES = (".header{background:#29B5E8;margin:0 0 24px;padding:32px 28px;border-radius:8px}"
              ".header .logo{color:#FFFFFF}.header h1{color:#FFFFFF;border:0;padding:0}"
              ".header h2{color:#0B3D5C}.header .meta{opacity:.9;color:#FFFFFF}"
              "body{max-width:none;padding:0}h1{font-size:1.45em}")


@functools.lru_cache(maxsize=None)
def template_sections() -> tuple:
    """(anchor, title) for each numbered h1 in the skill's report template, in order."""
    t = assets.skill_text(_TEMPLATE)
    return tuple((a, html.unescape(x)) for a, x in re.findall(r'<h1 id="([^"]+)">(.*?)</h1>', t))


@functools.lru_cache(maxsize=None)
def report_css() -> str:
    """The template's stylesheet, scoped under SCOPE so it cannot leak into the host page."""
    css = re.search(r"<style>(.*?)</style>", assets.skill_text(_TEMPLATE), re.S).group(1)
    return prefix_css(css + _OVERRIDES, SCOPE)


# Titles of the template's numbered sections (e.g. "1. Context & Background").
S2_HEADINGS = tuple(t for _, t in template_sections())
HANDS_ON = ("handson", "8. Hands-On Exercise")


def uc_slug(w, i) -> str:
    return f"sgx{i}-" + (re.sub(r"[^A-Za-z0-9]+", "-", str(_dict(w).get("uc_id") or "")).strip("-").lower() or "uc")


def _rtable(headers, rows):
    """Template-styled table; rows are lists of pre-escaped cell HTML."""
    if not rows:
        return ""
    head = "".join(f"<th>{_h(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _a(url, label=None):
    url = str(url or "")
    if url.startswith("https://"):
        return f'<a href="{_h(url)}" target="_blank" rel="noopener noreferrer">{_h(label or url.replace("https://", ""))}</a>'
    return _h(label or "")


def _source(url):
    return f'<p class="source">Source: {_a(url)}</p>' if str(url or "").startswith("https://") else ""


def _rul(items, tag="ul"):
    items = [x for x in _list(items) if str(x).strip()]
    return f"<{tag}>" + "".join(f"<li>{_h(x)}</li>" for x in items) + f"</{tag}>" if items else ""


def _tech_section(n, s):
    s = _dict(s)
    out = f"<h2>3.{n} {_h(s.get('title'))}</h2>"
    if s.get("challenge"):
        out += f"<p><strong>Challenge:</strong> {_h(s['challenge'])}</p>"
    if s.get("explanation"):
        out += f"<p>{_h(s['explanation'])}</p>"
    if s.get("coco_prompt"):
        out += f'<div class="coco-prompt"><strong>CoCo Prompt:</strong> {_h(s["coco_prompt"])}</div>'
    if s.get("sql"):
        out += f"<pre>{_h(s['sql'])}</pre>" + _source(s.get("source_url"))
    return out + _rul(s.get("notes"))


def _diagram_text(plan):
    arch = _dict(plan.get("architecture"))
    return diagram.render(arch) if _list(arch.get("layers")) else str(plan.get("architecture_flow") or "")


def report_html(w, slug, partner="", date=None) -> str:
    """Session 2 plan rendered with the skill's report template structure (scoped under SCOPE)."""
    w = _dict(w)
    plan = _dict(_dict(w.get("session2")).get("plan"))
    secs = dict(template_sections())
    ho = _dict(plan.get("hands_on"))
    order = [a for a, _ in template_sections()] + ([HANDS_ON[0]] if ho.get("intro") or ho.get("sql") else [])
    title = dict(secs, **{HANDS_ON[0]: HANDS_ON[1]})
    hid = lambda a: f"{slug}-{a}"
    h1 = lambda a: f'<h1 id="{hid(a)}">{_h(title[a])}</h1>'
    date = date or datetime.date.today().strftime("%B %Y")
    meta = (f"Prepared with: {_h(partner)}<br />" if partner else "") + \
        f"Prepared by: Snowflake Partner Solutions Engineering (PSE)<br />Date: {_h(date)}"
    out = (f'<div class="header"><div class="logo">SNOWFLAKE</div><h1>{_h(w.get("account"))}</h1>'
           f'<h2>{_h(w.get("name"))}</h2>'
           f'<div style="margin:12px 0 8px;font-size:0.95em;letter-spacing:2px;text-transform:uppercase;'
           f'color:#FFFFFF;font-weight:600;">Recommended Implementation Plan</div>'
           f'<div class="meta">{meta}</div></div>')
    toc_title = {a: _h(_NUM_PREFIX.sub("", title[a])) for a in order}
    out += ('<div class="toc"><h3>Table of Contents</h3><ol>' + "".join(
        f'<li><a href="#{hid(a)}">{toc_title[a]}</a></li>' for a in order) + "</ol></div>")
    # 1. Context & Background
    out += h1("context") + "<h2>Customer Overview</h2>" + \
        f"<p>{_h(w.get('account'))} is planning {_h(w.get('name'))} on Snowflake.</p>"
    if plan.get("problem_statement"):
        out += f"<h2>Problem Statement</h2><p>{_h(plan['problem_statement'])}</p>"
    rows = [[_h(_dict(r).get("topic")), _h(_dict(r).get("previous_state")), _h(_dict(r).get("solution"))]
            for r in _list(plan.get("executive_summary"))]
    if rows:
        out += "<h2>Executive Summary</h2>" + _rtable(("Topic", "Previous State", "Snowflake Solution"), rows)
    if _list(plan.get("decision_criteria_alignment")):
        out += "<h2>Decision Criteria Alignment</h2>" + _rul(plan["decision_criteria_alignment"])
    # 2. Solution Architecture
    out += h1("architecture") + "<h2>Layered Architecture</h2>" + _rul(plan.get("architecture_layers"))
    flow = _diagram_text(plan)
    if flow:
        out += f"<pre>{_h(flow)}</pre>"
    rows = [[_h(_dict(r).get("component")),
             _h(_dict(r).get("details")) + (f" ({_a(_dict(r)['source_url'], 'docs')})"
                                            if str(_dict(r).get("source_url") or "").startswith("https://") else "")]
            for r in _list(plan.get("component_status"))]
    if rows:
        out += "<h2>Component Status</h2>" + _rtable(("Component", "Details"), rows)
    # 3. Detailed Technical Approach
    out += h1("technical") + "".join(_tech_section(n, s) for n, s in enumerate(_list(plan.get("sections")), 1))
    # 4. CoCo Skills Acceleration
    out += h1("coco") + _rtable(("CoCo Skill", "What It Does for This Use Case", "Steps"), [
        [_h(_dict(r).get(k)) for k in ("skill", "what_it_does", "steps")] for r in _list(plan.get("coco_skills"))])
    if _list(plan.get("before_after")):
        out += "<h2>Before vs After</h2>" + _rtable(("Task", "Without CoCo", "With CoCo"), [
            [_h(_dict(r).get(k)) for k in ("task", "without", "with")] for r in plan["before_after"]])
    # 5. Summary & Decision Matrix
    out += h1("decision") + _rtable(("Topic", "Verdict", "Action Required"), [
        [_h(_dict(r).get("topic")), _h(_dict(r).get("verdict")), _h(_dict(r).get("action"))] for r in _list(plan.get("decision_matrix"))])
    # 6. Recommended Next Steps
    out += h1("nextsteps") + _rul(plan.get("next_steps"), "ol")
    # 7. Quickstart Resources & Documentation (two tables; legacy resources.github is ignored)
    res = _dict(plan.get("resources"))
    ok = lambda k: [_dict(d) for d in _list(res.get(k)) if str(_dict(d).get("url") or "").startswith("https://")
                    and "github.com" not in str(_dict(d).get("url"))]
    out += h1("resources")
    if ok("quickstarts"):
        out += "<h2>Quickstarts</h2>" + _rtable(("Name", "Link"), [[_h(d.get("title")), _a(d["url"], d.get("title"))]
                                                                  for d in ok("quickstarts")])
    if ok("docs"):
        out += "<h2>Documentation</h2>" + _rtable(("Feature", "URL"), [
            [_h(d.get("title")), _a(d["url"], d.get("title"))] for d in ok("docs")])
    if HANDS_ON[0] in order:
        out += h1(HANDS_ON[0]) + (f"<p>{_h(ho['intro'])}</p>" if ho.get("intro") else "")
        if ho.get("sql"):
            out += f"<pre>{_h(ho['sql'])}</pre>" + _source(ho.get("source_url"))
    return f'<div class="{SCOPE[1:]}">{out}</div>'


def _session2(s2, w=None, slug="sgx", partner=""):
    # Only the plan is rendered; any legacy session2.recipe in cached payloads is ignored.
    plan = _dict(_dict(s2).get("plan"))
    if not _list(plan.get("sections")):
        return ('<p style="font-size:12.5px;color:#92400e;">The implementation plan for this use case is not '
                      'available in this report. Regenerate the report to retry.</p>')
    return report_html(dict(_dict(w), session2={"plan": plan}), slug, partner)



REGION_COLORS = {"NoAM": "#2563eb", "EMEA": "#7c3aed", "APJ": "#059669", "LATAM": "#d97706"}


def _region_chip(reg):
    if not reg:
        return ""
    c = REGION_COLORS.get(reg, "#64748b")
    return (f'<span style="display:inline-block;font-size:10.5px;font-weight:700;color:{c};'
            f'border:1px solid {c};border-radius:10px;padding:1px 8px;margin-bottom:6px;">{_h(reg)}</span>')


def render_workshop_html(workshops: list, partner: str = "") -> str:
    if not workshops:
        return ""
    css = [report_css(), ".ws-pane,.ws-sec{display:none}",
           ".ws-side label{display:block;padding:8px 10px;border-radius:4px;cursor:pointer;font-size:12px;color:#374151}",
           ".ws-tabs label{display:inline-block;padding:6px 12px;margin-right:4px;border-bottom:2px solid transparent;cursor:pointer;font-size:12.5px}",
           ".ws input{display:none}"]
    radios, side, panes = "", "", ""
    counts = {}
    for w in workshops:
        reg = _dict(w).get("region") or ""
        counts[reg] = counts.get(reg, 0) + 1
    prev_reg = None
    for i, w in enumerate(workshops):
        w = _dict(w)
        reg = w.get("region") or ""
        color = REGION_COLORS.get(reg, "#94a3b8")
        radios += f'<input type="radio" name="ws-uc" id="ws-uc-{i}"{" checked" if i == 0 else ""}>'
        if reg and reg != prev_reg:
            side += (f'<div style="font-size:11px;font-weight:800;letter-spacing:.04em;color:{color};'
                     f'text-transform:uppercase;margin:{"0" if prev_reg is None else "12px"} 0 4px;'
                     f'padding-left:6px;">{_h(reg)} ({counts[reg]})</div>')
        prev_reg = reg
        side += (f'<label for="ws-uc-{i}" style="border-left:3px solid {color};">'
                 f'<b>{_h(w.get("account"))}</b><br>{_h(w.get("name"))}</label>')
        css.append(f"#ws-uc-{i}:checked~.ws-body .ws-p{i}{{display:block}}")
        css.append(f"#ws-uc-{i}:checked~.ws-body .ws-side label[for=ws-uc-{i}]{{background:#e0f2fe;color:#0c4a6e}}")
        tabs = "".join(f'<input type="radio" name="ws-t-{i}" id="ws-t-{i}-{k}"{" checked" if k == "a" else ""}>'
                       for k in "abc")
        bar = "".join(f'<label for="ws-t-{i}-{k}">{n}</label>'
                      for k, n in zip("abc", ("Brief", "Session 1", "Session 2")))
        for k in "abc":
            css.append(f"#ws-t-{i}-{k}:checked~.ws-s{k}{{display:block}}")
            css.append(f"#ws-t-{i}-{k}:checked~.ws-tabs label[for=ws-t-{i}-{k}]{{border-bottom-color:#29b5e8;font-weight:700}}")
        skills = ", ".join(_h(s) for s in _list(w.get("skills")))
        panes += (f'<div class="ws-pane ws-p{i}">{tabs}<div class="ws-tabs" style="border-bottom:1px solid #e5e7eb;margin-bottom:12px;">{bar}</div>'
                  f'<div class="ws-sec ws-sa">{_region_chip(reg)}<h3 style="margin:0 0 6px;">{_h(w.get("name"))}</h3>'
                  f'<p style="font-size:12.5px;">{_h(w.get("brief"))}</p><p style="font-size:12px;"><b>Proposed CoCo skills:</b> {skills}</p></div>'
                  f'<div class="ws-sec ws-sb"><h3 style="margin:0 0 6px;">Session 1 — Get started with CoCo</h3>{_session1(w.get("session1"))}</div>'
                  f'<div class="ws-sec ws-sc"><h3 style="margin:0 0 6px;">Session 2 — Co-build</h3>{_session2(w.get("session2"), w, uc_slug(w, i), partner)}</div></div>')
    return (f'<style>{"".join(css)}</style>'
            f'<div style="font-size:14px;font-weight:800;color:#0f172a;margin:26px 0 8px;">Workshop Plans</div>'
            f'<div class="ws">{radios}<div class="ws-body" style="display:flex;gap:14px;border:1px solid #e5e7eb;border-radius:6px;padding:10px;">'
            f'<div class="ws-side" style="flex:0 0 220px;border-right:1px solid #f1f5f9;padding-right:8px;">{side}</div>'
            f'<div style="flex:1;min-width:0;">{panes}</div></div></div>')
