"""Table with Excel-style filter dropdowns in the column headers (Streamlit custom component v2).

st.dataframe has no header filters, so this renders a plain HTML table. Filtering and sorting run
in the browser and do not rerun the app. Cell text is set with textContent, so Salesforce free text
is never interpreted as HTML.
"""
import math
from datetime import date, datetime

import pandas as pd
import streamlit as st


HTML = """
<div class="ft">
  <div class="ft-bar"><span class="ft-count"></span><span class="ft-actions"></span></div>
  <div class="ft-scroll"><table><thead><tr></tr></thead><tbody></tbody></table></div>
</div>
"""

CSS = """
.ft { font-family: var(--st-font); font-size: 14px; color: var(--st-text-color); position: relative; }
.ft-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;
          font-size: 13px; opacity: .85; min-height: 24px; }
.ft-actions button { margin-left: 8px; }
.ft-scroll { max-height: 520px; overflow: auto; border: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
             border-radius: var(--st-base-radius); }
table { border-collapse: separate; border-spacing: 0; width: max-content; min-width: 100%; }
th, td { padding: 5px 8px; font-size: 13px; border-bottom: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
         border-right: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
         white-space: nowrap; max-width: 200px; overflow: hidden; text-overflow: ellipsis; text-align: left; }
th { position: sticky; top: 0; z-index: 2; font-weight: 400; opacity: 1;
     background: var(--st-dataframe-header-background-color, var(--st-secondary-background-color)); }
th .ft-h { display: flex; align-items: center; gap: 4px; }
th .ft-label { cursor: pointer; flex: 1; color: var(--st-text-color); opacity: .7; }
th .ft-label:hover { opacity: 1; }
td.links { max-width: 360px; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.blank { opacity: .4; }
a { color: var(--st-link-color, var(--st-primary-color)); text-decoration: none; }
a:hover { text-decoration: underline; }
button { font: inherit; font-size: 12px; cursor: pointer; border: 1px solid var(--st-widget-border-color, var(--st-border-color));
         background: var(--st-background-color); color: var(--st-text-color); border-radius: var(--st-button-radius, 6px);
         padding: 2px 8px; }
button.ft-icon { border: none; background: transparent; padding: 2px 5px; opacity: .7; font-size: 18px; line-height: 1;
                 border-radius: 4px; }
button.ft-icon:hover { background: var(--st-secondary-background-color); }
button.ft-icon:hover, button.ft-icon.on { opacity: 1; color: var(--st-primary-color); }
.ft-pop { position: absolute; z-index: 1000; width: 280px; padding: 8px; box-shadow: 0 6px 24px rgba(0,0,0,.18);
          display: flex; flex-direction: column;
          background: var(--st-background-color); border: 1px solid var(--st-border-color); border-radius: var(--st-base-radius); }
.ft-pop input[type=text], .ft-pop input[type=number] { width: 100%; box-sizing: border-box; padding: 5px 8px; margin-bottom: 6px;
          font: inherit; font-size: 13px; color: var(--st-text-color); background: var(--st-secondary-background-color);
          border: 1px solid var(--st-widget-border-color, var(--st-border-color)); border-radius: 6px; }
.ft-list { max-height: 260px; overflow: auto; margin: 4px 0 0; }
.ft-list label { display: flex; gap: 6px; align-items: center; padding: 2px 0; font-size: 13px; cursor: pointer; }
.ft-list label span.n { margin-left: auto; opacity: .5; font-size: 12px; }
.ft-row { display: flex; justify-content: flex-end; gap: 6px; margin-bottom: 6px; }
.ft-row button.primary { background: var(--st-primary-color); border-color: var(--st-primary-color); color: #fff; }
.ft-pop .hint { font-size: 12px; opacity: .6; margin-bottom: 6px; }
"""

JS = """
const BLANK = "(Blank)";
const NUMERIC = new Set(["number", "money", "percent"]);

function display(col, v) {
  if (v === null || v === undefined || v === "") return BLANK;
  if (col.type === "bool") return v ? "Yes" : "No";
  if (col.type === "money") return "$" + Math.round(v).toLocaleString();
  if (col.type === "percent") return Math.round(v * 100) + "%";
  if (col.type === "number") return Number(v).toLocaleString();
  if (col.type === "link") return v.text || BLANK;
  if (col.type === "links") return v.length ? v.map((l) => l.text).join(", ") : BLANK;
  return String(v);
}

function sortValue(col, v) {
  if (v === null || v === undefined || v === "") return null;
  if (NUMERIC.has(col.type)) return Number(v);
  if (col.type === "bool") return v ? 1 : 0;
  if (col.type === "link") return (v.text || "").toLowerCase();
  if (col.type === "links") return v.length ? display(col, v).toLowerCase() : null;
  return String(v).toLowerCase();
}

export default function (component) {
  const { data, parentElement } = component;
  const root = parentElement.querySelector(".ft");
  if (!root || !data) return;
  const cols = data.columns, rows = data.rows;
  // Filters and sort survive reruns while this element stays mounted.
  const state = parentElement.__ftState || (parentElement.__ftState = { filters: {}, sort: null });
  const headRow = root.querySelector("thead tr"), body = root.querySelector("tbody");
  const count = root.querySelector(".ft-count"), actions = root.querySelector(".ft-actions");
  let pop = null;

  const passes = (row) => cols.every((col, i) => {
    const f = state.filters[col.key];
    if (!f) return true;
    if (f.kind === "range") {
      const v = row[i];
      if (v === null || v === undefined) return false;
      return (f.min === null || v >= f.min) && (f.max === null || v <= f.max);
    }
    return f.values.has(display(col, row[i]));
  });

  function closePop() { if (pop) { pop.remove(); pop = null; root.style.minHeight = ""; } }

  function placePop(anchor) {
    // Position inside the component (not the viewport) and grow the component while the dropdown
    // is open, so a short table never cuts it off and it scrolls with the page.
    const r = anchor.getBoundingClientRect(), box = root.getBoundingClientRect();
    const top = r.bottom - box.top + 4;
    pop.style.top = top + "px";
    pop.style.left = Math.max(0, Math.min(r.left - box.left - 140, box.width - pop.offsetWidth)) + "px";
    const needed = top + pop.offsetHeight + 12;
    if (root.offsetHeight < needed) root.style.minHeight = needed + "px";
  }

  function render() {
    let shown = rows.filter(passes);
    if (state.sort) {
      const i = state.sort.i, col = cols[i], dir = state.sort.dir;
      shown = shown.slice().sort((a, b) => {
        const x = sortValue(col, a[i]), y = sortValue(col, b[i]);
        if (x === y) return 0;
        if (x === null) return 1;
        if (y === null) return -1;
        return (x < y ? -1 : 1) * dir;
      });
    }
    headRow.replaceChildren(...cols.map((col, i) => {
      const th = document.createElement("th");
      const wrap = document.createElement("div"); wrap.className = "ft-h";
      const label = document.createElement("span"); label.className = "ft-label";
      const arrow = state.sort && state.sort.i === i ? (state.sort.dir > 0 ? " ↑" : " ↓") : "";
      label.textContent = col.label + arrow;
      label.title = col.label + " (click to sort)";
      label.onclick = () => {
        state.sort = state.sort && state.sort.i === i ? (state.sort.dir > 0 ? { i, dir: -1 } : null) : { i, dir: 1 };
        render();
      };
      const btn = document.createElement("button");
      btn.className = "ft-icon" + (state.filters[col.key] ? " on" : "");
      btn.textContent = state.filters[col.key] ? "▼" : "▾";
      btn.title = "Filter " + col.label;
      btn.onclick = (e) => { e.stopPropagation(); openFilter(i, btn); };
      wrap.append(label, btn); th.append(wrap);
      return th;
    }));
    body.replaceChildren(...shown.map((row) => {
      const tr = document.createElement("tr");
      cols.forEach((col, i) => {
        const td = document.createElement("td"), v = row[i];
        const text = display(col, v);
        if (text === BLANK) { td.textContent = "—"; td.className = "blank"; }
        else if (col.type === "link" && v.url) {
          const a = document.createElement("a");
          a.href = v.url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = text;
          td.append(a);
        } else if (col.type === "links") {
          td.className = "links";
          v.forEach((l, j) => {
            if (j) td.append(", ");
            if (!l.url) { td.append(l.text); return; }
            const a = document.createElement("a");
            a.href = l.url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = l.text;
            td.append(a);
          });
        } else { td.textContent = text; if (NUMERIC.has(col.type)) td.className = "num"; }
        td.title = text === BLANK ? "" : text;
        tr.append(td);
      });
      return tr;
    }));
    const idIndex = cols.findIndex((c) => c.key === data.count_key);
    const distinct = idIndex >= 0 ? new Set(shown.map((r) => r[idIndex])).size : null;
    const active = Object.keys(state.filters).length;
    count.textContent = (distinct !== null ? distinct.toLocaleString() + " " + data.count_label + " · " : "")
      + shown.length.toLocaleString() + " of " + rows.length.toLocaleString() + " rows"
      + (active ? " · " + active + " filter" + (active > 1 ? "s" : "") : " · use ▾ in a column header to filter");
    const buttons = [];
    if (active) {
      const clear = document.createElement("button");
      clear.textContent = "Clear filters";
      clear.onclick = () => { state.filters = {}; closePop(); render(); };
      buttons.push(clear);
    }
    const csv = document.createElement("button");
    csv.textContent = "Download CSV";
    csv.onclick = () => download(shown);
    buttons.push(csv);
    actions.replaceChildren(...buttons);
  }

  function download(shown) {
    const q = (s) => '"' + String(s).replace(/"/g, '""') + '"';
    const raw = (col, v) => v === null || v === undefined ? "" : col.type === "link" ? (v.text || "")
      : col.type === "links" ? (v.length ? display(col, v) : "") : v;
    const lines = [cols.map((c) => q(c.label)).join(",")]
      .concat(shown.map((r) => cols.map((c, i) => q(raw(c, r[i]))).join(",")));
    const url = URL.createObjectURL(new Blob([lines.join("\\n")], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url; a.download = (data.file_name || "table") + ".csv"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function openFilter(i, anchor) {
    closePop();
    const col = cols[i];
    pop = document.createElement("div"); pop.className = "ft-pop";
    pop.onclick = (e) => e.stopPropagation();
    const buttonRow = document.createElement("div"); buttonRow.className = "ft-row";
    const apply = document.createElement("button"); apply.textContent = "Apply"; apply.className = "primary";
    const reset = document.createElement("button"); reset.textContent = "Clear";
    reset.onclick = () => { delete state.filters[col.key]; closePop(); render(); };

    if (NUMERIC.has(col.type)) {
      const f = state.filters[col.key];
      const scale = col.type === "percent" ? 100 : 1;
      const hint = document.createElement("div"); hint.className = "hint";
      hint.textContent = col.label + (col.type === "percent" ? " (%)" : col.type === "money" ? " ($)" : "") + " between";
      const min = document.createElement("input"); min.type = "number"; min.placeholder = "Min";
      const max = document.createElement("input"); max.type = "number"; max.placeholder = "Max";
      if (f) { if (f.min !== null) min.value = f.min * scale; if (f.max !== null) max.value = f.max * scale; }
      apply.onclick = () => {
        const lo = min.value === "" ? null : Number(min.value) / scale;
        const hi = max.value === "" ? null : Number(max.value) / scale;
        if (lo === null && hi === null) delete state.filters[col.key];
        else state.filters[col.key] = { kind: "range", min: lo, max: hi };
        closePop(); render();
      };
      buttonRow.append(reset, apply);
      pop.append(hint, min, max, buttonRow);
      min.onkeydown = max.onkeydown = (e) => { if (e.key === "Enter") apply.onclick(); };
    } else {
      // Values offered = those in rows passing the *other* filters (cascading, like Excel).
      const others = rows.filter((row) => cols.every((c, j) => {
        if (j === i || !state.filters[c.key]) return true;
        const f = state.filters[c.key];
        if (f.kind === "range") { const v = row[j]; return v !== null && v !== undefined && (f.min === null || v >= f.min) && (f.max === null || v <= f.max); }
        return f.values.has(display(c, row[j]));
      }));
      const counts = new Map();
      others.forEach((row) => { const t = display(col, row[i]); counts.set(t, (counts.get(t) || 0) + 1); });
      const values = [...counts.keys()].sort((a, b) => a === BLANK ? 1 : b === BLANK ? -1 : a.localeCompare(b));
      const current = state.filters[col.key] ? new Set(state.filters[col.key].values) : new Set(values);
      const search = document.createElement("input"); search.type = "text"; search.placeholder = "Search " + col.label;
      const all = document.createElement("label");
      const allBox = document.createElement("input"); allBox.type = "checkbox";
      all.append(allBox, document.createTextNode(" Select all"));
      const list = document.createElement("div"); list.className = "ft-list";
      const boxes = values.map((v) => {
        const label = document.createElement("label");
        const box = document.createElement("input"); box.type = "checkbox"; box.checked = current.has(v);
        const text = document.createElement("span"); text.textContent = v;
        const n = document.createElement("span"); n.className = "n"; n.textContent = counts.get(v);
        box.onchange = () => { box.checked ? current.add(v) : current.delete(v); syncAll(); };
        label.append(box, text, n); list.append(label);
        return { v, label, box };
      });
      const visible = () => boxes.filter((b) => b.label.style.display !== "none");
      function syncAll() { const vis = visible(); allBox.checked = vis.length > 0 && vis.every((b) => b.box.checked); }
      allBox.onchange = () => { visible().forEach((b) => { b.box.checked = allBox.checked; allBox.checked ? current.add(b.v) : current.delete(b.v); }); };
      search.oninput = () => {
        const term = search.value.toLowerCase();
        boxes.forEach((b) => { b.label.style.display = b.v.toLowerCase().includes(term) ? "" : "none"; });
        syncAll();
      };
      search.onkeydown = (e) => { if (e.key === "Enter") apply.onclick(); };
      apply.onclick = () => {
        // With a search term, keep only the checked values that match it (like Excel).
        const term = search.value.toLowerCase();
        const chosen = new Set([...current].filter((v) => !term || v.toLowerCase().includes(term)));
        if (!term && chosen.size === values.length) delete state.filters[col.key];
        else state.filters[col.key] = { kind: "values", values: chosen };
        closePop(); render();
      };
      syncAll();
      buttonRow.append(reset, apply);
      // Buttons sit under the search box so they stay visible; only the value list scrolls.
      pop.append(search, buttonRow, all, list);
      setTimeout(() => search.focus({ preventScroll: true }), 0);
    }
    root.append(pop);
    placePop(anchor);
  }

  const outside = () => closePop();
  document.addEventListener("click", outside);
  render();
  return () => { document.removeEventListener("click", outside); closePop(); };
}
"""

_FILTER_TABLE = st.components.v2.component("acq_filter_table", html=HTML, css=CSS, js=JS)


def _cell(value, kind):
    if kind == "links":
        return [{"text": str(text), "url": url} for text, url in value] if isinstance(value, (list, tuple)) else []
    if isinstance(value, (list, tuple)) and kind == "link":
        text, url = value
        return {"text": None if pd.isna(text) else str(text), "url": url}
    if value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.strftime("%Y-%m-%d")
    if kind == "bool":
        return bool(value)
    if kind in ("number", "money", "percent"):
        return float(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def filter_table(df, columns, *, key, count_key=None, count_label="rows", file_name="table"):
    """Render `df` with header filters.

    columns: {column: (label, kind)} in display order; kind is text, link, number, money, percent,
    date, bool or links. A link column holds (text, url) tuples; a links column holds a list of them.
    """
    spec = [{"key": c, "label": label, "type": kind} for c, (label, kind) in columns.items()]
    rows = [[_cell(v, kind) for v, (_, kind) in zip(record, columns.values())]
            for record in df[list(columns)].itertuples(index=False, name=None)]
    _FILTER_TABLE(key=key, data={"columns": spec, "rows": rows, "count_key": count_key,
                                 "count_label": count_label, "file_name": file_name})
