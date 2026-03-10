import pandas as pd
import numpy as np
import requests
from modules.market_data import get_historical_data, get_live_price

def calculate_rsi(closes: pd.Series, period: int = 14) -> float:
    try:
        delta = closes.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 2)
    except:
        return 50.0

def calculate_macd(closes: pd.Series) -> dict:
    try:
        exp1 = closes.ewm(span=12, adjust=False).mean()
        exp2 = closes.ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        return {
            "macd": round(float(macd_line.iloc[-1]), 4),
            "signal": round(float(signal_line.iloc[-1]), 4),
            "histogram": round(float(histogram.iloc[-1]), 4)
        }
    except:
        return {"macd": 0, "signal": 0, "histogram": 0}

def calculate_bollinger_bands(closes: pd.Series, period: int = 20) -> dict:
    try:
        sma = closes.rolling(window=period).mean()
        std = closes.rolling(window=period).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        current_price = float(closes.iloc[-1])
        upper_val = float(upper.iloc[-1])
        lower_val = float(lower.iloc[-1])
        sma_val = float(sma.iloc[-1])
        band_position = (current_price - lower_val) / (upper_val - lower_val) if (upper_val - lower_val) != 0 else 0.5
        return {
            "upper": round(upper_val, 2),
            "middle": round(sma_val, 2),
            "lower": round(lower_val, 2),
            "band_position": round(band_position, 2)
        }
    except:
        return {"upper": 0, "middle": 0, "lower": 0, "band_position": 0.5}

def detect_pattern(df: pd.DataFrame) -> str:
    try:
        closes = df['Close'].tail(30)
        highs = df['High'].tail(30)
        lows = df['Low'].tail(30)
        top_indices = []
        for i in range(1, len(highs) - 1):
            if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
                top_indices.append(float(highs.iloc[i]))
        if len(top_indices) >= 2:
            if abs(top_indices[-1] - top_indices[-2]) / top_indices[-2] < 0.02:
                return "Double Top (Bearish)"
        bottom_indices = []
        for i in range(1, len(lows) - 1):
            if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
                bottom_indices.append(float(lows.iloc[i]))
        if len(bottom_indices) >= 2:
            if abs(bottom_indices[-1] - bottom_indices[-2]) / bottom_indices[-2] < 0.02:
                return "Double Bottom (Bullish)"
        if float(closes.iloc[-1]) > closes.mean() * 1.02:
            return "Uptrend"
        elif float(closes.iloc[-1]) < closes.mean() * 0.98:
            return "Downtrend"
        return "Sideways"
    except:
        return "Unknown"

def get_news_sentiment(symbol: str, api_key: str = None) -> dict:
    try:
        if not api_key:
            return {
                "sentiment_score": 50,
                "headlines": [],
                "sentiment_label": "Neutral"
            }
        clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": clean_symbol + " stock India",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": api_key
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("status") != "ok":
            return {"sentiment_score": 50, "headlines": [], "sentiment_label": "Neutral"}
        articles = data.get("articles", [])
        headlines = [a["title"] for a in articles[:5]]
        positive_words = ["up", "gain", "rise", "bull", "strong", "growth", "profit",
                         "beat", "surge", "rally", "high", "positive", "buy", "upgrade"]
        negative_words = ["down", "fall", "drop", "bear", "weak", "loss", "miss",
                         "crash", "decline", "low", "negative", "sell", "downgrade"]
        score = 50
        for headline in headlines:
            headline_lower = headline.lower()
            for word in positive_words:
                if word in headline_lower:
                    score += 5
            for word in negative_words:
                if word in headline_lower:
                    score -= 5
        score = max(0, min(100, score))
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
        return {"sentiment_score": 50, "headlines": [], "sentiment_label": "Neutral", "error": str(e)}

def generate_signal(symbol: str, timeframe: str = "1d", news_api_key: str = None) -> dict:
    try:
        df = get_historical_data(symbol, period="3mo", interval=timeframe)
        if df.empty:
            return {"error": "No data available for symbol"}
        closes = df['Close']
        rsi = calculate_rsi(closes)
        macd = calculate_macd(closes)
        bb = calculate_bollinger_bands(closes)
        pattern = detect_pattern(df)
        sentiment = get_news_sentiment(symbol, news_api_key)
        score = 0
        reasons = []
        if rsi < 30:
            score += 30
            reasons.append(f"RSI {rsi} is oversold (Bullish)")
        elif rsi > 70:
            score -= 30
            reasons.append(f"RSI {rsi} is overbought (Bearish)")
        elif rsi < 45:
            score += 10
            reasons.append(f"RSI {rsi} is mildly bullish")
        elif rsi > 55:
            score -= 10
            reasons.append(f"RSI {rsi} is mildly bearish")
        if macd["histogram"] > 0 and macd["macd"] > macd["signal"]:
            score += 25
            reasons.append("MACD bullish crossover")
        elif macd["histogram"] < 0 and macd["macd"] < macd["signal"]:
            score -= 25
            reasons.append("MACD bearish crossover")
        if bb["band_position"] < 0.2:
            score += 20
            reasons.append("Price near lower Bollinger Band (Oversold)")
        elif bb["band_position"] > 0.8:
            score -= 20
            reasons.append("Price near upper Bollinger Band (Overbought)")
        if "Bullish" in pattern or pattern == "Uptrend":
            score += 15
            reasons.append(f"Chart pattern: {pattern}")
        elif "Bearish" in pattern or pattern == "Downtrend":
            score -= 15
            reasons.append(f"Chart pattern: {pattern}")
        sentiment_score = sentiment["sentiment_score"]
        if sentiment_score >= 60:
            score += 10
            reasons.append(f"News sentiment is Positive ({sentiment_score})")
        elif sentiment_score <= 40:
            score -= 10
            reasons.append(f"News sentiment is Negative ({sentiment_score})")
        if score >= 30:
            signal = "BUY"
        elif score <= -30:
            signal = "SELL"
        else:
            signal = "HOLD"
        confidence = min(100, abs(score))
        return {
            "symbol": symbol.upper(),
            "signal": signal,
            "confidence": confidence,
            "score": score,
            "rsi": rsi,
            "macd": macd,
            "bollinger_bands": bb,
            "pattern": pattern,
            "sentiment": sentiment,
            "reasons": reasons,
            "timeframe": timeframe
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}