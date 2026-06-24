"""
config.py — Application settings loaded from environment variables.

Uses pydantic-settings so every value can be overridden via .env file
or shell environment without touching source code.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:postgres@localhost:5432/market_dashboard"

    # ── JWT Auth ──────────────────────────────────────────────────────────────
    secret_key: str = "dev-secret-change-in-production-please"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # ── Demo credentials (single user, no user table needed for portfolio) ────
    demo_username: str = "admin"
    demo_password: str = "dashboard123"

    # ── Data seeding ──────────────────────────────────────────────────────────
    # Tickers to fetch from Yahoo Finance when seeding the database
    seed_tickers: list[str] = ["EURUSD=X", "GBPUSD=X", "JPYUSD=X", "XAUUSD=X", "BTC-USD"]
    seed_period: str = "2y"      # 2 years of daily OHLCV data
    seed_interval: str = "1d"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
