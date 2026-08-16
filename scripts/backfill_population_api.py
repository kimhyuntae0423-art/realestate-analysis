"""KOSIS OpenAPI로 population_flow(인구이동) 과거 구간 백필.

기존 population_flow 데이터(source=kosis_csv, 2024-05~)는 사람이 KOSIS 웹사이트에서
CSV를 직접 내려받아 import_kosis_csv.py로 넣은 것. src/collectors/kosis_api.py는
tblId/objL1/objL2/itmId 파라미터를 잘못 추측해(예시값 그대로 사용) 실패만 하다가
이번 세션에 삭제됐었는데, KOSIS 웹 UI의 "OPENAPI URL생성" 기능으로 실제 통계표를
역추적해 올바른 파라미터를 확인했다.

국내인구이동통계 — 시군구/연령(5세)별 이동자수 (orgId=101, tblId=DT_1B26001_A03)
  objL1=ALL   : 전체 행정구역(전국/시도/시군구 다 섞여 나옴 -> 5자리 코드만 필터)
  objL2=000   : 연령 분류의 "계"(전체 연령 합계) 코드
  itmId=T10+T20 : T10=전입자, T20=전출자 (순이동 = T10-T20으로 직접 계산)

사용법:
    python -m scripts.backfill_population_api --start 202108 --end 202404
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
from collections import defaultdict
from datetime import date

import requests

from config.settings import KOSIS_API_KEY, REQUEST_TIMEOUT
from src.database.models import init_db
from src.database.repository import upsert_population_flow
from src.utils.logger import get_logger

log = get_logger(__name__)

KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
ORG_ID = "101"
TBL_ID = "DT_1B26001_A03"


def fetch(start_ym: str, end_ym: str) -> list[dict]:
    params = {
        "apiKey": KOSIS_API_KEY, "method": "getList", "format": "json", "jsonVD": "Y",
        "orgId": ORG_ID, "tblId": TBL_ID, "prdSe": "M",
        "startPrdDe": start_ym, "endPrdDe": end_ym,
        "objL1": "ALL", "objL2": "000", "itmId": "T10+T20",
    }
    r = requests.get(KOSIS_BASE, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        raise RuntimeError(f"KOSIS error: {data}")
    return data


def normalize(raw: list[dict]) -> list[dict]:
    """시군구(5자리) 단위 전입/전출을 순유입 행으로 묶는다. 전국/시도 집계행은 제외."""
    grouped: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for row in raw:
        region = row["C1"]
        if len(region) != 5:
            continue
        grouped[(region, row["PRD_DE"])][row["ITM_ID"]] = int(row["DT"])

    rows = []
    for (region_code, prd_de), items in grouped.items():
        if "T10" not in items or "T20" not in items:
            continue
        inflow, outflow = items["T10"], items["T20"]
        rows.append({
            "region_code": region_code,
            "flow_date": date(int(prd_de[:4]), int(prd_de[4:6]), 1),
            "inflow": inflow, "outflow": outflow, "net_inflow": inflow - outflow,
            "source": "kosis_api_backfill",
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="202108", help="시작 YYYYMM (기본: 202108)")
    ap.add_argument("--end", default="202404", help="종료 YYYYMM (기본: 202404, kosis_csv 시작 직전)")
    args = ap.parse_args()

    init_db()
    raw = fetch(args.start, args.end)
    log.info("KOSIS 원본 %d행 수신", len(raw))
    rows = normalize(raw)
    log.info("정규화 후 %d개 지역-월 행", len(rows))
    n = upsert_population_flow(rows)
    log.info("총 %d행 upsert 완료", n)


if __name__ == "__main__":
    main()
