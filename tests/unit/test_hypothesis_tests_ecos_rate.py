"""src/analysis/hypothesis_tests_ecos_rate.py — M1/M2 비율·실질금리 가설 검증."""
from __future__ import annotations

import pandas as pd

from src.analysis import hypothesis_tests_ecos_rate as er
from src.database.repository import upsert_trades, upsert_ecos_series


def _trade(days_ago, apt="A", ppp=6000, area=84.9, amount=100000):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": "11680", "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


def test_m1_m2_ratio_leads_price_detects_positive_lag():
    # 가격(단일 단지+평형): T0(90일전)->T1(60일전) +5%, T1->T2(30일전) +25%
    rows_t = []
    for i in range(3):
        rows_t.append(_trade(90 + i, ppp=10000))
        rows_t.append(_trade(60 + i, ppp=10500))  # T0->T1 +5%
        rows_t.append(_trade(30 + i, ppp=13125))  # T1->T2 +25%
    upsert_trades(rows_t)

    # M1/M2 비율을 T0=0.10, T1=0.15로 설계 -> 가격 성장(5%->25%)과 같은 방향 -> 양의 상관
    t0 = (pd.Timestamp.today() - pd.Timedelta(days=90)).date()
    t1 = (pd.Timestamp.today() - pd.Timedelta(days=60)).date()
    upsert_ecos_series([
        {"series": "m1_eop_raw", "ym_date": t0, "value": 100.0, "source": "test"},
        {"series": "m1_eop_raw", "ym_date": t1, "value": 150.0, "source": "test"},
        {"series": "m2_eop_raw", "ym_date": t0, "value": 1000.0, "source": "test"},
        {"series": "m2_eop_raw", "ym_date": t1, "value": 1000.0, "source": "test"},
    ])

    # 등록된 기본값(lag_months=18)이 아니라 fixture에 맞춘 1개월 지연으로 계산식 자체만 검증
    r = er.test_m1_m2_ratio_leads_price(months=6, lag_months=1)
    assert r.n >= 2
    assert r.statistic > 0  # 비율 높을수록 다음달 가격 상승폭도 큼 -> 양의 상관(계산식 검증용)


def test_m1_m2_ratio_leads_price_empty_when_no_data():
    r = er.test_m1_m2_ratio_leads_price()
    assert r.n == 0


def test_real_rate_leads_price_detects_negative_lag():
    # 가격(단일 단지+평형): T0(90일전)->T1(60일전) +5%, T1->T2(30일전) +25%
    rows_t = []
    for i in range(3):
        rows_t.append(_trade(90 + i, ppp=10000))
        rows_t.append(_trade(60 + i, ppp=10500))  # T0->T1 +5%
        rows_t.append(_trade(30 + i, ppp=13125))  # T1->T2 +25%
    upsert_trades(rows_t)

    # 실질금리를 T0=3.0%(기준5.0-기대2.0), T1=1.0%(기준3.0-기대2.0)로 설계
    # -> 실질금리 하락(3.0->1.0)과 가격 성장 가속(5%->25%)이 같이 감 -> 음의 상관
    t0 = (pd.Timestamp.today() - pd.Timedelta(days=90)).date()
    t1 = (pd.Timestamp.today() - pd.Timedelta(days=60)).date()
    upsert_ecos_series([
        {"series": "base_rate", "ym_date": t0, "value": 5.0, "source": "test"},
        {"series": "base_rate", "ym_date": t1, "value": 3.0, "source": "test"},
        {"series": "expected_inflation", "ym_date": t0, "value": 2.0, "source": "test"},
        {"series": "expected_inflation", "ym_date": t1, "value": 2.0, "source": "test"},
    ])

    # 등록된 기본값(lag_months=18)이 아니라 fixture에 맞춘 1개월 지연으로 계산식 자체만 검증
    r = er.test_real_rate_leads_price(months=6, lag_months=1)
    assert r.n >= 2
    assert r.statistic < 0  # 실질금리 낮을수록 다음달 가격 상승폭 큼 -> 음의 상관(계산식 검증용)


def test_real_rate_leads_price_empty_when_no_data():
    r = er.test_real_rate_leads_price()
    assert r.n == 0
