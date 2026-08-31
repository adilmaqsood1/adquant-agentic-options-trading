import os
import sys
from contextlib import asynccontextmanager

# Ensure root directory is always on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
from app.routers.agent_router import router as agent_router
from app.routers.dashboard_router import router as dashboard_router
from scheduler import start_scheduler, stop_scheduler




@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database Tables & Schema
    try:
        print("[FastAPI Startup] Ensuring database tables and indexes are initialized...")
        init_db()
    except Exception as db_err:
        print(f"[FastAPI Startup] Database initialization warning: {db_err}")

    # Start autonomous background scheduler and run initial scan
    print("[FastAPI Startup] Initializing BackgroundScheduler & Launching Initial Multi-Interval Scan...")
    start_scheduler(run_immediately=True)
    yield
    # Shutdown: Cleanly stop background scheduler
    print("[FastAPI Shutdown] Stopping BackgroundScheduler...")
    stop_scheduler()


app = FastAPI(
    title="AdQuant — Agentic Options Trading API",
    description="""High-performance quantitative options trading engine with autonomous multi-agent reasoning DeepSeek-V3.2, 
    5-Gate risk management, Black-Scholes pricing, and Alpaca MCP execution.""",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local React / Vite frontend and cloud dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(dashboard_router)
app.include_router(agent_router)



@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Alpaca AI Options Trading Backend",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)