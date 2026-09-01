import os, requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

headers = {
    'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY', ''),
    'APCA-API-SECRET-KEY': os.getenv('ALPACA_API_SECRET', '')
}
base_url = 'https://paper-api.alpaca.markets/v2'

r = requests.get(f'{base_url}/account/activities?activity_types=FILL&direction=asc', headers=headers)
fills = r.json() if r.status_code == 200 else []

trades_by_sym = {}
closed_trades = []

for f in fills:
    sym = f.get('symbol')
    side = f.get('side')
    qty = float(f.get('qty', 0))
    price = float(f.get('price', 0))
    t_time = f.get('transaction_time')
    
    if sym not in trades_by_sym:
        trades_by_sym[sym] = []
    trades_by_sym[sym].append({'side': side, 'qty': qty, 'price': price, 'time': t_time})

wins, losses = 0, 0
gross_profit, gross_loss = 0.0, 0.0
total_realized_pnl = 0.0

for sym, actions in trades_by_sym.items():
    buys = [a for a in actions if 'buy' in a['side']]
    sells = [a for a in actions if 'sell' in a['side']]
    if buys and sells:
        total_buy_qty = sum(b['qty'] for b in buys)
        total_sell_qty = sum(s['qty'] for s in sells)
        avg_buy = sum(b['price']*b['qty'] for b in buys) / total_buy_qty
        avg_sell = sum(s['price']*s['qty'] for s in sells) / total_sell_qty
        matched_qty = min(total_buy_qty, total_sell_qty)
        
        # Options have 100 multiplier
        multiplier = 100.0 if len(sym) > 6 else 1.0
        pnl = (avg_sell - avg_buy) * matched_qty * multiplier
        total_realized_pnl += pnl
        if pnl > 0:
            wins += 1
            gross_profit += pnl
        else:
            losses += 1
            gross_loss += abs(pnl)
        closed_trades.append({'symbol': sym, 'pnl': round(pnl, 2), 'buy': round(avg_buy, 2), 'sell': round(avg_sell, 2), 'qty': matched_qty})

total_trades = wins + losses
win_rate = round((wins / total_trades) * 100.0, 1) if total_trades > 0 else 0.0
pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (2.0 if gross_profit > 0 else 0.0)

print(f"Total Closed Trades: {total_trades}")
print(f"Wins: {wins} | Losses: {losses} | Win Rate: {win_rate}% | Profit Factor: {pf}")
print(f"Total Realized PnL: ${total_realized_pnl:,.2f}")
for ct in closed_trades:
    print(" ", ct)
