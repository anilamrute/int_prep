import os
import json
import logging
import httpx
from .base import AIProvider

logger = logging.getLogger(__name__)

LOCAL_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
LOCAL_MODEL = os.getenv("LOCAL_LLM_MODEL", "")


class LocalProvider(AIProvider):
    @property
    def name(self) -> str:
        return "Local AI"

    def _available(self) -> bool:
        return bool(LOCAL_MODEL)

    def check_health(self) -> bool:
        if not self._available():
            return False
        try:
            r = httpx.get(f"{LOCAL_BASE_URL}/models", timeout=3)
            if r.status_code != 200:
                return False
            models = r.json().get("data", [])
            model_name = LOCAL_MODEL.split(":")[0]
            return any(m.get("id", "").split(":")[0] == model_name for m in models)
        except Exception:
            return False

    def generate(
        self, question: str, system_prompt: str
    ) -> dict:
        if not self._available():
            yield {"error": "Local LLM not configured"}
            return

        payload = {
            "model": LOCAL_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "temperature": 0.7,
            "max_tokens": 500,
            "stream": True,
        }

        try:
            with httpx.Client(timeout=120) as client:
                with client.stream(
                    "POST",
                    f"{LOCAL_BASE_URL}/chat/completions",
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = resp.read()
                        err_text = body.decode()
                        logger.warning(f"Local LLM returned {resp.status_code}: {err_text[:200]}")
                        yield {"error": "unavailable"}
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
            yield {"error": "unavailable"}
            return
        except Exception as e:
            yield {"error": str(e)}
            return
