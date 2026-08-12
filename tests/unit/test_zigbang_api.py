"""src/collectors/zigbang_api.py — 직방 검색/딥링크 생성 검증 (HTTP는 mock)."""
from __future__ import annotations

import pandas as pd
import pytest
import requests

from src.collectors import zigbang_api as mod


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


def test_search_apt_complex_dict_with_items(mocker):
    mocker.patch.object(mod._SESSION, "get",
                         return_value=_FakeResponse(200, {"items": [{"id": 1}]}))
    out = mod.search_apt_complex("래미안")
    assert out == [{"id": 1}]


def test_search_apt_complex_bare_list_response(mocker):
    mocker.patch.object(mod._SESSION, "get", return_value=_FakeResponse(200, [{"id": 2}]))
    out = mod.search_apt_complex("래미안")
    assert out == [{"id": 2}]


def test_search_apt_complex_non_200_returns_empty(mocker):
    mocker.patch.object(mod._SESSION, "get", return_value=_FakeResponse(500, {}))
    assert mod.search_apt_complex("래미안") == []


def test_search_apt_complex_swallows_exceptions(mocker):
    mocker.patch.object(mod._SESSION, "get", side_effect=requests.ConnectionError("boom"))
    assert mod.search_apt_complex("래미안") == []


@pytest.mark.parametrize("item,expected", [
    ({"item_id": "111"}, "111"),
    ({"itemId": "222"}, "222"),
    ({"id": "333"}, "333"),
    ({"complexId": "444"}, "444"),
    ({}, None),
])
def test_complex_id_checks_aliases_in_order(item, expected):
    assert mod._complex_id(item) == expected


def test_make_links_with_id_points_to_complex_page():
    links = mod._make_links("래미안A", zigbang_id="999")
    assert links["직방_url"] == "https://www.zigbang.com/home/apt/complexes/999"
    assert "래미안A" not in links["직방_url"]  # ID가 있으면 검색어 대신 ID 경로 사용


def test_make_links_without_id_falls_back_to_search():
    links = mod._make_links("래미안 A", zigbang_id=None)
    assert "zigbang.com/home/apt?q=" in links["직방_url"]
    assert "%20" in links["직방_url"] or "+" in links["직방_url"]  # URL 인코딩 확인


def test_fetch_links_for_complexes_extracts_metadata(mocker):
    mocker.patch.object(mod, "search_apt_complex", return_value=[{
        "item_id": "555",
        "_source": {"신주소": "서울시 강남구", "사용승인일": "20150315", "enabled2": "12"},
    }])
    out = mod.fetch_links_for_complexes(["래미안A"], delay=0)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["zigbang_id"] == "555"
    assert row["주소"] == "서울시 강남구"
    assert row["사용승인"] == "2015"
    assert row["직방매물(추정)"] == 12


def test_fetch_links_for_complexes_handles_search_failure(mocker):
    mocker.patch.object(mod, "search_apt_complex", return_value=[])
    out = mod.fetch_links_for_complexes(["없는단지"], delay=0)
    assert len(out) == 1
    assert out.iloc[0]["zigbang_id"] is None
    assert "zigbang.com/home/apt?q=" in out.iloc[0]["직방_url"]


def test_fetch_links_for_complexes_empty_input_returns_empty_df():
    assert mod.fetch_links_for_complexes([], delay=0).empty
