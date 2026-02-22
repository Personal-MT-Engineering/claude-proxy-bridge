# Claude Proxy Bridge Integration

## Overview

This skill teaches NanoClaw how to use the Claude Proxy Bridge as its LLM backend.
The bridge exposes Claude Code CLI models (Opus, Sonnet, Haiku) as OpenAI-compatible endpoints.

## Endpoints

| Model | HTTP Endpoint | WebSocket |
|-------|--------------|-----------|
| Opus 4.6 | `http://127.0.0.1:5001/v1/chat/completions` | `ws://127.0.0.1:5001/ws` |
| Sonnet 4.6 | `http://127.0.0.1:5002/v1/chat/completions` | `ws://127.0.0.1:5002/ws` |
| Haiku 4.5 | `http://127.0.0.1:5003/v1/chat/completions` | `ws://127.0.0.1:5003/ws` |
| Bridge (auto-route) | — | `ws://127.0.0.1:5000/ws` |

API Key: `local-proxy` (configurable in `.env`)

## How to Connect NanoClaw

### Option 1: Direct HTTP (OpenAI-compatible)

In your NanoClaw configuration or `src/container-runner.ts`, set the LLM provider to use the proxy:

```typescript
const llmConfig = {
  baseUrl: "http://127.0.0.1:5001/v1",  // Opus
  apiKey: "local-proxy",
  model: "claude-opus-4-6",
};
```

### Option 2: WebSocket Bridge

Connect to `ws://127.0.0.1:5000/ws` and send JSON requests:

```json
{
  "model": "claude-opus-4-6",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": true
}
```

Responses come back as:
- `{"type": "delta", "content": "chunk of text"}` — streamed text
- `{"type": "done", "content": "full response", "model": "claude-opus-4-6"}` — final response
- `{"type": "error", "content": "error message"}` — errors

### Option 3: Model Selection Strategy

Use different models for different tasks:
- **Opus** (`claude-opus-4-6`): Complex reasoning, code generation, architecture decisions
- **Sonnet** (`claude-sonnet-4-6`): General-purpose tasks, balanced speed/quality
- **Haiku** (`claude-haiku-4-5-20251001`): Fast responses, simple queries, classification

## Prerequisites

1. Install and start the Claude Proxy Bridge:
   ```bash
   cd claude-proxy-bridge
   pip install -e .
   python start.py
   ```

2. Verify it's running:
   ```bash
   curl http://127.0.0.1:5001/health
   ```

## Troubleshooting

- If the proxy returns 502 errors, check that `claude` CLI is on your PATH
- If connections are refused, ensure the proxy is running on the expected ports
- Check proxy logs (printed to stdout) for detailed error messages
