"""부동산 "전문가 통념" 가설 검증 실험실.

책·전문가들이 흔히 주장하는 상승 예측 신호를, 실제 실거래가 DB로 통계적으로
검증한다. 각 가설은 (통계치, 표본수, 방향, 판정)을 반환하고 결과는
data/experiments/hypothesis_log.json에 타임스탬프와 함께 누적 기록된다.

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
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config.settings import ROOT
from src.database.repository import fetch_trades_df
from src.analysis.recommend import _bucketize

MIN_N = 30
RHO_THRESHOLD = 0.15
LOG_PATH = ROOT / "data" / "experiments" / "hypothesis_log.json"


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

    @property
    def verdict(self) -> str:
        if self.n < MIN_N or self.statistic != self.statistic:  # NaN check
            return "🟡 불확실 (표본부족)"
        if abs(self.statistic) < RHO_THRESHOLD:
            return "🟡 불확실 (상관 약함)"
        same_sign = (self.statistic > 0) == (self.expected_sign > 0)
        return "✅ 지지" if same_sign else "❌ 기각(반대방향)"

    def to_dict(self) -> dict:
        d = {**self.__dict__, "verdict": self.verdict}
        return d


def _empty_result(id: str, title: str, claim: str, method: str,
                   expected_sign: int, caveats: str) -> HypothesisResult:
    return HypothesisResult(id=id, title=title, claim=claim, method=method,
                             statistic=float("nan"), n=0,
                             expected_sign=expected_sign, caveats=caveats)


# ─── 1. 재건축 연한 효과 ────────────────────────────────────────────
def test_redevelopment_age_effect(months: int = 24, area_tol: float = 5.0,
                                   min_deals: int = 3) -> HypothesisResult:
    meta = dict(
        id="redevelopment_age",
        title="재건축 연한 효과",
        claim="오래된(재건축 기대감 있는) 단지일수록 최근 상승률이 더 높다",
        method=f"단지+평형 단위, 최근 {months}개월을 반으로 나눠 전반기→후반기 평당가 "
               f"상승률과 연식(2026-현재 - 준공연도)의 Spearman 상관",
        expected_sign=1,
        caveats="재건축은 '연한'만이 아니라 안전진단·조합설립 진행도가 더 중요할 수 있음. "
                "너무 오래된 단지는 오히려 슬럼화로 하락할 수도 있어 비선형(U자형) 관계일 가능성 있음.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    end = df["deal_date"].max()
    mid = end - pd.DateOffset(months=months // 2)

    keys = ["region_code", "apt_name", "area_bucket"]
    recent = df[df["deal_date"] > mid]
    prior = df[df["deal_date"] <= mid]
    r = recent.groupby(keys).agg(recent_ppp=("price_per_pyeong", "median"),
                                  recent_n=("price_per_pyeong", "count"),
                                  build_year=("build_year", "max"))
    p = prior.groupby(keys).agg(prior_ppp=("price_per_pyeong", "median"),
                                 prior_n=("price_per_pyeong", "count"))
    g = r.join(p, how="inner").reset_index()
    g = g[(g["recent_n"] >= min_deals) & (g["prior_n"] >= min_deals)
          & g["build_year"].notna() & (g["build_year"] > 1900)]
    if g.empty:
        return _empty_result(**meta)

    g["growth_%"] = (g["recent_ppp"] - g["prior_ppp"]) / g["prior_ppp"] * 100
    g["age"] = date.today().year - g["build_year"]
    rho, _ = spearmanr(g["age"], g["growth_%"])
    return HypothesisResult(statistic=float(rho), n=len(g), **meta)


# ─── 2. 거래량 선행지표 ─────────────────────────────────────────────
def test_volume_leads_price(months: int = 30) -> HypothesisResult:
    meta = dict(
        id="volume_leads_price",
        title="거래량 선행지표",
        claim="이번 달 거래량이 늘면(줄면) 다음 달 가격이 오른다(내린다) — 거래량이 가격을 선행한다",
        method=f"시군구×월 단위, 최근 {months}개월. 거래량 전월대비 변화율(t) vs "
               "평당가 전월대비 변화율(t+1)의 Spearman 상관 (시군구별 시차 적용)",
        expected_sign=1,
        caveats="동시성(같은 달 거래량↔가격) 상관과 섞여있을 수 있음 — 별도로 동시성 상관도 "
                "함께 계산해 caveats에 병기. 지역 규모가 작으면 월별 거래량 변동이 노이즈일 수 있음.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M")
    g = df.groupby(["region_code", "ym"]).agg(
        volume=("deal_amount", "count"),
        ppp=("price_per_pyeong", "median"),
    ).reset_index().sort_values(["region_code", "ym"])

    g["vol_chg"] = g.groupby("region_code")["volume"].pct_change()
    g["price_chg"] = g.groupby("region_code")["ppp"].pct_change()
    g["price_chg_next"] = g.groupby("region_code")["price_chg"].shift(-1)

    lead = g[["vol_chg", "price_chg_next"]].replace([np.inf, -np.inf], np.nan).dropna()
    contemp = g[["vol_chg", "price_chg"]].replace([np.inf, -np.inf], np.nan).dropna()

    if lead.empty:
        return _empty_result(**meta)
    rho_lead, _ = spearmanr(lead["vol_chg"], lead["price_chg_next"])
    rho_contemp = (spearmanr(contemp["vol_chg"], contemp["price_chg"])[0]
                   if not contemp.empty else float("nan"))

    result = HypothesisResult(statistic=float(rho_lead), n=len(lead), **meta)
    result.caveats += f" | 참고: 동시성(같은 달) 상관 ρ={rho_contemp:.3f} (n={len(contemp)})"
    return result


# ─── 3. 모멘텀 지속 vs 평균회귀 ─────────────────────────────────────
def test_momentum_vs_reversion(months: int = 24, area_tol: float = 5.0,
                                min_deals: int = 3) -> HypothesisResult:
    meta = dict(
        id="momentum_vs_reversion",
        title="모멘텀 지속 vs 평균회귀",
        claim="최근 많이 오른 단지는 계속 오른다 (모멘텀 지속). "
              "* 반대(평균회귀)라면 최근 많이 오른 단지가 다음 구간엔 덜 오르거나 꺾인다",
        method=f"단지+평형 단위, 최근 {months}개월을 3등분해 "
               "1구간→2구간 상승률과 2구간→3구간 상승률의 Spearman 상관 "
               "(양수=모멘텀 지속, 음수=평균회귀)",
        expected_sign=1,
        caveats="recommend.py의 현재 점수 공식은 tier·prestige(구조적 요인) 중심이라 "
                "이 결과가 음수(평균회귀)로 나와도 기존 점수 산식과 직접 모순되는 것은 아님 — "
                "다만 '과거 상승률'을 참고 지표로 표시하는 UI 문구는 재검토 필요.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    end = df["deal_date"].max()
    third = months // 3
    if third < 1:
        return _empty_result(**meta)
    p3 = end
    p2 = end - pd.DateOffset(months=third)
    p1 = end - pd.DateOffset(months=third * 2)
    p0 = end - pd.DateOffset(months=third * 3)

    keys = ["region_code", "apt_name", "area_bucket"]

    def _seg_median(lo, hi, name):
        seg = df[(df["deal_date"] > lo) & (df["deal_date"] <= hi)]
        return seg.groupby(keys).agg(**{
            f"{name}_ppp": ("price_per_pyeong", "median"),
            f"{name}_n": ("price_per_pyeong", "count"),
        })

    s0 = _seg_median(p0, p1, "seg0")
    s1 = _seg_median(p1, p2, "seg1")
    s2 = _seg_median(p2, p3, "seg2")
    g = s0.join(s1, how="inner").join(s2, how="inner").reset_index()
    g = g[(g["seg0_n"] >= min_deals) & (g["seg1_n"] >= min_deals) & (g["seg2_n"] >= min_deals)]
    if g.empty:
        return _empty_result(**meta)

    g["growth_a"] = (g["seg1_ppp"] - g["seg0_ppp"]) / g["seg0_ppp"] * 100
    g["growth_b"] = (g["seg2_ppp"] - g["seg1_ppp"]) / g["seg1_ppp"] * 100
    rho, _ = spearmanr(g["growth_a"], g["growth_b"])
    return HypothesisResult(statistic=float(rho), n=len(g), **meta)


ALL_HYPOTHESES = [
    test_redevelopment_age_effect,
    test_volume_leads_price,
    test_momentum_vs_reversion,
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
    results = [fn() for fn in ALL_HYPOTHESES]
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
