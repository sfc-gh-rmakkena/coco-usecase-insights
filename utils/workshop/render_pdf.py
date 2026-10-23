import html

from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, Preformatted, Spacer, Table, TableStyle

from . import diagram
from .render_html import HANDS_ON, SCOPE_NOTE, _dict, _list, template_sections


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _code(text, styles):
    st = ParagraphStyle("wsCode", parent=styles["cell"], fontName="Courier", fontSize=7.5, leading=9.5)
    return Preformatted(str(text or "")[:6000], st, maxLineLength=110)


def _doc(d):
    d = _dict(d)
    url, title = str(d.get("url") or ""), d.get("title") or d.get("url") or ""
    if url.startswith("https://"):
        return f'<link href="{_e(url)}" color="blue">{_e(title)}</link>'
    return _e(title)


def _link(url, label=None):
    url = str(url or "")
    if url.startswith("https://"):
        return f'<link href="{_e(url)}" color="blue">{_e(label or url.replace("https://", ""))}</link>'
    return _e(label or "")


def _table(headers, rows, styles, widths):
    """rows: lists of Paragraph markup strings (already escaped)."""
    if not rows:
        return []
    cell = ParagraphStyle("wsCell", parent=styles["cell"], fontSize=7.5, leading=9.5)
    data = [[Paragraph(f"<b>{_e(h)}</b>", cell) for h in headers]] + [[Paragraph(c, cell) for c in r] for r in rows]
    t = Table(data, colWidths=[w * 72 for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), HexColor("#F1F5F9")),
                           ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#E5E7EB")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [t, Spacer(1, 6)]


def _heading(text, styles):
    return Paragraph(f"<b>{_e(text)}</b>", styles["body"])


def _h1(text, styles):
    st = ParagraphStyle("wsH1", parent=styles["body"], fontSize=12, leading=15, spaceBefore=10, spaceAfter=4,
                        textColor=HexColor("#1B2A4A"))
    return Paragraph(f"<b>{_e(text)}</b>", st)


def _callout(markup, styles):
    """CoCo Prompt callout: shaded box with a blue left rule (template .coco-prompt)."""
    t = Table([[Paragraph(markup, styles["body"])]], colWidths=[7.3 * 72])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HexColor("#F0F8FF")),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, HexColor("#29B5E8")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def _source(url, styles):
    return [Paragraph(f"<i>Source: {_link(url)}</i>", styles["body"])] if str(url or "").startswith("https://") else []


def _plan_flowables(plan, styles, w=None) -> list:
    """Same numbering, titles and tables as the HTML report (skill template sections 1-7, optional 8)."""
    body, out = styles["body"], []
    plan, w = _dict(plan), _dict(w)
    title = dict(template_sections())
    rows = lambda key, fields: [[_e(_dict(r).get(f)) for f in fields] for r in _list(plan.get(key))]
    sub = lambda t: _heading(t, styles)
    # 1. Context & Background
    out.append(_h1(title["context"], styles))
    out += [sub("Customer Overview"), Paragraph(f"{_e(w.get('account'))} is planning {_e(w.get('name'))} on Snowflake.", body)]
    if plan.get("problem_statement"):
        out += [sub("Problem Statement"), Paragraph(_e(plan["problem_statement"]), body)]
    t = _table(("Topic", "Previous State", "Snowflake Solution"),
               rows("executive_summary", ("topic", "previous_state", "solution")), styles, (1.7, 2.5, 3.1))
    out += ([sub("Executive Summary")] + t) if t else []
    if _list(plan.get("decision_criteria_alignment")):
        out.append(sub("Decision Criteria Alignment"))
        out += [Paragraph(f"&bull; {_e(x)}", body) for x in plan["decision_criteria_alignment"]]
    # 2. Solution Architecture
    out += [_h1(title["architecture"], styles), sub("Layered Architecture")]
    out += [Paragraph(f"&bull; {_e(x)}", body) for x in _list(plan.get("architecture_layers"))]
    arch = _dict(plan.get("architecture"))
    flow = diagram.render(arch) if _list(arch.get("layers")) else str(plan.get("architecture_flow") or "")
    if flow:
        out.append(_code(diagram.to_ascii(flow), styles))
    t = _table(("Component", "Details"),
               [[_e(_dict(r).get("component")),
                 _e(_dict(r).get("details")) + (f" ({_link(_dict(r)['source_url'], 'docs')})"
                                                if str(_dict(r).get("source_url") or "").startswith("https://") else "")]
                for r in _list(plan.get("component_status"))], styles, (2.0, 5.3))
    out += ([sub("Component Status")] + t) if t else []
    # 3. Detailed Technical Approach
    out.append(_h1(title["technical"], styles))
    for i, s in enumerate(_list(plan.get("sections")), 1):
        s = _dict(s)
        out.append(sub(f"3.{i} {s.get('title') or ''}"))
        if s.get("challenge"):
            out.append(Paragraph(f"<b>Challenge:</b> {_e(s['challenge'])}", body))
        if s.get("explanation"):
            out.append(Paragraph(_e(s["explanation"]), body))
        if s.get("coco_prompt"):
            out.append(_callout(f"<b>CoCo Prompt:</b> <i>{_e(s['coco_prompt'])}</i>", styles))
        if s.get("sql"):
            out.append(_code(s["sql"], styles))
            out += _source(s.get("source_url"), styles)
        out += [Paragraph(f"&bull; {_e(n)}", body) for n in _list(s.get("notes"))]
    # 4. CoCo Skills Acceleration
    out.append(_h1(title["coco"], styles))
    out += _table(("CoCo Skill", "What It Does for This Use Case", "Steps"),
                  rows("coco_skills", ("skill", "what_it_does", "steps")), styles, (1.6, 3.2, 2.5))
    t = _table(("Task", "Without CoCo", "With CoCo"), rows("before_after", ("task", "without", "with")),
               styles, (1.8, 2.75, 2.75))
    out += ([sub("Before vs After")] + t) if t else []
    # 5. Summary & Decision Matrix
    out.append(_h1(title["decision"], styles))
    out += _table(("Topic", "Verdict", "Action Required"),
                  rows("decision_matrix", ("topic", "verdict", "action")), styles, (2.0, 1.8, 3.5))
    # 6. Recommended Next Steps
    out.append(_h1(title["nextsteps"], styles))
    out += [Paragraph(f"{i}. {_e(x)}", body) for i, x in enumerate(_list(plan.get("next_steps")), 1)]
    # 7. Quickstart Resources & Documentation (two tables; legacy resources.github is ignored)
    out.append(_h1(title["resources"], styles))
    res = _dict(plan.get("resources"))
    ok = lambda k: [_dict(d) for d in _list(res.get(k)) if str(_dict(d).get("url") or "").startswith("https://")
                    and "github.com" not in str(_dict(d).get("url"))]
    t = _table(("Name", "Link"), [[_e(d.get("title")), _doc(d)] for d in ok("quickstarts")], styles, (2.8, 4.5))
    out += ([sub("Quickstarts")] + t) if t else []
    t = _table(("Feature", "URL"), [[_e(d.get("title")), _doc(d)] for d in ok("docs")], styles, (2.8, 4.5))
    out += ([sub("Documentation")] + t) if t else []
    ho = _dict(plan.get("hands_on"))
    if ho.get("intro") or ho.get("sql"):
        out.append(_h1(HANDS_ON[1], styles))
        if ho.get("intro"):
            out.append(Paragraph(_e(ho["intro"]), body))
        if ho.get("sql"):
            out.append(_code(ho["sql"], styles))
            out += _source(ho.get("source_url"), styles)
    return out


def scope_note_flowable(styles):
    t = Table([[Paragraph(_e(SCOPE_NOTE), styles["body"])]], colWidths=[7.3 * 72])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HexColor("#F0F9FF")),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, HexColor("#29B5E8")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def workshop_pdf_flowables(workshops, styles, partner: str = "") -> list:
    out = []
    h2, body = styles["heading2"], styles["body"]
    prev_reg = None
    for w in workshops or []:
        w = _dict(w)
        reg = w.get("region") or ""
        out.append(PageBreak())
        if reg and reg != prev_reg:
            # Region section heading (plans arrive sorted by region).
            out.append(Paragraph(f"{_e(reg)} use cases", styles.get("heading1", h2)))
        prev_reg = reg
        tag = f"[{_e(reg)}] " if reg else ""
        out.append(Paragraph(f"{tag}{_e(w.get('account'))} &middot; {_e(w.get('name'))}", h2))
        out.append(Paragraph(_e(w.get("brief")), body))
        out.append(Paragraph(f"<b>Proposed CoCo skills:</b> {_e(', '.join(map(str, _list(w.get('skills')))))}", body))
        out.append(Spacer(1, 8))
        out.append(Paragraph("Session 1 &mdash; Get started with CoCo", h2))
        for i, p in enumerate(_list(w.get("session1")), 1):
            p = _dict(p)
            out.append(Paragraph(f"<b>{i}. {_e(p.get('title'))}</b> &mdash; {_e(p.get('purpose'))}", body))
            out.append(_code(p.get("prompt"), styles))
        out.append(Paragraph("Session 2 &mdash; Co-build", h2))
        # Only the plan is rendered; any legacy session2.recipe in cached payloads is ignored.
        plan = _dict(_dict(w.get("session2")).get("plan"))
        if not _list(plan.get("sections")):
            out.append(Paragraph("The implementation plan for this use case is not available in this "
                                 "report. Regenerate the report to retry.", body))
        else:
            if partner:
                out.append(Paragraph(f"Recommended Implementation Plan &middot; prepared with {_e(partner)}", body))
            out += _plan_flowables(plan, styles, w)
    return out
