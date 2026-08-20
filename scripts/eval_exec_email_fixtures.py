"""Fixtures for eval_exec_email self-test.

Each entry is (label, email_body, expected_failure_substrings). An empty expectation
means the body should pass every check. These exist to prove the checks actually
fire — a checker that silently passes everything is worthless.
"""

# ── Shared building blocks ─────────────────────────────────────────────────────

_GOOD_TABLE = """| Group | Scope | Total Partners | Total UCs | CoCo UCs | CoCo % |
|---|---|---|---|---|---|
| GSI | Global | 6 | 280 | 97 | 34.6% |
| NOAM RSI | NoAM | 29 | 256 | 108 | 42.2% |
| APJ RSI | APJ geo | 5 | 30 | 10 | 33.3% |
| EMEA RSI | EMEA geo | 4 | 18 | 8 | 44.4% |"""

# 280-97 + 256-108 + 30-10 + 18-8 = 183 + 148 + 20 + 10 = 361
_GOOD_NARRATIVE = ("With 12 weeks remaining, the trend is increasing by 7.5%. The "
                   "convertible pipeline includes 361 non-CoCo use cases still open.")

_GOOD_NOTABLE_WINS = """## NOTABLE WINS (managed partners only)
- **GSI Accenture** deployed CoCo at Proquire Plus Inc. — Stage 7, $100K EACV
- **NOAM RSI phData** deployed CoCo at Snowtek Corp. — Stage 7, $50K EACV
- **APJ RSI NTT DATA** deployed CoCo at Sumitomo Corp. — Stage 7, $30K EACV
- **EMEA RSI Kubrick** deployed CoCo at BritishTelecom Ltd. — Stage 7, $20K EACV
"""


def _scorecard(group_heading, n, col1_prefix="Partner"):
    rows = "\n".join(
        f"| {col1_prefix}{i} | 10 | 4 | 40.0% | - | - | $100K | 2 | 1 | 1 | 1.0B | $500 | $50 | +5% |"
        for i in range(1, n + 1)
    )
    return (
        f"## {group_heading}\n"
        "| Partner | Total UCs | CoCo UCs | CoCo% | WoW Δ% | WoW Δ UCs | EACV |"
        " AI | DE | Analytics | Q3 Tokens | Q3 Credits | Last 7d Credits | 7D Credits WoW% |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        f"{rows}\n"
    )


def _okr_table_from_counts(gsi_n, noam_n, apj_n, emea_n, ucs_per=10, coco_per=4):
    """Generate an OKR table that matches the dummy scorecard row counts exactly."""
    rows = [
        ("GSI",      "Global",   gsi_n,  gsi_n  * ucs_per, gsi_n  * coco_per),
        ("NOAM RSI", "NoAM",     noam_n, noam_n * ucs_per, noam_n * coco_per),
        ("APJ RSI",  "APJ geo",  apj_n,  apj_n  * ucs_per, apj_n  * coco_per),
        ("EMEA RSI", "EMEA geo", emea_n, emea_n * ucs_per, emea_n * coco_per),
    ]
    lines = ["| Group | Scope | Total Partners | Total UCs | CoCo UCs | CoCo % |",
             "|---|---|---|---|---|---|"]
    for grp, scope, n, total, coco in rows:
        pct = round(coco * 100.0 / total, 1) if total else 0
        lines.append(f"| {grp} | {scope} | {n} | {total} | {coco} | {pct}% |")
    return "\n".join(lines)


def _pipeline_from_counts(gsi_n, noam_n, apj_n, emea_n, ucs_per=10, coco_per=4):
    """Non-CoCo pipeline that reconciles with the OKR table."""
    gap = (gsi_n + noam_n + apj_n + emea_n) * (ucs_per - coco_per)
    return (f"With 12 weeks remaining, the trend is increasing by 7.5%. The "
            f"convertible pipeline includes {gap} non-CoCo use cases still open.")


def _full_email(table=None, narrative=None, gsi_n=6, noam_n=29, apj_n=5, emea_n=4,
                notable_wins=None, swap_order=False):
    t = table if table is not None else _okr_table_from_counts(gsi_n, noam_n, apj_n, emea_n)
    n = narrative if narrative is not None else _pipeline_from_counts(gsi_n, noam_n, apj_n, emea_n)
    w = notable_wins if notable_wins is not None else _GOOD_NOTABLE_WINS

    exec_sum  = "## EXECUTIVE SUMMARY\n231 CoCo use cases across 44 managed partners.\n\n"
    okr       = f"## OKR PROGRESS — REGIONAL BREAKDOWN\n{t}\n\n{n}\n\n"
    pipeline  = ("## MANAGED PARTNER PIPELINE OVERVIEW\n"
                 "| Stage | Total UCs | CoCo UCs |\n|---|---|---|\n| Stage 7 | 100 | 40 |\n\n")
    scorecards = (
        _scorecard("PARTNER SCORECARD — GSI (Global, all regions, target 75%)", gsi_n)  + "\n"
        + _scorecard("PARTNER SCORECARD — NOAM RSI (NoAM only, target 75%)", noam_n, "RSI")  + "\n"
        + _scorecard("PARTNER SCORECARD — APJ RSI (APJ geo-restricted, target 50%)", apj_n, "APJ") + "\n"
        + _scorecard("PARTNER SCORECARD — EMEA RSI (EMEA geo-restricted, target 50%)", emea_n, "EMEA") + "\n"
    )
    disclaimer = "## DISCLAIMER\n**Disclaimer:** sourced from SE comments.\n"

    if swap_order:
        # NOTABLE WINS placed AFTER scorecards instead of after exec summary
        return exec_sum + okr + pipeline + scorecards + w + disclaimer

    return exec_sum + w + okr + pipeline + scorecards + disclaimer


# ── Derived bad tables (for arithmetic checks — use explicit values) ──────────
_BASE_TABLE = _okr_table_from_counts(6, 29, 5, 4)   # matches default _full_email

_BAD_PCT_TABLE = _BASE_TABLE.replace(
    "| GSI | Global | 6 | 60 | 24 | 40.0% |",
    "| GSI | Global | 6 | 60 | 24 | 61.0% |")

_COCO_GT_TOTAL = _BASE_TABLE.replace(
    "| APJ RSI | APJ geo | 5 | 50 | 20 | 40.0% |",
    "| APJ RSI | APJ geo | 5 | 50 | 99 | 40.0% |")

# ── Fixtures ──────────────────────────────────────────────────────────────────

FIXTURES = [
    # ── Baseline ──────────────────────────────────────────────────────────────
    ("clean email — all checks should pass",
     _full_email(),
     []),

    # ── Arithmetic ────────────────────────────────────────────────────────────
    ("wrong CoCo percentage",
     _full_email(table=_BAD_PCT_TABLE),
     ["CoCo% == CoCo/Total"]),

    ("CoCo exceeds total",
     _full_email(table=_COCO_GT_TOTAL),
     ["CoCo <= Total"]),

    ("pipeline total does not reconcile",
     _full_email(narrative="With 12 weeks remaining, the convertible pipeline "
                           "includes 9999 non-CoCo use cases still open."),
     ["narrative pipeline"]),

    # ── Structure ─────────────────────────────────────────────────────────────
    ("calendar month leaked into OKR narrative",
     _full_email(narrative="Through August and October we are trending up by 7.5%."),
     ["no calendar months"]),

    ("missing disclaimer",
     _full_email().replace(
         "## DISCLAIMER\n**Disclaimer:** sourced from SE comments.\n", ""),
     ["DISCLAIMER"]),

    ("truncated mid-table",
     _full_email().split("## MANAGED PARTNER")[0].rstrip() + "\n| EMEA RSI | EMEA geo | 4 | 18 | 8 |",
     ["not truncated"]),

    # ── Section order ─────────────────────────────────────────────────────────
    ("notable wins placed after scorecards instead of after exec summary",
     _full_email(swap_order=True),
     ["'NOTABLE WINS' before 'OKR PROGRESS'"]),

    # ── Partner completeness ──────────────────────────────────────────────────
    ("GSI scorecard has 5 rows instead of 6",
     _full_email(gsi_n=5),
     ["GSI scorecard: 6 partner rows"]),

    ("APJ scorecard has 3 rows instead of 5",
     _full_email(apj_n=3),
     ["APJ RSI scorecard: 5 partner rows"]),

    ("EMEA scorecard has 2 rows instead of 4",
     _full_email(emea_n=2),
     ["EMEA RSI scorecard: 4 partner rows"]),

    ("NOAM scorecard has 25 rows instead of 29",
     _full_email(noam_n=25),
     ["NOAM RSI scorecard: 29 partner rows"]),

    # ── Notable wins ──────────────────────────────────────────────────────────
    ("notable wins section missing EMEA bullet",
     _full_email(notable_wins=(
         "## NOTABLE WINS (managed partners only)\n"
         "- **GSI Accenture** deployed CoCo at Proquire Plus Inc. — Stage 7, $100K EACV\n"
         "- **NOAM RSI phData** deployed CoCo at Snowtek Corp. — Stage 7, $50K EACV\n"
         "- **APJ RSI NTT DATA** deployed CoCo at Sumitomo Corp. — Stage 7, $30K EACV\n"
     )),
     ["exactly 4 win bullets", "EMEA RSI"]),

    ("notable wins bullets lack bold partner name",
     _full_email(notable_wins=(
         "## NOTABLE WINS (managed partners only)\n"
         "- GSI Accenture deployed CoCo at Proquire Plus Inc. — Stage 7, $100K EACV\n"
         "- NOAM RSI phData deployed CoCo at Snowtek Corp. — Stage 7, $50K EACV\n"
         "- APJ RSI NTT DATA deployed CoCo at Sumitomo Corp. — Stage 7, $30K EACV\n"
         "- EMEA RSI Kubrick deployed CoCo at BritishTelecom Ltd. — Stage 7, $20K EACV\n"
     )),
     ["bullet format valid"]),

    ("notable wins bullet references wrong stage (implementation in progress — Stage 5)",
     _full_email(notable_wins=(
         "## NOTABLE WINS (managed partners only)\n"
         "- **GSI Accenture** deployed CoCo at Proquire Plus Inc. — Stage 5 Implementation In Progress, $100K EACV\n"
         "- **NOAM RSI phData** deployed CoCo at Snowtek Corp. — Stage 7, $50K EACV\n"
         "- **APJ RSI NTT DATA** deployed CoCo at Sumitomo Corp. — Stage 7, $30K EACV\n"
         "- **EMEA RSI Kubrick** deployed CoCo at BritishTelecom Ltd. — Stage 7, $20K EACV\n"
     )),
     ["only Deployed/Won stage"]),

    ("notable wins bullet with stage 6 implementation complete — should pass",
     _full_email(notable_wins=(
         "## NOTABLE WINS (managed partners only)\n"
         "- **GSI Accenture** deployed CoCo at Proquire Plus Inc. — Stage 6 Implementation Complete, $100K EACV\n"
         "- **NOAM RSI phData** deployed CoCo at Snowtek Corp. — Stage 7, $50K EACV\n"
         "- **APJ RSI NTT DATA** deployed CoCo at Sumitomo Corp. — Stage 7, $30K EACV\n"
         "- **EMEA RSI Kubrick** deployed CoCo at BritishTelecom Ltd. — Stage 7, $20K EACV\n"
     )),
     []),  # Stage 6 is now allowed — should pass all checks

    ("notable wins bullet references validation stage",
     _full_email(notable_wins=(
         "## NOTABLE WINS (managed partners only)\n"
         "- **GSI Accenture** deployed CoCo at Proquire Plus Inc. — Technical Validation, $100K EACV\n"
         "- **NOAM RSI phData** deployed CoCo at Snowtek Corp. — Stage 7, $50K EACV\n"
         "- **APJ RSI NTT DATA** deployed CoCo at Sumitomo Corp. — Stage 7, $30K EACV\n"
         "- **EMEA RSI Kubrick** deployed CoCo at BritishTelecom Ltd. — Stage 7, $20K EACV\n"
     )),
     ["only Deployed/Won stage"]),
]
