"""
options.py
==========
Module 3: Options Chain Analyzer

Contains 4 functions:
1. black_scholes_greeks()   — Price options + calculate Delta/Gamma/Theta/Vega
2. get_options_chain()      — Fetch live CE/PE chain from yfinance
3. calculate_max_pain()     — Find strike where most option buyers lose money
4. detect_unusual_activity()— Flag volume/OI spikes (3x above average)

Key concept — Options Greeks:
    Delta → How much option price moves per ₹1 stock move
    Gamma → How fast Delta itself changes
    Theta → Daily time decay (options lose value every day)
    Vega  → Sensitivity to volatility changes
"""

import yfinance as yf              # Live options chain data
import numpy as np                 # Math operations (log, sqrt, exp)
from scipy.stats import norm       # Normal distribution CDF and PDF
from modules.market_data import get_symbol, get_live_price
from datetime import datetime      # Imported but not used — can be removed


# ─────────────────────────────────────────────
# BLACK-SCHOLES GREEKS (FROM SCRATCH)
# ─────────────────────────────────────────────
def black_scholes_greeks(S: float, K: float, T: float, r: float,
                          sigma: float, option_type: str = "CE") -> dict:
    """
    Calculate option price and all Greeks using Black-Scholes model.

    Black-Scholes is the industry-standard formula for pricing
    European options. Implemented here from scratch without any
    options-specific library.

    Parameters:
        S:           Spot price (current stock/index price)
        K:           Strike price of the option
        T:           Time to expiry in YEARS (e.g. 7 days = 7/365 = 0.0192)
        r:           Risk-free rate as decimal (India: 6.5% = 0.065)
        sigma:       Implied Volatility as decimal (e.g. 20% = 0.20)
        option_type: "CE" for Call, "PE" for Put

    Core Formulas:
        d1 = [ln(S/K) + (r + σ²/2) × T] / (σ × √T)
        d2 = d1 - σ × √T

        Call Price = S×N(d1) - K×e^(-rT)×N(d2)
        Put Price  = K×e^(-rT)×N(-d2) - S×N(-d1)

        where N() = cumulative normal distribution (norm.cdf)
              n() = normal PDF (norm.pdf)

    Greeks Formulas:
        Delta (Call) = N(d1)           → ranges 0 to 1
        Delta (Put)  = N(d1) - 1       → ranges -1 to 0
        Gamma        = n(d1) / (S×σ×√T) → same for CE and PE
        Theta (Call) = [-(S×n(d1)×σ)/(2√T) - r×K×e^(-rT)×N(d2)]  / 365
        Theta (Put)  = [-(S×n(d1)×σ)/(2√T) + r×K×e^(-rT)×N(-d2)] / 365
        Vega         = S×n(d1)×√T / 100  → same for CE and PE

    Returns:
        dict with price, delta, gamma, theta (daily), vega (per 1% vol), d1, d2
    """
    try:
        # Guard: can't price an expired option
        if T <= 0:
            return {"error": "Option has expired"}

        # ── Step 1: Calculate d1 and d2 ──
        # These are intermediate values used in all Greeks formulas
        # d1 combines: how far ITM/OTM, time value, and volatility
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))

        # d2 = d1 adjusted for volatility over time
        # Represents risk-adjusted probability of expiring ITM
        d2 = d1 - sigma * np.sqrt(T)

        # ── Step 2: Option Price + Delta ──
        if option_type.upper() == "CE":
            # Call option price (right to BUY at strike K)
            # N(d1) = probability-weighted stock price factor
            # N(d2) = probability of call expiring In The Money
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

            # Call Delta: 0 = far OTM, 0.5 = ATM, 1 = deep ITM
            delta = norm.cdf(d1)

        else:
            # Put option price (right to SELL at strike K)
            # N(-d2) = probability of put expiring In The Money
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

            # Put Delta: -1 = deep ITM, -0.5 = ATM, 0 = far OTM
            delta = norm.cdf(d1) - 1

        # ── Step 3: Gamma ──
        # Rate of change of Delta per ₹1 move in stock
        # Same formula for both Call and Put
        # High gamma near expiry = delta changes very fast (risky!)
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))

        # ── Step 4: Theta (Time Decay) ──
        # How much option loses in value per day due to time passing
        # Divided by 365 to convert from annual to daily decay
        # Always negative — options always lose time value each day
        if option_type.upper() == "CE":
            theta = (
                -(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                - r * K * np.exp(-r * T) * norm.cdf(d2)
            ) / 365
        else:
            # Put theta differs only in the second term (N(-d2) instead of N(d2))
            theta = (
                -(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                + r * K * np.exp(-r * T) * norm.cdf(-d2)
            ) / 365

        # ── Step 5: Vega ──
        # How much option price changes per 1% increase in volatility
        # Divided by 100 to express per 1% (not per 100%)
        # Same formula for both Call and Put
        vega = S * norm.pdf(d1) * np.sqrt(T) / 100

        return {
            "price": round(float(price), 2),   # Theoretical option price in ₹
            "delta": round(float(delta), 4),   # Per ₹1 stock move
            "gamma": round(float(gamma), 6),   # Rate of delta change
            "theta": round(float(theta), 4),   # Daily time decay in ₹
            "vega":  round(float(vega), 4),    # Per 1% volatility change
            "d1":    round(float(d1), 4),      # Intermediate value (shown for transparency)
            "d2":    round(float(d2), 4)       # Intermediate value (shown for transparency)
        }

    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────
# LIVE OPTIONS CHAIN
# ─────────────────────────────────────────────
def get_options_chain(symbol: str, expiry: str = None) -> dict:
    """
    Fetch live options chain data from yfinance.

    An options chain shows all available Call (CE) and Put (PE)
    contracts at every strike price for a given expiry date.

    Args:
        symbol: Stock/index symbol e.g. "NIFTY", "RELIANCE"
        expiry: Date string "YYYY-MM-DD" — uses nearest if not provided

    Returns:
        dict with calls list, puts list, current price, available expiries
        Each option row has: strike, last_price, bid, ask, volume, OI, IV%
    """
    try:
        # Convert to yfinance format e.g. NIFTY → ^NSEI
        yf_symbol = get_symbol(symbol)
        ticker    = yf.Ticker(yf_symbol)

        # Get all available expiry dates for this symbol
        expirations = ticker.options
        if not expirations:
            return {"error": "No options data available for this symbol"}

        # Use nearest expiry if none specified or if given expiry not found
        if expiry is None:
            expiry = expirations[0]        # Nearest available expiry
        elif expiry not in expirations:
            expiry = expirations[0]        # Fallback to nearest if invalid

        # Fetch the full options chain for selected expiry
        # chain.calls and chain.puts are pandas DataFrames
        chain = ticker.option_chain(expiry)
        calls = chain.calls
        puts  = chain.puts

        # Get current stock price for context (to identify ATM strikes)
        price_data    = get_live_price(symbol)
        current_price = price_data.get("price", 0)

        # ── Format Call Options ──
        calls_data = []
        for _, row in calls.iterrows():
            calls_data.append({
                "strike":        float(row.get("strike", 0)),
                "last_price":    float(row.get("lastPrice", 0)),
                "bid":           float(row.get("bid", 0)),
                "ask":           float(row.get("ask", 0)),
                # "or 0" handles NaN values from yfinance
                "volume":        int(row.get("volume", 0) or 0),
                "open_interest": int(row.get("openInterest", 0) or 0),
                # IV from yfinance is decimal → multiply by 100 for percentage
                "iv":            round(float(row.get("impliedVolatility", 0)) * 100, 2)
            })

        # ── Format Put Options ──
        puts_data = []
        for _, row in puts.iterrows():
            puts_data.append({
                "strike":        float(row.get("strike", 0)),
                "last_price":    float(row.get("lastPrice", 0)),
                "bid":           float(row.get("bid", 0)),
                "ask":           float(row.get("ask", 0)),
                "volume":        int(row.get("volume", 0) or 0),
                "open_interest": int(row.get("openInterest", 0) or 0),
                "iv":            round(float(row.get("impliedVolatility", 0)) * 100, 2)
            })

        return {
            "symbol":             symbol.upper(),
            "expiry":             expiry,
            "current_price":      current_price,
            "available_expiries": list(expirations),  # All future expiry dates
            "calls":              calls_data,
            "puts":               puts_data
        }

    except Exception as e:
        return {"error": str(e), "symbol": symbol}


# ─────────────────────────────────────────────
# MAX PAIN CALCULATOR
# ─────────────────────────────────────────────
def calculate_max_pain(symbol: str, expiry: str = None) -> dict:
    """
    Find the Max Pain strike price for an expiry.

    Max Pain Theory:
        At expiry, stock price tends to gravitate toward the strike
        where option BUYERS lose the maximum total money.
        (= where option SELLERS/writers gain the most)

    Algorithm:
        For each possible strike as a "test expiry price":
            Call pain = sum of (test - strike) × OI  for all calls where test > strike
            Put pain  = sum of (strike - test) × OI  for all puts where test < strike
            Total pain = call pain + put pain
        Max Pain = strike with the MINIMUM total pain

    Interpretation:
        current_price > max_pain → stock may drift DOWN toward max pain
        current_price < max_pain → stock may drift UP toward max pain

    Args:
        symbol: Stock/index symbol
        expiry: Optional expiry date

    Returns:
        dict with max_pain strike and distance from current price
    """
    try:
        # Fetch full options chain first
        chain_data = get_options_chain(symbol, expiry)
        if "error" in chain_data:
            return chain_data

        calls = chain_data["calls"]
        puts  = chain_data["puts"]

        # Get all unique strike prices from both calls and puts combined
        all_strikes = list(set(
            [c["strike"] for c in calls] +
            [p["strike"] for p in puts]
        ))
        all_strikes.sort()  # Sort ascending for clean iteration

        max_pain_strike = None
        min_pain_value  = float('inf')  # Start with highest possible pain

        # Test each strike as potential expiry price
        for test_strike in all_strikes:
            total_pain = 0

            # ── Call Holder Pain ──
            # Call is worthless if stock < strike at expiry
            # Pain = intrinsic value lost = (test - strike) × OI
            for c in calls:
                if test_strike > c["strike"]:
                    total_pain += (test_strike - c["strike"]) * c["open_interest"]

            # ── Put Holder Pain ──
            # Put is worthless if stock > strike at expiry
            # Pain = intrinsic value lost = (strike - test) × OI
            for p in puts:
                if test_strike < p["strike"]:
                    total_pain += (p["strike"] - test_strike) * p["open_interest"]

            # Track the strike with minimum total pain
            if total_pain < min_pain_value:
                min_pain_value  = total_pain
                max_pain_strike = test_strike

        return {
            "symbol":       symbol.upper(),
            "expiry":       chain_data["expiry"],
            "max_pain":     max_pain_strike,
            "current_price": chain_data["current_price"],
            # Positive = stock above max pain (may fall)
            # Negative = stock below max pain (may rise)
            "distance_from_max_pain": round(
                chain_data["current_price"] - max_pain_strike, 2
            ) if max_pain_strike else None
        }

    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────
# UNUSUAL ACTIVITY DETECTOR
# ─────────────────────────────────────────────
def detect_unusual_activity(symbol: str) -> dict:
    """
    Detect unusual options activity via volume and OI spikes.

    Unusual activity often signals large institutional bets,
    hedging activity, or informed trading before major moves.

    Detection Logic:
        1. Calculate average volume across ALL options (calls + puts)
        2. Calculate average OI across ALL options
        3. Flag any single option where:
           volume > 3× average → Volume Spike
           OI     > 3× average → OI Spike

    Why 3x threshold?
        Random variation rarely exceeds 2x average.
        3x+ indicates intentional large positioning.

    Args:
        symbol: Stock symbol e.g. "INFY", "RELIANCE"

    Returns:
        dict with alerts list — each alert has type, option, value, multiplier
    """
    try:
        # Fetch full options chain to analyze
        chain_data = get_options_chain(symbol)
        if "error" in chain_data:
            return chain_data

        alerts = []
        calls  = chain_data["calls"]
        puts   = chain_data["puts"]

        # ── Calculate Averages Across ALL Options ──
        # Combine calls and puts for a unified baseline
        all_volumes = [c["volume"] for c in calls] + [p["volume"] for p in puts]
        all_oi      = [c["open_interest"] for c in calls] + [p["open_interest"] for p in puts]

        # Guard against empty lists
        avg_volume = sum(all_volumes) / len(all_volumes) if all_volumes else 0
        avg_oi     = sum(all_oi) / len(all_oi) if all_oi else 0

        # ── Scan Call Options for Spikes ──
        for c in calls:
            # Volume spike: this call traded 3x+ more than average
            if avg_volume > 0 and c["volume"] > avg_volume * 3:
                alerts.append({
                    "type":       "Volume Spike",
                    "option":     f"CE {c['strike']}",
                    "value":      c["volume"],
                    "avg":        round(avg_volume, 0),
                    "multiplier": round(c["volume"] / avg_volume, 1)  # e.g. 4.2x
                })
            # OI spike: large open position built up at this strike
            if avg_oi > 0 and c["open_interest"] > avg_oi * 3:
                alerts.append({
                    "type":       "OI Spike",
                    "option":     f"CE {c['strike']}",
                    "value":      c["open_interest"],
                    "avg":        round(avg_oi, 0),
                    "multiplier": round(c["open_interest"] / avg_oi, 1)
                })

        # ── Scan Put Options for Spikes ──
        for p in puts:
            # Volume spike on puts = large bearish bet
            if avg_volume > 0 and p["volume"] > avg_volume * 3:
                alerts.append({
                    "type":       "Volume Spike",
                    "option":     f"PE {p['strike']}",
                    "value":      p["volume"],
                    "avg":        round(avg_volume, 0),
                    "multiplier": round(p["volume"] / avg_volume, 1)
                })
            # OI spike on puts = large hedging or bearish position
            if avg_oi > 0 and p["open_interest"] > avg_oi * 3:
                alerts.append({
                    "type":       "OI Spike",
                    "option":     f"PE {p['strike']}",
                    "value":      p["open_interest"],
                    "avg":        round(avg_oi, 0),
                    "multiplier": round(p["open_interest"] / avg_oi, 1)
                })

        return {
            "symbol":           symbol.upper(),
            "expiry":           chain_data["expiry"],
            "current_price":    chain_data["current_price"],
            "alerts":           alerts,
            "total_alerts":     len(alerts),
            "avg_call_volume":  round(avg_volume, 0),
            "avg_oi":           round(avg_oi, 0)
        }

    except Exception as e:
        return {"error": str(e)}