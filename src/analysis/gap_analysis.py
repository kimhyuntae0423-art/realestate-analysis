"""매매-전세 갭 분석

같은 단지의 비슷한 면적에서 (최근 매매 중위가) - (최근 전세 중위가) 계산.
보증부월세는 전세환산보증금 = 보증금 + 월세*100 으로 변환.
"""
from __future__ import annotations
import pandas as pd


def to_jeonse_equiv(df_rent: pd.DataFrame, monthly_to_deposit: int = 100) -> pd.DataFrame:
    """월세를 전세환산금액으로 (월세 * 100 + 보증금)"""
    df = df_rent.copy()
    df["jeonse_equiv"] = df["deposit"] + df["monthly_rent"] * monthly_to_deposit
    return df


def gap_table(df_trade: pd.DataFrame, df_rent: pd.DataFrame,
              area_tol: float = 5.0, months: int = 6) -> pd.DataFrame:
    """단지+면적 단위로 매매-전세 갭 산출.

    area_tol: 면적 묶음 허용 오차 (m²). 5m² 이내는 같은 평형으로 간주.
    months: 분석 기간 (최근 N개월)
    """
    if df_trade.empty or df_rent.empty:
        return pd.DataFrame()

    df_trade = df_trade.copy()
    df_rent = to_jeonse_equiv(df_rent)
    df_trade["deal_date"] = pd.to_datetime(df_trade["deal_date"])
    df_rent["deal_date"] = pd.to_datetime(df_rent["deal_date"])

    cutoff = max(df_trade["deal_date"].max(), df_rent["deal_date"].max()) - pd.DateOffset(months=months)
    t = df_trade[df_trade["deal_date"] >= cutoff].copy()
    r = df_rent[df_rent["deal_date"] >= cutoff].copy()

    t["area_bucket"] = (t["area_m2"] / area_tol).round() * area_tol
    r["area_bucket"] = (r["area_m2"] / area_tol).round() * area_tol

    t_agg = t.groupby(["apt_name", "area_bucket"]).agg(
        trade_median=("deal_amount", "median"),
        trade_count=("deal_amount", "count"),
    )
    r_agg = r.groupby(["apt_name", "area_bucket"]).agg(
        rent_median=("jeonse_equiv", "median"),
        rent_count=("jeonse_equiv", "count"),
    )
    joined = t_agg.join(r_agg, how="inner").reset_index()
    if joined.empty:
        return joined

    joined["gap"] = joined["trade_median"] - joined["rent_median"]
    joined["gap_ratio_%"] = (joined["gap"] / joined["trade_median"] * 100).round(2)
    joined = joined.sort_values("gap").reset_index(drop=True)
    return joined
