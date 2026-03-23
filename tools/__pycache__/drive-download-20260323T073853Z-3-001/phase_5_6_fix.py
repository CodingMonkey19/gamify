"""Surgical fix for Phase 5-6 naming gaps in Notion (Renaming Titles)."""

import os
import sys
import json

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import notion_client_wrapper as notion_api
from create_databases import number_schema, date_schema

logger = get_logger(__name__)

def fix_phase_5_6():
    db_ids_path = os.path.join(os.path.dirname(_tools_dir), "db_ids.json")
    with open(db_ids_path, "r") as f:
        db_ids = json.load(f)

    client = notion_api.get_client()

    # 1. Quests: Rename "Name" -> "Quest Title"
    logger.info("Fixing Quests database...")
    notion_api.update_database(client, db_ids["Quests"], {
        "Name": {"name": "Quest Title"}
    })

    # 2. Achievements: Rename "Name" -> "Badge Name"
    logger.info("Fixing Achievements database...")
    notion_api.update_database(client, db_ids["Achievements"], {
        "Name": {"name": "Badge Name"}
    })

    # 3. Player Achievements: Add "Date Unlocked" (Date)
    logger.info("Fixing Player Achievements database...")
    notion_api.update_database(client, db_ids["Player Achievements"], {
        "Date Unlocked": date_schema()
    })

    # 4. Loot Box Inventory: Rename "Name" -> "Reward Name", Add "Coins Awarded"
    logger.info("Fixing Loot Box Inventory database...")
    notion_api.update_database(client, db_ids["Loot Box Inventory"], {
        "Name": {"name": "Reward Name"},
        "Coins Awarded": number_schema()
    })

    logger.info("Phase 5-6 surgical fix complete.")

if __name__ == "__main__":
    fix_phase_5_6()
