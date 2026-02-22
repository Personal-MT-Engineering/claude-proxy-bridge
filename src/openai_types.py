"""OpenAI-compatible request/response Pydantic models."""

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field


# --- Request models ---

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | str | None = None

    def to_prompt(self) -> tuple[str | None, str]:
        """Convert messages array to (system_prompt, user_prompt) for Claude CLI.

        Concatenates system messages as the system prompt, and all
        user/assistant messages into a conversation string.
        """
        system_parts: list[str] = []
        conversation_parts: list[str] = []

        for msg in self.messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            elif msg.role == "user":
                conversation_parts.append(f"Human: {msg.content}")
            elif msg.role == "assistant":
                conversation_parts.append(f"Assistant: {msg.content}")

        system_prompt = "\n\n".join(system_parts) if system_parts else None

        if conversation_parts:
            prompt = "\n\n".join(conversation_parts)
        else:
            # Fallback: join all message content
            prompt = "\n\n".join(m.content for m in self.messages if m.content)

        return system_prompt, prompt


# --- Response models ---

class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[Choice] = []
    usage: Usage = Field(default_factory=Usage)

    @classmethod
    def from_text(cls, text: str, model: str) -> "ChatCompletionResponse":
        return cls(
            model=model,
            choices=[
                Choice(
                    message=ChatMessage(role="assistant", content=text),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                # Rough token estimate (1 token ~ 4 chars)
                prompt_tokens=0,
                completion_tokens=max(1, len(text) // 4),
                total_tokens=max(1, len(text) // 4),
            ),
        )


# --- Streaming chunk models ---

class DeltaContent(BaseModel):
    role: str | None = None
    content: str | None = None


class StreamChoice(BaseModel):
    index: int = 0
    delta: DeltaContent = Field(default_factory=DeltaContent)
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = ""
    choices: list[StreamChoice] = []

    @classmethod
    def first_chunk(cls, model: str, chunk_id: str) -> "ChatCompletionChunk":
        """Initial chunk with role."""
        return cls(
            id=chunk_id,
            model=model,
            choices=[StreamChoice(delta=DeltaContent(role="assistant", content=""))],
        )

    @classmethod
    def text_chunk(cls, text: str, model: str, chunk_id: str) -> "ChatCompletionChunk":
        """Content delta chunk."""
        return cls(
            id=chunk_id,
            model=model,
            choices=[StreamChoice(delta=DeltaContent(content=text))],
        )

    @classmethod
    def done_chunk(cls, model: str, chunk_id: str) -> "ChatCompletionChunk":
        """Final chunk with finish_reason."""
        return cls(
            id=chunk_id,
            model=model,
            choices=[StreamChoice(delta=DeltaContent(), finish_reason="stop")],
        )


# --- Model listing ---

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "claude-proxy-bridge"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo] = []
