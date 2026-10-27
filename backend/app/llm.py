"""Gọi LLM qua provider OpenAI-compatible. Trả (nội dung, usage)."""
import json, time

import httpx

from app import config

_client = httpx.Client(base_url=config.LLM_BASE_URL, headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
                       timeout=httpx.Timeout(25, connect=5))  # treo quá 25 s → thử model dự phòng


# provider hay lỗi 429/503 theo đợt ("No available channel") → thử lại bằng model dự phòng
FALLBACK_MODELS = ["gpt-4.1-mini", "gemini-3.5-flash"]


class LLMError(RuntimeError):
    pass


def parse_json(text):
    """Một số model (gemini) bọc JSON trong ```json … ``` → bỏ rào trước khi parse."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    return json.loads(t)


def chat(messages, model=None, json_mode=False, temperature=0.2, max_tokens=1200):
    first = model or config.LLM_MODEL_ONLINE
    models = [first, *(m for m in FALLBACK_MODELS if m != first)]
    body = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    last = None
    for attempt in range(4):
        body["model"] = models[attempt % len(models)]
        try:
            r = _client.post("/chat/completions", json=body)
            if r.status_code in (401, 402, 403):
                raise LLMError(f"provider từ chối ({r.status_code}): {r.text[:200]}")
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            usage = {**(data.get("usage") or {}), "_model": body["model"], "_attempt": attempt + 1}
            return (parse_json(text) if json_mode else text), usage
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
            last = e
            time.sleep(0.5 * (attempt + 1))
    raise LLMError(str(last))
