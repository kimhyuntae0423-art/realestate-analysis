"""국토부 실거래가 수집 (매매 + 전월세)

사용법:
    # 단일 지역, 최근 12개월
    python scripts/collect_data.py --region 11680 --months 12

    # 여러 지역
    python scripts/collect_data.py --regions 11680,11650,11710 --months 24

    # 매매만
    python scripts/collect_data.py --region 11680 --months 12 --no-rent
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
from datetime import date
from tqdm import tqdm

from src.collectors.molit_api import MolitCollector
from src.collectors.regulation_news import collect_regulation_news
from src.database.models import init_db
from src.database.repository import upsert_trades, upsert_rents, log_collection
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


def collect_region(mc: MolitCollector, region: str, ymds: list[str],
                   do_trade: bool, do_rent: bool):
    for ymd in tqdm(ymds, desc=f"[{region}]"):
        if do_trade:
            try:
                rows = mc.fetch_trades(region, ymd)
                inserted = upsert_trades(rows)
                log_collection("molit_trade", region, ymd, len(rows), inserted, "ok")
            except Exception as e:
                log.exception("trade 수집 실패 %s %s", region, ymd)
                log_collection("molit_trade", region, ymd, 0, 0, "fail", str(e))

        if do_rent:
            try:
                rows = mc.fetch_rents(region, ymd)
                inserted = upsert_rents(rows)
                log_collection("molit_rent", region, ymd, len(rows), inserted, "ok")
            except Exception as e:
                log.exception("rent 수집 실패 %s %s", region, ymd)
                log_collection("molit_rent", region, ymd, 0, 0, "fail", str(e))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--region", help="법정동 시군구 5자리 (예: 11680)")
    g.add_argument("--regions", help="콤마로 구분된 지역 코드들")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--no-trade", action="store_true")
    ap.add_argument("--no-rent", action="store_true")
    ap.add_argument("--skip-reg-news", action="store_true",
                    help="규제 변경 뉴스 감지 건너뜀")
    args = ap.parse_args()

    init_db()
    regions = [args.region] if args.region else [r.strip() for r in args.regions.split(",") if r.strip()]
    ymds = months_back(args.months)

    log.info("지역=%s, 기간=%s ~ %s (%d개월)",
             regions, ymds[0], ymds[-1], len(ymds))

    mc = MolitCollector()
    for region in regions:
        collect_region(mc, region, ymds,
                       do_trade=not args.no_trade,
                       do_rent=not args.no_rent)

    # ── 규제 뉴스 변경 감지 (자동 반영 아님 — 알림 전용) ──
    if not args.skip_reg_news:
        print("\n[규제 뉴스 감지 중...]")
        result = collect_regulation_news(days=30)
        if result["count"] == 0:
            print("  최근 30일 규제 관련 뉴스 없음")
        else:
            print(f"  ⚠️  규제 관련 뉴스 {result['count']}건 감지 — 앱 사이드바에서 확인하세요")
            for art in result["articles"][:3]:
                print(f"    [{art['datetime']}] {art['title'][:60]}")

    print("\nOK: 수집 완료")


if __name__ == "__main__":
    main()
