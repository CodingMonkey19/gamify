"""Tests for ai_cost_tracker.py — cost estimation, budget enforcement, spend recording."""
import pytest
from unittest.mock import patch, MagicMock
from tools.ai_cost_tracker import (
    estimate_cost,
    check_budget,
    record_spend,
    get_monthly_spend,
    MODEL_PRICING,
)


class TestEstimateCost:
    def test_known_values_gpt4o_mini(self):
        """100 input + 200 output on gpt-4o-mini should match hand-calculated cost."""
        # (100 * 0.15 + 200 * 0.60) / 1_000_000 = (15 + 120) / 1_000_000 = 0.000135
        cost = estimate_cost(100, 200, model="gpt-4o-mini")
        assert cost == pytest.approx(0.000135)

    def test_zero_tokens_returns_zero(self):
        """0 input + 0 output should return 0.0."""
        assert estimate_cost(0, 0) == 0.0

    def test_input_only(self):
        """Cost with output=0 should reflect input pricing only."""
        cost = estimate_cost(1_000_000, 0, model="gpt-4o-mini")
        assert cost == pytest.approx(0.15)

    def test_output_only(self):
        """Cost with input=0 should reflect output pricing only."""
        cost = estimate_cost(0, 1_000_000, model="gpt-4o-mini")
        assert cost == pytest.approx(0.60)

    def test_unknown_model_falls_back(self):
        """Unknown model should fall back to gpt-4o-mini pricing."""
        known = estimate_cost(500, 500, model="gpt-4o-mini")
        fallback = estimate_cost(500, 500, model="gpt-99-turbo")
        assert known == fallback

    def test_returns_float(self):
        """Return type should always be float."""
        assert isinstance(estimate_cost(100, 200), float)


class TestGetMonthlySpend:
    @patch("tools.ai_cost_tracker._get_notion_client")
    def test_returns_parsed_float(self, mock_get_client):
        """Should parse the rich_text Value as float."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.databases.query.return_value = {
            "results": [
                {
                    "id": "page-1",
                    "properties": {
                        "Value": {
                            "rich_text": [{"plain_text": "0.042500"}]
                        }
                    },
                }
            ]
        }
        assert get_monthly_spend() == pytest.approx(0.0425)

    @patch("tools.ai_cost_tracker._get_notion_client")
    def test_returns_zero_when_no_results(self, mock_get_client):
        """Should return 0.0 when AI_MONTHLY_SPEND row doesn't exist."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.databases.query.return_value = {"results": []}
        assert get_monthly_spend() == 0.0

    @patch("tools.ai_cost_tracker._get_notion_client")
    def test_returns_zero_when_client_unavailable(self, mock_get_client):
        """Should return 0.0 when notion_client is None."""
        mock_get_client.return_value = None
        assert get_monthly_spend() == 0.0

    @patch("tools.ai_cost_tracker._get_notion_client")
    def test_returns_zero_on_exception(self, mock_get_client):
        """Should return 0.0 on any exception."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.databases.query.side_effect = RuntimeError("API down")
        assert get_monthly_spend() == 0.0


class TestCheckBudget:
    @patch("tools.ai_cost_tracker.get_monthly_spend")
    def test_passes_when_under_cap(self, mock_spend):
        """Should return True when projected spend is within budget."""
        mock_spend.return_value = 0.0
        # 1000 input + 1500 output on gpt-4o-mini is tiny relative to $1.00 cap
        assert check_budget(1000, 1500) is True

    @patch("tools.ai_cost_tracker.get_monthly_spend")
    def test_rejects_when_over_cap(self, mock_spend):
        """Should return False when current spend already exceeds cap."""
        mock_spend.return_value = 1.00  # Already at cap
        assert check_budget(1000, 1500) is False

    @patch("tools.ai_cost_tracker.get_monthly_spend")
    def test_rejects_when_would_exceed_cap(self, mock_spend):
        """Should return False when projected call would push over cap."""
        mock_spend.return_value = 0.99
        # Use enough tokens to push over: 1M output = $0.60
        assert check_budget(0, 1_000_000) is False

    @patch("tools.ai_cost_tracker.get_monthly_spend")
    def test_passes_at_exact_cap(self, mock_spend):
        """Should return True when spend + worst_case exactly equals cap."""
        # Cap is $1.00. Set spend so that adding the call cost hits exactly $1.00
        worst_case = estimate_cost(1000, 1500, model="gpt-4o-mini")
        mock_spend.return_value = 1.00 - worst_case
        assert check_budget(1000, 1500) is True

    @patch("tools.ai_cost_tracker.get_monthly_spend")
    def test_zero_tokens_always_passes(self, mock_spend):
        """Zero-token call should always pass unless already over cap."""
        mock_spend.return_value = 0.50
        assert check_budget(0, 0) is True


class TestRecordSpend:
    @patch("tools.ai_cost_tracker._write_monthly_spend")
    @patch("tools.ai_cost_tracker._get_notion_client")
    def test_increments_spend_correctly(self, mock_get_client, mock_write):
        """Should add new cost to existing spend and write back."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.databases.query.return_value = {
            "results": [
                {
                    "id": "page-1",
                    "properties": {
                        "Value": {
                            "rich_text": [{"plain_text": "0.010000"}]
                        }
                    },
                }
            ]
        }

        usage = {"prompt_tokens": 100, "completion_tokens": 200}
        cost = record_spend(usage, model="gpt-4o-mini")

        expected_cost = estimate_cost(100, 200, model="gpt-4o-mini")
        assert cost == pytest.approx(expected_cost)

        # Verify the write was called with old + new
        mock_write.assert_called_once()
        written_amount = mock_write.call_args[0][1]
        assert written_amount == pytest.approx(0.01 + expected_cost)

    @patch("tools.ai_cost_tracker._get_notion_client")
    def test_returns_cost_even_when_client_unavailable(self, mock_get_client):
        """Should still return the calculated cost even if Notion is down."""
        mock_get_client.return_value = None
        usage = {"prompt_tokens": 500, "completion_tokens": 300}
        cost = record_spend(usage)
        expected = estimate_cost(500, 300)
        assert cost == pytest.approx(expected)

    @patch("tools.ai_cost_tracker._write_monthly_spend")
    @patch("tools.ai_cost_tracker._get_notion_client")
    def test_handles_empty_value_as_zero(self, mock_get_client, mock_write):
        """If Value rich_text is empty, current spend should be treated as 0."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.databases.query.return_value = {
            "results": [
                {
                    "id": "page-1",
                    "properties": {
                        "Value": {"rich_text": []}
                    },
                }
            ]
        }

        usage = {"prompt_tokens": 100, "completion_tokens": 100}
        cost = record_spend(usage)

        expected_cost = estimate_cost(100, 100)
        assert cost == pytest.approx(expected_cost)
        mock_write.assert_called_once()
        written_amount = mock_write.call_args[0][1]
        assert written_amount == pytest.approx(expected_cost)

    @patch("tools.ai_cost_tracker._get_notion_client")
    def test_returns_cost_on_query_failure(self, mock_get_client):
        """Should return cost even if the DB query throws."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.databases.query.side_effect = RuntimeError("Notion 500")

        usage = {"prompt_tokens": 200, "completion_tokens": 400}
        cost = record_spend(usage)
        assert cost == pytest.approx(estimate_cost(200, 400))
