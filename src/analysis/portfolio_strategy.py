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
    current_cash_man: float = 0.0,
) -> dict:
    """여러 부동산을 보유한 두 사람의 처분·매수 시나리오.

    props_mine: 내 부동산 목록
    props_partner: 파트너 부동산 목록
    """
    sales_mine    = [net_sale_proceeds(p) for p in props_mine]
    sales_partner = [net_sale_proceeds(p) for p in props_partner]

    equity_mine    = sum(s["net_man"] for s in sales_mine)
    equity_partner = sum(s["net_man"] for s in sales_partner)
    combined       = equity_mine + equity_partner + current_cash_man
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
        "current_cash_man": round(current_cash_man),
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


def recommend_sell_order(
    props_mine: list,
    props_partner: list,
    sales_mine: list,
    sales_partner: list,
    target: TargetProperty,
    current_cash_man: float = 0.0,
) -> list:
    """전략적 매도 순서 추천.

    각 부동산을 점수화해 '먼저 팔면 유리한 순서'로 정렬한다.

    점수 기준 (높을수록 먼저 팔기 유리):
      1. 계약 만료 긴급도   (30점) - 만료일 빠를수록 높음
      2. 세금 부담 낮음     (25점) - 양도세/시세 비율 낮을수록 높음
      3. 순수령액 작음      (20점) - 작은 것 먼저 팔아야 자금 압박 덜함
      4. 비과세 안정성      (25점) - 비과세 확보된 물건 먼저 정리
    """
    from datetime import date as _date

    today = _date.today()
    all_items = (
        [(p, s, "나") for p, s in zip(props_mine, sales_mine)] +
        [(p, s, "파트너") for p, s in zip(props_partner, sales_partner)]
    )

    def _score(prop, sale):
        score = 0
        reasons = []

        # 1. 계약 만료 긴급도 (30점)
        if prop.contract_end_date and prop.tenant_type in ("전세", "월세"):
            try:
                end = _date.fromisoformat(prop.contract_end_date)
                months_left = max(0, (end.year - today.year) * 12 + (end.month - today.month))
                if months_left <= 3:
                    score += 30
                    reasons.append(f"계약 만료 {months_left}개월 이내 — 즉시 매도 필요")
                elif months_left <= 6:
                    score += 20
                    reasons.append(f"계약 만료 {months_left}개월 내 — 조기 매도 권장")
                elif months_left <= 12:
                    score += 10
                    reasons.append(f"계약 만료 {months_left}개월 내")
                else:
                    reasons.append(f"계약 만료까지 {months_left}개월 여유")
            except Exception:
                pass
        elif prop.tenant_type == "직접거주":
            score += 5
            reasons.append("직접 거주 중 — 이사 계획 세우면 바로 매도 가능")
        elif prop.tenant_type == "공실":
            score += 15
            reasons.append("공실 — 즉시 매도 가능")

        # 2. 세금 부담 낮음 (25점)
        cgt = sale.get("capital_gains_tax_man", 0)
        est = sale.get("sale_price_man", 1)
        tax_rate = cgt / est if est > 0 else 0
        tax_note = sale.get("tax_note", "")
        if "비과세" in tax_note:
            score += 25
            reasons.append("양도세 비과세 — 세금 없이 전액 회수")
        elif tax_rate < 0.03:
            score += 18
            reasons.append(f"양도세 부담 낮음 ({tax_rate*100:.1f}%)")
        elif tax_rate < 0.08:
            score += 10
            reasons.append(f"양도세 중간 수준 ({tax_rate*100:.1f}%)")
        else:
            score += 3
            reasons.append(f"양도세 부담 높음 ({tax_rate*100:.1f}%) — 마지막에 팔수록 다른 비과세 활용 여지")

        # 3. 순수령액 크기 (20점) — 작은 것 먼저 팔아 초기 자금 확보
        net = sale.get("net_man", 0)
        ref_price = target.budget_min_man
        if net < ref_price * 0.3:
            score += 20
            reasons.append(f"순수령액 소규모({_fmt(net)}) — 먼저 팔아 초기 계약금 마련")
        elif net < ref_price * 0.6:
            score += 12
            reasons.append(f"순수령액 중간({_fmt(net)})")
        else:
            score += 5
            reasons.append(f"순수령액 대규모({_fmt(net)}) — 나중에 팔아 잔금 충당")

        # 4. 비과세 유지 안정성 (25점)
        if prop.is_sole_home and prop.hold_years >= 2 and prop.residency_years >= 2:
            score += 25
            reasons.append("1주택 비과세 요건 충족 — 팔수록 손해 없음")
        elif prop.hold_years < 2:
            score -= 10
            score = max(0, score)
            reasons.append(f"보유 {prop.hold_years:.1f}년 — 비과세 미충족, 단기양도 세율 적용 주의")

        return score, reasons

    ranked = []
    for i, (prop, sale, owner) in enumerate(all_items):
        s, reasons = _score(prop, sale)
        ranked.append({
            "rank": 0,
            "owner": owner,
            "label": prop.label,
            "net_man": sale.get("net_man", 0),
            "tax_man": sale.get("capital_gains_tax_man", 0),
            "tax_note": sale.get("tax_note", "-"),
            "tenant_type": prop.tenant_type,
            "contract_end_date": prop.contract_end_date,
            "score": s,
            "reasons": reasons,
        })

    ranked.sort(key=lambda x: -x["score"])
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    # 누적 자금 계산 (매도 순서대로)
    running = current_cash_man
    for item in ranked:
        running += item["net_man"]
        item["cumulative_cash_man"] = round(running)
        needed = target.budget_min_man
        item["can_buy_target"] = running >= needed

    return ranked


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
