"""Exhaustive audit of Phases 1-6 Notion requirements."""

import os
import sys
import json

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import notion_client_wrapper as notion_api

logger = get_logger(__name__)

# Full Phase 1-6 Requirement Map
PHASE_1_6_REQUIREMENTS = {
    "Character": [
        "Name", "Current HP", "Current Coins", "Gold", "TDEE", "Death Count", "Respawn",
        "STR XP", "INT XP", "WIS XP", "VIT XP", "CHA XP",
        "STR Level", "INT Level", "WIS Level", "VIT Level", "CHA Level",
        "Player Level", "Total XP", "Current Rank", "Avatar URL", "Radar Chart URL", "Pity Counter"
    ],
    "Activity Log": [
        "Type", "Domain", "Character", 
        "EXP + (Habit)", "EXP + (Goal)", "EXP + (Tasks)", "EXP + (Financial)", "EXP + (Workout)", "EXP + (Nutrition)", "EXP + (Achievement)", "EXP + (Quest)",
        "HP - (Bad Habit)", "HP + (Hotel)", "Coins + (Goal)", "Coins - (Market)", "Occurred At"
    ],
    "Good Habit": ["Domain", "XP Reward", "Streak Tracker", "Active"],
    "Bad Habit": ["Domain", "HP Penalty", "Active"],
    "Streak Tracker": ["Habit", "Current Streak", "Multiplier", "Current Tier"],
    "Treasury": ["Month", "Income", "Total Expenses", "Gold Earned", "WIS XP"],
    "Set Log": ["Weight", "Reps", "RPE", "Progressive Delta", "Session XP", "Exercise", "Session"],
    "Meal Log": ["Date", "Protein", "Carbs", "Fat", "Character"],
    "Settings": ["Name", "Value"],
    "Quests": [
        "Quest Title", "Narrative", "Domain", "Difficulty", "Status", 
        "Base XP", "Applied Multiplier", "Effective XP", "Gold Reward", "Source", "Due Date", "Character"
    ],
    "Achievements": ["Badge Name", "Description", "Condition Key", "XP Bonus", "Domain", "Icon URL"],
    "Player Achievements": ["Achievement", "Character", "Date Unlocked", "Notified"],
    "Loot Box Inventory": ["Reward Name", "Rarity", "Coins Awarded", "Gold Cost", "Claimed", "Date", "Character"]
}

def final_audit():
    db_ids_path = os.path.join(os.path.dirname(_tools_dir), "db_ids.json")
    with open(db_ids_path, "r") as f:
        db_ids = json.load(f)

    client = notion_api.get_client()
    errors = []
    
    print(f"{'DATABASE':<25} | {'RESULT':<10} | {'MISSING PROPERTIES'}")
    print("-" * 120)

    for db_name, required_props in PHASE_1_6_REQUIREMENTS.items():
        db_id = db_ids.get(db_name)
        if not db_id:
            print(f"{db_name:<25} | MISSING ID | Database not in db_ids.json")
            errors.append(f"Database ID missing: {db_name}")
            continue

        try:
            live_props = notion_api.get_database_properties(client, db_id)
            missing = [p for p in required_props if p not in live_props]
            
            if not missing:
                print(f"{db_name:<25} | PASS       | All {len(required_props)} properties verified.")
            else:
                print(f"{db_name:<25} | FAIL       | {', '.join(missing)}")
                errors.append(f"GAP in {db_name}: {missing}")

        except Exception as e:
            print(f"{db_name:<25} | ERROR      | {str(e)}")
            errors.append(f"ERROR querying {db_name}: {e}")

    print("\n" + "="*120)
    if not errors:
        print("PHASES 1-6 AUDIT: COMPLETE SUCCESS. Everything is wired correctly.")
    else:
        print(f"PHASES 1-6 AUDIT: FAILED. {len(errors)} gaps detected.")
        for err in errors:
            print(f"- {err}")
    print("="*120)

if __name__ == "__main__":
    final_audit()
