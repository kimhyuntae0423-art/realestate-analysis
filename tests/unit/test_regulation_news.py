"""src/collectors/regulation_news.py — 규제 뉴스 감지 검증 (HTTP는 mock)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from src.collectors import regulation_news as mod


class _FakeResponse:
    def __init__(self, documents):
        self._documents = documents

    def json(self):
        return {"documents": self._documents}


class _FakeClient:
    def __init__(self, documents):
        self._documents = documents

    def get(self, url, params=None):
        return _FakeResponse(self._documents)


def _doc(days_ago, title="<b>규제</b> 완화", url="https://news/1"):
    dt = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    return {"title": title, "url": url, "datetime": dt, "contents": "본문 요약"}


@pytest.fixture(autouse=True)
def _isolated_output_file(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "OUTPUT_FILE", tmp_path / "regulation_news.json")


def test_search_news_strips_bold_tags_and_filters_by_cutoff():
    client = _FakeClient([_doc(days_ago=5), _doc(days_ago=60, url="https://news/old")])
    out = mod._search_news("키워드", client, days=30)
    assert len(out) == 1
    assert out[0]["title"] == "규제 완화"


def test_search_news_returns_empty_on_client_exception():
    class _RaisingClient:
        def get(self, *a, **kw):
            raise RuntimeError("network down")
    assert mod._search_news("키워드", _RaisingClient()) == []


def test_collect_regulation_news_skips_without_api_key(monkeypatch):
    monkeypatch.setattr(mod, "KAKAO_REST_API_KEY", "")
    out = mod.collect_regulation_news()
    assert out["count"] == 0
    assert not mod.OUTPUT_FILE.exists()


def test_collect_regulation_news_dedupes_and_sorts(monkeypatch, mocker):
    monkeypatch.setattr(mod, "KAKAO_REST_API_KEY", "dummy-key")

    def _fake_search_news(keyword, client, days=30):
        # 같은 URL이 여러 키워드에서 중복으로 잡히는 상황 시뮬레이션
        return [
            {"title": f"{keyword} 기사", "url": "https://news/dup",
             "datetime": "2026-01-01", "source": "", "keyword": keyword},
            {"title": f"{keyword} 최신", "url": f"https://news/{keyword}",
             "datetime": "2026-06-01", "source": "", "keyword": keyword},
        ]
    mocker.patch.object(mod, "_search_news", side_effect=_fake_search_news)

    out = mod.collect_regulation_news(days=30)
    urls = [a["url"] for a in out["articles"]]
    assert urls.count("https://news/dup") == 1  # 중복 제거
    assert out["articles"][0]["datetime"] == "2026-06-01"  # 최신순 정렬
    assert mod.OUTPUT_FILE.exists()


def test_load_regulation_news_missing_file_returns_none():
    assert mod.load_regulation_news() is None


def test_load_regulation_news_reads_saved_file():
    mod.OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"collected_at": "2026-01-01", "count": 1, "articles": []}
    mod.OUTPUT_FILE.write_text(json.dumps(payload), encoding="utf-8")
    assert mod.load_regulation_news() == payload


def test_load_regulation_news_malformed_json_returns_none():
    mod.OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    mod.OUTPUT_FILE.write_text("{not valid json", encoding="utf-8")
    assert mod.load_regulation_news() is None
