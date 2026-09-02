import os, httpx, dotenv
dotenv.load_dotenv()
headers = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_API_SECRET')}
symbols = ['ORCL261002C00143000', 'DLR261002C00180000', 'EXC261016C00042000']
for sym in symbols:
    r = httpx.get(f'https://data.alpaca.markets/v1beta1/options/snapshots?symbols={sym}', headers=headers)
    snap = r.json().get('snapshots', {}).get(sym, {})
    q = snap.get('latestQuote', {})
    bp = q.get('bp')
    ap = q.get('ap')
    delta = snap.get('greeks', {}).get('delta')
    print(f"{sym} -> Live Market Bid: ${bp} | Ask: ${ap} | Delta: {delta}")
