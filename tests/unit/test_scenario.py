"""src/analysis/scenario.py — 5년 시나리오 + 스트레스 테스트 검증."""
from __future__ import annotations

from src.analysis.scenario import project_5y_scenarios, stress_test


def test_project_5y_scenarios_has_three_cases_ordered():
    out = project_5y_scenarios(
        price_man=100000, recent_annual_growth_pct=5.0,
        equity_man=50000, loan_man=50000,
    )
    assert set(out.keys()) == {"낙관", "중립", "비관"}
    # 낙관 성장률 > 중립 > 비관 (반대 방향 하락)
    assert out["낙관"]["growth_pct_annual"] > out["중립"]["growth_pct_annual"] > out["비관"]["growth_pct_annual"]
    assert out["낙관"]["future_price_man"] > out["비관"]["future_price_man"]


def test_project_5y_scenarios_zero_equity_gives_zero_roi():
    out = project_5y_scenarios(
        price_man=100000, recent_annual_growth_pct=5.0,
        equity_man=0, loan_man=100000,
    )
    for scenario in out.values():
        assert scenario["roi_annual_pct"] == 0.0


def test_project_5y_scenarios_invalid_price_returns_empty():
    assert project_5y_scenarios(0, 5.0, 50000, 50000) == {}


def test_stress_test_breakeven_drop_matches_ltv():
    # loan/price = 0.5 → breakeven_drop_pct = (0.5 - 1) * 100 = -50%
    out = stress_test(price_man=100000, loan_man=50000, equity_man=50000)
    assert out["breakeven_drop_pct"] == -50.0


def test_stress_test_price_drop_reduces_equity():
    out = stress_test(price_man=100000, loan_man=50000, equity_man=50000, price_drop_pct=-20)
    assert out["scenario_price_man"] == 80000
    assert out["equity_remaining_man"] == 30000
    assert out["equity_loss_pct"] == 40.0


def test_stress_test_price_crash_floors_equity_at_zero():
    out = stress_test(price_man=100000, loan_man=90000, equity_man=10000, price_drop_pct=-30)
    assert out["equity_remaining_man"] == 0
