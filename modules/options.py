import yfinance as yf
import numpy as np
from scipy.stats import norm
from modules.market_data import get_symbol, get_live_price
from datetime import datetime

def black_scholes_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "CE") -> dict:
    try:
        if T <= 0:
            return {"error": "Option has expired"}
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        if option_type.upper() == "CE":
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
            delta = norm.cdf(d1)
        else:
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            delta = norm.cdf(d1) - 1
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        if option_type.upper() == "CE":
            theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                    - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
        else:
            theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                    + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
        vega = S * norm.pdf(d1) * np.sqrt(T) / 100
        return {
            "price": round(float(price), 2),
            "delta": round(float(delta), 4),
            "gamma": round(float(gamma), 6),
            "theta": round(float(theta), 4),
            "vega": round(float(vega), 4),
            "d1": round(float(d1), 4),
            "d2": round(float(d2), 4)
        }
    except Exception as e:
        return {"error": str(e)}

def get_options_chain(symbol: str, expiry: str = None) -> dict:
    try:
        yf_symbol = get_symbol(symbol)
        ticker = yf.Ticker(yf_symbol)
        expirations = ticker.options
        if not expirations:
            return {"error": "No options data available for this symbol"}
        if expiry is None:
            expiry = expirations[0]
        elif expiry not in expirations:
            expiry = expirations[0]
        chain = ticker.option_chain(expiry)
        calls = chain.calls
        puts = chain.puts
        price_data = get_live_price(symbol)
        current_price = price_data.get("price", 0)
        calls_data = []
        for _, row in calls.iterrows():
            calls_data.append({
                "strike": float(row.get("strike", 0)),
                "last_price": float(row.get("lastPrice", 0)),
                "bid": float(row.get("bid", 0)),
                "ask": float(row.get("ask", 0)),
                "volume": int(row.get("volume", 0) or 0),
                "open_interest": int(row.get("openInterest", 0) or 0),
                "iv": round(float(row.get("impliedVolatility", 0)) * 100, 2)
            })
        puts_data = []
        for _, row in puts.iterrows():
            puts_data.append({
                "strike": float(row.get("strike", 0)),
                "last_price": float(row.get("lastPrice", 0)),
                "bid": float(row.get("bid", 0)),
                "ask": float(row.get("ask", 0)),
                "volume": int(row.get("volume", 0) or 0),
                "open_interest": int(row.get("openInterest", 0) or 0),
                "iv": round(float(row.get("impliedVolatility", 0)) * 100, 2)
            })
        return {
            "symbol": symbol.upper(),
            "expiry": expiry,
            "current_price": current_price,
            "available_expiries": list(expirations),
            "calls": calls_data,
            "puts": puts_data
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

def calculate_max_pain(symbol: str, expiry: str = None) -> dict:
    try:
        chain_data = get_options_chain(symbol, expiry)
        if "error" in chain_data:
            return chain_data
        calls = chain_data["calls"]
        puts = chain_data["puts"]
        all_strikes = list(set(
            [c["strike"] for c in calls] +
            [p["strike"] for p in puts]
        ))
        all_strikes.sort()
        max_pain_strike = None
        min_pain_value = float('inf')
        for test_strike in all_strikes:
            total_pain = 0
            for c in calls:
                if test_strike > c["strike"]:
                    total_pain += (test_strike - c["strike"]) * c["open_interest"]
            for p in puts:
                if test_strike < p["strike"]:
                    total_pain += (p["strike"] - test_strike) * p["open_interest"]
            if total_pain < min_pain_value:
                min_pain_value = total_pain
                max_pain_strike = test_strike
        return {
            "symbol": symbol.upper(),
            "expiry": chain_data["expiry"],
            "max_pain": max_pain_strike,
            "current_price": chain_data["current_price"],
            "distance_from_max_pain": round(
                chain_data["current_price"] - max_pain_strike, 2
            ) if max_pain_strike else None
        }
    except Exception as e:
        return {"error": str(e)}

def detect_unusual_activity(symbol: str) -> dict:
    try:
        chain_data = get_options_chain(symbol)
        if "error" in chain_data:
            return chain_data
        alerts = []
        calls = chain_data["calls"]
        puts = chain_data["puts"]
        all_volumes = [c["volume"] for c in calls] + [p["volume"] for p in puts]
        all_oi = [c["open_interest"] for c in calls] + [p["open_interest"] for p in puts]
        avg_volume = sum(all_volumes) / len(all_volumes) if all_volumes else 0
        avg_oi = sum(all_oi) / len(all_oi) if all_oi else 0
        for c in calls:
            if avg_volume > 0 and c["volume"] > avg_volume * 3:
                alerts.append({
                    "type": "Volume Spike",
                    "option": f"CE {c['strike']}",
                    "value": c["volume"],
                    "avg": round(avg_volume, 0),
                    "multiplier": round(c["volume"] / avg_volume, 1)
                })
            if avg_oi > 0 and c["open_interest"] > avg_oi * 3:
                alerts.append({
                    "type": "OI Spike",
                    "option": f"CE {c['strike']}",
                    "value": c["open_interest"],
                    "avg": round(avg_oi, 0),
                    "multiplier": round(c["open_interest"] / avg_oi, 1)
                })
        for p in puts:
            if avg_volume > 0 and p["volume"] > avg_volume * 3:
                alerts.append({
                    "type": "Volume Spike",
                    "option": f"PE {p['strike']}",
                    "value": p["volume"],
                    "avg": round(avg_volume, 0),
                    "multiplier": round(p["volume"] / avg_volume, 1)
                })
            if avg_oi > 0 and p["open_interest"] > avg_oi * 3:
                alerts.append({
                    "type": "OI Spike",
                    "option": f"PE {p['strike']}",
                    "value": p["open_interest"],
                    "avg": round(avg_oi, 0),
                    "multiplier": round(p["open_interest"] / avg_oi, 1)
                })
        return {
            "symbol": symbol.upper(),
            "expiry": chain_data["expiry"],
            "current_price": chain_data["current_price"],
            "alerts": alerts,
            "total_alerts": len(alerts),
            "avg_call_volume": round(avg_volume, 0),
            "avg_oi": round(avg_oi, 0)
        }
    except Exception as e:
        return {"error": str(e)}