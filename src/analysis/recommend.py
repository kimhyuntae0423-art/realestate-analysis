"""시드(가용자금) 기반 투자 추천

전략:
1. gap_investment     - 갭투자: 매매-전세=갭, 전세 끼고 매수 (대출 X)
2. rental_yield       - 임대수익: 보증금+대출+자기자본, 월세로 캐시플로우
3. buy_outright       - 자가매입: 시드+대출로 매수, 실거주 또는 단순 보유
4. investment_focus   - 🚀 투자수익: 호재 점수 + 매수세 모멘텀 + 레버리지 = 미래 상승 노림수

모든 금액 단위는 '만원' (DB 원본 단위).
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
import pandas as pd

from config.settings import ROOT
from src.database.repository import fetch_trades_df, fetch_rents_df
from src.analysis.gap_analysis import to_jeonse_equiv
from src.analysis.loan import get_ltv_pct, get_zone, vectorized_loan_equity
from src.analysis.forward_signals import (
    apt_relative_strength, jeonse_ratio_acceleration,
    supply_pressure, population_inflow, apt_prestige_score,
    region_market_score,
)


# ─── 호재(catalyst) 점수 시스템 ─────────────────────────────────────
@lru_cache(maxsize=1)
def _load_catalysts() -> dict:
    p = ROOT / "config" / "catalysts.json"
    if not p.exists():
        return {"region_catalysts": {}, "apt_catalysts": []}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def manual_catalyst_score(region_code: str, apt_name: str = "") -> float:
    """수동 등록된 호재의 총합 점수 (0~100)."""
    cat = _load_catalysts()
    score = 0.0
    for c in cat.get("region_catalysts", {}).get(region_code, []):
        score += float(c.get("score", 0))
    for c in cat.get("apt_catalysts", []):
        if c.get("region_code") == region_code and apt_name and c.get("apt_name", "") in apt_name:
            score += float(c.get("score", 0))
    return min(score, 100.0)


def manual_catalyst_text(region_code: str) -> str:
    """등록된 호재 텍스트 요약 (UI 표시용)."""
    cat = _load_catalysts()
    items = cat.get("region_catalysts", {}).get(region_code, [])
    if not items:
        return ""
    return " / ".join(f"[{c.get('type','?')}] {c.get('name','')}" for c in items)


# ─── 상급지 등급 시스템 (2022~23 규제지역 해제 순서 기반) ────────────
@lru_cache(maxsize=1)
def _load_region_tiers() -> dict:
    p = ROOT / "config" / "region_tiers.json"
    if not p.exists():
        return {"tiers": {}, "region_tier": {}, "default_tier": "",
                "default_score_when_missing": 30}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def region_tier_label(region_code: str) -> str:
    """지역의 등급 라벨 (예: '1_최상급지'). 미등록 지역은 default_tier."""
    cfg = _load_region_tiers()
    return cfg.get("region_tier", {}).get(region_code, cfg.get("default_tier", ""))


def region_tier_score(region_code: str) -> float:
    """지역의 등급 점수 (0~100). 늦게 규제 풀린 곳일수록 높음.

    미등록 지역은 default_score_when_missing (기본 30점).
    """
    cfg = _load_region_tiers()
    label = cfg.get("region_tier", {}).get(region_code)
    if label is None:
        return float(cfg.get("default_score_when_missing", 30))
    return float(cfg.get("tiers", {}).get(label, {}).get("score", 30))


def _volume_momentum_signals(months: int, area_tol: float = 5.0) -> pd.DataFrame:
    """최근 3개월 거래수 / 이전 3개월 거래수 비율 (지역·단지·평형 단위)."""
    now = date.today()
    cut_recent = now - timedelta(days=90)
    cut_prior = now - timedelta(days=180)

    df = fetch_trades_df(date_from=cut_prior)
    if df.empty:
        return pd.DataFrame()
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    cut_recent_ts = pd.Timestamp(cut_recent)

    recent = df[df["deal_date"] > cut_recent_ts]
    prior = df[df["deal_date"] <= cut_recent_ts]

    r = recent.groupby(["region_code", "apt_name", "area_bucket"]).size().rename("recent_n")
    p = prior.groupby(["region_code", "apt_name", "area_bucket"]).size().rename("prior_n")
    j = pd.concat([r, p], axis=1).fillna(0).reset_index()
    j["volume_momentum"] = (j["recent_n"] / (j["prior_n"] + 1)).round(2)
    return j[["region_code", "apt_name", "area_bucket", "volume_momentum",
              "recent_n", "prior_n"]]


# ─── 매수심리 지표 (KB 매수우위지수 proxy) ────────────────────────────
def _buyer_sentiment_signals(area_tol: float = 5.0) -> pd.DataFrame:
    """단지·평형별 매수심리 지표.

    구성요소:
    - volume_momentum: 거래량 모멘텀 (최근 3mo / 이전 3mo)
    - price_acceleration: 가격 가속도 (최근 3mo 변화율 - 이전 3mo 변화율)
    - mean_median_skew: 평균-중위 격차 (고가 매수 비중 신호, %)

    100점 만점 종합 sentiment_score 산출.
    """
    now = date.today()
    cut_t1 = now - timedelta(days=90)   # 최근 3mo 시작
    cut_t2 = now - timedelta(days=180)  # 이전 3mo 시작
    cut_t3 = now - timedelta(days=270)  # 그 이전 3mo 시작

    df = fetch_trades_df(date_from=cut_t3)
    if df.empty:
        return pd.DataFrame()
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    t1 = pd.Timestamp(cut_t1)
    t2 = pd.Timestamp(cut_t2)

    p1 = df[df["deal_date"] > t1]                                 # 최근 3mo
    p2 = df[(df["deal_date"] > t2) & (df["deal_date"] <= t1)]     # 그 전 3mo
    p3 = df[(df["deal_date"] <= t2)]                              # 그 이전 3mo

    g1 = p1.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        n_recent=("deal_amount", "count"),
        ppp_recent=("price_per_pyeong", "median"),
        mean_recent=("deal_amount", "mean"),
        median_recent=("deal_amount", "median"),
    )
    g2 = p2.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        n_mid=("deal_amount", "count"),
        ppp_mid=("price_per_pyeong", "median"),
    )
    g3 = p3.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        n_old=("deal_amount", "count"),
        ppp_old=("price_per_pyeong", "median"),
    )
    j = g1.join(g2, how="left").join(g3, how="left").reset_index()
    if j.empty:
        return j

    j["n_mid"] = j["n_mid"].fillna(0)
    j["n_old"] = j["n_old"].fillna(0)

    # 1) 거래량 모멘텀: 최근 / (이전 평균 + 1)
    j["volume_momentum"] = (j["n_recent"] / ((j["n_mid"] + j["n_old"]) / 2 + 1)).round(2)

    # 2) 가격 가속도 = 최근 변화율 - 이전 변화율
    j["recent_change_%"] = ((j["ppp_recent"] - j["ppp_mid"]) / j["ppp_mid"] * 100)
    j["prior_change_%"] = ((j["ppp_mid"] - j["ppp_old"]) / j["ppp_old"] * 100)
    j["price_acceleration_%"] = (j["recent_change_%"] - j["prior_change_%"]).round(2)

    # 3) 평균-중위 격차 (고가매수 비중 신호)
    j["mean_median_skew_%"] = ((j["mean_recent"] - j["median_recent"]) / j["median_recent"] * 100).round(2)

    # 점수화 (각 0~100)
    j["vol_score"] = (j["volume_momentum"].clip(0, 3) / 3 * 100).round(1)
    j["accel_score"] = (((j["price_acceleration_%"].fillna(0).clip(-30, 30) + 30) / 60) * 100).round(1)
    j["skew_score"] = (((j["mean_median_skew_%"].fillna(0).clip(-15, 15) + 15) / 30) * 100).round(1)

    # 매수심리 종합 = 거래량(50%) + 가격가속(30%) + 평균중위격차(20%)
    j["sentiment_score"] = (
        j["vol_score"] * 0.5
        + j["accel_score"] * 0.3
        + j["skew_score"] * 0.2
    ).round(1)

    return j[[
        "region_code", "apt_name", "area_bucket",
        "volume_momentum", "price_acceleration_%", "mean_median_skew_%",
        "vol_score", "accel_score", "skew_score", "sentiment_score",
    ]]


def region_sentiment_summary(area_tol: float = 5.0) -> pd.DataFrame:
    """지역(시군구) 단위 매수심리 평균."""
    sig = _buyer_sentiment_signals(area_tol)
    if sig.empty:
        return sig
    g = sig.groupby("region_code").agg(
        avg_sentiment=("sentiment_score", "mean"),
        avg_volume_momentum=("volume_momentum", "mean"),
        avg_accel=("price_acceleration_%", "mean"),
        avg_skew=("mean_median_skew_%", "mean"),
        n_complexes=("apt_name", "nunique"),
    ).round(2).reset_index()
    g["manual_catalyst"] = g["region_code"].apply(lambda r: manual_catalyst_score(r))
    g["catalyst_text"] = g["region_code"].apply(lambda r: manual_catalyst_text(r))
    return g.sort_values("avg_sentiment", ascending=False).reset_index(drop=True)


def _load_recent(months: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = date.today() - timedelta(days=30 * months)
    df_t = fetch_trades_df(date_from=cutoff)
    df_r = fetch_rents_df(date_from=cutoff)
    return df_t, df_r


def _bucketize(df: pd.DataFrame, tol: float) -> pd.DataFrame:
    df = df.copy()
    df["area_bucket"] = (df["area_m2"] / tol).round() * tol
    return df


def _compute_growth_signals(months: int, area_tol: float = 5.0) -> pd.DataFrame:
    """(region, apt, area_bucket) 별 평당가 상승률 신호.

    최근 N/2개월 평당가 중위값 vs 그 이전 N/2개월 비교.
    """
    half_days = 30 * max(months // 2, 3)
    end = date.today()
    mid = end - timedelta(days=half_days)
    start = mid - timedelta(days=half_days)

    df = fetch_trades_df(date_from=start)
    if df.empty:
        return pd.DataFrame()
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    mid_ts = pd.Timestamp(mid)

    recent = df[df["deal_date"] > mid_ts]
    prior = df[df["deal_date"] <= mid_ts]

    r = recent.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        recent_ppp=("price_per_pyeong", "median"),
        recent_deals=("price_per_pyeong", "count"),
    )
    p = prior.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        prior_ppp=("price_per_pyeong", "median"),
        prior_deals=("price_per_pyeong", "count"),
    )
    g = r.join(p, how="inner")
    g["price_growth_%"] = ((g["recent_ppp"] - g["prior_ppp"]) / g["prior_ppp"] * 100).round(2)
    return g.reset_index()


def recommend_gap_investment(seed_man: int, months: int = 6, area_tol: float = 5.0,
                              min_trade_deals: int = 50, min_rent_deals: int = 50,
                              max_jeonse_ratio: float = 1.0,
                              ownership: str = "무주택",
                              first_time_buyer: bool = False,
                              dsr_cap_man: float | None = None) -> pd.DataFrame:
    """갭투자용. 시드(만원)로 살 수 있는 (지역+단지+평형) 추천.

    갭투자는 일반적으로 전세 보증금이 임차인 부담분이므로 LTV 대출은 받지 않음.
    필요자기자본 = 갭 = trade - rent. → gap ≤ 시드 조건.
    """
    df_t, df_r = _load_recent(months)
    if df_t.empty or df_r.empty:
        return pd.DataFrame()
    df_t = _bucketize(df_t, area_tol)
    df_r = to_jeonse_equiv(_bucketize(df_r, area_tol))

    t_agg = df_t.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        trade_median=("deal_amount", "median"),
        trade_count=("deal_amount", "count"),
        build_year=("build_year", "max"),
    )
    r_agg = df_r.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        rent_median=("jeonse_equiv", "median"),
        rent_count=("jeonse_equiv", "count"),
    )
    j = t_agg.join(r_agg, how="inner").reset_index()
    if j.empty:
        return j

    j["gap"] = j["trade_median"] - j["rent_median"]
    j["jeonse_ratio"] = (j["rent_median"] / j["trade_median"] * 100).round(2)  # %
    j = j[
        (j["gap"] > 0)
        & (j["gap"] <= seed_man)
        & (j["trade_count"] >= min_trade_deals)
        & (j["rent_count"] >= min_rent_deals)
        & (j["jeonse_ratio"] <= max_jeonse_ratio * 100)
    ].copy()
    if j.empty:
        return j

    j["activity"] = j["trade_count"] + j["rent_count"]
    j["ltv_%"] = j["region_code"].apply(lambda r: get_ltv_pct(r, ownership, first_time_buyer))
    j["zone"] = j["region_code"].apply(get_zone)
    j["required_equity"] = j["gap"]
    j["loan_capacity"] = 0
    j["max_buy_price"] = j["trade_median"]
    j["score"] = (
        j["jeonse_ratio"].rank(pct=True) * 0.7
        + j["activity"].rank(pct=True) * 0.3
    ) * 100
    j["score"] = j["score"].round(1)
    j = j.sort_values("score", ascending=False).reset_index(drop=True)
    return j


def recommend_rental_yield(seed_man: int, months: int = 12, area_tol: float = 5.0,
                            min_trade_deals: int = 50, min_rent_deals: int = 50,
                            ownership: str = "무주택",
                            first_time_buyer: bool = False,
                            use_loan: bool = True,
                            dsr_cap_man: float | None = None) -> pd.DataFrame:
    """임대수익형. 시드로 가능한 (매매가-보증금) 매물 중 연수익률 높은 순."""
    df_t, df_r = _load_recent(months)
    if df_t.empty or df_r.empty:
        return pd.DataFrame()
    df_t = _bucketize(df_t, area_tol)
    df_r = _bucketize(df_r[df_r["monthly_rent"] > 0], area_tol)
    if df_r.empty:
        return pd.DataFrame()

    t_agg = df_t.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        trade_median=("deal_amount", "median"),
        trade_count=("deal_amount", "count"),
        build_year=("build_year", "max"),
    )
    r_agg = df_r.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        deposit_median=("deposit", "median"),
        monthly_median=("monthly_rent", "median"),
        rent_count=("monthly_rent", "count"),
    )
    j = t_agg.join(r_agg, how="inner").reset_index()
    if j.empty:
        return j

    # LTV+한도cap+DSR 적용 대출 (use_loan=False면 LTV 0%)
    if use_loan:
        res = vectorized_loan_equity(j["trade_median"], j["region_code"],
                                       ownership, first_time_buyer, dsr_cap_man)
        j["ltv_%"] = res["ltv_pct"]
        j["zone"] = res["zone"]
        j["loan_capacity"] = res["loan_capacity"]
    else:
        j["ltv_%"] = 0.0
        j["zone"] = j["region_code"].apply(get_zone)
        j["loan_capacity"] = 0.0
    # 임대수익: 자기자본 = 매매가 - 보증금 - 대출
    j["required_equity"] = (j["trade_median"] - j["deposit_median"] - j["loan_capacity"]).round(0)
    j["invest"] = j["required_equity"].clip(lower=0)
    j["max_buy_price"] = j["trade_median"]

    j = j[
        (j["trade_median"] > 0)
        & (j["required_equity"] > 0)
        & (j["required_equity"] <= seed_man)
        & (j["trade_count"] >= min_trade_deals)
        & (j["rent_count"] >= min_rent_deals)
    ].copy()
    if j.empty:
        return j

    j["annual_yield_%"] = (j["monthly_median"] * 12 / j["required_equity"] * 100).round(2)
    j["activity"] = j["trade_count"] + j["rent_count"]
    j["score"] = (
        j["annual_yield_%"].rank(pct=True) * 0.8
        + j["activity"].rank(pct=True) * 0.2
    ) * 100
    j["score"] = j["score"].round(1)
    j = j.sort_values("score", ascending=False).reset_index(drop=True)
    return j


def recommend_buy_outright(seed_man: int, months: int = 12, area_tol: float = 5.0,
                            min_trade_deals: int = 50,
                            ownership: str = "무주택",
                            first_time_buyer: bool = False,
                            use_loan: bool = True,
                            dsr_cap_man: float | None = None) -> pd.DataFrame:
    """자가매입형. (시드 + 지역별 LTV 대출)로 살 수 있는 매물 + 저평가된 순."""
    df_t, _ = _load_recent(months)
    if df_t.empty:
        return pd.DataFrame()
    df_t = _bucketize(df_t, area_tol)

    region_avg_ppp = df_t.groupby("region_code")["price_per_pyeong"].median()

    g = df_t.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        trade_median=("deal_amount", "median"),
        ppp_median=("price_per_pyeong", "median"),
        trade_count=("deal_amount", "count"),
        build_year=("build_year", "max"),
    ).reset_index()
    if g.empty:
        return g

    # LTV + 한도cap + DSR 적용 대출
    if use_loan:
        res = vectorized_loan_equity(g["trade_median"], g["region_code"],
                                       ownership, first_time_buyer, dsr_cap_man)
        g["ltv_%"] = res["ltv_pct"]
        g["zone"] = res["zone"]
        g["loan_capacity"] = res["loan_capacity"]
        g["required_equity"] = res["required_equity"]
    else:
        g["ltv_%"] = 0.0
        g["zone"] = g["region_code"].apply(get_zone)
        g["loan_capacity"] = 0.0
        g["required_equity"] = g["trade_median"]
    g["max_buy_price"] = g["trade_median"]

    g = g[
        (g["required_equity"] <= seed_man)
        & (g["trade_count"] >= min_trade_deals)
    ].copy()
    if g.empty:
        return g

    g["region_median_ppp"] = g["region_code"].map(region_avg_ppp)
    g["value_ratio"] = (g["ppp_median"] / g["region_median_ppp"] * 100).round(2)  # % (낮을수록 저평가)
    g["score"] = (
        (1 - g["value_ratio"].rank(pct=True)) * 0.6
        + g["trade_count"].rank(pct=True) * 0.4
    ) * 100
    g["score"] = g["score"].round(1)
    g = g.sort_values("score", ascending=False).reset_index(drop=True)
    return g


def recommend_investment_focus(seed_man: int, months: int = 12, area_tol: float = 5.0,
                                 min_trade_deals: int = 50, min_growth_deals: int = 2,
                                 ownership: str = "무주택",
                                 first_time_buyer: bool = False,
                                 use_loan: bool = True,
                                 catalyst_weight: float = 0.10,
                                 tier_weight: float = 0.70,
                                 prestige_weight: float = 0.30,
                                 dsr_cap_man: float | None = None) -> pd.DataFrame:
    """🚀 투자수익 추구. 호재 + 선행지표 + 레버리지 + 상급지 등급으로 추천.

    종합점수 = catalyst_weight * 호재 + tier_weight * 상급지 + rest * 선행/정량지표.
    rest (= 1 - cw - tw) 내부 구성:
      - 단지 상대강도 (RS):       25%  ← 신규
      - 전세가율 가속도:           20%  ← 신규
      - 입주물량 압력(역, 12mo):   10%  ← 신규 (데이터 없으면 중립)
      - 인구 순유입(12mo):         10%  ← 신규 (데이터 없으면 중립)
      - 단순 가격모멘텀:           15%
      - 예상 ROI(레버리지):        10%
      - 거래활성도:                10%
    """
    df_t, _ = _load_recent(months)
    if df_t.empty:
        return pd.DataFrame()
    df_t = _bucketize(df_t, area_tol)
    this_year = date.today().year

    g = df_t.groupby(["region_code", "apt_name", "area_bucket"]).agg(
        trade_median=("deal_amount", "median"),
        ppp_median=("price_per_pyeong", "median"),
        trade_count=("deal_amount", "count"),
        build_year=("build_year", "max"),
    ).reset_index()

    growth = _compute_growth_signals(months, area_tol)
    if not growth.empty:
        g = g.merge(growth, on=["region_code", "apt_name", "area_bucket"], how="left")
    else:
        g["recent_ppp"] = g["ppp_median"]
        g["prior_ppp"] = g["ppp_median"]
        g["price_growth_%"] = 0.0
        g["recent_deals"] = 0
        g["prior_deals"] = 0

    # 매수심리 시그널 (KB 매수우위지수 proxy)
    sentiment = _buyer_sentiment_signals(area_tol)
    if not sentiment.empty:
        g = g.merge(sentiment, on=["region_code", "apt_name", "area_bucket"], how="left")
    # 매수심리 미산출 단지는 중립 50점
    g["sentiment_score"] = g.get("sentiment_score", pd.Series(50.0, index=g.index)).fillna(50.0)
    g["volume_momentum"] = g.get("volume_momentum", pd.Series(1.0, index=g.index)).fillna(1.0)
    g["price_acceleration_%"] = g.get("price_acceleration_%", pd.Series(0.0, index=g.index)).fillna(0.0)
    g["vol_score"] = g.get("vol_score", pd.Series(50.0, index=g.index)).fillna(50.0)

    # 신축 가산점: 5년 이내 입주 80점, 10년 이내 40점
    g["new_build_score"] = 0.0
    g.loc[g["build_year"] >= this_year - 5, "new_build_score"] = 80
    g.loc[(g["build_year"] >= this_year - 10) & (g["build_year"] < this_year - 5), "new_build_score"] = 40
    # 수동 호재 (지역 단위)
    g["manual_catalyst"] = g["region_code"].apply(lambda r: manual_catalyst_score(r))
    g["catalysts"] = g["region_code"].apply(lambda r: manual_catalyst_text(r))

    # 상급지 등급 (정보 표시용으로만 유지 — 점수 산식에는 안 들어감)
    g["tier_score"] = g["region_code"].apply(region_tier_score)
    g["tier_label"] = g["region_code"].apply(region_tier_label)

    # 시장가치 점수 (시군구 중위 평당가 백분위) — 다중 윈도우 백테스트 결과 ρ +0.61로 가장 강한 신호
    mkt = region_market_score(months=months)
    if not mkt.empty:
        g = g.merge(mkt[["region_code", "market_score"]], on="region_code", how="left")
    g["market_score"] = g.get("market_score", pd.Series(50.0, index=g.index)).fillna(50.0)
    # 지역 점수 = market + 호재 가산
    # 호재 슬라이더가 클수록 호재 강한 지역(평택 등)에 가산점이 늘어남 → 저평가+호재 발굴 도구.
    cw_amp = max(0.0, min(1.0, catalyst_weight))
    g["region_score"] = (
        g["market_score"] + g["manual_catalyst"] * cw_amp
    ).clip(upper=100).round(1)

    # 종합 호재점수 = 수동(50%) + 매수심리(35%) + 신축(15%)
    g["catalyst_score"] = (
        g["manual_catalyst"] * 0.50
        + g["sentiment_score"] * 0.35
        + g["new_build_score"] * 0.15
    ).round(1)

    # LTV + 한도 cap + DSR 적용
    if use_loan:
        res = vectorized_loan_equity(g["trade_median"], g["region_code"],
                                       ownership, first_time_buyer, dsr_cap_man)
        g["ltv_%"] = res["ltv_pct"]
        g["zone"] = res["zone"]
        g["loan_capacity"] = res["loan_capacity"]
        g["required_equity"] = res["required_equity"]
    else:
        g["ltv_%"] = 0.0
        g["zone"] = g["region_code"].apply(get_zone)
        g["loan_capacity"] = 0.0
        g["required_equity"] = g["trade_median"]
    g["max_buy_price"] = g["trade_median"]

    # 매수 가능 조건
    g = g[
        (g["required_equity"] > 0)
        & (g["required_equity"] <= seed_man)
        & (g["trade_count"] >= min_trade_deals)
    ].copy()
    if g.empty:
        return g

    # 레버리지
    g["leverage"] = 1.0
    nonzero = g["ltv_%"] > 0
    g.loc[nonzero, "leverage"] = (1.0 / (1.0 - g.loc[nonzero, "ltv_%"] / 100)).round(2)

    g["price_growth_%"] = g["price_growth_%"].fillna(0)
    g["expected_roi_%"] = (g["price_growth_%"] * g["leverage"]).round(2)
    g["expected_gain"] = (g["trade_median"] * g["price_growth_%"] / 100).round(0)
    g["seed_usage_%"] = (g["required_equity"] / max(seed_man, 1) * 100).round(1)

    # ── 선행지표 시그널 merge ──
    keys = ["region_code", "apt_name", "area_bucket"]
    rs = apt_relative_strength(months=months, area_tol=area_tol)
    if not rs.empty:
        g = g.merge(rs[keys + ["rs_score"]], on=keys, how="left")
    g["rs_score"] = g.get("rs_score", pd.Series(50.0, index=g.index)).fillna(50.0)

    jr = jeonse_ratio_acceleration(months=months, area_tol=area_tol)
    if not jr.empty:
        g = g.merge(jr[keys + ["jeonse_accel_score"]], on=keys, how="left")
    g["jeonse_accel_score"] = g.get(
        "jeonse_accel_score", pd.Series(50.0, index=g.index)).fillna(50.0)

    sp = supply_pressure()
    if not sp.empty:
        g = g.merge(sp[["region_code", "supply_pressure_score"]],
                    on="region_code", how="left")
    g["supply_pressure_score"] = g.get(
        "supply_pressure_score", pd.Series(50.0, index=g.index)).fillna(50.0)

    pop = population_inflow()
    if not pop.empty:
        g = g.merge(pop[["region_code", "population_score"]],
                    on="region_code", how="left")
    g["population_score"] = g.get(
        "population_score", pd.Series(50.0, index=g.index)).fillna(50.0)

    # ── 단지 prestige (시군구 내 대장 점수) + dong 정보 ──
    pres = apt_prestige_score(months=months, area_tol=area_tol)
    if not pres.empty:
        extra = ["prestige_score"]
        if "dong" in pres.columns:
            extra.append("dong")
        g = g.merge(pres[keys + extra], on=keys, how="left")
    g["prestige_score"] = g.get(
        "prestige_score", pd.Series(50.0, index=g.index)).fillna(50.0)

    # ── 종합점수 (2026-05 단순화) ──
    # 다중 시점 백테스트(3 윈도우 평균 ρ +0.62) 결과
    # 가장 단순한 'market + prestige' 조합이 가장 정확. tier·호재·선행지표는 보조용.
    #   - tier·jeonse_accel·population·supply_pressure: 점수 산식에서 제외 (ρ 약하거나 역상관)
    #   - 호재: region_score 안에서 슬라이더로 가산만 (저평가+호재 발굴 도구)
    tw = max(0.0, min(1.0, tier_weight))            # region_score 비중 (default 0.7)
    pw = max(0.0, min(1.0, prestige_weight))        # prestige 비중 (default 0.3)
    if tw + pw <= 0:
        tw, pw = 0.7, 0.3
    total = tw + pw
    g["score"] = (
        g["region_score"].rank(pct=True) * (tw / total)
        + g["prestige_score"].rank(pct=True) * (pw / total)
    ) * 100
    g["score"] = g["score"].round(1)
    g = g.sort_values("score", ascending=False).reset_index(drop=True)
    return g


def region_summary(rec_df: pd.DataFrame, region_map: dict[str, str],
                    metric_col: str, top_n: int = 15) -> pd.DataFrame:
    """추천 결과를 지역(시군구) 단위로 집계.

    metric_col 에 따라 대표지표 컬럼명이 달라짐.
    """
    if rec_df.empty:
        return pd.DataFrame()
    agg_kw = {
        "opportunities": ("apt_name", "count"),
        "unique_apts":   ("apt_name", "nunique"),
        "avg_score":     ("score", "mean"),
    }
    if metric_col == "annual_yield_%":
        agg_kw["best_yield_%"] = (metric_col, "max")
    elif metric_col == "gap":
        agg_kw["min_gap"] = (metric_col, "min")
    elif metric_col == "ppp_median":
        agg_kw["min_trade"] = ("trade_median", "min")
    elif metric_col == "expected_roi_%":
        agg_kw["best_roi_%"] = (metric_col, "max")
        agg_kw["avg_growth_%"] = ("price_growth_%", "mean")

    by_region = rec_df.groupby("region_code").agg(**agg_kw).reset_index()
    by_region["region"] = by_region["region_code"].map(region_map).fillna(by_region["region_code"])
    by_region["avg_score"] = by_region["avg_score"].round(1)
    by_region = by_region.sort_values("opportunities", ascending=False).head(top_n)
    cols = ["region", "region_code", "opportunities", "unique_apts", "avg_score"]
    for k in ("best_yield_%", "min_gap", "min_trade", "best_roi_%", "avg_growth_%"):
        if k in by_region.columns:
            if k.endswith("_%"):
                by_region[k] = by_region[k].round(2)
            cols.append(k)
    return by_region[cols].reset_index(drop=True)
