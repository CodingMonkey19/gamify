"""Tests for weekly_report.py — delta calculation, overdraft, AI budget, fault tolerance."""
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Helpers — build mock Notion snapshot pages
# ---------------------------------------------------------------------------

def _make_snapshot(date_str: str, values: dict) -> dict:
    """Build a mock Notion page representing a Daily Snapshot row.

    Args:
        date_str: "YYYY-MM-DD"
        values: dict of field_name -> number (e.g. {"STR XP": 100, "HP": 800})
    """
    properties = {
        "Date": {"date": {"start": date_str}},
    }
    for field, val in values.items():
        properties[field] = {"number": val}
    # Add Character relation (not used in delta calc but present in real data)
    properties["Character"] = {"relation": [{"id": "char-001"}]}
    return {"properties": properties}


# Base field values for snapshot construction
BASE_VALUES = {
    "STR XP": 100, "INT XP": 200, "WIS XP": 150, "VIT XP": 80, "CHA XP": 50,
    "Level": 5, "Gold": 100, "Coins": 500, "HP": 800,
}

END_VALUES = {
    "STR XP": 250, "INT XP": 280, "WIS XP": 350, "VIT XP": 130, "CHA XP": 80,
    "Level": 6, "Gold": 125, "Coins": 650, "HP": 750,
}


# ---------------------------------------------------------------------------
# Delta calculation tests
# ---------------------------------------------------------------------------

class TestDeltaCalculation:
    """Test compute_deltas with various snapshot counts."""

    def test_delta_calculation_7_snapshots(self):
        """7 snapshots spanning a full week produce correct deltas."""
        # Build 7 snapshots: day 0 = BASE, days 1-5 = intermediate, day 6 = END
        snapshots = []
        for i in range(7):
            date_str = f"2026-03-{16 + i:02d}"
            if i == 0:
                snapshots.append(_make_snapshot(date_str, BASE_VALUES))
            elif i == 6:
                snapshots.append(_make_snapshot(date_str, END_VALUES))
            else:
                # Intermediate values (don't matter for delta calc)
                snapshots.append(_make_snapshot(date_str, BASE_VALUES))

        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": snapshots}

        from tools.weekly_report import compute_deltas

        run_date = datetime(2026, 3, 22, tzinfo=timezone.utc)
        result = compute_deltas(mock_notion, "char-001", run_date)

        assert result["snapshot_count"] == 7
        assert result["deltas"]["STR XP"] == 150   # 250 - 100
        assert result["deltas"]["INT XP"] == 80     # 280 - 200
        assert result["deltas"]["WIS XP"] == 200    # 350 - 150
        assert result["deltas"]["VIT XP"] == 50     # 130 - 80
        assert result["deltas"]["CHA XP"] == 30     # 80 - 50
        assert result["deltas"]["Level"] == 1       # 6 - 5
        assert result["deltas"]["Gold"] == 25       # 125 - 100
        assert result["deltas"]["Coins"] == 150     # 650 - 500
        assert result["deltas"]["HP"] == -50        # 750 - 800

    def test_delta_with_fewer_snapshots(self):
        """3 snapshots — deltas computed from first and last available."""
        snapshots = [
            _make_snapshot("2026-03-18", BASE_VALUES),
            _make_snapshot("2026-03-19", BASE_VALUES),
            _make_snapshot("2026-03-20", END_VALUES),
        ]

        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": snapshots}

        from tools.weekly_report import compute_deltas

        run_date = datetime(2026, 3, 22, tzinfo=timezone.utc)
        result = compute_deltas(mock_notion, "char-001", run_date)

        assert result["snapshot_count"] == 3
        # Deltas still computed: newest (END) - oldest (BASE)
        assert result["deltas"]["STR XP"] == 150
        assert result["deltas"]["HP"] == -50

    def test_delta_with_one_snapshot_returns_zeros(self):
        """Only 1 snapshot — not enough for delta, all zeros."""
        snapshots = [_make_snapshot("2026-03-22", BASE_VALUES)]

        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": snapshots}

        from tools.weekly_report import compute_deltas

        run_date = datetime(2026, 3, 22, tzinfo=timezone.utc)
        result = compute_deltas(mock_notion, "char-001", run_date)

        assert result["snapshot_count"] == 1
        for field in result["deltas"]:
            assert result["deltas"][field] == 0

    def test_delta_with_zero_snapshots_returns_zeros(self):
        """No snapshots at all — all zeros."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": []}

        from tools.weekly_report import compute_deltas

        run_date = datetime(2026, 3, 22, tzinfo=timezone.utc)
        result = compute_deltas(mock_notion, "char-001", run_date)

        assert result["snapshot_count"] == 0
        for field in result["deltas"]:
            assert result["deltas"][field] == 0


# ---------------------------------------------------------------------------
# Overdraft tests
# ---------------------------------------------------------------------------

class TestOverdraftCheck:
    """Test overdraft detection and penalty application."""

    def test_overdraft_detected_and_penalized(self):
        """Negative coins triggers check_overdraft → apply_overdraft_penalty."""
        mock_check = MagicMock(return_value=True)
        mock_apply = MagicMock()

        with patch(
            "tools.weekly_report._try_import",
            side_effect=lambda mod, attr=None: {
                (".coin_engine", "check_overdraft"): mock_check,
                (".coin_engine", "apply_overdraft_penalty"): mock_apply,
            }.get((mod, attr)),
        ):
            from tools.weekly_report import check_overdraft

            result = check_overdraft("char-001")

            assert result["checked"] is True
            assert result["overdraft"] is True
            assert result["penalty_applied"] is True
            mock_check.assert_called_once_with("char-001")
            mock_apply.assert_called_once_with("char-001")

    def test_no_overdraft(self):
        """Positive coins — no penalty applied."""
        mock_check = MagicMock(return_value=False)

        with patch(
            "tools.weekly_report._try_import",
            side_effect=lambda mod, attr=None: {
                (".coin_engine", "check_overdraft"): mock_check,
                (".coin_engine", "apply_overdraft_penalty"): MagicMock(),
            }.get((mod, attr)),
        ):
            from tools.weekly_report import check_overdraft

            result = check_overdraft("char-001")

            assert result["checked"] is True
            assert result["overdraft"] is False
            assert result["penalty_applied"] is False

    def test_coin_engine_unavailable(self):
        """coin_engine not installed — skip gracefully."""
        with patch(
            "tools.weekly_report._try_import",
            return_value=None,
        ):
            from tools.weekly_report import check_overdraft

            result = check_overdraft("char-001")

            assert result["checked"] is False


# ---------------------------------------------------------------------------
# AI cost cap tests
# ---------------------------------------------------------------------------

class TestAICostCap:
    """Test AI budget enforcement."""

    def test_ai_cost_cap_skips_coaching(self):
        """When spend >= cap, coaching and quest generation are skipped."""
        mock_notion = MagicMock()
        # AI_MONTHLY_SPEND = 1.50 (over default cap of 1.00)
        mock_notion.databases.query.return_value = {
            "results": [{
                "id": "settings-page",
                "properties": {
                    "Value": {"rich_text": [{"plain_text": "1.50"}]}
                },
            }]
        }

        from tools.weekly_report import run_ai_sections

        with patch("tools.weekly_report.OPENAI_MONTHLY_COST_CAP_USD", 1.00):
            result = run_ai_sections("char-001", mock_notion)

        assert result["ai_skipped"] is True
        assert result["coaching"] is None
        assert result["quests_generated"] is None
        # quests_processed may still run (quest_engine has no AI dependency)

    def test_ai_under_cap_runs_coaching(self):
        """When spend < cap, coaching and quest generation run."""
        mock_notion = MagicMock()
        # AI_MONTHLY_SPEND = 0.10 (under cap)
        mock_notion.databases.query.return_value = {
            "results": [{
                "id": "settings-page",
                "properties": {
                    "Value": {"rich_text": [{"plain_text": "0.10"}]}
                },
            }]
        }

        mock_coaching = MagicMock()
        mock_coaching.generate_briefing.return_value = {
            "persona": "Wartime CEO",
            "briefing": {"greeting": "hi"},
            "cost": 0.02,
        }

        mock_quest_gen = MagicMock()
        mock_quest_gen.generate_quests.return_value = {
            "quests_created": 3,
            "quests_rejected": 0,
            "cost": 0.01,
            "quest_ids": ["q1", "q2", "q3"],
        }

        mock_quest_engine = MagicMock()
        mock_quest_engine.process_all_quests.return_value = {
            "processed": 2,
            "total_xp": 100,
            "total_gold": 10,
            "quests": [],
        }

        with patch("tools.weekly_report.OPENAI_MONTHLY_COST_CAP_USD", 1.00), \
             patch(
                 "tools.weekly_report._try_import",
                 side_effect=lambda mod, attr=None: {
                     ".coaching_engine": mock_coaching,
                     ".quest_generator": mock_quest_gen,
                     ".quest_engine": mock_quest_engine,
                 }.get(mod),
             ):
            from tools.weekly_report import run_ai_sections

            result = run_ai_sections("char-001", mock_notion)

        assert result["ai_skipped"] is False
        assert result["coaching"] is not None
        assert result["coaching"]["persona"] == "Wartime CEO"
        assert result["quests_generated"]["quests_created"] == 3
        assert result["ai_cost"] == pytest.approx(0.03)


# ---------------------------------------------------------------------------
# AI failure doesn't crash
# ---------------------------------------------------------------------------

class TestAIFailureGraceful:
    """AI engine failures should not crash the report."""

    def test_ai_failure_doesnt_crash(self):
        """coaching_engine.generate_briefing raises — report continues."""
        mock_notion = MagicMock()
        # Under budget
        mock_notion.databases.query.return_value = {
            "results": [{
                "id": "settings-page",
                "properties": {
                    "Value": {"rich_text": [{"plain_text": "0.00"}]}
                },
            }]
        }

        mock_coaching = MagicMock()
        mock_coaching.generate_briefing.side_effect = RuntimeError("API down")

        mock_quest_gen = MagicMock()
        mock_quest_gen.generate_quests.return_value = None  # Also fails gracefully

        mock_quest_engine = MagicMock()
        mock_quest_engine.process_all_quests.return_value = {
            "processed": 0, "total_xp": 0, "total_gold": 0, "quests": [],
        }

        with patch("tools.weekly_report.OPENAI_MONTHLY_COST_CAP_USD", 1.00), \
             patch(
                 "tools.weekly_report._try_import",
                 side_effect=lambda mod, attr=None: {
                     ".coaching_engine": mock_coaching,
                     ".quest_generator": mock_quest_gen,
                     ".quest_engine": mock_quest_engine,
                 }.get(mod),
             ):
            from tools.weekly_report import run_ai_sections

            # Should not raise
            result = run_ai_sections("char-001", mock_notion)

        assert result["coaching"] is None
        assert result["ai_skipped"] is False


# ---------------------------------------------------------------------------
# Daily automation called first
# ---------------------------------------------------------------------------

class TestDailyAutomationCalledFirst:
    """Verify daily_automation.run_pipeline is called at the start."""

    def test_daily_automation_called_first(self):
        """run_daily_automation calls daily_automation.run_pipeline."""
        mock_daily = MagicMock()
        mock_daily.run_pipeline.return_value = None

        with patch(
            "tools.weekly_report._try_import",
            return_value=mock_daily,
        ):
            from tools.weekly_report import run_daily_automation

            result = run_daily_automation("char-001")

            mock_daily.run_pipeline.assert_called_once_with("char-001")
            assert result is True

    def test_daily_automation_unavailable(self):
        """daily_automation module missing — logs warning, returns False."""
        with patch("tools.weekly_report._try_import", return_value=None):
            from tools.weekly_report import run_daily_automation

            result = run_daily_automation("char-001")
            assert result is False

    def test_daily_automation_failure_doesnt_crash(self):
        """daily_automation.run_pipeline raises — report continues."""
        mock_daily = MagicMock()
        mock_daily.run_pipeline.side_effect = RuntimeError("Pipeline exploded")

        with patch("tools.weekly_report._try_import", return_value=mock_daily):
            from tools.weekly_report import run_daily_automation

            result = run_daily_automation("char-001")
            assert result is False


# ---------------------------------------------------------------------------
# Summary formatting
# ---------------------------------------------------------------------------

class TestFormatSummary:
    """Test the formatted summary output."""

    def test_summary_contains_key_sections(self):
        """Summary includes all expected sections."""
        from tools.weekly_report import format_summary

        delta_info = {
            "deltas": {
                "STR XP": 150, "INT XP": 80, "WIS XP": 200,
                "VIT XP": 50, "CHA XP": 30, "Level": 1,
                "Gold": 25, "Coins": 150, "HP": -50,
            },
            "period_start": "2026-03-16",
            "period_end": "2026-03-22",
            "snapshot_count": 7,
        }
        streaks = {"active": 5, "broken": 1}
        ai_info = {
            "coaching": {"persona": "Wartime CEO", "cost": 0.02},
            "quests_generated": {"quests_created": 3},
            "quests_processed": {"processed": 2},
            "ai_skipped": False,
            "ai_cost": 0.03,
        }
        overdraft_info = {"checked": True, "overdraft": False, "penalty_applied": False}

        summary = format_summary(delta_info, streaks, ai_info, overdraft_info)

        assert "Weekly Report" in summary
        assert "2026-03-16" in summary
        assert "2026-03-22" in summary
        assert "+150" in summary  # STR XP
        assert "-50" in summary   # HP
        assert "Active: 5" in summary
        assert "Broken: 1" in summary
        assert "Completed: 2" in summary
        assert "Generated: 3" in summary
        assert "Wartime CEO" in summary
        assert "clear" in summary  # overdraft status
