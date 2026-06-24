"""
models.py — SQLAlchemy ORM table definitions.

Schema:
    assets       — one row per instrument (e.g. EURUSD, BTC-USD)
    market_data  — daily OHLCV bars, one row per (asset, date)

Indexes are chosen to accelerate the three most common query patterns:
    1. Time-range scans on a single asset  →  (asset_id, date)
    2. Latest-price lookups               →  (asset_id, date DESC)
    3. Multi-asset correlation queries    →  (date)
"""

from datetime import date as DateType

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Asset(Base):
    """
    Represents a tradable instrument (forex pair, commodity, crypto).

    ticker   — Yahoo Finance symbol, e.g. "EURUSD=X"
    name     — human-readable label shown in the UI
    category — grouping bucket: "forex" | "crypto" | "commodity"
    """

    __tablename__ = "assets"

    id       = Column(Integer, primary_key=True, index=True)
    ticker   = Column(String(32), unique=True, nullable=False, index=True)
    name     = Column(String(64), nullable=False)
    category = Column(String(32), nullable=False, default="forex")

    # Back-reference to all price bars for this asset
    bars = relationship("MarketData", back_populates="asset", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Asset {self.ticker}>"


class MarketData(Base):
    """
    One row = one daily OHLCV bar for a given asset.

    Columns follow the standard OHLCV convention:
        open, high, low, close  — prices in USD
        volume                  — number of units traded (0 for forex spot)
    """

    __tablename__ = "market_data"

    id         = Column(Integer, primary_key=True, index=True)
    asset_id   = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    date       = Column(Date, nullable=False)
    open       = Column(Float, nullable=False)
    high       = Column(Float, nullable=False)
    low        = Column(Float, nullable=False)
    close      = Column(Float, nullable=False)
    volume     = Column(BigInteger, nullable=False, default=0)

    asset = relationship("Asset", back_populates="bars")

    # ── Constraints ────────────────────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint("asset_id", "date", name="uq_asset_date"),
        # Primary query pattern: range scan on one asset ordered by date
        Index("ix_market_data_asset_date", "asset_id", "date"),
        # Cross-asset correlation queries join on date
        Index("ix_market_data_date", "date"),
    )

    def __repr__(self) -> str:
        return f"<MarketData asset_id={self.asset_id} date={self.date} close={self.close}>"
