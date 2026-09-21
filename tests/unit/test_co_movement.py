"""src/analysis/co_movement.py — 전국 추세 제거 후 지역 동조 순위."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.co_movement import co_moving_regions, residual_growth_matrix

MONTHS = 27


def _growth_frame(series: dict[str, np.ndarray], n: int = 50) -> pd.DataFrame:
    ym = pd.period_range("2024-07", periods=MONTHS, freq="M")
    rows = [{"region_code": code, "ym": p, "growth": v, "n": n}
            for code, vals in series.items() for p, v in zip(ym, vals)]
    return pd.DataFrame(rows)


def _synthetic(seed: int = 0) -> dict[str, np.ndarray]:
    # 모든 지역에 큰 전국 추세 T가 깔려 있고, A·B만 작은 공통 성분 S를 공유한다.
    rng = np.random.default_rng(seed)
    T = rng.normal(0, 0.05, MONTHS)
    S = rng.normal(0, 0.02, MONTHS)
    out = {c: T + rng.normal(0, 0.01, MONTHS) for c in "CDEFGH"}
    out["A"] = T + S + rng.normal(0, 0.005, MONTHS)
    out["B"] = T + S + rng.normal(0, 0.005, MONTHS)
    return out


def test_raw_growth_is_dominated_by_national_trend():
    # 전제 확인: 추세 제거 없이 보면 A는 동조 짝이 아닌 C와도 강하게 상관된다
    s = _synthetic()
    raw = pd.DataFrame(s).rank().corr()
    assert raw.at["A", "C"] > 0.8


def test_residual_isolates_the_shared_component():
    R = residual_growth_matrix(_growth_frame(_synthetic()))
    df, _ = co_moving_regions(R, "A")
    assert df.iloc[0]["region_code"] == "B"
    assert df.iloc[0]["corr"] > 0.7
    others = df[df["region_code"] != "B"]["corr"]
    assert others.abs().max() < df.iloc[0]["corr"] - 0.3


def test_shared_component_exceeds_chance_line():
    R = residual_growth_matrix(_growth_frame(_synthetic()))
    df, thr = co_moving_regions(R, "A")
    assert thr is not None
    assert bool(df.iloc[0]["above_chance"]) is True


def test_half_period_columns_present():
    R = residual_growth_matrix(_growth_frame(_synthetic()))
    df, _ = co_moving_regions(R, "A")
    assert {"corr_first_half", "corr_second_half"} <= set(df.columns)
    assert df.iloc[0]["corr_first_half"] > 0.5 and df.iloc[0]["corr_second_half"] > 0.5


def test_thin_region_is_excluded_and_returns_empty():
    s = _synthetic()
    g = _growth_frame(s)
    # Z는 달마다 거래가 5건뿐 -> min_deals(20) 미달로 분석 대상에서 빠져야 함
    g = pd.concat([g, _growth_frame({"Z": s["A"]}, n=5)], ignore_index=True)
    R = residual_growth_matrix(g)
    assert "Z" not in R.columns
    df, thr = co_moving_regions(R, "Z")
    assert df.empty and thr is None


def test_too_few_months_is_excluded():
    s = _synthetic()
    g = _growth_frame(s)
    short = _growth_frame({"Y": s["A"]}).head(10)  # 10개월뿐 -> min_months(24) 미달
    R = residual_growth_matrix(pd.concat([g, short], ignore_index=True))
    assert "Y" not in R.columns


def test_empty_input():
    empty = pd.DataFrame(columns=["region_code", "ym", "growth", "n"])
    assert residual_growth_matrix(empty).empty
