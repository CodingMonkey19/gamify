"""Streak tracking and multiplier helpers for Phase 3."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
import sys
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import config
from create_databases import load_db_ids
from logger import get_logger
import notion_client_wrapper as notion_api


logger = get_logger(__name__)

_GOOD_HABIT_DB = "Good Habit"
_STREAK_DB = "Streak Tracker"
_ACTIVITY_LOG_DB = "Activity Log"
_SETTINGS_DB = "Settings"

_RELATION_PROPERTIES = ("Character",)
_HABIT_RELATION_PROPERTIES = ("Habit", "Good Habit")
_HABIT_DOMAIN_PROPERTIES = ("Domain", "Stat")
_DATE_PROPERTIES = ("Occurred At", "Date")
_STREAK_COUNT_PROPERTIES = ("Current Streak", "Streak Days")
_BEST_STREAK_PROPERTIES = ("Best Streak",)
_CURRENT_TIER_PROPERTIES = ("Current Tier",)
_MULTIPLIER_PROPERTIES = ("Multiplier",)
_LAST_COMPLETED_PROPERTIES = ("Last Completed",)

_TIER_NAMES = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Mythic"]


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


def _find_existing_property_names(page: Dict[str, Any], candidates: Iterable[str]) -> list[str]:
    properties = page.get("properties", {})
    return [name for name in candidates if name in properties]


def _number_from_property(prop: Optional[Dict[str, Any]]) -> Optional[float]:
    if not prop:
        return None
    if prop.get("type") == "number":
        value = prop.get("number")
        if value is not None:
            return float(value)
    return None


def _checkbox_from_property(prop: Optional[Dict[str, Any]]) -> bool:
    if not prop or prop.get("type") != "checkbox":
        return False
    return bool(prop.get("checkbox"))


def _select_name(prop: Optional[Dict[str, Any]]) -> str:
    if not prop:
        return ""
    if prop.get("type") == "select":
        select = prop.get("select") or {}
        return select.get("name", "")
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
    for property_name in _RELATION_PROPERTIES:
        if normalized_character_id in _relation_ids(properties.get(property_name)):
            return True
    return False


def _activity_entries(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    rows = notion_api.query_database(client, db_ids[_ACTIVITY_LOG_DB])
    return [row for row in rows if _page_matches_character(row, character_id)]


def _habit_rows(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    rows = notion_api.query_database(client, db_ids[_GOOD_HABIT_DB])
    return [
        row for row in rows
        if _page_matches_character(row, character_id)
        and _checkbox_from_property(row.get("properties", {}).get("Active"))
    ]


def _streak_rows(client, db_ids) -> list[Dict[str, Any]]:
    return notion_api.query_database(client, db_ids[_STREAK_DB])


def _row_for_habit(rows: Iterable[Dict[str, Any]], habit_id: str) -> Optional[Dict[str, Any]]:
    normalized_habit_id = _normalize_id(habit_id)
    for row in rows:
        properties = row.get("properties", {})
        for property_name in _HABIT_RELATION_PROPERTIES:
            if normalized_habit_id in _relation_ids(properties.get(property_name)):
                return row
    return None


def _date_key(page: Dict[str, Any]) -> str:
    props = page.get("properties", {})
    for name in _DATE_PROPERTIES:
        date_value = _date_start(props.get(name))
        if date_value:
            return date_value
    return ""


def _title_value(value: str) -> Dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _relation_value(page_ids: Iterable[str]) -> Dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def _number_value(value: int | float) -> Dict[str, Any]:
    return {"number": value}


def _select_value(value: str) -> Dict[str, Any]:
    return {"select": {"name": value}}


def _date_value(value: str) -> Dict[str, Any]:
    return {"date": {"start": value}}


def _rich_text_value(value: str) -> Dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value}}]}


def _as_local_date(value: str) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value.split("T", 1)[0])


def _tier_thresholds(cfg: Dict[str, Any]) -> list[tuple[int, float]]:
    tiers = cfg.get("STREAK_TIERS", config.STREAK_TIERS)
    return sorted(((int(days), float(multiplier)) for days, multiplier in tiers.items()), key=lambda item: item[0])


def get_today(timezone_name: str | None = None, *, client=None, db_ids=None, cfg=None, now: Optional[datetime] = None) -> str:
    """Return today's date in the configured player timezone."""
    if cfg is None and (client is not None or db_ids is not None):
        cfg = _resolve_config(_resolve_client(client), _resolve_db_ids(db_ids), None)
    cfg = cfg or config.get_config()
    timezone_name = timezone_name or cfg.get("PLAYER_TIMEZONE") or os.getenv("PLAYER_TIMEZONE") or "UTC"

    try:
        zone = ZoneInfo(str(timezone_name))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid PLAYER_TIMEZONE: {timezone_name}") from exc

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(zone).date().isoformat()


def calculate_multiplier(streak_count: int, *, cfg=None) -> float:
    """Return the configured multiplier for a streak count."""
    streak_count = max(int(streak_count), 0)
    cfg = cfg or config.get_config()
    multiplier = 1.0
    for threshold, threshold_multiplier in _tier_thresholds(cfg):
        if streak_count >= threshold:
            multiplier = threshold_multiplier
    return multiplier


def get_streak_tier(count: int, *, cfg=None) -> str:
    """Return the tier name for the streak count."""
    count = max(int(count), 0)
    cfg = cfg or config.get_config()
    current_tier = "None"
    for index, (threshold, _multiplier) in enumerate(_tier_thresholds(cfg)):
        if count >= threshold:
            current_tier = _TIER_NAMES[index]
    return current_tier


def _habit_context(habit_page: Dict[str, Any]) -> Dict[str, Any]:
    properties = habit_page.get("properties", {})
    return {
        "id": habit_page["id"],
        "name": _title_text(properties.get("Name")) or "Habit",
        "domain": _select_name(_first_property(properties, _HABIT_DOMAIN_PROPERTIES)),
        "character_ids": _relation_ids(properties.get("Character")),
    }


def _streak_state_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    properties = row.get("properties", {})
    current_streak = int(_number_from_property(_first_property(properties, _STREAK_COUNT_PROPERTIES)) or 0)
    best_streak = _number_from_property(_first_property(properties, _BEST_STREAK_PROPERTIES))
    if best_streak is None:
        best_streak = current_streak
    best_streak = int(best_streak)
    tier = _select_name(_first_property(properties, _CURRENT_TIER_PROPERTIES)) or get_streak_tier(current_streak)
    multiplier = _number_from_property(_first_property(properties, _MULTIPLIER_PROPERTIES))
    if multiplier is None:
        multiplier = calculate_multiplier(current_streak)
    last_completed = _date_start(_first_property(properties, _LAST_COMPLETED_PROPERTIES))
    return {
        "streak": current_streak,
        "best": best_streak,
        "tier": tier,
        "multiplier": float(multiplier),
        "last_completed": last_completed,
    }


def _supported_create_properties(rows: Iterable[Dict[str, Any]], desired: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    rows = list(rows)
    if not rows:
        return desired
    supported = set(rows[0].get("properties", {}).keys())
    return {name: value for name, value in desired.items() if name == "Name" or name in supported}


def _existing_decay_entry(entries: Iterable[Dict[str, Any]], habit_id: str, target_date: str) -> bool:
    normalized_habit_id = _normalize_id(habit_id)
    for entry in entries:
        properties = entry.get("properties", {})
        if _select_name(properties.get("Type")) != "DECAY":
            continue
        if _date_key(entry).split("T", 1)[0] != target_date:
            continue
        for property_name in _HABIT_RELATION_PROPERTIES:
            if normalized_habit_id in _relation_ids(properties.get(property_name)):
                return True
    return False


def apply_decay(character_id: str, habit_id: str, date_value: Optional[str] = None, client=None, db_ids=None, cfg=None) -> Dict[str, Any]:
    """Reset a streak to zero without applying an XP penalty."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    target_date = date_value or get_today(client=client, db_ids=db_ids, cfg=cfg)

    streak_rows = _streak_rows(client, db_ids)
    row = _row_for_habit(streak_rows, habit_id)
    if row is None:
        return {"habit_id": habit_id, "previous_streak": 0, "previous_tier": "None"}

    state = _streak_state_from_row(row)
    updates = {}
    for property_name in _find_existing_property_names(row, _STREAK_COUNT_PROPERTIES):
        updates[property_name] = _number_value(0)
    for property_name in _find_existing_property_names(row, _CURRENT_TIER_PROPERTIES):
        updates[property_name] = _select_value("None")
    for property_name in _find_existing_property_names(row, _MULTIPLIER_PROPERTIES):
        updates[property_name] = _number_value(1.0)

    if updates:
        notion_api.update_page(client, row["id"], updates)

    if state["streak"] > 0:
        habit_page = notion_api.get_page(client, habit_id)
        habit = _habit_context(habit_page)
        entries = _activity_entries(client, db_ids, character_id)
        if not _existing_decay_entry(entries, habit_id, target_date):
            properties = {
                "Name": _title_value(f"DECAY: {habit['name']}"),
                "Type": _select_value("DECAY"),
                "Character": _relation_value([character_id]),
                "Occurred At": _date_value(target_date),
                "Notes": _rich_text_value(f"Streak decayed for {habit['name']}"),
            }
            if habit["domain"]:
                properties["Domain"] = _select_value(habit["domain"] or "VIT")
            properties["Good Habit"] = _relation_value([habit_id])
            notion_api.create_page(client, db_ids[_ACTIVITY_LOG_DB], properties)

    return {
        "habit_id": habit_id,
        "previous_streak": state["streak"],
        "previous_tier": state["tier"],
    }


def update_streak_tracker(
    habit_id: str,
    completed: bool,
    date_value: str,
    *,
    client=None,
    db_ids=None,
    cfg=None,
) -> Dict[str, Any]:
    """Create or update the streak tracker row for a habit."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    habit_page = notion_api.get_page(client, habit_id)
    habit = _habit_context(habit_page)

    streak_rows = _streak_rows(client, db_ids)
    row = _row_for_habit(streak_rows, habit_id)
    target_date = _as_local_date(date_value)

    if row is None:
        if not completed:
            return {"streak": 0, "best": 0, "tier": "None", "multiplier": 1.0}

        streak = 1
        tier = get_streak_tier(streak, cfg=cfg)
        multiplier = calculate_multiplier(streak, cfg=cfg)
        properties = {
            "Name": _title_value(f"{habit['name']} Streak"),
            "Good Habit": _relation_value([habit_id]),
            "Habit": _relation_value([habit_id]),
            "Domain": _select_value(habit["domain"] or "VIT"),
            "Current Streak": _number_value(streak),
            "Best Streak": _number_value(streak),
            "Streak Days": _number_value(streak),
            "Current Tier": _select_value(tier),
            "Multiplier": _number_value(multiplier),
            "Last Completed": _date_value(date_value),
        }
        notion_api.create_page(
            client,
            db_ids[_STREAK_DB],
            _supported_create_properties(streak_rows, properties),
        )
        return {"streak": streak, "best": streak, "tier": tier, "multiplier": multiplier}

    state = _streak_state_from_row(row)
    last_completed = _as_local_date(state["last_completed"])

    if completed:
        if last_completed == target_date:
            return {
                "streak": state["streak"],
                "best": state["best"],
                "tier": state["tier"],
                "multiplier": state["multiplier"],
            }

        if last_completed and target_date and last_completed == target_date - timedelta(days=1):
            streak = state["streak"] + 1
        else:
            streak = 1
        best = max(state["best"], streak)
        tier = get_streak_tier(streak, cfg=cfg)
        multiplier = calculate_multiplier(streak, cfg=cfg)

        updates = {}
        for property_name in _find_existing_property_names(row, _STREAK_COUNT_PROPERTIES):
            updates[property_name] = _number_value(streak)
        for property_name in _find_existing_property_names(row, _BEST_STREAK_PROPERTIES):
            updates[property_name] = _number_value(best)
        for property_name in _find_existing_property_names(row, _CURRENT_TIER_PROPERTIES):
            updates[property_name] = _select_value(tier)
        for property_name in _find_existing_property_names(row, _MULTIPLIER_PROPERTIES):
            updates[property_name] = _number_value(multiplier)
        for property_name in _find_existing_property_names(row, _LAST_COMPLETED_PROPERTIES):
            updates[property_name] = _date_value(date_value)
        if "Domain" in row.get("properties", {}):
            updates["Domain"] = _select_value(habit["domain"] or "VIT")

        notion_api.update_page(client, row["id"], updates)
        return {"streak": streak, "best": best, "tier": tier, "multiplier": multiplier}

    if last_completed and target_date and last_completed == target_date:
        return {
            "streak": state["streak"],
            "best": state["best"],
            "tier": state["tier"],
            "multiplier": state["multiplier"],
        }

    decay_result = apply_decay(
        habit["character_ids"][0] if habit["character_ids"] else "",
        habit_id,
        date_value=date_value,
        client=client,
        db_ids=db_ids,
        cfg=cfg,
    )
    return {
        "streak": 0,
        "best": state["best"],
        "tier": "None",
        "multiplier": 1.0,
        "decay": decay_result,
    }


def check_streaks(character_id: str, date_value: Optional[str] = None, client=None, db_ids=None, cfg=None) -> Dict[str, Any]:
    """Update streak tracker rows for all active habits on the target date."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    target_date = date_value or get_today(client=client, db_ids=db_ids, cfg=cfg)

    active_habits = _habit_rows(client, db_ids, character_id)
    entries = _activity_entries(client, db_ids, character_id)
    completed_habit_ids = set()
    for entry in entries:
        properties = entry.get("properties", {})
        if _select_name(properties.get("Type")) != "GOOD":
            continue
        if _date_key(entry).split("T", 1)[0] != target_date:
            continue
        for property_name in _HABIT_RELATION_PROPERTIES:
            completed_habit_ids.update(_relation_ids(properties.get(property_name)))

    details = []
    updated = 0
    decayed = 0
    for habit in active_habits:
        completed = _normalize_id(habit["id"]) in completed_habit_ids
        result = update_streak_tracker(
            habit["id"],
            completed,
            target_date,
            client=client,
            db_ids=db_ids,
            cfg=cfg,
        )
        detail = {"habit_id": habit["id"], "completed": completed, **result}
        details.append(detail)
        if completed:
            updated += 1
        elif result.get("decay"):
            decayed += 1

    return {"updated": updated, "decayed": decayed, "details": details}
