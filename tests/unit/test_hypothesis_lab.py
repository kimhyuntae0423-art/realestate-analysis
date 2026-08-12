"""src/analysis/hypothesis_lab.py — 가설 검증 실험실 검증."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.analysis import hypothesis_lab as lab
from src.analysis.hypothesis_lab import HypothesisResult
from src.database.repository import upsert_trades


def _trade(days_ago, region="11680", apt="A", ppp=6000, amount=100000,
           build_year=2015, area=84.9):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp,
            "build_year": build_year}


# ─── verdict 임계값 로직 ────────────────────────────────────────────
def test_verdict_insufficient_sample():
    r = HypothesisResult(id="x", title="t", claim="c", method="m",
                          statistic=0.9, n=10, expected_sign=1, caveats="")
    assert r.verdict == "🟡 불확실 (표본부족)"


def test_verdict_weak_correlation():
    r = HypothesisResult(id="x", title="t", claim="c", method="m",
                          statistic=0.05, n=1000, expected_sign=1, caveats="")
    assert r.verdict == "🟡 불확실 (상관 약함)"


def test_verdict_supported_same_sign():
    r = HypothesisResult(id="x", title="t", claim="c", method="m",
                          statistic=0.3, n=1000, expected_sign=1, caveats="")
    assert r.verdict == "✅ 지지"


def test_verdict_rejected_opposite_sign():
    r = HypothesisResult(id="x", title="t", claim="c", method="m",
                          statistic=-0.3, n=1000, expected_sign=1, caveats="")
    assert r.verdict == "❌ 기각(반대방향)"


def test_verdict_nan_statistic_is_uncertain():
    r = HypothesisResult(id="x", title="t", claim="c", method="m",
                          statistic=float("nan"), n=1000, expected_sign=1, caveats="")
    assert r.verdict == "🟡 불확실 (표본부족)"


# ─── 재건축 연한 효과 ────────────────────────────────────────────────
def test_redevelopment_age_effect_detects_positive_signal():
    # 오래된 단지(1990)는 크게 오르고, 신축(2020)은 안 오르는 합성 데이터
    rows = []
    for i in range(5):
        rows.append(_trade(400 + i, apt="OLD", ppp=6000, build_year=1990))
        rows.append(_trade(10 + i, apt="OLD", ppp=9000, build_year=1990))
        rows.append(_trade(400 + i, apt="NEW", ppp=6000, build_year=2020))
        rows.append(_trade(10 + i, apt="NEW", ppp=6050, build_year=2020))
    upsert_trades(rows)

    r = lab.test_redevelopment_age_effect(months=24, min_deals=3)
    assert r.n >= 2
    assert r.statistic > 0  # 나이 클수록 더 오름 -> 양의 상관


def test_redevelopment_age_effect_empty_when_no_data():
    r = lab.test_redevelopment_age_effect()
    assert r.n == 0
    assert r.verdict == "🟡 불확실 (표본부족)"


# ─── 거래량 선행지표 ────────────────────────────────────────────────
def test_volume_leads_price_empty_when_no_data():
    r = lab.test_volume_leads_price()
    assert r.n == 0


def test_volume_leads_price_computes_lead_and_contemporaneous():
    rows = []
    for m in range(1, 13):
        d = date(2025, m, 1)
        n_deals = 5 if m % 2 == 0 else 15  # 거래량 진동
        for i in range(n_deals):
            rows.append(_trade((date.today() - d).days - i, ppp=6000 + m * 50))
    upsert_trades(rows)

    r = lab.test_volume_leads_price(months=13)
    assert r.n > 0
    assert "동시성" in r.caveats


# ─── 모멘텀 지속 vs 평균회귀 ─────────────────────────────────────────
def test_momentum_vs_reversion_detects_persistence():
    # A: 꾸준히 상승(모멘텀), B: 계속 하락(대칭적으로 성장a·성장b 둘다 음수라도 같은 부호=모멘텀)
    rows = []
    for i in range(4):
        rows.append(_trade(700 + i, apt="A", ppp=5000))
        rows.append(_trade(400 + i, apt="A", ppp=6000))
        rows.append(_trade(50 + i, apt="A", ppp=7500))
        rows.append(_trade(700 + i, apt="B", ppp=7000))
        rows.append(_trade(400 + i, apt="B", ppp=6500))
        rows.append(_trade(50 + i, apt="B", ppp=5500))
    upsert_trades(rows)

    r = lab.test_momentum_vs_reversion(months=24, min_deals=3)
    assert r.n >= 2
    assert r.statistic > 0  # growth_a, growth_b 둘 다 같은 방향(A:+/+ , B:-/-) -> 양의 상관


def test_momentum_vs_reversion_empty_when_no_data():
    r = lab.test_momentum_vs_reversion()
    assert r.n == 0


# ─── 로그 기록 ──────────────────────────────────────────────────────
def test_run_all_and_log_appends_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, "LOG_PATH", tmp_path / "hypothesis_log.json")
    assert lab.load_log() == []

    results = lab.run_all_and_log()
    assert len(results) == 3
    runs = lab.load_log()
    assert len(runs) == 1
    assert len(runs[0]["results"]) == 3
    assert "verdict" in runs[0]["results"][0]

    lab.run_all_and_log()
    assert len(lab.load_log()) == 2  # 두 번째 실행이 append 됨


def test_latest_results_returns_most_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, "LOG_PATH", tmp_path / "hypothesis_log.json")
    assert lab.latest_results() is None
    lab.run_all_and_log()
    assert lab.latest_results() is not None
    assert len(lab.latest_results()) == 3
