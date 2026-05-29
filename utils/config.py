import os


def get_env() -> str:
    # 1. Explicit override via secrets.toml (local dev only)
    try:
        import streamlit as st
        env = st.secrets.get("ENV", None)
        if env:
            return env.lower()
    except Exception:
        pass

    # 2. Explicit override via OS env var
    env = os.getenv("APP_ENV", None)
    if env:
        return env.lower()

    # 3. Auto-detect from Snowflake session schema (works in Snowflake SiS)
    # DEV app is deployed in COCO_PARTNER_ADOPTION_DEV schema
    try:
        import streamlit as st
        conn = st.connection("snowflake")
        result = conn.query("SELECT CURRENT_SCHEMA() AS S", ttl=3600)
        current_schema = result.iloc[0]["S"] if len(result) > 0 else ""
        if "DEV" in current_schema.upper():
            return "dev"
    except Exception:
        pass

    # 4. Default: prod
    return "prod"


def get_schema() -> str:
    if get_env() == "dev":
        return "TEMP.COCO_PARTNER_ADOPTION_DEV"
    return "TEMP.COCO_PARTNER_ADOPTION"


def get_warehouse() -> str:
    return "COCO_PARTNER_ADOPTION_WH"
