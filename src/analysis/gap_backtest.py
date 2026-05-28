"""갭투자 전용 백테스트 모듈.

4가지 방법론:
  A. gap_score_backtest       — 갭투자 5요소 점수 vs 실제 매매가 상승률 (Spearman ρ)
  B. jeonse_risk_backtest     — 역전세 리스크 레이블 분류 정확도 (Precision/Recall/F1)
  C. gap_simulation_backtest  — 과거 TOP-N 갭투자 시뮬레이션 (자기자본 수익률)
  D. gap_walk_forward         — 여러 시점 반복 (신뢰도·안정성 측정)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.database.repository import fetch_trades_df, fetch_rents_df
from src.analysis.gap_analysis import to_jeonse_equiv
from src.analysis.backtest import (
    _bucketize, _spearman, _topn_hit, _apt_price_growth, _months_ago,
    region_tier_score, _apply_gap_scores, _apply_rental_scores,
)
from src.analysis.forward_signals import jeonse_ratio_acceleration, region_market_score


# ── 갭투자 스코어링 헬퍼 (recommend.py 의존 제거) ─────────────────────

def _jeonse_quality_score(ratio: float) -> float:
    """전세가율(%) → 갭투자 적정구간 점수 (0~100, 역U자형). 65~78%가 최적."""
    if ratio < 50:
        return ratio
    elif ratio <= 65:
        return 50.0 + (ratio - 50) * (50.0 / 15)
    elif ratio <= 78:
        return 100.0
    elif ratio <= 87:
        return 100.0 - (ratio - 78) * (50.0 / 9)
    elif ratio <= 93:
        return 50.0 - (ratio - 87) * (40.0 / 6)
    else:
        return max(0.0, 10.0 - (ratio - 93) * 2)


def _jeonse_risk_label(ratio: float, accel: float = 0.0) -> str:
    """전세가율 + 추세로 역전세 리스크 레벨 산출."""
    if ratio >= 90:
        return "⚠️ 역전세위험"
    elif ratio >= 83 or (ratio >= 78 and accel < -2):
        return "🔶 주의"
    elif ratio >= 65:
        return "✅ 적정"
    else:
        return "🟢 갭여유"


# ── 결과 데이터클래스 ──────────────────────────────────────────────

@dataclass
class GapScoreResult:
    """Method A: 갭투자 점수 vs 실제 매매가 상승률."""
    as_of: date
    train_months: int
    test_months: int
    n: int
    spearman: float           # 종합 점수 ↔ 실제 상승률 Spearman ρ
    top10_hit: float          # 점수 Top10 중 실제 상위 20% 포함 비율
    top20_hit: float
    component_corr: dict      # 요소별 단독 ρ
    raw: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)


@dataclass
class RiskClassResult:
    """Method B: 역전세 리스크 레이블 분류 정확도."""
    as_of: date
    test_months: int
    n: int
    n_actual_risk: int        # 실제 역전세 발생 건수
    precision: float
    recall: float
    f1: float
    confusion: dict           # TP/FP/FN/TN
    fall_threshold_pct: float
    raw: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)


@dataclass
class GapSimResult:
    """Method C: 과거 시점 TOP-N 갭투자 수익 시뮬레이션."""
    as_of: date
    hold_months: int
    top_n: int
    n_matched: int
    avg_price_growth_pct: float    # 평균 매매가 상승률
    avg_gap_change_pct: float      # 평균 갭 변화율 (음수 = 갭 감소 = 유리)
    avg_roe_pct: float             # 평균 자기자본 수익률 = 매매가상승 / 초기갭
    median_roe_pct: float
    raw: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)


@dataclass
class WalkForwardResult:
    """Method D: 여러 시점 반복 결과."""
    method: str
    n_windows: int
    windows: list[dict]
    avg_spearman: float | None = None   # A용
    std_spearman: float | None = None
    avg_f1: float | None = None         # B용
    std_f1: float | None = None
    avg_roe_pct: float | None = None    # C용
    std_roe_pct: float | None = None
    summary: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)


# ── 내부 유틸 ──────────────────────────────────────────────────────

def _gap_scores_at(as_of: date, train_months: int,
                   area_tol: float = 5.0, min_deals: int = 3) -> pd.DataFrame:
    """as_of 시점 기준 갭투자 5요소 점수 산출 (point-in-time)."""
    train_start = _months_ago(as_of, train_months)
    df_t = fetch_trades_df(date_from=train_start, date_to=as_of)
    df_r = fetch_rents_df(date_from=train_start, date_to=as_of)
    if df_t.empty or df_r.empty:
        return pd.DataFrame()

    df_t = _bucketize(df_t, area_tol)
    df_r = to_jeonse_equiv(_bucketize(df_r, area_tol))
    keys = ["region_code", "apt_name", "area_bucket"]

    t_agg = df_t.groupby(keys).agg(
        trade_median=("deal_amount", "median"),
        trade_count=("deal_amount", "count"),
    ).reset_index()
    r_agg = df_r.groupby(keys).agg(
        rent_median=("jeonse_equiv", "median"),
        rent_count=("jeonse_equiv", "count"),
    ).reset_index()

    g = t_agg.merge(r_agg, on=keys, how="inner")
    g = g[(g["trade_count"] >= min_deals) & (g["rent_count"] >= min_deals)].copy()
    if g.empty:
        return g

    g["gap"] = g["trade_median"] - g["rent_median"]
    g["jeonse_ratio"] = (g["rent_median"] / g["trade_median"] * 100).round(2)
    g = g[g["gap"] > 0].copy()
    if g.empty:
        return g

    g["activity"] = g["trade_count"] + g["rent_count"]
    g["jeonse_quality_score"] = g["jeonse_ratio"].apply(_jeonse_quality_score)
    g["tier_score"] = g["region_code"].apply(region_tier_score)

    # recommend.py의 _apply_gap_scores와 동일 수식 — 수식 변경은 recommend.py 한 곳만 수정
    jr = jeonse_ratio_acceleration(as_of=as_of, months=train_months, area_tol=area_tol)
    mkt_df = region_market_score(months=train_months)
    g = _apply_gap_scores(g, jeonse_accel_df=jr, mkt_df=mkt_df)

    g["jeonse_risk"] = g.apply(
        lambda r: _jeonse_risk_label(r["jeonse_ratio"], r["jeonse_accel_%p"]), axis=1
    )

    return g


def _jeonse_ratio_at(as_of: date, months: int,
                     area_tol: float, min_deals: int) -> pd.DataFrame:
    """as_of 시점 기준 단지별 전세가율 산출."""
    start = _months_ago(as_of, months)
    df_t = fetch_trades_df(date_from=start, date_to=as_of)
    df_r = fetch_rents_df(date_from=start, date_to=as_of)
    if df_t.empty or df_r.empty:
        return pd.DataFrame()

    df_t = _bucketize(df_t, area_tol)
    df_r = to_jeonse_equiv(_bucketize(df_r, area_tol))
    keys = ["region_code", "apt_name", "area_bucket"]

    t = df_t.groupby(keys).agg(
        trade_med=("deal_amount", "median"),
        t_n=("deal_amount", "count"),
    ).reset_index()
    r = df_r.groupby(keys).agg(
        rent_med=("jeonse_equiv", "median"),
        r_n=("jeonse_equiv", "count"),
    ).reset_index()

    j = t.merge(r, on=keys, how="inner")
    j = j[(j["t_n"] >= min_deals) & (j["r_n"] >= min_deals)].copy()
    if j.empty:
        return j
    j["jeonse_ratio"] = (j["rent_med"] / j["trade_med"] * 100).round(2)
    return j[keys + ["trade_med", "jeonse_ratio"]]


# ── A. 점수-수익률 상관관계 ────────────────────────────────────────

def gap_score_backtest(
    as_of: date | None = None,
    train_months: int = 12,
    test_months: int = 12,
    area_tol: float = 5.0,
    min_deals: int = 3,
) -> GapScoreResult:
    """갭투자 5요소 점수 vs 실제 매매가 상승률 Spearman ρ.

    점수 산정: as_of 이전 train_months 데이터
    정답지: as_of ~ as_of+test_months 평당가 상승률
    """
    today = date.today()
    if as_of is None:
        as_of = _months_ago(today, test_months)

    g = _gap_scores_at(as_of, train_months, area_tol, min_deals)
    if g.empty:
        raise ValueError(f"[A] {as_of} 학습 데이터 부족")

    keys = ["region_code", "apt_name", "area_bucket"]
    test_end = min(today, as_of + timedelta(days=30 * test_months))
    test_mid = as_of + timedelta(days=30 * (test_months // 2))
    actual = _apt_price_growth(as_of, test_mid, test_end, area_tol=area_tol, min_deals=min_deals)
    if actual.empty:
        raise ValueError(f"[A] {as_of} 검증 데이터 부족")

    actual = actual.rename(columns={"growth_%": "actual_growth"})
    g = g.merge(actual[keys + ["actual_growth"]], on=keys, how="inner")
    if len(g) < 5:
        raise ValueError(f"[A] 매칭 데이터 부족: {len(g)}건")

    n = len(g)
    rho = _spearman(g["score"], g["actual_growth"])
    component_corr = {
        "jeonse_quality": round(_spearman(g["jeonse_quality_score"], g["actual_growth"]), 3),
        "jeonse_accel":   round(_spearman(g["jeonse_accel_score"],   g["actual_growth"]), 3),
        "tier":           round(_spearman(g["tier_score"],           g["actual_growth"]), 3),
        "leverage_mult":  round(_spearman(g["leverage_mult"],        g["actual_growth"]), 3),
        "activity":       round(_spearman(g["activity"],             g["actual_growth"]), 3),
        "jeonse_ratio":   round(_spearman(g["jeonse_ratio"],         g["actual_growth"]), 3),
    }
    return GapScoreResult(
        as_of=as_of,
        train_months=train_months,
        test_months=test_months,
        n=n,
        spearman=round(float(rho), 3),
        top10_hit=round(_topn_hit(g["score"], g["actual_growth"], max(10, n // 10)), 3),
        top20_hit=round(_topn_hit(g["score"], g["actual_growth"], max(20, n // 5)), 3),
        component_corr=component_corr,
        raw=g,
    )


# ── B. 역전세 리스크 분류 정확도 ──────────────────────────────────

def jeonse_risk_backtest(
    as_of: date | None = None,
    train_months: int = 6,
    test_months: int = 12,
    area_tol: float = 5.0,
    min_deals: int = 3,
    fall_threshold_pct: float = 3.0,
) -> RiskClassResult:
    """역전세 리스크 레이블의 실제 예측력 검증.

    예측: as_of 시점 jeonse_risk 레이블 (⚠️/🔶 = 위험, ✅/🟢 = 안전)
    정답: test_months 후 전세가율이 fall_threshold_pct(%p) 이상 하락했는지
    """
    today = date.today()
    if as_of is None:
        as_of = _months_ago(today, test_months)

    g = _gap_scores_at(as_of, train_months, area_tol, min_deals)
    if g.empty:
        raise ValueError(f"[B] {as_of} 학습 데이터 부족")

    # 예측 레이블 (이진)
    g["predicted_risk"] = g["jeonse_risk"].isin(["⚠️ 역전세위험", "🔶 주의"]).astype(int)

    # 실제 test_months 후 전세가율
    keys = ["region_code", "apt_name", "area_bucket"]
    test_end = min(today, as_of + timedelta(days=30 * test_months))
    future_ratio = _jeonse_ratio_at(test_end, train_months, area_tol, min_deals)
    if future_ratio.empty:
        raise ValueError(f"[B] {as_of} 미래 데이터 부족")

    future_ratio = future_ratio.rename(columns={"jeonse_ratio": "future_ratio"})
    g = g.merge(future_ratio[keys + ["future_ratio"]], on=keys, how="inner")
    if len(g) < 5:
        raise ValueError(f"[B] 매칭 데이터 부족: {len(g)}건")

    g["ratio_change"] = g["future_ratio"] - g["jeonse_ratio"]  # 음수 = 전세가율 하락
    g["actual_risk"] = (g["ratio_change"] <= -fall_threshold_pct).astype(int)

    tp = int(((g["predicted_risk"] == 1) & (g["actual_risk"] == 1)).sum())
    fp = int(((g["predicted_risk"] == 1) & (g["actual_risk"] == 0)).sum())
    fn = int(((g["predicted_risk"] == 0) & (g["actual_risk"] == 1)).sum())
    tn = int(((g["predicted_risk"] == 0) & (g["actual_risk"] == 0)).sum())

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return RiskClassResult(
        as_of=as_of,
        test_months=test_months,
        n=len(g),
        n_actual_risk=int(g["actual_risk"].sum()),
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(f1, 3),
        confusion={"TP": tp, "FP": fp, "FN": fn, "TN": tn},
        fall_threshold_pct=fall_threshold_pct,
        raw=g,
    )


# ── C. 갭 변화 수익 시뮬레이션 ────────────────────────────────────

def gap_simulation_backtest(
    as_of: date | None = None,
    train_months: int = 12,
    hold_months: int = 12,
    top_n: int = 20,
    area_tol: float = 5.0,
    min_deals: int = 3,
    max_gap_man: int | None = None,
) -> GapSimResult:
    """과거 시점 갭투자 TOP-N 선정 후 hold_months 동안 실제 수익 시뮬레이션.

    ROE = (hold_months 후 매매가 - 초기 매매가) / 초기 갭 × 100
    갭이 작을수록 레버리지 효과가 커서 ROE가 높아짐.
    """
    today = date.today()
    if as_of is None:
        as_of = _months_ago(today, hold_months)

    g = _gap_scores_at(as_of, train_months, area_tol, min_deals)
    if g.empty:
        raise ValueError(f"[C] {as_of} 점수 산출 데이터 부족")

    if max_gap_man:
        g = g[g["gap"] <= max_gap_man]
    if g.empty:
        raise ValueError(f"[C] max_gap 조건 후 데이터 없음")

    # 점수 상위 TOP-N 선택
    top = g.nlargest(top_n, "score").copy()

    # hold_months 후 매매가 측정
    end_date = min(today, as_of + timedelta(days=30 * hold_months))
    future_t = fetch_trades_df(
        date_from=as_of + timedelta(days=30 * (hold_months // 2)),
        date_to=end_date,
    )
    if future_t.empty:
        raise ValueError(f"[C] {as_of} 미래 매매 데이터 부족")

    future_t = _bucketize(future_t, area_tol)
    keys = ["region_code", "apt_name", "area_bucket"]
    f_agg = future_t.groupby(keys).agg(
        future_trade=("deal_amount", "median"),
        future_count=("deal_amount", "count"),
    ).reset_index()
    f_agg = f_agg[f_agg["future_count"] >= min_deals]

    sim = top.merge(f_agg, on=keys, how="inner")
    if sim.empty:
        raise ValueError(f"[C] 미래 데이터 매칭 실패")

    sim["price_growth_%"] = ((sim["future_trade"] - sim["trade_median"])
                              / sim["trade_median"] * 100).round(2)
    sim["gap_future"] = sim["future_trade"] - sim["rent_median"]  # 미래 전세는 고정으로 추정
    sim["gap_change_%"] = ((sim["gap_future"] - sim["gap"]) / sim["gap"] * 100).round(2)
    sim["roe_%"] = ((sim["future_trade"] - sim["trade_median"]) / sim["gap"] * 100).round(2)

    return GapSimResult(
        as_of=as_of,
        hold_months=hold_months,
        top_n=top_n,
        n_matched=len(sim),
        avg_price_growth_pct=round(float(sim["price_growth_%"].mean()), 2),
        avg_gap_change_pct=round(float(sim["gap_change_%"].mean()), 2),
        avg_roe_pct=round(float(sim["roe_%"].mean()), 2),
        median_roe_pct=round(float(sim["roe_%"].median()), 2),
        raw=sim,
    )


# ── D. Walk-forward ───────────────────────────────────────────────

def gap_walk_forward(
    n_windows: int = 4,
    test_months: int = 12,
    train_months: int = 12,
    window_gap_months: int = 6,
    method: str = "score",
    area_tol: float = 5.0,
    min_deals: int = 3,
    **kwargs,
) -> WalkForwardResult:
    """여러 시점에서 갭투자 백테스트를 반복해 안정성·신뢰도 측정.

    method: "score" (A), "risk" (B), "simulation" (C)
    시점 간격: window_gap_months개월씩 앞으로 이동
    """
    today = date.today()
    windows = []

    for i in range(n_windows):
        # 가장 최근 → 가장 과거 순으로 시점 생성
        offset = test_months + i * window_gap_months
        as_of_i = _months_ago(today, offset)

        try:
            if method == "score":
                r = gap_score_backtest(as_of=as_of_i,
                                       train_months=train_months,
                                       test_months=test_months,
                                       area_tol=area_tol, min_deals=min_deals)
                windows.append({
                    "as_of": as_of_i, "n": r.n,
                    "spearman": r.spearman,
                    "top10_hit": r.top10_hit,
                    "top20_hit": r.top20_hit,
                })

            elif method == "risk":
                fall_thr = kwargs.get("fall_threshold_pct", 3.0)
                r = jeonse_risk_backtest(as_of=as_of_i,
                                         train_months=train_months,
                                         test_months=test_months,
                                         area_tol=area_tol, min_deals=min_deals,
                                         fall_threshold_pct=fall_thr)
                windows.append({
                    "as_of": as_of_i, "n": r.n,
                    "n_actual_risk": r.n_actual_risk,
                    "precision": r.precision,
                    "recall": r.recall,
                    "f1": r.f1,
                })

            elif method == "simulation":
                top_n = kwargs.get("top_n", 20)
                r = gap_simulation_backtest(as_of=as_of_i,
                                             train_months=train_months,
                                             hold_months=test_months,
                                             top_n=top_n,
                                             area_tol=area_tol, min_deals=min_deals)
                windows.append({
                    "as_of": as_of_i,
                    "n_matched": r.n_matched,
                    "avg_price_growth_%": r.avg_price_growth_pct,
                    "avg_gap_change_%": r.avg_gap_change_pct,
                    "avg_roe_%": r.avg_roe_pct,
                    "median_roe_%": r.median_roe_pct,
                })

        except (ValueError, Exception) as e:
            windows.append({"as_of": as_of_i, "error": str(e)})

    summary = pd.DataFrame(windows)

    result = WalkForwardResult(method=method, n_windows=n_windows, windows=windows, summary=summary)

    valid = [w for w in windows if "error" not in w]
    if valid:
        if method == "score":
            vals = [w["spearman"] for w in valid if not np.isnan(w["spearman"])]
            if vals:
                result.avg_spearman = round(float(np.mean(vals)), 3)
                result.std_spearman = round(float(np.std(vals)), 3)
        elif method == "risk":
            vals = [w["f1"] for w in valid]
            if vals:
                result.avg_f1 = round(float(np.mean(vals)), 3)
                result.std_f1 = round(float(np.std(vals)), 3)
        elif method == "simulation":
            vals = [w["avg_roe_%"] for w in valid]
            if vals:
                result.avg_roe_pct = round(float(np.mean(vals)), 2)
                result.std_roe_pct = round(float(np.std(vals)), 2)

    return result


# ── E. 임대수익 전략 백테스트 ──────────────────────────────────────

def rental_yield_backtest(
    as_of: date | None = None,
    train_months: int = 12,
    test_months: int = 12,
    area_tol: float = 5.0,
    min_deals: int = 3,
) -> GapScoreResult:
    """임대수익 전략: annual_yield_% vs 실제 매매가 상승률 Spearman ρ.

    수익률 높은 곳(저가 매물)이 가격 상승률과 역상관인지 검증.
    점수 산정: as_of 이전 train_months 월세 데이터
    정답지: as_of ~ as_of+test_months 평당가 상승률
    """
    today = date.today()
    if as_of is None:
        as_of = _months_ago(today, test_months)

    train_start = _months_ago(as_of, train_months)
    df_t = fetch_trades_df(date_from=train_start, date_to=as_of)
    df_r = fetch_rents_df(date_from=train_start, date_to=as_of)
    if df_t.empty or df_r.empty:
        raise ValueError(f"[임대] {as_of} 학습 데이터 부족")

    # 월세 거래만 (deposit+monthly_rent 구조)
    df_r_monthly = df_r[df_r["monthly_rent"] > 0].copy()
    if df_r_monthly.empty:
        raise ValueError(f"[임대] {as_of} 월세 데이터 없음 (월세 거래 0건)")

    df_t = _bucketize(df_t, area_tol)
    df_r_monthly = _bucketize(df_r_monthly, area_tol)
    keys = ["region_code", "apt_name", "area_bucket"]

    t_agg = df_t.groupby(keys).agg(
        trade_median=("deal_amount", "median"),
        trade_count=("deal_amount", "count"),
    ).reset_index()
    r_agg = df_r_monthly.groupby(keys).agg(
        deposit_median=("deposit", "median"),
        monthly_median=("monthly_rent", "median"),
        rent_count=("monthly_rent", "count"),
    ).reset_index()

    g = t_agg.merge(r_agg, on=keys, how="inner")
    g = g[(g["trade_count"] >= min_deals) & (g["rent_count"] >= min_deals)].copy()
    if g.empty:
        raise ValueError(f"[임대] {as_of} 거래수 필터 후 데이터 없음 (min={min_deals})")

    g["invest"] = g["trade_median"] - g["deposit_median"]
    g = g[g["invest"] > 0].copy()
    g["annual_yield_%"] = (g["monthly_median"] * 12 / g["invest"] * 100).round(2)
    g["tier_score"] = g["region_code"].apply(region_tier_score)

    if len(g) < 5:
        raise ValueError(f"[임대] {as_of} 유효 수익률 데이터 부족: {len(g)}건")

    # recommend.py의 _apply_rental_scores와 동일 수식
    mkt_df = region_market_score(months=train_months)
    g = _apply_rental_scores(g, mkt_df=mkt_df)

    test_end = min(today, as_of + timedelta(days=30 * test_months))
    test_mid = as_of + timedelta(days=30 * (test_months // 2))
    actual = _apt_price_growth(as_of, test_mid, test_end, area_tol=area_tol, min_deals=min_deals)
    if actual.empty:
        raise ValueError(f"[임대] {as_of} 검증 데이터 부족")

    actual = actual.rename(columns={"growth_%": "actual_growth"})
    g = g.merge(actual[keys + ["actual_growth"]], on=keys, how="inner")
    if len(g) < 5:
        raise ValueError(f"[임대] 매칭 데이터 부족: {len(g)}건")

    n = len(g)
    rho = _spearman(g["score"], g["actual_growth"])
    component_corr = {
        "annual_yield_%":     round(float(_spearman(g["annual_yield_%"],     g["actual_growth"])), 3),
        "appreciation_score": round(float(_spearman(g["appreciation_score"], g["actual_growth"])), 3),
        "tier_score":         round(float(_spearman(g["tier_score"],         g["actual_growth"])), 3),
        "market_score":       round(float(_spearman(g["market_score"],       g["actual_growth"])), 3),
        "trade_median":       round(float(_spearman(g["trade_median"],       g["actual_growth"])), 3),
        "monthly_median":     round(float(_spearman(g["monthly_median"],     g["actual_growth"])), 3),
    }

    return GapScoreResult(
        as_of=as_of,
        train_months=train_months,
        test_months=test_months,
        n=n,
        spearman=round(float(rho), 3),
        top10_hit=round(_topn_hit(g["score"], g["actual_growth"], max(10, n // 10)), 3),
        top20_hit=round(_topn_hit(g["score"], g["actual_growth"], max(20, n // 5)), 3),
        component_corr=component_corr,
        raw=g,
    )
