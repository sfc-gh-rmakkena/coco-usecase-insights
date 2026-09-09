"""Persistent, content-addressed cache for the Approach 2 skill-grounding
judge pipeline (see docs/llm-judge-caching-recommendation.md for the design
rationale). Shared by both pse_email_hybrid.py (pipeline_tag='sql') and
pse_email_hybrid_rest.py (pipeline_tag='rest') -- the two pipelines stay
independently versioned/maintained, this module only owns the durable
storage layer underneath both.

Key idea: the cache key is a hash of the exact inputs that feed the judge's
prompts (name, desc, se_comments, partner_comments) plus a pipeline
tag/version. Same inputs -> same hash -> same stored result, forever, across
sessions/redeploys/weeks -- until an input actually changes (new hash,
guaranteed miss, fresh judgment) or the pipeline is intentionally
re-versioned (also a new hash, deliberate fresh judgment).

Deliberately NOT included in the hash: the deterministic candidate skill
list (`skills_key`). That list is itself just a computed function of
name/desc/se_comments/partner_comments (plus the TECHNICAL_USE_CASE
category) via map_coco_skills_explained/is_catalog_skill -- not an
independent signal -- so hashing it too would only make the key more
fragile to reproduce (e.g. for the one-time pdfs_went_out/ backfill, which
would otherwise have to re-run the deterministic tagger exactly as it stood
historically) for no real invalidation benefit: a change to the
deterministic-tagging logic itself is already treated as a
_JUDGE_PIPELINE_VERSION-bump event by this codebase's existing convention
(see the version-history comments above _JUDGE_PIPELINE_VERSION in both
app_pages files), so that invalidation path is covered without needing
skills_key in the hash.

PARTNER_NAME is stored as a plain column (not part of the hash) purely for
human readability/lookup -- confirmed earlier that partner identity never
feeds any of the judge's prompts, so it correctly has no bearing on the
cache key itself.
"""
import hashlib
import json

from utils.config import get_schema

TABLE = f"{get_schema()}.COCO_PSE_JUDGE_CACHE"


def ensure_table(conn):
    """Idempotent -- safe to call on every report generation.

    Uses conn.cursor() (raw DB-API cursor) rather than conn.query() --
    conn.query() (Streamlit's SnowflakeConnection helper) always calls
    fetch_pandas_all() on the result, which raises
    `NotSupportedError: Unknown error` for DDL statements like CREATE TABLE
    (their result set isn't Arrow-fetchable the way a SELECT's is). This
    was root-caused after a report generation, PDF-verified against
    `pdfs_went_out/`, showed zero cache hits despite the backfilled hash
    being byte-for-byte identical to what the live run recomputed -- the
    exception was previously swallowed silently by _judge_sanitize_batch's
    broad except, making every lookup silently degrade to a full miss with
    no visible error."""
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                CACHE_KEY_HASH   STRING NOT NULL,
                PIPELINE_TAG     STRING NOT NULL,
                PIPELINE_VERSION NUMBER NOT NULL,
                PARTNER_NAME     STRING,
                USE_CASE_NAME    STRING,
                SUMMARY          STRING,
                RATIONALE        STRING,
                SKILLS           VARIANT,
                JUDGE_REASONS    VARIANT,
                GPA_SCORES       VARIANT,
                CREATED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
                PRIMARY KEY (CACHE_KEY_HASH, PIPELINE_TAG)
            )
        """)


def compute_hash(name, desc, se_comments, partner_comments,
                  pipeline_tag: str, pipeline_version: int) -> str:
    """sha256 hex digest of the exact fields that feed the judge's prompts,
    plus a pipeline discriminator. Deterministic across processes/sessions --
    this IS the cache key. Same (name, desc, se_comments, partner_comments)
    -> same hash, forever, until one of those four actually changes or
    pipeline_version is deliberately bumped.

    Uses a rare delimiter (ASCII 0x1F, "unit separator") to join fields
    instead of JSON encoding -- deliberately, so the exact same hash can
    also be computed natively in SQL (plain string concatenation, no
    escaping ambiguity) for bulk backfill/audit work, e.g.:
        SHA2(name || CHR(31) || desc || CHR(31) || se_comments || CHR(31)
             || partner_comments || CHR(31) || pipeline_tag || CHR(31)
             || pipeline_version::STRING, 256)
    A JSON payload would require SQL's JSON serialization to exactly match
    Python's byte-for-byte (unicode escaping, control chars, etc.) to get
    the same hash -- fragile and easy to get subtly wrong. Plain
    concatenation has no such ambiguity as long as 0x1F never appears in
    real free-text business comments (it doesn't).

    Verified byte-for-byte equivalent SQL form (used by the one-time
    pdfs_went_out/ backfill to compute hashes in bulk without ever pulling
    full free-text columns through a truncating display) -- confirmed
    against em-dash, newline, backslash, and quote characters, and against
    Python's str.strip() (which strips more than SQL's default TRIM):
        WITH ws AS (SELECT ' '||CHR(9)||CHR(10)||CHR(13)||CHR(11)||CHR(12) AS C)
        SELECT SHA2(
            TRIM(name_col, ws.C) || CHR(31) ||
            TRIM(desc_col, ws.C) || CHR(31) ||
            TRIM(se_comments_col, ws.C) || CHR(31) ||
            TRIM(COALESCE(partner_comments_col, ''), ws.C) || CHR(31) ||
            'rest' || CHR(31) || '7', 256)
        FROM ws
    IMPORTANT: only safe on COLUMN references, never on hand-typed SQL
    string literals -- Snowflake single-quoted literals reinterpret
    backslash escape sequences (e.g. literal '\b' becomes a backspace
    control char) at parse time, which would silently produce a different
    hash than Python's raw string. Stored column values are unaffected
    (escape processing only happens during literal parsing), so this
    caveat never applies to real backfill data -- only matters if writing
    ad-hoc literal test strings containing a backslash."""
    payload = "\x1f".join([name, desc, se_comments, partner_comments,
                            pipeline_tag, str(pipeline_version)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def batch_lookup(conn, hashes: list, pipeline_tag: str) -> dict:
    """Returns {hash: entry_dict} for whichever of `hashes` already exist.
    entry_dict shape matches _judge_sanitize_batch's per-use-case result:
    {"summary", "rationale", "skills", "judge_reasons", "gpa_scores"}.
    hashes are our own sha256 hex digests (safe to interpolate directly --
    never raw user/partner text)."""
    if not hashes:
        return {}
    safe_tag = pipeline_tag.replace("'", "''")
    hash_list = ", ".join(f"'{h}'" for h in hashes)
    df = conn.query(f"""
        SELECT CACHE_KEY_HASH, SUMMARY, RATIONALE, SKILLS, JUDGE_REASONS, GPA_SCORES
        FROM {TABLE}
        WHERE PIPELINE_TAG = '{safe_tag}' AND CACHE_KEY_HASH IN ({hash_list})
    """, ttl=0)
    out = {}
    for _, row in df.iterrows():
        out[row["CACHE_KEY_HASH"]] = {
            "summary": row["SUMMARY"] or "",
            "rationale": row["RATIONALE"] or "",
            "skills": json.loads(row["SKILLS"]) if row["SKILLS"] else [],
            "judge_reasons": json.loads(row["JUDGE_REASONS"]) if row["JUDGE_REASONS"] else {},
            "gpa_scores": json.loads(row["GPA_SCORES"]) if row["GPA_SCORES"] else {},
        }
    return out


def batch_insert(conn, rows: list, pipeline_tag: str, pipeline_version: int):
    """rows: list of (hash, partner_name, use_case_name, entry_dict) tuples
    to persist. Plain INSERT (not MERGE) to match this repo's existing
    simple-write convention (see utils/queries.py's snapshot INSERTs) -- a
    rare concurrent double-insert of the same hash is harmless (batch_lookup
    just reads one of the duplicate rows), not worth the extra complexity of
    a MERGE here."""
    if not rows:
        return
    safe_tag = pipeline_tag.replace("'", "''")
    selects = []
    for h, partner_name, use_case_name, entry in rows:
        safe_partner = (partner_name or "").replace("'", "''")
        safe_uc_name = (use_case_name or "").replace("'", "''")
        summary = (entry.get("summary") or "").replace("'", "''")
        rationale = (entry.get("rationale") or "").replace("'", "''")
        skills_json = json.dumps(entry.get("skills") or []).replace("'", "''")
        judge_reasons_json = json.dumps(entry.get("judge_reasons") or {}).replace("'", "''")
        gpa_scores_json = json.dumps(entry.get("gpa_scores") or {}).replace("'", "''")
        # Snowflake's INSERT...VALUES does not accept PARSE_JSON() (or other
        # function calls) in the literal VALUES list -- only INSERT...SELECT
        # does. Hence UNION ALL SELECT rather than a VALUES(...) list here.
        selects.append(
            f"SELECT '{h}', '{safe_tag}', {pipeline_version}, '{safe_partner}', '{safe_uc_name}', "
            f"'{summary}', '{rationale}', "
            f"PARSE_JSON('{skills_json}'), PARSE_JSON('{judge_reasons_json}'), PARSE_JSON('{gpa_scores_json}')"
        )
    conn.query(f"""
        INSERT INTO {TABLE}
            (CACHE_KEY_HASH, PIPELINE_TAG, PIPELINE_VERSION, PARTNER_NAME, USE_CASE_NAME,
             SUMMARY, RATIONALE, SKILLS, JUDGE_REASONS, GPA_SCORES)
        {' UNION ALL '.join(selects)}
    """, ttl=0)
