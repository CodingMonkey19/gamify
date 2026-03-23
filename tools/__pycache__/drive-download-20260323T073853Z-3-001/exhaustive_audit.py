"""Exhaustive final audit of all 33 Notion databases."""

import os
import sys
import json

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import notion_client_wrapper as notion_api
from create_databases import DATABASE_SCHEMAS, RELATION_BLUEPRINTS

logger = get_logger(__name__)

def exhaustive_audit():
    db_ids_path = os.path.join(os.path.dirname(_tools_dir), "db_ids.json")
    with open(db_ids_path, "r") as f:
        db_ids = json.load(f)

    client = notion_api.get_client()
    total_errors = 0
    
    print(f"{'DATABASE':<25} | {'RESULT':<10} | {'DETAILS'}")
    print("-" * 100)

    for db_name, expected_props in DATABASE_SCHEMAS.items():
        db_id = db_ids.get(db_name)
        if not db_id:
            print(f"{db_name:<25} | FAIL       | Database missing from db_ids.json")
            total_errors += 1
            continue

        try:
            live_props = notion_api.get_database_properties(client, db_id)
            
            # 1. Check for missing properties
            missing = [p for p in expected_props if p not in live_props]
            
            # 2. Check relations (from blueprints)
            blueprints = RELATION_BLUEPRINTS.get(db_name, {})
            missing_relations = [p for p in blueprints if p not in live_props]
            
            # 3. Check property types
            type_mismatches = []
            for p_name, p_schema in expected_props.items():
                if p_name in live_props:
                    live_type = live_props[p_name]["type"]
                    expected_type = p_schema["type"]
                    if live_type != expected_type:
                        type_mismatches.append(f"{p_name}({live_type}!={expected_type})")

            if not missing and not missing_relations and not type_mismatches:
                print(f"{db_name:<25} | PASS       | 100% Schema Match")
            else:
                details = []
                if missing: details.append(f"Missing: {len(missing)}")
                if missing_relations: details.append(f"Rel Missing: {len(missing_relations)}")
                if type_mismatches: details.append(f"Type Err: {len(type_mismatches)}")
                
                print(f"{db_name:<25} | FAIL       | {', '.join(details)}")
                
                # Log detailed failures for debugging
                if missing: logger.error(f"[{db_name}] Missing properties: {missing}")
                if missing_relations: logger.error(f"[{db_name}] Missing relations: {missing_relations}")
                if type_mismatches: logger.error(f"[{db_name}] Type mismatches: {type_mismatches}")
                total_errors += 1

        except Exception as e:
            print(f"{db_name:<25} | ERROR      | {str(e)}")
            total_errors += 1

    print("\n" + "="*100)
    if total_errors == 0:
        print("FINAL VERDICT: WORKSPACE IS 100% IN SYNC WITH SPECIFICATIONS.")
    else:
        print(f"FINAL VERDICT: {total_errors} DATABASES STILL HAVE ISSUES. RE-FIX REQUIRED.")
    print("="*100)

if __name__ == "__main__":
    exhaustive_audit()
