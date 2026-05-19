# Partner alias mapping: sidebar name → all matching names in data
PARTNER_ALIASES = {
    'EY': ['EY', 'Ernst & Young (EY)'],
    '--- GSIs ---': [
        'Accenture', 'Capgemini Technologies LLC',
        'Cognizant Technology Solutions US Corp', 'Deloitte Consulting',
        'EY', 'Ernst & Young (EY)', 'IBM'
    ],
    '--- Regional SIs ---': [
        '7Rivers, Inc', 'Aimpoint Digital', 'BlueCloud Services Inc', 'kipi.ai',
        'evolv Consulting', 'Infostrux Solutions Inc.', 'Infosys', 'KPMG LLP',
        'LTIMindtree', 'NTT DATA Group Corporation', 'phData, Inc.',
        'Slalom, LLC.', 'Squadron Data Inc', 'Tredence Inc.'
    ],
}

# Group options to show at top of multiselect
PARTNER_GROUPS = ['--- GSIs ---', '--- Regional SIs ---']


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
