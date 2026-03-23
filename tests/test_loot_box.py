"""Tests for loot_box.py — weight distribution, pity timer, rewards, edge cases."""
import pytest
from collections import Counter
from tools.loot_box import roll_rarity, get_coin_reward
from tools.config import LOOT_WEIGHTS, LOOT_REWARDS, PITY_TIMER_THRESHOLD


class TestRollRarity:
    def test_returns_valid_rarity(self):
        """Should return one of the 4 rarity tiers."""
        valid = {"Common", "Rare", "Epic", "Legendary"}
        for _ in range(100):
            result = roll_rarity(0)
            assert result in valid, f"Got unexpected rarity: {result}"

    def test_pity_timer_guarantees_legendary(self):
        """At pity threshold, result MUST be Legendary."""
        for _ in range(20):
            assert roll_rarity(PITY_TIMER_THRESHOLD) == "Legendary"

    def test_pity_timer_above_threshold(self):
        """Above pity threshold also guarantees Legendary."""
        assert roll_rarity(PITY_TIMER_THRESHOLD + 10) == "Legendary"

    def test_pity_timer_just_below_threshold(self):
        """Just below threshold should use RNG (may or may not be Legendary)."""
        # Run many times — should NOT always be Legendary
        results = [roll_rarity(PITY_TIMER_THRESHOLD - 1) for _ in range(100)]
        # At least some should be non-Legendary (statistically guaranteed)
        assert "Common" in results or "Rare" in results or "Epic" in results

    def test_weight_distribution_approximate(self):
        """Over 10,000 samples, distribution should approximate weights ±5%."""
        n = 10000
        counts = Counter(roll_rarity(0) for _ in range(n))

        total_weight = sum(LOOT_WEIGHTS.values())
        for rarity, expected_weight in LOOT_WEIGHTS.items():
            expected_pct = expected_weight / total_weight
            actual_pct = counts.get(rarity, 0) / n
            tolerance = 0.05  # ±5 percentage points
            assert abs(actual_pct - expected_pct) < tolerance, (
                f"{rarity}: expected ~{expected_pct:.2%}, got {actual_pct:.2%}"
            )

    def test_pity_resets_on_legendary_rng(self):
        """If RNG gives Legendary before pity, it should still return Legendary."""
        # We can't force RNG, but we verify that Legendary is a valid RNG result
        results = [roll_rarity(0) for _ in range(10000)]
        assert "Legendary" in results, "Legendary never appeared in 10k rolls"


class TestGetCoinReward:
    def test_common_reward(self):
        assert get_coin_reward("Common") == LOOT_REWARDS["Common"]

    def test_rare_reward(self):
        assert get_coin_reward("Rare") == LOOT_REWARDS["Rare"]

    def test_epic_reward(self):
        assert get_coin_reward("Epic") == LOOT_REWARDS["Epic"]

    def test_legendary_reward(self):
        assert get_coin_reward("Legendary") == LOOT_REWARDS["Legendary"]

    def test_unknown_rarity_returns_zero(self):
        assert get_coin_reward("Mythical") == 0

    def test_rewards_are_integers(self):
        for rarity in ["Common", "Rare", "Epic", "Legendary"]:
            assert isinstance(get_coin_reward(rarity), int)

    def test_rewards_increase_with_rarity(self):
        """Higher rarity should give more Coins."""
        assert get_coin_reward("Common") < get_coin_reward("Rare")
        assert get_coin_reward("Rare") < get_coin_reward("Epic")
        assert get_coin_reward("Epic") < get_coin_reward("Legendary")

    def test_default_values_match_spec(self):
        """Verify default rewards match the spec values."""
        assert get_coin_reward("Common") == 25
        assert get_coin_reward("Rare") == 75
        assert get_coin_reward("Epic") == 200
        assert get_coin_reward("Legendary") == 1000
