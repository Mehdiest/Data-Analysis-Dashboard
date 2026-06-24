# Inside your trend router / endpoint
@router.get("/api/trend/{ticker}")
def get_trend(ticker: str, db=Depends(get_db)):
    # Your database query must select open, high, low, volume:
    result = db.execute(text("""
        SELECT date, open, high, low, close, volume 
        FROM asset_bars 
        WHERE ticker = :ticker 
        ORDER BY date ASC
    """), {"ticker": ticker}).fetchall()
    
    # When mapping into the "bars" array sent to frontend:
    bars = []
    closes = [r.close for r in result]
    
    # Simple MA calculation helper
    def get_ma(data, window):
        if len(data) < window: return data[-1] if data else 0
        return float(np.mean(data[-window:]))

    for i, r in enumerate(result):
        history_closes = closes[:i+1]
        bars.append({
            "date": str(r.date),
            "open": float(r.open) if r.open else float(r.close),
            "high": float(r.high) if r.high else float(r.close),
            "low": float(r.low) if r.low else float(r.close),
            "close": float(r.close),
            "volume": float(r.volume) if r.volume else 0.0,
            "ma_20": get_ma(history_closes, 20),
            "ma_50": get_ma(history_closes, 50)
        })
        
    # Calculate trend_direction, slope, r_squared...
    # Return the final dict
    return {
        "ticker": ticker,
        "bars": bars,
        "trend_direction": "up", # dynamically calculated in your code
        "trend_slope": 0.001,
        "r_squared": 0.85
    }