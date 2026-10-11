"""Side-by-side opportunity cards for the ACQ Theatre page."""
from datetime import date
import re

import pandas as pd
import streamlit as st


SOURCE = "SALES.RAVEN.SDA_OPPORTUNITY_W_PARTNER_SPLIT_VIEW"
OPPORTUNITY = "SNOW_CERTIFIED.SALESFORCE_OPPORTUNITY.DD_SALESFORCE_OPPORTUNITY"
ACCOUNT = "SNOW_CERTIFIED.SALESFORCE_ACCOUNT.DD_SALESFORCE_ACCOUNT"
USE_CASE = "SNOW_CERTIFIED.SALESFORCE_USE_CASE.DD_SALESFORCE_USE_CASE"
ACTIVITY = "SALES.SE_REPORTING.DIM_SE_ACTIVITY"
COCO = "SNOWSCIENCE.LLM.CORTEX_CODE_USER_DAY_FACT"
SF = "https://snowforce.lightning.force.com/lightning/r"
OPP_ID = re.compile(r"\b(006[a-zA-Z0-9]{12}(?:[a-zA-Z0-9]{3})?)\b")
MAX_MATCHES = 500
CARDS_PER_ROW = 4

STATUS_SQL = """CASE WHEN NOT IS_OPPORTUNITY_CLOSED THEN 'Open'
                     WHEN VALUE_TYPE IN ('Actual', 'Not In Deal Sheet') THEN 'Won'
                     ELSE 'Lost' END"""


def quarter_start(day: date) -> date:
    """Snowflake fiscal quarters start in Feb, May, Aug and Nov."""
    month = ((day.month - 2) % 12) // 3 * 3 + 2
    return date(day.year - (month > day.month), month, 1)


def engagement_sql(opps_sql):
    """SE / PSE engagement per opportunity, for the opportunity IDs selected by `opps_sql`.

    Activity counts whether it was logged on the opportunity or on one of its use cases.
    PSEs often record their work only in the use case Partner Comments field (no logged
    activity), so PSE_INVOLVED = a PSE activity OR partner comments on a linked use case.
    Scheduled (future) meetings are not counted.
    """
    return f"""
        WITH opps AS (SELECT DISTINCT OPPORTUNITY_ID FROM ({opps_sql})),
        ucs AS (
            SELECT SALESFORCE_USE_CASE_ID AS USE_CASE_ID, SALESFORCE_OPPORTUNITY_ID AS OPPORTUNITY_ID,
                   NULLIF(TRIM(SALESFORCE_USE_CASE_PARTNER_COMMENTS), '') AS PARTNER_COMMENTS
            FROM {USE_CASE}
            WHERE SALESFORCE_OPPORTUNITY_ID IN (SELECT OPPORTUNITY_ID FROM opps)
        ),
        act AS (
            SELECT COALESCE(o.OPPORTUNITY_ID, u.OPPORTUNITY_ID) AS OPPORTUNITY_ID,
                   a.ACTIVITY_DATE, a.ACTIVITY_SE_NAME, a.ACTIVITY_SE_GROUP
            FROM {ACTIVITY} a
            LEFT JOIN opps o ON a.OPP_ID = o.OPPORTUNITY_ID
            LEFT JOIN ucs u ON a.USE_CASE_ID = u.USE_CASE_ID
            WHERE (o.OPPORTUNITY_ID IS NOT NULL OR u.USE_CASE_ID IS NOT NULL)
              AND COALESCE(a.IS_FUTURE_MEETING, FALSE) = FALSE
              AND a.ACTIVITY_DATE <= CURRENT_DATE()
        ),
        act_agg AS (
            SELECT OPPORTUNITY_ID,
                   COUNT(*) AS SE_ACTIVITIES,
                   MAX(ACTIVITY_DATE) AS LAST_SE_ACTIVITY,
                   LISTAGG(DISTINCT ACTIVITY_SE_NAME || ' (' || COALESCE(ACTIVITY_SE_GROUP, '?') || ')', ', ')
                       WITHIN GROUP (ORDER BY ACTIVITY_SE_NAME || ' (' || COALESCE(ACTIVITY_SE_GROUP, '?') || ')') AS SE_PEOPLE,
                   BOOLOR_AGG(ACTIVITY_SE_GROUP = 'PSE') AS PSE_ACTIVITY,
                   LISTAGG(DISTINCT IFF(ACTIVITY_SE_GROUP = 'PSE', ACTIVITY_SE_NAME, NULL), ', ')
                       WITHIN GROUP (ORDER BY IFF(ACTIVITY_SE_GROUP = 'PSE', ACTIVITY_SE_NAME, NULL)) AS PSE_PEOPLE
            FROM act GROUP BY OPPORTUNITY_ID
        ),
        uc_agg AS (
            SELECT OPPORTUNITY_ID, COUNT(PARTNER_COMMENTS) > 0 AS UC_PARTNER_COMMENTS
            FROM ucs GROUP BY OPPORTUNITY_ID
        )
        SELECT o.OPPORTUNITY_ID,
               COALESCE(a.SE_ACTIVITIES, 0) AS SE_ACTIVITIES, a.LAST_SE_ACTIVITY, a.SE_PEOPLE,
               COALESCE(a.PSE_ACTIVITY, FALSE) AS PSE_ACTIVITY, a.PSE_PEOPLE,
               COALESCE(u.UC_PARTNER_COMMENTS, FALSE) AS UC_PARTNER_COMMENTS,
               COALESCE(a.PSE_ACTIVITY, FALSE) OR COALESCE(u.UC_PARTNER_COMMENTS, FALSE) AS PSE_INVOLVED
        FROM opps o
        LEFT JOIN act_agg a ON a.OPPORTUNITY_ID = o.OPPORTUNITY_ID
        LEFT JOIN uc_agg u ON u.OPPORTUNITY_ID = o.OPPORTUNITY_ID
    """


def placeholders(values):
    return ", ".join("?" for _ in values)


def find_opportunities(conn, ids, partner, statuses):
    """One row per opportunity (all partners and splits rolled up)."""
    if ids:
        where = " OR ".join(["OPPORTUNITY_ID = ? OR LEFT(OPPORTUNITY_ID, 15) = ?"] * len(ids))
        params = [v for opp_id in ids for v in (opp_id, opp_id[:15])]
        status_filter = ""
    else:
        where = "PARTNER_NAME ILIKE ? OR PARENT_PARTNER_NAME ILIKE ?"
        params = [f"%{partner}%", f"%{partner}%"]
        status_filter = f"HAVING MAX({STATUS_SQL}) IN ({placeholders(statuses)})"
        params += statuses
    query = f"""
        SELECT OPPORTUNITY_ID,
               MAX(OPPORTUNITY_NAME) AS OPPORTUNITY,
               MAX(SALESFORCE_ACCOUNT_NAME) AS CUSTOMER,
               MAX(SALESFORCE_ACCOUNT_ID) AS ACCOUNT_ID,
               MAX(OPPORTUNITY_OWNER_NAME) AS OWNER,
               MAX(OPPORTUNITY_THEATER) AS THEATER,
               MAX(OPPORTUNITY_REGION) AS REGION,
               MAX(CLOSED_AT) AS CLOSE_DATE,
               MAX({STATUS_SQL}) AS STATUS,
               BOOLOR_AGG(IS_OPPORTUNITY_CAP_ONE) AS IS_CAP_ONE,
               MAX(OPPORTUNITY_PIPELINE_SOURCE) AS PIPELINE_SOURCE,
               LISTAGG(DISTINCT PARTNER_NAME || ' (' || COALESCE(NULLIF(PARTNER_TYPE, ''), 'Unspecified')
                       || ', ' || ROUND(PARTNER_SPLIT * 100) || '%)', '; ') AS PARTNERS,
               COUNT(DISTINCT PARTNER_ID) AS PARTNER_COUNT,
               SUM(OPPORTUNITY_ACV_PARTNER_AFTER_SPLIT) AS ACV_USD,
               SUM(OPPORTUNITY_WEIGHTED_ACV_PARTNER_AFTER_SPLIT) AS WEIGHTED_ACV_USD
        FROM {SOURCE}
        -- Match on the search, then roll up every partner on the matched opportunities.
        WHERE PARTNER_ID IS NOT NULL
          AND OPPORTUNITY_ID IN (SELECT OPPORTUNITY_ID FROM {SOURCE} WHERE {where})
        GROUP BY OPPORTUNITY_ID
        {status_filter}
        ORDER BY CLOSE_DATE, ACV_USD DESC
        LIMIT {MAX_MATCHES + 1}
    """
    # Do not share row-policy-dependent results across viewers via a global cache.
    return conn.query(query, params=params, ttl=0)


def load_details(conn, ids, account_ids, coco_since):
    """Opportunity, use case, SE activity and CoCo details for the selected opportunities."""
    opp = conn.query(f"""
        SELECT o.SALESFORCE_OPPORTUNITY_ID AS OPPORTUNITY_ID,
               o.SALESFORCE_OPPORTUNITY_STAGE_NAME AS STAGE,
               o.SALESFORCE_OPPORTUNITY_TYPE AS OPPORTUNITY_TYPE,
               o.SALESFORCE_OPPORTUNITY_USE_CASES AS PRODUCT_CATEGORIES,
               o.SALESFORCE_OPPORTUNITY_LEAD_SOLUTION_ENGINEER_NAME AS LEAD_SE,
               o.SALESFORCE_OPPORTUNITY_NEXT_STEPS AS NEXT_STEPS,
               a.SALESFORCE_ACCOUNT_BILLING_COUNTRY AS COUNTRY
        FROM {OPPORTUNITY} o
        LEFT JOIN {ACCOUNT} a ON a.SALESFORCE_ACCOUNT_ID = o.SALESFORCE_ACCOUNT_ID
        WHERE o.SALESFORCE_OPPORTUNITY_ID IN ({placeholders(ids)})
    """, params=ids, ttl=0)
    use_cases = conn.query(f"""
        SELECT SALESFORCE_OPPORTUNITY_ID AS OPPORTUNITY_ID, SALESFORCE_USE_CASE_ID AS USE_CASE_ID,
               SALESFORCE_USE_CASE_NUMBER AS USE_CASE_NUMBER, SALESFORCE_USE_CASE_NAME AS USE_CASE_NAME,
               SALESFORCE_USE_CASE_STAGE AS USE_CASE_STAGE, SALESFORCE_USE_CASE_WORKLOADS AS WORKLOADS,
               SALESFORCE_USE_CASE_TECHNICAL_USE_CASE AS TECHNICAL_USE_CASE,
               SALESFORCE_USE_CASE_PARTNER_COMMENTS AS PARTNER_COMMENTS
        FROM {USE_CASE}
        WHERE SALESFORCE_OPPORTUNITY_ID IN ({placeholders(ids)})
        ORDER BY SALESFORCE_USE_CASE_NUMBER
    """, params=ids, ttl=0)
    activity = conn.query(engagement_sql(
        f"SELECT COLUMN1 AS OPPORTUNITY_ID FROM VALUES {', '.join('(?)' for _ in ids)}"), params=ids, ttl=0)
    # Paid accounts and trial / PoC accounts are reported separately: Cap 1 customers often
    # only have a trial account while the PoC runs.
    coco = conn.query(f"""
        SELECT SALESFORCE_ACCOUNT_ID AS ACCOUNT_ID,
               COUNT(DISTINCT IFF(SNOWFLAKE_ACCOUNT_TYPE = 'Customer', USER_ID, NULL)) AS COCO_USERS,
               COUNT(DISTINCT IFF(SNOWFLAKE_ACCOUNT_TYPE = 'Customer', DS, NULL)) AS COCO_DAYS,
               COUNT(DISTINCT IFF(SNOWFLAKE_ACCOUNT_TYPE <> 'Customer', USER_ID, NULL)) AS TRIAL_COCO_USERS,
               COUNT(DISTINCT IFF(SNOWFLAKE_ACCOUNT_TYPE <> 'Customer', DS, NULL)) AS TRIAL_COCO_DAYS
        FROM {COCO}
        WHERE SNOWFLAKE_ACCOUNT_TYPE IN ('Customer', 'Trial and other Non-Paying Customers')
          AND TOTAL_DAILY_REQUESTS > 0 AND DS >= ?
          AND SALESFORCE_ACCOUNT_ID IN ({placeholders(account_ids)})
        GROUP BY SALESFORCE_ACCOUNT_ID
    """, params=[coco_since, *account_ids], ttl=0)
    return opp, use_cases, activity, coco


def md(value) -> str:
    """Escape Salesforce free text so it renders as plain text inside a markdown table cell."""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~])", r"\\\1", text)


def money(value) -> str:
    value = num(value)
    return f"${value / 1e6:,.2f}M" if abs(value) >= 1e6 else f"${value / 1e3:,.0f}K"


def txt(value, default="—"):
    """Escaped text, or the default for blank / missing values (NaN is truthy, so test explicitly)."""
    return md(value) if isinstance(value, str) and value.strip() else default


def num(value) -> float:
    return float(value) if pd.notna(value) else 0.0


def flag(value) -> bool:
    return bool(value) if pd.notna(value) else False


def card_rows(opp, ucs, coco_since):
    """Field label -> markdown cell for one opportunity."""
    opp_link = f"[{md(opp['OPPORTUNITY_ID'])}]({SF}/Opportunity/{opp['OPPORTUNITY_ID']}/view)"
    cap = "Cap 1" if flag(opp["IS_CAP_ONE"]) else "Cap N"
    close = pd.to_datetime(opp["CLOSE_DATE"])
    close_label = "Close date" if opp["STATUS"] != "Open" else "Expected close"
    lead_se = txt(opp.get("LEAD_SE"))

    if len(ucs) == 1:
        uc = ucs.iloc[0]
        use_case = (f"[{md(uc['USE_CASE_NUMBER'])}]({SF}/Use_Case__c/{uc['USE_CASE_ID']}/view) "
                    f"\"{md(uc['USE_CASE_NAME'])}\", {md(uc['USE_CASE_STAGE'])}")
        sub_types = [t.strip() for t in str(uc["TECHNICAL_USE_CASE"] or "").split(";") if t.strip()]
        workload = f"**{txt(uc['WORKLOADS'], 'Not set').replace(';', ', ')}**"
        if sub_types:
            workload += f" ({md(', '.join(sub_types[:4]))}{f', +{len(sub_types) - 4} more' if len(sub_types) > 4 else ''})"
        workload += " — from use case"
    else:
        if ucs.empty:
            use_case = "None linked"
        else:
            use_case = f"{len(ucs)} linked: " + ", ".join(
                f"[{md(u['USE_CASE_NUMBER'])}]({SF}/Use_Case__c/{u['USE_CASE_ID']}/view)" for _, u in ucs.iterrows())
        categories = opp.get("PRODUCT_CATEGORIES")
        workload = (f"**{md(categories.replace(';', ', '))}** — from opportunity product categories"
                    if isinstance(categories, str) and categories.strip() else "Not specified")

    comments = [str(c) for c in ucs["PARTNER_COMMENTS"].dropna() if str(c).strip()] if not ucs.empty else []
    partner_comment = md(comments[0][:300] + ("…" if len(comments[0]) > 300 else "")) if comments else "—"
    # PSE involvement: logged PSE activity, or PSE notes in the use case partner comments.
    pse_evidence = []
    if flag(opp.get("PSE_ACTIVITY")):
        pse_evidence.append(f"PSE activity logged ({txt(opp.get('PSE_PEOPLE'), 'PSE')})")
    if comments:
        commented = ucs[ucs["PARTNER_COMMENTS"].fillna("").str.strip() != ""]
        dates = re.findall(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b", comments[0])
        pse_evidence.append("partner comments on " + ", ".join(md(n) for n in commented["USE_CASE_NUMBER"].astype(str))
                            + (f", latest entry {md(dates[0])}" if dates else ""))
    pse = ("**Yes** — " + "; ".join(pse_evidence)) if pse_evidence else (
        "No — no PSE activity logged" + (" and no use case partner comments" if not ucs.empty else ", no use case linked"))
    next_steps = opp.get("NEXT_STEPS")
    next_steps = txt(next_steps[:300] + ("…" if len(next_steps) > 300 else "")) if isinstance(next_steps, str) else "—"
    def usage(users, days, kind):
        users, days = int(num(users)), int(num(days))
        return f"**{users} user{'s' if users != 1 else ''}** on {kind} accounts, {days} active days" if users else None

    parts = [p for p in (usage(opp.get("COCO_USERS"), opp.get("COCO_DAYS"), "paid"),
                         usage(opp.get("TRIAL_COCO_USERS"), opp.get("TRIAL_COCO_DAYS"), "trial / PoC")) if p]
    coco = ("; ".join(parts) + f" since {coco_since:%b %d}") if parts else f"None since {coco_since:%b %d}"
    partner_count = int(num(opp["PARTNER_COUNT"]))

    return {
        "Opportunity": opp_link,
        "Customer": f"{txt(opp['CUSTOMER'])} ({txt(opp.get('COUNTRY'), txt(opp['REGION']))})",
        "Theater / region": f"{txt(opp['THEATER'])} / {txt(opp['REGION'])}",
        close_label: f"**{close:%b %d, %Y}**" if pd.notna(close) else "—",
        "Status / stage": f"{md(opp['STATUS'])} / {txt(opp.get('STAGE'))}",
        "Type": f"{cap}, {txt(opp.get('OPPORTUNITY_TYPE'))}",
        "ACV (weighted)": f"**{money(opp['ACV_USD'])}** ({money(opp['WEIGHTED_ACV_USD'])})",
        "PSE involved": pse,
        # One row for every card (a 1:1 use case, or none / several linked) so mixed cards line up.
        "Use case (1:1)": use_case,
        "Partner type / split": txt(opp["PARTNERS"]) + (" — sole partner" if partner_count == 1 else ""),
        "Pipeline source": txt(opp["PIPELINE_SOURCE"].title() if isinstance(opp["PIPELINE_SOURCE"], str) else None),
        "Owner / lead SE": f"{txt(opp['OWNER'])} / {lead_se}",
        "Workload": workload,
        "CoCo usage in account": coco,
        "Use case partner comment": partner_comment,
        "Next steps": next_steps,
    }


def render_cards(cards, titles):
    labels = list(dict.fromkeys(label for card in cards for label in card))
    header = "| | " + " | ".join(f"**{md(t)}**" for t in titles) + " |"
    lines = [header, "|---|" + "---|" * len(cards)]
    lines += ["| " + label + " | " + " | ".join(card.get(label, "—") for card in cards) + " |" for label in labels]
    st.markdown("\n".join(lines))


def show_cards(conn, ids, matches=None, coco_since=None):
    """Render side-by-side cards for the given opportunity IDs (in that order)."""
    if not ids:
        return
    try:
        if matches is None:
            matches = find_opportunities(conn, ids, None, None)
        chosen = matches[matches["OPPORTUNITY_ID"].isin(ids)].copy()
        if chosen.empty:
            st.info("None of these opportunities have a partner attached, or they are not visible to this connection.")
            return
        ids = [i for i in ids if i in set(chosen["OPPORTUNITY_ID"])]
        coco_since = coco_since or quarter_start(date.today())
        account_ids = chosen["ACCOUNT_ID"].dropna().unique().tolist() or [""]
        opp_info, use_cases, activity, coco = load_details(conn, ids, account_ids, coco_since)
    except Exception as exc:
        st.error(f"Could not load opportunity details: {exc}")
        return

    chosen = (chosen.merge(opp_info, on="OPPORTUNITY_ID", how="left")
              .merge(activity, on="OPPORTUNITY_ID", how="left")
              .merge(coco, on="ACCOUNT_ID", how="left"))
    chosen["OPPORTUNITY_ID"] = pd.Categorical(chosen["OPPORTUNITY_ID"], categories=ids, ordered=True)
    chosen = chosen.sort_values("OPPORTUNITY_ID")

    cards, titles = [], []
    for _, opp in chosen.iterrows():
        cards.append(card_rows(opp, use_cases[use_cases["OPPORTUNITY_ID"] == opp["OPPORTUNITY_ID"]], coco_since))
        titles.append(opp["OPPORTUNITY"] if isinstance(opp["OPPORTUNITY"], str) else str(opp["OPPORTUNITY_ID"]))
    for start in range(0, len(cards), CARDS_PER_ROW):
        render_cards(cards[start:start + CARDS_PER_ROW], titles[start:start + CARDS_PER_ROW])
    st.caption("Workload comes from the opportunity's single linked use case when there is exactly one; otherwise from "
               "the opportunity's product categories. SE activity = meetings and deliverables logged on the opportunity "
               f"in {ACTIVITY}. CoCo usage is for the customer's whole account, not this deal.")
