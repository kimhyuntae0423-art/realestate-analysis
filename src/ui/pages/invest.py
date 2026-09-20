"""🚀 투자 추천 탭 — 진입점(page_invest).

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
from datetime import date
import streamlit as st

from config.settings import (
    DEFAULT_CATALYST_WEIGHT, DEFAULT_TIER_WEIGHT, DEFAULT_PRESTIGE_WEIGHT,
)
from src.ui.shared import _personal_inputs_block
from src.ui.pages.invest_recommend import render_recommend_tab


def page_invest():
    """🚀 투자 추천 - 시드+대출 기반 전국 매수 매물 검색."""
    st.title("🚀 투자 추천")
    st.caption("자기자본 + 대출(LTV/한도cap/DSR)로 매수 가능한 매물 중 미래 상승 잠재력 상위 단지 추천")

    with st.container(border=True):
        st.markdown("##### 👤 매수자 조건")
        p = _personal_inputs_block(key_prefix="inv")

    with st.container(border=True):
        st.markdown("##### 🎯 검색 조건")
        with st.form("inv_form", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            strategy = c1.selectbox(
                "투자 전략",
                ["🔀 전략 비교", "🚀 투자수익", "갭투자", "임대수익"],
                index=0,
                help="🔀 전략 비교 = 3전략 동시 실행 후 교집합 하이라이트",
            )
            months = c2.slider("분석 기간 (개월)", 3, 36, 24,
                                 help="거래 활성도·선행지표 등 계산에 쓰는 전체 조회 기간. "
                                      "매매가 자체는 아래 '현재 매매가 기준 기간'을 따로 봄.")
            catalyst_weight = c3.slider(
                "호재 가중치", 0.0, 0.5, DEFAULT_CATALYST_WEIGHT, 0.05,
                help="호재 점수를 등급에 가산하는 강도. 0=호재 무시, 0.3=호재 100점 지역이 tier +30점 효과. "
                     "grid_search_apt(n=6251) 검증: 0.10이 균형, 0.0이 근소 우위(오차범위 수준).",
            )

            c4, c5, c6 = st.columns(3)
            min_deals = c4.slider("최소 매매 거래수", 1, 500, 50, step=10)
            top_n = c5.slider("추천 단지 개수", 10, 200, 50)
            tier_weight = c6.slider(
                "지역(평당가) 가중치", 0.0, 1.0, DEFAULT_TIER_WEIGHT, 0.05,
                help="시군구 중위 평당가 백분위가 점수에 차지하는 비중 (나머지는 대장단지 가중치). "
                     "예: 0.7이면 '동네가 좋은지' 70%, '동네 내 대장 단지인지' 30%. "
                     "grid_search_apt(n=6251) 검증 최적 구간: 0.7 근방.",
            )

            c7, c8, c9 = st.columns(3)
            with c7:
                area_range = st.slider(
                    "전용면적 범위 (㎡)",
                    min_value=0, max_value=200,
                    value=(60, 85), step=5,
                    help="기본 60~85㎡ (국민주택규모 상한 85㎡ 기준, 통상 24~34평형대). "
                         "실거래 데이터의 면적은 전용면적이라 시장에서 부르는 '평형'(공급면적 기준)보다 "
                         "숫자가 작다 — 전용 59㎡가 보통 '24~25평형', 전용 84㎡가 '34평형'으로 불림. "
                         "그래서 '24평'을 전용면적 24×3.3=79㎡로 그대로 환산하면 실제 24평형(전용 59㎡대)이 빠짐.",
                )
            with c8:
                _this_year = date.today().year
                year_range = st.slider(
                    "준공연도 범위",
                    min_value=1970, max_value=_this_year + 5,
                    value=(2000, _this_year + 5), step=1,
                    help=f"기본 2000년~{_this_year+5}(분양권 포함). 신축만 보려면 하한을 올리기.",
                )
            with c9:
                prestige_weight = st.slider(
                    "대장단지 가중치", 0.0, 1.0, DEFAULT_PRESTIGE_WEIGHT, 0.05,
                    help="시군구 내 단지 평당가 백분위가 점수에 차지하는 비중. "
                         "지역 가중치와 합해 100% 정규화. grid_search_apt(n=6251) 검증 최적 구간: 0.3 근방.",
                )

            trade_months = st.slider(
                "현재 매매가 기준 기간 (개월)", 1, min(months, 12), min(1, months),
                help="추천에 쓰는 매매가(trade_median)를 이 기간 내 실거래로만 계산. "
                     "'분석 기간'을 통째로 쓰면 그 기간 초반의 낮은 가격까지 섞여 "
                     "최근 급등을 놓친 매매가가 나온다 — 짧을수록 최근 실거래를 반영. "
                     "⚠️ 실거래 신고기한이 계약일로부터 30일 이내라 최근 1개월치는 아직 "
                     "신고 안 된 거래가 있어 실제보다 적게 잡힐 수 있음 — 그 단지·평형에 "
                     "1개월 내 거래가 하나도 없으면 자동으로 전체기간 median으로 대체(fallback)됨. "
                     "거래건수 필터는 '분석 기간' 전체 기준으로 유지.",
            )

            submitted = st.form_submit_button(
                "🔍 검색", type="primary", width='stretch',
            )

    inputs = dict(
        **p,
        strategy=strategy, months=months,
        min_deals=min_deals, top_n=top_n, catalyst_weight=catalyst_weight,
        tier_weight=tier_weight, prestige_weight=prestige_weight,
        area_range=area_range, year_range=year_range,
        trade_months=trade_months,
        submitted=submitted,
    )
    render_recommend_tab(inputs)
