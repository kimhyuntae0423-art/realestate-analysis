"""정기 실행용 — 데이터 최신화 + 가설 전체 재검증.

Windows 작업 스케줄러에 등록해서 주기적으로 돌리는 스크립트.
1) 보유 중인 모든 시군구의 최근 N개월 실거래(매매/전월세)를 증분 수집
   (src/ui/shared/data_refresh.py의 수동 "데이터 최신화" 버튼과 같은 로직,
   Streamlit 없이 커맨드라인에서 돌 수 있도록 분리)
2) KB(가격지수·매수우위지수), ECOS(M2·주담대·기준금리·기대인플레·M1·부동산원
   실거래가지수)를 최신 범위로 재수집 (2026-08-19 추가 — 전부 API 기반이라
   자동화 가능. KOSIS 인구이동·입주물량 수집은 2026-10-08에 영구 중단했다 —
   그 데이터로 돌던 가설 3개가 22회 내내 "불확실"이라 삭제했다. 되살리지 말 것)
3) 실험실 가설 전체 재검증 + data/experiments/hypothesis_log.json에 기록

사용법:
    python -m scripts.scheduled_refresh --months 3
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
from datetime import date, datetime

from src.collectors.molit_api import MolitCollector
from src.collectors.kb_price import KbPriceCollector
from src.collectors.kb_sentiment import KbSentimentCollector
from src.collectors.ecos import EcosCollector
from src.database.models import init_db
from src.database.repository import (
    upsert_trades, upsert_rents, fetch_trades_df,
    upsert_kb_price_series, upsert_kb_sentiment, upsert_ecos_series,
)
from src.analysis.hypothesis_lab import run_all_and_log
from src.utils.ca_bundle import ensure_ca_bundle
from src.utils.logger import get_logger
from src.utils.notify import notify_refresh_failure

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


def refresh_kb_ecos(months: int) -> dict:
    """KB(가격지수·매수우위지수), ECOS(M2 등 거시지표) 재수집.
    전부 API 기반이라 자동화 가능한 항목만 — 호재/등급은 사람 판단이 필요해
    여기 포함 안 됨(scheduled_refresh.py 상단 docstring 참고)."""
    summary = {"kb": 0, "ecos": 0, "errors": []}

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

    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=3, help="최근 N개월 증분 수집 (기본 3)")
    args = ap.parse_args()

    # 사내망 SSL 인터셉션 대응 — 이게 없으면 실거래 API 호출이 전부
    # CERTIFICATE_VERIFY_FAILED 로 실패한다 (2026-05 수집 중단 원인).
    ensure_ca_bundle()

    # 단계별 실패를 모아 마지막에 한 번만 알린다. 2026-09 에 Supabase 동기화가
    # 2주 내리 실패했는데 로그에만 남아서 아무도 몰랐다 — 그래서 붙인 장치다.
    failures: list[str] = []

    init_db()
    log.info("=== 정기 데이터 갱신 시작 ===")
    summary = refresh_trades(args.months)
    log.info("실거래 갱신: 매매 %d건, 전월세 %d건, 오류 %d건",
              summary["trade"], summary["rent"], len(summary["errors"]))
    for err in summary["errors"][:10]:
        log.warning("수집 오류: %s", err)
    if summary["errors"]:
        failures.append(f"실거래 수집 오류 {len(summary['errors'])}건 "
                        f"(첫 건: {summary['errors'][0]})")

    kb_ecos = refresh_kb_ecos(args.months)
    log.info("KB/ECOS 갱신: KB %d건, ECOS %d건, 오류 %d건",
              kb_ecos["kb"], kb_ecos["ecos"], len(kb_ecos["errors"]))
    for err in kb_ecos["errors"]:
        log.warning("수집 오류: %s", err)
    if kb_ecos["errors"]:
        failures.append(f"KB/ECOS 수집 오류 {len(kb_ecos['errors'])}건 "
                        f"(첫 건: {kb_ecos['errors'][0]})")

    log.info("=== 가설 재검증 시작 ===")
    try:
        results = run_all_and_log()
        for r in results:
            stat_str = f"{r.statistic:.4f}" if r.statistic == r.statistic else "NaN"
            log.info("%s | %s | n=%d | stat=%s", r.id, r.verdict, r.n, stat_str)
    except Exception as e:
        log.exception("가설 재검증 실패")
        failures.append(f"가설 재검증 실패: {e}")

    # 배포 Streamlit 이 읽는 클라우드 복제본에 반영.
    # 실패해도 로컬 갱신 결과는 유효하므로 전체를 중단시키지 않는다 —
    # 대신 아래에서 반드시 알린다(조용히 넘어가지 않게).
    log.info("=== Supabase 동기화 시작 ===")
    try:
        from scripts.migrate_to_supabase import run_sync
        rc = run_sync()
        log.info("Supabase 동기화 종료 rc=%s", rc)
        if rc != 0:
            failures.append(f"Supabase 동기화 비정상 종료 rc={rc}")
    except Exception as e:
        log.exception("Supabase 동기화 실패 — 로컬 데이터는 정상")
        failures.append(f"Supabase 동기화 실패: {e}")

    if failures:
        notify_refresh_failure(
            failures, datetime.now().strftime("%Y-%m-%d %H:%M"))
    log.info("=== 정기 갱신 완료 === (실패 %d건)", len(failures))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # 여기까지 왔다면 단계별 집계도 못 하고 죽은 것이다 — 그래도 알린다.
        # (알림까지 실패하면 notify 쪽이 삼키고 로그만 남긴다)
        log.exception("정기 갱신이 중단됐다")
        notify_refresh_failure([f"정기 갱신 중단: {type(e).__name__}: {e}"],
                                datetime.now().strftime("%Y-%m-%d %H:%M"))
        raise
