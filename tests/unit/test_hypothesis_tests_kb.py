"""src/analysis/hypothesis_tests_kb.py — KB 가격 시계열 교차검증 가설 검증."""
from __future__ import annotations

from datetime import date

from src.analysis import hypothesis_tests_kb as k
from src.database.repository import session_scope
from src.database.models import SupplySchedule, KbSentimentIndex, KbPriceSeries

M0, M1, M2 = date(2025, 4, 1), date(2025, 5, 1), date(2025, 6, 1)


def _add_kb_price(region="11"):
    with session_scope() as s:
        s.add(KbPriceSeries(series="median_price_apt_sale", region_code=region,
                             ym_date=M0, value=10000.0, source="test"))
        s.add(KbPriceSeries(series="median_price_apt_sale", region_code=region,
                             ym_date=M1, value=9000.0, source="test"))    # M0->M1 -10%
        s.add(KbPriceSeries(series="median_price_apt_sale", region_code=region,
                             ym_date=M2, value=10800.0, source="test"))  # M1->M2 +20%


def test_supply_leads_price_decline_kb_detects_negative_correlation():
    _add_kb_price()
    with session_scope() as s:
        s.add(SupplySchedule(region_code="11", move_in_date=M0, units=1000, source="test"))
        s.add(SupplySchedule(region_code="11", move_in_date=M1, units=100, source="test"))

    r = k.test_supply_leads_price_decline_kb()
    assert r.n >= 2
    assert r.statistic < 0  # 입주물량 많을수록 다음달 KB 가격 상승폭 작음 -> 음의 상관


def test_supply_leads_price_decline_kb_empty_when_no_data():
    r = k.test_supply_leads_price_decline_kb()
    assert r.n == 0


def test_buyer_sentiment_leads_price_kb_detects_positive_correlation():
    _add_kb_price()
    with session_scope() as s:
        s.add(KbSentimentIndex(region_code="11", ym_date=M0, sentiment_index=90.0,
                                buy_more_pct=20, sell_more_pct=30, similar_pct=50, source="test"))
        s.add(KbSentimentIndex(region_code="11", ym_date=M1, sentiment_index=150.0,
                                buy_more_pct=60, sell_more_pct=10, similar_pct=30, source="test"))

    r = k.test_buyer_sentiment_leads_price_kb()
    assert r.n >= 2
    assert r.statistic > 0  # 매수우위지수 높을수록 다음달 KB 가격 상승폭 큼 -> 양의 상관


def test_buyer_sentiment_leads_price_kb_empty_when_no_data():
    r = k.test_buyer_sentiment_leads_price_kb()
    assert r.n == 0
