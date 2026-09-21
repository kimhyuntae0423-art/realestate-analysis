"""지역 동조 패널 — 지역분석 페이지의 "이 지역과 같이 움직이는 지역".

계산 근거·한계는 src/analysis/co_movement.py docstring 참고.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from config.settings import CO_MOVEMENT_MIN_DEALS, CO_MOVEMENT_MIN_MONTHS
from src.analysis.co_movement import co_moving_regions
from src.ui.shared.cache import _cached_co_movement_base
from src.ui.shared.format import render_df
from src.ui.shared.regions import REGION_MAP


def _render_co_movement_panel(region_code: str):
    st.caption(
        "전국 공통 추세(금리 등)를 뺀 뒤, 이 지역과 **같은 달에** 같이 오르고 내린 지역입니다. "
        "선행 관계가 아니므로 'A가 올랐으니 B도 오른다'는 타이밍 신호로 쓰면 안 됩니다. "
        "가장 확실한 쓰임은 **분산 점검** — 아래 지역들을 함께 보유하면 지역이 달라도 "
        "같이 오르고 같이 떨어질 가능성이 큽니다."
    )
    # 전 지역 실거래를 읽어야 해서 첫 계산이 수십 초 걸린다 — 페이지를 열 때마다
    # 자동으로 돌지 않도록 토글로 연다. 키를 지역과 무관하게 둬서 지역을 바꿔도 유지된다.
    if not st.toggle("같이 움직이는 지역 계산하기", key="rg_comove",
                     help="처음 한 번은 전 지역 실거래를 읽느라 수십 초 걸립니다. 이후 1시간 캐시."):
        return

    R, price = _cached_co_movement_base()
    df, thr = co_moving_regions(R, region_code, top=10)
    if df.empty:
        st.info(
            f"이 지역은 월별 거래가 충분하지 않아 동조 분석 대상이 아닙니다 "
            f"(월 추적거래 {CO_MOVEMENT_MIN_DEALS}건 이상인 달이 "
            f"{CO_MOVEMENT_MIN_MONTHS}개월 이상 필요)."
        )
        return

    own = price.get(region_code)
    c1, c2, c3 = st.columns(3)
    c1.metric("이 지역 평당가 (최근 12개월 중위)", f"{own:,.0f} 만원" if pd.notna(own) else "—")
    c2.metric("우연 기준선", f"ρ = {thr:.3f}" if thr is not None else "—",
              help="시간축을 어긋나게 만든 가짜 데이터에서 1등 지역이 우연히 낼 수 있는 상관(95%).")
    c3.metric("분석 범위", f"{len(R)}개월 · {R.shape[1]}개 지역")

    n_above = int(df["above_chance"].sum())
    if n_above == 0:
        st.warning("우연 기준선을 넘는 지역이 없습니다 — 아래 순위는 잡음일 수 있으니 참고만 하세요.")

    disp = pd.DataFrame({
        "지역": df["region_code"].map(REGION_MAP).fillna(df["region_code"]),
        "동조 상관": df["corr"].round(3),
        "전반기": df["corr_first_half"].round(3),
        "후반기": df["corr_second_half"].round(3),
        "평당가(만원)": df["region_code"].map(price).round(0),
        "우연 기준선": df["above_chance"].map({True: "✅ 초과", False: "—"}),
    })
    render_df(disp)

    with st.expander("읽는 법 · 한계"):
        st.markdown(
            "- **동조 상관**: 전국 추세를 뺀 월별 가격 변화가 얼마나 같이 움직였는지(Spearman, −1~1).\n"
            "- **전반기 / 후반기**: 기간을 반으로 나눠 따로 계산한 값. 차이가 크면 최근에만 "
            "생긴 동조라 국면(규제·금리)이 바뀌면 사라질 수 있습니다.\n"
            "- **우연 기준선 초과**: 수십 개 지역 중 우연히 1등으로 나올 값보다도 높다는 뜻. "
            "넘지 못한 지역은 잡음과 구분되지 않습니다.\n"
            "- **평당가**: 2026-09 분석에서 동조는 지리(같은 시도)보다 **가격대가 비슷한 지역끼리** "
            "더 강하게 나타났습니다. 같은 매수층·같은 대출규제 기준선의 영향으로 추정되나 검증된 "
            "인과는 아닙니다.\n"
            f"- 표본이 {len(R)}개월뿐이라 개별 지역의 순위는 흔들릴 수 있습니다."
        )
    st.caption(
        "> 이 분석은 투자 판단을 돕기 위한 의사결정 보조 자료이며, "
        "최종 매수·매도 결정은 공식 실거래 데이터, 현장 확인, 금융·세무 전문가 상담 후 내려야 합니다."
    )
