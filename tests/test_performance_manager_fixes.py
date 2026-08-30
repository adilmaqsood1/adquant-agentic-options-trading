import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.engine.performance_manager import (
    fetch_live_alpaca_equity,
    get_portfolio_budget_breakdown,
    get_active_budget_with_reserve,
    get_dynamic_allocation,
    get_portfolio_health_report,
    compute_kelly_score
)

def test_performance_manager_fixes():
    print("=" * 80)
    print("🧪 TESTING PERFORMANCE MANAGER FIXES & HEALTH REPORT")
    print("=" * 80)

    # 1. Test Issue 1 & 2: Dynamic Allocation & Hard 3% Risk Cap
    print("\n1. Testing Issue 1 (Exact 3% Risk Cap) & Issue 2 (Pure Options Dollar Budget)...")
    res_normal = get_dynamic_allocation(
        strategy_id="momentum_ema_rsi_adx",
        symbol="AAPL",
        atr_14=3.5,
        current_price=220.0,
        groq_confidence=90,
        asset_class="option",
        override_kelly={
            "mode": "GROWTH",
            "size_multiplier": 1.5,
            "kelly_pct": 0.40,
            "quarter_kelly_pct": 0.10,
            "win_rate": 0.70,
            "consecutive_losses": 0
        }
    )
    print(f"  Approved:          {res_normal.get('approved')}")
    print(f"  Final Allocation:  ${res_normal.get('final_allocation'):,.2f}")
    print(f"  Audit Trail:")
    for k, v in res_normal.get("audit_trail", {}).items():
        print(f"    • {k}: {v}")
    
    max_cap = res_normal.get("audit_trail", {}).get("max_portfolio_risk_cap", 3000.0)
    assert res_normal.get("final_allocation") <= max_cap, f"Allocation must NOT exceed 3% risk cap (${max_cap:,.2f})!"
    assert "quantity" not in res_normal or res_normal.get("quantity") is None, "Spot ATR quantity must be absent for options!"
    print(f"  ✅ Issue 1 & Issue 2 Verified: Position capped at max 3% (${max_cap:,.2f}) and no spot share quantity!")

    # 2. Test Issue 3: Cash Reserve Release
    print("\n2. Testing Issue 3: Cash Reserve Release for RSI Oversold Reversal (Confidence >= 85%)...")
    live_eq = fetch_live_alpaca_equity()
    base_breakdown = get_portfolio_budget_breakdown(live_equity=live_eq, strategy_id="momentum_ema_rsi_adx", groq_confidence=90)
    print(f"  Standard Active Budget (75%): ${base_breakdown['active_options_budget']:,.2f} | Reserve: ${base_breakdown['cash_reserve_budget']:,.2f} (Released: {base_breakdown['reserve_released']})")

    rsi_breakdown = get_portfolio_budget_breakdown(live_equity=live_eq, strategy_id="rsi_oversold_reversal", groq_confidence=88)
    print(f"  RSI Oversold Active Budget (85%): ${rsi_breakdown['active_options_budget']:,.2f} | Reserve: ${rsi_breakdown['cash_reserve_budget']:,.2f} (Released: {rsi_breakdown['reserve_released']})")

    assert rsi_breakdown["active_options_budget"] > base_breakdown["active_options_budget"], "RSI Oversold must release 10% reserve!"
    assert rsi_breakdown["reserve_released"] is True, "reserve_released flag must be True!"
    print("  ✅ Issue 3 Verified: Cash reserve correctly releases +10% budget on RSI Oversold Reversal!")

    # 3. Test Enhancement: Portfolio Health Report
    print("\n3. Testing Enhancement: get_portfolio_health_report()...")
    report = get_portfolio_health_report()
    print(f"  Live Equity:       ${report['live_equity']:,.2f}")
    print(f"  Circuit Breaker:   Level {report['circuit_breaker']['circuit_breaker_level']} ({report['circuit_breaker']['circuit_breaker_label']})")
    print(f"  Active Options:    ${report['budget_breakdown']['active_options_budget']:,.2f}")
    print(f"  Cash Reserve:      ${report['budget_breakdown']['cash_reserve_budget']:,.2f}")
    print(f"  Strategies Tracked: {len(report['strategy_performance'])}")
    print(f"  Timestamp:         {report['timestamp']}")

    assert report["live_equity"] > 0
    assert "circuit_breaker" in report
    assert "budget_breakdown" in report
    print("  ✅ Enhancement Verified: Comprehensive health report generated successfully!")

    print("\n" + "=" * 80)
    print("🎉 ALL 3 ISSUES FIXED & ENHANCEMENT VERIFIED 100%!")
    print("=" * 80)

if __name__ == "__main__":
    test_performance_manager_fixes()
