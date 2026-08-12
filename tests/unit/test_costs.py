"""src/analysis/costs.py — 취득세/중개수수료/정책대출 적격성 검증."""
from __future__ import annotations

from src.analysis import costs


def test_acquisition_tax_brackets():
    # 6억 이하: 1.1%
    assert costs.acquisition_tax_man(50000, "무주택") == round(50000 * 0.011)
    # 6~9억: 6억까지 1.1% + 초과분 1.5%
    tax_75000 = costs.acquisition_tax_man(75000, "무주택")
    assert tax_75000 == round(60000 * 0.011 + 15000 * 0.015)
    # 9억 초과: 3.5%
    assert costs.acquisition_tax_man(100000, "무주택") == round(100000 * 0.035)


def test_acquisition_tax_first_time_buyer_deduction():
    normal = costs.acquisition_tax_man(50000, "무주택", first_time_buyer=False)
    ftb = costs.acquisition_tax_man(50000, "무주택", first_time_buyer=True)
    assert ftb == max(0, normal - 200)


def test_acquisition_tax_multihome_and_one_house_variants_flat_rate():
    # 2026-07 대책: 다주택/1주택(모든 변형)은 조정지역 구분 없이 일괄 8%
    assert costs.acquisition_tax_man(50000, "다주택") == round(50000 * 0.08)
    assert costs.acquisition_tax_man(50000, "1주택") == round(50000 * 0.08)
    assert costs.acquisition_tax_man(50000, "1주택(처분조건부)") == round(50000 * 0.08)
    assert costs.acquisition_tax_man(50000, "1주택(미처분)") == round(50000 * 0.08)


def test_broker_fee_cap_under_5eok():
    # 5억 이하 0.6%, 25만원 한도
    assert costs.broker_fee_man(50000) == 250  # 0.6% of 5억=300 > cap 250
    assert costs.broker_fee_man(10000) == round(10000 * 0.006)  # cap 미적용


def test_broker_fee_higher_brackets():
    assert costs.broker_fee_man(70000) == round(70000 * 0.005)   # 5~9억
    assert costs.broker_fee_man(120000) == round(120000 * 0.004)  # 9~15억


def test_total_acquisition_cost_sums_components():
    out = costs.total_acquisition_cost_man(70000, "무주택")
    assert out["total"] == out["acquisition_tax"] + out["broker_fee"] + out["registration_etc"]


def test_didimdol_eligible_within_limits():
    r = costs.check_didimdol(annual_income_man=5000, price_man=40000, ownership="무주택")
    assert r["eligible"] is True
    assert r["max_loan_man"] == 25000


def test_didimdol_ineligible_over_income():
    r = costs.check_didimdol(annual_income_man=9000, price_man=40000, ownership="무주택")
    assert r["eligible"] is False
    assert "연소득" in r["reason"]


def test_bogeumjari_ineligible_multihome():
    r = costs.check_bogeumjari(annual_income_man=5000, price_man=50000, ownership="다주택")
    assert r["eligible"] is False
    assert r["reason"] == "다주택"


def test_best_policy_loan_picks_higher_limit():
    # 신혼: 디딤돌 4억 vs 보금자리 4억 (둘 다 적격이면 first-max 선택, 여기선 didimdol 4억=bogeumjari 4억)
    out = costs.best_policy_loan(annual_income_man=8000, price_man=55000,
                                  ownership="무주택", is_newlywed=True)
    assert out["eligible"] is True
    assert out["max_loan_man"] == max(
        out["all_results"]["디딤돌"]["max_loan_man"],
        out["all_results"]["보금자리"]["max_loan_man"],
    )


def test_best_policy_loan_none_eligible():
    out = costs.best_policy_loan(annual_income_man=20000, price_man=100000, ownership="다주택")
    assert out["eligible"] is False
    assert out["name"] is None
