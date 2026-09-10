"""src/analysis/market_timing.py — 매크로 타이밍 진단 검증."""
from __future__ import annotations

import pandas as pd

from src.analysis.market_timing import market_timing_signal
from src.database.repository import upsert_ecos_series


def _rising_yoy_rows(series, start_month):
    """20개월 연속 원시값 — 앞 12개월 평탄(100), 뒤 8개월 105->112로 증가.
    pct_change(12)를 적용하면 YoY가 5%->12%로 단조증가하고, 마지막(현재) 값이
    역사상 최댓값(퍼센타일 100)이 되도록 설계됨."""
    values = [100.0] * 12 + [105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0]
    return [
        {"series": series, "ym_date": (start_month + k).to_timestamp().date(),
         "value": v, "source": "test"}
        for k, v in enumerate(values)
    ]


def test_market_timing_signal_computes_weighted_score():
    start = (pd.Timestamp.today() - pd.Timedelta(days=30 * 20)).to_period("M")
    rows = _rising_yoy_rows("mortgage_loan_eop", start) + _rising_yoy_rows("m2_eop_raw", start)
    upsert_ecos_series(rows)

    out = market_timing_signal()
    by_id = {s["id"]: s for s in out["signals"]}

    # 주담대(expected_sign=+1): 현재값이 역사적 최댓값 -> 퍼센타일 87.5(=7/8, 자기 자신은
    # "자신보다 작음"에 안 잡히므로 n개 중 최댓값도 100%는 아님) -> favorability도 87.5(우호적)
    assert by_id["mortgage_loan"]["percentile"] == 87.5
    assert by_id["mortgage_loan"]["favorability"] == 87.5

    # M2(expected_sign=-1, 검증된 반대방향): 같은 퍼센타일 87.5지만 favorability는 반대로 낮음
    assert by_id["m2_yoy"]["percentile"] == 87.5
    assert by_id["m2_yoy"]["favorability"] == 12.5

    # 데이터 없는 나머지 신호는 None으로 스킵되지만 에러 없이 처리됨
    assert by_id["kb_sentiment"]["favorability"] is None

    # 커버리지 게이트(2026-09-10): 주담대(0.35)+M2(0.10)=0.45 로 최소기준 0.60 미달이라
    # 종합점수를 내지 않는다. 예전에는 살아있는 가중치로 재정규화해 70.8 을 표시했는데,
    # 근거의 55%가 없는 상태를 정상처럼 보여주는 것이라 None 으로 바꿨다.
    assert out["coverage"] == 0.45
    assert out["score"] is None
    assert set(out["missing"]) == {
        "KB 매수우위지수", "실질금리(기준금리-기대인플레)", "M1/M2 비율",
    }


def test_market_timing_signal_scores_when_coverage_sufficient():
    """커버리지 게이트가 정상 동작까지 막지 않는지 — ECOS 4개가 채워지면 점수가 나온다.

    주담대(0.35)+M2(0.10)+실질금리(0.10)+M1/M2(0.10)=0.65 >= 0.60.
    KB(0.35)는 여전히 비어 있어 커버리지 100%는 아니다.
    """
    start = (pd.Timestamp.today() - pd.Timedelta(days=30 * 20)).to_period("M")
    rows = []
    for series in ("mortgage_loan_eop", "m2_eop_raw", "base_rate",
                   "expected_inflation", "m1_eop_raw"):
        rows += _rising_yoy_rows(series, start)
    upsert_ecos_series(rows)

    out = market_timing_signal()
    assert out["coverage"] >= out["min_coverage"]
    assert out["score"] is not None
    assert 0 <= out["score"] <= 100


def test_market_timing_signal_empty_when_no_data():
    out = market_timing_signal()
    assert out["score"] is None
    assert out["coverage"] == 0.0
    assert all(s["favorability"] is None for s in out["signals"])
