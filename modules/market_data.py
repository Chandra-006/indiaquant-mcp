import yfinance as yf
import pandas as pd
from datetime import datetime
import time

_cache = {}
CACHE_DURATION = 60

def get_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if symbol == "NIFTY" or symbol == "NIFTY50":
        return "^NSEI"
    if symbol == "BANKNIFTY":
        return "^NSEBANK"
    if symbol == "SENSEX":
        return "^BSESN"
    if not symbol.endswith(".NS") and not symbol.endswith(".BO") and not symbol.startswith("^"):
        return symbol + ".NS"
    return symbol

def get_live_price(symbol: str) -> dict:
    try:
        yf_symbol = get_symbol(symbol)
        cache_key = f"price_{yf_symbol}"
        if cache_key in _cache:
            cached_time, cached_data = _cache[cache_key]
            if time.time() - cached_time < CACHE_DURATION:
                return cached_data
        ticker = yf.Ticker(yf_symbol)
        info = ticker.fast_info
        price = round(float(info.last_price), 2)
        prev_close = round(float(info.previous_close), 2)
        change = round(price - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2)
        volume = int(info.three_month_average_volume or 0)
        result = {
            "symbol": symbol.upper(),
            "price": price,
            "previous_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        _cache[cache_key] = (time.time(), result)
        return result
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

def get_historical_data(symbol: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    try:
        yf_symbol = get_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        print(f"Error fetching historical data: {e}")
        return pd.DataFrame()

def get_sector_data() -> dict:
    sectors = {
        "IT": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"],
        "Banking": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS"],
        "Auto": ["MARUTI.NS", "TATAMOTORS.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
        "Pharma": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS"],
        "Energy": ["RELIANCE.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS"],
        "FMCG": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS"]
    }
    heatmap = {}
    for sector, stocks in sectors.items():
        changes = []
        for stock in stocks:
            try:
                ticker = yf.Ticker(stock)
                info = ticker.fast_info
                prev = float(info.previous_close)
                curr = float(info.last_price)
                change_pct = round(((curr - prev) / prev) * 100, 2)
                changes.append(change_pct)
            except:
                continue
        if changes:
            heatmap[sector] = round(sum(changes) / len(changes), 2)
    return heatmap