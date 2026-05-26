"""statsmodels Holt-Winters 기반 가격 시계열 예측

Prophet은 Windows 한글 경로에서 CmdStan 설치 어려워 대체.
간단한 지수평활 + 추세 외삽 + 잔차 표준편차 기반 신뢰구간.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

log = get_logger(__name__)


def forecast_monthly_price(df_trade: pd.DataFrame,
                            value_col: str = "deal_amount",
                            periods: int = 6,
                            min_points: int = 6) -> pd.DataFrame:
    """월별 중위가 시계열에 Holt-Winters 적용해 향후 N개월 예측.

    Returns DataFrame: ds(year-month), yhat(예상가-만원),
                       yhat_lower, yhat_upper, is_forecast(bool)
    """
    if df_trade.empty:
        return pd.DataFrame()
    df = df_trade.copy()
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    monthly = (
        df.groupby(df["deal_date"].dt.to_period("M"))[value_col]
        .median()
        .reset_index()
    )
    monthly["ds"] = monthly["deal_date"].dt.to_timestamp()
    monthly = monthly[["ds", value_col]].rename(columns={value_col: "y"})
    monthly = monthly.sort_values("ds").reset_index(drop=True)

    if len(monthly) < min_points:
        log.warning("forecast: 데이터 포인트 %d 개 < %d, 예측 생략", len(monthly), min_points)
        return pd.DataFrame()

    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(
            monthly["y"].values,
            trend="add",
            seasonal=None,
            initialization_method="estimated",
        )
        fit = model.fit(optimized=True)
        forecast_vals = fit.forecast(periods)
        fitted_vals = fit.fittedvalues
    except Exception as e:
        log.exception("Holt-Winters 실패, 단순 선형 추세로 폴백: %s", e)
        # 폴백: 선형 추세
        x = np.arange(len(monthly))
        y = monthly["y"].values
        slope, intercept = np.polyfit(x, y, 1)
        fitted_vals = slope * x + intercept
        forecast_vals = slope * np.arange(len(monthly), len(monthly) + periods) + intercept

    # 잔차 표준편차로 80% 신뢰구간 추정 (z=1.28)
    residuals = monthly["y"].values - np.array(fitted_vals)
    sigma = float(np.std(residuals)) if len(residuals) > 1 else 0.0
    band = 1.28 * sigma

    # 실측 부분
    hist = pd.DataFrame({
        "ds": monthly["ds"],
        "yhat": np.round(monthly["y"].values, 0),
        "yhat_lower": np.round(monthly["y"].values - band, 0),
        "yhat_upper": np.round(monthly["y"].values + band, 0),
        "is_forecast": False,
    })

    # 예측 부분
    last = monthly["ds"].iloc[-1]
    future_ds = pd.date_range(start=last + pd.DateOffset(months=1),
                              periods=periods, freq="MS")
    fc = pd.DataFrame({
        "ds": future_ds,
        "yhat": np.round(forecast_vals, 0),
        "yhat_lower": np.round(forecast_vals - band, 0),
        "yhat_upper": np.round(forecast_vals + band, 0),
        "is_forecast": True,
    })

    return pd.concat([hist, fc], ignore_index=True)


def forecast_region(region_code: str | None = None,
                     apt_name: str | None = None,
                     periods: int = 6,
                     months: int = 24) -> pd.DataFrame:
    """지역/단지 단위 가격 예측."""
    from datetime import date, timedelta
    from src.database.repository import fetch_trades_df

    date_from = date.today() - timedelta(days=30 * months)
    df = fetch_trades_df(region_code=region_code, date_from=date_from, apt_name=apt_name)
    return forecast_monthly_price(df, periods=periods)
