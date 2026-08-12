"""src/analysis/macro.py — 매크로 신호등 검증 (DB fixture 기반, 상대 날짜 사용).

signal_* 함수들은 date.today() 기준 상대 기간을 DB에서 조회하므로,
테스트 데이터도 실행 시점 today 기준 상대 날짜로 삽입해 시간에 안전하게 만든다.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.analysis import macro
from src.database.repository import upsert_trades, upsert_rents


def _trade_row(days_ago, region="11680", ppp=6000, amount=100000):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": "A",
            "area_m2": 84.9, "deal_amount": amount, "price_per_pyeong": ppp}


def _rent_row(days_ago, region="11680", deposit=70000, monthly_rent=0):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": "A",
            "area_m2": 84.9, "deposit": deposit, "monthly_rent": monthly_rent}


def test_signal_volume_momentum_no_data():
    out = macro.signal_volume_momentum()
    assert out["level"] == "yellow"
    assert out["value"] == "N/A"


def test_signal_volume_momentum_recent_surge_is_green():
    # 최근 3mo에 거래 몰림 (recent/prior >= 1.2 → green)
    rows = [_trade_row(d) for d in [10, 20, 30, 40, 50]]  # 최근 3mo(=90일) 내 5건
    rows += [_trade_row(d) for d in [100]]                 # 이전 3mo 1건
    upsert_trades(rows)
    out = macro.signal_volume_momentum()
    assert out["level"] == "green"


def test_signal_jeonse_ratio_computes_percentage():
    upsert_trades([_trade_row(10, amount=100000)])
    upsert_rents([_rent_row(10, deposit=70000)])
    out = macro.signal_jeonse_ratio()
    assert out["value"] == "70.0%"
    assert out["level"] == "green"  # 70% >= threshold


def test_signal_jeonse_ratio_no_data_is_yellow():
    out = macro.signal_jeonse_ratio()
    assert out["level"] == "yellow"
    assert out["value"] == "N/A"


def test_signal_regulation_is_static_red():
    out = macro.signal_regulation()
    assert out["level"] == "red"


def test_signal_interest_rate_is_static_yellow():
    out = macro.signal_interest_rate()
    assert out["level"] == "yellow"


def test_signal_supply_levels(tmp_path, monkeypatch):
    monkeypatch.setattr(macro, "ROOT", tmp_path)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()

    def _write(total_units):
        with open(cfg_dir / "supply.json", "w", encoding="utf-8") as f:
            json.dump({"by_region": {"11680": {"2026-01": total_units}}}, f)

    _write(10000)
    assert macro.signal_supply()["level"] == "green"   # < 30000
    _write(40000)
    assert macro.signal_supply()["level"] == "yellow"  # 30000~60000
    _write(70000)
    assert macro.signal_supply()["level"] == "red"     # >= 60000


def test_macro_dashboard_returns_six_signals():
    out = macro.macro_dashboard()
    assert len(out) == 6
    assert {s["name"] for s in out} == {
        "대출 규제", "기준금리", "거래량 동향", "전세가율", "공급량", "가격 모멘텀",
    }
