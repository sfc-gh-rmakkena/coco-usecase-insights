# Caching recommendation for Cortex LLM-judge pipelines

Context: this was written after observing that the CoCo skill "grounding
judge" (Approach 2, `pse_email_hybrid.py`) recommended different skills for
the same partner across different report generations. Root-caused (see
below) and captured here so the pattern can be reused wherever else this
app (or a future one) makes repeated Cortex LLM calls over the same
underlying business data.

## Why identical prompts can return different answers

`temperature=0` / `top_p=0` (Cortex's defaults) only make the *sampling*
step deterministic — they force the model to always pick its single
highest-probability token. They do **not** make the underlying computation
that produces those probabilities deterministic:

- Cloud LLM providers batch multiple users' concurrent requests together on
  shared GPUs for throughput. Floating-point addition isn't associative —
  `(a+b)+c` can differ from `a+(b+c)` in the last bits — and the reduction
  order inside GPU kernels depends on the batch shape, which depends on
  whatever other traffic happens to be running at that instant. You have no
  control over that as an API caller.
- A sub-percent logit wobble (e.g. `14.0000018` vs `13.9999992`) is enough
  to flip which token is picked, and once one token flips, the rest of that
  generation can diverge onto a different path.
- This is a documented, industry-wide limitation of hosted multi-tenant LLM
  inference (see Thinking Machines Lab, "Defeating Nondeterminism in LLM
  Inference," and multiple independent write-ups reaching the same
  conclusion) — not a Snowflake Cortex-specific bug, and not fixable by any
  `model_parameters`/`options` value Cortex exposes. There is no `seed`
  parameter in `SNOWFLAKE.CORTEX.COMPLETE` / `AI_COMPLETE`.
- Practical consequence for judge/classification pipelines specifically:
  when a decision is made against a numeric threshold (e.g. "admit this
  skill if context_relevance >= 0.7"), a borderline case sitting right at
  that boundary is exactly where a tiny inference-level variance flips the
  outcome — which is why symptoms show up as "different skills/labels
  chosen," not as generic gibberish.

**Conclusion: don't try to eliminate inference-level nondeterminism at the
model-call layer.** It can't be tuned away with parameters, and Cortex
doesn't expose the batch-invariance controls that self-hosted stacks use to
solve this. Instead, make the *system* deterministic by making sure any
given input is only ever sent to the model once.

## The fix: content-addressed caching, not use-case-ID caching

Key the cache on the actual input content (a hash of the raw fields the
prompt is built from), **not** on a row/entity ID:

```python
cache_key = (desc, se_comments, partner_comments, name, skills_key, PIPELINE_VERSION)
```

This one design choice gives you two properties for free, with zero extra
logic:

1. **Stability.** The same input always resolves to the same cache entry,
   so repeat report generations for unchanged data are guaranteed
   byte-identical (a pure cache hit, no new model call at all).
2. **Automatic invalidation when source data changes.** If an SE updates
   their comments or a partner note changes, the tuple changes, so the hash
   changes, so it's a cache **miss** — a fresh judgment is computed
   automatically. The old entry (keyed on the old text) simply becomes an
   orphan that can never be looked up again; no explicit invalidation logic
   is needed.
3. **Automatic invalidation on prompt/logic changes.** Including a
   `PIPELINE_VERSION` int in the key means bumping that constant after any
   prompt wording, parsing, or scoring-logic change forces fresh judgments
   for everything, even though the underlying business data didn't change —
   without needing to touch or clear the cache store itself.

This is strictly better than trying to cache by `use_case_id` (or any other
row identifier) and separately tracking "has this row's text changed since
we last judged it" — the content hash makes that tracking implicit.

## Where to put the cache: session-scoped is fine for most cases

For this app, `st.session_state` (in-memory, per-browser-session) was the
right call, not over-engineering:

```python
cache = st.session_state.setdefault("_pse_hybrid_judge_cache", {})
```

Pros: zero infrastructure, zero migration risk, trivially correct within a
session (a user regenerating the same report repeatedly never re-triggers
the LLM). Cons: it resets on page reload, new browser tab/session, or a
container restart (e.g. `DROP STREAMLIT` + redeploy) — so a user *will*
occasionally see the model asked fresh and (per the nondeterminism above)
occasionally land on a different borderline call than a previous session.

**When to upgrade to a persistent store instead** (a Snowflake table keyed
by the same content hash, looked up before falling through to the LLM):
only if the *frequency* of fresh-cache-miss reports crossing borderline
judgments becomes a real problem in practice — e.g. many different users
generating the same partner's report across many separate sessions/days,
or frequent redeploys during active development wiping useful cache state
repeatedly. Skipped here as unnecessary complexity for the actual usage
pattern (one browser session per PSE, occasional regeneration), but the
design is a straightforward extension of the same content-hash idea if it's
ever needed:

```sql
CREATE TABLE IF NOT EXISTS <db>.<schema>.JUDGE_CACHE (
    CACHE_KEY_HASH   STRING PRIMARY KEY,   -- sha256 of the same tuple, joined
    PIPELINE_VERSION NUMBER,
    <...judge output columns...>,
    CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

Lookup by hash before calling the LLM; insert on miss. Same
auto-invalidation behavior as the in-memory version (new text -> new hash
-> miss -> fresh row), just durable across sessions/redeploys. If adopted,
also plan a periodic `DELETE WHERE PIPELINE_VERSION < N` so superseded rows
from old prompt versions don't accumulate forever.

## Checklist for any future Cortex-judge/classification pipeline in this repo

- [ ] Key the cache on a hash/tuple of the actual raw input fields the
      prompt is built from — never on a row ID alone.
- [ ] Include a `PIPELINE_VERSION` (or similar) constant in the key; bump it
      whenever the prompt, parsing, or decision logic changes.
- [ ] Default to `st.session_state` (or equivalent in-process cache) unless
      you have a concrete, observed need (not a hypothetical one) for
      cross-session durability.
- [ ] Don't try to fix output instability by tuning `temperature`/`top_p` if
      they're already at their most deterministic setting (`0`) — that's
      not the source of the variance, and no Cortex parameter can remove
      GPU-batching-induced nondeterminism.
- [ ] Set expectations with stakeholders: cache hits are exactly
      reproducible; a genuine cache miss (new/changed input, or a fresh
      session/container) can legitimately produce a different answer than
      last time on borderline cases, and that's a property of hosted LLM
      inference in general, not a bug in this app.
