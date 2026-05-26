"""선행 지표 시그널 모음.

각 함수는 (region_code, apt_name, area_bucket) 키로 점수 산출.
점수는 0~100 정규화 (낮을수록 약세, 높을수록 강세).

함수들은 as_of 시점을 받아 그 시점 기준 시그널을 만들 수 있음 → 백테스트 호환.

시그널 목록:
  1. relative_strength       단지/평형 가격모멘텀 vs 시군구 평균
  2. jeonse_ratio_acceleration  전세가율 가속도 (매매 전환 신호)
  3. supply_pressure         입주물량 압력 (역지표) - 데이터 있을 때만
  4. population_inflow       시군구별 인구 순유입 - 데이터 있을 때만
"""
from __future__ import annotations
from datetime import date, timedelta

import pandas as pd

from src.database.repository import fetch_trades_df, fetch_rents_df
from src.analysis.gap_analysis import to_jeonse_equiv


def _bucketize(df: pd.DataFrame, tol: float) -> pd.DataFrame:
    df = df.copy()
    df["area_bucket"] = (df["area_m2"] / tol).round() * tol
    return df


def _months_ago(d: date, months: int) -> date:
    return d - timedelta(days=30 * months)


# ─── 1. 단지 상대강도 (Relative Strength) ──────────────────────────

def apt_relative_strength(
    as_of: date | None = None,
    months: int = 12,
    area_tol: float = 5.0,
    min_deals: int = 2,
) -> pd.DataFrame:
    """단지·평형별 상대강도 (단지 모멘텀 / 시군구 평균 모멘텀).

    시군구가 평탄해도 그 안에서 유독 잘 가는 단지를 잡아냄.
    > 1.0 = 시군구 대비 강세, < 1.0 = 약세.
    """
    as_of = as_of or date.today()
    half_days = 30 * max(months // 2, 3)
    end = as_of
    mid = end - timedelta(days=half_days)
    start = mid - timedelta(days=half_days)

    df = fetch_trades_df(date_from=start, date_to=end)
    if df.empty:
        return pd.DataFrame()
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    mid_ts = pd.Timestamp(mid)
    recent = df[df["deal_date"] > mid_ts]
    prior = df[df["deal_date"] <= mid_ts]

    keys = ["region_code", "apt_name", "area_bucket"]
    r = recent.groupby(keys).agg(
        recent_ppp=("price_per_pyeong", "median"),
        recent_deals=("price_per_pyeong", "count"),
    )
    p = prior.groupby(keys).agg(
        prior_ppp=("price_per_pyeong", "median"),
        prior_deals=("price_per_pyeong", "count"),
    )
    g = r.join(p, how="inner")
    g = g[(g["recent_deals"] >= min_deals) & (g["prior_deals"] >= min_deals)]
    if g.empty:
        return pd.DataFrame()
    g["apt_growth_%"] = ((g["recent_ppp"] - g["prior_ppp"]) / g["prior_ppp"] * 100)
    g = g.reset_index()

    region_avg = g.groupby("region_code")["apt_growth_%"].mean().rename("region_avg_growth_%")
    g = g.merge(region_avg, on="region_code", how="left")
    # +100 shift로 음수 시군구에서도 안전하게 비율 계산
    g["rs"] = ((g["apt_growth_%"] + 100) / (g["region_avg_growth_%"] + 100)).round(3)
    # 0~100 점수화 (1.0 기준, 0.7~1.3 → 0~100 선형)
    g["rs_score"] = ((g["rs"].clip(0.7, 1.3) - 0.7) / 0.6 * 100).round(1)
    return g[["region_code", "apt_name", "area_bucket",
              "apt_growth_%", "region_avg_growth_%", "rs", "rs_score"]]


# ─── 2. 전세가율 가속도 ────────────────────────────────────────────

def jeonse_ratio_acceleration(
    as_of: date | None = None,
    months: int = 12,
    area_tol: float = 5.0,
    min_deals: int = 2,
) -> pd.DataFrame:
    """전세가율(전세/매매)의 시기별 변화. 가속도 ↑ = 매매 전환 임박 신호.

    최근 N/2개월 평균 전세가율 - 그 이전 N/2개월 평균 전세가율 (%p).
    +5%p 이상이면 강한 신호.
    """
    as_of = as_of or date.today()
    half_days = 30 * max(months // 2, 3)
    end = as_of
    mid = end - timedelta(days=half_days)
    start = mid - timedelta(days=half_days)

    df_t = fetch_trades_df(date_from=start, date_to=end)
    df_r = fetch_rents_df(date_from=start, date_to=end)
    if df_t.empty or df_r.empty:
        return pd.DataFrame()
    df_t = _bucketize(df_t, area_tol)
    df_r = to_jeonse_equiv(_bucketize(df_r, area_tol))
    df_t["deal_date"] = pd.to_datetime(df_t["deal_date"])
    df_r["deal_date"] = pd.to_datetime(df_r["deal_date"])
    mid_ts = pd.Timestamp(mid)

    def _ratio_block(t_block, r_block):
        keys = ["region_code", "apt_name", "area_bucket"]
        t = t_block.groupby(keys)["deal_amount"].median().rename("trade_med")
        r = r_block.groupby(keys)["jeonse_equiv"].median().rename("rent_med")
        tn = t_block.groupby(keys)["deal_amount"].count().rename("t_n")
        rn = r_block.groupby(keys)["jeonse_equiv"].count().rename("r_n")
        j = pd.concat([t, r, tn, rn], axis=1).dropna()
        j["ratio_%"] = (j["rent_med"] / j["trade_med"] * 100)
        return j.reset_index()

    recent = _ratio_block(df_t[df_t["deal_date"] > mid_ts],
                          df_r[df_r["deal_date"] > mid_ts])
    prior = _ratio_block(df_t[df_t["deal_date"] <= mid_ts],
                         df_r[df_r["deal_date"] <= mid_ts])
    keys = ["region_code", "apt_name", "area_bucket"]
    recent = recent[(recent["t_n"] >= min_deals) & (recent["r_n"] >= min_deals)]
    prior = prior[(prior["t_n"] >= min_deals) & (prior["r_n"] >= min_deals)]

    j = recent[keys + ["ratio_%"]].rename(columns={"ratio_%": "recent_ratio_%"}).merge(
        prior[keys + ["ratio_%"]].rename(columns={"ratio_%": "prior_ratio_%"}),
        on=keys, how="inner")
    if j.empty:
        return pd.DataFrame()
    j["jeonse_accel_%p"] = (j["recent_ratio_%"] - j["prior_ratio_%"]).round(2)
    # -5%p ~ +10%p → 0~100 점수
    j["jeonse_accel_score"] = (
        (j["jeonse_accel_%p"].clip(-5, 10) + 5) / 15 * 100
    ).round(1)
    return j[keys + ["recent_ratio_%", "prior_ratio_%",
                       "jeonse_accel_%p", "jeonse_accel_score"]]


# ─── 3. 입주물량 압력 (역지표, KOSIS/HUG 데이터 필요) ───────────────

def supply_pressure(as_of: date | None = None, lookahead_months: int = 12) -> pd.DataFrame:
    """시군구별 입주물량 압력. 호수 ↑ → 점수 ↓ (역지표, 0~100).

    데이터 소스 우선순위:
      1. SupplySchedule 5자리(시군구) 직접 등록값
      2. SupplySchedule 2자리(시도) × 시군구 인구 가중치 (population_flow 전입 share)

    KOSIS는 시군구 입주물량을 제공하지 않아 시도 단위로 받아 분배함.
    사용검사실적은 향후 예정이 아닌 '직전 12개월' 실적이므로 lookback으로 동작.
    """
    try:
        from src.database.models import SupplySchedule, PopulationFlow, SessionLocal
        from sqlalchemy import select
    except ImportError:
        return pd.DataFrame()

    as_of = as_of or date.today()
    # 사용검사실적은 과거 12개월 누적을 가까운 미래 압력의 proxy로 사용
    start = as_of - timedelta(days=30 * lookahead_months)
    try:
        with SessionLocal() as s:
            q = select(SupplySchedule).where(
                SupplySchedule.move_in_date >= start,
                SupplySchedule.move_in_date <= as_of,
            )
            df = pd.read_sql(q, s.bind)
            pq = select(PopulationFlow).where(
                PopulationFlow.flow_date >= start,
                PopulationFlow.flow_date <= as_of,
            )
            pdf = pd.read_sql(pq, s.bind)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df["code_len"] = df["region_code"].str.len()
    direct = (df[df["code_len"] == 5]
              .groupby("region_code")["units"].sum()
              .rename("supply_units_12mo").reset_index())
    sido = (df[df["code_len"] == 2]
            .groupby("region_code")["units"].sum()
            .rename("sido_units_12mo").reset_index()
            .rename(columns={"region_code": "sido"}))

    # 시도 단위만 있는 경우 시군구로 분배. population_flow 전입을 가중치로 사용.
    fallback = pd.DataFrame()
    if not sido.empty and not pdf.empty:
        pdf = pdf[pdf["region_code"].str.len() == 5].copy()
        pdf["sido"] = pdf["region_code"].str[:2]
        # 시군구 12mo 전입 합 (양수 보장: 최소 1 처리)
        w = pdf.groupby(["sido", "region_code"])["inflow"].sum().rename("inflow_12mo").reset_index()
        w["inflow_12mo"] = w["inflow_12mo"].clip(lower=1)
        # 시도 내 시군구 share
        sido_total = w.groupby("sido")["inflow_12mo"].transform("sum")
        w["weight"] = w["inflow_12mo"] / sido_total
        fallback = w.merge(sido, on="sido", how="inner")
        fallback["supply_units_12mo"] = (fallback["sido_units_12mo"] * fallback["weight"]).round(0)
        fallback = fallback[["region_code", "supply_units_12mo"]]
        # 직접 등록값이 있는 시군구는 fallback에서 제외
        if not direct.empty:
            fallback = fallback[~fallback["region_code"].isin(direct["region_code"])]

    g = pd.concat([direct, fallback], ignore_index=True) if not fallback.empty else direct
    if g.empty:
        return g

    # 1만호 → 0점 (강한 압박), 0호 → 100점 (압박 없음)
    g["supply_pressure_score"] = (
        100 - (g["supply_units_12mo"].clip(0, 10000) / 10000 * 100)
    ).round(1)
    return g


# ─── 6. 시군구 시장가치 (평당가 백분위) ─────────────────────────────

def region_market_score(
    as_of: date | None = None,
    months: int = 24,
    min_deals: int = 20,
) -> pd.DataFrame:
    """시군구별 시장가치 점수 — 중위 평당가의 전체 시군구 백분위 (0~100).

    역할: tier(규제해제 순서)가 못 잡는 시장 평가를 보완.
        예: 마포(tier 80)는 평당가 백분위 93점 → 강남급 시장 인정.
    """
    as_of = as_of or date.today()
    start = as_of - timedelta(days=30 * months)
    df = fetch_trades_df(date_from=start, date_to=as_of)
    if df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["price_per_pyeong"])
    g = df.groupby("region_code").agg(
        median_ppp=("price_per_pyeong", "median"),
        n_deals=("price_per_pyeong", "count"),
    ).reset_index()
    g = g[g["n_deals"] >= min_deals]
    if g.empty:
        return g
    g["market_score"] = (g["median_ppp"].rank(pct=True) * 100).round(1)
    return g[["region_code", "median_ppp", "market_score"]]


# ─── 5. 단지 prestige (시군구 내 대장 아파트 신호) ─────────────────

def apt_prestige_score(
    as_of: date | None = None,
    months: int = 12,
    area_tol: float = 5.0,
    min_deals: int = 2,
    apt_weight: float = 0.6,
    dong_weight: float = 0.4,
) -> pd.DataFrame:
    """단지·평형별 '시군구 내 대장 점수'.

    가정: 같은 시군구라도 평당가 상위 단지가 대장. 동(dong) 단위 프리미엄도 추가
    (예: 화성 41590 안에서 동탄동 단지들은 시군구 평균보다 비쌈).

    구성:
      - apt_percentile: (단지 평당가 / 시군구 중위 평당가) 의 시군구 내 백분위
      - dong_percentile: (동 중위 평당가 / 시군구 중위 평당가) 의 시군구 내 백분위
      - prestige_score = apt × apt_weight + dong × dong_weight  (0~100)
    """
    as_of = as_of or date.today()
    start = as_of - timedelta(days=30 * months)
    df = fetch_trades_df(date_from=start, date_to=as_of)
    if df.empty:
        return pd.DataFrame()
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])

    # 시군구 중위 평당가
    region_med = df.groupby("region_code")["price_per_pyeong"].median().rename("region_ppp")

    # 단지·평형 중위 평당가
    keys = ["region_code", "apt_name", "area_bucket"]
    apt = df.groupby(keys).agg(
        apt_ppp=("price_per_pyeong", "median"),
        apt_deals=("price_per_pyeong", "count"),
    )
    apt = apt[apt["apt_deals"] >= min_deals].reset_index()
    apt = apt.merge(region_med, on="region_code", how="left")
    apt["apt_premium"] = apt["apt_ppp"] / apt["region_ppp"]
    # 시군구 내 백분위 (높을수록 대장)
    apt["apt_percentile"] = (
        apt.groupby("region_code")["apt_premium"].rank(pct=True) * 100
    ).round(1)

    # 동 prestige: 동(dong) 중위 평당가의 시군구 내 백분위
    if "dong" in df.columns:
        dong_df = df.copy()
        dong_df["dong"] = dong_df["dong"].fillna("").astype(str).str.strip()
        dong_df = dong_df[dong_df["dong"] != ""]
        if not dong_df.empty:
            dong_med = (dong_df.groupby(["region_code", "dong"])["price_per_pyeong"]
                              .median().rename("dong_ppp").reset_index())
            dong_med = dong_med.merge(region_med, on="region_code", how="left")
            dong_med["dong_premium"] = dong_med["dong_ppp"] / dong_med["region_ppp"]
            dong_med["dong_percentile"] = (
                dong_med.groupby("region_code")["dong_premium"].rank(pct=True) * 100
            ).round(1)
            # 단지 → 동 매핑 (단지가 여러 동에 걸치면 가장 거래 많은 동)
            apt_dong = (df.groupby(["region_code", "apt_name", "dong"]).size()
                          .reset_index(name="n"))
            apt_dong = apt_dong.sort_values("n", ascending=False).drop_duplicates(
                ["region_code", "apt_name"], keep="first")
            apt_dong = apt_dong[["region_code", "apt_name", "dong"]]
            apt = apt.merge(apt_dong, on=["region_code", "apt_name"], how="left")
            apt = apt.merge(dong_med[["region_code", "dong", "dong_percentile"]],
                            on=["region_code", "dong"], how="left")
        else:
            apt["dong_percentile"] = 50.0
    else:
        apt["dong_percentile"] = 50.0

    apt["dong_percentile"] = apt["dong_percentile"].fillna(50.0)
    apt["prestige_score"] = (
        apt["apt_percentile"] * apt_weight
        + apt["dong_percentile"] * dong_weight
    ).round(1)
    out_cols = keys + ["apt_premium", "apt_percentile",
                        "dong_percentile", "prestige_score"]
    if "dong" in apt.columns:
        out_cols = out_cols + ["dong"]
    return apt[out_cols]


# ─── 4. 인구 순유입 (KOSIS 데이터 필요) ────────────────────────────

def population_inflow(as_of: date | None = None, lookback_months: int = 12) -> pd.DataFrame:
    """시군구별 최근 N개월 순유입 인구 (전입 - 전출).

    데이터는 src.database.models.PopulationFlow (있다면) 또는 fallback empty.
    """
    try:
        from src.database.models import PopulationFlow, SessionLocal
        from sqlalchemy import select
    except ImportError:
        return pd.DataFrame()

    as_of = as_of or date.today()
    start = as_of - timedelta(days=30 * lookback_months)
    try:
        with SessionLocal() as s:
            q = select(PopulationFlow).where(
                PopulationFlow.flow_date >= start,
                PopulationFlow.flow_date <= as_of,
            )
            df = pd.read_sql(q, s.bind)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    g = df.groupby("region_code")["net_inflow"].sum().rename("net_inflow_12mo").reset_index()
    # ±5천명 → 0~100 점수 (대도시 기준 보정)
    g["population_score"] = (
        (g["net_inflow_12mo"].clip(-5000, 5000) + 5000) / 10000 * 100
    ).round(1)
    return g
