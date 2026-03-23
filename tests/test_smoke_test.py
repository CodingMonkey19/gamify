"""Tests for smoke_test.py — env var checks, API connectivity, warnings."""
import os
import pytest
from unittest.mock import patch, MagicMock

from tools.smoke_test import run, SmokeTestError


class TestSmokeTest:
    """Smoke test validation checks."""

    def test_missing_notion_token_raises(self):
        """No NOTION_TOKEN → SmokeTestError."""
        env = {"CHARACTER_ID": "test-char-id"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SmokeTestError, match="NOTION_TOKEN"):
                run()

    def test_missing_character_id_raises(self):
        """No CHARACTER_ID and no --character-id → SmokeTestError."""
        env = {"NOTION_TOKEN": "ntn_test_token"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(SmokeTestError, match="CHARACTER_ID"):
                run()

    def test_api_unreachable_raises(self):
        """Notion API unreachable → SmokeTestError."""
        env = {
            "NOTION_TOKEN": "ntn_test_token",
            "CHARACTER_ID": "test-char-id",
        }
        mock_client_instance = MagicMock()
        mock_client_instance.users.me.side_effect = Exception("Connection refused")

        with patch.dict(os.environ, env, clear=True):
            with patch("tools.smoke_test.Client", return_value=mock_client_instance):
                with pytest.raises(SmokeTestError, match="Notion API unreachable"):
                    run()

    def test_optional_missing_logs_warning(self, caplog):
        """No OPENAI_API_KEY → warning logged, no error raised."""
        env = {
            "NOTION_TOKEN": "ntn_test_token",
            "CHARACTER_ID": "test-char-id",
        }
        mock_client_instance = MagicMock()
        mock_client_instance.users.me.return_value = {"name": "Test Bot"}

        with patch.dict(os.environ, env, clear=True):
            with patch("tools.smoke_test.Client", return_value=mock_client_instance):
                import logging
                with caplog.at_level(logging.WARNING):
                    result = run()

                assert result == "test-char-id"
                assert any("OPENAI_API_KEY" in msg for msg in caplog.messages)

    def test_all_pass_returns_character_id(self):
        """All env vars set, API works → returns character_id."""
        env = {
            "NOTION_TOKEN": "ntn_test_token",
            "CHARACTER_ID": "test-char-id",
            "OPENAI_API_KEY": "sk-test",
            "NOTION_PARENT_PAGE_ID": "page-id-123",
        }
        mock_client_instance = MagicMock()
        mock_client_instance.users.me.return_value = {"name": "Test Bot"}

        with patch.dict(os.environ, env, clear=True):
            with patch("tools.smoke_test.Client", return_value=mock_client_instance):
                result = run()

        assert result == "test-char-id"

    def test_character_id_argument_overrides_env(self):
        """Passing character_id argument takes precedence over env var."""
        env = {
            "NOTION_TOKEN": "ntn_test_token",
            "CHARACTER_ID": "env-char-id",
            "OPENAI_API_KEY": "sk-test",
        }
        mock_client_instance = MagicMock()
        mock_client_instance.users.me.return_value = {"name": "Test Bot"}

        with patch.dict(os.environ, env, clear=True):
            with patch("tools.smoke_test.Client", return_value=mock_client_instance):
                result = run(character_id="arg-char-id")

        assert result == "arg-char-id"

    def test_character_id_from_env_when_no_arg(self):
        """CHARACTER_ID from env used when no argument passed."""
        env = {
            "NOTION_TOKEN": "ntn_test_token",
            "CHARACTER_ID": "env-char-id",
            "OPENAI_API_KEY": "sk-test",
        }
        mock_client_instance = MagicMock()
        mock_client_instance.users.me.return_value = {"name": "Test Bot"}

        with patch.dict(os.environ, env, clear=True):
            with patch("tools.smoke_test.Client", return_value=mock_client_instance):
                result = run()

        assert result == "env-char-id"
