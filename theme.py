"""
Shared theme, styling and disclaimer for the valuation tools site.

Single source of truth for anything that needs to look/read identically across
main.py (landing page), beta_page.py and dcf_page.py. Import from here instead
of redefining THEMES/CSS/disclaimer text locally in a page - that duplication
is exactly what caused the Reverse DCF page's colors to drift out of sync with
the Beta Calculator earlier.
"""

import streamlit as st

# Restrained institutional palette - one accent, used for meaning, not decoration.
THEMES = {
    "dark": {
        "bg": "#0b0f14", "surface1": "#131a24", "surface2": "#0f1520",
        "border": "#22303f", "text": "#e5e7eb", "text_muted": "#8b95a3",
        "accent": "#2dd4bf", "accent_text": "#0b0f14", "amber": "#f59e0b", "red": "#ef4444",
    },
    "light": {
        "bg": "#f7f8fa", "surface1": "#ffffff", "surface2": "#eef1f4",
        "border": "#dde2e8", "text": "#1a1f26", "text_muted": "#5b6472",
        "accent": "#0f766e", "accent_text": "#ffffff", "amber": "#b45309", "red": "#b91c1c",
    },
}


def get_custom_css(T: dict) -> str:
    """Full site CSS, parameterized on the active theme dict. Call once, in
    main.py, before st.navigation hands off to whichever page is selected -
    it applies globally to every page for the rest of that run."""
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=DM+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"]  {{ font-family: 'DM Sans', sans-serif; }}
code, .stCodeBlock, [data-testid="stMetricValue"] {{ font-family: 'IBM Plex Mono', monospace; }}

#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}

/* Top navigation bar (st.navigation position="top") lives inside this same
   header element. The old single-page app hid stToolbar/stDecoration
   entirely to remove Streamlit's default "Deploy" chrome - with top nav now
   living in that same region, `display: none` on those wiped out the whole
   nav bar too (this was the "empty header" bug). Style the header instead of
   hiding it, and set its own text/icon color explicitly - content inside
   stAppHeader does NOT inherit .stApp's color rules below, so without this
   the nav links can end up an invisible dark-on-dark. */
.stAppHeader, header[data-testid="stHeader"] {{
    background-color: {T['surface2']} !important;
    border-bottom: 1px solid {T['border']};
}}
.stAppHeader *, header[data-testid="stHeader"] * {{ color: {T['text']} !important; }}
.stAppHeader svg {{ fill: {T['text']} !important; }}

.stApp {{ background-color: {T['bg']}; color: {T['text']}; }}
.stApp, .stApp p, .stApp span, .stApp label, .stApp div {{ color: {T['text']}; }}
section[data-testid="stSidebar"] {{ background-color: {T['surface2']}; }}

/* Streamlit's default top padding is sized for a header with no nav row
   under it - with position="top" navigation added, that left a large gap
   above the page heading. Tighten it. */
[data-testid="stAppViewContainer"] .block-container, .block-container {{
    padding-top: 2rem !important;
}}

[data-testid="stMetric"] {{
    background-color: {T['surface1']};
    border: 0.5px solid {T['border']};
    border-radius: 10px;
    padding: 14px 16px;
    height: auto;
    overflow: visible;
}}
[data-testid="stMetricValue"] {{
    color: {T['accent']} !important;
    font-size: clamp(0.95rem, 2.1vw, 1.75rem) !important;
    white-space: normal !important;
    overflow-wrap: break-word !important;
    line-height: 1.2 !important;
}}
[data-testid="stMetricLabel"] {{ color: {T['text_muted']} !important; }}

[data-testid="stVerticalBlockBorderWrapper"] {{
    background-color: {T['surface1']}; border-color: {T['border']} !important;
}}

.stTabs [data-baseweb="tab-list"] {{
    gap: 4px; background-color: {T['surface2']}; padding: 4px;
    border-radius: 999px; width: fit-content;
}}
.stTabs [data-baseweb="tab"] {{
    border-radius: 999px; padding: 6px 18px; color: {T['text_muted']} !important;
    font-weight: 500; font-size: 14px; background-color: transparent;
}}
.stTabs [data-baseweb="tab"] p {{ color: inherit !important; }}
.stTabs [aria-selected="true"] {{
    background-color: {T['accent']}22 !important; color: {T['accent']} !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{ display: none; }}
.stTabs [data-baseweb="tab-border"] {{ display: none; }}

.stRadio label p, .stRadio div {{ color: {T['text']} !important; }}

input, textarea {{
    background-color: {T['surface1']} !important;
    border-color: {T['border']} !important;
    color: {T['text']} !important;
}}
[data-baseweb="select"] > div, [data-baseweb="select"] div {{
    background-color: {T['surface1']} !important;
    color: {T['text']} !important;
    border-color: {T['border']} !important;
}}
[data-baseweb="popover"] {{ background-color: {T['surface1']} !important; }}
ul[role="listbox"], li[role="option"] {{
    background-color: {T['surface1']} !important; color: {T['text']} !important;
}}

.badge-pass {{ color: {T['accent']}; font-weight: 600; }}
.badge-warn {{ color: {T['amber']}; font-weight: 600; }}
.badge-fail {{ color: {T['red']}; font-weight: 600; }}

div.stButton > button {{
    background-color: {T['accent']}; color: {T['accent_text']}; border: none; font-weight: 600;
    border-radius: 8px;
}}
div.stButton > button:hover {{ opacity: 0.88; }}

/* Landing-page tiles - the whole card is an <a> tag (see home.py), so the
   hover lift applies to the link itself, not a div sitting inside it. */
a.tool-tile {{
    display: block;
    background-color: {T['surface1']};
    border: 1px solid {T['border']};
    border-radius: 14px;
    padding: 24px;
    height: 100%;
    text-decoration: none;
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}}
a.tool-tile:hover {{
    transform: translateY(-4px);
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
    border-color: {T['accent']};
}}
a.tool-tile h3 {{ color: {T['text']}; margin-top: 0; }}
a.tool-tile p {{ color: {T['text_muted']}; }}
a.tool-tile .tile-cta {{ color: {T['accent']}; font-weight: 600; }}
/* Peer-set table (Bottom-Up Beta tab) - by default Streamlit stacks
   st.columns() vertically once the screen is too narrow for all of them
   side by side, which turns this into an unreadable list of labels on
   mobile. Instead, force the row to stay horizontal and let the container
   scroll sideways - a swipe, not a stack. Targets a specific container via
   st.container(key="peer_table") in beta_page.py. */
.st-key-peer_table {{
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}}
.st-key-peer_table div[data-testid="stHorizontalBlock"] {{
    flex-wrap: nowrap !important;
    min-width: 620px;
}}
</style>
"""


# Applied to every st.plotly_chart(..., config=PLOTLY_CONFIG) call across the
# app. What each setting does:
#   - displayModeBar: "hover" - shows the zoom/pan toolbar on mouse hover
#     (useful on a PC/laptop), but touch devices have no hover state, so on
#     mobile it effectively never appears and can't overlap the title.
#   - displaylogo: False - drops the Plotly logo button from that toolbar.
#   - scrollZoom: False - a scroll/wheel gesture over the chart no longer
#     zooms it, so scrolling past a chart on mobile just scrolls the page.
# Pair this with dragmode=False in each figure's own update_layout (below) -
# that's what actually stops a finger-swipe across the chart from being
# read as a box-zoom drag (the "box with two lines" selection). Desktop
# users can still click the toolbar's zoom/pan buttons to turn that back on
# for a specific chart when they want it.
#   - doubleClickDelay: 600 - Plotly's double-click-to-reset detection is
#     timing- and pixel-sensitive by default (300ms window) and is a known
#     source of "it took me 5-6 tries" complaints across Plotly apps
#     generally, not something specific to this app. Widening the window
#     to 600ms makes it noticeably more forgiving.
#   - modeBarButtonsToRemove: drops the box-select/lasso-select tools, which
#     this app never uses for selection - keeps the toolbar (zoom, pan,
#     zoom in/out, autoscale, download) focused. The "Reset axes" (house
#     icon) and "Autoscale" buttons both do the same job as double-click in
#     a single, reliable click - worth using instead of double-click when
#     precision matters.
PLOTLY_CONFIG = {
    "displayModeBar": "hover", "displaylogo": False, "scrollZoom": False,
    "doubleClickDelay": 600, "modeBarButtonsToRemove": ["select2d", "lasso2d"],
}


def searchbox_style(T: dict) -> dict:
    """Streamlit-searchbox style overrides, parameterized on the active theme."""
    return {
        "searchbox": {
            "control": {"backgroundColor": T["surface1"], "borderColor": T["border"],
                        "color": T["text"], "minHeight": "36px"},
            "input": {"color": T["text"]},
            "placeholder": {"color": T["text_muted"]},
            "singleValue": {"color": T["text"]},
            "menuList": {"backgroundColor": T["surface1"]},
            # NOTE: deliberately NOT setting option.backgroundColor or option.color -
            # doing so overrides the library's own isFocused/isSelected background
            # switch and makes the keyboard-highlighted row invisible.
            "option": {"highlightColor": T["accent"]},
        }
    }


DISCLAIMER_TEXT = """
<p><strong>Disclaimer:</strong> These tools are personal, educational projects built to
support my own equity analysis workflow. They are <strong>not investment advice or a
recommendation to buy or sell securities</strong> and should not be relied on as the sole
basis for any investment decision.</p>
<p>Calculations depend on third-party data (Yahoo Finance via <code>yfinance</code>) that
can be incomplete, delayed, mislabeled, or wrong for a given company or period - always
cross-check key figures against a primary source (the company's filings, or a data
provider like Screener) before relying on them. All models involve simplifying
assumptions (see each tool's methodology notes); a different, reasonable set of
assumptions can produce a materially different result. Use at your own judgment and
risk.</p>
"""


def render_disclaimer(T: dict):
    # Rendered as literal HTML (not Markdown-in-a-div): nesting **bold** markdown
    # syntax inside a raw <div unsafe_allow_html> block doesn't get re-parsed by
    # Streamlit's Markdown renderer (HTML blocks suppress inline Markdown per
    # CommonMark), which is why it was showing literal "**Disclaimer:**" text
    # before - using real <strong> tags avoids relying on that reprocessing.
    st.markdown(
        f"<div style='color:{T['text_muted']}; font-size:13px; line-height:1.6;'>"
        f"{DISCLAIMER_TEXT}</div>",
        unsafe_allow_html=True,
    )
