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

| Requirement | Version | Check command |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |
| Claude Code CLI | latest | `claude --version` |

## Installation

### Step 1: Install Claude Code CLI

Claude Code CLI is the underlying engine. Install it globally via npm:

```bash
npm install -g @anthropic-ai/claude-code
```

Verify it's working:

```bash
claude --version
claude -p "Say hello" --model claude-haiku-4-5-20251001
```

> If the second command returns a response, your Anthropic API credentials are configured correctly. Claude Code uses the `ANTHROPIC_API_KEY` environment variable or an existing `~/.claude/` config.

### Step 2: Clone the repository

```bash
git clone https://github.com/Personal-MT-Engineering/claude-proxy-bridge.git
cd claude-proxy-bridge
```

### Step 3: Run the setup script

**Linux/macOS:**

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

**Windows:**

```cmd
scripts\setup.bat
```

The setup script will:
1. Check that Python 3.10+, pip, and the Claude CLI are available
2. Create a Python virtual environment in `.venv/`
3. Install all dependencies (`fastapi`, `uvicorn`, `pydantic`, `websockets`, `python-dotenv`, `httpx`)
4. Copy `.env.example` to `.env`

### Step 3 (alternative): Manual install

If you prefer to install manually:

```bash
# Create and activate virtual environment
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

# Install the project and its dependencies
pip install -e .

# Create your config file
cp .env.example .env
```

### Step 4: Configure (optional)

Edit `.env` to customize ports, API key, routing behavior, etc. The defaults work out of the box:

```env
HOST=127.0.0.1          # Bind address
API_KEY=local-proxy      # Auth key clients must send
SMART_ROUTING=true       # Enable auto model selection
LOG_LEVEL=INFO           # DEBUG for verbose logging
```

See the [Configuration](#configuration) section for all options.

### Step 5: Start the bridge

```bash
# Activate venv first if not already active
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

python start.py
```

You should see output like:

```
12:00:00 [INFO] Found Claude CLI: /usr/local/bin/claude
12:00:00 [INFO] ============================================================
12:00:00 [INFO] Claude Proxy Bridge is starting up!
12:00:00 [INFO] ============================================================
12:00:00 [INFO]   Opus     → http://127.0.0.1:5001/v1/chat/completions
12:00:00 [INFO]   Sonnet   → http://127.0.0.1:5002/v1/chat/completions
12:00:00 [INFO]   Haiku    → http://127.0.0.1:5003/v1/chat/completions
12:00:00 [INFO]   Bridge   → ws://127.0.0.1:5000/ws
12:00:00 [INFO] ============================================================
```

### Step 6: Verify everything is running

```bash
python scripts/health_check.py
```

Expected output:

```
Claude Proxy Bridge — Health Check
============================================================
  [OK]   Opus Proxy           → http://127.0.0.1:5001/health  (status: ok)
  [OK]   Sonnet Proxy         → http://127.0.0.1:5002/health  (status: ok)
  [OK]   Haiku Proxy          → http://127.0.0.1:5003/health  (status: ok)
  [OK]   WebSocket Bridge     → http://127.0.0.1:5000/health  (status: ok)
============================================================
All 4 services are healthy!
```

Quick smoke test:

```bash
curl http://localhost:5001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-proxy" \
  -d '{"model":"claude-opus-4-6","messages":[{"role":"user","content":"Say hello in one word"}]}'
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

Full step-by-step guide to connect OpenClaw to the Claude Proxy Bridge, including Telegram bot setup.

### Step 1: Install OpenClaw

```bash
git clone https://github.com/open-claw/openclaw.git
cd openclaw
npm install
```

### Step 2: Register the proxy as a custom provider

Copy the included provider config into your OpenClaw installation:

```bash
# From the claude-proxy-bridge directory
cp configs/openclaw_provider.json5 /path/to/openclaw/config/providers/claude-proxy.json5
```

Or manually merge it into your main OpenClaw config file. The config registers **4 providers**:

| Provider ID | Endpoint | Model |
|---|---|---|
| `claude-proxy-opus` | `http://127.0.0.1:5001/v1` | `claude-opus-4-6` |
| `claude-proxy-sonnet` | `http://127.0.0.1:5002/v1` | `claude-sonnet-4-6` |
| `claude-proxy-haiku` | `http://127.0.0.1:5003/v1` | `claude-haiku-4-5` |
| `claude-proxy-auto` | `http://127.0.0.1:5000/v1` | `auto` (smart router) |

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

### Step 3: Configure the agent model defaults

The provider config above sets these defaults:

- **`large`** (complex tasks) routes to `claude-proxy-auto/auto` — the smart router picks Opus, Sonnet, or Haiku based on the request
- **`small`** (simple tasks) routes directly to `claude-proxy-haiku/claude-haiku-4-5`

To change this, edit the `agents.defaults.models` block. For example, to always use Opus for large tasks:

```json5
"agents": {
  "defaults": {
    "models": {
      "large": "claude-proxy-opus/claude-opus-4-6",
      "small": "claude-proxy-haiku/claude-haiku-4-5"
    }
  }
}
```

### Step 4: Set up a Telegram bot (optional)

This lets you chat with Claude via Telegram through OpenClaw.

**4a. Create the bot:**

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a display name (e.g., "Claude Assistant")
4. Choose a username ending in `bot` (e.g., `my_claude_bot`)
5. Save the API token BotFather gives you (format: `1234567890:ABCdefGHI...`)

**4b. Add the Telegram channel to OpenClaw config:**

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

DM policies:
- `"pairing"` — users must enter a pairing code shown in the OpenClaw console (recommended, more secure)
- `"open"` — anyone can message the bot directly

### Step 5: Start both services

**Terminal 1 — Start the proxy bridge:**

```bash
cd claude-proxy-bridge
source .venv/bin/activate
python start.py
```

**Terminal 2 — Start OpenClaw:**

```bash
cd openclaw
npm start
```

### Step 6: Verify the full chain

```bash
# Check the proxy bridge
python scripts/health_check.py

# Test via OpenClaw (if it exposes an API)
curl http://localhost:18789/health
```

If using Telegram:

1. Open Telegram, find your bot by username
2. Send `/start`
3. If using `"pairing"` policy: look at the OpenClaw console for the pairing code, then send it to the bot
4. Start chatting — messages flow through: `Telegram -> OpenClaw -> Proxy Bridge -> Claude CLI -> Response`

### OpenClaw troubleshooting

| Problem | Solution |
|---|---|
| Bot not responding | Check OpenClaw logs, verify bot token, run `python scripts/health_check.py` |
| Slow responses | Use Haiku for casual chat, or set `"small"` as the default model |
| Connection refused | Ensure the proxy bridge is running and ports 5000-5003 are free |
| Wrong model used | Check `agents.defaults.models` in your OpenClaw config |
| Pairing code not shown | Restart OpenClaw, send `/start` again in Telegram |
| 401 Unauthorized | Make sure `apiKey` in the provider config matches `API_KEY` in `.env` |

---

## NanoClaw Integration

Full step-by-step guide to connect NanoClaw to the Claude Proxy Bridge.

### Step 1: Install NanoClaw

```bash
git clone https://github.com/nano-claw/nanoclaw.git
cd nanoclaw
npm install
```

### Step 2: Choose your integration method

NanoClaw can connect to the proxy bridge in two ways:

#### Option A: HTTP (OpenAI-compatible API)

This is the simplest approach. Point NanoClaw's LLM config at a proxy endpoint.

**For smart routing (recommended):**

In your NanoClaw configuration (e.g., `config.json` or environment variables):

```json
{
  "llm": {
    "baseUrl": "http://127.0.0.1:5000/v1",
    "apiKey": "local-proxy",
    "model": "auto"
  }
}
```

The smart router will automatically pick the best model for each request.

**For a specific model:**

```json
{
  "llm": {
    "baseUrl": "http://127.0.0.1:5001/v1",
    "apiKey": "local-proxy",
    "model": "claude-opus-4-6"
  }
}
```

Available direct endpoints:

| Model | baseUrl |
|---|---|
| Opus 4.6 | `http://127.0.0.1:5001/v1` |
| Sonnet 4.6 | `http://127.0.0.1:5002/v1` |
| Haiku 4.5 | `http://127.0.0.1:5003/v1` |
| Smart Router | `http://127.0.0.1:5000/v1` |

**If NanoClaw uses TypeScript/Node.js internally** (e.g., in `src/container-runner.ts`):

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://127.0.0.1:5000/v1",
  apiKey: "local-proxy",
});

const response = await client.chat.completions.create({
  model: "auto",  // smart routing
  messages: [
    { role: "system", content: "You are a helpful coding assistant." },
    { role: "user", content: "Explain async/await in JavaScript" },
  ],
});

console.log(response.choices[0].message.content);
```

**With streaming:**

```typescript
const stream = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Write a quick sort in Python" }],
  stream: true,
});

for await (const chunk of stream) {
  const text = chunk.choices[0]?.delta?.content || "";
  process.stdout.write(text);
}
```

#### Option B: WebSocket bridge

For bidirectional streaming or when you need routing metadata.

Connect to `ws://127.0.0.1:5000/ws` and exchange JSON messages:

```typescript
import WebSocket from "ws";

const ws = new WebSocket("ws://127.0.0.1:5000/ws");

ws.on("open", () => {
  ws.send(JSON.stringify({
    model: "auto",  // or "claude-opus-4-6", "claude-sonnet-4-6", etc.
    messages: [
      { role: "system", content: "You are a helpful assistant." },
      { role: "user", content: "Hello!" },
    ],
    stream: true,
  }));
});

ws.on("message", (data) => {
  const msg = JSON.parse(data.toString());

  switch (msg.type) {
    case "routing":
      // Smart router decision: which model was picked and why
      console.log(`Routed to ${msg.model} (${msg.scenario}): ${msg.reason}`);
      console.log(`Fallback chain: ${msg.fallback.join(" -> ")}`);
      break;

    case "delta":
      // Streamed text chunk
      process.stdout.write(msg.content);
      break;

    case "done":
      // Final complete response
      console.log(`\n\nDone. Model used: ${msg.model}, scenario: ${msg.scenario}`);
      ws.close();
      break;

    case "error":
      console.error("Error:", msg.content);
      ws.close();
      break;
  }
});
```

WebSocket message types:

| Direction | Type | Fields | Description |
|---|---|---|---|
| Server -> Client | `routing` | `scenario`, `model`, `reason`, `fallback` | Smart router decision (sent before response) |
| Server -> Client | `delta` | `content` | Streamed text chunk |
| Server -> Client | `done` | `content`, `model`, `scenario` | Complete response |
| Server -> Client | `error` | `content` | Error message |

### Step 3: Install the skill file (optional)

Copy the NanoClaw skill file so NanoClaw's internal agent knows about the proxy bridge:

```bash
# From the claude-proxy-bridge directory
mkdir -p /path/to/nanoclaw/.claude/skills
cp configs/nanoclaw_skill.md /path/to/nanoclaw/.claude/skills/claude-proxy-bridge.md
```

### Step 4: Multi-model strategy (optional)

You can configure NanoClaw to use different models for different task types:

```typescript
// Complex reasoning, architecture decisions
const complexConfig = {
  baseURL: "http://127.0.0.1:5001/v1",  // Opus directly
  apiKey: "local-proxy",
  model: "claude-opus-4-6",
};

// General-purpose tasks, code generation
const generalConfig = {
  baseURL: "http://127.0.0.1:5002/v1",  // Sonnet directly
  apiKey: "local-proxy",
  model: "claude-sonnet-4-6",
};

// Quick classification, simple responses
const fastConfig = {
  baseURL: "http://127.0.0.1:5003/v1",  // Haiku directly
  apiKey: "local-proxy",
  model: "claude-haiku-4-5",
};

// Or let the smart router decide automatically:
const autoConfig = {
  baseURL: "http://127.0.0.1:5000/v1",
  apiKey: "local-proxy",
  model: "auto",
};
```

### Step 5: Start both services

**Terminal 1 — Start the proxy bridge:**

```bash
cd claude-proxy-bridge
source .venv/bin/activate
python start.py
```

**Terminal 2 — Start NanoClaw:**

```bash
cd nanoclaw
npm start
```

### Step 6: Verify

```bash
# Proxy bridge health
python scripts/health_check.py

# Quick test from NanoClaw's perspective
curl http://127.0.0.1:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-proxy" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Hello from NanoClaw!"}]
  }'
```

### NanoClaw troubleshooting

| Problem | Solution |
|---|---|
| Connection refused | Ensure proxy bridge is running: `python start.py` |
| 401 Unauthorized | Check `apiKey` matches `API_KEY` in `.env` (default: `local-proxy`) |
| 502 Bad Gateway | Claude CLI failed — check that `claude --version` works |
| Timeout | Increase `REQUEST_TIMEOUT` in `.env` (default: 300s) |
| Wrong model used | Send `model: "auto"` for smart routing or specify the exact model ID |
| WebSocket disconnects | Check `MAX_CONCURRENT` in `.env` — increase if hitting concurrency limits |

---

## Using with any OpenAI-compatible client

The proxy bridge works with any tool or library that speaks the OpenAI Chat Completions API.

### Python (openai library)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:5000/v1",
    api_key="local-proxy",
)

# Smart routing — model picked automatically
response = client.chat.completions.create(
    model="auto",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain Docker in simple terms"},
    ],
)
print(response.choices[0].message.content)
print(f"Model used: {response.model}")
```

### JavaScript/TypeScript (openai library)

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
