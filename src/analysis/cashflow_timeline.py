"""시기별 처분·매수 타임라인 + 자금 흐름 계산

각 부동산의 임대 상태(전세/월세/직거주)와 계약 만료일을 반영하여
시나리오별 월별 이벤트와 누적 자금 흐름을 계산한다.
모든 금액 만원.
"""
from __future__ import annotations
import calendar
from datetime import date
from typing import Optional


# ── 날짜 유틸 ──────────────────────────────────────────────────
def _add_months(d: date, months: int) -> date:
    m = d.month + months
    y = d.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _earliest_sell_date(prop, today: date) -> date:
    """매도 가능한 가장 빠른 시점 (계약 만료 + 이사 준비)."""
    if prop.tenant_type in ("전세", "월세") and prop.contract_end_date:
        end = date.fromisoformat(prop.contract_end_date)
        return _add_months(end, prop.move_out_buffer_months)
    # 직접거주·공실: 준비 기간 3개월 가정
    return _add_months(today, 3)


# ── 이벤트 생성 헬퍼 ────────────────────────────────────────────
def _ev(d: date, event: str, desc: str, cash_in: float, cash_out: float,
        note: str, category: str) -> dict:
    return {
        "date": d,
        "ym": f"{d.year}-{d.month:02d}",
        "event": event,
        "description": desc,
        "cash_in_man": round(cash_in),
        "cash_out_man": round(cash_out),
        "note": note,
        "category": category,  # "계약만료" | "매도" | "매수" | "임시거주" | "비용"
        "running_balance_man": 0,  # 후처리
    }


def _contract_expiry_event(prop, today: date) -> list[dict]:
    if prop.tenant_type not in ("전세", "월세") or not prop.contract_end_date:
        return []
    end = date.fromisoformat(prop.contract_end_date)
    kind = "전세" if prop.tenant_type == "전세" else "월세"
    dep = prop.jeonse_deposit_man if prop.tenant_type == "전세" else prop.monthly_rent_deposit_man
    events = []

    # 갱신 거절 통보 마감일 (계약 만료 2개월 전)
    import calendar as _cal
    nm, ny = end.month - 2, end.year
    if nm <= 0:
        nm += 12; ny -= 1
    notice_d = date(ny, nm, min(end.day, _cal.monthrange(ny, nm)[1]))
    days_left = (notice_d - today).days

    renewal_used = getattr(prop, "renewal_right_used", False)
    notified     = getattr(prop, "notified_nonrenewal", False)
    locked_end   = date(end.year + 2, end.month, end.day)

    if not renewal_used and not notified:
        if days_left >= 0:
            tag = "⚠️ 긴급" if days_left <= 30 else "📌"
            events.append(_ev(
                d=notice_d,
                event=f"[{prop.label}] {tag} 갱신 거절 통보 마감",
                desc=(
                    f"이 날까지 임차인에게 '계약 갱신 안 함'을 서면 통보해야 합니다. "
                    f"미통보 시 묵시적 갱신 → {locked_end.strftime('%Y-%m-%d')}까지 퇴거 불가"
                ),
                cash_in=0, cash_out=0,
                note=f"내용증명 또는 문자 발송 권장",
                category="갱신주의",
            ))
        else:
            events.append(_ev(
                d=today,
                event=f"[{prop.label}] 🚨 묵시적 갱신 위험",
                desc=(
                    f"통보 마감({notice_d.strftime('%Y-%m-%d')})이 지났고 통보 미완료. "
                    f"임차인 갱신청구 시 {locked_end.strftime('%Y-%m-%d')}까지 매도 불가."
                ),
                cash_in=0, cash_out=0,
                note="즉시 임차인 소통 및 법적 검토 필요",
                category="갱신주의",
            ))

    # 계약 만료 이벤트
    events.append(_ev(
        d=end,
        event=f"[{prop.label}] {kind} 계약 만료",
        desc=f"세입자 퇴거 후 매도 가능 (이사 준비 {prop.move_out_buffer_months}개월)",
        cash_in=0, cash_out=0,
        note=f"보증금 {dep:,.0f}만원 반환 예정 (매도 잔금 처리)",
        category="계약만료",
    ))
    return events


def _sell_event(prop, sell_date: date, sale: dict) -> dict:
    parts = [f"매도가 {sale['sale_price_man']:,.0f}만"]
    if sale.get("loan_repay_man", 0):
        parts.append(f"대출상환 {sale['loan_repay_man']:,.0f}만")
    if sale.get("capital_gains_tax_man", 0):
        parts.append(f"양도세 {sale['capital_gains_tax_man']:,.0f}만")
    if sale.get("deposit_return_man", 0):
        parts.append(f"보증금반환 {sale['deposit_return_man']:,.0f}만")

    net = sale["net_man"]
    return _ev(
        d=sell_date,
        event=f"[{prop.label}] 매도 완료",
        desc=" / ".join(parts),
        cash_in=max(0, net),
        cash_out=max(0, -net),
        note=f"순수령액 {net:,.0f}만원 ({sale.get('tax_note', '')})",
        category="매도",
    )


def _buy_equity_event(target, buy_date: date, equity_needed: float) -> dict:
    return _ev(
        d=buy_date,
        event=f"[{target.label}] 매수 잔금",
        desc=f"목표 예산 {target.budget_max_man:,.0f}만 기준 자기자본 {equity_needed:,.0f}만 지출",
        cash_in=0,
        cash_out=equity_needed,
        note="대출 제외 자기자본 부분만 현금 출금",
        category="매수",
    )


def _interim_rent_event(start: date, months: int, monthly: float) -> dict:
    total = monthly * months
    return _ev(
        d=start,
        event="임시 거주 비용",
        desc=f"월세 {monthly:,.0f}만 × {months}개월",
        cash_in=0,
        cash_out=total,
        note=f"총 임시 거주 비용 {total:,.0f}만원",
        category="임시거주",
    )


# ── 월세 수입 (매도 전까지) ──────────────────────────────────────
def _rental_income_event(prop, today: date, sell_date: date) -> list[dict]:
    if prop.tenant_type != "월세" or prop.monthly_rent_man <= 0:
        return []
    months = max(0, (sell_date.year - today.year) * 12 + (sell_date.month - today.month))
    if months <= 0:
        return []
    total = prop.monthly_rent_man * months
    return [_ev(
        d=today,
        event=f"[{prop.label}] 월세 수입",
        desc=f"{prop.monthly_rent_man:,.0f}만/월 × {months}개월 (매도까지)",
        cash_in=total, cash_out=0,
        note=f"월세 수입 합계 {total:,.0f}만원",
        category="월세수입",
    )]


# ── 메인 타임라인 빌더 (다중 부동산 지원) ─────────────────────────
def build_timeline(
    props_mine: list,
    props_partner: list,
    sales_mine: list[dict],
    sales_partner: list[dict],
    target,
    scenario_label: str = "A",
    today: Optional[date] = None,
    interim_rent_man: float = 0.0,
    target_closing_date: Optional[date] = None,
    equity_needed_man: float = 0.0,
) -> tuple[list[dict], dict]:
    """시나리오별 타임라인 이벤트 + 자금 흐름 반환.

    props_mine / props_partner: PropertyProfile 리스트
    sales_mine / sales_partner: net_sale_proceeds 결과 리스트 (동일 순서)
    equity_needed_man: 신규 매수 시 자기자본 지출액 (매수가 - 대출)
    """
    if today is None:
        today = date.today()

    sc = (scenario_label or "A")[0].upper()
    events: list[dict] = []

    sell_dates_mine    = [_earliest_sell_date(p, today) for p in props_mine]
    sell_dates_partner = [_earliest_sell_date(p, today) for p in props_partner]

    # 월세 수입 이벤트
    for p, sd in zip(props_mine, sell_dates_mine):
        events.extend(_rental_income_event(p, today, sd))
    for p, sd in zip(props_partner, sell_dates_partner):
        events.extend(_rental_income_event(p, today, sd))

    def _add_group_events(props, sell_dates, sales, today_):
        for p, sd in zip(props, sell_dates):
            events.extend(_contract_expiry_event(p, today_))
        for p, sd, sale in zip(props, sell_dates, sales):
            events.append(_sell_event(p, sd, sale))
        return max(sell_dates) if sell_dates else today_

    if sc == "A":
        last_mine    = _add_group_events(props_mine,    sell_dates_mine,    sales_mine,    today)
        last_partner = _add_group_events(props_partner, sell_dates_partner, sales_partner, today)
        all_out = max(last_mine, last_partner) if sell_dates_mine or sell_dates_partner else today
        buy_date = target_closing_date or _add_months(all_out, 2)
        interim_months = max(0, (buy_date.year - all_out.year) * 12
                             + (buy_date.month - all_out.month))
        if interim_rent_man > 0 and interim_months > 0:
            events.append(_interim_rent_event(all_out, interim_months, interim_rent_man))

    elif sc == "B":
        last_mine = _add_group_events(props_mine, sell_dates_mine, sales_mine, today)
        buy_date = target_closing_date or _add_months(last_mine, 2)
        for p, sd in zip(props_partner, sell_dates_partner):
            events.extend(_contract_expiry_event(p, today))
        for p, sd, sale in zip(props_partner, sell_dates_partner, sales_partner):
            late = max(sd, _add_months(buy_date, 1))
            events.append(_sell_event(p, late, sale))

    elif sc == "C":
        last_partner = _add_group_events(props_partner, sell_dates_partner, sales_partner, today)
        buy_date = target_closing_date or _add_months(last_partner, 2)
        for p, sd in zip(props_mine, sell_dates_mine):
            events.extend(_contract_expiry_event(p, today))
        for p, sd, sale in zip(props_mine, sell_dates_mine, sales_mine):
            late = max(sd, _add_months(buy_date, 1))
            events.append(_sell_event(p, late, sale))

    elif sc == "D":
        buy_date = target_closing_date or _add_months(today, 2)
        _add_group_events(props_mine,    sell_dates_mine,    sales_mine,    today)
        _add_group_events(props_partner, sell_dates_partner, sales_partner, today)

    else:
        buy_date = target_closing_date or _add_months(today, 2)

    if equity_needed_man > 0:
        events.append(_buy_equity_event(target, buy_date, equity_needed_man))

    # 날짜 정렬 + 누적 잔고 계산
    events.sort(key=lambda e: (e["date"], e["category"]))
    running = 0.0
    for e in events:
        running += e["cash_in_man"] - e["cash_out_man"]
        e["running_balance_man"] = round(running)

    total_in  = sum(e["cash_in_man"]  for e in events)
    total_out = sum(e["cash_out_man"] for e in events)
    summary = {
        "total_in_man":      round(total_in),
        "total_out_man":     round(total_out),
        "net_cashflow_man":  round(total_in - total_out),
        "buy_date":          buy_date,
        "sell_dates_mine":   sell_dates_mine,
        "sell_dates_partner": sell_dates_partner,
    }
    return events, summary
