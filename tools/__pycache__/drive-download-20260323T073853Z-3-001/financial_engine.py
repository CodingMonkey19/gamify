"""Monthly financial processing for Phase 4 domain modules."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import math
import os
import sys
from typing import Any, Dict, Iterable, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import coin_engine
import config
from create_databases import load_db_ids
from logger import get_logger
import notion_client_wrapper as notion_api
import xp_engine


logger = get_logger(__name__)

_ACTIVITY_LOG_DB = "Activity Log"
_BUDGET_DB = "Budget Categories"
_CHARACTER_DB = "Character"
_EXPENSE_DB = "Expense Log"
_SETTINGS_DB = "Settings"
_TREASURY_DB = "Treasury"

_RELATION_PROPERTIES = ("Character",)
_TITLE_PROPERTIES = ("Name", "Category", "Month")
_NOTES_PROPERTIES = ("Notes",)
_DATE_PROPERTIES = ("Date", "Logged At", "Occurred At", "Workout Date", "Session Date")
_CATEGORY_LIMIT_PROPERTIES = ("Monthly Limit", "Monthly Budget")
_CATEGORY_TYPE_PROPERTIES = ("Type",)
_CATEGORY_RELATION_PROPERTIES = ("Category",)
_EXPENSE_AMOUNT_PROPERTIES = ("Amount",)
_TREASURY_SURPLUS_PROPERTIES = ("Surplus", "Balance")
_TREASURY_INCOME_PROPERTIES = ("Income",)
_TREASURY_EXPENSE_PROPERTIES = ("Total Expenses",)
_TREASURY_GOLD_PROPERTIES = ("Gold Earned",)
_TREASURY_WIS_XP_PROPERTIES = ("WIS XP",)
_TREASURY_BREACH_PROPERTIES = ("Breached Categories",)

_ACTIVITY_XP_PROPERTIES = ("EXP + (Financial)", "XP Earned")
_ACTIVITY_GOLD_PROPERTIES = ("Gold Earned",)
_ACTIVITY_TYPE = "FINANCIAL"
_ACTIVITY_DOMAIN = "WIS"
_MARKER_PREFIX = "financial_engine:month:"


def _normalize_id(value: Optional[str]) -> str:
    return (value or "").replace("-", "")


def _resolve_client(client=None):
    return client if client is not None else notion_api.get_client()


def _resolve_db_ids(db_ids=None):
    return db_ids if db_ids is not None else load_db_ids()


def _resolve_config(client, db_ids, cfg=None):
    if cfg is not None:
        return cfg
    return config.get_config(
        notion_client=client,
        settings_db_id=db_ids.get(_SETTINGS_DB),
    )


def _first_property(properties: Dict[str, Any], names: Iterable[str]) -> Optional[Dict[str, Any]]:
    for name in names:
        if name in properties:
            return properties[name]
    return None


def _number_from_property(prop: Optional[Dict[str, Any]]) -> Optional[float]:
    if not prop:
        return None
    if prop.get("type") == "number":
        value = prop.get("number")
        if value is not None:
            return float(value)
    if prop.get("type") == "formula":
        formula = prop.get("formula", {})
        if formula.get("type") == "number" and formula.get("number") is not None:
            return float(formula["number"])
    return None


def _select_name(prop: Optional[Dict[str, Any]]) -> str:
    if not prop:
        return ""
    if prop.get("type") == "select":
        select = prop.get("select") or {}
        return select.get("name", "")
    if prop.get("type") == "status":
        status = prop.get("status") or {}
        return status.get("name", "")
    return ""


def _title_text(prop: Optional[Dict[str, Any]]) -> str:
    if not prop:
        return ""
    if prop.get("type") == "title":
        parts = prop.get("title", [])
    elif prop.get("type") == "rich_text":
        parts = prop.get("rich_text", [])
    else:
        return ""
    return "".join(part.get("plain_text", "") for part in parts)


def _rich_text_text(prop: Optional[Dict[str, Any]]) -> str:
    if not prop or prop.get("type") != "rich_text":
        return ""
    return "".join(part.get("plain_text", "") for part in prop.get("rich_text", []))


def _date_start(prop: Optional[Dict[str, Any]]) -> str:
    if not prop or prop.get("type") != "date":
        return ""
    date_value = prop.get("date") or {}
    return date_value.get("start", "") or ""


def _relation_ids(prop: Optional[Dict[str, Any]]) -> list[str]:
    if not prop or prop.get("type") != "relation":
        return []
    return [_normalize_id(item.get("id")) for item in prop.get("relation", []) if item.get("id")]


def _page_matches_character(page: Dict[str, Any], character_id: str) -> bool:
    normalized_character_id = _normalize_id(character_id)
    properties = page.get("properties", {})
    matched_any = False
    for property_name in _RELATION_PROPERTIES:
        relation_ids = _relation_ids(properties.get(property_name))
        if relation_ids:
            matched_any = True
            if normalized_character_id in relation_ids:
                return True
    return not matched_any


def _title_value(value: str) -> Dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _select_value(value: str) -> Dict[str, Any]:
    return {"select": {"name": value}}


def _number_value(value: int | float) -> Dict[str, Any]:
    return {"number": value}


def _relation_value(page_ids: Iterable[str]) -> Dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def _rich_text_value(value: str) -> Dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value}}]}


def _date_value(value: str) -> Dict[str, Any]:
    return {"date": {"start": value}}


def _month_key(year: int, month: int) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def _database_properties(client, db_id: str) -> Dict[str, Any]:
    try:
        database = notion_api.get_database(client, db_id)
    except Exception:
        return {}
    return database.get("properties") or {}


def _supported_property_names(client, db_id: str) -> set[str]:
    return set(_database_properties(client, db_id).keys())


def _title_property_name(client, db_id: str, candidates: Iterable[str]) -> str:
    properties = _database_properties(client, db_id)
    for name, prop in properties.items():
        if prop.get("type") == "title":
            return name
    for candidate in candidates:
        if candidate in properties:
            return candidate
    return next(iter(candidates), "Name")


def _select_options(client, db_id: str, property_name: str) -> set[str]:
    prop = _database_properties(client, db_id).get(property_name) or {}
    if prop.get("type") == "select":
        return {option.get("name", "") for option in prop.get("select", {}).get("options", []) if option.get("name")}
    if prop.get("type") == "status":
        return {option.get("name", "") for option in prop.get("status", {}).get("options", []) if option.get("name")}
    return set()


def _choose_select_option(client, db_id: str, property_name: str, *candidates: str) -> str:
    options = _select_options(client, db_id, property_name)
    if not options:
        return next((candidate for candidate in candidates if candidate), "")
    for candidate in candidates:
        if candidate and candidate in options:
            return candidate
    return ""


def _filter_supported_properties(client, db_id: str, desired: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    properties = _database_properties(client, db_id)
    if not properties:
        return desired

    filtered = {}
    for name, value in desired.items():
        schema_prop = properties.get(name)
        if not schema_prop:
            continue
        if "select" in value:
            select_name = (value.get("select") or {}).get("name", "")
            options = _select_options(client, db_id, name)
            if options and select_name not in options:
                continue
        filtered[name] = value
    return filtered


def _page_date(page: Dict[str, Any]) -> str:
    properties = page.get("properties", {})
    for property_name in _DATE_PROPERTIES:
        value = _date_start(properties.get(property_name))
        if value:
            return value
    return ""


def _page_title(page: Dict[str, Any]) -> str:
    properties = page.get("properties", {})
    for property_name in _TITLE_PROPERTIES:
        value = _title_text(properties.get(property_name))
        if value:
            return value
    return notion_api.get_page_title(page)


def _page_notes(page: Dict[str, Any]) -> str:
    return _rich_text_text(_first_property(page.get("properties", {}), _NOTES_PROPERTIES))


def _activity_entries(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    rows = notion_api.query_database(client, db_ids[_ACTIVITY_LOG_DB])
    return [row for row in rows if _page_matches_character(row, character_id)]


def _treasury_rows(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    rows = notion_api.query_database(client, db_ids[_TREASURY_DB])
    return [row for row in rows if _page_matches_character(row, character_id)]


def _existing_month_marker(entries: Iterable[Dict[str, Any]], month_key: str) -> bool:
    marker = f"{_MARKER_PREFIX}{month_key}"
    for entry in entries:
        if marker in _page_notes(entry):
            return True
    return False


def _tdee_for_character(character_id: str, client=None, db_ids=None, cfg=None) -> int:
    del character_id  # phase 4 financial engine does not need TDEE
    del client
    del db_ids
    del cfg
    return 0


def get_budget_categories(character_id: str, client=None, db_ids=None, cfg=None) -> list[dict]:
    """Fetch budget categories for the character."""
    del cfg
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    rows = notion_api.query_database(client, db_ids[_BUDGET_DB])
    categories = []
    for row in rows:
        if not _page_matches_character(row, character_id):
            continue
        properties = row.get("properties", {})
        limit_value = _number_from_property(_first_property(properties, _CATEGORY_LIMIT_PROPERTIES)) or 0
        categories.append(
            {
                "id": row["id"],
                "name": _page_title(row) or "Budget Category",
                "monthly_limit": float(limit_value),
                "type": _select_name(_first_property(properties, _CATEGORY_TYPE_PROPERTIES)),
            }
        )
    return categories


def get_monthly_expenses(character_id: str, year: int, month: int, client=None, db_ids=None, cfg=None) -> list[dict]:
    """Fetch and aggregate expenses for the requested month."""
    del cfg
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    rows = notion_api.query_database(client, db_ids[_EXPENSE_DB])
    category_cache: Dict[str, str] = {}
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not _page_matches_character(row, character_id):
            continue
        entry_date = _page_date(row)
        if not entry_date:
            continue
        entry_datetime = datetime.fromisoformat(entry_date.replace("Z", "+00:00"))
        if entry_datetime.year != int(year) or entry_datetime.month != int(month):
            continue

        properties = row.get("properties", {})
        amount = _number_from_property(_first_property(properties, _EXPENSE_AMOUNT_PROPERTIES)) or 0
        category_ids = _relation_ids(_first_property(properties, _CATEGORY_RELATION_PROPERTIES))
        category_id = category_ids[0] if category_ids else "uncategorized"

        if category_id not in category_cache:
            if category_ids:
                category_cache[category_id] = notion_api.get_page_title(notion_api.get_page(client, category_ids[0])) or "Uncategorized"
            else:
                category_cache[category_id] = "Uncategorized"

        if category_id not in grouped:
            grouped[category_id] = {
                "category_id": category_id,
                "category_name": category_cache[category_id],
                "total": 0.0,
            }
        grouped[category_id]["total"] += float(amount)
    return list(grouped.values())


def calculate_monthly_summary(categories: list, expenses: list, monthly_income: float, *, cfg=None) -> dict:
    """Calculate the financial summary for the month."""
    cfg = cfg or config.get_config()
    expense_lookup = {expense["category_id"]: float(expense["total"]) for expense in expenses}
    total_expenses = sum(float(expense["total"]) for expense in expenses)
    category_summaries = []
    breached_count = 0

    for category in categories:
        monthly_limit = float(category.get("monthly_limit") or 0)
        if monthly_limit <= 0:
            continue
        spent = float(expense_lookup.get(category["id"], 0))
        surplus = monthly_limit - spent
        breached = spent > monthly_limit
        if breached:
            breached_count += 1
        category_summaries.append(
            {
                "id": category["id"],
                "name": category.get("name", ""),
                "type": category.get("type", ""),
                "limit": monthly_limit,
                "spent": spent,
                "surplus": surplus,
                "breached": breached,
            }
        )

    overall_surplus = float(monthly_income) - total_expenses
    conversion_rate = max(int(cfg.get("GOLD_CONVERSION_RATE", config.GOLD_CONVERSION_RATE)), 1)
    gold_earned = math.floor(max(0, overall_surplus) / conversion_rate)
    wis_xp_per_gold = max(int(cfg.get("WIS_XP_PER_GOLD", config.WIS_XP_PER_GOLD)), 0)
    positive_wis_xp = math.floor(gold_earned * wis_xp_per_gold)
    breach_penalty = int(cfg.get("BUDGET_BREACH_XP_PENALTY", config.BUDGET_BREACH_XP_PENALTY))
    net_wis_xp = max(0, positive_wis_xp + (breached_count * breach_penalty))

    return {
        "income": float(monthly_income),
        "total_expenses": total_expenses,
        "surplus": overall_surplus,
        "categories": sorted(category_summaries, key=lambda item: item["name"]),
        "gold_earned": gold_earned,
        "wis_xp": net_wis_xp,
        "positive_wis_xp": positive_wis_xp,
        "breached_count": breached_count,
    }


def process_monthly_finances(
    character_id: str,
    year: int,
    month: int,
    client=None,
    db_ids=None,
    cfg=None,
    *,
    today: Optional[date] = None,
) -> Optional[dict]:
    """Run end-to-end monthly finance processing."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    today = today or datetime.now(timezone.utc).date()
    if (int(year), int(month)) >= (today.year, today.month):
        logger.info("Skipping incomplete month %s-%s", year, month)
        return None

    month_key = _month_key(year, month)
    treasury_rows = _treasury_rows(client, db_ids, character_id)
    for row in treasury_rows:
        if _page_title(row) == month_key:
            logger.info("Treasury row for %s already exists", month_key)
            return None

    activity_entries = _activity_entries(client, db_ids, character_id)
    if _existing_month_marker(activity_entries, month_key):
        logger.info("Financial activity for %s already exists", month_key)
        return None

    categories = get_budget_categories(character_id, client=client, db_ids=db_ids, cfg=cfg)
    expenses = get_monthly_expenses(character_id, year, month, client=client, db_ids=db_ids, cfg=cfg)
    monthly_income = float(cfg.get("MONTHLY_INCOME", config.MONTHLY_INCOME) or 0)
    summary = calculate_monthly_summary(categories, expenses, monthly_income, cfg=cfg)
    summary["month"] = month_key

    if summary["income"] <= 0 and summary["total_expenses"] <= 0:
        logger.info("No income or expenses for %s; skipping Treasury row", month_key)
        return None

    treasury_title_name = _title_property_name(client, db_ids[_TREASURY_DB], ("Month", "Name"))
    treasury_desired = {
        treasury_title_name: _title_value(month_key),
        "Character": _relation_value([character_id]),
        "Income": _number_value(summary["income"]),
        "Total Expenses": _number_value(summary["total_expenses"]),
        "Expenses": _number_value(summary["total_expenses"]),
        "Surplus": _number_value(summary["surplus"]),
        "Balance": _number_value(summary["surplus"]),
        "Gold Earned": _number_value(summary["gold_earned"]),
        "WIS XP": _number_value(summary["wis_xp"]),
        "Breached Categories": _number_value(summary["breached_count"]),
        "Notes": _rich_text_value(json.dumps(summary, sort_keys=True)),
    }
    notion_api.create_page(
        client,
        db_ids[_TREASURY_DB],
        _filter_supported_properties(client, db_ids[_TREASURY_DB], treasury_desired),
    )

    marker = f"{_MARKER_PREFIX}{month_key}"
    if summary["wis_xp"] > 0:
        activity_title_name = _title_property_name(client, db_ids[_ACTIVITY_LOG_DB], ("Activity", "Name"))
        activity_type = _choose_select_option(client, db_ids[_ACTIVITY_LOG_DB], "Type", _ACTIVITY_TYPE, "GOOD")
        activity_domain = _choose_select_option(client, db_ids[_ACTIVITY_LOG_DB], "Domain", _ACTIVITY_DOMAIN)
        activity_desired = {
            "Character": _relation_value([character_id]),
            "Occurred At": _date_value(f"{month_key}-01"),
            "EXP + (Financial)": _number_value(summary["wis_xp"]),
            "XP Earned": _number_value(summary["wis_xp"]),
            "Gold Earned": _number_value(summary["gold_earned"]),
            "Notes": _rich_text_value(
                f"{marker} surplus={summary['surplus']:.2f} breached={summary['breached_count']}"
            ),
        }
        activity_desired[activity_title_name] = _title_value(f"Financial {month_key}")
        if activity_type:
            activity_desired["Type"] = _select_value(activity_type)
        if activity_domain:
            activity_desired["Domain"] = _select_value(activity_domain)
        notion_api.create_page(
            client,
            db_ids[_ACTIVITY_LOG_DB],
            _filter_supported_properties(client, db_ids[_ACTIVITY_LOG_DB], activity_desired),
        )
        xp_engine.update_character_stats(character_id, client=client, db_ids=db_ids, cfg=cfg)

    if summary["gold_earned"] > 0:
        coin_engine.add_gold(character_id, summary["gold_earned"], client=client, db_ids=db_ids)

    return summary


def _parse_args(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    result = process_monthly_finances(
        args.character_id,
        args.year,
        args.month,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
