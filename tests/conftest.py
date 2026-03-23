"""Shared pytest fixtures for the Gamify RPG test suite.
Provides mock Notion responses for all reward system engines.
"""
import pytest


@pytest.fixture
def mock_character():
    """A sample character dict as returned by get_character()."""
    return {
        "Name": "TestHero",
        "Total XP": 5500,
        "Current Rank": "Knight",
        "Player Level": 5,
        "Current Coins": 500,
        "Gold": 1000,
        "Current HP": 800,
        "Max HP": 1000,
        "STR Level": 5,
        "INT Level": 3,
        "WIS Level": 7,
        "VIT Level": 4,
        "CHA Level": 2,
        "STR XP": 200,
        "INT XP": 150,
        "WIS XP": 350,
        "VIT XP": 180,
        "CHA XP": 100,
        "Avatar URL": None,
        "Radar Chart URL": None,
        "Pity Counter": 0,
        "Death Count": 0,
    }


@pytest.fixture
def mock_achievements():
    """Sample achievement definitions from Achievements DB."""
    return [
        {
            "id": "ach-001",
            "name": "First Blood",
            "condition_key": "first_workout",
            "xp_bonus": 50,
            "domain": "STR",
            "icon_url": "",
        },
        {
            "id": "ach-002",
            "name": "Budget Conscious",
            "condition_key": "first_budget",
            "xp_bonus": 50,
            "domain": "WIS",
            "icon_url": "",
        },
        {
            "id": "ach-003",
            "name": "On a Roll",
            "condition_key": "streak_3",
            "xp_bonus": 25,
            "domain": "VIT",
            "icon_url": "",
        },
        {
            "id": "ach-004",
            "name": "Weekly Warrior",
            "condition_key": "streak_7",
            "xp_bonus": 75,
            "domain": "STR",
            "icon_url": "",
        },
        {
            "id": "ach-005",
            "name": "Squire's Honor",
            "condition_key": "rank_squire",
            "xp_bonus": 100,
            "domain": "CHA",
            "icon_url": "",
        },
    ]


@pytest.fixture
def mock_loot_result():
    """Sample loot box result."""
    return {
        "rarity": "Rare",
        "coins_awarded": 75,
        "gold_spent": 100,
        "pity_counter": 5,
        "inventory_id": "inv-001",
    }


@pytest.fixture
def mock_character_page():
    """Full Notion page response for a character (as returned by pages.retrieve)."""
    return {
        "id": "char-001",
        "url": "https://notion.so/char-001",
        "properties": {
            "Name": {"title": [{"plain_text": "TestHero"}]},
            "Player Level": {"number": 1},
            "Current Rank": {"select": {"name": "Peasant"}},
            "Current HP": {"number": 1000},
            "Current Coins": {"number": 0},
            "Gold": {"number": 0},
            "Avatar URL": {"url": None},
            "Radar Chart URL": {"url": None},
            "Class": {"select": {"name": "Warrior"}},
            "STR XP": {"number": 0},
            "INT XP": {"number": 0},
            "WIS XP": {"number": 0},
            "VIT XP": {"number": 0},
            "CHA XP": {"number": 0},
        },
    }


@pytest.fixture
def mock_habit_rows():
    """Sample Good Habit DB query results."""
    return {
        "results": [
            {"id": f"habit-{i}", "properties": {"Name": {"title": [{"plain_text": name}]}}}
            for i, name in enumerate(["Exercise", "Read 30min", "Track Expenses", "Eat Clean", "Social Interaction"])
        ]
    }


@pytest.fixture
def mock_bad_habit_rows():
    """Sample Bad Habit DB query results."""
    return {
        "results": [
            {"id": f"bad-{i}", "properties": {"Name": {"title": [{"plain_text": name}]}}}
            for i, name in enumerate(["Junk Food", "Doom Scrolling", "Skipping Workout"])
        ]
    }


@pytest.fixture
def mock_vision_board_rows():
    """Sample Vision Board DB query results (8 categories)."""
    cats = ["Health", "Career", "Finance", "Relationships", "Learning", "Creativity", "Adventure", "Spirituality"]
    return {
        "results": [
            {"id": f"vb-{i}", "properties": {"Category": {"select": {"name": cat}}}}
            for i, cat in enumerate(cats)
        ]
    }


@pytest.fixture
def mock_identity_rows():
    """Sample Onboarding Identity DB query results."""
    return {
        "results": [
            {"id": "id-001", "properties": {"Type": {"select": {"name": "Strength"}}, "Entry": {"rich_text": [{"plain_text": "Disciplined"}]}}},
            {"id": "id-002", "properties": {"Type": {"select": {"name": "Weakness"}}, "Entry": {"rich_text": [{"plain_text": "Procrastination"}]}}},
        ]
    }


@pytest.fixture
def mock_dashboard_page():
    """Sample Notion page representing an existing dashboard."""
    return {
        "id": "dash-001",
        "url": "https://notion.so/dash-001",
        "properties": {
            "title": {"title": [{"plain_text": "Daily Dashboard"}]},
        },
    }


@pytest.fixture
def mock_db_ids():
    """Sample database IDs for Notion queries."""
    return {
        "character": "char-db-id",
        "activity_log": "log-db-id",
        "achievements": "ach-db-id",
        "player_achievements": "pa-db-id",
        "loot_box_inventory": "loot-db-id",
        "streak_tracker": "streak-db-id",
        "workout_sessions": "workout-db-id",
        "expense_log": "expense-db-id",
        "settings": "settings-db-id",
    }
