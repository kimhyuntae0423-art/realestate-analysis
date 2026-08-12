"""src/analysis/loan.py — LTV/한도cap/DSR 대출 계산 검증.

config/loan_regulations.json 실제 값 기준 (2025-10-15 대책):
- 규제지역(11680 강남 등) 무주택 LTV 50%, 생애최초 +20%p, 다주택 0%
- 한도 cap: 15억↓ 6억 / 15~25억 4억 / 25억↑ 2억 (규제지역만)
- 비규제지역: LTV 무주택 70%, cap 없음
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.analysis import loan


def test_get_zone_known_and_default():
    assert loan.get_zone("11680") == "규제"       # 강남구
    assert loan.get_zone("99999") == "비규제"      # 목록에 없는 코드 → default


def test_get_ltv_pct_regulation_and_bonus():
    assert loan.get_ltv_pct("11680", "무주택") == 50
    assert loan.get_ltv_pct("11680", "무주택", first_time_buyer=True) == 70  # 50+20
    assert loan.get_ltv_pct("11680", "다주택") == 0
    # 다주택은 base=0이라 생애최초 보너스도 적용 안 됨
    assert loan.get_ltv_pct("11680", "다주택", first_time_buyer=True) == 0


def test_loan_capacity_tier1_cap_binds():
    # 10억 매물, 규제지역, 무주택: LTV 50% = 5억 < tier1 cap 6억 → LTV가 binding
    cap = loan.loan_capacity_man(100000, "11680", "무주택")
    assert cap == 50000


def test_loan_capacity_tier2_cap_binds():
    # 20억 매물: LTV 50% = 10억 > tier2 cap(15~25억 구간) 4억 → cap이 binding
    cap = loan.loan_capacity_man(200000, "11680", "무주택")
    assert cap == 40000


def test_required_equity_is_price_minus_loan():
    price = 100000
    loan_amt = loan.loan_capacity_man(price, "11680", "무주택")
    assert loan.required_equity_man(price, "11680", "무주택") == price - loan_amt


def test_dsr_loan_capacity_scales_with_income():
    low = loan.dsr_loan_capacity_man(annual_income_man=3000)
    high = loan.dsr_loan_capacity_man(annual_income_man=9000)
    assert high > low > 0
    assert loan.dsr_loan_capacity_man(annual_income_man=0) == 0.0


def test_loan_breakdown_binding_field_matches_min_limit():
    br = loan.loan_breakdown_man(200000, "11680", "무주택")
    assert br["binding"] == "한도캡"
    assert br["final_loan_man"] == br["cap_limit_man"]
    assert br["required_equity_man"] == br["price_man"] - br["final_loan_man"]
    assert br["monthly_payment_man"] > 0


def test_vectorized_loan_equity_matches_scalar():
    prices = pd.Series([100000.0, 200000.0])
    regions = pd.Series(["11680", "11680"])
    res = loan.vectorized_loan_equity(prices, regions, ownership="무주택")
    assert res["loan_capacity"].tolist() == [
        loan.loan_capacity_man(100000, "11680", "무주택"),
        loan.loan_capacity_man(200000, "11680", "무주택"),
    ]


def test_max_purchase_man_unregulated_zone_uses_closed_form():
    # 비규제(미등록 코드): cap 없음 → seed / (1 - LTV)
    seed = 30000
    ltv = loan.get_ltv_pct("99999", "무주택") / 100.0  # 비규제 무주택 70%
    expected = round(seed / (1.0 - ltv))
    assert loan.max_purchase_man(seed, "99999", "무주택") == expected


def test_max_purchase_man_zero_ltv_returns_seed_as_is():
    # 다주택 규제지역은 LTV 0% → 매수력 = 시드 그대로
    assert loan.max_purchase_man(30000, "11680", "다주택") == 30000.0


def test_max_purchase_man_dsr_cap_reduces_purchasing_power():
    dsr_cap = loan.dsr_loan_capacity_man(annual_income_man=7000)
    without_dsr = loan.max_purchase_man(30000, "11680", "무주택")
    with_dsr = loan.max_purchase_man(30000, "11680", "무주택", dsr_cap_man=dsr_cap)
    assert with_dsr <= without_dsr


def test_max_purchase_man_matches_required_equity_at_result_price():
    # 매수 가능가 P에서 필요자기자본이 시드 이하여야 하고,
    # 한 단계(1천만원) 더 비싼 매물은 시드로 감당 못해야 함
    seed = 50000
    price = loan.max_purchase_man(seed, "11680", "무주택")
    assert loan.required_equity_man(price, "11680", "무주택") <= seed
    assert loan.required_equity_man(price + 1000, "11680", "무주택") > seed


def test_annotate_loan_columns_adds_affordable_flag():
    df = pd.DataFrame({"region_code": ["11680"], "trade_median": [100000.0]})
    out = loan.annotate_loan_columns(df, seed_man=60000, trade_col="trade_median")
    assert out.loc[0, "affordable"] == (out.loc[0, "required_equity"] <= 60000)
