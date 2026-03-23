"""
Dashboard Setup — Programmatic Notion Dashboard page builder.

Creates a Daily Dashboard page with 7 panels (Character Card, Growth, Battle,
Quest Board, Tasks, Journal, Stats) linked to the appropriate Notion databases.

Usage:
    python -m tools.dashboard_setup --character-id <ID> --parent-page-id <ID>

Exit Codes:
    0  Success
    1  Environment validation failure
    2  Character not found
"""
import argparse
import os
import sys

from notion_client import Client

from .logger import get_logger

logger = get_logger(__name__)

# --- Asset paths ---
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
DASHBOARD_COVER_PATH = os.path.join(ASSETS_DIR, "backgrounds", "COV-009.png")

# --- DB IDs from env (with hardcoded fallbacks from verified workspace) ---
GOOD_HABIT_DB_ID       = os.environ.get("GOOD_HABIT_DB_ID",       "5dc9eb37-5e0b-4537-bae5-b7a948251cdc")
BAD_HABIT_DB_ID        = os.environ.get("BAD_HABIT_DB_ID",        "f2d3667c-cd5d-46d3-a73b-42db195db1b4")
QUESTS_DB_ID           = os.environ.get("QUESTS_DB_ID",           "1eba33ab-6878-4e55-b07a-cb551d3af2cd")
BRAIN_DUMP_DB_ID       = os.environ.get("BRAIN_DUMP_DB_ID",       "172c204a-c0b6-43da-aa5a-2240aca72fef")
JOURNAL_DB_ID          = os.environ.get("JOURNAL_DB_ID",          "6f03d04f-4afd-4797-8e4a-911991b27bc4")
DAILY_SNAPSHOTS_DB_ID  = os.environ.get("DAILY_SNAPSHOTS_DB_ID",  "10168a1e-e30c-4907-8871-65519cec7abe")

REQUIRED_ENV_VARS = [
    "NOTION_TOKEN",
    "GOOD_HABIT_DB_ID",
    "BAD_HABIT_DB_ID",
    "QUESTS_DB_ID",
    "BRAIN_DUMP_DB_ID",
    "JOURNAL_DB_ID",
    "DAILY_SNAPSHOTS_DB_ID",
]

DASHBOARD_TITLE = "Daily Dashboard"


# ---------------------------------------------------------------------------
# Env validation
# ---------------------------------------------------------------------------

def validate_env() -> bool:
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
# Character data reader
# ---------------------------------------------------------------------------

def _read_character(notion: Client, character_id: str) -> dict | None:
    """Read character stats from Character DB. Returns dict or None if not found."""
    try:
        page = notion.pages.retrieve(page_id=character_id)
        props = page.get("properties", {})

        def _title(p):
            items = p.get("title", [])
            return items[0]["plain_text"] if items else ""

        def _num(p):
            return p.get("number") or 0

        def _sel(p):
            s = p.get("select")
            return s["name"] if s else ""

        def _url(p):
            return p.get("url") or ""

        return {
            "name": _title(props.get("Name", {})),
            "level": _num(props.get("Player Level", {})),
            "rank": _sel(props.get("Current Rank", {})),
            "hp": _num(props.get("Current HP", {})),
            "coins": _num(props.get("Current Coins", {})),
            "gold": _num(props.get("Gold", {})),
            "avatar_url": _url(props.get("Avatar URL", {})),
            "chart_url": _url(props.get("Radar Chart URL", {})),
        }
    except Exception as e:
        logger.error(f"Failed to read character {character_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------

def _text_block(content: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
    }


def _heading_block(text: str, level: int = 2) -> dict:
    block_type = f"heading_{level}"
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _callout_block(title: str, body_lines: list, icon_emoji: str = "🧙") -> dict:
    rich_text = [{"type": "text", "text": {"content": title + "\n"}}]
    for line in body_lines:
        rich_text.append({"type": "text", "text": {"content": line + "\n"}})
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": rich_text,
            "icon": {"type": "emoji", "emoji": icon_emoji},
            "color": "blue_background",
        },
    }


def _linked_db_block(db_id: str) -> dict:
    return {
        "object": "block",
        "type": "child_database",
        "child_database": {"title": ""},
    }


def _image_block(url: str) -> dict:
    return {
        "object": "block",
        "type": "image",
        "image": {"type": "external", "external": {"url": url}},
    }


# ---------------------------------------------------------------------------
# Character Card builder
# ---------------------------------------------------------------------------

def _build_character_card(char: dict) -> list:
    """Return list of blocks for the Character Card panel."""
    body_lines = [
        f"Level: {char['level']}  |  Rank: {char['rank']}",
        f"HP: {char['hp']}  |  Coins: {char['coins']}  |  Gold: {char['gold']}",
    ]
    blocks = [_callout_block(char["name"], body_lines, icon_emoji="⚔️")]
    if char.get("avatar_url"):
        blocks.append(_image_block(char["avatar_url"]))
    if char.get("chart_url"):
        blocks.append(_image_block(char["chart_url"]))
    return blocks


# ---------------------------------------------------------------------------
# Full page block list
# ---------------------------------------------------------------------------

def _build_dashboard_blocks(char: dict) -> list:
    """Build the full list of child blocks for the dashboard page (7 panels)."""
    panels = [
        # Panel 1: Character Card
        _heading_block("Character Card", level=1),
        *_build_character_card(char),
        _divider_block(),

        # Panel 2: Growth (Good Habits)
        _heading_block("Growth", level=2),
        _text_block("Filter by Character to see your active good habits. Check in daily."),
        _divider_block(),

        # Panel 3: Battle (Bad Habits)
        _heading_block("Battle", level=2),
        _text_block("Filter by Character to see your bad habit log. Log each occurrence."),
        _divider_block(),

        # Panel 4: Quest Board
        _heading_block("Quest Board", level=2),
        _text_block("Filter by Status = Active to see your open quests."),
        _divider_block(),

        # Panel 5: Tasks (Brain Dump)
        _heading_block("Tasks", level=2),
        _text_block("Your task backlog and brain dump. Filter by Priority or Status."),
        _divider_block(),

        # Panel 6: Journal
        _heading_block("Journal", level=2),
        _text_block("Daily journal entries. Create a new entry each day."),
        _divider_block(),

        # Panel 7: Stats (Daily Snapshots)
        _heading_block("Stats", level=2),
        _text_block("Historical stat snapshots. Filter by Character to view your progress over time."),
    ]
    return panels


# ---------------------------------------------------------------------------
# Cover image upload
# ---------------------------------------------------------------------------

def _upload_cover_image(image_path: str) -> str | None:
    """Upload a local image to Cloudinary and return the URL, or None on failure."""
    try:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
            api_key=os.environ.get("CLOUDINARY_API_KEY"),
            api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
        )
        result = cloudinary.uploader.upload(
            image_path,
            folder="gamify/covers",
            public_id=os.path.splitext(os.path.basename(image_path))[0],
            overwrite=True,
            resource_type="image",
        )
        url = result.get("secure_url")
        logger.info(f"Cover uploaded: {url}")
        return url
    except Exception as e:
        logger.warning(f"Cover upload skipped (Cloudinary not configured): {e}")
        return None


# ---------------------------------------------------------------------------
# Idempotency — find existing dashboard
# ---------------------------------------------------------------------------

def _find_existing_dashboard(notion: Client, parent_page_id: str) -> str | None:
    """Search for existing 'Daily Dashboard' page under parent. Returns page ID or None."""
    try:
        response = notion.blocks.children.list(block_id=parent_page_id)
        for block in response.get("results", []):
            if block.get("type") == "child_page":
                title = block.get("child_page", {}).get("title", "")
                if title == DASHBOARD_TITLE:
                    return block["id"]
    except Exception as e:
        logger.warning(f"Could not scan parent page for existing dashboard: {e}")
    return None


def _clear_page_blocks(notion: Client, page_id: str) -> None:
    """Delete all child blocks from a page."""
    try:
        response = notion.blocks.children.list(block_id=page_id)
        for block in response.get("results", []):
            notion.blocks.delete(block_id=block["id"])
    except Exception as e:
        logger.warning(f"Could not clear existing dashboard blocks: {e}")


# ---------------------------------------------------------------------------
# Main create_dashboard function
# ---------------------------------------------------------------------------

def create_dashboard(notion: Client, character_id: str, parent_page_id: str) -> dict:
    """Create or update the Daily Dashboard page.

    Returns:
        {"page_id": str, "url": str, "action": "created"|"updated"}
    """
    char = _read_character(notion, character_id)
    if char is None:
        raise ValueError(f"Character {character_id} not found")

    blocks = _build_dashboard_blocks(char)

    # Upload cover image (COV-009.png) if available
    cover = None
    if os.path.exists(DASHBOARD_COVER_PATH):
        cover_url = _upload_cover_image(DASHBOARD_COVER_PATH)
        if cover_url:
            cover = {"type": "external", "external": {"url": cover_url}}

    # Check for existing dashboard
    existing_id = _find_existing_dashboard(notion, parent_page_id)

    if existing_id:
        logger.info(f"Existing dashboard found ({existing_id}) — updating")
        _clear_page_blocks(notion, existing_id)
        update_kwargs = {"page_id": existing_id}
        if cover:
            update_kwargs["cover"] = cover
        notion.pages.update(**update_kwargs)
        notion.blocks.children.append(block_id=existing_id, children=blocks)
        page_url = f"https://notion.so/{existing_id.replace('-', '')}"
        logger.info("Dashboard updated")
        return {"page_id": existing_id, "url": page_url, "action": "updated"}
    else:
        logger.info("Creating new dashboard page")
        create_kwargs = {
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": {"title": [{"text": {"content": DASHBOARD_TITLE}}]},
            },
            "children": blocks,
        }
        if cover:
            create_kwargs["cover"] = cover
        page = notion.pages.create(**create_kwargs)
        page_id = page["id"]
        page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")
        logger.info(f"Dashboard created: {page_url}")
        return {"page_id": page_id, "url": page_url, "action": "created"}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Create or update the Daily Dashboard page in Notion")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    parser.add_argument("--parent-page-id", required=True, help="Notion page ID to create dashboard under")
    args = parser.parse_args()

    if not validate_env():
        sys.exit(1)

    notion = _get_notion_client()

    try:
        result = create_dashboard(notion, args.character_id, args.parent_page_id)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        logger.error(f"Dashboard setup failed: {e}")
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    action = result["action"].capitalize()
    print(f"Dashboard {result['action']}: {result['url']}")
    print("Panels: Character Card, Growth, Battle, Quest Board, Tasks, Journal, Stats")
    print("Note: Apply filters manually for optimal view (see workflows/onboarding.md)")


if __name__ == "__main__":
    main()
