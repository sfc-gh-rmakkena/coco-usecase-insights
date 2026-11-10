"""LATAM RSI roster (Q4): 17 partners in three sub-regions, Deloitte and Accenture in
both GSI and LATAM RSI without changing GSI totals or double-counting overall."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import (  # noqa: E402
    GROUP_GSI, GROUP_LATAM, GROUP_NOAM, LATAM_GSI_OVERLAP, LATAM_RSI_REGION_MAP,
    LATAM_SUBREGION, PARTNER_ALIASES, add_managed_group, in_group, managed_group,
    region_map_sql, scope_rsi_rows,
)

SHEET = {  # label -> sub-region, from the requested list
    'Mexico & CALA North': {'Viewnear', 'EgosBI', 'Seidor', 'Datateam', 'IVCISA'},
    'Colombia & CALA South': {'Triario', 'All For Analytics', 'Stratify',
                              'Deloitte (LATAM)', 'Accenture (LATAM)'},
    'Brazil': {'Keyrus', 'Triggo.ai', 'BeData/Objective', 'Jump Label',
               'iBlue Consulting', 'Dataside', 'DataSoluTec'},
}
COLS = ['PARTNER_NAME', 'THEATER_NAME', 'REGION_NAME']


def test_roster_matches_request():
    labels = {v[0] for v in LATAM_RSI_REGION_MAP.values()}
    assert labels == set().union(*SHEET.values())
    assert len(labels) == 17
    for sub, names in SHEET.items():
        assert {l for l, s in LATAM_SUBREGION.items() if s == sub} == names, sub
    assert set(PARTNER_ALIASES['--- LATAM RSIs ---']) == set(LATAM_RSI_REGION_MAP)


def test_exact_db_names_and_both_triggo_spellings():
    for raw in ('Viewnear - Partner', 'EGOS BI SA DE CV', 'SEIDOR ANALYTICS NORTH AMERICA CORP',
                'Datateam Consulting SA de CV', 'IVCISA', 'Triario International Group LLC',
                'All For Analytics', 'Deloitte Consulting', 'Accenture',
                'Keyrus Brasil Serviços de Informatica Ltda.', 'IBLUE CONSULTING',
                'TRIGGO.AI TECNOLOGIA E INTELIGENCIA DE DADOS LTDA.', 'Triggo.ai'):
        assert raw in LATAM_RSI_REGION_MAP, raw
    assert LATAM_RSI_REGION_MAP['Triggo.ai'][0] == LATAM_RSI_REGION_MAP[
        'TRIGGO.AI TECNOLOGIA E INTELIGENCIA DE DADOS LTDA.'][0]
    assert all(region == 'LATAM' for _, region in LATAM_RSI_REGION_MAP.values())


def test_old_only_partners_removed():
    assert 'EgosBi' not in {v[0] for v in LATAM_RSI_REGION_MAP.values()}  # relabelled EgosBI
    assert LATAM_GSI_OVERLAP == {'Deloitte Consulting', 'Accenture'}


@pytest.mark.parametrize("partner,theater,region,group,expected", [
    ('Accenture', 'AMSAcquisition', 'LATAM', GROUP_GSI, True),     # GSI stays global
    ('Accenture', 'AMSAcquisition', 'LATAM', GROUP_LATAM, True),   # ...and LATAM too
    ('Accenture', 'EMEA', 'UK', GROUP_LATAM, False),
    ('Deloitte Consulting', 'USMajors', 'West', GROUP_GSI, True),
    ('Deloitte Consulting', 'AMSAcquisition', 'LATAM', GROUP_LATAM, True),
    ('IVCISA', 'AMSAcquisition', 'LATAM', GROUP_LATAM, True),
    ('IVCISA', 'AMSAcquisition', 'LATAM', GROUP_NOAM, False),
    ('Triggo.ai', 'AMSAcquisition', 'LATAM', GROUP_LATAM, True),
])
def test_in_group(partner, theater, region, group, expected):
    assert in_group(partner, theater, region, group) is expected


def test_gsi_overlap_counts_in_both_groups_but_once_overall():
    rows = pd.DataFrame([
        ('Accenture', 'AMSAcquisition', 'LATAM'), ('Accenture', 'EMEA', 'UK'),
        ('Deloitte Consulting', 'AMSAcquisition', 'LATAM'),
        ('IVCISA', 'AMSAcquisition', 'LATAM'), ('Triggo.ai', 'AMSAcquisition', 'LATAM'),
    ], columns=COLS)
    tagged = add_managed_group(rows)
    # Overall: one group per row, GSI totals unchanged (3 GSI rows incl. LATAM ones).
    assert tagged['_GROUP'].value_counts().to_dict() == {GROUP_GSI: 3, GROUP_LATAM: 2}
    # LATAM RSI own figures add the GSIs' LATAM rows.
    latam = [in_group(p, t, r, GROUP_LATAM) for p, t, r in rows[COLS].itertuples(index=False)]
    assert sum(latam) == 4
    gsi = [in_group(p, t, r, GROUP_GSI) for p, t, r in rows[COLS].itertuples(index=False)]
    assert sum(gsi) == 3


def test_custom_selection_keeps_gsi_rows_global():
    df = pd.DataFrame([('Accenture', 'EMEA', 'UK'), ('Accenture', 'AMSAcquisition', 'LATAM'),
                       ('IVCISA', 'EMEA', 'UK'), ('IVCISA', 'AMSAcquisition', 'LATAM')],
                      columns=COLS)
    kept = list(map(tuple, scope_rsi_rows(df).values))
    assert kept == [('Accenture', 'EMEA', 'UK'), ('Accenture', 'AMSAcquisition', 'LATAM'),
                    ('IVCISA', 'AMSAcquisition', 'LATAM')]


def test_latam_adoption_sql_uses_exact_names():
    src = (ROOT / "utils" / "queries.py").read_text()
    fn = src[src.index("def get_latam_rsi_adoption"):][:400]
    assert "_rsi_adoption(_conn, LATAM_RSI_REGION_MAP" in fn
    assert "ILIKE '%Viewnear%'" not in src
    sql = region_map_sql(LATAM_RSI_REGION_MAP)
    assert "'Triggo.ai'" in sql and "REGION_NAME = 'LATAM'" in sql


def test_combined_sets_keep_gsi_latam_rows_once():
    for page, needle in (("overview.py", "_pf(_LATAM_RSI_PARTNER_NAMES - _GSI_PARTNER_NAMES)"),
                         ("okr_adoption.py", "set(LATAM_RSI_REGION_MAP.keys()) - _GSI_OKR"),
                         ("executive_email.py", "_LATAM_RSI_NAMES_EMAIL - set(_GSI_NAMES)")):
        assert needle in (ROOT / "app_pages" / page).read_text(), page


def test_overview_latam_section_has_subregions():
    src = (ROOT / "app_pages" / "overview.py").read_text()
    assert "LATAM_SUBREGION.get(_lbl, 'LATAM')" in src
    assert "_latam_df.groupby('COUNTRY', sort=False)" in src
    assert "'LATAM (CALA)'" not in src
