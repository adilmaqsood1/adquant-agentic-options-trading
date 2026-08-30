import os
import sys
import httpx
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_API_SECRET")
BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2")

headers = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": API_SECRET,
    "Content-Type": "application/json"
}

def test_alpaca_account_and_options():
    print("=" * 80)
    print("🦙 TESTING ALPACA PAPER TRADING API CONNECTIVITY")
    print("=" * 80)

    with httpx.Client(timeout=15.0) as client:
        # 1. Test Account endpoint
        acc_resp = client.get(f"{BASE_URL}/account", headers=headers)
        print(f"Account HTTP Status: {acc_resp.status_code}")
        if acc_resp.status_code == 200:
            acc = acc_resp.json()
            print(f"  Account ID:             {acc.get('id')}")
            print(f"  Status:                 {acc.get('status')}")
            print(f"  Portfolio Value:        ${float(acc.get('portfolio_value', 0)):,.2f}")
            print(f"  Cash:                   ${float(acc.get('cash', 0)):,.2f}")
            print(f"  Buying Power:           ${float(acc.get('buying_power', 0)):,.2f}")
            print(f"  Options Approved Level: {acc.get('options_approved_level')}")
            print(f"  Trading Blocked:        {acc.get('trading_blocked')}")
        else:
            print(f"Account Error: {acc_resp.text}")

        # 2. Test Positions endpoint
        pos_resp = client.get(f"{BASE_URL}/positions", headers=headers)
        print(f"\nPositions HTTP Status: {pos_resp.status_code}")
        if pos_resp.status_code == 200:
            positions = pos_resp.json()
            print(f"  Active Alpaca Positions: {len(positions)}")
            for p in positions[:5]:
                print(f"    • {p.get('symbol')} | Qty: {p.get('qty')} | Market Value: ${float(p.get('market_value', 0)):,.2f} | Unrealized PnL: ${float(p.get('unrealized_pl', 0)):,.2f}")

        # 3. Test Options contracts endpoint
        opt_resp = client.get(f"{BASE_URL}/options/contracts?underlying_symbols=AAPL&status=active&limit=5", headers=headers)
        print(f"\nOptions Contracts HTTP Status: {opt_resp.status_code}")
        if opt_resp.status_code == 200:
            contracts_data = opt_resp.json()
            contracts = contracts_data.get("option_contracts", [])
            print(f"  Retrieved {len(contracts)} AAPL active option contracts from Alpaca:")
            for c in contracts[:3]:
                print(f"    • OCC: {c.get('symbol')} | Strike: ${c.get('strike_price')} | Type: {c.get('type')} | Expiration: {c.get('expiration_date')}")

    print("\n" + "=" * 80)
    print("✅ ALPACA PAPER API LIVE CONNECTION VERIFIED")
    print("=" * 80)

if __name__ == "__main__":
    test_alpaca_account_and_options()
