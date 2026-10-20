import hashlib
import json

from .compliance import sql_quote

from utils.config import get_schema


def _t(name):
    return f"{get_schema()}.{name}"


def ensure_tables(conn):
    # DDL via raw cursor, same as utils/judge_cache.ensure_table: conn.query()
    # calls fetch_pandas_all(), which raises NotSupportedError on DDL.
    with conn.cursor() as cur:
        cur.execute(f"""CREATE TABLE IF NOT EXISTS {_t('COCO_PSE_WORKSHOP_CACHE')} (
            CACHE_KEY_HASH STRING, ASSET_VERSION STRING, PARTNER_NAME STRING, USE_CASE_ID STRING,
            PAYLOAD VARIANT, CREATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""")
        cur.execute(f"""CREATE TABLE IF NOT EXISTS {_t('WORKSHOP_GENERATION_AUDIT')} (
            PARTNER_NAME STRING, USE_CASE_ID STRING, PATH STRING, CACHE_HIT BOOLEAN,
            GENERATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""")


def compute_hash(inputs: dict, asset_version: str) -> str:
    blob = json.dumps(inputs, sort_keys=True, default=str) + "\x1f" + asset_version
    return hashlib.sha256(blob.encode()).hexdigest()


_q = sql_quote
MAX_ROWS_PER_INSERT = 20
MAX_SQL_CHARS = 400_000


def lookup(conn, hashes: list) -> dict:
    if not hashes:
        return {}
    df = conn.query(f"""SELECT CACHE_KEY_HASH, PAYLOAD FROM {_t('COCO_PSE_WORKSHOP_CACHE')}
        WHERE CACHE_KEY_HASH IN ({', '.join(f"'{_q(h)}'" for h in hashes)})
        QUALIFY ROW_NUMBER() OVER (PARTITION BY CACHE_KEY_HASH ORDER BY CREATED_AT DESC) = 1""", ttl=0)
    out = {}
    for _, r in df.iterrows():
        p = r["PAYLOAD"]
        out[r["CACHE_KEY_HASH"]] = json.loads(p) if isinstance(p, str) else p
    return out


def insert(conn, rows: list, asset_version: str = ""):
    """rows: (hash, partner, uc_id, payload_dict)."""
    if not rows:
        return
    head = f"""INSERT INTO {_t('COCO_PSE_WORKSHOP_CACHE')}
        (CACHE_KEY_HASH, ASSET_VERSION, PARTNER_NAME, USE_CASE_ID, PAYLOAD) """
    sep = " UNION ALL "
    chunk, size = [], len(head)

    def _flush():
        if chunk:
            conn.query(head + sep.join(chunk), ttl=0)

    for h, p, u, pl in rows:
        sel = (f"SELECT '{_q(h)}', '{_q(asset_version)}', '{_q(p)}', '{_q(u)}', "
               f"PARSE_JSON('{_q(json.dumps(pl))}')")
        if chunk and (len(chunk) >= MAX_ROWS_PER_INSERT or size + len(sep) + len(sel) > MAX_SQL_CHARS):
            _flush()
            chunk, size = [], len(head)
        chunk.append(sel)
        size += len(sep) + len(sel)
    _flush()


def audit(conn, rows: list):
    """rows: (partner, uc_id, path, cache_hit)."""
    if not rows:
        return
    sel = " UNION ALL ".join(f"SELECT '{_q(p)}', '{_q(u)}', '{_q(path)}', {str(bool(hit)).upper()}"
                             for p, u, path, hit in rows)
    conn.query(f"""INSERT INTO {_t('WORKSHOP_GENERATION_AUDIT')}
        (PARTNER_NAME, USE_CASE_ID, PATH, CACHE_HIT) {sel}""", ttl=0)
