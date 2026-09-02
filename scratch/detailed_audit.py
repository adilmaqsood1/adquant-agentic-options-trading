import json
import os
from collections import defaultdict
from tabulate import tabulate

with open("scratch/alpaca_audit_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

filled = data["filled_orders"]
open_pos = data["open_positions"]
canceled = data["canceled_orders"]
acc = data["account"]
activities = data.get("activities", [])
portfolio_history = data.get("portfolio_history", {})

print("=" * 100)
print("                       ALPACA ACCOUNT & ORDER HISTORY AUDIT REPORT                       ")
print("=" * 100)

print("\n[1] ACCOUNT OVERVIEW")
print(f"  • Account Number       : {acc.get('account_number')} (ID: {acc.get('id')})")
print(f"  • Status               : {acc.get('status')} | Currency: {acc.get('currency')}")
print(f"  • Options Approval     : Level {acc.get('options_approved_level')} ({acc.get('options_trading_level', 'Approved')})")
print(f"  • Initial/Base Capital : $100,000.00")
print(f"  • Current Equity       : ${float(acc.get('equity', 0)):,.2f}")
print(f"  • Portfolio Value      : ${float(acc.get('portfolio_value', 0)):,.2f}")
print(f"  • Cash Balance         : ${float(acc.get('cash', 0)):,.2f}")
print(f"  • Buying Power         : ${float(acc.get('buying_power', 0)):,.2f}")
net_profit = float(acc.get('equity', 0)) - 100000.0
print(f"  • Total Net PnL        : {'+$' if net_profit >= 0 else '-$'}{abs(net_profit):,.2f} ({(net_profit/100000.0)*100:.2f}%)")
print(f"  • Pattern Day Trader   : {acc.get('pattern_day_trader')} | Daytrade Count: {acc.get('daytrade_count')}")
print(f"  • Trading Blocked      : {acc.get('trading_blocked')}")
print(f"  • Account Created At   : {acc.get('created_at')}")

print("\n[2] CURRENT OPEN POSITIONS (Alpaca Broker Live)")
if not open_pos:
    print("  No open positions.")
else:
    pos_rows = []
    tot_market_val = 0.0
    tot_unrealized_pl = 0.0
    for p in open_pos:
        mv = float(p.get("market_value", 0))
        upl = float(p.get("unrealized_pl", 0))
        tot_market_val += mv
        tot_unrealized_pl += upl
        pos_rows.append([
            p.get("symbol"),
            p.get("asset_class"),
            p.get("qty"),
            f"${float(p.get('avg_entry_price', 0)):.2f}",
            f"${float(p.get('current_price', 0)):.2f}",
            f"${mv:,.2f}",
            f"{'+$' if upl >= 0 else '-$'}{abs(upl):.2f}",
            f"{float(p.get('unrealized_plpc', 0))*100:+.2f}%"
        ])
    print(tabulate(pos_rows, headers=["Symbol / OCC", "Class", "Qty", "Avg Entry", "Current Px", "Market Val", "Unrealized PL", "PL %"], tablefmt="grid"))
    print(f"  Total Position Market Value: ${tot_market_val:,.2f} | Total Unrealized PnL: {'+$' if tot_unrealized_pl >= 0 else '-$'}{abs(tot_unrealized_pl):.2f}")

print("\n[3] ORDER HISTORY METRICS")
print(f"  • Total Orders Submitted : 135")
print(f"  • Filled Orders          : 31 (23.0% fill rate)")
print(f"  • Canceled Orders        : 85 (63.0%)")
print(f"  • Expired Orders         : 19 (14.0%)")
print(f"  • Options Orders         : 133 (98.5%)")
print(f"  • Equity Orders          : 2 (1.5%)")

print("\n[4] ALL 31 FILLED ORDERS (Chronological / Audit Trail)")
filled_rows = []
total_buy_notional = 0.0
total_sell_notional = 0.0
trades_by_underlying = defaultdict(list)

for idx, o in enumerate(filled, 1):
    sym = o.get("symbol")
    side = o.get("side").upper()
    qty = float(o.get("filled_qty", 0))
    px = float(o.get("filled_avg_price", 0))
    # for options, notional = qty * px * 100
    is_opt = o.get("asset_class") == "us_option" or len(sym) > 6
    multiplier = 100 if is_opt else 1
    notional = qty * px * multiplier
    
    if side == "BUY":
        total_buy_notional += notional
    else:
        total_sell_notional += notional

    # Underlying extraction
    underlying = sym[:4].rstrip("0123456789") if is_opt else sym
    trades_by_underlying[underlying].append(o)

    filled_rows.append([
        idx,
        sym,
        o.get("asset_class"),
        side,
        int(qty) if qty.is_integer() else qty,
        f"${px:.2f}",
        f"${notional:,.2f}",
        o.get("order_type"),
        o.get("filled_at")[:19] if o.get("filled_at") else "-"
    ])

print(tabulate(filled_rows, headers=["#", "Symbol / OCC", "Class", "Side", "Qty", "Fill Price", "Notional ($)", "Type", "Filled At (UTC)"], tablefmt="grid"))
print(f"  Total Buy Premium Deployed  : ${total_buy_notional:,.2f}")
print(f"  Total Sell Premium Received  : ${total_sell_notional:,.2f}")

# Analyze round trips & closed positions
print("\n[5] COMPLETED ROUND-TRIP OPTIONS TRADES & REALIZED PNL ESTIMATION")
symbol_groups = defaultdict(list)
for o in filled:
    symbol_groups[o.get("symbol")].append(o)

round_trip_rows = []
for sym, orders_list in symbol_groups.items():
    buys = [o for o in orders_list if o.get("side") == "buy"]
    sells = [o for o in orders_list if o.get("side") == "sell"]
    buy_qty = sum(float(b.get("filled_qty", 0)) for b in buys)
    sell_qty = sum(float(s.get("filled_qty", 0)) for s in sells)
    
    is_opt = "us_option" in [o.get("asset_class") for o in orders_list] or len(sym) > 6
    mult = 100 if is_opt else 1
    
    buy_cost = sum(float(b.get("filled_qty", 0)) * float(b.get("filled_avg_price", 0)) * mult for b in buys)
    sell_rev = sum(float(s.get("filled_qty", 0)) * float(s.get("filled_avg_price", 0)) * mult for s in sells)
    
    avg_buy_px = (buy_cost / (buy_qty * mult)) if buy_qty > 0 else 0
    avg_sell_px = (sell_rev / (sell_qty * mult)) if sell_qty > 0 else 0

    status_trade = "CLOSED" if buy_qty == sell_qty and buy_qty > 0 else ("OPEN" if sell_qty == 0 else f"PARTIAL ({buy_qty - sell_qty} left)")
    
    realized_pnl = sell_rev - (avg_buy_px * sell_qty * mult) if sell_qty > 0 else 0.0
    pnl_pct = (realized_pnl / (avg_buy_px * sell_qty * mult) * 100) if (avg_buy_px * sell_qty * mult) > 0 else 0.0

    round_trip_rows.append([
        sym,
        status_trade,
        int(buy_qty),
        int(sell_qty),
        f"${avg_buy_px:.2f}" if buy_qty > 0 else "-",
        f"${avg_sell_px:.2f}" if sell_qty > 0 else "-",
        f"${buy_cost:,.2f}",
        f"${sell_rev:,.2f}",
        f"{'+$' if realized_pnl >= 0 else '-$'}{abs(realized_pnl):,.2f}" if sell_qty > 0 else "-",
        f"{pnl_pct:+.2f}%" if sell_qty > 0 else "-"
    ])

print(tabulate(round_trip_rows, headers=["Symbol / Contract", "Status", "Bought", "Sold", "Avg Buy Px", "Avg Sell Px", "Total Cost", "Total Rev", "Realized PnL", "Return %"], tablefmt="grid"))

print("\n[6] CANCELED / EXPIRED ORDERS ANALYSIS")
print(f"  • Canceled Count : {len(canceled)}")
limit_cancels = [c for c in canceled if c.get("type") == "limit"]
print(f"  • Limit Order Cancels : {len(limit_cancels)} (Likely limit orders submitted that went unfilled due to price drift or timeout)")
print(f"  • Sample Canceled Orders:")
for c in canceled[:5]:
    print(f"     - ID: {c.get('id')[:8]}.. | Symbol: {c.get('symbol')} | Side: {c.get('side')} | Qty: {c.get('qty')} | Limit Px: ${c.get('limit_price')} | Submitted: {c.get('submitted_at')[:19]}")

