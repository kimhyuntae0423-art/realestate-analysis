"""KOSIS 인구이동 + 입주물량 수집.

전제: .env 에 KOSIS_API_KEY 설정 필요. https://kosis.kr/openapi/ 에서 발급.

사용법:
    # 인구이동 (최근 24개월)
    python scripts/collect_kosis.py --target population --months 24

    # 입주물량 (현재 ~ 12개월 후)
    python scripts/collect_kosis.py --target supply --months 12

    # 둘다
    python scripts/collect_kosis.py --target all --months 24
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
from datetime import date

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.collectors.kosis_api import KosisCollector
from src.database.models import init_db, SupplySchedule, PopulationFlow, SessionLocal
from src.utils.logger import get_logger

log = get_logger(__name__)


def _months_back_ym(n: int) -> tuple[str, str]:
    """오늘부터 n개월 전 ~ 오늘 (YYYYMM)."""
    today = date.today()
    end = f"{today.year:04d}{today.month:02d}"
    y, m = today.year, today.month
    for _ in range(n):
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    start = f"{y:04d}{m:02d}"
    return start, end


def _ym_to_date(ym: str) -> date:
    return date(int(ym[:4]), int(ym[4:6]), 1)


def collect_population(months: int):
    col = KosisCollector()
    start, end = _months_back_ym(months)
    log.info("인구이동 수집: %s ~ %s", start, end)
    rows = col.fetch_population_flow(start, end)
    if not rows:
        log.warning("KOSIS 응답 비어있음. 통계표 ID/항목 ID를 확인하세요.")
        return

    # KOSIS 응답: {"prdDe": "202405", "C1": "11110", "C1_NM": "종로구",
    #              "ITM_ID": "T10", "DT": "1234"}
    # 같은 region+prdDe 쌍에 T10(전입), T20(전출) 두 row가 옴 → 묶어서 net 계산
    by_key: dict[tuple, dict] = {}
    for r in rows:
        region = r.get("C1") or r.get("C1_OBJ_NM_ID")
        ym = r.get("PRD_DE") or r.get("prdDe")
        itm = r.get("ITM_ID") or r.get("itmId")
        val = r.get("DT") or r.get("dt") or "0"
        if not region or not ym:
            continue
        if len(region) != 5:  # 시군구 5자리 코드만
            continue
        key = (region, ym)
        rec = by_key.setdefault(key, {"region_code": region, "ym": ym,
                                       "inflow": 0, "outflow": 0})
        try:
            iv = int(float(val))
        except (TypeError, ValueError):
            iv = 0
        if itm and "T10" in itm:
            rec["inflow"] = iv
        elif itm and "T20" in itm:
            rec["outflow"] = iv

    payload = []
    for rec in by_key.values():
        net = rec["inflow"] - rec["outflow"]
        payload.append({
            "region_code": rec["region_code"],
            "flow_date": _ym_to_date(rec["ym"]),
            "inflow": rec["inflow"],
            "outflow": rec["outflow"],
            "net_inflow": net,
            "source": "kosis",
        })

    if not payload:
        log.warning("정규화 후 비어있음.")
        return

    with SessionLocal() as s:
        stmt = sqlite_insert(PopulationFlow).values(payload).on_conflict_do_nothing()
        s.execute(stmt)
        s.commit()
    log.info("PopulationFlow upsert: %d rows", len(payload))


def collect_supply(months: int):
    col = KosisCollector()
    today = date.today()
    start = f"{today.year:04d}{today.month:02d}"
    y, m = today.year, today.month
    for _ in range(months):
        m += 1
        if m == 13:
            m = 1
            y += 1
    end = f"{y:04d}{m:02d}"
    log.info("입주물량 수집: %s ~ %s", start, end)
    rows = col.fetch_supply_schedule(start, end)
    if not rows:
        log.warning(
            "KOSIS 응답 비어있음. KOSIS는 입주물량 수록표가 제한적입니다. "
            "HUG 부동산정보포털(https://hug.or.kr) 또는 부동산R114 데이터를 "
            "CSV로 받아 직접 import 하는 게 안정적입니다."
        )
        return

    payload = []
    for r in rows:
        region = r.get("C1") or r.get("C1_OBJ_NM_ID")
        ym = r.get("PRD_DE") or r.get("prdDe")
        units = r.get("DT") or r.get("dt") or "0"
        if not region or not ym or len(region) != 5:
            continue
        try:
            n = int(float(units))
        except (TypeError, ValueError):
            n = 0
        payload.append({
            "region_code": region,
            "move_in_date": _ym_to_date(ym),
            "units": n,
            "source": "kosis",
        })
    if not payload:
        log.warning("정규화 후 비어있음.")
        return
    with SessionLocal() as s:
        stmt = sqlite_insert(SupplySchedule).values(payload).on_conflict_do_nothing()
        s.execute(stmt)
        s.commit()
    log.info("SupplySchedule upsert: %d rows", len(payload))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["population", "supply", "all"], default="all")
    ap.add_argument("--months", type=int, default=24)
    args = ap.parse_args()
    init_db()  # 테이블 생성

    if args.target in ("population", "all"):
        try:
            collect_population(args.months)
        except Exception as e:
            log.exception("인구이동 수집 실패: %s", e)
    if args.target in ("supply", "all"):
        try:
            collect_supply(args.months)
        except Exception as e:
            log.exception("입주물량 수집 실패: %s", e)


if __name__ == "__main__":
    main()
