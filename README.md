# Claude Proxy Bridge

Reverse proxy that wraps [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) as **OpenAI-compatible API endpoints** with smart model routing and automatic fallback chains.

```
Client (OpenClaw / NanoClaw / Telegram / curl)
    |
    v
┌──────────────────────────────────────────┐
│      WebSocket Bridge (port 5000)        │
│      + Smart Router (model="auto")       │
└─────┬────────────┬────────────┬──────────┘
      |            |            |
      v            v            v
  Port 5001    Port 5002    Port 5003
   (Opus)      (Sonnet)     (Haiku)
      |            |            |
      v            v            v
  claude -p    claude -p    claude -p
  --model      --model      --model
  opus-4-6     sonnet-4-6   haiku-4-5
```

Each model gets its own proxy with HTTP and WebSocket endpoints. The bridge on port 5000 adds smart routing that analyzes requests and picks the best model automatically.

## Features

- **OpenAI-compatible API** — drop-in `/v1/chat/completions` and `/v1/models` endpoints
- **Smart routing** — send `model: "auto"` and the router classifies your request:

  | Scenario | Primary Model | Fallback Chain | What triggers it |
  |----------|--------------|----------------|------------------|
  | `complex` | Opus | Sonnet → Haiku | Reasoning, architecture, step-by-step analysis, trade-offs |
  | `code` | Sonnet | Opus → Haiku | Code blocks, language keywords, "write/implement/fix" |
  | `long` | Opus | Sonnet | Token count exceeds threshold (default 50k) |
  | `moderate` | Sonnet | Haiku → Opus | Explanations, comparisons, "how to", best practices |
  | `simple` | Haiku | Sonnet | Greetings, short questions, definitions |

- **Fallback chains** — if a model fails (CLI error, timeout), the next model in the chain is tried automatically (up to 2 retries by default)
- **Streaming** — SSE streaming via HTTP and bidirectional WebSocket streaming
- **WebSocket bridge** — central router on port 5000 handles model selection and proxying
- **Cross-platform** — works on Windows, macOS, and Linux
- **Configurable** — override models, fallback chains, thresholds, and ports via `.env`

## Prerequisites

- **Python 3.10+**
- **Claude Code CLI** installed and on your PATH ([installation guide](https://docs.anthropic.com/en/docs/claude-code))
  ```bash
  npm install -g @anthropic-ai/claude-code
  ```

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/Personal-MT-Engineering/claude-proxy-bridge.git
cd claude-proxy-bridge
```

**Linux/macOS:**
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
source .venv/bin/activate
```

**Windows:**
```cmd
scripts\setup.bat
.venv\Scripts\activate
```

**Or manually:**
```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .
cp .env.example .env
```

### 2. Start the bridge

```bash
python start.py
```

This starts 4 servers:
- `http://127.0.0.1:5001` — Opus proxy
- `http://127.0.0.1:5002` — Sonnet proxy
- `http://127.0.0.1:5003` — Haiku proxy
- `ws://127.0.0.1:5000` — WebSocket bridge + smart router

### 3. Verify

```bash
python scripts/health_check.py
```

## Usage

### HTTP — Direct model

```bash
curl http://localhost:5001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-proxy" \
  -d '{
    "model": "claude-opus-4-6",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### HTTP — Smart routing

Send to the bridge (port 5000) with `model: "auto"`:

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-proxy" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Explain the trade-offs of microservices vs monolith"}]
  }'
```

The router will detect this as a `complex` request and route to Opus. A simple "hello" would route to Haiku.

### HTTP — Streaming

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-proxy" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Write a Python quicksort"}],
    "stream": true
  }'
```

### WebSocket

Connect to `ws://localhost:5000/ws` and send JSON:

```json
{
  "model": "auto",
  "messages": [{"role": "user", "content": "Hello!"}],
  "stream": true
}
```

Responses:
```json
{"type": "routing", "scenario": "simple", "model": "claude-haiku-4-5-20251001", "reason": "...", "fallback": ["claude-sonnet-4-6"]}
{"type": "delta", "content": "Hi"}
{"type": "delta", "content": " there!"}
{"type": "done", "content": "Hi there!", "model": "claude-haiku-4-5-20251001", "scenario": "simple"}
```

### List available models

```bash
curl http://localhost:5000/v1/models \
  -H "Authorization: Bearer local-proxy"
```

## Configuration

Copy `.env.example` to `.env` and edit:

```env
# Server
HOST=127.0.0.1
OPUS_PORT=5001
SONNET_PORT=5002
HAIKU_PORT=5003
BRIDGE_PORT=5000
API_KEY=local-proxy

# Timeouts & concurrency
REQUEST_TIMEOUT=300
MAX_CONCURRENT=5

# Smart routing
SMART_ROUTING=true
ROUTING_LONG_CONTEXT_THRESHOLD=50000
ROUTING_MAX_FALLBACK_ATTEMPTS=2

# Override which model handles each scenario
# ROUTING_MODEL_COMPLEX=claude-opus-4-6
# ROUTING_MODEL_CODE=claude-sonnet-4-6
# ROUTING_MODEL_MODERATE=claude-sonnet-4-6
# ROUTING_MODEL_SIMPLE=claude-haiku-4-5-20251001

# Override fallback chains (comma-separated, tried in order)
# ROUTING_FALLBACK_COMPLEX=claude-opus-4-6,claude-sonnet-4-6,claude-haiku-4-5-20251001
```

Set `SMART_ROUTING=false` to disable routing entirely — each proxy only serves its own model.

## OpenClaw Integration

Copy or merge `configs/openclaw_provider.json5` into your OpenClaw config:

```bash
cp configs/openclaw_provider.json5 ~/.openclaw/providers/claude-proxy.json5
```

This registers all three model proxies plus the `auto` smart router as OpenClaw providers. The default agent config routes `large` tasks through the smart router and `small` tasks through Haiku.

For Telegram bot setup, see [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md).

## NanoClaw Integration

See [configs/nanoclaw_skill.md](configs/nanoclaw_skill.md) for instructions on connecting NanoClaw to the proxy bridge via HTTP or WebSocket.

## Project Structure

```
claude-proxy-bridge/
├── start.py                  # Entry point — starts all 4 servers
├── src/
│   ├── config.py             # Settings & environment variable loading
│   ├── router.py             # Smart routing engine & fallback chains
│   ├── claude_runner.py      # Claude CLI subprocess manager
│   ├── openai_types.py       # OpenAI-compatible Pydantic models
│   ├── proxy_server.py       # FastAPI app per model (HTTP + WS)
│   └── ws_bridge.py          # Central WebSocket bridge/router
├── configs/
│   ├── openclaw_provider.json5
│   └── nanoclaw_skill.md
├── scripts/
│   ├── setup.sh              # Linux/macOS setup
│   ├── setup.bat             # Windows setup
│   └── health_check.py       # Health check utility
├── pyproject.toml
├── .env.example
└── TELEGRAM_SETUP.md
```

## How Smart Routing Works

The router in `src/router.py` classifies each request by:

1. **Token estimation** — counts approximate tokens across all messages
2. **Pattern matching** — scans message content for complexity/code/simple signals using regex
3. **Context scoring** — factors in message count, system prompt presence, conversation length
4. **Scenario selection** — picks the highest-scoring scenario
5. **Model assignment** — maps scenario to primary model + fallback chain

When a model fails, `run_with_fallback()` / `stream_with_fallback()` in `proxy_server.py` automatically tries the next model in the chain. For streaming, fallback only activates if the model fails _before_ producing any output (no silent mid-stream model swaps).

## API Reference

All proxies (ports 5001-5003) and the bridge (port 5000) expose:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completions (OpenAI-compatible) |
| `/v1/models` | GET | List available models |
| `/ws` | WebSocket | Bidirectional streaming |
| `/health` | GET | Health check |

The bridge additionally accepts `model: "auto"` (or `"smart"`, `"router"`) to enable smart routing on any endpoint.

## License

MIT
