"""
Landing page for the valuation tools site.
Registered as the default page in main.py's st.navigation - runs standalone,
no local page_config/CSS (both are handled once in main.py).
"""

import streamlit as st

from theme import THEMES, render_disclaimer, render_feedback_widget

T = THEMES[st.session_state.get("theme", "dark")]

st.title("Equity Analysis Tools")
st.caption(
    "A small, growing set of equity-analysis tools built for my own workflow — "
    "shared here in case they're useful to anyone else."
)

st.divider()

col1, col2 = st.columns(2, gap="large")

# Tiles are st.container(key=..., border=True) with a st.page_link stretched
# invisibly across the whole card via CSS (verified selectors this time -
# see theme.py's comment) so the entire tile is clickable, not just a link
# line. Using st.page_link specifically, not a raw <a href> (a hard browser
# reload, wipes st.session_state) and not st.switch_page either (Streamlit
# itself has open bug reports of switch_page losing session_state in some
# cases - page_link is the one confirmed reliable for this).
with col1:
    with st.container(key="tile_beta", border=True):
        st.markdown(
            """
<h3>📊 Beta Calculator</h3>
<p>Calculates a stock's beta against a benchmark via regression (with a covariance
cross-check), checks how stable that beta has been over time, and builds a
bottom-up beta from a peer set when the stock's own history is too short or noisy
to trust directly. Feeds straight into a CAPM cost of equity.</p>
<p><b>Answers:</b> how sensitive is this stock to the market, and what discount
rate does that imply?</p>
<p class="tile-cta">Open Beta Calculator →</p>
""",
            unsafe_allow_html=True,
        )
        st.page_link("beta_page.py", label="Open Beta Calculator →")

with col2:
    with st.container(key="tile_dcf", border=True):
        st.markdown(
            """
<h3>📉 Reverse DCF</h3>
<p>Runs a DCF backwards across three methodologies — Net Income, FCFF, or FCFE —
solving for the growth rate that today's market price already implies, then compares
it to the company's own historical growth. Net Income is generally the most reliable
starting point for Indian companies given how patchy free-cash-flow disclosure often is.</p>
<p><b>Answers:</b> what growth is the market already pricing in, and how does
that compare with the company's track record?</p>
<p class="tile-cta">Open Reverse DCF →</p>
""",
            unsafe_allow_html=True,
        )
        st.page_link("dcf_page.py", label="Open Reverse DCF →")

st.divider()

st.subheader("About")
st.markdown(
    "Good equity research often comes down to asking better questions — not just "
    "building bigger spreadsheets.\n\n"
    "I built these tools to make a few parts of my own research workflow faster, more "
    "transparent, and easier to revisit. The idea is simple: take concepts that normally "
    "live in scattered spreadsheets and turn them into small, focused tools that show the "
    "assumptions behind the answer.\n\n"
    "The **Beta Calculator** explores how a stock has behaved relative to the market, and "
    "how that feeds into its cost of equity.\n\n"
    "The **Reverse DCF** works backwards from today's valuation to ask a different "
    "question: what does the current price actually imply about the company's future?\n\n"
    "This is an evolving personal project. I'm building it primarily for my own workflow, "
    "but I'm sharing it publicly because I think these tools — and the thinking behind "
    "them — can be useful to other people interested in equity research and valuation.\n\n"
    "**Deepesh Joshi**"
)
st.markdown(
    "🔗 [GitHub](https://github.com/deepeshjoshii)  ·  "
    "💼 [LinkedIn](https://linkedin.com/in/deepeshjoshii)  ·  "
    "✉️ [Email](mailto:deepeshjosh2003@gmail.com)"
)

st.divider()

render_disclaimer(T)
render_feedback_widget("Home")
