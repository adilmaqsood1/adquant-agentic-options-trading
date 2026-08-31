import os
import sys
import time
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from data.alpaca_source import (
    submit_alpaca_equity_order,
    submit_alpaca_option_order,
    submit_alpaca_close_position
)
from app.mcp.alpaca_tools import get_account_summary

def test_alpaca_order_bridge():
    print("=" * 80)
    print("🦙 TESTING LIVE ALPACA ORDER EXECUTION BRIDGE")
    print("=" * 80)

    # 1. Fetch Account
    print("\n1. Fetching live Alpaca paper account...")
    acc = get_account_summary()
    print(f"  Account Status: {acc.get('status')}")
    print(f"  Portfolio Value: ${acc.get('portfolio_value', 0):,.2f}")
    print(f"  Buying Power:    ${acc.get('buying_power', 0):,.2f}")

    # 2. Test Spot Stock Order Submission (1 share of SPY / AAPL)
    print("\n2. Submitting spot paper order: 1 share of SPY...")
    spot_res = submit_alpaca_equity_order(symbol="SPY", qty=1, side="buy", order_type="market")
    print(f"  Spot Order Success: {spot_res.get('success')}")
    if spot_res.get("success"):
        print(f"  Order ID: {spot_res.get('order_id')}")
        print(f"  Status:   {spot_res.get('status')}")
    else:
        print(f"  Spot Error: {spot_res.get('error')}")

    # 3. Test Options Order Submission
    print("\n3. Testing options paper order submission on OCC symbol...")
    # Fetch active contract OCC symbol from Alpaca
    try:
        import httpx
        from app.core.config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL
        headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_API_SECRET}
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{ALPACA_BASE_URL}/options/contracts?underlying_symbols=SPY&status=active&limit=1", headers=headers)
            if resp.status_code == 200:
                contracts = resp.json().get("option_contracts", [])
                if contracts:
                    test_occ = contracts[0].get("symbol")
                    print(f"  Found active OCC contract: {test_occ}")
                    opt_res = submit_alpaca_option_order(
                        occ_symbol=test_occ,
                        contracts_qty=1,
                        side="buy",
                        order_type="market",
                        position_intent="buy_to_open"
                    )
                    print(f"  Options Order Success: {opt_res.get('success')}")
                    if opt_res.get("success"):
                        print(f"  Order ID: {opt_res.get('order_id')}")
                        print(f"  Status:   {opt_res.get('status')}")
                    else:
                        print(f"  Option Order Note: {opt_res.get('error')}")
    except Exception as e:
        print("  Options test note:", e)

    # 4. Clean up / Close SPY position
    print("\n4. Cleaning up paper test position on SPY...")
    time.sleep(2)
    close_res = submit_alpaca_close_position(symbol_or_occ="SPY")
    print(f"  Close Status: {close_res.get('success')} (Status: {close_res.get('status', 'OK')})")

    print("\n" + "=" * 80)
    print("✅ ALPACA LIVE ORDER EXECUTION BRIDGE TEST COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    test_alpaca_order_bridge()
