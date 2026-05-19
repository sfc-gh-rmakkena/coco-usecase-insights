import streamlit as st
from utils.queries import get_distinct_partners
from utils import PARTNER_GROUPS
from datetime import date

st.set_page_config(
    page_title="CoCo Use Case Intelligence",
    page_icon=":material/cases:",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "conn" not in st.session_state:
    st.session_state.conn = st.connection("snowflake")

if "selected_region" not in st.session_state:
    st.session_state.selected_region = "Global"
if "selected_partners" not in st.session_state:
    st.session_state.selected_partners = []
if "okr_start_date" not in st.session_state:
    st.session_state.okr_start_date = date(2026, 5, 1)
if "okr_end_date" not in st.session_state:
    st.session_state.okr_end_date = date(2026, 7, 31)

with st.sidebar:
    st.selectbox(
        "Region",
        options=["Global", "NoAM", "EMEA", "APJ"],
        key="selected_region",
        help="Filter all pages by region"
    )
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
    st.divider()
    if st.button(":material/refresh: Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("**CoCo Use Case Intelligence**")
    st.caption("Built by #psegoingcoco")

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
        st.Page("app_pages/executive_email.py", title="Executive Email", icon=":material/mail:"),
    ],
})

page.run()
