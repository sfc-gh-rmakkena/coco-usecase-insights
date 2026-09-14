"""One-time, offline LLM-as-judge labeling pass for the 50 unlabeled cases in
skill_grounding_sample_set.json.

Run: uv run python evals/label_with_judge.py [--model MODEL] [--dry-run]

Why a judge instead of manual review: hand-reviewing ~180 individual skill
suggestions doesn't scale. Why NOT trust the judge blindly: this harness
exists to catch an LLM (the skill-suggester) hallucinating ungrounded
associations -- a second LLM call judging "was that grounded?" can share the
same blind spots, since both are Cortex COMPLETE calls reasoning over similar
text. Mitigations below are mandatory, not configurable flags:

  1. CALIBRATION GATE: the judge is first run BLIND on the 2 already
     human-verified anchor cases (skill_grounding_golden_set.json). If its
     verdicts don't match the known-correct human labels exactly, this
     script aborts WITHOUT touching skill_grounding_sample_set.json --
     printing a calibration-failure report instead of persisting anything.
  2. STRICT RUBRIC, NOT OPEN JUDGMENT: the judge prompt states the exact
     grounding rule already implemented in code (is_evidence_grounded /
     has_scope_term_overlap in utils/coco_skill_map_v2.py) and is given the
     2 anchor cases as worked few-shot examples -- it is checking that
     rule's real-world application, not inventing its own definition of
     "correct". The rubric explicitly excludes certainty/decision-status
     from the definition of "grounded" (a "discuss using Openflow" or
     "Iceberg integration proposed" quote IS grounded for that skill) --
     an early run without this line over-rejected tentative/discussion
     language that the deterministic code correctly keeps, since
     is_evidence_grounded/has_scope_term_overlap never check certainty
     either.
  3. ONE-TIME OFFLINE RUN: this script is never invoked by
     skill_grounding_eval.py itself. It runs once (or whenever you want to
     re-label), writing judge_labels / judge_rationale / calibration_passed
     into the fixture JSON. The regular eval suite then replays those
     labels for free with zero live API calls, exactly like the anchors.
  4. LABELS ARE MARKED, NOT BLENDED: output fields are judge_labels /
     judge_rationale, never renamed to human_labels -- skill_grounding_eval.py
     and its output always distinguish "human-verified" (2 anchors) from
     "judge-verified, calibration-passed" (these 50 cases).

Requires a live Snowflake connection (uses the `snowhouse` CLI connection --
same pattern as scripts/eval_theatre_grounding.py). Costs real Cortex
COMPLETE calls; this is the one script in evals/ that isn't free to re-run.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import snowflake.connector

from utils.coco_skill_map_v2 import parse_ai_skill_response, COCO_SKILL_CATALOG

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_SET_PATH = FIXTURES_DIR / "skill_grounding_golden_set.json"
SAMPLE_SET_PATH = FIXTURES_DIR / "skill_grounding_sample_set.json"

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-5"

RUBRIC = (
    "You are auditing whether an AI-suggested Snowflake CoCo skill for a use case is GROUNDED "
    "or a HALLUCINATION.\n\n"
    "A suggestion is GROUNDED only if BOTH hold:\n"
    "1. The 'evidence' quote is REAL text that actually appears (verbatim or near-verbatim) in the "
    "use case text below -- not a paraphrase, not an inference, not a fabricated quote.\n"
    "2. The evidence quote shares a CONCRETE term with the skill's own scope (its name/summary/example "
    "use cases below) -- a topical or thematic connection is NOT enough. For example, the word 'content' "
    "alone does not ground 'document-intelligence' (that requires an actual file/PDF/form/stage mention); "
    "the word 'insights' alone does not ground a machine-learning skill (that requires an actual model/"
    "training/prediction mention).\n\n"
    "DO NOT judge certainty, decision status, or tentativeness -- that is out of scope for this rubric. "
    "Grounding is ONLY about whether the quote is real text that names a concrete, on-topic term for the "
    "skill; it does NOT require the use case to have already decided, committed to, or implemented "
    "anything. Words like 'discuss', 'proposed', 'considering', 'exploring', or 'may' do NOT disqualify an "
    "otherwise-grounded quote. For example: 'discuss using Openflow for the postgres db to replicate to "
    "Snowflake' IS grounded for the openflow skill (it names Openflow concretely, regardless of being a "
    "discussion); 'Iceberg Volume integration proposed' IS grounded for the iceberg skill (it names Iceberg "
    "concretely, regardless of being a proposal); 'Chatbot for document' IS grounded for document-"
    "intelligence (it names 'document' concretely). Only fail a suggestion for lacking a real quote or "
    "lacking a concrete shared term -- never for hedging language.\n\n"
    "Return ONLY a JSON object: {\"grounded\": true/false, \"rationale\": \"one sentence citing the "
    "specific reason\"}. No markdown, no preamble."
)


def _source_text(case: dict) -> str:
    return " ".join(str(case.get(k) or "") for k in ("name", "description", "se_comments", "partner_comments"))


def _skill_scope_text(skill_name: str) -> str:
    skill = next((s for s in COCO_SKILL_CATALOG if s["name"].lower() == skill_name.strip().lower()), None)
    if not skill:
        return "(no catalog entry found)"
    return f"{skill['name']}: {skill['summary']} (e.g. {'; '.join(skill['use_cases'])})"


_FEW_SHOT = None


def _few_shot_block() -> str:
    """The 2 anchor cases, with their HUMAN verdicts, as worked examples."""
    global _FEW_SHOT
    if _FEW_SHOT is not None:
        return _FEW_SHOT
    with open(GOLDEN_SET_PATH) as f:
        anchors = json.load(f)["anchors"]
    parts = []
    for a in anchors:
        source = _source_text(a)
        for skill, expected in a["human_labels"].items():
            parts.append(
                f"EXAMPLE -- use case text: \"{source[:400]}\"\n"
                f"Suggested skill: {skill}\nSkill scope: {_skill_scope_text(skill)}\n"
                f"Correct verdict: {{\"grounded\": {str(expected).lower()}, "
                f"\"rationale\": \"see notes: {a['notes'][:200]}\"}}"
            )
    _FEW_SHOT = "\n\n".join(parts)
    return _FEW_SHOT


def _judge_one(cur, model: str, source_text: str, skill_name: str, evidence: str) -> dict:
    # No truncation here: is_evidence_grounded() in utils/coco_skill_map_v2.py checks
    # evidence against the FULL, untruncated source text. Some SE-comment histories run
    # to ~11k chars (see max() over skill_grounding_sample_set.json) -- an earlier 1500-char
    # cap here caused false "evidence not found" verdicts for real quotes that were simply
    # further down a long comment history than the cap allowed (e.g. an "openflow" mention
    # 3000+ chars into Nationwide's SE notes). The judge must see everything the deterministic
    # code sees, or its verdicts aren't actually comparable to filter_grounded_skills()'s.
    prompt = (
        f"{RUBRIC}\n\nWorked examples with known-correct verdicts:\n{_few_shot_block()}\n\n"
        f"Now judge this case.\nUse case text: \"{source_text}\"\n"
        f"Suggested skill: {skill_name}\nSkill scope: {_skill_scope_text(skill_name)}\n"
        f"Evidence quote given by the suggester: \"{evidence}\"\n\nJSON:"
    )
    escaped = prompt.replace("\\", "\\\\").replace("'", "\\'")
    cur.execute(
        f"""SELECT SNOWFLAKE.CORTEX.COMPLETE(
                     '{model}',
                     [{{'role':'user','content':'{escaped}'}}],
                     {{'max_tokens': 400}}
                   ):choices[0].messages::string AS RESPONSE"""
    )
    row = cur.fetchone()
    raw = row[0] if row else ""
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return {"grounded": None, "rationale": f"unparseable judge output: {(raw or '')[:200]}"}
    try:
        d = json.loads(m.group(0))
        return {"grounded": bool(d.get("grounded")), "rationale": str(d.get("rationale", "")).strip()}
    except json.JSONDecodeError:
        return {"grounded": None, "rationale": f"bad judge JSON: {raw[:200]}"}


def run_calibration(cur, model: str) -> bool:
    """Blind judge run on the 2 anchor cases. True iff every verdict matches
    the known-correct human_labels exactly."""
    with open(GOLDEN_SET_PATH) as f:
        anchors = json.load(f)["anchors"]

    print("=" * 70)
    print("CALIBRATION (judge run blind against known-correct human labels)")
    print("=" * 70)
    all_ok = True
    for case in anchors:
        parsed = parse_ai_skill_response(case["raw_llm_response"], deterministic_skills=case["deterministic_skills"])
        source_text = _source_text(case)
        for skill, expected in case["human_labels"].items():
            payload = parsed["additional_skills"].get(skill, {})
            evidence = payload.get("evidence", "") if isinstance(payload, dict) else ""
            verdict = _judge_one(cur, model, source_text, skill, evidence)
            ok = verdict["grounded"] == expected
            all_ok = all_ok and ok
            print(f"  [{'PASS' if ok else 'FAIL'}] {case['label']} / {skill}: "
                  f"expected grounded={expected}, judge said grounded={verdict['grounded']} "
                  f"-- {verdict['rationale']}")
    print()
    return all_ok


def run_labeling(cur, model: str) -> dict:
    """Judge every additional_skill suggestion across the 50 sample cases.
    Mutates and returns the loaded fixture dict (judge_labels/judge_rationale
    added per case)."""
    with open(SAMPLE_SET_PATH) as f:
        data = json.load(f)
    cases = data["cases"]

    print("=" * 70)
    print(f"LABELING {len(cases)} sample cases with judge model {model}")
    print("=" * 70)
    for i, case in enumerate(cases):
        parsed = parse_ai_skill_response(case["raw_llm_response"], deterministic_skills=case["deterministic_skills"])
        source_text = _source_text(case)
        judge_labels, judge_rationale = {}, {}
        for skill, payload in parsed["additional_skills"].items():
            evidence = payload.get("evidence", "") if isinstance(payload, dict) else ""
            verdict = _judge_one(cur, model, source_text, skill, evidence)
            judge_labels[skill] = verdict["grounded"]
            judge_rationale[skill] = verdict["rationale"]
        case["judge_labels"] = judge_labels
        case["judge_rationale"] = judge_rationale
        print(f"  [{i + 1}/{len(cases)}] {case['name'][:50]!r}: {judge_labels}")
    print()
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=DEFAULT_JUDGE_MODEL, help="Cortex COMPLETE model to use as judge")
    ap.add_argument("--dry-run", action="store_true", help="Run calibration only, never write the fixture")
    args = ap.parse_args()

    conn = snowflake.connector.connect(
        connection_name="snowhouse", role="SALES_ENGINEER",
        warehouse="COCO_PARTNER_ADOPTION_WH", database="TEMP",
        schema="COCO_PARTNER_ADOPTION",
    )
    cur = conn.cursor()

    calibration_passed = run_calibration(cur, args.model)
    if not calibration_passed:
        print("RESULT: ABORT -- judge failed calibration against known-correct human labels.")
        print(f"Fixture NOT modified ({SAMPLE_SET_PATH}). Fix the rubric/prompt/model choice and re-run.")
        sys.exit(1)

    if args.dry_run:
        print("RESULT: calibration PASSED. --dry-run set, not labeling the 50 sample cases.")
        return

    data = run_labeling(cur, args.model)
    data["calibration_passed"] = True
    data["judge_model"] = args.model

    with open(SAMPLE_SET_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"RESULT: wrote judge_labels for {len(data['cases'])} cases to {SAMPLE_SET_PATH}")


if __name__ == "__main__":
    main()
