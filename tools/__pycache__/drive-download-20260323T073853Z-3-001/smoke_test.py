"""Standalone readiness checks for the Phase 1 workspace."""

import json
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from logger import get_logger
import notion_client_wrapper as notion_api
from create_databases import DATABASE_SCHEMAS, load_db_ids


logger = get_logger(__name__)


def _check(name, ok, message):
    return {"name": name, "status": "pass" if ok else "fail", "message": message}


def _load_env():
    """Load .env when python-dotenv is available so CLI runs see local config."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        return


def run_checks(client=None, db_ids=None, db_ids_path=None):
    """Run environment, connectivity, and database readiness checks."""
    _load_env()
    checks = []
    notion_api_key = os.getenv("NOTION_API_KEY")
    parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    checks.append(_check("NOTION_API_KEY", bool(notion_api_key), "Configured" if notion_api_key else "Missing NOTION_API_KEY"))
    checks.append(
        _check(
            "NOTION_PARENT_PAGE_ID",
            bool(parent_page_id),
            "Configured" if parent_page_id else "Missing NOTION_PARENT_PAGE_ID",
        )
    )
    checks.append(_check("OPENAI_API_KEY", bool(openai_api_key), "Configured" if openai_api_key else "Missing OPENAI_API_KEY"))

    if client is None and notion_api_key:
        try:
            client = notion_api.get_client()
        except Exception as exc:
            checks.append(_check("notion_client", False, f"Unable to create Notion client: {exc}"))
            client = None

    if client is not None:
        try:
            client.users.me()
            checks.append(_check("notion_connectivity", True, "Connected to Notion"))
        except Exception as exc:
            checks.append(_check("notion_connectivity", False, f"Notion connectivity failed: {exc}"))

        if parent_page_id:
            try:
                notion_api.get_page(client, parent_page_id)
                checks.append(_check("parent_page_access", True, "Parent page is accessible"))
            except Exception as exc:
                checks.append(_check("parent_page_access", False, f"Parent page is not accessible: {exc}"))
    else:
        checks.append(_check("notion_connectivity", False, "Notion client unavailable"))
        if parent_page_id:
            checks.append(_check("parent_page_access", False, "Skipped because Notion client is unavailable"))

    if db_ids is None:
        db_ids = load_db_ids(db_ids_path)

    expected_databases = list(DATABASE_SCHEMAS.keys())
    database_names = sorted(set(expected_databases) | set(db_ids.keys()))
    if not db_ids:
        checks.append(_check("db_ids.json", False, "No database mapping found"))

    for database_name in database_names:
        database_id = db_ids.get(database_name)
        if not database_id:
            checks.append(_check(f"db_{database_name}", False, f"Missing database id for {database_name}"))
            continue
        if client is None:
            checks.append(_check(f"db_{database_name}", False, "Skipped because Notion client is unavailable"))
            continue
        try:
            notion_api.get_database(client, database_id)
            checks.append(_check(f"db_{database_name}", True, f"{database_name} is accessible"))
        except Exception as exc:
            checks.append(_check(f"db_{database_name}", False, f"{database_name} is missing or inaccessible: {exc}"))

    settings_id = db_ids.get("Settings")
    if settings_id and client is not None:
        try:
            notion_api.query_database(client, settings_id)
            checks.append(_check("settings_db_readable", True, "Settings database is readable"))
        except Exception as exc:
            checks.append(_check("settings_db_readable", False, f"Settings database is not readable: {exc}"))
    else:
        checks.append(_check("settings_db_readable", False, "Settings database mapping missing"))

    status = "pass" if all(check["status"] == "pass" for check in checks) else "fail"
    return {"status": status, "checks": checks}


def main():
    result = run_checks()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
