"""Q4 FY27 targets: APJ and EMEA RSI 75%, LATAM RSI 50%, GSI/NOAM 90%, on every page."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import utils  # noqa: E402
from utils import (  # noqa: E402
    APJ_EMEA_TARGET, GSI_NOAM_TARGET, LATAM_RSI_TARGET, TARGETS_TEXT,
    APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, LATAM_RSI_REGION_MAP, group_target_for,
)
from utils.verified_metrics import GROUP_TARGETS  # noqa: E402

PAGES = {name: (ROOT / "app_pages" / f"{name}.py").read_text()
         for name in ("overview", "okr_adoption", "executive_email",
                      "pse_email_hybrid", "pse_email_hybrid_rest")}


def test_target_values():
    assert (GSI_NOAM_TARGET, APJ_EMEA_TARGET, LATAM_RSI_TARGET) == (90, 75, 50)
    assert TARGETS_TEXT == "GSI/NOAM 90%, APJ/EMEA 75%, LATAM 50%"
    assert GROUP_TARGETS == {"GSI": 90, "NOAM": 90, "APJ": 75, "EMEA": 75, "LATAM": 50}


def test_old_shared_regional_target_is_gone():
    assert not hasattr(utils, "REGIONAL_RSI_TARGET")
    for name, src in PAGES.items():
        assert "REGIONAL_RSI_TARGET" not in src, name
        assert not re.search(r"APJ/EMEA/LATAM (goal|&#8805;|\{)", src), name


def test_every_apj_emea_partner_targets_75_and_latam_50():
    # Partners that are only APJ/EMEA RSIs get 75%; partners also in GSI or NOAM
    # (e.g. Slalom, Infosys, Deloitte) keep the higher target.
    single = lambda p: not set(utils.partner_groups(p)) - {utils.GROUP_APJ, utils.GROUP_EMEA, utils.GROUP_LATAM}
    for partner in list(APJ_RSI_REGION_MAP) + list(EMEA_RSI_REGION_MAP):
        if single(partner):
            assert group_target_for(partner) == 75, partner
    for partner in LATAM_RSI_REGION_MAP:
        if single(partner):
            assert group_target_for(partner) == 50, partner


def test_overview_gauges_titles_and_tables():
    src = PAGES["overview"]
    assert "_apj_coco,  APJ_EMEA_TARGET)" in src
    assert "_emea_coco, APJ_EMEA_TARGET)" in src
    assert "_latam_coco, LATAM_RSI_TARGET)" in src
    assert "APJ RSI CoCo Adoption ({APJ_EMEA_TARGET}% Target)" in src
    assert "EMEA RSI CoCo Adoption ({APJ_EMEA_TARGET}% Target)" in src
    assert "LATAM RSI CoCo Adoption ({LATAM_RSI_TARGET}% Target)" in src
    assert "APJ_TARGET = APJ_EMEA_TARGET" in src
    assert "EMEA_TARGET = APJ_EMEA_TARGET" in src
    assert "LATAM_TARGET = LATAM_RSI_TARGET" in src
    assert "50% Target" not in src


def test_okr_page_region_target():
    src = PAGES["okr_adoption"]
    block = src[src.index("# Auto-set target based on region"):src.index("_uniform_target")]
    ns = {"APJ_EMEA_TARGET": 75, "LATAM_RSI_TARGET": 50, "TARGET_PCT": 90}
    for region, want in (("APJ", 75), ("ANZ", 75), ("EMEA", 75), ("UK", 75),
                         ("LATAM", 50), ("All", 90), ("USMajors", 90)):
        ns["region"] = region
        exec(block, ns)
        assert ns["target"] == want, region


def test_exec_email_scorecards_and_text():
    src = PAGES["executive_email"]
    assert "'APJ RSI (APJ geo)',          APJ_EMEA_TARGET, 'APJ RSI')" in src
    assert "'EMEA RSI (EMEA geo)',        APJ_EMEA_TARGET, 'EMEA RSI')" in src
    assert "'LATAM RSI (LATAM geo)',      LATAM_RSI_TARGET, 'LATAM RSI')" in src
    assert "{APJ_EMEA_TARGET}% for APJ RSI and EMEA RSI, {LATAM_RSI_TARGET}% for LATAM RSI" in src
    assert "Partners Meeting 50% Adoption" not in src
    assert "Below 50% Target" not in src


def test_pse_peer_group_targets():
    for name in ("pse_email_hybrid", "pse_email_hybrid_rest"):
        src = PAGES[name]
        assert "from utils import GSI_NOAM_TARGET, APJ_EMEA_TARGET, LATAM_RSI_TARGET" in src, name
        assert 'region, APJ_EMEA_TARGET, f"{region} RSIs")' in src, name
        assert '"LATAM", LATAM_RSI_TARGET, "LATAM RSIs")' in src, name
        assert ", 50," not in src[src.index("def _peer_group_for"):][:1500], name
