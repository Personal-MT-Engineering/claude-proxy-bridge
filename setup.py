#!/usr/bin/env python3
"""End-to-end setup script for Claude Proxy Bridge + OpenClaw / NanoClaw.

Interactive CLI that:
1. Sets up the proxy bridge (venv, deps, config)
2. Auto-configures OpenClaw or NanoClaw to use the bridge
3. Optionally sets up Telegram bot
4. Optionally registers with the health check dashboard
5. Generates start scripts for the full pipeline

Single file, uses only Python stdlib.

Usage:
    python setup.py
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
HOME = Path.home()
DESKTOP = HOME / "Desktop"

# Defaults (auto-detected later)
OPENCLAW_DIR = DESKTOP / "openclaw"
NANOCLAW_DIR = DESKTOP / "nanoclaw"
OPENCLAW_CONFIG_DIR = HOME / ".openclaw"
OPENCLAW_CONFIG_FILE = OPENCLAW_CONFIG_DIR / "openclaw.json"
HEALTH_CHECK_DIR = DESKTOP / "openclaw_health_check"

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 5000
API_KEY = "local-proxy"

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"

    @staticmethod
    def supported() -> bool:
        if os.getenv("NO_COLOR"):
            return False
        if sys.platform == "win32":
            # Enable ANSI on Windows 10+
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
                return True
            except Exception:
                return False
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


C = Colors if Colors.supported() else type("NoColor", (), {k: "" for k in dir(Colors) if not k.startswith("_")})()


def hr(char="─", width=64):
    print(f"{C.DIM}{char * width}{C.RESET}")


def banner(text: str):
    print()
    hr()
    print(f"  {C.BOLD}{C.CYAN}{text}{C.RESET}")
    hr()
    print()


def step(num: int, text: str):
    print(f"\n  {C.BOLD}{C.MAGENTA}[{num}]{C.RESET} {C.BOLD}{text}{C.RESET}\n")


def ok(text: str):
    print(f"  {C.GREEN}[OK]{C.RESET}   {text}")


def warn(text: str):
    print(f"  {C.YELLOW}[WARN]{C.RESET} {text}")


def fail(text: str):
    print(f"  {C.RED}[FAIL]{C.RESET} {text}")


def skip(text: str):
    print(f"  {C.DIM}[SKIP]{C.RESET} {text}")


def info(text: str):
    print(f"  {C.DIM}→{C.RESET} {text}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{C.DIM}{default}{C.RESET}]" if default else ""
    result = input(f"  {C.BOLD}{prompt}{suffix}: {C.RESET}").strip()
    return result or default


def ask_yn(prompt: str, default: bool = True) -> bool:
    yn = f"{C.GREEN}Y{C.RESET}/n" if default else f"y/{C.GREEN}N{C.RESET}"
    result = input(f"  {C.BOLD}{prompt}{C.RESET} ({yn}): ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes")


def ask_choice(prompt: str, options: list[tuple[str, str]], default: str = "1") -> str:
    """Single select. options: [(key, label), ...]. Returns key."""
    print(f"  {C.BOLD}{prompt}{C.RESET}")
    for key, label in options:
        marker = f"{C.GREEN}●{C.RESET}" if key == default else f"{C.DIM}○{C.RESET}"
        print(f"    {marker} [{C.BOLD}{key}{C.RESET}] {label}")
    result = input(f"\n  Select [{C.DIM}{default}{C.RESET}]: ").strip()
    valid_keys = [k for k, _ in options]
    return result if result in valid_keys else default


def ask_multi(prompt: str, options: list[tuple[str, str]]) -> list[str]:
    """Multi select. Returns list of keys."""
    print(f"  {C.BOLD}{prompt}{C.RESET}")
    for key, label in options:
        print(f"    [{C.BOLD}{key}{C.RESET}] {label}")
    result = input(f"\n  Enter numbers (e.g. 1,2,3): ").strip()
    valid_keys = {k for k, _ in options}
    selected = []
    for part in result.split(","):
        part = part.strip()
        if part in valid_keys:
            selected.append(part)
    return selected


def check_cmd(name: str, *alt_names: str) -> tuple[bool, str, str]:
    """Check if a command exists. Returns (found, path, version)."""
    names = [name] + list(alt_names)
    for n in names:
        path = shutil.which(n)
        if path:
            try:
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
                ver = (r.stdout or r.stderr or "").strip().split("\n")[0]
                return True, path, ver
            except Exception:
                return True, path, "(found)"
    return False, "", ""


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, return result."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kwargs)


# ---------------------------------------------------------------------------
# Claude model definitions
# ---------------------------------------------------------------------------

CLAUDE_MODELS = [
    {
        "id": "claude-opus-4-6",
        "name": "Claude Opus 4.6 (via Bridge)",
        "alias": "Opus (Bridge)",
        "reasoning": True,
        "context_window": 200000,
        "max_tokens": 16384,
        "port": 5001,
        "tier": "large",
    },
    {
        "id": "claude-sonnet-4-6",
        "name": "Claude Sonnet 4.6 (via Bridge)",
        "alias": "Sonnet (Bridge)",
        "reasoning": False,
        "context_window": 200000,
        "max_tokens": 16384,
        "port": 5002,
        "tier": "medium",
    },
    {
        "id": "claude-haiku-4-5-20251001",
        "name": "Claude Haiku 4.5 (via Bridge)",
        "alias": "Haiku (Bridge)",
        "reasoning": False,
        "context_window": 200000,
        "max_tokens": 16384,
        "port": 5003,
        "tier": "small",
    },
]


# ---------------------------------------------------------------------------
# Step 1: Welcome
# ---------------------------------------------------------------------------

def step_welcome() -> dict:
    banner("Claude Proxy Bridge — Full Setup")
    print(f"  {C.DIM}This script sets up the proxy bridge AND configures")
    print(f"  OpenClaw or NanoClaw to use it as their LLM backend.{C.RESET}")
    print()
    print(f"  {C.DIM}The bridge bypasses Claude Code's OAuth by using your")
    print(f"  already-authenticated CLI session as a local API.{C.RESET}")
    print()

    info(f"OS:       {platform.system()} {platform.release()} ({platform.machine()})")
    info(f"Python:   {platform.python_version()}")
    info(f"Home:     {HOME}")
    info(f"Bridge:   {SCRIPT_DIR}")

    return {
        "os": platform.system(),
        "python": platform.python_version(),
    }


# ---------------------------------------------------------------------------
# Step 2: Prerequisites
# ---------------------------------------------------------------------------

def step_prerequisites() -> dict:
    step(1, "Checking prerequisites")

    results = {}

    # Python
    ok(f"Python {platform.python_version()}")
    results["python"] = True

    # pip
    found, path, ver = check_cmd("pip", "pip3")
    if found:
        ok(f"pip: {ver}")
    else:
        fail("pip not found")
    results["pip"] = found

    # Node.js
    found, path, ver = check_cmd("node")
    if found:
        ok(f"Node.js: {ver}")
    else:
        warn("Node.js not found — needed for OpenClaw")
    results["node"] = found

    # pnpm (OpenClaw uses it)
    found, path, ver = check_cmd("pnpm")
    if found:
        ok(f"pnpm: {ver}")
    else:
        skip("pnpm not found — needed only for OpenClaw dev")
    results["pnpm"] = found

    # Claude CLI
    found, path, ver = check_cmd("claude", "claude.cmd", "claude.exe")
    if found:
        ok(f"Claude Code CLI: {ver}")
    else:
        warn("Claude CLI not found — the bridge needs it for Claude models")
    results["claude_cli"] = found
    results["claude_cli_path"] = path

    # Docker (optional)
    found, path, ver = check_cmd("docker")
    if found:
        ok(f"Docker: {ver}")
    else:
        skip("Docker not found — needed only for OpenClaw Docker mode")
    results["docker"] = found

    return results


# ---------------------------------------------------------------------------
# Step 3: Choose target
# ---------------------------------------------------------------------------

def step_choose_target() -> str:
    step(2, "What do you want to set up?")

    # Auto-detect installations
    oc_found = OPENCLAW_DIR.exists()
    nc_found = NANOCLAW_DIR.exists()

    options = []
    oc_label = "OpenClaw"
    if oc_found:
        oc_label += f" {C.GREEN}(found at {OPENCLAW_DIR}){C.RESET}"
    options.append(("1", oc_label))

    nc_label = "NanoClaw"
    if nc_found:
        nc_label += f" {C.GREEN}(found at {NANOCLAW_DIR}){C.RESET}"
    options.append(("2", nc_label))

    options.append(("3", "Both"))
    options.append(("4", "Proxy bridge only (no client setup)"))

    choice = ask_choice("Choose your setup target:", options, "1")

    return {"1": "openclaw", "2": "nanoclaw", "3": "both", "4": "bridge-only"}[choice]


# ---------------------------------------------------------------------------
# Step 4: Select models
# ---------------------------------------------------------------------------

def step_select_models() -> list[dict]:
    step(3, "Select Claude models to expose via the bridge")

    options = []
    for i, m in enumerate(CLAUDE_MODELS, 1):
        options.append((str(i), f"{m['name']:45s} → port {m['port']}"))

    selected = ask_multi("Which models do you want?", options)

    if not selected:
        info("No selection — using all models")
        return list(CLAUDE_MODELS)

    models = []
    for s in selected:
        idx = int(s) - 1
        if 0 <= idx < len(CLAUDE_MODELS):
            models.append(CLAUDE_MODELS[idx])

    if not models:
        models = list(CLAUDE_MODELS)

    print()
    for m in models:
        ok(f"{m['id']:35s} → :{m['port']}")

    return models


# ---------------------------------------------------------------------------
# Step 5: Configure smart routing
# ---------------------------------------------------------------------------

def step_routing(models: list[dict]) -> dict:
    step(4, "Smart routing configuration")

    enable = ask_yn("Enable smart routing? (model=\"auto\" picks best model per request)", True)
    if not enable:
        return {"enabled": False}

    # Auto-assign
    large = next((m for m in models if m["tier"] == "large"), models[0])
    medium = next((m for m in models if m["tier"] == "medium"), models[0])
    small = next((m for m in models if m["tier"] == "small"), models[-1])

    name_map = {m["id"]: m for m in models}

    routing = {
        "enabled": True,
        "scenario_models": {
            "complex": large["id"],
            "code": medium["id"],
            "long": large["id"],
            "moderate": medium["id"],
            "simple": small["id"],
        },
    }

    info(f"complex  → {large['id']}")
    info(f"code     → {medium['id']}")
    info(f"moderate → {medium['id']}")
    info(f"simple   → {small['id']}")

    return routing


# ---------------------------------------------------------------------------
# Step 6: Setup proxy bridge
# ---------------------------------------------------------------------------

def step_setup_bridge(models: list[dict], routing: dict) -> None:
    step(5, "Setting up the proxy bridge")

    # Create venv
    venv_path = SCRIPT_DIR / ".venv"
    if not venv_path.exists():
        info("Creating virtual environment...")
        run([sys.executable, "-m", "venv", str(venv_path)])
        ok("Virtual environment created")
    else:
        ok("Virtual environment already exists")

    # Install deps
    if sys.platform == "win32":
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        pip_path = venv_path / "bin" / "pip"

    if pip_path.exists():
        info("Installing dependencies...")
        r = run([str(pip_path), "install", "-e", str(SCRIPT_DIR), "-q"])
        if r.returncode == 0:
            ok("Dependencies installed")
        else:
            warn(f"pip install returned code {r.returncode}")
            if r.stderr:
                info(r.stderr[:200])
    else:
        warn("pip not found in venv — run manually: pip install -e .")

    # Generate .env
    env_path = SCRIPT_DIR / ".env"
    if not env_path.exists():
        env_content = textwrap.dedent(f"""\
            HOST={BRIDGE_HOST}
            BRIDGE_PORT={BRIDGE_PORT}
            API_KEY={API_KEY}
            CLAUDE_CLI_PATH=
            REQUEST_TIMEOUT=300
            MAX_CONCURRENT=5
            LOG_LEVEL=INFO
            SMART_ROUTING={'true' if routing.get('enabled') else 'false'}
            ROUTING_LONG_CONTEXT_THRESHOLD=50000
            ROUTING_MAX_FALLBACK_ATTEMPTS=2
        """)
        env_path.write_text(env_content, encoding="utf-8")
        ok(f"Generated {env_path}")
    else:
        ok(f".env already exists — keeping it")

    # Generate bridge.yaml (only if custom models or doesn't exist)
    yaml_path = SCRIPT_DIR / "bridge.yaml"
    lines = [
        "# Generated by setup.py",
        "",
        "providers:",
        "  claude-cli:",
        "    type: claude_cli",
        '    cli_path: ""',
        "",
        "models:",
    ]
    for m in models:
        name = m["id"].replace("claude-", "").replace("-20251001", "")
        lines.append(f"  {name}:")
        lines.append(f"    provider: claude-cli")
        lines.append(f'    model_id: "{m["id"]}"')
        lines.append(f"    port: {m['port']}")
        lines.append(f"    context_window: {m['context_window']}")
        lines.append(f"    max_tokens: {m['max_tokens']}")

    if routing.get("enabled") and routing.get("scenario_models"):
        lines.append("")
        lines.append("routing:")
        lines.append("  scenario_models:")
        for scenario, model_id in routing["scenario_models"].items():
            name = model_id.replace("claude-", "").replace("-20251001", "")
            lines.append(f"    {scenario}: {name}")

    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok(f"Generated {yaml_path}")


# ---------------------------------------------------------------------------
# Step 7: Configure OpenClaw
# ---------------------------------------------------------------------------

def step_setup_openclaw(models: list[dict]) -> dict:
    step(6, "Configuring OpenClaw")

    # Find OpenClaw
    global OPENCLAW_DIR
    if not OPENCLAW_DIR.exists():
        custom = ask("OpenClaw directory path", str(DESKTOP / "openclaw"))
        OPENCLAW_DIR = Path(custom)
        if not OPENCLAW_DIR.exists():
            fail(f"Directory not found: {OPENCLAW_DIR}")
            return {}

    ok(f"Found OpenClaw at {OPENCLAW_DIR}")

    # Read existing config
    OPENCLAW_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if OPENCLAW_CONFIG_FILE.exists():
        try:
            existing = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8"))
            ok(f"Loaded existing config ({len(existing)} top-level keys)")
        except (json.JSONDecodeError, OSError) as e:
            warn(f"Could not parse existing config: {e}")
            existing = {}

    # Build provider entry
    bridge_models = []
    for m in models:
        bridge_models.append({
            "id": m["id"],
            "name": m["name"],
            "reasoning": m.get("reasoning", False),
            "input": ["text"],
            "contextWindow": m["context_window"],
            "maxTokens": m["max_tokens"],
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        })

    # Build per-model providers (direct port access) + smart router
    providers: dict = {}

    for m in models:
        pkey = f"bridge-{m['id'].replace('claude-', '').split('-2025')[0]}"
        providers[pkey] = {
            "baseUrl": f"http://{BRIDGE_HOST}:{m['port']}/v1",
            "apiKey": API_KEY,
            "api": "openai-completions",
            "models": [{
                "id": m["id"],
                "name": m["name"],
                "reasoning": m.get("reasoning", False),
                "input": ["text"],
                "contextWindow": m["context_window"],
                "maxTokens": m["max_tokens"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            }],
        }

    # Smart router provider
    providers["bridge-auto"] = {
        "baseUrl": f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/v1",
        "apiKey": API_KEY,
        "api": "openai-completions",
        "models": [{
            "id": "auto",
            "name": "Smart Router (auto-selects best model)",
            "reasoning": True,
            "input": ["text"],
            "contextWindow": 200000,
            "maxTokens": 16384,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        }],
    }

    # Merge into config
    if "models" not in existing:
        existing["models"] = {}
    existing["models"]["mode"] = "merge"
    if "providers" not in existing["models"]:
        existing["models"]["providers"] = {}
    existing["models"]["providers"].update(providers)

    ok(f"Added {len(providers)} bridge providers to config")

    # Set agent defaults
    primary_model = models[0]  # Most capable
    fallback_models = models[1:] if len(models) > 1 else []
    primary_provider = f"bridge-{primary_model['id'].replace('claude-', '').split('-2025')[0]}"

    if "agents" not in existing:
        existing["agents"] = {}
    if "defaults" not in existing["agents"]:
        existing["agents"]["defaults"] = {}

    # Model selection
    print()
    info("Choose default model for OpenClaw agents:")
    model_options = []
    for i, m in enumerate(models, 1):
        pkey = f"bridge-{m['id'].replace('claude-', '').split('-2025')[0]}"
        model_options.append((str(i), f"{m['name']}"))
    model_options.append((str(len(models) + 1), "Smart Router (auto-picks best model per request)"))

    choice = ask_choice("Primary model for agents:", model_options, "1")
    choice_idx = int(choice) - 1

    if choice_idx < len(models):
        chosen = models[choice_idx]
        pkey = f"bridge-{chosen['id'].replace('claude-', '').split('-2025')[0]}"
        primary_ref = f"{pkey}/{chosen['id']}"
        fallback_refs = []
        for m in models:
            if m["id"] != chosen["id"]:
                fpkey = f"bridge-{m['id'].replace('claude-', '').split('-2025')[0]}"
                fallback_refs.append(f"{fpkey}/{m['id']}")
    else:
        primary_ref = "bridge-auto/auto"
        fallback_refs = []
        for m in models:
            fpkey = f"bridge-{m['id'].replace('claude-', '').split('-2025')[0]}"
            fallback_refs.append(f"{fpkey}/{m['id']}")

    existing["agents"]["defaults"]["model"] = {
        "primary": primary_ref,
        "fallbacks": fallback_refs,
    }

    # Model aliases
    if "models" not in existing["agents"]["defaults"]:
        existing["agents"]["defaults"]["models"] = {}
    for m in models:
        pkey = f"bridge-{m['id'].replace('claude-', '').split('-2025')[0]}"
        existing["agents"]["defaults"]["models"][f"{pkey}/{m['id']}"] = {
            "alias": m["alias"],
        }
    existing["agents"]["defaults"]["models"]["bridge-auto/auto"] = {
        "alias": "Auto (Smart Router)",
    }

    ok(f"Primary: {primary_ref}")
    if fallback_refs:
        ok(f"Fallbacks: {', '.join(fallback_refs)}")

    # Telegram bot
    print()
    has_telegram = (
        existing.get("channels", {}).get("telegram", {}).get("botToken", "")
    )
    if has_telegram:
        ok(f"Telegram bot already configured")
    else:
        setup_tg = ask_yn("Set up a Telegram bot?", False)
        if setup_tg:
            print()
            info("1. Open Telegram → search @BotFather")
            info("2. Send /newbot → pick a name and username")
            info("3. Copy the API token")
            print()
            token = ask("Telegram bot token")
            if token:
                if "channels" not in existing:
                    existing["channels"] = {}
                existing["channels"]["telegram"] = {
                    "enabled": True,
                    "dmPolicy": "open",
                    "botToken": token,
                    "allowFrom": ["*"],
                }
                ok("Telegram bot configured")

    # Write config
    OPENCLAW_CONFIG_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    ok(f"Saved {OPENCLAW_CONFIG_FILE}")

    return existing


# ---------------------------------------------------------------------------
# Step 8: Configure NanoClaw
# ---------------------------------------------------------------------------

def step_setup_nanoclaw(models: list[dict]) -> dict:
    step(6, "Configuring NanoClaw")

    global NANOCLAW_DIR
    if not NANOCLAW_DIR.exists():
        custom = ask("NanoClaw directory path", str(DESKTOP / "nanoclaw"))
        NANOCLAW_DIR = Path(custom)

    if NANOCLAW_DIR.exists():
        ok(f"Found NanoClaw at {NANOCLAW_DIR}")
    else:
        warn(f"NanoClaw not found at {NANOCLAW_DIR}")
        info("Config will be generated — install NanoClaw later and point it here")

    # Build config
    config = {
        "llm": {
            "baseUrl": f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/v1",
            "apiKey": API_KEY,
            "model": "auto",
        },
        "models": {},
    }

    for m in models:
        config["models"][m["id"]] = {
            "baseUrl": f"http://{BRIDGE_HOST}:{m['port']}/v1",
            "apiKey": API_KEY,
            "model": m["id"],
            "name": m["name"],
        }

    # Write to bridge configs dir
    nc_config_path = SCRIPT_DIR / "configs" / "nanoclaw_bridge.json"
    nc_config_path.parent.mkdir(parents=True, exist_ok=True)
    nc_config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    ok(f"Generated {nc_config_path}")

    # Also write to NanoClaw dir if it exists
    if NANOCLAW_DIR.exists():
        nc_target = NANOCLAW_DIR / "config" / "proxy-bridge.json"
        nc_target.parent.mkdir(parents=True, exist_ok=True)
        nc_target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        ok(f"Wrote {nc_target}")

    return config


# ---------------------------------------------------------------------------
# Step 9: Register with health check dashboard
# ---------------------------------------------------------------------------

def step_health_check(models: list[dict]) -> None:
    if not HEALTH_CHECK_DIR.exists():
        return

    step(7, "Health Check Dashboard")
    info(f"Found health check dashboard at {HEALTH_CHECK_DIR}")

    register = ask_yn("Register bridge endpoints with the dashboard?", True)
    if not register:
        return

    # Try to register via the API
    import urllib.request
    import urllib.error

    base = "http://localhost:4400"

    endpoints = []
    for m in models:
        endpoints.append({
            "name": f"Bridge - {m['name'].split('(')[0].strip()}",
            "url": f"http://{BRIDGE_HOST}:{m['port']}/health",
            "use_case": "claude-proxy-bridge",
            "description": f"Proxy for {m['id']}",
        })
    endpoints.append({
        "name": "Bridge - Smart Router",
        "url": f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/health",
        "use_case": "claude-proxy-bridge",
        "description": "Smart router (auto model selection)",
    })

    registered = 0
    for ep in endpoints:
        try:
            data = json.dumps(ep).encode("utf-8")
            req = urllib.request.Request(
                f"{base}/api/register",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 201):
                    registered += 1
        except (urllib.error.URLError, OSError):
            break

    if registered > 0:
        ok(f"Registered {registered}/{len(endpoints)} endpoints with dashboard")
    else:
        skip("Dashboard not running — start it later and register manually")


# ---------------------------------------------------------------------------
# Step 10: Generate start scripts
# ---------------------------------------------------------------------------

def step_generate_start_scripts(target: str, models: list[dict]) -> None:
    step(8, "Generating start scripts")

    if sys.platform == "win32":
        venv_activate = f'call "{SCRIPT_DIR}\\.venv\\Scripts\\activate.bat"'
        python_cmd = "python"
    else:
        venv_activate = f'source "{SCRIPT_DIR}/.venv/bin/activate"'
        python_cmd = "python3"

    # --- Start bridge script ---
    if sys.platform == "win32":
        bridge_script = SCRIPT_DIR / "start_bridge.bat"
        bridge_content = f"""@echo off
echo Starting Claude Proxy Bridge...
cd /d "{SCRIPT_DIR}"
{venv_activate}
{python_cmd} start.py
pause
"""
    else:
        bridge_script = SCRIPT_DIR / "start_bridge.sh"
        bridge_content = f"""#!/bin/bash
echo "Starting Claude Proxy Bridge..."
cd "{SCRIPT_DIR}"
{venv_activate}
{python_cmd} start.py
"""

    bridge_script.write_text(bridge_content, encoding="utf-8")
    if sys.platform != "win32":
        bridge_script.chmod(0o755)
    ok(f"Generated {bridge_script}")

    # --- Full pipeline script ---
    if target in ("openclaw", "both"):
        if sys.platform == "win32":
            full_script = SCRIPT_DIR / "start_all.bat"
            full_content = f"""@echo off
echo ============================================================
echo  Claude Proxy Bridge + OpenClaw — Full Pipeline
echo ============================================================
echo.

echo [1/2] Starting proxy bridge...
cd /d "{SCRIPT_DIR}"
start "Claude Proxy Bridge" cmd /k "{venv_activate} && {python_cmd} start.py"

echo Waiting for bridge to start...
timeout /t 5 /nobreak >nul

echo [2/2] Starting OpenClaw...
cd /d "{OPENCLAW_DIR}"
start "OpenClaw" cmd /k "pnpm start"

echo.
echo ============================================================
echo  Both services starting in separate windows.
echo  Bridge:   http://{BRIDGE_HOST}:{BRIDGE_PORT}/health
echo  OpenClaw: http://localhost:18789
echo ============================================================
pause
"""
        else:
            full_script = SCRIPT_DIR / "start_all.sh"
            full_content = f"""#!/bin/bash
echo "============================================================"
echo " Claude Proxy Bridge + OpenClaw — Full Pipeline"
echo "============================================================"
echo ""

echo "[1/2] Starting proxy bridge in background..."
cd "{SCRIPT_DIR}"
{venv_activate}
{python_cmd} start.py &
BRIDGE_PID=$!
echo "Bridge PID: $BRIDGE_PID"

sleep 3

echo "[2/2] Starting OpenClaw..."
cd "{OPENCLAW_DIR}"
pnpm start &
OPENCLAW_PID=$!
echo "OpenClaw PID: $OPENCLAW_PID"

echo ""
echo "============================================================"
echo " Both services running."
echo " Bridge:   http://{BRIDGE_HOST}:{BRIDGE_PORT}/health"
echo " OpenClaw: http://localhost:18789"
echo " Press Ctrl+C to stop both."
echo "============================================================"

trap "kill $BRIDGE_PID $OPENCLAW_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
"""

        full_script.write_text(full_content, encoding="utf-8")
        if sys.platform != "win32":
            full_script.chmod(0o755)
        ok(f"Generated {full_script}")

    if target in ("nanoclaw", "both"):
        if sys.platform == "win32":
            nc_script = SCRIPT_DIR / "start_with_nanoclaw.bat"
            nc_content = f"""@echo off
echo Starting Claude Proxy Bridge + NanoClaw...
cd /d "{SCRIPT_DIR}"
start "Claude Proxy Bridge" cmd /k "{venv_activate} && {python_cmd} start.py"
timeout /t 5 /nobreak >nul
cd /d "{NANOCLAW_DIR}"
start "NanoClaw" cmd /k "npm start"
pause
"""
        else:
            nc_script = SCRIPT_DIR / "start_with_nanoclaw.sh"
            nc_content = f"""#!/bin/bash
echo "Starting Claude Proxy Bridge + NanoClaw..."
cd "{SCRIPT_DIR}" && {venv_activate} && {python_cmd} start.py &
sleep 3
cd "{NANOCLAW_DIR}" && npm start &
wait
"""

        nc_script.write_text(nc_content, encoding="utf-8")
        if sys.platform != "win32":
            nc_script.chmod(0o755)
        ok(f"Generated {nc_script}")


# ---------------------------------------------------------------------------
# Step 11: Test
# ---------------------------------------------------------------------------

def step_test(models: list[dict]) -> None:
    step(9, "Verification")

    info("Checking bridge is ready to start...")

    # Verify venv + imports
    if sys.platform == "win32":
        py = SCRIPT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        py = SCRIPT_DIR / ".venv" / "bin" / "python3"

    if py.exists():
        r = run([str(py), "-c", "from src.config import settings; print(f'Models: {len(settings.models)}')"],
                cwd=str(SCRIPT_DIR))
        if r.returncode == 0:
            ok(f"Bridge config loads OK — {r.stdout.strip()}")
        else:
            warn(f"Config test failed: {r.stderr[:200]}")
    else:
        warn("Cannot find Python in venv for testing")

    # Check OpenClaw config
    if OPENCLAW_CONFIG_FILE.exists():
        try:
            cfg = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8"))
            providers = cfg.get("models", {}).get("providers", {})
            bridge_providers = [k for k in providers if k.startswith("bridge-")]
            if bridge_providers:
                ok(f"OpenClaw config has {len(bridge_providers)} bridge providers")
                primary = cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
                if primary:
                    ok(f"OpenClaw primary model: {primary}")
            else:
                skip("No bridge providers in OpenClaw config")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Step 12: Summary
# ---------------------------------------------------------------------------

def step_summary(target: str, models: list[dict]) -> None:
    banner("Setup Complete!")

    print(f"  {C.BOLD}Bridge endpoints:{C.RESET}")
    for m in models:
        print(f"    {m['id']:35s} → http://{BRIDGE_HOST}:{m['port']}/v1/chat/completions")
    print(f"    {'auto (smart router)':35s} → http://{BRIDGE_HOST}:{BRIDGE_PORT}/v1/chat/completions")

    print()
    print(f"  {C.BOLD}Quick start:{C.RESET}")

    if sys.platform == "win32":
        if target in ("openclaw", "both"):
            print(f"    {C.GREEN}start_all.bat{C.RESET}          — starts bridge + OpenClaw")
        print(f"    {C.GREEN}start_bridge.bat{C.RESET}       — starts bridge only")
    else:
        if target in ("openclaw", "both"):
            print(f"    {C.GREEN}./start_all.sh{C.RESET}         — starts bridge + OpenClaw")
        print(f"    {C.GREEN}./start_bridge.sh{C.RESET}      — starts bridge only")

    print()
    print(f"  {C.BOLD}Manual start:{C.RESET}")
    if sys.platform == "win32":
        print(f"    cd {SCRIPT_DIR}")
        print(f"    .venv\\Scripts\\activate")
    else:
        print(f"    cd {SCRIPT_DIR}")
        print(f"    source .venv/bin/activate")
    print(f"    python start.py")

    print()
    print(f"  {C.BOLD}Health check:{C.RESET}")
    print(f"    python scripts/health_check.py")

    print()
    print(f"  {C.BOLD}Test with curl:{C.RESET}")
    print(f"    curl http://localhost:{BRIDGE_PORT}/v1/chat/completions \\")
    print(f'      -H "Content-Type: application/json" \\')
    print(f'      -H "Authorization: Bearer {API_KEY}" \\')
    print(f"      -d '{{\"model\":\"auto\",\"messages\":[{{\"role\":\"user\",\"content\":\"Hello!\"}}]}}'")

    if target in ("openclaw", "both"):
        print()
        print(f"  {C.BOLD}OpenClaw config:{C.RESET}")
        print(f"    {OPENCLAW_CONFIG_FILE}")
        tg = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8")).get("channels", {}).get("telegram", {})
        if tg.get("botToken"):
            print()
            print(f"  {C.BOLD}Telegram:{C.RESET}")
            print(f"    Bot is configured — start OpenClaw and message your bot!")

    print()
    print(f"  {C.BOLD}How it works:{C.RESET}")
    print(f"  {C.DIM}Your Claude CLI is already authenticated on this machine.")
    print(f"  The bridge spawns 'claude -p' subprocesses using that session.")
    print(f"  OpenClaw/NanoClaw just hit the local HTTP API — no OAuth needed.{C.RESET}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        # Welcome
        step_welcome()

        # Prerequisites
        prereqs = step_prerequisites()

        if not prereqs.get("claude_cli"):
            print()
            warn("Claude CLI is not installed. The bridge won't work without it.")
            cont = ask_yn("Continue anyway?", False)
            if not cont:
                print("\n  Install Claude CLI: npm install -g @anthropic-ai/claude-code\n")
                sys.exit(1)

        # Choose target
        target = step_choose_target()

        # Select models
        models = step_select_models()

        # Routing
        routing = step_routing(models)

        # Setup bridge
        step_setup_bridge(models, routing)

        # Setup client
        if target in ("openclaw", "both"):
            step_setup_openclaw(models)

        if target in ("nanoclaw", "both"):
            step_setup_nanoclaw(models)

        # Health check dashboard
        step_health_check(models)

        # Generate start scripts
        step_generate_start_scripts(target, models)

        # Test
        step_test(models)

        # Summary
        step_summary(target, models)

    except KeyboardInterrupt:
        print(f"\n\n  {C.YELLOW}Setup cancelled.{C.RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
