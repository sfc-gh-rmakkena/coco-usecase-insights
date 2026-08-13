import json
import streamlit as st


def cortex_complete(conn, model, prompt):
    escaped = prompt.replace("\\", "\\\\").replace("'", "\\'")
    result = conn.query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}', '{escaped}') AS RESPONSE")
    return result.iloc[0]['RESPONSE'] if len(result) > 0 else ""


def _format_result_set(rs) -> str:
    """Render a Cortex Agent ResultSet (SQL API shape) as plain text."""
    if not isinstance(rs, dict):
        return ""
    meta = rs.get("resultSetMetaData") or {}
    cols = [c.get("name", "") for c in (meta.get("rowType") or [])]
    rows = rs.get("data") or []
    lines = []
    if cols:
        lines.append(" | ".join(cols))
    for row in rows[:20]:
        lines.append(" | ".join("" if v is None else str(v) for v in row))
    if len(rows) > 20:
        lines.append(f"... ({len(rows)} rows total)")
    return "\n".join(lines)


def _extract_tool_output(content_items):
    """Pull (sql, result_text) out of an agent response `content` array.

    Documented shape (Cortex Agents Run API — MessageContentItem/tool_result):
        {"type": "tool_result",
         "tool_result": {"content": [{"type": "json",
                                      "json": {"sql": ..., "result_set": {...}}}]}}

    Since Apr 2026 the tool type is `system_execute_sql` (previously
    `cortex_analyst_text_to_sql`); both nest the payload identically. Also
    tolerates a flattened `content` and a `text`/`answer` json field so older
    payload variants still yield something.
    """
    sql = None
    result_text = None
    for item in content_items or []:
        if item.get("type") not in ("tool_result", "tool_results"):
            continue
        tr = item.get("tool_result") or item.get("tool_results") or item
        inner = tr.get("content") if isinstance(tr, dict) else None
        if not isinstance(inner, list):
            inner = item.get("content") if isinstance(item.get("content"), list) else []
        for c in inner:
            if c.get("type") == "text" and not result_text:
                result_text = c.get("text")
                continue
            payload = c.get("json")
            if not isinstance(payload, dict):
                continue
            sql = payload.get("sql", sql)
            if payload.get("result_set") is not None:
                rendered = _format_result_set(payload["result_set"])
                if rendered:
                    result_text = rendered
            elif payload.get("text") and not result_text:
                result_text = payload["text"]
    return sql, result_text


def _parse_agent_sse(response) -> dict:
    """Parse SSE stream from Cortex Agent REST API.

    The API uses named SSE events. The final answer arrives as:
        event: response
        data: {"content": [{"type": "text", "text": "..."}, ...]}

    Text delta chunks arrive as event: message.delta but we use the final
    'response' event which has the complete assembled answer.
    """
    event_type = None
    final_response = None
    delta_parts = []
    sql_text = None
    sql_result_text = None

    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8") if isinstance(line, bytes) else line

        if decoded.startswith("event: "):
            event_type = decoded[7:].strip()
            continue

        if not decoded.startswith("data: "):
            continue

        raw_json = decoded[6:].strip()
        if raw_json == "[DONE]":
            break

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        if event_type == "response":
            # Final complete response
            final_response = data

        elif event_type == "message.delta":
            # Incremental text delta — accumulate as fallback
            for item in data.get("delta", {}).get("content", []):
                if item.get("type") == "text":
                    delta_parts.append(item.get("text", ""))

    # Extract from final 'response' event (preferred)
    if final_response:
        answer_parts = []
        for item in final_response.get("content", []):
            if item.get("type") == "text":
                answer_parts.append(item.get("text", ""))
        sql_text, sql_result_text = _extract_tool_output(final_response.get("content", []))
        return {
            "answer": "".join(answer_parts).strip(),
            "sql": sql_text,
            "sql_result": sql_result_text,
        }

    # Fallback: use accumulated delta text
    return {
        "answer": "".join(delta_parts).strip(),
        "sql": sql_text,
        "sql_result": sql_result_text,
    }


def run_cortex_agent(question: str, agent_fqn: str = "TEMP.COCO_PARTNER_ADOPTION.COCO_AGENT",
                     chat_history: list = None) -> dict:
    """Call a Cortex Agent via REST API. Works in both Snowflake SiS and locally."""
    messages = []
    if chat_history:
        for msg in chat_history[-4:]:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": [{"type": "text", "text": msg["content"]}]})
    messages.append({"role": "user", "content": [{"type": "text", "text": question}]})

    parts = agent_fqn.split(".")
    db, schema, name = parts[0], parts[1], parts[2]
    payload = {"messages": messages}

    # --- Path 1: Snowflake SiS (_snowflake module available) ---
    try:
        import _snowflake
        resp = _snowflake.send_snow_api_request(
            "POST",
            f"/api/v2/databases/{db}/schemas/{schema}/agents/{name}:run",
            {},
            {},
            payload,
            None,
            60000,
        )
        # SiS returns content as a JSON array of event objects:
        # [{"event": "response.thinking.delta", "data": {...}}, ..., {"event": "response", "data": {...}}]
        raw = resp.get("content", "") if isinstance(resp, dict) else str(resp)
        final_response = None
        delta_parts = []
        sql_text = None
        sql_result_text = None

        # Try JSON array format (SiS native format)
        try:
            events = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(events, list):
                for event in events:
                    evt = event.get("event", "")
                    data = event.get("data", {})
                    if evt == "response":
                        final_response = data
                    elif evt == "message.delta":
                        for item in data.get("delta", {}).get("content", []):
                            if item.get("type") == "text":
                                delta_parts.append(item.get("text", ""))
        except (json.JSONDecodeError, TypeError, AttributeError):
            # Fallback: try SSE line format
            event_type = None
            for line in (raw or "").splitlines():
                line = line.strip()
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                    continue
                if not line.startswith("data: "):
                    continue
                raw_json = line[6:].strip()
                if raw_json == "[DONE]":
                    break
                try:
                    data = json.loads(raw_json)
                except json.JSONDecodeError:
                    continue
                if event_type == "response":
                    final_response = data
                elif event_type == "message.delta":
                    for item in data.get("delta", {}).get("content", []):
                        if item.get("type") == "text":
                            delta_parts.append(item.get("text", ""))

        if final_response:
            answer_parts = []
            for item in final_response.get("content", []):
                if item.get("type") == "text":
                    answer_parts.append(item.get("text", ""))
            sql_text, sql_result_text = _extract_tool_output(final_response.get("content", []))
            return {"answer": "".join(answer_parts).strip(), "sql": sql_text, "sql_result": sql_result_text}

        fallback = "".join(delta_parts).strip()
        return {"answer": fallback or "No response from agent.", "sql": sql_text, "sql_result": sql_result_text}

    except ImportError:
        pass  # not in SiS
    except Exception as e:
        return {"answer": f"Agent call failed (SiS path): {e}", "sql": None, "sql_result": None,
                "error": True}

    # --- Path 2: Local development — direct REST via requests ---
    try:
        import requests

        conn_raw = st.connection("snowflake")._instance
        token = conn_raw.rest.token
        host = conn_raw.host

        url = f"https://{host}/api/v2/databases/{db}/schemas/{schema}/agents/{name}:run"
        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        import warnings
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

        response = requests.post(url, headers=headers, json=payload, stream=True, verify=False, timeout=120)

        if response.status_code != 200:
            return {
                "answer": f"Agent API error {response.status_code}: {response.text[:400]}",
                "sql": None,
                "sql_result": None,
                "error": True,
            }

        # Collect all raw lines for parsing (also keeps them for debug)
        raw_lines = []
        event_type = None
        final_response = None
        delta_parts = []
        sql_text = None
        sql_result_text = None

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8") if isinstance(line, bytes) else line
            raw_lines.append(decoded)

            if decoded.startswith("event: "):
                event_type = decoded[7:].strip()
                continue
            if not decoded.startswith("data: "):
                continue
            raw_json = decoded[6:].strip()
            if raw_json == "[DONE]":
                break
            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            if event_type == "response":
                final_response = data
            elif event_type == "message.delta":
                for item in data.get("delta", {}).get("content", []):
                    if item.get("type") == "text":
                        delta_parts.append(item.get("text", ""))

        if final_response:
            answer_parts = []
            for item in final_response.get("content", []):
                if item.get("type") == "text":
                    answer_parts.append(item.get("text", ""))
            sql_text, sql_result_text = _extract_tool_output(final_response.get("content", []))
            answer = "".join(answer_parts).strip()
            if answer:
                return {"answer": answer, "sql": sql_text, "sql_result": sql_result_text}

        # Fallback: delta text
        fallback = "".join(delta_parts).strip()
        if fallback:
            return {"answer": fallback, "sql": sql_text, "sql_result": sql_result_text}

        # Last resort: return raw lines so user can see what came back
        raw_dump = "\n".join(raw_lines[:30])
        return {"answer": f"(Could not parse agent response. Raw output below)\n```\n{raw_dump}\n```", "sql": None, "sql_result": None,
                "error": True}

    except Exception as e:
        return {"answer": f"Agent call failed (local path): {e}", "sql": None, "sql_result": None,
                "error": True}
