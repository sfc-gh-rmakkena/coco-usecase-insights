"""Shared report rendering helpers for AI-generated summaries.

Used by the Executive Email and Partner Consultants pages so the HTML styling
and the rich-text clipboard behaviour stay identical in both places.
"""
import markdown
import streamlit as st
import streamlit.components.v1 as components


def md_to_html(md_text):
    """Wrap markdown (incl. tables) in the email-safe inline stylesheet."""
    html_body = markdown.markdown(md_text, extensions=['tables'])
    return f"""<html><head><style>
    body {{ font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.5; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
    th {{ background-color: #29B5E8; color: white; font-weight: bold; }}
    tr:nth-child(even) {{ background-color: #f9f9f9; }}
    h2 {{ color: #29B5E8; margin-top: 20px; border-bottom: 2px solid #29B5E8; padding-bottom: 4px; }}
    h3 {{ color: #29B5E8; }}
    strong {{ color: #333; }}
    ul {{ padding-left: 20px; }}
    li {{ margin-bottom: 4px; }}
</style></head><body>{html_body}</body></html>"""


def copy_rich_text_button(html_email, plain_text, button_id="copyBtn"):
    """Render a Copy Rich Text button that writes both text/html and text/plain.

    Backticks and ${ are escaped because the payload is embedded in a JS
    template literal.
    """
    escaped_html = html_email.replace('`', '\\`').replace('${', '\\${')
    escaped_plain = (plain_text or "").replace('`', '\\`').replace('${', '\\${')[:8000]
    copy_js = f"""
    <button onclick="copyRich()" id="{button_id}" style="
        background-color: #29B5E8; color: white; border: none; padding: 8px 20px;
        border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600;
        width: 100%;">Copy Rich Text</button>
    <script>
    function copyRich() {{
        const html = `{escaped_html}`;
        const blob = new Blob([html], {{type: 'text/html'}});
        const plainBlob = new Blob([`{escaped_plain}`], {{type: 'text/plain'}});
        const item = new ClipboardItem({{
            'text/html': blob,
            'text/plain': plainBlob
        }});
        navigator.clipboard.write([item]).then(() => {{
            document.getElementById('{button_id}').textContent = 'Copied!';
            document.getElementById('{button_id}').style.backgroundColor = '#28a745';
            setTimeout(() => {{
                document.getElementById('{button_id}').textContent = 'Copy Rich Text';
                document.getElementById('{button_id}').style.backgroundColor = '#29B5E8';
            }}, 2000);
        }});
    }}
    </script>
    """
    components.html(copy_js, height=45)
