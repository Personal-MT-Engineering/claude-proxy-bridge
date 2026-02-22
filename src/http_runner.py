"""Generic HTTP runner for OpenAI-compatible APIs.

Calls any provider that speaks the OpenAI Chat Completions format:
OpenAI, DeepSeek, Gemini, Ollama, OpenRouter, Groq, Mistral, Together AI, etc.
"""

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from .config import settings

logger = logging.getLogger(__name__)


async def run_http(
    messages: list[dict[str, str]],
    model_id: str,
    *,
    base_url: str,
    api_key: str = "",
    extra_headers: dict[str, str] | None = None,
    timeout: int | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Call an OpenAI-compatible chat completions endpoint (non-streaming).

    Returns the assistant's response text.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    timeout = timeout or settings.request_timeout

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)

    payload: dict = {
        "model": model_id,
        "messages": messages,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    logger.info("HTTP request: model=%s url=%s msgs=%d", model_id, url, len(messages))

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code != 200:
        body = resp.text[:500]
        logger.error("HTTP %d from %s: %s", resp.status_code, url, body)
        raise RuntimeError(f"HTTP {resp.status_code} from {model_id}: {body}")

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"No choices in response from {model_id}")

    text = choices[0].get("message", {}).get("content", "")
    if not text:
        raise RuntimeError(f"Empty response from {model_id}")

    logger.info("HTTP response from %s: %d chars", model_id, len(text))
    return text


async def stream_http(
    messages: list[dict[str, str]],
    model_id: str,
    *,
    base_url: str,
    api_key: str = "",
    extra_headers: dict[str, str] | None = None,
    timeout: int | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """Stream from an OpenAI-compatible chat completions endpoint.

    Reads SSE lines and yields text deltas.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    timeout = timeout or settings.request_timeout

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)

    payload: dict = {
        "model": model_id,
        "messages": messages,
        "stream": True,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    logger.info("HTTP stream: model=%s url=%s msgs=%d", model_id, url, len(messages))

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                logger.error("HTTP %d from %s: %s", resp.status_code, url, body[:500])
                raise RuntimeError(f"HTTP {resp.status_code} from {model_id}: {body[:500]}")

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]  # strip "data: " prefix
                if data_str == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
