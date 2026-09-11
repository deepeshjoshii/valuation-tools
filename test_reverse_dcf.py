import pytest
from reverse_dcf import (
    value_at_growth,
    solve_implied_cagr,
    flow_trajectory,
    historical_cagr,
    historical_cagr_with_reason,
    trailing_cagr_with_reason,
    compute_fcff,
    compute_fcfe,
    estimate_cost_of_debt,
    compute_wacc,
)


# ---------------------------------------------------------------------------
# value_at_growth (generic PV engine - shared by Net Income/Ke, FCFF/WACC, FCFE/Ke)
# ---------------------------------------------------------------------------

def test_value_zero_growth_matches_manual_sum():
    v, pv_tv, tv = value_at_growth(
        current_flow=1000, growth_rate=0.0, discount_rate=0.10, terminal_growth=0.04,
        projection_years=5,
    )
    manual_pv = sum(1000 / (1.10 ** t) for t in range(1, 6))
    manual_tv = 1000 * 1.04 / (0.10 - 0.04)
    manual_pv_tv = manual_tv / (1.10 ** 5)
    assert v == pytest.approx(manual_pv + manual_pv_tv, rel=1e-9)
    assert tv == pytest.approx(manual_tv, rel=1e-9)
    assert pv_tv == pytest.approx(manual_pv_tv, rel=1e-9)


def test_value_increases_with_growth_rate():
    v_low, _, _ = value_at_growth(1000, 0.02, 0.10, 0.04, 5)
    v_high, _, _ = value_at_growth(1000, 0.15, 0.10, 0.04, 5)
    assert v_high > v_low


def test_value_raises_when_discount_rate_not_greater_than_terminal_growth():
    with pytest.raises(ValueError, match="must be greater than terminal growth"):
        value_at_growth(1000, 0.05, 0.04, 0.04, 5)
    with pytest.raises(ValueError):
        value_at_growth(1000, 0.05, 0.03, 0.04, 5)


# ---------------------------------------------------------------------------
# solve_implied_cagr (round-trip against value_at_growth)
# ---------------------------------------------------------------------------

def test_solve_round_trips_with_value_function():
    current_flow = 1000
    discount_rate, terminal_growth, years = 0.10, 0.04, 5
    known_growth = 0.12

    target_value, _, _ = value_at_growth(
        current_flow, known_growth, discount_rate, terminal_growth, years
    )
    solved_growth = solve_implied_cagr(
        current_flow, target_value, discount_rate, terminal_growth, years
    )
    assert solved_growth == pytest.approx(known_growth, abs=1e-4)


def test_solve_handles_negative_implied_growth():
    current_flow = 1000
    discount_rate, terminal_growth, years = 0.10, 0.04, 5
    known_growth = -0.10  # a price implying a declining flow base

    target_value, _, _ = value_at_growth(
        current_flow, known_growth, discount_rate, terminal_growth, years
    )
    solved_growth = solve_implied_cagr(
        current_flow, target_value, discount_rate, terminal_growth, years
    )
    assert solved_growth == pytest.approx(known_growth, abs=1e-4)


def test_solve_raises_on_nonpositive_current_flow():
    with pytest.raises(ValueError, match="zero or negative"):
        solve_implied_cagr(0, 10000, 0.10, 0.04, 5)
    with pytest.raises(ValueError, match="zero or negative"):
        solve_implied_cagr(-500, 10000, 0.10, 0.04, 5)


def test_solve_raises_when_target_unreachable_in_bounds():
    with pytest.raises(ValueError, match="No solution found"):
        solve_implied_cagr(
            current_flow=1000, target_value=10**15, discount_rate=0.10,
            terminal_growth=0.04, projection_years=5,
        )


def test_solve_works_for_ke_equity_pairing_not_just_wacc_ev():
    # Same math, different discount rate/target pairing (Net Income or FCFE
    # against Ke and Market Cap, rather than FCFF against WACC and EV) -
    # the solver itself doesn't know or care which pairing is in use.
    current_flow, ke, terminal_growth, years = 500, 0.13, 0.04, 5
    known_growth = 0.08
    market_cap, _, _ = value_at_growth(current_flow, known_growth, ke, terminal_growth, years)
    solved = solve_implied_cagr(current_flow, market_cap, ke, terminal_growth, years)
    assert solved == pytest.approx(known_growth, abs=1e-4)


# ---------------------------------------------------------------------------
# flow_trajectory
# ---------------------------------------------------------------------------

def test_trajectory_length_and_year_zero():
    traj = flow_trajectory(1000, 0.10, 5)
    assert len(traj) == 6  # years 0..5 inclusive
    assert traj[0]["year"] == 0
    assert traj[0]["flow"] == pytest.approx(1000)
    assert traj[5]["flow"] == pytest.approx(1000 * 1.10 ** 5)


# ---------------------------------------------------------------------------
# historical_cagr
# ---------------------------------------------------------------------------

def test_historical_cagr_basic():
    series = [1000, None, 1610.51]  # None should be filtered, changing n
    cagr = historical_cagr(series)
    assert cagr == pytest.approx(0.61051, rel=1e-4)


def test_historical_cagr_proper_multi_year():
    series = [1000, 1100, 1210, 1331, 1464.1]  # 10% CAGR over 4 periods
    cagr = historical_cagr(series)
    assert cagr == pytest.approx(0.10, rel=1e-3)


def test_historical_cagr_none_on_insufficient_data():
    assert historical_cagr([1000]) is None
    assert historical_cagr([]) is None


def test_historical_cagr_none_on_nonpositive_start():
    assert historical_cagr([-100, 500, 800]) is None
    assert historical_cagr([0, 500, 800]) is None


def test_historical_cagr_filters_nan_not_just_none():
    series = [float("nan"), 1000, 1100, 1210, 1331]
    cagr = historical_cagr(series)
    assert cagr == pytest.approx(0.10, rel=1e-3)


# ---------------------------------------------------------------------------
# compute_fcff / compute_fcfe
# ---------------------------------------------------------------------------

def test_compute_fcff_basic():
    # CFO=1200, Interest=100, tax=25%, Capex=300 -> 1200 + 100*0.75 - 300 = 975
    assert compute_fcff(1200, 100, 0.25, 300) == pytest.approx(975)


def test_compute_fcff_handles_negative_capex_sign_convention():
    assert compute_fcff(1200, 100, 0.25, -300) == pytest.approx(975)


def test_compute_fcfe_basic():
    assert compute_fcfe(1200, 300, 200) == pytest.approx(1100)


# ---------------------------------------------------------------------------
# historical_cagr_with_reason
# ---------------------------------------------------------------------------

def test_reason_ok_when_computable():
    series = [1000, 1100, 1210, 1331]
    cagr, reason, msg = historical_cagr_with_reason(series)
    assert reason == "ok"
    assert msg is None
    assert cagr == pytest.approx(0.10, rel=1e-3)


def test_reason_insufficient_data_when_too_few_periods_given():
    cagr, reason, msg = historical_cagr_with_reason([1000])
    assert cagr is None
    assert reason == "insufficient_data"


def test_reason_missing_values_when_nans_reduce_below_two():
    cagr, reason, msg = historical_cagr_with_reason([float("nan"), None, 1000])
    assert cagr is None
    assert reason == "missing_values"


def test_reason_non_positive_start_when_enough_data_but_bad_base():
    cagr, reason, msg = historical_cagr_with_reason([-100, 500, 800, 900])
    assert cagr is None
    assert reason == "non_positive_start"


# ---------------------------------------------------------------------------
# trailing_cagr_with_reason
# ---------------------------------------------------------------------------

def test_trailing_cagr_uses_only_the_requested_window():
    series = [1000, 1100, 1210, 1331, 1464.1, 1610.51]  # flat 10% CAGR throughout
    cagr_5y, reason_5y, _ = trailing_cagr_with_reason(series, years=5)
    cagr_3y, reason_3y, _ = trailing_cagr_with_reason(series, years=3)
    assert reason_5y == "ok" and cagr_5y == pytest.approx(0.10, rel=1e-3)
    assert reason_3y == "ok" and cagr_3y == pytest.approx(0.10, rel=1e-3)


def test_trailing_cagr_reports_insufficient_data_by_name():
    series = [1000, 1100, 1210, 1331]  # only 4 points - a 5-year CAGR needs 6
    cagr, reason, msg = trailing_cagr_with_reason(series, years=5)
    assert cagr is None
    assert reason == "insufficient_data"
    assert "6" in msg and "5-year" in msg


def test_trailing_cagr_picks_up_different_growth_in_window():
    series = [1000, 1050, 1100, 1300, 1550, 1850]  # accelerates in recent years
    cagr_3y, reason_3y, _ = trailing_cagr_with_reason(series, years=3)
    cagr_5y, reason_5y, _ = trailing_cagr_with_reason(series, years=5)
    assert reason_3y == "ok" and reason_5y == "ok"
    assert cagr_3y > cagr_5y


def test_trailing_cagr_with_only_4_years_of_history_gives_3y_cagr():
    # This is the realistic case: yfinance gives ~4 FY of history, so only a
    # 3-year trailing CAGR (4 data points) is ever available, never a 5-year one.
    series = [1000, 1100, 1210, 1331]  # exactly 4 periods, 10% CAGR
    cagr_3y, reason_3y, _ = trailing_cagr_with_reason(series, years=3)
    assert reason_3y == "ok"
    assert cagr_3y == pytest.approx(0.10, rel=1e-3)
    cagr_5y, reason_5y, _ = trailing_cagr_with_reason(series, years=5)
    assert reason_5y == "insufficient_data"


# ---------------------------------------------------------------------------
# estimate_cost_of_debt
# ---------------------------------------------------------------------------

def test_estimate_cost_of_debt_basic():
    # Interest expense 80, Total debt 1000 -> 8% effective cost of debt
    assert estimate_cost_of_debt(80, 1000) == pytest.approx(0.08)


def test_estimate_cost_of_debt_handles_negative_interest_sign_convention():
    assert estimate_cost_of_debt(-80, 1000) == pytest.approx(0.08)


def test_estimate_cost_of_debt_none_when_inputs_missing():
    assert estimate_cost_of_debt(None, 1000) is None
    assert estimate_cost_of_debt(80, None) is None
    assert estimate_cost_of_debt(80, 0) is None
    assert estimate_cost_of_debt(80, -100) is None


# ---------------------------------------------------------------------------
# compute_wacc
# ---------------------------------------------------------------------------

def test_compute_wacc_basic():
    # Ke=15%, Kd=8%, tax=25%, E=8000, D=2000
    # E/V=0.8, D/V=0.2 -> WACC = 0.8*0.15 + 0.2*0.08*0.75 = 0.12 + 0.012 = 0.132
    wacc = compute_wacc(ke=0.15, kd=0.08, tax_rate=0.25, market_value_equity=8000, market_value_debt=2000)
    assert wacc == pytest.approx(0.132)


def test_compute_wacc_all_equity_equals_ke():
    wacc = compute_wacc(ke=0.14, kd=0.08, tax_rate=0.25, market_value_equity=10000, market_value_debt=0)
    assert wacc == pytest.approx(0.14)


def test_compute_wacc_raises_on_zero_total_value():
    with pytest.raises(ValueError, match="must be positive"):
        compute_wacc(ke=0.14, kd=0.08, tax_rate=0.25, market_value_equity=0, market_value_debt=0)


# ---------------------------------------------------------------------------
# sensitivity_grid
# ---------------------------------------------------------------------------

from reverse_dcf import sensitivity_grid


def test_sensitivity_grid_shape_and_round_trip():
    current_flow = 1000
    discount_rates = [0.10, 0.12, 0.14]
    terminal_growths = [0.03, 0.04, 0.05]
    # Build a target value using the middle cell's own assumptions, at a known growth -
    # that cell should round-trip back to the known growth exactly.
    known_growth = 0.09
    target_value, _, _ = value_at_growth(current_flow, known_growth, 0.12, 0.04, 5)
    grid = sensitivity_grid(current_flow, target_value, discount_rates, terminal_growths, 5)
    assert len(grid) == 3
    assert all(len(row) == 3 for row in grid)
    assert grid[1][1] == pytest.approx(known_growth, abs=1e-4)


def test_sensitivity_grid_none_when_discount_rate_not_above_terminal_growth():
    grid = sensitivity_grid(1000, 8000, [0.03], [0.04], 5)
    assert grid == [[None]]


def test_sensitivity_grid_higher_terminal_growth_needs_lower_required_cagr():
    # For a fixed discount rate, a higher assumed terminal growth should let a
    # lower explicit-period CAGR still reach the same target value.
    current_flow, target_value, r, years = 1000, 20000, 0.12, 5
    grid = sensitivity_grid(current_flow, target_value, [r], [0.02, 0.04, 0.06], years)
    row = grid[0]
    assert all(v is not None for v in row)
    assert row[0] > row[1] > row[2]


# ---------------------------------------------------------------------------
# value_at_growth_exit_multiple / solve_implied_cagr_exit_multiple / sensitivity_grid_exit_multiple
# ---------------------------------------------------------------------------

from reverse_dcf import (
    value_at_growth_exit_multiple,
    solve_implied_cagr_exit_multiple,
    sensitivity_grid_exit_multiple,
)


def test_exit_multiple_value_matches_manual_calc():
    # current_flow=100, g=10%, r=12%, exit_multiple=15x, 5 years
    v, pv_tv, tv = value_at_growth_exit_multiple(100, 0.10, 0.12, 15, 5)
    flow_5 = 100 * 1.10 ** 5
    manual_tv = flow_5 * 15
    manual_pv_tv = manual_tv / (1.12 ** 5)
    manual_pv_explicit = sum(100 * 1.10 ** t / 1.12 ** t for t in range(1, 6))
    assert tv == pytest.approx(manual_tv, rel=1e-9)
    assert pv_tv == pytest.approx(manual_pv_tv, rel=1e-9)
    assert v == pytest.approx(manual_pv_explicit + manual_pv_tv, rel=1e-9)


def test_exit_multiple_raises_on_nonpositive_discount_rate():
    with pytest.raises(ValueError, match="must be positive"):
        value_at_growth_exit_multiple(100, 0.10, 0.0, 15, 5)
    with pytest.raises(ValueError, match="must be positive"):
        value_at_growth_exit_multiple(100, 0.10, -0.02, 15, 5)


def test_solve_exit_multiple_round_trips():
    current_flow, r, multiple, years = 100, 0.13, 18, 5
    known_growth = 0.07
    target_value, _, _ = value_at_growth_exit_multiple(current_flow, known_growth, r, multiple, years)
    solved = solve_implied_cagr_exit_multiple(current_flow, target_value, r, multiple, years)
    assert solved == pytest.approx(known_growth, abs=1e-4)


def test_solve_exit_multiple_raises_on_nonpositive_current_flow():
    with pytest.raises(ValueError, match="zero or negative"):
        solve_implied_cagr_exit_multiple(0, 10000, 0.13, 18, 5)


def test_sensitivity_grid_exit_multiple_shape_and_round_trip():
    current_flow, r, years = 100, 0.13, 5
    known_growth = 0.06
    target_value, _, _ = value_at_growth_exit_multiple(current_flow, known_growth, r, 20, years)
    grid = sensitivity_grid_exit_multiple(current_flow, target_value, [r], [15, 20, 25], years)
    assert len(grid) == 1 and len(grid[0]) == 3
    assert grid[0][1] == pytest.approx(known_growth, abs=1e-4)


def test_sensitivity_grid_exit_multiple_higher_multiple_needs_lower_cagr():
    current_flow, target_value, r, years = 100, 3000, 0.13, 5
    grid = sensitivity_grid_exit_multiple(current_flow, target_value, [r], [10, 20, 30], years)
    row = grid[0]
    assert all(v is not None for v in row)
    assert row[0] > row[1] > row[2]
