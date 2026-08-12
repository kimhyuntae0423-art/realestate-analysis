"""개인 정보(자금·가구·대출조건) 공통 입력 폼.

src/ui/shared.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
import streamlit as st

from src.analysis.loan import dsr_loan_capacity_man


def _personal_inputs_block(key_prefix: str = "p") -> dict:
    """개인 정보 입력 블록 (한도/추천 페이지 공용).

    레이아웃: 3개 섹션 (자금 · 가구 · 대출 조건). 각 섹션은 3 컬럼 동일 그리드.
    """
    # ── 자금 ──────────────────────────────────────────
    st.markdown("**💰 자금**")
    c1, c2, c3 = st.columns(3)
    seed_eok = c1.number_input(
        "자기자본 시드 (억원)", min_value=0.1, max_value=200.0,
        value=2.5, step=0.5, format="%.1f", key=f"{key_prefix}_seed",
    )
    annual_income = c2.number_input(
        "본인 연소득 (만원)", min_value=0, max_value=100000,
        value=7500, step=500, key=f"{key_prefix}_inc",
        help="세전 연소득",
    )
    is_couple = c3.checkbox(
        "💑 기혼 (부부합산 소득 적용)", value=False, key=f"{key_prefix}_couple",
        help="체크 시 DSR·정책대출에 부부합산 소득 사용",
    )
    if is_couple:
        c1b, c2b, c3b = st.columns(3)
        spouse_income = c2b.number_input(
            "배우자 연소득 (만원)", min_value=0, max_value=100000,
            value=0, step=500, key=f"{key_prefix}_spouse",
        )
    else:
        spouse_income = 0

    # ── 가구 ──────────────────────────────────────────
    st.markdown("**👨‍👩‍👧 가구 정보**")
    c1, c2, c3 = st.columns(3)
    ownership = c1.selectbox(
        "보유 주택 수",
        ["무주택", "서민실수요자", "1주택(처분조건부)", "1주택(미처분)", "다주택"],
        key=f"{key_prefix}_own",
        help=(
            "서민실수요자: 무주택 + 소득·주택가 요건 충족자 (규제지역 LTV 60%)\n"
            "1주택(처분조건부): 기존 주택 처분 조건으로 규제지역 LTV 40% (무주택과 동일)\n"
            "1주택(미처분): 처분 조건 미충족 — 규제지역 신규 주담대 불가(LTV 0%)"
        ),
    )
    children = c2.number_input(
        "자녀 수", min_value=0, max_value=10, value=0, key=f"{key_prefix}_kids",
        help="2명 이상이면 정책대출 한도 우대",
    )
    with c3:
        first_time = st.checkbox(
            "생애최초 구매", key=f"{key_prefix}_ft",
            help="LTV 우대 (규제지역 고정 70%, 보유주택수와 무관 / 비규제 +10%p 가산)",
        )
        is_newlywed = st.checkbox(
            "🎀 신혼부부 (혼인 7년 이내)", key=f"{key_prefix}_new",
            disabled=not is_couple,
            help="기혼인 경우만. 정책대출 우대",
        )

    # ── 대출 조건 ────────────────────────────────────
    st.markdown("**🏦 대출 조건**")
    c1, c2, c3 = st.columns(3)
    interest_rate = c1.slider(
        "대출 금리 (%)", 2.0, 8.0, 4.5, 0.1, key=f"{key_prefix}_rate",
        help="신청 시점 명목 금리",
    )
    existing_debt_monthly = c2.number_input(
        "기존 부채 월 원리금 (만원)", min_value=0, max_value=2000,
        value=0, step=10, key=f"{key_prefix}_debt",
        help="신용·차·카드 등 월 원리금 합",
    )
    with c3:
        use_loan = st.checkbox(
            "대출 사용", value=True, key=f"{key_prefix}_loan",
            help="갭투자는 무관 (전세=임차인 부담)",
        )
        use_dsr = st.checkbox(
            "DSR 40% 적용", value=True, key=f"{key_prefix}_dsr",
            help="체크 권장. 미체크 시 LTV/한도cap만",
        )
    # KB시세 보정
    kbc1, kbc2 = st.columns([3, 2])
    kb_direct_eok = kbc1.number_input(
        "KB시세 직접 입력 (억원)", min_value=0.0, max_value=300.0,
        value=0.0, step=0.5, format="%.1f", key=f"{key_prefix}_kb_direct",
        help="KB부동산 앱 → 단지 검색 → 시세 탭. 은행은 이 값 기준으로 LTV 계산. 0이면 오른쪽 비율 보정 사용.",
    )
    kb_ratio_pct = kbc2.slider(
        "KB시세/실거래가 (%)", min_value=75, max_value=100, value=90, step=1,
        key=f"{key_prefix}_kb",
        help="직접 입력이 없을 때 일괄 보정값. 기본 90%는 실제 범위(통상 90~97%)의 "
             "보수적인 하한값 — 매물 미정 상태에서 대출한도를 낙관적으로 부풀리지 않기 위함. "
             "특정 매물의 실제 KB시세를 알면 왼쪽에 직접 입력하세요.",
    )
    kb_ratio = kb_ratio_pct / 100
    kb_direct_man = int(kb_direct_eok * 10000) if kb_direct_eok > 0 else 0

    # 합산 소득 (DSR/정책대출 기준)
    household_income = annual_income + (spouse_income if is_couple else 0)

    # DSR 한도 즉시 계산 (가구 소득 기준)
    dsr_cap_man = None
    if use_dsr:
        dsr_cap_man = dsr_loan_capacity_man(
            annual_income_man=household_income,
            existing_monthly_payment_man=existing_debt_monthly,
            interest_rate_pct=interest_rate,
            dsr_limit_pct=40,
        )

    return dict(
        seed_eok=seed_eok, seed_man=int(seed_eok * 10000),
        ownership=ownership, first_time=first_time, use_loan=use_loan,
        annual_income=annual_income, spouse_income=spouse_income,
        household_income=household_income,
        is_couple=is_couple, is_newlywed=is_newlywed, children=children,
        existing_debt_monthly=existing_debt_monthly,
        interest_rate=interest_rate, use_dsr=use_dsr,
        dsr_cap_man=dsr_cap_man,
        kb_ratio=kb_ratio, kb_ratio_pct=kb_ratio_pct,
        kb_direct_man=kb_direct_man,
    )
