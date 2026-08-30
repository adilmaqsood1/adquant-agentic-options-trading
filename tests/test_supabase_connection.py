import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.core.config import SUPABASE_URL, SUPABASE_KEY, get_supabase_client

def test_supabase_connection():
    print("=" * 80)
    print("⚡ TESTING SUPABASE PRODUCTION CLIENT CONNECTION")
    print("=" * 80)
    print(f"Supabase URL: {SUPABASE_URL}")
    print(f"Supabase Key Present: {bool(SUPABASE_KEY)}")

    client = get_supabase_client()
    if client is not None:
        print("✅ Supabase client initialized successfully!")
        print("Client object:", type(client))
    else:
        print("❌ Failed to initialize Supabase client.")

if __name__ == "__main__":
    test_supabase_connection()
