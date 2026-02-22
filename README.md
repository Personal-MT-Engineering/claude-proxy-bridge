# Claude Proxy Bridge

Multi-provider reverse proxy that exposes **any LLM** as **OpenAI-compatible API endpoints** with smart model routing and automatic fallback chains.

```
Clients (OpenClaw / NanoClaw / Telegram / curl)
    │
    ▼
Bridge (port 5000) + Smart Router
    │
    ├──► Port 5001: claude-opus-4-6     (Claude CLI subprocess)
    ├──► Port 5002: claude-sonnet-4-6   (Claude CLI subprocess)
    ├──► Port 5003: gpt-4o              (HTTP → api.openai.com)
    ├──► Port 5004: deepseek-chat       (HTTP → api.deepseek.com)
    ├──► Port 5005: gemini-2.5-flash    (HTTP → googleapis.com)
    ├──► Port 5006: llama3              (HTTP → localhost:11434)
    └──► ...any model from any provider
```

Each model gets its own proxy with HTTP and WebSocket endpoints. The bridge on port 5000 adds smart routing that analyzes requests and picks the best model automatically — across all providers.

## Features

- **Multi-provider** — Claude CLI, OpenAI, DeepSeek, Gemini, Ollama, OpenRouter, Groq, Mistral, Together AI, or any OpenAI-compatible API
- **OpenAI-compatible API** — drop-in `/v1/chat/completions` and `/v1/models` endpoints
- **Smart routing** — send `model: "auto"` and the router classifies your request:

  | Scenario | Default Model | Fallback Chain | What triggers it |
  |----------|--------------|----------------|------------------|
  | `complex` | Opus | Sonnet → Haiku | Reasoning, architecture, step-by-step analysis, trade-offs |
  | `code` | Sonnet | Opus → Haiku | Code blocks, language keywords, "write/implement/fix" |
  | `long` | Opus | Sonnet | Token count exceeds threshold (default 50k) |
  | `moderate` | Sonnet | Haiku → Opus | Explanations, comparisons, "how to", best practices |
  | `simple` | Haiku | Sonnet | Greetings, short questions, definitions |

  > Routing is fully configurable via `bridge.yaml` — map any scenario to any model from any provider.

- **Fallback chains** — if a model fails, the next model in the chain is tried automatically (up to 2 retries, even across providers)
- **Streaming** — SSE streaming via HTTP and bidirectional WebSocket streaming
- **WebSocket bridge** — central router on port 5000 handles model selection and proxying
- **Interactive installer** — `python install.py` walks you through provider selection, API keys, model config, and OpenClaw/NanoClaw integration
- **Backward compatible** — without `bridge.yaml`, behaves identically to v1 (3 Claude CLI models)
- **Cross-platform** — works on Windows, macOS, and Linux

## Two Runner Types

| Type | How it works | Providers |
|------|-------------|-----------|
| `claude_cli` | Spawns `claude -p` subprocess | Claude Code CLI |
| `http` | Calls OpenAI-compatible API via `httpx` | OpenAI, DeepSeek, Gemini, Ollama, OpenRouter, Groq, Mistral, Together AI, any custom endpoint |

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | Required |
| Node.js | 18+ | Only if using Claude CLI provider |
| Claude Code CLI | latest | Only if using Claude CLI provider |
| API keys | — | Only for HTTP providers you select |

## Installation

### Option A: Interactive Installer (recommended)

```bash
git clone https://github.com/Personal-MT-Engineering/claude-proxy-bridge.git
cd claude-proxy-bridge
python install.py
```

The installer will:

1. Detect your OS and check prerequisites
2. Let you pick providers (Claude CLI, OpenAI, DeepSeek, Gemini, Ollama, etc.)
3. Collect API keys for selected providers
4. Let you choose which models to enable per provider
5. Auto-generate smart routing config based on model capabilities
6. Optionally configure OpenClaw or NanoClaw integration
7. Write `bridge.yaml`, `.env`, create venv, install dependencies

```
$ python install.py

────────────────────────────────────────────────────────
  Claude Proxy Bridge — Universal Installer
────────────────────────────────────────────────────────
  Detected: Windows 11 (AMD64)
  Python:   3.12.0

────────────────────────────────────────────────────────
  Prerequisite Checks
────────────────────────────────────────────────────────
  [OK]   Python: 3.12.0
  [OK]   pip: pip 24.0
  [OK]   Node.js: v22.0.0
  [OK]   Claude Code CLI: 1.0.0
  [SKIP] Ollama (not installed — needed only if you select it)

────────────────────────────────────────────────────────
  Provider Selection
────────────────────────────────────────────────────────
  Which LLM providers do you want to use?
    [ 1] Claude Code CLI (local, no API key needed)
    [ 2] OpenAI (GPT-4o, GPT-4o-mini, o1)
    [ 3] Anthropic API (Claude via HTTP — needs API key)
    [ 4] DeepSeek (DeepSeek-V3, DeepSeek-R1)
    [ 5] Google Gemini (Gemini 2.5 Flash, Pro)
    [ 6] Ollama (local models, no API key)
    [ 7] OpenRouter (100+ models via one key)
    [ 8] Together AI
    [ 9] Groq (fast inference)
    [10] Mistral
    [11] Custom HTTP endpoint
  Enter numbers (e.g. 1,2,6): █
```

### Option B: Manual Setup (Claude CLI only)

For backward-compatible setup with just Claude models (no `bridge.yaml` needed):

```bash
git clone https://github.com/Personal-MT-Engineering/claude-proxy-bridge.git
cd claude-proxy-bridge
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -e .
cp .env.example .env
python start.py
```

### Option C: Setup Scripts

```bash
# Linux/macOS
chmod +x scripts/setup.sh && ./scripts/setup.sh

# Windows
scripts\setup.bat
```

## Quick Start

```bash
# Activate venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# Start the bridge
python start.py
```

Output:

```
12:00:00 [INFO] Found Claude CLI: /usr/local/bin/claude
12:00:00 [INFO] ============================================================
12:00:00 [INFO] Claude Proxy Bridge is starting up!
12:00:00 [INFO] ============================================================
12:00:00 [INFO]   Opus (claude-cli)              → http://127.0.0.1:5001/v1/chat/completions
12:00:00 [INFO]   Sonnet (claude-cli)            → http://127.0.0.1:5002/v1/chat/completions
12:00:00 [INFO]   Gpt-4O (openai)                → http://127.0.0.1:5003/v1/chat/completions
12:00:00 [INFO]   Llama3 (ollama)                → http://127.0.0.1:5004/v1/chat/completions
12:00:00 [INFO]   Bridge (Smart Router)          → ws://127.0.0.1:5000/ws
12:00:00 [INFO] ============================================================
```

Health check:

```bash
python scripts/health_check.py
```

Smoke test:

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-proxy" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Say hello in one word"}]}'
```

## Configuration

### `bridge.yaml` (multi-provider config)

This is the primary configuration file. Copy from the template:

```bash
cp configs/bridge.example.yaml bridge.yaml
```

Structure:

```yaml
providers:
  claude-cli:
    type: claude_cli
    cli_path: ""                  # auto-detect

  openai:
    type: http
    base_url: "https://api.openai.com/v1"
    api_key: "${OPENAI_API_KEY}"  # resolved from environment

  ollama:
    type: http
    base_url: "http://localhost:11434/v1"
    api_key: "ollama"

models:
  opus:
    provider: claude-cli
    model_id: "claude-opus-4-6"
    port: 5001

  gpt-4o:
    provider: openai
    model_id: "gpt-4o"
    port: 5003

  llama3:
    provider: ollama
    model_id: "llama3"
    port: 5004

routing:
  scenario_models:
    complex: opus
    code: gpt-4o
    simple: llama3
  fallback_chains:
    complex: [opus, gpt-4o, llama3]
    simple: [llama3, gpt-4o]
```

**API key resolution**: Use `${ENV_VAR}` syntax in `api_key` fields — values are resolved from environment variables at startup.

**Backward compatibility**: If no `bridge.yaml` exists, the bridge defaults to 3 Claude CLI models (Opus:5001, Sonnet:5002, Haiku:5003) with the same routing as v1.

### Supported Providers

| Provider | Base URL | API Key Env Var |
|---|---|---|
| Claude Code CLI | *(subprocess)* | *(none — uses local CLI)* |
| OpenAI | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| Anthropic API | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` |
| DeepSeek | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` |
| Ollama | `http://localhost:11434/v1` | *(none)* |
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| Together AI | `https://api.together.xyz/v1` | `TOGETHER_API_KEY` |
| Groq | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| Mistral | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` |
| Custom | Any URL | Any |

### `.env` (environment variables)

```env
HOST=127.0.0.1
BRIDGE_PORT=5000
API_KEY=local-proxy
REQUEST_TIMEOUT=300
MAX_CONCURRENT=5
LOG_LEVEL=INFO
SMART_ROUTING=true
ROUTING_LONG_CONTEXT_THRESHOLD=50000
ROUTING_MAX_FALLBACK_ATTEMPTS=2

# API keys (referenced by bridge.yaml)
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
```

Env-var overrides for routing still work on top of `bridge.yaml`:
```env
ROUTING_MODEL_COMPLEX=claude-opus-4-6
ROUTING_FALLBACK_COMPLEX=claude-opus-4-6,gpt-4o,llama3
```

## Usage

### HTTP — Smart routing

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-proxy" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Explain the trade-offs of microservices vs monolith"}]
  }'
```

The router detects this as `complex` and routes to the most capable model. A simple "hello" routes to the cheapest/fastest model.

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
{"type": "routing", "scenario": "simple", "model": "llama3", "reason": "...", "fallback": ["gpt-4o"]}
{"type": "delta", "content": "Hi"}
{"type": "delta", "content": " there!"}
{"type": "done", "content": "Hi there!", "model": "llama3", "scenario": "simple"}
```

### List available models

```bash
curl http://localhost:5000/v1/models \
  -H "Authorization: Bearer local-proxy"
```

## OpenClaw Integration

### Step 1: Install OpenClaw

```bash
git clone https://github.com/open-claw/openclaw.git
cd openclaw
npm install
```

### Step 2: Register the proxy as a custom provider

**If you used the installer** (`python install.py` with OpenClaw option), the config at `~/.openclaw/openclaw.json` was generated automatically with all your bridge models.

**If setting up manually**, copy the included provider config:

```bash
cp configs/openclaw_provider.json5 /path/to/openclaw/config/providers/claude-proxy.json5
```

Or merge into your OpenClaw config. The default config registers:

| Provider ID | Endpoint | Model |
|---|---|---|
| `claude-proxy-opus` | `http://127.0.0.1:5001/v1` | `claude-opus-4-6` |
| `claude-proxy-sonnet` | `http://127.0.0.1:5002/v1` | `claude-sonnet-4-6` |
| `claude-proxy-haiku` | `http://127.0.0.1:5003/v1` | `claude-haiku-4-5` |
| `claude-proxy-auto` | `http://127.0.0.1:5000/v1` | `auto` (smart router) |

When using multi-provider, the installer generates one provider entry per configured model plus a `bridge-auto` entry for the smart router.

<details>
<summary>Full provider config (click to expand)</summary>

```json5
{
  "models": {
    "mode": "merge",
    "providers": {
      "claude-proxy-opus": {
        "baseUrl": "http://127.0.0.1:5001/v1",
        "apiKey": "local-proxy",
        "api": "openai-completions",
        "models": [{
          "id": "claude-opus-4-6",
          "name": "Claude Opus 4.6 (Local Proxy)",
          "reasoning": true,
          "input": ["text"],
          "contextWindow": 200000,
          "maxTokens": 16384
        }]
      },
      "claude-proxy-sonnet": {
        "baseUrl": "http://127.0.0.1:5002/v1",
        "apiKey": "local-proxy",
        "api": "openai-completions",
        "models": [{
          "id": "claude-sonnet-4-6",
          "name": "Claude Sonnet 4.6 (Local Proxy)",
          "input": ["text"],
          "contextWindow": 200000,
          "maxTokens": 16384
        }]
      },
      "claude-proxy-haiku": {
        "baseUrl": "http://127.0.0.1:5003/v1",
        "apiKey": "local-proxy",
        "api": "openai-completions",
        "models": [{
          "id": "claude-haiku-4-5",
          "name": "Claude Haiku 4.5 (Local Proxy)",
          "input": ["text"],
          "contextWindow": 200000,
          "maxTokens": 16384
        }]
      },
      "claude-proxy-auto": {
        "baseUrl": "http://127.0.0.1:5000/v1",
        "apiKey": "local-proxy",
        "api": "openai-completions",
        "models": [{
          "id": "auto",
          "name": "Claude Auto (Smart Router)",
          "reasoning": true,
          "input": ["text"],
          "contextWindow": 200000,
          "maxTokens": 16384
        }]
      }
    }
  },
  "agents": {
    "defaults": {
      "models": {
        "large": "claude-proxy-auto/auto",
        "small": "claude-proxy-haiku/claude-haiku-4-5"
      }
    }
  }
}
```

</details>

### Step 3: Configure agent model defaults

The provider config sets:

- **`large`** (complex tasks) routes to `claude-proxy-auto/auto` — the smart router picks the best model
- **`small`** (simple tasks) routes directly to `claude-proxy-haiku/claude-haiku-4-5`

### Step 4: Set up a Telegram bot (optional)

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`, choose a name and username
3. Save the API token
4. Add to your OpenClaw config:

```json5
{
  "channels": {
    "telegram": {
      "botToken": "YOUR_BOT_TOKEN_HERE",
      "dmPolicy": "pairing"
    }
  }
}
```

### Step 5: Start both services

```bash
# Terminal 1 — Proxy bridge
cd claude-proxy-bridge && source .venv/bin/activate && python start.py

# Terminal 2 — OpenClaw
cd openclaw && npm start
```

---

## NanoClaw Integration

### HTTP (recommended)

Point NanoClaw at the bridge:

```json
{
  "llm": {
    "baseUrl": "http://127.0.0.1:5000/v1",
    "apiKey": "local-proxy",
    "model": "auto"
  }
}
```

Or target a specific model:

| Model | baseUrl |
|---|---|
| Smart Router | `http://127.0.0.1:5000/v1` |
| Any configured model | `http://127.0.0.1:<port>/v1` |

### WebSocket

Connect to `ws://127.0.0.1:5000/ws` for bidirectional streaming with routing metadata.

### Start both services

```bash
# Terminal 1 — Proxy bridge
cd claude-proxy-bridge && source .venv/bin/activate && python start.py

# Terminal 2 — NanoClaw
cd nanoclaw && npm start
```

---

## Using with any OpenAI-compatible client

### Python

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:5000/v1",
    api_key="local-proxy",
)

response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Explain Docker in simple terms"}],
)
print(response.choices[0].message.content)
```

### JavaScript/TypeScript

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:5000/v1",
  apiKey: "local-proxy",
});

const response = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);
```

### curl

```bash
curl http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-proxy" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello!"}]}'
```

## Project Structure

```
claude-proxy-bridge/
├── start.py                  # Entry point — starts all servers
├── install.py                # Universal interactive installer
├── bridge.yaml               # Multi-provider config (generated by installer)
├── src/
│   ├── config.py             # Settings, ProviderConfig, YAML loading
│   ├── router.py             # Smart routing engine & fallback chains
│   ├── runners.py            # Dispatcher: claude_runner or http_runner
│   ├── claude_runner.py      # Claude CLI subprocess manager
│   ├── http_runner.py        # Generic HTTP runner (OpenAI-compatible APIs)
│   ├── openai_types.py       # OpenAI-compatible Pydantic models
│   ├── proxy_server.py       # FastAPI app per model (HTTP + WS)
│   └── ws_bridge.py          # Central WebSocket bridge/router
├── configs/
│   ├── bridge.example.yaml   # Full config template with all providers
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
└────────┼──────────────┼──────────────┼──────────────────┼──────────────┘
         │              │              │                  │
         ▼              ▼              ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    BRIDGE + SMART ROUTER (port 5000)                   │
│                                                                        │
│   ws_bridge.py → router.py → runners.py                                │
│                                                                        │
│   HTTP: /v1/chat/completions, /v1/models, /health                      │
│   WS:   /ws (bidirectional streaming)                                  │
│                                                                        │
│   model="auto" → classify → route to best model from ANY provider      │
└─────┬──────────┬──────────┬──────────┬──────────┬──────────────────────┘
      │          │          │          │          │
      ▼          ▼          ▼          ▼          ▼
┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│Port 5001 ││Port 5002 ││Port 5003 ││Port 5004 ││Port 5005 │
│Opus      ││Sonnet    ││GPT-4o    ││DeepSeek  ││Llama3    │
│claude_cli││claude_cli││  http    ││  http    ││  http    │
└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘
     │           │           │           │           │
     ▼           ▼           ▼           ▼           ▼
┌──────────────────┐  ┌──────────────────────────────────────┐
│ claude_runner.py │  │          http_runner.py               │
│                  │  │                                      │
│ Spawns CLI:      │  │ POST {base_url}/chat/completions    │
│ claude -p "..."  │  │ Authorization: Bearer {api_key}      │
│ --model <id>     │  │                                      │
│ --stream-json    │  │ Works with: OpenAI, DeepSeek,       │
│                  │  │ Gemini, Ollama, OpenRouter, Groq,    │
│                  │  │ Mistral, Together AI, any custom     │
└──────────────────┘  └──────────────────────────────────────┘
```

### Runner Dispatch Flow

```
             ┌──────────────────────────┐
             │   ChatCompletionRequest  │
             │   { model, messages }    │
             └────────────┬─────────────┘
                          │
                          ▼
               ┌──────────────────────┐
               │    runners.py        │
               │    run_model() /     │
               │    stream_model()    │
               └─────┬──────────┬────┘
                     │          │
        provider.type│          │provider.type
        == claude_cli│          │== http
                     ▼          ▼
          ┌──────────────┐  ┌──────────────────┐
          │claude_runner │  │  http_runner      │
          │              │  │                   │
          │ to_prompt()  │  │ messages as-is    │
          │ → (sys, usr) │  │ → POST /chat/     │
          │ → subprocess │  │   completions     │
          └──────────────┘  └──────────────────┘
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
                ┌──────────┐   ┌──────────────────┐
                │  LONG    │   │  Score patterns   │
                │  → best  │   │  against content  │
                │  model   │   └─────────┬────────┘
                └──────────┘             │
                              ┌──────────┴──────────┐
                              │  complex >= 3?      │──yes──► COMPLEX
                              │  code >= 3?         │──yes──► CODE
                              │  simple >= 3?       │──yes──► SIMPLE
                              │  code >= 2?         │──yes──► CODE
                              │  complex >= 2?      │──yes──► COMPLEX
                              │  moderate >= 2?     │──yes──► MODERATE
                              │  else               │──────► MODERATE
                              └─────────────────────┘
```

### Fallback Chain Execution

```
     ┌───────────────────────────────────────────┐
     │  Example: scenario=complex                │
     │  Primary: Opus (claude_cli)               │
     │  Fallback: [GPT-4o (http), Llama3 (http)] │
     │  Max attempts: 2                          │
     └─────────────────┬─────────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Try Opus       │──── ok ──► Return response
              │  (claude_cli)   │
              └────────┬────────┘
                  error │
                       ▼
              ┌─────────────────┐
              │  Try GPT-4o     │──── ok ──► Return response
              │  (http → OpenAI)│
              └────────┬────────┘
                  error │
                       ▼
              ┌─────────────────┐
              │  Try Llama3     │──── ok ──► Return response
              │  (http → Ollama)│
              └────────┬────────┘
                  error │
                       ▼
              ┌─────────────────┐
              │  HTTP 502       │
              │  All failed     │
              └─────────────────┘

     STREAMING FALLBACK RULE:
     ┌────────────────────────────────────────────┐
     │  If chunks already sent to client:         │
     │    → Cannot swap model mid-stream          │
     │    → Append error text, finish stream      │
     │                                            │
     │  If failed BEFORE any output:              │
     │    → Try next model (even different        │
     │      provider type)                        │
     │    → Client sees no interruption           │
     └────────────────────────────────────────────┘
```

### Module Dependency Graph

```
  start.py
    │
    ├──► src/config.py ◄──────────────────────────────┐
    │      Settings, ProviderConfig, ModelConfig       │
    │      load_bridge_yaml(), MODEL_MAP               │
    │                                                  │
    ├──► src/ws_bridge.py                              │
    │      │  create_bridge_app()                      │
    │      │  HTTP + WS on port 5000                   │
    │      ├──► src/router.py                          │
    │      │      route_request(), classify_scenario()  │
    │      │      _build_routing_tables() ◄── config   │
    │      │      └──► src/openai_types.py             │
    │      └──► src/proxy_server.py                    │
    │             run_with_fallback()                   │
    │             stream_with_fallback()                │
    │                                                  │
    └──► src/proxy_server.py                           │
           │  create_proxy_app()                       │
           │  HTTP + WS on ports 5001+                 │
           ├──► src/router.py                          │
           ├──► src/runners.py ◄── NEW dispatcher      │
           │      run_model() / stream_model()         │
           │      ├──► src/claude_runner.py             │
           │      │      run_claude() / stream_claude() │
           │      └──► src/http_runner.py  ◄── NEW     │
           │             run_http() / stream_http()     │
           │             └──► src/config.py ───────────┘
           └──► src/openai_types.py
                  ChatCompletionResponse
                  ChatCompletionChunk
                  ModelListResponse
```

## How Smart Routing Works

The router in `src/router.py` classifies each request by:

1. **Token estimation** — counts approximate tokens across all messages
2. **Pattern matching** — scans message content for complexity/code/simple signals using regex
3. **Context scoring** — factors in message count, system prompt presence, conversation length
4. **Scenario selection** — picks the highest-scoring scenario
5. **Model assignment** — maps scenario to primary model + fallback chain (from `bridge.yaml` or defaults)

When a model fails, `run_with_fallback()` / `stream_with_fallback()` in `proxy_server.py` automatically tries the next model in the chain — even across different provider types (e.g., Claude CLI → OpenAI HTTP → Ollama). For streaming, fallback only activates if the model fails _before_ producing any output.

## API Reference

All proxies and the bridge expose:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completions (OpenAI-compatible) |
| `/v1/models` | GET | List available models |
| `/ws` | WebSocket | Bidirectional streaming |
| `/health` | GET | Health check (includes provider info) |

The bridge additionally accepts `model: "auto"` (or `"smart"`, `"router"`) to enable smart routing on any endpoint.

## Troubleshooting

| Problem | Solution |
|---|---|
| Connection refused | Ensure `python start.py` is running and ports are free |
| 401 Unauthorized | Check `API_KEY` in `.env` matches your client's `apiKey` |
| 502 Bad Gateway | Model/provider failed — check logs, verify API keys |
| Claude CLI not found | Install Claude Code CLI or remove `claude_cli` providers from `bridge.yaml` |
| Timeout | Increase `REQUEST_TIMEOUT` in `.env` (default: 300s) |
| Ollama not responding | Ensure Ollama is running: `ollama serve` |
| Wrong model used | Send `model: "auto"` for smart routing or specify exact model ID |
| WebSocket disconnects | Increase `MAX_CONCURRENT` in `.env` |

## License

MIT
