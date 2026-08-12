"""src/analysis/supply.py — 입주물량 분석 검증 (config/supply.json 목킹).

_load_supply()가 lru_cache이므로 각 테스트 전후로 cache_clear() 하고
src.analysis.supply.ROOT 를 tmp_path로 monkeypatch 해서 실제 운영 config를 건드리지 않는다.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.analysis import supply


@pytest.fixture(autouse=True)
def _isolated_supply_config(tmp_path, monkeypatch):
    supply._load_supply.cache_clear()
    monkeypatch.setattr(supply, "ROOT", tmp_path)
    yield
    supply._load_supply.cache_clear()


def _write_supply_json(tmp_path, data):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg_dir / "supply.json", "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_supply_for_region_sums_within_lookahead_window(tmp_path):
    today = pd.Timestamp.today().to_period("M").to_timestamp()
    in_window_ym = (today + pd.DateOffset(months=3)).strftime("%Y-%m")
    out_of_window_ym = (today + pd.DateOffset(months=20)).strftime("%Y-%m")
    _write_supply_json(tmp_path, {
        "by_region": {"11680": {in_window_ym: 1000, out_of_window_ym: 5000}}
    })
    total = supply.supply_for_region("11680", lookahead_months=12)
    assert total == 1000


def test_supply_for_region_missing_region_returns_zero(tmp_path):
    _write_supply_json(tmp_path, {"by_region": {}})
    assert supply.supply_for_region("11680") == 0


def test_supply_pressure_score_scales_linearly(tmp_path):
    today = pd.Timestamp.today().to_period("M").to_timestamp()
    ym = (today + pd.DateOffset(months=1)).strftime("%Y-%m")
    _write_supply_json(tmp_path, {"by_region": {"11680": {ym: 1000}}})
    assert supply.supply_pressure_score("11680") == 20.0  # 1000/50


def test_supply_pressure_score_caps_at_100(tmp_path):
    today = pd.Timestamp.today().to_period("M").to_timestamp()
    ym = (today + pd.DateOffset(months=1)).strftime("%Y-%m")
    _write_supply_json(tmp_path, {"by_region": {"11680": {ym: 100000}}})
    assert supply.supply_pressure_score("11680") == 100.0


def test_supply_table_lists_all_regions(tmp_path):
    _write_supply_json(tmp_path, {"by_region": {
        "11680": {"2026-01": 100, "2026-02": 200},
        "11650": {"2026-01": 50},
    }})
    out = supply.supply_table()
    assert set(out["region_code"]) == {"11680", "11650"}
    assert out[out["region_code"] == "11680"]["total_units"].iloc[0] == 300
