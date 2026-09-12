"""
Injects SEO / social-preview (Open Graph, Twitter Card) meta tags into the
site, since Streamlit has no built-in way to set these (a long-standing open
request: github.com/streamlit/streamlit/issues/7648). Without this, pasting
the app's link into LinkedIn/WhatsApp/etc. shows a generic, textless preview
card instead of anything describing what the tool does.

HOW THIS WORKS (and why it's a bit unusual):
Streamlit serves one static index.html file (bundled inside the installed
`streamlit` package itself) for every page of the app. There's no supported
API to add tags to it, so the accepted workaround - used across many
Streamlit deployments - is to edit that file directly on disk, in-place,
every time the app starts. This is safe here because:
  - It only ever adds tags; it checks first and does nothing if they're
    already present, so restarting the app repeatedly can't duplicate them.
  - It's wrapped in a broad try/except - if a future Streamlit version moves
    or renames this file, the patch just silently no-ops and the site keeps
    working exactly as before, minus the nicer link previews. Nothing about
    the actual app can break from this.
  - @st.cache_resource means it only actually runs once per running process,
    not on every rerun triggered by a user interaction.
On Streamlit Community Cloud, the environment (and this file) is rebuilt
fresh on every deploy, so this needs to re-run on every startup rather than
being a one-time manual edit - that's what calling patch_meta_tags() from
main.py on every boot accomplishes.
"""

import os
import streamlit as st

SITE_URL = "https://valuation-tools.streamlit.app"
SITE_TITLE = "Equity Analysis Tools — Beta Calculator & Reverse DCF"
SITE_DESCRIPTION = (
    "Free equity-research tools built for real workflow: a stock beta calculator "
    "(regression, CAPM, bottom-up from peers) and a reverse DCF that solves for "
    "the growth rate a stock's current price already assumes."
)

_META_TAGS = f"""
    <meta name="description" content="{SITE_DESCRIPTION}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="{SITE_URL}">
    <meta property="og:title" content="{SITE_TITLE}">
    <meta property="og:description" content="{SITE_DESCRIPTION}">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{SITE_TITLE}">
    <meta name="twitter:description" content="{SITE_DESCRIPTION}">
"""

# Marker used to check "have we already patched this file", so re-running on
# every app start can't stack up duplicate tags.
_MARKER = "<!-- valuation-tools-meta-tags -->"


@st.cache_resource
def patch_meta_tags():
    try:
        index_path = os.path.join(os.path.dirname(st.__file__), "static", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()

        if _MARKER in html or "</head>" not in html:
            return  # already patched, or file structure isn't what we expect - no-op either way

        html = html.replace("</head>", _MARKER + _META_TAGS + "  </head>")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        # Deliberately silent - see module docstring. A failed patch should
        # never be allowed to take down the actual app.
        pass
