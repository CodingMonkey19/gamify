"""
Achievement Engine — Evaluates 43 achievement conditions via hardcoded dispatch.
Creates Player Achievement records, grants domain-routed XP bonuses via Activity Log.

Usage:
    python -m tools.achievement_engine --character-id <ID>
"""
import argparse
from datetime import datetime, timezone

from .config import get_config
from .logger import get_logger

logger = get_logger(__name__)


def get_all_achievements(notion, achievements_db_id: str) -> list:
    """Fetch all achievement definitions from Achievements DB.
    Returns: [{"id": str, "name": str, "condition_key": str,
               "xp_bonus": int, "domain": str, "icon_url": str}, ...]
    """
    results = []
    has_more = True
    start_cursor = None

    while has_more:
        kwargs = {"database_id": achievements_db_id}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        response = notion.databases.query(**kwargs)

        for page in response.get("results", []):
            props = page.get("properties", {})

            name_title = props.get("Name", {}).get("title", [])
            name = name_title[0]["plain_text"] if name_title else ""

            condition_rt = props.get("Condition Key", {}).get("rich_text", [])
            condition_key = condition_rt[0]["plain_text"] if condition_rt else ""

            xp_bonus = props.get("XP Bonus", {}).get("number") or 0

            domain_select = props.get("Domain", {}).get("select")
            domain = domain_select["name"] if domain_select else ""

            icon_url_prop = props.get("Icon URL", {}).get("url")

            results.append({
                "id": page["id"],
                "name": name,
                "condition_key": condition_key,
                "xp_bonus": int(xp_bonus),
                "domain": domain,
                "icon_url": icon_url_prop or "",
            })

        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")

    logger.info(f"Loaded {len(results)} achievement definitions")
    return results


def get_unlocked_achievements(notion, player_achievements_db_id: str, character_id: str) -> set:
    """Fetch all achievement IDs already unlocked by this character.
    Queries Player Achievements DB filtered by character relation.
    Returns: set of achievement IDs.
    """
    unlocked = set()
    has_more = True
    start_cursor = None

    while has_more:
        kwargs = {
            "database_id": player_achievements_db_id,
            "filter": {
                "property": "Character",
                "relation": {"contains": character_id},
            },
        }
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        response = notion.databases.query(**kwargs)

        for page in response.get("results", []):
            props = page.get("properties", {})
            achievement_rel = props.get("Achievement", {}).get("relation", [])
            for rel in achievement_rel:
                unlocked.add(rel["id"])

        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")

    logger.info(f"Character {character_id} has {len(unlocked)} unlocked achievements")
    return unlocked


# --- CONDITION CHECKERS ---
# Each checker: fn(notion, character_id) -> bool
# Queries relevant DBs to determine if condition is met.

def _query_count(notion, db_id: str, filter_obj: dict) -> int:
    """Helper: count rows matching a filter in a database."""
    response = notion.databases.query(database_id=db_id, filter=filter_obj)
    return len(response.get("results", []))


def check_first_workout(notion, character_id: str, db_ids: dict) -> bool:
    """1+ workout session completed."""
    count = _query_count(notion, db_ids["workout_sessions"], {
        "property": "Character",
        "relation": {"contains": character_id},
    })
    return count >= 1


def check_first_budget(notion, character_id: str, db_ids: dict) -> bool:
    """1+ monthly budget processed (expense log entry exists)."""
    count = _query_count(notion, db_ids["expense_log"], {
        "property": "Character",
        "relation": {"contains": character_id},
    })
    return count >= 1


def check_streak_n(notion, character_id: str, db_ids: dict, n: int) -> bool:
    """Any habit streak >= n days."""
    response = notion.databases.query(
        database_id=db_ids["streak_tracker"],
        filter={
            "and": [
                {"property": "Character", "relation": {"contains": character_id}},
                {"property": "Current Streak", "number": {"greater_than_or_equal_to": n}},
            ]
        },
    )
    return len(response.get("results", [])) > 0


def check_streak_3(notion, character_id: str, db_ids: dict) -> bool:
    return check_streak_n(notion, character_id, db_ids, 3)


def check_streak_7(notion, character_id: str, db_ids: dict) -> bool:
    return check_streak_n(notion, character_id, db_ids, 7)


def check_streak_14(notion, character_id: str, db_ids: dict) -> bool:
    return check_streak_n(notion, character_id, db_ids, 14)


def check_streak_30(notion, character_id: str, db_ids: dict) -> bool:
    return check_streak_n(notion, character_id, db_ids, 30)


def check_streak_60(notion, character_id: str, db_ids: dict) -> bool:
    return check_streak_n(notion, character_id, db_ids, 60)


def check_streak_100(notion, character_id: str, db_ids: dict) -> bool:
    return check_streak_n(notion, character_id, db_ids, 100)


def check_rank(notion, character_id: str, db_ids: dict, rank_name: str) -> bool:
    """Check if character has reached a specific rank."""
    from .rank_engine import RANK_ORDER, _rank_tier
    from .notion_client import get_character

    character = get_character(notion, character_id)
    current_rank = character.get("Current Rank", "Peasant") or "Peasant"
    return _rank_tier(current_rank) >= _rank_tier(rank_name)


def check_rank_squire(notion, character_id: str, db_ids: dict) -> bool:
    return check_rank(notion, character_id, db_ids, "Squire")


def check_rank_knight(notion, character_id: str, db_ids: dict) -> bool:
    return check_rank(notion, character_id, db_ids, "Knight")


def check_rank_champion(notion, character_id: str, db_ids: dict) -> bool:
    return check_rank(notion, character_id, db_ids, "Champion")


def check_rank_hero(notion, character_id: str, db_ids: dict) -> bool:
    return check_rank(notion, character_id, db_ids, "Hero")


def check_rank_legend(notion, character_id: str, db_ids: dict) -> bool:
    return check_rank(notion, character_id, db_ids, "Legend")


def check_rank_mythic(notion, character_id: str, db_ids: dict) -> bool:
    return check_rank(notion, character_id, db_ids, "Mythic")


def check_workout_count(notion, character_id: str, db_ids: dict, n: int) -> bool:
    """N+ workout sessions completed."""
    count = _query_count(notion, db_ids["workout_sessions"], {
        "property": "Character",
        "relation": {"contains": character_id},
    })
    return count >= n


def check_5_workouts(notion, character_id: str, db_ids: dict) -> bool:
    return check_workout_count(notion, character_id, db_ids, 5)


def check_10_workouts(notion, character_id: str, db_ids: dict) -> bool:
    return check_workout_count(notion, character_id, db_ids, 10)


def check_25_workouts(notion, character_id: str, db_ids: dict) -> bool:
    return check_workout_count(notion, character_id, db_ids, 25)


def check_50_workouts(notion, character_id: str, db_ids: dict) -> bool:
    return check_workout_count(notion, character_id, db_ids, 50)


def check_100_workouts(notion, character_id: str, db_ids: dict) -> bool:
    return check_workout_count(notion, character_id, db_ids, 100)


def check_first_good_habit(notion, character_id: str, db_ids: dict) -> bool:
    """Completed at least 1 good habit check-in."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "GOOD"}},
        ]
    })
    return count >= 1


def check_first_bad_habit_logged(notion, character_id: str, db_ids: dict) -> bool:
    """Logged at least 1 bad habit occurrence (honesty badge)."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "BAD"}},
        ]
    })
    return count >= 1


def check_first_goal_completed(notion, character_id: str, db_ids: dict) -> bool:
    """Completed at least 1 goal."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "GOAL"}},
        ]
    })
    return count >= 1


def check_first_loot_box(notion, character_id: str, db_ids: dict) -> bool:
    """Opened at least 1 loot box."""
    count = _query_count(notion, db_ids["loot_box_inventory"], {
        "property": "Character",
        "relation": {"contains": character_id},
    })
    return count >= 1


def check_first_death(notion, character_id: str, db_ids: dict) -> bool:
    """Died at least once."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "DIED"}},
        ]
    })
    return count >= 1


def check_gold_milestone(notion, character_id: str, db_ids: dict, amount: int) -> bool:
    """Character has accumulated >= amount Gold (current balance)."""
    from .notion_client import get_character
    character = get_character(notion, character_id)
    gold = character.get("Gold", 0) or 0
    return gold >= amount


def check_gold_100(notion, character_id: str, db_ids: dict) -> bool:
    return check_gold_milestone(notion, character_id, db_ids, 100)


def check_gold_1000(notion, character_id: str, db_ids: dict) -> bool:
    return check_gold_milestone(notion, character_id, db_ids, 1000)


def check_gold_10000(notion, character_id: str, db_ids: dict) -> bool:
    return check_gold_milestone(notion, character_id, db_ids, 10000)


# --- Additional checkers for Phase 5 achievement set ---

def check_first_quest(notion, character_id: str, db_ids: dict) -> bool:
    """Completed at least 1 quest."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "GOAL"}},
        ]
    })
    return count >= 1


def check_first_gold(notion, character_id: str, db_ids: dict) -> bool:
    """Earned any Gold (Gold > 0)."""
    return check_gold_milestone(notion, character_id, db_ids, 1)


def check_first_hotel(notion, character_id: str, db_ids: dict) -> bool:
    """Completed at least 1 hotel check-in."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "HOTEL"}},
        ]
    })
    return count >= 1


def check_first_social(notion, character_id: str, db_ids: dict) -> bool:
    """Completed at least 1 social domain habit check-in."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "GOOD"}},
            {"property": "Domain", "select": {"equals": "CHA"}},
        ]
    })
    return count >= 1


def check_first_meal(notion, character_id: str, db_ids: dict) -> bool:
    """Logged at least 1 meal."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "NUTRITION"}},
        ]
    })
    return count >= 1


def _check_coin_milestone(notion, character_id: str, db_ids: dict, amount: int) -> bool:
    """Character current coins >= amount."""
    from .notion_client import get_character
    character = get_character(notion, character_id)
    coins = character.get("Current Coins", 0) or 0
    return coins >= amount


def check_coins_100(notion, character_id: str, db_ids: dict) -> bool:
    return _check_coin_milestone(notion, character_id, db_ids, 100)


def check_coins_500(notion, character_id: str, db_ids: dict) -> bool:
    return _check_coin_milestone(notion, character_id, db_ids, 500)


def check_coins_1000(notion, character_id: str, db_ids: dict) -> bool:
    return _check_coin_milestone(notion, character_id, db_ids, 1000)


def _check_total_xp(notion, character_id: str, db_ids: dict, amount: int) -> bool:
    """Character Total XP >= amount."""
    from .notion_client import get_character
    character = get_character(notion, character_id)
    xp = character.get("Total XP", 0) or 0
    return xp >= amount


def check_xp_1000(notion, character_id: str, db_ids: dict) -> bool:
    return _check_total_xp(notion, character_id, db_ids, 1000)


def check_xp_10000(notion, character_id: str, db_ids: dict) -> bool:
    return _check_total_xp(notion, character_id, db_ids, 10000)


def _check_player_level(notion, character_id: str, db_ids: dict, level: int) -> bool:
    """Character Player Level >= level."""
    from .notion_client import get_character
    character = get_character(notion, character_id)
    plevel = character.get("Player Level", 1) or 1
    return plevel >= level


def check_level_5(notion, character_id: str, db_ids: dict) -> bool:
    return _check_player_level(notion, character_id, db_ids, 5)


def check_level_10(notion, character_id: str, db_ids: dict) -> bool:
    return _check_player_level(notion, character_id, db_ids, 10)


def check_level_20(notion, character_id: str, db_ids: dict) -> bool:
    return _check_player_level(notion, character_id, db_ids, 20)


def check_level_30(notion, character_id: str, db_ids: dict) -> bool:
    return _check_player_level(notion, character_id, db_ids, 30)


def check_level_50(notion, character_id: str, db_ids: dict) -> bool:
    return _check_player_level(notion, character_id, db_ids, 50)


def _check_activity_count(notion, character_id: str, db_ids: dict, activity_type: str, n: int) -> bool:
    """Count Activity Log entries of given type for character >= n."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": activity_type}},
        ]
    })
    return count >= n


def check_10_meals(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "NUTRITION", 10)


def check_25_meals(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "NUTRITION", 25)


def check_50_meals(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "NUTRITION", 50)


def check_10_expenses(notion, character_id: str, db_ids: dict) -> bool:
    """10+ expense entries logged."""
    count = _query_count(notion, db_ids["expense_log"], {
        "property": "Character",
        "relation": {"contains": character_id},
    })
    return count >= 10


def check_50_expenses(notion, character_id: str, db_ids: dict) -> bool:
    """50+ expense entries logged."""
    count = _query_count(notion, db_ids["expense_log"], {
        "property": "Character",
        "relation": {"contains": character_id},
    })
    return count >= 50


def check_habit_master(notion, character_id: str, db_ids: dict) -> bool:
    """3+ habits with streaks >= 30 days simultaneously."""
    response = notion.databases.query(
        database_id=db_ids["streak_tracker"],
        filter={
            "and": [
                {"property": "Current Streak", "number": {"greater_than_or_equal_to": 30}},
            ]
        },
    )
    return len(response.get("results", [])) >= 3


def check_volume_10k(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "WORKOUT", 10)


def check_volume_50k(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "WORKOUT", 25)


def check_protein_10(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "NUTRITION", 10)


def check_protein_25(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "NUTRITION", 25)


def check_speaker(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "GOOD", 10)


def check_connector(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "GOOD", 25)


def check_creator(notion, character_id: str, db_ids: dict) -> bool:
    """At least 1 CHA-domain goal completed."""
    count = _query_count(notion, db_ids["activity_log"], {
        "and": [
            {"property": "Character", "relation": {"contains": character_id}},
            {"property": "Type", "select": {"equals": "GOAL"}},
            {"property": "Domain", "select": {"equals": "CHA"}},
        ]
    })
    return count >= 1


def check_community_builder(notion, character_id: str, db_ids: dict) -> bool:
    return _check_activity_count(notion, character_id, db_ids, "GOOD", 50)


# --- CONDITION DISPATCH MAP ---
CONDITION_CHECKERS = {
    # First-action achievements
    "first_workout": check_first_workout,
    "first_budget": check_first_budget,
    "first_good_habit": check_first_good_habit,
    "first_bad_habit": check_first_bad_habit_logged,
    "first_goal": check_first_goal_completed,
    "first_loot_box": check_first_loot_box,
    "first_death": check_first_death,
    "first_quest": check_first_quest,
    "first_gold": check_first_gold,
    "first_hotel": check_first_hotel,
    "first_social": check_first_social,
    "first_meal": check_first_meal,
    # Streak milestones
    "streak_3": check_streak_3,
    "streak_7": check_streak_7,
    "streak_14": check_streak_14,
    "streak_30": check_streak_30,
    "streak_60": check_streak_60,
    "streak_100": check_streak_100,
    # Rank milestones
    "rank_squire": check_rank_squire,
    "rank_knight": check_rank_knight,
    "rank_champion": check_rank_champion,
    "rank_hero": check_rank_hero,
    "rank_legend": check_rank_legend,
    "rank_mythic": check_rank_mythic,
    # Workout milestones
    "5_workouts": check_5_workouts,
    "10_workouts": check_10_workouts,
    "25_workouts": check_25_workouts,
    "50_workouts": check_50_workouts,
    "100_workouts": check_100_workouts,
    # Gold milestones
    "gold_100": check_gold_100,
    "gold_1000": check_gold_1000,
    "gold_10000": check_gold_10000,
    # Coin milestones
    "coins_100": check_coins_100,
    "coins_500": check_coins_500,
    "coins_1000": check_coins_1000,
    # XP milestones
    "xp_1000": check_xp_1000,
    "xp_10000": check_xp_10000,
    # Level milestones
    "level_5": check_level_5,
    "level_10": check_level_10,
    "level_20": check_level_20,
    "level_30": check_level_30,
    "level_50": check_level_50,
    # Nutrition milestones
    "10_meals": check_10_meals,
    "25_meals": check_25_meals,
    "50_meals": check_50_meals,
    "protein_10": check_protein_10,
    "protein_25": check_protein_25,
    # Finance milestones
    "10_expenses": check_10_expenses,
    "50_expenses": check_50_expenses,
    # Volume/fitness
    "volume_10k": check_volume_10k,
    "volume_50k": check_volume_50k,
    # Habit mastery
    "habit_master": check_habit_master,
    # Social/CHA
    "speaker": check_speaker,
    "connector": check_connector,
    "creator": check_creator,
    "community_builder": check_community_builder,
}


def check_condition(condition_key: str, notion, character_id: str, db_ids: dict) -> bool:
    """Dispatch condition_key to the appropriate checker function.
    Returns: True if condition is met, False otherwise.
    Returns False for unknown condition keys (logged as warning).
    """
    checker = CONDITION_CHECKERS.get(condition_key)
    if checker is None:
        logger.warning(f"Unknown condition key: '{condition_key}' — returning False")
        return False

    try:
        return checker(notion, character_id, db_ids)
    except Exception as e:
        logger.warning(f"Condition check '{condition_key}' failed: {e}")
        return False


def check_all_achievements(character_id: str) -> dict:
    """Orchestrator: evaluate all achievement conditions for a character.
    1. Fetch all achievements
    2. Fetch already-unlocked achievement IDs
    3. For each not-yet-unlocked: check_condition()
    4. For each newly qualifying: create Player Achievement + Activity Log entry
    5. Call xp_engine.update_character_stats() if any unlocked
    Returns: {"checked": int, "newly_unlocked": list[str], "total_xp_granted": int}
    """
    from .notion_client import (
        get_notion_client,
        get_db_ids,
        create_page,
    )

    notion = get_notion_client()
    db_ids = get_db_ids()

    # Fetch all achievements and already-unlocked set
    all_achievements = get_all_achievements(notion, db_ids["achievements"])
    unlocked = get_unlocked_achievements(notion, db_ids["player_achievements"], character_id)

    checked = 0
    newly_unlocked = []
    total_xp = 0

    for achievement in all_achievements:
        if achievement["id"] in unlocked:
            continue  # Already unlocked — skip

        if not achievement["condition_key"]:
            continue  # No condition key — can't evaluate

        checked += 1
        if check_condition(achievement["condition_key"], notion, character_id, db_ids):
            # Unlock! Create Player Achievement row
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            create_page(notion, db_ids["player_achievements"], {
                "Achievement": {"relation": [{"id": achievement["id"]}]},
                "Character": {"relation": [{"id": character_id}]},
                "Earned At": {"date": {"start": today}},
                "Notified": {"checkbox": False},
            })

            # Create Activity Log entry with XP bonus routed to achievement's domain
            create_page(notion, db_ids["activity_log"], {
                "Type": {"select": {"name": "ACHIEVEMENT"}},
                "Character": {"relation": [{"id": character_id}]},
                "EXP + (Achievement)": {"number": achievement["xp_bonus"]},
                "Domain": {"select": {"name": achievement["domain"]}} if achievement["domain"] else {},
                "Notes": {"rich_text": [{"text": {"content": f"Achievement unlocked: {achievement['name']}"}}]},
            })

            newly_unlocked.append(achievement["name"])
            total_xp += achievement["xp_bonus"]
            logger.info(
                f"ACHIEVEMENT UNLOCKED: {achievement['name']} "
                f"(+{achievement['xp_bonus']} XP → {achievement['domain']})"
            )

    # Refresh stats if any achievements were unlocked
    if newly_unlocked:
        try:
            from .xp_engine import update_character_stats
            update_character_stats(character_id)
        except ImportError:
            logger.warning("xp_engine not available — stat refresh skipped")
        except Exception as e:
            logger.warning(f"Stat refresh failed after achievements: {e}")

    result = {
        "checked": checked,
        "newly_unlocked": newly_unlocked,
        "total_xp_granted": total_xp,
    }
    logger.info(
        f"Achievement check complete: {checked} checked, "
        f"{len(newly_unlocked)} unlocked, {total_xp} XP granted"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="Check and unlock achievements")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = check_all_achievements(args.character_id)
    print(f"Checked: {result['checked']}")
    print(f"Newly unlocked: {result['newly_unlocked']}")
    print(f"Total XP granted: {result['total_xp_granted']}")


if __name__ == "__main__":
    main()
