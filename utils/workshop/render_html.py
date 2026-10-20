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
    out += '<h4 style="margin:14px 0 6px;">Implementation plan</h4>'
    if plan.get("problem_statement"):
        out += f'<p style="font-size:12.5px;">{_h(plan["problem_statement"])}</p>'
    if _list(plan.get("architecture")):
        out += "<b>Architecture</b><ul>" + "".join(f"<li>{_h(a)}</li>" for a in plan["architecture"]) + "</ul>"
    for i, s in enumerate(_list(plan.get("steps")), 1):
        s = _dict(s)
        out += (f'<div style="margin:8px 0;"><b>Step {i}: {_h(s.get("title"))}</b>'
                f'<div style="font-size:12px;">{_h(s.get("detail"))}</div>')
        out += (_md_block(s["sql"]) if s.get("sql") else "") + "</div>"
    if _list(plan.get("coco_prompts")):
        out += "<b>CoCo prompts</b>" + "".join(_md_block(p) for p in plan["coco_prompts"])
    if _list(plan.get("considerations")):
        out += "<b>Considerations</b><ul>" + "".join(f"<li>{_h(c)}</li>" for c in plan["considerations"]) + "</ul>"
    if _list(plan.get("docs")):
        out += "<b>Resources</b><ul>" + "".join(f"<li>{_doc_link(d)}</li>" for d in plan["docs"]) + "</ul>"
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
