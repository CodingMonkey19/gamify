"""Workout processing for Phase 4 domain modules."""

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

import config
from create_databases import load_db_ids
from logger import get_logger
import notion_client_wrapper as notion_api
import xp_engine


logger = get_logger(__name__)

_ACTIVITY_LOG_DB = "Activity Log"
_CHARACTER_DB = "Character"
_EXERCISE_DB = "Exercise Dictionary"
_SET_LOG_DB = "Set Log"
_SETTINGS_DB = "Settings"
_WORKOUT_DB = "Workout Sessions"

_RELATION_PROPERTIES = ("Character",)
_TITLE_PROPERTIES = ("Name", "Exercise Name", "Session Name")
_NOTES_PROPERTIES = ("Notes",)
_DATE_PROPERTIES = ("Session Date", "Workout Date", "Date", "Occurred At")
_SESSION_RELATION_PROPERTIES = ("Session", "Workout Session")
_EXERCISE_RELATION_PROPERTIES = ("Exercise",)
_WEIGHT_PROPERTIES = ("Weight",)
_REPS_PROPERTIES = ("Reps",)
_RPE_PROPERTIES = ("RPE",)
_ONE_RM_PROPERTIES = ("Estimated 1RM",)
_DELTA_PROPERTIES = ("Progressive Delta",)
_SET_XP_PROPERTIES = ("Session XP",)
_EXERCISE_MODIFIER_PROPERTIES = ("Base XP Modifier",)

_ACTIVITY_TYPE = "WORKOUT"
_ACTIVITY_DOMAIN = "STR"
_MARKER_PREFIX = "fitness_engine:session:"


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
    direct_match = _direct_character_match(page, character_id)
    return True if direct_match is None else direct_match


def _direct_character_match(page: Dict[str, Any], character_id: str) -> Optional[bool]:
    normalized_character_id = _normalize_id(character_id)
    properties = page.get("properties", {})
    matched_any = False
    for property_name in _RELATION_PROPERTIES:
        relation_ids = _relation_ids(properties.get(property_name))
        if relation_ids:
            matched_any = True
            if normalized_character_id in relation_ids:
                return True
    return None if not matched_any else False


def _page_date(page: Dict[str, Any], names: Iterable[str] = _DATE_PROPERTIES) -> str:
    properties = page.get("properties", {})
    for property_name in names:
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


def _filter_supported_page_updates(page: Dict[str, Any], desired: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    properties = page.get("properties", {})
    return {name: value for name, value in desired.items() if name in properties}


def _session_page(client, session_id: str, cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    normalized = _normalize_id(session_id)
    if normalized not in cache:
        cache[normalized] = notion_api.get_page(client, session_id)
    return cache[normalized]


def _exercise_page(client, exercise_id: str, cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    normalized = _normalize_id(exercise_id)
    if normalized not in cache:
        cache[normalized] = notion_api.get_page(client, exercise_id)
    return cache[normalized]


def _set_session_ids(page: Dict[str, Any]) -> list[str]:
    return _relation_ids(_first_property(page.get("properties", {}), _SESSION_RELATION_PROPERTIES))


def _set_exercise_ids(page: Dict[str, Any]) -> list[str]:
    return _relation_ids(_first_property(page.get("properties", {}), _EXERCISE_RELATION_PROPERTIES))


def _set_matches_character(page: Dict[str, Any], character_id: str, client, session_cache: Dict[str, Dict[str, Any]]) -> bool:
    direct_match = _direct_character_match(page, character_id)
    if direct_match is not None:
        return direct_match

    session_ids = _set_session_ids(page)
    if not session_ids:
        return False
    for session_id in session_ids:
        if _page_matches_character(_session_page(client, session_id, session_cache), character_id):
            return True
    return False


def _set_session_date(page: Dict[str, Any], client, session_cache: Dict[str, Dict[str, Any]]) -> str:
    value = _page_date(page)
    if value:
        return value
    for session_id in _set_session_ids(page):
        value = _page_date(_session_page(client, session_id, session_cache))
        if value:
            return value
    return ""


def _activity_entries(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    rows = notion_api.query_database(client, db_ids[_ACTIVITY_LOG_DB])
    return [row for row in rows if _page_matches_character(row, character_id)]


def _session_sets(client, db_ids, session_id: str) -> list[Dict[str, Any]]:
    normalized_session_id = _normalize_id(session_id)
    rows = notion_api.query_database(client, db_ids[_SET_LOG_DB])
    return [
        row
        for row in rows
        if normalized_session_id in _set_session_ids(row)
    ]


def _activity_marker(session_id: str, session_date: str) -> str:
    return f"{_MARKER_PREFIX}{_normalize_id(session_id)}:{session_date}"


def _existing_marker(entries: Iterable[Dict[str, Any]], marker: str) -> bool:
    return any(marker in _page_notes(entry) for entry in entries)


def _exercise_modifier(
    set_page: Dict[str, Any],
    client,
    exercise_cache: Dict[str, Dict[str, Any]],
) -> tuple[str, float]:
    exercise_ids = _set_exercise_ids(set_page)
    if not exercise_ids:
        return "", 1.0

    exercise_page = _exercise_page(client, exercise_ids[0], exercise_cache)
    modifier = _number_from_property(_first_property(exercise_page.get("properties", {}), _EXERCISE_MODIFIER_PROPERTIES))
    return exercise_ids[0], float(modifier if modifier is not None else 1.0)


def calculate_1rm(weight: float, reps: float) -> int:
    """Estimate 1RM via the Epley formula."""
    if float(weight) <= 0 or float(reps) <= 0:
        return 0
    return math.floor(float(weight) * (1 + (float(reps) / 30.0)))


def calculate_volume(weight: float, reps: float) -> int:
    """Calculate total lifted volume for a set."""
    if float(weight) <= 0 or float(reps) <= 0:
        return 0
    return int(float(weight) * float(reps))


def calculate_set_xp(volume: float, exercise_modifier: float, rpe: float = 7, *, cfg=None) -> int:
    """Convert set volume into XP, optionally weighting by RPE."""
    if float(volume) <= 0:
        return 0
    cfg = cfg or config.get_config()
    base_xp = math.floor(float(volume) * float(exercise_modifier) / 1000.0)
    if base_xp <= 0:
        return 0
    if cfg.get("RPE_XP_WEIGHT", config.RPE_XP_WEIGHT):
        return max(0, math.floor(base_xp * (float(rpe) / 10.0)))
    return base_xp


def get_best_1rm(
    character_id: str,
    exercise_id: str,
    window_days: Optional[int] = None,
    client=None,
    db_ids=None,
    cfg=None,
    *,
    as_of: Optional[str | date | datetime] = None,
    exclude_set_id: Optional[str] = None,
) -> int:
    """Return the best 1RM for the exercise within the overload window."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    target_day = _parse_day(as_of)
    window = int(window_days or cfg.get("OVERLOAD_WINDOW_DAYS", config.OVERLOAD_WINDOW_DAYS))
    normalized_exercise_id = _normalize_id(exercise_id)
    normalized_exclude_set_id = _normalize_id(exclude_set_id)

    session_cache: Dict[str, Dict[str, Any]] = {}
    best_1rm = 0
    for row in notion_api.query_database(client, db_ids[_SET_LOG_DB]):
        if normalized_exclude_set_id and _normalize_id(row.get("id")) == normalized_exclude_set_id:
            continue
        if not _set_matches_character(row, character_id, client, session_cache):
            continue
        if normalized_exercise_id not in _set_exercise_ids(row):
            continue
        session_date = _set_session_date(row, client, session_cache)
        if not session_date:
            continue
        day = _parse_day(session_date)
        delta_days = (target_day - day).days
        if delta_days < 0 or delta_days > window:
            continue
        properties = row.get("properties", {})
        current_1rm = _number_from_property(_first_property(properties, _ONE_RM_PROPERTIES))
        if current_1rm is None:
            current_1rm = calculate_1rm(
                _number_from_property(_first_property(properties, _WEIGHT_PROPERTIES)) or 0,
                _number_from_property(_first_property(properties, _REPS_PROPERTIES)) or 0,
            )
        best_1rm = max(best_1rm, int(current_1rm))
    return best_1rm


def calculate_progressive_delta(current_1rm: int, best_1rm: int) -> Dict[str, Any]:
    """Return whether the current set beats the prior best and by how much."""
    current_1rm = max(int(current_1rm), 0)
    best_1rm = max(int(best_1rm), 0)
    if current_1rm <= 0 or best_1rm <= 0:
        return {"overload": False, "absolute": 0, "percentage": 0.0}
    absolute = current_1rm - best_1rm
    overload = absolute > 0
    percentage = (absolute / best_1rm * 100.0) if overload else 0.0
    return {"overload": overload, "absolute": max(absolute, 0), "percentage": percentage}


def process_set(
    character_id: str,
    set_data: Dict[str, Any],
    client=None,
    db_ids=None,
    cfg=None,
    *,
    session_date: Optional[str | date | datetime] = None,
) -> Dict[str, Any]:
    """Process a single set and return derived metrics."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)

    if "properties" in set_data:
        properties = set_data.get("properties", {})
        set_id = set_data.get("id")
        weight = _number_from_property(_first_property(properties, _WEIGHT_PROPERTIES)) or 0
        reps = _number_from_property(_first_property(properties, _REPS_PROPERTIES)) or 0
        rpe = _number_from_property(_first_property(properties, _RPE_PROPERTIES))
        exercise_id, exercise_modifier = _exercise_modifier(set_data, client, {})
    else:
        properties = {}
        set_id = set_data.get("id")
        weight = set_data.get("weight", 0)
        reps = set_data.get("reps", 0)
        rpe = set_data.get("rpe")
        exercise_id = set_data.get("exercise_id", "")
        exercise_modifier = float(set_data.get("exercise_modifier", 1.0))

    if float(weight) <= 0 or float(reps) <= 0:
        return {
            "valid": False,
            "1rm": 0,
            "volume": 0,
            "xp": 0,
            "delta": {"overload": False, "absolute": 0, "percentage": 0.0},
        }

    rpe_value = float(rpe if rpe is not None else 7)
    one_rm = calculate_1rm(weight, reps)
    volume = calculate_volume(weight, reps)
    xp = calculate_set_xp(volume, exercise_modifier, rpe=rpe_value, cfg=cfg)
    best_1rm = get_best_1rm(
        character_id,
        exercise_id,
        client=client,
        db_ids=db_ids,
        cfg=cfg,
        as_of=session_date,
        exclude_set_id=set_id,
    ) if exercise_id else 0
    delta = calculate_progressive_delta(one_rm, best_1rm)

    return {
        "valid": True,
        "1rm": one_rm,
        "volume": volume,
        "xp": xp,
        "delta": delta,
        "exercise_id": exercise_id,
        "best_1rm": best_1rm,
        "rpe": rpe_value,
        "properties": properties,
    }


def process_workout_session(character_id: str, session_id: str, client=None, db_ids=None, cfg=None) -> Optional[Dict[str, Any]]:
    """Process all sets for a workout session and emit one activity entry."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    session_page = notion_api.get_page(client, session_id)
    if not _page_matches_character(session_page, character_id):
        return None

    session_date = _page_date(session_page)
    if not session_date:
        return None
    session_day = _parse_day(session_date).isoformat()
    marker = _activity_marker(session_id, session_day)
    if _existing_marker(_activity_entries(client, db_ids, character_id), marker):
        logger.info("Workout session %s already processed", session_id)
        return None

    total_xp = 0
    valid_sets = 0
    for set_row in _session_sets(client, db_ids, session_id):
        result = process_set(
            character_id,
            set_row,
            client=client,
            db_ids=db_ids,
            cfg=cfg,
            session_date=session_day,
        )
        if not result["valid"]:
            continue
        valid_sets += 1
        total_xp += result["xp"]
        set_updates = _filter_supported_page_updates(
            set_row,
            {
                "Progressive Delta": _number_value(result["delta"]["absolute"]),
                "Session XP": _number_value(result["xp"]),
            },
        )
        if set_updates:
            notion_api.update_page(client, set_row["id"], set_updates)

    if valid_sets == 0 or total_xp <= 0:
        return {
            "session_id": session_id,
            "session_date": session_day,
            "valid_sets": valid_sets,
            "total_xp": total_xp,
            "created_activity": False,
        }

    activity_title_name = _title_property_name(client, db_ids[_ACTIVITY_LOG_DB], ("Activity", "Name"))
    activity_type = _choose_select_option(client, db_ids[_ACTIVITY_LOG_DB], "Type", _ACTIVITY_TYPE, "GOOD")
    activity_domain = _choose_select_option(client, db_ids[_ACTIVITY_LOG_DB], "Domain", _ACTIVITY_DOMAIN)
    activity_desired = {
        activity_title_name: _title_value(_page_title(session_page) or f"Workout {session_day}"),
        "Character": _relation_value([character_id]),
        "Occurred At": _date_value(session_day),
        "EXP + (Workout)": _number_value(total_xp),
        "XP Earned": _number_value(total_xp),
        "Notes": _rich_text_value(f"{marker} valid_sets={valid_sets}"),
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
    return {
        "session_id": session_id,
        "session_date": session_day,
        "valid_sets": valid_sets,
        "total_xp": total_xp,
        "created_activity": True,
    }


def process_daily_workouts(
    character_id: str,
    workout_date: str | date | datetime,
    client=None,
    db_ids=None,
    cfg=None,
) -> list[Dict[str, Any]]:
    """Process every workout session for the requested day."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    target_day = _parse_day(workout_date).isoformat()

    results = []
    for session_page in notion_api.query_database(client, db_ids[_WORKOUT_DB]):
        if not _page_matches_character(session_page, character_id):
            continue
        session_date = _page_date(session_page)
        if not session_date:
            continue
        if _parse_day(session_date).isoformat() != target_day:
            continue
        result = process_workout_session(
            character_id,
            session_page["id"],
            client=client,
            db_ids=db_ids,
            cfg=cfg,
        )
        if result is not None:
            results.append(result)
    return results


def _parse_args(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--date", required=True)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    result = process_daily_workouts(args.character_id, args.date)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
