"""보유 부동산 처분 + 신규 매수 전략 플래너

내 부동산(N채) + 파트너 부동산(M채) -> 합산 매수력 + 4가지 시나리오
모든 금액 만원.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.analysis.capital_gains_tax import capital_gains_tax_man
from src.analysis.costs import broker_fee_man, total_acquisition_cost_man
from src.analysis.loan import loan_capacity_man, dsr_loan_capacity_man, loan_breakdown_man


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
    # 계약갱신청구권
    renewal_right_used: bool = False   # 임차인이 이미 갱신청구권을 사용했는가
    notified_nonrenewal: bool = False   # 임대인이 갱신 거절 통보를 했는가


@dataclass
class TargetProperty:
    """매수 목표 부동산"""
    region_code: str
    label: str = "목표 부동산"
    budget_min_man: float = 0.0
    budget_max_man: float = 0.0
    kb_price_man: float = 0.0   # KB시세 (0이면 budget_max 기준)


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


def calc_renewal_risk(prop: PropertyProfile, today=None) -> dict:
    """계약갱신청구권·묵시적갱신 리스크 계산.

    Returns:
        risk_level: "none" | "low" | "medium" | "high" | "critical"
        notice_deadline: 임대인이 갱신 거절 통보해야 하는 마감일 (계약 만료 2개월 전)
        locked_until: 갱신 시 임차인이 머무를 수 있는 종료일 (계약만료 + 2년)
        days_to_deadline: 통보 마감까지 남은 일수 (음수면 이미 지남)
        message: 사람이 읽을 수 있는 설명
    """
    from datetime import date as _date, timedelta
    import calendar

    if today is None:
        today = _date.today()

    result = {
        "risk_level": "none",
        "notice_deadline": None,
        "locked_until": None,
        "days_to_deadline": None,
        "can_refuse_renewal": False,
        "message": "",
    }

    if prop.tenant_type not in ("전세", "월세") or not prop.contract_end_date:
        result["message"] = "임대 계약 없음 — 갱신 리스크 해당 없음"
        return result

    try:
        end = _date.fromisoformat(prop.contract_end_date)
    except Exception:
        return result

    # 통보 마감일 = 계약 만료 2개월 전
    m = end.month - 2
    y = end.year
    if m <= 0:
        m += 12
        y -= 1
    last = calendar.monthrange(y, m)[1]
    notice_deadline = _date(y, m, min(end.day, last))

    # 갱신 시 임차인 거주 가능 종료일 = 계약 만료 + 2년
    locked_y = end.year + 2
    locked_until = _date(locked_y, end.month, end.day)

    days_to_deadline = (notice_deadline - today).days
    result["notice_deadline"] = notice_deadline
    result["locked_until"] = locked_until
    result["days_to_deadline"] = days_to_deadline

    # 갱신청구권 이미 사용 → 리스크 없음
    if prop.renewal_right_used:
        result["risk_level"] = "low"
        result["can_refuse_renewal"] = True
        result["message"] = (
            "임차인이 계약갱신청구권을 이미 사용했습니다. "
            "계약 만료 후 임차인은 법적으로 연장을 요구할 수 없습니다. "
            f"다만 임대인은 만료 2개월 전({notice_deadline.strftime('%Y-%m-%d')})까지 "
            "퇴거 의사를 통보해야 합니다."
        )
        return result

    # 통보를 이미 했음
    if prop.notified_nonrenewal:
        result["risk_level"] = "low"
        result["can_refuse_renewal"] = True
        result["message"] = (
            "갱신 거절 통보 완료. 임차인은 계약 만료 후 퇴거해야 합니다. "
            "단, 임차인이 갱신청구권을 행사하겠다고 다투는 경우 법적 분쟁 가능성에 대비하세요."
        )
        return result

    # 통보 마감이 지남 + 미통보 → 묵시적 갱신 위험
    if days_to_deadline < 0:
        result["risk_level"] = "critical"
        result["can_refuse_renewal"] = False
        result["message"] = (
            f"⚠️ 위험: 갱신 거절 통보 마감일({notice_deadline.strftime('%Y-%m-%d')})이 "
            f"{abs(days_to_deadline)}일 지났습니다. "
            "임대인이 통보하지 않으면 '묵시적 갱신'이 성립해 임차인은 최대 2년을 더 거주할 수 있습니다. "
            f"이 경우 집을 팔 수 있는 시점이 {locked_until.strftime('%Y-%m-%d')}까지 미뤄질 수 있습니다. "
            "즉시 임차인과 소통하고 법적 대응 여부를 검토하세요."
        )
        return result

    # 통보 마감 30일 이내 → 긴급
    if days_to_deadline <= 30:
        result["risk_level"] = "high"
        result["message"] = (
            f"⚠️ 긴급: 갱신 거절 통보 마감이 {days_to_deadline}일 후({notice_deadline.strftime('%Y-%m-%d')})입니다. "
            "이 기한 내에 임차인에게 서면(문자/내용증명)으로 '계약을 갱신하지 않겠다'는 의사를 전달해야 합니다. "
            "미통보 시 묵시적 갱신으로 2년 더 묶입니다."
        )
        return result

    # 통보 마감 60일 이내 → 주의
    if days_to_deadline <= 60:
        result["risk_level"] = "medium"
        result["message"] = (
            f"주의: 갱신 거절 통보 마감이 {days_to_deadline}일 후({notice_deadline.strftime('%Y-%m-%d')})입니다. "
            "아직 여유가 있지만, 이 기한을 놓치면 임차인이 갱신청구권을 사용해 "
            f"집이 {locked_until.strftime('%Y-%m-%d')}까지 묶일 수 있습니다. "
            "지금 임차인에게 퇴거 의사를 미리 알려두는 것이 좋습니다."
        )
        return result

    # 여유 있음
    result["risk_level"] = "medium" if not prop.renewal_right_used else "low"
    result["message"] = (
        f"갱신 거절 통보 마감일은 {notice_deadline.strftime('%Y-%m-%d')} ({days_to_deadline}일 후)입니다. "
        "임차인이 갱신청구권을 행사하면 계약이 2년 연장될 수 있습니다. "
        f"만약 갱신되면 집을 팔 수 있는 가장 빠른 시점은 {locked_until.strftime('%Y-%m-%d')}이 됩니다. "
        f"매도 계획이 있다면 마감일 전에 반드시 통보하세요."
    )
    return result


def _loan_cap(target: TargetProperty, ownership: str, dsr_cap: float) -> float:
    ref = target.budget_max_man or target.budget_min_man
    kb = target.kb_price_man if target.kb_price_man > 0 else None
    ltv = loan_capacity_man(ref, target.region_code, ownership, kb_price_man=kb)
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

    effective_loan = _loan_cap(target, "무주택", dsr_cap)
    ref_price = target.budget_max_man or target.budget_min_man
    kb_for_breakdown = target.kb_price_man if target.kb_price_man > 0 else None
    target_loan_bd = loan_breakdown_man(
        price_man=ref_price,
        region_code=target.region_code,
        ownership="무주택",
        dsr_cap_man=dsr_cap if dsr_cap > 0 else None,
        kb_price_man=kb_for_breakdown,
    ) if ref_price > 0 else {}

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
        "effective_loan_man": round(effective_loan),
        "max_purchase_power_man": round(combined + effective_loan),
        "target_acquisition_cost": acq_cost,
        "target_loan_breakdown": target_loan_bd,
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
        reasons = []    # 짧은 이유 태그 (표 표시용)
        explains = []   # 풀 문장 설명 (왜 이 집을 먼저/나중에 파야 하는가)

        # ── 1. 계약 만료 긴급도 (30점) ──────────────────────
        if prop.contract_end_date and prop.tenant_type in ("전세", "월세"):
            try:
                end = _date.fromisoformat(prop.contract_end_date)
                months_left = max(0, (end.year - today.year) * 12 + (end.month - today.month))
                kind = "전세" if prop.tenant_type == "전세" else "월세"
                if months_left <= 3:
                    score += 30
                    reasons.append(f"{kind} 계약 {months_left}개월 내 만료")
                    explains.append(
                        f"{kind} 계약이 {months_left}개월 후 만료됩니다. "
                        f"계약이 끝나면 세입자가 나가야 하므로, 이 타이밍에 맞춰 매도를 준비하는 것이 자연스럽습니다. "
                        f"지금 움직이지 않으면 재계약(보통 2년)을 해야 하고, 그러면 전체 계획이 2년 미뤄질 수 있습니다."
                    )
                elif months_left <= 6:
                    score += 20
                    reasons.append(f"{kind} 계약 {months_left}개월 내 만료")
                    explains.append(
                        f"{kind} 계약이 {months_left}개월 후 만료됩니다. "
                        f"지금 매도 준비를 시작하면 계약 만료 시점에 깔끔하게 맞출 수 있습니다. "
                        f"늦게 시작하면 세입자 퇴거 후 공실 기간이 길어져 관리비·대출이자가 계속 나갑니다."
                    )
                elif months_left <= 12:
                    score += 10
                    reasons.append(f"{kind} 계약 {months_left}개월 내 만료")
                    explains.append(
                        f"{kind} 계약이 {months_left}개월 후 만료됩니다. "
                        f"아직 여유가 있지만, 매도 준비(호가 설정·중개 계약 등)는 미리 시작하는 것이 좋습니다."
                    )
                else:
                    reasons.append(f"{kind} 계약 {months_left}개월 여유")
                    explains.append(
                        f"{kind} 계약 만료까지 {months_left}개월이 남아 있습니다. "
                        f"이 집을 먼저 팔려면 세입자와 협의하거나 계약 만료를 기다려야 합니다. "
                        f"다른 물건을 먼저 처분하는 것이 더 현실적일 수 있습니다."
                    )
            except Exception:
                pass
        elif prop.tenant_type == "직접거주":
            score += 5
            reasons.append("직접 거주 중")
            explains.append(
                "현재 직접 거주 중인 집입니다. "
                "이사 날짜를 정하면 바로 매도를 진행할 수 있어 타이밍 조율이 비교적 자유롭습니다. "
                "단, 이사 전 거주지 확보(임시 월세 등)를 먼저 계획해야 합니다."
            )
        elif prop.tenant_type == "공실":
            score += 15
            reasons.append("공실 — 즉시 매도 가능")
            explains.append(
                "현재 공실 상태입니다. 세입자 퇴거를 기다릴 필요 없이 즉시 매물로 내놓을 수 있습니다. "
                "단, 공실 기간이 길어질수록 관리비·대출이자가 손실로 쌓이므로 빠르게 매도하는 것이 유리합니다."
            )

        # ── 1b. 갱신청구권·묵시적갱신 리스크 ────────────────
        renewal = calc_renewal_risk(prop, today)
        item_renewal = renewal  # 나중에 ranked에 포함
        if renewal["risk_level"] == "critical":
            score += 35  # 묵시적 갱신 성립 위험 → 최우선
            reasons.append("묵시적 갱신 위험 (통보 마감 초과)")
            explains.append(renewal["message"])
        elif renewal["risk_level"] == "high":
            score += 25
            reasons.append(f"갱신 거절 통보 마감 {renewal['days_to_deadline']}일 내")
            explains.append(renewal["message"])
        elif renewal["risk_level"] == "medium":
            score += 10
            if renewal["days_to_deadline"] is not None:
                reasons.append(f"갱신청구권 리스크 있음 (마감 {renewal['days_to_deadline']}일 후)")
                explains.append(renewal["message"])
        elif renewal["risk_level"] == "low":
            reasons.append("갱신청구권 리스크 낮음")
            explains.append(renewal["message"])

        # ── 2. 세금 부담 (25점) ──────────────────────────────
        cgt = sale.get("capital_gains_tax_man", 0)
        est = sale.get("sale_price_man", 1) or 1
        net = sale.get("net_man", 0)
        tax_rate = cgt / est
        tax_note = sale.get("tax_note", "")
        if "비과세" in tax_note:
            score += 25
            reasons.append("양도세 비과세")
            explains.append(
                f"양도세가 전액 비과세입니다. ({tax_note}) "
                f"시세 {_fmt(est)} 중 양도차익 전부를 세금 없이 가져갈 수 있습니다. "
                f"비과세 혜택은 보유·거주 요건이 바뀌거나 다른 주택을 먼저 취득하면 사라질 수 있으므로, "
                f"지금 이 상태에서 처분하는 것이 세금 측면에서 최적입니다."
            )
        elif tax_rate < 0.03:
            score += 18
            reasons.append(f"양도세 낮음 ({tax_rate*100:.1f}%)")
            explains.append(
                f"양도세가 시세 대비 {tax_rate*100:.1f}% ({_fmt(cgt)})로 부담이 적습니다. "
                f"세금이 적게 나오는 이 집을 먼저 처분해 깨끗하게 현금화하는 것이 좋습니다."
            )
        elif tax_rate < 0.08:
            score += 10
            reasons.append(f"양도세 중간 ({tax_rate*100:.1f}%)")
            explains.append(
                f"양도세가 시세 대비 {tax_rate*100:.1f}% ({_fmt(cgt)}) 수준입니다. "
                f"세금 부담이 있지만 감당 가능한 범위입니다. "
                f"보유 기간이 늘어날수록 장기보유특별공제가 커지므로, 당장 급하지 않다면 조금 더 기다리는 것도 검토해볼 수 있습니다."
            )
        else:
            score += 3
            reasons.append(f"양도세 높음 ({tax_rate*100:.1f}%)")
            explains.append(
                f"양도세가 시세 대비 {tax_rate*100:.1f}% ({_fmt(cgt)})로 상당합니다. "
                f"이 집을 나중에 팔면 다른 집의 일시적 2주택 비과세 특례를 활용하거나 "
                f"장기보유공제를 더 쌓을 수 있어 세금을 줄일 여지가 있습니다. "
                f"세무사 상담으로 최적 매도 시점을 확인하세요."
            )

        # ── 3. 순수령액 크기 (20점) ──────────────────────────
        ref = target.budget_min_man or 1
        if net < ref * 0.3:
            score += 20
            reasons.append(f"순수령액 소규모 ({_fmt(net)})")
            explains.append(
                f"이 집을 팔면 {_fmt(net)}이 생깁니다. "
                f"목표 예산의 30% 미만으로, 이것만으로는 새 집을 살 수 없지만 "
                f"계약금·중도금을 낼 수 있는 초기 실탄이 됩니다. "
                f"먼저 팔아 계약을 걸어두고, 더 큰 집의 매도 대금으로 잔금을 치르는 구조가 안전합니다."
            )
        elif net < ref * 0.6:
            score += 12
            reasons.append(f"순수령액 중간 ({_fmt(net)})")
            explains.append(
                f"이 집을 팔면 {_fmt(net)}이 생깁니다. "
                f"단독으로 새 집을 살 수는 없지만, 다른 매도 대금과 합치면 잔금을 충당할 수 있습니다."
            )
        else:
            score += 5
            reasons.append(f"순수령액 대규모 ({_fmt(net)})")
            explains.append(
                f"이 집을 팔면 {_fmt(net)}이 생깁니다. "
                f"순수령액이 크기 때문에 이 돈이 새 집 잔금의 핵심 재원입니다. "
                f"잔금일에 맞춰 이 집의 매도 잔금이 들어오도록 일정을 조율하면 "
                f"다른 자금을 건드릴 필요가 없습니다."
            )

        # ── 4. 비과세 요건 안정성 (25점) ─────────────────────
        if prop.is_sole_home and prop.hold_years >= 2 and prop.residency_years >= 2:
            score += 25
            reasons.append("1주택 비과세 요건 충족")
            explains.append(
                f"1세대 1주택 비과세 요건(보유 {prop.hold_years:.0f}년, "
                f"실거주 {prop.residency_years:.0f}년)을 갖추고 있습니다. "
                f"비과세 상태에서 팔면 세금이 없어 순수령액이 가장 극대화됩니다. "
                f"단, 다른 주택을 먼저 취득하거나 보유 형태가 바뀌면 이 혜택이 사라질 수 있으니 "
                f"순서를 바꾸기 전에 세무사 확인이 필요합니다."
            )
        elif prop.hold_years < 2:
            score = max(0, score - 10)
            reasons.append(f"보유 {prop.hold_years:.1f}년 — 단기양도 주의")
            explains.append(
                f"보유 기간이 {prop.hold_years:.1f}년으로 2년 미만입니다. "
                f"2년 미만 보유 시 단기양도 세율(1년 미만 77%, 1~2년 66%)이 적용되어 "
                f"세금 부담이 크게 늘어납니다. "
                f"2년을 채운 뒤 매도하면 일반세율이 적용되므로, "
                f"가능하다면 {24 - int(prop.hold_years*12)}개월 더 기다리는 것을 검토하세요."
            )

        return score, reasons, explains, item_renewal

    ranked = []
    for prop, sale, owner in all_items:
        s, reasons, explains, renewal = _score(prop, sale)
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
            "explains": explains,
            "renewal": renewal,
        })

    ranked.sort(key=lambda x: -x["score"])
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    # 누적 자금 계산
    running = current_cash_man
    for item in ranked:
        running += item["net_man"]
        item["cumulative_cash_man"] = round(running)
        item["can_buy_target"] = running >= target.budget_min_man

    # 전체 전략 요약 문단 생성
    total = len(ranked)
    first_items = [x for x in ranked if x["rank"] == 1]
    last_items  = [x for x in ranked if x["rank"] == total]
    first = first_items[0] if first_items else ranked[0]
    last  = last_items[0]  if last_items  else ranked[-1]

    buy_point = next((x for x in ranked if x["can_buy_target"]), None)
    buy_after = f"{buy_point['label']}을(를) 매도한 직후 (누적 {_fmt(buy_point['cumulative_cash_man'])}) 새 집 계약이 가능합니다." if buy_point else "전체 매도 후 신규 매수를 진행해야 합니다."

    narrative_lines = [
        f"**추천 순서: {' → '.join(x['label'] for x in ranked)}**",
        "",
        f"**{first['owner']}의 {first['label']}를 가장 먼저 파는 이유:**",
    ]
    for ex in first["explains"]:
        narrative_lines.append(f"- {ex}")

    if total > 1:
        narrative_lines += [
            "",
            f"**{last['owner']}의 {last['label']}를 마지막에 파는 이유:**",
        ]
        for ex in last["explains"]:
            narrative_lines.append(f"- {ex}")

    if current_cash_man > 0:
        narrative_lines += [
            "",
            f"**현재 보유 현금 {_fmt(current_cash_man)}의 역할:**",
            f"- 첫 번째 매도 전에도 이 돈으로 계약금을 낼 수 있어 "
            f"원하는 매물이 나왔을 때 바로 잡을 수 있습니다.",
        ]

    narrative_lines += ["", f"**자금 확보 시점:** {buy_after}"]

    summary = "\n".join(narrative_lines)
    for item in ranked:
        item["strategy_summary"] = summary

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
