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
    'SDK Tek Services Ltd.':  ['SDK Tek Services Ltd.'],
    'Archetype Consulting':   ['Archetype Consulting'],
    'Everforth Apex Systems': ['Everforth Apex Systems'],
    'OneSix':                 ['OneSix'],
    'Icon Analytics':         ['Icon Analytics'],
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
        'Tiger Analytics Inc.', 'Atrium', 'Perficient Inc.', 'SDK Tek Services Ltd.',
        'Merkle', 'Archetype Consulting', 'Everforth Apex Systems',  'Tata Consultancy Services',
        'OneSix', 'Icon Analytics', 'Sparq Holdings, Inc.', 'CitiusTech Inc.',
        'Hexaware Technologies',
    ],
    '--- APJ RSIs ---': [
        'NTT DATA Group Corporation',       # Japan
        'MegazoneCloud Corporation',         # Korea
        'Infinite Lambda Limited',           # ASEAN
        'Infinite Lambda Inc',               # ASEAN (alias)
        'INFINITE LAMBDA (SINGAPORE) PTE. LTD.',  # ASEAN (alias)
        'Altis Consulting, ANZ',             # ANZ
        'PROLIM Global Corporation',         # India
    ],
    '--- EMEA RSIs ---': [
        'INFOMOTION GMBH',                   # CentralEMEA
        'INFOMOTION GMBH, BearingPoint',     # CentralEMEA (alias)
        'CIVICA SOFTWARE, S.L.',             # SouthEMEA (Spain)
        'Kubrick Group',                     # UK
        'KPC (Key Performance Consulting)',  # SouthEMEA (France)
        'KPC',                               # SouthEMEA (alias)
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
APJ_RSI_REGION_MAP = {
    'NTT DATA Group Corporation':               ('NTT Data',          'Japan'),
    'MegazoneCloud Corporation':                ('Megazone',          'Korea'),
    'Infinite Lambda Limited':                  ('Infinite Lambda',   'ASEAN'),
    'Infinite Lambda Inc':                      ('Infinite Lambda',   'ASEAN'),
    'INFINITE LAMBDA (SINGAPORE) PTE. LTD.':   ('Infinite Lambda',   'ASEAN'),
    'Altis Consulting, ANZ':                    ('Altis',             'ANZ'),
    'PROLIM Global Corporation':                ('Prolim',            'India'),
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
EMEA_RSI_REGION_MAP = {
    'INFOMOTION GMBH':                      ('Infomotion',  'CentralEMEA'),
    'INFOMOTION GMBH, BearingPoint':        ('Infomotion',  'CentralEMEA'),
    'CIVICA SOFTWARE, S.L.':               ('Civica',      'SouthEMEA'),
    'Kubrick Group':                        ('Kubrick',     'UK'),
    'KPC (Key Performance Consulting)':     ('KPC',         'SouthEMEA'),
    'KPC':                                  ('KPC',         'SouthEMEA'),
}

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
#     Merkle, SDK Tek Services, Squadron Data Inc, TEKsystems -> no pipeline entry at
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

    Exception: a use case tagged only because a partner wrote "#coco" in
    PARTNER_COMMENTS must ALSO show measured CoCo tokens in that customer account.
    A free-text hashtag is an assertion, not evidence - without consumption it was
    admitting cases whose comments said things like "will update #coco details once
    partner starts work" or "Deloitte has been cortex code #coco enabled" (partner
    enablement, not customer usage). SE_COMMENTS and FEATURE_FLAG are unchanged.
    """
    import pandas as pd

    base = (df["IS_COCO"] == True)  # noqa: E712 - pandas needs ==, not `is`
    if "CONFIDENCE_BAND" in df.columns:
        base = base | df["CONFIDENCE_BAND"].isin(list(bands))

    if "COCO_SOURCE" not in df.columns or "Q2_TOKENS" not in df.columns:
        return base  # cannot validate; leave the base rule untouched

    partner_only = (df["COCO_SOURCE"] == "PARTNER_COMMENTS")
    has_tokens = pd.to_numeric(df["Q2_TOKENS"], errors="coerce").fillna(0) > 0
    # A qualifying confidence band is independent evidence, so it still stands
    # on its own even when the partner comment cannot be corroborated.
    band_ok = (df["CONFIDENCE_BAND"].isin(list(bands))
               if "CONFIDENCE_BAND" in df.columns else False)

    return base & ~(partner_only & ~has_tokens & ~band_ok)


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


def new_coco_wow(df, coco_col="IS_COCO_FINAL", created_col="CREATED_DATE"):
    """Week-over-week movement in NEWLY CREATED CoCo use cases.

    Compares the last completed ISO week against the one before it, counting use
    cases by CREATED_DATE. Returns a dict of overall figures plus a per-partner
    frame. WOW_PCT is None when the prior week was zero (undefined, not infinite).

    Caveat worth surfacing in the UI: the source population is stages 3-7 only, so a
    use case appears here the week it was created ONLY if it had already advanced to
    Technical/Business Validation. This is "newly created and already qualified",
    not all new pipeline.
    """
    import pandas as pd

    empty = {
        "LAST_WK_NEW_COCO": 0, "PRIOR_WK_NEW_COCO": 0,
        "LAST_WK_NEW_TOTAL": 0, "PRIOR_WK_NEW_TOTAL": 0,
        "WOW_PCT": None, "WOW_DELTA": 0,
        "LAST_WK_START": None, "PRIOR_WK_START": None,
        "BY_PARTNER": pd.DataFrame(columns=[
            "PARTNER_NAME", "LAST_WK_NEW_COCO", "PRIOR_WK_NEW_COCO",
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
    if "PARTNER_NAME" in df.columns:
        _w = pd.DataFrame({
            "PARTNER_NAME": df["PARTNER_NAME"],
            "LAST_WK_NEW_COCO": (in_last & is_coco).astype(int),
            "PRIOR_WK_NEW_COCO": (in_prior & is_coco).astype(int),
        })
        by_partner = _w.groupby("PARTNER_NAME", as_index=False).sum()
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

