"""
main.py — FastAPI application factory.

Registers all routers, configures CORS for the React frontend,
and exposes /health for infrastructure liveness checks.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, kpi, trend, correlation, forecast

# ── Create tables on startup (idempotent — won't drop existing data) ───────────
Base.metadata.create_all(bind=engine)

# ── Application instance ───────────────────────────────────────────────────────
app = FastAPI(
    title="Market Data Analysis Dashboard",
    description=(
        "REST API powering a forex / crypto analytics dashboard. "
        "Provides KPI cards, OHLC trend charts, correlation heatmaps, "
        "and time-series forecasts."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# In production, replace "*" with your frontend's exact origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(kpi.router)
app.include_router(trend.router)
app.include_router(correlation.router)
app.include_router(forecast.router)


# ── Health check ───────────────────────────────────────────────────────────────
@app.get("/health", tags=["meta"], summary="Liveness probe")
def health():
    """Returns 200 OK when the service is running."""
    return {"status": "ok", "version": app.version}


@app.get("/", tags=["meta"], summary="API root")
def root():
    return {
        "message": "Market Dashboard API is running",
        "docs":    "/docs",
        "health":  "/health",
    }
