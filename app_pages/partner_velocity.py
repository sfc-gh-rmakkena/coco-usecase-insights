import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from utils.queries import get_partner_velocity_data
from utils import resolve_partner_filter
from utils.ask_ai import build_filter_context
import datetime
conn = st.session_state.conn
selected_partners = st.session_state.get("selected_partners", [])

# All 24 managed partner aliases — constant so cache key is stable
_MANAGED_PARTNERS_SQL = (
    "'Accenture','Capgemini Technologies LLC','Cognizant Technology Solutions US Corp',"
    "'Deloitte Consulting','EY','Ernst & Young (EY)','IBM','IBM Consulting',"
    "'7Rivers, Inc','Aimpoint Digital','BlueCloud Services Inc','kipi.ai','Kipi.ai',"
    "'evolv Consulting','Infostrux Solutions Inc.','Infosys','KPMG LLP',"
    "'LTM','LTI Mindtree','NTT DATA Group Corporation','phData, Inc.',"
    "'Slalom, LLC.','Squadron Data Inc','Tredence Inc.'"
)

QUARTER_ORDER = ['FY26 Q1', 'FY26 Q2', 'FY26 Q3', 'FY26 Q4', 'FY27 Q1', 'FY27 Q2']
CATEGORY_COLORS = {
    'AI / ML':               '#1f77b4',
    'Data Engineering':      '#ff7f0e',
    'DWH / Migration':       '#2ca02c',
    'Platform / Governance': '#d62728',
    'Apps / Data Sharing':   '#9467bd',
}
# Approved soft palette for FY26→FY27 comparison
_GREEN  = '#34d399'   # faster in FY27 (darker mint)
_RED    = '#f87171'   # slower in FY27 (darker rose)
_GREEN_TXT = '#065f46'
_RED_TXT   = '#7f1d1d'
_GRAY   = '#e2e8f0'   # FY26 baseline bars

MIN_N = 3


st.title(":material/speed: Partner Implementation Velocity")
st.caption(
    "Compares how quickly managed partners deploy use cases of similar workload types: "
    "**FY26** (Feb 2025–Jan 2026) vs **FY27 Q1+Q2** (Feb 2026–Jul 2026). "
    "Workload categories assigned by AI from Salesforce descriptions."
)

# ---------- Load data ----------
_col_refresh, _col_info = st.columns([1, 6])
with _col_refresh:
    if st.button("↺ Refresh Data", help="Force re-query from Snowflake, bypassing the weekly cache"):
        get_partner_velocity_data.clear()
        st.rerun()
with _col_info:
    st.caption(
        "Data is cached weekly. GSI numbers are global (all theaters); "
        "RSI numbers are NoAM only. Click **↺ Refresh Data** to force an update."
    )

with st.spinner("Classifying use cases with AI... (cached weekly — first load ~2 min)"):
    raw = get_partner_velocity_data(conn, _MANAGED_PARTNERS_SQL)

df = raw.copy()
df.columns = [c.upper() for c in df.columns]
df = df[df['WORKLOAD_CATEGORY'].notna() & df['FISCAL_QUARTER'].notna()]
df['DAYS_FULL_CYCLE'] = pd.to_numeric(df['DAYS_FULL_CYCLE'], errors='coerce')
df = df[df['DAYS_FULL_CYCLE'].notna()]

if selected_partners:
    names = resolve_partner_filter(selected_partners)
    df = df[df['PARTNER_NAME'].isin(names)]

if len(df) == 0:
    st.warning("No data for the selected partner filter.")
    st.stop()

st.caption(f"Showing **{len(df):,}** deployed use cases across **{df['PARTNER_NAME'].nunique()}** partners.")

# ---------- Summary ----------
df['FISCAL_YEAR'] = df['FISCAL_QUARTER'].str[:4]   # 'FY26' or 'FY27'
_fy26 = df[df['FISCAL_YEAR'] == 'FY26']
_fy27 = df[df['FISCAL_YEAR'] == 'FY27']
_fy26_med = _fy26['DAYS_FULL_CYCLE'].median()
_fy27_med = _fy27['DAYS_FULL_CYCLE'].median()
_delta_overall = _fy26_med - _fy27_med  # positive = faster in FY27

# Inject context for Ask AI
st.session_state.ask_ai_context = (
    f"Current page: Partner Velocity. Partners: {df['PARTNER_NAME'].nunique()}. "
    f"Total deployed UCs: {len(df)} (FY26+FY27).\n"
    f"FY26 overall median: {_fy26_med:.0f} days ({len(_fy26)} UCs). "
    f"FY27 overall median: {_fy27_med:.0f} days ({len(_fy27)} UCs). "
    f"Overall delta: {_delta_overall:+.0f} days (positive = faster in FY27)."
    + build_filter_context()
)

# Per-partner FY26 vs FY27 medians (min 3 UCs each cohort)
_pp = (
    df.groupby(['PARTNER_NAME', 'FISCAL_YEAR'])['DAYS_FULL_CYCLE']
    .agg(['median', 'count'])
    .reset_index()
)
_pp26 = _pp[(_pp['FISCAL_YEAR'] == 'FY26') & (_pp['count'] >= MIN_N)].rename(columns={'median': 'fy26'})
_pp27 = _pp[(_pp['FISCAL_YEAR'] == 'FY27') & (_pp['count'] >= MIN_N)].rename(columns={'median': 'fy27'})
_pp_both = _pp26[['PARTNER_NAME', 'fy26']].merge(_pp27[['PARTNER_NAME', 'fy27']], on='PARTNER_NAME')
_pp_both['delta'] = _pp_both['fy26'] - _pp_both['fy27']
_n_faster = (_pp_both['delta'] > 0).sum()
_n_slower = (_pp_both['delta'] < 0).sum()
_best = _pp_both.loc[_pp_both['delta'].idxmax()] if len(_pp_both) else None
_worst = _pp_both.loc[_pp_both['delta'].idxmin()] if len(_pp_both) else None

_top_cat = (
    df[df['FISCAL_YEAR'] == 'FY27'].groupby('WORKLOAD_CATEGORY')['DAYS_FULL_CYCLE'].median()
    .sort_values().index[0] if len(_fy27) else 'N/A'
)

_dir = "faster" if _delta_overall > 0 else "slower"
_arrow = "↑" if _delta_overall > 0 else "↓"

_summary_lines = [
    f"Across all managed partners, median deployment time is "
    f"**{_arrow} {abs(_delta_overall):.0f} days {_dir}** in FY27 Q1+Q2 "
    f"({_fy27_med:.0f} days) vs FY26 ({_fy26_med:.0f} days).",

    f"Of the **{len(_pp_both)} partners** with sufficient data in both cohorts, "
    f"**{_n_faster} are accelerating** and **{_n_slower} are slowing down**.",
]
if _best is not None:
    _summary_lines.append(
        f"Fastest improver: **{_best['PARTNER_NAME']}** (↓ {_best['delta']:.0f} days); "
        f"most slowed: **{_worst['PARTNER_NAME']}** (↑ {abs(_worst['delta']):.0f} days longer)."
    )
_summary_lines.append(
    f"Fastest workload category in FY27: **{_top_cat}** by median cycle time."
)
_summary_lines.append(
    f"Use the tabs below to explore by workload, rank all partners, or drill into a single partner."
)

with st.expander("Summary", expanded=True):
    for line in _summary_lines:
        st.markdown(f"- {line}")

tab1, tab2, tab3 = st.tabs([
    ":material/grid_view: Workload Breakdown",
    ":material/leaderboard: Partner Ranking",
    ":material/person_search: Partner Drill-Down",
])


# ============================================================
# TAB 1 — 5-Panel Workload Grid (Option I)
# ============================================================
with tab1:
    st.subheader("Workload Drill-Down — All Partners × All Workloads")
    st.caption(
        f"Δ Days FY26 → FY27 Q1+Q2 per partner per workload. "
        f"Green = faster in FY27, Red = slower. Requires ≥ {MIN_N} UCs per cohort per cell."
    )

    cohort_df_t1 = df[df['COHORT'].notna()]
    if cohort_df_t1.empty:
        st.info("No cohort data available.")
    else:
        # Per-partner per-workload FY26 and FY27 medians
        _p26_grid = (
            cohort_df_t1[cohort_df_t1['COHORT'] == 'FY26']
            .groupby(['PARTNER_NAME', 'WORKLOAD_CATEGORY'])['DAYS_FULL_CYCLE']
            .agg(med='median', n='count').reset_index()
            .rename(columns={'med': 'fy26', 'n': 'n26'})
        )
        _p27_grid = (
            cohort_df_t1[cohort_df_t1['COHORT'] == 'FY27 Q1+Q2']
            .groupby(['PARTNER_NAME', 'WORKLOAD_CATEGORY'])['DAYS_FULL_CYCLE']
            .agg(med='median', n='count').reset_index()
            .rename(columns={'med': 'fy27', 'n': 'n27'})
        )
        grid = _p26_grid.merge(_p27_grid, on=['PARTNER_NAME', 'WORKLOAD_CATEGORY'], how='inner')
        grid = grid[(grid['n26'] >= MIN_N) & (grid['n27'] >= MIN_N)].copy()
        grid['delta'] = grid['fy26'] - grid['fy27']

        if len(grid) == 0:
            st.info(f"Not enough data. Try removing the sidebar partner filter.")
        else:
            cats = list(CATEGORY_COLORS.keys())
            n_cats = len(cats)

            fig_grid = make_subplots(
                rows=1, cols=n_cats,
                subplot_titles=cats,
                shared_yaxes=True,
                horizontal_spacing=0.04,
            )

            for ci, cat in enumerate(cats, start=1):
                sub = grid[grid['WORKLOAD_CATEGORY'] == cat].sort_values('delta', ascending=True)
                if len(sub) == 0:
                    continue

                partners_sub = sub['PARTNER_NAME'].tolist()
                deltas_sub   = sub['delta'].tolist()
                dot_colors   = [
                    _GREEN if d > 10 else '#6ee7b7' if d > 0 else '#fbbf24' if d > -10 else _RED
                    for d in deltas_sub
                ]

                # Stems (zero → delta)
                for i, (p, d) in enumerate(zip(partners_sub, deltas_sub)):
                    fig_grid.add_shape(
                        type='line', x0=0, x1=d, y0=i, y1=i,
                        line=dict(color=dot_colors[i], width=2),
                        row=1, col=ci,
                    )

                # Dots
                fig_grid.add_trace(go.Scatter(
                    x=deltas_sub, y=list(range(len(partners_sub))),
                    mode='markers+text',
                    marker=dict(color=dot_colors, size=12, line=dict(color='white', width=1.5)),
                    text=[f"{d:+.0f}" for d in deltas_sub],
                    textposition=['middle right' if d >= 0 else 'middle left' for d in deltas_sub],
                    textfont=dict(size=8, color='#334155'),
                    customdata=partners_sub,
                    hovertemplate='<b>%{customdata}</b><br>' + cat + '<br>Δ = %{x:+.0f} days<extra></extra>',
                    showlegend=False,
                ), row=1, col=ci)

                # Zero reference line
                fig_grid.add_vline(x=0, line_color='#d1d5db', line_width=1, line_dash='dot', row=1, col=ci)

                # Y-axis tick labels only on first panel
                axis_key = 'yaxis' if ci == 1 else f'yaxis{ci}'
                fig_grid.layout[axis_key].update(
                    tickvals=list(range(len(partners_sub))),
                    ticktext=partners_sub,
                    tickfont=dict(size=9),
                    showticklabels=(ci == 1),
                    range=[-0.5, len(partners_sub) - 0.5],
                    autorange=False,
                )
                axis_x_key = 'xaxis' if ci == 1 else f'xaxis{ci}'
                fig_grid.layout[axis_x_key].update(
                    title=dict(text='Δ Days', font=dict(size=9)),
                    zeroline=False, gridcolor='#f1f5f9', tickfont=dict(size=8),
                )

            all_partners = sorted(grid['PARTNER_NAME'].unique().tolist())
            n_partners   = len(all_partners)

            fig_grid.update_layout(
                plot_bgcolor='#fafafa', paper_bgcolor='white',
                height=max(400, n_partners * 26 + 100),
                margin=dict(t=50, b=40, l=110, r=20),
            )
            st.plotly_chart(fig_grid, use_container_width=True)

            # UC count summary by category and cohort
            st.caption("Use case counts by workload category and cohort")
            _counts = (
                cohort_df_t1.groupby(['COHORT', 'WORKLOAD_CATEGORY'])
                .size().reset_index(name='UCs')
            )
            _count_pivot = _counts.pivot(index='WORKLOAD_CATEGORY', columns='COHORT', values='UCs').fillna(0).astype(int)
            # Ensure consistent column order
            for _col in ['FY26', 'FY27 Q1+Q2']:
                if _col not in _count_pivot.columns:
                    _count_pivot[_col] = 0
            # CoCo UCs in FY27 — requires IS_COCO column in df
            if 'IS_COCO' in cohort_df_t1.columns:
                _coco_fy27 = (
                    cohort_df_t1[(cohort_df_t1['COHORT'] == 'FY27 Q1+Q2') & (cohort_df_t1['IS_COCO'] == True)]
                    .groupby('WORKLOAD_CATEGORY').size().rename('_coco_n')
                )
                _count_pivot = _count_pivot.join(_coco_fy27, how='left')
                _count_pivot['_coco_n'] = _count_pivot['_coco_n'].fillna(0).astype(int)
                _count_pivot['CoCo UCs (FY27)'] = _count_pivot.apply(
                    lambda r: f"{r['_coco_n']} ({round(r['_coco_n'] * 100 / r['FY27 Q1+Q2'])}%)" if r['FY27 Q1+Q2'] > 0 else "0",
                    axis=1
                )
                _count_pivot = _count_pivot.drop(columns=['_coco_n'])
                _count_pivot = _count_pivot[['FY26', 'FY27 Q1+Q2', 'CoCo UCs (FY27)']]
            else:
                _count_pivot = _count_pivot[['FY26', 'FY27 Q1+Q2']]
            _count_pivot['Total'] = _count_pivot['FY26'] + _count_pivot['FY27 Q1+Q2']
            _count_pivot.index.name = 'Workload Category'
            st.dataframe(_count_pivot.reset_index(), use_container_width=True, hide_index=True)

            # --- 3-point dumbbell: FY26 all vs FY27 all vs FY27 CoCo ---
            if 'IS_COCO' in cohort_df_t1.columns:
                st.subheader("FY26 Baseline vs FY27 CoCo — Delivery Speed by Workload")
                st.caption(
                    "Compares median days (decision → go-live) across three groups. "
                    "Diamond = FY27 CoCo-only UCs (IS_COCO=TRUE). Green = faster than FY26, Red = slower."
                )

                _cats_order = ['DWH / Migration', 'AI / ML', 'Platform / Governance',
                               'Apps / Data Sharing', 'Data Engineering']

                _fy26_agg = (cohort_df_t1[cohort_df_t1['COHORT'] == 'FY26']
                             .groupby('WORKLOAD_CATEGORY')['DAYS_FULL_CYCLE']
                             .agg(fy26_med='median', fy26_n='count').reset_index())
                _fy27_agg = (cohort_df_t1[cohort_df_t1['COHORT'] == 'FY27 Q1+Q2']
                             .groupby('WORKLOAD_CATEGORY')['DAYS_FULL_CYCLE']
                             .agg(fy27_all_med='median', fy27_all_n='count').reset_index())
                _coco_agg = (cohort_df_t1[(cohort_df_t1['COHORT'] == 'FY27 Q1+Q2') &
                                          (cohort_df_t1['IS_COCO'] == True)]
                             .groupby('WORKLOAD_CATEGORY')['DAYS_FULL_CYCLE']
                             .agg(fy27_coco_med='median', fy27_coco_n='count').reset_index())

                _dumb = (_fy26_agg
                         .merge(_fy27_agg, on='WORKLOAD_CATEGORY', how='left')
                         .merge(_coco_agg, on='WORKLOAD_CATEGORY', how='left'))
                _dumb = _dumb[_dumb['WORKLOAD_CATEGORY'].isin(_cats_order)].copy()
                _dumb['WORKLOAD_CATEGORY'] = pd.Categorical(
                    _dumb['WORKLOAD_CATEGORY'], categories=_cats_order, ordered=True)
                _dumb = _dumb.sort_values('WORKLOAD_CATEGORY', ascending=False)  # top of chart = first in list

                fig_dumb = go.Figure()

                for _, row in _dumb.iterrows():
                    cat = row['WORKLOAD_CATEGORY']
                    fy26 = float(row['fy26_med']) if pd.notna(row['fy26_med']) else None
                    fy27_all = float(row['fy27_all_med']) if pd.notna(row['fy27_all_med']) else None
                    fy27_coco = float(row['fy27_coco_med']) if pd.notna(row['fy27_coco_med']) else None
                    coco_n = int(row['fy27_coco_n']) if pd.notna(row.get('fy27_coco_n', None)) else 0

                    if fy26 and fy27_coco and coco_n >= 3:
                        coco_color = _GREEN if fy27_coco < fy26 else _RED
                        x_min = min(v for v in [fy26, fy27_all, fy27_coco] if v)
                        x_max = max(v for v in [fy26, fy27_all, fy27_coco] if v)
                        fig_dumb.add_shape(type='line',
                            x0=x_min, x1=x_max, y0=cat, y1=cat,
                            line=dict(color='#e2e8f0', width=2))
                    else:
                        coco_color = _GRAY

                    is_first = (cat == list(_dumb['WORKLOAD_CATEGORY'])[-1])

                    if fy26:
                        fig_dumb.add_trace(go.Scatter(
                            x=[fy26], y=[cat], mode='markers+text',
                            marker=dict(color='#94a3b8', size=14, symbol='circle'),
                            text=[f"{int(fy26)}d"], textposition='top center',
                            textfont=dict(size=9),
                            name='FY26 All', legendgroup='fy26',
                            showlegend=is_first,
                            hovertemplate=f'<b>{cat}</b><br>FY26 All: {int(fy26)}d (n={int(row["fy26_n"])})<extra></extra>'
                        ))

                    if fy27_all:
                        fig_dumb.add_trace(go.Scatter(
                            x=[fy27_all], y=[cat], mode='markers',
                            marker=dict(color='#29B5E8', size=13, symbol='circle-open',
                                        line=dict(width=2.5, color='#29B5E8')),
                            name='FY27 All', legendgroup='fy27all',
                            showlegend=is_first,
                            hovertemplate=f'<b>{cat}</b><br>FY27 All: {int(fy27_all)}d (n={int(row["fy27_all_n"])})<extra></extra>'
                        ))

                    if fy27_coco and coco_n >= 3:
                        delta_label = f"{int(fy26) - int(fy27_coco):+d}d vs FY26"
                        fig_dumb.add_trace(go.Scatter(
                            x=[fy27_coco], y=[cat], mode='markers+text',
                            marker=dict(color=coco_color, size=14, symbol='diamond'),
                            text=[f"{int(fy27_coco)}d"], textposition='bottom center',
                            textfont=dict(size=9, color=coco_color),
                            name='FY27 CoCo Only', legendgroup='fy27coco',
                            showlegend=is_first,
                            hovertemplate=f'<b>{cat}</b><br>FY27 CoCo: {{int(fy27_coco)}}d (n={coco_n})<br>{delta_label}<extra></extra>'
                        ))

                fig_dumb.update_layout(
                    height=350,
                    xaxis=dict(title='Median Days (Decision → Go-Live)', gridcolor='#f1f5f9', zeroline=False),
                    yaxis=dict(tickfont=dict(size=11)),
                    plot_bgcolor='#fafafa', paper_bgcolor='white',
                    legend=dict(orientation='h', y=1.14, font=dict(size=10)),
                    margin=dict(l=160, r=20, t=50, b=40),
                )
                st.plotly_chart(fig_dumb, use_container_width=True)
                st.caption(
                    "Circle (gray) = FY26 all UCs baseline  ·  Open circle (blue) = FY27 all UCs  ·  "
                    "Diamond = FY27 CoCo UCs only (IS_COCO=TRUE, min n=3). "
                    "Green diamond = CoCo faster than FY26. Red diamond = CoCo slower."
                )


# ============================================================
# TAB 2 — Partner Ranking (Option E: Lollipop)
# ============================================================
with tab2:
    cohort_df = df[df['COHORT'].notna()]

    if cohort_df.empty:
        st.info("No cohort data available.")
    else:
        # Compute overall per-partner delta (FY26 median − FY27 median, weighted by UC count)
        p26 = (cohort_df[cohort_df['COHORT'] == 'FY26']
               .groupby('PARTNER_NAME')['DAYS_FULL_CYCLE']
               .agg(fy26_med='median', n26='count').reset_index())
        p27 = (cohort_df[cohort_df['COHORT'] == 'FY27 Q1+Q2']
               .groupby('PARTNER_NAME')['DAYS_FULL_CYCLE']
               .agg(fy27_med='median', n27='count').reset_index())
        rank = p26.merge(p27, on='PARTNER_NAME', how='inner')
        rank = rank[(rank['n26'] >= MIN_N) & (rank['n27'] >= MIN_N)].copy()
        rank['delta'] = rank['fy26_med'] - rank['fy27_med']
        rank = rank.sort_values('delta', ascending=True)  # ascending so top of chart = best

        if len(rank) == 0:
            st.info(f"Not enough partners with ≥ {MIN_N} UCs in both cohorts.")
        else:
            partners = rank['PARTNER_NAME'].tolist()
            deltas = rank['delta'].tolist()

            dot_colors = [
                '#34d399' if d > 15 else
                '#6ee7b7' if d > 0 else
                '#fbbf24' if d > -10 else
                '#f87171'
                for d in deltas
            ]
            verdicts = [
                '↑ Improving' if d > 15 else
                '↑ Slight gain' if d > 0 else
                '→ Flat' if d > -10 else
                '↓ Slowing'
                for d in deltas
            ]
            verdict_colors = [
                '#065f46' if d > 15 else '#166534' if d > 0 else '#92400e' if d > -10 else '#7f1d1d'
                for d in deltas
            ]

            fig_lollipop = go.Figure()

            # Zero reference line
            fig_lollipop.add_shape(
                type='line', x0=0, x1=0, y0=-0.5, y1=len(partners) - 0.5,
                line=dict(color='#d1d5db', width=1, dash='dot')
            )

            # Stems
            for i, (p, d) in enumerate(zip(partners, deltas)):
                fig_lollipop.add_shape(
                    type='line', x0=0, x1=d, y0=i, y1=i,
                    line=dict(color=dot_colors[i], width=2)
                )

            # Dots
            fig_lollipop.add_trace(go.Scatter(
                x=deltas, y=partners,
                mode='markers',
                marker=dict(color=dot_colors, size=16, line=dict(color='white', width=2)),
                hovertemplate='<b>%{y}</b><br>Δ = %{x:+.0f} days in FY27 vs FY26<extra></extra>',
                showlegend=False,
            ))

            # Delta value labels
            fig_lollipop.add_trace(go.Scatter(
                x=deltas, y=partners,
                mode='text',
                text=[f"{d:+.0f}d" for d in deltas],
                textposition=['middle right' if d >= 0 else 'middle left' for d in deltas],
                textfont=dict(size=11, color='#1e293b'),
                showlegend=False,
                hoverinfo='skip',
            ))

            # Verdict labels on right
            x_max = max(deltas) + 25
            fig_lollipop.add_trace(go.Scatter(
                x=[x_max] * len(partners), y=partners,
                mode='text',
                text=verdicts,
                textfont=dict(size=10, color=verdict_colors),
                textposition='middle right',
                showlegend=False,
                hoverinfo='skip',
            ))

            fig_lollipop.update_layout(
                title=dict(text='Partner Velocity Ranking — FY26 → FY27 Q1+Q2 (Δ Days, positive = faster)',
                           font=dict(size=14)),
                xaxis=dict(title='Δ Days (positive = faster in FY27)',
                           zeroline=False, gridcolor='#f1f5f9',
                           range=[min(deltas) - 20, x_max + 60]),
                yaxis=dict(tickfont=dict(size=11)),
                plot_bgcolor='#fafafa', paper_bgcolor='white',
                height=max(400, len(partners) * 28 + 80),
                margin=dict(t=60, b=60, l=110, r=80),
            )
            st.plotly_chart(fig_lollipop, use_container_width=True)

            # Scorecard table
            st.caption("Partner Velocity Scorecard")
            sc = rank.copy()
            sc['Trend'] = sc['delta'].apply(
                lambda x: '↑ Improving' if x > 15 else ('↑ Slight' if x > 0 else ('→ Flat' if x > -10 else '↓ Slowing'))
            )
            sc['FY26 Median'] = sc['fy26_med'].round(0).astype(int)
            sc['FY27 Median'] = sc['fy27_med'].round(0).astype(int)
            sc['Δ Days'] = sc['delta'].round(1)
            st.dataframe(
                sc[['PARTNER_NAME', 'Trend', 'FY26 Median', 'FY27 Median', 'Δ Days', 'n26', 'n27']]
                .rename(columns={'PARTNER_NAME': 'Partner', 'n26': 'FY26 UCs', 'n27': 'FY27 UCs'})
                .sort_values('Δ Days', ascending=False),
                use_container_width=True, hide_index=True,
            )


# ============================================================
# TAB 3 — Partner Drill-Down (Option B revised: gray + green/red bars)
# ============================================================
with tab3:
    st.subheader("Partner Deep-Dive — FY26 vs FY27 by Workload")

    partner_list = sorted(df['PARTNER_NAME'].unique().tolist())
    focus = st.selectbox("Select Partner", partner_list, key="velocity_partner")

    pdf = df[df['PARTNER_NAME'] == focus].copy()
    cohort_pdf = pdf[pdf['COHORT'].notna()]

    st.caption(f"**{focus}** — {len(pdf)} deployed use cases total")

    if len(cohort_pdf) == 0:
        st.info("No FY26/FY27 cohort data for this partner.")
    else:
        # Per-category cohort comparison
        pc26 = (cohort_pdf[cohort_pdf['COHORT'] == 'FY26']
                .groupby('WORKLOAD_CATEGORY')['DAYS_FULL_CYCLE']
                .agg(med='median', n='count').reset_index()
                .rename(columns={'med': 'fy26', 'n': 'n26'}))
        pc27 = (cohort_pdf[cohort_pdf['COHORT'] == 'FY27 Q1+Q2']
                .groupby('WORKLOAD_CATEGORY')['DAYS_FULL_CYCLE']
                .agg(med='median', n='count').reset_index()
                .rename(columns={'med': 'fy27', 'n': 'n27'}))
        pcat = pc26.merge(pc27, on='WORKLOAD_CATEGORY', how='outer')
        pcat = pcat[(pcat['n26'].fillna(0) >= 2) | (pcat['n27'].fillna(0) >= 2)].copy()
        pcat['delta'] = pcat['fy26'] - pcat['fy27']

        if len(pcat) == 0:
            st.info("Not enough use cases per workload category (need ≥ 2 in at least one cohort).")
        else:
            cats = pcat['WORKLOAD_CATEGORY'].tolist()
            fy26_vals = pcat['fy26'].fillna(0).tolist()
            fy27_vals = pcat['fy27'].fillna(0).tolist()
            deltas = pcat['delta'].tolist()

            bar_fill = [_GREEN if d > 0 else _RED if d < 0 else '#cbd5e1' for d in deltas]
            bar_txt_color = [_GREEN_TXT if d > 0 else _RED_TXT if d < 0 else '#475569' for d in deltas]

            # Delta annotations floating above bars
            annotations = []
            for i, (cat, d, f26, f27) in enumerate(zip(cats, deltas, fy26_vals, fy27_vals)):
                if d != 0 and not np.isnan(d):
                    y_pos = max(f26, f27) + 5
                    txt = f"{'↑' if d > 0 else '↓'} {abs(d):.0f}d"
                    annotations.append(dict(
                        x=cat, y=y_pos, text=f"<b>{txt}</b>",
                        showarrow=False,
                        font=dict(size=13, color=_GREEN_TXT if d > 0 else _RED_TXT),
                        xanchor='center',
                    ))

            fig_bars = go.Figure()
            fig_bars.add_trace(go.Bar(
                name='FY26 baseline',
                x=cats,
                y=fy26_vals,
                marker=dict(color=_GRAY, line=dict(color='#94a3b8', width=1.5)),
                text=[f"{int(v)}d" if v > 0 else '' for v in fy26_vals],
                textposition='inside',
                textfont=dict(color='#475569', size=11),
                hovertemplate='<b>FY26 — %{x}</b><br>%{y:.0f} days<extra></extra>',
            ))
            fig_bars.add_trace(go.Bar(
                name='FY27 Q1+Q2',
                x=cats,
                y=fy27_vals,
                marker=dict(color=bar_fill, line=dict(color='white', width=1.5)),
                text=[f"{int(v)}d" if v > 0 else '' for v in fy27_vals],
                textposition='inside',
                textfont=dict(color=bar_txt_color, size=11),
                hovertemplate='<b>FY27 — %{x}</b><br>%{y:.0f} days<extra></extra>',
            ))

            y_max = max([v for v in fy26_vals + fy27_vals if v > 0], default=100)
            fig_bars.update_layout(
                title=dict(text=f"{focus} — Deployment Speed by Workload (FY26 vs FY27)",
                           font=dict(size=14)),
                barmode='group',
                bargap=0.25, bargroupgap=0.05,
                xaxis=dict(tickfont=dict(size=12)),
                yaxis=dict(title='Median Days Decision → Go-Live',
                           gridcolor='#f1f5f9', range=[0, y_max + 30]),
                annotations=annotations,
                legend=dict(orientation='h', y=1.08, x=0),
                plot_bgcolor='#fafafa', paper_bgcolor='white',
                height=420,
                margin=dict(t=80, b=60, l=70, r=20),
            )
            st.plotly_chart(fig_bars, use_container_width=True)
            st.caption(
                "Gray = FY26 baseline · "
                ":green[Green] = faster in FY27 · "
                ":red[Red] = slower in FY27 · "
                "↑↓ label = days difference"
            )

        st.divider()

        # Quarter-by-quarter trend for this partner
        st.subheader("Quarter-by-Quarter Trend")
        pq = (
            pdf[pdf['WORKLOAD_CATEGORY'].notna()]
            .groupby(['FISCAL_QUARTER', 'WORKLOAD_CATEGORY'])['DAYS_FULL_CYCLE']
            .agg(median='median', count='count')
            .reset_index()
        )
        pq = pq[pq['count'] >= 2]
        pq['FISCAL_QUARTER'] = pd.Categorical(pq['FISCAL_QUARTER'], categories=QUARTER_ORDER, ordered=True)
        pq = pq.sort_values('FISCAL_QUARTER')

        if len(pq) > 0:
            fig_trend = go.Figure()
            for cat, color in CATEGORY_COLORS.items():
                sub = pq[pq['WORKLOAD_CATEGORY'] == cat]
                if len(sub) == 0:
                    continue
                fig_trend.add_trace(go.Scatter(
                    x=sub['FISCAL_QUARTER'].astype(str),
                    y=sub['median'],
                    mode='lines+markers',
                    name=cat,
                    line=dict(color=color, width=2.5),
                    marker=dict(size=8),
                    hovertemplate=f"<b>{cat}</b><br>%{{x}}: %{{y:.0f}} days (n=%{{customdata}})<extra></extra>",
                    customdata=sub['count'].values,
                ))
            fig_trend.add_vline(x=3.5, line_dash='dash', line_color='#9ca3af', opacity=0.6)
            fig_trend.update_layout(
                xaxis_title='Fiscal Quarter', yaxis_title='Median Days',
                plot_bgcolor='#fafafa', paper_bgcolor='white',
                legend=dict(orientation='h', y=1.05, x=0),
                height=360, hovermode='x unified',
                margin=dict(t=40, b=40, l=60, r=20),
            )
            st.plotly_chart(fig_trend, use_container_width=True)

        st.divider()

        # Use case detail table
        st.subheader("Use Cases (spot-check AI classification)")
        show_cols = ['FISCAL_QUARTER', 'COHORT', 'WORKLOAD_CATEGORY', 'DAYS_FULL_CYCLE',
                     'DECISION_DATE', 'GO_LIVE_DATE', 'DESCRIPTION_PREVIEW']
        show_cols = [c for c in show_cols if c in pdf.columns]
        st.dataframe(
            pdf[show_cols].sort_values('GO_LIVE_DATE', ascending=False),
            use_container_width=True, hide_index=True,
            column_config={
                'FISCAL_QUARTER':      st.column_config.TextColumn('Quarter'),
                'COHORT':              st.column_config.TextColumn('Cohort'),
                'WORKLOAD_CATEGORY':   st.column_config.TextColumn('AI Category'),
                'DAYS_FULL_CYCLE':     st.column_config.NumberColumn('Days', format='%d'),
                'DECISION_DATE':       st.column_config.DateColumn('Decision Date'),
                'GO_LIVE_DATE':        st.column_config.DateColumn('Go-Live Date'),
                'DESCRIPTION_PREVIEW': st.column_config.TextColumn('Description', width='large'),
            }
        )
