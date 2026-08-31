import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import random
import re
import string
from datetime import date
import html as html_lib

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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _theater_label(theater: str) -> str:
    t = (theater or "").upper()
    if any(x in t for x in ("AMS", "USM", "USPUB", "MAJORS", "EXPANSION", "ACQUISITION")):
        return "AMS"
    if any(x in t for x in ("EMEA", "UK", "CENTRAL", "SOUTH", "NORTH")):
        return "EMEA"
    if any(x in t for x in ("APJ", "JAPAN", "KOREA", "ASEAN", "ANZ", "INDIA")):
        return "APJ"
    return "AMS"


def _parse_skill_suggestions(response_text: str, df: pd.DataFrame) -> dict:
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
    """Batched call to PSE_UC_PORTFOLIO_ANALYSIS via COCO_AGENT. Falls back to cortex_complete."""
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

    try:
        response_text = cortex_complete(conn, "claude-sonnet-4-5", prompt, max_tokens=2048)
        if response_text:
            return _parse_skill_suggestions(response_text, df)
    except Exception:
        pass

    return {}


def _h(text) -> str:
    """HTML-escape a value."""
    return html_lib.escape(str(text or ""))


def _build_email_html(partner, coco_count, total_ucs, coco_pct, non_coco_count,
                       non_coco_eacv, target, gap_needed, q_start, q_end,
                       non_coco_df: pd.DataFrame, skill_suggestions: dict) -> str:
    """Return a full HTML email matching the IBM CoCo confirmation layout from the screenshot."""
    ref_id  = "REF-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    eacv_m  = non_coco_eacv / 1_000_000

    # Metric box colors
    pct_color    = "#dc2626" if coco_pct < target else "#16a34a"
    await_color  = "#f59e0b"
    eacv_color   = "#1d4ed8"
    count_color  = "#374151"

    # ── 4 metric boxes ────────────────────────────────────────────────────────
    metric_td = (
        "border: 1px solid #e5e7eb; padding: 12px 16px; width: 25%; "
        "vertical-align: top; border-radius: 4px;"
    )
    metrics_html = f"""
<table width="100%" cellspacing="6" cellpadding="0"
       style="border-collapse: separate; border-spacing: 6px; margin: 16px 0 20px 0;">
  <tr>
    <td style="{metric_td} border-left: 4px solid {pct_color};">
      <div style="font-size:28px;font-weight:700;color:{pct_color};line-height:1.1;">{_h(coco_pct)}%</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px;">CoCo attach today ·<br>target {_h(target)}%</div>
    </td>
    <td style="{metric_td} border-left: 4px solid {count_color};">
      <div style="font-size:28px;font-weight:700;color:{count_color};line-height:1.1;">{_h(coco_count)} of {_h(total_ucs)}</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px;">use cases with CoCo<br>attached</div>
    </td>
    <td style="{metric_td} border-left: 4px solid {await_color};">
      <div style="font-size:28px;font-weight:700;color:{await_color};line-height:1.1;">{_h(non_coco_count)}</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px;">awaiting<br>confirmation</div>
    </td>
    <td style="{metric_td} border-left: 4px solid {eacv_color};">
      <div style="font-size:28px;font-weight:700;color:{eacv_color};line-height:1.1;">${eacv_m:.2f}M</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px;">EACV in those use<br>cases</div>
    </td>
  </tr>
</table>"""

    # ── UC sections grouped by theater ────────────────────────────────────────
    theater_groups: dict = {}
    for _, row in non_coco_df.sort_values("USE_CASE_EACV", ascending=False).iterrows():
        label = _theater_label(row.get("THEATER_NAME", ""))
        theater_groups.setdefault(label, []).append(row)

    uc_sections_html = ""
    for label in ["AMS", "EMEA", "APJ", "Other"]:
        ucs = theater_groups.get(label, [])
        if not ucs:
            continue
        t_eacv = sum(r.get("USE_CASE_EACV", 0) for r in ucs) / 1_000_000
        n_word = "USE CASE" if len(ucs) == 1 else "USE CASES"
        uc_sections_html += f"""
<p style="font-size:11px;font-weight:700;color:#9ca3af;letter-spacing:0.07em;
          text-transform:uppercase;margin:28px 0 10px 0;">
  {_h(label)} &middot; {_h(len(ucs))} {n_word} &middot; ${t_eacv:.2f}M EACV
</p>"""

        for row in ucs:
            uc_id    = row.get("USE_CASE_ID", "")
            uc_num   = row.get("USE_CASE_NUMBER", uc_id)
            name     = row.get("USE_CASE_NAME", "")
            account  = row.get("ACCOUNT_NAME", "")
            stage    = row.get("USE_CASE_STAGE", "")
            tech     = row.get("TECHNICAL_USE_CASE", "")
            eacv     = row.get("USE_CASE_EACV", 0)
            eacv_str = f"${eacv/1_000_000:.2f}M" if eacv >= 1_000_000 else f"${eacv/1000:.0f}K"
            skill    = skill_suggestions.get(uc_id, "")

            # Stage: keep "5 - Implementation In Progress" format
            sm = re.match(r"^(\d+)\s*-\s*(.+)$", stage)
            stage_disp = f"{sm.group(1)} - {sm.group(2)}" if sm else stage

            # USED / WILL USE COCO content
            if skill:
                coco_content = _h(skill)
            else:
                coco_content = '<span style="color:#2563eb;">click here and type</span>'

            uc_sections_html += f"""
<div style="margin-bottom:18px;">
  <p style="margin:0 0 3px 0;font-size:14px;">
    &bull; <strong>{_h(uc_num)}</strong> &mdash; {_h(name)}
  </p>
  <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;">
    {_h(account)} &middot; {_h(stage_disp)} &middot; {_h(eacv_str)}
  </p>
  <p style="margin:0 0 8px 0;font-size:13px;color:#374151;">{_h(tech)}</p>
  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;
              padding:10px 14px;font-size:13px;line-height:1.5;">
    <strong style="font-size:11px;text-transform:uppercase;letter-spacing:0.05em;
                   color:#374151;">USED / WILL USE COCO:</strong>&nbsp;{coco_content}
  </div>
</div>"""

    # ── Assemble full HTML ────────────────────────────────────────────────────
    summary_table = f"""
<table width="100%" cellpadding="6" cellspacing="0"
       style="border-collapse:collapse;font-size:13px;border-top:2px solid #e5e7eb;margin-bottom:20px;">
  <tr style="background:#f9fafb;">
    <td style="padding:6px 12px;color:#6b7280;font-size:11px;font-weight:700;
               text-transform:uppercase;white-space:nowrap;">Quarter</td>
    <td style="padding:6px 12px;">Q3 FY27 ({_h(q_start)} to {_h(q_end)})</td>
  </tr>
  <tr>
    <td style="padding:6px 12px;color:#6b7280;font-size:11px;font-weight:700;
               text-transform:uppercase;white-space:nowrap;">CoCo attach today</td>
    <td style="padding:6px 12px;">{_h(coco_count)} of {_h(total_ucs)} = {_h(coco_pct)}% (target {_h(target)}%)</td>
  </tr>
  <tr style="background:#f9fafb;">
    <td style="padding:6px 12px;color:#6b7280;font-size:11px;font-weight:700;
               text-transform:uppercase;white-space:nowrap;">Awaiting confirmation</td>
    <td style="padding:6px 12px;">{_h(non_coco_count)} use cases &middot; ${eacv_m:.2f}M EACV</td>
  </tr>
</table>"""

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,Arial,sans-serif;font-size:14px;
             color:#1a1a1a;max-width:680px;margin:0 auto;padding:20px;line-height:1.6;">

<p style="color:#6b7280;font-size:13px;margin:0 0 2px 0;">{_h(partner)} &amp; Snowflake Partnership</p>
<h2 style="color:#111827;margin:0 0 14px 0;font-size:20px;font-weight:700;">
  CoCo Adoption &mdash; Q3 FY27 Use Case Confirmation
</h2>

{summary_table}

<p style="margin:0 0 8px 0;">Quick ask on Cortex Code (CoCo) attribution for <strong>Q3 FY27</strong>
({_h(q_start)} to {_h(q_end)}). Here is where the joint number stands right now:</p>

{metrics_html}

<p style="margin:0 0 10px 0;">
  We are <strong>{_h(coco_pct)}%</strong> against a <strong>{_h(target)}%</strong> target for Q3 FY27.
  <strong>{_h(gap_needed)} more</strong> of the use cases below would close that gap.
</p>

<p style="margin:0 0 10px 0;">
  The <strong>{_h(non_coco_count)} use cases</strong> below
  (<strong>${eacv_m:.2f}M</strong> EACV) have no CoCo signal on record.
  In most cases that means the work happened and simply was not tagged.
  <strong>Could you confirm which of these used CoCo?</strong>
</p>


{uc_sections_html}

</body>
</html>"""


# ── Page ───────────────────────────────────────────────────────────────────────

if get_env() not in ("dev",):
    st.warning("This page is only available in the DEV environment.")
    st.stop()

conn = st.session_state.conn

st.title(":material/forward_to_inbox: PSE Email — CoCo Confirmation")
st.caption(
    "Generate a partner-targeted CoCo confirmation email listing all non-CoCo "
    "use cases for the selected partner in the current quarter."
)

# Date range from sidebar
q_start = str(st.session_state.get("okr_start_date", date(2026, 8, 1)))
q_end   = str(st.session_state.get("okr_end_date",   date(2026, 10, 31)))
include_account_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter    = st.session_state.get("confidence_filter", ["High"])
confidence           = "High" if confidence_filter == ["High"] else ("Medium" if confidence_filter else None)

# Canonical partner dropdown
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

# Load UCs
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

# Confidence scoring (same logic as OKR deep dive)
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

with st.expander(f"Non-CoCo Opportunities ({non_coco_count} use cases)", expanded=False):
    _preview_cols = ["USE_CASE_NUMBER", "USE_CASE_NAME", "ACCOUNT_NAME",
                     "THEATER_NAME", "USE_CASE_STAGE", "USE_CASE_EACV", "TECHNICAL_USE_CASE"]
    _avail   = [c for c in _preview_cols if c in non_coco.columns]
    _preview = non_coco[_avail].copy()
    if "USE_CASE_STAGE" in _preview.columns:
        _preview["USE_CASE_STAGE"] = _preview["USE_CASE_STAGE"].str.extract(r"^(\d+)").iloc[:, 0]
    if "USE_CASE_EACV" in _preview.columns:
        _preview["USE_CASE_EACV"] = non_coco["USE_CASE_EACV"].apply(
            lambda x: f"${x/1_000_000:.2f}M" if x >= 1_000_000 else f"${x/1000:.0f}K"
        )
    st.dataframe(_preview, hide_index=True, use_container_width=True,
                 height=38 + 35 * min(non_coco_count, 20))

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
        html_email = _build_email_html(
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
    # Persist so the copy button survives subsequent reruns
    st.session_state["_pse_email_html"]    = html_email
    st.session_state["_pse_email_partner"] = selected_partner

# Render copy button + preview whenever we have a cached email for this partner
_cached_html    = st.session_state.get("_pse_email_html")
_cached_partner = st.session_state.get("_pse_email_partner")

if _cached_html and _cached_partner == selected_partner:
    st.subheader("Generated Email")
    st.info("**How to send:** Click **Copy Rich Text** below, then open Gmail and paste (Ctrl+V / Cmd+V) into the email body.")

    col1, col2 = st.columns(2)
    with col1:
        escaped_html = _cached_html.replace('`', '\\`').replace('${', '\\${')
        copy_js = f"""
        <button onclick="copyRich()" id="copyBtn" style="
            background-color:#29B5E8;color:white;border:none;padding:8px 20px;
            border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;width:100%;">
            Copy Rich Text
        </button>
        <script>
        function copyRich() {{
            const html = `{escaped_html}`;
            const blob = new Blob([html], {{type:'text/html'}});
            const item = new ClipboardItem({{'text/html': blob}});
            navigator.clipboard.write([item]).then(() => {{
                document.getElementById('copyBtn').textContent = 'Copied!';
                document.getElementById('copyBtn').style.backgroundColor = '#16a34a';
                setTimeout(() => {{
                    document.getElementById('copyBtn').textContent = 'Copy Rich Text';
                    document.getElementById('copyBtn').style.backgroundColor = '#29B5E8';
                }}, 2000);
            }});
        }}
        </script>
        """
        components.html(copy_js, height=45)

    with col2:
        st.download_button(
            label=":material/download: Download as HTML",
            data=_cached_html,
            file_name=f"PSE_CoCo_Email_{selected_partner.replace(' ', '_')}.html",
            mime="text/html",
            use_container_width=True,
        )

    st.divider()
    components.html(_cached_html, height=200 + 120 * min(non_coco_count, 40), scrolling=True)
