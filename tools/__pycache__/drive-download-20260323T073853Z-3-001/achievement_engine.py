"""Achievement evaluation and granting logic."""

import argparse
import os
import sys
from datetime import date

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import config
import notion_client_wrapper as notion_api
import xp_engine

logger = get_logger(__name__)


def get_all_achievements(client=None, db_ids=None):
    """Query Achievements DB, return list of achievement dicts."""
    if client is None:
        client = notion_api.get_client()
    if db_ids is None:
        db_ids = notion_api.get_database_ids()
        
    rows = notion_api.query_database(client, db_ids["Achievements"])
    achievements = []
    for row in rows:
        props = row.get("properties", {})
        achievements.append({
            "id": row["id"],
            "name": props.get("Badge Name", {}).get("title", [{}])[0].get("plain_text", ""),
            "condition_key": props.get("Condition Key", {}).get("rich_text", [{}])[0].get("plain_text", ""),
            "xp_bonus": props.get("XP Bonus", {}).get("number", 0),
            "domain": props.get("Domain", {}).get("select", {}).get("name", "STR"),
            "icon_url": props.get("Icon URL", {}).get("url", "")
        })
    return achievements


def get_unlocked_achievements(character_id, client=None, db_ids=None):
    """Query Player Achievements DB for character, return set of achievement IDs."""
    if client is None:
        client = notion_api.get_client()
    if db_ids is None:
        db_ids = notion_api.get_database_ids()
        
    filter_obj = {
        "property": "Character",
        "relation": {"contains": character_id}
    }
    rows = notion_api.query_database(client, db_ids["Player Achievements"], filter_obj)
    unlocked_ids = set()
    for row in rows:
        rel = row.get("properties", {}).get("Achievement", {}).get("relation", [])
        if rel:
            unlocked_ids.add(rel[0]["id"])
    return unlocked_ids


# --- Condition Checkers ---

def check_first_workout(character_id, client, db_ids):
    """1+ workout session completed."""
    filter_obj = {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Status", "status": {"equals": "Done"}}
        ]
    }
    rows = notion_api.query_database(client, db_ids["Workout Sessions"], filter_obj)
    return len(rows) > 0


def check_first_budget(character_id, client, db_ids):
    """1+ monthly budget processed (Treasury row exists)."""
    # Assuming Treasury rows are linked to Character or just represent a month
    # Usually Treasury is a global log but if it's per character, it's easier.
    # If not linked, we check if there's any row.
    rows = notion_api.query_database(client, db_ids["Treasury"])
    return len(rows) > 0


def check_streak_3(character_id, client, db_ids):
    """Any habit streak >= 3 days."""
    filter_obj = {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Current Streak", "number": {"greater_than_or_equal_to": 3}}
        ]
    }
    rows = notion_api.query_database(client, db_ids["Streak Tracker"], filter_obj)
    return len(rows) > 0


def check_streak_7(character_id, client, db_ids):
    """Any habit streak >= 7 days."""
    filter_obj = {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Current Streak", "number": {"greater_than_or_equal_to": 7}}
        ]
    }
    rows = notion_api.query_database(client, db_ids["Streak Tracker"], filter_obj)
    return len(rows) > 0


def check_rank_squire(character_id, client, db_ids):
    """Reached Squire rank."""
    char_page = notion_api.get_page(client, character_id)
    rank = char_page.get("properties", {}).get("Current Rank", {}).get("select", {}).get("name", "")
    # Higher ranks also count? The spec says "Reached Squire rank". 
    # Usually accomplishments are inclusive of lower tiers.
    # But we'll just check if current rank is in [Squire, Knight, Champion, Hero, Legend, Mythic]
    ranks = ["Squire", "Knight", "Champion", "Hero", "Legend", "Mythic"]
    return rank in ranks


CONDITION_CHECKERS = {
    "first_workout": check_first_workout,
    "first_budget": check_first_budget,
    "streak_3": check_streak_3,
    "streak_7": check_streak_7,
    "rank_squire": check_rank_squire,
}


def check_condition(condition_key, character_id, client, db_ids):
    """Dispatch to CONDITION_CHECKERS map."""
    checker = CONDITION_CHECKERS.get(condition_key)
    if not checker:
        logger.warning(f"Unknown condition key: {condition_key}")
        return False
    try:
        return checker(character_id, client, db_ids)
    except Exception as e:
        logger.error(f"Error checking condition {condition_key} for {character_id}: {e}")
        return False


def check_all_achievements(character_id, client=None, db_ids=None, cfg=None, today=None):
    """Orchestrator: check all non-unlocked achievements, grant rewards."""
    if client is None:
        client = notion_api.get_client()
    if db_ids is None:
        db_ids = notion_api.get_database_ids()
    if cfg is None:
        cfg = config.get_config(client, db_ids.get("Settings"))
    if today is None:
        today = date.today()
        
    all_achievements = get_all_achievements(client, db_ids)
    unlocked_ids = get_unlocked_achievements(character_id, client, db_ids)
    
    newly_unlocked = []
    for ach in all_achievements:
        if ach["id"] in unlocked_ids:
            continue
            
        if check_condition(ach["condition_key"], character_id, client, db_ids):
            logger.info(f"Achievement unlocked for {character_id}: {ach['name']}")
            
            # Create Player Achievement record
            notion_api.create_page(client, db_ids["Player Achievements"], {
                "Achievement": {"relation": [{"id": ach["id"]}]},
                "Character": {"relation": [{"id": character_id}]},
                "Date Unlocked": {"date": {"start": today.isoformat()}}
            })
            
            # Create Activity Log entry
            notion_api.create_page(client, db_ids["Activity Log"], {
                "Name": {"title": [{"text": {"content": f"Unlocked: {ach['name']}"}}]},
                "Type": {"select": {"name": "ACHIEVEMENT"}},
                "Character": {"relation": [{"id": character_id}]},
                "Domain": {"select": {"name": ach["domain"]}},
                "XP Earned": {"number": ach["xp_bonus"]},
                "Occurred At": {"date": {"start": today.isoformat()}},
                "Notes": {"rich_text": [{"text": {"content": f"Achievement: {ach['condition_key']}"}}]}
            })
            
            newly_unlocked.append(ach)
            
    if newly_unlocked:
        xp_engine.update_character_stats(character_id, client, db_ids, cfg)
        
    return {
        "checked": len(all_achievements),
        "newly_unlocked": [a["name"] for a in newly_unlocked],
        "total_xp_granted": sum(a["xp_bonus"] for a in newly_unlocked)
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate and grant achievements.")
    parser.add_argument("--character-id", required=True, help="Notion Page ID of the character")
    args = parser.parse_args()

    result = check_all_achievements(args.character_id)
    print(f"Checked {result['checked']} achievements.")
    if result["newly_unlocked"]:
        print(f"Unlocked {len(result['newly_unlocked'])} new achievements!")
        for name in result["newly_unlocked"]:
            print(f" - {name}")
    else:
        print("No new achievements unlocked.")
