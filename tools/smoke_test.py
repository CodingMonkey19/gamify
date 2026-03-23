"""
Smoke Test — Pre-flight checks for environment and Notion connectivity.
Validates required env vars, API reachability, and warns about optional config.

Usage:
    python -m tools.smoke_test [--character-id <UUID>]

Exit Codes:
    0   All checks passed
    1   Required check failed
"""
import argparse
import os
import sys

from notion_client import Client

from .logger import get_logger

logger = get_logger(__name__)


class SmokeTestError(Exception):
    """Raised when a required smoke test check fails."""
    pass


def run(character_id=None):
    """Run all smoke test checks.

    Required checks (fail = SmokeTestError):
        - NOTION_TOKEN env var exists and is non-empty
        - CHARACTER_ID env var or character_id argument provided
        - Notion API reachable (notion.users.me() succeeds)

    Optional checks (warn only):
        - OPENAI_API_KEY present
        - NOTION_PARENT_PAGE_ID present

    Returns:
        str: The validated character_id

    Raises:
        SmokeTestError: If any required check fails
    """
    # --- Required: NOTION_TOKEN ---
    notion_token = os.environ.get("NOTION_TOKEN", "").strip()
    if not notion_token:
        raise SmokeTestError("NOTION_TOKEN env var is missing or empty")
    logger.info("NOTION_TOKEN: present")

    # --- Required: CHARACTER_ID ---
    resolved_character_id = character_id or os.environ.get("CHARACTER_ID", "").strip()
    if not resolved_character_id:
        raise SmokeTestError(
            "CHARACTER_ID not provided. Pass --character-id or set CHARACTER_ID env var"
        )
    logger.info(f"CHARACTER_ID: {resolved_character_id}")

    # --- Required: Notion API reachable ---
    try:
        notion = Client(auth=notion_token)
        user = notion.users.me()
        logger.info(f"Notion API: reachable (user: {user.get('name', 'unknown')})")
    except Exception as e:
        raise SmokeTestError(f"Notion API unreachable: {e}")

    # --- Optional: OPENAI_API_KEY ---
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        logger.warning("OPENAI_API_KEY not set — AI features will be unavailable")

    # --- Optional: NOTION_PARENT_PAGE_ID ---
    if not os.environ.get("NOTION_PARENT_PAGE_ID", "").strip():
        logger.warning("NOTION_PARENT_PAGE_ID not set — page creation may be limited")

    logger.info("All smoke test checks passed")
    return resolved_character_id


def main():
    parser = argparse.ArgumentParser(description="Pre-flight environment and connectivity checks")
    parser.add_argument("--character-id", default=None, help="Notion Character page ID")
    args = parser.parse_args()

    try:
        character_id = run(character_id=args.character_id)
        print(f"All checks passed. Character ID: {character_id}")
        sys.exit(0)
    except SmokeTestError as e:
        print(f"SMOKE TEST FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
