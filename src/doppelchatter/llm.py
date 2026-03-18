"""LLM client with OpenRouter and Anthropic support, streaming and fallback chain."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from enum import StrEnum

import httpx

from doppelchatter.models import (
    GenerationTimeoutError,
    LLMError,
    ModelUnavailableError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
XAI_BASE_URL = "https://api.x.ai/v1"
ANTHROPIC_API_VERSION = "2023-06-01"


class Provider(StrEnum):
    OPENROUTER = "openrouter"
    ANTHROPIC = "anthropic"
    XAI = "xai"


def _resolve_provider(model: str, anthropic_api_key: str, xai_api_key: str = "") -> Provider:
    """Determine which provider to use for a given model.

    Uses Anthropic directly when:
    - An Anthropic API key is available, AND
    - The model is a Claude model (starts with 'anthropic/' or 'claude')
    """
    normalised = model.lower()

    if anthropic_api_key and (normalised.startswith("anthropic/") or normalised.startswith("claude")):
        return Provider.ANTHROPIC

    if xai_api_key and (normalised.startswith("xai/") or normalised.startswith("grok")):
        return Provider.XAI

    return Provider.OPENROUTER


def _strip_provider_prefix(model: str) -> str:
    """Strip 'anthropic/' prefix for direct Anthropic API calls."""
    if model.lower().startswith("anthropic/"):
        return model[len("anthropic/"):]
    return model


class LLMClient:
    """Multi-provider LLM client with streaming and fallback chain.

    Supports OpenRouter (default) and Anthropic (direct) APIs.
    """

    def __init__(
        self,
        api_key: str,
        anthropic_api_key: str = "",
        xai_api_key: str = "",
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._anthropic_api_key = anthropic_api_key
        self._xai_api_key = xai_api_key

        self._openrouter_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/axiotic-ai/doppelchatter",
                "X-Title": "Doppelchatter",
            },
        )

        self._anthropic_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={
                "x-api-key": anthropic_api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
        ) if anthropic_api_key else None

        self._xai_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={
                "Authorization": f"Bearer {xai_api_key}",
                "Content-Type": "application/json",
            },
        ) if xai_api_key else None

    async def stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.85,
        max_tokens: int = 512,
        fallback_chain: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens. Falls back through model chain on failure."""
        models = [model] + (fallback_chain or [])

        for i, current_model in enumerate(models):
            try:
                provider = _resolve_provider(
                    current_model, self._anthropic_api_key, self._xai_api_key
                )

                if provider == Provider.ANTHROPIC:
                    async for token in self._stream_anthropic(
                        current_model, messages, temperature, max_tokens
                    ):
                        yield token
                elif provider == Provider.XAI:
                    async for token in self._stream_xai(
                        current_model, messages, temperature, max_tokens
                    ):
                        yield token
                else:
                    async for token in self._stream_openrouter(
                        current_model, messages, temperature, max_tokens
                    ):
                        yield token
                return
            except Exception as e:
                is_last = i == len(models) - 1
                logger.warning(
                    f"Model {current_model} failed: {e}. "
                    f"{'No more fallbacks.' if is_last else 'Trying next.'}"
                )
                if is_last:
                    raise

    async def _stream_openrouter(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from OpenRouter API."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            async with self._openrouter_client.stream(
                "POST",
                f"{OPENROUTER_BASE_URL}/chat/completions",
                json=payload,
            ) as response:
                if response.status_code == 429:
                    retry_after = float(response.headers.get("retry-after", "5"))
                    raise RateLimitError(retry_after)
                if response.status_code == 404:
                    raise ModelUnavailableError(f"Model not found: {model}")
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        content = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        except httpx.TimeoutException as e:
            raise GenerationTimeoutError(f"Timeout streaming from {model}") from e
        except (RateLimitError, ModelUnavailableError, GenerationTimeoutError):
            raise
        except httpx.HTTPStatusError as e:
            raise LLMError(f"HTTP error from {model}: {e.response.status_code}") from e

    async def _stream_anthropic(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Stream from Anthropic Messages API directly."""
        if not self._anthropic_client:
            raise LLMError("Anthropic API key not configured")

        bare_model = _strip_provider_prefix(model)

        # Separate system message from conversation messages
        system_text = ""
        conversation: list[dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_text = msg.get("content", "")
            else:
                conversation.append(msg)

        payload: dict[str, object] = {
            "model": bare_model,
            "messages": conversation,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text

        try:
            async with self._anthropic_client.stream(
                "POST",
                f"{ANTHROPIC_BASE_URL}/messages",
                json=payload,
            ) as response:
                if response.status_code == 429:
                    retry_after = float(response.headers.get("retry-after", "5"))
                    raise RateLimitError(retry_after)
                if response.status_code == 404:
                    raise ModelUnavailableError(f"Model not found: {bare_model}")
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    try:
                        event = json.loads(data)
                        event_type = event.get("type", "")

                        if event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield text

                        elif event_type == "message_stop":
                            break

                        elif event_type == "error":
                            error_msg = event.get("error", {}).get("message", "Unknown error")
                            raise LLMError(f"Anthropic error: {error_msg}")

                    except json.JSONDecodeError:
                        continue

        except httpx.TimeoutException as e:
            raise GenerationTimeoutError(f"Timeout streaming from {bare_model}") from e
        except (RateLimitError, ModelUnavailableError, GenerationTimeoutError):
            raise
        except httpx.HTTPStatusError as e:
            raise LLMError(f"HTTP error from Anthropic ({bare_model}): {e.response.status_code}") from e

    async def close(self) -> None:
        await self._openrouter_client.aclose()
        if self._anthropic_client:
            await self._anthropic_client.aclose()
