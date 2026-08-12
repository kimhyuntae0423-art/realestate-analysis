"""src/collectors/molit_api.py — 국토부 실거래가 수집기 검증 (HTTP는 mock).

RAW_DIR는 tmp_path로 monkeypatch해서 실제 data/raw/ 를 건드리지 않는다.
"""
from __future__ import annotations

import pytest

from src.collectors import molit_api as mod
from src.collectors.molit_api import MolitCollector


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


_SINGLE_ITEM_XML = """<?xml version="1.0"?>
<response><header><resultCode>000</resultCode></header>
<body><items><item>
<dealYear>2025</dealYear><dealMonth>6</dealMonth><dealDay>1</dealDay>
<aptNm>래미안A</aptNm><excluUseAr>84.9</excluUseAr><dealAmount>150,000</dealAmount>
</item></items><totalCount>1</totalCount></body></response>"""

_MULTI_ITEM_XML = """<?xml version="1.0"?>
<response><header><resultCode>000</resultCode></header>
<body><items>
<item><dealYear>2025</dealYear><dealMonth>6</dealMonth><dealDay>1</dealDay>
<aptNm>A</aptNm><excluUseAr>84.9</excluUseAr><dealAmount>100000</dealAmount></item>
<item><dealYear>2025</dealYear><dealMonth>6</dealMonth><dealDay>2</dealDay>
<aptNm>B</aptNm><excluUseAr>59.9</excluUseAr><dealAmount>80000</dealAmount></item>
</items><totalCount>2</totalCount></body></response>"""

_ERROR_XML = """<?xml version="1.0"?>
<response><header><resultCode>99</resultCode><resultMsg>SERVICE ERROR</resultMsg></header></response>"""

_RENT_XML = """<?xml version="1.0"?>
<response><header><resultCode>000</resultCode></header>
<body><items><item>
<dealYear>2025</dealYear><dealMonth>6</dealMonth><dealDay>1</dealDay>
<aptNm>A</aptNm><excluUseAr>84.9</excluUseAr><deposit>70,000</deposit><monthlyRent>0</monthlyRent>
</item></items><totalCount>1</totalCount></body></response>"""


@pytest.fixture(autouse=True)
def _isolated_raw_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "RAW_DIR", tmp_path)


def test_constructor_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(mod, "DATA_GO_KR_API_KEY", "")
    with pytest.raises(RuntimeError, match="DATA_GO_KR_API_KEY"):
        MolitCollector(api_key="")


def test_fetch_trades_parses_single_item(mocker):
    collector = MolitCollector(api_key="dummy")
    mocker.patch.object(collector.http, "get", return_value=_FakeResponse(_SINGLE_ITEM_XML))
    rows = collector.fetch_trades("11680", "202506")
    assert len(rows) == 1
    assert rows[0]["apt_name"] == "래미안A"
    assert rows[0]["deal_amount"] == 150000
    assert (mod.RAW_DIR / "trade_11680_202506.json").exists()


def test_fetch_trades_parses_multiple_items(mocker):
    collector = MolitCollector(api_key="dummy")
    mocker.patch.object(collector.http, "get", return_value=_FakeResponse(_MULTI_ITEM_XML))
    rows = collector.fetch_trades("11680", "202506")
    assert {r["apt_name"] for r in rows} == {"A", "B"}


def test_fetch_trades_paginates_until_total_count_reached(mocker):
    collector = MolitCollector(api_key="dummy")
    page1 = _SINGLE_ITEM_XML.replace("<totalCount>1</totalCount>", "<totalCount>2</totalCount>")
    page2 = _SINGLE_ITEM_XML.replace("래미안A", "래미안B").replace(
        "<totalCount>1</totalCount>", "<totalCount>2</totalCount>")
    mock_get = mocker.patch.object(collector.http, "get")
    mock_get.side_effect = [_FakeResponse(page1), _FakeResponse(page2)]
    rows = collector.fetch_trades("11680", "202506")
    assert mock_get.call_count == 2
    assert {r["apt_name"] for r in rows} == {"래미안A", "래미안B"}


def test_fetch_trades_raises_on_api_error_body(mocker):
    collector = MolitCollector(api_key="dummy")
    mocker.patch.object(collector.http, "get", return_value=_FakeResponse(_ERROR_XML))
    with pytest.raises(RuntimeError, match="API 오류"):
        collector.fetch_trades("11680", "202506")


def test_fetch_trades_raises_on_non_xml_response(mocker):
    collector = MolitCollector(api_key="dummy")
    mocker.patch.object(collector.http, "get",
                         return_value=_FakeResponse("SERVICE_KEY_IS_NOT_REGISTERED_ERROR"))
    with pytest.raises(RuntimeError, match="비정상 응답"):
        collector.fetch_trades("11680", "202506")


def test_fetch_rents_parses_deposit_and_rent(mocker):
    collector = MolitCollector(api_key="dummy")
    mocker.patch.object(collector.http, "get", return_value=_FakeResponse(_RENT_XML))
    rows = collector.fetch_rents("11680", "202506")
    assert len(rows) == 1
    assert rows[0]["deposit"] == 70000
    assert rows[0]["monthly_rent"] == 0
    assert (mod.RAW_DIR / "rent_11680_202506.json").exists()
