import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ALPACA_API_KEY")
api_secret = os.getenv("ALPACA_API_SECRET")
base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2")

headers = {
    "APCA-API-KEY-ID": api_key,
    "APCA-API-SECRET-KEY": api_secret,
    "Content-Type": "application/json"
}

with httpx.Client(timeout=15.0) as client:
    # 1. Account Summary
    acc_resp = client.get(f"{base_url}/account", headers=headers)
    acc = acc_resp.json() if acc_resp.status_code == 200 else {"error": acc_resp.text}
    
    # 2. Open Positions
    pos_resp = client.get(f"{base_url}/positions", headers=headers)
    pos = pos_resp.json() if pos_resp.status_code == 200 else []
    
    # 3. Recent Orders
    orders_resp = client.get(f"{base_url}/orders?status=all&limit=100", headers=headers)
    orders = orders_resp.json() if orders_resp.status_code == 200 else []

print("=== ACCOUNT SUMMARY ===")
print(f"Account ID: {acc.get('id')}")
print(f"Status: {acc.get('status')}")
print(f"Currency: {acc.get('currency')}")
print(f"Equity: ${float(acc.get('equity', 0)):,.2f}")
print(f"Cash: ${float(acc.get('cash', 0)):,.2f}")
print(f"Buying Power: ${float(acc.get('buying_power', 0)):,.2f}")
print(f"Portfolio Value: ${float(acc.get('portfolio_value', 0)):,.2f}")
print(f"Options Buying Power: ${float(acc.get('options_buying_power', 0)):,.2f}")
print(f"Options Level: {acc.get('options_approved_level')}")

print("\n=== OPEN POSITIONS ===")
print(f"Total Open Positions: {len(pos)}")
total_unrealized_pnl = 0.0
for p in pos:
    sym = p.get('symbol')
    qty = p.get('qty')
    avg_entry = float(p.get('avg_entry_price', 0))
    current_price = float(p.get('current_price', 0))
    market_val = float(p.get('market_value', 0))
    unrealized_pl = float(p.get('unrealized_pl', 0))
    unrealized_plpc = float(p.get('unrealized_plpc', 0)) * 100.0
    total_unrealized_pnl += unrealized_pl
    print(f"- {sym}: {qty} contracts/shares @ ${avg_entry:.2f} -> Current: ${current_price:.2f} | Mkt Val: ${market_val:,.2f} | Unrealized PnL: ${unrealized_pl:,.2f} ({unrealized_plpc:+.2f}%)")

print(f"\nNet Unrealized P&L Across Open Positions: ${total_unrealized_pnl:,.2f}")

filled_orders = [o for o in orders if o.get('status') == 'filled']
open_orders = [o for o in orders if o.get('status') in ['new', 'accepted', 'pending_new', 'partially_filled']]
canceled_orders = [o for o in orders if o.get('status') in ['canceled', 'expired', 'rejected']]

print(f"\n=== ORDER ACTIVITY BREAKDOWN (Last 100 Orders) ===")
print(f"Total Orders Evaluated: {len(orders)}")
print(f"Filled Executions: {len(filled_orders)}")
print(f"Working / Pending Limit Orders: {len(open_orders)}")
print(f"Canceled / Expired Orders: {len(canceled_orders)}")

print("\n--- Working / Open Orders ---")
for o in open_orders:
    print(f"- {o.get('symbol')} | {o.get('side').upper()} {o.get('qty')} @ ${o.get('limit_price')} | Status: {o.get('status')} | Submitted: {o.get('submitted_at')}")

print("\n--- Recent Filled Orders ---")
for o in filled_orders[:10]:
    print(f"- {o.get('symbol')} | {o.get('side').upper()} {o.get('qty')} @ Avg ${o.get('filled_avg_price')} | Value: ${float(o.get('qty', 0))*float(o.get('filled_avg_price', 0)):,.2f} | Filled: {o.get('filled_at')}")
