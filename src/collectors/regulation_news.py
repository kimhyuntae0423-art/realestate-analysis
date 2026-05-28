"""부동산 대출규제 변경 뉴스 감지 (카카오 Daum 뉴스 검색)

목적: 자동 반영 아님 — 규제 변경 가능성 감지 후 사용자에게 알림만.
수치 파싱은 하지 않고, 기사 제목·링크·날짜만 저장한다.
"""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from config.settings import KAKAO_REST_API_KEY, RAW_DIR
from src.collectors.base import HttpClient
from src.utils.logger import get_logger

log = get_logger(__name__)

KAKAO_SEARCH_URL = "https://dapi.kakao.com/v2/search/news"

# 규제 변경 관련 검색 키워드 (Daum 뉴스 검색)
KEYWORDS = [
    "부동산 대출규제 변경",
    "LTV DSR 규제 완화",
    "투기과열지구 조정대상지역",
    "주담대 규제 개편",
]

OUTPUT_FILE = RAW_DIR / "regulation_news.json"


def _search_news(keyword: str, client: HttpClient, days: int = 30) -> list[dict]:
    """카카오 뉴스 검색 → 최근 N일 기사 반환."""
    try:
        resp = client.get(
            KAKAO_SEARCH_URL,
            params={"query": keyword, "size": 10, "sort": "recency"},
        )
        items = resp.json().get("documents", [])
    except Exception as e:
        log.warning("뉴스 검색 실패 [%s]: %s", keyword, e)
        return []

    cutoff = datetime.now() - timedelta(days=days)
    results = []
    for item in items:
        try:
            dt = datetime.strptime(item["datetime"][:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            continue
        if dt < cutoff:
            continue
        results.append({
            "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
            "url": item.get("url", ""),
            "datetime": item["datetime"][:10],
            "source": item.get("contents", "")[:80],
            "keyword": keyword,
        })
    return results


def collect_regulation_news(days: int = 30) -> dict:
    """
    규제 관련 최근 뉴스를 수집해 data/raw/regulation_news.json에 저장.

    Returns:
        {"collected_at": "...", "articles": [...], "count": N}
    """
    if not KAKAO_REST_API_KEY:
        log.warning("KAKAO_REST_API_KEY 없음 — 규제 뉴스 수집 건너뜀")
        return {"collected_at": date.today().isoformat(), "articles": [], "count": 0}

    client = HttpClient(base_headers={"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"})

    seen_urls: set[str] = set()
    articles: list[dict] = []
    for kw in KEYWORDS:
        for art in _search_news(kw, client, days=days):
            if art["url"] not in seen_urls:
                seen_urls.add(art["url"])
                articles.append(art)

    # 최신 순 정렬
    articles.sort(key=lambda x: x["datetime"], reverse=True)

    result = {
        "collected_at": date.today().isoformat(),
        "days_window": days,
        "count": len(articles),
        "articles": articles,
    }
    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("규제 뉴스 수집 완료: %d건 (최근 %d일)", len(articles), days)
    return result


def load_regulation_news() -> dict | None:
    """저장된 규제 뉴스 파일 로드. 없으면 None."""
    if not OUTPUT_FILE.exists():
        return None
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
