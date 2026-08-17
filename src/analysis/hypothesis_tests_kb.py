"""부동산 통념 가설 검증 — KB 가격 시계열 교차검증 계열.

src/analysis/hypothesis_tests_valuation.py의 입주물량/매수심리 가설과 신호는
동일하지만, "가격" 쪽을 우리가 실거래로 직접 계산한 ppp 대신 KB부동산
데이터허브가 공식 발표하는 중위가격으로 바꿔 재현한다. 신호와 결과의 출처를
완전히 분리해(KOSIS/KB 신호 vs KB 가격) 우리 ppp 계산 자체의 노이즈가
양쪽에 동시에 스며드는 걸 피하는 교차검증 — 300줄 제한으로 별도 파일 분리.
hypothesis_lab.get_all_hypotheses()에 등록.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sqlalchemy import select

from src.database.repository import session_scope
from src.database.models import SupplySchedule, KbSentimentIndex, KbPriceSeries
from src.analysis.hypothesis_lab import HypothesisResult, _empty_result, reindex_monthly
from src.analysis.hypothesis_tests_valuation import SUPPLY_SIDO_NAMES

KB_PRICE_SERIES = "median_price_apt_sale"


def _kb_price_growth_panel() -> pd.DataFrame:
    """KB 시/도 단위 중위가격 시계열에서 지역x월 상승률(growth) 패널을 만든다."""
    with session_scope() as s:
        rows = s.execute(
            select(KbPriceSeries.region_code, KbPriceSeries.ym_date, KbPriceSeries.value)
            .where(KbPriceSeries.series == KB_PRICE_SERIES)
        ).all()
    df = pd.DataFrame(rows, columns=["sido", "ym_date", "value"])
    if df.empty:
        return df
    df["ym"] = pd.to_datetime(df["ym_date"]).dt.to_period("M")
    g = df.groupby(["sido", "ym"])["value"].mean().reset_index()
    g = reindex_monthly(g, ["sido"], "ym").sort_values(["sido", "ym"])
    g["growth"] = g.groupby("sido")["value"].pct_change()
    return g


# ─── 13. 입주물량(공급과잉) 효과 — KB 가격 기준 ─────────────────────────
def test_supply_leads_price_decline_kb() -> HypothesisResult:
    sido_label = "·".join(SUPPLY_SIDO_NAMES.values())
    meta = dict(
        id="supply_glut_kb_price",
        title=f"입주물량(공급과잉) 효과 — KB 가격 기준 (시/도: {sido_label})",
        claim="입주물량이 몰리는 시기·지역일수록 KB 중위가격 기준으로도 다음달 가격이 덜 오른다",
        method="시/도 단위 월별 입주물량(supply_schedule, KOSIS 실적) vs 다음달 KB 중위가격 "
               "변화율의 Spearman 상관 — supply_glut(우리 ppp 기준)의 KB 가격판 재현",
        expected_sign=-1,
        caveats="supply_glut과 신호(공급)는 동일, 가격만 KB 공식 중위가격으로 교체한 교차검증. "
                "결과가 같으면 신뢰도 강화, 다르면 원래 가설의 ppp 계산(구성 효과 등 노이즈) "
                "재검토 필요. KB 가격은 시/도 단위 집계값이라 우리 ppp보다 해상도는 낮지만 "
                "표본구성 변화(어떤 단지가 팔렸는지)에 덜 민감함.",
    )
    growth_df = _kb_price_growth_panel()
    if growth_df.empty:
        return _empty_result(**meta)
    growth_df = growth_df[["sido", "ym", "growth"]].dropna()

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

    merged = growth_df.merge(supply_g, on=["sido", "ym"], how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["units"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)


# ─── 14. KB 매수우위지수 선행 — KB 가격 기준 ────────────────────────────
def test_buyer_sentiment_leads_price_kb() -> HypothesisResult:
    sido_label = "·".join(SUPPLY_SIDO_NAMES.values())
    meta = dict(
        id="buyer_sentiment_leads_price_kb",
        title=f"KB 매수우위지수 선행 — KB 가격 기준 (시/도: {sido_label})",
        claim="KB 매수우위지수가 높은 시/도일수록 KB 중위가격 기준으로도 다음달 가격이 더 오른다",
        method="시/도 단위 월별 KB 매수우위지수 vs 다음달 KB 중위가격 변화율의 Spearman 상관 — "
               "신호·가격 전부 KB 공식 통계로만 구성된 순수 KB 내부 검증 (우리 실거래 데이터 "
               "전혀 안 씀)",
        expected_sign=1,
        caveats="buyer_sentiment_leads_price(우리 ppp 기준)의 KB 가격판 재현. 신호와 가격이 "
                "모두 KB 출처라 우리 데이터 계산 오류 가능성은 완전히 배제되지만, 반대로 "
                "KB 자체 방법론의 한계(설문 기반 체감지표, 시/도 집계)는 그대로 남음.",
    )
    growth_df = _kb_price_growth_panel()
    if growth_df.empty:
        return _empty_result(**meta)
    growth_df = growth_df[["sido", "ym", "growth"]].dropna()

    with session_scope() as s:
        rows = s.execute(select(KbSentimentIndex.region_code, KbSentimentIndex.ym_date,
                                 KbSentimentIndex.sentiment_index)).all()
    sent_df = pd.DataFrame(rows, columns=["sido", "ym_date", "sentiment_index"])
    if sent_df.empty:
        return _empty_result(**meta)
    sent_df = sent_df.copy()
    sent_df["ym"] = pd.to_datetime(sent_df["ym_date"]).dt.to_period("M")
    sent_g = sent_df.groupby(["sido", "ym"])["sentiment_index"].mean().reset_index()
    sent_g["ym"] = sent_g["ym"] + 1  # 이번달 지수를 다음달 라벨로 이동(선행 정렬)

    merged = growth_df.merge(sent_g, on=["sido", "ym"], how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["sentiment_index"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)
