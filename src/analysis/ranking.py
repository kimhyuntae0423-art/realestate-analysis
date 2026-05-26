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


def apt_growth(df_trade: pd.DataFrame, lookback_months: int = 12, min_deals: int = 4) -> pd.DataFrame:
    """단지별 가격 상승률 (최근 lookback_months vs 그 이전 동일 기간)"""
    if df_trade.empty:
        return pd.DataFrame()
    df = df_trade.copy()
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    end = df["deal_date"].max()
    mid = end - pd.DateOffset(months=lookback_months)
    start = mid - pd.DateOffset(months=lookback_months)

    recent = df[(df["deal_date"] > mid) & (df["deal_date"] <= end)]
    prior = df[(df["deal_date"] > start) & (df["deal_date"] <= mid)]

    r = recent.groupby("apt_name").agg(recent_ppp=("price_per_pyeong", "median"),
                                       recent_deals=("price_per_pyeong", "count"))
    p = prior.groupby("apt_name").agg(prior_ppp=("price_per_pyeong", "median"),
                                      prior_deals=("price_per_pyeong", "count"))
    j = r.join(p, how="inner").reset_index()
    j = j[(j["recent_deals"] >= min_deals) & (j["prior_deals"] >= min_deals)]
    if j.empty:
        return j
    j["change_%"] = ((j["recent_ppp"] - j["prior_ppp"]) / j["prior_ppp"] * 100).round(2)
    j = j.sort_values("change_%", ascending=False).reset_index(drop=True)
    return j
