_NOAM_THEATERS = ['AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec']

import re as _re

def _normalize_name(s: str) -> str:
    """Normalize a company name for partner-own-account detection."""
    s = s.lower()
    for suffix in [' inc', ' llc', ' ltd', ' corp', ' consulting', ' services',
                   ' group', ' technologies', ' technology', ' limited', ' solutions',
                   ' advisory', ' partners', ' global', ' management']:
        s = s.replace(suffix, '')
    return _re.sub(r'[^a-z0-9]', '', s)


def is_partner_own_account(partner_name: str, account_name: str) -> bool:
    """Return True if account_name is likely the partner's own company account.

    Catches cases like:
    - 'BlueCloud Services Inc'  vs 'Blue.cloud'
    - 'Tata Consultancy Services' vs 'TATA Consultancy Services'
    - 'Merkle'                  vs 'Merkle, Inc.'
    - 'Deloitte Consulting'     vs 'Deloitte Services LP'
    """
    pn = _normalize_name(partner_name)
    an = _normalize_name(account_name)
    if not pn or not an or min(len(pn), len(an)) < 4:
        return False
    return pn in an or an in pn


def filter_out_partner_own_accounts(df, partner_col: str = 'PARTNER_NAME',
                                    account_col: str = 'ACCOUNT_NAME_UPPER') -> "pd.DataFrame":
    """Filter a DataFrame to remove rows where the account is the partner's own company.

    Args:
        df: DataFrame with partner and account columns.
        partner_col: column name for partner name.
        account_col: column name for account name (upper-cased expected).
    Returns:
        Filtered DataFrame with partner-own accounts removed.
    """
    if df is None or len(df) == 0:
        return df
    mask = df.apply(
        lambda r: not is_partner_own_account(
            str(r.get(partner_col, '') or ''),
            str(r.get(account_col, '') or '')
        ),
        axis=1
    )
    return df[mask].copy()


def resolve_region_theaters(region: str) -> list:
    """Map region or theater name to list of THEATER_NAME values for DataFrame filtering.
    Returns None when no filter should be applied (Global).
    """
    if not region or region == 'Global':
        return None
    elif region == 'NoAM':
        return _NOAM_THEATERS
    elif region in _NOAM_THEATERS:
        return [region]
    elif region == 'EMEA':
        return ['EMEA']
    elif region == 'APJ':
        return ['APJ']
    elif region == 'LATAM':
        return ['LATAM']
    return None



PARTNER_ALIASES = {
    'EY':      ['EY', 'Ernst & Young (EY)'],
    'IBM':     ['IBM', 'IBM Consulting'],
    'kipi.ai': ['kipi.ai', 'Kipi.ai'],
    'LTM':     ['LTM', 'LTI Mindtree'],
    'Tata Consultancy Services': [
        'Tata Consultancy Services', 'TCS', 'Tata Consultancy Services (TCS)',
    ],
    'Hexaware Technologies': [
        'Hexaware Technologies', 'Hexaware Technologies Limited',
        'Hexaware Technologies Inc', 'Hexaware Technologies UK Limited',
        'Hexaware Technolgies',
    ],
    'TEKsystems Global Services, LLC.': [
        'TEKsystems Global Services, LLC.', 'TEKsystems - Canada',
        'TEKSYSTEMS GLOBAL SERVICES (UK) LIMITED',
    ],
    'Perficient Inc.': ['Perficient Inc.', 'Perficient India Pvt Ltd'],
    'Merkle': [
        'Merkle', 'Merkle inc USA', 'Merkle ANZ Pty Ltd', 'Merkle Switzerland AG',
        'PT Merkle Inovasi Teknologi', 'Davanti a Merkle Company',
    ],
    'CitiusTech Inc.':        ['CitiusTech Inc.', 'CITIUS TECH'],
    'Spaulding Ridge':        ['Spaulding Ridge', 'Spaulding Ridge, EMEA',
                               'Spaulding Ridge Advisory Spain, S.L.'],
    'Blend360, LLC':          ['Blend360, LLC'],
    'Tiger Analytics Inc.':   ['Tiger Analytics Inc.'],
    'Atrium':                 ['Atrium'],
    # SDK Tek Services rebranded as Ateko; keep the old name for legacy use cases/history
    'Ateko':                  ['Ateko', 'SDK Tek Services Ltd.'],
    'Archetype Consulting':   ['Archetype Consulting'],
    'Everforth Apex Systems': ['Everforth Apex Systems'],
    'OneSix':                 ['OneSix'],
    'Sparq Holdings, Inc.':   ['Sparq Holdings, Inc.'],
    '--- GSIs ---': [
        'Accenture', 'Capgemini Technologies LLC',
        'Cognizant Technology Solutions US Corp', 'Deloitte Consulting',
        'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting'
    ],
    '--- NOAM RSIs ---': [
        # Former Regional SIs
        '7Rivers, Inc', 'Aimpoint Digital', 'BlueCloud Services Inc',
        'kipi.ai', 'Kipi.ai',
        'evolv Consulting', 'Infostrux Solutions Inc.', 'Infosys', 'KPMG LLP',
        'LTM', 'LTI Mindtree', 'phData, Inc.',
        'Slalom, LLC.', 'Squadron Data Inc', 'Tredence Inc.',
        # Former PSE Managed Partners
        'Spaulding Ridge', 'TEKsystems Global Services, LLC.', 'Blend360, LLC',
        'Tiger Analytics Inc.', 'Atrium', 'Perficient Inc.', 'Ateko', 'SDK Tek Services Ltd.',
        'Merkle', 'Archetype Consulting', 'Everforth Apex Systems',  'Tata Consultancy Services',
        'OneSix', 'Sparq Holdings, Inc.', 'CitiusTech Inc.',
        'Hexaware Technologies',
    ],
    '--- APJ RSIs ---': [
        # Partner names as stored in DT_OKR_USE_CASES; region per APJ_RSI_REGION_MAP.
        'NTT DATA Group Corporation', 'Altis Global Limited', 'Mantel', 'Slalom, LLC.',
        'Vivanti USA LLC', 'Bitek Information & Communication Inc.', 'DATUM STUDIO Co. Ltd.',
        'Billigence APAC', 'MegazoneCloud Corporation', 'NS Solutions Corporation',
        'InterWorks, Inc', 'ZEAL Corporation', 'ZEAL CORPORATION',
        'ITOCHU Techno-Solutions Corporation', 'Hitachi Solutions, Ltd.',
        'Intage Technosphere inc.', 'iZeno Pte Ltd', 'SHI Solutions India Private Limited',
        'PROLIM Global Corporation', 'SoftwareONE Pte Ltd (Singapore)', 'Infosys',
        'Quantiphi Inc.', 'ITGN OPS CO PTY LTD.', 'Infinite Lambda Limited', 'NEC Corporation',
        'Nomura Research Institute, Ltd.', 'Classmethod',
    ],
    '--- EMEA RSIs ---': [
        # Partner names as stored in DT_OKR_USE_CASES; region per EMEA_RSI_REGION_MAP.
        'Aimpoint Digital', 'Lumilinks Group Ltd', 'Slalom, LLC.',
        'SDG Consulting (EMEA) Consolidated', 'CIVICA SOFTWARE, S.L.', 'Devoteam',
        'KPC (Key Performance Consulting)', 'Twoday Oy', 'Recordly Oy', 'Solita Oy',
        'Navara Consulting Services BV', 'IN516HT TECHNOLOGIES CO. L.L.C',
        'Datalab Solutions (Pty) Ltd', '8Insights Consulting LLC', 'INFOMOTION GMBH',
        'Billigence APAC', 'b.telligent Group', 'synvert GmbH', 'CACI Limited',
        'Vivanti USA LLC',
    ],
    '--- LATAM RSIs ---': [
        'Viewnear - Partner',                                   # Mexico
        'EGOS BI SA DE CV',                                     # Mexico
        'IVCISA',                                               # CALA
        'SEIDOR ANALYTICS NORTH AMERICA CORP',                  # CALA
        'Keyrus Brasil Serviços de Informatica Ltda.',          # Brazil
    ],
}

# Group options to show at top of multiselect
PARTNER_GROUPS = ['--- GSIs ---', '--- NOAM RSIs ---', '--- APJ RSIs ---', '--- EMEA RSIs ---', '--- LATAM RSIs ---']

# Per-partner country restriction for APJ RSIs (REGION_NAME in DT_OKR / MDM)
# Key = canonical DT_OKR PARTNER_NAME, Value = (display_label, REGION_NAME)
# Slalom and Infosys are also NOAM RSIs: their NoAM-theater use cases count for
# NOAM and their ANZ ones for APJ. Decide a row's group with managed_group(), never
# by `partner in APJ_RSI_REGION_MAP` alone.
APJ_RSI_REGION_MAP = {
    'NTT DATA Group Corporation':               ('NTT DATA',          'ASEAN'),
    'Altis Global Limited':                     ('Altis',             'ANZ'),
    'Mantel':                                   ('Mantel',            'ANZ'),
    'Slalom, LLC.':                             ('Slalom (ANZ)',      'ANZ'),
    'Vivanti USA LLC':                          ('Vivanti',           'ANZ'),
    'Bitek Information & Communication Inc.':   ('Bitek',             'Korea'),
    'DATUM STUDIO Co. Ltd.':                    ('DATUM STUDIO',      'Japan'),
    'Billigence APAC':                          ('Billigence (ANZ)',  'ANZ'),
    'MegazoneCloud Corporation':                ('Megazone',          'Korea'),
    'NS Solutions Corporation':                 ('NS Solutions',      'Japan'),
    'InterWorks, Inc':                          ('InterWorks',        'ANZ'),
    'ZEAL Corporation':                         ('ZEAL Corporation',  'Japan'),
    'ZEAL CORPORATION':                         ('ZEAL Corporation',  'Japan'),
    'ITOCHU Techno-Solutions Corporation':      ('CTC (ITOCHU)',      'Japan'),
    'Hitachi Solutions, Ltd.':                  ('Hitachi Solutions', 'Japan'),
    'Intage Technosphere inc.':                 ('Intage',            'Japan'),
    'iZeno Pte Ltd':                            ('iZeno',             'ASEAN'),
    'SHI Solutions India Private Limited':      ('SHI Solutions',     'India'),
    'PROLIM Global Corporation':                ('PROLIM',            'India'),
    'SoftwareONE Pte Ltd (Singapore)':          ('SoftwareONE',       'ASEAN'),
    'Infosys':                                  ('Infosys (ANZ)',     'ANZ'),
    'Quantiphi Inc.':                           ('Quantiphi',         'India'),
    'ITGN OPS CO PTY LTD.':                     ('ITGN',              'ANZ'),
    'Infinite Lambda Limited':                  ('Infinite Lambda',   'ASEAN'),
    'NEC Corporation':                          ('NEC',               'Japan'),
    'Nomura Research Institute, Ltd.':          ('NRI',               'Japan'),
    'Classmethod':                              ('Classmethod',       'Japan'),
}

# Per-partner geo restriction for LATAM RSIs (REGION_NAME in DT_OKR)
LATAM_RSI_REGION_MAP = {
    'Viewnear - Partner':                               ('Viewnear',  'LATAM'),
    'EGOS BI SA DE CV':                                 ('EgosBi',    'LATAM'),
    'IVCISA':                                           ('IVCISA',    'LATAM'),
    'SEIDOR ANALYTICS NORTH AMERICA CORP':              ('Seidor',    'LATAM'),
    'Keyrus Brasil Serviços de Informatica Ltda.':      ('Keyrus',    'LATAM'),
}

# Per-partner country restriction for EMEA RSIs (REGION_NAME in DT_OKR)
# Some partners are in several groups (Aimpoint, Slalom: NOAM; Billigence, Vivanti,
# Slalom: APJ). Each use case still lands in one group via managed_group().
EMEA_RSI_REGION_MAP = {
    'Aimpoint Digital':                    ('Aimpoint Digital (UK)', 'UK'),
    'Lumilinks Group Ltd':                 ('Lumilinks',            'UK'),
    'Slalom, LLC.':                        ('Slalom (UK)',          'UK'),
    'SDG Consulting (EMEA) Consolidated':  ('SDG Consulting',       'SouthEMEA'),
    'CIVICA SOFTWARE, S.L.':               ('Civica',               'SouthEMEA'),
    'Devoteam':                            ('Devoteam',             'SouthEMEA'),
    'KPC (Key Performance Consulting)':    ('KPC',                  'SouthEMEA'),
    'Twoday Oy':                           ('Twoday',               'NorthEMEA'),
    'Recordly Oy':                         ('Recordly',             'NorthEMEA'),
    'Solita Oy':                           ('Solita',               'NorthEMEA'),
    'Navara Consulting Services BV':       ('Navara',               'NorthEMEA'),
    'IN516HT TECHNOLOGIES CO. L.L.C':      ('IN516HT',              'META'),
    'Datalab Solutions (Pty) Ltd':         ('Datalab Solutions',    'META'),
    '8Insights Consulting LLC':            ('8Insights',            'META'),
    'INFOMOTION GMBH':                     ('Infomotion',           'CentralEMEA'),
    'Billigence APAC':                     ('Billigence (EMEA)',    'CentralEMEA'),
    'b.telligent Group':                   ('b.telligent',          'CentralEMEA'),
    'synvert GmbH':                        ('synvert',              'CentralEMEA'),
    'CACI Limited':                        ('CACI',                 'UK'),
    'Vivanti USA LLC':                     ('Vivanti (UK)',         'UK'),
}


GROUP_GSI, GROUP_NOAM, GROUP_APJ, GROUP_EMEA, GROUP_LATAM = (
    'GSI', 'NOAM RSI', 'APJ RSI', 'EMEA RSI', 'LATAM RSI')

# Current OKR quarter. Change these (and the targets below) at each quarter roll-over.
OKR_QUARTER = 'Q4'
OKR_QUARTER_LABEL = 'Q4 FY27'
OKR_Q_START = '2026-11-01'
OKR_Q_END = '2027-01-31'
OKR_Q_MONTHS = 'Nov 2026 – Jan 2027'

# Q4 FY27 OKR CoCo adoption targets (%): GSI and NOAM RSI 90, regional RSIs 50.
GSI_NOAM_TARGET = 90
REGIONAL_RSI_TARGET = 50
GROUP_TARGET_PCT = {
    GROUP_GSI: GSI_NOAM_TARGET, GROUP_NOAM: GSI_NOAM_TARGET,
    GROUP_APJ: REGIONAL_RSI_TARGET, GROUP_EMEA: REGIONAL_RSI_TARGET, GROUP_LATAM: REGIONAL_RSI_TARGET,
}


def managed_group(partner, theater, region):
    """Managed group a single use-case row counts toward, or None.

    Decided per row, not per partner: a partner can be in more than one group
    (Slalom and Infosys are NOAM RSIs and APJ RSIs), and each of its use cases
    lands in exactly one group by geography, so group totals never double-count.
    """
    if partner in PARTNER_ALIASES['--- GSIs ---']:
        return GROUP_GSI
    if partner in PARTNER_ALIASES['--- NOAM RSIs ---'] and theater in _NOAM_THEATERS:
        return GROUP_NOAM
    for group, region_map in ((GROUP_APJ, APJ_RSI_REGION_MAP),
                              (GROUP_EMEA, EMEA_RSI_REGION_MAP),
                              (GROUP_LATAM, LATAM_RSI_REGION_MAP)):
        if partner in region_map and region == region_map[partner][1]:
            return group
    return None


def add_managed_group(df, partner_col='PARTNER_NAME', theater_col='THEATER_NAME',
                      region_col='REGION_NAME', out_col='_GROUP'):
    """Return a copy of df with `out_col` set by managed_group() for each row."""
    df = df.copy()
    df[out_col] = [
        managed_group(p, t, r) for p, t, r in
        zip(df[partner_col], df.get(theater_col, [None] * len(df)),
            df.get(region_col, [None] * len(df)))
    ]
    return df


def partner_groups(partner):
    """All managed groups a partner name belongs to (several for e.g. Slalom)."""
    out = []
    if partner in PARTNER_ALIASES['--- GSIs ---']:
        out.append(GROUP_GSI)
    if partner in PARTNER_ALIASES['--- NOAM RSIs ---']:
        out.append(GROUP_NOAM)
    for group, region_map in ((GROUP_APJ, APJ_RSI_REGION_MAP),
                              (GROUP_EMEA, EMEA_RSI_REGION_MAP),
                              (GROUP_LATAM, LATAM_RSI_REGION_MAP)):
        if partner in region_map:
            out.append(group)
    return out


def group_target_for(partner, rename_map=None):
    """OKR goal (%) for a partner from its first group (GSI/NOAM 90, regional RSIs 50),
    or None for a partner in no managed group. `rename_map` maps raw -> display names,
    so a display name like 'LTM' resolves through its raw alias."""
    groups = partner_groups(partner)
    if not groups and rename_map:
        raw = next((k for k, v in rename_map.items() if v == partner and partner_groups(k)), None)
        groups = partner_groups(raw) if raw else []
    return GROUP_TARGET_PCT[groups[0]] if groups else None


def scope_rsi_rows(df, partner_col='PARTNER_NAME', theater_col='THEATER_NAME',
                   region_col='REGION_NAME'):
    """Geo-scope rows for a custom partner selection.

    Partners only in region-scoped groups (APJ/EMEA/LATAM) keep rows in one of
    their mapped regions. Partners that are also GSIs or NOAM RSIs keep every row
    outside the APJ and EMEA theaters too (their unscoped view, as before), plus
    their mapped-region rows inside them. Partners in no RSI group are untouched.
    """
    if df is None or len(df) == 0 or region_col not in df.columns:
        return df

    def keep(partner, theater, region):
        groups = partner_groups(partner)
        regional = [g for g in groups if g in (GROUP_APJ, GROUP_EMEA, GROUP_LATAM)]
        if not regional:
            return True
        if managed_group(partner, theater, region) in regional:
            return True
        unscoped = GROUP_GSI in groups or GROUP_NOAM in groups
        return unscoped and theater not in ('APJ', 'EMEA')

    theaters = df[theater_col] if theater_col in df.columns else [None] * len(df)
    return df[[keep(p, t, r) for p, t, r in zip(df[partner_col], theaters, df[region_col])]]


def region_map_sql(region_map, alias='uc'):
    """OR'd SQL condition: each partner's rows in its own region only."""
    by_region = {}
    for partner, (_, region) in region_map.items():
        by_region.setdefault(region, []).append(partner.replace("'", "''"))
    terms = [
        f"({alias}.PARTNER_NAME IN ('" + "','".join(sorted(names)) + f"') "
        f"AND {alias}.REGION_NAME = '{region}')"
        for region, names in sorted(by_region.items())
    ]
    return "(" + " OR ".join(terms) + ")" if terms else "FALSE"

# Flat alias→canonical map for DataFrame PARTNER_NAME .replace() operations
# Derived from PARTNER_ALIASES: each non-group entry's aliases beyond the first
PARTNER_RENAME_MAP = {
    alias: canonical
    for canonical, aliases in PARTNER_ALIASES.items()
    if not canonical.startswith('---')
    for alias in aliases[1:]
}
# Results in: {'Ernst & Young (EY)': 'EY', 'IBM Consulting': 'IBM', 'Kipi.ai': 'kipi.ai', 'LTI Mindtree': 'LTM'}

# Case-insensitive lookup from any known spelling to its canonical display name.
# The partner-consultant pipeline stores some names in a different case than the
# use-case taxonomy — e.g. the roster has 'accenture' while use cases have
# 'Accenture' — which made an exact-match filter return nothing for that partner.
PARTNER_CANONICAL_BY_LOWER = {}
for _key, _names in PARTNER_ALIASES.items():
    # Group entries ('--- GSIs ---') list their member partners; non-group entries map a
    # canonical name to its alternate spellings. Both need to be in the lookup, or
    # partners that only appear inside a group (e.g. Accenture) would be missed.
    _candidates = list(_names) if _key.startswith('---') else [_key] + list(_names)
    for _name in _candidates:
        PARTNER_CANONICAL_BY_LOWER.setdefault(
            _name.lower(), PARTNER_RENAME_MAP.get(_name, _name))


def canonical_partner(name):
    """Map any known spelling/casing of a partner name to its canonical form."""
    if name is None:
        return name
    return PARTNER_CANONICAL_BY_LOWER.get(str(name).lower(), name)


# Sidebar/use-case taxonomy name -> the name(s) the partner-consultant pipeline uses.
# These are two independent naming systems: the sidebar comes from the use-case taxonomy
# while PARTNER_CONSULTANT_RESOLVED comes from the ultimate-parent account name, so an
# exact match fails for most partners and the page silently showed zero rows.
# Only unambiguous single-candidate matches are listed. Deliberately NOT mapped:
#   Tata Consultancy Services -> the pipeline has 'Tata Group of Companies' and
#     'Tata Elxsi', which are different legal entities from TCS.
#   Everforth Apex Systems, Blend360, Hexaware Technologies, KPC, kipi.ai, LTM/LTI Mindtree,
#     Merkle, Squadron Data Inc, TEKsystems -> no pipeline entry at
#     all, so they have genuinely no resolved consultants rather than a naming gap.
PARTNER_PIPELINE_CROSSWALK = {
    'Aimpoint Digital':                       ['Aimpoint Digital, LP'],
    'Capgemini Technologies LLC':             ['Capgemini Self-Service 2019-07-03 14:03:01Z'],
    'CitiusTech Inc.':                        ['CITIUSTECH HEALTHCARE TECHNOLOGY PRIVATE LIMITED'],
    'Cognizant Technology Solutions US Corp': ['Cognizant Technology Solutions Corporation-NJ (Life Sciences)'],
    # The only IBM entity in the pipeline is the Canadian one, so IBM reflects Canada
    # consultants only. Better than zero, but it is not IBM global.
    'IBM':                                    ['IBM Canada Limited'],
    'INFOMOTION GMBH':                        ['INFOMOTION'],
    'Infosys':                                ['Infosys Technologies Limited'],
    'MegazoneCloud Corporation':              ['Megazone'],
    'NTT DATA Group Corporation':             ['NTT'],
    'Perficient Inc.':                        ['Perficient'],
    'Tiger Analytics Inc.':                   ['Tiger Analytics'],
    'Tredence Inc.':                          ['Tredence'],
    'phData, Inc.':                           ['phdata'],
}

# Pipeline spellings must also resolve back to the canonical display name, otherwise
# rows render under the pipeline name and fail to merge with use-case counts.
for _canon, _pipeline_names in PARTNER_PIPELINE_CROSSWALK.items():
    for _pn in _pipeline_names:
        PARTNER_CANONICAL_BY_LOWER[_pn.lower()] = PARTNER_RENAME_MAP.get(_canon, _canon)


def resolve_partner_filter(partner_names):
    """Return list of all partner names to match for given sidebar selections.

    Expands group labels to their members, then adds the partner-consultant pipeline's
    own spelling for each name via PARTNER_PIPELINE_CROSSWALK, so a sidebar selection
    matches both the use-case taxonomy and the consultant tables.

    Args:
        partner_names: list of selected partner names from multiselect (empty = all)
    """
    if not partner_names:
        return []
    resolved = []
    for name in partner_names:
        resolved.extend(PARTNER_ALIASES.get(name, [name]))
    for name in list(resolved):
        resolved.extend(PARTNER_PIPELINE_CROSSWALK.get(name, []))
    return list(set(resolved))


def apply_coco_final(df, bands=("High",)):
    """Compute IS_COCO_FINAL on a confidence-scored frame.

    Base rule: IS_COCO (keyword or feature flag) OR the confidence band qualifies.

    Exception 1: a use case tagged only because a partner wrote "#coco" in
    PARTNER_COMMENTS must ALSO show measured CoCo tokens in that customer account.
    A free-text hashtag is an assertion, not evidence - without consumption it was
    admitting cases whose comments said things like "will update #coco details once
    partner starts work" or "Deloitte has been cortex code #coco enabled" (partner
    enablement, not customer usage). SE_COMMENTS and FEATURE_FLAG are unchanged.
    The rule is skipped when the UC also has "AI - Cortex Code" in Prioritized
    Features (HAS_FEATURE_FLAG): the PSE comment plus the structured flag together
    count as CoCo even before consumption shows up (or when telemetry lands under a
    differently named account, e.g. a parent billing entity).

    Exception 2: a use case tagged with "#notcoco" in PARTNER_COMMENTS (IS_NOT_COCO=TRUE)
    is suppressed from CoCo counting UNLESS the account shows actual token consumption
    (has_tokens=True) or a qualifying confidence band from usage data (band_ok=True).
    This lets PSEs flag UCs that cannot use CoCo right now; if they later add #coco
    or consumption evidence appears, the UC automatically becomes CoCo again.

    Exception 3: a use case tagged with "#notinvolved" in PARTNER_COMMENTS
    (IS_NOT_INVOLVED=TRUE) is suppressed unconditionally — the PSE has confirmed the
    partner has no active involvement in this deal, so it cannot be attributed to
    them regardless of token/consumption evidence.
    """
    import pandas as pd

    base = (df["IS_COCO"] == True)  # noqa: E712 - pandas needs ==, not `is`
    if "CONFIDENCE_BAND" in df.columns:
        base = base | df["CONFIDENCE_BAND"].isin(list(bands))

    if "COCO_SOURCE" not in df.columns or "Q2_TOKENS" not in df.columns:
        return base  # cannot validate; leave the base rule untouched

    tokens = pd.to_numeric(df["Q2_TOKENS"], errors="coerce").fillna(0)
    has_tokens = tokens > 0
    band_ok = (df["CONFIDENCE_BAND"].isin(list(bands))
               if "CONFIDENCE_BAND" in df.columns else False)

    # Exception 1: PARTNER_COMMENTS-only requires token evidence, unless the
    # "AI - Cortex Code" prioritized feature flag is also set on the UC
    partner_only = (df["COCO_SOURCE"] == "PARTNER_COMMENTS")
    if "HAS_FEATURE_FLAG" in df.columns:
        partner_only = partner_only & ~df["HAS_FEATURE_FLAG"].fillna(False).astype(bool)
    result = base & ~(partner_only & ~has_tokens & ~band_ok)

    # Exception 2: #notcoco always wins — PSE explicitly blocks the UC regardless of token data
    if "IS_NOT_COCO" in df.columns:
        not_coco = df["IS_NOT_COCO"].fillna(False).astype(bool)
        result = result & ~not_coco

    # Exception 3: #notinvolved — PSE confirms the partner has no active involvement in this
    # deal, so it can't be attributed to them as CoCo regardless of token data
    if "IS_NOT_INVOLVED" in df.columns:
        not_involved = df["IS_NOT_INVOLVED"].fillna(False).astype(bool)
        result = result & ~not_involved

    return result


def last_two_iso_weeks():
    """(last_week_start, last_week_end, prior_week_start, prior_week_end) as dates.

    Both windows are COMPLETED Monday-Sunday weeks. The week in progress is excluded
    on purpose: new-use-case creation runs only 4-20 per week in the OKR population,
    so a partial week reads as a collapse (measured -100% on a Wednesday) rather than
    a real decline.
    """
    from datetime import date, timedelta as _td

    today = date.today()
    this_week_start = today - _td(days=today.weekday())   # Monday of current week
    last_start = this_week_start - _td(days=7)
    prior_start = this_week_start - _td(days=14)
    return last_start, last_start + _td(days=6), prior_start, prior_start + _td(days=6)


def new_coco_wow(df, coco_col="IS_COCO_FINAL", created_col="CREATED_DATE", group_col="PARTNER_NAME"):
    """Week-over-week movement in NEWLY CREATED CoCo use cases.

    Compares the last completed ISO week against the one before it, counting use
    cases by CREATED_DATE. Returns a dict of overall figures plus a per-group frame
    (keyed by group_col — PARTNER_NAME, _GROUP, STAGE_GROUP, ...). WOW_PCT is None
    when the prior week was zero (undefined, not infinite).

    Caveat worth surfacing in the UI: the source population is stages 3-7 only, so a
    use case appears here the week it was created ONLY if it had already advanced to
    Technical/Business Validation. This is "newly created and already qualified",
    not all new pipeline.
    """
    import pandas as pd

    _gc = group_col or "PARTNER_NAME"
    empty = {
        "LAST_WK_NEW_COCO": 0, "PRIOR_WK_NEW_COCO": 0,
        "LAST_WK_NEW_TOTAL": 0, "PRIOR_WK_NEW_TOTAL": 0,
        "WOW_PCT": None, "WOW_DELTA": 0,
        "LAST_WK_START": None, "PRIOR_WK_START": None,
        "BY_PARTNER": pd.DataFrame(columns=[
            _gc, "LAST_WK_NEW_COCO", "PRIOR_WK_NEW_COCO",
            "NEW_COCO_WOW_PCT", "NEW_COCO_WOW_DELTA"]),
    }
    if df is None or len(df) == 0 or created_col not in df.columns or coco_col not in df.columns:
        return empty

    ls, le, ps, pe = last_two_iso_weeks()
    created = pd.to_datetime(df[created_col], errors="coerce")
    if created.notna().sum() == 0:
        return empty
    created = created.dt.date

    in_last = (created >= ls) & (created <= le)
    in_prior = (created >= ps) & (created <= pe)
    is_coco = df[coco_col].fillna(False).astype(bool)

    last_coco = int((in_last & is_coco).sum())
    prior_coco = int((in_prior & is_coco).sum())
    wow_pct = round((last_coco - prior_coco) * 100.0 / prior_coco, 1) if prior_coco > 0 else None

    by_partner = pd.DataFrame()
    if _gc in df.columns:
        _w = pd.DataFrame({
            _gc: df[_gc],
            "LAST_WK_NEW_COCO": (in_last & is_coco).astype(int),
            "PRIOR_WK_NEW_COCO": (in_prior & is_coco).astype(int),
            "LAST_WK_NEW_TOTAL": in_last.astype(int),
            "PRIOR_WK_NEW_TOTAL": in_prior.astype(int),
        })
        by_partner = _w.groupby(_gc, as_index=False).sum()
        by_partner["NEW_COCO_WOW_DELTA"] = (
            by_partner["LAST_WK_NEW_COCO"] - by_partner["PRIOR_WK_NEW_COCO"])
        by_partner["NEW_COCO_WOW_PCT"] = (
            by_partner["NEW_COCO_WOW_DELTA"] * 100.0
            / by_partner["PRIOR_WK_NEW_COCO"].replace(0, float("nan"))
        ).round(1)

    return {
        "LAST_WK_NEW_COCO": last_coco,
        "PRIOR_WK_NEW_COCO": prior_coco,
        "LAST_WK_NEW_TOTAL": int(in_last.sum()),
        "PRIOR_WK_NEW_TOTAL": int(in_prior.sum()),
        "WOW_PCT": wow_pct,
        "WOW_DELTA": last_coco - prior_coco,
        "LAST_WK_START": ls,
        "PRIOR_WK_START": ps,
        "BY_PARTNER": by_partner,
    }


NEW_COCO_WOW_HELP = (
    "Newly created CoCo use cases: last completed Mon-Sun week vs the week before, "
    "counted by CREATED_DATE. Population is stages 3-7, so a use case counts only if "
    "it had already reached Technical/Business Validation — this is new-and-qualified, "
    "not all new pipeline. Blank means the prior week was zero."
)

# ── "New CoCo use cases this week" columns, shared across every table ─────────
# One definition, one pair of labels, so the theatre / region / partner / stage
# tables cannot drift apart. NEW_COCO_WK is the count created in the last COMPLETED
# Mon-Sun week; NEW_COCO_DELTA is that count minus the prior week's.
NEW_COCO_WK_COL = "NEW_COCO_WK"
NEW_COCO_DELTA_COL = "NEW_COCO_DELTA"
NEW_COCO_WK_LABEL = "New CoCo UCs (wk)"
NEW_COCO_DELTA_LABEL = "Δ vs prior wk"
NEW_COCO_WK_HELP = (
    "Use cases that TRANSITIONED into CoCo status during the last completed Mon-Sun "
    "week — SE/partner comment added, AI feature flag enabled, or account consumption "
    "crossed the High confidence threshold for the first time. Source: "
    "UC_COCO_STATUS_WEEKLY snapshot comparison."
)
NEW_COCO_DELTA_HELP = (
    "Change vs the week before: last completed week's newly-CoCo use cases minus the "
    "prior week's. Shown as a raw count rather than a percentage because weekly "
    "volumes are small."
)
NEW_THIS_WEEK_LABEL = "New this wk"
NEW_THIS_WEEK_HELP = (
    "Yes = this use case was created during the last completed Mon-Sun week."
)


def new_coco_col_config(st_mod, wk_key=NEW_COCO_WK_COL, delta_key=NEW_COCO_DELTA_COL):
    """column_config entries for the two shared columns. Pass in `streamlit`.

    wk_key/delta_key let callers whose display frame is keyed by the human labels
    (several overview tables rename positionally) reuse the same formats and help.
    """
    return {
        wk_key: st_mod.column_config.NumberColumn(
            NEW_COCO_WK_LABEL, format="%d", help=NEW_COCO_WK_HELP),
        delta_key: st_mod.column_config.NumberColumn(
            NEW_COCO_DELTA_LABEL, format="%+d", help=NEW_COCO_DELTA_HELP),
    }


def new_coco_by_group(uc_df, group_col, coco_col="IS_COCO_FINAL", created_col="CREATED_DATE"):
    """Per-group new-CoCo counts for the last completed week and the change vs prior.

    group_col may be a single column name or a list of names (composite grain, e.g.
    partner x stage). Returns a frame of [*group_cols, NEW_COCO_WK, NEW_COCO_DELTA],
    or an empty frame with those columns when the inputs cannot support the metric.
    """
    import pandas as pd

    keys = [group_col] if isinstance(group_col, str) else list(group_col)
    cols = keys + [NEW_COCO_WK_COL, NEW_COCO_DELTA_COL]
    if (uc_df is None or len(uc_df) == 0
            or created_col not in uc_df.columns
            or coco_col not in uc_df.columns
            or any(k not in uc_df.columns for k in keys)):
        return pd.DataFrame(columns=cols)

    ls, le, ps, pe = last_two_iso_weeks()
    created = pd.to_datetime(uc_df[created_col], errors="coerce")
    if created.notna().sum() == 0:
        return pd.DataFrame(columns=cols)
    created = created.dt.date
    is_coco = uc_df[coco_col].fillna(False).astype(bool)

    work = uc_df[keys].copy()
    work["_last"] = ((created >= ls) & (created <= le) & is_coco).astype(int)
    work["_prior"] = ((created >= ps) & (created <= pe) & is_coco).astype(int)
    agg = work.groupby(keys, as_index=False, dropna=False).sum()
    agg[NEW_COCO_WK_COL] = agg["_last"].astype(int)
    agg[NEW_COCO_DELTA_COL] = (agg["_last"] - agg["_prior"]).astype(int)
    return agg[cols]


def merge_new_coco(display_df, uc_df, group_col, left_key=None,
                   coco_col="IS_COCO_FINAL", created_col="CREATED_DATE"):
    """Attach NEW_COCO_WK / NEW_COCO_DELTA to a display frame.

    left_key names the matching column(s) on display_df when they differ from
    group_col. Rows with no match get 0 rather than NaN: a group that booked no new
    CoCo use cases genuinely booked zero, which is different from "unknown". When the
    metric cannot be computed at all the columns are still added as 0 so callers can
    reference them unconditionally.
    """
    import pandas as pd

    if display_df is None or len(display_df) == 0:
        return display_df

    keys = [group_col] if isinstance(group_col, str) else list(group_col)
    lkeys = keys if left_key is None else ([left_key] if isinstance(left_key, str) else list(left_key))
    out = display_df.copy()

    by_group = new_coco_by_group(uc_df, group_col, coco_col=coco_col, created_col=created_col)
    if len(by_group) == 0 or any(k not in out.columns for k in lkeys):
        out[NEW_COCO_WK_COL] = 0
        out[NEW_COCO_DELTA_COL] = 0
        return out

    right = by_group.rename(columns=dict(zip(keys, lkeys)))
    out = out.merge(right, on=lkeys, how="left")
    for _c in (NEW_COCO_WK_COL, NEW_COCO_DELTA_COL):
        out[_c] = pd.to_numeric(out[_c], errors="coerce").fillna(0).astype(int)
    return out


def merge_newly_coco(display_df, conn, group_col, left_key=None):
    """Attach NEW_COCO_WK / NEW_COCO_DELTA to a display frame using the
    transition-based UC_COCO_STATUS_WEEKLY snapshot (False→True this week).

    Preferred over merge_new_coco() when the snapshot table has data.
    Falls back silently to zero-filled columns when the table is empty or
    the query fails, so callers never need to guard against missing columns.

    group_col: column in UC_COCO_STATUS_WEEKLY to group by
               ('THEATER_NAME' | 'PARTNER_NAME' | 'REGION_NAME')
    left_key:  matching column on display_df when it differs from group_col
    """
    import pandas as pd
    from utils.queries import get_newly_coco_by_group

    if display_df is None or len(display_df) == 0:
        return display_df

    out = display_df.copy()
    lkey = left_key if left_key is not None else group_col

    by_group = get_newly_coco_by_group(conn, group_col)
    if len(by_group) == 0 or lkey not in out.columns:
        out[NEW_COCO_WK_COL]    = 0
        out[NEW_COCO_DELTA_COL] = 0
        return out

    right = by_group.rename(columns={group_col: lkey})
    out = out.merge(right, on=lkey, how="left")
    for _c in (NEW_COCO_WK_COL, NEW_COCO_DELTA_COL):
        out[_c] = pd.to_numeric(out[_c], errors="coerce").fillna(0).astype(int)
    return out


def new_this_week_flag(df, created_col="CREATED_DATE"):
    """Per-row "was this use case created in the last completed week?" as Yes / "-".

    For individual-use-case tables, where a group count has no meaning.
    """
    import pandas as pd

    if df is None or len(df) == 0 or created_col not in df.columns:
        return pd.Series(["-"] * (0 if df is None else len(df)),
                         index=None if df is None else df.index)
    ls, le, _ps, _pe = last_two_iso_weeks()
    created = pd.to_datetime(df[created_col], errors="coerce").dt.date
    return pd.Series(
        [("Yes" if (d is not None and pd.notna(d) and ls <= d <= le) else "-") for d in created],
        index=df.index,
    )


