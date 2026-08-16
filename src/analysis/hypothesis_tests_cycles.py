"""부동산 통념 가설 검증 — "순환/사이클" 계열 (선도-추종, 평형 순환, 가격수준 회귀).

src/analysis/hypothesis_tests.py 와 같은 패턴(HypothesisResult 반환)이지만
300줄 제한으로 별도 파일로 분리. hypothesis_lab.get_all_hypotheses()에 등록.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.database.repository import fetch_trades_df
from src.analysis.hypothesis_lab import HypothesisResult, _empty_result, reindex_monthly

LEADER_REGION = "11680"  # 강남구


# ─── 4. 순환매(키맞추기) 효과 ────────────────────────────────────────
def test_seoul_leads_other_regions(months: int = 60, leader_region: str = LEADER_REGION,
                                    min_deals: int = 5) -> HypothesisResult:
    meta = dict(
        id="region_leadlag",
        title="순환매(키맞추기) 효과",
        claim="강남(선도지역) 가격이 오르면, 시차를 두고 다른 지역들도 따라 오른다",
        method=f"시군구x월 평당가 변화율. 강남구(11680) 이번달 변화율(t) vs 다른 지역들의 "
               f"다음달 변화율(t+1, 지역간 중앙값으로 집계)의 Spearman 상관, 최근 {months}개월",
        expected_sign=1,
        caveats="강남 하나만 선도지역으로 가정 — 실제론 여러 상급지가 동시에 선도할 수 있음. "
                "전국 동시 매크로 충격(금리·정책)이 있으면 진짜 '선도-추종'이 아니라 동시반응일 수 있음. "
                "n은 '월' 단위 독립 관측치 수 — 지역별로 뻥튀기하지 않음(강남 변화율 하나를 "
                "그 달 모든 지역에 복제하면 가짜로 표본이 커져 통계 검정력이 과대평가됨).",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M")
    g = df.groupby(["region_code", "ym"]).agg(
        ppp=("price_per_pyeong", "median"), n=("price_per_pyeong", "count")
    ).reset_index()
    g = reindex_monthly(g, ["region_code"], "ym").sort_values(["region_code", "ym"])
    g.loc[g["n"] < min_deals, "ppp"] = float("nan")  # 결측월과 동일하게 취급해 pct_change가 건너뜀
    g["chg"] = g.groupby("region_code")["ppp"].pct_change()

    leader = g[g["region_code"] == leader_region][["ym", "chg"]].rename(
        columns={"chg": "leader_chg"}).dropna().copy()
    if leader.empty:
        return _empty_result(**meta)
    leader["ym"] = leader["ym"] + 1  # 직전월 강남 변화율을 이번월 라벨로 이동(선행 정렬)

    # 지역별로 각각 짝지으면 같은 달 leader_chg 하나가 수십 개 지역에 복제돼 표본이
    # 가짜로 부풀려짐(pseudo-replication) -> 월별 중앙값 하나로 집계해 "월"을 관측 단위로 삼는다.
    followers = g[g["region_code"] != leader_region][["ym", "chg"]].dropna()
    follower_monthly = followers.groupby("ym")["chg"].median().reset_index()
    merged = follower_monthly.merge(leader, on="ym", how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["leader_chg"], merged["chg"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)


# ─── 5. 평형별 순환 (큰 평형 선행) ────────────────────────────────────
def test_large_units_lead_small_units(months: int = 60, area_threshold: float = 85.0,
                                       min_deals: int = 5) -> HypothesisResult:
    meta = dict(
        id="size_rotation",
        title="평형별 순환 (큰 평형 선행)",
        claim=f"큰 평형({area_threshold}㎡ 이상)이 먼저 오르고, 작은 평형이 시차를 두고 따라 오른다",
        method=f"지역x평형그룹(대/소)x월 평당가 변화율. 같은 지역의 큰 평형 이번달 변화율(t) vs "
               f"작은 평형 다음달 변화율(t+1)의 Spearman 상관, 최근 {months}개월",
        expected_sign=1,
        caveats="평형 컷을 85㎡ 하나로 단순화. 반대 방향(소형·실수요가 먼저 움직인다)을 주장하는 "
                "통념도 있어 부호가 반대로 나올 수 있음.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df = df.copy()
    df["size_class"] = np.where(df["area_m2"] >= area_threshold, "large", "small")
    df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M")
    g = df.groupby(["region_code", "size_class", "ym"]).agg(
        ppp=("price_per_pyeong", "median"), n=("price_per_pyeong", "count")
    ).reset_index()
    g = reindex_monthly(g, ["region_code", "size_class"], "ym").sort_values(
        ["region_code", "size_class", "ym"])
    g.loc[g["n"] < min_deals, "ppp"] = float("nan")
    g["chg"] = g.groupby(["region_code", "size_class"])["ppp"].pct_change()

    large = g[g["size_class"] == "large"][["region_code", "ym", "chg"]].rename(
        columns={"chg": "large_chg"}).dropna().copy()
    small = g[g["size_class"] == "small"][["region_code", "ym", "chg"]].rename(
        columns={"chg": "small_chg"}).dropna()
    if large.empty or small.empty:
        return _empty_result(**meta)
    large["ym"] = large["ym"] + 1

    merged = small.merge(large, on=["region_code", "ym"], how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["large_chg"], merged["small_chg"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)


# ─── 6. 저가 매수(갭메우기) 재확인 ────────────────────────────────────
def test_price_level_mean_reversion(months: int = 60, min_deals: int = 20) -> HypothesisResult:
    meta = dict(
        id="price_level_reversion",
        title="저가 매수(갭메우기) 효과",
        claim="평당가가 낮은(저평가) 지역일수록 격차를 메우며 이후 상승률이 더 높다",
        method=f"시군구 단위, 최근 {months}개월을 반으로 나눠 전반기 평당가 수준과 "
               "후반기 상승률의 Spearman 상관 — 음수면 저가 지역이 더 오른다는 뜻(가설 지지)",
        expected_sign=-1,
        caveats="이 프로젝트 개발 히스토리(사이드바 '개발 히스토리')에 저평가 가설은 이미 "
                "데이터로 기각됐다고 기록돼 있음 — 이번 결과는 다른 방법론(시군구 단위 "
                "Spearman)으로도 같은 결론이 재현되는지 확인하는 성격.",
    )
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return _empty_result(**meta)
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    end = df["deal_date"].max()
    mid = end - pd.DateOffset(months=months // 2)
    prior = df[df["deal_date"] <= mid]
    recent = df[df["deal_date"] > mid]
    p = prior.groupby("region_code").agg(prior_ppp=("price_per_pyeong", "median"),
                                          prior_n=("price_per_pyeong", "count"))
    r = recent.groupby("region_code").agg(recent_ppp=("price_per_pyeong", "median"),
                                           recent_n=("price_per_pyeong", "count"))
    g = p.join(r, how="inner").reset_index()
    g = g[(g["prior_n"] >= min_deals) & (g["recent_n"] >= min_deals)]
    if len(g) < 2:
        return _empty_result(**meta)
    g["growth_%"] = (g["recent_ppp"] - g["prior_ppp"]) / g["prior_ppp"] * 100
    rho, _ = spearmanr(g["prior_ppp"], g["growth_%"])
    return HypothesisResult(statistic=float(rho), n=len(g), **meta)


# ─── 7. 규제발 풍선효과 (다중 이벤트 반복성 검증) ────────────────────────
# 이벤트/지역 출처: 국토교통부 대책 발표 + 경기신문·아시아투데이·나무위키 교차검증(2026-08 기준)
GANGNAM4 = {"11680", "11650", "11710", "11170"}          # 강남·서초·송파·용산 — 5년 내내 규제 유지
GG_CORE_5 = {"41290", "41135", "41131", "41450", "41210"}  # 과천·분당·수정·하남·광명
GG_2025_NEW = {"41117", "41111", "41115", "41173", "41465", "41430"}  # 수원3구·안양동안·용인수지·의왕
GG_2026_NEW = {"41597", "41463", "41310"}  # 화성동탄·용인기흥·구리

REGULATION_EVENTS = [
    {"date": "2022-11-14", "direction": "완화",
     "note": "경기 대부분 규제 해제 (서울 전역+과천·분당·수정·하남·광명만 유지)"},
    {"date": "2023-01-05", "direction": "완화",
     "note": "서울 21개구+경기 5곳(과천 등) 추가 해제 (강남3구·용산만 유지)"},
    {"date": "2025-10-16", "direction": "강화",
     "note": "서울 전역+경기 6곳(수원3구·안양동안·용인수지·의왕) 재지정"},
    {"date": "2026-06-30", "direction": "강화",
     "note": "화성 동탄·용인 기흥·구리 신규 규제"},
]


def _shock_and_stable_regions(all_regions: set, event_date: str) -> tuple[set, set]:
    """이벤트 날짜에 규제 상태가 바뀐(shock) 지역과 안 바뀐(stable) 지역 코드 집합.

    비교 대상은 수도권(서울·경기·인천)으로 한정한다. DB에 섞여 있는 부산 등
    비수도권 지역은 서울발 규제와 자금 이동 관계가 없어 애초에 후보군에서 제외.
    """
    seoul = {c for c in all_regions if c.startswith("11")}
    gg = {c for c in all_regions if c.startswith("41")}
    incheon = {c for c in all_regions if c.startswith("28")}
    capital_area = seoul | gg | incheon
    if event_date == "2022-11-14":
        shock = gg - GG_CORE_5
    elif event_date == "2023-01-05":
        shock = (seoul - GANGNAM4) | (GG_CORE_5 & all_regions)
    elif event_date == "2025-10-16":
        shock = (seoul - GANGNAM4) | (GG_2025_NEW & all_regions)
    elif event_date == "2026-06-30":
        shock = GG_2026_NEW & all_regions
    else:
        return set(), set()
    return shock, capital_area - shock


def _growth_pct(df: pd.DataFrame, regions: set, start: pd.Timestamp, end: pd.Timestamp,
                 min_deals: int) -> float | None:
    sub = df[df["region_code"].isin(regions) & (df["deal_date"] >= start) & (df["deal_date"] < end)]
    if len(sub) < min_deals:
        return None
    return float(sub["price_per_pyeong"].median())


def test_regulation_balloon_effect(months_before: int = 6, months_after: int = 6,
                                    min_deals: int = 5) -> HypothesisResult:
    meta = dict(
        id="regulation_balloon",
        title="규제발 풍선효과 (수도권: 서울·경기·인천)",
        claim="한 지역이 규제로 묶이거나 풀리면, 나머지 지역들의 상승률이 반대 방향으로 움직인다(자금 재배치)",
        method=f"국토부 규제지역 지정·해제 이벤트 {len(REGULATION_EVENTS)}건마다, 상태가 바뀐 지역들의 "
               f"평당가 증감률(전후 각 {months_before}/{months_after}개월)과 안 바뀐 나머지 지역들의 "
               "증감률(지역간 중앙값)을 이벤트 하나당 관측치 하나로 집계해 Spearman 상관. "
               "음의 상관이면 두 그룹이 반대로 움직인다는 뜻(가설 지지)",
        expected_sign=-1,
        caveats="이벤트가 서로 독립적인 반복이 아니라 2022~2023년 완화 국면과 2025~2026년 강화 국면, "
                "사실상 두 사이클뿐 — '매번 반복' 주장은 이 4건 한정. 동시기 금리 등 거시 변수와 "
                "혼재 가능해 인과관계 증명 아님. 2026-06-30 이벤트는 DB에 이후 데이터가 부족하면 "
                "자동으로 통계에서 제외되고, 데이터가 쌓이면 재검증 시 자동 반영됨. n은 이벤트 개수 "
                "(현재 3~4건)로, 안 바뀐 지역 수만큼 뻥튀기하지 않음 — 표본이 원래 매우 작은 "
                "검정이라 MIN_N 미만이면 정직하게 '표본부족'으로 판정됨.",
    )
    df = fetch_trades_df()
    if df.empty:
        return _empty_result(**meta)
    df = df.copy()
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    all_regions = set(df["region_code"].unique())

    shock_deltas, stable_deltas, breakdown = [], [], {}
    for ev in REGULATION_EVENTS:
        event_dt = pd.Timestamp(ev["date"])
        before_start = event_dt - pd.DateOffset(months=months_before)
        after_end = event_dt + pd.DateOffset(months=months_after)
        shock_regions, stable_regions = _shock_and_stable_regions(all_regions, ev["date"])
        if not shock_regions or not stable_regions:
            continue

        shock_before = _growth_pct(df, shock_regions, before_start, event_dt, min_deals)
        shock_after = _growth_pct(df, shock_regions, event_dt, after_end, min_deals)
        if shock_before is None or shock_after is None:
            continue
        shock_delta = (shock_after - shock_before) / shock_before * 100

        candidates = []
        region_deltas = []
        for region in sorted(stable_regions):
            b = _growth_pct(df, {region}, before_start, event_dt, min_deals)
            a = _growth_pct(df, {region}, event_dt, after_end, min_deals)
            if b is None or a is None:
                continue
            delta = (a - b) / b * 100
            region_deltas.append(delta)
            candidates.append({"region_code": region, "delta_%": round(delta, 2)})

        if not region_deltas:
            continue
        # 이벤트당 관측치 하나만 남긴다(대조군의 중앙값) — 지역 수만큼 반복 추가하면
        # 같은 이벤트의 거시 충격을 여러 개의 독립 표본인 것처럼 취급하는 가짜 표본크기 문제가 생김.
        shock_deltas.append(shock_delta)
        stable_deltas.append(float(np.median(region_deltas)))

        candidates.sort(key=lambda c: c["delta_%"], reverse=(ev["direction"] == "강화"))
        breakdown[ev["date"]] = {
            "note": ev["note"],
            "shock_delta_%": round(shock_delta, 2),
            "top_후보": candidates[:3],
        }

    if len(shock_deltas) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(shock_deltas, stable_deltas)
    return HypothesisResult(statistic=float(rho), n=len(shock_deltas),
                             breakdown=breakdown or None, **meta)
