"""한국은행 ECOS(경제통계시스템) - 거시경제 시계열 수집기 (M2 통화량).

무료 인증키 필요(ecos.bok.or.kr 회원가입 후 즉시 발급). config.ECOS_API_KEY.

M2는 "신지표"(1.1.3, 통계표 161Y008)와 "구지표"(1.7.3, 통계표 101Y004) 두 계열이
있는데, 구지표는 2004-09에 갱신이 끊긴 폐기 계열이라 신지표만 쓴다
(2026-08-18 확인, StatisticItemList로 END_TIME 직접 대조함).
161Y008/BBGA00 = "M2(말잔, 원계열)", 월별, 2003-10~현재.
151Y005/11100A0 = "주택관련대출-예금취급기관"(전 금융권 주택담보대출 잔액), 월별,
2007-12~현재.
161Y007/BBGS00 = "M2(말잔, 계절조정계열)" — 원계열 로버스트니스 체크용.
161Y004/BBKA00 = "M1(말잔, 원계열)", 월별, 2003-10~현재.
722Y001/0101000 = "한국은행 기준금리", 월별(원래 일별, 월말 스냅샷), 1999-05~현재.
511Y003/FMB = "향후1년 기대인플레이션율"(소비자동향조사), 월별, 2002-02~현재.
901Y089 = "아파트 매매 실거래가격지수"(한국부동산원, ECOS 재배포), 월별, 2006-01~현재,
지역코드는 시/도 전체가 있음(우리 sido 코드와 다른 KAB 자체 코드, KAB_APT_INDEX_REGIONS로 매핑).
"""
from __future__ import annotations

from datetime import date

from config.settings import ECOS_API_KEY
from src.collectors.base import HttpClient
from src.utils.logger import get_logger

log = get_logger(__name__)

ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"

# (series 이름, 통계표코드, 항목코드) — 필요해지면 여기에 추가
SERIES = [
    ("m2_eop_raw", "161Y008", "BBGA00"),           # M2(말잔, 원계열), 십억원
    ("mortgage_loan_eop", "151Y005", "11100A0"),   # 주택관련대출-예금취급기관(말잔), 십억원
    ("m2_eop_sa", "161Y007", "BBGS00"),            # M2(말잔, 계절조정계열), 십억원
    ("m1_eop_raw", "161Y004", "BBKA00"),           # M1(말잔, 원계열), 십억원
    ("base_rate", "722Y001", "0101000"),           # 한국은행 기준금리, %
    ("expected_inflation", "511Y003", "FMB"),      # 향후1년 기대인플레이션율, %
]

# 아파트 매매 실거래가격지수(901Y089) — KAB 자체 지역코드 -> 우리 sido 코드("00"=전국)
KAB_APT_INDEX_REGIONS = {
    "100": "00",  # 전국
    "200": "11",  # 서울
    "C00": "41",  # 경기
    "700": "28",  # 인천
    "500": "26",  # 부산
}


def _ym_n_years_ago(years: int) -> str:
    today = date.today()
    y = today.year - years
    return f"{y:04d}{today.month:02d}"


class EcosCollector:
    def __init__(self):
        self.client = HttpClient()

    def fetch_series(self, series: str, stat_code: str, item_code: str,
                      years: int = 8) -> list[dict]:
        start = _ym_n_years_ago(years)
        end = date.today().strftime("%Y%m")
        url = f"{ECOS_BASE}/{ECOS_API_KEY}/json/kr/1/500/{stat_code}/M/{start}/{end}/{item_code}"
        r = self.client.get(url)
        body = r.json()
        if "StatisticSearch" not in body:
            msg = body.get("RESULT", {}).get("MESSAGE", "알 수 없는 오류")
            raise RuntimeError(f"ECOS API error ({stat_code}/{item_code}): {msg}")
        rows = []
        for row in body["StatisticSearch"].get("row", []):
            t = row["TIME"]  # "202101" 형식
            val = row.get("DATA_VALUE")
            if val is None:
                continue
            rows.append({
                "series": series, "ym_date": date(int(t[:4]), int(t[4:6]), 1),
                "value": float(val), "source": f"ecos_{stat_code}",
            })
        return rows

    def fetch_all(self, years: int = 8) -> list[dict]:
        rows = []
        for series, stat_code, item_code in SERIES:
            r = self.fetch_series(series, stat_code, item_code, years)
            log.info("ECOS %s: %d행", series, len(r))
            rows += r
        return rows

    def fetch_kab_apt_price_index(self, years: int = 8) -> list[dict]:
        """한국부동산원 아파트 매매 실거래가격지수 — 우리가 추적하는 4개 시/도 + 전국."""
        rows = []
        for item_code, sido in KAB_APT_INDEX_REGIONS.items():
            r = self.fetch_series(f"kab_apt_price_idx_{sido}", "901Y089", item_code, years)
            log.info("ECOS kab_apt_price_idx_%s: %d행", sido, len(r))
            rows += r
        return rows
