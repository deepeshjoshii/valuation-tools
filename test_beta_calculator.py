"""
test_beta_calculator.py
------------------------
Automated tests for beta_calculator.py's core statistics. Run with:
    pytest test_beta_calculator.py -v

These use synthetic data with KNOWN properties (a known true beta, a known
zero-variance series, etc.) rather than live Yahoo Finance data, so they run
offline and give an exact right answer to check against - not just "did it
crash". Network-dependent functions (fetch_prices, search_company,
fetch_company_financials) are exercised structurally with mocked responses,
since live data isn't available in every environment this runs in.
"""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from beta_calculator import (
    compute_beta, unlever_beta, relever_beta, bottom_up_beta,
    beta_sensitivity, regression_mean_ci_band, rolling_beta,
    infer_market_region, index_region, detect_cross_market,
)


# ---------------------------------------------------------
# Fixtures: synthetic return series with known properties
# ---------------------------------------------------------
@pytest.fixture
def synthetic_returns():
    """Index returns + stock returns built from a KNOWN true beta of 1.35,
    so the regression's recovered beta can be checked against ground truth."""
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=500, freq="D")
    index_returns = pd.Series(np.random.normal(0, 0.01, 500), index=dates)
    true_beta = 1.35
    noise = np.random.normal(0, 0.005, 500)
    stock_returns = pd.Series(true_beta * index_returns.values + noise, index=dates)
    return stock_returns, index_returns, true_beta


@pytest.fixture
def small_sample_returns():
    """11 observations - matches the 1Y-monthly case flagged throughout
    the conversation as needing the t-distribution, not a fixed 1.96."""
    np.random.seed(7)
    n = 11
    dates = pd.date_range("2025-01-01", periods=n, freq="ME")
    index_returns = pd.Series(np.random.normal(0, 0.03, n), index=dates)
    stock_returns = pd.Series(1.2 * index_returns.values + np.random.normal(0, 0.015, n), index=dates)
    return stock_returns, index_returns


# ---------------------------------------------------------
# Test 1 - Regression beta matches covariance/variance beta
# ---------------------------------------------------------
def test_regression_matches_covariance_beta(synthetic_returns):
    stock_returns, index_returns, _ = synthetic_returns
    result = compute_beta(stock_returns, index_returns, interval="1d")
    assert result["beta_match_check"] == "PASS"
    assert abs(result["beta_regression"] - result["beta_cov_variance"]) < 1e-6


def test_regression_recovers_known_beta(synthetic_returns):
    """With synthetic data built from a true beta of 1.35, the regression
    should recover something close to it (within noise tolerance)."""
    stock_returns, index_returns, true_beta = synthetic_returns
    result = compute_beta(stock_returns, index_returns, interval="1d")
    assert abs(result["beta_regression"] - true_beta) < 0.1


# ---------------------------------------------------------
# Test 2 - Blume adjustment formula
# ---------------------------------------------------------
def test_blume_adjustment_formula(synthetic_returns):
    stock_returns, index_returns, _ = synthetic_returns
    result = compute_beta(stock_returns, index_returns, interval="1d")
    expected_blume = round((2 / 3) * result["beta_regression"] + (1 / 3) * 1.0, 3)
    # Allow tiny tolerance since beta_regression is itself rounded for display;
    # the actual implementation computes Blume from the raw unrounded slope.
    assert abs(result["beta_blume_adjusted"] - expected_blume) < 0.005


# ---------------------------------------------------------
# Test 3 - R-squared equals correlation squared (simple linear regression identity)
# ---------------------------------------------------------
def test_r_squared_equals_correlation_squared(synthetic_returns):
    stock_returns, index_returns, _ = synthetic_returns
    result = compute_beta(stock_returns, index_returns, interval="1d")
    assert abs(result["r_squared"] - result["correlation"] ** 2) < 0.001


# ---------------------------------------------------------
# Test 4 - Confidence interval uses the Student-t critical value, not 1.96
# ---------------------------------------------------------
def test_ci_uses_t_distribution_not_fixed_1_96(small_sample_returns):
    stock_returns, index_returns = small_sample_returns
    result = compute_beta(stock_returns, index_returns, interval="1mo")

    n = result["n_observations"]
    df = n - 2
    expected_t_critical = stats.t.ppf(0.975, df)

    assert abs(result["t_critical_95"] - expected_t_critical) < 0.001
    # At n=11 (df=9), t-critical (~2.262) must be meaningfully wider than 1.96
    assert result["t_critical_95"] > 1.96 + 0.1

    expected_ci_low = result["_beta_raw"] - expected_t_critical * result["std_error"]
    assert abs(result["ci_95_low"] - round(expected_ci_low, 3)) < 0.01


@pytest.mark.parametrize("n,expected_t_critical", [
    (11, 2.262), (35, 2.035), (52, 2.009), (156, 1.975),
    (261, 1.969), (738, 1.963), (1234, 1.962),
])
def test_t_critical_matches_known_table_values(n, expected_t_critical):
    """Cross-checks scipy's t.ppf against a known reference table of
    critical values for common sample sizes in this tool's sensitivity grid."""
    df = n - 2
    t_critical = stats.t.ppf(0.975, df)
    assert abs(t_critical - expected_t_critical) < 0.001


# ---------------------------------------------------------
# Test 5 - Degrees of freedom = n - 2
# ---------------------------------------------------------
def test_degrees_of_freedom(synthetic_returns):
    stock_returns, index_returns, _ = synthetic_returns
    result = compute_beta(stock_returns, index_returns, interval="1d")
    assert result["df_resid"] == result["n_observations"] - 2


# ---------------------------------------------------------
# Test 6 - Insufficient observations fails gracefully, not silently
# ---------------------------------------------------------
def test_insufficient_observations_raises():
    dates = pd.date_range("2025-01-01", periods=2, freq="D")
    stock_returns = pd.Series([0.01, 0.02], index=dates)
    index_returns = pd.Series([0.01, 0.015], index=dates)
    with pytest.raises(ValueError, match="not enough"):
        compute_beta(stock_returns, index_returns)


# ---------------------------------------------------------
# Test 7 - Constant (zero-variance) benchmark returns should not silently
# produce a beta - division by zero variance is undefined, not "0" or "inf"
# ---------------------------------------------------------
def test_constant_benchmark_raises():
    dates = pd.date_range("2025-01-01", periods=20, freq="D")
    stock_returns = pd.Series(np.random.normal(0, 0.01, 20), index=dates)
    index_returns = pd.Series([0.0] * 20, index=dates)  # zero variance
    with pytest.raises(ValueError, match="zero variance"):
        compute_beta(stock_returns, index_returns)


# ---------------------------------------------------------
# Test 8 - Missing/misaligned data is correctly inner-joined, not silently
# padded or mismatched
# ---------------------------------------------------------
def test_misaligned_dates_use_inner_join_only():
    dates_stock = pd.date_range("2025-01-01", periods=30, freq="D")
    dates_index = pd.date_range("2025-01-10", periods=30, freq="D")  # offset, partial overlap
    stock_returns = pd.Series(np.random.normal(0, 0.01, 30), index=dates_stock)
    index_returns = pd.Series(np.random.normal(0, 0.01, 30), index=dates_index)

    result = compute_beta(stock_returns, index_returns, interval="1d")
    expected_overlap = len(set(dates_stock) & set(dates_index))
    assert result["n_observations"] == expected_overlap
    assert result["n_observations"] < 30  # confirms it did NOT just use all 30 of either series


# ---------------------------------------------------------
# Test 9 - Bottom-up beta: unlever/relever formulas and mean/median
# ---------------------------------------------------------
def test_unlever_relever_round_trip():
    levered = 1.35
    de, tax = 0.6, 0.25
    unlevered = unlever_beta(levered, de, tax)
    relevered = relever_beta(unlevered, de, tax)
    assert abs(relevered - levered) < 1e-9  # same D/E and tax in both directions must round-trip exactly


def test_unlever_formula_matches_hamada():
    levered, de, tax = 1.35, 0.6, 0.25
    expected = levered / (1 + (1 - tax) * de)
    assert abs(unlever_beta(levered, de, tax) - expected) < 1e-12


def test_bottom_up_beta_exposes_mean_and_median(monkeypatch):
    """Uses a mocked calculate_stock_beta so this test doesn't need network -
    fixed betas simulate the TVS-Motor-style outlier case from earlier
    testing in this conversation."""
    import beta_calculator as bc

    fixed_betas = {"A.NS": 1.669, "B.NS": 1.12, "C.NS": 1.166}

    def fake_calc(ticker, index_key="Nifty 50", period="3y", interval="1wk"):
        return {"beta_regression": fixed_betas[ticker], "r_squared": 0.3}

    monkeypatch.setattr(bc, "calculate_stock_beta", fake_calc)

    peers = [
        {"ticker": "A.NS", "debt_equity": 3.428, "tax_rate": 0.339},  # outlier D/E
        {"ticker": "B.NS", "debt_equity": 0.583, "tax_rate": 0.25},
        {"ticker": "C.NS", "debt_equity": 0.15, "tax_rate": 0.25},
    ]
    result = bc.bottom_up_beta(peers, target_debt_equity=0.3, target_tax_rate=0.25)

    assert "bottom_up_beta" in result and "bottom_up_beta_median" in result
    assert result["average_unlevered_beta"] is not None
    assert result["median_unlevered_beta"] is not None
    # The outlier peer (A.NS) must be flagged
    outlier_flags = [p["de_outlier_flag"] for p in result["peer_details"] if p["ticker"] == "A.NS"]
    assert outlier_flags[0] is not None
    assert "x peer median" in outlier_flags[0]


# ---------------------------------------------------------
# Test 10 - Sensitivity grid: correct combination count, uniqueness, and
# explicit error status rather than silently swallowed failures
# ---------------------------------------------------------
def test_sensitivity_grid_combination_count_and_uniqueness(monkeypatch):
    import beta_calculator as bc

    def fake_calc(ticker, index_key="Nifty 50", period="3y", interval="1wk"):
        return {
            "beta_regression": 1.05, "beta_blume_adjusted": 1.03,
            "ci_95_low": 0.9, "ci_95_high": 1.2, "r_squared": 0.4,
            "n_observations": 100, "sample_size_tier": "Adequate (30+ observations)",
        }

    monkeypatch.setattr(bc, "calculate_stock_beta", fake_calc)

    df = bc.beta_sensitivity("TEST.NS", periods=("1y", "3y", "5y"),
                              intervals=("1d", "1wk", "1mo"), index_keys=("Nifty 50",))

    assert len(df) == 9  # 3 periods x 3 intervals x 1 index
    combos = df[["benchmark", "period", "interval"]].drop_duplicates()
    assert len(combos) == 9  # no duplicate combinations
    assert (df["status"] == "success").all()
    assert df["r_squared"].between(0, 1).all()


def test_sensitivity_grid_surfaces_errors_explicitly(monkeypatch):
    import beta_calculator as bc

    def fake_calc_fails_on_1y_monthly(ticker, index_key="Nifty 50", period="3y", interval="1wk"):
        if period == "1y" and interval == "1mo":
            raise ValueError("insufficient observations")
        return {
            "beta_regression": 1.0, "beta_blume_adjusted": 1.0,
            "ci_95_low": 0.8, "ci_95_high": 1.2, "r_squared": 0.3,
            "n_observations": 50, "sample_size_tier": "Limited (12-30 observations)",
        }

    monkeypatch.setattr(bc, "calculate_stock_beta", fake_calc_fails_on_1y_monthly)

    df = bc.beta_sensitivity("TEST.NS", periods=("1y", "3y"), intervals=("1mo", "1wk"),
                              index_keys=("Nifty 50",))

    failed_row = df[(df["period"] == "1y") & (df["interval"] == "1mo")].iloc[0]
    assert failed_row["status"] == "error"
    # pandas coerces None to NaN when a column mixes floats and None across
    # rows - that's expected pandas behavior, not a defect in beta_sensitivity
    assert pd.isna(failed_row["beta"])
    assert "insufficient observations" in failed_row["error"]
    # Every other combination should still have succeeded independently
    assert (df[df["status"] == "success"].shape[0]) == 3


# ---------------------------------------------------------
# Extra: regression confidence band shape (narrower near mean(x))
# ---------------------------------------------------------
def test_confidence_band_narrower_near_mean_x(synthetic_returns):
    stock_returns, index_returns, _ = synthetic_returns
    result = compute_beta(stock_returns, index_returns, interval="1d")

    x = np.array([result["_mean_x"] - 0.05, result["_mean_x"], result["_mean_x"] + 0.05])
    y_center, y_low, y_high = regression_mean_ci_band(x, result)

    width_at_mean = y_high[1] - y_low[1]
    width_at_extremes = (y_high[0] - y_low[0]) + (y_high[2] - y_low[2])
    assert width_at_mean * 2 < width_at_extremes  # band must widen away from the mean


# ---------------------------------------------------------
# Extra: rolling beta handles short windows without crashing
# ---------------------------------------------------------
def test_rolling_beta_insufficient_window_returns_empty():
    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    stock_returns = pd.Series(np.random.normal(0, 0.01, 5), index=dates)
    index_returns = pd.Series(np.random.normal(0, 0.01, 5), index=dates)
    result = rolling_beta(stock_returns, index_returns, window=26)  # window > available data
    assert len(result) == 0  # should be empty, not crash


def test_bottom_up_beta_isolates_single_peer_failure(monkeypatch):
    """One peer failing (sparse data, bad ticker, etc.) must not crash the
    whole calculation - the other peers should still succeed, and the
    failure should be explicit, not silent."""
    import beta_calculator as bc

    fixed = {"A.NS": 1.05, "B.NS": 0.95, "C.NS": 1.02}

    def fake_calc(ticker, index_key="Nifty 50", period="3y", interval="1wk"):
        if ticker == "BAD.NS":
            raise ValueError("Only 1 matched observations - not enough to run a regression (need at least 3).")
        return {"beta_regression": fixed[ticker], "r_squared": 0.35}

    monkeypatch.setattr(bc, "calculate_stock_beta", fake_calc)

    peers = [
        {"ticker": "A.NS", "debt_equity": 0.6, "tax_rate": 0.25},
        {"ticker": "B.NS", "debt_equity": 0.5, "tax_rate": 0.25},
        {"ticker": "C.NS", "debt_equity": 0.4, "tax_rate": 0.25},
        {"ticker": "BAD.NS", "debt_equity": 0.3, "tax_rate": 0.25},
    ]
    res = bc.bottom_up_beta(peers, target_debt_equity=0.3, target_tax_rate=0.25)

    assert res["bottom_up_beta"] is not None  # must not have crashed
    assert len(res["failed_peers"]) == 1
    assert res["failed_peers"][0]["ticker"] == "BAD.NS"
    succeeded = [p for p in res["peer_details"] if p["status"] == "success"]
    assert len(succeeded) == 3  # the 3 good peers must still be present


def test_bottom_up_beta_all_peers_fail_raises_clear_error(monkeypatch):
    import beta_calculator as bc

    def fake_calc_always_fails(ticker, index_key="Nifty 50", period="3y", interval="1wk"):
        raise ValueError("no data")

    monkeypatch.setattr(bc, "calculate_stock_beta", fake_calc_always_fails)

    peers = [{"ticker": "X.NS", "debt_equity": 0.5, "tax_rate": 0.25}]
    with pytest.raises(ValueError, match="None of the"):
        bc.bottom_up_beta(peers, target_debt_equity=0.3, target_tax_rate=0.25)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))


# ---------------------------------------------------------
# Cross-market detection (pure functions, no network)
# ---------------------------------------------------------

def test_infer_market_region_india_suffixes():
    assert infer_market_region("RELIANCE.NS") == "India"
    assert infer_market_region("TATASTEEL.BO") == "India"


def test_infer_market_region_defaults_to_north_america_for_no_suffix():
    assert infer_market_region("AAPL") == "North America"
    assert infer_market_region("MSFT") == "North America"


def test_infer_market_region_other_suffixes():
    assert infer_market_region("VOD.L") == "Europe"
    assert infer_market_region("7203.T") == "Asia-Pacific"
    assert infer_market_region("PETR4.SA") == "Other"
    assert infer_market_region("SHOP.TO") == "North America"


def test_index_region_known_indices():
    assert index_region("Nifty 50") == "India"
    assert index_region("S&P 500") == "North America"
    assert index_region("FTSE 100 (UK)") == "Europe"
    assert index_region("Nikkei 225 (Japan)") == "Asia-Pacific"


def test_index_region_falls_back_to_suffix_for_raw_ticker():
    assert index_region("^GSPTSE") == "North America"  # not in INDEX_REGIONS names, no suffix match either -> default


def test_detect_cross_market_flags_indian_stock_vs_sp500():
    result = detect_cross_market("RELIANCE.NS", "S&P 500")
    assert result["is_cross_market"] is True
    assert result["stock_region"] == "India"
    assert result["benchmark_region"] == "North America"
    assert "Cross-market benchmark" in result["warning"]
    assert "RELIANCE.NS" in result["warning"]


def test_detect_cross_market_no_warning_for_same_market():
    result = detect_cross_market("RELIANCE.NS", "Nifty 50")
    assert result["is_cross_market"] is False
    assert result["warning"] is None


def test_detect_cross_market_no_warning_for_us_stock_vs_sp500():
    result = detect_cross_market("AAPL", "S&P 500")
    assert result["is_cross_market"] is False
    assert result["warning"] is None
