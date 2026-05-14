import streamlit as st


def cortex_complete(conn, model, prompt):
    escaped = prompt.replace("\\", "\\\\").replace("'", "\\'")
    result = conn.query(f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{model}', '{escaped}') AS RESPONSE")
    return result.iloc[0]['RESPONSE'] if len(result) > 0 else ""
