"""src/analysis/yield_calc.py — 임대 수익률 계산 검증."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.analysis.yield_calc import rental_yield


def test_rental_yield_basic_formula():
    trade = pd.DataFrame([
        {"apt_name": "래미안A", "area_m2": 84.9, "deal_amount": 150000,
         "deal_date": date(2025, 6, 1)},
        {"apt_name": "래미안A", "area_m2": 85.0, "deal_amount": 152000,
         "deal_date": date(2025, 7, 1)},
    ])
    rent = pd.DataFrame([
        {"apt_name": "래미안A", "area_m2": 84.9, "deposit": 30000,
         "monthly_rent": 100, "deal_date": date(2025, 6, 15)},
        {"apt_name": "래미안A", "area_m2": 85.0, "deposit": 30000,
         "monthly_rent": 100, "deal_date": date(2025, 7, 15)},
    ])
    out = rental_yield(trade, rent, area_tol=5.0, months=12)
    assert len(out) == 1
    row = out.iloc[0]
    invest = row["trade_median"] - row["deposit_median"]
    expected_yield = round(row["monthly_median"] * 12 / invest * 100, 2)
    assert row["annual_yield_%"] == expected_yield


def test_rental_yield_ignores_jeonse_only_rows():
    trade = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deal_amount": 150000, "deal_date": date(2025, 6, 1)},
    ])
    rent = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deposit": 90000, "monthly_rent": 0,
         "deal_date": date(2025, 6, 1)},
    ])
    out = rental_yield(trade, rent)
    assert out.empty


def test_rental_yield_empty_inputs():
    assert rental_yield(pd.DataFrame(), pd.DataFrame()).empty
