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
                                 help="과거 N개월 데이터 사용")
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
                    value=(80, 110), step=5,
                    help="기본 24~33평(80~110㎡). 1평 ≈ 3.3㎡ (30평 ≈ 99㎡, 40평 ≈ 132㎡)",
                )
            with c8:
                _this_year = date.today().year
                year_range = st.slider(
                    "준공연도 범위",
                    min_value=1970, max_value=_this_year + 5,
                    value=(_this_year - 10, _this_year + 5), step=1,
                    help=f"기본 최근 10년({_this_year-10}~{_this_year+5}). 구축까지 보려면 하한 내리기.",
                )
            with c9:
                prestige_weight = st.slider(
                    "대장단지 가중치", 0.0, 1.0, DEFAULT_PRESTIGE_WEIGHT, 0.05,
                    help="시군구 내 단지 평당가 백분위가 점수에 차지하는 비중. "
                         "지역 가중치와 합해 100% 정규화. grid_search_apt(n=6251) 검증 최적 구간: 0.3 근방.",
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
        submitted=submitted,
    )
    render_recommend_tab(inputs)
