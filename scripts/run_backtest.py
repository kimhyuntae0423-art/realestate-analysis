"""점수 산정 검증 - 시군구/단지 백테스트 결과 출력.

usage:
    python -m scripts.run_backtest
    python -m scripts.run_backtest --grid          # 가중치 그리드 서치도 실행
    python -m scripts.run_backtest --test-months 6 # 검증 윈도우 6개월로 단축
"""
from __future__ import annotations
import argparse
import json
from datetime import date

import pandas as pd

from config.settings import ROOT
from src.analysis.backtest import (
    region_backtest, apt_backtest,
    grid_search_region, grid_search_apt,
)


def _print_result(r, region_map: dict[str, str] | None = None):
    print(f"\n[{r.scope.upper()}] n={r.n}  weights={r.weights}")
    print(f"  종합점수 ↔ 실제 상승률 Spearman corr: {r.spearman:+.3f}")
    print(f"  Top10 적중률 (실제 상위 20% 안): {r.top10_hit*100:.1f}%")
    print(f"  Top20 적중률 (실제 상위 20% 안): {r.top20_hit*100:.1f}%")
    print("  컴포넌트별 단독 상관:")
    for k, v in r.component_corr.items():
        print(f"    - {k:<14} {v:+.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-months", type=int, default=12)
    ap.add_argument("--train-months", type=int, default=12)
    ap.add_argument("--cw", type=float, default=0.30, help="catalyst weight")
    ap.add_argument("--tw", type=float, default=0.30, help="tier weight")
    ap.add_argument("--grid", action="store_true", help="가중치 그리드 서치")
    ap.add_argument("--save", action="store_true", help="결과 reports/backtest_*.csv 저장")
    args = ap.parse_args()

    print(f"검증일: {date.today()}  / train={args.train_months}mo  test={args.test_months}mo")
    print(f"현재 가중치: catalyst={args.cw}, tier={args.tw}")
    print("=" * 70)

    # ── 시군구 ──
    try:
        r_region = region_backtest(
            train_months=args.train_months, test_months=args.test_months,
            catalyst_weight=args.cw, tier_weight=args.tw,
        )
        _print_result(r_region)
    except ValueError as e:
        print(f"[REGION] 실패: {e}")

    # ── 단지 ──
    try:
        r_apt = apt_backtest(
            train_months=args.train_months, test_months=args.test_months,
            catalyst_weight=args.cw, tier_weight=args.tw,
        )
        _print_result(r_apt)
    except ValueError as e:
        print(f"[APT] 실패: {e}")

    # ── 그리드 서치 ──
    if args.grid:
        print("\n" + "=" * 70)
        print("[GRID] 시군구 단위 가중치 탐색 (Spearman 상위 10)")
        print("=" * 70)
        gs_r = grid_search_region(
            train_months=args.train_months, test_months=args.test_months,
        )
        print(gs_r.head(10).to_string(index=False))

        print("\n[GRID] 단지 단위 가중치 탐색 (Spearman 상위 10)")
        print("=" * 70)
        gs_a = grid_search_apt(
            train_months=args.train_months, test_months=args.test_months,
        )
        print(gs_a.head(10).to_string(index=False))

        if args.save:
            out_dir = ROOT / "data" / "reports"
            out_dir.mkdir(parents=True, exist_ok=True)
            gs_r.to_csv(out_dir / "backtest_region_grid.csv", index=False, encoding="utf-8-sig")
            gs_a.to_csv(out_dir / "backtest_apt_grid.csv", index=False, encoding="utf-8-sig")
            print(f"\n저장됨: {out_dir}/backtest_*_grid.csv")


if __name__ == "__main__":
    main()
