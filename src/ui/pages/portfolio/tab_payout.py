"""탭 1 — 💰 순수령액 & 매수력 (대출 한도 분석 · 자금 준비 로드맵 · 시간순 실행 플랜)."""
from __future__ import annotations
import pandas as pd
import streamlit as st

from .context import PortfolioContext, _eok


def render(ctx: PortfolioContext):
    result = ctx.result
    props_mine, props_partner = ctx.props_mine, ctx.props_partner
    my_cash_seed, partner_cash_seed = ctx.my_cash_seed, ctx.partner_cash_seed
    t_min, t_max, t_kb = ctx.t_min, ctx.t_max, ctx.t_kb
    ex_pay, cash_seed = ctx.ex_pay, ctx.cash_seed
    buy_strategy = ctx.buy_strategy
    _order = ctx.order

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
