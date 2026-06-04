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
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        current_schema = session.sql("SELECT CURRENT_SCHEMA()").collect()[0][0]
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
