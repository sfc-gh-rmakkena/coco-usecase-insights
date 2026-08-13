import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import urllib.parse
import markdown
from datetime import datetime
from utils.queries import (
    get_summary_stats, get_by_partner, get_by_stage, get_source_breakdown,
    get_by_region, get_email_summary_data, get_use_case_type_patterns,
    get_workload_patterns, get_competitive_landscape, get_comment_narratives,
    get_partner_workload_cross, get_regional_themes, get_regional_comment_narratives,
    get_partner_coco_coverage, get_partner_credit_consumption, get_adoption_overview,
    get_bulk_confidence_scores, get_pipeline_wow, get_gsi_wow, get_noam_si_wow,
    get_recent_wins, get_coco_final_wow, get_coco_final_trend_4w, save_coco_final_snapshot,
    get_partners_at_target_trend_4w, save_okr_target_count,
    get_partner_velocity_data, get_account_coco_credits,
)
from utils.cortex_helpers import cortex_complete
from utils import APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, PARTNER_ALIASES as _PA_EMAIL

_NOAM_RSI_NAMES_EMAIL = frozenset(
    p for p in _PA_EMAIL.get('--- NOAM RSIs ---', []) if not p.startswith('---')
) | {'LTI Mindtree', 'Kipi.ai'}
_APJ_RSI_NAMES_EMAIL  = frozenset(APJ_RSI_REGION_MAP.keys())
_EMEA_RSI_NAMES_EMAIL = frozenset(EMEA_RSI_REGION_MAP.keys())

MANAGED_PARTNERS = list(
    # GSIs
    {'Accenture', 'Capgemini Technologies LLC', 'Cognizant Technology Solutions US Corp',
     'Deloitte Consulting', 'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting'}
    | _NOAM_RSI_NAMES_EMAIL
    | _APJ_RSI_NAMES_EMAIL
    | _EMEA_RSI_NAMES_EMAIL
)

# GSIs report globally (all theaters); NOAM RSIs report NoAM only.
# Aliases: EY=Ernst & Young (EY), IBM=IBM Consulting, kipi.ai=Kipi.ai, LTM=LTI Mindtree
_GSI_NAMES = frozenset({
    'Accenture', 'Capgemini Technologies LLC', 'Cognizant Technology Solutions US Corp',
    'Deloitte Consulting', 'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting'
})

# Short display name → canonical partner name for heatmap tiles
# Built dynamically from all 4 groups
_HEATMAP_GSI = [
    ('Accenture',  'Accenture'),
    ('Capgemini',  'Capgemini Technologies LLC'),
    ('Cognizant',  'Cognizant Technology Solutions US Corp'),
    ('Deloitte',   'Deloitte Consulting'),
    ('EY',         'EY'),
    ('IBM',        'IBM'),
]
_HEATMAP_NOAM = [
    ('7Rivers',     '7Rivers, Inc'),       ('Aimpoint',  'Aimpoint Digital'),
    ('BlueCloud',   'BlueCloud Services Inc'), ('kipi.ai', 'kipi.ai'),
    ('evolv',       'evolv Consulting'),   ('Infostrux', 'Infostrux Solutions Inc.'),
    ('Infosys',     'Infosys'),            ('KPMG',      'KPMG LLP'),
    ('LTM',         'LTM'),               ('phData',    'phData, Inc.'),
    ('Slalom',      'Slalom, LLC.'),       ('Squadron',  'Squadron Data Inc'),
    ('Tredence',    'Tredence Inc.'),      ('Spaulding', 'Spaulding Ridge'),
    ('TEKsystems',  'TEKsystems Global Services, LLC.'),
    ('Blend360',    'Blend360, LLC'),      ('Tiger',     'Tiger Analytics Inc.'),
    ('Atrium',      'Atrium'),             ('Perficient','Perficient Inc.'),
    ('SDK Tek',     'SDK Tek Services Ltd.'), ('Merkle',  'Merkle'),
    ('Archetype',   'Archetype Consulting'), ('Apex',    'Apex Systems'),
    ('TCS',         'Tata Consultancy Services'), ('OneSix', 'OneSix'),
    ('Icon',        'Icon Analytics'),    ('Sparq',     'Sparq Holdings, Inc.'),
    ('CitiusTech',  'CitiusTech Inc.'),   ('Hexaware',  'Hexaware Technologies'),
]
# APJ/EMEA: deduplicate aliases by display label (v[0]) keeping first canonical key
_seen_apj = {}
for k, v in APJ_RSI_REGION_MAP.items():
    _seen_apj.setdefault(v[0], k)
_HEATMAP_APJ  = [(label, key) for label, key in _seen_apj.items()]
_seen_emea = {}
for k, v in EMEA_RSI_REGION_MAP.items():
    _seen_emea.setdefault(v[0], k)
_HEATMAP_EMEA = [(label, key) for label, key in _seen_emea.items()]

HEATMAP_PARTNERS = _HEATMAP_GSI + _HEATMAP_NOAM + _HEATMAP_APJ + _HEATMAP_EMEA
# Group target thresholds for heatmap colouring (GSI/NOAM=75%, APJ/EMEA=50%)
_HEATMAP_GSI_KEYS  = {k for _, k in _HEATMAP_GSI}
_HEATMAP_NOAM_KEYS = {k for _, k in _HEATMAP_NOAM}
_APJ_KEYS_HEATMAP  = {k for _, k in _HEATMAP_APJ}
_EMEA_KEYS_HEATMAP = {k for _, k in _HEATMAP_EMEA}
def _partner_target(data_key):
    return 50 if (data_key in _APJ_KEYS_HEATMAP or data_key in _EMEA_KEYS_HEATMAP) else 75


def _fmt_tokens(n):
    if n is None or n != n:  # NaN check
        return "-"
    n = float(n)
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{int(n)}"


def name_to_email(name):
    name = name.strip()
    if '@' in name:
        return name
    parts = name.lower().split()
    if len(parts) >= 2:
        return f"{'.'.join(parts)}@snowflake.com"
    elif len(parts) == 1:
        return f"{parts[0]}@snowflake.com"
    return name


def generate_heatmap_html(adoption_wow_data: pd.DataFrame, managed_q2_partners: pd.DataFrame) -> str:
    """Build Gmail-compatible partner OKR heat map.
    Green ≥75%, amber 50-74%, red <50%.
    """
    pct_map: dict = {}
    wow_map: dict = {}

    # Primary: IS_COCO_FINAL from managed_q2_partners (same basis as scorecard)
    if len(managed_q2_partners) > 0:
        for _, row in managed_q2_partners.iterrows():
            pct_map[str(row['PARTNER_NAME'])] = float(row.get('COCO_PCT') or 0)

    # WoW delta from snapshot (only source for deltas)
    if len(adoption_wow_data) > 0:
        for _, row in adoption_wow_data[adoption_wow_data['PARTNER_NAME'].notna()].iterrows():
            name = str(row['PARTNER_NAME'])
            wow_val = row.get('WOW_COCO_PCT')
            wow_map[name] = float(wow_val) if pd.notna(wow_val) else None
            # Fallback pct for partners absent from managed_q2_partners
            if name not in pct_map:
                pct_map[name] = float(row.get('COCO_PCT') or 0)

    # EY alias
    if 'EY' not in pct_map and 'Ernst & Young (EY)' in pct_map:
        pct_map['EY'] = pct_map['Ernst & Young (EY)']
        wow_map['EY'] = wow_map.get('Ernst & Young (EY)')

    partner_items = []
    for display_name, data_key in HEATMAP_PARTNERS:
        pct = pct_map.get(data_key, pct_map.get(display_name, 0))
        wow = wow_map.get(data_key, wow_map.get(display_name))
        target = _partner_target(data_key)
        partner_items.append((display_name, pct, wow, target))

    def tier_order(item):
        _, pct, _, target = item
        if pct >= target:     return (0, -pct)
        if pct >= target / 2: return (1, -pct)
        return (2, -pct)

    partner_items.sort(key=tier_order)

    tiles = []
    for display_name, pct, wow, target in partner_items:
        if pct >= target:
            bg, border, val_color = '#dcfce7', '1px solid #86efac', '#16a34a'
        elif pct >= target / 2:
            bg, border, val_color = '#fef3c7', '1px solid #fbbf24', '#d97706'
        else:
            bg, border, val_color = '#fee2e2', '1px solid #fca5a5', '#dc2626'

        # crossed = newly crossed target this week
        crossed = pct >= target and wow is not None and (pct - wow) < target

        wow_html = ''
        if wow is not None and wow != 0:
            if wow > 0:
                wow_html = f'<div style="font-size:9px;color:#16a34a;">&#9650; +{wow:.1f}pp</div>'
            else:
                wow_html = f'<div style="font-size:9px;color:#dc2626;">&#9660; {wow:.1f}pp</div>'

        star = ' &#9733;' if wow is not None and wow != 0 else ''
        target_label = f'<div style="font-size:8px;color:#9ca3af;">goal {target}%</div>'
        tiles.append(
            f'<td style="background:{bg};border:{border};border-radius:6px;'
            f'padding:8px 4px;text-align:center;width:20%;vertical-align:top;">'
            f'<div style="font-size:11px;font-weight:700;white-space:nowrap;">{display_name}{star}</div>'
            f'<div style="font-size:17px;font-weight:900;color:{val_color};">{pct:.0f}%</div>'
            f'{target_label}'
            f'{wow_html}'
            f'</td>'
        )

    row_htmls = []
    for i in range(0, len(tiles), 5):
        chunk = tiles[i:i+5]
        while len(chunk) < 5:
            chunk.append('<td style="width:20%;"></td>')
        row_htmls.append(f'<tr style="vertical-align:top;">{"" .join(chunk)}</tr>')

    n_partners = len(HEATMAP_PARTNERS)
    legend_row = (
        '<tr><td colspan="5" style="padding:0 0 8px 0;font-size:11px;">'
        '<span style="background:#dcfce7;color:#16a34a;padding:3px 9px;border-radius:4px;font-weight:700;">&#9632; At/above goal</span>&nbsp;'
        '<span style="background:#fef3c7;color:#d97706;padding:3px 9px;border-radius:4px;font-weight:700;">&#9632; 50&#8211;99% of goal</span>&nbsp;'
        '<span style="background:#fee2e2;color:#dc2626;padding:3px 9px;border-radius:4px;font-weight:700;">&#9632; &lt;50% of goal</span>&nbsp;'
        '<span style="color:#0369a1;font-weight:700;">&#9733; = WoW change</span>'
        '</td></tr>'
    )

    return (
        '<div style="margin:14px 0;">'
        f'<div style="font-size:13px;font-weight:700;margin-bottom:8px;">Partner OKR Heat Map &#8212; All {n_partners} (GSI/NOAM goal=75% &middot; APJ/EMEA goal=50% &middot; &#9733; = WoW change)</div>'
        '<table width="100%" cellpadding="6" cellspacing="4" style="border-collapse:separate;table-layout:fixed;">'
        f'{legend_row}{" ".join(row_htmls)}'
        '</table></div>'
    )


def generate_trend_chart_html(trend_data: list) -> str:
    """Gmail-safe 4-week CoCo adoption % bar chart with 75% reference line."""
    if not trend_data:
        return ''

    ZONE_H = 40
    CHART_H = ZONE_H * 2
    BAR_W = 88
    GAP = 24
    NB = 'border:none;outline:none;'

    n = len(trend_data)
    n_cols = 2 * n - 1
    chart_w = n * BAR_W + (n - 1) * GAP
    total_w = chart_w + 35

    current_pct = trend_data[-1][1]
    if n >= 2:
        arrow = '&#9650;' if trend_data[-1][1] > trend_data[-2][1] else (
                '&#9660;' if trend_data[-1][1] < trend_data[-2][1] else '&#8212;')
    else:
        arrow = '&#8212;'
    pct_color = '#16a34a' if current_pct >= 75 else ('#f59e0b' if current_pct >= 30 else '#dc2626')

    def bar_fill(i):
        return '#16a34a' if i == n - 1 else '#29B5E8'

    label_cells, above_cells, below_cells, date_cells = [], [], [], []

    for i, (label, pct) in enumerate(trend_data):
        bar_h = max(2, int(CHART_H * pct / 100))
        bar_below = min(bar_h, ZONE_H)
        bar_above = max(0, bar_h - ZONE_H)
        spacer_h = ZONE_H - bar_below
        fill = bar_fill(i)

        if i > 0:
            for lst in (label_cells, date_cells):
                lst.append(f'<td width="{GAP}" style="width:{GAP}px;{NB}"></td>')
            above_cells.append(f'<td width="{GAP}" bgcolor="#ffffff" style="width:{GAP}px;background-color:#ffffff;font-size:0;line-height:0;{NB}">&nbsp;</td>')
            below_cells.append(f'<td width="{GAP}" style="width:{GAP}px;font-size:0;line-height:0;{NB}">&nbsp;</td>')

        label_cells.append(f'<td width="{BAR_W}" align="center" style="width:{BAR_W}px;text-align:center;font-size:12px;font-weight:bold;color:{fill};padding-bottom:4px;{NB}">{pct:.1f}%</td>')

        if bar_above > 0:
            gs = ZONE_H - bar_above
            inner = (f'<table width="{BAR_W}" border="0" cellpadding="0" cellspacing="0" style="width:{BAR_W}px;border-collapse:collapse;">'
                     f'<tr><td width="{BAR_W}" height="{gs}" bgcolor="#ffffff" style="width:{BAR_W}px;height:{gs}px;background-color:#ffffff;font-size:0;line-height:0;{NB}">&nbsp;</td></tr>'
                     f'<tr><td width="{BAR_W}" height="{bar_above}" bgcolor="{fill}" style="width:{BAR_W}px;height:{bar_above}px;background-color:{fill};font-size:0;line-height:0;{NB}">&nbsp;</td></tr>'
                     f'</table>')
            above_cells.append(f'<td width="{BAR_W}" height="{ZONE_H}" bgcolor="#ffffff" valign="bottom" style="width:{BAR_W}px;height:{ZONE_H}px;background-color:#ffffff;vertical-align:bottom;padding:0;{NB}">{inner}</td>')
        else:
            above_cells.append(f'<td width="{BAR_W}" height="{ZONE_H}" bgcolor="#ffffff" style="width:{BAR_W}px;height:{ZONE_H}px;background-color:#ffffff;font-size:0;line-height:0;{NB}">&nbsp;</td>')

        inner_below = f'<table width="{BAR_W}" border="0" cellpadding="0" cellspacing="0" style="width:{BAR_W}px;border-collapse:collapse;">'
        if spacer_h > 0:
            inner_below += f'<tr><td width="{BAR_W}" height="{spacer_h}" bgcolor="#ffffff" style="width:{BAR_W}px;height:{spacer_h}px;background-color:#ffffff;font-size:0;line-height:0;{NB}">&nbsp;</td></tr>'
        inner_below += (f'<tr><td width="{BAR_W}" height="{bar_below}" bgcolor="{fill}" style="width:{BAR_W}px;height:{bar_below}px;background-color:{fill};font-size:0;line-height:0;{NB}">&nbsp;</td></tr></table>')
        below_cells.append(f'<td width="{BAR_W}" height="{ZONE_H}" valign="bottom" style="width:{BAR_W}px;height:{ZONE_H}px;vertical-align:bottom;padding:0;{NB}">{inner_below}</td>')

        date_cells.append(f'<td width="{BAR_W}" align="center" style="width:{BAR_W}px;text-align:center;font-size:10px;color:#374151;padding-top:6px;{NB}">{label}</td>')

    lbl_col_e = f'<td width="35" style="width:35px;{NB}"></td>'
    lbl_col_w = f'<td width="35" bgcolor="#ffffff" style="width:35px;background-color:#ffffff;font-size:0;line-height:0;{NB}">&nbsp;</td>'

    row0 = '<tr>' + ''.join(label_cells) + lbl_col_e + '</tr>'
    row1 = '<tr>' + ''.join(above_cells) + lbl_col_w + '</tr>'
    row2 = (f'<tr><td colspan="{n_cols}" height="2" style="height:2px;border-bottom:2px dashed #dc2626;font-size:0;line-height:0;"></td>'
            f'<td width="35" height="2" style="width:35px;height:2px;border-bottom:2px dashed #dc2626;padding:0 0 2px 4px;font-size:10px;color:#dc2626;font-weight:bold;vertical-align:bottom;white-space:nowrap;">75%</td></tr>')
    row3 = '<tr>' + ''.join(below_cells) + lbl_col_e + '</tr>'
    row4 = f'<tr><td colspan="{n_cols + 1}" height="2" bgcolor="#d1d5db" style="height:2px;background-color:#d1d5db;font-size:0;line-height:0;">&nbsp;</td></tr>'
    row5 = '<tr>' + ''.join(date_cells) + lbl_col_e + '</tr>'

    chart_table = (f'<table width="{total_w}" border="0" cellpadding="0" cellspacing="0" style="width:{total_w}px;border-collapse:collapse;">'
                   f'{row0}{row1}{row2}{row3}{row4}{row5}</table>')

    return (
        '<table width="600" border="0" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif;margin:16px 0;border:1px solid #e5e7eb;">'
        '<tr><td style="padding:12px 16px;background-color:#f9fafb;border-bottom:1px solid #e5e7eb;">'
        f'<span style="font-size:13px;font-weight:bold;color:#111827;">&#128200; CoCo Adoption % &#8212; {n}-Week Trend</span>'
        f'&nbsp;&nbsp;<span style="font-size:12px;color:{pct_color};font-weight:bold;">Current: {current_pct:.1f}% {arrow}</span>'
        '</td></tr>'
        f'<tr><td style="padding:8px 16px 8px;background-color:#ffffff;">{chart_table}'
        '<table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top:6px;">'
        '<tr><td style="font-size:10px;color:#6b7280;padding-top:2px;">'
        '&#8212;&#8212; Dashed red = 75% OKR target &nbsp;&middot;&nbsp; <span style="color:#16a34a;font-weight:bold;">&#9646;</span> = current week'
        '</td></tr></table></td></tr></table>'
    )


def generate_partners_target_chart_html(trend_data: list, total_partners: int = 44) -> str:
    """Gmail-safe vertical bar chart — partners meeting goal% per week.
    trend_data: [(week_label, partners_at_target, total_partners), ...]
    """
    if not trend_data:
        return ''

    import pandas as _pd

    MAX    = total_partners
    CH     = 180       # chart height — tall enough so even low values are visible
    BW     = 76        # bar width
    GAP    = 20        # gap between bars
    YW     = 34        # y-axis column width
    NB     = 'border:none;outline:none;'
    BG     = '#f0f4f8' # bar container background (empty area above bar)

    _now_week = _pd.Timestamp.now().to_period('W').start_time.normalize()

    n             = len(trend_data)
    current_count = trend_data[-1][1]
    pct_color     = '#16a34a' if current_count >= MAX * 0.5 else ('#f59e0b' if current_count >= MAX * 0.3 else '#dc2626')

    if n >= 2:
        wow_delta = trend_data[-1][1] - trend_data[-2][1]
        arrow     = '&#9650;' if wow_delta > 0 else ('&#9660;' if wow_delta < 0 else '&#8212;')
        if wow_delta > 0:
            wow_label = f'&nbsp;&nbsp;<span style="font-size:11px;color:#16a34a;font-weight:bold;">+{wow_delta} new this week</span>'
        elif wow_delta < 0:
            wow_label = f'&nbsp;&nbsp;<span style="font-size:11px;color:#dc2626;font-weight:bold;">{wow_delta} this week</span>'
        else:
            wow_label = f'&nbsp;&nbsp;<span style="font-size:11px;color:#6b7280;">no change</span>'
    else:
        arrow     = '&#8212;'
        wow_label = ''

    # Y-axis: 3 ticks scaled to actual max (0, MAX//2, MAX)
    tick_mid    = MAX // 2
    tick_half_h = (CH - 3) // 2   # pixel spacing between tick rows

    y_axis = (
        f'<td width="{YW}" valign="top" style="width:{YW}px;vertical-align:top;padding:0;{NB}">'
        f'<table width="{YW}" border="0" cellpadding="0" cellspacing="0" style="width:{YW}px;border-collapse:collapse;">'
        f'<tr><td style="font-size:9px;color:#9ca3af;text-align:right;padding-right:5px;'
        f'white-space:nowrap;line-height:1.2;{NB}">{MAX}</td></tr>'
        f'<tr><td height="{tick_half_h}" style="height:{tick_half_h}px;{NB}"></td></tr>'
        f'<tr><td style="font-size:9px;color:#9ca3af;text-align:right;padding-right:5px;'
        f'white-space:nowrap;line-height:1.2;{NB}">{tick_mid}</td></tr>'
        f'<tr><td height="{tick_half_h}" style="height:{tick_half_h}px;{NB}"></td></tr>'
        f'<tr><td style="font-size:9px;color:#9ca3af;text-align:right;padding-right:5px;'
        f'white-space:nowrap;line-height:1.2;{NB}">0</td></tr>'
        f'</table></td>'
    )
    y_title_cell = (
        f'<td width="{YW}" style="width:{YW}px;font-size:9px;color:#9ca3af;'
        f'text-align:right;padding-right:5px;padding-bottom:2px;{NB}">Partners</td>'
    )

    label_cells, bar_cells, date_cells = [], [], []

    for i, (raw_label, count, _total) in enumerate(trend_data):
        try:
            ts    = _pd.Timestamp(raw_label)
            if ts.normalize() >= _now_week:
                label = 'Current Week'
            else:
                day    = ts.day
                suffix = 'th' if 11 <= day <= 13 else {1:'st',2:'nd',3:'rd'}.get(day % 10, 'th')
                label  = f"{ts.strftime('%b')} {day}{suffix}"
        except Exception:
            label = str(raw_label)

        is_current = (i == n - 1)
        fill       = '#16a34a' if is_current else '#29B5E8'
        bar_h      = max(8, int(CH * count / MAX))
        spacer_h   = CH - bar_h

        if i > 0:
            for lst in (label_cells, date_cells):
                lst.append(f'<td width="{GAP}" style="width:{GAP}px;{NB}"></td>')
            bar_cells.append(
                f'<td width="{GAP}" height="{CH}" '
                f'style="width:{GAP}px;height:{CH}px;font-size:0;line-height:0;{NB}">&nbsp;</td>'
            )

        # Value label above bar: "5" in bold, "/44" smaller gray
        label_cells.append(
            f'<td width="{BW}" align="center" style="width:{BW}px;text-align:center;'
            f'padding-bottom:4px;{NB}">'
            f'<span style="font-size:14px;font-weight:700;color:{fill};">{count}</span>'
            f'<span style="font-size:9px;color:#9ca3af;font-weight:400;">/{MAX}</span>'
            f'</td>'
        )

        # Bar: spacer on top (light bg) + filled bar at bottom
        inner = (
            f'<table width="{BW}" border="0" cellpadding="0" cellspacing="0" '
            f'style="width:{BW}px;border-collapse:collapse;">'
        )
        if spacer_h > 0:
            inner += (
                f'<tr><td width="{BW}" height="{spacer_h}" bgcolor="{BG}" '
                f'style="width:{BW}px;height:{spacer_h}px;background-color:{BG};'
                f'font-size:0;line-height:0;{NB}">&nbsp;</td></tr>'
            )
        inner += (
            f'<tr><td width="{BW}" height="{bar_h}" bgcolor="{fill}" '
            f'style="width:{BW}px;height:{bar_h}px;background-color:{fill};'
            f'font-size:0;line-height:0;{NB}">&nbsp;</td></tr>'
            f'</table>'
        )
        bar_cells.append(
            f'<td width="{BW}" height="{CH}" valign="bottom" '
            f'style="width:{BW}px;height:{CH}px;vertical-align:bottom;padding:0;{NB}">{inner}</td>'
        )

        date_cells.append(
            f'<td width="{BW}" align="center" '
            f'style="width:{BW}px;text-align:center;font-size:10px;color:#6b7280;'
            f'padding-top:5px;{NB}">{label}</td>'
        )

    bars_w  = n * BW + (n - 1) * GAP
    total_w = YW + bars_w

    row_title  = f'<tr>{y_title_cell}<td></td></tr>'
    row_labels = (f'<tr><td width="{YW}" style="width:{YW}px;{NB}"></td>'
                  f'<td><table border="0" cellpadding="0" cellspacing="0">'
                  f'<tr>{"".join(label_cells)}</tr></table></td></tr>')
    row_bars   = (f'<tr>{y_axis}'
                  f'<td><table border="0" cellpadding="0" cellspacing="0">'
                  f'<tr>{"".join(bar_cells)}</tr></table></td></tr>')
    row_axis   = (f'<tr><td colspan="2" height="2" bgcolor="#cbd5e1" '
                  f'style="height:2px;background-color:#cbd5e1;font-size:0;line-height:0;{NB}">&nbsp;</td></tr>')
    row_dates  = (f'<tr><td width="{YW}" style="width:{YW}px;{NB}"></td>'
                  f'<td><table border="0" cellpadding="0" cellspacing="0">'
                  f'<tr>{"".join(date_cells)}</tr></table></td></tr>')

    chart_table = (
        f'<table width="{total_w}" border="0" cellpadding="0" cellspacing="0" '
        f'style="width:{total_w}px;border-collapse:collapse;">'
        f'{row_title}{row_labels}{row_bars}{row_axis}{row_dates}'
        f'</table>'
    )

    return (
        '<table width="600" border="0" cellpadding="0" cellspacing="0" '
        'style="font-family:Arial,sans-serif;margin:16px 0;border:1px solid #e5e7eb;">'
        # Header
        '<tr><td style="padding:12px 16px;background-color:#f9fafb;border-bottom:1px solid #e5e7eb;">'
        f'<span style="font-size:13px;font-weight:bold;color:#111827;">'
        f'&#127942; Partners Meeting Goal% &#8212; {n}-Week Trend</span>'
        f'&nbsp;&nbsp;<span style="font-size:12px;color:{pct_color};font-weight:bold;">'
        f'Current: {current_count}/{MAX} {arrow}</span>'
        f'{wow_label}'
        '</td></tr>'
        # Chart
        f'<tr><td style="padding:10px 16px 6px;background-color:#ffffff;">{chart_table}</td></tr>'
        # Footer
        '<tr><td style="padding:2px 16px 10px;">'
        '<table width="100%" border="0" cellpadding="0" cellspacing="0"><tr>'
        '<td style="font-size:10px;color:#6b7280;">'
        f'# of {MAX} managed partners meeting their group goal '
        f'(GSI/NOAM &#8805;75%, APJ/EMEA &#8805;50%) &nbsp;&middot;&nbsp; '
        '<span style="color:#16a34a;font-weight:bold;">&#9646;</span> = current week'
        '</td></tr></table></td></tr>'
        '</table>'
    )
    if not trend_data:
        return ''

    import pandas as _pd

    MAX   = total_partners
    BAR_W = 360   # total bar track width in px
    ROW_H = 26    # bar height in px
    NB    = 'border:none;outline:none;'

    _now_week = _pd.Timestamp.now().to_period('W').start_time.normalize()

    n             = len(trend_data)
    current_count = trend_data[-1][1]
    pct_color     = '#16a34a' if current_count >= MAX * 0.5 else ('#f59e0b' if current_count >= MAX * 0.3 else '#dc2626')

    if n >= 2:
        wow_delta = trend_data[-1][1] - trend_data[-2][1]
        arrow     = '&#9650;' if wow_delta > 0 else ('&#9660;' if wow_delta < 0 else '&#8212;')
        if wow_delta > 0:
            wow_label = f'&nbsp;&nbsp;<span style="font-size:11px;color:#16a34a;font-weight:bold;">+{wow_delta} this week</span>'
        elif wow_delta < 0:
            wow_label = f'&nbsp;&nbsp;<span style="font-size:11px;color:#dc2626;font-weight:bold;">{wow_delta} this week</span>'
        else:
            wow_label = f'&nbsp;&nbsp;<span style="font-size:11px;color:#6b7280;">no change</span>'
    else:
        arrow     = '&#8212;'
        wow_label = ''

    rows_html = ''
    for i, (raw_label, count, _total) in enumerate(trend_data):
        try:
            ts = _pd.Timestamp(raw_label)
            label = 'Current Week' if ts.normalize() >= _now_week else (
                f"Week of {ts.strftime('%b')} {ts.day}"
                + ('th' if 11 <= ts.day <= 13 else {1:'st',2:'nd',3:'rd'}.get(ts.day % 10,'th'))
            )
        except Exception:
            label = str(raw_label)

        is_current = (i == n - 1)
        bar_color  = '#16a34a' if is_current else '#29B5E8'
        fill_w     = max(3, int(BAR_W * count / MAX))
        empty_w    = BAR_W - fill_w
        pct_str    = f'{round(count * 100.0 / MAX, 0):.0f}%'
        count_str  = f'{count}/{MAX}'

        rows_html += (
            f'<tr>'
            # Week label
            f'<td width="110" style="width:110px;font-size:11px;color:#555;'
            f'padding:5px 10px 5px 0;white-space:nowrap;vertical-align:middle;">{label}</td>'
            # Bar track
            f'<td width="{BAR_W}" style="width:{BAR_W}px;padding:5px 0;vertical-align:middle;">'
            f'<table width="{BAR_W}" border="0" cellpadding="0" cellspacing="0" '
            f'style="width:{BAR_W}px;border-collapse:collapse;border-radius:3px;overflow:hidden;">'
            f'<tr>'
            f'<td width="{fill_w}" height="{ROW_H}" bgcolor="{bar_color}" '
            f'style="width:{fill_w}px;height:{ROW_H}px;background-color:{bar_color};'
            f'font-size:0;line-height:0;{NB}">&nbsp;</td>'
            f'<td width="{empty_w}" height="{ROW_H}" bgcolor="#e9ecef" '
            f'style="width:{empty_w}px;height:{ROW_H}px;background-color:#e9ecef;'
            f'font-size:0;line-height:0;{NB}">&nbsp;</td>'
            f'</tr></table></td>'
            # Count + pct
            f'<td width="80" style="width:80px;font-size:12px;font-weight:700;'
            f'color:{bar_color};padding:5px 0 5px 10px;white-space:nowrap;vertical-align:middle;">'
            f'{count_str} <span style="font-weight:400;color:#9ca3af;font-size:10px;">({pct_str})</span></td>'
            f'</tr>'
        )

    return (
        '<table width="600" border="0" cellpadding="0" cellspacing="0" '
        'style="font-family:Arial,sans-serif;margin:16px 0;border:1px solid #e5e7eb;">'
        # Header
        '<tr><td style="padding:12px 16px;background-color:#f9fafb;border-bottom:1px solid #e5e7eb;">'
        f'<span style="font-size:13px;font-weight:bold;color:#111827;">&#127942; Partners Meeting Goal% &#8212; {n}-Week Trend</span>'
        f'&nbsp;&nbsp;<span style="font-size:12px;color:{pct_color};font-weight:bold;">'
        f'Current: {current_count}/{MAX} {arrow}</span>'
        f'{wow_label}'
        '</td></tr>'
        # Bar rows
        '<tr><td style="padding:10px 16px 8px;background-color:#ffffff;">'
        '<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;">'
        f'{rows_html}'
        '</table></td></tr>'
        # Footer
        '<tr><td style="padding:4px 16px 10px;">'
        '<table width="100%" border="0" cellpadding="0" cellspacing="0">'
        '<tr><td style="font-size:10px;color:#6b7280;">'
        f'# of {MAX} managed partners meeting their group goal '
        '(GSI/NOAM &#8805;75%, APJ/EMEA &#8805;50%) &nbsp;&middot;&nbsp;'
        '<span style="color:#16a34a;font-weight:bold;"> &#9646;</span> = current week'
        '</td></tr></table></td></tr>'
        '</table>'
    )


def inject_heatmap(html_email: str, heatmap_html: str) -> str:
    """Insert heat map after the Executive Summary bullet list."""
    import re
    match = re.compile(r'(EXECUTIVE SUMMARY.*?</ul>)', re.DOTALL | re.IGNORECASE).search(html_email)
    if match:
        pos = match.end()
        return html_email[:pos] + heatmap_html + html_email[pos:]
    okr_match = re.search(r'(<h[23][^>]*>[^<]*OKR PROGRESS[^<]*</h[23]>)', html_email, re.IGNORECASE)
    if okr_match:
        return html_email[:okr_match.start()] + heatmap_html + html_email[okr_match.start():]
    return html_email.replace('<body>', '<body>' + heatmap_html, 1)


def inject_after_okr_table(html_email: str, chart_html: str) -> str:
    """Insert trend chart immediately after the OKR PROGRESS table."""
    import re
    m = re.compile(r'(OKR PROGRESS.*?</table>)', re.DOTALL | re.IGNORECASE).search(html_email)
    if m:
        pos = m.end()
        return html_email[:pos] + chart_html + html_email[pos:]
    pos = html_email.find('</table>')
    if pos >= 0:
        return html_email[:pos + len('</table>')] + chart_html + html_email[pos + len('</table>'):]
    return html_email + chart_html


_VEL_CATS = ['AI / ML', 'Data Engineering', 'DWH / Migration', 'Platform / Governance', 'Apps / Data Sharing']
_VEL_MANAGED_SQL = (
    "'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',"
    "'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting',"
    "'7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai','Kipi.ai',"
    "'evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP',"
    "'LTM','LTI Mindtree','NTT DATA Group Corporation','phData, Inc.',"
    "'Slalom, LLC.','Squadron Data Inc','Tredence Inc.'"
)


def _compute_velocity_medians(conn):
    """Fetch and compute per-workload FY26/FY27 medians. Returns (fy26_map, fy27_map)."""
    raw = get_partner_velocity_data(conn, _VEL_MANAGED_SQL)
    df = raw.copy()
    df.columns = [c.upper() for c in df.columns]
    df['DAYS_FULL_CYCLE'] = pd.to_numeric(df['DAYS_FULL_CYCLE'], errors='coerce')
    df = df[df['DAYS_FULL_CYCLE'].notna() & df['WORKLOAD_CATEGORY'].notna() & df['FISCAL_QUARTER'].notna()]
    df['FISCAL_YEAR'] = df['FISCAL_QUARTER'].str[:4]
    med = df.groupby(['WORKLOAD_CATEGORY', 'FISCAL_YEAR'])['DAYS_FULL_CYCLE'].median().reset_index()
    fy26 = med[med['FISCAL_YEAR'] == 'FY26'].set_index('WORKLOAD_CATEGORY')['DAYS_FULL_CYCLE'].to_dict()
    fy27 = med[med['FISCAL_YEAR'] == 'FY27'].set_index('WORKLOAD_CATEGORY')['DAYS_FULL_CYCLE'].to_dict()
    return fy26, fy27


def generate_velocity_dumbbell_html(fy26_map: dict, fy27_map: dict) -> str:
    """Gmail-safe table-based dumbbell chart — same approach as the heatmap (pure tables, no SVG)."""
    _G  = '#34d399'
    _R  = '#f87171'
    _GR = '#94a3b8'

    cats = [c for c in _VEL_CATS if fy26_map.get(c) is not None and fy27_map.get(c) is not None]
    if not cats:
        return ''

    all_vals = [fy26_map[c] for c in cats] + [fy27_map[c] for c in cats]
    x_min = min(all_vals) * 0.90
    x_max = max(all_vals) * 1.08
    x_range = x_max - x_min or 1
    TRACK_W = 280  # total track width in px

    def track_px(v):
        return max(1.0, (v - x_min) / x_range * TRACK_W)

    rows = ''
    for cat in cats:
        v26 = fy26_map[cat]
        v27 = fy27_map[cat]
        delta = v27 - v26
        color = _G if delta < -3 else (_R if delta > 3 else _GR)
        arrow = f'&#8595; {abs(delta):.0f}d faster' if delta < -3 else (f'&#8593; {delta:.0f}d slower' if delta > 3 else '&#8776; flat')

        p26 = track_px(v26)
        p27 = track_px(v27)
        left_dot_x  = min(p26, p27)
        right_dot_x = max(p26, p27)
        line_w = max(right_dot_x - left_dot_x, 2)
        left_gap  = int(left_dot_x)
        right_gap = max(int(TRACK_W - right_dot_x - 12), 0)

        dot26_style = ('width:12px;height:12px;border-radius:6px;background:#cbd5e1;'
                       'border:2px solid #94a3b8;display:inline-block;vertical-align:middle;')
        dot27_style = (f'width:12px;height:12px;border-radius:6px;background:{color};'
                       f'border:2px solid {color};display:inline-block;vertical-align:middle;')

        left_dot_html  = (f'<td width="14" style="width:14px;padding:0;" align="center" valign="middle">'
                          f'<span style="{dot26_style if p26 <= p27 else dot27_style}"></span>'
                          f'<div style="font-size:9px;color:#64748b;text-align:center;">{(v26 if p26 <= p27 else v27):.0f}d</div>'
                          f'</td>')
        right_dot_html = (f'<td width="14" style="width:14px;padding:0;" align="center" valign="middle">'
                          f'<span style="{dot27_style if p26 <= p27 else dot26_style}"></span>'
                          f'<div style="font-size:9px;color:{color if p26<=p27 else "#64748b"};text-align:center;">{(v27 if p26 <= p27 else v26):.0f}d</div>'
                          f'</td>')

        track_cells = (
            f'<td width="{left_gap}" style="width:{left_gap}px;padding:0;"></td>'
            f'{left_dot_html}'
            f'<td width="{int(line_w)}" style="width:{int(line_w)}px;padding:0;" valign="middle">'
            f'<div style="height:3px;background:{color};"></div></td>'
            f'{right_dot_html}'
            f'<td width="{right_gap}" style="width:{right_gap}px;padding:0;"></td>'
        )

        rows += (
            f'<tr>'
            f'<td width="160" style="width:160px;font-size:12px;font-weight:700;color:#475569;'
            f'padding:6px 8px 6px 0;white-space:nowrap;">{cat}</td>'
            f'<td width="{TRACK_W}" style="width:{TRACK_W}px;padding:4px 0;">'
            f'<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
            f'<tr>{track_cells}</tr></table></td>'
            f'<td width="130" style="width:130px;font-size:12px;font-weight:700;color:{color};'
            f'padding:6px 0 6px 12px;white-space:nowrap;">{arrow}</td>'
            f'</tr>'
        )

    legend = (
        f'<tr><td colspan="3" style="padding:8px 0 0 0;font-size:11px;color:#64748b;">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:5px;'
        f'background:#cbd5e1;border:1px solid #94a3b8;vertical-align:middle;margin-right:4px;"></span>FY26&nbsp;&nbsp;'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:5px;'
        f'background:{_G};vertical-align:middle;margin-right:4px;"></span>FY27 faster&nbsp;&nbsp;'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:5px;'
        f'background:{_R};vertical-align:middle;margin-right:4px;"></span>FY27 slower'
        f'</td></tr>'
    )

    return (
        '<div style="margin:16px 0;font-family:Arial,sans-serif;">'
        '<div style="font-size:13px;font-weight:700;color:#29B5E8;margin-bottom:6px;">'
        'Partner Implementation Velocity by Workload &#8592; fewer days = faster</div>'
        f'<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
        f'{rows}{legend}'
        '</table>'
        '<p style="font-size:10px;color:#94a3b8;margin:6px 0 0 0;line-height:1.4;">'
        'FY26 vs FY27 Q1+Q2 &middot; Median days decision &#8594; go-live, grouped by workload type. '
        '<em>Workload categories AI-assigned from Salesforce descriptions (one category per use case).</em>'
        '</p></div>'
    )


def inject_velocity_chart(html_email: str, chart_html: str) -> str:
    """Insert dumbbell chart before USE CASE PATTERNS so the scorecard 75% sentence stays above."""
    import re
    # Primary: just before USE CASE PATTERNS heading (matches any h2/h3 containing those words)
    m = re.search(r'(<h[23][^>]*>[^<]*USE\s+CASE\s+PATTERN[^<]*</h[23]>)', html_email, re.IGNORECASE)
    if m:
        return html_email[:m.start()] + chart_html + html_email[m.start():]
    # Secondary: before NOTABLE WINS heading as fallback
    m2 = re.search(r'(<h[23][^>]*>[^<]*NOTABLE\s+WINS[^<]*</h[23]>)', html_email, re.IGNORECASE)
    if m2:
        return html_email[:m2.start()] + chart_html + html_email[m2.start():]
    # Last resort: after the last </table> in the body
    pos = html_email.rfind('</table>')
    if pos >= 0:
        end = pos + len('</table>')
        return html_email[:end] + chart_html + html_email[end:]
    return html_email


def md_to_html(md_text):
    html_body = markdown.markdown(md_text, extensions=['tables'])
    return f"""<html><head><style>
    body {{ font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
    th {{ background-color: #29B5E8; color: white; font-weight: bold; }}
    tr:nth-child(even) {{ background-color: #f9f9f9; }}
    h2 {{ color: #29B5E8; margin-top: 20px; border-bottom: 2px solid #29B5E8; padding-bottom: 4px; }}
    h3 {{ color: #29B5E8; }}
    strong {{ color: #333; }}
    ul {{ padding-left: 20px; }}
    li {{ margin-bottom: 4px; }}
</style></head><body>{html_body}</body></html>"""


conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])

st.title(":material/mail: Executive Email Summary")
filter_label = f"Region: {region}"
if selected_partners:
    filter_label += f" | Partners: {', '.join(selected_partners)}"
st.caption(f"AI-generated weekly summary for CoCo Use Case Intelligence | {filter_label}")

source_toggle = st.segmented_control("Use Case View", ["Overall", "PSE Confirmed", "Feature Flag"], default="Overall", key="email_source")
st.caption(f"Filters active: {source_toggle} use cases • {region} region")

def _apply_partner_filter(df, col='PARTNER_NAME'):
    """Filter DataFrame by sidebar multiselect partners."""
    if selected_partners and col in df.columns:
        from utils import resolve_partner_filter
        names = resolve_partner_filter(selected_partners)
        return df[df[col].isin(names)]
    return df

with st.spinner("Loading data..."):
    stats = get_summary_stats(conn, region=region, source=source_toggle)
    partner_data = get_email_summary_data(conn, region=region, source=source_toggle)
    stage_data = get_by_stage(conn, region=region, source=source_toggle)
    source_data = get_source_breakdown(conn, region=region)
    region_data = get_by_region(conn, source=source_toggle)
    type_patterns = get_use_case_type_patterns(conn, region=region, source=source_toggle)
    workload_data = get_workload_patterns(conn, region=region, source=source_toggle)
    competitive_data = get_competitive_landscape(conn, region=region, source=source_toggle)
    comment_data = get_comment_narratives(conn, region=region, source=source_toggle)
    partner_workloads = get_partner_workload_cross(conn, region=region, source=source_toggle)
    regional_themes = get_regional_themes(conn, source=source_toggle)
    coco_coverage = get_partner_coco_coverage(conn, region=region, include_account_coco=False, confidence=None)
    global_overview = get_adoption_overview(conn, '2026-08-01', '2026-10-31', include_account_coco=True, confidence='High')
    pipeline_wow = get_pipeline_wow(conn)
    gsi_wow = get_gsi_wow(conn)
    noam_si_wow = get_noam_si_wow(conn)
    adoption_wow_data = get_coco_final_wow(conn, partners=MANAGED_PARTNERS, gsi_global=True, gsi_names=_GSI_NAMES)

    # Managed partner stage EACV breakdown — Q3 ONLY (Aug 1 - Oct 31, 2026)
    managed_partners_sql = "','".join(MANAGED_PARTNERS)
    Q3_START = '2026-08-01'
    Q3_END = '2026-10-31'
    Q2_START = Q3_START  # alias so existing references still work
    Q2_END = Q3_END

    recent_wins_data = get_recent_wins(conn, MANAGED_PARTNERS, Q3_START, Q3_END)

    # Q3 Credit consumption — same as OKR Coverage: IS_COCO_FINAL accounts only
    # computed after managed_bulk_conf IS_COCO_FINAL is resolved (see below)
    credit_data = pd.DataFrame()

    # GSI global coverage — all regions (not NoAM-filtered), using IS_COCO_FINAL
    GSI_LIST = ['Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
                'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting']
    gsi_bulk_conf = get_bulk_confidence_scores(conn, GSI_LIST, Q3_START, Q3_END)
    if len(gsi_bulk_conf) > 0:
        gsi_bulk_conf['IS_COCO_FINAL'] = (
            (gsi_bulk_conf['IS_COCO'] == True) |
            (gsi_bulk_conf['CONFIDENCE_BAND'].isin(['High']))
        )
        gsi_bulk_conf['REGION'] = gsi_bulk_conf['THEATER_NAME'].map(
            lambda t: 'NoAM' if t in ('AMSExpansion','USMajors','AMSAcquisition','USPubSec')
                      else ('EMEA' if t == 'EMEA' else ('APJ' if t == 'APJ' else 'Other'))
        )
        gsi_global_data = gsi_bulk_conf.groupby('REGION').agg(
            TOTAL_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
        ).reset_index()
        gsi_global_data['COCO_PCT'] = round(
            gsi_global_data['COCO_UCS'] * 100.0 / gsi_global_data['TOTAL_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        gsi_global_data = gsi_global_data.sort_values('TOTAL_UCS', ascending=False)
    else:
        gsi_global_data = pd.DataFrame(columns=['REGION','TOTAL_UCS','COCO_UCS','COCO_PCT','TOTAL_EACV'])

    managed_stage_data = conn.query(f"""
        SELECT 
            CASE 
                WHEN USE_CASE_STAGE IN ('3 - Technical / Business Validation') THEN 'Validation (3)'
                WHEN USE_CASE_STAGE = '4 - Use Case Won / Migration Plan' THEN 'Won (4)'
                WHEN USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete') THEN 'Implementation (5-6)'
                WHEN USE_CASE_STAGE = '7 - Deployed' THEN 'Deployed (7)'
            END AS STAGE_GROUP,
            COUNT(*) AS UC_COUNT,
            COALESCE(SUM(USE_CASE_EACV), 0) AS TOTAL_EACV
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES uc
        WHERE uc.PARTNER_NAME IN ('{managed_partners_sql}')
        AND uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation','4 - Use Case Won / Migration Plan','5 - Implementation In Progress','6 - Implementation Complete','7 - Deployed')
        AND (
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{Q3_START}' AND uc.DECISION_DATE <= '{Q3_END}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{Q3_START}' AND uc.GO_LIVE_DATE <= '{Q3_END}')
        )
        -- GSIs: all theaters (global); NOAM RSIs: NoAM only; APJ/EMEA RSIs: their respective regions
        AND (
            uc.PARTNER_NAME IN ('Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
                                'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting')
            OR uc.THEATER_NAME IN ('AMSExpansion','USMajors','AMSAcquisition','USPubSec')
            OR uc.REGION_NAME IN ('Japan','Korea','ASEAN','ANZ','India','CentralEMEA','SouthEMEA','UK')
        )
        GROUP BY STAGE_GROUP
        ORDER BY STAGE_GROUP
    """)

    # Fetch per-use-case confidence scores for all managed partners (High confidence = score >= 75)
    # Executive email always uses: account-level CoCo ON, High confidence only
    _EMAIL_BANDS = ['High']
    managed_bulk_conf = get_bulk_confidence_scores(conn, tuple(sorted(MANAGED_PARTNERS)), Q3_START, Q3_END)
    # GSIs: global (all theaters); NOAM RSIs: NoAM only; APJ/EMEA RSIs: geo-restricted.
    _NOAM_THEATERS = ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec')
    if len(managed_bulk_conf) > 0:
        _gsi_rows = managed_bulk_conf[managed_bulk_conf['PARTNER_NAME'].isin(_GSI_NAMES)].copy()
        _noam_rsi_rows = managed_bulk_conf[
            managed_bulk_conf['PARTNER_NAME'].isin(_NOAM_RSI_NAMES_EMAIL) &
            managed_bulk_conf['THEATER_NAME'].isin(_NOAM_THEATERS)
        ].copy()
        _apj_rsi_rows = managed_bulk_conf[managed_bulk_conf['PARTNER_NAME'].isin(_APJ_RSI_NAMES_EMAIL)].copy()
        if 'REGION_NAME' in _apj_rsi_rows.columns and len(_apj_rsi_rows) > 0:
            _apj_rsi_rows['_c'] = _apj_rsi_rows['PARTNER_NAME'].map({k: v[1] for k, v in APJ_RSI_REGION_MAP.items()})
            _apj_rsi_rows = _apj_rsi_rows[_apj_rsi_rows['REGION_NAME'] == _apj_rsi_rows['_c']].drop(columns=['_c'])
        _emea_rsi_rows = managed_bulk_conf[managed_bulk_conf['PARTNER_NAME'].isin(_EMEA_RSI_NAMES_EMAIL)].copy()
        if 'REGION_NAME' in _emea_rsi_rows.columns and len(_emea_rsi_rows) > 0:
            _emea_rsi_rows['_c'] = _emea_rsi_rows['PARTNER_NAME'].map({k: v[1] for k, v in EMEA_RSI_REGION_MAP.items()})
            _emea_rsi_rows = _emea_rsi_rows[_emea_rsi_rows['REGION_NAME'] == _emea_rsi_rows['_c']].drop(columns=['_c'])
        # Merge aliases into canonical names
        _gsi_rows['PARTNER_NAME'] = _gsi_rows['PARTNER_NAME'].replace({'Ernst & Young (EY)': 'EY', 'IBM Consulting': 'IBM'})
        _noam_rsi_rows['PARTNER_NAME'] = _noam_rsi_rows['PARTNER_NAME'].replace({'Kipi.ai': 'kipi.ai', 'LTI Mindtree': 'LTM'})
        # Tag group for each row
        _gsi_rows['_GROUP'] = 'GSI'
        _noam_rsi_rows['_GROUP'] = 'NOAM RSI'
        _apj_rsi_rows['_GROUP'] = 'APJ RSI'
        _emea_rsi_rows['_GROUP'] = 'EMEA RSI'
        managed_bulk_conf = pd.concat([_gsi_rows, _noam_rsi_rows, _apj_rsi_rows, _emea_rsi_rows], ignore_index=True)

    if len(managed_bulk_conf) > 0:
        managed_bulk_conf['IS_COCO_FINAL'] = (
            (managed_bulk_conf['IS_COCO'] == True) |
            (managed_bulk_conf['CONFIDENCE_BAND'].isin(_EMAIL_BANDS))
        )
        managed_bulk_conf['REGION'] = managed_bulk_conf['THEATER_NAME'].map(
            lambda t: 'NoAM' if t in ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec')
                      else 'EMEA' if t == 'EMEA' else 'APJ' if t == 'APJ' else 'Other'
        )
        coco_mask = managed_bulk_conf['IS_COCO_FINAL']

        # Q2 Credit consumption — same approach as OKR Coverage page:
        # fetch account-level credits for IS_COCO_FINAL accounts, aggregate per partner
        _coco_final_acct_df = managed_bulk_conf[coco_mask][['PARTNER_NAME', 'ACCOUNT_NAME_UPPER']].drop_duplicates()
        _coco_accts_email = tuple(_coco_final_acct_df['ACCOUNT_NAME_UPPER'].dropna().unique())
        if _coco_accts_email:
            _acct_usage = get_account_coco_credits(conn, _coco_accts_email, Q3_START)
            if len(_acct_usage) > 0:
                _usage_joined = _coco_final_acct_df.merge(_acct_usage, on='ACCOUNT_NAME_UPPER', how='left')
                credit_data = _usage_joined.groupby('PARTNER_NAME').agg(
                    Q2_TOTAL_CREDITS=('Q2_CREDITS', 'sum'),
                    Q2_TOKENS=('Q2_TOKENS', 'sum'),
                    LAST7_CREDITS=('LAST7_CREDITS', 'sum'),
                    PRIOR7_CREDITS=('PRIOR7_CREDITS', 'sum'),
                    LAST7_TOKENS=('LAST7_TOKENS', 'sum'),
                    ACCTS_WITH_USAGE=('Q2_CREDITS', lambda x: (x > 0).sum()),
                ).reset_index()
                # Portfolio WoW% — sum-based, matches Deep Dive header exactly
                credit_data['WOW_PCT'] = (
                    (credit_data['LAST7_CREDITS'] - credit_data['PRIOR7_CREDITS'])
                    / credit_data['PRIOR7_CREDITS'].replace(0, float('nan'))
                    * 100
                )

        # Q2 headline stats
        managed_q2_stats = pd.DataFrame([{
            'TOTAL_UCS': len(managed_bulk_conf),
            'COCO_UCS': int(coco_mask.sum()),
            'TOTAL_EACV': managed_bulk_conf['USE_CASE_EACV'].sum() or 0,
            'COCO_EACV': managed_bulk_conf.loc[coco_mask, 'USE_CASE_EACV'].sum() or 0,
            'ACTIVE_PARTNERS': managed_bulk_conf['PARTNER_NAME'].nunique(),
            'COCO_DEPLOYED': int(managed_bulk_conf[
                coco_mask & (managed_bulk_conf['USE_CASE_STAGE'] == '7 - Deployed')
            ].shape[0]),
        }])

        # Q2 CoCo coverage by region
        reg_agg = managed_bulk_conf.groupby('REGION').agg(
            TOTAL_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            PARTNER_COUNT=('PARTNER_NAME', 'nunique'),
        ).reset_index()
        reg_agg['COCO_PCT'] = round(
            reg_agg['COCO_UCS'] * 100.0 / reg_agg['TOTAL_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        managed_q2_regional = reg_agg.sort_values('TOTAL_UCS', ascending=False)

        # Avg CoCo% per partner per region
        pstats = managed_bulk_conf.groupby(['REGION', 'PARTNER_NAME']).agg(
            TOTAL_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
        ).reset_index()
        pstats['COCO_PCT'] = round(
            pstats['COCO_UCS'] * 100.0 / pstats['TOTAL_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        managed_q2_partner_avg = pstats.groupby('REGION').agg(
            AVG_COCO_PCT_PER_PARTNER=('COCO_PCT', 'mean')
        ).reset_index()
        managed_q2_partner_avg['AVG_COCO_PCT_PER_PARTNER'] = managed_q2_partner_avg['AVG_COCO_PCT_PER_PARTNER'].round(1)

        # Per-partner breakdown
        p_coco_eacv = managed_bulk_conf.loc[coco_mask].groupby('PARTNER_NAME')['USE_CASE_EACV'].sum().reset_index()
        p_coco_eacv.columns = ['PARTNER_NAME', 'COCO_EACV']
        managed_q2_partners = managed_bulk_conf.groupby('PARTNER_NAME').agg(
            TOTAL_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
            AI=('TECHNICAL_USE_CASE', lambda x: x.str.contains('AI', case=False, na=False).sum()),
            DE=('TECHNICAL_USE_CASE', lambda x: x.str.contains('DE:', case=False, na=False).sum()),
            ANALYTICS=('TECHNICAL_USE_CASE', lambda x: x.str.contains('Analytics', case=False, na=False).sum()),
        ).reset_index()
        managed_q2_partners = managed_q2_partners.merge(p_coco_eacv, on='PARTNER_NAME', how='left')
        managed_q2_partners['COCO_EACV'] = managed_q2_partners['COCO_EACV'].fillna(0)
        managed_q2_partners['COCO_PCT'] = round(
            managed_q2_partners['COCO_UCS'] * 100.0 / managed_q2_partners['TOTAL_UCS'].replace(0, float('nan')), 0
        ).fillna(0)
        managed_q2_partners = managed_q2_partners.sort_values('TOTAL_EACV', ascending=False)
    else:
        managed_q2_stats = pd.DataFrame([{'TOTAL_UCS': 0, 'COCO_UCS': 0, 'TOTAL_EACV': 0, 'COCO_EACV': 0, 'ACTIVE_PARTNERS': 0, 'COCO_DEPLOYED': 0}])
        managed_q2_regional = pd.DataFrame(columns=['REGION', 'TOTAL_UCS', 'COCO_UCS', 'COCO_PCT', 'PARTNER_COUNT'])
        managed_q2_partner_avg = pd.DataFrame(columns=['REGION', 'AVG_COCO_PCT_PER_PARTNER'])
        managed_q2_partners = pd.DataFrame(columns=['PARTNER_NAME', 'TOTAL_UCS', 'COCO_UCS', 'COCO_PCT', 'TOTAL_EACV', 'AI', 'DE', 'ANALYTICS'])

# Executive email always uses MANAGED_PARTNERS list, ignoring sidebar partner filter
# Auto-save IS_COCO_FINAL (Def C) weekly snapshot — idempotent, first load each week triggers save
if len(managed_bulk_conf) > 0:
    try:
        _saved = save_coco_final_snapshot(conn, managed_bulk_conf)
        if _saved:
            st.toast("Weekly IS_COCO_FINAL snapshot saved", icon="✅")
    except Exception as _e:
        st.toast(f"Snapshot save skipped: {_e}", icon="⚠️")
# Filter to managed partners only for executive email context
partner_data = partner_data[partner_data['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
comment_data = comment_data[comment_data['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
partner_workloads = partner_workloads[partner_workloads['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
coco_coverage = coco_coverage[coco_coverage['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
if 'PARTNER_NAME' in regional_themes.columns:
    regional_themes = regional_themes[regional_themes['PARTNER_NAME'].isin(MANAGED_PARTNERS)]

# Override coco_coverage with High-confidence scoring (same logic as OKR Coverage)
if len(coco_coverage) > 0 and len(managed_bulk_conf) > 0:
    bulk_for_cov = managed_bulk_conf[managed_bulk_conf['PARTNER_NAME'].isin(coco_coverage['PARTNER_NAME'])].copy()
    if region and region != 'Global':
        region_theaters = {'NoAM': ['AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec'], 'EMEA': ['EMEA'], 'APJ': ['APJ']}
        bulk_for_cov = bulk_for_cov[bulk_for_cov['THEATER_NAME'].isin(region_theaters.get(region, []))]
    if len(bulk_for_cov) > 0:
        cov_coco_eacv = bulk_for_cov[bulk_for_cov['IS_COCO_FINAL']].groupby('PARTNER_NAME')['USE_CASE_EACV'].sum().reset_index()
        cov_coco_eacv.columns = ['PARTNER_NAME', 'COCO_EACV']
        cov_summary = bulk_for_cov.groupby('PARTNER_NAME').agg(
            TOTAL_PARTNER_UCS=('USE_CASE_ID', 'count'),
            COCO_UCS=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
        ).reset_index()
        cov_summary = cov_summary.merge(cov_coco_eacv, on='PARTNER_NAME', how='left')
        cov_summary['COCO_EACV'] = cov_summary['COCO_EACV'].fillna(0)
        cov_summary['COCO_PCT'] = round(
            cov_summary['COCO_UCS'] * 100.0 / cov_summary['TOTAL_PARTNER_UCS'].replace(0, float('nan')), 1
        ).fillna(0)
        coco_coverage = coco_coverage[['PARTNER_NAME']].merge(cov_summary, on='PARTNER_NAME', how='left').fillna(0)
        coco_coverage['COCO_PCT'] = coco_coverage['COCO_PCT'].astype(float)
        coco_coverage[['TOTAL_PARTNER_UCS', 'COCO_UCS']] = coco_coverage[['TOTAL_PARTNER_UCS', 'COCO_UCS']].astype(int)

if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

# Recompute headline stats from Q2 managed partner data
q2 = managed_q2_stats.iloc[0]
managed_total_ucs = int(q2['TOTAL_UCS'])
managed_coco_ucs = int(q2['COCO_UCS'])
managed_total_eacv = q2['TOTAL_EACV'] or 0
managed_coco_eacv = q2['COCO_EACV'] or 0
managed_total_partners = int(q2['ACTIVE_PARTNERS'])
managed_coco_deployed = int(q2['COCO_DEPLOYED'])
managed_coco_pct = round(managed_coco_ucs * 100.0 / managed_total_ucs, 1) if managed_total_ucs > 0 else 0
managed_inactive_partners = len(MANAGED_PARTNERS) - managed_total_partners
managed_inactive_names = [p for p in MANAGED_PARTNERS if p not in partner_data['PARTNER_NAME'].values]

# Compute full per-partner OKR summary — count each partner against their group target
# GSI/NOAM RSI target = 75%; APJ/EMEA RSI target = 50%
if len(managed_bulk_conf) > 0 and '_GROUP' in managed_bulk_conf.columns:
    _full_partner_summary = managed_bulk_conf.groupby(['PARTNER_NAME', '_GROUP']).agg(
        TOTAL_UCS=('USE_CASE_ID', 'count'),
        COCO_UCS=('IS_COCO_FINAL', 'sum'),
    ).reset_index()
    _full_partner_summary['COCO_PCT'] = round(
        _full_partner_summary['COCO_UCS'] * 100.0 / _full_partner_summary['TOTAL_UCS'].replace(0, float('nan')), 1
    ).fillna(0)
    _full_partner_summary['TARGET'] = _full_partner_summary['_GROUP'].map(
        {'GSI': 75, 'NOAM RSI': 75, 'APJ RSI': 50, 'EMEA RSI': 50}
    ).fillna(75)
    _full_partner_summary['MEETS_GOAL'] = _full_partner_summary['COCO_PCT'] >= _full_partner_summary['TARGET']
    partners_meeting_75 = int(_full_partner_summary['MEETS_GOAL'].sum())
    total_managed_partner_count = len(_full_partner_summary)
    partners_meeting_list = ', '.join(_full_partner_summary[_full_partner_summary['MEETS_GOAL']]['PARTNER_NAME'].tolist())
    partners_below_50 = int((~_full_partner_summary['MEETS_GOAL']).sum())
    _below_df = _full_partner_summary[~_full_partner_summary['MEETS_GOAL']].sort_values('COCO_PCT', ascending=False)
    _below_str = '; '.join(f"{r.PARTNER_NAME} {r.COCO_PCT:.1f}% (goal {int(r.TARGET)}%)" for _, r in _below_df.iterrows())
else:
    partners_meeting_75 = 0
    partners_meeting_list = 'N/A'
    partners_below_50 = managed_total_partners
    _below_str = 'N/A'
    total_managed_partner_count = len(MANAGED_PARTNERS)

# Inject context for Ask AI
st.session_state.ask_ai_context = (
    f"Current page: Executive Email. GSI + NOAM/APJ/EMEA RSI managed partners. Period: FY27 Q3 (Aug–Oct 2026).\n"
    f"Partners meeting goal (75%/50%): {partners_meeting_75}/44. Partners at goal: {partners_meeting_list}.\n"
    f"Partners below 75% (closest first): {_below_str}."
)

# Upsert current week's count into COCO_OKR_TARGET_WEEKLY (freezes automatically when week rolls over)
try:
    save_okr_target_count(conn, partners_meeting_75, 44)
except Exception as _e:
    import traceback; traceback.print_exc()
    st.toast(f"OKR trend save skipped: {_e}", icon="⚠️")
get_partners_at_target_trend_4w.clear()  # always refresh trend cache

# Fetch trend data after upsert so current week's value is always fresh
trend_data = get_partners_at_target_trend_4w(
    conn, tuple(MANAGED_PARTNERS),
    gsi_names=tuple(_GSI_NAMES)
)

s = stats.iloc[0]
go = global_overview.iloc[0]



coverage_map = {}
if len(coco_coverage) > 0:
    for _, cv in coco_coverage.iterrows():
        coverage_map[cv['PARTNER_NAME']] = {
            'total': int(cv['TOTAL_PARTNER_UCS']),
            'coco': int(cv['COCO_UCS']),
            'pct': float(cv['COCO_PCT'] or 0)
        }

_credit_lookup = {}
if len(credit_data) > 0:
    for _, cr in credit_data.iterrows():
        _credit_lookup[str(cr['PARTNER_NAME'])] = {
            'credits':       cr.get('Q2_TOTAL_CREDITS', 0) or 0,
            'tokens':        cr.get('Q2_TOKENS', 0) or 0,
            'last7_credits': cr.get('LAST7_CREDITS', 0) or 0,
            'last7_tokens':  cr.get('LAST7_TOKENS', 0) or 0,
            'accts_w_usage': int(cr.get('ACCTS_WITH_USAGE', 0) or 0),
            'wow_pct':       cr.get('WOW_PCT', None),
        }

def _build_group_ctx(group_df, group_label, credit_lkp, wow_lkp):
    """Build partner context string for a single group (GSI, NOAM RSI, APJ RSI, EMEA RSI)."""
    ctx = f"\n=== {group_label} ===\n"
    if len(group_df) == 0:
        return ctx + "  (no data)\n"
    for _, p in group_df.iterrows():
        eacv = p.get('TOTAL_EACV', 0) or 0
        cr = credit_lkp.get(p['PARTNER_NAME'], {})
        credits = cr.get('credits', 0)
        tokens  = cr.get('tokens', 0)
        last7   = cr.get('last7_credits', 0)
        accts   = cr.get('accts_w_usage', 0)
        wow_pct = cr.get('wow_pct', None)
        wow_str = f"{wow_pct:+.1f}%" if wow_pct is not None and pd.notna(wow_pct) else "-"
        lv = wow_lkp.get(p['PARTNER_NAME'], {})
        wow_coco_pct = f"{float(lv.get('WOW_COCO_PCT', 0) or 0):+.1f}%" if pd.notna(lv.get('WOW_COCO_PCT', None)) else "-"
        wow_coco_ucs = f"{int(lv.get('WOW_COCO_UCS', 0) or 0):+d}" if pd.notna(lv.get('WOW_COCO_UCS', None)) else "-"
        ctx += (
            f"  {p['PARTNER_NAME']}: {int(p['TOTAL_UCS'])} UCs, {int(p['COCO_UCS'])} CoCo ({int(p['COCO_PCT'])}%), "
            f"${eacv/1000:.0f}K EACV, AI={int(p['AI'])}, DE={int(p['DE'])}, Analytics={int(p['ANALYTICS'])}, "
            f"Q3 Credits=${credits:,.0f}, Last 7d Credits=${last7:,.0f}, Q3 Tokens={_fmt_tokens(tokens)}, "
            f"7D Credits WoW%={wow_str}, CoCo% WoW={wow_coco_pct}, CoCo UCs WoW={wow_coco_ucs}\n"
        )
    return ctx

# Build WoW lookup from adoption_wow_data (partner rows)
_wow_lkp = {}
if len(adoption_wow_data) > 0:
    for _, _wr in adoption_wow_data[adoption_wow_data['PARTNER_NAME'].notna()].iterrows():
        _wow_lkp[str(_wr['PARTNER_NAME'])] = _wr.to_dict()

# Build group-level partner DataFrames from managed_q2_partners + _GROUP tag
_has_group = '_GROUP' in managed_bulk_conf.columns if len(managed_bulk_conf) > 0 else False

def _group_partners(group_tag):
    if not _has_group or len(managed_bulk_conf) == 0:
        return pd.DataFrame()
    _g = managed_bulk_conf[managed_bulk_conf['_GROUP'] == group_tag]
    if len(_g) == 0:
        return pd.DataFrame()
    _coco_eacv = _g[_g['IS_COCO_FINAL']].groupby('PARTNER_NAME')['USE_CASE_EACV'].sum().reset_index()
    _coco_eacv.columns = ['PARTNER_NAME', 'COCO_EACV']
    _agg = _g.groupby('PARTNER_NAME').agg(
        TOTAL_UCS=('USE_CASE_ID', 'count'),
        COCO_UCS=('IS_COCO_FINAL', 'sum'),
        TOTAL_EACV=('USE_CASE_EACV', 'sum'),
        AI=('TECHNICAL_USE_CASE', lambda x: x.str.contains('AI', case=False, na=False).sum()),
        DE=('TECHNICAL_USE_CASE', lambda x: x.str.contains('DE:', case=False, na=False).sum()),
        ANALYTICS=('TECHNICAL_USE_CASE', lambda x: x.str.contains('Analytics', case=False, na=False).sum()),
    ).reset_index()
    _agg = _agg.merge(_coco_eacv, on='PARTNER_NAME', how='left').fillna({'COCO_EACV': 0})
    _agg['COCO_PCT'] = (_agg['COCO_UCS'] * 100.0 / _agg['TOTAL_UCS'].replace(0, float('nan'))).round(0).fillna(0)
    return _agg.sort_values('TOTAL_EACV', ascending=False)

_gsi_partners_df  = _group_partners('GSI')
_noam_partners_df = _group_partners('NOAM RSI')
_apj_partners_df  = _group_partners('APJ RSI')
_emea_partners_df = _group_partners('EMEA RSI')

gsi_partner_ctx  = _build_group_ctx(_gsi_partners_df,  'GSI (Global)',    _credit_lookup, _wow_lkp)
noam_partner_ctx = _build_group_ctx(_noam_partners_df, 'NOAM RSI',        _credit_lookup, _wow_lkp)
apj_partner_ctx  = _build_group_ctx(_apj_partners_df,  'APJ RSI',         _credit_lookup, _wow_lkp)
emea_partner_ctx = _build_group_ctx(_emea_partners_df, 'EMEA RSI',        _credit_lookup, _wow_lkp)

# Combined context (kept for backward compatibility in data_context)
partner_ctx = gsi_partner_ctx + noam_partner_ctx + apj_partner_ctx + emea_partner_ctx

stage_ctx = ""
if len(managed_stage_data) > 0 and len(managed_bulk_conf) > 0:
    # Map USE_CASE_STAGE → STAGE_GROUP labels (same as managed_stage_data SQL)
    def _stage_group(s):
        if s == '3 - Technical / Business Validation':
            return 'Validation (3)'
        elif s == '4 - Use Case Won / Migration Plan':
            return 'Won (4)'
        elif s in ('5 - Implementation In Progress', '6 - Implementation Complete'):
            return 'Implementation (5-6)'
        elif s == '7 - Deployed':
            return 'Deployed (7)'
        return None

    stage_coco = managed_bulk_conf.copy()
    stage_coco['STAGE_GROUP'] = stage_coco['USE_CASE_STAGE'].apply(_stage_group)
    stage_coco = stage_coco[stage_coco['STAGE_GROUP'].notna()]
    stage_coco_agg = stage_coco.groupby('STAGE_GROUP').agg(
        COCO_UCS=('IS_COCO_FINAL', 'sum'),
        TOTAL_UCS_CONF=('USE_CASE_ID', 'count')
    ).reset_index()
    stage_coco_eacv = stage_coco[stage_coco['IS_COCO_FINAL']].groupby('STAGE_GROUP')['USE_CASE_EACV'].sum().reset_index()
    stage_coco_eacv.columns = ['STAGE_GROUP', 'COCO_EACV']
    stage_coco_agg = stage_coco_agg.merge(stage_coco_eacv, on='STAGE_GROUP', how='left').fillna({'COCO_EACV': 0})

    stage_merged = managed_stage_data.merge(stage_coco_agg, on='STAGE_GROUP', how='left').fillna(0)
    stage_merged['COCO_UCS'] = stage_merged['COCO_UCS'].astype(int)
    stage_merged['COCO_PCT'] = (stage_merged['COCO_UCS'] * 100.0 / stage_merged['UC_COUNT'].replace(0, float('nan'))).round(0).fillna(0).astype(int)

    for _, sg in stage_merged.iterrows():
        eacv = sg.get('TOTAL_EACV', 0) or 0
        coco_eacv = sg.get('COCO_EACV', 0) or 0
        stage_ctx += f"  {sg['STAGE_GROUP']}: {int(sg['UC_COUNT'])} UCs, {int(sg['COCO_UCS'])} CoCo ({int(sg['COCO_PCT'])}%), Total EACV ${eacv/1_000_000:.1f}M, CoCo EACV ${coco_eacv/1_000_000:.1f}M\n"
else:
    for _, sg in managed_stage_data.iterrows():
        eacv = sg.get('TOTAL_EACV', 0) or 0
        stage_ctx += f"  {sg['STAGE_GROUP']}: {int(sg['UC_COUNT'])} UCs, ${eacv/1_000_000:.1f}M\n"

region_ctx = ""
for _, rg in region_data.iterrows():
    eacv = rg.get('TOTAL_EACV', 0) or 0
    region_ctx += f"  {rg['REGION']}: {int(rg['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K EACV, {int(rg['PARTNER_COUNT'])} partners\n"

type_ctx = ""
for _, tp in type_patterns.head(10).iterrows():
    eacv = tp.get('TOTAL_EACV', 0) or 0
    type_ctx += f"  {tp['TECHNICAL_USE_CASE']}: {int(tp['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K, {int(tp['PARTNER_COUNT'])} partners, {int(tp['WON_PLUS'])} won+\n"

workload_ctx = ""
for _, wl in workload_data.iterrows():
    eacv = wl.get('TOTAL_EACV', 0) or 0
    workload_ctx += f"  {wl['WORKLOADS']}: {int(wl['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K, {int(wl['PARTNER_COUNT'])} partners\n"

competitive_ctx = ""
for _, comp in competitive_data.head(8).iterrows():
    eacv = comp.get('TOTAL_EACV', 0) or 0
    competitive_ctx += f"  {comp['COMPETITORS']}: {int(comp['USE_CASE_COUNT'])} UCs, ${eacv/1000:.0f}K\n"

partner_wl_ctx = ""
for _, pw in partner_workloads.head(12).iterrows():
    eacv = pw.get('TOTAL_EACV', 0) or 0
    cv = coverage_map.get(pw['PARTNER_NAME'], {})
    total_ucs = cv.get('total', '?')
    coco_pct = cv.get('pct', 0)
    partner_wl_ctx += f"  {pw['PARTNER_NAME']}: CoCo={int(pw['TOTAL_USE_CASES'])}/{total_ucs} ({coco_pct:.0f}%), ${eacv/1000:.0f}K | AI={int(pw['AI_USE_CASES'])}, DE={int(pw['DE_USE_CASES'])}, Analytics={int(pw['ANALYTICS_USE_CASES'])}, Platform={int(pw['PLATFORM_USE_CASES'])}, Apps={int(pw['APPS_USE_CASES'])}\n"

comment_ctx = ""
for _, cm in comment_data.head(10).iterrows():
    eacv = cm.get('USE_CASE_EACV', 0) or 0
    se_snip = str(cm.get('SE_COMMENTS_EXCERPT', '') or '')[:200].replace('\n', ' ')
    partner_snip = str(cm.get('PARTNER_COMMENTS_EXCERPT', '') or '')[:200].replace('\n', ' ')
    entry = f"  [{cm['PARTNER_NAME']} | {cm['ACCOUNT_NAME']} | ${eacv/1000:.0f}K | {cm.get('TECHNICAL_USE_CASE', 'N/A')}]"
    if se_snip:
        entry += f" SE: {se_snip}"
    if partner_snip:
        entry += f" PARTNER: {partner_snip}"
    comment_ctx += entry + "\n"


def _build_region_theme_ctx(df, region_name):
    region_df = df[df['REGION'] == region_name]
    if len(region_df) == 0:
        return f"  No data for {region_name}\n"
    total_ucs = int(region_df['USE_CASE_COUNT'].sum())
    total_eacv = region_df['TOTAL_EACV'].sum() or 0
    ctx = f"  {total_ucs} UCs, ${total_eacv/1_000_000:.1f}M EACV\n"
    type_agg = region_df.groupby('TECHNICAL_USE_CASE').agg({'USE_CASE_COUNT': 'sum', 'TOTAL_EACV': 'sum'}).reset_index().sort_values('TOTAL_EACV', ascending=False).head(5)
    for _, row in type_agg.iterrows():
        if row['TECHNICAL_USE_CASE']:
            ctx += f"    {row['TECHNICAL_USE_CASE']}: {int(row['USE_CASE_COUNT'])} UCs, ${(row.get('TOTAL_EACV', 0) or 0)/1000:.0f}K\n"
    comp_agg = region_df[region_df['COMPETITORS'].notna()].groupby('COMPETITORS').agg({'USE_CASE_COUNT': 'sum'}).reset_index().sort_values('USE_CASE_COUNT', ascending=False).head(3)
    comps = ", ".join([f"{r['COMPETITORS']}({int(r['USE_CASE_COUNT'])})" for _, r in comp_agg.iterrows()])
    if comps:
        ctx += f"    Competitors: {comps}\n"
    return ctx

# Build Q2 regional CoCo coverage context
partner_avg_map = {}
if len(managed_q2_partner_avg) > 0:
    for _, row in managed_q2_partner_avg.iterrows():
        partner_avg_map[row['REGION']] = row['AVG_COCO_PCT_PER_PARTNER']

regional_coco_ctx = ""
for _, rg in managed_q2_regional.iterrows():
    avg_pct = partner_avg_map.get(rg['REGION'], 0)
    regional_coco_ctx += f"  {rg['REGION']}: {int(rg['TOTAL_UCS'])} total UCs, {int(rg['COCO_UCS'])} CoCo, {rg['COCO_PCT']}% overall, {int(rg['PARTNER_COUNT'])} partners, {avg_pct}% avg/partner\n"

# Build credit consumption context
credit_ctx = ""
if len(credit_data) > 0:
    for _, cr in credit_data.head(12).iterrows():
        wow = f"{cr['WOW_PCT']:+.1f}%" if pd.notna(cr['WOW_PCT']) else "N/A"
        last7 = cr.get('LAST7_CREDITS', 0) or 0
        credit_ctx += f"  {cr['PARTNER_NAME']}: Q2 Credits=${cr['Q2_TOTAL_CREDITS']:,.0f}, Last 7d Credits=${last7:,.0f}, Q2 Tokens={cr['Q2_TOKENS']:,.0f}, Accts w/ Usage={int(cr['ACCTS_WITH_USAGE'])}, 7D Credits WoW%={wow}\n"



# CoCo adoption WoW context — current values from IS_COCO_FINAL, deltas from weekly snapshot
adoption_wow_ctx = ""
adoption_wow_partner_ctx = ""

# Build IS_COCO_FINAL per-partner lookup from managed_bulk_conf (same basis as scorecard)
_live_lookup = {}
if len(managed_bulk_conf) > 0:
    _live_partner = (
        managed_bulk_conf.groupby('PARTNER_NAME')
        .agg(TOTAL_UCS=('USE_CASE_ID', 'count'), COCO_UCS=('IS_COCO_FINAL', 'sum'))
        .reset_index()
    )
    _live_partner['COCO_PCT'] = round(
        _live_partner['COCO_UCS'] * 100.0 / _live_partner['TOTAL_UCS'].replace(0, float('nan')), 1
    ).fillna(0)
    _live_lookup = _live_partner.set_index('PARTNER_NAME').to_dict('index')

# IS_COCO_FINAL overall totals from managed_q2_stats
_live_total = int(managed_q2_stats.iloc[0]['TOTAL_UCS']) if len(managed_q2_stats) > 0 else 0
_live_coco  = int(managed_q2_stats.iloc[0]['COCO_UCS'])  if len(managed_q2_stats) > 0 else 0
_live_pct   = round(_live_coco * 100.0 / _live_total, 1) if _live_total > 0 else 0.0

# Pre-compute OKR headline targets so LLM doesn't need to infer them
import math as _math
_okr_target_ucs = _math.ceil(_live_total * 0.75)   # target = 75% of total UCs
_okr_gap_ucs    = _live_coco - _okr_target_ucs      # negative = short of target
_okr_target_pct = 75.0
_okr_gap_pct    = round(_live_pct - _okr_target_pct, 1)
# Partners meeting 75% per partner — computed from managed_bulk_conf
_p_meeting_50 = 0
if len(managed_bulk_conf) > 0:
    _pm = (managed_bulk_conf.groupby('PARTNER_NAME')
           .agg(T=('USE_CASE_ID','count'), C=('IS_COCO_FINAL','sum'))
           .assign(PCT=lambda d: d['C']/d['T'].replace(0, float('nan'))))
    _p_meeting_50 = int((_pm['PCT'] >= 0.50).sum())

okr_headline_ctx = (
    f"  Scope: GSIs (Global all regions) + NOAM RSIs (NoAM) + APJ RSIs (APJ geo) + EMEA RSIs (EMEA geo)\n"
    f"  Total Use Cases: {_live_total}\n"
    f"  CoCo Use Cases (Current): {_live_coco}\n"
    f"  CoCo Adoption % (Current): {_live_pct}%\n"
    f"  Target CoCo UCs (75% of total): {_okr_target_ucs}\n"
    f"  Target CoCo Adoption %: {_okr_target_pct}%\n"
    f"  Gap (UCs): {_okr_gap_ucs:+d}\n"
    f"  Gap (Adoption %): {_okr_gap_pct:+.1f}pp\n"
    f"  Partners Meeting 75% Target: {_p_meeting_50}/44\n"
)

if len(adoption_wow_data) > 0:
    overall_row = adoption_wow_data[adoption_wow_data['PARTNER_NAME'].isna()]
    partner_rows = adoption_wow_data[adoption_wow_data['PARTNER_NAME'].notna()].sort_values('COCO_PCT', ascending=False)
    if len(overall_row) > 0:
        ow = overall_row.iloc[0]
        wow_pct = f"{float(ow['WOW_COCO_PCT']):+.1f}%" if pd.notna(ow.get('WOW_COCO_PCT')) else "N/A (first week)"
        wow_ucs = f"{int(ow['WOW_COCO_UCS']):+d}" if pd.notna(ow.get('WOW_COCO_UCS')) else "N/A"
        adoption_wow_ctx = (
            f"  Week of {ow['WEEK_START']}:\n"
            f"  Overall CoCo Adoption %: {_live_pct}% (WoW: {wow_pct})\n"
            f"  Overall CoCo UCs: {_live_coco} of {_live_total} (WoW: {wow_ucs})\n"
        )
    for _, pr in partner_rows.iterrows():
        if pr['PARTNER_NAME'] not in MANAGED_PARTNERS:
            continue
        wow_pct = f"{float(pr['WOW_COCO_PCT']):+.1f}%" if pd.notna(pr.get('WOW_COCO_PCT')) else "N/A"
        wow_ucs = f"{int(pr['WOW_COCO_UCS']):+d}" if pd.notna(pr.get('WOW_COCO_UCS')) else "N/A"
        lv = _live_lookup.get(pr['PARTNER_NAME'], {})
        live_pct   = lv.get('COCO_PCT',  pr['COCO_PCT'])
        live_coco  = lv.get('COCO_UCS',  pr['COCO_UCS'])
        live_total = lv.get('TOTAL_UCS', pr['TOTAL_UCS'])
        adoption_wow_partner_ctx += f"  {pr['PARTNER_NAME']}: {live_pct}% CoCo ({int(live_coco)}/{int(live_total)} UCs), WoW Δ={wow_pct}, Δ UCs={wow_ucs}\n"
else:
    adoption_wow_ctx = "  No adoption WoW data yet (first snapshot seeded, next available after Sunday task run).\n"
    adoption_wow_partner_ctx = adoption_wow_ctx

# Regional OKR breakdown — hybrid live sources:
# 4-row OKR breakdown: GSI (global), NOAM RSI, APJ RSI, EMEA RSI — all from _GROUP-tagged managed_bulk_conf
regional_okr_ctx = ""

def _okr_row(grp_df, label, target_pct):
    if len(grp_df) == 0:
        return f"  {label}: no data\n"
    total = len(grp_df)
    coco  = int(grp_df['IS_COCO_FINAL'].sum())
    pct   = round(coco * 100.0 / total, 1)
    _pm   = grp_df.groupby('PARTNER_NAME').agg(T=('USE_CASE_ID','count'), C=('IS_COCO_FINAL','sum')).reset_index()
    _pm['PCT'] = _pm['C'] / _pm['T'].replace(0, float('nan'))
    meeting = int((_pm['PCT'] >= target_pct / 100.0).sum())
    return (
        f"  {label}: {total} total UCs, {coco} CoCo UCs, {pct}% CoCo adoption, "
        f"{meeting}/{len(_pm)} partners meeting goal ({target_pct}%)\n"
    )

if len(managed_bulk_conf) > 0 and '_GROUP' in managed_bulk_conf.columns:
    regional_okr_ctx += _okr_row(managed_bulk_conf[managed_bulk_conf['_GROUP'] == 'GSI'],      'GSI (Global, all regions)', 75)
    regional_okr_ctx += _okr_row(managed_bulk_conf[managed_bulk_conf['_GROUP'] == 'NOAM RSI'], 'NOAM RSI (NoAM only)',       75)
    regional_okr_ctx += _okr_row(managed_bulk_conf[managed_bulk_conf['_GROUP'] == 'APJ RSI'],  'APJ RSI (APJ geo)',          50)
    regional_okr_ctx += _okr_row(managed_bulk_conf[managed_bulk_conf['_GROUP'] == 'EMEA RSI'], 'EMEA RSI (EMEA geo)',        50)

# Recent wins context — last 7 days (deployments, competitive wins, pipeline moves)
recent_wins_ctx = ""
if len(recent_wins_data) > 0:
    for _, rw in recent_wins_data.iterrows():
        eacv = rw.get('USE_CASE_EACV', 0) or 0
        comp = f", displacing {rw['COMPETITORS']}" if rw.get('COMPETITORS') and str(rw['COMPETITORS']).strip() else ""
        recent_wins_ctx += (
            f"  [{rw['WIN_TYPE']}] {rw['PARTNER_NAME']} @ {rw['ACCOUNT_NAME']}: "
            f"{rw['USE_CASE_STAGE']}, ${eacv/1000:.0f}K EACV"
            f"{comp}\n"
        )
else:
    recent_wins_ctx = "  No new deployments, competitive wins, or pipeline moves in the last 7 days.\n"

# Notable wins by region — one IS_COCO_FINAL UC per group (GSI/NOAM RSI/APJ RSI/EMEA RSI)
# Picks the best UC: Deployed first, then highest EACV. Partners restricted to managed lists.
notable_wins_by_region_ctx = ""
if len(managed_bulk_conf) > 0 and 'IS_COCO_FINAL' in managed_bulk_conf.columns and '_GROUP' in managed_bulk_conf.columns:
    _stage_pri_map = {
        '7 - Deployed': 1, '6 - Implementation Complete': 2,
        '5 - Implementation In Progress': 3, '4 - Use Case Won / Migration Plan': 4,
        '3 - Technical / Business Validation': 5,
    }
    _cf = managed_bulk_conf[managed_bulk_conf['IS_COCO_FINAL']].copy()
    _cf['_spri'] = _cf['USE_CASE_STAGE'].map(_stage_pri_map).fillna(6)
    _cf['_eacv'] = pd.to_numeric(_cf['USE_CASE_EACV'], errors='coerce').fillna(0)
    _cf = _cf.sort_values(['_GROUP', '_spri', '_eacv'], ascending=[True, True, False])
    _best = _cf.drop_duplicates(subset=['_GROUP'], keep='first')

    # Fetch GO_LIVE_DATE and COMPETITORS for the selected UCs
    _best_ids = [str(i) for i in _best['USE_CASE_ID'].dropna().tolist()]
    _uc_detail = pd.DataFrame()
    if _best_ids:
        _ids_sql = "','".join(_best_ids)
        _uc_detail = conn.query(f"""
            SELECT USE_CASE_ID, GO_LIVE_DATE, DECISION_DATE, COMPETITORS
            FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES
            WHERE USE_CASE_ID IN ('{_ids_sql}')
        """)

    for _grp in ['GSI', 'NOAM RSI', 'APJ RSI', 'EMEA RSI']:
        _row = _best[_best['_GROUP'] == _grp]
        if len(_row) == 0:
            notable_wins_by_region_ctx += f"  [{_grp}] No IS_COCO_FINAL use case found.\n"
            continue
        r = _row.iloc[0]
        eacv = float(r.get('_eacv', 0) or 0)
        stage_short = str(r.get('USE_CASE_STAGE', '')).split(' - ', 1)[-1]
        date_str = comp_str = ""
        if len(_uc_detail) > 0:
            _det = _uc_detail[_uc_detail['USE_CASE_ID'] == r['USE_CASE_ID']]
            if len(_det) > 0:
                d = _det.iloc[0]
                if pd.notna(d.get('GO_LIVE_DATE')):
                    date_str = f", deployed {d['GO_LIVE_DATE']}"
                elif pd.notna(d.get('DECISION_DATE')):
                    date_str = f", decision {d['DECISION_DATE']}"
                if d.get('COMPETITORS') and str(d['COMPETITORS']).strip():
                    comp_str = f", displacing {d['COMPETITORS']}"
        notable_wins_by_region_ctx += (
            f"  [{_grp}] {r['PARTNER_NAME']} @ {r['ACCOUNT_NAME']}: "
            f"{stage_short}, ${eacv/1000:.0f}K EACV, {r.get('TECHNICAL_USE_CASE','N/A')}"
            f"{date_str}{comp_str}\n"
        )
else:
    notable_wins_by_region_ctx = "  IS_COCO_FINAL data not available.\n"

# Pipeline WoW context (use case count change vs prior week)
def _fmt_wow(val):
    return f"+{int(val)}" if val > 0 else str(int(val))

pipeline_wow_ctx = ""
if len(pipeline_wow) > 0:
    pw = pipeline_wow.iloc[0]
    wow_eacv = pw['WOW_EACV']
    eacv_sign = "+" if wow_eacv >= 0 else ""
    pipeline_wow_ctx = (
        f"  Week of {pw['WEEK_START']} vs {pw['PREV_WEEK_START']} (all CoCo partners, proxy for managed):\n"
        f"  CoCo Use Cases:  {int(pw['TOTAL_UCS'])} ({_fmt_wow(pw['WOW_TOTAL'])} WoW)\n"
        f"  CoCo EACV:       ${pw['TOTAL_EACV']/1_000_000:.1f}M ({eacv_sign}${wow_eacv/1_000_000:.1f}M WoW)\n"
        f"  Deployed (7):    {int(pw['DEPLOYED'])} ({_fmt_wow(pw['WOW_DEPLOYED'])} WoW)\n"
        f"  In Impl (5-6):   {int(pw['IN_IMPL'])} ({_fmt_wow(pw['WOW_IN_IMPL'])} WoW)\n"
        f"  Won (4):         {int(pw['WON'])} ({_fmt_wow(pw['WOW_WON'])} WoW)\n"
        f"  Active (3):      {int(pw['ACTIVE_PIPELINE'])} ({_fmt_wow(pw['WOW_ACTIVE'])} WoW)\n"
    )
else:
    pipeline_wow_ctx = "  No WoW data available.\n"

# GSI WoW context (engagement — CoCo requests, all regions)
gsi_wow_ctx = ""
if len(gsi_wow) > 0:
    for _, g in gsi_wow.iterrows():
        wow = f"{g['WOW_PCT']:+.1f}%" if pd.notna(g['WOW_PCT']) else "N/A"
        gsi_wow_ctx += f"  {g['GSI_GROUP']}: {int(g['TOTAL_REQUESTS']):,} requests (LW={int(g['LW_REQUESTS']):,}, PW={int(g['PW_REQUESTS']):,}), WoW={wow}\n"
else:
    gsi_wow_ctx = "  No GSI WoW data available.\n"

# NoAM SI WoW context (engagement — CoCo requests)
noam_si_wow_ctx = ""
if len(noam_si_wow) > 0:
    for _, s in noam_si_wow.iterrows():
        wow = f"{s['WOW_PCT']:+.1f}%" if pd.notna(s['WOW_PCT']) else "N/A"
        noam_si_wow_ctx += f"  {s['PARTNER_NAME']}: {int(s['TOTAL_REQUESTS']):,} requests (LW={int(s['LW_REQUESTS']):,}, PW={int(s['PW_REQUESTS']):,}), WoW={wow}\n"
else:
    noam_si_wow_ctx = "  No NoAM SI WoW data available.\n"


data_context = f"""
=== Q3 (Aug-Oct 2026) | MANAGED PARTNERS (GSI + NOAM RSI + APJ RSI + EMEA RSI) | Stages 3-7 ===
NOTE: Q3 = Aug 1 – Oct 31, 2026. GSIs report globally; NOAM RSIs = NoAM theaters only; APJ/EMEA RSIs = their respective geo regions.

GLOBAL REFERENCE (all partners, Q3, Stages 3-7, with account-level attribution): {int(go['COCO_USE_CASES'])} CoCo UCs | {int(go['TOTAL_PARTNERS'])} partners | ${go['TOTAL_EACV']/1_000_000:.1f}M EACV | {go['COCO_PCT']}% CoCo adoption

MANAGED PARTNERS Q3 HEADLINE:
  CoCo Use Cases: {managed_coco_ucs} (THIS is the CoCo number for the opening sentence)
  Total Pipeline (CoCo + non-CoCo): {managed_total_ucs} use cases
  CoCo Adoption: {managed_coco_pct}%
  Active Partners: {managed_total_partners}
  Total EACV: ${managed_total_eacv/1_000_000:.1f}M
  CoCo EACV: ${managed_coco_eacv/1_000_000:.1f}M
  CoCo Deployed: {managed_coco_deployed}
  Partners Meeting 75% Target: {partners_meeting_75} ({partners_meeting_list})
  Partners Below 50% Target: {partners_below_50}
No Q3 Activity ({managed_inactive_partners} partners): {', '.join(managed_inactive_names)}

MANAGED PARTNER COCO COVERAGE (Q3, by region):
  Overall: {managed_total_ucs} total UCs, {managed_coco_ucs} CoCo, {managed_coco_pct}%
{regional_coco_ctx}

PIPELINE (Managed Partners, Q3, all UCs):
{stage_ctx}

PIPELINE WoW (all CoCo partners, use case count change vs prior week):
{pipeline_wow_ctx}

COCO CREDIT CONSUMPTION (Q3, managed partners):
{credit_ctx}

REGIONAL BREAKDOWN (Managed and Unmanaged):
{region_ctx}

PARTNER SCORECARD BY GROUP (Q3, target 75% CoCo adoption):
{gsi_partner_ctx}
{noam_partner_ctx}
{apj_partner_ctx}
{emea_partner_ctx}

COCO ADOPTION WoW — OVERALL (from weekly snapshot table):
{adoption_wow_ctx}

COCO ADOPTION WoW — PER MANAGED PARTNER (sorted by CoCo %):
{adoption_wow_partner_ctx}

PARTNER WORKLOAD MIX (managed partners only):
{partner_wl_ctx}

OKR PROGRESS — 6 GSIs WoW (CoCo engagement, all regions combined — LW=last week, PW=prior week):
{gsi_wow_ctx}

OKR PROGRESS — NoAM SIs WoW (CoCo engagement — LW=last week, PW=prior week):
{noam_si_wow_ctx}

OKR PROGRESS — REGIONAL BREAKDOWN (4 groups; GSI/NOAM goal=75%, APJ/EMEA goal=50%):
{regional_okr_ctx}

COMMENT HIGHLIGHTS (managed partners only, Top 10 by EACV):
{comment_ctx}

RECENT ACTIVITY — LAST 7 DAYS (deployments, competitive wins, pipeline moves):
{recent_wins_ctx}

NOTABLE WINS BY REGION (one IS_COCO_FINAL UC per group — best stage then highest EACV):
{notable_wins_by_region_ctx}
"""

st.markdown("---")
st.subheader("Generate Email Summary")

current_user = "rithesh.makkena"
try:
    current_user = conn.query("SELECT CURRENT_USER()").iloc[0][0].lower()
except Exception:
    pass

recipients_input = st.text_area(
    "To (one name per line, e.g. 'John Smith' → john.smith@snowflake.com)",
    value="",
    height=80,
    placeholder="John Smith\nJane Doe\ncustom.email@partner.com",
    key="email_recipients"
)

default_prompt = f"""You are writing a polished executive briefing for Snowflake leadership on CoCo partner use case performance for Q3 FY27 (Aug–Oct 2026). This will be read by VPs and the CEO — keep it sharp, data-rich, and action-oriented.
Do NOT include a title, heading, or subject line like "Cortex Code (CoCo) Partner Use Case Traction" at the top of the email. Start directly with the Note block.

SCOPE: 4 partner groups — GSIs report GLOBAL numbers; NOAM RSIs report NoAM only; APJ RSIs report their respective APJ geo region; EMEA RSIs report their respective EMEA geo region.

Follow this EXACT structure with 9 sections:

## **Note: Mixed scope — GSIs global (all regions) | NOAM RSIs: NoAM only | APJ RSIs: APJ geo | EMEA RSIs: EMEA geo.**

## EXECUTIVE SUMMARY
2-3 sentences maximum, then exactly 6 bullets.
- Open with: "[X] CoCo use cases across managed partners **(GSIs global + NOAM/APJ/EMEA RSIs geo-scoped)** representing $[Z]M in CoCo EACV, with [W] deployed in production."
- Second sentence: one crisp insight on the dominant pattern.
- Bullet 1: "**Leading use case types:** [top 3 by count]"
- Bullet 2: "**CoCo Adoption:** [X]% overall — GSIs: [GSI%] | NOAM RSIs: [NOAM%] | APJ RSIs: [APJ%] | EMEA RSIs: [EMEA%]"
- Bullet 3: "**Top GSIs by EACV:** ([top 3 GSIs])"
- Bullet 4: "**Top RSIs by EACV:** ([top 3 RSI partners across all 3 RSI groups])"
- Bullet 5: "**Competitive displacement:** [top 3 competitors by count]"
- Bullet 6: "**[Detailed Partner CoCo usecase dashboard](https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS)**"

## OKR PROGRESS — REGIONAL BREAKDOWN
| Group | Scope | Total UCs | CoCo UCs | CoCo % | Partners Meeting Goal% |
- Show 4 rows: GSI (Global), NOAM RSI, APJ RSI, EMEA RSI
- Use "OKR PROGRESS — REGIONAL BREAKDOWN" data from context (each row has group name, total UCs, CoCo UCs, CoCo %, partners meeting goal)
- Goal% is 75% for GSI and NOAM RSI, 50% for APJ RSI and EMEA RSI — reflect the correct target per row
- After table: ONE sentence — which group is lagging most and what it signals for enablement focus

## MANAGED PARTNER PIPELINE OVERVIEW
| Stage | Total UCs | CoCo UCs | CoCo % | Total EACV | CoCo EACV |
- Use MANAGED PARTNERS pipeline data (stage_ctx) for all columns

## PARTNER SCORECARD — GSI (Global, all regions, target 75%)
| Partner | Total UCs | CoCo UCs | CoCo% | WoW Δ% | WoW Δ UCs | EACV | AI | DE | Analytics | Q3 Tokens | Q3 Credits | Last 7d Credits | 7D Credits WoW% |
- Show ALL GSI partners. Sort by EACV descending. UCs are GLOBAL (all regions).
- WoW Δ% and WoW Δ UCs from adoption WoW data — show "-" if N/A
- After table: one sentence listing GSIs below 75% in ascending order of CoCo%.

## PARTNER SCORECARD — NOAM RSI (NoAM only, target 75%)
| Partner | Total UCs | CoCo UCs | CoCo% | WoW Δ% | WoW Δ UCs | EACV | AI | DE | Analytics | Q3 Tokens | Q3 Credits | Last 7d Credits | 7D Credits WoW% |
- Show ALL NOAM RSI partners. Sort by EACV descending. UCs are NoAM scope only.
- After table: one sentence listing NOAM RSIs below 75% in ascending order of CoCo%.

## PARTNER SCORECARD — APJ RSI (APJ geo-restricted, target 50%)
| Partner | Total UCs | CoCo UCs | CoCo% | WoW Δ% | WoW Δ UCs | EACV | AI | DE | Analytics | Q3 Tokens | Q3 Credits | Last 7d Credits | 7D Credits WoW% |
- Show ALL APJ RSI partners. Sort by EACV descending. UCs are each partner's respective APJ region.
- After table: one sentence listing APJ RSIs below 50% in ascending order of CoCo%.

## PARTNER SCORECARD — EMEA RSI (EMEA geo-restricted, target 50%)
| Partner | Total UCs | CoCo UCs | CoCo% | WoW Δ% | WoW Δ UCs | EACV | AI | DE | Analytics | Q3 Tokens | Q3 Credits | Last 7d Credits | 7D Credits WoW% |
- Show ALL EMEA RSI partners. Sort by EACV descending. UCs are each partner's respective EMEA region.
- After table: one sentence listing EMEA RSIs below 50% in ascending order of CoCo%.

## NOTABLE WINS (managed partners only)
4 bullets — exactly one per region group. Use data from "NOTABLE WINS BY REGION" in context.
- Format each as: "**[Group] Partner** deployed/won CoCo at Account — Stage, $EACVK EACV[, displacing Competitor if present]"
- Groups in order: GSI, NOAM RSI, APJ RSI, EMEA RSI
- If a group has no IS_COCO_FINAL UC, write “**[Group]** No notable win this period”
- Do NOT use RECENT ACTIVITY data or COMMENT HIGHLIGHTS for this section

## DISCLAIMER
"**Disclaimer:** Use case data sourced from SE comments (coco/cortex code mentions), #coco in Partner Comments, and AI-Cortex Code feature flag. Pipeline figures are being confirmed by the PDM team and are subject to change. Detailed stats: http://go/cocopse"

FORMATTING RULES:
- Markdown tables for ALL data — no narrative paragraphs for numbers
- Executive summary: exactly 2-3 sentences + 6 bullets, nothing more
- Section headings: ## format, no numbering
- Currency: $X.XM for millions, $XK for thousands, $0 when zero
- Numbers: use commas (e.g., 1,200)
- Total length: under 700 words
- Tone: confident, data-driven, executive-appropriate
- No greeting, sign-off, subject line, or filler"""

prompt_input = st.text_area(
    "Prompt",
    value=default_prompt,
    height=300,
    help="Edit this prompt to customize the email output. Data summary above will be automatically included."
)

if st.button("Generate Email Summary", type="primary", key="email_generate"):
    full_prompt = f"""{prompt_input}

DATA:
{data_context}

Write the executive briefing:"""

    response_placeholder = st.empty()
    response_placeholder.info("Generating executive briefing with Cortex Complete...")
    full_response = cortex_complete(conn, "claude-sonnet-4-5", full_prompt)
    # Escape $ followed by digits so Streamlit doesn't interpret $X.XM as LaTeX math delimiters.
    # Without this, text like "$23.5M), Deloitte(19.8M), EY ($" renders "Deloitte" in italic serif.
    import re as _re
    _display = _re.sub(r'\$(\d)', r'\\$\1', full_response)
    response_placeholder.markdown(_display)

    st.success("Email generated successfully!")
    st.markdown("---")

    html_email = md_to_html(full_response)

    # Inject heat map after Executive Summary bullets
    if len(managed_q2_partners) > 0:
        heatmap_html = generate_heatmap_html(adoption_wow_data, managed_q2_partners)
        html_email = inject_heatmap(html_email, heatmap_html)

    # Inject partners-meeting-50% trend chart after OKR Progress table
    if trend_data:
        trend_chart_html = generate_partners_target_chart_html(trend_data, total_partners=44)
        html_email = inject_after_okr_table(html_email, trend_chart_html)

    to_lines = [l.strip() for l in recipients_input.strip().splitlines() if l.strip()] if recipients_input.strip() else []
    to_emails = [name_to_email(n) for n in to_lines]
    to_str = ','.join(to_emails)
    subject_text = f"Cortex Code Q3 FY27 Partner Intelligence - {datetime.now().strftime('%B %d, %Y')}"
    subject = urllib.parse.quote(subject_text)
    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_str}&su={subject}"

    st.info("**How to send:** Click **Copy Rich Text** below, then **Open in Gmail**, and paste (Ctrl+V / Cmd+V) into the email body. Tables will render with full formatting.")

    col1, col2, col3 = st.columns(3)
    with col1:
        escaped_html = html_email.replace('`', '\\`').replace('${', '\\${')
        plain_text = full_response.replace(chr(96), '').replace('${', '')[:8000]
        copy_js = f"""
        <button onclick="copyRich()" id="copyBtn" style="
            background-color: #29B5E8; color: white; border: none; padding: 8px 20px;
            border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600;
            width: 100%;">Copy Rich Text</button>
        <script>
        function copyRich() {{
            const html = `{escaped_html}`;
            const blob = new Blob([html], {{type: 'text/html'}});
            const plainBlob = new Blob([`{plain_text}`], {{type: 'text/plain'}});
            const item = new ClipboardItem({{
                'text/html': blob,
                'text/plain': plainBlob
            }});
            navigator.clipboard.write([item]).then(() => {{
                document.getElementById('copyBtn').textContent = 'Copied!';
                document.getElementById('copyBtn').style.backgroundColor = '#28a745';
                setTimeout(() => {{
                    document.getElementById('copyBtn').textContent = 'Copy Rich Text';
                    document.getElementById('copyBtn').style.backgroundColor = '#29B5E8';
                }}, 2000);
            }});
        }}
        </script>
        """
        components.html(copy_js, height=45)
    with col2:
        st.link_button("Open in Gmail", gmail_url, type="primary")
    with col3:
        st.download_button(
            label="Download as HTML",
            data=html_email,
            file_name=f"coco_usecase_briefing_{datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html"
        )

st.markdown("---")
st.caption("Powered by Snowflake Cortex Complete | Q3 FY27 (Aug–Oct 2026) | Data sourced from CoCo Use Case Intelligence")
