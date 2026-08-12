"""src/analysis/forecast.py — Holt-Winters 월별 가격 예측 검증."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.analysis.forecast import forecast_monthly_price, forecast_region
from src.database.repository import upsert_trades


def _monthly_trade_df(n_months=12, start_price=100000, growth=1000):
    rows = []
    for i in range(n_months):
        month = (i % 12) + 1
        year = 2024 + (i // 12)
        rows.append({
            "deal_date": date(year, month, 15),
            "deal_amount": start_price + growth * i,
        })
    return pd.DataFrame(rows)


def test_forecast_monthly_price_returns_history_plus_periods():
    df = _monthly_trade_df(n_months=12)
    out = forecast_monthly_price(df, periods=6, min_points=6)
    assert len(out) == 12 + 6
    assert out["is_forecast"].sum() == 6
    assert (~out["is_forecast"]).sum() == 12


def test_forecast_monthly_price_below_min_points_returns_empty():
    df = _monthly_trade_df(n_months=3)
    assert forecast_monthly_price(df, min_points=6).empty


def test_forecast_monthly_price_empty_input():
    assert forecast_monthly_price(pd.DataFrame()).empty


def test_forecast_monthly_price_upward_trend_forecasts_higher():
    df = _monthly_trade_df(n_months=12, start_price=100000, growth=2000)
    out = forecast_monthly_price(df, periods=3, min_points=6)
    hist_last = out[~out["is_forecast"]]["yhat"].iloc[-1]
    forecast_first = out[out["is_forecast"]]["yhat"].iloc[0]
    assert forecast_first > hist_last


def test_forecast_region_reads_from_db():
    today = pd.Timestamp.today().normalize()
    rows = []
    for i in range(12):
        d = (today - pd.DateOffset(months=i)).date()
        rows.append({
            "region_code": "11680", "deal_date": d,
            "deal_year": d.year, "deal_month": d.month, "deal_day": d.day,
            "apt_name": "래미안A", "area_m2": 84.9, "deal_amount": 100000 + i * 1000,
        })
    upsert_trades(rows)
    out = forecast_region(region_code="11680", periods=3, months=24)
    assert not out.empty
    assert out["is_forecast"].sum() == 3
