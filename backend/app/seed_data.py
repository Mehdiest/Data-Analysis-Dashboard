"""
seed_data.py — Fetch real OHLCV data from Yahoo Finance and populate the database.

Usage:
    python seed_data.py                   # Use tickers defined in config
    python seed_data.py --tickers EURUSD=X BTC-USD   # Override tickers
    python seed_data.py --reset           # Drop existing data first

The script is idempotent: re-running it only inserts rows not already present,
so it is safe to run on a schedule to keep the database up-to-date.
"""

import argparse
import sys
from datetime import date

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

# Ensure the app package is importable when running from backend/
sys.path.insert(0, ".")

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Asset, MarketData


# ── Asset catalogue ────────────────────────────────────────────────────────────
# Maps Yahoo Finance ticker → (human name, category)
ASSET_CATALOGUE: dict[str, tuple[str, str]] = {
    "EURUSD=X":  ("EUR / USD", "forex"),
    "GBPUSD=X":  ("GBP / USD", "forex"),
    "JPYUSD=X":  ("JPY / USD", "forex"),
    "XAUUSD=X":  ("Gold / USD", "commodity"),
    "BTC-USD":   ("Bitcoin / USD", "crypto"),
    "ETH-USD":   ("Ethereum / USD", "crypto"),
    "GC=F":      ("Gold Futures", "commodity"),
    "CL=F":      ("Crude Oil Futures", "commodity"),
}


def fetch_ohlcv(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """
    Download OHLCV data for one ticker from Yahoo Finance.

    Returns a cleaned DataFrame with columns:
        date (datetime.date), open, high, low, close, volume

    Raises ValueError if yfinance returns an empty result.
    """
    raw = yf.download(
        ticker,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        raise ValueError(f"yfinance returned no data for '{ticker}'")

    # Flatten MultiIndex columns produced when downloading a single ticker
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.droplevel(1)

    raw = raw.rename(columns={
        "Open":   "open",
        "High":   "high",
        "Low":    "low",
        "Close":  "close",
        "Volume": "volume",
    })

    raw = raw[["open", "high", "low", "close", "volume"]].copy()
    raw = raw.dropna(subset=["open", "high", "low", "close"])
    raw.index = pd.to_datetime(raw.index)
    raw["date"] = raw.index.date
    raw["volume"] = raw["volume"].fillna(0).astype(int)

    return raw.reset_index(drop=True)


def upsert_asset(db: Session, ticker: str) -> Asset:
    """Return existing Asset row or create a new one."""
    name, category = ASSET_CATALOGUE.get(ticker, (ticker, "other"))
    asset = db.query(Asset).filter(Asset.ticker == ticker).first()
    if not asset:
        asset = Asset(ticker=ticker, name=name, category=category)
        db.add(asset)
        db.flush()   # Populate asset.id without committing
    return asset


def seed_ticker(db: Session, ticker: str, period: str, interval: str, reset: bool) -> int:
    """
    Fetch and store OHLCV bars for one ticker.

    Returns the number of new rows inserted.
    """
    print(f"  → Fetching {ticker} ...")
    try:
        df = fetch_ohlcv(ticker, period, interval)
    except Exception as exc:
        print(f"    ⚠ Skipped ({exc})")
        return 0

    asset = upsert_asset(db, ticker)

    if reset:
        db.query(MarketData).filter(MarketData.asset_id == asset.id).delete()
        existing_dates: set[date] = set()
    else:
        existing = (
            db.query(MarketData.date)
            .filter(MarketData.asset_id == asset.id)
            .all()
        )
        existing_dates = {row.date for row in existing}

    new_rows = [
        MarketData(
            asset_id=asset.id,
            date=row["date"],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
        )
        for _, row in df.iterrows()
        if row["date"] not in existing_dates
    ]

    db.bulk_save_objects(new_rows)
    print(f"    ✓ {len(new_rows)} new bars inserted (total fetched: {len(df)})")
    return len(new_rows)


def main():
    parser = argparse.ArgumentParser(description="Seed market data into PostgreSQL")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=settings.seed_tickers,
        help="Yahoo Finance ticker symbols to fetch",
    )
    parser.add_argument(
        "--period",
        default=settings.seed_period,
        help="History length (e.g. 1y, 2y, 5y)",
    )
    parser.add_argument(
        "--interval",
        default=settings.seed_interval,
        help="Bar interval (e.g. 1d, 1wk)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing bars for the requested tickers before inserting",
    )
    args = parser.parse_args()

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    total_inserted = 0
    print(f"\nSeeding {len(args.tickers)} ticker(s)  [period={args.period}, interval={args.interval}]\n")

    try:
        for ticker in args.tickers:
            total_inserted += seed_ticker(db, ticker.upper(), args.period, args.interval, args.reset)
        db.commit()
        print(f"\n✅  Done — {total_inserted} total rows inserted.\n")
    except Exception as exc:
        db.rollback()
        print(f"\n❌  Seed failed: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
