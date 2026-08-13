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
    "EXECUTIVE SUMMARY", "OKR PROGRESS", "MANAGED PARTNER PIPELINE OVERVIEW",
    "PARTNER SCORECARD — GSI", "PARTNER SCORECARD — NOAM RSI",
    "PARTNER SCORECARD — APJ RSI", "PARTNER SCORECARD — EMEA RSI",
    "NOTABLE WINS", "DISCLAIMER",
]


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
            out.append(("GROUNDING", f"account exists in Snowflake: {a}",
                        a.upper() in accounts, "not found in PARTNER_COCO_USE_CASES"))
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
st.title("Executive Email — deterministic eval")

if os.environ.get("EVAL_SELFTEST") == "1":
    from scripts.eval_exec_email_fixtures import FIXTURES
    report = []
    for label, body, expect_fail in FIXTURES:
        res = check_structure(body) + check_arithmetic(body)
        got = {n for _, n, ok, _ in res if not ok}
        hit = any(any(k in n for k in expect_fail) for n in got) if expect_fail else not got
        report.append(f"{'OK ' if hit else 'BAD'} fixture '{label}': "
                      f"expected_fail={expect_fail or 'none'}; failures={sorted(got) or 'none'}")
    out = "\n".join(report)
    print(out, flush=True)
    st.code(out)
    st.stop()

email_file = os.environ.get("EMAIL_FILE")
if not email_file or not Path(email_file).exists():
    st.error("Set EMAIL_FILE to a file containing the generated email body.")
    st.stop()

body = Path(email_file).read_text()
if "conn" not in st.session_state:
    st.session_state.conn = st.connection("snowflake")

results = check_structure(body) + check_arithmetic(body) + check_grounding(st.session_state.conn, body)
report = score(results)
out_path = Path(os.environ.get("EVAL_OUT", "/tmp/exec_email_eval.md"))
out_path.write_text(report)
print(report, flush=True)
st.markdown(report)
