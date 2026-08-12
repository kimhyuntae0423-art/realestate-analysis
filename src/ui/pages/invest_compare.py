"""🚀 투자 추천 탭 — 3전략(투자수익·갭투자·임대수익) 동시 비교 뷰.

src/ui/pages/invest.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
import pandas as pd
import streamlit as st
import plotly.express as px

from src.analysis.fair_value import enrich_with_fair_value
from src.ui.shared import (
    REGION_MAP, render_table, render_df,
    _simplify_apt_name, naver_land_url,
    _cached_gap, _cached_yield, _cached_investment, _cached_all_trades,
)


def _render_compare_view(
    seed_man: int, months: int, min_deals: int,
    ownership: str, first_time: bool, use_loan: bool,
    catalyst_weight: float, tier_weight: float, prestige_weight: float,
    dsr_cap_man, top_n: int, area_range, year_range,
    max_buy_reg_net: int = 0, max_buy_nonreg_net: int = 0,
    kb_ratio: float = 1.0,
):
    """3전략 동시 비교 — 겹치는 단지가 높은 확신도."""
    st.markdown("### 🔀 3전략 동시 비교")
    st.caption(
        "같은 조건으로 투자수익·갭투자·임대수익을 동시 실행합니다. "
        "여러 전략 상위권에 겹치는 단지일수록 확신도가 높습니다."
    )
    half_months = max(months // 2, 3)

    if max_buy_reg_net > 0 or max_buy_nonreg_net > 0:
        _ca, _cb = st.columns(2)
        _ca.metric("🏙️ 규제지역 최대 매수가 (부대비용 포함)", f"{max_buy_reg_net/10000:.2f} 억")
        _cb.metric("🏞️ 비규제지역 최대 매수가 (부대비용 포함)", f"{max_buy_nonreg_net/10000:.2f} 억")

    # kb_ratio 적용 부대비용 필터: 캐시 결과는 kb_ratio=1.0 기준이므로 여기서 재필터
    def _filter_affordable(df: pd.DataFrame, is_gap: bool = False) -> pd.DataFrame:
        """required_equity + 부대비용 ≤ 시드 조건으로 매수 불가 매물 제거.

        is_gap=True면 required_equity = gap 그대로 사용 (갭투자는 주담대 아닌 전세보증금 기준).
        is_gap=False면 kb_ratio < 1.0일 때 대출 재계산.
        """
        if df.empty:
            return df
        df = df.copy()
        from src.analysis.costs import total_acquisition_cost_man as _tacm2
        df["_acq_cost2"] = df["trade_median"].apply(lambda p: _tacm2(p, ownership, first_time)["total"])
        if not is_gap and kb_ratio < 1.0 and "trade_median" in df.columns and "region_code" in df.columns:
            from src.analysis.loan import annotate_loan_columns as _alc
            df = _alc(df, seed_man, ownership, first_time, "trade_median", dsr_cap_man, kb_ratio)
        if "required_equity" in df.columns:
            df = df[(df["required_equity"] > 0) & (df["required_equity"] + df["_acq_cost2"] <= seed_man)]
        return df.drop(columns=["_acq_cost2"], errors="ignore")

    _prog = st.progress(0, text="🚀 투자수익 계산 중…")
    try:
        rec_inv = _filter_affordable(_cached_investment(seed_man, months, min_deals, ownership, first_time,
                                      use_loan, catalyst_weight, tier_weight, prestige_weight, dsr_cap_man))
        _prog.progress(34, text="🏠 갭투자 계산 중…")
        rec_gap = _filter_affordable(_cached_gap(seed_man, months, min_deals, ownership, first_time, dsr_cap_man), is_gap=True)
        _prog.progress(67, text="💰 임대수익 계산 중…")
        rec_yld = _filter_affordable(_cached_yield(seed_man, months, min_deals, ownership, first_time, use_loan, dsr_cap_man))
        _prog.progress(100, text="✅ 완료")
        _prog.empty()
    except MemoryError:
        _prog.empty()
        st.error("메모리 부족으로 중단됐습니다. 최소 거래수를 높이거나 분석 기간을 줄여보세요.")
        return
    except Exception as e:
        _prog.empty()
        st.error(f"계산 오류: {e}")
        return

    def _prep(df):
        if df.empty:
            return df
        df = df.copy()
        if area_range and "area_bucket" in df.columns:
            df = df[(df["area_bucket"] >= area_range[0]) & (df["area_bucket"] <= area_range[1])]
        if year_range and "build_year" in df.columns:
            df = df[df["build_year"].notna()
                    & (df["build_year"] >= year_range[0])
                    & (df["build_year"] <= year_range[1])]
        df["지역"] = df["region_code"].map(REGION_MAP).fillna(df["region_code"])
        return df.head(top_n).reset_index(drop=True)

    inv = _prep(rec_inv)
    gap = _prep(rec_gap)
    yld = _prep(rec_yld)

    def _keys(df):
        if df.empty or not {"apt_name", "region_code", "area_bucket"}.issubset(df.columns):
            return set()
        return set(zip(df["apt_name"], df["region_code"], df["area_bucket"]))

    k_inv, k_gap, k_yld = _keys(inv), _keys(gap), _keys(yld)
    all3 = k_inv & k_gap & k_yld
    any2 = ((k_inv & k_gap) | (k_inv & k_yld) | (k_gap & k_yld)) - all3

    def _badge(r):
        k = (r["apt_name"], r["region_code"], r["area_bucket"])
        if k in all3: return "🏆 3전략"
        if k in any2: return "🔶 2전략"
        return ""

    for df in [inv, gap, yld]:
        if not df.empty:
            df["일치"] = df.apply(_badge, axis=1)

    # ── 교집합 섹션 ──
    _key_cols = ["apt_name", "region_code", "area_bucket"]
    ann = 12 / half_months

    if all3:
        st.success(f"🏆 **3전략 모두 상위권 — {len(all3)}개 단지** | 시세차익 + 갭 진입 + 월세수익 동시 유망")

        # 베이스: 투자수익 DataFrame (price_growth_% 포함)
        _inv_cols = _key_cols + ["지역", "trade_median", "score"]
        for _c in ["expected_roi_%", "required_equity", "price_growth_%"]:
            if _c in inv.columns: _inv_cols.append(_c)
        over = inv[inv["일치"] == "🏆 3전략"][_inv_cols].copy()
        over.insert(0, "순위", range(1, len(over) + 1))
        over["매매가(억)"] = (over["trade_median"] / 10000).round(2)
        over["naver_url"] = [naver_land_url(r.get("지역"), r.get("apt_name")) for r in over.to_dict("records")]

        # 갭투자 데이터 병합 (gap + jeonse_ratio)
        if not gap.empty and "gap" in gap.columns:
            _g_cols = _key_cols + ["gap"]
            if "jeonse_ratio" in gap.columns: _g_cols.append("jeonse_ratio")
            _g = gap[gap["일치"] == "🏆 3전략"][_g_cols].copy()
            over = over.merge(_g, on=_key_cols, how="left")
            over["🏠 갭(억)"] = (over["gap"] / 10000).round(2)

        # 임대수익 데이터 병합 (annual_yield_% + monthly_median)
        if not yld.empty and "annual_yield_%" in yld.columns:
            _y_cols = _key_cols + ["annual_yield_%"]
            if "monthly_median" in yld.columns: _y_cols.append("monthly_median")
            _y = yld[yld["일치"] == "🏆 3전략"][_y_cols].copy()
            over = over.merge(_y, on=_key_cols, how="left")

        # 🚀 투자수익: 예상수익금 = 수익률 × 투입자본
        if "expected_roi_%" in over.columns and "required_equity" in over.columns:
            over["🚀 예상수익금(억)"] = (
                over["expected_roi_%"] * over["required_equity"] / 100 / 10000
            ).round(2)

        # 💰 임대수익: 연수익금 = 월세 × 12
        if "monthly_median" in over.columns:
            over["💰 연수익금(억)"] = (over["monthly_median"] * 12 / 10000).round(2)

        # 🏠 갭투자: 수익금 = 매매가 상승분 / 수익률 = 상승분 ÷ 갭
        if "price_growth_%" in over.columns and "gap" in over.columns:
            gain = over["trade_median"] * over["price_growth_%"] / 100
            over["🏠 갭투자수익금(억)"] = (gain / 10000).round(2)
            over["🏠 갭투자수익률(%)"] = (gain / over["gap"] * 100).round(2)

        # ── HTML 2단 헤더 테이블 (rowspan/colspan, 전부 연환산) ──

        has_inv_g = "🚀 예상수익금(억)" in over.columns
        has_inv_r = "expected_roi_%" in over.columns
        has_yld_g = "💰 연수익금(억)" in over.columns
        has_yld_r = "annual_yield_%" in over.columns
        has_gap_g = "🏠 갭투자수익금(억)" in over.columns
        has_gap_r = "🏠 갭투자수익률(%)" in over.columns
        has_gap_v = "🏠 갭(억)" in over.columns

        def _n(v):
            try:
                return "—" if pd.isna(v) else f"{float(v):.2f}"
            except Exception:
                return "—"

        _tbl_css = """
<style>
.cmp-tbl{width:100%;border-collapse:collapse;font-size:13px}
.cmp-tbl th{padding:6px 10px;text-align:center;white-space:nowrap;border:1px solid #e2e8f0}
.cmp-tbl th.base{background:#f1f5f9;color:#374151}
.cmp-tbl th.inv{background:#dbeafe;color:#1e40af}
.cmp-tbl th.yld{background:#dcfce7;color:#166534}
.cmp-tbl th.gap{background:#fef3c7;color:#92400e}
.cmp-tbl td{padding:5px 10px;border-bottom:1px solid #e2e8f0;text-align:center;white-space:nowrap}
.cmp-tbl tr:nth-child(even) td{background:#f9fafb}
.cmp-tbl tr:hover td{background:#f0f9ff}
</style>"""

        _thead = """
<tr>
  <th rowspan="2" class="base">순위</th>
  <th rowspan="2" class="base">🔗</th>
  <th rowspan="2" class="base">지역</th>
  <th rowspan="2" class="base">단지</th>
  <th rowspan="2" class="base">매매가(억)</th>
  <th rowspan="2" class="base">면적(㎡)</th>
  <th colspan="2" class="inv">🚀 투자수익</th>
  <th colspan="3" class="gap">🏠 갭투자</th>
  <th colspan="2" class="yld">💰 임대수익</th>
  <th rowspan="2" class="base">점수</th>
</tr>
<tr>
  <th class="inv">연수익금(억)</th><th class="inv">연수익률(%)</th>
  <th class="gap">연수익금(억)</th><th class="gap">연수익률(%)</th><th class="gap">갭(억)</th>
  <th class="yld">연수익금(억)</th><th class="yld">연수익률(%)</th>
</tr>"""

        _rows = []
        for _, r in over.iterrows():
            ig = _n(r["🚀 예상수익금(억)"] * ann) if has_inv_g else "—"
            ir = _n(r["expected_roi_%"] * ann)    if has_inv_r else "—"
            gg = _n(r["🏠 갭투자수익금(억)"] * ann) if has_gap_g else "—"
            gr = _n(r["🏠 갭투자수익률(%)"] * ann) if has_gap_r else "—"
            gv = _n(r["🏠 갭(억)"])               if has_gap_v else "—"
            yg = _n(r["💰 연수익금(억)"])          if has_yld_g else "—"
            yr = _n(r["annual_yield_%"])           if has_yld_r else "—"
            _url = r.get("naver_url") or ""
            _link = f"<a href='{_url}' target='_blank' style='color:#2563eb;text-decoration:none'>🔗</a>" if _url else "—"
            _rows.append(
                f"<tr><td>{int(r['순위'])}</td><td>{_link}</td><td>{r['지역']}</td><td>{r['apt_name']}</td>"
                f"<td>{r['매매가(억)']:.2f}</td><td>{r['area_bucket']:.0f}</td>"
                f"<td>{ig}</td><td>{ir}</td>"
                f"<td>{gg}</td><td>{gr}</td><td>{gv}</td>"
                f"<td>{yg}</td><td>{yr}</td><td>{r['score']:.1f}</td></tr>"
            )

        st.markdown(
            _tbl_css + f"<div style='overflow-x:auto'>"
            f"<table class='cmp-tbl'><thead>{_thead}</thead>"
            f"<tbody>{''.join(_rows)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"📅 전부 연환산 기준 (× 12 ÷ {half_months}개월). "
            f"🚀·🏠 수치는 최근 {half_months}개월 실거래 추세를 연환산한 추정값 — 과거 추세 지속 보장 아님. "
            f"💰 임대수익은 실제 연간 월세 수입."
        )
    elif any2:
        st.info(f"🔶 **2전략 이상 상위권 — {len(any2)}개 단지**")
    else:
        st.caption("현재 조건에서 두 전략 이상 겹치는 단지 없음 — 단지 수(top_n) 늘리거나 최소 거래수 낮춰보세요.")

    if any2:
        with st.expander(f"🔶 2전략 이상 겹치는 단지 ({len(any2)}개)", expanded=bool(not all3)):
            rows = []
            for df, label in [(inv, "🚀투자수익"), (gap, "🏠갭투자"), (yld, "💰임대수익")]:
                if df.empty: continue
                sub = df[df["일치"].isin(["🏆 3전략", "🔶 2전략"])].copy()
                sub["전략"] = label
                rows.append(sub[["지역", "apt_name", "area_bucket", "trade_median", "전략"]])
            if rows:
                m = pd.concat(rows)
                m["매매가(억)"] = (m["trade_median"] / 10000).round(2)
                piv = m.groupby(["지역", "apt_name", "area_bucket", "매매가(억)"])["전략"].apply(
                    lambda x: " · ".join(sorted(set(x)))
                ).reset_index()
                render_df(piv.rename(columns={"apt_name": "단지", "area_bucket": "면적(㎡)"}))

    st.markdown("---")

    # ── 전략별 탭 ──
    tab_inv, tab_gap, tab_yld, tab_under = st.tabs(
        ["🚀 투자수익", "🏠 갭투자", "💰 임대수익", "💎 저평가 매물"]
    )

    # 추천 단지 매물 확인 링크 (3탭 공유)
    def _render_catch_board(show_df: pd.DataFrame, tab_key: str):
        """💎 저평가 캐치 알림판.

        전략 추천 단지의 최근 거래가 분포 + 적정가를 분석해
        '이 가격 이하 매물이 나오면 잡아라'는 캐치 기준가를 제시한다.
        """
        st.markdown("#### 💎 저평가 캐치 알림판")
        st.caption(
            "추천 단지들의 **최근 실거래 분포**와 **적정가**를 바탕으로 매수 기준가를 계산합니다. "
            "**캐치기준가 이하 매물이 나오면 저평가 매물**입니다."
        )

        # ── 최근 거래 통계 계산 ──────────────────────────────────────────
        _raw = _cached_all_trades(months)
        _apt_set = set(show_df["apt_name"].unique())
        _df = _raw[_raw["apt_name"].isin(_apt_set)].copy()

        if _df.empty:
            st.info("해당 단지의 최근 거래 데이터가 없습니다.")
            return

        _area_tol = 5.0
        _df["area_bucket"] = (_df["area_m2"] / _area_tol).round() * _area_tol
        _df["deal_date"] = pd.to_datetime(_df["deal_date"])
        _cutoff = _df["deal_date"].max() - pd.DateOffset(months=3)
        _recent = _df[_df["deal_date"] >= _cutoff]

        if _recent.empty:
            _recent = _df  # fallback to full period

        _stats = _recent.groupby(["apt_name", "area_bucket"]).agg(
            최저가=("deal_amount", "min"),
            하위25=("deal_amount", lambda x: int(x.quantile(0.25))),
            중위가=("deal_amount", "median"),
            최고가=("deal_amount", "max"),
            거래건=("deal_amount", "count"),
        ).reset_index()

        # ── 전략 결과와 조인 ─────────────────────────────────────────────
        _key = ["apt_name", "area_bucket"]
        _base = show_df[[c for c in show_df.columns
                          if c in (_key + ["rank", "지역", "naver_url",
                                            "fair_value", "fv_premium_%", "verdict",
                                            "score", "gap", "jeonse_ratio",
                                            "annual_yield_%"])]].copy()
        merged = _base.merge(_stats, on=_key, how="inner")
        if merged.empty:
            st.info("면적 매칭 데이터가 없습니다.")
            return

        # ── 캐치 기준가 계산 ─────────────────────────────────────────────
        def _catch_price(row) -> float:
            fv = row.get("fair_value")
            p25 = row.get("하위25", 0)
            mid = row.get("중위가", 0)
            # 적정가가 중위가보다 낮으면 적정가를 기준으로 (더 보수적)
            if fv and fv > 0 and fv < mid:
                return round(float(fv))
            # 하위 25%ile: 실제로 이 가격에 거래된 사람들이 있음
            if p25 and p25 > 0 and p25 < mid:
                return int(p25)
            # 기본: 중위가의 95%
            return round(mid * 0.95) if mid else 0

        merged["캐치기준가"] = merged.apply(_catch_price, axis=1)
        merged["시세대비할인(%)"] = (
            (merged["캐치기준가"] - merged["중위가"]) / merged["중위가"] * 100
        ).round(1)

        # 저평가 판정 (캐치기준가 ≤ 중위가 * 0.97 이면 의미있는 할인)
        merged["상태"] = merged["시세대비할인(%)"].apply(
            lambda x: "🔥 강추 매수가" if x <= -10 else
                      ("💎 저평가 기준" if x <= -5 else
                       ("✅ 적정 기준" if x <= -2 else "—"))
        )

        # ── 억 단위 변환 ─────────────────────────────────────────────────
        for col in ["최저가", "하위25", "중위가", "최고가", "캐치기준가"]:
            if col in merged.columns:
                merged[col + "_억"] = (merged[col] / 10000).round(2)
        if "fair_value" in merged.columns:
            merged["적정가_억"] = (merged["fair_value"] / 10000).round(2)

        # ── 네이버 링크 ──────────────────────────────────────────────────
        if "naver_url" not in merged.columns:
            merged["naver_url"] = [
                naver_land_url(r.get("지역"), r.get("apt_name"))
                for r in merged.to_dict("records")
            ]

        # ── 표시 ─────────────────────────────────────────────────────────
        # 정렬: 캐치기준가 할인율 큰 순 (저평가 많은 것 우선)
        merged = merged.sort_values("시세대비할인(%)", ascending=True).reset_index(drop=True)

        disp_cols = [
            "naver_url", "상태", "지역", "apt_name", "area_bucket",
            "최저가_억", "하위25_억", "중위가_억", "최고가_억",
            "적정가_억", "캐치기준가_억", "시세대비할인(%)",
            "거래건",
        ]
        if "fv_premium_%" in merged.columns:
            disp_cols.append("fv_premium_%")
        if "verdict" in merged.columns:
            disp_cols.append("verdict")

        render_table(merged[[c for c in disp_cols if c in merged.columns]], height=540)
        st.caption(
            "📌 **캐치기준가**: 적정가(전세가율·수익률 역산)가 시세보다 낮으면 적정가, "
            "없으면 최근 하위25% 거래가 기준. "
            "**이 가격 이하 매물이 네이버/직방에 올라오면 저평가 매물입니다.**\n\n"
            "🔥 강추 매수가: 시세 대비 10%↑ 할인 | 💎 저평가 기준: 5~10% 할인 | "
            "✅ 적정 기준: 2~5% 할인"
        )

    with tab_inv:
        if inv.empty:
            st.warning("해당 조건의 투자수익 매물 없음")
        else:
            show = inv.copy()
            show["rank"] = range(1, len(show) + 1)
            show["naver_url"] = [naver_land_url(r.get("지역"), r.get("apt_name")) for r in show.to_dict("records")]
            if "expected_roi_%" in show.columns and "required_equity" in show.columns:
                show["연수익률(%)"] = (show["expected_roi_%"] * ann).round(2)
                show["연수익금(억)"] = (
                    show["expected_roi_%"] * ann * show["required_equity"] / 100 / 10000
                ).round(2)
            _key = ["apt_name", "region_code", "area_bucket"]
            if not gap.empty and "rent_median" in gap.columns:
                _rent = gap[_key + ["rent_median"]].drop_duplicates(_key)
                show = show.merge(_rent, on=_key, how="left")
                show = enrich_with_fair_value(show, jeonse_col="rent_median")
            cols = [
                "naver_url", "rank", "지역", "apt_name",
                "trade_median", "required_equity",
                "tier_label", "area_bucket", "build_year",
                "catalyst_score", "sentiment_score",
                "price_growth_%", "expected_roi_%",
                "연수익률(%)", "연수익금(억)",
                "score",
                "fair_value", "fv_premium_%", "verdict",
            ]
            st.markdown("#### 📊 단지별 전략 분석 요약")
            render_table(show[[c for c in cols if c in show.columns]], height=420)
            st.caption(f"📅 연환산 기준 (× 12 ÷ {half_months}개월 실거래 추세) | 💎 적정가: 전세가율 65% 역산")
            st.markdown("---")
            _render_catch_board(show, "inv")

    with tab_gap:
        if gap.empty:
            st.warning("해당 조건의 갭투자 매물 없음")
        else:
            show = gap.copy()
            show["rank"] = range(1, len(show) + 1)
            show["naver_url"] = [naver_land_url(r.get("지역"), r.get("apt_name")) for r in show.to_dict("records")]
            _key = ["apt_name", "region_code", "area_bucket"]
            if not inv.empty and "price_growth_%" in inv.columns:
                _pg = inv[_key + ["price_growth_%"]].drop_duplicates(_key)
                show = show.merge(_pg, on=_key, how="left")
                show["price_growth_%"] = show["price_growth_%"].fillna(0)
                gain = show["trade_median"] * show["price_growth_%"] / 100
                show["연수익금(억)"] = (gain / 10000 * ann).round(2)
                show["연수익률(%)"] = (gain / show["gap"] * 100 * ann).round(2)
            show = enrich_with_fair_value(show, jeonse_col="rent_median")
            cols = [
                "naver_url", "rank", "지역", "apt_name",
                "trade_median", "rent_median", "gap",
                "jeonse_risk", "jeonse_ratio", "jeonse_accel_%p",
                "leverage_mult",
                "tier_label", "area_bucket", "build_year",
                "trade_count", "rent_count",
                "연수익률(%)", "연수익금(억)",
                "score",
                "fair_value", "fv_premium_%", "verdict",
            ]
            st.markdown("#### 📊 단지별 전략 분석 요약")
            render_table(show[[c for c in cols if c in show.columns]], height=420)
            st.caption(f"📅 연수익률·연수익금: 연환산 기준 (× 12 ÷ {half_months}개월). 갭투자 수익률 = 시세차익 ÷ 갭(자기자본). | 💎 적정가: 전세가율 65% 역산")
            st.markdown("---")
            _render_catch_board(show, "gap")

    with tab_yld:
        if yld.empty:
            st.warning("해당 조건의 임대수익 매물 없음")
        else:
            show = yld.copy()
            show["rank"] = range(1, len(show) + 1)
            show["naver_url"] = [naver_land_url(r.get("지역"), r.get("apt_name")) for r in show.to_dict("records")]
            show = enrich_with_fair_value(show, jeonse_col=None, monthly_col="monthly_median")
            cols = [
                "naver_url", "rank", "지역", "apt_name",
                "trade_median", "required_equity",
                "area_bucket", "build_year",
                "deposit_median", "monthly_median",
                "annual_yield_%",
                "trade_count", "rent_count",
                "score",
                "fair_value", "fv_premium_%", "verdict",
            ]
            st.markdown("#### 📊 단지별 전략 분석 요약")
            render_table(show[[c for c in cols if c in show.columns]], height=420)
            st.caption("💎 적정가: 수익률 3.5% 역산 기준")
            st.markdown("---")
            _render_catch_board(show, "yld")

    with tab_under:
        st.subheader("💎 저평가 매물 — 매수 가능 범위 내 저평가 단지")
        st.caption(
            "갭투자(전세가율 65% 역산)·임대수익(수익률 3.5% 역산) 두 방법으로 "
            "적정가를 계산하고, 현재가가 **적정가보다 낮은 매물**만 표시합니다. "
            "같은 단지가 두 방법에서 모두 포착되면 더 낮은 값을 사용합니다."
        )

        with st.container(border=True):
            _fr1, _fr2, _fr3 = st.columns(3)
            under_thresh = _fr1.slider(
                "적정가 대비 범위 (%)", min_value=-40, max_value=30, value=-5, step=1,
                key="under_thresh",
                help="0% 이하: 저평가(적정가보다 싼 것만) | 0~10%: 적정 구간 포함 | 10%↑: 다소 고평가까지 포함",
            )
            under_sort = _fr2.radio(
                "정렬", ["저평가도 높은 순", "추천점수 높은 순", "매매가 낮은 순"], horizontal=True,
                key="under_sort",
            )
            # 전용면적 필터 — 투자전략 탭 기본값(80~110㎡)과 동일하게
            _area_default = area_range if area_range else (80, 110)
            under_area_range = _fr3.slider(
                "전용면적 범위 (㎡)", min_value=0, max_value=200,
                value=_area_default, step=5,
                key="under_area_range",
                help="투자전략 탭의 전용면적 기본값(80~110㎡)과 동일. 소형 구축 제외하려면 하한을 올리세요.",
            )

            # 지역 필터 — 전략 결과에서 지역 목록 동적 추출
            _all_regions_under: list[str] = sorted({
                r for df in [inv, gap, yld] if not df.empty and "지역" in df.columns
                for r in df["지역"].dropna().unique()
            })
            under_regions = st.multiselect(
                "지역 필터 (비워두면 전체)",
                options=_all_regions_under,
                default=[],
                key="under_regions",
                placeholder="지역을 선택하세요…",
            )

        # ── 전략 추천 단지 목록 (inv/gap/yld 결과에 있는 것만) ──────────────
        _strategy_apts: set[str] = set()
        for _sdf in [inv, gap, yld]:
            if not _sdf.empty and "apt_name" in _sdf.columns:
                _strategy_apts.update(_sdf["apt_name"].unique())

        _key_cols = ["apt_name", "region_code", "area_bucket"]
        rows_under = []

        # 갭투자 기반 (전세가율 역산) — 전략 추천 단지만
        if not gap.empty and "rent_median" in gap.columns:
            g_fv = enrich_with_fair_value(gap.copy(), jeonse_col="rent_median")
            g_fv["방법"] = "전세가율 역산"
            mask = g_fv["fv_premium_%"].notna() & (g_fv["fv_premium_%"] <= under_thresh)
            if mask.any():
                rows_under.append(g_fv[mask])

        # 임대수익 기반 (수익률 역산) — 전략 추천 단지만
        if not yld.empty and "monthly_median" in yld.columns:
            y_fv = enrich_with_fair_value(yld.copy(), jeonse_col=None, monthly_col="monthly_median")
            y_fv["방법"] = "수익률 역산"
            mask = y_fv["fv_premium_%"].notna() & (y_fv["fv_premium_%"] <= under_thresh)
            if mask.any():
                rows_under.append(y_fv[mask])

        if not rows_under:
            st.info(
                f"전략 추천 단지 중 저평가({under_thresh}% 이하) 단지가 없습니다. "
                "슬라이더를 올려보세요 (예: 0% → 적정가 이하 전체)."
            )
        else:
            combined = pd.concat(rows_under, ignore_index=True)
            # 전략 추천 단지만 유지
            combined = combined[combined["apt_name"].isin(_strategy_apts)].copy()

            if combined.empty:
                st.info("전략 추천 단지 중 해당 저평가 기준에 맞는 단지가 없습니다.")
            else:
                # 지역 필터
                if under_regions and "지역" in combined.columns:
                    combined = combined[combined["지역"].isin(under_regions)].copy()
                # 전용면적 필터
                if "area_bucket" in combined.columns:
                    combined = combined[
                        (combined["area_bucket"] >= under_area_range[0]) &
                        (combined["area_bucket"] <= under_area_range[1])
                    ].copy()

                if combined.empty:
                    st.info("선택한 조건에 해당하는 저평가 단지가 없습니다. 필터를 조정해보세요.")
                else:
                    # 같은 단지+면적에서 두 방법이 모두 걸리면 더 낮은 fv_premium_% 기준 하나만 남김
                    combined = (
                        combined
                        .sort_values("fv_premium_%")
                        .drop_duplicates(_key_cols, keep="first")
                        .reset_index(drop=True)
                    )

                    if under_sort == "추천점수 높은 순" and "score" in combined.columns:
                        combined = combined.sort_values("score", ascending=False).reset_index(drop=True)
                    elif under_sort == "매매가 낮은 순" and "trade_median" in combined.columns:
                        combined = combined.sort_values("trade_median", ascending=True).reset_index(drop=True)

                    combined["rank"] = range(1, len(combined) + 1)

                    # 네이버 가격 낮은순 매물 링크
                    def _naver_cheap_url(region: str | None, apt_name: str | None) -> str | None:
                        import urllib.parse as _ul
                        if not apt_name:
                            return None
                        clean = _simplify_apt_name(apt_name)
                        tokens = []
                        if region:
                            toks = str(region).strip().split()
                            if toks:
                                last = toks[-1]
                                if any(last.endswith(s) for s in ("동", "읍", "면", "리", "가")):
                                    if len(toks) >= 2:
                                        tokens.append(toks[-2])
                                tokens.append(last)
                        tokens.append(clean)
                        tokens.append("매매")
                        q = " ".join(t for t in tokens if t)
                        enc = _ul.quote(q, safe="")
                        return f"https://m.land.naver.com/search/result/{enc}?rletTypeCd=A01&tradeTypeCd=A1&sortField=prc&sortMethod=asc"

                    combined["naver_url"] = [
                        _naver_cheap_url(r.get("지역"), r.get("apt_name"))
                        for r in combined.to_dict("records")
                    ]

                    # 요약 메트릭
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("전략 추천 저평가 단지", f"{len(combined)}개")
                    mc2.metric(
                        "최대 저평가",
                        f"{combined['fv_premium_%'].min():.1f}%",
                        help="가장 많이 저평가된 단지의 값",
                    )
                    mc3.metric(
                        "평균 저평가",
                        f"{combined['fv_premium_%'].mean():.1f}%",
                    )

                    # 테이블
                    show_cols = [
                        "naver_url", "rank", "지역", "apt_name", "area_bucket",
                        "trade_median", "fair_value", "fv_premium_%", "verdict", "방법",
                    ]
                    if "gap" in combined.columns:          show_cols.append("gap")
                    if "jeonse_ratio" in combined.columns: show_cols.append("jeonse_ratio")
                    if "annual_yield_%" in combined.columns: show_cols.append("annual_yield_%")
                    if "score" in combined.columns:        show_cols.append("score")
                    render_table(
                        combined[[c for c in show_cols if c in combined.columns]],
                        height=600,
                    )
                    st.caption("📌 **보기** 링크 → 네이버 부동산 매물 **가격 낮은순** 정렬로 바로 이동")

                    # 바 차트
                    top_u = combined.head(25).copy()
                    color_map_u = {"전세가율 역산": "#3b82f6", "수익률 역산": "#22c55e"}
                    fig_u = px.bar(
                        top_u, x="apt_name", y="fv_premium_%",
                        color="방법",
                        color_discrete_map=color_map_u,
                        labels={"apt_name": "단지명", "fv_premium_%": "현재가-적정가 (%)"},
                        title=f"전략 추천 저평가 TOP {min(25, len(top_u))} (낮을수록 더 저평가)",
                        text="fv_premium_%",
                    )
                    fig_u.add_hline(y=0, line_dash="dash", line_color="gray")
                    fig_u.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
                    fig_u.update_xaxes(tickangle=-45)
                    st.plotly_chart(fig_u, width='stretch')

                    st.markdown("---")
                    _render_catch_board(combined, "under")

            st.caption(
                "> 이 분석은 투자 판단을 돕기 위한 의사결정 보조 자료이며, "
                "최종 매수·매도 결정은 공식 실거래 데이터, 현장 확인, 금융·세무 전문가 상담 후 내려야 합니다."
            )


