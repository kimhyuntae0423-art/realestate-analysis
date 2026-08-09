"""recommend.py 점수 계산 로직 유닛테스트.

DB/외부 API 없이 검증 가능한 순수 함수만 대상으로 함:
_jeonse_quality_score, _jeonse_risk_label, region_tier_score/label,
manual_catalyst_score, _apply_gap_scores, _apply_rental_scores, region_summary.
"""
import pandas as pd
import pytest

from src.analysis import recommend as rec


# ─── _jeonse_quality_score (65~78% 최적, 역U자형) ──────────────────────
@pytest.mark.parametrize("ratio, expected", [
    (30, 30.0),    # ratio < 50 구간: ratio 그대로
    (50, 50.0),    # 상승 구간 시작
    (65, 100.0),   # 최적 구간 진입
    (70, 100.0),   # 최적 구간 내부
    (78, 100.0),   # 최적 구간 끝
    (87, 50.0),    # 하락 구간 경계
    (93, 10.0),    # 역전세 위험 구간 경계
    (96, 4.0),     # 위험 구간 내부
    (100, 0.0),    # 0 하한 클립
    (110, 0.0),
])
def test_jeonse_quality_score(ratio, expected):
    assert rec._jeonse_quality_score(ratio) == pytest.approx(expected, abs=0.01)


# ─── _jeonse_risk_label ─────────────────────────────────────────────────
@pytest.mark.parametrize("ratio, accel, expected", [
    (95, 0.0, "⚠️ 역전세위험"),
    (90, 0.0, "⚠️ 역전세위험"),   # >=90 경계
    (85, 0.0, "🔶 주의"),         # >=83
    (80, -3.0, "🔶 주의"),        # 78<=ratio<83, accel<-2
    (78, -5.0, "🔶 주의"),
    (80, 0.0, "✅ 적정"),         # accel 조건 미충족
    (78, 0.0, "✅ 적정"),
    (65, 0.0, "✅ 적정"),
    (60, 0.0, "🟢 갭여유"),
])
def test_jeonse_risk_label(ratio, accel, expected):
    assert rec._jeonse_risk_label(ratio, accel) == expected


# ─── region_tier_score / region_tier_label ───────────────────────────────
# 실제 config/region_tiers.json에 의존하지 않도록 고정 픽스처로 대체(추후 등급표
# 개정에도 테스트가 깨지지 않게 하기 위함).
FAKE_TIER_CFG = {
    "tiers": {
        "1_최상급지": {"score": 100},
        "2_상급지": {"score": 80},
    },
    "default_tier": "5_하급지",
    "default_score_when_missing": 30,
    "region_tier": {
        "11680": "1_최상급지",
        "11110": "2_상급지",
    },
}


def test_region_tier_score_known_region(monkeypatch):
    monkeypatch.setattr(rec, "_load_region_tiers", lambda: FAKE_TIER_CFG)
    assert rec.region_tier_score("11680") == 100.0
    assert rec.region_tier_score("11110") == 80.0


def test_region_tier_score_missing_region_uses_default(monkeypatch):
    monkeypatch.setattr(rec, "_load_region_tiers", lambda: FAKE_TIER_CFG)
    assert rec.region_tier_score("99999") == 30.0


def test_region_tier_label(monkeypatch):
    monkeypatch.setattr(rec, "_load_region_tiers", lambda: FAKE_TIER_CFG)
    assert rec.region_tier_label("11680") == "1_최상급지"
    assert rec.region_tier_label("99999") == "5_하급지"


# ─── manual_catalyst_score ────────────────────────────────────────────────
FAKE_CATALYST_CFG = {
    "region_catalysts": {
        "11680": [{"score": 40}, {"score": 30}],
    },
    "apt_catalysts": [
        {"region_code": "11680", "apt_name": "래미안", "score": 20},
    ],
}


def test_manual_catalyst_score_region_only(monkeypatch):
    monkeypatch.setattr(rec, "_load_catalysts", lambda: FAKE_CATALYST_CFG)
    assert rec.manual_catalyst_score("11680") == 70.0


def test_manual_catalyst_score_includes_matching_apt(monkeypatch):
    monkeypatch.setattr(rec, "_load_catalysts", lambda: FAKE_CATALYST_CFG)
    assert rec.manual_catalyst_score("11680", apt_name="래미안퍼스티지") == 90.0


def test_manual_catalyst_score_ignores_non_matching_apt(monkeypatch):
    monkeypatch.setattr(rec, "_load_catalysts", lambda: FAKE_CATALYST_CFG)
    assert rec.manual_catalyst_score("11680", apt_name="자이") == 70.0


def test_manual_catalyst_score_capped_at_100(monkeypatch):
    cfg = {
        "region_catalysts": {"11680": [{"score": 60}, {"score": 60}]},
        "apt_catalysts": [],
    }
    monkeypatch.setattr(rec, "_load_catalysts", lambda: cfg)
    assert rec.manual_catalyst_score("11680") == 100.0


def test_manual_catalyst_score_unknown_region(monkeypatch):
    monkeypatch.setattr(rec, "_load_catalysts", lambda: FAKE_CATALYST_CFG)
    assert rec.manual_catalyst_score("00000") == 0.0


# ─── _apply_gap_scores (tier_score 80% + activity 20%) ───────────────────
def test_apply_gap_scores_weighting():
    df = pd.DataFrame({
        "region_code": ["A", "B", "C"],
        "tier_score": [100.0, 60.0, 20.0],
        "activity": [10, 100, 50],
        "trade_median": [50000, 30000, 20000],
        "gap": [10000, 5000, 8000],
    })
    result = rec._apply_gap_scores(df)

    assert result["market_score"].tolist() == [50.0, 50.0, 50.0]
    assert result["appreciation_score"].tolist() == pytest.approx([80.0, 56.0, 32.0], abs=0.01)
    assert result["score"].tolist() == pytest.approx([86.7, 73.3, 40.0], abs=0.05)


def test_apply_gap_scores_defaults_when_no_extra_data():
    df = pd.DataFrame({
        "region_code": ["A"],
        "tier_score": [50.0],
        "activity": [10],
        "trade_median": [10000],
        "gap": [1000],
    })
    result = rec._apply_gap_scores(df)
    assert result.loc[0, "jeonse_accel_%p"] == 0.0
    assert result.loc[0, "jeonse_accel_score"] == 50.0
    assert result.loc[0, "leverage_mult"] == 10.0


# ─── _apply_rental_scores (appreciation 70% + yield_quality 30%) ─────────
def test_apply_rental_scores_weighting():
    df = pd.DataFrame({
        "region_code": ["A", "B", "C"],
        "tier_score": [100.0, 60.0, 20.0],
        "annual_yield_%": [3.0, 12.0, 5.0],
    })
    result = rec._apply_rental_scores(df)

    assert result["yield_quality"].tolist() == pytest.approx([2.4, 5.6, 1.6], abs=0.01)
    assert result["score"].tolist() == pytest.approx([90.0, 76.7, 33.3], abs=0.05)


def test_apply_rental_scores_caps_yield_outliers():
    """annual_yield_%는 10%로 클립된 뒤 appreciation_score 비중을 곱함 —
    비정상적으로 높은 수익률(데이터 오류 등)이 점수를 왜곡하지 않는지 확인."""
    df = pd.DataFrame({
        "region_code": ["A", "B"],
        "tier_score": [100.0, 100.0],
        "annual_yield_%": [999.0, 5.0],
    })
    result = rec._apply_rental_scores(df)
    assert result.loc[0, "yield_quality"] == pytest.approx(8.0, abs=0.01)


# ─── region_summary ───────────────────────────────────────────────────────
def test_region_summary_empty_input_returns_empty():
    result = rec.region_summary(pd.DataFrame(), {}, metric_col="gap")
    assert result.empty


def test_region_summary_aggregates_by_region():
    rec_df = pd.DataFrame({
        "region_code": ["11680", "11680", "28110"],
        "apt_name": ["A", "B", "C"],
        "score": [90.0, 80.0, 50.0],
        "gap": [5000, 3000, 8000],
    })
    region_map = {"11680": "강남구", "28110": "부평구"}
    result = rec.region_summary(rec_df, region_map, metric_col="gap")

    gangnam = result[result["region_code"] == "11680"].iloc[0]
    assert gangnam["opportunities"] == 2
    assert gangnam["unique_apts"] == 2
    assert gangnam["avg_score"] == pytest.approx(85.0)
    assert gangnam["min_gap"] == 3000
    assert gangnam["region"] == "강남구"

    # opportunities 내림차순 정렬 확인 (11680: 2건 > 28110: 1건)
    assert result.iloc[0]["region_code"] == "11680"
