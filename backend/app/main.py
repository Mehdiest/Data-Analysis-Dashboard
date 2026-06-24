"""
main.py — FastAPI application factory.

Registers all routers, configures CORS for the frontend,
and exposes /health for infrastructure liveness checks.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, kpi, trend, correlation, forecast, intraday

# Create tables on startup (idempotent)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Market Data Analysis Dashboard",
    description=(
        "REST API powering a forex / crypto analytics dashboard. "
        "Provides KPI cards, OHLC trend charts, correlation heatmaps, "
        "intraday (1H/4H) charts, and time-series forecasts."
    ),
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(kpi.router)
app.include_router(trend.router)
app.include_router(correlation.router)
app.include_router(forecast.router)
app.include_router(intraday.router)


@app.get("/health", tags=["meta"], summary="Liveness probe")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/", tags=["meta"])
def root():
    return {"message": "Market Dashboard API", "docs": "/docs", "health": "/health"}
