"""
Onboarding — Interactive CLI to create a character and auto-generate the dashboard.

Creates a Character row, Onboarding Identity rows, default Good/Bad Habits,
Vision Board entries, and a Daily Dashboard page in one command.

Usage:
    python -m tools.onboarding --parent-page-id <NOTION_PAGE_ID>

Exit Codes:
    0  Success
    1  Environment validation failure
    2  User cancelled (existing character declined)
"""
import argparse
import os
import sys

from notion_client import Client

from .config import (
    CHARACTER_CLASSES,
    DEFAULT_BAD_HABITS,
    DEFAULT_GOOD_HABITS,
    DEFAULT_HABIT_XP,
    DEFAULT_BAD_HABIT_HP,
    STARTING_HP,
    VISION_BOARD_CATEGORIES,
)
from .logger import get_logger

logger = get_logger(__name__)

# --- DB IDs ---
CHARACTER_DB_ID        = os.environ.get("CHARACTER_DB_ID",        "f814ec57-8879-482b-81cb-e68104d252c8")
GOOD_HABIT_DB_ID       = os.environ.get("GOOD_HABIT_DB_ID",       "5dc9eb37-5e0b-4537-bae5-b7a948251cdc")
BAD_HABIT_DB_ID        = os.environ.get("BAD_HABIT_DB_ID",        "f2d3667c-cd5d-46d3-a73b-42db195db1b4")
VISION_BOARD_DB_ID     = os.environ.get("VISION_BOARD_DB_ID",     "3000ccc4-2e76-41d9-b4be-43107dca120b")
ONBOARDING_IDENTITY_DB_ID = os.environ.get("ONBOARDING_IDENTITY_DB_ID", "79bc2de7-8e94-4613-8d64-9b52d82523e5")

REQUIRED_ENV_VARS = [
    "NOTION_TOKEN",
    "CHARACTER_DB_ID",
    "GOOD_HABIT_DB_ID",
    "BAD_HABIT_DB_ID",
    "VISION_BOARD_DB_ID",
    "ONBOARDING_IDENTITY_DB_ID",
]


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def prompt_required(question: str) -> str:
    """Prompt until user enters a non-empty response."""
    while True:
        answer = input(question).strip()
        if answer:
            return answer
        print("  (This field is required — please enter a value)")


def prompt_choice(question: str, options: list) -> str:
    """Display numbered options and validate numeric selection. Returns chosen option."""
    print(question)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = input("Enter number: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        print(f"  (Please enter a number between 1 and {len(options)})")


def prompt_multiline(question: str) -> list:
    """Collect lines until user enters a blank line. Returns list of non-empty strings."""
    print(question + " (blank line to finish)")
    lines = []
    while True:
        line = input("  > ").strip()
        if not line:
            break
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Env validation
# ---------------------------------------------------------------------------

def validate_env() -> bool:
    """Check all required env vars are present. Returns True if valid."""
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return False
    return True


# ---------------------------------------------------------------------------
# Notion client
# ---------------------------------------------------------------------------

def _get_notion_client() -> Client:
    return Client(auth=os.environ["NOTION_TOKEN"])


# ---------------------------------------------------------------------------
# Partial state detection
# ---------------------------------------------------------------------------

def _check_existing_character(notion: Client, parent_page_id: str) -> str | None:
    """Return character_id if a character already exists under parent_page_id, else None."""
    try:
        response = notion.databases.query(
            database_id=CHARACTER_DB_ID,
        )
        results = response.get("results", [])
        if results:
            return results[0]["id"]
    except Exception as e:
        logger.warning(f"Could not check for existing character: {e}")
    return None


def _count_existing(notion: Client, db_id: str, character_id: str, relation_field: str = "Character") -> int:
    """Count rows in db_id that are related to character_id."""
    try:
        response = notion.databases.query(
            database_id=db_id,
            filter={"property": relation_field, "relation": {"contains": character_id}},
        )
        return len(response.get("results", []))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Step 1: Create character row
# ---------------------------------------------------------------------------

def setup_character(notion: Client, parent_page_id: str, name: str, char_class: str,
                    master_objective: str, death_penalty: str) -> str:
    """Create the Character row in Notion and return its page ID."""
    properties = {
        "Name": {"title": [{"text": {"content": name}}]},
        "Class": {"select": {"name": char_class}},
        "Master Objective": {"rich_text": [{"text": {"content": master_objective}}]},
        "Death Penalty": {"rich_text": [{"text": {"content": death_penalty}}]},
        "Player Level": {"number": 1},
        "Current HP": {"number": STARTING_HP},
        "Max HP": {"number": STARTING_HP},
        "Current Coins": {"number": 0},
        "Gold": {"number": 0},
        "Current Rank": {"select": {"name": "Peasant"}},
        "STR XP": {"number": 0},
        "INT XP": {"number": 0},
        "WIS XP": {"number": 0},
        "VIT XP": {"number": 0},
        "CHA XP": {"number": 0},
        "Total XP": {"number": 0},
        "Pity Counter": {"number": 0},
        "Death Count": {"number": 0},
    }

    page = notion.pages.create(
        parent={"database_id": CHARACTER_DB_ID},
        properties=properties,
    )
    character_id = page["id"]
    logger.info(f"Character created: {name} ({char_class}) — ID: {character_id}")
    return character_id


# ---------------------------------------------------------------------------
# Step 2: Onboarding Identity rows
# ---------------------------------------------------------------------------

def setup_identity_rows(notion: Client, character_id: str,
                        strengths: list, weaknesses: list, objectives: list) -> int:
    """Create identity rows in Onboarding Identity DB. Returns count created."""
    entries = (
        [("Strength", s) for s in strengths]
        + [("Weakness", w) for w in weaknesses]
        + [("Minor Objective", o) for o in objectives]
    )

    created = 0
    for entry_type, text in entries:
        try:
            notion.pages.create(
                parent={"database_id": ONBOARDING_IDENTITY_DB_ID},
                properties={
                    "Name": {"title": [{"text": {"content": f"{entry_type}: {text}"}}]},
                    "Type": {"select": {"name": entry_type}},
                    "Entry": {"rich_text": [{"text": {"content": text}}]},
                    "Character": {"relation": [{"id": character_id}]},
                },
            )
            created += 1
        except Exception as e:
            logger.error(f"Failed to create identity row '{entry_type}: {text}': {e}")

    logger.info(f"Identity rows created: {created}")
    return created


# ---------------------------------------------------------------------------
# Step 3: Default habits
# ---------------------------------------------------------------------------

def setup_default_habits(notion: Client, character_id: str) -> dict:
    """Create 5 good habits and 3 bad habits linked to character. Returns counts."""
    good_created = 0
    for habit_name, stat in DEFAULT_GOOD_HABITS.items():
        try:
            notion.pages.create(
                parent={"database_id": GOOD_HABIT_DB_ID},
                properties={
                    "Name": {"title": [{"text": {"content": habit_name}}]},
                    "Stat": {"select": {"name": stat}},
                    "XP Reward": {"number": DEFAULT_HABIT_XP},
                    "Character": {"relation": [{"id": character_id}]},
                },
            )
            good_created += 1
        except Exception as e:
            logger.error(f"Failed to create good habit '{habit_name}': {e}")

    bad_created = 0
    for habit_name, hp_penalty in DEFAULT_BAD_HABITS.items():
        try:
            notion.pages.create(
                parent={"database_id": BAD_HABIT_DB_ID},
                properties={
                    "Name": {"title": [{"text": {"content": habit_name}}]},
                    "HP Penalty": {"number": hp_penalty},
                    "Character": {"relation": [{"id": character_id}]},
                },
            )
            bad_created += 1
        except Exception as e:
            logger.error(f"Failed to create bad habit '{habit_name}': {e}")

    logger.info(f"Habits created: {good_created} good, {bad_created} bad")
    return {"good": good_created, "bad": bad_created}


# ---------------------------------------------------------------------------
# Step 4: Vision Board
# ---------------------------------------------------------------------------

def setup_vision_board(notion: Client, character_id: str) -> int:
    """Create 8 Vision Board category entries. Returns count created."""
    created = 0
    for category in VISION_BOARD_CATEGORIES:
        try:
            notion.pages.create(
                parent={"database_id": VISION_BOARD_DB_ID},
                properties={
                    "Name": {"title": [{"text": {"content": category}}]},
                    "Category": {"select": {"name": category}},
                    "Character": {"relation": [{"id": character_id}]},
                },
            )
            created += 1
        except Exception as e:
            logger.error(f"Failed to create vision board entry '{category}': {e}")

    logger.info(f"Vision board entries created: {created}")
    return created


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Create a new character and set up the daily dashboard")
    parser.add_argument("--parent-page-id", required=True, help="Notion page ID to create character under")
    args = parser.parse_args()

    if not validate_env():
        sys.exit(1)

    notion = _get_notion_client()

    # --- Check for existing character ---
    existing_id = _check_existing_character(notion, args.parent_page_id)
    if existing_id:
        print(f"\nWARNING: A character already exists (ID: {existing_id}).")
        confirm = input("Do you want to proceed anyway and create another character? (yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            print("Onboarding cancelled.")
            sys.exit(2)

    print("\n" + "=" * 50)
    print(" Welcome to Gamify Your Life — Character Creation")
    print("=" * 50 + "\n")

    # --- Collect inputs ---
    name = prompt_required("Character Name: ")
    char_class = prompt_choice("\nChoose your Class:", CHARACTER_CLASSES)
    master_objective = prompt_required("\nMaster Objective (your ultimate life goal): ")
    minor_objectives = prompt_multiline("\nMinor Objectives (supporting goals, optional):")
    death_penalty = prompt_required("\nDeath Penalty (what happens if HP reaches 0?): ")
    strengths = prompt_multiline("\nYour Strengths (at least 1 required):")
    while not strengths:
        print("  (At least one strength is required)")
        strengths = prompt_multiline("\nYour Strengths:")
    weaknesses = prompt_multiline("\nYour Weaknesses (at least 1 required):")
    while not weaknesses:
        print("  (At least one weakness is required)")
        weaknesses = prompt_multiline("\nYour Weaknesses:")

    print("\n[1/5] Creating character...")
    character_id = setup_character(notion, args.parent_page_id, name, char_class, master_objective, death_penalty)

    print("[2/5] Creating identity rows...")
    identity_count = setup_identity_rows(notion, character_id, strengths, weaknesses, minor_objectives)

    print("[3/5] Creating default habits...")
    habit_counts = setup_default_habits(notion, character_id)

    print("[4/5] Creating vision board...")
    vb_count = setup_vision_board(notion, character_id)

    print("[4.5/5] Generating avatar and radar chart...")
    try:
        from .avatar_renderer import update_character_avatar
        update_character_avatar(character_id)
        print("  Avatar generated (peasant frame applied)")
    except Exception as e:
        logger.warning(f"Avatar generation skipped: {e}")
        print(f"  (Avatar generation skipped — run avatar_renderer.py manually)")

    try:
        from .chart_renderer import update_character_chart
        update_character_chart(character_id)
        print("  Radar chart generated")
    except Exception as e:
        logger.warning(f"Radar chart generation skipped: {e}")
        print(f"  (Radar chart generation skipped — run chart_renderer.py manually)")

    print("[5/5] Creating dashboard (with cover image)...")
    dashboard_url = "N/A"
    try:
        from . import dashboard_setup
        dashboard_result = dashboard_setup.create_dashboard(notion, character_id, args.parent_page_id)
        dashboard_url = dashboard_result.get("url", "N/A")
    except Exception as e:
        logger.error(f"Dashboard creation failed: {e}")
        print(f"  (Dashboard creation failed: {e} — run dashboard_setup.py manually)")

    # --- Summary ---
    summary = f"""
{'=' * 40}
 Character Created
{'=' * 40}
Name:          {name}
Class:         {char_class}
Character ID:  {character_id}
Dashboard:     {dashboard_url}

Records created:
  ✓ Character row (Level 1, HP {STARTING_HP}, Peasant)
  ✓ Identity rows ({identity_count} entries)
  ✓ Good habits ({habit_counts['good']})
  ✓ Bad habits ({habit_counts['bad']})
  ✓ Vision Board ({vb_count} categories)
  ✓ Dashboard (7 panels)
{'=' * 40}
"""
    print(summary)
    logger.info(summary)


if __name__ == "__main__":
    main()
