"""src/analysis/gap_analysis.py — 매매-전세 갭 계산 검증."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.analysis.gap_analysis import to_jeonse_equiv, gap_table


def test_to_jeonse_equiv_converts_monthly_rent():
    df = pd.DataFrame([{"deposit": 10000, "monthly_rent": 50}])
    out = to_jeonse_equiv(df, monthly_to_deposit=100)
    assert out.loc[0, "jeonse_equiv"] == 10000 + 50 * 100


def test_gap_table_basic():
    trade = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deal_amount": 150000, "deal_date": date(2025, 6, 1)},
        {"apt_name": "A", "area_m2": 85.0, "deal_amount": 152000, "deal_date": date(2025, 7, 1)},
    ])
    rent = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deposit": 90000, "monthly_rent": 0,
         "deal_date": date(2025, 6, 15)},
    ])
    out = gap_table(trade, rent, area_tol=5.0, months=12)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["gap"] == row["trade_median"] - row["rent_median"]
    assert row["gap_ratio_%"] == round(row["gap"] / row["trade_median"] * 100, 2)


def test_gap_table_trade_months_falls_back_when_no_recent_deals():
    # 매매 거래는 10개월 전 1건뿐 → trade_months=1(최근 1개월) 창에는 없음
    # → months=12 전체 기간 median으로 fallback 되어야 함
    trade = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deal_amount": 150000, "deal_date": date(2025, 2, 1)},
    ])
    rent = pd.DataFrame([
        {"apt_name": "A", "area_m2": 84.9, "deposit": 90000, "monthly_rent": 0,
         "deal_date": date(2025, 12, 1)},
    ])
    out = gap_table(trade, rent, area_tol=5.0, months=12, trade_months=1)
    assert len(out) == 1
    assert out.iloc[0]["trade_median"] == 150000


def test_gap_table_empty_inputs():
    assert gap_table(pd.DataFrame(), pd.DataFrame()).empty
