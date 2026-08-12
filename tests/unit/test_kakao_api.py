"""src/collectors/kakao_api.py — 카카오 로컬 API 클라이언트 검증 (HTTP는 mock)."""
from __future__ import annotations

import pytest

from src.collectors import kakao_api as mod
from src.collectors.kakao_api import KakaoClient


class _FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def json(self):
        return self._json


def test_constructor_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(mod, "KAKAO_REST_API_KEY", "")
    with pytest.raises(RuntimeError, match="KAKAO_REST_API_KEY"):
        KakaoClient(api_key=None)


def test_geocode_prefers_apartment_match_among_keyword_results(mocker):
    client = KakaoClient(api_key="dummy")
    docs = [
        {"place_name": "래미안A 상가", "category_name": "부동산", "y": "37.1", "x": "127.1"},
        {"place_name": "래미안A아파트", "category_name": "아파트", "y": "37.5", "x": "127.0"},
    ]
    mocker.patch.object(client.http, "get", return_value=_FakeResponse({"documents": docs}))
    lat, lon = client.geocode("래미안A")
    assert (lat, lon) == (37.5, 127.0)


def test_geocode_falls_back_to_address_search_when_keyword_empty(mocker):
    client = KakaoClient(api_key="dummy")
    mock_get = mocker.patch.object(client.http, "get")
    mock_get.side_effect = [
        _FakeResponse({"documents": []}),
        _FakeResponse({"documents": [{"y": "37.2", "x": "127.3"}]}),
    ]
    lat, lon = client.geocode("어떤주소")
    assert (lat, lon) == (37.2, 127.3)
    assert mock_get.call_count == 2


def test_geocode_returns_none_when_nothing_found(mocker):
    client = KakaoClient(api_key="dummy")
    mocker.patch.object(client.http, "get", return_value=_FakeResponse({"documents": []}))
    assert client.geocode("존재안함") is None


def test_nearby_returns_documents(mocker):
    client = KakaoClient(api_key="dummy")
    docs = [{"place_name": "강남역", "distance": "200"}]
    mock_get = mocker.patch.object(client.http, "get", return_value=_FakeResponse({"documents": docs}))
    out = client.nearby(37.5, 127.0, "SW8", radius=1000)
    assert out == docs
    params = mock_get.call_args.kwargs["params"]
    assert params["category_group_code"] == "SW8"
    assert params["x"] == 127.0 and params["y"] == 37.5
