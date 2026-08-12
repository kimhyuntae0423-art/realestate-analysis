"""src/analysis/recommend.py — 추천 엔진 핵심 검증.

config 기반 순수 함수(manual_catalyst_score, region_tier_*)와,
4대 추천 함수(recommend_gap_investment/rental_yield/buy_outright/investment_focus)의
DB 기반 스모크 검증(필터·정렬·핵심 컬럼)을 다룬다.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.analysis import recommend as rec
from src.database.repository import upsert_trades, upsert_rents


# ── 순수 함수 (config/*.json 실제 값 기준) ──────────────────────────

def test_manual_catalyst_score_reads_config():
    # config/catalysts.json: 11680(강남) 재건축 호재 score=75
    assert rec.manual_catalyst_score("11680") == 75.0


def test_manual_catalyst_score_unregistered_region_is_zero():
    assert rec.manual_catalyst_score("00000") == 0.0


def test_region_tier_score_top_tier():
    # config/region_tiers.json: 11680은 1_최상급지 = 100점
    assert rec.region_tier_score("11680") == 100.0
    assert rec.region_tier_label("11680") == "1_최상급지"


def test_region_tier_score_unregistered_uses_default():
    assert rec.region_tier_score("00000") == 30.0


def test_manual_catalyst_text_summarizes_registered_catalysts():
    text = rec.manual_catalyst_text("11680")
    assert "재건축" in text


def test_manual_catalyst_text_empty_for_unregistered_region():
    assert rec.manual_catalyst_text("00000") == ""


# ── 추천 함수 DB fixture 헬퍼 ────────────────────────────────────────

def _trade(days_ago, region="11680", apt="래미안A", amount=100000, ppp=6000,
           area=84.9, build_year=2015):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deal_amount": amount, "price_per_pyeong": ppp,
            "build_year": build_year}


def _rent(days_ago, region="11680", apt="래미안A", deposit=60000, monthly_rent=0,
          area=84.9):
    d = (pd.Timestamp.today() - pd.Timedelta(days=days_ago)).date()
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "deposit": deposit, "monthly_rent": monthly_rent}


def _seed_gap_scenario():
    # 매매 10억, 전세 7억 -> 갭 3억. 충분한 유동성(5건 이상)으로 필터 통과.
    trades = [_trade(d, amount=100000, ppp=6000) for d in range(1, 6)]
    rents = [_rent(d, deposit=70000) for d in range(1, 6)]
    upsert_trades(trades)
    upsert_rents(rents)


def test_recommend_gap_investment_filters_by_seed():
    _seed_gap_scenario()
    # 갭(3억)보다 작은 시드는 매물이 안 나와야 함
    too_small = rec.recommend_gap_investment(seed_man=10000, months=12,
                                              min_trade_deals=5, min_rent_deals=5)
    assert too_small.empty

    enough = rec.recommend_gap_investment(seed_man=40000, months=12,
                                           min_trade_deals=5, min_rent_deals=5)
    assert len(enough) == 1
    row = enough.iloc[0]
    assert row["gap"] == 30000
    assert row["required_equity"] == 30000
    assert "score" in enough.columns


def test_recommend_gap_investment_empty_when_no_data():
    assert rec.recommend_gap_investment(seed_man=50000).empty


def test_recommend_rental_yield_computes_required_equity_and_sorts_desc():
    trades = [_trade(d, amount=40000, ppp=6000) for d in range(1, 6)]
    rents = [_rent(d, deposit=5000, monthly_rent=100) for d in range(1, 6)]
    upsert_trades(trades)
    upsert_rents(rents)

    out = rec.recommend_rental_yield(seed_man=40000, months=12,
                                      min_trade_deals=5, min_rent_deals=5,
                                      use_loan=False)
    assert len(out) == 1
    row = out.iloc[0]
    # use_loan=False → required_equity = trade - deposit = 40000-5000 = 35000
    assert row["required_equity"] == 35000
    assert row["annual_yield_%"] == round(100 * 12 / 35000 * 100, 2)


def test_recommend_buy_outright_applies_ltv_loan():
    trades = [_trade(d, region="11680", amount=100000, ppp=6000) for d in range(1, 6)]
    upsert_trades(trades)

    out = rec.recommend_buy_outright(seed_man=60000, months=12, min_trade_deals=5,
                                      ownership="무주택", use_loan=True)
    assert len(out) == 1
    row = out.iloc[0]
    # 규제지역(11680) 무주택 LTV 50% → 대출 5억, 필요자기자본 5억
    assert row["loan_capacity"] == 50000
    assert row["required_equity"] == 50000


def test_recommend_investment_focus_returns_scored_candidates():
    trades = [_trade(d, region="11680", amount=100000, ppp=6000, build_year=2023)
              for d in range(1, 8)]
    upsert_trades(trades)

    out = rec.recommend_investment_focus(seed_man=100000, months=12,
                                          min_trade_deals=5, min_growth_deals=1)
    assert not out.empty
    for col in ["ltv_%", "loan_capacity", "required_equity", "leverage",
                "expected_roi_%", "score"]:
        assert col in out.columns
    # 점수 내림차순 정렬 확인
    assert list(out["score"]) == sorted(out["score"], reverse=True)
    # 규제지역(11680) 무주택 LTV 50% → 레버리지 2배
    assert out.iloc[0]["leverage"] == 2.0


def test_recommend_investment_focus_empty_when_no_data():
    assert rec.recommend_investment_focus(seed_man=50000).empty


def test_recommend_investment_focus_catalyst_weight_boosts_region_score():
    # 11680(호재 등록 O, catalyst=75) vs 41360(호재 미등록 -> 0) 비교.
    # market_score는 거래량 부족(min_deals=20 미달)으로 양쪽 다 중립 50 → 차이는 오직 호재 가산분.
    trades = (
        [_trade(d, region="11680", apt="A", amount=100000, ppp=6000) for d in range(1, 6)]
        + [_trade(d, region="41360", apt="B", amount=100000, ppp=6000) for d in range(1, 6)]
    )
    upsert_trades(trades)

    with_catalyst = rec.recommend_investment_focus(
        seed_man=100000, months=12, min_trade_deals=5, min_growth_deals=1,
        catalyst_weight=1.0, tier_weight=0.0, prestige_weight=1.0,
    )
    no_catalyst = rec.recommend_investment_focus(
        seed_man=100000, months=12, min_trade_deals=5, min_growth_deals=1,
        catalyst_weight=0.0, tier_weight=0.0, prestige_weight=1.0,
    )
    gangnam_with = with_catalyst.set_index("region_code").loc["11680", "region_score"]
    gangnam_without = no_catalyst.set_index("region_code").loc["11680", "region_score"]
    assert gangnam_with > gangnam_without
