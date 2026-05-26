"""부대비용 + 정책대출 적격 판정

부대비용 = 취득세 + 중개수수료 + 등기·법무·이사
정책대출 = 보금자리 / 디딤돌 자동 적격성 체크
모든 금액 단위: 만원
"""
from __future__ import annotations


# ─── 취득세 (2026 기준 일반 매수) ─────────────────────────
def acquisition_tax_man(price_man: float, ownership: str = "무주택",
                          first_time_buyer: bool = False) -> float:
    """매매 취득세 (만원).

    무주택 1주택: 6억 이하 1.1% / 6~9억 1.5%(누진) / 9억 초과 3.5%
    1주택 → 2주택(조정대상): 8% / 비조정 1.1%
    2주택 → 다주택 추가취득: 조정 12% / 비조정 8%
    생애최초: 200만원 한도 감면 (단순화)
    """
    if price_man <= 0:
        return 0.0

    if ownership == "다주택":
        rate = 0.08  # 단순화: 다주택 일괄 8%
    elif ownership == "1주택":
        # 1주택자 추가매수는 조정대상지역 여부에 따라 다르지만 단순화
        rate = 0.08
    else:  # 무주택 → 1주택
        if price_man <= 60000:
            rate = 0.011
        elif price_man <= 90000:
            # 누진: 6억 1.1% + 초과분 1.5% 가중평균 근사
            # 6억 1.1% + (P-6억)에 1.5%
            tax = 60000 * 0.011 + (price_man - 60000) * 0.015
            return round(max(0, tax - (200 if first_time_buyer else 0)))
        else:
            rate = 0.035
    tax = price_man * rate
    if first_time_buyer:
        tax = max(0, tax - 200)  # 생애최초 200만원 감면
    return round(tax)


# ─── 중개수수료 (2026 한도) ───────────────────────────────
# 거래금액 구간별 상한요율 (매매 기준)
_BROKER_BRACKETS = [
    (50000,  0.006,    250),     # 5억 이하: 0.6%, 25만원 한도
    (90000,  0.005,   None),     # 5~9억: 0.5%
    (150000, 0.004,   None),     # 9~15억: 0.4%
    (1e12,   0.007,   None),     # 15억 초과: 협의 (상한 0.7%로 보수적)
]


def broker_fee_man(price_man: float) -> float:
    """중개수수료 (만원). 매매 기준 법정 상한 가정."""
    if price_man <= 0:
        return 0.0
    for limit, rate, cap in _BROKER_BRACKETS:
        if price_man <= limit:
            fee = price_man * rate
            if cap is not None:
                fee = min(fee, cap)
            return round(fee)
    return round(price_man * 0.007)


# ─── 등기·법무·이사 (대략 0.3%) ────────────────────────────
def registration_etc_man(price_man: float) -> float:
    return round(price_man * 0.003)


def total_acquisition_cost_man(price_man: float, ownership: str = "무주택",
                                 first_time_buyer: bool = False) -> dict:
    """매수가 P에 대해 부대비용 총합과 항목별 내역."""
    tax = acquisition_tax_man(price_man, ownership, first_time_buyer)
    broker = broker_fee_man(price_man)
    reg = registration_etc_man(price_man)
    return {
        "acquisition_tax": tax,
        "broker_fee": broker,
        "registration_etc": reg,
        "total": tax + broker + reg,
    }


# ─── 정책대출 적격 판정 ────────────────────────────────────
def check_didimdol(annual_income_man: float, price_man: float,
                    ownership: str,
                    is_couple: bool = False,
                    is_newlywed: bool = False,
                    children: int = 0,
                    first_time_buyer: bool = False) -> dict:
    """디딤돌 대출 적격성.

    조건 (2026 추정):
    - 무주택 + 만 30세 이상 또는 혼인
    - 부부합산 연소득 한도:
      · 일반 6,000만원 / 생애최초 7,000만 / 신혼 8,500만 / 2자녀+ 8,500만 / 3자녀+ 1억
    - 주택가액 한도: 일반 5억 / 신혼·다자녀 6억
    - 최대 한도: 일반 2.5억 / 신혼 4억 / 2자녀+ 4억 (단순화)
    """
    # 소득 한도
    income_limit = 6000
    if first_time_buyer:
        income_limit = max(income_limit, 7000)
    if is_newlywed:
        income_limit = max(income_limit, 8500)
    if children >= 3:
        income_limit = max(income_limit, 10000)
    elif children >= 2:
        income_limit = max(income_limit, 8500)

    # 주택가 한도
    price_limit = 50000
    if is_newlywed or children >= 2:
        price_limit = 60000

    # 최대 한도
    max_loan = 25000
    if is_newlywed:
        max_loan = 40000
    elif children >= 2:
        max_loan = 40000

    eligible = (
        ownership == "무주택"
        and annual_income_man <= income_limit
        and price_man <= price_limit
    )

    reasons = []
    if ownership != "무주택":
        reasons.append("무주택 아님")
    if annual_income_man > income_limit:
        reasons.append(f"연소득 {income_limit}만 초과")
    if price_man > price_limit:
        reasons.append(f"주택가 {price_limit//10000}억 초과")

    return {
        "eligible": eligible,
        "max_loan_man": max_loan if eligible else 0,
        "rate_pct": 3.0 if eligible else None,
        "income_limit_man": income_limit,
        "price_limit_man": price_limit,
        "reason": "OK" if eligible else " / ".join(reasons),
    }


def check_bogeumjari(annual_income_man: float, price_man: float,
                      ownership: str,
                      is_couple: bool = False,
                      is_newlywed: bool = False,
                      children: int = 0,
                      first_time_buyer: bool = False) -> dict:
    """보금자리론 적격성.

    조건 (2026 추정):
    - 무주택 또는 처분조건부 1주택
    - 부부합산 연소득 한도:
      · 일반 7,000만 / 신혼 8,500만 / 다자녀(1+) 8,500만
    - 주택가액 한도: 6억 (일반·신혼·다자녀 동일)
    - 최대 한도: 3.6억 / 신혼·다자녀 4억
    """
    income_limit = 7000
    if is_newlywed:
        income_limit = max(income_limit, 8500)
    if children >= 1:
        income_limit = max(income_limit, 8500)

    price_limit = 60000

    max_loan = 36000
    if is_newlywed or children >= 1:
        max_loan = 40000

    eligible = (
        ownership in ("무주택", "1주택")
        and annual_income_man <= income_limit
        and price_man <= price_limit
    )

    reasons = []
    if ownership == "다주택":
        reasons.append("다주택")
    if annual_income_man > income_limit:
        reasons.append(f"연소득 {income_limit}만 초과")
    if price_man > price_limit:
        reasons.append(f"주택가 {price_limit//10000}억 초과")

    return {
        "eligible": eligible,
        "max_loan_man": max_loan if eligible else 0,
        "rate_pct": 3.5 if eligible else None,
        "income_limit_man": income_limit,
        "price_limit_man": price_limit,
        "reason": "OK" if eligible else " / ".join(reasons),
    }


def best_policy_loan(annual_income_man: float, price_man: float,
                      ownership: str,
                      is_couple: bool = False,
                      is_newlywed: bool = False,
                      children: int = 0,
                      first_time_buyer: bool = False) -> dict:
    """가능한 정책대출 중 최고 한도 반환."""
    ddl = check_didimdol(annual_income_man, price_man, ownership,
                          is_couple, is_newlywed, children, first_time_buyer)
    bgmj = check_bogeumjari(annual_income_man, price_man, ownership,
                              is_couple, is_newlywed, children, first_time_buyer)
    candidates = []
    if ddl["eligible"]:
        candidates.append(("디딤돌", ddl))
    if bgmj["eligible"]:
        candidates.append(("보금자리", bgmj))
    if not candidates:
        return {"name": None, "max_loan_man": 0, "rate_pct": None,
                "eligible": False, "all_results": {"디딤돌": ddl, "보금자리": bgmj}}
    name, best = max(candidates, key=lambda x: x[1]["max_loan_man"])
    return {"name": name, "max_loan_man": best["max_loan_man"],
            "rate_pct": best["rate_pct"], "eligible": True,
            "all_results": {"디딤돌": ddl, "보금자리": bgmj}}
