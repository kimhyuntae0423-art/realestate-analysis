"""적정가 분석 — 역산법 (전세가율/수익률)

fair_value.py에서 분리 (300줄 제한, 모듈화 2단계).

  1. 전세가율 역산법 : 적정 전세가율(기본 65%)로 매매 적정가 역산
  2. 수익률 역산법  : 목표 임대수익률(기본 3.5%)로 적정가 역산 (월세 데이터 필요)

premium_pct > 0  → 현재가 > 적정가 → 오버슈팅(고평가)
premium_pct < 0  → 현재가 < 적정가 → 저평가
"""
from __future__ import annotations
import pandas as pd

from src.analysis.fair_value import _verdict


# ── 1. 전세가율 역산법 ───────────────────────────────────────────────────

def _split_trade_agg(
    df_trade: pd.DataFrame,
    keys: list[str],
    area_tol: float,
    months: int,
    trade_months: int | None,
    max_date,
) -> pd.DataFrame:
    """trade_count(전체기간) + trade_median(최근기간, fallback=전체) 분리 집계."""
    t_full = df_trade.copy()
    t_full["area_bucket"] = (t_full["area_m2"] / area_tol).round() * area_tol

    count_agg = t_full.groupby(keys).agg(trade_count=("deal_amount", "count"))
    full_price_agg = t_full.groupby(keys).agg(trade_median_full=("deal_amount", "median"))

    _tm = trade_months if (trade_months is not None and trade_months < months) else None
    if _tm:
        t_recent = df_trade[
            df_trade["deal_date"] >= max_date - pd.DateOffset(months=_tm)
        ].copy()
        t_recent["area_bucket"] = (t_recent["area_m2"] / area_tol).round() * area_tol
        price_agg = t_recent.groupby(keys).agg(trade_median=("deal_amount", "median"))
        result = count_agg.join(price_agg, how="left").join(full_price_agg, how="left")
        result["trade_median"] = result["trade_median"].fillna(result["trade_median_full"])
        return result.drop(columns=["trade_median_full"])

    result = count_agg.join(full_price_agg.rename(columns={"trade_median_full": "trade_median"}))
    return result


def fair_value_by_jeonse(
    df_trade: pd.DataFrame,
    df_rent: pd.DataFrame,
    target_jeonse_ratio: float = 0.65,
    area_tol: float = 5.0,
    months: int = 6,
    trade_months: int | None = 3,
) -> pd.DataFrame:
    """단지+면적별 전세가율 역산 적정가.

    fair_value = 전세환산 중위가 / target_jeonse_ratio
    fv_premium_% = (매매 중위가 - fair_value) / fair_value × 100
    trade_months: 현재 매매가 계산 기간. None이면 months와 동일.
    """
    from src.analysis.gap_analysis import to_jeonse_equiv

    if df_trade.empty or df_rent.empty:
        return pd.DataFrame()

    df_t = df_trade.copy()
    df_r = to_jeonse_equiv(df_rent)
    df_t["deal_date"] = pd.to_datetime(df_t["deal_date"])
    df_r["deal_date"] = pd.to_datetime(df_r["deal_date"])

    max_date = max(df_t["deal_date"].max(), df_r["deal_date"].max())
    rent_cutoff = max_date - pd.DateOffset(months=months)
    r = df_r[df_r["deal_date"] >= rent_cutoff].copy()
    r["area_bucket"] = (r["area_m2"] / area_tol).round() * area_tol

    keys = ["apt_name", "area_bucket"]
    t_agg = _split_trade_agg(df_t, keys, area_tol, months, trade_months, max_date)
    r_agg = r.groupby(keys).agg(
        jeonse_median=("jeonse_equiv", "median"),
        rent_count=("jeonse_equiv", "count"),
    )

    df = t_agg.join(r_agg, how="inner").reset_index()
    if df.empty:
        return df

    df = df[df["jeonse_median"] > 0].copy()
    df["jeonse_ratio_%"] = (df["jeonse_median"] / df["trade_median"] * 100).round(2)
    df["fair_value"] = (df["jeonse_median"] / target_jeonse_ratio).round(0)
    df["fv_premium_%"] = (
        (df["trade_median"] - df["fair_value"]) / df["fair_value"] * 100
    ).round(2)
    df["verdict"] = df["fv_premium_%"].apply(_verdict)

    return df.sort_values("fv_premium_%", ascending=False).reset_index(drop=True)


# ── 2. 수익률 역산법 ─────────────────────────────────────────────────────

def fair_value_by_yield(
    df_trade: pd.DataFrame,
    df_rent: pd.DataFrame,
    target_yield_pct: float = 3.5,
    area_tol: float = 5.0,
    months: int = 12,
    trade_months: int | None = 3,
) -> pd.DataFrame:
    """단지+면적별 임대수익률 역산 적정가.

    fair_value = (월세 × 12) / (target_yield_pct / 100)
    fv_premium_% = (매매 중위가 - fair_value) / fair_value × 100
    trade_months: 현재 매매가 계산 기간. None이면 months와 동일.
    월세 데이터가 없으면 빈 DataFrame 반환.
    """
    if df_trade.empty or df_rent.empty:
        return pd.DataFrame()

    df_t = df_trade.copy()
    df_r = df_rent.copy()
    df_t["deal_date"] = pd.to_datetime(df_t["deal_date"])
    df_r["deal_date"] = pd.to_datetime(df_r["deal_date"])
    max_date = max(df_t["deal_date"].max(), df_r["deal_date"].max())
    rent_cutoff = max_date - pd.DateOffset(months=months)

    r = df_r[
        (df_r["deal_date"] >= rent_cutoff) & (df_r["monthly_rent"] > 0)
    ].copy()
    if r.empty:
        return pd.DataFrame()

    r["area_bucket"] = (r["area_m2"] / area_tol).round() * area_tol

    keys = ["apt_name", "area_bucket"]
    t_agg = _split_trade_agg(df_t, keys, area_tol, months, trade_months, max_date)
    r_agg = r.groupby(keys).agg(
        monthly_median=("monthly_rent", "median"),
        rent_count=("monthly_rent", "count"),
    )

    df = t_agg.join(r_agg, how="inner").reset_index()
    if df.empty:
        return df

    df = df[df["monthly_median"] > 0].copy()
    df["annual_rent"] = (df["monthly_median"] * 12).round(0)
    df["fair_value"] = (df["annual_rent"] / (target_yield_pct / 100)).round(0)
    df["fv_premium_%"] = (
        (df["trade_median"] - df["fair_value"]) / df["fair_value"] * 100
    ).round(2)
    df["verdict"] = df["fv_premium_%"].apply(_verdict)

    return df.sort_values("fv_premium_%", ascending=False).reset_index(drop=True)
