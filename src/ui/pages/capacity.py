"""💰 나의 한도 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
import streamlit as st

from src.ui.shared import _personal_inputs_block


def page_my_capacity():
    """💰 나의 한도 — 시드+대출+정책대출+부대비용 시뮬. 특정 매물 입력 전엔 계산하지 않음."""
    st.title("💰 나의 매수 한도")
    st.caption("관심 매물의 매매가·KB시세·지역을 입력하면 LTV·한도캡·DSR을 반영한 실제 대출 한도를 계산합니다")

    with st.container(border=True):
        st.markdown("##### 입력")
        p = _personal_inputs_block(key_prefix="cap")

    if p["use_dsr"] and p["dsr_cap_man"] is not None:
        st.info(f"💳 DSR 대출 한도 산정: **{p['dsr_cap_man']/10000:.2f} 억** "
                f"(연소득 {p['annual_income']:,}만 / 금리 {p['interest_rate']}% / 스트레스+3%)")

    # 특정 매물 대출 계산기 (매매가 미입력 시 계산 안 함)
    _render_loan_simulator(p)

    # 추가 안내
    st.markdown("---")
    st.markdown("### ℹ️ 어떻게 활용하나요?")
    st.markdown(
        "- **💰 나의 한도** 페이지: 관심 매물 하나를 정해 실제 대출 한도를 정밀 계산\n"
        "- **🚀 투자 추천** 페이지: 예산 내 실제 매물 후보 검색 (매물 미정 상태에서도 탐색 가능)\n"
        "- **📊 지역 분석** 페이지: 관심 지역 시세 추이·갭·수익률 등 깊이 분석\n"
        "- **🚦 시장 진단**: 매크로 환경 · 지역별 매수심리"
    )


def _render_loan_simulator(p: dict):
    """특정 매물 대출 계산기: KB시세 직접 입력 + binding 제약 표시 + 월납입액."""
    from src.analysis.loan import loan_breakdown_man, get_zone

    st.markdown("---")
    st.markdown("### 🎯 특정 매물 대출 계산기")
    st.caption(
        "관심 단지를 KB부동산 앱에서 확인 후 KB시세를 직접 입력하면 "
        "실제 대출 가능액과 **어떤 제약이 binding인지** 보여줍니다."
    )

    # 위 입력 블록에서 KB시세 직접 입력한 값이 있으면 자동 채워줌
    _kb_preset = p.get("kb_direct_man", 0)
    if _kb_preset > 0 and st.session_state.get("sim_kb", 0.0) == 0.0:
        st.session_state["sim_kb"] = float(_kb_preset / 10000)

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        price_eok = c1.number_input(
            "매매가 (억원)", min_value=0.0, max_value=300.0,
            value=0.0, step=0.5, format="%.1f", key="sim_price",
        )
        kb_eok = c2.number_input(
            "KB시세 (억원)", min_value=0.0, max_value=300.0,
            value=0.0, step=0.5, format="%.1f", key="sim_kb",
            help="KB부동산 앱 → 단지 검색 → 시세 탭 확인. 0 입력 시 매매가로 계산.",
        )

        REGION_OPTIONS = {
            "서울 전체 (규제)": "11680",
            "경기 기존규제 12곳": "41135",
            "경기 신규규제 3곳 (화성동탄·용인기흥·구리, 2026-07)": "41597",
            "비규제 (수도권 외·지방)": "99999",
        }
        region_label = c3.selectbox("지역 구분", list(REGION_OPTIONS.keys()), key="sim_region")
        region_code = REGION_OPTIONS[region_label]

        loan_years = st.slider("대출 만기 (년)", 10, 40, 30, key="sim_years")

    price_man = int(price_eok * 10000)
    kb_man = int(kb_eok * 10000) if kb_eok > 0 else None

    if price_man <= 0:
        st.caption("매매가를 입력하면 분석이 시작됩니다.")
        return

    bd = loan_breakdown_man(
        price_man=price_man,
        region_code=region_code,
        ownership=p["ownership"],
        first_time_buyer=p["first_time"],
        dsr_cap_man=p.get("dsr_cap_man"),
        kb_price_man=kb_man,
        interest_rate_pct=p["interest_rate"],
        loan_years=loan_years,
    )

    if not bd:
        return

    binding = bd["binding"]
    kb_used = bd["kb_price_man"]
    kb_note = (
        f"KB시세 {kb_used/10000:.2f}억 입력"
        if kb_man else
        f"KB시세 미입력 → 매매가 {price_eok:.1f}억 기준 (실제보다 대출 과대 추정 가능)"
    )

    # ── 세 제약 카드 ──────────────────────────────────────
    st.markdown("#### 제약별 대출 한도")
    st.caption(kb_note)

    col1, col2, col3 = st.columns(3)

    def _badge(name):
        return "🔴 binding" if name == binding else "✅ 여유"

    with col1:
        st.metric(
            f"① LTV {bd['ltv_pct']:.0f}% 한도",
            f"{bd['ltv_limit_man']/10000:.2f} 억",
            delta=_badge("LTV"),
            delta_color="off",
            help=f"담보가 {kb_used/10000:.2f}억 × LTV {bd['ltv_pct']:.0f}%",
        )
    with col2:
        cap_str = "없음 (비규제)" if bd["cap_is_inf"] else f"{bd['cap_limit_man']/10000:.0f} 억"
        st.metric(
            "② 한도 캡",
            cap_str,
            delta=_badge("한도캡") if not bd["cap_is_inf"] else "✅ 해당없음",
            delta_color="off",
            help="규제지역: 매매가 무관 flat 6억 (2026-07 대책)",
        )
    with col3:
        if bd["dsr_limit_man"] is not None:
            st.metric(
                "③ DSR 40% 한도",
                f"{bd['dsr_limit_man']/10000:.2f} 억",
                delta=_badge("DSR"),
                delta_color="off",
                help=f"연소득 {p.get('annual_income', 0):,}만원 기준 / 스트레스금리 +3%",
            )
        else:
            st.metric("③ DSR 한도", "미적용",
                      help="DSR 체크 시 소득 기반 한도 계산됨")

    # ── 최종 결과 ─────────────────────────────────────────
    st.markdown("#### 최종 결과")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("최종 대출",       f"{bd['final_loan_man']/10000:.2f} 억",
               help=f"{binding}이 binding")
    r2.metric("필요 자기자본",   f"{bd['required_equity_man']/10000:.2f} 억",
               help="매매가 − 최종 대출")
    r3.metric("월 원리금",       f"{bd['monthly_payment_man']:,} 만원",
               help=f"원리금 균등 {loan_years}년 / {bd['interest_rate_pct']}%")
    r4.metric("연 이자 (이자만)",f"{bd['annual_interest_man']/10000:.2f} 억",
               help="원금 미상환 시 연간 이자 비용")

    # ── binding 제약 설명 ─────────────────────────────────
    if binding == "DSR":
        st.warning(
            f"**DSR이 한계입니다.** 소득(연 {p.get('annual_income',0):,}만)으로는 "
            f"{bd['dsr_limit_man']/10000:.2f}억 이상 대출이 어렵습니다.  \n"
            "→ 기존 부채 상환, 소득 증빙 추가, 2금융권(DSR 50%) 검토로 한도를 늘릴 수 있습니다."
        )
    elif binding == "한도캡":
        st.warning(
            f"**정부 한도캡이 한계입니다.** LTV·소득과 무관하게 {bd['cap_limit_man']/10000:.0f}억이 최대입니다.  \n"
            "→ 이 제약은 개인 조건으로 극복 불가. 자기자본을 더 준비하거나 매물 가격대를 바꿔야 합니다."
        )
    else:  # LTV
        margin_to_cap = (
            (bd["cap_limit_man"] - bd["ltv_limit_man"]) / 10000
            if not bd["cap_is_inf"] else None
        )
        note = f" (한도캡까지 {margin_to_cap:.2f}억 여유)" if margin_to_cap and margin_to_cap > 0 else ""
        st.info(
            f"**LTV가 한계입니다{note}.** 담보가 기준 {bd['ltv_pct']:.0f}% 한도입니다.  \n"
            "→ KB시세를 높이는 것은 불가. 생애최초 여부나 보유주택 수를 재확인하세요."
        )

    # ── 규제지역 부가 경고 (2026-07 대책) ────────────────────
    if bd.get("land_permit_required"):
        st.warning(
            "🚧 **토지거래허가구역** — 일정 규모 이상 거래 시 시·군·구청 허가가 필요합니다. "
            "전세를 끼고 매수하는 갭투자는 사실상 어렵습니다."
        )
    if bd.get("occupancy_required"):
        st.info("🏠 **실거주 의무** — 주담대 실행 후 일정 기간 내 실입주해야 합니다. 갭투자 목적 매수는 제한됩니다.")
    if bd.get("refinance_restricted"):
        st.warning("🔒 **다주택자 대출 제한** — 규제지역 다주택자는 신규 주담대뿐 아니라 만기 연장도 원칙적으로 제한됩니다.")

    st.caption(
        "이 분석은 의사결정 보조 자료입니다. "
        "실제 대출은 은행별 내부 심사 기준·감정가 차이에 따라 달라질 수 있습니다."
    )
