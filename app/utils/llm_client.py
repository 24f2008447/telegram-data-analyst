"""
Minimal wrapper around an OpenAI-compatible /chat/completions endpoint.
Kept dependency-light (just `requests`) so it's easy to swap providers.
"""
import json
import time
import requests

from app.config import settings


class LLMError(RuntimeError):
    pass


def chat(system_prompt: str, user_content: str, json_mode: bool = True, temperature: float = 0.0,
         max_retries: int = 1, timeout: int = 30) -> str:
    """Send a single-turn (system + user) chat completion request. Returns raw text content.
    Retries transient network/5xx/429 failures with backoff, but keeps the retry budget small:
    grading questions have a fixed timeout (commonly a few minutes), and this call may be one of
    several in a single run (planner -> SQL writer -> formatter, plus download attempts), so an
    over-long retry chain on any single call can eat the whole budget by itself."""
    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY is not set")

    url = f"{settings.openai_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(1.0 * (attempt + 1))
            continue

        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        last_error = f"{resp.status_code} {resp.text[:500]}"
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
            time.sleep(1.0 * (attempt + 1))
            continue
        break

    raise LLMError(f"LLM call failed after retries: {last_error}")


def chat_json(system_prompt: str, user_content: str, temperature: float = 0.0) -> dict:
    """Call chat() and parse the result as JSON, stripping accidental code fences."""
    raw = chat(system_prompt, user_content, json_mode=True, temperature=temperature)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM did not return valid JSON: {e}\nRaw: {raw[:500]}")
