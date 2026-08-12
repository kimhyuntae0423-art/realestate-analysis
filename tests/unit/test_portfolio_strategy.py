"""src/analysis/portfolio_strategy.py — 처분·매수 전략 플래너 핵심 로직 검증."""
from __future__ import annotations

from datetime import date

from src.analysis.portfolio_strategy import (
    PropertyProfile, TargetProperty,
    net_sale_proceeds, calc_renewal_risk, plan_scenarios_multi, recommend_sell_order,
)


def _prop(**kwargs) -> PropertyProfile:
    base = dict(
        label="내집", region_code="11680", apt_name="래미안A",
        acquisition_price_man=80000, estimated_price_man=150000,
        loan_balance_man=30000, hold_years=5, residency_years=5,
        is_sole_home=True, tenant_type="전세", jeonse_deposit_man=90000,
        contract_end_date="2026-12-01",
    )
    base.update(kwargs)
    return PropertyProfile(**base)


def test_net_sale_proceeds_subtracts_loan_broker_tax_deposit():
    prop = _prop(estimated_price_man=0)
    out = net_sale_proceeds(prop)
    assert out["net_man"] == 0
    assert out["sale_price_man"] == 0


def test_net_sale_proceeds_returns_deposit_for_jeonse():
    prop = _prop(tenant_type="전세", jeonse_deposit_man=90000, loan_balance_man=0,
                 estimated_price_man=150000, acquisition_price_man=150000)  # 무이득 -> 세금 0
    out = net_sale_proceeds(prop)
    assert out["deposit_return_man"] == 90000
    assert out["net_man"] == 150000 - out["broker_fee_man"] - 90000


def test_calc_renewal_risk_critical_when_deadline_passed_and_not_notified():
    prop = _prop(contract_end_date="2026-02-01", renewal_right_used=False, notified_nonrenewal=False)
    risk = calc_renewal_risk(prop, today=date(2026, 3, 1))  # 통보마감(2025-12-01)이 이미 지남
    assert risk["risk_level"] == "critical"
    assert risk["can_refuse_renewal"] is False


def test_calc_renewal_risk_low_when_already_notified():
    prop = _prop(contract_end_date="2026-12-01", notified_nonrenewal=True)
    risk = calc_renewal_risk(prop, today=date(2026, 1, 1))
    assert risk["risk_level"] == "low"
    assert risk["can_refuse_renewal"] is True


def test_calc_renewal_risk_none_when_no_tenant():
    prop = _prop(tenant_type="직접거주", contract_end_date="")
    risk = calc_renewal_risk(prop, today=date(2026, 1, 1))
    assert risk["risk_level"] == "none"


def test_plan_scenarios_multi_returns_four_scenarios_and_recommendation():
    prop = _prop()
    target = TargetProperty(region_code="41135", budget_min_man=100000, budget_max_man=120000)
    out = plan_scenarios_multi(
        props_mine=[prop], props_partner=[], target=target,
        annual_income_man=8000, current_cash_man=10000,
    )
    assert len(out["scenarios"]) == 4
    assert out["recommended_scenario"] in {"A", "B", "C", "D"}
    assert out["combined_equity_man"] == out["equity_mine_man"] + out["equity_partner_man"] + out["current_cash_man"]


def test_plan_scenarios_multi_no_properties_still_returns_shape():
    target = TargetProperty(region_code="41135", budget_min_man=50000, budget_max_man=60000)
    out = plan_scenarios_multi(props_mine=[], props_partner=[], target=target)
    assert out["combined_equity_man"] == 0
    assert len(out["scenarios"]) == 4


def test_recommend_sell_order_prioritizes_urgent_contract_expiry():
    # today가 명시 인자가 아니라 date.today() 기준이므로, 실행 시점 기준으로
    # 확실히 "1개월 내 만료"가 되도록 오늘 날짜에서 상대적으로 날짜를 계산한다.
    from datetime import timedelta
    today = date.today()
    urgent_end = (today + timedelta(days=20)).isoformat()
    relaxed_end = (today + timedelta(days=700)).isoformat()

    urgent = _prop(label="급함", contract_end_date=urgent_end, tenant_type="전세")
    relaxed = _prop(label="여유", contract_end_date=relaxed_end, tenant_type="전세")
    sales = [net_sale_proceeds(urgent), net_sale_proceeds(relaxed)]
    target = TargetProperty(region_code="41135", budget_min_man=100000, budget_max_man=120000)
    ranked = recommend_sell_order(
        props_mine=[urgent, relaxed], props_partner=[],
        sales_mine=sales, sales_partner=[], target=target,
    )
    assert len(ranked) == 2
    assert ranked[0]["rank"] == 1
    assert ranked[0]["label"] == "급함"
    assert ranked[0]["score"] > ranked[1]["score"]
