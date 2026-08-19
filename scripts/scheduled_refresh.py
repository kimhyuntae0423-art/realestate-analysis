"""정기 실행용 — 데이터 최신화 + 가설 전체 재검증.

Windows 작업 스케줄러에 등록해서 주기적으로 돌리는 스크립트.
1) 보유 중인 모든 시군구의 최근 N개월 실거래(매매/전월세)를 증분 수집
   (src/ui/shared/data_refresh.py의 수동 "데이터 최신화" 버튼과 같은 로직,
   Streamlit 없이 커맨드라인에서 돌 수 있도록 분리)
2) KB(가격지수·매수우위지수), ECOS(M2·주담대·기준금리·기대인플레·M1·부동산원
   실거래가지수), KOSIS 인구이동을 최신 범위로 재수집 (2026-08-19 추가 —
   전부 API 기반이라 자동화 가능. 입주물량(supply_schedule)은 KOSIS가
   시군구 단위 API를 안 줘서 CSV 수동 다운로드만 가능 — 자동화 불가, 제외)
3) 실험실 가설 전체 재검증 + data/experiments/hypothesis_log.json에 기록

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
from src.collectors.kb_price import KbPriceCollector
from src.collectors.kb_sentiment import KbSentimentCollector
from src.collectors.ecos import EcosCollector
from src.database.models import init_db
from src.database.repository import (
    upsert_trades, upsert_rents, fetch_trades_df,
    upsert_kb_price_series, upsert_kb_sentiment, upsert_ecos_series,
    upsert_population_flow,
)
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


def refresh_kb_ecos_population(months: int) -> dict:
    """KB(가격지수·매수우위지수), ECOS(M2 등 거시지표), KOSIS 인구이동 재수집.
    전부 API 기반이라 자동화 가능한 항목만 — 입주물량/호재/등급은 CSV 수동
    다운로드나 사람 판단이 필요해 여기 포함 안 됨(scheduled_refresh.py 상단 docstring 참고)."""
    from scripts.backfill_population_api import fetch as kosis_fetch, normalize as kosis_normalize

    summary = {"kb": 0, "ecos": 0, "population": 0, "errors": []}

    try:
        kb_price = KbPriceCollector()
        rows = kb_price.fetch_all_region_series(years=1) + kb_price.fetch_lead_apt50(years=1)
        summary["kb"] += upsert_kb_price_series(rows)
    except Exception as e:
        log.exception("KB 가격 시계열 수집 실패")
        summary["errors"].append(f"kb_price: {e}")

    try:
        rows = KbSentimentCollector().fetch_buy_sentiment(years=1)
        summary["kb"] += upsert_kb_sentiment(rows)
    except Exception as e:
        log.exception("KB 매수우위지수 수집 실패")
        summary["errors"].append(f"kb_sentiment: {e}")

    try:
        ecos = EcosCollector()
        rows = ecos.fetch_all(years=1) + ecos.fetch_kab_apt_price_index(years=1)
        summary["ecos"] += upsert_ecos_series(rows)
    except Exception as e:
        log.exception("ECOS 수집 실패")
        summary["errors"].append(f"ecos: {e}")

    try:
        ymds = months_back(months)
        raw = kosis_fetch(ymds[0], ymds[-1])
        rows = kosis_normalize(raw)
        summary["population"] += upsert_population_flow(rows)
    except Exception as e:
        log.exception("KOSIS 인구이동 수집 실패")
        summary["errors"].append(f"population: {e}")

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

    kb_ecos_pop = refresh_kb_ecos_population(args.months)
    log.info("KB/ECOS/인구이동 갱신: KB %d건, ECOS %d건, 인구이동 %d건, 오류 %d건",
              kb_ecos_pop["kb"], kb_ecos_pop["ecos"], kb_ecos_pop["population"],
              len(kb_ecos_pop["errors"]))
    for err in kb_ecos_pop["errors"]:
        log.warning("수집 오류: %s", err)

    log.info("=== 가설 재검증 시작 ===")
    results = run_all_and_log()
    for r in results:
        stat_str = f"{r.statistic:.4f}" if r.statistic == r.statistic else "NaN"
        log.info("%s | %s | n=%d | stat=%s", r.id, r.verdict, r.n, stat_str)
    log.info("=== 정기 갱신 완료 ===")


if __name__ == "__main__":
    main()
