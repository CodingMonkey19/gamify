"""Create the full Phase 1 Notion database workspace."""

from collections import OrderedDict
import argparse
import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from logger import get_logger
import notion_client_wrapper as notion_api


logger = get_logger(__name__)
DB_IDS_FILENAME = "db_ids.json"


def title_schema():
    return {"type": "title", "title": {}}


def rich_text_schema():
    return {"type": "rich_text", "rich_text": {}}


def number_schema(fmt="number"):
    return {"type": "number", "number": {"format": fmt}}


def select_schema(options):
    return {"type": "select", "select": {"options": [{"name": name, "color": color} for name, color in options]}}


def multi_select_schema(options):
    return {"type": "multi_select", "multi_select": {"options": [{"name": name, "color": color} for name, color in options]}}


def status_schema(options=None):
    payload = {"type": "status", "status": {}}
    if options:
        payload["status"]["options"] = [{"name": name, "color": color} for name, color in options]
    return payload


def checkbox_schema():
    return {"type": "checkbox", "checkbox": {}}


def date_schema():
    return {"type": "date", "date": {}}


def url_schema():
    return {"type": "url", "url": {}}


def files_schema():
    return {"type": "files", "files": {}}


def formula_schema(expression):
    return {"type": "formula", "formula": {"expression": expression}}


def relation_schema(target_db_id):
    return {
        "type": "relation",
        "relation": {
            "database_id": target_db_id,
            "type": "single_property",
            "single_property": {},
        },
    }


def rollup_schema(relation_property_name, rollup_property_name, function="count_all"):
    return {
        "type": "rollup",
        "rollup": {
            "relation_property_name": relation_property_name,
            "rollup_property_name": rollup_property_name,
            "function": function,
        },
    }


DOMAIN_OPTIONS = [
    ("STR", "red"),
    ("INT", "blue"),
    ("WIS", "yellow"),
    ("VIT", "green"),
    ("CHA", "purple"),
]
STATUS_OPTIONS = [("Not started", "gray"), ("In progress", "blue"), ("Done", "green")]
RARITY_OPTIONS = [("Common", "gray"), ("Rare", "blue"), ("Epic", "purple"), ("Legendary", "yellow")]
HOTEL_TIER_OPTIONS = [("Budget", "green"), ("Ordinary", "blue"), ("Premium", "yellow")]
RANK_OPTIONS = [
    ("Peasant", "gray"),
    ("Squire", "blue"),
    ("Knight", "green"),
    ("Champion", "yellow"),
    ("Hero", "orange"),
    ("Legend", "red"),
    ("Mythic", "purple"),
]
CLASS_OPTIONS = [
    ("Warrior", "red"),
    ("Mage", "blue"),
    ("Rogue", "purple"),
    ("Paladin", "yellow"),
    ("Ranger", "green"),
]
STREAK_TIER_OPTIONS = [
    ("None", "gray"),
    ("Bronze", "brown"),
    ("Silver", "blue"),
    ("Gold", "yellow"),
    ("Platinum", "green"),
    ("Diamond", "purple"),
    ("Mythic", "red"),
]
ACTIVITY_TYPE_OPTIONS = [
    ("GOOD", "green"),
    ("BAD", "red"),
    ("GOAL", "blue"),
    ("TASKS", "yellow"),
    ("FINANCIAL", "yellow"),
    ("WORKOUT", "red"),
    ("NUTRITION", "green"),
    ("MARKET", "orange"),
    ("HOTEL", "purple"),
    ("BLACKMARKET", "brown"),
    ("DIED", "gray"),
    ("RESPAWN", "green"),
    ("PENALTY", "red"),
    ("DECAY", "gray"),
]
OVERDRAFT_FREQUENCY_OPTIONS = [
    ("Daily", "green"),
    ("Weekly", "blue"),
    ("Biweekly", "yellow"),
    ("Disabled", "gray"),
]


DATABASE_SCHEMAS = OrderedDict(
    [
        (
            "Character",
            {
                "Name": title_schema(),
                "HP": number_schema(),
                "Current HP": number_schema(),
                "Max HP": number_schema(),
                "Coins": number_schema(),
                "Current Coins": number_schema(),
                "Gold": number_schema(),
                "TDEE": number_schema(),
                "Level": number_schema(),
                "Player Level": number_schema(),
                "Total XP": number_schema(),
                "Death Count": number_schema(),
                "Respawn": checkbox_schema(),
                "Rank": select_schema(RANK_OPTIONS),
                "Current Rank": select_schema(RANK_OPTIONS),
                "Class": select_schema(CLASS_OPTIONS),
                "STR XP": number_schema(),
                "STR Level": number_schema(),
                "INT XP": number_schema(),
                "INT Level": number_schema(),
                "WIS XP": number_schema(),
                "WIS Level": number_schema(),
                "VIT XP": number_schema(),
                "VIT Level": number_schema(),
                "CHA XP": number_schema(),
                "CHA Level": number_schema(),
                "Death Penalty": rich_text_schema(),
                "Avatar URL": url_schema(),
                "Radar Chart URL": url_schema(),
                "EXP Progress": formula_schema('""'),
                "HP Progress": formula_schema('""'),
                "Character Details": formula_schema('prop("Name")'),
            },
        ),
        (
            "Activity Log",
            {
                "Name": title_schema(),
                "Type": select_schema(ACTIVITY_TYPE_OPTIONS),
                "Domain": select_schema(DOMAIN_OPTIONS),
                "XP Earned": number_schema(),
                "EXP + (Habit)": number_schema(),
                "EXP + (Goal)": number_schema(),
                "EXP + (Tasks)": number_schema(),
                "EXP + (Financial)": number_schema(),
                "EXP + (Workout)": number_schema(),
                "EXP + (Nutrition)": number_schema(),
                "Coins Earned": number_schema(),
                "HP Delta": number_schema(),
                "Gold Earned": number_schema(),
                "Occurred At": date_schema(),
                "Notes": rich_text_schema(),
                "Status": formula_schema('prop("Type")'),
            },
        ),
        (
            "Good Habit",
            {
                "Name": title_schema(),
                "Stat": select_schema(DOMAIN_OPTIONS),
                "Domain": select_schema(DOMAIN_OPTIONS),
                "XP Reward": number_schema(),
                "EXP Earn": number_schema(),
                "Frequency": select_schema([("Daily", "green"), ("Weekly", "blue")]),
                "Active": checkbox_schema(),
                "Check-in Status": formula_schema('if(prop("Active"), "Ready", "Paused")'),
                "Heat Map": formula_schema('""'),
            },
        ),
        (
            "Bad Habit",
            {
                "Name": title_schema(),
                "Stat": select_schema(DOMAIN_OPTIONS),
                "Domain": select_schema(DOMAIN_OPTIONS),
                "HP Penalty": number_schema(),
                "HP Damage": number_schema(),
                "Severity": select_schema([("Low", "green"), ("Medium", "yellow"), ("High", "red")]),
                "Active": checkbox_schema(),
                "Check-in Status": formula_schema('if(prop("Active"), "Tracking", "Paused")'),
            },
        ),
        (
            "Skill/Area",
            {
                "Name": title_schema(),
                "Primary Stat": select_schema(DOMAIN_OPTIONS),
                "Stat": select_schema(DOMAIN_OPTIONS),
                "Description": rich_text_schema(),
                "Level Progress": formula_schema('prop("Name")'),
            },
        ),
        (
            "Streak Tracker",
            {
                "Name": title_schema(),
                "Domain": select_schema(DOMAIN_OPTIONS),
                "Current Streak": number_schema(),
                "Best Streak": number_schema(),
                "Streak Days": number_schema(),
                "Current Tier": select_schema(STREAK_TIER_OPTIONS),
                "Multiplier": number_schema(),
                "Last Completed": date_schema(),
            },
        ),
        (
            "Goal",
            {
                "Name": title_schema(),
                "Domain": select_schema(DOMAIN_OPTIONS),
                "XP Reward": number_schema(),
                "Coin Reward": number_schema(),
                "Status": status_schema(STATUS_OPTIONS),
                "Due Date": date_schema(),
            },
        ),
        (
            "Brain Dump",
            {
                "Name": title_schema(),
                "Domain": select_schema(DOMAIN_OPTIONS),
                "Status": status_schema(STATUS_OPTIONS),
                "Notes": rich_text_schema(),
            },
        ),
        (
            "To-do Difficulty",
            {
                "Name": title_schema(),
                "XP Reward": number_schema(),
                "Coin Reward": number_schema(),
                "Description": rich_text_schema(),
            },
        ),
        (
            "Market",
            {
                "Name": title_schema(),
                "Category": select_schema([("Consumable", "green"), ("Upgrade", "blue"), ("Reward", "yellow")]),
                "Price": number_schema(),
                "Stock": number_schema(),
                "Purchased": checkbox_schema(),
                "Redemption Date": date_schema(),
                "Description": rich_text_schema(),
                "T.Price": formula_schema('format(prop("Price")) + " Coins"'),
            },
        ),
        (
            "My Cart",
            {
                "Name": title_schema(),
                "Quantity": number_schema(),
                "Holding Coins": formula_schema('format(prop("Quantity"))'),
                "Message": formula_schema('prop("Name")'),
            },
        ),
        (
            "Hotel",
            {
                "Name": title_schema(),
                "Tier": select_schema(HOTEL_TIER_OPTIONS),
                "Price": number_schema(),
                "HP Recovery": number_schema(),
                "Details": formula_schema('prop("Name")'),
                "Color Bar": formula_schema('prop("Tier")'),
            },
        ),
        (
            "Black Market",
            {
                "Name": title_schema(),
                "Category": select_schema([("Recovery", "purple"), ("Shortcut", "orange"), ("Luxury", "red")]),
                "Price": number_schema(),
                "HP Cost": number_schema(),
                "Description": rich_text_schema(),
            },
        ),
        (
            "Overdraft Penalty",
            {
                "Name": title_schema(),
                "HP Delta": number_schema(),
                "HP Penalty": number_schema(),
                "Frequency": select_schema(OVERDRAFT_FREQUENCY_OPTIONS),
                "Last Check": date_schema(),
                "Reason": rich_text_schema(),
                "Active": checkbox_schema(),
            },
        ),
        (
            "Level Setting",
            {
                "Name": title_schema(),
                "Base XP": number_schema(),
                "Exponent": number_schema(),
                "Linear Mod": number_schema(),
            },
        ),
        (
            "Settings",
            {
                "Name": title_schema(),
                "Value": rich_text_schema(),
                "Type": select_schema([("number", "blue"), ("text", "gray"), ("json", "purple")]),
                "Description": rich_text_schema(),
            },
        ),
        (
            "Quests",
            {
                "Name": title_schema(),
                "Difficulty": select_schema([("Easy", "green"), ("Medium", "blue"), ("Hard", "orange"), ("Epic", "purple")]),
                "XP Reward": number_schema(),
                "Gold Reward": number_schema(),
                "Due Date": date_schema(),
                "Status": status_schema(STATUS_OPTIONS),
            },
        ),
        (
            "Daily Journal",
            {
                "Name": title_schema(),
                "Entry Date": date_schema(),
                "Reflection": rich_text_schema(),
                "Mood Summary": rich_text_schema(),
            },
        ),
        (
            "Mood",
            {
                "Name": title_schema(),
                "Intensity": number_schema(),
                "Notes": rich_text_schema(),
                "Logged At": date_schema(),
            },
        ),
        (
            "Onboarding Identity",
            {
                "Name": title_schema(),
                "Value": rich_text_schema(),
                "Prompt": rich_text_schema(),
                "Completed": checkbox_schema(),
            },
        ),
        (
            "Vision Board Items",
            {
                "Name": title_schema(),
                "Category": select_schema(
                    [
                        ("Health", "green"),
                        ("Career", "blue"),
                        ("Finance", "yellow"),
                        ("Relationships", "purple"),
                        ("Adventure", "orange"),
                        ("Learning", "red"),
                        ("Lifestyle", "gray"),
                        ("Legacy", "brown"),
                    ]
                ),
                "Description": rich_text_schema(),
                "Image": files_schema(),
                "Priority": select_schema([("P1", "red"), ("P2", "yellow"), ("P3", "gray")]),
                "Completed": checkbox_schema(),
            },
        ),
        (
            "Budget Categories",
            {
                "Name": title_schema(),
                "Monthly Budget": number_schema("dollar"),
                "Monthly Limit": number_schema("dollar"),
                "Type": select_schema([("Need", "green"), ("Want", "blue"), ("Saving", "yellow"), ("Debt", "red")]),
                "Notes": rich_text_schema(),
            },
        ),
        (
            "Expense Log",
            {
                "Name": title_schema(),
                "Amount": number_schema("dollar"),
                "Date": date_schema(),
                "Logged At": date_schema(),
                "Notes": rich_text_schema(),
            },
        ),
        (
            "Treasury",
            {
                "Name": title_schema(),
                "Balance": number_schema("dollar"),
                "Income": number_schema("dollar"),
                "Total Expenses": number_schema("dollar"),
                "Surplus": number_schema("dollar"),
                "Gold Earned": number_schema(),
                "WIS XP": number_schema(),
                "Breached Categories": number_schema(),
                "Notes": rich_text_schema(),
                "Updated At": {"type": "last_edited_time", "last_edited_time": {}},
            },
        ),
        (
            "Exercise Dictionary",
            {
                "Name": title_schema(),
                "Body Part": select_schema(
                    [
                        ("Chest", "red"),
                        ("Back", "blue"),
                        ("Legs", "green"),
                        ("Shoulders", "yellow"),
                        ("Arms", "purple"),
                        ("Core", "orange"),
                        ("Full Body", "gray"),
                        ("Cardio", "brown"),
                    ]
                ),
                "Equipment": select_schema(
                    [
                        ("Bodyweight", "green"),
                        ("Barbell", "red"),
                        ("Dumbbell", "blue"),
                        ("Machine", "yellow"),
                        ("Cable", "purple"),
                        ("Kettlebell", "orange"),
                        ("Cardio", "gray"),
                    ]
                ),
                "Primary Stat": select_schema(DOMAIN_OPTIONS),
                "Base XP Modifier": number_schema(),
                "Notes": rich_text_schema(),
            },
        ),
        (
            "Workout Sessions",
            {
                "Name": title_schema(),
                "Session Date": date_schema(),
                "Workout Date": date_schema(),
                "Duration Minutes": number_schema(),
                "Notes": rich_text_schema(),
            },
        ),
        (
            "Set Log",
            {
                "Name": title_schema(),
                "Weight": number_schema(),
                "Reps": number_schema(),
                "RPE": number_schema(),
                "Volume": formula_schema('prop("Weight") * prop("Reps")'),
                "Estimated 1RM": formula_schema('floor(prop("Weight") * (1 + prop("Reps") / 30))'),
                "Progressive Delta": number_schema(),
                "Session XP": number_schema(),
            },
        ),
        (
            "Meal Log",
            {
                "Name": title_schema(),
                "Date": date_schema(),
                "Logged At": date_schema(),
                "Calories": formula_schema('(prop("Protein") * 4) + (prop("Carbs") * 4) + (prop("Fat") * 9)'),
                "Protein": number_schema(),
                "Carbs": number_schema(),
                "Fat": number_schema(),
                "Notes": rich_text_schema(),
            },
        ),
        (
            "Ingredients Library",
            {
                "Name": title_schema(),
                "Calories": number_schema(),
                "Protein": number_schema(),
                "Carbs": number_schema(),
                "Fat": number_schema(),
                "Unit": rich_text_schema(),
            },
        ),
        (
            "Loot Box Inventory",
            {
                "Name": title_schema(),
                "Rarity": select_schema(RARITY_OPTIONS),
                "Value": number_schema(),
                "Claimed": checkbox_schema(),
            },
        ),
        (
            "Achievements",
            {
                "Name": title_schema(),
                "Category": select_schema(
                    [
                        ("Habits", "green"),
                        ("XP", "blue"),
                        ("Finance", "yellow"),
                        ("Fitness", "red"),
                        ("Nutrition", "orange"),
                        ("Social", "purple"),
                        ("Milestone", "brown"),
                    ]
                ),
                "Threshold": number_schema(),
                "Reward Coins": number_schema(),
                "Description": rich_text_schema(),
            },
        ),
        (
            "Player Achievements",
            {
                "Name": title_schema(),
                "Earned At": date_schema(),
                "Claimed": checkbox_schema(),
            },
        ),
        (
            "Daily Snapshots",
            {
                "Name": title_schema(),
                "Snapshot Date": date_schema(),
                "HP": number_schema(),
                "Coins": number_schema(),
                "Gold": number_schema(),
                "Total XP": number_schema(),
            },
        ),
    ]
)


RELATION_BLUEPRINTS = {
    "Activity Log": {
        "Character": ("Character", relation_schema),
        "Good Habit": ("Good Habit", relation_schema),
        "Bad Habit": ("Bad Habit", relation_schema),
        "Goal": ("Goal", relation_schema),
        "Brain Dump": ("Brain Dump", relation_schema),
        "Quest": ("Quests", relation_schema),
    },
    "Good Habit": {
        "Character": ("Character", relation_schema),
        "Activity Entries": ("Activity Log", relation_schema),
        "Current Streak": ("Streak Tracker", relation_schema),
        "Entries Count": ("Activity Entries", lambda _db_id: rollup_schema("Activity Entries", "Name")),
    },
    "Bad Habit": {
        "Character": ("Character", relation_schema),
        "Activity Entries": ("Activity Log", relation_schema),
        "Entries Count": ("Activity Entries", lambda _db_id: rollup_schema("Activity Entries", "Name")),
    },
    "Skill/Area": {
        "Character": ("Character", relation_schema),
        "Related Goals": ("Goal", relation_schema),
    },
    "Streak Tracker": {
        "Habit": ("Good Habit", relation_schema),
        "Good Habit": ("Good Habit", relation_schema),
        "Bad Habit": ("Bad Habit", relation_schema),
    },
    "Goal": {
        "Character": ("Character", relation_schema),
        "Activity Entries": ("Activity Log", relation_schema),
        "Related Skills": ("Skill/Area", relation_schema),
    },
    "Brain Dump": {
        "Character": ("Character", relation_schema),
        "Difficulty": ("To-do Difficulty", relation_schema),
        "Activity Entries": ("Activity Log", relation_schema),
        "Related Skills": ("Skill/Area", relation_schema),
    },
    "Market": {
        "Character": ("Character", relation_schema),
        "Cart Items": ("My Cart", relation_schema),
    },
    "My Cart": {
        "Character": ("Character", relation_schema),
        "Market Item": ("Market", relation_schema),
    },
    "Hotel": {
        "Character": ("Character", relation_schema),
        "Activity Entries": ("Activity Log", relation_schema),
    },
    "Black Market": {
        "Character": ("Character", relation_schema),
        "Activity Entries": ("Activity Log", relation_schema),
    },
    "Overdraft Penalty": {
        "Character": ("Character", relation_schema),
        "Activity Entries": ("Activity Log", relation_schema),
    },
    "Settings": {
        "Level Settings": ("Level Setting", relation_schema),
    },
    "Quests": {
        "Character": ("Character", relation_schema),
        "Skill": ("Skill/Area", relation_schema),
        "Activity Entries": ("Activity Log", relation_schema),
    },
    "Daily Journal": {
        "Character": ("Character", relation_schema),
        "Mood": ("Mood", relation_schema),
    },
    "Mood": {
        "Character": ("Character", relation_schema),
        "Journal Entries": ("Daily Journal", relation_schema),
    },
    "Vision Board Items": {
        "Character": ("Character", relation_schema),
    },
    "Budget Categories": {
        "Character": ("Character", relation_schema),
        "Expenses": ("Expense Log", relation_schema),
    },
    "Expense Log": {
        "Character": ("Character", relation_schema),
        "Category": ("Budget Categories", relation_schema),
        "Treasury": ("Treasury", relation_schema),
    },
    "Treasury": {
        "Character": ("Character", relation_schema),
        "Expenses": ("Expense Log", relation_schema),
    },
    "Exercise Dictionary": {
        "Sets": ("Set Log", relation_schema),
    },
    "Workout Sessions": {
        "Sets": ("Set Log", relation_schema),
        "Character": ("Character", relation_schema),
    },
    "Set Log": {
        "Workout Session": ("Workout Sessions", relation_schema),
        "Exercise": ("Exercise Dictionary", relation_schema),
    },
    "Meal Log": {
        "Ingredients": ("Ingredients Library", relation_schema),
        "Character": ("Character", relation_schema),
    },
    "Ingredients Library": {
        "Meals": ("Meal Log", relation_schema),
    },
    "Loot Box Inventory": {
        "Character": ("Character", relation_schema),
    },
    "Achievements": {
        "Player Unlocks": ("Player Achievements", relation_schema),
    },
    "Player Achievements": {
        "Character": ("Character", relation_schema),
        "Achievement": ("Achievements", relation_schema),
    },
    "Daily Snapshots": {
        "Character": ("Character", relation_schema),
    },
}


BUTTON_BLUEPRINTS = {
    "Good Habit": ["Check-in"],
    "Bad Habit": ["Crap, I did..."],
    "Goal": ["COMPLETE"],
    "Brain Dump": ["COMPLETED", "REDO"],
    "Market": ["Add to Cart", "Buy"],
    "Hotel": ["HOTEL CHECK-IN"],
    "Black Market": ["Buy"],
}


def _db_ids_path(path=None):
    return path or os.path.join(os.path.dirname(_TOOLS_DIR), DB_IDS_FILENAME)


def load_db_ids(path=None):
    file_path = _db_ids_path(path)
    if not os.path.exists(file_path):
        return {}
    with open(file_path) as handle:
        return json.load(handle)


def save_db_ids(db_ids, path=None):
    file_path = _db_ids_path(path)
    with open(file_path, "w") as handle:
        json.dump(db_ids, handle, indent=2, sort_keys=True)


def _title_payload(name):
    return [{"type": "text", "text": {"content": name}}]


def _result_title(result):
    title = notion_api.get_page_title(result)
    if title:
        return title
    return ""


def _result_database_id(result):
    """Normalize search results across old database objects and new data source objects."""
    if result.get("object") == "database":
        return result.get("id")

    parent = result.get("parent", {})
    if isinstance(parent, dict) and parent.get("database_id"):
        return parent["database_id"]

    database_parent = result.get("database_parent", {})
    if isinstance(database_parent, dict) and database_parent.get("database_id"):
        return database_parent["database_id"]

    return result.get("id")


def find_existing_database(client, database_name, parent_page_id):
    """Find an existing database by title using Notion search."""
    filter_obj = {"property": "object", "value": "database"}
    search_result = notion_api.search_pages(client=client, query=database_name, filter_obj=filter_obj)
    for result in search_result.get("results", []):
        if result.get("object") not in {"database", "data_source"}:
            continue
        if _result_title(result) == database_name:
            database_id = _result_database_id(result)
            if database_id:
                normalized = dict(result)
                normalized["id"] = database_id
                return normalized
    return None


def create_all_databases(client, parent_page_id, db_ids_path=None):
    """Create all phase-1 databases and link their relations."""
    if not parent_page_id:
        raise ValueError("parent_page_id is required")

    db_ids = load_db_ids(db_ids_path)
    created = []
    skipped = []

    for database_name, properties in DATABASE_SCHEMAS.items():
        existing_id = db_ids.get(database_name)
        if existing_id:
            try:
                notion_api.get_database(client=client, db_id=existing_id)
                skipped.append(database_name)
                continue
            except Exception as exc:
                logger.warning(f"Stored id for '{database_name}' is invalid ({exc}); falling back to title match.")

        found = find_existing_database(client, database_name, parent_page_id)
        if found:
            db_ids[database_name] = found["id"]
            save_db_ids(db_ids, db_ids_path)
            skipped.append(database_name)
            continue

        created_db = notion_api.create_database(
            client=client,
            parent={"type": "page_id", "page_id": parent_page_id},
            title=_title_payload(database_name),
            properties=properties,
        )
        db_ids[database_name] = created_db["id"]
        save_db_ids(db_ids, db_ids_path)
        created.append(database_name)

    relation_result = link_all_relations(client, db_ids)
    return {
        "created": created,
        "skipped": skipped,
        "relations_linked": relation_result["relations_linked"],
        "buttons_added": relation_result["buttons_added"],
    }


def link_all_relations(client, db_ids):
    """Add relation, rollup, and best-effort button properties to existing databases."""
    relations_linked = 0
    buttons_added = 0

    for database_name, blueprints in RELATION_BLUEPRINTS.items():
        if database_name not in db_ids:
            continue
        properties = {}
        linked_here = 0
        for property_name, (target_name, builder) in blueprints.items():
            if builder is relation_schema:
                target_id = db_ids.get(target_name)
                if not target_id:
                    logger.warning(f"Skipping relation '{property_name}' on '{database_name}' because '{target_name}' is missing.")
                    continue
                properties[property_name] = builder(target_id)
                linked_here += 1
            else:
                properties[property_name] = builder(target_name)
                linked_here += 1

        if properties:
            notion_api.update_database(client=client, db_id=db_ids[database_name], properties=properties)
            relations_linked += linked_here

    for database_name, button_names in BUTTON_BLUEPRINTS.items():
        if database_name not in db_ids:
            continue
        properties = {name: {"type": "button", "button": {}} for name in button_names}
        try:
            notion_api.update_database(client=client, db_id=db_ids[database_name], properties=properties)
            buttons_added += len(button_names)
        except Exception as exc:
            logger.warning(
                f"Skipping button configuration on '{database_name}': {exc}. "
                "The current public Notion schema docs do not document button properties."
            )

    return {"relations_linked": relations_linked, "buttons_added": buttons_added}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create all Gamify Life Notion databases.")
    parser.add_argument("--parent-page-id", default=os.getenv("NOTION_PARENT_PAGE_ID"))
    parser.add_argument("--db-ids-path", default=None)
    args = parser.parse_args(argv)

    if not args.parent_page_id:
        parser.error("--parent-page-id is required (or set NOTION_PARENT_PAGE_ID)")

    client = notion_api.get_client()
    result = create_all_databases(client=client, parent_page_id=args.parent_page_id, db_ids_path=args.db_ids_path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
