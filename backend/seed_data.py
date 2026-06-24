"""
seed_data.py — Fetch real OHLCV data from Yahoo Finance and populate the database.

Usage:
    python seed_data.py              # seed all instruments
    python seed_data.py --reset      # wipe and re-seed
    python seed_data.py --tickers GC=F BTC-USD   # specific tickers only
"""

import argparse
import sys
from datetime import date

import pandas as pd
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, ".")

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Asset, MarketData


# ── Complete instrument catalogue ──────────────────────────────────────────────
# Organised by market segment.  ticker → (display name, category, market)
ASSET_CATALOGUE: dict[str, tuple[str, str, str]] = {

    # ── Forex Major Pairs ──────────────────────────────────────────────────────
    "EURUSD=X":  ("EUR / USD",  "forex", "major"),
    "GBPUSD=X":  ("GBP / USD",  "forex", "major"),
    "USDJPY=X":  ("USD / JPY",  "forex", "major"),
    "USDCHF=X":  ("USD / CHF",  "forex", "major"),
    "AUDUSD=X":  ("AUD / USD",  "forex", "major"),
    "USDCAD=X":  ("USD / CAD",  "forex", "major"),
    "NZDUSD=X":  ("NZD / USD",  "forex", "major"),

    # ── Forex Minor Pairs ──────────────────────────────────────────────────────
    "EURGBP=X":  ("EUR / GBP",  "forex", "minor"),
    "EURJPY=X":  ("EUR / JPY",  "forex", "minor"),
    "GBPJPY=X":  ("GBP / JPY",  "forex", "minor"),
    "EURCHF=X":  ("EUR / CHF",  "forex", "minor"),
    "AUDCAD=X":  ("AUD / CAD",  "forex", "minor"),
    "AUDNZD=X":  ("AUD / NZD",  "forex", "minor"),
    "CADJPY=X":  ("CAD / JPY",  "forex", "minor"),
    "CHFJPY=X":  ("CHF / JPY",  "forex", "minor"),
    "GBPAUD=X":  ("GBP / AUD",  "forex", "minor"),
    "GBPCAD=X":  ("GBP / CAD",  "forex", "minor"),

    # ── Metals ────────────────────────────────────────────────────────────────
    "GC=F":      ("Gold Futures",    "commodity", "metals"),
    "SI=F":      ("Silver Futures",  "commodity", "metals"),
    "PL=F":      ("Platinum Futures","commodity", "metals"),
    "HG=F":      ("Copper Futures",  "commodity", "metals"),

    # ── Energy ────────────────────────────────────────────────────────────────
    "CL=F":      ("Crude Oil (WTI)", "commodity", "energy"),
    "BZ=F":      ("Brent Crude Oil", "commodity", "energy"),
    "NG=F":      ("Natural Gas",     "commodity", "energy"),

    # ── Crypto — Major ────────────────────────────────────────────────────────
    "BTC-USD":   ("Bitcoin / USD",   "crypto", "major"),
    "ETH-USD":   ("Ethereum / USD",  "crypto", "major"),
    "BNB-USD":   ("BNB / USD",       "crypto", "major"),
    "SOL-USD":   ("Solana / USD",    "crypto", "major"),
    "XRP-USD":   ("XRP / USD",       "crypto", "major"),

    # ── Crypto — Stablecoins ──────────────────────────────────────────────────
    "USDT-USD":  ("Tether / USD",    "crypto", "stablecoin"),
    "USDC-USD":  ("USD Coin / USD",  "crypto", "stablecoin"),
    "DAI-USD":   ("DAI / USD",       "crypto", "stablecoin"),
}

# Default tickers to seed when no --tickers flag is passed
DEFAULT_TICKERS = list(ASSET_CATALOGUE.keys())


def init_db():
    """Drops old tables and lets SQLAlchemy recreate them with exact schemas."""
    print("Initializing database and synchronization structures...")
    with engine.connect() as conn:
        # Drop bars and old market data to avoid any column conflicts
        conn.execute(text("DROP TABLE IF EXISTS asset_bars CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS market_data CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS assets CASCADE;"))
        conn.commit()
    
    # Recreate tables matching the ORM Models perfectly
    Base.metadata.create_all(bind=engine)


def fetch_ohlcv(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """
    Download OHLCV bars for one ticker from Yahoo Finance.
    Returns a clean DataFrame with columns:
        date (datetime.date), open, high, low, close, volume
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

    # Safe column normalization to handle newer yfinance formats (MultiIndex / Strings)
    flat_cols = []
    for col in raw.columns:
        if isinstance(col, tuple):
            flat_cols.append(str(col).lower())
        else:
            flat_cols.append(str(col).lower())
    raw.columns = flat_cols

    # Map possible naming variations safely
    rename_map = {}
    for c in raw.columns:
        if "open" in c: rename_map[c] = "open"
        elif "high" in c: rename_map[c] = "high"
        elif "low" in c: rename_map[c] = "low"
        elif "close" in c: rename_map[c] = "close"
        elif "volume" in c: rename_map[c] = "volume"
        
    raw = raw.rename(columns=rename_map)
    
    # Ensure all required OHLCV columns exist
    for expected in ["open", "high", "low", "close"]:
        if expected not in raw.columns:
            raise ValueError(f"Missing structural column '{expected}' for {ticker}")
            
    if "volume" not in raw.columns:
        raw["volume"] = 0

    # Build fresh clean dataframe
    processed = pd.DataFrame(index=raw.index)
    processed["open"] = raw["open"].astype(float)
    processed["high"] = raw["high"].astype(float)
    processed["low"] = raw["low"].astype(float)
    processed["close"] = raw["close"].astype(float)
    processed["volume"] = raw["volume"].fillna(0).astype(int)
    
    # Extract structural dates safely from index
    processed["date"] = pd.to_datetime(processed.index).date
    processed = processed.dropna(subset=["open", "high", "low", "close"])

    return processed.reset_index(drop=True)


def upsert_asset(db: Session, ticker: str) -> Asset:
    """Return existing Asset row or insert a new one."""
    info = ASSET_CATALOGUE.get(ticker, (ticker, "other", "other"))
    name, category, market = info

    asset = db.query(Asset).filter(Asset.ticker == ticker).first()
    if not asset:
        asset = Asset(ticker=ticker, name=name, category=category)
        db.add(asset)
        db.flush()
    return asset


def seed_ticker(db: Session, ticker: str, period: str, interval: str, reset: bool) -> int:
    """
    Fetch and upsert OHLCV bars for one ticker.
    Returns the number of newly inserted rows.
    """
    print(f"  → {ticker:<14}", end="", flush=True)
    try:
        df = fetch_ohlcv(ticker, period, interval)
    except Exception as exc:
        print(f"  ⚠  skipped — {exc}")
        return 0

    asset = upsert_asset(db, ticker)

    if reset:
        db.query(MarketData).filter(MarketData.asset_id == asset.id).delete()
        existing_dates: set[date] = set()
    else:
        rows = db.query(MarketData.date).filter(MarketData.asset_id == asset.id).all()
        existing_dates = {r.date for r in rows}

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
    info = ASSET_CATALOGUE.get(ticker, (ticker, "", ""))
    market_tag = f"[{info}]" if len(info) > 2 else ""
    print(f"  ✓  {len(new_rows):>4} new bars  (fetched {len(df)})  {market_tag}")
    return len(new_rows)


def main():
    parser = argparse.ArgumentParser(description="Seed market data into PostgreSQL")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--period",   default=settings.seed_period,   help="e.g. 2y, 5y")
    parser.add_argument("--interval", default=settings.seed_interval, help="e.g. 1d, 1wk")
    parser.add_argument("--reset",    action="store_true",            help="Wipe existing data first")
    args = parser.parse_args()

    # Always initialize or sync database schemas on startup
    if args.reset:
        init_db()
    else:
        Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    tickers = [t.upper() for t in args.tickers]
    print(f"\nSeeding {len(tickers)} instrument(s)  "
          f"[period={args.period}  interval={args.interval}  reset={args.reset}]\n")

    total = 0
    try:
        for ticker in tickers:
            total += seed_ticker(db, ticker, args.period, args.interval, args.reset)
        db.commit()
        print(f"\n✅  Done — {total} total rows inserted.\n")
    except Exception as exc:
        db.rollback()
        print(f"\n❌  Seed failed: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()