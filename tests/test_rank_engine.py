"""Tests for rank_engine.py — threshold mapping and high-water mark."""
import pytest
from tools.rank_engine import get_rank_from_xp, _rank_tier, RANK_ORDER


class TestGetRankFromXP:
    """Test all 7 threshold boundaries."""

    def test_zero_xp_is_peasant(self):
        assert get_rank_from_xp(0) == "Peasant"

    def test_just_below_squire(self):
        assert get_rank_from_xp(999) == "Peasant"

    def test_exactly_squire(self):
        assert get_rank_from_xp(1000) == "Squire"

    def test_just_below_knight(self):
        assert get_rank_from_xp(4999) == "Squire"

    def test_exactly_knight(self):
        assert get_rank_from_xp(5000) == "Knight"

    def test_just_below_champion(self):
        assert get_rank_from_xp(14999) == "Knight"

    def test_exactly_champion(self):
        assert get_rank_from_xp(15000) == "Champion"

    def test_just_below_hero(self):
        assert get_rank_from_xp(39999) == "Champion"

    def test_exactly_hero(self):
        assert get_rank_from_xp(40000) == "Hero"

    def test_just_below_legend(self):
        assert get_rank_from_xp(99999) == "Hero"

    def test_exactly_legend(self):
        assert get_rank_from_xp(100000) == "Legend"

    def test_just_below_mythic(self):
        assert get_rank_from_xp(249999) == "Legend"

    def test_exactly_mythic(self):
        assert get_rank_from_xp(250000) == "Mythic"

    def test_way_above_mythic(self):
        assert get_rank_from_xp(999999) == "Mythic"

    def test_negative_xp(self):
        """Edge case: negative XP should still return Peasant."""
        assert get_rank_from_xp(-100) == "Peasant"


class TestRankTier:
    """Test numeric tier ordering."""

    def test_peasant_is_tier_0(self):
        assert _rank_tier("Peasant") == 0

    def test_mythic_is_tier_6(self):
        assert _rank_tier("Mythic") == 6

    def test_all_ranks_ordered(self):
        for i, rank in enumerate(RANK_ORDER):
            assert _rank_tier(rank) == i

    def test_unknown_rank_is_tier_0(self):
        assert _rank_tier("InvalidRank") == 0

    def test_tier_ordering_monotonic(self):
        """Each rank tier is strictly higher than the previous."""
        for i in range(1, len(RANK_ORDER)):
            assert _rank_tier(RANK_ORDER[i]) > _rank_tier(RANK_ORDER[i - 1])
