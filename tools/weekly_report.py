"""
Weekly Report — 7-day stat deltas, overdraft check, AI coaching, quest generation.

Calls daily_automation first to ensure today's snapshot exists, then computes
weekly deltas from Daily Snapshots DB, checks overdraft, generates AI coaching
briefing and quests (budget-permitting), processes completed quests, and prints
a formatted summary.

Usage:
    python -m tools.weekly_report --character-id <UUID>

Exit Codes:
    0  Success
    1  Smoke test failure
    2  Fatal error
"""
import argparse
import importlib
import os
import sys
from datetime import datetime, timezone, timedelta

from .config import get_config, OPENAI_MONTHLY_COST_CAP_USD
from .logger import get_logger

logger = get_logger(__name__)

# --- Notion DB IDs (hardcoded from verified workspace) ---
SETTINGS_DB_ID = "49bc6e3d-d39d-45f4-968f-756f779ed819"
CHARACTER_DB_ID = "f814ec57-8879-482b-81cb-e68104d252c8"
DAILY_SNAPSHOTS_DB_ID = "10168a1e-e30c-4907-8871-65519cec7abe"
STREAK_TRACKER_DB_ID = "2da610df-0671-4259-a8bb-905c396fb3d0"
QUESTS_DB_ID = "1eba33ab-6878-4e55-b07a-cb551d3af2cd"

# Fields to compute deltas for
DELTA_FIELDS = [
    "STR XP", "INT XP", "WIS XP", "VIT XP", "CHA XP",
    "Level", "Gold", "Coins", "HP",
]


# ---------------------------------------------------------------------------
# _try_import — graceful import for engines that may not exist yet
# ---------------------------------------------------------------------------

def _try_import(module_name: str, attr: str = None):
    """Try to import a module from the tools package.

    Args:
        module_name: Relative module name (e.g. ".coin_engine").
        attr: Optional attribute to extract (e.g. "check_overdraft").

    Returns:
        The module or attribute, or None if import fails.
    """
    try:
        mod = importlib.import_module(module_name, package="tools")
        if attr:
            return getattr(mod, attr, None)
        return mod
    except (ImportError, ModuleNotFoundError) as e:
        logger.warning(f"Optional import {module_name} failed: {e}")
        return None


# ---------------------------------------------------------------------------
# _get_notion_client — lazy Notion client
# ---------------------------------------------------------------------------

def _get_notion_client():
    """Return a Notion client, or None if unavailable."""
    try:
        from notion_client import Client
        return Client(auth=os.environ["NOTION_TOKEN"])
    except Exception as e:
        logger.error(f"Failed to create Notion client: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 1: Run daily automation
# ---------------------------------------------------------------------------

def run_daily_automation(character_id: str) -> bool:
    """Run daily_automation.run_pipeline to ensure today's snapshot exists."""
    daily_automation = _try_import(".daily_automation")
    if daily_automation is None:
        logger.warning("daily_automation not available — skipping daily pipeline")
        return False
    try:
        daily_automation.run_pipeline(character_id)
        logger.info("Daily automation pipeline completed")
        return True
    except Exception as e:
        logger.error(f"Daily automation failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 2: Delta calculation
# ---------------------------------------------------------------------------

def compute_deltas(notion, character_id: str, run_date: datetime) -> dict:
    """Query Daily Snapshots from the last 7 days and compute deltas.

    Returns:
        {
            "deltas": {"STR XP": int, ...},
            "snapshot_count": int,
            "period_start": str,
            "period_end": str,
        }
    """
    seven_days_ago = (run_date - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        response = notion.databases.query(
            database_id=DAILY_SNAPSHOTS_DB_ID,
            filter={
                "and": [
                    {"property": "Date", "date": {"on_or_after": seven_days_ago}},
                    {"property": "Character", "relation": {"contains": character_id}},
                ]
            },
            sorts=[{"property": "Date", "direction": "ascending"}],
        )
    except Exception as e:
        logger.error(f"Failed to query Daily Snapshots: {e}")
        return {
            "deltas": {f: 0 for f in DELTA_FIELDS},
            "snapshot_count": 0,
            "period_start": seven_days_ago,
            "period_end": run_date.strftime("%Y-%m-%d"),
        }

    snapshots = response.get("results", [])
    snapshot_count = len(snapshots)

    if snapshot_count < 2:
        logger.warning(
            f"Only {snapshot_count} snapshot(s) found — deltas will be zero"
        )
        return {
            "deltas": {f: 0 for f in DELTA_FIELDS},
            "snapshot_count": snapshot_count,
            "period_start": seven_days_ago,
            "period_end": run_date.strftime("%Y-%m-%d"),
        }

    oldest = snapshots[0]
    newest = snapshots[-1]

    deltas = {}
    for field in DELTA_FIELDS:
        old_val = _extract_number(oldest, field)
        new_val = _extract_number(newest, field)
        deltas[field] = new_val - old_val

    # Extract period dates from snapshots
    period_start = _extract_date(oldest) or seven_days_ago
    period_end = _extract_date(newest) or run_date.strftime("%Y-%m-%d")

    logger.info(
        f"Deltas computed from {snapshot_count} snapshots "
        f"({period_start} to {period_end})"
    )
    return {
        "deltas": deltas,
        "snapshot_count": snapshot_count,
        "period_start": period_start,
        "period_end": period_end,
    }


def _extract_number(snapshot: dict, field: str) -> int:
    """Extract a number property from a Notion snapshot page."""
    props = snapshot.get("properties", {})
    prop = props.get(field, {})
    val = prop.get("number")
    return val if val is not None else 0


def _extract_date(snapshot: dict) -> str | None:
    """Extract the Date property from a Notion snapshot page."""
    props = snapshot.get("properties", {})
    date_prop = props.get("Date", {}).get("date")
    if date_prop and isinstance(date_prop, dict):
        return date_prop.get("start")
    return None


# ---------------------------------------------------------------------------
# Step 3: Overdraft check
# ---------------------------------------------------------------------------

def check_overdraft(character_id: str) -> dict:
    """Check for coin overdraft and apply penalty if needed.

    Returns:
        {"checked": bool, "overdraft": bool, "penalty_applied": bool}
    """
    result = {"checked": False, "overdraft": False, "penalty_applied": False}

    check_fn = _try_import(".coin_engine", "check_overdraft")
    apply_fn = _try_import(".coin_engine", "apply_overdraft_penalty")

    if check_fn is None:
        logger.warning("coin_engine.check_overdraft not available — skipping")
        return result

    try:
        overdraft = check_fn(character_id)
        result["checked"] = True
        result["overdraft"] = bool(overdraft)

        if overdraft and apply_fn:
            apply_fn(character_id)
            result["penalty_applied"] = True
            logger.info("Overdraft detected — penalty applied")
        elif overdraft:
            logger.warning("Overdraft detected but apply_overdraft_penalty not available")
    except Exception as e:
        logger.error(f"Overdraft check failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Step 4: AI integration
# ---------------------------------------------------------------------------

def get_ai_monthly_spend(notion) -> float:
    """Read AI_MONTHLY_SPEND from Settings DB."""
    try:
        response = notion.databases.query(
            database_id=SETTINGS_DB_ID,
            filter={
                "property": "Name",
                "title": {"equals": "AI_MONTHLY_SPEND"},
            },
        )
        results = response.get("results", [])
        if not results:
            return 0.0
        value_prop = results[0]["properties"]["Value"]["rich_text"]
        if not value_prop:
            return 0.0
        return float(value_prop[0]["plain_text"])
    except Exception as e:
        logger.error(f"Failed to read AI_MONTHLY_SPEND: {e}")
        return 0.0


def run_ai_sections(character_id: str, notion) -> dict:
    """Run AI coaching and quest generation if budget allows.

    Returns:
        {
            "coaching": dict|None,
            "quests_generated": dict|None,
            "quests_processed": dict|None,
            "ai_skipped": bool,
            "ai_cost": float,
        }
    """
    result = {
        "coaching": None,
        "quests_generated": None,
        "quests_processed": None,
        "ai_skipped": False,
        "ai_cost": 0.0,
    }

    # Check budget
    spend = get_ai_monthly_spend(notion)
    cap = OPENAI_MONTHLY_COST_CAP_USD

    if spend >= cap:
        logger.warning(
            f"AI monthly spend ${spend:.4f} >= cap ${cap:.2f} — "
            f"skipping coaching and quest generation"
        )
        result["ai_skipped"] = True
    else:
        # Coaching
        coaching_engine = _try_import(".coaching_engine")
        if coaching_engine:
            try:
                briefing = coaching_engine.generate_briefing(character_id)
                result["coaching"] = briefing
                if briefing:
                    result["ai_cost"] += briefing.get("cost", 0.0)
                logger.info("Coaching briefing generated")
            except Exception as e:
                logger.error(f"Coaching engine failed: {e}")
        else:
            logger.warning("coaching_engine not available — skipping briefing")

        # Quest generation
        quest_generator = _try_import(".quest_generator")
        if quest_generator:
            try:
                gen_result = quest_generator.generate_quests(character_id)
                result["quests_generated"] = gen_result
                if gen_result:
                    result["ai_cost"] += gen_result.get("cost", 0.0)
                logger.info("Quest generation completed")
            except Exception as e:
                logger.error(f"Quest generator failed: {e}")
        else:
            logger.warning("quest_generator not available — skipping quest generation")

    # Quest processing — no AI dependency, always runs
    quest_engine = _try_import(".quest_engine")
    if quest_engine:
        try:
            proc_result = quest_engine.process_all_quests(character_id)
            result["quests_processed"] = proc_result
            logger.info("Quest processing completed")
        except Exception as e:
            logger.error(f"Quest engine failed: {e}")
    else:
        logger.warning("quest_engine not available — skipping quest processing")

    return result


# ---------------------------------------------------------------------------
# Step 5: Streak summary
# ---------------------------------------------------------------------------

def get_streak_summary(notion, character_id: str) -> dict:
    """Count active and broken streaks.

    Returns:
        {"active": int, "broken": int}
    """
    try:
        response = notion.databases.query(
            database_id=STREAK_TRACKER_DB_ID,
            filter={
                "property": "Character",
                "relation": {"contains": character_id},
            },
        )
        active = 0
        broken = 0
        for page in response.get("results", []):
            props = page.get("properties", {})
            current = props.get("Current Streak", {}).get("number", 0) or 0
            best = props.get("Best Streak", {}).get("number", 0) or 0
            if current > 0:
                active += 1
            elif best > 0:
                broken += 1
        return {"active": active, "broken": broken}
    except Exception as e:
        logger.error(f"Failed to query streaks: {e}")
        return {"active": 0, "broken": 0}


# ---------------------------------------------------------------------------
# Summary output
# ---------------------------------------------------------------------------

def format_summary(delta_info: dict, streaks: dict, ai_info: dict,
                   overdraft_info: dict) -> str:
    """Build the formatted weekly report summary string."""
    deltas = delta_info["deltas"]
    period_start = delta_info["period_start"]
    period_end = delta_info["period_end"]

    # Quest counts
    quests_completed = 0
    quests_generated = 0
    if ai_info.get("quests_processed"):
        quests_completed = ai_info["quests_processed"].get("processed", 0)
    if ai_info.get("quests_generated"):
        quests_generated = ai_info["quests_generated"].get("quests_created", 0)

    # Coaching info
    coaching_persona = "N/A"
    coaching_cost = 0.0
    if ai_info.get("coaching"):
        coaching_persona = ai_info["coaching"].get("persona", "N/A")
        coaching_cost = ai_info["coaching"].get("cost", 0.0)

    # Overdraft status
    if not overdraft_info["checked"]:
        overdraft_status = "not checked"
    elif overdraft_info["overdraft"]:
        overdraft_status = "OVERDRAFT — penalty applied" if overdraft_info["penalty_applied"] else "OVERDRAFT"
    else:
        overdraft_status = "clear"

    def _fmt_delta(val):
        return f"+{val}" if val >= 0 else str(val)

    lines = [
        "",
        "═══ Weekly Report ═══",
        f"Period: {period_start} to {period_end}",
        "── Stat Deltas ──",
        f"  STR XP: {_fmt_delta(deltas.get('STR XP', 0))}  "
        f"INT XP: {_fmt_delta(deltas.get('INT XP', 0))}  "
        f"WIS XP: {_fmt_delta(deltas.get('WIS XP', 0))}  "
        f"VIT XP: {_fmt_delta(deltas.get('VIT XP', 0))}  "
        f"CHA XP: {_fmt_delta(deltas.get('CHA XP', 0))}",
        f"  HP: {_fmt_delta(deltas.get('HP', 0))}  "
        f"Gold: {_fmt_delta(deltas.get('Gold', 0))}  "
        f"Coins: {_fmt_delta(deltas.get('Coins', 0))}",
        "── Streaks ──",
        f"  Active: {streaks['active']}  Broken: {streaks['broken']}",
        "── Quests ──",
        f"  Completed: {quests_completed}  Generated: {quests_generated}",
        "── AI Coaching ──",
        f"  Persona: {coaching_persona}",
        f"  Cost: ${ai_info['ai_cost']:.2f}",
        "── Overdraft ──",
        f"  Status: {overdraft_status}",
        "═════════════════════",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_weekly_report(character_id: str) -> int:
    """Execute the full weekly report pipeline.

    Returns:
        Exit code: 0 success, 1 smoke test fail, 2 fatal error.
    """
    run_date = datetime.now(timezone.utc)

    # --- Smoke test ---
    smoke_test = _try_import(".smoke_test")
    if smoke_test:
        try:
            smoke_test.run()
            logger.info("Smoke test passed")
        except Exception as e:
            logger.error(f"Smoke test failed: {e}")
            print(f"Smoke test failed: {e}", file=sys.stderr)
            return 1
    else:
        logger.warning("smoke_test not available — skipping")

    # --- Notion client ---
    notion = _get_notion_client()
    if notion is None:
        logger.error("Cannot create Notion client — aborting")
        return 2

    try:
        # Step 1: Run daily automation
        run_daily_automation(character_id)

        # Step 2: Compute deltas
        delta_info = compute_deltas(notion, character_id, run_date)

        # Step 3: Overdraft check
        overdraft_info = check_overdraft(character_id)

        # Step 4: AI integration
        ai_info = run_ai_sections(character_id, notion)

        # Step 5: Streak summary
        streaks = get_streak_summary(notion, character_id)

        # Step 6: Print summary
        summary = format_summary(delta_info, streaks, ai_info, overdraft_info)
        print(summary)
        logger.info(summary)

        return 0

    except Exception as e:
        logger.error(f"Weekly report fatal error: {e}")
        return 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate weekly report")
    parser.add_argument(
        "--character-id", required=True, help="Notion Character page ID"
    )
    args = parser.parse_args()

    exit_code = run_weekly_report(args.character_id)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
