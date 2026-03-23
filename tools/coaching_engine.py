"""
Coaching Engine — Multi-persona AI coaching with weekly briefings.
Rotates 3 personas in round-robin: Wartime CEO -> Methodical Analyst -> Quest Master.

Usage:
    python -m tools.coaching_engine --character-id <ID>
"""
import argparse
import json
from datetime import datetime, timezone, timedelta

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from .config import OPENAI_MODEL, OPENAI_MAX_TOKENS, STATS
from .logger import get_logger
from . import ai_cost_tracker

logger = get_logger(__name__)

# --- Notion DB IDs (hardcoded from verified workspace) ---
SETTINGS_DB_ID = "49bc6e3d-d39d-45f4-968f-756f779ed819"
CHARACTER_DB_ID = "f814ec57-8879-482b-81cb-e68104d252c8"
ACTIVITY_LOG_DB_ID = "caa7198e-e6c0-4d6a-948b-89b4cd0eb06f"
STREAK_TRACKER_DB_ID = "2da610df-0671-4259-a8bb-905c396fb3d0"
QUESTS_DB_ID = "1eba33ab-6878-4e55-b07a-cb551d3af2cd"

# --- Personas ---
PERSONAS = {
    "wartime_ceo": {
        "name": "Wartime CEO",
        "system_prompt": (
            "You are the Wartime CEO — a direct, commanding coach who doesn't "
            "sugarcoat. You call out weaknesses bluntly, demand accountability, "
            "and push for immediate action. Your tone is urgent and action-oriented. "
            "Focus on what's failing and what needs to change NOW. You respond in "
            "JSON with keys: greeting, observations (array of strings), "
            "recommendations (array of strings), encouragement (string)."
        ),
    },
    "methodical_analyst": {
        "name": "Methodical Analyst",
        "system_prompt": (
            "You are the Methodical Analyst — a calm, data-driven coach who finds "
            "patterns others miss. You analyze trends, correlations, and anomalies "
            "in the player's data. Your tone is measured and intellectual. Focus on "
            "what the numbers reveal about habits and progress. You respond in JSON "
            "with keys: greeting, observations (array of strings), recommendations "
            "(array of strings), encouragement (string)."
        ),
    },
    "quest_master": {
        "name": "Quest Master",
        "system_prompt": (
            "You are the Quest Master — an RPG narrator who treats the player as a "
            "hero on an epic journey. You frame recommendations as quest objectives, "
            "call habits 'training regimens', and treat stats as powers. Your tone "
            "is narrative and encouraging. Focus on the adventure and growth. You "
            "respond in JSON with keys: greeting, observations (array of strings), "
            "recommendations (array of strings), encouragement (string)."
        ),
    },
}
ROTATION_ORDER = ["wartime_ceo", "methodical_analyst", "quest_master"]

# Required keys in the briefing JSON returned by the AI
BRIEFING_KEYS = {"greeting", "observations", "recommendations", "encouragement"}


def _get_notion_client():
    """Lazy import of notion_client to avoid circular imports."""
    try:
        from .notion_client import get_notion_client
        return get_notion_client()
    except ImportError:
        logger.warning("notion_client not available — Notion calls will be skipped")
        return None


# ---------------------------------------------------------------------------
# 1. get_next_persona
# ---------------------------------------------------------------------------

def get_next_persona() -> str:
    """Read LAST_COACH_PERSONA from Settings DB, return the next in rotation.

    If the setting is empty, missing, or invalid, defaults to the first
    persona in ROTATION_ORDER ('wartime_ceo').
    """
    notion = _get_notion_client()
    if notion is None:
        logger.warning("Notion unavailable — defaulting to first persona")
        return ROTATION_ORDER[0]

    try:
        response = notion.databases.query(
            database_id=SETTINGS_DB_ID,
            filter={
                "property": "Name",
                "title": {"equals": "LAST_COACH_PERSONA"},
            },
        )

        results = response.get("results", [])
        if not results:
            logger.info("LAST_COACH_PERSONA not found in Settings DB — starting at first persona")
            return ROTATION_ORDER[0]

        page = results[0]
        value_prop = page["properties"]["Value"]["rich_text"]
        if not value_prop:
            logger.info("LAST_COACH_PERSONA is empty — starting at first persona")
            return ROTATION_ORDER[0]

        last_persona = value_prop[0]["plain_text"].strip()

        if last_persona not in ROTATION_ORDER:
            logger.warning(
                f"LAST_COACH_PERSONA '{last_persona}' is invalid — starting at first persona"
            )
            return ROTATION_ORDER[0]

        current_index = ROTATION_ORDER.index(last_persona)
        next_index = (current_index + 1) % len(ROTATION_ORDER)
        next_persona = ROTATION_ORDER[next_index]

        logger.info(f"Persona rotation: {last_persona} -> {next_persona}")
        return next_persona

    except Exception as e:
        logger.error(f"Failed to read LAST_COACH_PERSONA: {e}")
        return ROTATION_ORDER[0]


def _update_last_persona(persona_key: str) -> None:
    """Write the persona key back to LAST_COACH_PERSONA in Settings DB."""
    notion = _get_notion_client()
    if notion is None:
        logger.warning("Notion unavailable — cannot persist persona rotation")
        return

    try:
        response = notion.databases.query(
            database_id=SETTINGS_DB_ID,
            filter={
                "property": "Name",
                "title": {"equals": "LAST_COACH_PERSONA"},
            },
        )

        results = response.get("results", [])
        if not results:
            logger.error("LAST_COACH_PERSONA row not found — cannot update")
            return

        page_id = results[0]["id"]
        notion.pages.update(
            page_id=page_id,
            properties={
                "Value": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": persona_key},
                        }
                    ]
                }
            },
        )
        logger.info(f"Updated LAST_COACH_PERSONA to '{persona_key}'")

    except Exception as e:
        logger.error(f"Failed to update LAST_COACH_PERSONA: {e}")


# ---------------------------------------------------------------------------
# 2. build_coaching_context
# ---------------------------------------------------------------------------

def build_coaching_context(character_id: str) -> dict:
    """Gather weekly metrics from multiple Notion DBs for the coaching prompt.

    Returns a dict with:
        - character_stats: dict of stat XPs, HP, Gold, Coins, level, rank
        - weekly_xp: dict of domain -> XP earned in last 7 days
        - active_streaks: list of active streak dicts (Current Streak > 0)
        - broken_streaks: list of recently broken streak dicts (Current Streak = 0, Best Streak > 0)
        - quests_completed_this_week: int
        - quests_total: int
    """
    notion = _get_notion_client()
    if notion is None:
        logger.warning("Notion unavailable — returning empty context")
        return {}

    context = {}

    # --- Character stats ---
    try:
        char_response = notion.pages.retrieve(page_id=character_id)
        props = char_response.get("properties", {})

        stat_xps = {}
        for stat in STATS:
            xp_prop = props.get(f"{stat} XP", {})
            stat_xps[stat] = xp_prop.get("number", 0) or 0

        context["character_stats"] = {
            "stat_xps": stat_xps,
            "hp": (props.get("Current HP", {}).get("number", 0) or 0),
            "max_hp": (props.get("Max HP", {}).get("number", 0) or 0),
            "gold": (props.get("Gold", {}).get("number", 0) or 0),
            "coins": (props.get("Current Coins", {}).get("number", 0) or 0),
            "level": (props.get("Player Level", {}).get("number", 0) or 0),
            "rank": _extract_select(props.get("Current Rank", {})),
        }
    except Exception as e:
        logger.error(f"Failed to read character stats: {e}")
        context["character_stats"] = {}

    # --- Activity Log: last 7 days ---
    try:
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        log_response = notion.databases.query(
            database_id=ACTIVITY_LOG_DB_ID,
            filter={
                "and": [
                    {"property": "Character", "relation": {"contains": character_id}},
                    {"property": "Date", "date": {"on_or_after": seven_days_ago}},
                ]
            },
        )

        weekly_xp = {}
        for page in log_response.get("results", []):
            p = page.get("properties", {})
            domain = _extract_select(p.get("Domain", {}))
            xp_delta = p.get("EXP + (Quest)", {}).get("number", 0) or 0
            if domain:
                weekly_xp[domain] = weekly_xp.get(domain, 0) + xp_delta

        context["weekly_xp"] = weekly_xp
    except Exception as e:
        logger.error(f"Failed to read Activity Log: {e}")
        context["weekly_xp"] = {}

    # --- Streak Tracker ---
    try:
        streak_response = notion.databases.query(
            database_id=STREAK_TRACKER_DB_ID,
            filter={
                "property": "Character",
                "relation": {"contains": character_id},
            },
        )

        active_streaks = []
        broken_streaks = []
        for page in streak_response.get("results", []):
            p = page.get("properties", {})
            name_title = p.get("Name", {}).get("title", [])
            name = name_title[0]["plain_text"] if name_title else "Unknown"
            current = p.get("Current Streak", {}).get("number", 0) or 0
            best = p.get("Best Streak", {}).get("number", 0) or 0
            domain = _extract_select(p.get("Domain", {}))

            entry = {"name": name, "current": current, "best": best, "domain": domain}

            if current > 0:
                active_streaks.append(entry)
            elif best > 0:
                broken_streaks.append(entry)

        context["active_streaks"] = active_streaks
        context["broken_streaks"] = broken_streaks
    except Exception as e:
        logger.error(f"Failed to read Streak Tracker: {e}")
        context["active_streaks"] = []
        context["broken_streaks"] = []

    # --- Quests ---
    try:
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        # Completed this week
        completed_response = notion.databases.query(
            database_id=QUESTS_DB_ID,
            filter={
                "and": [
                    {"property": "Character", "relation": {"contains": character_id}},
                    {"property": "Status", "status": {"equals": "Done"}},
                    {"property": "Completed Date", "date": {"on_or_after": seven_days_ago}},
                ]
            },
        )
        context["quests_completed_this_week"] = len(completed_response.get("results", []))

        # Total quests (all statuses)
        total_response = notion.databases.query(
            database_id=QUESTS_DB_ID,
            filter={
                "property": "Character",
                "relation": {"contains": character_id},
            },
        )
        context["quests_total"] = len(total_response.get("results", []))

    except Exception as e:
        logger.error(f"Failed to read Quests DB: {e}")
        context["quests_completed_this_week"] = 0
        context["quests_total"] = 0

    logger.info(f"Coaching context built for character {character_id}")
    return context


def _extract_select(prop: dict) -> str | None:
    """Extract the name from a Notion select property, or None."""
    select = prop.get("select")
    if select and isinstance(select, dict):
        return select.get("name")
    return None


# ---------------------------------------------------------------------------
# 3. generate_briefing
# ---------------------------------------------------------------------------

def generate_briefing(character_id: str) -> dict | None:
    """Generate a weekly coaching briefing for the given character.

    Flow:
        1. Pre-flight budget check via ai_cost_tracker.check_budget()
        2. Determine next persona via get_next_persona()
        3. Build coaching context via build_coaching_context()
        4. Call OpenAI with persona system prompt + metrics (JSON mode)
        5. Record actual spend via ai_cost_tracker.record_spend()
        6. Update LAST_COACH_PERSONA in Settings DB
        7. Parse and validate the briefing JSON

    Returns:
        {"persona": str, "briefing": dict, "cost": float} on success.
        None on budget cap exceeded or API failure.
    """
    # 1. Budget check
    # Estimate ~500 input tokens (system + context), max output from config
    estimated_input_tokens = 500
    if not ai_cost_tracker.check_budget(estimated_input_tokens, OPENAI_MAX_TOKENS, OPENAI_MODEL):
        logger.warning("Coaching briefing skipped — monthly AI budget cap reached")
        return None

    # 2. Get next persona
    persona_key = get_next_persona()
    persona = PERSONAS[persona_key]

    # 3. Build context
    context = build_coaching_context(character_id)

    # 4. Call OpenAI
    try:
        client = OpenAI()
        user_message = (
            f"Here are the player's weekly metrics:\n"
            f"{json.dumps(context, indent=2, default=str)}\n\n"
            f"Provide your coaching briefing as JSON."
        )

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": persona["system_prompt"]},
                {"role": "user", "content": user_message},
            ],
            max_tokens=OPENAI_MAX_TOKENS,
            response_format={"type": "json_object"},
        )

        # 5. Record spend (FR-023: include prompt hash + persona)
        import hashlib
        p_hash = hashlib.sha256(persona["system_prompt"].encode()).hexdigest()[:12]
        usage = response.usage
        cost = ai_cost_tracker.record_spend(
            {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
            },
            model=OPENAI_MODEL,
            prompt_hash=f"{persona_key}:{p_hash}",
        )

        # 6. Update persona rotation
        _update_last_persona(persona_key)

        # 7. Parse and validate briefing
        raw_content = response.choices[0].message.content
        briefing = json.loads(raw_content)

        # Validate required keys
        missing = BRIEFING_KEYS - set(briefing.keys())
        if missing:
            logger.warning(f"Briefing missing keys {missing} — filling with defaults")
            for key in missing:
                if key in ("observations", "recommendations"):
                    briefing[key] = []
                else:
                    briefing[key] = ""

        # Validate types
        if not isinstance(briefing.get("observations"), list):
            briefing["observations"] = [str(briefing["observations"])]
        if not isinstance(briefing.get("recommendations"), list):
            briefing["recommendations"] = [str(briefing["recommendations"])]
        if not isinstance(briefing.get("greeting"), str):
            briefing["greeting"] = str(briefing.get("greeting", ""))
        if not isinstance(briefing.get("encouragement"), str):
            briefing["encouragement"] = str(briefing.get("encouragement", ""))

        result = {
            "persona": persona["name"],
            "briefing": briefing,
            "cost": cost,
        }

        logger.info(
            f"Coaching briefing generated: persona={persona['name']}, "
            f"cost=${cost:.6f}, observations={len(briefing['observations'])}, "
            f"recommendations={len(briefing['recommendations'])}"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse briefing JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate AI coaching briefing")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = generate_briefing(args.character_id)

    if result is None:
        print("Briefing generation failed or budget exceeded. Check logs.")
        return

    print(f"Persona: {result['persona']}")
    print(f"Cost: ${result['cost']:.6f}")
    print()

    briefing = result["briefing"]
    print(f"Greeting: {briefing['greeting']}")
    print()

    print("Observations:")
    for obs in briefing["observations"]:
        print(f"  - {obs}")
    print()

    print("Recommendations:")
    for rec in briefing["recommendations"]:
        print(f"  - {rec}")
    print()

    print(f"Encouragement: {briefing['encouragement']}")


if __name__ == "__main__":
    main()
