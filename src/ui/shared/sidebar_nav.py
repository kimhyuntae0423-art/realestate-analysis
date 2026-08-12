"""사이드바 페이지 네비게이션.

src/ui/shared.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
import streamlit as st

from src.ui.shared.regions import REGIONS
from src.ui.shared.data_refresh import _data_freshness, _refresh_recent_data


def _sidebar_nav() -> str:
    """사이드바: 페이지 네비게이션 + 캐시 클리어 + 데이터 최신화. 모든 페이지 공통."""
    with st.sidebar:
        if "_nav_section" not in st.session_state:
            st.session_state["_nav_section"] = "analysis"

        def _on_analysis_nav():
            st.session_state["_nav_section"] = "analysis"

        _sec = st.session_state["_nav_section"]

        # ── 섹션 1: 부동산 분석 ──────────────────────────────
        st.markdown("#### 🏠 부동산 분석")
        page_radio = st.radio(
            "페이지",
            ["💰 나의 한도", "🚀 투자 추천", "💎 저평가 매물", "📊 지역 분석", "🗺️ 지도", "🚦 시장 진단"],
            label_visibility="collapsed",
            key="nav_page",
            on_change=_on_analysis_nav,
        )

        # ── 섹션 2: 도구 ─────────────────────────────────────
        st.markdown("#### 🛠️ 도구")
        if st.button(
            "🔬 전략 백테스트",
            use_container_width=True,
            key="nav_backtest",
            type="primary" if _sec == "backtest" else "secondary",
        ):
            st.session_state["_nav_section"] = "backtest"
            st.rerun()

        if st.button(
            "🏘️ 처분·매수 전략 플래너",
            use_container_width=True,
            key="nav_portfolio",
            type="primary" if _sec == "portfolio" else "secondary",
        ):
            st.session_state["_nav_section"] = "portfolio"
            st.rerun()

        if st.session_state["_nav_section"] == "backtest":
            page = "🔬 전략 백테스트"
        elif st.session_state["_nav_section"] == "portfolio":
            page = "🏘️ 처분·매수 전략"
        else:
            page = page_radio

        # ── 섹션 3: 유틸 ─────────────────────────────────────
        st.markdown("#### ⚙️ 유틸")
        if st.button("🔄 캐시 비우기", use_container_width=True, key="nav_clear",
                     help="데이터 수집 후 또는 강제 재계산 시"):
            st.cache_data.clear()
            st.success("캐시 비움")

        with st.expander("🗓️ 데이터 최신화", expanded=False):
            fresh = _data_freshness()
            st.caption("권장 주기: **분기 1회**")
            for label, info in fresh.items():
                last = info.get("last")
                days = info.get("days_ago")
                if isinstance(last, str):
                    # config 파일
                    icon = "📝"
                    line = f"{icon} **{label}**: {last[:30]}"
                elif last is None:
                    icon = "❌"
                    line = f"{icon} **{label}**: 데이터 없음"
                else:
                    if days is not None and days <= 30:
                        icon = "✅"
                    elif days is not None and days <= 90:
                        icon = "🟡"
                    else:
                        icon = "🔴"
                    line = f"{icon} **{label}**: {last} ({days}일 전)"
                st.caption(line)

            st.markdown("")
            # 시/도 선택 (첫 수집 또는 특정 지역만 갱신)
            sido_options = list(REGIONS.keys())
            selected_sido = st.multiselect(
                "수집할 시/도 선택", sido_options, default=[],
                key="nav_sido_select",
                help="비워두면 DB에 있는 기존 지역만 갱신. 처음엔 원하는 시/도를 선택하세요.",
            )
            selected_regions = None
            if selected_sido:
                selected_regions = [
                    code for s in selected_sido
                    for code in REGIONS.get(s, {}).keys()
                ]

            if st.button("🔄 데이터 수집 (최근 3개월)",
                         width='stretch', type="primary", key="nav_refresh"):
                with st.spinner("국토부 실거래 수집 중… 5~10분 소요"):
                    res = _refresh_recent_data(months=3, regions=selected_regions)
                msg = f"✅ 매매 {res['trade']:,}건 / 전월세 {res['rent']:,}건 신규 upsert"
                st.success(msg)
                if res["errors"]:
                    st.error(f"⚠️ {len(res['errors'])}개 오류:\n" + "\n".join(res["errors"][:5]))
                st.cache_data.clear()

            st.caption(
                "**자동 갱신**\n"
                "• 실거래 매매·전월세 (국토부 API) ← 점수 산정에 사용\n\n"
                "**수동 갱신**\n"
                "• 호재(`config/catalysts.json`): GTX·신도시 확정 시 직접 편집\n"
                "• 등급(`config/region_tiers.json`): 정보 표시용 (점수 산식 X)\n"
                "• 대출규제(`config/loan_regulations.json`): 변경 감지 시 확인 후 직접 편집\n\n"
                "**중단된 수집** (실제 API 검증 결과 제거됨)\n"
                "• KOSIS 입주물량·인구이동 — 필수 파라미터 누락/통계표 미존재로 항상 실패\n"
                "• 카카오 뉴스검색 기반 규제뉴스 감지 — 카카오가 news 검색 카테고리 자체를 폐지(404)"
            )

        with st.expander("📜 개발 히스토리", expanded=False):
            st.markdown(
                """
**v0.1 — 초기 시스템 (2026-05)**
- 호재 + 상급지(tier) + 다양한 선행지표(전세가율·인구·공급·RS) 종합 점수
- 사용자가 슬라이더로 호재·tier 가중치 조절

**v0.2 — KOSIS 데이터 통합**
- 인구이동·입주물량(시도 단위) 추가 → 시도 단위 입주물량을 시군구로 분배
- 화성시 4구 분구 코드(41591/93/95/97) 발견 후 별도 수집

**v0.3 — prestige 시그널 (시군구 내 대장 단지)**
- 단지 평당가가 시군구 평균 대비 얼마나 높은지 백분위
- 대장 아파트 가산점

**v0.4 — market 시그널 (시군구 자체의 시장가치)**
- 시군구 중위 평당가의 전국 백분위
- tier(규제 기준)가 못 잡는 시장 평가 보완 (마포 80→93)

**v0.5 — 호재 슬라이더 통합**
- 호재 점수를 region_score에 가산하는 강도로 재정의
- 평택처럼 시장가 낮지만 잠재력 큰 곳 발굴 도구

**v1.0 — 단순화 (현재, 다중 시점 백테스트 기반)**
- 핵심 결과: **"좋은 동네의 대장 단지가 가장 잘 오른다"** (마태 효과 ρ +0.62)
- **저평가 가설 데이터로 기각** — 평당가 낮은 곳이 더 안 오름 (ρ -0.61)
- 최종 점수 = `market 70% + prestige 30% + 호재 가산`
- 제외된 신호: tier(약), jeonse_accel(역상관), population(역상관), supply_pressure(약)
- tier·jeonse·population·supply는 데이터 수집 또는 점수 산식에서 제외
                """
            )
            st.caption("자세한 백테스트 결과/메서드는 별도 메모리에 저장됨.")

        st.caption(
            "각 페이지가 자체 입력을 가집니다.\n\n"
            "💰 한도 = 시드/소득 기반 매수가\n"
            "🚀 추천 = 매물 검색\n"
            "📊 지역 = 단일 시군구 시계열\n"
            "🗺️ 지도 = 전국 시각화\n"
            "🚦 진단 = 시장 환경\n"
            "🔬 백테스트 = 전략별 예측력 검증"
        )
    return page


