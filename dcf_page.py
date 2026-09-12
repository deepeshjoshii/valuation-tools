"""
Reverse DCF Calculator - Streamlit UI (V2)
Three methodologies sharing one solver: Net Income/Ke, FCFF/WACC, FCFE/Ke.

Shares its visual identity with the Beta Calculator (same THEMES/CSS,
same company-searchbox pattern via beta_calculator.search_company) so the
two feel like one product rather than two different tools bolted together.

Display convention: every rupee figure is shown in Rs Crore (Rs Lakh Crore
above 1,00,000 Cr) with Indian digit grouping, EXCEPT the current market
price (CMP), which stays as per-share Rs (also Indian-grouped, just not
Crore-scaled).

Why three tabs: FCFF's line-item construction (CFO, interest, CapEx) turned
out to be unreliable for a lot of Indian tickers on the free yfinance feed -
Net Income is the most reliably-scraped headline figure (at the cost of
including one-off items), and FCFE sits in between. All three share the
same Gordon-Growth/Brent's-method engine underneath - only the flow series,
discount rate (Ke vs WACC) and target value (Market Cap vs Enterprise
Value) differ. See reverse_dcf.py's module docstring for the full pairing
rationale.

Place this file alongside beta_calculator.py (same folder) so the company
search box can import search_company from it, and so the Ke bridge below
can read the Cost of Equity calculated on that page's CAPM tab.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_searchbox import st_searchbox

from reverse_dcf import (
    fetch_company_financials,
    solve_implied_cagr,
    flow_trajectory,
    trailing_cagr_with_reason,
    value_at_growth,
    estimate_cost_of_debt,
    compute_wacc,
    sensitivity_grid,
    value_at_growth_exit_multiple,
    solve_implied_cagr_exit_multiple,
    sensitivity_grid_exit_multiple,
)

try:
    from beta_calculator import search_company
except ImportError:
    search_company = None

CR = 1e7  # 1 Crore = 10,000,000
LAKH_CR = 100_000  # 1 Lakh Crore, expressed in Cr units

# ============================================================
# PAGE CONFIG + THEME (identical palette to the Beta Calculator)
# ============================================================
from theme import THEMES, searchbox_style, render_disclaimer, PLOTLY_CONFIG, friendly_error, show_error_detail

if "theme" not in st.session_state:
    st.session_state.theme = "dark"

T = THEMES[st.session_state.theme]

ZONE_HISTORICAL = f"{T['border']}80"
ZONE_PROJECTION = f"{T['accent']}14"
ZONE_TERMINAL = f"{T['amber']}14"
PLOT_TEMPLATE = "plotly_dark" if st.session_state.theme == "dark" else "plotly_white"


GLOSSARY = {
    "implied_cagr": "The constant annual growth rate this flow would need to sustain over the projection period to justify today's price — solved backwards from the market price, not assumed.",
    "terminal_growth": "The growth rate assumed forever after the explicit projection period ends (Gordon Growth model). Should be a conservative, sustainable long-run rate — well below the explicit-period CAGR for a maturing business.",
    "wacc": "Weighted Average Cost of Capital — the discount rate for FCFF (a firm-level flow, before financing effects). Blends the cost of equity and after-tax cost of debt, weighted by market value.",
    "ke": "Cost of Equity — the return equity holders require. Used to discount Net Income and FCFE (both already after interest — equity-level flows), against Market Cap.",
    "kd": "Cost of Debt — the rate the company pays lenders. Estimated here as Interest Expense ÷ Total Debt (a backward-looking accounting average), not a market rate — verify independently.",
    "target_ev": "Enterprise Value = Market Cap + Net Debt. The correct target for a WACC-discounted FCFF DCF, since FCFF belongs to all capital providers, not just shareholders.",
    "target_mcap": "Market Capitalization = Price × Shares Outstanding. The correct target for a Ke-discounted Net Income or FCFE DCF, since both flows already belong to equity holders only.",
    "terminal_value_share": "What fraction of total value comes from the terminal value versus the explicit forecast period. Naturally high for long projection windows or a wide rate-to-growth spread — not inherently a red flag on its own.",
    "historical_cagr": "The company's own actual growth rate over the trailing window shown, computed from the (possibly edited) historical table above — compare against the implied CAGR to see how big an expectations gap the market price bakes in.",
    "sensitivity_grid": "Shows how the required CAGR changes across a range of discount-rate and terminal-growth (or exit-multiple) assumptions, since both are estimates you're making, not observed facts.",
    "exit_multiple": "An alternative to assuming perpetual growth: applies a P/E-style multiple to the projected terminal-year Net Income to get terminal value, anchored to a market-observed multiple (the stock's own, a peer's, or your own view) instead of a growth rate.",
}


def searchbox_direct(search_fn, **kwargs):
    """Plain app-wide rerun (see V1 notes) - this page has only one searchbox,
    so there's no keystroke-storm to guard against with fragment scoping."""
    return st_searchbox(search_fn, rerun_scope="app", **kwargs)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_search_company(query):
    return search_company(query)


@st.cache_data(ttl=900, show_spinner=False)
def cached_fetch_company_financials(ticker):
    return fetch_company_financials(ticker)


def searchbox_callback(searchterm: str):
    if not searchterm or len(searchterm.strip()) < 2:
        return []
    res = cached_search_company(searchterm)
    return [(f"{r['symbol']} — {r['name']} ({r['exchange']})", r["symbol"]) for r in res["results"]]


def to_cr(x):
    """Raw rupees -> Rs Crore, safe for None."""
    return (x / CR) if x is not None else None


def from_cr(x):
    """Rs Crore -> raw rupees, safe for None."""
    return (x * CR) if x is not None else None


def _indian_grouping(n) -> str:
    """1772077 -> '17,72,077' (Indian digit grouping: last 3, then pairs)."""
    neg = n < 0
    s = str(abs(int(n)))
    if len(s) <= 3:
        out = s
    else:
        last3, rest = s[-3:], s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        out = ",".join(groups) + "," + last3
    return ("-" + out) if neg else out


def fmt_cr(x_cr, decimals=0):
    """Format a value already expressed in Rs Crore, switching to Lakh Cr above 1,00,000 Cr."""
    if x_cr is None:
        return "-"
    if abs(x_cr) >= LAKH_CR:
        return f"Rs {x_cr / LAKH_CR:,.2f} Lakh Cr"
    sign = "-" if x_cr < 0 else ""
    whole = int(abs(x_cr))
    grouped = _indian_grouping(whole)
    if decimals > 0:
        frac = abs(x_cr) - whole
        frac_str = f"{frac:.{decimals}f}".split(".")[1]
        return f"Rs {sign}{grouped}.{frac_str} Cr"
    return f"Rs {sign}{grouped} Cr"


def fmt_inr(x, decimals=2):
    """Format a plain (non-Crore-scaled) rupee amount with Indian digit grouping - for per-share price."""
    if x is None:
        return "-"
    sign = "-" if x < 0 else ""
    whole = int(abs(x))
    grouped = _indian_grouping(whole)
    if decimals > 0:
        frac = abs(x) - whole
        frac_str = f"{frac:.{decimals}f}".split(".")[1]
        return f"Rs {sign}{grouped}.{frac_str}"
    return f"Rs {sign}{grouped}"


def sync_ke_from_beta(state_key: str):
    """Factory for an on_click callback that copies the Beta Calculator's
    CAPM-tab Cost of Equity into this tab's own Ke number_input, the same
    'sync before the widget renders' pattern beta_page.py uses for beta."""
    def _sync():
        if "ce_cost_of_equity" in st.session_state:
            st.session_state[state_key] = round(st.session_state.ce_cost_of_equity, 2)
    return _sync


def ke_input_with_bridge(key_prefix: str, default: float = 13.0) -> float:
    """Renders a Ke (%) number_input plus a one-click 'use Beta Calculator's
    Ke' button. Returns Ke as a decimal (e.g. 0.13)."""
    state_key = f"{key_prefix}_ke_pct"
    if state_key not in st.session_state:
        st.session_state[state_key] = default
    ke_pct = st.number_input("Cost of Equity — Ke (%)", step=0.1, key=state_key, help=GLOSSARY["ke"])
    bridge_available = "ce_cost_of_equity" in st.session_state
    st.button(
        "↻ Use Ke from Beta Calculator's CAPM tab", key=f"{key_prefix}_ke_sync",
        on_click=sync_ke_from_beta(state_key), disabled=not bridge_available,
        use_container_width=True,
    )
    if bridge_available:
        st.caption(f"Beta Calculator's CAPM tab currently has Ke = {st.session_state.ce_cost_of_equity:.2f}%")
    else:
        st.caption("Calculate Cost of Equity in the Beta Calculator's CAPM tab first, then sync it here.")
    return ke_pct / 100


def render_transposed_history_editor(detail: list, row_label: str, editor_key: str):
    """
    Years-as-columns, one editable value row - e.g.:
                    FY2023   FY2024   FY2025   FY2026
    Net Income (Rs Cr)  120      145      160      210
    Returns (edited_raw_values_oldest_to_newest, last_period_label_with_a_value).
    """
    if not detail:
        st.info("No historical data could be built automatically for this period range.")
        return [], None

    periods = [r["period"] for r in detail]
    values_cr = [round(to_cr(r["value"]), 1) if r["value"] is not None else None for r in detail]
    df = pd.DataFrame([values_cr], columns=periods, index=[row_label])

    edited = st.data_editor(
        df, key=editor_key, use_container_width=True,
        column_config={p: st.column_config.NumberColumn(p, help="Editable - override if this looks wrong.")
                       for p in periods},
    )
    edited_cr = edited.iloc[0].tolist()
    edited_raw = [from_cr(float(v)) if v is not None and not pd.isna(v) else None for v in edited_cr]

    skip_notes = [f"{r['period']}: {r['skip_reason']}" for r in detail if r.get("skip_reason")]
    if skip_notes:
        with st.expander(f"Why some years are blank ({len(skip_notes)})", expanded=False):
            for note in skip_notes:
                st.write(f"- {note}")

    last_valid_idx = next((i for i in range(len(edited_raw) - 1, -1, -1) if edited_raw[i] is not None), None)
    last_period = periods[last_valid_idx] if last_valid_idx is not None else None
    return edited_raw, last_period


def render_flow_chart(edited_series: list, last_period_label, trajectory, terminal_growth, projection_years, title: str, show_terminal_extension: bool = True):
    start_year = None
    if last_period_label:
        digits = "".join(ch for ch in last_period_label if ch.isdigit())
        if digits:
            start_year = int(digits[-4:])

    hist_values = edited_series[:-1] if len(edited_series) > 1 else []
    hist_labels = [f"Hist. {i+1}" for i in range(len(hist_values))]  # placeholder, overwritten below if periods known

    # We don't have period labels here directly (caller passes only values) -
    # trajectory/current label carries the anchor point instead.
    current_label = last_period_label or "Current"
    proj_labels, proj_values_cr = [], []
    for pt in trajectory:
        if pt["year"] == 0:
            proj_labels.append(current_label)
        elif start_year:
            proj_labels.append(f"FY{start_year + pt['year']}")
        else:
            proj_labels.append(f"Year {pt['year']}")
        proj_values_cr.append(round(to_cr(pt["flow"]), 1))

    terminal_years_shown = min(projection_years, 10) if show_terminal_extension else 0
    term_labels, term_values_cr = [], []
    last_proj_flow = trajectory[-1]["flow"]
    for t in range(1, terminal_years_shown + 1):
        val = last_proj_flow * (1 + terminal_growth) ** t
        term_values_cr.append(round(to_cr(val), 1))
        term_labels.append(f"FY{start_year + projection_years + t}" if start_year else f"Year {projection_years + t}")

    hist_values_cr = [round(to_cr(v), 1) if v is not None else None for v in hist_values]
    all_labels = hist_labels + proj_labels + term_labels
    all_values = hist_values_cr + proj_values_cr + term_values_cr
    x_idx = list(range(len(all_labels)))

    n_hist = len(hist_labels)
    n_proj_incl_current = len(proj_labels)
    n_term = len(term_labels)

    fig = go.Figure()
    if n_hist > 0:
        fig.add_vrect(x0=-0.5, x1=n_hist - 0.5, fillcolor=ZONE_HISTORICAL, line_width=0,
                      annotation_text="Historical", annotation_position="top left",
                      annotation_font_color=T["text_muted"])
    fig.add_vrect(x0=n_hist - 0.5, x1=n_hist + n_proj_incl_current - 0.5, fillcolor=ZONE_PROJECTION,
                  line_width=0, annotation_text="Projection", annotation_position="top left",
                  annotation_font_color=T["accent"])
    if n_term > 0:
        fig.add_vrect(x0=n_hist + n_proj_incl_current - 0.5,
                      x1=n_hist + n_proj_incl_current + n_term - 0.5,
                      fillcolor=ZONE_TERMINAL, line_width=0,
                      annotation_text="Terminal (illustrative)", annotation_position="top left",
                      annotation_font_color=T["amber"])
    fig.add_trace(go.Scatter(
        x=x_idx, y=all_values, mode="lines+markers",
        line=dict(color=T["accent"], width=2), marker=dict(color=T["accent"], size=6),
        connectgaps=False, name=title,
        hovertemplate="%{text}<br>Rs %{y:,.0f} Cr<extra></extra>", text=all_labels,
    ))
    fig.update_layout(
        template=PLOT_TEMPLATE, paper_bgcolor=T["bg"], plot_bgcolor=T["bg"],
        xaxis=dict(tickmode="array", tickvals=x_idx, ticktext=all_labels, tickangle=-45),
        yaxis_title=f"{title} (Rs Cr)", dragmode=False, height=420, margin=dict(t=60, b=10), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    if show_terminal_extension:
        st.caption(
            "Grey = actual historical figures, teal = the required-CAGR projection being solved for, "
            "amber = an illustrative continuation at the terminal growth rate (not a separate "
            "calculation - just shows what steady-state looks like beyond the explicit forecast)."
        )
    else:
        st.caption(
            "Grey = actual historical figures, teal = the required-CAGR projection being solved for. "
            "No illustrative continuation is drawn here since the terminal value comes from an exit "
            "multiple applied at the end of the projection, not an assumed perpetual growth rate."
        )


st.title("Reverse DCF")
st.caption("What growth rate does today's price already assume?")
st.caption("All figures in Rs Crore (Rs Lakh Crore above 1,00,000 Cr), except current price (per share).")

if search_company is not None:
    picked = searchbox_direct(
        searchbox_callback,
        placeholder="Search company name (e.g. Reliance Industries) or type a ticker directly...",
        key="reverse_dcf_searchbox",
        default_use_searchterm=True,
        style_overrides=searchbox_style(T),
    )
    ticker = picked or ""
    if ticker:
        st.caption(f"Using ticker: **{ticker}**")
else:
    ticker = st.text_input("Ticker (e.g. TATAMOTORS.NS, RELIANCE.NS)")
    st.caption(
        "Company search unavailable - place beta_calculator.py in the same folder as this "
        "app to enable it. Falling back to manual ticker entry."
    )

if ticker:
    with st.spinner("Fetching financials..."):
        try:
            data = cached_fetch_company_financials(ticker)
            fetch_error = None
        except Exception as e:
            data = None
            fetch_error = e

    if fetch_error:
        st.error(friendly_error(fetch_error, ticker))
        show_error_detail(fetch_error)
    elif data.price is None and data.market_cap is None and not any(
        [data.historical_fcff, data.historical_net_income, data.historical_fcfe]
    ):
        st.error(
            f"No data found for '{ticker}'. This usually means the ticker symbol is wrong or "
            f"unlisted on Yahoo Finance — for NSE/BSE stocks, check it ends in .NS or .BO "
            f"(e.g. RELIANCE.NS, not just RELIANCE)."
        )
    else:
        if data.warnings:
            with st.expander(f"Data fetch warnings ({len(data.warnings)})", expanded=False):
                for w in data.warnings:
                    st.write(f"- {w}")

        st.subheader("Current financials (auto-fetched — edit if needed)")
        col1, col2, col3 = st.columns(3)
        with col1:
            price = st.number_input("Current price (Rs per share)", value=float(data.price or 0.0), step=1.0)
            st.caption(f"≈ {fmt_inr(price)}")
            shares_cr = st.number_input(
                "Shares outstanding (Cr)", value=float(to_cr(data.shares_outstanding) or 0.0),
                step=0.01, format="%.2f",
            )
            st.caption(f"≈ {fmt_cr(shares_cr, 2)} shares")
        with col2:
            total_debt_cr = st.number_input(
                "Total debt — gross (Rs Cr)", value=float(to_cr(data.total_debt) or 0.0), step=1.0,
                help="Used for D in the WACC builder (FCFF tab) — gross debt, not net of cash.",
            )
            cash_cr = st.number_input(
                "Cash & equivalents (Rs Cr)", value=float(to_cr(data.cash) or 0.0), step=1.0,
            )
        with col3:
            shares = from_cr(shares_cr)
            total_debt = from_cr(total_debt_cr)
            cash = from_cr(cash_cr)
            net_debt = total_debt - cash
            market_cap = price * shares if price and shares else None
            market_cap_cr = to_cr(market_cap)
            net_debt_cr = to_cr(net_debt)
            ev_cr = (market_cap_cr + net_debt_cr) if market_cap_cr is not None else None
            st.metric("Market cap", fmt_cr(market_cap_cr), help=GLOSSARY["target_mcap"])
            st.metric("Enterprise value (Mkt Cap + Net Debt)", fmt_cr(ev_cr), help=GLOSSARY["target_ev"])
            st.caption(f"Net debt = Total debt − Cash = {fmt_cr(net_debt_cr, 1)}")

        st.divider()

        TERMINAL_GROWTH_DEFAULT = 4.0
        methodologies = [
            {
                "key": "ni", "label": "Net Income", "row_label": "Net Income (Rs Cr)",
                "detail": data.historical_net_income, "current": data.current_net_income,
                "target_basis": "market_cap",
                "caution": (
                    "Net income is the most reliably-scraped figure of the three, but it includes "
                    "one-off/exceptional items that aren't stripped out here (asset sales, write-offs, "
                    "tax credits, etc.). Sanity-check the current figure against the company's own "
                    "reported normalized/adjusted profit before relying on it."
                ),
            },
            {
                "key": "fcff", "label": "FCFF", "row_label": "FCFF (Rs Cr)",
                "detail": data.historical_fcff, "current": data.current_fcff,
                "target_basis": "ev",
                "caution": (
                    "FCFF is built from CFO, interest expense and CapEx as separately reported by "
                    "Yahoo Finance — these line items are frequently mismapped or missing for Indian "
                    "tickers, so treat the auto-built figure as a starting point to verify, not a "
                    "ground-truth number. Override any year that looks wrong."
                ),
            },
            {
                "key": "fcfe", "label": "FCFE", "row_label": "FCFE (Rs Cr)",
                "detail": data.historical_fcfe, "current": data.current_fcfe,
                "target_basis": "market_cap",
                "caution": (
                    "FCFE shares FCFF's CFO/CapEx data-quality caveats (see the FCFF tab) but adds "
                    "net borrowing instead of an interest add-back — check that figure too if a year "
                    "looks off, and override manually where needed."
                ),
            },
        ]

        tabs = st.tabs([m["label"] for m in methodologies])

        for tab, cfg in zip(tabs, methodologies):
            with tab:
                key = cfg["key"]
                st.caption(cfg["caution"])

                st.markdown(f"**{cfg['label']} history (auto-built — edit any year that looks wrong)**")
                edited_series, last_period = render_transposed_history_editor(
                    cfg["detail"], cfg["row_label"], editor_key=f"{key}_history_editor",
                )

                auto_current = cfg["current"] or 0.0
                current_cr = st.number_input(
                    f"Current {cfg['label']} used for the DCF (Rs Cr)",
                    value=round(to_cr(auto_current) or 0.0, 1), step=1.0,
                    key=f"{key}_current_input",
                    help="Defaults to the latest column of the table above — override here if needed.",
                )
                current_flow = from_cr(current_cr)
                st.caption(f"≈ {fmt_cr(current_cr, 1)}")

                st.markdown("**Discount rate**")
                if key == "fcff":
                    w1, w2 = st.columns(2)
                    with w1:
                        ke = ke_input_with_bridge("fcff")
                        kd_default = round((data.estimated_cost_of_debt or 0.08) * 100, 2)
                        kd_pct = st.number_input(
                            "Cost of Debt — Kd (%)", value=kd_default, step=0.1, key="fcff_kd_pct",
                            help=GLOSSARY["kd"],
                        )
                        if data.estimated_cost_of_debt is None:
                            st.caption("Couldn't estimate Kd from fetched data — enter your own from research.")
                        else:
                            st.caption(f"Estimated from financials: {data.estimated_cost_of_debt:.2%} — verify before relying on it.")
                    with w2:
                        tax_default = round((data.latest_effective_tax_rate or 0.25) * 100, 2)
                        tax_pct = st.number_input(
                            "Tax rate for WACC (%)", value=tax_default, step=0.5, key="fcff_tax_pct",
                            help="Defaults to the latest statement's effective tax rate.",
                        )
                        st.metric("Market cap (E)", fmt_cr(market_cap_cr))
                        st.metric("Total debt (D)", fmt_cr(total_debt_cr))
                    try:
                        discount_rate = compute_wacc(
                            ke=ke, kd=kd_pct / 100, tax_rate=tax_pct / 100,
                            market_value_equity=market_cap or 0.0, market_value_debt=total_debt or 0.0,
                        )
                        st.metric("WACC (computed)", f"{discount_rate:.2%}", help=GLOSSARY["wacc"])
                        st.caption(
                            f"= {market_cap_cr / (market_cap_cr + total_debt_cr):.0%} × {ke:.2%} (Ke)  +  "
                            f"{total_debt_cr / (market_cap_cr + total_debt_cr):.0%} × {kd_pct/100:.2%} (Kd) × "
                            f"(1 − {tax_pct/100:.0%} tax)"
                            if (market_cap_cr or 0) + (total_debt_cr or 0) > 0 else ""
                        )
                    except ValueError as e:
                        st.error(str(e))
                        discount_rate = None
                    target_value = (market_cap + net_debt) if market_cap is not None else None
                    target_label = "Enterprise Value (Market Cap + Net Debt)"
                    target_value_cr = ev_cr
                else:
                    discount_rate = ke_input_with_bridge(key)
                    target_value = market_cap
                    target_label = "Market Cap"
                    target_value_cr = market_cap_cr

                if key == "ni":
                    terminal_mode = st.radio(
                        "Terminal value method", ["Perpetuity Growth", "Exit P/E Multiple"],
                        horizontal=True, key=f"{key}_terminal_mode",
                        help="Exit multiple applies a P/E-style multiple to terminal-year Net Income "
                             "instead of assuming a perpetual growth rate — a relative-valuation cross-check "
                             "rather than a replacement for the growth method.",
                    )
                else:
                    terminal_mode = "Perpetuity Growth"

                c1, c2 = st.columns(2)
                with c1:
                    if terminal_mode == "Exit P/E Multiple":
                        auto_pe = (market_cap / current_flow) if (market_cap and current_flow and current_flow > 0) else None
                        pe_default = round(auto_pe, 1) if auto_pe and auto_pe > 0 else 15.0
                        exit_multiple = st.number_input(
                            "Exit P/E multiple (x)", value=pe_default, step=0.5, key=f"{key}_exit_multiple",
                            help="Applied to projected terminal-year Net Income: TV = Net Income at year N "
                                 "× this multiple. Defaults to the stock's own current trailing P/E — "
                                 "override with a peer average or your own normalized view.",
                        )
                        if auto_pe:
                            st.caption(f"Current trailing P/E ≈ {auto_pe:.1f}x")
                        terminal_growth = None
                    else:
                        terminal_growth = st.number_input(
                            "Terminal growth (%)", value=TERMINAL_GROWTH_DEFAULT, step=0.1, key=f"{key}_tg",
                            help=GLOSSARY["terminal_growth"],
                        ) / 100
                        exit_multiple = None
                with c2:
                    period_choice = st.selectbox(
                        "Projection period (years)", [3, 5, 10, "Custom"], index=1, key=f"{key}_period_choice",
                    )
                    if period_choice == "Custom":
                        projection_years = st.number_input(
                            "Custom projection years", min_value=1, max_value=30, value=7, step=1,
                            key=f"{key}_custom_years",
                        )
                    else:
                        projection_years = period_choice

                calculate = st.button("Calculate", type="primary", key=f"{key}_calculate")

                if calculate:
                    if discount_rate is None:
                        st.error("Fix the discount-rate inputs above before calculating.")
                    elif not price or price <= 0:
                        st.error("Current price must be greater than zero (auto-fetch may have failed above).")
                    elif not shares or shares <= 0:
                        st.error("Shares outstanding must be greater than zero (auto-fetch may have failed above).")
                    elif target_value is None or target_value <= 0:
                        st.error(f"{target_label} must be greater than zero to solve against.")
                    elif terminal_mode == "Perpetuity Growth" and discount_rate <= terminal_growth:
                        st.error(f"Discount rate ({discount_rate:.1%}) must be greater than terminal growth ({terminal_growth:.1%}).")
                    elif terminal_mode == "Exit P/E Multiple" and (not exit_multiple or exit_multiple <= 0):
                        st.error("Exit multiple must be greater than zero.")
                    elif current_flow <= 0:
                        st.error(
                            f"Reverse DCF CAGR cannot be calculated because current {cfg['label']} is zero or "
                            "negative. Enter a normalized positive starting figure above if you want to run "
                            "a CAGR-based valuation."
                        )
                    else:
                        try:
                            if terminal_mode == "Exit P/E Multiple":
                                implied_cagr = solve_implied_cagr_exit_multiple(
                                    current_flow, target_value, discount_rate, exit_multiple, projection_years
                                )
                                value_check, pv_terminal, terminal_value = value_at_growth_exit_multiple(
                                    current_flow, implied_cagr, discount_rate, exit_multiple, projection_years
                                )
                            else:
                                implied_cagr = solve_implied_cagr(
                                    current_flow, target_value, discount_rate, terminal_growth, projection_years
                                )
                                value_check, pv_terminal, terminal_value = value_at_growth(
                                    current_flow, implied_cagr, discount_rate, terminal_growth, projection_years
                                )
                            pv_explicit = value_check - pv_terminal
                            trajectory = flow_trajectory(current_flow, implied_cagr, projection_years)

                            st.subheader("Market-implied expectations")
                            m1, m2 = st.columns(2)
                            m1.metric("Required CAGR", f"{implied_cagr:.1%}", help=GLOSSARY["implied_cagr"])

                            cagr_3y, reason_3y, msg_3y = trailing_cagr_with_reason(edited_series, years=3)
                            with m2:
                                if reason_3y == "ok":
                                    st.metric("Historical 3-Yr CAGR", f"{cagr_3y:.1%}", help=GLOSSARY["historical_cagr"])
                                    st.caption(f"Gap vs required: {implied_cagr - cagr_3y:+.1%}")
                                else:
                                    st.metric("Historical 3-Yr CAGR", "N/A", help=GLOSSARY["historical_cagr"])
                                    st.caption(msg_3y)

                            st.subheader(f"{cfg['label']} trajectory ({projection_years}-year projection, Rs Cr)")
                            render_flow_chart(
                                edited_series, last_period, trajectory,
                                terminal_growth if terminal_mode == "Perpetuity Growth" else 0.0,
                                projection_years, title=cfg["label"],
                                show_terminal_extension=(terminal_mode == "Perpetuity Growth"),
                            )

                            st.subheader(f"{target_label} breakdown")
                            e1, e2, e3 = st.columns(3)
                            e1.metric("PV of explicit forecast period", fmt_cr(to_cr(pv_explicit)))
                            e2.metric("PV of terminal value", fmt_cr(to_cr(pv_terminal)))
                            e3.metric(f"Total {('EV' if cfg['target_basis']=='ev' else 'Mkt Cap')} (check)", fmt_cr(to_cr(value_check)))
                            st.caption(
                                f"Total (check) = PV of explicit forecast + PV of terminal value, and should match "
                                f"the target {target_label} below — this is the solver's own consistency check, "
                                "not a separate estimate."
                            )

                            st.subheader("Terminal value diagnostics")
                            d1, d2 = st.columns(2)
                            d1.metric("Terminal value (undiscounted)", fmt_cr(to_cr(terminal_value)))
                            d2.metric("Terminal value share", f"{pv_terminal / value_check:.1%}", help=GLOSSARY["terminal_value_share"])
                            st.caption(
                                "A high terminal-value share isn't inherently a red flag - it's normal for "
                                "growth names with a long projection window, high rate-to-growth spread, or "
                                "both. Read it alongside the CAGR gap above, not on its own."
                            )

                            st.subheader("Sensitivity: required CAGR")
                            st.caption(GLOSSARY["sensitivity_grid"])
                            rate_label = "WACC" if key == "fcff" else "Ke"
                            rate_step = 0.01
                            rate_range = [round(discount_rate + i * rate_step, 4) for i in range(-2, 3)]
                            rate_range = [r for r in rate_range if r > 0]
                            if terminal_mode == "Exit P/E Multiple":
                                m_step = 1.0
                                multiple_range = [round(exit_multiple + i * m_step, 2) for i in range(-2, 3)]
                                multiple_range = [m for m in multiple_range if m > 0]
                                grid = sensitivity_grid_exit_multiple(
                                    current_flow, target_value, rate_range, multiple_range, projection_years
                                )
                                x_labels = [f"{m:.1f}x" for m in multiple_range]
                                x_title = "Exit P/E multiple"
                            else:
                                tg_step = 0.01
                                tg_range = [round(terminal_growth + i * tg_step, 4) for i in range(-2, 3)]
                                tg_range = [g for g in tg_range if g >= 0]
                                grid = sensitivity_grid(current_flow, target_value, rate_range, tg_range, projection_years)
                                x_labels = [f"{g:.1%}" for g in tg_range]
                                x_title = "Terminal growth"
                            z = [[(v * 100 if v is not None else None) for v in row] for row in grid]
                            text = [[f"{v:.1%}" if v is not None else "—" for v in row] for row in grid]
                            fig_sens = go.Figure(data=go.Heatmap(
                                z=z, x=x_labels, y=[f"{r:.1%}" for r in rate_range],
                                text=text, texttemplate="%{text}",
                                colorscale=[[0, T["surface1"]], [1, T["accent"]]],
                                showscale=False, xgap=4, ygap=4,
                            ))
                            fig_sens.update_layout(
                                template=PLOT_TEMPLATE, paper_bgcolor=T["bg"], plot_bgcolor=T["bg"],
                                xaxis_title=x_title, yaxis_title=rate_label,
                                title=f"Required CAGR across discount-rate x {x_title.lower()} assumptions",
                                dragmode=False, height=280, margin=dict(t=50, b=10),
                            )
                            st.plotly_chart(fig_sens, use_container_width=True, config=PLOTLY_CONFIG)
                            st.caption("Blank cells (—) mean the assumptions in that cell make no CAGR solvable within the search range.")

                            with st.expander("Assumptions used in this run"):
                                assumptions = {
                                    f"Current {cfg['label']}": fmt_cr(to_cr(current_flow), 1),
                                    "Discount rate": f"{discount_rate:.2%}",
                                    "Terminal method": terminal_mode,
                                    "Terminal growth" if terminal_mode == "Perpetuity Growth" else "Exit multiple":
                                        f"{terminal_growth:.1%}" if terminal_mode == "Perpetuity Growth" else f"{exit_multiple:.1f}x",
                                    "Projection years": projection_years,
                                    "Market cap": fmt_cr(market_cap_cr),
                                    "Net debt": fmt_cr(net_debt_cr, 1),
                                    f"Target {target_label}": fmt_cr(target_value_cr),
                                }
                                st.write(assumptions)

                            st.subheader("Export this result")
                            summary_rows = [
                                {"Item": "Ticker", "Value": ticker},
                                {"Item": "Methodology", "Value": cfg["label"]},
                                {"Item": "Current price (Rs)", "Value": round(price, 2)},
                                {"Item": f"Current {cfg['label']} (Rs Cr)", "Value": round(current_cr, 1)},
                                {"Item": "Discount rate", "Value": f"{discount_rate:.2%}"},
                                {"Item": "Terminal method", "Value": terminal_mode},
                                {"Item": "Terminal growth" if terminal_mode == "Perpetuity Growth" else "Exit multiple",
                                 "Value": f"{terminal_growth:.2%}" if terminal_mode == "Perpetuity Growth" else f"{exit_multiple:.1f}x"},
                                {"Item": "Projection years", "Value": projection_years},
                                {"Item": f"Target {target_label} (Rs Cr)", "Value": round(target_value_cr, 1) if target_value_cr else None},
                                {"Item": "Required CAGR", "Value": f"{implied_cagr:.2%}"},
                                {"Item": "Historical 3-Yr CAGR", "Value": f"{cagr_3y:.2%}" if reason_3y == "ok" else "N/A"},
                                {"Item": "PV of explicit forecast (Rs Cr)", "Value": round(to_cr(pv_explicit), 1)},
                                {"Item": "PV of terminal value (Rs Cr)", "Value": round(to_cr(pv_terminal), 1)},
                                {"Item": "Terminal value share", "Value": f"{pv_terminal / value_check:.1%}"},
                            ]
                            summary_df = pd.DataFrame(summary_rows)
                            st.download_button(
                                "Download result summary (CSV)", summary_df.to_csv(index=False),
                                file_name=f"{ticker}_{key}_reverse_dcf.csv", mime="text/csv",
                                key=f"{key}_download",
                            )
                        except ValueError as e:
                            st.error(str(e))
else:
    st.info("Search for or enter a ticker above to begin.")

st.divider()
st.subheader("Data & Methodology")
with st.expander("How this reverse DCF works, and the caveats behind each methodology"):
    st.markdown("""
**Core idea:** instead of assuming a growth rate to estimate a price, this tool takes
today's actual market price and solves backwards for the constant growth rate that
would justify it (Gordon Growth terminal value, Brent's-method root finder) — then
compares that required rate to the company's own trailing growth.

**Three methodologies, one engine underneath:**

| Tab | Flow discounted | Discount rate | Target value |
|---|---|---|---|
| Net Income | Net income (after interest) | Ke — Cost of Equity | Market Cap |
| FCFF | Unlevered free cash flow (CFO + after-tax interest − CapEx) | WACC | Enterprise Value (Market Cap + Net Debt) |
| FCFE | Levered free cash flow (CFO − CapEx + Net Borrowing) | Ke — Cost of Equity | Market Cap |

Net Income and FCFE are equity-level flows (already after interest), so they're
discounted at Ke against Market Cap — never at WACC against Enterprise Value, which
would double-count the effect of leverage.

**Data reliability, tab by tab:**
- **Net Income** is the most reliably-scraped figure of the three (it's the single
  headline number on every statement), but includes one-off/exceptional items that
  aren't stripped out automatically.
- **FCFF** is built explicitly from CFO, after-tax interest, and CapEx rather than
  Yahoo's own CFO-minus-CapEx shortcut — but these underlying line items are
  frequently mismapped or missing for Indian tickers on the free feed. Treat the
  auto-built figure as a starting point to verify, not ground truth.
- **FCFE** shares FCFF's CFO/CapEx caveats, plus its own dependency on a correctly
  identified net-borrowing figure.

In all three tabs, every historical year is editable — override any figure that
looks wrong against the company's own filings or a source like Screener.

**History window:** capped to the most recent 4 fiscal years (yfinance's free annual
statements rarely go back further), giving a 3-year trailing CAGR as the longest
reliable comparison point.

**Cost of Debt (FCFF tab):** pre-filled as Interest Expense ÷ Total Debt from the
latest statement — a backward-looking accounting average, not a market rate. yfinance
has no field for a company's actual current borrowing cost, so this needs your own
verification (recent bond yields, loan terms) before you rely on it.
    """)

st.caption("[GitHub](https://github.com/deepeshjoshii) · Source and other tools for this project.")
render_disclaimer(T)
