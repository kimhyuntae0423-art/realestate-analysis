"""
국토교통부 실거래가 공개 API 수집기

API 가이드:
- 매매: RTMSDataSvcAptTradeDev / getRTMSDataSvcAptTradeDev
- 전월세: RTMSDataSvcAptRent / getRTMSDataSvcAptRent

요청 파라미터:
- serviceKey: 인증키 (Decoded)
- LAWD_CD: 법정동 시군구 5자리
- DEAL_YMD: YYYYMM
- pageNo, numOfRows
"""
from __future__ import annotations
import xmltodict
from pathlib import Path
import json

from config.settings import DATA_GO_KR_API_KEY, MOLIT_ENDPOINTS, RAW_DIR
from src.collectors.base import HttpClient
from src.parsers.price_parser import parse_trade_item, parse_rent_item
from src.utils.logger import get_logger

log = get_logger(__name__)


class MolitCollector:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or DATA_GO_KR_API_KEY
        if not self.api_key:
            raise RuntimeError("DATA_GO_KR_API_KEY 가 설정되지 않았습니다. .env 확인하세요.")
        self.http = HttpClient()

    def _fetch_page(self, endpoint: str, lawd_cd: str, ymd: str,
                    page_no: int = 1, rows: int = 1000) -> dict:
        params = {
            "serviceKey": self.api_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": ymd,
            "pageNo": page_no,
            "numOfRows": rows,
        }
        r = self.http.get(endpoint, params=params)
        text = r.text
        if not text.lstrip().startswith("<"):
            raise RuntimeError(f"비정상 응답: {text[:200]}")
        data = xmltodict.parse(text)
        body = data.get("response", {}).get("body")
        if body is None:
            header = data.get("response", {}).get("header", {})
            raise RuntimeError(f"API 오류: {header}")
        return body

    def _iter_items(self, body: dict):
        items = body.get("items")
        if not items:
            return []
        item = items.get("item")
        if item is None:
            return []
        if isinstance(item, list):
            return item
        return [item]

    def _cache_raw(self, kind: str, lawd_cd: str, ymd: str, raw: dict):
        p = RAW_DIR / f"{kind}_{lawd_cd}_{ymd}.json"
        p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    def fetch_trades(self, lawd_cd: str, ymd: str) -> list[dict]:
        body = self._fetch_page(MOLIT_ENDPOINTS["apt_trade"], lawd_cd, ymd)
        items = self._iter_items(body)
        self._cache_raw("trade", lawd_cd, ymd, {"items": items})
        rows = []
        for it in items:
            try:
                rows.append(parse_trade_item(it, lawd_cd))
            except Exception as e:
                log.warning("trade parse 실패: %s | item=%s", e, it)
        log.info("trade %s %s: %d rows", lawd_cd, ymd, len(rows))
        return rows

    def fetch_rents(self, lawd_cd: str, ymd: str) -> list[dict]:
        body = self._fetch_page(MOLIT_ENDPOINTS["apt_rent"], lawd_cd, ymd)
        items = self._iter_items(body)
        self._cache_raw("rent", lawd_cd, ymd, {"items": items})
        rows = []
        for it in items:
            try:
                rows.append(parse_rent_item(it, lawd_cd))
            except Exception as e:
                log.warning("rent parse 실패: %s | item=%s", e, it)
        log.info("rent %s %s: %d rows", lawd_cd, ymd, len(rows))
        return rows
