from .generator import generate_workshops
from .render_html import SCOPE_NOTE, render_workshop_html, scope_note_html
from .render_pdf import scope_note_flowable, workshop_pdf_flowables


def filter_not_deployed(gap_rows_by_region: dict) -> dict:
    return {reg: [r for r in rows if r.get("stage_label") != "Deployed"]
            for reg, rows in gap_rows_by_region.items()}
