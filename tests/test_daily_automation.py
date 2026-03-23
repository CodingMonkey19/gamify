"""Tests for daily_automation.py — pipeline ordering, fault tolerance, and summary output."""
import sys
from datetime import date
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_module(func_name, return_value=None, side_effect=None):
    """Create a mock module with a single callable attribute."""
    mod = MagicMock()
    fn = MagicMock(return_value=return_value, side_effect=side_effect)
    setattr(mod, func_name, fn)
    return mod, fn


# We patch importlib.import_module inside daily_automation's _try_import so
# we can control which engines are "available" and track call order.

CHARACTER_ID = "test-char-001"


class TestPipelineExecutionOrder:
    """Verify all 16 steps are called in the correct order."""

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_pipeline_execution_order(self, mock_get_config, mock_try_import):
        """All engines available — verify call order matches PIPELINE_STEPS."""
        from tools.daily_automation import run_pipeline, PIPELINE_STEPS

        mock_get_config.return_value = {"KEY": "VALUE"}

        # Track call order
        call_order = []

        def fake_try_import(module_path, func_name):
            fn = MagicMock(return_value={"status": "ok"})
            # Special case: rank_engine returns rank_changed=False by default
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False, "previous_rank": "Peasant", "current_rank": "Peasant"}

            original_fn = fn

            def tracked_fn(*args, **kwargs):
                call_order.append(func_name)
                return original_fn(*args, **kwargs)

            return tracked_fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # Verify smoke_test is first
        assert call_order[0] == "run", "smoke_test.run must be the first step"

        # Verify the overall order (excluding load_settings which uses get_config directly)
        # and avatar_update which is skipped when no rank change
        expected_order = [
            "run",                       # smoke_test
            # load_settings is handled internally via get_config
            "process_daily_habits",      # good habits
            "process_bad_habits",        # bad habits
            "apply_decay",               # streak decay
            "aggregate_xp",              # fitness
            "aggregate_xp",              # nutrition
            "aggregate_xp",              # financial
            "update_character_stats",    # xp update
            "check_death",               # hp check
            "check_rank_up",             # rank check
            # avatar_update skipped (no rank change)
            "check_all_achievements",    # achievements
            "update_character_chart",    # chart
            "take_snapshot",             # snapshot
            "process_all_quests",        # quests
        ]
        assert call_order == expected_order

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_pipeline_execution_order_with_rank_change(self, mock_get_config, mock_try_import):
        """When rank changes, avatar_update is included in the order."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {"KEY": "VALUE"}

        call_order = []

        def fake_try_import(module_path, func_name):
            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": True, "previous_rank": "Peasant", "current_rank": "Squire"}

            original_fn = fn

            def tracked_fn(*args, **kwargs):
                call_order.append(func_name)
                return original_fn(*args, **kwargs)

            return tracked_fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # avatar_update should now be present after check_rank_up
        assert "update_character_avatar" in call_order
        rank_idx = call_order.index("check_rank_up")
        avatar_idx = call_order.index("update_character_avatar")
        assert avatar_idx == rank_idx + 1, "avatar_update must immediately follow rank_check"


class TestFaultTolerance:
    """Verify pipeline continues when individual engines fail."""

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_fault_tolerance_continues_on_error(self, mock_get_config, mock_try_import):
        """One engine raises — remaining steps still run."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {}

        call_order = []

        def fake_try_import(module_path, func_name):
            if func_name == "apply_decay":
                # streak_engine raises an error
                def failing_fn(*args, **kwargs):
                    call_order.append(func_name)
                    raise RuntimeError("Streak API timeout")
                return failing_fn

            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False}

            original_fn = fn

            def tracked_fn(*args, **kwargs):
                call_order.append(func_name)
                return original_fn(*args, **kwargs)

            return tracked_fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # streak_decay failed but subsequent steps still ran
        assert "apply_decay" in call_order
        assert "update_character_stats" in call_order
        assert "check_death" in call_order
        assert "take_snapshot" in call_order
        assert "process_all_quests" in call_order

        # Verify the error was recorded
        assert context["steps_failed"] >= 1
        error_names = [e[0] for e in context["errors"]]
        assert "streak_decay" in error_names

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_multiple_failures_still_complete(self, mock_get_config, mock_try_import):
        """Multiple engines fail — pipeline still completes all steps."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {}

        failing_steps = {"apply_decay", "aggregate_xp", "check_death"}
        call_order = []

        def fake_try_import(module_path, func_name):
            if func_name in failing_steps:
                def failing_fn(*args, **kwargs):
                    call_order.append(func_name)
                    raise RuntimeError(f"{func_name} failed")
                return failing_fn

            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False}

            original_fn = fn

            def tracked_fn(*args, **kwargs):
                call_order.append(func_name)
                return original_fn(*args, **kwargs)

            return tracked_fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # Pipeline completed even with multiple failures
        assert "process_all_quests" in call_order
        assert "take_snapshot" in call_order
        assert context["steps_failed"] >= 2


class TestSmokeTestFailure:
    """Verify smoke test failure aborts the pipeline immediately."""

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_smoke_test_failure_aborts(self, mock_get_config, mock_try_import):
        """smoke_test raises — exit before any processing."""
        from tools.daily_automation import run_pipeline

        call_order = []

        def fake_try_import(module_path, func_name):
            if func_name == "run":
                def smoke_fail(*args, **kwargs):
                    call_order.append("smoke_test")
                    raise RuntimeError("NOTION_TOKEN missing")
                return smoke_fail

            fn = MagicMock(return_value={"status": "ok"})
            original_fn = fn

            def tracked_fn(*args, **kwargs):
                call_order.append(func_name)
                return original_fn(*args, **kwargs)

            return tracked_fn

        mock_try_import.side_effect = fake_try_import

        with pytest.raises(SystemExit) as exc_info:
            run_pipeline(CHARACTER_ID)

        assert exc_info.value.code == 1
        # Only smoke_test was attempted — nothing else ran
        assert call_order == ["smoke_test"]

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_smoke_test_module_missing_aborts(self, mock_get_config, mock_try_import):
        """smoke_test module unavailable — exit(1) immediately."""
        from tools.daily_automation import run_pipeline

        def fake_try_import(module_path, func_name):
            if func_name == "run":
                return None  # Module not found
            return MagicMock(return_value={"status": "ok"})

        mock_try_import.side_effect = fake_try_import

        with pytest.raises(SystemExit) as exc_info:
            run_pipeline(CHARACTER_ID)

        assert exc_info.value.code == 1


class TestIdempotencySnapshotExists:
    """Verify pipeline runs even when snapshot already exists."""

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_idempotency_snapshot_exists(self, mock_get_config, mock_try_import):
        """Snapshot already exists — engines still run, snapshot reports skipped."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {}

        call_order = []

        def fake_try_import(module_path, func_name):
            if func_name == "take_snapshot":
                def snapshot_fn(*args, **kwargs):
                    call_order.append(func_name)
                    return {"skipped": True, "reason": "already exists"}
                return snapshot_fn

            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False}

            original_fn = fn

            def tracked_fn(*args, **kwargs):
                call_order.append(func_name)
                return original_fn(*args, **kwargs)

            return tracked_fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # Snapshot step ran (engine handles idempotency internally)
        assert "take_snapshot" in call_order
        # Other engines also ran (pipeline doesn't skip based on snapshot)
        assert "process_all_quests" in call_order
        assert "check_all_achievements" in call_order


class TestMissingEngineSkipped:
    """Verify missing engine imports are skipped with warnings."""

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_missing_engine_skipped(self, mock_get_config, mock_try_import):
        """Engine import fails — step skipped, remaining steps continue."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {}

        call_order = []

        def fake_try_import(module_path, func_name):
            # Simulate missing engines for habit_engine and fitness_engine
            if func_name in ("process_daily_habits", "process_bad_habits", "aggregate_xp"):
                return None  # Module not available

            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False}

            original_fn = fn

            def tracked_fn(*args, **kwargs):
                call_order.append(func_name)
                return original_fn(*args, **kwargs)

            return tracked_fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # Missing engines were skipped
        assert context["steps_skipped"] >= 3
        # Remaining steps still executed
        assert "update_character_stats" in call_order
        assert "take_snapshot" in call_order
        assert "process_all_quests" in call_order


class TestSummaryOutput:
    """Verify summary includes step counts."""

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_summary_output(self, mock_get_config, mock_try_import, capsys):
        """Summary block includes completed, failed, and skipped counts."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {}

        def fake_try_import(module_path, func_name):
            if func_name in ("process_daily_habits",):
                return None  # Skipped
            if func_name == "apply_decay":
                def failing(*args, **kwargs):
                    raise RuntimeError("fail")
                return failing

            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False}
            return fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        captured = capsys.readouterr()
        output = captured.out

        # Summary contains key fields
        assert "Daily Automation Summary" in output
        assert f"Date: {date.today()}" in output
        assert "Steps completed:" in output
        assert "Steps failed:" in output
        assert "Steps skipped:" in output
        assert "Snapshot:" in output

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_summary_step_counts_accurate(self, mock_get_config, mock_try_import, capsys):
        """Step counts in summary reflect actual pipeline execution."""
        from tools.daily_automation import run_pipeline, PIPELINE_STEPS

        mock_get_config.return_value = {}

        def fake_try_import(module_path, func_name):
            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False}
            return fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # With no rank change, avatar is skipped
        # All other steps should complete
        total = context["total_steps"]
        completed = context["steps_completed"]
        skipped = context["steps_skipped"]
        failed = context["steps_failed"]

        assert completed + skipped + failed == total
        assert failed == 0
        assert skipped == 1  # avatar_update skipped (no rank change)


class TestAvatarOnlyOnRankChange:
    """Verify avatar_renderer is only called when rank actually changes."""

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_avatar_only_on_rank_change(self, mock_get_config, mock_try_import):
        """avatar_renderer NOT called when rank_engine reports no change."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {}
        avatar_called = []

        def fake_try_import(module_path, func_name):
            if func_name == "update_character_avatar":
                def avatar_fn(*args, **kwargs):
                    avatar_called.append(True)
                    return {"status": "ok"}
                return avatar_fn

            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False, "current_rank": "Peasant"}
            return fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # Avatar was NOT called
        assert avatar_called == []
        assert context["results"].get("avatar_update", {}).get("skipped") is True

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_avatar_called_on_rank_change(self, mock_get_config, mock_try_import):
        """avatar_renderer IS called when rank_engine reports a rank change."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {}
        avatar_called = []

        def fake_try_import(module_path, func_name):
            if func_name == "update_character_avatar":
                def avatar_fn(*args, **kwargs):
                    avatar_called.append(True)
                    return {"avatar_url": "https://example.com/avatar.png"}
                return avatar_fn

            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": True, "previous_rank": "Peasant", "current_rank": "Squire"}
            return fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        # Avatar WAS called
        assert avatar_called == [True]
        assert context["results"].get("avatar_update") == {"avatar_url": "https://example.com/avatar.png"}


class TestSnapshotReceivesRunDate:
    """Verify snapshot_engine.take_snapshot receives both character_id and run_date."""

    @patch("tools.daily_automation._try_import")
    @patch("tools.daily_automation.get_config")
    def test_snapshot_receives_run_date(self, mock_get_config, mock_try_import):
        """take_snapshot is called with (character_id, run_date)."""
        from tools.daily_automation import run_pipeline

        mock_get_config.return_value = {}
        snapshot_args = []

        def fake_try_import(module_path, func_name):
            if func_name == "take_snapshot":
                def snapshot_fn(*args, **kwargs):
                    snapshot_args.append(args)
                    return {"snapshot_id": "snap-001"}
                return snapshot_fn

            fn = MagicMock(return_value={"status": "ok"})
            if func_name == "check_rank_up":
                fn.return_value = {"rank_changed": False}
            return fn

        mock_try_import.side_effect = fake_try_import

        context = run_pipeline(CHARACTER_ID)

        assert len(snapshot_args) == 1
        assert snapshot_args[0][0] == CHARACTER_ID
        assert snapshot_args[0][1] == date.today()


class TestCLIEntryPoint:
    """Verify CLI argument handling."""

    @patch("tools.daily_automation.run_pipeline")
    def test_character_id_from_args(self, mock_run_pipeline):
        """--character-id argument is passed to run_pipeline."""
        from tools.daily_automation import main

        mock_run_pipeline.return_value = {"steps_completed": 16}

        test_args = ["daily_automation.py", "--character-id", "abc-123"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            # Exits 0 on success
            assert exc_info.value.code == 0

        mock_run_pipeline.assert_called_once_with("abc-123")

    @patch.dict("os.environ", {"CHARACTER_ID": "env-char-456"})
    @patch("tools.daily_automation.run_pipeline")
    def test_character_id_from_env(self, mock_run_pipeline):
        """Falls back to CHARACTER_ID env var when --character-id not provided."""
        from tools.daily_automation import main

        mock_run_pipeline.return_value = {"steps_completed": 16}

        test_args = ["daily_automation.py"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        mock_run_pipeline.assert_called_once_with("env-char-456")

    @patch.dict("os.environ", {}, clear=True)
    def test_no_character_id_exits_2(self):
        """No character ID anywhere — exits with code 2."""
        from tools.daily_automation import main

        test_args = ["daily_automation.py"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2
