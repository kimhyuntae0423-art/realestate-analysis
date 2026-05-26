"""임대 수익률 추정

연수익률 = (월세 * 12) / (매매가 - 보증금) * 100
같은 단지+면적 묶음에서 매매 중위가, 임대 중위 보증금/월세를 사용.
"""
from __future__ import annotations
import pandas as pd


def rental_yield(df_trade: pd.DataFrame, df_rent: pd.DataFrame,
                 area_tol: float = 5.0, months: int = 12) -> pd.DataFrame:
    if df_trade.empty or df_rent.empty:
        return pd.DataFrame()

    df_trade = df_trade.copy()
    df_rent = df_rent.copy()
    df_trade["deal_date"] = pd.to_datetime(df_trade["deal_date"])
    df_rent["deal_date"] = pd.to_datetime(df_rent["deal_date"])
    cutoff = max(df_trade["deal_date"].max(), df_rent["deal_date"].max()) - pd.DateOffset(months=months)

    t = df_trade[df_trade["deal_date"] >= cutoff].copy()
    # 월세 거래만 (monthly_rent > 0)
    r = df_rent[(df_rent["deal_date"] >= cutoff) & (df_rent["monthly_rent"] > 0)].copy()

    t["area_bucket"] = (t["area_m2"] / area_tol).round() * area_tol
    r["area_bucket"] = (r["area_m2"] / area_tol).round() * area_tol

    t_agg = t.groupby(["apt_name", "area_bucket"]).agg(
        trade_median=("deal_amount", "median"),
        trade_count=("deal_amount", "count"),
    )
    r_agg = r.groupby(["apt_name", "area_bucket"]).agg(
        deposit_median=("deposit", "median"),
        monthly_median=("monthly_rent", "median"),
        rent_count=("monthly_rent", "count"),
    )

    j = t_agg.join(r_agg, how="inner").reset_index()
    if j.empty:
        return j

    j["invest"] = j["trade_median"] - j["deposit_median"]
    j = j[j["invest"] > 0]
    j["annual_yield_%"] = (j["monthly_median"] * 12 / j["invest"] * 100).round(2)
    j = j.sort_values("annual_yield_%", ascending=False).reset_index(drop=True)
    return j
