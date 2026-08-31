import streamlit as st
import pandas as pd
import random
import re
import string
from datetime import date

from utils import (
    APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, LATAM_RSI_REGION_MAP,
    PARTNER_RENAME_MAP, PARTNER_ALIASES as _PA,
)

# Build the managed partner list the same way executive_email.py does
_NOAM_RSI = frozenset(
    p for p in _PA.get('--- NOAM RSIs ---', []) if not p.startswith('---')
) | {'LTI Mindtree', 'Kipi.ai'}

MANAGED_PARTNERS = list(
    {'Accenture', 'Capgemini Technologies LLC', 'Cognizant Technology Solutions US Corp',
     'Deloitte Consulting', 'EY', 'Ernst & Young (EY)', 'IBM', 'IBM Consulting'}
    | _NOAM_RSI
    | frozenset(APJ_RSI_REGION_MAP.keys())
    | frozenset(EMEA_RSI_REGION_MAP.keys())
    | frozenset(LATAM_RSI_REGION_MAP.keys())
)
from utils.queries import get_okr_coco_adoption, get_usecase_confidence_scores
from utils.cortex_helpers import cortex_complete, run_cortex_agent
from utils.config import get_env


# ── Helper functions (defined before page logic) ───────────────────────────────

def _theater_label(theater: str) -> str:
    t = (theater or "").upper()
    if any(x in t for x in ("AMS", "USM", "USPUB", "MAJORS", "EXPANSION", "ACQUISITION")):
        return "AMS"
    if any(x in t for x in ("EMEA", "UK", "CENTRAL", "SOUTH", "NORTH")):
        return "EMEA"
    if any(x in t for x in ("APJ", "JAPAN", "KOREA", "ASEAN", "ANZ", "INDIA")):
        return "APJ"
    return "AMS"  # default to AMS for unknown


def _parse_skill_suggestions(response_text: str, df: pd.DataFrame) -> dict:
    """Parse 'UC-XXXXXX: suggestion' lines from LLM response into {USE_CASE_ID: suggestion}."""
    suggestions = {}
    id_to_num = dict(zip(df["USE_CASE_ID"], df.get("USE_CASE_NUMBER", df["USE_CASE_ID"])))
    num_to_id = {v: k for k, v in id_to_num.items()}

    for line in response_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"[-•]?\s*(UC-\w+)\s*[:\-]\s*(.+)", line)
        if m:
            uc_num, suggestion = m.group(1).strip(), m.group(2).strip()
            uc_id = num_to_id.get(uc_num)
            if uc_id:
                suggestions[uc_id] = suggestion
    return suggestions


def _batch_skill_suggestions(conn, df: pd.DataFrame, partner: str) -> dict:
    """
    Calls PSE_UC_PORTFOLIO_ANALYSIS skill via COCO_AGENT to generate CoCo
    capability suggestions for all non-CoCo use cases in a single batched call.
    Falls back to cortex_complete if the agent call fails.
    Returns dict: {USE_CASE_ID -> suggestion_text}
    """
    if len(df) == 0:
        return {}

    uc_lines = []
    for _, row in df.iterrows():
        uc_num   = row.get("USE_CASE_NUMBER", row.get("USE_CASE_ID", ""))
        name     = row.get("USE_CASE_NAME", "")
        account  = row.get("ACCOUNT_NAME", "")
        stage    = row.get("USE_CASE_STAGE", "")
        tech     = row.get("TECHNICAL_USE_CASE", "")
        eacv     = row.get("USE_CASE_EACV", 0)
        eacv_str = f"${eacv/1_000_000:.2f}M" if eacv >= 1_000_000 else f"${eacv/1000:.0f}K"
        uc_lines.append(f"- {uc_num}: {name} | {account} | {stage} | {tech} | {eacv_str}")

    uc_list = "\n".join(uc_lines)
    first_num = uc_lines[0].split(":")[0].lstrip("- ").strip() if uc_lines else "UC-XXXXX"

    prompt = f"""You are a Snowflake Partner SE using the PSE_UC_PORTFOLIO_ANALYSIS skill \
(snow://skill_catalog/USER$DSHAVKANI.SKILL_SHARING_89F4D7DE.PSE_UC_PORTFOLIO_ANALYSIS) \
to suggest how Cortex Code (CoCo) can be leveraged for each use case below.

For each use case, write ONE specific sentence for the "USED / WILL USE COCO" field. \
Be concrete — mention specific Cortex Code capabilities like SQL generation/migration, \
Python/code conversion, Snowflake Intelligence for agentic workflows, Cortex Search, \
Cortex Analyst, or Snowpark notebooks as appropriate to the workload type.

Format your response EXACTLY as one line per use case:
{first_num}: [1-sentence CoCo suggestion]

Use cases for partner {partner}:
{uc_list}

Return ONLY the UC lines, nothing else."""

    try:
        result = run_cortex_agent(prompt)
        response_text = result.get("answer", "")
        if response_text:
            return _parse_skill_suggestions(response_text, df)
    except Exception:
        pass

    # Fallback to direct LLM complete
    try:
        response_text = cortex_complete(conn, "claude-sonnet-4-5", prompt, max_tokens=2048)
        if response_text:
            return _parse_skill_suggestions(response_text, df)
    except Exception:
        pass

    return {}


def _build_email(partner, coco_count, total_ucs, coco_pct, non_coco_count,
                  non_coco_eacv, target, gap_needed, q_start, q_end,
                  non_coco_df: pd.DataFrame, skill_suggestions: dict) -> str:
    """Build the full email body in the IBM CoCo confirmation format."""
    ref_id = "REF-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    eacv_m = non_coco_eacv / 1_000_000

    # Group UCs by theater label
    theater_groups: dict = {}
    for _, row in non_coco_df.sort_values("USE_CASE_EACV", ascending=False).iterrows():
        label = _theater_label(row.get("THEATER_NAME", ""))
        theater_groups.setdefault(label, []).append(row)

    # Build UC sections
    uc_sections = ""
    for label in ["AMS", "EMEA", "APJ", "Other"]:
        ucs = theater_groups.get(label, [])
        if not ucs:
            continue
        t_eacv = sum(r.get("USE_CASE_EACV", 0) for r in ucs) / 1_000_000
        uc_sections += (
            f"\n{label} · {len(ucs)} USE {'CASE' if len(ucs)==1 else 'CASES'} · "
            f"${t_eacv:.2f}M EACV\n\n"
        )
        for row in ucs:
            uc_id    = row.get("USE_CASE_ID", "")
            uc_num   = row.get("USE_CASE_NUMBER", uc_id)
            name     = row.get("USE_CASE_NAME", "")
            account  = row.get("ACCOUNT_NAME", "")
            stage    = row.get("USE_CASE_STAGE", "")
            tech     = row.get("TECHNICAL_USE_CASE", "")
            eacv     = row.get("USE_CASE_EACV", 0)
            eacv_str = f"${eacv/1_000_000:.2f}M" if eacv >= 1_000_000 else f"${eacv/1000:.0f}K"
            skill    = skill_suggestions.get(uc_id, "click here and type")

            # Shorten stage: "5 - Implementation In Progress" → "5 - Implementation In Progress"
            m = re.match(r"^(\d+)\s*-\s*(.+)$", stage)
            stage_disp = f"{m.group(1)} - {m.group(2)}" if m else stage

            uc_sections += (
                f"• {uc_num} — {name}\n"
                f"  {account} · {stage_disp} · {eacv_str}\n"
                f"  {tech}\n\n"
                f"  USED / WILL USE COCO:  {skill}\n"
                f"  NOTES:  click here and type\n\n"
            )

    return f"""Subject: CoCo Adoption Q3 FY27 - confirm CoCo on {non_coco_count} {partner} use cases [{ref_id}]

{partner} & Snowflake Partnership
CoCo Adoption — Q3 FY27 Use Case Confirmation

Quick ask on Cortex Code (CoCo) attribution for Q3 FY27 ({q_start} to {q_end}). Here is where the joint number stands right now:

  {coco_pct}%  CoCo attach today · target {target}%
  {coco_count} of {total_ucs}  use cases with CoCo attached
  {non_coco_count}  awaiting confirmation
  ${eacv_m:.2f}M  EACV in those use cases

We are {coco_pct}% against a {target}% target for Q3 FY27. {gap_needed} more of the use cases below would close that gap.

The {non_coco_count} use cases below (${eacv_m:.2f}M EACV) have no CoCo signal on record. In most cases that means the work happened and simply was not tagged. Could you confirm which of these used CoCo?

You can answer without leaving this email. Hit Reply All and type straight into the box under each use case — the quoted message is editable, so just type your answer and any notes. Only the ones you can speak to; blanks are fine. If you would rather just list the use case numbers that used CoCo, that works too — we will handle the tagging either way.
{uc_sections}
One mechanical note for future quarters: partner comments only register when the literal #coco is present, including the hash. Writing "CoCo" without it reads as untagged even though the intent is obvious.

⚠ REPLY ALL, TYPE IN THE BOXES, AND KEEP [{ref_id}] IN THE SUBJECT

Each use case above has a box you can type directly into on Reply — no form to open and nothing to download. The reference id {ref_id} is what routes your answers back to the Q3 FY27 CoCo review automatically, so nothing gets lost in a thread.

REQUEST
  Quarter:               Q3 FY27 ({q_start} to {q_end})
  Scope:                 {partner} use cases in Stages 3–7, all geos
  CoCo attach today:     {coco_count} of {total_ucs} = {coco_pct}% (target {target}%)
  Awaiting confirmation: {non_coco_count} use cases · ${eacv_m:.2f}M EACV
  Reference id:          {ref_id}
"""


# ── Page (runs top-to-bottom on every Streamlit rerun) ────────────────────────

# DEV-only guard
if get_env() not in ("dev",):
    st.warning("This page is only available in the DEV environment.")
    st.stop()

conn = st.session_state.conn

st.title(":material/forward_to_inbox: PSE Email — CoCo Confirmation")
st.caption(
    "Generate a partner-targeted CoCo confirmation email listing all non-CoCo "
    "use cases for the selected partner in the current quarter."
)

# Date range from sidebar session state
q_start = str(st.session_state.get("okr_start_date", date(2026, 8, 1)))
q_end   = str(st.session_state.get("okr_end_date",   date(2026, 10, 31)))
include_account_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter    = st.session_state.get("confidence_filter", ["High"])
confidence           = "High" if confidence_filter == ["High"] else ("Medium" if confidence_filter else None)

# Canonical partner list — remove secondary aliases so dropdown shows clean names
_ALIAS_SECONDARIES = {"Ernst & Young (EY)", "IBM Consulting", "Kipi.ai", "LTI Mindtree"}
partner_options = sorted(set(MANAGED_PARTNERS) - _ALIAS_SECONDARIES)

selected_partner = st.selectbox(
    "Select Partner",
    options=partner_options,
    index=None,
    placeholder="Choose a managed partner…",
)

if not selected_partner:
    st.info("Select a partner above to load their non-CoCo use cases.")
    st.stop()

# Load and filter use cases for the selected partner
with st.spinner("Loading use cases…"):
    detail = get_okr_coco_adoption(
        conn, q_start, q_end, region=None,
        include_account_coco=include_account_coco, confidence=confidence,
    )
    detail = detail.copy()
    detail["PARTNER_NAME"] = detail["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
    detail = detail[detail["PARTNER_NAME"] == selected_partner].copy()

if len(detail) == 0:
    st.warning(f"No Q3 use cases found for **{selected_partner}**.")
    st.stop()

# Apply same confidence scoring logic as OKR deep dive
if include_account_coco:
    conf_scores = get_usecase_confidence_scores(conn, selected_partner, q_start, q_end)
    if len(conf_scores) > 0:
        conf_map = conf_scores[["USE_CASE_ID", "CONFIDENCE_BAND"]].set_index("USE_CASE_ID")
        detail["CONFIDENCE_BAND"] = detail["USE_CASE_ID"].map(conf_map["CONFIDENCE_BAND"])
        bands    = confidence_filter or ["High", "Medium", "Low"]
        is_flag  = detail["COCO_SOURCE"].notna()
        has_conf = detail["CONFIDENCE_BAND"].isin(bands)
        detail["IS_COCO_ATTACHED"] = is_flag | has_conf

non_coco = detail[detail["IS_COCO_ATTACHED"] == False].copy()
coco_ucs = detail[detail["IS_COCO_ATTACHED"] == True].copy()

total_ucs      = len(detail)
coco_count     = len(coco_ucs)
non_coco_count = len(non_coco)
coco_pct       = round(coco_count * 100.0 / total_ucs, 1) if total_ucs > 0 else 0.0
non_coco_eacv  = non_coco["USE_CASE_EACV"].sum()

# Target: 50% for APJ/EMEA/LATAM RSIs, 75% otherwise
_apj_emea_latam = (
    set(APJ_RSI_REGION_MAP.keys())
    | set(EMEA_RSI_REGION_MAP.keys())
    | set(LATAM_RSI_REGION_MAP.keys())
)
target     = 50 if selected_partner in _apj_emea_latam else 75
gap_needed = max(0, round(target / 100.0 * total_ucs) - coco_count)

# Summary metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("CoCo Attach Today", f"{coco_pct}%",
          f"{'MET' if coco_pct >= target else 'BELOW'} {target}% target")
c2.metric("CoCo Attached", f"{coco_count} of {total_ucs}")
c3.metric("Awaiting Confirmation", non_coco_count)
c4.metric("EACV Awaiting", f"${non_coco_eacv/1_000_000:.2f}M")

if non_coco_count == 0:
    st.success(f"All {total_ucs} use cases already have CoCo attached for {selected_partner}!")
    st.stop()

st.divider()

# Preview non-CoCo UCs
with st.expander(f"Non-CoCo Opportunities ({non_coco_count} use cases)", expanded=False):
    _preview_cols = ["USE_CASE_NUMBER", "USE_CASE_NAME", "ACCOUNT_NAME",
                     "THEATER_NAME", "USE_CASE_STAGE", "USE_CASE_EACV", "TECHNICAL_USE_CASE"]
    _avail = [c for c in _preview_cols if c in non_coco.columns]
    _preview = non_coco[_avail].copy()
    if "USE_CASE_STAGE" in _preview.columns:
        _preview["USE_CASE_STAGE"] = _preview["USE_CASE_STAGE"].str.extract(r"^(\d+)").iloc[:, 0]
    if "USE_CASE_EACV" in _preview.columns:
        _preview["USE_CASE_EACV"] = non_coco["USE_CASE_EACV"].apply(
            lambda x: f"${x/1_000_000:.2f}M" if x >= 1_000_000 else f"${x/1000:.0f}K"
        )
    st.dataframe(_preview, hide_index=True, use_container_width=True,
                 height=38 + 35 * min(non_coco_count, 20))

# Generate button
generate = st.button(
    f":material/auto_awesome: Generate Email for {non_coco_count} Non-CoCo Use Cases",
    type="primary",
    use_container_width=True,
)

if generate:
    with st.spinner(
        f"Calling PSE_UC_PORTFOLIO_ANALYSIS skill for {non_coco_count} use cases… "
        "(this may take 15–30 seconds)"
    ):
        skill_suggestions = _batch_skill_suggestions(conn, non_coco, selected_partner)

    with st.spinner("Formatting email…"):
        email_text = _build_email(
            partner=selected_partner,
            coco_count=coco_count,
            total_ucs=total_ucs,
            coco_pct=coco_pct,
            non_coco_count=non_coco_count,
            non_coco_eacv=non_coco_eacv,
            target=target,
            gap_needed=gap_needed,
            q_start=q_start,
            q_end=q_end,
            non_coco_df=non_coco,
            skill_suggestions=skill_suggestions,
        )

    st.subheader("Generated Email")
    st.caption("Copy the text below and paste into your email client.")
    st.text_area("", email_text, height=700)
    st.download_button(
        label=":material/download: Download as .txt",
        data=email_text,
        file_name=f"PSE_CoCo_Email_{selected_partner.replace(' ', '_')}.txt",
        mime="text/plain",
    )
