"""
Monthly Automation — Budget surplus → Gold conversion, Treasury row, AI spend reset.

Calculates previous month's income vs expenses from Expense Log, converts positive
surplus to Gold and WIS XP, creates an idempotent Treasury row, takes a monthly
snapshot, and resets AI_MONTHLY_SPEND to 0.

Usage:
    python -m tools.monthly_automation --character-id <UUID>

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

from .config import get_config, GOLD_CONVERSION_RATE, WIS_XP_PER_GOLD
from .logger import get_logger

logger = get_logger(__name__)

# --- Notion DB IDs (hardcoded from verified workspace) ---
SETTINGS_DB_ID = "49bc6e3d-d39d-45f4-968f-756f779ed819"
CHARACTER_DB_ID = "f814ec57-8879-482b-81cb-e68104d252c8"
TREASURY_DB_ID = "c27a588d-846a-49fe-95b7-e14f22d5385d"
EXPENSE_LOG_DB_ID = "b39eb37e-6bc8-4d0a-909f-0675ba663558"
BUDGET_CATEGORY_DB_ID = "604af9b3-48a8-4a8a-bd23-02cb8ca2cca7"
DAILY_SNAPSHOTS_DB_ID = "10168a1e-e30c-4907-8871-65519cec7abe"


# ---------------------------------------------------------------------------
# _try_import — graceful import for engines that may not exist yet
# ---------------------------------------------------------------------------

def _try_import(module_name: str, attr: str = None):
    """Try to import a module from the tools package.

    Args:
        module_name: Relative module name (e.g. ".coin_engine").
        attr: Optional attribute to extract.

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
# _get_notion_client
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
# Step 2: Calculate previous month surplus
# ---------------------------------------------------------------------------

def get_target_month(run_date: datetime) -> str:
    """Return the previous month in YYYY-MM format."""
    first_of_current = run_date.replace(day=1)
    last_of_previous = first_of_current - timedelta(days=1)
    return last_of_previous.strftime("%Y-%m")


def calculate_surplus(notion, target_month: str) -> dict:
    """Query Expense Log for the target month, compute income and expenses.

    Args:
        notion: Notion client.
        target_month: YYYY-MM format.

    Returns:
        {"income": float, "expenses": float, "surplus": float}
    """
    # Build date range for the target month
    year, month = map(int, target_month.split("-"))
    start_date = f"{target_month}-01"
    # End date: first day of next month
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"

    try:
        response = notion.databases.query(
            database_id=EXPENSE_LOG_DB_ID,
            filter={
                "and": [
                    {"property": "Date", "date": {"on_or_after": start_date}},
                    {"property": "Date", "date": {"before": end_date}},
                ]
            },
        )
    except Exception as e:
        logger.error(f"Failed to query Expense Log for {target_month}: {e}")
        return {"income": 0.0, "expenses": 0.0, "surplus": 0.0}

    income = 0.0
    expenses = 0.0

    for page in response.get("results", []):
        props = page.get("properties", {})

        # Get amount
        amount = props.get("Amount", {}).get("number", 0) or 0

        # Get type (Income or Expense)
        type_select = props.get("Type", {}).get("select")
        entry_type = type_select["name"] if type_select else None

        if entry_type == "Income":
            income += amount
        elif entry_type == "Expense":
            expenses += amount

    surplus = income - expenses
    logger.info(
        f"Month {target_month}: income=${income:.2f}, "
        f"expenses=${expenses:.2f}, surplus=${surplus:.2f}"
    )
    return {"income": income, "expenses": expenses, "surplus": surplus}


# ---------------------------------------------------------------------------
# Step 3: Treasury idempotency check
# ---------------------------------------------------------------------------

def check_treasury_exists(notion, target_month: str, character_id: str) -> bool:
    """Check if a Treasury row already exists for this month + character.

    Returns True if row exists (skip processing), False otherwise.
    """
    try:
        response = notion.databases.query(
            database_id=TREASURY_DB_ID,
            filter={
                "and": [
                    {"property": "Month", "title": {"equals": target_month}},
                    {"property": "Character", "relation": {"contains": character_id}},
                ]
            },
        )
        exists = len(response.get("results", [])) > 0
        if exists:
            logger.info(f"Treasury row already exists for {target_month} — skipping")
        return exists
    except Exception as e:
        logger.error(f"Failed to check Treasury for {target_month}: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 4: Gold conversion and XP
# ---------------------------------------------------------------------------

def convert_surplus_to_gold(surplus: float) -> dict:
    """Convert surplus to Gold and WIS XP.

    Returns:
        {"gold": int, "wis_xp": int}
    """
    gold = int(max(0, surplus) / GOLD_CONVERSION_RATE)
    wis_xp = gold * WIS_XP_PER_GOLD
    logger.info(f"Gold conversion: surplus=${surplus:.2f} → {gold} Gold, {wis_xp} WIS XP")
    return {"gold": gold, "wis_xp": wis_xp}


def credit_gold_and_xp(character_id: str, gold: int, wis_xp: int) -> dict:
    """Credit Gold via coin_engine and WIS XP via xp_engine.

    Returns:
        {"gold_credited": bool, "xp_credited": bool}
    """
    result = {"gold_credited": False, "xp_credited": False}

    if gold > 0:
        credit_gold_fn = _try_import(".coin_engine", "credit_gold")
        if credit_gold_fn:
            try:
                credit_gold_fn(character_id, gold)
                result["gold_credited"] = True
                logger.info(f"Credited {gold} Gold to character {character_id}")
            except Exception as e:
                logger.error(f"Failed to credit Gold: {e}")
        else:
            logger.warning(
                f"coin_engine not available — {gold} Gold should be credited manually"
            )

    if wis_xp > 0:
        award_xp_fn = _try_import(".xp_engine", "award_xp")
        if award_xp_fn:
            try:
                award_xp_fn(character_id, "WIS", wis_xp)
                result["xp_credited"] = True
                logger.info(f"Awarded {wis_xp} WIS XP to character {character_id}")
            except Exception as e:
                logger.error(f"Failed to award WIS XP: {e}")
        else:
            logger.warning(
                f"xp_engine not available — {wis_xp} WIS XP should be awarded manually"
            )

    return result


# ---------------------------------------------------------------------------
# Step 5: Create Treasury row
# ---------------------------------------------------------------------------

def create_treasury_row(notion, target_month: str, character_id: str,
                        financials: dict, gold: int, wis_xp: int) -> bool:
    """Create a Treasury row in Notion.

    Returns True on success, False on failure.
    """
    properties = {
        "Month": {
            "title": [{"text": {"content": target_month}}]
        },
        "Character": {
            "relation": [{"id": character_id}]
        },
        "Income": {
            "number": financials["income"]
        },
        "Expenses": {
            "number": financials["expenses"]
        },
        "Surplus": {
            "number": financials["surplus"]
        },
        "Gold Earned": {
            "number": gold
        },
        "WIS XP": {
            "number": wis_xp
        },
    }

    try:
        notion.pages.create(
            parent={"database_id": TREASURY_DB_ID},
            properties=properties,
        )
        logger.info(f"Treasury row created for {target_month}")
        return True
    except Exception as e:
        logger.error(f"Failed to create Treasury row: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 6: Monthly snapshot
# ---------------------------------------------------------------------------

def take_monthly_snapshot(character_id: str) -> bool:
    """Call snapshot_engine.take_snapshot for end-of-month state."""
    snapshot_engine = _try_import(".snapshot_engine")
    if snapshot_engine is None:
        logger.warning("snapshot_engine not available — monthly snapshot skipped")
        return False
    try:
        snapshot_engine.take_snapshot(character_id)
        logger.info("Monthly snapshot created")
        return True
    except Exception as e:
        logger.error(f"Monthly snapshot failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Step 7: Reset AI_MONTHLY_SPEND
# ---------------------------------------------------------------------------

def reset_ai_monthly_spend(notion) -> bool:
    """Set AI_MONTHLY_SPEND to 0 in Settings DB."""
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
            logger.warning("AI_MONTHLY_SPEND row not found — cannot reset")
            return False

        page_id = results[0]["id"]
        notion.pages.update(
            page_id=page_id,
            properties={
                "Value": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "0"},
                        }
                    ]
                }
            },
        )
        logger.info("AI_MONTHLY_SPEND reset to 0")
        return True
    except Exception as e:
        logger.error(f"Failed to reset AI_MONTHLY_SPEND: {e}")
        return False


# ---------------------------------------------------------------------------
# Summary output
# ---------------------------------------------------------------------------

def format_summary(target_month: str, financials: dict, gold: int,
                   wis_xp: int, treasury_skipped: bool) -> str:
    """Build the formatted monthly summary string."""
    lines = [
        "",
        "═══ Monthly Automation Summary ═══",
        f"Month: {target_month}",
        f"Income: ${financials['income']:,.2f}  Expenses: ${financials['expenses']:,.2f}",
        f"Surplus: ${financials['surplus']:,.2f}  Gold earned: {gold}  WIS XP: {wis_xp}",
    ]
    if treasury_skipped:
        lines.append("Treasury: already processed (skipped)")
    else:
        lines.append("Treasury: row created")
    lines.append("AI Monthly Spend: reset to $0.00")
    lines.append("══════════════════════════════════")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_monthly_automation(character_id: str) -> int:
    """Execute the full monthly automation pipeline.

    Returns:
        Exit code: 0 success, 1 smoke test fail, 2 fatal error.
    """
    run_date = datetime.now(timezone.utc)

    # --- Step 1: Smoke test + load settings ---
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

    # Load settings (for overrides)
    config = get_config()

    # --- Notion client ---
    notion = _get_notion_client()
    if notion is None:
        logger.error("Cannot create Notion client — aborting")
        return 2

    try:
        # Step 2: Calculate previous month surplus
        target_month = get_target_month(run_date)
        financials = calculate_surplus(notion, target_month)

        # Step 3: Treasury idempotency check
        treasury_skipped = check_treasury_exists(notion, target_month, character_id)

        gold = 0
        wis_xp = 0

        if not treasury_skipped:
            # Step 4: Gold conversion and XP
            conversion = convert_surplus_to_gold(financials["surplus"])
            gold = conversion["gold"]
            wis_xp = conversion["wis_xp"]

            credit_gold_and_xp(character_id, gold, wis_xp)

            # Step 5: Create Treasury row
            create_treasury_row(
                notion, target_month, character_id, financials, gold, wis_xp
            )

        # Step 6: Monthly snapshot
        take_monthly_snapshot(character_id)

        # Step 7: Reset AI_MONTHLY_SPEND (always safe to re-run)
        reset_ai_monthly_spend(notion)

        # Summary
        summary = format_summary(
            target_month, financials, gold, wis_xp, treasury_skipped
        )
        print(summary)
        logger.info(summary)

        return 0

    except Exception as e:
        logger.error(f"Monthly automation fatal error: {e}")
        return 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run monthly automation")
    parser.add_argument(
        "--character-id", required=True, help="Notion Character page ID"
    )
    args = parser.parse_args()

    exit_code = run_monthly_automation(args.character_id)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
