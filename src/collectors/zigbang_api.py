"""직방 비공식 API — 아파트 현재 매물 조회

공식 API가 아니므로 응답 구조가 변경될 수 있음.
오류 단지는 건너뛰고 빈 DataFrame 반환.
"""
from __future__ import annotations
import logging
import time

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
    "Accept-Language": "ko-KR,ko;q=0.9",
})


def _get(url: str, params: dict | None = None, timeout: int = 10) -> dict | list:
    resp = _SESSION.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _extract_list(data: dict | list, keys: tuple[str, ...] = ("items", "units", "data", "result")) -> list:
    if isinstance(data, list):
        return data
    for k in keys:
        if k in data and isinstance(data[k], list):
            return data[k]
    return []


# ── 1. 단지 검색 ─────────────────────────────────────────────────────────────

def search_apt_complex(name: str) -> list[dict]:
    """단지명으로 직방 아파트 단지 검색 → 단지 목록 반환."""
    data = _get(
        "https://apis.zigbang.com/v2/search",
        {"q": name, "serviceType": "아파트", "leaseYn": "N"},
    )
    return _extract_list(data)


def _complex_id(item: dict) -> str | None:
    for k in ("item_id", "itemId", "id", "complexId", "danji_id", "complex_id"):
        v = item.get(k)
        if v:
            return str(v)
    return None


# ── 2. 매물 목록 조회 ─────────────────────────────────────────────────────────

def get_complex_listings(complex_id: str, sales_type: str = "매매") -> list[dict]:
    """직방 단지 ID로 현재 매물 목록 조회. 엔드포인트 두 개 순서 시도."""
    for url, params in [
        (
            f"https://apis.zigbang.com/property/apt/complexes/{complex_id}/units",
            {"salesType": sales_type},
        ),
        (
            f"https://apis.zigbang.com/v2/apt/complexes/{complex_id}/items",
            {"salesType": sales_type},
        ),
    ]:
        try:
            data = _get(url, params)
            items = _extract_list(data, ("units", "items", "data", "result"))
            if items:
                return items
        except Exception as e:
            log.debug("엔드포인트 실패 %s: %s", url, e)
    return []


# ── 3. 단일 매물 dict 정규화 ─────────────────────────────────────────────────

def _parse_unit(unit: dict, apt_name: str) -> dict | None:
    # 가격 추출 (만원 단위)
    price_man = None
    for k in ("salePrice", "price", "dealPrice", "보증금액"):
        v = unit.get(k)
        if v and float(v) > 0:
            price_man = float(v)
            break
    if not price_man:
        return None

    # 층 정보
    floor_str = ""
    fl = unit.get("floor") or unit.get("floorInfo") or unit.get("층수")
    total = unit.get("totalFloor") or unit.get("maxFloor") or unit.get("건물층수")
    if fl:
        floor_str = f"{fl}층" if not total else f"{fl}/{total}층"

    # 면적
    area = unit.get("area") or unit.get("전용면적") or unit.get("exclusiveArea")
    supply = unit.get("supplyArea") or unit.get("공급면적")

    # 기타
    direction = unit.get("direction") or unit.get("향") or ""
    memo = (unit.get("memo") or unit.get("description") or unit.get("remark") or "")
    agency = unit.get("agencyName") or unit.get("중개사명") or unit.get("agency") or ""

    # 직방 링크
    item_id = unit.get("itemId") or unit.get("item_id") or unit.get("id") or ""
    zigbang_url = f"https://www.zigbang.com/home/apt/items/{item_id}" if item_id else None

    return {
        "apt_name": apt_name,
        "호가(억)": round(price_man / 10000, 2) if price_man >= 1000 else round(price_man, 2),
        "층": floor_str,
        "전용(㎡)": round(area, 1) if area else None,
        "공급(㎡)": round(supply, 1) if supply else None,
        "향": direction,
        "특이사항": str(memo)[:60] if memo else "",
        "중개사": agency,
        "zigbang_url": zigbang_url,
    }


# ── 4. 공개 함수 ─────────────────────────────────────────────────────────────

def fetch_listings_for_complex(apt_name: str, sales_type: str = "매매") -> pd.DataFrame:
    """단지명 → 검색 → 매물 목록 DataFrame."""
    try:
        complexes = search_apt_complex(apt_name)
        if not complexes:
            log.debug("직방 검색 결과 없음: %s", apt_name)
            return pd.DataFrame()

        cid = _complex_id(complexes[0])
        if not cid:
            log.debug("단지 ID 없음: %s | raw=%s", apt_name, complexes[0])
            return pd.DataFrame()

        units = get_complex_listings(cid, sales_type)
        rows = [r for u in units if (r := _parse_unit(u, apt_name))]
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["complex_id"] = cid
        return df

    except Exception as e:
        log.warning("직방 오류 (%s): %s", apt_name, e)
        return pd.DataFrame()


def fetch_listings_for_complexes(
    apt_names: list[str],
    sales_type: str = "매매",
    delay: float = 0.35,
) -> tuple[pd.DataFrame, list[str]]:
    """여러 단지 매물 합산 조회.

    Returns:
        (listings_df, failed_names)
    """
    frames: list[pd.DataFrame] = []
    failed: list[str] = []

    for name in apt_names:
        df = fetch_listings_for_complex(name, sales_type)
        if df.empty:
            failed.append(name)
        else:
            frames.append(df)
        time.sleep(delay)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined, failed
