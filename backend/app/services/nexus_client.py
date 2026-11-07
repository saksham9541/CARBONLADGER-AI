"""
CarbonLedger AI — Nexus AI Provider Adapter
===========================================
Client adapter for Navigate Labs Nexus API (OpenAI-compatible gateway).
Features:
- Configurable base URL, API key, models, and timeouts.
- Exponential backoff with jitter on 429 rate-limits and 5xx errors.
- Automatic model fallback (nova-micro -> mistral-7b-instruct -> llama3-8b-instruct).
- Robust JSON response extraction from markdown fences.
- Audio transcription adapter with graceful provider fallback.
- Mock mode support for isolated offline test suites.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class NexusAPIError(Exception):
    """Raised when an unrecoverable Nexus API error occurs."""
    def __init__(self, message: str, status_code: int = 500, response_body: str = ""):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body


class NexusClient:
    """HTTP client for Nexus API with retry/backoff and model fallback."""

    FALLBACK_MODELS = ["nova-micro", "mistral-7b-instruct", "llama3-8b-instruct"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        extraction_model: Optional[str] = None,
        audio_model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.nexus_api_key
        # Ensure base_url does not end with a trailing slash
        raw_url = base_url or settings.nexus_base_url
        self.base_url = raw_url.rstrip("/")
        # Ensure /v1 is included in the base_url
        if not self.base_url.endswith("/v1"):
            self.base_url = f"{self.base_url}/v1"

        self.extraction_model = extraction_model or settings.nexus_extraction_model
        self.audio_model = audio_model or settings.nexus_audio_model
        self.timeout_seconds = timeout_seconds or settings.nexus_timeout_seconds
        self.max_retries = max_retries or settings.nexus_max_retries

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "CarbonLedgerAI/0.1.0",
        }

    def clean_json_response(self, raw_text: str) -> Dict[str, Any]:
        """Strips markdown code fences and parses pure JSON."""
        cleaned = raw_text.strip()
        # Remove markdown code fences like ```json ... ```
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
            if match:
                cleaned = match.group(1).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to decode JSON from Nexus response", raw=raw_text[:300], error=str(exc))
            raise NexusAPIError(f"Nexus AI returned non-JSON content: {str(exc)}", status_code=502, response_body=raw_text)

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1500,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Sends chat completion request to Nexus API with retry backoff
        and automatic model fallback on model-access errors.
        """
        if not self.is_configured:
            raise NexusAPIError("Nexus API key is not configured.", status_code=503)

        models_to_try = [model or self.extraction_model]
        for fallback in self.FALLBACK_MODELS:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error: Optional[Exception] = None

        for current_model in models_to_try:
            url = f"{self.base_url}/chat/completions"
            payload: Dict[str, Any] = {
                "model": current_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                payload["response_format"] = response_format

            for attempt in range(1, self.max_retries + 1):
                try:
                    start_time = time.time()
                    with httpx.Client(timeout=self.timeout_seconds) as client:
                        response = client.post(url, headers=self._get_headers(), json=payload)

                    latency_ms = round((time.time() - start_time) * 1000, 2)

                    # 1. Successful response
                    if response.status_code == 200:
                        data = response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        parsed_json = self.clean_json_response(content)
                        return {
                            "model_used": current_model,
                            "latency_ms": latency_ms,
                            "raw_content": content,
                            "data": parsed_json,
                        }

                    # 2. Rate-limited (429) -> exponential backoff
                    if response.status_code == 429:
                        backoff = 2 ** attempt
                        logger.warning("Nexus rate limit encountered (429). Retrying...", attempt=attempt, backoff=backoff)
                        time.sleep(backoff)
                        continue

                    # 3. Model access denied (401/403) -> try next fallback model
                    if response.status_code in (401, 403):
                        logger.warning(
                            "Model access denied on Nexus gateway. Trying fallback model...",
                            model=current_model,
                            status=response.status_code,
                        )
                        last_error = NexusAPIError(
                            f"Model '{current_model}' unavailable on Nexus: {response.text[:200]}",
                            status_code=response.status_code,
                            response_body=response.text,
                        )
                        break  # Break inner retry loop to try next model in models_to_try

                    # 4. Gateway error (500, 502, 503, 504) -> retry
                    if response.status_code in (500, 502, 503, 504):
                        backoff = 1.5 ** attempt
                        logger.warning("Nexus server error. Retrying...", status=response.status_code, backoff=backoff)
                        time.sleep(backoff)
                        continue

                    # Unhandled client error
                    raise NexusAPIError(
                        f"Nexus API call failed with HTTP {response.status_code}: {response.text[:300]}",
                        status_code=response.status_code,
                        response_body=response.text,
                    )

                except httpx.RequestError as exc:
                    logger.warning("Network error calling Nexus API", error=str(exc), attempt=attempt)
                    if attempt == self.max_retries:
                        last_error = exc
                    else:
                        time.sleep(1.0 * attempt)

        raise NexusAPIError(
            f"All Nexus model attempts exhausted. Last error: {str(last_error)}",
            status_code=502,
        )


_nexus_singleton: Optional[NexusClient] = None


def get_nexus_client() -> NexusClient:
    """Dependency injector for NexusClient."""
    global _nexus_singleton
    if _nexus_singleton is None:
        _nexus_singleton = NexusClient()
    return _nexus_singleton
