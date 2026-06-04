"""page_portfolio_strategy 함수 교체 스크립트"""
from pathlib import Path

src = Path(__file__).parent.parent / "src" / "ui" / "streamlit_app.py"
lines = src.read_text(encoding="utf-8").splitlines(keepends=True)

NEW_FUNC = '''def page_portfolio_strategy():
    """🏘️ 처분·매수 전략 — 내/파트너 부동산 처분 + 신규 매수 시나리오 + 타임라인."""
    from src.analysis.portfolio_strategy import (
        PropertyProfile, TargetProperty, plan_scenarios_multi,
    )
    from src.analysis.cashflow_timeline import build_timeline

    st.title("🏘️ 처분·매수 전략 플래너")
    st.caption("보유 부동산 전체를 처분하고 새 집을 사는 시나리오 · 타임라인 · 자금 흐름 분석")

    # ── 지역 목록 (코드→이름 올바르게 매핑) ─────────────────────
    region_flat: dict[str, str] = {}        # "서울 강남구" → "11680"
    for sido, subs in REGIONS.items():
        for code, name in subs.items():     # regions.json: {코드: 이름}
            region_flat[f"{sido} {name}"] = code

    region_options = sorted(region_flat.keys())

    def _rsel(label: str, key: str, default: str = "서울 강남구") -> str:
        idx = region_options.index(default) if default in region_options else 0
        sel = st.selectbox(label, region_options, index=idx, key=key)
        return region_flat[sel]

    TENANT_OPTS = ["직접거주", "전세", "월세", "공실"]

    def _prop_block(prefix: str, default_region: str = "서울 강남구",
                    default_buy: int = 50_000, default_est: int = 80_000,
                    default_loan: int = 20_000) -> dict:
        name = st.text_input("단지명", value="", key=f"{prefix}_name",
                             placeholder="예: 반포자이")
        code = _rsel("지역", f"{prefix}_region", default_region)
        buy  = st.number_input("매수가 (만원)", min_value=0, value=default_buy,
                               step=1_000, key=f"{prefix}_buy")
        est  = st.number_input("현재 추정 시세 (만원)", min_value=0, value=default_est,
                               step=1_000, key=f"{prefix}_est")
        loan = st.number_input("대출 잔액 (만원)", min_value=0, value=default_loan,
                               step=1_000, key=f"{prefix}_loan")
        c1, c2 = st.columns(2)
        with c1:
            hold = st.number_input("보유기간 (년)", min_value=0.0, value=5.0,
                                   step=0.5, key=f"{prefix}_hold")
        with c2:
            resi = st.number_input("실거주 기간 (년)", min_value=0.0, value=2.0,
                                   step=0.5, key=f"{prefix}_resi")
        sole = st.checkbox("1세대 1주택", value=True, key=f"{prefix}_sole",
                           help="이 집만 보유 중이면 체크 (양도세 비과세 판단)")
        adj  = st.checkbox("조정대상지역", value=True, key=f"{prefix}_adj")
        sur  = st.checkbox("다주택 중과 적용", value=False, key=f"{prefix}_sur")
        st.markdown("**임대 현황**")
        tenant = st.selectbox("유형", TENANT_OPTS, key=f"{prefix}_tenant")
        jdep = rdep = rmon = 0; cend = ""; buf = 2
        if tenant in ("전세", "월세"):
            if tenant == "전세":
                jdep = st.number_input("전세 보증금 (만원)", 0, value=0,
                                       step=1_000, key=f"{prefix}_jdep")
            else:
                rdep = st.number_input("월세 보증금 (만원)", 0, value=0,
                                       step=500, key=f"{prefix}_rdep")
                rmon = st.number_input("월세 (만원/월)", 0, value=0,
                                       step=10, key=f"{prefix}_rmon")
            c3, c4 = st.columns(2)
            with c3:
                ed = st.date_input("계약 만료일", key=f"{prefix}_end",
                                   value=date.today())
                cend = ed.isoformat() if ed else ""
            with c4:
                buf = st.number_input("이사 준비 기간 (개월)", 0, value=2,
                                      step=1, key=f"{prefix}_buf")
        return dict(
            label=name or prefix, region_code=code, apt_name=name,
            acquisition_price_man=float(buy), estimated_price_man=float(est),
            loan_balance_man=float(loan), hold_years=float(hold),
            residency_years=float(resi), is_sole_home=sole,
            is_adjusted_area=adj, multihome_surcharge=sur,
            tenant_type=tenant, jeonse_deposit_man=float(jdep),
            monthly_rent_deposit_man=float(rdep), monthly_rent_man=float(rmon),
            contract_end_date=cend, move_out_buffer_months=int(buf),
        )

    # ── 보유 부동산 수 조절 ──────────────────────────────────────
    if "n_mine" not in st.session_state:
        st.session_state["n_mine"] = 1
    if "n_partner" not in st.session_state:
        st.session_state["n_partner"] = 1

    st.markdown("### 1. 보유 부동산")
    col_a, col_b = st.columns(2)

    with col_a:
        hd, badd, bdel = st.columns([3, 1, 1])
        with hd:
            st.markdown(f"#### 내 부동산 ({st.session_state['n_mine']}채)")
        with badd:
            if st.button("＋", key="add_mine") and st.session_state["n_mine"] < 5:
                st.session_state["n_mine"] += 1
                st.rerun()
        with bdel:
            if st.button("－", key="del_mine") and st.session_state["n_mine"] > 1:
                st.session_state["n_mine"] -= 1
                st.rerun()
        kws_mine = []
        for i in range(st.session_state["n_mine"]):
            with st.container(border=True):
                if st.session_state["n_mine"] > 1:
                    st.markdown(f"**{i+1}번째**")
                kws_mine.append(_prop_block(f"mine_{i}",
                    default_region="서울 서초구" if i == 0 else "서울 강남구"))

    with col_b:
        hd2, badd2, bdel2 = st.columns([3, 1, 1])
        with hd2:
            st.markdown(f"#### 파트너 부동산 ({st.session_state['n_partner']}채)")
        with badd2:
            if st.button("＋", key="add_partner") and st.session_state["n_partner"] < 5:
                st.session_state["n_partner"] += 1
                st.rerun()
        with bdel2:
            if st.button("－", key="del_partner") and st.session_state["n_partner"] > 1:
                st.session_state["n_partner"] -= 1
                st.rerun()
        kws_partner = []
        for i in range(st.session_state["n_partner"]):
            with st.container(border=True):
                if st.session_state["n_partner"] > 1:
                    st.markdown(f"**{i+1}번째**")
                kws_partner.append(_prop_block(f"partner_{i}",
                    default_region="서울 마포구" if i == 0 else "서울 용산구"))

    # ── 목표 부동산 & 재무 ───────────────────────────────────────
    st.markdown("### 2. 목표 부동산 & 재무 정보")
    col_t, col_f = st.columns(2)

    with col_t:
        with st.container(border=True):
            st.markdown("#### 목표 부동산")
            t_name  = st.text_input("단지명/메모", value="", key="t_name",
                                    placeholder="예: 잠실엘스")
            t_code  = _rsel("목표 지역", "t_region", "서울 송파구")
            t_min   = st.number_input("목표 예산 하한 (만원)", 0, value=150_000,
                                      step=1_000, key="t_min")
            t_max   = st.number_input("목표 예산 상한 (만원)", 0, value=200_000,
                                      step=1_000, key="t_max")
            t_close = st.date_input("목표 잔금일 (비우면 자동)", value=None,
                                    key="t_close")

    with col_f:
        with st.container(border=True):
            st.markdown("#### 재무 정보")
            income   = st.number_input("연 소득 합산 (만원, 0=DSR 미계산)",
                                       0, value=0, step=500, key="income")
            ex_pay   = st.number_input("기존 월 원리금 (만원)",
                                       0, value=0, step=10, key="ex_pay")
            int_rent = st.number_input("임시 거주 월세 (만원/월, 시나리오A용)",
                                       0, value=0, step=10, key="int_rent")

    if st.button("시나리오 분석 실행", type="primary", use_container_width=True):
        from datetime import date as _date
        props_mine    = [PropertyProfile(**kw) for kw in kws_mine]
        props_partner = [PropertyProfile(**kw) for kw in kws_partner]
        target = TargetProperty(
            region_code=t_code,
            label=t_name or "목표 부동산",
            budget_min_man=float(t_min),
            budget_max_man=float(t_max),
        )
        result = plan_scenarios_multi(
            props_mine=props_mine,
            props_partner=props_partner,
            target=target,
            annual_income_man=float(income),
            existing_monthly_payment_man=float(ex_pay),
        )

        def _eok(v: float) -> str:
            return f"{v/10000:.2f}억" if abs(v) >= 10000 else f"{v:,.0f}만"

        rec = result["recommended_scenario"]
        tab1, tab2, tab3 = st.tabs(["💰 순수령액 & 매수력", "📋 시나리오 비교", "📅 타임라인 & 자금흐름"])

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
            m1, m2, m3, m4 = st.columns(4)
            with m1: st.metric("내 부동산 합계",  _eok(result["equity_mine_man"]))
            with m2: st.metric("파트너 합계",      _eok(result["equity_partner_man"]))
            with m3: st.metric("합산 자기자본",    _eok(result["combined_equity_man"]))
            with m4: st.metric("최대 매수 가능",   _eok(result["max_purchase_power_man"]))
            acq_t = result["target_acquisition_cost"]["total"]
            min_needed = t_min + acq_t; max_needed = t_max + acq_t
            total_power = result["combined_equity_man"] + result["effective_loan_man"]
            if total_power >= max_needed:
                st.success(f"목표 상한({_eok(t_max)}) 충분 — 부대비용({_eok(acq_t)}) 포함 충당 가능")
            elif total_power >= min_needed:
                st.warning(f"목표 하한({_eok(t_min)}) 가능 / 상한({_eok(t_max)}) 부족")
            else:
                st.error(f"목표 하한도 미달 — {_eok(min_needed - total_power)} 부족")

        with tab2:
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

        with tab3:
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
                    "임시거주":"🏨","월세수입":"💰","비용":"💸"}
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

'''

# page_portfolio_strategy 함수 범위: 1611~1954 (1-indexed) → 1610~1953 (0-indexed)
start_idx = next(i for i, l in enumerate(lines) if "def page_portfolio_strategy" in l)
end_idx   = next(i for i, l in enumerate(lines) if i > start_idx and l.startswith("def "))

before = lines[:start_idx]
after  = lines[end_idx:]

result_lines = before + [NEW_FUNC] + after
src.write_text("".join(result_lines), encoding="utf-8")
print(f"OK: replaced lines {start_idx+1}~{end_idx} → total {len(result_lines)} lines")
