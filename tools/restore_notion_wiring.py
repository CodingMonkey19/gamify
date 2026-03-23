"""Restoration script for Notion database wiring (Properties + Relations)."""

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
    DATABASE_SCHEMAS, RELATION_BLUEPRINTS, BUTTON_BLUEPRINTS,
    relation_schema, rollup_schema
)

logger = get_logger(__name__)

def restore_wiring():
    db_ids_path = os.path.join(os.path.dirname(_tools_dir), "db_ids.json")
    if not os.path.exists(db_ids_path):
        logger.error("db_ids.json not found.")
        return

    with open(db_ids_path, "r") as f:
        db_ids = json.load(f)

    client = notion_api.get_client()

    # PASS 1: Restore non-relation properties
    logger.info("--- PASS 1: Restoring non-relation properties ---")
    for db_name, expected_props in DATABASE_SCHEMAS.items():
        db_id = db_ids.get(db_name)
        if not db_id:
            logger.warning(f"Database '{db_name}' missing from db_ids.json, skipping.")
            continue

        try:
            # Fetch current database to check existing properties
            existing_props = notion_api.get_database_properties(client, db_id)
            
            # Find properties that are missing in the live database
            props_to_add = {k: v for k, v in expected_props.items() if k not in existing_props}
            
            if props_to_add:
                logger.info(f"Adding {len(props_to_add)} missing properties to '{db_name}'")
                notion_api.update_database(client, db_id, props_to_add)
            else:
                logger.info(f"Database '{db_name}' already has all base properties.")
        except Exception as e:
            logger.error(f"Error in Pass 1 for '{db_name}': {e}")

    # PASS 2: Restore relations and rollups
    logger.info("--- PASS 2: Restoring relations and rollups ---")
    for db_name, blueprints in RELATION_BLUEPRINTS.items():
        db_id = db_ids.get(db_name)
        if not db_id:
            continue

        try:
            existing_props = notion_api.get_database_properties(client, db_id)
            
            props_to_add = {}
            for prop_name, (target_name, builder) in blueprints.items():
                if prop_name in existing_props:
                    continue # Skip if already exists
                
                if builder is relation_schema:
                    target_id = db_ids.get(target_name)
                    if not target_id:
                        logger.warning(f"Relation target '{target_name}' missing for '{db_name}.{prop_name}'")
                        continue
                    props_to_add[prop_name] = builder(target_id)
                elif callable(builder): # Handle rollup lambdas
                    # For rollups like "Entries Count", builder(target_name) where target_name is "Activity Entries"
                    # But the schema actually expects relation_property_name and rollup_property_name.
                    # Looking at RELATION_BLUEPRINTS, it's: "Entries Count": ("Activity Entries", lambda _db_id: rollup_schema("Activity Entries", "Name"))
                    # The lambda ignores its argument in the current implementation.
                    props_to_add[prop_name] = builder(target_name)
                else:
                    logger.warning(f"Unknown builder for '{db_name}.{prop_name}'")

            if props_to_add:
                logger.info(f"Adding {len(props_to_add)} relations/rollups to '{db_name}'")
                notion_api.update_database(client, db_id, props_to_add)
            else:
                logger.info(f"Database '{db_name}' relations already intact.")
        except Exception as e:
            logger.error(f"Error in Pass 2 for '{db_name}': {e}")

    # PASS 3: Buttons (Best effort)
    logger.info("--- PASS 3: Restoring buttons ---")
    for db_name, button_names in BUTTON_BLUEPRINTS.items():
        db_id = db_ids.get(db_name)
        if not db_id: continue
        
        try:
            existing_props = notion_api.get_database_properties(client, db_id)
            
            missing_buttons = [b for b in button_names if b not in existing_props]
            if missing_buttons:
                btn_props = {name: {"type": "button", "button": {}} for name in missing_buttons}
                logger.info(f"Adding {len(missing_buttons)} buttons to '{db_name}'")
                notion_api.update_database(client, db_id, btn_props)
        except Exception as e:
            logger.warning(f"Button restoration failed for '{db_name}': {e}")

    logger.info("Wiring restoration complete.")

if __name__ == "__main__":
    restore_wiring()
