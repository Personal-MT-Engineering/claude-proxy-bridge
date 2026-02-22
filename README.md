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

## Solution Design

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL CLIENTS                              │
│                                                                        │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐  │
│   │ Telegram  │   │ OpenClaw │   │ NanoClaw │   │  Any OpenAI-     │  │
│   │   Bot     │   │ Gateway  │   │          │   │  compatible app  │  │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘   └───────┬──────────┘  │
│        │              │              │                  │              │
└────────┼──────────────┼──────────────┼──────────────────┼──────────────┘
         │              │              │                  │
         │    HTTP POST /v1/chat/completions              │
         │    or WebSocket /ws                            │
         ▼              ▼              ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│                    BRIDGE + SMART ROUTER (port 5000)                   │
│                                                                        │
│   ┌──────────────────────────────────────────────────────────────┐     │
│   │                    ws_bridge.py                               │     │
│   │                                                              │     │
│   │  HTTP: /v1/chat/completions, /v1/models, /health             │     │
│   │  WS:   /ws (bidirectional streaming)                         │     │
│   │                                                              │     │
│   │  ┌────────────────────────────────────────────────────────┐  │     │
│   │  │                  router.py                              │  │     │
│   │  │                                                        │  │     │
│   │  │  1. Estimate tokens across all messages                │  │     │
│   │  │  2. Pattern-match for complexity / code / simple       │  │     │
│   │  │  3. Score each scenario (complex, code, long,          │  │     │
│   │  │     moderate, simple)                                  │  │     │
│   │  │  4. Select primary model + fallback chain              │  │     │
│   │  │                                                        │  │     │
│   │  │  model="auto" ──► classify ──► route to best model     │  │     │
│   │  │  model="opus"  ──► honor it + attach fallback chain    │  │     │
│   │  └────────────────────────────────────────────────────────┘  │     │
│   └──────────────────────────────────────────────────────────────┘     │
│                                                                        │
└─────────┬─────────────────────┬─────────────────────┬──────────────────┘
          │                     │                     │
          ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  OPUS PROXY      │  │  SONNET PROXY    │  │  HAIKU PROXY     │
│  port 5001       │  │  port 5002       │  │  port 5003       │
│                  │  │                  │  │                  │
│  proxy_server.py │  │  proxy_server.py │  │  proxy_server.py │
│                  │  │                  │  │                  │
│  HTTP + WS       │  │  HTTP + WS       │  │  HTTP + WS       │
│  endpoints       │  │  endpoints       │  │  endpoints       │
│                  │  │                  │  │                  │
│  Fallback-aware  │  │  Fallback-aware  │  │  Fallback-aware  │
│  execution       │  │  execution       │  │  execution       │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                      claude_runner.py                            │
│                                                                  │
│  Spawns Claude Code CLI as async subprocess:                     │
│                                                                  │
│    claude -p "<prompt>"                                          │
│           --model <model_id>                                     │
│           --dangerously-skip-permissions                          │
│           --output-format stream-json   (if streaming)           │
│           --system-prompt "<system>"    (if provided)             │
│                                                                  │
│  Parses NDJSON stream ──► extracts text deltas ──► yields chunks │
└──────────────────────────────────────────────────────────────────┘
```

### Request Lifecycle

```
               ┌──────────────────────────────┐
               │       Incoming Request        │
               │  POST /v1/chat/completions    │
               │  { model, messages, stream }  │
               └──────────────┬───────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │       Authentication          │
               │  Check Authorization header   │
               │  against API_KEY              │
               └──────────────┬───────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │     Convert Messages          │
               │  messages[] ──► (system, prompt)│
               │  system msgs ──► system_prompt │
               │  user/assistant ──► prompt str │
               └──────────────┬───────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │   model == "auto" ?    │
                 └─────┬──────────┬──────┘
                  yes  │          │  no
                       ▼          ▼
          ┌─────────────────┐  ┌──────────────────────┐
          │  Smart Router   │  │  Use requested model  │
          │                 │  │  + attach fallback    │
          │  Estimate tokens│  │  chain from scenario  │
          │  Score patterns │  │  classification       │
          │  Pick scenario  │  └──────────┬───────────┘
          │  Select model   │             │
          └────────┬────────┘             │
                   │                      │
                   ▼                      ▼
          ┌──────────────────────────────────────┐
          │         RoutingDecision               │
          │  { scenario, model, fallback_chain }  │
          └──────────────────┬───────────────────┘
                             │
                ┌────────────┴────────────┐
                │     stream == true ?    │
                └────┬───────────────┬────┘
              yes    │               │  no
                     ▼               ▼
          ┌──────────────┐  ┌──────────────────┐
          │  SSE Stream  │  │  Full Response    │
          │  via HTTP    │  │  via HTTP         │
          │  or WS delta │  │  or WS done msg   │
          └──────┬───────┘  └────────┬─────────┘
                 │                   │
                 ▼                   ▼
          ┌──────────────────────────────────────┐
          │     Execute with Fallback             │
          │                                      │
          │  TRY primary model:                   │
          │    Spawn claude -p subprocess          │
          │    Parse output / stream chunks        │
          │                                      │
          │  ON FAILURE (RuntimeError):            │
          │    Log error                           │
          │    Try next model in fallback chain    │
          │    Up to ROUTING_MAX_FALLBACK_ATTEMPTS │
          │                                      │
          │  STREAM RULE:                          │
          │    If chunks already sent ──► no swap  │
          │    If failed before output ──► retry   │
          └──────────────────┬───────────────────┘
                             │
                             ▼
          ┌──────────────────────────────────────┐
          │          Return Response              │
          │                                      │
          │  HTTP: ChatCompletionResponse JSON    │
          │    or SSE chunks + [DONE]             │
          │                                      │
          │  WS: {type: "done", content, model,  │
          │       scenario}                       │
          └──────────────────────────────────────┘
```

### Smart Routing Classification

```
                        ┌──────────────┐
                        │   Request    │
                        │   messages   │
                        └──────┬───────┘
                               │
                               ▼
                  ┌────────────────────────┐
                  │   Estimate tokens      │
                  │   across all messages  │
                  └────────────┬───────────┘
                               │
                      ┌────────┴────────┐
                      │  tokens > 50k?  │
                      └───┬─────────┬───┘
                    yes   │         │  no
                          ▼         ▼
                ┌──────────┐   ┌────────────────────┐
                │  LONG    │   │  Score patterns     │
                │  ──► Opus│   │  against content    │
                └──────────┘   └─────────┬──────────┘
                                         │
                               ┌─────────┴─────────┐
                               │                   │
                    ┌──────────┴───┐    ┌──────────┴───┐
                    │  complex     │    │  code        │
                    │  patterns:   │    │  patterns:   │
                    │  reasoning,  │    │  ```,        │
                    │  trade-offs, │    │  languages,  │
                    │  step-by-step│    │  write/fix,  │
                    │  + reasoning │    │  imports     │
                    │  patterns    │    │              │
                    └──────┬───────┘    └──────┬───────┘
                           │                   │
                    ┌──────┴───┐        ┌──────┴───┐
                    │ score>=3 │        │ score>=3 │
                    └──┬───┬───┘        └──┬───┬───┘
                  yes  │   │ no       yes  │   │ no
                       ▼   │              ▼   │
              ┌─────────┐  │    ┌──────────┐  │
              │ COMPLEX  │  │    │   CODE   │  │
              │ ──► Opus │  │    │ ──►Sonnet│  │
              └─────────┘  │    └──────────┘  │
                           ▼                  ▼
                  ┌──────────────────────────────┐
                  │  simple patterns:             │
                  │  greetings, short msgs,       │
                  │  definitions                  │
                  │                              │
                  │  score>=3 AND complex<2       │
                  │  AND code<2 AND moderate<2?   │
                  └──────────┬─────┬─────────────┘
                        yes  │     │  no
                             ▼     ▼
                  ┌──────────┐  ┌───────────────────┐
                  │  SIMPLE  │  │  Check remaining   │
                  │ ──► Haiku│  │  code>=2? ──► CODE │
                  └──────────┘  │  complex>=2?──►COMP│
                                │  moderate>=2? ──►  │
                                │  tokens>200? ──►   │
                                │      MODERATE      │
                                │  else ──► MODERATE │
                                └───────────────────┘
```

### Fallback Chain Execution

```
     ┌───────────────────────────────────────────┐
     │  Example: scenario=complex                │
     │  Primary: Opus                            │
     │  Fallback: [Sonnet, Haiku]                │
     │  Max attempts: 2                          │
     └─────────────────┬─────────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Try Opus       │
              │  claude -p ...  │
              │  --model opus   │
              └────┬───────┬────┘
            ok     │       │  error
                   ▼       ▼
          ┌─────────┐  ┌──────────────────┐
          │ Return  │  │ Log: "Opus fail" │
          │ response│  │ attempt 1/2      │
          └─────────┘  └────────┬─────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │  Try Sonnet     │
                       │  claude -p ...  │
                       │  --model sonnet │
                       └────┬───────┬────┘
                     ok     │       │  error
                            ▼       ▼
                   ┌─────────┐  ┌──────────────────┐
                   │ Return  │  │ Log: "Sonnet fail"│
                   │ response│  │ attempt 2/2       │
                   └─────────┘  └────────┬──────────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │  Try Haiku      │
                                │  claude -p ...  │
                                │  --model haiku  │
                                └────┬───────┬────┘
                              ok     │       │  error
                                     ▼       ▼
                            ┌─────────┐  ┌────────────┐
                            │ Return  │  │ HTTP 502   │
                            │ response│  │ All models │
                            └─────────┘  │ failed     │
                                         └────────────┘

     STREAMING FALLBACK RULE:
     ┌────────────────────────────────────────────┐
     │  If chunks already sent to client:         │
     │    ──► Cannot swap model mid-stream        │
     │    ──► Append error text, finish stream    │
     │                                            │
     │  If failed BEFORE any output:              │
     │    ──► Try next model in chain             │
     │    ──► Client sees no interruption         │
     └────────────────────────────────────────────┘
```

### Module Dependency Graph

```
  start.py
    │
    ├──► src/config.py ◄──────────────────────────┐
    │      Settings, ModelConfig, MODEL_MAP        │
    │                                              │
    ├──► src/ws_bridge.py                          │
    │      │  create_bridge_app()                  │
    │      │  HTTP + WS on port 5000               │
    │      ├──► src/router.py                      │
    │      │      route_request()                  │
    │      │      classify_scenario()              │
    │      │      ├──► src/config.py ──────────────┘
    │      │      └──► src/openai_types.py
    │      │             ChatCompletionRequest
    │      │             ChatMessage
    │      └──► src/proxy_server.py
    │             run_with_fallback()
    │             stream_with_fallback()
    │
    └──► src/proxy_server.py
           │  create_proxy_app()
           │  HTTP + WS on ports 5001-5003
           ├──► src/router.py
           ├──► src/claude_runner.py
           │      run_claude()
           │      stream_claude()
           │      └──► src/config.py
           └──► src/openai_types.py
                  ChatCompletionResponse
                  ChatCompletionChunk
                  ModelListResponse
```

### Integration Points

```
┌────────────────────────────────────────────────────────────────────┐
│                      INTEGRATION OPTIONS                          │
│                                                                    │
│  ┌─── OpenClaw ───────────────────────────────────────────────┐   │
│  │                                                            │   │
│  │  configs/openclaw_provider.json5                           │   │
│  │                                                            │   │
│  │  Registers 4 providers:                                    │   │
│  │    claude-proxy-opus   ──► http://127.0.0.1:5001/v1       │   │
│  │    claude-proxy-sonnet ──► http://127.0.0.1:5002/v1       │   │
│  │    claude-proxy-haiku  ──► http://127.0.0.1:5003/v1       │   │
│  │    claude-proxy-auto   ──► http://127.0.0.1:5000/v1       │   │
│  │                                                            │   │
│  │  Agent defaults:                                           │   │
│  │    large ──► claude-proxy-auto/auto  (smart routing)       │   │
│  │    small ──► claude-proxy-haiku/claude-haiku-4-5           │   │
│  │                                                            │   │
│  │  Telegram channel:                                         │   │
│  │    User ──► Telegram Bot ──► OpenClaw ──► Bridge ──► CLI   │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌─── NanoClaw ───────────────────────────────────────────────┐   │
│  │                                                            │   │
│  │  Option A: HTTP (OpenAI-compatible)                        │   │
│  │    baseUrl: http://127.0.0.1:5001/v1                      │   │
│  │    apiKey: local-proxy                                     │   │
│  │                                                            │   │
│  │  Option B: WebSocket bridge                                │   │
│  │    ws://127.0.0.1:5000/ws                                 │   │
│  │    Send: {model: "auto", messages: [...]}                  │   │
│  │    Recv: {type: "delta"/"done", content: "..."}            │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌─── Any OpenAI Client ──────────────────────────────────────┐   │
│  │                                                            │   │
│  │  from openai import OpenAI                                 │   │
│  │  client = OpenAI(                                          │   │
│  │      base_url="http://127.0.0.1:5000/v1",                │   │
│  │      api_key="local-proxy"                                 │   │
│  │  )                                                         │   │
│  │  client.chat.completions.create(                           │   │
│  │      model="auto",  # smart routing                        │   │
│  │      messages=[...]                                        │   │
│  │  )                                                         │   │
│  └────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
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
