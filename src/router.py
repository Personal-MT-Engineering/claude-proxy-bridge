"""Smart routing engine — analyzes requests and picks the best model with fallback chains."""

import logging
import re
from dataclasses import dataclass
from enum import Enum

from .config import HAIKU, MODEL_MAP, OPUS, SONNET, ModelConfig, settings
from .openai_types import ChatCompletionRequest

logger = logging.getLogger(__name__)


class Scenario(str, Enum):
    """Request classification scenarios."""
    COMPLEX = "complex"          # Reasoning, architecture, multi-step analysis
    CODE_GENERATION = "code"     # Writing or reviewing code
    LONG_CONTEXT = "long"        # Large token count
    MODERATE = "moderate"        # General-purpose, balanced
    SIMPLE = "simple"            # Short answers, classification, greetings


@dataclass
class RoutingDecision:
    """Result of the smart router's analysis."""
    scenario: Scenario
    model: ModelConfig
    reason: str
    fallback_chain: list[ModelConfig]


# --- Token estimation ---

def estimate_tokens(text: str) -> int:
    """Rough token estimate. ~4 chars per token for English, ~2.5 for code."""
    if not text:
        return 0
    # Detect code-heavy content (more tokens per char due to symbols)
    code_indicators = text.count("```") + text.count("def ") + text.count("function ")
    if code_indicators >= 2:
        return max(1, int(len(text) / 2.5))
    return max(1, len(text) // 4)


def estimate_request_tokens(request: ChatCompletionRequest) -> int:
    """Estimate total token count across all messages."""
    total = 0
    for msg in request.messages:
        total += estimate_tokens(msg.content)
    return total


# --- Complexity signals ---

# Patterns that suggest complex reasoning tasks
_COMPLEX_PATTERNS = [
    r"\b(explain|analyze|architect|design|compare|evaluate|reason|trade-?off)\b",
    r"\b(step[- ]by[- ]step|in[- ]depth|thorough|comprehensive|detailed analysis)\b",
    r"\b(why does|how does .+ work|what are the implications)\b",
    r"\b(optimize|refactor|review .+ code|debug|root cause)\b",
    r"\b(implement .+ system|build .+ from scratch|create .+ architecture)\b",
    r"\b(proof|theorem|mathematical|algorithm complexity)\b",
]

# Patterns that suggest code generation
_CODE_PATTERNS = [
    r"\b(write|generate|create|implement|code|function|class|module)\b.*\b(code|script|program|function|api|endpoint)\b",
    r"```",
    r"\b(python|javascript|typescript|rust|go|java|c\+\+|sql|html|css)\b",
    r"\b(fix .+ bug|add .+ feature|write .+ test|create .+ file)\b",
    r"\b(import|export|require|from .+ import)\b",
]

# Patterns that suggest simple/quick responses
_SIMPLE_PATTERNS = [
    r"^(hi|hello|hey|thanks|thank you|ok|yes|no|sure)[.!]?$",
    r"^(what is|what's|who is|define|translate)\b.{0,50}$",
    r"^.{0,40}$",  # Very short messages (under 40 chars, e.g. greetings)
    r"^(summarize|tldr|tl;dr)\b",
]

# Patterns that push toward moderate (not trivial, but not deeply complex)
_MODERATE_PATTERNS = [
    r"\b(differences?|compare|overview|explain briefly|how to)\b",
    r"\b(example|show me|describe|what are the)\b",
    r"\b(best practice|recommend|suggest|which .+ should)\b",
]

# Patterns that suggest reasoning/thinking mode
_REASONING_PATTERNS = [
    r"\b(think|reason|consider|let's think|chain of thought)\b",
    r"\b(pros and cons|advantages|disadvantages|trade-?offs)\b",
    r"\b(plan|strategy|approach|methodology)\b",
    r"\b(philosophical|ethical|moral|existential)\b",
]


def _count_pattern_matches(text: str, patterns: list[str]) -> int:
    """Count how many patterns match in the text."""
    text_lower = text.lower()
    return sum(1 for p in patterns if re.search(p, text_lower, re.IGNORECASE))


def classify_scenario(request: ChatCompletionRequest) -> tuple[Scenario, str]:
    """Classify a request into a routing scenario.

    Returns (scenario, reason) explaining the classification.
    """
    token_count = estimate_request_tokens(request)

    # Combine all message content for analysis
    all_content = " ".join(m.content for m in request.messages if m.content)
    last_user_msg = ""
    for msg in reversed(request.messages):
        if msg.role == "user" and msg.content:
            last_user_msg = msg.content
            break

    message_count = len(request.messages)
    has_system_prompt = any(m.role == "system" for m in request.messages)

    # --- Long context detection (highest priority) ---
    long_threshold = settings.routing_long_context_threshold
    if token_count > long_threshold:
        return Scenario.LONG_CONTEXT, f"Token count ({token_count}) exceeds threshold ({long_threshold})"

    # --- Score each scenario ---
    complex_score = _count_pattern_matches(all_content, _COMPLEX_PATTERNS)
    complex_score += _count_pattern_matches(all_content, _REASONING_PATTERNS)
    if message_count > 10:
        complex_score += 2  # Long conversations suggest complexity
    if has_system_prompt and len(all_content) > 2000:
        complex_score += 1

    code_score = _count_pattern_matches(all_content, _CODE_PATTERNS)
    if all_content.count("```") >= 2:
        code_score += 2  # Multiple code blocks

    simple_score = _count_pattern_matches(last_user_msg, _SIMPLE_PATTERNS)
    if token_count < 50 and message_count <= 2:
        simple_score += 2
    if not has_system_prompt and token_count < 100:
        simple_score += 1

    moderate_score = _count_pattern_matches(all_content, _MODERATE_PATTERNS)
    if 100 <= token_count <= 2000 and message_count <= 5:
        moderate_score += 1

    logger.debug(
        "Routing scores: complex=%d code=%d simple=%d moderate=%d tokens=%d msgs=%d",
        complex_score, code_score, simple_score, moderate_score, token_count, message_count,
    )

    # --- Decision ---
    if complex_score >= 3:
        return Scenario.COMPLEX, f"High complexity score ({complex_score}): reasoning/analysis detected"

    if code_score >= 3:
        return Scenario.CODE_GENERATION, f"Code generation detected (score={code_score})"

    if simple_score >= 3 and complex_score < 2 and code_score < 2 and moderate_score < 2:
        return Scenario.SIMPLE, f"Simple query detected (score={simple_score}, tokens={token_count})"

    if code_score >= 2:
        return Scenario.CODE_GENERATION, f"Code-related content detected (score={code_score})"

    if complex_score >= 2:
        return Scenario.COMPLEX, f"Moderate complexity detected (score={complex_score})"

    if moderate_score >= 2 or token_count > 200:
        return Scenario.MODERATE, f"Moderate task detected (score={moderate_score}, tokens={token_count})"

    # Default: moderate
    return Scenario.MODERATE, f"General request (tokens={token_count}, msgs={message_count})"


# --- Fallback chains ---

# Default fallback chains per scenario (best → worst for that scenario)
DEFAULT_FALLBACK_CHAINS: dict[Scenario, list[ModelConfig]] = {
    Scenario.COMPLEX:         [OPUS, SONNET, HAIKU],
    Scenario.CODE_GENERATION: [SONNET, OPUS, HAIKU],
    Scenario.LONG_CONTEXT:    [OPUS, SONNET],
    Scenario.MODERATE:        [SONNET, HAIKU, OPUS],
    Scenario.SIMPLE:          [HAIKU, SONNET],
}

# Default primary model per scenario
DEFAULT_SCENARIO_MODELS: dict[Scenario, ModelConfig] = {
    Scenario.COMPLEX:         OPUS,
    Scenario.CODE_GENERATION: SONNET,
    Scenario.LONG_CONTEXT:    OPUS,
    Scenario.MODERATE:        SONNET,
    Scenario.SIMPLE:          HAIKU,
}


def get_fallback_chain(scenario: Scenario) -> list[ModelConfig]:
    """Get the fallback chain for a scenario, respecting user overrides."""
    override = settings.routing_fallback_overrides.get(scenario.value)
    if override:
        chain = []
        for model_id in override:
            mc = MODEL_MAP.get(model_id)
            if mc:
                chain.append(mc)
            else:
                logger.warning("Unknown model in fallback override: %s", model_id)
        if chain:
            return chain

    return list(DEFAULT_FALLBACK_CHAINS.get(scenario, [SONNET, HAIKU]))


def get_scenario_model(scenario: Scenario) -> ModelConfig:
    """Get the primary model for a scenario, respecting user overrides."""
    override = settings.routing_scenario_overrides.get(scenario.value)
    if override:
        mc = MODEL_MAP.get(override)
        if mc:
            return mc
        logger.warning("Unknown model in scenario override: %s", override)

    return DEFAULT_SCENARIO_MODELS.get(scenario, SONNET)


# --- Main routing function ---

def route_request(request: ChatCompletionRequest) -> RoutingDecision:
    """Analyze a request and decide which model to use.

    If the request specifies a concrete model (not "auto"), that model is used
    but still gets a fallback chain based on the detected scenario.
    """
    scenario, reason = classify_scenario(request)

    # Check if client requested a specific model
    requested_model = request.model.lower().strip()
    explicit = MODEL_MAP.get(requested_model)

    if explicit and requested_model not in ("auto", "smart", "router"):
        # Client wants a specific model — honor it, but provide fallback chain
        fallback = get_fallback_chain(scenario)
        # Remove the explicit model from fallback and put remaining models as fallback
        fallback = [m for m in fallback if m.model_id != explicit.model_id]
        logger.info(
            "Explicit model=%s, scenario=%s (%s), fallback=%s",
            explicit.model_id, scenario.value, reason,
            [m.name for m in fallback],
        )
        return RoutingDecision(
            scenario=scenario,
            model=explicit,
            reason=f"Explicit model request. Scenario detected: {reason}",
            fallback_chain=fallback,
        )

    # Smart routing: pick best model for the scenario
    model = get_scenario_model(scenario)
    fallback = get_fallback_chain(scenario)
    # Remove primary from fallback chain
    fallback = [m for m in fallback if m.model_id != model.model_id]

    logger.info(
        "Smart routing: scenario=%s → model=%s (%s), fallback=%s",
        scenario.value, model.name, reason,
        [m.name for m in fallback],
    )

    return RoutingDecision(
        scenario=scenario,
        model=model,
        reason=reason,
        fallback_chain=fallback,
    )
