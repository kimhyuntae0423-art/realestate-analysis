"""src/analysis/hypothesis_tests_spillover.py — 동탄발 인근지역 갭메우기 가설 검증."""
from __future__ import annotations

import pandas as pd

from src.analysis import hypothesis_tests_spillover as sp
from src.database.repository import upsert_trades


def _trade(days_ago, region, apt="A", ppp=6000, amount=100000, area=84.9):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


def _month_ago_days(n: int) -> int:
    """n개월 전 대략적인 일수 (30일/월 근사, hypothesis_tests_cycles.py와 동일 관례)."""
    return 30 * n


def test_dongtan_spillover_detects_positive_lag():
    # 동탄(41597)이 서로 다른 상승폭(+50%, +20%)을 보인 두 시점을 만들고, 병점(41595)이
    # 정확히 1개월 늦게 같은 크기로 따라 오르게 구성 -> t+1 시차에서 강한 양의 상관이 나와야 함
    rows = []
    for i in range(6):
        rows.append(_trade(_month_ago_days(4) + i, "41597", apt="X", ppp=6000))
        rows.append(_trade(_month_ago_days(3) + i, "41597", apt="X", ppp=9000))    # 동탄 t1: +50%
        rows.append(_trade(_month_ago_days(2) + i, "41597", apt="X", ppp=10800))   # 동탄 t2: +20%
        rows.append(_trade(_month_ago_days(3) + i, "41595", apt="Y", ppp=4000))
        rows.append(_trade(_month_ago_days(2) + i, "41595", apt="Y", ppp=6000))    # 병점 t1+1: +50%
        rows.append(_trade(_month_ago_days(1) + i, "41595", apt="Y", ppp=7200))    # 병점 t2+1: +20%
    upsert_trades(rows)

    r = sp.test_dongtan_spillover_to_adjacent(
        months=6, follower_regions={"41595": "화성 병점구"}, max_lag=3, min_unit_deals=1,
    )
    assert r.n >= 2
    assert r.statistic > 0
    assert "화성 병점구 (t+1개월)" in r.breakdown


def test_dongtan_spillover_reports_per_region_breakdown():
    # 병점(41595)은 1개월 시차로 강하게 따라오고, 오산(41370)은 데이터가 아예 없는 상태 ->
    # breakdown에는 병점만 잡히고, explored 텍스트에는 오산이 "데이터 없음"으로 남아야 함
    rows = []
    for i in range(6):
        rows.append(_trade(_month_ago_days(4) + i, "41597", apt="X", ppp=6000))
        rows.append(_trade(_month_ago_days(3) + i, "41597", apt="X", ppp=9000))
        rows.append(_trade(_month_ago_days(2) + i, "41597", apt="X", ppp=10800))
        rows.append(_trade(_month_ago_days(3) + i, "41595", apt="Y", ppp=4000))
        rows.append(_trade(_month_ago_days(2) + i, "41595", apt="Y", ppp=6000))
        rows.append(_trade(_month_ago_days(1) + i, "41595", apt="Y", ppp=7200))
    upsert_trades(rows)

    r = sp.test_dongtan_spillover_to_adjacent(
        months=6, max_lag=3, min_unit_deals=1,
        follower_regions={"41595": "화성 병점구", "41370": "오산시"},
    )
    assert any("화성 병점구" in k for k in r.breakdown)
    assert not any("오산시" in k for k in r.breakdown)
    assert "오산시: 데이터 없음" in r.explored


def test_dongtan_spillover_empty_when_no_data():
    r = sp.test_dongtan_spillover_to_adjacent()
    assert r.n == 0
