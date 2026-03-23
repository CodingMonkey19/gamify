"""Daily habit processing for Phase 3 progression."""

from __future__ import annotations

from datetime import date, timedelta
import math
import os
import sys
from typing import Any, Dict, Iterable, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import config
from create_databases import load_db_ids
import hp_engine
from logger import get_logger
import notion_client_wrapper as notion_api
import streak_engine
import xp_engine


logger = get_logger(__name__)

_ACTIVITY_LOG_DB = "Activity Log"
_GOOD_HABIT_DB = "Good Habit"
_BAD_HABIT_DB = "Bad Habit"
_SETTINGS_DB = "Settings"

_RELATION_PROPERTIES = ("Character",)
_GOOD_HABIT_RELATION_PROPERTIES = ("Good Habit", "Habit")
_BAD_HABIT_RELATION_PROPERTIES = ("Bad Habit",)
_DOMAIN_PROPERTIES = ("Domain", "Stat")
_GOOD_HABIT_XP_PROPERTIES = ("EXP Earn", "XP Reward")
_BAD_HABIT_DAMAGE_PROPERTIES = ("HP Damage", "HP Penalty")
_ACTIVITY_DATE_PROPERTIES = ("Occurred At", "Date")
_ACTIVITY_GOOD_XP_PROPERTIES = ("EXP + (Habit)", "XP Earned")
_ACTIVE_PROPERTIES = ("Active",)
_NOTES_PROPERTIES = ("Notes",)

_XP_GRANT_MARKER_PREFIX = "habit_engine:xp:"
_BAD_DAMAGE_MARKER_PREFIX = "raw:"


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
    for property_name in _RELATION_PROPERTIES:
        if normalized_character_id in _relation_ids(page.get("properties", {}).get(property_name)):
            return True
    return False


def _query_rows(client, db_id: str) -> list[Dict[str, Any]]:
    return notion_api.query_database(client, db_id)


def _activity_entries(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    rows = _query_rows(client, db_ids[_ACTIVITY_LOG_DB])
    return [row for row in rows if _page_matches_character(row, character_id)]


def _date_key(page: Dict[str, Any]) -> str:
    props = page.get("properties", {})
    for name in _ACTIVITY_DATE_PROPERTIES:
        date_value = _date_start(props.get(name))
        if date_value:
            return date_value.split("T", 1)[0]
    return ""


def _entry_type(page: Dict[str, Any]) -> str:
    return _select_name(page.get("properties", {}).get("Type"))


def _relation_contains(page: Dict[str, Any], relation_names: Iterable[str], page_id: str) -> bool:
    normalized_page_id = _normalize_id(page_id)
    properties = page.get("properties", {})
    for relation_name in relation_names:
        if normalized_page_id in _relation_ids(properties.get(relation_name)):
            return True
    return False


def _title_value(value: str) -> Dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _relation_value(page_ids: Iterable[str]) -> Dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def _date_value(value: str) -> Dict[str, Any]:
    return {"date": {"start": value}}


def _number_value(value: int | float) -> Dict[str, Any]:
    return {"number": value}


def _select_value(value: str) -> Dict[str, Any]:
    return {"select": {"name": value}}


def _rich_text_value(value: str) -> Dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value}}]}


def _supported_create_properties(rows: Iterable[Dict[str, Any]], desired: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    rows = list(rows)
    if not rows:
        return desired
    supported = set(rows[0].get("properties", {}).keys())
    return {name: value for name, value in desired.items() if name == "Name" or name in supported}


def _good_habit_context(page: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    properties = page.get("properties", {})
    base_xp = _number_from_property(_first_property(properties, _GOOD_HABIT_XP_PROPERTIES))
    if base_xp is None:
        base_xp = cfg.get("DEFAULT_HABIT_XP", config.DEFAULT_HABIT_XP)
    return {
        "id": page["id"],
        "name": _title_text(properties.get("Name")) or "Habit",
        "domain": _select_name(_first_property(properties, _DOMAIN_PROPERTIES)),
        "base_xp": int(base_xp),
    }


def _bad_habit_context(page: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    properties = page.get("properties", {})
    damage = _number_from_property(_first_property(properties, _BAD_HABIT_DAMAGE_PROPERTIES))
    if damage is None:
        damage = cfg.get("DEFAULT_BAD_HABIT_HP", config.DEFAULT_BAD_HABIT_HP)
    return {
        "id": page["id"],
        "name": _title_text(properties.get("Name")) or "Bad Habit",
        "domain": _select_name(_first_property(properties, _DOMAIN_PROPERTIES)),
        "damage": abs(int(damage)),
    }


def _habit_marker(prefix: str, habit_id: str, date_value: str) -> str:
    return f"{prefix}{_normalize_id(habit_id)}:{date_value}"


def _has_marker(page: Dict[str, Any], marker: str) -> bool:
    notes = _rich_text_text(_first_property(page.get("properties", {}), _NOTES_PROPERTIES))
    return marker in notes


def _has_good_completion(entries: Iterable[Dict[str, Any]], habit_id: str, date_value: str) -> bool:
    for entry in entries:
        if _entry_type(entry) != "GOOD":
            continue
        if _date_key(entry) != date_value:
            continue
        if _relation_contains(entry, _GOOD_HABIT_RELATION_PROPERTIES, habit_id):
            return True
    return False


def _has_xp_grant(entries: Iterable[Dict[str, Any]], habit_id: str, date_value: str) -> bool:
    marker = _habit_marker(_XP_GRANT_MARKER_PREFIX, habit_id, date_value)
    for entry in entries:
        if _entry_type(entry) != "GOOD":
            continue
        if _date_key(entry) != date_value:
            continue
        if _relation_contains(entry, _GOOD_HABIT_RELATION_PROPERTIES, habit_id) and _has_marker(entry, marker):
            return True
    return False


def _processed_bad_damage(entries: Iterable[Dict[str, Any]], raw_entry_id: str, date_value: str) -> bool:
    marker = f"{_BAD_DAMAGE_MARKER_PREFIX}{raw_entry_id}"
    for entry in entries:
        if _entry_type(entry) != "BAD":
            continue
        if _date_key(entry) != date_value:
            continue
        if _has_marker(entry, marker):
            return True
    return False


def get_active_habits(character_id: str, client=None, db_ids=None, cfg=None) -> list[Dict[str, Any]]:
    """Return active good habits for the character."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)

    rows = _query_rows(client, db_ids[_GOOD_HABIT_DB])
    habits = []
    for row in rows:
        properties = row.get("properties", {})
        if not _page_matches_character(row, character_id):
            continue
        if not _checkbox_from_property(_first_property(properties, _ACTIVE_PROPERTIES)):
            continue
        habits.append(_good_habit_context(row, cfg))
    return habits


def calculate_habit_xp(base_xp: int, multiplier: float) -> int:
    """Return floor(base_xp * multiplier) as an integer."""
    return math.floor(max(int(base_xp), 0) * max(float(multiplier), 0.0))


def process_daily_habits(
    character_id: str,
    date_value: Optional[str] = None,
    client=None,
    db_ids=None,
    cfg=None,
) -> Dict[str, Any]:
    """Process daily good habits idempotently for the target date."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    target_date = date_value or streak_engine.get_today(client=client, db_ids=db_ids, cfg=cfg)

    all_activity_rows = _query_rows(client, db_ids[_ACTIVITY_LOG_DB])
    character_entries = [row for row in all_activity_rows if _page_matches_character(row, character_id)]
    active_habits = get_active_habits(character_id, client=client, db_ids=db_ids, cfg=cfg)
    streaks = streak_engine.check_streaks(character_id, target_date, client=client, db_ids=db_ids, cfg=cfg)
    streak_by_habit = {
        _normalize_id(detail["habit_id"]): detail
        for detail in streaks.get("details", [])
    }

    processed = 0
    completed = 0
    xp_granted = 0
    for habit in active_habits:
        if not _has_good_completion(character_entries, habit["id"], target_date):
            continue
        completed += 1
        if _has_xp_grant(character_entries, habit["id"], target_date):
            continue

        streak_state = streak_by_habit.get(_normalize_id(habit["id"]), {})
        multiplier = float(streak_state.get("multiplier", 1.0))
        xp_amount = calculate_habit_xp(habit["base_xp"], multiplier)
        marker = _habit_marker(_XP_GRANT_MARKER_PREFIX, habit["id"], target_date)
        properties = {
            "Name": _title_value(f"GOOD XP: {habit['name']}"),
            "Type": _select_value("GOOD"),
            "Character": _relation_value([character_id]),
            "Occurred At": _date_value(target_date),
            "Good Habit": _relation_value([habit["id"]]),
            "Habit": _relation_value([habit["id"]]),
            "Notes": _rich_text_value(marker),
            "EXP + (Habit)": _number_value(xp_amount),
            "XP Earned": _number_value(xp_amount),
        }
        if habit["domain"]:
            properties["Domain"] = _select_value(habit["domain"])

        notion_api.create_page(
            client,
            db_ids[_ACTIVITY_LOG_DB],
            _supported_create_properties(all_activity_rows, properties),
        )
        processed += 1
        xp_granted += xp_amount

    already_processed = completed > 0 and processed == 0
    if processed > 0:
        xp_engine.update_character_stats(character_id, client=client, db_ids=db_ids, cfg=cfg)

    return {
        "processed": processed,
        "xp_granted": xp_granted,
        "streaks_updated": int(streaks.get("updated", 0)),
        "streaks_decayed": int(streaks.get("decayed", 0)),
        "already_processed": already_processed,
    }


def process_bad_habits(
    character_id: str,
    date_value: Optional[str] = None,
    client=None,
    db_ids=None,
    cfg=None,
) -> Dict[str, Any]:
    """Process today's bad habit check-ins into HP damage idempotently."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    target_date = date_value or streak_engine.get_today(client=client, db_ids=db_ids, cfg=cfg)

    entries = _activity_entries(client, db_ids, character_id)
    page_cache: Dict[str, Dict[str, Any]] = {}
    processed = 0
    total_damage = 0
    died = False

    for entry in entries:
        if _entry_type(entry) != "BAD":
            continue
        if _date_key(entry) != target_date:
            continue

        bad_habit_prop = _first_property(entry.get("properties", {}), _BAD_HABIT_RELATION_PROPERTIES)
        bad_habit_ids = _relation_ids(bad_habit_prop)
        if not bad_habit_ids:
            continue
        if _processed_bad_damage(entries, entry["id"], target_date):
            continue

        habit_id = bad_habit_ids[0]
        normalized_habit_id = _normalize_id(habit_id)
        if normalized_habit_id not in page_cache:
            page_cache[normalized_habit_id] = notion_api.get_page(client, habit_id)
        habit = _bad_habit_context(page_cache[normalized_habit_id], cfg)
        source = f"{habit['name']} [{_BAD_DAMAGE_MARKER_PREFIX}{entry['id']}]"
        result = hp_engine.apply_damage(
            character_id,
            habit["damage"],
            source,
            client=client,
            db_ids=db_ids,
            cfg=cfg,
            occurred_at=target_date,
        )
        processed += 1
        total_damage += habit["damage"]
        died = died or bool(result.get("died"))

    return {"processed": processed, "total_damage": total_damage, "died": died}


def get_trailing_adherence(
    habit_id: str,
    days: int = 30,
    *,
    date_value: Optional[str] = None,
    client=None,
    db_ids=None,
    cfg=None,
) -> float:
    """Return the percentage of days completed in the trailing window."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    window_days = max(int(days), 1)
    target_date = date.fromisoformat(date_value or streak_engine.get_today(client=client, db_ids=db_ids, cfg=cfg))
    window_start = target_date - timedelta(days=window_days - 1)

    completed_days = set()
    for entry in _query_rows(client, db_ids[_ACTIVITY_LOG_DB]):
        if _entry_type(entry) != "GOOD":
            continue
        if not _relation_contains(entry, _GOOD_HABIT_RELATION_PROPERTIES, habit_id):
            continue
        entry_date_text = _date_key(entry)
        if not entry_date_text:
            continue
        entry_date = date.fromisoformat(entry_date_text)
        if window_start <= entry_date <= target_date:
            completed_days.add(entry_date.isoformat())

    return len(completed_days) / window_days
