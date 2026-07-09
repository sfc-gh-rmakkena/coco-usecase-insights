import streamlit as st
from utils.queries import get_distinct_partners
from utils import PARTNER_GROUPS
from utils.ask_ai import ask_ai
from datetime import date

st.set_page_config(
    page_title="CoCo Use Case Intelligence",
    page_icon=":material/cases:",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "conn" not in st.session_state:
    st.session_state.conn = st.connection("snowflake")

if "_ui_region" not in st.session_state:
    st.session_state._ui_region = "Global"
if "selected_region" not in st.session_state:
    st.session_state.selected_region = "Global"
if "selected_theater" not in st.session_state:
    st.session_state.selected_theater = "All"
if "selected_partners" not in st.session_state:
    st.session_state.selected_partners = []
if "okr_start_date" not in st.session_state:
    st.session_state.okr_start_date = date(2026, 5, 1)
if "okr_end_date" not in st.session_state:
    st.session_state.okr_end_date = date(2026, 7, 31)
if "include_account_coco" not in st.session_state:
    st.session_state.include_account_coco = "Yes"
if "confidence_filter" not in st.session_state:
    st.session_state.confidence_filter = ["High"]
if "ask_ai_history" not in st.session_state:
    st.session_state.ask_ai_history = []
if "ask_ai_context" not in st.session_state:
    st.session_state.ask_ai_context = ""
with st.sidebar:
    st.selectbox(
        "Region",
        options=["Global", "NoAM", "EMEA", "APJ"],
        key="_ui_region",
        help="Filter all pages by region"
    )
    st.selectbox(
        "Theater",
        options=["All", "AMSExpansion", "USMajors", "USPubSec", "AMSAcquisition"],
        key="selected_theater",
        help="Filter by NoAM theater. Only applies when Region is NoAM or Global."
    )
    # Compute effective region: theater name overrides NoAM/Global for query cache keying
    _theater = st.session_state.selected_theater
    _ui_reg = st.session_state._ui_region
    if _theater != "All" and _ui_reg in ("NoAM", "Global"):
        st.session_state.selected_region = _theater
    else:
        st.session_state.selected_region = _ui_reg
    partners = get_distinct_partners(st.session_state.conn, region=st.session_state.selected_region)
    # Remove "All" from the options list for multiselect (empty = all)
    partner_options = [p for p in partners if p != "All"]
    # Add group options at the top
    partner_options = PARTNER_GROUPS + partner_options
    st.multiselect(
        "Partners",
        options=partner_options,
        key="selected_partners",
        help="Select group (GSIs/Regional SIs) or individual partners. Leave empty for all."
    )
    st.divider()
    st.date_input("OKR Start Date", key="okr_start_date", help="Start of reporting period")
    st.date_input("OKR End Date", key="okr_end_date", help="End of reporting period")
    st.selectbox(
        "Account Level CoCo",
        options=["Yes", "No"],
        key="include_account_coco",
        help="Include account-level CoCo usage in attribution (customer accounts with product usage)"
    )
    st.multiselect(
        "Account Level CoCo Adoption Confidence",
        options=["High", "Medium"],
        key="confidence_filter",
        help="Filter account-level CoCo attribution by confidence band. Default: High only."
    )
    st.divider()
    if st.button(":material/refresh: Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("**CoCo Use Case Intelligence**")
    st.caption("Built by #psegoingcoco")

    # Ask AI chat
    st.divider()
    st.markdown("**Ask AI**")
    conn = st.session_state.conn

    # Display last 3 exchanges
    history = st.session_state.ask_ai_history
    for msg in history[-6:]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if question := st.chat_input("Ask about the data...", key="ask_ai_input"):
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                page_ctx = st.session_state.get("ask_ai_context", "")
                response = ask_ai(conn, question, page_ctx)
            st.markdown(response)
        st.session_state.ask_ai_history.append({"role": "user", "content": question})
        st.session_state.ask_ai_history.append({"role": "assistant", "content": response})

    if history:
        if st.button("Clear chat", key="ask_ai_clear", use_container_width=True):
            st.session_state.ask_ai_history = []
            st.rerun()

page = st.navigation({
    "Overview": [
        st.Page("app_pages/overview.py", title="Adoption Metrics", icon=":material/monitoring:"),
    ],
    "Use Cases": [
        st.Page("app_pages/pipeline.py", title="Pipeline & Funnel", icon=":material/filter_alt:"),
        st.Page("app_pages/deep_dive.py", title="Use Case Explorer", icon=":material/search_insights:"),
        st.Page("app_pages/comments_intelligence.py", title="Comments & AI Insights", icon=":material/smart_toy:"),
        st.Page("app_pages/trends.py", title="Trends & Aging", icon=":material/trending_up:"),
    ],
    "OKR & Reports": [
        st.Page("app_pages/okr_summary.py", title="OKR: CoCo Coverage", icon=":material/dashboard:"),
        st.Page("app_pages/okr_adoption.py", title="OKR: CoCo Adoption", icon=":material/check_circle:"),
        st.Page("app_pages/partner_velocity.py", title="Partner Velocity", icon=":material/speed:"),
        st.Page("app_pages/executive_email.py", title="Executive Email", icon=":material/mail:"),
    ],
})

page.run()
