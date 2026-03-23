"""Tests for monthly_automation.py — surplus calculation, Gold conversion, Treasury
idempotency, AI spend reset, monthly snapshot."""
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers — build mock Notion Expense Log pages
# ---------------------------------------------------------------------------

def _make_expense_page(date_str: str, amount: float) -> dict:
    """Build a mock Notion page representing an Expense Log entry."""
    return {
        "properties": {
            "Date": {"date": {"start": date_str}},
            "Amount": {"number": amount},
        }
    }


# ---------------------------------------------------------------------------
# Surplus and Gold conversion tests
# ---------------------------------------------------------------------------

class TestSurplusGoldConversion:
    """Test surplus calculation and Gold conversion."""

    def test_surplus_gold_conversion(self):
        """Positive surplus converts to correct Gold and WIS XP."""
        from tools.monthly_automation import convert_surplus_to_gold

        # Surplus = $700, GOLD_CONVERSION_RATE = 10, WIS_XP_PER_GOLD = 5
        with patch("tools.monthly_automation.GOLD_CONVERSION_RATE", 10), \
             patch("tools.monthly_automation.WIS_XP_PER_GOLD", 5):
            result = convert_surplus_to_gold(700.0)

        assert result["gold"] == 70   # 700 / 10
        assert result["wis_xp"] == 350  # 70 * 5

    def test_surplus_with_remainder_floors(self):
        """Non-round surplus floors Gold (int conversion)."""
        from tools.monthly_automation import convert_surplus_to_gold

        with patch("tools.monthly_automation.GOLD_CONVERSION_RATE", 10), \
             patch("tools.monthly_automation.WIS_XP_PER_GOLD", 5):
            result = convert_surplus_to_gold(755.99)

        assert result["gold"] == 75   # int(755.99 / 10) = 75
        assert result["wis_xp"] == 375

    def test_deficit_no_gold(self):
        """Negative surplus produces 0 Gold (max(0, surplus) = 0)."""
        from tools.monthly_automation import convert_surplus_to_gold

        with patch("tools.monthly_automation.GOLD_CONVERSION_RATE", 10), \
             patch("tools.monthly_automation.WIS_XP_PER_GOLD", 5):
            result = convert_surplus_to_gold(-300.0)

        assert result["gold"] == 0
        assert result["wis_xp"] == 0

    def test_zero_surplus_no_gold(self):
        """Zero surplus produces 0 Gold."""
        from tools.monthly_automation import convert_surplus_to_gold

        with patch("tools.monthly_automation.GOLD_CONVERSION_RATE", 10), \
             patch("tools.monthly_automation.WIS_XP_PER_GOLD", 5):
            result = convert_surplus_to_gold(0.0)

        assert result["gold"] == 0
        assert result["wis_xp"] == 0


class TestCalculateSurplus:
    """Test surplus calculation from Expense Log."""

    def test_income_minus_expenses(self):
        """Surplus = MONTHLY_INCOME from config - sum of Expense Log amounts."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {
            "results": [
                _make_expense_page("2026-02-05", 1200.0),
                _make_expense_page("2026-02-20", 1600.0),
            ]
        }

        from tools.monthly_automation import calculate_surplus

        # Mock config to return MONTHLY_INCOME = 4000
        with patch("tools.monthly_automation.get_config", return_value={"MONTHLY_INCOME": 4000}), \
             patch("tools.config.MONTHLY_INCOME", 4000):
            result = calculate_surplus(mock_notion, "2026-02")

        assert result["income"] == 4000.0    # from config
        assert result["expenses"] == 2800.0  # 1200 + 1600
        assert result["surplus"] == 1200.0   # 4000 - 2800

    def test_no_entries_returns_income_only(self):
        """No expense entries — expenses=0, surplus=income."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": []}

        from tools.monthly_automation import calculate_surplus

        with patch("tools.monthly_automation.get_config", return_value={"MONTHLY_INCOME": 3000}), \
             patch("tools.config.MONTHLY_INCOME", 3000):
            result = calculate_surplus(mock_notion, "2026-02")

        assert result["income"] == 3000.0
        assert result["expenses"] == 0.0
        assert result["surplus"] == 3000.0


# ---------------------------------------------------------------------------
# Treasury idempotency tests
# ---------------------------------------------------------------------------

class TestTreasuryIdempotency:
    """Test that duplicate Treasury rows are prevented."""

    def test_treasury_idempotency_existing_row_skips(self):
        """Existing Treasury row for month → return True (skip)."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {
            "results": [{"id": "existing-treasury-row"}]
        }

        from tools.monthly_automation import check_treasury_exists

        assert check_treasury_exists(mock_notion, "2026-02", "char-001") is True

    def test_treasury_no_existing_row(self):
        """No Treasury row for month → return False (proceed)."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": []}

        from tools.monthly_automation import check_treasury_exists

        assert check_treasury_exists(mock_notion, "2026-02", "char-001") is False

    def test_treasury_row_created_with_correct_fields(self):
        """Treasury row has Month, Character, Income, Expenses, Surplus, Gold, WIS XP."""
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "new-treasury-row"}

        from tools.monthly_automation import create_treasury_row

        financials = {"income": 3500.0, "expenses": 2800.0, "surplus": 700.0}
        result = create_treasury_row(
            mock_notion, "2026-02", "char-001", financials, gold=70, wis_xp=350
        )

        assert result is True
        mock_notion.pages.create.assert_called_once()

        create_call = mock_notion.pages.create.call_args
        props = create_call.kwargs["properties"]

        assert props["Name"]["title"][0]["text"]["content"] == "Treasury 2026-02"
        assert props["Month"]["rich_text"][0]["text"]["content"] == "2026-02"
        assert props["Character"]["relation"][0]["id"] == "char-001"
        assert props["Income"]["number"] == 3500.0
        assert props["Total Expenses"]["number"] == 2800.0
        assert props["Surplus"]["number"] == 700.0
        assert props["Gold Earned"]["number"] == 70
        assert props["WIS XP"]["number"] == 350

    def test_deficit_treasury_row_still_created(self):
        """Negative surplus → Gold=0, but Treasury row still created."""
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {"id": "deficit-row"}

        from tools.monthly_automation import create_treasury_row

        financials = {"income": 1000.0, "expenses": 1500.0, "surplus": -500.0}
        result = create_treasury_row(
            mock_notion, "2026-02", "char-001", financials, gold=0, wis_xp=0
        )

        assert result is True
        create_call = mock_notion.pages.create.call_args
        props = create_call.kwargs["properties"]
        assert props["Gold Earned"]["number"] == 0
        assert props["Surplus"]["number"] == -500.0


# ---------------------------------------------------------------------------
# AI spend reset tests
# ---------------------------------------------------------------------------

class TestAISpendReset:
    """Test AI_MONTHLY_SPEND reset to 0."""

    def test_ai_spend_reset(self):
        """AI_MONTHLY_SPEND Value updated to '0'."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {
            "results": [{
                "id": "ai-spend-page",
                "properties": {
                    "Value": {"rich_text": [{"plain_text": "0.45"}]}
                },
            }]
        }

        from tools.monthly_automation import reset_ai_monthly_spend

        result = reset_ai_monthly_spend(mock_notion)

        assert result is True
        mock_notion.pages.update.assert_called_once()
        update_call = mock_notion.pages.update.call_args
        assert update_call.kwargs["page_id"] == "ai-spend-page"
        value_text = update_call.kwargs["properties"]["Value"]["rich_text"][0]["text"]["content"]
        assert value_text == "0"

    def test_ai_spend_reset_no_row(self):
        """AI_MONTHLY_SPEND row not found — returns False, no crash."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": []}

        from tools.monthly_automation import reset_ai_monthly_spend

        result = reset_ai_monthly_spend(mock_notion)

        assert result is False
        mock_notion.pages.update.assert_not_called()


# ---------------------------------------------------------------------------
# Monthly snapshot tests
# ---------------------------------------------------------------------------

class TestMonthlySnapshot:
    """Test monthly snapshot creation."""

    def test_monthly_snapshot_created(self):
        """snapshot_engine.take_snapshot called with character_id."""
        mock_snapshot = MagicMock()
        mock_snapshot.take_snapshot.return_value = True

        with patch(
            "tools.monthly_automation._try_import",
            return_value=mock_snapshot,
        ):
            from tools.monthly_automation import take_monthly_snapshot

            result = take_monthly_snapshot("char-001")

            assert result is True
            mock_snapshot.take_snapshot.assert_called_once_with("char-001")

    def test_snapshot_engine_unavailable(self):
        """snapshot_engine missing — logs warning, returns False."""
        with patch("tools.monthly_automation._try_import", return_value=None):
            from tools.monthly_automation import take_monthly_snapshot

            result = take_monthly_snapshot("char-001")
            assert result is False


# ---------------------------------------------------------------------------
# WIS XP awarded
# ---------------------------------------------------------------------------

class TestWISXPAwarded:
    """Test WIS XP is correctly awarded based on Gold earned."""

    def test_wis_xp_awarded(self):
        """Gold > 0 → xp_engine.award_xp called with correct WIS XP."""
        mock_award_xp = MagicMock()

        with patch(
            "tools.monthly_automation._try_import",
            side_effect=lambda mod, attr=None: {
                (".coin_engine", "credit_gold"): MagicMock(),
                (".xp_engine", "award_xp"): mock_award_xp,
            }.get((mod, attr)),
        ):
            from tools.monthly_automation import credit_gold_and_xp

            result = credit_gold_and_xp("char-001", gold=70, wis_xp=350)

            assert result["xp_credited"] is True
            mock_award_xp.assert_called_once_with("char-001", "WIS", 350)

    def test_zero_gold_no_xp(self):
        """Gold = 0, WIS XP = 0 → no engine calls."""
        mock_credit = MagicMock()
        mock_award = MagicMock()

        with patch(
            "tools.monthly_automation._try_import",
            side_effect=lambda mod, attr=None: {
                (".coin_engine", "credit_gold"): mock_credit,
                (".xp_engine", "award_xp"): mock_award,
            }.get((mod, attr)),
        ):
            from tools.monthly_automation import credit_gold_and_xp

            result = credit_gold_and_xp("char-001", gold=0, wis_xp=0)

            assert result["gold_credited"] is False
            assert result["xp_credited"] is False
            mock_credit.assert_not_called()
            mock_award.assert_not_called()


# ---------------------------------------------------------------------------
# Target month calculation
# ---------------------------------------------------------------------------

class TestGetTargetMonth:
    """Test previous month calculation."""

    def test_march_returns_february(self):
        from tools.monthly_automation import get_target_month

        run_date = datetime(2026, 3, 15, tzinfo=timezone.utc)
        assert get_target_month(run_date) == "2026-02"

    def test_january_returns_december_previous_year(self):
        from tools.monthly_automation import get_target_month

        run_date = datetime(2026, 1, 5, tzinfo=timezone.utc)
        assert get_target_month(run_date) == "2025-12"

    def test_first_day_of_month(self):
        """Even on the 1st, target is previous month."""
        from tools.monthly_automation import get_target_month

        run_date = datetime(2026, 4, 1, tzinfo=timezone.utc)
        assert get_target_month(run_date) == "2026-03"


# ---------------------------------------------------------------------------
# Summary formatting
# ---------------------------------------------------------------------------

class TestFormatSummary:
    """Test summary output formatting."""

    def test_summary_contains_key_info(self):
        from tools.monthly_automation import format_summary

        financials = {"income": 3500.0, "expenses": 2800.0, "surplus": 700.0}
        summary = format_summary("2026-02", financials, gold=70, wis_xp=350,
                                 treasury_skipped=False)

        assert "Monthly Automation Summary" in summary
        assert "2026-02" in summary
        assert "3,500.00" in summary
        assert "2,800.00" in summary
        assert "700.00" in summary
        assert "Gold earned: 70" in summary
        assert "WIS XP: 350" in summary
        assert "row created" in summary
        assert "reset to $0.00" in summary

    def test_summary_shows_skipped_when_idempotent(self):
        from tools.monthly_automation import format_summary

        financials = {"income": 0.0, "expenses": 0.0, "surplus": 0.0}
        summary = format_summary("2026-02", financials, gold=0, wis_xp=0,
                                 treasury_skipped=True)

        assert "already processed" in summary
