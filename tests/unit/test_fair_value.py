"""src/analysis/fair_value.py — 적정가(전세가율/수익률/이동평균) 역산 검증."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.analysis.fair_value import (
    fair_value_by_jeonse, fair_value_by_yield, fair_value_ppp_trend,
    fair_value_apt_vs_ma, enrich_with_fair_value,
)


def test_fair_value_by_jeonse_premium_sign():
    trade = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deal_amount": 100000, "deal_date": date(2025, 6, 1)},
    ])
    rent = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deposit": 65000, "monthly_rent": 0,
         "deal_date": date(2025, 6, 1)},
    ])
    out = fair_value_by_jeonse(trade, rent, target_jeonse_ratio=0.65, trade_months=None)
    assert len(out) == 1
    row = out.iloc[0]
    # 전세 6.5억 / 65% = 매매 적정가 10억 → 실거래 10억이면 premium 0%
    assert row["fair_value"] == 100000
    assert row["fv_premium_%"] == 0.0
    assert row["verdict"] == "🟡 적정"


def test_fair_value_by_jeonse_overshoot_verdict():
    trade = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deal_amount": 130000, "deal_date": date(2025, 6, 1)},
    ])
    rent = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deposit": 65000, "monthly_rent": 0,
         "deal_date": date(2025, 6, 1)},
    ])
    out = fair_value_by_jeonse(trade, rent, target_jeonse_ratio=0.65, trade_months=None)
    # fair_value=100000, 실거래 130000 → premium 30% → 오버슈팅
    assert out.iloc[0]["verdict"] == "🔴 오버슈팅"


def test_fair_value_by_yield_ignores_jeonse_only():
    trade = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deal_amount": 100000, "deal_date": date(2025, 6, 1)},
    ])
    rent = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deposit": 65000, "monthly_rent": 0,
         "deal_date": date(2025, 6, 1)},
    ])
    assert fair_value_by_yield(trade, rent).empty


def test_fair_value_by_yield_formula():
    trade = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deal_amount": 40000, "deal_date": date(2025, 6, 1)},
    ])
    rent = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deposit": 5000, "monthly_rent": 100,
         "deal_date": date(2025, 6, 1)},
    ])
    out = fair_value_by_yield(trade, rent, target_yield_pct=3.5, trade_months=None)
    assert len(out) == 1
    row = out.iloc[0]
    expected_fv = round(100 * 12 / 0.035)
    assert row["fair_value"] == expected_fv


def test_fair_value_ppp_trend_requires_6_months():
    df = pd.DataFrame([
        {"deal_date": date(2025, 1, 1), "price_per_pyeong": 6000, "deal_amount": 100000},
    ])
    assert fair_value_ppp_trend(df).empty


def test_fair_value_ppp_trend_computes_overshoot():
    rows = []
    for m in range(1, 8):
        rows.append({"deal_date": date(2025, m, 1), "price_per_pyeong": 6000, "deal_amount": 100000})
    rows.append({"deal_date": date(2025, 8, 1), "price_per_pyeong": 9000, "deal_amount": 100000})
    df = pd.DataFrame(rows)
    out = fair_value_ppp_trend(df, ma_months=24)
    assert not out.empty
    last = out.iloc[-1]
    assert last["overshoot_%"] > 0


def test_fair_value_apt_vs_ma_filters_low_liquidity():
    rows = []
    for m in range(1, 6):
        rows.append({"apt_name": "저유동성", "deal_date": date(2025, m, 1),
                      "price_per_pyeong": 6000, "deal_amount": 100000})
    out = fair_value_apt_vs_ma(pd.DataFrame(rows), min_deals=10)
    assert out.empty  # 거래량 5건 < min_deals 10


def test_enrich_with_fair_value_uses_jeonse_column_when_present():
    df = pd.DataFrame({"trade_median": [100000.0], "rent_median": [65000.0]})
    out = enrich_with_fair_value(df, target_jeonse_ratio=0.65)
    assert out.loc[0, "fair_value"] == 100000.0
    assert out.loc[0, "fv_premium_%"] == 0.0


def test_enrich_with_fair_value_no_columns_returns_unchanged():
    df = pd.DataFrame({"trade_median": [100000.0]})
    out = enrich_with_fair_value(df, jeonse_col="rent_median", monthly_col="monthly_median")
    assert "fair_value" not in out.columns
