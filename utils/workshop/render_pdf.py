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
        out.append(Paragraph("<b>Implementation plan</b>", body))
        if plan.get("problem_statement"):
            out.append(Paragraph(_e(plan["problem_statement"]), body))
        for a in _list(plan.get("architecture")):
            out.append(Paragraph(f"&bull; {_e(a)}", body))
        for i, s in enumerate(_list(plan.get("steps")), 1):
            s = _dict(s)
            out.append(Paragraph(f"<b>Step {i}: {_e(s.get('title'))}</b> {_e(s.get('detail'))}", body))
            if s.get("sql"):
                out.append(_code(s["sql"], styles))
        for p in _list(plan.get("coco_prompts")):
            out.append(_code(p, styles))
        for c in _list(plan.get("considerations")):
            out.append(Paragraph(f"&bull; {_e(c)}", body))
        for d in _list(plan.get("docs")):
            out.append(Paragraph(_doc(d), body))
    return out
