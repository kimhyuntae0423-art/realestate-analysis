"""src/analysis/price_trend.py — 월별/단지별 가격 추이 검증."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.analysis.price_trend import monthly_summary, apt_summary, yoy_change


def _row(y, m, d, price, ppp=6000, area=84.9, apt="A", build_year=2015):
    return {"deal_date": date(y, m, d), "deal_amount": price, "price_per_pyeong": ppp,
            "area_m2": area, "apt_name": apt, "build_year": build_year}


def test_monthly_summary_groups_by_year_month():
    df = pd.DataFrame([_row(2025, 1, 5, 100000), _row(2025, 1, 20, 110000), _row(2025, 2, 1, 120000)])
    out = monthly_summary(df)
    assert list(out["ym"]) == ["2025-01", "2025-02"]
    jan = out[out["ym"] == "2025-01"].iloc[0]
    assert jan["deals"] == 2
    assert jan["median_price"] == 105000


def test_apt_summary_top_n_sorted_by_deal_count():
    df = pd.DataFrame(
        [_row(2025, 1, i, 100000, apt="A") for i in range(1, 6)]
        + [_row(2025, 1, i, 100000, apt="B") for i in range(1, 3)]
    )
    out = apt_summary(df, top=1)
    assert len(out) == 1
    assert out.iloc[0]["apt_name"] == "A"
    assert out.iloc[0]["deals"] == 5


def test_yoy_change_requires_13_months():
    short = pd.DataFrame({"ym": ["2025-01"], "avg_price": [100000], "avg_ppp": [6000]})
    assert yoy_change(short) is short or yoy_change(short).equals(short)

    rows = [{"ym": f"2024-{m:02d}", "avg_price": 100000, "avg_ppp": 6000} for m in range(1, 13)]
    rows.append({"ym": "2025-01", "avg_price": 110000, "avg_ppp": 6600})
    long_df = pd.DataFrame(rows)
    out = yoy_change(long_df)
    last = out.iloc[-1]
    assert last["avg_price_yoy_%"] == 10.0
    assert last["avg_ppp_yoy_%"] == 10.0


def test_monthly_summary_empty_input():
    assert monthly_summary(pd.DataFrame()).empty
