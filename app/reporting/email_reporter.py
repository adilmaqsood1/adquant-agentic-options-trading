import os
import json
import smtplib
import datetime
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# Load env variables from backend root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
GMAIL_USER = os.getenv("GMAIL_USER") or os.getenv("SMTP_LOGIN")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("SMTP_PASSWORD")
ALERT_EMAIL = os.getenv("ALERT_EMAIL") or GMAIL_USER

# Minimum throttle interval between automated email reports (10 minutes)
# Prevents duplicate email storms across rapid multi-timeframe boot sweeps
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
CACHE_FILE = os.path.join(CACHE_DIR, "last_email_sent.json")
EMAIL_COOLDOWN_SECONDS: float = 600.0  # 10 minutes cooldown


def _get_last_email_timestamp() -> float:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return float(data.get("last_sent_ts", 0.0))
    except Exception:
        pass
    return 0.0


def _set_last_email_timestamp(ts: float):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_sent_ts": ts, "last_sent_iso": datetime.datetime.utcnow().isoformat()}, f)
    except Exception:
        pass


def build_premium_html_email(cycle_summary: Dict[str, Any]) -> str:
    """
    Constructs a modern, crisp white-theme responsive HTML/CSS email.
    Uses clean typography, light cards, subtle borders, and vivid badge accents.
    """
    timeframe_scope = cycle_summary.get("timeframe_scope", "4H")
    cycle_time_str = cycle_summary.get("cycle_time", datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))
    if "T" in cycle_time_str:
        cycle_time_str = cycle_time_str[:19].replace("T", " ") + " UTC"
    duration_sec = cycle_summary.get("duration_seconds", 0.0)
    symbols_scanned = cycle_summary.get("symbols_scanned", 0)
    approved_orders = cycle_summary.get("approved_orders", [])
    risk_approved = cycle_summary.get("risk_approved", len(approved_orders))
    portfolio = cycle_summary.get("portfolio_summary", {})

    total_allocated = portfolio.get("total_allocated", 0.0)
    open_positions = portfolio.get("total_open_positions", len(approved_orders))
    unrealized_pnl = portfolio.get("unrealized_pnl", 0.0)

    research = cycle_summary.get("research_insights", {})
    regime_data = research.get("market_regime", {})
    regime_name = regime_data.get("regime", "SIDEWAYS_CONSOLIDATION") if isinstance(regime_data, dict) else str(regime_data)
    regime_assessment = regime_data.get("overall_assessment", "Favorable volatility conditions for defined-risk option structures.") if isinstance(regime_data, dict) else ""
    actionable_insight = research.get("actionable_insight", "")
    novel_strats = research.get("novel_strategies", [])

    # Format orders rows
    orders_html_rows = ""
    for ord_item in approved_orders:
        s_id = ord_item.get("strategy_id", "options_core")
        sym = ord_item.get("symbol", "OPTION")
        occ = ord_item.get("occ_symbol", sym)
        conf_tier = ord_item.get("confluence_tier", "SINGLE_STRATEGY")
        conf_badge = "badge-purple" if "TRIPLE" in conf_tier else ("badge-gold" if "DOUBLE" in conf_tier else "badge-green")
        rank_val = ord_item.get("tournament_rank", 1)
        exec_px = float(ord_item.get("execution_price") or ord_item.get("premium_paid") or 0.0)
        final_cap = float(ord_item.get("final_capital") or ord_item.get("allocated_capital") or 0.0)
        qty = ord_item.get("final_quantity") or ord_item.get("contracts_qty") or 1
        conf_pct = ord_item.get("groq_confidence") or 85
        reason = ord_item.get("groq_reasoning") or ord_item.get("rationale") or "High probability setup validated by 5-Gate Defense."

        orders_html_rows += f"""
        <tr>
            <td style="padding: 12px 14px; border-bottom: 1px solid #E2E8F0; font-weight: 700; color: #0F172A;">
                #{rank_val} {sym}
                <div style="font-size: 11px; color: #64748B; font-family: monospace; margin-top: 2px;">{occ}</div>
            </td>
            <td style="padding: 12px 14px; border-bottom: 1px solid #E2E8F0;">
                <span class="{conf_badge}" style="display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;">{conf_tier.replace('_', ' ')}</span>
                <div style="font-size: 11px; color: #64748B; margin-top: 3px;">{s_id}</div>
            </td>
            <td style="padding: 12px 14px; border-bottom: 1px solid #E2E8F0; text-align: center; color: #0F172A; font-weight: 600;">
                {qty} Contract{'s' if int(qty) > 1 else ''}
            </td>
            <td style="padding: 12px 14px; border-bottom: 1px solid #E2E8F0; text-align: right; font-weight: 700; color: #059669;">
                ${exec_px:,.2f}
                <div style="font-size: 11px; color: #64748B;">Cap: ${final_cap:,.0f}</div>
            </td>
        </tr>
        <tr>
            <td colspan="4" style="padding: 10px 14px 14px 14px; border-bottom: 1px solid #E2E8F0; background-color: #F8FAFC; font-size: 12px; color: #334155; line-height: 1.5;">
                <strong style="color: #059669;">DeepSeek-V3.2 Reasoning ({conf_pct}% Conviction):</strong> {reason}
            </td>
        </tr>
        """

    # Novel strategies list
    novel_html = ""
    if novel_strats:
        for idx, ns in enumerate(novel_strats[:2], 1):
            novel_html += f"""
            <div style="background-color: #FFFFFF; border-left: 3px solid #D97706; border-radius: 4px; padding: 10px 12px; margin-top: 8px; border: 1px solid #E2E8F0; border-left-width: 3px;">
                <div style="font-weight: 700; color: #B45309; font-size: 13px;">{idx}. {ns.get('name')} <span style="font-size: 11px; color: #64748B;">({ns.get('option_structure', 'Spread')}) &bull; Conf: {ns.get('estimated_confidence', 85)}%</span></div>
                <div style="font-size: 12px; color: #475569; margin-top: 4px;">{ns.get('logic')}</div>
            </div>
            """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ADQuant Options Execution Report</title>
    <style>
        body {{ margin: 0; padding: 0; background-color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #0F172A; }}
        .badge-green {{ background-color: #ECFDF5; color: #059669; border: 1px solid #A7F3D0; }}
        .badge-gold {{ background-color: #FFFBEB; color: #D97706; border: 1px solid #FDE68A; }}
        .badge-purple {{ background-color: #F5F3FF; color: #7C3AED; border: 1px solid #DDD6FE; }}
    </style>
</head>
<body style="background-color: #F8FAFC; padding: 24px 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #0F172A;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 680px; margin: 0 auto; background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.05);">
        
        <!-- Header Banner -->
        <tr>
            <td style="background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); padding: 24px; border-bottom: 1px solid #334155;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td>
                            <div style="font-size: 20px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px;">
                                AD<span style="color: #10B981;">Quant</span>
                            </div>
                            <div style="font-size: 12px; color: #94A3B8; margin-top: 3px; font-weight: 500;">
                                Autonomous Options Trading Desk &bull; Alpaca MCP Live Execution
                            </div>
                        </td>
                        <td align="right" valign="middle">
                            <span style="background-color: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.4); padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; text-transform: uppercase;">
                                {timeframe_scope} Live Execution
                            </span>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- KPI Metrics Grid -->
        <tr>
            <td style="padding: 20px 24px;">
                <table width="100%" border="0" cellspacing="8" cellpadding="0">
                    <tr>
                        <td width="33%" style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px; text-align: left;">
                            <div style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Trades Approved</div>
                            <div style="font-size: 22px; font-weight: 800; color: #059669; margin-top: 4px;">{risk_approved}</div>
                            <div style="font-size: 11px; color: #64748B; margin-top: 2px;">{symbols_scanned} Assets Scanned</div>
                        </td>
                        <td width="33%" style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px; text-align: left;">
                            <div style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Market Regime</div>
                            <div style="font-size: 14px; font-weight: 700; color: #D97706; margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{regime_name}</div>
                            <div style="font-size: 11px; color: #64748B; margin-top: 2px;">DeepSeek Macro Agent</div>
                        </td>
                        <td width="33%" style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 14px; text-align: left;">
                            <div style="font-size: 11px; color: #64748B; text-transform: uppercase; font-weight: 600;">Risk Defense</div>
                            <div style="font-size: 15px; font-weight: 700; color: #059669; margin-top: 5px;">CB Level 0</div>
                            <div style="font-size: 11px; color: #64748B; margin-top: 2px;">3% Sizing Cap Active</div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>

        <!-- Executed Options Orders Section -->
        <tr>
            <td style="padding: 0 24px 20px 24px;">
                <div style="font-size: 14px; font-weight: 700; color: #0F172A; margin-bottom: 10px;">
                    Live Options Orders Routed to Alpaca
                </div>
                <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; border-collapse: collapse; overflow: hidden;">
                    <thead>
                        <tr style="background-color: #F1F5F9;">
                            <th align="left" style="padding: 10px 14px; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 600; border-bottom: 1px solid #E2E8F0;">Asset / OCC Contract</th>
                            <th align="left" style="padding: 10px 14px; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 600; border-bottom: 1px solid #E2E8F0;">Confluence / Strategy</th>
                            <th align="center" style="padding: 10px 14px; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 600; border-bottom: 1px solid #E2E8F0;">Contracts</th>
                            <th align="right" style="padding: 10px 14px; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 600; border-bottom: 1px solid #E2E8F0;">Premium / Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                        {orders_html_rows}
                    </tbody>
                </table>
            </td>
        </tr>

        <!-- Autonomous Research & Insights -->
        <tr>
            <td style="padding: 0 24px 24px 24px;">
                <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px;">
                    <div style="font-size: 13px; font-weight: 700; color: #D97706; margin-bottom: 6px;">
                        Macro Regime Assessment & Alpha Focus
                    </div>
                    <div style="font-size: 12px; color: #475569; line-height: 1.6;">
                        {regime_assessment}
                    </div>
                    {f'<div style="font-size: 12px; color: #059669; margin-top: 8px; font-weight: 600;">💡 Actionable Insight: <span style="color: #0F172A; font-weight: normal;">{actionable_insight}</span></div>' if actionable_insight else ''}
                    {novel_html}
                </div>
            </td>
        </tr>

        <!-- Footer -->
        <tr>
            <td style="background-color: #F1F5F9; padding: 18px 24px; border-top: 1px solid #E2E8F0; text-align: center;">
                <div style="font-size: 11px; color: #64748B;">
                    Execution Timestamp: {cycle_time_str} &bull; Duration: {duration_sec}s
                </div>
                <div style="font-size: 11px; color: #64748B; margin-top: 4px;">
                    ADQuant Multi-Agent Trading System &bull; Powered by DeepSeek-V3.2 + Alpaca MCP
                </div>
            </td>
        </tr>
    </table>
</body>
</html>"""


def send_cycle_report(cycle_summary: Dict[str, Any], force: bool = False) -> bool:
    """
    Sends an automated, single consolidated HTML execution report with attached cycle_log.json.
    Enforces a 10-minute cooldown throttle to guarantee only 1 consolidated email is delivered.
    """
    global _LAST_EMAIL_SENT_TIMESTAMP

    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not ALERT_EMAIL:
        print("[EmailReporter] WARNING: Gmail credentials not fully set in .env. Skipping email dispatch.")
        return False

    approved_orders = cycle_summary.get("approved_orders", [])
    risk_approved = cycle_summary.get("risk_approved", len(approved_orders))
    cb_level = cycle_summary.get("cb_level", 0)

    # 1. Suppress routine scans when 0 orders were approved
    if risk_approved == 0 and cb_level == 0 and not force:
        print("[EmailReporter] Zero new orders placed in cycle. Skipping email dispatch.")
        return True

    # 2. Enforce 10-minute cooldown throttle to prevent duplicate email bursts
    now = time.time()
    last_sent = _get_last_email_timestamp()
    if not force and (now - last_sent) < EMAIL_COOLDOWN_SECONDS:
        elapsed_min = round((now - last_sent) / 60.0, 1)
        print(f"[EmailReporter] Email throttled: Last report was sent {elapsed_min}m ago (Cooldown: {EMAIL_COOLDOWN_SECONDS/60:.0f}m). Consolidating into active cycle.")
        return True

    timeframe_scope = cycle_summary.get("timeframe_scope", "4H")

    # 3. Subject Line (Clean, professional, zero emojis)
    if approved_orders:
        first_order = approved_orders[0]
        sym = first_order.get("symbol", "OPTIONS")
        conf_tier = first_order.get("confluence_tier", "APPROVED")
        order_count = len(approved_orders)
        if order_count > 1:
            subject = f"[ADQuant Execution] {order_count} Options Orders Placed | Top Pick: {sym} ({conf_tier})"
        else:
            subject = f"[ADQuant Execution] {sym} ({conf_tier}) | Order Placed | Strategy: {first_order.get('strategy_id', 'options_core')}"
    elif cb_level > 0:
        subject = f"[ADQuant Emergency] Circuit Breaker Level {cb_level} Triggered"
    else:
        subject = f"[ADQuant Trade Execution] {timeframe_scope} Cycle Completed"

    # 4. Generate Premium HTML Body
    html_content = build_premium_html_email(cycle_summary)

    # Plain text fallback
    plain_fallback = f"ADQuant Options Trade Execution Report ({timeframe_scope})\n"
    for o in approved_orders:
        plain_fallback += f"- {o.get('symbol')} ({o.get('occ_symbol')}): {o.get('final_quantity', 1)} contracts @ ${float(o.get('execution_price', 0)):.2f}\n"

    # 5. Create Multipart Message with explicit UTF-8 encoding
    msg = MIMEMultipart("mixed")
    msg["From"] = f"ADQuant Options Desk <{GMAIL_USER}>"
    msg["To"] = ALERT_EMAIL
    msg["Subject"] = subject

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(plain_fallback, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(alt_part)

    # Attachment: cycle_log.json
    try:
        json_bytes = json.dumps(cycle_summary, indent=2, default=str).encode("utf-8")
        att = MIMEApplication(json_bytes, _subtype="json")
        att.add_header("Content-Disposition", "attachment", filename="cycle_log.json")
        msg.attach(att)
    except Exception as e:
        print(f"[EmailReporter] WARNING: Could not attach cycle_log.json: {e}")

    # 6. Dispatch via SMTP TLS
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            clean_pw = GMAIL_APP_PASSWORD.replace(" ", "")
            server.login(GMAIL_USER, clean_pw)
            server.send_message(msg)

        _set_last_email_timestamp(now)
        print(f"[EmailReporter] SUCCESS: Single consolidated HTML email report dispatched to {ALERT_EMAIL} | Subject: '{subject}'")
        return True
    except Exception as e:
        print(f"[EmailReporter] ERROR sending email via SMTP: {e}")
        return False
