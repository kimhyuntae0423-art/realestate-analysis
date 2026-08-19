"""🚀 투자 추천 탭 — 검색 조건 기반 단지 추천 결과 렌더링.

src/ui/pages/invest.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
from datetime import date
import pandas as pd
import streamlit as st

from config.settings import DEFAULT_TIER_WEIGHT, DEFAULT_PRESTIGE_WEIGHT
from src.analysis.location import is_kakao_ready, enrich_with_location
from src.ui.shared import (
    REGION_MAP, render_table, render_df, naver_land_url,
    _cached_gap, _cached_yield, _cached_outright, _cached_investment,
    _cached_region_sentiment, _cached_region_momentum, _render_market_timing_panel,
)
from src.ui.pages.invest_compare import _render_compare_view
from src.ui.pages.invest_stress import _render_stress_test


def render_recommend_tab(inputs: dict):
    seed_eok = inputs["seed_eok"]
    ownership = inputs["ownership"]
    first_time = inputs["first_time"]
    use_loan = inputs["use_loan"]
    strategy = inputs["strategy"]
    months = inputs["months"]
    min_deals = inputs["min_deals"]
    top_n = inputs["top_n"]
    catalyst_weight = inputs["catalyst_weight"]
    tier_weight = inputs.get("tier_weight", DEFAULT_TIER_WEIGHT)
    prestige_weight = inputs.get("prestige_weight", DEFAULT_PRESTIGE_WEIGHT)
    area_range = inputs.get("area_range")
    year_range = inputs.get("year_range")
    submitted = inputs["submitted"]
    use_dsr = inputs.get("use_dsr", False)
    # DSR 한도는 _personal_inputs_block 에서 이미 계산해서 전달
    dsr_cap_man = inputs.get("dsr_cap_man")
    kb_ratio = inputs.get("kb_ratio", 1.0)

    if not submitted and not st.session_state.get("rec_has_run", False):
        st.info(
            "위 **검색 조건**을 설정하고 **🔍 검색** 버튼을 누르세요."
        )
        return
    if submitted:
        st.session_state["rec_has_run"] = True

    # ─── 🌡️ 매크로 타이밍 진단 (WHEN축 — 국가 단위, 전략 무관) ───
    _render_market_timing_panel(expanded=False)

    seed_man = int(seed_eok * 10000)

    from src.analysis.loan import get_ltv_pct, max_purchase_man
    ltv_규제 = get_ltv_pct("11680", ownership, first_time)
    ltv_비규제 = get_ltv_pct("99999", ownership, first_time)
    max_buy_reg = max_purchase_man(seed_man, "11680", ownership, first_time, dsr_cap_man, kb_ratio) if use_loan else seed_man
    max_buy_nonreg = max_purchase_man(seed_man, "99999", ownership, first_time, dsr_cap_man, kb_ratio) if use_loan else seed_man

    from src.analysis.costs import total_acquisition_cost_man as _tacm
    from src.analysis.loan import loan_capacity_man as _lcm
    def _max_buy_net(seed, rc, own, ft, dsr, loan_ok, kr=kb_ratio):
        best = 0
        for p in range(1000, 300000, 1000):
            lv = _lcm(p, rc, own, ft, dsr, kb_price_man=p * kr) if loan_ok else 0
            eq = p - lv
            if eq > seed:
                break
            if eq + _tacm(p, own, ft)["total"] <= seed:
                best = p
        return best
    max_buy_reg_net    = _max_buy_net(seed_man, "11680", ownership, first_time, dsr_cap_man, use_loan)
    max_buy_nonreg_net = _max_buy_net(seed_man, "99999", ownership, first_time, dsr_cap_man, use_loan)
    costs_reg    = _tacm(max_buy_reg_net,    ownership, first_time)
    costs_nonreg = _tacm(max_buy_nonreg_net, ownership, first_time)


    from src.analysis.loan import load_regulations as _load_regs
    _reg_cap_man = _load_regs().get("loan_cap_man", {}).get("규제", {}).get("tier1_cap_man")
    if use_dsr and dsr_cap_man is not None and _reg_cap_man is not None and dsr_cap_man < _reg_cap_man:
        st.warning(
            f"⚠️ DSR 한도({dsr_cap_man/10000:.2f}억)가 LTV 한도({_reg_cap_man/10000:.2f}억)보다 작습니다. "
            "실제 대출은 DSR 쪽이 binding 됩니다."
        )

    if strategy == "🔀 전략 비교":
        _render_compare_view(
            seed_man=seed_man,
            months=months,
            min_deals=min_deals,
            ownership=ownership,
            first_time=first_time,
            use_loan=use_loan,
            catalyst_weight=catalyst_weight,
            tier_weight=tier_weight,
            prestige_weight=prestige_weight,
            dsr_cap_man=dsr_cap_man,
            top_n=top_n,
            area_range=area_range,
            year_range=year_range,
            max_buy_reg_net=max_buy_reg_net,
            max_buy_nonreg_net=max_buy_nonreg_net,
            kb_ratio=kb_ratio,
        )
        return

    if strategy == "🚀 투자수익":
        half_mo = max(months // 2, 3)
        with st.expander("💡 투자수익 전략 — 미래 상승을 노리는 레버리지 매수 (자세히)"):
            st.markdown(
                f"- 자금구조: 자기자본 {seed_eok}억 + **LTV 대출** = 매매가\n"
                f"- 매수 후 매도까지 보유 (실거주 또는 단순 보유)\n"
                f"- 매월 이자 부담 있음 (≈ 대출액 × 4~5% / 12)\n"
                f"- 종합점수 = **지역시장강도+호재(region_score)** × **{int(tier_weight*100)}%** + **대장단지(prestige_score)** × **{int(prestige_weight*100)}%**\n"
                f"- region_score = 시군구 평당가 시장강도 + 호재점수 × 호재가중치({int(catalyst_weight*100)}%) (100점 상한)\n"
                f"- 상급지등급(tier_score)은 참고 표시용이며 다중 시점 백테스트 결과에 따라 점수 산식에는 포함되지 않음\n"
                f"- 과거상승률·레버리지수익률·시드활용률도 점수에 포함되지 않고 별도 참고 지표로 표시\n"
                f"- 대장단지: 시군구 내 평당가 백분위(60%) + 동(dong) 평당가 백분위(40%). 그 지역의 1군 단지에 가산점.\n\n"
                f"📅 **수익률 기간 기준**: 분석기간 {months}개월 → 최근 **{half_mo}개월** vs 이전 **{half_mo}개월** 실거래 평당가 비교\n"
                f"- **예상평가차익·예상자기자본수익률은 연환산이 아닌 {half_mo}개월치 가격 변화율 × 레버리지**\n"
                f"- 연환산 참고치 = 표시값 ÷ {half_mo} × 12\n\n"
                f"⚙️ `config/catalysts.json`·`config/region_tiers.json` 직접 편집 가능"
            )
        rec = _cached_investment(seed_man, months, min_deals,
                                  ownership, first_time, use_loan, catalyst_weight,
                                  tier_weight, prestige_weight, dsr_cap_man)
        metric_col = "expected_roi_%"

        # 등록된 호재 보기
        from src.analysis.recommend import _load_catalysts, manual_catalyst_text
        with st.expander("📋 등록된 호재 목록 (config/catalysts.json)"):
            cat = _load_catalysts()
            rc = cat.get("region_catalysts", {})
            if not rc:
                st.write("등록된 호재 없음")
            else:
                rows = []
                for code, items in rc.items():
                    rname = REGION_MAP.get(code, code) if "REGION_MAP" in globals() else code
                    for c in items:
                        rows.append({
                            "지역": rname,
                            "유형": c.get("type", ""),
                            "내용": c.get("name", ""),
                            "점수": c.get("score", 0),
                        })
                render_df(pd.DataFrame(rows), height=400)
            st.caption("호재 추가/수정: `config/catalysts.json` 직접 편집. 저장 후 사이드바 [🔄 캐시 비우기].")
    elif strategy == "갭투자":
        st.info(
            f"💡 **갭투자 전략** — 전세 끼고 매수, 차익 노림수\n\n"
            f"- 자금구조: 자기자본 {seed_eok}억 = **매매가 − 전세보증금(갭)**\n"
            f"- 대출 X (전세보증금이 임차인 부담분) · 매월 이자 부담 없음\n\n"
            f"**종합점수 구성**\n"
            f"- 상급지 등급 80% — 백테스트 결과 단독 상관계수가 가장 높아 시세차익 예측의 핵심 지표\n"
            f"- 거래 활성도 20% — 유동성\n\n"
            f"- 전세가율·전세가율 추세·갭 레버리지 배수는 화면에 표시되지만 종합점수에는 포함되지 않음 "
            f"(백테스트에서 역상관 확인되어 제외, 역전세 위험 판정용으로만 사용)\n\n"
            f"⚠️ **역전세 리스크**: 전세가율 90%↑ 위험 · 83%↑ 또는 전세가 하락 추세 주의"
        )
        rec = _cached_gap(seed_man, months, min_deals, ownership, first_time, dsr_cap_man)
        metric_col = "gap"
    elif strategy == "임대수익":
        st.info(
            f"💡 **임대수익 전략**: 자기자본 + 보증금 + LTV 대출로 매수, 월세로 수익. "
            "필요자기자본 = 매매가 − 보증금중위 − 대출가능액."
        )
        rec = _cached_yield(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man)
        metric_col = "annual_yield_%"
    else:  # 자가매입
        st.info(
            f"💡 **자가매입 전략**: 자기자본(시드 {seed_eok}억) + LTV 대출로 매수. "
            "지역 평균 평당가 대비 저평가된 곳을 상위 배치."
        )
        rec = _cached_outright(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man)
        metric_col = "ppp_median"

    if rec.empty:
        st.warning(
            f"해당 조건을 만족하는 매물이 없습니다.\n\n"
            f"- 시드를 늘려보세요\n"
            f"- 분석 기간을 늘려보세요\n"
            f"- 최소 거래수를 낮춰보세요"
        )
        return

    # 부대비용 컬럼 추가 (모든 필터에 공통 사용)
    rec["_acq_cost"] = rec["trade_median"].apply(
        lambda p: _tacm(p, ownership, first_time)["total"]
    )
    # 🛡️ 안전망: 부대비용 포함 실제 현금(자기자본+부대비용) ≤ 시드
    if "required_equity" in rec.columns:
        rec = rec[(rec["required_equity"] > 0)
                  & (rec["required_equity"] + rec["_acq_cost"] <= seed_man)].reset_index(drop=True)
    elif "gap" in rec.columns:
        rec = rec[(rec["gap"] > 0)
                  & (rec["gap"] + rec["_acq_cost"] <= seed_man)].reset_index(drop=True)

    # 평형/준공연도 사용자 필터
    if area_range and "area_bucket" in rec.columns:
        a_lo, a_hi = area_range
        rec = rec[(rec["area_bucket"] >= a_lo) & (rec["area_bucket"] <= a_hi)].reset_index(drop=True)
    if year_range and "build_year" in rec.columns:
        y_lo, y_hi = year_range
        # build_year NaN 매물은 제외
        rec = rec[rec["build_year"].notna()
                  & (rec["build_year"] >= y_lo)
                  & (rec["build_year"] <= y_hi)].reset_index(drop=True)

    if rec.empty:
        st.warning(
            f"시드 {seed_eok}억 + 대출(LTV·DSR 반영)로 매수 가능한 매물이 없습니다.\n\n"
            f"- 규제지역 최대 매수가: **{max_buy_reg/10000:.2f}억**\n"
            f"- 비규제지역 최대 매수가: **{max_buy_nonreg/10000:.2f}억**\n\n"
            f"시드를 늘리거나 비규제지역을 검토하세요."
        )
        return

    # 지역명 컬럼 추가
    rec_disp = rec.copy()
    rec_disp["region"] = rec_disp["region_code"].map(REGION_MAP).fillna(rec_disp["region_code"])

    # KB시세 비율이 100% 미만이면 대출 컬럼 재계산 (캐시 결과는 kb_ratio=1.0 기준)
    if kb_ratio < 1.0 and "trade_median" in rec_disp.columns and "region_code" in rec_disp.columns:
        from src.analysis.loan import annotate_loan_columns
        rec_disp = annotate_loan_columns(
            rec_disp, seed_man, ownership, first_time,
            trade_col="trade_median", dsr_cap_man=dsr_cap_man, kb_ratio=kb_ratio,
        )
        if kb_ratio < 0.99:
            st.caption(
                f"💡 대출 계산 기준: KB시세 = 실거래가 × {kb_ratio:.0%} "
                f"(KB부동산 앱 미확인 시 실제 대출은 표시보다 적을 수 있음)"
            )

    # 입지 점수 (카카오 키 있을 때만 활성)
    if is_kakao_ready():
        cc1, cc2 = st.columns([1, 5])
        with cc1:
            enable_loc = st.checkbox("🚇 입지점수 계산", value=False,
                                      help="상위 TOP N 단지에 한해 카카오 API 호출 (캐시 사용)")
        with cc2:
            if enable_loc:
                st.caption(
                    "단지 주변 1km 지하철·학교·마트·병원 개수를 점수화 (캐시: data/processed/apt_locations.json)"
                )
        if enable_loc:
            rec_disp = enrich_with_location(rec_disp.head(top_n), max_calls=30,
                                              region_map=REGION_MAP)
    else:
        st.caption("💡 카카오 REST API 키를 .env 에 추가하면 입지점수 기능 활성화됩니다.")

    # 규제/비규제 실제 대출액 + 바인딩 요인 계산
    _loan_reg = max_buy_reg - seed_man
    _loan_nonreg = max_buy_nonreg - seed_man
    # LTV가 허용하는 대출 (시드 / (1 - LTV%) × LTV%)
    _ltv_loan_reg = seed_man * ltv_규제 / (100 - ltv_규제)
    _ltv_loan_nonreg = seed_man * ltv_비규제 / (100 - ltv_비규제)
    # 한도 cap: 규제지역은 매매가 무관 flat (2026-07 대책)
    _cap_reg = _reg_cap_man
    # 바인딩 요인 판별 — 세 한도 중 가장 작은 값이 실제 대출을 결정
    _limits_reg = [(_ltv_loan_reg, f"LTV {ltv_규제:.0f}%"),
                   (_cap_reg,       f"한도 cap {_cap_reg//10000}억")]
    if dsr_cap_man is not None:
        _limits_reg.append((dsr_cap_man, f"DSR 한도 {dsr_cap_man/10000:.1f}억"))
    _bind_reg = min(_limits_reg, key=lambda x: x[0])[1]

    _limits_nonreg = [(_ltv_loan_nonreg, f"LTV {ltv_비규제:.0f}%")]
    if dsr_cap_man is not None:
        _limits_nonreg.append((dsr_cap_man, f"DSR 한도 {dsr_cap_man/10000:.1f}억"))
    _bind_nonreg = min(_limits_nonreg, key=lambda x: x[0])[1]

    # 툴팁용 값 미리 계산
    _loan_reg_net    = _lcm(max_buy_reg_net,    "11680", ownership, first_time, dsr_cap_man)
    _loan_nonreg_net = _lcm(max_buy_nonreg_net, "99999", ownership, first_time, dsr_cap_man)
    _eq_reg_net    = (max_buy_reg_net    - _loan_reg_net)    / 10000
    _eq_nonreg_net = (max_buy_nonreg_net - _loan_nonreg_net) / 10000
    _cash_reg    = (_eq_reg_net    + costs_reg["total"]    / 10000)
    _cash_nonreg = (_eq_nonreg_net + costs_nonreg["total"] / 10000)
    _dsr_str = f"{dsr_cap_man/10000:.2f}억" if dsr_cap_man else "미적용"

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("매물 후보", f"{len(rec):,} 건")
    c2.metric("단지 수", f"{rec['apt_name'].nunique():,} 개")
    c3.metric("지역 수", f"{rec['region_code'].nunique():,} 개")
    c4.metric("🏙️ 규제지역 최대 매수가", f"{max_buy_reg_net/10000:.2f} 억",
              help=(
                  f"【부대비용 포함 실제 한도】\n"
                  f"매수가 {max_buy_reg_net/10000:.2f}억 = 자기자본 {_eq_reg_net:.2f}억 + 대출 {_loan_reg_net/10000:.2f}억\n"
                  f"총 필요 현금: 자기자본 {_eq_reg_net:.2f}억 + 부대비용 {costs_reg['total']/10000:.2f}억 = {_cash_reg:.2f}억 (시드 {seed_man/10000:.1f}억 이내)\n"
                  f"  · 취득세 {costs_reg['acquisition_tax']:,}만 / 중개 {costs_reg['broker_fee']:,}만 / 등기 {costs_reg['registration_etc']:,}만\n\n"
                  f"【대출 결정 요인: {_bind_reg}】\n"
                  f"① LTV {ltv_규제:.0f}%: 허용 대출 {_ltv_loan_reg/10000:.2f}억\n"
                  f"② 한도 cap: {_cap_reg//10000}억 (규제지역 매매가 무관 flat, 2026-07 대책)\n"
                  f"③ DSR: {_dsr_str}\n\n"
                  f"※ 부대비용 전 이론 한도 {max_buy_reg/10000:.2f}억 → 포함 시 {max_buy_reg_net/10000:.2f}억\n"
                  "※ LTV: 규제지역 무주택 40% / 서민실수요자 60% / 생애최초 고정 70%"
              ))
    c5.metric("🏞️ 비규제지역 최대 매수가", f"{max_buy_nonreg_net/10000:.2f} 억",
              help=(
                  f"【부대비용 포함 실제 한도】\n"
                  f"매수가 {max_buy_nonreg_net/10000:.2f}억 = 자기자본 {_eq_nonreg_net:.2f}억 + 대출 {_loan_nonreg_net/10000:.2f}억\n"
                  f"총 필요 현금: 자기자본 {_eq_nonreg_net:.2f}억 + 부대비용 {costs_nonreg['total']/10000:.2f}억 = {_cash_nonreg:.2f}억 (시드 {seed_man/10000:.1f}억 이내)\n"
                  f"  · 취득세 {costs_nonreg['acquisition_tax']:,}만 / 중개 {costs_nonreg['broker_fee']:,}만 / 등기 {costs_nonreg['registration_etc']:,}만\n\n"
                  f"【대출 결정 요인: {_bind_nonreg}】\n"
                  f"① LTV {ltv_비규제:.0f}%: 허용 대출 {_ltv_loan_nonreg/10000:.2f}억\n"
                  f"② DSR: {_dsr_str}\n\n"
                  f"※ 부대비용 전 이론 한도 {max_buy_nonreg/10000:.2f}억 → 포함 시 {max_buy_nonreg_net/10000:.2f}억\n"
                  "※ LTV: 무주택 70% (생애최초 80%) / 1주택 60% / 다주택 0%(신규 주담대 불가), 한도 cap 없음"
              ))
    if strategy == "🚀 투자수익":
        c6.metric("최고 예상수익률(자기자본)", f"{rec['expected_roi_%'].max():.2f} %")
    elif strategy == "임대수익":
        c6.metric("최고 연수익률", f"{rec['annual_yield_%'].max():.2f} %")
    elif strategy == "갭투자":
        c6.metric("최저 갭", f"{rec['gap'].min()/10000:.2f} 억")
    else:
        c6.metric("최저 자기자본", f"{rec['required_equity'].min()/10000:.2f} 억")

    # 지역 모멘텀(region_momentum_ranking) — 표로 따로 안 보여주고, 아래 단지 리스트
    # 정렬에 반영한다("지역 순위가 좋으면 위로 뜨게" 요청 — 2026-08-19).
    region_momentum_map: dict[str, float] = {}
    if strategy == "🚀 투자수익":
        mom = _cached_region_momentum(months)
        if not mom.empty:
            region_momentum_map = dict(zip(mom["region_code"], mom["momentum_score"]))

    if strategy == "🚀 투자수익":
        st.markdown("### 🏆 지역 추천순위")
        st.caption(
            f"✅ 시드 {seed_eok}억 기준 (부대비용 포함) · "
            f"규제지역 최대 **{max_buy_reg_net/10000:.2f}억** / "
            f"비규제지역 최대 **{max_buy_nonreg_net/10000:.2f}억** 이내 매물이 "
            "1건 이상 있는 지역만 표시."
        )
        st.caption(
            "avg_score = 위 매물별 종합점수(지역시장강도+호재 × 상급지가중치 + 대장단지 × 대장단지가중치)의 지역 평균."
        )

        sent_df = _cached_region_sentiment()
        from src.analysis.recommend import region_tier_score, region_tier_label
        from src.analysis.loan import max_purchase_man

        # 매수가능 매물 (시드 통과 + UI 한도 컷 반영)
        buyable_rec = rec[(rec["required_equity"] + rec["_acq_cost"] <= seed_man)].copy()
        # 지역별 매매가 한도 컷 (단지 추천표와 동일 규칙 적용 — 일관성)
        if not buyable_rec.empty:
            mb_map = {
                c: (max_purchase_man(seed_man, c, ownership, first_time, dsr_cap_man, kb_ratio)
                    if use_loan else seed_man)
                for c in buyable_rec["region_code"].unique()
            }
            buyable_rec["_max_buy"] = buyable_rec["region_code"].map(mb_map)
            buyable_rec = buyable_rec[buyable_rec["trade_median"] <= buyable_rec["_max_buy"]].drop(columns="_max_buy")
        # UI 필터 적용 (사이드바에서 받은 면적·연도)
        if area_range and "area_bucket" in buyable_rec.columns:
            a_lo, a_hi = area_range
            buyable_rec = buyable_rec[(buyable_rec["area_bucket"] >= a_lo) & (buyable_rec["area_bucket"] <= a_hi)]
        if year_range and "build_year" in buyable_rec.columns:
            y_lo, y_hi = year_range
            buyable_rec = buyable_rec[buyable_rec["build_year"].notna()
                                     & (buyable_rec["build_year"] >= y_lo)
                                     & (buyable_rec["build_year"] <= y_hi)]

        if "dong" in buyable_rec.columns:
            buyable_rec["dong"] = buyable_rec["dong"].fillna("").astype(str).str.strip()
            buyable_rec.loc[buyable_rec["dong"] == "", "dong"] = "(동 미상)"
        else:
            buyable_rec["dong"] = "(동 미상)"

        # (시군구, 동) 단위 집계 — 동탄/새솔동 같은 sub-지역이 분리됨
        dong_stats = buyable_rec.groupby(["region_code", "dong"]).agg(
            n_buyable=("apt_name", "count"),
            min_equity=("required_equity", "min"),
            min_trade=("trade_median", "min"),
            avg_score=("score", "mean"),
            avg_prestige=("prestige_score", "mean") if "prestige_score" in buyable_rec.columns else ("apt_name", "count"),
        ).reset_index()
        dong_stats = dong_stats[dong_stats["n_buyable"] > 0].copy()

        if dong_stats.empty:
            st.info("매수 가능한 매물이 있는 지역이 없습니다.")
        else:
            # 시군구 메타 (sentiment / catalyst / tier)
            sent_meta = sent_df[["region_code", "avg_sentiment", "manual_catalyst", "catalyst_text"]] if not sent_df.empty else pd.DataFrame(columns=["region_code"])
            dong_stats = dong_stats.merge(sent_meta, on="region_code", how="left")
            dong_stats["avg_sentiment"] = dong_stats.get("avg_sentiment", pd.Series(50.0)).fillna(50.0)
            dong_stats["manual_catalyst"] = dong_stats.get("manual_catalyst", pd.Series(0.0)).fillna(0.0)
            dong_stats["region"] = dong_stats["region_code"].map(REGION_MAP).fillna(dong_stats["region_code"])
            dong_stats["tier_label"] = (
                dong_stats["region_code"].apply(region_tier_label)
                .astype(str).str.extract(r"^(\d)", expand=False)
            )
            dong_stats["tier_score"] = dong_stats["region_code"].apply(region_tier_score)

            # (동 단위) 종합점수: 단지 추천 score 평균이 가장 직접적인 sub-지역 강도
            #   + 상급지 가중치 반영
            tw = max(0.0, min(1.0, tier_weight))
            rest = 1.0 - tw
            dong_stats["region_rank_score"] = (
                dong_stats["avg_score"].fillna(50) * (rest * 0.50)
                + dong_stats["tier_score"] * tw
                + dong_stats["avg_prestige"].fillna(50) * (rest * 0.30)
                + dong_stats["avg_sentiment"] * (rest * 0.10)
                + dong_stats["manual_catalyst"] * (rest * 0.10)
            ).round(1)

            dong_stats = dong_stats.sort_values("region_rank_score", ascending=False).reset_index(drop=True)
            dong_top = dong_stats.head(40).copy()
            dong_top["rank"] = range(1, len(dong_top) + 1)
            dong_top["min_equity_억"] = (dong_top["min_equity"] / 10000).round(2)
            dong_top["min_trade_억"] = (dong_top["min_trade"] / 10000).round(2)

            st.caption("👇 각 (지역·동)을 펼치면 그 동 안의 매수가능 매물이 전부 나옵니다. "
                       "최대한 작은 단위(동)로 쪼개 표시.")

            for _, row in dong_top.iterrows():
                code = row["region_code"]
                dong = row["dong"]
                name = row["region"]
                rk = int(row["rank"])
                score = row["region_rank_score"]
                n_buy = int(row["n_buyable"])
                min_eq_eok = row["min_equity_억"]
                min_tr_eok = row["min_trade_억"]
                tier = row["tier_label"] or "-"

                full_name = f"{name} · {dong}" if dong != "(동 미상)" else f"{name} · (동 미상)"
                header = (
                    f"#{rk:>2}  {full_name}   "
                    f"급지 {tier}  ·  점수 {score:.1f}  ·  "
                    f"매물 {n_buy}건  ·  최저 자기자본 {min_eq_eok:.2f}억 / 매매가 {min_tr_eok:.2f}억"
                )
                with st.expander(header, expanded=(rk == 1)):
                    max_buy_sel = (
                        max_purchase_man(seed_man, code, ownership, first_time, dsr_cap_man)
                        if use_loan else seed_man
                    )
                    rgn_rec = buyable_rec[
                        (buyable_rec["region_code"] == code)
                        & (buyable_rec["dong"] == dong)
                    ].copy()
                    if "required_equity" in rgn_rec.columns:
                        rgn_rec = rgn_rec[
                            (rgn_rec["required_equity"] > 0)
                            & (rgn_rec["trade_median"] <= max_buy_sel)
                        ]
                    rgn_rec = rgn_rec.sort_values("score", ascending=False).reset_index(drop=True)
                    rgn_rec["apt_rank"] = range(1, len(rgn_rec) + 1)

                    if rgn_rec.empty:
                        st.info("매수 가능 매물이 없습니다.")
                        continue

                    # 네이버 검색은 '지역 동 단지명' 으로 좀 더 정확히
                    naver_q = f"{name} {dong}" if dong != "(동 미상)" else name
                    rgn_rec["naver_url"] = [
                        naver_land_url(naver_q, an) for an in rgn_rec["apt_name"]
                    ]

                    drill_cols = ["naver_url", "apt_rank", "apt_name", "trade_median", "required_equity",
                                   "tier_label", "area_bucket", "build_year",
                                   "catalyst_score", "sentiment_score",
                                   "price_growth_%", "expected_roi_%", "score"]
                    drill_cols = [c for c in drill_cols if c in rgn_rec.columns]
                    rgn_show = rgn_rec[drill_cols].copy()
                    rgn_show = rgn_show.rename(columns={"apt_rank": "rank"})
                    if "tier_label" in rgn_show.columns:
                        rgn_show["tier_label"] = (
                            rgn_show["tier_label"].astype(str).str.extract(r"^(\d)", expand=False)
                        )
                    render_table(rgn_show)
                    cat_text = row.get("catalyst_text")
                    if isinstance(cat_text, str) and cat_text:
                        st.caption(f"📌 등록호재: {cat_text}")

    elif strategy == "갭투자":
        st.markdown("### 🏆 지역별 갭투자 요약")
        st.caption("역전세 리스크 낮고 상급지인 지역 우선. 최고점수 내림차순.")

        gap_rec = rec[(rec["gap"] > 0) & (rec["gap"] + rec["_acq_cost"] <= seed_man)].copy()
        if not gap_rec.empty:
            # 역전세 리스크 분포
            risk_dist = gap_rec["jeonse_risk"].value_counts().reset_index()
            risk_dist.columns = ["리스크레벨", "건수"]

            rc1, rc2 = st.columns([1, 3])
            with rc1:
                st.markdown("**역전세 리스크 분포**")
                render_df(risk_dist)

            # 지역별 요약 집계
            rg = gap_rec.groupby("region_code").agg(
                n_opp=("apt_name", "count"),
                n_apts=("apt_name", "nunique"),
                min_gap=("gap", "min"),
                avg_ratio=("jeonse_ratio", "mean"),
                avg_leverage=("leverage_mult", "mean"),
                avg_accel=("jeonse_accel_%p", "mean"),
                max_score=("score", "max"),
            ).reset_index()
            rg["region"] = rg["region_code"].map(REGION_MAP).fillna(rg["region_code"])
            rg["safe_n"] = gap_rec.groupby("region_code")["jeonse_risk"].apply(
                lambda x: ((x == "✅ 적정") | (x == "🟢 갭여유")).sum()
            ).values
            rg["risk_n"] = gap_rec.groupby("region_code")["jeonse_risk"].apply(
                lambda x: (x == "⚠️ 역전세위험").sum()
            ).values
            rg = rg.sort_values("max_score", ascending=False).reset_index(drop=True)
            rg.insert(0, "rank", range(1, len(rg) + 1))
            rg["최저갭(억)"] = (rg["min_gap"] / 10000).round(2)
            rg["평균전세가율(%)"] = rg["avg_ratio"].round(1)
            rg["전세가율추세(%p)"] = rg["avg_accel"].round(2)
            rg["평균레버리지(배)"] = rg["avg_leverage"].round(1)
            rg["최고점수"] = rg["max_score"].round(1)

            show_cols = ["rank", "region", "n_opp", "최저갭(억)",
                         "평균전세가율(%)", "전세가율추세(%p)",
                         "safe_n", "risk_n",
                         "평균레버리지(배)", "최고점수"]
            rg_show = rg[show_cols].rename(columns={
                "n_opp": "기회수",
                "safe_n": "안전·적정",
                "risk_n": "역전세위험",
            })
            with rc2:
                render_df(rg_show, height=380)

    st.markdown(f"### 🎯 단지·평형 추천 TOP {top_n}")
    # 🛡️ 시드 안전망 + 매매가 한도 안전망 (지역별 max_purchase 계산해서 매매가 자체도 컷)
    from src.analysis.loan import max_purchase_man
    # 지역코드별 max_purchase 캐싱 (rec에 등장한 지역만)
    unique_codes = rec_disp["region_code"].unique() if "region_code" in rec_disp.columns else []
    max_buy_by_region = {
        c: max_purchase_man(seed_man, c, ownership, first_time, dsr_cap_man, kb_ratio) if use_loan else seed_man
        for c in unique_codes
    }
    if "required_equity" in rec_disp.columns:
        before = len(rec_disp)
        # (1) 자기자본+부대비용 ≤ 시드, (2) 매매가 ≤ 지역별 매수 한도
        rec_disp["_max_buy"] = rec_disp["region_code"].map(max_buy_by_region)
        rec_disp = rec_disp[
            (rec_disp["required_equity"] > 0)
            & (rec_disp["required_equity"] + rec_disp["_acq_cost"] <= seed_man)
            & (rec_disp["trade_median"] <= rec_disp["_max_buy"])
        ].drop(columns=["_max_buy", "_acq_cost"]).reset_index(drop=True)
        dropped = before - len(rec_disp)
        if dropped > 0:
            st.caption(f"⚠️ 시드+대출한도+부대비용({seed_eok}억 기준) 초과 매물 {dropped}건 제외됨")
    if rec_disp.empty:
        st.warning(
            f"시드 {seed_eok}억 + 대출(LTV·DSR 반영)로 매수 가능한 매물이 없습니다. "
            f"위 '규제지역 최대 매수가' / '비규제지역 최대 매수가' 카드를 확인하세요."
        )
        return
    st.caption(
        f"✅ 자기자본 **{seed_eok}억** + 규제별 LTV·한도cap·DSR 반영해 매매가 자체가 매수 한도 이내인 매물만 표시. "
        f"필요자기자본 = 매매가 − 실대출, 매수 시 본인 부담 금액."
    )
    # 컬럼 순서: 네이버링크 → 추천순위 → 단지·가격 → 급지·면적·연도 → 분석지표
    if strategy == "🚀 투자수익":
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "tier_label",
                      "area_bucket", "build_year",
                      "catalyst_score", "sentiment_score",
                      "price_growth_%", "expected_roi_%",
                      "catalysts", "score"]
    elif strategy == "갭투자":
        cols_order = ["naver_url", "rank", "region", "apt_name",
                      "trade_median", "rent_median", "gap", "required_equity",
                      "jeonse_risk",
                      "jeonse_ratio", "jeonse_accel_%p",
                      "leverage_mult",
                      "tier_label",
                      "area_bucket", "build_year",
                      "trade_count", "rent_count", "score"]
    elif strategy == "임대수익":
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "area_bucket", "build_year",
                      "ltv_%", "loan_capacity",
                      "deposit_median", "monthly_median",
                      "annual_yield_%", "trade_count", "rent_count", "score"]
    else:  # 자가매입
        cols_order = ["naver_url", "rank", "region", "apt_name", "trade_median", "required_equity",
                      "area_bucket", "build_year",
                      "ltv_%", "loan_capacity",
                      "ppp_median", "region_median_ppp", "value_ratio",
                      "trade_count", "score"]

    # 지역모멘텀 우선 정렬 — 모멘텀 좋은 지역의 단지가 리스트 위쪽에 뜨도록
    # (같은 지역 안에서는 기존 score 순서 유지)
    if region_momentum_map and "region_code" in rec_disp.columns:
        rec_disp = rec_disp.copy()
        rec_disp["_region_momentum"] = rec_disp["region_code"].map(region_momentum_map).fillna(0.0)
        rec_disp = rec_disp.sort_values(
            ["_region_momentum", "score"], ascending=[False, False]
        ).drop(columns=["_region_momentum"]).reset_index(drop=True)

    # 추천 순위 부여: rec_disp는 이미 정렬됨 → 1,2,3...
    rec_disp_ranked = rec_disp.copy()
    rec_disp_ranked["rank"] = range(1, len(rec_disp_ranked) + 1)
    # 네이버 부동산 검색 링크 (지역명 + 단지명)
    rec_disp_ranked["naver_url"] = [
        naver_land_url(r.get("region"), r.get("apt_name"))
        for r in rec_disp_ranked.to_dict("records")
    ]
    rec_top = rec_disp_ranked[cols_order].head(top_n).copy()
    # tier_label "2_상급지" → "2" (숫자 한 자리만)
    if "tier_label" in rec_top.columns:
        rec_top["tier_label"] = rec_top["tier_label"].astype(str).str.extract(r"^(\d)", expand=False)
    render_table(rec_top, height=600)

    csv = rec_disp_ranked[cols_order].to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 추천 결과 CSV 다운로드", csv,
                        file_name=f"추천_{strategy}_{seed_eok}억_{date.today():%Y%m%d}.csv",
                        mime="text/csv")

    # ─── 🧪 단지 선택 후 스트레스 테스트 ───
    if "trade_median" in rec.columns and "loan_capacity" in rec.columns:
        st.markdown("---")
        st.markdown("### 🎯 관심 단지 깊이 분석")
        st.caption("아래에서 한 단지를 선택하면 5년 시나리오 + 스트레스 테스트가 표시됩니다.")
        rec_top = rec_disp.head(top_n).reset_index(drop=True)
        labels = [
            f"{r['region']} · {r['apt_name']} · {r['area_bucket']:.0f}㎡  "
            f"({r['trade_median']/10000:.2f}억)"
            for _, r in rec_top.iterrows()
        ]
        if labels:
            picked_idx = st.selectbox(
                "단지 선택", range(len(labels)),
                format_func=lambda i: labels[i],
                key="stress_picker",
            )
            selected = rec_top.iloc[picked_idx].to_dict()
            _render_stress_test(inputs, selected)
