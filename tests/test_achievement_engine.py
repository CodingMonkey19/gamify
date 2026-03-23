"""Tests for achievement_engine.py — condition dispatch, idempotency, XP routing."""
import pytest
from tools.achievement_engine import (
    CONDITION_CHECKERS,
    check_condition,
)


class TestConditionCheckers:
    def test_dispatch_map_has_entries(self):
        """Should have at least 43 condition checkers to cover all achievements."""
        assert len(CONDITION_CHECKERS) >= 43

    def test_all_checkers_are_callable(self):
        """Every entry in dispatch map should be a callable function."""
        for key, checker in CONDITION_CHECKERS.items():
            assert callable(checker), f"Checker '{key}' is not callable"

    def test_unknown_key_returns_false(self):
        """Unknown condition key should return False, not raise."""
        result = check_condition("nonexistent_condition_xyz", None, "fake-id", {})
        assert result is False

    def test_expected_keys_exist(self):
        """All condition keys referenced by seeded achievements must exist."""
        expected = [
            "first_workout", "first_budget", "first_good_habit", "first_goal",
            "first_loot_box", "first_quest", "first_gold", "first_hotel",
            "first_social", "first_meal", "first_death",
            "streak_3", "streak_7", "streak_14", "streak_30", "streak_60", "streak_100",
            "rank_squire", "rank_knight", "rank_champion", "rank_hero", "rank_legend", "rank_mythic",
            "5_workouts", "10_workouts", "25_workouts", "50_workouts", "100_workouts",
            "gold_100", "gold_1000", "gold_10000",
            "coins_100", "coins_500", "coins_1000",
            "xp_1000", "xp_10000",
            "level_5", "level_10", "level_20", "level_30", "level_50",
            "10_meals", "25_meals", "50_meals",
            "protein_10", "protein_25",
            "10_expenses", "50_expenses",
            "volume_10k", "volume_50k",
            "habit_master",
            "speaker", "connector", "creator", "community_builder",
        ]
        for key in expected:
            assert key in CONDITION_CHECKERS, f"Missing condition key: {key}"

    def test_streak_checkers_cover_all_tiers(self):
        """All streak tier milestones should have checkers."""
        streak_keys = ["streak_3", "streak_7", "streak_14", "streak_30", "streak_60", "streak_100"]
        for key in streak_keys:
            assert key in CONDITION_CHECKERS, f"Missing streak checker: {key}"

    def test_rank_checkers_cover_all_ranks(self):
        """All rank milestones should have checkers (except Peasant — everyone starts there)."""
        rank_keys = ["rank_squire", "rank_knight", "rank_champion", "rank_hero", "rank_legend", "rank_mythic"]
        for key in rank_keys:
            assert key in CONDITION_CHECKERS, f"Missing rank checker: {key}"

    def test_workout_milestones_exist(self):
        """Workout milestone checkers should exist."""
        workout_keys = ["first_workout", "5_workouts", "10_workouts", "25_workouts", "50_workouts", "100_workouts"]
        for key in workout_keys:
            assert key in CONDITION_CHECKERS, f"Missing workout checker: {key}"

    def test_gold_milestones_exist(self):
        """Gold milestone checkers should exist."""
        gold_keys = ["gold_100", "gold_1000", "gold_10000"]
        for key in gold_keys:
            assert key in CONDITION_CHECKERS, f"Missing gold checker: {key}"
