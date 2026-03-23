"""
Loot Box Engine — Gold-to-Coins conversion via weighted PRNG with pity timer.
CLI-triggered, records to Loot Box Inventory.

Usage:
    python -m tools.loot_box --character-id <ID>
"""
import argparse
import random
from datetime import datetime, timezone

from .config import (
    LOOT_WEIGHTS,
    LOOT_COST,
    LOOT_REWARDS,
    PITY_TIMER_THRESHOLD,
    get_config,
)
from .logger import get_logger

logger = get_logger(__name__)

RARITY_NAMES = {
    "Common": "Common Coin Pouch",
    "Rare": "Rare Coin Pouch",
    "Epic": "Epic Treasure Chest",
    "Legendary": "Legendary Hoard",
}


def roll_rarity(pity_counter: int) -> str:
    """Select random rarity using LOOT_WEIGHTS from config.
    If pity_counter >= PITY_TIMER_THRESHOLD: return 'Legendary' (guaranteed).
    Otherwise: weighted random selection.
    Returns: rarity name ('Common', 'Rare', 'Epic', 'Legendary').
    """
    config = get_config()
    threshold = config.get("PITY_TIMER_THRESHOLD", PITY_TIMER_THRESHOLD)
    weights = config.get("LOOT_WEIGHTS", LOOT_WEIGHTS)

    if pity_counter >= threshold:
        logger.info(f"Pity timer triggered at {pity_counter} — guaranteed Legendary!")
        return "Legendary"

    rarities = list(weights.keys())
    weight_values = list(weights.values())
    result = random.choices(rarities, weights=weight_values, k=1)[0]
    return result


def get_coin_reward(rarity: str) -> int:
    """Look up Coin reward for a rarity tier from LOOT_REWARDS config.
    Default: Common=25, Rare=75, Epic=200, Legendary=1000.
    Returns: Coin amount (int).
    """
    config = get_config()
    rewards = config.get("LOOT_REWARDS", LOOT_REWARDS)
    reward = rewards.get(rarity, 0)
    return int(reward)


def open_loot_box(character_id: str) -> dict:
    """Full loot box purchase pipeline.
    1. Read Gold balance and Pity Counter from Character DB
    2. Check Gold >= LOOT_COST → reject if insufficient
    3. Deduct Gold via coin_engine
    4. Roll rarity (passing current pity_counter)
    5. Get Coin reward for rarity
    6. Credit Coins via coin_engine
    7. Update Pity Counter: reset to 0 if Legendary, else increment by 1
    8. Create Loot Box Inventory row
    Returns: {"rarity": str, "coins_awarded": int, "gold_spent": int,
              "pity_counter": int, "inventory_id": str}
    Returns None with error message if insufficient Gold.
    """
    from .notion_client import (
        get_notion_client,
        get_character,
        update_character,
        get_db_ids,
        create_page,
    )

    config = get_config()
    cost = config.get("LOOT_COST", LOOT_COST)

    notion = get_notion_client()
    character = get_character(notion, character_id)
    db_ids = get_db_ids()

    gold = character.get("Gold", 0) or 0
    pity_counter = character.get("Pity Counter", 0) or 0

    # Check sufficient Gold
    if gold < cost:
        logger.warning(
            f"Insufficient Gold: {gold} < {cost} (need {cost - gold} more)"
        )
        return None

    # Deduct Gold
    try:
        from .coin_engine import deduct_gold
        deduct_gold(notion, character_id, cost)
    except ImportError:
        # Fallback: direct update if coin_engine not available yet
        update_character(notion, character_id, {"Gold": {"number": gold - cost}})
        logger.info(f"Deducted {cost} Gold (direct update, coin_engine not available)")

    # Roll rarity
    rarity = roll_rarity(pity_counter)
    coins = get_coin_reward(rarity)

    # Credit Coins
    current_coins = character.get("Current Coins", 0) or 0
    try:
        from .coin_engine import credit_coins
        credit_coins(notion, character_id, coins)
    except ImportError:
        update_character(notion, character_id, {"Current Coins": {"number": current_coins + coins}})
        logger.info(f"Credited {coins} Coins (direct update, coin_engine not available)")

    # Update Pity Counter
    new_pity = 0 if rarity == "Legendary" else pity_counter + 1
    update_character(notion, character_id, {"Pity Counter": {"number": new_pity}})

    # Create Loot Box Inventory row
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reward_name = RARITY_NAMES.get(rarity, f"{rarity} Reward")

    inventory_page = create_page(notion, db_ids["loot_box_inventory"], {
        "Name": {"title": [{"text": {"content": reward_name}}]},
        "Rarity": {"select": {"name": rarity}},
        "Value": {"number": coins},
        "Gold Cost": {"number": cost},
        "Claimed": {"checkbox": True},
        "Date": {"date": {"start": today}},
        "Character": {"relation": [{"id": character_id}]},
    })

    inventory_id = inventory_page.get("id", "")

    logger.info(
        f"LOOT BOX OPENED: {rarity} — {coins} Coins awarded, "
        f"{cost} Gold spent, pity={new_pity}"
    )

    return {
        "rarity": rarity,
        "coins_awarded": coins,
        "gold_spent": cost,
        "pity_counter": new_pity,
        "inventory_id": inventory_id,
    }


def main():
    parser = argparse.ArgumentParser(description="Open a loot box")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = open_loot_box(args.character_id)
    if result:
        print(f"Rarity: {result['rarity']}")
        print(f"Coins awarded: {result['coins_awarded']}")
        print(f"Gold spent: {result['gold_spent']}")
        print(f"Pity counter: {result['pity_counter']}")
    else:
        print("Loot box purchase failed — insufficient Gold")


if __name__ == "__main__":
    main()
