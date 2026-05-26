"""5년 시나리오 + 스트레스 테스트

낙관/중립/비관 가정으로 매도가 예상 + 자기자본 수익률 계산.
금리 인상 / 가격 하락 시 자기자본 잔존율 시뮬레이션.
모든 금액 만원.
"""
from __future__ import annotations
import numpy as np


def project_5y_scenarios(price_man: float,
                          recent_annual_growth_pct: float,
                          equity_man: float,
                          loan_man: float,
                          interest_rate_pct: float = 4.5,
                          loan_years: int = 30,
                          years_forward: int = 5) -> dict:
    """5년 후 매도 시나리오별 자기자본 수익.

    낙관: 최근 상승률 × 1.5
    중립: 최근 상승률
    비관: 최근 상승률 × -0.5 (반대 방향, 약한 하락)
    """
    if price_man <= 0:
        return {}

    scenarios = {
        "낙관": recent_annual_growth_pct * 1.5,
        "중립": recent_annual_growth_pct,
        "비관": min(recent_annual_growth_pct * -0.5, -1.0),
    }

    # 5년간 누적 이자 (원리금균등 가정, 30년)
    r = interest_rate_pct / 100 / 12
    n = loan_years * 12
    if r > 0 and loan_man > 0:
        monthly_payment = loan_man * r * (1 + r) ** n / ((1 + r) ** n - 1)
    else:
        monthly_payment = loan_man / n if loan_man > 0 else 0

    total_payment_5y = monthly_payment * 12 * years_forward
    # 5년 후 잔존 원금
    months_paid = 12 * years_forward
    if r > 0 and loan_man > 0:
        remaining_principal = loan_man * (1 + r) ** n - monthly_payment * ((1 + r) ** months_paid - 1) / r
        remaining_principal = loan_man * ((1 + r) ** n - (1 + r) ** months_paid) / ((1 + r) ** n - 1)
    else:
        remaining_principal = max(0, loan_man - monthly_payment * months_paid)

    interest_paid = total_payment_5y - (loan_man - remaining_principal)

    out = {}
    for name, growth_pct in scenarios.items():
        future_price = price_man * (1 + growth_pct / 100) ** years_forward
        # 매도 시 자기자본 = 매도가 - 잔존원금 - 5년간 이자비용
        equity_at_exit = future_price - remaining_principal - interest_paid
        # 추가로 양도세는 일단 0 (1세대 1주택 비과세 가정 등 복잡)
        roi_total = (equity_at_exit - equity_man) / equity_man * 100 if equity_man > 0 else 0
        if equity_man <= 0:
            roi_annual = 0.0
        elif equity_at_exit <= 0:
            # 자기자본 전손: 음수 분수승은 complex가 되므로 -100%로 클램프
            roi_annual = -100.0
        else:
            roi_annual = ((equity_at_exit / equity_man) ** (1/years_forward) - 1) * 100

        out[name] = {
            "growth_pct_annual": round(growth_pct, 2),
            "future_price_man": round(future_price),
            "remaining_loan_man": round(remaining_principal),
            "total_interest_5y_man": round(interest_paid),
            "monthly_payment_man": round(monthly_payment),
            "equity_at_exit_man": round(equity_at_exit),
            "roi_total_pct": round(roi_total, 1),
            "roi_annual_pct": round(roi_annual, 1),
        }
    return out


def stress_test(price_man: float, loan_man: float, equity_man: float,
                  price_drop_pct: float = 0,
                  rate_bump_pct: float = 0,
                  interest_rate_pct: float = 4.5,
                  loan_years: int = 30) -> dict:
    """가격 하락 + 금리 인상 시 자기자본·월상환액 변화."""
    new_price = price_man * (1 + price_drop_pct / 100)

    # 가격 하락 후 자기자본 잔존 (대출 그대로 가정)
    equity_remaining = max(0, new_price - loan_man)
    equity_loss_pct = (equity_man - equity_remaining) / equity_man * 100 if equity_man > 0 else 0

    # 금리 변경 시 월상환액
    new_rate = (interest_rate_pct + rate_bump_pct) / 100 / 12
    n = loan_years * 12
    if new_rate > 0 and loan_man > 0:
        new_monthly = loan_man * new_rate * (1 + new_rate) ** n / ((1 + new_rate) ** n - 1)
    else:
        new_monthly = loan_man / n if loan_man > 0 else 0

    # 자기자본 소멸 임계점 = 가격이 얼마나 떨어지면 equity=0
    if price_man > 0 and loan_man > 0:
        breakeven_drop_pct = (loan_man / price_man - 1) * 100
    else:
        breakeven_drop_pct = -100.0

    return {
        "scenario_price_man": round(new_price),
        "equity_remaining_man": round(equity_remaining),
        "equity_loss_pct": round(equity_loss_pct, 1),
        "new_monthly_payment_man": round(new_monthly),
        "breakeven_drop_pct": round(breakeven_drop_pct, 1),
    }
