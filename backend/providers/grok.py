import os
import json
import logging
import httpx
from .base import AIProvider

logger = logging.getLogger(__name__)

GROK_API_KEY = os.getenv("GROK_API_KEY", "")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-2-latest")
GROK_BASE_URL = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")


class GrokProvider(AIProvider):
    @property
    def name(self) -> str:
        return "Grok"

    def _available(self) -> bool:
        return bool(GROK_API_KEY)

    def check_health(self) -> bool:
        if not self._available():
            return False
        try:
            headers = {
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json",
            }
            r = httpx.get(
                f"{GROK_BASE_URL}/models",
                headers=headers,
                timeout=5,
            )
            return r.status_code == 200
        except Exception:
            return False

    def generate(
        self, question: str, system_prompt: str
    ) -> dict:
        if not self._available():
            yield {"error": "Grok API key not configured"}
            return

        headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": GROK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.7,
            "max_tokens": 150,
            "stream": True,
        }

        try:
            with httpx.Client(timeout=60) as client:
                with client.stream(
                    "POST",
                    f"{GROK_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status_code != 200:
                        body = resp.read()
                        provider_err = self._classify_error(resp.status_code, body.decode())
                        yield {"error": provider_err}
                        return

                    buffer = ""
                    for chunk in resp.iter_bytes():
                        buffer += chunk.decode()
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line or not line.startswith("data: "):
                                continue
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                continue
                            try:
                                data = json.loads(data_str)
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield {"token": content}
                            except json.JSONDecodeError:
                                continue

        except httpx.TimeoutException:
            yield {"error": "timeout"}
            return
        except httpx.NetworkError:
            yield {"error": "network_error"}
            return
        except Exception as e:
            yield {"error": str(e)}
            return

    def _classify_error(self, status_code: int, body: str) -> str:
        if status_code == 429:
            return "rate_limited"
        if status_code == 403:
            return "quota_exhausted"
        if status_code == 402 or "insufficient" in body.lower():
            return "insufficient_credits"
        if status_code >= 500:
            return "provider_error"
        return f"http_{status_code}"
