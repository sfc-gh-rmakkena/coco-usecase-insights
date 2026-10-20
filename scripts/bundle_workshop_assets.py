"""Regenerate utils/workshop/assets from the AI cookbook and the two source skills.

Usage: uv run --with pyyaml python scripts/bundle_workshop_assets.py
Env overrides: COOKBOOK_DIR (cookbook recipes dir), ACTIVATION_SKILL_DIR (activation planner skill dir).
"""
import glob
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "utils" / "workshop" / "assets"
COOKBOOK = Path(os.environ.get("COOKBOOK_DIR", "/Users/plakhanpal/Documents/git/cortex-ai-cookbook/recipes"))
ACTIVATION = Path(os.environ.get("ACTIVATION_SKILL_DIR",
                  "/Users/plakhanpal/Documents/git/cortexcode/coco-customer-activation-planner"))
IMPL_GLOB = os.path.expanduser(
    "~/.snowflake/cortex/stage_cache/*/skills/pse-uc-implementation-plan")
URL_RE = re.compile(r"https://(?:docs|quickstarts|www|developers)\.snowflake\.com[^\s)\"'<>`\]*]*")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if not COOKBOOK.is_dir():
        raise SystemExit(f"COOKBOOK_DIR not found: {COOKBOOK}")
    recipe_ymls = sorted(COOKBOOK.glob("*/*/recipe.yaml"))
    if not recipe_ymls:
        raise SystemExit(f"no recipes found under {COOKBOOK}")
    if not (ACTIVATION / "SKILL.md").is_file():
        raise SystemExit(f"activation SKILL.md not found in {ACTIVATION}")
    impl_dirs = sorted(glob.glob(IMPL_GLOB), key=os.path.getmtime)
    if not impl_dirs:
        raise SystemExit("pse-uc-implementation-plan not found in stage cache")
    impl = Path(impl_dirs[-1])

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "recipes").mkdir(parents=True)
    (OUT / "skills").mkdir()
    versions, index, links = {}, [], set()

    for yml in recipe_ymls:
        meta = yaml.safe_load(yml.read_text())
        rid = f"{yml.parent.parent.name}/{yml.parent.name}"
        readme = yml.parent / "README.md"
        if not readme.exists():
            print(f"warning: {rid} has no README.md")
        body = readme.read_text() if readme.exists() else ""
        sql_files = sorted(p.name for p in (yml.parent / "sql").glob("*.sql")) if (yml.parent / "sql").exists() else []
        (OUT / "recipes" / (rid.replace("/", "__") + ".md")).write_text(body)
        index.append({"id": rid, "title": meta.get("title", ""), "description": meta.get("description", ""),
                      "topics": meta.get("topics", []), "features": meta.get("features", []),
                      "stages": meta.get("stages", []), "estimated_time": meta.get("estimated_time", ""),
                      "sql_files": sql_files,
                      "related_skills": [s.get("name") for s in meta.get("related_skills", []) or []]})
        links.update(u.rstrip(".,;:") for u in URL_RE.findall(body))
        versions[f"recipe:{rid}"] = sha(yml) + ":" + (sha(readme) if readme.exists() else "")

    for name, src in [("coco-customer-activation-planner/SKILL.md", ACTIVATION / "SKILL.md"),
                      ("pse-uc-implementation-plan/SKILL.md", impl / "SKILL.md"),
                      ("pse-uc-implementation-plan/templates/report_template.html",
                       impl / "templates" / "report_template.html")]:
        dst = OUT / "skills" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        versions[f"skill:{name}"] = sha(src)
        links.update(u.rstrip(".,;:") for u in URL_RE.findall(src.read_text()))

    (OUT / "recipes_index.json").write_text(json.dumps(index, indent=1))
    (OUT / "link_allowlist.json").write_text(json.dumps(sorted(links), indent=1))
    (OUT / "skills" / "VERSIONS.json").write_text(json.dumps(versions, indent=1, sort_keys=True))
    print(f"recipes={len(index)} links={len(links)} skills=3")


if __name__ == "__main__":
    main()
