"""카카오 로컬 API - 좌표 변환 / 주변 시설 검색 (선택 기능)"""
from __future__ import annotations
from config.settings import KAKAO_REST_API_KEY
from src.collectors.base import HttpClient
from src.utils.logger import get_logger

log = get_logger(__name__)

KAKAO_BASE = "https://dapi.kakao.com/v2/local"


class KakaoClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or KAKAO_REST_API_KEY
        if not self.api_key:
            raise RuntimeError("KAKAO_REST_API_KEY 가 .env 에 없습니다.")
        self.http = HttpClient(base_headers={"Authorization": f"KakaoAK {self.api_key}"})

    def geocode(self, query: str) -> tuple[float, float] | None:
        """장소명·단지명·주소로 좌표 찾기. 키워드 검색이 먼저, 실패 시 주소 검색."""
        # 1) 키워드 검색 (단지명 매칭에 강함)
        r = self.http.get(f"{KAKAO_BASE}/search/keyword.json",
                          params={"query": query, "size": 5})
        docs = r.json().get("documents", [])
        if docs:
            # "아파트" 단어 포함된 결과 우선
            apt_match = [d for d in docs if "아파트" in d.get("place_name", "") or "아파트" in d.get("category_name", "")]
            d = apt_match[0] if apt_match else docs[0]
            return float(d["y"]), float(d["x"])

        # 2) 주소 검색 (백업)
        r = self.http.get(f"{KAKAO_BASE}/search/address.json", params={"query": query})
        docs = r.json().get("documents", [])
        if docs:
            d = docs[0]
            return float(d["y"]), float(d["x"])
        return None

    def nearby(self, lat: float, lon: float, category: str, radius: int = 1000) -> list[dict]:
        """category: SW8(지하철), SC4(학교), MT1(대형마트), CS2(편의점), HP8(병원)"""
        r = self.http.get(f"{KAKAO_BASE}/search/category.json", params={
            "category_group_code": category,
            "x": lon, "y": lat, "radius": radius, "size": 15,
        })
        return r.json().get("documents", [])
