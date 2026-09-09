"""탭 2 — 🏆 최적 매도 순서."""
from __future__ import annotations
import streamlit as st

from .context import PortfolioContext, _eok


def render(ctx: PortfolioContext):
    order = ctx.order  # 탭 바깥에서 미리 계산됨

    st.markdown("#### 전략적 매도 순서 추천")

    # ── 전략 요약 문단 ──────────────────────────────
    if order:
        with st.container(border=True):
            st.markdown("##### 전략 요약")
            st.markdown(order[0].get("strategy_summary", ""))

    st.divider()
    st.caption("아래는 각 물건별 상세 근거입니다.")

    # ── 순서별 카드 ──────────────────────────────────
    MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]
    for item in order:
        medal = MEDALS[min(item["rank"] - 1, 5)]
        rank_label = "먼저 파세요" if item["rank"] == 1 else (
            "마지막에 파세요" if item["rank"] == len(order) else f"{item['rank']}번째"
        )
        with st.expander(
            f"{medal} **{rank_label}** — {item['owner']}의 {item['label']}  "
            f"(순수령액 {_eok(item['net_man'])})",
            expanded=(item["rank"] == 1),
        ):
            # 수치 요약
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("순수령액", _eok(item["net_man"]))
            with c2:
                st.metric("양도세", _eok(item["tax_man"]),
                          help=item["tax_note"])
            with c3:
                color = "normal" if item["can_buy_target"] else "off"
                st.metric(
                    "이 시점 누적 자금", _eok(item["cumulative_cash_man"]),
                    delta="새 집 계약 가능" if item["can_buy_target"] else "아직 부족",
                    delta_color=color,
                )

            # 갱신 리스크 배너
            renewal = item.get("renewal", {})
            rl = renewal.get("risk_level", "none")
            if rl == "critical":
                st.error(f"🚨 **묵시적 갱신 위험** — {renewal.get('message','')}")
            elif rl == "high":
                st.warning(f"⚠️ **갱신 거절 통보 마감 임박** — {renewal.get('message','')}")
            elif rl == "medium" and renewal.get("days_to_deadline") is not None:
                st.info(f"📌 **갱신청구권 주의** — {renewal.get('message','')}")

            st.markdown("**왜 이 순서인가요?**")
            for ex in item.get("explains", item.get("reasons", [])):
                st.markdown(f"> {ex}")

            # 만약 이 순서대로 안 하면?
            if item["rank"] == 1 and len(order) > 1:
                with st.expander("만약 이 집을 나중에 팔면 어떻게 되나요?", expanded=False):
                    last_item = order[-1]
                    st.warning(
                        f"**{last_item['label']}를 먼저 팔고 {item['label']}를 나중에 파는 경우:**\n\n"
                        f"초기 자금이 {_eok(last_item['net_man'])}로 시작됩니다. "
                        f"{'이 금액으로 새 집 계약금을 낼 수 있지만, ' if last_item['can_buy_target'] else '이 금액만으로는 새 집 계약이 어렵고, '}"
                        f"{item['label']}의 {item['tenant_type']} 계약 문제가 해결되지 않은 상태에서 "
                        f"새 집과 기존 집을 동시에 보유하는 기간이 길어질 수 있습니다. "
                        f"취득세 중과(1주택 이상 상태에서 매수) 위험도 확인이 필요합니다."
                    )

    st.caption(
        "⚠️ 이 순서는 분석 모델 기반 참고용입니다. "
        "실제 매도 순서는 세무사·중개사와 함께 결정하세요."
    )
