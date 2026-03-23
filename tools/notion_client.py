"""Expose the real Notion SDK while also re-exporting local wrapper helpers.

Works both as a standalone module (tools/ on sys.path) and as a package member
(imported as tools.notion_client). The shim temporarily adjusts sys.path and
sys.modules to load the *real* notion_client SDK, then re-registers itself.
"""

import importlib
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_THIS_MODULE = sys.modules[__name__]


def _load_sdk():
    """Import the real notion_client SDK, bypassing this local shim."""
    _SDK_NAME = "notion_client"
    original_sys_path = list(sys.path)
    # Temporarily remove any cached local notion_client entries
    saved_modules = {}
    for key in list(sys.modules):
        if key == _SDK_NAME or key.startswith(_SDK_NAME + "."):
            saved_modules[key] = sys.modules.pop(key)
    try:
        # Remove tools/ from path so importlib finds the real SDK
        sys.path = [p for p in sys.path if os.path.abspath(p) != _TOOLS_DIR]
        sdk = importlib.import_module(_SDK_NAME)
        errors_module = importlib.import_module(f"{_SDK_NAME}.errors")
        return sdk, errors_module
    finally:
        sys.path = original_sys_path
        sys.modules[__name__] = _THIS_MODULE


_sdk, errors = _load_sdk()
__path__ = list(getattr(_sdk, "__path__", []))
sys.modules["notion_client.errors"] = errors

Client = _sdk.Client
APIResponseError = errors.APIResponseError

# Import wrapper helpers — try absolute (standalone) then relative (package)
try:
    from notion_client_wrapper import (
        acquire_lock, check_lock, create_database, create_page, delete_page,
        get_client, get_database, get_page, get_page_title, query_database,
        release_lock, search_pages, update_database, update_page,
    )
except ImportError:
    from .notion_client_wrapper import (
        acquire_lock, check_lock, create_database, create_page, delete_page,
        get_client, get_database, get_page, get_page_title, query_database,
        release_lock, search_pages, update_database, update_page,
    )


# ---------------------------------------------------------------------------
# Convenience helpers used by Phase 5-7 engines
# ---------------------------------------------------------------------------

def get_notion_client():
    """Return an authenticated Notion client.

    Tries NOTION_TOKEN first (Phase 5-7 / GitHub Actions),
    then falls back to NOTION_API_KEY (Phase 1-4 wrapper).
    """
    token = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")
    if not token:
        raise EnvironmentError("Neither NOTION_TOKEN nor NOTION_API_KEY set")
    return Client(auth=token)


def _extract_property(prop):
    """Extract a plain Python value from a Notion property object."""
    if prop is None:
        return None
    ptype = prop.get("type")
    if ptype == "number":
        return prop.get("number")
    if ptype == "select":
        sel = prop.get("select")
        return sel.get("name") if sel else None
    if ptype == "url":
        return prop.get("url")
    if ptype == "title":
        parts = prop.get("title", [])
        return parts[0].get("plain_text", "") if parts else ""
    if ptype == "rich_text":
        parts = prop.get("rich_text", [])
        return parts[0].get("plain_text", "") if parts else ""
    if ptype == "checkbox":
        return prop.get("checkbox", False)
    if ptype == "relation":
        return [r["id"] for r in prop.get("relation", [])]
    if ptype == "date":
        d = prop.get("date")
        return d.get("start") if d else None
    return None


def get_character(client, character_id):
    """Read a Character DB page and return a flat dict of property values."""
    page = get_page(client, character_id)
    props = page.get("properties", {})
    result = {"id": page["id"]}
    for name, prop in props.items():
        result[name] = _extract_property(prop)
    return result


def update_character(client, character_id, properties):
    """Update a Character DB page with the given Notion API property format."""
    return update_page(client, character_id, properties)


__all__ = [
    "APIResponseError",
    "Client",
    "acquire_lock",
    "check_lock",
    "create_database",
    "create_page",
    "delete_page",
    "errors",
    "get_character",
    "get_client",
    "get_database",
    "get_notion_client",
    "get_page",
    "get_page_title",
    "query_database",
    "release_lock",
    "search_pages",
    "update_character",
    "update_database",
    "update_page",
]
