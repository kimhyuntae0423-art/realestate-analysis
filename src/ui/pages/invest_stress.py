"""🚀 투자 추천 탭 — 관심 단지 스트레스 테스트.

src/ui/pages/invest.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from src.analysis.scenario import project_5y_scenarios, stress_test
from src.ui.shared import render_df


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
