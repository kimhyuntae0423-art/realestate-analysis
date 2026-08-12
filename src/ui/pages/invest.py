"""🚀 투자 추천 탭 — 진입점(page_invest).

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
from datetime import date
import streamlit as st

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
                "호재 가중치", 0.0, 0.5, 0.10, 0.05,
                help="호재 점수를 등급에 가산하는 강도. 0=호재 무시, 0.3=호재 100점 지역이 tier +30점 효과. "
                     "백테스트: 0.10이 균형, 0.30이면 Top10 적중률↑ 대신 전체 순위 ρ↓.",
            )

            c4, c5, c6 = st.columns(3)
            min_deals = c4.slider("최소 매매 거래수", 1, 500, 50, step=10)
            top_n = c5.slider("추천 단지 개수", 10, 200, 50)
            tier_weight = c6.slider(
                "지역(평당가) 가중치", 0.0, 1.0, 0.7, 0.05,
                help="시군구 중위 평당가 백분위가 점수에 차지하는 비중 (나머지는 대장단지 가중치). "
                     "예: 0.7이면 '동네가 좋은지' 70%, '동네 내 대장 단지인지' 30%. "
                     "백테스트 권장: 0.7.",
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
                    "대장단지 가중치", 0.0, 1.0, 0.30, 0.05,
                    help="시군구 내 단지 평당가 백분위가 점수에 차지하는 비중. "
                         "지역 가중치와 합해 100% 정규화. 백테스트 권장: 0.30.",
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


def _invest_sidebar_inputs_UNUSED() -> dict:
    """미사용. _personal_inputs_block으로 대체됨."""
    with st.sidebar:
        st.markdown("### 💎 투자 조건")
        months = st.slider(
            "분석 기간 (개월)", 3, 36, 24, key="i_months",
            help="과거 N개월 데이터를 분석에 사용",
        )

        with st.form("rec_form", clear_on_submit=False):
            seed_eok = st.number_input(
                "자기자본 시드 (억원)", min_value=0.1, max_value=200.0,
                value=5.0, step=0.5, format="%.1f",
            )
            ownership = st.selectbox("보유 주택 수", ["무주택", "1주택", "다주택"])
            cc1, cc2 = st.columns(2)
            first_time = cc1.checkbox("생애최초", help="LTV 보너스")
            use_loan = cc2.checkbox(
                "대출 사용", value=True,
                help="갭투자는 무관 (전세=임차인 부담)",
            )
            strategy = st.selectbox(
                "투자 전략",
                ["🔀 전략 비교", "🚀 투자수익", "갭투자", "임대수익", "자가매입"],
                index=0,
                help="🔀 전략 비교 = 3전략 동시 실행 후 교집합 하이라이트",
            )
            with st.expander("💳 DSR + KB시세 — 정확한 대출 한도"):
                use_dsr = st.checkbox(
                    "DSR 적용", value=False,
                    help="체크 시 LTV·한도cap·DSR 모두 적용. 미체크 시 LTV·한도cap만"
                )
                annual_income = st.number_input(
                    "연 소득 (만원)", min_value=0, max_value=100000,
                    value=6000, step=500,
                    help="세전 연소득"
                )
                existing_debt_monthly = st.number_input(
                    "기존 부채 월 원리금 (만원)", min_value=0, max_value=2000,
                    value=0, step=10,
                    help="신용대출/자동차/카드 등 기존 월 원리금 합"
                )
                interest_rate = st.slider(
                    "대출 금리 (%)", 2.0, 8.0, 4.5, 0.1,
                    help="신청 시점 명목 금리"
                )
                dsr_limit = st.slider("DSR 한도 (%)", 30, 50, 40,
                                        help="1금융 40, 2금융 50")
                kb_ratio_pct = st.slider(
                    "KB시세 / 실거래가 (%)", 75, 100, 95, step=1,
                    help="은행은 KB시세 기준으로 LTV 계산. KB부동산 앱에서 단지별 확인 가능. 통상 90~97%.",
                )

            with st.expander("👤 인적 사항 (선택)"):
                age = st.number_input("나이", min_value=20, max_value=80, value=35)
                family_size = st.number_input("부양가족 수", min_value=0, max_value=10, value=0)
                residence_type = st.selectbox(
                    "거주방식", ["실거주", "전세임대"],
                    help="전세임대는 다주택 보유시 양도세에 영향"
                )
                risk_profile = st.selectbox(
                    "투자 성향", ["중립", "공격적", "보수적"],
                    help="추천 점수에 ±15% 가중치 보정 (현재는 표시만)"
                )
                commute_hubs = st.multiselect(
                    "출퇴근 거점 (선택)",
                    ["강남", "판교", "광화문", "여의도", "송도", "수원", "화성", "평택", "천안"],
                    help="추후 거점 거리 필터링용"
                )

            with st.expander("⚙️ 고급 필터"):
                min_deals = st.slider("최소 매매 거래수", 1, 500, 50, step=10)
                top_n = st.slider("추천 단지 개수", 10, 200, 50)
                catalyst_weight = st.slider(
                    "호재 가중치", 0.0, 1.0, 0.0, 0.05,
                    help="0=과거 모멘텀만 / 1=호재만 (백테스트 권장: 0)",
                )
                tier_weight = st.slider(
                    "상급지 가중치", 0.0, 1.0, 0.6, 0.05,
                    help="규제지역 해제 순서 기반 등급 가산점. "
                         "강남3구·용산=100점, 서울 비강남=80, 인천/경기=60, 지방 광역시=40. "
                         "슬라이더 하나로 전 지역 가중치 동시 조절.",
                )
            submitted = st.form_submit_button(
                "🔍 검색", type="primary", width='stretch',
            )

        st.divider()
        if st.button("🔄 캐시 비우기", width='stretch', key="i_clear",
                     help="새 데이터 수집 후 또는 강제 재계산 시"):
            st.cache_data.clear()
            st.success("캐시 비움. 다음 검색은 재실행됩니다.")

    return dict(
        months=months,
        seed_eok=seed_eok, ownership=ownership, first_time=first_time,
        use_loan=use_loan, strategy=strategy,
        min_deals=min_deals, top_n=top_n, catalyst_weight=catalyst_weight,
        tier_weight=tier_weight,
        submitted=submitted,
        use_dsr=use_dsr, annual_income=annual_income,
        existing_debt_monthly=existing_debt_monthly,
        interest_rate=interest_rate, dsr_limit=dsr_limit,
        age=age, family_size=family_size,
        residence_type=residence_type, risk_profile=risk_profile,
        commute_hubs=commute_hubs,
        kb_ratio=kb_ratio_pct / 100, kb_ratio_pct=kb_ratio_pct,
    )


