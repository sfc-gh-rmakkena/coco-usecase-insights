"""Multi-turn eval scenarios for the Ask AI feature.

Each scenario is a scripted conversation. Turns run in order against a single
shared chat history, exactly as the sidebar chat does, so a turn's grading
reflects whether earlier context actually survived.

Per-turn deterministic checks (all optional):
    expect_entities    list[str]  — at least one must appear in the answer (case-insensitive)
    expect_all_entities list[str] — every one must appear in the answer
    forbid_entities    list[str]  — none may appear in the answer
    sql_required       bool       — a SQL query must have been generated
    sql_must_contain   list[str]  — every fragment must appear in the generated SQL
    sql_must_not_contain list[str]— no fragment may appear in the generated SQL

`probe` marks the turn that actually tests memory. Turn 1 usually just seeds
context, so a scenario is only counted as a multi-turn pass if its probe turns
pass. `carry_from` documents which earlier turn the probe depends on.
"""

SCENARIOS = [
    {
        "id": "single_turn_control",
        "title": "Control — single turn, no history",
        "why": "Baseline. If this fails the harness or connection is broken, "
               "not multi-turn.",
        "turns": [
            {
                "q": "How many CoCo use cases does Accenture have?",
                "expect_entities": ["Accenture"],
                "sql_required": True,
                "sql_must_contain": ["Accenture"],
                "probe": False,
            },
        ],
    },
    {
        "id": "pronoun_carryover",
        "title": "Pronoun carryover across three turns",
        "why": "'those' and 'their' must resolve to the partner named in turn 1 "
               "without the user repeating it.",
        "turns": [
            {
                "q": "Which single GSI partner has the most CoCo use cases? "
                     "Name only that one partner.",
                "sql_required": True,
                "probe": False,
                "capture_entity": True,
            },
            {
                "q": "How many of those are deployed?",
                "sql_required": True,
                "probe": True,
                "carry_from": 1,
                "expect_carried_entity": True,
            },
            {
                "q": "And what is their total EACV?",
                "sql_required": True,
                "probe": True,
                "carry_from": 1,
                "expect_carried_entity": True,
            },
        ],
    },
    {
        "id": "constraint_accumulation",
        "title": "Filter accumulation then entity swap",
        "why": "Turn 2 must add a stage filter while keeping the partner. "
               "Turn 3 must swap the partner but KEEP the stage filter.",
        "turns": [
            {
                "q": "Show me CoCo use cases for Accenture.",
                "sql_required": True,
                "sql_must_contain": ["Accenture"],
                "probe": False,
            },
            {
                "q": "Only the ones in stage 7.",
                "sql_required": True,
                "sql_must_contain": ["Accenture", "7"],
                "probe": True,
                "carry_from": 1,
            },
            {
                "q": "Now show the same thing for Deloitte instead.",
                "sql_required": True,
                "sql_must_contain": ["Deloitte", "7"],
                "sql_must_not_contain": ["Accenture"],
                "expect_entities": ["Deloitte"],
                "probe": True,
                "carry_from": 2,
            },
        ],
    },
    {
        "id": "user_correction",
        "title": "Mid-conversation correction",
        "why": "'Actually I meant X' must override the previous subject, not "
               "blend the two.",
        "turns": [
            {
                "q": "What is the CoCo adoption percentage for APJ RSI partners?",
                "sql_required": True,
                "probe": False,
            },
            {
                "q": "Actually I meant EMEA RSI partners.",
                "sql_required": True,
                "expect_entities": ["EMEA"],
                "probe": True,
                "carry_from": 1,
            },
        ],
    },
    {
        "id": "ordinal_reference",
        "title": "Ordinal reference into a prior result set",
        "why": "Answering 'the second one' requires the previous ROWS, not just "
               "the previous prose. The direct path replays SQL results; the "
               "agent path does not. Expected discriminator between the paths.",
        "turns": [
            {
                "q": "List the top 5 GSI partners by CoCo EACV, ranked.",
                "sql_required": True,
                "probe": False,
            },
            {
                "q": "What is the CoCo adoption percentage for the second one on that list?",
                "sql_required": True,
                "probe": True,
                "carry_from": 1,
            },
        ],
    },
    {
        "id": "deep_window_recall",
        "title": "Recall past the truncation window",
        "why": "Turn 5 references turn 1. The agent path keeps 4 messages "
               "(2 exchanges) and the direct path 6 (3 exchanges), so both are "
               "expected to have dropped turn 1. Documents the real limit.",
        "turns": [
            {
                "q": "Which NOAM RSI partner has the highest CoCo EACV? Name only that partner.",
                "sql_required": True,
                "probe": False,
                "capture_entity": True,
            },
            {"q": "How many total GSI use cases are there?", "probe": False},
            {"q": "What is the overall CoCo adoption percentage?", "probe": False},
            {"q": "How many use cases are in stage 7 overall?", "probe": False},
            {
                "q": "Going back to the very first partner I asked about — how many go-lives do they have?",
                "probe": True,
                "carry_from": 1,
                "expect_carried_entity": True,
            },
        ],
    },
]

JUDGE_RUBRIC = """You are grading whether an AI data assistant maintained CONVERSATIONAL MEMORY
across a multi-turn conversation. You are NOT grading whether the numbers are correct — you
cannot verify them. Grade ONLY context retention.

Score 1-5:
5 = Every follow-up correctly resolved its reference to earlier turns. No re-asking, no
    silent subject change, no generic non-answer.
4 = References resolved, but with minor hedging or a redundant clarification.
3 = One follow-up partially lost context (e.g. answered about the right entity but dropped
    an earlier filter, or asked the user to repeat something already established).
2 = A follow-up clearly lost the thread — wrong entity, ignored an established filter, or
    answered a different question than the reference implied.
1 = No evidence of memory. Follow-ups treated as standalone questions, or the assistant
    asked the user to restate context that was already given.

Red flags that cap the score at 2:
- Asking "which partner do you mean?" when a prior turn named exactly one partner.
- Switching to a different entity than the one under discussion, without the user asking.
- An error string, stack trace, or "failed" message presented as the answer.

Respond with STRICT JSON only, no prose outside it:
{"score": <1-5>, "verdict": "<one sentence>", "failure_mode": "<none|entity_lost|filter_lost|asked_user_to_repeat|error_response|other>"}
"""
