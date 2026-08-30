import os
import json
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load env variables from backend root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
GMAIL_USER = os.getenv("GMAIL_USER") or os.getenv("SMTP_LOGIN")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("SMTP_PASSWORD")
ALERT_EMAIL = os.getenv("ALERT_EMAIL") or GMAIL_USER


def send_cycle_report(cycle_summary: Dict[str, Any]) -> bool:
    """
    Sends an automated plain-text cycle report with attached cycle_log.json.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not ALERT_EMAIL:
        print("[EmailReporter] WARNING: Gmail credentials not fully set in .env. Skipping email dispatch.")
        return False

    timeframe_scope = cycle_summary.get("timeframe_scope", "4H")
    cycle_time_str = cycle_summary.get("cycle_time", datetime.datetime.utcnow().isoformat())
    duration_sec = cycle_summary.get("duration_seconds", 0.0)
    symbols_scanned = cycle_summary.get("symbols_scanned", 0)
    signals_detected = cycle_summary.get("signals_detected", 0)
    groq_approved = cycle_summary.get("groq_approved", 0)
    risk_approved = cycle_summary.get("risk_approved", 0)
    approved_orders = cycle_summary.get("approved_orders", [])
    blocked_signals = cycle_summary.get("blocked_signals", [])
    errors = cycle_summary.get("errors", [])
    portfolio = cycle_summary.get("portfolio_summary", {})

    total_allocated = portfolio.get("total_allocated", 0.0)
    open_positions = portfolio.get("total_open_positions", 0)
    unrealized_pnl = portfolio.get("unrealized_pnl", 0.0)

    # Dynamic options market context for subject line
    asset_ctx = []
    if "1D" in timeframe_scope:
        asset_ctx.append("US Equities 1D Options")
    elif "4H" in timeframe_scope or "2H" in timeframe_scope:
        asset_ctx.append("US Equities Options Universe")
    else:
        asset_ctx.append("Options Universe")
    
    asset_tag = " / ".join(asset_ctx)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Subject Line Logic
    # ─────────────────────────────────────────────────────────────────────────
    if risk_approved > 0 and approved_orders:
        first_order = approved_orders[0]
        s_id = first_order.get("strategy_id", "algo")
        sym = first_order.get("symbol", "BTCUSDT")
        sig_t = first_order.get("signal_type", "ENTER_LONG")
        subject = f"[AGENT] {timeframe_scope} Cycle | ORDER APPROVED | {s_id} {sym} {sig_t}"
    elif signals_detected > 0:
        subject = f"[AGENT] {timeframe_scope} Cycle | {signals_detected} Signals | {risk_approved} Approved | {symbols_scanned} Assets Scanned"
    else:
        subject = f"[AGENT] {timeframe_scope} Cycle | No Signals | {symbols_scanned} Assets Scanned ({asset_tag})"

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Email Body Composition
    # ─────────────────────────────────────────────────────────────────────────
    lines = [
        "============================================================",
        "             AUTONOMOUS TRADING AGENT REPORT               ",
        "============================================================",
        f"Cycle Time   : {cycle_time_str[:19].replace('T', ' ')} UTC",
        f"Scope        : {timeframe_scope}",
        f"Duration     : {duration_sec}s",
        "============================================================",
        "PORTFOLIO STATUS",
        "============================================================",
        "Starting Capital : $100,000.00",
        f"Total Allocated  : ${total_allocated:,.2f}",
        f"Open Positions   : {open_positions}",
        f"Unrealized PnL   : ${unrealized_pnl:,.2f}",
        "============================================================",
        "SIGNAL SCAN RESULTS",
        "============================================================",
        f"Symbols Scanned  : {symbols_scanned}",
        f"Signals Fired    : {signals_detected}",
        f"Groq Approved    : {groq_approved}",
        f"Risk Approved    : {risk_approved}",
        "============================================================"
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # Research Agent Autonomous Insights (Creativity & Market Intelligence)
    # ─────────────────────────────────────────────────────────────────────────
    research = cycle_summary.get("research_insights", {})
    actionable_insight = research.get("actionable_insight")
    next_focus = research.get("next_cycle_focus")
    regime_data = research.get("market_regime", {})
    regime_name = regime_data.get("regime", "UNKNOWN") if isinstance(regime_data, dict) else str(regime_data)
    regime_assessment = regime_data.get("overall_assessment", "") if isinstance(regime_data, dict) else ""
    novel_strats = research.get("novel_strategies", [])

    if actionable_insight and actionable_insight != "Research agent unavailable.":
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🔬 AUTONOMOUS RESEARCH AGENT INSIGHTS",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Market Regime   : {regime_name}",
            f"Assessment      : {regime_assessment}",
            "",
            "💡 ACTIONABLE INSIGHT:",
            f"  {actionable_insight}",
            "",
            f"🎯 NEXT CYCLE FOCUS: {next_focus}",
        ])

        if novel_strats:
            lines.append("\n🧪 NOVEL OPTIONS STRATEGIES DISCOVERED:")
            for idx, ns in enumerate(novel_strats[:2], 1):
                lines.append(f"  {idx}. {ns.get('name')} [{ns.get('option_structure', 'options')}] (Conf: {ns.get('estimated_confidence', 0)}%)")
                lines.append(f"     Logic: {ns.get('logic')}")
                lines.append(f"     DTE: {ns.get('optimal_dte', '30-35')} | Why: {ns.get('why_now')}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Fired and Approved Orders Details
    if approved_orders:
        lines.append("APPROVED ORDERS (EXECUTED / READY)")
        lines.append("============================================================")
        for ord_item in approved_orders:
            lines.append(f"Strategy     : {ord_item.get('strategy_id')}")
            lines.append(f"Symbol       : {ord_item.get('symbol')}")
            lines.append(f"Signal Type  : {ord_item.get('signal_type')}")
            lines.append(f"Execution Px : ${ord_item.get('execution_price', 0.0):,.2f}")
            lines.append(f"Final Capital: ${ord_item.get('final_capital', 0.0):,.2f}")
            lines.append(f"Quantity     : {ord_item.get('final_quantity')}")
            lines.append(f"Groq Conf    : {ord_item.get('groq_confidence')}/100")
            lines.append(f"Reasoning    : {ord_item.get('groq_reasoning')}")
            lines.append("------------------------------------------------------------")

    # Blocked Signals Details
    if blocked_signals:
        lines.append("BLOCKED SIGNALS (REJECTED)")
        lines.append("============================================================")
        for b in blocked_signals:
            lines.append(f"Strategy: {b.get('strategy_id')} | Symbol: {b.get('symbol')}")
            lines.append(f"Reason  : {b.get('reason')}")
            lines.append("------------------------------------------------------------")

    # Errors section
    if errors:
        lines.append("ERRORS ENCOUNTERED")
        lines.append("============================================================")
        for err in errors:
            lines.append(f"- {err}")
        lines.append("============================================================")

    # Next cycle estimate
    next_cycle_hrs = 2 if timeframe_scope == "2H" else (4 if timeframe_scope == "4H" else 24)
    next_time_est = (datetime.datetime.utcnow() + datetime.timedelta(hours=next_cycle_hrs)).strftime("%Y-%m-%d %H:00 UTC")

    lines.extend([
        f"Next {timeframe_scope} cycle approx: {next_time_est}",
        "Agent v1.0 | Powered by Featherless DeepSeek-V3.2 + LangGraph + Alpaca MCP",
        "============================================================"
    ])

    body_text = "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Create MIME Message & Attach cycle_log.json
    # ─────────────────────────────────────────────────────────────────────────
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = ALERT_EMAIL
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain"))

    # Attachment: cycle_log.json
    try:
        json_bytes = json.dumps(cycle_summary, indent=2, default=str).encode("utf-8")
        att = MIMEApplication(json_bytes, _subtype="json")
        att.add_header("Content-Disposition", "attachment", filename="cycle_log.json")
        msg.attach(att)
    except Exception as e:
        print(f"[EmailReporter] WARNING: Could not attach cycle_log.json: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Dispatch via Gmail SMTP TLS
    # ─────────────────────────────────────────────────────────────────────────
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            # Clean spaces from app password if present
            clean_pw = GMAIL_APP_PASSWORD.replace(" ", "")
            server.login(GMAIL_USER, clean_pw)
            server.send_message(msg)

        print(f"[EmailReporter] SUCCESS: Cycle report email dispatched to {ALERT_EMAIL} | Subject: '{subject}'")
        return True
    except Exception as e:
        print(f"[EmailReporter] ERROR sending email via SMTP: {e}")
        return False


def send_email_alert(subject: str, body: str) -> bool:
    """
    Sends an instant text alert email for orders, circuit breakers, or critical events.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not ALERT_EMAIL:
        return False
    try:
        msg = MIMEText(body, "plain")
        msg["From"] = GMAIL_USER
        msg["To"] = ALERT_EMAIL
        msg["Subject"] = subject

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD.replace(" ", ""))
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[EmailReporter] Alert email error: {e}")
        return False


def generate_html_report(
    signals: list,
    decisions: list,
    approved_orders: list,
    blocked_orders: list,
    active_positions: list,
    circuit_breaker: dict
) -> str:
    """
    Generates a structured HTML dashboard report for cycle summaries and email broadcasts.
    """
    cb_label = circuit_breaker.get("circuit_breaker_label", "Green (Normal)")
    cb_lvl = circuit_breaker.get("circuit_breaker_level", 0)
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #222;">
        <h2 style="color: #0b5cff;">⚡ Alpaca AI Trading — Cycle Summary Report</h2>
        <div style="padding: 10px; background: #f0f4f8; border-radius: 6px; margin-bottom: 15px;">
            <strong>Circuit Breaker:</strong> Level {cb_lvl} ({cb_label}) | 
            <strong>Signals Scanned:</strong> {len(signals)} | 
            <strong>Orders Approved:</strong> {len(approved_orders)}
        </div>
        <h3>Approved Options Orders</h3>
        <ul>
            {''.join(f"<li><b>{o.get('symbol')}</b>: ${o.get('allocated_capital', 0):,.2f}</li>" for o in approved_orders) if approved_orders else "<li>No new orders executed.</li>"}
        </ul>
    </div>
    """
    return html
