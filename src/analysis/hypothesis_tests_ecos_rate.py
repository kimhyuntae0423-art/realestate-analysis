"""부동산 통념 가설 검증 — 거시경제(한국은행 ECOS) 계열, 금리·유동성 비율.

hypothesis_tests_ecos.py(M2/주담대)와 같은 패턴이지만 300줄 제한으로 분리.
hypothesis_lab.get_all_hypotheses()에 등록.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sqlalchemy import select

from src.database.repository import session_scope
from src.database.models import EcosSeries
from src.analysis.hypothesis_lab import HypothesisResult, _empty_result
from src.analysis.hypothesis_tests_ecos import M2_SERIES, _national_price_growth_panel

_POLICY_LAG_EXPLORED = (
    "2026-08-18 시차 스캔(1~24개월): 짧은 시차(1~3개월)에선 약하거나 이론과 반대 부호였다가 "
    "시차를 늘릴수록 계속 강해지고 18개월에서 정점(M1/M2비율 rho=-0.48, 실질금리 rho=+0.54, "
    "둘 다 p<0.0001), 24개월엔 다시 약해짐. money_supply_leads_price(M2)에서 발견된 것과 "
    "정확히 같은 패턴 — 정책(기준금리)이 움직이는 시점 자체가 '시장이 이미 과열된' 시점이라, "
    "정책 효과가 실제로 나타나는 12~18개월 동안은 시장이 관성으로 계속 움직이고 있어 정책변수와 "
    "가격의 단순 시차상관이 진짜 인과가 아니라 정책의 내생성(endogeneity)을 반영할 가능성이 큼. "
    "M2/실질금리/M1-M2비율 세 지표 모두 같은 패턴을 보이는 건 우연이 아니라 이 셋이 전부 같은 "
    "통화정책 사이클에 얽혀있기 때문으로 보임."
)


def _ecos_level_panel(series: str, out_col: str) -> pd.DataFrame:
    """ECOS 월별 원시계열을 그대로(레벨) 반환 — 이미 비율/금리인 시계열(기준금리 등)에 사용."""
    with session_scope() as s:
        rows = s.execute(
            select(EcosSeries.ym_date, EcosSeries.value)
            .where(EcosSeries.series == series)
        ).all()
    df = pd.DataFrame(rows, columns=["ym_date", "value"])
    if df.empty:
        return pd.DataFrame(columns=["ym", out_col])
    df["ym"] = pd.to_datetime(df["ym_date"]).dt.to_period("M")
    df = df.sort_values("ym").rename(columns={"value": out_col})
    return df[["ym", out_col]]


def _real_rate_panel() -> pd.DataFrame:
    """실질금리 = 기준금리 - 향후1년 기대인플레이션율 (둘 다 %, 레벨 그대로 차감)."""
    base = _ecos_level_panel("base_rate", "base_rate")
    infl = _ecos_level_panel("expected_inflation", "expected_inflation")
    df = base.merge(infl, on="ym", how="inner")
    df["real_rate"] = df["base_rate"] - df["expected_inflation"]
    return df[["ym", "real_rate"]]


def _m1_m2_ratio_panel() -> pd.DataFrame:
    """M1/M2 비율(레벨) — 대기 투자자금(현금성) 비중. YoY 증가율이 아니라 비율값 자체를 쓴다."""
    m1 = _ecos_level_panel("m1_eop_raw", "m1")
    m2 = _ecos_level_panel(M2_SERIES, "m2")
    df = m1.merge(m2, on="ym", how="inner")
    df["m1_m2_ratio"] = df["m1"] / df["m2"]
    return df[["ym", "m1_m2_ratio"]]


# ─── 1. M1/M2 비율(대기 투자자금) 선행 ──────────────────────────────
def test_m1_m2_ratio_leads_price(months: int = 60, lag_months: int = 18) -> HypothesisResult:
    meta = dict(
        id="m1_m2_ratio_leads_price",
        title="M1/M2 비율(대기 투자자금) 선행",
        claim=f"M1/M2 비율이 높을수록(현금성 자금 비중 증가) {lag_months}개월 뒤 전국 아파트 "
              "가격이 오히려 덜 오른다 — 처음엔 '대기 투자자금 신호'로 양의 상관을 기대했으나 "
              "실DB 시차 스캔에서 반대로 확인됨",
        method=f"한국은행 ECOS M1(말잔,원계열)/M2(말잔,원계열) 비율(t) vs {lag_months}개월 후 "
               f"전국 단지+평형 추적 매매가 성장률(t+{lag_months}, 구성효과 제거)의 Spearman "
               f"상관, 최근 {months}개월. 1개월 지연(원래 기대)으로 설계했으나 신호가 약하고 "
               f"부호도 반대라, 시차 스캔 결과 가장 강했던 {lag_months}개월·음의 상관으로 재설정.",
        expected_sign=-1,
        caveats="비율은 YoY 증가율이 아니라 레벨 자체를 쓴다 — 추세(단조증가/감소)가 있으면 "
                "가성회귀 위험이 있어 해석에 주의. 국가 단위 월별 시계열이라 표본(n)이 지역×월 "
                "패널보다 훨씬 작음. 이 음의 상관도 M2와 마찬가지로 정책 내생성 아티팩트일 "
                "가능성이 큼(아래 explored).",
        explored=_POLICY_LAG_EXPLORED,
    )
    price_g = _national_price_growth_panel(months)
    if price_g.empty:
        return _empty_result(**meta)

    ratio = _m1_m2_ratio_panel()
    if ratio.empty:
        return _empty_result(**meta)
    ratio = ratio.copy()
    ratio["ym"] = ratio["ym"] + lag_months  # t시점 비율을 t+lag시점 라벨로 이동(선행 정렬)

    merged = price_g.merge(ratio, on="ym", how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["m1_m2_ratio"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)


# ─── 2. 실질금리 선행 ─────────────────────────────────────────────────
def test_real_rate_leads_price(months: int = 60, lag_months: int = 18) -> HypothesisResult:
    meta = dict(
        id="real_rate_leads_price",
        title="실질금리 선행",
        claim=f"실질금리(기준금리-기대인플레이션)가 높을수록 {lag_months}개월 뒤 전국 아파트 "
              "가격이 오히려 더 오른다 — 처음엔 표준 이론대로 음의 상관을 기대했으나 실DB "
              "시차 스캔에서 반대로 확인됨",
        method=f"한국은행 ECOS 기준금리 - 향후1년 기대인플레이션율(t) vs {lag_months}개월 후 "
               f"전국 단지+평형 추적 매매가 성장률(t+{lag_months}, 구성효과 제거)의 Spearman "
               f"상관, 최근 {months}개월. 1개월 지연(표준 이론)으로 설계했으나 신호가 약하고 "
               f"부호도 반대라, 시차 스캔 결과 가장 강했던 {lag_months}개월·양의 상관으로 재설정. "
               "실험실 미검증 후보였던 '기준금리 변동 선행'을 기대인플레이션까지 반영한 "
               "실질금리로 대체해 해결.",
        expected_sign=1,
        caveats="기대인플레이션율은 설문(소비자동향조사) 기반 체감 지표라 실제 인플레이션과 "
                "괴리 가능. 국가 단위 월별 시계열이라 표본(n)이 지역×월 패널보다 훨씬 작음. "
                "이 양의 상관은 실질금리가 가격을 밀어올린다는 뜻이 아니라, 금리 인상 자체가 "
                "'시장이 이미 과열됐을 때' 나오는 정책 반응이라 그 후 12~18개월은 관성으로 "
                "계속 오르는 국면과 겹쳐 보이는 정책 내생성 아티팩트일 가능성이 큼(아래 explored) "
                "— 표준 이론(고금리→가격하락)을 반박하는 근거로 쓰면 안 됨.",
        explored=_POLICY_LAG_EXPLORED,
    )
    price_g = _national_price_growth_panel(months)
    if price_g.empty:
        return _empty_result(**meta)

    real_rate = _real_rate_panel()
    if real_rate.empty:
        return _empty_result(**meta)
    real_rate = real_rate.copy()
    real_rate["ym"] = real_rate["ym"] + lag_months  # t시점 실질금리를 t+lag시점 라벨로 이동(선행 정렬)

    merged = price_g.merge(real_rate, on="ym", how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["real_rate"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)
