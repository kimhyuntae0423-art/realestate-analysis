"""매크로 타이밍 신호 패널 — 투자추천 배너와 시장진단 페이지 공용.

market_timing_signal()을 렌더링하는 로직을 한 곳에 모아 두 페이지가 서로 다른
문구/포맷으로 드리프트하지 않게 한다.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from src.ui.shared.cache import _cached_market_timing
from src.ui.shared.format import render_df


def _render_market_timing_panel(expanded: bool = False):
    timing = _cached_market_timing()
    if timing["score"] is None:
        st.info("매크로 타이밍 신호를 계산할 데이터가 부족합니다.")
        return
    score = timing["score"]
    if score >= 60:
        icon, label = "🟢", "우호적"
    elif score <= 40:
        icon, label = "🔴", "불리"
    else:
        icon, label = "🟡", "중립"
    with st.expander(f"{icon} 매크로 타이밍: {score}/100 ({label}) — 신호별 상세", expanded=expanded):
        st.caption(
            "실험실에서 검증된 국가 단위 신호 기준. 단기(1개월, 직접효과)와 장기"
            "(12~18개월, 정책 내생성 의심이라 낮은 가중치) 신호를 섞어 계산 — "
            "참고용이며 매수·매도 신호가 아님."
        )
        tdf = pd.DataFrame(timing["signals"])[
            ["label", "tier", "weight", "current_value", "percentile", "favorability", "as_of"]
        ]
        render_df(tdf)
