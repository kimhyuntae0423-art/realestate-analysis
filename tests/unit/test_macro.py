"""src/analysis/macro.py — 매크로 신호등 검증 (DB fixture 기반, 상대 날짜 사용).

signal_* 함수들은 date.today() 기준 상대 기간을 DB에서 조회하므로,
테스트 데이터도 실행 시점 today 기준 상대 날짜로 삽입해 시간에 안전하게 만든다.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.analysis import macro
from src.database.repository import upsert_trades, upsert_rents, upsert_ecos_series


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
    # 단지+평형 유닛 매칭 방식(2026-08-17 재설계) — 매매ppp=6000, 전세ppp=deposit/84.9*3.3058
    # 이 되도록 deposit=115570으로 잡으면 두 ppp의 비율이 정확히 75.0%가 됨
    upsert_trades([_trade_row(10, ppp=6000)])
    upsert_rents([_rent_row(10, deposit=115570)])
    out = macro.signal_jeonse_ratio()
    assert out["value"] == "75.0%"
    assert out["level"] == "yellow"  # 실험실 검증 결과 선행지표 아님 — 항상 참고용(yellow)


def test_signal_jeonse_ratio_no_data_is_yellow():
    out = macro.signal_jeonse_ratio()
    assert out["level"] == "yellow"
    assert out["value"] == "N/A"


def test_signal_regulation_is_static_red():
    out = macro.signal_regulation()
    assert out["level"] == "red"


def test_signal_interest_rate_no_data_is_yellow():
    out = macro.signal_interest_rate()
    assert out["level"] == "yellow"
    assert out["value"] == "N/A"


def _base_rate_rows(values):
    base = pd.Timestamp.today().replace(day=1)
    rows = []
    for i, v in enumerate(reversed(values)):
        d = (base - pd.DateOffset(months=i)).date()
        rows.append({"series": "base_rate", "ym_date": d, "value": v, "source": "test"})
    return rows


def test_signal_interest_rate_cut_is_green():
    # 3개월 전 3.50% -> 이번달 3.25% (인하 0.25%p)
    upsert_ecos_series(_base_rate_rows([3.50, 3.50, 3.50, 3.25]))
    out = macro.signal_interest_rate()
    assert out["level"] == "green"
    assert out["value"] == "3.25%"
    assert "인하" in out["detail"]


def test_signal_interest_rate_hike_is_red():
    # 3개월 전 3.50% -> 이번달 3.75% (인상 0.25%p)
    upsert_ecos_series(_base_rate_rows([3.50, 3.50, 3.50, 3.75]))
    out = macro.signal_interest_rate()
    assert out["level"] == "red"
    assert "인상" in out["detail"]


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
