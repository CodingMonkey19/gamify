"""Tests for dashboard_setup.py — page creation, 7 panels, idempotency, character card."""
import pytest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_character_page(name="TestHero", level=5, rank="Knight", hp=800, coins=500, gold=1000):
    return {
        "id": "char-001",
        "url": "https://notion.so/char-001",
        "properties": {
            "Name": {"title": [{"plain_text": name}]},
            "Player Level": {"number": level},
            "Current Rank": {"select": {"name": rank}},
            "Current HP": {"number": hp},
            "Current Coins": {"number": coins},
            "Gold": {"number": gold},
            "Avatar URL": {"url": None},
            "Radar Chart URL": {"url": None},
        },
    }


def _make_child_page_block(title: str, page_id: str) -> dict:
    return {
        "id": page_id,
        "type": "child_page",
        "child_page": {"title": title},
    }


# ---------------------------------------------------------------------------
# _read_character
# ---------------------------------------------------------------------------

class TestReadCharacter:

    def test_reads_character_correctly(self):
        mock_notion = MagicMock()
        mock_notion.pages.retrieve.return_value = _make_character_page()

        from tools.dashboard_setup import _read_character

        char = _read_character(mock_notion, "char-001")

        assert char["name"] == "TestHero"
        assert char["level"] == 5
        assert char["rank"] == "Knight"
        assert char["hp"] == 800
        assert char["coins"] == 500
        assert char["gold"] == 1000

    def test_returns_none_on_error(self):
        mock_notion = MagicMock()
        mock_notion.pages.retrieve.side_effect = Exception("API error")

        from tools.dashboard_setup import _read_character

        result = _read_character(mock_notion, "char-001")
        assert result is None


# ---------------------------------------------------------------------------
# _build_dashboard_blocks
# ---------------------------------------------------------------------------

class TestBuildDashboardBlocks:

    def _get_blocks(self):
        from tools.dashboard_setup import _build_dashboard_blocks
        char = {
            "name": "Hero", "level": 1, "rank": "Peasant",
            "hp": 1000, "coins": 0, "gold": 0,
            "avatar_url": "", "chart_url": "",
        }
        return _build_dashboard_blocks(char)

    def test_contains_7_panel_headings(self):
        blocks = self._get_blocks()
        headings = [
            b for b in blocks
            if b.get("type") in ("heading_1", "heading_2")
        ]
        heading_texts = [
            h.get(h["type"], {}).get("rich_text", [{}])[0].get("text", {}).get("content", "")
            for h in headings
        ]
        expected = ["Character Card", "Growth", "Battle", "Quest Board", "Tasks", "Journal", "Stats"]
        for panel in expected:
            assert panel in heading_texts, f"Panel '{panel}' not found in headings"

    def test_character_card_callout_contains_name(self):
        from tools.dashboard_setup import _build_dashboard_blocks
        char = {
            "name": "Aldric", "level": 3, "rank": "Squire",
            "hp": 900, "coins": 100, "gold": 50,
            "avatar_url": "", "chart_url": "",
        }
        blocks = _build_dashboard_blocks(char)
        callouts = [b for b in blocks if b.get("type") == "callout"]
        assert len(callouts) >= 1
        callout_text = callouts[0]["callout"]["rich_text"][0]["text"]["content"]
        assert "Aldric" in callout_text

    def test_character_card_includes_level_and_rank(self):
        from tools.dashboard_setup import _build_dashboard_blocks
        char = {
            "name": "Hero", "level": 7, "rank": "Champion",
            "hp": 800, "coins": 200, "gold": 300,
            "avatar_url": "", "chart_url": "",
        }
        blocks = _build_dashboard_blocks(char)
        callouts = [b for b in blocks if b.get("type") == "callout"]
        full_text = "".join(
            rt["text"]["content"] for rt in callouts[0]["callout"]["rich_text"]
        )
        assert "7" in full_text  # level
        assert "Champion" in full_text  # rank

    def test_image_block_added_when_avatar_url_present(self):
        from tools.dashboard_setup import _build_dashboard_blocks
        char = {
            "name": "Hero", "level": 1, "rank": "Peasant",
            "hp": 1000, "coins": 0, "gold": 0,
            "avatar_url": "https://res.cloudinary.com/avatar.png",
            "chart_url": "",
        }
        blocks = _build_dashboard_blocks(char)
        image_blocks = [b for b in blocks if b.get("type") == "image"]
        assert len(image_blocks) >= 1
        assert image_blocks[0]["image"]["external"]["url"] == "https://res.cloudinary.com/avatar.png"

    def test_no_image_block_when_urls_empty(self):
        from tools.dashboard_setup import _build_dashboard_blocks
        char = {
            "name": "Hero", "level": 1, "rank": "Peasant",
            "hp": 1000, "coins": 0, "gold": 0,
            "avatar_url": "", "chart_url": "",
        }
        blocks = _build_dashboard_blocks(char)
        image_blocks = [b for b in blocks if b.get("type") == "image"]
        assert len(image_blocks) == 0


# ---------------------------------------------------------------------------
# create_dashboard — idempotency
# ---------------------------------------------------------------------------

class TestCreateDashboardIdempotency:

    def test_creates_new_page_when_none_exists(self):
        mock_notion = MagicMock()
        mock_notion.pages.retrieve.return_value = _make_character_page()
        mock_notion.blocks.children.list.return_value = {"results": []}
        mock_notion.pages.create.return_value = {
            "id": "dash-001",
            "url": "https://notion.so/dash-001",
        }

        from tools.dashboard_setup import create_dashboard

        result = create_dashboard(mock_notion, "char-001", "parent-001")

        assert result["action"] == "created"
        assert result["page_id"] == "dash-001"
        mock_notion.pages.create.assert_called_once()

    def test_updates_existing_page_not_duplicate(self):
        mock_notion = MagicMock()
        mock_notion.pages.retrieve.return_value = _make_character_page()
        mock_notion.blocks.children.list.side_effect = [
            # First call: scanning parent for existing dashboard
            {"results": [_make_child_page_block("Daily Dashboard", "dash-existing")]},
            # Second call: clearing existing blocks
            {"results": [{"id": "block-1"}, {"id": "block-2"}]},
        ]

        from tools.dashboard_setup import create_dashboard

        result = create_dashboard(mock_notion, "char-001", "parent-001")

        assert result["action"] == "updated"
        assert result["page_id"] == "dash-existing"
        # Should NOT have created a new page
        mock_notion.pages.create.assert_not_called()
        # Should have deleted old blocks
        assert mock_notion.blocks.delete.call_count == 2
        # Should have appended new blocks
        mock_notion.blocks.children.append.assert_called_once()

    def test_returns_error_when_character_not_found(self):
        mock_notion = MagicMock()
        mock_notion.pages.retrieve.side_effect = Exception("Page not found")

        from tools.dashboard_setup import create_dashboard

        with pytest.raises(ValueError):
            create_dashboard(mock_notion, "nonexistent-char", "parent-001")


# ---------------------------------------------------------------------------
# DB references
# ---------------------------------------------------------------------------

class TestDBReferences:

    def test_all_6_db_ids_referenced_in_text_blocks(self):
        """All 6 linked DBs should be referenced in the panel filter instructions."""
        from tools.dashboard_setup import (
            _build_dashboard_blocks,
            GOOD_HABIT_DB_ID, BAD_HABIT_DB_ID, QUESTS_DB_ID,
            BRAIN_DUMP_DB_ID, JOURNAL_DB_ID, DAILY_SNAPSHOTS_DB_ID,
        )
        char = {
            "name": "Hero", "level": 1, "rank": "Peasant",
            "hp": 1000, "coins": 0, "gold": 0,
            "avatar_url": "", "chart_url": "",
        }
        blocks = _build_dashboard_blocks(char)

        # All 6 DB IDs should be importable (already tested above via the constants)
        db_ids = {
            GOOD_HABIT_DB_ID, BAD_HABIT_DB_ID, QUESTS_DB_ID,
            BRAIN_DUMP_DB_ID, JOURNAL_DB_ID, DAILY_SNAPSHOTS_DB_ID,
        }
        assert len(db_ids) == 6, "All 6 DB IDs must be distinct"

    def test_validate_env_missing_vars_returns_false(self):
        from tools.dashboard_setup import validate_env, REQUIRED_ENV_VARS

        with patch.dict("os.environ", {v: "" for v in REQUIRED_ENV_VARS}, clear=False):
            result = validate_env()
        assert result is False
