"""
Beta Calculator - Streamlit Interface
----------------------------------------
Wraps beta_calculator.py in a web UI. Run locally with:
    streamlit run app.py

Structure: one continuous analytical narrative per stock (Setup -> Result ->
Evidence -> Stability -> Sensitivity -> Bottom-Up -> Methodology) rather than
disconnected tabs that each required re-entering the ticker. Cost of Equity
stays a separate tab since it's a downstream valuation application, not part
of computing beta itself.

Author: Built with Claude for Deepesh
"""

import streamlit as st
from streamlit_searchbox import st_searchbox
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

from beta_calculator import (
    calculate_stock_beta, beta_sensitivity, bottom_up_beta,
    fetch_company_financials, fetch_prices, compute_returns,
    rolling_beta, search_company, INDEX_TICKERS, INDEX_LABELS,
    regression_mean_ci_band,
)


@st.fragment
def searchbox_fragment(search_fn, **kwargs):
    """Wraps st_searchbox so its rerun can be scoped to just this component
    (rerun_scope='fragment') instead of the whole page. Without this, every
    keystroke triggers a FULL app rerun, which tears down and rebuilds the
    dropdown's keyboard-highlighted state each time - that's what was
    breaking arrow-key/Enter navigation."""
    return st_searchbox(search_fn, rerun_scope="fragment", **kwargs)

# ============================================================
# PAGE CONFIG + THEME
# ============================================================
# st.set_page_config and the CSS injection now happen once in main.py, before
# st.navigation hands off to this page - both apply globally across pages,
# so they're not repeated here. THEMES/searchbox_style now live in theme.py,
# the single shared source both pages import from.
from theme import THEMES, searchbox_style, render_disclaimer, PLOTLY_CONFIG

if "theme" not in st.session_state:
    st.session_state.theme = "dark"

T = THEMES[st.session_state.theme]

DISPLAY_TO_INTERVAL = {"Daily": "1d", "Weekly": "1wk", "Monthly": "1mo"}

BENCHMARK_OPTIONS_ALL = sorted(INDEX_LABELS.keys())
DEFAULT_BENCHMARK = "India — Nifty 50"
COMMON_BENCHMARKS = ["India — Nifty 50", "India — Sensex", "North America — S&P 500"]
BENCHMARK_OPTIONS = COMMON_BENCHMARKS + [b for b in BENCHMARK_OPTIONS_ALL if b not in COMMON_BENCHMARKS]


def label_to_name(label: str) -> str:
    return label.split(" — ", 1)[1]


def benchmark_searchbox_callback(searchterm: str):
    if not searchterm:
        return [(lbl, lbl) for lbl in COMMON_BENCHMARKS]
    matches = [lbl for lbl in BENCHMARK_OPTIONS if searchterm.lower() in lbl.lower()]
    return [(lbl, lbl) for lbl in matches[:12]]


def section_header(title: str, subtitle: str = None):
    html = (
        f"<div style='margin: 34px 0 12px 0;'>"
        f"<div style='font-size:12px; letter-spacing:1.5px; color:{T['text_muted']}; "
        f"font-weight:600; text-transform:uppercase;'>{title}</div>"
    )
    if subtitle:
        html += f"<div style='font-size:13px; color:{T['text_muted']}; margin-top:2px;'>{subtitle}</div>"
    html += f"<div style='border-bottom:1px solid {T['border']}; margin-top:8px;'></div></div>"
    st.markdown(html, unsafe_allow_html=True)


def hero_number(label: str, value, subtitle: str = None, glossary_key: str = None):
    icon = info_icon(glossary_key) if glossary_key else ""
    html = (
        f"<div style='text-align:center; padding: 8px 0 4px 0;'>"
        f"<div style='font-size:12px; letter-spacing:1.5px; color:{T['text_muted']}; "
        f"font-weight:600; text-transform:uppercase;'>{label}{icon}</div>"
        f"<div style='font-size:60px; font-weight:700; color:{T['accent']}; "
        f"font-family:\"IBM Plex Mono\", monospace; line-height:1.15;'>{value}</div>"
    )
    if subtitle:
        html += f"<div style='font-size:13px; color:{T['text_muted']};'>{subtitle}</div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def data_quality_badge(sample_size_tier: str, n_obs: int):
    if sample_size_tier.startswith("Adequate"):
        color, label = T["accent"], "Good"
    elif sample_size_tier.startswith("Limited ("):
        color, label = T["amber"], "Limited"
    else:
        color, label = T["red"], "Very Limited"
    html = (
        f"<div style='background-color:{T['surface2']}; border:0.5px solid {T['border']}; "
        f"border-radius:8px; padding:10px 14px; display:inline-block;'>"
        f"<span style='font-size:11px; letter-spacing:1px; color:{T['text_muted']}; "
        f"font-weight:600;'>DATA QUALITY{info_icon('data_quality')}</span>"
        f"<span style='color:{color}; font-weight:700;'>&nbsp;&nbsp;● {label}</span>"
        f"<div style='font-size:12px; color:{T['text_muted']}; margin-top:2px;'>"
        f"{n_obs} observations · {sample_size_tier}</div></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def beta_interpretation(beta: float) -> str:
    pct = round(abs(beta - 1) * 100)
    if beta > 1.15:
        return (f"Beta of {beta} indicates the stock has historically moved about {pct}% "
                 f"more than the benchmark for a 1% benchmark move, on average — "
                 f"**higher systematic risk than the benchmark**.")
    elif beta < 0.85:
        return (f"Beta of {beta} indicates the stock has historically moved about {pct}% "
                 f"less than the benchmark for a 1% benchmark move, on average — "
                 f"**lower systematic risk than the benchmark**.")
    else:
        return f"Beta of {beta} indicates **systematic risk broadly similar to the benchmark**."


# ============================================================
# GLOSSARY - plain-English explanations for hover tooltips, so someone
# unfamiliar with the statistics doesn't have to look each term up elsewhere.
# ============================================================
GLOSSARY = {
    "beta": "Measures how much a stock's returns move relative to the benchmark. Beta > 1 means historically more volatile than the benchmark; beta < 1 means historically less volatile.",
    "blume": "Shrinks the raw historical beta two-thirds of the way toward 1.0, reflecting the tendency of betas to drift toward the market average over time. This is the convention Bloomberg and most terminals use by default.",
    "ci95": "The range within which the true beta most likely falls, with 95% confidence, given the sample size and data variability. A wide range means the point estimate is less precise.",
    "r_squared": "The percentage of the stock's return variance explained by the benchmark's movements. Higher = the benchmark explains more of the stock's returns; lower = more of the movement is company-specific.",
    "n_obs": "The number of matched return observations (dates where both the stock and benchmark have data) used in the regression. More observations generally means a more reliable estimate.",
    "correlation": "How closely the stock's returns move in the same direction as the benchmark's returns, from -1 (perfectly opposite) to +1 (perfectly in sync).",
    "std_error": "The standard error of the beta estimate — how much the estimated beta could vary due to sampling noise. Smaller means more precise.",
    "t_stat": "Tests whether beta is statistically different from zero. As a rule of thumb, a t-stat above ~2 (in absolute value) is generally significant at 95% confidence.",
    "p_value": "The probability of seeing this beta (or a more extreme one) if the true beta were actually zero. Below 0.05 is conventionally considered statistically significant.",
    "alpha": "The average return the stock generated beyond what its beta would predict from the benchmark's return, annualized. A simplistic measure, not true risk-adjusted alpha.",
    "significance": "Whether the beta coefficient is statistically distinguishable from zero (based on t-stat/p-value). Different from R² — a beta can be significant even when R² is low.",
    "explanatory_power": "How much of the stock's return variance the benchmark explains (R²). Different from statistical significance — this measures fit, not whether beta itself is reliable.",
    "data_quality": "A combined read on how much to trust this beta, based mainly on sample size. Small samples (e.g. ~11 observations for 1-year monthly data) produce much less reliable estimates.",
    "cov_var_check": "An independent cross-check: beta computed as Covariance(stock, benchmark) / Variance(benchmark) should exactly match the regression-based beta. PASS confirms the math is internally consistent.",
    "book_de": "Debt-to-equity from balance sheet (book) values, not market values — market-value D/E would need additional market-cap data this tool doesn't currently pull.",
    "eff_tax_rate": "The tax rate actually paid (tax expense ÷ pre-tax income) in the most recent fiscal year — not necessarily the statutory/marginal rate.",
    "unlevered_beta": "A peer's beta with the effect of its own debt (capital structure) removed, isolating pure business/asset risk — the Hamada equation.",
    "bottom_up_mean": "The target's beta estimated by averaging peers' unlevered betas and re-levering to the target's own capital structure. Useful when the target lacks a reliable trading history.",
    "bottom_up_median": "Same methodology as the mean version, but using the median of peers' unlevered betas — more robust to one outlier peer distorting the result.",
    "beta_range": "The spread between the lowest and highest beta produced across all methodology combinations run (different benchmarks, lookback periods, frequencies).",
    "median_beta_sens": "The middle value of all betas produced across the methodology combinations — less sensitive to one or two extreme combinations than a simple average.",
    "rolling_beta": "Beta re-calculated on a moving (trailing) window through time, rather than once over the whole period — shows whether the relationship to the benchmark has drifted.",
    "risk_free_rate": "The return on a theoretically risk-free investment — typically the yield on a long-term government bond (e.g. 10-year G-Sec for India).",
    "erp": "Equity Risk Premium — the extra return investors demand for holding stocks over risk-free government bonds.",
    "cost_of_equity": "The return shareholders require for holding this stock, via CAPM: Risk-free rate + Beta × Equity Risk Premium.",
}


def info_icon(key: str) -> str:
    """Small circled-i with a native browser tooltip (title attribute) - no
    JS, no extra component, works identically in light and dark mode."""
    text = GLOSSARY.get(key, "").replace('"', "&quot;")
    return (
        f"<span title=\"{text}\" style='cursor:help; color:{T['text_muted']}; "
        f"font-size:10px; border:1px solid {T['text_muted']}; border-radius:50%; "
        f"width:13px; height:13px; display:inline-flex; align-items:center; justify-content:center; "
        f"margin-left:5px; vertical-align:middle;'>i</span>"
    )


st.title("Beta Calculator")
st.caption("Historical & Bottom-Up Equity Beta Analysis")

if "history" not in st.session_state:
    st.session_state.history = []
if "peers" not in st.session_state:
    st.session_state.peers = []
if "single_result" not in st.session_state:
    st.session_state.single_result = None
if "bottom_up_result" not in st.session_state:
    st.session_state.bottom_up_result = None


def log_history(ticker, context):
    st.session_state.history.insert(0, {
        "ticker": ticker, "context": context,
        "time": datetime.now().strftime("%H:%M:%S")
    })
    st.session_state.history = st.session_state.history[:15]


@st.cache_data(ttl=900, show_spinner=False)
def cached_calculate_stock_beta(ticker, index_key, period, interval, start=None, end=None):
    return calculate_stock_beta(ticker, index_key, period, interval, start, end)


@st.cache_data(ttl=900, show_spinner=False)
def cached_fetch_financials(ticker):
    return fetch_company_financials(ticker)


@st.cache_data(ttl=900, show_spinner=False)
def cached_prices(ticker, period, interval, start=None, end=None):
    return fetch_prices(ticker, period, interval, start, end)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_search_company(query):
    return search_company(query)


def searchbox_callback(searchterm: str):
    if not searchterm or len(searchterm.strip()) < 2:
        return []
    res = cached_search_company(searchterm)
    return [(f"{r['symbol']} — {r['name']} ({r['exchange']})", r["symbol"]) for r in res["results"]]


with st.sidebar:
    st.markdown("### Session History")
    if not st.session_state.history:
        st.caption("Tickers you calculate will show up here.")
    for h in st.session_state.history:
        st.markdown(f"**{h['ticker']}** · {h['context']}  \n<span style='color:{T['text_muted']}'>{h['time']}</span>",
                     unsafe_allow_html=True)

tab_beta, tab_bottomup, tab_coe = st.tabs(["Beta Analysis", "Bottom-Up Beta", "Cost of Equity"])

with tab_beta:

    with st.container(border=True):
        ticker_mode = st.radio("Ticker type", ["Stock", "Index"], horizontal=True, key="t1_mode")

        if ticker_mode == "Stock":
            picked = searchbox_fragment(
                searchbox_callback,
                placeholder="Search company name (e.g. Reliance) or type a ticker directly...",
                key="t1_searchbox",
                default_use_searchterm=True,
                style_overrides=searchbox_style(T),
            )
            c1, c2, c3, c4 = st.columns([2, 1.6, 1, 1])
            with c1:
                ticker1 = picked or "RELIANCE.NS"
                st.caption(f"Using ticker: **{ticker1}**")
        else:
            c1, c2, c3, c4 = st.columns([2, 1.6, 1, 1])
            with c1:
                index_ticker_label = searchbox_fragment(
                    benchmark_searchbox_callback, placeholder="Search or select an index...",
                    key="t1_index_ticker_sb", default_options=[(l, l) for l in COMMON_BENCHMARKS],
                    style_overrides=searchbox_style(T),
                ) or DEFAULT_BENCHMARK
                ticker1 = INDEX_LABELS[index_ticker_label]

        with c2:
            idx1_label = searchbox_fragment(
                benchmark_searchbox_callback, placeholder="Search or select a benchmark...",
                key="t1_idx_sb", default_options=[(l, l) for l in COMMON_BENCHMARKS],
                style_overrides=searchbox_style(T),
            ) or DEFAULT_BENCHMARK
            st.caption(f"Ticker: `{INDEX_TICKERS[label_to_name(idx1_label)]}`")
        with c3:
            period1 = st.selectbox("Lookback", ["1y", "3y", "5y", "Custom"], index=1, key="t1_period")
        with c4:
            interval1_display = st.selectbox("Frequency", list(DISPLAY_TO_INTERVAL.keys()),
                                              index=1, key="t1_interval")

        custom_start, custom_end = None, None
        if period1 == "Custom":
            dc1, dc2, _ = st.columns([1, 1, 2])  # full-width row, plenty of room for both dates
            with dc1:
                custom_start = st.date_input("From", value=datetime.now() - timedelta(days=3 * 365),
                                              key="t1_custom_start")
            with dc2:
                custom_end = st.date_input("To", value=datetime.now(), key="t1_custom_end")
            if custom_start >= custom_end:
                st.warning("'From' date must be before 'To' date.")

        st.caption(
            "Unlike Yahoo Finance and most aggregators, which benchmark every stock against the "
            "S&P 500 regardless of its home market, this uses whichever index you select above. "
            "For an INR-based cost-of-equity analysis, a broad Indian index (Nifty 50, Nifty 500) "
            "is often a reasonable choice — but benchmark selection should reflect the investment "
            "universe and purpose of the analysis, not a single universally 'correct' answer."
        )

        calc_clicked = st.button("Calculate Beta", key="t1_calc", use_container_width=False)

    if calc_clicked:
        interval1 = DISPLAY_TO_INTERVAL[interval1_display]
        idx1_name = label_to_name(idx1_label)
        start_str = str(custom_start) if period1 == "Custom" and custom_start else None
        end_str = str(custom_end) if period1 == "Custom" and custom_end else None
        period_for_calc = period1 if period1 != "Custom" else "3y"  # fallback, ignored when start/end given
        try:
            with st.spinner("Fetching data and running regression..."):
                result = cached_calculate_stock_beta(ticker1, idx1_name, period_for_calc, interval1,
                                                       start_str, end_str)
                stock_prices = cached_prices(ticker1, period_for_calc, interval1, start_str, end_str)
                index_prices = cached_prices(INDEX_TICKERS[idx1_name], period_for_calc, interval1,
                                              start_str, end_str)
            st.session_state.single_result = result
            st.session_state.single_prices = (stock_prices, index_prices, interval1)
            period_label = f"{start_str} to {end_str}" if start_str else period1
            log_history(ticker1, f"Single beta ({idx1_name}, {period_label}/{interval1_display})")
        except Exception as e:
            st.error(f"Couldn't calculate beta: {e}")
            st.session_state.single_result = None

    result = st.session_state.single_result

    if result:
        market_audit = result.get("market_audit")
        if market_audit and market_audit.get("is_cross_market"):
            st.warning(market_audit["warning"])

        section_header("Result")

        hero_number("Historical Beta", result["beta_regression"],
                    subtitle=f"{result['benchmark']} • {result['period'].upper()} • {interval1_display}",
                    glossary_key="beta")

        hr1, hr2, hr3, hr4 = st.columns(4)
        hr1.metric("Blume-Adjusted", result["beta_blume_adjusted"], help=GLOSSARY["blume"])
        hr2.metric("95% CI", f"{result['ci_95_low']} – {result['ci_95_high']}", help=GLOSSARY["ci95"])
        hr3.metric("R²", result["r_squared"], help=GLOSSARY["r_squared"])
        hr4.metric("N", result["n_observations"], help=GLOSSARY["n_obs"])

        st.markdown(beta_interpretation(result["beta_regression"]))

        dq1, dq2 = st.columns([1, 3])
        with dq1:
            data_quality_badge(result["sample_size_tier"], result["n_observations"])
        with dq2:
            css_class = "badge-pass" if result["beta_match_check"] == "PASS" else "badge-fail"
            st.markdown(
                f"Cov/Variance cross-check{info_icon('cov_var_check')}: "
                f"<span class='{css_class}'>{result['beta_match_check']}</span><br>"
                f"<span style='font-size:13px; color:{T['text_muted']};'>"
                f"Calculated at {result['calculated_at']} — cached for up to 15 minutes.</span>",
                unsafe_allow_html=True,
            )

        sp, ip, _ = st.session_state.single_prices
        p1, p2 = st.columns(2)
        p1.metric(f"{ticker1} last close (adj.)", f"{sp.iloc[-1]:,.2f}", help=f"As of {sp.index[-1].date()}")
        idx_display_ticker = INDEX_TICKERS[label_to_name(idx1_label)]
        p2.metric(f"{idx_display_ticker} last close", f"{ip.iloc[-1]:,.2f}", help=f"As of {ip.index[-1].date()}")

        section_header("Statistical Evidence", subtitle="How does the stock move with the benchmark, and how confident should you be in that?")

        sig_class = "badge-pass" if result["significance"].startswith(("Strong", "Significant")) else "badge-warn"
        exp_class = "badge-pass" if result["explanatory_power"].startswith("High") else (
            "badge-warn" if result["explanatory_power"].startswith("Moderate") else "badge-fail")

        def diagnostic_card(label, glossary_key, value, css_class):
            st.markdown(
                f"<div style='background-color:{T['surface2']}; border:0.5px solid {T['border']}; "
                f"border-radius:8px; padding:10px 14px;'>"
                f"<span style='font-size:11px; letter-spacing:1px; color:{T['text_muted']}; "
                f"font-weight:600;'>{label.upper()}{info_icon(glossary_key)}</span><br>"
                f"<span class='{css_class}' style='font-size:14px;'>{value}</span></div>",
                unsafe_allow_html=True,
            )

        ev1, ev2 = st.columns(2)
        with ev1:
            diagnostic_card("Statistical Significance", "significance", result["significance"], sig_class)
        with ev2:
            diagnostic_card("Explanatory Power (R²)", "explanatory_power", result["explanatory_power"], exp_class)

        _, _, used_interval = st.session_state.single_prices
        reg_data = result["regression_data"]
        sr, ir = reg_data["stock_return"], reg_data["index_return"]

        x_line = np.linspace(ir.min(), ir.max(), 50)
        y_center, y_low, y_high = regression_mean_ci_band(x_line, result)
        plot_template = "plotly_dark" if st.session_state.theme == "dark" else "plotly_white"

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ir, y=sr, mode="markers",
                                  marker=dict(color=T["accent"], size=6, opacity=0.5), name="Returns"))
        fig.add_trace(go.Scatter(x=x_line, y=y_low, mode="lines",
                                  line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x_line, y=y_high, mode="lines", line=dict(width=0),
                                  fill="tonexty", fillcolor=f"{T['amber']}26",
                                  name="95% CI (fitted line)", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x_line, y=y_center, mode="lines",
                                  line=dict(color=T["amber"], width=2), name="Regression line"))
        fig.update_layout(template=plot_template, paper_bgcolor=T["bg"], plot_bgcolor=T["bg"],
                           title=f"Stock vs Benchmark Returns  ·  {interval1_display} returns, last {result['period']}",
                           xaxis_title="Index return", yaxis_title="Stock return",
                           height=400, margin=dict(t=40))
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        st.caption("Shaded band = 95% confidence interval for the fitted regression line itself "
                    "(narrower near the middle of the data, wider at the extremes) — not the same "
                    "as the beta coefficient's own CI shown above.")

        st.markdown("###### Full diagnostics")
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Correlation", result["correlation"], help=GLOSSARY["correlation"])
        d2.metric("Std Error", result["std_error"], help=GLOSSARY["std_error"])
        d3.metric("t-stat", result["t_stat"], help=GLOSSARY["t_stat"])
        p_display = "< 0.001" if result["p_value"] < 0.001 else f"{result['p_value']:.4f}"
        d4.metric("p-value", p_display, help=GLOSSARY["p_value"])
        d5.metric("Alpha (ann.)", f"{result['alpha_annualized_pct']}%", help=GLOSSARY["alpha"])

        section_header("Beta Stability", subtitle="Is the historical beta stable over time, or drifting?")
        window = 26 if used_interval == "1wk" else (12 if used_interval == "1mo" else 60)
        rb = rolling_beta(sr, ir, window=window)
        if len(rb) > 2:
            window_months = {"1wk": window / 4.33, "1mo": window, "1d": window / 21}.get(used_interval)
            rb_median = round(rb.median(), 3)
            median_color = T["text"]  # near-white in dark theme, clearly distinct from amber and teal
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=rb.index, y=rb.values, mode="lines",
                                       line=dict(color=T["accent"], width=2), name="Rolling beta"))
            # No on-chart text annotations here - two annotation labels sitting close
            # together on the plot area overlapped and became unreadable. A legend
            # with the actual values sits below the chart instead.
            fig2.add_hline(y=result["beta_regression"], line_dash="dash", line_color=T["amber"])
            fig2.add_hline(y=rb_median, line_dash="dot", line_color=median_color)
            fig2.update_layout(template=plot_template, paper_bgcolor=T["bg"], plot_bgcolor=T["bg"],
                                title=f"Rolling Beta  ·  trailing {window}-observation window "
                                      f"(~{window_months:.0f} months), {interval1_display.lower()} steps",
                                yaxis_title="Beta", height=350, margin=dict(t=40))
            st.plotly_chart(fig2, use_container_width=True, config=PLOTLY_CONFIG)
            st.markdown(
                f"<div style='text-align:center;'>"
                f"<span style='color:{T['amber']}; font-weight:700;'>●</span> Full-period beta: "
                f"<b>{result['beta_regression']}</b> &nbsp;&nbsp;&nbsp; "
                f"<span style='color:{median_color}; font-weight:700;'>●</span> Median (rolling): "
                f"<b>{rb_median}</b></div>",
                unsafe_allow_html=True,
            )
            st.caption(
                f"Each point re-calculates beta using only the trailing {window} {interval1_display.lower()} "
                f"observations (~{window_months:.0f} months) up to that date, sliding forward one observation "
                f"at a time across the full {result['period']} lookback — so it shows how beta would have looked if "
                f"you'd calculated it at each point in time, not just once over the whole period."
            )
        else:
            st.caption("Not enough observations for a rolling beta chart at this lookback/frequency.")
    else:
        st.info("Set up a ticker and benchmark above, then click Calculate Beta to see the result.")

    section_header("Sensitivity Analysis", subtitle=f"How does {ticker1}'s beta move across benchmark, lookback, and frequency choices?")

    s1, s2, s3 = st.columns(3)
    with s1:
        periods2 = st.multiselect("Lookback periods", ["1y", "3y", "5y", "Custom"], default=["1y", "3y", "5y"])
    with s2:
        intervals2_display = st.multiselect("Frequencies", list(DISPLAY_TO_INTERVAL.keys()),
                                             default=["Weekly", "Monthly"])
    with s3:
        indices2_display = st.multiselect("Benchmarks", BENCHMARK_OPTIONS, default=[DEFAULT_BENCHMARK])

    sens_custom_start, sens_custom_end = None, None
    if "Custom" in periods2:
        sc1, sc2, _ = st.columns([1, 1, 2])
        with sc1:
            sens_custom_start = st.date_input("From", value=datetime.now() - timedelta(days=3 * 365),
                                               key="t2_custom_start")
        with sc2:
            sens_custom_end = st.date_input("To", value=datetime.now(), key="t2_custom_end")
        if sens_custom_start >= sens_custom_end:
            st.warning("'From' date must be before 'To' date.")

    if st.button("Run Sensitivity Table", key="t2_run"):
        intervals2 = [DISPLAY_TO_INTERVAL[i] for i in intervals2_display]
        indices2 = [label_to_name(i) for i in indices2_display]
        if not (periods2 and intervals2 and indices2):
            st.warning("Pick at least one option in each column.")
        else:
            with st.spinner("Running combinations..."):
                df_sens = beta_sensitivity(
                    ticker1, periods=tuple(periods2), intervals=tuple(intervals2), index_keys=tuple(indices2),
                    custom_start=str(sens_custom_start) if sens_custom_start else None,
                    custom_end=str(sens_custom_end) if sens_custom_end else None,
                )
            st.session_state.sensitivity_df = df_sens
            st.session_state.sensitivity_ticker = ticker1  # remember which ticker this table is for
            log_history(ticker1, "Sensitivity table")

    if "sensitivity_df" in st.session_state:
        sens_ticker = st.session_state.get("sensitivity_ticker")
        if sens_ticker != ticker1:
            st.markdown(
                f"<span class='badge-warn'>⚠ This table is for {sens_ticker}</span> — "
                f"you've since changed the ticker above to {ticker1}. "
                f"Click **Run Sensitivity Table** again to update it.",
                unsafe_allow_html=True,
            )
        df_sens = st.session_state.sensitivity_df
        valid = df_sens.dropna(subset=["beta"])
        failed = df_sens[df_sens["status"] == "error"]
        chart_template = "plotly_dark" if st.session_state.theme == "dark" else "plotly_white"

        if not valid.empty:
            bmin, bmax = valid["beta"].min(), valid["beta"].max()
            bmedian = round(valid["beta"].median(), 3)
            sr1, sr2, sr3, sr4 = st.columns(4)
            sr1.metric("Beta Range", f"{bmin} – {bmax}", help=GLOSSARY["beta_range"])
            sr2.metric("Median Beta", bmedian, help=GLOSSARY["median_beta_sens"])
            if result and result.get("ticker") == ticker1:
                sr3.metric("Current Specification", result["beta_regression"],
                           help="The beta from the Result section above, using your current Setup choices.")
            sr4.metric("Specifications", len(valid),
                       help="Number of benchmark x lookback x frequency combinations successfully calculated.")
            spread = bmax - bmin
            if spread < 0.3:
                st.caption(f"Beta is relatively stable across benchmark and lookback choices "
                           f"(range of {round(spread, 2)}).")
            else:
                st.caption(f"Beta varies meaningfully across methodology choices "
                           f"(range of {round(spread, 2)}) — check which combinations drive the spread "
                           f"before relying on a single number.")

        if not failed.empty:
            for _, row in failed.iterrows():
                st.markdown(f"<span class='badge-fail'>⚠ {row['benchmark']} / {row['period']} / "
                            f"{row['interval']}</span>: {row['error']}", unsafe_allow_html=True)

        for bench in valid["benchmark"].unique():
            sub = valid[valid["benchmark"] == bench]
            preset_periods = [p for p in ["1y", "3y", "5y"] if p in sub["period"].unique()]
            custom_periods = sorted(p for p in sub["period"].unique() if p not in ["1y", "3y", "5y"])
            periods_order = preset_periods + custom_periods
            intervals_order = [i for i in ["1d", "1wk", "1mo"] if i in sub["interval"].unique()]

            z = [[sub[(sub["period"] == p) & (sub["interval"] == iv)]["beta"].values[0]
                  if not sub[(sub["period"] == p) & (sub["interval"] == iv)].empty else None
                  for iv in intervals_order] for p in periods_order]
            text = [[
                (f"{sub[(sub['period'] == p) & (sub['interval'] == iv)]['beta'].values[0]}"
                 f"<br>R²={sub[(sub['period'] == p) & (sub['interval'] == iv)]['r_squared'].values[0]}")
                if not sub[(sub["period"] == p) & (sub["interval"] == iv)].empty else ""
                for iv in intervals_order] for p in periods_order]

            fig_hm = go.Figure(data=go.Heatmap(
                z=z, x=intervals_order, y=periods_order, text=text, texttemplate="%{text}",
                colorscale=[[0, T["surface1"]], [1, T["accent"]]],
                showscale=False, xgap=4, ygap=4,
            ))
            fig_hm.update_layout(template=chart_template,
                                  paper_bgcolor=T["bg"], plot_bgcolor=T["bg"],
                                  title=f"{bench} — beta by lookback × frequency", height=220,
                                  margin=dict(t=40, b=20))
            st.plotly_chart(fig_hm, use_container_width=True, config=PLOTLY_CONFIG)

        with st.expander("Raw table + CSV download"):
            st.dataframe(df_sens, use_container_width=True)
            st.download_button("Download as CSV", df_sens.to_csv(index=False),
                                file_name=f"{ticker1}_beta_sensitivity.csv", mime="text/csv")

    section_header("Data & Methodology")
    with st.expander("Regression methodology, price adjustment, and data audit"):
        st.markdown("""
**Regression:** `stock_return = α + β × benchmark_return + ε`, ordinary least squares,
cross-checked independently against `Cov(stock, benchmark) / Var(benchmark)`.

**Price data:** Yahoo Finance, auto-adjusted for dividends and splits.

**Returns:** simple period-over-period percentage returns.

**Date alignment:** inner join on trading dates — only dates where both the stock and
benchmark have data are used; this is why the matched regression sample is usually
smaller than either series' raw observation count.

**Confidence intervals:** Student-t critical value for the sample's actual degrees of
freedom (n − 2), not a fixed 1.96 — matters most for small samples like 1Y monthly (~11 obs).
        """)
        if result:
            a = result["audit"]
            ma = result.get("market_audit", {})
            st.markdown(f"""
**Current single-stock calculation — Data / Date Alignment Audit:**
- Stock: {result['ticker']} — {a['stock_raw_price_obs']} raw prices ({a['stock_date_range']}), {a['stock_return_obs']} return observations, {a['stock_missing_values_dropped']} dropped for missing values
- Benchmark: {result['benchmark']} ({result['benchmark_ticker']}) — {a['index_raw_price_obs']} raw prices ({a['index_date_range']}), {a['index_return_obs']} return observations, {a['index_missing_values_dropped']} dropped for missing values
- Matched regression sample: {a['matched_regression_obs']} observations, {a['matched_date_range']}
- Dates present for the stock only (dropped by the inner join): {a['stock_only_dates']}
- Dates present for the benchmark only (dropped by the inner join): {a['benchmark_only_dates']}
- Market/calendar check: {result['ticker']} ({ma.get('stock_region', '?')}) vs {result['benchmark']} ({ma.get('benchmark_region', '?')}) — {"cross-market" if ma.get('is_cross_market') else "same market"}
- Annualization convention: {result['annualization_convention']}
            """)
            st.caption(
                "This audit reflects exactly what was used in the regression above — it isn't a "
                "separate recalculation, just the alignment bookkeeping made explicit. No prices are "
                "forward-filled or zero-filled to force calendars to match; only genuinely overlapping "
                "trading dates go into the regression."
            )

with tab_bottomup:
    section_header("Bottom-Up Beta",
                    subtitle="Estimates beta from comparable companies rather than the subject company's own historical returns — for illiquid, recently listed, or unlisted names.")

    with st.container(border=True):
        st.markdown("**Target company**")
        tc1, tc2, tc3, tc4, tc5 = st.columns([1, 1, 1.6, 0.8, 0.9])
        with tc1:
            target_de = st.number_input("Target Book D/E", value=0.30, step=0.05, key="target_de",
                                         help=GLOSSARY["book_de"])
        with tc2:
            target_tax = st.number_input("Target effective tax rate", value=0.25, step=0.01, key="target_tax",
                                          help=GLOSSARY["eff_tax_rate"])
        with tc3:
            st.caption("Benchmark (for peer betas)")
            bu_index_display = searchbox_fragment(
                benchmark_searchbox_callback, placeholder="Search or select a benchmark...",
                key="bu_idx_sb", default_options=[(l, l) for l in COMMON_BENCHMARKS],
                style_overrides=searchbox_style(T),
            ) or DEFAULT_BENCHMARK
        with tc4:
            bu_period = st.selectbox("Lookback", ["1y", "3y", "5y"], index=1, key="bu_period")
        with tc5:
            bu_interval_display = st.selectbox("Frequency", list(DISPLAY_TO_INTERVAL.keys()),
                                                index=1, key="bu_interval")
        st.caption("Lookback and frequency apply to every peer's individual beta calculation before unlevering.")

        st.markdown("**Add peers**")
        ap1, ap2 = st.columns([3, 1])
        with ap1:
            new_peer_picked = searchbox_fragment(
                searchbox_callback,
                placeholder="Search company name or type a ticker directly...",
                key="t3_searchbox",
                default_use_searchterm=True,
                style_overrides=searchbox_style(T),
            )
        with ap2:
            add_clicked = st.button("Add Peer", use_container_width=True)

        if add_clicked and new_peer_picked:
            with st.spinner(f"Fetching {new_peer_picked}..."):
                fin = cached_fetch_financials(new_peer_picked)
            st.session_state.peers.append({
                "ticker": new_peer_picked.strip().upper(),
                "debt_equity": fin["debt_equity"] if fin["debt_equity"] is not None else 0.30,
                "de_source": fin["debt_equity_source"],
                "tax_rate": fin["tax_rate"] if fin["tax_rate"] is not None else 0.25,
                "tax_source": fin["tax_rate_source"],
                "balance_sheet_date": fin["balance_sheet_date"],
                "tax_statement_date": fin["tax_statement_date"],
                "include": True,
            })

        if st.session_state.peers:
            st.markdown("**Peer set**")
            header = st.columns([0.6, 2, 1.5, 1.5, 1, 0.7])
            header[0].markdown("**Use**")
            header[1].markdown("**Ticker**")
            header[2].markdown("**Book D/E**")
            header[3].markdown("**Eff. Tax Rate**")
            header[4].markdown("**Source**")
            header[5].markdown("**Remove**")

            to_remove = None
            for i, p in enumerate(st.session_state.peers):
                row = st.columns([0.6, 2, 1.5, 1.5, 1, 0.7])
                p["include"] = row[0].checkbox("", value=p["include"], key=f"inc_{i}", label_visibility="collapsed")
                row[1].markdown(p["ticker"])
                bs_date = p.get("balance_sheet_date")
                de_help = f"Balance sheet date: {bs_date}" if bs_date else "Manually entered"
                p["debt_equity"] = row[2].number_input("", value=float(p["debt_equity"]), step=0.05,
                                                         key=f"de_{i}", label_visibility="collapsed", help=de_help)
                tax_date = p.get("tax_statement_date")
                tax_help = f"Income statement date: {tax_date}" if tax_date else "Manually entered"
                p["tax_rate"] = row[3].number_input("", value=float(p["tax_rate"]), step=0.01,
                                                     key=f"tax_{i}", label_visibility="collapsed", help=tax_help)
                src_label = "auto" if p["de_source"] == "auto-fetched" else "manual"
                row[4].caption(src_label)
                if row[5].button("✕", key=f"rm_{i}"):
                    to_remove = i
            if to_remove is not None:
                st.session_state.peers.pop(to_remove)
                st.rerun()

            if st.button("Recalculate Bottom-Up Beta", key="t3_calc"):
                active_peers = [
                    {"ticker": p["ticker"], "debt_equity": p["debt_equity"], "tax_rate": p["tax_rate"]}
                    for p in st.session_state.peers if p["include"]
                ]
                if not active_peers:
                    st.warning("Check at least one peer to include.")
                else:
                    bu_index = label_to_name(bu_index_display)
                    bu_interval = DISPLAY_TO_INTERVAL[bu_interval_display]
                    with st.spinner("Calculating peer betas and unlevering..."):
                        try:
                            res = bottom_up_beta(active_peers, target_de, target_tax, index_key=bu_index,
                                                  period=bu_period, interval=bu_interval)
                            st.session_state.bottom_up_result = res
                            log_history(", ".join(p["ticker"] for p in active_peers), "Bottom-up beta")
                        except Exception as e:
                            st.error(f"Couldn't calculate: {e}")

    if st.session_state.bottom_up_result:
        res = st.session_state.bottom_up_result
        bu1, bu2 = st.columns(2)
        bu1.metric("Bottom-Up Beta (mean)", res["bottom_up_beta"], help=GLOSSARY["bottom_up_mean"])
        bu2.metric("Bottom-Up Beta (median)", res["bottom_up_beta_median"], help=GLOSSARY["bottom_up_median"])
        st.caption(f"Mean unlevered (asset) beta: {res['average_unlevered_beta']} · "
                   f"Median unlevered beta: {res['median_unlevered_beta']} · "
                   f"Peer median Book D/E: {res['median_debt_equity']}")
        st.caption("Mean is the default methodology; median is shown as a robustness check — "
                   "if the two disagree meaningfully, an outlier peer is likely distorting the mean.")

        if res["failed_peers"]:
            for fp in res["failed_peers"]:
                st.markdown(f"<span class='badge-fail'>⚠ {fp['ticker']} excluded</span>: {fp['error']}",
                            unsafe_allow_html=True)
            st.caption(f"The betas above are calculated from the {len(res['peer_details']) - len(res['failed_peers'])} "
                       f"peer(s) that succeeded — excluded peers did not affect the result.")

        detail_df = pd.DataFrame(res["peer_details"]).drop(columns=["de_outlier_flag", "status", "error"],
                                                             errors="ignore")
        st.dataframe(detail_df, use_container_width=True)

        for d in res["peer_details"]:
            if d.get("de_outlier_flag"):
                st.markdown(f"<span class='badge-warn'>⚠ {d['ticker']}</span>: {d['de_outlier_flag']}",
                            unsafe_allow_html=True)
            if d.get("r_squared") is not None and d["r_squared"] < 0.2:
                st.markdown(f"<span class='badge-warn'>⚠ {d['ticker']}</span>: R² of {d['r_squared']} "
                            f"is low - this peer's own beta may not be reliable",
                            unsafe_allow_html=True)

with tab_coe:
    st.caption("Bridges into the reverse DCF later - CAPM needs a discount rate, this is where it comes from.")

    if "ce_beta" not in st.session_state:
        st.session_state.ce_beta = 1.0

    def sync_beta_from_analysis():
        if st.session_state.single_result:
            st.session_state.ce_beta = st.session_state.single_result["beta_regression"]

    def sync_beta_from_bottom_up():
        if st.session_state.bottom_up_result:
            st.session_state.ce_beta = st.session_state.bottom_up_result["bottom_up_beta"]

    ce1, ce2, ce3 = st.columns(3)
    with ce1:
        beta_input = st.number_input("Beta", step=0.01, key="ce_beta", help=GLOSSARY["beta"])
        sync_disabled_ba = st.session_state.single_result is None
        sync_disabled_bu = st.session_state.bottom_up_result is None
        sb1, sb2 = st.columns(2)
        with sb1:
            st.button("↻ From Beta Analysis", key="ce_sync_ba", on_click=sync_beta_from_analysis,
                       disabled=sync_disabled_ba, use_container_width=True)
        with sb2:
            st.button("↻ From Bottom-Up Beta", key="ce_sync_bu", on_click=sync_beta_from_bottom_up,
                       disabled=sync_disabled_bu, use_container_width=True)
        captions = []
        if not sync_disabled_ba:
            captions.append(f"Beta Analysis: {st.session_state.single_result['beta_regression']}")
        if not sync_disabled_bu:
            captions.append(f"Bottom-Up (mean): {st.session_state.bottom_up_result['bottom_up_beta']}")
        st.caption(" · ".join(captions) if captions else
                   "Calculate a beta in Beta Analysis or Bottom-Up Beta first, then sync it here.")
    with ce2:
        rf_input = st.number_input("Risk-free rate (%)", value=6.9, step=0.1, key="ce_rf",
                                    help=GLOSSARY["risk_free_rate"])
        st.caption("Defaults to an approximate 10Y G-Sec yield - check the current rate and update.")
    with ce3:
        erp_input = st.number_input("Equity risk premium (%)", value=6.0, step=0.1, key="ce_erp",
                                     help=GLOSSARY["erp"])
        st.caption("Typical India ERP range is roughly 6-6.5% - adjust to your own view.")

    cost_of_equity = rf_input + beta_input * erp_input
    st.session_state.ce_cost_of_equity = cost_of_equity  # bridged into Reverse DCF's Ke fields
    st.divider()
    st.metric("Cost of Equity (CAPM)", f"{round(cost_of_equity, 2)}%", help=GLOSSARY["cost_of_equity"])
    st.caption(f"= {rf_input}% + ({beta_input} × {erp_input}%)")
    st.caption("This value is available to the Reverse DCF page's Net Income and FCFE tabs "
               "as a one-click Ke default once calculated here.")

st.divider()
st.caption("[GitHub](https://github.com/deepeshjoshii) · Source and other tools for this project.")
render_disclaimer(T)
