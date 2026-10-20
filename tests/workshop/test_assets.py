from utils.workshop import assets


def test_recipes_index_loaded():
    idx = assets.recipes_index()
    assert len(idx) == 23
    assert {"id", "title", "description", "topics", "features"} <= set(idx[0])


def test_recipe_body_and_skills_present():
    rid = assets.recipes_index()[0]["id"]
    assert isinstance(assets.recipe_body(rid), str)
    assert "Red Light" in assets.skill_text("pse-uc-implementation-plan/SKILL.md")
    assert "APP OVERRIDE" in assets.override_text()


def test_asset_version_stable():
    assert assets.asset_version() == assets.asset_version()
    assert len(assets.asset_version()) == 16
