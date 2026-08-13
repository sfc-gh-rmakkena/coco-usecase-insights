"""Multi-turn eval harness for the Ask AI feature.

Runs scripted conversations from eval_scenarios.py through BOTH Ask AI
implementations and grades context retention two ways: deterministic per-turn
assertions plus a Cortex LLM-as-judge score over the whole transcript.

Must be run under Streamlit, because ask_ai/ask_ai_agent read st.session_state
and st.connection exactly as the sidebar chat does:

    streamlit run scripts/eval_ask_ai_multiturn.py --server.headless true

Optional env vars:
    EVAL_PATHS=agent,direct     which implementations to exercise
    EVAL_SCENARIOS=id1,id2      subset of scenario ids (default: all)
    EVAL_OUT=/path/report.md    report destination

Results are written to the report file, printed to stdout, and rendered in the
Streamlit page.
"""

import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import PARTNER_ALIASES
from utils.ask_ai import ask_ai, ask_ai_agent
from utils.cortex_helpers import cortex_complete
from scripts.eval_scenarios import SCENARIOS, JUDGE_RUBRIC

st.set_page_config(page_title="Ask AI multi-turn eval", layout="wide")

PATHS = [p.strip() for p in os.environ.get("EVAL_PATHS", "agent,direct").split(",") if p.strip()]
ONLY = {s.strip() for s in os.environ.get("EVAL_SCENARIOS", "").split(",") if s.strip()}
OUT = Path(os.environ.get("EVAL_OUT", "/tmp/ask_ai_multiturn_report.md"))
JUDGE_MODEL = "claude-sonnet-4-5"

# Candidate partner names used to detect which entity an answer is talking about.
KNOWN_ENTITIES = sorted(
    {
        name
        for canonical, aliases in PARTNER_ALIASES.items()
        if not canonical.startswith("---")
        for name in ([canonical] + list(aliases))
    },
    key=len,
    reverse=True,
)

ERROR_MARKERS = ("agent call failed", "traceback", "sql error", "api error",
                 "could not parse agent response", "no response from agent")


def bootstrap_session():
    """Mirror the sidebar defaults so filter context matches the real app."""
    if "conn" not in st.session_state:
        st.session_state.conn = st.connection("snowflake")
    st.session_state.setdefault("_ui_region", "Global")
    st.session_state.setdefault("selected_region", "Global")
    st.session_state.setdefault("selected_theater", "All")
    st.session_state.setdefault("selected_partners", [])
    st.session_state.setdefault("selected_stages", [])
    st.session_state.setdefault("okr_start_date", date(2026, 8, 1))
    st.session_state.setdefault("okr_end_date", date(2026, 10, 31))
    st.session_state.setdefault("include_account_coco", "Yes")
    st.session_state.setdefault("confidence_filter", ["High"])
    st.session_state.setdefault("ask_ai_context", "")


def detect_entity(text):
    """Return the first known partner name mentioned in text, else None.

    Falls back to a bolded/quoted proper noun so partners absent from
    PARTNER_ALIASES (e.g. 'phData, Inc.') are still captured — without this the
    carryover assertions silently degrade to 'could not verify'.
    """
    if not text:
        return None
    low = text.lower()
    for name in KNOWN_ENTITIES:
        if name.lower() in low:
            return name
    for pat in (r"\*\*([A-Za-z][\w&.,'\- ]{2,40}?)\*\*", r"^([A-Za-z][\w&.,'\- ]{2,40})\s*$"):
        m = re.search(pat, text.strip(), re.MULTILINE)
        if m:
            cand = m.group(1).strip().rstrip(".,")
            if (any(c.isupper() for c in cand)
                    and len(cand.split()) <= 5
                    and cand.lower() not in ("total uc", "total go-lives", "gsi", "gsis")):
                return cand
    return None


def build_page_context(conn):
    """Approximate what a real page injects into ask_ai_context.

    Every app page sets st.session_state.ask_ai_context before the chat is
    reachable, so evaluating the direct path with an empty context is not
    representative — with no data it answers NO_SQL_NEEDED and invents numbers.
    Set EVAL_PAGE_CTX=empty to reproduce that cold-start behaviour instead.
    """
    if os.environ.get("EVAL_PAGE_CTX") == "empty":
        return ""
    from utils.ask_ai import build_filter_context
    try:
        df = conn.query(
            """
            SELECT PARTNER_NAME,
                   COUNT(*) AS TOTAL_UCS,
                   COUNT(CASE WHEN IS_COCO_FINAL THEN 1 END) AS COCO_UCS,
                   ROUND(SUM(USE_CASE_EACV)/1000, 0) AS EACV_K
            FROM TEMP.COCO_PARTNER_ADOPTION.DT_OKR_USE_CASES
            GROUP BY PARTNER_NAME
            ORDER BY COCO_UCS DESC
            LIMIT 25
            """,
            ttl=0,
        )
        table = df.to_string(index=False)
    except Exception as e:
        table = f"(page data unavailable: {e})"
    return (
        "Current page: Adoption Metrics (Overview).\n"
        f"{build_filter_context()}\n\n"
        f"TOP PARTNERS BY COCO USE CASES:\n{table}\n"
    )


def grade_turn(turn, answer, sql, carried_entity, path):
    """Deterministic checks. Returns (passed, failures, warnings).

    SQL-based checks are WARNINGS, never failures, because neither path makes
    them a reliable multi-turn signal:
      - the agent path never surfaces SQL to the caller (cortex_helpers.py
        parses "tool_result" while the payload uses "tool_results");
      - the direct path legitimately answers from injected page context
        without generating SQL at all.
    Context retention is judged from the answer text and carried entity.
    """
    fails = []
    warns = []
    ans = (answer or "").lower()
    sql_l = (sql or "").lower()

    for marker in ERROR_MARKERS:
        if marker in ans:
            fails.append(f"answer contains error marker '{marker}'")

    if not (answer or "").strip():
        fails.append("empty answer")

    if turn.get("sql_required") and not (sql or "").strip():
        warns.append("no SQL surfaced/generated (informational)")

    for frag in turn.get("sql_must_contain", []):
        if frag.lower() not in sql_l:
            warns.append(f"SQL missing fragment '{frag}'")

    for frag in turn.get("sql_must_not_contain", []):
        if frag.lower() in sql_l:
            warns.append(f"SQL contains forbidden fragment '{frag}'")

    ents = turn.get("expect_entities", [])
    if ents and not any(e.lower() in ans for e in ents):
        fails.append(f"answer mentions none of {ents}")

    for e in turn.get("expect_all_entities", []):
        if e.lower() not in ans:
            fails.append(f"answer missing required entity '{e}'")

    for e in turn.get("forbid_entities", []):
        if e.lower() in ans:
            fails.append(f"answer mentions forbidden entity '{e}'")

    if turn.get("expect_carried_entity"):
        if not carried_entity:
            fails.append("no entity captured in seeding turn (cannot verify carryover)")
        elif carried_entity.lower() not in ans and carried_entity.lower() not in sql_l:
            fails.append(f"carried entity '{carried_entity}' absent from answer and SQL")

    return (not fails), fails, warns


def judge(conn, scenario, transcript):
    """LLM-as-judge over the whole conversation. Returns dict."""
    convo = "\n\n".join(
        f"TURN {t['n']}\nUser: {t['q']}\nAssistant: {(t['answer'] or '')[:1200]}"
        for t in transcript
    )
    prompt = (
        f"{JUDGE_RUBRIC}\n\n"
        f"What this conversation is testing: {scenario['why']}\n\n"
        f"CONVERSATION:\n{convo}\n\nJSON:"
    )
    try:
        raw = cortex_complete(conn, JUDGE_MODEL, prompt)
    except Exception as e:
        return {"score": None, "verdict": f"judge call failed: {e}", "failure_mode": "judge_error"}

    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return {"score": None, "verdict": f"unparseable judge output: {(raw or '')[:200]}",
                "failure_mode": "judge_error"}
    try:
        d = json.loads(m.group(0))
        return {"score": d.get("score"), "verdict": d.get("verdict", ""),
                "failure_mode": d.get("failure_mode", "")}
    except json.JSONDecodeError as e:
        return {"score": None, "verdict": f"bad judge JSON: {e}", "failure_mode": "judge_error"}


def run_scenario(conn, path, scenario, log, page_ctx=""):
    """Execute one scenario end to end on one implementation."""
    history = []
    transcript = []
    carried = None

    for i, turn in enumerate(scenario["turns"], start=1):
        q = turn["q"]
        log(f"    turn {i}: {q[:70]}")
        t0 = time.time()
        try:
            if path == "agent":
                result = ask_ai_agent(q, chat_history=history)
            else:
                result = ask_ai(conn, q, page_ctx, debug=False, chat_history=history)
            answer = result.get("answer", "")
            sql = result.get("sql")
            sql_result = result.get("sql_result")
            err = None
        except Exception as e:
            answer, sql, sql_result = "", None, None
            err = f"{type(e).__name__}: {e}"
        elapsed = round(time.time() - t0, 1)

        if turn.get("capture_entity") and not carried:
            carried = detect_entity(answer)

        passed, fails, warns = grade_turn(turn, answer, sql, carried, path)
        if err:
            passed = False
            fails.append(f"exception: {err}")

        transcript.append({
            "n": i, "q": q, "answer": answer, "sql": sql,
            "sql_result": (sql_result or "")[:500],
            "probe": bool(turn.get("probe")), "carry_from": turn.get("carry_from"),
            "passed": passed, "failures": fails, "warnings": warns, "seconds": elapsed,
        })

        # Feed history exactly as streamlit_app.py does, including SQL metadata.
        history.append({"role": "user", "content": q})
        entry = {"role": "assistant", "content": answer}
        if sql:
            entry["sql"] = sql
        if sql_result:
            entry["sql_result"] = sql_result
        history.append(entry)

    probes = [t for t in transcript if t["probe"]]
    verdict = judge(conn, scenario, transcript)

    return {
        "scenario": scenario["id"],
        "title": scenario["title"],
        "path": path,
        "captured_entity": carried,
        "turns": transcript,
        "probe_total": len(probes),
        "probe_passed": sum(1 for t in probes if t["passed"]),
        "deterministic_pass": all(t["passed"] for t in probes) if probes else all(
            t["passed"] for t in transcript),
        "judge": verdict,
    }


def render_report(results):
    lines = [
        "# Ask AI — multi-turn eval report",
        "",
        f"Run: {datetime.now().isoformat(timespec='seconds')}",
        f"Paths: {', '.join(PATHS)} | Judge model: {JUDGE_MODEL}",
        f"Direct-path page context: {len(PAGE_CTX)} chars"
        f"{' (EMPTY — cold start)' if not PAGE_CTX else ''}",
        "",
        "Deterministic pass = every probe turn satisfied its assertions.",
        "Judge score grades context retention only (1-5), not numeric accuracy.",
        "",
        "## Summary",
        "",
        "| Scenario | Path | Probes passed | Deterministic | Judge | Failure mode |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['scenario']} | {r['path']} | {r['probe_passed']}/{r['probe_total']} | "
            f"{'PASS' if r['deterministic_pass'] else 'FAIL'} | "
            f"{r['judge'].get('score')} | {r['judge'].get('failure_mode') or '-'} |"
        )

    for path in PATHS:
        rs = [r for r in results if r["path"] == path]
        if not rs:
            continue
        det = sum(1 for r in rs if r["deterministic_pass"])
        scores = [r["judge"]["score"] for r in rs if isinstance(r["judge"].get("score"), (int, float))]
        avg = round(sum(scores) / len(scores), 2) if scores else "n/a"
        lines += ["", f"**{path}**: {det}/{len(rs)} scenarios passed deterministically, "
                      f"mean judge score {avg}"]

    lines += ["", "## Detail", ""]
    for r in results:
        lines += [f"### {r['scenario']} — {r['path']}", "",
                  f"*{r['title']}*", "",
                  f"- Captured entity: `{r['captured_entity']}`",
                  f"- Judge: **{r['judge'].get('score')}** — {r['judge'].get('verdict')}", ""]
        for t in r["turns"]:
            tag = "PROBE" if t["probe"] else "seed"
            lines += [f"**Turn {t['n']}** ({tag}, {t['seconds']}s) — "
                      f"{'PASS' if t['passed'] else 'FAIL'}", "",
                      f"> Q: {t['q']}", ""]
            if t["failures"]:
                lines += ["Failures:", ""] + [f"- {f}" for f in t["failures"]] + [""]
            if t.get("warnings"):
                lines += ["Warnings (not counted):", ""] + [f"- {w}" for w in t["warnings"]] + [""]
            ans = (t["answer"] or "").strip().replace("\n", " ")
            lines += [f"A: {ans[:400]}{'...' if len(ans) > 400 else ''}", ""]
            if t["sql"]:
                lines += ["```sql", t["sql"][:700], "```", ""]
    return "\n".join(lines)


# ── run ──────────────────────────────────────────────────────────────────────
bootstrap_session()
conn = st.session_state.conn

selected = [s for s in SCENARIOS if not ONLY or s["id"] in ONLY]

st.title("Ask AI — multi-turn eval")
st.caption(f"{len(selected)} scenarios x {len(PATHS)} paths — report to {OUT}")
progress = st.empty()
live = st.container()

_logs = []


def log(msg):
    _logs.append(msg)
    print(msg, flush=True)
    progress.text(msg)


results = []
PAGE_CTX = build_page_context(conn) if "direct" in PATHS else ""
log(f"page context: {len(PAGE_CTX)} chars")
total = len(selected) * len(PATHS)
done = 0
for path in PATHS:
    log(f"=== path: {path} ===")
    for sc in selected:
        log(f"  scenario: {sc['id']}")
        results.append(run_scenario(conn, path, sc, log, page_ctx=PAGE_CTX))
        done += 1
        log(f"  done {done}/{total}")

report = render_report(results)
OUT.write_text(report)
OUT.with_suffix(".json").write_text(json.dumps(results, indent=2, default=str))

print("\n" + report, flush=True)
progress.success(f"Complete — {OUT}")
with live:
    st.markdown(report)
