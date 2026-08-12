"""src/analysis/forward_signals.py — 선행 지표 시그널 검증 (DB fixture, 상대 날짜).

as_of 기준 상대 기간을 DB에서 읽으므로, 테스트 데이터도 as_of 기준 상대 날짜로 삽입한다.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.analysis import forward_signals as fs
from src.database.repository import upsert_trades, upsert_rents
from src.database.models import SupplySchedule, PopulationFlow
from src.database.repository import session_scope

AS_OF = pd.Timestamp("2026-06-01").date()


def _trade(days_before_as_of, region="11680", apt="A", ppp=6000, amount=100000, area=84.9):
    d = (pd.Timestamp(AS_OF) - pd.Timedelta(days=days_before_as_of)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


def _rent(days_before_as_of, region="11680", apt="A", deposit=70000, area=84.9):
    d = (pd.Timestamp(AS_OF) - pd.Timedelta(days=days_before_as_of)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deposit": deposit, "monthly_rent": 0}


def test_apt_relative_strength_flags_outperformer():
    rows = []
    # 시군구 평균 대비 A단지가 더 크게 오름 (prior 100 days ago vs recent 30 days ago)
    for i in range(3):
        rows.append(_trade(280 + i, apt="A", ppp=6000))  # prior
        rows.append(_trade(280 + i, apt="B", ppp=6000))
    for i in range(3):
        rows.append(_trade(40 + i, apt="A", ppp=9000))   # recent: A +50%
        rows.append(_trade(40 + i, apt="B", ppp=6300))   # recent: B +5%
    upsert_trades(rows)
    out = fs.apt_relative_strength(as_of=AS_OF, months=12, min_deals=2)
    assert not out.empty
    a_row = out[out["apt_name"] == "A"].iloc[0]
    b_row = out[out["apt_name"] == "B"].iloc[0]
    assert a_row["rs_score"] > b_row["rs_score"]


def test_apt_relative_strength_empty_when_no_data():
    assert fs.apt_relative_strength(as_of=AS_OF).empty


def test_jeonse_ratio_acceleration_detects_rising_ratio():
    rows_t, rows_r = [], []
    for i in range(3):
        rows_t.append(_trade(280 + i, amount=100000))
        rows_r.append(_rent(280 + i, deposit=50000))   # prior ratio 50%
    for i in range(3):
        rows_t.append(_trade(40 + i, amount=100000))
        rows_r.append(_rent(40 + i, deposit=70000))    # recent ratio 70%
    upsert_trades(rows_t)
    upsert_rents(rows_r)
    out = fs.jeonse_ratio_acceleration(as_of=AS_OF, months=12, min_deals=2)
    assert not out.empty
    row = out.iloc[0]
    assert row["jeonse_accel_%p"] > 0
    assert row["jeonse_accel_score"] > 50


def test_supply_pressure_scores_inversely_to_units():
    with session_scope() as s:
        s.add(SupplySchedule(region_code="11680", move_in_date=AS_OF, units=0, source="test"))
        s.add(SupplySchedule(region_code="11650", move_in_date=AS_OF, units=10000, source="test"))
    out = fs.supply_pressure(as_of=AS_OF)
    assert not out.empty
    low_supply = out[out["region_code"] == "11680"].iloc[0]["supply_pressure_score"]
    high_supply = out[out["region_code"] == "11650"].iloc[0]["supply_pressure_score"]
    assert low_supply == 100.0
    assert high_supply == 0.0


def test_population_inflow_scores_around_midpoint_at_zero_net():
    with session_scope() as s:
        s.add(PopulationFlow(region_code="11680", flow_date=AS_OF,
                              inflow=100, outflow=100, net_inflow=0, source="test"))
        s.add(PopulationFlow(region_code="11650", flow_date=AS_OF,
                              inflow=1000, outflow=0, net_inflow=1000, source="test"))
    out = fs.population_inflow(as_of=AS_OF)
    zero_net = out[out["region_code"] == "11680"].iloc[0]["population_score"]
    positive_net = out[out["region_code"] == "11650"].iloc[0]["population_score"]
    assert zero_net == 50.0
    assert positive_net > 50.0


def test_region_market_score_ranks_by_median_ppp():
    rows = []
    for i in range(25):
        rows.append(_trade(10 + i, region="11680", ppp=9000))  # 비싼 지역
    for i in range(25):
        rows.append(_trade(10 + i, region="11650", ppp=4000))  # 저렴한 지역
    upsert_trades(rows)
    out = fs.region_market_score(as_of=AS_OF, min_deals=20)
    high = out[out["region_code"] == "11680"].iloc[0]["market_score"]
    low = out[out["region_code"] == "11650"].iloc[0]["market_score"]
    assert high > low


def test_apt_prestige_score_ranks_premium_apt_higher():
    rows = []
    for i in range(3):
        rows.append(_trade(10 + i, apt="프리미엄", ppp=9000))
        rows.append(_trade(10 + i, apt="평범", ppp=6000))
    upsert_trades(rows)
    out = fs.apt_prestige_score(as_of=AS_OF, min_deals=2)
    premium = out[out["apt_name"] == "프리미엄"].iloc[0]["prestige_score"]
    normal = out[out["apt_name"] == "평범"].iloc[0]["prestige_score"]
    assert premium > normal
