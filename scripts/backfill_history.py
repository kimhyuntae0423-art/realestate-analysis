"""과거 데이터 백필 — 현재 DB에 없는 오래된 구간만 채움 (이어받기 지원).

collect_data.py는 "오늘부터 N개월 전"만 지원해서 이미 받은 최근 구간을 다시
호출하게 됨. 이 스크립트는 CollectionLog에서 이미 성공(status=ok)한 (지역,월)은
건너뛰고, DB의 가장 오래된 데이터보다 더 이전 구간만 채운다.
API 호출이 연속 실패하면(한도 초과 등) 중단하고, 다음에 재실행하면 이어받는다.

사용법:
    python scripts/backfill_history.py --years 5
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
from datetime import date
from tqdm import tqdm

from src.collectors.molit_api import MolitCollector
from src.database.models import init_db, CollectionLog, SessionLocal
from src.database.repository import upsert_trades, upsert_rents, log_collection, fetch_trades_df
from src.utils.logger import get_logger

log = get_logger(__name__)
MAX_CONSECUTIVE_FAILURES = 10


def months_range(start_ym: str, end_ym: str) -> list[str]:
    """start_ym ~ end_ym(포함) YYYYMM 오름차순 리스트."""
    y, m = int(start_ym[:4]), int(start_ym[4:6])
    ey, em = int(end_ym[:4]), int(end_ym[4:6])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


def _already_done(region: str, ym: str, source: str) -> bool:
    with SessionLocal() as s:
        row = s.query(CollectionLog).filter_by(
            region_code=region, year_month=ym, source=source, status="ok"
        ).first()
        return row is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5, help="목표 총 보유 기간(년)")
    args = ap.parse_args()

    init_db()
    df = fetch_trades_df()
    if df.empty:
        print("DB가 비어있습니다. collect_data.py로 먼저 최근 데이터를 받으세요.")
        return
    regions = sorted(df["region_code"].unique())
    earliest = df["deal_date"].min()

    today = date.today()
    target_start = date(today.year - args.years, today.month, 1)
    if target_start >= earliest:
        print(f"이미 목표 기간({args.years}년) 이상 데이터가 있습니다 (최고 {earliest}).")
        return

    end_dt = earliest.replace(day=1)
    m, y = end_dt.month - 1, end_dt.year
    if m == 0:
        m, y = 12, y - 1
    end_ym = f"{y:04d}{m:02d}"
    start_ym = f"{target_start.year:04d}{target_start.month:02d}"
    ymds = months_range(start_ym, end_ym)

    print(f"백필 대상: 지역 {len(regions)}개 x {len(ymds)}개월 ({start_ym}~{end_ym})")
    print("CollectionLog 기준 이미 완료된 건은 건너뜁니다.")

    mc = MolitCollector()
    total_trade = total_rent = skipped = 0
    errors: list[str] = []
    consecutive_failures = 0
    aborted = False

    for region in regions:
        if aborted:
            break
        for ym in tqdm(ymds, desc=f"[{region}]"):
            for kind, source, fetch_fn, upsert_fn in [
                ("trade", "molit_trade_backfill", mc.fetch_trades, upsert_trades),
                ("rent", "molit_rent_backfill", mc.fetch_rents, upsert_rents),
            ]:
                if _already_done(region, ym, source):
                    skipped += 1
                    continue
                try:
                    rows = fetch_fn(region, ym)
                    inserted = upsert_fn(rows)
                    if kind == "trade":
                        total_trade += inserted
                    else:
                        total_rent += inserted
                    log_collection(source, region, ym, len(rows), inserted, "ok")
                    consecutive_failures = 0
                except Exception as e:
                    log.warning("%s 백필 실패 %s %s: %s", kind, region, ym, e)
                    log_collection(source, region, ym, 0, 0, "fail", str(e))
                    errors.append(f"{region}/{ym}/{kind}: {e}")
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print(f"\n연속 {MAX_CONSECUTIVE_FAILURES}회 실패 — API 한도 초과 가능성. "
                              "중단합니다. 나중에 재실행하면 이어받습니다.")
                        aborted = True
                        break
            if aborted:
                break

    print(f"\n완료: 매매 {total_trade:,}건 / 전월세 {total_rent:,}건 신규 upsert, "
          f"건너뜀 {skipped}건, 오류 {len(errors)}건, 중단여부={aborted}")
    if errors:
        print("오류 예시(최대 10개):")
        for e in errors[:10]:
            print(" -", e)


if __name__ == "__main__":
    main()
