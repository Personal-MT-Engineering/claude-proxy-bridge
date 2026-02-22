"""Runner dispatcher — picks claude_runner or http_runner per model config."""

import logging
from collections.abc import AsyncGenerator

from .claude_runner import run_claude, stream_claude
from .config import ModelConfig
from .http_runner import run_http, stream_http
from .openai_types import ChatCompletionRequest

logger = logging.getLogger(__name__)


def _messages_to_dicts(request: ChatCompletionRequest) -> list[dict[str, str]]:
    """Convert request messages to plain dicts for the HTTP runner."""
    return [{"role": m.role, "content": m.content} for m in request.messages]


async def run_model(request: ChatCompletionRequest, model_config: ModelConfig) -> str:
    """Run a model and return the full response text.

    Dispatches to claude_runner (subprocess) or http_runner (API call)
    based on the model's provider type.
    """
    provider = model_config.provider

    if provider.type == "claude_cli":
        system_prompt, prompt = request.to_prompt()
        return await run_claude(
            prompt=prompt,
            model_id=model_config.model_id,
            system_prompt=system_prompt,
        )

    # HTTP provider (OpenAI-compatible)
    messages = _messages_to_dicts(request)
    return await run_http(
        messages,
        model_config.model_id,
        base_url=provider.base_url,
        api_key=provider.api_key,
        extra_headers=provider.extra_headers or None,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )


async def stream_model(
    request: ChatCompletionRequest, model_config: ModelConfig
) -> AsyncGenerator[str, None]:
    """Stream a model response, yielding text chunks.

    Dispatches to claude_runner (subprocess) or http_runner (API call)
    based on the model's provider type.
    """
    provider = model_config.provider

    if provider.type == "claude_cli":
        system_prompt, prompt = request.to_prompt()
        async for text in stream_claude(
            prompt=prompt,
            model_id=model_config.model_id,
            system_prompt=system_prompt,
        ):
            yield text
        return

    # HTTP provider (OpenAI-compatible)
    messages = _messages_to_dicts(request)
    async for text in stream_http(
        messages,
        model_config.model_id,
        base_url=provider.base_url,
        api_key=provider.api_key,
        extra_headers=provider.extra_headers or None,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    ):
        yield text
