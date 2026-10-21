import html

from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, Preformatted, Spacer, Table, TableStyle

from .render_html import SCOPE_NOTE, _conf, _dict, _list


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


def _plan_flowables(plan, styles) -> list:
    body, out = styles["body"], []
    plan = _dict(plan)
    rows = lambda key, fields: [[_e(_dict(r).get(f)) for f in fields] for r in _list(plan.get(key))]
    if plan.get("problem_statement"):
        out += [_heading("Problem Statement", styles), Paragraph(_e(plan["problem_statement"]), body)]
    t = _table(("Topic", "Previous State", "Snowflake Solution", "Status"),
               rows("executive_summary", ("topic", "previous_state", "solution", "status")), styles, (1.5, 2.0, 2.6, 1.2))
    out += ([_heading("Executive Summary", styles)] + t) if t else []
    if _list(plan.get("decision_criteria_alignment")):
        out.append(_heading("Decision Criteria Alignment", styles))
        out += [Paragraph(f"&bull; {_e(x)}", body) for x in plan["decision_criteria_alignment"]]
    if _list(plan.get("architecture_layers")) or plan.get("architecture_flow") or _list(plan.get("component_status")):
        out.append(_heading("Solution Architecture", styles))
        out += [Paragraph(f"&bull; {_e(x)}", body) for x in _list(plan.get("architecture_layers"))]
        if plan.get("architecture_flow"):
            out.append(_code(plan["architecture_flow"], styles))
        out += _table(("Component", "Status", "Details", "Source"),
                      [[_e(_dict(r).get("component")), _e(_dict(r).get("status")), _e(_dict(r).get("details")),
                        _link(_dict(r).get("source_url"), "docs") if _dict(r).get("source_url") else ""]
                       for r in _list(plan.get("component_status"))], styles, (1.8, 1.3, 3.3, 0.9))
    if _list(plan.get("sections")):
        out.append(_heading("Detailed Technical Approach", styles))
        for i, s in enumerate(plan["sections"], 1):
            s = _dict(s)
            out.append(Paragraph(f"<b>{i}. {_e(s.get('title'))}</b>", body))
            if s.get("challenge"):
                out.append(Paragraph(f"<i>Challenge:</i> {_e(s['challenge'])}", body))
            if s.get("explanation"):
                out.append(Paragraph(_e(s["explanation"]), body))
            if s.get("coco_prompt"):
                out.append(Paragraph(f"<b>CoCo Prompt:</b> {_e(s['coco_prompt'])}", body))
            if s.get("sql"):
                out.append(_code(s["sql"], styles))
                if s.get("source_url"):
                    out.append(Paragraph(f"<i>Source:</i> {_link(s['source_url'])}", body))
            out += [Paragraph(f"&bull; {_e(n)}", body) for n in _list(s.get("notes"))]
    t = _table(("CoCo Skill", "What It Does for This Use Case", "Steps"),
               rows("coco_skills", ("skill", "what_it_does", "steps")), styles, (1.6, 3.2, 2.5))
    out += ([_heading("CoCo Skills Acceleration", styles)] + t) if t else []
    t = _table(("Task", "Without CoCo", "With CoCo"), rows("before_after", ("task", "without", "with")),
               styles, (1.8, 2.75, 2.75))
    out += ([_heading("Before vs After", styles)] + t) if t else []
    t = _table(("Topic", "Verdict", "Production Ready?", "Action Required"),
               rows("decision_matrix", ("topic", "verdict", "production_ready", "action")), styles, (1.8, 1.2, 1.6, 2.7))
    out += ([_heading("Decision Matrix", styles)] + t) if t else []
    if _list(plan.get("next_steps")):
        out.append(_heading("Recommended Next Steps", styles))
        out += [Paragraph(f"{i}. {_e(x)}", body) for i, x in enumerate(plan["next_steps"], 1)]
    res = _dict(plan.get("resources"))
    links = [(label, d) for key, label in (("quickstarts", "Quickstart"), ("docs", "Docs"), ("github", "GitHub"))
             for d in _list(res.get(key)) if str(_dict(d).get("url") or "").startswith("https://")]
    if links:
        out.append(_heading("Resources", styles))
        out += [Paragraph(f"{label}: {_doc(d)}", body) for label, d in links]
    return out


def scope_note_flowable(styles):
    t = Table([[Paragraph(_e(SCOPE_NOTE), styles["body"])]], colWidths=[7.3 * 72])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HexColor("#F0F9FF")),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, HexColor("#29B5E8")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def workshop_pdf_flowables(workshops, styles) -> list:
    out = []
    h2, body = styles["heading2"], styles["body"]
    for w in workshops or []:
        w = _dict(w)
        out.append(PageBreak())
        out.append(Paragraph(f"{_e(w.get('account'))} &middot; {_e(w.get('name'))}", h2))
        out.append(Paragraph(_e(w.get("brief")), body))
        out.append(Paragraph(f"<b>Proposed CoCo skills:</b> {_e(', '.join(map(str, _list(w.get('skills')))))}", body))
        out.append(Spacer(1, 8))
        out.append(Paragraph("Session 1 &mdash; Get started with CoCo", h2))
        for i, p in enumerate(_list(w.get("session1")), 1):
            p = _dict(p)
            out.append(Paragraph(f"<b>{i}. {_e(p.get('title'))}</b> &mdash; {_e(p.get('purpose'))}", body))
            out.append(_code(p.get("prompt"), styles))
        out.append(Paragraph("Session 2 &mdash; Co-build", h2))
        s2 = _dict(w.get("session2"))
        rec, plan = _dict(s2.get("recipe")), _dict(s2.get("plan"))
        if rec.get("band") == "full":
            out.append(Paragraph(f"<b>Recommended recipe:</b> {_e(rec.get('title'))} "
                                 f"({_conf(rec.get('confidence'))}% match). {_e(rec.get('rationale'))}", body))
            out.append(_code(rec.get("body"), styles))
        elif rec.get("band") == "reference":
            out.append(Paragraph(f"Closest recipe: {_e(rec.get('title'))} &middot; "
                                 f"{_conf(rec.get('confidence'))}% &mdash; reference", body))
        if not _list(plan.get("sections")):
            out.append(Paragraph("The implementation plan for this use case is not available in this "
                                 "report. Regenerate the report to retry.", body))
        out += _plan_flowables(plan, styles)
    return out
