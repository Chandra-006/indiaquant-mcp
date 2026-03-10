# IndiaQuant MCP 🇮🇳📈

A real-time Indian stock market AI assistant built using Model Context Protocol (MCP) + 100% free APIs.

## What It Does

IndiaQuant MCP connects Claude Desktop to live Indian stock market data, giving Claude the ability to:
- Fetch live NSE/BSE stock prices
- Generate BUY/SELL/HOLD signals using technical analysis
- Analyze options chains and calculate Greeks
- Detect unusual options activity
- Manage a virtual portfolio with real-time P&L
- Scan the market using filters
- Show sector-wise performance heatmap

## Architecture
```
indiaquant-mcp/
│
├── main.py                 # MCP server entry point
├── modules/
│   ├── market_data.py      # Live prices, historical data, sector heatmap
│   ├── signals.py          # RSI, MACD, Bollinger Bands, sentiment, signals
│   ├── options.py          # Options chain, Black-Scholes Greeks, max pain
│   ├── portfolio.py        # Virtual trading, P&L, market scanner
│   └── tools.py            # MCP tool definitions and routing
└── data/
    └── portfolio.db        # SQLite virtual portfolio database
```

## Free API Stack

| Purpose | API | Limit |
|---|---|---|
| Live NSE/BSE prices | yfinance | Unlimited |
| Historical OHLC data | yfinance | Unlimited |
| Options chain data | yfinance | Unlimited |
| News sentiment | NewsAPI.org | 100 req/day |
| Technical analysis | pandas, numpy | Free |
| Greeks calculation | Custom Black-Scholes | Free |

## 10 MCP Tools

| Tool | Description |
|---|---|
| get_live_price | Live price, change%, volume |
| get_options_chain | CE/PE strikes, OI, IV |
| analyze_sentiment | News sentiment score |
| generate_signal | BUY/SELL/HOLD with confidence |
| get_portfolio_pnl | Real-time P&L |
| place_virtual_trade | Virtual BUY/SELL orders |
| calculate_greeks | Delta, Gamma, Theta, Vega |
| detect_unusual_activity | OI and volume spike alerts |
| scan_market | Filter Nifty 50 stocks |
| get_sector_heatmap | Sector performance |

## Setup Guide

### Requirements
- Python 3.11
- Claude Desktop

### Installation

1. Clone the repository:
```
git clone https://github.com/Chandra-006/indiaquant-mcp.git
cd indiaquant-mcp
```

2. Create virtual environment:
```
py -3.11 -m venv venv
venv\Scripts\activate
```

3. Install dependencies:
```
pip install mcp[cli] yfinance pandas numpy scipy newsapi-python requests
```

4. Add your NewsAPI key in modules/tools.py:
```
NEWS_API_KEY = "your_key_here"
```

5. Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "indiaquant-mcp": {
      "command": "path/to/venv/Scripts/python.exe",
      "args": ["path/to/main.py"]
    }
  }
}
```

6. Restart Claude Desktop and start chatting!

## Example Claude Conversations

- "What is the live price of RELIANCE?"
- "Generate a trading signal for TCS"
- "Show me my portfolio P&L"
- "Calculate Greeks for Nifty 22000 CE expiring in 7 days"
- "Detect unusual options activity on INFY"
- "Scan for stocks with more than 2% gain today"
- "Show me the sector heatmap"

## Signal Generator Logic

The signal generator combines multiple indicators with weighted scoring:

- RSI (30% weight) — oversold/overbought detection
- MACD (25% weight) — momentum and crossover signals
- Bollinger Bands (20% weight) — price position within bands
- Chart Patterns (15% weight) — double top/bottom, trends
- News Sentiment (10% weight) — keyword-based headline scoring

Final score above +30 = BUY, below -30 = SELL, otherwise HOLD.

## Black-Scholes Implementation

Greeks are calculated from scratch using the Black-Scholes model:
- Delta — price sensitivity to underlying movement
- Gamma — rate of change of delta
- Theta — time decay per day
- Vega — sensitivity to volatility changes

## Trade-offs and Limitations

- yfinance prices have ~15 minute delay (standard for free APIs)
- NewsAPI free tier limited to 100 requests/day
- Virtual portfolio only (no real broker integration)
- Options data availability depends on Yahoo Finance support

## Tech Stack

- Python 3.11
- MCP SDK (Model Context Protocol)
- yfinance (market data)
- pandas, numpy, scipy (calculations)
- SQLite (portfolio storage)
- NewsAPI (sentiment analysis)