"""KOSIS에서 다운받은 CSV 파일을 DB에 import.

KOSIS CSV는 cp949(EUC-KR) 인코딩.

[target=population] 시군구 인구이동 (DT_1B26001 계열)
  [0] 행정구역 코드 (5자리)  [2] 성별코드  [4] 시점  [5] 전입 [6] 전출 [7] 순이동

[target=supply_sido] 시도별 사용검사실적 = 입주물량 proxy (DT_MLTM_5372)
  KOSIS는 시군구 입주물량 수록표가 없어서 시도 단위로 타협.
  [1] 구분명  [3] 부문명  [5] 시도명  [6] 시점  [7] 사용검사실적(호)

사용법:
    python -m scripts.import_kosis_csv data/raw/kosis/부동산_데이터_20260523.csv
    python -m scripts.import_kosis_csv data/raw/kosis/supply_sido_사용검사실적_20260523.csv --target supply_sido
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
import csv
from datetime import date

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.database.models import init_db, PopulationFlow, SupplySchedule, SessionLocal
from src.utils.logger import get_logger

log = get_logger(__name__)


# KOSIS 시도명 → 표준 행정구역 2자리 코드.
# 강원/전북 2023~24 명칭변경(특별자치도) 반영.
SIDO_NAME_TO_CODE = {
    "서울": "11", "서울특별시": "11",
    "부산": "26", "부산광역시": "26",
    "대구": "27", "대구광역시": "27",
    "인천": "28", "인천광역시": "28",
    "광주": "29", "광주광역시": "29",
    "대전": "30", "대전광역시": "30",
    "울산": "31", "울산광역시": "31",
    "세종": "36", "세종특별자치시": "36",
    "경기": "41", "경기도": "41",
    "강원": "51", "강원도": "51", "강원특별자치도": "51",
    "충북": "43", "충청북도": "43",
    "충남": "44", "충청남도": "44",
    "전북": "52", "전라북도": "52", "전북특별자치도": "52",
    "전남": "46", "전라남도": "46",
    "경북": "47", "경상북도": "47",
    "경남": "48", "경상남도": "48",
    "제주": "50", "제주특별자치도": "50",
}


def _parse_ym(text: str) -> date | None:
    """'2024.05 월' → date(2024, 5, 1)."""
    text = text.strip().split()[0]  # "2024.05"
    try:
        y, m = text.split(".")
        return date(int(y), int(m), 1)
    except (ValueError, IndexError):
        return None


def _to_int(s: str) -> int:
    try:
        return int(float(s.strip().strip('"')))
    except (ValueError, AttributeError):
        return 0


def import_population(csv_path: Path) -> int:
    rows = []
    # KOSIS CSV는 cp949 인코딩
    with open(csv_path, "r", encoding="cp949", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # 헤더 스킵
        log.info("CSV 헤더: %s", header[:8] if header else None)
        for row in reader:
            if len(row) < 8:
                continue
            region = row[0].strip().strip('"')
            gender_code = row[2].strip().strip('"')
            ym_str = row[4].strip().strip('"')
            # 시군구 5자리만 (시도 2자리 코드 등 제외)
            if len(region) != 5:
                continue
            # 성별 "계"만 사용 (코드 0)
            if gender_code != "0":
                continue
            d = _parse_ym(ym_str)
            if d is None:
                continue
            inflow = _to_int(row[5])
            outflow = _to_int(row[6])
            net = _to_int(row[7]) if row[7] else (inflow - outflow)
            if inflow == 0 and outflow == 0:
                continue  # 빈 행
            rows.append({
                "region_code": region,
                "flow_date": d,
                "inflow": inflow,
                "outflow": outflow,
                "net_inflow": net,
                "source": "kosis_csv",
            })

    if not rows:
        log.warning("정규화 후 데이터가 비어있습니다.")
        return 0

    # SQLite 변수 한도(999) 회피 — 컬럼 7개 × 100행 = 700 변수
    BATCH = 100
    with SessionLocal() as s:
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            stmt = sqlite_insert(PopulationFlow).values(chunk).on_conflict_do_nothing()
            s.execute(stmt)
        s.commit()
    log.info("PopulationFlow upsert: %d rows", len(rows))
    return len(rows)


def import_supply_sido(csv_path: Path) -> int:
    """KOSIS 시도별 사용검사실적 CSV → SupplySchedule (region_code=2자리).

    부문='총계', 구분='총계'만 받아서 시도-월 단위로 한 행씩 적재.
    """
    rows = []
    seen: set[tuple] = set()
    with open(csv_path, "r", encoding="cp949", errors="replace", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        log.info("CSV 헤더: %s", header)
        for row in reader:
            if len(row) < 8:
                continue
            gubun = row[1].strip().strip('"')   # 구분명 (총계)
            bumun = row[3].strip().strip('"')   # 부문명 (총계 / 민간분양 / ...)
            sido = row[5].strip().strip('"')    # 시도명
            ym_str = row[6].strip().strip('"')  # "2024.05 월"
            units_s = row[7].strip().strip('"')

            if gubun != "총계" or bumun != "총계":
                continue
            if sido == "전국":
                continue
            code = SIDO_NAME_TO_CODE.get(sido)
            if not code:
                log.warning("시도명 매핑 실패: %s", sido)
                continue
            d = _parse_ym(ym_str)
            if d is None:
                continue
            units = _to_int(units_s)
            if units <= 0:
                continue
            key = (code, d)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "region_code": code,
                "move_in_date": d,
                "units": units,
                "source": "kosis_sido",
                "note": f"{sido} 사용검사실적(총계)",
            })

    if not rows:
        log.warning("정규화 후 데이터가 비어있습니다.")
        return 0

    BATCH = 100
    with SessionLocal() as s:
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            stmt = sqlite_insert(SupplySchedule).values(chunk).on_conflict_do_nothing()
            s.execute(stmt)
        s.commit()
    log.info("SupplySchedule(시도) upsert: %d rows", len(rows))
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", type=str, help="CSV 파일 경로")
    ap.add_argument("--target", choices=["population", "supply_sido"], default="population")
    args = ap.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        log.error("파일 없음: %s", csv_path)
        sys.exit(1)

    init_db()
    if args.target == "population":
        n = import_population(csv_path)
    else:
        n = import_supply_sido(csv_path)
    log.info("총 %d행 import 완료", n)


if __name__ == "__main__":
    main()
