"""Tests for onboarding.py — character creation, habits, vision board, partial recovery."""
import pytest
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(page_id: str = "char-001") -> dict:
    return {"id": page_id, "url": f"https://notion.so/{page_id}"}


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

class TestInputHelpers:

    def test_prompt_required_returns_on_first_valid_input(self):
        from tools.onboarding import prompt_required
        with patch("builtins.input", return_value="Hero"):
            assert prompt_required("Name: ") == "Hero"

    def test_prompt_required_loops_on_empty(self):
        from tools.onboarding import prompt_required
        with patch("builtins.input", side_effect=["", "  ", "Hero"]):
            result = prompt_required("Name: ")
        assert result == "Hero"

    def test_prompt_choice_valid_selection(self):
        from tools.onboarding import prompt_choice
        with patch("builtins.input", return_value="2"):
            result = prompt_choice("Pick class:", ["Warrior", "Mage", "Rogue"])
        assert result == "Mage"

    def test_prompt_choice_invalid_then_valid(self):
        from tools.onboarding import prompt_choice
        with patch("builtins.input", side_effect=["0", "6", "abc", "1"]):
            result = prompt_choice("Pick:", ["Warrior", "Mage"])
        assert result == "Warrior"

    def test_prompt_multiline_returns_lines(self):
        from tools.onboarding import prompt_multiline
        with patch("builtins.input", side_effect=["line1", "line2", ""]):
            result = prompt_multiline("Enter items:")
        assert result == ["line1", "line2"]

    def test_prompt_multiline_empty_returns_empty_list(self):
        from tools.onboarding import prompt_multiline
        with patch("builtins.input", return_value=""):
            result = prompt_multiline("Enter items:")
        assert result == []


# ---------------------------------------------------------------------------
# setup_character
# ---------------------------------------------------------------------------

class TestSetupCharacter:

    def test_creates_character_with_starting_values(self):
        """Character row created with Level 1, HP 1000, Peasant rank, all XPs 0."""
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = _make_page("char-001")

        from tools.onboarding import setup_character

        char_id = setup_character(
            mock_notion, "parent-001", "Hero", "Warrior",
            "Become the best version of myself", "No gaming for a week"
        )

        assert char_id == "char-001"
        mock_notion.pages.create.assert_called_once()
        call_kwargs = mock_notion.pages.create.call_args.kwargs
        props = call_kwargs["properties"]

        assert props["Player Level"]["number"] == 1
        assert props["Current HP"]["number"] == 1000
        assert props["Current Rank"]["select"]["name"] == "Peasant"
        assert props["Current Coins"]["number"] == 0
        assert props["Gold"]["number"] == 0
        assert props["STR XP"]["number"] == 0
        assert props["INT XP"]["number"] == 0
        assert props["WIS XP"]["number"] == 0
        assert props["VIT XP"]["number"] == 0
        assert props["CHA XP"]["number"] == 0

    def test_character_name_and_class_stored(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = _make_page("char-002")

        from tools.onboarding import setup_character

        setup_character(mock_notion, "parent-001", "Aria", "Mage", "Master magic", "No TV")

        props = mock_notion.pages.create.call_args.kwargs["properties"]
        assert props["Name"]["title"][0]["text"]["content"] == "Aria"
        assert props["Class"]["select"]["name"] == "Mage"


# ---------------------------------------------------------------------------
# setup_default_habits
# ---------------------------------------------------------------------------

class TestSetupDefaultHabits:

    def test_creates_exactly_5_good_and_3_bad_habits(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "habit-x"}

        from tools.onboarding import setup_default_habits

        result = setup_default_habits(mock_notion, "char-001")

        assert result["good"] == 5
        assert result["bad"] == 3
        assert mock_notion.pages.create.call_count == 8

    def test_good_habits_have_stat_field(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "h"}

        from tools.onboarding import setup_default_habits, GOOD_HABIT_DB_ID

        setup_default_habits(mock_notion, "char-001")

        # All good habit calls should target GOOD_HABIT_DB_ID
        good_calls = [
            c for c in mock_notion.pages.create.call_args_list
            if c.kwargs["parent"]["database_id"] == GOOD_HABIT_DB_ID
        ]
        assert len(good_calls) == 5
        for c in good_calls:
            props = c.kwargs["properties"]
            assert "Stat" in props
            assert "XP Reward" in props

    def test_bad_habits_have_hp_penalty_field(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "h"}

        from tools.onboarding import setup_default_habits, BAD_HABIT_DB_ID

        setup_default_habits(mock_notion, "char-001")

        bad_calls = [
            c for c in mock_notion.pages.create.call_args_list
            if c.kwargs["parent"]["database_id"] == BAD_HABIT_DB_ID
        ]
        assert len(bad_calls) == 3
        for c in bad_calls:
            props = c.kwargs["properties"]
            assert "HP Penalty" in props


# ---------------------------------------------------------------------------
# setup_vision_board
# ---------------------------------------------------------------------------

class TestSetupVisionBoard:

    def test_creates_8_categories(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "vb"}

        from tools.onboarding import setup_vision_board

        count = setup_vision_board(mock_notion, "char-001")

        assert count == 8
        assert mock_notion.pages.create.call_count == 8

    def test_all_categories_present(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "vb"}

        from tools.onboarding import setup_vision_board
        from tools.config import VISION_BOARD_CATEGORIES

        setup_vision_board(mock_notion, "char-001")

        created_names = [
            c.kwargs["properties"]["Category"]["select"]["name"]
            for c in mock_notion.pages.create.call_args_list
        ]
        for cat in VISION_BOARD_CATEGORIES:
            assert cat in created_names


# ---------------------------------------------------------------------------
# setup_identity_rows
# ---------------------------------------------------------------------------

class TestSetupIdentityRows:

    def test_creates_correct_count(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "id-x"}

        from tools.onboarding import setup_identity_rows

        count = setup_identity_rows(
            mock_notion, "char-001",
            strengths=["Disciplined", "Creative"],
            weaknesses=["Procrastination"],
            objectives=["Lose weight", "Save money"],
        )

        # 2 strengths + 1 weakness + 2 objectives = 5
        assert count == 5
        assert mock_notion.pages.create.call_count == 5

    def test_types_are_set_correctly(self):
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "id-x"}

        from tools.onboarding import setup_identity_rows

        setup_identity_rows(
            mock_notion, "char-001",
            strengths=["Focused"],
            weaknesses=["Lazy"],
            objectives=[],
        )

        type_values = [
            c.kwargs["properties"]["Type"]["select"]["name"]
            for c in mock_notion.pages.create.call_args_list
        ]
        assert "Strength" in type_values
        assert "Weakness" in type_values


# ---------------------------------------------------------------------------
# Partial recovery (duplicate detection)
# ---------------------------------------------------------------------------

class TestPartialRecovery:

    def test_existing_character_detected(self):
        """_check_existing_character returns ID when character found."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {
            "results": [{"id": "char-existing"}]
        }

        from tools.onboarding import _check_existing_character

        result = _check_existing_character(mock_notion, "parent-001")
        assert result == "char-existing"

    def test_no_existing_character_returns_none(self):
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": []}

        from tools.onboarding import _check_existing_character

        result = _check_existing_character(mock_notion, "parent-001")
        assert result is None


# ---------------------------------------------------------------------------
# validate_env
# ---------------------------------------------------------------------------

class TestValidateEnv:

    def test_missing_vars_returns_false(self):
        from tools.onboarding import validate_env, REQUIRED_ENV_VARS
        import os

        with patch.dict("os.environ", {v: "" for v in REQUIRED_ENV_VARS}, clear=False):
            result = validate_env()
        assert result is False

    def test_all_vars_present_returns_true(self):
        from tools.onboarding import validate_env, REQUIRED_ENV_VARS

        env = {v: "test_value" for v in REQUIRED_ENV_VARS}
        with patch.dict("os.environ", env, clear=False):
            result = validate_env()
        assert result is True
