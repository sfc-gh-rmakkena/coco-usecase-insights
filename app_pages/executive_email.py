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
    get_partner_coco_coverage,
)
from utils.cortex_helpers import cortex_complete

MANAGED_PARTNERS = [
    '7Rivers, Inc', 'Accenture', 'Aimpoint Digital', 'Apex Systems', 'Archetype Consulting',
    'Ateko', 'Atrium', 'Blend360, LLC', 'BlueCloud Services Inc',
    'Capgemini Technologies LLC', 'kipi.ai', 'CitiusTech Inc.',
    'Cognizant Technology Solutions US Corp', 'Deloitte Consulting', 'EY',
    'Hexaware Technologies', 'IBM', 'Icon Analytics', 'Infostrux Solutions Inc.',
    'Infosys', 'KPMG LLP', 'LTIMindtree', 'Merkle', 'NTT DATA Group Corporation',
    'OneSix', 'Perficient Inc.', 'Slalom, LLC.', 'Sparq Holdings, Inc.',
    'Spaulding Ridge', 'Squadron Data Inc', 'Coastal',
    'TEKsystems Global Services, LLC.', 'Tiger Analytics Inc.', 'Tredence Inc.',
    'evolv Consulting', 'phData, Inc.'
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
partner_filter = st.session_state.get("selected_partner", "All")

st.title(":material/mail: Executive Email Summary")
filter_label = f"Region: {region}"
if partner_filter and partner_filter != "All":
    filter_label += f" | Partner: {partner_filter}"
st.caption(f"AI-generated weekly summary for CoCo Use Case Intelligence | {filter_label}")

source_toggle = st.segmented_control("Use Case View", ["Overall", "PSE Confirmed", "Feature Flag"], default="Overall", key="email_source")
st.caption(f"Filters active: {source_toggle} use cases • {region} region")

def _apply_partner_filter(df, col='PARTNER_NAME'):
    if partner_filter and partner_filter != "All" and col in df.columns:
        return df[df[col].str.contains(partner_filter, case=False, na=False)]
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
    coco_coverage = get_partner_coco_coverage(conn, region=region)

    # Managed partner stage EACV breakdown
    managed_partners_sql = "','".join(MANAGED_PARTNERS)
    managed_stage_data = conn.query(f"""
        SELECT 
            CASE 
                WHEN USE_CASE_STAGE IN ('1 - Discovery', '2 - Scoping', '3 - Technical / Business Validation') THEN 'Active Pipeline (1-3)'
                WHEN USE_CASE_STAGE = '4 - Use Case Won / Migration Plan' THEN 'Won (4)'
                WHEN USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete') THEN 'Implementation (5-6)'
                WHEN USE_CASE_STAGE = '7 - Deployed' THEN 'Deployed (7)'
            END AS STAGE_GROUP,
            COUNT(*) AS UC_COUNT,
            COALESCE(SUM(USE_CASE_EACV), 0) AS TOTAL_EACV
        FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES
        WHERE PARTNER_NAME IN ('{managed_partners_sql}')
        AND IS_COCO = TRUE
        AND (
            (USE_CASE_STAGE IN ('1 - Discovery', '2 - Scoping', '3 - Technical / Business Validation', '4 - Use Case Won / Migration Plan') AND DECISION_DATE > '2025-11-20')
            OR (USE_CASE_STAGE IN ('5 - Implementation In Progress', '6 - Implementation Complete', '7 - Deployed') AND GO_LIVE_DATE > '2025-11-20')
        )
        GROUP BY STAGE_GROUP
        ORDER BY STAGE_GROUP
    """)

if partner_filter and partner_filter != "All":
    partner_data = _apply_partner_filter(partner_data)
    comment_data = _apply_partner_filter(comment_data)
    partner_workloads = _apply_partner_filter(partner_workloads)

# Filter to managed partners only for executive email context
partner_data = partner_data[partner_data['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
comment_data = comment_data[comment_data['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
partner_workloads = partner_workloads[partner_workloads['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
coco_coverage = coco_coverage[coco_coverage['PARTNER_NAME'].isin(MANAGED_PARTNERS)]
if 'PARTNER_NAME' in regional_themes.columns:
    regional_themes = regional_themes[regional_themes['PARTNER_NAME'].isin(MANAGED_PARTNERS)]

if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

# Recompute headline stats from managed-partners-only data
managed_total_ucs = int(partner_data['USE_CASE_COUNT'].sum())
managed_total_partners = len(partner_data)
managed_total_eacv = partner_data['TOTAL_EACV'].sum() or 0
managed_active = int(partner_data['ACTIVE_PIPELINE'].sum())
managed_won = int(partner_data['WON'].sum())
managed_impl = int(partner_data['IN_IMPL'].sum())
managed_deployed = int(partner_data['DEPLOYED'].sum())
managed_inactive_partners = 35 - managed_total_partners
managed_inactive_names = [p for p in MANAGED_PARTNERS if p not in partner_data['PARTNER_NAME'].values]

s = stats.iloc[0]

st.subheader("Data Summary")
with st.expander("View Raw Metrics", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Use Cases", int(s['TOTAL_USE_CASES']))
    c2.metric("Total EACV", f"${s['TOTAL_EACV']/1_000_000:.1f}M" if s['TOTAL_EACV'] else "$0")
    c3.metric("Partners", int(s['TOTAL_PARTNERS']))
    c4.metric("Accounts", int(s['TOTAL_ACCOUNTS']))

    tab1, tab2, tab3, tab4 = st.tabs(["Pipeline", "Use Case Types", "Workloads", "Competitors"])
    with tab1:
        if len(stage_data) > 0:
            st.dataframe(stage_data, hide_index=True, use_container_width=True)
    with tab2:
        if len(type_patterns) > 0:
            st.dataframe(type_patterns[['TECHNICAL_USE_CASE', 'USE_CASE_COUNT', 'TOTAL_EACV', 'PARTNER_COUNT', 'WON_PLUS']], hide_index=True, use_container_width=True)
    with tab3:
        if len(workload_data) > 0:
            st.dataframe(workload_data, hide_index=True, use_container_width=True)
    with tab4:
        if len(competitive_data) > 0:
            st.dataframe(competitive_data, hide_index=True, use_container_width=True)

coverage_map = {}
if len(coco_coverage) > 0:
    for _, cv in coco_coverage.iterrows():
        coverage_map[cv['PARTNER_NAME']] = {
            'total': int(cv['TOTAL_PARTNER_UCS']),
            'coco': int(cv['COCO_UCS']),
            'pct': float(cv['COCO_PCT'] or 0)
        }

partner_ctx = ""
for _, p in partner_data.head(15).iterrows():
    eacv = p.get('TOTAL_EACV', 0) or 0
    cv = coverage_map.get(p['PARTNER_NAME'], {})
    total_ucs = cv.get('total', '?')
    coco_ucs = cv.get('coco', int(p['USE_CASE_COUNT']))
    coco_pct = cv.get('pct', 0)
    partner_ctx += f"  {p['PARTNER_NAME']}: CoCo={coco_ucs}/{total_ucs} ({coco_pct:.0f}%), ${eacv/1000:.0f}K, Active={int(p.get('ACTIVE_PIPELINE', 0))}, Won={int(p.get('WON', 0))}, Impl={int(p.get('IN_IMPL', 0))}, Deployed={int(p.get('DEPLOYED', 0))}\n"

stage_ctx = ""
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


data_context = f"""
=== MANAGED PARTNERS ONLY (35) | {source_toggle} Use Cases | {region} Region ===
NOTE: All numbers below are for the 35 managed partners ONLY, except REGIONAL BREAKDOWN which shows all partners.

GLOBAL REFERENCE (all partners, for context only): {int(s['TOTAL_USE_CASES'])} total CoCo UCs | {int(s['TOTAL_PARTNERS'])} partners | ${s['TOTAL_EACV']/1_000_000:.1f}M EACV

MANAGED PARTNERS HEADLINE: {managed_total_ucs} CoCo UCs | {managed_total_partners} Active Managed Partners | ${managed_total_eacv/1_000_000:.1f}M EACV
Active(1-3): {managed_active} | Won(4): {managed_won} | Impl(5-6): {managed_impl} | Deployed(7): {managed_deployed}
CoCo Active: {managed_total_partners} of 35 managed partners have CoCo activity
No CoCo Activity ({managed_inactive_partners} partners): {', '.join(managed_inactive_names)}

PIPELINE (Managed Partners Only):
{stage_ctx}

REGIONAL BREAKDOWN (All Partners — managed + unmanaged):
{region_ctx}

TOP PARTNERS (by EACV, managed partners only, with CoCo coverage — target 50%):
{partner_ctx}

PARTNER WORKLOAD MIX (managed partners only):
{partner_wl_ctx}

COMMENT HIGHLIGHTS (managed partners only, Top 10 by EACV):
{comment_ctx}
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

default_prompt = f"""You are writing a polished executive briefing for Snowflake leadership on Cortex Code (CoCo) partner use case traction. This will be read by VPs and the CEO — keep it sharp, data-rich, and action-oriented.

SCOPE: Focus on the 35 managed partners. Use MANAGED PARTNERS HEADLINE numbers for all sections EXCEPT Regional Breakdown.
- The GLOBAL REFERENCE line is for context only — mention it once in the opening sentence.
- REGIONAL BREAKDOWN uses all-partner data (managed + unmanaged) to show geographic traction.
- ALL other sections (Pipeline, Top Partners, OKR, Patterns, Wins) use managed partners ONLY.

Follow this EXACT structure with 8 sections:

## EXECUTIVE SUMMARY
2-3 sentences maximum, then exactly 6 bullets.
- Open with: "[X] CoCo use cases across 35 managed partners representing $[Z]M in CoCo EACV, with [W] deployed in production. Global CoCo pipeline: [G] use cases across [A] partners worth $[T]M."
- Second sentence: one crisp insight on the dominant pattern (e.g., what's working, what's accelerating).
- Bullet 1: "**Leading use case types:** [top 3 by count]"
- Bullet 2: "**Region leaders:** NoAM ([top 3 partners]), EMEA ([top 3]), APJ ([top 3])"
- Bullet 3: "**Top Global SIs by EACV:** ([top 3 global partners by EACV])"
- Bullet 4: "**Top Regional SIs by EACV:** ([top 3 regional managed partners by EACV])"
- Bullet 5: "**Competitive displacement:** [top 3 competitors by count]"
- Bullet 6: "**CoCo activity:** [X] of 35 managed partners active; [Y] with no CoCo activity: [list names]"

PARTNER CLASSIFICATION:
- Global SIs (7): EY, Deloitte Consulting, Accenture, Cognizant Technology Solutions US Corp, Capgemini Technologies LLC, kipi.ai, IBM, LTIMindtree
- Regional Managed Partners (28): 7Rivers, Aimpoint Digital, Apex Systems, Archetype Consulting, Ateko, Atrium, Blend360, BlueCloud, CitiusTech, Coastal, Hexaware, Icon Analytics, Infostrux, Infosys, KPMG, Merkle, NTT DATA, OneSix, Perficient, Slalom, Sparq, Spaulding Ridge, Squadron Data, TEKsystems, Tiger Analytics, Tredence, evolv Consulting, phData

## OKR PROGRESS
| Metric | Current | Target | Gap |
- Show: CoCo use cases vs 50% target, CoCo adoption %, partners meeting 50%, CoCo EACV
- After the table: ONE sentence on what it takes to close the gap (how many more CoCo UCs needed, which partners have the biggest gaps)
- Call out partners already meeting 50% target
- Use MANAGED PARTNERS data only

## MANAGED PARTNER PIPELINE OVERVIEW
| Stage | Count | EACV |
- Use MANAGED PARTNERS pipeline data only

## REGIONAL BREAKDOWN (ALL PARTNERS — managed + unmanaged)
| Region | Use Cases | EACV | Partners |
After the table, ONE sentence per region on its dominant theme.
- This is the ONLY section that uses all-partner data

## TOP PARTNERS (managed partners only)
| Partner | Total UCs | CoCo UCs | CoCo% | EACV | AI | DE | Analytics |
- Top 12 by EACV. "Total UCs" = all partner use cases (stages 3-7). "CoCo%" = CoCo/Total.
- Our target is **50% CoCo adoption** per partner. After the table, add ONE sentence calling out which partners are closest to 50% and which need enablement focus.

## USE CASE PATTERNS (managed partners only)
3-4 bullets. Each: **Pattern Name** — one sentence with partner names and EACV.

## NOTABLE WINS (managed partners only)
2-3 bullets. Cite specific partner + customer account + what happened. Focus on production deployments, competitive wins, or executive-level engagement.

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
