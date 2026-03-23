"""
Daily Automation Pipeline — 16-step idempotent pipeline that processes habits,
aggregates XP, updates stats, and captures a daily snapshot.

Usage:
    python -m tools.daily_automation --character-id <UUID>
    python tools/daily_automation.py --character-id <UUID>

Exit Codes:
    0   Success (some steps may have logged errors)
    1   Smoke test failure
    2   Fatal error
"""
import argparse
import importlib
import os
import sys
from datetime import date

from .config import get_config
from .logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Dynamic import helper — gracefully handles missing engines
# ---------------------------------------------------------------------------

def _try_import(module_path: str, func_name: str):
    """Try to import a function from a module. Return None if unavailable.

    Args:
        module_path: Dotted module path (e.g. "tools.habit_engine").
        func_name: Function name within the module.

    Returns:
        The function object, or None if the module/function doesn't exist.
    """
    try:
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        logger.warning(f"Engine not available: {module_path}.{func_name} — {e}")
        return None


# ---------------------------------------------------------------------------
# Pipeline step definitions
# ---------------------------------------------------------------------------

# Each tuple: (step_name, module_path, func_name, is_hard_fail)
# is_hard_fail=True means failure aborts the pipeline entirely.
PIPELINE_STEPS = [
    ("smoke_test",              ".smoke_test",          "run",                         True),
    ("load_settings",           None,                   None,                          False),
    ("good_habits",             ".habit_engine",        "process_daily_habits",        False),
    ("bad_habits",              ".habit_engine",        "process_bad_habits",          False),
    ("streak_decay",            ".streak_engine",       "check_streaks",               False),
    ("fitness_xp",              ".fitness_engine",      "process_daily_workouts",      False),
    ("nutrition_xp",            ".nutrition_engine",    "process_daily_nutrition",     False),
    ("financial_xp",            ".financial_engine",    "process_monthly_finances",    False),
    ("xp_update",               ".xp_engine",          "update_character_stats",       False),
    ("hp_check",                ".hp_engine",           "check_death",                 False),
    ("rank_check",              ".rank_engine",         "check_rank_up",               False),
    ("avatar_update",           ".avatar_renderer",     "update_character_avatar",      False),
    ("achievements",            ".achievement_engine",  "check_all_achievements",       False),
    ("chart_update",            ".chart_renderer",      "update_character_chart",       False),
    ("snapshot",                ".snapshot_engine",     "take_snapshot",                False),
    ("quest_processing",        ".quest_engine",        "process_all_quests",           False),
]


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(character_id: str) -> dict:
    """Execute the 16-step daily automation pipeline.

    Args:
        character_id: Notion page ID of the character to process.

    Returns:
        Pipeline context dict with results, errors, and step counts.

    Raises:
        SystemExit(1): If the smoke test fails.
        SystemExit(2): If a fatal, unrecoverable error occurs.
    """
    run_date = date.today()
    context = {
        "character_id": character_id,
        "run_date": run_date,
        "settings": {},
        "results": {},
        "errors": [],
        "steps_completed": 0,
        "steps_failed": 0,
        "steps_skipped": 0,
        "total_steps": len(PIPELINE_STEPS),
    }

    logger.info(f"Daily automation started — character={character_id}, date={run_date}")

    for step_index, (step_name, module_path, func_name, is_hard_fail) in enumerate(PIPELINE_STEPS, 1):
        logger.info(f"[{step_index}/{len(PIPELINE_STEPS)}] Running: {step_name}")

        # --- Step 1: Smoke test (hard fail) ---
        if step_name == "smoke_test":
            fn = _try_import("tools" + module_path, func_name) if module_path else None
            if fn is None:
                logger.error("smoke_test module not available — aborting pipeline")
                context["errors"].append(("smoke_test", "Module not available"))
                context["steps_failed"] += 1
                _print_summary(context)
                sys.exit(1)
            try:
                result = fn(character_id)
                context["results"]["smoke_test"] = result
                context["steps_completed"] += 1
                logger.info(f"  smoke_test: PASSED")
            except Exception as e:
                logger.error(f"  smoke_test: FAILED — {e}")
                context["errors"].append(("smoke_test", str(e)))
                context["steps_failed"] += 1
                _print_summary(context)
                sys.exit(1)
            continue

        # --- Step 2: Load settings (built-in) ---
        if step_name == "load_settings":
            try:
                settings = get_config()
                context["settings"] = settings
                context["results"]["load_settings"] = settings
                context["steps_completed"] += 1
                logger.info(f"  load_settings: loaded {len(settings)} settings")
            except Exception as e:
                logger.error(f"  load_settings: FAILED — {e}")
                context["errors"].append(("load_settings", str(e)))
                context["steps_failed"] += 1
            continue

        # --- Step 12: Avatar update (conditional on rank change) ---
        if step_name == "avatar_update":
            rank_result = context["results"].get("rank_check")
            rank_changed = False
            if isinstance(rank_result, dict):
                rank_changed = rank_result.get("rank_changed", False)

            if not rank_changed:
                logger.info(f"  avatar_update: SKIPPED (no rank change)")
                context["results"]["avatar_update"] = {"skipped": True, "reason": "no rank change"}
                context["steps_skipped"] += 1
                continue

            # Rank changed — proceed with avatar update
            fn = _try_import("tools" + module_path, func_name) if module_path else None
            if fn is None:
                context["steps_skipped"] += 1
                continue
            try:
                result = fn(character_id)
                context["results"]["avatar_update"] = result
                context["steps_completed"] += 1
                logger.info(f"  avatar_update: SUCCESS")
            except Exception as e:
                logger.error(f"  avatar_update: FAILED — {e}")
                context["errors"].append(("avatar_update", str(e)))
                context["steps_failed"] += 1
            continue

        # --- Step 15: Snapshot (passes run_date) ---
        if step_name == "snapshot":
            fn = _try_import("tools" + module_path, func_name) if module_path else None
            if fn is None:
                context["steps_skipped"] += 1
                continue
            try:
                result = fn(character_id, run_date)
                context["results"]["snapshot"] = result
                context["steps_completed"] += 1
                logger.info(f"  snapshot: SUCCESS")
            except Exception as e:
                logger.error(f"  snapshot: FAILED — {e}")
                context["errors"].append(("snapshot", str(e)))
                context["steps_failed"] += 1
            continue

        # --- All other steps: standard engine call ---
        fn = _try_import("tools" + module_path, func_name) if module_path else None
        if fn is None:
            context["steps_skipped"] += 1
            continue

        try:
            result = fn(character_id)
            context["results"][step_name] = result
            context["steps_completed"] += 1
            logger.info(f"  {step_name}: SUCCESS")
        except Exception as e:
            logger.error(f"  {step_name}: FAILED — {e}")
            context["errors"].append((step_name, str(e)))
            context["steps_failed"] += 1

    logger.info("Daily automation finished")
    _print_summary(context)
    return context


# ---------------------------------------------------------------------------
# Summary output
# ---------------------------------------------------------------------------

def _print_summary(context: dict) -> None:
    """Print the final summary block to stdout."""
    completed = context.get("steps_completed", 0)
    failed = context.get("steps_failed", 0)
    skipped = context.get("steps_skipped", 0)
    total = context.get("total_steps", len(PIPELINE_STEPS))
    run_date = context.get("run_date", date.today())

    # Determine snapshot status
    snapshot_result = context.get("results", {}).get("snapshot")
    if snapshot_result is None and "snapshot" in [e[0] for e in context.get("errors", [])]:
        snapshot_status = "failed"
    elif snapshot_result is None:
        snapshot_status = "skipped"
    elif isinstance(snapshot_result, dict) and snapshot_result.get("skipped"):
        snapshot_status = "skipped (already exists)"
    else:
        snapshot_status = "created"

    failed_suffix = " (logged)" if failed > 0 else ""
    skipped_suffix = " (engine not available)" if skipped > 0 else ""

    summary = (
        f"\n"
        f"{'=' * 35}\n"
        f" Daily Automation Summary\n"
        f"{'=' * 35}\n"
        f"Date: {run_date}\n"
        f"Steps completed: {completed}/{total}\n"
        f"Steps failed: {failed}{failed_suffix}\n"
        f"Steps skipped: {skipped}{skipped_suffix}\n"
        f"Snapshot: {snapshot_status}\n"
        f"{'=' * 35}\n"
    )
    print(summary)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run the daily automation pipeline for a character"
    )
    parser.add_argument(
        "--character-id",
        required=False,
        help="Notion Character page ID (falls back to CHARACTER_ID env var)",
    )
    args = parser.parse_args()

    character_id = args.character_id or os.environ.get("CHARACTER_ID")
    if not character_id:
        logger.error("No character ID provided. Use --character-id or set CHARACTER_ID env var.")
        sys.exit(2)

    try:
        context = run_pipeline(character_id)
        # Exit 0 even if some steps failed — pipeline completed
        sys.exit(0)
    except SystemExit:
        raise  # Re-raise SystemExit from smoke test or other hard failures
    except Exception as e:
        logger.error(f"Fatal error in daily automation: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
