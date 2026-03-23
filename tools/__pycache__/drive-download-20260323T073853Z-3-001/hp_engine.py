"""HP tracking, death detection, and respawn helpers for Phase 2."""

from __future__ import annotations

from datetime import datetime, timezone
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
_SETTINGS_DB = "Settings"
_CHARACTER_HP_PROPERTIES = ("Current HP", "HP")
_CHARACTER_DEATH_COUNT_PROPERTIES = ("Death Count",)
_CHARACTER_RESPAWN_PROPERTIES = ("Respawn",)
_CHARACTER_DEATH_PENALTY_PROPERTIES = ("Death Penalty",)
_ACTIVITY_HP_PROPERTIES = (
    "HP Delta",
    "HP + (Hotel)",
    "HP - (Bad Habit)",
    "HP - (Overdraft)",
)
_ACTIVITY_DATE_PROPERTIES = ("Occurred At", "Date")
_RELATION_PROPERTIES = ("Character",)
_DEATH_TYPES = {"DIED", "RESPAWN"}


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


def _checkbox_from_property(prop: Optional[Dict[str, Any]]) -> bool:
    if not prop:
        return False
    if prop.get("type") == "checkbox":
        return bool(prop.get("checkbox"))
    return False


def _select_name(prop: Optional[Dict[str, Any]]) -> str:
    if not prop:
        return ""
    select = prop.get("select")
    return select.get("name", "") if isinstance(select, dict) else ""


def _plain_text(prop: Optional[Dict[str, Any]]) -> str:
    if not prop:
        return ""
    prop_type = prop.get("type")
    if prop_type == "title":
        parts = prop.get("title", [])
    elif prop_type == "rich_text":
        parts = prop.get("rich_text", [])
    else:
        return ""
    return "".join(part.get("plain_text", "") for part in parts)


def _date_start(prop: Optional[Dict[str, Any]]) -> str:
    if not prop or prop.get("type") != "date":
        return ""
    date_value = prop.get("date")
    if not isinstance(date_value, dict):
        return ""
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
        relation_ids = _relation_ids(props.get(prop_name))
        if normalized_character_id in relation_ids:
            return True
    return False


def _get_activity_entries(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    activity_log_db_id = db_ids[_ACTIVITY_LOG_DB]
    rows = notion_api.query_database(client, activity_log_db_id)
    return [row for row in rows if _page_matches_character(row, character_id)]


def _sum_hp(row: Dict[str, Any]) -> int:
    properties = row.get("properties", {})
    total = 0
    for name in _ACTIVITY_HP_PROPERTIES:
        total += _number_from_property(properties.get(name)) or 0
    return total


def _entry_timestamp(value: Optional[str] = None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def _date_key(row: Dict[str, Any]) -> str:
    props = row.get("properties", {})
    for name in _ACTIVITY_DATE_PROPERTIES:
        date_value = _date_start(props.get(name))
        if date_value:
            return date_value
    return ""


def _title_value(value: str) -> Dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _select_value(value: str) -> Dict[str, Any]:
    return {"select": {"name": value}}


def _number_value(value: int) -> Dict[str, Any]:
    return {"number": value}


def _relation_value(page_ids: Iterable[str]) -> Dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def _rich_text_value(value: str) -> Dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value}}]}


def _date_value(value: str) -> Dict[str, Any]:
    return {"date": {"start": value}}


def _find_existing_property_name(page: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    properties = page.get("properties", {})
    for name in candidates:
        if name in properties:
            return name
    return None


def _find_existing_property_names(page: Dict[str, Any], candidates: Iterable[str]) -> list[str]:
    properties = page.get("properties", {})
    return [name for name in candidates if name in properties]


def _make_activity_name(entry_type: str, source: str) -> str:
    suffix = source.strip() if source else entry_type
    return f"{entry_type}: {suffix}"[:200]


def _create_activity_entry(
    client,
    db_ids,
    character_id: str,
    entry_type: str,
    hp_delta: int = 0,
    notes: str = "",
    source: str = "",
    occurred_at: Optional[str] = None,
):
    properties = {
        "Name": _title_value(_make_activity_name(entry_type, source)),
        "Type": _select_value(entry_type),
        "Character": _relation_value([character_id]),
        "Occurred At": _date_value(_entry_timestamp(occurred_at)),
    }
    if hp_delta:
        properties["HP Delta"] = _number_value(hp_delta)
    if notes:
        properties["Notes"] = _rich_text_value(notes)
    return notion_api.create_page(client, db_ids[_ACTIVITY_LOG_DB], properties)


def _character_page(client, character_id: str) -> Dict[str, Any]:
    return notion_api.get_page(client, character_id)


def get_current_hp(character_id: str, client=None, db_ids=None, cfg=None) -> int:
    """Sum all HP-related activity entries for a character."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    entries = _get_activity_entries(client, db_ids, character_id)
    return sum(_sum_hp(entry) for entry in entries)


def update_character_hp(character_id: str, client=None, db_ids=None, cfg=None) -> int:
    """Recalculate and write the current HP back to the Character page."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    current_hp = get_current_hp(character_id, client=client, db_ids=db_ids)
    page = _character_page(client, character_id)
    hp_property_names = _find_existing_property_names(page, _CHARACTER_HP_PROPERTIES) or [_CHARACTER_HP_PROPERTIES[0]]
    notion_api.update_page(
        client,
        character_id,
        {property_name: _number_value(current_hp) for property_name in hp_property_names},
    )
    logger.info("Updated character %s HP to %s", character_id, current_hp)
    return current_hp


def is_dead(character_id: str, client=None, db_ids=None, cfg=None) -> bool:
    """Return True when the latest death-related event is DIED."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    entries = _get_activity_entries(client, db_ids, character_id)
    death_entries = [
        entry
        for entry in entries
        if _select_name(entry.get("properties", {}).get("Type")) in _DEATH_TYPES
    ]
    if not death_entries:
        return False
    death_entries.sort(key=_date_key, reverse=True)
    latest_type = _select_name(death_entries[0].get("properties", {}).get("Type"))
    return latest_type == "DIED"


def check_death(character_id: str, client=None, db_ids=None, cfg=None) -> bool:
    """Return True when HP is at or below the threshold and the character is not already dead."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    threshold = int(cfg.get("HP_DEATH_THRESHOLD", 0))
    current_hp = get_current_hp(character_id, client=client, db_ids=db_ids)
    return current_hp <= threshold and not is_dead(character_id, client=client, db_ids=db_ids)


def trigger_death(character_id: str, client=None, db_ids=None, cfg=None, occurred_at: Optional[str] = None) -> Dict[str, Any]:
    """Create a DIED marker entry and increment the death counter when needed."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    if not check_death(character_id, client=client, db_ids=db_ids, cfg=cfg):
        page = _character_page(client, character_id)
        death_count = _number_from_property(
            _first_property(page.get("properties", {}), _CHARACTER_DEATH_COUNT_PROPERTIES)
        ) or 0
        death_penalty_text = _plain_text(
            _first_property(page.get("properties", {}), _CHARACTER_DEATH_PENALTY_PROPERTIES)
        )
        return {"death_count": death_count, "death_penalty_text": death_penalty_text}

    page = _character_page(client, character_id)
    properties = page.get("properties", {})
    death_count_name = _find_existing_property_name(page, _CHARACTER_DEATH_COUNT_PROPERTIES)
    current_death_count = _number_from_property(_first_property(properties, _CHARACTER_DEATH_COUNT_PROPERTIES)) or 0
    death_penalty_text = _plain_text(_first_property(properties, _CHARACTER_DEATH_PENALTY_PROPERTIES))

    _create_activity_entry(
        client,
        db_ids,
        character_id,
        entry_type="DIED",
        hp_delta=0,
        notes=death_penalty_text or "Character died.",
        source="death",
        occurred_at=occurred_at,
    )

    updates = {}
    if death_count_name:
        updates[death_count_name] = _number_value(current_death_count + 1)
    if updates:
        notion_api.update_page(client, character_id, updates)

    logger.info("Triggered death for character %s", character_id)
    return {"death_count": current_death_count + 1, "death_penalty_text": death_penalty_text}


def apply_damage(
    character_id: str,
    amount: int,
    source: str,
    client=None,
    db_ids=None,
    cfg=None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Create HP damage in the Activity Log and trigger death if needed."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    hp_before = get_current_hp(character_id, client=client, db_ids=db_ids)
    hp_delta = -abs(int(amount))
    entry_type = "PENALTY" if source.strip().upper() in {"OVERDRAFT", "PENALTY"} else "BAD"

    _create_activity_entry(
        client,
        db_ids,
        character_id,
        entry_type=entry_type,
        hp_delta=hp_delta,
        notes=f"Damage source: {source}",
        source=source,
        occurred_at=occurred_at,
    )

    died = False
    if check_death(character_id, client=client, db_ids=db_ids, cfg=cfg):
        trigger_death(character_id, client=client, db_ids=db_ids, cfg=cfg, occurred_at=occurred_at)
        died = True

    hp_after = update_character_hp(character_id, client=client, db_ids=db_ids)
    return {"hp_before": hp_before, "hp_after": hp_after, "died": died}


def apply_recovery(
    character_id: str,
    amount: int,
    source: str,
    client=None,
    db_ids=None,
    cfg=None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Create HP recovery in the Activity Log and refresh the Character page."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    hp_before = get_current_hp(character_id, client=client, db_ids=db_ids)
    hp_delta = abs(int(amount))

    _create_activity_entry(
        client,
        db_ids,
        character_id,
        entry_type="HOTEL",
        hp_delta=hp_delta,
        notes=f"Recovery source: {source}",
        source=source,
        occurred_at=occurred_at,
    )

    hp_after = update_character_hp(character_id, client=client, db_ids=db_ids)
    return {"hp_before": hp_before, "hp_after": hp_after}


def respawn(character_id: str, client=None, db_ids=None, cfg=None, occurred_at: Optional[str] = None) -> Dict[str, Any]:
    """Respawn a dead character back to the configured starting HP."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    page = _character_page(client, character_id)
    respawn_property_name = _find_existing_property_name(page, _CHARACTER_RESPAWN_PROPERTIES)

    updates = {}
    if respawn_property_name:
        updates[respawn_property_name] = {"checkbox": False}

    if not is_dead(character_id, client=client, db_ids=db_ids):
        if updates:
            notion_api.update_page(client, character_id, updates)
        logger.info("Respawn ignored for alive character %s", character_id)
        return {
            "respawned": False,
            "new_hp": get_current_hp(character_id, client=client, db_ids=db_ids),
        }

    respawn_date = _entry_timestamp(occurred_at).split("T", 1)[0]
    existing_entries = _get_activity_entries(client, db_ids, character_id)
    for entry in existing_entries:
        properties = entry.get("properties", {})
        if _select_name(properties.get("Type")) != "RESPAWN":
            continue
        if _date_key(entry).split("T", 1)[0] == respawn_date:
            if updates:
                notion_api.update_page(client, character_id, updates)
            logger.info("Skipping duplicate respawn for character %s on %s", character_id, respawn_date)
            return {"respawned": False, "new_hp": get_current_hp(character_id, client=client, db_ids=db_ids)}

    _create_activity_entry(
        client,
        db_ids,
        character_id,
        entry_type="RESPAWN",
        hp_delta=int(cfg.get("STARTING_HP", 1000)),
        notes="Respawned",
        source="respawn",
        occurred_at=occurred_at,
    )
    if updates:
        notion_api.update_page(client, character_id, updates)
    new_hp = update_character_hp(character_id, client=client, db_ids=db_ids)
    logger.info("Respawned character %s to HP %s", character_id, new_hp)
    return {"respawned": True, "new_hp": new_hp}
