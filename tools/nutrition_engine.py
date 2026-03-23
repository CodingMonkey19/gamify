"""Daily nutrition processing for Phase 4 domain modules."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
import sys
from typing import Any, Dict, Iterable, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import config
from create_databases import load_db_ids
from logger import get_logger
import notion_client_wrapper as notion_api
import xp_engine


logger = get_logger(__name__)

_ACTIVITY_LOG_DB = "Activity Log"
_CHARACTER_DB = "Character"
_MEAL_LOG_DB = "Meal Log"
_SETTINGS_DB = "Settings"

_RELATION_PROPERTIES = ("Character",)
_TITLE_PROPERTIES = ("Name", "Meal Name")
_NOTES_PROPERTIES = ("Notes",)
_MEAL_DATE_PROPERTIES = ("Date", "Logged At")
_PROTEIN_PROPERTIES = ("Protein",)
_CARB_PROPERTIES = ("Carbs",)
_FAT_PROPERTIES = ("Fat",)
_CALORIE_PROPERTIES = ("Calories",)
_TDEE_PROPERTIES = ("TDEE",)

_ACTIVITY_TYPE = "NUTRITION"
_ACTIVITY_DOMAIN = "VIT"
_MARKER_PREFIX = "nutrition_engine:date:"


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


def _date_start(prop: Optional[Dict[str, Any]]) -> str:
    if not prop or prop.get("type") != "date":
        return ""
    date_value = prop.get("date") or {}
    return date_value.get("start", "") or ""


def _relation_ids(prop: Optional[Dict[str, Any]]) -> list[str]:
    if not prop or prop.get("type") != "relation":
        return []
    return [_normalize_id(item.get("id")) for item in prop.get("relation", []) if item.get("id")]


def _parse_day(value: Optional[str | date | datetime]) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, "today"):
        return datetime.now(timezone.utc).date()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


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


def _page_date(page: Dict[str, Any], names: Iterable[str] = _MEAL_DATE_PROPERTIES) -> str:
    properties = page.get("properties", {})
    for property_name in names:
        value = _date_start(properties.get(property_name))
        if value:
            return value
    return ""


def _page_notes(page: Dict[str, Any]) -> str:
    return _rich_text_text(_first_property(page.get("properties", {}), _NOTES_PROPERTIES))


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


def _database_properties(client, db_id: str) -> Dict[str, Any]:
    try:
        database = notion_api.get_database(client, db_id)
    except Exception:
        return {}
    return database.get("properties") or {}


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


def _filter_supported_database_properties(client, db_id: str, desired: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
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


def _activity_entries(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    rows = notion_api.query_database(client, db_ids[_ACTIVITY_LOG_DB])
    return [row for row in rows if _page_matches_character(row, character_id)]


def _existing_marker(entries: Iterable[Dict[str, Any]], day_key: str) -> bool:
    marker = f"{_MARKER_PREFIX}{day_key}"
    return any(marker in _page_notes(entry) for entry in entries)


def _tdee_for_character(character_id: str, client=None, db_ids=None, cfg=None) -> int:
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    page = notion_api.get_page(client, character_id)
    tdee = _number_from_property(_first_property(page.get("properties", {}), _TDEE_PROPERTIES))
    if tdee is not None and tdee > 0:
        return int(tdee)
    return int(cfg.get("DEFAULT_TDEE", config.DEFAULT_TDEE))


def calculate_calories(protein: float, carbs: float, fat: float) -> int:
    """Calculate calories from raw macros."""
    protein = float(protein or 0)
    carbs = float(carbs or 0)
    fat = float(fat or 0)
    if protein <= 0 and carbs <= 0 and fat <= 0:
        return 0
    return math.floor((protein * 4) + (carbs * 4) + (fat * 9))


def calculate_adherence(actual_calories: float, target_tdee: float) -> float:
    """Score calorie adherence symmetrically around the target."""
    target_tdee = float(target_tdee or 0)
    if target_tdee <= 0:
        return 0.0
    actual_calories = float(actual_calories or 0)
    return max(0.0, 1.0 - abs(actual_calories - target_tdee) / target_tdee)


def _meal_payload(page: Dict[str, Any]) -> Dict[str, Any]:
    properties = page.get("properties", {})
    protein = _number_from_property(_first_property(properties, _PROTEIN_PROPERTIES)) or 0
    carbs_prop = _first_property(properties, _CARB_PROPERTIES)
    fat_prop = _first_property(properties, _FAT_PROPERTIES)
    carbs = _number_from_property(carbs_prop) or 0
    fat = _number_from_property(fat_prop) or 0
    stored_calories = _number_from_property(_first_property(properties, _CALORIE_PROPERTIES)) or 0

    if carbs_prop is None and fat_prop is None:
        calories = int(stored_calories)
    else:
        calories = calculate_calories(protein, carbs, fat)
        if calories <= 0 and stored_calories > 0:
            calories = int(stored_calories)

    return {
        "id": page["id"],
        "name": _title_text(_first_property(properties, _TITLE_PROPERTIES)),
        "protein": float(protein),
        "carbs": float(carbs),
        "fat": float(fat),
        "calories": int(calories),
        "date": _page_date(page).split("T", 1)[0],
    }


def get_daily_meals(character_id: str, meal_date: str | date | datetime, client=None, db_ids=None, cfg=None) -> list[Dict[str, Any]]:
    """Fetch all meal rows for the requested day."""
    del cfg
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    target_day = _parse_day(meal_date).isoformat()
    meals = []
    for row in notion_api.query_database(client, db_ids[_MEAL_LOG_DB]):
        if not _page_matches_character(row, character_id):
            continue
        row_date = _page_date(row)
        if not row_date:
            continue
        if _parse_day(row_date).isoformat() != target_day:
            continue
        meals.append(_meal_payload(row))
    return meals


def get_nutrition_streak(character_id: str, meal_date: str | date | datetime, client=None, db_ids=None, cfg=None) -> int:
    """Count consecutive adherent days ending at the requested day."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    target_day = _parse_day(meal_date)
    target_tdee = _tdee_for_character(character_id, client=client, db_ids=db_ids, cfg=cfg)
    adherence_threshold = 1.0 - (float(cfg.get("MACRO_TOLERANCE_PCT", config.MACRO_TOLERANCE_PCT)) / 100.0)

    daily_totals: Dict[str, int] = {}
    for row in notion_api.query_database(client, db_ids[_MEAL_LOG_DB]):
        if not _page_matches_character(row, character_id):
            continue
        row_date = _page_date(row)
        if not row_date:
            continue
        payload = _meal_payload(row)
        daily_totals[payload["date"]] = daily_totals.get(payload["date"], 0) + payload["calories"]

    streak = 0
    cursor = target_day
    while True:
        day_key = cursor.isoformat()
        calories = daily_totals.get(day_key, 0)
        if calories <= 0:
            break
        adherence = calculate_adherence(calories, target_tdee)
        if adherence < adherence_threshold:
            break
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def calculate_vit_xp(adherence: float, nutrition_streak: int, base_vit_xp: Optional[int] = None, *, cfg=None) -> int:
    """Convert nutrition adherence into VIT XP."""
    cfg = cfg or config.get_config()
    if adherence <= 0:
        return 0
    base_xp = int(base_vit_xp if base_vit_xp is not None else cfg.get("DEFAULT_HABIT_XP", config.DEFAULT_HABIT_XP))
    multiplier = float(cfg.get("NUTRITION_STREAK_MULTIPLIER", config.NUTRITION_STREAK_MULTIPLIER)) if int(nutrition_streak) >= 3 else 1.0
    return max(0, math.floor(base_xp * float(adherence) * multiplier))


def process_daily_nutrition(
    character_id: str,
    meal_date: str | date | datetime,
    client=None,
    db_ids=None,
    cfg=None,
) -> Optional[Dict[str, Any]]:
    """Process all meals for the requested day and emit one activity entry."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    day_key = _parse_day(meal_date).isoformat()

    if _existing_marker(_activity_entries(client, db_ids, character_id), day_key):
        logger.info("Nutrition for %s already processed", day_key)
        return None

    meals = get_daily_meals(character_id, day_key, client=client, db_ids=db_ids, cfg=cfg)
    if not meals:
        return None

    valid_meals = [
        meal
        for meal in meals
        if meal["calories"] > 0 or any(meal[key] > 0 for key in ("protein", "carbs", "fat"))
    ]
    if not valid_meals:
        return None

    total_calories = sum(meal["calories"] for meal in valid_meals)
    target_tdee = _tdee_for_character(character_id, client=client, db_ids=db_ids, cfg=cfg)
    adherence = calculate_adherence(total_calories, target_tdee)
    streak = get_nutrition_streak(character_id, day_key, client=client, db_ids=db_ids, cfg=cfg)
    vit_xp = calculate_vit_xp(adherence, streak, cfg=cfg)

    summary = {
        "date": day_key,
        "meal_count": len(valid_meals),
        "calories": total_calories,
        "target_tdee": target_tdee,
        "adherence": adherence,
        "streak": streak,
        "vit_xp": vit_xp,
    }

    if vit_xp <= 0:
        return summary

    activity_title_name = _title_property_name(client, db_ids[_ACTIVITY_LOG_DB], ("Activity", "Name"))
    activity_type = _choose_select_option(client, db_ids[_ACTIVITY_LOG_DB], "Type", _ACTIVITY_TYPE, "GOOD")
    activity_domain = _choose_select_option(client, db_ids[_ACTIVITY_LOG_DB], "Domain", _ACTIVITY_DOMAIN)
    marker = f"{_MARKER_PREFIX}{day_key}"
    activity_desired = {
        activity_title_name: _title_value(f"Nutrition {day_key}"),
        "Character": _relation_value([character_id]),
        "Occurred At": _date_value(day_key),
        "EXP + (Nutrition)": _number_value(vit_xp),
        "XP Earned": _number_value(vit_xp),
        "Notes": _rich_text_value(
            f"{marker} calories={total_calories} adherence={adherence:.4f} streak={streak}"
        ),
    }
    if activity_type:
        activity_desired["Type"] = _select_value(activity_type)
    if activity_domain:
        activity_desired["Domain"] = _select_value(activity_domain)

    notion_api.create_page(
        client,
        db_ids[_ACTIVITY_LOG_DB],
        _filter_supported_database_properties(client, db_ids[_ACTIVITY_LOG_DB], activity_desired),
    )
    xp_engine.update_character_stats(character_id, client=client, db_ids=db_ids, cfg=cfg)
    return summary


def _parse_args(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--date", required=True)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    result = process_daily_nutrition(args.character_id, args.date)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
