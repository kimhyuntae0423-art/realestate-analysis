"""부동산 "전문가 통념" 가설 검증 실험실 — 프레임워크.

책·전문가들이 흔히 주장하는 상승 예측 신호를, 실제 실거래가 DB로 통계적으로
검증한다. 각 가설은 (통계치, 표본수, 방향, 판정)을 반환하고 결과는
data/experiments/hypothesis_log.json에 타임스탬프와 함께 누적 기록된다.

실제 가설 검증 함수들은 src/analysis/hypothesis_tests.py 에 있음 (300줄 제한으로 분리).
새 가설을 추가하려면: hypothesis_tests.py에 test_* 함수 작성 → 아래 ALL_HYPOTHESES에 등록.

판정 기준 (임계값은 보수적으로 고정):
  - 표본 부족(n < MIN_N) → "🟡 불확실 (표본부족)"
  - |rho| < RHO_THRESHOLD → "🟡 불확실 (상관 약함)"
  - |rho| >= RHO_THRESHOLD 이고 부호가 가설 방향과 같음 → "✅ 지지"
  - |rho| >= RHO_THRESHOLD 이고 부호가 가설 방향과 반대 → "❌ 기각(반대방향)"

주의: 상관관계 ≠ 인과관계. 이 결과는 투자 판단의 참고 자료이며,
"이 신호로 사라/팔아라"를 의미하지 않는다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from config.settings import ROOT

MIN_N = 30
RHO_THRESHOLD = 0.15
LOG_PATH = ROOT / "data" / "experiments" / "hypothesis_log.json"


def _verdict_for(statistic: float, n: int, expected_sign: int) -> str:
    if n < MIN_N or statistic != statistic:  # NaN check
        return "🟡 불확실 (표본부족)"
    if abs(statistic) < RHO_THRESHOLD:
        return "🟡 불확실 (상관 약함)"
    same_sign = (statistic > 0) == (expected_sign > 0)
    return "✅ 지지" if same_sign else "❌ 기각(반대방향)"


@dataclass
class HypothesisResult:
    id: str
    title: str
    claim: str                  # 검증하려는 주장 (전문가 통념)
    method: str                 # 어떻게 계산했는지 한 줄 설명
    statistic: float            # Spearman rho (NaN 가능)
    n: int
    expected_sign: int          # +1 = 양의 상관 기대, -1 = 음의 상관 기대
    caveats: str                # 반박 여지 / 한계
    computed_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    # 하위그룹 분석 (선택): {그룹명: {"statistic":, "n":, "verdict":}}
    breakdown: dict | None = None

    @property
    def verdict(self) -> str:
        return _verdict_for(self.statistic, self.n, self.expected_sign)

    def to_dict(self) -> dict:
        d = {**self.__dict__, "verdict": self.verdict}
        return d


def _empty_result(id: str, title: str, claim: str, method: str,
                   expected_sign: int, caveats: str) -> HypothesisResult:
    return HypothesisResult(id=id, title=title, claim=claim, method=method,
                             statistic=float("nan"), n=0,
                             expected_sign=expected_sign, caveats=caveats)


def get_all_hypotheses() -> list:
    """등록된 가설 검증 함수 전체.

    지연 import: hypothesis_tests*.py가 이 모듈(HypothesisResult 등)을 import하므로,
    모듈 최상단에서 바로 import하면 순환참조가 생겨 함수 호출 시점에 import한다.
    """
    from src.analysis import hypothesis_tests as t
    from src.analysis import hypothesis_tests_cycles as c
    return [
        t.test_redevelopment_age_effect,
        t.test_catalyst_announcement_vs_age,
        t.test_volume_leads_price,
        t.test_momentum_vs_reversion,
        c.test_seoul_leads_other_regions,
        c.test_large_units_lead_small_units,
        c.test_price_level_mean_reversion,
        c.test_regulation_balloon_effect,
    ]


# ─── 결과 기록 (append-only 로그) ───────────────────────────────────
def load_log() -> list[dict]:
    """과거 실행 기록 전체 (오래된 순)."""
    if not LOG_PATH.exists():
        return []
    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            return json.load(f).get("runs", [])
    except Exception:
        return []


def run_all_and_log() -> list[HypothesisResult]:
    """전체 가설을 재실행하고 결과를 로그에 append 한 뒤 반환."""
    results = [fn() for fn in get_all_hypotheses()]
    runs = load_log()
    runs.append({
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "results": [r.to_dict() for r in results],
    })
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"runs": runs}, f, ensure_ascii=False, indent=2)
    return results


def latest_results() -> list[dict] | None:
    """가장 최근 실행 결과 (없으면 None)."""
    runs = load_log()
    return runs[-1]["results"] if runs else None
