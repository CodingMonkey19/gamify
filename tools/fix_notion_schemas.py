"""Fix missing Notion database properties based on Gap Analysis Report."""

import os
import sys
import json
from collections import OrderedDict

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import notion_client_wrapper as notion_api
from create_databases import (
    number_schema, title_schema, rich_text_schema, select_schema,
    checkbox_schema, date_schema, formula_schema, status_schema,
    DOMAIN_OPTIONS, STATUS_OPTIONS, HOTEL_TIER_OPTIONS, ACTIVITY_TYPE_OPTIONS
)

logger = get_logger(__name__)

# Mapping of Database Name -> Missing Properties (from Gap Report)
# Using schemas from create_databases.py to ensure correctness
MISSING_PROPS = {
    "Character": {
        "TDEE": number_schema(),
    },
    "Activity Log": {
        "EXP + (Financial)": number_schema(),
        "EXP + (Workout)": number_schema(),
        "EXP + (Nutrition)": number_schema(),
    },
    "Good Habit": {
        "Name": title_schema(),
        "Domain": select_schema(DOMAIN_OPTIONS),
        "XP Reward": number_schema(),
        "Frequency": select_schema([("Daily", "green"), ("Weekly", "blue")]),
        "Active": checkbox_schema(),
        "Check-in Status": formula_schema('if(prop("Active"), "Ready", "Paused")'),
    },
    "Bad Habit": {
        "Name": title_schema(),
        "Domain": select_schema(DOMAIN_OPTIONS),
        "HP Penalty": number_schema(),
        "HP Damage": number_schema(),
        "Severity": select_schema([("Low", "green"), ("Medium", "yellow"), ("High", "red")]),
        "Active": checkbox_schema(),
        "Check-in Status": formula_schema('if(prop("Active"), "Tracking", "Paused")'),
    },
    "Goal": {
        "Domain": select_schema(DOMAIN_OPTIONS),
        "XP Reward": number_schema(),
        "Coin Reward": number_schema(),
        "Status": status_schema(),
        "Due Date": date_schema(),
    },
    "Market": {
        "Name": title_schema(),
        "Category": select_schema([("Consumable", "green"), ("Upgrade", "blue"), ("Reward", "yellow")]),
        "Stock": number_schema(),
        "Purchased": checkbox_schema(),
        "Description": rich_text_schema(),
    },
    "My Cart": {
        "Name": title_schema(),
        "Quantity": number_schema(),
    },
    "Hotel": {
        "Name": title_schema(),
        "Tier": select_schema(HOTEL_TIER_OPTIONS),
    },
    "Black Market": {
        "Name": title_schema(),
        "Category": select_schema([("Recovery", "purple"), ("Shortcut", "orange"), ("Luxury", "red")]),
        "HP Cost": number_schema(),
        "Description": rich_text_schema(),
    },
    "Level Setting": {
        "Name": title_schema(),
        "Base XP": number_schema(),
        "Exponent": number_schema(),
        "Linear Mod": number_schema(),
    },
    "Budget Categories": {
        "Monthly Limit": number_schema("dollar"),
    },
    "Expense Log": {
        "Date": date_schema(),
    },
    "Treasury": {
        "Income": number_schema("dollar"),
        "Total Expenses": number_schema("dollar"),
        "Surplus": number_schema("dollar"),
        "Gold Earned": number_schema(),
        "WIS XP": number_schema(),
        "Breached Categories": number_schema(),
    },
    "Exercise Dictionary": {
        "Base XP Modifier": number_schema(),
    },
    "Workout Sessions": {
        "Session Date": date_schema(),
    },
    "Set Log": {
        "Estimated 1RM": formula_schema('floor(prop("Weight") * (1 + prop("Reps") / 30))'),
        "Progressive Delta": number_schema(),
        "Session XP": number_schema(),
    },
    "Meal Log": {
        "Date": date_schema(),
        "Carbs": number_schema(),
        "Fat": number_schema(),
    }
}

def fix_schemas():
    db_ids_path = os.path.join(os.path.dirname(_tools_dir), "db_ids.json")
    if not os.path.exists(db_ids_path):
        logger.error(f"db_ids.json not found at {db_ids_path}")
        return

    with open(db_ids_path, "r") as f:
        db_ids = json.load(f)

    client = notion_api.get_client()
    
    total_fixed = 0
    for db_name, props in MISSING_PROPS.items():
        db_id = db_ids.get(db_name)
        if not db_id:
            logger.warning(f"Database '{db_name}' not found in db_ids.json, skipping.")
            continue
            
        logger.info(f"Checking/Fixing schema for '{db_name}' ({db_id})...")
        try:
            # First, check what properties already exist to avoid unnecessary updates
            # and to log what's actually being added.
            db_obj = notion_api.get_database(client, db_id)
            existing_props = db_obj.get("properties", {}).keys()
            
            props_to_add = {k: v for k, v in props.items() if k not in existing_props}
            
            if not props_to_add:
                logger.info(f"All properties for '{db_name}' already exist. Skipping.")
                continue
                
            logger.info(f"Adding properties to '{db_name}': {list(props_to_add.keys())}")
            notion_api.update_database(client, db_id, props_to_add)
            total_fixed += 1
            logger.info(f"Successfully updated '{db_name}'.")
            
        except Exception as e:
            logger.error(f"Failed to update '{db_name}': {e}")

    logger.info(f"Finished schema fixes. Databases updated: {total_fixed}")

if __name__ == "__main__":
    fix_schemas()
