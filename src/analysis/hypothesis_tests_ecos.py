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
MORTGAGE_SERIES = "mortgage_loan_eop"

_M2_LAG_EXPLORED = (
    "2026-08-18 시차 스캔(전국+서울 분리, 0~24개월): 1개월(전국 rho=-0.09)에선 신호가 "
    "약했지만 시차를 늘릴수록 뚜렷해짐 — 서울만 보면 6개월 -0.42, 9개월 -0.54, 12개월 -0.59, "
    "24개월 -0.74(전부 p<0.01). 그런데 반대 방향(가격 성장률(t) -> M2 증가율(t+lag))도 같이 "
    "돌려보니 6~12개월에서 유의미한 '양의' 상관(12개월 rho=+0.54, p=0.0001)이 나옴 — 즉 "
    "\"M2가 늘면 가격이 눌린다\"가 아니라 \"가격이 오르면 6~12개월 뒤 M2가 늘고(신용창조 경로), "
    "그 시점 M2 수치는 이미 지나간 상승분의 흔적이라 그 다음 국면의 가격 둔화와 겹쳐 보이는" \
    " 역인과/시차 아티팩트일 가능성이 있음. 이 가설(M2->가격, expected_sign=-1)의 통계적 지지가 "
    "M2 자체의 독립적 인과력을 증명하진 않는다 — test_price_leads_money_supply 참고."
)

_MULTIVARIATE_EXPLORED = (
    "2026-08-18 다중회귀(M2_yoy + loan_yoy -> 가격성장률, 표준화계수) 진단: 1개월 지연(주담대 "
    "최적점)에서 결합 R²=0.316(주담대 단독 0.184 + M2 단독 0.068보다 높음) — 두 변수 다 유의미 "
    "(주담대 coef=+0.51 p<0.0001, M2 coef=-0.37 p=0.002). 특히 M2는 단독일 때(-0.26, p=0.05, "
    "경계선)보다 주담대를 통제했을 때 더 강해짐 — M2가 '주담대(가격에 긍정적) + 나머지(정기예금 "
    "등, 가격에 부정적)'로 쪼개져 있고, 주담대 성분을 걷어내니 나머지의 위험회피 신호가 더 "
    "선명해진 것으로 해석됨. 반대로 12개월 지연(M2 최적점)에서는 주담대가 완전히 무의미해짐 "
    "(coef=-0.005, p=0.97) — M2의 장기 음의 상관은 주담대와 무관한 별개 메커니즘(정책반응/경기 "
    "순환)임을 재확인. 결론: 단기(1개월)엔 두 지표를 같이 봐야 각자의 순수 성분이 드러나고, "
    "장기(12개월)엔 M2 단독 신호만 유효 — 전략에 반영 시 참고."
)


def _ecos_yoy_panel(series: str, out_col: str) -> pd.DataFrame:
    """ECOS 월별 원시계열에서 전년동월대비(YoY) 증가율 패널을 만든다 (M2, 주담대 등 공용)."""
    with session_scope() as s:
        rows = s.execute(
            select(EcosSeries.ym_date, EcosSeries.value)
            .where(EcosSeries.series == series)
        ).all()
    df = pd.DataFrame(rows, columns=["ym_date", "value"])
    if df.empty:
        return pd.DataFrame(columns=["ym", out_col])
    df["ym"] = pd.to_datetime(df["ym_date"]).dt.to_period("M")
    df = df.sort_values("ym")
    df[out_col] = df["value"].pct_change(12)
    return df[["ym", out_col]]


def _m2_yoy_panel() -> pd.DataFrame:
    return _ecos_yoy_panel(M2_SERIES, "m2_yoy")


def _national_price_growth_panel(months: int) -> pd.DataFrame:
    df_trade = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df_trade.empty:
        return pd.DataFrame(columns=["ym", "growth"])
    price_g = region_growth_via_unit_tracking(df_trade, group_cols=[])
    return price_g[["ym", "growth"]].dropna()


# ─── 1. 통화량(M2) 증가 선행 ─────────────────────────────────────────
def test_money_supply_leads_price(months: int = 60, lag_months: int = 12) -> HypothesisResult:
    meta = dict(
        id="money_supply_leads_price",
        title="통화량(M2) 증가 선행",
        claim=f"M2(광의통화) 증가율이 높을수록 {lag_months}개월 뒤 전국 아파트 가격이 오히려 위축된다",
        method=f"한국은행 ECOS M2(말잔, 원계열) 전년동월대비(YoY) 증가율(t) vs {lag_months}개월 후 "
               f"전국 단지+평형 추적 매매가 성장률(t+{lag_months}, 구성효과 제거)의 Spearman 상관, "
               f"최근 {months}개월. 처음엔 통념대로 '증가율 높을수록 다음달 가격 상승'(1개월, 양의 "
               f"상관)으로 설계했으나 실DB 시차 스캔 결과 {lag_months}개월·음의 상관이 훨씬 강하게 "
               "나와 그 방향으로 재설정함(아래 caveats 참고).",
        expected_sign=-1,
        caveats="M2는 지역 구분 없는 국가 단위 지표라 전국 평균 가격과만 비교 가능. 국가 단위 "
                "월별 시계열이라 표본(n)이 다른 가설(지역×월 패널)보다 훨씬 작음. 이 음의 상관은 "
                "M2가 가격을 억누른다는 직접 인과가 아니라, 가격 상승이 먼저고 그게 시차를 두고 "
                "M2에 반영된 뒤(신용창조 경로) 그 다음 국면의 가격 둔화와 겹쳐 보이는 역인과/시차 "
                "아티팩트일 가능성이 있음 — test_price_leads_money_supply(가격이 M2를 선행)가 "
                "이 해석을 뒷받침하는 별도 증거.",
        explored=_M2_LAG_EXPLORED + " " + _MULTIVARIATE_EXPLORED,
    )
    price_g = _national_price_growth_panel(months)
    if price_g.empty:
        return _empty_result(**meta)

    m2 = _m2_yoy_panel().dropna(subset=["m2_yoy"])
    if m2.empty:
        return _empty_result(**meta)
    m2 = m2.copy()
    m2["ym"] = m2["ym"] + lag_months  # t시점 M2 증가율을 t+lag시점 라벨로 이동(선행 정렬)

    merged = price_g.merge(m2, on="ym", how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["m2_yoy"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)


# ─── 2. 가격 상승이 통화량(M2) 증가를 선행 (신용창조 경로) ─────────────
def test_price_leads_money_supply(months: int = 60, lag_months: int = 12) -> HypothesisResult:
    meta = dict(
        id="price_leads_money_supply",
        title="가격 상승 -> 통화량(M2) 증가 (신용창조 경로)",
        claim=f"아파트 가격이 오르면(내리면) {lag_months}개월 뒤 M2(통화량) 증가율도 따라 "
              "오른다(내린다) — 매매가 상승이 주택담보대출 실행 증가를 통해 시차를 두고 "
              "통화량에 반영된다",
        method=f"전국 단지+평형 추적 매매가 성장률(t, 구성효과 제거) vs {lag_months}개월 후 "
               f"한국은행 ECOS M2(말잔, 원계열) 전년동월대비(YoY) 증가율(t+{lag_months})의 "
               f"Spearman 상관, 최근 {months}개월. money_supply_leads_price(반대 방향, M2가 "
               "가격을 선행한다는 통념)를 검증하다 우연히 발견한 역방향 관계.",
        expected_sign=1,
        caveats="같은 두 시계열(가격 성장률, M2 YoY)로 방향만 바꿔 검증한 것이라, "
                "money_supply_leads_price의 음의 상관과 이 가설의 양의 상관이 서로 완전히 "
                "독립적인 증거는 아님 — 두 결과를 합쳐 '가격이 M2를 선행하고, M2 자체는 "
                "가격의 독립적 선행지표가 아니다'로 해석하는 게 더 정확함. 신용창조 채널을 "
                "더 직접 검증하려면 M2가 아니라 가계대출(주담대) 통계가 더 적합 — "
                "test_mortgage_loan_leads_price 참고.",
        explored=_M2_LAG_EXPLORED + " " + _MULTIVARIATE_EXPLORED,
    )
    price_g = _national_price_growth_panel(months)
    if price_g.empty:
        return _empty_result(**meta)

    m2 = _m2_yoy_panel().dropna(subset=["m2_yoy"])
    if m2.empty:
        return _empty_result(**meta)

    price_shifted = price_g.copy()
    price_shifted["ym"] = price_shifted["ym"] + lag_months  # t시점 가격성장률을 t+lag시점 라벨로 이동

    merged = price_shifted.merge(m2, on="ym", how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["growth"], merged["m2_yoy"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)


# ─── 3. 가계 주택담보대출 증가 선행 (신용창조 채널 직접검증) ───────────
def test_mortgage_loan_leads_price(months: int = 60, lag_months: int = 1) -> HypothesisResult:
    meta = dict(
        id="mortgage_loan_leads_price",
        title="가계 주택담보대출 증가 선행",
        claim=f"주택담보대출(전 금융권) 증가율이 높을수록 {lag_months}개월 뒤 전국 아파트 "
              "가격이 더 오른다",
        method=f"한국은행 ECOS 주택관련대출(예금취급기관, 말잔) 전년동월대비(YoY) 증가율(t) vs "
               f"{lag_months}개월 후 전국 단지+평형 추적 매매가 성장률(t+{lag_months}, 구성효과 "
               f"제거)의 Spearman 상관, 최근 {months}개월. M2는 정기예적금까지 섞여 위험회피 "
               "시에도 늘 수 있어 신호가 뒤집혔지만(money_supply_leads_price 참고), 주담대는 "
               "실제 매수 자금 집행이라 더 직접적인 신호일 것으로 기대.",
        expected_sign=1,
        caveats="국가 단위 월별 시계열이라 표본(n)이 지역×월 패널보다 훨씬 작음. M2와 마찬가지로 "
                "정책(DSR·LTV 규제, 정책모기지 등)이 대출 증가율 자체를 좌우해 인과가 역방향일 "
                "가능성도 배제 못함 — 다만 시차 스캔 결과(아래 explored)는 M2와 달리 짧은 시차에서 "
                "가장 강하고 6개월부터 약해지는 패턴이라, M2에서 발견된 역인과(장기 시차일수록 "
                "강해지는 패턴)와는 형태가 달라 직접 대출 실행 시점 효과일 가능성이 더 큼.",
        explored=(
            "2026-08-18 시차 스캔(전국, 1~12개월): 1개월 rho=+0.412(p=0.002)로 시작해 2개월 "
            "+0.405, 3개월 +0.388까지 비슷하게 유지되다 6개월 +0.314(p=0.015)로 약해지고, "
            "9개월 +0.101(유의하지 않음), 12개월 -0.130(유의하지 않음)으로 신호가 사라짐/역전됨. "
            "등록된 기본값(1개월)이 이미 최적점이라 재조정 불필요 — M2(장기 시차일수록 강해짐, "
            "역인과 의심)와 반대로 짧은 시차에서 감쇠하는 형태라 대출 실행 자체가 매수 완료 "
            "시점과 가깝다는 직접효과 해석에 더 부합. " + _MULTIVARIATE_EXPLORED
        ),
    )
    price_g = _national_price_growth_panel(months)
    if price_g.empty:
        return _empty_result(**meta)

    loan = _ecos_yoy_panel(MORTGAGE_SERIES, "loan_yoy").dropna(subset=["loan_yoy"])
    if loan.empty:
        return _empty_result(**meta)
    loan = loan.copy()
    loan["ym"] = loan["ym"] + lag_months  # t시점 주담대 증가율을 t+lag시점 라벨로 이동(선행 정렬)

    merged = price_g.merge(loan, on="ym", how="inner")
    merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
    if len(merged) < 2:
        return _empty_result(**meta)
    rho, _ = spearmanr(merged["loan_yoy"], merged["growth"])
    return HypothesisResult(statistic=float(rho), n=len(merged), **meta)
