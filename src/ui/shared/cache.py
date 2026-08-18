"""Streamlit 캐시(@st.cache_data) 래퍼 함수들.

src/ui/shared.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from src.database.repository import fetch_trades_df
from src.analysis.recommend import (
    recommend_gap_investment, recommend_rental_yield, recommend_buy_outright,
    recommend_investment_focus, region_sentiment_summary,
)
from src.analysis.forecast import forecast_monthly_price
from config.settings import (
    ROOT as APP_ROOT, DEFAULT_TIER_WEIGHT, DEFAULT_PRESTIGE_WEIGHT,
)


@st.cache_data(ttl=600)
def _load_region_coords() -> dict:
    import json
    p = APP_ROOT / "config" / "region_coords.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


@st.cache_data(ttl=600, show_spinner="📈 가격 예측 중...")
def _cached_forecast(region_code: str, months_data: int, periods: int) -> pd.DataFrame:
    from datetime import date, timedelta
    df = fetch_trades_df(region_code=region_code,
                         date_from=date.today() - timedelta(days=30 * months_data))
    return forecast_monthly_price(df, periods=periods)


# ─── 추천 함수 캐싱 래퍼 (10분 TTL) ───
# 동일 입력으로 호출 시 DB·계산 생략하여 즉시 반환
@st.cache_data(ttl=600, show_spinner="🔍 추천 계산 중...")
def _cached_gap(seed_man: int, months: int, min_deals: int,
                ownership: str, first_time: bool,
                dsr_cap_man: float | None = None) -> pd.DataFrame:
    return recommend_gap_investment(
        seed_man, months=months,
        min_trade_deals=min_deals, min_rent_deals=min_deals,
        ownership=ownership, first_time_buyer=first_time,
        dsr_cap_man=dsr_cap_man,
    )


@st.cache_data(ttl=600, show_spinner="🔍 추천 계산 중...")
def _cached_yield(seed_man: int, months: int, min_deals: int,
                  ownership: str, first_time: bool, use_loan: bool,
                  dsr_cap_man: float | None = None) -> pd.DataFrame:
    return recommend_rental_yield(
        seed_man, months=months,
        min_trade_deals=min_deals, min_rent_deals=min_deals,
        ownership=ownership, first_time_buyer=first_time, use_loan=use_loan,
        dsr_cap_man=dsr_cap_man,
    )


@st.cache_data(ttl=600, show_spinner="🔍 추천 계산 중...")
def _cached_outright(seed_man: int, months: int, min_deals: int,
                     ownership: str, first_time: bool, use_loan: bool,
                     dsr_cap_man: float | None = None) -> pd.DataFrame:
    return recommend_buy_outright(
        seed_man, months=months, min_trade_deals=min_deals,
        ownership=ownership, first_time_buyer=first_time, use_loan=use_loan,
        dsr_cap_man=dsr_cap_man,
    )


@st.cache_data(ttl=600, show_spinner="🚀 호재·모멘텀 분석 중...")
def _cached_investment(seed_man: int, months: int, min_deals: int,
                        ownership: str, first_time: bool, use_loan: bool,
                        catalyst_weight: float,
                        tier_weight: float = DEFAULT_TIER_WEIGHT,
                        prestige_weight: float = DEFAULT_PRESTIGE_WEIGHT,
                        dsr_cap_man: float | None = None) -> pd.DataFrame:
    return recommend_investment_focus(
        seed_man, months=months, min_trade_deals=min_deals,
        ownership=ownership, first_time_buyer=first_time, use_loan=use_loan,
        catalyst_weight=catalyst_weight, tier_weight=tier_weight,
        prestige_weight=prestige_weight,
        dsr_cap_man=dsr_cap_man,
    )


@st.cache_data(ttl=600, show_spinner="📊 지역별 매수심리 집계 중...")
def _cached_region_sentiment() -> pd.DataFrame:
    return region_sentiment_summary()


@st.cache_data(ttl=1800, show_spinner="📋 거래 내역 로드 중...")
def _cached_all_trades(months: int) -> pd.DataFrame:
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=30 * months)
    return fetch_trades_df(date_from=cutoff)


@st.cache_data(ttl=600, show_spinner="📍 지역 모멘텀 계산 중...")
def _cached_region_momentum(months: int) -> pd.DataFrame:
    from src.analysis.region_momentum import region_momentum_ranking
    return region_momentum_ranking(months=months)


@st.cache_data(ttl=600, show_spinner="🌡️ 매크로 타이밍 진단 중...")
def _cached_market_timing() -> dict:
    from src.analysis.market_timing import market_timing_signal
    return market_timing_signal()
