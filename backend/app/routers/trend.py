"""
routers/trend.py — /api/trend endpoints for OHLC + moving average charts.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import pandas as pd

from app.auth import get_current_user
from app.database import get_db
from app.models import Asset, MarketData
from app.schemas import TrendResponse
from app.analysis.statistics import compute_trend

router = APIRouter(prefix="/api/trend", tags=["trend"])


@router.get(
    "/{ticker}",
    response_model=TrendResponse,
    summary="OHLC bars + moving averages + OLS trend for a single asset",
)
def get_trend(
    ticker:     str,
    start_date: Optional[date] = Query(None, description="Filter bars from this date (inclusive)"),
    end_date:   Optional[date] = Query(None, description="Filter bars up to this date (inclusive)"),
    db:         Session        = Depends(get_db),
    _user:      str            = Depends(get_current_user),
):
    """
    Return daily OHLC bars enriched with MA-20, MA-50, and an OLS trend fit.

    The optional `start_date` / `end_date` query params let the frontend
    zoom into a specific time window without re-fetching everything.
    """
    asset = db.query(Asset).filter(Asset.ticker == ticker.upper()).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    query = (
        db.query(MarketData)
        .filter(MarketData.asset_id == asset.id)
        .order_by(MarketData.date)
    )
    if start_date:
        query = query.filter(MarketData.date >= start_date)
    if end_date:
        query = query.filter(MarketData.date <= end_date)

    rows = query.all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for '{ticker}' in the requested range")

    df = pd.DataFrame([{
        "date":   r.date,
        "open":   r.open,
        "high":   r.high,
        "low":    r.low,
        "close":  r.close,
        "volume": r.volume,
    } for r in rows])

    return compute_trend(df, asset.ticker, asset.name)
