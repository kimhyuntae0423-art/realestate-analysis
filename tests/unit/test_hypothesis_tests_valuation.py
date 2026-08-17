"""src/analysis/hypothesis_tests_valuation.py — 가치평가/밸류에이션 계열 가설 검증."""
from __future__ import annotations

import pandas as pd

from src.analysis import hypothesis_tests_valuation as v
from src.database.repository import upsert_trades, upsert_rents, session_scope
from src.database.models import SupplySchedule, PopulationFlow, KbSentimentIndex


def _trade(days_ago, region="11680", apt="A", ppp=6000, amount=100000, area=84.9):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


def _rent(days_ago, region="11680", apt="A", deposit=3000, area=84.9, monthly_rent=0):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deposit": deposit, "monthly_rent": monthly_rent}


def _month_ago_days(n: int) -> int:
    return 30 * n


def test_jeonse_ratio_leads_price_detects_positive_lag():
    # M0(3개월전): 전세가율 낮음 -> M1(2개월전) 매매가 +10%
    # M1(2개월전): 전세가율 높음 -> M2(1개월전) 매매가 +25%
    # (전세가율의 절대 수치는 중요하지 않음 - "다음달 상승폭"과의 순위 상관만 검증)
    # growth는 rent와 겹치는 달만 계산되므로 M0~M2 전 구간에 렌트 데이터가 있어야 함
    rows_t, rows_r = [], []
    for i in range(6):
        rows_t.append(_trade(_month_ago_days(3) + i, ppp=10000))
        rows_t.append(_trade(_month_ago_days(2) + i, ppp=11000))   # M0->M1 +10%
        rows_t.append(_trade(_month_ago_days(1) + i, ppp=13750))   # M1->M2 +25%
        rows_r.append(_rent(_month_ago_days(3) + i, deposit=3000))   # M0 전세가율 낮음
        rows_r.append(_rent(_month_ago_days(2) + i, deposit=5500))   # M1 전세가율 높음
        rows_r.append(_rent(_month_ago_days(1) + i, deposit=6000))   # M2 (growth 계산용)
    upsert_trades(rows_t)
    upsert_rents(rows_r)

    r = v.test_jeonse_ratio_leads_price(months=6, min_deals=3)
    assert r.n >= 2
    assert r.statistic > 0  # 전세가율 높을수록 다음달 매매가 상승폭 큼 -> 양의 상관


def test_jeonse_ratio_leads_price_empty_when_no_data():
    r = v.test_jeonse_ratio_leads_price()
    assert r.n == 0


def test_supply_leads_price_decline_detects_negative_correlation():
    # M0(3개월전) 입주물량 많음(1000) -> M1(2개월전) 매매가 -10%
    # M1(2개월전) 입주물량 적음(100)  -> M2(1개월전) 매매가 +20%
    # 공급 많았던 달일수록 다음달 상승폭이 작아야 가설 지지(음의 상관)
    rows_t = []
    for i in range(3):
        rows_t.append(_trade(_month_ago_days(3) + i, ppp=10000))
        rows_t.append(_trade(_month_ago_days(2) + i, ppp=9000))    # M0->M1 -10%
        rows_t.append(_trade(_month_ago_days(1) + i, ppp=10800))   # M1->M2 +20%
    upsert_trades(rows_t)

    m0 = (pd.Timestamp.today() - pd.Timedelta(days=_month_ago_days(3))).date()
    m1 = (pd.Timestamp.today() - pd.Timedelta(days=_month_ago_days(2))).date()
    with session_scope() as s:
        s.add(SupplySchedule(region_code="11", move_in_date=m0, units=1000, source="test"))
        s.add(SupplySchedule(region_code="11", move_in_date=m1, units=100, source="test"))

    r = v.test_supply_leads_price_decline(months=6, min_deals=3)
    assert r.n >= 2
    assert r.statistic < 0  # 입주물량 많을수록 다음달 상승폭 작음 -> 음의 상관


def test_supply_leads_price_decline_empty_when_no_data():
    r = v.test_supply_leads_price_decline()
    assert r.n == 0


def test_population_migration_leads_price_detects_positive_lag():
    # M0(3개월전) 순유입 적음(-500) -> M1(2개월전) 매매가 -10%
    # M1(2개월전) 순유입 많음(800)  -> M2(1개월전) 매매가 +20%
    # 순유입 많았던 달일수록 다음달 상승폭이 커야 가설 지지(양의 상관)
    rows_t = []
    for i in range(3):
        rows_t.append(_trade(_month_ago_days(3) + i, ppp=10000))
        rows_t.append(_trade(_month_ago_days(2) + i, ppp=9000))    # M0->M1 -10%
        rows_t.append(_trade(_month_ago_days(1) + i, ppp=10800))   # M1->M2 +20%
    upsert_trades(rows_t)

    m0 = (pd.Timestamp.today() - pd.Timedelta(days=_month_ago_days(3))).date()
    m1 = (pd.Timestamp.today() - pd.Timedelta(days=_month_ago_days(2))).date()
    with session_scope() as s:
        s.add(PopulationFlow(region_code="11680", flow_date=m0, inflow=100, outflow=600,
                              net_inflow=-500, source="test"))
        s.add(PopulationFlow(region_code="11680", flow_date=m1, inflow=900, outflow=100,
                              net_inflow=800, source="test"))

    r = v.test_population_migration_leads_price(months=6, min_deals=3)
    assert r.n >= 2
    assert r.statistic > 0  # 순유입 많을수록 다음달 상승폭 큼 -> 양의 상관


def test_population_migration_leads_price_empty_when_no_data():
    r = v.test_population_migration_leads_price()
    assert r.n == 0


def test_buyer_sentiment_leads_price_detects_positive_lag():
    # M0(3개월전) 매수우위지수 낮음(90) -> M1(2개월전) 매매가 -10%
    # M1(2개월전) 매수우위지수 높음(150) -> M2(1개월전) 매매가 +20%
    # 매수우위지수 높았던 달일수록 다음달 상승폭이 커야 가설 지지(양의 상관)
    rows_t = []
    for i in range(3):
        rows_t.append(_trade(_month_ago_days(3) + i, ppp=10000))
        rows_t.append(_trade(_month_ago_days(2) + i, ppp=9000))    # M0->M1 -10%
        rows_t.append(_trade(_month_ago_days(1) + i, ppp=10800))   # M1->M2 +20%
    upsert_trades(rows_t)

    m0 = (pd.Timestamp.today() - pd.Timedelta(days=_month_ago_days(3))).date()
    m1 = (pd.Timestamp.today() - pd.Timedelta(days=_month_ago_days(2))).date()
    with session_scope() as s:
        s.add(KbSentimentIndex(region_code="11", ym_date=m0, sentiment_index=90.0,
                                buy_more_pct=20, sell_more_pct=30, similar_pct=50, source="test"))
        s.add(KbSentimentIndex(region_code="11", ym_date=m1, sentiment_index=150.0,
                                buy_more_pct=60, sell_more_pct=10, similar_pct=30, source="test"))

    r = v.test_buyer_sentiment_leads_price(months=6, min_deals=3)
    assert r.n >= 2
    assert r.statistic > 0  # 매수우위지수 높을수록 다음달 상승폭 큼 -> 양의 상관


def test_buyer_sentiment_leads_price_empty_when_no_data():
    r = v.test_buyer_sentiment_leads_price()
    assert r.n == 0
