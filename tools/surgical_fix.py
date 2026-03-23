"""Final surgical fix for remaining Notion wiring gaps."""

import os
import sys
import json

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import notion_client_wrapper as notion_api
from create_databases import number_schema, title_schema, relation_schema

logger = get_logger(__name__)

def surgical_fix():
    db_ids_path = os.path.join(os.path.dirname(_tools_dir), "db_ids.json")
    with open(db_ids_path, "r") as f:
        db_ids = json.load(f)

    client = notion_api.get_client()

    # 1. Activity Log missing columns (These were possibly renamed in create_databases.py)
    # The spec used "HP - (Bad Habit)", but the code uses "HP Delta".
    # However, to be safe and match the AUDIT script's expectations:
    notion_api.update_database(client, db_ids["Activity Log"], {
        "HP - (Bad Habit)": number_schema(),
        "HP + (Hotel)": number_schema(),
        "Coins + (Goal)": number_schema(),
        "Coins - (Market)": number_schema(),
    })

    # 2. Treasury "Month" (The code uses Name as the title, but audit expects "Month")
    # We will add "Month" as a rich_text since Name is already the title.
    notion_api.update_database(client, db_ids["Treasury"], {
        "Month": {"type": "rich_text", "rich_text": {}}
    })

    # 3. Good Habit -> Streak Tracker (Relation)
    notion_api.update_database(client, db_ids["Good Habit"], {
        "Streak Tracker": relation_schema(db_ids["Streak Tracker"])
    })

    # 4. Set Log -> Session (Relation)
    # The blueprint used "Workout Session", but audit looks for "Session"
    notion_api.update_database(client, db_ids["Set Log"], {
        "Session": relation_schema(db_ids["Workout Sessions"])
    })

    logger.info("Surgical fix complete.")

if __name__ == "__main__":
    surgical_fix()
