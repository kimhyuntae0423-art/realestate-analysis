"""부동산 통념 가설 검증 — 거시경제(한국은행 ECOS) 계열.

src/analysis/hypothesis_tests_kb.py와 같은 패턴이지만 데이터 출처가 KB가 아니라
한국은행 ECOS(M2 통화량 등)라 별도 파일로 분리. hypothesis_lab.get_all_hypotheses()에 등록.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sqlalchemy import select

from src.database.repository import fetch_trades_df, session_scope
from src.database.models import EcosSeries
from src.analysis.hypothesis_lab import HypothesisResult, _empty_result, region_growth_via_unit_tracking

M2_SERIES = "m2_eop_raw"


def _m2_yoy_panel() -> pd.DataFrame:
    """M2(말잔, 원계열) 전국 월별 시계열에서 전년동월대비(YoY) 증가율 패널을 만든다."""
    with session_scope() as s:
        rows = s.execute(
            select(EcosSeries.ym_date, EcosSeries.value)
            .where(EcosSeries.series == M2_SERIES)
        ).all()
    df = pd.DataFrame(rows, columns=["ym_date", "value"])
    if df.empty:
        return pd.DataFrame(columns=["ym", "m2_yoy"])
    df["ym"] = pd.to_datetime(df["ym_date"]).dt.to_period("M")
    df = df.sort_values("ym")
    df["m2_yoy"] = df["value"].pct_change(12)
    return df[["ym", "m2_yoy"]]


# ─── 통화량(M2) 증가 선행 ────────────────────────────────────────────
def test_money_supply_leads_price(months: int = 60) -> HypothesisResult:
    meta = dict(
        id="money_supply_leads_price",
        title="통화량(M2) 증가 선행",
        claim="M2(광의통화) 증가율이 높을수록 다음달 전국 아파트 가격이 더 오른다",
        method=f"한국은행 ECOS M2(말잔, 원계열) 전년동월대비(YoY) 증가율(t) vs 전국 단지+평형 "
               f"추적 매매가 성장률(t+1, 구성효과 제거)의 Spearman 상관, 최근 {months}개월",
        expected_sign=1,
        caveats="M2는 지역 구분 없는 국가 단위 지표라 전국 평균 가격과만 비교 가능 — 지역별 "
                "차이(수도권 vs 지방)는 이 검정으로 알 수 없음. 국가 단위 월별 시계열이라 "
                "표본(n)이 다른 가설(지역×월 패널)보다 훨씬 작음 — 표본부족 판정이 나오기 쉬움. "
                "통화량 증가가 자산가격에 반영되는 데는 이론상 시차가 있을 수 있어 1개월 지연은 "
                "과소평가일 가능성 — 다른 시차는 추후 explored로 탐색 예정.",
    )
    df_trade = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df_trade.empty:
        return _empty_result(**meta)

    price_g = region_growth_via_unit_tracking(df_trade, group_cols=[])
    if price_g.empty:
        return _empty_result(**meta)
    price_g = price_g[["ym", "growth"]].dropna()

    m2 = _m2_yoy_panel().dropna(subset=["m2_yoy"])
    if m2.empty:
        return _empty_result(**meta)
    m2 = m2.copy()
    m2["ym"] = m2["ym"] + 1  # t시점 M2 증가율을 t+1시점 라벨로 이동(선행 정렬)

    merged = price_g.merge(m2, on="ym", how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["m2_yoy"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)
