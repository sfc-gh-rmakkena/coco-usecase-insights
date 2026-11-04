import functools
import hashlib
import json
from pathlib import Path

_DIR = Path(__file__).parent
_ASSETS = _DIR / "assets"


@functools.lru_cache(maxsize=None)
def recipes_index() -> list:
    return json.loads((_ASSETS / "recipes_index.json").read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=None)
def recipe_body(recipe_id: str) -> str:
    p = _ASSETS / "recipes" / (recipe_id.replace("/", "__") + ".md")
    return p.read_text(encoding="utf-8") if p.exists() else ""


def recipe_meta(recipe_id: str) -> dict:
    return next((r for r in recipes_index() if r["id"] == recipe_id), {})


@functools.lru_cache(maxsize=None)
def skill_text(rel_path: str) -> str:
    return (_ASSETS / "skills" / rel_path).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=None)
def override_text() -> str:
    return (_DIR / "skill_override.md").read_text(encoding="utf-8")


@functools.lru_cache(maxsize=None)
def link_allowlist() -> frozenset:
    links = set(json.loads((_ASSETS / "link_allowlist.json").read_text(encoding="utf-8")))
    g = _ASSETS / "grounding.json"
    if g.exists():
        links.update(grounding_links(json.loads(g.read_text(encoding="utf-8"))))
    return frozenset(links)


def grounding_links(grounding: dict) -> set:
    out = set()
    for v in grounding.values():
        for kind in ("docs", "quickstarts"):
            out.update(d["url"] for d in v.get(kind, []) if "github.com" not in d["url"])
        out.update(s["source_url"] for s in v.get("sql_snippets", []))
    return out


@functools.lru_cache(maxsize=None)
def asset_version() -> str:
    h = hashlib.sha256((_ASSETS / "skills" / "VERSIONS.json").read_bytes())
    h.update(override_text().encode())
    h.update(b"s2-schema:no-status-no-github-no-recipe-v5-ctx-pack")  # bump when the Session 2 JSON schema changes
    # recipe_units.json carries the per-guide content digests, so any guide change re-keys the cache.
    for name in ("grounding.json", "vendor_terms.json", "locations.json", "first_names.json",
                 "recipe_units.json"):
        if (_ASSETS / name).exists():
            h.update((_ASSETS / name).read_bytes())
    return h.hexdigest()[:16]
