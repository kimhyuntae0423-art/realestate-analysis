"""가격 추이 분석"""
from __future__ import annotations
import pandas as pd

PYEONG = 3.305785


def monthly_summary(df_trade: pd.DataFrame) -> pd.DataFrame:
    """월별 평균/중위/거래량/평당가"""
    if df_trade.empty:
        return pd.DataFrame()
    df = df_trade.copy()
    df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M").astype(str)
    g = df.groupby("ym").agg(
        deals=("deal_amount", "count"),
        avg_price=("deal_amount", "mean"),
        median_price=("deal_amount", "median"),
        avg_ppp=("price_per_pyeong", "mean"),
        avg_area_m2=("area_m2", "mean"),
    ).round(0).astype({"deals": int})
    g = g.reset_index().sort_values("ym")
    return g


def apt_summary(df_trade: pd.DataFrame, top: int = 30) -> pd.DataFrame:
    """단지별 거래 요약 (거래 많은 순)"""
    if df_trade.empty:
        return pd.DataFrame()
    g = df_trade.groupby("apt_name").agg(
        deals=("deal_amount", "count"),
        avg_price=("deal_amount", "mean"),
        median_price=("deal_amount", "median"),
        min_price=("deal_amount", "min"),
        max_price=("deal_amount", "max"),
        avg_ppp=("price_per_pyeong", "mean"),
        avg_area_m2=("area_m2", "mean"),
        build_year=("build_year", "max"),
    ).round(0).astype({"deals": int})
    g = g.sort_values("deals", ascending=False).head(top).reset_index()
    return g


def yoy_change(monthly: pd.DataFrame) -> pd.DataFrame:
    """전년동월 대비 변동률"""
    if monthly.empty or len(monthly) < 13:
        return monthly
    m = monthly.copy()
    m["avg_price_yoy_%"] = (m["avg_price"].pct_change(12) * 100).round(2)
    m["avg_ppp_yoy_%"] = (m["avg_ppp"].pct_change(12) * 100).round(2)
    return m
