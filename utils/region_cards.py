"""Clickable region cards for the ACQ Theatre page (Streamlit custom component v2).

Clicking a card toggles that region; clicking a chip inside a card (e.g. a LATAM territory) toggles
that sub-filter. Each click is sent to Python as a trigger, and the caller keeps the selection in
session state, so the cards always render what Python says is selected. Names are set with
textContent, never as HTML.
"""
import streamlit as st


HTML = """<div class="rc-grid"></div>"""

CSS = """
.rc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px;
           font-family: var(--st-font); }
.rc-card { background: linear-gradient(135deg, #a8dff5 0%, #6ec5ed 100%); border-radius: 8px; padding: 12px 16px;
           box-shadow: 0 1px 4px rgba(41,181,232,.2); border: 3px solid transparent; cursor: pointer;
           transition: transform .08s ease, box-shadow .08s ease; user-select: none; }
.rc-card:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(41,181,232,.35); }
.rc-card.selected { border-color: #003a5c; box-shadow: 0 2px 10px rgba(0,58,92,.35); }
.rc-card.dim { opacity: .55; }
.rc-head { display: flex; justify-content: space-between; align-items: center; min-height: 18px; }
.rc-name { color: rgba(0,40,70,.8); font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
.rc-check { width: 18px; height: 18px; border-radius: 50%; border: 2px solid rgba(0,58,92,.45); display: flex;
            align-items: center; justify-content: center; font-size: 11px; color: #fff; font-weight: 800; }
.rc-card.selected .rc-check { background: #003a5c; border-color: #003a5c; }
.rc-value { color: #003a5c; font-weight: 800; font-size: 26px; line-height: 1.25; }
.rc-value span { font-size: 13px; font-weight: 600; }
.rc-stats { display: flex; gap: 14px; flex-wrap: wrap; color: #0b4f73; font-size: 12px; margin-top: 2px; }
.rc-stats b { color: #003a5c; }
.rc-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.rc-chip { background: rgba(255,255,255,.6); color: #003a5c; border-radius: 10px; padding: 2px 9px; font-size: 11px;
           font-weight: 600; border: 1px solid rgba(0,58,92,.25); cursor: pointer; }
.rc-chip:hover { background: #fff; }
.rc-chip.selected { background: #003a5c; color: #fff; border-color: #003a5c; }
"""

JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const grid = parentElement.querySelector(".rc-grid");
  if (!grid || !data) return;
  const selected = new Set(data.selected || []);
  const anySelected = selected.size > 0;
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  grid.replaceChildren(...data.cards.map((card) => {
    const chipSelected = (card.chips || []).some((c) => selected.has(c.id));
    const isSelected = selected.has(card.id) || chipSelected;
    const node = el("div", "rc-card" + (isSelected ? " selected" : anySelected ? " dim" : ""));
    node.title = isSelected ? "Click to remove this filter" : "Click to filter the Partners table";
    const head = el("div", "rc-head");
    head.append(el("span", "rc-name", card.name), el("span", "rc-check", isSelected ? "✓" : ""));
    const value = el("div", "rc-value", card.value + " ");
    value.append(el("span", null, card.unit));
    const stats = el("div", "rc-stats");
    card.stats.forEach(([v, label]) => { const s = el("span"); s.append(el("b", null, v), " " + label); stats.append(s); });
    node.append(head, value, stats);
    if (card.chips && card.chips.length) {
      const chips = el("div", "rc-chips");
      card.chips.forEach((chip) => {
        const c = el("span", "rc-chip" + (selected.has(chip.id) ? " selected" : ""), chip.label);
        c.title = "Click to filter to " + chip.label;
        c.onclick = (e) => { e.stopPropagation(); setTriggerValue("toggle", chip.id); };
        chips.append(c);
      });
      node.append(chips);
    }
    node.onclick = () => setTriggerValue("toggle", card.id);
    return node;
  }));
}
"""

_REGION_CARDS = st.components.v2.component("acq_region_cards", html=HTML, css=CSS, js=JS)


def region_cards(cards, state_key, *, key):
    """Render clickable cards and keep the toggled ids in st.session_state[state_key] (a list).

    cards: [{"id", "name", "value", "unit", "stats": [(value, label)], "chips": [{"id", "label"}]}]
    """
    st.session_state.setdefault(state_key, [])
    chips_of = {card["id"]: [chip["id"] for chip in card.get("chips", [])] for card in cards}
    card_of = {chip: card for card, chips in chips_of.items() for chip in chips}

    def toggle():
        clicked = st.session_state[key]["toggle"]
        current = list(st.session_state[state_key])
        if clicked in chips_of:
            # A card counts as selected if it or any of its chips is; clicking it clears all of them.
            group = {clicked, *chips_of[clicked]}
            current = ([c for c in current if c not in group] if group & set(current)
                       else [*current, clicked])
        elif clicked in card_of:
            # A chip narrows its card to that chip, so drop the card-level selection.
            current = ([c for c in current if c != clicked] if clicked in current
                       else [c for c in current if c != card_of[clicked]] + [clicked])
        st.session_state[state_key] = current

    _REGION_CARDS(key=key, data={"cards": cards, "selected": st.session_state[state_key]},
                  on_toggle_change=toggle)
