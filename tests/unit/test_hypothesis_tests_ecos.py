"""src/analysis/hypothesis_tests_ecos.py — 한국은행 ECOS(M2) 가설 검증."""
from __future__ import annotations

import pandas as pd

from src.analysis import hypothesis_tests_ecos as e
from src.database.repository import upsert_trades, session_scope
from src.database.models import EcosSeries


def _trade(days_ago, apt="A", ppp=6000, area=84.9, amount=100000):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": "11680", "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


def test_money_supply_leads_price_detects_positive_lag():
    # 가격(단일 단지+평형): T0(90일전)->T1(60일전) +5%, T1->T2(30일전) +25%
    rows_t = []
    for i in range(3):
        rows_t.append(_trade(90 + i, ppp=10000))
        rows_t.append(_trade(60 + i, ppp=10500))  # T0->T1 +5%
        rows_t.append(_trade(30 + i, ppp=13125))  # T1->T2 +25%
    upsert_trades(rows_t)

    # M2: T0-12개월 ~ T1까지 14개월 연속 채워서 T0, T1 둘 다 YoY(전년동월대비)가 정의되게 함.
    # T0 시점 YoY=5%, T1 시점 YoY=15%로 설계 -> 가격 성장(5%->25%)과 같은 방향으로 커짐 -> 양의 상관
    t0_month = (pd.Timestamp.today() - pd.Timedelta(days=90)).to_period("M")
    values = [100, 100, 101, 101, 102, 102, 103, 103, 104, 104, 104, 104, 105, 115]
    with session_scope() as s:
        for k, val in enumerate(values):
            ym = (t0_month + (k - 12)).to_timestamp().date()
            s.add(EcosSeries(series="m2_eop_raw", ym_date=ym, value=float(val), source="test"))

    r = e.test_money_supply_leads_price(months=6)
    assert r.n >= 2
    assert r.statistic > 0  # M2 증가율 클수록 다음달 가격 상승폭도 큼 -> 양의 상관


def test_money_supply_leads_price_empty_when_no_data():
    r = e.test_money_supply_leads_price()
    assert r.n == 0
