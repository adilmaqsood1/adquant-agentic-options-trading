import sys
import os
import json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agents.consensus_agent import evaluate_asset_consensus

def display_desk_deliberation(symbol: str):
    res = evaluate_asset_consensus(symbol)
    tp = res["trade_parameters"]
    perf = res["resulting_performance"]
    opt = res.get("options_contract")
    
    print("\n" + "═" * 65)
    print(f" LIVE AGENT DECISION DESK: {res['symbol']}")
    print("═" * 65)
    
    for agent_key, a in res["agents"].items():
        name = agent_key.replace("_", " ").title()
        vote = a.get("vote")
        conf = f"{a.get('confidence')}%" if "confidence" in a else ("APPROVED ✓" if a.get("approved") else "REJECTED ✗")
        print(f"  {name:18s} {vote:10s}  {conf}")
        
    print("─" * 65)
    print(f"  CONSENSUS          {res['consensus']['decision']:10s}  {res['consensus']['overall_confidence']}%")
    print("─" * 65)
    print(f"  Underlying Spot:   ${tp['entry_price']:,.2f}")
    print(f"  Position Size:     {tp['position_size']}")
    print(f"  Stop Loss:         ${tp['stop_loss']:,.2f}")
    print(f"  Target:            ${tp['target_price']:,.2f}")
    print(f"  Risk:              {tp['risk_pct']}%  •  R/R: {tp['reward_risk_ratio']:.2f}")

    if opt:
        g = opt["greeks"]
        print("─" * 65)
        print("  🎯 SELECTED OPTIONS CONTRACT (IN-THE-MONEY ~0.70 DELTA)")
        print("─" * 65)
        print(f"  OCC Symbol:        {opt['option_symbol']}")
        print(f"  Contract Type:     {opt['option_type'].upper()}  •  Strike: ${opt['strike_price']:,.2f}")
        print(f"  Expiration:        {opt['expiration_date']} ({opt['dte']} DTE)")
        print(f"  Premium:           ${opt['contract_premium']:,.2f} ($ {opt['cost_per_contract']:,.2f}/contract)")
        print(f"  Contracts:         {opt['contracts']} ({opt['contracts']*100} shares leverage)")
        print(f"  Greeks:            Delta: {g['delta']} | Gamma: {g['gamma']} | Theta: {g['theta']} | IV: {g['iv']}%")
        print(f"  Breakeven / Lev:   ${opt['breakeven_price']:,.2f}  •  {opt['leverage_multiplier']:.1f}x Leverage")

    print("═" * 65)
    print("  RESULTING PnL & EXECUTION PERFORMANCE")
    print("═" * 65)
    print(f"  Status:            {perf['status']}")
    if perf['is_live_position']:
        pnl_sign = "+" if perf['unrealized_pnl'] >= 0 else ""
        print(f"  Live Unrealized:   {pnl_sign}${perf['unrealized_pnl']:,.2f} ({pnl_sign}{perf['unrealized_pnl_pct']:.2f}%)")
        print(f"  Entry vs Live:     ${perf['entry_price']:,.2f}  →  ${perf['current_price']:,.2f}")
        print(f"  Target Progress:   {perf['target_progress_pct']}% toward 2.0 R/R Target")
    else:
        print(f"  Projected Target:  +${perf['projected_target_profit']:,.2f} (at Target ${tp['target_price']:,.2f})")
        print(f"  Max Stop Risk:     -${perf['max_stop_risk']:,.2f} (at Stop ${tp['stop_loss']:,.2f})")
    print("═" * 65)

print("=" * 65)
print("TESTING CONSENSUS DESK WITH INTEGRATED OPTIONS CONTRACTS")
print("=" * 65)

# Test Equity with Options Selection
display_desk_deliberation('AAPL')
display_desk_deliberation('TEAM')
display_desk_deliberation('SOL/USD')
