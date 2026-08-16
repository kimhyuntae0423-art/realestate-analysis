"""정기 실행용 — 데이터 최신화 + 가설 전체 재검증.

Windows 작업 스케줄러에 등록해서 주기적으로 돌리는 스크립트.
1) 보유 중인 모든 시군구의 최근 N개월 실거래(매매/전월세)를 증분 수집
   (src/ui/shared/data_refresh.py의 수동 "데이터 최신화" 버튼과 같은 로직,
   Streamlit 없이 커맨드라인에서 돌 수 있도록 분리)
2) 실험실 가설 전체 재검증 + data/experiments/hypothesis_log.json에 기록

사용법:
    python -m scripts.scheduled_refresh --months 3
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
from datetime import date

from src.collectors.molit_api import MolitCollector
from src.database.models import init_db
from src.database.repository import upsert_trades, upsert_rents, fetch_trades_df
from src.analysis.hypothesis_lab import run_all_and_log
from src.utils.logger import get_logger

log = get_logger(__name__)


def months_back(n: int) -> list[str]:
    """최근 n개월의 YYYYMM 리스트 (오름차순)"""
    today = date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def refresh_trades(months: int) -> dict:
    """보유 중인 모든 시군구의 최근 N개월 실거래를 증분 수집."""
    df = fetch_trades_df()
    regions = sorted(df["region_code"].unique()) if not df.empty else []
    ymds = months_back(months)
    mc = MolitCollector()
    summary = {"trade": 0, "rent": 0, "errors": []}
    for region in regions:
        for ymd in ymds:
            try:
                rows = mc.fetch_trades(region, ymd)
                summary["trade"] += upsert_trades(rows)
                rows = mc.fetch_rents(region, ymd)
                summary["rent"] += upsert_rents(rows)
            except Exception as e:
                log.exception("수집 실패 %s %s", region, ymd)
                summary["errors"].append(f"{region}/{ymd}: {e}")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=3, help="최근 N개월 증분 수집 (기본 3)")
    args = ap.parse_args()

    init_db()
    log.info("=== 정기 데이터 갱신 시작 ===")
    summary = refresh_trades(args.months)
    log.info("실거래 갱신: 매매 %d건, 전월세 %d건, 오류 %d건",
              summary["trade"], summary["rent"], len(summary["errors"]))
    for err in summary["errors"][:10]:
        log.warning("수집 오류: %s", err)

    log.info("=== 가설 재검증 시작 ===")
    results = run_all_and_log()
    for r in results:
        stat_str = f"{r.statistic:.4f}" if r.statistic == r.statistic else "NaN"
        log.info("%s | %s | n=%d | stat=%s", r.id, r.verdict, r.n, stat_str)
    log.info("=== 정기 갱신 완료 ===")


if __name__ == "__main__":
    main()
