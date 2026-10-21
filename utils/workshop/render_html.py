import html

SCOPE_NOTE = ("The summary above reflects all use cases in the selected period. The sections that follow "
              "focus only on use cases not yet in production — each with a ready-to-run workshop plan for "
              "the partner and Snowflake to co-build with the customer.")

_HTML_BODY_CAP = 20000


def _h(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _conf(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _cap(text, n):
    text = str(text or "")
    return text[:n] + "…" if len(text) > n else text


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


def _doc_link(d):
    d = _dict(d)
    url, title = str(d.get("url") or ""), d.get("title") or d.get("url") or ""
    if url.startswith("https://"):
        return f'<a href="{_h(url)}" target="_blank" rel="noopener noreferrer">{_h(title)}</a>'
    return _h(title)


def _session1(items):
    out = ""
    for i, p in enumerate(_list(items), 1):
        p = _dict(p)
        out += (f'<div style="margin:0 0 12px;"><b>{i}. {_h(p.get("title"))}</b>'
                f'<div style="color:#6b7280;font-size:12px;">{_h(p.get("purpose"))}</div>'
                f'{_md_block(p.get("prompt"))}</div>')
    return out


_TH = 'style="text-align:left;padding:5px 8px;background:#f1f5f9;border-bottom:1px solid #e5e7eb;"'
_TD = 'style="padding:5px 8px;border-bottom:1px solid #f1f5f9;vertical-align:top;"'
S2_HEADINGS = ("Problem Statement", "Executive Summary", "Decision Criteria Alignment", "Solution Architecture",
               "Detailed Technical Approach", "CoCo Skills Acceleration", "Before vs After", "Decision Matrix",
               "Recommended Next Steps", "Resources")


def _h4(t):
    return f'<h4 style="margin:16px 0 6px;color:#0f172a;">{_h(t)}</h4>'


def _url_link(url, label=None):
    url = str(url or "")
    if url.startswith("https://"):
        return (f'<a href="{_h(url)}" target="_blank" rel="noopener noreferrer">'
                f'{_h(label or url.replace("https://", ""))}</a>')
    return _h(label or "")


def _table(headers, rows):
    """rows: lists of pre-escaped cell HTML."""
    if not rows:
        return ""
    head = "".join(f"<th {_TH}>{_h(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td {_TD}>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table style="border-collapse:collapse;width:100%;font-size:12px;margin:4px 0 10px;">' \
           f'<tr>{head}</tr>{body}</table>'


def _ul(items, tag="ul"):
    items = [x for x in _list(items) if str(x).strip()]
    return f"<{tag}>" + "".join(f"<li>{_h(x)}</li>" for x in items) + f"</{tag}>" if items else ""


def _section(i, s):
    s = _dict(s)
    out = f'<div style="margin:10px 0 14px;"><b>{i}. {_h(s.get("title"))}</b>'
    if s.get("challenge"):
        out += f'<div style="font-size:12px;"><i>Challenge:</i> {_h(s["challenge"])}</div>'
    if s.get("explanation"):
        out += f'<div style="font-size:12.5px;margin:4px 0;">{_h(s["explanation"])}</div>'
    if s.get("coco_prompt"):
        out += (f'<div style="border-left:3px solid #29b5e8;background:#f0f9ff;padding:6px 10px;font-size:12px;'
                f'margin:6px 0;"><b>CoCo Prompt:</b> {_h(s["coco_prompt"])}</div>')
    if s.get("sql"):
        out += _md_block(s["sql"])
        if s.get("source_url"):
            out += f'<p style="font-size:11px;color:#706e6b;font-style:italic;margin:2px 0;">Source: {_url_link(s["source_url"])}</p>'
    out += _ul(s.get("notes"))
    return out + "</div>"


def _resources(res):
    res = _dict(res)
    out = ""
    for key, label in (("quickstarts", "Quickstarts"), ("docs", "Documentation"), ("github", "GitHub")):
        links = [d for d in _list(res.get(key)) if str(_dict(d).get("url") or "").startswith("https://")]
        if links:
            out += f"<b>{label}</b><ul>" + "".join(f"<li>{_doc_link(d)}</li>" for d in links) + "</ul>"
    return out


def _session2(s2):
    s2 = _dict(s2)
    rec, plan = _dict(s2.get("recipe")), _dict(s2.get("plan"))
    out = ""
    if rec.get("band") == "full":
        out += (f'<h4 style="margin:0 0 6px;">Recommended recipe: {_h(rec.get("title"))} '
                f'<span style="background:#dcfce7;color:#166534;border-radius:10px;padding:1px 8px;font-size:11px;">'
                f'{_conf(rec.get("confidence"))}% match</span></h4>'
                f'<p style="font-size:12px;">{_h(rec.get("rationale"))}</p>'
                f'{_md_block(_cap(rec.get("body"), _HTML_BODY_CAP))}')
    elif rec.get("band") == "reference":
        out += (f'<p style="font-size:12px;color:#6b7280;">Closest recipe: {_h(rec.get("title"))} · '
                f'{_conf(rec.get("confidence"))}% — reference</p>')
    if not _list(plan.get("sections")):
        out += ('<p style="font-size:12.5px;color:#92400e;">The implementation plan for this use case is not '
                'available in this report. Regenerate the report to retry.</p>')
    if plan.get("problem_statement"):
        out += _h4("Problem Statement") + f'<p style="font-size:12.5px;">{_h(plan["problem_statement"])}</p>'
    out += (_h4("Executive Summary") + _table(("Topic", "Previous State", "Snowflake Solution", "Status"), [
        [_h(_dict(r).get(k)) for k in ("topic", "previous_state", "solution", "status")]
        for r in _list(plan.get("executive_summary"))])) if _list(plan.get("executive_summary")) else ""
    if _list(plan.get("decision_criteria_alignment")):
        out += _h4("Decision Criteria Alignment") + _ul(plan["decision_criteria_alignment"])
    if _list(plan.get("architecture_layers")) or plan.get("architecture_flow") or _list(plan.get("component_status")):
        out += _h4("Solution Architecture") + _ul(plan.get("architecture_layers"))
        if plan.get("architecture_flow"):
            out += _md_block(plan["architecture_flow"])
        out += _table(("Component", "Status", "Details", "Source"), [
            [_h(_dict(r).get("component")), _h(_dict(r).get("status")), _h(_dict(r).get("details")),
             _url_link(_dict(r).get("source_url"), "docs") if _dict(r).get("source_url") else ""]
            for r in _list(plan.get("component_status"))])
    if _list(plan.get("sections")):
        out += _h4("Detailed Technical Approach") + "".join(
            _section(i, s) for i, s in enumerate(plan["sections"], 1))
    if _list(plan.get("coco_skills")):
        out += _h4("CoCo Skills Acceleration") + _table(("CoCo Skill", "What It Does for This Use Case", "Steps"), [
            [_h(_dict(r).get(k)) for k in ("skill", "what_it_does", "steps")] for r in plan["coco_skills"]])
    if _list(plan.get("before_after")):
        out += _h4("Before vs After") + _table(("Task", "Without CoCo", "With CoCo"), [
            [_h(_dict(r).get(k)) for k in ("task", "without", "with")] for r in plan["before_after"]])
    if _list(plan.get("decision_matrix")):
        out += _h4("Decision Matrix") + _table(("Topic", "Verdict", "Production Ready?", "Action Required"), [
            [_h(_dict(r).get(k)) for k in ("topic", "verdict", "production_ready", "action")]
            for r in plan["decision_matrix"]])
    if _list(plan.get("next_steps")):
        out += _h4("Recommended Next Steps") + _ul(plan["next_steps"], "ol")
    res = _resources(plan.get("resources"))
    if res:
        out += _h4("Resources") + res
    return out


def render_workshop_html(workshops: list) -> str:
    if not workshops:
        return ""
    css = [".ws-pane,.ws-sec{display:none}",
           ".ws-side label{display:block;padding:8px 10px;border-radius:4px;cursor:pointer;font-size:12px;color:#374151}",
           ".ws-tabs label{display:inline-block;padding:6px 12px;margin-right:4px;border-bottom:2px solid transparent;cursor:pointer;font-size:12.5px}",
           ".ws input{display:none}"]
    radios, side, panes = "", "", ""
    for i, w in enumerate(workshops):
        w = _dict(w)
        radios += f'<input type="radio" name="ws-uc" id="ws-uc-{i}"{" checked" if i == 0 else ""}>'
        side += f'<label for="ws-uc-{i}"><b>{_h(w.get("account"))}</b><br>{_h(w.get("name"))}</label>'
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
                  f'<div class="ws-sec ws-sa"><h3 style="margin:0 0 6px;">{_h(w.get("name"))}</h3>'
                  f'<p style="font-size:12.5px;">{_h(w.get("brief"))}</p><p style="font-size:12px;"><b>Proposed CoCo skills:</b> {skills}</p></div>'
                  f'<div class="ws-sec ws-sb"><h3 style="margin:0 0 6px;">Session 1 — Get started with CoCo</h3>{_session1(w.get("session1"))}</div>'
                  f'<div class="ws-sec ws-sc"><h3 style="margin:0 0 6px;">Session 2 — Co-build</h3>{_session2(w.get("session2"))}</div></div>')
    return (f'<style>{"".join(css)}</style>'
            f'<div style="font-size:14px;font-weight:800;color:#0f172a;margin:26px 0 8px;">Workshop Plans</div>'
            f'<div class="ws">{radios}<div class="ws-body" style="display:flex;gap:14px;border:1px solid #e5e7eb;border-radius:6px;padding:10px;">'
            f'<div class="ws-side" style="flex:0 0 220px;border-right:1px solid #f1f5f9;padding-right:8px;">{side}</div>'
            f'<div style="flex:1;min-width:0;">{panes}</div></div></div>')
