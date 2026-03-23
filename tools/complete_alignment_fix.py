"""Final comprehensive alignment fix for all findings (Phases 1-6)."""

import os
import sys
import json

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import notion_client_wrapper as notion_api
from create_databases import (
    status_schema, STATUS_OPTIONS, number_schema, rich_text_schema, select_schema
)

logger = get_logger(__name__)

def align_all():
    with open('db_ids.json') as f:
        db_ids = json.load(f)
    
    client = notion_api.get_client()

    # 1. FIX QUESTS STATUS OPTIONS
    # Spec: Available / In Progress / Completed / Failed
    # We must update the Status property schema. 
    # Note: Notion API allows updating status options.
    logger.info("Fixing Quests Status options...")
    notion_api.update_database(client, db_ids["Quests"], {
        "Status": {
            "type": "status",
            "status": {
                "options": [
                    {"name": "Available", "color": "default"},
                    {"name": "In Progress", "color": "blue"},
                    {"name": "Completed", "color": "green"},
                    {"name": "Failed", "color": "red"}
                ]
            }
        }
    })

    # 2. SEED MISSING SETTINGS ROWS
    MISSING_SETTINGS = {
        "WIS_XP_PER_GOLD": "10",
        "RPE_XP_WEIGHT": "True",
        "OVERLOAD_WINDOW_DAYS": "14",
        "NUTRITION_STREAK_MULTIPLIER": "1.15",
        "LOOT_WEIGHTS": '{"Common": 70, "Rare": 20, "Epic": 8, "Legendary": 2}',
        "LOOT_REWARDS": '{"Common": 25, "Rare": 75, "Epic": 200, "Legendary": 1000}',
        "RANK_THRESHOLDS": '{0: "Peasant", 1000: "Squire", 5000: "Knight", 15000: "Champion", 40000: "Hero", 100000: "Legend", 250000: "Mythic"}',
        "QUEST_DIFFICULTY_REWARDS": '{"Easy": {"xp": 25, "gold": 5}, "Medium": {"xp": 50, "gold": 10}, "Hard": {"xp": 100, "gold": 25}, "Epic": {"xp": 200, "gold": 50}}',
        "OPENAI_MODEL": "gpt-4o-mini"
    }
    
    existing_settings_rows = notion_api.query_database(client, db_ids["Settings"])
    existing_names = [row['properties']['Name']['title'][0]['plain_text'] for row in existing_settings_rows if row['properties']['Name']['title']]
    
    for name, value in MISSING_SETTINGS.items():
        if name not in existing_names:
            logger.info(f"Seeding missing setting: {name}")
            notion_api.create_page(client, db_ids["Settings"], {
                "Name": {"title": [{"text": {"content": name}}]},
                "Value": {"rich_text": [{"text": {"content": value}}]},
                "Type": {"select": {"name": "json" if "{" in value else ("number" if value.isdigit() else "text")}}
            })

    # 3. FIX PHASE 4 PROPERTY DRIFT
    # Set Log: Add Set# and RIR
    logger.info("Fixing Set Log properties...")
    notion_api.update_database(client, db_ids["Set Log"], {
        "Set#": number_schema(),
        "RIR": number_schema()
    })
    
    # Ingredients Library: Rename/Add per-100g contract
    logger.info("Fixing Ingredients Library properties...")
    notion_api.update_database(client, db_ids["Ingredients Library"], {
        "Calories (per 100g)": number_schema(),
        "Protein (per 100g)": number_schema(),
        "Carbs (per 100g)": number_schema(),
        "Fat (per 100g)": number_schema()
    })

    logger.info("Alignment fix complete.")

if __name__ == "__main__":
    align_all()
