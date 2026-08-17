"""부동산 통념 가설 검증 — "가치평가/밸류에이션" 계열 (전세가율 등).

src/analysis/hypothesis_tests.py 와 같은 패턴(HypothesisResult 반환)이지만
300줄 제한으로 별도 파일로 분리. hypothesis_lab.get_all_hypotheses()에 등록.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from sqlalchemy import select

from src.database.repository import fetch_trades_df, fetch_rents_df, session_scope
from src.database.models import SupplySchedule, PopulationFlow, KbSentimentIndex
from src.analysis.gap_analysis import to_jeonse_equiv
from src.analysis.hypothesis_lab import (HypothesisResult, _empty_result,
                                          region_growth_via_unit_tracking, jeonse_ratio_via_unit_matching)

# supply_schedule은 시/도(2자리) 단위. 실거래 DB에 해당 시/도가 있는 경우만 검증 가능.
SUPPLY_SIDO_NAMES = {"11": "서울", "41": "경기", "28": "인천", "26": "부산"}


# ─── 9. 전세가율 선행 ─────────────────────────────────────────────────
def test_jeonse_ratio_leads_price(months: int = 60, min_deals: int = 5,
                                   area_tol: float = 5.0, min_unit_deals: int = 1) -> HypothesisResult:
    meta = dict(
        id="jeonse_ratio_leads_price",
        title="전세가율 선행",
        claim="전세가율(전세/매매)이 오르면 매매가가 뒤따라 오른다",
        method=f"시군구x월 패널. 같은 단지+평형 유닛에서 그 달 매매·전세가 동시에 관측된 "
               f"경우만 매칭해 전세가율(%) 계산(구성효과 제거) — 이번달 전세가율(t) vs 다음달 "
               f"단지+평형 추적 매매가 성장률(t+1, 구성효과 제거)의 Spearman 상관, 최근 {months}개월",
        expected_sign=1,
        caveats="전세가율이 매매가 상승의 원인이 아니라, 둘 다 같은 시장 심리(매수 관망 시 "
                "전세 수요 증가)의 결과일 수 있어 인과관계로 해석 불가. 투자추천 페이지의 "
                "'전세가율 가속도' 신호와 같은 원천 데이터를 쓰지만, 이 실험실의 검증 방식은 "
                "그 신호와 독립적으로 새로 계산한 것. 전세가율·매매가 성장률 모두 단지+평형 "
                "유닛 단위(구성효과 제거)로 계산 — 같은 유닛에서 매매·전세가 동시에 관측된 "
                "달만 표본이 되므로 원시 지역 median 방식보다 표본이 적을 수 있음.",
    )
    df_trade = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    df_rent = fetch_rents_df(date_from=date.today() - timedelta(days=30 * months))
    if df_trade.empty or df_rent.empty:
        return _empty_result(**meta)

    df_trade = df_trade.copy()
    growth_g = region_growth_via_unit_tracking(df_trade, ["region_code"], area_tol, min_unit_deals)

    df_rent = to_jeonse_equiv(df_rent)
    df_rent["ppp"] = df_rent["jeonse_equiv"] / df_rent["area_m2"] * 3.3058
    ratio_g = jeonse_ratio_via_unit_matching(df_trade, df_rent, ["region_code"], area_tol)
    ratio_g = ratio_g[ratio_g["n"] >= min_deals]
    if ratio_g.empty:
        return _empty_result(**meta)

    ratio_df = ratio_g[["region_code", "ym", "jeonse_ratio"]].dropna().copy()
    ratio_df["ym"] = ratio_df["ym"] + 1  # t시점 전세가율을 t+1시점 라벨로 이동(선행 정렬)
    growth_df = growth_g[["region_code", "ym", "growth"]].dropna()

    merged = growth_df.merge(ratio_df, on=["region_code", "ym"], how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["jeonse_ratio"], merged["growth"])
    explored = (
        "2026-08-17 다음 변형들을 실DB로 시도했으나 전부 결론(음의 상관, 기각) 안 바뀜 — "
        "재시도 의미 없음: "
        "①시차 1~12개월 스캔(전부 rho -0.13~-0.19), "
        "②누적 3/6/12개월 평균 전세가율(윈도우 늘릴수록 오히려 더 강한 음수, -0.19→-0.25), "
        "③인구 순유입 지역 필터(순유입 -0.196 vs 순유출 -0.204, 차이 없음), "
        "④입주물량 필터(적음 -0.274 vs 많음 -0.115 — 이론과 반대로 공급 적을 때 더 강한 음수), "
        "⑤규제완화기 vs 강화기(완화기 -0.300 vs 강화기 -0.166 — 매수전환 열린 시기에 더 강한 음수). "
        "④⑤는 '규제완화=매매약세 국면의 대응'이라는 confound로 설명 가능 — 전세가율은 "
        "선행지표가 아니라 매매약세의 후행/동행 결과일 가능성에 무게."
    )
    return HypothesisResult(statistic=float(rho), n=len(merged), explored=explored, **meta)


# ─── 10. 입주물량(공급과잉) 효과 ───────────────────────────────────────
def test_supply_leads_price_decline(months: int = 60, area_tol: float = 5.0,
                                     min_unit_deals: int = 1) -> HypothesisResult:
    sido_label = "·".join(SUPPLY_SIDO_NAMES.values())
    meta = dict(
        id="supply_glut",
        title=f"입주물량(공급과잉) 효과 (시/도 단위: {sido_label})",
        claim="입주물량이 몰리는 시기·지역일수록 가격이 하락한다",
        method=f"시/도 단위({sido_label}) 월별 입주물량(supply_schedule, KOSIS 실적)과 단지+평형 "
               f"추적 매매가 성장률(구성효과 제거)을 시/도로 집계 — 이번달 입주물량(t) vs 다음달 "
               f"가격 변화율(t+1)의 Spearman 상관, 최근 {months}개월. 음수면 공급 많을수록 "
               "다음달 덜 오른다는 뜻(가설 지지)",
        expected_sign=-1,
        caveats="supply_schedule은 시/도(광역) 단위라 시군구 세부 공급 편차를 반영 못함. "
                "원천 KOSIS 수집기는 이미 폐기돼(API 응답 문제로 이번 세션에 삭제) 2026-03 "
                "이후 데이터는 갱신되지 않음. 실거래 DB에 있는 4개 광역으로만 검증 가능. "
                "지역 전체 중위가 기준 성장률은 KB 공식 가격지수와 상관이 거의 없었음(rho=-0.1 "
                "안팎) — 단지+평형 추적 방식으로 성장률을 계산해 구성효과를 줄임.",
    )
    df_trade = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df_trade.empty:
        return _empty_result(**meta)
    df_trade = df_trade.copy()
    df_trade["sido"] = df_trade["region_code"].str[:2]
    df_trade = df_trade[df_trade["sido"].isin(SUPPLY_SIDO_NAMES)]
    if df_trade.empty:
        return _empty_result(**meta)
    trade_g = region_growth_via_unit_tracking(df_trade, ["sido"], area_tol, min_unit_deals)
    if trade_g.empty:
        return _empty_result(**meta)

    with session_scope() as s:
        rows = s.execute(select(SupplySchedule.region_code, SupplySchedule.move_in_date,
                                 SupplySchedule.units)).all()
    supply_df = pd.DataFrame(rows, columns=["sido", "move_in_date", "units"])
    supply_df = supply_df[supply_df["sido"].isin(SUPPLY_SIDO_NAMES)]
    if supply_df.empty:
        return _empty_result(**meta)
    supply_df = supply_df.copy()
    supply_df["ym"] = pd.to_datetime(supply_df["move_in_date"]).dt.to_period("M")
    supply_g = supply_df.groupby(["sido", "ym"])["units"].sum().reset_index()
    supply_g["ym"] = supply_g["ym"] + 1  # 이번달 입주물량을 다음달 라벨로 이동(선행 정렬)

    growth_df = trade_g[["sido", "ym", "growth"]].dropna()
    merged = growth_df.merge(supply_g, on=["sido", "ym"], how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["units"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)


# ─── 11. 인구이동 선행 ─────────────────────────────────────────────────
def test_population_migration_leads_price(months: int = 60, area_tol: float = 5.0,
                                            min_unit_deals: int = 1) -> HypothesisResult:
    meta = dict(
        id="population_migration",
        title="인구이동 선행",
        claim="순유입 인구가 늘어나는 지역일수록 가격이 먼저 오른다",
        method=f"시군구x월 패널. population_flow의 순유입(전입-전출)과 단지+평형 추적 매매가 "
               f"성장률(구성효과 제거) — 이번달 순유입(t) vs 다음달 가격 변화율(t+1)의 "
               f"Spearman 상관, 최근 {months}개월",
        expected_sign=1,
        caveats="population_flow는 2021-08부터 시작(2024-05 이전 구간은 이번 세션에 KOSIS API로 "
                "추가 백필) — 다른 5년치 가설보다는 데이터 이력이 짧음. 순유입이 가격을 미는 게 "
                "아니라 이미 오르는 지역으로 사람이 몰리는 역방향 인과일 수 있어 해석 주의. "
                "지역 전체 중위가 기준 성장률 대신 단지+평형 추적 방식(구성효과 제거)으로 계산.",
    )
    df_trade = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df_trade.empty:
        return _empty_result(**meta)
    trade_g = region_growth_via_unit_tracking(df_trade, ["region_code"], area_tol, min_unit_deals)
    if trade_g.empty:
        return _empty_result(**meta)

    with session_scope() as s:
        rows = s.execute(select(PopulationFlow.region_code, PopulationFlow.flow_date,
                                 PopulationFlow.net_inflow)).all()
    flow_df = pd.DataFrame(rows, columns=["region_code", "flow_date", "net_inflow"])
    if flow_df.empty:
        return _empty_result(**meta)
    flow_df = flow_df.copy()
    flow_df["ym"] = pd.to_datetime(flow_df["flow_date"]).dt.to_period("M")
    flow_g = flow_df.groupby(["region_code", "ym"])["net_inflow"].sum().reset_index()
    flow_g["ym"] = flow_g["ym"] + 1  # 이번달 순유입을 다음달 라벨로 이동(선행 정렬)

    growth_df = trade_g[["region_code", "ym", "growth"]].dropna()
    merged = growth_df.merge(flow_g, on=["region_code", "ym"], how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["net_inflow"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)


# ─── 12. KB 매수우위지수 선행 ───────────────────────────────────────────
def test_buyer_sentiment_leads_price(months: int = 60, area_tol: float = 5.0,
                                      min_unit_deals: int = 1) -> HypothesisResult:
    sido_label = "·".join(SUPPLY_SIDO_NAMES.values())
    meta = dict(
        id="buyer_sentiment_leads_price",
        title=f"KB 매수우위지수 선행 (시/도 단위: {sido_label})",
        claim="KB 매수우위지수가 높은 시/도일수록 다음달 가격이 더 오른다",
        method=f"시/도 단위({sido_label}) 월별 KB 매수우위지수(KB부동산 데이터허브)와 단지+평형 "
               f"추적 매매가 성장률(구성효과 제거)을 시/도로 집계 — 이번달 매수우위지수(t) vs "
               f"다음달 가격 변화율(t+1)의 Spearman 상관, 최근 {months}개월",
        expected_sign=1,
        caveats="recommend.py의 자체 매수심리 proxy(_buyer_sentiment_signals)와는 별개 지표 — "
                "이건 KB가 공인중개사 설문으로 직접 발표하는 실제 지수, 자체 proxy와의 정확도 "
                "비교는 하지 않음(별도 가설로 가능). 시/도 단위라 해상도 거침(supply_glut과 동일한 한계). "
                "지역 전체 중위가 기준으로 계산했을 땐 KB 가격 기준 재현 버전(buyer_sentiment_"
                "leads_price_kb)과 정반대 결론이 나왔었음 — 단지+평형 추적으로 성장률을 다시 계산.",
    )
    df_trade = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df_trade.empty:
        return _empty_result(**meta)
    df_trade = df_trade.copy()
    df_trade["sido"] = df_trade["region_code"].str[:2]
    df_trade = df_trade[df_trade["sido"].isin(SUPPLY_SIDO_NAMES)]
    if df_trade.empty:
        return _empty_result(**meta)
    trade_g = region_growth_via_unit_tracking(df_trade, ["sido"], area_tol, min_unit_deals)
    if trade_g.empty:
        return _empty_result(**meta)

    with session_scope() as s:
        rows = s.execute(select(KbSentimentIndex.region_code, KbSentimentIndex.ym_date,
                                 KbSentimentIndex.sentiment_index)).all()
    sent_df = pd.DataFrame(rows, columns=["sido", "ym_date", "sentiment_index"])
    sent_df = sent_df[sent_df["sido"].isin(SUPPLY_SIDO_NAMES)]
    if sent_df.empty:
        return _empty_result(**meta)
    sent_df = sent_df.copy()
    sent_df["ym"] = pd.to_datetime(sent_df["ym_date"]).dt.to_period("M")
    sent_g = sent_df.groupby(["sido", "ym"])["sentiment_index"].mean().reset_index()
    sent_g["ym"] = sent_g["ym"] + 1  # 이번달 지수를 다음달 라벨로 이동(선행 정렬)

    growth_df = trade_g[["sido", "ym", "growth"]].dropna()
    merged = growth_df.merge(sent_g, on=["sido", "ym"], how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["sentiment_index"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)
