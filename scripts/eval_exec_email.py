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


def check_industry_narrative(text, industry_data=None, overall_coco_pct=None):
    """Pipeline by Industry narrative checks (only runs when industry_data is provided):
    1. CoCo % per industry must match pre-computed coco_pct (±3pp)
    2. UC counts per industry must match total_ucs (±5 UCs tolerance for rounding)
    3. No % figures appear that cannot be tied to a known industry or the overall average
    4. Overall managed CoCo % must match pre-computed value (±3pp)
    """
    out = []
    if industry_data is None or len(industry_data) == 0:
        return out  # tab not selected or data unavailable — skip

    # Find the OKR Regional Breakdown section where the industry narrative appears.
    # If no section header exists (e.g. UC Insights bullet output), check the full text.
    section_m = re.search(
        r"##\s*OKR PROGRESS.*?REGIONAL BREAKDOWN(.*?)(?=\n##\s|$)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if section_m:
        section = section_m.group(1)
    else:
        section = text  # UC Insights: entire response is the industry narrative
    pct_pattern = re.compile(r'(\d{1,3}(?:\.\d)?)\s*%')
    num_pattern = re.compile(r'\b(\d{1,4})\b')

    # Build lookups keyed by lowercase industry name
    known_pcts  = {str(r['ACCOUNT_INDUSTRY']).lower(): float(r['COCO_PCT'])   for _, r in industry_data.iterrows()}
    known_total = {str(r['ACCOUNT_INDUSTRY']).lower(): int(r['TOTAL_UCS'])    for _, r in industry_data.iterrows()}
    known_coco  = {str(r['ACCOUNT_INDUSTRY']).lower(): int(r['COCO_UCS'])     for _, r in industry_data.iterrows()}
    industry_names = list(industry_data['ACCOUNT_INDUSTRY'].dropna().unique())
    known_names_lower = {n.lower() for n in industry_names}

    sentences = re.split(r'(?<=[.!?])\s+', section)

    # 1. CoCo % per industry must be grounded (±3pp)
    for ind_name in industry_names:
        ind_lower = ind_name.lower()
        for sent in sentences:
            if ind_lower not in sent.lower():
                continue
            for m in pct_pattern.finditer(sent):
                stated_pct = float(m.group(1))
                expected   = known_pcts.get(ind_lower)
                if expected is None:
                    continue
                out.append((
                    "INDUSTRY_NARRATIVE",
                    f"{ind_name} CoCo% grounded: stated {stated_pct}% vs data {expected}%",
                    abs(stated_pct - expected) <= 3.0,
                    f"stated {stated_pct}% deviates >3pp from pre-computed {expected}%",
                ))

    # 2. UC counts per industry must be grounded (±5 UCs)
    # Only check sentences that explicitly mention "use case", "UC", or "deal" counts
    # Skip numbers adjacent to $ or followed by M/K/% (EACV values)
    _dollar_adj = re.compile(r'\$\s*\d|[\d]\s*[MKmk%]')
    for ind_name in industry_names:
        ind_lower = ind_name.lower()
        for sent in sentences:
            if ind_lower not in sent.lower():
                continue
            # Only check sentences that are talking about counts, not EACV
            if not re.search(r'\buse\s*case|\bUC\b|\bdeals?\b|\baccounts?\b', sent, re.I):
                continue
            for m in num_pattern.finditer(sent):
                n = int(m.group(1))
                if not (5 <= n <= 500):
                    continue
                # Skip if the number appears to be part of an EACV/currency figure
                start = m.start()
                surrounding = sent[max(0, start-2):m.end()+2]
                if re.search(r'[\$MKmk%]', surrounding):
                    continue
                total = known_total.get(ind_lower, 0)
                coco  = known_coco.get(ind_lower, 0)
                if abs(n - total) <= 5 or abs(n - coco) <= 5:
                    continue  # matches — OK
                out.append((
                    "INDUSTRY_NARRATIVE",
                    f"{ind_name} UC count grounded: stated {n} vs total={total}/coco={coco}",
                    False,
                    f"stated {n} UCs doesn't match total={total} or coco={coco} (±5 tolerance)",
                ))

    # 3. No % figures without a known industry name or overall average nearby
    for sent in sentences:
        if not pct_pattern.search(sent):
            continue
        has_known_ind = any(n in sent.lower() for n in known_names_lower)
        has_overall   = bool(re.search(r'overall|average|managed\s+average|adoption\s+rate', sent, re.I))
        if not has_known_ind and not has_overall:
            out.append(("INDUSTRY_NARRATIVE",
                        f"% tied to known industry or overall avg: {sent[:80]}",
                        False,
                        "percentage in narrative cannot be tied to any industry in data block"))

    # 4. Overall managed CoCo % must be grounded (±3pp)
    if overall_coco_pct is not None:
        for sent in sentences:
            if not re.search(r'overall|average|managed\s+average', sent, re.I):
                continue
            for m in pct_pattern.finditer(sent):
                stated = float(m.group(1))
                out.append((
                    "INDUSTRY_NARRATIVE",
                    f"overall managed CoCo% grounded: stated {stated}% vs data {overall_coco_pct}%",
                    abs(stated - overall_coco_pct) <= 3.0,
                    f"stated {stated}% deviates >3pp from pre-computed overall {overall_coco_pct}%",
                ))

    if not out:
        out.append(("INDUSTRY_NARRATIVE", "industry figures checked", True,
                    "no industry-specific figures found to verify"))
    return out


def check_velocity_narrative(text, velocity_ctx: dict | None = None):
    """Pipeline Velocity narrative checks (only runs when velocity_ctx is provided):
    1. Partners-meeting count is stated and matches pre-computed value (±1)
    2. Partners-below count matches (±1)
    3. Partners-within-threshold count matches (±1)
    4. Weeks-remaining figure matches today's real date arithmetic (±1 week)
    """
    out = []
    if not velocity_ctx:
        return out
    pct_pat = re.compile(r'\b(\d{1,3}(?:\.\d)?)\s*%')
    num_pat = re.compile(r'\b(\d{1,3})\b')

    # 1. Partners meeting target
    expected_meeting = int(velocity_ctx.get('partners_meeting', -1))
    expected_below   = int(velocity_ctx.get('partners_below', -1))
    expected_close   = int(velocity_ctx.get('partners_close', -1))
    expected_weeks   = float(velocity_ctx.get('weeks_remaining', -1))

    nums = [int(m.group(1)) for m in num_pat.finditer(text)]

    if expected_meeting >= 0:
        close_match = any(abs(n - expected_meeting) <= 1 for n in nums)
        out.append(("VELOCITY", f"partners meeting target ({expected_meeting}) mentioned", close_match,
                    f"expected ~{expected_meeting} in text"))

    if expected_below >= 0:
        close_match = any(abs(n - expected_below) <= 1 for n in nums)
        out.append(("VELOCITY", f"partners below target ({expected_below}) mentioned", close_match,
                    f"expected ~{expected_below} in text"))

    if expected_close >= 0:
        close_match = any(abs(n - expected_close) <= 1 for n in nums)
        out.append(("VELOCITY", f"partners within 1-2 UCs of threshold ({expected_close}) mentioned", close_match,
                    f"expected ~{expected_close} in text"))

    # 2. Weeks remaining ±1
    if expected_weeks >= 0:
        wk_match = any(abs(float(m.group(1)) - expected_weeks) <= 1.5 for m in re.finditer(r'\b(\d{1,2}(?:\.\d)?)\b', text))
        out.append(("VELOCITY", f"weeks remaining (~{expected_weeks}) mentioned", wk_match,
                    f"expected ~{expected_weeks} weeks in text"))

    return out


def check_eacv_conversion(text, eacv_ctx: dict | None = None):
    """EACV Conversion narrative checks (only runs when eacv_ctx is provided):
    1. Total unconverted EACV is stated and within ±10% of pre-computed value
    2. Stage-5 EACV stated within ±10%
    3. Total non-CoCo UC count mentioned within ±5
    4. No unanchored large EACV figure appears (>10% deviation from any known value)
    """
    out = []
    if not eacv_ctx:
        return out

    total_eacv  = float(eacv_ctx.get('total_eacv_m', -1))
    stage5_eacv = float(eacv_ctx.get('stage5_eacv_m', -1))
    total_ucs   = int(eacv_ctx.get('total_ucs', -1))

    dollar_pat = re.compile(r'\$(\d+(?:\.\d+)?)\s*([MKmk]?)')

    def _to_m(val, suffix):
        suffix = suffix.upper()
        if suffix == 'M': return float(val)
        if suffix == 'K': return float(val) / 1000
        return float(val) / 1_000_000

    stated_eacvs = [_to_m(m.group(1), m.group(2)) for m in dollar_pat.finditer(text)]

    if total_eacv > 0 and stated_eacvs:
        best = min(abs(v - total_eacv) / total_eacv for v in stated_eacvs)
        out.append(("EACV_CONVERSION", f"total unconverted EACV (~${total_eacv}M) grounded",
                    best <= 0.10, f"closest stated value deviates {round(best*100)}% from ${total_eacv}M"))

    if stage5_eacv > 0 and stated_eacvs:
        best = min(abs(v - stage5_eacv) / max(stage5_eacv, 0.01) for v in stated_eacvs)
        out.append(("EACV_CONVERSION", f"Stage-5 EACV (~${stage5_eacv}M) grounded",
                    best <= 0.10, f"closest stated value deviates {round(best*100)}% from ${stage5_eacv}M"))

    if total_ucs > 0:
        nums = [int(m.group(1)) for m in re.finditer(r'\b(\d{2,3})\b', text)]
        out.append(("EACV_CONVERSION", f"non-CoCo UC count (~{total_ucs}) mentioned",
                    any(abs(n - total_ucs) <= 5 for n in nums),
                    f"expected ~{total_ucs} UCs in text"))

    return out


def check_stalled_pipeline(text, stall_ctx: dict | None = None):
    """Stalled Pipeline narrative checks (only runs when stall_ctx is provided):
    1. >180-day stalled count mentioned within ±2
    2. >180-day stalled EACV within ±10%
    3. 90-180-day stalled count mentioned within ±2
    4. At least one top stalled account name mentioned (basic grounding)
    """
    out = []
    if not stall_ctx:
        return out

    count180    = int(stall_ctx.get('count180', -1))
    eacv180     = float(stall_ctx.get('eacv180_m', -1))
    count90_180 = int(stall_ctx.get('count90_180', -1))
    top_accounts = stall_ctx.get('top_accounts', [])

    nums = [int(m.group(1)) for m in re.finditer(r'\b(\d{1,3})\b', text)]

    if count180 >= 0:
        out.append(("STALLED_PIPELINE", f">180d stalled count ({count180}) mentioned",
                    any(abs(n - count180) <= 2 for n in nums),
                    f"expected ~{count180} in text"))

    if eacv180 > 0:
        dollar_pat = re.compile(r'\$(\d+(?:\.\d+)?)\s*([MKmk]?)')
        def _to_m(val, suffix):
            s = suffix.upper()
            if s == 'M': return float(val)
            if s == 'K': return float(val) / 1000
            return float(val) / 1_000_000
        stated = [_to_m(m.group(1), m.group(2)) for m in dollar_pat.finditer(text)]
        best = min((abs(v - eacv180) / max(eacv180, 0.01) for v in stated), default=1.0)
        out.append(("STALLED_PIPELINE", f">180d stalled EACV (~${eacv180}M) grounded",
                    best <= 0.10, f"closest stated deviates {round(best*100)}% from ${eacv180}M"))

    if count90_180 >= 0:
        out.append(("STALLED_PIPELINE", f"90-180d stalled count ({count90_180}) mentioned",
                    any(abs(n - count90_180) <= 2 for n in nums),
                    f"expected ~{count90_180} in text"))

    if top_accounts:
        found = any(acct.lower() in text.lower() for acct in top_accounts)
        out.append(("STALLED_PIPELINE", "at least one top stalled account named", found,
                    f"none of {top_accounts[:3]} found in output"))

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
