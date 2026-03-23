"""Tests for quest_generator.py — quest validation, AI generation, budget enforcement."""
import pytest
from unittest.mock import patch, MagicMock

from tools.config import QUEST_DIFFICULTY_REWARDS


# ---------------------------------------------------------------------------
# validate_quest — PURE FUNCTION tests (no mocks needed)
# ---------------------------------------------------------------------------

class TestValidateQuest:
    """Test quest validation logic with various inputs."""

    def _call(self, quest_data, weakest_stat="CHA"):
        """Helper: import and call validate_quest."""
        from tools.quest_generator import validate_quest
        return validate_quest(quest_data, weakest_stat)

    def test_valid_data_returns_validated_dict(self):
        """Complete valid quest data should return a validated dict."""
        quest = {
            "title": "The Iron Trial",
            "narrative": "Complete 50 push-ups before noon.",
            "domain": "STR",
            "difficulty": "Medium",
        }
        result = self._call(quest)
        assert result is not None
        assert result["title"] == "The Iron Trial"
        assert result["narrative"] == "Complete 50 push-ups before noon."
        assert result["domain"] == "STR"
        assert result["difficulty"] == "Medium"

    def test_invalid_domain_defaults_to_weakest_stat(self):
        """Invalid domain should default to weakest_stat."""
        quest = {
            "title": "Mystery Quest",
            "narrative": "Do something mysterious.",
            "domain": "MAGIC",
            "difficulty": "Easy",
        }
        result = self._call(quest, weakest_stat="WIS")
        assert result is not None
        assert result["domain"] == "WIS"

    def test_empty_domain_defaults_to_weakest_stat(self):
        """Empty string domain should default to weakest_stat."""
        quest = {
            "title": "Empty Domain Quest",
            "narrative": "A quest without direction.",
            "domain": "",
            "difficulty": "Hard",
        }
        result = self._call(quest, weakest_stat="INT")
        assert result is not None
        assert result["domain"] == "INT"

    def test_invalid_difficulty_defaults_to_medium(self):
        """Invalid difficulty should default to 'Medium'."""
        quest = {
            "title": "Impossible Quest",
            "narrative": "This difficulty is wrong.",
            "domain": "STR",
            "difficulty": "Legendary",
        }
        result = self._call(quest)
        assert result is not None
        assert result["difficulty"] == "Medium"

    def test_empty_difficulty_defaults_to_medium(self):
        """Empty string difficulty should default to 'Medium'."""
        quest = {
            "title": "No Difficulty Quest",
            "narrative": "How hard is this?",
            "domain": "VIT",
            "difficulty": "",
        }
        result = self._call(quest)
        assert result is not None
        assert result["difficulty"] == "Medium"

    def test_missing_title_returns_none(self):
        """Quest with no title key should return None."""
        quest = {
            "narrative": "A nameless quest.",
            "domain": "STR",
            "difficulty": "Easy",
        }
        result = self._call(quest)
        assert result is None

    def test_empty_title_returns_none(self):
        """Quest with empty string title should return None."""
        quest = {
            "title": "",
            "narrative": "A nameless quest.",
            "domain": "STR",
            "difficulty": "Easy",
        }
        result = self._call(quest)
        assert result is None

    def test_whitespace_title_returns_none(self):
        """Quest with whitespace-only title should return None."""
        quest = {
            "title": "   ",
            "narrative": "A quest with spaces only.",
            "domain": "INT",
            "difficulty": "Medium",
        }
        result = self._call(quest)
        assert result is None

    def test_missing_narrative_returns_none(self):
        """Quest with no narrative key should return None."""
        quest = {
            "title": "Narrationless",
            "domain": "WIS",
            "difficulty": "Hard",
        }
        result = self._call(quest)
        assert result is None

    def test_empty_narrative_returns_none(self):
        """Quest with empty string narrative should return None."""
        quest = {
            "title": "No Story",
            "narrative": "",
            "domain": "CHA",
            "difficulty": "Epic",
        }
        result = self._call(quest)
        assert result is None

    def test_whitespace_narrative_returns_none(self):
        """Quest with whitespace-only narrative should return None."""
        quest = {
            "title": "Blank Story",
            "narrative": "   ",
            "domain": "VIT",
            "difficulty": "Easy",
        }
        result = self._call(quest)
        assert result is None

    def test_title_and_narrative_are_stripped(self):
        """Leading/trailing whitespace should be stripped from title and narrative."""
        quest = {
            "title": "  Trimmed Title  ",
            "narrative": "  Trimmed narrative.  ",
            "domain": "STR",
            "difficulty": "Easy",
        }
        result = self._call(quest)
        assert result is not None
        assert result["title"] == "Trimmed Title"
        assert result["narrative"] == "Trimmed narrative."

    def test_all_valid_domains_accepted(self):
        """Each valid domain should pass validation unchanged."""
        for domain in ["STR", "INT", "WIS", "VIT", "CHA"]:
            quest = {
                "title": f"Test {domain}",
                "narrative": f"Testing {domain} domain.",
                "domain": domain,
                "difficulty": "Easy",
            }
            result = self._call(quest)
            assert result is not None
            assert result["domain"] == domain

    def test_all_valid_difficulties_accepted(self):
        """Each valid difficulty should pass validation unchanged."""
        for difficulty in ["Easy", "Medium", "Hard", "Epic"]:
            quest = {
                "title": f"Test {difficulty}",
                "narrative": f"Testing {difficulty} difficulty.",
                "domain": "STR",
                "difficulty": difficulty,
            }
            result = self._call(quest)
            assert result is not None
            assert result["difficulty"] == difficulty


# ---------------------------------------------------------------------------
# QUEST_DIFFICULTY_REWARDS — config lookup
# ---------------------------------------------------------------------------

class TestQuestDifficultyRewards:
    """Verify QUEST_DIFFICULTY_REWARDS produces correct XP/Gold for each tier."""

    def test_easy_rewards(self):
        assert QUEST_DIFFICULTY_REWARDS["Easy"]["xp"] == 25
        assert QUEST_DIFFICULTY_REWARDS["Easy"]["gold"] == 5

    def test_medium_rewards(self):
        assert QUEST_DIFFICULTY_REWARDS["Medium"]["xp"] == 50
        assert QUEST_DIFFICULTY_REWARDS["Medium"]["gold"] == 10

    def test_hard_rewards(self):
        assert QUEST_DIFFICULTY_REWARDS["Hard"]["xp"] == 100
        assert QUEST_DIFFICULTY_REWARDS["Hard"]["gold"] == 25

    def test_epic_rewards(self):
        assert QUEST_DIFFICULTY_REWARDS["Epic"]["xp"] == 200
        assert QUEST_DIFFICULTY_REWARDS["Epic"]["gold"] == 50

    def test_all_difficulties_present(self):
        """All four difficulties should be defined."""
        assert set(QUEST_DIFFICULTY_REWARDS.keys()) == {"Easy", "Medium", "Hard", "Epic"}


# ---------------------------------------------------------------------------
# generate_quests — budget enforcement
# ---------------------------------------------------------------------------

class TestGenerateQuestsBudget:
    """Test that generate_quests respects the AI cost budget."""

    def test_returns_none_when_budget_exceeded(self):
        """generate_quests should return None when check_budget returns False."""
        from tools.quest_generator import generate_quests

        with patch("tools.ai_cost_tracker.check_budget", return_value=False):
            result = generate_quests("test-char-id")

        assert result is None

    def test_budget_check_called_before_api(self):
        """Budget check should be the first gate — no OpenAI call if rejected."""
        from tools.quest_generator import generate_quests

        with patch("tools.ai_cost_tracker.check_budget", return_value=False) as mock_budget:
            result = generate_quests("test-char-id")

        assert result is None
        mock_budget.assert_called_once()


# ---------------------------------------------------------------------------
# generate_quests — API error handling
# ---------------------------------------------------------------------------

class TestGenerateQuestsApiError:
    """Test graceful degradation when OpenAI API fails."""

    def _mock_context(self):
        """Return a minimal context dict for mocking build_generation_context."""
        return {
            "player_stats": {"STR": 200, "INT": 150, "WIS": 350, "VIT": 180, "CHA": 100},
            "stat_levels": {"STR": 2, "INT": 1, "WIS": 3, "VIT": 1, "CHA": 1},
            "weakest_stat": "CHA",
            "active_streaks": [],
            "recent_quests_completed": 0,
            "total_quests_available": 0,
            "player_rank": "Knight",
            "player_level": 5,
        }

    def test_api_exception_returns_none(self):
        """OpenAI raising an exception should return None gracefully."""
        from tools.quest_generator import generate_quests

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.side_effect = Exception("API timeout")

        with patch("tools.ai_cost_tracker.check_budget", return_value=True), \
             patch("tools.quest_generator.build_generation_context", return_value=self._mock_context()), \
             patch("tools.quest_generator.OpenAI", return_value=mock_openai_client):
            result = generate_quests("test-char-id")

        assert result is None

    def test_malformed_json_response_returns_none(self):
        """If AI returns non-JSON content, generate_quests should return None."""
        from tools.quest_generator import generate_quests

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 200

        mock_message = MagicMock()
        mock_message.content = "This is not valid JSON at all"

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.return_value = mock_response

        with patch("tools.ai_cost_tracker.check_budget", return_value=True), \
             patch("tools.ai_cost_tracker.record_spend", return_value=0.001), \
             patch("tools.quest_generator.build_generation_context", return_value=self._mock_context()), \
             patch("tools.quest_generator.OpenAI", return_value=mock_openai_client):
            result = generate_quests("test-char-id")

        assert result is None


# ---------------------------------------------------------------------------
# generate_quests — successful generation end-to-end
# ---------------------------------------------------------------------------

class TestGenerateQuestsSuccess:
    """Test the full happy-path flow with all external deps mocked."""

    def _mock_context(self):
        return {
            "player_stats": {"STR": 200, "INT": 150, "WIS": 350, "VIT": 180, "CHA": 100},
            "stat_levels": {"STR": 2, "INT": 1, "WIS": 3, "VIT": 1, "CHA": 1},
            "weakest_stat": "CHA",
            "active_streaks": [],
            "recent_quests_completed": 0,
            "total_quests_available": 0,
            "player_rank": "Knight",
            "player_level": 5,
        }

    def _mock_openai_response(self, quests_json):
        import json as _json
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 200
        mock_message = MagicMock()
        mock_message.content = _json.dumps(quests_json)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]
        return mock_response

    def test_creates_quests_in_notion(self):
        """Successful AI response should create quest rows and return summary."""
        from tools.quest_generator import generate_quests

        ai_json = {"quests": [
            {"title": "The Mage's Trial", "narrative": "Study a new topic.", "domain": "INT", "difficulty": "Medium"},
            {"title": "Social Expedition", "narrative": "Reach out to a friend.", "domain": "CHA", "difficulty": "Easy"},
            {"title": "Iron Will Challenge", "narrative": "Extra workout.", "domain": "STR", "difficulty": "Hard"},
        ]}

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.return_value = self._mock_openai_response(ai_json)

        mock_notion = MagicMock()
        mock_notion.pages.create.side_effect = [{"id": "q-aaa"}, {"id": "q-bbb"}, {"id": "q-ccc"}]

        with patch("tools.ai_cost_tracker.check_budget", return_value=True), \
             patch("tools.ai_cost_tracker.record_spend", return_value=0.000135), \
             patch("tools.quest_generator.build_generation_context", return_value=self._mock_context()), \
             patch("tools.quest_generator.OpenAI", return_value=mock_openai_client), \
             patch("tools.quest_generator.get_notion_client", return_value=mock_notion):
            result = generate_quests("test-char-id")

        assert result is not None
        assert result["quests_created"] == 3
        assert result["quests_rejected"] == 0
        assert result["cost"] == 0.000135
        assert mock_notion.pages.create.call_count == 3

    def test_partial_validation_failure(self):
        """If 1 of 3 quests fails validation, only 2 should be created."""
        from tools.quest_generator import generate_quests

        ai_json = {"quests": [
            {"title": "Valid Quest", "narrative": "A real quest.", "domain": "STR", "difficulty": "Easy"},
            {"title": "", "narrative": "Missing title.", "domain": "INT", "difficulty": "Medium"},
            {"title": "Another Valid", "narrative": "Another real quest.", "domain": "CHA", "difficulty": "Hard"},
        ]}

        mock_openai_client = MagicMock()
        mock_openai_client.chat.completions.create.return_value = self._mock_openai_response(ai_json)

        mock_notion = MagicMock()
        mock_notion.pages.create.side_effect = [{"id": "q-111"}, {"id": "q-222"}]

        with patch("tools.ai_cost_tracker.check_budget", return_value=True), \
             patch("tools.ai_cost_tracker.record_spend", return_value=0.000135), \
             patch("tools.quest_generator.build_generation_context", return_value=self._mock_context()), \
             patch("tools.quest_generator.OpenAI", return_value=mock_openai_client), \
             patch("tools.quest_generator.get_notion_client", return_value=mock_notion):
            result = generate_quests("test-char-id")

        assert result is not None
        assert result["quests_created"] == 2
        assert result["quests_rejected"] == 1
        assert len(result["quest_ids"]) == 2
