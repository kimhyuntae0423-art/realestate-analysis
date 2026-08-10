"""💰 나의 한도 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
import streamlit as st

from src.analysis.costs import total_acquisition_cost_man, best_policy_loan
from src.analysis.loan import (
    max_purchase_man as calc_max_purchase,
    loan_capacity_man,
)
from src.ui.shared import _personal_inputs_block


def page_my_capacity():
    """💰 나의 한도 — 시드+대출+정책대출+부대비용 시뮬."""
    st.title("💰 나의 매수 한도")
    st.caption("자기자본·소득·LTV·DSR·정책대출·부대비용을 모두 반영한 최대 매수가")

    with st.container(border=True):
        st.markdown("##### 입력")
        p = _personal_inputs_block(key_prefix="cap")

    if p["use_dsr"] and p["dsr_cap_man"] is not None:
        st.info(f"💳 DSR 대출 한도 산정: **{p['dsr_cap_man']/10000:.2f} 억** "
                f"(연소득 {p['annual_income']:,}만 / 금리 {p['interest_rate']}% / 스트레스+3%)")

    # 헤드라인 카드
    _render_headline_card(p, p["seed_man"], p["dsr_cap_man"])

    # 특정 매물 대출 계산기
    _render_loan_simulator(p)

    # 추가 안내
    st.markdown("---")
    st.markdown("### ℹ️ 어떻게 활용하나요?")
    st.markdown(
        "- **💰 나의 한도** 페이지: 본인 자금으로 어디까지 살 수 있는지 한눈에 파악\n"
        "- **🚀 투자 추천** 페이지: 위 한도 내 실제 매물 후보 검색\n"
        "- **📊 지역 분석** 페이지: 관심 지역 시세 추이·갭·수익률 등 깊이 분석\n"
        "- **🗺️ 지도**: 전국 평당가·거래량 시각적 비교\n"
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
            value=10.0, step=0.5, format="%.1f", key="sim_price",
        )
        kb_eok = c2.number_input(
            "KB시세 (억원)", min_value=0.0, max_value=300.0,
            value=0.0, step=0.5, format="%.1f", key="sim_kb",
            help="KB부동산 앱 → 단지 검색 → 시세 탭 확인. 0 입력 시 매매가로 계산.",
        )

        REGION_OPTIONS = {
            "서울 전체 (규제)": "11680",
            "경기 규제 12곳": "41135",
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
            help="규제지역: 15억이하→6억 / 15~25억→4억 / 25억초과→2억",
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

    st.caption(
        "이 분석은 의사결정 보조 자료입니다. "
        "실제 대출은 은행별 내부 심사 기준·감정가 차이에 따라 달라질 수 있습니다."
    )


def _render_headline_card(inputs: dict, seed_man: int, dsr_cap_man: float | None):
    """최대 매수가 헤드라인 카드. 강남구 기준 예시 + 일반 비규제 기준 비교."""
    ownership = inputs["ownership"]
    first_time = inputs["first_time"]
    kb_ratio = inputs.get("kb_ratio", 1.0)
    # 정책대출은 부부합산 소득 기준
    household_income = inputs.get("household_income", inputs.get("annual_income", 0))
    is_couple = inputs.get("is_couple", False)
    is_newlywed = inputs.get("is_newlywed", False)
    children = inputs.get("children", 0)

    # 규제/비규제 양쪽 매수가능 최고가 (KB시세 비율 반영)
    try:
        p_reg = calc_max_purchase(
            float(seed_man), "11680", str(ownership), bool(first_time),
            float(dsr_cap_man) if dsr_cap_man is not None else None,
            float(kb_ratio),
        )
        p_nonreg = calc_max_purchase(
            float(seed_man), "99999", str(ownership), bool(first_time),
            float(dsr_cap_man) if dsr_cap_man is not None else None,
            float(kb_ratio),
        )
    except Exception as _e:
        st.error(
            f"**대출 계산 오류** — {type(_e).__name__}: {_e}\n\n"
            f"seed={seed_man!r} ({type(seed_man).__name__}), "
            f"ownership={ownership!r}, first_time={first_time!r}, "
            f"dsr_cap={dsr_cap_man!r} ({type(dsr_cap_man).__name__}), "
            f"kb_ratio={kb_ratio!r} ({type(kb_ratio).__name__})"
        )
        return

    # 부대비용 (규제/비규제 지역 각각 반영)
    costs = total_acquisition_cost_man(p_reg, ownership, first_time, is_adjusted_area=True)
    actual_p_reg = p_reg - costs["total"]
    actual_p_nonreg_costs = total_acquisition_cost_man(p_nonreg, ownership, first_time, is_adjusted_area=False)
    actual_p_nonreg = p_nonreg - actual_p_nonreg_costs["total"]

    # 정책대출 적격 (부부합산·신혼·자녀 반영)
    policy = best_policy_loan(
        household_income, p_reg, ownership,
        is_couple=is_couple, is_newlywed=is_newlywed,
        children=children, first_time_buyer=first_time,
    )

    st.markdown("## 💰 최대 매수 가능 시뮬레이션")

    # kb_direct_man 입력 시 아래 계산기와 연동 안내
    kb_direct_man = inputs.get("kb_direct_man", 0)
    if kb_direct_man > 0:
        st.info(
            f"💡 KB시세 **{kb_direct_man/10000:.1f}억** 입력 반영 → "
            "아래 '특정 매물 대출 계산기'에 자동 적용됩니다."
        )

    cc1, cc2 = st.columns([1, 1])
    with cc1:
        st.markdown("##### 🏙️ 규제지역 (서울25 + 경기12)",
                    help=(
                        "**서울** — 25개구 전체\n\n"
                        "**경기** — 12곳\n"
                        "수원시(장안·팔달·영통) · 성남시(수정·중원·분당) · "
                        "안양시(동안) · 광명시 · 과천시 · 하남시 · 용인시(처인·수지)\n\n"
                        "※ 2025-10-15 부동산 대책 기준, 2026-12-31까지 한시 적용"
                    ))
        st.metric("최대 매수가", f"{actual_p_reg/10000:.2f} 억",
                  help=f"부대비용 {costs['total']/10000:.2f}억 차감 후 실매수가")
        loan_reg = loan_capacity_man(p_reg, "11680", ownership, first_time, dsr_cap_man,
                                      kb_price_man=p_reg * kb_ratio)
        st.caption(
            f"매매가 {p_reg/10000:.2f}억 = 시드 {seed_man/10000:.1f}억 + 대출 {loan_reg/10000:.2f}억 - 부대비 {costs['total']/10000:.2f}억"
        )
        st.caption(
            f"취득세 {costs['acquisition_tax']/10000:.2f}억 · "
            f"중개 {costs['broker_fee']/10000:.2f}억 · "
            f"등기·이사 {costs['registration_etc']/10000:.2f}억"
        )

    with cc2:
        st.markdown("##### 🏞️ 비규제지역 (수도권 외곽 등)")
        st.metric("최대 매수가", f"{actual_p_nonreg/10000:.2f} 억",
                  help="LTV 70%로 더 큰 레버리지 가능")
        loan_nonreg = loan_capacity_man(p_nonreg, "99999", ownership, first_time, dsr_cap_man,
                                         kb_price_man=p_nonreg * kb_ratio)
        st.caption(
            f"매매가 {p_nonreg/10000:.2f}억 = 시드 {seed_man/10000:.1f}억 + 대출 {loan_nonreg/10000:.2f}억 - 부대비 {actual_p_nonreg_costs['total']/10000:.2f}억"
        )
        st.caption(
            f"취득세 {actual_p_nonreg_costs['acquisition_tax']/10000:.2f}억 · "
            f"중개 {actual_p_nonreg_costs['broker_fee']/10000:.2f}억 · "
            f"등기·이사 {actual_p_nonreg_costs['registration_etc']/10000:.2f}억"
        )

    # 정책대출 적격성 표시
    if policy["eligible"]:
        st.success(
            f"✅ **{policy['name']} 정책대출 적격** — 최대 {policy['max_loan_man']/10000:.1f}억 "
            f"@ 약 {policy['rate_pct']:.1f}% (일반 주담대보다 유리)"
        )
    else:
        with st.expander("ℹ️ 정책대출 적격성 (디딤돌/보금자리) — 불가 사유"):
            for name, r in policy["all_results"].items():
                st.markdown(f"- **{name}**: {'✅' if r['eligible'] else '❌'} {r['reason']}")
