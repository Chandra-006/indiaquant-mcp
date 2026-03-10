"""
tools.py
========
MCP Tools Layer — The Bridge between Claude and all modules.

This file does TWO things:
1. handle_tool() — Routes tool calls from Claude to correct module function
2. TOOLS list    — Defines all 10 tools so Claude knows what's available

Flow:
    Claude says "get price of RELIANCE"
    → MCP calls handle_tool("get_live_price", {"symbol": "RELIANCE"})
    → handle_tool calls get_live_price("RELIANCE")
    → Returns JSON: {"price": 1412.8, "change_pct": -0.41, ...}
    → Claude responds to user with the data
"""

import json

# ── Import functions from all 4 modules ──
from modules.market_data import get_live_price, get_sector_data
from modules.signals import generate_signal, get_news_sentiment
from modules.options import (
    get_options_chain, calculate_max_pain,     # calculate_max_pain imported but unused
    detect_unusual_activity, black_scholes_greeks
)
from modules.portfolio import (
    get_portfolio_pnl, place_virtual_trade,
    scan_market, init_db
)

# ─────────────────────────────────────────────
# INITIALIZATION
# ─────────────────────────────────────────────
# Create SQLite tables (positions, trades, balance)
# when this module is first imported.
# Safe to call multiple times — uses IF NOT EXISTS.
init_db()

# ─────────────────────────────────────────────
# API KEY
# ─────────────────────────────────────────────
# NewsAPI free tier: 100 requests/day
# Sign up at: https://newsapi.org/register
# Without this key, sentiment defaults to Neutral (score=50)
NEWS_API_KEY = "your_newsapi_key_here"


# ─────────────────────────────────────────────
# TOOL ROUTER
# ─────────────────────────────────────────────
def handle_tool(tool_name: str, arguments: dict) -> str:
    """
    Route MCP tool calls to the correct module function.

    All tool responses are normalized into a result dict
    and JSON-encoded at the end for consistent output.

    Args:
        tool_name:  Name of the tool e.g. "get_live_price"
        arguments:  Dict of inputs e.g. {"symbol": "RELIANCE"}

    Returns:
        JSON string — always returns JSON even on errors
        so the MCP interface stays stable.
    """
    try:
        # All tool responses are normalized into this dict
        # and JSON-encoded at the end
        result = {}

        # ── Route request to the matching tool handler ──

        # ── Tool 1: Live Stock Price ──
        if tool_name == "get_live_price":
            symbol = arguments.get("symbol", "")
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                # Fetches from yfinance with 60s cache
                result = get_live_price(symbol)

        # ── Tool 2: Options Chain ──
        elif tool_name == "get_options_chain":
            symbol = arguments.get("symbol", "")
            expiry = arguments.get("expiry", None)  # Optional — uses nearest if None
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                result = get_options_chain(symbol, expiry)

        # ── Tool 3: News Sentiment Analysis ──
        elif tool_name == "analyze_sentiment":
            symbol = arguments.get("symbol", "")
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                sentiment = get_news_sentiment(symbol, NEWS_API_KEY)

                # Map numeric sentiment score into an actionable trade bias:
                # score >= 60 → BUY (positive news)
                # score <= 40 → SELL (negative news)
                # score 40-60 → HOLD (neutral news)
                result = {
                    "symbol": symbol.upper(),
                    "sentiment_score": sentiment["sentiment_score"],
                    "sentiment_label": sentiment["sentiment_label"],
                    "headlines": sentiment["headlines"],
                    "signal": "BUY" if sentiment["sentiment_score"] >= 60
                              else "SELL" if sentiment["sentiment_score"] <= 40
                              else "HOLD"
                }

        # ── Tool 4: Trade Signal Generator ──
        elif tool_name == "generate_signal":
            symbol = arguments.get("symbol", "")
            timeframe = arguments.get("timeframe", "1d")  # Default: daily candles
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                # Combines RSI + MACD + Bollinger Bands + Pattern + Sentiment
                result = generate_signal(symbol, timeframe, NEWS_API_KEY)

        # ── Tool 5: Portfolio P&L ──
        elif tool_name == "get_portfolio_pnl":
            # No arguments needed — reads all positions from SQLite
            result = get_portfolio_pnl()

        # ── Tool 6: Virtual Trade ──
        elif tool_name == "place_virtual_trade":
            symbol    = arguments.get("symbol", "")
            quantity  = arguments.get("quantity", 0)
            side      = arguments.get("side", "")        # "BUY" or "SELL"
            stop_loss = arguments.get("stop_loss", None) # Optional alert price
            target    = arguments.get("target", None)    # Optional alert price

            if not symbol or not quantity or not side:
                result = {"error": "symbol, quantity and side are required"}
            else:
                result = place_virtual_trade(
                    symbol, int(quantity), side, stop_loss, target
                )

        # ── Tool 7: Options Greeks (Black-Scholes) ──
        elif tool_name == "calculate_greeks":
            spot_price     = arguments.get("spot_price")
            strike_price   = arguments.get("strike_price")
            expiry_days    = arguments.get("expiry_days")
            volatility     = arguments.get("volatility", 0.20)    # Default 20% IV
            option_type    = arguments.get("option_type", "CE")   # Default Call
            risk_free_rate = arguments.get("risk_free_rate", 0.065) # India: 6.5%

            # Core pricing inputs are mandatory
            # Optional values use practical defaults
            if not all([spot_price, strike_price, expiry_days]):
                result = {"error": "spot_price, strike_price and expiry_days are required"}
            else:
                # Black-Scholes expects time to expiry in YEARS not days
                # e.g. 7 days = 7/365 = 0.0192 years
                T = float(expiry_days) / 365

                result = black_scholes_greeks(
                    S=float(spot_price),    # Spot price
                    K=float(strike_price),  # Strike price
                    T=T,                    # Time in years
                    r=float(risk_free_rate),# Risk-free rate
                    sigma=float(volatility),# Implied volatility
                    option_type=option_type # CE or PE
                )

                # Include input parameters in response for transparency
                result["inputs"] = {
                    "spot_price": spot_price,
                    "strike_price": strike_price,
                    "expiry_days": expiry_days,
                    "volatility": volatility,
                    "option_type": option_type
                }

        # ── Tool 8: Unusual Options Activity ──
        elif tool_name == "detect_unusual_activity":
            symbol = arguments.get("symbol", "")
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                # Detects volume/OI spikes that are 3x above average
                result = detect_unusual_activity(symbol)

        # ── Tool 9: Market Scanner ──
        elif tool_name == "scan_market":
            # Use wide defaults so users can provide only
            # the filters they care about
            filter_criteria = {
                "min_price":      arguments.get("min_price", 0),
                "max_price":      arguments.get("max_price", float('inf')),
                "min_change_pct": arguments.get("min_change_pct", -float('inf')),
                "max_change_pct": arguments.get("max_change_pct", float('inf')),
                "sector":         arguments.get("sector", None)
            }
            result = scan_market(filter_criteria)

        # ── Tool 10: Sector Heatmap ──
        elif tool_name == "get_sector_heatmap":
            result = {
                "heatmap": get_sector_data(),
                # Attach server-side timestamp for freshness checks
                "timestamp": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        else:
            # Unknown tool name received
            result = {"error": f"Unknown tool: {tool_name}"}

        # Ensure non-serializable objects (e.g. datetime, numpy floats)
        # are converted safely using default=str
        return json.dumps(result, default=str)

    except Exception as e:
        # Keep tool interface stable by always returning JSON even on failures
        # This prevents the MCP server from crashing on unexpected errors
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────
# MCP TOOL DEFINITIONS
# ─────────────────────────────────────────────
# This list is read by Claude on startup to discover all tools.
# Each tool has:
#   name        — unique identifier used in handle_tool()
#   description — Claude reads this to know when to use the tool
#   inputSchema — JSON Schema defining required and optional inputs
#
# Claude uses the description to decide WHICH tool to call.
# The inputSchema validates inputs before handle_tool() runs.

TOOLS = [
    {
        # Tool 1
        "name": "get_live_price",
        "description": "Get live price, change% and volume for any NSE/BSE stock or index",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol e.g. RELIANCE, TCS, NIFTY, BANKNIFTY"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        # Tool 2
        "name": "get_options_chain",
        "description": "Get live options chain with CE/PE strikes and open interest",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol e.g. NIFTY, RELIANCE"
                },
                "expiry": {
                    "type": "string",
                    "description": "Expiry date in YYYY-MM-DD format (optional)"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        # Tool 3
        "name": "analyze_sentiment",
        "description": "Analyze news sentiment for a stock and return score and headlines",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol e.g. INFY, HDFC"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        # Tool 4
        "name": "generate_signal",
        "description": "Generate BUY/SELL/HOLD signal with confidence score using technicals and sentiment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol e.g. TCS, WIPRO"
                },
                "timeframe": {
                    "type": "string",
                    "description": "Timeframe: 1d, 1h, 15m (default: 1d)"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        # Tool 5
        "name": "get_portfolio_pnl",
        "description": "Get real-time P&L for all virtual portfolio positions",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        # Tool 6
        "name": "place_virtual_trade",
        "description": "Place a virtual BUY or SELL trade with optional stop loss and target",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol"
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of shares"
                },
                "side": {
                    "type": "string",
                    "description": "BUY or SELL"
                },
                "stop_loss": {
                    "type": "number",
                    "description": "Stop loss price (optional)"
                },
                "target": {
                    "type": "number",
                    "description": "Target price (optional)"
                }
            },
            "required": ["symbol", "quantity", "side"]
        }
    },
    {
        # Tool 7
        "name": "calculate_greeks",
        "description": "Calculate Black-Scholes option Greeks: Delta, Gamma, Theta, Vega",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spot_price": {
                    "type": "number",
                    "description": "Current stock/index price"
                },
                "strike_price": {
                    "type": "number",
                    "description": "Option strike price"
                },
                "expiry_days": {
                    "type": "integer",
                    "description": "Days to expiry"
                },
                "volatility": {
                    "type": "number",
                    "description": "Implied volatility as decimal e.g. 0.20 for 20%"
                },
                "option_type": {
                    "type": "string",
                    "description": "CE for Call or PE for Put"
                }
            },
            "required": ["spot_price", "strike_price", "expiry_days"]
        }
    },
    {
        # Tool 8
        "name": "detect_unusual_activity",
        "description": "Detect unusual options activity via volume and OI spikes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol e.g. INFY, RELIANCE"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        # Tool 9
        "name": "scan_market",
        "description": "Scan Nifty 50 stocks using filters like price range and % change",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_price": {
                    "type": "number",
                    "description": "Minimum stock price"
                },
                "max_price": {
                    "type": "number",
                    "description": "Maximum stock price"
                },
                "min_change_pct": {
                    "type": "number",
                    "description": "Minimum % change e.g. -5"
                },
                "max_change_pct": {
                    "type": "number",
                    "description": "Maximum % change e.g. 5"
                }
            },
            "required": []  # All filters are optional
        }
    },
    {
        # Tool 10
        "name": "get_sector_heatmap",
        "description": "Get sector-wise performance heatmap for IT, Banking, Auto, Pharma etc.",
        "inputSchema": {
            "type": "object",
            "properties": {}  # No inputs needed
        }
    }
]