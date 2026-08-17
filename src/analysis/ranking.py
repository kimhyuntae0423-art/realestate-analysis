"""지역별 랭킹 / 단지별 가격 상승률"""
from __future__ import annotations
import pandas as pd


def region_ranking(df_trade: pd.DataFrame, region_map: dict[str, str]) -> pd.DataFrame:
    """지역(시군구) 단위 평균 평당가, 거래량 랭킹"""
    if df_trade.empty:
        return pd.DataFrame()
    g = df_trade.groupby("region_code").agg(
        deals=("deal_amount", "count"),
        avg_ppp=("price_per_pyeong", "mean"),
        median_price=("deal_amount", "median"),
    ).round(0).astype({"deals": int}).reset_index()
    g["region"] = g["region_code"].map(region_map).fillna(g["region_code"])
    g = g.sort_values("avg_ppp", ascending=False)
    return g[["region", "region_code", "deals", "avg_ppp", "median_price"]].reset_index(drop=True)


def apt_growth(df_trade: pd.DataFrame, lookback_months: int = 12, min_deals: int = 4,
               area_tol: float = 5.0) -> pd.DataFrame:
    """단지+평형별 가격 상승률 (최근 lookback_months vs 그 이전 동일 기간).

    apt_name만으로 묶으면 같은 단지 안에서도 이 기간엔 큰 평형이, 저 기간엔 작은 평형이
    우연히 더 많이 거래됐을 때(구성효과) 실제 가격 변동과 무관하게 수치가 왜곡된다
    (2026-08-17 감리, forward_signals.py의 apt_relative_strength는 이미 area_bucket을
    쓰고 있어 문제 없었음). area_bucket을 키에 추가해 같은 평형끼리만 비교한다.
    """
    if df_trade.empty:
        return pd.DataFrame()
    from src.analysis.recommend import _bucketize

    df = _bucketize(df_trade, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    end = df["deal_date"].max()
    mid = end - pd.DateOffset(months=lookback_months)
    start = mid - pd.DateOffset(months=lookback_months)

    recent = df[(df["deal_date"] > mid) & (df["deal_date"] <= end)]
    prior = df[(df["deal_date"] > start) & (df["deal_date"] <= mid)]

    keys = ["apt_name", "area_bucket"]
    r = recent.groupby(keys).agg(recent_ppp=("price_per_pyeong", "median"),
                                 recent_deals=("price_per_pyeong", "count"))
    p = prior.groupby(keys).agg(prior_ppp=("price_per_pyeong", "median"),
                                prior_deals=("price_per_pyeong", "count"))
    j = r.join(p, how="inner").reset_index()
    j = j[(j["recent_deals"] >= min_deals) & (j["prior_deals"] >= min_deals)]
    if j.empty:
        return j
    j["change_%"] = ((j["recent_ppp"] - j["prior_ppp"]) / j["prior_ppp"] * 100).round(2)
    j = j.sort_values("change_%", ascending=False).reset_index(drop=True)
    return j
