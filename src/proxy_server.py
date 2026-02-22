"""FastAPI proxy server — one instance per model, exposes OpenAI-compatible endpoints.

Supports smart routing (model="auto") and fallback chains on failure.
"""

import asyncio
import json
import logging
import uuid

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .claude_runner import run_claude, stream_claude
from .config import ModelConfig, settings
from .openai_types import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelInfo,
    ModelListResponse,
)
from .router import RoutingDecision, route_request

logger = logging.getLogger(__name__)


async def run_with_fallback(
    prompt: str,
    system_prompt: str | None,
    decision: RoutingDecision,
) -> tuple[str, ModelConfig]:
    """Run Claude CLI with fallback chain. Returns (response_text, model_used).

    Tries the primary model first. On failure, walks down the fallback chain
    up to `max_fallback_attempts` times.
    """
    max_attempts = settings.routing_max_fallback_attempts
    chain = [decision.model] + decision.fallback_chain[:max_attempts]
    last_error: Exception | None = None

    for i, mc in enumerate(chain):
        try:
            if i > 0:
                logger.warning(
                    "Fallback attempt %d/%d: trying %s (after %s failed)",
                    i, max_attempts, mc.name, chain[i - 1].name,
                )
            text = await run_claude(
                prompt=prompt,
                model_id=mc.model_id,
                system_prompt=system_prompt,
            )
            return text, mc
        except RuntimeError as e:
            last_error = e
            logger.error("Model %s failed: %s", mc.name, e)
            if i >= max_attempts:
                break

    raise RuntimeError(
        f"All models failed. Last error from {chain[min(max_attempts, len(chain) - 1)].name}: {last_error}"
    )


async def stream_with_fallback(
    prompt: str,
    system_prompt: str | None,
    decision: RoutingDecision,
):
    """Stream from Claude CLI with fallback. Yields (text_chunk, model_config).

    If the primary model fails before producing any output, tries the next
    model in the fallback chain. Once streaming has started, errors are
    yielded as text (no silent model switch mid-stream).
    """
    max_attempts = settings.routing_max_fallback_attempts
    chain = [decision.model] + decision.fallback_chain[:max_attempts]
    last_error: Exception | None = None

    for i, mc in enumerate(chain):
        try:
            if i > 0:
                logger.warning(
                    "Stream fallback attempt %d/%d: trying %s",
                    i, max_attempts, mc.name,
                )
            started = False
            async for text in stream_claude(
                prompt=prompt,
                model_id=mc.model_id,
                system_prompt=system_prompt,
            ):
                started = True
                yield text, mc

            # Completed successfully
            return

        except RuntimeError as e:
            last_error = e
            logger.error("Stream model %s failed: %s", mc.name, e)
            if started:
                # Already sent chunks — can't switch model silently
                yield f"\n\n[Error: {e}]", mc
                return
            if i >= max_attempts:
                break

    raise RuntimeError(
        f"All stream models failed. Last error: {last_error}"
    )


def create_proxy_app(model_config: ModelConfig) -> FastAPI:
    """Create a FastAPI app for a specific model."""
    app = FastAPI(
        title=f"Claude Proxy - {model_config.name.title()}",
        description=f"OpenAI-compatible proxy for Claude {model_config.name.title()} via Claude Code CLI",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _semaphore = asyncio.Semaphore(settings.max_concurrent)

    def _check_auth(authorization: str | None) -> None:
        if not settings.api_key:
            return
        if not authorization:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        token = authorization.removeprefix("Bearer ").strip()
        if token != settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    def _resolve_routing(request: ChatCompletionRequest) -> RoutingDecision:
        """Determine routing: smart route or use this proxy's model with fallback."""
        if settings.smart_routing_enabled and request.model.lower() in ("auto", "smart", "router"):
            return route_request(request)

        # This proxy's own model — still get a fallback chain via the router
        request_copy = request.model_copy(update={"model": model_config.model_id})
        return route_request(request_copy)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "model": model_config.model_id,
            "name": model_config.name,
            "port": model_config.port,
            "smart_routing": settings.smart_routing_enabled,
        }

    @app.get("/v1/models")
    async def list_models(authorization: str | None = Header(default=None)):
        _check_auth(authorization)
        models = [ModelInfo(id=model_config.model_id)]
        if settings.smart_routing_enabled:
            models.append(ModelInfo(id="auto", owned_by="claude-proxy-bridge-router"))
        return ModelListResponse(data=models)

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: ChatCompletionRequest,
        authorization: str | None = Header(default=None),
    ):
        _check_auth(authorization)

        system_prompt, prompt = request.to_prompt()
        if not prompt:
            raise HTTPException(status_code=400, detail="No prompt content in messages")

        decision = _resolve_routing(request)
        logger.info(
            "Chat request: scenario=%s model=%s stream=%s reason='%s' fallback=%s",
            decision.scenario.value, decision.model.name, request.stream,
            decision.reason, [m.name for m in decision.fallback_chain],
        )

        if request.stream:
            return StreamingResponse(
                _stream_sse(prompt, system_prompt, decision),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # Non-streaming with fallback
        async with _semaphore:
            try:
                text, used_model = await run_with_fallback(prompt, system_prompt, decision)
            except RuntimeError as e:
                raise HTTPException(status_code=502, detail=str(e))

        resp = ChatCompletionResponse.from_text(text, used_model.model_id)
        # Add routing metadata in a custom header-friendly field
        resp.model = used_model.model_id
        return resp

    async def _stream_sse(prompt: str, system_prompt: str | None, decision: RoutingDecision):
        """Generate SSE stream with fallback support."""
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        actual_model = decision.model.model_id

        # Send initial chunk with role
        first = ChatCompletionChunk.first_chunk(actual_model, chunk_id)
        yield f"data: {first.model_dump_json()}\n\n"

        async with _semaphore:
            try:
                async for text, used_mc in stream_with_fallback(prompt, system_prompt, decision):
                    actual_model = used_mc.model_id
                    chunk = ChatCompletionChunk.text_chunk(text, actual_model, chunk_id)
                    yield f"data: {chunk.model_dump_json()}\n\n"
            except RuntimeError as e:
                err_chunk = ChatCompletionChunk.text_chunk(
                    f"\n\n[Error: {e}]", actual_model, chunk_id
                )
                yield f"data: {err_chunk.model_dump_json()}\n\n"

        done = ChatCompletionChunk.done_chunk(actual_model, chunk_id)
        yield f"data: {done.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        logger.info("WebSocket connected to %s proxy", model_config.name)

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "content": "Invalid JSON"})
                    continue

                try:
                    request = ChatCompletionRequest(**data)
                except Exception as e:
                    await ws.send_json({"type": "error", "content": f"Invalid request: {e}"})
                    continue

                system_prompt, prompt = request.to_prompt()
                if not prompt:
                    await ws.send_json({"type": "error", "content": "Empty prompt"})
                    continue

                decision = _resolve_routing(request)
                await ws.send_json({
                    "type": "routing",
                    "scenario": decision.scenario.value,
                    "model": decision.model.model_id,
                    "reason": decision.reason,
                    "fallback": [m.model_id for m in decision.fallback_chain],
                })

                stream = data.get("stream", False)

                if stream:
                    async with _semaphore:
                        full_text = []
                        actual_model = decision.model
                        try:
                            async for text, used_mc in stream_with_fallback(
                                prompt, system_prompt, decision
                            ):
                                actual_model = used_mc
                                full_text.append(text)
                                await ws.send_json({"type": "delta", "content": text})
                        except RuntimeError as e:
                            await ws.send_json({"type": "error", "content": str(e)})
                            continue

                    await ws.send_json({
                        "type": "done",
                        "content": "".join(full_text),
                        "model": actual_model.model_id,
                        "scenario": decision.scenario.value,
                    })
                else:
                    async with _semaphore:
                        try:
                            text, used_model = await run_with_fallback(
                                prompt, system_prompt, decision
                            )
                        except RuntimeError as e:
                            await ws.send_json({"type": "error", "content": str(e)})
                            continue

                    await ws.send_json({
                        "type": "done",
                        "content": text,
                        "model": used_model.model_id,
                        "scenario": decision.scenario.value,
                    })

        except WebSocketDisconnect:
            logger.info("WebSocket disconnected from %s proxy", model_config.name)

    return app
