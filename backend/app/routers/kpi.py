"""
routers/kpi.py — /api/kpi endpoints for dashboard summary cards.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Asset, MarketData
from app.schemas import AssetOut, KPIResponse
from app.analysis.statistics import compute_kpi

import pandas as pd

router = APIRouter(prefix="/api/kpi", tags=["kpi"])


def _load_df(db: Session, ticker: str) -> tuple[Asset, pd.DataFrame]:
    """Fetch asset + all its market data bars as a sorted DataFrame."""
    asset = db.query(Asset).filter(Asset.ticker == ticker).first()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

    rows = (
        db.query(MarketData)
        .filter(MarketData.asset_id == asset.id)
        .order_by(MarketData.date)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No market data for '{ticker}'")

    df = pd.DataFrame([{
        "date":   r.date,
        "open":   r.open,
        "high":   r.high,
        "low":    r.low,
        "close":  r.close,
        "volume": r.volume,
    } for r in rows])

    return asset, df


@router.get(
    "/{ticker}",
    response_model=KPIResponse,
    summary="KPI summary cards for a single asset",
)
def get_kpi(
    ticker: str,
    db:     Session = Depends(get_db),
    _user:  str     = Depends(get_current_user),
):
    """Return KPI metrics (returns, volatility, 52w range) for the requested ticker."""
    asset, df = _load_df(db, ticker.upper())
    return compute_kpi(df, asset.ticker, asset.name)


@router.get(
    "/",
    response_model=list[KPIResponse],
    summary="KPI summary cards for all assets",
)
def get_all_kpis(
    db:    Session = Depends(get_db),
    _user: str     = Depends(get_current_user),
):
    """Return KPI metrics for every asset in the database."""
    assets = db.query(Asset).all()
    results = []
    for asset in assets:
        try:
            _, df = _load_df(db, asset.ticker)
            results.append(compute_kpi(df, asset.ticker, asset.name))
        except Exception:
            continue   # Skip assets with insufficient data silently
    return results


@router.get(
    "/assets/list",
    response_model=list[AssetOut],
    summary="List all available assets",
)
def list_assets(
    db:    Session = Depends(get_db),
    _user: str     = Depends(get_current_user),
):
    """Return the catalogue of all seeded instruments."""
    return db.query(Asset).order_by(Asset.category, Asset.ticker).all()
