"""Data context and default prompt for the ACQ Theatre "Generate report" button.

Every figure the report quotes is computed here from the page's own rows, so the readout
matches the page and the model never has to add, divide or rank anything itself.
"""
from datetime import timedelta

import pandas as pd

HIGH_STAKES = 10      # largest open deals in the window
TOP_PARTNERS = 8
RECENT_DAYS = 7       # "last week" = the 7 days before today


def money(value):
    value = float(value or 0)
    return f"${value / 1e6:,.2f}M" if abs(value) >= 1e6 else f"${value / 1e3:,.0f}K"


def pct(part, whole):
    return f"{part / whole:.0%}" if whole else "n/a"


def gap_text(value, baseline):
    """e.g. '$36K below (0.1% below)' — the sign is in the words, never a negative dollar figure."""
    gap = value - baseline
    if abs(gap) < 500:
        return "level with it"
    direction = "above" if gap > 0 else "below"
    share = f" ({abs(gap) / baseline:.1%} {direction})" if baseline else ""
    return f"{money(abs(gap))} {direction}{share}"


def summary(df):
    opps = lambda status: df.loc[df["STATUS"] == status, "OPPORTUNITY_ID"].nunique()
    won, lost = opps("Won"), opps("Lost")
    return {"opps": df["OPPORTUNITY_ID"].nunique(), "won": won, "lost": lost, "open": opps("Open"),
            "win_rate": pct(won, won + lost),
            "won_acv": df.loc[df["STATUS"] == "Won", "ACV_USD"].sum(),
            "pipeline": df.loc[df["STATUS"] == "Open", "ACV_USD"].sum(),
            "weighted": df.loc[df["STATUS"] == "Open", "WEIGHTED_ACV_USD"].sum(),
            "partners": df["PARTNER_PARENT"].nunique(),
            "pse_opps": df.loc[df["PSE_INVOLVED"], "OPPORTUNITY_ID"].nunique()}


def per_opportunity(df):
    """One row per opportunity; split ACV summed across its partner rows."""
    if df.empty:
        return pd.DataFrame(columns=["OPPORTUNITY_ID", "OPPORTUNITY", "CUSTOMER", "REGION", "TERRITORY", "OWNER",
                                     "STATUS", "CLOSE", "ACV", "WEIGHTED", "PSE", "PSES", "PARTNERS"])
    out = df.groupby("OPPORTUNITY_ID").agg(
        OPPORTUNITY=("OPPORTUNITY", "first"), CUSTOMER=("CUSTOMER", "first"), REGION=("CUSTOMER_REGION", "first"),
        TERRITORY=("LATAM_TERRITORY", "first"), OWNER=("OWNER", "first"), STATUS=("STATUS", "first"),
        CLOSE=("CLOSE_DATE", "first"), ACV=("ACV_USD", "sum"), WEIGHTED=("WEIGHTED_ACV_USD", "sum"),
        PSE=("PSE_INVOLVED", "max"), PSES=("PSE_PEOPLE", "first"),
        PARTNERS=("PARTNER_PARENT", lambda s: ", ".join(sorted(set(s.dropna().astype(str)))))).reset_index()
    out["CLOSE"] = pd.to_datetime(out["CLOSE"]).dt.date
    return out


def deal_table(opps):
    if opps.empty:
        return "(none)"
    view = pd.DataFrame({
        "OPPORTUNITY": opps["OPPORTUNITY"], "CUSTOMER_REGION": [
            f"{r} · {t}" if isinstance(t, str) else r for r, t in zip(opps["REGION"], opps["TERRITORY"])],
        "CLOSE": opps["CLOSE"].astype(str), "ACV": opps["ACV"].map(money), "WEIGHTED": opps["WEIGHTED"].map(money),
        "PSE": [p if isinstance(p, str) and p.strip() else ("Yes" if flag else "—")
                for p, flag in zip(opps["PSES"], opps["PSE"])],
        "PARTNERS": opps["PARTNERS"], "OWNER": opps["OWNER"]})
    return view.to_string(index=False, max_colwidth=60)


def summary_line(s):
    return (f"{s['opps']:,} opportunities ({s['won']:,} won · {s['lost']:,} lost · {s['open']:,} open) | "
            f"won ACV {money(s['won_acv'])} | open pipeline {money(s['pipeline'])} (weighted {money(s['weighted'])}) | "
            f"win rate {s['win_rate']} | partners {s['partners']:,} | PSE-involved opportunities {s['pse_opps']:,}")


def breakdown(df, column, label):
    data = [(name, summary(group)) for name, group in df.groupby(column)]
    if not data:
        return "(none)"
    data.sort(key=lambda item: -item[1]["opps"])
    return pd.DataFrame([{label: name, "OPPS": s["opps"], "WON": s["won"], "LOST": s["lost"], "OPEN": s["open"],
                          "WIN_RATE": s["win_rate"], "WON_ACV": money(s["won_acv"]),
                          "OPEN_PIPELINE": money(s["pipeline"]), "PSE_OPPS": s["pse_opps"]}
                         for name, s in data]).to_string(index=False)


def build_context(rows, *, period, customer_region, today, theater=None, previous=None, following=None):
    """rows: the page's filtered opportunity x partner rows. previous/following: (label, rows) or None."""
    total = summary(rows)
    previous_total = summary(previous[1]) if previous and previous[1] is not None and not previous[1].empty else None
    opps = per_opportunity(rows)
    open_opps = opps[opps["STATUS"] == "Open"]
    won_opps = opps[opps["STATUS"] == "Won"]
    projected = total["won_acv"] + total["weighted"]

    theater_text = "(not available)"
    if theater:
        theater_text = (f"All {theater['OPPORTUNITIES']:,} AMSAcquisition opportunities in the window, with or without a "
                        f"partner: {theater['WON']:,} won · {theater['LOST']:,} lost · {theater['OPEN']:,} open "
                        f"(win rate {pct(theater['WON'], theater['WON'] + theater['LOST'])}). Partner-attached share "
                        f"of theater opportunities: {pct(total['opps'], theater['OPPORTUNITIES'])}.")

    overdue = open_opps[open_opps["CLOSE"] < today]
    soon = open_opps[(open_opps["CLOSE"] >= today) & (open_opps["CLOSE"] < today + timedelta(days=14))]

    # Partners
    partners = pd.DataFrame([{"PARTNER": name, **summary(group)} for name, group in rows.groupby("PARTNER_PARENT")])
    def partner_rank(column):
        top = partners[partners[column] > 0].nlargest(TOP_PARTNERS, column)
        if top.empty:
            return "(none)"
        return pd.DataFrame({"PARTNER": top["PARTNER"], "OPPS": top["opps"], "WON": top["won"],
                             "WON_ACV": top["won_acv"].map(money), "OPEN_PIPELINE": top["pipeline"].map(money),
                             "WIN_RATE": top["win_rate"], "PSE_OPPS": top["pse_opps"]}).to_string(index=False)

    # PSE engagement
    pse, no_pse = summary(rows[rows["PSE_INVOLVED"]]), summary(rows[~rows["PSE_INVOLVED"]])
    avg_won = lambda flag: won_opps.loc[won_opps["PSE"] == flag, "ACV"].mean()
    avg_pse, avg_no_pse = avg_won(True), avg_won(False)
    multiple = (f"{avg_pse / avg_no_pse:.1f}x" if pd.notna(avg_pse) and pd.notna(avg_no_pse) and avg_no_pse > 0
                else "n/a")
    names = pd.Series([name.strip() for people in rows.loc[rows["PSE_INVOLVED"]].drop_duplicates("OPPORTUNITY_ID")
                       ["PSE_PEOPLE"].dropna() for name in str(people).split(",") if name.strip()])
    top_pses = (", ".join(f"{n} ({c} opps)" for n, c in names.value_counts().head(8).items())
                if len(names) else "(no PSE named)")
    regions = rows.assign(CUSTOMER_REGION=rows["CUSTOMER_REGION"].fillna("Unassigned"))
    no_coverage = [f"{region} ({s['opps']} opps, {money(s['won_acv'])} won, {money(s['pipeline'])} open pipeline)"
                   for region, group in regions.groupby("CUSTOMER_REGION") if not group["PSE_INVOLVED"].any()
                   for s in [summary(group)]]

    # High-stakes and recent deals
    high = open_opps.nlargest(HIGH_STAKES, "ACV")
    high_uncovered = high[~high["PSE"].astype(bool)]
    recent = opps[(opps["CLOSE"] >= today - timedelta(days=RECENT_DAYS)) & (opps["CLOSE"] < today)]
    recent_won = recent[recent["STATUS"] == "Won"].sort_values("ACV", ascending=False)
    recent_lost = recent[recent["STATUS"] == "Lost"].sort_values("ACV", ascending=False)
    # A debook (won, negative ACV) cancels its rebook; drop both so neither counts as a win.
    adjustments = recent_won[recent_won["ACV"] <= 0]
    offset_ids = set(adjustments["OPPORTUNITY_ID"])
    for _, debook in adjustments[adjustments["ACV"] < 0].iterrows():
        match = recent_won[(recent_won["ACV"] == -debook["ACV"]) & (recent_won["CUSTOMER"] == debook["CUSTOMER"])
                           & ~recent_won["OPPORTUNITY_ID"].isin(offset_ids)]
        if len(match):
            offset_ids.add(match.iloc[0]["OPPORTUNITY_ID"])
    adjustments = recent_won[recent_won["OPPORTUNITY_ID"].isin(offset_ids)]
    wins = recent_won[~recent_won["OPPORTUNITY_ID"].isin(offset_ids)]
    real_losses, zero_losses = recent_lost[recent_lost["ACV"] > 0], recent_lost[recent_lost["ACV"] <= 0]

    def other_quarter(item, kind):
        if not item:
            return "(not loaded)"
        label, other = item
        if other is None or other.empty:
            return f"{label}: no partner-attached opportunities."
        text = f"{label}: {summary_line(summary(other))}"
        if kind == "next":
            top = per_opportunity(other).query("STATUS == 'Open'").nlargest(5, "ACV")
            text += f"\nLargest open {label} deals:\n{deal_table(top)}"
        return text

    return f"""SCOPE: ACQ Theatre page — partner-attached opportunities credited to AMSAcquisition.
Close-date window: {period} | Customer region filter: {customer_region} | Today: {today:%b %d, %Y}
ACV is after partner and booking splits. PSE involved = a logged PSE activity OR partner comments on a linked
use case. Results reflect the viewer's Salesforce row access.

=== 1. BUSINESS HEALTH (headline figures — quote verbatim) ===
WINDOW TOTALS: {summary_line(total)}
PROJECTED WINDOW TOTAL if open pipeline converts at its weighted value (won ACV + weighted pipeline): {money(projected)}
PROJECTED vs PREVIOUS QUARTER WON ACV: {gap_text(projected, previous_total['won_acv']) if previous_total else 'n/a'}
THEATER CONTEXT: {theater_text}
OPEN DEALS CLOSING IN THE NEXT 14 DAYS: {len(soon):,} deals, {money(soon['ACV'].sum())}
OPEN DEALS PAST THEIR CLOSE DATE (hygiene): {len(overdue):,} deals, {money(overdue['ACV'].sum())}
PREVIOUS QUARTER (comparison): {other_quarter(previous, 'previous')}

BY CUSTOMER REGION:
{breakdown(regions, 'CUSTOMER_REGION', 'CUSTOMER_REGION')}

LATAM BY TERRITORY:
{breakdown(rows[rows['LATAM_TERRITORY'].notna()], 'LATAM_TERRITORY', 'TERRITORY')}

=== 2. PARTNERS INVOLVED ===
BY PARTNER TYPE:
{breakdown(rows, 'PARTNER_TYPE', 'PARTNER_TYPE')}

TOP PARTNERS BY WON ACV:
{partner_rank('won_acv')}

TOP PARTNERS BY OPEN PIPELINE:
{partner_rank('pipeline')}

MOST ACTIVE PARTNERS BY OPPORTUNITY COUNT:
{partner_rank('opps')}

=== 3. PSE ENGAGEMENT IMPACT ===
PSE INVOLVED: {summary_line(pse)}
NO PSE: {summary_line(no_pse)}
PSE share of opportunities: {pct(pse['opps'], total['opps'])} | PSE share of won ACV: {pct(pse['won_acv'], total['won_acv'])} | PSE share of open pipeline: {pct(pse['pipeline'], total['pipeline'])}
Average won deal — PSE involved: {money(avg_pse) if pd.notna(avg_pse) else 'n/a'} | no PSE: {money(avg_no_pse) if pd.notna(avg_no_pse) else 'n/a'} | multiple: {multiple}
MOST ACTIVE PSEs: {top_pses}
CUSTOMER REGIONS WITH ZERO PSE-INVOLVED OPPORTUNITIES: {', '.join(no_coverage) if no_coverage else '(none)'}
LARGEST WINS IN THE WINDOW (PSE column shows who was involved):
{deal_table(won_opps.nlargest(5, 'ACV'))}

=== 4. HIGH-STAKES DEALS (largest open deals in the window) ===
These {len(high)} deals total {money(high['ACV'].sum())}, {pct(high['ACV'].sum(), total['pipeline'])} of the open pipeline.
{len(high_uncovered)} of them have no PSE involved, totalling {money(high_uncovered['ACV'].sum())}, closing {high_uncovered['CLOSE'].min() if len(high_uncovered) else 'n/a'} to {high_uncovered['CLOSE'].max() if len(high_uncovered) else 'n/a'}: {', '.join(high_uncovered['CUSTOMER'].astype(str)) or '(none)'}
{deal_table(high)}

=== 5. LAST WEEK ({today - timedelta(days=RECENT_DAYS):%b %d} – {today - timedelta(days=1):%b %d}) ===
WINS (excluding booking adjustments): {len(wins):,} deals, {money(wins['ACV'].sum())}
WINS BEYOND THE LARGEST 6: {max(len(wins) - 6, 0):,} deals, {money(wins.iloc[6:]['ACV'].sum())}
{deal_table(wins)}
BOOKING ADJUSTMENTS (debooks, the rebooks they cancel, and $0 wins — already excluded from WINS; never count them as wins): {len(adjustments):,} rows, net {money(adjustments['ACV'].sum())}
{deal_table(adjustments) if len(adjustments) else ''}
LOSSES WITH ACV: {len(real_losses):,} deals, {money(real_losses['ACV'].sum())}
{deal_table(real_losses)}
$0 LOSSES (amendments / term extensions): {len(zero_losses):,}

=== 6. OUTLOOK ===
REST OF WINDOW: {len(open_opps):,} open deals, {money(open_opps['ACV'].sum())} ({money(open_opps['WEIGHTED'].sum())} weighted)
NEXT QUARTER: {other_quarter(following, 'next')}
"""


DEFAULT_PROMPT = """You are writing the ACQ THEATRE UPDATE: a weekly business readout on partner-attached opportunities in the AMSAcquisition theatre.

Audience: ACQ theatre leadership, partner leaders and PSE managers. They have 2 minutes. Be specific, concrete and declarative. No hedging, no filler, no methodology paragraph.

RULES ON NUMBERS
- Every figure MUST be copied verbatim from the DATA. Do NOT add, subtract, divide, average or rank anything yourself — every total, share, multiple and ranking you need is already computed.
- Name only real opportunities, customers, partners, PSEs and owners that appear in the DATA. Never invent a name or figure.
- Booking adjustments (debooks / rebooks with zero or negative ACV) are NOT wins. $0 amendment losses are NOT real losses.
- The partner-attached win rate is much higher than the theatre overall partly because partners are often attached to deals already progressing. Say so in one short clause when you compare the two; never claim partners cause the gap.
- PSEs go to the larger, strategic deals. When you cite the PSE average-deal multiple, state it as association, not causation.
- If a block says "(none)" or "(not loaded)", say so briefly or omit that point. Never fill the gap with guesses.

Produce EXACTLY these sections, in this order, with these headings, and nothing else.

# ACQ Theatre update
One italic line: the close-date window, the customer region filter and "as of" today's date.

## 1. Business health
- A markdown table comparing the window totals with the previous quarter: opportunities (won · lost · open), won ACV, open pipeline (weighted), win rate, partners involved. If the previous quarter is not loaded, show the window column only.
- Then 2–3 bullets: the projected window total and its gap to the previous quarter (use PROJECTED vs PREVIOUS QUARTER WON ACV as given); deals and ACV closing in the next 14 days; deals past their close date; the partner-attached share of theatre opportunities and the theatre win rate (with the caveat above).
- A table "By customer region": Region | Opps | Won ACV | Open pipeline | Win rate, in the order given.
- One bullet per LATAM territory with its won ACV, open pipeline and the most notable fact.

## 2. Partners involved
- One bullet on the partner type mix (won ACV and partner count per type).
- One bullet listing the top 5 partners by won ACV with their figures.
- One bullet on the most active partners by opportunity count.
- One bullet listing the top 5 partners by open pipeline.

## 3. PSE engagement impact
- A table: Metric | PSE involved | No PSE — opportunities, won ACV, average won deal, win rate, open pipeline.
- 3–4 bullets: PSE share of opportunities vs share of won ACV; the average-deal multiple (as association); which of the largest wins had a PSE, naming the PSE; the most active PSEs; the customer regions with zero PSE coverage.

## 4. High-stakes deals
- A table of the high-stakes deals: Opportunity | Region | Close | ACV | PSE | Partner, in the order given.
- 1–2 bullets: their combined ACV and share of the open pipeline, and the deals with no PSE (their count, total and close-date range exactly as given; call out those closing soonest).

## 5. Last week's wins
- One bolded line: the number of wins and total ACV, copied from the WINS line (booking adjustments are already excluded there).
- Bullets for the largest 6 wins from the WINS table (customer or opportunity, ACV, partner, and region/territory when LATAM), then one bullet summarizing the rest using the WINS BEYOND THE LARGEST 6 line as given.
- One line on losses with ACV (count, total, names), and a short note on $0 amendment losses and booking adjustments if any exist.

## 6. Outlook
- One bullet on the rest of the window: open deals and ACV, and which dated cluster of deals decides the outcome.
- One bullet on the next quarter: open opportunities, pipeline (weighted) and partners, then the largest deals with their partner and close date.
- "Asks:" as a short numbered list of 3–4 concrete actions drawn ONLY from the data, quoting its figures as given (e.g. PSE coverage on the named uncovered high-stakes deals, regions with zero PSE coverage with their won ACV and open pipeline, cleanup of overdue deals, early partner alignment on the largest next-quarter deal).

FORMATTING RULES
- Markdown headings, tables and bullets exactly as specified. Bold the single most important number in each section.
- Money as $XK or $X.XXM exactly as given in the DATA. Numbers with commas.
- Keep the whole update under 650 words, tables excluded.
- No greeting, no sign-off, no closing remarks, no extra sections."""
