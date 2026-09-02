import json
from collections import defaultdict

with open("scratch/alpaca_audit_data.json", "r", encoding="utf-8") as f:
    d = json.load(f)

cancels = d.get("canceled_orders", [])
cancel_times = defaultdict(list)
for o in cancels:
    can = o.get("canceled_at", "")[:19]
    cancel_times[can].append(o)

print("CANCELLATION BATCHES:")
for t, ords in sorted(cancel_times.items(), key=lambda x: len(x[1]), reverse=True):
    print(f"Timestamp: {t} -> {len(ords)} orders canceled in batch")
    sample = ords[0]
    print(f"   Example: {sample.get('symbol')} (sub at {sample.get('submitted_at')[:19]}, limit ${sample.get('limit_price')})")
