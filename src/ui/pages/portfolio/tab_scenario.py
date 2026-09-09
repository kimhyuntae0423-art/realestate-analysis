"""탭 3 — 📋 시나리오 비교 + WRAP 체크리스트."""
from __future__ import annotations
import streamlit as st

from .context import PortfolioContext, _eok


def render(ctx: PortfolioContext):
    result, rec = ctx.result, ctx.rec

    for sc in result["scenarios"]:
        is_rec = sc["label"].startswith(rec)
        with st.expander(("✅ **[추천]** " if is_rec else "") + sc["label"], expanded=is_rec):
            st.markdown(f"_{sc['description']}_")
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.metric("자기자본",  _eok(sc["available_equity_man"]))
            with c2: st.metric("대출 한도", _eok(sc["loan_capacity_man"]))
            with c3: st.metric("최대 예산", _eok(sc["max_budget_man"]))
            with c4: st.metric("취득세 등", _eok(sc["acq_total_cost_man"]),
                               help=f"취득세 {_eok(sc['acquisition_tax_man'])} 포함")
            if sc["can_afford_target_max"]: st.success("목표 상한까지 매수 가능")
            elif sc["can_afford_target_min"]: st.warning("목표 하한 가능, 상한 부족")
            else: st.error("목표 하한도 자금 부족")
            col_r, col_tip = st.columns(2)
            with col_r:
                st.markdown("**위험 요소**")
                for r in sc["risks"]: st.markdown(f"- {r}")
            with col_tip:
                st.markdown("**실행 팁**")
                for tip in sc["tips"]: st.markdown(f"- {tip}")
    st.markdown("---")
    with st.container(border=True):
        st.markdown("##### WRAP 체크리스트")
        st.markdown("""
| | 질문 |
|---|---|
| **W** | 처분 외 대안(전세 유지, 일부만 매도)도 검토했나요? |
| **R** | 시세 추정값이 실제 호가·실거래와 일치하나요? |
| **A** | 지금 결정이 FOMO(시장 상승 공포)에 의한 건 아닌가요? |
| **P** | 매도가 20% 낮아도 자금 계획이 성립하나요? |
""")
