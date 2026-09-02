import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
from datetime import date

from utils import (
    APJ_RSI_REGION_MAP, EMEA_RSI_REGION_MAP, LATAM_RSI_REGION_MAP,
    PARTNER_RENAME_MAP,
)
from utils.queries import get_okr_coco_adoption, get_usecase_confidence_scores
from utils.config import get_env

# Shared, UI-free mapping module — importing a page script would execute its body
from utils.coco_skill_map import (
    MIGRATION_KEYWORDS, SPARK_KEYWORDS, TECH_UC_SKILL_MAP,
    detect_migration, map_coco_skills_explained,
    theater_label as _theater_label, h as _h, MANAGED_PARTNERS,
)


# ── Email builder with inline reasoning ───────────────────────────────────────

def _build_explained_email_html(partner, coco_count, total_ucs, coco_pct,
                                 non_coco_count, non_coco_eacv, target,
                                 q_start, q_end, non_coco_df: pd.DataFrame) -> str:
    eacv_m = non_coco_eacv / 1_000_000

    pct_color   = "#dc2626" if coco_pct < target else "#16a34a"
    await_color = "#f59e0b"
    eacv_color  = "#1d4ed8"
    count_color = "#374151"
    metric_td   = ("border:1px solid #e5e7eb;padding:12px 16px;width:25%;"
                   "vertical-align:top;border-radius:4px;")

    metrics_html = f"""
<table width="100%" cellspacing="6" cellpadding="0"
       style="border-collapse:separate;border-spacing:6px;margin:16px 0 20px 0;">
  <tr>
    <td style="{metric_td} border-left:4px solid {pct_color};">
      <div style="font-size:28px;font-weight:700;color:{pct_color};line-height:1.1;">{_h(coco_pct)}%</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px;">CoCo attach today &middot;<br>target {_h(target)}%</div>
    </td>
    <td style="{metric_td} border-left:4px solid {count_color};">
      <div style="font-size:28px;font-weight:700;color:{count_color};line-height:1.1;">{_h(coco_count)} of {_h(total_ucs)}</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px;">use cases with CoCo<br>attached</div>
    </td>
    <td style="{metric_td} border-left:4px solid {await_color};">
      <div style="font-size:28px;font-weight:700;color:{await_color};line-height:1.1;">{_h(non_coco_count)}</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px;">CoCo adoption<br>opportunities</div>
    </td>
    <td style="{metric_td} border-left:4px solid {eacv_color};">
      <div style="font-size:28px;font-weight:700;color:{eacv_color};line-height:1.1;">${eacv_m:.2f}M</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px;">EACV in those use<br>cases</div>
    </td>
  </tr>
</table>"""

    # Group by theater
    theater_groups: dict = {}
    for _, row in non_coco_df.sort_values("USE_CASE_EACV", ascending=False).iterrows():
        theater_groups.setdefault(_theater_label(row.get("THEATER_NAME", "")), []).append(row)

    def _stage_num(s):
        m = re.match(r"^(\d+)", str(s or ""))
        return int(m.group(1)) if m else 99

    _bucket_style = ("font-size:12px;font-weight:700;color:#1a1a1a;letter-spacing:0.03em;"
                     "margin:20px 0 10px 0;padding:8px 12px;background:#f1f5f9;"
                     "border-left:4px solid #29b5e8;border-radius:0 4px 4px 0;")

    def _uc_html(row):
        uc_id    = row.get("USE_CASE_ID", "")
        uc_num   = row.get("USE_CASE_NUMBER", uc_id)
        name     = row.get("USE_CASE_NAME", "") or ""
        account  = row.get("ACCOUNT_NAME", "")
        stage    = row.get("USE_CASE_STAGE", "")
        tech     = row.get("TECHNICAL_USE_CASE", "") or ""
        desc     = row.get("USE_CASE_DESCRIPTION", "") or ""
        eacv     = row.get("USE_CASE_EACV", 0)
        eacv_str = f"${eacv/1_000_000:.2f}M" if eacv >= 1_000_000 else f"${eacv/1000:.0f}K"
        sm = re.match(r"^(\d+)\s*-\s*(.+)$", stage)
        stage_disp = f"{sm.group(1)} - {sm.group(2)}" if sm else stage
        if len(desc) > 400:
            desc = desc[:397].rsplit(" ", 1)[0] + "\u2026"
        desc_html = (f'<p style="margin:0 0 8px 0;font-size:13px;color:#374151;">{_h(desc)}</p>'
                     if desc.strip() else "")

        exp = map_coco_skills_explained(name, tech)

        if exp["skills"]:
            # Each skill on its own row with its reasoning
            rows = ""
            for s in exp["skills"]:
                why = "<br>".join(f"&#8226; {r}" for r in exp["reasons"][s])
                rows += f"""
      <tr>
        <td style="padding:5px 10px 5px 0;vertical-align:top;white-space:nowrap;">
          <span style="display:inline-block;background:#fff;border:1.5px solid #29b5e8;
                       border-radius:4px;padding:3px 8px;font-size:10px;font-family:monospace;
                       color:#0369a1;font-weight:600;">{_h(s)}</span>
        </td>
        <td style="padding:5px 0;vertical-align:top;font-size:11px;color:#475569;line-height:1.5;">{why}</td>
      </tr>"""
            skills_block = f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-top:6px;">
      {rows}
    </table>"""
        else:
            reason = (f'No rule matched tech use case: <i>{_h(", ".join(exp["unmatched"]))}</i>'
                      if exp["unmatched"] else "No technical use case set on this UC")
            skills_block = (f'<p style="margin:6px 0 0 0;font-size:11px;color:#9ca3af;'
                            f'font-style:italic;">{reason}</p>')

        return f"""
<div style="border-bottom:1px solid #f3f4f6;padding-bottom:16px;margin-bottom:16px;">
  <p style="margin:0 0 2px 0;font-size:14px;font-weight:600;color:#111;">
    &bull; <span style="font-family:monospace;color:#29b5e8;font-weight:700;">{_h(uc_num)}</span> &mdash; {_h(name)}
  </p>
  <p style="margin:0 0 6px 0;font-size:12px;color:#6b7280;">
    {_h(account)} &middot; {_h(stage_disp)} &middot; {_h(eacv_str)} &middot; {_h(tech)}
  </p>
  {desc_html}
  <div style="background:linear-gradient(135deg,#f0f9ff 0%,#e0f2fe 100%);
              border:1.5px solid #29b5e8;border-radius:8px;padding:10px 14px;margin-bottom:8px;">
    <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;
                 color:#0369a1;display:block;margin-bottom:2px;">&#9889; Cortex Code Skills Available for This Use Case</span>
    <span style="font-size:10px;color:#0c4a6e;opacity:0.75;display:block;margin-bottom:4px;">why each skill applies &darr;</span>
    {skills_block}
  </div>
  <div style="background:#f9fafb;border:1px dashed #d1d5db;border-radius:6px;padding:8px 14px;">
    <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;
                 color:#374151;display:block;margin-bottom:3px;">Partner: How is / will CoCo be used?</span>
    <span style="color:#9ca3af;font-style:italic;font-size:12px;">&lt;click here and type&gt;</span>
  </div>
</div>"""

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
        poc  = sorted([r for r in ucs if _stage_num(r.get("USE_CASE_STAGE","")) == 3],
                      key=lambda r: r.get("USE_CASE_EACV", 0), reverse=True)
        impl = sorted([r for r in ucs if _stage_num(r.get("USE_CASE_STAGE","")) >= 4],
                      key=lambda r: r.get("USE_CASE_EACV", 0), reverse=True)
        for bucket_name, bucket in (("POC", poc), ("Implementation", impl)):
            if not bucket:
                continue
            b_eacv = sum(r.get("USE_CASE_EACV", 0) for r in bucket) / 1_000_000
            word = "case" if len(bucket) == 1 else "cases"
            uc_sections_html += (f'<p style="{_bucket_style}">{bucket_name} &middot; '
                                 f'{len(bucket)} use {word} &middot; ${b_eacv:.2f}M EACV</p>')
            for row in bucket:
                uc_sections_html += _uc_html(row)

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
               text-transform:uppercase;white-space:nowrap;">Adoption opportunities</td>
    <td style="padding:6px 12px;">{_h(non_coco_count)} use cases &middot; ${eacv_m:.2f}M EACV</td>
  </tr>
</table>"""

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,Arial,sans-serif;font-size:14px;
             color:#1a1a1a;max-width:760px;margin:0 auto;padding:20px;line-height:1.6;">

<p style="color:#6b7280;font-size:13px;margin:0 0 2px 0;">{_h(partner)} &amp; Snowflake Partnership</p>
<h2 style="color:#111827;margin:0 0 14px 0;font-size:20px;font-weight:700;">
  CoCo Adoption &mdash; Q3 FY27 Use Case Confirmation
</h2>

<p style="margin:0 0 16px 0;font-size:14px;color:#374151;line-height:1.7;">
  As your Snowflake Partner SE, I&rsquo;ve reviewed your active use cases and identified
  opportunities where Cortex Code (CoCo) can directly accelerate delivery. The use cases
  below map to specific CoCo skills your team can leverage today &mdash; from SQL generation
  and code migration to agentic workflows and ML pipelines. Each skill includes the reason
  it applies to that use case. I&rsquo;d like to connect you with your account delivery team
  to discuss how they can leverage these skills and share best practices.
</p>

{summary_table}

<p style="margin:0 0 8px 0;">Here is where the joint CoCo number stands right now for <strong>Q3 FY27</strong>
({_h(q_start)} to {_h(q_end)}):</p>

{metrics_html}

{uc_sections_html}

</body>
</html>"""


# ── Page ──────────────────────────────────────────────────────────────────────

if get_env() not in ("dev",):
    st.warning("This page is only available in the DEV environment.")
    st.stop()

conn = st.session_state.conn

st.title(":material/rule: PSE Email — Skill Mapping Explained")
st.caption(
    "Same use case selection and email layout as PSE Email, plus the reason each "
    "CoCo skill was mapped. Useful for validating the mapping and for coaching conversations."
)

q_start = str(st.session_state.get("okr_start_date", date(2026, 8, 1)))
q_end   = str(st.session_state.get("okr_end_date",   date(2026, 10, 31)))
include_account_coco = st.session_state.get("include_account_coco", "Yes") == "Yes"
confidence_filter    = st.session_state.get("confidence_filter", ["High"])
confidence           = "High" if confidence_filter == ["High"] else ("Medium" if confidence_filter else None)

_ALIAS_SECONDARIES = {"Ernst & Young (EY)", "IBM Consulting", "Kipi.ai", "LTI Mindtree"}
partner_options = sorted(set(MANAGED_PARTNERS) - _ALIAS_SECONDARIES)

selected_partner = st.selectbox(
    "Select Partner", options=partner_options, index=None,
    placeholder="Choose a managed partner\u2026",
)

if not selected_partner:
    st.info("Select a partner above to load their non-CoCo use cases.")
    st.stop()

with st.spinner("Loading use cases\u2026"):
    detail = get_okr_coco_adoption(
        conn, q_start, q_end, region=None,
        include_account_coco=include_account_coco, confidence=confidence,
    ).copy()
    detail["PARTNER_NAME"] = detail["PARTNER_NAME"].replace(PARTNER_RENAME_MAP)
    detail = detail[detail["PARTNER_NAME"] == selected_partner].copy()

if len(detail) == 0:
    st.warning(f"No Q3 use cases found for **{selected_partner}**.")
    st.stop()

if include_account_coco:
    conf_scores = get_usecase_confidence_scores(conn, selected_partner, q_start, q_end)
    if len(conf_scores) > 0:
        conf_map = conf_scores[["USE_CASE_ID", "CONFIDENCE_BAND"]].set_index("USE_CASE_ID")
        detail["CONFIDENCE_BAND"] = detail["USE_CASE_ID"].map(conf_map["CONFIDENCE_BAND"])
        bands = confidence_filter or ["High", "Medium", "Low"]
        detail["IS_COCO_ATTACHED"] = detail["COCO_SOURCE"].notna() | detail["CONFIDENCE_BAND"].isin(bands)

non_coco = detail[detail["IS_COCO_ATTACHED"] == False].copy()
coco_ucs = detail[detail["IS_COCO_ATTACHED"] == True].copy()

total_ucs      = len(detail)
coco_count     = len(coco_ucs)
non_coco_count = len(non_coco)
coco_pct       = round(coco_count * 100.0 / total_ucs, 1) if total_ucs > 0 else 0.0
non_coco_eacv  = non_coco["USE_CASE_EACV"].sum()

_apj_emea_latam = (set(APJ_RSI_REGION_MAP) | set(EMEA_RSI_REGION_MAP) | set(LATAM_RSI_REGION_MAP))
target = 50 if selected_partner in _apj_emea_latam else 75

c1, c2, c3, c4 = st.columns(4)
c1.metric("CoCo Attach Today", f"{coco_pct}%",
          f"{'MET' if coco_pct >= target else 'BELOW'} {target}% target")
c2.metric("CoCo Attached", f"{coco_count} of {total_ucs}")
c3.metric("Adoption Opportunities", non_coco_count)
c4.metric("EACV in Those UCs", f"${non_coco_eacv/1_000_000:.2f}M")

if non_coco_count == 0:
    st.success(f"All {total_ucs} use cases already have CoCo attached for {selected_partner}!")
    st.stop()

st.divider()

# ── Mapping audit table ───────────────────────────────────────────────────────
st.subheader("Skill Mapping Audit")
st.caption("One row per use case showing which rule fired and why. "
           "Rows with no skills indicate an unmapped technical use case.")

audit_rows = []
for _, row in non_coco.iterrows():
    exp = map_coco_skills_explained(row.get("USE_CASE_NAME", "") or "",
                                    row.get("TECHNICAL_USE_CASE", "") or "")
    audit_rows.append({
        "UC":            row.get("USE_CASE_NUMBER", row.get("USE_CASE_ID", "")),
        "Use Case":      (row.get("USE_CASE_NAME") or "")[:55],
        "Tech Use Case": (row.get("TECHNICAL_USE_CASE") or "")[:60],
        "Migration?":    "YES" if exp["is_migration"] else "",
        "Signals":       ", ".join(exp["signals"]),
        "Matched Rules": " | ".join(exp["matched_cats"]),
        "Unmapped":      " | ".join(exp["unmatched"]),
        "Skills":        ", ".join(exp["skills"]),
        "# Skills":      len(exp["skills"]),
    })
audit_df = pd.DataFrame(audit_rows)

m1, m2, m3 = st.columns(3)
m1.metric("UCs with skills mapped", int((audit_df["# Skills"] > 0).sum()))
m2.metric("UCs with no mapping", int((audit_df["# Skills"] == 0).sum()))
m3.metric("Migration UCs detected", int((audit_df["Migration?"] == "YES").sum()))

st.dataframe(audit_df, hide_index=True, use_container_width=True,
             height=38 + 35 * min(len(audit_df), 15))

# Unmapped tech-UC categories rollup — shows gaps in TECH_UC_SKILL_MAP
_unmapped = {}
for r in audit_rows:
    for part in [p.strip() for p in r["Unmapped"].split("|") if p.strip()]:
        _unmapped[part] = _unmapped.get(part, 0) + 1
if _unmapped:
    with st.expander(f"Unmapped technical use case values ({len(_unmapped)} distinct)", expanded=False):
        st.caption("These values have no rule in TECH_UC_SKILL_MAP, so they produce no skill tags.")
        st.dataframe(
            pd.DataFrame(sorted(_unmapped.items(), key=lambda x: -x[1]),
                         columns=["Technical Use Case value", "UC count"]),
            hide_index=True, use_container_width=True,
        )

st.divider()

# ── Email generation ──────────────────────────────────────────────────────────
if st.button(f":material/auto_awesome: Generate Explained Email for {non_coco_count} Use Cases",
             type="primary", use_container_width=True):
    html_email = _build_explained_email_html(
        partner=selected_partner, coco_count=coco_count, total_ucs=total_ucs,
        coco_pct=coco_pct, non_coco_count=non_coco_count, non_coco_eacv=non_coco_eacv,
        target=target, q_start=q_start, q_end=q_end, non_coco_df=non_coco,
    )
    st.session_state["_pse_exp_html"]    = html_email
    st.session_state["_pse_exp_partner"] = selected_partner

_cached = st.session_state.get("_pse_exp_html")
if _cached and st.session_state.get("_pse_exp_partner") == selected_partner:
    st.subheader("Generated Email")
    st.info("**How to send:** Click **Copy Rich Text**, then open Gmail and paste (Ctrl+V / Cmd+V).")

    col1, col2 = st.columns(2)
    with col1:
        escaped = _cached.replace('`', '\\`').replace('${', '\\${')
        components.html(f"""
        <button onclick="copyRich()" id="copyBtn" style="
            background-color:#29B5E8;color:white;border:none;padding:8px 20px;
            border-radius:6px;cursor:pointer;font-size:14px;font-weight:600;width:100%;">
            Copy Rich Text
        </button>
        <script>
        function copyRich() {{
            const blob = new Blob([`{escaped}`], {{type:'text/html'}});
            navigator.clipboard.write([new ClipboardItem({{'text/html': blob}})]).then(() => {{
                const b = document.getElementById('copyBtn');
                b.textContent = 'Copied!'; b.style.backgroundColor = '#16a34a';
                setTimeout(() => {{ b.textContent = 'Copy Rich Text';
                                    b.style.backgroundColor = '#29B5E8'; }}, 2000);
            }});
        }}
        </script>
        """, height=45)
    with col2:
        st.download_button(
            label=":material/download: Download as HTML", data=_cached,
            file_name=f"PSE_CoCo_Email_Explained_{selected_partner.replace(' ', '_')}.html",
            mime="text/html", use_container_width=True,
        )

    st.divider()
    components.html(_cached, height=300 + 190 * min(non_coco_count, 30), scrolling=True)
