"""
routers/correlation.py — /api/correlation endpoint for the heatmap panel.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import pandas as pd

from app.auth import get_current_user
from app.database import get_db
from app.models import Asset, MarketData
from app.schemas import CorrelationResponse
from app.analysis.statistics import compute_correlation

router = APIRouter(prefix="/api/correlation", tags=["correlation"])


@router.get(
    "/",
    response_model=CorrelationResponse,
    summary="Pearson correlation matrix of daily log-returns across all assets",
)
def get_correlation(
    tickers: Optional[list[str]] = Query(
        None,
        description="Subset of tickers to include. Omit to use all available assets.",
    ),
    db:    Session = Depends(get_db),
    _user: str     = Depends(get_current_user),
):
    """
    Compute and return a pairwise Pearson correlation matrix.

    Correlations are calculated on daily log-returns so the series are
    stationary and scale-invariant (a 1.0 EURUSD move is comparable to
    a 50,000 BTC move).

    Pass `?tickers=EURUSD=X&tickers=BTC-USD` to restrict the matrix to
    a specific subset of instruments.
    """
    # Resolve asset list
    asset_query = db.query(Asset)
    if tickers:
        normalised = [t.upper() for t in tickers]
        asset_query = asset_query.filter(Asset.ticker.in_(normalised))

    assets = asset_query.all()
    if len(assets) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least two assets are required for a correlation matrix.",
        )

    # Load data for each asset
    frames: dict[str, pd.DataFrame] = {}
    for asset in assets:
        rows = (
            db.query(MarketData)
            .filter(MarketData.asset_id == asset.id)
            .order_by(MarketData.date)
            .all()
        )
        if len(rows) < 30:
            continue   # Skip assets with too little history
        frames[asset.ticker] = pd.DataFrame([{
            "date":  r.date,
            "close": r.close,
        } for r in rows])

    if len(frames) < 2:
        raise HTTPException(
            status_code=400,
            detail="Not enough assets have sufficient history for correlation.",
        )

    return compute_correlation(frames)
