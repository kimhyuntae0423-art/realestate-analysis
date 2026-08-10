"""💎 저평가 매물 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
from datetime import date
import pandas as pd
import streamlit as st
import plotly.express as px

from src.analysis.fair_value import enrich_with_fair_value
from src.ui.shared import (
    REGION_MAP, render_table, naver_land_url,
    _personal_inputs_block, _cached_gap, _cached_yield,
)


def page_undervalued():
    """💎 저평가 매물 — 매수 가능 범위 내 저평가 단지 한눈에 보기."""
    st.title("💎 저평가 매물")
    st.caption(
        "내 예산으로 살 수 있는 매물 중 **전세가율·임대수익률 기반 적정가보다 저렴한 단지**만 추려줍니다. "
        "두 방법 중 더 저평가된 값으로 정렬."
    )

    with st.container(border=True):
        st.markdown("##### 👤 매수자 조건")
        p = _personal_inputs_block(key_prefix="uv")

    with st.container(border=True):
        st.markdown("##### 🎯 필터 조건")
        with st.form("uv_form", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            under_thresh = c1.slider(
                "적정가 대비 범위 (%)", min_value=-40, max_value=30, value=-5, step=1,
                help="0% 이하: 저평가(적정가보다 싼 것만) | 0~10%: 적정 구간 포함 | 10%↑: 다소 고평가까지 포함",
            )
            months = c2.slider("분석 기간 (개월)", 3, 36, 12)
            min_deals = c3.slider("최소 거래수", 1, 200, 30, step=10)

            c4, c5 = st.columns(2)
            fv_jeonse_ratio = c4.slider(
                "목표 전세가율 (%)", 50, 80, 65,
                help="갭투자 적정가 산식: 적정가 = 전세환산 중위가 ÷ 이 비율",
            ) / 100.0
            fv_yield_pct = c5.slider(
                "목표 임대수익률 (%)", 1.0, 8.0, 3.5, step=0.5,
                help="임대수익 적정가 산식: 적정가 = (월세 × 12) ÷ 이 수익률",
            )

            c6, c7 = st.columns(2)
            uv_area_range = c6.slider(
                "전용면적 범위 (㎡)", min_value=0, max_value=200,
                value=(80, 110), step=5,
                help="기본 80~110㎡ (24~33평). 소형 구축 제외 목적.",
            )
            uv_year_range = c7.slider(
                "준공연도 범위", min_value=1970, max_value=date.today().year + 5,
                value=(date.today().year - 15, date.today().year + 5), step=1,
                help="오래된 구축 제외하려면 하한을 올리세요.",
            )

            submitted = st.form_submit_button(
                "🔍 저평가 매물 찾기", use_container_width=True, type="primary",
            )

    if not submitted and not st.session_state.get("uv_has_run", False):
        st.info("조건을 설정하고 **🔍 저평가 매물 찾기** 버튼을 누르세요.")
        return
    if submitted:
        st.session_state["uv_has_run"] = True

    seed_man = int(p["seed_eok"] * 10000)
    ownership = p["ownership"]
    first_time = p["first_time"]
    use_loan = p.get("use_loan", True)
    dsr_cap_man = p.get("dsr_cap_man")

    prog = st.progress(0, text="갭 데이터 검색 중…")
    try:
        gap_df = _cached_gap(seed_man, months, min_deals, ownership, first_time, dsr_cap_man)
        prog.progress(50, text="임대수익 데이터 검색 중…")
        yld_df = _cached_yield(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man)
        prog.progress(100, text="✅ 완료")

    # 전략 상위 단지만 유지 (면적·연도 필터 → top 50)
        def _prep_strategy(df: pd.DataFrame) -> pd.DataFrame:
            if df.empty:
                return df
            # 전략 상위 100개 먼저 자르고, 그 안에서 면적·연도 필터
            df = df.head(100).copy()
            if "area_bucket" in df.columns:
                df = df[(df["area_bucket"] >= uv_area_range[0]) & (df["area_bucket"] <= uv_area_range[1])]
            if "build_year" in df.columns:
                df = df[df["build_year"].isna() | ((df["build_year"] >= uv_year_range[0]) & (df["build_year"] <= uv_year_range[1]))]
            return df.reset_index(drop=True)

        gap_df = _prep_strategy(gap_df)
        yld_df = _prep_strategy(yld_df)
        prog.empty()
    except Exception as e:
        prog.empty()
        st.error(f"데이터 로드 오류: {e}")
        return

    rows_under = []

    if not gap_df.empty and "rent_median" in gap_df.columns:
        g_fv = enrich_with_fair_value(
            gap_df.copy(), jeonse_col="rent_median", target_jeonse_ratio=fv_jeonse_ratio,
        )
        g_fv["방법"] = "전세가율 역산"
        g_fv["지역"] = g_fv["region_code"].map(REGION_MAP).fillna(g_fv["region_code"])
        mask = g_fv["fv_premium_%"].notna() & (g_fv["fv_premium_%"] <= under_thresh)
        if mask.any():
            rows_under.append(g_fv[mask])

    if not yld_df.empty and "monthly_median" in yld_df.columns:
        y_fv = enrich_with_fair_value(
            yld_df.copy(), jeonse_col=None, monthly_col="monthly_median",
            target_yield_pct=fv_yield_pct,
        )
        y_fv["방법"] = "수익률 역산"
        y_fv["지역"] = y_fv["region_code"].map(REGION_MAP).fillna(y_fv["region_code"])
        mask = y_fv["fv_premium_%"].notna() & (y_fv["fv_premium_%"] <= under_thresh)
        if mask.any():
            rows_under.append(y_fv[mask])

    if not rows_under:
        st.warning(
            f"기준({under_thresh}% 이하)에 해당하는 저평가 매물이 없습니다. "
            "슬라이더를 올려보거나(예: 0%), 최소 거래수를 낮추거나, 분석 기간을 늘려보세요."
        )
        return

    _key_cols = ["apt_name", "region_code", "area_bucket"]
    combined = pd.concat(rows_under, ignore_index=True)
    combined = (
        combined.sort_values("fv_premium_%")
        .drop_duplicates(_key_cols, keep="first")
        .reset_index(drop=True)
    )

    # ── 면적·연도 필터 적용 ─────────────────────────────────────────────
    if "area_bucket" in combined.columns:
        combined = combined[
            (combined["area_bucket"] >= uv_area_range[0]) &
            (combined["area_bucket"] <= uv_area_range[1])
        ].copy()
    if "build_year" in combined.columns:
        combined = combined[
            combined["build_year"].isna() |
            ((combined["build_year"] >= uv_year_range[0]) &
             (combined["build_year"] <= uv_year_range[1]))
        ].copy()

    if combined.empty:
        st.warning("필터 조건에 맞는 저평가 매물이 없습니다. 면적·연도 범위를 조정해보세요.")
        return

    # ── 지역 필터 (폼 밖 — 즉시 반응) ─────────────────────────────────
    _all_regions_uv = sorted(combined["지역"].dropna().unique()) if "지역" in combined.columns else []
    if _all_regions_uv:
        uv_regions = st.multiselect(
            "지역 필터 (비워두면 전체)",
            options=_all_regions_uv,
            default=[],
            key="uv_regions",
            placeholder="지역을 선택하세요…",
        )
        if uv_regions:
            combined = combined[combined["지역"].isin(uv_regions)].copy()
        if combined.empty:
            st.info("선택한 지역에 해당하는 저평가 매물이 없습니다.")
            return

    # 요약 메트릭
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("저평가 매물 수", f"{len(combined)}개")
    mc2.metric("최대 저평가", f"{combined['fv_premium_%'].min():.1f}%")
    mc3.metric("평균 저평가", f"{combined['fv_premium_%'].mean():.1f}%")
    mc4.metric("최저 매매가", f"{combined['trade_median'].min()/10000:.2f}억")

    # 정렬 옵션
    sort_opt = st.radio(
        "정렬 기준",
        ["저평가도 높은 순", "추천점수 높은 순", "매매가 낮은 순"],
        horizontal=True, key="uv_sort",
    )
    if sort_opt == "추천점수 높은 순" and "score" in combined.columns:
        combined = combined.sort_values("score", ascending=False).reset_index(drop=True)
    elif sort_opt == "매매가 낮은 순":
        combined = combined.sort_values("trade_median").reset_index(drop=True)

    combined["rank"] = range(1, len(combined) + 1)
    combined["naver_url"] = [
        naver_land_url(r.get("지역"), r.get("apt_name"))
        for r in combined.to_dict("records")
    ]

    show_cols = [
        "naver_url", "rank", "지역", "apt_name", "area_bucket",
        "trade_median", "fair_value", "fv_premium_%", "verdict", "방법",
    ]
    if "gap" in combined.columns:            show_cols.append("gap")
    if "jeonse_ratio" in combined.columns:   show_cols.append("jeonse_ratio")
    if "annual_yield_%" in combined.columns: show_cols.append("annual_yield_%")
    if "score" in combined.columns:          show_cols.append("score")
    render_table(combined[[c for c in show_cols if c in combined.columns]], height=650)

    # 바 차트
    top_u = combined.head(30).copy()
    color_map_u = {"전세가율 역산": "#3b82f6", "수익률 역산": "#22c55e"}
    fig_u = px.bar(
        top_u, x="apt_name", y="fv_premium_%",
        color="방법", color_discrete_map=color_map_u,
        labels={"apt_name": "단지명", "fv_premium_%": "현재가-적정가 (%)"},
        title=f"저평가 TOP {min(30, len(top_u))} (낮을수록 더 저평가)",
        text="fv_premium_%",
    )
    fig_u.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_u.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_u.update_xaxes(tickangle=-45)
    st.plotly_chart(fig_u, width='stretch')

    st.caption(
        "> 이 분석은 투자 판단을 돕기 위한 의사결정 보조 자료이며, "
        "최종 매수·매도 결정은 공식 실거래 데이터, 현장 확인, 금융·세무 전문가 상담 후 내려야 합니다."
    )
