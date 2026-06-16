import json
import logging
import threading
from typing import Generator, Optional

import os
import httpx
from providers import GeminiProvider, GrokProvider, LocalProvider, OpenAICompatibleProvider, AIProvider

logger = logging.getLogger(__name__)

RETRYABLE_ERRORS = {
    "rate_limited",
    "quota_exhausted",
    "insufficient_credits",
    "timeout",
    "network_error",
    "provider_error",
    "unavailable",
    "http_429",
    "http_403",
    "http_402",
    "http_500",
    "http_502",
    "http_503",
}

HEALTH_CHECK_INTERVAL = 60


class ProviderManager:
    def __init__(self):
        self._preferred_idx = 0
        self._lock = threading.Lock()
        self._last_health_check: dict[str, float] = {}
        self._health_cache: dict[str, bool] = {}

        self._providers: list[AIProvider] = [
            GeminiProvider(),
            GrokProvider(),
            LocalProvider(),
        ]

        legacy_key = os.getenv("OPENAI_API_KEY", "")
        legacy_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        legacy_model = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
        if legacy_key:
            self._providers.append(
                OpenAICompatibleProvider(legacy_key, legacy_base, legacy_model, "Groq")
            )

        backup_key = os.getenv("BACKUP_OPENAI_API_KEY", "")
        backup_base = os.getenv("BACKUP_OPENAI_BASE_URL", "")
        backup_model = os.getenv("BACKUP_MODEL", "openai/gpt-4o")
        if backup_key and backup_base:
            self._providers.append(
                OpenAICompatibleProvider(backup_key, backup_base, backup_model, "OpenRouter")
            )

    @property
    def providers(self) -> list[AIProvider]:
        return self._providers

    def _get_preferred_providers(self) -> list[AIProvider]:
        with self._lock:
            preferred = self._preferred_idx

        ordered = []
        for i in range(preferred, len(self._providers)):
            ordered.append((i, self._providers[i]))
        for i in range(preferred):
            ordered.append((i, self._providers[i]))
        return ordered

    def _set_preferred(self, idx: int):
        with self._lock:
            self._preferred_idx = idx

    def _is_retryable(self, error_str: str) -> bool:
        error_lower = error_str.lower().strip()
        if error_lower in RETRYABLE_ERRORS:
            return True
        if any(err in error_lower for err in ["rate", "quota", "credit", "limit", "timeout", "unavailable", "network", "not configured", "not_config"]):
            return True
        if error_lower.startswith("http_4") or error_lower.startswith("http_5"):
            return True
        return False

    def _run_health_checks(self):
        import time
        now = time.time()
        for idx, provider in enumerate(self._providers):
            cache_key = provider.name
            last_check = self._last_health_check.get(cache_key, 0)
            if now - last_check < HEALTH_CHECK_INTERVAL:
                continue
            try:
                healthy = provider.check_health()
                self._last_health_check[cache_key] = now
                self._health_cache[cache_key] = healthy
                if healthy and idx < self._preferred_idx:
                    logger.info(f"Healthier provider {provider.name} is back — promoting to preferred")
                    self._set_preferred(idx)
            except Exception:
                self._health_cache[cache_key] = False

    SUPPORTED_LOCAL_MODELS = ["qwen2.5", "gemma2", "llama3.2", "mistral"]

    def get_available_models(self) -> list[dict]:
        models = []

        cloud = []
        if os.getenv("GEMINI_API_KEY"):
            cloud.append({"id": "gemini", "name": "Gemini", "badges": ["cloud", "fast"]})
        if os.getenv("GROK_API_KEY"):
            cloud.append({"id": "grok", "name": "Grok", "badges": ["cloud"]})

        local = []
        try:
            r = httpx.get(f"{os.getenv('LOCAL_LLM_BASE_URL', 'http://localhost:11434/v1')}/models", timeout=3)
            if r.status_code == 200:
                installed = {m.get("id", "").split(":")[0] for m in r.json().get("data", [])}
                for model_id in self.SUPPORTED_LOCAL_MODELS:
                    if model_id in installed:
                        display = model_id[0].upper() + model_id[1:]
                        local.append({"id": model_id, "name": display, "badges": ["local", "fast"]})
        except Exception:
            pass

        legacy = []
        for p in self._providers:
            if isinstance(p, OpenAICompatibleProvider):
                legacy.append({"id": p.name.lower(), "name": p.name, "badges": ["cloud", "fast"]})

        default = None
        if legacy:
            default = legacy[0]["id"]
        elif local:
            default = local[0]["id"]
        elif cloud:
            default = cloud[0]["id"]

        if not models:
            models.extend(legacy)

        models.extend(local)
        models.extend(cloud)

        return {"models": models, "default": default or "gemini"}

    def _model_to_provider_idx(self, model: str) -> int | None:
        if not model:
            return None
        ml = model.lower()
        if ml == "gemini":
            for i, p in enumerate(self._providers):
                if isinstance(p, GeminiProvider):
                    return i
        if ml == "grok":
            for i, p in enumerate(self._providers):
                if isinstance(p, GrokProvider):
                    return i
        if ml == "groq":
            for i, p in enumerate(self._providers):
                if isinstance(p, OpenAICompatibleProvider) and "groq" in p.name.lower():
                    return i
        if ml == "openrouter":
            for i, p in enumerate(self._providers):
                if isinstance(p, OpenAICompatibleProvider) and "openrouter" in p.name.lower():
                    return i
        for i, p in enumerate(self._providers):
            if isinstance(p, LocalProvider):
                return i
        return None

    def generate(
        self, question: str, system_prompt: str, preferred_model: Optional[str] = None
    ) -> Generator[str, None, None]:
        if preferred_model:
            idx = self._model_to_provider_idx(preferred_model)
            if idx is not None:
                with self._lock:
                    self._preferred_idx = idx

        preferred = self._get_preferred_providers()
        attempted = 0
        total_providers = len(self._providers)

        for idx, provider in preferred:
            attempted += 1
            label = provider.name
            logger.info(f"Trying provider: {label}")

            yield f"data: {json.dumps({'provider': label})}\n\n"

            accumulated_tokens = []
            failed = False
            error_msg = ""

            try:
                batch = []
                for event in provider.generate(question, system_prompt):
                    if "error" in event:
                        if batch:
                            yield f"data: {json.dumps({'token': ''.join(batch)})}\n\n"
                            batch = []
                        error_msg = event["error"]
                        logger.warning(f"Provider {label} returned error: {error_msg}")
                        if self._is_retryable(error_msg):
                            failed = True
                            break
                        else:
                            yield f"data: {json.dumps({'error': error_msg})}\n\n"
                            return
                    elif "token" in event:
                        token = event["token"]
                        accumulated_tokens.append(token)
                        batch.append(token)
                        text = ''.join(batch)
                        if len(batch) >= 5 or text.rstrip().endswith(('.', '!', '?', ':', ';', '\n')):
                            yield f"data: {json.dumps({'token': text})}\n\n"
                            batch = []

                if batch:
                    yield f"data: {json.dumps({'token': ''.join(batch)})}\n\n"

                if not failed:
                    try:
                        yield f"data: {json.dumps({'done': True})}\n\n"
                    except GeneratorExit:
                        pass

                    self._set_preferred(idx)
                    return

            except GeneratorExit:
                raise
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Provider {label} raised exception: {error_msg}")
                if self._is_retryable(error_msg):
                    failed = True
                else:
                    yield f"data: {json.dumps({'error': error_msg})}\n\n"
                    return

            if failed and attempted < total_providers:
                if accumulated_tokens:
                    yield f"data: {json.dumps({'token': ' [Switching to another AI provider...]'})}\n\n"
                else:
                    yield f"data: {json.dumps({'token': 'Switching to another AI provider...'})}\n\n"

        yield f"data: {json.dumps({'error': 'All AI providers are currently unavailable. Please try again later.'})}\n\n"
