"""Coin economy, shopping, and overdraft helpers for Phase 2."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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


logger = get_logger(__name__)

_ACTIVITY_LOG_DB = "Activity Log"
_SETTINGS_DB = "Settings"
_OVERDRAFT_DB = "Overdraft Penalty"
_CHARACTER_COIN_PROPERTIES = ("Current Coins", "Coins")
_CHARACTER_GOLD_PROPERTIES = ("Gold",)
_ACTIVITY_COIN_PROPERTIES = (
    "Coins Earned",
    "Coins + Goal",
    "Coins + Tasks",
    "Coins - Market",
    "Coins - Hotel",
    "Coins - Black",
)
_MARKET_PRICE_PROPERTIES = ("Price",)
_MARKET_PURCHASED_PROPERTIES = ("Purchased",)
_MARKET_REDEMPTION_DATE_PROPERTIES = ("Redemption Date",)
_HOTEL_PRICE_PROPERTIES = ("Price",)
_HOTEL_RECOVERY_PROPERTIES = ("HP Recovery",)
_BLACK_MARKET_PRICE_PROPERTIES = ("Price",)
_OVERDRAFT_FREQUENCY_PROPERTIES = ("Frequency",)
_OVERDRAFT_PENALTY_PROPERTIES = ("HP Penalty", "HP Delta")
_OVERDRAFT_LAST_CHECK_PROPERTIES = ("Last Check",)
_OVERDRAFT_ACTIVE_PROPERTIES = ("Active",)


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
    return None


def _select_name(prop: Optional[Dict[str, Any]]) -> str:
    if not prop:
        return ""
    select = prop.get("select")
    return select.get("name", "") if isinstance(select, dict) else ""


def _checkbox_from_property(prop: Optional[Dict[str, Any]]) -> bool:
    if not prop:
        return False
    if prop.get("type") == "checkbox":
        return bool(prop.get("checkbox"))
    return False


def _date_start(prop: Optional[Dict[str, Any]]) -> str:
    if not prop or prop.get("type") != "date":
        return ""
    date_value = prop.get("date")
    if not isinstance(date_value, dict):
        return ""
    return date_value.get("start", "") or ""


def _title_text(prop: Optional[Dict[str, Any]]) -> str:
    if not prop or prop.get("type") != "title":
        return ""
    return "".join(part.get("plain_text", "") for part in prop.get("title", []))


def _find_existing_property_name(page: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
    properties = page.get("properties", {})
    for name in candidates:
        if name in properties:
            return name
    return None


def _find_existing_property_names(page: Dict[str, Any], candidates: Iterable[str]) -> list[str]:
    properties = page.get("properties", {})
    return [name for name in candidates if name in properties]


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


def _timestamp(value: Optional[str] = None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def _today_string(today: Optional[date] = None) -> str:
    return (today or datetime.now(timezone.utc).date()).isoformat()


def _activity_entries(client, db_ids, character_id: str) -> list[Dict[str, Any]]:
    return hp_engine._get_activity_entries(client, db_ids, character_id)


def _sum_coins(row: Dict[str, Any]) -> int:
    properties = row.get("properties", {})
    total = 0
    for name in _ACTIVITY_COIN_PROPERTIES:
        total += _number_from_property(properties.get(name)) or 0
    return total


def _activity_name(entry_type: str, source: str) -> str:
    suffix = source.strip() if source else entry_type
    return f"{entry_type}: {suffix}"[:200]


def _create_activity_entry(
    client,
    db_ids,
    character_id: str,
    entry_type: str,
    coin_delta: int = 0,
    notes: str = "",
    source: str = "",
    occurred_at: Optional[str] = None,
):
    properties = {
        "Name": _title_value(_activity_name(entry_type, source)),
        "Type": _select_value(entry_type),
        "Character": _relation_value([character_id]),
        "Occurred At": _date_value(_timestamp(occurred_at)),
    }
    if coin_delta:
        properties["Coins Earned"] = _number_value(coin_delta)
    if notes:
        properties["Notes"] = _rich_text_value(notes)
    return notion_api.create_page(client, db_ids[_ACTIVITY_LOG_DB], properties)


def _page_title(page: Dict[str, Any]) -> str:
    return _title_text(page.get("properties", {}).get("Name"))


def _coerce_frequency(value: str, cfg: Dict[str, Any]) -> str:
    if value:
        return value.lower()
    return str(cfg.get("OVERDRAFT_CHECK_FREQUENCY", "weekly")).lower()


def _penalty_amount(row: Dict[str, Any], cfg: Dict[str, Any]) -> int:
    properties = row.get("properties", {})
    value = _number_from_property(_first_property(properties, _OVERDRAFT_PENALTY_PROPERTIES))
    if value is not None:
        return abs(value)
    return abs(int(cfg.get("HP_OVERDRAFT_PENALTY", -100)))


def _active_penalty_row(client, db_ids, character_id: str) -> Optional[Dict[str, Any]]:
    rows = notion_api.query_database(client, db_ids[_OVERDRAFT_DB])
    matched_rows = [
        row for row in rows
        if hp_engine._page_matches_character(row, character_id)
        or not row.get("properties", {}).get("Character")
    ]
    if not matched_rows:
        return rows[0] if rows else None
    for row in matched_rows:
        active_prop = _first_property(row.get("properties", {}), _OVERDRAFT_ACTIVE_PROPERTIES)
        if active_prop is None or _checkbox_from_property(active_prop):
            return row
    return matched_rows[0]


def _is_check_due(last_check: str, frequency: str, today: date) -> bool:
    if frequency == "disabled":
        return False
    if not last_check:
        return True
    last_date = datetime.fromisoformat(last_check.replace("Z", "+00:00")).date()
    if frequency == "daily":
        interval = 1
    elif frequency == "biweekly":
        interval = 14
    else:
        interval = 7
    return today >= last_date + timedelta(days=interval)


def get_coin_balance(character_id: str, client=None, db_ids=None, cfg=None) -> int:
    """Sum all coin-related activity entries for a character."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    return sum(_sum_coins(entry) for entry in _activity_entries(client, db_ids, character_id))


def update_character_coins(character_id: str, client=None, db_ids=None, cfg=None) -> int:
    """Recalculate and write the current coin balance to the Character page."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    balance = get_coin_balance(character_id, client=client, db_ids=db_ids)
    page = notion_api.get_page(client, character_id)
    coin_property_names = _find_existing_property_names(page, _CHARACTER_COIN_PROPERTIES) or [_CHARACTER_COIN_PROPERTIES[0]]
    notion_api.update_page(
        client,
        character_id,
        {property_name: _number_value(balance) for property_name in coin_property_names},
    )
    logger.info("Updated character %s coin balance to %s", character_id, balance)
    return balance


def add_gold(character_id: str, amount: int, client=None, db_ids=None, cfg=None) -> Dict[str, Any]:
    """Add earned gold directly to the Character page."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    page = notion_api.get_page(client, character_id)
    gold_prop = _first_property(page.get("properties", {}), _CHARACTER_GOLD_PROPERTIES)
    balance_before = _number_from_property(gold_prop) or 0
    balance_after = balance_before + abs(int(amount))
    gold_property_names = _find_existing_property_names(page, _CHARACTER_GOLD_PROPERTIES) or [_CHARACTER_GOLD_PROPERTIES[0]]
    notion_api.update_page(
        client,
        character_id,
        {property_name: _number_value(balance_after) for property_name in gold_property_names},
    )
    return {"balance_before": balance_before, "balance_after": balance_after}


def spend_coins(
    character_id: str,
    amount: int,
    entry_type: str,
    source: str = "",
    client=None,
    db_ids=None,
    cfg=None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Spend coins unless the character is currently dead."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    balance_before = get_coin_balance(character_id, client=client, db_ids=db_ids)

    if hp_engine.is_dead(character_id, client=client, db_ids=db_ids):
        return {
            "blocked": True,
            "balance_before": balance_before,
            "balance_after": balance_before,
        }

    _create_activity_entry(
        client,
        db_ids,
        character_id,
        entry_type=entry_type,
        coin_delta=-abs(int(amount)),
        notes=f"Spend source: {source or entry_type}",
        source=source or entry_type,
        occurred_at=occurred_at,
    )
    balance_after = update_character_coins(character_id, client=client, db_ids=db_ids)
    return {"blocked": False, "balance_before": balance_before, "balance_after": balance_after}


def earn_coins(
    character_id: str,
    amount: int,
    entry_type: str,
    source: str = "",
    client=None,
    db_ids=None,
    cfg=None,
    occurred_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Earn coins, including while the character is dead."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    balance_before = get_coin_balance(character_id, client=client, db_ids=db_ids)
    _create_activity_entry(
        client,
        db_ids,
        character_id,
        entry_type=entry_type,
        coin_delta=abs(int(amount)),
        notes=f"Earn source: {source or entry_type}",
        source=source or entry_type,
        occurred_at=occurred_at,
    )
    balance_after = update_character_coins(character_id, client=client, db_ids=db_ids)
    return {"balance_before": balance_before, "balance_after": balance_after}


def process_market_purchase(
    character_id: str,
    market_item_id: str,
    client=None,
    db_ids=None,
    cfg=None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Spend coins on a market item and mark it purchased when supported by schema."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    market_item = notion_api.get_page(client, market_item_id)
    price = _number_from_property(_first_property(market_item.get("properties", {}), _MARKET_PRICE_PROPERTIES)) or 0
    title = _page_title(market_item) or "market purchase"
    spend_result = spend_coins(
        character_id,
        amount=price,
        entry_type="MARKET",
        source=title,
        client=client,
        db_ids=db_ids,
    )
    if spend_result["blocked"]:
        return {"success": False, "balance_after": spend_result["balance_after"], "blocked": True}

    updates = {}
    purchased_name = _find_existing_property_name(market_item, _MARKET_PURCHASED_PROPERTIES)
    redemption_name = _find_existing_property_name(market_item, _MARKET_REDEMPTION_DATE_PROPERTIES)
    if purchased_name:
        updates[purchased_name] = {"checkbox": True}
    if redemption_name:
        updates[redemption_name] = _date_value(_today_string(today))
    if updates:
        notion_api.update_page(client, market_item_id, updates)

    return {"success": True, "balance_after": spend_result["balance_after"], "blocked": False}


def process_hotel_checkin(character_id: str, hotel_id: str, client=None, db_ids=None, cfg=None) -> Dict[str, Any]:
    """Spend coins on a hotel and apply the linked HP recovery."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    hotel_page = notion_api.get_page(client, hotel_id)
    properties = hotel_page.get("properties", {})
    price = _number_from_property(_first_property(properties, _HOTEL_PRICE_PROPERTIES)) or 0
    hp_recovery = _number_from_property(_first_property(properties, _HOTEL_RECOVERY_PROPERTIES))
    if hp_recovery is None:
        tier = _select_name(properties.get("Tier"))
        hp_recovery = int(cfg.get("HOTEL_TIERS", {}).get(tier, {}).get("hp_recovery", 0))
    hotel_name = _page_title(hotel_page) or "hotel check-in"

    spend_result = spend_coins(
        character_id,
        amount=price,
        entry_type="HOTEL",
        source=hotel_name,
        client=client,
        db_ids=db_ids,
    )
    if spend_result["blocked"]:
        return {
            "success": False,
            "coins_after": spend_result["balance_after"],
            "hp_after": hp_engine.get_current_hp(character_id, client=client, db_ids=db_ids),
            "blocked": True,
        }

    recovery_result = hp_engine.apply_recovery(
        character_id,
        amount=hp_recovery,
        source=hotel_name,
        client=client,
        db_ids=db_ids,
    )
    return {
        "success": True,
        "coins_after": spend_result["balance_after"],
        "hp_after": recovery_result["hp_after"],
        "blocked": False,
    }


def process_black_market(
    character_id: str,
    black_market_item_id: str,
    missed_date: str,
    client=None,
    db_ids=None,
    cfg=None,
) -> Dict[str, Any]:
    """Spend coins on a black market recovery entry without repairing streak state."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    page = notion_api.get_page(client, black_market_item_id)
    price = _number_from_property(_first_property(page.get("properties", {}), _BLACK_MARKET_PRICE_PROPERTIES)) or 0
    title = _page_title(page) or "black market"

    spend_result = spend_coins(
        character_id,
        amount=price,
        entry_type="BLACKMARKET",
        source=title,
        client=client,
        db_ids=db_ids,
    )
    if spend_result["blocked"]:
        return {"success": False, "coins_after": spend_result["balance_after"], "blocked": True}

    _create_activity_entry(
        client,
        db_ids,
        character_id,
        entry_type="BLACKMARKET",
        coin_delta=0,
        notes=f"Recovered missed check-in for {missed_date}. Streaks remain unchanged.",
        source=title,
        occurred_at=missed_date,
    )
    return {"success": True, "coins_after": spend_result["balance_after"], "blocked": False}


def check_overdraft(character_id: str, client=None, db_ids=None, cfg=None) -> bool:
    """Return True when the current coin balance is negative."""
    del cfg  # retained for signature stability
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    return get_coin_balance(character_id, client=client, db_ids=db_ids) < 0


def apply_overdraft_penalty(
    character_id: str,
    client=None,
    db_ids=None,
    cfg=None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Apply scheduled HP damage for negative coin balance when due."""
    client = _resolve_client(client)
    db_ids = _resolve_db_ids(db_ids)
    cfg = _resolve_config(client, db_ids, cfg)
    if not check_overdraft(character_id, client=client, db_ids=db_ids):
        return {"penalized": False, "hp_damage": 0, "died": False}

    penalty_row = _active_penalty_row(client, db_ids, character_id)
    if penalty_row is None:
        return {"penalized": False, "hp_damage": 0, "died": False}

    properties = penalty_row.get("properties", {})
    frequency = _coerce_frequency(
        _select_name(_first_property(properties, _OVERDRAFT_FREQUENCY_PROPERTIES)),
        cfg,
    )
    if frequency == "disabled":
        return {"penalized": False, "hp_damage": 0, "died": False}

    today = today or datetime.now(timezone.utc).date()
    last_check = _date_start(_first_property(properties, _OVERDRAFT_LAST_CHECK_PROPERTIES))
    if not _is_check_due(last_check, frequency, today):
        return {"penalized": False, "hp_damage": 0, "died": False}

    hp_damage = _penalty_amount(penalty_row, cfg)
    damage_result = hp_engine.apply_damage(
        character_id,
        amount=hp_damage,
        source="OVERDRAFT",
        client=client,
        db_ids=db_ids,
    )

    last_check_name = _find_existing_property_name(penalty_row, _OVERDRAFT_LAST_CHECK_PROPERTIES)
    if last_check_name:
        notion_api.update_page(client, penalty_row["id"], {last_check_name: _date_value(_today_string(today))})

    return {"penalized": True, "hp_damage": -abs(hp_damage), "died": damage_result["died"]}
