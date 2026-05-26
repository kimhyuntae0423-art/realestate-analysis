"""대출 한도 계산 (LTV + 한도cap + DSR)

모든 금액 단위는 만원.

2025-10-15 대책 반영:
- 규제지역(서울25 + 경기12): LTV 무주택 50% / 1주택 50% / 다주택 0%
- 주담대 한도 cap: 15억 이하 6억 / 15~25억 4억 / 25억 초과 2억
- DSR 40% (1금융), 스트레스 +3%
"""
from __future__ import annotations
import json
from functools import lru_cache

import numpy as np
import pandas as pd

from config.settings import ROOT


@lru_cache(maxsize=1)
def load_regulations() -> dict:
    p = ROOT / "config" / "loan_regulations.json"
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def get_zone(region_code: str) -> str:
    reg = load_regulations()
    return reg["zone_by_region"].get(region_code, reg["default_zone"])


def get_ltv_pct(region_code: str, ownership: str = "무주택",
                 first_time_buyer: bool = False) -> float:
    reg = load_regulations()
    zone = get_zone(region_code)
    table = reg["ltv_table"].get(zone, {})
    base = float(table.get(ownership, 0))
    if first_time_buyer and base > 0:
        bonus = float(table.get("_생애최초_bonus", 0))
        base = min(base + bonus, 80)
    return base


def _loan_cap_for(zone: str, price_man: float) -> float:
    reg = load_regulations()
    caps = reg.get("loan_cap_man", {}).get(zone, {})
    if not caps:
        return float("inf")
    if price_man <= caps.get("tier1_price_max_man", float("inf")):
        return float(caps.get("tier1_cap_man", float("inf")))
    if price_man <= caps.get("tier2_price_max_man", float("inf")):
        return float(caps.get("tier2_cap_man", float("inf")))
    return float(caps.get("tier3_cap_man", float("inf")))


def loan_capacity_man(price_man: float, region_code: str,
                       ownership: str = "무주택",
                       first_time_buyer: bool = False,
                       dsr_cap_man: float | None = None) -> float:
    """매매가 price_man 매물에 대해 가능한 실제 대출액 (만원).

    = min(LTV × 매매가, 한도 cap, DSR 한도)
    """
    if price_man <= 0:
        return 0.0
    ltv = get_ltv_pct(region_code, ownership, first_time_buyer) / 100.0
    loan_ltv = price_man * ltv
    cap = _loan_cap_for(get_zone(region_code), price_man)
    loan = min(loan_ltv, cap)
    if dsr_cap_man is not None:
        loan = min(loan, dsr_cap_man)
    return round(loan)


def required_equity_man(price_man: float, region_code: str,
                         ownership: str = "무주택",
                         first_time_buyer: bool = False,
                         dsr_cap_man: float | None = None) -> float:
    if price_man <= 0:
        return 0.0
    return round(price_man - loan_capacity_man(
        price_man, region_code, ownership, first_time_buyer, dsr_cap_man
    ))


def max_purchase_man(seed_man: float, region_code: str,
                      ownership: str = "무주택",
                      first_time_buyer: bool = False,
                      dsr_cap_man: float | None = None) -> float:
    """시드로 매수 가능한 최대 매매가 (만원). 한도 cap + DSR 다 고려."""
    ltv = get_ltv_pct(region_code, ownership, first_time_buyer) / 100.0
    if ltv <= 0:
        return float(seed_man)

    zone = get_zone(region_code)
    reg = load_regulations()
    caps = reg.get("loan_cap_man", {}).get(zone, {})

    # 비규제 + DSR 없음 → 단순 공식
    if zone == "비규제" and dsr_cap_man is None:
        return round(seed_man / (1.0 - ltv))

    # 일반: 가격 격자 탐색 (1억~100억, 100만원 단위)
    best = float(seed_man)
    p = 1000.0  # 1억=1만만원? No: 1억 = 10000 만원
    p = 10000.0  # 1억 시작
    step = 1000.0  # 1천만원 단위
    p_max_search = 5_000_000.0  # 500억까지 (충분)
    while p <= p_max_search:
        loan = price_loan(p, ltv, zone, caps, dsr_cap_man)
        equity = p - loan
        if equity <= seed_man:
            best = p
        else:
            break
        p += step
    return best


def price_loan(price_man: float, ltv: float, zone: str, caps: dict,
                dsr_cap_man: float | None) -> float:
    """내부 헬퍼: 매매가에 대한 실제 대출액 계산 (한도 cap + DSR)."""
    loan = price_man * ltv
    if caps:
        if price_man <= caps.get("tier1_price_max_man", float("inf")):
            cap = caps.get("tier1_cap_man", float("inf"))
        elif price_man <= caps.get("tier2_price_max_man", float("inf")):
            cap = caps.get("tier2_cap_man", float("inf"))
        else:
            cap = caps.get("tier3_cap_man", float("inf"))
        loan = min(loan, cap)
    if dsr_cap_man is not None:
        loan = min(loan, dsr_cap_man)
    return loan


# ─── DSR 한도 계산 ─────────────────────────────────────
def dsr_loan_capacity_man(annual_income_man: float,
                            existing_monthly_payment_man: float = 0,
                            interest_rate_pct: float = 4.5,
                            dsr_limit_pct: float | None = None,
                            loan_years: int = 30,
                            stress_rate_pct: float | None = None) -> float:
    """DSR 한도로 가능한 신규 대출 원금 (만원).

    annual_income_man: 연 소득 (만원)
    existing_monthly_payment_man: 기존 부채 월 원리금 (만원)
    interest_rate_pct: 대출 명목 금리 (%)
    dsr_limit_pct: DSR 한도 (None이면 config 기본값 40)
    loan_years: 만기 (보통 30)
    stress_rate_pct: 스트레스 가산 금리 (None이면 config 기본값 3.0)
    """
    reg = load_regulations().get("dsr_defaults", {})
    if dsr_limit_pct is None:
        dsr_limit_pct = float(reg.get("dsr_limit_pct", 40))
    if stress_rate_pct is None:
        stress_rate_pct = float(reg.get("stress_rate_pct", 3.0))

    if annual_income_man <= 0:
        return 0.0

    # 연 가용 원리금 (만원)
    annual_capacity = annual_income_man * dsr_limit_pct / 100 - existing_monthly_payment_man * 12
    if annual_capacity <= 0:
        return 0.0

    monthly_capacity = annual_capacity / 12

    # 스트레스 가산 적용한 금리로 한도 산정
    effective_rate = (interest_rate_pct + stress_rate_pct) / 100 / 12
    n_months = loan_years * 12
    if effective_rate <= 0:
        return monthly_capacity * n_months

    # 원리금 균등 상환 역산: P = M × ((1+r)^n - 1) / (r(1+r)^n)
    growth = (1 + effective_rate) ** n_months
    principal = monthly_capacity * (growth - 1) / (effective_rate * growth)
    return round(principal)


# ─── 벡터 연산 (추천 함수용) ────────────────────────────
def vectorized_loan_equity(prices: pd.Series, region_codes: pd.Series,
                             ownership: str = "무주택",
                             first_time_buyer: bool = False,
                             dsr_cap_man: float | None = None) -> dict[str, pd.Series]:
    """대량 매매가에 대해 LTV/대출/자기자본 일괄 계산."""
    reg = load_regulations()
    ltv_pct = region_codes.map(lambda r: get_ltv_pct(r, ownership, first_time_buyer))
    zones = region_codes.map(get_zone)

    loan_ltv = prices.astype(float) * ltv_pct / 100

    # 한도 cap (규제지역만)
    cap = pd.Series(np.inf, index=prices.index, dtype=float)
    is_reg = zones == "규제"
    cap_cfg = reg.get("loan_cap_man", {}).get("규제", {})
    t1_max = cap_cfg.get("tier1_price_max_man", float("inf"))
    t1_cap = cap_cfg.get("tier1_cap_man", float("inf"))
    t2_max = cap_cfg.get("tier2_price_max_man", float("inf"))
    t2_cap = cap_cfg.get("tier2_cap_man", float("inf"))
    t3_cap = cap_cfg.get("tier3_cap_man", float("inf"))

    cap[is_reg & (prices <= t1_max)] = t1_cap
    cap[is_reg & (prices > t1_max) & (prices <= t2_max)] = t2_cap
    cap[is_reg & (prices > t2_max)] = t3_cap

    loan = loan_ltv.clip(upper=cap)
    if dsr_cap_man is not None:
        loan = loan.clip(upper=dsr_cap_man)

    loan = loan.round().astype(float)
    equity = (prices - loan).round().astype(float)

    return {
        "ltv_pct": ltv_pct,
        "zone": zones,
        "loan_capacity": loan,
        "required_equity": equity,
    }


# ─── 기존 호환 ────────────────────────────────────────────
def annotate_loan_columns(df: pd.DataFrame, seed_man: float,
                           ownership: str = "무주택",
                           first_time_buyer: bool = False,
                           trade_col: str = "trade_median",
                           dsr_cap_man: float | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    res = vectorized_loan_equity(out[trade_col], out["region_code"],
                                   ownership, first_time_buyer, dsr_cap_man)
    out["ltv_%"] = res["ltv_pct"]
    out["zone"] = res["zone"]
    out["loan_capacity"] = res["loan_capacity"]
    out["required_equity"] = res["required_equity"]
    out["affordable"] = out["required_equity"] <= seed_man
    return out
