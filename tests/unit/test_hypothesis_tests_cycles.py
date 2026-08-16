"""src/analysis/hypothesis_tests_cycles.py — 순환/사이클 계열 가설 검증."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.analysis import hypothesis_tests_cycles as c
from src.database.repository import upsert_trades


def _trade(days_ago, region="11680", apt="A", ppp=6000, amount=100000, area=84.9):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


def _month_ago_days(n: int) -> int:
    """n개월 전 대략적인 일수 (30일/월 근사, 다른 hypothesis 함수들과 동일 관례)."""
    return 30 * n


def _trade_on(date_str, region, apt, ppp, area=84.9, amount=100000):
    """규제 이벤트처럼 특정 고정 날짜를 기준으로 한 거래 (오늘 기준 상대일이 아님)."""
    d = pd.Timestamp(date_str).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp}


# ─── 순환매(키맞추기) 효과 ────────────────────────────────────────────
def test_seoul_leads_other_regions_detects_positive_lag():
    # merge 결과가 leader_chg 기준 상수 입력이 되면 Spearman이 미정의(NaN)가 되므로,
    # 강남이 서로 다른 상승폭(+50%, +20%)을 보인 두 시점을 만들고 각 다음달에 다른 지역이
    # 같은 크기로 따라 오르게 해서 두 컬럼 모두에 분산이 생기도록 구성
    rows = []
    for i in range(6):
        rows.append(_trade(_month_ago_days(4) + i, region="11680", apt="X", ppp=6000))
        rows.append(_trade(_month_ago_days(3) + i, region="11680", apt="X", ppp=9000))    # 강남 t1: +50%
        rows.append(_trade(_month_ago_days(2) + i, region="11680", apt="X", ppp=10800))   # 강남 t2: +20%
        rows.append(_trade(_month_ago_days(3) + i, region="11350", apt="Y", ppp=4000))
        rows.append(_trade(_month_ago_days(2) + i, region="11350", apt="Y", ppp=6000))    # 후행 t1+1: +50%
        rows.append(_trade(_month_ago_days(1) + i, region="11350", apt="Y", ppp=7200))    # 후행 t2+1: +20%
    upsert_trades(rows)

    r = c.test_seoul_leads_other_regions(months=6, min_deals=3)
    assert r.n >= 2
    assert r.statistic > 0  # 강남 상승폭이 클수록 다음달 다른 지역 상승폭도 큼 -> 양의 상관


def test_seoul_leads_other_regions_empty_when_no_data():
    r = c.test_seoul_leads_other_regions()
    assert r.n == 0


# ─── 평형별 순환 (큰 평형 선행) ────────────────────────────────────────
def test_large_units_lead_small_units_detects_positive_lag():
    # 지역 2곳(11680, 11350)에 상승폭이 다른(50% vs 20%) 패턴을 심어야 merge 결과가
    # 2행 이상 & 분산이 있는 데이터가 되어 Spearman 상관이 계산됨
    # (지역 1곳뿐이면 병합 후 1행이라 상관 계산 불가, 상승폭이 같으면 상수 입력이라 NaN이 됨)
    rows = []
    for i in range(6):
        # 11680: 큰 평형(120㎡) 2개월전->1개월전 +50%, 작은 평형(50㎡) 1개월전->이번달 +50% (한달 늦게 따라감)
        rows.append(_trade(_month_ago_days(3) + i, region="11680", area=120.0, apt="BIG", ppp=6000))
        rows.append(_trade(_month_ago_days(2) + i, region="11680", area=120.0, apt="BIG", ppp=9000))
        rows.append(_trade(_month_ago_days(2) + i, region="11680", area=50.0, apt="SMALL", ppp=4000))
        rows.append(_trade(_month_ago_days(1) + i, region="11680", area=50.0, apt="SMALL", ppp=6000))
        # 11350: 큰 평형 +20%, 작은 평형도 한달 늦게 +20%
        rows.append(_trade(_month_ago_days(3) + i, region="11350", area=120.0, apt="BIG", ppp=5000))
        rows.append(_trade(_month_ago_days(2) + i, region="11350", area=120.0, apt="BIG", ppp=6000))
        rows.append(_trade(_month_ago_days(2) + i, region="11350", area=50.0, apt="SMALL", ppp=5000))
        rows.append(_trade(_month_ago_days(1) + i, region="11350", area=50.0, apt="SMALL", ppp=6000))
    upsert_trades(rows)

    r = c.test_large_units_lead_small_units(months=6, min_deals=3)
    assert r.n >= 2
    assert r.statistic > 0


def test_large_units_lead_small_units_empty_when_no_data():
    r = c.test_large_units_lead_small_units()
    assert r.n == 0


# ─── 저가 매수(갭메우기) 재확인 ────────────────────────────────────────
def test_price_level_mean_reversion_detects_negative_correlation():
    # 저가 지역(11350, 전반기 낮은 평당가)이 후반기에 크게 오르고,
    # 고가 지역(11680, 전반기 높은 평당가)은 안 오르는 합성 데이터 -> 가설(저가가 더 오름) 지지
    rows = []
    for i in range(5):
        rows.append(_trade(_month_ago_days(10) + i, region="11350", apt="CHEAP", ppp=3000))
        rows.append(_trade(_month_ago_days(1) + i, region="11350", apt="CHEAP", ppp=5000))  # +67%
        rows.append(_trade(_month_ago_days(10) + i, region="11680", apt="EXP", ppp=9000))
        rows.append(_trade(_month_ago_days(1) + i, region="11680", apt="EXP", ppp=9100))   # +1%
    upsert_trades(rows)

    r = c.test_price_level_mean_reversion(months=12, min_deals=3)
    assert r.n >= 2
    assert r.statistic < 0  # 전반기 평당가 높을수록 후반기 상승률 낮음 -> 음의 상관
    # 표본(n=2)이 MIN_N(30) 미만이라 verdict는 항상 "표본부족"으로 나옴 -> 여기선 statistic만 검증


def test_price_level_mean_reversion_empty_when_no_data():
    r = c.test_price_level_mean_reversion()
    assert r.n == 0


# ─── 규제발 풍선효과 (다중 이벤트) ──────────────────────────────────────
def test_regulation_balloon_effect_detects_reallocation_pattern():
    # 이벤트 A(2023-01-05, 완화): 종로(11110, 규제 유지 -> 해제 대상은 아니고 이 시점엔 그대로
    # "규제 유지"가 아니라 실제로는 shock 대상이지만, 여기선 단순화해 종로를 이벤트A의 shock으로,
    # 강남/서초(GANGNAM4, 항상 stable)를 대조군으로 삼아 "크게 눌렸던 지역일수록(-20%) 대조군이
    # 크게 뛴다(+50%,+45%)"는 패턴을 심음
    rows = []
    for i in range(6):
        rows.append(_trade_on(f"2022-08-{1+i:02d}", "11110", "SHOCK_A", 10000))
        rows.append(_trade_on(f"2023-02-{1+i:02d}", "11110", "SHOCK_A", 8000))    # -20%
        rows.append(_trade_on(f"2022-08-{1+i:02d}", "11680", "STABLE_A1", 10000))
        rows.append(_trade_on(f"2023-02-{1+i:02d}", "11680", "STABLE_A1", 15000))  # +50%
        rows.append(_trade_on(f"2022-08-{1+i:02d}", "11650", "STABLE_A2", 10000))
        rows.append(_trade_on(f"2023-02-{1+i:02d}", "11650", "STABLE_A2", 14500))  # +45%
    # 이벤트 B(2025-10-16, 강화): 수원영통(41117, 신규규제)이 소폭만 밀리고(-2%),
    # 대조군(안양만안·구리, 비규제 유지)이 소폭만 뛰는(+5%,+8%) 약한 버전의 같은 패턴
    for i in range(6):
        rows.append(_trade_on(f"2025-06-{1+i:02d}", "41117", "SHOCK_B", 10000))
        rows.append(_trade_on(f"2025-12-{1+i:02d}", "41117", "SHOCK_B", 9800))    # -2%
        rows.append(_trade_on(f"2025-06-{1+i:02d}", "41171", "STABLE_B1", 10000))
        rows.append(_trade_on(f"2025-12-{1+i:02d}", "41171", "STABLE_B1", 10500))  # +5%
        rows.append(_trade_on(f"2025-06-{1+i:02d}", "41310", "STABLE_B2", 10000))
        rows.append(_trade_on(f"2025-12-{1+i:02d}", "41310", "STABLE_B2", 10800))  # +8%
    upsert_trades(rows)

    r = c.test_regulation_balloon_effect(months_before=6, months_after=6, min_deals=5)
    assert r.n == 2  # 이벤트 2건 (대조군은 지역별로 뻥튀기 안 하고 이벤트당 1개로 집계)
    assert r.statistic < 0  # 많이 눌린 이벤트일수록 대조군이 더 크게 뜀 -> 음의 상관
    assert "2023-01-05" in r.breakdown
    assert "2025-10-16" in r.breakdown
    # 2022-11-14/2026-06-30은 해당 시점 데이터가 없어 자동 제외돼야 함
    assert "2022-11-14" not in r.breakdown
    assert "2026-06-30" not in r.breakdown


def test_regulation_balloon_effect_empty_when_no_data():
    r = c.test_regulation_balloon_effect()
    assert r.n == 0
