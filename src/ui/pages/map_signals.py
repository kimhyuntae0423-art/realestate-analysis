"""🚦 시장 진단 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
import streamlit as st

from src.analysis.macro import macro_dashboard
from src.ui.shared import (
    REGION_MAP, render_table,
    _cached_region_sentiment, _render_market_timing_panel,
)


def _render_macro_signals():
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


def page_market_signals():
    """🚦 시장 진단 - 매크로 타이밍(검증됨) + 참고 지표 6요인 + 지역별 매수심리."""
    st.title("🚦 시장 진단")
    st.caption("실험실에서 검증된 매크로 타이밍 신호 + 현재 시장 상태 참고 지표 + 수도권 지역별 매수심리 순위")

    st.markdown("### ✅ 검증된 매크로 타이밍 신호")
    _render_market_timing_panel(expanded=True)

    st.markdown("---")
    st.markdown("### 📋 참고 지표 (현재 시장 상태 — 예측력 검증 대상 아님)")
    st.caption(
        "'지금 상태가 어떤가'를 보여주는 서술적 지표입니다. 위 매크로 타이밍과 달리 실험실 "
        "상관관계 검증을 거치지 않았거나(거래량·가격 모멘텀·공급·규제), 검증 결과 선행지표가 "
        "아닌 것으로 확인됐습니다(전세가율) — 매수·매도 신호로 쓰지 마세요."
    )
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
