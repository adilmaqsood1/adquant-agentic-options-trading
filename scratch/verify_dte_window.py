import os
import datetime
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

today = datetime.date(2026, 9, 1)

with httpx.Client(timeout=15.0) as client:
    orders_resp = client.get(f"{base_url}/orders?status=open", headers=headers)
    orders = orders_resp.json() if orders_resp.status_code == 200 else []

print(f"=== OCC SYMBOL & DTE VERIFICATION (Reference Date: {today}) ===\n")

all_valid = True
for idx, o in enumerate(orders, 1):
    occ = o.get("symbol")
    side = o.get("side").upper()
    qty = o.get("qty")
    limit_px = float(o.get("limit_price", 0))
    
    # Format: [ROOT][YYMMDD][C/P][STRIKE*1000]
    # Find C or P (the option type separator)
    type_idx = -1
    for i in range(len(occ) - 9, len(occ) - 8 + 1):
        if occ[i] in ['C', 'P']:
            type_idx = i
            break
            
    if type_idx == -1:
        type_idx = occ.rfind('C') if 'C' in occ else occ.rfind('P')
        
    underlying = occ[:type_idx-6]
    date_str = occ[type_idx-6:type_idx]
    opt_type = "CALL" if occ[type_idx] == "C" else "PUT"
    strike_str = occ[type_idx+1:]
    strike = float(strike_str) / 1000.0 if strike_str.isdigit() else 0.0
    
    exp_year = int("20" + date_str[0:2])
    exp_month = int(date_str[2:4])
    exp_day = int(date_str[4:6])
    exp_date = datetime.date(exp_year, exp_month, exp_day)
    
    dte = (exp_date - today).days
    is_in_window = 21 <= dte <= 45
    if not is_in_window:
        all_valid = False
        
    status_str = "PASS (21-45 DTE)" if is_in_window else "FAIL (Out of window)"
    
    print(f"{idx}. OCC: {occ}")
    print(f"   Ticker: {underlying} | Type: {opt_type} | Strike: ${strike:.2f}")
    print(f"   Expiration: {exp_date} | DTE: {dte} Days | Status: [{status_str}]")
    print(f"   Order: {side} {qty} contract(s) @ Limit ${limit_px:.2f} | Committed: ${float(qty)*limit_px*100:,.2f}\n")

print("----------------------------------------------------------------------")
print(f"FINAL AUDIT VERIFICATION: {'ALL 8 ORDERS 100% VALID IN 21-45 DTE WINDOW' if all_valid and len(orders) == 8 else 'VERIFICATION FAILED'}")
print("----------------------------------------------------------------------")
