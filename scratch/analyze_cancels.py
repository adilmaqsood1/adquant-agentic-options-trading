import json
import os
from datetime import datetime
from collections import Counter

with open("scratch/alpaca_audit_data.json", "r", encoding="utf-8") as f:
    d = json.load(f)

cancels = d.get("canceled_orders", [])
print(f"Total Canceled Orders: {len(cancels)}")

time_diffs = []
cancels_by_symbol = Counter()
cancels_by_tif = Counter()
cancels_by_type = Counter()
time_buckets = {"< 1 min": 0, "1-5 min": 0, "5-15 min": 0, "15-30 min": 0, "30-60 min": 0, "> 60 min": 0}

for o in cancels:
    sym = o.get("symbol")
    cancels_by_symbol[sym] += 1
    cancels_by_tif[o.get("time_in_force")] += 1
    cancels_by_type[o.get("type")] += 1

    sub = o.get("submitted_at")
    can = o.get("canceled_at")
    if sub and can:
        t_sub = datetime.fromisoformat(sub.replace("Z", "+00:00"))
        t_can = datetime.fromisoformat(can.replace("Z", "+00:00"))
        diff_sec = (t_can - t_sub).total_seconds()
        time_diffs.append(diff_sec)
        
        diff_min = diff_sec / 60.0
        if diff_min < 1:
            time_buckets["< 1 min"] += 1
        elif diff_min < 5:
            time_buckets["1-5 min"] += 1
        elif diff_min < 15:
            time_buckets["5-15 min"] += 1
        elif diff_min < 30:
            time_buckets["15-30 min"] += 1
        elif diff_min < 60:
            time_buckets["30-60 min"] += 1
        else:
            time_buckets["> 60 min"] += 1

print("\n--- TIME TO CANCELLATION DISTRIBUTION ---")
for bucket, count in time_buckets.items():
    print(f"  {bucket:12s}: {count:3d} ({count/len(cancels)*100:.1f}%)")

if time_diffs:
    print(f"\nMin time before cancel: {min(time_diffs):.1f}s ({min(time_diffs)/60:.1f}m)")
    print(f"Max time before cancel: {max(time_diffs):.1f}s ({max(time_diffs)/60:.1f}m)")
    print(f"Median time before cancel: {sorted(time_diffs)[len(time_diffs)//2]:.1f}s ({sorted(time_diffs)[len(time_diffs)//2]/60:.1f}m)")
    print(f"Average time before cancel: {sum(time_diffs)/len(time_diffs):.1f}s ({sum(time_diffs)/len(time_diffs)/60:.1f}m)")

print("\n--- SAMPLE CANCELED ORDERS (FIRST 10) ---")
for o in cancels[:10]:
    sub = o.get("submitted_at", "")[:19]
    can = o.get("canceled_at", "")[:19]
    t_diff = None
    if o.get("submitted_at") and o.get("canceled_at"):
        t_sub = datetime.fromisoformat(o["submitted_at"].replace("Z", "+00:00"))
        t_can = datetime.fromisoformat(o["canceled_at"].replace("Z", "+00:00"))
        t_diff = f"{(t_can - t_sub).total_seconds():.0f}s"
    print(f"Symbol: {o.get('symbol'):22s} | Side: {o.get('side'):4s} | Limit: ${str(o.get('limit_price')):6s} | Sub: {sub} | Can: {can} | Duration: {t_diff}")

print("\n--- TOP CANCELED SYMBOLS ---")
for sym, cnt in cancels_by_symbol.most_common(8):
    print(f"  {sym:22s}: {cnt} cancels")
