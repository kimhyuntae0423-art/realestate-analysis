"""KB부동산 데이터허브 - 가격 시계열 수집기 (가격지수/평균가/중위가/전세가율/선도50지수).

kb_sentiment.py(매수우위지수)와 같은 base URL의 다른 통계표들. 인증키 불필요.
User-Agent 헤더 없이 호출하면 가끔 연결이 끊긴다(RemoteDisconnected) — 반드시 넣는다.

응답 구조가 두 가지로 나뉜다:
  - 지역별 시계열(가격지수/평균가/중위가/전세가율): {날짜리스트, 데이터리스트:[{지역코드,dataList}]}
    dataList가 날짜리스트보다 길 때가 있어(끝에 요약통계 덧붙는 응답 확인됨) 방어적으로
    len(날짜리스트)만큼만 자른다.
  - 선도아파트50지수: 지역 구분 없이 전국 단일 시계열, 최상위에 바로
    {날짜리스트, 선도50지수리스트, ...} 형태로 온다.
"""
from __future__ import annotations

from datetime import date

from src.collectors.base import HttpClient
from src.utils.logger import get_logger

log = get_logger(__name__)

KB_BASE = "https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd"
UA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 실거래 DB가 실제로 커버하는 시/도만 저장 (kb_sentiment.py의 TRACKED_SIDO와 동일)
TRACKED_SIDO = {"11": "서울", "41": "경기", "28": "인천", "26": "부산"}

# (series 이름, 엔드포인트, 파라미터) — 전부 아파트/매매 기준
REGION_SERIES = [
    ("price_index_apt_sale", "priceIndex",
     {"월간주간구분코드": "01", "매물종별구분": "01", "매매전세코드": "01"}),
    ("avg_price_per_sqm_apt_sale", "avgPrcPerSqmt",
     {"매물종별구분": "01", "매매전세코드": "01"}),
    ("median_price_apt_sale", "mdpsPrc",
     {"매물종별구분": "01", "매매전세코드": "01"}),
    ("jeonse_ratio_apt", "dealCntstTnantRato",
     {"매물종별구분": "01"}),
]


class KbPriceCollector:
    def __init__(self):
        self.client = HttpClient(base_headers=UA_HEADERS)

    def _region_rows(self, series: str, endpoint: str, extra_params: dict, years: int) -> list[dict]:
        params = {**extra_params, "기간": str(years)}
        r = self.client.get(f"{KB_BASE}/{endpoint}", params=params)
        body = r.json().get("dataBody", {})
        if str(body.get("resultCode")) != "11000":
            raise RuntimeError(f"KB API error ({endpoint}): {body}")
        data = body["data"]
        dates = data["날짜리스트"]
        rows = []
        for region in data["데이터리스트"]:
            sido = region.get("지역코드", "")[:2]
            if sido not in TRACKED_SIDO:
                continue
            values = region.get("dataList", [])[:len(dates)]
            for ym, val in zip(dates, values):
                if val is None:
                    continue
                rows.append({
                    "series": series, "region_code": sido,
                    "ym_date": date(int(ym[:4]), int(ym[4:6]), 1),
                    "value": float(val), "source": f"kb_{endpoint}",
                })
        return rows

    def fetch_all_region_series(self, years: int = 5) -> list[dict]:
        rows = []
        for series, endpoint, params in REGION_SERIES:
            r = self._region_rows(series, endpoint, params, years)
            log.info("KB %s: %d행", series, len(r))
            rows += r
        return rows

    def fetch_lead_apt50(self, years: int = 5) -> list[dict]:
        """선도아파트50지수 — 지역 구분 없는 전국 단일 시계열."""
        params = {"기간": str(years)}
        r = self.client.get(f"{KB_BASE}/leadApt50Indx", params=params)
        body = r.json().get("dataBody", {})
        if str(body.get("resultCode")) != "11000":
            raise RuntimeError(f"KB API error (leadApt50Indx): {body}")
        data = body["data"]
        dates = data["날짜리스트"]
        values = data.get("선도50지수리스트", [])[:len(dates)]
        rows = []
        for ym, val in zip(dates, values):
            if val is None:
                continue
            rows.append({
                "series": "lead_apt50_index", "region_code": "00",
                "ym_date": date(int(ym[:4]), int(ym[4:6]), 1),
                "value": float(val), "source": "kb_leadApt50Indx",
            })
        log.info("KB lead_apt50_index: %d행", len(rows))
        return rows
