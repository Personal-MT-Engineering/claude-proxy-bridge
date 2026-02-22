"""Configuration & environment variable loading.

Supports two modes:
1. bridge.yaml in project root → multi-provider, dynamic model list
2. No bridge.yaml → backward-compatible 3 Claude CLI models (Opus, Sonnet, Haiku)
"""

import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


# ---------------------------------------------------------------------------
# Provider & Model dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for an LLM provider (Claude CLI or HTTP-based)."""
    key: str            # "claude-cli", "openai", "deepseek", ...
    type: str           # "claude_cli" or "http"
    base_url: str = ""  # for http providers
    api_key: str = ""   # resolved from ${ENV_VAR} at load time
    cli_path: str = ""  # for claude_cli only
    extra_headers: dict[str, str] = field(default_factory=dict)


# Default provider used when no bridge.yaml is present
_DEFAULT_CLAUDE_CLI_PROVIDER = ProviderConfig(
    key="claude-cli",
    type="claude_cli",
    cli_path=os.getenv("CLAUDE_CLI_PATH", ""),
)


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for a single model exposed by the bridge."""
    name: str               # alias key: "opus", "gpt-4o", "llama3"
    model_id: str           # "claude-opus-4-6", "gpt-4o", etc.
    port: int
    provider: ProviderConfig = _DEFAULT_CLAUDE_CLI_PROVIDER
    context_window: int = 200000
    max_tokens: int = 16384


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------

_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} with the corresponding environment variable value."""
    def _replace(m: re.Match) -> str:
        var = m.group(1)
        return os.getenv(var, "")
    return _ENV_VAR_RE.sub(_replace, value)


def _load_bridge_yaml() -> dict | None:
    """Load bridge.yaml from project root. Returns None if absent."""
    yaml_path = _project_root / "bridge.yaml"
    if not yaml_path.exists():
        return None

    try:
        import yaml
    except ImportError:
        logger.warning("bridge.yaml found but pyyaml is not installed. Using defaults.")
        return None

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        logger.warning("bridge.yaml is not a valid mapping. Using defaults.")
        return None

    return data


def _build_from_yaml(data: dict) -> tuple[
    list[ModelConfig],
    dict[str, ModelConfig],
    dict[str, str],
    dict[str, list[str]],
]:
    """Build model list, model map, and routing tables from parsed YAML.

    Returns (models, model_map, scenario_models, fallback_chains).
    """
    # --- Parse providers ---
    providers: dict[str, ProviderConfig] = {}
    for key, pdata in data.get("providers", {}).items():
        if not isinstance(pdata, dict):
            continue
        ptype = pdata.get("type", "http")
        base_url = pdata.get("base_url", "")
        raw_api_key = pdata.get("api_key", "")
        api_key = _resolve_env_vars(raw_api_key) if raw_api_key else ""
        cli_path = pdata.get("cli_path", "")
        extra_headers = pdata.get("extra_headers", {}) or {}
        providers[key] = ProviderConfig(
            key=key, type=ptype, base_url=base_url, api_key=api_key,
            cli_path=cli_path, extra_headers=dict(extra_headers),
        )

    # --- Parse models ---
    models: list[ModelConfig] = []
    model_map: dict[str, ModelConfig] = {}
    for name, mdata in data.get("models", {}).items():
        if not isinstance(mdata, dict):
            continue
        provider_key = mdata.get("provider", "")
        provider = providers.get(provider_key)
        if not provider:
            logger.warning("Model '%s' references unknown provider '%s', skipping.", name, provider_key)
            continue
        mc = ModelConfig(
            name=name,
            model_id=mdata.get("model_id", name),
            port=int(mdata.get("port", 5001 + len(models))),
            provider=provider,
            context_window=int(mdata.get("context_window", 200000)),
            max_tokens=int(mdata.get("max_tokens", 16384)),
        )
        models.append(mc)
        model_map[mc.model_id] = mc
        model_map[mc.name] = mc

    # --- Parse routing ---
    routing = data.get("routing", {}) or {}
    scenario_models: dict[str, str] = {}
    for scenario, model_key in (routing.get("scenario_models", {}) or {}).items():
        scenario_models[scenario] = str(model_key)

    fallback_chains: dict[str, list[str]] = {}
    for scenario, chain in (routing.get("fallback_chains", {}) or {}).items():
        if isinstance(chain, list):
            fallback_chains[scenario] = [str(m) for m in chain]

    return models, model_map, scenario_models, fallback_chains


# ---------------------------------------------------------------------------
# Build default (backward-compatible) configuration
# ---------------------------------------------------------------------------

def _build_defaults() -> tuple[
    list[ModelConfig],
    dict[str, ModelConfig],
    dict[str, str],
    dict[str, list[str]],
]:
    """Construct the same 3 Claude CLI models as before (no bridge.yaml)."""
    opus = ModelConfig(
        name="opus",
        model_id="claude-opus-4-6",
        port=int(os.getenv("OPUS_PORT", "5001")),
        provider=_DEFAULT_CLAUDE_CLI_PROVIDER,
    )
    sonnet = ModelConfig(
        name="sonnet",
        model_id="claude-sonnet-4-6",
        port=int(os.getenv("SONNET_PORT", "5002")),
        provider=_DEFAULT_CLAUDE_CLI_PROVIDER,
    )
    haiku = ModelConfig(
        name="haiku",
        model_id="claude-haiku-4-5-20251001",
        port=int(os.getenv("HAIKU_PORT", "5003")),
        provider=_DEFAULT_CLAUDE_CLI_PROVIDER,
    )

    models = [opus, sonnet, haiku]
    model_map: dict[str, ModelConfig] = {}
    for m in models:
        model_map[m.model_id] = m
        model_map[m.name] = m
    # Common alias
    model_map["claude-haiku-4-5"] = haiku

    # Default routing
    scenario_models = {
        "complex": "opus", "code": "sonnet", "long": "opus",
        "moderate": "sonnet", "simple": "haiku",
    }
    fallback_chains = {
        "complex": ["opus", "sonnet", "haiku"],
        "code": ["sonnet", "opus", "haiku"],
        "long": ["opus", "sonnet"],
        "moderate": ["sonnet", "haiku", "opus"],
        "simple": ["haiku", "sonnet"],
    }

    return models, model_map, scenario_models, fallback_chains


# ---------------------------------------------------------------------------
# Load configuration (YAML or defaults)
# ---------------------------------------------------------------------------

_yaml_data = _load_bridge_yaml()

if _yaml_data is not None:
    ALL_MODELS, MODEL_MAP, _yaml_scenario_models, _yaml_fallback_chains = _build_from_yaml(_yaml_data)
    if not ALL_MODELS:
        logger.warning("bridge.yaml produced no models — falling back to defaults.")
        ALL_MODELS, MODEL_MAP, _yaml_scenario_models, _yaml_fallback_chains = _build_defaults()
else:
    ALL_MODELS, MODEL_MAP, _yaml_scenario_models, _yaml_fallback_chains = _build_defaults()


# ---------------------------------------------------------------------------
# Env-var overrides (same as before, merged on top of YAML/defaults)
# ---------------------------------------------------------------------------

def _parse_fallback_overrides() -> dict[str, list[str]]:
    """Parse ROUTING_FALLBACK_* env vars into a dict of scenario -> [model_id, ...]."""
    overrides: dict[str, list[str]] = {}
    for scenario in ("complex", "code", "long", "moderate", "simple"):
        val = os.getenv(f"ROUTING_FALLBACK_{scenario.upper()}", "")
        if val.strip():
            overrides[scenario] = [m.strip() for m in val.split(",") if m.strip()]
    return overrides


def _parse_scenario_overrides() -> dict[str, str]:
    """Parse ROUTING_MODEL_* env vars into a dict of scenario -> model_id."""
    overrides: dict[str, str] = {}
    for scenario in ("complex", "code", "long", "moderate", "simple"):
        val = os.getenv(f"ROUTING_MODEL_{scenario.upper()}", "")
        if val.strip():
            overrides[scenario] = val.strip()
    return overrides


# ---------------------------------------------------------------------------
# Settings singleton
# ---------------------------------------------------------------------------

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

    # Routing tables — YAML values merged with env-var overrides
    routing_scenario_models: dict[str, str] = field(default_factory=lambda: {
        **_yaml_scenario_models, **_parse_scenario_overrides(),
    })
    routing_fallback_chains: dict[str, list[str]] = field(default_factory=lambda: {
        **_yaml_fallback_chains, **_parse_fallback_overrides(),
    })

    # Legacy aliases (env-var overrides only, for backward compat)
    routing_fallback_overrides: dict[str, list[str]] = field(default_factory=_parse_fallback_overrides)
    routing_scenario_overrides: dict[str, str] = field(default_factory=_parse_scenario_overrides)

    def resolve_claude_cli(self) -> str:
        """Find the claude CLI binary, cross-platform."""
        if self.claude_cli_path:
            p = Path(self.claude_cli_path)
            if p.exists():
                return str(p)
            raise FileNotFoundError(f"Claude CLI not found at configured path: {self.claude_cli_path}")

        # Check if any provider has a cli_path configured
        for m in self.models:
            if m.provider.type == "claude_cli" and m.provider.cli_path:
                p = Path(m.provider.cli_path)
                if p.exists():
                    return str(p)

        # Auto-detect
        if sys.platform == "win32":
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

    def has_claude_cli_provider(self) -> bool:
        """Check if any configured model uses the Claude CLI provider."""
        return any(m.provider.type == "claude_cli" for m in self.models)


settings = Settings()
