import os
import sys
import httpx
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

api_key = os.getenv("FEATHERLESS_API_KEY") or os.getenv("Featherless_API_KEY")
base_url = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
model = os.getenv("FEATHERLESS_MODEL", "deepseek-ai/DeepSeek-V3.2")
temperature = float(os.getenv("TEMPERATURE", 0.1))
max_tokens = int(os.getenv("MAX_TOKENS", 1000))

print(f"API Key present: {bool(api_key)}")
print(f"Base URL: {base_url}")
print(f"Model: {model}")

url = f"{base_url.rstrip('/')}/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
payload = {
    "model": model,
    "messages": [
        {"role": "system", "content": "You are a quantitative financial reasoning agent. Output only JSON."},
        {"role": "user", "content": "Evaluate trading signal: AAPL RSI Oversold 28.5. Return JSON with confidence (0-100), go (bool), reasoning (string)."}
    ],
    "temperature": temperature,
    "max_tokens": max_tokens
}

try:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        print(f"HTTP Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            print("Response Content:\n", content)
        else:
            print("Error Response:\n", resp.text)
except Exception as e:
    print("Exception during request:", e)
