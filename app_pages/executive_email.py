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
    get_partner_velocity_data,
)
from utils.cortex_helpers import cortex_complete

MANAGED_PARTNERS = [
    # Global SIs
    'Accenture', 'Capgemini Technologies LLC',
    'Cognizant Technology Solutions US Corp', 'Deloitte Consulting', 'EY', 'Ernst & Young (EY)',
    'IBM', 'IBM Consulting',
    # Regional Managed Partners
    '7Rivers, Inc', 'Aimpoint Digital', 'BlueCloud Services Inc', 'kipi.ai', 'Kipi.ai',
    'evolv Consulting', 'Infostrux Solutions Inc.', 'Infosys', 'KPMG LLP',
    'LTM', 'LTI Mindtree', 'NTT DATA Group Corporation', 'phData, Inc.',
    'Slalom, LLC.', 'Squadron Data Inc', 'Tredence Inc.'
]

# GSIs report globally (all theaters); Regional SIs report NoAM only.
# Aliases: EY=Ernst & Young (EY), IBM=IBM Consulting, kipi.ai=Kipi.ai, LTM=LTI Mindtree
_GSI_NAMES = frozenset({
    'Accenture', 'Capgemini Technologies LLC', 'Cognizant Technology Solutions US Corp',
    'Deloitte Consulting', 'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting'
})

# Short display name → canonical partner name (for heat map tiles)
HEATMAP_PARTNERS = [
    ('Accenture',   'Accenture'),
    ('Capgemini',   'Capgemini Technologies LLC'),
    ('Cognizant',   'Cognizant Technology Solutions US Corp'),
    ('Deloitte',    'Deloitte Consulting'),
    ('EY',          'EY'),
    ('IBM',         'IBM'),
    ('7Rivers',     '7Rivers, Inc'),
    ('Aimpoint',    'Aimpoint Digital'),
    ('BlueCloud',   'BlueCloud Services Inc'),
    ('kipi.ai',     'kipi.ai'),
    ('evolv',       'evolv Consulting'),
    ('Infostrux',   'Infostrux Solutions Inc.'),
    ('Infosys',     'Infosys'),
    ('KPMG',        'KPMG LLP'),
    ('LTM',         'LTM'),
    ('NTT DATA',    'NTT DATA Group Corporation'),
    ('phData',      'phData, Inc.'),
    ('Slalom',      'Slalom, LLC.'),
    ('Squadron',    'Squadron Data Inc'),
    ('Tredence',    'Tredence Inc.'),
]


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
    Green ≥50%, amber 30-49%, red <30%.
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
        partner_items.append((display_name, pct, wow))

    def tier_order(item):
        _, pct, _ = item
        if pct >= 50: return (0, -pct)
        if pct >= 30: return (1, -pct)
        return (2, -pct)

    partner_items.sort(key=tier_order)

    tiles = []
    for display_name, pct, wow in partner_items:
        if pct >= 50:
            bg, border, val_color = '#dcfce7', '1px solid #86efac', '#16a34a'
        elif pct >= 30:
            bg, border, val_color = '#fef3c7', '1px solid #fbbf24', '#d97706'
        else:
            bg, border, val_color = '#fee2e2', '1px solid #fca5a5', '#dc2626'

        # crossed = newly crossed 50% this week (was below 50% last week, now at or above)
        crossed = pct >= 50 and wow is not None and (pct - wow) < 50

        wow_html = ''
        if wow is not None and wow != 0:
            if wow > 0:
                wow_html = f'<div style="font-size:9px;color:#16a34a;">&#9650; +{wow:.1f}pp</div>'
            else:
                wow_html = f'<div style="font-size:9px;color:#dc2626;">&#9660; {wow:.1f}pp</div>'

        star = ' &#9733;' if wow is not None and wow != 0 else ''
        tiles.append(
            f'<td style="background:{bg};border:{border};border-radius:6px;'
            f'padding:8px 4px;text-align:center;width:20%;vertical-align:top;">'
            f'<div style="font-size:11px;font-weight:700;white-space:nowrap;">{display_name}{star}</div>'
            f'<div style="font-size:17px;font-weight:900;color:{val_color};">{pct:.0f}%</div>'
            f'{wow_html}'
            f'</td>'
        )

    row_htmls = []
    for i in range(0, len(tiles), 5):
        chunk = tiles[i:i+5]
        while len(chunk) < 5:
            chunk.append('<td style="width:20%;"></td>')
        row_htmls.append(f'<tr style="vertical-align:top;">{"" .join(chunk)}</tr>')

    legend_row = (
        '<tr><td colspan="5" style="padding:0 0 8px 0;font-size:11px;">'
        '<span style="background:#dcfce7;color:#16a34a;padding:3px 9px;border-radius:4px;font-weight:700;">&#9632; &#8805;50%</span>&nbsp;'
        '<span style="background:#fef3c7;color:#d97706;padding:3px 9px;border-radius:4px;font-weight:700;">&#9632; 30&#8211;49%</span>&nbsp;'
        '<span style="background:#fee2e2;color:#dc2626;padding:3px 9px;border-radius:4px;font-weight:700;">&#9632; &lt;30%</span>&nbsp;'
        '<span style="color:#0369a1;font-weight:700;">&#9733; = WoW change</span>'
        '</td></tr>'
    )

    return (
        '<div style="margin:14px 0;">'
        '<div style="font-size:13px;font-weight:700;margin-bottom:8px;">Partner OKR Heat Map &#8212; All 20 (&#9733; = changed this week)</div>'
        '<table width="100%" cellpadding="6" cellspacing="4" style="border-collapse:separate;table-layout:fixed;">'
        f'{legend_row}{" ".join(row_htmls)}'
        '</table></div>'
    )


def generate_trend_chart_html(trend_data: list) -> str:
    """Gmail-safe 4-week CoCo adoption % bar chart with 50% reference line."""
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
    pct_color = '#16a34a' if current_pct >= 50 else ('#f59e0b' if current_pct >= 30 else '#dc2626')

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
            f'<td width="35" height="2" style="width:35px;height:2px;border-bottom:2px dashed #dc2626;padding:0 0 2px 4px;font-size:10px;color:#dc2626;font-weight:bold;vertical-align:bottom;white-space:nowrap;">50%</td></tr>')
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
        '&#8212;&#8212; Dashed red = 50% OKR target &nbsp;&middot;&nbsp; <span style="color:#16a34a;font-weight:bold;">&#9646;</span> = current week'
        '</td></tr></table></td></tr></table>'
    )


def generate_partners_target_chart_html(trend_data: list) -> str:
    """Gmail-safe bar chart showing count of partners meeting the 50% CoCo target per week.
    trend_data: [(week_label, partners_at_target, total_partners), ...]
    """
    if not trend_data:
        return ''

    MAX_PARTNERS = 20  # always 20 managed partners (EY + Ernst & Young are aliases of one)
    CHART_H = 80       # chart area height in px
    BAR_W = 88
    GAP = 24
    Y_W = 28           # y-axis label column width
    NB = 'border:none;outline:none;'

    n = len(trend_data)
    n_cols = 2 * n - 1
    bars_w = n * BAR_W + (n - 1) * GAP
    total_w = Y_W + bars_w

    current_count = trend_data[-1][1]
    if n >= 2:
        wow_delta = trend_data[-1][1] - trend_data[-2][1]
        arrow = '&#9650;' if wow_delta > 0 else ('&#9660;' if wow_delta < 0 else '&#8212;')
        if wow_delta > 0:
            wow_label = f'&nbsp;<span style="font-size:11px;color:#16a34a;font-weight:bold;">+{wow_delta} new this week</span>'
        elif wow_delta < 0:
            wow_label = f'&nbsp;<span style="font-size:11px;color:#dc2626;font-weight:bold;">{wow_delta} this week</span>'
        else:
            wow_label = f'&nbsp;<span style="font-size:11px;color:#6b7280;">no change this week</span>'
    else:
        arrow = '&#8212;'
        wow_label = ''
    pct_color = '#16a34a' if current_count >= MAX_PARTNERS * 0.5 else ('#f59e0b' if current_count >= MAX_PARTNERS * 0.3 else '#dc2626')

    # Y-axis: ticks at 20, 10, 0
    half_h = CHART_H // 2
    y_axis = (
        f'<td width="{Y_W}" valign="top" style="width:{Y_W}px;vertical-align:top;padding:0;{NB}">'
        f'<table width="{Y_W}" border="0" cellpadding="0" cellspacing="0" style="width:{Y_W}px;border-collapse:collapse;">'
        f'<tr><td width="{Y_W}" height="1" style="width:{Y_W}px;font-size:9px;color:#9ca3af;text-align:right;padding-right:4px;line-height:1;{NB}">20</td></tr>'
        f'<tr><td width="{Y_W}" height="{half_h - 6}" style="width:{Y_W}px;{NB}"></td></tr>'
        f'<tr><td width="{Y_W}" height="1" style="width:{Y_W}px;font-size:9px;color:#9ca3af;text-align:right;padding-right:4px;line-height:1;{NB}">10</td></tr>'
        f'<tr><td width="{Y_W}" height="{half_h - 6}" style="width:{Y_W}px;{NB}"></td></tr>'
        f'<tr><td width="{Y_W}" height="1" style="width:{Y_W}px;font-size:9px;color:#9ca3af;text-align:right;padding-right:4px;line-height:1;{NB}">0</td></tr>'
        f'</table></td>'
    )
    y_axis_title_cell = (
        f'<td width="{Y_W}" style="width:{Y_W}px;font-size:9px;color:#9ca3af;text-align:right;padding-right:4px;padding-bottom:2px;{NB}">Partners</td>'
    )

    label_cells, bar_cells, date_cells = [], [], []

    import pandas as _pd
    _current_week_start = _pd.Timestamp.now().to_period('W').start_time.normalize()

    for i, (raw_label, count, total) in enumerate(trend_data):
        # Format label fresh at render time (not cached)
        try:
            ts = _pd.Timestamp(raw_label)
            if ts.normalize() >= _current_week_start:
                label = "Current Week"
            else:
                day = ts.day
                suffix = 'th' if 11 <= day <= 13 else {1:'st',2:'nd',3:'rd'}.get(day % 10, 'th')
                label = f"Week of {ts.strftime('%b')} {day}{suffix}"
        except Exception:
            label = raw_label
        fill = '#16a34a' if i == n - 1 else '#29B5E8'
        bar_h = max(4, int(CHART_H * count / MAX_PARTNERS))
        spacer_h = CHART_H - bar_h

        if i > 0:
            for lst in (label_cells, date_cells):
                lst.append(f'<td width="{GAP}" style="width:{GAP}px;{NB}"></td>')
            bar_cells.append(f'<td width="{GAP}" style="width:{GAP}px;font-size:0;line-height:0;{NB}">&nbsp;</td>')

        label_cells.append(
            f'<td width="{BAR_W}" align="center" style="width:{BAR_W}px;text-align:center;'
            f'font-size:13px;font-weight:bold;color:{fill};padding-bottom:4px;{NB}">'
            f'{count}/{MAX_PARTNERS}</td>'
        )

        inner = f'<table width="{BAR_W}" border="0" cellpadding="0" cellspacing="0" style="width:{BAR_W}px;border-collapse:collapse;">'
        if spacer_h > 0:
            inner += f'<tr><td width="{BAR_W}" height="{spacer_h}" bgcolor="#ffffff" style="width:{BAR_W}px;height:{spacer_h}px;background-color:#ffffff;font-size:0;line-height:0;{NB}">&nbsp;</td></tr>'
        inner += (f'<tr><td width="{BAR_W}" height="{bar_h}" bgcolor="{fill}" '
                  f'style="width:{BAR_W}px;height:{bar_h}px;background-color:{fill};font-size:0;line-height:0;{NB}">&nbsp;</td></tr></table>')
        bar_cells.append(f'<td width="{BAR_W}" height="{CHART_H}" valign="bottom" style="width:{BAR_W}px;height:{CHART_H}px;vertical-align:bottom;padding:0;{NB}">{inner}</td>')

        date_cells.append(f'<td width="{BAR_W}" align="center" style="width:{BAR_W}px;text-align:center;font-size:10px;color:#374151;padding-top:6px;{NB}">{label}</td>')

    # Rows: Partners label (top), value labels, bars, x-axis line, date labels
    row_title = f'<tr>{y_axis_title_cell}<td></td></tr>'
    row0 = f'<tr>{y_axis}<td><table border="0" cellpadding="0" cellspacing="0">{"<tr>" + "".join(label_cells) + "</tr>"}</table></td></tr>'
    row1 = f'<tr><td width="{Y_W}" style="width:{Y_W}px;{NB}"></td><td><table border="0" cellpadding="0" cellspacing="0">{"<tr>" + "".join(bar_cells) + "</tr>"}</table></td></tr>'
    row2 = f'<tr><td colspan="2" height="2" bgcolor="#d1d5db" style="height:2px;background-color:#d1d5db;font-size:0;line-height:0;">&nbsp;</td></tr>'
    row3 = f'<tr><td width="{Y_W}" style="width:{Y_W}px;{NB}"></td><td><table border="0" cellpadding="0" cellspacing="0">{"<tr>" + "".join(date_cells) + "</tr>"}</table></td></tr>'
    row4 = f'<tr><td></td><td align="center" style="font-size:9px;color:#9ca3af;padding-top:2px;">Week</td></tr>'

    chart_table = (f'<table width="{total_w}" border="0" cellpadding="0" cellspacing="0" style="width:{total_w}px;border-collapse:collapse;">'
                   f'{row_title}{row0}{row1}{row2}{row3}{row4}</table>')

    return (
        '<table width="600" border="0" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif;margin:16px 0;border:1px solid #e5e7eb;">'
        '<tr><td style="padding:12px 16px;background-color:#f9fafb;border-bottom:1px solid #e5e7eb;">'
        f'<span style="font-size:13px;font-weight:bold;color:#111827;">&#127942; Partners Meeting 50% Target &#8212; {n}-Week Trend</span>'
        f'&nbsp;&nbsp;<span style="font-size:12px;color:{pct_color};font-weight:bold;">Current: {current_count}/{MAX_PARTNERS} {arrow}</span>'
        f'{wow_label}'
        '</td></tr>'
        f'<tr><td style="padding:8px 16px 8px;background-color:#ffffff;">{chart_table}'
        '<table width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top:6px;">'
        '<tr><td style="font-size:10px;color:#6b7280;padding-top:2px;">'
        f'# of 20 managed partners with \u226550% CoCo adoption &nbsp;&middot;&nbsp; '
        '<span style="color:#16a34a;font-weight:bold;">&#9646;</span> = current week'
        '</td></tr></table></td></tr></table>'
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
    """Insert dumbbell chart before USE CASE PATTERNS so the scorecard 50% sentence stays above."""
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
    global_overview = get_adoption_overview(conn, '2026-05-01', '2026-07-31', include_account_coco=True, confidence='High')
    pipeline_wow = get_pipeline_wow(conn)
    gsi_wow = get_gsi_wow(conn)
    noam_si_wow = get_noam_si_wow(conn)
    adoption_wow_data = get_coco_final_wow(conn, partners=MANAGED_PARTNERS, gsi_global=True, gsi_names=_GSI_NAMES)

    # Managed partner stage EACV breakdown — Q2 ONLY (May 1 - Jul 31, 2026)
    managed_partners_sql = "','".join(MANAGED_PARTNERS)
    Q2_START = '2026-05-01'
    Q2_END = '2026-07-31'

    recent_wins_data = get_recent_wins(conn, MANAGED_PARTNERS, Q2_START, Q2_END)

    # Q2 Credit consumption for managed partners
    credit_data = get_partner_credit_consumption(conn, MANAGED_PARTNERS, Q2_START, Q2_END)

    # GSI global coverage — all regions (not NoAM-filtered), using IS_COCO_FINAL
    GSI_LIST = ['Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
                'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting']
    gsi_bulk_conf = get_bulk_confidence_scores(conn, GSI_LIST, Q2_START, Q2_END)
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
            (uc.USE_CASE_STAGE IN ('3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND uc.DECISION_DATE >= '{Q2_START}' AND uc.DECISION_DATE <= '{Q2_END}')
            OR (uc.USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND uc.GO_LIVE_DATE >= '{Q2_START}' AND uc.GO_LIVE_DATE <= '{Q2_END}')
        )
        -- GSIs: all theaters (global); RSIs: NoAM only
        AND (
            uc.PARTNER_NAME IN ('Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
                                'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting')
            OR uc.THEATER_NAME IN ('AMSExpansion','USMajors','AMSAcquisition','USPubSec')
        )
        GROUP BY STAGE_GROUP
        ORDER BY STAGE_GROUP
    """)

    # Fetch per-use-case confidence scores for all managed partners (High confidence = score >= 75)
    # Executive email always uses: account-level CoCo ON, High confidence only
    _EMAIL_BANDS = ['High']
    managed_bulk_conf = get_bulk_confidence_scores(conn, MANAGED_PARTNERS, Q2_START, Q2_END)
    # GSIs: global scope (all theaters), EY aliases merged.
    # Regional SIs: NoAM only (consistent with OKR tracking scope).
    if len(managed_bulk_conf) > 0:
        _gsi_rows = managed_bulk_conf[managed_bulk_conf['PARTNER_NAME'].isin(_GSI_NAMES)].copy()
        _regional_rows = managed_bulk_conf[~managed_bulk_conf['PARTNER_NAME'].isin(_GSI_NAMES)].copy()
        # Regional SIs → NoAM only
        _regional_rows = _regional_rows[
            _regional_rows['THEATER_NAME'].isin(['AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec'])
        ]
        # Merge aliases into canonical names
        _gsi_rows['PARTNER_NAME'] = _gsi_rows['PARTNER_NAME'].replace(
            {'Ernst & Young (EY)': 'EY', 'IBM Consulting': 'IBM'}
        )
        _regional_rows['PARTNER_NAME'] = _regional_rows['PARTNER_NAME'].replace(
            {'Kipi.ai': 'kipi.ai', 'LTI Mindtree': 'LTM'}
        )
        managed_bulk_conf = pd.concat([_gsi_rows, _regional_rows], ignore_index=True)

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
managed_inactive_partners = 35 - managed_total_partners
managed_inactive_names = [p for p in MANAGED_PARTNERS if p not in partner_data['PARTNER_NAME'].values]

# Compute full per-partner OKR summary (all managed partners, not capped at 15)
# Used to accurately report partners meeting/below the 50% target
if len(managed_bulk_conf) > 0:
    _full_partner_summary = managed_bulk_conf.groupby('PARTNER_NAME').agg(
        TOTAL_UCS=('USE_CASE_ID', 'count'),
        COCO_UCS=('IS_COCO_FINAL', 'sum'),
    ).reset_index()
    _full_partner_summary['COCO_PCT'] = round(
        _full_partner_summary['COCO_UCS'] * 100.0 / _full_partner_summary['TOTAL_UCS'].replace(0, float('nan')), 1
    ).fillna(0)
    partners_meeting_50 = int((_full_partner_summary['COCO_PCT'] >= 50).sum())
    partners_meeting_list = ', '.join(_full_partner_summary[_full_partner_summary['COCO_PCT'] >= 50]['PARTNER_NAME'].tolist())
    partners_below_50 = int((_full_partner_summary['COCO_PCT'] < 50).sum())
else:
    partners_meeting_50 = 0
    partners_meeting_list = 'N/A'
    partners_below_50 = managed_total_partners

# Upsert current week's count into COCO_OKR_TARGET_WEEKLY (freezes automatically when week rolls over)
try:
    save_okr_target_count(conn, partners_meeting_50, managed_total_partners)
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

partner_ctx = ""
for _, p in managed_q2_partners.iterrows():
    eacv = p.get('TOTAL_EACV', 0) or 0
    partner_ctx += f"  {p['PARTNER_NAME']}: {int(p['TOTAL_UCS'])} UCs, {int(p['COCO_UCS'])} CoCo ({int(p['COCO_PCT'])}%), ${eacv/1000:.0f}K, AI={int(p['AI'])}, DE={int(p['DE'])}, Analytics={int(p['ANALYTICS'])}\n"

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
        credit_ctx += f"  {cr['PARTNER_NAME']}: Q2 Total=${cr['Q2_TOTAL_CREDITS']:,.0f}, Accounts={int(cr['COCO_CUSTOMER_ACCOUNTS'])}, Active Days={int(cr['ACTIVE_DAYS'])}, WoW={wow}\n"



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
_okr_target_ucs = _math.ceil(_live_total * 0.50)   # target = 50% of total UCs
_okr_gap_ucs    = _live_coco - _okr_target_ucs      # negative = short of target
_okr_target_pct = 50.0
_okr_gap_pct    = round(_live_pct - _okr_target_pct, 1)
# Partners meeting 50% per partner — computed from managed_bulk_conf
_p_meeting_50 = 0
if len(managed_bulk_conf) > 0:
    _pm = (managed_bulk_conf.groupby('PARTNER_NAME')
           .agg(T=('USE_CASE_ID','count'), C=('IS_COCO_FINAL','sum'))
           .assign(PCT=lambda d: d['C']/d['T'].replace(0, float('nan'))))
    _p_meeting_50 = int((_pm['PCT'] >= 0.50).sum())

okr_headline_ctx = (
    f"  Scope: 6 GSIs (Global all regions) + 14 RSIs (NoAM only)\n"
    f"  Total Use Cases: {_live_total}\n"
    f"  CoCo Use Cases (Current): {_live_coco}\n"
    f"  CoCo Adoption % (Current): {_live_pct}%\n"
    f"  Target CoCo UCs (50% of total): {_okr_target_ucs}\n"
    f"  Target CoCo Adoption %: {_okr_target_pct}%\n"
    f"  Gap (UCs): {_okr_gap_ucs:+d}\n"
    f"  Gap (Adoption %): {_okr_gap_pct:+.1f}pp\n"
    f"  Partners Meeting 50% Target: {_p_meeting_50}/20\n"
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
# NoAM: managed_bulk_conf (all 20 managed partners, NoAM scope)
# EMEA/APJ: gsi_bulk_conf (6 GSIs only) — same account pool as OKR Coverage with GSI filter
regional_okr_ctx = ""

# NoAM row — managed_bulk_conf NoAM rows (GSI NoAM + RSI NoAM, all 20 managed partners)
if len(managed_bulk_conf) > 0:
    _noam = managed_bulk_conf[managed_bulk_conf['REGION'] == 'NoAM']
    if len(_noam) > 0:
        _noam_total = len(_noam)
        _noam_coco  = int(_noam['IS_COCO_FINAL'].sum())
        _noam_pct   = round(_noam_coco * 100.0 / _noam_total, 1)
        _np = _noam.groupby('PARTNER_NAME').agg(T=('USE_CASE_ID','count'), C=('IS_COCO_FINAL','sum')).reset_index()
        _np['PCT'] = _np['C'] / _np['T'].replace(0, float('nan'))
        regional_okr_ctx += (
            f"  NoAM (6 GSI + 14 RSI): {_noam_total} total UCs, "
            f"{_noam_coco} CoCo UCs, {_noam_pct}% CoCo, "
            f"{int((_np['PCT'] >= 0.5).sum())} partners meeting 50%\n"
        )

# EMEA and APJ rows — gsi_bulk_conf (6 GSIs only, same pool as OKR Coverage GSI filter)
if len(gsi_bulk_conf) > 0 and 'REGION' in gsi_bulk_conf.columns and 'IS_COCO_FINAL' in gsi_bulk_conf.columns:
    for _rname in ['EMEA', 'APJ']:
        _gr = gsi_bulk_conf[gsi_bulk_conf['REGION'] == _rname]
        if len(_gr) > 0:
            _gr_total = len(_gr)
            _gr_coco  = int(_gr['IS_COCO_FINAL'].sum())
            _gr_pct   = round(_gr_coco * 100.0 / _gr_total, 1)
            _gp = _gr.groupby('PARTNER_NAME').agg(T=('USE_CASE_ID','count'), C=('IS_COCO_FINAL','sum')).reset_index()
            _gp['PCT'] = _gp['C'] / _gp['T'].replace(0, float('nan'))
            regional_okr_ctx += (
                f"  {_rname} (6 GSIs): {_gr_total} total UCs, "
                f"{_gr_coco} CoCo UCs, {_gr_pct}% CoCo, "
                f"{int((_gp['PCT'] >= 0.5).sum())} partners meeting 50%\n"
            )

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
=== Q2 (May-Jul 2026) | MANAGED PARTNERS ONLY (20) | Stages 3-7 ===
NOTE: All numbers are Q2 only (May 1 - Jul 31, 2026) for the 20 managed partners, except REGIONAL BREAKDOWN which shows all partners.

GLOBAL REFERENCE (all partners, Q2, Stages 3-7, with account-level attribution): {int(go['COCO_USE_CASES'])} CoCo UCs | {int(go['TOTAL_PARTNERS'])} partners | ${go['TOTAL_EACV']/1_000_000:.1f}M EACV | {go['COCO_PCT']}% CoCo adoption

MANAGED PARTNERS Q2 HEADLINE:
  CoCo Use Cases: {managed_coco_ucs} (THIS is the CoCo number for the opening sentence)
  Total Pipeline (CoCo + non-CoCo): {managed_total_ucs} use cases
  CoCo Adoption: {managed_coco_pct}%
  Active Partners: {managed_total_partners}
  Total EACV: ${managed_total_eacv/1_000_000:.1f}M
  CoCo EACV: ${managed_coco_eacv/1_000_000:.1f}M
  CoCo Deployed: {managed_coco_deployed}
  Partners Meeting 50% Target: {partners_meeting_50} ({partners_meeting_list})
  Partners Below 50% Target: {partners_below_50}
CoCo Active: {managed_total_partners} of 20 managed partners have Q2 activity
No Q2 Activity ({managed_inactive_partners} partners): {', '.join(managed_inactive_names)}

MANAGED PARTNER COCO COVERAGE (Q2, by region):
  Overall: {managed_total_ucs} total UCs, {managed_coco_ucs} CoCo, {managed_coco_pct}%
{regional_coco_ctx}

PIPELINE (Managed Partners, Q2, all UCs):
{stage_ctx}

PIPELINE WoW (all CoCo partners, use case count change vs prior week):
{pipeline_wow_ctx}

COCO CREDIT CONSUMPTION (Q2, managed partners):
{credit_ctx}

REGIONAL BREAKDOWN (Managed and Unmanaged):
{region_ctx}

PARTNER SCORECARD (all 20 managed partners, by EACV, with CoCo coverage — target 50%):
{partner_ctx}

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

OKR PROGRESS — REGIONAL BREAKDOWN (current week; NoAM=6 GSI + 14 RSI, EMEA/APJ=GSIs only):
{regional_okr_ctx}

COMMENT HIGHLIGHTS (managed partners only, Top 10 by EACV):
{comment_ctx}

RECENT ACTIVITY — LAST 7 DAYS (deployments, competitive wins, pipeline moves):
{recent_wins_ctx}
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

default_prompt = f"""You are writing a polished executive briefing for Snowflake leadership on CoCo partner use case performance. This will be read by VPs and the CEO — keep it sharp, data-rich, and action-oriented.
Do NOT include a title, heading, or subject line like "Cortex Code (CoCo) Partner Use Case Traction" at the top of the email. Start directly with the Note block.

SCOPE: Focus on the 20 managed partners. **GSIs (6) report GLOBAL numbers (NoAM + EMEA + APJ combined). RSIs (14) report NoAM-only numbers.** All sections must respect this scope.

Follow this EXACT structure with 8 sections:

## **Note: Mixed scope — 6 GSIs report globally (all regions) | 14 Regional SIs report NoAM only.**

## EXECUTIVE SUMMARY
2-3 sentences maximum, then exactly 6 bullets.
- Open with: "[X] CoCo use cases across 20 managed partners **(6 GSIs global + 14 RSIs NoAM)** representing $[Z]M in CoCo EACV, with [W] deployed in production."
- Second sentence: one crisp insight on the dominant pattern (e.g., what's working, what's accelerating).
- Bullet 1: "**Leading use case types:** [top 3 by count]"
- Bullet 2: "**CoCo Adoption (mixed scope):** [X]% overall — GSIs globally: [GSI CoCo UCs]/[GSI Total UCs] UCs | RSIs NoAM: [RSI CoCo UCs]/[RSI Total UCs] UCs"
- Bullet 3: "**Top Global SIs by EACV:** ([top 3 global partners by EACV])"
- Bullet 4: "**Top Regional SIs by EACV:** ([top 3 regional managed partners by EACV])"
- Bullet 5: "**Competitive displacement:** [top 3 competitors by count]"
- Bullet 6: "**[Detailed Partner CoCo usecase dashboard](https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/TEMP.COCO_PARTNER_ADOPTION.COCO_USECASE_INSIGHTS)**"

PARTNER CLASSIFICATION:
- Global SIs (6): EY (incl. Ernst & Young (EY)), Deloitte Consulting, Accenture, Cognizant Technology Solutions US Corp, Capgemini Technologies LLC, IBM (incl. IBM Consulting)
- Regional Managed Partners (14): 7Rivers, Aimpoint Digital, BlueCloud, kipi.ai (incl. Kipi.ai), evolv Consulting, Infostrux, Infosys, KPMG, LTM (incl. LTI Mindtree), NTT DATA, phData, Slalom, Squadron Data, Tredence

## OKR PROGRESS — REGIONAL BREAKDOWN
| Region | Scope | Total UCs | CoCo UCs | CoCo Usecase % | Partners Meeting 50% |
- Show 3 rows: NoAM, EMEA, APJ
- Use "OKR PROGRESS — REGIONAL BREAKDOWN" data from context
- NoAM row: all 20 GSI+RSI partners (NoAM scope for all)
- EMEA row: 6 GSIs only (their EMEA pipeline)
- APJ row: 6 GSIs only (their APJ pipeline)
- After table: ONE sentence — which region is lagging most and what it signals for GSI enablement focus


## MANAGED PARTNER PIPELINE OVERVIEW
| Stage | Total UCs | CoCo UCs | CoCo % | Total EACV | CoCo EACV |
- Use MANAGED PARTNERS pipeline data (stage_ctx) for all columns
- stage_ctx has: Total UCs, CoCo UCs, CoCo %, Total EACV, CoCo EACV per stage
- Use stage mapping: Validation (3), Won (4), Implementation (5-6), Deployed (7)

## PARTNER SCORECARD (all 20 managed partners)
| Partner | Total UCs | CoCo UCs | CoCo% | WoW Δ% | WoW Δ UCs | EACV | AI | DE | Analytics |
- Show ALL 20 managed partners (do not cap or truncate). Sort by EACV descending.
- **GSIs (6): Total UCs and CoCo UCs are GLOBAL (all regions combined).** RSIs (14): Total UCs and CoCo UCs are NoAM only.
- "CoCo%" = CoCo/Total for each partner's scoped data.
- WoW Δ% and WoW Δ UCs from "COCO ADOPTION WoW — PER MANAGED PARTNER" — show "-" if N/A
- Our target is **50% CoCo adoption** per partner. After the table, add ONE sentence listing the partners below 50% in ascending order of CoCo% (closest to 50% first, lowest last) — these need the most enablement focus.

## USE CASE PATTERNS (managed partners only)
3-4 bullets. Each: **Pattern Name** — one sentence with partner names and EACV.

## NOTABLE WINS (managed partners only)
2-3 bullets. **Prioritize "RECENT ACTIVITY — LAST 7 DAYS" data first** — cite specific partner + customer account + what happened.
- For [New Deployment]: "{{Partner}} deployed CoCo at {{Account}} — {{stage}}, ${{EACV}}K EACV"
- For [Competitive Win]: "{{Partner}} won {{Account}} displacing {{Competitor}} — ${{EACV}}K"
- For [Pipeline Move]: "{{Partner}} advanced {{Account}} to {{stage}} — ${{EACV}}K"
- If no recent activity, draw from COMMENT HIGHLIGHTS — focus on production deployments or executive engagement.

## DISCLAIMER
"**Disclaimer:** Use case data sourced from SE comments (coco/cortex code mentions), #coco in Partner Comments, and AI-Cortex Code feature flag. Pipeline figures are being confirmed by the PDM team and are subject to change. Detailed stats: http://go/cocopse"

FORMATTING RULES:
- Markdown tables for ALL data — no narrative paragraphs for numbers
- Executive summary: exactly 2-3 sentences + 6 bullets, nothing more
- Section headings: ## format, no numbering
- Currency: $X.XM for millions, $XK for thousands, $0 when zero
- Numbers: use commas (e.g., 1,200)
- Total length: under 600 words
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
    response_placeholder.markdown(full_response)

    st.success("Email generated successfully!")
    st.markdown("---")

    html_email = md_to_html(full_response)

    # Inject heat map after Executive Summary bullets
    if len(managed_q2_partners) > 0:
        heatmap_html = generate_heatmap_html(adoption_wow_data, managed_q2_partners)
        html_email = inject_heatmap(html_email, heatmap_html)

    # Inject partners-meeting-50% trend chart after OKR Progress table
    if trend_data:
        trend_chart_html = generate_partners_target_chart_html(trend_data)
        html_email = inject_after_okr_table(html_email, trend_chart_html)

    to_lines = [l.strip() for l in recipients_input.strip().splitlines() if l.strip()] if recipients_input.strip() else []
    to_emails = [name_to_email(n) for n in to_lines]
    to_str = ','.join(to_emails)
    subject_text = f"Cortex Code Use Case Intelligence - {datetime.now().strftime('%B %d, %Y')}"
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
st.caption("Powered by Snowflake Cortex Complete | Data sourced from CoCo Use Case Intelligence")
