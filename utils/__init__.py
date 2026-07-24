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
    'Apex Systems':           ['Apex Systems'],
    'OneSix':                 ['OneSix'],
    'Icon Analytics':         ['Icon Analytics'],
    'Sparq Holdings, Inc.':   ['Sparq Holdings, Inc.'],
    '--- GSIs ---': [
        'Accenture', 'Capgemini Technologies LLC',
        'Cognizant Technology Solutions US Corp', 'Deloitte Consulting',
        'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting'
    ],
    '--- Regional SIs ---': [
        '7Rivers, Inc', 'Aimpoint Digital', 'BlueCloud Services Inc',
        'kipi.ai', 'Kipi.ai',
        'evolv Consulting', 'Infostrux Solutions Inc.', 'Infosys', 'KPMG LLP',
        'LTM', 'LTI Mindtree', 'NTT DATA Group Corporation', 'phData, Inc.',
        'Slalom, LLC.', 'Squadron Data Inc', 'Tredence Inc.'
    ],
    '--- PSE Managed Partners ---': [
        'Spaulding Ridge', 'TEKsystems Global Services, LLC.', 'Blend360, LLC',
        'Tiger Analytics Inc.', 'Atrium', 'Perficient Inc.', 'SDK Tek Services Ltd.',
        'Merkle', 'Archetype Consulting', 'Apex Systems', 'Tata Consultancy Services',
        'OneSix', 'Icon Analytics', 'Sparq Holdings, Inc.', 'CitiusTech Inc.',
        'Hexaware Technologies',
    ],
}

# Group options to show at top of multiselect
PARTNER_GROUPS = ['--- GSIs ---', '--- Regional SIs ---', '--- PSE Managed Partners ---']

# Flat alias→canonical map for DataFrame PARTNER_NAME .replace() operations
# Derived from PARTNER_ALIASES: each non-group entry's aliases beyond the first
PARTNER_RENAME_MAP = {
    alias: canonical
    for canonical, aliases in PARTNER_ALIASES.items()
    if not canonical.startswith('---')
    for alias in aliases[1:]
}
# Results in: {'Ernst & Young (EY)': 'EY', 'IBM Consulting': 'IBM', 'Kipi.ai': 'kipi.ai', 'LTI Mindtree': 'LTM'}


def resolve_partner_filter(partner_names):
    """Return list of all partner names to match for given sidebar selections.
    
    Args:
        partner_names: list of selected partner names from multiselect (empty = all)
    """
    if not partner_names:
        return []
    resolved = []
    for name in partner_names:
        resolved.extend(PARTNER_ALIASES.get(name, [name]))
    return list(set(resolved))
