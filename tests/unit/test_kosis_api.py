"""src/collectors/kosis_api.py — KOSIS OpenAPI 수집기 검증 (HTTP는 mock)."""
from __future__ import annotations

import pytest
import requests

from src.collectors.kosis_api import KosisCollector


class _FakeResponse:
    def __init__(self, json_data, status_ok=True):
        self._json = json_data
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            raise requests.HTTPError("500 Server Error")

    def json(self):
        return self._json


def test_constructor_raises_without_api_key(monkeypatch):
    import src.collectors.kosis_api as mod
    monkeypatch.setattr(mod, "KOSIS_API_KEY", "")
    with pytest.raises(RuntimeError, match="KOSIS_API_KEY"):
        KosisCollector(api_key="")


def test_fetch_population_flow_returns_list(mocker):
    fake_data = [{"prdDe": "202506", "C1": "11680", "ITM_ID": "T30", "DT": "500"}]
    mocker.patch("src.collectors.kosis_api.requests.get",
                 return_value=_FakeResponse(fake_data))
    collector = KosisCollector(api_key="dummy")
    out = collector.fetch_population_flow("202401", "202506")
    assert out == fake_data


def test_fetch_population_flow_raises_on_kosis_error_payload(mocker):
    mocker.patch("src.collectors.kosis_api.requests.get",
                 return_value=_FakeResponse({"err": "31", "errMsg": "잘못된 요청"}))
    collector = KosisCollector(api_key="dummy")
    with pytest.raises(RuntimeError, match="KOSIS error"):
        collector.fetch_population_flow("202401", "202506")


def test_fetch_population_flow_non_list_response_returns_empty(mocker):
    mocker.patch("src.collectors.kosis_api.requests.get",
                 return_value=_FakeResponse({"unexpected": "shape"}))
    collector = KosisCollector(api_key="dummy")
    assert collector.fetch_population_flow("202401", "202506") == []


def test_fetch_population_flow_raises_on_http_error(mocker):
    mocker.patch("src.collectors.kosis_api.requests.get",
                 return_value=_FakeResponse([], status_ok=False))
    collector = KosisCollector(api_key="dummy")
    with pytest.raises(requests.HTTPError):
        collector.fetch_population_flow("202401", "202506")


def test_fetch_supply_schedule_uses_same_get_pipeline(mocker):
    fake_data = [{"prdDe": "202506", "C1": "41", "DT": "1000"}]
    mock_get = mocker.patch("src.collectors.kosis_api.requests.get",
                             return_value=_FakeResponse(fake_data))
    collector = KosisCollector(api_key="dummy")
    out = collector.fetch_supply_schedule("202401", "202506")
    assert out == fake_data
    params = mock_get.call_args.kwargs["params"]
    assert params["tblId"] == "DT_116N_INSURING_001"
