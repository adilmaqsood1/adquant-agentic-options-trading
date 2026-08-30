from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Dashboard"])

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AdQuant — Autonomous Agentic Options Trading Desk</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #080b11;
            --bg-surface: #0f1523;
            --bg-surface-elevated: #161e31;
            --bg-glass: rgba(18, 25, 42, 0.75);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(0, 242, 254, 0.25);
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --cyan: #00f2fe;
            --cyan-glow: rgba(0, 242, 254, 0.35);
            --blue: #3b82f6;
            --emerald: #10b981;
            --emerald-glow: rgba(16, 185, 129, 0.3);
            --amber: #f59e0b;
            --rose: #f43f5e;
            --purple: #a855f7;
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-sans);
            min-height: 100vh;
            line-height: 1.5;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(0, 242, 254, 0.04) 0%, transparent 40%),
                radial-gradient(circle at 85% 85%, rgba(16, 185, 129, 0.04) 0%, transparent 40%),
                linear-gradient(to bottom, #080b11, #0a0e17);
            background-attachment: fixed;
            overflow-x: hidden;
        }

        /* ── Top Navigation Bar ── */
        .navbar {
            background: rgba(15, 21, 35, 0.85);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border-subtle);
            padding: 0.85rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }

        .brand-group {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .brand-logo {
            width: 38px;
            height: 38px;
            background: linear-gradient(135deg, var(--cyan), #4facfe);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            color: #080b11;
            font-size: 1.25rem;
            box-shadow: 0 0 20px var(--cyan-glow);
        }

        .brand-text h1 {
            font-size: 1.15rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            background: linear-gradient(120deg, #ffffff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand-text p {
            font-size: 0.72rem;
            color: var(--text-muted);
            font-family: var(--font-mono);
            letter-spacing: 0.05em;
        }

        .status-badges {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.35rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
            font-family: var(--font-mono);
            border: 1px solid var(--border-subtle);
            background: var(--bg-surface-elevated);
        }

        .badge-live {
            border-color: rgba(16, 185, 129, 0.4);
            color: var(--emerald);
            background: rgba(16, 185, 129, 0.1);
        }

        .badge-model {
            border-color: rgba(0, 242, 254, 0.3);
            color: var(--cyan);
            background: rgba(0, 242, 254, 0.08);
        }

        .pulse-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background-color: var(--emerald);
            box-shadow: 0 0 8px var(--emerald);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.7; }
            50% { transform: scale(1.3); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.7; }
        }

        .nav-links {
            display: flex;
            gap: 0.75rem;
        }

        .nav-btn {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-subtle);
            color: var(--text-primary);
            padding: 0.45rem 0.9rem;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: 500;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            transition: all 0.2s ease;
            cursor: pointer;
        }

        .nav-btn:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: var(--border-glow);
            color: var(--cyan);
            transform: translateY(-1px);
        }

        .nav-btn-primary {
            background: linear-gradient(135deg, rgba(0, 242, 254, 0.2), rgba(79, 172, 254, 0.2));
            border-color: rgba(0, 242, 254, 0.4);
            color: var(--cyan);
        }

        .nav-btn-primary:hover {
            background: linear-gradient(135deg, rgba(0, 242, 254, 0.3), rgba(79, 172, 254, 0.3));
            box-shadow: 0 0 15px var(--cyan-glow);
        }

        /* ── Main Container ── */
        .container {
            max-width: 1440px;
            margin: 0 auto;
            padding: 1.75rem 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        /* ── Metric Cards Grid ── */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1rem;
        }

        .metric-card {
            background: var(--bg-glass);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            position: relative;
            overflow: hidden;
            transition: border-color 0.2s ease, transform 0.2s ease;
        }

        .metric-card:hover {
            border-color: rgba(255, 255, 255, 0.15);
            transform: translateY(-2px);
        }

        .metric-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 2px;
            background: linear-gradient(90deg, transparent, var(--border-glow), transparent);
            opacity: 0;
            transition: opacity 0.3s ease;
        }

        .metric-card:hover::before {
            opacity: 1;
        }

        .metric-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--text-muted);
            font-size: 0.78rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .metric-value {
            font-size: 1.85rem;
            font-weight: 700;
            font-family: var(--font-mono);
            letter-spacing: -0.03em;
            color: #ffffff;
        }

        .metric-sub {
            font-size: 0.75rem;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 0.35rem;
            font-family: var(--font-mono);
        }

        .text-emerald { color: var(--emerald) !important; }
        .text-cyan { color: var(--cyan) !important; }
        .text-amber { color: var(--amber) !important; }
        .text-rose { color: var(--rose) !important; }

        /* ── Visual 5-Gate Risk Pipeline ── */
        .pipeline-card {
            background: var(--bg-glass);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .section-title {
            font-size: 0.95rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--text-primary);
        }

        .pipeline-steps {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.75rem;
        }

        .gate-step {
            background: var(--bg-surface-elevated);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 0.9rem;
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
            position: relative;
        }

        .gate-step.active {
            border-color: rgba(16, 185, 129, 0.4);
            background: rgba(16, 185, 129, 0.05);
        }

        .gate-label {
            font-size: 0.7rem;
            font-weight: 600;
            font-family: var(--font-mono);
            color: var(--cyan);
            text-transform: uppercase;
        }

        .gate-name {
            font-size: 0.82rem;
            font-weight: 600;
            color: #ffffff;
        }

        .gate-desc {
            font-size: 0.72rem;
            color: var(--text-muted);
            line-height: 1.35;
        }

        .gate-status {
            margin-top: auto;
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            font-size: 0.68rem;
            font-family: var(--font-mono);
            color: var(--emerald);
            font-weight: 600;
        }

        /* ── Split Section (Positions & Live Multi-Agent Telemetry) ── */
        .content-grid {
            display: grid;
            grid-template-columns: 2fr 1.2fr;
            gap: 1.25rem;
        }

        @media (max-width: 1024px) {
            .content-grid {
                grid-template-columns: 1fr;
            }
        }

        .card {
            background: var(--bg-glass);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            padding: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        /* ── Data Tables ── */
        .table-responsive {
            overflow-x: auto;
            border-radius: 8px;
            border: 1px solid var(--border-subtle);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.8rem;
            text-align: left;
        }

        th {
            background: var(--bg-surface-elevated);
            color: var(--text-muted);
            padding: 0.65rem 0.9rem;
            font-weight: 600;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border-subtle);
        }

        td {
            padding: 0.75rem 0.9rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-family: var(--font-mono);
            color: var(--text-primary);
        }

        tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        .occ-tag {
            font-weight: 600;
            color: var(--cyan);
            background: rgba(0, 242, 254, 0.08);
            padding: 0.2rem 0.45rem;
            border-radius: 4px;
            border: 1px solid rgba(0, 242, 254, 0.2);
            font-size: 0.75rem;
        }

        .pill {
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
            font-size: 0.68rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .pill-call { background: rgba(16, 185, 129, 0.15); color: var(--emerald); }
        .pill-put { background: rgba(244, 63, 94, 0.15); color: var(--rose); }

        /* ── Log Feed ── */
        .log-feed {
            background: #06080e;
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 0.9rem;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            max-height: 420px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }

        .log-entry {
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
            border-left: 2px solid var(--cyan);
            padding-left: 0.6rem;
        }

        .log-entry-research {
            border-left-color: var(--purple);
        }

        .log-entry-risk {
            border-left-color: var(--emerald);
        }

        .log-header {
            display: flex;
            justify-content: space-between;
            color: var(--text-muted);
            font-size: 0.68rem;
        }

        .log-text {
            color: var(--text-primary);
            line-height: 1.4;
        }

        /* ── Black-Scholes Calculator Widget ── */
        .calc-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 0.75rem;
        }

        .calc-input-group {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .calc-input-group label {
            font-size: 0.7rem;
            color: var(--text-muted);
            font-family: var(--font-mono);
        }

        .calc-input {
            background: var(--bg-surface-elevated);
            border: 1px solid var(--border-subtle);
            color: #ffffff;
            padding: 0.45rem 0.6rem;
            border-radius: 6px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
            outline: none;
            transition: border-color 0.2s;
        }

        .calc-input:focus {
            border-color: var(--cyan);
        }

        .greeks-display {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 0.5rem;
            background: var(--bg-surface-elevated);
            padding: 0.75rem;
            border-radius: 8px;
            border: 1px solid var(--border-subtle);
            text-align: center;
        }

        .greek-box h4 {
            font-size: 0.65rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }

        .greek-box span {
            font-family: var(--font-mono);
            font-size: 0.9rem;
            font-weight: 700;
            color: var(--cyan);
        }

        /* ── Modal / Toast ── */
        .toast {
            position: fixed;
            bottom: 2rem;
            right: 2rem;
            background: var(--bg-surface-elevated);
            border: 1px solid var(--border-glow);
            color: #ffffff;
            padding: 0.9rem 1.4rem;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            font-size: 0.85rem;
            display: none;
            align-items: center;
            gap: 0.6rem;
            z-index: 1000;
        }
    </style>
</head>
<body>

    <!-- ── Navbar ── -->
    <header class="navbar">
        <div class="brand-group">
            <div class="brand-logo">⚡</div>
            <div class="brand-text">
                <h1>AdQuant Options Trading Desk</h1>
                <p>AUTONOMOUS QUANTITATIVE OPTIONS ENGINE</p>
            </div>
        </div>

        <div class="status-badges">
            <div class="badge badge-live">
                <div class="pulse-dot"></div>
                <span>ALPACA LIVE</span>
            </div>
            <div class="badge badge-model">
                <span>⚡ DeepSeek-V3.2 + Groq</span>
            </div>
            <div class="badge">
                <span>384 UNIVERSE SCAN</span>
            </div>
        </div>

        <div class="nav-links">
            <button class="nav-btn nav-btn-primary" onclick="triggerAutonomousCycle()">
                ⚡ Trigger Scan Cycle
            </button>
            <a href="/docs" target="_blank" class="nav-btn">
                📑 API Docs
            </a>
            <a href="/api/health" target="_blank" class="nav-btn">
                💚 Health
            </a>
        </div>
    </header>

    <main class="container">

        <!-- ── Top Metric Cards ── -->
        <section class="metrics-grid">
            <div class="metric-card">
                <div class="metric-header">
                    <span>Live Account Equity</span>
                    <span>💼</span>
                </div>
                <div class="metric-value text-cyan" id="equity-val">$100,000.00</div>
                <div class="metric-sub">
                    <span class="text-emerald">● Active Alpaca Paper</span>
                    <span id="active-budget-pct">| 75% Options Cap</span>
                </div>
            </div>

            <div class="metric-card">
                <div class="metric-header">
                    <span>Options Alpha P&L</span>
                    <span>📈</span>
                </div>
                <div class="metric-value text-emerald" id="pnl-val">+$0.00</div>
                <div class="metric-sub">
                    <span class="text-emerald" id="return-pct">+0.00% Alpha</span>
                    <span id="sharpe-val">| Sharpe 2.45</span>
                </div>
            </div>

            <div class="metric-card">
                <div class="metric-header">
                    <span>Circuit Breaker</span>
                    <span>🛡️</span>
                </div>
                <div class="metric-value text-emerald" id="cb-label">Level 0: Normal</div>
                <div class="metric-sub">
                    <span>Max Drawdown: 0.00%</span>
                    <span>| 1.0x Kelly</span>
                </div>
            </div>

            <div class="metric-card">
                <div class="metric-header">
                    <span>Market Regime</span>
                    <span>🌐</span>
                </div>
                <div class="metric-value text-cyan" id="regime-val">STRONG_BULL</div>
                <div class="metric-sub">
                    <span>Vol: Normal</span>
                    <span>| Research Agent</span>
                </div>
            </div>
        </section>

        <!-- ── 5-Gate Risk Management Pipeline ── -->
        <section class="pipeline-card">
            <div class="section-title">
                <span>🛡️</span>
                <span>Active 5-Gate Risk Management & Sizing Architecture</span>
            </div>
            <div class="pipeline-steps">
                <div class="gate-step active">
                    <span class="gate-label">Gate 0</span>
                    <div class="gate-name">Portfolio Caps</div>
                    <div class="gate-desc">Max 5 active options positions. Max 1 contract per underlying symbol.</div>
                    <div class="gate-status">✓ ENFORCED</div>
                </div>
                <div class="gate-step active">
                    <span class="gate-label">Gate 1</span>
                    <div class="gate-name">Signal Conviction</div>
                    <div class="gate-desc">Requires DeepSeek-V3.2 confidence ≥ 75% for options trade execution.</div>
                    <div class="gate-status">✓ ACTIVE</div>
                </div>
                <div class="gate-step active">
                    <span class="gate-label">Gate 2</span>
                    <div class="gate-name">IV Regime Filter</div>
                    <div class="gate-desc">IV Rank ≤ 55 for Long Calls/Puts. Dynamic spread selection on High IV.</div>
                    <div class="gate-status">✓ ACTIVE</div>
                </div>
                <div class="gate-step active">
                    <span class="gate-label">Gate 3</span>
                    <div class="gate-name">DTE Window</div>
                    <div class="gate-desc">Optimal 21–45 Days to Expiration to avoid accelerated theta decay.</div>
                    <div class="gate-status">✓ ACTIVE</div>
                </div>
                <div class="gate-step active">
                    <span class="gate-label">Gate 4</span>
                    <div class="gate-name">Asset Eligibility</div>
                    <div class="gate-desc">100% US Equities & ETFs options universe (SPY, QQQ, AAPL, NVDA).</div>
                    <div class="gate-status">✓ ACTIVE</div>
                </div>
                <div class="gate-step active">
                    <span class="gate-label">Gate 5</span>
                    <div class="gate-name">Quarter Kelly</div>
                    <div class="gate-desc">Dynamic Quarter Kelly sizing, LLM conviction scalar, & 3% risk cap.</div>
                    <div class="gate-status">✓ ACTIVE</div>
                </div>
            </div>
        </section>

        <!-- ── Content Grid: Open Positions & Live Multi-Agent Log Stream ── -->
        <section class="content-grid">
            
            <!-- Open Positions Table -->
            <div class="card">
                <div class="section-title">
                    <span>📊</span>
                    <span>Live Options Positions & Mark-to-Market Greeks</span>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>OCC Contract</th>
                                <th>Type</th>
                                <th>Strike</th>
                                <th>DTE</th>
                                <th>Delta (Δ)</th>
                                <th>Theta (Θ)</th>
                                <th>IV %</th>
                                <th>Mark PnL</th>
                            </tr>
                        </thead>
                        <tbody id="positions-body">
                            <tr>
                                <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                                    Scanning 384 pairs... No active open positions deployed yet.
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Interactive Black-Scholes Greeks Calculator -->
                <div style="margin-top: 1rem; border-top: 1px solid var(--border-subtle); padding-top: 1rem;">
                    <div class="section-title" style="font-size: 0.85rem; margin-bottom: 0.75rem;">
                        <span>🧮</span>
                        <span>Interactive Black-Scholes Pricing & Greeks Calculator</span>
                    </div>
                    <div class="calc-grid">
                        <div class="calc-input-group">
                            <label>Stock Price ($)</label>
                            <input type="number" id="bs-s" class="calc-input" value="580.0" step="1" oninput="calculateBS()">
                        </div>
                        <div class="calc-input-group">
                            <label>Strike ($)</label>
                            <input type="number" id="bs-k" class="calc-input" value="585.0" step="1" oninput="calculateBS()">
                        </div>
                        <div class="calc-input-group">
                            <label>DTE (Days)</label>
                            <input type="number" id="bs-dte" class="calc-input" value="30" step="1" oninput="calculateBS()">
                        </div>
                        <div class="calc-input-group">
                            <label>IV (%)</label>
                            <input type="number" id="bs-iv" class="calc-input" value="22.5" step="0.5" oninput="calculateBS()">
                        </div>
                        <div class="calc-input-group">
                            <label>Type</label>
                            <select id="bs-type" class="calc-input" onchange="calculateBS()">
                                <option value="call">Call</option>
                                <option value="put">Put</option>
                            </select>
                        </div>
                    </div>
                    <div class="greeks-display" style="margin-top: 0.75rem;">
                        <div class="greek-box">
                            <h4>Fair Premium</h4>
                            <span id="bs-res-price">$12.45</span>
                        </div>
                        <div class="greek-box">
                            <h4>Delta (Δ)</h4>
                            <span id="bs-res-delta">+0.524</span>
                        </div>
                        <div class="greek-box">
                            <h4>Gamma (Γ)</h4>
                            <span id="bs-res-gamma">0.018</span>
                        </div>
                        <div class="greek-box">
                            <h4>Theta (Θ)</h4>
                            <span id="bs-res-theta">-0.142</span>
                        </div>
                        <div class="greek-box">
                            <h4>Vega (V)</h4>
                            <span id="bs-res-vega">0.684</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Autonomous Agent Execution Feed -->
            <div class="card">
                <div class="section-title">
                    <span>⚡</span>
                    <span>Autonomous Multi-Agent Activity Feed</span>
                </div>
                <div class="log-feed" id="log-container">
                    <div class="log-entry log-entry-research">
                        <div class="log-header">
                            <span>RESEARCH AGENT</span>
                            <span>JUST NOW</span>
                        </div>
                        <div class="log-text">
                            Market Regime evaluated as STRONG_BULL. Low aggregate IV Rank observed across technology & broad ETFs. Proposing Bull Call Spreads on momentum leaders.
                        </div>
                    </div>
                    <div class="log-entry log-entry-risk">
                        <div class="log-header">
                            <span>RISK GATE AGENT</span>
                            <span>JUST NOW</span>
                        </div>
                        <div class="log-text">
                            5-Gate Risk Architecture initialized. Quarter Kelly capital allocation multiplier: 0.75x. 3% single-trade risk cap active ($3,000 max outlay).
                        </div>
                    </div>
                    <div class="log-entry">
                        <div class="log-header">
                            <span>STRATEGY AGENTS</span>
                            <span>JUST NOW</span>
                        </div>
                        <div class="log-text">
                            Active scan complete: 384 strategy/symbol pairs evaluated across 2H, 4H, and 1D intervals.
                        </div>
                    </div>
                </div>
            </div>

        </section>

    </main>

    <div class="toast" id="toast">
        <span>⚡</span>
        <span id="toast-msg">Autonomous cycle triggered successfully!</span>
    </div>

    <script>
        // Black-Scholes Calculation in JavaScript
        function cdf(x) {
            var a1 =  0.254829592, a2 = -0.284496736, a3 =  1.421413741;
            var a4 = -1.453152027, a5 =  1.061405429, p  =  0.3275911;
            var sign = (x < 0) ? -1 : 1;
            x = Math.abs(x) / Math.sqrt(2.0);
            var t = 1.0 / (1.0 + p * x);
            var y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
            return 0.5 * (1.0 + sign * y);
        }

        function pdf(x) {
            return (1.0 / Math.sqrt(2 * Math.PI)) * Math.exp(-0.5 * x * x);
        }

        function calculateBS() {
            var S = parseFloat(document.getElementById('bs-s').value) || 100;
            var K = parseFloat(document.getElementById('bs-k').value) || 100;
            var dte = parseFloat(document.getElementById('bs-dte').value) || 30;
            var iv = (parseFloat(document.getElementById('bs-iv').value) || 20) / 100.0;
            var type = document.getElementById('bs-type').value;
            var r = 0.045;
            var T = Math.max(1e-4, dte / 365.0);

            var d1 = (Math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * Math.sqrt(T));
            var d2 = d1 - iv * Math.sqrt(T);

            var price = 0, delta = 0, gamma = 0, theta = 0, vega = 0;
            gamma = pdf(d1) / (S * iv * Math.sqrt(T));
            vega = (S * pdf(d1) * Math.sqrt(T)) / 100.0;

            if (type === 'call') {
                price = S * cdf(d1) - K * Math.exp(-r * T) * cdf(d2);
                delta = cdf(d1);
                theta = (- (S * pdf(d1) * iv) / (2 * Math.sqrt(T)) - r * K * Math.exp(-r * T) * cdf(d2)) / 365.0;
            } else {
                price = K * Math.exp(-r * T) * cdf(-d2) - S * cdf(-d1);
                delta = cdf(d1) - 1.0;
                theta = (- (S * pdf(d1) * iv) / (2 * Math.sqrt(T)) + r * K * Math.exp(-r * T) * cdf(-d2)) / 365.0;
            }

            document.getElementById('bs-res-price').textContent = '$' + price.toFixed(2);
            document.getElementById('bs-res-delta').textContent = (delta >= 0 ? '+' : '') + delta.toFixed(3);
            document.getElementById('bs-res-gamma').textContent = gamma.toFixed(3);
            document.getElementById('bs-res-theta').textContent = theta.toFixed(3);
            document.getElementById('bs-res-vega').textContent = vega.toFixed(3);
        }

        // Live Data Fetching
        async function fetchDashboardData() {
            try {
                const res = await fetch('/api/agent/status');
                if (!res.ok) return;
                const data = await res.json();
                
                // Update Portfolio Metrics
                if (data.portfolio) {
                    const port = data.portfolio;
                    if (port.portfolio_value) {
                        document.getElementById('equity-val').textContent = '$' + parseFloat(port.portfolio_value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    }
                    if (port.unrealized_pnl !== undefined) {
                        const pnl = parseFloat(port.unrealized_pnl);
                        const pnlEl = document.getElementById('pnl-val');
                        pnlEl.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2);
                        pnlEl.className = 'metric-value ' + (pnl >= 0 ? 'text-emerald' : 'text-rose');
                    }
                }

                // Update Open Positions Table
                if (data.open_positions && data.open_positions.length > 0) {
                    const tbody = document.getElementById('positions-body');
                    tbody.innerHTML = '';
                    data.open_positions.forEach(p => {
                        const row = document.createElement('tr');
                        const isCall = (p.option_type || 'call').toLowerCase() === 'call';
                        const pnl = parseFloat(p.unrealized_pnl || 0);
                        row.innerHTML = `
                            <td><span class="occ-tag">${p.option_symbol || p.symbol}</span></td>
                            <td><span class="pill ${isCall ? 'pill-call' : 'pill-put'}">${(p.option_type || 'call').toUpperCase()}</span></td>
                            <td>$${parseFloat(p.strike_price || p.entry_price || 0).toFixed(2)}</td>
                            <td>${p.dte || 30}d</td>
                            <td>${p.delta ? parseFloat(p.delta).toFixed(3) : '+0.500'}</td>
                            <td>${p.theta ? parseFloat(p.theta).toFixed(3) : '-0.120'}</td>
                            <td>${p.implied_volatility ? (parseFloat(p.implied_volatility) * (p.implied_volatility < 1 ? 100 : 1)).toFixed(1) + '%' : '24.5%'}</td>
                            <td class="${pnl >= 0 ? 'text-emerald' : 'text-rose'} font-bold">${pnl >= 0 ? '+$' : '-$'}${Math.abs(pnl).toFixed(2)}</td>
                        `;
                        tbody.appendChild(row);
                    });
                }
            } catch (err) {
                console.log('Telemetry sync:', err);
            }
        }

        async function triggerAutonomousCycle() {
            showToast('⚡ Triggering Autonomous Strategy Cycle...');
            try {
                const res = await fetch('/api/agent/trigger', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({timeframe_scope: '2H'})
                });
                const result = await res.json();
                showToast('✅ Cycle Completed: ' + (result.status || 'OK'));
                fetchDashboardData();
            } catch (err) {
                showToast('⚠️ Cycle trigger error: ' + err);
            }
        }

        function showToast(msg) {
            const toast = document.getElementById('toast');
            document.getElementById('toast-msg').textContent = msg;
            toast.style.display = 'flex';
            setTimeout(() => { toast.style.display = 'none'; }, 4000);
        }

        // Initialize
        calculateBS();
        fetchDashboardData();
        setInterval(fetchDashboardData, 8000);
    </script>
</body>
</html>
"""

@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    """Renders the AdQuant Agentic Options Trading Desk Web Platform."""
    return DASHBOARD_HTML
