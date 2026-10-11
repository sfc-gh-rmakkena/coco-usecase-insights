"""Partner opportunity metrics for the AMSAcquisition (ACQ) theater."""
from datetime import date, timedelta
import re

import pandas as pd
import streamlit as st

from utils.opportunity_cards import CARDS_PER_ROW, OPP_ID, engagement_sql, find_opportunities, show_cards


# Grain: opportunity x partner x booking split. ACV columns are already multiplied by
# PARTNER_SPLIT and BOOKINGS_SPLIT_PERCENTAGE, so they can be summed directly; counts
# must use distinct opportunity IDs.
SOURCE = "SALES.RAVEN.SDA_OPPORTUNITY_W_PARTNER_SPLIT_VIEW"
# SE/PSE activity (Setsail meetings and Vivun deliverables) logged against an opportunity.
ACTIVITY_SOURCE = "SALES.SE_REPORTING.DIM_SE_ACTIVITY"
THEATER = "AMSAcquisition"
PARTNER_REGIONS = ("AMSPartner_Services", "LATAM")
MAX_ROWS = 5000


def opportunity_filters(start, end_exclusive, customer_region):
    # Split theater = the theater credited with this booking split, so a deal shared
    # with another theater only contributes its ACQ share.
    conditions = [
        "OPPORTUNITY_SPLIT_THEATER = ?",
        "PARTNER_ID IS NOT NULL",
        f"PARTNER_ETM_REGION IN ({', '.join('?' for _ in PARTNER_REGIONS)})",
        "CLOSED_AT >= ?",
        "CLOSED_AT < ?",
    ]
    params = [THEATER, *PARTNER_REGIONS, start, end_exclusive]
    if customer_region != "All":
        conditions.append("OPPORTUNITY_REGION = ?")
        params.append(customer_region)
    return " AND ".join(conditions), params


def load_opportunities(conn, start, end_exclusive, customer_region):
    where, params = opportunity_filters(start, end_exclusive, customer_region)
    query = f"""
        SELECT OPPORTUNITY_ID,
               OPPORTUNITY_NAME AS OPPORTUNITY,
               SALESFORCE_ACCOUNT_NAME AS CUSTOMER,
               OPPORTUNITY_REGION AS CUSTOMER_REGION,
               OPPORTUNITY_OWNER_NAME AS OWNER,
               PARTNER_NAME AS PARTNER,
               COALESCE(NULLIF(PARENT_PARTNER_NAME, ''), PARTNER_NAME) AS PARTNER_PARENT,
               COALESCE(NULLIF(PARTNER_TYPE, ''), 'Unspecified') AS PARTNER_TYPE,
               COALESCE(NULLIF(PARTNER_ETM_REGION, ''), 'No Partner ETM') AS PARTNER_REGION,
               CASE WHEN NOT IS_OPPORTUNITY_CLOSED THEN 'Open'
                    WHEN VALUE_TYPE IN ('Actual', 'Not In Deal Sheet') THEN 'Won'
                    ELSE 'Lost' END AS STATUS,
               CLOSED_AT AS CLOSE_DATE,
               IS_OPPORTUNITY_CAP_ONE AS IS_CAP_ONE,
               OPPORTUNITY_PIPELINE_SOURCE AS PIPELINE_SOURCE,
               PARTNER_SPLIT,
               BOOKINGS_SPLIT_PERCENTAGE AS BOOKING_SPLIT,
               OPPORTUNITY_ACV_PARTNER_AFTER_SPLIT AS ACV_USD,
               OPPORTUNITY_WEIGHTED_ACV_PARTNER_AFTER_SPLIT AS WEIGHTED_ACV_USD
        FROM {SOURCE}
        WHERE {where}
        ORDER BY CLOSED_AT DESC, OPPORTUNITY_ID
        LIMIT {MAX_ROWS + 1}
    """
    # Do not share row-policy-dependent results across viewers via a global cache.
    return conn.query(query, params=params, ttl=0)


def load_theater_totals(conn, start, end_exclusive, customer_region):
    """Distinct opportunity counts by status for the whole theater, with or without partners."""
    conditions = ["OPPORTUNITY_SPLIT_THEATER = ?", "CLOSED_AT >= ?", "CLOSED_AT < ?"]
    params = [THEATER, start, end_exclusive]
    if customer_region != "All":
        conditions.append("OPPORTUNITY_REGION = ?")
        params.append(customer_region)
    query = f"""
        SELECT COUNT(*) AS OPPORTUNITIES,
               COUNT_IF(STATUS = 'Won') AS WON,
               COUNT_IF(STATUS = 'Lost') AS LOST,
               COUNT_IF(STATUS = 'Open') AS OPEN
        FROM (
            SELECT OPPORTUNITY_ID,
                   ANY_VALUE(CASE WHEN NOT IS_OPPORTUNITY_CLOSED THEN 'Open'
                                  WHEN VALUE_TYPE IN ('Actual', 'Not In Deal Sheet') THEN 'Won'
                                  ELSE 'Lost' END) AS STATUS
            FROM {SOURCE}
            WHERE {' AND '.join(conditions)}
            GROUP BY OPPORTUNITY_ID
        )
    """
    return conn.query(query, params=params, ttl=0)


def load_se_activity(conn, start, end_exclusive, customer_region):
    """Per-opportunity SE/PSE engagement (shared definition with the opportunity cards)."""
    where, params = opportunity_filters(start, end_exclusive, customer_region)
    query = engagement_sql(f"SELECT OPPORTUNITY_ID FROM {SOURCE} WHERE {where}")
    return conn.query(query, params=params, ttl=0)


st.title(":material/handshake: ACQ Theatre")
st.caption(f"Partner-attached opportunities credited to {THEATER} with partners in "
           f"{' and '.join(PARTNER_REGIONS)}, from {SOURCE}. "
           "Every section uses the OKR Start / End Date in the sidebar as the close-date window; "
           "open deals use expected close dates.")

today = date.today()
with st.sidebar:
    st.divider()
    st.markdown("**ACQ Theatre**")
    customer_region = st.selectbox(
        "Customer region", ["All", "CommAcqWest", "CommAcqEast", "LATAM", "EntAcqEast", "EntAcqCentral", "EntAcqWest", "MajorsAcq"],
        key="acq_customer_region", help="Opportunity region within AMSAcquisition.",
    )

# The app-wide OKR date filters (sidebar) define the close-date window for the whole page.
start_date = st.session_state.get("okr_start_date") or date(2026, 8, 1)
last_day = st.session_state.get("okr_end_date") or date(2026, 10, 31)
if start_date > last_day:
    st.error("OKR Start Date is after OKR End Date. Adjust the dates in the sidebar.")
    st.stop()
end_date = last_day + timedelta(days=1)  # exclusive
period = f"{start_date:%b %d, %Y} – {last_day:%b %d, %Y}"
st.caption(f"Close-date window: {period} | Customer region: {customer_region}")

try:
    rows = load_opportunities(st.session_state.conn, start_date, end_date, customer_region)
except Exception as exc:
    st.error(f"Could not load ACQ partner opportunities: {exc}")
    st.stop()

if len(rows) > MAX_ROWS:
    st.warning(f"More than {MAX_ROWS:,} partner rows match. Narrow the region filters to see a complete breakdown.")
    st.stop()
if rows.empty:
    st.info(f"No partner opportunities close between {period} for these filters, or none are visible to this "
            "connection. Widen the OKR Start / End Date in the sidebar.")
    st.stop()

for col in ("ACV_USD", "WEIGHTED_ACV_USD"):
    rows[col] = pd.to_numeric(rows[col], errors="coerce").fillna(0)
# Cap 1 is an opportunity-level flag; take it from any of the opportunity's rows.
rows["CAP"] = rows.groupby("OPPORTUNITY_ID")["IS_CAP_ONE"].transform("max").map({True: "Cap 1"}).fillna("Cap N")

activity_columns = ["OPPORTUNITY_ID", "SE_ACTIVITIES", "LAST_SE_ACTIVITY", "SE_PEOPLE", "PSE_INVOLVED", "PSE_PEOPLE"]
try:
    activity = load_se_activity(st.session_state.conn, start_date, end_date, customer_region)
except Exception as exc:
    st.warning(f"SE activity could not be loaded from {ACTIVITY_SOURCE}: {exc}")
    activity = pd.DataFrame(columns=activity_columns)
rows = rows.merge(activity[activity_columns], on="OPPORTUNITY_ID", how="left")
rows["SE_ACTIVITIES"] = pd.to_numeric(rows["SE_ACTIVITIES"], errors="coerce").fillna(0).astype(int)
rows["PSE_INVOLVED"] = rows["PSE_INVOLVED"].astype("boolean").fillna(False).astype(bool)

partner_types = sorted(rows["PARTNER_TYPE"].unique())
partner_regions = rows["PARTNER_REGION"].value_counts().index.tolist()
filter_columns = st.columns(2)
with filter_columns[0]:
    selected_regions = st.pills("Partner region", partner_regions, selection_mode="multi",
                                default=partner_regions, key="acq_partner_region", help="Partner's ETM region.")
with filter_columns[1]:
    selected_types = st.pills("Partner type", partner_types, selection_mode="multi",
                              default=partner_types, key="acq_partner_type")
rows = rows[rows["PARTNER_REGION"].isin(selected_regions or partner_regions)
            & rows["PARTNER_TYPE"].isin(selected_types or partner_types)]


def summarize(df):
    """Opportunity counts (distinct) and split ACV by status."""
    opps = lambda status: df.loc[df["STATUS"] == status, "OPPORTUNITY_ID"].nunique()
    acv = lambda status, col="ACV_USD": df.loc[df["STATUS"] == status, col].sum()
    won, lost = opps("Won"), opps("Lost")
    return {
        "OPPORTUNITIES": df["OPPORTUNITY_ID"].nunique(),
        "WON": won, "LOST": lost, "OPEN": opps("Open"),
        "WIN_RATE": won / (won + lost) if won + lost else None,
        "WON_ACV_USD": acv("Won"),
        "PIPELINE_ACV_USD": acv("Open"),
        "WEIGHTED_PIPELINE_USD": acv("Open", "WEIGHTED_ACV_USD"),
        "WITH_SE_ACTIVITY": df.loc[df["SE_ACTIVITIES"] > 0, "OPPORTUNITY_ID"].nunique(),
        "WITH_PSE": df.loc[df["PSE_INVOLVED"], "OPPORTUNITY_ID"].nunique(),
    }


def money_short(value):
    return f"${value / 1e6:,.2f}M" if abs(value) >= 1e6 else f"${value / 1e3:,.0f}K"


def share(part, whole, of="opps"):
    return f"{part / whole:.0%} of {of}" if whole else None


def tile_row(label, items):
    """A labelled, wrapping row of compact bordered metric tiles: (title, value, note)."""
    st.caption(f"**{label}**")
    with st.container(horizontal=True):
        for title, value, note in items:
            st.metric(title, value, note, delta_color="off", delta_arrow="off", border=True)


# Compact tiles, scoped to this page's tile containers (keys starting with acq_tiles).
# The headline box mirrors the "Overall Company Sentiment" box on the Overview page.
st.markdown("""<style>
[class*="st-key-acq_tiles"] [data-testid="stMetric"] { padding: 6px 12px !important; min-width: 130px; }
[class*="st-key-acq_tiles"] [data-testid="stMetricLabel"] p {
    font-size: 11px !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: .4px; }
[class*="st-key-acq_tiles"] [data-testid="stMetricValue"] { font-size: 20px !important; font-weight: 700 !important; }
[class*="st-key-acq_tiles"] [data-testid="stMetricDelta"] { font-size: 11px !important; }
.acq-total-box { border: 2px solid #29B5E8; border-radius: 8px; padding: 12px 16px; background: rgba(41,181,232,0.06); }
.acq-total-title { color: #003a5c; font-weight: 700; font-size: 18px; margin-bottom: 10px; }
.acq-total-metrics { display: flex; gap: 48px; flex-wrap: wrap; }
.acq-total-label { color: #0b6c96; font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
.acq-total-value { color: #003a5c; font-weight: 800; font-size: 28px; line-height: 1.2; }
.acq-total-note { color: #0b6c96; font-size: 12px; margin-top: 2px; }
</style>""", unsafe_allow_html=True)

total = summarize(rows)
n = total["OPPORTUNITIES"]
cap = {c: summarize(rows[rows["CAP"] == c]) for c in ("Cap 1", "Cap N")}
opp_level = rows.drop_duplicates("OPPORTUNITY_ID")
partner_sourced = int(opp_level["PIPELINE_SOURCE"].fillna("").str.contains("PARTNER").sum())
try:
    theater = load_theater_totals(st.session_state.conn, start_date, end_date, customer_region).iloc[0]
    theater = {key: int(theater[key]) for key in ("OPPORTUNITIES", "WON", "LOST", "OPEN")}
except Exception as exc:
    st.warning(f"Theater totals could not be loaded: {exc}")
    theater = None


def win_rate(won, lost):
    return f"{won / (won + lost):.0%}" if won + lost else "–"


def headline_box(title, items):
    """Blue headline box; items are (label, value, hover tip, note under the value). Values are app-computed."""
    st.markdown(
        f'<div class="acq-total-box"><div class="acq-total-title">{title}</div><div class="acq-total-metrics">'
        + "".join(f'<div title="{tip or ""}"><div class="acq-total-label">{label}</div>'
                  f'<div class="acq-total-value">{value}</div>'
                  + (f'<div class="acq-total-note">{note}</div>' if note else "") + "</div>"
                  for label, value, tip, note in items)
        + "</div></div>", unsafe_allow_html=True)
    st.write("")


if theater:
    headline_box(f"All {THEATER} Opportunities", [
        ("Total opps", f"{theater['OPPORTUNITIES']:,}", f"All {THEATER} opportunities, with or without a partner", None),
        ("Won", f"{theater['WON']:,}", None, None), ("Lost", f"{theater['LOST']:,}", None, None),
        ("Open", f"{theater['OPEN']:,}", None, None),
        ("Win rate", win_rate(theater["WON"], theater["LOST"]), "Won / (won + lost)", None),
    ])

acq_noun = {"OPPORTUNITIES": "opps", "WON": "won", "LOST": "lost", "OPEN": "open"}
# Partner share of the matching all-ACQ count in the box above, e.g. partner won / all ACQ won.
of_acq = lambda key: share(total[key], theater[key], f"all ACQ {acq_noun[key]}") if theater else None
regions = " / ".join(PARTNER_REGIONS)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Partner opps", f"{n:,}", of_acq("OPPORTUNITIES"),
          help=f"Opportunities with at least one {regions} partner attached")
c2.metric("Partner won", f"{total['WON']:,}", of_acq("WON"), help="Closed won partner opportunities")
c3.metric("Partner lost", f"{total['LOST']:,}", of_acq("LOST"), delta_color="inverse",
          help="Closed with no booked value; closed-lost deals are under-recorded in the source view")
c4.metric("Partner open", f"{total['OPEN']:,}", of_acq("OPEN"), help="Not yet closed; uses expected close date")
c5.metric("Partner win rate", win_rate(total["WON"], total["LOST"]),
          f"vs {win_rate(theater['WON'], theater['LOST'])} all ACQ" if theater else None,
          help="Won / (won + lost) for partner opportunities")
st.write("")

# Weekly view (Monday-Sunday) for partner opportunities only, clipped to the sidebar date
# window like the rest of the page; follows the region and partner filters.
this_week = today - timedelta(days=today.weekday())
last_week = this_week - timedelta(days=7)
next_week = this_week + timedelta(days=7)
week_start, week_end = max(last_week, start_date), min(next_week, end_date)
weeks_clipped = (week_start, week_end) != (last_week, next_week)
try:
    if week_start >= week_end:
        raise LookupError
    weekly = load_opportunities(st.session_state.conn, week_start, week_end, customer_region)
    weekly = weekly[weekly["PARTNER_REGION"].isin(selected_regions or partner_regions)
                    & weekly["PARTNER_TYPE"].isin(selected_types or partner_types)].copy()
    weekly["CLOSE_DATE"] = pd.to_datetime(weekly["CLOSE_DATE"]).dt.date
    weekly["ACV_USD"] = pd.to_numeric(weekly["ACV_USD"], errors="coerce").fillna(0)
    # One row per opportunity; ACV summed across its partner split rows.
    weekly = (weekly.groupby("OPPORTUNITY_ID", as_index=False)
              .agg(OPPORTUNITY=("OPPORTUNITY", "first"), CLOSE_DATE=("CLOSE_DATE", "first"),
                   STATUS=("STATUS", "first"), ACV_USD=("ACV_USD", "sum")))
except LookupError:
    st.caption(f"Partner opportunities by week: last week and this week fall outside {period}.")
    weekly = None
except Exception as exc:
    st.warning(f"Weekly partner opportunities could not be loaded: {exc}")
    weekly = None

if weekly is not None:
    week_status = lambda first, last, status: int(((weekly["CLOSE_DATE"] >= first) & (weekly["CLOSE_DATE"] < last)
                                                  & (weekly["STATUS"] == status)).sum())
    last_won, last_lost = week_status(last_week, this_week, "Won"), week_status(last_week, this_week, "Lost")
    this_won, this_lost = week_status(this_week, next_week, "Won"), week_status(this_week, next_week, "Lost")
    scheduled = weekly[(weekly["STATUS"] == "Open") & (weekly["CLOSE_DATE"] >= this_week)
                       & (weekly["CLOSE_DATE"] < next_week)]
    past_due = int((scheduled["CLOSE_DATE"] < today).sum())
    headline_box("Partner Opportunities by Week" + (" (within the selected dates)" if weeks_clipped else ""), [
        ("Closed last week", f"{last_won + last_lost:,}", "Partner opps closed won or lost last week",
         f"{last_won} won · {last_lost} lost · {last_week:%b %d}–{this_week - timedelta(days=1):%b %d}"),
        ("Closed so far this week", f"{this_won + this_lost:,}", "Partner opps closed won or lost since Monday",
         f"{this_won} won · {this_lost} lost · {this_week:%b %d}–{next_week - timedelta(days=1):%b %d}"),
        ("Scheduled to close this week", f"{len(scheduled):,}",
         "Open partner opps whose expected close date falls this week",
         f"{money_short(scheduled['ACV_USD'].sum())} open" + (f" · {past_due} past due" if past_due else "")),
    ])

with st.container(key="acq_tiles_kpis"):
    tile_row("ACV (after partner and booking splits) and engagement", [
        ("Won ACV", money_short(total["WON_ACV_USD"]), None),
        ("Open pipeline", money_short(total["PIPELINE_ACV_USD"]), None),
        ("Partner-sourced opps", f"{partner_sourced:,}", share(partner_sourced, n)),
        ("With PSE involvement", f"{total['WITH_PSE']:,}", share(total["WITH_PSE"], n)),
    ])
    tile_row("Cap 1 / Cap N", [
        (c, f"{cap[c]['OPPORTUNITIES']:,} opps · {money_short(cap[c]['WON_ACV_USD'])} won ACV",
         f"{cap[c]['WON']} won · {cap[c]['OPEN']} open ({money_short(cap[c]['PIPELINE_ACV_USD'])})") for c in cap
    ])
st.caption("An opportunity can have several partners, so partner counts can overlap, but ACV is not double "
           "counted. Win rate = won / (won + lost); closed-lost deals are under-recorded in the source view. "
           f"PSE involvement = a PSE activity logged on the opportunity or its use case in {ACTIVITY_SOURCE}, "
           "or partner comments on its use case (PSEs often record their work only there).")

st.subheader("Customer regions")
st.caption("Select one or more region tiles to filter the Partners table. With none selected, all regions are shown.")
rows = rows.assign(CUSTOMER_REGION=rows["CUSTOMER_REGION"].fillna("Unassigned"))
by_region = pd.DataFrame([{"CUSTOMER_REGION": region, **summarize(group)}
                          for region, group in rows.groupby("CUSTOMER_REGION")])
by_region = by_region.sort_values("OPPORTUNITIES", ascending=False)
region_keys = {region: "acq_region_" + re.sub(r"\W+", "_", str(region)) for region in by_region["CUSTOMER_REGION"]}


def clear_region_selection():
    for key in region_keys.values():
        st.session_state[key] = False


with st.container(key="acq_tiles_regions"), st.container(horizontal=True):
    for _, region_row in by_region.iterrows():
        region = str(region_row["CUSTOMER_REGION"])
        with st.container(border=True, key=f"{region_keys[region]}_tile"):
            st.metric(region, f'{int(region_row["OPPORTUNITIES"]):,} opps',
                      f'{money_short(region_row["WON_ACV_USD"])} won · {int(region_row["OPEN"])} open',
                      delta_color="off", delta_arrow="off")
            st.checkbox("Select", key=region_keys[region])
selected_customer_regions = [region for region, key in region_keys.items() if st.session_state.get(key)]
if selected_customer_regions:
    # Highlight selected tiles like the headline boxes.
    st.markdown("<style>" + "".join(
        f".st-key-{region_keys[region]}_tile {{ border: 2px solid #29B5E8 !important; "
        "background: rgba(41,181,232,0.08) !important; }"
        for region in selected_customer_regions) + "</style>", unsafe_allow_html=True)

money = lambda label: st.column_config.NumberColumn(label, format="$%.0f")
st.subheader("Partners")
partner_rows = rows[rows["CUSTOMER_REGION"].isin(selected_customer_regions)] if selected_customer_regions else rows
with st.container(horizontal=True, vertical_alignment="center"):
    st.caption(f"Customer regions: **{', '.join(selected_customer_regions) if selected_customer_regions else 'All'}** · "
               f"{partner_rows['PARTNER_PARENT'].nunique():,} partners · "
               f"{partner_rows['OPPORTUNITY_ID'].nunique():,} opportunities")
    if selected_customer_regions:
        st.button("Clear selection", icon=":material/close:", on_click=clear_region_selection,
                  key="acq_region_clear", type="tertiary")
by_partner = pd.DataFrame([{"PARTNER_PARENT": partner, **summarize(group),
                            "PARTNER_TYPES": ", ".join(sorted(group["PARTNER_TYPE"].unique())),
                            "CUSTOMER_REGIONS": ", ".join(group["CUSTOMER_REGION"].value_counts().index)}
                           for partner, group in partner_rows.groupby("PARTNER_PARENT")])
by_partner = by_partner.sort_values(["WON_ACV_USD", "OPPORTUNITIES"], ascending=False)
by_partner = by_partner.drop(columns=["WEIGHTED_PIPELINE_USD", "WITH_SE_ACTIVITY"])
st.dataframe(by_partner, hide_index=True, use_container_width=True,
             column_config={"PARTNER_PARENT": "Partner (parent)",
                            "WIN_RATE": st.column_config.NumberColumn("Win rate", format="percent"),
                            "WON_ACV_USD": money("Won ACV"),
                            "PIPELINE_ACV_USD": money("Open pipeline ACV"),
                            "WITH_PSE": "Opps with PSE",
                            "PARTNER_TYPES": "Partner types",
                            "CUSTOMER_REGIONS": "Customer regions (most deals first)"})

QUICK_PICKS = {"Closing this week": ":material/event:", "Closed last week": ":material/history:",
               "Largest open deals": ":material/trending_up:"}


def opportunity_candidates(df):
    """One row per opportunity with total ACV across its partner rows."""
    return (df.groupby("OPPORTUNITY_ID", as_index=False)
            .agg(OPPORTUNITY=("OPPORTUNITY", "first"), STATUS=("STATUS", "first"),
                 CLOSE_DATE=("CLOSE_DATE", "first"), ACV_USD=("ACV_USD", "sum")))


with st.container(border=True):
    st.markdown("#### :material/view_column: Opportunity cards")
    st.caption(f"Compare up to {CARDS_PER_ROW} partner opportunities side by side: status, ACV, partners and splits, "
               "SE/PSE involvement, use case, workload, CoCo usage and next steps.")
    pick_col, search_col = st.columns([3, 2], vertical_alignment="bottom")
    with pick_col:
        quick = st.segmented_control("Quick pick", list(QUICK_PICKS), format_func=lambda o: f"{QUICK_PICKS[o]} {o}",
                                     key="acq_card_quick")
    with search_col:
        card_search = st.text_input(
            "Or search", key="acq_card_search", icon=":material/search:",
            placeholder="Opportunity ID, link, partner or customer",
            help="Paste an opportunity ID or Salesforce link, or type part of a partner, customer or opportunity "
                 "name. Results are limited to the OKR date range and filters in the sidebar."
        ).strip()

    card_ids = list(dict.fromkeys(OPP_ID.findall(card_search)))
    candidates, source = None, None
    if card_ids:
        # IDs follow the same date window and filters as the rest of the page.
        in_scope = {opp_id[:15]: opp_id for opp_id in rows["OPPORTUNITY_ID"].unique()}
        outside = [opp_id for opp_id in card_ids if opp_id[:15] not in in_scope]
        card_ids = [in_scope[opp_id[:15]] for opp_id in card_ids if opp_id[:15] in in_scope]
        if outside:
            try:
                found = find_opportunities(st.session_state.conn, outside, None, None)
            except Exception:
                found = pd.DataFrame(columns=["OPPORTUNITY_ID"])
            for opp_id in outside:
                match = found[found["OPPORTUNITY_ID"].str[:15] == opp_id[:15]]
                if match.empty:
                    st.info(f"{opp_id} was not found, has no partner attached, or is not visible to this connection.",
                            icon=":material/search_off:")
                else:
                    opp = match.iloc[0]
                    close = pd.to_datetime(opp["CLOSE_DATE"])
                    in_window = pd.notna(close) and start_date <= close.date() < end_date
                    reason = ("is outside the sidebar or partner filters" if in_window else
                              f"{'closed' if opp['STATUS'] != 'Open' else 'is expected to close'} on "
                              f"{close:%b %d, %Y}, outside {period}. Widen the OKR Start / End Date in the sidebar")
                    st.info(f"{opp['OPPORTUNITY']} ({opp['STATUS']}) {reason}.", icon=":material/event_busy:")
    elif card_search:
        term = card_search.lower()
        hits = rows[rows[["PARTNER", "PARTNER_PARENT", "CUSTOMER", "OPPORTUNITY"]].fillna("")
                    .apply(lambda col: col.str.lower().str.contains(term, regex=False)).any(axis=1)]
        candidates = opportunity_candidates(hits).sort_values(["CLOSE_DATE", "ACV_USD"], ascending=[True, False])
        source = f'matching "{card_search}"'
    elif not card_search and quick == "Largest open deals":
        candidates = opportunity_candidates(rows[rows["STATUS"] == "Open"]).nlargest(20, "ACV_USD")
        source = f"open, closing {period}, largest ACV first"
    elif not card_search and quick and weekly is not None:
        first, last = (this_week, next_week) if quick == "Closing this week" else (last_week, this_week)
        in_week = weekly[(weekly["CLOSE_DATE"] >= first) & (weekly["CLOSE_DATE"] < last)]
        in_week = in_week[in_week["STATUS"] == "Open"] if quick == "Closing this week" else in_week[in_week["STATUS"] != "Open"]
        candidates = in_week.sort_values(["CLOSE_DATE", "ACV_USD"], ascending=[True, False])
        source = f"{quick.lower()} ({first:%b %d}–{last - timedelta(days=1):%b %d})"

    if candidates is not None:
        if candidates.empty:
            st.info(f"No partner opportunities {source}"
                    + (f" closing {period}. Widen the OKR Start / End Date in the sidebar." if card_search else "."),
                    icon=":material/search_off:")
        else:
            labels = dict(zip(candidates["OPPORTUNITY"].fillna(candidates["OPPORTUNITY_ID"])
                              + " · " + candidates["STATUS"]
                              + " · " + pd.to_datetime(candidates["CLOSE_DATE"]).dt.strftime("%b %d")
                              + " · " + candidates["ACV_USD"].map(money_short),
                              candidates["OPPORTUNITY_ID"]))
            chosen = st.multiselect(
                f"{len(labels)} opportunities {source} — choose which to compare", list(labels),
                default=list(labels)[:CARDS_PER_ROW], max_selections=CARDS_PER_ROW,
                # A new search or quick pick starts from its own default selection.
                key=f"acq_card_selected_{quick}_{card_search}")
            card_ids = [labels[label] for label in chosen]
    if card_ids:
        show_cards(st.session_state.conn, card_ids, coco_since=start_date)
    elif candidates is None and not card_search:
        st.info("Choose a quick pick or search for a partner, customer or opportunity ID to see its cards here.",
                icon=":material/touch_app:")

st.subheader("Opportunity and partner detail")
detail = rows[["OPPORTUNITY_ID", "OPPORTUNITY", "CUSTOMER", "CUSTOMER_REGION", "OWNER", "PARTNER",
               "PARTNER_PARENT", "PARTNER_TYPE", "PARTNER_REGION", "STATUS", "CLOSE_DATE",
               "PARTNER_SPLIT", "BOOKING_SPLIT", "ACV_USD", "SE_ACTIVITIES", "LAST_SE_ACTIVITY",
               "SE_PEOPLE", "PSE_INVOLVED", "PSE_PEOPLE"]].copy()
# Build links only for Salesforce opportunity IDs; encode names for safe display in LinkColumn.
valid_id = detail["OPPORTUNITY_ID"].astype("string").str.fullmatch(r"[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?").fillna(False)


def opportunity_link(opportunity_id, name):
    clean_name = re.sub(r"[\r\n\t#]+", " ", str(name)).strip()
    return f"https://snowforce.lightning.force.com/lightning/r/Opportunity/{opportunity_id}/view#{clean_name}"


detail["OPPORTUNITY"] = [
    opportunity_link(opportunity_id, name) if valid and pd.notna(name) else None
    for valid, opportunity_id, name in zip(valid_id, detail["OPPORTUNITY_ID"], detail["OPPORTUNITY"])
]
st.dataframe(detail, hide_index=True, use_container_width=True,
             column_config={"OPPORTUNITY": st.column_config.LinkColumn(
                                "Opportunity", display_text=r"#(.+)$", help="Open opportunity in Salesforce"),
                            "PARTNER_SPLIT": st.column_config.NumberColumn("Partner split", format="percent"),
                            "BOOKING_SPLIT": st.column_config.NumberColumn("Booking split", format="percent"),
                            "ACV_USD": money("ACV (after splits)"),
                            "SE_ACTIVITIES": st.column_config.NumberColumn("SE activities", format="%d",
                                                                           help="Meetings and deliverables logged on the opportunity"),
                            "LAST_SE_ACTIVITY": st.column_config.DateColumn("Last SE activity"),
                            "SE_PEOPLE": "SEs / PSEs involved",
                            "PSE_INVOLVED": st.column_config.CheckboxColumn("PSE involved"),
                            "PSE_PEOPLE": "PSEs"})
