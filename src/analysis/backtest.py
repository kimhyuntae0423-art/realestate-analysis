"""추천 점수 vs 실제 상승률 백테스트.

가설: 호재/상급지/매수심리 등 현재 점수 시그널이 미래 가격 상승을 얼마나 예측하는가?

방식 (out-of-sample):
  - 점수 산정 시점 (as_of): 검증일 - 12개월
  - 점수 입력 데이터: as_of 이전 12개월
  - 정답지: as_of ~ 검증일 (12개월) 평당가 상승률
  - 호재/상급지는 static이라 시점 동일 (한계)

메트릭:
  - Spearman 순위 상관계수
  - Top-N 적중률 (점수 상위 N개 중 실제 상위 M개 포함 비율)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from config.settings import (
    ROOT, DEFAULT_CATALYST_WEIGHT, DEFAULT_TIER_WEIGHT, DEFAULT_PRESTIGE_WEIGHT,
)
from src.database.repository import fetch_trades_df
from src.analysis.recommend import (
    manual_catalyst_score, region_tier_score, _bucketize,
    _apply_gap_scores, _apply_rental_scores, _buyer_sentiment_signals,
)
from src.analysis.forward_signals import (
    apt_relative_strength, jeonse_ratio_acceleration,
    supply_pressure, population_inflow, apt_prestige_score,
    region_market_score,
)


# ── 유틸 ──────────────────────────────────────────────────────────

def _months_ago(d: date, months: int) -> date:
    return d - timedelta(days=30 * months)


def _load_region_map() -> dict[str, str]:
    p = ROOT / "config" / "regions.json"
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    # regions.json 구조: {"11110": "종로구", ...} 또는 nested
    if "regions" in data:
        return data["regions"]
    return data


# ── 시점별 시그널 ──────────────────────────────────────────────────

def _region_price_growth(start: date, mid: date, end: date,
                          min_deals: int = 20) -> pd.DataFrame:
    """시군구별 가격 상승률 [mid~end 중위 평당가 / start~mid 중위 평당가 - 1].

    min_deals: 양쪽 윈도우 모두에서 요구되는 최소 거래수.
    """
    df = fetch_trades_df(date_from=start, date_to=end)
    if df.empty:
        return pd.DataFrame()
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    mid_ts = pd.Timestamp(mid)

    recent = df[df["deal_date"] > mid_ts]
    prior = df[df["deal_date"] <= mid_ts]

    r = recent.groupby("region_code").agg(
        recent_ppp=("price_per_pyeong", "median"),
        recent_deals=("price_per_pyeong", "count"),
    )
    p = prior.groupby("region_code").agg(
        prior_ppp=("price_per_pyeong", "median"),
        prior_deals=("price_per_pyeong", "count"),
    )
    g = r.join(p, how="inner")
    g = g[(g["recent_deals"] >= min_deals) & (g["prior_deals"] >= min_deals)]
    g["growth_%"] = ((g["recent_ppp"] - g["prior_ppp"]) / g["prior_ppp"] * 100).round(2)
    return g.reset_index()


def _region_volume_momentum(start: date, mid: date, end: date) -> pd.DataFrame:
    """시군구별 거래량 모멘텀 (최근/이전 거래수 비율)."""
    df = fetch_trades_df(date_from=start, date_to=end)
    if df.empty:
        return pd.DataFrame()
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    mid_ts = pd.Timestamp(mid)
    recent_n = df[df["deal_date"] > mid_ts].groupby("region_code").size().rename("recent_n")
    prior_n = df[df["deal_date"] <= mid_ts].groupby("region_code").size().rename("prior_n")
    j = pd.concat([recent_n, prior_n], axis=1).fillna(0).reset_index()
    j["vol_momentum"] = (j["recent_n"] / (j["prior_n"] + 1)).round(2)
    return j[["region_code", "vol_momentum"]]


def _apt_price_growth(start: date, mid: date, end: date,
                       area_tol: float = 5.0, min_deals: int = 3) -> pd.DataFrame:
    """단지·평형별 가격 상승률."""
    df = fetch_trades_df(date_from=start, date_to=end)
    if df.empty:
        return pd.DataFrame()
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    mid_ts = pd.Timestamp(mid)
    recent = df[df["deal_date"] > mid_ts]
    prior = df[df["deal_date"] <= mid_ts]
    keys = ["region_code", "apt_name", "area_bucket"]
    r = recent.groupby(keys).agg(
        recent_ppp=("price_per_pyeong", "median"),
        recent_deals=("price_per_pyeong", "count"),
    )
    p = prior.groupby(keys).agg(
        prior_ppp=("price_per_pyeong", "median"),
        prior_deals=("price_per_pyeong", "count"),
    )
    g = r.join(p, how="inner")
    g = g[(g["recent_deals"] >= min_deals) & (g["prior_deals"] >= min_deals)]
    g["growth_%"] = ((g["recent_ppp"] - g["prior_ppp"]) / g["prior_ppp"] * 100).round(2)
    return g.reset_index()


# ── 메트릭 ─────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    scope: str                  # "region" or "apt"
    n: int                      # 표본 수
    spearman: float             # 종합점수 ↔ 실제 상승률
    top10_hit: float            # 점수 Top10 중 실제 Top 20% 포함 비율
    top20_hit: float
    component_corr: dict        # 컴포넌트별 단독 상관
    weights: dict               # 사용한 가중치


def _spearman(s1: pd.Series, s2: pd.Series) -> float:
    """NaN 제거 후 Spearman 상관."""
    df = pd.concat([s1, s2], axis=1).dropna()
    if len(df) < 5:
        return float("nan")
    rho, _ = spearmanr(df.iloc[:, 0], df.iloc[:, 1])
    return float(rho)


def _topn_hit(score: pd.Series, actual: pd.Series, n: int, m_pct: float = 0.2) -> float:
    """점수 상위 N개 중 실제 상위 m_pct에 포함된 비율."""
    df = pd.concat([score.rename("s"), actual.rename("a")], axis=1).dropna()
    if len(df) < n:
        return float("nan")
    top_score = df.nlargest(n, "s").index
    m = max(int(len(df) * m_pct), n)
    top_actual = set(df.nlargest(m, "a").index)
    hits = sum(1 for i in top_score if i in top_actual)
    return hits / n


# ── 시군구 백테스트 ────────────────────────────────────────────────

def region_backtest(
    as_of: date | None = None,
    train_months: int = 12,
    test_months: int = 12,
    min_train_deals: int = 30,
    min_test_deals: int = 30,
    catalyst_weight: float = 0.0,
    tier_weight: float = 0.60,
) -> BacktestResult:
    """시군구 단위 백테스트.

    - 점수 시점: as_of (default: today - test_months)
    - 점수 입력 데이터: as_of - train_months ~ as_of
    - 정답지: as_of ~ as_of + test_months
    """
    today = date.today()
    if as_of is None:
        as_of = _months_ago(today, test_months)

    train_start = _months_ago(as_of, train_months)
    train_mid = _months_ago(as_of, train_months // 2)
    test_end = today  # 보유 데이터 끝까지

    # ── 시그널 ──
    train_growth = _region_price_growth(train_start, train_mid, as_of, min_deals=min_train_deals)
    vol_mom = _region_volume_momentum(_months_ago(as_of, 6), _months_ago(as_of, 3), as_of)

    if train_growth.empty:
        raise ValueError("학습 윈도우 데이터 부족")

    # 시군구 단위 점수 시그널 모음
    g = train_growth[["region_code", "growth_%"]].rename(columns={"growth_%": "train_growth"})
    g = g.merge(vol_mom, on="region_code", how="left")
    g["vol_momentum"] = g["vol_momentum"].fillna(1.0)
    g["catalyst"] = g["region_code"].apply(lambda r: manual_catalyst_score(r))
    g["tier"] = g["region_code"].apply(lambda r: region_tier_score(r))

    # 종합점수 = cw*호재 + tw*상급지 + rest*(가격모멘텀 0.6 + 거래량모멘텀 0.4)
    cw = catalyst_weight
    tw = tier_weight
    rest = max(0.0, 1.0 - cw - tw)
    g["score"] = (
        g["catalyst"].rank(pct=True) * cw
        + g["tier"].rank(pct=True) * tw
        + g["train_growth"].rank(pct=True) * (rest * 0.6)
        + g["vol_momentum"].rank(pct=True) * (rest * 0.4)
    ) * 100

    # ── 정답지: as_of 이후 실제 상승률 ──
    test_mid = as_of + timedelta(days=30 * (test_months // 2))
    test_growth = _region_price_growth(as_of, test_mid, test_end, min_deals=min_test_deals)
    if test_growth.empty:
        raise ValueError("검증 윈도우 데이터 부족")
    g = g.merge(test_growth[["region_code", "growth_%"]].rename(
        columns={"growth_%": "actual_growth"}), on="region_code", how="inner")

    # ── 메트릭 ──
    n = len(g)
    rho = _spearman(g["score"], g["actual_growth"])
    component_corr = {
        "catalyst": _spearman(g["catalyst"], g["actual_growth"]),
        "tier": _spearman(g["tier"], g["actual_growth"]),
        "train_growth": _spearman(g["train_growth"], g["actual_growth"]),
        "vol_momentum": _spearman(g["vol_momentum"], g["actual_growth"]),
    }
    return BacktestResult(
        scope="region", n=n, spearman=rho,
        top10_hit=_topn_hit(g["score"], g["actual_growth"], max(10, n // 10)),
        top20_hit=_topn_hit(g["score"], g["actual_growth"], max(20, n // 5)),
        component_corr=component_corr,
        weights={"catalyst": cw, "tier": tw, "rest": rest},
    )


# ── 단지 백테스트 ─────────────────────────────────────────────────

def _apt_backtest_base(
    as_of: date | None = None,
    train_months: int = 12,
    test_months: int = 12,
    min_deals: int = 3,
    area_tol: float = 5.0,
) -> pd.DataFrame:
    """apt_backtest의 가중치-무관 부분(신호 계산 + 정답지 merge)만 한 번 계산.

    grid_search_apt가 가중치 조합마다 이 무거운 계산을 반복하지 않도록 분리했다
    (2026-07-20). catalyst/tier/market/rs/jeonse_accel/supply_pressure/population/
    prestige/sentiment/train_growth/actual_growth를 전부 포함한 df를 반환하며, region_score와
    score는 가중치에 따라 달라지므로 여기서 계산하지 않는다.
    """
    today = date.today()
    if as_of is None:
        as_of = _months_ago(today, test_months)

    train_start = _months_ago(as_of, train_months)
    train_mid = _months_ago(as_of, train_months // 2)
    test_end = today

    train_growth = _apt_price_growth(train_start, train_mid, as_of,
                                       area_tol=area_tol, min_deals=min_deals)
    if train_growth.empty:
        raise ValueError("학습 윈도우 데이터 부족")

    g = train_growth.rename(columns={"growth_%": "train_growth"})
    g["catalyst"] = g["region_code"].apply(lambda r: manual_catalyst_score(r))
    g["tier"] = g["region_code"].apply(lambda r: region_tier_score(r))
    mkt_df = region_market_score(months=train_months)
    if not mkt_df.empty:
        g = g.merge(mkt_df[["region_code", "market_score"]], on="region_code", how="left")
    g["market_score"] = g.get("market_score", pd.Series(50.0, index=g.index)).fillna(50.0)

    # ── 선행 시그널 (학습 시점 기준) ──
    keys = ["region_code", "apt_name", "area_bucket"]
    rs = apt_relative_strength(as_of=as_of, months=train_months, area_tol=area_tol)
    if not rs.empty:
        g = g.merge(rs[keys + ["rs_score"]], on=keys, how="left")
    g["rs_score"] = g.get("rs_score", pd.Series(50.0, index=g.index)).fillna(50.0)

    jr = jeonse_ratio_acceleration(as_of=as_of, months=train_months, area_tol=area_tol)
    if not jr.empty:
        g = g.merge(jr[keys + ["jeonse_accel_score"]], on=keys, how="left")
    g["jeonse_accel_score"] = g.get("jeonse_accel_score",
        pd.Series(50.0, index=g.index)).fillna(50.0)

    sp = supply_pressure(as_of=as_of)
    if not sp.empty:
        g = g.merge(sp[["region_code", "supply_pressure_score"]],
                    on="region_code", how="left")
    g["supply_pressure_score"] = g.get("supply_pressure_score",
        pd.Series(50.0, index=g.index)).fillna(50.0)

    pop = population_inflow(as_of=as_of)
    if not pop.empty:
        g = g.merge(pop[["region_code", "population_score"]],
                    on="region_code", how="left")
    g["population_score"] = g.get("population_score",
        pd.Series(50.0, index=g.index)).fillna(50.0)

    pres = apt_prestige_score(as_of=as_of, months=train_months, area_tol=area_tol)
    if not pres.empty:
        g = g.merge(pres[keys + ["prestige_score"]], on=keys, how="left")
    g["prestige_score"] = g.get("prestige_score",
        pd.Series(50.0, index=g.index)).fillna(50.0)

    sent = _buyer_sentiment_signals(as_of=as_of, area_tol=area_tol)
    if not sent.empty:
        g = g.merge(sent[keys + ["sentiment_score"]], on=keys, how="left")
    g["sentiment_score"] = g.get("sentiment_score",
        pd.Series(50.0, index=g.index)).fillna(50.0)

    test_mid = as_of + timedelta(days=30 * (test_months // 2))
    test_growth = _apt_price_growth(as_of, test_mid, test_end,
                                     area_tol=area_tol, min_deals=min_deals)
    if test_growth.empty:
        raise ValueError("검증 윈도우 데이터 부족")
    test_growth = test_growth.rename(columns={"growth_%": "actual_growth"})
    g = g.merge(test_growth[keys + ["actual_growth"]], on=keys, how="inner")
    return g


def _apt_backtest_score(
    g: pd.DataFrame,
    catalyst_weight: float = DEFAULT_CATALYST_WEIGHT,
    tier_weight: float = DEFAULT_TIER_WEIGHT,
    prestige_weight: float = DEFAULT_PRESTIGE_WEIGHT,
) -> BacktestResult:
    """_apt_backtest_base() 결과에 가중치를 적용해 점수·지표만 (재)계산 — 값싼 연산.

    recommend.py::recommend_investment_focus()의 실제(2026-05 단순화) 공식과 동일:
    region_score(=market_score 단독 + 호재 가산, tier는 안 섞음) × tw
    + prestige_score × pw, tw/pw는 합이 1이 되게 정규화.
    rs_score·jeonse_accel·supply_pressure·population·train_growth는 점수 산식에서
    제외됨(ρ 약하거나 역상관) — component_corr 진단용으로만 유지.
    """
    cw_amp = max(0.0, min(1.0, catalyst_weight))
    region_score = (g["market_score"] + g["catalyst"] * cw_amp).clip(upper=100)

    tw = max(0.0, min(1.0, tier_weight))
    pw = max(0.0, min(1.0, prestige_weight))
    if tw + pw <= 0:
        tw, pw = 0.7, 0.3
    total = tw + pw
    score = (
        region_score.rank(pct=True) * (tw / total)
        + g["prestige_score"].rank(pct=True) * (pw / total)
    ) * 100

    n = len(g)
    rho = _spearman(score, g["actual_growth"])
    component_corr = {
        "catalyst": _spearman(g["catalyst"], g["actual_growth"]),
        "tier": _spearman(g["tier"], g["actual_growth"]),
        "market": _spearman(g["market_score"], g["actual_growth"]),
        "region_score": _spearman(region_score, g["actual_growth"]),
        "prestige": _spearman(g["prestige_score"], g["actual_growth"]),
        "train_growth": _spearman(g["train_growth"], g["actual_growth"]),
        "rs_score": _spearman(g["rs_score"], g["actual_growth"]),
        "jeonse_accel": _spearman(g["jeonse_accel_score"], g["actual_growth"]),
        "supply_pressure": _spearman(g["supply_pressure_score"], g["actual_growth"]),
        "population": _spearman(g["population_score"], g["actual_growth"]),
        "sentiment": _spearman(g["sentiment_score"], g["actual_growth"]),
    }
    return BacktestResult(
        scope="apt", n=n, spearman=rho,
        top10_hit=_topn_hit(score, g["actual_growth"], max(10, n // 10)),
        top20_hit=_topn_hit(score, g["actual_growth"], max(20, n // 5)),
        component_corr=component_corr,
        weights={"catalyst_boost": catalyst_weight,
                 "region_score": round(tw / total, 3), "prestige": round(pw / total, 3)},
    )


def apt_backtest(
    as_of: date | None = None,
    train_months: int = 12,
    test_months: int = 12,
    min_deals: int = 3,
    catalyst_weight: float = DEFAULT_CATALYST_WEIGHT,
    tier_weight: float = DEFAULT_TIER_WEIGHT,
    prestige_weight: float = DEFAULT_PRESTIGE_WEIGHT,
    area_tol: float = 5.0,
) -> BacktestResult:
    g = _apt_backtest_base(as_of, train_months, test_months, min_deals, area_tol)
    return _apt_backtest_score(g, catalyst_weight, tier_weight, prestige_weight)


# ── 가중치 그리드 서치 ─────────────────────────────────────────────

def grid_search_region(
    cw_grid: Iterable[float] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
    tw_grid: Iterable[float] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
    **kwargs,
) -> pd.DataFrame:
    rows = []
    for cw in cw_grid:
        for tw in tw_grid:
            if cw + tw > 1.0:
                continue
            try:
                r = region_backtest(catalyst_weight=cw, tier_weight=tw, **kwargs)
            except ValueError:
                continue
            rows.append({
                "catalyst_w": cw, "tier_w": tw, "rest_w": round(1 - cw - tw, 2),
                "n": r.n, "spearman": round(r.spearman, 3),
                "top10_hit": round(r.top10_hit, 3),
                "top20_hit": round(r.top20_hit, 3),
            })
    return pd.DataFrame(rows).sort_values("spearman", ascending=False).reset_index(drop=True)


def grid_search_apt(
    cw_grid: Iterable[float] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
    tw_grid: Iterable[float] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
    pw_grid: Iterable[float] = (0.1, 0.2, 0.3, 0.4, 0.5),
    **kwargs,
) -> pd.DataFrame:
    """apt_backtest 가중치 그리드 서치.

    apt_backtest의 실제 점수식은 region_score×(tw/(tw+pw)) + prestige_score×(pw/(tw+pw))
    로 정규화되므로 (region_backtest와 달리) cw+tw+pw가 1을 넘어도 무방하다 — "rest"
    개념 자체가 없다(2026-07-20 apt_backtest 죽은 공식 제거 때 같이 정리).

    가중치와 무관한 무거운 신호 계산(_apt_backtest_base)은 그리드 전체에서 딱 한 번만
    돌리고, 조합마다는 값싼 재가중치(_apt_backtest_score)만 반복한다 — 245개 조합을
    245번 처음부터 계산하면 수 시간 걸리던 것을 몇 분으로 단축(2026-07-20).
    """
    base = _apt_backtest_base(**kwargs)
    rows = []
    for cw in cw_grid:
        for tw in tw_grid:
            for pw in pw_grid:
                if tw + pw <= 0:
                    continue
                r = _apt_backtest_score(base, catalyst_weight=cw,
                                         tier_weight=tw, prestige_weight=pw)
                rows.append({
                    "catalyst_w": cw, "region_score_w_norm": round(tw / (tw + pw), 2),
                    "prestige_w_norm": round(pw / (tw + pw), 2),
                    "n": r.n, "spearman": round(r.spearman, 3),
                    "top10_hit": round(r.top10_hit, 3),
                    "top20_hit": round(r.top20_hit, 3),
                })
    return pd.DataFrame(rows).sort_values("spearman", ascending=False).reset_index(drop=True)
