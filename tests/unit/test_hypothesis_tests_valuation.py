"""src/analysis/hypothesis_tests_valuation.py — 가치평가/밸류에이션 계열 가설 검증."""
from __future__ import annotations

import pandas as pd

from src.analysis import hypothesis_tests_valuation as v
from src.database.repository import upsert_trades, upsert_rents


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
