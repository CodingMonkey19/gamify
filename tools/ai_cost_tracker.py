"""
AI Cost Tracker — Shared budget enforcement for all OpenAI API calls.
Tracks cumulative monthly spend in Settings DB, enforces configurable cap.

Usage: Imported by quest_generator.py and coaching_engine.py (not standalone CLI).
"""
import hashlib

from .config import OPENAI_MONTHLY_COST_CAP_USD
from .logger import get_logger

logger = get_logger(__name__)

# USD per 1M tokens
MODEL_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

SETTINGS_DB_ID = "49bc6e3d-d39d-45f4-968f-756f779ed819"


def _get_notion_client():
    """Lazy import of notion_client to avoid circular imports."""
    try:
        from .notion_client import notion_client
        return notion_client
    except ImportError:
        logger.warning("notion_client not available — Notion calls will be skipped")
        return None


def estimate_cost(input_tokens: int, output_tokens: int, model: str = "gpt-4o-mini") -> float:
    """
    Pure math cost estimate.
    Returns USD amount based on token counts and model pricing.
    Falls back to gpt-4o-mini pricing if model is unknown.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        logger.warning(f"Unknown model '{model}', falling back to gpt-4o-mini pricing")
        pricing = MODEL_PRICING["gpt-4o-mini"]

    input_price = pricing["input"]
    output_price = pricing["output"]
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def get_monthly_spend() -> float:
    """
    Read AI_MONTHLY_SPEND from Settings DB via notion_client.
    Returns 0.0 if not found, not parseable, or on error.
    """
    client = _get_notion_client()
    if client is None:
        return 0.0

    try:
        response = client.databases.query(
            database_id=SETTINGS_DB_ID,
            filter={
                "property": "Name",
                "title": {"equals": "AI_MONTHLY_SPEND"},
            },
        )

        results = response.get("results", [])
        if not results:
            logger.info("AI_MONTHLY_SPEND row not found in Settings DB, returning 0.0")
            return 0.0

        page = results[0]
        value_prop = page["properties"]["Value"]["rich_text"]
        if not value_prop:
            return 0.0

        raw = value_prop[0]["plain_text"]
        return float(raw)

    except Exception as e:
        logger.error(f"Failed to read AI_MONTHLY_SPEND: {e}")
        return 0.0


def _write_monthly_spend(page_id: str, amount: float) -> None:
    """
    Write the updated spend amount back to the Settings DB page.
    Updates the 'Value' rich_text property with the new amount as string.
    """
    client = _get_notion_client()
    if client is None:
        logger.warning("notion_client not available — cannot write spend")
        return

    client.pages.update(
        page_id=page_id,
        properties={
            "Value": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": f"{amount:.6f}"},
                    }
                ]
            }
        },
    )


def check_budget(
    estimated_input_tokens: int,
    max_output_tokens: int,
    model: str = "gpt-4o-mini",
) -> bool:
    """
    Pre-flight budget check.
    Returns True if projected spend + current spend <= monthly cap.
    Logs a warning when rejecting.
    """
    worst_case = estimate_cost(estimated_input_tokens, max_output_tokens, model)
    current_spend = get_monthly_spend()
    cap = OPENAI_MONTHLY_COST_CAP_USD

    if current_spend + worst_case <= cap:
        logger.info(
            f"Budget check passed: current ${current_spend:.4f} + "
            f"worst-case ${worst_case:.6f} <= cap ${cap:.2f}"
        )
        return True

    logger.warning(
        f"Budget check REJECTED: current ${current_spend:.4f} + "
        f"worst-case ${worst_case:.6f} = ${current_spend + worst_case:.4f} "
        f"> cap ${cap:.2f}"
    )
    return False


def record_spend(usage: dict, model: str = "gpt-4o-mini", prompt_hash: str = None) -> float:
    """
    Record actual API spend after a successful call.
    - Calculates cost from usage['prompt_tokens'] and usage['completion_tokens']
    - Reads current spend, adds new cost, writes back to Settings DB
    - Logs prompt_hash for FR-023 traceability
    - Returns the cost of this individual call
    """
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost = estimate_cost(prompt_tokens, completion_tokens, model)

    hash_str = prompt_hash or "n/a"
    logger.info(
        f"API call: model={model}, prompt_tokens={prompt_tokens}, "
        f"completion_tokens={completion_tokens}, cost=${cost:.6f}, "
        f"prompt_hash={hash_str}"
    )

    client = _get_notion_client()
    if client is None:
        logger.warning("notion_client not available — spend not persisted")
        return cost

    try:
        response = client.databases.query(
            database_id=SETTINGS_DB_ID,
            filter={
                "property": "Name",
                "title": {"equals": "AI_MONTHLY_SPEND"},
            },
        )

        results = response.get("results", [])
        if not results:
            logger.error("AI_MONTHLY_SPEND row not found — cannot record spend")
            return cost

        page = results[0]
        page_id = page["id"]

        # Read current value
        value_prop = page["properties"]["Value"]["rich_text"]
        current = 0.0
        if value_prop:
            current = float(value_prop[0]["plain_text"])

        new_total = current + cost
        _write_monthly_spend(page_id, new_total)

        logger.info(f"Monthly spend updated: ${current:.6f} -> ${new_total:.6f}")

    except Exception as e:
        logger.error(f"Failed to record spend: {e}")

    return cost
