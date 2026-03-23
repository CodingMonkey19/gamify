"""Versioned schema migrations for the Notion workspace."""

from datetime import datetime, timezone
import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from logger import get_logger
import notion_client_wrapper as notion_api
from create_databases import (
    ACTIVITY_TYPE_OPTIONS,
    DOMAIN_OPTIONS,
    OVERDRAFT_FREQUENCY_OPTIONS,
    RANK_OPTIONS,
    STREAK_TIER_OPTIONS,
    checkbox_schema,
    date_schema,
    formula_schema,
    load_db_ids,
    number_schema,
    relation_schema,
    select_schema,
)


logger = get_logger(__name__)
LEDGER_FILENAME = "migrations.json"


def _phase3_activity_log_fields(db_ids):
    return {
        "EXP + (Habit)": number_schema(),
        "EXP + (Goal)": number_schema(),
        "EXP + (Tasks)": number_schema(),
        "Brain Dump": relation_schema(db_ids["Brain Dump"]),
    }


def _phase3_streak_tracker_fields(db_ids):
    return {
        "Habit": relation_schema(db_ids["Good Habit"]),
        "Domain": select_schema(DOMAIN_OPTIONS),
        "Current Streak": number_schema(),
        "Best Streak": number_schema(),
        "Current Tier": select_schema(STREAK_TIER_OPTIONS),
    }


def _phase3_goal_fields(db_ids):
    return {"Related Skills": relation_schema(db_ids["Skill/Area"])}


def _phase3_brain_dump_fields(db_ids):
    return {"Related Skills": relation_schema(db_ids["Skill/Area"])}


def _phase4_activity_log_fields(db_ids):
    del db_ids
    return {
        "EXP + (Financial)": number_schema(),
        "EXP + (Workout)": number_schema(),
        "EXP + (Nutrition)": number_schema(),
    }


def _phase4_character_fields(db_ids):
    del db_ids
    return {"TDEE": number_schema()}


def _phase4_budget_category_fields(db_ids):
    return {
        "Character": relation_schema(db_ids["Character"]),
        "Monthly Limit": number_schema("dollar"),
    }


def _phase4_expense_log_fields(db_ids):
    return {
        "Character": relation_schema(db_ids["Character"]),
        "Date": date_schema(),
    }


def _phase4_treasury_fields(db_ids):
    return {
        "Character": relation_schema(db_ids["Character"]),
        "Income": number_schema("dollar"),
        "Total Expenses": number_schema("dollar"),
        "Surplus": number_schema("dollar"),
        "Gold Earned": number_schema(),
        "WIS XP": number_schema(),
        "Breached Categories": number_schema(),
    }


def _phase4_exercise_fields(db_ids):
    del db_ids
    return {"Base XP Modifier": number_schema()}


def _phase4_workout_session_fields(db_ids):
    del db_ids
    return {"Session Date": date_schema()}


def _phase4_set_log_fields(db_ids):
    del db_ids
    return {
        "Estimated 1RM": formula_schema('floor(prop("Weight") * (1 + prop("Reps") / 30))'),
        "Progressive Delta": number_schema(),
        "Session XP": number_schema(),
    }


def _phase4_meal_log_fields(db_ids):
    del db_ids
    return {
        "Date": date_schema(),
        "Carbs": number_schema(),
        "Fat": number_schema(),
    }


SAMPLE_MIGRATIONS = [
    {
        "id": "001_add_mood_intensity",
        "description": "Add Intensity property to Mood database",
        "database": "Mood",
        "operation": "add_property",
        "property_name": "Intensity",
        "property_schema": {"Intensity": {"type": "number", "number": {"format": "number"}}},
    },
    {
        "id": "002_phase2_character_fields",
        "description": "Add Phase 2 Character fields",
        "database": "Character",
        "operation": "add_property",
        "property_name": "Phase 2 Character fields",
        "property_schema": {
            "Current HP": number_schema(),
            "Current Coins": number_schema(),
            "Death Count": number_schema(),
            "Respawn": checkbox_schema(),
        },
    },
    {
        "id": "003_phase2_activity_log_types",
        "description": "Extend Activity Log Type options for Phase 2",
        "database": "Activity Log",
        "operation": "update_property",
        "property_name": "Type",
        "property_schema": {"Type": select_schema(ACTIVITY_TYPE_OPTIONS)},
    },
    {
        "id": "004_phase2_market_fields",
        "description": "Add Market purchase tracking fields",
        "database": "Market",
        "operation": "add_property",
        "property_name": "Market purchase fields",
        "property_schema": {
            "Purchased": checkbox_schema(),
            "Redemption Date": date_schema(),
        },
    },
    {
        "id": "005_phase2_overdraft_fields",
        "description": "Add Overdraft scheduling fields",
        "database": "Overdraft Penalty",
        "operation": "add_property",
        "property_name": "Overdraft scheduling fields",
        "property_schema": {
            "HP Penalty": number_schema(),
            "Frequency": select_schema(OVERDRAFT_FREQUENCY_OPTIONS),
            "Last Check": date_schema(),
        },
    },
    {
        "id": "006_phase3_character_fields",
        "description": "Add Phase 3 Character progression fields",
        "database": "Character",
        "operation": "add_property",
        "property_name": "Phase 3 Character fields",
        "property_schema": {
            "Player Level": number_schema(),
            "Total XP": number_schema(),
            "Current Rank": select_schema(RANK_OPTIONS),
            "STR Level": number_schema(),
            "INT Level": number_schema(),
            "WIS Level": number_schema(),
            "VIT Level": number_schema(),
            "CHA Level": number_schema(),
        },
    },
    {
        "id": "007_phase3_activity_log_fields",
        "description": "Add Phase 3 Activity Log XP fields and task relation",
        "database": "Activity Log",
        "operation": "add_property",
        "property_name": "Phase 3 Activity Log fields",
        "property_schema_builder": _phase3_activity_log_fields,
    },
    {
        "id": "008_phase3_activity_log_types",
        "description": "Extend Activity Log Type options for Phase 3",
        "database": "Activity Log",
        "operation": "update_property",
        "property_name": "Type",
        "property_schema": {"Type": select_schema(ACTIVITY_TYPE_OPTIONS)},
    },
    {
        "id": "009_phase3_good_habit_fields",
        "description": "Add Phase 3 Good Habit alias fields",
        "database": "Good Habit",
        "operation": "add_property",
        "property_name": "Phase 3 Good Habit fields",
        "property_schema": {
            "Domain": select_schema(DOMAIN_OPTIONS),
            "EXP Earn": number_schema(),
        },
    },
    {
        "id": "010_phase3_bad_habit_fields",
        "description": "Add Phase 3 Bad Habit alias fields",
        "database": "Bad Habit",
        "operation": "add_property",
        "property_name": "Phase 3 Bad Habit fields",
        "property_schema": {
            "Domain": select_schema(DOMAIN_OPTIONS),
            "HP Damage": number_schema(),
        },
    },
    {
        "id": "011_phase3_skill_area_fields",
        "description": "Add Phase 3 Skill/Area stat alias",
        "database": "Skill/Area",
        "operation": "add_property",
        "property_name": "Phase 3 Skill fields",
        "property_schema": {"Stat": select_schema(DOMAIN_OPTIONS)},
    },
    {
        "id": "012_phase3_streak_tracker_fields",
        "description": "Add Phase 3 Streak Tracker fields",
        "database": "Streak Tracker",
        "operation": "add_property",
        "property_name": "Phase 3 Streak Tracker fields",
        "property_schema_builder": _phase3_streak_tracker_fields,
    },
    {
        "id": "013_phase3_goal_fields",
        "description": "Add Phase 3 Goal skill relation",
        "database": "Goal",
        "operation": "add_property",
        "property_name": "Phase 3 Goal fields",
        "property_schema_builder": _phase3_goal_fields,
    },
    {
        "id": "014_phase3_brain_dump_fields",
        "description": "Add Phase 3 Brain Dump skill relation",
        "database": "Brain Dump",
        "operation": "add_property",
        "property_name": "Phase 3 Brain Dump fields",
        "property_schema_builder": _phase3_brain_dump_fields,
    },
    {
        "id": "015_phase4_activity_log_fields",
        "description": "Add Phase 4 Activity Log XP fields",
        "database": "Activity Log",
        "operation": "add_property",
        "property_name": "Phase 4 Activity Log fields",
        "property_schema_builder": _phase4_activity_log_fields,
    },
    {
        "id": "016_phase4_activity_log_types",
        "description": "Extend Activity Log Type options for Phase 4",
        "database": "Activity Log",
        "operation": "update_property",
        "property_name": "Type",
        "property_schema": {"Type": select_schema(ACTIVITY_TYPE_OPTIONS)},
    },
    {
        "id": "017_phase4_character_fields",
        "description": "Add Phase 4 Character fields",
        "database": "Character",
        "operation": "add_property",
        "property_name": "Phase 4 Character fields",
        "property_schema_builder": _phase4_character_fields,
    },
    {
        "id": "018_phase4_budget_category_fields",
        "description": "Add Phase 4 Budget Category fields",
        "database": "Budget Categories",
        "operation": "add_property",
        "property_name": "Phase 4 Budget Category fields",
        "property_schema_builder": _phase4_budget_category_fields,
    },
    {
        "id": "019_phase4_expense_log_fields",
        "description": "Add Phase 4 Expense Log fields",
        "database": "Expense Log",
        "operation": "add_property",
        "property_name": "Phase 4 Expense Log fields",
        "property_schema_builder": _phase4_expense_log_fields,
    },
    {
        "id": "020_phase4_treasury_fields",
        "description": "Add Phase 4 Treasury fields",
        "database": "Treasury",
        "operation": "add_property",
        "property_name": "Phase 4 Treasury fields",
        "property_schema_builder": _phase4_treasury_fields,
    },
    {
        "id": "021_phase4_exercise_fields",
        "description": "Add Phase 4 Exercise Dictionary fields",
        "database": "Exercise Dictionary",
        "operation": "add_property",
        "property_name": "Phase 4 Exercise fields",
        "property_schema_builder": _phase4_exercise_fields,
    },
    {
        "id": "022_phase4_workout_session_fields",
        "description": "Add Phase 4 Workout Session fields",
        "database": "Workout Sessions",
        "operation": "add_property",
        "property_name": "Phase 4 Workout Session fields",
        "property_schema_builder": _phase4_workout_session_fields,
    },
    {
        "id": "023_phase4_set_log_fields",
        "description": "Add Phase 4 Set Log fields",
        "database": "Set Log",
        "operation": "add_property",
        "property_name": "Phase 4 Set Log fields",
        "property_schema_builder": _phase4_set_log_fields,
    },
    {
        "id": "024_phase4_meal_log_fields",
        "description": "Add Phase 4 Meal Log fields",
        "database": "Meal Log",
        "operation": "add_property",
        "property_name": "Phase 4 Meal Log fields",
        "property_schema_builder": _phase4_meal_log_fields,
    },
]


def _ledger_path(path=None):
    return path or os.path.join(os.path.dirname(_TOOLS_DIR), LEDGER_FILENAME)


def load_ledger(path=None):
    file_path = _ledger_path(path)
    if not os.path.exists(file_path):
        return {"applied": []}
    with open(file_path) as handle:
        return json.load(handle)


def save_ledger(ledger, path=None):
    file_path = _ledger_path(path)
    with open(file_path, "w") as handle:
        json.dump(ledger, handle, indent=2)


def _apply_migration(client, db_ids, migration):
    database_name = migration["database"]
    database_id = db_ids.get(database_name)
    if not database_id:
        raise KeyError(f"Missing database id for {database_name}")

    property_schema = migration.get("property_schema")
    property_schema_builder = migration.get("property_schema_builder")
    if property_schema_builder is not None:
        property_schema = property_schema_builder(db_ids)

    operation = migration["operation"]
    if operation in {"add_property", "update_property"}:
        notion_api.update_database(client, database_id, property_schema)
        return

    raise ValueError(f"Unsupported migration operation: {operation}")


def run_migrations(client, db_ids, migrations=None, ledger_path=None):
    """Apply pending migrations in order and record successes."""
    migrations = migrations if migrations is not None else SAMPLE_MIGRATIONS
    ledger = load_ledger(ledger_path)
    applied_ids = {item["id"] for item in ledger.get("applied", [])}

    result = {"applied": [], "skipped": [], "failed": [], "pending": 0}

    for migration in sorted(migrations, key=lambda item: item["id"]):
        migration_id = migration["id"]
        if migration_id in applied_ids:
            result["skipped"].append(migration_id)
            continue

        try:
            _apply_migration(client, db_ids, migration)
            ledger.setdefault("applied", []).append(
                {"id": migration_id, "applied_at": datetime.now(timezone.utc).isoformat()}
            )
            save_ledger(ledger, ledger_path)
            result["applied"].append(migration_id)
        except Exception as exc:
            logger.error(f"Migration {migration_id} failed: {exc}")
            result["failed"].append(migration_id)

    applied_or_skipped = len(result["applied"]) + len(result["skipped"])
    result["pending"] = max(len(migrations) - applied_or_skipped, 0)
    return result


def main():
    client = notion_api.get_client()
    db_ids = load_db_ids()
    result = run_migrations(client=client, db_ids=db_ids)
    print(json.dumps(result, indent=2))
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
