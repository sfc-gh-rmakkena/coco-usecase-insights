import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from utils.queries import (
    get_okr_partner_summary, get_bulk_confidence_scores,
    get_coco_final_wow, get_partner_velocity_data, get_partner_coco_trend_4w,
)
from utils.cortex_helpers import cortex_complete
from utils import resolve_partner_filter, resolve_region_theaters, PARTNER_RENAME_MAP, filter_out_partner_own_accounts

# ── Session state ─────────────────────────────────────────────────────────────
conn              = st.session_state.conn
region            = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])
start_date        = st.session_state.get("okr_start_date", date(2026, 5, 1))
end_date          = st.session_state.get("okr_end_date", date(2026, 7, 31))
include_acct_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter = st.session_state.get("confidence_filter", ["High"])
TARGET            = 75
q_start, q_end    = str(start_date), str(end_date)

st.title("Partner Health Intelligence")
st.caption(
    f"Composite health score · 4-week trends · predictive alerts  |  {start_date} to {end_date}"
)

# ── Data Loading ──────────────────────────────────────────────────────────────
with st.spinner("Loading partner data…"):
    base_summary = get_okr_partner_summary(
        conn, q_start, q_end, region=region, include_account_coco=False, confidence=None
    )
    adoption_wow = get_coco_final_wow(conn)

if selected_partners:
    _pnames = resolve_partner_filter(selected_partners)
    base_summary = base_summary[base_summary["PARTNER_NAME"].isin(_pnames)]

if len(base_summary) == 0:
    st.warning("No partner data. Adjust sidebar filters.")
    st.stop()

bands   = confidence_filter if confidence_filter else ["High", "Medium", "Low"]
summary = base_summary.copy()
bulk_conf = pd.DataFrame()

if include_acct_coco:
    with st.spinner("Scoring accounts…"):
        bulk_conf = get_bulk_confidence_scores(
            conn, base_summary["PARTNER_NAME"].tolist(), q_start, q_end
        )
    if len(bulk_conf) > 0:
        _theaters = resolve_region_theaters(region)
        if _theaters and "THEATER_NAME" in bulk_conf.columns:
            bulk_conf = bulk_conf[bulk_conf["THEATER_NAME"].isin(_theaters)]
        bulk_conf["PARTNER_NAME"] = bulk_conf["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
        # Apply stage filter from sidebar
        _sel_stages = st.session_state.get("selected_stages", [])
        if _sel_stages and "USE_CASE_STAGE" in bulk_conf.columns:
            bulk_conf = bulk_conf[bulk_conf["USE_CASE_STAGE"].isin(_sel_stages)]
        bulk_conf["IS_COCO_FINAL"] = (
            (bulk_conf["IS_COCO"] == True) | (bulk_conf["CONFIDENCE_BAND"].isin(bands))
        )
        coco_eacv = (
            bulk_conf[bulk_conf["IS_COCO_FINAL"]]
            .groupby("PARTNER_NAME")["USE_CASE_EACV"].sum()
            .reset_index().rename(columns={"USE_CASE_EACV": "COCO_EACV"})
        )
        deployed_coco = (
            bulk_conf[bulk_conf["IS_COCO_FINAL"] & (bulk_conf["USE_CASE_STAGE"] == "7 - Deployed")]
            .groupby("PARTNER_NAME")["USE_CASE_ID"].count()
            .reset_index(name="DEPLOYED_COCO_UCS")
        )
        summary = (
            bulk_conf.groupby("PARTNER_NAME")
            .agg(TOTAL_USE_CASES=("USE_CASE_ID","count"), COCO_USE_CASES=("IS_COCO_FINAL","sum"), TOTAL_EACV=("USE_CASE_EACV","sum"))
            .reset_index()
        )
        summary = summary.merge(coco_eacv, on="PARTNER_NAME", how="left")
        summary["COCO_EACV"] = summary["COCO_EACV"].fillna(0)
        summary = summary.merge(deployed_coco, on="PARTNER_NAME", how="left")
        summary["DEPLOYED_COCO_UCS"] = summary["DEPLOYED_COCO_UCS"].fillna(0)
        summary["COCO_PCT"] = (
            summary["COCO_USE_CASES"] * 100.0 / summary["TOTAL_USE_CASES"].replace(0, float("nan"))
        ).round(1).fillna(0)

        _coco_df = bulk_conf[bulk_conf["IS_COCO_FINAL"]].copy()
        _coco_df = filter_out_partner_own_accounts(_coco_df)
        _dedup   = _coco_df.drop_duplicates(subset=["PARTNER_NAME", "ACCOUNT_NAME_UPPER"])
        _surf_cols = ["Q2_CREDITS","Q2_TOKENS","LAST7_CREDITS","PRIOR7_CREDITS","LAST7_TOKENS","PRIOR7_TOKENS",
                      "CLI_CREDITS","CLI_TOKENS","DESKTOP_CREDITS","DESKTOP_TOKENS","UI_CREDITS","UI_TOKENS",
                      "AGENT_REQUESTS","REASONING_AGENT_REQUESTS"]
        for _c in _surf_cols:
            if _c in _dedup.columns:
                _dedup[_c] = pd.to_numeric(_dedup[_c], errors="coerce").fillna(0)
        _agg = {c: (c,"sum") for c in _surf_cols if c in _dedup.columns}
        _agg["ACCTS_WITH_USAGE"] = ("Q2_CREDITS", lambda x: (x > 0).sum())
        _pu = _dedup.groupby("PARTNER_NAME").agg(**_agg).reset_index()
        _tot = pd.to_numeric(_pu.get("Q2_CREDITS", 0), errors="coerce").replace(0, float("nan"))
        for _surf in ["CLI","DESKTOP","UI"]:
            _col = f"{_surf}_CREDITS"
            if _col in _pu.columns:
                _pu[f"{_surf}_PCT"] = (pd.to_numeric(_pu[_col], errors="coerce") / _tot * 100).round(1).fillna(0)
        if all(c in _pu.columns for c in ["LAST7_CREDITS","PRIOR7_CREDITS"]):
            _p7c = pd.to_numeric(_pu["PRIOR7_CREDITS"], errors="coerce").replace(0, float("nan"))
            _pu["CREDITS_WOW_PCT"] = ((pd.to_numeric(_pu["LAST7_CREDITS"], errors="coerce") - pd.to_numeric(_pu["PRIOR7_CREDITS"], errors="coerce")) / _p7c * 100).round(1)
        summary = summary.merge(_pu, on="PARTNER_NAME", how="left")

if len(adoption_wow) > 0:
    _wow = adoption_wow[adoption_wow["PARTNER_NAME"].notna()][["PARTNER_NAME","WOW_COCO_PCT","WOW_COCO_UCS"]].copy()
    _wow["PARTNER_NAME"] = _wow["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
    summary = summary.merge(_wow, on="PARTNER_NAME", how="left")

_bs_cols = [c for c in ["PARTNER_NAME","SE_COMMENTS","PSE_COMMENTS","FEATURE_FLAG"] if c in base_summary.columns]
if len(_bs_cols) > 1:
    summary = summary.merge(base_summary[_bs_cols], on="PARTNER_NAME", how="left")

# ── 4-Week Trend Data ─────────────────────────────────────────────────────────
_partner_tuple = tuple(summary["PARTNER_NAME"].tolist())
trend_df = pd.DataFrame()
try:
    trend_df = get_partner_coco_trend_4w(conn, _partner_tuple, region)
    if len(trend_df) > 0:
        trend_df["PARTNER_NAME"] = trend_df["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
        trend_df["WEEK_START"]   = pd.to_datetime(trend_df["WEEK_START"])
        trend_df["COCO_PCT"]     = pd.to_numeric(trend_df["COCO_PCT"], errors="coerce")
except Exception:
    pass

# Compute per-partner trajectory from trend data
def _compute_trajectory(partner):
    if len(trend_df) == 0:
        return None, None, None
    _pd = trend_df[trend_df["PARTNER_NAME"] == partner].sort_values("WEEK_START")
    if len(_pd) < 2:
        return None, None, None
    _pcts = _pd["COCO_PCT"].dropna().tolist()
    if len(_pcts) < 2:
        return None, None, None
    # Average weekly change (simple linear)
    _slope = (_pcts[-1] - _pcts[0]) / (len(_pcts) - 1)
    # Weeks to target
    _cur = _pcts[-1]
    _weeks_to_target = None
    if _cur < TARGET and _slope > 0:
        _weeks_to_target = round((_cur - TARGET) / _slope * -1)
    elif _cur >= TARGET:
        _weeks_to_target = 0
    if _slope > 0.5:   traj = "↑ Improving"
    elif _slope < -0.5: traj = "↓ Declining"
    else:               traj = "→ Stable"
    return traj, round(_slope, 1), _weeks_to_target

# Velocity delta
vel_delta = {}
try:
    _MANAGED_SQL = "','".join(summary["PARTNER_NAME"].tolist())
    _vel_raw = get_partner_velocity_data(conn, f"'{_MANAGED_SQL}'")
    if len(_vel_raw) > 0 and "DAYS_FULL_CYCLE" in _vel_raw.columns:
        _vel_raw["PARTNER_NAME"] = _vel_raw["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
        _fy_col = next((c for c in ["FY_LABEL","FISCAL_YEAR","FY"] if c in _vel_raw.columns), None)
        if _fy_col:
            _fy26 = _vel_raw[_vel_raw[_fy_col].str.contains("FY26", na=False)]
            _fy27 = _vel_raw[_vel_raw[_fy_col].str.contains("FY27", na=False)]
            if len(_fy26) > 0 and len(_fy27) > 0:
                _m26 = _fy26.groupby("PARTNER_NAME")["DAYS_FULL_CYCLE"].median()
                _m27 = _fy27.groupby("PARTNER_NAME")["DAYS_FULL_CYCLE"].median()
                for p in _m26.index:
                    if p in _m27.index:
                        vel_delta[p] = float(_m27[p] - _m26[p])
except Exception:
    pass

# ── Health Score Computation ──────────────────────────────────────────────────
def _f(row, col, default=0):
    v = row.get(col, default)
    return float(v) if v is not None and pd.notna(v) else float(default)

def compute_health_score(row):
    dims = {}
    pname       = row.get("PARTNER_NAME","")
    coco_pct    = _f(row,"COCO_PCT");  coco_ucs = _f(row,"COCO_USE_CASES")
    total_eacv  = _f(row,"TOTAL_EACV"); coco_eacv = _f(row,"COCO_EACV")
    deployed    = _f(row,"DEPLOYED_COCO_UCS"); accts = _f(row,"ACCTS_WITH_USAGE")
    se_cmts     = _f(row,"SE_COMMENTS"); pse_cmts = _f(row,"PSE_COMMENTS")
    wow_coco    = row.get("WOW_COCO_PCT"); cred_wow = row.get("CREDITS_WOW_PCT")
    cli_pct     = _f(row,"CLI_PCT"); desk_pct = _f(row,"DESKTOP_PCT")
    agent       = _f(row,"AGENT_REQUESTS"); reasoning = _f(row,"REASONING_AGENT_REQUESTS")

    d1 = min(coco_pct / TARGET, 1.0) * 20
    if wow_coco is not None and pd.notna(wow_coco):
        d1 += 10 if float(wow_coco) > 0 else (5 if float(wow_coco) == 0 else 0)
    dims["Adoption"] = round(d1)

    d2 = 0.0
    if cred_wow is not None and pd.notna(cred_wow):
        d2 += 10 if float(cred_wow) > 0 else (5 if float(cred_wow) >= -10 else 0)
    prod_pct = cli_pct + desk_pct
    d2 += 10 if prod_pct >= 50 else (6 if prod_pct >= 25 else (3 if prod_pct > 0 else 0))
    d2 += 5 if reasoning > 0 else (3 if agent > 0 else 0)
    dims["Usage Depth"] = round(d2)

    d3_fy  = 0.0
    d3_dep = 0.0
    delta  = vel_delta.get(pname)
    if delta is not None:
        d3_fy += 10 if delta < -7 else (7 if delta < 0 else (4 if delta <= 7 else 0))
    if coco_ucs > 0:
        d3_dep += min(deployed / coco_ucs, 1.0) * 10
    dims["FY Speed"]    = round(d3_fy)
    dims["Deploy Rate"] = round(d3_dep)
    dims["Velocity"]    = round(d3_fy + d3_dep)

    d4 = 0.0
    if total_eacv > 0: d4 += min(coco_eacv / total_eacv, 1.0) * 10
    if coco_ucs > 0:   d4 += min(accts / coco_ucs, 1.0) * 5
    dims["Pipeline Value"] = round(d4)

    d5 = 0.0
    if coco_ucs > 0: d5 += min((se_cmts + pse_cmts) / coco_ucs, 1.0) * 5
    if wow_coco is not None and pd.notna(wow_coco):
        d5 += 5 if float(wow_coco) > 0 else (2 if float(wow_coco) >= -5 else 0)
    dims["Engagement"] = round(d5)

    return sum(dims.values()), dims

def _band(score):
    if score >= 75: return "Healthy",  "#27ae60"
    if score >= 50: return "On Track", "#2980b9"
    if score >= 30: return "At Risk",  "#e67e22"
    return "Lagging", "#e74c3c"

rows = []
for _, row in summary.iterrows():
    total, dims  = compute_health_score(row)
    band, color  = _band(total)
    traj, slope, w2t = _compute_trajectory(row["PARTNER_NAME"])
    rows.append({
        "PARTNER_NAME":    row["PARTNER_NAME"],
        "HEALTH_SCORE":    total,
        "BAND":            band,
        "COLOR":           color,
        "Trajectory":      traj or "—",
        "Weekly Δ%":       slope,
        "Weeks to Target": w2t,
        **dims,
        "CoCo%":           round(_f(row,"COCO_PCT"),1),
        "WoW CoCo%":       row.get("WOW_COCO_PCT"),
        "7D Credits WoW%":    row.get("CREDITS_WOW_PCT"),
        "CoCo EACV":       _f(row,"COCO_EACV"),
        "Total EACV":      _f(row,"TOTAL_EACV"),
        "Q2 Credits":      row.get("Q2_CREDITS"),
        "Last 7d Credits": row.get("LAST7_CREDITS"),
        "Accts w/ Usage":  int(_f(row,"ACCTS_WITH_USAGE")),
        "Deployed CoCo":   int(_f(row,"DEPLOYED_COCO_UCS")),
        "CLI%":            round(_f(row,"CLI_PCT"),1),
        "Desktop%":        round(_f(row,"DESKTOP_PCT"),1),
        "UI%":             round(_f(row,"UI_PCT"),1),
        "Agent Requests":  int(_f(row,"AGENT_REQUESTS")),
        "Reasoning Agent": int(_f(row,"REASONING_AGENT_REQUESTS")),
    })

scored = pd.DataFrame(rows).sort_values("HEALTH_SCORE", ascending=False).reset_index(drop=True)

if len(scored) == 0:
    st.warning("No scored partners. Enable 'Account Level CoCo' in the sidebar.")
    st.stop()

# Shared column definitions used by both Deep Dive and Scorecard sections
_DIM_COLS  = ["Adoption", "Usage Depth", "FY Speed", "Deploy Rate", "Pipeline Value", "Engagement"]
_DIM_MAXES = [30, 25, 10, 10, 15, 10]
_META_COLS = ["CoCo%", "WoW CoCo%", "7D Credits WoW%", "Q2 Credits", "Last 7d Credits",
              "Accts w/ Usage", "Deployed CoCo", "CoCo EACV", "CLI%", "Desktop%", "UI%",
              "Agent Requests", "Reasoning Agent"]

# ── Leaderboard Chart ─────────────────────────────────────────────────────────
st.divider()
st.subheader("Partner Deep Dive")
_sel = st.selectbox("Select Partner", scored["PARTNER_NAME"].tolist(), key="health_partner_select")

if _sel:
    _row   = scored[scored["PARTNER_NAME"] == _sel].iloc[0]
    _score = int(_row["HEALTH_SCORE"])
    _color = _row["COLOR"]
    _band_label = _row["BAND"]
    _traj_label = _row["Trajectory"]

    _hc1,_hc2,_hc3,_hc4,_hc5 = st.columns(5)
    _hc1.metric("Health Score",    f"{_score} / 100",   help=f"Band: {_band_label}")
    _hc2.metric("CoCo Adoption",   f"{_row['CoCo%']:.1f}%",
                delta=f"{float(_row['WoW CoCo%']):+.1f}%" if pd.notna(_row.get("WoW CoCo%")) else None)
    _hc3.metric("Q2 Credits",
                f"${float(_row['Q2 Credits']):,.0f}" if pd.notna(_row.get("Q2 Credits")) else "N/A",
                delta=f"{float(_row['7D Credits WoW%']):+.1f}% WoW" if pd.notna(_row.get("7D Credits WoW%")) else None)
    _hc4.metric("Trajectory",      _traj_label,
                delta=f"{float(_row['Weekly Δ%']):+.1f}%/wk" if pd.notna(_row.get("Weekly Δ%")) else None)
    _wtt = _row.get("Weeks to Target")
    _hc5.metric("Weeks to Target", f"{int(_wtt)}w" if _wtt is not None and pd.notna(_wtt) and int(_wtt) > 0 else ("At target" if _row["CoCo%"] >= TARGET else "—"))

    _rc1, _rc2 = st.columns([1, 1])

    with _rc1:
        # Radar chart
        _dim_labels = _DIM_COLS
        _dim_maxes  = _DIM_MAXES
        _dim_vals   = [int(_row[d]) for d in _dim_labels]
        _dim_pct    = [v / m * 100 for v, m in zip(_dim_vals, _dim_maxes)]
        _fig_radar  = go.Figure(go.Scatterpolar(
            r=_dim_pct + [_dim_pct[0]],
            theta=_dim_labels + [_dim_labels[0]],
            fill="toself",
            fillcolor=f"rgba({int(_color[1:3],16)},{int(_color[3:5],16)},{int(_color[5:7],16)},0.25)",
            line=dict(color=_color, width=2),
            hovertemplate="%{theta}: %{r:.0f}%<extra></extra>",
        ))
        _fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%", tickfont=dict(size=9)),
                       angularaxis=dict(tickfont=dict(size=11))),
            showlegend=False, height=320,
            margin=dict(t=30, b=30, l=50, r=50),
            title=dict(text=f"{_sel} — {_score}/100 ({_band_label})", x=0.5, font=dict(size=13)),
        )
        st.plotly_chart(_fig_radar, use_container_width=True)

        # 4-week mini trend for this partner
        _pd = trend_df[trend_df["PARTNER_NAME"] == _sel].sort_values("WEEK_START") if len(trend_df) > 0 else pd.DataFrame()
        if len(_pd) >= 2:
            _fig_mini = go.Figure()
            _fig_mini.add_hline(y=TARGET, line_dash="dot", line_color="#e74c3c", annotation_text="Target")
            _fig_mini.add_trace(go.Scatter(
                x=_pd["WEEK_START"], y=_pd["COCO_PCT"],
                mode="lines+markers+text",
                text=[f"{v:.0f}%" for v in _pd["COCO_PCT"]],
                textposition="top center",
                line=dict(color=_color, width=2), marker=dict(size=8),
            ))
            _fig_mini.update_layout(
                xaxis=dict(tickformat="%b %d"), yaxis=dict(title="CoCo%", range=[0, 105]),
                height=200, margin=dict(t=10, b=30, l=40, r=10), showlegend=False,
                title=dict(text="CoCo% — Last 4 Weeks", font=dict(size=12), x=0.5),
            )
            st.plotly_chart(_fig_mini, use_container_width=True)

    with _rc2:
        st.markdown("**Dimension Breakdown**")
        for dim, maxv in zip(_DIM_COLS, _DIM_MAXES):
            _v   = int(_row[dim])
            _pct = _v / maxv * 100
            _bar_color = "#27ae60" if _pct >= 70 else ("#e67e22" if _pct >= 40 else "#e74c3c")
            st.markdown(
                f"**{dim}** &nbsp; {_v}/{maxv} pts "
                f"<span style='color:{_bar_color}'>{'█' * round(_pct/10)}{'░' * (10 - round(_pct/10))}</span> "
                f"<small>({_pct:.0f}%)</small>",
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("**Rule-based Insights**")
        _insights = []
        if _row["CoCo%"] >= TARGET:
            _insights.append(f"✅ Above {TARGET}% OKR target at **{_row['CoCo%']:.0f}%**")
        else:
            _gap = TARGET - _row["CoCo%"]
            if _wtt and pd.notna(_wtt) and int(_wtt) > 0:
                _insights.append(f"⚠️ {_gap:.0f}% below target — projected **{int(_wtt)} weeks** to reach 75% at current pace")
            else:
                _insights.append(f"⚠️ {_gap:.0f}% below {TARGET}% target — trend is {'declining or flat' if _traj_label in ('↓ Declining','→ Stable') else 'improving'}")
        if _traj_label == "↓ Declining":
            _slope_val = _row.get("Weekly Δ%")
            _insights.append(f"📉 CoCo% declining at **{float(_slope_val):+.1f}%/week** — risk of missing Q2 target")
        elif _traj_label == "↑ Improving":
            _insights.append(f"📈 Positive trajectory — gaining **{float(_row.get('Weekly Δ%',0)):+.1f}%/week** over last 4 weeks")
        if int(_row["Reasoning Agent"]) > 0:
            _insights.append(f"🤖 Advanced usage: **{int(_row['Reasoning Agent']):,} reasoning agent requests** — highest maturity signal")
        elif int(_row["Agent Requests"]) > 0:
            _insights.append(f"🤖 Agent adoption: **{int(_row['Agent Requests']):,} coding agent requests**")
        if _row["CLI%"] + _row["Desktop%"] >= 50:
            _insights.append(f"💻 Production-grade surface — CLI {_row['CLI%']:.0f}% + Desktop {_row['Desktop%']:.0f}% = {_row['CLI%']+_row['Desktop%']:.0f}%")
        elif _row["UI%"] >= 70:
            _insights.append(f"🌐 UI-heavy ({_row['UI%']:.0f}%) — exploratory usage, not yet embedded in developer workflows")
        if pd.notna(_row.get("7D Credits WoW%")) and float(_row["7D Credits WoW%"]) > 15:
            _insights.append(f"⚡ Credit consumption surging — **+{float(_row['7D Credits WoW%']):.0f}% WoW**, accounts expanding usage")
        elif pd.notna(_row.get("7D Credits WoW%")) and float(_row["7D Credits WoW%"]) < -15:
            _insights.append(f"📉 Credit consumption declining **{float(_row['7D Credits WoW%']):.0f}% WoW** — check for account churn")
        if int(_row["Deployed CoCo"]) == 0:
            _insights.append(f"🚧 No deployed CoCo use cases — pipeline not converting; focus on Stage 5-6 acceleration")
        for ins in _insights:
            st.markdown(ins)

        # AI narrative (Cortex)
        st.markdown("---")
        st.markdown("**AI Narrative**")
        if st.button("Generate AI Insight", key=f"ai_insight_{_sel}"):
            _profile = f"""
Partner: {_sel}
Health Score: {_score}/100 (Band: {_band_label}, Trajectory: {_traj_label})
CoCo Adoption: {_row['CoCo%']:.1f}% (Target: {TARGET}%, WoW: {f"{float(_row['WoW CoCo%']):+.1f}%" if pd.notna(_row.get('WoW CoCo%')) else 'N/A'})
4-week trend slope: {f"{float(_row['Weekly Δ%']):+.1f}%/week" if pd.notna(_row.get('Weekly Δ%')) else 'N/A'}
Q2 Credits: {f"${float(_row['Q2 Credits']):,.0f}" if pd.notna(_row.get('Q2 Credits')) else 'N/A'} (WoW: {f"{float(_row['7D Credits WoW%']):+.1f}%" if pd.notna(_row.get('7D Credits WoW%')) else 'N/A'})
Surface Mix: CLI {_row['CLI%']:.0f}% / Desktop {_row['Desktop%']:.0f}% / UI {_row['UI%']:.0f}%
Agent Requests: {int(_row['Agent Requests'])} coding, {int(_row['Reasoning Agent'])} reasoning
Deployed CoCo UCs: {int(_row['Deployed CoCo'])}
Accounts with Usage: {int(_row['Accts w/ Usage'])}
Dimension Scores: Adoption {int(_row['Adoption'])}/30, Usage Depth {int(_row['Usage Depth'])}/25, Velocity {int(_row['Velocity'])}/20 (FY Speed {int(_row['FY Speed'])}/10 + Deploy Rate {int(_row['Deploy Rate'])}/10), Pipeline Value {int(_row['Pipeline Value'])}/15, Engagement {int(_row['Engagement'])}/10
"""
            _prompt = f"""You are a senior Snowflake Partner Sales Executive analyzing a partner's CoCo (Cortex Code) adoption health.

PARTNER PROFILE:
{_profile}

Write a 3-sentence executive insight covering:
1. Current health status and primary driver (what is making them strong or weak)
2. Trend direction and what it signals for Q2 target attainment
3. One specific, actionable recommendation for the PSE or SE to improve health score

Be direct, data-driven, and use specific numbers. Do not use generic language."""
            with st.spinner("Generating insight…"):
                try:
                    _narrative = cortex_complete(conn, "claude-sonnet-4-5", _prompt)
                    st.info(_narrative)
                except Exception as _e:
                    st.error(f"Cortex unavailable: {_e}")

# ── Partner Comparison — Overlaid Radar ───────────────────────────────────────
st.divider()
st.subheader("Partner Comparison — Radar Chart")
st.caption("Select up to 6 partners to overlay their dimension profiles on a single radar chart.")

_RADAR_DIMS  = ["Adoption", "Usage Depth", "Velocity", "Pipeline Value", "Engagement"]
_RADAR_MAXES = [30, 25, 20, 15, 10]
_RADAR_PALETTE = [
    "#29B5E8","#E8671A","#27ae60","#8e44ad","#e74c3c","#f39c12",
]

_compare_partners = st.multiselect(
    "Select partners to compare",
    options=scored["PARTNER_NAME"].tolist(),
    default=scored["PARTNER_NAME"].tolist()[:3],
    max_selections=6,
    key="health_compare_select",
)

if len(_compare_partners) >= 2:
    _compare_col1, _compare_col2 = st.columns([1.2, 1])

    with _compare_col1:
        _fig_compare = go.Figure()
        for i, pname in enumerate(_compare_partners):
            _crow = scored[scored["PARTNER_NAME"] == pname]
            if len(_crow) == 0:
                continue
            _crow = _crow.iloc[0]
            _color = _RADAR_PALETTE[i % len(_RADAR_PALETTE)]
            _vals  = [int(_crow.get(d, 0) or 0) for d in _RADAR_DIMS]
            _pcts  = [v / m * 100 for v, m in zip(_vals, _RADAR_MAXES)]
            _rgb   = f"{int(_color[1:3],16)},{int(_color[3:5],16)},{int(_color[5:7],16)}"
            _fig_compare.add_trace(go.Scatterpolar(
                r=_pcts + [_pcts[0]],
                theta=_RADAR_DIMS + [_RADAR_DIMS[0]],
                fill="toself",
                fillcolor=f"rgba({_rgb},0.12)",
                line=dict(color=_color, width=2),
                name=f"{pname} ({int(_crow['HEALTH_SCORE'])})",
                hovertemplate=f"<b>{pname}</b><br>%{{theta}}: %{{r:.0f}}%<extra></extra>",
            ))
        _fig_compare.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%", tickfont=dict(size=9)),
                angularaxis=dict(tickfont=dict(size=12)),
            ),
            legend=dict(orientation="v", x=1.05, y=1, font=dict(size=11)),
            height=420,
            margin=dict(t=30, b=30, l=50, r=160),
            title=dict(text="Dimension Profile Comparison (% of max per dimension)", x=0.45, font=dict(size=13)),
        )
        st.plotly_chart(_fig_compare, use_container_width=True)

    with _compare_col2:
        st.markdown("**Dimension Scores**")
        _cmp_rows = []
        for pname in _compare_partners:
            _crow = scored[scored["PARTNER_NAME"] == pname]
            if len(_crow) == 0:
                continue
            _crow = _crow.iloc[0]
            _cmp_rows.append({
                "Partner":        pname,
                "Score":          int(_crow["HEALTH_SCORE"]),
                "Band":           _crow["BAND"],
                "Trend":          _crow["Trajectory"],
                "Adoption":       f"{int(_crow.get('Adoption',0))}/30",
                "Usage Depth":    f"{int(_crow.get('Usage Depth',0))}/25",
                "Velocity":       f"{int(_crow.get('Velocity',0))}/20",
                "Pipeline Value": f"{int(_crow.get('Pipeline Value',0))}/15",
                "Engagement":     f"{int(_crow.get('Engagement',0))}/10",
            })
        _cmp_df = pd.DataFrame(_cmp_rows)

        def _score_cell(val):
            try:
                v = float(str(val).split("/")[0])
                m = float(str(val).split("/")[1])
                pct = v / m * 100
                return "background-color:#d4edda;color:#155724" if pct >= 70 else (
                    "background-color:#fff3cd;color:#856404" if pct >= 40 else
                    "background-color:#f8d7da;color:#721c24"
                )
            except Exception:
                return ""

        def _overall_style(val):
            try:
                v = float(val)
                if v >= 75: return "background-color:#d4edda;color:#155724;font-weight:bold"
                if v >= 50: return "background-color:#cce5ff;color:#004085;font-weight:bold"
                if v >= 30: return "background-color:#fff3cd;color:#856404;font-weight:bold"
                return "background-color:#f8d7da;color:#721c24;font-weight:bold"
            except Exception: return ""

        def _traj_cell(val):
            if "Improving" in str(val): return "color:#27ae60;font-weight:bold"
            if "Declining" in str(val): return "color:#e74c3c;font-weight:bold"
            return "color:#888"

        _dim_score_cols = ["Adoption","Usage Depth","Velocity","Pipeline Value","Engagement"]
        _styled_cmp = (
            _cmp_df.style
            .map(_overall_style, subset=["Score"])
            .map(_traj_cell,     subset=["Trend"])
            .map(_score_cell,    subset=_dim_score_cols)
        )
        st.dataframe(
            _styled_cmp,
            column_config={
                "Partner":        st.column_config.TextColumn("Partner",   width="medium"),
                "Score":          st.column_config.NumberColumn("Score",   format="%d", width=65),
                "Band":           st.column_config.TextColumn("Band",      width=85),
                "Trend":          st.column_config.TextColumn("Trend",     width=100),
                "Adoption":       st.column_config.TextColumn("Adoption",  width=80),
                "Usage Depth":    st.column_config.TextColumn("Usage",     width=70),
                "Velocity":       st.column_config.TextColumn("Velocity",  width=75),
                "Pipeline Value": st.column_config.TextColumn("Pipeline",  width=72),
                "Engagement":     st.column_config.TextColumn("Engage",    width=70),
            },
            hide_index=True, use_container_width=True,
        )
        # Highlight strongest and weakest dimension per selected partner
        st.markdown("**Strengths & Gaps**")
        for pname in _compare_partners:
            _crow = scored[scored["PARTNER_NAME"] == pname]
            if len(_crow) == 0: continue
            _crow = _crow.iloc[0]
            _dim_pcts = {d: (int(_crow.get(d, 0) or 0) / m * 100) for d, m in zip(_RADAR_DIMS, _RADAR_MAXES)}
            _best = max(_dim_pcts, key=_dim_pcts.get)
            _worst = min(_dim_pcts, key=_dim_pcts.get)
            st.markdown(
                f"**{pname}** — ✅ {_best} ({_dim_pcts[_best]:.0f}%)  ·  "
                f"⚠️ {_worst} ({_dim_pcts[_worst]:.0f}%)"
            )
elif len(_compare_partners) == 1:
    st.info("Select at least 2 partners to compare.")
else:
    st.info("Select partners above to compare their radar profiles.")

st.divider()
st.subheader("Full Partner Scorecard")
st.caption("Adoption 30 · Usage Depth 25 · Velocity 20 (FY Speed 10 + Deploy Rate 10) · Pipeline Value 15 · Engagement 10. "
           "Trajectory = 4-week direction. Weeks to Target = projection at current weekly slope.")

_tbl = scored[["PARTNER_NAME","HEALTH_SCORE","BAND","Trajectory","Weekly Δ%","Weeks to Target"] + _DIM_COLS + _META_COLS].copy()

def _wow_style(val):
    try:
        v = float(val)
        return "background-color:#d4edda;color:#155724" if v > 0 else ("background-color:#f8d7da;color:#721c24" if v < 0 else "")
    except Exception: return ""

def _score_style(val):
    try:
        v = float(val)
        if v >= 75: return "background-color:#d4edda;color:#155724;font-weight:bold"
        if v >= 50: return "background-color:#cce5ff;color:#004085;font-weight:bold"
        if v >= 30: return "background-color:#fff3cd;color:#856404;font-weight:bold"
        return "background-color:#f8d7da;color:#721c24;font-weight:bold"
    except Exception: return ""

def _traj_style(val):
    if "Improving" in str(val): return "color:#27ae60;font-weight:bold"
    if "Declining" in str(val): return "color:#e74c3c;font-weight:bold"
    return "color:#888"

_styled_tbl = (
    _tbl.style
    .map(_score_style, subset=["HEALTH_SCORE"])
    .map(_wow_style,   subset=["WoW CoCo%","7D Credits WoW%","Weekly Δ%"])
    .map(_traj_style,  subset=["Trajectory"])
)

_col_cfg = {
    "PARTNER_NAME":    st.column_config.TextColumn("Partner",       width="medium"),
    "HEALTH_SCORE":    st.column_config.NumberColumn("Score",        format="%d",      width=70),
    "BAND":            st.column_config.TextColumn("Band",          width=85),
    "Trajectory":      st.column_config.TextColumn("Trend",         width=110,   help="4-week direction based on CoCo% slope"),
    "Weekly Δ%":       st.column_config.NumberColumn("Wk Δ%",        format="%+.1f%%", width=75,  help="Avg weekly CoCo% change over last 4 weeks"),
    "Weeks to Target": st.column_config.NumberColumn("Wks to 75%",   format="%d",      width=90,  help="Projected weeks to hit 50% at current trajectory (blank if at/above target or declining)"),
    "Adoption":        st.column_config.NumberColumn("Adoption",     format="%d /30",  width=90),
    "Usage Depth":     st.column_config.NumberColumn("Usage Depth",  format="%d /25",  width=100),
    "FY Speed":     st.column_config.NumberColumn("FY Speed",    format="%d /10", width=85,  help="FY26→FY27 improvement: how much faster partners deploy vs prior year (0=slower/no data, 10=7+ days faster)"),
    "Deploy Rate": st.column_config.NumberColumn("Deploy Rate", format="%d /10", width=95,  help="% of CoCo UCs that reached Stage 7 (Deployed): 0=none deployed, 10=all deployed"),
    "Pipeline Value":  st.column_config.NumberColumn("Pipeline Val", format="%d /15",  width=100),
    "Engagement":      st.column_config.NumberColumn("Engagement",   format="%d /10",  width=90),
    "CoCo%":           st.column_config.ProgressColumn("CoCo%",      min_value=0, max_value=100, format="%.1f%%"),
    "WoW CoCo%":       st.column_config.NumberColumn("WoW CoCo%",    format="%+.1f%%", width=95),
    "7D Credits WoW%":    st.column_config.NumberColumn("7D Credits WoW%", format="%+.1f%%", width=100),
    "Q2 Credits":      st.column_config.NumberColumn("Q2 Credits",   format="$%.0f",   width=100),
    "Last 7d Credits": st.column_config.NumberColumn("Last 7d Cred", format="$%.0f",   width=100),
    "Accts w/ Usage":  st.column_config.NumberColumn("Accts",        format="%d",      width=65),
    "Deployed CoCo":   st.column_config.NumberColumn("Deployed",     format="%d",      width=75),
    "CoCo EACV":       st.column_config.NumberColumn("CoCo EACV",    format="$%.0f",   width=95),
    "CLI%":            st.column_config.NumberColumn("CLI%",         format="%.0f%%",  width=60),
    "Desktop%":        st.column_config.NumberColumn("Desktop%",     format="%.0f%%",  width=75),
    "UI%":             st.column_config.NumberColumn("UI%",          format="%.0f%%",  width=55),
    "Agent Requests":  st.column_config.NumberColumn("Agent",        format="%d",      width=70),
    "Reasoning Agent": st.column_config.NumberColumn("Reasoning",    format="%d",      width=85),
}

st.dataframe(_styled_tbl, column_config=_col_cfg, hide_index=True,
             use_container_width=True, height=38 + 35 * len(scored))

# ── Partner Drill-Down ────────────────────────────────────────────────────────
st.divider()
st.subheader("Partner Health Leaderboard")
_ldf = scored.sort_values("HEALTH_SCORE")
_fig_lb = go.Figure(go.Bar(
    x=_ldf["HEALTH_SCORE"], y=_ldf["PARTNER_NAME"], orientation="h",
    marker_color=_ldf["COLOR"].tolist(),
    text=_ldf["HEALTH_SCORE"].astype(str) + " — " + _ldf["BAND"] + "  " + _ldf["Trajectory"],
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>Score: %{x}<extra></extra>",
))
_fig_lb.add_vline(x=75, line_dash="dot", line_color="#27ae60", annotation_text="Healthy")
_fig_lb.add_vline(x=50, line_dash="dot", line_color="#2980b9", annotation_text="On Track")
_fig_lb.add_vline(x=30, line_dash="dot", line_color="#e67e22", annotation_text="At Risk")
_fig_lb.update_layout(
    xaxis=dict(range=[0, 115], title="Health Score"),
    yaxis=dict(title=""),
    height=max(400, len(scored) * 28 + 80),
    margin=dict(l=10, r=150, t=20, b=40),
    showlegend=False,
)
st.plotly_chart(_fig_lb, use_container_width=True)

# ── Scorecard Table ───────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Health Score = Adoption (30) + Usage Depth (25) + Velocity (20) + Pipeline Value (15) + Engagement (10). "
    "Bands: Healthy ≥75 · On Track 50–74 · At Risk 30–49 · Lagging <30. "
    "Trend = 4-week CoCo% slope from IS_COCO_FINAL_WEEKLY_SNAPSHOT."
)
