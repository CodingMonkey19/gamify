"""
Snapshot Engine — Creates daily character snapshots for trend tracking.
Reads character stats and active streaks, writes to Daily Snapshots DB.

Usage:
    python -m tools.snapshot_engine --character-id <ID>
"""
import argparse
import os
import sys
from datetime import date

from notion_client import Client

from .logger import get_logger

logger = get_logger(__name__)

# --- Notion DB IDs (hardcoded from verified workspace) ---
DAILY_SNAPSHOTS_DB_ID = "10168a1e-e30c-4907-8871-65519cec7abe"
CHARACTER_DB_ID = "f814ec57-8879-482b-81cb-e68104d252c8"
STREAK_TRACKER_DB_ID = "2da610df-0671-4259-a8bb-905c396fb3d0"


def take_snapshot(character_id, run_date=None):
    """Create a daily snapshot of character stats.

    1. Init Notion client from env NOTION_TOKEN
    2. Default run_date to today if not provided
    3. Check for existing snapshot (idempotent — skip if exists)
    4. Read character stats from Character DB
    5. Count active streaks from Streak Tracker DB
    6. Create snapshot page in Daily Snapshots DB

    Args:
        character_id (str): Notion Character page ID
        run_date (date, optional): Date for the snapshot. Defaults to today.

    Returns:
        dict: Snapshot data if created, None if snapshot already exists
    """
    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    if not notion_token:
        raise RuntimeError("NOTION_TOKEN env var is missing or empty")

    notion = Client(auth=notion_token)

    # Default to today
    if run_date is None:
        run_date = date.today()

    run_date_str = run_date.isoformat()
    logger.info(f"Taking snapshot for character {character_id} on {run_date_str}")

    # --- Check for existing snapshot (idempotent) ---
    existing = notion.databases.query(
        database_id=DAILY_SNAPSHOTS_DB_ID,
        filter={
            "property": "Date",
            "date": {"equals": run_date_str},
        },
    )

    if existing.get("results"):
        logger.info(f"Snapshot already exists for {run_date_str} — skipping")
        return None

    # --- Read character stats ---
    character_page = notion.pages.retrieve(page_id=character_id)
    props = character_page.get("properties", {})

    str_xp = props.get("STR XP", {}).get("number") or 0
    int_xp = props.get("INT XP", {}).get("number") or 0
    wis_xp = props.get("WIS XP", {}).get("number") or 0
    vit_xp = props.get("VIT XP", {}).get("number") or 0
    cha_xp = props.get("CHA XP", {}).get("number") or 0
    level = props.get("Level", {}).get("number") or 0
    gold = props.get("Gold", {}).get("number") or 0
    coins = props.get("Coins", {}).get("number") or 0
    hp = props.get("HP", {}).get("number") or 0

    rank_select = props.get("Rank", {}).get("select")
    rank = rank_select["name"] if rank_select else "Peasant"

    logger.info(
        f"Character stats — STR:{str_xp} INT:{int_xp} WIS:{wis_xp} "
        f"VIT:{vit_xp} CHA:{cha_xp} Level:{level} Gold:{gold} "
        f"Coins:{coins} HP:{hp} Rank:{rank}"
    )

    # --- Count active streaks ---
    streak_response = notion.databases.query(
        database_id=STREAK_TRACKER_DB_ID,
        filter={
            "and": [
                {"property": "Active", "checkbox": {"equals": True}},
                {"property": "Character", "relation": {"contains": character_id}},
            ]
        },
    )

    active_streaks = len(streak_response.get("results", []))
    logger.info(f"Active streaks: {active_streaks}")

    # --- Create snapshot page ---
    snapshot_properties = {
        "Date": {"date": {"start": run_date_str}},
        "Character": {"relation": [{"id": character_id}]},
        "STR XP": {"number": str_xp},
        "INT XP": {"number": int_xp},
        "WIS XP": {"number": wis_xp},
        "VIT XP": {"number": vit_xp},
        "CHA XP": {"number": cha_xp},
        "Level": {"number": level},
        "Gold": {"number": gold},
        "Coins": {"number": coins},
        "HP": {"number": hp},
        "Rank": {"select": {"name": rank}},
        "Active Streaks": {"number": active_streaks},
        "Mood": {"select": {"name": "Neutral"}},
    }

    notion.pages.create(
        parent={"database_id": DAILY_SNAPSHOTS_DB_ID},
        properties=snapshot_properties,
    )

    snapshot_data = {
        "date": run_date_str,
        "character_id": character_id,
        "str_xp": str_xp,
        "int_xp": int_xp,
        "wis_xp": wis_xp,
        "vit_xp": vit_xp,
        "cha_xp": cha_xp,
        "level": level,
        "gold": gold,
        "coins": coins,
        "hp": hp,
        "rank": rank,
        "active_streaks": active_streaks,
        "mood": "Neutral",
    }

    logger.info(f"Snapshot created for {run_date_str}")
    return snapshot_data


def main():
    parser = argparse.ArgumentParser(description="Create daily character snapshot")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = take_snapshot(args.character_id)
    if result is None:
        print("Snapshot already exists for today — skipped")
    else:
        print(f"Snapshot created for {result['date']}")
        print(f"  Level: {result['level']}  Rank: {result['rank']}")
        print(f"  STR: {result['str_xp']}  INT: {result['int_xp']}  WIS: {result['wis_xp']}  "
              f"VIT: {result['vit_xp']}  CHA: {result['cha_xp']}")
        print(f"  Gold: {result['gold']}  Coins: {result['coins']}  HP: {result['hp']}")
        print(f"  Active Streaks: {result['active_streaks']}  Mood: {result['mood']}")


if __name__ == "__main__":
    main()
