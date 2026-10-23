"""Deterministic ASCII architecture diagram for the Session 2 plan (skill reference style).

Input is the structured plan["architecture"] dict:
  {"sources": [str], "layers": [{"name", "capability", "detail"}], "consumers": [str]}
Output is plain text (renderers escape it), every line <= MAX_WIDTH columns.
"""
import textwrap

MAX_WIDTH = 100
_BOX = 80  # inner width of the medallion boxes
_PAD = "        "
_MEDALLION = (("Bronze", "BRONZE", "raw landing tables"),
              ("Silver", "SILVER", "conformed, deduplicated entities"),
              ("Gold", "GOLD", "curated marts and aggregates"))
_CANON = ("ingestion", "bronze", "silver", "gold", "semantic", "consumption", "sharing", "governance")
# Unicode box-drawing -> ASCII, for fonts without those glyphs (PDF Courier).
_ASCII = str.maketrans({"│": "|", "▼": "v", "►": ">", "├": "+", "└": "`", "┌": "+", "┐": "+",
                        "┘": "+", "─": "-", "═": "=", "…": "~"})


def _s(v):
    return " ".join(str(v or "").split())


def _cut(line, n=MAX_WIDTH):
    return line if len(line) <= n else line[:n - 1] + "…"


def _wrap(line, indent, n=MAX_WIDTH):
    """Wrap a long line instead of truncating; continuation lines start with `indent`."""
    if len(line) <= n:
        return [line]
    lead = len(line) - len(line.lstrip())
    first, rest = line[:lead], line[lead:]
    out = textwrap.wrap(rest, n - lead, break_on_hyphens=False) or [""]
    head = first + out[0]
    tail = textwrap.wrap(" ".join(out[1:]), n - len(indent), break_on_hyphens=False)
    return [head] + [indent + t for t in tail]


def _layers(arch):
    out = []
    for l in (arch or {}).get("layers") or []:
        if isinstance(l, dict) and (_s(l.get("name")) or _s(l.get("capability"))):
            out.append({k: _s(l.get(k)) for k in ("name", "capability", "detail")})
    return out


def _by(layers, name):
    return [l for l in layers if l["name"].lower() == name]


def _label(ls, default=""):
    caps = []
    for l in ls:
        if l["capability"] and l["capability"] not in caps:
            caps.append(l["capability"])
    return " + ".join(caps) or default


def _box(title, text):
    head = f" {title:<7} "
    pad = " " * len(head)
    body = textwrap.wrap(text, _BOX - len(head) - 1, break_on_hyphens=False) or [""]
    rows = [f"│{(head if i == 0 else pad) + b:<{_BOX}}│" for i, b in enumerate(body)]
    return [f"┌{'─' * _BOX}┐", *rows, f"└{'─' * _BOX}┘"]


def _arrow(label):
    if not label:
        return [f"{_PAD}│", f"{_PAD}▼"]
    return [*_wrap(f"{_PAD}│  {label}", f"{_PAD}│  "), f"{_PAD}▼"]


def layer_bullets(arch) -> list:
    """Architecture-layer bullet strings derived from the structured layers."""
    return [" — ".join(x for x in (f"{l['name']}: {l['capability']}".strip(": "), l["detail"]) if x)
            for l in _layers(arch)]


def render(arch) -> str:
    """ASCII flow: sources -> ingestion -> BRONZE -> SILVER -> GOLD -> semantic -> fan-out; governance band."""
    arch = arch if isinstance(arch, dict) else {}
    layers = _layers(arch)
    sources = [_s(x) for x in arch.get("sources") or [] if _s(x)] or ["Source systems"]
    lines = [w for x in sources for w in _wrap(x, "  ")]
    ing = _by(layers, "ingestion")
    ing_detail = "; ".join(l["detail"] for l in ing if l["detail"])
    lines += _arrow(_label(ing, "Ingestion") + (f"  ({ing_detail})" if ing_detail else ""))
    extra = [l for l in layers if l["name"].lower() not in _CANON]
    for i, (name, title, default) in enumerate(_MEDALLION):
        ls = _by(layers, name.lower())
        if i:
            lines += _arrow(_label(ls, "Dynamic Tables"))
        detail = "; ".join(l["detail"] for l in ls if l["detail"]) or default
        if i == 0 and _label(ls):
            detail = f"{_label(ls)} - {detail}"
        lines += _box(title, detail)
    for l in extra:
        lines.extend(_wrap(f"{_PAD}├── {l['name']}: {l['capability']}" + (f" ({l['detail']})" if l["detail"] else ""), f"{_PAD}│   "))
    sem = _by(layers, "semantic")
    if sem:
        lines += _arrow(_label(sem))
        lines += _box("SEMANTIC", "; ".join(l["detail"] for l in sem if l["detail"]) or "business metrics and definitions")
    fan = [f"{l['capability']}" + (f" ({l['detail']})" if l["detail"] else "")
           for l in _by(layers, "consumption") + _by(layers, "sharing")]
    fan += [_s(c) for c in arch.get("consumers") or [] if _s(c)]
    if fan:
        lines.append(f"{_PAD}│")
        for j, f in enumerate(fan):
            last = j == len(fan) - 1
            lines.extend(_wrap(f"{_PAD}{'└' if last else '├'}──► {f}", f"{_PAD}{' ' if last else '│'}    "))
    gov = _by(layers, "governance")
    if gov:
        lines.append("")
        lines.append("═" * (_BOX + 2))
        for l in gov:
            lines.extend(_wrap(f" GOVERNANCE  {l['capability']}" + (f" - {l['detail']}" if l["detail"] else ""), " " * 13))
        lines.append("═" * (_BOX + 2))
    return "\n".join(l.rstrip() for l in lines)


def to_ascii(text) -> str:
    return str(text or "").translate(_ASCII)
