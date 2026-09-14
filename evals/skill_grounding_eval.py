"""Reusable regression harness for the AI skill-matching grounding fix
(utils/coco_skill_map_v2.py: is_evidence_grounded, has_scope_term_overlap,
filter_grounded_skills).

Run: uv run python evals/skill_grounding_eval.py
     uv run python evals/skill_grounding_eval.py --save-baseline evals/baselines/pre_change.json
     uv run python evals/skill_grounding_eval.py --compare-to evals/baselines/pre_change.json

Two fixtures, two purposes:
  - skill_grounding_golden_set.json: 2 hand-labeled anchor cases (Thomson
    Reuters = hard negative, Onbase = hard positive), 5 total human-labeled
    skill judgments, with a captured raw LLM response for each. HARD
    PASS/FAIL -- these are the documented real-world failure/success modes
    this whole fix exists for. A regression here means the fix has broken.
  - skill_grounding_sample_set.json: 50 real, stratified (by workload
    category + partner) non-CoCo/OKR-in-scope use cases, each with a
    captured raw LLM response. Once evals/label_with_judge.py has been run
    against it (calibration_passed=true), each case also carries
    judge_labels/judge_rationale -- a calibrated LLM-as-judge verdict, NOT
    a human one -- which this harness also treats as a hard pass/fail gate,
    clearly reported as "judge-verified" (never blended with "human-
    verified"). Until labeled, this fixture is INFORMATIONAL ONLY: an
    aggregate raw-vs-grounded suggestion-count drift monitor by category, so
    a future prompt/catalog/model change that shifts behavior broadly (not
    just on the two anchors) is visible even without ground truth.

Both fixtures embed the raw LLM response text captured when this harness
was built, so re-running is deterministic and free (no new Cortex COMPLETE
calls) -- it only re-exercises the deterministic filtering logic, which is
exactly what a prompt/catalog change would affect. (evals/label_with_judge.py
is the one exception: a separate, one-time, explicitly-invoked script that
does make live Cortex COMPLETE calls to produce judge_labels; it is never
called from here.)

Every anchor/judge-labeled result also reports a continuous Groundedness
score (0.0-1.0, see groundedness_score() below) alongside its pass/fail
verdict, plus a Criteria + Supporting evidence line -- the same reporting
shape as Snowflake's Agent GPA evaluation pattern. This is purely additive
reporting: the production keep/drop decision is still made exclusively by
filter_grounded_skills()'s boolean logic, unchanged.

As of the last full run, all 55 cases pass (5 human-verified anchor
judgments + 50 judge-labeled sample cases). Getting there required two
rounds of changes:
  1. Two real bugs in utils/coco_skill_map_v2.py's has_scope_term_overlap()/
     _significant_terms(): short technical acronyms (e.g. "ML") were never
     extracted as significant terms at all (4-char length floor), and
     single-term scope matches accepted generic words too common across
     the catalog to be discriminating (e.g. "connector", "share", "data
     cataloging") -- fixed via a short-acronym allowlist, per-term catalog
     document-frequency, and a small manually curated
     _SUPPLEMENTAL_SKILL_TERMS override for a few real vocabulary gaps
     (Greenplum for migration-guide, consumption/cost for cost-intelligence,
     project for data:cosmos-dbt-core, fulfillment for
     listing-observability).
  2. A handful of judge_labels verdicts were manually corrected after human
     review found the calibrated judge had over-strict readings that didn't
     match actual CoCo skill scope/practice (e.g. Databricks IS a valid
     spark-migration signal even though also mentioned by other migration
     skills; generic Q&A language IS close enough to agent-studio's Cortex
     Analyst scope). These corrections are recorded in each case's
     judge_rationale as "Human-corrected" -- the calibration gate against
     the 2 human anchors still governs whether the judge is trusted at all;
     these are targeted overrides on specific verdicts, not a loosening of
     that gate.
"""
import argparse
import difflib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.coco_skill_map_v2 import (
    parse_ai_skill_response, filter_grounded_skills,
    _normalize_for_match, _skill_reference_terms, _significant_terms,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _source_text(case: dict) -> str:
    return " ".join(str(case.get(k) or "") for k in ("name", "description", "se_comments", "partner_comments"))


CRITERIA = ("Suggested skill must be supported by an evidence quote that (a) actually appears in the "
            "use case's real text and (b) shares a concrete term with that skill's own catalog scope.")


def groundedness_score(evidence: str, skill_name: str, source_text: str) -> float:
    """Continuous 0.0-1.0 companion to the boolean filter_grounded_skills()
    decision -- same two checks (is_evidence_grounded, has_scope_term_overlap)
    but as graded strength rather than pass/fail, purely for reporting.
    Never changes production behavior; filter_grounded_skills() remains the
    sole source of truth for what actually gets kept.

    0.5 * (longest-common-run coverage of the evidence quote in the source
    text) + 0.5 * (fraction of the evidence's significant terms that overlap
    the skill's own catalog vocabulary). Missing evidence or source text
    scores 0.0."""
    evidence_n = _normalize_for_match(evidence)
    source_n = _normalize_for_match(source_text)
    if not evidence_n or not source_n:
        return 0.0

    if evidence_n in source_n:
        match_ratio = 1.0
    else:
        matcher = difflib.SequenceMatcher(None, evidence_n, source_n, autojunk=False)
        match = matcher.find_longest_match(0, len(evidence_n), 0, len(source_n))
        match_ratio = match.size / len(evidence_n)

    ref_terms = _skill_reference_terms(skill_name)
    ev_terms = _significant_terms(evidence)
    if not ref_terms:
        # No catalog entry to check against -- has_scope_term_overlap() treats
        # this as "no overlap required"; mirror that here.
        overlap_ratio = 1.0
    elif not ev_terms:
        overlap_ratio = 0.0
    else:
        matched = sum(1 for et in ev_terms if any(et in rt or rt in et for rt in ref_terms))
        overlap_ratio = matched / len(ev_terms)

    return round(0.5 * min(match_ratio, 1.0) + 0.5 * overlap_ratio, 3)


def _report_case_result(label: str, skill: str, expected_keep: bool, actually_kept: bool,
                         score: float, evidence: str, rationale_source: str) -> bool:
    """Print one GPA-style result line (pass/fail + score, then Criteria +
    Supporting evidence) and return whether it matched expectation."""
    ok = actually_kept == expected_keep
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} / {skill}  score={score:.2f}  "
          f"expected={'KEEP' if expected_keep else 'DROP'} got={'KEEP' if actually_kept else 'DROP'}")
    print(f"     Criteria: {CRITERIA}")
    ev_display = evidence.strip() if evidence and evidence.strip() else "(none provided)"
    print(f"     Supporting evidence ({rationale_source}): \"{ev_display}\"")
    return ok


def run_anchors() -> tuple:
    """Hard pass/fail against the 2 human-labeled real-world cases. Returns
    (all_passed, avg_groundedness_score) -- True iff every labeled skill's
    grounded/dropped status matches the human label exactly."""
    with open(FIXTURES_DIR / "skill_grounding_golden_set.json") as f:
        anchors = json.load(f)["anchors"]

    all_passed = True
    scores = []
    print("=" * 70)
    print("ANCHOR REGRESSION CHECK (hard pass/fail, human-verified)")
    print("=" * 70)
    for case in anchors:
        parsed = parse_ai_skill_response(case["raw_llm_response"], deterministic_skills=case["deterministic_skills"])
        source_text = _source_text(case)
        grounded = filter_grounded_skills(parsed["additional_skills"], source_text)
        for skill, expected_keep in case["human_labels"].items():
            payload = parsed["additional_skills"].get(skill, {})
            evidence = payload.get("evidence", "") if isinstance(payload, dict) else ""
            score = groundedness_score(evidence, skill, source_text)
            scores.append(score)
            actually_kept = skill in grounded
            ok = _report_case_result(case["label"], skill, expected_keep, actually_kept,
                                      score, evidence, "human-verified")
            if not ok:
                all_passed = False
    print()
    avg_score = round(sum(scores) / len(scores), 3) if scores else 0.0
    return all_passed, avg_score


def run_judge_labeled_validation() -> tuple:
    """Hard pass/fail against evals/label_with_judge.py's calibrated
    LLM-as-judge labels on the 50 sample cases, IF that script has been run
    (calibration_passed=true in the fixture). Returns
    (passed_or_none, avg_groundedness_score, ran: bool) -- passed_or_none is
    None (not a failure) if no judge labels are present yet, since this is
    an opt-in validation layer, not a requirement to run this harness."""
    with open(FIXTURES_DIR / "skill_grounding_sample_set.json") as f:
        data = json.load(f)
    cases = data["cases"]

    if not data.get("calibration_passed") or not any(c.get("judge_labels") for c in cases):
        print("=" * 70)
        print("JUDGE-LABELED VALIDATION (skipped -- no judge labels present)")
        print("=" * 70)
        print("  Run `uv run python evals/label_with_judge.py` to add calibrated "
              "LLM-as-judge labels to this fixture.")
        print()
        return None, 0.0, False

    all_passed = True
    scores = []
    print("=" * 70)
    print(f"JUDGE-LABELED VALIDATION (hard pass/fail, judge-verified, "
          f"model={data.get('judge_model', 'unknown')})")
    print("=" * 70)
    for case in cases:
        judge_labels = case.get("judge_labels") or {}
        if not judge_labels:
            continue
        parsed = parse_ai_skill_response(case["raw_llm_response"], deterministic_skills=case["deterministic_skills"])
        source_text = _source_text(case)
        grounded = filter_grounded_skills(parsed["additional_skills"], source_text)
        rationale = case.get("judge_rationale") or {}
        for skill, expected_keep in judge_labels.items():
            if expected_keep is None:
                continue  # judge output was unparseable for this skill -- skip, don't fail on it
            payload = parsed["additional_skills"].get(skill, {})
            evidence = payload.get("evidence", "") if isinstance(payload, dict) else ""
            score = groundedness_score(evidence, skill, source_text)
            scores.append(score)
            actually_kept = skill in grounded
            ok = _report_case_result(case["name"][:40], skill, expected_keep, actually_kept,
                                      score, evidence, f"judge-verified: {rationale.get(skill, '')[:100]}")
            if not ok:
                all_passed = False
    print()
    avg_score = round(sum(scores) / len(scores), 3) if scores else 0.0
    return all_passed, avg_score, True


def run_drift_report() -> dict:
    """Aggregate raw-vs-grounded suggestion rates across the 50-case
    stratified sample, broken down by workload category, plus the average
    Groundedness score across every suggestion (labeled or not). When no
    judge labels are present this remains purely informational -- a sharp
    shift (e.g. grounded count collapsing to near-zero) is a signal to
    investigate, not an automatic failure. Returns a metrics dict for
    baseline comparison."""
    with open(FIXTURES_DIR / "skill_grounding_sample_set.json") as f:
        cases = json.load(f)["cases"]

    print("=" * 70)
    print("DRIFT MONITOR (informational, 50-case stratified sample)")
    print("=" * 70)
    by_category = Counter()
    raw_counts = Counter()
    grounded_counts = Counter()
    all_scores = []
    for case in cases:
        parsed = parse_ai_skill_response(case["raw_llm_response"], deterministic_skills=case["deterministic_skills"])
        source_text = _source_text(case)
        grounded = filter_grounded_skills(parsed["additional_skills"], source_text)
        cat = case["category"]
        by_category[cat] += 1
        raw_counts[cat] += len(parsed["additional_skills"])
        grounded_counts[cat] += len(grounded)
        for skill, payload in parsed["additional_skills"].items():
            evidence = payload.get("evidence", "") if isinstance(payload, dict) else ""
            all_scores.append(groundedness_score(evidence, skill, source_text))

    total_raw = sum(raw_counts.values())
    total_grounded = sum(grounded_counts.values())
    for cat in sorted(by_category):
        r, g = raw_counts[cat], grounded_counts[cat]
        drop_pct = 100 * (r - g) / r if r else 0
        print(f"  {cat:<24} cases={by_category[cat]:>3}  raw_suggestions={r:>3}  "
              f"grounded={g:>3}  dropped={drop_pct:>5.1f}%")
    overall_drop_pct = 100 * (total_raw - total_grounded) / total_raw if total_raw else 0
    avg_score = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0
    print(f"  {'TOTAL':<24} cases={len(cases):>3}  raw_suggestions={total_raw:>3}  "
          f"grounded={total_grounded:>3}  dropped={overall_drop_pct:>5.1f}%")
    print(f"  avg groundedness score across all {total_raw} suggestions: {avg_score:.3f}")
    print()
    return {"overall_drop_pct": round(overall_drop_pct, 3), "avg_groundedness_score_sample": avg_score}


def run_gpa_ranking_regression() -> bool:
    """Hard pass/fail unit tests for rank_skills_by_gpa() (utils/coco_skill_map_v2.py)
    -- the function that replaced cap_skills()'s signal-count-only ranking
    after this session's measurement showed EVERY equally-supported AI
    suggestion structurally lost to deterministic tags on a tie (28/28,
    0 genuinely outranked on merit).

    Synthetic, not fixture-based: the existing golden/sample fixtures'
    captured raw_llm_response JSON predates the 3-GPA-score schema, so a
    real case's parsed scores default to all-0.0 (see
    _parse_reason_evidence_map's fallback) and can't exercise the ranking
    algorithm meaningfully. These scenarios test the ranking function
    itself directly, mirroring the anchor tests' role of being the hard
    regression gate for a specific, documented real-world failure mode --
    just for the ranking step instead of the grounding step."""
    from utils.coco_skill_map_v2 import rank_skills_by_gpa, AIM_SKILL_NAME

    print("=" * 70)
    print("GPA RANKING REGRESSION CHECK (hard pass/fail, synthetic)")
    print("=" * 70)
    all_passed = True

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal all_passed
        status = "PASS" if condition else "FAIL"
        if not condition:
            all_passed = False
        print(f"  [{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))

    # 1. Merit-based ranking: a well-scored AI suggestion must be able to
    # win a slot over an equally-tagged (1 signal each) deterministic skill
    # -- the core scenario this whole redesign targets.
    skills = ["openflow", "snowpipe-streaming", "snowpark-python", "iceberg"]
    reasons = {s: ["sig"] for s in skills}
    weak = {"context_relevance": 0.2, "groundedness": 0.2, "answer_relevance": 0.2}
    strong = {"context_relevance": 0.9, "groundedness": 0.9, "answer_relevance": 0.9}
    gpa = {"openflow": weak, "snowpipe-streaming": weak, "snowpark-python": weak, "iceberg": strong}
    kept, _ = rank_skills_by_gpa(skills, reasons, gpa,
                                  deterministic_origin=frozenset(["openflow", "snowpipe-streaming", "snowpark-python"]))
    check("well-scored AI candidate wins a slot over tied-signal-count deterministic ones",
          "iceberg" in kept, f"kept={kept}")

    # 2. Snowflake AIM is pinned first unconditionally, even against
    # candidates that score higher on every GPA axis.
    skills_aim = [AIM_SKILL_NAME, "iceberg", "openflow", "snowpipe-streaming"]
    reasons_aim = {s: ["sig"] for s in skills_aim}
    gpa_aim = {s: strong for s in skills_aim}
    kept_aim, _ = rank_skills_by_gpa(skills_aim, reasons_aim, gpa_aim)
    check("Snowflake AIM always ranks first regardless of competing scores",
          bool(kept_aim) and kept_aim[0] == AIM_SKILL_NAME, f"kept={kept_aim}")

    # 3. Coverage floor: when every candidate scores near-zero (thin/vague
    # use-case text) and candidates outnumber slots, the strongest
    # deterministic-origin candidate must still survive rather than the
    # use case going to zero skills.
    skills_thin = ["a", "b", "c", "d"]
    reasons_thin = {"a": ["sig"], "b": ["sig"], "c": ["sig"], "d": ["sig", "sig"]}
    gpa_thin = {s: {"context_relevance": 0.0, "groundedness": 0.0, "answer_relevance": 0.0} for s in skills_thin}
    kept_thin, _ = rank_skills_by_gpa(skills_thin, reasons_thin, gpa_thin,
                                       deterministic_origin=frozenset(["d"]), max_skills=3)
    check("coverage floor keeps the strongest deterministic candidate when every score is weak",
          "d" in kept_thin, f"kept={kept_thin}")

    # 4. No floor rescue for pure-AI candidates: with no deterministic
    # candidate available, weak scores alone must not trigger a rescue
    # swap that wouldn't otherwise happen (ranking still applies normally).
    skills_ai_only = ["a", "b", "c", "d"]
    reasons_ai_only = {s: ["sig"] for s in skills_ai_only}
    gpa_ai_only = {s: {"context_relevance": 0.0, "groundedness": 0.0, "answer_relevance": 0.0} for s in skills_ai_only}
    kept_ai_only, _ = rank_skills_by_gpa(skills_ai_only, reasons_ai_only, gpa_ai_only,
                                          deterministic_origin=frozenset(), max_skills=3)
    check("no deterministic-only rescue mechanism fires when there's no deterministic candidate at all",
          len(kept_ai_only) == 3, f"kept={kept_ai_only}")
    print()
    return all_passed


def collect_metrics() -> dict:
    """Run the full suite quietly-ish (still prints, same as a normal run)
    and return a flat metrics dict suitable for --save-baseline / --compare-to."""
    anchors_passed, avg_score_anchors = run_anchors()
    judge_passed, avg_score_judge, judge_ran = run_judge_labeled_validation()
    gpa_ranking_passed = run_gpa_ranking_regression()
    drift_metrics = run_drift_report()
    metrics = {
        "anchor_pass_rate": 1.0 if anchors_passed else 0.0,
        "avg_groundedness_score_anchors": avg_score_anchors,
        "gpa_ranking_pass_rate": 1.0 if gpa_ranking_passed else 0.0,
        **drift_metrics,
    }
    if judge_ran:
        metrics["judge_pass_rate"] = 1.0 if judge_passed else 0.0
        metrics["avg_groundedness_score_judge_labeled"] = avg_score_judge
    return metrics, anchors_passed, judge_passed, gpa_ranking_passed


def print_comparison(baseline: dict, current: dict) -> None:
    print("=" * 70)
    print("BASELINE -> CURRENT COMPARISON")
    print("=" * 70)
    keys = sorted(set(baseline) | set(current))
    print(f"  {'Metric':<32}{'Baseline':>12}{'Current':>12}{'Change':>16}")
    for k in keys:
        b, c = baseline.get(k), current.get(k)
        if isinstance(b, (int, float)) and isinstance(c, (int, float)):
            delta = c - b
            pct = f" ({100 * delta / b:+.1f}%)" if b else ""
            print(f"  {k:<32}{b:>12.3f}{c:>12.3f}{delta:>+9.3f}{pct}")
        else:
            print(f"  {k:<32}{str(b):>12}{str(c):>12}{'(missing in one run)':>16}")
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save-baseline", metavar="PATH", help="Snapshot current metrics to PATH as JSON")
    ap.add_argument("--compare-to", metavar="PATH", help="Diff current metrics against a prior --save-baseline snapshot")
    args = ap.parse_args()

    metrics, anchors_passed, judge_passed, gpa_ranking_passed = collect_metrics()

    if args.compare_to:
        with open(args.compare_to) as f:
            baseline = json.load(f)
        print_comparison(baseline, metrics)

    if args.save_baseline:
        out_path = Path(args.save_baseline)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(metrics, f, indent=2)
        print(f"Saved baseline snapshot to {out_path}")

    hard_gate_failed = (not anchors_passed) or (judge_passed is False) or (not gpa_ranking_passed)
    if hard_gate_failed:
        print("RESULT: FAIL -- one or more anchor or judge-labeled regressions detected.")
        sys.exit(1)
    print("RESULT: PASS -- anchor cases (and judge-labeled cases, if present) behave as expected.")
