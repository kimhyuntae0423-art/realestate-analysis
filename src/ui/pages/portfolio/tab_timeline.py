"""탭 4 — 📅 타임라인 & 자금흐름."""
from __future__ import annotations
from datetime import date as _date
import pandas as pd
import streamlit as st

from src.analysis.cashflow_timeline import build_timeline
from .context import PortfolioContext, _eok


def render(ctx: PortfolioContext):
    result, rec = ctx.result, ctx.rec
    props_mine, props_partner, target = ctx.props_mine, ctx.props_partner, ctx.target
    t_close, t_max, int_rent = ctx.t_close, ctx.t_max, ctx.int_rent

    sc_labels   = [s["label"] for s in result["scenarios"]]
    default_idx = next((i for i, l in enumerate(sc_labels) if l.startswith(rec)), 0)
    chosen      = st.selectbox("시나리오 선택", sc_labels, index=default_idx, key="tl_sc")
    closing     = t_close if t_close else None
    equity_needed = max(0.0, float(t_max) - result["effective_loan_man"])

    tl_events, tl_sum = build_timeline(
        props_mine=props_mine, props_partner=props_partner,
        sales_mine=result["sales_mine"], sales_partner=result["sales_partner"],
        target=target, scenario_label=chosen, today=_date.today(),
        interim_rent_man=float(int_rent),
        target_closing_date=closing, equity_needed_man=equity_needed,
    )
    s1, s2, s3 = st.columns(3)
    with s1: st.metric("매도 수입 합계", _eok(tl_sum["total_in_man"]))
    with s2: st.metric("지출 합계",      _eok(tl_sum["total_out_man"]))
    with s3:
        ncf = tl_sum["net_cashflow_man"]
        st.metric("순 현금흐름", _eok(ncf))

    ICON = {"계약만료":"📋","매도":"💵","매수":"🏠",
            "임시거주":"🏨","월세수입":"💰","비용":"💸","갱신주의":"⚠️"}
    tl_rows = [{
        "시점":     e["ym"],
        "이벤트":   ICON.get(e["category"], "•") + " " + e["event"],
        "내용":     e["description"],
        "입금(만)": f"+{e['cash_in_man']:,.0f}"  if e["cash_in_man"]  else "-",
        "출금(만)": f"-{e['cash_out_man']:,.0f}" if e["cash_out_man"] else "-",
        "잔고(만)": f"{e['running_balance_man']:,.0f}",
        "비고":     e["note"],
    } for e in tl_events]

    if tl_rows:
        st.dataframe(pd.DataFrame(tl_rows), use_container_width=True, hide_index=True,
                     height=min(420, 55 + len(tl_rows) * 40))
    else:
        st.info("계약 만료일이나 임대 현황을 입력하면 타임라인이 생성됩니다.")

    if len(tl_events) >= 2:
        chart_df = pd.DataFrame([
            {"시점": e["ym"], "잔고(만원)": e["running_balance_man"]}
            for e in tl_events if e["cash_in_man"] or e["cash_out_man"]
        ])
        if not chart_df.empty:
            import plotly.express as px
            fig = px.bar(chart_df, x="시점", y="잔고(만원)",
                         title="시점별 누적 자금 잔고",
                         color="잔고(만원)",
                         color_continuous_scale=["#e74c3c","#f39c12","#2ecc71"],
                         height=300)
            fig.update_layout(showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "⚠️ 이 분석은 투자 판단을 돕기 위한 의사결정 보조 자료이며, "
        "최종 매수·매도 결정은 공식 실거래 데이터, 현장 확인, "
        "금융·세무 전문가 상담 후 내려야 합니다."
    )
