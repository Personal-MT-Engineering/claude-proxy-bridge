"""Central WebSocket bridge/router — routes requests to the appropriate model proxy.

Supports model="auto" for smart routing via the router module.
"""

import asyncio
import json
import logging

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .config import MODEL_MAP, settings
from .openai_types import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelInfo,
    ModelListResponse,
)
from .proxy_server import run_with_fallback, stream_with_fallback
from .router import RoutingDecision, route_request

logger = logging.getLogger(__name__)


def create_bridge_app() -> FastAPI:
    """Create the central WebSocket bridge FastAPI app."""
    app = FastAPI(
        title="Claude Proxy Bridge - Smart Router",
        description="Routes requests to the appropriate model proxy with smart routing and fallback",
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
        """Smart route or look up the requested model."""
        model_key = request.model.lower().strip()
        if settings.smart_routing_enabled and model_key in ("auto", "smart", "router", ""):
            return route_request(request)

        mc = MODEL_MAP.get(model_key)
        if not mc:
            # Try smart routing as fallback for unknown model IDs
            return route_request(request)
        # Explicit model with fallback chain
        request_copy = request.model_copy(update={"model": mc.model_id})
        return route_request(request_copy)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": "ws-bridge",
            "port": settings.bridge_port,
            "smart_routing": settings.smart_routing_enabled,
            "available_models": [m.model_id for m in settings.models] + ["auto"],
        }

    @app.get("/v1/models")
    async def list_all_models(authorization: str | None = Header(default=None)):
        _check_auth(authorization)
        models = [ModelInfo(id=m.model_id) for m in settings.models]
        models.append(ModelInfo(id="auto", owned_by="claude-proxy-bridge-router"))
        return ModelListResponse(data=models)

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: ChatCompletionRequest,
        authorization: str | None = Header(default=None),
    ):
        """OpenAI-compatible chat endpoint on the bridge — smart routes by default."""
        _check_auth(authorization)

        if not any(m.content for m in request.messages):
            raise HTTPException(status_code=400, detail="No prompt content in messages")

        decision = _resolve_routing(request)
        logger.info(
            "Bridge chat: scenario=%s model=%s stream=%s reason='%s' fallback=%s",
            decision.scenario.value, decision.model.name, request.stream,
            decision.reason, [m.name for m in decision.fallback_chain],
        )

        if request.stream:
            return StreamingResponse(
                _stream_sse(request, decision),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        async with _semaphore:
            try:
                text, used_model = await run_with_fallback(request, decision)
            except RuntimeError as e:
                raise HTTPException(status_code=502, detail=str(e))

        return ChatCompletionResponse.from_text(text, used_model.model_id)

    async def _stream_sse(request: ChatCompletionRequest, decision: RoutingDecision):
        """SSE stream with smart routing and fallback."""
        import uuid
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        actual_model = decision.model.model_id

        first = ChatCompletionChunk.first_chunk(actual_model, chunk_id)
        yield f"data: {first.model_dump_json()}\n\n"

        async with _semaphore:
            try:
                async for text, used_mc in stream_with_fallback(request, decision):
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
    async def bridge_ws(ws: WebSocket):
        await ws.accept()
        logger.info("Client connected to WebSocket bridge")

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "content": "Invalid JSON"})
                    continue

                # Parse into request for routing
                try:
                    request = ChatCompletionRequest(**data)
                except Exception as e:
                    await ws.send_json({"type": "error", "content": f"Invalid request: {e}"})
                    continue

                if not any(m.content for m in request.messages):
                    await ws.send_json({"type": "error", "content": "Empty prompt"})
                    continue

                decision = _resolve_routing(request)

                # Tell the client which model was chosen and why
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
                                request, decision
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
                                request, decision
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
            logger.info("Client disconnected from WebSocket bridge")

    return app
