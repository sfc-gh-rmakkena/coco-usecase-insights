import functools
import hashlib
import json
from pathlib import Path

_DIR = Path(__file__).parent
_ASSETS = _DIR / "assets"


@functools.lru_cache(maxsize=None)
def recipes_index() -> list:
    return json.loads((_ASSETS / "recipes_index.json").read_text())


@functools.lru_cache(maxsize=None)
def recipe_body(recipe_id: str) -> str:
    p = _ASSETS / "recipes" / (recipe_id.replace("/", "__") + ".md")
    return p.read_text() if p.exists() else ""


def recipe_meta(recipe_id: str) -> dict:
    return next((r for r in recipes_index() if r["id"] == recipe_id), {})


@functools.lru_cache(maxsize=None)
def skill_text(rel_path: str) -> str:
    return (_ASSETS / "skills" / rel_path).read_text()


@functools.lru_cache(maxsize=None)
def override_text() -> str:
    return (_DIR / "skill_override.md").read_text()


@functools.lru_cache(maxsize=None)
def link_allowlist() -> frozenset:
    return frozenset(json.loads((_ASSETS / "link_allowlist.json").read_text()))


@functools.lru_cache(maxsize=None)
def asset_version() -> str:
    h = hashlib.sha256((_ASSETS / "skills" / "VERSIONS.json").read_bytes())
    h.update(override_text().encode())
    return h.hexdigest()[:16]
