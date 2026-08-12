"""🏘️ 처분·매수 전략 플래너 탭.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations
from datetime import date
import pandas as pd
import streamlit as st

from config.settings import (
    DEFAULT_CATALYST_WEIGHT, DEFAULT_TIER_WEIGHT, DEFAULT_PRESTIGE_WEIGHT,
)
from src.ui.shared import (
    REGIONS, REGION_MAP, render_table, naver_land_url,
    _cached_gap, _cached_yield, _cached_outright, _cached_investment,
)

try:
    from src.analysis.portfolio_strategy import (
        PropertyProfile, TargetProperty, plan_scenarios_multi,
    )
    from src.analysis.cashflow_timeline import build_timeline
    _PORTFOLIO_OK = True
    _PORTFOLIO_ERR = ""
except Exception as _e:
    _PORTFOLIO_OK = False
    _PORTFOLIO_ERR = f"{type(_e).__name__}: {_e}"
    # stub classes so the rest of the module parses
    class PropertyProfile: pass  # type: ignore
    class TargetProperty: pass   # type: ignore
    def plan_scenarios_multi(*a, **kw): return {}  # type: ignore
    def build_timeline(*a, **kw): return [], {}    # type: ignore


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

    _SIDO_LIST = list(REGIONS.keys())

    def _parse_region(default: str) -> tuple[str, str]:
        """'서울 강남구' → ('서울', '강남구'). 시/도 없으면 첫 번째 시/도."""
        parts = default.split(" ", 1)
        sido = parts[0] if parts[0] in _SIDO_LIST else _SIDO_LIST[0]
        gu = parts[1] if len(parts) > 1 else ""
        return sido, gu

    TENANT_OPTS = ["직접거주", "전세", "월세", "공실"]

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

    # ── session state 초기화 ──────────────────────────────────────
    if "n_mine" not in st.session_state:
        st.session_state["n_mine"] = 1
    if "n_partner" not in st.session_state:
        st.session_state["n_partner"] = 0   # 기본값: 파트너 없음
    if "show_partner" not in st.session_state:
        st.session_state["show_partner"] = False

    st.markdown("### 1. 보유 부동산")

    MINE_DEFAULTS    = ["충남 천안시 동남구", "서울 강남구", "경기 성남시 분당구", "서울 송파구", "서울 서초구"]
    PARTNER_DEFAULTS = ["서울 마포구", "서울 용산구", "서울 강동구", "인천 연수구", "경기 수원시 영통구"]

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

    from datetime import date as _date
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

    if "_port_result" not in st.session_state:
        st.info("위 정보를 입력하고 **시나리오 분석 실행** 버튼을 누르세요.")
        return

    result        = st.session_state["_port_result"]
    props_mine, props_partner, target = st.session_state["_port_props"]
    _pi           = st.session_state["_port_inputs"]
    t_min   = _pi["t_min"];  t_max   = _pi["t_max"];  t_kb    = _pi["t_kb"]
    t_close = _pi["t_close"]; income  = _pi["income"]; ex_pay  = _pi["ex_pay"]
    int_rent = _pi["int_rent"]; cash_seed = _pi["cash_seed"]
    my_cash_seed      = _pi.get("my_cash_seed", cash_seed)
    partner_cash_seed = _pi.get("partner_cash_seed", 0)
    household_homes   = _pi.get("household_homes", 1)
    buy_strategy      = _pi.get("buy_strategy", "전량 매도 후 매수")

    def _eok(v: float) -> str:
        return f"{v/10000:.2f}억" if abs(v) >= 10000 else f"{v:,.0f}만"

    rec = result["recommended_scenario"]

    # 탭 공용: 매도 순서·타임라인은 탭 밖에서 미리 계산
    from src.analysis.portfolio_strategy import recommend_sell_order as _rso
    _order = _rso(
        props_mine=props_mine,
        props_partner=props_partner,
        sales_mine=result["sales_mine"],
        sales_partner=result["sales_partner"],
        target=target,
        current_cash_man=float(cash_seed),
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "💰 순수령액 & 매수력", "🏆 최적 매도 순서", "📋 시나리오 비교",
        "📅 타임라인 & 자금흐름", "🏠 추천 매물",
    ])

    with tab1:
        st.markdown("#### 부동산별 매도 순수령액")
        rows = []
        for prop, sale in list(zip(props_mine, result["sales_mine"])) + list(zip(props_partner, result["sales_partner"])):
            rows.append({
                "소유자":      "나" if prop in props_mine else "파트너",
                "단지명":      prop.label,
                "임대":        sale.get("tenant_type", "-"),
                "시세":        _eok(sale["sale_price_man"]),
                "대출상환":    _eok(sale["loan_repay_man"]),
                "보증금반환":  _eok(sale.get("deposit_return_man", 0)),
                "중개비":      _eok(sale["broker_fee_man"]),
                "양도세(추정)": _eok(sale["capital_gains_tax_man"]),
                "순수령액":    _eok(sale["net_man"]),
                "양도세 판정": sale["tax_note"],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("⚠️ 양도세 추정값. 실제 세액은 세무사 확인 필수.")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        with m1: st.metric("내 부동산 합계",  _eok(result["equity_mine_man"]))
        with m2: st.metric("파트너 합계",      _eok(result["equity_partner_man"]))
        with m3: st.metric("👤 내 현금",       _eok(my_cash_seed),
                           help="직접 입력한 내 보유 현금")
        with m4: st.metric("👥 파트너 현금",   _eok(partner_cash_seed),
                           help="직접 입력한 파트너 보유 현금")
        with m5: st.metric("합산 자기자본",    _eok(result["combined_equity_man"]),
                           help="내 부동산 + 파트너 + 현금 합계")
        with m6: st.metric("최대 매수 가능",   _eok(result["max_purchase_power_man"]))
        acq_t = result["target_acquisition_cost"]["total"]
        min_needed = t_min + acq_t; max_needed = t_max + acq_t
        total_power = result["combined_equity_man"] + result["effective_loan_man"]
        if total_power >= max_needed:
            st.success(f"목표 상한({_eok(t_max)}) 충분 — 부대비용({_eok(acq_t)}) 포함 충당 가능")
        elif total_power >= min_needed:
            st.warning(f"목표 하한({_eok(t_min)}) 가능 / 상한({_eok(t_max)}) 부족")
        else:
            st.error(f"목표 하한도 미달 — {_eok(min_needed - total_power)} 부족")

        # ── 대출 한도 분석 ────────────────────────────────────
        bd = result.get("target_loan_breakdown", {})
        if bd:
            st.markdown("---")
            binding = bd["binding"]
            _cap_none = bd["cap_is_inf"] or bd.get("cap_limit_man", 0) >= 500_000_000

            # binding → 한국어 레이블
            _BINDING_KO = {"LTV": f"LTV {bd['ltv_pct']:.0f}%", "한도캡": "정책 상한", "DSR": "소득(DSR)"}
            _binding_name = _BINDING_KO.get(binding, binding)

            kb_note = (f"KB시세 {bd['kb_price_man']/10000:.2f}억 기준"
                       if t_kb > 0 else f"매매가 {t_max/10000:.1f}억 기준 (KB시세 미입력 — 실제보다 클 수 있음)")

            st.markdown(
                f"#### 대출 가능 금액  "
                f"<span style='font-size:13px;color:#888'>{kb_note}</span>",
                unsafe_allow_html=True,
            )
            st.caption(
                f"은행은 아래 세 조건을 동시에 적용하고, **그 중 가장 낮은 금액**만 대출합니다. "
                f"지금은 **{_binding_name} 조건**이 실제 한도를 결정하고 있습니다."
            )

            with st.container(border=True):
                # 행 1: 세 가지 제약 + 최종 대출 (4열)
                _c1, _c2, _c3, _c4 = st.columns(4)

                def _limit_label(name):
                    return "← 지금 이 한도 적용 중" if name == binding else "여유 있음"
                def _limit_color(name):
                    return "inverse" if name == binding else "off"

                with _c1:
                    st.metric(
                        f"① LTV {bd['ltv_pct']:.0f}% 한도",
                        f"{bd['ltv_limit_man']/10000:.2f}억",
                        delta=_limit_label("LTV"), delta_color=_limit_color("LTV"),
                        help=(f"KB시세 {bd['kb_price_man']/10000:.2f}억의 {bd['ltv_pct']:.0f}%까지 대출 가능. "
                              f"KB시세가 낮을수록 한도도 줄어듭니다."),
                    )
                with _c2:
                    if _cap_none:
                        st.metric("② 정책 상한", "없음 (비규제)",
                                   delta="해당없음", delta_color="off",
                                   help="비규제지역은 정부 한도캡 미적용입니다.")
                    else:
                        st.metric(
                            "② 정책 상한", f"{bd['cap_limit_man']/10000:.0f}억",
                            delta=_limit_label("한도캡"), delta_color=_limit_color("한도캡"),
                            help="규제지역 한도: 매매가 무관 flat 6억 (2026-07 대책).",
                        )
                with _c3:
                    if bd["dsr_limit_man"]:
                        st.metric(
                            "③ 소득(DSR) 한도", f"{bd['dsr_limit_man']/10000:.2f}억",
                            delta=_limit_label("DSR"), delta_color=_limit_color("DSR"),
                            help="연 소득의 40%를 원리금으로 낼 때 빌릴 수 있는 최대 금액. "
                                 "소득이 높거나 기존 부채가 적으면 한도가 올라갑니다.",
                        )
                    else:
                        st.metric("③ 소득(DSR) 한도", "미입력",
                                   delta="소득 입력 시 계산", delta_color="off",
                                   help="연 소득을 0으로 입력하면 DSR 계산이 생략됩니다.")
                with _c4:
                    st.metric(
                        "✅ 최종 대출 가능액",
                        _eok(bd["final_loan_man"]),
                        help=f"세 한도 중 가장 낮은 값 ({_binding_name} 기준).",
                    )

                st.divider()

                # 행 2: 실질 숫자 3가지
                _r1, _r2, _r3 = st.columns(3)
                with _r1:
                    st.metric(
                        "내가 직접 내야 할 돈",
                        _eok(bd["required_equity_man"]),
                        help="매매가 − 대출. 계약금·잔금으로 내 돈을 써야 하는 금액. 취득세·중개비는 별도.",
                    )
                with _r2:
                    st.metric(
                        "월 상환액 (30년 / 4.5%)",
                        f"{bd['monthly_payment_man']:,}만원",
                        help="원리금 균등 30년 기준. 실제 금리·만기에 따라 달라집니다.",
                    )
                with _r3:
                    st.metric(
                        "연간 이자 부담",
                        _eok(bd["annual_interest_man"]),
                        help="명목 금리 4.5% × 대출원금. 원금 상환 진행에 따라 매년 줄어듭니다.",
                    )

        # ── 자금 준비 로드맵 ────────────────────────────────
        st.markdown("---")
        st.markdown("#### 자금 준비 로드맵")
        equity = result["combined_equity_man"]
        loan   = result["effective_loan_man"]
        shortage_max = max(0, max_needed - (equity + loan))
        shortage_min = max(0, min_needed - (equity + loan))

        # binding 설명 — 무엇이 문제이고, 어떻게 풀 수 있는지
        if bd and binding == "DSR" and bd.get("dsr_limit_man"):
            st.warning(
                f"**🔴 DSR이 병목 — 소득이 대출 한도를 결정하고 있습니다.**  \n"
                f"현재 연 소득 기준 DSR 40% 한도: **{_eok(bd['dsr_limit_man'])}**  \n"
                f"→ **해결 방법**: ① 기존 부채 월납입({_eok(float(ex_pay))}/월)을 먼저 상환해 DSR 여유를 만들거나, "
                f"② 부부 공동명의로 소득 합산, ③ 2금융권(DSR 50%, 단 금리 높음) 검토"
            )
        elif bd and binding == "한도캡" and not _cap_none:
            st.warning(
                f"**🔴 정책 한도캡이 병목 — 개인 조건으로는 극복 불가합니다.**  \n"
                f"규제지역 최대 대출: **{_eok(bd['cap_limit_man'])}** (매매가 무관 flat, 2026-07 대책)  \n"
                f"→ **해결 방법**: ① 부족분({_eok(shortage_max)})을 자기자본으로 추가 준비, "
                f"② 비규제지역 검토 (한도캡 없음)"
            )
        elif bd and binding == "LTV":
            st.info(
                f"**🔵 LTV가 병목 — 자기자본을 늘릴수록 매수 가능 가격이 올라갑니다.**  \n"
                f"KB시세의 {bd['ltv_pct']:.0f}%만 대출 가능 → 나머지 {100 - bd['ltv_pct']:.0f}%는 자기자본으로 충당.  \n"
                f"→ **해결 방법**: ① 보유 부동산 매도로 현금 확보, "
                f"② 생애최초 요건 충족 시 규제지역 LTV 고정 70% 적용 확인"
            )

        # ── 규제지역 부가 경고 (2026-07 대책) ────────────────
        if bd:
            if bd.get("land_permit_required"):
                st.warning("🚧 목표 지역은 **토지거래허가구역**입니다. 일정 규모 이상 거래 시 허가가 필요하고, 갭투자(전세 승계)는 사실상 어렵습니다.")
            if bd.get("occupancy_required"):
                st.info("🏠 목표 지역은 **실거주 의무** 대상입니다. 주담대 실행 후 일정 기간 내 실입주해야 합니다.")
            if bd.get("refinance_restricted"):
                st.warning("🔒 다주택 상태로 매수 시 규제지역 신규 대출·만기 연장이 원칙적으로 제한됩니다.")

        # 자금 부족 여부 및 구체적 행동 지침
        if shortage_max > 0:
            st.error(
                f"**목표 상한({_eok(max_needed)}) 매수까지 부족: {_eok(shortage_max)}**  \n"
                f"현재 동원 가능 자금: 자기자본 {_eok(equity)} + 대출 {_eok(loan)} = {_eok(equity + loan)}"
            )
            st.markdown("**지금 할 수 있는 것:**")
            tips = []
            if bd and binding in ("LTV", "한도캡"):
                tips.append(f"✅ 추가 저축·투자로 자기자본 **{_eok(shortage_max)}** 확보 (가장 직접적)")
            if bd and binding == "DSR":
                tips.append(f"✅ 기존 부채 월납입({_eok(float(ex_pay))}/월) 조기 상환 → DSR 여유 확보")
                tips.append("✅ 2금융권(DSR 50%) 검토 — 단, 금리가 1~2%p 높아 월납입 부담 증가")
            tips.append(f"✅ 예산 하한({_eok(min_needed)})으로 목표 낮추기 — 부족분 {_eok(shortage_min)} 으로 줄어듦")
            tips.append("✅ 파트너 보유 부동산 추가 매도 또는 현금 기여 검토")
            for t in tips:
                st.markdown(f"- {t}")
        elif shortage_min > 0:
            gap = max_needed - min_needed
            st.warning(
                f"**목표 하한({_eok(min_needed)})은 가능하지만, 상한까지는 {_eok(gap)} 부족합니다.**  \n"
                f"현재 자금: {_eok(equity + loan)}"
            )
            st.markdown(
                f"- 예산 상한을 낮추거나, **{_eok(gap)}** 추가 저축으로 목표 상한도 달성 가능합니다."
            )
        else:
            st.success("현재 자금 계획으로 목표 상한도 충당 가능합니다.")

        st.caption(
            "이 분석은 의사결정 보조 자료입니다. "
            "실제 대출·세금은 은행·세무사와 함께 확인하세요."
        )

        # ── 시간순 실행 플랜 ─────────────────────────────────
        if _order:
            st.markdown("---")
            _is_temp2 = buy_strategy.startswith("새 집 먼저")
            if _is_temp2:
                st.markdown("#### 📅 시간순 실행 플랜 — 새 집 먼저 계약 후 순차 매도 (일시적 2주택)")
                st.info(
                    "**일시적 2주택 전략**: 새 집 계약금을 먼저 치르고, "
                    "기존 주택을 **3년 이내**에 순차 매도합니다.  \n"
                    "기존 집이 1주택 비과세 요건(보유 2년·거주 2년)을 충족하면 "
                    "매도 순서에 관계없이 비과세 적용이 가능합니다.  \n"
                    "⚠️ 새 집 취득 후 3년 초과하면 특례 소멸 → 반드시 세무사 확인."
                )
            else:
                st.markdown("#### 📅 시간순 실행 플랜 — 무엇을 언제, 어떤 순서로?")

            from datetime import date as _today_dt
            _today = _today_dt.today()
            MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]

            # 현재 직접거주 중인 집 목록
            _living_now = [p.label for p in list(props_mine) + list(props_partner)
                           if p.tenant_type == "직접거주"]

            # 현재 상태 표시
            _cash_str = _eok(float(cash_seed))
            _living_str = f" · 현재 거주: {', '.join(_living_now)}" if _living_now else ""
            st.info(f"**지금** — 보유 현금 **{_cash_str}**{_living_str}")

            # 일시적 2주택: 첫 번째 스텝으로 "새 집 계약" 표시
            if _is_temp2:
                with st.container(border=True):
                    _sc1, _sc2 = st.columns([4, 2])
                    with _sc1:
                        st.markdown("**🏠 Step 0 — 목표 아파트 계약 (계약금 지불)**")
                        st.caption("기존 주택 매도 전에 먼저 계약금을 넣어 새 집을 확보합니다.")
                        st.markdown(f"→ 이후 **3년 이내**에 아래 기존 주택들을 순차 매도")
                    with _sc2:
                        _contract_deposit = float(t_max) * 0.10  # 통상 10%
                        st.metric("계약금 (시세 10%)", _eok(_contract_deposit))
                        st.metric("현금 잔여", _eok(float(cash_seed) - _contract_deposit))
                st.markdown("<div style='text-align:center;color:#aaa;font-size:18px'>↓</div>",
                             unsafe_allow_html=True)

            for _i, _item in enumerate(_order):
                _medal = MEDALS[min(_i, 5)]

                # 매도 가능 시점
                _end = _item.get("contract_end_date") or ""
                _ttype = _item["tenant_type"]
                if _ttype in ("전세", "월세") and _end:
                    try:
                        from datetime import date as _dparse
                        _edt = _dparse.fromisoformat(_end)
                        _timing = f"{_edt.strftime('%Y년 %m월')} 계약 만료 후" if _edt > _today else "계약 만료 (즉시 가능)"
                    except Exception:
                        _timing = "계약 만료 후"
                elif _ttype == "공실":
                    _timing = "즉시 매도 가능 (공실)"
                elif _ttype == "직접거주":
                    _timing = "이사 준비 후 즉시"
                else:
                    _timing = "계약 조율 필요"

                # 이 집 팔고 나서 어디서 사나
                _after = [o for o in _order if o["rank"] > _item["rank"]]
                _next_home = next((o["label"] for o in _after if o["tenant_type"] == "직접거주"), None)
                if _ttype == "직접거주":
                    _move = f"→ **{_next_home}로 이사해 거주**" if _next_home else "→ **임시 전세·월세 필요** (목표 아파트 잔금 전까지)"
                else:
                    _cur_home = _living_now[0] if _living_now else None
                    # 팔고 나서도 남아있는 직접거주 집이 있으면 유지
                    _still_living = [o["label"] for o in _after if o["tenant_type"] == "직접거주"]
                    if _still_living:
                        _move = f"→ **{_still_living[0]} 계속 거주**"
                    elif _cur_home and _cur_home != _item["label"]:
                        _move = f"→ **{_cur_home} 계속 거주**"
                    else:
                        _move = "→ 거주지 별도 확보 필요"

                _can_buy = _item["can_buy_target"]

                with st.container(border=True):
                    _ca, _cb, _cc = st.columns([0.4, 3.5, 2])
                    with _ca:
                        st.markdown(f"<div style='font-size:28px;text-align:center'>{_medal}</div>",
                                     unsafe_allow_html=True)
                    with _cb:
                        st.markdown(f"**{_item['owner']}의 '{_item['label']}' 매도**")
                        st.caption(f"🕐 시점: {_timing}")
                        if _item.get("reasons"):
                            st.caption(f"이유: {' · '.join(_item['reasons'][:2])}")
                        st.markdown(_move)
                    with _cc:
                        st.metric("순수령액", _eok(_item["net_man"]))
                        st.metric("이후 누적 자금", _eok(_item["cumulative_cash_man"]))

                    if _can_buy:
                        st.success(f"✅ **이 시점부터 목표 아파트 계약 가능!** (누적 자금 {_eok(_item['cumulative_cash_man'])} + 대출 {_eok(result['effective_loan_man'])})")

                if _i < len(_order) - 1:
                    st.markdown("<div style='text-align:center;color:#aaa;font-size:18px'>↓</div>",
                                 unsafe_allow_html=True)

            # 최종 매수 단계
            _final_equity = _order[-1]["cumulative_cash_man"]
            _final_budget = _final_equity + result["effective_loan_man"]
            st.markdown("<div style='text-align:center;color:#aaa;font-size:18px'>↓</div>",
                         unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown("**🏠 최종 — 목표 아파트 매수**")
                _fc1, _fc2, _fc3 = st.columns(3)
                _fc1.metric("확보 자기자본", _eok(_final_equity))
                _fc2.metric("대출", _eok(result["effective_loan_man"]))
                _fc3.metric("총 예산", _eok(_final_budget))
                if _final_budget >= float(t_max):
                    st.success(f"목표 상한 {_eok(float(t_max))} 매수 가능 ✅")
                elif _final_budget >= float(t_min):
                    st.warning(f"목표 하한 {_eok(float(t_min))} 가능 / 상한까지 {_eok(float(t_max) - _final_budget)} 부족")
                else:
                    st.error(f"목표 하한 {_eok(float(t_min))}도 {_eok(float(t_min) - _final_budget)} 부족 — 추가 자금 마련 필요")

    # ══ TAB 2: 최적 매도 순서 ══════════════════════════════
    with tab2:
        order = _order  # 탭 바깥에서 미리 계산됨

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

    with tab3:
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

    with tab4:
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

    # ══ TAB 5: 추천 매물 ════════════════════════════════════
    with tab5:
        seed_man_port  = int(result["combined_equity_man"])
        dsr_cap_port   = result["dsr_loan_limit_man"]
        dsr_cap_man_port = float(dsr_cap_port) if dsr_cap_port > 0 else None
        # KB비율: 목표 KB시세 입력했으면 그걸로, 아니면 0.95 기본
        kb_ratio_port  = (t_kb / t_max) if (t_kb > 0 and t_max > 0) else 0.95

        st.markdown("### 🏠 이 자금으로 살 수 있는 집 추천")
        st.caption(
            f"분석된 자기자본 **{_eok(seed_man_port)}** 기준으로 "
            f"LTV·DSR·한도캡을 반영해 실제 매수 가능한 단지를 추천합니다."
        )

        with st.container(border=True):
            rc1, rc2, rc3, rc4 = st.columns(4)
            rec_strategy = rc1.selectbox(
                "전략", ["🚀 투자수익", "갭투자", "임대수익", "자가매입"],
                key="port_rec_strat",
                help="투자수익=레버리지 상승 노림 / 갭투자=전세끼고 / 임대수익=월세 / 자가매입=실거주",
            )
            rec_months  = rc2.slider("분석 기간 (개월)", 6, 36, 24, key="port_rec_mo")
            rec_min_deals = rc3.slider("최소 거래수",  10, 200, 30, step=10, key="port_rec_md")
            rec_top_n   = rc4.slider("추천 수", 5, 50, 20, key="port_rec_n")

        if seed_man_port <= 0:
            st.warning("자기자본이 0입니다. 보유 부동산 시세를 입력하세요.")
        else:
            with st.spinner("추천 계산 중..."):
                if rec_strategy == "🚀 투자수익":
                    rec_df = _cached_investment(
                        seed_man_port, rec_months, rec_min_deals,
                        "무주택", False, True,
                        catalyst_weight=DEFAULT_CATALYST_WEIGHT, tier_weight=DEFAULT_TIER_WEIGHT,
                        prestige_weight=DEFAULT_PRESTIGE_WEIGHT, dsr_cap_man=dsr_cap_man_port,
                    )
                elif rec_strategy == "갭투자":
                    rec_df = _cached_gap(
                        seed_man_port, rec_months, rec_min_deals,
                        "무주택", False, dsr_cap_man_port,
                    )
                elif rec_strategy == "임대수익":
                    rec_df = _cached_yield(
                        seed_man_port, rec_months, rec_min_deals,
                        "무주택", False, True, dsr_cap_man_port,
                    )
                else:
                    rec_df = _cached_outright(
                        seed_man_port, rec_months, rec_min_deals,
                        "무주택", False, True, dsr_cap_man_port,
                    )

            if rec_df is None or rec_df.empty:
                st.warning(
                    f"자기자본 {_eok(seed_man_port)}로 매수 가능한 매물이 없습니다. "
                    "보유 부동산 시세를 확인하거나 전략을 바꿔보세요."
                )
            else:
                # KB비율 재계산 (캐시 결과는 kb_ratio=1.0 기준)
                if kb_ratio_port < 0.99 and "trade_median" in rec_df.columns:
                    from src.analysis.loan import annotate_loan_columns
                    rec_df = annotate_loan_columns(
                        rec_df, seed_man_port, "무주택", False,
                        kb_ratio=kb_ratio_port, dsr_cap_man=dsr_cap_man_port,
                    )

                # 매수 가능 필터 + 취득비용 포함
                if "trade_median" in rec_df.columns:
                    from src.analysis.costs import total_acquisition_cost_man as _tacm2
                    rec_df = rec_df.copy()
                    rec_df["_acq2"] = rec_df["trade_median"].apply(
                        lambda p: _tacm2(p, "무주택", False)["total"]
                    )
                    if "required_equity" in rec_df.columns:
                        rec_df = rec_df[
                            (rec_df["required_equity"] > 0)
                            & (rec_df["required_equity"] + rec_df["_acq2"] <= seed_man_port)
                        ].drop(columns=["_acq2"]).reset_index(drop=True)

                if rec_df.empty:
                    st.warning(
                        f"부대비용 포함 시 자기자본 {_eok(seed_man_port)} 내 매물이 없습니다. "
                        "취득세·중개비까지 고려하면 실제 매수 가능 범위가 좁아집니다."
                    )
                    if dsr_cap_man_port:
                        st.caption(f"DSR 한도 {_eok(dsr_cap_man_port)} 적용 중")
                else:
                    rec_df["region"] = rec_df["region_code"].map(REGION_MAP).fillna(rec_df["region_code"])
                    rec_df["rank"] = range(1, len(rec_df) + 1)
                    rec_df["naver_url"] = [
                        naver_land_url(r.get("region"), r.get("apt_name"))
                        for r in rec_df.to_dict("records")
                    ]

                    # 전략별 컬럼 선택
                    base_cols = ["naver_url", "rank", "region", "apt_name",
                                 "trade_median", "required_equity", "loan_capacity",
                                 "area_bucket", "build_year", "score"]
                    if rec_strategy == "갭투자":
                        extra = ["deposit_median", "gap", "jeonse_ratio_%", "jeonse_risk"]
                    elif rec_strategy == "임대수익":
                        extra = ["deposit_median", "monthly_median", "annual_yield_%"]
                    else:
                        extra = ["price_growth_%", "expected_roi_%"]
                    show_cols = [c for c in base_cols + extra if c in rec_df.columns]

                    st.caption(
                        f"매수 가능 단지 {len(rec_df)}개 · "
                        f"KB시세 비율 {kb_ratio_port:.0%} 반영 · "
                        f"상위 {rec_top_n}개 표시"
                    )
                    render_table(rec_df[show_cols].head(rec_top_n), height=600)

                    st.caption(
                        "이 추천은 투자 판단 보조 자료입니다. "
                        "최종 결정은 공식 실거래 데이터·현장 확인·전문가 상담 후 내려야 합니다."
                    )
