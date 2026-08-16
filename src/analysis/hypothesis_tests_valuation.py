"""부동산 통념 가설 검증 — "가치평가/밸류에이션" 계열 (전세가율 등).

src/analysis/hypothesis_tests.py 와 같은 패턴(HypothesisResult 반환)이지만
300줄 제한으로 별도 파일로 분리. hypothesis_lab.get_all_hypotheses()에 등록.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.database.repository import fetch_trades_df, fetch_rents_df
from src.analysis.gap_analysis import to_jeonse_equiv
from src.analysis.hypothesis_lab import HypothesisResult, _empty_result


# ─── 9. 전세가율 선행 ─────────────────────────────────────────────────
def test_jeonse_ratio_leads_price(months: int = 60, min_deals: int = 5) -> HypothesisResult:
    meta = dict(
        id="jeonse_ratio_leads_price",
        title="전세가율 선행",
        claim="전세가율(전세/매매)이 오르면 매매가가 뒤따라 오른다",
        method=f"시군구x월 패널. 전세(월세 포함, 전세환산금액=보증금+월세x100)의 평당가와 "
               f"매매 평당가로 전세가율(%) 계산 — 이번달 전세가율(t) vs 다음달 매매가 "
               f"변화율(t+1)의 Spearman 상관, 최근 {months}개월",
        expected_sign=1,
        caveats="전세가율이 매매가 상승의 원인이 아니라, 둘 다 같은 시장 심리(매수 관망 시 "
                "전세 수요 증가)의 결과일 수 있어 인과관계로 해석 불가. 투자추천 페이지의 "
                "'전세가율 가속도' 신호와 같은 원천 데이터를 쓰지만, 이 실험실의 검증 방식은 "
                "그 신호와 독립적으로 새로 계산한 것.",
    )
    df_trade = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    df_rent = fetch_rents_df(date_from=date.today() - timedelta(days=30 * months))
    if df_trade.empty or df_rent.empty:
        return _empty_result(**meta)

    df_trade = df_trade.copy()
    df_trade["ym"] = pd.to_datetime(df_trade["deal_date"]).dt.to_period("M")
    trade_g = df_trade.groupby(["region_code", "ym"]).agg(
        trade_ppp=("price_per_pyeong", "median"), trade_n=("price_per_pyeong", "count")
    ).reset_index()

    df_rent = to_jeonse_equiv(df_rent)
    df_rent["ppp"] = df_rent["jeonse_equiv"] / df_rent["area_m2"] * 3.3058
    df_rent["ym"] = pd.to_datetime(df_rent["deal_date"]).dt.to_period("M")
    rent_g = df_rent.groupby(["region_code", "ym"]).agg(
        rent_ppp=("ppp", "median"), rent_n=("ppp", "count")
    ).reset_index()

    g = trade_g.merge(rent_g, on=["region_code", "ym"], how="inner")
    g = g[(g["trade_n"] >= min_deals) & (g["rent_n"] >= min_deals)].sort_values(["region_code", "ym"])
    if g.empty:
        return _empty_result(**meta)
    g["jeonse_ratio"] = g["rent_ppp"] / g["trade_ppp"] * 100
    g["growth"] = g.groupby("region_code")["trade_ppp"].pct_change()

    ratio_df = g[["region_code", "ym", "jeonse_ratio"]].dropna().copy()
    ratio_df["ym"] = ratio_df["ym"] + 1  # t시점 전세가율을 t+1시점 라벨로 이동(선행 정렬)
    growth_df = g[["region_code", "ym", "growth"]].dropna()

    merged = growth_df.merge(ratio_df, on=["region_code", "ym"], how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["jeonse_ratio"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)
