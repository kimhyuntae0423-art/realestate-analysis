"""🧪 실험실 탭 — 부동산 통념 가설을 실거래가로 검증하고 기록.

src/ui/streamlit_app.py 에서 분리 (모듈화 2단계).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.analysis.hypothesis_lab import run_all_and_log, load_log, latest_results, get_pending_hypotheses
from src.ui.shared import render_df

_VERDICT_STYLE = {
    "✅ 지지": "success",
    "❌ 기각(반대방향)": "error",
    "🟡 불확실 (표본부족)": "warning",
    "🟡 불확실 (상관 약함)": "warning",
}


def page_lab():
    st.title("🧪 실험실")
    st.caption(
        "책·전문가들이 흔히 주장하는 부동산 상승 예측 신호를, 이 프로젝트가 모은 실거래가 DB로 "
        "직접 통계 검증합니다. **상관관계는 인과관계가 아닙니다** — 여기 판정은 "
        "'이 표본·이 기간에서 관측된 것'이지 미래를 보장하지 않습니다."
    )

    c1, c2 = st.columns([1, 3])
    with c1:
        run_clicked = st.button("🔄 전체 가설 재검증 실행", type="primary",
                                  use_container_width=True,
                                  help="최근 데이터로 다시 계산해 로그에 새 기록을 남깁니다 (수십 초 소요)")
    with c2:
        st.caption("버튼을 누르면 현재 DB로 재계산하고 결과를 `data/experiments/hypothesis_log.json`에 누적 기록합니다.")

    if run_clicked:
        with st.spinner("가설 검증 중… (거래량·연식·모멘텀 상관 계산)"):
            results = [r.to_dict() for r in run_all_and_log()]
        st.success(f"✅ {len(results)}개 가설 재검증 완료 — 로그에 기록됨")
    else:
        results = latest_results()

    if not results:
        st.info("아직 실행 기록이 없습니다. 위 버튼을 눌러 첫 검증을 실행하세요.")
        return

    st.markdown("---")
    st.markdown("### 📋 최신 판정")

    for r in results:
        verdict = r["verdict"]
        badge = _VERDICT_STYLE.get(verdict, "info")
        with st.container(border=True):
            head = f"**{r['title']}** — {verdict}"
            getattr(st, badge)(head)
            st.markdown(f"**주장**: {r['claim']}")
            stat = r["statistic"]
            stat_str = "N/A (데이터 부족)" if stat != stat else f"{stat:.4f}"
            st.caption(f"통계치(Spearman ρ) = {stat_str} · 표본수 n = {r['n']:,} · 검증일 {r['computed_at']}")

            breakdown = r.get("breakdown")
            if breakdown and all("statistic" in d for d in breakdown.values()):
                st.markdown("**하위그룹 분석**")
                bd_cols = st.columns(len(breakdown))
                for col, (label, d) in zip(bd_cols, breakdown.items()):
                    bd_stat = d["statistic"]
                    bd_stat_str = "N/A" if bd_stat != bd_stat else f"{bd_stat:.4f}"
                    col.metric(label, bd_stat_str, help=f"n={d['n']:,} · {d['verdict']}")
                    col.caption(d["verdict"])
            elif breakdown:
                st.markdown("**이벤트별 상세**")
                for label, d in breakdown.items():
                    st.markdown(f"`{label}` {d.get('note', '')} — 변경지역 증감률 {d.get('shock_delta_%', 'N/A')}%")
                    candidates = d.get("top_후보")
                    if candidates:
                        cand_df = pd.DataFrame(candidates).rename(
                            columns={"region_code": "지역코드", "delta_%": "증감률(%)"})
                        render_df(cand_df)

            with st.expander("방법론 · 반박 여지"):
                st.markdown(f"**계산 방법**: {r['method']}")
                st.markdown(f"**한계 / 반박 여지**: {r['caveats']}")
                if r.get("explored"):
                    st.markdown(f"**이미 시도해본 것들 (재시도 전 참고)**: {r['explored']}")

    # ── 미검증 후보 ──────────────────────────────────────────────────
    pending = get_pending_hypotheses()
    if pending:
        st.markdown("---")
        st.markdown("### 🔬 미검증 후보")
        st.caption("아직 통계 검증을 시도하지 않은 가설입니다.")
        for p in pending:
            with st.container(border=True):
                st.markdown(f"**{p.title}** — ⚪ 미검증")
                st.markdown(f"**주장**: {p.claim}")
                st.caption(f"{p.data_status} · {p.note}")

    # ── 판정 변화 이력 ──────────────────────────────────────────────
    runs = load_log()
    if len(runs) > 1:
        st.markdown("---")
        st.markdown("### 📈 판정 이력")
        st.caption("가설별로 재검증할 때마다 판정이 어떻게 바뀌었는지 봅니다.")
        hist_rows = []
        for run in runs:
            for res in run["results"]:
                hist_rows.append({
                    "검증일": run["run_at"][:16].replace("T", " "),
                    "가설": res["title"],
                    "rho": round(res["statistic"], 3) if res["statistic"] == res["statistic"] else None,
                    "n": res["n"],
                    "판정": res["verdict"],
                })
        hist_df = pd.DataFrame(hist_rows).sort_values("검증일", ascending=False)
        render_df(hist_df, height=300)

    st.caption(
        "> 이 분석은 투자 판단을 돕기 위한 의사결정 보조 자료이며, "
        "최종 매수·매도 결정은 공식 실거래 데이터, 현장 확인, 금융·세무 전문가 상담 후 내려야 합니다."
    )
