"""
Beta Calculator v2 - Core Logic
----------------------------------------
Adds to v1:
  - Blume-adjusted beta (Bloomberg-style shrinkage toward 1.0)
  - Full regression diagnostics: t-stat, p-value, 95% confidence interval
  - Covariance/variance cross-check (independent formula, must match regression beta)
  - Plain-language reliability flag based on R-squared / t-stat
  - Selectable benchmark index (Nifty 50 / Sensex / Nifty 500)
  - Beta sensitivity table across lookback x frequency x index combinations
  - Bottom-up (peer-averaged) beta for illiquid/unlisted names

Author: Built with Claude for Deepesh
"""

import yfinance as yf
import pandas as pd
import numpy as np
from scipy import stats

# Benchmark indices, grouped by region for the UI, with a flat lookup for
# resolving names to Yahoo tickers. Verified against Yahoo Finance directly,
# but Yahoo occasionally changes/retires symbols - re-verify if one stops working.
INDEX_REGIONS = {
    "India": {
        "Nifty 50": "^NSEI",
        "Sensex": "^BSESN",
        "Nifty 500": "^CRSLDX",
        "Nifty Bank": "^NSEBANK",
        "Nifty Next 50": "^NSMIDCP",
        "Nifty Midcap 50": "^NSEMDCP50",
        "Nifty Midcap 100": "NIFTY_MIDCAP_100.NS",
        "Nifty Midcap 150": "NIFTYMIDCAP150.NS",
    },
    "North America": {
        "S&P 500": "^GSPC",
        "Dow Jones": "^DJI",
        "Nasdaq Composite": "^IXIC",
        "Russell 2000": "^RUT",
        "S&P/TSX (Canada)": "^GSPTSE",
    },
    "Europe": {
        "FTSE 100 (UK)": "^FTSE",
        "DAX (Germany)": "^GDAXI",
        "CAC 40 (France)": "^FCHI",
        "Euro Stoxx 50": "^STOXX50E",
    },
    "Asia-Pacific": {
        "Nikkei 225 (Japan)": "^N225",
        "Hang Seng (Hong Kong)": "^HSI",
        "Shanghai Composite (China)": "000001.SS",
        "KOSPI (South Korea)": "^KS11",
        "Taiwan Weighted": "^TWII",
        "Straits Times (Singapore)": "^STI",
        "S&P/ASX 200 (Australia)": "^AXJO",
        "Jakarta Composite (Indonesia)": "^JKSE",
    },
    "Other": {
        "Bovespa (Brazil)": "^BVSP",
    },
}

# Flat name -> ticker lookup (used internally; keeps calculate_stock_beta etc. unchanged)
INDEX_TICKERS = {name: ticker for region in INDEX_REGIONS.values() for name, ticker in region.items()}
# Region-prefixed labels for a single searchable dropdown, e.g. "India — Nifty 50"
INDEX_LABELS = {f"{region} — {name}": ticker
                 for region, indices in INDEX_REGIONS.items() for name, ticker in indices.items()}

# ---------------------------------------------------------
# CROSS-MARKET DETECTION: heuristic only, not authoritative -
# yfinance doesn't expose a clean "market"/exchange-region field, so this
# infers region from Yahoo's ticker-suffix convention. Good enough to flag
# an obvious mismatch (an Indian stock vs the S&P 500); not reliable for
# edge cases like ADRs, dual listings, or GDRs.
# ---------------------------------------------------------
TICKER_SUFFIX_REGION = {
    ".NS": "India", ".BO": "India",
    ".L": "Europe", ".DE": "Europe", ".PA": "Europe", ".MI": "Europe", ".AS": "Europe", ".SW": "Europe",
    ".HK": "Asia-Pacific", ".SS": "Asia-Pacific", ".SZ": "Asia-Pacific", ".T": "Asia-Pacific",
    ".KS": "Asia-Pacific", ".TW": "Asia-Pacific", ".SI": "Asia-Pacific", ".AX": "Asia-Pacific",
    ".JK": "Asia-Pacific",
    ".SA": "Other",
    ".TO": "North America", ".V": "North America",
}


def infer_market_region(ticker: str) -> str:
    """
    Best-effort region inference from Yahoo's ticker-suffix convention.
    Defaults to "North America" for suffix-less tickers, since that's the
    common case (US-listed stocks carry no suffix on Yahoo) - this default
    only matters for cross-market detection, never for the beta calculation
    itself.
    """
    ticker_upper = (ticker or "").upper()
    for suffix, region in TICKER_SUFFIX_REGION.items():
        if ticker_upper.endswith(suffix):
            return region
    return "North America"


def index_region(index_key: str) -> str:
    """Region of a benchmark - looked up from its group in INDEX_REGIONS first
    (authoritative for the 28 curated indices), falling back to suffix
    inference if index_key is a raw ticker not in that lookup."""
    for region, indices in INDEX_REGIONS.items():
        if index_key in indices:
            return region
    return infer_market_region(index_key)


def detect_cross_market(ticker: str, index_key: str) -> dict:
    """
    Flags when a stock and its chosen benchmark sit in different regions/
    trading calendars (e.g. an Indian stock against the S&P 500). This is a
    methodological warning only - it does not change the beta calculation,
    restrict the frequency choice, or alter which observations are used.
    """
    stock_region = infer_market_region(ticker)
    bench_region = index_region(index_key)
    is_cross_market = stock_region != bench_region
    warning = None
    if is_cross_market:
        warning = (
            f"Cross-market benchmark: {ticker} ({stock_region}) and {index_key} ({bench_region}) "
            "have different trading calendars and market closing times. Daily beta may be affected "
            "by non-synchronous trading. Weekly or monthly frequency may provide a more comparable "
            "estimate."
        )
    return {
        "stock_region": stock_region,
        "benchmark_region": bench_region,
        "is_cross_market": is_cross_market,
        "warning": warning,
    }


# ---------------------------------------------------------
# STEP 1: Fetch historical prices
# ---------------------------------------------------------
def fetch_prices(ticker: str, period: str = "3y", interval: str = "1wk",
                  start: str = None, end: str = None) -> pd.Series:
    # auto_adjust=True is set explicitly (not left to yfinance's default) so
    # this always returns dividend/split-adjusted close, regardless of which
    # yfinance version is installed - the library changed its own default
    # behavior for this across versions, so relying on it would be fragile.
    if start and end:
        data = yf.download(ticker, start=start, end=end, interval=interval, progress=False, auto_adjust=True)
    else:
        data = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    if data.empty:
        raise ValueError(f"No data returned for {ticker}. Check the ticker symbol.")
    if isinstance(data.columns, pd.MultiIndex):
        close_raw = data["Close"][ticker] if ticker in data["Close"] else data["Close"].iloc[:, 0]
    else:
        close_raw = data["Close"]
    close = close_raw.dropna()
    # Stashed via .attrs (pandas metadata dict) purely for audit reporting -
    # does not change what's returned or how downstream code uses this
    # series; the existing dropna()-based methodology is unchanged.
    close.attrs["raw_len"] = len(close_raw)
    close.attrs["nan_dropped"] = len(close_raw) - len(close)
    return close


def compute_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()


# ---------------------------------------------------------
# COMPANY SEARCH: name -> ticker, via Yahoo's search endpoint
# ---------------------------------------------------------
def search_company(query: str, max_results: int = 8) -> dict:
    """
    Searches by company name (not ticker text-matching) and returns
    candidate tickers. Uses Yahoo Finance's public search endpoint - the
    same one powering the autocomplete on their website - so it handles
    fuzzy/partial name matches, not just exact ticker substrings.

    This is an unofficial endpoint (not a documented API), so it can break
    if Yahoo changes something. Always returns a dict with an 'error' key
    on failure so the UI can fall back to manual ticker entry rather than
    crashing.
    """
    import requests

    if not query or len(query.strip()) < 2:
        return {"results": [], "error": "Type at least 2 characters."}

    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": query, "quotesCount": max_results, "newsCount": 0}
    headers = {"User-Agent": "Mozilla/5.0"}  # Yahoo blocks requests with no User-Agent

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"results": [], "error": f"Search failed ({e}). Enter the ticker manually instead."}

    results = []
    for q in data.get("quotes", []):
        if q.get("quoteType") != "EQUITY":
            continue
        results.append({
            "symbol": q.get("symbol"),
            "name": q.get("shortname") or q.get("longname") or "",
            "exchange": q.get("exchange"),
        })

    if not results:
        return {"results": [], "error": "No matches found. Try a different spelling, or enter the ticker manually."}
    return {"results": results, "error": None}


# ---------------------------------------------------------
# STEP 2: Beta via regression, with a cov/variance cross-check
# ---------------------------------------------------------
def compute_beta(stock_returns: pd.Series, index_returns: pd.Series, interval: str = "1wk") -> dict:
    df = pd.concat([stock_returns, index_returns], axis=1, join="inner")
    df.columns = ["stock", "index"]
    n = len(df)

    if n < 3:
        raise ValueError(f"Only {n} matched observations - not enough to run a regression (need at least 3).")
    if df["index"].var() == 0:
        raise ValueError("Benchmark returns have zero variance over this window - beta is undefined.")

    slope, intercept, r_value, p_value, std_err = stats.linregress(df["index"], df["stock"])

    # Independent cross-check: beta = Cov(stock, index) / Var(index)
    cov_var_beta = df["stock"].cov(df["index"]) / df["index"].var()

    # Annualization factor depends on return frequency
    periods_per_year = {"1d": 252, "1wk": 52, "1mo": 12}.get(interval, 252)

    t_stat = slope / std_err
    df_resid = n - 2  # degrees of freedom: n observations minus 2 estimated params (slope, intercept)

    # 95% CI uses the Student-t critical value for this sample size, not a fixed
    # 1.96 (which is only the large-sample/normal approximation). At small n -
    # e.g. ~11 observations for a 1Y-monthly lookback - the t critical value is
    # meaningfully wider (~2.26 vs 1.96), so the interval would otherwise be
    # falsely narrow.
    t_critical = float(stats.t.ppf(0.975, df_resid))
    ci_low = slope - t_critical * std_err
    ci_high = slope + t_critical * std_err

    # Residual std and Sxx (sum of squared deviations of x) - needed downstream
    # to draw the statistically standard confidence band for the fitted
    # regression LINE (not just the beta coefficient's own CI, which is a
    # different, narrower question). Kept as private (_-prefixed) fields since
    # they're inputs to a calculation, not numbers meant for direct display.
    fitted = intercept + slope * df["index"]
    sse = float(((df["stock"] - fitted) ** 2).sum())
    residual_std = (sse / df_resid) ** 0.5 if df_resid > 0 else float("nan")
    mean_x = float(df["index"].mean())
    sum_sq_dev_x = float(((df["index"] - mean_x) ** 2).sum())

    blume_beta = round((2 / 3) * slope + (1 / 3) * 1.0, 3)  # computed from raw slope, not the rounded display value

    # Three SEPARATE diagnostics rather than one blended "reliability" label -
    # R-squared (how much of the stock's return variance the benchmark
    # explains) and the statistical significance of the beta coefficient
    # itself are different questions; a beta can be statistically significant
    # even when R-squared is low, and conflating them is misleading.
    if abs(t_stat) >= 3:
        significance = "Strong (p < 0.01)"
    elif abs(t_stat) >= t_critical:
        significance = "Significant at 95% confidence"
    else:
        significance = "Not statistically significant at 95% confidence"

    if r_value ** 2 >= 0.40:
        explanatory_power = "High - benchmark explains most of this stock's return variance"
    elif r_value ** 2 >= 0.15:
        explanatory_power = "Moderate - typical for a single stock"
    else:
        explanatory_power = "Low - most of this stock's movement is idiosyncratic, not benchmark-driven"

    if n < 12:
        sample_size_tier = "Very limited (<12 observations) - treat with real caution"
    elif n < 30:
        sample_size_tier = "Limited (12-30 observations)"
    else:
        sample_size_tier = "Adequate (30+ observations)"

    return {
        "beta_regression": round(slope, 3),
        "beta_cov_variance": round(cov_var_beta, 3),
        "beta_match_check": "PASS" if abs(slope - cov_var_beta) < 1e-6 else "FAIL",
        "beta_blume_adjusted": blume_beta,
        "intercept_raw": intercept,  # per-period, unrounded - use this for chart lines, not annualized alpha
        "alpha_period_pct": round(intercept * 100, 4),
        "alpha_annualized_pct": round(intercept * periods_per_year * 100, 2),
        "annualization_convention": f"simple: period alpha × {periods_per_year} periods/year (not compounded)",
        "r_squared": round(r_value ** 2, 3),
        "correlation": round(r_value, 3),
        "std_error": round(std_err, 4),
        "t_stat": round(t_stat, 2),
        "p_value": p_value,
        "df_resid": df_resid,
        "t_critical_95": round(t_critical, 3),
        "ci_95_low": round(ci_low, 3),
        "ci_95_high": round(ci_high, 3),
        "significance": significance,
        "explanatory_power": explanatory_power,
        "sample_size_tier": sample_size_tier,
        "n_observations": n,
        "matched_first_date": str(df.index[0].date()) if hasattr(df.index[0], "date") else str(df.index[0]),
        "matched_last_date": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        # Private fields for chart use only (proper confidence band for the fitted line)
        "_beta_raw": slope,
        "_residual_std": residual_std,
        "_mean_x": mean_x,
        "_sum_sq_dev_x": sum_sq_dev_x,
        # The exact aligned (date, stock_return, index_return) sample used in
        # the regression - the UI should plot THIS, not recompute its own
        # version, so the chart can never silently diverge from the numbers.
        "regression_data": df.rename(columns={"stock": "stock_return", "index": "index_return"}),
    }


def regression_mean_ci_band(x_values, result: dict):
    """
    Proper 95% confidence band for the fitted regression LINE (the mean
    predicted return at each x), as distinct from the beta coefficient's own
    CI. Formula: y_hat(x) +/- t_critical * s * sqrt(1/n + (x-x_bar)^2 / Sxx).
    Narrower near the mean of x, wider at the extremes - the standard shape
    for this kind of band, not a constant-width strip.
    Returns (y_center, y_low, y_high) as numpy arrays aligned to x_values.
    """
    x_values = np.asarray(x_values, dtype=float)
    beta = result["_beta_raw"]
    intercept = result["intercept_raw"]
    s = result["_residual_std"]
    n = result["n_observations"]
    x_bar = result["_mean_x"]
    sxx = result["_sum_sq_dev_x"]
    t_crit = result["t_critical_95"]

    y_center = intercept + beta * x_values
    if sxx <= 0 or n <= 2:
        margin = np.zeros_like(x_values)
    else:
        margin = t_crit * s * np.sqrt(1 / n + (x_values - x_bar) ** 2 / sxx)
    return y_center, y_center - margin, y_center + margin


# ---------------------------------------------------------
# STEP 3: Unlever / relever beta (for comps / bottom-up work)
# ---------------------------------------------------------
def unlever_beta(levered_beta: float, debt_equity: float, tax_rate: float) -> float:
    return levered_beta / (1 + (1 - tax_rate) * debt_equity)


def relever_beta(unlevered_beta: float, debt_equity: float, tax_rate: float) -> float:
    return unlevered_beta * (1 + (1 - tax_rate) * debt_equity)


# ---------------------------------------------------------
# MAIN: single-stock beta, full diagnostics
# ---------------------------------------------------------
def calculate_stock_beta(ticker: str, index_key: str = "Nifty 50",
                          period: str = "3y", interval: str = "1wk",
                          start: str = None, end: str = None) -> dict:
    from datetime import datetime

    index_ticker = INDEX_TICKERS.get(index_key, index_key)  # allow raw ticker too
    stock_prices = fetch_prices(ticker, period, interval, start, end)
    index_prices = fetch_prices(index_ticker, period, interval, start, end)

    stock_returns = compute_returns(stock_prices)
    index_returns = compute_returns(index_prices)

    result = compute_beta(stock_returns, index_returns, interval)
    result["ticker"] = ticker
    result["benchmark"] = index_key
    result["benchmark_ticker"] = index_ticker
    result["period"] = f"{start} to {end}" if (start and end) else period
    result["interval"] = interval
    result["price_adjustment"] = "Auto-adjusted for dividends and splits"
    result["calculated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Date-alignment specifics: how many dates exist in one series' return
    # history but not the other's - these are exactly the observations the
    # inner join in compute_beta drops, made explicit rather than left
    # implicit in the gap between raw counts and matched count.
    stock_dates = set(stock_returns.index)
    index_dates = set(index_returns.index)
    stock_only_dates = len(stock_dates - index_dates)
    benchmark_only_dates = len(index_dates - stock_dates)

    # Audit trail: raw price/return observation counts are NOT the same number
    # as the matched regression sample (n_observations, from compute_beta) -
    # conflating "how many prices we fetched" with "how many aligned pairs
    # went into the regression" hides date-mismatch or missing-data issues.
    result["audit"] = {
        "stock_raw_price_obs": len(stock_prices),
        "stock_date_range": f"{stock_prices.index[0].date()} to {stock_prices.index[-1].date()}",
        "stock_return_obs": len(stock_returns),
        "stock_missing_values_dropped": stock_prices.attrs.get("nan_dropped", 0),
        "index_raw_price_obs": len(index_prices),
        "index_date_range": f"{index_prices.index[0].date()} to {index_prices.index[-1].date()}",
        "index_return_obs": len(index_returns),
        "index_missing_values_dropped": index_prices.attrs.get("nan_dropped", 0),
        "matched_regression_obs": result["n_observations"],
        "matched_date_range": f"{result['matched_first_date']} to {result['matched_last_date']}",
        "stock_only_dates": stock_only_dates,
        "benchmark_only_dates": benchmark_only_dates,
    }

    # Cross-market check: methodological warning only - does not alter the
    # calculation, the observations used, or the frequency selected.
    result["market_audit"] = detect_cross_market(ticker, index_key)

    # Raw price series are already fetched above for the regression itself -
    # exposing them here lets callers (e.g. the charts in beta_page.py) reuse
    # this exact data instead of fetching the same ticker/period/interval a
    # second time. Previously beta_page.py called a separate cached_prices()
    # for chart data right after this function ran, downloading the same two
    # series twice on every fresh (uncached) calculation.
    result["stock_prices"] = stock_prices
    result["index_prices"] = index_prices

    return result


# ---------------------------------------------------------
# SENSITIVITY TABLE: same stock, multiple methodologies
# ---------------------------------------------------------
def beta_sensitivity(ticker: str,
                      periods=("1y", "3y", "5y"),
                      intervals=("1d", "1wk", "1mo"),
                      index_keys=("Nifty 50",),
                      custom_start: str = None, custom_end: str = None) -> pd.DataFrame:
    """
    If "Custom" appears in periods, that entry uses custom_start/custom_end
    (explicit dates) instead of a preset relative lookback - the displayed
    'period' label for that row becomes the actual date range.
    """
    rows = []
    for idx_key in index_keys:
        for period in periods:
            for interval in intervals:
                try:
                    if period == "Custom" and custom_start and custom_end:
                        r = calculate_stock_beta(ticker, idx_key, interval=interval,
                                                  start=custom_start, end=custom_end)
                        period_label = f"{custom_start} to {custom_end}"
                    else:
                        r = calculate_stock_beta(ticker, idx_key, period, interval)
                        period_label = period
                    rows.append({
                        "benchmark": idx_key,
                        "period": period_label,
                        "interval": interval,
                        "beta": r["beta_regression"],
                        "blume_beta": r["beta_blume_adjusted"],
                        "ci_95_low": r["ci_95_low"],
                        "ci_95_high": r["ci_95_high"],
                        "r_squared": r["r_squared"],
                        "n_obs": r["n_observations"],
                        "sample_size_tier": r["sample_size_tier"],
                        "status": "success",
                        "error": None,
                    })
                except Exception as e:
                    # Explicit failure, not a blank cell that looks like a
                    # legitimate missing result - a failed calculation and a
                    # merely-missing one should never look identical.
                    period_label = f"{custom_start} to {custom_end}" if period == "Custom" else period
                    rows.append({
                        "benchmark": idx_key, "period": period_label, "interval": interval,
                        "beta": None, "blume_beta": None, "ci_95_low": None, "ci_95_high": None,
                        "r_squared": None, "n_obs": None, "sample_size_tier": None,
                        "status": "error", "error": str(e),
                    })
    return pd.DataFrame(rows)


# ---------------------------------------------------------
# ROLLING BETA: re-estimate beta on a trailing window to spot drift
# ---------------------------------------------------------
def rolling_beta(stock_returns: pd.Series, index_returns: pd.Series, window: int = 26) -> pd.Series:
    """
    Computes beta on a trailing rolling window (cov/variance method - fast,
    avoids re-running a full regression at every point).
    window: periods per window (e.g. 26 weeks ~ 6 months for weekly data).
    """
    df = pd.concat([stock_returns, index_returns], axis=1, join="inner")
    df.columns = ["stock", "index"]

    rolling_cov = df["stock"].rolling(window).cov(df["index"])
    rolling_var = df["index"].rolling(window).var()
    return (rolling_cov / rolling_var).dropna()


# ---------------------------------------------------------
# AUTO-FETCH: pull D/E and effective tax rate from financials
# ---------------------------------------------------------
def fetch_company_financials(ticker: str) -> dict:
    """
    Pulls Total Debt, Total Equity, and effective tax rate from the
    latest available balance sheet / income statement on yfinance.

    Returns None for any field it can't find, plus a 'source' flag per
    field, so the UI can show "auto-fetched" vs "needs manual input"
    rather than silently displaying a wrong or zero value.
    """
    result = {
        "debt_equity": None, "debt_equity_source": "missing",
        "tax_rate": None, "tax_rate_source": "missing",
        "total_debt": None, "total_equity": None,
        "balance_sheet_date": None, "tax_statement_date": None,
    }

    tk = yf.Ticker(ticker)

    # --- Balance sheet: Total Debt / Total Equity -> D/E ---
    try:
        bs = tk.balance_sheet
        if bs is not None and not bs.empty:
            latest = bs.iloc[:, 0]  # most recent fiscal period, first column
            result["balance_sheet_date"] = str(bs.columns[0].date()) if hasattr(bs.columns[0], "date") \
                else str(bs.columns[0])

            debt_row = next((r for r in ["Total Debt", "TotalDebt"] if r in bs.index), None)
            equity_row = next((r for r in ["Stockholders Equity", "Total Stockholder Equity",
                                            "Common Stock Equity"] if r in bs.index), None)

            if debt_row and equity_row:
                total_debt = latest[debt_row]
                total_equity = latest[equity_row]
                if total_equity and float(total_equity) > 0:
                    result["total_debt"] = round(float(total_debt), 0)
                    result["total_equity"] = round(float(total_equity), 0)
                    result["debt_equity"] = round(float(total_debt) / float(total_equity), 3)
                    result["debt_equity_source"] = "auto-fetched"
                elif total_equity and float(total_equity) <= 0:
                    # Negative/zero book equity makes D/E meaningless (or
                    # infinite/undefined) - leave as missing rather than
                    # silently showing a nonsensical or negative ratio.
                    result["debt_equity_source"] = "missing (negative or zero book equity - needs manual input)"
    except Exception:
        pass  # leave as "missing" - UI will prompt for manual entry

    # --- Income statement: tax expense / pre-tax income -> effective tax rate ---
    try:
        inc = tk.financials
        if inc is not None and not inc.empty:
            latest = inc.iloc[:, 0]
            result["tax_statement_date"] = str(inc.columns[0].date()) if hasattr(inc.columns[0], "date") \
                else str(inc.columns[0])
            tax_row = next((r for r in ["Tax Provision", "Income Tax Expense"] if r in inc.index), None)
            pretax_row = next((r for r in ["Pretax Income", "Income Before Tax"] if r in inc.index), None)

            if tax_row and pretax_row:
                tax_expense = latest[tax_row]
                pretax_income = latest[pretax_row]
                if pretax_income and pretax_income != 0:
                    rate = float(tax_expense) / float(pretax_income)
                    # Sanity bound - effective rates outside this range are usually a
                    # one-off (deferred tax credit, etc.), not the "normal" rate to use
                    if 0 <= rate <= 0.45:
                        result["tax_rate"] = round(rate, 3)
                        result["tax_rate_source"] = "auto-fetched"
    except Exception:
        pass

    return result


# ---------------------------------------------------------
# BOTTOM-UP BETA: for illiquid/unlisted names via peer set
# ---------------------------------------------------------
def bottom_up_beta(peers: list, target_debt_equity: float, target_tax_rate: float,
                    index_key: str = "Nifty 50", period: str = "3y", interval: str = "1wk") -> dict:
    """
    peers: list of dicts, each {"ticker": "PEER.NS", "debt_equity": 0.4, "tax_rate": 0.25}
    Unlevers each peer's beta, averages the unlevered (asset) betas,
    then relevers to the target company's own capital structure.

    A single peer failing (sparse data, delisting, bad ticker, etc.) does NOT
    abort the whole calculation - that peer is excluded from the aggregate
    and flagged explicitly, the rest still get calculated normally.
    """
    unlevered_betas = []
    peer_details = []
    failed_peers = []
    for peer in peers:
        try:
            r = calculate_stock_beta(peer["ticker"], index_key, period, interval)
            u_beta = unlever_beta(r["beta_regression"], peer["debt_equity"], peer["tax_rate"])
            unlevered_betas.append(u_beta)
            peer_details.append({
                "ticker": peer["ticker"],
                "levered_beta": r["beta_regression"],
                "debt_equity": peer["debt_equity"],
                "unlevered_beta": round(u_beta, 3),
                "r_squared": r["r_squared"],
                "status": "success",
            })
        except Exception as e:
            failed_peers.append({"ticker": peer["ticker"], "error": str(e)})
            peer_details.append({
                "ticker": peer["ticker"],
                "levered_beta": None,
                "debt_equity": peer["debt_equity"],
                "unlevered_beta": None,
                "r_squared": None,
                "status": "error",
                "error": str(e),
            })

    if not unlevered_betas:
        raise ValueError(
            f"None of the {len(peers)} peers could be calculated. "
            f"First error ({failed_peers[0]['ticker']}): {failed_peers[0]['error']}"
        )

    # D/E outlier check: a peer whose leverage is way out of line with the
    # group (e.g. a consolidated NBFC subsidiary skewing the balance sheet,
    # like TVS Motor) can silently drag the average to an unrepresentative
    # number. Flag anything beyond 2x / below 0.5x the group median.
    # Only successful peers have a meaningful debt_equity to compare here.
    successful_peers = [p for p in peer_details if p["status"] == "success"]
    de_values = [p["debt_equity"] for p in successful_peers]
    median_de = float(np.median(de_values)) if de_values else 0.0
    for p in peer_details:
        if p["status"] != "success":
            p["de_outlier_flag"] = None
            continue
        if median_de > 0 and (p["debt_equity"] > 2 * median_de or p["debt_equity"] < 0.5 * median_de):
            ratio = p["debt_equity"] / median_de
            p["de_outlier_flag"] = (f"D/E = {ratio:.1f}x peer median ({median_de}) - "
                                     f"verify this isn't a consolidation artifact")
        else:
            p["de_outlier_flag"] = None

    avg_unlevered = np.mean(unlevered_betas)
    median_unlevered = float(np.median(unlevered_betas))
    relevered_mean = relever_beta(avg_unlevered, target_debt_equity, target_tax_rate)
    relevered_median = relever_beta(median_unlevered, target_debt_equity, target_tax_rate)

    return {
        "peer_details": peer_details,
        "failed_peers": failed_peers,
        "median_debt_equity": round(median_de, 3),
        "average_unlevered_beta": round(avg_unlevered, 3),
        "median_unlevered_beta": round(median_unlevered, 3),
        "target_debt_equity": target_debt_equity,
        "target_tax_rate": target_tax_rate,
        "bottom_up_beta": round(relevered_mean, 3),  # mean stays the default methodology
        "bottom_up_beta_median": round(relevered_median, 3),  # exposed as a robustness check, not a replacement
    }


if __name__ == "__main__":
    # Example (requires live internet - run this on your machine, not in a sandbox):
    result = calculate_stock_beta("RELIANCE.NS", "Nifty 50", period="3y", interval="1wk")
    print("Beta Calculation")
    print("-" * 40)
    for k, v in result.items():
        print(f"{k:28}{v}")
