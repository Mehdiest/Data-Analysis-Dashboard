# Market Data Analysis Dashboard — Backend

FastAPI backend powering a forex/crypto analytics dashboard.  
PostgreSQL + SQLAlchemy · pandas · statsmodels · scikit-learn · Prophet

---

## 🚀 Key Features

- **Multi-Asset Ingestion:** Automating data pipelines for 32+ instruments including Major/Minor Forex pairs, Crypto assets, Stablecoins, Precious Metals, and Energy commodities via `yfinance`.
- **Advanced Trend Analytics:** Real-time OLS (Ordinary Least Squares) linear trend regression scoring slopes, $R^2$ values, and dynamically computing 20-day and 50-day Moving Averages (MA).
- **Pairwise Correlation Heatmaps:** Generates interactive Pearson correlation matrices based on daily log-returns across all cross-asset history.
- **Predictive Forecasting Engine:** Implements time-series forecasting models (Prophet / Rolling Regressions) estimating price action with 80% confidence prediction intervals.
- **JWT Authenticated Terminal:** Secure endpoint access with stateful sessions and custom styling tokens built for high-density visualization.

---

## Quick start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ running locally (or Docker)

### 2. Create the database

```bash
psql -U postgres -c "CREATE DATABASE market_dashboard;"
```

### 3. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Configure environment (optional)

Create a `.env` file in `backend/` to override any default:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/market_dashboard
SECRET_KEY=change-me-in-production
DEMO_USERNAME=admin
DEMO_PASSWORD=dashboard123
```

### 5. Seed the database

Fetches 2 years of daily OHLCV bars from Yahoo Finance:

```bash
python seed_data.py
```

Add `--reset` to wipe and re-seed, or `--tickers BTC-USD ETH-USD` to seed a subset.

### 6. Run the API server

```bash
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

---

## Authentication

All `/api/*` endpoints require a JWT bearer token.

```bash
# 1. Obtain a token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "dashboard123"}'

# 2. Use the token
curl http://localhost:8000/api/kpi/BTC-USD \
  -H "Authorization: Bearer <your_token>"
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/login` | Obtain JWT token |
| `GET` | `/api/kpi/` | KPI cards for all assets |
| `GET` | `/api/kpi/{ticker}` | KPI card for one asset |
| `GET` | `/api/kpi/assets/list` | List all available assets |
| `GET` | `/api/trend/{ticker}` | OHLC + MA-20/50 + OLS trend |
| `GET` | `/api/correlation/` | Pearson correlation matrix |
| `GET` | `/api/forecast/{ticker}` | Price forecast (Prophet / linear) |
| `GET` | `/health` | Liveness probe |

### Query parameters

**`/api/trend/{ticker}`**
- `start_date` — ISO date, filter bars from this date
- `end_date`   — ISO date, filter bars up to this date

**`/api/correlation/`**
- `tickers` — repeatable param, e.g. `?tickers=EURUSD=X&tickers=BTC-USD`

**`/api/forecast/{ticker}`**
- `horizon_days` — integer 5–180, default 30

---

## Project structure

```
backend/
├── app/
│   ├── main.py           # FastAPI app, CORS, router registration
│   ├── config.py         # Settings (pydantic-settings, .env support)
│   ├── database.py       # SQLAlchemy engine + session + Base
│   ├── models.py         # ORM: Asset, MarketData
│   ├── schemas.py        # Pydantic v2 request/response models
│   ├── auth.py           # JWT creation and verification
│   ├── routers/
│   │   ├── auth.py       # POST /auth/login
│   │   ├── kpi.py        # GET  /api/kpi/*
│   │   ├── trend.py      # GET  /api/trend/*
│   │   ├── correlation.py# GET  /api/correlation/
│   │   └── forecast.py   # GET  /api/forecast/*
│   └── analysis/
│       ├── statistics.py # KPI, trend, correlation computations
│       └── forecaster.py # Prophet + linear regression forecast
├── seed_data.py          # CLI: fetch yfinance data → PostgreSQL
└── requirements.txt
```

---

## Supported instruments (default seed)

| Ticker | Name | Category |
|--------|------|----------|
| `EURUSD=X` | EUR / USD | forex |
| `GBPUSD=X` | GBP / USD | forex |
| `JPYUSD=X` | JPY / USD | forex |
| `XAUUSD=X` | Gold / USD | commodity |
| `BTC-USD`  | Bitcoin / USD | crypto |

Add any Yahoo Finance ticker to `ASSET_CATALOGUE` in `seed_data.py` and re-run the seeder.
