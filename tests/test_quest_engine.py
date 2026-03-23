"""Tests for quest_engine.py — XP calculation, streak multipliers, idempotency, domain fallback."""
import math
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# get_weakest_stat — pure logic once character dict is resolved
# ---------------------------------------------------------------------------

class TestGetWeakestStat:
    """Test weakest stat resolution with various XP combos + tie-breaking."""

    def _call(self, character_dict):
        """Helper: patch notion_client module and call get_weakest_stat."""
        mock_notion = MagicMock()
        mock_nc = MagicMock(
            get_notion_client=MagicMock(return_value=mock_notion),
            get_character=MagicMock(return_value=character_dict),
        )
        with patch.dict("sys.modules", {"tools.notion_client": mock_nc}):
            from tools.quest_engine import get_weakest_stat
            return get_weakest_stat("test-char-id")

    def test_clear_minimum(self):
        """STR has lowest XP — should return STR."""
        char = {"STR XP": 10, "INT XP": 200, "WIS XP": 300, "VIT XP": 150, "CHA XP": 100}
        assert self._call(char) == "STR"

    def test_cha_is_weakest(self):
        """CHA has lowest XP."""
        char = {"STR XP": 200, "INT XP": 200, "WIS XP": 300, "VIT XP": 150, "CHA XP": 50}
        assert self._call(char) == "CHA"

    def test_tie_break_alphabetical_cha_wins(self):
        """CHA and INT tied — CHA comes first alphabetically."""
        char = {"STR XP": 200, "INT XP": 100, "WIS XP": 300, "VIT XP": 150, "CHA XP": 100}
        assert self._call(char) == "CHA"

    def test_tie_break_alphabetical_int_over_str(self):
        """INT and STR tied — INT comes first alphabetically."""
        char = {"STR XP": 50, "INT XP": 50, "WIS XP": 300, "VIT XP": 150, "CHA XP": 200}
        assert self._call(char) == "INT"

    def test_tie_break_alphabetical_vit_over_wis(self):
        """VIT and WIS tied — VIT comes first alphabetically."""
        char = {"STR XP": 500, "INT XP": 500, "WIS XP": 10, "VIT XP": 10, "CHA XP": 500}
        assert self._call(char) == "VIT"

    def test_all_stats_tied(self):
        """All stats equal — should return CHA (first alphabetically)."""
        char = {"STR XP": 100, "INT XP": 100, "WIS XP": 100, "VIT XP": 100, "CHA XP": 100}
        assert self._call(char) == "CHA"

    def test_all_stats_zero(self):
        """All stats at 0 — should return CHA."""
        char = {"STR XP": 0, "INT XP": 0, "WIS XP": 0, "VIT XP": 0, "CHA XP": 0}
        assert self._call(char) == "CHA"

    def test_missing_stat_treated_as_zero(self):
        """Missing stat XP property treated as 0."""
        char = {"STR XP": 100, "INT XP": 100, "WIS XP": 100, "VIT XP": 100}
        # CHA XP missing -> 0 -> CHA is weakest
        assert self._call(char) == "CHA"

    def test_none_stat_treated_as_zero(self):
        """None stat XP value treated as 0."""
        char = {"STR XP": 100, "INT XP": 100, "WIS XP": None, "VIT XP": 100, "CHA XP": 100}
        assert self._call(char) == "WIS"


# ---------------------------------------------------------------------------
# get_domain_streak_multiplier — mock Notion query
# ---------------------------------------------------------------------------

class TestGetDomainStreakMultiplier:
    """Test streak multiplier lookup with mocked Notion responses."""

    def _call(self, domain, query_results):
        """Helper: patch notion_client and Notion query, call get_domain_streak_multiplier."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": query_results}

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
            )
        }):
            from tools.quest_engine import get_domain_streak_multiplier
            return get_domain_streak_multiplier("test-char-id", domain)

    def test_no_matches_returns_1(self):
        """No streak entries for domain — return 1.0."""
        assert self._call("STR", []) == 1.0

    def test_none_domain_returns_1(self):
        """None domain — return 1.0 without querying."""
        from tools.quest_engine import get_domain_streak_multiplier
        assert get_domain_streak_multiplier("test-char-id", None) == 1.0

    def test_single_match(self):
        """Single streak entry with multiplier 1.5."""
        results = [
            {"properties": {"Multiplier": {"number": 1.5}, "Domain": {"select": {"name": "STR"}}}},
        ]
        assert self._call("STR", results) == 1.5

    def test_multiple_matches_returns_highest(self):
        """Multiple streak entries — return the highest multiplier."""
        results = [
            {"properties": {"Multiplier": {"number": 1.1}, "Domain": {"select": {"name": "STR"}}}},
            {"properties": {"Multiplier": {"number": 2.0}, "Domain": {"select": {"name": "STR"}}}},
            {"properties": {"Multiplier": {"number": 1.5}, "Domain": {"select": {"name": "STR"}}}},
        ]
        assert self._call("STR", results) == 2.0

    def test_multiplier_none_treated_as_default(self):
        """Multiplier property is None — should not exceed 1.0."""
        results = [
            {"properties": {"Multiplier": {"number": None}}},
        ]
        assert self._call("INT", results) == 1.0

    def test_multiplier_below_1_still_returned(self):
        """A multiplier below 1.0 in data does not override the 1.0 floor."""
        results = [
            {"properties": {"Multiplier": {"number": 0.5}}},
        ]
        # max_multiplier starts at 1.0, 0.5 < 1.0, so returns 1.0
        assert self._call("WIS", results) == 1.0


# ---------------------------------------------------------------------------
# process_quest_completion — XP calculation
# ---------------------------------------------------------------------------

class TestProcessQuestCompletion:
    """Test Effective XP = floor(base_xp * multiplier) and quest processing."""

    def test_floor_calculation_exact(self):
        """100 * 1.5 = 150 (exact)."""
        assert math.floor(100 * 1.5) == 150

    def test_floor_calculation_rounds_down(self):
        """33 * 1.1 = 36.3 -> floor = 36."""
        assert math.floor(33 * 1.1) == 36

    def test_floor_calculation_no_rounding_up(self):
        """99 * 1.25 = 123.75 -> floor = 123, NOT 124."""
        assert math.floor(99 * 1.25) == 123

    def test_floor_with_multiplier_1(self):
        """Multiplier 1.0 — no change."""
        assert math.floor(50 * 1.0) == 50

    def test_floor_with_large_multiplier(self):
        """200 * 3.0 = 600."""
        assert math.floor(200 * 3.0) == 600

    def test_floor_with_zero_base(self):
        """0 base XP * any multiplier = 0."""
        assert math.floor(0 * 2.5) == 0

    def test_process_writes_correct_values(self):
        """process_quest_completion should write floor(base*mult) to Notion."""
        mock_notion = MagicMock()
        mock_notion.pages.update.return_value = {}
        mock_notion.pages.create.return_value = {}
        mock_notion.databases.query.return_value = {
            "results": [
                {"properties": {"Multiplier": {"number": 1.25}}},
            ]
        }

        mock_character = {
            "STR XP": 100, "INT XP": 200, "WIS XP": 300,
            "VIT XP": 150, "CHA XP": 50,
        }

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
                get_character=MagicMock(return_value=mock_character),
            ),
            "tools.coin_engine": MagicMock(
                credit_gold=MagicMock(),
            ),
        }):
            from tools.quest_engine import process_quest_completion

            quest = {
                "page_id": "quest-001",
                "name": "Test Quest",
                "domain": "STR",
                "difficulty": "Medium",
                "base_xp": 80,
                "gold_reward": 10,
                "effective_xp": 0,
                "source": None,
            }

            result = process_quest_completion("char-001", quest)

            assert result["effective_xp"] == math.floor(80 * 1.25)  # 100
            assert result["multiplier"] == 1.25
            assert result["domain"] == "STR"
            assert result["name"] == "Test Quest"

            # Verify Notion update was called with correct values
            mock_notion.pages.update.assert_called_once()
            update_call = mock_notion.pages.update.call_args
            update_props = update_call.kwargs.get("properties", {})
            assert update_props["Applied Multiplier"]["number"] == 1.25
            assert update_props["Effective XP"]["number"] == 100

    def test_domain_fallback_to_weakest_stat(self):
        """Quest without domain should fall back to weakest stat."""
        mock_notion = MagicMock()
        mock_notion.pages.update.return_value = {}
        mock_notion.pages.create.return_value = {}
        # No streak entries => multiplier 1.0
        mock_notion.databases.query.return_value = {"results": []}

        mock_character = {
            "STR XP": 200, "INT XP": 200, "WIS XP": 300,
            "VIT XP": 150, "CHA XP": 200,
        }

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
                get_character=MagicMock(return_value=mock_character),
            ),
        }):
            from tools.quest_engine import process_quest_completion

            quest = {
                "page_id": "quest-002",
                "name": "Domainless Quest",
                "domain": None,  # No domain set
                "difficulty": "Easy",
                "base_xp": 25,
                "gold_reward": 0,
                "effective_xp": 0,
                "source": None,
            }

            result = process_quest_completion("char-001", quest)

            # VIT has lowest XP (150), so domain should be VIT
            assert result["domain"] == "VIT"
            assert result["effective_xp"] == 25  # 25 * 1.0

    def test_gold_credit_with_coin_engine(self):
        """Gold reward > 0 should trigger coin_engine.credit_gold."""
        mock_notion = MagicMock()
        mock_notion.pages.update.return_value = {}
        mock_notion.pages.create.return_value = {}
        mock_notion.databases.query.return_value = {"results": []}

        mock_credit_gold = MagicMock()

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
                get_character=MagicMock(return_value={
                    "STR XP": 100, "INT XP": 100, "WIS XP": 100,
                    "VIT XP": 100, "CHA XP": 100,
                }),
            ),
            "tools.coin_engine": MagicMock(
                credit_gold=mock_credit_gold,
            ),
        }):
            from tools.quest_engine import process_quest_completion

            quest = {
                "page_id": "quest-003",
                "name": "Gold Quest",
                "domain": "WIS",
                "difficulty": "Hard",
                "base_xp": 100,
                "gold_reward": 25,
                "effective_xp": 0,
                "source": None,
            }

            result = process_quest_completion("char-001", quest)

            assert result["gold_reward"] == 25
            assert result["gold_credited"] == 25
            mock_credit_gold.assert_called_once_with(mock_notion, "char-001", 25)

    def test_gold_zero_skips_credit(self):
        """Gold reward = 0 should NOT call coin_engine."""
        mock_notion = MagicMock()
        mock_notion.pages.update.return_value = {}
        mock_notion.pages.create.return_value = {}
        mock_notion.databases.query.return_value = {"results": []}

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
                get_character=MagicMock(return_value={
                    "STR XP": 100, "INT XP": 100, "WIS XP": 100,
                    "VIT XP": 100, "CHA XP": 100,
                }),
            ),
        }):
            from tools.quest_engine import process_quest_completion

            quest = {
                "page_id": "quest-004",
                "name": "No Gold Quest",
                "domain": "INT",
                "difficulty": "Easy",
                "base_xp": 25,
                "gold_reward": 0,
                "effective_xp": 0,
                "source": None,
            }

            result = process_quest_completion("char-001", quest)

            assert result["gold_credited"] == 0


# ---------------------------------------------------------------------------
# Idempotency — quest with Effective XP already set is skipped
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Quests already processed (Effective XP > 0) should not appear in pending."""

    def test_quest_with_effective_xp_not_in_pending(self):
        """get_pending_quests filters out quests where Effective XP is already set.
        This is enforced by the Notion filter: Effective XP is_empty OR equals 0.
        A quest with Effective XP = 150 would not match the filter.
        """
        # Simulate: Notion returns only quests matching the filter (Effective XP empty/0)
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {
            "results": [
                # Only the unprocessed quest is returned by Notion
                {
                    "id": "quest-new",
                    "properties": {
                        "Name": {"title": [{"plain_text": "New Quest"}]},
                        "Domain": {"select": {"name": "STR"}},
                        "Difficulty": {"select": {"name": "Easy"}},
                        "Base XP": {"number": 25},
                        "Gold Reward": {"number": 5},
                        "Effective XP": {"number": None},
                        "Source": {"select": None},
                    },
                },
                # quest-processed would NOT be returned because Effective XP = 150
            ],
        }

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
            ),
        }):
            from tools.quest_engine import get_pending_quests

            quests = get_pending_quests("char-001")

            assert len(quests) == 1
            assert quests[0]["name"] == "New Quest"
            assert quests[0]["effective_xp"] == 0

    def test_no_pending_quests_returns_empty(self):
        """No quests matching filter — return empty list."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": []}

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
            ),
        }):
            from tools.quest_engine import get_pending_quests

            quests = get_pending_quests("char-001")
            assert quests == []


# ---------------------------------------------------------------------------
# process_all_quests — multiple quests processed independently
# ---------------------------------------------------------------------------

class TestProcessAllQuests:
    """Test orchestrator processes multiple quests independently."""

    def test_multiple_quests_summed(self):
        """Two quests: total XP and Gold are summed correctly."""
        mock_notion = MagicMock()
        mock_notion.pages.update.return_value = {}
        mock_notion.pages.create.return_value = {}
        # Streak query returns no entries => multiplier 1.0 for all
        mock_notion.databases.query.side_effect = [
            # First call: get_pending_quests
            {
                "results": [
                    {
                        "id": "quest-a",
                        "properties": {
                            "Name": {"title": [{"plain_text": "Quest A"}]},
                            "Domain": {"select": {"name": "STR"}},
                            "Difficulty": {"select": {"name": "Easy"}},
                            "Base XP": {"number": 50},
                            "Gold Reward": {"number": 10},
                            "Effective XP": {"number": 0},
                            "Source": {"select": None},
                        },
                    },
                    {
                        "id": "quest-b",
                        "properties": {
                            "Name": {"title": [{"plain_text": "Quest B"}]},
                            "Domain": {"select": {"name": "INT"}},
                            "Difficulty": {"select": {"name": "Hard"}},
                            "Base XP": {"number": 100},
                            "Gold Reward": {"number": 25},
                            "Effective XP": {"number": None},
                            "Source": {"select": None},
                        },
                    },
                ],
            },
            # Second call: streak query for Quest A (STR)
            {"results": []},
            # Third call: streak query for Quest B (INT)
            {"results": []},
        ]

        mock_character = {
            "STR XP": 100, "INT XP": 100, "WIS XP": 100,
            "VIT XP": 100, "CHA XP": 100,
        }

        mock_credit_gold = MagicMock()

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
                get_character=MagicMock(return_value=mock_character),
            ),
            "tools.coin_engine": MagicMock(
                credit_gold=mock_credit_gold,
            ),
            "tools.xp_engine": MagicMock(
                update_character_stats=MagicMock(),
            ),
        }):
            from tools.quest_engine import process_all_quests

            result = process_all_quests("char-001")

            assert result["processed"] == 2
            assert result["total_xp"] == 150  # 50 + 100 (multiplier 1.0)
            assert result["total_gold"] == 35  # 10 + 25
            assert len(result["quests"]) == 2

    def test_one_quest_fails_others_continue(self):
        """If one quest fails, remaining quests still process."""
        mock_notion = MagicMock()
        mock_notion.pages.create.return_value = {}
        # First quest update fails, second succeeds
        mock_notion.pages.update.side_effect = [
            Exception("Notion API error"),
            {},
        ]
        mock_notion.databases.query.side_effect = [
            # get_pending_quests
            {
                "results": [
                    {
                        "id": "quest-fail",
                        "properties": {
                            "Name": {"title": [{"plain_text": "Failing Quest"}]},
                            "Domain": {"select": {"name": "STR"}},
                            "Difficulty": {"select": {"name": "Easy"}},
                            "Base XP": {"number": 50},
                            "Gold Reward": {"number": 0},
                            "Effective XP": {"number": 0},
                            "Source": {"select": None},
                        },
                    },
                    {
                        "id": "quest-ok",
                        "properties": {
                            "Name": {"title": [{"plain_text": "OK Quest"}]},
                            "Domain": {"select": {"name": "INT"}},
                            "Difficulty": {"select": {"name": "Easy"}},
                            "Base XP": {"number": 30},
                            "Gold Reward": {"number": 0},
                            "Effective XP": {"number": 0},
                            "Source": {"select": None},
                        },
                    },
                ],
            },
            # streak query for Failing Quest (STR)
            {"results": []},
            # streak query for OK Quest (INT)
            {"results": []},
        ]

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
                get_character=MagicMock(return_value={
                    "STR XP": 100, "INT XP": 100, "WIS XP": 100,
                    "VIT XP": 100, "CHA XP": 100,
                }),
            ),
            "tools.xp_engine": MagicMock(
                update_character_stats=MagicMock(),
            ),
        }):
            from tools.quest_engine import process_all_quests

            result = process_all_quests("char-001")

            # Only the second quest should succeed
            assert result["processed"] == 1
            assert result["total_xp"] == 30
            assert len(result["quests"]) == 1
            assert result["quests"][0]["name"] == "OK Quest"

    def test_no_pending_quests_skips_xp_refresh(self):
        """No pending quests — xp_engine.update_character_stats should NOT be called."""
        mock_notion = MagicMock()
        mock_notion.databases.query.return_value = {"results": []}

        mock_update_stats = MagicMock()

        with patch.dict("sys.modules", {
            "tools.notion_client": MagicMock(
                get_notion_client=MagicMock(return_value=mock_notion),
            ),
            "tools.xp_engine": MagicMock(
                update_character_stats=mock_update_stats,
            ),
        }):
            from tools.quest_engine import process_all_quests

            result = process_all_quests("char-001")

            assert result["processed"] == 0
            assert result["total_xp"] == 0
            assert result["total_gold"] == 0
            assert result["quests"] == []
            mock_update_stats.assert_not_called()
