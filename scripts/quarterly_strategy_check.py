"""정기 실행용 — 전략 백테스트(WHERE축) 가중치 재검증.

Windows 작업 스케줄러에 분기별로 등록해서 돌리는 스크립트. 데이터가 쌓이면서
region_backtest/apt_backtest의 최적 가중치가 실제로 바뀌었는지(2026-08-18에
region 쪽에서 실제로 바뀐 걸 발견함) 주기적으로 확인하고 로그에 남긴다.

가중치를 자동으로 코드에 반영하지는 않음 — 이 로그를 사람이 검토해서
개선폭이 노이즈 수준(rho +0.02 이하)이 아니라 실제로 의미있게 크면
region_momentum.py / config.settings의 가중치를 수동으로 업데이트해야 함.

사용법:
    python -m scripts.quarterly_strategy_check
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json
from datetime import datetime

from src.database.models import init_db
from src.analysis.backtest import (
    region_backtest, grid_search_region, apt_backtest,
    _apt_backtest_base, _spearman,
)
from src.utils.logger import get_logger

log = get_logger(__name__)

LOG_PATH = ROOT / "data" / "experiments" / "strategy_backtest_log.json"
RHO_NOISE_THRESHOLD = 0.02  # 이보다 작은 개선은 노이즈로 간주 (2026-08-18 세션에서 확립한 기준)
_GRID = [round(x * 0.1, 1) for x in range(0, 11)]


def _load_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            return json.load(f).get("runs", [])
    except Exception:
        return []


def check_region_strategy() -> dict:
    """region_backtest 현재 가중치 vs 그리드서치 최적 비교."""
    current = region_backtest()
    grid = grid_search_region()
    if grid.empty:
        return {"current_spearman": current.spearman, "best_found": None}
    best = grid.iloc[0]
    gap = round(float(best["spearman"]) - current.spearman, 4)
    return {
        "current_spearman": round(current.spearman, 4),
        "current_top10": round(current.top10_hit, 3),
        "best_spearman": round(float(best["spearman"]), 4),
        "best_top10": round(float(best["top10_hit"]), 3),
        "best_weights": {"catalyst_w": float(best["catalyst_w"]), "tier_w": float(best["tier_w"]),
                          "rest_w": float(best["rest_w"])},
        "improvement": gap,
        "meaningful": gap > RHO_NOISE_THRESHOLD,
    }


def _apt_grid_search(base, components: dict) -> tuple[float, dict]:
    """4개 컴포넌트(이름->rank-pct 시리즈) 조합 중 actual_growth와 가장 상관 높은
    가중치 탐색 — 0.1 단위 3중 루프 + 나머지 가중치(2026-08-18 세션 방식과 동일)."""
    names = list(components.keys())
    assert len(names) == 4, "4개 컴포넌트 전용"
    actual = base["actual_growth"]
    best_rho, best_w = -1.0, None
    for w0 in _GRID:
        for w1 in _GRID:
            for w2 in _GRID:
                w3 = round(1.0 - w0 - w1 - w2, 1)
                if w3 < 0 or w3 > 1.0:
                    continue
                weights = [w0, w1, w2, w3]
                score = sum(components[n] * w for n, w in zip(names, weights))
                rho = _spearman(score * 100, actual)
                if rho == rho and rho > best_rho:
                    best_rho, best_w = rho, dict(zip(names, weights))
    return best_rho, best_w


def check_apt_strategy() -> dict:
    """apt_backtest 현재 가중치(market+prestige) vs 확장 그리드서치(+tier/train_growth/지역모멘텀) 비교."""
    from src.analysis.region_momentum import region_momentum_ranking

    base = _apt_backtest_base()
    current = apt_backtest()

    market_r = base["market_score"].rank(pct=True)
    tier_r = base["tier"].rank(pct=True)
    train_r = base["train_growth"].rank(pct=True)
    prestige_r = base["prestige_score"].rank(pct=True)

    mom = region_momentum_ranking(months=12)
    mom_map = dict(zip(mom["region_code"], mom["momentum_score"])) if not mom.empty else {}
    region_mom_r = base["region_code"].map(mom_map).fillna(50.0).rank(pct=True)

    rho1, w1 = _apt_grid_search(base, {
        "market": market_r, "tier": tier_r, "train_growth": train_r, "prestige": prestige_r,
    })
    rho2, w2 = _apt_grid_search(base, {
        "market": market_r, "region_momentum": region_mom_r, "train_growth": train_r, "prestige": prestige_r,
    })
    best_rho, best_weights, best_label = (
        (rho1, w1, "market+tier+train_growth+prestige") if rho1 >= rho2
        else (rho2, w2, "market+region_momentum+train_growth+prestige")
    )
    gap = round(best_rho - current.spearman, 4)
    return {
        "current_spearman": round(current.spearman, 4),
        "current_top10": round(current.top10_hit, 3),
        "best_spearman": round(best_rho, 4),
        "best_combo": best_label,
        "best_weights": best_weights,
        "improvement": gap,
        "meaningful": gap > RHO_NOISE_THRESHOLD,
    }


def main():
    init_db()
    log.info("=== 분기 전략 백테스트 재검증 시작 ===")

    region_result = check_region_strategy()
    log.info("region_backtest: 현재=%.4f 최적발견=%s 개선폭=%s 유의미=%s",
              region_result["current_spearman"], region_result.get("best_spearman"),
              region_result.get("improvement"), region_result.get("meaningful"))

    apt_result = check_apt_strategy()
    log.info("apt_backtest: 현재=%.4f 최적발견=%.4f(%s) 개선폭=%s 유의미=%s",
              apt_result["current_spearman"], apt_result["best_spearman"], apt_result["best_combo"],
              apt_result["improvement"], apt_result["meaningful"])

    if region_result.get("meaningful") or apt_result.get("meaningful"):
        log.warning("⚠️ 노이즈 기준(rho +%.2f) 초과 개선 발견 — region_momentum.py/config.settings "
                    "가중치 재검토 필요", RHO_NOISE_THRESHOLD)

    runs = _load_log()
    runs.append({
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "region": region_result,
        "apt": apt_result,
    })
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"runs": runs}, f, ensure_ascii=False, indent=2)
    log.info("=== 분기 전략 백테스트 재검증 완료 (로그: %s) ===", LOG_PATH)


if __name__ == "__main__":
    main()
