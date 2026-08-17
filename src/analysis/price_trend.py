"""가격 추이 분석"""
from __future__ import annotations
import pandas as pd

PYEONG = 3.305785


def monthly_summary(df_trade: pd.DataFrame) -> pd.DataFrame:
    """월별 평균/중위/거래량/평당가.

    tracked_ppp: 단지+평형 추적 성장률(구성효과 제거)을 이어붙인 합성 평당가 지수 —
    yoy_change()가 원시 avg_ppp 대신 이 컬럼으로 YoY%를 계산한다.
    """
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

    from src.analysis.hypothesis_lab import region_growth_via_unit_tracking

    growth = region_growth_via_unit_tracking(df_trade, group_cols=[])
    growth_map = dict(zip(growth["ym"].astype(str), growth["growth"])) if not growth.empty else {}
    unit_growth = g["ym"].map(growth_map).fillna(0.0)
    g["tracked_ppp"] = (g["avg_ppp"].iloc[0] * (1 + unit_growth).cumprod()).round(0)
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
    """전년동월 대비 변동률.

    평당가 YoY는 원시 avg_ppp 대신 tracked_ppp(단지+평형 추적, 구성효과 제거)로 계산한다 —
    avg_ppp를 그대로 pct_change하면 그 달 우연히 어떤 단지·평형이 거래됐는지에 좌우됨
    (2026-08-17 감리). monthly_summary()가 만든 컬럼이 없으면(구버전 입력 등) avg_ppp로 대체.
    """
    if monthly.empty or len(monthly) < 13:
        return monthly
    m = monthly.copy()
    m["avg_price_yoy_%"] = (m["avg_price"].pct_change(12) * 100).round(2)
    ppp_col = "tracked_ppp" if "tracked_ppp" in m.columns else "avg_ppp"
    m["avg_ppp_yoy_%"] = (m[ppp_col].pct_change(12) * 100).round(2)
    return m
