"""
analysis/forecaster.py — Time-series forecasting with Prophet and linear regression fallback.

Strategy:
  1. Try Prophet (best accuracy, handles seasonality and holidays).
  2. Fall back to scikit-learn LinearRegression if Prophet is unavailable
     or if the series is too short for Prophet (< 60 data points).

Both paths return the same dict structure so the router is model-agnostic.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


# ── Internal helpers ───────────────────────────────────────────────────────────

def _eval_metrics(actual: np.ndarray, predicted: np.ndarray) -> tuple[float, float]:
    """Return (MAE, RMSE) rounded to 6 decimal places."""
    mae  = float(mean_absolute_error(actual, predicted))
    rmse = float(np.sqrt(mean_squared_error(actual, predicted)))
    return round(mae, 6), round(rmse, 6)


def _forecast_linear(df: pd.DataFrame, horizon_days: int) -> dict:
    """
    Fit a simple OLS linear trend (time index → close price) and project forward.

    Prediction intervals are estimated as ±1.28 × residual std (≈80% coverage
    under a Gaussian residual assumption).

    Args:
        df:           Sorted daily OHLCV DataFrame.
        horizon_days: Number of calendar days to forecast ahead.

    Returns:
        Dict matching ForecastResponse schema.
    """
    df = df.copy().reset_index(drop=True)
    n = len(df)

    # 30-day holdout for metric evaluation
    holdout_n = min(30, n // 5)
    train_df  = df.iloc[: n - holdout_n]
    test_df   = df.iloc[n - holdout_n :]

    t_train = np.arange(len(train_df)).reshape(-1, 1)
    t_test  = np.arange(len(train_df), n).reshape(-1, 1)
    t_full  = np.arange(n).reshape(-1, 1)

    model = LinearRegression()
    model.fit(t_train, train_df["close"].values)

    # Residual std on training set for interval width
    train_pred = model.predict(t_train).ravel()
    residual_std = float(np.std(train_df["close"].values - train_pred))
    interval_half = 1.28 * residual_std   # 80% interval

    # In-sample history (fitted values on full training period)
    full_pred = model.predict(t_full).ravel()
    history = [
        {
            "date":      row["date"],
            "predicted": round(float(full_pred[i]), 6),
            "lower":     round(float(full_pred[i]) - interval_half, 6),
            "upper":     round(float(full_pred[i]) + interval_half, 6),
        }
        for i, (_, row) in enumerate(df.iterrows())
    ]

    # Holdout metrics
    test_pred = model.predict(t_test).ravel()
    mae, rmse = _eval_metrics(test_df["close"].values, test_pred)

    # Future forecast
    last_date   = pd.Timestamp(df["date"].iloc[-1])
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon_days, freq="B")
    t_future    = np.arange(n, n + len(future_dates)).reshape(-1, 1)
    future_pred = model.predict(t_future).ravel()

    forecast = [
        {
            "date":      d.date(),
            "predicted": round(float(p), 6),
            "lower":     round(float(p) - interval_half, 6),
            "upper":     round(float(p) + interval_half, 6),
        }
        for d, p in zip(future_dates, future_pred)
    ]

    return {
        "model_used":   "linear_regression",
        "history":      history,
        "forecast":     forecast,
        "mae":          mae,
        "rmse":         rmse,
        "horizon_days": horizon_days,
    }


def _forecast_prophet(df: pd.DataFrame, horizon_days: int) -> dict:
    """
    Fit a Facebook Prophet model and return in-sample + out-of-sample forecasts.

    Prophet handles trend changepoints, weekly seasonality, and missing dates
    automatically, making it significantly more accurate than linear regression
    on real market data.

    Args:
        df:           Sorted daily OHLCV DataFrame.
        horizon_days: Number of trading days to forecast.

    Returns:
        Dict matching ForecastResponse schema (model_used = "prophet").
    """
    from prophet import Prophet  # Lazy import — heavy dependency

    # Prophet expects columns named "ds" (datestamp) and "y" (target)
    prophet_df = pd.DataFrame({
        "ds": pd.to_datetime(df["date"]),
        "y":  df["close"].values,
    })

    # 30-day holdout for metric evaluation
    holdout_n  = min(30, len(prophet_df) // 5)
    train_data = prophet_df.iloc[: len(prophet_df) - holdout_n]
    test_data  = prophet_df.iloc[len(prophet_df) - holdout_n :]

    model = Prophet(
        interval_width=0.80,
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        changepoint_prior_scale=0.05,   # Regularise trend changepoints
    )
    model.fit(train_data)

    # Predict over the full historical range for in-sample history
    full_future   = model.make_future_dataframe(periods=holdout_n + horizon_days, freq="B")
    full_forecast = model.predict(full_future)

    history_fc = full_forecast[full_forecast["ds"] <= prophet_df["ds"].iloc[-1]]
    history = [
        {
            "date":      row["ds"].date(),
            "predicted": round(float(row["yhat"]),       6),
            "lower":     round(float(row["yhat_lower"]), 6),
            "upper":     round(float(row["yhat_upper"]), 6),
        }
        for _, row in history_fc.iterrows()
    ]

    # Holdout metrics
    holdout_fc  = full_forecast[full_forecast["ds"].isin(test_data["ds"])]
    mae, rmse   = _eval_metrics(test_data["y"].values, holdout_fc["yhat"].values)

    # Future-only rows
    last_hist_date = prophet_df["ds"].iloc[-1]
    future_fc = full_forecast[full_forecast["ds"] > last_hist_date].head(horizon_days)
    forecast = [
        {
            "date":      row["ds"].date(),
            "predicted": round(float(row["yhat"]),       6),
            "lower":     round(float(row["yhat_lower"]), 6),
            "upper":     round(float(row["yhat_upper"]), 6),
        }
        for _, row in future_fc.iterrows()
    ]

    return {
        "model_used":   "prophet",
        "history":      history,
        "forecast":     forecast,
        "mae":          mae,
        "rmse":         rmse,
        "horizon_days": horizon_days,
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def compute_forecast(
    df: pd.DataFrame,
    ticker: str,
    name: str,
    horizon_days: int = 30,
) -> dict:
    """
    Generate a price forecast for the given asset.

    Tries Prophet first; falls back to linear regression if Prophet
    is unavailable or the series is too short (< 60 bars).

    Args:
        df:           Sorted daily OHLCV DataFrame.
        ticker:       Instrument symbol.
        name:         Human-readable name.
        horizon_days: Number of business days to project forward.

    Returns:
        Dict matching ForecastResponse schema.
    """
    if len(df) < 10:
        raise ValueError(f"Need at least 10 data points to forecast {ticker}; got {len(df)}.")

    result = None
    model_tried = "prophet"

    if len(df) >= 60:
        try:
            result = _forecast_prophet(df, horizon_days)
        except Exception:
            # Prophet failed (import error, insufficient data, etc.) — fall back silently
            result = None

    if result is None:
        model_tried = "linear_regression"
        result      = _forecast_linear(df, horizon_days)

    result["ticker"] = ticker
    result["name"]   = name
    return result
