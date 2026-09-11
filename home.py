"""
Landing page for the valuation tools site.
Registered as the default page in main.py's st.navigation - runs standalone,
no local page_config/CSS (both are handled once in main.py).
"""

import streamlit as st

from theme import THEMES, render_disclaimer

T = THEMES[st.session_state.get("theme", "dark")]

st.title("Equity Analysis Tools")
st.caption(
    "A small, growing set of equity-analysis tools built for my own workflow — "
    "shared here in case they're useful to anyone else."
)

st.divider()

col1, col2 = st.columns(2, gap="large")

# Tiles are whole <a> tags (see .tool-tile CSS in theme.py) - the entire card
# is clickable and links straight to the page's url_path set in main.py, with
# a hover lift (translateY + shadow) instead of a separate link line below.
with col1:
    st.markdown(
        """
<a href="beta-calculator" target="_self" class="tool-tile">
<h3>📊 Beta Calculator</h3>
<p>Calculates a stock's beta against a benchmark via regression (with a covariance
cross-check), checks how stable that beta has been over time, and builds a
bottom-up beta from a peer set when the stock's own history is too short or noisy
to trust directly. Feeds straight into a CAPM cost of equity.</p>
<p><b>Answers:</b> how sensitive is this stock to the market, and what discount
rate does that imply?</p>
<p class="tile-cta">Open Beta Calculator →</p>
</a>
""",
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        """
<a href="reverse-dcf" target="_self" class="tool-tile">
<h3>📉 Reverse DCF</h3>
<p>Runs a WACC/FCFF enterprise-value DCF backwards: instead of assuming a growth
rate to estimate a price, it takes today's actual market price and solves for the
free-cash-flow growth rate that would justify it - then compares that to the
company's own historical FCF growth.</p>
<p><b>Answers:</b> what growth is the market already pricing in, and how does
that compare with the company's track record?</p>
<p class="tile-cta">Open Reverse DCF →</p>
</a>
""",
        unsafe_allow_html=True,
    )

st.divider()

st.subheader("About")
st.markdown(
    "I'm Deepesh — a finance professional working in equity research, based in Indore. "
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
