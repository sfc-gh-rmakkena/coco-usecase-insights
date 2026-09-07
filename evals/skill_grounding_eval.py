"""Reusable regression harness for the AI skill-matching grounding fix
(utils/coco_skill_map_v2.py: is_evidence_grounded, has_scope_term_overlap,
filter_grounded_skills).

Run: uv run python evals/skill_grounding_eval.py

Two fixtures, two purposes:
  - skill_grounding_golden_set.json: 2 hand-labeled anchor cases (Thomson
    Reuters = hard negative, Onbase = hard positive) with a captured raw
    LLM response for each. HARD PASS/FAIL -- these are the documented
    real-world failure/success modes this whole fix exists for. A
    regression here means the fix has broken.
  - skill_grounding_sample_set.json: 50 real, stratified (by workload
    category + partner) non-CoCo/OKR-in-scope use cases, each with a
    captured raw LLM response. INFORMATIONAL drift monitor -- reports
    aggregate raw-vs-grounded suggestion counts by category so a future
    prompt/catalog/model change that shifts behavior broadly (not just on
    the two anchors) is visible, without requiring exhaustive hand-labels
    on all ~180 individual suggestions in this set.

Both fixtures embed the raw LLM response text captured when this harness
was built, so re-running is deterministic and free (no new Cortex COMPLETE
calls) -- it only re-exercises the deterministic filtering logic, which is
exactly what a prompt/catalog change would affect.
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.coco_skill_map_v2 import parse_ai_skill_response, filter_grounded_skills

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _source_text(case: dict) -> str:
    return " ".join(str(case.get(k) or "") for k in ("name", "description", "se_comments", "partner_comments"))


def run_anchors() -> bool:
    """Hard pass/fail against the 2 hand-labeled real-world cases. Returns
    True iff every labeled skill's grounded/dropped status matches the
    human label exactly."""
    with open(FIXTURES_DIR / "skill_grounding_golden_set.json") as f:
        anchors = json.load(f)["anchors"]

    all_passed = True
    print("=" * 70)
    print("ANCHOR REGRESSION CHECK (hard pass/fail)")
    print("=" * 70)
    for case in anchors:
        parsed = parse_ai_skill_response(case["raw_llm_response"], deterministic_skills=case["deterministic_skills"])
        source_text = _source_text(case)
        grounded = filter_grounded_skills(parsed["additional_skills"], source_text)
        case_ok = True
        for skill, expected_keep in case["human_labels"].items():
            actually_kept = skill in grounded
            if actually_kept != expected_keep:
                case_ok = False
                all_passed = False
                print(f"  FAIL [{case['label']}] {skill}: expected "
                      f"{'KEPT' if expected_keep else 'DROPPED'}, got "
                      f"{'KEPT' if actually_kept else 'DROPPED'}")
        status = "PASS" if case_ok else "FAIL"
        print(f"  [{status}] {case['label']} ({len(case['human_labels'])} labeled skill(s))")
    print()
    return all_passed


def run_drift_report() -> None:
    """Informational: aggregate raw-vs-grounded suggestion rates across the
    50-case stratified sample, broken down by workload category. Not a
    pass/fail gate -- a sharp shift here (e.g. grounded count collapsing to
    near-zero, or the drop rate falling to zero) is a signal to
    investigate, not an automatic failure."""
    with open(FIXTURES_DIR / "skill_grounding_sample_set.json") as f:
        cases = json.load(f)["cases"]

    print("=" * 70)
    print("DRIFT MONITOR (informational, 50-case stratified sample)")
    print("=" * 70)
    by_category = Counter()
    raw_counts = Counter()
    grounded_counts = Counter()
    for case in cases:
        parsed = parse_ai_skill_response(case["raw_llm_response"], deterministic_skills=case["deterministic_skills"])
        source_text = _source_text(case)
        grounded = filter_grounded_skills(parsed["additional_skills"], source_text)
        cat = case["category"]
        by_category[cat] += 1
        raw_counts[cat] += len(parsed["additional_skills"])
        grounded_counts[cat] += len(grounded)

    total_raw = sum(raw_counts.values())
    total_grounded = sum(grounded_counts.values())
    for cat in sorted(by_category):
        r, g = raw_counts[cat], grounded_counts[cat]
        drop_pct = 100 * (r - g) / r if r else 0
        print(f"  {cat:<24} cases={by_category[cat]:>3}  raw_suggestions={r:>3}  "
              f"grounded={g:>3}  dropped={drop_pct:>5.1f}%")
    overall_drop_pct = 100 * (total_raw - total_grounded) / total_raw if total_raw else 0
    print(f"  {'TOTAL':<24} cases={len(cases):>3}  raw_suggestions={total_raw:>3}  "
          f"grounded={total_grounded:>3}  dropped={overall_drop_pct:>5.1f}%")
    print()


if __name__ == "__main__":
    anchors_passed = run_anchors()
    run_drift_report()
    if not anchors_passed:
        print("RESULT: FAIL -- one or more anchor regressions detected.")
        sys.exit(1)
    print("RESULT: PASS -- both anchor cases behave as expected.")
