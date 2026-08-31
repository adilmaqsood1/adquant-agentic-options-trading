from app.engine.opportunity_ranker import detect_confluence_opportunities, rank_opportunities_tournament

mock_signals = [
    {'symbol': 'AAPL', 'strategy_id': 'momentum_ema_rsi_adx', 'confidence': 88, 'last_close': 225.0, 'signal_type': 'BUY'},
    {'symbol': 'AAPL', 'strategy_id': 'liquidity_sweep_absorption', 'confidence': 92, 'last_close': 225.0, 'signal_type': 'BUY'},
    {'symbol': 'NVDA', 'strategy_id': 'momentum_ema_rsi_adx', 'confidence': 84, 'last_close': 128.0, 'signal_type': 'BUY'},
    {'symbol': 'TSLA', 'strategy_id': 'lead_lag_propagation', 'confidence': 80, 'last_close': 210.0, 'signal_type': 'BUY'},
    {'symbol': 'NVDA', 'strategy_id': 'lead_lag_propagation', 'confidence': 89, 'last_close': 128.0, 'signal_type': 'BUY'},
    {'symbol': 'NVDA', 'strategy_id': 'liquidity_sweep_absorption', 'confidence': 94, 'last_close': 128.0, 'signal_type': 'BUY'}
]

pool = detect_confluence_opportunities(mock_signals)
print("=== CONFLUENCE POOL ===")
for c in pool:
    print(f"  {c['symbol']}: {c['confluence_tier']} ({c['confluence_count']} strategies) -> Composite Score: {c['composite_conviction']}%")

tourney = rank_opportunities_tournament(pool, available_capacity=2)
print("\n=== TOURNAMENT WINNERS SELECTED FOR EXECUTION ===")
for item in tourney['selected_for_execution']:
    print(f"  Rank #{item['rank']}: {item['symbol']} | Tier: {item['confluence_tier']} | Score: {item['tournament_score']}%")
    print(f"    Action: {item['recommended_action']}")
    print(f"    Reasoning: {item['rationale']}")
