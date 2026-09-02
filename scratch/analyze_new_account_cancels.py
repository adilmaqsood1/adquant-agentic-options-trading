import json
from datetime import datetime
from collections import defaultdict
from tabulate import tabulate

with open("scratch/current_account_data.json", "r", encoding="utf-8") as f:
    d = json.load(f)

orders = d["orders"]
cancels = d["canceled_orders"]
filled = d["filled_orders"]
positions = d["positions"]

print("=" * 100)
print("                       NEW ACCOUNT TRADES & CANCEL AUDIT                       ")
print("=" * 100)

print(f"\nAccount ID: {d['account']['id']} | Number: {d['account']['account_number']}")
print(f"Equity/Portfolio: ${float(d['account']['portfolio_value']):,.2f} | Cash: ${float(d['account']['cash']):,.2f}")

print("\n[1] OPEN POSITIONS:")
for p in positions:
    print(f"  - {p.get('symbol')} ({p.get('side')} {p.get('qty')}) | Avg Entry: ${p.get('avg_entry_price')} | Current: ${p.get('current_price')} | Unrealized PL: ${p.get('unrealized_pl')}")

print("\n[2] FILLED ORDERS (2):")
for f_ord in filled:
    print(f"  - {f_ord.get('symbol')} | Side: {f_ord.get('side')} | Qty: {f_ord.get('filled_qty')} | Fill Price: ${f_ord.get('filled_avg_price')} | Type: {f_ord.get('type')} | Submitted: {f_ord.get('submitted_at')} | Filled: {f_ord.get('filled_at')}")

print("\n[3] ALL 18 CANCELED ORDERS IN DETAIL:")
cancel_rows = []
for idx, o in enumerate(cancels, 1):
    sub = o.get("submitted_at")
    can = o.get("canceled_at")
    dur = ""
    if sub and can:
        t_sub = datetime.fromisoformat(sub.replace("Z", "+00:00"))
        t_can = datetime.fromisoformat(can.replace("Z", "+00:00"))
        dur = f"{(t_can - t_sub).total_seconds():.0f}s ({(t_can - t_sub).total_seconds()/60:.1f}m)"

    cancel_rows.append([
        idx,
        o.get("symbol"),
        o.get("side").upper(),
        o.get("qty"),
        f"${float(o.get('limit_price') or 0):.2f}",
        o.get("type"),
        sub[:19] if sub else "-",
        can[:19] if can else "-",
        dur
    ])

print(tabulate(cancel_rows, headers=["#", "Symbol / OCC", "Side", "Qty", "Limit Px", "Type", "Submitted (UTC)", "Canceled (UTC)", "Duration"], tablefmt="grid"))

# Check cancellation timestamps for batches
cancel_times = defaultdict(list)
for o in cancels:
    can_time = o.get("canceled_at", "")[:19]
    cancel_times[can_time].append(o)

print("\n[4] CANCELLATION BATCHES:")
for ct, ords in sorted(cancel_times.items(), key=lambda x: x[0]):
    print(f"  At {ct} UTC: {len(ords)} orders canceled simultaneously:")
    for o in ords:
        print(f"     -> {o.get('symbol')} (Limit: ${o.get('limit_price')}, Sub: {o.get('submitted_at')[:19]})")
