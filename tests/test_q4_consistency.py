"""Q4 consistency fixes: group-scoped section cards, per-partner OKR targets,
group-header selection = managed scope, and the Q4 weekly snapshot / forecast."""
import ast
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import (  # noqa: E402
    GROUP_GSI, GROUP_NOAM, GROUP_APJ, GROUP_EMEA, PARTNER_RENAME_MAP,
    add_managed_group, group_target_for,
)
import utils.queries as Q  # noqa: E402

OVERVIEW = (ROOT / "app_pages" / "overview.py").read_text()
OKR = (ROOT / "app_pages" / "okr_adoption.py").read_text()


# --- 1. Overview section cards count only their own group's rows -------------

def test_section_card_filters_by_group():
    fn = OVERVIEW[OVERVIEW.index("def _render_partner_section"):][:6000]
    assert "managed_group(p, t, r) == group" in fn


def test_gsi_and_noam_sections_pass_their_group():
    gsi = OVERVIEW[OVERVIEW.index("_render_partner_section(_gsi_base"):][:300]
    noam = OVERVIEW[OVERVIEW.index("_render_partner_section(_noam_base"):][:300]
    assert "group=GROUP_GSI" in gsi
    assert "group=GROUP_NOAM" in noam


def test_noam_card_excludes_multigroup_rows_outside_noam():
    """The card's CoCo numerator must equal the gauge's: Slalom APJ/EMEA rows drop out."""
    rows = pd.DataFrame([
        ('Slalom, LLC.', 'USMajors', 'Northeast', True),
        ('Slalom, LLC.', 'APJ', 'ANZ', True),
        ('Slalom, LLC.', 'EMEA', 'UK', True),
        ('Aimpoint Digital', 'EMEA', 'UK', True),
        ('phData, Inc.', 'USMajors', 'West', False),
    ], columns=['PARTNER_NAME', 'THEATER_NAME', 'REGION_NAME', 'IS_COCO_FINAL'])
    noam = add_managed_group(rows).query("_GROUP == @GROUP_NOAM")
    assert len(noam) == 2 and int(noam['IS_COCO_FINAL'].sum()) == 1


# --- 2. OKR page judges each partner against its own group target ------------

def test_group_target_for():
    assert group_target_for('Accenture') == 90
    assert group_target_for('phData, Inc.') == 90
    assert group_target_for('Slalom, LLC.') == 90          # first group: NOAM
    assert group_target_for('Billigence APAC') == 50        # APJ and EMEA
    assert group_target_for('Devoteam') == 50
    assert group_target_for('NTT DATA Group Corporation') == 50
    assert group_target_for('Viewnear - Partner') == 50
    assert group_target_for('Not A Partner') is None


def test_group_target_for_display_names():
    display = {v for k, v in PARTNER_RENAME_MAP.items() if group_target_for(k)}
    for name in display:
        assert group_target_for(name, PARTNER_RENAME_MAP) is not None, name


def test_okr_meets_target_uses_per_partner_target():
    assert "summary['TARGET_PCT'] = summary['PARTNER_NAME'].map(_partner_target)" in OKR
    assert "summary['MEETS_TARGET'] = summary['COCO_PCT'] >= summary['TARGET_PCT']" in OKR
    assert "summary['MEETS_TARGET'] = summary['COCO_PCT'] >= target\n" not in OKR
    assert "_p_target = _partner_target(selected_partner)" in OKR


# --- 3. Group-header selection uses the managed geo scoping -----------------

def _default_managed(selected):
    src = OKR[OKR.index("_using_default_managed = ("):]
    src = src[:src.index("selected_partners))") + len("selected_partners))")]
    ns = {"selected_partners": selected}
    exec(src, ns)
    return ns["_using_default_managed"]


def test_header_only_selection_is_managed_scope():
    assert _default_managed([]) is True
    assert _default_managed(['--- GSIs ---', '--- NOAM RSIs ---', '--- APJ RSIs ---',
                             '--- EMEA RSIs ---', '--- LATAM RSIs ---']) is True
    assert _default_managed(['Slalom, LLC.']) is False
    assert _default_managed(['--- GSIs ---', 'Slalom, LLC.']) is False


# --- 4. Q4 snapshot and forecast -------------------------------------------

class _FakeConn:
    def __init__(self, existing=0):
        self.existing, self.sql, self.ttls = existing, [], []

    def query(self, sql, ttl=None):
        self.sql.append(sql)
        self.ttls.append(ttl)
        return pd.DataFrame([{'CNT': self.existing}])


def _bc():
    df = pd.DataFrame([
        ('Slalom, LLC.', 'USMajors', 'Northeast', True, 1, 100.0),
        ('Slalom, LLC.', 'APJ', 'ANZ', False, 2, 50.0),
        ('Slalom, LLC.', 'EMEA', 'UK', True, 3, 10.0),
        ('Accenture', 'EMEA', 'UK', True, 4, 5.0),
    ], columns=['PARTNER_NAME', 'THEATER_NAME', 'REGION_NAME', 'IS_COCO_FINAL',
                'USE_CASE_ID', 'USE_CASE_EACV'])
    return add_managed_group(df)


def test_q4_snapshot_splits_multigroup_partner_by_region():
    conn = _FakeConn()
    assert Q.save_coco_final_snapshot(conn, _bc(), table=Q.SNAPSHOT_TABLE_Q4) is True
    insert = conn.sql[-1]
    assert Q.SNAPSHOT_TABLE_Q4 in insert
    assert "'Slalom, LLC.', 1, 1, 100.0, 100.0, 100.0, 'NoAM'" in insert
    assert "'Slalom, LLC.', 1, 0, 0.0, 50.0, 0.0, 'APJ'" in insert
    assert "'Slalom, LLC.', 1, 1, 100.0, 10.0, 10.0, 'EMEA'" in insert
    assert "'Accenture', 1, 1, 100.0, 5.0, 5.0, 'Global'" in insert


def test_default_snapshot_table_is_q4_and_q3_not_written():
    conn = _FakeConn()
    Q.save_coco_final_snapshot(conn, _bc())        # Executive Email's call (no table arg)
    insert = conn.sql[-1]
    assert "IS_COCO_FINAL_WEEKLY_SNAPSHOT_Q4" in insert
    assert "SNAPSHOT_Q3" not in " ".join(conn.sql)
    assert insert.count("'Slalom, LLC.'") == 3      # one row per group: NoAM, APJ, EMEA


def test_snapshot_check_and_insert_bypass_cache():
    """A cached 'not saved yet' count made a later run save the same week again."""
    conn = _FakeConn()
    Q.save_coco_final_snapshot(conn, _bc())
    assert conn.ttls == [0, 0]
    assert "WHERE NOT EXISTS (SELECT 1 FROM" in conn.sql[-1]


def test_snapshot_is_idempotent_per_week():
    conn = _FakeConn(existing=5)
    assert Q.save_coco_final_snapshot(conn, _bc(), table=Q.SNAPSHOT_TABLE_Q4) is False
    assert not any("INSERT" in s for s in conn.sql)


def test_forecast_reads_q4_and_needs_two_weeks():
    trend = OVERVIEW[OVERVIEW.index("def _get_gsi_noam_snapshot_trend"):][:1200]
    assert "snapshot_table = SNAPSHOT_TABLE_Q4" in trend
    assert "IS_COCO_FINAL_WEEKLY_SNAPSHOT_Q3" not in trend
    assert "if _trend_weeks >= 2:" in OVERVIEW


def test_executive_email_is_the_only_snapshot_writer():
    """Two writers loading in the same week saved the week twice; keep one."""
    pages = {p.name: p.read_text() for p in (ROOT / "app_pages").glob("*.py")}
    writers = sorted(n for n, src in pages.items() if "save_coco_final_snapshot(" in src)
    assert writers == ["executive_email.py"]


def test_forecast_projection_math():
    fn_src = OVERVIEW[OVERVIEW.index("def _forecast_snapshot_group"):]
    fn_src = fn_src[:fn_src.index("\n# NoAM theater list")]
    ns = {"pd": pd, "GSI_NOAM_TARGET": 90}
    exec(fn_src, ns)
    rows = pd.DataFrame({
        'WEEK_START': ['2026-11-02', '2026-11-09', '2026-11-16'],
        'TOTAL_UCS': [100, 110, 120], 'COCO_UCS': [60, 70, 80], 'COCO_PCT': [60.0, 63.6, 66.7],
    })
    fc = ns["_forecast_snapshot_group"](rows, '2027-01-31', 90.0)
    assert fc['current_coco'] == 80 and fc['weeks_left'] == 11   # Nov 16 -> Jan 31, rounded up
    assert fc['avg_coco_delta'] == 10 and fc['avg_total_delta'] == 10
    assert fc['projected_pct'] == round(190 * 100 / 230, 1)    # 80+10*11 of 120+10*11
    assert fc['status'] == 'Needs acceleration'


def test_pages_compile():
    for page in ("overview.py", "okr_adoption.py", "executive_email.py"):
        ast.parse((ROOT / "app_pages" / page).read_text())
