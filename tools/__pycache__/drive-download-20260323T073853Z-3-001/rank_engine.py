"""Rank calculation and progression logic."""

import argparse
import os
import sys

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import config
import notion_client_wrapper as notion_api

logger = get_logger(__name__)


def get_rank_from_xp(total_xp, cfg=None):
    """
    Finds the highest threshold <= total_xp from RANK_THRESHOLDS.
    Returns the rank name (str). Defaults to 'Peasant' for 0.
    """
    if cfg is None:
        cfg = config.get_config()
    
    thresholds = cfg.get("RANK_THRESHOLDS", {})
    # Ensure thresholds are sorted by XP (the keys are ints in config, but might be strings from Notion)
    sorted_thresholds = sorted(
        [(int(xp), name) for xp, name in thresholds.items()],
        key=lambda x: x[0]
    )
    
    current_rank = "Peasant"
    for threshold, name in sorted_thresholds:
        if total_xp >= threshold:
            current_rank = name
        else:
            break
            
    return current_rank


def check_rank_up(character_id, client=None, db_ids=None, cfg=None):
    """
    Reads Total XP + Current Rank from Character DB, calculates rank,
    compares tier (high-water mark: only promote, never demote),
    updates Character DB if rank-up, triggers avatar_renderer.update_character_avatar().
    Returns dict {previous_rank, current_rank, rank_changed}.
    """
    if client is None:
        client = notion_api.get_client()
    if db_ids is None:
        db_ids = notion_api.get_database_ids()
    if cfg is None:
        cfg = config.get_config(client, db_ids.get("Settings"))

    # Fetch character data
    char_page = notion_api.get_page(client, character_id)
    props = char_page.get("properties", {})
    
    total_xp = props.get("Total XP", {}).get("number", 0)
    current_rank_name = props.get("Current Rank", {}).get("select", {}).get("name", "Peasant")
    
    new_rank_name = get_rank_from_xp(total_xp, cfg)
    
    # Tier ordering for high-water mark
    thresholds = cfg.get("RANK_THRESHOLDS", {})
    sorted_ranks = [name for _, name in sorted(
        [(int(xp), name) for xp, name in thresholds.items()],
        key=lambda x: x[0]
    )]
    
    try:
        current_tier = sorted_ranks.index(current_rank_name)
    except ValueError:
        current_tier = 0
        
    try:
        new_tier = sorted_ranks.index(new_rank_name)
    except ValueError:
        new_tier = 0
        
    rank_changed = False
    if new_tier > current_tier:
        logger.info(f"Rank up detected for {character_id}: {current_rank_name} -> {new_rank_name}")
        # Update Character DB
        notion_api.update_page(client, character_id, {
            "Current Rank": {"select": {"name": new_rank_name}}
        })
        rank_changed = True
        
        # Trigger avatar regeneration
        try:
            import avatar_renderer
            avatar_renderer.update_character_avatar(character_id, client, db_ids, cfg)
        except Exception as e:
            logger.error(f"Failed to trigger avatar regeneration after rank up: {e}")
            
    return {
        "previous_rank": current_rank_name,
        "current_rank": new_rank_name if rank_changed else current_rank_name,
        "rank_changed": rank_changed
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check and update character rank.")
    parser.add_argument("--character-id", required=True, help="Notion Page ID of the character")
    args = parser.parse_args()

    result = check_rank_up(args.character_id)
    if result["rank_changed"]:
        print(f"RANK UP! {result['previous_rank']} -> {result['current_rank']}")
    else:
        print(f"Current rank: {result['current_rank']} (Total XP: {result['previous_rank']} logic applied)")
