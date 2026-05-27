"""점수 산정 검증 - 시군구/단지/갭투자 백테스트 결과 출력.

usage:
    python -m scripts.run_backtest                  # 기존 투자수익 백테스트
    python -m scripts.run_backtest --gap            # 갭투자 4종 백테스트
    python -m scripts.run_backtest --gap --walk     # walk-forward 포함
    python -m scripts.run_backtest --grid           # 가중치 그리드 서치
    python -m scripts.run_backtest --test-months 6  # 검증 윈도우 6개월
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
from src.analysis.gap_backtest import (
    gap_score_backtest, jeonse_risk_backtest,
    gap_simulation_backtest, gap_walk_forward,
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
    ap.add_argument("--gap", action="store_true", help="갭투자 4종 백테스트 실행")
    ap.add_argument("--walk", action="store_true", help="Walk-forward (--gap과 함께 사용)")
    ap.add_argument("--walk-windows", type=int, default=4, help="Walk-forward 시점 수")
    ap.add_argument("--top-n", type=int, default=20, help="시뮬레이션 TOP-N 단지 수")
    ap.add_argument("--fall-threshold", type=float, default=3.0,
                    help="역전세 판정 기준 (%p 하락)")
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

    # ── 갭투자 백테스트 ──────────────────────────────────────────
    if args.gap:
        print("\n" + "=" * 70)
        print("[ 갭투자 백테스트 ]")
        print("=" * 70)

        # A. 점수-수익률 상관관계
        print("\n[A] 갭투자 점수 vs 실제 매매가 상승률 (Spearman ρ)")
        try:
            ra = gap_score_backtest(
                train_months=args.train_months,
                test_months=args.test_months,
            )
            print(f"  시점: {ra.as_of}  n={ra.n}")
            print(f"  종합 점수 ↔ 실제 상승률:  ρ = {ra.spearman:+.3f}")
            print(f"  Top10 적중률 (실제 상위 20%): {ra.top10_hit*100:.1f}%")
            print(f"  Top20 적중률 (실제 상위 20%): {ra.top20_hit*100:.1f}%")
            print("  요소별 단독 ρ:")
            for k, v in ra.component_corr.items():
                print(f"    - {k:<18} {v:+.3f}")
            if args.save:
                out_dir = ROOT / "data" / "reports"
                out_dir.mkdir(parents=True, exist_ok=True)
                ra.raw.to_csv(out_dir / "gap_backtest_A.csv", index=False, encoding="utf-8-sig")
        except ValueError as e:
            print(f"  실패: {e}")

        # B. 역전세 리스크 분류 정확도
        print(f"\n[B] 역전세 리스크 분류 정확도 (기준: {args.fall_threshold}%p 하락)")
        try:
            rb = jeonse_risk_backtest(
                train_months=args.train_months,
                test_months=args.test_months,
                fall_threshold_pct=args.fall_threshold,
            )
            print(f"  시점: {rb.as_of}  n={rb.n}  실제 역전세 발생: {rb.n_actual_risk}건")
            print(f"  Precision: {rb.precision:.3f}  Recall: {rb.recall:.3f}  F1: {rb.f1:.3f}")
            c = rb.confusion
            print(f"  Confusion: TP={c['TP']}  FP={c['FP']}  FN={c['FN']}  TN={c['TN']}")
            if args.save:
                out_dir = ROOT / "data" / "reports"
                out_dir.mkdir(parents=True, exist_ok=True)
                rb.raw.to_csv(out_dir / "gap_backtest_B.csv", index=False, encoding="utf-8-sig")
        except ValueError as e:
            print(f"  실패: {e}")

        # C. 갭 변화 수익 시뮬레이션
        print(f"\n[C] 갭투자 TOP-{args.top_n} 수익 시뮬레이션")
        try:
            rc = gap_simulation_backtest(
                train_months=args.train_months,
                hold_months=args.test_months,
                top_n=args.top_n,
            )
            print(f"  시점: {rc.as_of}  보유: {rc.hold_months}개월  매칭: {rc.n_matched}건")
            print(f"  평균 매매가 상승률:    {rc.avg_price_growth_pct:+.2f}%")
            print(f"  평균 갭 변화율:        {rc.avg_gap_change_pct:+.2f}%  (음수=갭 감소)")
            print(f"  평균 자기자본 수익률:  {rc.avg_roe_pct:+.2f}%")
            print(f"  중앙값 자기자본 수익률:{rc.median_roe_pct:+.2f}%")
            if args.save:
                out_dir = ROOT / "data" / "reports"
                out_dir.mkdir(parents=True, exist_ok=True)
                rc.raw.to_csv(out_dir / "gap_backtest_C.csv", index=False, encoding="utf-8-sig")
        except ValueError as e:
            print(f"  실패: {e}")

        # D. Walk-forward
        if args.walk:
            for method_label, method_key in [
                ("A: 점수-수익률", "score"),
                ("B: 역전세 리스크", "risk"),
                ("C: 수익 시뮬레이션", "simulation"),
            ]:
                print(f"\n[D-{method_label}] Walk-forward ({args.walk_windows}개 시점)")
                try:
                    rd = gap_walk_forward(
                        n_windows=args.walk_windows,
                        test_months=args.test_months,
                        train_months=args.train_months,
                        method=method_key,
                        fall_threshold_pct=args.fall_threshold,
                        top_n=args.top_n,
                    )
                    print(rd.summary.to_string(index=False))
                    if method_key == "score":
                        print(f"  평균 ρ: {rd.avg_spearman:+.3f} ± {rd.std_spearman:.3f}")
                    elif method_key == "risk":
                        print(f"  평균 F1: {rd.avg_f1:.3f} ± {rd.std_f1:.3f}")
                    elif method_key == "simulation":
                        print(f"  평균 ROE: {rd.avg_roe_pct:+.2f}% ± {rd.std_roe_pct:.2f}%")
                    if args.save:
                        out_dir = ROOT / "data" / "reports"
                        out_dir.mkdir(parents=True, exist_ok=True)
                        rd.summary.to_csv(
                            out_dir / f"gap_walkforward_{method_key}.csv",
                            index=False, encoding="utf-8-sig"
                        )
                except Exception as e:
                    print(f"  실패: {e}")


if __name__ == "__main__":
    main()
