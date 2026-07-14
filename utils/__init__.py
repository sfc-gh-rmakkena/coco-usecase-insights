_NOAM_THEATERS = ['AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec']

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
