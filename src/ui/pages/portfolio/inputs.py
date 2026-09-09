"""처분·매수 전략 플래너 — 입력 UI (1. 보유 부동산 / 2. 살 집 & 재무).

`시나리오 분석 실행` 버튼까지 담당한다. 실행 결과는 session_state
(`_port_result` / `_port_props` / `_port_inputs`)에 저장한다.
"""
from __future__ import annotations
from datetime import date
import streamlit as st

from src.ui.shared import REGIONS
from src.analysis.portfolio_strategy import (
    PropertyProfile, TargetProperty, plan_scenarios_multi,
)

_SIDO_LIST = list(REGIONS.keys())

TENANT_OPTS = ["직접거주", "전세", "월세", "공실"]

MINE_DEFAULTS    = ["충남 천안시 동남구", "서울 강남구", "경기 성남시 분당구", "서울 송파구", "서울 서초구"]
PARTNER_DEFAULTS = ["서울 마포구", "서울 용산구", "서울 강동구", "인천 연수구", "경기 수원시 영통구"]


def _parse_region(default: str) -> tuple[str, str]:
    """'서울 강남구' → ('서울', '강남구'). 시/도 없으면 첫 번째 시/도."""
    parts = default.split(" ", 1)
    sido = parts[0] if parts[0] in _SIDO_LIST else _SIDO_LIST[0]
    gu = parts[1] if len(parts) > 1 else ""
    return sido, gu


def _prop_block(prefix: str, default_region: str = "서울 강남구",
                default_buy: int = 50_000, default_est: int = 80_000,
                default_loan: int = 20_000) -> dict:
    """컴팩트 2~3열 병렬 레이아웃으로 한 물건 입력 폼을 렌더링."""
    # 행 1: 단지명 + 시/도 + 시군구
    _def_sido, _def_gu = _parse_region(default_region)
    r1a, r1b, r1c = st.columns([2, 1.5, 1.5])
    with r1a:
        name = st.text_input("단지명", value="", key=f"{prefix}_name",
                             placeholder="예: 반포자이")
    with r1b:
        sel_sido = st.selectbox("시/도", _SIDO_LIST,
                                index=_SIDO_LIST.index(_def_sido),
                                key=f"{prefix}_region_sido")
    with r1c:
        _sub = REGIONS[sel_sido]
        _gus = list(dict.fromkeys(_sub.values()))
        _gu_idx = _gus.index(_def_gu) if _def_gu in _gus else 0
        sel_gu = st.selectbox("시군구", _gus, index=_gu_idx,
                               key=f"{prefix}_region_gu")
    code = {v: k for k, v in _sub.items()}.get(sel_gu, list(_sub.keys())[0])

    # 행 2: 매수가 / 현재 시세 / 대출 잔액
    r2a, r2b, r2c = st.columns(3)
    with r2a:
        buy = st.number_input("매수가(만원)", 0, value=default_buy,
                              step=1_000, key=f"{prefix}_buy")
    with r2b:
        est = st.number_input("현재 시세(만원)", 0, value=default_est,
                              step=1_000, key=f"{prefix}_est")
    with r2c:
        loan = st.number_input("대출 잔액(만원)", 0, value=default_loan,
                               step=1_000, key=f"{prefix}_loan")

    # 행 3: 취득일 / 실거주 / 체크박스 3개
    _5y_ago = date(date.today().year - 5, date.today().month, date.today().day)
    r3a, r3b, r3c, r3d, r3e = st.columns([1.8, 1.2, 1.3, 1.3, 1.3])
    with r3a:
        acq_date = st.date_input(
            "취득일 (잔금 기준)", value=_5y_ago, key=f"{prefix}_acq",
            help="등기 완료일. 장기보유공제·단기양도세율·비과세 2년 요건에 직접 사용됩니다.",
        )
        hold = max(0.0, (date.today() - acq_date).days / 365.25)
        st.caption(f"보유 {hold:.1f}년 자동계산")
    with r3b:
        resi = st.number_input(
            "실거주(년)", 0.0, value=2.0, step=0.5, key=f"{prefix}_resi",
            help="주민등록 전입 기준 실거주 기간. 조정지역 비과세는 2년 이상 필요.",
        )
    with r3c:
        sole = st.checkbox("1주택", value=True, key=f"{prefix}_sole",
                           help="이 집 매도 시점에 1세대 1주택인지 여부")
    with r3d:
        adj = st.checkbox("조정지역", value=True, key=f"{prefix}_adj")
    with r3e:
        sur = st.checkbox("중과 적용", value=False, key=f"{prefix}_sur",
                          help="다주택 양도세 중과 (현재 2026까지 배제 연장 중)")

    st.caption("임대 현황")
    # 행 4: 임대 유형 선택
    tenant = st.radio("", TENANT_OPTS, horizontal=True, key=f"{prefix}_tenant",
                      label_visibility="collapsed")

    jdep = rdep = rmon = 0; cend = ""; buf = 2
    renewal_used = False; notified = False

    if tenant in ("전세", "월세"):
        # 행 5: 보증금 계열
        if tenant == "전세":
            r5a, r5b, r5c = st.columns(3)
            with r5a:
                jdep = st.number_input("전세보증금(만원)", 0, value=0,
                                       step=1_000, key=f"{prefix}_jdep")
            with r5b:
                ed = st.date_input("계약 만료일", key=f"{prefix}_end",
                                   value=date.today())
                cend = ed.isoformat() if ed else ""
            with r5c:
                buf = st.number_input("이사 준비(개월)", 0, value=2,
                                     step=1, key=f"{prefix}_buf")
        else:
            r5a, r5b, r5c, r5d = st.columns(4)
            with r5a:
                rdep = st.number_input("보증금(만원)", 0, value=0,
                                      step=500, key=f"{prefix}_rdep")
            with r5b:
                rmon = st.number_input("월세(만원)", 0, value=0,
                                      step=10, key=f"{prefix}_rmon")
            with r5c:
                ed = st.date_input("계약 만료일", key=f"{prefix}_end",
                                   value=date.today())
                cend = ed.isoformat() if ed else ""
            with r5d:
                buf = st.number_input("이사 준비(개월)", 0, value=2,
                                     step=1, key=f"{prefix}_buf")

        # 행 6: 갱신청구권 체크박스
        r6a, r6b = st.columns(2)
        with r6a:
            renewal_used = st.checkbox(
                "갱신청구권 이미 사용됨",
                value=False, key=f"{prefix}_renewal_used",
                help="임차인이 이전 계약에서 갱신청구권을 이미 사용한 경우")
        with r6b:
            notified = st.checkbox(
                "갱신 거절 통보 완료",
                value=False, key=f"{prefix}_notified",
                help="임대인이 만료 2개월 전까지 갱신 안 함을 서면 통보한 경우")

        # 실시간 갱신 리스크 경고
        if cend and not renewal_used and not notified:
            from src.analysis.portfolio_strategy import calc_renewal_risk
            from dataclasses import dataclass as _dc
            @_dc
            class _P:
                tenant_type: str; contract_end_date: str
                renewal_right_used: bool; notified_nonrenewal: bool
            _risk = calc_renewal_risk(_P(tenant, cend, False, False))
            if _risk["risk_level"] == "critical":
                st.error(_risk["message"])
            elif _risk["risk_level"] == "high":
                st.warning(_risk["message"])
            elif _risk["risk_level"] == "medium" and _risk["days_to_deadline"] is not None:
                st.info(_risk["message"])

    return dict(
        label=name or prefix, region_code=code, apt_name=name,
        acquisition_price_man=float(buy), estimated_price_man=float(est),
        loan_balance_man=float(loan), hold_years=float(hold),
        residency_years=float(resi), is_sole_home=sole,
        is_adjusted_area=adj, multihome_surcharge=sur,
        tenant_type=tenant, jeonse_deposit_man=float(jdep),
        monthly_rent_deposit_man=float(rdep), monthly_rent_man=float(rmon),
        contract_end_date=cend, move_out_buffer_months=int(buf),
        renewal_right_used=renewal_used, notified_nonrenewal=notified,
    )


def render_inputs():
    """섹션 1·2 입력 UI + `시나리오 분석 실행` 버튼."""
    # ── session state 초기화 ──────────────────────────────────────
    if "n_mine" not in st.session_state:
        st.session_state["n_mine"] = 1
    if "n_partner" not in st.session_state:
        st.session_state["n_partner"] = 0   # 기본값: 파트너 없음
    if "show_partner" not in st.session_state:
        st.session_state["show_partner"] = False

    st.markdown("### 1. 보유 부동산")

    # ── 헤더 2행: 내 부동산 / 파트너 부동산 (동일 레이아웃) ────────
    h1, h2, h3, _hsp = st.columns([3, 1, 1, 5])
    with h1:
        st.markdown("##### 👤 내 부동산")
    with h2:
        if st.button("＋", key="add_mine", use_container_width=True, help="내 물건 추가"):
            if st.session_state["n_mine"] < 5:
                st.session_state["n_mine"] += 1
            st.rerun()
    with h3:
        if st.button("－", key="del_mine", use_container_width=True, help="내 물건 삭제"):
            if st.session_state["n_mine"] > 1:
                st.session_state["n_mine"] -= 1
            st.rerun()

    p1, p2, p3, p4, _psp = st.columns([0.25, 2.75, 1, 1, 5])
    with p1:
        show_partner = st.toggle(
            "", value=st.session_state["show_partner"],
            key="show_partner_toggle",
        )
    with p2:
        st.markdown(
            f"##### {'👥 파트너 부동산' if show_partner else '<span style=\"color:#aaa\">👥 파트너 부동산</span>'}",
            unsafe_allow_html=True,
        )
    with p3:
        _partner_add = st.button("＋", key="add_partner", use_container_width=True,
                                  help="파트너 물건 추가", disabled=not show_partner)
    with p4:
        _partner_del = st.button("－", key="del_partner", use_container_width=True,
                                  help="파트너 물건 삭제", disabled=not show_partner)

    st.session_state["show_partner"] = show_partner

    if show_partner and st.session_state["n_partner"] == 0:
        st.session_state["n_partner"] = 1
    if not show_partner:
        st.session_state["n_partner"] = 0

    if _partner_add and show_partner and st.session_state["n_partner"] < 5:
        st.session_state["n_partner"] += 1
        st.rerun()
    if _partner_del and show_partner and st.session_state["n_partner"] > 1:
        st.session_state["n_partner"] -= 1
        st.rerun()

    n_mine    = st.session_state["n_mine"]
    n_partner = st.session_state["n_partner"] if show_partner else 0

    kws_mine    = []
    kws_partner = []

    # ── 위→아래 순차 배치 (좌우 분리 없음) ────────────────────────
    # 내 물건 먼저, 파트너 물건 그 아래
    for i in range(n_mine):
        label = f"👤 내 {i+1}번째 부동산" if n_mine > 1 else "👤 내 부동산"
        with st.expander(label, expanded=True):
            kws_mine.append(_prop_block(
                f"mine_{i}",
                default_region=MINE_DEFAULTS[i % len(MINE_DEFAULTS)],
            ))

    if show_partner and n_partner > 0:
        st.divider()
        for i in range(n_partner):
            label = f"👥 파트너 {i+1}번째 부동산" if n_partner > 1 else "👥 파트너 부동산"
            with st.expander(label, expanded=True):
                kws_partner.append(_prop_block(
                    f"partner_{i}",
                    default_region=PARTNER_DEFAULTS[i % len(PARTNER_DEFAULTS)],
                ))

    # ── 목표 부동산 & 재무 ───────────────────────────────────────
    st.divider()
    st.markdown("### 2. 살 집 & 재무 정보")

    with st.container(border=True):
        st.markdown("#### 🏡 살 집 (목표 부동산)")
        _t_def_sido, _t_def_gu = _parse_region("서울 송파구")
        ca, cb, cc, cd, ce, cf, cg = st.columns([2, 1.2, 1.5, 1.5, 1.5, 1.5, 1.5])
        with ca:
            t_name = st.text_input("단지명/메모", value="", key="t_name",
                                   placeholder="예: 잠실엘스")
        with cb:
            t_sel_sido = st.selectbox("시/도", _SIDO_LIST,
                                      index=_SIDO_LIST.index(_t_def_sido),
                                      key="t_region_sido")
        with cc:
            _t_sub = REGIONS[t_sel_sido]
            _t_gus = list(dict.fromkeys(_t_sub.values()))
            _t_gu_idx = _t_gus.index(_t_def_gu) if _t_def_gu in _t_gus else 0
            t_sel_gu = st.selectbox("시군구", _t_gus, index=_t_gu_idx,
                                     key="t_region_gu")
            t_code = {v: k for k, v in _t_sub.items()}.get(t_sel_gu, list(_t_sub.keys())[0])
        with cd:
            t_min = st.number_input("예산 하한 (만원)", 0, value=150_000,
                                    step=1_000, key="t_min")
        with ce:
            t_max = st.number_input("예산 상한 (만원)", 0, value=200_000,
                                    step=1_000, key="t_max")
        with cf:
            t_kb = st.number_input(
                "KB시세 (만원, 선택)", 0, value=0, step=1_000, key="t_kb",
                help="KB부동산 앱에서 목표 단지 시세 확인 후 입력. 0이면 예산 상한 기준으로 계산.",
            )
        with cg:
            t_close = st.date_input("희망 잔금일 (선택)", value=None,
                                    key="t_close")

    with st.container(border=True):
        st.markdown("#### 💰 자금 & 소득")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            my_cash_seed = st.number_input(
                "👤 내 현금 (만원)", 0, value=0, step=1_000, key="my_cash_seed",
                help="나의 현금·예금. 계약금으로 바로 쓸 수 있어요.",
            )
        with c2:
            partner_cash_seed = st.number_input(
                "👥 파트너 현금 (만원)", 0, value=0, step=1_000, key="partner_cash_seed",
                help="파트너의 현금·예금. 계약금으로 바로 쓸 수 있어요.",
            )
        with c3:
            income = st.number_input(
                "연 소득 합산 (만원)", 0, value=0, step=500, key="income",
                help="0 입력 시 DSR 대출 한도 계산 생략",
            )
        with c4:
            ex_pay = st.number_input(
                "기존 월 원리금 (만원)", 0, value=0, step=10, key="ex_pay",
                help="이미 갚고 있는 대출 원리금 (신규 주담대 제외)",
            )
        with c5:
            int_rent = st.number_input(
                "임시 거주 월세 (만원/월)", 0, value=0, step=10, key="int_rent",
                help="전체 매도 후 입주 전까지 임시로 살 곳의 월세",
            )
        cash_seed = my_cash_seed + partner_cash_seed
        st.caption(f"현금 합계 {cash_seed:,}만원 — 총 자기자본은 매도 순수령액 합산 후 계산됩니다.")

    with st.container(border=True):
        st.markdown("#### 🏠 주택 현황 & 매수 전략")
        _default_hh = len(kws_mine) + len(kws_partner)
        sx1, sx2, sx3 = st.columns(3)
        with sx1:
            household_homes = st.number_input(
                "가구 총 보유 주택 수 (본인 + 배우자 합산)", 1, 10,
                value=_default_hh, step=1, key="household_homes",
                help="등기 기준 모든 주택 합산. 1주택 비과세·중과 여부 자동 판단에 사용됩니다.",
            )
        with sx2:
            buy_strategy = st.radio(
                "매수 전략",
                ["전량 매도 후 매수", "새 집 먼저 계약 후 순차 매도 (일시적 2주택 특례)"],
                index=0, key="buy_strategy", horizontal=False,
                help=(
                    "**전량 매도 후 매수**: 기존 주택을 모두 팔고 새 집 계약. 자금 확보 확실, 임시 거주 필요.\n\n"
                    "**일시적 2주택**: 새 집 계약 → 기존 주택을 1~3년 내 매도. "
                    "기존 집이 1주택 비과세 요건 충족 시 세금 절감 가능. 단, 일시적으로 대출이 2건."
                ),
            )
        with sx3:
            if household_homes == 1:
                st.success("✅ 1주택: 비과세 요건(보유 2년·조정지역 거주 2년) 충족 시 양도세 없음")
            elif household_homes == 2:
                st.info(
                    "📌 2주택: 먼저 파는 집은 다주택 세율 적용.\n"
                    "마지막 남은 집이 비과세 요건 충족 시 혜택 적용 가능."
                )
            else:
                st.warning(
                    f"⚠️ {household_homes}주택: 중과 세율 적용 가능성 높음.\n"
                    "각 집의 '중과 적용' 체크박스로 개별 조정하세요."
                )
            if buy_strategy.startswith("새 집 먼저"):
                st.info(
                    "💡 일시적 2주택 특례:\n"
                    "새 집 취득 후 **3년 이내** 기존 주택 매도 시 기존 집에 1주택 비과세 적용 가능.\n"
                    "취득세도 1주택 세율(1~3%) 적용."
                )

    props_mine    = [PropertyProfile(**kw) for kw in kws_mine]
    props_partner = [PropertyProfile(**kw) for kw in kws_partner]
    _target_now = TargetProperty(
        region_code=t_code,
        label=t_name or "목표 부동산",
        budget_min_man=float(t_min),
        budget_max_man=float(t_max),
        kb_price_man=float(t_kb),
    )

    if st.button("시나리오 분석 실행", type="primary", use_container_width=True):
        result = plan_scenarios_multi(
            props_mine=props_mine,
            props_partner=props_partner,
            target=_target_now,
            annual_income_man=float(income),
            existing_monthly_payment_man=float(ex_pay),
            current_cash_man=float(cash_seed),
        )
        st.session_state["_port_result"]  = result
        st.session_state["_port_props"]   = (props_mine, props_partner, _target_now)
        st.session_state["_port_inputs"]  = dict(
            t_min=t_min, t_max=t_max, t_kb=t_kb, t_close=t_close,
            income=income, ex_pay=ex_pay, int_rent=int_rent, cash_seed=cash_seed,
            my_cash_seed=my_cash_seed, partner_cash_seed=partner_cash_seed,
            household_homes=household_homes, buy_strategy=buy_strategy,
        )
