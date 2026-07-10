import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from utils.queries import get_okr_partner_summary, get_okr_coco_adoption, get_partner_credit_consumption, get_usecase_confidence_scores, get_bulk_confidence_scores, get_account_coco_credits
from utils.ask_ai import build_filter_context
from utils import resolve_partner_filter, resolve_region_theaters, PARTNER_RENAME_MAP

conn = st.session_state.conn
region = st.session_state.get("selected_region", "Global")
selected_partners = st.session_state.get("selected_partners", [])
start_date = st.session_state.get("okr_start_date", date(2026, 5, 1))
end_date = st.session_state.get("okr_end_date", date(2026, 7, 31))
include_account_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter = st.session_state.get("confidence_filter", ["High"])
confidence = 'High' if confidence_filter == ['High'] else ('Medium' if confidence_filter else None)

st.title(":material/check_circle: OKR: CoCo Adoption per Partner")
st.caption(f"Track 50% CoCo attachment target for partner use cases (Stages 3-7) | Region: {region} | {start_date} to {end_date}")

TARGET_PCT = 50

f1, f2 = st.columns([1, 1])
with f1:
    target = st.number_input("Target %", min_value=10, max_value=100, value=TARGET_PCT, step=5, key="okr_target")
with f2:
    min_use_cases = st.number_input("Min Use Cases", min_value=1, max_value=20, value=2, step=1, key="okr_min_uc")

q_start = str(start_date)
q_end = str(end_date)

# Get base summary for partner list and totals
base_summary = get_okr_partner_summary(conn, q_start, q_end, region=region, include_account_coco=False, confidence=None)
credit_data = get_partner_credit_consumption(conn, base_summary['PARTNER_NAME'].tolist(), q_start)

if len(base_summary) == 0:
    st.info("No use cases found for the selected date range.")
    st.stop()

# Apply sidebar partner filter
if selected_partners:
    partner_names = resolve_partner_filter(selected_partners)
    base_summary = base_summary[base_summary['PARTNER_NAME'].isin(partner_names)]
    if len(base_summary) == 0:
        st.info(f"No data for selected partners.")
        st.stop()

# Compute CoCo using full confidence scoring when account-level is enabled
if include_account_coco:
    bulk_conf = get_bulk_confidence_scores(conn, base_summary['PARTNER_NAME'].tolist(), q_start, q_end)
    if len(bulk_conf) > 0:
        # Apply region filter in Python (bulk_conf includes THEATER_NAME via uc.*)
        if region and region != 'Global':
            _theaters = resolve_region_theaters(region)
            if _theaters is not None:
                bulk_conf = bulk_conf[bulk_conf['THEATER_NAME'].isin(_theaters)]

        # Merge partner aliases (IBM Consulting→IBM, EY aliases, etc.) before groupby
        bulk_conf['PARTNER_NAME'] = bulk_conf['PARTNER_NAME'].replace(PARTNER_RENAME_MAP)
        bands = confidence_filter if confidence_filter else ['High', 'Medium', 'Low']
        bulk_conf['IS_COCO_FINAL'] = (
            (bulk_conf['IS_COCO'] == True) |
            (bulk_conf['CONFIDENCE_BAND'].isin(bands))
        )

        # Recompute per-partner summary
        coco_eacv = bulk_conf[bulk_conf['IS_COCO_FINAL']].groupby('PARTNER_NAME')['USE_CASE_EACV'].sum().reset_index()
        coco_eacv.columns = ['PARTNER_NAME', 'COCO_EACV']
        summary = bulk_conf.groupby('PARTNER_NAME').agg(
            TOTAL_USE_CASES=('USE_CASE_ID', 'count'),
            COCO_USE_CASES=('IS_COCO_FINAL', 'sum'),
            TOTAL_EACV=('USE_CASE_EACV', 'sum'),
        ).reset_index()
        summary = summary.merge(coco_eacv, on='PARTNER_NAME', how='left')
        summary['COCO_EACV'] = summary['COCO_EACV'].fillna(0)
        summary['NON_COCO_USE_CASES'] = summary['TOTAL_USE_CASES'] - summary['COCO_USE_CASES']
        summary['COCO_PCT'] = round(summary['COCO_USE_CASES'] * 100.0 / summary['TOTAL_USE_CASES'].replace(0, float('nan')), 1).fillna(0)
        # Count account-level use cases at the selected confidence bands
        high_conf_coco = int(bulk_conf['CONFIDENCE_BAND'].isin(bands).sum())
    else:
        # Rename aliases in base_summary and re-aggregate so merged partners show as one row
        base_summary = base_summary.copy()
        base_summary['PARTNER_NAME'] = base_summary['PARTNER_NAME'].replace(PARTNER_RENAME_MAP)
        if base_summary['PARTNER_NAME'].duplicated().any():
            _agg = base_summary.groupby('PARTNER_NAME').agg(
                total_use_cases=('total_use_cases', 'sum'),
                coco_use_cases=('coco_use_cases', 'sum'),
                total_eacv=('total_eacv', 'sum'),
                coco_eacv=('coco_eacv', 'sum'),
            ).reset_index()
            _agg['non_coco_use_cases'] = _agg['total_use_cases'] - _agg['coco_use_cases']
            _agg['coco_pct'] = round(_agg['coco_use_cases'] * 100.0 / _agg['total_use_cases'].replace(0, float('nan')), 1).fillna(0)
            _agg['MEETS_TARGET'] = _agg['coco_pct'] >= 50
            base_summary = _agg
        summary = base_summary
        bulk_conf = pd.DataFrame()
        high_conf_coco = 0
else:
    summary = base_summary
    bulk_conf = pd.DataFrame()
    high_conf_coco = 0

summary['MEETS_TARGET'] = summary['COCO_PCT'] >= target
filtered = summary[summary['TOTAL_USE_CASES'] >= min_use_cases].copy()

st.divider()

total_partners = len(filtered)
meeting_target = filtered['MEETS_TARGET'].sum()
not_meeting = total_partners - meeting_target
overall_coco = filtered['COCO_USE_CASES'].sum()
overall_total = filtered['TOTAL_USE_CASES'].sum()
overall_pct = round(overall_coco * 100.0 / overall_total, 1) if overall_total > 0 else 0
high_conf_pct = round(high_conf_coco * 100.0 / overall_total, 1) if overall_total > 0 else 0

# Inject context for Ask AI
import streamlit as _st_ctx
_top_partners = filtered.sort_values('COCO_PCT', ascending=False).head(5)
_top_str = "; ".join(f"{r.PARTNER_NAME} {r.COCO_PCT:.1f}%" for _, r in _top_partners.iterrows())
_bot_partners = filtered[~filtered['MEETS_TARGET']].sort_values('COCO_PCT', ascending=False).head(5)
_bot_str = "; ".join(f"{r.PARTNER_NAME} {r.COCO_PCT:.1f}%" for _, r in _bot_partners.iterrows())
_st_ctx.session_state.ask_ai_context = (
    f"Current page: OKR CoCo Adoption. Region: {region}. Period: {start_date} to {end_date}.\n"
    f"Partners tracked: {total_partners}. Meeting {target}% target: {int(meeting_target)}. Below target: {int(not_meeting)}.\n"
    f"Overall CoCo%: {overall_pct}% ({int(overall_coco)}/{int(overall_total)} UCs).\n"
    f"Top partners by CoCo%: {_top_str}.\n"
    f"Partners below target (closest first): {_bot_str}."
    + build_filter_context()
)

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Partners Tracked", total_partners)
c2.metric(f"Meeting {target}%", int(meeting_target), f"{round(meeting_target*100/total_partners)}%" if total_partners else "0%")
c3.metric(f"Below {target}%", int(not_meeting), delta_color="inverse")
conf_desc = 'High' if confidence_filter == ['High'] else 'High + Medium' if confidence_filter else 'All account-level'
c4.metric("Overall CoCo %", f"{overall_pct}%", f"{int(overall_coco)}/{int(overall_total)} UCs",
    help=f"SE/PSE/Flag always + Account Level at {conf_desc} confidence (full scoring)")
c5.metric(f"Account Level CoCo ({conf_desc})", f"{high_conf_pct}%", f"{high_conf_coco}/{int(overall_total)} UCs",
    help=f"Use cases where account confidence band is {conf_desc} (S1+S2+S3+S4 scoring)")
c6.metric("Total EACV", f"${filtered['TOTAL_EACV'].sum()/1_000_000:.1f}M")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("CoCo Adoption Distribution")
    st.caption("Each bar = number of partners at that CoCo adoption level. Red line = 50% target.")
    
    # Color bars based on target
    colors = ['#2ecc71' if x >= target else '#e74c3c' for x in filtered['COCO_PCT']]
    
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=filtered['COCO_PCT'], nbinsx=10,
        marker_color='#3498db', 
        name='Partners',
        hovertemplate='CoCo %: %{x:.0f}%<br>Partners: %{y}<extra></extra>'
    ))
    fig.add_vline(x=target, line_dash="dash", line_color="red", 
                  annotation_text=f"OKR Target: {target}%",
                  annotation_position="top right",
                  annotation_font_size=12,
                  annotation_font_color="red")
    fig.update_layout(
        height=350, 
        xaxis_title="Partner CoCo Adoption Rate (%)", 
        yaxis_title="Number of Partners",
        xaxis=dict(range=[0, 105], dtick=10, ticksuffix='%'),
        showlegend=False,
        bargap=0.1
    )
    fig.add_annotation(
        x=25, y=0.9, xref='x', yref='paper',
        text="Below Target", showarrow=False,
        font=dict(size=11, color='#e74c3c')
    )
    fig.add_annotation(
        x=75, y=0.9, xref='x', yref='paper',
        text="Meeting Target", showarrow=False,
        font=dict(size=11, color='#2ecc71')
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Target Achievement")
    fig = go.Figure(data=[
        go.Pie(
            labels=[f"Meeting {target}%", f"Below {target}%"],
            values=[int(meeting_target), int(not_meeting)],
            marker_colors=['#2ecc71', '#e74c3c'],
            hole=0.5
        )
    ])
    fig.update_layout(height=350)
    fig.add_annotation(
        text=f"{round(meeting_target*100/total_partners)}%", x=0.5, y=0.5,
        font_size=28, showarrow=False
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Partner Scorecard")

filtered_sorted = filtered.sort_values('COCO_PCT', ascending=False)

display_df = filtered_sorted[['PARTNER_NAME', 'TOTAL_USE_CASES', 'COCO_USE_CASES', 'NON_COCO_USE_CASES', 'TOTAL_EACV', 'COCO_EACV', 'MEETS_TARGET']].copy()
display_df['TOTAL_EACV'] = display_df['TOTAL_EACV'].apply(lambda x: f"${(x or 0)/1000:.0f}K" if (x or 0) < 1_000_000 else f"${(x or 0)/1_000_000:.1f}M")
display_df['COCO_EACV'] = display_df['COCO_EACV'].apply(lambda x: f"${(x or 0)/1000:.0f}K" if (x or 0) < 1_000_000 else f"${(x or 0)/1_000_000:.1f}M")
display_df['GAP'] = filtered_sorted.apply(
    lambda r: max(0, int((target / 100.0 * r['TOTAL_USE_CASES']) - r['COCO_USE_CASES'] + 0.999)), axis=1
)

st.dataframe(
    display_df,
    use_container_width=True,
    height=500,
    column_config={
        "PARTNER_NAME": st.column_config.TextColumn("Partner", width="medium"),
        "TOTAL_USE_CASES": st.column_config.NumberColumn("Total UCs", format="%d"),
        "COCO_USE_CASES": st.column_config.NumberColumn("CoCo UCs", format="%d"),
        "NON_COCO_USE_CASES": st.column_config.NumberColumn("Non-CoCo", format="%d"),
        "TOTAL_EACV": st.column_config.TextColumn("Total EACV"),
        "COCO_EACV": st.column_config.TextColumn("CoCo EACV"),
        "MEETS_TARGET": st.column_config.CheckboxColumn(f">={target}%"),
        "GAP": st.column_config.NumberColumn("UCs to Target", help="Additional CoCo UCs needed to reach target"),
    },
    hide_index=True
)

st.divider()

st.subheader("Partner Deep Dive")
partner_list = filtered_sorted['PARTNER_NAME'].tolist()
selected_partner = st.selectbox("Select Partner", partner_list, key="okr_partner_select")

if selected_partner:
    detail = get_okr_coco_adoption(conn, q_start, q_end, region=region, include_account_coco=include_account_coco, confidence=confidence)
    partner_detail = detail[detail['PARTNER_NAME'] == selected_partner]

    if len(partner_detail) > 0:
        # Override IS_COCO_ATTACHED using full confidence scoring (same as summary metrics)
        if include_account_coco:
            conf_scores = get_usecase_confidence_scores(conn, selected_partner, q_start, q_end)
            if len(conf_scores) > 0:
                partner_detail = partner_detail.copy()
                conf_map = conf_scores[['USE_CASE_ID', 'CONFIDENCE_BAND']].set_index('USE_CASE_ID')
                partner_detail['CONFIDENCE_BAND'] = partner_detail['USE_CASE_ID'].map(conf_map['CONFIDENCE_BAND'])
                bands = confidence_filter if confidence_filter else ['High', 'Medium', 'Low']
                is_flag = partner_detail['COCO_SOURCE'].notna()
                has_conf = partner_detail['CONFIDENCE_BAND'].isin(bands)
                partner_detail['IS_COCO_ATTACHED'] = is_flag | has_conf

                def _rebuild_flags(row):
                    parts = []
                    band = row.get('CONFIDENCE_BAND')
                    if pd.notna(band) and band in bands:
                        parts.append(f"Account ({band})")
                    if row['COCO_SOURCE'] == 'SE_COMMENTS':
                        parts.append('SE Comments')
                    elif row['COCO_SOURCE'] == 'PARTNER_COMMENTS':
                        parts.append('PSE Comments')
                    elif row['COCO_SOURCE'] == 'FEATURE_FLAG':
                        parts.append('Feature Flag')
                    return ' | '.join(parts)
                partner_detail['ATTRIBUTION_FLAGS'] = partner_detail.apply(_rebuild_flags, axis=1)

        p_stats = filtered_sorted[filtered_sorted['PARTNER_NAME'] == selected_partner].iloc[0]
        coco_pct = p_stats['COCO_PCT']

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Use Cases", int(p_stats['TOTAL_USE_CASES']))
        c2.metric("CoCo Attached", int(p_stats['COCO_USE_CASES']))
        c3.metric("CoCo %", f"{coco_pct:.1f}%", f"{'MET' if coco_pct >= target else 'BELOW'} {target}% target")
        gap = max(0, int((target / 100.0 * p_stats['TOTAL_USE_CASES']) - p_stats['COCO_USE_CASES'] + 0.999))
        c4.metric("UCs Needed for Target", gap if gap > 0 else "0 (Met!)")
        # Account-only: CoCo attached but no comments/flag (COCO_SOURCE is NULL)
        account_only = int(partner_detail[(partner_detail['IS_COCO_ATTACHED'] == True) & (partner_detail['COCO_SOURCE'].isna())].shape[0])
        c5.metric("CoCo Attribution- Account Level Usage", account_only, help="CoCo via customer account usage, no SE/PSE comments")

        # Credit consumption for selected partner
        partner_credits = credit_data[credit_data['PARTNER_NAME'] == selected_partner] if len(credit_data) > 0 else pd.DataFrame()
        if len(partner_credits) > 0:
            pc = partner_credits.iloc[0]
            cr1, cr2 = st.columns(2)
            cr1.metric("Q2 Total Credits", f"${pc['Q2_TOTAL_CREDITS']:,.0f}" if pd.notna(pc['Q2_TOTAL_CREDITS']) else "N/A")
            cr2.metric("WoW", f"{pc['WOW_PCT']:+.1f}%" if pd.notna(pc['WOW_PCT']) else "N/A")

        coco_ucs = partner_detail[partner_detail['IS_COCO_ATTACHED'] == True]
        non_coco_ucs = partner_detail[partner_detail['IS_COCO_ATTACHED'] == False]

        tab_coco, tab_noncoco, tab_confidence = st.tabs([
            f"CoCo Attached ({len(coco_ucs)})",
            f"Non-CoCo ({len(non_coco_ucs)}) - Opportunities",
            "Confidence Scoring"
        ])

        uc_cols = ['USE_CASE_NAME', 'ACCOUNT_NAME', 'THEATER_NAME', 'USE_CASE_STAGE', 'USE_CASE_EACV', 'TECHNICAL_USE_CASE', 'ATTRIBUTION_FLAGS']
        uc_config = {
            "USE_CASE_NAME": st.column_config.TextColumn("Use Case", width=200),
            "ACCOUNT_NAME": st.column_config.TextColumn("Account", width=160),
            "THEATER_NAME": st.column_config.TextColumn("Theater", width=80),
            "USE_CASE_STAGE": st.column_config.TextColumn("Stage", width=50),
            "USE_CASE_EACV": st.column_config.NumberColumn("EACV", format="$%.0f", width=90),
            "TECHNICAL_USE_CASE": st.column_config.TextColumn("Technical Type", width=150),
            "ATTRIBUTION_FLAGS": st.column_config.TextColumn("CoCo Source", width=140),
        }

        with tab_coco:
            if len(coco_ucs) > 0:
                # Fetch account-level CoCo credit consumption (Option 1: CORTEX_CODE_USER_DAY_FACT)
                _acct_list = tuple(coco_ucs['ACCOUNT_NAME'].str.upper().unique())
                _credits = get_account_coco_credits(conn, _acct_list, str(q_start))

                coco_display = coco_ucs[uc_cols].copy()
                coco_display['USE_CASE_STAGE'] = coco_display['USE_CASE_STAGE'].str.extract(r'^(\d+)').iloc[:, 0]

                if len(_credits) > 0:
                    _credits_map = _credits.set_index('ACCOUNT_NAME_UPPER')[['Q2_CREDITS', 'Q2_TOKENS', 'ACTIVE_DAYS', 'LAST_ACTIVE', 'WOW_CREDITS_PCT']]
                    coco_display['Q2_CREDITS'] = coco_display['ACCOUNT_NAME'].str.upper().map(_credits_map['Q2_CREDITS'])
                    coco_display['Q2_TOKENS'] = coco_display['ACCOUNT_NAME'].str.upper().map(_credits_map['Q2_TOKENS'])
                    coco_display['ACTIVE_DAYS'] = coco_display['ACCOUNT_NAME'].str.upper().map(_credits_map['ACTIVE_DAYS'])
                    coco_display['LAST_ACTIVE'] = coco_display['ACCOUNT_NAME'].str.upper().map(_credits_map['LAST_ACTIVE'])
                    coco_display['WOW_CREDITS_PCT'] = coco_display['ACCOUNT_NAME'].str.upper().map(_credits_map['WOW_CREDITS_PCT'])
                    coco_uc_config = {
                        **uc_config,
                        'Q2_CREDITS': st.column_config.NumberColumn("CoCo Q2 Credits", format="$%.0f", width=110, help="Account-level CoCo token credits since Q2 start"),
                        'Q2_TOKENS': st.column_config.NumberColumn("Q2 Tokens", format="%d", width=100, help="Total tokens consumed (input + output + cache) since Q2 start"),
                        'WOW_CREDITS_PCT': st.column_config.NumberColumn("WoW %", format="%+.1f%%", width=80, help="Week-over-week % change in CoCo credit spend (last 7 days vs prior 7 days)"),
                        'ACTIVE_DAYS': st.column_config.NumberColumn("Active Days", format="%d", width=90, help="Days with CoCo activity at this account since Q2 start"),
                        'LAST_ACTIVE': st.column_config.DateColumn("Last Active", width=100, help="Last day CoCo was used at this account"),
                    }
                    # Explicit column order: WOW_CREDITS_PCT after Q2_TOKENS
                    _ordered_cols = [c for c in uc_cols] + ['Q2_CREDITS', 'Q2_TOKENS', 'WOW_CREDITS_PCT', 'ACTIVE_DAYS', 'LAST_ACTIVE']
                    _ordered_cols = [c for c in _ordered_cols if c in coco_display.columns]
                    st.dataframe(coco_display[_ordered_cols], hide_index=True, use_container_width=True, column_config=coco_uc_config)
                    st.caption("Q2 Credits and Active Days are account-level signals shared across all UCs at the same account.")
                else:
                    st.dataframe(coco_display, hide_index=True, use_container_width=True, column_config=uc_config)
            else:
                st.info("No CoCo-attached use cases.")

        with tab_noncoco:
            if len(non_coco_ucs) > 0:
                st.warning(f"These {len(non_coco_ucs)} use cases do NOT have CoCo attached. Adding CoCo to these would help reach the {target}% target.")
                noncoco_display = non_coco_ucs[uc_cols].copy()
                noncoco_display['USE_CASE_STAGE'] = noncoco_display['USE_CASE_STAGE'].str.extract(r'^(\d+)').iloc[:, 0]
                st.dataframe(noncoco_display, hide_index=True, use_container_width=True, column_config=uc_config)
            else:
                st.success("All use cases have CoCo attached!")

        with tab_confidence:
            confidence_data = get_usecase_confidence_scores(conn, selected_partner, q_start, q_end)
            if len(confidence_data) > 0:
                # Summary metrics (always show ALL bands regardless of sidebar filter)
                high = int((confidence_data['CONFIDENCE_BAND'] == 'High').sum())
                medium = int((confidence_data['CONFIDENCE_BAND'] == 'Medium').sum())
                low = int((confidence_data['CONFIDENCE_BAND'] == 'Low').sum())
                no_signal = int((confidence_data['CONFIDENCE_BAND'] == 'No Signal').sum())
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("High", high, help="Score 75-100")
                m2.metric("Medium", medium, help="Score 40-74")
                m3.metric("Low", low, help="Score 1-39")
                m4.metric("No Signal", no_signal, help="Score 0")

                _base_conf_cols = ['ACCOUNT_NAME', 'THEATER_NAME', 'TECHNICAL_USE_CASE', 'WORKLOAD_CATEGORY', 'RELEVANT_SKILL_INVOCATIONS', 'RELEVANT_CUSTOM_SKILLS', 'TOOLS_INVOKED', 'ACTIVE_DAYS', 'DISTINCT_USERS', 'TOTAL_SCORE', 'CONFIDENCE_BAND']
                conf_cols = (['USE_CASE_NAME'] if 'USE_CASE_NAME' in confidence_data.columns else []) + _base_conf_cols
                st.dataframe(
                    confidence_data[conf_cols],
                    column_config={
                        'USE_CASE_NAME': st.column_config.TextColumn("Use Case", width="large"),
                        'ACCOUNT_NAME': st.column_config.TextColumn("Account", width="medium"),
                        'THEATER_NAME': st.column_config.TextColumn("Theater", width="small"),
                        'TECHNICAL_USE_CASE': st.column_config.TextColumn("Technical Type", width="medium"),
                        'WORKLOAD_CATEGORY': st.column_config.TextColumn("Workload", width="small"),
                        'RELEVANT_SKILL_INVOCATIONS': st.column_config.NumberColumn("Bundled Skills", format="%d", help="Relevant bundled skill invocations for this workload"),
                        'RELEVANT_CUSTOM_SKILLS': st.column_config.NumberColumn("Custom Skills", format="%d", help="Workload-relevant custom skills (keyword matched)"),
                        'TOOLS_INVOKED': st.column_config.NumberColumn("Tools", format="%d", help="Total tool invocations"),
                        'ACTIVE_DAYS': st.column_config.NumberColumn("Active Days", format="%d"),
                        'DISTINCT_USERS': st.column_config.NumberColumn("Users", format="%d"),
                        'TOTAL_SCORE': st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                        'CONFIDENCE_BAND': st.column_config.TextColumn("Band"),
                    },
                    hide_index=True, use_container_width=True, height=500
                )
                st.caption("Scoring: S1 Relevant Bundled Skills (30pts) + S2 Relevant Custom Skills (35pts) + S3 Tools (20pts) + S4 Skill Intensity per Day (15pts)")
            else:
                st.info("No confidence scoring data available.")

st.divider()

st.subheader("Top Partners by CoCo Adoption Gap")
gap_partners = filtered_sorted[~filtered_sorted['MEETS_TARGET']].head(15)
if len(gap_partners) > 0:
    gap_partners = gap_partners.copy()
    gap_partners['GAP'] = gap_partners.apply(
        lambda r: max(0, int((target / 100.0 * r['TOTAL_USE_CASES']) - r['COCO_USE_CASES'] + 0.999)), axis=1
    )
    gap_partners['GAP_EACV'] = gap_partners['TOTAL_EACV'] - gap_partners['COCO_EACV']

    fig = px.bar(
        gap_partners.sort_values('GAP', ascending=True),
        y='PARTNER_NAME', x='GAP', orientation='h',
        color='COCO_PCT', color_continuous_scale='RdYlGn',
        labels={'GAP': 'Additional CoCo UCs Needed', 'PARTNER_NAME': '', 'COCO_PCT': 'Current %'},
        text='GAP'
    )
    fig.update_layout(height=450, yaxis={'categoryorder': 'total ascending'})
    fig.update_traces(textposition='outside')
    st.plotly_chart(fig, use_container_width=True)
else:
    st.success(f"All tracked partners meet the {target}% target!")

st.divider()
st.caption(f"OKR Target: {target}% of use cases in Stages 3-7 should have CoCo attached | {start_date} to {end_date} | Min UCs: {min_use_cases}")
st.caption("CoCo detection: SE Comments (coco/cortex code) OR Partner Comments (#coco) OR Feature Flag (AI - Cortex Code) OR CoCo Account Level Usage")
