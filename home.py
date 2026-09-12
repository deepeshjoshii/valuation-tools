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

# Tiles are st.container(key=..., border=True) with a real st.switch_page
# button inside - NOT a raw <a href> (see theme.py's CSS comment for why:
# a plain anchor tag causes an actual browser page load, which starts a
# brand new Streamlit session and silently wipes everything in
# st.session_state - beta/Ke calculated in the Beta Calculator, peer sets,
# etc. - the moment someone goes Home first and clicks a tile from there.
# st.switch_page is Streamlit's own internal navigation and preserves
# session state exactly like the top nav bar does.
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
""",
            unsafe_allow_html=True,
        )
        st.button("Open Beta Calculator →", key="go_beta", use_container_width=True,
                  on_click=lambda: st.switch_page("beta_page.py"))

with col2:
    with st.container(key="tile_dcf", border=True):
        st.markdown(
            """
<h3>📉 Reverse DCF</h3>
<p>Runs a WACC/FCFF enterprise-value DCF backwards: instead of assuming a growth
rate to estimate a price, it takes today's actual market price and solves for the
free-cash-flow growth rate that would justify it - then compares that to the
company's own historical FCF growth.</p>
<p><b>Answers:</b> what growth is the market already pricing in, and how does
that compare with the company's track record?</p>
""",
            unsafe_allow_html=True,
        )
        st.button("Open Reverse DCF →", key="go_dcf", use_container_width=True,
                  on_click=lambda: st.switch_page("dcf_page.py"))

st.divider()

st.subheader("About")
st.markdown(
    "I'm Deepesh — a finance professional working in equity analysis, based in Indore. "
    "I'm pursuing an MA in Economics alongside the CFA Program, and I built these tools "
    "to make my own valuation and research process faster and more consistent, rather "
    "than rebuilding the same spreadsheet logic every time. I'm sharing them here in "
    "case they're useful to others doing similar work."
)
st.markdown(
    "[LinkedIn](https://linkedin.com/in/deepeshjoshii) · "
    "[GitHub](https://github.com/deepeshjoshii)"
    # No email included - add one here (e.g. " · [Email](mailto:you@example.com)")
    # if you want to list one; I don't have one on file to add for you.
)

st.divider()

render_disclaimer(T)
render_feedback_widget("Home")
