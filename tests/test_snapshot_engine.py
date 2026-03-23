"""Tests for snapshot_engine.py — daily snapshot creation, idempotency, streak counting."""
from datetime import date
from unittest.mock import patch, MagicMock, call

import pytest

from tools.snapshot_engine import take_snapshot, DAILY_SNAPSHOTS_DB_ID, STREAK_TRACKER_DB_ID


def _make_character_page(
    str_xp=200, int_xp=150, wis_xp=350, vit_xp=180, cha_xp=100,
    level=5, gold=1000, coins=500, hp=800, rank="Knight",
):
    """Build a mock Notion page response for a character."""
    return {
        "properties": {
            "STR XP": {"number": str_xp},
            "INT XP": {"number": int_xp},
            "WIS XP": {"number": wis_xp},
            "VIT XP": {"number": vit_xp},
            "CHA XP": {"number": cha_xp},
            "Level": {"number": level},
            "Gold": {"number": gold},
            "Coins": {"number": coins},
            "HP": {"number": hp},
            "Rank": {"select": {"name": rank}},
        }
    }


def _make_streak_results(count):
    """Build a mock Notion query response with `count` active streak pages."""
    return {"results": [{"id": f"streak-{i}"} for i in range(count)]}


class TestSnapshotCreation:
    """Test snapshot page creation with correct fields."""

    def test_snapshot_created_with_correct_fields(self):
        """Mock Character DB read + Notion create → verify all 14 fields."""
        mock_notion = MagicMock()
        # No existing snapshot
        mock_notion.databases.query.side_effect = [
            {"results": []},           # existing snapshot check
            _make_streak_results(3),   # active streak query
        ]
        mock_notion.pages.retrieve.return_value = _make_character_page()
        mock_notion.pages.create.return_value = {"id": "snapshot-001"}

        env = {"NOTION_TOKEN": "ntn_test_token"}
        run_date = date(2026, 3, 23)

        with patch.dict("os.environ", env, clear=True):
            with patch("tools.snapshot_engine.Client", return_value=mock_notion):
                result = take_snapshot("char-001", run_date=run_date)

        # Verify returned data
        assert result is not None
        assert result["date"] == "2026-03-23"
        assert result["character_id"] == "char-001"
        assert result["str_xp"] == 200
        assert result["int_xp"] == 150
        assert result["wis_xp"] == 350
        assert result["vit_xp"] == 180
        assert result["cha_xp"] == 100
        assert result["level"] == 5
        assert result["gold"] == 1000
        assert result["coins"] == 500
        assert result["hp"] == 800
        assert result["rank"] == "Knight"
        assert result["active_streaks"] == 3
        assert result["mood"] == "Neutral"

        # Verify Notion page was created with all 14 properties
        mock_notion.pages.create.assert_called_once()
        create_call = mock_notion.pages.create.call_args
        create_props = create_call.kwargs.get("properties", {})

        assert create_props["Date"] == {"date": {"start": "2026-03-23"}}
        assert create_props["Character"] == {"relation": [{"id": "char-001"}]}
        assert create_props["STR XP"] == {"number": 200}
        assert create_props["INT XP"] == {"number": 150}
        assert create_props["WIS XP"] == {"number": 350}
        assert create_props["VIT XP"] == {"number": 180}
        assert create_props["CHA XP"] == {"number": 100}
        assert create_props["Level"] == {"number": 5}
        assert create_props["Gold"] == {"number": 1000}
        assert create_props["Coins"] == {"number": 500}
        assert create_props["HP"] == {"number": 800}
        assert create_props["Rank"] == {"select": {"name": "Knight"}}
        assert create_props["Active Streaks"] == {"number": 3}
        assert create_props["Mood"] == {"select": {"name": "Neutral"}}


class TestIdempotency:
    """Test that existing snapshots are not duplicated."""

    def test_idempotency_existing_snapshot(self):
        """Existing snapshot for date → returns None, no create call."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {
            "results": [{"id": "existing-snapshot-001"}],
        }

        env = {"NOTION_TOKEN": "ntn_test_token"}
        run_date = date(2026, 3, 23)

        with patch.dict("os.environ", env, clear=True):
            with patch("tools.snapshot_engine.Client", return_value=mock_notion):
                result = take_snapshot("char-001", run_date=run_date)

        assert result is None
        mock_notion.pages.retrieve.assert_not_called()
        mock_notion.pages.create.assert_not_called()


class TestActiveStreakCount:
    """Test active streak counting from Streak Tracker DB."""

    def test_active_streak_count(self):
        """Mock Streak Tracker query → correct count reflected in snapshot."""
        mock_notion = MagicMock()
        mock_notion.databases.query.side_effect = [
            {"results": []},            # no existing snapshot
            _make_streak_results(7),    # 7 active streaks
        ]
        mock_notion.pages.retrieve.return_value = _make_character_page()
        mock_notion.pages.create.return_value = {"id": "snapshot-002"}

        env = {"NOTION_TOKEN": "ntn_test_token"}

        with patch.dict("os.environ", env, clear=True):
            with patch("tools.snapshot_engine.Client", return_value=mock_notion):
                result = take_snapshot("char-001", run_date=date(2026, 3, 23))

        assert result["active_streaks"] == 7

        # Verify the streak query filter
        streak_query_call = mock_notion.databases.query.call_args_list[1]
        assert streak_query_call.kwargs["database_id"] == STREAK_TRACKER_DB_ID

    def test_zero_active_streaks(self):
        """No active streaks → active_streaks = 0."""
        mock_notion = MagicMock()
        mock_notion.databases.query.side_effect = [
            {"results": []},            # no existing snapshot
            _make_streak_results(0),    # 0 active streaks
        ]
        mock_notion.pages.retrieve.return_value = _make_character_page()
        mock_notion.pages.create.return_value = {"id": "snapshot-003"}

        env = {"NOTION_TOKEN": "ntn_test_token"}

        with patch.dict("os.environ", env, clear=True):
            with patch("tools.snapshot_engine.Client", return_value=mock_notion):
                result = take_snapshot("char-001", run_date=date(2026, 3, 23))

        assert result["active_streaks"] == 0


class TestDefaultMood:
    """Test that Mood defaults to 'Neutral'."""

    def test_default_mood_is_neutral(self):
        """Verify Mood field defaults to 'Neutral' in both result and Notion properties."""
        mock_notion = MagicMock()
        mock_notion.databases.query.side_effect = [
            {"results": []},
            _make_streak_results(0),
        ]
        mock_notion.pages.retrieve.return_value = _make_character_page()
        mock_notion.pages.create.return_value = {"id": "snapshot-004"}

        env = {"NOTION_TOKEN": "ntn_test_token"}

        with patch.dict("os.environ", env, clear=True):
            with patch("tools.snapshot_engine.Client", return_value=mock_notion):
                result = take_snapshot("char-001", run_date=date(2026, 3, 23))

        # Check return value
        assert result["mood"] == "Neutral"

        # Check Notion create call
        create_props = mock_notion.pages.create.call_args.kwargs["properties"]
        assert create_props["Mood"] == {"select": {"name": "Neutral"}}
