"""
routers/forecast.py — /api/forecast endpoint for the prediction panel.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import pandas as pd

from app.auth import get_current_user
from app.database import get_db
from app.models import Asset, MarketData
from app.schemas import ForecastResponse
from app.analysis.forecaster import compute_forecast

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


@router.get(
    "/{ticker}",
    response_model=ForecastResponse,
    summary="Price forecast with confidence intervals",
)
def get_forecast(
    ticker:       str,
    horizon_days: int = Query(30, ge=5, le=180, description="Number of business days to forecast"),
    db:           Session = Depends(get_db),
    _user:        str     = Depends(get_current_user),
):
    """
    Generate a price forecast using Prophet (or linear regression fallback).

    The response includes:
    - `history`  — in-sample fitted values with prediction intervals
    - `forecast` — out-of-sample predictions for the next `horizon_days` business days
    - `mae` / `rmse` — accuracy metrics evaluated on a 30-day hold-out set
    - `model_used` — indicates which model was selected
    """
    asset = db.query(Asset).filter(Asset.ticker == ticker.upper()).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    rows = (
        db.query(MarketData)
        .filter(MarketData.asset_id == asset.id)
        .order_by(MarketData.date)
        .all()
    )
    if len(rows) < 10:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient data for '{ticker}': need at least 10 bars, found {len(rows)}.",
        )

    df = pd.DataFrame([{
        "date":   r.date,
        "open":   r.open,
        "high":   r.high,
        "low":    r.low,
        "close":  r.close,
        "volume": r.volume,
    } for r in rows])

    return compute_forecast(df, asset.ticker, asset.name, horizon_days=horizon_days)
