import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from utils.queries import get_adoption_overview, get_adoption_by_partner, get_adoption_by_stage, get_adoption_by_region, get_by_technical_type, get_by_account_gvp, get_bulk_confidence_scores, get_partner_coco_coverage, get_all_uc_counts, get_all_uc_counts_by_theatre, get_partner_metrics_by_theatre, get_all_uc_counts_by_region, get_partner_metrics_by_region, get_apj_rsi_adoption, get_emea_rsi_adoption, get_latam_rsi_adoption, get_gsi_adoption, get_noam_rsi_adoption, get_coco_final_wow
from utils import resolve_partner_filter, resolve_region_theaters, filter_out_partner_own_accounts, apply_coco_final
from utils.config import get_schema
from utils import APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, LATAM_RSI_REGION_MAP
from utils import PARTNER_ALIASES as _PA_EARLY

# Combined set of all managed partner names (GSI + NOAM RSI + APJ RSI + EMEA RSI)
# Used to scope the top summary metrics to the managed partner universe only
_GSI_PARTNER_NAMES = {
    'Accenture', 'Capgemini Technologies LLC',
    'Cognizant Technology Solutions US Corp', 'Deloitte Consulting',
    'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting',
}
_NOAM_RSI_PARTNER_NAMES = set(
    p for p in _PA_EARLY.get('--- NOAM RSIs ---', []) if not p.startswith('---')
) | {'LTI Mindtree', 'Kipi.ai'}
_APJ_RSI_PARTNER_NAMES  = set(APJ_RSI_REGION_MAP.keys())
_EMEA_RSI_PARTNER_NAMES = set(EMEA_RSI_REGION_MAP.keys())
_LATAM_RSI_PARTNER_NAMES = set(LATAM_RSI_REGION_MAP.keys())
_ALL_MANAGED_PARTNERS   = _GSI_PARTNER_NAMES | _NOAM_RSI_PARTNER_NAMES | _APJ_RSI_PARTNER_NAMES | _EMEA_RSI_PARTNER_NAMES | _LATAM_RSI_PARTNER_NAMES


def _sql_list(values):
    return "','".join(str(v).replace("'", "''") for v in sorted(set(values)))


@st.cache_data(ttl=30 * 60)
def _get_gsi_noam_snapshot_trend(_conn, gsi_names, noam_names):
    """Weekly GSI/NOAM adoption trend from the Q3 snapshot table.

    This is the same snapshot basis as the WoW Δ UCs columns: net movement in the
    Q3-scoped stock of use cases, not CREATED_DATE. GSI is global; NOAM RSI is
    restricted to REGION='NoAM'.
    """
    snapshot_table = f"{get_schema()}.IS_COCO_FINAL_WEEKLY_SNAPSHOT_Q3"
    gsi_sql = _sql_list(gsi_names)
    noam_sql = _sql_list(noam_names)
    return _conn.query(f"""
        WITH deduped AS (
            SELECT WEEK_START, PARTNER_NAME, REGION, TOTAL_UCS, COCO_UCS
            FROM {snapshot_table}
            WHERE (
                (PARTNER_NAME IN ('{gsi_sql}')  AND REGION = 'Global')
                OR (PARTNER_NAME IN ('{noam_sql}') AND REGION = 'NoAM')
            )
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY WEEK_START, PARTNER_NAME, REGION
                ORDER BY SAVED_AT
            ) = 1
        ), grouped AS (
            SELECT WEEK_START,
                   CASE WHEN REGION = 'Global' THEN 'GSI' ELSE 'NOAM RSI' END AS GROUP_NAME,
                   SUM(TOTAL_UCS) AS TOTAL_UCS,
                   SUM(COCO_UCS) AS COCO_UCS
            FROM deduped
            GROUP BY 1, 2
        )
        SELECT WEEK_START, GROUP_NAME, TOTAL_UCS, COCO_UCS,
               ROUND(COCO_UCS * 100.0 / NULLIF(TOTAL_UCS, 0), 1) AS COCO_PCT
        FROM grouped
        ORDER BY WEEK_START, GROUP_NAME
    """)


def _forecast_snapshot_group(rows, q_end, target_pct=75.0):
    """Linear quarter-end forecast from recent weekly snapshot deltas."""
    if rows is None or len(rows) == 0:
        return None
    work = rows.sort_values('WEEK_START').copy()
    for c in ['TOTAL_UCS', 'COCO_UCS', 'COCO_PCT']:
        work[c] = pd.to_numeric(work[c], errors='coerce').fillna(0)
    latest = work.iloc[-1]
    deltas = work[['TOTAL_UCS', 'COCO_UCS']].diff().tail(3)
    avg_total_delta = float(deltas['TOTAL_UCS'].mean() or 0)
    avg_coco_delta = float(deltas['COCO_UCS'].mean() or 0)
    latest_week = pd.to_datetime(latest['WEEK_START']).date()
    quarter_end = pd.to_datetime(q_end).date()
    weeks_left = max(0, -((latest_week - quarter_end).days // 7))
    projected_total = max(0, float(latest['TOTAL_UCS']) + avg_total_delta * weeks_left)
    projected_coco = min(projected_total, max(0, float(latest['COCO_UCS']) + avg_coco_delta * weeks_left))
    projected_pct = round(projected_coco * 100.0 / projected_total, 1) if projected_total else 0.0
    required_total = projected_total
    required_coco_delta = max(0.0, (target_pct / 100.0 * required_total) - float(latest['COCO_UCS']))
    required_weekly = required_coco_delta / weeks_left if weeks_left > 0 else required_coco_delta
    if projected_pct >= target_pct:
        status = 'On track'
    elif avg_coco_delta <= 0:
        status = 'Unlikely at current pace'
    else:
        status = 'Needs acceleration'
    return {
        'current_pct': float(latest['COCO_PCT']),
        'current_coco': int(latest['COCO_UCS']),
        'current_total': int(latest['TOTAL_UCS']),
        'avg_coco_delta': round(avg_coco_delta, 1),
        'avg_total_delta': round(avg_total_delta, 1),
        'projected_pct': projected_pct,
        'required_weekly': round(required_weekly, 1),
        'weeks_left': int(weeks_left),
        'status': status,
    }

# NoAM theater list — needed by managed-bc builder and region breakdown
_NOAM_THEATERS = ('AMSExpansion', 'USMajors', 'AMSAcquisition', 'USPubSec')

from utils.ask_ai import build_filter_context

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])
selected_subregions = st.session_state.get("selected_subregions", []) or []
start_date = str(st.session_state.get("okr_start_date", "2026-05-01"))
end_date = str(st.session_state.get("okr_end_date", "2026-07-31"))
# Resolved theater tuple for the selected region — passed to SQL queries so they respect the region filter
_sidebar_theaters = None
if region and region != 'Global':
    _t = resolve_region_theaters(region)
    if _t is not None:
        _sidebar_theaters = tuple(_t)
include_account_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter = st.session_state.get("confidence_filter", ["High"])
confidence = 'High' if confidence_filter == ['High'] else ('Medium' if confidence_filter else None)

st.title(":material/monitoring: CoCo Use Case Adoption Overview")
st.caption(f"High-level metrics across all partner CoCo use cases | Region: {region} | {start_date} to {end_date}")

# ── Snowflake-blue KPI tiles for partner group sections (inside expanders) ───
st.markdown("""
<style>
[data-testid="stExpander"] [data-testid="stMetric"] {
    background: linear-gradient(135deg, #a8dff5 0%, #6ec5ed 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 4px rgba(41,181,232,.2) !important;
    padding: 8px 10px !important;
    min-height: unset !important;
}
[data-testid="stExpander"] [data-testid="stMetricLabel"] p,
[data-testid="stExpander"] [data-testid="stMetricLabel"] span {
    color: rgba(0,40,70,0.8) !important;
    font-weight: 700 !important;
    font-size: 10px !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
[data-testid="stExpander"] [data-testid="stMetricValue"] {
    color: #003a5c !important;
    font-weight: 800 !important;
    font-size: 20px !important;
}
[data-testid="stExpander"] [data-testid="stMetricDelta"] {
    color: rgba(0,40,70,0.65) !important;
    font-size: 10px !important;
}
.coco-sentiment-box {
    border: 2px solid #29B5E8;
    border-radius: 8px;
    padding: 12px 16px;
    background: rgba(41,181,232,0.06);
}
.coco-sentiment-title {
    color: #003a5c;
    font-weight: 700;
    font-size: 18px;
    margin-bottom: 10px;
}
.coco-sentiment-metrics {
    display: flex;
    gap: 48px;
}
.coco-sentiment-item {
    flex: 0 0 auto;
}
.coco-sentiment-label {
    color: #0b6c96;
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.coco-sentiment-value {
    color: #003a5c;
    font-weight: 800;
    font-size: 28px;
    line-height: 1.2;
}
</style>
""", unsafe_allow_html=True)

with st.expander(":material/info: How Use Cases Are Retrieved", expanded=False):
    st.markdown("""
    Use cases must meet **BOTH** criteria below to be included:
    
    **1. CoCo Attribution Criteria** (at least one must match):
    
    | Method | How It Works |
    |--------|-------------|
    | **SE Comments** | Contains "coco" OR "cortex code" |
    | **Partner Comments** | Contains "#coco" |
    | **Feature Flag** | Prioritized Features includes "AI - Cortex Code" |
    | **Account-Level Usage** | Customer account has actual CoCo credit consumption AND partner is mapped to that account |
    
    **2. Date Criteria** (based on use case stage):
    
    | Stage | Date Field | Requirement |
    |-------|------------|-------------|
    | **1-4** (Discovery to Won) | Decision Date | Within selected date range |
    | **5-7** (Implementation to Deployed) | Go Live Date | Within selected date range |
    
    **CoCo Partner Attribution — How It Works:**
    
    1. **Account-level (Product Usage):** Customer account consuming CoCo credits + partner mapped → partner gets attribution
    2. **Use case-level (Feature Flag):** Use case tagged with "AI - Cortex Code" + partner attached
    3. **Use case-level (Comments):** SE writes "coco"/"cortex code" OR partner writes "#coco"

    ---

    **Partner groups included in the top summary metrics** *(by default, scoped to managed partners only)*:

    | Group | Partners | Scope |
    |---|---|---|
    | **GSI** | Accenture, Capgemini Technologies LLC, Cognizant Technology Solutions US Corp, Deloitte Consulting, EY, IBM | Global |
    | **NOAM RSI** | 7Rivers, Aimpoint Digital, Everforth Apex Systems, Archetype Consulting, Atrium, Blend360, BlueCloud, CitiusTech, evolv Consulting, Hexaware, Icon Analytics, Infosys, Infostrux, kipi.ai, KPMG, LTM, Merkle, OneSix, Perficient, phData, SDK Tek, Slalom, Sparq, Spaulding Ridge, Squadron Data, Tata Consultancy Services, TEKsystems, Tiger Analytics, Tredence | NoAM theaters |
    | **APJ RSI** | NTT Data (Japan), Megazone (Korea), Infinite Lambda (ASEAN), Altis (ANZ), Prolim (India) | Country-scoped |
    | **EMEA RSI** | Infomotion (CentralEMEA), Civica (SouthEMEA), Kubrick (UK), KPC (SouthEMEA) | Region-scoped |
    """)

import pandas as pd

# Get base stats (total counts, EACV, stage info) — always use IS_COCO only for base
stats = get_adoption_overview(conn, start_date=start_date, end_date=end_date, region=region,
    partners=resolve_partner_filter(selected_partners) if selected_partners else None,
    include_account_coco=False, confidence=None, subregions=selected_subregions or None)
if len(stats) == 0:
    st.warning("No data available.")
    st.stop()

s = stats.iloc[0]

bulk_conf = pd.DataFrame()
account_level_count = 0

# Override CoCo count with full confidence scoring when account-level is enabled
if include_account_coco and selected_partners:
    partner_names = resolve_partner_filter(selected_partners)
    bulk_conf = get_bulk_confidence_scores(conn, partner_names, start_date, end_date)
    if len(bulk_conf) > 0:
        if region and region != 'Global':
            _theaters = resolve_region_theaters(region)
            if _theaters is not None:
                bulk_conf = bulk_conf[bulk_conf['THEATER_NAME'].isin(_theaters)]
        bands = confidence_filter if confidence_filter else ['High', 'Medium', 'Low']
        bulk_conf['IS_COCO_FINAL'] = apply_coco_final(bulk_conf, bands)
        coco_count = int(bulk_conf['IS_COCO_FINAL'].sum())
        total_count = len(bulk_conf)
        coco_pct = round(coco_count * 100.0 / total_count, 1) if total_count > 0 else 0
        coco_uc_display = f"{coco_count} ({coco_pct}%)"
        account_level_count = int(bulk_conf['CONFIDENCE_BAND'].isin(bands).sum())
    else:
        bulk_conf = pd.DataFrame()
        coco_uc_display = f"{int(s['COCO_USE_CASES'])} ({s['COCO_PCT']}%)"
        coco_count = int(s['COCO_USE_CASES'])
        coco_pct = float(s['COCO_PCT'] or 0)
elif include_account_coco:
    # Use canonical managed partner list (sorted) — same cache key as exec email → consistent numbers
    bulk_conf = get_bulk_confidence_scores(conn, tuple(sorted(_ALL_MANAGED_PARTNERS)), start_date, end_date)
    if len(bulk_conf) > 0:
        if region and region != 'Global':
            _theaters = resolve_region_theaters(region)
            if _theaters is not None:
                bulk_conf = bulk_conf[bulk_conf['THEATER_NAME'].isin(_theaters)]
        bands = confidence_filter if confidence_filter else ['High', 'Medium', 'Low']
        bulk_conf['IS_COCO_FINAL'] = apply_coco_final(bulk_conf, bands)
        coco_count = int(bulk_conf['IS_COCO_FINAL'].sum())
        total_count = len(bulk_conf)
        coco_pct = round(coco_count * 100.0 / total_count, 1) if total_count > 0 else 0
        coco_uc_display = f"{coco_count} ({coco_pct}%)"
        account_level_count = int(bulk_conf['CONFIDENCE_BAND'].isin(bands).sum())
    else:
        coco_count = int(s['COCO_USE_CASES'])
        coco_pct = float(s['COCO_PCT'] or 0)
        coco_uc_display = f"{coco_count} ({coco_pct}%)"
        account_level_count = 0
else:
    coco_count = int(s['COCO_USE_CASES'])
    coco_pct = float(s['COCO_PCT'] or 0)
    coco_uc_display = f"{coco_count} ({coco_pct}%)"

# All UCs (partner + non-partner) from MDM
_all_uc = get_all_uc_counts(conn, start_date, end_date, region)
_all_uc_total   = int(_all_uc.iloc[0]['ALL_USE_CASES'])   if len(_all_uc) > 0 else 0
_all_go_lives   = int(_all_uc.iloc[0]['ALL_GO_LIVES'])    if len(_all_uc) > 0 else 0

# Scope all top-summary metrics to the managed partner universe with geo restrictions
# (same filter used for theatre/region breakdowns — ensures numbers match)

# Resolved selected partner names (empty set = no filter = show all)
_selected_partner_names = set(resolve_partner_filter(selected_partners)) if selected_partners else set()

def _build_managed_bc(bc):
    """Return a bulk_conf slice covering managed partners with geo restrictions applied.
    GSI: global, NOAM RSI: NoAM theaters, APJ/EMEA/LATAM RSI: country/region-scoped.
    Respects sidebar partner filter (_selected_partner_names)."""
    if bc is None or len(bc) == 0 or 'IS_COCO_FINAL' not in bc.columns:
        return pd.DataFrame()
    parts = []
    _sel = _selected_partner_names  # shorthand; empty = no extra filter
    def _pf(names): return names & _sel if _sel else names
    parts.append(bc[bc['PARTNER_NAME'].isin(_pf(_GSI_PARTNER_NAMES))].copy())
    parts.append(bc[bc['PARTNER_NAME'].isin(_pf(_NOAM_RSI_PARTNER_NAMES)) &
                    bc['THEATER_NAME'].isin(_NOAM_THEATERS)].copy())
    if 'REGION_NAME' in bc.columns:
        _apj = bc[bc['PARTNER_NAME'].isin(_pf(_APJ_RSI_PARTNER_NAMES))].copy()
        _apj['_c'] = _apj['PARTNER_NAME'].map({k: v[1] for k, v in APJ_RSI_REGION_MAP.items()})
        parts.append(_apj[_apj['REGION_NAME'] == _apj['_c']].drop(columns=['_c']))
        _emea = bc[bc['PARTNER_NAME'].isin(_pf(_EMEA_RSI_PARTNER_NAMES))].copy()
        _emea['_c'] = _emea['PARTNER_NAME'].map({k: v[1] for k, v in EMEA_RSI_REGION_MAP.items()})
        parts.append(_emea[_emea['REGION_NAME'] == _emea['_c']].drop(columns=['_c']))
        _latam = bc[bc['PARTNER_NAME'].isin(_pf(_LATAM_RSI_PARTNER_NAMES))].copy()
        parts.append(_latam[_latam['REGION_NAME'] == 'LATAM'])
    return pd.concat([p for p in parts if len(p) > 0], ignore_index=True) if parts else pd.DataFrame()

_bc_managed = pd.DataFrame()
if len(bulk_conf) > 0 and 'IS_COCO_FINAL' in bulk_conf.columns:
    _bc_managed = _build_managed_bc(bulk_conf)
    _partner_total       = len(_bc_managed)
    _all_deployed_partner = int((_bc_managed['USE_CASE_STAGE'] == '7 - Deployed').sum())
    _cf_managed          = _bc_managed[_bc_managed['IS_COCO_FINAL']]
    coco_count           = int(_bc_managed['IS_COCO_FINAL'].sum())
    coco_pct             = round(coco_count * 100.0 / _partner_total, 1) if _partner_total > 0 else 0.0
    _go_live_coco        = int((_cf_managed['USE_CASE_STAGE'] == '7 - Deployed').sum())
    _tech_wins_coco      = int((_cf_managed['USE_CASE_STAGE'] == '4 - Use Case Won / Migration Plan').sum())
    _in_impl_coco        = int(_cf_managed['USE_CASE_STAGE'].isin(['5 - Implementation In Progress', '6 - Implementation Complete']).sum())
    _coco_eacv           = float(_cf_managed['USE_CASE_EACV'].sum() or 0)
    _total_eacv          = float(_bc_managed['USE_CASE_EACV'].sum() or 0)
    coco_uc_display      = f"{coco_count} ({coco_pct:.1f}%)"
else:
    # Fall back to raw SQL stats (no bulk_conf available)
    _partner_total        = int(s['TOTAL_USE_CASES'])
    _all_deployed_partner = int(s.get('DEPLOYED_COUNT', 0) or 0)
    _go_live_coco         = int(s.get('DEPLOYED_COUNT', 0) or 0)
    _tech_wins_coco       = int(s.get('WON_COUNT', 0) or 0)
    _in_impl_coco         = int(s.get('IMPL_COUNT', 0) or 0)
    _coco_eacv            = 0
    _total_eacv           = float(s['TOTAL_EACV'] or 0)

_go_lives_pct      = round(_all_deployed_partner * 100.0 / _partner_total, 1) if _partner_total > 0 else 0.0
_coco_go_lives_pct = round(_go_live_coco * 100.0 / coco_count, 1) if coco_count > 0 else 0.0

_snapshot_wow_lkp = {}
_snapshot_overall = {}
try:
    _snapshot_wow = get_coco_final_wow(
        conn,
        partners=tuple(sorted(_ALL_MANAGED_PARTNERS)),
        gsi_global=True,
        gsi_names=frozenset(_GSI_PARTNER_NAMES),
    )
    if len(_snapshot_wow) > 0:
        _snapshot_overall_rows = _snapshot_wow[_snapshot_wow['PARTNER_NAME'].isna()]
        if len(_snapshot_overall_rows) > 0:
            _snapshot_overall = _snapshot_overall_rows.iloc[0].to_dict()
        _snapshot_wow_lkp = {
            str(r['PARTNER_NAME']): r.to_dict()
            for _, r in _snapshot_wow[_snapshot_wow['PARTNER_NAME'].notna()].iterrows()
        }
except Exception:
    _snapshot_wow_lkp = {}
    _snapshot_overall = {}


def _apply_snapshot_wow(display_df, partner_col='PARTNER_LABEL'):
    out = display_df.copy()
    out['WOW_COCO_UCS'] = out[partner_col].apply(
        lambda p: _snapshot_wow_lkp.get(str(p), {}).get('WOW_COCO_UCS') if str(p) != 'TOTAL' else None)
    out['WOW_COCO_PCT'] = out[partner_col].apply(
        lambda p: _snapshot_wow_lkp.get(str(p), {}).get('WOW_COCO_PCT') if str(p) != 'TOTAL' else None)
    out['WOW_COCO_UCS'] = pd.to_numeric(out['WOW_COCO_UCS'], errors='coerce')
    out['WOW_COCO_PCT'] = pd.to_numeric(out['WOW_COCO_PCT'], errors='coerce')
    return out

st.markdown(
    f"""<div class="coco-sentiment-box">
  <div class="coco-sentiment-title">Overall Company Sentiment</div>
  <div class="coco-sentiment-metrics">
    <div class="coco-sentiment-item" title="All use cases in scope — partner and non-partner (MDM, Stages 3–7, date range filtered)">
      <div class="coco-sentiment-label">Total UC</div>
      <div class="coco-sentiment-value">{_all_uc_total:,}</div>
    </div>
    <div class="coco-sentiment-item" title="All Stage 7 deployed use cases regardless of partner attachment (MDM)">
      <div class="coco-sentiment-label">Total Go-Lives</div>
      <div class="coco-sentiment-value">{_all_go_lives:,}</div>
    </div>
  </div>
</div>""",
    unsafe_allow_html=True,
)

st.write("")

c3, c4, c5, c6 = st.columns(4)
_managed_partner_count = int(_bc_managed['PARTNER_NAME'].nunique()) if len(_bc_managed) > 0 else int(s['TOTAL_PARTNERS'])

c3.metric("Total Partner UC",          _partner_total,
          help="Partner-attached use cases in scope (DT_OKR_USE_CASES)")
c4.metric("Partner CoCo Usecases",     coco_count,
          f"{coco_pct:.1f}% of partner UCs",
          help="Partner use cases where IS_COCO_FINAL = true (IS_COCO flag OR confidence band)")
c5.metric("Total Partner Go-Lives",    f"{_go_lives_pct:.1f}%",
          f"{_all_deployed_partner} of {_partner_total} partner UCs",
          help="All Stage 7 partner UCs as % of all partner UCs in scope")
c6.metric("CoCo Partner Go-Lives",     f"{_coco_go_lives_pct:.1f}%",
          f"{_go_live_coco} of {coco_count} CoCo UCs",
          help="IS_COCO_FINAL Stage 7 as % of total IS_COCO_FINAL UCs — deployment rate within CoCo")

if _snapshot_overall:
    n1, n2, n3 = st.columns(3)
    n1.metric("WoW Δ CoCo UCs", f"{int(_snapshot_overall['WOW_COCO_UCS']):+d}",
              help="Net change in Q3-scoped CoCo use cases vs the prior weekly snapshot. This matches the Executive Email and partner scorecards.")
    n2.metric("WoW Δ Total UCs", f"{int(_snapshot_overall['WOW_TOTAL_UCS']):+d}",
              help="Net change in all Q3-scoped partner use cases vs the prior weekly snapshot.")
    n3.metric("WoW Δ CoCo %", f"{float(_snapshot_overall['WOW_COCO_PCT']):+.1f}pp",
              help="Percentage-point change in Q3-scoped CoCo adoption vs the prior weekly snapshot.")
    st.caption(
        f"Weekly snapshot comparison: {_snapshot_overall['WEEK_START']} vs {_snapshot_overall['PREV_WEEK']}. "
        "These are snapshot deltas, not CREATED_DATE counts."
    )

st.divider()
st.subheader("Weekly Growth & 75% Forecast")
_trend = _get_gsi_noam_snapshot_trend(conn, tuple(_GSI_PARTNER_NAMES), tuple(_NOAM_RSI_PARTNER_NAMES))
if len(_trend) > 0:
    _trend['WEEK_START'] = pd.to_datetime(_trend['WEEK_START'])
    _trend['COCO_PCT'] = pd.to_numeric(_trend['COCO_PCT'], errors='coerce').fillna(0)
    _trend['COCO_UCS'] = pd.to_numeric(_trend['COCO_UCS'], errors='coerce').fillna(0).astype(int)
    _trend['TOTAL_UCS'] = pd.to_numeric(_trend['TOTAL_UCS'], errors='coerce').fillna(0).astype(int)

    _fig = go.Figure()
    for _group, _group_rows in _trend.groupby('GROUP_NAME'):
        _fig.add_trace(go.Scatter(
            x=_group_rows['WEEK_START'],
            y=_group_rows['COCO_PCT'],
            mode='lines+markers',
            name=f'{_group} CoCo %',
            customdata=_group_rows[['COCO_UCS', 'TOTAL_UCS']],
            hovertemplate='%{x|%Y-%m-%d}<br>%{y:.1f}% CoCo<br>%{customdata[0]} / %{customdata[1]} UCs<extra></extra>',
        ))
    _fig.add_hline(
        y=75,
        line_dash='dash',
        line_color='#d62728',
        annotation_text='75% target',
        annotation_position='top left',
    )
    _fig.update_layout(
        height=360,
        yaxis_title='CoCo Adoption %',
        xaxis_title='',
        yaxis=dict(range=[0, 100], ticksuffix='%'),
        legend=dict(orientation='h', y=1.12),
        margin=dict(l=20, r=20, t=30, b=20),
    )
    st.plotly_chart(_fig, use_container_width=True)

    _card_cols = st.columns(2)
    for _idx, _group in enumerate(['GSI', 'NOAM RSI']):
        _fc = _forecast_snapshot_group(_trend[_trend['GROUP_NAME'] == _group], end_date, target_pct=75.0)
        if not _fc:
            continue
        with _card_cols[_idx]:
            st.metric(
                f'{_group} projected quarter-end',
                f"{_fc['projected_pct']:.1f}%",
                f"current {_fc['current_pct']:.1f}% ({_fc['current_coco']}/{_fc['current_total']} UCs)",
            )
            st.caption(
                f"{_fc['status']} | Last-3-week avg: +{_fc['avg_coco_delta']:.1f} CoCo UCs/wk, "
                f"+{_fc['avg_total_delta']:.1f} total UCs/wk | Need +{_fc['required_weekly']:.1f} CoCo UCs/wk "
                f"over {_fc['weeks_left']} weeks to reach 75%."
            )
    st.caption("Forecast uses weekly snapshot deltas, not CREATED_DATE. It projects both CoCo UCs and total UCs using the last 3 weekly changes.")
else:
    st.info("Weekly snapshot trend is not available yet.")


st.caption(
    "By default, partner metrics (Total Partner UC, Partner CoCo Usecases, Go-Lives) are scoped to "
    "managed partners: **GSI · NOAM RSI · APJ RSI · EMEA RSI · LATAM RSI**"
)

# 4 gauges — one per partner group
def _group_stats(bc, names):
    """Return (total, coco, pct) for a partner name set from managed bulk_conf."""
    if bc is None or len(bc) == 0 or 'IS_COCO_FINAL' not in bc.columns:
        return 0, 0, 0.0
    _g = bc[bc['PARTNER_NAME'].isin(names)]
    total = len(_g)
    coco  = int(_g['IS_COCO_FINAL'].sum())
    pct   = round(coco * 100.0 / total, 1) if total > 0 else 0.0
    return total, coco, pct

_gauge_bc = _bc_managed if (len(bulk_conf) > 0 and 'IS_COCO_FINAL' in bulk_conf.columns) else pd.DataFrame()

def _make_gauge(label, pct, total, coco, target):
    steps = (
        [{"range": [0, target/2],  "color": "#fde8e8"},
         {"range": [target/2, target], "color": "#fef3cd"},
         {"range": [target, 100], "color": "#d4edda"}]
    )
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=pct,
        number={"suffix": "%", "font": {"size": 26, "color": "#003a5c"}},
        delta={"reference": target, "suffix": "%", "valueformat": ".1f",
               "increasing": {"color": "#27ae60"}, "decreasing": {"color": "#e74c3c"}},
        domain={"x": [0, 1], "y": [0, 0.75]},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#bbb",
                     "tickvals": [0, target, 100],
                     "tickfont": {"size": 10, "color": "#666"}},
            "bar": {"color": "#003a5c", "thickness": 0.3},
            "bgcolor": "#f9f9f9",
            "borderwidth": 1, "bordercolor": "#e0e0e0",
            "steps": steps,
            "threshold": {"line": {"color": "#c0392b", "width": 3},
                          "thickness": 0.8, "value": target},
        },
    ))
    fig.add_annotation(
        x=0.5, y=1.0, xref="paper", yref="paper",
        text=f"<b>{label}</b><br><span style='font-size:11px;color:#666'>{coco}/{total} UCs · target {target}%</span>",
        showarrow=False, align="center",
        font={"size": 13, "color": "#333"},
        xanchor="center", yanchor="top",
    )
    fig.update_layout(
        height=250,
        margin=dict(t=55, b=10, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#333"},
    )
    return fig

_gsi_total,  _gsi_coco,  _gsi_pct  = _group_stats(_gauge_bc, _GSI_PARTNER_NAMES)
_noam_total, _noam_coco, _noam_pct = _group_stats(_gauge_bc, _NOAM_RSI_PARTNER_NAMES)
_apj_total,  _apj_coco,  _apj_pct  = _group_stats(_gauge_bc, _APJ_RSI_PARTNER_NAMES)
_emea_total, _emea_coco, _emea_pct = _group_stats(_gauge_bc, _EMEA_RSI_PARTNER_NAMES)
_latam_total, _latam_coco, _latam_pct = _group_stats(_gauge_bc, _LATAM_RSI_PARTNER_NAMES)
_gc1, _gc2, _gc3, _gc4, _gc5 = st.columns(5)
_gc1.plotly_chart(_make_gauge("GSI",      _gsi_pct,  _gsi_total,  _gsi_coco,  75), use_container_width=True)
_gc2.plotly_chart(_make_gauge("NOAM RSI", _noam_pct, _noam_total, _noam_coco, 75), use_container_width=True)
_gc3.plotly_chart(_make_gauge("APJ RSI",  _apj_pct,  _apj_total,  _apj_coco,  50), use_container_width=True)
_gc4.plotly_chart(_make_gauge("EMEA RSI", _emea_pct, _emea_total, _emea_coco, 50), use_container_width=True)
_gc5.plotly_chart(_make_gauge("LATAM RSI", _latam_pct, _latam_total, _latam_coco, 50), use_container_width=True)

st.divider()

def _build_partner_theatre_from_bulk(bc):
    """Derive per-theatre partner CoCo metrics from bulk_conf (IS_COCO_FINAL)."""
    _bc = bc.copy()
    _bc['_deployed_coco'] = _bc['IS_COCO_FINAL'] & (_bc['USE_CASE_STAGE'] == '7 - Deployed')
    _bc['_deployed_all'] = (_bc['USE_CASE_STAGE'] == '7 - Deployed')
    grp = (
        _bc.groupby('THEATER_NAME', dropna=True)
        .agg(TOTAL_PARTNER_UCS=('USE_CASE_ID', 'count'),
             COCO_UCS=('IS_COCO_FINAL', 'sum'),
             DEPLOYED_COCO=('_deployed_coco', 'sum'),
             DEPLOYED_ALL=('_deployed_all', 'sum'))
        .reset_index()
    )
    grp['GO_LIVE_PCT'] = (grp['DEPLOYED_ALL'] * 100.0 /
                          grp['TOTAL_PARTNER_UCS'].replace(0, float('nan'))).round(1).fillna(0)
    grp['COCO_GO_LIVE_PCT'] = (grp['DEPLOYED_COCO'] * 100.0 /
                                grp['COCO_UCS'].replace(0, float('nan'))).round(1).fillna(0)
    # Token aggregation: IS_COCO_FINAL accounts only, deduped per (theatre, account)
    _tok_cols = ['LAST7_TOKENS', 'PRIOR7_TOKENS']
    if all(c in _bc.columns for c in _tok_cols) and 'ACCOUNT_NAME_UPPER' in _bc.columns:
        _coco = _bc[_bc['IS_COCO_FINAL']].copy()
        for c in _tok_cols:
            _coco[c] = pd.to_numeric(_coco[c], errors='coerce').fillna(0)
        _tok_dedup = _coco.drop_duplicates(subset=['THEATER_NAME', 'ACCOUNT_NAME_UPPER'])
        _tok_grp = _tok_dedup.groupby('THEATER_NAME')[_tok_cols].sum().reset_index()
        grp = grp.merge(_tok_grp, on='THEATER_NAME', how='left')
        for c in _tok_cols:
            grp[c] = grp[c].fillna(0).astype(int)
        grp['TOKENS_WOW_PCT'] = (
            (grp['LAST7_TOKENS'] - grp['PRIOR7_TOKENS']) * 100.0 /
            grp['PRIOR7_TOKENS'].replace(0, float('nan'))
        ).round(1)
    return grp


def _build_partner_region_from_bulk(bc):
    """Derive per-region partner CoCo metrics from bulk_conf (IS_COCO_FINAL)."""
    _bc = bc.copy()
    # LATAM RSI partners must be bucketed as 'LATAM' regardless of their THEATER_NAME
    # (e.g. SEIDOR ANALYTICS has a NoAM theater but is LATAM-scoped)
    _latam_partner_set = set(LATAM_RSI_REGION_MAP.keys())
    _bc['REGION'] = _bc.apply(
        lambda r: 'LATAM' if r['PARTNER_NAME'] in _latam_partner_set
        else ('NoAM' if r['THEATER_NAME'] in _NOAM_THEATERS
              else ('EMEA' if r['THEATER_NAME'] == 'EMEA'
                    else ('APJ' if r['THEATER_NAME'] == 'APJ' else 'Other'))),
        axis=1
    )
    _bc['_deployed_coco'] = _bc['IS_COCO_FINAL'] & (_bc['USE_CASE_STAGE'] == '7 - Deployed')
    _bc['_deployed_all'] = (_bc['USE_CASE_STAGE'] == '7 - Deployed')
    grp = (
        _bc.groupby('REGION', dropna=True)
        .agg(TOTAL_PARTNER_UCS=('USE_CASE_ID', 'count'),
             COCO_UCS=('IS_COCO_FINAL', 'sum'),
             DEPLOYED_COCO=('_deployed_coco', 'sum'),
             DEPLOYED_ALL=('_deployed_all', 'sum'))
        .reset_index()
    )
    grp['GO_LIVE_PCT'] = (grp['DEPLOYED_ALL'] * 100.0 /
                          grp['TOTAL_PARTNER_UCS'].replace(0, float('nan'))).round(1).fillna(0)
    grp['COCO_GO_LIVE_PCT'] = (grp['DEPLOYED_COCO'] * 100.0 /
                                grp['COCO_UCS'].replace(0, float('nan'))).round(1).fillna(0)
    # Token aggregation: IS_COCO_FINAL accounts only, deduped per (region, account)
    _tok_cols = ['LAST7_TOKENS', 'PRIOR7_TOKENS']
    if all(c in _bc.columns for c in _tok_cols) and 'ACCOUNT_NAME_UPPER' in _bc.columns:
        _coco = _bc[_bc['IS_COCO_FINAL']].copy()
        for c in _tok_cols:
            _coco[c] = pd.to_numeric(_coco[c], errors='coerce').fillna(0)
        _tok_dedup = _coco.drop_duplicates(subset=['REGION', 'ACCOUNT_NAME_UPPER'])
        _tok_grp = _tok_dedup.groupby('REGION')[_tok_cols].sum().reset_index()
        grp = grp.merge(_tok_grp, on='REGION', how='left')
        for c in _tok_cols:
            grp[c] = grp[c].fillna(0).astype(int)
        grp['TOKENS_WOW_PCT'] = (
            (grp['LAST7_TOKENS'] - grp['PRIOR7_TOKENS']) * 100.0 /
            grp['PRIOR7_TOKENS'].replace(0, float('nan'))
        ).round(1)
    return grp

# ── Managed-partner geo-scoped bulk_conf (reuse for Theatre/Region breakdowns) ─
_managed_bc = _bc_managed if len(bulk_conf) > 0 and 'IS_COCO_FINAL' in bulk_conf.columns else pd.DataFrame()

# ── Breakdown by Theatre ──────────────────────────────────────────────────────
with st.expander(":material/table: Breakdown by Theatre", expanded=True):
    st.caption("Partner CoCo UCs = IS_COCO_FINAL | Scoped to managed partners: GSI · NOAM RSI · APJ RSI · EMEA RSI · LATAM RSI")
    _theatre_mdm = get_all_uc_counts_by_theatre(conn, start_date, end_date)
    # Housekeeping theatres, not real go-to-market territories. Filtered here rather
    # than at render time so the TOTAL row excludes them too.
    if len(_theatre_mdm) > 0:
        _theatre_mdm = _theatre_mdm[
            ~_theatre_mdm["THEATER_NAME"].str.strip().str.upper()
            .isin({"ACCTSTODELETE", "AMSPARTNER"})]
    # Derive partner side from managed bulk_conf (IS_COCO_FINAL) when available; SQL fallback otherwise
    if len(_managed_bc) > 0 and 'IS_COCO_FINAL' in _managed_bc.columns:
        _theatre_partner = _build_partner_theatre_from_bulk(_managed_bc)
    else:
        _theatre_partner = get_partner_metrics_by_theatre(conn, start_date, end_date)
    if len(_theatre_mdm) > 0:
        _t = _theatre_mdm.set_index("THEATER_NAME")[["ALL_USE_CASES", "ALL_GO_LIVES"]]
        if len(_theatre_partner) > 0:
            _tp_cols = ["TOTAL_PARTNER_UCS", "COCO_UCS", "DEPLOYED_ALL", "GO_LIVE_PCT", "DEPLOYED_COCO", "COCO_GO_LIVE_PCT"]
            _t_has_tokens = all(c in _theatre_partner.columns for c in ['LAST7_TOKENS', 'TOKENS_WOW_PCT'])
            if _t_has_tokens:
                _tp_cols += ['LAST7_TOKENS', 'TOKENS_WOW_PCT']
            _tp = _theatre_partner.set_index("THEATER_NAME")[_tp_cols]
            _theatre_combined = _t.join(_tp, how="left").reset_index()
        else:
            _theatre_combined = _t.reset_index()
            _theatre_combined["TOTAL_PARTNER_UCS"] = 0
            _theatre_combined["COCO_UCS"] = 0
            _theatre_combined["DEPLOYED_ALL"] = 0
            _theatre_combined["GO_LIVE_PCT"] = 0.0
            _theatre_combined["DEPLOYED_COCO"] = 0
            _theatre_combined["COCO_GO_LIVE_PCT"] = 0.0
            _t_has_tokens = False
        _theatre_combined.columns = ["Theatre", "Overall UCs", "Go Live UCs",
                                      "Total Partner UCs", "Partner CoCo UCs", "_dep_all", "_pct_all", "_dep_coco", "_pct_coco"] + (
                                     ["Last 7d Tokens", "7D Tokens WoW%"] if _t_has_tokens else [])
        _theatre_combined = _theatre_combined.drop(columns=["Overall UCs", "Go Live UCs"])
        _theatre_combined[["_dep_all", "_dep_coco", "_pct_all", "_pct_coco"]] = \
            _theatre_combined[["_dep_all", "_dep_coco", "_pct_all", "_pct_coco"]].fillna(0)
        _t_total_ucs  = int(_theatre_combined["Total Partner UCs"].sum())
        _t_coco_ucs   = int(_theatre_combined["Partner CoCo UCs"].sum())
        _t_dep_all    = int(_theatre_combined["_dep_all"].sum())
        _t_dep_coco   = int(_theatre_combined["_dep_coco"].sum())
        _t_pct_all    = _t_dep_all  * 100.0 / _t_total_ucs if _t_total_ucs > 0 else 0.0
        _t_pct_coco   = _t_dep_coco * 100.0 / _t_coco_ucs  if _t_coco_ucs  > 0 else 0.0
        _t_last7_tok  = int(_theatre_combined["Last 7d Tokens"].sum())  if _t_has_tokens else None
        _theatre_combined["Total Partner Go-Lives"] = _theatre_combined.apply(
            lambda r: f"{int(r['_dep_all'])} ({r['_pct_all']:.1f}%)", axis=1
        )
        _theatre_combined["CoCo Partner Go-Lives"] = _theatre_combined.apply(
            lambda r: f"{int(r['_dep_coco'])} ({r['_pct_coco']:.1f}%)", axis=1
        )
        _theatre_combined = _theatre_combined.drop(columns=["_dep_all", "_pct_all", "_dep_coco", "_pct_coco"])
        _theatre_combined = _theatre_combined.fillna(0)
        _theatre_combined["Total Partner UCs"] = _theatre_combined["Total Partner UCs"].astype(int)
        _theatre_combined["Partner CoCo UCs"]  = _theatre_combined["Partner CoCo UCs"].astype(int)
        _theatre_total = pd.DataFrame([{
            "Theatre": "TOTAL",
            "Total Partner UCs": _t_total_ucs,
            "Partner CoCo UCs": _t_coco_ucs,
            "Total Partner Go-Lives": f"{_t_dep_all} ({_t_pct_all:.1f}%)",
            "CoCo Partner Go-Lives": f"{_t_dep_coco} ({_t_pct_coco:.1f}%)",
            **({
                "Last 7d Tokens": _t_last7_tok,
                "7D Tokens WoW%": None,
            } if _t_has_tokens else {}),
        }])
        _t_col_cfg = {}
        if _t_has_tokens:
            _t_col_cfg = {
                "Last 7d Tokens": st.column_config.NumberColumn(format="%d", help="Token usage in last 7 rolling days — IS_COCO_FINAL accounts only"),
                "7D Tokens WoW%": st.column_config.NumberColumn(format="%+.1f%%", help="Week-over-week % change in tokens (last 7d vs prior 7d)"),
            }
        _t_df = pd.concat([_theatre_combined, _theatre_total], ignore_index=True)
        def _t_wow_bg(val):
            if pd.isna(val) or val == 0: return ''
            return 'background-color: #d4edda; color: #155724' if val > 0 else 'background-color: #fde8e8; color: #9b2335'
        _t_display = _t_df.style.map(_t_wow_bg, subset=['7D Tokens WoW%']) if _t_has_tokens else _t_df.style
        st.dataframe(
            _t_display,
            column_config=_t_col_cfg,
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("No theatre-level data available for the selected date range.")

# ── Breakdown by Region ───────────────────────────────────────────────────────
with st.expander(":material/public: Breakdown by Region", expanded=True):
    st.caption("Partner CoCo UCs = IS_COCO_FINAL | Scoped to managed partners: GSI · NOAM RSI · APJ RSI · EMEA RSI · LATAM RSI")
    _region_mdm = get_all_uc_counts_by_region(conn, start_date, end_date)
    # 'Other' is the ELSE bucket holding non-territory theatres (AMSPartner,
    # APJPartner, EMEAPartner, AcctsToDelete). Dropped here rather than at render
    # time so the TOTAL row excludes them too.
    if len(_region_mdm) > 0:
        _region_mdm = _region_mdm[_region_mdm["REGION"].str.strip() != "Other"]
    # Derive partner side from managed bulk_conf (IS_COCO_FINAL) when available; SQL fallback otherwise
    if len(_managed_bc) > 0 and 'IS_COCO_FINAL' in _managed_bc.columns:
        _region_partner = _build_partner_region_from_bulk(_managed_bc)
    else:
        _region_partner = get_partner_metrics_by_region(conn, start_date, end_date)
    if len(_region_partner) > 0 and "REGION" in _region_partner.columns:
        _region_partner = _region_partner[_region_partner["REGION"].str.strip() != "Other"]
    if len(_region_mdm) > 0:
        _r = _region_mdm.set_index("REGION")[["ALL_USE_CASES", "ALL_GO_LIVES"]]
        if len(_region_partner) > 0:
            _rp_cols = ["TOTAL_PARTNER_UCS", "COCO_UCS", "DEPLOYED_ALL", "GO_LIVE_PCT", "DEPLOYED_COCO", "COCO_GO_LIVE_PCT"]
            _r_has_tokens = all(c in _region_partner.columns for c in ['LAST7_TOKENS', 'TOKENS_WOW_PCT'])
            if _r_has_tokens:
                _rp_cols += ['LAST7_TOKENS', 'TOKENS_WOW_PCT']
            _rp = _region_partner.set_index("REGION")[_rp_cols]
            # Use outer join so LATAM rows (present in _rp but not in the SQL-based _r) are preserved
            _region_combined = _r.join(_rp, how="outer").reset_index()
            _region_combined[["ALL_USE_CASES", "ALL_GO_LIVES"]] = \
                _region_combined[["ALL_USE_CASES", "ALL_GO_LIVES"]].fillna(0)
        else:
            _region_combined = _r.reset_index()
            _region_combined["TOTAL_PARTNER_UCS"] = 0
            _region_combined["COCO_UCS"] = 0
            _region_combined["DEPLOYED_ALL"] = 0
            _region_combined["GO_LIVE_PCT"] = 0.0
            _region_combined["DEPLOYED_COCO"] = 0
            _region_combined["COCO_GO_LIVE_PCT"] = 0.0
            _r_has_tokens = False
        _region_combined.columns = ["Region", "Overall UCs", "Go Live UCs",
                                     "Total Partner UCs", "Partner CoCo UCs", "_dep_all", "_pct_all", "_dep_coco", "_pct_coco"] + (
                                    ["Last 7d Tokens", "7D Tokens WoW%"] if _r_has_tokens else [])
        _region_combined = _region_combined.drop(columns=["Overall UCs", "Go Live UCs"])
        _region_combined[["_dep_all", "_dep_coco", "_pct_all", "_pct_coco"]] = \
            _region_combined[["_dep_all", "_dep_coco", "_pct_all", "_pct_coco"]].fillna(0)
        _r_total_ucs  = int(_region_combined["Total Partner UCs"].sum())
        _r_coco_ucs   = int(_region_combined["Partner CoCo UCs"].sum())
        _r_dep_all    = int(_region_combined["_dep_all"].sum())
        _r_dep_coco   = int(_region_combined["_dep_coco"].sum())
        _r_pct_all    = _r_dep_all  * 100.0 / _r_total_ucs if _r_total_ucs > 0 else 0.0
        _r_pct_coco   = _r_dep_coco * 100.0 / _r_coco_ucs  if _r_coco_ucs  > 0 else 0.0
        _r_last7_tok  = int(_region_combined["Last 7d Tokens"].sum()) if _r_has_tokens else None
        _region_combined["Total Partner Go-Lives"] = _region_combined.apply(
            lambda r: f"{int(r['_dep_all'])} ({r['_pct_all']:.1f}%)", axis=1
        )
        _region_combined["CoCo Partner Go-Lives"] = _region_combined.apply(
            lambda r: f"{int(r['_dep_coco'])} ({r['_pct_coco']:.1f}%)", axis=1
        )
        _region_combined = _region_combined.drop(columns=["_dep_all", "_pct_all", "_dep_coco", "_pct_coco"])
        _region_combined = _region_combined.fillna(0)
        _region_combined["Total Partner UCs"] = _region_combined["Total Partner UCs"].astype(int)
        _region_combined["Partner CoCo UCs"]  = _region_combined["Partner CoCo UCs"].astype(int)
        _region_total = pd.DataFrame([{
            "Region": "TOTAL",
            "Total Partner UCs": _r_total_ucs,
            "Partner CoCo UCs": _r_coco_ucs,
            "Total Partner Go-Lives": f"{_r_dep_all} ({_r_pct_all:.1f}%)",
            "CoCo Partner Go-Lives": f"{_r_dep_coco} ({_r_pct_coco:.1f}%)",
            **({
                "Last 7d Tokens": _r_last7_tok,
                "7D Tokens WoW%": None,
            } if _r_has_tokens else {}),
        }])
        _r_col_cfg = {}
        if _r_has_tokens:
            _r_col_cfg = {
                "Last 7d Tokens": st.column_config.NumberColumn(format="%d", help="Token usage in last 7 rolling days — IS_COCO_FINAL accounts only"),
                "7D Tokens WoW%": st.column_config.NumberColumn(format="%+.1f%%", help="Week-over-week % change in tokens (last 7d vs prior 7d)"),
            }
        _r_df = pd.concat([_region_combined, _region_total], ignore_index=True)
        def _r_wow_bg(val):
            if pd.isna(val) or val == 0: return ''
            return 'background-color: #d4edda; color: #155724' if val > 0 else 'background-color: #fde8e8; color: #9b2335'
        _r_display = _r_df.style.map(_r_wow_bg, subset=['7D Tokens WoW%']) if _r_has_tokens else _r_df.style
        st.dataframe(
            _r_display,
            column_config=_r_col_cfg,
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("No region-level data available for the selected date range.")

st.divider()

# ── Shared helper: render any RSI/GSI section ────────────────────────────────
def _add_totals_row(display_df, partner_col='Partner', scope_col='Scope',
                    total_col='Total UCs', coco_col='CoCo UCs',
                    pct_col=None, eacv_col='Total EACV ($)', coco_eacv_col='CoCo EACV ($)',
                    status_col='Status'):
    """Append a TOTAL row to a partner detail DataFrame."""
    t_ucs  = int(display_df[total_col].sum())
    c_ucs  = int(display_df[coco_col].sum())
    t_eacv = display_df[eacv_col].sum()      if eacv_col      in display_df.columns else 0
    c_eacv = display_df[coco_eacv_col].sum() if coco_eacv_col in display_df.columns else 0
    pct    = round(c_ucs * 100.0 / t_ucs, 1) if t_ucs > 0 else 0.0
    row = {partner_col: 'TOTAL', scope_col: '—', total_col: t_ucs, coco_col: c_ucs}
    if pct_col:                                 row[pct_col]        = pct
    if eacv_col      in display_df.columns:    row[eacv_col]       = t_eacv
    if coco_eacv_col in display_df.columns:    row[coco_eacv_col]  = c_eacv
    if status_col    in display_df.columns:    row[status_col]     = f'{pct:.1f}%'
    return pd.concat([display_df, pd.DataFrame([row])], ignore_index=True)


def _build_token_usage(bc: pd.DataFrame, partner_map: dict) -> pd.DataFrame:
    """Compute per-partner token stats from bulk_conf — mirrors partner scorecard logic exactly.
    Filters to IS_COCO_FINAL, removes own-account rows, deduplicates by (PARTNER_NAME, ACCOUNT).
    """
    tok_cols = ['Q2_TOKENS', 'LAST7_TOKENS', 'PRIOR7_TOKENS']
    if bc is None or len(bc) == 0 or not all(c in bc.columns for c in tok_cols):
        return pd.DataFrame(columns=['PARTNER_LABEL', 'Tokens Consumed', 'Last 7d Tokens', '7D Tokens WoW%'])
    # Step 1: IS_COCO_FINAL only + restrict to this partner group (same as scorecard)
    _bc = bc[bc['IS_COCO_FINAL'] & bc['PARTNER_NAME'].isin(partner_map.keys())].copy()
    if len(_bc) == 0:
        return pd.DataFrame(columns=['PARTNER_LABEL', 'Tokens Consumed', 'Last 7d Tokens', '7D Tokens WoW%'])
    # Step 2: remove partner's own accounts (same as scorecard)
    _bc = filter_out_partner_own_accounts(_bc)
    # Step 3: map to display label
    _bc['_label'] = _bc['PARTNER_NAME'].map({k: v[0] for k, v in partner_map.items()})
    for c in tok_cols:
        _bc[c] = pd.to_numeric(_bc[c], errors='coerce').fillna(0)
    # Step 4: dedup by original PARTNER_NAME + ACCOUNT (same as scorecard) then group by label
    _dedup = _bc.drop_duplicates(subset=['PARTNER_NAME', 'ACCOUNT_NAME_UPPER'])
    _agg = _dedup.groupby('_label').agg(
        _q2=('Q2_TOKENS', 'sum'),
        _l7=('LAST7_TOKENS', 'sum'),
        _p7=('PRIOR7_TOKENS', 'sum'),
    ).reset_index().rename(columns={'_label': 'PARTNER_LABEL'})
    _agg['Tokens Consumed'] = _agg['_q2'].astype(int)
    _agg['Last 7d Tokens']  = _agg['_l7'].astype(int)
    _agg['7D Tokens WoW%'] = (
        (_agg['_l7'] - _agg['_p7']) * 100.0 / _agg['_p7'].replace(0, float('nan'))
    ).round(1)
    return _agg[['PARTNER_LABEL', 'Tokens Consumed', 'Last 7d Tokens', '7D Tokens WoW%']]


def _render_coco_funnel(total: int, coco: int, s3: int, s4: int, s5: int, s6: int, s7: int):
    """Render a vertical flow / funnel summary — all rows in one unified box."""
    coco_pct_of_total = round(coco * 100.0 / total, 1) if total > 0 else 0.0

    def _pct(n): return f"{round(n * 100.0 / coco, 1):.1f}" if coco > 0 else "0.0"

    # Each row: label left, bold-number + (pct) right — same format as CoCo Usecases header
    def _num_cell(n, pct_str, num_color="#1a1a1a", pct_color="#888"):
        return (f'<span style="font-size:18px;font-weight:700;color:{num_color}">{n}</span>'
                f'<span style="font-size:13px;font-weight:500;color:{pct_color}"> ({pct_str}%)</span>')

    stages = [
        ("Tech / Biz Validation",      "S3", s3),
        ("Use Case Won / Migr. Plan",  "S4", s4),
        ("Implementation In Progress", "S5", s5),
        ("Implementation Complete",    "S6", s6),
        ("Deployed",                   "S7", s7),
    ]

    def _stage_row(name, tag, n):
        return f"""
  <div style="display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-top:1px solid #f0f0f0">
    <span style="font-size:13px;color:#555">{name}</span>
    <span style="white-space:nowrap">{_num_cell(n, _pct(n))}</span>
  </div>"""

    stage_rows_html = "".join(_stage_row(name, tag, n) for name, tag, n in stages)

    html = f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                           border:1.5px solid #29b5e8;border-radius:10px;
                           padding:14px 18px;background:#fff;max-width:520px">
  <div style="display:flex;align-items:center;justify-content:space-between;padding-bottom:10px;border-bottom:1px solid #e8e8e8">
    <span style="font-size:13px;color:#666;font-weight:500">Total Usecases</span>
    <span style="font-size:22px;font-weight:700;color:#1a1a1a">{total}</span>
  </div>
  <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:2px solid #d4eef9">
    <span style="font-size:13px;color:#0d6e9e;font-weight:600">CoCo Usecases</span>
    <span style="white-space:nowrap">{_num_cell(coco, f"{coco_pct_of_total:.1f}", "#0d6e9e", "#4a9fc4")}</span>
  </div>
  {stage_rows_html}
</div>"""
    st.html(html)


def _render_partner_section(base_df, bc, bc_partner_map, skeleton_df, target_pct, section_label, detail_label):
    """Render 6 bordered KPI metrics + collapsible table for any partner group.
    bc_partner_map: dict {partner_name: (label, region_or_None)} or None for no geo filter.
    skeleton_df: DataFrame with PARTNER_LABEL, COUNTRY columns (all expected rows).
    """
    # Aggregate SQL base (include per-stage counts when present)
    _stage_sql_cols = ['S3_COCO','S4_COCO','S5_COCO','S6_COCO','S7_COCO']
    _has_stage_cols = len(base_df) > 0 and all(c in base_df.columns for c in _stage_sql_cols)
    if len(base_df) > 0:
        _agg_kwargs = dict(
            TOTAL_UCS=('TOTAL_UCS','sum'), COCO_UCS_SQL=('COCO_UCS','sum'),
            VALIDATION_SQL=('VALIDATION_COCO','sum'), IN_PROGRESS_SQL=('IN_PROGRESS_COCO','sum'),
            IMPL_COMPLETE_DEPLOYED_SQL=('IMPL_COMPLETE_DEPLOYED_COCO','sum'),
            DEPLOYED_ALL=('DEPLOYED_ALL','sum'), DEPLOYED_COCO_SQL=('DEPLOYED_COCO','sum'),
            TOTAL_EACV=('TOTAL_EACV','sum'), COCO_EACV_SQL=('COCO_EACV','sum'),
        )
        if _has_stage_cols:
            _agg_kwargs.update({f'{c}_SQL': (c,'sum') for c in _stage_sql_cols})
        sql_agg = base_df.groupby('PARTNER_LABEL').agg(**_agg_kwargs).reset_index()
    else:
        sql_agg = pd.DataFrame(columns=['PARTNER_LABEL','TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL',
                                        'IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL',
                                        'DEPLOYED_COCO_SQL','TOTAL_EACV','COCO_EACV_SQL'])

    df = skeleton_df.merge(sql_agg, on='PARTNER_LABEL', how='left').fillna(0)
    int_cols = ['TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL',
                'IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL']
    if _has_stage_cols:
        int_cols += [f'{c}_SQL' for c in _stage_sql_cols]
    df[int_cols] = df[int_cols].astype(int)

    # Enrich with IS_COCO_FINAL from bulk_conf
    _has_region = 'REGION_NAME' in bc.columns
    if len(bc) > 0 and 'IS_COCO_FINAL' in bc.columns and bc_partner_map:
        _bc = bc[bc['PARTNER_NAME'].isin(bc_partner_map.keys())].copy()
        _bc['_label']   = _bc['PARTNER_NAME'].map({k: v[0] for k, v in bc_partner_map.items()})
        _bc['_country'] = _bc['PARTNER_NAME'].map({k: v[1] for k, v in bc_partner_map.items()})
        # Apply geo filter only when REGION_NAME exists AND at least one partner has a country restriction
        _has_geo = _has_region and _bc['_country'].notna().any()
        if _has_geo:
            _bc = _bc[_bc.apply(
                lambda r: r['REGION_NAME'] == r['_country'] if pd.notna(r['_country']) else True,
                axis=1,
            )]
        _bc['_s3']  = _bc['IS_COCO_FINAL'] & (_bc['USE_CASE_STAGE'] == '3 - Technical / Business Validation')
        _bc['_s4']  = _bc['IS_COCO_FINAL'] & (_bc['USE_CASE_STAGE'] == '4 - Use Case Won / Migration Plan')
        _bc['_s5']  = _bc['IS_COCO_FINAL'] & (_bc['USE_CASE_STAGE'] == '5 - Implementation In Progress')
        _bc['_s6']  = _bc['IS_COCO_FINAL'] & (_bc['USE_CASE_STAGE'] == '6 - Implementation Complete')
        _bc['_s7']  = _bc['IS_COCO_FINAL'] & (_bc['USE_CASE_STAGE'] == '7 - Deployed')
        _bc['_tw']  = _bc['_s3'] | _bc['_s4']
        _bc['_ip']  = _bc['_s5']
        _bc['_icd'] = _bc['_s6'] | _bc['_s7']
        _bc['_dep'] = _bc['_s7']
        _bc['_coco_eacv'] = _bc['USE_CASE_EACV'].where(_bc['IS_COCO_FINAL'], 0)
        agg = (_bc.groupby('_label').agg(
            COCO_FINAL_UCS=('IS_COCO_FINAL','sum'),
            VALIDATION_COCO=('_tw','sum'), IN_PROGRESS_COCO=('_ip','sum'),
            IMPL_COMPLETE_DEPLOYED_COCO=('_icd','sum'), DEPLOYED_COCO=('_dep','sum'),
            S3_COCO=('_s3','sum'), S4_COCO=('_s4','sum'), S5_COCO=('_s5','sum'),
            S6_COCO=('_s6','sum'), S7_COCO=('_s7','sum'),
            COCO_EACV=('_coco_eacv','sum'),
        ).reset_index().rename(columns={'_label':'PARTNER_LABEL'}))
        df = df.merge(agg, on='PARTNER_LABEL', how='left')
        for c in ['COCO_FINAL_UCS','VALIDATION_COCO','IN_PROGRESS_COCO','IMPL_COMPLETE_DEPLOYED_COCO',
                  'DEPLOYED_COCO','S3_COCO','S4_COCO','S5_COCO','S6_COCO','S7_COCO']:
            df[c] = df[c].fillna(0).astype(int)
        df['COCO_EACV'] = df['COCO_EACV'].fillna(0)
    else:
        df['COCO_FINAL_UCS']              = df['COCO_UCS_SQL']
        df['VALIDATION_COCO']             = df['VALIDATION_SQL']
        df['IN_PROGRESS_COCO']            = df['IN_PROGRESS_SQL']
        df['IMPL_COMPLETE_DEPLOYED_COCO'] = df['IMPL_COMPLETE_DEPLOYED_SQL']
        df['DEPLOYED_COCO']               = df['DEPLOYED_COCO_SQL']
        df['COCO_EACV']                   = df['COCO_EACV_SQL']
        for c in _stage_sql_cols:
            df[c] = df.get(f'{c}_SQL', pd.Series(0, index=df.index))

    df['COCO_PCT'] = (df['COCO_FINAL_UCS'] * 100.0 / df['TOTAL_UCS'].replace(0, float('nan'))).round(1).fillna(0)

    # Vertical funnel summary
    total = int(df['TOTAL_UCS'].sum())
    coco  = int(df['COCO_FINAL_UCS'].sum())
    s3 = int(df['S3_COCO'].sum()) if 'S3_COCO' in df.columns else 0
    s4 = int(df['S4_COCO'].sum()) if 'S4_COCO' in df.columns else 0
    s5 = int(df['S5_COCO'].sum()) if 'S5_COCO' in df.columns else int(df['IN_PROGRESS_COCO'].sum())
    s6 = int(df['S6_COCO'].sum()) if 'S6_COCO' in df.columns else 0
    s7 = int(df['S7_COCO'].sum()) if 'S7_COCO' in df.columns else int(df['DEPLOYED_COCO'].sum())
    _render_coco_funnel(total, coco, s3, s4, s5, s6, s7)

    # Collapsible table — sorted desc by CoCo %, colored status, EACV + token columns
    with st.expander(f":material/table_chart: {detail_label}", expanded=False):
        _disp = df[['PARTNER_LABEL','COUNTRY','TOTAL_UCS','COCO_FINAL_UCS','COCO_PCT','TOTAL_EACV','COCO_EACV']].copy()
        _disp = _apply_snapshot_wow(_disp)
        # Merge token usage
        _tok = _build_token_usage(bc, bc_partner_map) if bc_partner_map else pd.DataFrame(columns=['PARTNER_LABEL'])
        if len(_tok) > 0:
            _disp = _disp.merge(_tok, on='PARTNER_LABEL', how='left')
        _disp = _disp.sort_values('COCO_PCT', ascending=False)
        _disp['Status'] = _disp['COCO_PCT'].apply(
            lambda p: '✅ On target' if p >= target_pct else (f'⚠️ {target_pct-p:.0f}% to go' if p > 0 else '— No UCs')
        )
        _pct_label = f'CoCo % vs {target_pct}% Target'
        _rename = {
            'PARTNER_LABEL': 'Partner', 'COUNTRY': 'Scope',
            'TOTAL_UCS': 'Total UCs', 'COCO_FINAL_UCS': 'CoCo UCs',
            'COCO_PCT': _pct_label,
            'WOW_COCO_UCS': 'WoW Δ UCs', 'WOW_COCO_PCT': 'WoW Δ%',
            'TOTAL_EACV': 'Total EACV ($)', 'COCO_EACV': 'CoCo EACV ($)',
        }
        _disp = _add_totals_row(_disp.rename(columns=_rename), pct_col=_pct_label)
        _col_cfg = {
            _pct_label:         st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
            'Total UCs':        st.column_config.NumberColumn(format="%d"),
            'CoCo UCs':         st.column_config.NumberColumn(format="%d"),
            'WoW Δ UCs':        st.column_config.NumberColumn(format="%+d"),
            'WoW Δ%':           st.column_config.NumberColumn(format="%+.1f%%"),
            'Total EACV ($)':   st.column_config.NumberColumn(format="$%.0f"),
            'CoCo EACV ($)':    st.column_config.NumberColumn(format="$%.0f"),
            'Tokens Consumed':  st.column_config.NumberColumn(format="%d"),
            'Last 7d Tokens':   st.column_config.NumberColumn(format="%d"),
            '7D Tokens WoW%':      st.column_config.NumberColumn(format="%+.1f%%"),
        }
        st.dataframe(_disp, column_config=_col_cfg, hide_index=True, use_container_width=True)

# ── GSI Adoption (75% Target) ─────────────────────────────────────────────────
_GSI_NAMES_MAP = {
    'Accenture': ('Accenture', None), 'Capgemini Technologies LLC': ('Capgemini Technologies LLC', None),
    'Cognizant Technology Solutions US Corp': ('Cognizant Technology Solutions US Corp', None),
    'Deloitte Consulting': ('Deloitte Consulting', None),
    'EY': ('EY', None), 'Ernst & Young (EY)': ('EY', None),
    'IBM': ('IBM', None), 'IBM Consulting': ('IBM', None),
}
_GSI_SKELETON = pd.DataFrame([
    {'PARTNER_LABEL': p, 'COUNTRY': 'Global'}
    for p in ['Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',
              'Deloitte Consulting','EY','IBM']
])
with st.expander(":material/groups: GSI CoCo Adoption (75% Target)", expanded=True):
    st.caption(f"{'Region: ' + region if _sidebar_theaters else 'Global scope'} — {'theater-filtered' if _sidebar_theaters else 'all theaters included'}")
    _gsi_base = get_gsi_adoption(conn, start_date, end_date, theaters=_sidebar_theaters)
    if _selected_partner_names and 'PARTNER_LABEL' in _gsi_base.columns:
        # GSI canonical labels: Accenture, Capgemini..., EY, IBM
        # PARTNER_ALIASES already uses canonical names for GSIs so direct match works
        _gsi_alias_map = {'Ernst & Young (EY)': 'EY', 'IBM Consulting': 'IBM'}
        _gsi_sel = {_gsi_alias_map.get(p, p) for p in _selected_partner_names}
        _gsi_sel_in_group = _gsi_sel & {v[0] for v in _GSI_NAMES_MAP.values()}
        if _gsi_sel_in_group:
            _gsi_base = _gsi_base[_gsi_base['PARTNER_LABEL'].isin(_gsi_sel_in_group)]
        else:
            _gsi_base = _gsi_base.iloc[0:0]
    _render_partner_section(_gsi_base, _managed_bc, _GSI_NAMES_MAP, _GSI_SKELETON,
                            target_pct=75, section_label="GSI", detail_label="Partner detail")

# ── NOAM RSI Adoption (75% Target) ───────────────────────────────────────────
from utils import PARTNER_ALIASES as _PA
_NOAM_RSI_NAMES = [p for p in _PA.get('--- NOAM RSIs ---', [])
                   if not p.startswith('---')]
_NOAM_RSI_MAP   = {p: (p, None) for p in _NOAM_RSI_NAMES}
# Merge LTM + kipi.ai aliases in map
for _alias, _canon in [('LTI Mindtree','LTM'),('Kipi.ai','kipi.ai')]:
    _NOAM_RSI_MAP[_alias] = (_canon, None)
_NOAM_RSI_SKELETON = pd.DataFrame([
    {'PARTNER_LABEL': p, 'COUNTRY': 'NoAM'}
    for p in sorted({v[0] for v in _NOAM_RSI_MAP.values()})
])
with st.expander(":material/location_on: NOAM RSI CoCo Adoption (75% Target)", expanded=True):
    st.caption("NoAM scope — AMSExpansion, USMajors, AMSAcquisition, USPubSec theaters")
    _noam_base = get_noam_rsi_adoption(conn, start_date, end_date, theaters=_sidebar_theaters)
    if _selected_partner_names:
        # NOAM PARTNER_LABEL = raw DT_OKR name; apply alias map for LTM/kipi
        _noam_alias = {'LTI Mindtree': 'LTM', 'Kipi.ai': 'kipi.ai'}
        _noam_raw_names = _NOAM_RSI_PARTNER_NAMES  # DT_OKR names in this group
        _noam_sel_labels = set()
        for p in _selected_partner_names:
            if p in _noam_alias:
                _noam_sel_labels.add(_noam_alias[p])
            elif p in _noam_raw_names:
                _noam_sel_labels.add(p)
        if _noam_sel_labels:
            _noam_base = _noam_base[_noam_base['PARTNER_LABEL'].isin(_noam_sel_labels)]
        else:
            _noam_base = _noam_base.iloc[0:0]
    _render_partner_section(_noam_base, _managed_bc, _NOAM_RSI_MAP, _NOAM_RSI_SKELETON,
                            target_pct=75, section_label="NOAM RSI", detail_label="Partner detail")

# ── APJ RSI Adoption (50% CoCo Target) ───────────────────────────────────────
with st.expander(":material/language: APJ RSI CoCo Adoption (50% Target)", expanded=True):
    st.caption("Each partner scoped to their assigned country — NTT Data→Japan | Megazone→Korea | Infinite Lambda→ASEAN | Altis→ANZ | Prolim→India")
    _apj_base = get_apj_rsi_adoption(conn, start_date, end_date)
    if _selected_partner_names and 'PARTNER_LABEL' in _apj_base.columns:
        # Translate raw DT_OKR names → canonical APJ labels (e.g. 'NTT DATA Group Corporation' → 'NTT Data')
        _apj_canonical_sel = {v[0] for k, v in APJ_RSI_REGION_MAP.items() if k in _selected_partner_names}
        if _apj_canonical_sel:
            _apj_base = _apj_base[_apj_base['PARTNER_LABEL'].isin(_apj_canonical_sel)]
        else:
            _apj_base = _apj_base.iloc[0:0]

    # Canonical 5-partner skeleton — all partners always appear even with 0 UCs
    _APJ_SKELETON = pd.DataFrame([
        {'PARTNER_LABEL': 'Altis',           'COUNTRY': 'ANZ'},
        {'PARTNER_LABEL': 'Infinite Lambda', 'COUNTRY': 'ASEAN'},
        {'PARTNER_LABEL': 'Megazone',        'COUNTRY': 'Korea'},
        {'PARTNER_LABEL': 'NTT Data',        'COUNTRY': 'Japan'},
        {'PARTNER_LABEL': 'Prolim',          'COUNTRY': 'India'},
    ])

    # Aggregate SQL results (may be missing partners with 0 UCs)
    if len(_apj_base) > 0:
        _apj_sql_agg = _apj_base.groupby('PARTNER_LABEL').agg(
            TOTAL_UCS=('TOTAL_UCS', 'sum'),
            COCO_UCS_SQL=('COCO_UCS', 'sum'),
            VALIDATION_SQL=('VALIDATION_COCO', 'sum'),
            IN_PROGRESS_SQL=('IN_PROGRESS_COCO', 'sum'),
            IMPL_COMPLETE_DEPLOYED_SQL=('IMPL_COMPLETE_DEPLOYED_COCO', 'sum'),
            DEPLOYED_ALL=('DEPLOYED_ALL', 'sum'),
            DEPLOYED_COCO_SQL=('DEPLOYED_COCO', 'sum'),
            TOTAL_EACV=('TOTAL_EACV', 'sum'),
            COCO_EACV_SQL=('COCO_EACV', 'sum'),
        ).reset_index()
    else:
        _apj_sql_agg = pd.DataFrame(columns=['PARTNER_LABEL','TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL','TOTAL_EACV','COCO_EACV_SQL'])

    # Merge skeleton with SQL results — missing partners get 0s
    _apj_df = _APJ_SKELETON.merge(_apj_sql_agg, on='PARTNER_LABEL', how='left').fillna(0)
    _apj_df[['TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL']] = \
        _apj_df[['TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL']].astype(int)
    if 'TOTAL_EACV' not in _apj_df.columns: _apj_df['TOTAL_EACV'] = 0.0
    if 'COCO_EACV_SQL' not in _apj_df.columns: _apj_df['COCO_EACV_SQL'] = 0.0

    # Enrich COCO_UCS with IS_COCO_FINAL from bulk_conf where available
    if len(_managed_bc) > 0 and "IS_COCO_FINAL" in _managed_bc.columns:
        _apj_rsi_names = list(APJ_RSI_REGION_MAP.keys())
        _apj_bc = _managed_bc[_managed_bc['PARTNER_NAME'].isin(_apj_rsi_names)].copy()
        _apj_bc['_label'] = _apj_bc['PARTNER_NAME'].map({k: v[0] for k, v in APJ_RSI_REGION_MAP.items()})
        _apj_bc['_country'] = _apj_bc['PARTNER_NAME'].map({k: v[1] for k, v in APJ_RSI_REGION_MAP.items()})
        _apj_bc = _apj_bc[_apj_bc['REGION_NAME'] == _apj_bc['_country']]
        _apj_bc['_s3']  = _apj_bc['IS_COCO_FINAL'] & (_apj_bc['USE_CASE_STAGE'] == '3 - Technical / Business Validation')
        _apj_bc['_s4']  = _apj_bc['IS_COCO_FINAL'] & (_apj_bc['USE_CASE_STAGE'] == '4 - Use Case Won / Migration Plan')
        _apj_bc['_s5']  = _apj_bc['IS_COCO_FINAL'] & (_apj_bc['USE_CASE_STAGE'] == '5 - Implementation In Progress')
        _apj_bc['_s6']  = _apj_bc['IS_COCO_FINAL'] & (_apj_bc['USE_CASE_STAGE'] == '6 - Implementation Complete')
        _apj_bc['_s7']  = _apj_bc['IS_COCO_FINAL'] & (_apj_bc['USE_CASE_STAGE'] == '7 - Deployed')
        _bc_agg = (
            _apj_bc.groupby('_label')
            .agg(COCO_FINAL_UCS=('IS_COCO_FINAL', 'sum'),
                 S3_COCO=('_s3','sum'), S4_COCO=('_s4','sum'), S5_COCO=('_s5','sum'),
                 S6_COCO=('_s6','sum'), S7_COCO=('_s7','sum'),
                 DEPLOYED_COCO=('_s7','sum'))
            .reset_index().rename(columns={'_label': 'PARTNER_LABEL'})
        )
        _apj_df = _apj_df.merge(_bc_agg, on='PARTNER_LABEL', how='left')
        for _c in ['COCO_FINAL_UCS','S3_COCO','S4_COCO','S5_COCO','S6_COCO','S7_COCO','DEPLOYED_COCO']:
            _apj_df[_c] = _apj_df[_c].fillna(0).astype(int)
        _apj_bc_eacv = _apj_bc.assign(_coco_eacv=_apj_bc['USE_CASE_EACV'].where(_apj_bc['IS_COCO_FINAL'], 0)).groupby('_label').agg(COCO_EACV=('_coco_eacv', 'sum')).reset_index().rename(columns={'_label':'PARTNER_LABEL'})
        _apj_df = _apj_df.merge(_apj_bc_eacv, on='PARTNER_LABEL', how='left')
        _apj_df['COCO_EACV'] = _apj_df['COCO_EACV'].fillna(0)
    else:
        _apj_df['COCO_FINAL_UCS'] = _apj_df['COCO_UCS_SQL']
        _apj_df['COCO_EACV']      = _apj_df['COCO_EACV_SQL']
        for _c in ['S3_COCO','S4_COCO','S5_COCO','S6_COCO','S7_COCO']:
            _apj_df[_c] = _apj_df.get(f'{_c}_SQL', pd.Series(0, index=_apj_df.index)).fillna(0).astype(int)
        _apj_df['DEPLOYED_COCO'] = _apj_df['S7_COCO']

    _apj_df['COCO_PCT'] = (
        _apj_df['COCO_FINAL_UCS'] * 100.0 /
        _apj_df['TOTAL_UCS'].replace(0, float('nan'))
    ).round(1).fillna(0)

    APJ_TARGET = 50
    _apj_df['Status'] = _apj_df['COCO_PCT'].apply(
        lambda p: '✅ On target' if p >= APJ_TARGET else (f'⚠️ {APJ_TARGET-p:.0f}% to go' if p > 0 else '— No UCs')
    )

    _render_coco_funnel(
        total=int(_apj_df['TOTAL_UCS'].sum()),
        coco=int(_apj_df['COCO_FINAL_UCS'].sum()),
        s3=int(_apj_df['S3_COCO'].sum()) if 'S3_COCO' in _apj_df.columns else 0,
        s4=int(_apj_df['S4_COCO'].sum()) if 'S4_COCO' in _apj_df.columns else 0,
        s5=int(_apj_df['S5_COCO'].sum()) if 'S5_COCO' in _apj_df.columns else 0,
        s6=int(_apj_df['S6_COCO'].sum()) if 'S6_COCO' in _apj_df.columns else 0,
        s7=int(_apj_df['S7_COCO'].sum()) if 'S7_COCO' in _apj_df.columns else 0,
    )

    with st.expander(":material/table_chart: Partner detail", expanded=False):
        _apj_display = _apj_df[['PARTNER_LABEL','COUNTRY','TOTAL_UCS','COCO_FINAL_UCS','COCO_PCT','TOTAL_EACV','COCO_EACV','Status']].copy()
        _apj_display = _apply_snapshot_wow(_apj_display)
        _apj_tok = _build_token_usage(_bc_managed, APJ_RSI_REGION_MAP)
        if len(_apj_tok) > 0:
            _apj_display = _apj_display.merge(_apj_tok, on='PARTNER_LABEL', how='left')
        _apj_display = _apj_display.sort_values('COCO_PCT', ascending=False)
        _apj_display['Status'] = _apj_display['COCO_PCT'].apply(
            lambda p: '✅ On target' if p >= APJ_TARGET else (f'⚠️ {APJ_TARGET-p:.0f}% to go' if p > 0 else '— No UCs')
        )
        _apj_display = _add_totals_row(
            _apj_display.rename(columns={
                'PARTNER_LABEL': 'Partner', 'COUNTRY': 'Country',
                'TOTAL_UCS': 'Total UCs', 'COCO_FINAL_UCS': 'CoCo UCs',
                'COCO_PCT': 'CoCo % vs 50% Target',
                'WOW_COCO_UCS': 'WoW Δ UCs', 'WOW_COCO_PCT': 'WoW Δ%',
                'TOTAL_EACV': 'Total EACV ($)', 'COCO_EACV': 'CoCo EACV ($)',
            }),
            scope_col='Country', pct_col='CoCo % vs 50% Target',
        )
        st.dataframe(
            _apj_display,
            column_config={
                'CoCo % vs 50% Target': st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                'Total UCs':       st.column_config.NumberColumn(format="%d"),
                'CoCo UCs':        st.column_config.NumberColumn(format="%d"),
                'WoW Δ UCs':       st.column_config.NumberColumn(format="%+d"),
                'WoW Δ%':          st.column_config.NumberColumn(format="%+.1f%%"),
                'Total EACV ($)':  st.column_config.NumberColumn(format="$%.0f"),
                'CoCo EACV ($)':   st.column_config.NumberColumn(format="$%.0f"),
                'Tokens Consumed': st.column_config.NumberColumn(format="%d"),
                'Last 7d Tokens':  st.column_config.NumberColumn(format="%d"),
                '7D Tokens WoW%':     st.column_config.NumberColumn(format="%+.1f%%"),
            },
            hide_index=True, use_container_width=True,
        )

# ─── LATAM RSI Section ───────────────────────────────────────────────────────
with st.expander("🌎 LATAM RSI CoCo Adoption (50% Target)", expanded=True):
    _latam_base = get_latam_rsi_adoption(conn, start_date, end_date)
    if _selected_partner_names and 'PARTNER_LABEL' in _latam_base.columns:
        _latam_canonical_sel = {v[0] for k, v in LATAM_RSI_REGION_MAP.items() if k in _selected_partner_names}
        if _latam_canonical_sel:
            _latam_base = _latam_base[_latam_base['PARTNER_LABEL'].isin(_latam_canonical_sel)]
        else:
            _latam_base = _latam_base.iloc[0:0]

    _LATAM_SKELETON = pd.DataFrame([
        {'PARTNER_LABEL': 'EgosBi',   'COUNTRY': 'LATAM (Mexico)'},
        {'PARTNER_LABEL': 'IVCISA',   'COUNTRY': 'LATAM (CALA)'},
        {'PARTNER_LABEL': 'Keyrus',   'COUNTRY': 'LATAM (Brazil)'},
        {'PARTNER_LABEL': 'Seidor',   'COUNTRY': 'LATAM (CALA)'},
        {'PARTNER_LABEL': 'Viewnear', 'COUNTRY': 'LATAM (Mexico)'},
    ])

    if len(_latam_base) > 0:
        _latam_sql_agg = _latam_base.groupby('PARTNER_LABEL').agg(
            TOTAL_UCS=('TOTAL_UCS', 'sum'),
            COCO_UCS_SQL=('COCO_UCS', 'sum'),
            VALIDATION_SQL=('VALIDATION_COCO', 'sum'),
            IN_PROGRESS_SQL=('IN_PROGRESS_COCO', 'sum'),
            IMPL_COMPLETE_DEPLOYED_SQL=('IMPL_COMPLETE_DEPLOYED_COCO', 'sum'),
            DEPLOYED_ALL=('DEPLOYED_ALL', 'sum'),
            DEPLOYED_COCO_SQL=('DEPLOYED_COCO', 'sum'),
            TOTAL_EACV=('TOTAL_EACV', 'sum'),
            COCO_EACV_SQL=('COCO_EACV', 'sum'),
        ).reset_index()
    else:
        _latam_sql_agg = pd.DataFrame(columns=['PARTNER_LABEL','TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL','TOTAL_EACV','COCO_EACV_SQL'])

    _latam_df = _LATAM_SKELETON.merge(_latam_sql_agg, on='PARTNER_LABEL', how='left').fillna(0)
    _latam_df[['TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL']] = \
        _latam_df[['TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL']].astype(int)
    if 'TOTAL_EACV' not in _latam_df.columns: _latam_df['TOTAL_EACV'] = 0.0
    if 'COCO_EACV_SQL' not in _latam_df.columns: _latam_df['COCO_EACV_SQL'] = 0.0

    if len(_managed_bc) > 0 and "IS_COCO_FINAL" in _managed_bc.columns:
        _latam_rsi_names = list(LATAM_RSI_REGION_MAP.keys())
        _latam_bc = _managed_bc[_managed_bc['PARTNER_NAME'].isin(_latam_rsi_names)].copy()
        _latam_bc['_label'] = _latam_bc['PARTNER_NAME'].map({k: v[0] for k, v in LATAM_RSI_REGION_MAP.items()})
        if 'REGION_NAME' in _latam_bc.columns:
            _latam_bc = _latam_bc[_latam_bc['REGION_NAME'] == 'LATAM']
        _latam_bc['_s3']  = _latam_bc['IS_COCO_FINAL'] & (_latam_bc['USE_CASE_STAGE'] == '3 - Technical / Business Validation')
        _latam_bc['_s4']  = _latam_bc['IS_COCO_FINAL'] & (_latam_bc['USE_CASE_STAGE'] == '4 - Use Case Won / Migration Plan')
        _latam_bc['_s5']  = _latam_bc['IS_COCO_FINAL'] & (_latam_bc['USE_CASE_STAGE'] == '5 - Implementation In Progress')
        _latam_bc['_s6']  = _latam_bc['IS_COCO_FINAL'] & (_latam_bc['USE_CASE_STAGE'] == '6 - Implementation Complete')
        _latam_bc['_s7']  = _latam_bc['IS_COCO_FINAL'] & (_latam_bc['USE_CASE_STAGE'] == '7 - Deployed')
        _lbc_agg = (
            _latam_bc.groupby('_label')
            .agg(COCO_FINAL_UCS=('IS_COCO_FINAL', 'sum'),
                 S3_COCO=('_s3','sum'), S4_COCO=('_s4','sum'), S5_COCO=('_s5','sum'),
                 S6_COCO=('_s6','sum'), S7_COCO=('_s7','sum'),
                 DEPLOYED_COCO=('_s7','sum'))
            .reset_index().rename(columns={'_label': 'PARTNER_LABEL'})
        )
        _latam_df = _latam_df.merge(_lbc_agg, on='PARTNER_LABEL', how='left')
        for _c in ['COCO_FINAL_UCS','S3_COCO','S4_COCO','S5_COCO','S6_COCO','S7_COCO','DEPLOYED_COCO']:
            _latam_df[_c] = _latam_df[_c].fillna(0).astype(int)
        _latam_bc_eacv = _latam_bc.assign(_coco_eacv=_latam_bc['USE_CASE_EACV'].where(_latam_bc['IS_COCO_FINAL'], 0)).groupby('_label').agg(COCO_EACV=('_coco_eacv', 'sum')).reset_index().rename(columns={'_label':'PARTNER_LABEL'})
        _latam_df = _latam_df.merge(_latam_bc_eacv, on='PARTNER_LABEL', how='left')
        _latam_df['COCO_EACV'] = _latam_df['COCO_EACV'].fillna(0)
    else:
        _latam_df['COCO_FINAL_UCS'] = _latam_df['COCO_UCS_SQL']
        _latam_df['COCO_EACV']      = _latam_df['COCO_EACV_SQL']
        for _c in ['S3_COCO','S4_COCO','S5_COCO','S6_COCO','S7_COCO']:
            _latam_df[_c] = _latam_df.get(f'{_c}_SQL', pd.Series(0, index=_latam_df.index)).fillna(0).astype(int)
        _latam_df['DEPLOYED_COCO'] = _latam_df['S7_COCO']

    _latam_df['COCO_PCT'] = (
        _latam_df['COCO_FINAL_UCS'] * 100.0 /
        _latam_df['TOTAL_UCS'].replace(0, float('nan'))
    ).round(1).fillna(0)

    LATAM_TARGET = 50
    _latam_df['Status'] = _latam_df['COCO_PCT'].apply(
        lambda p: '✅ On target' if p >= LATAM_TARGET else (f'⚠️ {LATAM_TARGET-p:.0f}% to go' if p > 0 else '— No UCs')
    )

    _render_coco_funnel(
        total=int(_latam_df['TOTAL_UCS'].sum()),
        coco=int(_latam_df['COCO_FINAL_UCS'].sum()),
        s3=int(_latam_df['S3_COCO'].sum()) if 'S3_COCO' in _latam_df.columns else 0,
        s4=int(_latam_df['S4_COCO'].sum()) if 'S4_COCO' in _latam_df.columns else 0,
        s5=int(_latam_df['S5_COCO'].sum()) if 'S5_COCO' in _latam_df.columns else 0,
        s6=int(_latam_df['S6_COCO'].sum()) if 'S6_COCO' in _latam_df.columns else 0,
        s7=int(_latam_df['S7_COCO'].sum()) if 'S7_COCO' in _latam_df.columns else 0,
    )

    with st.expander(":material/table_chart: Partner detail", expanded=False):
        _latam_display = _latam_df[['PARTNER_LABEL','COUNTRY','TOTAL_UCS','COCO_FINAL_UCS','COCO_PCT','TOTAL_EACV','COCO_EACV','Status']].copy()
        _latam_display = _apply_snapshot_wow(_latam_display)
        _latam_tok = _build_token_usage(_bc_managed, LATAM_RSI_REGION_MAP)
        if len(_latam_tok) > 0:
            _latam_display = _latam_display.merge(_latam_tok, on='PARTNER_LABEL', how='left')
        _latam_display = _latam_display.sort_values('COCO_PCT', ascending=False)
        _latam_display = _add_totals_row(
            _latam_display.rename(columns={
                'PARTNER_LABEL': 'Partner', 'COUNTRY': 'Country',
                'TOTAL_UCS': 'Total UCs', 'COCO_FINAL_UCS': 'CoCo UCs',
                'COCO_PCT': 'CoCo % vs 50% Target',
                'WOW_COCO_UCS': 'WoW Δ UCs', 'WOW_COCO_PCT': 'WoW Δ%',
                'TOTAL_EACV': 'Total EACV ($)', 'COCO_EACV': 'CoCo EACV ($)',
            }),
            scope_col='Country', pct_col='CoCo % vs 50% Target',
        )
        st.dataframe(
            _latam_display,
            column_config={
                'CoCo % vs 50% Target': st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                'Total UCs':       st.column_config.NumberColumn(format="%d"),
                'CoCo UCs':        st.column_config.NumberColumn(format="%d"),
                'WoW Δ UCs':       st.column_config.NumberColumn(format="%+d"),
                'WoW Δ%':          st.column_config.NumberColumn(format="%+.1f%%"),
                'Total EACV ($)':  st.column_config.NumberColumn(format="$%.0f"),
                'CoCo EACV ($)':   st.column_config.NumberColumn(format="$%.0f"),
                'Tokens Consumed': st.column_config.NumberColumn(format="%d"),
                'Last 7d Tokens':  st.column_config.NumberColumn(format="%d"),
                '7D Tokens WoW%':  st.column_config.NumberColumn(format="%+.1f%%"),
            },
            hide_index=True, use_container_width=True,
        )

st.divider()

# ── EMEA RSI Adoption (50% CoCo Target) ──────────────────────────────────────
with st.expander(":material/globe_uk: EMEA RSI CoCo Adoption (50% Target)", expanded=True):
    st.caption("Each partner scoped to their assigned region — Infomotion→CentralEMEA | Civica→SouthEMEA (Spain) | Kubrick→UK | KPC→SouthEMEA (France)")
    _emea_base = get_emea_rsi_adoption(conn, start_date, end_date)
    if _selected_partner_names and 'PARTNER_LABEL' in _emea_base.columns:
        # Translate raw DT_OKR names → canonical EMEA labels (e.g. 'INFOMOTION GMBH' → 'Infomotion')
        _emea_canonical_sel = {v[0] for k, v in EMEA_RSI_REGION_MAP.items() if k in _selected_partner_names}
        if _emea_canonical_sel:
            _emea_base = _emea_base[_emea_base['PARTNER_LABEL'].isin(_emea_canonical_sel)]
        else:
            _emea_base = _emea_base.iloc[0:0]

    # Canonical 4-partner skeleton — all partners always appear even with 0 UCs
    _EMEA_SKELETON = pd.DataFrame([
        {'PARTNER_LABEL': 'Civica',     'COUNTRY': 'SouthEMEA (Spain)'},
        {'PARTNER_LABEL': 'Infomotion', 'COUNTRY': 'CentralEMEA'},
        {'PARTNER_LABEL': 'KPC',        'COUNTRY': 'SouthEMEA (France)'},
        {'PARTNER_LABEL': 'Kubrick',    'COUNTRY': 'UK'},
    ])

    if len(_emea_base) > 0:
        _emea_sql_agg = _emea_base.groupby('PARTNER_LABEL').agg(
            TOTAL_UCS=('TOTAL_UCS', 'sum'),
            COCO_UCS_SQL=('COCO_UCS', 'sum'),
            VALIDATION_SQL=('VALIDATION_COCO', 'sum'),
            IN_PROGRESS_SQL=('IN_PROGRESS_COCO', 'sum'),
            IMPL_COMPLETE_DEPLOYED_SQL=('IMPL_COMPLETE_DEPLOYED_COCO', 'sum'),
            DEPLOYED_ALL=('DEPLOYED_ALL', 'sum'),
            DEPLOYED_COCO_SQL=('DEPLOYED_COCO', 'sum'),
            TOTAL_EACV=('TOTAL_EACV', 'sum'),
            COCO_EACV_SQL=('COCO_EACV', 'sum'),
        ).reset_index()
    else:
        _emea_sql_agg = pd.DataFrame(columns=['PARTNER_LABEL','TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL','TOTAL_EACV','COCO_EACV_SQL'])

    _emea_df = _EMEA_SKELETON.merge(_emea_sql_agg, on='PARTNER_LABEL', how='left').fillna(0)
    _emea_df[['TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL']] = \
        _emea_df[['TOTAL_UCS','COCO_UCS_SQL','VALIDATION_SQL','IN_PROGRESS_SQL','IMPL_COMPLETE_DEPLOYED_SQL','DEPLOYED_ALL','DEPLOYED_COCO_SQL']].astype(int)
    if 'TOTAL_EACV' not in _emea_df.columns: _emea_df['TOTAL_EACV'] = 0.0
    if 'COCO_EACV_SQL' not in _emea_df.columns: _emea_df['COCO_EACV_SQL'] = 0.0

    # Enrich COCO_UCS with IS_COCO_FINAL from bulk_conf where available
    if len(_managed_bc) > 0 and "IS_COCO_FINAL" in _managed_bc.columns:
        _emea_rsi_names = list(EMEA_RSI_REGION_MAP.keys())
        _emea_bc = _managed_bc[_managed_bc['PARTNER_NAME'].isin(_emea_rsi_names)].copy()
        _emea_bc['_label']   = _emea_bc['PARTNER_NAME'].map({k: v[0] for k, v in EMEA_RSI_REGION_MAP.items()})
        _emea_bc['_country'] = _emea_bc['PARTNER_NAME'].map({k: v[1] for k, v in EMEA_RSI_REGION_MAP.items()})
        _emea_bc = _emea_bc[_emea_bc['REGION_NAME'] == _emea_bc['_country']]
        _emea_bc['_s3']  = _emea_bc['IS_COCO_FINAL'] & (_emea_bc['USE_CASE_STAGE'] == '3 - Technical / Business Validation')
        _emea_bc['_s4']  = _emea_bc['IS_COCO_FINAL'] & (_emea_bc['USE_CASE_STAGE'] == '4 - Use Case Won / Migration Plan')
        _emea_bc['_s5']  = _emea_bc['IS_COCO_FINAL'] & (_emea_bc['USE_CASE_STAGE'] == '5 - Implementation In Progress')
        _emea_bc['_s6']  = _emea_bc['IS_COCO_FINAL'] & (_emea_bc['USE_CASE_STAGE'] == '6 - Implementation Complete')
        _emea_bc['_s7']  = _emea_bc['IS_COCO_FINAL'] & (_emea_bc['USE_CASE_STAGE'] == '7 - Deployed')
        _ebc_agg = (
            _emea_bc.groupby('_label')
            .agg(COCO_FINAL_UCS=('IS_COCO_FINAL', 'sum'),
                 S3_COCO=('_s3','sum'), S4_COCO=('_s4','sum'), S5_COCO=('_s5','sum'),
                 S6_COCO=('_s6','sum'), S7_COCO=('_s7','sum'),
                 DEPLOYED_COCO=('_s7','sum'))
            .reset_index().rename(columns={'_label': 'PARTNER_LABEL'})
        )
        _emea_df = _emea_df.merge(_ebc_agg, on='PARTNER_LABEL', how='left')
        for _c in ['COCO_FINAL_UCS','S3_COCO','S4_COCO','S5_COCO','S6_COCO','S7_COCO','DEPLOYED_COCO']:
            _emea_df[_c] = _emea_df[_c].fillna(0).astype(int)
        _emea_bc_eacv = _emea_bc.assign(_coco_eacv=_emea_bc['USE_CASE_EACV'].where(_emea_bc['IS_COCO_FINAL'], 0)).groupby('_label').agg(COCO_EACV=('_coco_eacv', 'sum')).reset_index().rename(columns={'_label':'PARTNER_LABEL'})
        _emea_df = _emea_df.merge(_emea_bc_eacv, on='PARTNER_LABEL', how='left')
        _emea_df['COCO_EACV'] = _emea_df['COCO_EACV'].fillna(0)
    else:
        _emea_df['COCO_FINAL_UCS'] = _emea_df['COCO_UCS_SQL']
        _emea_df['COCO_EACV']      = _emea_df['COCO_EACV_SQL']
        for _c in ['S3_COCO','S4_COCO','S5_COCO','S6_COCO','S7_COCO']:
            _emea_df[_c] = _emea_df.get(f'{_c}_SQL', pd.Series(0, index=_emea_df.index)).fillna(0).astype(int)
        _emea_df['DEPLOYED_COCO'] = _emea_df['S7_COCO']

    _emea_df['COCO_PCT'] = (
        _emea_df['COCO_FINAL_UCS'] * 100.0 /
        _emea_df['TOTAL_UCS'].replace(0, float('nan'))
    ).round(1).fillna(0)

    EMEA_TARGET = 50
    _emea_df['Status'] = _emea_df['COCO_PCT'].apply(
        lambda p: '✅ On target' if p >= EMEA_TARGET else (f'⚠️ {EMEA_TARGET-p:.0f}% to go' if p > 0 else '— No UCs')
    )

    _render_coco_funnel(
        total=int(_emea_df['TOTAL_UCS'].sum()),
        coco=int(_emea_df['COCO_FINAL_UCS'].sum()),
        s3=int(_emea_df['S3_COCO'].sum()) if 'S3_COCO' in _emea_df.columns else 0,
        s4=int(_emea_df['S4_COCO'].sum()) if 'S4_COCO' in _emea_df.columns else 0,
        s5=int(_emea_df['S5_COCO'].sum()) if 'S5_COCO' in _emea_df.columns else 0,
        s6=int(_emea_df['S6_COCO'].sum()) if 'S6_COCO' in _emea_df.columns else 0,
        s7=int(_emea_df['S7_COCO'].sum()) if 'S7_COCO' in _emea_df.columns else 0,
    )

    with st.expander(":material/table_chart: Partner detail", expanded=False):
        _emea_display = _emea_df[['PARTNER_LABEL','COUNTRY','TOTAL_UCS','COCO_FINAL_UCS','COCO_PCT','TOTAL_EACV','COCO_EACV','Status']].copy()
        _emea_display = _apply_snapshot_wow(_emea_display)
        _emea_tok = _build_token_usage(_bc_managed, EMEA_RSI_REGION_MAP)
        if len(_emea_tok) > 0:
            _emea_display = _emea_display.merge(_emea_tok, on='PARTNER_LABEL', how='left')
        _emea_display = _emea_display.sort_values('COCO_PCT', ascending=False)
        _emea_display = _add_totals_row(
            _emea_display.rename(columns={
                'PARTNER_LABEL': 'Partner', 'COUNTRY': 'Country',
                'TOTAL_UCS': 'Total UCs', 'COCO_FINAL_UCS': 'CoCo UCs',
                'COCO_PCT': 'CoCo % vs 50% Target',
                'WOW_COCO_UCS': 'WoW Δ UCs', 'WOW_COCO_PCT': 'WoW Δ%',
                'TOTAL_EACV': 'Total EACV ($)', 'COCO_EACV': 'CoCo EACV ($)',
            }),
            scope_col='Country', pct_col='CoCo % vs 50% Target',
        )
        st.dataframe(
            _emea_display,
            column_config={
                'CoCo % vs 50% Target': st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
                'Total UCs':       st.column_config.NumberColumn(format="%d"),
                'CoCo UCs':        st.column_config.NumberColumn(format="%d"),
                'WoW Δ UCs':       st.column_config.NumberColumn(format="%+d"),
                'WoW Δ%':          st.column_config.NumberColumn(format="%+.1f%%"),
                'Total EACV ($)':  st.column_config.NumberColumn(format="$%.0f"),
                'CoCo EACV ($)':   st.column_config.NumberColumn(format="$%.0f"),
                'Tokens Consumed': st.column_config.NumberColumn(format="%d"),
                'Last 7d Tokens':  st.column_config.NumberColumn(format="%d"),
                '7D Tokens WoW%':     st.column_config.NumberColumn(format="%+.1f%%"),
            },
            hide_index=True, use_container_width=True,
        )

st.divider()

# Inject context for Ask AI
st.session_state.ask_ai_context = (
    f"Current page: Adoption Metrics (Overview). Region: {region}. Partner filter: {selected_partners or 'All'}.\n"
    f"CoCo adoption: {coco_pct:.1f}% ({coco_count}/{int(s['TOTAL_USE_CASES'])} UCs). OKR target: 75%."
    + build_filter_context()
)

st.subheader("CoCo % by Stage Breakdown")
# Build stage agg from _bc_managed (IS_COCO_FINAL, geo-restricted) when available, else fall back to SQL stats
if len(_bc_managed) > 0 and 'IS_COCO_FINAL' in _bc_managed.columns:
    _bc = _bc_managed.copy()
    _bc['_is_coco_final'] = _bc['IS_COCO_FINAL'].astype(bool)
    _stage_agg = (
        _bc.groupby('USE_CASE_STAGE', dropna=True)
        .agg(TOTAL_UCS=('USE_CASE_ID', 'count'),
             COCO_UCS=('_is_coco_final', 'sum'),
             TOTAL_EACV=('USE_CASE_EACV', 'sum'))
        .reset_index()
    )
    _stage_agg['COCO_EACV'] = (
        _bc[_bc['_is_coco_final']].groupby('USE_CASE_STAGE')['USE_CASE_EACV'].sum()
        .reindex(_stage_agg['USE_CASE_STAGE']).fillna(0).values
    )
else:
    # Fallback: build from summary stats (no EACV split available)
    _stage_agg = pd.DataFrame([
        {'USE_CASE_STAGE': '3 - Technical / Business Validation',
         'TOTAL_UCS': int(s['VALIDATION_COUNT']), 'COCO_UCS': int(s.get('VALIDATION_COCO_COUNT', 0)),
         'TOTAL_EACV': float(s['VALIDATION_EACV'] or 0), 'COCO_EACV': 0},
        {'USE_CASE_STAGE': '4 - Use Case Won / Migration Plan',
         'TOTAL_UCS': int(s['WON_COUNT']), 'COCO_UCS': _tech_wins_coco,
         'TOTAL_EACV': float(s['WON_EACV'] or 0), 'COCO_EACV': 0},
        {'USE_CASE_STAGE': '5-6 - Implementation',
         'TOTAL_UCS': int(s['IMPL_COUNT']), 'COCO_UCS': _in_impl_coco,
         'TOTAL_EACV': float(s['IMPL_EACV'] or 0), 'COCO_EACV': 0},
        {'USE_CASE_STAGE': '7 - Deployed',
         'TOTAL_UCS': int(s['DEPLOYED_COUNT']), 'COCO_UCS': _go_live_coco,
         'TOTAL_EACV': float(s['DEPLOYED_EACV'] or 0), 'COCO_EACV': _coco_eacv},
    ])

if len(_stage_agg) > 0:
    _stage_agg['COCO_PCT'] = (
        _stage_agg['COCO_UCS'] * 100.0 /
        _stage_agg['TOTAL_UCS'].replace(0, float('nan'))
    ).round(1).fillna(0)
    _stage_agg['NON_COCO'] = _stage_agg['TOTAL_UCS'] - _stage_agg['COCO_UCS']
    _stage_agg['STAGE_SHORT'] = _stage_agg['USE_CASE_STAGE'].str.replace(r'^\d+ - ', '', regex=True)
    _stage_agg = _stage_agg.sort_values('USE_CASE_STAGE')

    import plotly.graph_objects as go
    _sfig = go.Figure()
    _sfig.add_trace(go.Bar(
        name='CoCo (IS_COCO_FINAL)', x=_stage_agg['STAGE_SHORT'], y=_stage_agg['COCO_UCS'],
        marker_color='#29B5E8', text=_stage_agg['COCO_UCS'], textposition='inside'))
    _sfig.add_trace(go.Bar(
        name='Non-CoCo', x=_stage_agg['STAGE_SHORT'], y=_stage_agg['NON_COCO'],
        marker_color='#e0e0e0', text=_stage_agg['NON_COCO'], textposition='inside'))
    _sfig.update_layout(barmode='stack', height=360, xaxis_title='', yaxis_title='Use Cases',
        legend=dict(orientation='h', y=1.12))
    for _, _row in _stage_agg.iterrows():
        _sfig.add_annotation(x=_row['STAGE_SHORT'], y=_row['TOTAL_UCS'],
            text=f"{_row['COCO_PCT']:.0f}%", showarrow=False, yshift=14,
            font=dict(size=13, color='#29B5E8', weight='bold'))
    st.plotly_chart(_sfig, use_container_width=True)

    st.dataframe(
        _stage_agg[['USE_CASE_STAGE', 'TOTAL_UCS', 'COCO_UCS', 'COCO_PCT', 'TOTAL_EACV', 'COCO_EACV']].rename(columns={
            'USE_CASE_STAGE': 'Stage', 'TOTAL_UCS': 'Total UCs', 'COCO_UCS': 'CoCo UCs (IS_COCO_FINAL)',
            'COCO_PCT': 'CoCo %', 'TOTAL_EACV': 'Total EACV', 'COCO_EACV': 'CoCo EACV',
        }),
        column_config={
            'CoCo %': st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
            'Total EACV': st.column_config.NumberColumn(format="$%.0f"),
            'CoCo EACV': st.column_config.NumberColumn(format="$%.0f"),
        },
        hide_index=True, use_container_width=True,
    )

st.divider()

