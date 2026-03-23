"""Seed reference data into the Phase 1 Notion workspace."""

import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import config
from logger import get_logger
import notion_client_wrapper as notion_api
from create_databases import load_db_ids


logger = get_logger(__name__)


GOOD_HABITS = [
    {"name": "Exercise", "stat": "STR", "xp": 5, "frequency": "Daily"},
    {"name": "Read 30 Minutes", "stat": "INT", "xp": 5, "frequency": "Daily"},
    {"name": "Track Expenses", "stat": "WIS", "xp": 5, "frequency": "Daily"},
    {"name": "Eat Clean", "stat": "VIT", "xp": 5, "frequency": "Daily"},
    {"name": "Social Interaction", "stat": "CHA", "xp": 5, "frequency": "Daily"},
]

BAD_HABITS = [
    {"name": "Scrolling", "stat": "INT", "hp_penalty": -10, "severity": "Medium"},
    {"name": "Smoking", "stat": "VIT", "hp_penalty": -25, "severity": "High"},
    {"name": "Drinking", "stat": "WIS", "hp_penalty": -15, "severity": "Medium"},
]

HOTEL_SEED = [
    {"name": "Budget Rest", "tier": "Budget", "price": 100, "hp_recovery": 50},
    {"name": "Ordinary Rest", "tier": "Ordinary", "price": 200, "hp_recovery": 150},
    {"name": "Premium Rest", "tier": "Premium", "price": 300, "hp_recovery": 500},
]

DIFFICULTY_LEVELS = [
    {"name": "Level 1", "xp": 5, "coins": 5},
    {"name": "Level 2", "xp": 10, "coins": 10},
    {"name": "Level 3", "xp": 15, "coins": 15},
]

MOOD_SEED = [
    {"name": "Anxiety"},
    {"name": "Joy"},
    {"name": "Regret"},
    {"name": "Sadness"},
    {"name": "Boredom"},
    {"name": "Surprise"},
    {"name": "Shame"},
]

SKILLS = [
    {"name": "Strength Training", "stat": "STR"},
    {"name": "Learning", "stat": "INT"},
    {"name": "Finance", "stat": "WIS"},
    {"name": "Nutrition", "stat": "VIT"},
    {"name": "Social Skills", "stat": "CHA"},
    {"name": "Creativity", "stat": "CHA"},
    {"name": "Recovery", "stat": "VIT"},
]

DEFAULT_CHARACTER = {"name": "Hero", "hp": 1000, "coins": 0, "gold": 0, "level": 1}
OVERDRAFT_PENALTY_SEED = [
    {
        "name": "Default Overdraft Penalty",
        "hp_delta": -100,
        "hp_penalty": 100,
        "frequency": "Weekly",
        "reason": "Default overdraft damage",
        "active": True,
    }
]

VISION_BOARD_CATEGORIES = [
    {"name": "Health"},
    {"name": "Career"},
    {"name": "Finance"},
    {"name": "Relationships"},
    {"name": "Adventure"},
    {"name": "Learning"},
    {"name": "Lifestyle"},
    {"name": "Legacy"},
]

BUDGET_CATEGORIES = [
    {"name": "Housing", "budget": 1200, "type": "Need"},
    {"name": "Food", "budget": 500, "type": "Need"},
    {"name": "Transportation", "budget": 250, "type": "Need"},
    {"name": "Utilities", "budget": 200, "type": "Need"},
    {"name": "Entertainment", "budget": 150, "type": "Want"},
    {"name": "Savings", "budget": 400, "type": "Saving"},
    {"name": "Debt", "budget": 300, "type": "Debt"},
    {"name": "Giving", "budget": 100, "type": "Want"},
]

EXERCISES = [
    {"name": "Push-up", "body_part": "Chest", "equipment": "Bodyweight", "stat": "STR"},
    {"name": "Pull-up", "body_part": "Back", "equipment": "Bodyweight", "stat": "STR"},
    {"name": "Squat", "body_part": "Legs", "equipment": "Bodyweight", "stat": "STR"},
    {"name": "Barbell Squat", "body_part": "Legs", "equipment": "Barbell", "stat": "STR"},
    {"name": "Deadlift", "body_part": "Back", "equipment": "Barbell", "stat": "STR"},
    {"name": "Bench Press", "body_part": "Chest", "equipment": "Barbell", "stat": "STR"},
    {"name": "Overhead Press", "body_part": "Shoulders", "equipment": "Barbell", "stat": "STR"},
    {"name": "Barbell Row", "body_part": "Back", "equipment": "Barbell", "stat": "STR"},
    {"name": "Dumbbell Row", "body_part": "Back", "equipment": "Dumbbell", "stat": "STR"},
    {"name": "Walking Lunge", "body_part": "Legs", "equipment": "Dumbbell", "stat": "STR"},
    {"name": "Romanian Deadlift", "body_part": "Legs", "equipment": "Barbell", "stat": "STR"},
    {"name": "Lat Pulldown", "body_part": "Back", "equipment": "Machine", "stat": "STR"},
    {"name": "Leg Press", "body_part": "Legs", "equipment": "Machine", "stat": "STR"},
    {"name": "Leg Curl", "body_part": "Legs", "equipment": "Machine", "stat": "STR"},
    {"name": "Leg Extension", "body_part": "Legs", "equipment": "Machine", "stat": "STR"},
    {"name": "Cable Fly", "body_part": "Chest", "equipment": "Cable", "stat": "STR"},
    {"name": "Face Pull", "body_part": "Shoulders", "equipment": "Cable", "stat": "STR"},
    {"name": "Bicep Curl", "body_part": "Arms", "equipment": "Dumbbell", "stat": "STR"},
    {"name": "Tricep Pushdown", "body_part": "Arms", "equipment": "Cable", "stat": "STR"},
    {"name": "Plank", "body_part": "Core", "equipment": "Bodyweight", "stat": "VIT"},
    {"name": "Hanging Leg Raise", "body_part": "Core", "equipment": "Bodyweight", "stat": "VIT"},
    {"name": "Burpee", "body_part": "Full Body", "equipment": "Bodyweight", "stat": "VIT"},
    {"name": "Jump Rope", "body_part": "Cardio", "equipment": "Cardio", "stat": "VIT"},
    {"name": "Rowing Machine", "body_part": "Cardio", "equipment": "Machine", "stat": "VIT"},
    {"name": "Bike Sprint", "body_part": "Cardio", "equipment": "Cardio", "stat": "VIT"},
    {"name": "Farmer Carry", "body_part": "Full Body", "equipment": "Dumbbell", "stat": "STR"},
    {"name": "Kettlebell Swing", "body_part": "Full Body", "equipment": "Kettlebell", "stat": "STR"},
    {"name": "Goblet Squat", "body_part": "Legs", "equipment": "Kettlebell", "stat": "STR"},
]

INGREDIENTS = [
    {"name": "Chicken Breast", "calories": 165, "protein": 31, "carbs": 0, "fat": 3.6, "unit": "100 g"},
    {"name": "Salmon", "calories": 208, "protein": 20, "carbs": 0, "fat": 13, "unit": "100 g"},
    {"name": "Lean Beef", "calories": 217, "protein": 26, "carbs": 0, "fat": 12, "unit": "100 g"},
    {"name": "Egg", "calories": 72, "protein": 6, "carbs": 0.4, "fat": 5, "unit": "1 egg"},
    {"name": "Egg White", "calories": 17, "protein": 3.6, "carbs": 0.2, "fat": 0.1, "unit": "1 white"},
    {"name": "Greek Yogurt", "calories": 97, "protein": 10, "carbs": 3.6, "fat": 5, "unit": "100 g"},
    {"name": "Cottage Cheese", "calories": 98, "protein": 11, "carbs": 3.4, "fat": 4.3, "unit": "100 g"},
    {"name": "Milk", "calories": 42, "protein": 3.4, "carbs": 5, "fat": 1, "unit": "100 ml"},
    {"name": "Oats", "calories": 389, "protein": 17, "carbs": 66, "fat": 7, "unit": "100 g"},
    {"name": "Rice", "calories": 130, "protein": 2.4, "carbs": 28, "fat": 0.3, "unit": "100 g cooked"},
    {"name": "Pasta", "calories": 131, "protein": 5, "carbs": 25, "fat": 1.1, "unit": "100 g cooked"},
    {"name": "Potato", "calories": 77, "protein": 2, "carbs": 17, "fat": 0.1, "unit": "100 g"},
    {"name": "Sweet Potato", "calories": 86, "protein": 1.6, "carbs": 20, "fat": 0.1, "unit": "100 g"},
    {"name": "Quinoa", "calories": 120, "protein": 4.4, "carbs": 21, "fat": 1.9, "unit": "100 g cooked"},
    {"name": "Bread", "calories": 265, "protein": 9, "carbs": 49, "fat": 3.2, "unit": "100 g"},
    {"name": "Banana", "calories": 89, "protein": 1.1, "carbs": 23, "fat": 0.3, "unit": "100 g"},
    {"name": "Apple", "calories": 52, "protein": 0.3, "carbs": 14, "fat": 0.2, "unit": "100 g"},
    {"name": "Blueberries", "calories": 57, "protein": 0.7, "carbs": 14, "fat": 0.3, "unit": "100 g"},
    {"name": "Avocado", "calories": 160, "protein": 2, "carbs": 9, "fat": 15, "unit": "100 g"},
    {"name": "Almonds", "calories": 579, "protein": 21, "carbs": 22, "fat": 50, "unit": "100 g"},
    {"name": "Peanut Butter", "calories": 588, "protein": 25, "carbs": 20, "fat": 50, "unit": "100 g"},
    {"name": "Olive Oil", "calories": 884, "protein": 0, "carbs": 0, "fat": 100, "unit": "100 g"},
    {"name": "Broccoli", "calories": 34, "protein": 2.8, "carbs": 7, "fat": 0.4, "unit": "100 g"},
    {"name": "Spinach", "calories": 23, "protein": 2.9, "carbs": 3.6, "fat": 0.4, "unit": "100 g"},
    {"name": "Carrot", "calories": 41, "protein": 0.9, "carbs": 10, "fat": 0.2, "unit": "100 g"},
    {"name": "Cucumber", "calories": 15, "protein": 0.7, "carbs": 3.6, "fat": 0.1, "unit": "100 g"},
    {"name": "Tomato", "calories": 18, "protein": 0.9, "carbs": 3.9, "fat": 0.2, "unit": "100 g"},
    {"name": "Bell Pepper", "calories": 31, "protein": 1, "carbs": 6, "fat": 0.3, "unit": "100 g"},
    {"name": "Onion", "calories": 40, "protein": 1.1, "carbs": 9.3, "fat": 0.1, "unit": "100 g"},
    {"name": "Garlic", "calories": 149, "protein": 6.4, "carbs": 33, "fat": 0.5, "unit": "100 g"},
    {"name": "Lentils", "calories": 116, "protein": 9, "carbs": 20, "fat": 0.4, "unit": "100 g cooked"},
    {"name": "Black Beans", "calories": 132, "protein": 8.9, "carbs": 24, "fat": 0.5, "unit": "100 g cooked"},
    {"name": "Chickpeas", "calories": 164, "protein": 8.9, "carbs": 27, "fat": 2.6, "unit": "100 g cooked"},
    {"name": "Tofu", "calories": 76, "protein": 8, "carbs": 1.9, "fat": 4.8, "unit": "100 g"},
    {"name": "Tempeh", "calories": 193, "protein": 20, "carbs": 8, "fat": 11, "unit": "100 g"},
    {"name": "Cheddar Cheese", "calories": 403, "protein": 25, "carbs": 1.3, "fat": 33, "unit": "100 g"},
    {"name": "Tuna", "calories": 132, "protein": 29, "carbs": 0, "fat": 1, "unit": "100 g"},
    {"name": "Shrimp", "calories": 99, "protein": 24, "carbs": 0.2, "fat": 0.3, "unit": "100 g"},
    {"name": "Turkey Breast", "calories": 135, "protein": 30, "carbs": 0, "fat": 1, "unit": "100 g"},
    {"name": "Brown Rice", "calories": 123, "protein": 2.7, "carbs": 26, "fat": 1, "unit": "100 g cooked"},
]

ACHIEVEMENTS = [
    {"name": "First Check-in", "category": "Habits", "threshold": 1, "reward": 10},
    {"name": "Habit Apprentice", "category": "Habits", "threshold": 10, "reward": 25},
    {"name": "Habit Adept", "category": "Habits", "threshold": 25, "reward": 50},
    {"name": "Habit Master", "category": "Habits", "threshold": 50, "reward": 100},
    {"name": "Seven-Day Fire", "category": "Habits", "threshold": 7, "reward": 35},
    {"name": "Fourteen-Day Fire", "category": "Habits", "threshold": 14, "reward": 70},
    {"name": "Thirty-Day Fire", "category": "Habits", "threshold": 30, "reward": 150},
    {"name": "Hundred-Day Fire", "category": "Habits", "threshold": 100, "reward": 500},
    {"name": "Reach Level 2", "category": "XP", "threshold": 2, "reward": 20},
    {"name": "Reach Level 5", "category": "XP", "threshold": 5, "reward": 50},
    {"name": "Reach Level 10", "category": "XP", "threshold": 10, "reward": 120},
    {"name": "Reach Level 20", "category": "XP", "threshold": 20, "reward": 250},
    {"name": "Reach Level 30", "category": "XP", "threshold": 30, "reward": 400},
    {"name": "Reach Level 50", "category": "XP", "threshold": 50, "reward": 800},
    {"name": "Gain 1,000 XP", "category": "XP", "threshold": 1000, "reward": 40},
    {"name": "Gain 10,000 XP", "category": "XP", "threshold": 10000, "reward": 200},
    {"name": "Earn 100 Coins", "category": "Finance", "threshold": 100, "reward": 25},
    {"name": "Earn 500 Coins", "category": "Finance", "threshold": 500, "reward": 60},
    {"name": "Earn 1,000 Coins", "category": "Finance", "threshold": 1000, "reward": 125},
    {"name": "Save 100 Gold", "category": "Finance", "threshold": 100, "reward": 250},
    {"name": "Track 10 Expenses", "category": "Finance", "threshold": 10, "reward": 40},
    {"name": "Track 50 Expenses", "category": "Finance", "threshold": 50, "reward": 120},
    {"name": "Complete First Workout", "category": "Fitness", "threshold": 1, "reward": 20},
    {"name": "Train 10 Times", "category": "Fitness", "threshold": 10, "reward": 50},
    {"name": "Train 25 Times", "category": "Fitness", "threshold": 25, "reward": 100},
    {"name": "Train 50 Times", "category": "Fitness", "threshold": 50, "reward": 180},
    {"name": "Hit 10,000 Volume", "category": "Fitness", "threshold": 10000, "reward": 75},
    {"name": "Hit 50,000 Volume", "category": "Fitness", "threshold": 50000, "reward": 250},
    {"name": "Log First Meal", "category": "Nutrition", "threshold": 1, "reward": 15},
    {"name": "Log 10 Meals", "category": "Nutrition", "threshold": 10, "reward": 40},
    {"name": "Log 25 Meals", "category": "Nutrition", "threshold": 25, "reward": 80},
    {"name": "Log 50 Meals", "category": "Nutrition", "threshold": 50, "reward": 150},
    {"name": "Hit Protein Goal 10 Times", "category": "Nutrition", "threshold": 10, "reward": 70},
    {"name": "Hit Protein Goal 25 Times", "category": "Nutrition", "threshold": 25, "reward": 160},
    {"name": "Social Starter", "category": "Social", "threshold": 1, "reward": 15},
    {"name": "Connector", "category": "Social", "threshold": 10, "reward": 45},
    {"name": "Community Builder", "category": "Social", "threshold": 25, "reward": 90},
    {"name": "Speaker", "category": "Social", "threshold": 50, "reward": 150},
    {"name": "Creator", "category": "Social", "threshold": 75, "reward": 220},
    {"name": "First Gold", "category": "Milestone", "threshold": 1, "reward": 25},
    {"name": "First Hotel Stay", "category": "Milestone", "threshold": 1, "reward": 35},
    {"name": "First Quest", "category": "Milestone", "threshold": 1, "reward": 35},
    {"name": "First Loot Box", "category": "Milestone", "threshold": 1, "reward": 50},
]


def title_value(value):
    return {"title": [{"type": "text", "text": {"content": value}}]}


def rich_text_value(value):
    return {"rich_text": [{"type": "text", "text": {"content": str(value)}}]}


def number_value(value):
    return {"number": value}


def select_value(value):
    return {"select": {"name": value}}


def checkbox_value(value):
    return {"checkbox": bool(value)}


def _settings_seed():
    cfg = config.get_config()
    keys = [
        ("LEVEL_BASE_XP", "number"),
        ("LEVEL_EXPONENT", "number"),
        ("LEVEL_LINEAR_MOD", "number"),
        ("PLAYER_TIMEZONE", "text"),
        ("STARTING_HP", "number"),
        ("HP_OVERDRAFT_PENALTY", "number"),
        ("DEFAULT_HABIT_XP", "number"),
        ("DEFAULT_BAD_HABIT_HP", "number"),
        ("LOOT_COST", "number"),
        ("PITY_TIMER_THRESHOLD", "number"),
        ("GOLD_CONVERSION_RATE", "number"),
        ("BUDGET_BREACH_XP_PENALTY", "number"),
        ("MONTHLY_INCOME", "number"),
        ("WIS_XP_PER_GOLD", "number"),
        ("RPE_XP_WEIGHT", "text"),
        ("OVERLOAD_WINDOW_DAYS", "number"),
        ("DEFAULT_TDEE", "number"),
        ("MACRO_TOLERANCE_PCT", "number"),
        ("NUTRITION_STREAK_MULTIPLIER", "number"),
        ("OPENAI_MONTHLY_COST_CAP_USD", "number"),
        ("OPENAI_MAX_TOKENS", "number"),
    ]
    return [
        {"name": key, "value": cfg[key], "type": value_type, "description": f"Default for {key}"}
        for key, value_type in keys
    ]


def _titles_from_rows(rows):
    return {notion_api.get_page_title(row) for row in rows if notion_api.get_page_title(row)}


def _good_habit_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Stat": select_value(row["stat"]),
        "Domain": select_value(row["stat"]),
        "XP Reward": number_value(row["xp"]),
        "EXP Earn": number_value(row["xp"]),
        "Frequency": select_value(row["frequency"]),
        "Active": checkbox_value(True),
    }


def _bad_habit_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Stat": select_value(row["stat"]),
        "Domain": select_value(row["stat"]),
        "HP Penalty": number_value(row["hp_penalty"]),
        "HP Damage": number_value(abs(row["hp_penalty"])),
        "Severity": select_value(row["severity"]),
        "Active": checkbox_value(True),
    }


def _hotel_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Tier": select_value(row["tier"]),
        "Price": number_value(row["price"]),
        "HP Recovery": number_value(row["hp_recovery"]),
    }


def _difficulty_properties(row):
    return {
        "Name": title_value(row["name"]),
        "XP Reward": number_value(row["xp"]),
        "Coin Reward": number_value(row["coins"]),
    }


def _mood_properties(row):
    return {"Name": title_value(row["name"]), "Intensity": number_value(0)}


def _skill_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Primary Stat": select_value(row["stat"]),
        "Stat": select_value(row["stat"]),
    }


def _character_properties(row):
    return {
        "Name": title_value(row["name"]),
        "HP": number_value(row["hp"]),
        "Current HP": number_value(row["hp"]),
        "Max HP": number_value(row["hp"]),
        "Coins": number_value(row["coins"]),
        "Current Coins": number_value(row["coins"]),
        "Gold": number_value(row["gold"]),
        "TDEE": number_value(config.DEFAULT_TDEE),
        "Level": number_value(row["level"]),
        "Player Level": number_value(row["level"]),
        "Total XP": number_value(0),
        "Death Count": number_value(0),
        "Respawn": checkbox_value(False),
        "Rank": select_value("Peasant"),
        "Current Rank": select_value("Peasant"),
        "Class": select_value("Warrior"),
        "STR XP": number_value(0),
        "STR Level": number_value(1),
        "INT XP": number_value(0),
        "INT Level": number_value(1),
        "WIS XP": number_value(0),
        "WIS Level": number_value(1),
        "VIT XP": number_value(0),
        "VIT Level": number_value(1),
        "CHA XP": number_value(0),
        "CHA Level": number_value(1),
    }


def _overdraft_penalty_properties(row):
    return {
        "Name": title_value(row["name"]),
        "HP Delta": number_value(row["hp_delta"]),
        "HP Penalty": number_value(row["hp_penalty"]),
        "Frequency": select_value(row["frequency"]),
        "Reason": rich_text_value(row["reason"]),
        "Active": checkbox_value(row["active"]),
    }


def _settings_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Value": rich_text_value(row["value"]),
        "Type": select_value(row["type"]),
        "Description": rich_text_value(row["description"]),
    }


def _vision_board_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Category": select_value(row["name"]),
        "Priority": select_value("P2"),
        "Completed": checkbox_value(False),
    }


def _budget_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Monthly Budget": number_value(row["budget"]),
        "Type": select_value(row["type"]),
    }


def _exercise_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Body Part": select_value(row["body_part"]),
        "Equipment": select_value(row["equipment"]),
        "Primary Stat": select_value(row["stat"]),
        "Base XP Modifier": number_value(row.get("base_xp_modifier", 1.0)),
    }


def _ingredient_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Calories": number_value(row["calories"]),
        "Protein": number_value(row["protein"]),
        "Carbs": number_value(row["carbs"]),
        "Fat": number_value(row["fat"]),
        "Unit": rich_text_value(row["unit"]),
    }


def _achievement_properties(row):
    return {
        "Name": title_value(row["name"]),
        "Category": select_value(row["category"]),
        "Threshold": number_value(row["threshold"]),
        "Reward Coins": number_value(row["reward"]),
        "Description": rich_text_value(f"{row['category']} achievement"),
    }


SEED_PLANS = {
    "Good Habit": (GOOD_HABITS, _good_habit_properties),
    "Bad Habit": (BAD_HABITS, _bad_habit_properties),
    "Hotel": (HOTEL_SEED, _hotel_properties),
    "To-do Difficulty": (DIFFICULTY_LEVELS, _difficulty_properties),
    "Mood": (MOOD_SEED, _mood_properties),
    "Skill/Area": (SKILLS, _skill_properties),
    "Character": ([DEFAULT_CHARACTER], _character_properties),
    "Overdraft Penalty": (OVERDRAFT_PENALTY_SEED, _overdraft_penalty_properties),
    "Settings": (_settings_seed(), _settings_properties),
    "Vision Board Items": (VISION_BOARD_CATEGORIES, _vision_board_properties),
    "Budget Categories": (BUDGET_CATEGORIES, _budget_properties),
    "Exercise Dictionary": (EXERCISES, _exercise_properties),
    "Ingredients Library": (INGREDIENTS, _ingredient_properties),
    "Achievements": (ACHIEVEMENTS, _achievement_properties),
}


def seed_all(db_ids, client):
    """Seed all configured datasets without overwriting existing rows."""
    missing = [db_name for db_name in SEED_PLANS if db_name not in db_ids]
    if missing:
        raise ValueError(f"Missing required databases: {', '.join(sorted(missing))}")

    result = {"seeded": {}, "skipped": {}, "total_created": 0, "total_skipped": 0}

    for db_name, (rows, builder) in SEED_PLANS.items():
        existing_rows = notion_api.query_database(client, db_ids[db_name])
        existing_titles = _titles_from_rows(existing_rows)
        created = 0
        skipped = 0

        for row in rows:
            if row["name"] in existing_titles:
                skipped += 1
                continue

            notion_api.create_page(client, db_ids[db_name], builder(row))
            created += 1

        result["seeded"][db_name] = created
        result["skipped"][db_name] = skipped
        result["total_created"] += created
        result["total_skipped"] += skipped

    return result


def main():
    client = notion_api.get_client()
    db_ids = load_db_ids()
    result = seed_all(db_ids=db_ids, client=client)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
