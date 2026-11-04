"""Scope a simple stylesheet under one container selector so it cannot leak into the host page.

Handles the report template's rule set: comments, plain rules, comma lists, :root/html/body/*,
and @media blocks (recursively). Other at-rules (@font-face, @keyframes, @import) are dropped.
"""
import re

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_ROOTS = (":root", "html", "body")


def _sel(sel, scope):
    sel = sel.strip()
    if not sel:
        return ""
    if sel in _ROOTS:
        return scope
    for r in _ROOTS:
        if sel.startswith(r + " ") or sel.startswith(r + ">"):
            return scope + sel[len(r):]
    return f"{scope} {sel}"


def _blocks(css):
    """Yield (prelude, body) for each top-level block, matching nested braces."""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            return
        depth, k = 1, j + 1
        while k < n and depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        yield css[i:j].strip(), css[j + 1:k - 1]
        i = k


def prefix_css(css, scope) -> str:
    out = []
    for pre, body in _blocks(_COMMENT.sub("", css or "")):
        if pre.startswith("@media"):
            out.append(f"{pre}{{{prefix_css(body, scope)}}}")
        elif pre.startswith("@"):
            continue
        else:
            sels = ",".join(s for s in (_sel(x, scope) for x in pre.split(",")) if s)
            decl = " ".join(body.split())
            if sels:
                out.append(f"{sels}{{{decl}}}")
    return "".join(out)


def selectors(css) -> list:
    """All rule selectors (inside @media too); used by tests."""
    out = []
    for pre, body in _blocks(_COMMENT.sub("", css or "")):
        if pre.startswith("@media"):
            out += selectors(body)
        elif not pre.startswith("@"):
            out += [s.strip() for s in pre.split(",") if s.strip()]
    return out
