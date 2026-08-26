"""
AIM Adoption — Partner AIM Engagement & FDE Project Tracker
Pulls from snowscience.snowconvert tables (daily snapshots via Fivetran).
"""
import streamlit as st
import pandas as pd

# ── connection ────────────────────────────────────────────────────────────────
try:
    from utils import get_connection
    conn = get_connection()
except Exception:
    conn = st.connection("snowflake")

SCHEMA = "SNOWSCIENCE.SNOWCONVERT"

# ── theme / CSS (matches CoCo Adoption Metrics) ───────────────────────────────
st.markdown("""
<style>
/* KPI metric tiles — Snowflake blue gradient */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #a8dff5 0%, #6ec5ed 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 4px rgba(41,181,232,.2) !important;
    padding: 10px 14px !important;
}
[data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] span {
    color: rgba(0,40,70,0.8) !important;
    font-weight: 700 !important;
    font-size: 10px !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
[data-testid="stMetricValue"] {
    color: #003a5c !important;
    font-weight: 800 !important;
    font-size: 22px !important;
}
/* Section divider label */
.aim-section-label {
    color: #0b6c96;
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 4px;
}
/* Info card border (matches coco-sentiment-box) */
.aim-info-box {
    border: 2px solid #29B5E8;
    border-radius: 8px;
    padding: 10px 16px;
    background: rgba(41,181,232,0.06);
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

SCHEMA = "SNOWSCIENCE.SNOWCONVERT"
LATEST = "(SELECT MAX(DS) FROM {table})"


def _latest(table):
    return f"SELECT MAX(DS) FROM {SCHEMA}.{table}"


@st.cache_data(ttl=3600)
def load_aim(_conn):
    return _conn.query(f"""
        SELECT
            ACCOUNT,
            PARTNER_                    AS PARTNER,
            USE_CASE_S_NAME_SFDC_LINKS  AS USE_CASE_LINK,
            STATUS,
            ENGAGEMENT,
            SALES_THEATER               AS THEATER,
            REGION,
            SOLUTION_ENGINEER           AS SE,
            MSE_ASSIGNED,
            PDM_LEAD,
            PSM_LEAD,
            PSE,
            _1_QUALIFY                  AS "QUALIFY",
            _2_ASSESS                   AS "ASSESS",
            _3_VALIDATE                 AS "VALIDATE",
            _4_AIM_DEPLOYED             AS "AIM_DEPLOYED",
            NOMINATED_BY_PARTNER_FIELD_ AS NOMINATED_BY,
            NOTES
        FROM {SCHEMA}.SF_PARTNER_AIM_ENGAGEMENT_TRACKER
        WHERE DS = ({_latest('SF_PARTNER_AIM_ENGAGEMENT_TRACKER')})
        ORDER BY SALES_THEATER, REGION, ACCOUNT
    """)


@st.cache_data(ttl=3600)
def load_active(_conn):
    return _conn.query(f"""
        SELECT
            PROJECT_NAME, STATUS, TYPE, FOCUS_AREA,
            SOURCE_SYSTEM, ENGINEER_S_ AS ENGINEERS,
            ARCHITECT, ACV_EACV AS EACV,
            SOW_SIGNED_DATE, PLANNED_ASSESSMENT_START,
            MIGRATION_END_DATE_PLANNED_,
            PLUGIN_USAGE, NOTES
        FROM {SCHEMA}.ACTIVE_FDE_PROJECTS_RESOURCING
        WHERE DS = ({_latest('ACTIVE_FDE_PROJECTS_RESOURCING')})
        ORDER BY PROJECT_NAME
    """)


@st.cache_data(ttl=3600)
def load_onboarding(_conn):
    return _conn.query(f"""
        SELECT
            PROJECT_NAME, STATUS, TYPE, FOCUS_AREA,
            SOURCE_SYSTEM, ENGINEER_S_ AS ENGINEERS,
            ARCHITECT, ACV_EACV AS EACV,
            SOW_SIGNED_DATE, PLANNED_ASSESSMENT_START,
            PROJECT_SIZING, NOTES
        FROM {SCHEMA}.ONBOARDING_FDE_PROJECTS_SIGNED_RESOURCING
        WHERE DS = ({_latest('ONBOARDING_FDE_PROJECTS_SIGNED_RESOURCING')})
        ORDER BY PROJECT_NAME
    """)


@st.cache_data(ttl=3600)
def load_completed(_conn):
    return _conn.query(f"""
        SELECT
            PROJECT_NAME, STATUS, TYPE, FOCUS_AREA,
            SOURCE_SYSTEM, ENGINEER_S_ AS ENGINEERS,
            ARCHITECT, ACV_EACV AS EACV,
            SOW_SIGNED_DATE, ACTUAL_MIGRATION_END,
            GO_LIVE_DATE_PER_SFDC_ AS GO_LIVE_DATE,
            SOW_TO_FDE_MIGRATION_COMPLETE, SOW_TO_SFDC_GO_LIVE,
            NOTES
        FROM {SCHEMA}.COMPLETED_FDE_PROJECTS
        WHERE DS = ({_latest('COMPLETED_FDE_PROJECTS')})
          AND PROJECT_NAME IS NOT NULL AND PROJECT_NAME != ''
        ORDER BY PROJECT_NAME
    """)


# ── load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading AIM & FDE data..."):
    aim_df        = load_aim(conn)
    active_df     = load_active(conn)
    onboarding_df = load_onboarding(conn)
    completed_df  = load_completed(conn)

aim_mse   = aim_df[aim_df['STATUS'].str.contains('Completed', na=False, case=False)]
aim_other = aim_df[~aim_df['STATUS'].str.contains('Completed', na=False, case=False)]

# ── Partner summary table (AIM only — FDE tables have no partner dimension) ──
_partner_summary = (
    aim_df[aim_df['PARTNER'].notna() & (aim_df['PARTNER'] != '')]
    .groupby('PARTNER')
    .agg(
        mse_handover    =('STATUS', lambda x: x.str.contains('Completed', na=False).sum()),
        under_discussion=('STATUS', lambda x: (x == 'Under Discussion').sum()),
        not_pursuing    =('STATUS', lambda x: (x == 'Not Pursuing').sum()),
        blank_status    =('STATUS', lambda x: (x.isna() | (x == '')).sum()),
        total           =('STATUS', 'count'),
    )
    .reset_index()
    # Only show partners with at least one classified engagement
    .query('mse_handover > 0 or under_discussion > 0 or not_pursuing > 0')
    .sort_values(['mse_handover', 'total'], ascending=False)
)
_unique_partners  = len(_partner_summary)
_partners_mse     = int((_partner_summary['mse_handover'] > 0).sum())
_partners_discuss = int((_partner_summary['under_discussion'] > 0).sum())

# ── header ────────────────────────────────────────────────────────────────────
st.title(":material/rocket_launch: AIM Adoption")
st.caption("Partner AIM engagement tracker & FDE project pipeline | Data refreshed daily via Fivetran")

with st.expander(":material/info: How this data is retrieved — and what filters apply", expanded=False):
    st.markdown("""
**⚠️ Sidebar filters do not apply to this page.**
All data is sourced directly from Snowflake's internal AIM and FDE tracking sheets
(synced via Fivetran) and is **not filtered** by Region, Theater, Partner, or Use Case Stage
selected in the sidebar. The data shown always reflects the **full global view**.

---

**Data sources**

| Table | What it tracks |
|---|---|
| `SNOWSCIENCE.SNOWCONVERT.SF_PARTNER_AIM_ENGAGEMENT_TRACKER` | Partner-nominated AIM engagements — tracks which SI partners are engaged in AIM advisory or hands-on-keyboard work, and whether they have been handed over to an MSE |
| `SNOWSCIENCE.SNOWCONVERT.ACTIVE_FDE_PROJECTS_RESOURCING` | FDE projects currently in active assessment or migration |
| `SNOWSCIENCE.SNOWCONVERT.ONBOARDING_FDE_PROJECTS_SIGNED_RESOURCING` | FDE projects with a signed SOW — in onboarding or pre-assessment phase |
| `SNOWSCIENCE.SNOWCONVERT.COMPLETED_FDE_PROJECTS` | FDE migrations that have been completed and handed off |

**Refresh cadence:** Fivetran syncs these tables daily. The `DS` column stores the snapshot date —
this page always reads the latest snapshot (`MAX(DS)`).

---

**AIM Engagement statuses**

| Status | Meaning |
|---|---|
| `Under Discussion` | Engagement being evaluated — partner and Snowflake team are in active conversation |
| `Completed / Handed Over To MSE` | AIM work is complete; a Migration Services Engineer (MSE) has been assigned |
| `Not Pursuing` | Engagement was deprioritized or dropped |
| *(blank)* | Early-stage entry — no formal status assigned yet in the source sheet |

**AIM Stages** (boolean flags on each engagement):
`1 - Qualify → 2 - Assess → 3 - Validate → 4 - AIM Deployed`
    """)

# ── top KPI metrics ───────────────────────────────────────────────────────────
st.markdown("---")
st.markdown('<p class="aim-section-label">AIM Engagements</p>', unsafe_allow_html=True)
aim_discuss      = int((aim_df['STATUS'] == 'Under Discussion').sum())
aim_not_pursuing = int((aim_df['STATUS'] == 'Not Pursuing').sum())
aim_total        = aim_discuss + len(aim_mse) + aim_not_pursuing

def _eacv_sum(df):
    return pd.to_numeric(df['EACV'], errors='coerce').sum()

active_eacv     = _eacv_sum(active_df)
onboarding_eacv = _eacv_sum(onboarding_df)
completed_eacv  = _eacv_sum(completed_df[completed_df['STATUS'] == 'Completed'])

def _kpi_item(label, value):
    return (f'<div style="flex:1;min-width:120px;">'
            f'<div style="color:#0b6c96;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">{label}</div>'
            f'<div style="color:#003a5c;font-weight:800;font-size:28px;line-height:1.1;">{value}</div>'
            f'</div>')

_aim_items = "".join([
    _kpi_item("Total AIM Engagements", aim_total),
    _kpi_item("Under Discussion", aim_discuss),
    _kpi_item("Handed Over to MSE", len(aim_mse)),
    _kpi_item("Not Pursuing", aim_not_pursuing),
])
st.markdown(
    f'<div style="border:2px solid #29B5E8;border-radius:8px;padding:14px 20px;background:rgba(41,181,232,0.06);margin-bottom:12px;">'
    f'<div style="color:#003a5c;font-weight:700;font-size:15px;margin-bottom:12px;">AIM Engagements</div>'
    f'<div style="display:flex;gap:40px;flex-wrap:wrap;">{_aim_items}</div>'
    f'</div>',
    unsafe_allow_html=True
)

_fde_items = "".join([
    _kpi_item("Active FDE Projects", len(active_df)),
    _kpi_item("Onboarding / Signed", len(onboarding_df)),
    _kpi_item("Completed FDE Projects", len(completed_df[completed_df['STATUS'] == 'Completed'])),
    _kpi_item("Active EACV", f"${active_eacv/1_000_000:.1f}M"),
    _kpi_item("Onboarding EACV", f"${onboarding_eacv/1_000_000:.1f}M"),
    _kpi_item("Completed EACV", f"${completed_eacv/1_000_000:.1f}M"),
])
st.markdown(
    f'<div style="border:2px solid #29B5E8;border-radius:8px;padding:14px 20px;background:rgba(41,181,232,0.06);margin-bottom:12px;">'
    f'<div style="color:#003a5c;font-weight:700;font-size:15px;margin-bottom:12px;">FDE Projects</div>'
    f'<div style="display:flex;gap:40px;flex-wrap:wrap;">{_fde_items}</div>'
    f'</div>',
    unsafe_allow_html=True
)

st.markdown("---")

# ── Partner Summary Table ─────────────────────────────────────────────────────
st.subheader("Partner Summary")
st.caption(
    f"{_unique_partners} unique partners in AIM tracker — "
    f"{_partners_mse} with MSE handover, {_partners_discuss} with active discussions."
)

_ps_display = _partner_summary.drop(columns=['blank_status'], errors='ignore').rename(columns={
    'PARTNER':          'Partner',
    'mse_handover':     'AIM → MSE',
    'under_discussion': 'Under Discussion',
    'not_pursuing':     'Not Pursuing',
    'total':            'Total Engagements',
})
st.dataframe(
    _ps_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        'Partner':            st.column_config.TextColumn(width='medium'),
        'AIM → MSE':          st.column_config.NumberColumn(width='small'),
        'Under Discussion':   st.column_config.NumberColumn(width='small'),
        'Not Pursuing':       st.column_config.NumberColumn(width='small'),
        'Total Engagements':  st.column_config.NumberColumn(width='small'),
    }
)

st.markdown("---")

# ── SECTION 1: AIM Pipeline — Under Discussion ────────────────────────────────
st.subheader(f"AIM Pipeline — Under Discussion ({aim_discuss})")
st.caption("Engagements still being evaluated — not yet handed over to MSE.")

_under = aim_df[aim_df['STATUS'] == 'Under Discussion']
if len(_under) > 0:
    st.dataframe(
        _under[['PARTNER', 'ACCOUNT', 'THEATER', 'REGION', 'ENGAGEMENT',
                 'SE', 'PDM_LEAD', 'PSM_LEAD', 'PSE', 'NOMINATED_BY', 'NOTES']].rename(columns={
            'PARTNER':       'Partner',
            'ACCOUNT':       'Account',
            'THEATER':       'Theater',
            'REGION':        'Region',
            'ENGAGEMENT':    'Engagement Type',
            'PDM_LEAD':      'PDM Lead',
            'PSM_LEAD':      'PSM Lead',
            'NOMINATED_BY':  'Nominated By',
            'NOTES':         'Notes',
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            'Partner': st.column_config.TextColumn(width='medium'),
            'Notes':   st.column_config.TextColumn(width='large'),
        }
    )

st.markdown("---")

# ── SECTION 2: AIM Engagements Handed Over to MSE ────────────────────────────
st.subheader(f"AIM Engagements Handed Over to MSE ({len(aim_mse)})")
st.caption("Status: **Completed / Handed Over To MSE** — nominated partner field engagements where AIM work is complete and MSE has been assigned.")

if len(aim_mse) > 0:
    # Stage progress summary
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Advisory", int((aim_mse['ENGAGEMENT'] == 'Advisory').sum()))
    col_b.metric("Hands-on-keyboard", int((aim_mse['ENGAGEMENT'] == 'Hands-on-keyboard').sum()))
    col_c.metric("AIM Fully Staged (Q+A+V)", int(
        aim_mse[['QUALIFY','ASSESS','VALIDATE']]
        .apply(lambda col: col.apply(lambda v: str(v).strip().lower() == 'true'))
        .all(axis=1).sum()
    ))

    # Normalise boolean stage columns (Snowflake may return bool or string)
    def _to_bool(val):
        if isinstance(val, bool): return val
        if isinstance(val, str):  return val.strip().lower() == 'true'
        return bool(val) if val is not None else False

    aim_display = aim_mse.copy()
    for _sc in ['QUALIFY', 'ASSESS', 'VALIDATE', 'AIM_DEPLOYED']:
        if _sc in aim_display.columns:
            aim_display[_sc] = aim_display[_sc].apply(_to_bool)

    # Stage progress as individual ✅ / — columns
    aim_display['Qualify']  = aim_display['QUALIFY'].map({True: '✅', False: '—'})
    aim_display['Assess']   = aim_display['ASSESS'].map({True: '✅', False: '—'})
    aim_display['Validate'] = aim_display['VALIDATE'].map({True: '✅', False: '—'})
    aim_display['Deployed'] = aim_display['AIM_DEPLOYED'].map({True: '✅', False: '—'})

    display_cols = [
        'PARTNER', 'ACCOUNT', 'THEATER', 'REGION', 'ENGAGEMENT',
        'USE_CASE_LINK', 'MSE_ASSIGNED', 'PDM_LEAD', 'PSM_LEAD', 'PSE', 'SE',
        'NOMINATED_BY', 'Qualify', 'Assess', 'Validate', 'Deployed', 'NOTES',
    ]
    display_cols = [c for c in display_cols if c in aim_display.columns]

    st.dataframe(
        aim_display[display_cols].rename(columns={
            'ACCOUNT':       'Account',
            'PARTNER':       'Partner',
            'THEATER':       'Theater',
            'REGION':        'Region',
            'ENGAGEMENT':    'Engagement Type',
            'USE_CASE_LINK': 'Use Case / SFDC Link',
            'MSE_ASSIGNED':  'MSE Assigned',
            'PDM_LEAD':      'PDM Lead',
            'PSM_LEAD':      'PSM Lead',
            'NOMINATED_BY':  'Nominated By',
            'NOTES':         'Notes',
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            'Use Case / SFDC Link': st.column_config.LinkColumn(
                'Use Case / SFDC Link', display_text='Open in SFDC', width='small'
            ),
            'Notes':      st.column_config.TextColumn(width='large'),
            'MSE Assigned': st.column_config.TextColumn(width='medium'),
            'Qualify':    st.column_config.TextColumn(width='small'),
            'Assess':     st.column_config.TextColumn(width='small'),
            'Validate':   st.column_config.TextColumn(width='small'),
            'Deployed':   st.column_config.TextColumn(width='small'),
        }
    )

    # Theater breakdown
    st.markdown("**By Theater**")
    _theater = aim_mse.groupby('THEATER').size().reset_index(name='Count').sort_values('Count', ascending=False)
    st.dataframe(_theater, use_container_width=False, hide_index=True)

st.markdown("---")

# ── Not Pursuing ──────────────────────────────────────────────────────────────────────────────
_not_pursuing = aim_df[aim_df['STATUS'] == 'Not Pursuing']
st.subheader(f"Not Pursuing ({len(_not_pursuing)})")
st.caption("Engagements that were evaluated but deprioritized or dropped.")

if len(_not_pursuing) > 0:
    st.dataframe(
        _not_pursuing[['PARTNER', 'ACCOUNT', 'THEATER', 'REGION', 'ENGAGEMENT',
                        'SE', 'PDM_LEAD', 'PSM_LEAD', 'PSE', 'NOMINATED_BY', 'NOTES']].rename(columns={
            'PARTNER':      'Partner',
            'ACCOUNT':      'Account',
            'THEATER':      'Theater',
            'REGION':       'Region',
            'ENGAGEMENT':   'Engagement Type',
            'PDM_LEAD':     'PDM Lead',
            'PSM_LEAD':     'PSM Lead',
            'NOMINATED_BY': 'Nominated By',
            'NOTES':        'Notes',
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            'Partner': st.column_config.TextColumn(width='medium'),
            'Notes':   st.column_config.TextColumn(width='large'),
        }
    )
else:
    st.info("No engagements marked as Not Pursuing.")

st.markdown("---")

# ── SECTION 3: Active FDE Projects ───────────────────────────────────────────
st.subheader(f"Active FDE Projects ({len(active_df)})")
st.caption("FDE projects currently in flight — assessment or migration in progress.")

if len(active_df) > 0:
    # Status badges
    _status_counts = active_df['STATUS'].value_counts()
    cols = st.columns(len(_status_counts))
    for i, (status, cnt) in enumerate(_status_counts.items()):
        cols[i].metric(status or 'Unknown', cnt)

    # EACV
    st.metric("Total Pipeline EACV", f"${active_eacv/1_000_000:.1f}M")

    _active_display = active_df.copy()
    _active_display['EACV_FMT'] = pd.to_numeric(_active_display['EACV'], errors='coerce').apply(
        lambda x: f"${x/1000:.0f}K" if pd.notna(x) and x > 0 else '—'
    )

    st.dataframe(
        _active_display[['PROJECT_NAME', 'STATUS', 'TYPE', 'SOURCE_SYSTEM',
                          'FOCUS_AREA', 'EACV_FMT', 'ARCHITECT', 'ENGINEERS',
                          'SOW_SIGNED_DATE', 'MIGRATION_END_DATE_PLANNED_', 'NOTES']].rename(columns={
            'PROJECT_NAME': 'Project', 'SOURCE_SYSTEM': 'Source System',
            'FOCUS_AREA': 'Focus Area', 'EACV_FMT': 'EACV',
            'SOW_SIGNED_DATE': 'SOW Signed', 'MIGRATION_END_DATE_PLANNED_': 'Planned End',
            'NOTES': 'Notes',
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            'Notes': st.column_config.TextColumn(width='large'),
            'Engineers': st.column_config.TextColumn(width='medium'),
        }
    )

    # Source system breakdown
    st.markdown("**By Source System**")
    _src = active_df['SOURCE_SYSTEM'].fillna('Unknown').value_counts().reset_index()
    _src.columns = ['Source System', 'Count']
    st.dataframe(_src, use_container_width=False, hide_index=True)

st.markdown("---")

# ── SECTION 3: Onboarding / Signed Projects ───────────────────────────────────
st.subheader(f"Onboarding / Signed FDE Projects ({len(onboarding_df)})")
st.caption("SOW signed — projects in onboarding, resourcing, or pre-assessment phase.")

if len(onboarding_df) > 0:
    _delayed = int((onboarding_df['STATUS'].str.lower() == 'delayed').sum())
    col1, col2, col3 = st.columns(3)
    col1.metric("Total", len(onboarding_df))
    col2.metric("Delayed / At Risk", _delayed)
    col3.metric("Total EACV", f"${onboarding_eacv/1_000_000:.1f}M")

    _onb_display = onboarding_df.copy()
    _onb_display['EACV_FMT'] = pd.to_numeric(_onb_display['EACV'], errors='coerce').apply(
        lambda x: f"${x/1000:.0f}K" if pd.notna(x) and x > 0 else '—'
    )

    st.dataframe(
        _onb_display[['PROJECT_NAME', 'STATUS', 'TYPE', 'SOURCE_SYSTEM',
                       'FOCUS_AREA', 'EACV_FMT', 'ARCHITECT', 'ENGINEERS',
                       'SOW_SIGNED_DATE', 'PLANNED_ASSESSMENT_START', 'NOTES']].rename(columns={
            'PROJECT_NAME': 'Project', 'SOURCE_SYSTEM': 'Source System',
            'FOCUS_AREA': 'Focus Area', 'EACV_FMT': 'EACV',
            'SOW_SIGNED_DATE': 'SOW Signed', 'PLANNED_ASSESSMENT_START': 'Assessment Start',
            'NOTES': 'Notes',
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            'Notes': st.column_config.TextColumn(width='large'),
            'Engineers': st.column_config.TextColumn(width='medium'),
        }
    )

st.markdown("---")

# ── SECTION 4: Completed FDE Projects ────────────────────────────────────────
_completed_only = completed_df[completed_df['STATUS'] == 'Completed']
st.subheader(f"Completed FDE Projects ({len(_completed_only)})")
st.caption("FDE migrations completed and handed off to customer.")

if len(_completed_only) > 0:
    _avg_sow_to_mig = pd.to_numeric(_completed_only['SOW_TO_FDE_MIGRATION_COMPLETE'], errors='coerce').mean()
    _avg_sow_to_live = pd.to_numeric(_completed_only['SOW_TO_SFDC_GO_LIVE'], errors='coerce').mean()

    col1, col2, col3 = st.columns(3)
    col1.metric("Completed Projects", len(_completed_only))
    col2.metric("Avg SOW → Migration Complete", f"{_avg_sow_to_mig:.0f}d" if pd.notna(_avg_sow_to_mig) else "—")
    col3.metric("Avg SOW → SFDC Go-Live", f"{_avg_sow_to_live:.0f}d" if pd.notna(_avg_sow_to_live) else "—")
    st.metric("Total Completed EACV", f"${completed_eacv/1_000_000:.1f}M")

    _comp_display = _completed_only.copy()
    _comp_display['EACV_FMT'] = pd.to_numeric(_comp_display['EACV'], errors='coerce').apply(
        lambda x: f"${x/1000:.0f}K" if pd.notna(x) and x > 0 else '—'
    )

    st.dataframe(
        _comp_display[['PROJECT_NAME', 'TYPE', 'SOURCE_SYSTEM', 'FOCUS_AREA',
                        'EACV_FMT', 'ARCHITECT', 'ENGINEERS',
                        'SOW_SIGNED_DATE', 'ACTUAL_MIGRATION_END', 'GO_LIVE_DATE',
                        'SOW_TO_FDE_MIGRATION_COMPLETE', 'SOW_TO_SFDC_GO_LIVE', 'NOTES']].rename(columns={
            'PROJECT_NAME': 'Project', 'SOURCE_SYSTEM': 'Source System',
            'FOCUS_AREA': 'Focus Area', 'EACV_FMT': 'EACV',
            'SOW_SIGNED_DATE': 'SOW Signed', 'ACTUAL_MIGRATION_END': 'Migration End',
            'GO_LIVE_DATE': 'Go-Live', 'SOW_TO_FDE_MIGRATION_COMPLETE': 'SOW→Mig (days)',
            'SOW_TO_SFDC_GO_LIVE': 'SOW→GoLive (days)', 'NOTES': 'Notes',
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            'Notes': st.column_config.TextColumn(width='large'),
            'Engineers': st.column_config.TextColumn(width='medium'),
            'SOW→Mig (days)': st.column_config.NumberColumn(format='%.0f d'),
            'SOW→GoLive (days)': st.column_config.NumberColumn(format='%.0f d'),
        }
    )

# Cancelled
_cancelled = completed_df[completed_df['STATUS'] == 'Canceled']
if len(_cancelled) > 0:
    with st.expander(f"Cancelled projects ({len(_cancelled)})"):
        st.dataframe(_cancelled[['PROJECT_NAME', 'STATUS', 'NOTES']].rename(
            columns={'PROJECT_NAME': 'Project', 'NOTES': 'Notes'}),
            use_container_width=True, hide_index=True)

st.markdown("---")

st.caption("Data sourced from SNOWSCIENCE.SNOWCONVERT | Refreshed daily")
