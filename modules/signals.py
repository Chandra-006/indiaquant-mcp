"""
signals.py
==========
Module 2: AI Trade Signal Generator

Contains 5 functions:
1. calculate_rsi()         — Momentum indicator (oversold/overbought)
2. calculate_macd()        — Trend + momentum indicator
3. calculate_bollinger_bands() — Volatility indicator
4. detect_pattern()        — Chart pattern recognition
5. get_news_sentiment()    — News headline scoring via NewsAPI
6. generate_signal()       — Combines all above into BUY/SELL/HOLD
"""

import pandas as pd    # Data manipulation — Series and DataFrame operations
import numpy as np     # Math operations (imported but not directly used here)
import requests        # HTTP requests to NewsAPI

from modules.market_data import get_historical_data, get_live_price


# ─────────────────────────────────────────────
# INDICATOR 1: RSI (Relative Strength Index)
# ─────────────────────────────────────────────
def calculate_rsi(closes: pd.Series, period: int = 14) -> float:
    """
    Calculate RSI to measure momentum.

    RSI tells us how fast prices are moving up or down.

    Interpretation:
        RSI < 30  → Oversold  → Stock may bounce up   → BUY signal
        RSI > 70  → Overbought → Stock may pull back  → SELL signal
        RSI 30-70 → Neutral zone

    Formula:
        RS  = Average Gain / Average Loss (over 14 days)
        RSI = 100 - (100 / (1 + RS))

    Args:
        closes: Series of daily closing prices
        period: Lookback window (default 14 days — industry standard)

    Returns:
        RSI value between 0 and 100
    """
    try:
        # Step 1: Calculate daily price changes
        # e.g. [100, 102, 101] → [NaN, +2, -1]
        delta = closes.diff()

        # Step 2: Separate gains and losses
        # gain: keep positive changes, replace negatives with 0
        # loss: keep negative changes (flip sign), replace positives with 0
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=period).mean()

        # Step 3: RS = ratio of average gain to average loss
        rs = gain / loss

        # Step 4: Apply RSI formula
        rsi = 100 - (100 / (1 + rs))

        # Return most recent RSI value
        return round(float(rsi.iloc[-1]), 2)

    except:
        # Return neutral 50 if calculation fails
        # (e.g. not enough data points for the period)
        return 50.0


# ─────────────────────────────────────────────
# INDICATOR 2: MACD
# (Moving Average Convergence Divergence)
# ─────────────────────────────────────────────
def calculate_macd(closes: pd.Series) -> dict:
    """
    Calculate MACD to detect trend direction and momentum shifts.

    MACD uses two EMAs (Exponential Moving Averages).
    EMA gives more weight to recent prices than simple average.

    Interpretation:
        MACD > Signal → Bullish momentum  → BUY
        MACD < Signal → Bearish momentum  → SELL
        Histogram > 0 → Bullish crossover
        Histogram < 0 → Bearish crossover

    Formula:
        EMA12     = 12-day EMA of closing prices (fast)
        EMA26     = 26-day EMA of closing prices (slow)
        MACD Line = EMA12 - EMA26
        Signal    = 9-day EMA of MACD Line
        Histogram = MACD Line - Signal Line

    Returns:
        dict with macd, signal, histogram values
    """
    try:
        # Fast EMA (12 days) — reacts quickly to price changes
        exp1 = closes.ewm(span=12, adjust=False).mean()

        # Slow EMA (26 days) — reacts slowly to price changes
        exp2 = closes.ewm(span=26, adjust=False).mean()

        # MACD Line = difference between fast and slow EMA
        # Positive = fast EMA above slow EMA = upward momentum
        macd_line = exp1 - exp2

        # Signal Line = 9-day EMA of MACD (smoothed version)
        signal_line = macd_line.ewm(span=9, adjust=False).mean()

        # Histogram = gap between MACD and Signal
        # Growing histogram = momentum increasing
        # Shrinking histogram = momentum fading
        histogram = macd_line - signal_line

        return {
            "macd":      round(float(macd_line.iloc[-1]), 4),
            "signal":    round(float(signal_line.iloc[-1]), 4),
            "histogram": round(float(histogram.iloc[-1]), 4)
        }

    except:
        # Return zeros (neutral) if calculation fails
        return {"macd": 0, "signal": 0, "histogram": 0}


# ─────────────────────────────────────────────
# INDICATOR 3: BOLLINGER BANDS
# ─────────────────────────────────────────────
def calculate_bollinger_bands(closes: pd.Series, period: int = 20) -> dict:
    """
    Calculate Bollinger Bands to measure price volatility.

    Bands expand when volatility is high, contract when low.

    Interpretation:
        Price near lower band (band_position < 0.2) → Oversold  → BUY
        Price near upper band (band_position > 0.8) → Overbought → SELL
        band_position = 0.5 → Price at middle (neutral)

    Formula:
        Middle Band = 20-day SMA
        Upper Band  = SMA + (2 × Standard Deviation)
        Lower Band  = SMA - (2 × Standard Deviation)

    band_position:
        0.0 = price exactly at lower band
        0.5 = price exactly at middle band
        1.0 = price exactly at upper band

    Args:
        closes: Series of closing prices
        period: SMA window (default 20 days)

    Returns:
        dict with upper, middle, lower prices and band_position
    """
    try:
        # 20-day Simple Moving Average = middle band
        sma = closes.rolling(window=period).mean()

        # Standard deviation measures how spread out prices are
        std = closes.rolling(window=period).std()

        # Upper and lower bands = 2 standard deviations from mean
        # ~95% of prices fall within these bands statistically
        upper = sma + (std * 2)
        lower = sma - (std * 2)

        # Get the most recent values
        current_price = float(closes.iloc[-1])
        upper_val     = float(upper.iloc[-1])
        lower_val     = float(lower.iloc[-1])
        sma_val       = float(sma.iloc[-1])

        # band_position: normalizes price position within the bands
        # Formula: (price - lower) / (upper - lower)
        # Guard against division by zero when bands collapse
        band_position = (
            (current_price - lower_val) / (upper_val - lower_val)
            if (upper_val - lower_val) != 0
            else 0.5
        )

        return {
            "upper":         round(upper_val, 2),
            "middle":        round(sma_val, 2),
            "lower":         round(lower_val, 2),
            "band_position": round(band_position, 2)
        }

    except:
        # Return neutral values on failure
        return {"upper": 0, "middle": 0, "lower": 0, "band_position": 0.5}


# ─────────────────────────────────────────────
# PATTERN DETECTOR
# ─────────────────────────────────────────────
def detect_pattern(df: pd.DataFrame) -> str:
    """
    Detect basic chart patterns from last 30 days of price data.

    Patterns detected (in priority order):
        Double Top (Bearish)   — Two similar peaks → price likely to fall
        Double Bottom (Bullish) — Two similar troughs → price likely to rise
        Uptrend                — Price above 30-day average by 2%+
        Downtrend              — Price below 30-day average by 2%+
        Sideways               — Price within ±2% of average

    Args:
        df: DataFrame with High, Low, Close columns

    Returns:
        Pattern name as string
    """
    try:
        # Use only last 30 candles for pattern detection
        closes = df['Close'].tail(30)
        highs  = df['High'].tail(30)
        lows   = df['Low'].tail(30)

        # ── Detect Double Top ──
        # A local high = higher than both its neighbors
        top_indices = []
        for i in range(1, len(highs) - 1):
            if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
                top_indices.append(float(highs.iloc[i]))

        # Two peaks within 2% of each other = Double Top
        # 2% tolerance handles real-world price noise
        if len(top_indices) >= 2:
            if abs(top_indices[-1] - top_indices[-2]) / top_indices[-2] < 0.02:
                return "Double Top (Bearish)"

        # ── Detect Double Bottom ──
        # A local low = lower than both its neighbors
        bottom_indices = []
        for i in range(1, len(lows) - 1):
            if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
                bottom_indices.append(float(lows.iloc[i]))

        # Two troughs within 2% of each other = Double Bottom
        if len(bottom_indices) >= 2:
            if abs(bottom_indices[-1] - bottom_indices[-2]) / bottom_indices[-2] < 0.02:
                return "Double Bottom (Bullish)"

        # ── Detect Simple Trend ──
        # Compare current price vs 30-day average
        current = float(closes.iloc[-1])
        if current > closes.mean() * 1.02:    # 2% above average = Uptrend
            return "Uptrend"
        elif current < closes.mean() * 0.98:  # 2% below average = Downtrend
            return "Downtrend"

        return "Sideways"

    except:
        return "Unknown"


# ─────────────────────────────────────────────
# NEWS SENTIMENT ANALYZER
# ─────────────────────────────────────────────
def get_news_sentiment(symbol: str, api_key: str = None) -> dict:
    """
    Fetch news headlines and calculate a sentiment score.

    Uses simple keyword matching — no ML model needed.

    Scoring:
        Base score = 50 (neutral)
        Each positive keyword found in headline → +5
        Each negative keyword found in headline → -5
        Score clamped between 0 and 100

    Final Labels:
        score >= 60 → "Positive"
        score <= 40 → "Negative"
        40-60       → "Neutral"

    API: NewsAPI.org (free tier: 100 requests/day)

    Args:
        symbol:  Stock symbol e.g. "TCS", "RELIANCE.NS"
        api_key: NewsAPI key — returns Neutral if not provided

    Returns:
        dict with sentiment_score, sentiment_label, headlines
    """
    try:
        # Without API key, return neutral — don't block signal generation
        if not api_key:
            return {
                "sentiment_score": 50,
                "headlines": [],
                "sentiment_label": "Neutral"
            }

        # Strip .NS or .BO suffix for cleaner search query
        # e.g. "RELIANCE.NS" → "RELIANCE"
        clean_symbol = symbol.replace(".NS", "").replace(".BO", "")

        # Fetch latest news from NewsAPI
        url = "https://newsapi.org/v2/everything"
        params = {
            "q":        clean_symbol + " stock India",
            "language": "en",
            "sortBy":   "publishedAt",  # Most recent first
            "pageSize": 10,             # Fetch 10, use top 5
            "apiKey":   api_key
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        # Return neutral if API call failed
        if data.get("status") != "ok":
            return {"sentiment_score": 50, "headlines": [], "sentiment_label": "Neutral"}

        articles = data.get("articles", [])

        # Extract top 5 headline strings
        headlines = [a["title"] for a in articles[:5]]

        # Keyword lists for scoring
        positive_words = ["up", "gain", "rise", "bull", "strong", "growth", "profit",
                          "beat", "surge", "rally", "high", "positive", "buy", "upgrade"]
        negative_words = ["down", "fall", "drop", "bear", "weak", "loss", "miss",
                          "crash", "decline", "low", "negative", "sell", "downgrade"]

        # Start at neutral 50, adjust based on keyword matches
        score = 50
        for headline in headlines:
            headline_lower = headline.lower()
            for word in positive_words:
                if word in headline_lower:
                    score += 5   # Positive word found
            for word in negative_words:
                if word in headline_lower:
                    score -= 5   # Negative word found

        # Clamp score to valid range [0, 100]
        score = max(0, min(100, score))

        # Convert numeric score to human-readable label
        if score >= 60:
            label = "Positive"
        elif score <= 40:
            label = "Negative"
        else:
            label = "Neutral"

        return {
            "sentiment_score": score,
            "headlines": headlines,
            "sentiment_label": label
        }

    except Exception as e:
        # Don't crash signal generation just because news fetch failed
        return {
            "sentiment_score": 50,
            "headlines": [],
            "sentiment_label": "Neutral",
            "error": str(e)
        }


# ─────────────────────────────────────────────
# MAIN SIGNAL GENERATOR
# ─────────────────────────────────────────────
def generate_signal(symbol: str, timeframe: str = "1d", news_api_key: str = None) -> dict:
    """
    Generate a BUY/SELL/HOLD signal by combining all indicators.

    Weighted Scoring System (total range: -100 to +100):
    ┌──────────────────┬────────┬─────────────────────────────────────┐
    │ Indicator        │ Weight │ Logic                               │
    ├──────────────────┼────────┼─────────────────────────────────────┤
    │ RSI              │  30%   │ <30=+30, >70=-30, <45=+10, >55=-10 │
    │ MACD             │  25%   │ bullish crossover=+25, bearish=-25  │
    │ Bollinger Bands  │  20%   │ near lower=+20, near upper=-20      │
    │ Chart Pattern    │  15%   │ bullish=+15, bearish=-15            │
    │ News Sentiment   │  10%   │ positive=+10, negative=-10          │
    └──────────────────┴────────┴─────────────────────────────────────┘

    Final Decision:
        score >= +30 → BUY
        score <= -30 → SELL
        else         → HOLD

    Confidence = abs(score) capped at 100

    Args:
        symbol:       Stock symbol e.g. "RELIANCE", "TCS"
        timeframe:    Candle size "1d", "1h", "15m"
        news_api_key: Optional NewsAPI key

    Returns:
        dict with signal, confidence, score, all indicator values, reasons list
    """
    try:
        # Fetch 3 months of historical data for indicator calculations
        df = get_historical_data(symbol, period="3mo", interval=timeframe)
        if df.empty:
            return {"error": "No data available for symbol"}

        closes = df['Close']

        # ── Calculate all 5 indicators ──
        rsi       = calculate_rsi(closes)
        macd      = calculate_macd(closes)
        bb        = calculate_bollinger_bands(closes)
        pattern   = detect_pattern(df)
        sentiment = get_news_sentiment(symbol, news_api_key)

        # ── Scoring: starts at 0 (neutral) ──
        score   = 0
        reasons = []  # Human-readable explanation of signal

        # ── RSI Score (weight: 30%) ──
        if rsi < 30:
            score += 30
            reasons.append(f"RSI {rsi} is oversold (Bullish)")
        elif rsi > 70:
            score -= 30
            reasons.append(f"RSI {rsi} is overbought (Bearish)")
        elif rsi < 45:
            # Mildly bullish zone
            score += 10
            reasons.append(f"RSI {rsi} is mildly bullish")
        elif rsi > 55:
            # Mildly bearish zone
            score -= 10
            reasons.append(f"RSI {rsi} is mildly bearish")

        # ── MACD Score (weight: 25%) ──
        # Bullish crossover: MACD crossed above Signal line
        if macd["histogram"] > 0 and macd["macd"] > macd["signal"]:
            score += 25
            reasons.append("MACD bullish crossover")
        # Bearish crossover: MACD crossed below Signal line
        elif macd["histogram"] < 0 and macd["macd"] < macd["signal"]:
            score -= 25
            reasons.append("MACD bearish crossover")

        # ── Bollinger Bands Score (weight: 20%) ──
        # band_position < 0.2 = price in bottom 20% of band = oversold
        if bb["band_position"] < 0.2:
            score += 20
            reasons.append("Price near lower Bollinger Band (Oversold)")
        # band_position > 0.8 = price in top 20% of band = overbought
        elif bb["band_position"] > 0.8:
            score -= 20
            reasons.append("Price near upper Bollinger Band (Overbought)")

        # ── Chart Pattern Score (weight: 15%) ──
        if "Bullish" in pattern or pattern == "Uptrend":
            score += 15
            reasons.append(f"Chart pattern: {pattern}")
        elif "Bearish" in pattern or pattern == "Downtrend":
            score -= 15
            reasons.append(f"Chart pattern: {pattern}")

        # ── Sentiment Score (weight: 10%) ──
        sentiment_score = sentiment["sentiment_score"]
        if sentiment_score >= 60:
            score += 10
            reasons.append(f"News sentiment is Positive ({sentiment_score})")
        elif sentiment_score <= 40:
            score -= 10
            reasons.append(f"News sentiment is Negative ({sentiment_score})")

        # ── Final Signal Decision ──
        if score >= 30:
            signal = "BUY"
        elif score <= -30:
            signal = "SELL"
        else:
            signal = "HOLD"

        # Confidence = how strong the signal is (0-100)
        # abs() because -80 score = 80% confident SELL
        confidence = min(100, abs(score))

        return {
            "symbol":         symbol.upper(),
            "signal":         signal,
            "confidence":     confidence,
            "score":          score,
            "rsi":            rsi,
            "macd":           macd,
            "bollinger_bands": bb,
            "pattern":        pattern,
            "sentiment":      sentiment,
            "reasons":        reasons,
            "timeframe":      timeframe
        }

    except Exception as e:
        return {"error": str(e), "symbol": symbol}