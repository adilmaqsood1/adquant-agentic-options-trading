import os, sys, json, asyncio
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app.routers.dashboard_router import get_rrg_data

async def main():
    res = await get_rrg_data()
    body = json.loads(res.body.decode('utf-8'))
    symbols = body.get('symbols', [])
    print(f"RRG Endpoint returned {len(symbols)} symbols:")
    for s in symbols:
        print(f"Symbol: {s.get('symbol')} | OCC: {s.get('contract_symbol')} | Quadrant: {s.get('quadrant')} | RS-Ratio: {s.get('rs_ratio')} | RS-Momentum: {s.get('rs_momentum')}")

asyncio.run(main())
