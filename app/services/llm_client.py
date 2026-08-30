"""
Autonomous LLM Client — Featherless DeepSeek-V3.2 (Primary) + Groq (Fallback)
=============================================================================
Provides structured JSON querying with:
  1. Primary Model: Featherless DeepSeek-V3.2 (https://api.featherless.ai/v1)
  2. Automatic Failover: Secondary Groq LLM fallback for 100% uptime
  3. Robust JSON extraction handling markdown code fences (```json ... ```)
"""

import os
import json
import re
from typing import Dict, Any, Optional, Tuple
import httpx
from dotenv import load_dotenv

# Load env variables from backend root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
FEATHERLESS_API_KEY = os.getenv("FEATHERLESS_API_KEY") or os.getenv("Featherless_API_KEY")
FEATHERLESS_BASE_URL = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1").rstrip("/")
FEATHERLESS_MODEL = os.getenv("FEATHERLESS_MODEL", "deepseek-ai/DeepSeek-V3.2")
DEFAULT_TEMPERATURE = float(os.getenv("TEMPERATURE", "0.1"))
DEFAULT_MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1000"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-120b")


def extract_json_payload(raw_content: str) -> Dict[str, Any]:
    """
    Robustly parses JSON from LLM text, handling markdown fences or surrounding chatter.
    """
    text = raw_content.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: search for first '{' to last '}'
        start_idx = text.find("{")
        end_idx = text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            extracted = text[start_idx:end_idx + 1]
            return json.loads(extracted)
        raise


def query_llm_json(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 25.0
) -> Tuple[Dict[str, Any], str, Dict[str, int]]:
    """
    Executes a structured JSON LLM call.
    Attempts Primary Featherless DeepSeek-V3.2 first; falls back to Groq on failure.

    Returns:
        (parsed_json_dict, model_used_name, usage_dict)
    """
    req_model = model or FEATHERLESS_MODEL
    req_temp = temperature if temperature is not None else DEFAULT_TEMPERATURE
    req_max_tokens = max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # ── 1. PRIMARY ATTEMPT: Featherless DeepSeek-V3.2 ────────────────────────────
    if FEATHERLESS_API_KEY:
        try:
            featherless_url = f"{FEATHERLESS_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {FEATHERLESS_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": req_model,
                "messages": messages,
                "temperature": req_temp,
                "max_tokens": req_max_tokens,
            }
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(featherless_url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = extract_json_payload(content)
                    usage = data.get("usage", {})
                    return parsed, f"featherless/{req_model}", usage
                else:
                    print(f"[LLMClient] Featherless HTTP {resp.status_code}: {resp.text[:150]} — Switching to Groq fallback.")
        except Exception as e:
            print(f"[LLMClient] Featherless exception: {e} — Switching to Groq fallback.")

    # ── 2. SECONDARY FALLBACK: Groq API ──────────────────────────────────────────
    if GROQ_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": GROQ_FALLBACK_MODEL,
                "messages": messages,
                "temperature": req_temp,
                "max_tokens": req_max_tokens,
                "response_format": {"type": "json_object"}
            }
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(GROQ_API_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = extract_json_payload(content)
                    usage = data.get("usage", {})
                    return parsed, f"groq/{GROQ_FALLBACK_MODEL}", usage
                else:
                    print(f"[LLMClient] Groq fallback HTTP {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            print(f"[LLMClient] Groq fallback exception: {e}")

    raise RuntimeError("All LLM providers (Featherless Primary & Groq Fallback) failed to return a valid response.")
