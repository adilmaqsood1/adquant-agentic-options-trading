# ⚡ AdQuant — Agentic Options Trading

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Alpaca API](https://img.shields.io/badge/Alpaca-Options%20API%20v2-yellow.svg)](https://alpaca.markets)
[![MCP Protocol](https://img.shields.io/badge/MCP-FastMCP%20%7C%20JSON--RPC-purple.svg)](https://modelcontextprotocol.io)
[![DeepSeek-V3.2](https://img.shields.io/badge/LLM-Featherless%20DeepSeek--V3.2-indigo.svg)](https://featherless.ai)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)](https://www.postgresql.org/)
[![Validation](https://img.shields.io/badge/Tests-32%2F32%20Passed%20(100%25)-success.svg)](tests/test_full_system_validation.py)

An institutional-grade, multi-agent AI quantitative options trading platform built on the **Alpaca Trading API**, **Model Context Protocol (MCP)**, **FastAPI Cloud**, and **Featherless DeepSeek-V3.2**.

---

## 📑 Table of Contents

- [Architectural Overview](#-architectural-overview)
- [System Flowchart](#-system-flowchart)
- [Core Innovation & Features](#-core-innovation--features)
- [Repository Structure](#-repository-structure)
- [Quick Start Guide (Local Setup)](#-quick-start-guide-local-setup)
- [Production Cloud Deployment](#-production-cloud-deployment)
  - [Deploy on FastAPI Cloud / Deta Space](#1-deploy-on-fastapi-cloud--deta-space)
  - [Deploy with Docker / Render / Railway](#2-deploy-with-docker--render--railway)
- [Interactive CLI Console (`alpaca_cli.py`)](#-interactive-cli-console-alpacaclipy)
- [Model Context Protocol Server (`mcp_server.py`)](#-model-context-protocol-server-mcpserverpy)
- [Automated 5-Gate Risk & 4-Exit Management](#-automated-5-gate-risk--4-exit-management)
- [Validation & Test Suite](#-validation--test-suite)

---

## 🏛️ Architectural Overview

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             MARKET DATA INGESTION                                │
│        Alpaca Market Data API (Live 1D, 4H, 2H Bars) across Optionable Universe  │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                       LAYER 1: DATA & CONTEXT ENGINE                             │
│ • Data Agent: 12 Technical Indicators (RSI, ADX, Supertrend, ATR, BB Squeeze)   │
│ • Market Context Agent: Fear & Greed Index, yfinance Fundamentals, VADER Sentiment│
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   LAYER 2 & 3: ALPHA DETECTION & RESEARCH                        │
│ • Strategy Micro-Agents: 20+ Quants with Options Suitability Evaluation          │
│ • Research Agent (DeepSeek-V3.2): Regime Detection & Novel Options Strategies    │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│               LAYER 4: BLACK-SCHOLES GREEKS & REASONING AGENT                    │
│ • Contract Selector: Strike selection (Delta ~0.70, 21-45 DTE, Spreads)          │
│ • Reasoning Agent (DeepSeek-V3.2): Multi-factor Go/No-Go Reasoning + Sizing      │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   LAYER 5: 5-GATE DYNAMIC RISK & PORTFOLIO ENGINE                │
│ • 5 Gates: Portfolio Limits, Quality, IV Regime, DTE Window, Dynamic Sizing      │
│ • Performance Manager: Quarter Kelly × 5-Level Circuit Breakers × LLM Scalar     │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                      LAYER 6: BROKER EXECUTION & MONITOR                         │
│ • MCP stdio Client & Options Executor: Live Alpaca Paper Trading Orders          │
│ • 4-Exit Options Monitor: +60% Target, -35% Stop, 14 DTE Time Stop, CB Liquidate │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 System Flowchart

```mermaid
flowchart TD
    A[Alpaca Market Data API] --> B[market_state.py]
    B --> C[data_agent.py]
    C --> D[FeatureSnapshot Cache]
    
    E[Fear & Greed / yfinance / VADER] --> F[market_context_agent.py]
    F --> G[LLM Context Injector]
    
    D --> H[strategy_agents.py]
    G --> H
    H -->|Fired Signals| I[contract_selector.py]
    
    D --> J[research_agent.py]
    J -->|DeepSeek-V3.2| K[Market Regime & Novel Strategies]
    
    I -->|OCC Contract & Greeks| L[reasoning_agent.py]
    G --> L
    L -->|Approved Signals| M[risk_gate_agent.py]
    
    N[performance_manager.py] -->|Quarter Kelly & Circuit Breaker| M
    M -->|Approved Order| O[execution_router.py]
    
    O -->|Slippage < 15%| P[mcp_client.py]
    P --> Q[options_executor.py]
    Q --> R[Alpaca Paper Trading Account]
    
    R --> S[PostgreSQL DB]
    S --> T[options_monitor_agent.py]
    T -->|Auto 4-Exit| Q
    
    K --> U[email_reporter.py]
    O --> U
    U --> V[Gmail SMTP Dispatched]
```

---

## 💡 Core Innovation & Features

1. **100% Options Mandate**:
   - Operates strictly in listed US equity options (Calls, Puts, Bull Call Spreads) on liquid underlyings (`AAPL`, `NVDA`, `SPY`, `QQQ`, `MSFT`, `AMZN`, etc.).
   - Analytical **Black-Scholes engine** computing $\Delta, \Gamma, \Theta, \text{Vega}, \rho$ and Implied Volatility surfaces.
2. **Dual-Model Autonomous Reasoning**:
   - **Primary LLM**: **Featherless DeepSeek-V3.2** (`deepseek-ai/DeepSeek-V3.2`).
   - **Secondary Failover**: **Groq API** with automatic fallback handling.
   - Dedicated reasoning protocols enforcing options suitability (IV rank, theta burn, trend clarity, and momentum sustainability).
3. **Dynamic Capital Management & 5-Level Circuit Breaker**:
   - Active Capital (\$75,000) / Reserve Lock (\$25,000) split.
   - **Quarter Kelly Criterion** sizing based on closed trade history.
   - 5-Tier Drawdown Circuit Breakers (Green $\to$ Yellow $\to$ Orange $\to$ Red $\to$ Black Shutdown).
4. **Alpaca Model Context Protocol (MCP)**:
   - Standalone MCP server (`mcp_server.py`) exposing 7 quantitative trading tools via FastMCP and stdio JSON-RPC 2.0.
5. **Human Operator CLI (`alpaca_cli.py`)**:
   - Rich terminal interface for account metrics, Greeks inspection, manual trades, and monitoring.

---

## 📁 Repository Structure

```text
Alpaca_AI_Trading/
├── backend/
│   ├── app/
│   │   ├── agents/               # Autonomous Multi-Agent Hierarchy
│   │   │   ├── consensus_agent.py        # Multi-agent voting committee
│   │   │   ├── data_agent.py             # 12 technical indicators & feature cache
│   │   │   ├── market_context_agent.py   # FNG index, fundamentals & VADER news
│   │   │   ├── reasoning_agent.py        # DeepSeek-V3.2 risk reasoning analyst
│   │   │   ├── research_agent.py         # Creative Layer 3 research analyst
│   │   │   ├── risk_agent.py             # Initial duplicate & parameter gate
│   │   │   └── strategy_agents.py        # 20+ quant micro-agents
│   │   ├── core/
│   │   │   └── database.py               # PostgreSQL pool & SQLAlchemy models
│   │   ├── engine/               # Pricing, Risk & Sizing Engine
│   │   │   ├── contract_selector.py      # Delta 0.70 & DTE 21-45 contract builder
│   │   │   ├── options_monitor_agent.py  # 4-Exit automated risk monitor
│   │   │   ├── options_position_manager.py # Position CRUD & mark-to-market
│   │   │   ├── options_pricing.py        # Black-Scholes Greeks engine
│   │   │   ├── performance_manager.py    # Kelly sizing & circuit breakers
│   │   │   └── risk_gate_agent.py        # 5-Gate risk validation
│   │   ├── execution/            # Broker & MCP Execution Layer
│   │   │   ├── execution_router.py       # Pre-trade slippage & gate routing
│   │   │   ├── mcp_client.py             # Subprocess stdio JSON-RPC MCP client
│   │   │   └── options_executor.py       # Live Alpaca options order submitter
│   │   ├── mcp/
│   │   │   └── alpaca_tools.py           # Shared tools registry for MCP and CLI
│   │   ├── reporting/
│   │   │   └── email_reporter.py         # Automated HTML cycle reporting & SMTP
│   │   ├── routers/
│   │   │   ├── agent_router.py           # FastAPI routes for agents & live state
│   │   │   └── backtest.py               # Backtesting REST endpoints
│   │   └── services/
│   │       ├── llm_client.py             # Featherless + Groq dual-model client
│   │       ├── market_state.py           # Multi-asset bar ingestion & caching
│   │       ├── orchestrator.py           # Master LangGraph pipeline StateGraph
│   │       └── signal_detector.py        # Vectorized quantitative alpha rules
│   ├── tests/
│   │   └── test_full_system_validation.py # Master 32-test 12-block validation suite
│   ├── alpaca_cli.py             # Command Line Interface console
│   ├── mcp_server.py             # FastMCP & JSON-RPC 2.0 stdio server
│   ├── main.py                   # FastAPI REST API application
│   ├── scheduler.py              # Background APScheduler daemon
│   ├── Dockerfile                # Production multi-stage Dockerfile
│   ├── requirements.txt          # Production Python dependencies
│   ├── .env.example              # Environment variables template
│   └── .dockerignore             # Docker build ignores
├── supabase_schema.sql           # Complete PostgreSQL DDL & indexes
└── README.md                     # Project documentation
```

---

## 🚀 Quick Start Guide (Local Setup)

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 14+ or Supabase account
- Alpaca Paper Trading Account (API Key + Secret)
- Featherless AI API Key (DeepSeek-V3.2) and/or Groq API Key

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/your-username/Alpaca_AI_Trading.git
cd Alpaca_AI_Trading/backend

# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create `.env` inside `backend/`:

```bash
cp .env.example .env
```

Fill in your credentials in `.env`:
```ini
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_API_SECRET=your_alpaca_api_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

FEATHERLESS_API_KEY=your_featherless_api_key
FEATHERLESS_MODEL=deepseek-ai/DeepSeek-V3.2
GROQ_API_KEY=your_groq_api_key

DATABASE_URL=postgresql://postgres:password@localhost:5432/alpaca_trading
ALERT_EMAIL=your_email@example.com
```

### 4. Run the Backend REST API Server

```bash
python main.py
```
*The FastAPI application starts on `http://localhost:8000`. Swagger API docs are available at `http://localhost:8000/docs`.*

---

## ☁️ Production Cloud Deployment

### 1. Deploy on FastAPI Cloud / Deta Space

1. **Install FastAPI Cloud / Space CLI**:
   ```bash
   pip install space-cli  # or use FastAPI Cloud Dashboard
   ```
2. **Configure Environment Secrets**:
   Add all keys from `.env.example` into your Cloud Dashboard Environment settings (`ALPACA_API_KEY`, `FEATHERLESS_API_KEY`, `DATABASE_URL`, etc.).
3. **Launch**:
   ```bash
   cd backend
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

### 2. Deploy with Docker / Render / Railway / Fly.io

The included multi-stage [`backend/Dockerfile`](backend/Dockerfile) is production-optimized:

```bash
# Build the Docker container
cd backend
docker build -t alpaca-ai-options-desk .

# Run container with environment variables
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name options-trading-desk \
  alpaca-ai-options-desk
```

#### One-Click Render / Railway Configuration:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path**: `/api/health`

---

## 💻 Interactive CLI Console (`alpaca_cli.py`)

Interact directly with the options desk from your terminal:

```bash
# 1. View live account status & Level 3 options approval
python alpaca_cli.py account

# 2. View active positions with Black-Scholes Greeks
python alpaca_cli.py positions

# 3. Inspect analytical Greeks and strike selection for any symbol
python alpaca_cli.py inspect NVDA

# 4. Check Circuit Breaker level & Quarter Kelly sizing
python alpaca_cli.py circuit-breaker

# 5. Submit an autonomous quantitative trade
python alpaca_cli.py trade --symbol AAPL --strategy long_call --confidence 85

# 6. Run the 4-Exit automated monitor
python alpaca_cli.py monitor

# 7. Run a multi-strategy market scan
python alpaca_cli.py scan --timeframe 2H
```

---

## 🔌 Model Context Protocol Server (`mcp_server.py`)

The platform includes a built-in MCP server that enables external AI agents (Claude Desktop, Cursor, Antigravity) to control the options desk via standard JSON-RPC tools.

### Adding to Claude Desktop / Cursor Config (`mcp_config.json`):

```json
{
  "mcpServers": {
    "alpaca-options-desk": {
      "command": "python",
      "args": ["c:/path/to/Alpaca_AI_Trading/backend/mcp_server.py"],
      "env": {
        "ALPACA_API_KEY": "your_alpaca_key",
        "ALPACA_API_SECRET": "your_alpaca_secret",
        "DATABASE_URL": "postgresql://..."
      }
    }
  }
}
```

### Registered MCP Tools:
- `alpaca_get_account`: Live account balance & options buying power.
- `alpaca_get_positions`: Open options positions with live Greeks.
- `alpaca_inspect_option`: Evaluates strike, DTE, Greeks, and 5-Gate checks.
- `alpaca_get_circuit_breaker_status`: 5-level drawdown circuit breaker status.
- `alpaca_submit_options_order`: Dispatches Kelly-sized options order.
- `alpaca_close_position`: Liquidates position on Alpaca.
- `alpaca_run_options_monitor`: Executes 4-Exit risk rules.

---

## 🛡️ Automated 5-Gate Risk & 4-Exit Management

### 5-Gate Entry Filter
Every candidate signal must pass all 5 gates before capital is allocated:
1. **Gate 0 (Portfolio Limits)**: Max 5 concurrent options, max 1 per underlying.
2. **Gate 1 (Quality)**: Confidence $\ge 75\%$ from DeepSeek-V3.2.
3. **Gate 2 (IV Regime)**: IV Rank $<35$ (full size), $35-55$ (half size), $>55$ (blocked for long options).
4. **Gate 3 (DTE Window)**: $21 \le \text{DTE} \le 45$ (optimal theta decay curve).
5. **Gate 5 (Dynamic Sizing)**: Quarter Kelly Criterion $\times$ Circuit Breaker $\times$ LLM Size Scalar (capped at 3% max portfolio risk).

### 4-Exit Automated Discipline
The Options Monitor runs on every cycle:
- **Profit Target**: Take profit at **+60% to +80%** gain.
- **Stop Loss**: Strict stop loss at **-35% to -40%** loss.
- **Theta Stop**: Auto-exit at **14 DTE** to avoid exponential theta bleed.
- **Circuit Breaker Exit**: Auto-liquidate if Level 4 (Black) shutdown triggers.

---

## 🧪 Validation & Test Suite

Run the master 12-block verification test suite covering all subsystems:

```bash
cd backend
python tests/test_full_system_validation.py
```

```text
=====================================================================================
📊 FULL SYSTEM VALIDATION SUMMARY REPORT
=====================================================================================
  TOTAL TESTS RUN: 32
  PASSED:          32  ✅
  FAILED:          0  
  SUCCESS RATE:    100.0%
=====================================================================================
🏆 SYSTEM IS 100% PRODUCTION READY FOR COMPETITION PAPER TRADING!
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
