"""📊 지역 분석 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import plotly.express as px

from src.database.repository import fetch_trades_df, fetch_rents_df
from src.analysis.price_trend import monthly_summary, apt_summary, yoy_change
from src.analysis.gap_analysis import gap_table
from src.analysis.yield_calc import rental_yield
from src.analysis.ranking import apt_growth
from src.analysis.fair_value import fair_value_ppp_trend, fair_value_apt_vs_ma
from src.analysis.fair_value_reverse import fair_value_by_jeonse, fair_value_by_yield
from src.analysis.supply import supply_for_region, supply_pressure_score
from src.ui.shared import (
    REGIONS, REGION_MAP, render_table, render_df,
    _cached_forecast, _cached_region_sentiment, _cached_region_momentum,
)


def chart_monthly_price(monthly: pd.DataFrame, label: str):
    # 만원 → 억원 변환
    df = monthly.copy()
    df["평균매매가(억원)"] = (df["avg_price"] / 10000).round(2)
    df["중위매매가(억원)"] = (df["median_price"] / 10000).round(2)
    fig = px.line(df, x="ym", y=["평균매매가(억원)", "중위매매가(억원)"],
                  labels={"value": "가격 (억원)", "ym": "년월", "variable": "구분"},
                  title=f"{label} 월별 평균/중위 매매가")
    fig.update_layout(legend_title_text="")
    return fig


def chart_monthly_ppp(monthly: pd.DataFrame):
    fig = px.line(monthly, x="ym", y="avg_ppp",
                  labels={"avg_ppp": "평당가 (만원/평)", "ym": "년월"},
                  title="월별 평당가 추이")
    return fig


def page_region():
    """📊 지역 분석 - 단일 시군구 시계열 깊이 분석."""
    st.title("📊 지역 분석")
    st.caption("특정 시군구의 추이·단지·갭·수익률·상승률을 한 번에")

    # ─── 🗺️ 전체 지역 모멘텀 비교 (예산 무관, 순수 지역 비교) ───
    with st.expander("🗺️ 전체 지역 모멘텀 비교 (예산 무관)"):
        mom = _cached_region_momentum(12)
        if not mom.empty:
            mom_disp = mom.copy()
            mom_disp["region"] = mom_disp["region_code"].map(REGION_MAP).fillna(mom_disp["region_code"])
            mom_disp["tier_label"] = mom_disp["tier_label"].astype(str).str.extract(r"^(\d)", expand=False)
            mom_disp = mom_disp.rename(columns={"growth_%": "가격모멘텀(%)", "vol_momentum": "거래량모멘텀"})
            st.caption(
                "region_backtest 검증(2026-08-18, spearman 0.73→0.78) 기반 — 입지등급 20%"
                "+가격모멘텀(구성효과 제거) 48%+거래량모멘텀 32%. 예산과 무관한 전국 지역 비교(상위 30개)."
            )
            render_table(mom_disp[["region", "tier_label", "가격모멘텀(%)", "거래량모멘텀", "momentum_score"]].head(30))
        else:
            st.caption("모멘텀 데이터가 부족합니다.")

    with st.container(border=True):
        st.markdown("##### 분석 대상")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            sido = st.selectbox("시/도", list(REGIONS.keys()), key="rg_sido")
        sub = REGIONS[sido]
        code_by_name = {n: c for c, n in sub.items()}
        with c2:
            gu_name = st.selectbox(
                "시군구", list(code_by_name.keys()), key="rg_gu",
            )
        code = code_by_name[gu_name]
        label = gu_name
        with c3:
            months = st.slider("최근 N개월", 3, 36, 12, key="rg_months")

    date_from = date.today() - timedelta(days=30 * months)
    df_t = fetch_trades_df(region_code=code, date_from=date_from)
    df_r = fetch_rents_df(region_code=code, date_from=date_from)

    st.markdown(f"### {label}")
    st.caption(f"최근 {months}개월 데이터 기준")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("매매 거래", f"{len(df_t):,} 건")
    c2.metric("전월세 거래", f"{len(df_r):,} 건")
    c3.metric("분석 단지 수", f"{df_t['apt_name'].nunique() if not df_t.empty else 0:,} 개")
    avg_ppp = int(df_t["price_per_pyeong"].mean()) if not df_t.empty else 0
    c4.metric("평균 평당가", f"{avg_ppp:,} 만원/평")

    if df_t.empty:
        st.warning(f"{label} 데이터가 없습니다. scripts/collect_data.py 로 먼저 수집하세요.")
        st.code(f"python scripts/collect_data.py --region {code} --months {months}")
        return

    # 🔬 지역 상세 진단 (매수심리·호재·공급 등 종합)
    with st.expander("🔬 지역 상세 진단 (매수심리·호재·공급)", expanded=True):
        _render_region_detail(code)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["📈 추이", "🏢 단지", "↔ 갭분석", "💰 수익률", "🔥 상승률", "💎 적정가"]
    )

    with tab1:
        st.subheader("월별 매매가 추이")
        st.caption("금액 단위: 억원 (1억원 = 10,000 만원). 평당가는 만원/평.")
        monthly = yoy_change(monthly_summary(df_t))
        if not monthly.empty:
            st.plotly_chart(chart_monthly_price(monthly, label), width='stretch')
            st.plotly_chart(chart_monthly_ppp(monthly), width='stretch')
            render_table(monthly)

        st.markdown("---")
        st.markdown("### 📈 Prophet 시계열 예측 (실험적)")
        st.caption(
            "최근 24개월 월별 중위 매매가에 Prophet을 적용해 향후 6개월 예측. "
            "**과거 추세 외삽이며 단순 통계 모델입니다. 미래를 보장하지 않습니다.**"
        )
        forecast_df = _cached_forecast(code, months_data=24, periods=6)
        if forecast_df.empty:
            st.info("예측을 위한 데이터가 부족합니다 (최소 6개월 이상 필요).")
        else:
            f = forecast_df.copy()
            f["가격(억원)"] = (f["yhat"] / 10000).round(2)
            f["하한(억원)"] = (f["yhat_lower"] / 10000).round(2)
            f["상한(억원)"] = (f["yhat_upper"] / 10000).round(2)
            f["구분"] = f["is_forecast"].map({True: "예측", False: "실측"})
            fig = px.line(f, x="ds", y="가격(억원)", color="구분",
                          color_discrete_map={"실측": "#1f77b4", "예측": "#d62728"},
                          labels={"ds": "년월"},
                          title=f"{label} 매매가 예측 (다음 6개월)")
            fig.add_scatter(x=f["ds"], y=f["하한(억원)"], mode="lines",
                            line=dict(color="rgba(214,39,40,0.2)"), name="하한",
                            showlegend=False)
            fig.add_scatter(x=f["ds"], y=f["상한(억원)"], mode="lines",
                            line=dict(color="rgba(214,39,40,0.2)"), name="상한",
                            fill="tonexty", fillcolor="rgba(214,39,40,0.1)",
                            showlegend=False)
            st.plotly_chart(fig, width='stretch')
            fc_only = f[f["is_forecast"]].copy()
            st.markdown("**향후 6개월 예측값**")
            render_df(
                fc_only[["ds", "가격(억원)", "하한(억원)", "상한(억원)"]]
                .rename(columns={"ds": "년월"})
            )

    with tab2:
        st.subheader("단지별 거래 요약")
        st.caption("금액: 억원, 평당가: 만원/평, 면적: ㎡")
        apts = apt_summary(df_t, top=100)
        render_table(apts, height=600)

        sel = st.text_input("단지명 검색", "")
        if sel:
            sub = df_t[df_t["apt_name"].str.contains(sel, na=False)]
            if not sub.empty:
                sub_m = monthly_summary(sub)
                if not sub_m.empty:
                    fig = px.line(
                        sub_m.assign(평균매매가_억원=(sub_m["avg_price"]/10000).round(2)),
                        x="ym", y="평균매매가_억원",
                        labels={"평균매매가_억원": "평균매매가 (억원)", "ym": "년월"},
                        title=f"'{sel}' 월별 평균가",
                    )
                    st.plotly_chart(fig, width='stretch')
                st.markdown("**최근 거래 내역 (최대 200건)**")
                recent = sub.sort_values("deal_date", ascending=False).head(200)
                show_cols = ["deal_date", "apt_name", "dong", "area_m2", "floor",
                             "deal_amount", "price_per_pyeong", "build_year"]
                render_table(recent[show_cols])

    with tab3:
        st.subheader("매매-전세 갭")
        st.caption("같은 단지·면적의 최근 매매 중위가 − 전세환산 중위가 (월세는 ×100 환산). 금액: 억원.")
        _trade_mo = st.slider(
            "현재 매매가 기준 기간 (개월)", 1, min(months, 6), min(3, months),
            key="gap_trade_months",
            help="짧을수록 최근 실거래가 반영. 거래건수 필터는 전체 분석 기간 기준 유지.",
        )
        gap = gap_table(df_t, df_r, area_tol=5.0, months=min(months, 6), trade_months=_trade_mo)
        render_table(gap, height=600)

    with tab4:
        st.subheader("임대 수익률 추정")
        st.caption("연수익률 = (월세 × 12) ÷ (매매가 − 보증금) × 100. 금액: 억원, 월세: 만원.")
        yld = rental_yield(df_t, df_r, area_tol=5.0, months=months)
        render_table(yld, height=600)

    with tab5:
        st.subheader("단지별 가격 상승률")
        st.caption(f"최근 {max(months//2, 3)}개월 평당가 중위값 vs 그 이전 같은 기간. 평당가: 만원/평.")
        growth = apt_growth(df_t, lookback_months=max(months // 2, 3), min_deals=3)
        render_table(growth, height=600)
        if not growth.empty:
            top = growth.head(20)
            fig = px.bar(top, x="apt_name", y="change_%",
                         labels={"apt_name": "단지명", "change_%": "변동률 (%)"},
                         title="평당가 상승률 TOP 20")
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, width='stretch')

    with tab6:
        st.subheader("💎 적정가 분석 — 오버슈팅 / 저평가 판정")
        st.caption(
            "3가지 방법으로 적정 매매가를 역산해 현재 가격이 얼마나 고평가·저평가됐는지 판정합니다. "
            "**참고 지표이며 투자 결정의 근거로 단독 사용하지 마세요.**"
        )

        _verdict_legend = (
            "🔴 오버슈팅(+20%↑)  🟠 고평가(+10~20%)  🟡 적정(±10%)  🟢 저평가(−10~15%)  🔵 심한저평가(−15%↓)"
        )
        st.info(_verdict_legend)

        fv_method1, fv_method2, fv_method3 = st.tabs([
            "① 전세가율 역산", "② 수익률 역산", "③ 이동평균 비교",
        ])

        # ── ① 전세가율 역산 ──────────────────────────────────────────────
        with fv_method1:
            st.markdown("#### 전세가율 역산법")
            st.caption(
                "적정 매매가 = 전세환산 중위가 ÷ 목표 전세가율. "
                "현재가 > 적정가 → 고평가(오버슈팅), 현재가 < 적정가 → 저평가."
            )
            with st.container(border=True):
                c1, c2 = st.columns(2)
                fv_jeonse_ratio = c1.slider(
                    "목표 전세가율 (%)", 50, 80, 65, key="fv_jeonse_ratio",
                    help="65%: 적정 기준. 낮출수록 적정가 상향 → 오버슈팅 단지가 줄어듦.",
                ) / 100.0
                fv_j_months = c2.slider(
                    "분석 기간 (개월)", 3, 12, 6, key="fv_j_months",
                )

            fv_j = fair_value_by_jeonse(
                df_t, df_r,
                target_jeonse_ratio=fv_jeonse_ratio,
                months=fv_j_months,
            )

            if fv_j.empty:
                st.info("전세 데이터가 부족합니다. 해당 지역 전월세 거래를 먼저 수집하세요.")
            else:
                show_cols = [
                    "apt_name", "area_bucket", "trade_median",
                    "jeonse_median", "jeonse_ratio_%",
                    "fair_value", "fv_premium_%", "verdict",
                ]
                show_cols = [c for c in show_cols if c in fv_j.columns]
                render_table(fv_j[show_cols], height=500)

                # 바 차트 (오버슈팅 내림차순)
                top_fv = fv_j.head(30).copy()
                color_map = {
                    "🔴 오버슈팅": "#ef4444",
                    "🟠 고평가":   "#f97316",
                    "🟡 적정":     "#eab308",
                    "🟢 저평가":   "#22c55e",
                    "🔵 심한저평가": "#3b82f6",
                }
                top_fv["color"] = top_fv["verdict"].map(color_map).fillna("#94a3b8")
                fig_fv = px.bar(
                    top_fv,
                    x="apt_name", y="fv_premium_%",
                    color="verdict",
                    color_discrete_map=color_map,
                    labels={"apt_name": "단지명", "fv_premium_%": "현재가-적정가 (%)"},
                    title=f"전세가율 역산 적정가 대비 고/저평가 (목표 전세가율 {int(fv_jeonse_ratio*100)}%)",
                )
                fig_fv.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_fv.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_fv, width='stretch')

        # ── ② 수익률 역산 ────────────────────────────────────────────────
        with fv_method2:
            st.markdown("#### 임대수익률 역산법")
            st.caption(
                "적정 매매가 = (월세 × 12) ÷ 목표 수익률. "
                "월세 거래 데이터가 있는 단지만 표시됩니다. "
                "수익률이 낮을수록 적정가가 높아짐(저평가로 판정)."
            )
            with st.container(border=True):
                c1, c2 = st.columns(2)
                fv_yield_pct = c1.slider(
                    "목표 임대수익률 (%)", 1.0, 8.0, 3.5, step=0.5, key="fv_yield_pct",
                    help="서울 아파트 평균 3~4%. 높일수록 적정가 하향 → 더 많은 단지가 고평가로 분류.",
                )
                fv_y_months = c2.slider(
                    "분석 기간 (개월)", 6, 24, 12, key="fv_y_months",
                )

            fv_y = fair_value_by_yield(
                df_t, df_r,
                target_yield_pct=fv_yield_pct,
                months=fv_y_months,
            )

            if fv_y.empty:
                st.info("월세 데이터가 부족합니다. 해당 지역 월세 거래를 먼저 수집하세요.")
            else:
                show_cols = [
                    "apt_name", "area_bucket", "trade_median",
                    "monthly_median", "annual_rent",
                    "fair_value", "fv_premium_%", "verdict",
                ]
                show_cols = [c for c in show_cols if c in fv_y.columns]
                render_table(fv_y[show_cols], height=500)

                top_fy = fv_y.head(30).copy()
                color_map2 = {
                    "🔴 오버슈팅": "#ef4444",
                    "🟠 고평가":   "#f97316",
                    "🟡 적정":     "#eab308",
                    "🟢 저평가":   "#22c55e",
                    "🔵 심한저평가": "#3b82f6",
                }
                fig_fy = px.bar(
                    top_fy,
                    x="apt_name", y="fv_premium_%",
                    color="verdict",
                    color_discrete_map=color_map2,
                    labels={"apt_name": "단지명", "fv_premium_%": "현재가-적정가 (%)"},
                    title=f"수익률 역산 적정가 대비 고/저평가 (목표 수익률 {fv_yield_pct}%)",
                )
                fig_fy.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_fy.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_fy, width='stretch')

        # ── ③ 이동평균 비교 ──────────────────────────────────────────────
        with fv_method3:
            st.markdown("#### 평당가 이동평균 비교법")
            st.caption(
                "현재 평당가 vs N개월 이동평균. "
                "이동평균을 '내재 가치'로 보고 얼마나 괴리됐는지 측정."
            )
            ma_months = st.slider("이동평균 기간 (개월)", 6, 36, 24, key="fv_ma_months")

            st.markdown("##### 지역 전체 월별 추이")
            trend = fair_value_ppp_trend(df_t, ma_months=ma_months)
            if trend.empty:
                st.info("이동평균 계산에 필요한 데이터가 부족합니다 (최소 6개월 이상).")
            else:
                # 라인 차트 (구성효과 보정된 tracked_ppp 기준 — avg_ppp는 원본 참고용, 표에만 노출)
                fig_trend = px.line(
                    trend,
                    x="ym", y=["tracked_ppp", "ma_ppp"],
                    labels={"ym": "년월", "value": "평당가 (만원/평)", "variable": "구분"},
                    title=f"평당가 vs {ma_months}개월 이동평균",
                    color_discrete_map={"tracked_ppp": "#3b82f6", "ma_ppp": "#f97316"},
                )
                newnames = {"tracked_ppp": "월 평균평당가(추적보정)", "ma_ppp": f"{ma_months}개월 이동평균"}
                fig_trend.for_each_trace(lambda t: t.update(name=newnames.get(t.name, t.name)))
                st.plotly_chart(fig_trend, width='stretch')

                # 오버슈팅 바 차트 (최근 12개월)
                recent_trend = trend.tail(12).copy()
                color_vals = recent_trend["overshoot_%"].apply(
                    lambda v: "#ef4444" if v >= 10 else ("#f97316" if v >= 5 else ("#22c55e" if v <= -5 else "#eab308"))
                )
                fig_os = px.bar(
                    recent_trend,
                    x="ym", y="overshoot_%",
                    labels={"ym": "년월", "overshoot_%": "이동평균 대비 (%)"},
                    title=f"최근 12개월 이동평균 대비 오버슈팅/저평가",
                )
                fig_os.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_os.update_traces(marker_color=color_vals.tolist())
                st.plotly_chart(fig_os, width='stretch')

                show_trend = ["ym", "avg_ppp", "tracked_ppp", "ma_ppp", "overshoot_%", "verdict"]
                render_table(trend[show_trend], height=400)

            st.markdown("---")
            st.markdown("##### 단지별 이동평균 대비 오버슈팅")
            fv_apt = fair_value_apt_vs_ma(df_t, ma_months=ma_months, min_deals=3)
            if fv_apt.empty:
                st.info("단지별 분석에 필요한 데이터가 부족합니다.")
            else:
                show_apt_cols = ["apt_name", "recent_ppp", "ma_ppp", "overshoot_%", "verdict", "total_deals"]
                render_table(fv_apt[show_apt_cols], height=500)

                top_apt = fv_apt.head(25).copy()
                color_map3 = {
                    "🔴 오버슈팅": "#ef4444",
                    "🟠 고평가":   "#f97316",
                    "🟡 적정":     "#eab308",
                    "🟢 저평가":   "#22c55e",
                    "🔵 심한저평가": "#3b82f6",
                }
                fig_apt = px.bar(
                    top_apt,
                    x="apt_name", y="overshoot_%",
                    color="verdict",
                    color_discrete_map=color_map3,
                    labels={"apt_name": "단지명", "overshoot_%": "이동평균 대비 (%)"},
                    title=f"단지별 이동평균({ma_months}개월) 대비 오버슈팅 TOP25",
                )
                fig_apt.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_apt.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_apt, width='stretch')

        st.markdown("---")
        st.caption(
            "> 이 분석은 투자 판단을 돕기 위한 의사결정 보조 자료이며, "
            "최종 매수·매도 결정은 공식 실거래 데이터, 현장 확인, 금융·세무 전문가 상담 후 내려야 합니다."
        )


def _render_region_detail(region_code: str, rec_df: pd.DataFrame | None = None,
                          sent_df: pd.DataFrame | None = None):
    """선택된 지역의 모든 지표를 한 화면에 표시.

    rec_df=None이면 추천단지 TOP10 섹션 생략 (page_region 등 단일 지역 페이지용).
    sent_df=None이면 내부에서 매수심리 데이터를 자동 로드.
    """
    from src.analysis.recommend import _load_catalysts

    if sent_df is None:
        sent_df = _cached_region_sentiment()

    region_name = REGION_MAP.get(region_code, region_code)
    st.markdown(f"#### 📍 {region_name}")

    # 매수심리 (지역 단위)
    if sent_df is not None and not sent_df.empty and region_code in sent_df["region_code"].values:
        row = sent_df[sent_df["region_code"] == region_code].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("매수심리 점수", f"{row['avg_sentiment']:.1f} / 100",
                  delta="강세" if row['avg_sentiment'] >= 60 else ("약세" if row['avg_sentiment'] < 40 else "중립"))
        c2.metric("거래량 모멘텀", f"{row['avg_volume_momentum']:.2f} x",
                  help="1.0=평소, 2.0=2배 급증")
        c3.metric("가격 가속도", f"{row['avg_accel']:+.2f} %p",
                  help="최근 3mo 변화율 - 이전 3mo 변화율")
        c4.metric("호재점수(수동)", f"{row['manual_catalyst']:.0f} / 100")

    # 입주물량 (공급 부담)
    supply_units = supply_for_region(region_code, lookahead_months=12)
    supply_score = supply_pressure_score(region_code, lookahead_months=12)
    sc1, sc2 = st.columns(2)
    sc1.metric("향후 12개월 입주 예정", f"{supply_units:,} 호",
               help="등록된 분양 데이터 기준. config/supply.json")
    sc2.metric("공급 부담 지수", f"{supply_score:.1f} / 100",
               delta=("부담" if supply_score > 50 else "보통"),
               delta_color="inverse",
               help="높을수록 공급 과잉 (가격 상승에 불리)")

    # 등록된 호재 카드 형태로
    cat = _load_catalysts()
    items = cat.get("region_catalysts", {}).get(region_code, [])
    if items:
        st.markdown("**등록된 호재**")
        for c in items:
            st.markdown(f"- 🏷️ **[{c.get('type','?')}]** {c.get('name','')}  — 점수 {c.get('score',0)}")
    else:
        st.caption("⚠️ 이 지역에는 등록된 수동 호재가 없습니다. "
                   "config/catalysts.json 에 직접 추가 가능합니다.")

    # 이 지역에서 추천된 단지 TOP 10 (rec_df가 있을 때만 — 추천 페이지 컨텍스트)
    if rec_df is not None and not rec_df.empty:
        region_rec = rec_df[rec_df["region_code"] == region_code]
        if not region_rec.empty:
            st.markdown(f"**이 지역의 추천 단지 TOP 10**")
            cols = ["apt_name", "area_bucket", "trade_median", "required_equity",
                    "catalyst_score", "sentiment_score", "price_growth_%", "expected_roi_%"]
            cols = [c for c in cols if c in region_rec.columns]
            render_table(region_rec[cols].head(10))
