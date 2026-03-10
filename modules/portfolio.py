"""
portfolio.py
============
Module 4: Portfolio Risk Manager

Manages a virtual trading portfolio using SQLite database.
No server needed — SQLite stores everything in a single .db file.

Contains 4 functions:
1. init_db()            — Create tables and set starting balance
2. place_virtual_trade()— Execute BUY/SELL at live market price
3. get_portfolio_pnl()  — Calculate real-time P&L for all positions
4. scan_market()        — Filter Nifty 50 stocks by price/change criteria

Database Schema:
    positions — currently held stocks
    trades    — full history of all orders
    balance   — available cash (starts at ₹10,00,000)
"""

import sqlite3                        # Built-in Python database — no installation needed
from datetime import datetime         # For timestamps and order ID generation
from modules.market_data import get_live_price

# Path to the SQLite database file
# All portfolio data persists here across sessions
DB_PATH = "data/portfolio.db"


# ─────────────────────────────────────────────
# DATABASE INITIALIZATION
# ─────────────────────────────────────────────
def init_db():
    """
    Create required tables if they don't exist yet.

    Called automatically before every trade and P&L check.
    Safe to call multiple times — IF NOT EXISTS prevents duplicates.

    Tables created:
        positions — open stock holdings
        trades    — complete order history
        balance   — single row with cash amount
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── Table 1: Open Positions ──
    # Stores stocks currently held in the portfolio
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol        TEXT NOT NULL,        -- e.g. "RELIANCE"
            quantity      INTEGER NOT NULL,     -- number of shares held
            avg_buy_price REAL NOT NULL,        -- weighted average cost
            side          TEXT NOT NULL,        -- always "BUY" for long positions
            stop_loss     REAL,                 -- alert price (optional)
            target        REAL,                 -- profit target price (optional)
            created_at    TEXT NOT NULL         -- first buy timestamp
        )
    """)

    # ── Table 2: Trade History ──
    # Every BUY and SELL order is recorded here permanently
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id  TEXT NOT NULL,    -- unique ID e.g. "ORD20260310150158"
            symbol    TEXT NOT NULL,
            quantity  INTEGER NOT NULL,
            price     REAL NOT NULL,    -- execution price
            side      TEXT NOT NULL,    -- "BUY" or "SELL"
            status    TEXT NOT NULL,    -- always "EXECUTED" for now
            timestamp TEXT NOT NULL
        )
    """)

    # ── Table 3: Cash Balance ──
    # Single row — updated on every BUY (deduct) and SELL (add)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balance (
            id   INTEGER PRIMARY KEY,
            cash REAL NOT NULL
        )
    """)

    # Set starting balance to ₹10,00,000 only if it doesn't exist yet
    # This prevents resetting balance on every server restart
    cursor.execute("SELECT * FROM balance WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO balance VALUES (1, 1000000.0)")

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# VIRTUAL TRADE EXECUTION
# ─────────────────────────────────────────────
def place_virtual_trade(symbol: str, quantity: int, side: str,
                         stop_loss: float = None, target: float = None) -> dict:
    """
    Execute a virtual BUY or SELL at the current live market price.

    BUY Logic:
        1. Check sufficient cash available
        2. Deduct (price × qty) from cash balance
        3. If position exists → recalculate weighted average price
        4. If new position → insert fresh row in positions table
        5. Record order in trades table

    SELL Logic:
        1. Check position exists
        2. Check sufficient quantity available to sell
        3. Add (price × qty) back to cash balance
        4. Reduce quantity or delete position if fully closed
        5. Record order in trades table

    Average Price Formula (for adding to existing position):
        new_avg = (old_qty × old_price + new_qty × new_price) / total_qty
        e.g. 10 shares @ ₹100 + 5 shares @ ₹120
             = (10×100 + 5×120) / 15 = ₹106.67

    Args:
        symbol:    Stock symbol e.g. "RELIANCE"
        quantity:  Number of shares
        side:      "BUY" or "SELL"
        stop_loss: Optional price — triggers alert when price drops here
        target:    Optional price — triggers alert when price rises here

    Returns:
        dict with order_id, execution price, remaining cash, status
    """
    try:
        init_db()  # Ensure tables exist before any DB operation

        # Normalize side to uppercase for consistent comparisons
        side = side.upper()
        if side not in ["BUY", "SELL"]:
            return {"error": "Side must be BUY or SELL"}

        # Fetch live price — this is the execution price
        price_data = get_live_price(symbol)
        if "error" in price_data:
            return {"error": f"Could not fetch price: {price_data['error']}"}

        current_price = price_data["price"]
        total_value   = current_price * quantity  # Total rupee value of trade

        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Read current cash balance
        cursor.execute("SELECT cash FROM balance WHERE id = 1")
        cash = cursor.fetchone()[0]

        # ── BUY Logic ──
        if side == "BUY":

            # Reject if not enough cash to complete purchase
            if cash < total_value:
                conn.close()
                return {"error": f"Insufficient balance. Need ₹{total_value:.2f}, have ₹{cash:.2f}"}

            # Deduct purchase cost from cash
            cursor.execute("UPDATE balance SET cash = cash - ? WHERE id = 1", (total_value,))

            # Check if a position already exists for this stock
            cursor.execute("SELECT * FROM positions WHERE symbol = ?", (symbol.upper(),))
            existing = cursor.fetchone()

            if existing:
                # Position exists → average down/up the buy price
                old_qty   = existing[2]   # Current quantity held
                old_price = existing[3]   # Current average buy price
                new_qty   = old_qty + quantity
                # Weighted average: accounts for different prices across multiple buys
                new_avg   = ((old_qty * old_price) + (quantity * current_price)) / new_qty

                cursor.execute("""
                    UPDATE positions
                    SET quantity = ?, avg_buy_price = ?, stop_loss = ?, target = ?
                    WHERE symbol = ?
                """, (new_qty, new_avg, stop_loss, target, symbol.upper()))

            else:
                # New position — insert fresh record
                cursor.execute("""
                    INSERT INTO positions
                    (symbol, quantity, avg_buy_price, side, stop_loss, target, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol.upper(), quantity, current_price, side, stop_loss, target,
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        # ── SELL Logic ──
        elif side == "SELL":

            # Check position exists before trying to sell
            cursor.execute("SELECT * FROM positions WHERE symbol = ?", (symbol.upper(),))
            existing = cursor.fetchone()

            if not existing:
                conn.close()
                return {"error": f"No position found for {symbol}"}

            # Check sufficient quantity available
            if existing[2] < quantity:
                conn.close()
                return {"error": f"Not enough shares. Have {existing[2]}, trying to sell {quantity}"}

            # Add sale proceeds back to cash
            cursor.execute("UPDATE balance SET cash = cash + ? WHERE id = 1", (total_value,))

            new_qty = existing[2] - quantity

            if new_qty == 0:
                # Position fully closed — remove from positions table
                cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol.upper(),))
            else:
                # Partial sell — just reduce quantity
                cursor.execute(
                    "UPDATE positions SET quantity = ? WHERE symbol = ?",
                    (new_qty, symbol.upper())
                )

        # ── Record Trade in History ──
        # Order ID = "ORD" + timestamp — unique enough for virtual trading
        order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cursor.execute("""
            INSERT INTO trades (order_id, symbol, quantity, price, side, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (order_id, symbol.upper(), quantity, current_price, side, "EXECUTED",
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()

        # Fetch updated cash balance for the response
        cursor.execute("SELECT cash FROM balance WHERE id = 1")
        new_cash = cursor.fetchone()[0]
        conn.close()

        return {
            "order_id":        order_id,
            "symbol":          symbol.upper(),
            "side":            side,
            "quantity":        quantity,
            "price":           current_price,
            "total_value":     round(total_value, 2),
            "status":          "EXECUTED",
            "remaining_cash":  round(new_cash, 2),
            "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────
# PORTFOLIO P&L CALCULATOR
# ─────────────────────────────────────────────
def get_portfolio_pnl() -> dict:
    """
    Calculate real-time P&L for every open position.

    For each position:
        invested    = avg_buy_price × quantity
        current_val = live_price × quantity
        pnl         = current_val - invested
        pnl_pct     = (pnl / invested) × 100
        risk_score  = abs(daily_change_pct) × 10  (capped at 100)

    Stop-loss / target alerts:
        If current_price <= stop_loss → "STOP LOSS HIT" alert
        If current_price >= target    → "TARGET REACHED" alert

    Returns:
        dict with per-position details + overall totals + cash balance
    """
    try:
        init_db()
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Fetch all open positions from DB
        cursor.execute("SELECT * FROM positions")
        positions = cursor.fetchall()

        # Fetch current cash balance
        cursor.execute("SELECT cash FROM balance WHERE id = 1")
        cash = cursor.fetchone()[0]
        conn.close()

        # Return empty portfolio summary if no positions held
        if not positions:
            return {
                "positions":       [],
                "total_invested":  0,
                "current_value":   0,
                "total_pnl":       0,
                "total_pnl_pct":   0,
                "cash_balance":    round(cash, 2),
                "portfolio_value": round(cash, 2)  # Only cash, no stocks
            }

        position_details = []
        total_invested   = 0
        total_current    = 0

        # Process each position one by one
        for pos in positions:
            symbol    = pos[1]   # Stock symbol
            quantity  = pos[2]   # Shares held
            avg_price = pos[3]   # Average buy price
            stop_loss = pos[5]   # Stop-loss price (may be None)
            target    = pos[6]   # Target price (may be None)

            # Fetch live price for real-time P&L
            price_data    = get_live_price(symbol)
            current_price = price_data.get("price", avg_price)   # Fallback to avg if fetch fails
            change_pct    = price_data.get("change_pct", 0)      # Today's % change

            # P&L calculations
            invested    = avg_price * quantity
            current_val = current_price * quantity
            pnl         = current_val - invested
            pnl_pct     = round((pnl / invested) * 100, 2) if invested > 0 else 0

            # Risk score: higher daily swing = higher risk
            # e.g. 5% daily change → risk_score = 50
            risk_score = min(100, abs(change_pct) * 10)

            # Check stop-loss and target alert conditions
            alerts = []
            if stop_loss and current_price <= stop_loss:
                alerts.append(f"STOP LOSS HIT at ₹{stop_loss}")
            if target and current_price >= target:
                alerts.append(f"TARGET REACHED at ₹{target}")

            position_details.append({
                "symbol":        symbol,
                "quantity":      quantity,
                "avg_buy_price": round(avg_price, 2),
                "current_price": round(current_price, 2),
                "invested":      round(invested, 2),
                "current_value": round(current_val, 2),
                "pnl":           round(pnl, 2),
                "pnl_pct":       pnl_pct,
                "stop_loss":     stop_loss,
                "target":        target,
                "risk_score":    round(risk_score, 1),
                "alerts":        alerts
            })

            total_invested += invested
            total_current  += current_val

        # Overall portfolio totals
        total_pnl     = total_current - total_invested
        total_pnl_pct = round((total_pnl / total_invested) * 100, 2) if total_invested > 0 else 0

        return {
            "positions":       position_details,
            "total_invested":  round(total_invested, 2),
            "current_value":   round(total_current, 2),
            "total_pnl":       round(total_pnl, 2),
            "total_pnl_pct":   total_pnl_pct,
            "cash_balance":    round(cash, 2),
            "portfolio_value": round(total_current + cash, 2)  # Stocks value + Cash
        }

    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────
# MARKET SCANNER
# ─────────────────────────────────────────────
def scan_market(filter_criteria: dict) -> dict:
    """
    Scan a universe of Nifty 50 stocks and filter by criteria.

    All filter parameters are optional — wide defaults
    mean unfiltered scan returns all 25 stocks.

    Filter options:
        min_price:      Only stocks priced above this (e.g. 500)
        max_price:      Only stocks priced below this (e.g. 2000)
        min_change_pct: Only stocks with change above this (e.g. 2.0 = up 2%+)
        max_change_pct: Only stocks with change below this (e.g. -2.0 = down 2%+)

    Results sorted by change_pct descending (best performers first).

    Args:
        filter_criteria: dict with optional filter keys

    Returns:
        dict with matching stocks list and total count
    """
    try:
        # Nifty 50 universe — 25 large-cap Indian stocks
        # Can be expanded to full 50 stocks for wider coverage
        nifty50 = [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
            "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
            "TITAN", "BAJFINANCE", "WIPRO", "ULTRACEMCO", "NESTLEIND",
            "POWERGRID", "NTPC", "TECHM", "HCLTECH", "DRREDDY"
        ]

        # Extract filters — use wide defaults so all parameters are optional
        min_price  = filter_criteria.get("min_price", 0)
        max_price  = filter_criteria.get("max_price", float('inf'))
        min_change = filter_criteria.get("min_change_pct", -float('inf'))
        max_change = filter_criteria.get("max_change_pct", float('inf'))

        matching = []

        for stock in nifty50:
            try:
                price_data = get_live_price(stock)

                # Skip stocks where price fetch failed
                if "error" in price_data:
                    continue

                price      = price_data["price"]
                change_pct = price_data["change_pct"]

                # Apply ALL filters — stock must pass every condition
                if (min_price  <= price      <= max_price and
                    min_change <= change_pct <= max_change):
                    matching.append({
                        "symbol":     stock,
                        "price":      price,
                        "change_pct": change_pct,
                        "volume":     price_data.get("volume", 0)
                    })

            except:
                # Skip individual stock errors silently
                # One bad stock shouldn't abort the whole scan
                continue

        # Sort by best performers first
        matching.sort(key=lambda x: x["change_pct"], reverse=True)

        return {
            "filter_criteria": filter_criteria,
            "matches":         matching,
            "total_matches":   len(matching)
        }

    except Exception as e:
        return {"error": str(e)}