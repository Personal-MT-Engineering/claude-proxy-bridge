# Telegram Bot Setup Guide

This guide walks you through creating a Telegram bot and connecting it to OpenClaw via the Claude Proxy Bridge.

## Prerequisites

- Claude Proxy Bridge running (`python start.py`)
- OpenClaw installed and configured with the proxy provider (see `configs/openclaw_provider.json5`)

## Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts:
   - Choose a **display name** for your bot (e.g., "Claude Assistant")
   - Choose a **username** (must end in `bot`, e.g., `my_claude_assistant_bot`)
4. BotFather will give you an **API token** — save this! It looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

## Step 2: Configure OpenClaw

Add the Telegram channel to your OpenClaw configuration:

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

### DM Policies

- `"pairing"` — Users must enter a pairing code to start chatting (more secure)
- `"open"` — Anyone can message the bot directly (less secure)

## Step 3: Start Everything

1. Start the Claude Proxy Bridge:
   ```bash
   cd claude-proxy-bridge
   python start.py
   ```

2. Start OpenClaw (in another terminal):
   ```bash
   cd openclaw
   npm start
   ```

3. Verify both are running:
   ```bash
   python scripts/health_check.py
   ```

## Step 4: Connect via Telegram

1. Open Telegram and find your bot by its username
2. Send `/start`
3. If using `"pairing"` policy:
   - OpenClaw will show a pairing code in its console
   - Send the code to the bot in Telegram
4. Start chatting! Your messages go through:
   ```
   Telegram → OpenClaw → Claude Proxy Bridge → Claude Code CLI → Response
   ```

## Step 5: Choose a Model (Optional)

By default, OpenClaw uses the model configured in `agents.defaults.models.large`. To change models:

- Edit `configs/openclaw_provider.json5` and change the `agents.defaults.models` section
- Or configure model selection per-agent in OpenClaw's agent config

## Troubleshooting

### Bot not responding
- Check OpenClaw logs for errors
- Verify the bot token is correct
- Make sure the proxy bridge is running: `python scripts/health_check.py`

### Slow responses
- Claude Code CLI can take time to start up for each request
- Consider using Haiku for faster responses in casual conversations
- Check if `claude` CLI works directly: `claude -p "Hello" --model claude-haiku-4-5-20251001`

### Connection errors
- Ensure all ports (5000-5003) are free
- Check firewall settings if OpenClaw is on a different machine
- Verify `.env` settings match your OpenClaw config

### Pairing code not showing
- Check OpenClaw console output
- Restart OpenClaw and try `/start` again in Telegram
