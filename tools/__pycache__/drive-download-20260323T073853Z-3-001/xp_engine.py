"""XP aggregation, leveling, and rank helpers for Phase 3."""

from __future__ import annotations

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


logger = get_logger(__name__)

_ACTIVITY_LOG_DB = "Activity Log"
_CHARACTER_DB = "Character"
_SETTINGS_DB = "Settings"
_GOOD_HABIT_DB = "Good Habit"
_GOAL_DB = "Goal"
_BRAIN_DUMP_DB = "Brain Dump"

_XP_ENTRY_TYPES = {"GOOD", "GOAL", "TASKS", "FINANCIAL", "WORKOUT", "NUTRITION"}
_RELATION_PROPERTIES = ("Character",)
_DOMAIN_PROPERTIES = ("Domain", "Stat", "Primary Stat")
_GOOD_HABIT_RELATION_PROPERTIES = ("Good Habit",)
_GOAL_RELATION_PROPERTIES = ("Goal",)
_TASK_RELATION_PROPERTIES = ("Brain Dump",)
_RELATED_SKILLS_PROPERTIES = ("Related Skills",)
_CHARACTER_CLASS_PROPERTIES = ("Class",)
_CHARACTER_PLAYER_LEVEL_PROPERTIES = ("Player Level", "Level")
_CHARACTER_TOTAL_XP_PROPERTIES = ("Total XP",)
_CHARACTER_RANK_PROPERTIES = ("Current Rank", "Rank")
_ACTIVITY_DATE_PROPERTIES = ("Occurred At", "Date")
_XP_PROPERTY_BY_TYPE = {
    "GOOD": ("EXP + (Habit)", "XP Earned"),
    "GOAL": ("EXP + (Goal)", "XP Earned"),
    "TASKS": ("EXP + (Tasks)", "XP Earned"),
    "FINANCIAL": ("EXP + (Financial)", "XP Earned"),
    "WORKOUT": ("EXP + (Workout)", "XP Earned"),
    "NUTRITION": ("EXP + (Nutrition)", "XP Earned"),
}


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


def _number_from_property(prop: Optional[Dict[str, Any]]) -> Optional[int]:
    if not prop:
        return None
    if prop.get("type") == "number":
        value = prop.get("number")
        if value is not None:
            return int(value)
    if prop.get("type") == "formula":
        formula = prop.get("formula", {})
        if formula.get("type") == "number" and formula.get("number") is not None:
            return int(formula["number"])
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


def _date_start(prop: Optional[Dict[str, Any]]) -> str:
    if not prop or prop.get("type") != "date":
        return ""
    date_value = prop.get("date") or {}
    return date_value.get("start", "") or ""


def _relation_ids(prop: Optional[Dict[str, Any]]) -> list[str]:
    if not prop or prop.get("type") != "relation":
        return []
    relation = prop.get("relation", [])
    return [_normalize_id(item.get("id")) for item in relation if item.get("id")]


def _page_matches_character(page: Dict[str, Any], character_id: str) -> bool:
    props = page.get("properties", {})
    normalized_character_id = _normalize_id(character_id)
    for prop_name in _RELATION_PROPERTIES:
        if normalized_character_id in _relation_ids(props.get(prop_name)):
            return True
    return False


def _activity_entries(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    rows = notion_api.query_database(client, db_ids[_ACTIVITY_LOG_DB])
    return [row for row in rows if _page_matches_character(row, character_id)]


def _page_cache_get(cache: Dict[str, Dict[str, Any]], page_id: str, client) -> Dict[str, Any]:
    normalized_id = _normalize_id(page_id)
    if normalized_id not in cache:
        cache[normalized_id] = notion_api.get_page(client, page_id)
    return cache[normalized_id]


def _coerce_threshold_mapping(mapping: Dict[Any, Any]) -> list[tuple[int, Any]]:
    return sorted(((int(key), value) for key, value in mapping.items()), key=lambda item: item[0])


def _map_domain_to_stats(value: str, cfg: Dict[str, Any]) -> list[str]:
    if not value:
        return []
    if value in cfg.get("STATS", config.STATS):
        return [value]

    normalized = value.strip().lower()
    stats = []
    for stat, domains in cfg.get("STAT_DOMAIN_MAP", config.STAT_DOMAIN_MAP).items():
        normalized_domains = {str(item).strip().lower() for item in domains}
        if normalized in normalized_domains:
            stats.append(stat)
    return stats


def _entry_type(entry: Dict[str, Any]) -> str:
    return _select_name(entry.get("properties", {}).get("Type"))


def _entry_xp(entry: Dict[str, Any]) -> int:
    props = entry.get("properties", {})
    entry_type = _entry_type(entry)
    candidates = _XP_PROPERTY_BY_TYPE.get(entry_type, ("XP Earned",))
    for name in candidates:
        value = _number_from_property(props.get(name))
        if value is not None:
            return value
    return 0


def _related_stats_from_page(
    page: Dict[str, Any],
    client,
    cfg: Dict[str, Any],
    page_cache: Dict[str, Dict[str, Any]],
) -> list[str]:
    props = page.get("properties", {})
    related_skills = _relation_ids(_first_property(props, _RELATED_SKILLS_PROPERTIES))
    if related_skills:
        stats = []
        for skill_id in related_skills:
            skill_page = _page_cache_get(page_cache, skill_id, client)
            stat_name = _select_name(_first_property(skill_page.get("properties", {}), _DOMAIN_PROPERTIES))
            for mapped in _map_domain_to_stats(stat_name, cfg):
                if mapped not in stats:
                    stats.append(mapped)
        if stats:
            return stats

    domain_name = _select_name(_first_property(props, _DOMAIN_PROPERTIES))
    return _map_domain_to_stats(domain_name, cfg)


def _entry_stats(
    entry: Dict[str, Any],
    client,
    db_ids,
    cfg: Dict[str, Any],
    page_cache: Dict[str, Dict[str, Any]],
) -> list[str]:
    props = entry.get("properties", {})
    entry_type = _entry_type(entry)

    if entry_type == "GOOD":
        good_habit_ids = _relation_ids(_first_property(props, _GOOD_HABIT_RELATION_PROPERTIES))
        if good_habit_ids:
            habit_page = _page_cache_get(page_cache, good_habit_ids[0], client)
            domain_name = _select_name(_first_property(habit_page.get("properties", {}), _DOMAIN_PROPERTIES))
            stats = _map_domain_to_stats(domain_name, cfg)
            if stats:
                return stats

    if entry_type == "GOAL":
        goal_ids = _relation_ids(_first_property(props, _GOAL_RELATION_PROPERTIES))
        if goal_ids:
            goal_page = _page_cache_get(page_cache, goal_ids[0], client)
            stats = _related_stats_from_page(goal_page, client, cfg, page_cache)
            if stats:
                return stats

    if entry_type == "TASKS":
        task_ids = _relation_ids(_first_property(props, _TASK_RELATION_PROPERTIES))
        if task_ids:
            task_page = _page_cache_get(page_cache, task_ids[0], client)
            stats = _related_stats_from_page(task_page, client, cfg, page_cache)
            if stats:
                return stats

    domain_name = _select_name(_first_property(props, _DOMAIN_PROPERTIES))
    return _map_domain_to_stats(domain_name, cfg)


def _number_value(value: int) -> Dict[str, Any]:
    return {"number": value}


def _select_value(value: str) -> Dict[str, Any]:
    return {"select": {"name": value}}


def xp_for_level(level: int, cfg=None) -> int:
    """XP required from level n-1 to level n."""
    if level <= 0:
        return 0
    cfg = cfg or config.get_config()
    base = float(cfg.get("LEVEL_BASE_XP", config.LEVEL_BASE_XP))
    exponent = float(cfg.get("LEVEL_EXPONENT", config.LEVEL_EXPONENT))
    linear = float(cfg.get("LEVEL_LINEAR_MOD", config.LEVEL_LINEAR_MOD))
    return math.floor(base * (level ** exponent) + linear * level)


def cumulative_xp_for_level(level: int, cfg=None) -> int:
    """Total cumulative XP required through the specified level."""
    if level <= 0:
        return 0
    return sum(xp_for_level(index, cfg=cfg) for index in range(1, level + 1))


def level_from_xp(total_xp: int, cfg=None) -> int:
    """Return the character level for the given total XP."""
    total_xp = max(int(total_xp), 0)
    cfg = cfg or config.get_config()
    level = 1
    while total_xp > cumulative_xp_for_level(level, cfg=cfg):
        level += 1
    return level


def progress_to_next_level(total_xp: int, cfg=None) -> float:
    """Return progress toward the next level as a 0.0-1.0 float."""
    total_xp = max(int(total_xp), 0)
    cfg = cfg or config.get_config()
    current_level = level_from_xp(total_xp, cfg=cfg)
    exact_boundary = cumulative_xp_for_level(current_level, cfg=cfg)
    if total_xp == exact_boundary:
        return 0.0

    previous_threshold = cumulative_xp_for_level(current_level - 1, cfg=cfg)
    next_threshold = cumulative_xp_for_level(current_level, cfg=cfg)
    span = max(next_threshold - previous_threshold, 1)
    return max(0.0, min(1.0, (total_xp - previous_threshold) / span))


def aggregate_stat_xp(character_id: str, stat: str, client=None, db_ids=None, cfg=None) -> int:
    """Sum all XP entries mapped to the requested stat before class bonuses."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    stat = stat.upper()
    entries = _activity_entries(client, db_ids, character_id)
    page_cache: Dict[str, Dict[str, Any]] = {}

    total = 0
    for entry in entries:
        entry_type = _entry_type(entry)
        if entry_type not in _XP_ENTRY_TYPES:
            continue

        xp_value = _entry_xp(entry)
        if xp_value <= 0:
            continue

        stats = _entry_stats(entry, client, db_ids, cfg, page_cache)
        if not stats:
            logger.warning("Skipping XP entry %s because no stat mapping was found.", entry.get("id"))
            continue

        unique_stats = list(dict.fromkeys(stats))
        if stat not in unique_stats:
            continue
        if len(unique_stats) == 1:
            total += xp_value
        else:
            total += xp_value // len(unique_stats)

    return total


def apply_class_bonus(
    base_xp: int,
    stat: str,
    character_class: Optional[str] = None,
    *,
    character_id: Optional[str] = None,
    client=None,
    db_ids=None,
    cfg=None,
) -> int:
    """Apply the +10% class bonus when the stat matches the character class."""
    client = _resolve_client(client) if client is not None or character_id else client
    db_ids = _resolve_db_ids(db_ids) if db_ids is not None or character_id else db_ids
    cfg = _resolve_config(client, db_ids, cfg) if (client is not None and db_ids is not None) else (cfg or config.get_config())

    if character_class is None and character_id and client is not None:
        page = notion_api.get_page(client, character_id)
        character_class = _select_name(_first_property(page.get("properties", {}), _CHARACTER_CLASS_PROPERTIES))

    if not character_class:
        return int(base_xp)

    target_stat = cfg.get("CLASS_BONUSES", config.CLASS_BONUSES).get(character_class)
    if target_stat == stat.upper():
        return math.floor(int(base_xp) * 1.1)
    return int(base_xp)


def _character_page(client, character_id: str) -> Dict[str, Any]:
    return notion_api.get_page(client, character_id)


def _rank_for_total_xp(total_xp: int, cfg: Dict[str, Any]) -> str:
    rank = ""
    for threshold, name in _coerce_threshold_mapping(cfg.get("RANK_THRESHOLDS", config.RANK_THRESHOLDS)):
        if total_xp >= threshold:
            rank = str(name)
    return rank or "Peasant"


def update_character_stats(character_id: str, client=None, db_ids=None, cfg=None) -> Dict[str, Any]:
    """Recalculate stat XP, levels, player level, total XP, and rank."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    page = _character_page(client, character_id)
    character_class = _select_name(_first_property(page.get("properties", {}), _CHARACTER_CLASS_PROPERTIES))

    stats_payload = {}
    updates: Dict[str, Dict[str, Any]] = {}
    stat_order = cfg.get("STATS", config.STATS)

    for stat in stat_order:
        raw_xp = aggregate_stat_xp(character_id, stat, client=client, db_ids=db_ids, cfg=cfg)
        final_xp = apply_class_bonus(raw_xp, stat, character_class, cfg=cfg)
        level = level_from_xp(final_xp, cfg=cfg)
        stats_payload[stat] = {"xp": final_xp, "level": level}

        if stat + " XP" in page.get("properties", {}):
            updates[f"{stat} XP"] = _number_value(final_xp)
        if f"{stat} Level" in page.get("properties", {}):
            updates[f"{stat} Level"] = _number_value(level)

    levels = [payload["level"] for payload in stats_payload.values()]
    player_level = sum(levels) // max(len(levels), 1)
    total_xp = sum(payload["xp"] for payload in stats_payload.values())
    rank = _rank_for_total_xp(total_xp, cfg)

    for property_name in _find_existing_property_names(page, _CHARACTER_PLAYER_LEVEL_PROPERTIES):
        updates[property_name] = _number_value(player_level)
    for property_name in _find_existing_property_names(page, _CHARACTER_TOTAL_XP_PROPERTIES):
        updates[property_name] = _number_value(total_xp)
    for property_name in _find_existing_property_names(page, _CHARACTER_RANK_PROPERTIES):
        updates[property_name] = _select_value(rank)

    if updates:
        notion_api.update_page(client, character_id, updates)

    return {
        "stats": stats_payload,
        "player_level": player_level,
        "total_xp": total_xp,
        "rank": rank,
    }


def generate_progress_bar(current: int, target: int, segments: int = 10) -> str:
    """Render a simple text progress bar for XP display."""
    current = max(int(current), 0)
    target = max(int(target), 1)
    segments = max(int(segments), 1)
    filled = min(segments, math.floor(current / target * segments))
    return f"{'◾' * filled}{'◽' * (segments - filled)} {current}/{target}"
