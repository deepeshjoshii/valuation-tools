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

/* Landing-page tiles - st.container(key="tile_...", border=True) with a
   st.page_link inside, NOT a raw <a href> and NOT st.switch_page (see
   home.py's comment for why - both wipe or can wipe st.session_state).
   The page_link's own real anchor is stretched to cover the entire tile
   and made invisible, so the whole card is clickable; what's actually
   *seen* is the separate ".tile-cta" text below, styled to look like the
   link. Targets any container whose key starts with "tile_". */
div[class*="st-key-tile_"] {{
    position: relative;
    background-color: {T['surface1']};
    border: 1px solid {T['border']} !important;
    border-radius: 14px;
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}}
div[class*="st-key-tile_"]:hover {{
    transform: translateY(-4px);
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
    border-color: {T['accent']} !important;
}}
div[class*="st-key-tile_"] h3 {{ color: {T['text']}; margin-top: 0; }}
div[class*="st-key-tile_"] p {{ color: {T['text_muted']}; }}
div[class*="st-key-tile_"] .tile-cta {{ color: {T['accent']}; font-weight: 600; }}
div[class*="st-key-tile_"] [data-testid="stPageLink"] {{
    position: absolute; inset: 0; margin: 0; z-index: 2;
}}
div[class*="st-key-tile_"] [data-testid="stPageLink"] a {{
    display: block; width: 100%; height: 100%;
}}
div[class*="st-key-tile_"] [data-testid="stPageLink"] a p,
div[class*="st-key-tile_"] [data-testid="stPageLink"] a span {{
    opacity: 0;
}}
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
/* info_icon()'s <details>/<summary> popover - strip the default disclosure
   triangle every browser adds to <summary>, since here it's styled to look
   like a plain circled-i button, not an expand/collapse arrow. */
.info-popover summary {{ list-style: none; }}
.info-popover summary::-webkit-details-marker {{ display: none; }}
.info-popover summary::marker {{ content: ""; }}

/* Feedback widget (render_feedback_widget in this file) - a tab fixed to
   the right edge of the screen, vertically centered, matching the floating
   feedback buttons common on other sites. Targets any container whose key
   starts with "feedback_toggle_"/"feedback_panel_" (one per page, so each
   page's feedback state is independent). */
div[class*="st-key-feedback_toggle_"] {{
    position: fixed;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    z-index: 1000;
}}
div[class*="st-key-feedback_toggle_"] button {{
    writing-mode: vertical-rl;
    border-radius: 8px 0 0 8px !important;
    padding: 14px 10px !important;
    box-shadow: -3px 0 12px rgba(0, 0, 0, 0.25);
}}
div[class*="st-key-feedback_panel_"] {{
    position: fixed;
    right: 56px;
    top: 50%;
    transform: translateY(-50%);
    z-index: 999;
    width: 320px;
    max-width: 80vw;
    background-color: {T['surface1']};
    border: 1px solid {T['border']};
    border-radius: 12px;
    padding: 18px;
    box-shadow: -6px 0 24px rgba(0, 0, 0, 0.35);
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


def friendly_error(e: Exception, ticker: str = "") -> str:
    """Turns a caught exception into a message written for a site visitor,
    not a developer. Used in `except Exception` blocks around data
    fetches/calculations, where the raw exception could be a network error,
    a yfinance-internal message, or anything else unanticipated - none of
    which read well shown directly on a public page.

    Deliberately narrow: only recognizes a few common failure signatures
    (connection issues, "no data" from yfinance) and gives everything else
    a single honest fallback rather than guessing at more patterns. Pair
    this with show_error_detail() below so the raw text is still one click
    away for debugging, not hidden entirely.
    """
    msg = str(e).lower()
    who = f"'{ticker}'" if ticker else "this"
    if any(s in msg for s in ("connection", "timeout", "max retries", "temporarily unavailable")):
        return "Couldn't reach Yahoo Finance — it may be temporarily unavailable. Try again in a moment."
    if any(s in msg for s in ("no data found", "no price data", "possibly delisted", "not found")):
        return (f"No data found for {who} — check the ticker symbol is correct and still listed "
                f"(NSE/BSE tickers need a .NS or .BO suffix, e.g. RELIANCE.NS).")
    return (f"Something went wrong fetching or calculating data for {who}. This usually means the "
            f"ticker doesn't exist, has too little price history, or Yahoo Finance is temporarily "
            f"unavailable — try again, or double-check the ticker symbol.")


def show_error_detail(e: Exception):
    """Raw exception text, tucked into a collapsed expander rather than
    shown inline - available for anyone (including you) who wants to see
    exactly what failed, without putting technical text in front of every
    visitor by default."""
    with st.expander("Technical details"):
        st.code(str(e))


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

FEEDBACK_EMAIL = "deepeshjosh2003@gmail.com"

# Formspree endpoint (set up and confirmed) - feedback submissions POST here
# and Formspree forwards them to FEEDBACK_EMAIL. If this ever needs to
# change (new form, different account), just replace the URL below.
FORMSPREE_ENDPOINT = "https://formspree.io/f/mqpkvegn"


def submit_feedback(page_name: str, email: str, message: str, would_return: str) -> bool:
    """POSTs the feedback to Formspree (a free form-backend service - no
    server or database of your own needed). Returns True on success. Kept
    separate from render_feedback_widget so the network call and its
    failure handling are easy to follow on their own."""
    import requests
    try:
        resp = requests.post(
            FORMSPREE_ENDPOINT,
            data={
                "email": email or "(not provided)",
                "page": page_name,
                "would_use_again": would_return,
                "message": message,
            },
            headers={"Accept": "application/json"},
            timeout=8,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


def render_feedback_widget(page_name: str):
    """A feedback tab fixed to the right edge of the screen (the CSS in
    get_custom_css targets keys starting with "feedback_toggle_"/
    "feedback_panel_"), matching the floating feedback buttons common on
    other sites. Deliberately asks a couple of specific, easy-to-answer
    questions (which page, would they use it again) alongside the open
    message box, rather than just "any feedback?" - specific questions get
    answered; an open blank box mostly doesn't. Submitting POSTs it to
    Formspree, which forwards it to your inbox without exposing your email
    address anywhere in the page's code (unlike a mailto: link) and without
    you running any backend of your own.

    ONE-TIME SETUP (not yet done - submissions won't go anywhere until you
    do this):
      1. Go to formspree.io, sign up free, create a new form.
      2. Formspree gives you an endpoint URL like
         https://formspree.io/f/abcdwxyz - copy it.
      3. Paste it in as FORMSPREE_ENDPOINT above, replacing the placeholder.
      4. Formspree will ask you to confirm your email the first time a
         submission comes in - just click the confirmation link it sends.
    Free tier covers 50 submissions/month, plenty for a site like this.

    Call this once near the bottom of each page (home.py, beta_page.py,
    dcf_page.py), passing a short name for that page so submissions arrive
    with useful context."""
    import urllib.parse

    open_key = f"feedback_open_{page_name}"
    if open_key not in st.session_state:
        st.session_state[open_key] = False

    label = "✕ Close" if st.session_state[open_key] else "💬 Feedback"
    with st.container(key=f"feedback_toggle_{page_name}"):
        if st.button(label, key=f"feedback_toggle_btn_{page_name}"):
            st.session_state[open_key] = not st.session_state[open_key]

    if st.session_state[open_key]:
        with st.container(key=f"feedback_panel_{page_name}"):
            st.markdown("**Help improve the tools**")
            st.caption(f"Feedback on: {page_name}")
            would_return = st.radio("Would you use this again?", ["Yes", "Maybe", "No"],
                                     key=f"feedback_return_{page_name}", horizontal=True)
            msg = st.text_area(
                "Found something confusing, incorrect, or missing?",
                key=f"feedback_msg_{page_name}", height=110,
                placeholder="What worked, what didn't, or what you'd like to see...",
            )
            email = st.text_input("Your email (optional — only if you'd like a reply)",
                                   key=f"feedback_email_{page_name}")
            if st.button("Submit", key=f"feedback_submit_{page_name}", use_container_width=True):
                if not msg.strip():
                    st.warning("Please write a message before submitting.")
                elif FORMSPREE_ENDPOINT.endswith("REPLACE_ME"):
                    # Setup not done yet - fall back to mailto rather than
                    # silently losing the visitor's feedback.
                    subject = urllib.parse.quote(f"Feedback — Valuation Tools ({page_name})")
                    body = urllib.parse.quote(
                        f"From: {email or '(not provided)'}\nWould use again: {would_return}\n\n{msg}"
                    )
                    st.warning("Feedback backend isn't set up yet — here's a direct email link instead:")
                    st.link_button("📧 Send as email", f"mailto:{FEEDBACK_EMAIL}?subject={subject}&body={body}",
                                    use_container_width=True)
                elif submit_feedback(page_name, email, msg, would_return):
                    st.success("Thanks — feedback sent!")
                    st.session_state[open_key] = False
                else:
                    st.error("Couldn't send that just now — please try again in a moment.")
