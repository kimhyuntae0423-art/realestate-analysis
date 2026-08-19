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
        # ── 섹션 1: 메뉴 ─────────────────────────────────────
        st.markdown("#### 🏠 메뉴")
        page = st.radio(
            "페이지",
            ["💰 나의 한도", "🚀 투자 추천", "💎 저평가 매물", "📊 지역 분석",
             "🗺️ 지도", "🚦 시장 진단", "🔬 전략 백테스트", "🏘️ 처분·매수 전략", "🧪 실험실"],
            label_visibility="collapsed",
            key="nav_page",
        )

        st.divider()

        # ── 섹션 2: 유틸 ─────────────────────────────────────
        st.markdown("#### ⚙️ 유틸")
        if st.button("🔄 캐시 비우기", use_container_width=True, key="nav_clear",
                     help="데이터 수집 후 또는 강제 재계산 시"):
            st.cache_data.clear()
            st.success("캐시 비움")

        with st.expander("🗓️ 데이터 최신화", expanded=False):
            fresh = _data_freshness()
            st.caption("실거래·KB·ECOS·인구이동은 매월 1일 자동 갱신됨 (이 PC 작업 스케줄러)")
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
                "**수동 갱신 필요**\n"
                "• 호재(`config/catalysts.json`): GTX·신도시 확정 시 직접 편집\n"
                "• 등급(`config/region_tiers.json`): 정보 표시용 (점수 산식 X)\n"
                "• 대출규제(`config/loan_regulations.json`): 변경 감지 시 확인 후 직접 편집"
            )
    return page


