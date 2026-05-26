"""KOSIS 통계청 OpenAPI - 인구이동 / 입주물량 수집.

API 키 발급: https://kosis.kr/openapi/ → 가입 후 발급 (.env에 KOSIS_API_KEY=)

이 모듈은 두 통계표를 다룸:
  1. 주민등록 인구이동 (전입/전출, 시군구별 월별)
     orgId=101, tblId=DT_1B26001 등
  2. 공동주택 입주예정물량 (시도/시군구별)
     국토부 HUG 공시 데이터 활용 (KOSIS 수록표가 있을 때)

KOSIS 통계표 ID는 시기에 따라 바뀔 수 있어 main()에서 점검 필요.
"""
from __future__ import annotations
from datetime import date
from typing import Any
import requests

from config.settings import KOSIS_API_KEY, REQUEST_TIMEOUT
from src.utils.logger import get_logger

log = get_logger(__name__)

KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"


class KosisCollector:
    """KOSIS OpenAPI 호출 헬퍼.

    공통 파라미터:
      apiKey: KOSIS API KEY
      method: getList
      format: json
      jsonVD: Y
      orgId: 기관 ID (101 = 통계청)
      tblId: 통계표 ID
      prdSe: 시점 종류 (M=월, Y=년)
      startPrdDe, endPrdDe: 시점 (YYYYMM)
      itmId: 항목 ID
      objL1, objL2, ...: 분류값
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or KOSIS_API_KEY
        if not self.api_key:
            raise RuntimeError(
                "KOSIS_API_KEY가 설정되지 않았습니다. "
                "https://kosis.kr/openapi/ 에서 키 발급 후 .env에 추가하세요."
            )

    def _get(self, params: dict) -> list[dict]:
        params.update({
            "apiKey": self.api_key,
            "method": "getList",
            "format": "json",
            "jsonVD": "Y",
        })
        r = requests.get(KOSIS_BASE, params=params, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("err"):
            raise RuntimeError(f"KOSIS error: {data}")
        return data if isinstance(data, list) else []

    # ── 1. 인구이동 (전입/전출) ─────────────────────────────────────
    def fetch_population_flow(
        self,
        start_ym: str,           # "202401"
        end_ym: str,             # "202612"
        tbl_id: str = "DT_1B26001_A02",  # 시군구별 이동자수 (예시)
        org_id: str = "101",
    ) -> list[dict]:
        """KOSIS '시군구별 이동자수' 통계표.

        반환: [{"prdDe": "202405", "C1": "11110", "ITM_ID": "T20", "DT": "1234"}, ...]
        ITM_ID: T10=전입, T20=전출, T30=순이동 (통계표에 따라 다름, 확인 필요)
        """
        params = {
            "orgId": org_id,
            "tblId": tbl_id,
            "prdSe": "M",
            "startPrdDe": start_ym,
            "endPrdDe": end_ym,
        }
        return self._get(params)

    # ── 2. 입주예정물량 ─────────────────────────────────────────────
    def fetch_supply_schedule(
        self,
        start_ym: str,
        end_ym: str,
        tbl_id: str = "DT_116N_INSURING_001",  # HUG 입주예정물량 (예시)
        org_id: str = "116",
    ) -> list[dict]:
        """KOSIS에 수록된 입주예정 통계표.

        KOSIS는 HUG/국토부 자료 일부만 수록하므로, 누락 시 직접 HUG/REB
        CSV 다운로드 후 manual upsert 권장.
        """
        params = {
            "orgId": org_id,
            "tblId": tbl_id,
            "prdSe": "M",
            "startPrdDe": start_ym,
            "endPrdDe": end_ym,
        }
        return self._get(params)
