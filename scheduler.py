import os
import sys
import time
import datetime
import threading
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.orchestrator import run_cycle
from app.core.database import init_db

_global_scheduler: Optional[BackgroundScheduler] = None


def job_2h_cycle():
    """Job 1: 2-Hour Strategy Cycle (Momentum EMA/RSI/ADX, VWAP Deviation)"""
    print(f"\n[SCHEDULER TRIGGER] Running 2H Cycle at {datetime.datetime.utcnow().isoformat()} UTC...")
    try:
        return run_cycle("2H")
    except Exception as e:
        print(f"[SCHEDULER ERROR] 2H Cycle exception: {e}")
        return None


def job_4h_cycle():
    """Job 2: 4-Hour Strategy Cycle (CVD Squeeze, Liquidity Sweep, Supertrend, Donchian, Hurst, VWAP)"""
    print(f"\n[SCHEDULER TRIGGER] Running 4H Cycle at {datetime.datetime.utcnow().isoformat()} UTC...")
    try:
        return run_cycle("4H")
    except Exception as e:
        print(f"[SCHEDULER ERROR] 4H Cycle exception: {e}")
        return None


def job_daily_cycle():
    """Job 3: Daily Strategy Cycle (Sharpe Residual Momentum, Cross-Sectional Momentum)"""
    print(f"\n[SCHEDULER TRIGGER] Running Daily Cycle at {datetime.datetime.utcnow().isoformat()} UTC...")
    try:
        return run_cycle("1D")
    except Exception as e:
        print(f"[SCHEDULER ERROR] Daily Cycle exception: {e}")
        return None



def run_full_initial_scan() -> Dict[str, Any]:
    """
    Runs an immediate comprehensive scan across ALL time intervals (2H, 4H, 1D)
    and all 4 production strategies on engine boot to identify any active opportunities immediately.
    """
    print("\n" + "=" * 80)
    print("      INITIAL ENGINE BOOT: SCANNING ALL TIME INTERVALS (2H, 4H, 1D)")
    print("=" * 80)
    
    results = {}
    
    # 1. Scan 2H Timeframe
    print("\n>>> [INITIAL SCAN 1/3] Scanning 2H Timeframe (BTCUSDT)...")
    res_2h = job_2h_cycle()
    results["2H"] = res_2h
    
    # 2. Scan 4H Timeframe
    print("\n>>> [INITIAL SCAN 2/3] Scanning 4H Timeframe (BTCUSDT)...")
    res_4h = job_4h_cycle()
    results["4H"] = res_4h
    
    # 3. Scan 1D Timeframe
    print("\n>>> [INITIAL SCAN 3/3] Scanning 1D Daily Timeframe (SPY, QQQ, AAPL, NVDA)...")
    res_1d = job_daily_cycle()
    results["1D"] = res_1d
    
    print("\n" + "=" * 80)
    print("      INITIAL COMPREHENSIVE SCAN COMPLETED ACROSS ALL INTERVALS")
    print("=" * 80 + "\n")
    
    return results


def start_scheduler(run_immediately: bool = True) -> BackgroundScheduler:
    """
    Initializes and starts the autonomous background scheduler with all 3 recurring jobs.
    If run_immediately=True, immediately triggers the initial scan across all intervals in a background thread.
    """
    global _global_scheduler

    if _global_scheduler is not None and _global_scheduler.running:
        print("[SCHEDULER] BackgroundScheduler is already running.")
        return _global_scheduler

    init_db()

    scheduler = BackgroundScheduler(timezone="UTC")

    # 1. Job 1 — Every 2 Hours (recurring)
    scheduler.add_job(
        job_2h_cycle,
        trigger=IntervalTrigger(hours=2),
        id="job_2h_momentum",
        name="2H Momentum EMA/RSI/ADX Cycle",
        misfire_grace_time=300,
        replace_existing=True
    )

    # 2. Job 2 — Every 4 Hours (recurring)
    scheduler.add_job(
        job_4h_cycle,
        trigger=IntervalTrigger(hours=4),
        id="job_4h_trend_breakout",
        name="4H Supertrend & Donchian Turtle Cycle",
        misfire_grace_time=300,
        replace_existing=True
    )

    # 3. Job 3 — Daily at 14:30 UTC (US Market Open + 1 hour)
    scheduler.add_job(
        job_daily_cycle,
        trigger=CronTrigger(hour=14, minute=30, timezone="UTC"),
        id="job_daily_cross_sectional",
        name="Daily Cross-Sectional Momentum Cycle (14:30 UTC)",
        misfire_grace_time=300,
        replace_existing=True
    )

    scheduler.start()
    _global_scheduler = scheduler

    print("=" * 80)
    print("      AUTONOMOUS AI TRADING AGENT SCHEDULER STARTED (UTC)")
    print("=" * 80)
    print("Active Scheduled Recurring Jobs:")
    print("  1. [2H Cycle] : Every 2 Hours    | Strategy: momentum_ema_rsi_adx (BTCUSDT)")
    print("  2. [4H Cycle] : Every 4 Hours    | Strategies: supertrend, donchian_turtle (BTCUSDT)")
    print("  3. [1D Cycle] : Daily @ 14:30 UTC| Strategy: cross_sectional_momentum (SPY, QQQ, AAPL, NVDA)")
    print("  * Misfire Grace Time: 300s (5 minutes)")
    print("=" * 80)

    # Run immediate full scan across all intervals in a background thread on boot
    if run_immediately:
        boot_thread = threading.Thread(target=run_full_initial_scan, daemon=True)
        boot_thread.start()

    return scheduler


def get_scheduler() -> Optional[BackgroundScheduler]:
    return _global_scheduler


def get_scheduler_status() -> Dict[str, Any]:
    """Returns detailed status of the scheduler and next run times for each job."""
    global _global_scheduler
    if _global_scheduler is None or not _global_scheduler.running:
        return {"running": False, "jobs": []}

    jobs_info = []
    for job in _global_scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })

    return {
        "running": True,
        "current_time_utc": datetime.datetime.utcnow().isoformat(),
        "jobs": jobs_info
    }


def stop_scheduler():
    global _global_scheduler
    if _global_scheduler and _global_scheduler.running:
        _global_scheduler.shutdown(wait=False)
        print("[SCHEDULER] Scheduler stopped cleanly.")
        _global_scheduler = None


if __name__ == "__main__":
    scheduler = start_scheduler(run_immediately=True)

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        print("\n[SCHEDULER] Shutdown signal received. Stopping scheduler...")
        stop_scheduler()
