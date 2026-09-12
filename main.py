"""
Valuation Tools - entry point.

Run with:
    streamlit run main.py

This is the ONLY place st.set_page_config() and the global CSS injection
happen - both must run exactly once, before st.navigation() hands off to
whichever page the person picks. Individual pages (home.py, beta_page.py,
dcf_page.py) assume this has already happened and don't repeat it.
"""

import streamlit as st

from theme import THEMES, get_custom_css
from meta_tags import patch_meta_tags

patch_meta_tags()

st.set_page_config(page_title="Deepesh's Valuation Tools", layout="wide", page_icon="📈")

if "theme" not in st.session_state:
    st.session_state.theme = "dark"

st.markdown(get_custom_css(THEMES[st.session_state.theme]), unsafe_allow_html=True)

home = st.Page("home.py", title="Home", icon="🏠", default=True)
beta = st.Page("beta_page.py", title="Beta Calculator", icon="📊", url_path="beta-calculator")
dcf = st.Page("dcf_page.py", title="Reverse DCF", icon="📉", url_path="reverse-dcf")

# position="top" renders these as a header nav bar (functionally the tabs you
# were picturing) rather than the sidebar list - if your Streamlit version
# doesn't support position="top" (needs a reasonably recent 1.4x+), drop the
# argument and it'll fall back to the sidebar automatically.
pg = st.navigation([home, beta, dcf], position="top")
pg.run()
