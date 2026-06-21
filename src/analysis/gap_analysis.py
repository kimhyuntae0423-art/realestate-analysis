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
              area_tol: float = 5.0, months: int = 6,
              trade_months: int | None = None) -> pd.DataFrame:
    """단지+면적 단위로 매매-전세 갭 산출.

    area_tol:     면적 묶음 허용 오차 (m²). 5m² 이내는 같은 평형으로 간주.
    months:       전세 기간 (최근 N개월). 거래건수 필터도 이 기간 기준.
    trade_months: 매매가 계산 기간. None이면 months와 동일.
                  최근 실거래 기반 현재가를 원하면 3 이하로 설정.
                  최근 기간에 거래 없으면 전체 기간 median으로 fallback.
    """
    if df_trade.empty or df_rent.empty:
        return pd.DataFrame()

    df_trade = df_trade.copy()
    df_rent = to_jeonse_equiv(df_rent)
    df_trade["deal_date"] = pd.to_datetime(df_trade["deal_date"])
    df_rent["deal_date"] = pd.to_datetime(df_rent["deal_date"])

    max_date = max(df_trade["deal_date"].max(), df_rent["deal_date"].max())
    rent_cutoff = max_date - pd.DateOffset(months=months)
    trade_cutoff_full = max_date - pd.DateOffset(months=months)
    r = df_rent[df_rent["deal_date"] >= rent_cutoff].copy()
    t_full = df_trade[df_trade["deal_date"] >= trade_cutoff_full].copy()

    t_full["area_bucket"] = (t_full["area_m2"] / area_tol).round() * area_tol
    r["area_bucket"] = (r["area_m2"] / area_tol).round() * area_tol

    # trade_count: 전체 기간 (유동성 필터용)
    count_agg = t_full.groupby(["apt_name", "area_bucket"]).agg(
        trade_count=("deal_amount", "count"),
    )
    # trade_median: 최근 trade_months 기간 (현재가)
    _tm = trade_months if (trade_months is not None and trade_months < months) else None
    if _tm:
        trade_cutoff_recent = max_date - pd.DateOffset(months=_tm)
        t_recent = df_trade[df_trade["deal_date"] >= trade_cutoff_recent].copy()
        t_recent["area_bucket"] = (t_recent["area_m2"] / area_tol).round() * area_tol
        price_agg = t_recent.groupby(["apt_name", "area_bucket"]).agg(
            trade_median=("deal_amount", "median"),
        )
        full_price_agg = t_full.groupby(["apt_name", "area_bucket"]).agg(
            trade_median_full=("deal_amount", "median"),
        )
        t_agg = count_agg.join(price_agg, how="left").join(full_price_agg, how="left")
        t_agg["trade_median"] = t_agg["trade_median"].fillna(t_agg["trade_median_full"])
        t_agg = t_agg.drop(columns=["trade_median_full"])
    else:
        price_agg = t_full.groupby(["apt_name", "area_bucket"]).agg(
            trade_median=("deal_amount", "median"),
        )
        t_agg = count_agg.join(price_agg, how="left")

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
