"""
Centralized configuration for the RPG-Gamified Life Tracker.
Includes game balance constants with hardcoded fallbacks and a Notion Settings DB reader.
"""
from .logger import get_logger

logger = get_logger(__name__)

# --- DEFAULTS (overridable via Notion Settings DB) ---

# Leveling
LEVEL_BASE_XP = 1000          # B in XP formula
LEVEL_EXPONENT = 1.8          # E in XP formula
LEVEL_LINEAR_MOD = 200        # L in XP formula

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
HP_DEATH_THRESHOLD = 0        # HP <= this triggers death
HP_OVERDRAFT_PENALTY = -100   # Weekly penalty if coins < 0
OVERDRAFT_CHECK_FREQUENCY = "weekly"  # weekly / biweekly / disabled

# Streaks
STREAK_TIERS = {3: 1.1, 7: 1.25, 14: 1.5, 30: 2.0, 60: 2.5, 100: 3.0}
STREAK_DECAY_RATE = 0.05

# Hotels
HOTEL_TIERS = {
    "Budget":   {"price": 100, "hp_recovery": 50},
    "Ordinary": {"price": 200, "hp_recovery": 150},
    "Premium":  {"price": 300, "hp_recovery": 500},
}

# Black Market
CHECKIN_RECOVERY_PRICE = 50   # coins to buy back a missed check-in

# Financial
GOLD_CONVERSION_RATE = 10
BUDGET_BREACH_XP_PENALTY = -50
WIS_XP_PER_GOLD = 5

# Fitness
RPE_XP_WEIGHT = True
OVERLOAD_WINDOW_DAYS = 14

# Nutrition
DEFAULT_TDEE = 2200
MACRO_TOLERANCE_PCT = 10
NUTRITION_STREAK_MULTIPLIER = 1.15

# Loot Box
LOOT_WEIGHTS = {"Common": 70, "Rare": 20, "Epic": 8, "Legendary": 2}
LOOT_COST = 100
PITY_TIMER_THRESHOLD = 50
LOOT_REWARDS = {"Common": 25, "Rare": 75, "Epic": 200, "Legendary": 1000}

# Task/Brain Dump Difficulty Rewards
DIFFICULTY_REWARDS = {
    "Level 1": {"xp": 5, "coins": 5},
    "Level 2": {"xp": 10, "coins": 10},
    "Level 3": {"xp": 15, "coins": 15},
}

# Good Habit Defaults
DEFAULT_HABIT_XP = 5
DEFAULT_BAD_HABIT_HP = -10

# OpenAI
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MONTHLY_COST_CAP_USD = 1.00
OPENAI_MAX_TOKENS = 1500

# Quest Difficulty Rewards
QUEST_DIFFICULTY_REWARDS = {
    "Easy":   {"xp": 25,  "gold": 5},
    "Medium": {"xp": 50,  "gold": 10},
    "Hard":   {"xp": 100, "gold": 25},
    "Epic":   {"xp": 200, "gold": 50},
}

# Class-to-Stat Mapping
CLASS_STAT_MAP = {
    "Warrior": "STR",
    "Mage": "INT",
    "Rogue": "CHA",
    "Paladin": "VIT",
    "Ranger": "WIS",
}

# Ranks
RANK_THRESHOLDS = {
    0: "Peasant", 1000: "Squire", 5000: "Knight", 15000: "Champion",
    40000: "Hero", 100000: "Legend", 250000: "Mythic",
}

# Mood Categories
MOOD_TYPES = ["Anxiety", "Joy", "Regret", "Sadness", "Boredom", "Surprise", "Shame"]

# --- Settings DB Reader ---
def load_settings_from_notion(notion_client, settings_db_id):
    """
    Reads user overrides from Notion Settings DB.
    Returns merged config.
    TODO: Implementation when notion_client is ready.
    """
    logger.info(f"Loading settings from Notion DB: {settings_db_id}")
    # Placeholder for now, returning defaults
    return {k: v for k, v in globals().items() if k.isupper() and not k.startswith('_')}

def get_config(notion_client=None, settings_db_id=None):
    """
    Main entry point for other tools to get configuration.
    If notion_client and settings_db_id are provided, it attempts to load overrides.
    """
    if notion_client and settings_db_id:
        try:
            return load_settings_from_notion(notion_client, settings_db_id)
        except Exception as e:
            logger.warning(f"Failed to load settings from Notion, using defaults: {e}")
    
    # Return all uppercase global variables as the default config
    return {k: v for k, v in globals().items() if k.isupper() and not k.startswith('_')}
