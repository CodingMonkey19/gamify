"""
Quest Generator — AI-powered procedural quest generation via OpenAI.
Generates 3 personalized quests per week based on player stats, streaks, and weak areas.

Usage:
    python -m tools.quest_generator --character-id <ID>
"""
import argparse
import json
from datetime import datetime, timezone, timedelta

from .config import (
    get_config,
    STATS,
    QUEST_DIFFICULTY_REWARDS,
    OPENAI_MODEL,
    OPENAI_MAX_TOKENS,
)
from .logger import get_logger

logger = get_logger(__name__)

# Lazy-loaded at module level for testability (patchable)
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from .notion_client import get_notion_client
except ImportError:
    get_notion_client = None

# --- Notion DB IDs (hardcoded from verified workspace) ---
QUESTS_DB_ID = "1eba33ab-6878-4e55-b07a-cb551d3af2cd"
CHARACTER_DB_ID = "f814ec57-8879-482b-81cb-e68104d252c8"
STREAK_TRACKER_DB_ID = "2da610df-0671-4259-a8bb-905c396fb3d0"
SETTINGS_DB_ID = "49bc6e3d-d39d-45f4-968f-756f779ed819"

VALID_DOMAINS = set(STATS)  # {"STR", "INT", "WIS", "VIT", "CHA"}
VALID_DIFFICULTIES = set(QUEST_DIFFICULTY_REWARDS.keys())  # {"Easy", "Medium", "Hard", "Epic"}


# ---------------------------------------------------------------------------
# build_generation_context — gather player data for AI prompt
# ---------------------------------------------------------------------------

def build_generation_context(character_id: str) -> dict:
    """Read player stats, streaks, and quest counts from Notion.
    Returns a context dict matching the schema in data-model.md:
    {
        "player_stats": {"STR": int, ...},
        "stat_levels": {"STR": int, ...},
        "weakest_stat": str,
        "active_streaks": [{"habit": str, "domain": str, "streak": int, "tier": str}, ...],
        "recent_quests_completed": int,
        "total_quests_available": int,
        "player_rank": str,
        "player_level": int,
    }
    """
    from .notion_client import get_notion_client, get_character
    from .quest_engine import get_weakest_stat

    notion = get_notion_client()
    character = get_character(notion, character_id)

    # --- Player stats and levels ---
    player_stats = {}
    stat_levels = {}
    for stat in STATS:
        player_stats[stat] = character.get(f"{stat} XP", 0) or 0
        stat_levels[stat] = character.get(f"{stat} Level", 0) or 0

    player_level = character.get("Player Level", 1) or 1
    player_rank = character.get("Current Rank", "Peasant") or "Peasant"

    # --- Weakest stat ---
    weakest_stat = get_weakest_stat(character_id)

    # --- Active streaks (Current Streak > 0) ---
    active_streaks = []
    try:
        streak_response = notion.databases.query(
            database_id=STREAK_TRACKER_DB_ID,
            filter={
                "property": "Current Streak",
                "number": {"greater_than": 0},
            },
        )
        for page in streak_response.get("results", []):
            props = page.get("properties", {})

            habit_title = props.get("Name", {}).get("title", [])
            habit = habit_title[0]["plain_text"] if habit_title else "Unknown"

            domain_select = props.get("Domain", {}).get("select")
            domain = domain_select["name"] if domain_select else "Unknown"

            streak = props.get("Current Streak", {}).get("number") or 0

            tier_select = props.get("Tier", {}).get("select")
            tier = tier_select["name"] if tier_select else "None"

            active_streaks.append({
                "habit": habit,
                "domain": domain,
                "streak": streak,
                "tier": tier,
            })
    except Exception as e:
        logger.warning(f"Failed to query Streak Tracker: {e} — continuing with empty streaks")

    # --- Recently completed quests (Status = Done) ---
    recent_quests_completed = 0
    try:
        completed_response = notion.databases.query(
            database_id=QUESTS_DB_ID,
            filter={
                "and": [
                    {"property": "Status", "status": {"equals": "Done"}},
                    {"property": "Character", "relation": {"contains": character_id}},
                ]
            },
        )
        recent_quests_completed = len(completed_response.get("results", []))
    except Exception as e:
        logger.warning(f"Failed to count completed quests: {e}")

    # --- Currently available quests (Status = Not started) ---
    total_quests_available = 0
    try:
        available_response = notion.databases.query(
            database_id=QUESTS_DB_ID,
            filter={
                "and": [
                    {"property": "Status", "status": {"equals": "Not started"}},
                    {"property": "Character", "relation": {"contains": character_id}},
                ]
            },
        )
        total_quests_available = len(available_response.get("results", []))
    except Exception as e:
        logger.warning(f"Failed to count available quests: {e}")

    context = {
        "player_stats": player_stats,
        "stat_levels": stat_levels,
        "weakest_stat": weakest_stat,
        "active_streaks": active_streaks,
        "recent_quests_completed": recent_quests_completed,
        "total_quests_available": total_quests_available,
        "player_rank": player_rank,
        "player_level": player_level,
    }

    logger.info(
        f"Generation context built: weakest={weakest_stat}, "
        f"streaks={len(active_streaks)}, completed={recent_quests_completed}, "
        f"available={total_quests_available}"
    )
    return context


# ---------------------------------------------------------------------------
# validate_quest — PURE FUNCTION, no Notion dependency
# ---------------------------------------------------------------------------

def validate_quest(quest_data: dict, weakest_stat: str) -> dict | None:
    """Validate a single AI-generated quest dict.
    Returns validated dict with corrections applied, or None if quest is invalid.

    Validation rules:
    - title: non-empty string → return None if missing/empty
    - narrative: non-empty string → return None if missing/empty
    - domain: must be in VALID_DOMAINS → default to weakest_stat + log warning
    - difficulty: must be in VALID_DIFFICULTIES → default to "Medium" + log warning
    """
    title = quest_data.get("title", "")
    narrative = quest_data.get("narrative", "")
    domain = quest_data.get("domain", "")
    difficulty = quest_data.get("difficulty", "")

    # --- Title validation ---
    if not title or not isinstance(title, str) or not title.strip():
        logger.warning(f"Quest rejected: missing or empty title — {quest_data}")
        return None

    # --- Narrative validation ---
    if not narrative or not isinstance(narrative, str) or not narrative.strip():
        logger.warning(f"Quest rejected: missing or empty narrative — title='{title}'")
        return None

    # --- Domain validation ---
    if domain not in VALID_DOMAINS:
        logger.warning(
            f"Quest '{title}': invalid domain '{domain}' — "
            f"defaulting to weakest stat '{weakest_stat}'"
        )
        domain = weakest_stat

    # --- Difficulty validation ---
    if difficulty not in VALID_DIFFICULTIES:
        logger.warning(
            f"Quest '{title}': invalid difficulty '{difficulty}' — "
            f"defaulting to 'Medium'"
        )
        difficulty = "Medium"

    return {
        "title": title.strip(),
        "narrative": narrative.strip(),
        "domain": domain,
        "difficulty": difficulty,
    }


# ---------------------------------------------------------------------------
# generate_quests — orchestrate AI call and write to Notion
# ---------------------------------------------------------------------------

def generate_quests(character_id: str) -> dict | None:
    """Generate 3 AI-powered quests for the given character.

    Steps:
    1. Check budget via ai_cost_tracker.check_budget()
    2. Build context via build_generation_context()
    3. Call OpenAI with structured JSON mode
    4. Record spend via ai_cost_tracker.record_spend()
    5. Validate each quest, look up rewards, create Notion rows
    6. Return summary dict or None on failure

    Returns:
        {"quests_created": int, "quests_rejected": int, "cost": float, "quest_ids": list}
        or None on budget cap / API failure.
    """
    from . import ai_cost_tracker

    # --- 1. Budget pre-flight ---
    # Estimate ~500 input tokens for context + system prompt, max_tokens for output
    estimated_input_tokens = 500
    if not ai_cost_tracker.check_budget(estimated_input_tokens, OPENAI_MAX_TOKENS, OPENAI_MODEL):
        logger.warning("Quest generation skipped: monthly AI budget cap reached")
        return None

    # --- 2. Build context ---
    try:
        context = build_generation_context(character_id)
    except Exception as e:
        logger.error(f"Failed to build generation context: {e}")
        return None

    weakest_stat = context["weakest_stat"]

    # --- 3. Construct prompts and call OpenAI ---
    system_prompt = (
        "You are a quest designer for an RPG life gamification system. "
        "Generate exactly 3 quests as a JSON object.\n"
        f"The player's weakest stat is {weakest_stat} — at least one quest MUST target this stat.\n"
        "Each quest needs: title (short, thematic), narrative (1-2 sentences, actionable real-world task), "
        "domain (STR/INT/WIS/VIT/CHA), difficulty (Easy/Medium/Hard/Epic).\n"
        'Return JSON: {"quests": [{"title": "...", "narrative": "...", "domain": "...", "difficulty": "..."}]}'
    )

    user_prompt = json.dumps(context, indent=2)

    try:
        from dotenv import load_dotenv
        load_dotenv()
        client = OpenAI()  # reads OPENAI_API_KEY from env

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            max_tokens=OPENAI_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        return None

    # --- 4. Record spend (FR-023: include prompt hash) ---
    import hashlib
    p_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
    usage = response.usage
    cost = ai_cost_tracker.record_spend(
        {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
        },
        model=OPENAI_MODEL,
        prompt_hash=p_hash,
    )

    # --- 5. Parse and validate ---
    try:
        raw_content = response.choices[0].message.content
        parsed = json.loads(raw_content)
        raw_quests = parsed.get("quests", [])
    except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
        logger.error(f"Failed to parse AI response: {e}")
        return None

    if not isinstance(raw_quests, list):
        logger.error(f"AI response 'quests' is not a list: {type(raw_quests)}")
        return None

    # --- 6. Validate, look up rewards, create Notion rows ---
    notion = get_notion_client()
    due_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")

    quests_created = 0
    quests_rejected = 0
    quest_ids = []

    for raw_quest in raw_quests:
        validated = validate_quest(raw_quest, weakest_stat)
        if validated is None:
            quests_rejected += 1
            continue

        # Look up rewards from difficulty
        rewards = QUEST_DIFFICULTY_REWARDS.get(validated["difficulty"], QUEST_DIFFICULTY_REWARDS["Medium"])
        base_xp = rewards["xp"]
        gold_reward = rewards["gold"]

        # Build Notion page properties
        properties = {
            "Name": {
                "title": [{"text": {"content": validated["title"]}}]
            },
            "Narrative": {
                "rich_text": [{"text": {"content": validated["narrative"]}}]
            },
            "Domain": {
                "select": {"name": validated["domain"]}
            },
            "Difficulty": {
                "select": {"name": validated["difficulty"]}
            },
            "Base XP": {
                "number": base_xp
            },
            "Gold Reward": {
                "number": gold_reward
            },
            "Source": {
                "select": {"name": "AI-Generated"}
            },
            "Status": {
                "status": {"name": "Not started"}
            },
            "Due Date": {
                "date": {"start": due_date}
            },
            "Character": {
                "relation": [{"id": character_id}]
            },
        }

        try:
            page = notion.pages.create(
                parent={"database_id": QUESTS_DB_ID},
                properties=properties,
            )
            quest_ids.append(page["id"])
            quests_created += 1
            logger.info(
                f"Quest created: '{validated['title']}' — "
                f"{validated['domain']} {validated['difficulty']} "
                f"({base_xp} XP, {gold_reward} Gold)"
            )
        except Exception as e:
            logger.error(f"Failed to create quest '{validated['title']}' in Notion: {e}")
            quests_rejected += 1

    # --- 7. Post-generation check: FR-015 weakest stat targeting ---
    created_domains = [validate_quest(q, weakest_stat)["domain"]
                       for q in raw_quests
                       if validate_quest(q, weakest_stat) is not None
                       and validate_quest(q, weakest_stat)["domain"] == weakest_stat]
    if not created_domains and quests_created > 0:
        logger.warning(
            f"FR-015: No generated quest targets weakest stat '{weakest_stat}'. "
            f"AI did not follow targeting instruction."
        )

    summary = {
        "quests_created": quests_created,
        "quests_rejected": quests_rejected,
        "cost": cost,
        "quest_ids": quest_ids,
    }

    logger.info(
        f"Quest generation complete: {quests_created} created, "
        f"{quests_rejected} rejected, cost=${cost:.6f}"
    )
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate AI-powered quests")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = generate_quests(args.character_id)
    if result is None:
        print("Quest generation failed or was blocked by budget cap.")
        return

    print(f"Quests created: {result['quests_created']}")
    print(f"Quests rejected: {result['quests_rejected']}")
    print(f"Cost: ${result['cost']:.6f}")
    for qid in result["quest_ids"]:
        print(f"  - {qid}")


if __name__ == "__main__":
    main()
