"""보유 부동산 처분 + 신규 매수 전략 플래너

내 부동산(A) + 파트너 부동산(B) → 합산 매수력 + 4가지 순서 시나리오
모든 금액 만원.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from src.analysis.capital_gains_tax import capital_gains_tax_man
from src.analysis.costs import broker_fee_man, total_acquisition_cost_man
from src.analysis.loan import loan_capacity_man, dsr_loan_capacity_man


@dataclass
class PropertyProfile:
    """보유 부동산 정보"""
    label: str                              # '내 아파트' / '파트너 아파트'
    region_code: str                         # 법정동 시군구 5자리
    apt_name: str = ""
    acquisition_price_man: float = 0.0      # 취득가 (만원)
    estimated_price_man: float = 0.0        # 현재 추정 시세 (만원)
    loan_balance_man: float = 0.0           # 현재 대출 잔액 (만원)
    hold_years: float = 3.0                 # 보유기간 (년)
    residency_years: float = 2.0            # 실거주 기간 (년)
    is_sole_home: bool = True               # 이 집만 보유 중 (1주택 비과세 판단)
    is_adjusted_area: bool = True           # 조정대상지역 여부
    multihome_surcharge: bool = False       # 다주택 양도세 중과 여부


@dataclass
class TargetProperty:
    """매수 목표 부동산"""
    region_code: str
    label: str = "목표 부동산"
    budget_min_man: float = 0.0
    budget_max_man: float = 0.0


def net_sale_proceeds(prop: PropertyProfile) -> dict:
    """매도 순수령액 산출.

    순수령액 = 매도가 − 대출상환 − 중개수수료 − 양도세
    """
    sale = prop.estimated_price_man
    if sale <= 0:
        return {
            "net_man": 0,
            "sale_price_man": 0,
            "loan_repay_man": 0,
            "broker_fee_man": 0,
            "capital_gains_tax_man": 0,
            "tax_note": "-",
        }

    broker = broker_fee_man(sale)
    tax_info = capital_gains_tax_man(
        sale_price_man=sale,
        acquisition_price_man=prop.acquisition_price_man,
        hold_years=prop.hold_years,
        residency_years=prop.residency_years,
        is_sole_home=prop.is_sole_home,
        is_adjusted_area=prop.is_adjusted_area,
        multihome_surcharge=prop.multihome_surcharge,
    )
    cgt = tax_info["tax_man"]
    net = sale - prop.loan_balance_man - broker - cgt

    return {
        "net_man": round(net),
        "sale_price_man": round(sale),
        "loan_repay_man": round(prop.loan_balance_man),
        "broker_fee_man": round(broker),
        "capital_gains_tax_man": cgt,
        "tax_note": tax_info["note"],
        "tax_detail": tax_info,
    }


def _loan_capacity(target: TargetProperty, ownership: str,
                   dsr_cap: float) -> float:
    """LTV + DSR 중 작은 값."""
    ref_price = target.budget_max_man or target.budget_min_man
    ltv_loan = loan_capacity_man(ref_price, target.region_code, ownership)
    if dsr_cap > 0:
        return min(ltv_loan, dsr_cap)
    return ltv_loan


def plan_scenarios(
    prop_a: PropertyProfile,
    prop_b: PropertyProfile,
    target: TargetProperty,
    annual_income_man: float = 0.0,
    existing_monthly_payment_man: float = 0.0,
) -> dict:
    """4가지 처분·매수 순서 시나리오 분석.

    A. 둘 다 매도 → 신규 매수  (안전 최우선)
    B. prop_a 매도 → 매수 → prop_b 매도
    C. prop_b 매도 → 매수 → prop_a 매도
    D. 신규 매수 먼저 → 둘 다 매도  (고위험)
    """
    sale_a = net_sale_proceeds(prop_a)
    sale_b = net_sale_proceeds(prop_b)

    combined = sale_a["net_man"] + sale_b["net_man"]

    # DSR 대출 한도
    dsr_cap = 0.0
    if annual_income_man > 0:
        dsr_cap = dsr_loan_capacity_man(
            annual_income_man=annual_income_man,
            existing_monthly_payment_man=existing_monthly_payment_man,
        )

    acq_cost = total_acquisition_cost_man(
        target.budget_max_man or target.budget_min_man,
        ownership="무주택",
    )

    def _make_scenario(
        label: str,
        desc: str,
        equity: float,
        ownership: str,
        risks: list[str],
        tips: list[str],
    ) -> dict:
        loan = _loan_capacity(target, ownership, dsr_cap)
        ref_price = target.budget_max_man or target.budget_min_man
        acq = total_acquisition_cost_man(ref_price, ownership)
        max_budget = equity + loan
        can_afford_min = max_budget >= (target.budget_min_man + acq["total"])
        can_afford_max = max_budget >= (target.budget_max_man + acq["total"])
        return {
            "label": label,
            "description": desc,
            "available_equity_man": round(equity),
            "loan_capacity_man": round(loan),
            "max_budget_man": round(max_budget),
            "acquisition_tax_man": acq["acquisition_tax"],
            "acq_total_cost_man": acq["total"],
            "ownership_when_buy": ownership,
            "can_afford_target_min": can_afford_min,
            "can_afford_target_max": can_afford_max,
            "risks": risks,
            "tips": tips,
        }

    scenarios = [
        _make_scenario(
            label="A. 둘 다 매도 → 신규 매수",
            desc="두 부동산 모두 매도 완료 후 신규 매수. 무주택 취득세(최저), LTV 한도 최고.",
            equity=combined,
            ownership="무주택",
            risks=[
                "이사 2번 (임시 월세 필요)",
                "매도 → 매수 타이밍 갭: 시장 상승 시 기회 손실 가능",
                "전세·월세 계약 기간에 따른 잔금 조율 필요",
            ],
            tips=[
                "임시 거주 비용(월세 × 6~12개월)을 예산에 포함하세요",
                "잔금일 맞추기로 이사를 1회로 줄일 수 있습니다",
                "무주택자 LTV가 가장 유리 — 대출 한도 최대",
            ],
        ),
        _make_scenario(
            label=f"B. {prop_a.label} 매도 → 신규 매수 → {prop_b.label} 매도",
            desc=f"{prop_a.label}만 먼저 매도 후 신규 매수, 잔여 {prop_b.label}는 이후 정리.",
            equity=sale_a["net_man"],
            ownership="1주택",
            risks=[
                "신규 매수 시 1주택 상태 → 취득세 8% 중과 가능 (조정지역)",
                f"{prop_b.label} 매도 전까지 2주택 유지비 발생",
                "일시적 2주택 비과세 요건: 신규 취득 후 3년 내 기존 주택 처분 필수",
            ],
            tips=[
                f"일시적 2주택 특례 적용 시 {prop_b.label} 양도세 비과세 가능 (3년 내 처분)",
                "1주택→신규 취득 취득세 중과 여부: 세무사 확인 권장",
                f"{prop_a.label} 순수령액이 더 클 때 이 시나리오가 유리",
            ],
        ),
        _make_scenario(
            label=f"C. {prop_b.label} 매도 → 신규 매수 → {prop_a.label} 매도",
            desc=f"{prop_b.label}만 먼저 매도 후 신규 매수, 잔여 {prop_a.label}는 이후 정리.",
            equity=sale_b["net_man"],
            ownership="1주택",
            risks=[
                "신규 매수 시 1주택 상태 → 취득세 8% 중과 가능 (조정지역)",
                f"{prop_a.label} 매도 전까지 2주택 유지비",
                "일시적 2주택 비과세 요건: 3년 내 처분 필수",
            ],
            tips=[
                f"일시적 2주택 특례 적용 시 {prop_a.label} 양도세 비과세 가능",
                f"{prop_b.label} 순수령액이 더 클 때 이 시나리오가 유리",
                "순수령액 더 큰 쪽을 나중에 매도하면 자금 압박 감소",
            ],
        ),
        _make_scenario(
            label="D. 신규 매수 먼저 → 두 부동산 매도 (고위험)",
            desc="신규 매수 후 기존 2채 매도. 3주택 상태 발생, 자금·세금 부담 최대.",
            equity=combined,
            ownership="다주택",
            risks=[
                "3주택 취득세: 12% 중과",
                "3채 동시 대출이자 + 관리비 부담",
                "매도 지연 시 현금흐름 심각 위협",
                "다주택 양도세 중과(+20%) 적용 가능",
            ],
            tips=[
                "자금 여유가 충분한 경우에만 고려하세요",
                "세무사·법무사 사전 상담 필수",
                "매도 시점을 미리 계약서에 명시하는 방법도 있음",
            ],
        ),
    ]

    # 추천 순서 (can_afford_target_min True + 위험 최소)
    recommended = next(
        (s["label"][0] for s in scenarios if s["can_afford_target_min"]),
        "A",
    )

    return {
        "prop_a_sale": sale_a,
        "prop_b_sale": sale_b,
        "combined_equity_man": round(combined),
        "dsr_loan_limit_man": round(dsr_cap),
        "ltv_loan_limit_man": round(_loan_capacity(target, "무주택", 0)),
        "effective_loan_man": round(_loan_capacity(target, "무주택", dsr_cap)),
        "max_purchase_power_man": round(combined + _loan_capacity(target, "무주택", dsr_cap)),
        "target_acquisition_cost": acq_cost,
        "scenarios": scenarios,
        "recommended_scenario": recommended,
    }
