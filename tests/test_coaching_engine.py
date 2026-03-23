"""Tests for coaching_engine.py — persona rotation, briefing generation, budget enforcement."""
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock


# ---------------------------------------------------------------------------
# PERSONAS and ROTATION_ORDER — structural assertions
# ---------------------------------------------------------------------------

class TestPersonasStructure:
    """Validate the PERSONAS dict and ROTATION_ORDER list."""

    def test_personas_has_three_entries(self):
        """PERSONAS dict should have exactly 3 personas."""
        from tools.coaching_engine import PERSONAS
        assert len(PERSONAS) == 3

    def test_personas_keys_match_rotation_order(self):
        """Every key in ROTATION_ORDER should exist in PERSONAS."""
        from tools.coaching_engine import PERSONAS, ROTATION_ORDER
        for key in ROTATION_ORDER:
            assert key in PERSONAS, f"'{key}' in ROTATION_ORDER but missing from PERSONAS"

    def test_rotation_order_has_three_items(self):
        """ROTATION_ORDER should have exactly 3 items."""
        from tools.coaching_engine import ROTATION_ORDER
        assert len(ROTATION_ORDER) == 3

    def test_each_persona_has_name_and_system_prompt(self):
        """Each persona entry must have 'name' and 'system_prompt' keys."""
        from tools.coaching_engine import PERSONAS
        for key, persona in PERSONAS.items():
            assert "name" in persona, f"'{key}' missing 'name'"
            assert "system_prompt" in persona, f"'{key}' missing 'system_prompt'"
            assert isinstance(persona["name"], str)
            assert isinstance(persona["system_prompt"], str)
            assert len(persona["system_prompt"]) > 0

    def test_rotation_order_is_correct_sequence(self):
        """ROTATION_ORDER should be wartime_ceo -> methodical_analyst -> quest_master."""
        from tools.coaching_engine import ROTATION_ORDER
        assert ROTATION_ORDER == ["wartime_ceo", "methodical_analyst", "quest_master"]


# ---------------------------------------------------------------------------
# get_next_persona — round-robin rotation
# ---------------------------------------------------------------------------

class TestGetNextPersona:
    """Test persona rotation logic with mocked Settings DB reads."""

    def _mock_settings_response(self, value: str):
        """Build a mock Notion query response with a given LAST_COACH_PERSONA value."""
        if value is None:
            # Row exists but Value is empty
            return {
                "results": [
                    {
                        "id": "page-1",
                        "properties": {
                            "Value": {"rich_text": []}
                        },
                    }
                ]
            }
        return {
            "results": [
                {
                    "id": "page-1",
                    "properties": {
                        "Value": {
                            "rich_text": [{"plain_text": value}]
                        }
                    },
                }
            ]
        }

    def _call_with_last_persona(self, last_value):
        """Helper: mock Notion and call get_next_persona."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = self._mock_settings_response(last_value)

        with patch("tools.coaching_engine._get_notion_client", return_value=mock_notion):
            from tools.coaching_engine import get_next_persona
            return get_next_persona()

    def test_wartime_to_analyst(self):
        """wartime_ceo -> methodical_analyst."""
        assert self._call_with_last_persona("wartime_ceo") == "methodical_analyst"

    def test_analyst_to_quest_master(self):
        """methodical_analyst -> quest_master."""
        assert self._call_with_last_persona("methodical_analyst") == "quest_master"

    def test_quest_master_wraps_to_wartime(self):
        """quest_master -> wartime_ceo (wrap around)."""
        assert self._call_with_last_persona("quest_master") == "wartime_ceo"

    def test_empty_value_starts_at_wartime(self):
        """Empty LAST_COACH_PERSONA should default to wartime_ceo."""
        assert self._call_with_last_persona(None) == "wartime_ceo"

    def test_invalid_value_starts_at_wartime(self):
        """Invalid/unknown persona name should default to wartime_ceo."""
        assert self._call_with_last_persona("nonexistent_persona") == "wartime_ceo"

    def test_no_results_row_starts_at_wartime(self):
        """If the LAST_COACH_PERSONA row doesn't exist, default to wartime_ceo."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": []}

        with patch("tools.coaching_engine._get_notion_client", return_value=mock_notion):
            from tools.coaching_engine import get_next_persona
            assert get_next_persona() == "wartime_ceo"

    def test_notion_unavailable_starts_at_wartime(self):
        """If Notion client is None, default to wartime_ceo."""
        with patch("tools.coaching_engine._get_notion_client", return_value=None):
            from tools.coaching_engine import get_next_persona
            assert get_next_persona() == "wartime_ceo"

    def test_notion_exception_starts_at_wartime(self):
        """If Notion query raises, default to wartime_ceo."""
        mock_notion = MagicMock()
        mock_notion.databases.query.side_effect = RuntimeError("API down")

        with patch("tools.coaching_engine._get_notion_client", return_value=mock_notion):
            from tools.coaching_engine import get_next_persona
            assert get_next_persona() == "wartime_ceo"


# ---------------------------------------------------------------------------
# Briefing JSON structure validation
# ---------------------------------------------------------------------------

class TestBriefingJsonStructure:
    """Validate that a well-formed briefing has all required keys and types."""

    def _make_valid_briefing(self):
        return {
            "greeting": "Hello, Commander.",
            "observations": [
                "Your STR XP is lagging behind other stats.",
                "You completed 3 quests this week, up from 1 last week.",
            ],
            "recommendations": [
                "Focus on gym-related activities to boost STR.",
                "Maintain your reading streak for INT gains.",
            ],
            "encouragement": "Keep pushing. The grind is paying off.",
        }

    def test_has_all_required_keys(self):
        """Briefing must contain greeting, observations, recommendations, encouragement."""
        from tools.coaching_engine import BRIEFING_KEYS
        briefing = self._make_valid_briefing()
        assert set(briefing.keys()) >= BRIEFING_KEYS

    def test_greeting_is_string(self):
        briefing = self._make_valid_briefing()
        assert isinstance(briefing["greeting"], str)

    def test_observations_is_list_of_strings(self):
        briefing = self._make_valid_briefing()
        assert isinstance(briefing["observations"], list)
        for item in briefing["observations"]:
            assert isinstance(item, str)

    def test_recommendations_is_list_of_strings(self):
        briefing = self._make_valid_briefing()
        assert isinstance(briefing["recommendations"], list)
        for item in briefing["recommendations"]:
            assert isinstance(item, str)

    def test_encouragement_is_string(self):
        briefing = self._make_valid_briefing()
        assert isinstance(briefing["encouragement"], str)


# ---------------------------------------------------------------------------
# generate_briefing — budget enforcement
# ---------------------------------------------------------------------------

class TestGenerateBriefingBudget:
    """Test that generate_briefing respects the AI budget cap."""

    @patch("tools.coaching_engine.ai_cost_tracker")
    def test_returns_none_when_budget_exceeded(self, mock_tracker):
        """Should return None when check_budget returns False."""
        mock_tracker.check_budget.return_value = False

        from tools.coaching_engine import generate_briefing
        result = generate_briefing("char-001")

        assert result is None
        mock_tracker.check_budget.assert_called_once()

    @patch("tools.coaching_engine.ai_cost_tracker")
    def test_does_not_call_openai_when_budget_exceeded(self, mock_tracker):
        """Should NOT call OpenAI when budget is exceeded."""
        mock_tracker.check_budget.return_value = False

        with patch("tools.coaching_engine.OpenAI") as mock_openai_cls:
            from tools.coaching_engine import generate_briefing
            generate_briefing("char-001")
            mock_openai_cls.assert_not_called()


# ---------------------------------------------------------------------------
# generate_briefing — API error handling
# ---------------------------------------------------------------------------

class TestGenerateBriefingApiErrors:
    """Test that generate_briefing handles OpenAI API failures gracefully."""

    @patch("tools.coaching_engine._update_last_persona")
    @patch("tools.coaching_engine.build_coaching_context", return_value={"test": True})
    @patch("tools.coaching_engine.get_next_persona", return_value="wartime_ceo")
    @patch("tools.coaching_engine.ai_cost_tracker")
    @patch("tools.coaching_engine.OpenAI")
    def test_returns_none_on_api_exception(
        self, mock_openai_cls, mock_tracker, mock_get_persona, mock_build_ctx, mock_update
    ):
        """OpenAI API exception -> return None, do not crash."""
        mock_tracker.check_budget.return_value = True
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = RuntimeError("OpenAI 500")

        from tools.coaching_engine import generate_briefing
        result = generate_briefing("char-001")

        assert result is None

    @patch("tools.coaching_engine._update_last_persona")
    @patch("tools.coaching_engine.build_coaching_context", return_value={"test": True})
    @patch("tools.coaching_engine.get_next_persona", return_value="wartime_ceo")
    @patch("tools.coaching_engine.ai_cost_tracker")
    @patch("tools.coaching_engine.OpenAI")
    def test_returns_none_on_invalid_json_response(
        self, mock_openai_cls, mock_tracker, mock_get_persona, mock_build_ctx, mock_update
    ):
        """If the API returns non-JSON content, should return None."""
        mock_tracker.check_budget.return_value = True

        # Build a mock response with invalid JSON
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 200

        mock_choice = MagicMock()
        mock_choice.message.content = "This is not valid JSON {{{{"

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        mock_tracker.record_spend.return_value = 0.001

        from tools.coaching_engine import generate_briefing
        result = generate_briefing("char-001")

        assert result is None


# ---------------------------------------------------------------------------
# generate_briefing — successful path
# ---------------------------------------------------------------------------

class TestGenerateBriefingSuccess:
    """Test the full happy path of generate_briefing with all mocks."""

    @patch("tools.coaching_engine._update_last_persona")
    @patch("tools.coaching_engine.build_coaching_context")
    @patch("tools.coaching_engine.get_next_persona", return_value="methodical_analyst")
    @patch("tools.coaching_engine.ai_cost_tracker")
    @patch("tools.coaching_engine.OpenAI")
    def test_successful_briefing_returns_expected_structure(
        self, mock_openai_cls, mock_tracker, mock_get_persona, mock_build_ctx, mock_update
    ):
        """Happy path: budget ok, API returns valid JSON, result has persona/briefing/cost."""
        mock_tracker.check_budget.return_value = True
        mock_tracker.record_spend.return_value = 0.000135

        mock_build_ctx.return_value = {
            "character_stats": {"stat_xps": {"STR": 200}},
            "weekly_xp": {"STR": 50},
        }

        valid_briefing = {
            "greeting": "Greetings, analyst here.",
            "observations": ["STR is progressing steadily."],
            "recommendations": ["Increase workout frequency."],
            "encouragement": "The data shows growth.",
        }

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 200

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(valid_briefing)

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        from tools.coaching_engine import generate_briefing
        result = generate_briefing("char-001")

        assert result is not None
        assert result["persona"] == "Methodical Analyst"
        assert result["cost"] == pytest.approx(0.000135)
        assert result["briefing"]["greeting"] == valid_briefing["greeting"]
        assert result["briefing"]["observations"] == valid_briefing["observations"]
        assert result["briefing"]["recommendations"] == valid_briefing["recommendations"]
        assert result["briefing"]["encouragement"] == valid_briefing["encouragement"]

        # Verify persona was persisted
        mock_update.assert_called_once_with("methodical_analyst")

        # Verify record_spend was called
        mock_tracker.record_spend.assert_called_once()

    @patch("tools.coaching_engine._update_last_persona")
    @patch("tools.coaching_engine.build_coaching_context", return_value={})
    @patch("tools.coaching_engine.get_next_persona", return_value="quest_master")
    @patch("tools.coaching_engine.ai_cost_tracker")
    @patch("tools.coaching_engine.OpenAI")
    def test_missing_keys_filled_with_defaults(
        self, mock_openai_cls, mock_tracker, mock_get_persona, mock_build_ctx, mock_update
    ):
        """If the AI response is missing some keys, they get filled with defaults."""
        mock_tracker.check_budget.return_value = True
        mock_tracker.record_spend.return_value = 0.0001

        # AI only returns greeting and encouragement, missing observations/recommendations
        partial_briefing = {
            "greeting": "Hero! Your quest awaits.",
            "encouragement": "Onward!",
        }

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 80
        mock_usage.completion_tokens = 50

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(partial_briefing)

        mock_response = MagicMock()
        mock_response.usage = mock_usage
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = mock_response

        from tools.coaching_engine import generate_briefing
        result = generate_briefing("char-001")

        assert result is not None
        briefing = result["briefing"]
        # Missing keys should be filled with defaults
        assert isinstance(briefing["observations"], list)
        assert isinstance(briefing["recommendations"], list)
        assert briefing["greeting"] == "Hero! Your quest awaits."
        assert briefing["encouragement"] == "Onward!"
