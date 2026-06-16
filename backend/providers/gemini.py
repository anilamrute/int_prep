import os
import json
import logging
import httpx
from .base import AIProvider

logger = logging.getLogger(__name__)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


class GeminiProvider(AIProvider):
    @property
    def name(self) -> str:
        return "Gemini"

    def _available(self) -> bool:
        return bool(GEMINI_API_KEY)

    def check_health(self) -> bool:
        if not self._available():
            return False
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}?key={GEMINI_API_KEY}"
            r = httpx.get(url, timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def generate(
        self, question: str, system_prompt: str
    ) -> dict:
        if not self._available():
            yield {"error": "Gemini API key not configured"}
            return

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"

        payload = {
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 150,
            },
        }

        try:
            with httpx.Client(timeout=60) as client:
                with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        body = resp.read()
                        err_text = body.decode()
                        provider_err = self._classify_error(resp.status_code, err_text)
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
                                candidates = data.get("candidates", [])
                                if candidates:
                                    content = candidates[0].get("content", {})
                                    parts = content.get("parts", [])
                                    for part in parts:
                                        text = part.get("text", "")
                                        if text:
                                            yield {"token": text}
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
        if status_code == 402:
            return "insufficient_credits"
        if status_code >= 500:
            return "provider_error"
        return f"http_{status_code}"
