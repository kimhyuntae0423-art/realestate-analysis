"""KB부동산 데이터허브 - 매수우위지수 수집기.

인증키 불필요(공개 JSON API). 엔드포인트/파라미터는 PublicDataReader
오픈소스(kbland.py)에서 확인한 실제 KB 내부 API를 직접 호출한다.

엔드포인트: https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd/maktTrnd
파라미터:
  메뉴코드=01 (매수우위지수), 월간주간구분코드=01 (월간), 기간=N (최근 N년)

반환 지역은 전국/광역시도/서울 하위그룹 등 25개 — 이 중 우리 실거래 DB가
커버하는 시/도(서울·경기·인천·부산)만 저장해서 쓴다. KB 10자리 지역코드의
앞 2자리가 우리 프로젝트의 법정동 시/도 코드와 그대로 일치한다
(예: "1100000000" 서울 -> "11").
"""
from __future__ import annotations

from datetime import date

from src.collectors.base import HttpClient
from src.utils.logger import get_logger

log = get_logger(__name__)

KB_URL = "https://data-api.kbland.kr/bfmstat/weekMnthlyHuseTrnd/maktTrnd"

# 실거래 DB가 실제로 커버하는 시/도만 저장 (다른 hypothesis_tests_valuation.py의
# SUPPLY_SIDO_NAMES와 동일 — 프로젝트 전체에서 이 4개 시/도로 일관되게 검증)
TRACKED_SIDO = {"11": "서울", "41": "경기", "28": "인천", "26": "부산"}


class KbSentimentCollector:
    def __init__(self):
        self.client = HttpClient()

    def fetch_buy_sentiment(self, years: int = 5) -> list[dict]:
        """최근 N년 시/도별 월간 매수우위지수. TRACKED_SIDO만 정규화해서 반환."""
        params = {"메뉴코드": "01", "월간주간구분코드": "01", "기간": str(years)}
        r = self.client.get(KB_URL, params=params)
        body = r.json().get("dataBody", {})
        if str(body.get("resultCode")) != "11000":
            raise RuntimeError(f"KB API error: {body}")
        data = body["data"]

        rows = []
        for region in data["데이터리스트"]:
            kb_code = region.get("지역코드", "")
            sido = kb_code[:2]
            if sido not in TRACKED_SIDO:
                continue
            for item in region["dataList"]:
                ym = item.get("기준날짜")  # "YYYYMM"
                if not ym or len(ym) != 6:
                    continue
                rows.append({
                    "region_code": sido,
                    "ym_date": date(int(ym[:4]), int(ym[4:6]), 1),
                    "buy_more_pct": item.get("매수자많음"),
                    "sell_more_pct": item.get("매도자많음"),
                    "similar_pct": item.get("비슷함"),
                    "sentiment_index": item.get("매수우위지수"),
                    "source": "kb_maktrnd",
                })
        log.info("KB 매수우위지수: %d행 (시/도 %d곳)", len(rows), len({r["region_code"] for r in rows}))
        return rows
