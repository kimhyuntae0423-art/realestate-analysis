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

import numpy as np
import pandas as pd

from config.settings import ROOT

MIN_N = 30
RHO_THRESHOLD = 0.15
LOG_PATH = ROOT / "data" / "experiments" / "hypothesis_log.json"


def reindex_monthly(g: pd.DataFrame, group_cols: list[str], ym_col: str = "ym") -> pd.DataFrame:
    """그룹(지역 등)별로 월 인덱스를 촘촘하게 채운다 — 빠진 달을 명시적 NaN 행으로 만든다.

    groupby 후 min_deals 미달 등으로 값이 없는 달을 그냥 드롭하면, 이후 pct_change()가
    그 빈 구간을 조용히 건너뛰어 "한 달 변화율"이라 표기된 값이 실제로는 여러 달치
    누적 변화일 수 있다. 이 함수로 결측월을 NaN 행으로 명시해두면 pct_change()가
    결측 다음 행에도 정확히 NaN을 내보내(직전 값이 없다고 인식), 다개월 변화가 단일월
    변화로 잘못 표기되는 걸 막는다. 호출부는 이 함수 다음에 pct_change()를 호출해야 한다.
    """
    if g.empty:
        return g
    out = []
    for key, sub in g.groupby(group_cols):
        full = pd.period_range(sub[ym_col].min(), sub[ym_col].max(), freq="M")
        sub = sub.set_index(ym_col).reindex(full)
        sub.index.name = ym_col
        sub = sub.reset_index()
        key_tuple = key if isinstance(key, tuple) else (key,)
        for col, val in zip(group_cols, key_tuple):
            sub[col] = val
        out.append(sub)
    return pd.concat(out, ignore_index=True)


def region_growth_via_unit_tracking(df: pd.DataFrame, group_cols: list[str],
                                     area_tol: float = 5.0, min_unit_deals: int = 1) -> pd.DataFrame:
    """지역(구성원 그룹) 전체의 "이번달 중위가 vs 다음달 중위가"로 성장률을 재면,
    그 달 우연히 어떤 단지·평형이 거래됐는지(구성효과)에 따라 실제 가격 변동과 무관하게
    출렁인다 — KB 공식 가격지수와 비교했더니 이 방식의 월간 성장률은 상관이 거의 0(-0.2)
    이었음(2026-08-17 감리). 같은 단지+평형을 이번달->다음달로 추적한 성장률을 거래량
    가중평균해 지역 성장률로 집계하면 이 노이즈가 크게 줄어든다(같은 비교로 상관 +0.63).

    df는 region_code, apt_name, area_m2, deal_date, price_per_pyeong 컬럼과
    group_cols에 필요한 추가 컬럼(sido, size_class 등)을 이미 갖고 있어야 한다.
    반환: group_cols + ["ym", "growth", "n"] — n은 그 달 성장률 계산에 쓰인 거래 건수 합
    (지역 단위 신뢰도 필터링용). 그룹 첫 시점은 growth가 NaN(직전 없음)이라 애초에 빠짐.
    """
    from src.analysis.recommend import _bucketize

    if df.empty:
        return pd.DataFrame(columns=group_cols + ["ym", "growth", "n"])
    df = _bucketize(df, area_tol)
    df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M")
    unit_keys = group_cols + ["apt_name", "area_bucket"]
    unit_g = df.groupby(unit_keys + ["ym"]).agg(
        ppp=("price_per_pyeong", "median"), n=("price_per_pyeong", "count")
    ).reset_index()
    unit_g = unit_g[unit_g["n"] >= min_unit_deals].sort_values(unit_keys + ["ym"])
    unit_g["unit_growth"] = unit_g.groupby(unit_keys)["ppp"].pct_change()

    valid = unit_g.replace([np.inf, -np.inf], np.nan).dropna(subset=["unit_growth"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=group_cols + ["ym", "growth"])
    valid["weighted"] = valid["unit_growth"] * valid["n"]
    agg = valid.groupby(group_cols + ["ym"]).agg(
        weighted_sum=("weighted", "sum"), n=("n", "sum")
    ).reset_index()
    agg["growth"] = agg["weighted_sum"] / agg["n"]
    return agg[group_cols + ["ym", "growth", "n"]]


def jeonse_ratio_via_unit_matching(df_trade: pd.DataFrame, df_rent: pd.DataFrame,
                                    group_cols: list[str], area_tol: float = 5.0) -> pd.DataFrame:
    """전세가율(전세/매매)을 지역(구성원 그룹)×월 raw median끼리 나누면, 그 달 매매/전세
    각각 우연히 어떤 단지·평형이 거래됐는지(구성효과)가 분자·분모에 이중으로 껴서 왜곡된다
    — KB 공식 전세가격비율과 비교했더니 지역별로 쪼개면 전부 반대 부호(rho -0.15~-0.68)였음
    (2026-08-17 감리). 같은 단지+평형 유닛에서 그 달 매매와 전세가 동시에 관측된 경우만
    매칭해 유닛별 비율을 구하고, 거래량(min(매매건수,전세건수)) 가중평균으로 집계하면
    부호가 KB와 같은 방향으로 돌아온다(같은 비교로 rho -0.185 -> +0.157).

    df_trade는 price_per_pyeong, df_rent는 ppp(전세환산 평당가) 컬럼이 이미 있어야 한다.
    반환: group_cols + ["ym", "jeonse_ratio", "n"] — n은 매칭에 쓰인 거래건수(가중치용).
    """
    from src.analysis.recommend import _bucketize

    cols = group_cols + ["ym", "jeonse_ratio", "n"]
    if df_trade.empty or df_rent.empty:
        return pd.DataFrame(columns=cols)
    t = _bucketize(df_trade, area_tol)
    r = _bucketize(df_rent, area_tol)
    t["ym"] = pd.to_datetime(t["deal_date"]).dt.to_period("M")
    r["ym"] = pd.to_datetime(r["deal_date"]).dt.to_period("M")
    unit_keys = group_cols + ["apt_name", "area_bucket", "ym"]
    t_u = t.groupby(unit_keys).agg(
        trade_med=("price_per_pyeong", "median"), trade_n=("price_per_pyeong", "count")
    ).reset_index()
    r_u = r.groupby(unit_keys).agg(
        rent_med=("ppp", "median"), rent_n=("ppp", "count")
    ).reset_index()

    unit = t_u.merge(r_u, on=unit_keys, how="inner")
    if unit.empty:
        return pd.DataFrame(columns=cols)
    unit["ratio"] = unit["rent_med"] / unit["trade_med"] * 100
    unit["n"] = unit[["trade_n", "rent_n"]].min(axis=1)
    unit = unit.replace([np.inf, -np.inf], np.nan).dropna(subset=["ratio"])
    unit["weighted"] = unit["ratio"] * unit["n"]

    agg = unit.groupby(group_cols + ["ym"]).agg(
        weighted_sum=("weighted", "sum"), n=("n", "sum")
    ).reset_index()
    agg["jeonse_ratio"] = agg["weighted_sum"] / agg["n"]
    return agg[cols]


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
    # 이미 시도해봤지만 결론이 안 바뀐 변형들 (선택) — 다음에 같은 걸 또 시도하지 않도록 기록
    explored: str | None = None

    @property
    def verdict(self) -> str:
        return _verdict_for(self.statistic, self.n, self.expected_sign)

    def to_dict(self) -> dict:
        d = {**self.__dict__, "verdict": self.verdict}
        return d


def _empty_result(id: str, title: str, claim: str, method: str,
                   expected_sign: int, caveats: str, explored: str | None = None) -> HypothesisResult:
    return HypothesisResult(id=id, title=title, claim=claim, method=method,
                             statistic=float("nan"), n=0,
                             expected_sign=expected_sign, caveats=caveats, explored=explored)


def get_all_hypotheses() -> list:
    """등록된 가설 검증 함수 전체.

    지연 import: hypothesis_tests*.py가 이 모듈(HypothesisResult 등)을 import하므로,
    모듈 최상단에서 바로 import하면 순환참조가 생겨 함수 호출 시점에 import한다.
    """
    from src.analysis import hypothesis_tests as t
    from src.analysis import hypothesis_tests_cycles as c
    from src.analysis import hypothesis_tests_valuation as v
    from src.analysis import hypothesis_tests_kb as k
    from src.analysis import hypothesis_tests_ecos as e
    return [
        t.test_catalyst_announcement_vs_age,
        t.test_volume_leads_price,
        t.test_momentum_vs_reversion,
        c.test_seoul_leads_other_regions,
        c.test_large_units_lead_small_units,
        c.test_price_level_mean_reversion,
        c.test_regulation_balloon_effect,
        v.test_jeonse_ratio_leads_price,
        v.test_supply_leads_price_decline,
        v.test_population_migration_leads_price,
        v.test_buyer_sentiment_leads_price,
        k.test_supply_leads_price_decline_kb,
        k.test_buyer_sentiment_leads_price_kb,
        e.test_money_supply_leads_price,
        e.test_price_leads_money_supply,
        e.test_mortgage_loan_leads_price,
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


# ─── 미검증 후보 (통계 검증을 아직 시도하지 않은 가설) ──────────────────
@dataclass
class PendingHypothesis:
    id: str
    title: str
    claim: str
    data_status: str  # 필요한 데이터가 있는지/없는지
    note: str          # 왜 아직 안 만들었는지 · 다음 단계


PENDING_HYPOTHESES: list[PendingHypothesis] = [
    PendingHypothesis(
        id="school_district",
        title="학군 효과",
        claim="학군이 좋은 지역일수록 가격이 더 오른다",
        data_status="데이터 없음 — 교육부 학교알리미 데이터 미수집",
        note="수집 파이프라인부터 필요",
    ),
    PendingHypothesis(
        id="interest_rate",
        title="기준금리 변동 선행",
        claim="기준금리가 내리면(오르면) 가격이 뒤따라 오른다(내린다)",
        data_status="데이터 정적 — macro.py 신호가 수동 토글식이라 과거 시계열 없음",
        note="금리 시계열 수집부터 필요",
    ),
]


def get_pending_hypotheses() -> list[PendingHypothesis]:
    """아직 검증을 시도하지 않은 가설 후보 전체."""
    return PENDING_HYPOTHESES
