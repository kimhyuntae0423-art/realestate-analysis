"""src/analysis/backtest.py — 백테스트 순수 헬퍼 + region_backtest 스모크 검증.

region_backtest/apt_backtest는 통계적 파이프라인(회귀 지표) 성격이라 결과값의
정확한 수치를 assert하기보다, (1) 순수 헬퍼(_spearman/_topn_hit)의 계산식과
(2) 전체 파이프라인이 합성 데이터에서 크래시 없이 유효한 형태의 결과를 내는지를 검증한다.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.analysis import backtest as bt
from src.database.repository import upsert_trades


def test_months_ago_subtracts_30_days_per_month():
    d = date(2026, 6, 15)
    assert bt._months_ago(d, 1) == d - timedelta(days=30)
    assert bt._months_ago(d, 12) == d - timedelta(days=360)


def test_spearman_perfect_positive_correlation():
    s1 = pd.Series([1, 2, 3, 4, 5])
    s2 = pd.Series([10, 20, 30, 40, 50])
    assert bt._spearman(s1, s2) == pytest.approx(1.0)


def test_spearman_perfect_negative_correlation():
    s1 = pd.Series([1, 2, 3, 4, 5])
    s2 = pd.Series([50, 40, 30, 20, 10])
    assert bt._spearman(s1, s2) == pytest.approx(-1.0)


def test_spearman_returns_nan_when_too_few_points():
    s1 = pd.Series([1, 2, 3])
    s2 = pd.Series([1, 2, 3])
    assert np.isnan(bt._spearman(s1, s2))


def test_topn_hit_perfect_alignment_is_full_hit_rate():
    score = pd.Series([5, 4, 3, 2, 1], index=range(5))
    actual = pd.Series([5, 4, 3, 2, 1], index=range(5))
    assert bt._topn_hit(score, actual, n=2, m_pct=0.4) == 1.0


def test_topn_hit_inverted_alignment_is_low_hit_rate():
    score = pd.Series([5, 4, 3, 2, 1], index=range(5))
    actual = pd.Series([1, 2, 3, 4, 5], index=range(5))
    assert bt._topn_hit(score, actual, n=2, m_pct=0.4) == 0.0


def _trade(region, days_ago, ppp):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": "A",
            "area_m2": 84.9, "deal_amount": 100000, "price_per_pyeong": ppp}


def test_region_backtest_smoke_runs_without_crashing():
    today = date.today()
    as_of = bt._months_ago(today, 12)
    train_start = bt._months_ago(as_of, 12)
    train_mid = bt._months_ago(as_of, 6)
    test_mid = as_of + timedelta(days=180)

    regions = ["11680", "11650", "11710", "11440", "11170"]
    rows = []
    for idx, region in enumerate(regions):
        growth_ppp = 6000 + idx * 500  # 지역마다 다른 상승폭
        # 학습 구간: prior(6000) -> recent(growth_ppp)
        for i in range(4):
            rows.append(_trade(region, (today - train_start).days - i, 6000))
            rows.append(_trade(region, (today - train_mid).days - i, growth_ppp))
        # 검증 구간: prior(6000) -> recent(growth_ppp)
        for i in range(4):
            rows.append(_trade(region, (today - as_of).days - i, 6000))
            rows.append(_trade(region, (today - test_mid).days - i, growth_ppp))
    upsert_trades(rows)

    result = bt.region_backtest(
        as_of=as_of, train_months=12, test_months=12,
        min_train_deals=3, min_test_deals=3,
    )
    assert result.scope == "region"
    assert result.n == len(regions)
    assert np.isnan(result.spearman) or -1.0 <= result.spearman <= 1.0
    assert set(result.component_corr.keys()) == {"catalyst", "tier", "train_growth", "vol_momentum"}
