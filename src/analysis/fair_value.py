"""적정가 분석 — 오버슈팅/저평가 판단 (이동평균법 + 공용 판정)

역산법(전세가율/수익률)은 fair_value_reverse.py로 분리 (300줄 제한, 모듈화 2단계).

  3. 이동평균법 : 평당가 N개월 이동평균 대비 현재 위치 (지역 월별 + 단지별)

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


# ── 3-A. 이동평균법 — 지역 월별 ─────────────────────────────────────────

def fair_value_ppp_trend(
    df_trade: pd.DataFrame,
    ma_months: int = 24,
) -> pd.DataFrame:
    """지역 월별 평당가 이동평균 vs 현재 오버슈팅.

    원시 월평균 평당가(avg_ppp)를 그대로 이동평균 대비 비교하면 그 달 우연히
    어떤 단지·평형이 거래됐는지(구성효과)에 좌우돼, KB 공식 지수 기준 오버슈팅과
    비교했을 때 상관이 거의 0(rho -0.07)이었음(2026-08-17 감리). 단지+평형 추적
    성장률(region_growth_via_unit_tracking)을 이어붙인 합성 지수(tracked_ppp)로
    이동평균/오버슈팅을 계산해 이 노이즈를 제거한다. avg_ppp는 참고용 원본 수치로
    남겨둔다.

    Columns: ym, avg_ppp, tracked_ppp, ma_ppp, overshoot_%, verdict
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

    from src.analysis.hypothesis_lab import region_growth_via_unit_tracking

    growth = region_growth_via_unit_tracking(df_trade, group_cols=[])
    growth_map = dict(zip(growth["ym"].astype(str), growth["growth"])) if not growth.empty else {}
    monthly["unit_growth"] = monthly["ym"].map(growth_map).fillna(0.0)
    monthly["tracked_ppp"] = (monthly["avg_ppp"].iloc[0] * (1 + monthly["unit_growth"]).cumprod()).round(0)

    min_periods = max(6, ma_months // 3)
    monthly["ma_ppp"] = (
        monthly["tracked_ppp"].rolling(ma_months, min_periods=min_periods).mean().round(0)
    )
    monthly["overshoot_%"] = (
        (monthly["tracked_ppp"] - monthly["ma_ppp"]) / monthly["ma_ppp"] * 100
    ).round(2)
    monthly["verdict"] = monthly["overshoot_%"].apply(
        lambda x: _verdict(x) if pd.notna(x) else "—"
    )

    return monthly.drop(columns=["unit_growth"]).dropna(subset=["ma_ppp"]).reset_index(drop=True)


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
