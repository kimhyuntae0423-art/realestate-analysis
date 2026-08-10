"""🗺️ 지도 / 🚦 시장 진단 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
import pandas as pd
import streamlit as st
import plotly.express as px

from src.database.repository import fetch_trades_df
from src.analysis.macro import macro_dashboard
from src.ui.shared import (
    REGION_MAP, render_table, render_df,
    _cached_region_sentiment, _load_region_coords,
)


def _render_macro_signals():
    st.markdown("---")
    st.markdown("### 🚦 매크로 환경 신호등")
    st.caption("현재 시장 환경 6요인. 녹=우호 / 황=중립 / 적=불리")
    signals = macro_dashboard()
    cols = st.columns(len(signals))
    color_map = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    for col, sig in zip(cols, signals):
        with col:
            st.markdown(f"**{color_map[sig['level']]} {sig['name']}**")
            st.markdown(f"<span style='font-size:20px;font-weight:600'>{sig['value']}</span>",
                        unsafe_allow_html=True)
            st.caption(sig["detail"])


def page_map():
    """🗺️ 지도 페이지 — 전국 시각화."""
    st.title("🗺️ 전국 분포 지도")
    st.caption("시군구 중심 좌표 기준 평균 평당가(색) + 거래량(크기)")
    with st.container(border=True):
        c1, c2 = st.columns([1, 1])
        with c1:
            months = st.slider("최근 N개월", 3, 36, 12, key="map_months")
        with c2:
            st.caption("좌측 슬라이더로 분석 기간 조절. 지도 옵션은 아래.")
    render_map_tab(months)


def page_market_signals():
    """🚦 시장 진단 - 매크로 신호등 + 지역별 매수심리."""
    st.title("🚦 시장 진단")
    st.caption("현재 시장 환경 6요인 + 수도권 지역별 매수심리 순위")

    _render_macro_signals()

    st.markdown("---")
    st.markdown("### 📊 지역별 매수심리 순위 (수도권)")
    st.caption(
        "매수심리 점수 = 거래량 모멘텀(50%) + 가격 가속도(30%) + 평균-중위 격차(20%). "
        "100점에 가까울수록 매수세 강함 (KB 매수우위지수와 유사 개념)."
    )
    sent = _cached_region_sentiment()
    if sent.empty:
        st.info("표시할 데이터가 없습니다.")
        return
    disp = sent.copy()
    disp["region"] = disp["region_code"].map(REGION_MAP).fillna(disp["region_code"])
    disp = disp[[
        "region", "avg_sentiment", "manual_catalyst",
        "avg_volume_momentum", "avg_accel", "avg_skew",
        "n_complexes", "catalyst_text",
    ]].rename(columns={"catalyst_text": "등록호재"})
    render_table(disp, height=500)


def render_map_tab(months: int):
    """전국 매물 지도 — 시군구 중심 좌표 기반.

    각 시군구를 점으로 그리고, 색=평당가 / 크기=거래량.
    apt 단위 정확 좌표가 없어서 시군구 단위 집계 표시 (한계).
    """
    st.subheader("🗺️ 전국 거래 분포 지도")
    st.caption(
        "시군구 중심 좌표 기준 평균 평당가(색) + 거래량(크기). "
        "단지별 정확 좌표는 카카오 지오코딩 도입 시 추가 예정."
    )

    coords = _load_region_coords()
    if not coords:
        st.error("config/region_coords.json 이 없습니다.")
        return

    from datetime import date, timedelta
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        st.info("표시할 데이터가 없습니다.")
        return

    agg = df.groupby("region_code").agg(
        deals=("deal_amount", "count"),
        avg_ppp=("price_per_pyeong", "mean"),
        median_price=("deal_amount", "median"),
        apt_count=("apt_name", "nunique"),
    ).round(0).reset_index()

    rows = []
    for _, r in agg.iterrows():
        c = coords.get(r["region_code"])
        if not c:
            continue
        rows.append({
            "region_code": r["region_code"],
            "region": REGION_MAP.get(r["region_code"], r["region_code"]),
            "lat": c[0], "lon": c[1],
            "거래량": int(r["deals"]),
            "평당가(만원/평)": int(r["avg_ppp"] or 0),
            "중위매매가(억원)": round((r["median_price"] or 0) / 10000, 2),
            "단지수": int(r["apt_count"]),
        })
    map_df = pd.DataFrame(rows)
    if map_df.empty:
        st.info("좌표를 찾을 수 있는 지역이 없습니다.")
        return

    c1, c2, c3 = st.columns(3)
    metric = c1.selectbox(
        "색상 기준", ["평당가(만원/평)", "거래량", "중위매매가(억원)"], index=0,
    )
    style = c2.selectbox(
        "지도 스타일",
        ["open-street-map", "carto-positron", "carto-darkmatter"],
        index=1,
    )
    size_max = c3.slider("점 최대 크기", 20, 80, 40)

    fig = px.scatter_mapbox(
        map_df, lat="lat", lon="lon",
        hover_name="region",
        hover_data={
            "lat": False, "lon": False,
            "거래량": True, "평당가(만원/평)": True,
            "중위매매가(억원)": True, "단지수": True,
        },
        color=metric, size="거래량",
        color_continuous_scale="RdYlBu_r",
        size_max=size_max, zoom=8.5,
        mapbox_style=style,
        center={"lat": 37.55, "lon": 127.0},
        height=650,
    )
    fig.update_layout(margin={"r": 0, "t": 30, "l": 0, "b": 0})
    st.plotly_chart(fig, width='stretch')

    st.markdown("### 지역 요약 (테이블)")
    show = map_df.drop(columns=["lat", "lon", "region_code"]).sort_values("평당가(만원/평)", ascending=False)
    render_df(show, height=400)
