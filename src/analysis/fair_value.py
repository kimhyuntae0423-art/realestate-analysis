"""적정가 분석 — 오버슈팅/저평가 판단

3가지 방법으로 단지별/지역별 적정 매매가를 산출하고
현재 가격이 얼마나 고평가/저평가됐는지 판정한다.

  1. 전세가율 역산법 : 적정 전세가율(기본 65%)로 매매 적정가 역산
  2. 수익률 역산법  : 목표 임대수익률(기본 3.5%)로 적정가 역산 (월세 데이터 필요)
  3. 이동평균법    : 평당가 N개월 이동평균 대비 현재 위치 (지역 월별 + 단지별)

premium_pct > 0  → 현재가 > 적정가 → 오버슈팅(고평가)
premium_pct < 0  → 현재가 < 적정가 → 저평가
"""
from __future__ import annotations
import pandas as pd

# ── 판정 임계값 (premium_pct 기준, 내림차순) ─────────────────────────────
_THRESHOLDS = [
    (20,  "🔴 오버슈팅"),
    (10,  "🟠 고평가"),
    (-5,  "🟡 적정"),
    (-15, "🟢 저평가"),
]


def _verdict(pct: float) -> str:
    for threshold, label in _THRESHOLDS:
        if pct >= threshold:
            return label
    return "🔵 심한저평가"


# ── 1. 전세가율 역산법 ───────────────────────────────────────────────────

def fair_value_by_jeonse(
    df_trade: pd.DataFrame,
    df_rent: pd.DataFrame,
    target_jeonse_ratio: float = 0.65,
    area_tol: float = 5.0,
    months: int = 6,
) -> pd.DataFrame:
    """단지+면적별 전세가율 역산 적정가.

    fair_value = 전세환산 중위가 / target_jeonse_ratio
    fv_premium_% = (매매 중위가 - fair_value) / fair_value × 100
    """
    from src.analysis.gap_analysis import to_jeonse_equiv

    if df_trade.empty or df_rent.empty:
        return pd.DataFrame()

    df_t = df_trade.copy()
    df_r = to_jeonse_equiv(df_rent)
    df_t["deal_date"] = pd.to_datetime(df_t["deal_date"])
    df_r["deal_date"] = pd.to_datetime(df_r["deal_date"])

    cutoff = (
        max(df_t["deal_date"].max(), df_r["deal_date"].max())
        - pd.DateOffset(months=months)
    )
    t = df_t[df_t["deal_date"] >= cutoff].copy()
    r = df_r[df_r["deal_date"] >= cutoff].copy()

    t["area_bucket"] = (t["area_m2"] / area_tol).round() * area_tol
    r["area_bucket"] = (r["area_m2"] / area_tol).round() * area_tol

    t_agg = t.groupby(["apt_name", "area_bucket"]).agg(
        trade_median=("deal_amount", "median"),
        trade_count=("deal_amount", "count"),
    )
    r_agg = r.groupby(["apt_name", "area_bucket"]).agg(
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
) -> pd.DataFrame:
    """단지+면적별 임대수익률 역산 적정가.

    fair_value = (월세 × 12) / (target_yield_pct / 100)
    fv_premium_% = (매매 중위가 - fair_value) / fair_value × 100
    월세 데이터가 없으면 빈 DataFrame 반환.
    """
    if df_trade.empty or df_rent.empty:
        return pd.DataFrame()

    df_t = df_trade.copy()
    df_r = df_rent.copy()
    df_t["deal_date"] = pd.to_datetime(df_t["deal_date"])
    df_r["deal_date"] = pd.to_datetime(df_r["deal_date"])
    cutoff = (
        max(df_t["deal_date"].max(), df_r["deal_date"].max())
        - pd.DateOffset(months=months)
    )

    t = df_t[df_t["deal_date"] >= cutoff].copy()
    r = df_r[
        (df_r["deal_date"] >= cutoff) & (df_r["monthly_rent"] > 0)
    ].copy()

    if r.empty:
        return pd.DataFrame()

    t["area_bucket"] = (t["area_m2"] / area_tol).round() * area_tol
    r["area_bucket"] = (r["area_m2"] / area_tol).round() * area_tol

    t_agg = t.groupby(["apt_name", "area_bucket"]).agg(
        trade_median=("deal_amount", "median"),
        trade_count=("deal_amount", "count"),
    )
    r_agg = r.groupby(["apt_name", "area_bucket"]).agg(
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


# ── 3-A. 이동평균법 — 지역 월별 ─────────────────────────────────────────

def fair_value_ppp_trend(
    df_trade: pd.DataFrame,
    ma_months: int = 24,
) -> pd.DataFrame:
    """지역 월별 평당가 이동평균 vs 현재 오버슈팅.

    Columns: ym, avg_ppp, ma_ppp, overshoot_%, verdict
    """
    if df_trade.empty:
        return pd.DataFrame()

    df = df_trade.copy()
    df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M").astype(str)
    monthly = (
        df.groupby("ym")
        .agg(avg_ppp=("price_per_pyeong", "mean"), deals=("deal_amount", "count"))
        .reset_index()
        .sort_values("ym")
    )

    if len(monthly) < 6:
        return pd.DataFrame()

    min_periods = max(6, ma_months // 3)
    monthly["ma_ppp"] = (
        monthly["avg_ppp"].rolling(ma_months, min_periods=min_periods).mean().round(0)
    )
    monthly["overshoot_%"] = (
        (monthly["avg_ppp"] - monthly["ma_ppp"]) / monthly["ma_ppp"] * 100
    ).round(2)
    monthly["verdict"] = monthly["overshoot_%"].apply(
        lambda x: _verdict(x) if pd.notna(x) else "—"
    )

    return monthly.dropna(subset=["ma_ppp"]).reset_index(drop=True)


# ── 4. 추천 DataFrame 보강 ──────────────────────────────────────────────

def enrich_with_fair_value(
    df: pd.DataFrame,
    trade_col: str = "trade_median",
    jeonse_col: str | None = "rent_median",
    monthly_col: str | None = "monthly_median",
    target_jeonse_ratio: float = 0.65,
    target_yield_pct: float = 3.5,
) -> pd.DataFrame:
    """추천 결과 DataFrame에 적정가(전세가율 역산 또는 수익률 역산) 컬럼을 붙인다.

    - jeonse_col이 있으면 전세가율 역산 우선 적용
    - monthly_col만 있으면 수익률 역산 적용
    - 둘 다 없으면 원본 반환
    추가 컬럼: fair_value, fv_premium_%, verdict
    """
    df = df.copy()
    done = False

    if jeonse_col and jeonse_col in df.columns:
        valid = df[jeonse_col] > 0
        df.loc[valid, "fair_value"] = (
            df.loc[valid, jeonse_col] / target_jeonse_ratio
        ).round(0)
        done = True

    elif monthly_col and monthly_col in df.columns:
        valid = df[monthly_col] > 0
        df.loc[valid, "fair_value"] = (
            df.loc[valid, monthly_col] * 12 / (target_yield_pct / 100)
        ).round(0)
        done = True

    if not done or "fair_value" not in df.columns:
        return df

    fv_mask = df["fair_value"].notna() & (df["fair_value"] > 0)
    df.loc[fv_mask, "fv_premium_%"] = (
        (df.loc[fv_mask, trade_col] - df.loc[fv_mask, "fair_value"])
        / df.loc[fv_mask, "fair_value"] * 100
    ).round(2)
    df["verdict"] = df["fv_premium_%"].apply(
        lambda x: _verdict(x) if pd.notna(x) else "—"
    )
    return df


# ── 3-B. 이동평균법 — 단지별 ────────────────────────────────────────────

def fair_value_apt_vs_ma(
    df_trade: pd.DataFrame,
    ma_months: int = 18,
    min_deals: int = 5,
) -> pd.DataFrame:
    """단지별 평당가 이동평균 대비 현재 오버슈팅.

    Columns: apt_name, recent_ppp, ma_ppp, overshoot_%, verdict, total_deals
    """
    if df_trade.empty:
        return pd.DataFrame()

    df = df_trade.copy()
    df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M").astype(str)

    apt_monthly = (
        df.groupby(["apt_name", "ym"])
        .agg(avg_ppp=("price_per_pyeong", "mean"), deals=("deal_amount", "count"))
        .reset_index()
    )

    rows = []
    for apt, grp in apt_monthly.groupby("apt_name"):
        grp = grp.sort_values("ym")
        total_deals = int(grp["deals"].sum())
        if total_deals < min_deals or len(grp) < 4:
            continue
        min_periods = max(3, ma_months // 4)
        ma_series = grp["avg_ppp"].rolling(ma_months, min_periods=min_periods).mean()
        if ma_series.isna().all():
            continue
        ma_val = float(ma_series.dropna().iloc[-1])
        recent_ppp = float(grp["avg_ppp"].iloc[-1])
        overshoot = (recent_ppp - ma_val) / ma_val * 100
        rows.append({
            "apt_name": apt,
            "recent_ppp": round(recent_ppp),
            "ma_ppp": round(ma_val),
            "overshoot_%": round(overshoot, 2),
            "verdict": _verdict(overshoot),
            "total_deals": total_deals,
        })

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values("overshoot_%", ascending=False)
        .reset_index(drop=True)
    )
