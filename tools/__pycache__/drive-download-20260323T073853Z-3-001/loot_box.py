"""Loot box roll and reward logic."""

import argparse
import os
import sys
import random
from datetime import date

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import config
import notion_client_wrapper as notion_api
import coin_engine

logger = get_logger(__name__)


def roll_rarity(pity_counter, cfg=None):
    """
    Determines rarity of a loot box roll.
    Guarantees Legendary if pity_counter >= PITY_TIMER_THRESHOLD.
    """
    if cfg is None:
        cfg = config.get_config()
        
    pity_threshold = cfg.get("PITY_TIMER_THRESHOLD", 50)
    if pity_counter >= pity_threshold:
        logger.info(f"Pity timer reached ({pity_counter}). Guaranteeing Legendary!")
        return "Legendary"
        
    weights_dict = cfg.get("LOOT_WEIGHTS", {"Common": 70, "Rare": 20, "Epic": 8, "Legendary": 2})
    rarities = list(weights_dict.keys())
    weights = list(weights_dict.values())
    
    return random.choices(rarities, weights=weights, k=1)[0]


def get_coin_reward(rarity, cfg=None):
    """Returns Coin reward amount for a given rarity."""
    if cfg is None:
        cfg = config.get_config()
        
    rewards = cfg.get("LOOT_REWARDS", {"Common": 25, "Rare": 75, "Epic": 200, "Legendary": 1000})
    return rewards.get(rarity, 25)


def open_loot_box(character_id, client=None, db_ids=None, cfg=None):
    """
    Orchestrator: opens a loot box, deducts Gold, grants Coins, updates pity.
    Returns result summary dict.
    """
    if client is None:
        client = notion_api.get_client()
    if db_ids is None:
        db_ids = notion_api.get_database_ids()
    if cfg is None:
        cfg = config.get_config(client, db_ids.get("Settings"))
        
    loot_cost = cfg.get("LOOT_COST", 100)
    
    # Fetch character stats
    char_page = notion_api.get_page(client, character_id)
    props = char_page.get("properties", {})
    
    gold_balance = props.get("Gold", {}).get("number", 0)
    pity_counter = props.get("Pity Counter", {}).get("number", 0)
    
    if gold_balance < loot_cost:
        logger.warning(f"Insufficient Gold for {character_id}: {gold_balance} < {loot_cost}")
        return {"error": "Insufficient Gold", "gold_needed": loot_cost, "gold_current": gold_balance}
        
    # Roll and determine reward
    rarity = roll_rarity(pity_counter, cfg)
    coins = get_coin_reward(rarity, cfg)
    
    # Deduct Gold and credit Coins
    logger.info(f"Opening loot box for {character_id}: Roll={rarity}, Reward={coins} Coins")
    coin_engine.add_gold(character_id, -loot_cost, client, db_ids)
    coin_engine.earn_coins(character_id, coins, entry_type="LOOTBOX", source=rarity, client=client, db_ids=db_ids)
    
    # Update Pity Counter
    new_pity = 0 if rarity == "Legendary" else pity_counter + 1
    notion_api.update_page(client, character_id, {
        "Pity Counter": {"number": new_pity}
    })
    
    # Record in Loot Box Inventory
    inventory_page = notion_api.create_page(client, db_ids["Loot Box Inventory"], {
        "Reward Name": {"title": [{"text": {"content": f"{rarity} Coin Pouch"}}]},
        "Rarity": {"select": {"name": rarity}},
        "Coins Awarded": {"number": coins},
        "Gold Cost": {"number": loot_cost},
        "Claimed": {"checkbox": True},
        "Date": {"date": {"start": date.today().isoformat()}},
        "Character": {"relation": [{"id": character_id}]}
    })
    
    return {
        "rarity": rarity,
        "coins_awarded": coins,
        "gold_spent": loot_cost,
        "pity_counter": new_pity,
        "inventory_id": inventory_page["id"]
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open a loot box.")
    parser.add_argument("--character-id", required=True, help="Notion Page ID of the character")
    args = parser.parse_args()

    result = open_loot_box(args.character_id)
    if "error" in result:
        print(f"FAILED: {result['error']} (Need {result['gold_needed']} Gold, have {result['gold_current']})")
    else:
        print(f"SUCCESS! Opened a {result['rarity']} loot box.")
        print(f"Earned {result['coins_awarded']} Coins for {result['gold_spent']} Gold.")
        print(f"Pity counter now at {result['pity_counter']}.")
