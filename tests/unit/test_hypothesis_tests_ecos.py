"""src/analysis/hypothesis_tests_ecos.py — 한국은행 ECOS(M2) 가설 검증."""
from __future__ import annotations

import pandas as pd

from src.analysis import hypothesis_tests_ecos as e
from src.database.repository import upsert_trades, upsert_ecos_series


def _trade(days_ago, apt="A", ppp=6000, area=84.9, amount=100000):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": "11680", "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


def _m2_rows_ending_at(anchor_month, yoy_at_anchor=5.0, yoy_at_next=15.0):
    """anchor_month, anchor_month+1 시점에 각각 YoY(전년동월대비)=5%/15%가 정의되도록
    anchor_month-12 ~ anchor_month+1까지 14개월 연속 M2 원값을 만든다."""
    values = [100, 100, 101, 101, 102, 102, 103, 103, 104, 104, 104, 104,
              100 * (1 + yoy_at_anchor / 100), 100 * (1 + yoy_at_next / 100)]
    return [
        {"series": "m2_eop_raw", "ym_date": (anchor_month + (k - 12)).to_timestamp().date(),
         "value": float(val), "source": "test"}
        for k, val in enumerate(values)
    ]


def test_money_supply_leads_price_computes_correlation_direction():
    # 가격(단일 단지+평형): T0(90일전)->T1(60일전) +5%, T1->T2(30일전) +25%
    rows_t = []
    for i in range(3):
        rows_t.append(_trade(90 + i, ppp=10000))
        rows_t.append(_trade(60 + i, ppp=10500))  # T0->T1 +5%
        rows_t.append(_trade(30 + i, ppp=13125))  # T1->T2 +25%
    upsert_trades(rows_t)

    # M2 YoY를 T0=5%, T1=15%로 설계 -> 가격 성장(5%->25%)과 같은 방향으로 커짐 -> 양의 상관.
    # 등록된 기본값(lag_months=12)이 아니라 fixture에 맞춘 1개월 지연으로 계산식 자체만 검증.
    t0_month = (pd.Timestamp.today() - pd.Timedelta(days=90)).to_period("M")
    upsert_ecos_series(_m2_rows_ending_at(t0_month))

    r = e.test_money_supply_leads_price(months=6, lag_months=1)
    assert r.n >= 2
    assert r.statistic > 0  # M2 증가율 클수록 다음달 가격 상승폭도 큼 -> 양의 상관(계산식 검증용)


def test_money_supply_leads_price_empty_when_no_data():
    r = e.test_money_supply_leads_price()
    assert r.n == 0


def test_price_leads_money_supply_computes_correlation_direction():
    # 가격(단일 단지+평형): T0(90일전)->T1(60일전) +5%, T1->T2(30일전) +25%
    rows_t = []
    for i in range(3):
        rows_t.append(_trade(90 + i, ppp=10000))
        rows_t.append(_trade(60 + i, ppp=10500))  # T0->T1 +5%
        rows_t.append(_trade(30 + i, ppp=13125))  # T1->T2 +25%
    upsert_trades(rows_t)

    # 역방향(가격(t) -> M2(t+1)) 검증이라 M2 YoY 정의 시점을 T1+1=T2, T2+1 쪽에 맞춘다
    t2_month = (pd.Timestamp.today() - pd.Timedelta(days=30)).to_period("M")
    upsert_ecos_series(_m2_rows_ending_at(t2_month))

    r = e.test_price_leads_money_supply(months=6, lag_months=1)
    assert r.n >= 2
    assert r.statistic > 0  # 가격 상승폭 클수록 그다음 M2 증가율도 큼 -> 양의 상관(계산식 검증용)


def test_price_leads_money_supply_empty_when_no_data():
    r = e.test_price_leads_money_supply()
    assert r.n == 0
