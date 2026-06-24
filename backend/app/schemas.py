"""
schemas.py — Pydantic v2 request and response models.

Keeping schemas separate from ORM models ensures the API contract stays
stable even when the database schema evolves.
"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


# ── Auth ───────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Asset ──────────────────────────────────────────────────────────────────────

class AssetOut(BaseModel):
    id:       int
    ticker:   str
    name:     str
    category: str

    model_config = {"from_attributes": True}


# ── KPI ────────────────────────────────────────────────────────────────────────

class KPIResponse(BaseModel):
    """Summary statistics shown in the KPI cards at the top of the dashboard."""

    ticker:            str
    name:              str
    latest_close:      float = Field(description="Most recent closing price")
    change_pct_1d:     float = Field(description="1-day return in percent")
    change_pct_7d:     float = Field(description="7-day return in percent")
    change_pct_30d:    float = Field(description="30-day return in percent")
    volatility_30d:    float = Field(description="Annualised 30-day volatility in percent")
    avg_volume_30d:    float = Field(description="30-day average daily volume")
    high_52w:          float = Field(description="52-week high")
    low_52w:           float = Field(description="52-week low")
    data_start:        date
    data_end:          date


# ── Trend ──────────────────────────────────────────────────────────────────────

class OHLCPoint(BaseModel):
    date:   date
    open:   float
    high:   float
    low:    float
    close:  float
    volume: int
    ma_20:  Optional[float] = None   # 20-day moving average
    ma_50:  Optional[float] = None   # 50-day moving average


class TrendResponse(BaseModel):
    ticker: str
    name:   str
    bars:   list[OHLCPoint]
    trend_slope:     float = Field(description="OLS slope of close price per day")
    trend_direction: str   = Field(description="'up' | 'down' | 'sideways'")
    r_squared:       float = Field(description="Goodness-of-fit for the linear trend")


# ── Correlation ────────────────────────────────────────────────────────────────

class CorrelationResponse(BaseModel):
    """Pairwise Pearson correlation matrix for daily log-returns."""

    tickers: list[str]
    matrix:  list[list[float]]   # [i][j] = corr(tickers[i], tickers[j])
    start_date: date
    end_date:   date


# ── Forecast ───────────────────────────────────────────────────────────────────

class ForecastPoint(BaseModel):
    date:       date
    predicted:  float
    lower:      float   # 80% prediction interval lower bound
    upper:      float   # 80% prediction interval upper bound


class ForecastResponse(BaseModel):
    ticker:     str
    name:       str
    model_used: str      # "prophet" or "linear_regression"
    horizon_days: int
    history:    list[ForecastPoint]   # In-sample fitted values
    forecast:   list[ForecastPoint]   # Out-of-sample predictions
    mae:        float    # Mean absolute error on last 30-day holdout
    rmse:       float
