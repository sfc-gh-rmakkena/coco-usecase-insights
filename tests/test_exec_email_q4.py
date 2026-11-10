"""Executive Email set up for the current OKR quarter (Q4 FY27): dates, weekly tables,
targets, partner rosters and counts. Runs the page's real module-level setup code
(partner lists, tile keys, counts, target lookup) with Streamlit mocked out."""
import re
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import utils  # noqa: E402
import utils.queries as Q  # noqa: E402
from utils import APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP  # noqa: E402

PAGE = ROOT / "app_pages" / "executive_email.py"
SRC = PAGE.read_text()


@pytest.fixture(scope="module")
def email_ns():
    """Execute the page's setup block: imports through the roster counts."""
    end = SRC.index("_GROUP_COUNT_STR = ")
    end = SRC.index("\n", end) + 1
    # ...plus the per-tile target helper defined just after it
    tgt_start = SRC.index("_HEATMAP_GSI_KEYS")
    tgt_end = SRC.index("\ndef _fmt_tokens")
    code = SRC[:end] + "\n" + SRC[tgt_start:tgt_end]
    ns = {"__name__": "email_setup"}
    with mock.patch.dict(sys.modules, {"streamlit": mock.MagicMock(),
                                       "streamlit.components": mock.MagicMock(),
                                       "streamlit.components.v1": mock.MagicMock()}):
        exec(compile(code, str(PAGE), "exec"), ns)
    return ns


# --- Quarter: Q4 FY27 everywhere -------------------------------------------

def test_quarter_settings_are_q4():
    assert (utils.OKR_QUARTER, utils.OKR_QUARTER_LABEL) == ("Q4", "Q4 FY27")
    assert (utils.OKR_Q_START, utils.OKR_Q_END) == ("2026-11-01", "2027-01-31")


def test_email_uses_quarter_settings_not_q3_dates():
    assert "Q3_START = OKR_Q_START" in SRC and "Q3_END = OKR_Q_END" in SRC
    assert "get_adoption_overview(conn, OKR_Q_START, OKR_Q_END" in SRC
    for stale in ("'2026-08-01'", "'2026-10-31'", "_date(2026, 10, 31)"):
        assert stale not in SRC, stale


def test_email_text_has_no_q3_wording():
    # Only one historical code comment may still say Q3.
    lines = [l for l in SRC.splitlines() if re.search(r"\bQ3\b", l)
             and not re.search(r"Q3_START|Q3_END|_q3_end", l)]
    assert all(l.strip().startswith("#") for l in lines), lines
    for wording in ("Q3 FY27", "Aug–Oct 2026", "Aug-Oct 2026", "Weeks remaining in Q3",
                    "No Q3 Activity", "| Q3 Tokens |", "before Q3 ends"):
        assert wording not in SRC, wording
    assert 'subject_text = f"Cortex Code {OKR_QUARTER_LABEL} Partner Intelligence' in SRC


def test_weekly_tables_are_q4():
    assert Q._SNAPSHOT_TABLE.endswith("IS_COCO_FINAL_WEEKLY_SNAPSHOT_Q4")
    assert Q._OKR_TARGET_TABLE.endswith("COCO_OKR_TARGET_WEEKLY_Q4")
    assert "snapshot_table = SNAPSHOT_TABLE_Q4" in SRC
    assert "IS_COCO_FINAL_WEEKLY_SNAPSHOT_Q3\"" not in SRC


# --- New partner lists are in the email ------------------------------------

def test_every_apj_and_emea_partner_has_a_tile(email_ns):
    apj_labels = {label for label, _ in email_ns["_HEATMAP_APJ"]}
    emea_labels = {label for label, _ in email_ns["_HEATMAP_EMEA"]}
    assert apj_labels == {v[0] for v in APJ_RSI_REGION_MAP.values()}
    assert emea_labels == {v[0] for v in EMEA_RSI_REGION_MAP.values()}
    assert len(apj_labels) == 26 and len(emea_labels) == 20


def test_removed_partners_are_gone(email_ns):
    names = " ".join(f"{l} {k}" for l, k in email_ns["HEATMAP_PARTNERS"])
    for gone in ("Kubrick", "Icon Analytics"):
        assert gone not in names and gone not in SRC


def test_multigroup_partners_get_one_tile_per_group(email_ns):
    keys = {k for _, k in email_ns["HEATMAP_PARTNERS"]}
    assert {"Slalom, LLC.", "Slalom, LLC. | APJ", "Slalom, LLC. | EMEA"} <= keys
    assert {"Billigence APAC", "Billigence APAC | EMEA"} <= keys
    assert {"Aimpoint Digital", "Aimpoint Digital | EMEA"} <= keys


# --- Partner counts come from the rosters ----------------------------------

def test_group_counts_match_rosters(email_ns):
    counts = email_ns["_GROUP_PARTNER_COUNTS"]
    assert counts["GSI"] == 6 and counts["APJ RSI"] == 26
    assert counts["EMEA RSI"] == 20 and counts["LATAM RSI"] == 17   # Triggo's two names = one
    assert email_ns["_PARTNER_SLOTS"] == sum(counts.values())
    # Multi-group partners are counted once in the unique total: Slalom x2, Billigence,
    # Vivanti, Aimpoint, Infosys, plus Deloitte and Accenture (GSI + LATAM).
    assert email_ns["_UNIQUE_MANAGED"] == email_ns["_PARTNER_SLOTS"] - 8


def test_no_stale_hardcoded_counts():
    for stale in ("exactly 44", "across 49 managed", "Total Partners in Scope: 49", "APJ RSI=5",
                  "EMEA RSI=4", "/44", "(6, 32, 5, 4)", "32 NOAM RSIs", "_CANONICAL_TOTAL = 49",
                  "save_okr_target_count(conn, partners_meeting_75, 44)"):
        assert stale not in SRC, stale
    assert "_grp_sizes = dict(_GROUP_PARTNER_COUNTS)" in SRC
    assert "_CANONICAL_TOTAL = _PARTNER_SLOTS" in SRC


# --- Q4 targets (90% / 75% / 50%) ------------------------------------------------

def test_heatmap_targets(email_ns):
    target = email_ns["_partner_target"]
    for _, key in email_ns["_HEATMAP_GSI"] + email_ns["_HEATMAP_NOAM"]:
        assert target(key) == 90, key
    for _, key in email_ns["_HEATMAP_APJ"] + email_ns["_HEATMAP_EMEA"]:
        assert target(key) == 75, key
    for _, key in email_ns["_HEATMAP_LATAM"]:
        assert target(key) == 50, key


def test_group_goal_counts_use_q4_targets():
    assert "_full_partner_summary['_GROUP'].map(\n        GROUP_TARGET_PCT\n    )" in SRC
    assert "_grp_targets = dict(GROUP_TARGET_PCT)" in SRC
    assert "'GSI (Global, all regions)', GSI_NOAM_TARGET" in SRC
    assert "'NOAM RSI (NoAM only)',       GSI_NOAM_TARGET" in SRC


# --- Numbers use the same scoping as Overview / OKR ------------------------

def test_stage_sql_scopes_regional_rsis_by_region():
    assert "OR {region_map_sql(APJ_RSI_REGION_MAP)}" in SRC
    assert "OR {region_map_sql(EMEA_RSI_REGION_MAP)}" in SRC
    assert "REGION_NAME IN ('CentralEMEA','SouthEMEA','UK')" not in SRC


def test_scorecards_and_tiles_are_per_group():
    assert "_group_view[_group_view['_GROUP'] == group_tag]" in SRC
    assert "_tile_key_for(p, g) for p, g in zip(_group_view['PARTNER_NAME'], _group_view['_GROUP'])" in SRC


def test_heatmap_tiles_match_scorecard_rosters(email_ns):
    """Every scorecard partner has a heatmap tile (SDK Tek was missing), per group."""
    from utils import PARTNER_ALIASES
    aliases = {'Ernst & Young (EY)': 'EY', 'IBM Consulting': 'IBM', 'Kipi.ai': 'kipi.ai',
               'LTI Mindtree': 'LTM', 'ZEAL CORPORATION': 'ZEAL Corporation'}
    noam_roster = {aliases.get(p, p) for p in PARTNER_ALIASES['--- NOAM RSIs ---']
                   if not p.startswith('---')}
    noam_tiles = {k for _, k in email_ns["_HEATMAP_NOAM"]}
    assert noam_tiles == noam_roster
    assert email_ns["_GROUP_PARTNER_COUNTS"]["NOAM RSI"] == len(noam_roster)


def test_unique_partner_count_matches_alias_merged_roster(email_ns):
    aliases = {'Ernst & Young (EY)': 'EY', 'IBM Consulting': 'IBM', 'Kipi.ai': 'kipi.ai',
               'LTI Mindtree': 'LTM', 'ZEAL CORPORATION': 'ZEAL Corporation',
               'Triggo.ai': 'TRIGGO.AI TECNOLOGIA E INTELIGENCIA DE DADOS LTDA.'}
    merged = {aliases.get(p, p) for p in email_ns["MANAGED_PARTNERS"]}
    assert email_ns["_UNIQUE_MANAGED"] == len(merged)


def test_inactive_partners_ignore_alias_spellings():
    block = SRC[SRC.index("_ACTIVE_ALIASES = {"):SRC.index("managed_inactive_partners = len(managed_inactive_names)")]
    assert "_ACTIVE_ALIASES.get(p, p) for p in managed_bulk_conf['PARTNER_NAME']" in block
    assert "len(MANAGED_PARTNERS) - managed_total_partners" not in SRC
