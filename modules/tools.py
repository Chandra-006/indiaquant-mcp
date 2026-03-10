import json
from modules.market_data import get_live_price, get_sector_data
from modules.signals import generate_signal, get_news_sentiment
from modules.options import (
    get_options_chain, calculate_max_pain,
    detect_unusual_activity, black_scholes_greeks
)
from modules.portfolio import (
    get_portfolio_pnl, place_virtual_trade,
    scan_market, init_db
)

init_db()

# PUT YOUR NEWSAPI KEY HERE
NEWS_API_KEY = "your_newsapi_key_here"

def handle_tool(tool_name: str, arguments: dict) -> str:
    try:
        result = {}

        if tool_name == "get_live_price":
            symbol = arguments.get("symbol", "")
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                result = get_live_price(symbol)

        elif tool_name == "get_options_chain":
            symbol = arguments.get("symbol", "")
            expiry = arguments.get("expiry", None)
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                result = get_options_chain(symbol, expiry)

        elif tool_name == "analyze_sentiment":
            symbol = arguments.get("symbol", "")
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                sentiment = get_news_sentiment(symbol, NEWS_API_KEY)
                result = {
                    "symbol": symbol.upper(),
                    "sentiment_score": sentiment["sentiment_score"],
                    "sentiment_label": sentiment["sentiment_label"],
                    "headlines": sentiment["headlines"],
                    "signal": "BUY" if sentiment["sentiment_score"] >= 60
                              else "SELL" if sentiment["sentiment_score"] <= 40
                              else "HOLD"
                }

        elif tool_name == "generate_signal":
            symbol = arguments.get("symbol", "")
            timeframe = arguments.get("timeframe", "1d")
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                result = generate_signal(symbol, timeframe, NEWS_API_KEY)

        elif tool_name == "get_portfolio_pnl":
            result = get_portfolio_pnl()

        elif tool_name == "place_virtual_trade":
            symbol = arguments.get("symbol", "")
            quantity = arguments.get("quantity", 0)
            side = arguments.get("side", "")
            stop_loss = arguments.get("stop_loss", None)
            target = arguments.get("target", None)
            if not symbol or not quantity or not side:
                result = {"error": "symbol, quantity and side are required"}
            else:
                result = place_virtual_trade(
                    symbol, int(quantity), side, stop_loss, target
                )

        elif tool_name == "calculate_greeks":
            spot_price = arguments.get("spot_price")
            strike_price = arguments.get("strike_price")
            expiry_days = arguments.get("expiry_days")
            volatility = arguments.get("volatility", 0.20)
            option_type = arguments.get("option_type", "CE")
            risk_free_rate = arguments.get("risk_free_rate", 0.065)
            if not all([spot_price, strike_price, expiry_days]):
                result = {"error": "spot_price, strike_price and expiry_days are required"}
            else:
                T = float(expiry_days) / 365
                result = black_scholes_greeks(
                    S=float(spot_price),
                    K=float(strike_price),
                    T=T,
                    r=float(risk_free_rate),
                    sigma=float(volatility),
                    option_type=option_type
                )
                result["inputs"] = {
                    "spot_price": spot_price,
                    "strike_price": strike_price,
                    "expiry_days": expiry_days,
                    "volatility": volatility,
                    "option_type": option_type
                }

        elif tool_name == "detect_unusual_activity":
            symbol = arguments.get("symbol", "")
            if not symbol:
                result = {"error": "symbol is required"}
            else:
                result = detect_unusual_activity(symbol)

        elif tool_name == "scan_market":
            filter_criteria = {
                "min_price": arguments.get("min_price", 0),
                "max_price": arguments.get("max_price", float('inf')),
                "min_change_pct": arguments.get("min_change_pct", -float('inf')),
                "max_change_pct": arguments.get("max_change_pct", float('inf')),
                "sector": arguments.get("sector", None)
            }
            result = scan_market(filter_criteria)

        elif tool_name == "get_sector_heatmap":
            result = {
                "heatmap": get_sector_data(),
                "timestamp": __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return json.dumps(result, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


TOOLS = [
    {
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
        "name": "get_portfolio_pnl",
        "description": "Get real-time P&L for all virtual portfolio positions",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
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
            "required": []
        }
    },
    {
        "name": "get_sector_heatmap",
        "description": "Get sector-wise performance heatmap for IT, Banking, Auto, Pharma etc.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]