"""src/analysis/location.py — 입지 점수 계산/캐싱 검증 (카카오 API는 mock).

KakaoClient(실제 HTTP 호출)는 stage 5 collectors 테스트에서 별도로 검증한다.
여기서는 location.py 자체 로직(점수 계산식, 캐시 hit/miss, 키 부재 처리)만 검증.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.analysis import location


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(location, "CACHE_PATH", tmp_path / "apt_locations.json")


def test_is_kakao_ready_reflects_api_key(monkeypatch):
    monkeypatch.setattr(location, "KAKAO_REST_API_KEY", "")
    assert location.is_kakao_ready() is False
    monkeypatch.setattr(location, "KAKAO_REST_API_KEY", "dummy-key")
    assert location.is_kakao_ready() is True


def test_lookup_or_fetch_returns_none_without_key(monkeypatch):
    monkeypatch.setattr(location, "KAKAO_REST_API_KEY", "")
    assert location.lookup_or_fetch("11680", "래미안A") is None


def test_lookup_or_fetch_uses_cache_without_calling_api(monkeypatch, mocker):
    monkeypatch.setattr(location, "KAKAO_REST_API_KEY", "dummy-key")
    location.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cached = {"11680::래미안A": {"lat": 1.0, "lon": 2.0, "n_subway": 1,
                                  "n_school": 1, "n_mart": 1, "n_hospital": 1,
                                  "score": 50.0, "fetched_at": "x"}}
    with open(location.CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cached, f)

    mock_client_cls = mocker.patch("src.collectors.kakao_api.KakaoClient")
    rec = location.lookup_or_fetch("11680", "래미안A")
    assert rec["score"] == 50.0
    mock_client_cls.assert_not_called()


def test_lookup_or_fetch_scores_close_amenities_as_max(monkeypatch, mocker):
    monkeypatch.setattr(location, "KAKAO_REST_API_KEY", "dummy-key")
    mock_client = mocker.Mock()
    mock_client.geocode.return_value = (37.5, 127.0)
    mock_client.nearby.side_effect = [
        [{"distance": "200"}],                                   # 지하철 300m 이내 → 40점
        [{"distance": "100"}] * 5,                                # 학교 5개+ → 30점
        [{"distance": "250"}],                                   # 마트 300m 이내 → 20점
        [{"distance": "100"}] * 5,                                # 병원 5개+ → 10점
    ]
    mocker.patch("src.collectors.kakao_api.KakaoClient", return_value=mock_client)

    rec = location.lookup_or_fetch("11680", "래미안A")
    assert rec["score"] == 100.0


def test_lookup_or_fetch_scores_no_amenities_as_zero(monkeypatch, mocker):
    monkeypatch.setattr(location, "KAKAO_REST_API_KEY", "dummy-key")
    mock_client = mocker.Mock()
    mock_client.geocode.return_value = (37.5, 127.0)
    mock_client.nearby.side_effect = [[], [], [], []]
    mocker.patch("src.collectors.kakao_api.KakaoClient", return_value=mock_client)

    rec = location.lookup_or_fetch("11680", "래미안A")
    assert rec["score"] == 0.0


def test_lookup_or_fetch_geocode_failure_caches_none(monkeypatch, mocker):
    monkeypatch.setattr(location, "KAKAO_REST_API_KEY", "dummy-key")
    mock_client = mocker.Mock()
    mock_client.geocode.return_value = None
    mocker.patch("src.collectors.kakao_api.KakaoClient", return_value=mock_client)

    rec = location.lookup_or_fetch("11680", "없는단지")
    assert rec is None
    with open(location.CACHE_PATH, encoding="utf-8") as f:
        cache = json.load(f)
    assert cache["11680::없는단지"] is None


def test_enrich_with_location_without_key_sets_na_column(monkeypatch):
    monkeypatch.setattr(location, "KAKAO_REST_API_KEY", "")
    df = pd.DataFrame([{"region_code": "11680", "apt_name": "래미안A"}])
    out = location.enrich_with_location(df)
    assert pd.isna(out.loc[0, "location_score"])


def test_enrich_with_location_empty_df_passthrough():
    df = pd.DataFrame()
    assert location.enrich_with_location(df).empty
