"""부동산 통념 가설 검증 — "지역 파급(스필오버)" 계열: 특정 선도지역 → 인근 하급지 갭메우기.

hypothesis_tests_cycles.py의 순환매(키맞추기) 가설(test_seoul_leads_other_regions)은
강남 → 전국 전체를 대상으로 지역간 중앙값을 써서 검증한다. 전국 단위로 뭉치면 "특정
벨트(반도체 등 국지적 호재)를 낀 인접지역"만의 파급은 다른 지역들의 노이즈에 묻혀 안
보일 수 있다. 이 파일은 사용자가 임장 중 관찰한 "동탄(상급지) 상승이 병점·오산·평택 등
인근 하급지로 시차를 두고 번진다"는 구체적 관찰을, 그 지역들로 범위를 좁혀 직접
검증한다. 300줄 제한으로 hypothesis_tests_cycles.py와 분리.

── 결론 (2026-09-21) — 정기 재검증에서 제외하고 기록으로만 남김 ──────────────
생각: 동탄이 오르면 병점·오산·평택이 시차를 두고 갭을 메우며 따라 오른다.
실제: "시차를 두고"는 뒷받침되지 않는다. "같이 움직인다"는 일부 맞다.

- 원본 t+1 상관(병점 +0.575, 평택 +0.494)은 동탄 자체의 관성 때문에 생긴 착시였다.
  동탄은 한 번 오르면 다음 달도 오르는 성향이 매우 강해서(자기상관 +0.82), "이번 달
  같이 오름" + "동탄은 다음 달도 오름"이 겹치면 선행처럼 보인다. AR(1) 사전백색화로
  이 관성을 빼면 병점 +0.143, 평택 +0.299(t+2에선 -0.326)로 떨어진다.
- 같은 달 동조는 병점·평택에 실재한다 — 전국 추세를 빼도 병점 +0.560, 평택 +0.333.
  오산은 전국 추세를 빼면 +0.077로 사라진다(오산의 동조는 전국 공통 요인뿐).
- 후속 분석(80개 시군구 동조 분석, 순환이동 귀무검정 200회): 동탄과 실제로 같이
  움직이는 지역은 인근 하급지가 아니라 **비슷한 가격대** 지역이었다 — 서울 도봉·중랑,
  수원 영통·팔달, 군포(평당 2,300~3,200만원, 동탄 3,009만원). 이 동조는 후반기에
  강해졌다(전반 +0.26 -> 후반 +0.69). 전국적으로도 "가격대가 비슷할수록 같이
  움직인다"가 지리(같은 시도)보다 강한 요인이었다(rho -0.251, 귀무 p<0.005).
- 표본 27개월이라 "선도가 없다고 증명"된 게 아니라 "선도 증거가 없다"이다.

제외 이유: 설계상 t+0 포함 시차 중 최대값을 대표값으로 써서, n이 MIN_N(30)을 넘는
2027년 초에 위 착시로 "✅ 지지"로 자동 전환될 구조였다. 재검증이 필요하면 시차를
고정하고 사전백색화를 넣은 뒤 다시 등록할 것. 함수·테스트는 기록용으로 유지한다.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.database.repository import fetch_trades_df
from src.analysis.hypothesis_lab import (
    HypothesisResult, _empty_result, _verdict_for, region_growth_via_unit_tracking,
)

# config/regions.json 코드 기준. 2026-07 화성 동탄구가 용인 기흥구·구리와 함께
# 신규 규제로 묶인 배경(반도체벨트: 용인 클러스터-화성 삼성캠퍼스)은
# hypothesis_tests_cycles.py::GG_2026_NEW 참고.
DONGTAN = "41597"  # 화성시 동탄구 — 반도체벨트 인접 상급지
ADJACENT_FOLLOWERS = {
    "41595": "화성 병점구",  # 동탄과 같은 화성시 — 물리적으로 가장 가까운 인접구
    "41370": "오산시",       # 동탄-평택 사이 경부선 라인
    "41220": "평택시",       # 삼성전자 평택캠퍼스(반도체) 인접, 지제역 포함 — 사용자가 지목한 지역
}


def test_dongtan_spillover_to_adjacent(
    months: int = 60,
    leader_region: str = DONGTAN,
    follower_regions: dict[str, str] | None = None,
    max_lag: int = 3,
    area_tol: float = 5.0,
    min_unit_deals: int = 1,
) -> HypothesisResult:
    """동탄(상급지) 상승이 인근 하급지로 갭을 메우며 번지는지 지역·시차별로 검증.

    전국 대상 순환매 가설(test_seoul_leads_other_regions)과 같은 방법론(단지+평형
    추적 성장률)을 쓰되, 대상을 동탄 + 인근 3개 지역으로만 좁힌다. 시차는 t+0~t+max_lag
    개월을 전부 계산해 지역별로 가장 강한 시차를 breakdown에 남기고, 그 지역별 최선값의
    중앙값을 종합 통계치로 삼는다.
    """
    followers = follower_regions or ADJACENT_FOLLOWERS
    meta = dict(
        id="dongtan_adjacent_spillover",
        title="동탄발 인근지역 갭메우기(풍선효과)",
        claim="동탄(상급지·반도체벨트)이 오르면 시차를 두고 병점·오산·평택 등 인근 하급지가 "
              "갭을 메우며 따라 오른다 — 전국 대상 순환매 가설을 이 벨트로 좁혀 재검증",
        method=f"단지+평형 단위 추적 성장률(구성효과 제거)로 동탄구({leader_region}) 이번달 "
               f"성장률(t)과 인근 {len(followers)}개 지역 각각의 t+0~t+{max_lag}개월 성장률의 "
               f"Spearman 상관을 지역×시차별로 전부 계산, 최근 {months}개월. 종합 통계치는 "
               "지역별로 가장 강한 시차의 결과를 지역 간 중앙값으로 집계.",
        expected_sign=1,
        caveats="후보 지역·최대시차를 사용자 임장 관찰(2026-09)에 맞춰 미리 골랐다 — 지역당 "
                "여러 시차 중 가장 잘 맞는 것을 골라 쓰므로 다중비교로 우연히 유의해 보일 "
                "위험(멀티플 테스팅)이 있음. 후보가 3개 지역뿐이라 전국판보다 표본이 훨씬 "
                "작고 잡음에 민감함. 화성 동탄구는 2026-07 신규 규제 지정 지역이라 최근 "
                "구간엔 규제발 자금 이동(규제발 풍선효과 가설과 원인이 겹침)도 섞여 있어, "
                "순수 '선도-추종'과 '규제 후 재배치'를 이 표본만으로는 분리하지 못함. "
                "반도체(삼성전자 평택캠퍼스 등) 호재 자체의 효과는 이 통계로 직접 검증되지 "
                "않으며, 가격 파급의 시차 패턴만 확인한다.",
    )
    if not followers:
        return _empty_result(**meta)

    cutoff = date.today() - timedelta(days=30 * months)
    codes = [leader_region] + list(followers.keys())
    # 거래가 없는 지역은 fetch_trades_df가 전 컬럼 object dtype인 빈 프레임을 주고,
    # 그걸 concat에 섞으면 price_per_pyeong까지 object로 승격돼 growth가 object가 되고
    # 아래 spearmanr이 numpy 내부에서 터진다 -> 빈 프레임은 concat 전에 제외한다.
    # (후보 지역 중 일부만 데이터가 없는 건 정상 상황이라 "데이터 없음"으로 보고돼야 함)
    frames = [f for f in (fetch_trades_df(region_code=c, date_from=cutoff) for c in codes)
              if not f.empty]
    if not frames:
        return _empty_result(**meta)
    df = pd.concat(frames, ignore_index=True)
    if df.empty:
        return _empty_result(**meta)

    g = region_growth_via_unit_tracking(df, ["region_code"], area_tol, min_unit_deals)
    if g.empty:
        return _empty_result(**meta)

    leader = g[g["region_code"] == leader_region][["ym", "growth"]].rename(
        columns={"growth": "leader_chg"}).dropna()
    if leader.empty:
        return _empty_result(**meta)

    breakdown: dict[str, dict] = {}
    explored_lines: list[str] = []
    region_best_rhos: list[float] = []

    for code, name in followers.items():
        follower = g[g["region_code"] == code][["ym", "growth"]].rename(
            columns={"growth": "follower_chg"}).dropna()
        if follower.empty:
            explored_lines.append(f"{name}: 데이터 없음")
            continue

        lag_results = []  # (lag, rho, n)
        for lag in range(0, max_lag + 1):
            leader_shifted = leader.copy()
            leader_shifted["ym"] = leader_shifted["ym"] + lag
            merged = follower.merge(leader_shifted, on="ym", how="inner")
            merged = merged.replace([np.inf, -np.inf], np.nan).dropna()
            if len(merged) < 2:
                continue
            rho, _ = spearmanr(merged["leader_chg"], merged["follower_chg"])
            lag_results.append((lag, float(rho), len(merged)))

        if not lag_results:
            explored_lines.append(f"{name}: 매칭되는 달 없음")
            continue

        explored_lines.append(
            f"{name}: " + ", ".join(
                f"t+{lag}개월 ρ={rho:+.3f}(n={n})" for lag, rho, n in lag_results
            )
        )
        best_lag, best_rho, best_n = max(lag_results, key=lambda x: x[1])
        breakdown[f"{name} (t+{best_lag}개월)"] = {
            "statistic": best_rho, "n": best_n,
            "verdict": _verdict_for(best_rho, best_n, 1),
        }
        region_best_rhos.append(best_rho)

    if not region_best_rhos:
        return _empty_result(**meta)

    overall_n = int(np.median([d["n"] for d in breakdown.values()]))
    return HypothesisResult(
        statistic=float(np.median(region_best_rhos)),
        n=overall_n,
        breakdown=breakdown,
        explored="; ".join(explored_lines),
        **meta,
    )
