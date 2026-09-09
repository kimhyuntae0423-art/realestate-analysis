"""🏘️ 처분·매수 전략 플래너 탭.

원래 단일 파일 `src/ui/pages/portfolio.py` (1065줄) 였던 것을 입력 UI + 탭 5개로
분리 (모듈화 4단계). 로직 변경 없이 이동만 했다.

호출부(`src/ui/streamlit_app.py`)는 `from src.ui.pages.portfolio import
page_portfolio_strategy` 그대로 동작한다.
"""
from __future__ import annotations
import streamlit as st

try:
    from src.analysis.portfolio_strategy import (  # noqa: F401
        PropertyProfile, TargetProperty, plan_scenarios_multi,
    )
    from src.analysis.cashflow_timeline import build_timeline  # noqa: F401
    _PORTFOLIO_OK = True
    _PORTFOLIO_ERR = ""
except Exception as _e:
    _PORTFOLIO_OK = False
    _PORTFOLIO_ERR = f"{type(_e).__name__}: {_e}"


def _build_context():
    """session_state 에 저장된 분석 결과를 탭 공용 컨텍스트로 복원."""
    from src.analysis.portfolio_strategy import recommend_sell_order as _rso
    from .context import PortfolioContext

    result = st.session_state["_port_result"]
    props_mine, props_partner, target = st.session_state["_port_props"]
    _pi = st.session_state["_port_inputs"]

    cash_seed = _pi["cash_seed"]

    # 탭 공용: 매도 순서·타임라인은 탭 밖에서 미리 계산
    order = _rso(
        props_mine=props_mine,
        props_partner=props_partner,
        sales_mine=result["sales_mine"],
        sales_partner=result["sales_partner"],
        target=target,
        current_cash_man=float(cash_seed),
    )

    return PortfolioContext(
        result=result,
        props_mine=props_mine,
        props_partner=props_partner,
        target=target,
        rec=result["recommended_scenario"],
        order=order,
        t_min=_pi["t_min"], t_max=_pi["t_max"], t_kb=_pi["t_kb"],
        t_close=_pi["t_close"], income=_pi["income"], ex_pay=_pi["ex_pay"],
        int_rent=_pi["int_rent"], cash_seed=cash_seed,
        my_cash_seed=_pi.get("my_cash_seed", cash_seed),
        partner_cash_seed=_pi.get("partner_cash_seed", 0),
        household_homes=_pi.get("household_homes", 1),
        buy_strategy=_pi.get("buy_strategy", "전량 매도 후 매수"),
    )


# ─────────────────────────────────────────────────────────────
# 처분·매수 전략 플래너 (임대 현황 + 자금 흐름 타임라인 포함)
# ─────────────────────────────────────────────────────────────
def page_portfolio_strategy():
    """🏘️ 처분·매수 전략 — 내/파트너 부동산 처분 + 신규 매수 시나리오 + 타임라인."""
    st.title("🏘️ 처분·매수 전략 플래너")
    if not _PORTFOLIO_OK:
        st.error(f"모듈 로드 실패 — 아래 에러를 캡쳐해서 공유해 주세요:\n\n```\n{_PORTFOLIO_ERR}\n```")
        return
    st.caption("보유 부동산 전체를 처분하고 새 집을 사는 시나리오 · 타임라인 · 자금 흐름 분석")

    # 모듈 로드 성공을 확인한 뒤에 import (실패 시 위 에러 메시지를 그대로 보여주기 위함)
    from . import inputs, tab_payout, tab_order, tab_scenario, tab_timeline, tab_listings

    inputs.render_inputs()

    if "_port_result" not in st.session_state:
        st.info("위 정보를 입력하고 **시나리오 분석 실행** 버튼을 누르세요.")
        return

    ctx = _build_context()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "💰 순수령액 & 매수력", "🏆 최적 매도 순서", "📋 시나리오 비교",
        "📅 타임라인 & 자금흐름", "🏠 추천 매물",
    ])

    with tab1:
        tab_payout.render(ctx)
    with tab2:
        tab_order.render(ctx)
    with tab3:
        tab_scenario.render(ctx)
    with tab4:
        tab_timeline.render(ctx)
    with tab5:
        tab_listings.render(ctx)
