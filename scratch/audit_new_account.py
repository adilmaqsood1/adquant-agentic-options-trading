import os
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv
from collections import Counter, defaultdict

load_dotenv(override=True)
api_key = os.getenv("ALPACA_API_KEY")
api_secret = os.getenv("ALPACA_API_SECRET")
base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2").rstrip("/")

headers = {
    "APCA-API-KEY-ID": api_key,
    "APCA-API-SECRET-KEY": api_secret
}

client = httpx.Client(timeout=30.0, headers=headers)

# 1. Account
acc = client.get(f"{base_url}/account").json()

# 2. Orders (all)
orders_resp = client.get(f"{base_url}/orders", params={"status": "all", "limit": 500, "nested": "true"})
orders = orders_resp.json() if orders_resp.status_code == 200 else []

# 3. Activities
activities_resp = client.get(f"{base_url}/account/activities", params={"page_size": 100})
activities = activities_resp.json() if activities_resp.status_code == 200 else []

# 4. Positions
pos_resp = client.get(f"{base_url}/positions")
positions = pos_resp.json() if pos_resp.status_code == 200 else []

print("=" * 80)
print(f"ACCOUNT: {acc.get('account_number')} (ID: {acc.get('id')})")
print(f"Status: {acc.get('status')} | Cash: ${float(acc.get('cash', 0)):,.2f} | Portfolio Value: ${float(acc.get('portfolio_value', 0)):,.2f}")
print(f"Total Orders: {len(orders)}")
print(f"Total Positions: {len(positions)}")
print(f"Total Activities: {len(activities)}")

status_counts = Counter(o.get("status") for o in orders)
print("\nOrder Statuses:")
for s, c in status_counts.items():
    print(f"  {s}: {c}")

canceled_orders = [o for o in orders if o.get("status") == "canceled"]
filled_orders = [o for o in orders if o.get("status") == "filled"]

print(f"\nTotal Canceled: {len(canceled_orders)}")
print(f"Total Filled: {len(filled_orders)}")

# Save to scratch for deep analysis
with open("scratch/current_account_data.json", "w", encoding="utf-8") as f:
    json.dump({
        "account": acc,
        "orders": orders,
        "canceled_orders": canceled_orders,
        "filled_orders": filled_orders,
        "positions": positions,
        "activities": activities
    }, f, indent=2, default=str)

print("\nDetailed data written to scratch/current_account_data.json")
