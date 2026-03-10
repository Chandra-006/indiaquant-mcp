import sqlite3
from datetime import datetime
from modules.market_data import get_live_price

DB_PATH = "data/portfolio.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            avg_buy_price REAL NOT NULL,
            side TEXT NOT NULL,
            stop_loss REAL,
            target REAL,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            side TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS balance (
            id INTEGER PRIMARY KEY,
            cash REAL NOT NULL
        )
    """)
    cursor.execute("SELECT * FROM balance WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO balance VALUES (1, 1000000.0)")
    conn.commit()
    conn.close()

def place_virtual_trade(symbol: str, quantity: int, side: str,
                         stop_loss: float = None, target: float = None) -> dict:
    try:
        init_db()
        side = side.upper()
        if side not in ["BUY", "SELL"]:
            return {"error": "Side must be BUY or SELL"}
        price_data = get_live_price(symbol)
        if "error" in price_data:
            return {"error": f"Could not fetch price: {price_data['error']}"}
        current_price = price_data["price"]
        total_value = current_price * quantity
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT cash FROM balance WHERE id = 1")
        cash = cursor.fetchone()[0]
        if side == "BUY":
            if cash < total_value:
                conn.close()
                return {"error": f"Insufficient balance. Need ₹{total_value:.2f}, have ₹{cash:.2f}"}
            cursor.execute("UPDATE balance SET cash = cash - ? WHERE id = 1", (total_value,))
            cursor.execute("SELECT * FROM positions WHERE symbol = ?", (symbol.upper(),))
            existing = cursor.fetchone()
            if existing:
                old_qty = existing[2]
                old_price = existing[3]
                new_qty = old_qty + quantity
                new_avg = ((old_qty * old_price) + (quantity * current_price)) / new_qty
                cursor.execute("""
                    UPDATE positions
                    SET quantity = ?, avg_buy_price = ?, stop_loss = ?, target = ?
                    WHERE symbol = ?
                """, (new_qty, new_avg, stop_loss, target, symbol.upper()))
            else:
                cursor.execute("""
                    INSERT INTO positions (symbol, quantity, avg_buy_price, side, stop_loss, target, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol.upper(), quantity, current_price, side, stop_loss, target,
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        elif side == "SELL":
            cursor.execute("SELECT * FROM positions WHERE symbol = ?", (symbol.upper(),))
            existing = cursor.fetchone()
            if not existing:
                conn.close()
                return {"error": f"No position found for {symbol}"}
            if existing[2] < quantity:
                conn.close()
                return {"error": f"Not enough shares. Have {existing[2]}, trying to sell {quantity}"}
            cursor.execute("UPDATE balance SET cash = cash + ? WHERE id = 1", (total_value,))
            new_qty = existing[2] - quantity
            if new_qty == 0:
                cursor.execute("DELETE FROM positions WHERE symbol = ?", (symbol.upper(),))
            else:
                cursor.execute("UPDATE positions SET quantity = ? WHERE symbol = ?",
                             (new_qty, symbol.upper()))
        order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cursor.execute("""
            INSERT INTO trades (order_id, symbol, quantity, price, side, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (order_id, symbol.upper(), quantity, current_price, side, "EXECUTED",
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        cursor.execute("SELECT cash FROM balance WHERE id = 1")
        new_cash = cursor.fetchone()[0]
        conn.close()
        return {
            "order_id": order_id,
            "symbol": symbol.upper(),
            "side": side,
            "quantity": quantity,
            "price": current_price,
            "total_value": round(total_value, 2),
            "status": "EXECUTED",
            "remaining_cash": round(new_cash, 2),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {"error": str(e)}

def get_portfolio_pnl() -> dict:
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM positions")
        positions = cursor.fetchall()
        cursor.execute("SELECT cash FROM balance WHERE id = 1")
        cash = cursor.fetchone()[0]
        conn.close()
        if not positions:
            return {
                "positions": [],
                "total_invested": 0,
                "current_value": 0,
                "total_pnl": 0,
                "total_pnl_pct": 0,
                "cash_balance": round(cash, 2),
                "portfolio_value": round(cash, 2)
            }
        position_details = []
        total_invested = 0
        total_current = 0
        for pos in positions:
            symbol = pos[1]
            quantity = pos[2]
            avg_price = pos[3]
            stop_loss = pos[5]
            target = pos[6]
            price_data = get_live_price(symbol)
            current_price = price_data.get("price", avg_price)
            change_pct = price_data.get("change_pct", 0)
            invested = avg_price * quantity
            current_val = current_price * quantity
            pnl = current_val - invested
            pnl_pct = round((pnl / invested) * 100, 2) if invested > 0 else 0
            risk_score = min(100, abs(change_pct) * 10)
            alerts = []
            if stop_loss and current_price <= stop_loss:
                alerts.append(f"STOP LOSS HIT at ₹{stop_loss}")
            if target and current_price >= target:
                alerts.append(f"TARGET REACHED at ₹{target}")
            position_details.append({
                "symbol": symbol,
                "quantity": quantity,
                "avg_buy_price": round(avg_price, 2),
                "current_price": round(current_price, 2),
                "invested": round(invested, 2),
                "current_value": round(current_val, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": pnl_pct,
                "stop_loss": stop_loss,
                "target": target,
                "risk_score": round(risk_score, 1),
                "alerts": alerts
            })
            total_invested += invested
            total_current += current_val
        total_pnl = total_current - total_invested
        total_pnl_pct = round((total_pnl / total_invested) * 100, 2) if total_invested > 0 else 0
        return {
            "positions": position_details,
            "total_invested": round(total_invested, 2),
            "current_value": round(total_current, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": total_pnl_pct,
            "cash_balance": round(cash, 2),
            "portfolio_value": round(total_current + cash, 2)
        }
    except Exception as e:
        return {"error": str(e)}

def scan_market(filter_criteria: dict) -> dict:
    try:
        nifty50 = [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
            "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
            "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
            "TITAN", "BAJFINANCE", "WIPRO", "ULTRACEMCO", "NESTLEIND",
            "POWERGRID", "NTPC", "TECHM", "HCLTECH", "DRREDDY"
        ]
        min_price = filter_criteria.get("min_price", 0)
        max_price = filter_criteria.get("max_price", float('inf'))
        min_change = filter_criteria.get("min_change_pct", -float('inf'))
        max_change = filter_criteria.get("max_change_pct", float('inf'))
        matching = []
        for stock in nifty50:
            try:
                price_data = get_live_price(stock)
                if "error" in price_data:
                    continue
                price = price_data["price"]
                change_pct = price_data["change_pct"]
                if (min_price <= price <= max_price and
                    min_change <= change_pct <= max_change):
                    matching.append({
                        "symbol": stock,
                        "price": price,
                        "change_pct": change_pct,
                        "volume": price_data.get("volume", 0)
                    })
            except:
                continue
        matching.sort(key=lambda x: x["change_pct"], reverse=True)
        return {
            "filter_criteria": filter_criteria,
            "matches": matching,
            "total_matches": len(matching)
        }
    except Exception as e:
        return {"error": str(e)}