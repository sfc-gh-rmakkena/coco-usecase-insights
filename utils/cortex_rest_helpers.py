import json
import random
import time
import warnings

# Max attempts and backoff schedule for HTTP 429 ("too many requests") --
# see cortex_complete_rest's docstring for why this exists: raising the
# judge pipeline's worker count on the REST tab (_JUDGE_MAX_WORKERS 16->32,
# 2026-09-08) closes most of the RPM headroom gap vs. SQL COMPLETE, but a
# real account-usage check that day showed claude-sonnet-4-5 already at 84%
# of its 10M TPM budget at just 16-way concurrency (the "Skills" call embeds
# the full ~57K-token skill catalog on every request) -- pushing concurrency
# higher without retry logic would silently recreate the exact empty-
# Description/empty-skills bug this REST migration was meant to fix, just
# via 429 instead of truncation. Fixed delays with jitter, not the
# Retry-After header -- Snowflake's own docs say Cortex REST API responses
# don't include rate-limit headers (x-ratelimit-*, retry-after all listed as
# "Not supported").
_MAX_429_RETRIES = 4
_BACKOFF_BASE_S = 2.0


def cortex_complete_rest(conn, model: str, prompt: str, max_tokens: int = 16384) -> str:
    """Drop-in REST-API replacement for utils.cortex_helpers.cortex_complete --
    same (conn, model, prompt, max_tokens) signature, same plain-string return
    contract, same "raise on failure, let the caller's try/except handle it"
    behavior -- so every existing cortex_complete(...) call site can switch
    to this function with zero other code changes.

    Built for app_pages/pse_email_hybrid_rest.py, the REST-API twin of
    app_pages/pse_email_hybrid.py, after test_apps/cortex_rest_test proved
    the Cortex Messages REST API runs ~2.4x faster than SNOWFLAKE.CORTEX.
    COMPLETE under 16-way concurrent load (13.6s vs 32.9s for 16 calls, both
    16/16 correct) with zero cross-thread corruption on either path.

    Uses the Messages API (/api/v2/cortex/v1/messages, Claude-only) rather
    than Chat Completions, since every call site in this app targets
    "claude-sonnet-4-5" specifically.

    Path 1 (_snowflake.send_snow_api_request) is the officially-documented
    way to call REST endpoints from inside Streamlit-in-Snowflake without
    manual token handling -- kept for forward-compatibility, but the
    concurrency test proved `_snowflake` is NOT available in this app's
    container runtime (SYSTEM$ST_CONTAINER_RUNTIME_PY3_11): every REST call
    in that test hit ImportError and fell through to Path 2. Path 2 is
    therefore the real, proven path here: pull the raw connector's own
    active session token/host out from under Streamlit's st.connection
    wrapper and POST directly with `Authorization: Snowflake Token="..."`.
    Reading conn._instance.rest.token/.host is just attribute access on an
    already-established connection object, not a query -- safe to call from
    ThreadPoolExecutor worker threads (the same pattern the concurrency test
    exercised successfully at 16-way concurrency).

    Session-token auth is NOT one of the three officially recommended
    Cortex REST API auth methods (JWT / OAuth / PAT) -- it's used here only
    because PAT creation is blocked by this account's authentication policy.
    Per Snowflake's own "Known issues" docs for the Cortex REST API, an
    expired session token returns HTTP 200 with an embedded error code
    390112 rather than a clean HTTP error, so every response body is
    checked for that code even on success.
    """
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    attempt = 0
    while True:
        # --- Path 1: Snowflake SiS (_snowflake module available) ---
        try:
            import _snowflake
            try:
                resp = _snowflake.send_snow_api_request(
                    "POST", "/api/v2/cortex/v1/messages", {}, {}, payload, None, 60000,
                )
                raw = resp.get("content", "") if isinstance(resp, dict) else str(resp)
                return _extract_and_check(raw)
            except Exception as exc:  # noqa: BLE001 -- retry only on 429-like signals
                if _is_429(exc) and attempt < _MAX_429_RETRIES:
                    attempt += 1
                    time.sleep(_backoff_delay(attempt))
                    continue
                raise
        except ImportError:
            pass  # expected in this app's container runtime -- fall through to Path 2

        # --- Path 2: raw requests + the connection's own session token ---
        import requests
        conn_raw = conn._instance
        token = conn_raw.rest.token
        host = conn_raw.host
        url = f"https://{host}/api/v2/cortex/v1/messages"
        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
            "Accept": "application/json",
            "anthropic-version": "2023-06-01",
        }
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=120)
        if resp.status_code == 429:
            if attempt < _MAX_429_RETRIES:
                attempt += 1
                time.sleep(_backoff_delay(attempt))
                continue
            raise RuntimeError(
                f"Cortex REST API HTTP 429 (rate limited) after {_MAX_429_RETRIES} retries: "
                f"{resp.text[:300]}"
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Cortex REST API HTTP {resp.status_code}: {resp.text[:300]}")
        return _extract_and_check(resp.text)


def _is_429(exc: Exception) -> bool:
    """Best-effort 429 detection for the _snowflake.send_snow_api_request path,
    whose exception shape isn't documented -- match on status code attrs or
    the string "429" in the message rather than assuming a specific type."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 429:
        return True
    return "429" in str(exc)


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: attempt 1 ~2-3s, 2 ~4-5s, 3 ~8-9s, 4 ~16-17s."""
    return (_BACKOFF_BASE_S * (2 ** (attempt - 1))) + random.uniform(0, 1.0)


def _extract_and_check(raw) -> str:
    """Parse a Messages-API response body (dict or JSON string) into plain
    text, raising if it embeds error code 390112 (expired session token --
    see cortex_complete_rest's docstring) even though the HTTP status was
    200."""
    if not raw:
        return ""
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        return str(data)

    code = str(data.get("code", "")) or str((data.get("error") or {}).get("code", ""))
    if code == "390112":
        raise RuntimeError(f"Cortex REST API: expired session token (code 390112): {data}")

    blocks = data.get("content", [])
    if isinstance(blocks, list):
        return "".join(
            b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
    return ""
