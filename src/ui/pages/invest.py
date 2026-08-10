"""🚀 투자 추천 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
from datetime import date
import pandas as pd
import streamlit as st
import plotly.express as px

from src.analysis.location import is_kakao_ready, enrich_with_location
from src.analysis.scenario import project_5y_scenarios, stress_test
from src.analysis.fair_value import enrich_with_fair_value
from src.ui.shared import (
    REGION_MAP, render_table, render_df,
    _simplify_apt_name, naver_land_url, _personal_inputs_block,
    _cached_gap, _cached_yield, _cached_outright, _cached_investment,
    _cached_region_sentiment, _cached_all_trades,
)


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


def _render_stress_test(inputs: dict, selected_row: dict):
    """선택 단지 1개에 대한 5년 시나리오 + 스트레스 테스트."""
    st.markdown("---")
    st.markdown(f"### 🧪 스트레스 테스트 — {selected_row.get('apt_name', '?')}")

    price_man = float(selected_row.get("trade_median", 0))
    kb_ratio_st = inputs.get("kb_ratio", 1.0)
    loan_man = float(selected_row.get("loan_capacity", 0))
    # loan_capacity가 kb_ratio 미반영 캐시 값일 경우 직접 재계산
    if kb_ratio_st < 1.0 and price_man > 0:
        from src.analysis.loan import loan_capacity_man as _lcm_st
        region_code_st = selected_row.get("region_code", "11680")
        ownership_st = inputs.get("ownership", "무주택")
        ft_st = inputs.get("first_time", False)
        dsr_st = inputs.get("dsr_cap_man")
        loan_man = _lcm_st(price_man, region_code_st, ownership_st, ft_st, dsr_st,
                            kb_price_man=price_man * kb_ratio_st)
    equity_man = round(price_man - loan_man)
    growth_pct = float(selected_row.get("price_growth_%", 0))
    interest_rate = inputs.get("interest_rate", 4.5)

    # 시뮬레이션 슬라이더
    c1, c2 = st.columns(2)
    with c1:
        rate_bump = st.slider("금리 가산 (%)", 0.0, 3.0, 0.0, 0.25,
                                help="기준 금리 대비 추가 인상폭 가정")
    with c2:
        price_drop = st.slider("가격 변동 (%)", -30, 20, 0, 5,
                                 help="음수=하락, 양수=상승")

    # 스트레스 테스트
    stress = stress_test(price_man, loan_man, equity_man,
                          price_drop_pct=price_drop, rate_bump_pct=rate_bump,
                          interest_rate_pct=interest_rate)

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("월 상환액", f"{stress['new_monthly_payment_man']:,} 만원",
                help=f"가산 금리 {interest_rate + rate_bump:.2f}%")
    sc2.metric("자기자본 잔존", f"{stress['equity_remaining_man']/10000:.2f} 억",
                delta=f"{-stress['equity_loss_pct']:.1f}%",
                delta_color="inverse")
    sc3.metric("매도시 가격", f"{stress['scenario_price_man']/10000:.2f} 억")
    sc4.metric("자기자본 소멸 임계점", f"{stress['breakeven_drop_pct']:.1f}%",
                help="가격이 이만큼 떨어지면 자기자본 0",
                delta_color="off")

    # 24개월 이자만 감당 가능?
    months_24_interest = stress["new_monthly_payment_man"] * 24
    seed_remaining = inputs["seed_eok"] * 10000 - equity_man
    if seed_remaining < months_24_interest:
        st.warning(
            f"⚠️ 매수 후 24개월 이자/원리금 합계 {months_24_interest:,}만원 "
            f"> 시드 잔여 {seed_remaining:,}만원. 현금흐름 부담 주의."
        )

    # 5년 시나리오
    st.markdown("#### 📊 5년 후 시나리오")
    scenarios = project_5y_scenarios(
        price_man, growth_pct, equity_man, loan_man,
        interest_rate_pct=interest_rate,
    )
    if scenarios:
        rows = []
        for name, s in scenarios.items():
            rows.append({
                "시나리오": name,
                "연 상승률(%)": s["growth_pct_annual"],
                "5년 후 가격(억)": round(s["future_price_man"] / 10000, 2),
                "잔존 대출(억)": round(s["remaining_loan_man"] / 10000, 2),
                "누적 이자(억)": round(s["total_interest_5y_man"] / 10000, 2),
                "매도 시 자기자본(억)": round(s["equity_at_exit_man"] / 10000, 2),
                "연환산 수익률(%)": s["roi_annual_pct"],
            })
        render_df(pd.DataFrame(rows))


def _render_compare_view(
    seed_man: int, months: int, min_deals: int,
    ownership: str, first_time: bool, use_loan: bool,
    catalyst_weight: float, tier_weight: float, prestige_weight: float,
    dsr_cap_man, top_n: int, area_range, year_range,
    max_buy_reg_net: int = 0, max_buy_nonreg_net: int = 0,
    kb_ratio: float = 1.0,
):
    """3전략 동시 비교 — 겹치는 단지가 높은 확신도."""
    st.markdown("### 🔀 3전략 동시 비교")
    st.caption(
        "같은 조건으로 투자수익·갭투자·임대수익을 동시 실행합니다. "
        "여러 전략 상위권에 겹치는 단지일수록 확신도가 높습니다."
    )
    half_months = max(months // 2, 3)

    if max_buy_reg_net > 0 or max_buy_nonreg_net > 0:
        _ca, _cb = st.columns(2)
        _ca.metric("🏙️ 규제지역 최대 매수가 (부대비용 포함)", f"{max_buy_reg_net/10000:.2f} 억")
        _cb.metric("🏞️ 비규제지역 최대 매수가 (부대비용 포함)", f"{max_buy_nonreg_net/10000:.2f} 억")

    # kb_ratio 적용 부대비용 필터: 캐시 결과는 kb_ratio=1.0 기준이므로 여기서 재필터
    def _filter_affordable(df: pd.DataFrame, is_gap: bool = False) -> pd.DataFrame:
        """required_equity + 부대비용 ≤ 시드 조건으로 매수 불가 매물 제거.

        is_gap=True면 required_equity = gap 그대로 사용 (갭투자는 주담대 아닌 전세보증금 기준).
        is_gap=False면 kb_ratio < 1.0일 때 대출 재계산.
        """
        if df.empty:
            return df
        df = df.copy()
        from src.analysis.costs import total_acquisition_cost_man as _tacm2
        df["_acq_cost2"] = df["trade_median"].apply(lambda p: _tacm2(p, ownership, first_time)["total"])
        if not is_gap and kb_ratio < 1.0 and "trade_median" in df.columns and "region_code" in df.columns:
            from src.analysis.loan import annotate_loan_columns as _alc
            df = _alc(df, seed_man, ownership, first_time, "trade_median", dsr_cap_man, kb_ratio)
        if "required_equity" in df.columns:
            df = df[(df["required_equity"] > 0) & (df["required_equity"] + df["_acq_cost2"] <= seed_man)]
        return df.drop(columns=["_acq_cost2"], errors="ignore")

    _prog = st.progress(0, text="🚀 투자수익 계산 중…")
    try:
        rec_inv = _filter_affordable(_cached_investment(seed_man, months, min_deals, ownership, first_time,
                                      use_loan, catalyst_weight, tier_weight, prestige_weight, dsr_cap_man))
        _prog.progress(34, text="🏠 갭투자 계산 중…")
        rec_gap = _filter_affordable(_cached_gap(seed_man, months, min_deals, ownership, first_time, dsr_cap_man), is_gap=True)
        _prog.progress(67, text="💰 임대수익 계산 중…")
        rec_yld = _filter_affordable(_cached_yield(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man))
        _prog.progress(100, text="✅ 완료")
        _prog.empty()
    except MemoryError:
        _prog.empty()
        st.error("메모리 부족으로 중단됐습니다. 최소 거래수를 높이거나 분석 기간을 줄여보세요.")
        return
    except Exception as e:
        _prog.empty()
        st.error(f"계산 오류: {e}")
        return

    def _prep(df):
        if df.empty:
            return df
        df = df.copy()
        if area_range and "area_bucket" in df.columns:
            df = df[(df["area_bucket"] >= area_range[0]) & (df["area_bucket"] <= area_range[1])]
        if year_range and "build_year" in df.columns:
            df = df[df["build_year"].notna()
                    & (df["build_year"] >= year_range[0])
                    & (df["build_year"] <= year_range[1])]
        df["지역"] = df["region_code"].map(REGION_MAP).fillna(df["region_code"])
        return df.head(top_n).reset_index(drop=True)

    inv = _prep(rec_inv)
    gap = _prep(rec_gap)
    yld = _prep(rec_yld)

    def _keys(df):
        if df.empty or not {"apt_name", "region_code", "area_bucket"}.issubset(df.columns):
            return set()
        return set(zip(df["apt_name"], df["region_code"], df["area_bucket"]))

    k_inv, k_gap, k_yld = _keys(inv), _keys(gap), _keys(yld)
    all3 = k_inv & k_gap & k_yld
    any2 = ((k_inv & k_gap) | (k_inv & k_yld) | (k_gap & k_yld)) - all3

    def _badge(r):
        k = (r["apt_name"], r["region_code"], r["area_bucket"])
        if k in all3: return "🏆 3전략"
        if k in any2: return "🔶 2전략"
        return ""

    for df in [inv, gap, yld]:
        if not df.empty:
            df["일치"] = df.apply(_badge, axis=1)

    # ── 교집합 섹션 ──
    _key_cols = ["apt_name", "region_code", "area_bucket"]
    ann = 12 / half_months

    if all3:
        st.success(f"🏆 **3전략 모두 상위권 — {len(all3)}개 단지** | 시세차익 + 갭 진입 + 월세수익 동시 유망")

        # 베이스: 투자수익 DataFrame (price_growth_% 포함)
        _inv_cols = _key_cols + ["지역", "trade_median", "score"]
        for _c in ["expected_roi_%", "required_equity", "price_growth_%"]:
            if _c in inv.columns: _inv_cols.append(_c)
        over = inv[inv["일치"] == "🏆 3전략"][_inv_cols].copy()
        over.insert(0, "순위", range(1, len(over) + 1))
        over["매매가(억)"] = (over["trade_median"] / 10000).round(2)
        over["naver_url"] = [naver_land_url(r.get("지역"), r.get("apt_name")) for r in over.to_dict("records")]

        # 갭투자 데이터 병합 (gap + jeonse_ratio)
        if not gap.empty and "gap" in gap.columns:
            _g_cols = _key_cols + ["gap"]
            if "jeonse_ratio" in gap.columns: _g_cols.append("jeonse_ratio")
            _g = gap[gap["일치"] == "🏆 3전략"][_g_cols].copy()
            over = over.merge(_g, on=_key_cols, how="left")
            over["🏠 갭(억)"] = (over["gap"] / 10000).round(2)

        # 임대수익 데이터 병합 (annual_yield_% + monthly_median)
        if not yld.empty and "annual_yield_%" in yld.columns:
            _y_cols = _key_cols + ["annual_yield_%"]
            if "monthly_median" in yld.columns: _y_cols.append("monthly_median")
            _y = yld[yld["일치"] == "🏆 3전략"][_y_cols].copy()
            over = over.merge(_y, on=_key_cols, how="left")

        # 🚀 투자수익: 예상수익금 = 수익률 × 투입자본
        if "expected_roi_%" in over.columns and "required_equity" in over.columns:
            over["🚀 예상수익금(억)"] = (
                over["expected_roi_%"] * over["required_equity"] / 100 / 10000
            ).round(2)

        # 💰 임대수익: 연수익금 = 월세 × 12
        if "monthly_median" in over.columns:
            over["💰 연수익금(억)"] = (over["monthly_median"] * 12 / 10000).round(2)

        # 🏠 갭투자: 수익금 = 매매가 상승분 / 수익률 = 상승분 ÷ 갭
        if "price_growth_%" in over.columns and "gap" in over.columns:
            gain = over["trade_median"] * over["price_growth_%"] / 100
            over["🏠 갭투자수익금(억)"] = (gain / 10000).round(2)
            over["🏠 갭투자수익률(%)"] = (gain / over["gap"] * 100).round(2)

        # ── HTML 2단 헤더 테이블 (rowspan/colspan, 전부 연환산) ──

        has_inv_g = "🚀 예상수익금(억)" in over.columns
        has_inv_r = "expected_roi_%" in over.columns
        has_yld_g = "💰 연수익금(억)" in over.columns
        has_yld_r = "annual_yield_%" in over.columns
        has_gap_g = "🏠 갭투자수익금(억)" in over.columns
        has_gap_r = "🏠 갭투자수익률(%)" in over.columns
        has_gap_v = "🏠 갭(억)" in over.columns

        def _n(v):
            try:
                return "—" if pd.isna(v) else f"{float(v):.2f}"
            except Exception:
                return "—"

        _tbl_css = """
<style>
.cmp-tbl{width:100%;border-collapse:collapse;font-size:13px}
.cmp-tbl th{padding:6px 10px;text-align:center;white-space:nowrap;border:1px solid #e2e8f0}
.cmp-tbl th.base{background:#f1f5f9;color:#374151}
.cmp-tbl th.inv{background:#dbeafe;color:#1e40af}
.cmp-tbl th.yld{background:#dcfce7;color:#166534}
.cmp-tbl th.gap{background:#fef3c7;color:#92400e}
.cmp-tbl td{padding:5px 10px;border-bottom:1px solid #e2e8f0;text-align:center;white-space:nowrap}
.cmp-tbl tr:nth-child(even) td{background:#f9fafb}
.cmp-tbl tr:hover td{background:#f0f9ff}
</style>"""

        _thead = """
<tr>
  <th rowspan="2" class="base">순위</th>
  <th rowspan="2" class="base">🔗</th>
  <th rowspan="2" class="base">지역</th>
  <th rowspan="2" class="base">단지</th>
  <th rowspan="2" class="base">매매가(억)</th>
  <th rowspan="2" class="base">면적(㎡)</th>
  <th colspan="2" class="inv">🚀 투자수익</th>
  <th colspan="3" class="gap">🏠 갭투자</th>
  <th colspan="2" class="yld">💰 임대수익</th>
  <th rowspan="2" class="base">점수</th>
</tr>
<tr>
  <th class="inv">연수익금(억)</th><th class="inv">연수익률(%)</th>
  <th class="gap">연수익금(억)</th><th class="gap">연수익률(%)</th><th class="gap">갭(억)</th>
  <th class="yld">연수익금(억)</th><th class="yld">연수익률(%)</th>
</tr>"""

        _rows = []
        for _, r in over.iterrows():
            ig = _n(r["🚀 예상수익금(억)"] * ann) if has_inv_g else "—"
            ir = _n(r["expected_roi_%"] * ann)    if has_inv_r else "—"
            gg = _n(r["🏠 갭투자수익금(억)"] * ann) if has_gap_g else "—"
            gr = _n(r["🏠 갭투자수익률(%)"] * ann) if has_gap_r else "—"
            gv = _n(r["🏠 갭(억)"])               if has_gap_v else "—"
            yg = _n(r["💰 연수익금(억)"])          if has_yld_g else "—"
            yr = _n(r["annual_yield_%"])           if has_yld_r else "—"
            _url = r.get("naver_url") or ""
            _link = f"<a href='{_url}' target='_blank' style='color:#2563eb;text-decoration:none'>🔗</a>" if _url else "—"
            _rows.append(
                f"<tr><td>{int(r['순위'])}</td><td>{_link}</td><td>{r['지역']}</td><td>{r['apt_name']}</td>"
                f"<td>{r['매매가(억)']:.2f}</td><td>{r['area_bucket']:.0f}</td>"
                f"<td>{ig}</td><td>{ir}</td>"
                f"<td>{gg}</td><td>{gr}</td><td>{gv}</td>"
                f"<td>{yg}</td><td>{yr}</td><td>{r['score']:.1f}</td></tr>"
            )

        st.markdown(
            _tbl_css + f"<div style='overflow-x:auto'>"
            f"<table class='cmp-tbl'><thead>{_thead}</thead>"
            f"<tbody>{''.join(_rows)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"📅 전부 연환산 기준 (× 12 ÷ {half_months}개월). "
            f"🚀·🏠 수치는 최근 {half_months}개월 실거래 추세를 연환산한 추정값 — 과거 추세 지속 보장 아님. "
            f"💰 임대수익은 실제 연간 월세 수입."
        )
    elif any2:
        st.info(f"🔶 **2전략 이상 상위권 — {len(any2)}개 단지**")
    else:
        st.caption("현재 조건에서 두 전략 이상 겹치는 단지 없음 — 단지 수(top_n) 늘리거나 최소 거래수 낮춰보세요.")

    if any2:
        with st.expander(f"🔶 2전략 이상 겹치는 단지 ({len(any2)}개)", expanded=bool(not all3)):
            rows = []
            for df, label in [(inv, "🚀투자수익"), (gap, "🏠갭투자"), (yld, "💰임대수익")]:
                if df.empty: continue
                sub = df[df["일치"].isin(["🏆 3전략", "🔶 2전략"])].copy()
                sub["전략"] = label
                rows.append(sub[["지역", "apt_name", "area_bucket", "trade_median", "전략"]])
            if rows:
                m = pd.concat(rows)
                m["매매가(억)"] = (m["trade_median"] / 10000).round(2)
                piv = m.groupby(["지역", "apt_name", "area_bucket", "매매가(억)"])["전략"].apply(
                    lambda x: " · ".join(sorted(set(x)))
                ).reset_index()
                render_df(piv.rename(columns={"apt_name": "단지", "area_bucket": "면적(㎡)"}))

    st.markdown("---")

    # ── 전략별 탭 ──
    tab_inv, tab_gap, tab_yld, tab_under = st.tabs(
        ["🚀 투자수익", "🏠 갭투자", "💰 임대수익", "💎 저평가 매물"]
    )

    # 추천 단지 매물 확인 링크 (3탭 공유)
    def _render_catch_board(show_df: pd.DataFrame, tab_key: str):
        """💎 저평가 캐치 알림판.

        전략 추천 단지의 최근 거래가 분포 + 적정가를 분석해
        '이 가격 이하 매물이 나오면 잡아라'는 캐치 기준가를 제시한다.
        """
        st.markdown("#### 💎 저평가 캐치 알림판")
        st.caption(
            "추천 단지들의 **최근 실거래 분포**와 **적정가**를 바탕으로 매수 기준가를 계산합니다. "
            "**캐치기준가 이하 매물이 나오면 저평가 매물**입니다."
        )

        # ── 최근 거래 통계 계산 ──────────────────────────────────────────
        _raw = _cached_all_trades(months)
        _apt_set = set(show_df["apt_name"].unique())
        _df = _raw[_raw["apt_name"].isin(_apt_set)].copy()

        if _df.empty:
            st.info("해당 단지의 최근 거래 데이터가 없습니다.")
            return

        _area_tol = 5.0
        _df["area_bucket"] = (_df["area_m2"] / _area_tol).round() * _area_tol
        _df["deal_date"] = pd.to_datetime(_df["deal_date"])
        _cutoff = _df["deal_date"].max() - pd.DateOffset(months=3)
        _recent = _df[_df["deal_date"] >= _cutoff]

        if _recent.empty:
            _recent = _df  # fallback to full period

        _stats = _recent.groupby(["apt_name", "area_bucket"]).agg(
            최저가=("deal_amount", "min"),
            하위25=("deal_amount", lambda x: int(x.quantile(0.25))),
            중위가=("deal_amount", "median"),
            최고가=("deal_amount", "max"),
            거래건=("deal_amount", "count"),
        ).reset_index()

        # ── 전략 결과와 조인 ─────────────────────────────────────────────
        _key = ["apt_name", "area_bucket"]
        _base = show_df[[c for c in show_df.columns
                          if c in (_key + ["rank", "지역", "naver_url",
                                            "fair_value", "fv_premium_%", "verdict",
                                            "score", "gap", "jeonse_ratio",
                                            "annual_yield_%"])]].copy()
        merged = _base.merge(_stats, on=_key, how="inner")
        if merged.empty:
            st.info("면적 매칭 데이터가 없습니다.")
            return

        # ── 캐치 기준가 계산 ─────────────────────────────────────────────
        def _catch_price(row) -> float:
            fv = row.get("fair_value")
            p25 = row.get("하위25", 0)
            mid = row.get("중위가", 0)
            # 적정가가 중위가보다 낮으면 적정가를 기준으로 (더 보수적)
            if fv and fv > 0 and fv < mid:
                return round(float(fv))
            # 하위 25%ile: 실제로 이 가격에 거래된 사람들이 있음
            if p25 and p25 > 0 and p25 < mid:
                return int(p25)
            # 기본: 중위가의 95%
            return round(mid * 0.95) if mid else 0

        merged["캐치기준가"] = merged.apply(_catch_price, axis=1)
        merged["시세대비할인(%)"] = (
            (merged["캐치기준가"] - merged["중위가"]) / merged["중위가"] * 100
        ).round(1)

        # 저평가 판정 (캐치기준가 ≤ 중위가 * 0.97 이면 의미있는 할인)
        merged["상태"] = merged["시세대비할인(%)"].apply(
            lambda x: "🔥 강추 매수가" if x <= -10 else
                      ("💎 저평가 기준" if x <= -5 else
                       ("✅ 적정 기준" if x <= -2 else "—"))
        )

        # ── 억 단위 변환 ─────────────────────────────────────────────────
        for col in ["최저가", "하위25", "중위가", "최고가", "캐치기준가"]:
            if col in merged.columns:
                merged[col + "_억"] = (merged[col] / 10000).round(2)
        if "fair_value" in merged.columns:
            merged["적정가_억"] = (merged["fair_value"] / 10000).round(2)

        # ── 네이버 링크 ──────────────────────────────────────────────────
        if "naver_url" not in merged.columns:
            merged["naver_url"] = [
                naver_land_url(r.get("지역"), r.get("apt_name"))
                for r in merged.to_dict("records")
            ]

        # ── 표시 ─────────────────────────────────────────────────────────
        # 정렬: 캐치기준가 할인율 큰 순 (저평가 많은 것 우선)
        merged = merged.sort_values("시세대비할인(%)", ascending=True).reset_index(drop=True)

        disp_cols = [
            "naver_url", "상태", "지역", "apt_name", "area_bucket",
            "최저가_억", "하위25_억", "중위가_억", "최고가_억",
            "적정가_억", "캐치기준가_억", "시세대비할인(%)",
            "거래건",
        ]
        if "fv_premium_%" in merged.columns:
            disp_cols.append("fv_premium_%")
        if "verdict" in merged.columns:
            disp_cols.append("verdict")

        render_table(merged[[c for c in disp_cols if c in merged.columns]], height=540)
        st.caption(
            "📌 **캐치기준가**: 적정가(전세가율·수익률 역산)가 시세보다 낮으면 적정가, "
            "없으면 최근 하위25% 거래가 기준. "
            "**이 가격 이하 매물이 네이버/직방에 올라오면 저평가 매물입니다.**\n\n"
            "🔥 강추 매수가: 시세 대비 10%↑ 할인 | 💎 저평가 기준: 5~10% 할인 | "
            "✅ 적정 기준: 2~5% 할인"
        )

    with tab_inv:
        if inv.empty:
            st.warning("해당 조건의 투자수익 매물 없음")
        else:
            show = inv.copy()
            show["rank"] = range(1, len(show) + 1)
            show["naver_url"] = [naver_land_url(r.get("지역"), r.get("apt_name")) for r in show.to_dict("records")]
            if "expected_roi_%" in show.columns and "required_equity" in show.columns:
                show["연수익률(%)"] = (show["expected_roi_%"] * ann).round(2)
                show["연수익금(억)"] = (
                    show["expected_roi_%"] * ann * show["required_equity"] / 100 / 10000
                ).round(2)
            _key = ["apt_name", "region_code", "area_bucket"]
            if not gap.empty and "rent_median" in gap.columns:
                _rent = gap[_key + ["rent_median"]].drop_duplicates(_key)
                show = show.merge(_rent, on=_key, how="left")
                show = enrich_with_fair_value(show, jeonse_col="rent_median")
            cols = [
                "naver_url", "rank", "지역", "apt_name",
                "trade_median", "required_equity",
                "tier_label", "area_bucket", "build_year",
                "catalyst_score", "sentiment_score",
                "price_growth_%", "expected_roi_%",
                "연수익률(%)", "연수익금(억)",
                "score",
                "fair_value", "fv_premium_%", "verdict",
            ]
            st.markdown("#### 📊 단지별 전략 분석 요약")
            render_table(show[[c for c in cols if c in show.columns]], height=420)
            st.caption(f"📅 연환산 기준 (× 12 ÷ {half_months}개월 실거래 추세) | 💎 적정가: 전세가율 65% 역산")
            st.markdown("---")
            _render_catch_board(show, "inv")

    with tab_gap:
        if gap.empty:
            st.warning("해당 조건의 갭투자 매물 없음")
        else:
            show = gap.copy()
            show["rank"] = range(1, len(show) + 1)
            show["naver_url"] = [naver_land_url(r.get("지역"), r.get("apt_name")) for r in show.to_dict("records")]
            _key = ["apt_name", "region_code", "area_bucket"]
            if not inv.empty and "price_growth_%" in inv.columns:
                _pg = inv[_key + ["price_growth_%"]].drop_duplicates(_key)
                show = show.merge(_pg, on=_key, how="left")
                show["price_growth_%"] = show["price_growth_%"].fillna(0)
                gain = show["trade_median"] * show["price_growth_%"] / 100
                show["연수익금(억)"] = (gain / 10000 * ann).round(2)
                show["연수익률(%)"] = (gain / show["gap"] * 100 * ann).round(2)
            show = enrich_with_fair_value(show, jeonse_col="rent_median")
            cols = [
                "naver_url", "rank", "지역", "apt_name",
                "trade_median", "rent_median", "gap",
                "jeonse_risk", "jeonse_ratio", "jeonse_accel_%p",
                "leverage_mult",
                "tier_label", "area_bucket", "build_year",
                "trade_count", "rent_count",
                "연수익률(%)", "연수익금(억)",
                "score",
                "fair_value", "fv_premium_%", "verdict",
            ]
            st.markdown("#### 📊 단지별 전략 분석 요약")
            render_table(show[[c for c in cols if c in show.columns]], height=420)
            st.caption(f"📅 연수익률·연수익금: 연환산 기준 (× 12 ÷ {half_months}개월). 갭투자 수익률 = 시세차익 ÷ 갭(자기자본). | 💎 적정가: 전세가율 65% 역산")
            st.markdown("---")
            _render_catch_board(show, "gap")

    with tab_yld:
        if yld.empty:
            st.warning("해당 조건의 임대수익 매물 없음")
        else:
            show = yld.copy()
            show["rank"] = range(1, len(show) + 1)
            show["naver_url"] = [naver_land_url(r.get("지역"), r.get("apt_name")) for r in show.to_dict("records")]
            show = enrich_with_fair_value(show, jeonse_col=None, monthly_col="monthly_median")
            cols = [
                "naver_url", "rank", "지역", "apt_name",
                "trade_median", "required_equity",
                "area_bucket", "build_year",
                "deposit_median", "monthly_median",
                "annual_yield_%",
                "trade_count", "rent_count",
                "score",
                "fair_value", "fv_premium_%", "verdict",
            ]
            st.markdown("#### 📊 단지별 전략 분석 요약")
            render_table(show[[c for c in cols if c in show.columns]], height=420)
            st.caption("💎 적정가: 수익률 3.5% 역산 기준")
            st.markdown("---")
            _render_catch_board(show, "yld")

    with tab_under:
        st.subheader("💎 저평가 매물 — 매수 가능 범위 내 저평가 단지")
        st.caption(
            "갭투자(전세가율 65% 역산)·임대수익(수익률 3.5% 역산) 두 방법으로 "
            "적정가를 계산하고, 현재가가 **적정가보다 낮은 매물**만 표시합니다. "
            "같은 단지가 두 방법에서 모두 포착되면 더 낮은 값을 사용합니다."
        )

        with st.container(border=True):
            _fr1, _fr2, _fr3 = st.columns(3)
            under_thresh = _fr1.slider(
                "적정가 대비 범위 (%)", min_value=-40, max_value=30, value=-5, step=1,
                key="under_thresh",
                help="0% 이하: 저평가(적정가보다 싼 것만) | 0~10%: 적정 구간 포함 | 10%↑: 다소 고평가까지 포함",
            )
            under_sort = _fr2.radio(
                "정렬", ["저평가도 높은 순", "추천점수 높은 순", "매매가 낮은 순"], horizontal=True,
                key="under_sort",
            )
            # 전용면적 필터 — 투자전략 탭 기본값(80~110㎡)과 동일하게
            _area_default = area_range if area_range else (80, 110)
            under_area_range = _fr3.slider(
                "전용면적 범위 (㎡)", min_value=0, max_value=200,
                value=_area_default, step=5,
                key="under_area_range",
                help="투자전략 탭의 전용면적 기본값(80~110㎡)과 동일. 소형 구축 제외하려면 하한을 올리세요.",
            )

            # 지역 필터 — 전략 결과에서 지역 목록 동적 추출
            _all_regions_under: list[str] = sorted({
                r for df in [inv, gap, yld] if not df.empty and "지역" in df.columns
                for r in df["지역"].dropna().unique()
            })
            under_regions = st.multiselect(
                "지역 필터 (비워두면 전체)",
                options=_all_regions_under,
                default=[],
                key="under_regions",
                placeholder="지역을 선택하세요…",
            )

        # ── 전략 추천 단지 목록 (inv/gap/yld 결과에 있는 것만) ──────────────
        _strategy_apts: set[str] = set()
        for _sdf in [inv, gap, yld]:
            if not _sdf.empty and "apt_name" in _sdf.columns:
                _strategy_apts.update(_sdf["apt_name"].unique())

        _key_cols = ["apt_name", "region_code", "area_bucket"]
        rows_under = []

        # 갭투자 기반 (전세가율 역산) — 전략 추천 단지만
        if not gap.empty and "rent_median" in gap.columns:
            g_fv = enrich_with_fair_value(gap.copy(), jeonse_col="rent_median")
            g_fv["방법"] = "전세가율 역산"
            mask = g_fv["fv_premium_%"].notna() & (g_fv["fv_premium_%"] <= under_thresh)
            if mask.any():
                rows_under.append(g_fv[mask])

        # 임대수익 기반 (수익률 역산) — 전략 추천 단지만
        if not yld.empty and "monthly_median" in yld.columns:
            y_fv = enrich_with_fair_value(yld.copy(), jeonse_col=None, monthly_col="monthly_median")
            y_fv["방법"] = "수익률 역산"
            mask = y_fv["fv_premium_%"].notna() & (y_fv["fv_premium_%"] <= under_thresh)
            if mask.any():
                rows_under.append(y_fv[mask])

        if not rows_under:
            st.info(
                f"전략 추천 단지 중 저평가({under_thresh}% 이하) 단지가 없습니다. "
                "슬라이더를 올려보세요 (예: 0% → 적정가 이하 전체)."
            )
        else:
            combined = pd.concat(rows_under, ignore_index=True)
            # 전략 추천 단지만 유지
            combined = combined[combined["apt_name"].isin(_strategy_apts)].copy()

            if combined.empty:
                st.info("전략 추천 단지 중 해당 저평가 기준에 맞는 단지가 없습니다.")
            else:
                # 지역 필터
                if under_regions and "지역" in combined.columns:
                    combined = combined[combined["지역"].isin(under_regions)].copy()
                # 전용면적 필터
                if "area_bucket" in combined.columns:
                    combined = combined[
                        (combined["area_bucket"] >= under_area_range[0]) &
                        (combined["area_bucket"] <= under_area_range[1])
                    ].copy()

                if combined.empty:
                    st.info("선택한 조건에 해당하는 저평가 단지가 없습니다. 필터를 조정해보세요.")
                else:
                    # 같은 단지+면적에서 두 방법이 모두 걸리면 더 낮은 fv_premium_% 기준 하나만 남김
                    combined = (
                        combined
                        .sort_values("fv_premium_%")
                        .drop_duplicates(_key_cols, keep="first")
                        .reset_index(drop=True)
                    )

                    if under_sort == "추천점수 높은 순" and "score" in combined.columns:
                        combined = combined.sort_values("score", ascending=False).reset_index(drop=True)
                    elif under_sort == "매매가 낮은 순" and "trade_median" in combined.columns:
                        combined = combined.sort_values("trade_median", ascending=True).reset_index(drop=True)

                    combined["rank"] = range(1, len(combined) + 1)

                    # 네이버 가격 낮은순 매물 링크
                    def _naver_cheap_url(region: str | None, apt_name: str | None) -> str | None:
                        import urllib.parse as _ul
                        if not apt_name:
                            return None
                        clean = _simplify_apt_name(apt_name)
                        tokens = []
                        if region:
                            toks = str(region).strip().split()
                            if toks:
                                last = toks[-1]
                                if any(last.endswith(s) for s in ("동", "읍", "면", "리", "가")):
                                    if len(toks) >= 2:
                                        tokens.append(toks[-2])
                                tokens.append(last)
                        tokens.append(clean)
                        tokens.append("매매")
                        q = " ".join(t for t in tokens if t)
                        enc = _ul.quote(q, safe="")
                        return f"https://m.land.naver.com/search/result/{enc}?rletTypeCd=A01&tradeTypeCd=A1&sortField=prc&sortMethod=asc"

                    combined["naver_url"] = [
                        _naver_cheap_url(r.get("지역"), r.get("apt_name"))
                        for r in combined.to_dict("records")
                    ]

                    # 요약 메트릭
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("전략 추천 저평가 단지", f"{len(combined)}개")
                    mc2.metric(
                        "최대 저평가",
                        f"{combined['fv_premium_%'].min():.1f}%",
                        help="가장 많이 저평가된 단지의 값",
                    )
                    mc3.metric(
                        "평균 저평가",
                        f"{combined['fv_premium_%'].mean():.1f}%",
                    )

                    # 테이블
                    show_cols = [
                        "naver_url", "rank", "지역", "apt_name", "area_bucket",
                        "trade_median", "fair_value", "fv_premium_%", "verdict", "방법",
                    ]
                    if "gap" in combined.columns:          show_cols.append("gap")
                    if "jeonse_ratio" in combined.columns: show_cols.append("jeonse_ratio")
                    if "annual_yield_%" in combined.columns: show_cols.append("annual_yield_%")
                    if "score" in combined.columns:        show_cols.append("score")
                    render_table(
                        combined[[c for c in show_cols if c in combined.columns]],
                        height=600,
                    )
                    st.caption("📌 **보기** 링크 → 네이버 부동산 매물 **가격 낮은순** 정렬로 바로 이동")

                    # 바 차트
                    top_u = combined.head(25).copy()
                    color_map_u = {"전세가율 역산": "#3b82f6", "수익률 역산": "#22c55e"}
                    fig_u = px.bar(
                        top_u, x="apt_name", y="fv_premium_%",
                        color="방법",
                        color_discrete_map=color_map_u,
                        labels={"apt_name": "단지명", "fv_premium_%": "현재가-적정가 (%)"},
                        title=f"전략 추천 저평가 TOP {min(25, len(top_u))} (낮을수록 더 저평가)",
                        text="fv_premium_%",
                    )
                    fig_u.add_hline(y=0, line_dash="dash", line_color="gray")
                    fig_u.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                    fig_u.update_xaxes(tickangle=-45)
                    st.plotly_chart(fig_u, width='stretch')

                    st.markdown("---")
                    _render_catch_board(combined, "under")

            st.caption(
                "> 이 분석은 투자 판단을 돕기 위한 의사결정 보조 자료이며, "
                "최종 매수·매도 결정은 공식 실거래 데이터, 현장 확인, 금융·세무 전문가 상담 후 내려야 합니다."
            )


def render_recommend_tab(inputs: dict):
    seed_eok = inputs["seed_eok"]
    ownership = inputs["ownership"]
    first_time = inputs["first_time"]
    use_loan = inputs["use_loan"]
    strategy = inputs["strategy"]
    months = inputs["months"]
    min_deals = inputs["min_deals"]
    top_n = inputs["top_n"]
    catalyst_weight = inputs["catalyst_weight"]
    tier_weight = inputs.get("tier_weight", 0.6)
    prestige_weight = inputs.get("prestige_weight", 0.10)
    area_range = inputs.get("area_range")
    year_range = inputs.get("year_range")
    submitted = inputs["submitted"]
    use_dsr = inputs.get("use_dsr", False)
    # DSR 한도는 _personal_inputs_block 에서 이미 계산해서 전달
    dsr_cap_man = inputs.get("dsr_cap_man")
    kb_ratio = inputs.get("kb_ratio", 1.0)

    if not submitted and not st.session_state.get("rec_has_run", False):
        st.info(
            "위 **검색 조건**을 설정하고 **🔍 검색** 버튼을 누르세요."
        )
        return
    if submitted:
        st.session_state["rec_has_run"] = True

    seed_man = int(seed_eok * 10000)

    from src.analysis.loan import get_ltv_pct, max_purchase_man
    ltv_규제 = get_ltv_pct("11680", ownership, first_time)
    ltv_비규제 = get_ltv_pct("99999", ownership, first_time)
    max_buy_reg = max_purchase_man(seed_man, "11680", ownership, first_time, dsr_cap_man, kb_ratio) if use_loan else seed_man
    max_buy_nonreg = max_purchase_man(seed_man, "99999", ownership, first_time, dsr_cap_man, kb_ratio) if use_loan else seed_man

    from src.analysis.costs import total_acquisition_cost_man as _tacm
    from src.analysis.loan import loan_capacity_man as _lcm
    def _max_buy_net(seed, rc, own, ft, dsr, loan_ok, kr=kb_ratio):
        best = 0
        for p in range(1000, 300000, 1000):
            lv = _lcm(p, rc, own, ft, dsr, kb_price_man=p * kr) if loan_ok else 0
            eq = p - lv
            if eq > seed:
                break
            if eq + _tacm(p, own, ft)["total"] <= seed:
                best = p
        return best
    max_buy_reg_net    = _max_buy_net(seed_man, "11680", ownership, first_time, dsr_cap_man, use_loan)
    max_buy_nonreg_net = _max_buy_net(seed_man, "99999", ownership, first_time, dsr_cap_man, use_loan)
    costs_reg    = _tacm(max_buy_reg_net,    ownership, first_time)
    costs_nonreg = _tacm(max_buy_nonreg_net, ownership, first_time)


    if use_dsr and dsr_cap_man is not None and dsr_cap_man < 60000:
        st.warning(
            f"⚠️ DSR 한도({dsr_cap_man/10000:.2f}억)가 LTV 한도(6억)보다 작습니다. "
            "실제 대출은 DSR 쪽이 binding 됩니다."
        )

    if strategy == "🔀 전략 비교":
        _render_compare_view(
            seed_man=seed_man,
            months=months,
            min_deals=min_deals,
            ownership=ownership,
            first_time=first_time,
            use_loan=use_loan,
            catalyst_weight=catalyst_weight,
            tier_weight=tier_weight,
            prestige_weight=prestige_weight,
            dsr_cap_man=dsr_cap_man,
            top_n=top_n,
            area_range=area_range,
            year_range=year_range,
            max_buy_reg_net=max_buy_reg_net,
            max_buy_nonreg_net=max_buy_nonreg_net,
            kb_ratio=kb_ratio,
        )
        return

    if strategy == "🚀 투자수익":
        half_mo = max(months // 2, 3)
        st.info(
            f"💡 **투자수익 전략** — 미래 상승을 노리는 **레버리지 매수**\n\n"
            f"- 자금구조: 자기자본 {seed_eok}억 + **LTV 대출** = 매매가\n"
            f"- 매수 후 매도까지 보유 (실거주 또는 단순 보유)\n"
            f"- 매월 이자 부담 있음 (≈ 대출액 × 4~5% / 12)\n"
            f"- 종합점수 = **지역시장강도+호재(region_score)** × **{int(tier_weight*100)}%** + **대장단지(prestige_score)** × **{int(prestige_weight*100)}%**\n"
            f"- region_score = 시군구 평당가 시장강도 + 호재점수 × 호재가중치({int(catalyst_weight*100)}%) (100점 상한)\n"
            f"- 상급지등급(tier_score)은 참고 표시용이며 다중 시점 백테스트 결과에 따라 점수 산식에는 포함되지 않음\n"
            f"- 과거상승률·레버리지수익률·시드활용률도 점수에 포함되지 않고 별도 참고 지표로 표시\n"
            f"- 대장단지: 시군구 내 평당가 백분위(60%) + 동(dong) 평당가 백분위(40%). 그 지역의 1군 단지에 가산점.\n\n"
            f"📅 **수익률 기간 기준**: 분석기간 {months}개월 → 최근 **{half_mo}개월** vs 이전 **{half_mo}개월** 실거래 평당가 비교\n"
            f"- **예상평가차익·예상자기자본수익률은 연환산이 아닌 {half_mo}개월치 가격 변화율 × 레버리지**\n"
            f"- 연환산 참고치 = 표시값 ÷ {half_mo} × 12\n\n"
            f"⚙️ `config/catalysts.json`·`config/region_tiers.json` 직접 편집 가능"
        )
        rec = _cached_investment(seed_man, months, min_deals,
                                  ownership, first_time, use_loan, catalyst_weight,
                                  tier_weight, prestige_weight, dsr_cap_man)
        metric_col = "expected_roi_%"

        # 등록된 호재 보기
        from src.analysis.recommend import _load_catalysts, manual_catalyst_text
        with st.expander("📋 등록된 호재 목록 (config/catalysts.json)"):
            cat = _load_catalysts()
            rc = cat.get("region_catalysts", {})
            if not rc:
                st.write("등록된 호재 없음")
            else:
                rows = []
                for code, items in rc.items():
                    rname = REGION_MAP.get(code, code) if "REGION_MAP" in globals() else code
                    for c in items:
                        rows.append({
                            "지역": rname,
                            "유형": c.get("type", ""),
                            "내용": c.get("name", ""),
                            "점수": c.get("score", 0),
                        })
                render_df(pd.DataFrame(rows), height=400)
            st.caption("호재 추가/수정: `config/catalysts.json` 직접 편집. 저장 후 사이드바 [🔄 캐시 비우기].")
    elif strategy == "갭투자":
        st.info(
            f"💡 **갭투자 전략** — 전세 끼고 매수, 차익 노림수\n\n"
            f"- 자금구조: 자기자본 {seed_eok}억 = **매매가 − 전세보증금(갭)**\n"
            f"- 대출 X (전세보증금이 임차인 부담분) · 매월 이자 부담 없음\n\n"
            f"**종합점수 구성**\n"
            f"- 상급지 등급 80% — 백테스트 결과 단독 상관계수가 가장 높아 시세차익 예측의 핵심 지표\n"
            f"- 거래 활성도 20% — 유동성\n\n"
            f"- 전세가율·전세가율 추세·갭 레버리지 배수는 화면에 표시되지만 종합점수에는 포함되지 않음 "
            f"(백테스트에서 역상관 확인되어 제외, 역전세 위험 판정용으로만 사용)\n\n"
            f"⚠️ **역전세 리스크**: 전세가율 90%↑ 위험 · 83%↑ 또는 전세가 하락 추세 주의"
        )
        rec = _cached_gap(seed_man, months, min_deals, ownership, first_time, dsr_cap_man)
        metric_col = "gap"
    elif strategy == "임대수익":
        st.info(
            f"💡 **임대수익 전략**: 자기자본 + 보증금 + LTV 대출로 매수, 월세로 수익. "
            "필요자기자본 = 매매가 − 보증금중위 − 대출가능액."
        )
        rec = _cached_yield(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man)
        metric_col = "annual_yield_%"
    else:  # 자가매입
        st.info(
            f"💡 **자가매입 전략**: 자기자본(시드 {seed_eok}억) + LTV 대출로 매수. "
            "지역 평균 평당가 대비 저평가된 곳을 상위 배치."
        )
        rec = _cached_outright(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man)
        metric_col = "ppp_median"

    if rec.empty:
        st.warning(
            f"해당 조건을 만족하는 매물이 없습니다.\n\n"
            f"- 시드를 늘려보세요\n"
            f"- 분석 기간을 늘려보세요\n"
            f"- 최소 거래수를 낮춰보세요"
        )
        return

    # 부대비용 컬럼 추가 (모든 필터에 공통 사용)
    rec["_acq_cost"] = rec["trade_median"].apply(
        lambda p: _tacm(p, ownership, first_time)["total"]
    )
    # 🛡️ 안전망: 부대비용 포함 실제 현금(자기자본+부대비용) ≤ 시드
    if "required_equity" in rec.columns:
        rec = rec[(rec["required_equity"] > 0)
                  & (rec["required_equity"] + rec["_acq_cost"] <= seed_man)].reset_index(drop=True)
    elif "gap" in rec.columns:
        rec = rec[(rec["gap"] > 0)
                  & (rec["gap"] + rec["_acq_cost"] <= seed_man)].reset_index(drop=True)

    # 평형/준공연도 사용자 필터
    if area_range and "area_bucket" in rec.columns:
        a_lo, a_hi = area_range
        rec = rec[(rec["area_bucket"] >= a_lo) & (rec["area_bucket"] <= a_hi)].reset_index(drop=True)
    if year_range and "build_year" in rec.columns:
        y_lo, y_hi = year_range
        # build_year NaN 매물은 제외
        rec = rec[rec["build_year"].notna()
                  & (rec["build_year"] >= y_lo)
                  & (rec["build_year"] <= y_hi)].reset_index(drop=True)

    if rec.empty:
        st.warning(
            f"시드 {seed_eok}억 + 대출(LTV·DSR 반영)로 매수 가능한 매물이 없습니다.\n\n"
            f"- 규제지역 최대 매수가: **{max_buy_reg/10000:.2f}억**\n"
            f"- 비규제지역 최대 매수가: **{max_buy_nonreg/10000:.2f}억**\n\n"
            f"시드를 늘리거나 비규제지역을 검토하세요."
        )
        return

    # 지역명 컬럼 추가
    rec_disp = rec.copy()
    rec_disp["region"] = rec_disp["region_code"].map(REGION_MAP).fillna(rec_disp["region_code"])

    # KB시세 비율이 100% 미만이면 대출 컬럼 재계산 (캐시 결과는 kb_ratio=1.0 기준)
    if kb_ratio < 1.0 and "trade_median" in rec_disp.columns and "region_code" in rec_disp.columns:
        from src.analysis.loan import annotate_loan_columns
        rec_disp = annotate_loan_columns(
            rec_disp, seed_man, ownership, first_time,
            trade_col="trade_median", dsr_cap_man=dsr_cap_man, kb_ratio=kb_ratio,
        )
        if kb_ratio < 0.99:
            st.caption(
                f"💡 대출 계산 기준: KB시세 = 실거래가 × {kb_ratio:.0%} "
                f"(KB부동산 앱 미확인 시 실제 대출은 표시보다 적을 수 있음)"
            )

    # 입지 점수 (카카오 키 있을 때만 활성)
    if is_kakao_ready():
        cc1, cc2 = st.columns([1, 5])
        with cc1:
            enable_loc = st.checkbox("🚇 입지점수 계산", value=False,
                                      help="상위 TOP N 단지에 한해 카카오 API 호출 (캐시 사용)")
        with cc2:
            if enable_loc:
                st.caption(
                    "단지 주변 1km 지하철·학교·마트·병원 개수를 점수화 (캐시: data/processed/apt_locations.json)"
                )
        if enable_loc:
            rec_disp = enrich_with_location(rec_disp.head(top_n), max_calls=30,
                                              region_map=REGION_MAP)
    else:
        st.caption("💡 카카오 REST API 키를 .env 에 추가하면 입지점수 기능 활성화됩니다.")

    # 규제/비규제 실제 대출액 + 바인딩 요인 계산
    _loan_reg = max_buy_reg - seed_man
    _loan_nonreg = max_buy_nonreg - seed_man
    # LTV가 허용하는 대출 (시드 / (1 - LTV%) × LTV%)
    _ltv_loan_reg = seed_man * ltv_규제 / (100 - ltv_규제)
    _ltv_loan_nonreg = seed_man * ltv_비규제 / (100 - ltv_비규제)
    # 한도 cap: 매매가에 따라 다름 (규제지역만 적용)
    _cap_reg = (60000 if max_buy_reg <= 150000
                else 40000 if max_buy_reg <= 250000
                else 20000)
    # 바인딩 요인 판별 — 세 한도 중 가장 작은 값이 실제 대출을 결정
    _limits_reg = [(_ltv_loan_reg, f"LTV {ltv_규제:.0f}%"),
                   (_cap_reg,       f"한도 cap {_cap_reg//10000}억")]
    if dsr_cap_man is not None:
        _limits_reg.append((dsr_cap_man, f"DSR 한도 {dsr_cap_man/10000:.1f}억"))
    _bind_reg = min(_limits_reg, key=lambda x: x[0])[1]

    _limits_nonreg = [(_ltv_loan_nonreg, f"LTV {ltv_비규제:.0f}%")]
    if dsr_cap_man is not None:
        _limits_nonreg.append((dsr_cap_man, f"DSR 한도 {dsr_cap_man/10000:.1f}억"))
    _bind_nonreg = min(_limits_nonreg, key=lambda x: x[0])[1]

    # 툴팁용 값 미리 계산
    _loan_reg_net    = _lcm(max_buy_reg_net,    "11680", ownership, first_time, dsr_cap_man)
    _loan_nonreg_net = _lcm(max_buy_nonreg_net, "99999", ownership, first_time, dsr_cap_man)
    _eq_reg_net    = (max_buy_reg_net    - _loan_reg_net)    / 10000
    _eq_nonreg_net = (max_buy_nonreg_net - _loan_nonreg_net) / 10000
    _cash_reg    = (_eq_reg_net    + costs_reg["total"]    / 10000)
    _cash_nonreg = (_eq_nonreg_net + costs_nonreg["total"] / 10000)
    _dsr_str = f"{dsr_cap_man/10000:.2f}억" if dsr_cap_man else "미적용"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("매물 후보", f"{len(rec):,} 건")
    c2.metric("단지 수", f"{rec['apt_name'].nunique():,} 개")
    c3.metric("지역 수", f"{rec['region_code'].nunique():,} 개")
    c4.metric("🏙️ 규제지역 최대 매수가", f"{max_buy_reg_net/10000:.2f} 억",
              help=(
                  f"【부대비용 포함 실제 한도】\n"
                  f"매수가 {max_buy_reg_net/10000:.2f}억 = 자기자본 {_eq_reg_net:.2f}억 + 대출 {_loan_reg_net/10000:.2f}억\n"
                  f"총 필요 현금: 자기자본 {_eq_reg_net:.2f}억 + 부대비용 {costs_reg['total']/10000:.2f}억 = {_cash_reg:.2f}억 (시드 {seed_man/10000:.1f}억 이내)\n"
                  f"  · 취득세 {costs_reg['acquisition_tax']:,}만 / 중개 {costs_reg['broker_fee']:,}만 / 등기 {costs_reg['registration_etc']:,}만\n\n"
                  f"【대출 결정 요인: {_bind_reg}】\n"
                  f"① LTV {ltv_규제:.0f}%: 허용 대출 {_ltv_loan_reg/10000:.2f}억\n"
                  f"② 한도 cap: {_cap_reg//10000}억 (매매가 {max_buy_reg_net/10000:.1f}억 기준)\n"
                  f"③ DSR: {_dsr_str}\n\n"
                  f"※ 부대비용 전 이론 한도 {max_buy_reg/10000:.2f}억 → 포함 시 {max_buy_reg_net/10000:.2f}억\n"
                  "※ LTV: 강남3구·용산 40% / 기타 규제 50% / 생애최초 +10%p"
              ))
    c5.metric("🏞️ 비규제지역 최대 매수가", f"{max_buy_nonreg_net/10000:.2f} 억",
              help=(
                  f"【부대비용 포함 실제 한도】\n"
                  f"매수가 {max_buy_nonreg_net/10000:.2f}억 = 자기자본 {_eq_nonreg_net:.2f}억 + 대출 {_loan_nonreg_net/10000:.2f}억\n"
                  f"총 필요 현금: 자기자본 {_eq_nonreg_net:.2f}억 + 부대비용 {costs_nonreg['total']/10000:.2f}억 = {_cash_nonreg:.2f}억 (시드 {seed_man/10000:.1f}억 이내)\n"
                  f"  · 취득세 {costs_nonreg['acquisition_tax']:,}만 / 중개 {costs_nonreg['broker_fee']:,}만 / 등기 {costs_nonreg['registration_etc']:,}만\n\n"
                  f"【대출 결정 요인: {_bind_nonreg}】\n"
                  f"① LTV {ltv_비규제:.0f}%: 허용 대출 {_ltv_loan_nonreg/10000:.2f}억\n"
                  f"② DSR: {_dsr_str}\n\n"
                  f"※ 부대비용 전 이론 한도 {max_buy_nonreg/10000:.2f}억 → 포함 시 {max_buy_nonreg_net/10000:.2f}억\n"
                  "※ LTV: 무주택 70% (생애최초 80%) / 1주택 60% / 다주택 50%, 한도 cap 없음"
              ))
    if strategy == "🚀 투자수익":
        c6.metric("최고 예상수익률(자기자본)", f"{rec['expected_roi_%'].max():.2f} %")
    elif strategy == "임대수익":
        c6.metric("최고 연수익률", f"{rec['annual_yield_%'].max():.2f} %")
    elif strategy == "갭투자":
        c6.metric("최저 갭", f"{rec['gap'].min()/10000:.2f} 억")
    else:
        c6.metric("최저 자기자본", f"{rec['required_equity'].min()/10000:.2f} 억")

    if strategy == "🚀 투자수익":
        st.markdown("### 🏆 지역 추천순위")
        st.caption(
            f"✅ 시드 {seed_eok}억 기준 (부대비용 포함) · "
            f"규제지역 최대 **{max_buy_reg_net/10000:.2f}억** / "
            f"비규제지역 최대 **{max_buy_nonreg_net/10000:.2f}억** 이내 매물이 "
            "1건 이상 있는 지역만 표시."
        )
        st.caption(
            "avg_score = 위 매물별 종합점수(지역시장강도+호재 × 상급지가중치 + 대장단지 × 대장단지가중치)의 지역 평균."
        )

        sent_df = _cached_region_sentiment()
        from src.analysis.recommend import region_tier_score, region_tier_label
        from src.analysis.loan import max_purchase_man

        # 매수가능 매물 (시드 통과 + UI 한도 컷 반영)
        buyable_rec = rec[(rec["required_equity"] + rec["_acq_cost"] <= seed_man)].copy()
        # 지역별 매매가 한도 컷 (단지 추천표와 동일 규칙 적용 — 일관성)
        if not buyable_rec.empty:
            mb_map = {
                c: (max_purchase_man(seed_man, c, ownership, first_time, dsr_cap_man, kb_ratio)
                    if use_loan else seed_man)
                for c in buyable_rec["region_code"].unique()
            }
            buyable_rec["_max_buy"] = buyable_rec["region_code"].map(mb_map)
            buyable_rec = buyable_rec[buyable_rec["trade_median"] <= buyable_rec["_max_buy"]].drop(columns="_max_buy")
        # UI 필터 적용 (사이드바에서 받은 면적·연도)
        if area_range and "area_bucket" in buyable_rec.columns:
            a_lo, a_hi = area_range
            buyable_rec = buyable_rec[(buyable_rec["area_bucket"] >= a_lo) & (buyable_rec["area_bucket"] <= a_hi)]
        if year_range and "build_year" in buyable_rec.columns:
            y_lo, y_hi = year_range
            buyable_rec = buyable_rec[buyable_rec["build_year"].notna()
                                     & (buyable_rec["build_year"] >= y_lo)
                                     & (buyable_rec["build_year"] <= y_hi)]

        # ─── 시군구 단위 요약 표 (한눈에 비교) ──────────────────
        if not buyable_rec.empty:
            sig = buyable_rec.groupby("region_code").agg(
                n_buyable=("apt_name", "count"),
                n_apts=("apt_name", "nunique"),
                max_score=("score", "max"),
                avg_score=("score", "mean"),
                best_roi_=("expected_roi_%", "max"),
                avg_growth_=("price_growth_%", "mean"),
                min_trade=("trade_median", "min"),
                avg_prestige=("prestige_score", "mean"),
            ).reset_index()
            sig["region"] = sig["region_code"].map(REGION_MAP).fillna(sig["region_code"])
            sig["tier_label"] = (
                sig["region_code"].apply(region_tier_label).astype(str)
                .str.extract(r"^(\d)", expand=False)
            )
            sig = sig.sort_values("max_score", ascending=False).reset_index(drop=True)
            sig["rank"] = range(1, len(sig) + 1)
            sig["best_score"] = sig["max_score"].round(1)
            sig["avg_score"] = sig["avg_score"].round(1)
            sig["best_roi_%"] = sig["best_roi_"].round(2)
            sig["avg_growth_%"] = sig["avg_growth_"].round(2)
            sig["avg_prestige"] = sig["avg_prestige"].round(1)
            cols_sig = ["rank", "region", "tier_label",
                        "n_buyable", "n_apts",
                        "best_score", "avg_score", "avg_prestige",
                        "best_roi_%", "avg_growth_%", "min_trade"]
            st.markdown("#### 📊 시군구 한눈 요약 (점수·매물수·수익률)")
            st.caption("매수가능 매물 기준 시군구 집계. 최고점수 내림차순.")
            render_table(sig[cols_sig].head(30), height=380)
            st.markdown("")
        # ────────────────────────────────────────────────────
        if "dong" in buyable_rec.columns:
            buyable_rec["dong"] = buyable_rec["dong"].fillna("").astype(str).str.strip()
            buyable_rec.loc[buyable_rec["dong"] == "", "dong"] = "(동 미상)"
        else:
            buyable_rec["dong"] = "(동 미상)"

        # (시군구, 동) 단위 집계 — 동탄/새솔동 같은 sub-지역이 분리됨
        dong_stats = buyable_rec.groupby(["region_code", "dong"]).agg(
            n_buyable=("apt_name", "count"),
            min_equity=("required_equity", "min"),
            min_trade=("trade_median", "min"),
            avg_score=("score", "mean"),
            avg_prestige=("prestige_score", "mean") if "prestige_score" in buyable_rec.columns else ("apt_name", "count"),
        ).reset_index()
        dong_stats = dong_stats[dong_stats["n_buyable"] > 0].copy()

        if dong_stats.empty:
            st.info("매수 가능한 매물이 있는 지역이 없습니다.")
        else:
            # 시군구 메타 (sentiment / catalyst / tier)
            sent_meta = sent_df[["region_code", "avg_sentiment", "manual_catalyst", "catalyst_text"]] if not sent_df.empty else pd.DataFrame(columns=["region_code"])
            dong_stats = dong_stats.merge(sent_meta, on="region_code", how="left")
            dong_stats["avg_sentiment"] = dong_stats.get("avg_sentiment", pd.Series(50.0)).fillna(50.0)
            dong_stats["manual_catalyst"] = dong_stats.get("manual_catalyst", pd.Series(0.0)).fillna(0.0)
            dong_stats["region"] = dong_stats["region_code"].map(REGION_MAP).fillna(dong_stats["region_code"])
            dong_stats["tier_label"] = (
                dong_stats["region_code"].apply(region_tier_label)
                .astype(str).str.extract(r"^(\d)", expand=False)
            )
            dong_stats["tier_score"] = dong_stats["region_code"].apply(region_tier_score)

            # (동 단위) 종합점수: 단지 추천 score 평균이 가장 직접적인 sub-지역 강도
            #   + 상급지 가중치 반영
            tw = max(0.0, min(1.0, tier_weight))
            rest = 1.0 - tw
            dong_stats["region_rank_score"] = (
                dong_stats["avg_score"].fillna(50) * (rest * 0.50)
                + dong_stats["tier_score"] * tw
                + dong_stats["avg_prestige"].fillna(50) * (rest * 0.30)
                + dong_stats["avg_sentiment"] * (rest * 0.10)
                + dong_stats["manual_catalyst"] * (rest * 0.10)
            ).round(1)

            dong_stats = dong_stats.sort_values("region_rank_score", ascending=False).reset_index(drop=True)
            dong_top = dong_stats.head(40).copy()
            dong_top["rank"] = range(1, len(dong_top) + 1)
            dong_top["min_equity_억"] = (dong_top["min_equity"] / 10000).round(2)
            dong_top["min_trade_억"] = (dong_top["min_trade"] / 10000).round(2)

            st.caption("👇 각 (지역·동)을 펼치면 그 동 안의 매수가능 매물이 전부 나옵니다. "
                       "최대한 작은 단위(동)로 쪼개 표시.")

            for _, row in dong_top.iterrows():
                code = row["region_code"]
                dong = row["dong"]
                name = row["region"]
                rk = int(row["rank"])
                score = row["region_rank_score"]
                n_buy = int(row["n_buyable"])
                min_eq_eok = row["min_equity_억"]
                min_tr_eok = row["min_trade_억"]
                tier = row["tier_label"] or "-"

                full_name = f"{name} · {dong}" if dong != "(동 미상)" else f"{name} · (동 미상)"
                header = (
                    f"#{rk:>2}  {full_name}   "
                    f"급지 {tier}  ·  점수 {score:.1f}  ·  "
                    f"매물 {n_buy}건  ·  최저 자기자본 {min_eq_eok:.2f}억 / 매매가 {min_tr_eok:.2f}억"
                )
                with st.expander(header, expanded=(rk == 1)):
                    max_buy_sel = (
                        max_purchase_man(seed_man, code, ownership, first_time, dsr_cap_man)
                        if use_loan else seed_man
                    )
                    rgn_rec = buyable_rec[
                        (buyable_rec["region_code"] == code)
                        & (buyable_rec["dong"] == dong)
                    ].copy()
                    if "required_equity" in rgn_rec.columns:
                        rgn_rec = rgn_rec[
                            (rgn_rec["required_equity"] > 0)
                            & (rgn_rec["trade_median"] <= max_buy_sel)
                        ]
                    rgn_rec = rgn_rec.sort_values("score", ascending=False).reset_index(drop=True)
                    rgn_rec["apt_rank"] = range(1, len(rgn_rec) + 1)

                    if rgn_rec.empty:
                        st.info("매수 가능 매물이 없습니다.")
                        continue

                    # 네이버 검색은 '지역 동 단지명' 으로 좀 더 정확히
                    naver_q = f"{name} {dong}" if dong != "(동 미상)" else name
                    rgn_rec["naver_url"] = [
                        naver_land_url(naver_q, an) for an in rgn_rec["apt_name"]
                    ]

                    drill_cols = ["naver_url", "apt_rank", "apt_name", "trade_median", "required_equity",
                                   "tier_label", "area_bucket", "build_year",
                                   "catalyst_score", "sentiment_score",
                                   "price_growth_%", "expected_roi_%", "score"]
                    drill_cols = [c for c in drill_cols if c in rgn_rec.columns]
                    rgn_show = rgn_rec[drill_cols].copy()
                    rgn_show = rgn_show.rename(columns={"apt_rank": "rank"})
                    if "tier_label" in rgn_show.columns:
                        rgn_show["tier_label"] = (
                            rgn_show["tier_label"].astype(str).str.extract(r"^(\d)", expand=False)
                        )
                    render_table(rgn_show)
                    cat_text = row.get("catalyst_text")
                    if isinstance(cat_text, str) and cat_text:
                        st.caption(f"📌 등록호재: {cat_text}")

    elif strategy == "갭투자":
        st.markdown("### 🏆 지역별 갭투자 요약")
        st.caption("역전세 리스크 낮고 상급지인 지역 우선. 최고점수 내림차순.")

        gap_rec = rec[(rec["gap"] > 0) & (rec["gap"] + rec["_acq_cost"] <= seed_man)].copy()
        if not gap_rec.empty:
            # 역전세 리스크 분포
            risk_dist = gap_rec["jeonse_risk"].value_counts().reset_index()
            risk_dist.columns = ["리스크레벨", "건수"]

            rc1, rc2 = st.columns([1, 3])
            with rc1:
                st.markdown("**역전세 리스크 분포**")
                render_df(risk_dist)

            # 지역별 요약 집계
            rg = gap_rec.groupby("region_code").agg(
                n_opp=("apt_name", "count"),
                n_apts=("apt_name", "nunique"),
                min_gap=("gap", "min"),
                avg_ratio=("jeonse_ratio", "mean"),
                avg_leverage=("leverage_mult", "mean"),
                avg_accel=("jeonse_accel_%p", "mean"),
                max_score=("score", "max"),
            ).reset_index()
            rg["region"] = rg["region_code"].map(REGION_MAP).fillna(rg["region_code"])
            rg["safe_n"] = gap_rec.groupby("region_code")["jeonse_risk"].apply(
                lambda x: ((x == "✅ 적정") | (x == "🟢 갭여유")).sum()
            ).values
            rg["risk_n"] = gap_rec.groupby("region_code")["jeonse_risk"].apply(
                lambda x: (x == "⚠️ 역전세위험").sum()
            ).values
            rg = rg.sort_values("max_score", ascending=False).reset_index(drop=True)
            rg.insert(0, "rank", range(1, len(rg) + 1))
            rg["최저갭(억)"] = (rg["min_gap"] / 10000).round(2)
            rg["평균전세가율(%)"] = rg["avg_ratio"].round(1)
            rg["전세가율추세(%p)"] = rg["avg_accel"].round(2)
            rg["평균레버리지(배)"] = rg["avg_leverage"].round(1)
            rg["최고점수"] = rg["max_score"].round(1)

            show_cols = ["rank", "region", "n_opp", "최저갭(억)",
                         "평균전세가율(%)", "전세가율추세(%p)",
                         "safe_n", "risk_n",
                         "평균레버리지(배)", "최고점수"]
            rg_show = rg[show_cols].rename(columns={
                "n_opp": "기회수",
                "safe_n": "안전·적정",
                "risk_n": "역전세위험",
            })
            with rc2:
                render_df(rg_show, height=380)

    st.markdown(f"### 🎯 단지·평형 추천 TOP {top_n}")
    # 🛡️ 시드 안전망 + 매매가 한도 안전망 (지역별 max_purchase 계산해서 매매가 자체도 컷)
    from src.analysis.loan import max_purchase_man
    # 지역코드별 max_purchase 캐싱 (rec에 등장한 지역만)
    unique_codes = rec_disp["region_code"].unique() if "region_code" in rec_disp.columns else []
    max_buy_by_region = {
        c: max_purchase_man(seed_man, c, ownership, first_time, dsr_cap_man, kb_ratio) if use_loan else seed_man
        for c in unique_codes
    }
    if "required_equity" in rec_disp.columns:
        before = len(rec_disp)
        # (1) 자기자본+부대비용 ≤ 시드, (2) 매매가 ≤ 지역별 매수 한도
        rec_disp["_max_buy"] = rec_disp["region_code"].map(max_buy_by_region)
        rec_disp = rec_disp[
            (rec_disp["required_equity"] > 0)
            & (rec_disp["required_equity"] + rec_disp["_acq_cost"] <= seed_man)
            & (rec_disp["trade_median"] <= rec_disp["_max_buy"])
        ].drop(columns=["_max_buy", "_acq_cost"]).reset_index(drop=True)
        dropped = before - len(rec_disp)
        if dropped > 0:
            st.caption(f"⚠️ 시드+대출한도+부대비용({seed_eok}억 기준) 초과 매물 {dropped}건 제외됨")
    if rec_disp.empty:
        st.warning(
            f"시드 {seed_eok}억 + 대출(LTV·DSR 반영)로 매수 가능한 매물이 없습니다. "
            f"위 '규제지역 최대 매수가' / '비규제지역 최대 매수가' 카드를 확인하세요."
        )
        return
    st.caption(
        f"✅ 자기자본 **{seed_eok}억** + 규제별 LTV·한도cap·DSR 반영해 매매가 자체가 매수 한도 이내인 매물만 표시. "
        f"필요자기자본 = 매매가 − 실대출, 매수 시 본인 부담 금액."
    )
    # 컬럼 순서: 네이버링크 → 추천순위 → 단지·가격 → 급지·면적·연도 → 분석지표
    if strategy == "🚀 투자수익":
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "tier_label",
                      "area_bucket", "build_year",
                      "catalyst_score", "sentiment_score",
                      "price_growth_%", "expected_roi_%",
                      "catalysts", "score"]
    elif strategy == "갭투자":
        cols_order = ["naver_url", "rank", "region", "apt_name",
                      "trade_median", "rent_median", "gap", "required_equity",
                      "jeonse_risk",
                      "jeonse_ratio", "jeonse_accel_%p",
                      "leverage_mult",
                      "tier_label",
                      "area_bucket", "build_year",
                      "trade_count", "rent_count", "score"]
    elif strategy == "임대수익":
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "area_bucket", "build_year",
                      "ltv_%", "loan_capacity",
                      "deposit_median", "monthly_median",
                      "annual_yield_%", "trade_count", "rent_count", "score"]
    else:  # 자가매입
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "area_bucket", "build_year",
                      "ltv_%", "loan_capacity",
                      "ppp_median", "region_median_ppp", "value_ratio",
                      "trade_count", "score"]

    # 추천 순위 부여: rec_disp는 이미 score 내림차순 정렬 → 1,2,3...
    rec_disp_ranked = rec_disp.copy()
    rec_disp_ranked["rank"] = range(1, len(rec_disp_ranked) + 1)
    # 네이버 부동산 검색 링크 (지역명 + 단지명)
    rec_disp_ranked["naver_url"] = [
        naver_land_url(r.get("region"), r.get("apt_name"))
        for r in rec_disp_ranked.to_dict("records")
    ]
    rec_top = rec_disp_ranked[cols_order].head(top_n).copy()
    # tier_label "2_상급지" → "2" (숫자 한 자리만)
    if "tier_label" in rec_top.columns:
        rec_top["tier_label"] = rec_top["tier_label"].astype(str).str.extract(r"^(\d)", expand=False)
    render_table(rec_top, height=600)

    csv = rec_disp_ranked[cols_order].to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 추천 결과 CSV 다운로드", csv,
                        file_name=f"추천_{strategy}_{seed_eok}억_{date.today():%Y%m%d}.csv",
                        mime="text/csv")

    # ─── 🧪 단지 선택 후 스트레스 테스트 ───
    if "trade_median" in rec.columns and "loan_capacity" in rec.columns:
        st.markdown("---")
        st.markdown("### 🎯 관심 단지 깊이 분석")
        st.caption("아래에서 한 단지를 선택하면 5년 시나리오 + 스트레스 테스트가 표시됩니다.")
        rec_top = rec_disp.head(top_n).reset_index(drop=True)
        labels = [
            f"{r['region']} · {r['apt_name']} · {r['area_bucket']:.0f}㎡  "
            f"({r['trade_median']/10000:.2f}억)"
            for _, r in rec_top.iterrows()
        ]
        if labels:
            picked_idx = st.selectbox(
                "단지 선택", range(len(labels)),
                format_func=lambda i: labels[i],
                key="stress_picker",
            )
            selected = rec_top.iloc[picked_idx].to_dict()
            _render_stress_test(inputs, selected)
