"""Expose the real Notion SDK while also re-exporting local wrapper helpers.

The test suite prepends `tools/` to `sys.path`, so a local `notion_client.py`
would normally shadow the third-party `notion_client` package. This shim
temporarily removes itself from the import path, loads the real SDK, then
re-registers itself and forwards the SDK types plus the local helper surface.
"""

import importlib
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_THIS_MODULE = sys.modules[__name__]


def _load_sdk():
    original_sys_path = list(sys.path)
    try:
        sys.path = [path for path in sys.path if os.path.abspath(path) != _TOOLS_DIR]
        sys.modules.pop(__name__, None)
        sdk = importlib.import_module(__name__)
        errors_module = importlib.import_module(f"{__name__}.errors")
        return sdk, errors_module
    finally:
        sys.path = original_sys_path
        sys.modules[__name__] = _THIS_MODULE


_sdk, errors = _load_sdk()
__path__ = list(getattr(_sdk, "__path__", []))
sys.modules["notion_client.errors"] = errors

Client = _sdk.Client
APIResponseError = errors.APIResponseError

from notion_client_wrapper import (  # noqa: E402
    acquire_lock,
    check_lock,
    create_database,
    create_page,
    delete_page,
    get_client,
    get_database,
    get_page,
    get_page_title,
    query_database,
    release_lock,
    search_pages,
    update_database,
    update_page,
)

__all__ = [
    "APIResponseError",
    "Client",
    "acquire_lock",
    "check_lock",
    "create_database",
    "create_page",
    "delete_page",
    "errors",
    "get_client",
    "get_database",
    "get_page",
    "get_page_title",
    "query_database",
    "release_lock",
    "search_pages",
    "update_database",
    "update_page",
]
