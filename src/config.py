"""Configuration & environment variable loading."""

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


@dataclass(frozen=True)
class ModelConfig:
    name: str
    model_id: str
    port: int


# Model definitions
OPUS = ModelConfig(name="opus", model_id="claude-opus-4-6", port=int(os.getenv("OPUS_PORT", "5001")))
SONNET = ModelConfig(name="sonnet", model_id="claude-sonnet-4-6", port=int(os.getenv("SONNET_PORT", "5002")))
HAIKU = ModelConfig(name="haiku", model_id="claude-haiku-4-5-20251001", port=int(os.getenv("HAIKU_PORT", "5003")))

ALL_MODELS = [OPUS, SONNET, HAIKU]

# Map model IDs to configs (including short aliases)
MODEL_MAP: dict[str, ModelConfig] = {}
for _m in ALL_MODELS:
    MODEL_MAP[_m.model_id] = _m
    MODEL_MAP[_m.name] = _m
# Common aliases
MODEL_MAP["claude-haiku-4-5"] = HAIKU


def _parse_fallback_overrides() -> dict[str, list[str]]:
    """Parse ROUTING_FALLBACK_* env vars into a dict of scenario → [model_id, ...]."""
    overrides: dict[str, list[str]] = {}
    for scenario in ("complex", "code", "long", "moderate", "simple"):
        val = os.getenv(f"ROUTING_FALLBACK_{scenario.upper()}", "")
        if val.strip():
            overrides[scenario] = [m.strip() for m in val.split(",") if m.strip()]
    return overrides


def _parse_scenario_overrides() -> dict[str, str]:
    """Parse ROUTING_MODEL_* env vars into a dict of scenario → model_id."""
    overrides: dict[str, str] = {}
    for scenario in ("complex", "code", "long", "moderate", "simple"):
        val = os.getenv(f"ROUTING_MODEL_{scenario.upper()}", "")
        if val.strip():
            overrides[scenario] = val.strip()
    return overrides


@dataclass
class Settings:
    host: str = os.getenv("HOST", "127.0.0.1")
    bridge_port: int = int(os.getenv("BRIDGE_PORT", "5000"))
    api_key: str = os.getenv("API_KEY", "local-proxy")
    claude_cli_path: str = os.getenv("CLAUDE_CLI_PATH", "")
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "300"))
    max_concurrent: int = int(os.getenv("MAX_CONCURRENT", "5"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    models: list[ModelConfig] = field(default_factory=lambda: list(ALL_MODELS))

    # Smart routing
    smart_routing_enabled: bool = os.getenv("SMART_ROUTING", "true").lower() in ("true", "1", "yes")
    routing_long_context_threshold: int = int(os.getenv("ROUTING_LONG_CONTEXT_THRESHOLD", "50000"))
    routing_max_fallback_attempts: int = int(os.getenv("ROUTING_MAX_FALLBACK_ATTEMPTS", "2"))
    routing_fallback_overrides: dict[str, list[str]] = field(default_factory=_parse_fallback_overrides)
    routing_scenario_overrides: dict[str, str] = field(default_factory=_parse_scenario_overrides)

    def resolve_claude_cli(self) -> str:
        """Find the claude CLI binary, cross-platform."""
        if self.claude_cli_path:
            p = Path(self.claude_cli_path)
            if p.exists():
                return str(p)
            raise FileNotFoundError(f"Claude CLI not found at configured path: {self.claude_cli_path}")

        # Auto-detect
        if sys.platform == "win32":
            # Try claude.cmd first (npm global install), then claude.exe
            for name in ("claude.cmd", "claude.exe", "claude"):
                found = shutil.which(name)
                if found:
                    return found
        else:
            found = shutil.which("claude")
            if found:
                return found

        raise FileNotFoundError(
            "Claude CLI not found on PATH. Install it or set CLAUDE_CLI_PATH in .env"
        )


settings = Settings()
