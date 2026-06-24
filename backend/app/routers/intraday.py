"""
routers/intraday.py — /api/intraday/{ticker} endpoint for sub-daily OHLC data.

Fetches live from Yahoo Finance (not stored in DB) because:
  - Intraday data changes constantly
  - yfinance limits history: 1h → 730 days, 1h resampled to 4h
  - Storing tick data would bloat the database significantly

Supported intervals:
  - 1h  : 1-hour bars, up to 730 days history
  - 4h  : 4-hour bars (resampled from 1h data)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Literal

import pandas as pd
import numpy as np
import yfinance as yf
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

from app.auth import get_current_user
from app.models import Asset
from app.database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/intraday", tags=["intraday"])


def fetch_intraday(ticker: str, interval: str) -> pd.DataFrame:
    """
    Fetch intraday OHLCV bars from Yahoo Finance.

    For 4h interval, downloads 1h data and resamples using OHLC aggregation.
    Returns a clean DataFrame with columns: datetime, open, high, low, close, volume.
    """
    yf_interval = "1h" if interval == "4h" else "1h"
    period = "60d" if interval == "1h" else "60d"

    raw = yf.download(
        ticker,
        period=period,
        interval=yf_interval,
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        raise ValueError(f"No intraday data available for '{ticker}'")

    # Flatten MultiIndex columns
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)

    raw = raw.rename(columns={
        "Open": "open", "High": "high",
        "Low":  "low",  "Close": "close", "Volume": "volume",
    })
    raw = raw[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])

    # Resample 1h → 4h if needed
    if interval == "4h":
        raw = raw.resample("4h").agg({
            "open":   "first",
            "high":   "max",
            "low":    "min",
            "close":  "last",
            "volume": "sum",
        }).dropna(subset=["close"])

    raw["datetime"] = raw.index.strftime("%Y-%m-%dT%H:%M:%S")
    raw["volume"]   = raw["volume"].fillna(0).astype(int)

    # Moving averages
    raw["ma_20"] = raw["close"].rolling(20).mean()
    raw["ma_50"] = raw["close"].rolling(50).mean()

    return raw.reset_index(drop=True)


def compute_intraday_trend(df: pd.DataFrame) -> dict:
    """Compute OLS trend slope, R², and direction on intraday close prices."""
    close = df["close"].values
    t     = np.arange(len(close), dtype=float)
    try:
        result    = OLS(close, add_constant(t)).fit()
        slope     = float(result.params[1])
        r_squared = float(result.rsquared)
    except Exception:
        slope, r_squared = 0.0, 0.0

    if r_squared < 0.30:
        direction = "sideways"
    elif slope > 0:
        direction = "up"
    else:
        direction = "down"

    return {
        "trend_slope":     round(slope, 10),
        "trend_direction": direction,
        "r_squared":       round(r_squared, 4),
    }


@router.get(
    "/{ticker}",
    summary="Intraday OHLC bars — 1H or 4H interval (live fetch from Yahoo Finance)",
)
def get_intraday(
    ticker:   str,
    interval: Literal["1h", "4h"] = Query("1h", description="Bar interval: '1h' or '4h'"),
    db:       Session = Depends(get_db),
    _user:    str     = Depends(get_current_user),
):
    """
    Return sub-daily OHLC bars with MA-20, MA-50, and OLS trend metrics.

    Data is fetched live from Yahoo Finance — not stored in the database.
    History: up to 60 days for both 1h and 4h intervals.
    """
    # Verify the ticker exists in our asset catalogue
    asset = db.query(Asset).filter(Asset.ticker == ticker.upper()).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in catalogue")

    try:
        df = fetch_intraday(ticker.upper(), interval)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch intraday data: {e}")

    trend = compute_intraday_trend(df)

    bars = [
        {
            "datetime": row["datetime"],
            "open":     round(float(row["open"]),   6),
            "high":     round(float(row["high"]),   6),
            "low":      round(float(row["low"]),    6),
            "close":    round(float(row["close"]),  6),
            "volume":   int(row["volume"]),
            "ma_20":    round(float(row["ma_20"]), 6) if pd.notna(row["ma_20"]) else None,
            "ma_50":    round(float(row["ma_50"]), 6) if pd.notna(row["ma_50"]) else None,
        }
        for _, row in df.iterrows()
    ]

    return {
        "ticker":          asset.ticker,
        "name":            asset.name,
        "interval":        interval,
        "bar_count":       len(bars),
        "bars":            bars,
        **trend,
    }
