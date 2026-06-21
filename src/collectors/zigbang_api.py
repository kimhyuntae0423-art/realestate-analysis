"""직방 검색 API — 단지 ID 조회 + 플랫폼 딥링크 생성

직방/네이버/호갱노노의 매물 임베드 API는 인증 또는 비공개여서 접근 불가.
대신 직방 공개 검색 API로 단지 ID를 확인하고,
각 플랫폼 단지 페이지 URL을 생성해 반환한다.
"""
from __future__ import annotations
import logging
import time
import urllib.parse

import requests
import pandas as pd

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.zigbang.com/",
    "Accept": "application/json, text/plain, */*",
})


def search_apt_complex(name: str, timeout: int = 8) -> list[dict]:
    """단지명으로 직방 아파트 단지 검색."""
    try:
        resp = _SESSION.get(
            "https://apis.zigbang.com/v2/search",
            params={"q": name, "serviceType": "아파트", "leaseYn": "N"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return data.get("items", [])
            if isinstance(data, list):
                return data
    except Exception as e:
        log.debug("직방 검색 오류 (%s): %s", name, e)
    return []


def _complex_id(item: dict) -> str | None:
    for k in ("item_id", "itemId", "id", "complexId"):
        v = item.get(k)
        if v:
            return str(v)
    return None


def _make_links(apt_name: str, zigbang_id: str | None = None) -> dict:
    """단지명 + 직방ID로 각 플랫폼 딥링크 생성."""
    q = urllib.parse.quote(apt_name)

    # 직방: ID 있으면 단지 직행, 없으면 검색
    if zigbang_id:
        zigbang_url = f"https://www.zigbang.com/home/apt/complexes/{zigbang_id}"
    else:
        zigbang_url = f"https://www.zigbang.com/home/apt?q={q}"

    # 네이버 부동산 통합검색
    naver_url = f"https://search.naver.com/search.naver?query={q}+아파트+매물"

    # 호갱노노 검색
    hgnn_url = f"https://hogangnono.com/search?q={q}"

    return {
        "직방_url": zigbang_url,
        "네이버_url": naver_url,
        "호갱노노_url": hgnn_url,
    }


def fetch_links_for_complexes(
    apt_names: list[str],
    delay: float = 0.3,
) -> pd.DataFrame:
    """여러 단지 → 직방 ID 조회 + 3개 플랫폼 딥링크 DataFrame.

    직방 검색 실패 단지는 검색 링크로 대체.
    """
    rows = []
    for name in apt_names:
        complexes = search_apt_complex(name)
        cid = _complex_id(complexes[0]) if complexes else None

        meta = {}
        if complexes:
            src = complexes[0].get("_source", {})
            meta["주소"] = src.get("신주소") or src.get("주소") or ""
            meta["사용승인"] = str(src.get("사용승인일", ""))[:4]
            # enabled2: 직방 서비스 매물 수 (추정)
            active = src.get("enabled2") or src.get("activeItems")
            meta["직방매물(추정)"] = int(active) if active else 0

        links = _make_links(name, cid)
        rows.append({"apt_name": name, "zigbang_id": cid, **meta, **links})
        time.sleep(delay)

    return pd.DataFrame(rows) if rows else pd.DataFrame()
