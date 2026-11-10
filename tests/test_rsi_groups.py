"""APJ/EMEA RSI rosters and row-level group assignment (utils.managed_group).

Several partners belong to more than one group (Slalom: NOAM, APJ, EMEA; Infosys:
NOAM, APJ; Aimpoint: NOAM, EMEA; Billigence, Vivanti: APJ, EMEA). Each of their use
cases must land in exactly one group by geography, so group totals add up to the
overall managed total.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import (  # noqa: E402
    APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, PARTNER_ALIASES,
    GROUP_NOAM, GROUP_APJ, GROUP_EMEA, GROUP_GSI,
    managed_group, add_managed_group, partner_groups, scope_rsi_rows, region_map_sql,
)

APJ_SHEET = {  # PARTNER_NAME_IN_DB -> REGION, from the APJ partner sheet
    'NTT DATA Group Corporation': 'ASEAN', 'Altis Global Limited': 'ANZ', 'Mantel': 'ANZ',
    'Slalom, LLC.': 'ANZ', 'Vivanti USA LLC': 'ANZ',
    'Bitek Information & Communication Inc.': 'Korea', 'DATUM STUDIO Co. Ltd.': 'Japan',
    'Billigence APAC': 'ANZ', 'MegazoneCloud Corporation': 'Korea',
    'NS Solutions Corporation': 'Japan', 'InterWorks, Inc': 'ANZ', 'ZEAL Corporation': 'Japan',
    'ITOCHU Techno-Solutions Corporation': 'Japan', 'Hitachi Solutions, Ltd.': 'Japan',
    'Intage Technosphere inc.': 'Japan', 'iZeno Pte Ltd': 'ASEAN',
    'SHI Solutions India Private Limited': 'India', 'PROLIM Global Corporation': 'India',
    'SoftwareONE Pte Ltd (Singapore)': 'ASEAN', 'Infosys': 'ANZ', 'Quantiphi Inc.': 'India',
    'ITGN OPS CO PTY LTD.': 'ANZ', 'Infinite Lambda Limited': 'ASEAN',
    'NEC Corporation': 'Japan', 'Nomura Research Institute, Ltd.': 'Japan',
    'Classmethod': 'Japan',
}

EMEA_SHEET = {  # PARTNER_NAME_IN_DB -> REGION_NAME, from the EMEA partner sheet
    'Aimpoint Digital': 'UK', 'Lumilinks Group Ltd': 'UK', 'Slalom, LLC.': 'UK',
    'SDG Consulting (EMEA) Consolidated': 'SouthEMEA', 'CIVICA SOFTWARE, S.L.': 'SouthEMEA',
    'Devoteam': 'SouthEMEA', 'KPC (Key Performance Consulting)': 'SouthEMEA',
    'Twoday Oy': 'NorthEMEA', 'Recordly Oy': 'NorthEMEA', 'Solita Oy': 'NorthEMEA',
    'Navara Consulting Services BV': 'NorthEMEA', 'IN516HT TECHNOLOGIES CO. L.L.C': 'META',
    'Datalab Solutions (Pty) Ltd': 'META', '8Insights Consulting LLC': 'META',
    'INFOMOTION GMBH': 'CentralEMEA', 'Billigence APAC': 'CentralEMEA',
    'b.telligent Group': 'CentralEMEA', 'synvert GmbH': 'CentralEMEA',
    'CACI Limited': 'UK', 'Vivanti USA LLC': 'UK',
}

COLS = ['PARTNER_NAME', 'THEATER_NAME', 'REGION_NAME']


def test_apj_roster_matches_sheet():
    assert len(APJ_SHEET) == 26
    for name, region in APJ_SHEET.items():
        assert APJ_RSI_REGION_MAP[name][1] == region, name
    # Only extra key is the upper-case spelling of ZEAL that exists in the data.
    assert set(APJ_RSI_REGION_MAP) - set(APJ_SHEET) == {'ZEAL CORPORATION'}
    assert set(PARTNER_ALIASES['--- APJ RSIs ---']) == set(APJ_RSI_REGION_MAP)


def test_emea_roster_matches_sheet():
    assert len(EMEA_SHEET) == 20
    assert {k: v[1] for k, v in EMEA_RSI_REGION_MAP.items()} == EMEA_SHEET
    assert set(PARTNER_ALIASES['--- EMEA RSIs ---']) == set(EMEA_RSI_REGION_MAP)
    assert len({v[0] for v in EMEA_RSI_REGION_MAP.values()}) == 20  # unique labels


def test_regions_are_valid():
    assert {r for _, r in APJ_RSI_REGION_MAP.values()} <= {'ANZ', 'Japan', 'ASEAN', 'Korea', 'India'}
    assert {r for _, r in EMEA_RSI_REGION_MAP.values()} <= {
        'UK', 'SouthEMEA', 'NorthEMEA', 'META', 'CentralEMEA'}


def test_multi_group_partners():
    noam = set(PARTNER_ALIASES['--- NOAM RSIs ---'])
    assert noam & set(APJ_RSI_REGION_MAP) == {'Slalom, LLC.', 'Infosys'}
    assert noam & set(EMEA_RSI_REGION_MAP) == {'Slalom, LLC.', 'Aimpoint Digital'}
    assert set(APJ_RSI_REGION_MAP) & set(EMEA_RSI_REGION_MAP) == {
        'Slalom, LLC.', 'Billigence APAC', 'Vivanti USA LLC'}
    assert partner_groups('Slalom, LLC.') == [GROUP_NOAM, GROUP_APJ, GROUP_EMEA]
    assert partner_groups('Billigence APAC') == [GROUP_APJ, GROUP_EMEA]


@pytest.mark.parametrize("partner,theater,region,expected", [
    ('Slalom, LLC.', 'USMajors', 'Northeast', GROUP_NOAM),
    ('Slalom, LLC.', 'APJ', 'ANZ', GROUP_APJ),
    ('Slalom, LLC.', 'APJ', 'Japan', None),
    ('Slalom, LLC.', 'EMEA', 'UK', GROUP_EMEA),
    ('Slalom, LLC.', 'EMEA', 'CentralEMEA', None),
    ('Infosys', 'AMSExpansion', 'West', GROUP_NOAM),
    ('Infosys', 'APJ', 'ANZ', GROUP_APJ),
    ('Aimpoint Digital', 'USMajors', 'Northeast', GROUP_NOAM),
    ('Aimpoint Digital', 'EMEA', 'UK', GROUP_EMEA),
    ('Aimpoint Digital', 'EMEA', 'EMEACommercial', None),
    ('Billigence APAC', 'APJ', 'ANZ', GROUP_APJ),
    ('Billigence APAC', 'EMEA', 'CentralEMEA', GROUP_EMEA),
    ('Billigence APAC', 'EMEA', 'UK', None),
    ('Vivanti USA LLC', 'EMEA', 'UK', GROUP_EMEA),
    ('Devoteam', 'EMEA', 'SouthEMEA', GROUP_EMEA),
    ('Devoteam', 'EMEA', 'NorthEMEA', None),
    ('NTT DATA Group Corporation', 'APJ', 'ASEAN', GROUP_APJ),
    ('NTT DATA Group Corporation', 'APJ', 'Japan', None),
    ('Accenture', 'APJ', 'Japan', GROUP_GSI),
    ('Mantel', 'AMSExpansion', 'West', None),
])
def test_managed_group(partner, theater, region, expected):
    assert managed_group(partner, theater, region) == expected


def test_group_totals_do_not_double_count():
    rows = pd.DataFrame([
        ('Slalom, LLC.', 'USMajors', 'Northeast'), ('Slalom, LLC.', 'APJ', 'ANZ'),
        ('Slalom, LLC.', 'APJ', 'ANZ'), ('Slalom, LLC.', 'APJ', 'Japan'),
        ('Slalom, LLC.', 'EMEA', 'UK'),
        ('Infosys', 'AMSExpansion', 'West'), ('Infosys', 'APJ', 'ANZ'),
        ('Billigence APAC', 'APJ', 'ANZ'), ('Billigence APAC', 'EMEA', 'CentralEMEA'),
        ('Mantel', 'APJ', 'ANZ'), ('Accenture', 'EMEA', 'UK'),
    ], columns=COLS)
    tagged = add_managed_group(rows)
    managed = tagged[tagged['_GROUP'].notna()]
    counts = managed['_GROUP'].value_counts().to_dict()
    assert counts == {GROUP_APJ: 5, GROUP_NOAM: 2, GROUP_EMEA: 2, GROUP_GSI: 1}
    assert sum(counts.values()) == len(managed) == 10  # Slalom Japan row is in no group


def test_region_map_sql_scopes_each_partner_to_its_region():
    sql = region_map_sql(APJ_RSI_REGION_MAP)
    anz = next(t for t in sql.split(" OR ") if "REGION_NAME = 'ANZ'" in t)
    assert "'Slalom, LLC.'" in anz and "'Infosys'" in anz
    assert "'NTT DATA Group Corporation'" not in anz
    esql = region_map_sql(EMEA_RSI_REGION_MAP)
    uk = next(t for t in esql.split(" OR ") if "REGION_NAME = 'UK'" in t)
    assert "'Aimpoint Digital'" in uk and "'Vivanti USA LLC'" in uk
    assert "'Billigence APAC'" not in uk


def test_scope_rsi_rows_custom_selection():
    df = pd.DataFrame([
        ('Slalom, LLC.', 'USMajors', 'Northeast'),   # NOAM view kept
        ('Slalom, LLC.', 'APJ', 'ANZ'),              # APJ region kept
        ('Slalom, LLC.', 'APJ', 'Japan'),            # dropped
        ('Slalom, LLC.', 'EMEA', 'UK'),              # EMEA region kept
        ('Slalom, LLC.', 'EMEA', 'NorthEMEA'),       # dropped
        ('Billigence APAC', 'APJ', 'ANZ'),           # kept
        ('Billigence APAC', 'EMEA', 'CentralEMEA'),  # kept
        ('Billigence APAC', 'EMEA', 'UK'),           # dropped
        ('Devoteam', 'EMEA', 'NorthEMEA'),           # dropped
        ('Mantel', 'AMSExpansion', 'West'),          # dropped (APJ-only RSI)
        ('Accenture', 'EMEA', 'UK'),                 # not an RSI: untouched
    ], columns=COLS)
    kept = list(map(tuple, scope_rsi_rows(df).values))
    assert kept == [
        ('Slalom, LLC.', 'USMajors', 'Northeast'), ('Slalom, LLC.', 'APJ', 'ANZ'),
        ('Slalom, LLC.', 'EMEA', 'UK'), ('Billigence APAC', 'APJ', 'ANZ'),
        ('Billigence APAC', 'EMEA', 'CentralEMEA'), ('Accenture', 'EMEA', 'UK'),
    ]


def test_pages_have_no_name_only_dual_logic():
    for page in ("okr_adoption.py", "overview.py", "executive_email.py"):
        src = (ROOT / "app_pages" / page).read_text()
        for stale in ("_NOAM_APJ_OKR", "_scope_apj_rows", "_DUAL_APJ_SUFFIX", "Kubrick"):
            assert stale not in src, (page, stale)


def test_pse_email_target_follows_peer_group():
    for page in ("pse_email_hybrid.py", "pse_email_hybrid_rest.py"):
        src = (ROOT / "app_pages" / page).read_text()
        assert "target = _peer_group_for(selected_partner)[3]" in src, page


def test_q4_okr_targets():
    from utils import GROUP_TARGET_PCT, GSI_NOAM_TARGET
    from utils.verified_metrics import GROUP_TARGETS
    assert GSI_NOAM_TARGET == 90
    assert GROUP_TARGET_PCT == {GROUP_GSI: 90, GROUP_NOAM: 90, GROUP_APJ: 75,
                                GROUP_EMEA: 75, 'LATAM RSI': 50}
    assert GROUP_TARGETS == {"GSI": 90, "NOAM": 90, "APJ": 75, "EMEA": 75, "LATAM": 50}
    for page in ("pse_email_hybrid.py", "pse_email_hybrid_rest.py"):
        src = (ROOT / "app_pages" / page).read_text()
        assert 'None, 75, "GSIs"' not in src and 'NOAM_THEATERS, 75' not in src, page
