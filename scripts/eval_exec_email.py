"""Deterministic eval for the Executive Email output.

Scores a generated email body against three kinds of check, all pass/fail — no LLM
judge, no fuzzy scoring:

  STRUCTURE  required sections, disclaimer, banned calendar months in the OKR
             narrative, word budget
  ARITHMETIC every markdown table row must be internally consistent (CoCo <= Total,
             CoCo% == CoCo/Total), group rows must sum to the summary totals, and
             stated pipeline must equal Total - CoCo
  GROUNDING  every partner name and customer account name mentioned must exist in
             Snowflake, and weeks-remaining must match real date arithmetic

Usage (needs a Snowflake connection, so run under Streamlit like the other harness):

    EMAIL_FILE=/tmp/email.md streamlit run scripts/eval_exec_email.py \
        --server.port 8530 --server.headless true

Set EMAIL_FILE to a file containing the email body (paste the generated markdown).
Set EVAL_SELFTEST=1 to run built-in fixtures instead, which prove each check fires.
"""

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUARTER_END = os.environ.get("EVAL_QUARTER_END", "2026-10-31")
WORD_BUDGET = int(os.environ.get("EVAL_WORD_BUDGET", "2200"))
MONTHS = ("january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december",
          "jan ", "feb ", "mar ", "apr ", "jun ", "jul ", "aug", "sep", "oct", "nov", "dec")
REQUIRED_SECTIONS = [
    "EXECUTIVE SUMMARY", "NOTABLE WINS", "OKR PROGRESS", "MANAGED PARTNER PIPELINE OVERVIEW",
    "PARTNER SCORECARD — GSI", "PARTNER SCORECARD — NOAM RSI",
    "PARTNER SCORECARD — APJ RSI", "PARTNER SCORECARD — EMEA RSI",
    "DISCLAIMER",
]

# Expected section order (index = required position)
SECTION_ORDER = [
    "EXECUTIVE SUMMARY",
    "NOTABLE WINS",
    "OKR PROGRESS",
    "MANAGED PARTNER PIPELINE OVERVIEW",
    "PARTNER SCORECARD — GSI",
    "PARTNER SCORECARD — NOAM RSI",
    "PARTNER SCORECARD — APJ RSI",
    "PARTNER SCORECARD — EMEA RSI",
    "DISCLAIMER",
]

# Expected partner counts per scorecard group (canonical, deduplicated)
EXPECTED_PARTNER_COUNTS = {
    "GSI":      6,
    "NOAM RSI": 29,
    "APJ RSI":  5,
    "EMEA RSI": 4,
}

NOTABLE_WINS_GROUPS = ["GSI", "NOAM RSI", "APJ RSI", "EMEA RSI"]


# ── helpers ──────────────────────────────────────────────────────────────────
def _num(s):
    """'$1.7M' -> 1700000 ; '34.6%' -> 34.6 ; '1,234' -> 1234 ; else None."""
    if s is None:
        return None
    t = str(s).strip().replace(",", "").replace("$", "").replace("+", "")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)([KMB])?%?", t, re.IGNORECASE)
    if not m:
        return None
    v = float(m.group(1))
    mult = {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower())
    return v * mult if mult else v


def parse_tables(text):
    """Return [(header_cells, [row_cells, ...]), ...] for every markdown table."""
    tables, header, rows = [], None, []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue                      # separator row
            if header is None:
                header = cells
            else:
                rows.append(cells)
        else:
            if header is not None:
                tables.append((header, rows))
            header, rows = None, []
    if header is not None:
        tables.append((header, rows))
    return tables


def okr_narrative(text):
    """Text between the OKR table and the next heading."""
    m = re.search(r"##\s*OKR PROGRESS.*?\n(.*?)(?=\n##\s)", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    body = m.group(1)
    return "\n".join(l for l in body.splitlines() if not l.strip().startswith("|"))


def weeks_remaining(as_of=None):
    d = as_of or date.today()
    days = (datetime.strptime(QUARTER_END, "%Y-%m-%d").date() - d).days
    return max(0, -(-days // 7))


# ── checks ───────────────────────────────────────────────────────────────────
def check_structure(text):
    out = []
    for sec in REQUIRED_SECTIONS:
        out.append(("STRUCTURE", f"section present: {sec}", sec.lower() in text.lower(), ""))
    narr = okr_narrative(text)
    hits = [m for m in MONTHS if m in narr.lower()]
    out.append(("STRUCTURE", "no calendar months in OKR narrative", not hits, f"found {hits}"))
    wc = len(text.split())
    out.append(("STRUCTURE", f"word count <= {WORD_BUDGET}", wc <= WORD_BUDGET, f"{wc} words"))
    out.append(("STRUCTURE", "not truncated mid-table",
                not text.rstrip().endswith("|"), "body ends on a table row"))
    return out


def check_arithmetic(text):
    out = []
    for header, rows in parse_tables(text):
        h = [c.lower() for c in header]
        def idx(*names):
            for n in names:
                for i, c in enumerate(h):
                    if n in c:
                        return i
            return None
        i_total, i_coco, i_pct = idx("total uc"), idx("coco uc"), idx("coco %", "coco%")
        label = header[0]
        if i_total is None or i_coco is None:
            continue
        for r in rows:
            if max(i_total, i_coco) >= len(r):
                continue
            name = r[0]
            total, coco = _num(r[i_total]), _num(r[i_coco])
            if total is None or coco is None:
                continue
            out.append(("ARITHMETIC", f"{label} '{name}': CoCo <= Total",
                        coco <= total, f"{coco} > {total}"))
            if i_pct is not None and i_pct < len(r):
                pct = _num(r[i_pct])
                if pct is not None and total:
                    exp = round(coco * 100.0 / total, 1)
                    # Emails legitimately round to whole percent, so allow half a point.
                    ok = abs(pct - exp) <= 0.55 or round(pct) == round(exp)
                    out.append(("ARITHMETIC", f"{label} '{name}': CoCo% == CoCo/Total",
                                ok, f"stated {pct}, computed {exp}"))
    # pipeline figures quoted in the narrative must equal Total - CoCo from the OKR table
    narr = okr_narrative(text)
    okr = next((t for t in parse_tables(text)
                if any("coco uc" in c.lower() for c in t[0])), None)
    if okr and narr:
        h = [c.lower() for c in okr[0]]
        i_t = next((i for i, c in enumerate(h) if "total uc" in c), None)
        i_c = next((i for i, c in enumerate(h) if "coco uc" in c), None)
        if i_t is not None and i_c is not None:
            gap = sum((_num(r[i_t]) or 0) - (_num(r[i_c]) or 0) for r in okr[1]
                      if len(r) > max(i_t, i_c))
            stated = [_num(x) for x in re.findall(r"([\d,]+)\s+non-CoCo", narr)]
            for s in stated:
                out.append(("ARITHMETIC", "narrative pipeline == sum(Total - CoCo)",
                            s is not None and abs(s - gap) < 1, f"stated {s}, computed {gap}"))
    return out


def check_grounding(conn, text):
    out = []
    wk = weeks_remaining()
    stated_weeks = [_num(x) for x in re.findall(r"(\d+)\s+weeks? remaining", text, re.IGNORECASE)]
    for s in stated_weeks:
        out.append(("GROUNDING", "weeks remaining matches date arithmetic",
                    s == wk, f"stated {s}, computed {wk}"))
    if not stated_weeks:
        out.append(("GROUNDING", "weeks remaining stated", False, "not found in output"))

    try:
        known = conn.query("""
            SELECT DISTINCT UPPER(PARTNER_NAME) AS N
            FROM TEMP.COCO_PARTNER_ADOPTION.PARTNER_COCO_USE_CASES
            WHERE PARTNER_NAME IS NOT NULL
            UNION
            SELECT DISTINCT UPPER(PARTNER_NAME) FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES
            WHERE PARTNER_NAME IS NOT NULL
        """)["N"].tolist()
        accounts = conn.query("""
            SELECT DISTINCT UPPER(ACCOUNT_NAME) AS N
            FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES
            WHERE ACCOUNT_NAME IS NOT NULL
            UNION
            SELECT DISTINCT UPPER(ACCOUNT_NAME)
            FROM TEMP.COCO_PARTNER_ADOPTION.PARTNER_COCO_USE_CASES
            WHERE ACCOUNT_NAME IS NOT NULL
        """)["N"].tolist()
    except Exception as e:
        out.append(("GROUNDING", "load partner/account universe from Snowflake", False, str(e)[:160]))
        return out

    # partner names: first column of every scorecard table
    seen = set()
    for header, rows in parse_tables(text):
        if "partner" not in header[0].lower():
            continue
        for r in rows:
            nm = re.sub(r"\*+", "", r[0]).strip()
            if not nm or nm.lower() in ("partner", "group", "stage") or nm in seen:
                continue
            seen.add(nm)
            out.append(("GROUNDING", f"partner exists in Snowflake: {nm}",
                        nm.upper() in known, "not found in PARTNER_COCO_USE_CASES/DT_OKR"))

    # account names from NOTABLE WINS bullets: "... CoCo at <Account> —"
    wins = re.search(r"##\s*NOTABLE WINS(.*?)(?=\n##\s|$)", text, re.DOTALL | re.IGNORECASE)
    if wins:
        for acct in re.findall(r"(?:at|@)\s+([A-Z][^—\-\n,]{2,60}?)\s*[—\-]", wins.group(1)):
            a = acct.strip()
            # Skip if the name resolves to a known partner (false positive — LLM used partner as account)
            if a.upper() in known:
                continue
            out.append(("GROUNDING", f"account exists in Snowflake: {a}",
                        a.upper() in accounts, "not found in PARTNER_COCO_USE_CASES"))
    return out


def check_section_order(text):
    """Sections must appear in the prescribed sequence."""
    out = []
    positions = {}
    for sec in SECTION_ORDER:
        pos = text.upper().find(sec.upper())
        positions[sec] = pos  # -1 if absent

    for i in range(len(SECTION_ORDER) - 1):
        a, b = SECTION_ORDER[i], SECTION_ORDER[i + 1]
        pa, pb = positions[a], positions[b]
        if pa == -1 or pb == -1:
            continue  # section-present check is handled in check_structure
        out.append(("SECTION_ORDER", f"'{a}' before '{b}'",
                    pa < pb, f"positions: {a}={pa}, {b}={pb}"))
    return out


def _scorecard_rows(text, group_label):
    """Return data rows from the scorecard table for a given group label.

    Two-step: find the heading line that mentions both PARTNER SCORECARD and
    group_label (case-insensitive), then collect table rows until the next ##
    heading or end of string.  Avoids brittle single-regex matching of the
    em-dash and parenthetical suffix the LLM adds to the heading.
    """
    lines = text.splitlines()
    section_start = None
    label_lower = group_label.lower()

    for i, line in enumerate(lines):
        s = line.strip()
        if (s.startswith("##")
                and "partner scorecard" in s.lower()
                and label_lower in s.lower()):
            section_start = i + 1
            break

    if section_start is None:
        return []

    rows = []
    header = None
    for line in lines[section_start:]:
        s = line.strip()
        # Stop at next heading
        if s.startswith("##"):
            break
        if not (s.startswith("|") and s.endswith("|")):
            if header:
                break  # table ended, trailing narrative
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue  # separator row
        if header is None:
            header = cells
        else:
            rows.append(cells)
    return rows


def check_completeness(text):
    """Every scorecard must have the exact expected number of partner rows."""
    out = []
    for group, expected in EXPECTED_PARTNER_COUNTS.items():
        rows = _scorecard_rows(text, group)
        # Filter out any non-data rows (e.g. summary/total rows)
        data_rows = [r for r in rows if r and r[0].strip() not in ("", "Partner", "Group")]
        actual = len(data_rows)
        out.append(("COMPLETENESS", f"{group} scorecard: {expected} partner rows",
                    actual == expected,
                    f"found {actual}, expected {expected}"))
    return out


def check_cross_table(text):
    """Sum of all scorecard partner rows must match the OKR regional breakdown table."""
    out = []

    # Extract OKR regional breakdown (the first table with Total UCs + CoCo UCs columns)
    okr_table = None
    for header, rows in parse_tables(text):
        h = [c.lower() for c in header]
        if any("total uc" in c for c in h) and any("coco uc" in c for c in h):
            okr_table = (header, rows)
            break

    if not okr_table:
        out.append(("CROSS_TABLE", "OKR regional breakdown table found", False, "table not found"))
        return out

    h = [c.lower() for c in okr_table[0]]
    i_total = next((i for i, c in enumerate(h) if "total uc" in c), None)
    i_coco  = next((i for i, c in enumerate(h) if "coco uc" in c), None)
    if i_total is None or i_coco is None:
        out.append(("CROSS_TABLE", "OKR table has Total UCs + CoCo UCs columns", False, "columns missing"))
        return out

    okr_total = sum(_num(r[i_total]) or 0 for r in okr_table[1] if len(r) > max(i_total, i_coco))
    okr_coco  = sum(_num(r[i_coco])  or 0 for r in okr_table[1] if len(r) > max(i_total, i_coco))

    # Sum partner rows across all four scorecards
    sc_total = sc_coco = 0
    for group in EXPECTED_PARTNER_COUNTS:
        for row in _scorecard_rows(text, group):
            if len(row) < 3:
                continue
            # Total UCs = col 1, CoCo UCs = col 2 (standard scorecard layout)
            sc_total += _num(row[1]) or 0
            sc_coco  += _num(row[2]) or 0

    if okr_total > 0:
        out.append(("CROSS_TABLE", "scorecard Total UCs sum ≈ OKR table Total UCs",
                    abs(sc_total - okr_total) <= 5,
                    f"scorecard sum={sc_total:.0f}, OKR table={okr_total:.0f}"))
    if okr_coco > 0:
        out.append(("CROSS_TABLE", "scorecard CoCo UCs sum ≈ OKR table CoCo UCs",
                    abs(sc_coco - okr_coco) <= 5,
                    f"scorecard sum={sc_coco:.0f}, OKR table={okr_coco:.0f}"))
    return out


def check_notable_wins(text):
    """Notable Wins section: 1-4 bullets (groups without a win are omitted),
    correct format, and ONLY Stage 7/6/4 use cases mentioned."""
    out = []
    m = re.search(r"##\s*NOTABLE WINS(.*?)(?=\n##\s|$)", text, re.DOTALL | re.IGNORECASE)
    if not m:
        out.append(("NOTABLE_WINS", "NOTABLE WINS section present", False, "section not found"))
        return out

    section = m.group(1)
    bullets  = [l.strip() for l in section.splitlines() if l.strip().startswith("-")]

    out.append(("NOTABLE_WINS", "at least 1 win bullet present",
                len(bullets) >= 1, f"found {len(bullets)} bullets"))

    # No "No notable win" placeholders allowed — groups should be omitted instead
    for b in bullets:
        has_placeholder = bool(re.search(r"no\s+notable\s+win", b, re.IGNORECASE))
        out.append(("NOTABLE_WINS", f"no placeholder bullet: {b[:60]}",
                    not has_placeholder,
                    "group with no win should be omitted, not shown as 'No notable win'"))

    # Format check: each bullet should have a partner name in bold + "CoCo at"
    for b in bullets:
        has_bold   = bool(re.search(r"\*\*.+\*\*", b))
        has_anchor = bool(re.search(r"coco\s+at", b, re.IGNORECASE))
        out.append(("NOTABLE_WINS", f"bullet format valid: {b[:60]}",
                    has_bold and has_anchor,
                    "expected '**Partner**... CoCo at Account'"))

    # Stage check: only Stage 7 Deployed or Stage 4 Won may appear — no other stages
    _FORBIDDEN_STAGES = re.compile(
        r"stage\s*[35]\b|implementation\s+in\s+progress"
        r"|tech(?:nical)?[/ ]+biz|validation|in\s+progress",
        re.IGNORECASE,
    )
    _ALLOWED_STAGES = re.compile(
        r"stage\s*7|deployed|stage\s*6|implementation\s+complete|stage\s*4|won|migration\s+plan|no\s+notable\s+win",
        re.IGNORECASE,
    )
    for b in bullets:
        if re.search(r"no\s+notable\s+win", b, re.IGNORECASE):
            continue  # placeholder bullet — no stage to check
        has_forbidden = bool(_FORBIDDEN_STAGES.search(b))
        has_allowed   = bool(_ALLOWED_STAGES.search(b))
        out.append(("NOTABLE_WINS", f"only Deployed/Won stage in bullet: {b[:60]}",
                    has_allowed and not has_forbidden,
                    "bullet references a non-Deployed/Won stage (only Stage 7 or Stage 4 allowed)"))

    return out


def score(results):
    lines = ["# Executive Email — deterministic eval", "",
             f"Run: {datetime.now().isoformat(timespec='seconds')}", ""]
    cats = {}
    for cat, _, ok, _ in results:
        c = cats.setdefault(cat, [0, 0])
        c[1] += 1
        c[0] += 1 if ok else 0
    lines += ["| Category | Passed | Total | Score |", "|---|---|---|---|"]
    tp = tt = 0
    for cat, (p, t) in cats.items():
        tp, tt = tp + p, tt + t
        lines.append(f"| {cat} | {p} | {t} | {100.0*p/t:.0f}% |")
    lines.append(f"| **OVERALL** | **{tp}** | **{tt}** | **{100.0*tp/tt if tt else 0:.0f}%** |")
    fails = [r for r in results if not r[2]]
    lines += ["", f"## Failures ({len(fails)})", ""]
    if not fails:
        lines.append("None.")
    for cat, name, _, detail in fails:
        lines.append(f"- **[{cat}]** {name} — {detail}")
    lines += ["", "## All checks", ""]
    for cat, name, ok, detail in results:
        lines.append(f"- {'PASS' if ok else 'FAIL'} [{cat}] {name}"
                     + (f" — {detail}" if not ok else ""))
    return "\n".join(lines)


# ── run ──────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Exec email eval", layout="wide")
st.subheader("Executive Email — deterministic eval")

if os.environ.get("EVAL_SELFTEST") == "1":
    from scripts.eval_exec_email_fixtures import FIXTURES
    report = []
    for label, body, expect_fail in FIXTURES:
        res = (check_structure(body) + check_arithmetic(body)
               + check_section_order(body) + check_completeness(body)
               + check_cross_table(body) + check_notable_wins(body))
        got = {n for _, n, ok, _ in res if not ok}
        hit = any(any(k in n for k in expect_fail) for n in got) if expect_fail else not got
        report.append(f"{'OK ' if hit else 'BAD'} fixture '{label}': "
                      f"expected_fail={expect_fail or 'none'}; failures={sorted(got) or 'none'}")
    out = "\n".join(report)
    print(out, flush=True)
    st.code(out)
    st.stop()

    out = "\n".join(report)
    print(out, flush=True)
    st.code(out)
    st.stop()

if __name__ == "__main__" or os.environ.get("EMAIL_FILE"):
    email_file = os.environ.get("EMAIL_FILE")
    if not email_file or not Path(email_file).exists():
        st.error("Set EMAIL_FILE to a file containing the generated email body.")
        st.stop()

    body = Path(email_file).read_text()
    if "conn" not in st.session_state:
        st.session_state.conn = st.connection("snowflake")

    results = (check_structure(body) + check_arithmetic(body) + check_grounding(st.session_state.conn, body)
               + check_section_order(body) + check_completeness(body)
               + check_cross_table(body) + check_notable_wins(body))
    report = score(results)
    out_path = Path(os.environ.get("EVAL_OUT", "/tmp/exec_email_eval.md"))
    out_path.write_text(report)
    print(report, flush=True)
    st.markdown(report)
