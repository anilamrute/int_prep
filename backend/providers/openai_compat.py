import os
import json
import logging
import httpx
from .base import AIProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, api_key: str, base_url: str, model: str, label: str):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._label = label

    @property
    def name(self) -> str:
        return self._label

    def _available(self) -> bool:
        return bool(self._api_key)

    def check_health(self) -> bool:
        if not self._available():
            return False
        try:
            headers = {"Authorization": f"Bearer {self._api_key}"}
            r = httpx.get(
                f"{self._base_url}/models",
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
            yield {"error": f"{self._label} not configured"}
            return

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.7,
            "max_tokens": 500,
            "stream": True,
        }

        try:
            with httpx.Client(timeout=60) as client:
                with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    if resp.status_code != 200:
                        body = resp.read()
                        err = self._classify_error(resp.status_code, body.decode())
                        yield {"error": err}
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
