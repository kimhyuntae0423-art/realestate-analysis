"""보유 부동산 처분 + 신규 매수 전략 플래너

내 부동산(N채) + 파트너 부동산(M채) -> 합산 매수력 + 4가지 시나리오
모든 금액 만원.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.analysis.capital_gains_tax import capital_gains_tax_man
from src.analysis.costs import broker_fee_man, total_acquisition_cost_man
from src.analysis.loan import loan_capacity_man, dsr_loan_capacity_man


def _fmt(v: float) -> str:
    """만원 값을 억/만 단위 문자열로 변환."""
    return f"{v/10000:.1f}억" if abs(v) >= 10000 else f"{v:,.0f}만"


@dataclass
class PropertyProfile:
    """보유 부동산 정보"""
    label: str
    region_code: str
    apt_name: str = ""
    acquisition_price_man: float = 0.0
    estimated_price_man: float = 0.0
    loan_balance_man: float = 0.0
    hold_years: float = 3.0
    residency_years: float = 2.0
    is_sole_home: bool = True
    is_adjusted_area: bool = True
    multihome_surcharge: bool = False
    # 임대 현황
    tenant_type: str = "직접거주"
    jeonse_deposit_man: float = 0.0
    monthly_rent_deposit_man: float = 0.0
    monthly_rent_man: float = 0.0
    contract_end_date: str = ""
    move_out_buffer_months: int = 2


@dataclass
class TargetProperty:
    """매수 목표 부동산"""
    region_code: str
    label: str = "목표 부동산"
    budget_min_man: float = 0.0
    budget_max_man: float = 0.0


def net_sale_proceeds(prop: PropertyProfile) -> dict:
    """매도 순수령액 = 시세 - 대출상환 - 중개비 - 양도세 - 보증금반환"""
    sale = prop.estimated_price_man
    if sale <= 0:
        return {
            "net_man": 0, "sale_price_man": 0,
            "loan_repay_man": 0, "broker_fee_man": 0,
            "capital_gains_tax_man": 0, "deposit_return_man": 0,
            "tenant_type": prop.tenant_type, "tax_note": "-",
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

    deposit_return = 0.0
    if prop.tenant_type == "전세":
        deposit_return = prop.jeonse_deposit_man
    elif prop.tenant_type == "월세":
        deposit_return = prop.monthly_rent_deposit_man

    net = sale - prop.loan_balance_man - broker - cgt - deposit_return

    return {
        "net_man": round(net),
        "sale_price_man": round(sale),
        "loan_repay_man": round(prop.loan_balance_man),
        "broker_fee_man": round(broker),
        "capital_gains_tax_man": cgt,
        "deposit_return_man": round(deposit_return),
        "tenant_type": prop.tenant_type,
        "tax_note": tax_info["note"],
        "tax_detail": tax_info,
    }


def _loan_cap(target: TargetProperty, ownership: str, dsr_cap: float) -> float:
    ref = target.budget_max_man or target.budget_min_man
    ltv = loan_capacity_man(ref, target.region_code, ownership)
    return min(ltv, dsr_cap) if dsr_cap > 0 else ltv


def _make_sc(target: TargetProperty, dsr_cap: float,
             label: str, desc: str, equity: float, ownership: str,
             risks: list, tips: list) -> dict:
    loan = _loan_cap(target, ownership, dsr_cap)
    ref  = target.budget_max_man or target.budget_min_man
    acq  = total_acquisition_cost_man(ref, ownership)
    mb   = equity + loan
    return {
        "label": label, "description": desc,
        "available_equity_man": round(equity),
        "loan_capacity_man": round(loan),
        "max_budget_man": round(mb),
        "acquisition_tax_man": acq["acquisition_tax"],
        "acq_total_cost_man": acq["total"],
        "ownership_when_buy": ownership,
        "can_afford_target_min": mb >= (target.budget_min_man + acq["total"]),
        "can_afford_target_max": mb >= (target.budget_max_man + acq["total"]),
        "risks": risks, "tips": tips,
    }


def plan_scenarios_multi(
    props_mine: list,
    props_partner: list,
    target: TargetProperty,
    annual_income_man: float = 0.0,
    existing_monthly_payment_man: float = 0.0,
) -> dict:
    """여러 부동산을 보유한 두 사람의 처분·매수 시나리오.

    props_mine: 내 부동산 목록
    props_partner: 파트너 부동산 목록
    """
    sales_mine    = [net_sale_proceeds(p) for p in props_mine]
    sales_partner = [net_sale_proceeds(p) for p in props_partner]

    equity_mine    = sum(s["net_man"] for s in sales_mine)
    equity_partner = sum(s["net_man"] for s in sales_partner)
    combined       = equity_mine + equity_partner
    total_count    = len(props_mine) + len(props_partner)

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

    n_mine    = len(props_mine)
    n_partner = len(props_partner)
    mine_label    = "내 부동산" + (f" ({n_mine}채)" if n_mine > 1 else "")
    partner_label = "파트너 부동산" + (f" ({n_partner}채)" if n_partner > 1 else "")

    def _own_remain(sold: str) -> str:
        remain = n_partner if sold == "mine" else n_mine
        if remain == 0:
            return "무주택"
        if remain == 1:
            return "1주택"
        return "다주택"

    own_a = "무주택"
    own_b = _own_remain("mine")
    own_c = _own_remain("partner")
    own_d = "다주택" if total_count >= 2 else "1주택"

    own_b_tax = "8%" if own_b == "1주택" else "12%"
    own_c_tax = "8%" if own_c == "1주택" else "12%"

    def sc(label, desc, equity, ownership, risks, tips):
        return _make_sc(target, dsr_cap, label, desc, equity, ownership, risks, tips)

    scenarios = [
        sc(
            "A. 전체 매도 -> 신규 매수",
            f"총 {total_count}채 모두 매도 후 무주택으로 신규 매수. 취득세 최저, LTV 최고.",
            equity=combined, ownership=own_a,
            risks=["이사 여러 번 (임시 거주 필요)", "매도 타이밍 분산 -> 자금 묶임"],
            tips=["무주택 LTV 최대 활용", "잔금일 조율로 이사 횟수 최소화"],
        ),
        sc(
            f"B. {mine_label} 먼저 매도 -> 신규 매수 -> {partner_label} 매도",
            f"{mine_label} 먼저 처분, {partner_label}는 신규 취득 후 정리.",
            equity=equity_mine, ownership=own_b,
            risks=[
                f"매수 시 {own_b} 상태 -> 취득세 {own_b_tax} 중과 가능",
                f"{partner_label} 처분 완료까지 다주택 유지비",
                "일시적 2주택 특례: 신규 취득 후 3년 내 처분 필수",
            ],
            tips=[
                "일시적 2주택 특례 적용 시 양도세 비과세 가능",
                f"{mine_label} 순수령액({_fmt(equity_mine)})이 클수록 유리",
            ],
        ),
        sc(
            f"C. {partner_label} 먼저 매도 -> 신규 매수 -> {mine_label} 매도",
            f"{partner_label} 먼저 처분, {mine_label}는 신규 취득 후 정리.",
            equity=equity_partner, ownership=own_c,
            risks=[
                f"매수 시 {own_c} 상태 -> 취득세 {own_c_tax} 중과 가능",
                f"{mine_label} 처분 완료까지 다주택 유지비",
            ],
            tips=[
                f"{partner_label} 순수령액({_fmt(equity_partner)})이 클수록 유리",
                "순수령액 큰 쪽을 마지막에 팔면 자금 압박 감소",
            ],
        ),
        sc(
            "D. 신규 매수 먼저 -> 전체 매도 (고위험)",
            f"신규 매수 후 {total_count}채 순차 처분. 최대 {total_count + 1}주택 상태 발생.",
            equity=combined, ownership=own_d,
            risks=[
                f"취득 시 {own_d} -> 취득세 최중과",
                f"{total_count + 1}채 동시 이자/관리비",
                "매도 지연 시 현금흐름 위기",
            ],
            tips=["자금 여유 충분할 때만 고려", "세무사/법무사 사전 상담 필수"],
        ),
    ]

    recommended = next(
        (s["label"][0] for s in scenarios if s["can_afford_target_min"]), "A"
    )

    return {
        "sales_mine": sales_mine,
        "sales_partner": sales_partner,
        "props_mine": props_mine,
        "props_partner": props_partner,
        "equity_mine_man": round(equity_mine),
        "equity_partner_man": round(equity_partner),
        "combined_equity_man": round(combined),
        "dsr_loan_limit_man": round(dsr_cap),
        "effective_loan_man": round(_loan_cap(target, "무주택", dsr_cap)),
        "max_purchase_power_man": round(combined + _loan_cap(target, "무주택", dsr_cap)),
        "target_acquisition_cost": acq_cost,
        "scenarios": scenarios,
        "recommended_scenario": recommended,
        "prop_a_sale": sales_mine[0] if sales_mine else {},
        "prop_b_sale": sales_partner[0] if sales_partner else {},
    }


# 하위 호환 래퍼
def plan_scenarios(prop_a: PropertyProfile, prop_b: PropertyProfile,
                   target: TargetProperty,
                   annual_income_man: float = 0.0,
                   existing_monthly_payment_man: float = 0.0) -> dict:
    return plan_scenarios_multi(
        props_mine=[prop_a], props_partner=[prop_b],
        target=target,
        annual_income_man=annual_income_man,
        existing_monthly_payment_man=existing_monthly_payment_man,
    )
