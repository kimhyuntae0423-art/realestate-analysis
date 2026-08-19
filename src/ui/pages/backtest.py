"""🔬 전략 백테스트 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
import pandas as pd
import streamlit as st
import plotly.express as px

from config.settings import DEFAULT_CATALYST_WEIGHT, DEFAULT_TIER_WEIGHT
from src.ui.shared import render_df

# region_backtest()의 tier_weight 기본값과 동일 (grid_search_region 실측 최적값,
# region_momentum_ranking()의 근거) — apt용 DEFAULT_TIER_WEIGHT(0.70, region_score 비중)와는
# 의미가 다른 파라미터라 별도 상수로 구분한다.
DEFAULT_REGION_TIER_WEIGHT = 0.20


def page_strategy_backtest():
    """🔬 전략 백테스트 — 투자수익·갭투자·임대수익 예측력 비교."""
    from src.analysis.gap_backtest import (
        gap_score_backtest, jeonse_risk_backtest,
        gap_simulation_backtest, gap_walk_forward,
        rental_yield_backtest,
    )
    from src.analysis.backtest import apt_backtest, region_backtest

    st.title("🔬 전략 백테스트")
    st.caption("투자수익·갭투자·임대수익 전략의 점수 예측력을 Spearman ρ로 실증 검증합니다.")

    with st.expander("📖 백테스트란? — 지표 읽는 법", expanded=False):
        st.markdown("""
**백테스트 구조**

> 과거 특정 시점에 "지금 이 단지 점수가 높다" → 이후 실제로 더 올랐는가?

- **학습 기간**: 점수를 계산할 때 참고하는 과거 데이터 범위
- **검증 기간**: 점수 산출 이후, 실제 가격이 얼마나 올랐는지 측정하는 기간
- 두 기간이 겹치지 않아야 진짜 예측력 검증 (out-of-sample)

---

**Spearman ρ (스피어만 순위 상관계수)**

점수 순위와 실제 상승률 순위가 얼마나 일치하는지를 -1 ~ +1로 표현합니다.

| ρ 범위 | 의미 | 판단 |
|---|---|---|
| **+0.5 이상** | 점수 높은 단지가 실제로도 많이 올랐다 | ✅ 강한 예측력 |
| **+0.3 ~ +0.5** | 어느 정도 예측 가능 | ✅ 유의미 |
| **-0.3 ~ +0.3** | 점수와 상승률이 무관 | ❌ 예측력 없음 |
| **-0.3 이하** | 점수 높을수록 오히려 덜 올랐다 | ❌ 역효과 |

ρ = 0.3 선을 넘어야 "이 점수를 믿고 투자 판단에 활용할 수 있다"고 봅니다.

---

**상위10% 적중률**

점수 상위 10% 단지 중 실제 상승률 상위 20%에 포함된 비율입니다.

- **랜덤 기대치: 20%** — 아무렇게나 골라도 상위 20%에 들어갈 확률이 20%
- **50%** → 랜덤 대비 2.5배 정확하게 좋은 단지를 고른 것
- **30% 이상**이면 실무에서 참고할 만한 선별력으로 봅니다
        """)

    with st.container(border=True):
        st.markdown("##### ⚙️ 공통 파라미터")
        st.caption("⚠️ DB 보유 데이터: 약 2024년~현재. 학습 기간 + 검증 기간 합계가 24개월 이하여야 오류 없이 동작합니다.")
        c1, c2, c3, c4 = st.columns(4)
        train_months = c1.slider("학습 기간 (개월)", 6, 24, 12, key="bt_train",
                                  help="점수 산출에 사용할 과거 데이터 기간. 길수록 노이즈 감소, 짧을수록 최근 트렌드 반영. DB 데이터는 2024년~이므로 학습+검증 합계 24개월 이하 권장")
        test_months  = c2.slider("검증 기간 (개월)", 6, 18, 12, key="bt_test",
                                  help="점수 산출 후 실제 성과를 측정할 기간. 학습+검증 합계가 DB 보유 기간을 초과하면 데이터 부족 오류 발생")
        min_deals    = c3.slider("최소 거래수", 3, 30, 5, key="bt_min",
                                  help="학습 기간을 전반/후반으로 나눴을 때 각각 이 건수 이상인 단지만 포함. 12개월 학습이면 '6개월당 5건 이상' 조건 → 실질적으로 연 10건 이상 거래 단지만 반영됨")
        fall_thr     = c4.slider("역전세 기준 (%p)", 1.0, 10.0, 3.0, 0.5, key="bt_fall",
                                  help="전세가율이 이 수치 이상 하락하면 역전세 '발생'으로 판정")

    _used_months = train_months + test_months
    _remaining = max(0, 24 - _used_months)
    st.caption(
        f"📅 현재 설정 사용 기간: **{_used_months}개월** (학습 {train_months} + 검증 {test_months}) | "
        f"DB 누적 목표: **24개월 이상** — "
        + (f"약 {_remaining}개월 더 쌓이면 갭투자·임대수익 점수 수식 재검토 권장"
           if _remaining > 0 else "✅ 24개월 이상 누적 — 수식 재검토 적기")
    )

    tab_compare, tab_invest, tab_gap, tab_yield = st.tabs([
        "📊 전략 비교",
        "🚀 투자수익",
        "🏠 갭투자",
        "💰 임대수익",
    ])

    # ── 전략 비교 ──────────────────────────────────────────────────
    with tab_compare:
        st.markdown("#### 전략별 Spearman ρ 비교")
        st.markdown(
            "세 전략의 종합점수가 실제 매매가 상승률을 얼마나 잘 예측하는지 한눈에 비교합니다.  \n"
            "**초록 점선(ρ = 0.3)을 넘는 전략만 실제 투자 판단에 활용할 수 있습니다.**"
        )

        st.info(
            "**자가매입 전략은 제외됩니다.**  \n"
            "저평가 가설(평당가 낮은 곳이 더 오른다)을 다중 시점 백테스트로 검증: **ρ = −0.61** — 음의 상관.  \n"
            "비싼 지역·대장 단지가 더 오르는 '마태 효과' 확인. 자가매입 기준은 투자수익(market+prestige) 점수로 흡수됨."
        )

        if st.button("▶ 3전략 전체 실행", key="run_compare", type="primary"):
            compare_rows = []
            col_status = st.empty()

            for label, runner in [
                ("🚀 투자수익", lambda: apt_backtest(train_months=train_months, test_months=test_months)),
                ("🏠 갭투자",   lambda: gap_score_backtest(train_months=train_months, test_months=test_months, min_deals=min_deals)),
                ("💰 임대수익", lambda: rental_yield_backtest(train_months=train_months, test_months=test_months, min_deals=min_deals)),
            ]:
                col_status.text(f"{label} 계산 중...")
                try:
                    r = runner()
                    compare_rows.append({
                        "전략": label, "ρ": r.spearman, "표본수": r.n,
                        "상위10% 적중률(%)": round(r.top10_hit * 100, 1),
                    })
                except Exception as e:
                    compare_rows.append({"전략": label, "ρ": None, "표본수": 0,
                                         "상위10% 적중률(%)": 0, "오류": str(e)})
            col_status.empty()

            df_cmp = pd.DataFrame(compare_rows)
            valid_cmp = df_cmp[df_cmp["ρ"].notna()].copy()

            if not valid_cmp.empty:
                # ── 신뢰도 판정 ──
                def _reliability(rho, hit, label=""):
                    if "갭투자" in label:
                        # 갭투자는 매매가 상승 예측이 목적이 아님 — ρ 음수도 정상
                        if rho >= 0.3:   return "🟢 높음", f"갭 조건 좋은 곳이 실제 상승도 높음 (상위10% 중 {hit:.0f}% 적중)"
                        if rho >= 0.0:   return "🟡 중립", "ρ≥0 — 탭 C ROE 시뮬레이션이 핵심 지표입니다"
                        return "⚪ 해당없음", "갭투자 점수는 매매가 상승 예측 목적이 아닙니다. 탭 C ROE를 확인하세요"
                    # 투자수익 · 임대수익 공통 (두 전략 모두 양의 ρ 목표)
                    if rho >= 0.5:   return "🟢 높음", f"점수가 실제 상승을 잘 예측합니다 (상위10% 중 {hit:.0f}% 적중)"
                    if rho >= 0.3:   return "🟡 보통", f"어느 정도 예측 가능합니다 (상위10% 중 {hit:.0f}% 적중)"
                    if rho >= 0.0:   return "🔴 낮음", f"예측력이 약합니다 (점수와 상승률 거의 무관)"
                    return "🔴 역방향", f"점수 높은 곳이 오히려 덜 올랐습니다 — 수식 점검 필요"

                c_m = st.columns(len(valid_cmp))
                for col, (_, row) in zip(c_m, valid_cmp.iterrows()):
                    badge, desc = _reliability(row["ρ"], row["상위10% 적중률(%)"], row["전략"])
                    col.markdown(f"**{row['전략']}**")
                    col.markdown(f"### {badge}")
                    col.caption(desc)
                    col.caption(f"표본 {row['표본수']:,}건 | 상위10% 적중 {row['상위10% 적중률(%)']:.0f}% (랜덤 기대치 20%)")

                st.markdown("---")

                # ── 차트: ρ 값은 참고용으로만 표시 ──
                valid_cmp["신뢰도"] = valid_cmp.apply(
                    lambda r: _reliability(r["ρ"], r["상위10% 적중률(%)"], r["전략"])[0], axis=1)
                fig_cmp = px.bar(
                    valid_cmp, x="전략", y="ρ",
                    color="ρ", color_continuous_scale="RdYlGn", range_color=[-0.7, 0.7],
                    text="신뢰도",
                    title="전략별 점수 예측력 — 초록 점선(0.3) 이상이어야 믿을 수 있음",
                    height=400,
                )
                fig_cmp.add_hline(y=0.3, line_dash="dash", line_color="green",
                                   annotation_text="신뢰 기준선")
                fig_cmp.add_hline(y=0, line_dash="solid", line_color="gray")
                fig_cmp.update_traces(textposition="outside")
                fig_cmp.update_layout(coloraxis_showscale=False,
                                       yaxis_title="예측력 (Spearman ρ, 참고용)")
                st.plotly_chart(fig_cmp, width='stretch')

                st.markdown("**수치 상세** — 상위10% 적중률 랜덤 기대치 = **20%**, 30% 이상이면 활용 가능")
                display_cmp = valid_cmp[["전략", "신뢰도", "표본수", "상위10% 적중률(%)", "ρ"]].copy()
                display_cmp["ρ"] = display_cmp["ρ"].apply(lambda v: f"{v:+.3f}")
                render_df(display_cmp)

            for _, row in df_cmp[df_cmp["ρ"].isna()].iterrows():
                st.warning(f"{row['전략']}: {row.get('오류', '알 수 없는 오류')}")

    # ── 투자수익 탭 ────────────────────────────────────────────────
    with tab_invest:
        st.markdown("#### 🚀 투자수익 전략 검증")
        st.markdown(
            "**이 전략의 핵심 질문:** 시장 강도(매수 심리)와 단지 명성(prestige)이 높은 곳이 실제로 더 오르는가?  \n"
            "- 단지 점수 = `region_score(시장강도+호재) × 0.7 + prestige × 0.3` (투자추천 탭 실제 공식)  \n"
            "- 지역 점수 = `tier × 0.2 + 가격모멘텀 × 0.48 + 거래량모멘텀 × 0.32` (`region_momentum_ranking()`과 동일 — 투자추천 탭이 실제로 지역 정렬에 쓰는 공식)  \n"
            "ρ > 0.3 이면 이 점수가 미래 상승을 예측한다는 것이 통계적으로 입증됩니다."
        )

        with st.expander("📜 백테스트 결론 및 개발 히스토리", expanded=True):
            st.markdown(
                """
**결론 (2026-05 다중시점 백테스트)**

| 모델 / 요소 | Spearman ρ | 채택 |
|-------------|-----------|------|
| **market×0.7 + prestige×0.3 (단지)** | **+0.62** | ✅ |
| **market×0.7 + prestige×0.3 (시군구)** | **+0.62** | ✅ |
| 저평가 점수 (자가매입 기준) | −0.61 | ❌ 기각 |
| tier만 (규제해제 순서) | 약함 | 보조만 |
| jeonse_accel | 역상관 | ❌ |
| population 순유입 | 역상관 | ❌ |
| supply_pressure | 효과 없음 | ❌ |

**자가매입 전략 제외 이유:** 저평가 가설 데이터로 기각 (ρ −0.61).
"싼 곳이 더 오른다"는 반대 — 비싼 지역·대장 단지가 더 오르는 **마태 효과** 확인.
자가매입 추천은 투자수익 점수(market+prestige)로 통합되어 별도 백테스트 불필요.
                """
            )

        c1_inv, c2_inv, c3_inv = st.columns(3)
        cw_inv = c1_inv.slider("호재 가중치", 0.0, 0.3, DEFAULT_CATALYST_WEIGHT, 0.05, key="bt_inv_cw",
                               help="개발·교통 호재의 점수 반영 강도. 높일수록 호재 지역이 상위권 차지")
        tw_apt_inv = c2_inv.slider("단지 가중치 (region_score)", 0.0, 1.0, DEFAULT_TIER_WEIGHT, 0.05,
                               key="bt_inv_tw_apt",
                               help="단지 점수 중 region_score(시장강도+호재) 비중, 나머지는 prestige. "
                                    "실제 서비스 기본값 0.70")
        tw_reg_inv = c3_inv.slider("지역 가중치 (tier)", 0.0, 1.0, DEFAULT_REGION_TIER_WEIGHT, 0.05,
                               key="bt_inv_tw_reg",
                               help="지역 점수 중 상급지등급(tier) 비중, 나머지는 가격·거래량모멘텀. "
                                    "실제 서비스 기본값 0.20 (region_momentum_ranking()과 동일)")

        if st.button("▶ 투자수익 재실행", key="run_invest"):
            with st.spinner("계산 중..."):
                try:
                    ri_apt = apt_backtest(
                        train_months=train_months, test_months=test_months,
                        catalyst_weight=cw_inv, tier_weight=tw_apt_inv,
                    )
                    ri_reg = region_backtest(
                        train_months=train_months, test_months=test_months,
                        catalyst_weight=cw_inv, tier_weight=tw_reg_inv,
                    )
                    ci1, ci2 = st.columns(2)
                    with ci1:
                        st.markdown("**단지 단위** — 개별 아파트 단지 예측력")
                        st.metric("Spearman ρ", f"{ri_apt.spearman:+.3f}",
                                  help="점수 순위 ↔ 실제 상승률 순위 일치도")
                        st.metric("상위10% 적중률", f"{ri_apt.top10_hit*100:.1f}%",
                                  help="점수 상위 10% 중 실제 상위 20%에 포함된 비율. 랜덤 기대치=20%")
                        st.metric("표본 수", f"{ri_apt.n:,}")
                    with ci2:
                        st.markdown("**시군구 단위** — 지역(구·군) 예측력")
                        st.metric("Spearman ρ", f"{ri_reg.spearman:+.3f}")
                        st.metric("상위10% 적중률", f"{ri_reg.top10_hit*100:.1f}%")
                        st.metric("표본 수", f"{ri_reg.n:,}")
                    st.markdown("**요소별 단독 ρ (단지)** — 각 요소가 혼자서 얼마나 예측하는가")
                    st.caption("ρ가 양수(↑)면 이 요소가 높은 단지가 실제 더 올랐다는 뜻, 음수(↓)면 반대")
                    comp_inv = pd.DataFrame([
                        {"요소": k, "ρ": v,
                         "방향": "↑ 양 (높을수록 오름)" if v > 0.05 else ("↓ 음 (높을수록 덜 오름)" if v < -0.05 else "→ 중립")}
                        for k, v in ri_apt.component_corr.items()
                    ]).sort_values("ρ", ascending=False)
                    render_df(comp_inv)
                    st.caption(
                        f"📌 단지 ρ={ri_apt.spearman:+.3f} / 시군구 ρ={ri_reg.spearman:+.3f}. "
                        + ("두 단위 모두 유의미 — 점수를 신뢰할 수 있습니다." if min(ri_apt.spearman, ri_reg.spearman) >= 0.3
                           else "한 단위 이상이 기준 미달 — 가중치 조정을 시도해 보세요.")
                    )
                except ValueError as e:
                    st.error(f"계산 실패: {e}")

    # ── 갭투자 탭 ──────────────────────────────────────────────────
    with tab_gap:
        st.markdown("#### 🏠 갭투자 전략 백테스트 (4종)")
        st.markdown(
            "**갭투자 점수 구성:** 상급지 등급(tier) **80%** + 거래활성도 **20%**  \n"
            "갭투자도 결국 시세차익이 핵심 — 갭 크기는 진입 필터(시드 조건)로만 사용하고, "
            "점수는 얼마나 오를 곳인가를 기준으로 산정합니다.  \n"
            "leverage_mult·jeonse_quality·market_score는 역상관 또는 노이즈 확인으로 점수에서 제외됐으며, 표시 목적으로만 출력됩니다."
        )

        inner_a, inner_b, inner_c, inner_d = st.tabs([
            "A. 점수-수익률",
            "B. 역전세 리스크",
            "C. 수익 시뮬",
            "D. Walk-forward",
        ])

        with inner_a:
            st.markdown("#### A. 갭투자 점수 vs 실제 매매가 상승률")
            st.markdown(
                "갭투자 점수가 높은 단지가 실제 매매가도 더 올랐는가?  \n"
                "ρ가 **음수**여도 괜찮습니다 — 갭투자의 목적은 '싸게 들어가서 레버리지 수익'이지, "
                "'가장 빨리 오를 곳 고르기'가 아니기 때문입니다. 탭 C의 ROE 시뮬레이션이 더 중요합니다."
            )
            if st.button("▶ 실행 (A)", key="run_a"):
                with st.spinner("계산 중..."):
                    try:
                        ra = gap_score_backtest(train_months=train_months, test_months=test_months, min_deals=min_deals)
                        ca1, ca2, ca3 = st.columns(3)
                        ca1.metric("표본 수", f"{ra.n:,}건")
                        ca2.metric("종합 점수 ρ", f"{ra.spearman:+.3f}",
                                   help="점수 순위 ↔ 상승률 순위 상관. 음수=점수 높은 곳이 덜 오름 (정상 현상)")
                        ca3.metric("상위10% 적중률", f"{ra.top10_hit*100:.1f}%",
                                   help="랜덤 기대치=20%. 이 지표보다 ρ와 탭C ROE가 더 핵심")
                        st.markdown("**요소별 단독 ρ** — 각 요소가 매매가 상승과 어떤 관계인지")
                        st.caption("요소가 양의 ρ면 그 요소가 높은 곳이 실제 더 올랐다는 뜻")
                        comp = pd.DataFrame([
                            {"요소": k, "ρ": v,
                             "방향": "↑ 양 (상승 연관)" if v > 0.05 else ("↓ 음 (역연관)" if v < -0.05 else "→ 중립")}
                            for k, v in ra.component_corr.items()
                        ]).sort_values("ρ", ascending=False)
                        render_df(comp)
                        if not ra.raw.empty:
                            fig = px.scatter(
                                ra.raw, x="score", y="actual_growth",
                                hover_data=["region_code", "apt_name"],
                                labels={"score": "갭투자 점수", "actual_growth": "실제 상승률 (%)"},
                                title=f"갭투자 점수 vs 실제 매매가 상승률 (ρ={ra.spearman:+.3f})",
                                trendline="ols",
                            )
                            st.plotly_chart(fig, width='stretch')
                            st.caption("점들이 우상향(/)이면 점수가 상승 예측, 우하향(\\)이면 역상관")
                    except ValueError as e:
                        st.error(f"계산 실패: {e}")

        with inner_b:
            st.markdown("#### B. 역전세 리스크 레이블 분류 정확도")
            st.markdown(
                f"갭투자 점수의 ⚠️·🔶 위험 레이블이 실제 전세가율 **{fall_thr}%p 이상 하락**을 얼마나 잘 잡아냈는가?  \n"
                "**Precision**: 위험 경고 중 실제 위험이었던 비율 (낮으면 헛경보가 많음)  \n"
                "**Recall**: 실제 위험 중 경고를 발령한 비율 (낮으면 위험을 놓침)  \n"
                "**F1**: 둘의 조화평균. **0.5 이상**이면 실무에서 참고할 만한 수준"
            )
            if st.button("▶ 실행 (B)", key="run_b"):
                with st.spinner("계산 중..."):
                    try:
                        rb = jeonse_risk_backtest(
                            train_months=train_months, test_months=test_months,
                            min_deals=min_deals, fall_threshold_pct=fall_thr,
                        )
                        cb1, cb2, cb3, cb4 = st.columns(4)
                        cb1.metric("표본 수", f"{rb.n:,}건")
                        cb2.metric("Precision", f"{rb.precision:.3f}",
                                   help="위험 경고 중 실제 역전세 발생 비율. 높을수록 헛경보 少")
                        cb3.metric("Recall", f"{rb.recall:.3f}",
                                   help="실제 역전세 중 경고 발령 비율. 높을수록 위험을 놓치지 않음")
                        cb4.metric("F1", f"{rb.f1:.3f}",
                                   help="Precision과 Recall의 균형. 0.5 이상=실용적")
                        st.markdown(f"**실제 역전세 발생**: {rb.n_actual_risk}건 / {rb.n}건 ({rb.n_actual_risk/rb.n*100:.1f}%)")
                        c = rb.confusion
                        conf_df = pd.DataFrame({
                            "": ["예측: 위험", "예측: 안전"],
                            "실제: 위험": [c["TP"], c["FN"]],
                            "실제: 안전": [c["FP"], c["TN"]],
                        }).set_index("")
                        st.markdown("**혼동 행렬 (Confusion Matrix)**")
                        st.caption("TP=맞게 위험 경고, FP=헛경보(실제 안전), FN=놓친 위험, TN=맞게 안전 판정")
                        render_df(conf_df)
                        st.caption(
                            f"📌 F1={rb.f1:.3f} → "
                            + ("실용적 수준 — 역전세 회피에 이 지표를 활용할 수 있습니다." if rb.f1 >= 0.5
                               else "아직 개선 여지 — 역전세 기준(%p)을 조정해 보세요.")
                            + f" | 역전세 기준: {fall_thr}%p 하락"
                        )
                    except ValueError as e:
                        st.error(f"계산 실패: {e}")

        with inner_c:
            st.markdown("#### C. 갭투자 TOP-N 수익 시뮬레이션")
            st.markdown(
                "과거 시점에 갭투자 점수 **상위 N개 단지**를 실제로 매수했다면 얼마나 벌었는가?  \n"
                "**ROE (자기자본 수익률)** = 매매가 상승액 ÷ 초기 갭(내 실투자금)  \n"
                "예: 갭 1억에 매수 후 매매가 3천만 오르면 ROE = +30%"
            )
            top_n_c = st.slider("TOP-N 단지 수", 5, 50, 20, key="top_n_c")
            if st.button("▶ 실행 (C)", key="run_c"):
                with st.spinner("계산 중..."):
                    try:
                        rc = gap_simulation_backtest(
                            train_months=train_months, hold_months=test_months,
                            top_n=top_n_c, min_deals=min_deals,
                        )
                        cc1, cc2, cc3, cc4 = st.columns(4)
                        cc1.metric("매칭 단지", f"{rc.n_matched}건")
                        cc2.metric("평균 매매가 상승", f"{rc.avg_price_growth_pct:+.2f}%")
                        cc3.metric("평균 ROE", f"{rc.avg_roe_pct:+.2f}%",
                                   help="자기자본(갭) 대비 매매가 상승 수익률")
                        cc4.metric("중앙값 ROE", f"{rc.median_roe_pct:+.2f}%")
                        if not rc.raw.empty:
                            show = rc.raw[["apt_name", "region_code", "gap",
                                            "price_growth_%", "roe_%", "score"]].copy()
                            show["gap_억"] = (show["gap"] / 10000).round(2)
                            show = show.drop(columns="gap").sort_values("roe_%", ascending=False)
                            show.insert(0, "rank", range(1, len(show) + 1))
                            fig_roe = px.bar(
                                show.head(top_n_c), x="apt_name", y="roe_%",
                                color="roe_%", color_continuous_scale="RdYlGn",
                                labels={"apt_name": "단지명", "roe_%": "ROE (%)"},
                                title=f"TOP-{top_n_c} 자기자본 수익률",
                            )
                            fig_roe.update_xaxes(tickangle=45)
                            st.plotly_chart(fig_roe, width='stretch')
                            render_df(show)
                        st.caption(
                            f"📌 갭 1억으로 ROE {rc.avg_roe_pct:+.2f}% = "
                            f"평균 {abs(rc.avg_roe_pct)/100:.2f}억 수익. 보유 {rc.hold_months}개월."
                        )
                    except ValueError as e:
                        st.error(f"계산 실패: {e}")

        with inner_d:
            st.markdown("#### D. Walk-forward: 여러 시점 반복 검증")
            st.markdown(
                "한 시점 결과는 운일 수 있습니다. 여러 과거 시점에서 반복 실행해 **평균과 편차**를 확인합니다.  \n"
                "편차(±)가 작을수록 일관성 있는 전략, 클수록 시점에 따라 들쭉날쭉한 전략입니다."
            )
            cd1, cd2 = st.columns(2)
            n_windows = cd1.slider("시점 수", 2, 8, 4, key="bt_n_win")
            top_n_d   = cd2.slider("시뮬레이션 TOP-N", 5, 50, 20, key="top_n_d")
            if st.button("▶ 실행 (D — 시간 오래 걸림)", key="run_d"):
                progress = st.progress(0, text="Walk-forward 실행 중...")
                wf_results = {}
                methods = [("score", "A. 점수-수익률"), ("risk", "B. 역전세 리스크"),
                           ("simulation", "C. 수익 시뮬레이션")]
                for idx, (mkey, mlabel) in enumerate(methods):
                    progress.progress((idx + 1) / len(methods), text=f"{mlabel} 계산 중...")
                    try:
                        rd = gap_walk_forward(
                            n_windows=n_windows, test_months=test_months, train_months=train_months,
                            method=mkey, min_deals=min_deals,
                            fall_threshold_pct=fall_thr, top_n=top_n_d,
                        )
                        wf_results[mkey] = rd
                    except Exception as e:
                        st.warning(f"{mlabel} 실패: {e}")
                progress.empty()
                if "score" in wf_results:
                    rd = wf_results["score"]
                    st.markdown("**A. 점수-수익률 walk-forward**")
                    st.metric("평균 ρ", f"{rd.avg_spearman:+.3f}", delta=f"±{rd.std_spearman:.3f}")
                    if not rd.summary.empty and "spearman" in rd.summary.columns:
                        valid_s = rd.summary[rd.summary["spearman"].notna()]
                        if not valid_s.empty:
                            fig_a = px.bar(valid_s, x="as_of", y="spearman",
                                            labels={"as_of": "기준 시점", "spearman": "ρ"}, title="시점별 ρ")
                            fig_a.add_hline(y=0, line_dash="dash", line_color="gray")
                            st.plotly_chart(fig_a, width='stretch')
                    render_df(rd.summary)
                if "risk" in wf_results:
                    rd = wf_results["risk"]
                    st.markdown("**B. 역전세 리스크 walk-forward**")
                    st.metric("평균 F1", f"{rd.avg_f1:.3f}", delta=f"±{rd.std_f1:.3f}")
                    render_df(rd.summary)
                if "simulation" in wf_results:
                    rd = wf_results["simulation"]
                    st.markdown("**C. 수익 시뮬레이션 walk-forward**")
                    st.metric("평균 ROE", f"{rd.avg_roe_pct:+.2f}%", delta=f"±{rd.std_roe_pct:.2f}%")
                    if not rd.summary.empty and "avg_roe_%" in rd.summary.columns:
                        fig_c = px.bar(
                            rd.summary[rd.summary["avg_roe_%"].notna()],
                            x="as_of", y="avg_roe_%",
                            labels={"as_of": "기준 시점", "avg_roe_%": "평균 ROE (%)"},
                            title="시점별 평균 ROE",
                        )
                        fig_c.add_hline(y=0, line_dash="dash", line_color="gray")
                        st.plotly_chart(fig_c, width='stretch')
                    render_df(rd.summary)

    # ── 임대수익 탭 ───────────────────────────────────────────────
    with tab_yield:
        st.markdown("#### 💰 임대수익 전략 백테스트")
        st.markdown(
            "**이 전략의 핵심 질문:** 현금흐름(월세 수익률)과 상승잠재력(상급지×시장강도)을 동시에 만족하는 단지를 찾는가?  \n\n"
            "**점수 구성:** 상승예상(tier+시장강도) **70%** + 수익률품질(yield × 상급지 보정) **30%**  \n"
            "`yield_quality = annual_yield_% × appreciation_score/100` — 같은 수익률이면 상급지 매물을 우대, 저가지역 고수익률 역상관 효과를 제거  \n\n"
            "**기대 결과:** ρ ≥ 0 (수식 개선 전 역상관이었으나, yield_quality 도입으로 양의 상관 목표)"
        )
        if st.button("▶ 실행", key="run_yield"):
            with st.spinner("계산 중..."):
                try:
                    ry = rental_yield_backtest(
                        train_months=train_months, test_months=test_months, min_deals=min_deals,
                    )
                    cy1, cy2, cy3 = st.columns(3)
                    cy1.metric("표본 수", f"{ry.n:,}건")
                    cy2.metric("종합점수 ρ", f"{ry.spearman:+.3f}",
                               help="양수이면 점수 높은 곳이 실제로도 상승 — 0.3 이상이면 활용 가능")
                    cy3.metric("상위10% 적중률", f"{ry.top10_hit*100:.1f}%",
                               help="랜덤 기대치=20%. 30% 이상이면 선별력 있음")

                    st.markdown("**요소별 단독 ρ** — 각 요소와 매매가 상승률의 관계")
                    st.caption("yield_quality(수익률품질)가 annual_yield(%)(원시 수익률)보다 높은 ρ를 보이면 수식 개선 효과가 입증됨")
                    comp_y = pd.DataFrame([
                        {"요소": k, "ρ": v,
                         "해석": "양의 상관 (높을수록 시세도 오름)" if v > 0.1
                                 else ("역상관" if v < -0.1 else "중립")}
                        for k, v in ry.component_corr.items()
                    ]).sort_values("ρ", ascending=False)
                    render_df(comp_y)

                    if not ry.raw.empty and "yield_quality" in ry.raw.columns:
                        fig_y = px.scatter(
                            ry.raw, x="yield_quality", y="actual_growth",
                            hover_data=["region_code", "apt_name", "annual_yield_%"],
                            labels={"yield_quality": "수익률품질 (yield×상급지)", "actual_growth": "실제 상승률 (%)"},
                            title=f"수익률품질 vs 실제 매매가 상승률 (종합ρ={ry.spearman:+.3f})",
                            trendline="ols",
                        )
                        st.caption("우상향(/) 추세선이면 yield_quality 높은 곳이 실제로도 올랐다는 것")
                        st.plotly_chart(fig_y, width='stretch')

                    if ry.spearman >= 0.3:
                        st.success(f"📌 ρ = {ry.spearman:+.3f} — 현금흐름·상승잠재력 동시 선별 확인")
                    elif ry.spearman >= 0.0:
                        st.info(f"📌 ρ = {ry.spearman:+.3f} — 약한 양의 상관 | n={ry.n:,}. 가중치 추가 조정 여지 있음")
                    else:
                        st.warning(
                            f"📌 ρ = {ry.spearman:+.3f} — 여전히 역상관. "
                            "annual_yield_%와 appreciation_score 역방향이 강한 데이터 구간일 수 있습니다."
                        )
                except ValueError as e:
                    st.error(f"계산 실패: {e}")
