"""
Rank Engine — Determines player rank tier from Total XP (high-water mark).
Triggers avatar re-rendering on rank-up.

Usage:
    python -m tools.rank_engine --character-id <ID>
"""
import argparse
import sys

from .config import RANK_THRESHOLDS, get_config
from .logger import get_logger

logger = get_logger(__name__)

# Ordered tier list for comparison (lowest → highest)
RANK_ORDER = ["Peasant", "Squire", "Knight", "Champion", "Hero", "Legend", "Mythic"]


def get_rank_from_xp(total_xp: int) -> str:
    """Determine rank tier from Total XP using RANK_THRESHOLDS from config.
    Finds the highest threshold <= total_xp.
    Returns: rank name (e.g., 'Peasant', 'Squire', 'Knight', etc.)
    """
    config = get_config()
    thresholds = config.get("RANK_THRESHOLDS", RANK_THRESHOLDS)

    # Sort thresholds descending to find the highest one <= total_xp
    rank = "Peasant"
    for threshold in sorted(thresholds.keys(), reverse=True):
        threshold_int = int(threshold)
        if total_xp >= threshold_int:
            rank = thresholds[threshold]
            break

    return rank


def _rank_tier(rank_name: str) -> int:
    """Return numeric tier index for a rank name (0=Peasant, 6=Mythic)."""
    try:
        return RANK_ORDER.index(rank_name)
    except ValueError:
        logger.warning(f"Unknown rank '{rank_name}', treating as Peasant (tier 0)")
        return 0


def check_rank_up(character_id: str) -> dict:
    """Check if character has earned a rank-up (high-water mark).
    1. Read Total XP and Current Rank from Character DB
    2. Calculate rank from Total XP
    3. Compare: if calculated rank is higher tier than current → rank-up
    4. If rank-up: update Character DB Current Rank, trigger avatar_renderer
    5. If no change: return without action
    Returns: {"character_id": str, "previous_rank": str, "current_rank": str,
              "rank_changed": bool}
    """
    from .notion_client import get_notion_client, get_character, update_character

    notion = get_notion_client()
    character = get_character(notion, character_id)

    total_xp = character.get("Total XP", 0) or 0
    current_rank = character.get("Current Rank", "Peasant") or "Peasant"

    calculated_rank = get_rank_from_xp(total_xp)
    calculated_tier = _rank_tier(calculated_rank)
    current_tier = _rank_tier(current_rank)

    result = {
        "character_id": character_id,
        "previous_rank": current_rank,
        "current_rank": current_rank,
        "rank_changed": False,
    }

    # High-water mark: only promote, never demote
    if calculated_tier > current_tier:
        logger.info(
            f"RANK UP! {current_rank} → {calculated_rank} "
            f"(Total XP: {total_xp})"
        )
        update_character(notion, character_id, {"Current Rank": {"select": {"name": calculated_rank}}})
        result["current_rank"] = calculated_rank
        result["rank_changed"] = True

        # Trigger avatar re-render with new rank frame
        try:
            from .avatar_renderer import update_character_avatar
            update_character_avatar(character_id)
        except Exception as e:
            logger.warning(f"Avatar update failed after rank-up: {e}")
    else:
        logger.info(
            f"No rank change for character {character_id}: "
            f"{current_rank} (Total XP: {total_xp})"
        )

    return result


def main():
    parser = argparse.ArgumentParser(description="Check and update player rank")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = check_rank_up(args.character_id)
    if result["rank_changed"]:
        print(f"RANK UP! {result['previous_rank']} → {result['current_rank']}")
    else:
        print(f"Rank unchanged: {result['current_rank']}")


if __name__ == "__main__":
    main()
