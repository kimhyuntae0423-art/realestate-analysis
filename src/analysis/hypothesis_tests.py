"""부동산 통념 가설 검증 함수 모음.

각 함수는 HypothesisResult(src/analysis/hypothesis_lab.py)를 반환한다.
새 가설을 추가하려면 여기에 test_* 함수를 만들고 hypothesis_lab.ALL_HYPOTHESES에 등록한다.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, mannwhitneyu

from config.settings import ROOT
from src.database.repository import fetch_trades_df
from src.analysis.recommend import _bucketize
from src.analysis.hypothesis_lab import HypothesisResult, _verdict_for, _empty_result

# ─── 1. 재건축 연한 효과 ────────────────────────────────────────────
SEOUL_GYEONGGI_PREFIXES = ("11", "41")  # 법정동코드 앞 2자리: 11=서울, 41=경기


def test_redevelopment_age_effect(months: int = 60, area_tol: float = 5.0,
                                   min_deals: int = 3) -> HypothesisResult:
    meta = dict(
        id="redevelopment_age",
        title="재건축 연한 효과",
        claim="오래된(재건축 기대감 있는) 단지일수록 최근 상승률이 더 높다",
        method=f"단지+평형 단위, 최근 {months}개월(=DB 보유 최대 범위)을 반으로 나눠 "
               f"전반기→후반기 평당가 상승률과 연식(올해-준공연도)의 Spearman 상관. "
               "서울/경기(법정동코드 11/41) vs 그 외 지역으로 나눈 하위그룹도 함께 계산.",
        expected_sign=1,
        caveats="재건축은 '연한'만이 아니라 안전진단·조합설립 진행도가 더 중요할 수 있음. "
                "너무 오래된 단지는 오히려 슬럼화로 하락할 수도 있어 비선형(U자형) 관계일 가능성 있음.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    end = df["deal_date"].max()
    mid = end - pd.DateOffset(months=months // 2)

    keys = ["region_code", "apt_name", "area_bucket"]
    recent = df[df["deal_date"] > mid]
    prior = df[df["deal_date"] <= mid]
    r = recent.groupby(keys).agg(recent_ppp=("price_per_pyeong", "median"),
                                  recent_n=("price_per_pyeong", "count"),
                                  build_year=("build_year", "max"))
    p = prior.groupby(keys).agg(prior_ppp=("price_per_pyeong", "median"),
                                 prior_n=("price_per_pyeong", "count"))
    g = r.join(p, how="inner").reset_index()
    g = g[(g["recent_n"] >= min_deals) & (g["prior_n"] >= min_deals)
          & g["build_year"].notna() & (g["build_year"] > 1900)]
    if g.empty:
        return _empty_result(**meta)

    g["growth_%"] = (g["recent_ppp"] - g["prior_ppp"]) / g["prior_ppp"] * 100
    g["age"] = date.today().year - g["build_year"]
    rho, _ = spearmanr(g["age"], g["growth_%"])

    is_sg = g["region_code"].str.startswith(SEOUL_GYEONGGI_PREFIXES)
    breakdown = {}
    for label, mask in [("서울/경기", is_sg), ("그 외 지역", ~is_sg)]:
        sub = g[mask]
        if len(sub) >= 2:
            sub_rho, _ = spearmanr(sub["age"], sub["growth_%"])
        else:
            sub_rho = float("nan")
        breakdown[label] = {
            "statistic": float(sub_rho), "n": len(sub),
            "verdict": _verdict_for(float(sub_rho), len(sub), meta["expected_sign"]),
        }

    return HypothesisResult(statistic=float(rho), n=len(g), breakdown=breakdown, **meta)


def _load_redevelopment_catalyst_regions() -> set[str]:
    """config/catalysts.json에 재건축·재개발 타입 호재가 등록된 region_code 집합."""
    p = ROOT / "config" / "catalysts.json"
    with open(p, encoding="utf-8") as f:
        cat = json.load(f)
    return {
        code for code, items in cat.get("region_catalysts", {}).items()
        if any(it.get("type") in ("재건축", "재개발") for it in items)
    }


# ─── 1b. 재건축 호재 발표 vs 단순 연한 ──────────────────────────────
def test_catalyst_announcement_vs_age(months: int = 60, area_tol: float = 5.0,
                                       min_deals: int = 3, age_threshold: int = 25) -> HypothesisResult:
    meta = dict(
        id="catalyst_vs_age",
        title="재건축 호재 발표 vs 단순 연한",
        claim=f"노후 단지(연식 {age_threshold}년 이상)의 상승은 나이 자체가 아니라 "
              "재건축/재개발 호재가 실제 등록(발표)된 지역인지에 좌우된다",
        method=f"연식 {age_threshold}년 이상 단지만 추려, config/catalysts.json에 재건축·재개발 "
               "호재가 등록된 지역 vs 그렇지 않은 지역의 상승률 분포를 Mann-Whitney U 검정 "
               "(rank-biserial 효과크기로 [-1,1] 환산, 다른 가설의 rho와 같은 방식으로 판정)",
        expected_sign=1,
        caveats="호재 등록은 수동 큐레이션이라, 실제로는 호재가 있는데 config에 반영 안 된 지역이 "
                "'호재없음'으로 잘못 분류될 수 있음 — 이 검정은 config의 최신성에 의존적.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    end = df["deal_date"].max()
    mid = end - pd.DateOffset(months=months // 2)

    keys = ["region_code", "apt_name", "area_bucket"]
    recent = df[df["deal_date"] > mid]
    prior = df[df["deal_date"] <= mid]
    r = recent.groupby(keys).agg(recent_ppp=("price_per_pyeong", "median"),
                                  recent_n=("price_per_pyeong", "count"),
                                  build_year=("build_year", "max"))
    p = prior.groupby(keys).agg(prior_ppp=("price_per_pyeong", "median"),
                                 prior_n=("price_per_pyeong", "count"))
    g = r.join(p, how="inner").reset_index()
    g = g[(g["recent_n"] >= min_deals) & (g["prior_n"] >= min_deals)
          & g["build_year"].notna() & (g["build_year"] > 1900)]
    if g.empty:
        return _empty_result(**meta)
    g["growth_%"] = (g["recent_ppp"] - g["prior_ppp"]) / g["prior_ppp"] * 100
    g["age"] = date.today().year - g["build_year"]

    old = g[g["age"] >= age_threshold]
    catalyst_regions = _load_redevelopment_catalyst_regions()
    has_catalyst = old["region_code"].isin(catalyst_regions)
    group_c = old.loc[has_catalyst, "growth_%"]
    group_n = old.loc[~has_catalyst, "growth_%"]
    if len(group_c) < 2 or len(group_n) < 2:
        return _empty_result(**meta)

    # mannwhitneyu(x, y)의 U는 "x_i > y_j인 쌍의 수"(U1) 기준이므로,
    # x(group_c)가 y(group_n)보다 체계적으로 크면 U1 -> n1*n2(최대)가 되고
    # rank-biserial r = 2*U1/(n1*n2) - 1 은 +1에 가까워진다 (양수 = group_c가 더 큼).
    u_stat, _ = mannwhitneyu(group_c, group_n, alternative="two-sided")
    n1, n2 = len(group_c), len(group_n)
    rank_biserial = (2 * u_stat) / (n1 * n2) - 1

    result = HypothesisResult(statistic=float(rank_biserial), n=len(old), **meta)
    result.caveats += (f" | 호재등록지역 중위상승률={group_c.median():.2f}%(n={n1}) vs "
                        f"미등록지역 중위상승률={group_n.median():.2f}%(n={n2})")
    return result


# ─── 2. 거래량 선행지표 ─────────────────────────────────────────────
def test_volume_leads_price(months: int = 60) -> HypothesisResult:
    meta = dict(
        id="volume_leads_price",
        title="거래량 선행지표",
        claim="이번 달 거래량이 늘면(줄면) 다음 달 가격이 오른다(내린다) — 거래량이 가격을 선행한다",
        method=f"시군구×월 단위, 최근 {months}개월. 거래량 전월대비 변화율(t) vs "
               "평당가 전월대비 변화율(t+1)의 Spearman 상관 (시군구별 시차 적용)",
        expected_sign=1,
        caveats="동시성(같은 달 거래량↔가격) 상관과 섞여있을 수 있음 — 별도로 동시성 상관도 "
                "함께 계산해 caveats에 병기. 지역 규모가 작으면 월별 거래량 변동이 노이즈일 수 있음.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M")
    g = df.groupby(["region_code", "ym"]).agg(
        volume=("deal_amount", "count"),
        ppp=("price_per_pyeong", "median"),
    ).reset_index().sort_values(["region_code", "ym"])

    g["vol_chg"] = g.groupby("region_code")["volume"].pct_change()
    g["price_chg"] = g.groupby("region_code")["ppp"].pct_change()
    g["price_chg_next"] = g.groupby("region_code")["price_chg"].shift(-1)

    lead = g[["vol_chg", "price_chg_next"]].replace([np.inf, -np.inf], np.nan).dropna()
    contemp = g[["vol_chg", "price_chg"]].replace([np.inf, -np.inf], np.nan).dropna()

    if lead.empty:
        return _empty_result(**meta)
    rho_lead, _ = spearmanr(lead["vol_chg"], lead["price_chg_next"])
    rho_contemp = (spearmanr(contemp["vol_chg"], contemp["price_chg"])[0]
                   if not contemp.empty else float("nan"))

    result = HypothesisResult(statistic=float(rho_lead), n=len(lead), **meta)
    result.caveats += f" | 참고: 동시성(같은 달) 상관 ρ={rho_contemp:.3f} (n={len(contemp)})"
    return result


# ─── 3. 모멘텀 지속 vs 평균회귀 ─────────────────────────────────────
def test_momentum_vs_reversion(months: int = 60, area_tol: float = 5.0,
                                min_deals: int = 3) -> HypothesisResult:
    meta = dict(
        id="momentum_vs_reversion",
        title="모멘텀 지속 vs 평균회귀",
        claim="최근 많이 오른 단지는 계속 오른다 (모멘텀 지속). "
              "* 반대(평균회귀)라면 최근 많이 오른 단지가 다음 구간엔 덜 오르거나 꺾인다",
        method=f"단지+평형 단위, 최근 {months}개월을 3등분해 "
               "1구간→2구간 상승률과 2구간→3구간 상승률의 Spearman 상관 "
               "(양수=모멘텀 지속, 음수=평균회귀)",
        expected_sign=1,
        caveats="recommend.py의 현재 점수 공식은 tier·prestige(구조적 요인) 중심이라 "
                "이 결과가 음수(평균회귀)로 나와도 기존 점수 산식과 직접 모순되는 것은 아님 — "
                "다만 '과거 상승률'을 참고 지표로 표시하는 UI 문구는 재검토 필요.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df = _bucketize(df, area_tol)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    end = df["deal_date"].max()
    third = months // 3
    if third < 1:
        return _empty_result(**meta)
    p3 = end
    p2 = end - pd.DateOffset(months=third)
    p1 = end - pd.DateOffset(months=third * 2)
    p0 = end - pd.DateOffset(months=third * 3)

    keys = ["region_code", "apt_name", "area_bucket"]

    def _seg_median(lo, hi, name):
        seg = df[(df["deal_date"] > lo) & (df["deal_date"] <= hi)]
        return seg.groupby(keys).agg(**{
            f"{name}_ppp": ("price_per_pyeong", "median"),
            f"{name}_n": ("price_per_pyeong", "count"),
        })

    s0 = _seg_median(p0, p1, "seg0")
    s1 = _seg_median(p1, p2, "seg1")
    s2 = _seg_median(p2, p3, "seg2")
    g = s0.join(s1, how="inner").join(s2, how="inner").reset_index()
    g = g[(g["seg0_n"] >= min_deals) & (g["seg1_n"] >= min_deals) & (g["seg2_n"] >= min_deals)]
    if g.empty:
        return _empty_result(**meta)

    g["growth_a"] = (g["seg1_ppp"] - g["seg0_ppp"]) / g["seg0_ppp"] * 100
    g["growth_b"] = (g["seg2_ppp"] - g["seg1_ppp"]) / g["seg1_ppp"] * 100
    rho, _ = spearmanr(g["growth_a"], g["growth_b"])
    return HypothesisResult(statistic=float(rho), n=len(g), **meta)
