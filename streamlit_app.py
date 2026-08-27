import streamlit as st
from utils.queries import get_distinct_partners, get_distinct_subregions
from utils import PARTNER_GROUPS
from utils.ask_ai import ask_ai, ask_ai_agent
from datetime import date, timedelta

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
if "selected_subregions" not in st.session_state:
    st.session_state.selected_subregions = []
if "selected_partners" not in st.session_state:
    st.session_state.selected_partners = list(PARTNER_GROUPS)
if "okr_start_date" not in st.session_state:
    st.session_state.okr_start_date = date(2026, 8, 1)
if "okr_end_date" not in st.session_state:
    st.session_state.okr_end_date = date(2026, 10, 31)
if "include_account_coco" not in st.session_state:
    st.session_state.include_account_coco = "Yes"
if "confidence_filter" not in st.session_state:
    st.session_state.confidence_filter = ["High"]
if "selected_stages" not in st.session_state:
    st.session_state.selected_stages = []
    st.session_state.ask_ai_history = []
if "ask_ai_context" not in st.session_state:
    st.session_state.ask_ai_context = ""
with st.sidebar:
    st.selectbox(
        "Region",
        options=["Global", "NoAM", "EMEA", "APJ", "LATAM"],
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

    # Sub-region sits one level below theatre. Its options depend on the theatre
    # selected above, because the values are industries under USMajors, countries
    # under APJ and sub-geographies under EMEA. Empty selection means all.
    _subregion_options = get_distinct_subregions(
        st.session_state.conn, region=st.session_state.selected_region
    )
    _kept = [s for s in st.session_state.get("selected_subregions", [])
             if s in _subregion_options]
    if _kept != st.session_state.get("selected_subregions", []):
        st.session_state.selected_subregions = _kept
    st.multiselect(
        "Sub-region",
        options=_subregion_options,
        key="selected_subregions",
        help="Level below Theater: industry for USMajors (HCLS, FSI, TMT), country "
             "for APJ, sub-geography for EMEA. Empty = all.",
    )
    # Remove "All" from the options list for multiselect (empty = all)
    partner_options = [p for p in partners if p != "All"]
    # Add group options at the top
    partner_options = PARTNER_GROUPS + partner_options
    st.multiselect(
        "Partners",
        options=partner_options,
        key="selected_partners",
        help="Select group (GSIs/NOAM RSIs) or individual partners. Leave empty for all."
    )
    st.multiselect(
        "Use Case Stage",
        options=[
            "3 - Technical / Business Validation",
            "4 - Use Case Won / Migration Plan",
            "5 - Implementation In Progress",
            "6 - Implementation Complete",
            "7 - Deployed",
        ],
        key="selected_stages",
        help="Filter by use case stage. Leave empty to include all stages."
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

    show_debug = st.toggle("SQL debug", value=False, key="ask_ai_debug")
    use_agent = st.toggle("Use Agent (more accurate)", value=True, key="ask_ai_use_agent")

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
                if use_agent:
                    result = ask_ai_agent(question, chat_history=st.session_state.ask_ai_history)
                else:
                    page_ctx = st.session_state.get("ask_ai_context", "")
                    result = ask_ai(conn, question, page_ctx, debug=show_debug,
                                   chat_history=st.session_state.ask_ai_history)

            if show_debug and isinstance(result, dict):
                response = result["answer"]
                st.markdown(response)
                with st.expander("SQL Debug", expanded=True):
                    sql_needed = result.get("sql_needed", result.get("sql") is not None)
                    st.write(f"**SQL generated:** {'Yes' if sql_needed else 'No — answered from page context'}")
                    gen_sql = result.get("generated_sql") or result.get("sql") or "(no SQL extracted — answered from context)"
                    if sql_needed and gen_sql != "(no SQL extracted — answered from context)":
                        st.code(gen_sql, language="sql")
                    else:
                        st.info(gen_sql)
                    sql_res = result.get("sql_result") or "(no result)"
                    if sql_res and sql_res != "(no result)":
                        st.write("**SQL result (first 1000 chars):**")
                        st.text(sql_res[:1000])
                    if result.get("step1_decision"):
                        st.write("**Step 1 decision:**")
                        st.text(result["step1_decision"])
            else:
                response = result.get("answer", "") if isinstance(result, dict) else result
                st.markdown(response)

        # Don't persist failed calls: an error string stored as an assistant turn
        # poisons the context of every following question.
        if isinstance(result, dict) and result.get("error"):
            st.warning("That call failed, so it was not added to the chat history.")
        else:
            st.session_state.ask_ai_history.append({"role": "user", "content": question})
            # Store SQL + result in history so follow-up questions can reference previous query context
            _hist_entry = {"role": "assistant", "content": response}
            if isinstance(result, dict):
                if result.get("sql"):
                    _hist_entry["sql"] = result["sql"]
                if result.get("sql_result"):
                    _hist_entry["sql_result"] = result["sql_result"]
            st.session_state.ask_ai_history.append(_hist_entry)

    if history:
        if st.button("Clear chat", key="ask_ai_clear", use_container_width=True):
            st.session_state.ask_ai_history = []
            st.rerun()

# Executive Email is restricted to a named list. This hides the nav entry; it is a
# UI convenience, NOT a security control - the page is also guarded on entry, but
# anyone with access to this app can still query the underlying views directly.
EXEC_EMAIL_USERS = {"RMAKKENA", "NIRASHAH", "SDOGRA", "PLAKHANPAL"}


@st.cache_data(ttl=timedelta(minutes=30))
def _current_snowflake_user(_conn) -> str:
    """Snowflake login of the viewer. Empty string if it cannot be determined."""
    try:
        df = _conn.query("SELECT CURRENT_USER() AS U", ttl=0)
        return str(df.iloc[0]["U"]).strip().upper() if len(df) else ""
    except Exception:
        return ""


_viewer = _current_snowflake_user(st.session_state.conn)
st.session_state.exec_email_allowed = _viewer in EXEC_EMAIL_USERS

_okr_pages = [
    st.Page("app_pages/okr_adoption.py", title="OKR: CoCo Adoption", icon=":material/check_circle:"),
]
if st.session_state.exec_email_allowed:
    _okr_pages.append(
        st.Page("app_pages/executive_email.py", title="Executive Email", icon=":material/mail:")
    )

page = st.navigation({
    "Overview": [
        st.Page("app_pages/overview.py", title="Adoption Metrics", icon=":material/monitoring:"),
    ],
    "Use Cases": [
        st.Page("app_pages/pipeline.py", title="Pipeline & Funnel", icon=":material/filter_alt:"),
        st.Page("app_pages/deep_dive.py", title="Use Case Explorer", icon=":material/search_insights:"),
        st.Page("app_pages/comments_intelligence.py", title="Comments & AI Insights", icon=":material/smart_toy:"),
        st.Page("app_pages/trends.py", title="Trends & Aging", icon=":material/trending_up:"),
        st.Page("app_pages/partner_consultants.py", title="Partner Consultants", icon=":material/groups:"),
    ],
    "OKR & Reports": _okr_pages,
    "AIM & FDE": [
        st.Page("app_pages/aim_adoption.py", title="AIM Adoption", icon=":material/rocket_launch:"),
    ],
})

page.run()
