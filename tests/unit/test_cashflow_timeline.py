"""src/analysis/cashflow_timeline.py — 처분·매수 타임라인 자금흐름 검증.

PropertyProfile/TargetProperty는 portfolio_strategy.py에 정의됨(공유 데이터 모델).
"""
from __future__ import annotations

from datetime import date

from src.analysis.cashflow_timeline import build_timeline
from src.analysis.portfolio_strategy import PropertyProfile, TargetProperty, net_sale_proceeds


def _prop(**kwargs) -> PropertyProfile:
    base = dict(
        label="내집", region_code="11680", apt_name="래미안A",
        acquisition_price_man=80000, estimated_price_man=150000,
        loan_balance_man=30000, hold_years=5, residency_years=5,
        is_sole_home=True, tenant_type="전세", jeonse_deposit_man=90000,
        contract_end_date="2026-12-01", move_out_buffer_months=2,
    )
    base.update(kwargs)
    return PropertyProfile(**base)


def _target(**kwargs) -> TargetProperty:
    base = dict(region_code="41135", label="목표", budget_min_man=100000, budget_max_man=120000)
    base.update(kwargs)
    return TargetProperty(**base)


def test_scenario_a_running_balance_matches_cumulative_sum():
    prop = _prop()
    sale = net_sale_proceeds(prop)
    target = _target()
    events, summary = build_timeline(
        props_mine=[prop], props_partner=[], sales_mine=[sale], sales_partner=[],
        target=target, scenario_label="A", today=date(2026, 1, 1),
        equity_needed_man=20000,
    )
    assert events, "이벤트가 하나도 생성되지 않음"
    running = 0.0
    for e in events:
        running += e["cash_in_man"] - e["cash_out_man"]
        assert e["running_balance_man"] == round(running)
    assert summary["total_in_man"] - summary["total_out_man"] == summary["net_cashflow_man"]


def test_sell_event_schedules_capital_gains_tax_two_months_later():
    # 1세대1주택 비과세 조건을 깨서 양도세가 실제로 발생하도록 다주택 설정
    prop = _prop(is_sole_home=False, hold_years=5, residency_years=0,
                 acquisition_price_man=30000, estimated_price_man=200000)
    sale = net_sale_proceeds(prop)
    assert sale["capital_gains_tax_man"] > 0, "테스트 전제: 양도세가 0보다 커야 함"

    target = _target()
    events, _ = build_timeline(
        props_mine=[prop], props_partner=[], sales_mine=[sale], sales_partner=[],
        target=target, scenario_label="A", today=date(2026, 1, 1),
    )
    tax_events = [e for e in events if e["category"] == "비용" and "양도세" in e["event"]]
    sell_events = [e for e in events if e["category"] == "매도"]
    assert len(tax_events) == 1
    assert len(sell_events) == 1
    delta_months = (tax_events[0]["date"].year - sell_events[0]["date"].year) * 12 + \
                   (tax_events[0]["date"].month - sell_events[0]["date"].month)
    assert delta_months == 2


def test_expired_notice_deadline_flags_urgent_renewal_warning():
    # 계약 만료가 임박(통보 마감이 30일 이내)한 케이스
    today = date(2026, 3, 1)
    prop = _prop(contract_end_date="2026-05-25")  # 통보 마감 = 만료 2개월 전 = 3/25 (오늘로부터 24일)
    sale = net_sale_proceeds(prop)
    target = _target()
    events, _ = build_timeline(
        props_mine=[prop], props_partner=[], sales_mine=[sale], sales_partner=[],
        target=target, scenario_label="A", today=today,
    )
    urgent = [e for e in events if e["category"] == "갱신주의" and "긴급" in e["event"]]
    assert len(urgent) == 1


def test_scenario_d_buys_before_selling():
    prop = _prop()
    sale = net_sale_proceeds(prop)
    target = _target()
    events, summary = build_timeline(
        props_mine=[prop], props_partner=[], sales_mine=[sale], sales_partner=[],
        target=target, scenario_label="D", today=date(2026, 1, 1),
        equity_needed_man=20000,
    )
    buy_events = [e for e in events if e["category"] == "매수"]
    sell_events = [e for e in events if e["category"] == "매도"]
    assert len(buy_events) == 1
    assert buy_events[0]["date"] < sell_events[0]["date"]


def test_no_properties_only_buy_equity_event():
    target = _target()
    events, summary = build_timeline(
        props_mine=[], props_partner=[], sales_mine=[], sales_partner=[],
        target=target, scenario_label="A", today=date(2026, 1, 1),
        equity_needed_man=50000,
    )
    assert len(events) == 1
    assert events[0]["category"] == "매수"
    assert summary["net_cashflow_man"] == -50000
