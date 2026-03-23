"""
Quest Engine — Processes completed quests: streak multiplier, Effective XP, Activity Log, Gold.
No AI dependency — works even when OpenAI is unreachable.

Usage:
    python -m tools.quest_engine --character-id <ID>
"""
import argparse
import math
from datetime import datetime, timezone

from .config import get_config
from .logger import get_logger

logger = get_logger(__name__)

# --- Notion DB IDs (hardcoded from verified workspace) ---
QUESTS_DB_ID = "1eba33ab-6878-4e55-b07a-cb551d3af2cd"
ACTIVITY_LOG_DB_ID = "caa7198e-e6c0-4d6a-948b-89b4cd0eb06f"
CHARACTER_DB_ID = "f814ec57-8879-482b-81cb-e68104d252c8"
STREAK_TRACKER_DB_ID = "2da610df-0671-4259-a8bb-905c396fb3d0"

# Alphabetical ordering for tie-breaking in get_weakest_stat
STAT_ALPHA_ORDER = ["CHA", "INT", "STR", "VIT", "WIS"]


def get_weakest_stat(character_id: str) -> str:
    """Read STR XP, INT XP, WIS XP, VIT XP, CHA XP from Character DB.
    Return the stat name with the lowest XP value.
    Tie-breaking: alphabetical order (CHA < INT < STR < VIT < WIS).
    """
    try:
        from .notion_client import get_notion_client, get_character
    except ImportError:
        logger.error("notion_client not available — cannot read character stats")
        raise

    notion = get_notion_client()
    character = get_character(notion, character_id)

    stats = {}
    for stat in STAT_ALPHA_ORDER:
        stats[stat] = character.get(f"{stat} XP", 0) or 0

    # Find minimum XP value
    min_xp = min(stats.values())

    # Return first stat (alphabetically) that matches the minimum
    for stat in STAT_ALPHA_ORDER:
        if stats[stat] == min_xp:
            logger.info(f"Weakest stat for {character_id}: {stat} ({min_xp} XP)")
            return stat

    # Should never reach here, but fallback
    return STAT_ALPHA_ORDER[0]


def get_domain_streak_multiplier(character_id: str, domain: str) -> float:
    """Query Streak Tracker DB filtered by Domain = given domain.
    Return the highest Multiplier value found.
    Return 1.0 if no matches or domain is None.
    """
    if domain is None:
        return 1.0

    try:
        from .notion_client import get_notion_client
    except ImportError:
        logger.warning("notion_client not available — returning default multiplier 1.0")
        return 1.0

    notion = get_notion_client()

    try:
        response = notion.databases.query(
            database_id=STREAK_TRACKER_DB_ID,
            filter={
                "property": "Domain",
                "select": {"equals": domain},
            },
        )
    except Exception as e:
        logger.warning(f"Streak Tracker query failed: {e} — returning 1.0")
        return 1.0

    results = response.get("results", [])
    if not results:
        logger.info(f"No streak entries for domain {domain} — multiplier 1.0")
        return 1.0

    # Find highest Multiplier value
    max_multiplier = 1.0
    for page in results:
        props = page.get("properties", {})
        multiplier = props.get("Multiplier", {}).get("number")
        if multiplier is not None and multiplier > max_multiplier:
            max_multiplier = multiplier

    logger.info(f"Streak multiplier for {domain}: {max_multiplier}")
    return max_multiplier


def get_pending_quests(character_id: str) -> list:
    """Query Quests DB: Status = 'Done' AND Effective XP is empty (None or 0).
    Filter by Character relation containing character_id.
    Return list of quest dicts with relevant fields extracted.
    """
    try:
        from .notion_client import get_notion_client
    except ImportError:
        logger.error("notion_client not available — cannot query quests")
        raise

    notion = get_notion_client()

    try:
        response = notion.databases.query(
            database_id=QUESTS_DB_ID,
            filter={
                "and": [
                    {"property": "Status", "status": {"equals": "Done"}},
                    {"property": "Character", "relation": {"contains": character_id}},
                    {
                        "or": [
                            {"property": "Effective XP", "number": {"is_empty": True}},
                            {"property": "Effective XP", "number": {"equals": 0}},
                        ]
                    },
                ]
            },
        )
    except Exception as e:
        logger.error(f"Failed to query pending quests: {e}")
        raise

    quests = []
    for page in response.get("results", []):
        props = page.get("properties", {})

        # Extract quest title
        name_title = props.get("Name", {}).get("title", [])
        name = name_title[0]["plain_text"] if name_title else "Unnamed Quest"

        # Extract domain (select)
        domain_select = props.get("Domain", {}).get("select")
        domain = domain_select["name"] if domain_select else None

        # Extract difficulty (select)
        difficulty_select = props.get("Difficulty", {}).get("select")
        difficulty = difficulty_select["name"] if difficulty_select else None

        # Extract numeric fields
        base_xp = props.get("Base XP", {}).get("number") or 0
        gold_reward = props.get("Gold Reward", {}).get("number") or 0
        effective_xp = props.get("Effective XP", {}).get("number") or 0

        # Extract source (select)
        source_select = props.get("Source", {}).get("select")
        source = source_select["name"] if source_select else None

        quests.append({
            "page_id": page["id"],
            "name": name,
            "domain": domain,
            "difficulty": difficulty,
            "base_xp": int(base_xp),
            "gold_reward": int(gold_reward),
            "effective_xp": int(effective_xp),
            "source": source,
        })

    logger.info(f"Found {len(quests)} pending quests for character {character_id}")
    return quests


def process_quest_completion(character_id: str, quest: dict) -> dict:
    """Process a single completed quest.
    1. Resolve domain (quest domain or get_weakest_stat() if empty)
    2. Get multiplier via get_domain_streak_multiplier()
    3. Calculate Effective XP = floor(base_xp * multiplier)
    4. Write Applied Multiplier + Effective XP to quest row
    5. Create Activity Log entry (Type=QUEST, EXP + (Quest)=effective_xp, Domain, Character)
    6. Credit Gold via coin_engine if gold_reward > 0
    Returns: result dict with quest details and calculated values.
    """
    try:
        from .notion_client import get_notion_client
    except ImportError:
        logger.error("notion_client not available — cannot process quest")
        raise

    notion = get_notion_client()

    page_id = quest["page_id"]
    name = quest["name"]
    base_xp = quest["base_xp"]
    gold_reward = quest["gold_reward"]

    # 1. Resolve domain
    domain = quest.get("domain")
    if not domain:
        domain = get_weakest_stat(character_id)
        logger.info(f"Quest '{name}' has no domain — defaulting to weakest stat: {domain}")

    # 2. Get streak multiplier
    multiplier = get_domain_streak_multiplier(character_id, domain)

    # 3. Calculate Effective XP
    effective_xp = math.floor(base_xp * multiplier)

    # 4. Update quest row with Applied Multiplier and Effective XP
    try:
        notion.pages.update(
            page_id=page_id,
            properties={
                "Applied Multiplier": {"number": multiplier},
                "Effective XP": {"number": effective_xp},
            },
        )
        logger.info(f"Updated quest '{name}': multiplier={multiplier}, effective_xp={effective_xp}")
    except Exception as e:
        logger.error(f"Failed to update quest '{name}': {e}")
        raise

    # 5. Create Activity Log entry
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    activity_properties = {
        "Type": {"select": {"name": "QUEST"}},
        "EXP + (Quest)": {"number": effective_xp},
        "Domain": {"select": {"name": domain}},
        "Character": {"relation": [{"id": character_id}]},
        "Notes": {"rich_text": [{"text": {"content": f"Quest completed: {name}"}}]},
    }

    try:
        notion.pages.create(
            parent={"database_id": ACTIVITY_LOG_DB_ID},
            properties=activity_properties,
        )
        logger.info(f"Activity Log entry created for quest '{name}'")
    except Exception as e:
        logger.error(f"Failed to create Activity Log entry for quest '{name}': {e}")
        raise

    # 6. Credit Gold if applicable
    gold_credited = 0
    if gold_reward > 0:
        try:
            from .coin_engine import credit_gold
            credit_gold(notion, character_id, gold_reward)
            gold_credited = gold_reward
            logger.info(f"Credited {gold_reward} Gold for quest '{name}'")
        except ImportError:
            logger.warning("coin_engine not available — Gold credit skipped")
        except Exception as e:
            logger.warning(f"Gold credit failed for quest '{name}': {e}")

    result = {
        "page_id": page_id,
        "name": name,
        "domain": domain,
        "base_xp": base_xp,
        "multiplier": multiplier,
        "effective_xp": effective_xp,
        "gold_reward": gold_reward,
        "gold_credited": gold_credited,
    }

    logger.info(
        f"QUEST COMPLETE: '{name}' — {effective_xp} XP ({base_xp} x {multiplier}) "
        f"→ {domain}, {gold_credited} Gold"
    )
    return result


def process_all_quests(character_id: str) -> dict:
    """Orchestrator: process all pending quests for a character.
    1. get_pending_quests()
    2. Process each quest via process_quest_completion()
    3. If any quests were processed, call xp_engine.update_character_stats()
    Returns: {"processed": int, "total_xp": int, "total_gold": int, "quests": list}
    """
    pending = get_pending_quests(character_id)

    processed = 0
    total_xp = 0
    total_gold = 0
    quest_results = []

    for quest in pending:
        try:
            result = process_quest_completion(character_id, quest)
            processed += 1
            total_xp += result["effective_xp"]
            total_gold += result["gold_credited"]
            quest_results.append(result)
        except Exception as e:
            logger.error(f"Failed to process quest '{quest.get('name', '?')}': {e}")
            # Continue processing remaining quests
            continue

    # Refresh character stats if any quests were processed
    if processed > 0:
        try:
            from .xp_engine import update_character_stats
            update_character_stats(character_id)
            logger.info(f"Character stats refreshed after {processed} quest(s)")
        except ImportError:
            logger.warning("xp_engine not available — stat refresh skipped")
        except Exception as e:
            logger.warning(f"Stat refresh failed after quests: {e}")

    summary = {
        "processed": processed,
        "total_xp": total_xp,
        "total_gold": total_gold,
        "quests": quest_results,
    }

    logger.info(
        f"Quest processing complete: {processed} processed, "
        f"{total_xp} total XP, {total_gold} total Gold"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description="Process completed quests")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = process_all_quests(args.character_id)
    print(f"Processed: {result['processed']}")
    print(f"Total XP: {result['total_xp']}")
    print(f"Total Gold: {result['total_gold']}")
    for q in result["quests"]:
        print(f"  - {q['name']}: {q['effective_xp']} XP ({q['base_xp']} x {q['multiplier']})")


if __name__ == "__main__":
    main()
