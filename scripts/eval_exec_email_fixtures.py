"""Fixtures for eval_exec_email self-test.

Each entry is (label, email_body, expected_failure_substrings). An empty expectation
means the body should pass every structural and arithmetic check. These exist to prove
the checks actually fire — a checker that silently passes everything is worthless.
"""

_SECTIONS = """## EXECUTIVE SUMMARY
Some summary text.

## OKR PROGRESS — REGIONAL BREAKDOWN
{table}

{narrative}

## MANAGED PARTNER PIPELINE OVERVIEW
text

## PARTNER SCORECARD — GSI
text

## PARTNER SCORECARD — NOAM RSI
text

## PARTNER SCORECARD — APJ RSI
text

## PARTNER SCORECARD — EMEA RSI
text

## NOTABLE WINS
- **GSI Accenture** deployed CoCo at Proquire Plus Inc. — Stage 7, $100K EACV

## DISCLAIMER
**Disclaimer:** sourced from SE comments.
"""

_GOOD_TABLE = """| Group | Scope | Total UCs | CoCo UCs | CoCo % |
|---|---|---|---|---|
| GSI | Global | 280 | 97 | 34.6% |
| NOAM RSI | NoAM | 256 | 108 | 42.2% |
| APJ RSI | APJ geo | 30 | 10 | 33.3% |
| EMEA RSI | EMEA geo | 18 | 8 | 44.4% |"""

# 280-97 + 256-108 + 30-10 + 18-8 = 183 + 148 + 20 + 10 = 361
_GOOD_NARRATIVE = ("With 12 weeks remaining, the trend is increasing by 7.5%. The "
                   "convertible pipeline includes 361 non-CoCo use cases still open.")

_BAD_PCT_TABLE = _GOOD_TABLE.replace("| GSI | Global | 280 | 97 | 34.6% |",
                                     "| GSI | Global | 280 | 97 | 61.0% |")
_COCO_GT_TOTAL = _GOOD_TABLE.replace("| APJ RSI | APJ geo | 30 | 10 | 33.3% |",
                                     "| APJ RSI | APJ geo | 30 | 44 | 33.3% |")

FIXTURES = [
    ("clean email",
     _SECTIONS.format(table=_GOOD_TABLE, narrative=_GOOD_NARRATIVE),
     []),

    ("wrong CoCo percentage",
     _SECTIONS.format(table=_BAD_PCT_TABLE, narrative=_GOOD_NARRATIVE),
     ["CoCo% == CoCo/Total"]),

    ("CoCo exceeds total",
     _SECTIONS.format(table=_COCO_GT_TOTAL, narrative=_GOOD_NARRATIVE),
     ["CoCo <= Total"]),

    ("calendar month leaked into narrative",
     _SECTIONS.format(table=_GOOD_TABLE,
                      narrative="Through August and October we are trending up by 7.5%."),
     ["no calendar months"]),

    ("pipeline total does not reconcile",
     _SECTIONS.format(table=_GOOD_TABLE,
                      narrative="With 12 weeks remaining, the convertible pipeline "
                                "includes 999 non-CoCo use cases still open."),
     ["narrative pipeline"]),

    ("missing disclaimer",
     _SECTIONS.format(table=_GOOD_TABLE, narrative=_GOOD_NARRATIVE)
     .replace("## DISCLAIMER\n**Disclaimer:** sourced from SE comments.\n", ""),
     ["DISCLAIMER"]),

    ("truncated mid-table",
     _SECTIONS.format(table=_GOOD_TABLE, narrative=_GOOD_NARRATIVE)
     .split("## MANAGED PARTNER")[0].rstrip() + "\n| EMEA RSI | EMEA geo | 18 | 8 |",
     ["not truncated", "NOTABLE WINS", "DISCLAIMER"]),
]
