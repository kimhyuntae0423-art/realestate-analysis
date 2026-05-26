"""단지 입지 점수 분석 (카카오 로컬 API 기반)

각 단지의 주변 1km 이내 지하철역·학교·대형마트 개수를 카운트해 점수화.
카카오 REST API 키가 .env 에 KAKAO_REST_API_KEY 로 설정되어야 동작.
키가 없으면 점수 N/A.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import KAKAO_REST_API_KEY, ROOT
from src.utils.logger import get_logger

log = get_logger(__name__)

CACHE_PATH = ROOT / "data" / "processed" / "apt_locations.json"


def is_kakao_ready() -> bool:
    return bool(KAKAO_REST_API_KEY)


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(d: dict):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _key(region_code: str, apt_name: str) -> str:
    return f"{region_code}::{apt_name}"


def lookup_or_fetch(region_code: str, apt_name: str, region_text: str = "") -> Optional[dict]:
    """단지명+지역으로 좌표/입지정보 조회. 캐시 우선, 없으면 카카오 호출.

    Returns dict { lat, lon, n_subway, n_school, n_mart, n_hospital, score, fetched_at } or None
    """
    if not is_kakao_ready():
        return None

    cache = _load_cache()
    k = _key(region_code, apt_name)
    if k in cache:
        return cache[k]

    from src.collectors.kakao_api import KakaoClient
    client = KakaoClient()
    query = f"{region_text} {apt_name}".strip()
    try:
        coord = client.geocode(query)
    except RuntimeError as e:
        if "403" in str(e):
            log.error(
                "카카오 API 403 - 앱에서 '카카오맵' 서비스가 비활성. "
                "https://developers.kakao.com/console/app → 제품 설정 → 카카오맵 활성화"
            )
        else:
            log.error("카카오 호출 실패: %s", e)
        return None
    if not coord:
        log.warning("geocode 실패: %s", query)
        cache[k] = None
        _save_cache(cache)
        return None
    lat, lon = coord

    subway = client.nearby(lat, lon, "SW8", radius=1000)
    school = client.nearby(lat, lon, "SC4", radius=1000)
    mart = client.nearby(lat, lon, "MT1", radius=1000)
    hospital = client.nearby(lat, lon, "HP8", radius=1000)

    n_subway = len(subway)
    n_school = len(school)
    n_mart = len(mart)
    n_hospital = len(hospital)

    def _nearest(items):
        if not items:
            return None
        try:
            return min(int(x.get("distance", "9999") or 9999) for x in items)
        except Exception:
            return None

    d_subway = _nearest(subway)
    d_school = _nearest(school)
    d_mart = _nearest(mart)

    # 거리 기반 점수 (가까울수록 높음)
    # 지하철: 0~300m=40, 300~600m=25, 600~1000m=10, 없음=0
    if d_subway is None:
        s_sub = 0
    elif d_subway <= 300: s_sub = 40
    elif d_subway <= 600: s_sub = 25
    else:                 s_sub = 10

    # 학교: 1km 내 5개+ = 30, 3~4 = 20, 1~2 = 10, 0 = 0
    if n_school >= 5:  s_sch = 30
    elif n_school >= 3: s_sch = 20
    elif n_school >= 1: s_sch = 10
    else:               s_sch = 0

    # 마트: 가장 가까운 거리 300m=20, 600m=12, 1km=5
    if d_mart is None:    s_mart = 0
    elif d_mart <= 300:   s_mart = 20
    elif d_mart <= 600:   s_mart = 12
    else:                 s_mart = 5

    # 병원: 5개+ = 10, 3~4 = 6, 1~2 = 3
    if n_hospital >= 5:   s_hos = 10
    elif n_hospital >= 3: s_hos = 6
    elif n_hospital >= 1: s_hos = 3
    else:                 s_hos = 0

    score = s_sub + s_sch + s_mart + s_hos  # max 100

    rec = {
        "lat": lat, "lon": lon,
        "n_subway": n_subway, "n_school": n_school,
        "n_mart": n_mart, "n_hospital": n_hospital,
        "score": round(score, 1),
        "fetched_at": datetime.utcnow().isoformat(),
    }
    cache[k] = rec
    _save_cache(cache)
    return rec


def enrich_with_location(df: pd.DataFrame, max_calls: int = 50,
                          region_map: Optional[dict[str, str]] = None) -> pd.DataFrame:
    """추천 결과 DataFrame에 입지 점수 컬럼 추가.

    max_calls: 새로 API 호출할 최대 개수 (rate limit 보호).
    cache hit는 무료. 캐시에 있으면 카운트 안 함.
    """
    if df.empty:
        return df
    if not is_kakao_ready():
        df = df.copy()
        df["location_score"] = pd.NA
        return df

    cache = _load_cache()
    new_calls = 0
    rows = []
    for _, r in df.iterrows():
        k = _key(r["region_code"], r["apt_name"])
        if k in cache:
            rec = cache[k]
        elif new_calls < max_calls:
            region_text = ""
            if region_map:
                region_text = region_map.get(r["region_code"], "")
            rec = lookup_or_fetch(r["region_code"], r["apt_name"], region_text)
            new_calls += 1
        else:
            rec = None
        if rec:
            rows.append({
                "n_subway": rec["n_subway"], "n_school": rec["n_school"],
                "n_mart": rec["n_mart"], "n_hospital": rec["n_hospital"],
                "location_score": rec["score"],
            })
        else:
            rows.append({
                "n_subway": pd.NA, "n_school": pd.NA,
                "n_mart": pd.NA, "n_hospital": pd.NA,
                "location_score": pd.NA,
            })
    enrichment = pd.DataFrame(rows, index=df.index)
    return pd.concat([df, enrichment], axis=1)
