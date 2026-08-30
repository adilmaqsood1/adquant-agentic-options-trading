import os
from dotenv import load_dotenv

load_dotenv()

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL")
ALPACA_DATA_URL = os.getenv("ALPACA_DATA_URL")

# LLM Primary Model Settings (Featherless DeepSeek-V3.2)
FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY") or os.getenv("Featherless_API_KEY")
FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "deepseek-ai/DeepSeek-V3.2")
FEATHERLESS_BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1000"))

# Secondary Fallback LLM (Groq)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_FALLBACK_MODEL = "openai/gpt-oss-120b"

# Supabase Production Settings
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://twnzbwukcgaxjexjpodl.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_Kw_sxnta-I6kjADmevWrYg_2H8AECit")

_supabase_client = None

def get_supabase_client():
    """Initializes and returns a cached Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        try:
            from supabase import create_client, Client
            if SUPABASE_URL and SUPABASE_KEY:
                _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            print(f"[Supabase] Warning: Could not initialize Supabase client: {e}")
    return _supabase_client

# Trading parameters
STARTING_BALANCE = 100_000
MAX_POSITION_SIZE = 0.05      # 5% of portfolio per trade
MAX_PORTFOLIO_DELTA = 0.30    # total portfolio delta cap
TARGET_DELTA = 0.30           # OTM options target
MIN_IV_RANK = 50              # only trade when IV rank >= 50th percentile
DTE_TARGET = 14               # days to expiration target
STOP_LOSS_MULTIPLIER = 2.0    # close if loss = 2x premium received