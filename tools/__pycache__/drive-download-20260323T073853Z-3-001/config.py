"""Centralized game configuration with optional Notion-backed overrides."""

import json
import os
import sys

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import notion_client_wrapper as notion_api

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# DEFAULTS — all game balance values (overridable via Notion Settings DB)
# ---------------------------------------------------------------------------

# Leveling formula: XP_required(n) = LEVEL_BASE_XP * n^LEVEL_EXPONENT + LEVEL_LINEAR_MOD * n
LEVEL_BASE_XP = 1000
LEVEL_EXPONENT = 1.8
LEVEL_LINEAR_MOD = 200

# Stats
STATS = ["STR", "INT", "WIS", "VIT", "CHA"]
STAT_DOMAIN_MAP = {
    "STR": ["gym", "organized"],
    "INT": ["learning"],
    "WIS": ["finance"],
    "VIT": ["nutrition", "habits", "health"],
    "CHA": ["social", "content", "creativity", "writing"],
}

# HP System
STARTING_HP = 1000
HP_DEATH_THRESHOLD = 0
HP_OVERDRAFT_PENALTY = -100
OVERDRAFT_CHECK_FREQUENCY = "weekly"

# Streaks — {min_days: multiplier}
STREAK_TIERS = {3: 1.1, 7: 1.25, 14: 1.5, 30: 2.0, 60: 2.5, 100: 3.0}
STREAK_DECAY_RATE = 0.05  # not used as XP penalty; streak just resets
PLAYER_TIMEZONE = "UTC"

# Hotels — {tier_name: {price_coins, hp_recovery}}
HOTEL_TIERS = {
    "Budget":   {"price": 100, "hp_recovery": 50},
    "Ordinary": {"price": 200, "hp_recovery": 150},
    "Premium":  {"price": 300, "hp_recovery": 500},
}

# Black Market
CHECKIN_RECOVERY_PRICE = 50

# Financial engine
MONTHLY_INCOME = 0  # override in Settings DB (player-specific)
GOLD_CONVERSION_RATE = 10
BUDGET_BREACH_XP_PENALTY = -50
WIS_XP_PER_GOLD = 5

# Fitness engine
RPE_XP_WEIGHT = True
OVERLOAD_WINDOW_DAYS = 14

# Nutrition engine
DEFAULT_TDEE = 2200
MACRO_TOLERANCE_PCT = 10
NUTRITION_STREAK_MULTIPLIER = 1.15

# Loot Box
LOOT_WEIGHTS = {"Common": 70, "Rare": 20, "Epic": 8, "Legendary": 2}
LOOT_COST = 100
PITY_TIMER_THRESHOLD = 50
LOOT_REWARDS = {"Common": 25, "Rare": 75, "Epic": 200, "Legendary": 1000}

# Brain Dump / Task difficulty rewards
DIFFICULTY_REWARDS = {
    "Level 1": {"xp": 5,  "coins": 5},
    "Level 2": {"xp": 10, "coins": 10},
    "Level 3": {"xp": 15, "coins": 15},
}

# Quest difficulty rewards
QUEST_DIFFICULTY_REWARDS = {
    "Easy":   {"xp": 25,  "gold": 5},
    "Medium": {"xp": 50,  "gold": 10},
    "Hard":   {"xp": 100, "gold": 25},
    "Epic":   {"xp": 200, "gold": 50},
}

# Habit defaults
DEFAULT_HABIT_XP = 5
DEFAULT_BAD_HABIT_HP = -10

# OpenAI
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MONTHLY_COST_CAP_USD = 1.00
OPENAI_MAX_TOKENS = 1500

# Rank thresholds — {min_total_xp: rank_name}
RANK_THRESHOLDS = {
    0: "Peasant",
    1000: "Squire",
    5000: "Knight",
    15000: "Champion",
    40000: "Hero",
    100000: "Legend",
    250000: "Mythic",
}

# Mood categories
MOOD_TYPES = ["Anxiety", "Joy", "Regret", "Sadness", "Boredom", "Surprise", "Shame"]

# RPG Classes — each gets +10% bonus to its stat
CLASS_BONUSES = {
    "Warrior": "STR",
    "Mage":    "INT",
    "Rogue":   "CHA",
    "Paladin": "VIT",
    "Ranger":  "WIS",
}

# Automation
LOCK_TIMEOUT_MINUTES = 30

# ---------------------------------------------------------------------------
# Settings DB types — maps setting name → expected Python type for validation
# ---------------------------------------------------------------------------
_SETTING_TYPES = {
    "LEVEL_BASE_XP": int,
    "LEVEL_EXPONENT": float,
    "LEVEL_LINEAR_MOD": int,
    "PLAYER_TIMEZONE": str,
    "STARTING_HP": int,
    "HP_OVERDRAFT_PENALTY": int,
    "DEFAULT_HABIT_XP": int,
    "DEFAULT_BAD_HABIT_HP": int,
    "LOOT_COST": int,
    "PITY_TIMER_THRESHOLD": int,
    "GOLD_CONVERSION_RATE": int,
    "BUDGET_BREACH_XP_PENALTY": int,
    "MONTHLY_INCOME": int,
    "WIS_XP_PER_GOLD": int,
    "RPE_XP_WEIGHT": bool,
    "DEFAULT_TDEE": int,
    "MACRO_TOLERANCE_PCT": float,
    "NUTRITION_STREAK_MULTIPLIER": float,
    "OVERLOAD_WINDOW_DAYS": int,
    "OPENAI_MONTHLY_COST_CAP_USD": float,
    "OPENAI_MAX_TOKENS": int,
    "LOCK_TIMEOUT_MINUTES": int,
}


def _load_dotenv():
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        return


def _parse_bool(raw_value, key="value"):
    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {key}: {raw_value}")


def _coerce_value(key, raw_value, defaults, prop_type=None):
    expected_type = _SETTING_TYPES.get(key)
    if expected_type is not None:
        if expected_type is bool:
            return _parse_bool(raw_value, key)
        return expected_type(raw_value)

    default_value = defaults.get(key)
    if prop_type == "json" or isinstance(default_value, (dict, list)):
        if isinstance(raw_value, str):
            return json.loads(raw_value)
        return raw_value

    if isinstance(default_value, bool):
        return _parse_bool(raw_value, key)
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        return int(raw_value)
    if isinstance(default_value, float):
        return float(raw_value)
    return raw_value


def _env_overrides(defaults):
    overrides = {}
    for key in defaults:
        if key not in os.environ:
            continue
        raw_value = os.environ[key]
        try:
            overrides[key] = _coerce_value(key, raw_value, defaults)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning(
                "Environment override for %s has invalid value %r. Using existing config value.",
                key,
                raw_value,
            )
    return overrides


def _load_notion_overrides(notion_client, settings_db_id, defaults):
    if not notion_client or not settings_db_id:
        return {}

    try:
        rows = notion_api.query_database(notion_client, settings_db_id)
    except Exception as e:
        logger.warning(f"Cannot read Settings DB ({settings_db_id}): {e}. Using defaults.")
        return {}

    overrides = {}
    for row in rows:
        props = row.get("properties", {})
        # Name is the title property
        name_prop = props.get("Name", {})
        title_content = name_prop.get("title", [])
        if not title_content:
            continue
        key = title_content[0].get("plain_text", "").strip()
        if not key or key not in defaults:
            continue

        # Value can be stored as Number or Rich text
        value_prop = props.get("Value", {})
        type_prop = props.get("Type", {})
        raw_value = None
        if value_prop.get("type") == "number":
            raw_value = value_prop.get("number")
        elif value_prop.get("type") == "rich_text":
            rt = value_prop.get("rich_text", [])
            if rt:
                raw_value = rt[0].get("plain_text", "").strip()

        if raw_value is None:
            continue

        prop_type = ""
        if type_prop.get("type") == "select":
            selected = type_prop.get("select") or {}
            prop_type = selected.get("name", "")

        # Type-coerce and validate
        expected_type = _SETTING_TYPES.get(key)
        try:
            raw_value = _coerce_value(key, raw_value, defaults, prop_type=prop_type)
        except (ValueError, TypeError, json.JSONDecodeError):
            expected_label = expected_type.__name__ if expected_type else prop_type or type(defaults[key]).__name__
            logger.warning(
                f"Settings DB: '{key}' has invalid value '{raw_value}' "
                f"(expected {expected_label}). Using default: {defaults[key]}"
            )
            continue

        overrides[key] = raw_value
        logger.info(f"Config override: {key} = {raw_value}")

    return overrides


def load_settings_from_notion(notion_client, settings_db_id):
    """
    Reads overrides from the Notion Settings DB.
    Each row: Name (title) = setting key, Value (number or text) = override value.
    Returns a merged config dict: Notion overrides take precedence over module defaults.
    Invalid values (wrong type) fall back to defaults with a warning logged.
    """
    defaults = _get_defaults()
    overrides = _load_notion_overrides(notion_client, settings_db_id, defaults)
    return {**defaults, **overrides}


def get_config(notion_client=None, settings_db_id=None):
    """
    Main entry point for all tools to get configuration.
    Pass notion_client + settings_db_id to load Notion overrides.
    Falls back to module defaults on any failure.
    """
    _load_dotenv()
    defaults = _get_defaults()
    merged = {**defaults, **_env_overrides(defaults)}
    if notion_client and settings_db_id:
        try:
            notion_overrides = _load_notion_overrides(notion_client, settings_db_id, defaults)
            return {**merged, **notion_overrides}
        except Exception as e:
            logger.warning(f"get_config: failed to load Notion settings: {e}. Using defaults.")
    return merged


def _get_defaults():
    """Returns a dict of all uppercase module-level constants."""
    import sys as _sys
    module = _sys.modules[__name__]
    return {
        k: getattr(module, k)
        for k in dir(module)
        if k.isupper() and not k.startswith("_")
    }
