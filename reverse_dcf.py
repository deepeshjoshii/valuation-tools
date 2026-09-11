"""
Reverse DCF Calculator - Core Logic (V2)
Three methodologies, one shared solver: Net Income/Ke, FCFF/WACC, FCFE/Ke.

Why three methodologies:
- FCFF (built from CFO + after-tax interest - CapEx) is the "correct" DCF
  input in theory, but in practice Yahoo/yfinance's line-item mapping for
  Indian tickers is frequently wrong or missing (misclassified CapEx,
  missing interest expense, etc.) - the FCFF figure this module builds
  should be treated as a starting point to sanity-check, not a ground
  truth number.
- Net Income is a much more reliably-scraped figure (it's the single
  headline number on every statement), at the cost of being noisier
  period-to-period (one-off/exceptional items aren't stripped out here).
- FCFE sits in between: built from the same CFO figure as FCFF (drop the
  interest add-back, add net borrowing instead), so it inherits FCFF's
  data-quality caveats but not its interest-expense dependency.

Design principles (carried over from V1):
- Every auto-fetched number is surfaced raw, not hidden behind a black box.
- A single missing line item should not take down the whole fetch - each
  field is wrapped and fetch failures are collected as warnings.
- yfinance's free annual statements typically span ~4 fiscal years - every
  historical series here is explicitly capped to the most recent 4 periods
  (3 CAGR periods) rather than silently showing however many columns
  yfinance happens to return, so a "3-Yr CAGR" label is never quietly wrong.

Flow / discount-rate / target-value pairing (get this wrong and the implied
growth rate is systematically biased by the company's leverage):
    Net Income  ->  Ke (cost of equity)  ->  Market Cap
    FCFF        ->  WACC                 ->  Enterprise Value (Market Cap + Net Debt)
    FCFE        ->  Ke (cost of equity)  ->  Market Cap
Net Income and FCFE are equity-level flows (already after interest) and so
are discounted at Ke against Market Cap, never at WACC against EV - mixing
those pairs double- or under-counts the effect of leverage.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from scipy.optimize import brentq

try:
    import yfinance as yf
except ImportError:  # allows the pure-math functions to be imported/tested
    yf = None          # without yfinance installed

HISTORY_YEARS_CAP = 4  # yfinance's free annual statements typically span ~4 FY -> 3 CAGR periods


# ---------------------------------------------------------------------------
# Core DCF math (pure functions - no network calls, fully unit-testable)
# Generic across all three methodologies: the caller supplies whichever flow,
# discount rate, and target value belong together (see pairing table above).
# ---------------------------------------------------------------------------

def value_at_growth(
    current_flow: float,
    growth_rate: float,
    discount_rate: float,
    terminal_growth: float,
    projection_years: int,
):
    """
    Compute the present value of a flow (FCFF, FCFE, or Net Income) given a
    constant growth rate over the projection period, followed by a Gordon
    Growth terminal value, discounted at `discount_rate` (WACC for FCFF,
    Ke for FCFE/Net Income - this function is agnostic to which).

        V = sum_{t=1..n} Flow_0*(1+g)^t / (1+r)^t  +  TV / (1+r)^n
        TV = Flow_n * (1 + terminal_growth) / (r - terminal_growth)

    Returns (value, pv_of_terminal_value, undiscounted_terminal_value).
    """
    if discount_rate <= terminal_growth:
        raise ValueError(
            f"Discount rate ({discount_rate:.2%}) must be greater than terminal growth "
            f"({terminal_growth:.2%}) or the terminal value is undefined/infinite."
        )

    pv_explicit = 0.0
    for t in range(1, projection_years + 1):
        flow_t = current_flow * (1 + growth_rate) ** t
        pv_explicit += flow_t / (1 + discount_rate) ** t

    flow_terminal_year = current_flow * (1 + growth_rate) ** projection_years
    terminal_value = flow_terminal_year * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / (1 + discount_rate) ** projection_years

    return pv_explicit + pv_terminal, pv_terminal, terminal_value


def solve_implied_cagr(
    current_flow: float,
    target_value: float,
    discount_rate: float,
    terminal_growth: float,
    projection_years: int,
    search_bounds: tuple = (-0.50, 3.00),
) -> float:
    """
    Solve for the constant flow growth rate (CAGR) over `projection_years`
    that makes computed present value equal `target_value`.

    Uses Brent's method - robust bracketed root finding, no derivative needed.
    """
    if current_flow <= 0:
        raise ValueError(
            "Current flow is zero or negative - a CAGR-based reverse DCF is not "
            "meaningful from a negative or zero base. Consider using a "
            "normalized starting figure instead."
        )

    def f(g):
        v, _, _ = value_at_growth(
            current_flow, g, discount_rate, terminal_growth, projection_years
        )
        return v - target_value

    lo, hi = search_bounds
    f_lo, f_hi = f(lo), f(hi)

    if f_lo * f_hi > 0:
        raise ValueError(
            "No solution found in the search range "
            f"({lo:.0%} to {hi:.0%} CAGR). The target value may be unreachable "
            "with these discount-rate/terminal-growth assumptions - try widening the "
            "search range or revisiting the inputs."
        )

    return brentq(f, lo, hi, xtol=1e-6)


def value_at_growth_exit_multiple(
    current_flow: float,
    growth_rate: float,
    discount_rate: float,
    exit_multiple: float,
    projection_years: int,
):
    """
    Present value using an EXIT MULTIPLE terminal value instead of Gordon
    Growth - i.e. relative valuation instead of a perpetuity assumption:

        TV = Flow_n * exit_multiple   (e.g. a terminal P/E x terminal Net Income)

    This sidesteps picking a perpetual growth rate, but doesn't avoid making
    an assumption - it just relocates it into whatever multiple is chosen
    (the stock's own current multiple, a peer average, etc.), which is
    itself a growth-and-quality assumption in disguise. Most useful for
    Net Income, where a P/E-style multiple is an intuitive, market-observed
    reference point; use alongside (not instead of) the perpetuity-growth
    method as a cross-check.

    Returns (value, pv_of_terminal_value, undiscounted_terminal_value).
    """
    if discount_rate <= 0:
        raise ValueError("Discount rate must be positive.")

    pv_explicit = 0.0
    for t in range(1, projection_years + 1):
        flow_t = current_flow * (1 + growth_rate) ** t
        pv_explicit += flow_t / (1 + discount_rate) ** t

    flow_terminal_year = current_flow * (1 + growth_rate) ** projection_years
    terminal_value = flow_terminal_year * exit_multiple
    pv_terminal = terminal_value / (1 + discount_rate) ** projection_years

    return pv_explicit + pv_terminal, pv_terminal, terminal_value


def solve_implied_cagr_exit_multiple(
    current_flow: float,
    target_value: float,
    discount_rate: float,
    exit_multiple: float,
    projection_years: int,
    search_bounds: tuple = (-0.50, 3.00),
) -> float:
    """Exit-multiple counterpart to solve_implied_cagr() - same root-finding
    approach, different terminal-value construction."""
    if current_flow <= 0:
        raise ValueError(
            "Current flow is zero or negative - a CAGR-based reverse DCF is not "
            "meaningful from a negative or zero base. Consider using a "
            "normalized starting figure instead."
        )

    def f(g):
        v, _, _ = value_at_growth_exit_multiple(
            current_flow, g, discount_rate, exit_multiple, projection_years
        )
        return v - target_value

    lo, hi = search_bounds
    f_lo, f_hi = f(lo), f(hi)

    if f_lo * f_hi > 0:
        raise ValueError(
            "No solution found in the search range "
            f"({lo:.0%} to {hi:.0%} CAGR). The target value may be unreachable "
            "with this discount-rate/exit-multiple combination - try widening the "
            "search range or revisiting the inputs."
        )

    return brentq(f, lo, hi, xtol=1e-6)


def sensitivity_grid_exit_multiple(
    current_flow: float,
    target_value: float,
    discount_rates: list,
    exit_multiples: list,
    projection_years: int,
) -> list:
    """Sensitivity_grid() counterpart for the exit-multiple terminal method -
    rows are discount rates, columns are exit multiples."""
    grid = []
    for r in discount_rates:
        row = []
        for m in exit_multiples:
            if r <= 0:
                row.append(None)
                continue
            try:
                row.append(solve_implied_cagr_exit_multiple(current_flow, target_value, r, m, projection_years))
            except ValueError:
                row.append(None)
        grid.append(row)
    return grid


def flow_trajectory(current_flow: float, growth_rate: float, projection_years: int) -> list:
    """Year-by-year flow path (year 0 = current) implied by a given growth rate."""
    return [
        {"year": t, "flow": current_flow * (1 + growth_rate) ** t}
        for t in range(0, projection_years + 1)
    ]


def historical_cagr(flow_series: list) -> Optional[float]:
    """
    Geometric CAGR from the oldest to the newest value in a chronologically
    ordered list of historical flow figures (oldest first).
    Returns None if fewer than 2 usable points, or if the starting value
    isn't positive (CAGR is undefined/meaningless from a non-positive base).
    """
    clean = [v for v in flow_series if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(clean) < 2:
        return None
    start, end = clean[0], clean[-1]
    n = len(clean) - 1
    if start <= 0 or n <= 0:
        return None
    return (end / start) ** (1 / n) - 1


def historical_cagr_with_reason(flow_series: list):
    """
    Same underlying result as historical_cagr() - this wrapper additionally
    classifies *why* the result is None, so the UI can show something more
    useful than a bare "N/A":

        "ok"                -> a CAGR was computed
        "missing_values"     -> some periods were NaN/None and got dropped,
                                 leaving fewer than 2 usable points
        "insufficient_data"  -> fewer than 2 periods were provided at all
        "non_positive_start" -> enough clean data, but the earliest usable
                                 flow is <= 0, so CAGR isn't meaningful

    Returns (cagr_or_None, reason_code, human_readable_message_or_None).
    """
    raw_len = len(flow_series)
    clean = [v for v in flow_series if v is not None and not (isinstance(v, float) and math.isnan(v))]

    if len(clean) < 2:
        if raw_len > len(clean):
            return None, "missing_values", (
                f"Only {len(clean)} of {raw_len} historical period(s) had usable data - "
                "not enough to compute a CAGR."
            )
        return None, "insufficient_data", (
            f"Only {len(clean)} historical period(s) available - at least 2 are needed for a CAGR."
        )

    if clean[0] <= 0:
        return None, "non_positive_start", (
            "The earliest usable figure in this window is zero or negative, so a "
            "conventional CAGR from that base isn't meaningful."
        )

    return historical_cagr(flow_series), "ok", None


def trailing_cagr_with_reason(flow_series: list, years: int):
    """
    CAGR (with reason code) computed over a trailing window of exactly
    `years` periods - i.e. using the last (years + 1) chronologically
    ordered entries of flow_series (start and end points for `years` periods
    of compounding).

    Unlike historical_cagr_with_reason(), which uses however much history is
    available, this deliberately requires the full window: if fewer than
    (years + 1) entries exist, it reports "insufficient_data" naming the
    shortfall, rather than silently computing a shorter-window CAGR and
    mislabeling it as N years.
    """
    window = flow_series[-(years + 1):] if flow_series else []
    if len(window) < years + 1:
        return None, "insufficient_data", (
            f"Only {len(window)} period(s) available - {years + 1} are needed "
            f"for a {years}-year CAGR."
        )
    return historical_cagr_with_reason(window)


# ---------------------------------------------------------------------------
# FCFF / FCFE construction from raw statement line items
# ---------------------------------------------------------------------------

def compute_fcff(cfo: float, interest_expense: float, tax_rate: float, capex: float) -> float:
    """
    FCFF (unlevered), CFO-based route:
        FCFF = CFO + Interest Expense * (1 - tax rate) - CapEx

    NOT the same as yfinance's own "Free Cash Flow" line (CFO - CapEx) -
    that hybrid shortcut omits the interest add-back and isn't a rigorous
    unlevered figure. We compute it explicitly for internal consistency
    with WACC discounting.
    """
    interest_expense = abs(interest_expense) if interest_expense is not None else 0.0
    return cfo + interest_expense * (1 - tax_rate) - abs(capex)


def compute_fcfe(cfo: float, capex: float, net_borrowing: float) -> float:
    """
    FCFE (levered):
        FCFE = CFO - CapEx + Net Borrowing
    An equity-level flow - discount at Ke against Market Cap, never at WACC
    against EV (it's already net of the effect of debt financing).
    """
    return cfo - abs(capex) + net_borrowing


def sensitivity_grid(
    current_flow: float,
    target_value: float,
    discount_rates: list,
    terminal_growths: list,
    projection_years: int,
) -> list:
    """
    Grid of implied CAGR across combinations of discount rate x terminal
    growth - same idea as the Beta Calculator's benchmark x lookback x
    frequency sensitivity table, applied to the two assumptions a reverse
    DCF is most sensitive to.

    Returns a list of rows (one per discount_rate, in the order given),
    each row a list of implied-CAGR-or-None (one per terminal_growth) -
    None where discount_rate <= terminal_growth (undefined) or no root
    exists in the default search bounds.
    """
    grid = []
    for r in discount_rates:
        row = []
        for g in terminal_growths:
            if r <= g:
                row.append(None)
                continue
            try:
                row.append(solve_implied_cagr(current_flow, target_value, r, g, projection_years))
            except ValueError:
                row.append(None)
        grid.append(row)
    return grid


# ---------------------------------------------------------------------------
# WACC construction
# ---------------------------------------------------------------------------

def estimate_cost_of_debt(interest_expense: Optional[float], total_debt: Optional[float]) -> Optional[float]:
    """
    Effective cost of debt = Interest Expense / Total Debt, from the same
    statement lines the FCFF fetch already pulls.

    This is a backward-looking ACCOUNTING AVERAGE, not a market cost of
    debt - it can be badly wrong if the company's debt mix or borrowing
    rates have shifted recently, if there's significant off-balance-sheet
    or short-term debt, or if the "interest expense" line includes non-debt
    items. Treat this as a starting estimate to verify against the
    company's actual current borrowing cost (recent bond yields, loan
    terms), not as an authoritative market rate.
    """
    if interest_expense is None or total_debt is None or total_debt <= 0:
        return None
    return abs(interest_expense) / total_debt


def compute_wacc(
    ke: float,
    kd: float,
    tax_rate: float,
    market_value_equity: float,
    market_value_debt: float,
) -> float:
    """
    WACC = E/V * Ke  +  D/V * Kd * (1 - tax_rate)
    where V = E + D (market value of equity + market value of debt).

    Market cap is used for E; total debt (book value, since market value of
    debt is rarely observable for Indian corporate debt) is used for D.
    """
    total = market_value_equity + market_value_debt
    if total <= 0:
        raise ValueError("Combined equity + debt value must be positive to compute WACC.")
    e_weight = market_value_equity / total
    d_weight = market_value_debt / total
    return e_weight * ke + d_weight * kd * (1 - tax_rate)


# ---------------------------------------------------------------------------
# Data fetch (network-dependent - cannot be exercised in this sandbox;
# verify on your machine, same as the Beta Calculator's live-data testing)
# ---------------------------------------------------------------------------

@dataclass
class CompanyFinancials:
    ticker: str
    price: Optional[float] = None
    shares_outstanding: Optional[float] = None
    market_cap: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    net_debt: Optional[float] = None
    latest_interest_expense: Optional[float] = None
    latest_effective_tax_rate: Optional[float] = None
    estimated_cost_of_debt: Optional[float] = None
    # Each of these: oldest -> newest, capped to HISTORY_YEARS_CAP periods,
    # list of {"period", "value", "skip_reason"} - "value" is in raw rupees.
    historical_fcff: list = field(default_factory=list)
    historical_net_income: list = field(default_factory=list)
    historical_fcfe: list = field(default_factory=list)
    current_fcff: Optional[float] = None
    current_net_income: Optional[float] = None
    current_fcfe: Optional[float] = None
    warnings: list = field(default_factory=list)


def _first_available_row(df, row_names):
    if df is None or df.empty:
        return None
    for name in row_names:
        if name in df.index:
            return df.loc[name]
    return None


def _fy_label(col) -> str:
    """
    Convert a yfinance annual-statement column (a period-end Timestamp) to an
    Indian-fiscal-year label, e.g. 2026-03-31 -> 'FY2026' (FY is named for the
    calendar year it ends in, matching standard Indian convention/Screener).
    Falls back to str(col) if it isn't a recognizable date.
    """
    year = getattr(col, "year", None)
    return f"FY{year}" if year else str(col)


def _clean_num(v):
    """pandas cells return NaN (not None) for missing data - normalize both to None."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _series_from_detail(detail: list) -> list:
    """oldest->newest list of raw values (None kept, for downstream CAGR filtering)."""
    return [r["value"] for r in detail]


def fetch_company_financials(ticker: str) -> CompanyFinancials:
    """
    Pull the raw inputs needed for all three Reverse DCF methodologies from
    yfinance. Each field is fetched independently and wrapped so one
    missing/renamed line item (a real, recurring issue with Indian tickers)
    doesn't take down the whole fetch.

    Builds three parallel historical series (FCFF, Net Income, FCFE), each
    oldest -> newest and capped to the most recent HISTORY_YEARS_CAP (4)
    fiscal years, since yfinance's free annual statements typically don't
    go back further than that - showing more would just be padding with
    columns that don't exist.
    """
    if yf is None:
        raise RuntimeError("yfinance is not installed in this environment.")

    data = CompanyFinancials(ticker=ticker)
    stock = yf.Ticker(ticker)

    # --- price, shares, market cap ---
    try:
        info = stock.info
        data.price = info.get("currentPrice") or info.get("regularMarketPrice")
        data.shares_outstanding = info.get("sharesOutstanding")
        if data.price and data.shares_outstanding:
            data.market_cap = data.price * data.shares_outstanding
        else:
            data.market_cap = info.get("marketCap")
    except Exception as e:
        data.warnings.append(f"Could not fetch price/shares/market cap: {e}")

    # --- balance sheet: debt & cash ---
    try:
        bs = stock.balance_sheet
        total_debt = None
        cash = None
        debt_row = _first_available_row(bs, ["Total Debt"])
        cash_row = _first_available_row(bs, ["Cash And Cash Equivalents", "Cash"])
        if debt_row is not None:
            total_debt = _clean_num(debt_row.iloc[0])
        if cash_row is not None:
            cash = _clean_num(cash_row.iloc[0])
        data.total_debt = total_debt
        data.cash = cash
        if total_debt is not None and cash is not None:
            data.net_debt = total_debt - cash
    except Exception as e:
        data.warnings.append(f"Could not fetch balance sheet debt/cash: {e}")

    # --- cash flow & income statement: build all three flow histories together ---
    try:
        cf = stock.cashflow
        inc = stock.financials

        cfo_row = _first_available_row(cf, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        capex_row = _first_available_row(cf, ["Capital Expenditure", "Capital Expenditures"])
        interest_row = _first_available_row(inc, ["Interest Expense"])
        pretax_row = _first_available_row(inc, ["Pretax Income"])
        tax_row = _first_available_row(inc, ["Tax Provision"])
        net_income_row = _first_available_row(inc, ["Net Income Common Stockholders", "Net Income"])
        issuance_row = _first_available_row(cf, ["Issuance Of Debt", "Long Term Debt Issuance"])
        repayment_row = _first_available_row(cf, ["Repayment Of Debt", "Long Term Debt Payments"])
        net_borrow_row = _first_available_row(cf, ["Net Issuance Payments Of Debt"])

        # Most recent HISTORY_YEARS_CAP columns only - yfinance's free annual
        # statements rarely go back further, and showing more columns than
        # actually exist elsewhere is worse than just capping explicitly.
        cols = sorted(cf.columns)[-HISTORY_YEARS_CAP:]

        fcff_detail, ni_detail, fcfe_detail = [], [], []

        for col in cols:
            period = _fy_label(col)
            cfo_val = _clean_num(cfo_row.get(col)) if cfo_row is not None else None
            capex_val = _clean_num(capex_row.get(col)) if capex_row is not None else None
            interest_val = _clean_num(interest_row.get(col)) if interest_row is not None else None
            pretax_val = _clean_num(pretax_row.get(col)) if pretax_row is not None else None
            tax_val = _clean_num(tax_row.get(col)) if tax_row is not None else None
            ni_val = _clean_num(net_income_row.get(col)) if net_income_row is not None else None

            if pretax_val not in (None, 0) and tax_val is not None:
                tax_rate = tax_val / pretax_val
            else:
                tax_rate = 0.25
                data.warnings.append(
                    f"{period}: effective tax rate unavailable from statement data - "
                    "defaulted to 25%. Check manually."
                )

            # --- FCFF ---
            missing = []
            if cfo_val is None:
                missing.append("Operating Cash Flow")
            if capex_val is None:
                missing.append("Capital Expenditure")
            if missing:
                fcff_detail.append({
                    "period": period, "value": None,
                    "skip_reason": f"{' and '.join(missing)} unavailable for {period}.",
                })
                data.warnings.append(f"{period}: FCFF not computed - {' and '.join(missing)} unavailable.")
            else:
                if interest_val is None:
                    data.warnings.append(
                        f"{period}: Interest Expense unavailable - treated as 0 for FCFF. Check manually."
                    )
                fcff_val = compute_fcff(cfo_val, interest_val or 0.0, tax_rate, capex_val)
                fcff_detail.append({"period": period, "value": fcff_val, "skip_reason": None})

            # --- Net Income ---
            if ni_val is None:
                ni_detail.append({
                    "period": period, "value": None,
                    "skip_reason": f"Net income unavailable for {period}.",
                })
                data.warnings.append(f"{period}: Net income not available.")
            else:
                ni_detail.append({"period": period, "value": ni_val, "skip_reason": None})

            # --- FCFE (CFO - CapEx + Net Borrowing) ---
            if net_borrow_row is not None:
                net_borrow_val = _clean_num(net_borrow_row.get(col))
            else:
                iss_val = _clean_num(issuance_row.get(col)) if issuance_row is not None else None
                rep_val = _clean_num(repayment_row.get(col)) if repayment_row is not None else None
                if iss_val is not None or rep_val is not None:
                    net_borrow_val = (iss_val or 0.0) - abs(rep_val or 0.0)
                else:
                    net_borrow_val = None

            fcfe_missing = []
            if cfo_val is None:
                fcfe_missing.append("Operating Cash Flow")
            if capex_val is None:
                fcfe_missing.append("Capital Expenditure")
            if net_borrow_val is None:
                fcfe_missing.append("Net Borrowing")
            if fcfe_missing:
                fcfe_detail.append({
                    "period": period, "value": None,
                    "skip_reason": f"{' and '.join(fcfe_missing)} unavailable for {period}.",
                })
                data.warnings.append(f"{period}: FCFE not computed - {' and '.join(fcfe_missing)} unavailable.")
            else:
                fcfe_val = compute_fcfe(cfo_val, capex_val, net_borrow_val)
                fcfe_detail.append({"period": period, "value": fcfe_val, "skip_reason": None})

            # Latest-period-only fields (used for the WACC builder's cost-of-debt estimate)
            if col == cols[-1]:
                data.latest_interest_expense = interest_val
                data.latest_effective_tax_rate = tax_rate

        data.historical_fcff = fcff_detail
        data.historical_net_income = ni_detail
        data.historical_fcfe = fcfe_detail

        fcff_clean = [v for v in _series_from_detail(fcff_detail) if v is not None]
        ni_clean = [v for v in _series_from_detail(ni_detail) if v is not None]
        fcfe_clean = [v for v in _series_from_detail(fcfe_detail) if v is not None]
        data.current_fcff = fcff_clean[-1] if fcff_clean else None
        data.current_net_income = ni_clean[-1] if ni_clean else None
        data.current_fcfe = fcfe_clean[-1] if fcfe_clean else None

    except Exception as e:
        data.warnings.append(f"Could not build flow history from cash flow/income statement: {e}")

    data.estimated_cost_of_debt = estimate_cost_of_debt(data.latest_interest_expense, data.total_debt)

    return data
