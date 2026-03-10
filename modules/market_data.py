"""
market_data.py
==============
Module 1: Market Data Engine

The foundation of the entire project — every other module
depends on this one to get price data.

Contains 4 functions:
1. get_symbol()          — Convert Indian symbol to yfinance format
2. get_live_price()      — Fetch current price with 60s cache
3. get_historical_data() — Fetch OHLCV data for indicator calculations
4. get_sector_data()     — Sector-wise average % change heatmap

Data Source: Yahoo Finance via yfinance (free, no API key needed)
Limitation: ~15 min delayed prices on free tier
"""

import yfinance as yf          # Yahoo Finance API wrapper
import pandas as pd            # DataFrame for historical OHLCV data
from datetime import datetime  # For timestamp in price response
import time                    # For cache expiry check (time.time())


# ─────────────────────────────────────────────
# IN-MEMORY CACHE
# ─────────────────────────────────────────────
# Stores recently fetched prices to avoid hitting
# yfinance API on every single tool call.
#
# Structure: { "price_RELIANCE.NS": (timestamp, result_dict) }
# Key   = "price_" + yfinance symbol
# Value = tuple of (fetch_time, price_data_dict)
_cache = {}

# How long to reuse cached price before fetching fresh (seconds)
# 60s is a good balance — fast enough for live trading context,
# low enough to avoid API rate limiting
CACHE_DURATION = 60


# ─────────────────────────────────────────────
# SYMBOL CONVERTER
# ─────────────────────────────────────────────
def get_symbol(symbol: str) -> str:
    """
    Convert Indian stock symbol to yfinance-compatible format.

    yfinance requires specific formats for Indian market:
        NSE stocks  → append ".NS"   e.g. RELIANCE  → RELIANCE.NS
        BSE stocks  → append ".BO"   e.g. RELIANCE  → RELIANCE.BO
        NSE indices → prefix "^"     e.g. NIFTY     → ^NSEI

    Special index mappings:
        NIFTY / NIFTY50 → ^NSEI     (Nifty 50 index)
        BANKNIFTY       → ^NSEBANK  (Bank Nifty index)
        SENSEX          → ^BSESN    (BSE Sensex index)

    Args:
        symbol: Raw symbol e.g. "reliance", "NIFTY", "TCS.NS"

    Returns:
        yfinance-ready symbol e.g. "RELIANCE.NS", "^NSEI"
    """
    # Normalize: uppercase and strip whitespace
    symbol = symbol.upper().strip()

    # ── Special Index Mappings ──
    # These have completely different yfinance symbols
    if symbol == "NIFTY" or symbol == "NIFTY50":
        return "^NSEI"      # NSE Nifty 50 index

    if symbol == "BANKNIFTY":
        return "^NSEBANK"   # NSE Bank Nifty index

    if symbol == "SENSEX":
        return "^BSESN"     # BSE Sensex index

    # ── NSE Stock Default ──
    # If symbol has no suffix and no ^ prefix, assume it's an NSE stock
    if (not symbol.endswith(".NS") and
        not symbol.endswith(".BO") and
        not symbol.startswith("^")):
        return symbol + ".NS"   # Default to NSE exchange

    # Already formatted (e.g. passed as "RELIANCE.NS" or "^NSEI")
    return symbol


# ─────────────────────────────────────────────
# LIVE PRICE FETCHER
# ─────────────────────────────────────────────
def get_live_price(symbol: str) -> dict:
    """
    Fetch the current live price for a stock or index.

    Uses a 60-second in-memory cache to avoid excessive
    API calls when multiple tools request the same symbol.

    Flow:
        1. Convert symbol to yfinance format
        2. Check cache — return cached data if fresh (< 60s old)
        3. Fetch fresh data from yfinance using fast_info
        4. Calculate change and change_pct from previous close
        5. Store in cache and return result

    fast_info vs info:
        ticker.info      → full data, slow (~2-3 seconds)
        ticker.fast_info → price only, fast (~0.3 seconds)
        We use fast_info since we only need price data here.

    Args:
        symbol: Stock symbol e.g. "RELIANCE", "TCS", "NIFTY"

    Returns:
        dict with symbol, price, previous_close, change,
              change_pct, volume, timestamp
        OR dict with "error" key if fetch fails
    """
    try:
        # Step 1: Convert to yfinance format
        yf_symbol = get_symbol(symbol)

        # Step 2: Check in-memory cache
        cache_key = f"price_{yf_symbol}"   # Unique key per symbol
        if cache_key in _cache:
            cached_time, cached_data = _cache[cache_key]
            if time.time() - cached_time < CACHE_DURATION:
                # Cache is fresh — return stored data without API call
                return cached_data

        # Step 3: Fetch fresh price from yfinance
        ticker = yf.Ticker(yf_symbol)
        info   = ticker.fast_info  # Faster than .info for price-only data

        # Step 4: Calculate price change from previous close
        price      = round(float(info.last_price), 2)
        prev_close = round(float(info.previous_close), 2)
        change     = round(price - prev_close, 2)        # Absolute ₹ change
        change_pct = round((change / prev_close) * 100, 2)  # % change

        # three_month_average_volume → fallback to 0 if unavailable
        volume = int(info.three_month_average_volume or 0)

        # Build clean result dict
        result = {
            "symbol":         symbol.upper(),
            "price":          price,
            "previous_close": prev_close,
            "change":         change,       # e.g. -5.8 (₹ change)
            "change_pct":     change_pct,   # e.g. -0.41 (% change)
            "volume":         volume,
            "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Step 5: Save to cache with current timestamp
        _cache[cache_key] = (time.time(), result)

        return result

    except Exception as e:
        # Return error dict — never raise, so callers don't crash
        return {"error": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
# HISTORICAL DATA FETCHER
# ─────────────────────────────────────────────
def get_historical_data(symbol: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    """
    Fetch historical OHLCV candlestick data for a stock.

    Used by signals.py to calculate technical indicators:
        RSI              → needs Close prices
        MACD             → needs Close prices
        Bollinger Bands  → needs Close prices
        Pattern Detector → needs High, Low, Close prices

    period options:
        "1mo"  = 1 month      "6mo"  = 6 months
        "3mo"  = 3 months     "1y"   = 1 year
        "ytd"  = year to date "max"  = all available data

    interval options:
        "1d"  = daily candles    (for swing trading signals)
        "1h"  = hourly candles   (for intraday signals)
        "15m" = 15-min candles   (for short-term signals)
        Note: intervals < 1d only available for last 60 days

    Args:
        symbol:   Stock symbol e.g. "TCS", "RELIANCE"
        period:   How far back to fetch (default: 3 months)
        interval: Candle size (default: daily)

    Returns:
        pandas DataFrame with columns: Open, High, Low, Close, Volume
        Empty DataFrame if fetch fails or no data available
    """
    try:
        yf_symbol = get_symbol(symbol)
        ticker    = yf.Ticker(yf_symbol)

        # Download OHLCV data for requested period and interval
        df = ticker.history(period=period, interval=interval)

        # Return empty DataFrame if no data received
        if df.empty:
            return pd.DataFrame()

        # Ensure index is proper datetime type for time-based operations
        df.index = pd.to_datetime(df.index)

        return df

    except Exception as e:
        # Print error for debugging but return empty DataFrame
        # so signal generation can handle it gracefully
        print(f"Error fetching historical data: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# SECTOR HEATMAP
# ─────────────────────────────────────────────
def get_sector_data() -> dict:
    """
    Calculate average % change for each market sector today.

    Sectors covered: IT, Banking, Auto, Pharma, Energy, FMCG
    Each sector uses 4 representative large-cap stocks.

    Method:
        For each stock in sector:
            change_pct = (current_price - prev_close) / prev_close × 100
        Sector change = average of all stock changes in that sector

    Example output:
        {"IT": -0.34, "Banking": 1.61, "Auto": 2.87, ...}

    Positive = sector up today, Negative = sector down today

    Returns:
        dict mapping sector name to average % change
        Only includes sectors where at least 1 stock fetched successfully
    """
    # Define sectors with their representative NSE stocks
    # .NS suffix already included — no need to run through get_symbol()
    sectors = {
        "IT":      ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"],
        "Banking": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS"],
        "Auto":    ["MARUTI.NS", "TATAMOTORS.NS", "BAJAJ-AUTO.NS", "HEROMOTOCO.NS"],
        "Pharma":  ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS"],
        "Energy":  ["RELIANCE.NS", "ONGC.NS", "NTPC.NS", "POWERGRID.NS"],
        "FMCG":    ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS"]
    }

    heatmap = {}

    for sector, stocks in sectors.items():
        changes = []  # Collect % changes for all stocks in this sector

        for stock in stocks:
            try:
                ticker = yf.Ticker(stock)
                info   = ticker.fast_info  # Fast price-only fetch

                prev = float(info.previous_close)
                curr = float(info.last_price)

                # Calculate today's % change for this stock
                change_pct = round(((curr - prev) / prev) * 100, 2)
                changes.append(change_pct)

            except:
                # Skip individual stock errors silently
                # e.g. TATAMOTORS.NS sometimes returns 404
                continue

        # Only add sector if at least 1 stock fetched successfully
        # Prevents showing 0% for sectors where all fetches failed
        if changes:
            heatmap[sector] = round(sum(changes) / len(changes), 2)

    return heatmap