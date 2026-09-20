"""탭 5 — 🏠 추천 매물 (분석된 자기자본 기준 매수 가능 단지)."""
from __future__ import annotations
import streamlit as st

from config.settings import (
    DEFAULT_CATALYST_WEIGHT, DEFAULT_TIER_WEIGHT, DEFAULT_PRESTIGE_WEIGHT,
)
from src.ui.shared import (
    REGION_MAP, render_table, naver_land_url,
    _cached_gap, _cached_yield, _cached_outright, _cached_investment,
)
from .context import PortfolioContext, _eok


def render(ctx: PortfolioContext):
    result = ctx.result
    t_kb, t_max = ctx.t_kb, ctx.t_max

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
