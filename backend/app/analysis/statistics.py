"""
analysis/statistics.py — Pure-function statistical computation layer.

All functions accept a pandas DataFrame with columns:
    date, open, high, low, close, volume

and return plain Python dicts / lists that the routers serialise into
Pydantic response models.  No SQLAlchemy or FastAPI imports here —
this keeps the analysis logic independently testable.
"""

import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant


# ── KPI computation ────────────────────────────────────────────────────────────

def compute_kpi(df: pd.DataFrame, ticker: str, name: str) -> dict:
    """
    Compute dashboard KPI card metrics from a sorted daily OHLCV DataFrame.

    Args:
        df:     DataFrame sorted ascending by date.
        ticker: Instrument symbol (for labelling).
        name:   Human-readable instrument name.

    Returns:
        Dict matching the KPIResponse schema.
    """
    if df.empty or len(df) < 2:
        raise ValueError(f"Insufficient data for {ticker}")

    close = df["close"]
    latest = float(close.iloc[-1])

    def safe_pct_change(n_days: int) -> float:
        """Return n-day return in percent, or 0.0 if not enough history."""
        if len(close) <= n_days:
            return 0.0
        prev = float(close.iloc[-(n_days + 1)])
        return round((latest - prev) / prev * 100, 4) if prev != 0 else 0.0

    # Annualised volatility = std(daily log-returns) * sqrt(252)
    log_returns = np.log(close / close.shift(1)).dropna()
    vol_30d = float(log_returns.tail(30).std() * np.sqrt(252) * 100)

    window_52w = min(252, len(df))

    return {
        "ticker":         ticker,
        "name":           name,
        "latest_close":   round(latest, 6),
        "change_pct_1d":  safe_pct_change(1),
        "change_pct_7d":  safe_pct_change(7),
        "change_pct_30d": safe_pct_change(30),
        "volatility_30d": round(vol_30d, 4),
        "avg_volume_30d": round(float(df["volume"].tail(30).mean()), 2),
        "high_52w":       round(float(df["high"].tail(window_52w).max()), 6),
        "low_52w":        round(float(df["low"].tail(window_52w).min()), 6),
        "data_start":     df["date"].iloc[0],
        "data_end":       df["date"].iloc[-1],
    }


# ── Trend analysis ─────────────────────────────────────────────────────────────

def compute_trend(df: pd.DataFrame, ticker: str, name: str) -> dict:
    """
    Fit an OLS linear trend to closing prices and add moving averages.

    The slope is expressed as price-per-day.  Direction is classified as:
        up        slope > 0  and  R² ≥ 0.30
        down      slope < 0  and  R² ≥ 0.30
        sideways  R² < 0.30 (noisy, no clear trend)

    Args:
        df:     Sorted daily OHLCV DataFrame.
        ticker: Symbol label.
        name:   Human-readable name.

    Returns:
        Dict matching TrendResponse schema.
    """
    df = df.copy().reset_index(drop=True)
    close = df["close"]

    # Moving averages (NaN for initial window)
    df["ma_20"] = close.rolling(20).mean()
    df["ma_50"] = close.rolling(50).mean()

    # OLS: close ~ intercept + t
    t = np.arange(len(close), dtype=float)
    ols_result = OLS(close.values, add_constant(t)).fit()
    slope    = float(ols_result.params[1])
    r_sq     = float(ols_result.rsquared)

    if r_sq < 0.30:
        direction = "sideways"
    elif slope > 0:
        direction = "up"
    else:
        direction = "down"

    bars = []
    for _, row in df.iterrows():
        bars.append({
            "date":   row["date"],
            "open":   round(row["open"],   6),
            "high":   round(row["high"],   6),
            "low":    round(row["low"],    6),
            "close":  round(row["close"],  6),
            "volume": int(row["volume"]),
            "ma_20":  round(row["ma_20"], 6) if pd.notna(row["ma_20"]) else None,
            "ma_50":  round(row["ma_50"], 6) if pd.notna(row["ma_50"]) else None,
        })

    return {
        "ticker":          ticker,
        "name":            name,
        "bars":            bars,
        "trend_slope":     round(slope, 8),
        "trend_direction": direction,
        "r_squared":       round(r_sq, 4),
    }


# ── Correlation matrix ─────────────────────────────────────────────────────────

def compute_correlation(frames: dict[str, pd.DataFrame]) -> dict:
    """
    Compute a Pearson correlation matrix of daily log-returns across assets.

    Args:
        frames: Mapping of ticker → sorted OHLCV DataFrame.

    Returns:
        Dict with keys: tickers, matrix, start_date, end_date.
    """
    if not frames:
        raise ValueError("No data provided for correlation computation")

    # Align all series on the same date index
    series = {
        ticker: np.log(df.set_index("date")["close"] / df.set_index("date")["close"].shift(1))
        for ticker, df in frames.items()
    }
    combined = pd.DataFrame(series).dropna()

    if combined.empty:
        raise ValueError("No overlapping dates found across selected assets")

    corr_matrix = combined.corr(method="pearson")
    tickers = list(corr_matrix.columns)

    return {
        "tickers":    tickers,
        "matrix":     [[round(float(v), 4) for v in row] for row in corr_matrix.values],
        "start_date": combined.index.min(),
        "end_date":   combined.index.max(),
    }
