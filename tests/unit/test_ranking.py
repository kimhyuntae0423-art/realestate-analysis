"""src/analysis/ranking.py — 지역 랭킹 / 단지 상승률 검증."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.analysis.ranking import region_ranking, apt_growth


def test_region_ranking_sorts_by_avg_ppp_desc():
    df = pd.DataFrame([
        {"region_code": "11680", "deal_amount": 150000, "price_per_pyeong": 6000},
        {"region_code": "11680", "deal_amount": 160000, "price_per_pyeong": 6200},
        {"region_code": "11650", "deal_amount": 100000, "price_per_pyeong": 4000},
    ])
    out = region_ranking(df, region_map={"11680": "강남구", "11650": "서초구"})
    assert out.iloc[0]["region"] == "강남구"
    assert out.iloc[0]["deals"] == 2
    assert list(out["avg_ppp"]) == sorted(out["avg_ppp"], reverse=True)


def test_region_ranking_unmapped_code_falls_back_to_code():
    df = pd.DataFrame([{"region_code": "99999", "deal_amount": 100000, "price_per_pyeong": 3000}])
    out = region_ranking(df, region_map={})
    assert out.iloc[0]["region"] == "99999"


def test_apt_growth_filters_by_min_deals():
    rows = []
    # apt A: 충분한 거래량 (recent 5건, prior 5건), 가격 상승
    for i in range(5):
        rows.append({"apt_name": "A", "price_per_pyeong": 6000, "deal_date": date(2025, 1, 1 + i)})
    for i in range(5):
        rows.append({"apt_name": "A", "price_per_pyeong": 5000, "deal_date": date(2023, 6, 1 + i)})
    # apt B: 거래량 부족 (min_deals=4 미만) → 결과에서 제외되어야 함
    rows.append({"apt_name": "B", "price_per_pyeong": 9000, "deal_date": date(2025, 1, 1)})
    rows.append({"apt_name": "B", "price_per_pyeong": 8000, "deal_date": date(2023, 6, 1)})
    df = pd.DataFrame(rows)
    out = apt_growth(df, lookback_months=12, min_deals=4)
    assert list(out["apt_name"]) == ["A"]
    assert out.iloc[0]["change_%"] == round((6000 - 5000) / 5000 * 100, 2)


def test_region_ranking_empty_input():
    assert region_ranking(pd.DataFrame(), {}).empty
