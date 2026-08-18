"""src/analysis/region_momentum.py — 지역 모멘텀 랭킹 검증."""
from __future__ import annotations

import pandas as pd

from src.analysis.region_momentum import region_momentum_ranking
from src.database.repository import upsert_trades


def _trade(days_ago, region, apt="A", ppp=6000, area=84.9, amount=100000):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


def test_region_momentum_ranking_ranks_hot_region_first():
    # 99999(미등록 tier, 기본점수): 이전 반기 저가 -> 최근 반기 고가(+가격모멘텀) + 거래량도 급증
    # 88888(미등록 tier, 동일 기본점수): 가격 변화 없음, 거래량도 동일 -> 모멘텀 없음
    rows = []
    for i in range(15):
        rows.append(_trade(150 + i, region="99999", ppp=6000))   # 이전 반기: 낮은가
    for i in range(30):
        rows.append(_trade(60 + i, region="99999", ppp=9000))    # 최근 반기: 높은가 + 거래량 2배
    for i in range(15):
        rows.append(_trade(150 + i, region="88888", ppp=6000))
    for i in range(15):
        rows.append(_trade(60 + i, region="88888", ppp=6000))    # 가격도 거래량도 그대로
    upsert_trades(rows)

    out = region_momentum_ranking(months=6, min_deals=5)
    assert not out.empty
    assert list(out["region_code"])[:1] == ["99999"]
    hot = out[out["region_code"] == "99999"].iloc[0]
    cold = out[out["region_code"] == "88888"].iloc[0]
    assert hot["momentum_score"] > cold["momentum_score"]


def test_region_momentum_ranking_empty_when_no_data():
    out = region_momentum_ranking()
    assert out.empty
