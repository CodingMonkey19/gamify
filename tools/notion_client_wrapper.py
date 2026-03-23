"""Notion API wrapper with throttling, retries, and lock utilities."""

import atexit
import json
import os
import sys
import time
import random
import threading
from datetime import datetime, timezone

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting — max 3 requests per second
# ---------------------------------------------------------------------------
_RATE_LIMIT = 3
_MIN_INTERVAL = 1.0 / _RATE_LIMIT
_last_call_time = 0.0
_rate_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------
_MAX_RETRIES = 3
_INITIAL_BACKOFF = 1.0
_DATA_SOURCE_ID_CACHE = {}

# ---------------------------------------------------------------------------
# Lock file
# ---------------------------------------------------------------------------
_LOCK_PATH = os.path.join(os.path.dirname(_tools_dir), ".automation.lock")
_LOCK_TIMEOUT_MINUTES = 30


def _maybe_throttle(client):
    """Skip throttling for unittest mocks; enforce it for real SDK clients."""
    if "unittest.mock" in type(client).__module__:
        return
    _throttle()


def _uses_data_sources_api(client):
    """Detect the post-2025 Notion SDK surface that split databases and data sources."""
    databases_endpoint = getattr(client, "databases", None)
    data_sources_endpoint = getattr(client, "data_sources", None)
    return (
        not hasattr(databases_endpoint, "query")
        and (hasattr(data_sources_endpoint, "query") or hasattr(data_sources_endpoint, "update"))
    )


def _extract_first_data_source_id(database_obj):
    """Return the first child data source id from a database response."""
    for source in database_obj.get("data_sources", []):
        data_source_id = source.get("id")
        if data_source_id:
            return data_source_id
    raise KeyError(f"Database '{database_obj.get('id', 'unknown')}' did not expose any child data sources")


def _resolve_data_source_id(client, db_id):
    """Resolve a database id to its primary data source id for the new API surface."""
    if not _uses_data_sources_api(client):
        return db_id
    cached = _DATA_SOURCE_ID_CACHE.get(db_id)
    if cached:
        return cached
    _maybe_throttle(client)
    database_obj = _call_with_retry(client.databases.retrieve, database_id=db_id)
    data_source_id = _extract_first_data_source_id(database_obj)
    _DATA_SOURCE_ID_CACHE[db_id] = data_source_id
    return data_source_id


def _translate_relation_properties(client, properties):
    """Swap relation targets from database ids to data source ids when required."""
    if not _uses_data_sources_api(client):
        return properties

    translated = {}
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            translated[name] = prop
            continue
        relation = prop.get("relation")
        if prop.get("type") == "relation" and isinstance(relation, dict) and relation.get("database_id"):
            translated_relation = dict(relation)
            target_db_id = translated_relation.pop("database_id")
            translated_relation["data_source_id"] = _resolve_data_source_id(client, target_db_id)
            translated[name] = dict(prop)
            translated[name]["relation"] = translated_relation
            continue
        translated[name] = prop
    return translated


def get_client():
    """Create and return a Notion API client using NOTION_API_KEY."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from notion_client import Client as NotionClient

    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        raise EnvironmentError("NOTION_API_KEY not set in environment or .env file")

    return NotionClient(auth=api_key)


def _throttle():
    """Enforce max 3 req/sec by sleeping if necessary."""
    global _last_call_time
    with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_call_time
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_call_time = now


def _call_with_retry(fn, *args, **kwargs):
    """Call fn with retry-on-transient-failure semantics."""
    from notion_client.errors import APIResponseError

    last_exc = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = fn(*args, **kwargs)
            if attempt > 0:
                logger.info(f"Notion call succeeded on attempt {attempt + 1}")
            return result
        except APIResponseError as e:
            status = getattr(e, "status", None)
            if status in (429, 500, 502, 503, 504) and attempt < _MAX_RETRIES:
                backoff = _INITIAL_BACKOFF * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(
                    f"Notion API error {status} on attempt {attempt + 1}. "
                    f"Retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
                last_exc = e
            else:
                logger.error(f"Notion API error {status}: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error calling Notion API: {e}")
            raise

    logger.error(f"Notion API call failed after {_MAX_RETRIES} retries: {last_exc}")
    raise last_exc


def create_database(client, parent, title, properties):
    """Create a Notion database."""
    db_name = title[0]["text"]["content"] if title else "unknown"
    logger.info(f"Creating database: {db_name}")
    _maybe_throttle(client)
    kwargs = {"parent": parent, "title": title}
    if _uses_data_sources_api(client):
        kwargs["initial_data_source"] = {"properties": properties}
    else:
        kwargs["properties"] = properties
    return _call_with_retry(client.databases.create, **kwargs)


def update_database(client, db_id, properties):
    """Add or update properties on an existing database."""
    logger.info(f"Updating database {db_id} with {len(properties)} properties")
    _maybe_throttle(client)
    translated_properties = _translate_relation_properties(client, properties)
    if _uses_data_sources_api(client):
        return _call_with_retry(
            client.data_sources.update,
            data_source_id=_resolve_data_source_id(client, db_id),
            properties=translated_properties,
        )
    return _call_with_retry(
        client.databases.update,
        database_id=db_id,
        properties=translated_properties,
    )


def query_database(client, db_id, filter_obj=None, sorts=None):
    """Query a database and follow pagination until exhausted."""
    results = []
    cursor = None
    page_num = 0
    uses_data_sources = _uses_data_sources_api(client)
    query_target = _resolve_data_source_id(client, db_id)
    query_method = client.data_sources.query if uses_data_sources else client.databases.query

    while True:
        page_num += 1
        kwargs = {"data_source_id": query_target} if uses_data_sources else {"database_id": query_target}
        if filter_obj:
            kwargs["filter"] = filter_obj
        if sorts:
            kwargs["sorts"] = sorts
        if cursor:
            kwargs["start_cursor"] = cursor

        _maybe_throttle(client)
        response = _call_with_retry(query_method, **kwargs)
        results.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    logger.info(f"Queried database {db_id}: {len(results)} rows across {page_num} page(s)")
    return results


def get_database(client, db_id):
    """Retrieve a database object by ID."""
    _maybe_throttle(client)
    return _call_with_retry(client.databases.retrieve, database_id=db_id)


def get_database_properties(client, db_id):
    """Retrieve properties from a database or its primary data source."""
    _maybe_throttle(client)
    db_obj = _call_with_retry(client.databases.retrieve, database_id=db_id)
    
    # If using Data Sources API, properties are on the Data Source
    if _uses_data_sources_api(client) and "data_sources" in db_obj:
        ds_id = _resolve_data_source_id(client, db_id)
        ds_obj = _call_with_retry(client.data_sources.retrieve, data_source_id=ds_id)
        return ds_obj.get("properties", {})
    
    return db_obj.get("properties", {})


# ---------------------------------------------------------------------------
# Page operations
# ---------------------------------------------------------------------------

def create_page(client, parent_db_id, properties, children=None):
    """Create a page in a Notion database."""
    if _uses_data_sources_api(client):
        parent = {
            "type": "data_source_id",
            "data_source_id": _resolve_data_source_id(client, parent_db_id),
        }
    else:
        parent = {"type": "database_id", "database_id": parent_db_id}
    kwargs = {
        "parent": parent,
        "properties": properties,
    }
    if children:
        kwargs["children"] = children
    _maybe_throttle(client)
    return _call_with_retry(client.pages.create, **kwargs)


def update_page(client, page_id, properties):
    """Update properties on an existing page."""
    _maybe_throttle(client)
    return _call_with_retry(
        client.pages.update,
        page_id=page_id,
        properties=properties,
    )


def get_page(client, page_id):
    """Retrieve a page by ID."""
    _maybe_throttle(client)
    return _call_with_retry(client.pages.retrieve, page_id=page_id)


def delete_page(client, page_id):
    """Archive (soft-delete) a page."""
    _maybe_throttle(client)
    return _call_with_retry(
        client.pages.update,
        page_id=page_id,
        archived=True,
    )


def search_pages(client, query, filter_obj=None):
    """Search for pages/databases by title."""
    kwargs = {"query": query}
    if filter_obj:
        translated_filter = dict(filter_obj)
        if (
            _uses_data_sources_api(client)
            and translated_filter.get("property") == "object"
            and translated_filter.get("value") == "database"
        ):
            translated_filter["value"] = "data_source"
        kwargs["filter"] = translated_filter
    _maybe_throttle(client)
    return _call_with_retry(client.search, **kwargs)


# ---------------------------------------------------------------------------
# Lock file utilities
# ---------------------------------------------------------------------------

def acquire_lock(module_name, lock_path=None):
    """Acquire the shared automation lock."""
    path = lock_path or _LOCK_PATH
    timeout_minutes = _LOCK_TIMEOUT_MINUTES

    if os.path.exists(path):
        try:
            with open(path) as f:
                lock_data = json.load(f)
            pid = lock_data.get("pid")
            started_at = lock_data.get("started_at", "")
            lock_module = lock_data.get("module", "unknown")

            # Check age
            if started_at:
                started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                age_minutes = (datetime.now(timezone.utc) - started_dt).total_seconds() / 60
                if age_minutes > timeout_minutes:
                    logger.warning(
                        f"Stale lock detected (age: {age_minutes:.1f}m > {timeout_minutes}m). "
                        f"Removing and proceeding."
                    )
                    os.remove(path)
                else:
                    # Check if PID is still running
                    if pid and _pid_running(pid):
                        raise RuntimeError(
                            f"Automation already running: module='{lock_module}', "
                            f"pid={pid}, started={started_at}"
                        )
                    else:
                        logger.warning(
                            f"Lock PID {pid} not running. Removing stale lock and proceeding."
                        )
                        os.remove(path)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning(f"Corrupted lock file at {path}: {exc}. Removing and proceeding.")
            os.remove(path)

    lock_data = {
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "module": module_name,
    }
    with open(path, "w") as f:
        json.dump(lock_data, f)
    logger.info(f"Lock acquired: module={module_name}, pid={os.getpid()}")
    atexit.register(release_lock, lock_path=path)
    return True


def release_lock(lock_path=None):
    """Release the automation lock file."""
    path = lock_path or _LOCK_PATH
    if os.path.exists(path):
        os.remove(path)
        logger.info("Lock released")


def check_lock(lock_path=None):
    """Returns True if a lock currently exists."""
    path = lock_path or _LOCK_PATH
    return os.path.exists(path)


def _pid_running(pid):
    """Return True if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# ---------------------------------------------------------------------------
# Helper: get page title as plain text
# ---------------------------------------------------------------------------

def get_page_title(page):
    """Extract plain text title from a Notion page or database object."""
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            return "".join(p.get("plain_text", "") for p in parts)
    title_parts = page.get("title", [])
    if title_parts:
        return "".join(part.get("plain_text", "") for part in title_parts)
    return ""
    # Databases: title array at top level
    title_array = page.get("title", [])
    if title_array:
        return "".join(p.get("plain_text", "") for p in title_array)
    return ""
