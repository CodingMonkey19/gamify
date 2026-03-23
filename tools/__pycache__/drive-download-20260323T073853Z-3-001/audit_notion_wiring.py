"""Audit Notion wiring against Phase 1-4 specifications."""

import os
import sys
import json
from collections import OrderedDict

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import notion_client_wrapper as notion_api

logger = get_logger(__name__)

def audit_wiring():
    db_ids_path = os.path.join(os.path.dirname(_tools_dir), "db_ids.json")
    if not os.path.exists(db_ids_path):
        logger.error("db_ids.json not found.")
        return

    with open(db_ids_path, "r") as f:
        db_ids = json.load(f)

    client = notion_api.get_client()
    report = []
    
    # Define critical wiring requirements (Databases -> Properties)
    # This is a representative subset based on the Specs for Phase 1-4
    CRITICAL_WIRING = {
        "Character": ["Current HP", "Current Coins", "STR XP", "INT XP", "WIS XP", "VIT XP", "CHA XP", "STR Level", "Player Level", "Total XP", "Current Rank", "Death Count", "Respawn", "TDEE"],
        "Activity Log": ["Type", "Domain", "Character", "EXP + (Habit)", "EXP + (Goal)", "EXP + (Tasks)", "EXP + (Financial)", "EXP + (Workout)", "EXP + (Nutrition)", "HP - (Bad Habit)", "HP + (Hotel)", "Coins + (Goal)", "Coins - (Market)"],
        "Good Habit": ["Domain", "XP Reward", "Streak Tracker", "Active"],
        "Bad Habit": ["Domain", "HP Penalty", "Active"],
        "Streak Tracker": ["Habit", "Current Streak", "Multiplier", "Current Tier"],
        "Treasury": ["Month", "Income", "Total Expenses", "Gold Earned", "WIS XP"],
        "Set Log": ["Weight", "Reps", "RPE", "Progressive Delta", "Session XP", "Exercise", "Session"],
        "Meal Log": ["Date", "Protein", "Carbs", "Fat", "Character"],
        "Settings": ["Name", "Value"],
        "Workout Sessions": ["Session Date", "Character"],
        "Goal": ["Domain", "Status", "XP Reward", "Coin Reward"],
        "Brain Dump": ["Status", "Difficulty"]
    }

    print(f"{'DATABASE':<20} | {'STATUS':<10} | {'DETAILS'}")
    print("-" * 80)

    for db_name, required_props in CRITICAL_WIRING.items():
        db_id = db_ids.get(db_name)
        if not db_id:
            print(f"{db_name:<20} | {'MISSING':<10} | Database ID not in db_ids.json")
            report.append(f"FAIL: {db_name} is missing from db_ids.json")
            continue

        try:
            existing_props = notion_api.get_database_properties(client, db_id)
            
            missing = [p for p in required_props if p not in existing_props]
            
            if not missing:
                print(f"{db_name:<20} | {'OK':<10} | All {len(required_props)} critical properties present")
            else:
                print(f"{db_name:<20} | {'GAPS':<10} | Missing: {', '.join(missing)}")
                report.append(f"GAP: {db_name} is missing properties: {missing}")

            # Special check for relations (Wiring)
            if db_name == "Activity Log":
                char_rel = existing_props.get("Character", {})
                if char_rel.get("type") != "relation":
                    report.append(f"WIRING FAIL: Activity Log -> Character is not a relation")
            
            if db_name == "Streak Tracker":
                habit_rel = existing_props.get("Habit", {})
                if habit_rel.get("type") != "relation":
                    report.append(f"WIRING FAIL: Streak Tracker -> Habit is not a relation")

        except Exception as e:
            print(f"{db_name:<20} | {'ERROR':<10} | {str(e)}")
            report.append(f"ERROR: Could not audit {db_name}: {e}")

    print("\n" + "="*80)
    print("FINAL AUDIT SUMMARY")
    print("="*80)
    if not report:
        print("ALL CLEAR: All critical Phase 1-4 wiring is verified and present.")
    else:
        for line in report:
            print(f"- {line}")

if __name__ == "__main__":
    audit_wiring()
