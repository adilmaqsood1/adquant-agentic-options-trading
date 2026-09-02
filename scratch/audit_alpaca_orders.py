import os
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict, Counter

load_dotenv()
api_key = os.getenv("ALPACA_API_KEY")
api_secret = os.getenv("ALPACA_API_SECRET")
base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2")

headers = {
    "APCA-API-KEY-ID": api_key,
    "APCA-API-SECRET-KEY": api_secret
}

client = httpx.Client(timeout=30.0, headers=headers)

# 1. Account
acc = client.get(f"{base_url}/account").json()

# 2. Orders (fetch all up to 500)
orders_resp = client.get(f"{base_url}/orders", params={"status": "all", "limit": 500, "nested": "true"})
orders = orders_resp.json() if orders_resp.status_code == 200 else []

# 3. Activities
activities_resp = client.get(f"{base_url}/account/activities", params={"page_size": 100})
activities = activities_resp.json() if activities_resp.status_code == 200 else []

# 4. Positions
pos_resp = client.get(f"{base_url}/positions")
positions = pos_resp.json() if pos_resp.status_code == 200 else []

# 5. Portfolio History (if available)
history_resp = client.get(f"{base_url}/account/portfolio/history", params={"period": "1M", "timeframe": "1D"})
portfolio_history = history_resp.json() if history_resp.status_code == 200 else {}

print(f"--- RAW DATA SUMMARY ---")
print(f"Account ID: {acc.get('id')} | Number: {acc.get('account_number')}")
print(f"Portfolio Value: ${float(acc.get('portfolio_value', 0)):,.2f} | Cash: ${float(acc.get('cash', 0)):,.2f}")
print(f"Total Orders: {len(orders)}")
print(f"Total Activities: {len(activities)}")
print(f"Total Open Positions: {len(positions)}")

# Analyze Orders
status_counts = Counter(o.get("status") for o in orders)
asset_class_counts = Counter(o.get("asset_class") for o in orders)
side_counts = Counter(o.get("side") for o in orders)
type_counts = Counter(o.get("type") for o in orders)

symbols_counter = Counter(o.get("symbol") for o in orders)

filled_orders = [o for o in orders if o.get("status") == "filled"]
canceled_orders = [o for o in orders if o.get("status") == "canceled"]
rejected_orders = [o for o in orders if o.get("status") in ["rejected", "stopped", "suspended"]]
open_orders = [o for o in orders if o.get("status") in ["new", "accepted", "pending_new", "accepted_for_bidding", "partially_filled"]]

print(f"\n--- ORDER STATUS BREAKDOWN ---")
for s, c in status_counts.items():
    print(f"  {s}: {c}")

print(f"\n--- ASSET CLASS BREAKDOWN ---")
for ac, c in asset_class_counts.items():
    print(f"  {ac}: {c}")

print(f"\n--- ORDER TYPE BREAKDOWN ---")
for ot, c in type_counts.items():
    print(f"  {ot}: {c}")

# Let's inspect filled orders in detail
print(f"\n--- FILLED ORDERS ({len(filled_orders)}) ---")
filled_summary = []
for o in sorted(filled_orders, key=lambda x: x.get("filled_at") or x.get("submitted_at") or "", reverse=True):
    filled_summary.append({
        "id": o.get("id"),
        "client_order_id": o.get("client_order_id"),
        "symbol": o.get("symbol"),
        "asset_class": o.get("asset_class"),
        "side": o.get("side"),
        "order_type": o.get("type"),
        "qty": o.get("qty") or o.get("filled_qty"),
        "filled_qty": o.get("filled_qty"),
        "filled_avg_price": o.get("filled_avg_price"),
        "notional_value": float(o.get("filled_qty", 0) or 0) * float(o.get("filled_avg_price", 0) or 0),
        "submitted_at": o.get("submitted_at"),
        "filled_at": o.get("filled_at"),
        "time_in_force": o.get("time_in_force"),
        "position_intent": o.get("position_intent")
    })

# Dump full data to a scratch json file for deep inspection
scratch_path = os.path.join(os.path.dirname(__file__), "alpaca_audit_data.json")
with open(scratch_path, "w", encoding="utf-8") as f:
    json.dump({
        "account": acc,
        "status_counts": status_counts,
        "asset_class_counts": asset_class_counts,
        "open_positions": positions,
        "filled_orders": filled_summary,
        "canceled_orders": canceled_orders,
        "rejected_orders": rejected_orders,
        "open_orders": open_orders,
        "activities": activities,
        "portfolio_history": portfolio_history,
        "all_orders_sample": orders[:20]
    }, f, indent=2, default=str)

print(f"\nAudit data saved to {scratch_path}")
