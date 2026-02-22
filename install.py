#!/usr/bin/env python3
"""Universal interactive installer for Claude Proxy Bridge.

Single file, uses only Python stdlib. Generates bridge.yaml, .env, and
optionally configures OpenClaw or NanoClaw integration.

Usage:
    python install.py
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent

PROVIDERS = {
    "claude-cli": {
        "label": "Claude Code CLI (local, no API key needed)",
        "type": "claude_cli",
        "base_url": "",
        "needs_key": False,
        "key_env": "",
        "key_prefix": "",
        "models": [
            ("opus", "claude-opus-4-6", "Opus 4.6"),
            ("sonnet", "claude-sonnet-4-6", "Sonnet 4.6"),
            ("haiku", "claude-haiku-4-5-20251001", "Haiku 4.5"),
        ],
    },
    "openai": {
        "label": "OpenAI (GPT-4o, GPT-4o-mini, o1)",
        "type": "http",
        "base_url": "https://api.openai.com/v1",
        "needs_key": True,
        "key_env": "OPENAI_API_KEY",
        "key_prefix": "sk-",
        "models": [
            ("gpt-4o", "gpt-4o", "GPT-4o"),
            ("gpt-4o-mini", "gpt-4o-mini", "GPT-4o Mini"),
            ("o1", "o1", "o1"),
        ],
    },
    "anthropic-api": {
        "label": "Anthropic API (Claude via HTTP — needs API key)",
        "type": "http",
        "base_url": "https://api.anthropic.com/v1",
        "needs_key": True,
        "key_env": "ANTHROPIC_API_KEY",
        "key_prefix": "sk-ant-",
        "extra_headers": {"anthropic-version": "2023-06-01"},
        "models": [
            ("claude-opus", "claude-opus-4-6", "Claude Opus 4.6"),
            ("claude-sonnet", "claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("claude-haiku", "claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
        ],
    },
    "deepseek": {
        "label": "DeepSeek (DeepSeek-V3, DeepSeek-R1)",
        "type": "http",
        "base_url": "https://api.deepseek.com/v1",
        "needs_key": True,
        "key_env": "DEEPSEEK_API_KEY",
        "key_prefix": "sk-",
        "models": [
            ("deepseek-chat", "deepseek-chat", "DeepSeek Chat (V3)"),
            ("deepseek-reasoner", "deepseek-reasoner", "DeepSeek Reasoner (R1)"),
        ],
    },
    "gemini": {
        "label": "Google Gemini (Gemini 2.5 Flash, Pro)",
        "type": "http",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "needs_key": True,
        "key_env": "GEMINI_API_KEY",
        "key_prefix": "AIza",
        "models": [
            ("gemini-flash", "gemini-2.5-flash", "Gemini 2.5 Flash"),
            ("gemini-pro", "gemini-2.5-pro", "Gemini 2.5 Pro"),
        ],
    },
    "ollama": {
        "label": "Ollama (local models, no API key)",
        "type": "http",
        "base_url": "http://localhost:11434/v1",
        "needs_key": False,
        "key_env": "",
        "key_prefix": "",
        "default_api_key": "ollama",
        "models": [
            ("llama3", "llama3", "Llama 3"),
            ("mistral-local", "mistral", "Mistral"),
            ("codellama", "codellama", "Code Llama"),
            ("phi3", "phi3", "Phi-3"),
        ],
    },
    "openrouter": {
        "label": "OpenRouter (100+ models via one key)",
        "type": "http",
        "base_url": "https://openrouter.ai/api/v1",
        "needs_key": True,
        "key_env": "OPENROUTER_API_KEY",
        "key_prefix": "sk-or-",
        "models": [
            ("or-claude-opus", "anthropic/claude-opus-4-5", "Claude Opus (OpenRouter)"),
            ("or-gpt-4o", "openai/gpt-4o", "GPT-4o (OpenRouter)"),
            ("or-llama-70b", "meta-llama/llama-3-70b", "Llama 3 70B (OpenRouter)"),
        ],
    },
    "together": {
        "label": "Together AI",
        "type": "http",
        "base_url": "https://api.together.xyz/v1",
        "needs_key": True,
        "key_env": "TOGETHER_API_KEY",
        "key_prefix": "",
        "models": [
            ("together-llama-70b", "meta-llama/Llama-3-70b", "Llama 3 70B"),
            ("together-mixtral", "mistralai/Mixtral-8x7B", "Mixtral 8x7B"),
        ],
    },
    "groq": {
        "label": "Groq (fast inference)",
        "type": "http",
        "base_url": "https://api.groq.com/openai/v1",
        "needs_key": True,
        "key_env": "GROQ_API_KEY",
        "key_prefix": "gsk_",
        "models": [
            ("groq-llama-70b", "llama-3.1-70b-versatile", "Llama 3.1 70B"),
            ("groq-mixtral", "mixtral-8x7b-32768", "Mixtral 8x7B"),
        ],
    },
    "mistral": {
        "label": "Mistral",
        "type": "http",
        "base_url": "https://api.mistral.ai/v1",
        "needs_key": True,
        "key_env": "MISTRAL_API_KEY",
        "key_prefix": "",
        "models": [
            ("mistral-large", "mistral-large-latest", "Mistral Large"),
            ("mistral-small", "mistral-small-latest", "Mistral Small"),
        ],
    },
    "custom": {
        "label": "Custom HTTP endpoint",
        "type": "http",
        "base_url": "",
        "needs_key": False,
        "key_env": "CUSTOM_API_KEY",
        "key_prefix": "",
        "models": [],
    },
}

PROVIDER_ORDER = [
    "claude-cli", "openai", "anthropic-api", "deepseek", "gemini",
    "ollama", "openrouter", "together", "groq", "mistral", "custom",
]

# Routing tier assignment: maps provider to capability tier
# Tier 1 = most capable, Tier 3 = fastest/cheapest
MODEL_TIER: dict[str, int] = {
    # Claude CLI
    "claude-opus-4-6": 1, "claude-sonnet-4-6": 2, "claude-haiku-4-5-20251001": 3,
    # OpenAI
    "gpt-4o": 1, "gpt-4o-mini": 3, "o1": 1,
    # Anthropic API
    # (same IDs as Claude CLI, already covered)
    # DeepSeek
    "deepseek-chat": 2, "deepseek-reasoner": 1,
    # Gemini
    "gemini-2.5-flash": 3, "gemini-2.5-pro": 1,
    # Ollama
    "llama3": 2, "mistral": 3, "codellama": 2, "phi3": 3,
    # OpenRouter
    "anthropic/claude-opus-4-5": 1, "openai/gpt-4o": 1, "meta-llama/llama-3-70b": 2,
    # Together
    "meta-llama/Llama-3-70b": 2, "mistralai/Mixtral-8x7B": 3,
    # Groq
    "llama-3.1-70b-versatile": 2, "mixtral-8x7b-32768": 3,
    # Mistral
    "mistral-large-latest": 1, "mistral-small-latest": 3,
}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def hr():
    print("─" * 60)


def banner(text: str):
    hr()
    print(f"  {text}")
    hr()


def ask(prompt: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    if default:
        result = input(f"{prompt} [{default}]: ").strip()
        return result or default
    return input(f"{prompt}: ").strip()


def ask_yn(prompt: str, default: bool = True) -> bool:
    """Yes/No prompt."""
    suffix = "(Y/n)" if default else "(y/N)"
    result = input(f"{prompt} {suffix}: ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes")


def ask_multi(prompt: str, options: list[tuple[int, str]], allow_all: bool = False) -> list[int]:
    """Multi-select from numbered list. Returns list of selected indices."""
    print(prompt)
    for idx, label in options:
        print(f"  [{idx:2d}] {label}")
    if allow_all:
        print(f"  [ A] All")
    raw = input("Enter numbers (e.g. 1,2,6): ").strip()
    if allow_all and raw.lower() == "a":
        return [idx for idx, _ in options]
    selected = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            n = int(part)
            if any(idx == n for idx, _ in options):
                selected.append(n)
    return selected


def check_command(cmd: str) -> tuple[bool, str]:
    """Check if a command exists and return (found, version_string)."""
    path = shutil.which(cmd)
    if not path:
        return False, ""
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=10,
        )
        ver = result.stdout.strip().split("\n")[0] if result.stdout else ""
        if not ver:
            ver = result.stderr.strip().split("\n")[0] if result.stderr else "found"
        return True, ver
    except Exception:
        return True, "found"


def check_python_package(name: str) -> bool:
    """Check if a Python package is importable."""
    try:
        subprocess.run(
            [sys.executable, "-c", f"import {name}"],
            capture_output=True, timeout=10,
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def step_welcome() -> dict:
    """Welcome and OS detection."""
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "python": platform.python_version(),
        "arch": platform.machine(),
    }

    banner("Claude Proxy Bridge — Universal Installer")
    print(f"  Detected: {info['os']} {info['os_release']} ({info['arch']})")
    print(f"  Python:   {info['python']}")
    print()

    return info


def step_prerequisites() -> None:
    """Check prerequisites."""
    banner("Prerequisite Checks")

    checks = [
        ("Python", sys.executable, f"{platform.python_version()}"),
        ("pip", "pip", ""),
        ("Node.js", "node", ""),
    ]

    # Check Claude CLI
    if sys.platform == "win32":
        for name in ("claude.cmd", "claude.exe", "claude"):
            found = shutil.which(name)
            if found:
                checks.append(("Claude Code CLI", name, ""))
                break
        else:
            checks.append(("Claude Code CLI", "claude", ""))
    else:
        checks.append(("Claude Code CLI", "claude", ""))

    checks.append(("Ollama", "ollama", ""))

    for label, cmd, override_ver in checks:
        if override_ver:
            print(f"  [OK]   {label}: {override_ver}")
            continue
        found, ver = check_command(cmd)
        if found:
            print(f"  [OK]   {label}: {ver}")
        elif label == "Ollama":
            print(f"  [SKIP] {label} (not installed — needed only if you select it)")
        elif label == "Claude Code CLI":
            print(f"  [SKIP] {label} (not found — needed only for Claude CLI provider)")
        else:
            print(f"  [MISS] {label} — please install before continuing")

    print()


def step_select_providers() -> list[str]:
    """Interactive provider selection."""
    banner("Provider Selection")

    options = []
    for i, key in enumerate(PROVIDER_ORDER, 1):
        options.append((i, PROVIDERS[key]["label"]))

    selected_nums = ask_multi("Which LLM providers do you want to use?", options)
    if not selected_nums:
        print("No providers selected. Defaulting to Claude Code CLI.")
        return ["claude-cli"]

    selected = []
    for num in selected_nums:
        if 1 <= num <= len(PROVIDER_ORDER):
            selected.append(PROVIDER_ORDER[num - 1])

    print(f"\nSelected: {', '.join(selected)}")
    return selected


def step_collect_api_keys(selected_providers: list[str]) -> dict[str, str]:
    """Collect API keys for providers that need them."""
    keys: dict[str, str] = {}
    needs_input = False

    for pkey in selected_providers:
        pdata = PROVIDERS[pkey]
        if pdata["needs_key"]:
            needs_input = True
            break

    if not needs_input:
        return keys

    banner("API Key Collection")
    print("  Keys are stored in .env (local only, not committed).\n")

    for pkey in selected_providers:
        pdata = PROVIDERS[pkey]
        if not pdata["needs_key"]:
            continue

        env_var = pdata["key_env"]
        existing = os.getenv(env_var, "")
        if existing:
            masked = existing[:8] + "..." + existing[-4:] if len(existing) > 12 else "***"
            print(f"  Found ${env_var} in environment: {masked}")
            keys[env_var] = existing
        else:
            prefix_hint = f" (starts with {pdata['key_prefix']})" if pdata["key_prefix"] else ""
            key = ask(f"  Enter your {pdata['label'].split('(')[0].strip()} API key{prefix_hint}")
            if key:
                keys[env_var] = key
            else:
                print(f"  Warning: No key provided for {pdata['label']}. You can add it to .env later.")

    return keys


def step_select_models(selected_providers: list[str]) -> list[dict]:
    """Select models per provider. Returns list of model dicts."""
    banner("Model Selection")

    all_models: list[dict] = []
    next_port = 5001

    for pkey in selected_providers:
        pdata = PROVIDERS[pkey]
        available = pdata["models"]

        if pkey == "custom":
            # Custom endpoint: ask for details
            print(f"\n  Custom HTTP endpoint:")
            base_url = ask("    Base URL (e.g. http://localhost:8080/v1)")
            model_id = ask("    Model ID")
            model_name = ask("    Short name for this model", model_id.split("/")[-1])
            api_key = ask("    API key (leave empty if none)", "")
            if base_url and model_id:
                all_models.append({
                    "name": model_name,
                    "model_id": model_id,
                    "port": next_port,
                    "provider": pkey,
                    "custom_base_url": base_url,
                    "custom_api_key": api_key,
                })
                next_port += 1
            continue

        if not available:
            continue

        options = []
        for i, (name, mid, label) in enumerate(available, 1):
            options.append((i, f"{label:30s} ({mid})"))

        print(f"\n  {pdata['label']} models:")
        selected_nums = ask_multi("  Select models:", options, allow_all=True)

        for num in selected_nums:
            if 1 <= num <= len(available):
                name, mid, label = available[num - 1]
                all_models.append({
                    "name": name,
                    "model_id": mid,
                    "port": next_port,
                    "provider": pkey,
                })
                next_port += 1

    if not all_models:
        print("\n  No models selected. Adding default Claude CLI models.")
        for name, mid, label in PROVIDERS["claude-cli"]["models"]:
            all_models.append({
                "name": name,
                "model_id": mid,
                "port": next_port,
                "provider": "claude-cli",
            })
            next_port += 1

    print(f"\n  Total models configured: {len(all_models)}")
    for m in all_models:
        print(f"    :{m['port']}  {m['name']:20s} → {m['model_id']} ({m['provider']})")

    return all_models


def step_smart_routing(models: list[dict]) -> dict:
    """Configure smart routing based on selected models."""
    banner("Smart Routing Configuration")

    enable = ask_yn("Enable smart routing?", True)
    if not enable:
        return {"enabled": False}

    # Auto-generate routing based on model tiers
    tier1, tier2, tier3 = [], [], []
    for m in models:
        tier = MODEL_TIER.get(m["model_id"], 2)
        if tier == 1:
            tier1.append(m["name"])
        elif tier == 2:
            tier2.append(m["name"])
        else:
            tier3.append(m["name"])

    # Pick best model for each scenario
    def pick(tiers_preferred: list[list[str]]) -> str:
        for tier in tiers_preferred:
            if tier:
                return tier[0]
        return models[0]["name"]

    def chain(tiers_preferred: list[list[str]]) -> list[str]:
        result = []
        for tier in tiers_preferred:
            result.extend(tier)
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for m in result:
            if m not in seen:
                seen.add(m)
                deduped.append(m)
        return deduped

    routing = {
        "enabled": True,
        "scenario_models": {
            "complex": pick([tier1, tier2, tier3]),
            "code": pick([tier2, tier1, tier3]),
            "long": pick([tier1, tier2, tier3]),
            "moderate": pick([tier2, tier3, tier1]),
            "simple": pick([tier3, tier2, tier1]),
        },
        "fallback_chains": {
            "complex": chain([tier1, tier2, tier3]),
            "code": chain([tier2, tier1, tier3]),
            "long": chain([tier1, tier2]),
            "moderate": chain([tier2, tier3, tier1]),
            "simple": chain([tier3, tier2]),
        },
    }

    print("\n  Auto-generated routing:")
    for scenario, model_name in routing["scenario_models"].items():
        fallback = routing["fallback_chains"].get(scenario, [])
        print(f"    {scenario:10s} → {model_name:20s} fallback: {fallback}")

    return routing


def step_integration() -> str:
    """Choose integration target."""
    banner("Integration Target")

    print("  How do you want to use the bridge?")
    print("    [1] Standalone (just the proxy bridge)")
    print("    [2] With OpenClaw (+ optional Telegram bot)")
    print("    [3] With NanoClaw")
    choice = ask("  Select", "1")

    if choice == "2":
        return "openclaw"
    elif choice == "3":
        return "nanoclaw"
    return "standalone"


def step_openclaw_setup(models: list[dict]) -> dict | None:
    """Configure OpenClaw integration."""
    banner("OpenClaw Integration")

    # Check if openclaw is installed
    found, ver = check_command("openclaw")
    if not found:
        found, ver = check_command("npx")
        if found:
            print("  OpenClaw not found globally. You can install it with: npm install -g openclaw")
            install = ask_yn("  Install OpenClaw now?", False)
            if install:
                print("  Installing OpenClaw...")
                subprocess.run(["npm", "install", "-g", "openclaw"], check=False)
        else:
            print("  OpenClaw and npm not found. Skipping OpenClaw setup.")
            print("  You can generate the config and install OpenClaw later.")

    # Generate config
    config: dict = {
        "models": {
            "mode": "merge",
            "providers": {},
        },
    }

    # Add bridge models as providers
    for m in models:
        provider_key = f"bridge-{m['name']}"
        config["models"]["providers"][provider_key] = {
            "baseUrl": f"http://127.0.0.1:{m['port']}/v1",
            "apiKey": "local-proxy",
            "api": "openai-completions",
            "models": [{
                "id": m["model_id"],
                "name": f"{m['name'].title()} (Bridge)",
            }],
        }

    # Add auto-router
    config["models"]["providers"]["bridge-auto"] = {
        "baseUrl": "http://127.0.0.1:5000/v1",
        "apiKey": "local-proxy",
        "api": "openai-completions",
        "models": [{"id": "auto", "name": "Smart Router"}],
    }

    # Telegram bot
    telegram_config = None
    setup_telegram = ask_yn("  Set up Telegram bot?", False)
    if setup_telegram:
        token = ask("  Enter your Telegram bot token from @BotFather")
        if token:
            config["channels"] = {
                "telegram": {
                    "enabled": True,
                    "botToken": token,
                    "dmPolicy": "pairing",
                },
            }
            telegram_config = token

    return config


def step_nanoclaw_setup(models: list[dict]) -> dict:
    """Generate NanoClaw configuration."""
    banner("NanoClaw Integration")

    config = {
        "bridge": {
            "url": "http://127.0.0.1:5000",
            "apiKey": "local-proxy",
        },
        "models": {},
    }

    for m in models:
        config["models"][m["name"]] = {
            "url": f"http://127.0.0.1:{m['port']}/v1/chat/completions",
            "model_id": m["model_id"],
        }

    return config


# ---------------------------------------------------------------------------
# File generation
# ---------------------------------------------------------------------------

def generate_bridge_yaml(
    selected_providers: list[str],
    models: list[dict],
    api_keys: dict[str, str],
    routing: dict,
) -> str:
    """Generate bridge.yaml content."""
    lines = [
        "# Claude Proxy Bridge Configuration",
        "# Generated by install.py",
        "",
        "providers:",
    ]

    # Collect which providers are actually used
    used_providers = set(m["provider"] for m in models)

    for pkey in selected_providers:
        if pkey not in used_providers:
            continue
        pdata = PROVIDERS[pkey]

        if pkey == "custom":
            # Custom providers are handled per-model
            custom_models = [m for m in models if m["provider"] == "custom"]
            for i, m in enumerate(custom_models):
                ckey = f"custom-{i}" if i > 0 else "custom"
                lines.append(f"  {ckey}:")
                lines.append(f"    type: http")
                lines.append(f'    base_url: "{m.get("custom_base_url", "")}"')
                capi = m.get("custom_api_key", "")
                if capi:
                    lines.append(f'    api_key: "{capi}"')
            continue

        lines.append(f"  {pkey}:")
        lines.append(f"    type: {pdata['type']}")

        if pdata["type"] == "http":
            lines.append(f'    base_url: "{pdata["base_url"]}"')
            if pdata["needs_key"]:
                lines.append(f'    api_key: "${{{pdata["key_env"]}}}"')
            elif pdata.get("default_api_key"):
                lines.append(f'    api_key: "{pdata["default_api_key"]}"')
            if pdata.get("extra_headers"):
                lines.append("    extra_headers:")
                for hk, hv in pdata["extra_headers"].items():
                    lines.append(f'      {hk}: "{hv}"')
        elif pdata["type"] == "claude_cli":
            lines.append('    cli_path: ""')

    lines.append("")
    lines.append("models:")

    for m in models:
        lines.append(f"  {m['name']}:")
        pkey = m["provider"]
        if pkey == "custom":
            custom_idx = [cm for cm in models if cm["provider"] == "custom"].index(m)
            pkey = f"custom-{custom_idx}" if custom_idx > 0 else "custom"
        lines.append(f"    provider: {pkey}")
        lines.append(f'    model_id: "{m["model_id"]}"')
        lines.append(f"    port: {m['port']}")

    if routing.get("enabled"):
        lines.append("")
        lines.append("routing:")
        lines.append("  scenario_models:")
        for scenario, model_name in routing["scenario_models"].items():
            lines.append(f"    {scenario}: {model_name}")
        lines.append("  fallback_chains:")
        for scenario, chain in routing["fallback_chains"].items():
            chain_str = ", ".join(chain)
            lines.append(f"    {scenario}: [{chain_str}]")

    return "\n".join(lines) + "\n"


def generate_env(api_keys: dict[str, str], extra: dict[str, str] | None = None) -> str:
    """Generate .env content."""
    lines = [
        "# Claude Proxy Bridge — Environment Configuration",
        "# Generated by install.py",
        "",
        "HOST=127.0.0.1",
        "BRIDGE_PORT=5000",
        "API_KEY=local-proxy",
        "CLAUDE_CLI_PATH=",
        "REQUEST_TIMEOUT=300",
        "MAX_CONCURRENT=5",
        "LOG_LEVEL=INFO",
        "SMART_ROUTING=true",
        "ROUTING_LONG_CONTEXT_THRESHOLD=50000",
        "ROUTING_MAX_FALLBACK_ATTEMPTS=2",
        "",
    ]

    if api_keys:
        lines.append("# API Keys")
        for env_var, key in api_keys.items():
            lines.append(f"{env_var}={key}")
        lines.append("")

    if extra:
        for k, v in extra.items():
            lines.append(f"{k}={v}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main installer flow
# ---------------------------------------------------------------------------

def main() -> None:
    print()

    # 1. Welcome
    info = step_welcome()

    # 2. Prerequisites
    step_prerequisites()

    # 3. Provider selection
    selected_providers = step_select_providers()

    # 4. API key collection
    api_keys = step_collect_api_keys(selected_providers)

    # 5. Model selection
    models = step_select_models(selected_providers)

    # 6. Smart routing
    routing = step_smart_routing(models)

    # 7. Integration target
    integration = step_integration()

    # 8. Integration-specific setup
    openclaw_config = None
    nanoclaw_config = None

    if integration == "openclaw":
        openclaw_config = step_openclaw_setup(models)
    elif integration == "nanoclaw":
        nanoclaw_config = step_nanoclaw_setup(models)

    # 9. Generate files
    banner("Generating Configuration Files")

    # bridge.yaml
    yaml_content = generate_bridge_yaml(selected_providers, models, api_keys, routing)
    yaml_path = SCRIPT_DIR / "bridge.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    print(f"  [OK] {yaml_path}")

    # .env
    env_content = generate_env(api_keys)
    env_path = SCRIPT_DIR / ".env"
    env_path.write_text(env_content, encoding="utf-8")
    print(f"  [OK] {env_path}")

    # OpenClaw config
    if openclaw_config:
        oc_dir = Path.home() / ".openclaw"
        oc_dir.mkdir(parents=True, exist_ok=True)
        oc_path = oc_dir / "openclaw.json"

        # Merge with existing if present
        existing = {}
        if oc_path.exists():
            try:
                existing = json.loads(oc_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        # Merge providers
        if "models" in existing and "providers" in existing["models"]:
            existing["models"]["providers"].update(openclaw_config["models"]["providers"])
            openclaw_config["models"]["providers"] = existing["models"]["providers"]

        oc_path.write_text(json.dumps(openclaw_config, indent=2), encoding="utf-8")
        print(f"  [OK] {oc_path}")

    # NanoClaw config
    if nanoclaw_config:
        nc_path = SCRIPT_DIR / "configs" / "nanoclaw_bridge.json"
        nc_path.parent.mkdir(parents=True, exist_ok=True)
        nc_path.write_text(json.dumps(nanoclaw_config, indent=2), encoding="utf-8")
        print(f"  [OK] {nc_path}")

    # 10. Install Python dependencies
    banner("Installing Dependencies")

    venv_path = SCRIPT_DIR / ".venv"
    if not venv_path.exists():
        print("  Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=False)

    # Determine pip path
    if sys.platform == "win32":
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        pip_path = venv_path / "bin" / "pip"

    if pip_path.exists():
        print("  Installing packages...")
        subprocess.run(
            [str(pip_path), "install", "-e", str(SCRIPT_DIR), "-q"],
            check=False,
        )
        print("  [OK] Dependencies installed")
    else:
        print("  [SKIP] Could not find pip in venv. Run: pip install -e . manually")

    # 11. Done
    banner("Setup Complete!")

    if sys.platform == "win32":
        activate = f"  .venv\\Scripts\\activate"
        python = "python"
    else:
        activate = f"  source .venv/bin/activate"
        python = "python3"

    print(f"""
  To start the bridge:
    cd {SCRIPT_DIR}
  {activate}
    {python} start.py

  Health check:
    {python} scripts/health_check.py

  Configuration files:
    bridge.yaml  — providers, models, routing
    .env         — API keys, global settings
""")

    if openclaw_config:
        print("  OpenClaw config written to ~/.openclaw/openclaw.json")
        print("  Start OpenClaw with: openclaw start")
    if nanoclaw_config:
        print(f"  NanoClaw config written to configs/nanoclaw_bridge.json")

    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInstaller cancelled.")
        sys.exit(1)
