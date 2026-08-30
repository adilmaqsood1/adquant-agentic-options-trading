import os
import sys
from dotenv import load_dotenv
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.core.database import get_pool

pool = get_pool()
conn = pool.getconn()
try:
    with conn.cursor() as cur:
        cur.execute("UPDATE positions SET status='closed' WHERE status='open';")
        cur.execute("UPDATE options_contracts SET status='closed' WHERE status='open';")
        conn.commit()
        print("✅ Cleaned all mock open test positions in PostgreSQL.")
finally:
    pool.putconn(conn)
