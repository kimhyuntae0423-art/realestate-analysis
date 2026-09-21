"""지역 동조 분석 — 전국 공통 추세를 뺀 뒤, 어떤 지역들이 같은 달에 같이 움직이는가.

배경 (2026-09-21 분석, hypothesis_tests_spillover.py docstring 참고):
- 전국 추세를 안 빼면 금리 등 전국 요인 때문에 모든 지역이 서로 상관돼 보인다
  (동탄-오산 동시상관 0.336 이 전국 추세를 빼자 0.077 로 사라짐).
- 80개 시군구에서 동조는 지리(같은 시도끼리 +0.056)보다 가격대(비슷할수록 동조,
  rho -0.251, 순환이동 귀무검정 p<0.005)가 더 강한 요인이었다.
- 소규모 군집(2~4개 지역)은 잡음과 구분되지 않아(실제 안정묶음 7개 vs 가짜 데이터
  평균 7.4개) 군집 목록은 만들지 않고 "특정 지역 기준 동조 순위 + 우연 기준선"만 낸다.

동조는 같은 달에 같이 움직인다는 뜻이지 선행(A가 오르면 B가 따라 오른다)이 아니다 —
타이밍 신호로 쓰지 말 것. 가장 확실한 쓰임은 분산 점검이다.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from config.settings import CO_MOVEMENT_MIN_DEALS, CO_MOVEMENT_MIN_MONTHS
from src.analysis.hypothesis_lab import region_growth_via_unit_tracking
from src.database.repository import fetch_trades_df


def residual_growth_matrix(g: pd.DataFrame, min_deals: int = CO_MOVEMENT_MIN_DEALS,
                           min_months: int = CO_MOVEMENT_MIN_MONTHS) -> pd.DataFrame:
    """region_growth_via_unit_tracking() 결과(region_code, ym, growth, n)를 월×지역
    잔차 성장률 행렬로 바꾼다.

    잔차 = 각 지역 성장률에서 전국(대상 지역들의 월별 중위) 성장률로 설명되는 부분을
    회귀로 뺀 나머지. 단순 차감이 아니라 회귀인 이유: 지역마다 전국 흐름에 반응하는
    크기(기울기)가 달라서, 차감만 하면 민감한 지역끼리 전국 흐름 때문에 같이 움직이는
    것처럼 남는다.
    """
    g = g[g["n"] >= min_deals]
    if g.empty:
        return pd.DataFrame()
    P = g.pivot(index="ym", columns="region_code", values="growth").astype(float).sort_index()
    P = P.loc[:, P.count() >= min_months]
    if P.shape[1] < 3:
        return pd.DataFrame()
    nat = P.median(axis=1)
    R = pd.DataFrame(index=P.index, columns=P.columns, dtype=float)
    for c in P.columns:
        m = P[c].notna() & nat.notna()
        b, a = np.polyfit(nat[m], P[c][m], 1)
        R.loc[m, c] = P[c][m] - (a + b * nat[m])
    return R


def co_moving_regions(R: pd.DataFrame, region_code: str,
                      top: int = 10) -> tuple[pd.DataFrame, float | None]:
    """region_code 와 같은 달에 같이 움직이는 지역 상위 top개와 우연 기준선.

    반환 df 컬럼: region_code, corr(전체 기간 Spearman), corr_first_half,
    corr_second_half, above_chance.

    우연 기준선: 기준 지역 시계열을 3~(n-3)개월 순환이동해 시간 정렬만 깨뜨린(자기상관은
    보존) 가짜 시계열로 같은 계산을 했을 때 "최상위 지역의 상관"의 95백분위. 이걸 넘는
    지역은 수십 개 지역 중 우연히 1등으로 나온 값보다도 높다는 뜻이다. 순환이동 가짓수가
    n-6개뿐이라(27개월이면 21개) 기준선 자체도 대략적인 값이다.
    """
    if R.empty or region_code not in R.columns:
        return pd.DataFrame(), None

    def _corr(sub: pd.DataFrame) -> pd.Series:
        r = sub.rank()
        return r.drop(columns=region_code).corrwith(r[region_code])

    half = len(R) // 2
    corr, c1, c2 = _corr(R), _corr(R.iloc[:half]), _corr(R.iloc[half:])

    others = R.drop(columns=region_code).rank()
    vals = R[region_code].values
    null_max = [others.corrwith(pd.Series(np.roll(vals, k), index=R.index).rank()).max()
                for k in range(3, len(R) - 3)]
    thr = float(np.nanpercentile(null_max, 95)) if len(null_max) >= 5 else None

    out = pd.DataFrame({
        "region_code": corr.index,
        "corr": corr.values,
        "corr_first_half": c1.reindex(corr.index).values,
        "corr_second_half": c2.reindex(corr.index).values,
    }).dropna(subset=["corr"]).sort_values("corr", ascending=False).head(top)
    out["above_chance"] = (out["corr"] > thr) if thr is not None else False
    return out.reset_index(drop=True), thr


def build_co_movement_base(months: int = 60) -> tuple[pd.DataFrame, pd.Series]:
    """DB에서 잔차 성장률 행렬과 지역별 최근 12개월 평당가 중위를 만든다 (UI 캐시용).

    평당가를 같이 내는 이유: 동조가 지리보다 가격대를 따라 나타나므로, 표에 가격을
    나란히 보여줘야 사용자가 그 패턴을 읽을 수 있다.
    """
    df = fetch_trades_df(date_from=date.today() - timedelta(days=30 * months))
    if df.empty:
        return pd.DataFrame(), pd.Series(dtype=float)
    R = residual_growth_matrix(region_growth_via_unit_tracking(df, ["region_code"]))
    recent = df[pd.to_datetime(df["deal_date"]) >= pd.Timestamp(date.today() - timedelta(days=365))]
    price = recent.groupby("region_code")["price_per_pyeong"].median().astype(float)
    return R, price
