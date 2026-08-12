"""src/analysis/gap_backtest.py — 순수 스코어링 헬퍼 검증.

gap_score_backtest/jeonse_risk_backtest/gap_simulation_backtest/gap_walk_forward는
이미 검증된 하위 모듈(backtest.py의 _spearman/_topn_hit, forward_signals.py,
gap_analysis.py)을 조합한 통계 파이프라인이라 별도 스모크 테스트는 생략하고,
투자 판단에 직접 쓰이는 임계값 로직(_jeonse_quality_score, _jeonse_risk_label)만 검증한다.
"""
from __future__ import annotations

from src.analysis.gap_backtest import _jeonse_quality_score, _jeonse_risk_label


def test_jeonse_quality_score_peaks_in_optimal_band():
    assert _jeonse_quality_score(70) == 100.0
    assert _jeonse_quality_score(78) == 100.0


def test_jeonse_quality_score_low_ratio_scores_low():
    assert _jeonse_quality_score(30) == 30.0


def test_jeonse_quality_score_decreases_past_optimal_band():
    at_peak = _jeonse_quality_score(78)
    past_peak = _jeonse_quality_score(85)
    danger_zone = _jeonse_quality_score(95)
    assert at_peak > past_peak > danger_zone
    assert danger_zone >= 0.0


def test_jeonse_quality_score_never_negative():
    assert _jeonse_quality_score(150) >= 0.0


def test_jeonse_risk_label_high_ratio_is_danger():
    assert _jeonse_risk_label(95) == "⚠️ 역전세위험"


def test_jeonse_risk_label_moderate_ratio_is_caution():
    assert _jeonse_risk_label(85) == "🔶 주의"
    # 78~83% 구간은 가속도(하락 추세)가 있어야 주의로 분류
    assert _jeonse_risk_label(80, accel=-3) == "🔶 주의"
    assert _jeonse_risk_label(80, accel=0) == "✅ 적정"


def test_jeonse_risk_label_low_ratio_is_comfortable():
    assert _jeonse_risk_label(60) == "🟢 갭여유"


def test_jeonse_risk_label_normal_range_is_ok():
    assert _jeonse_risk_label(70) == "✅ 적정"
