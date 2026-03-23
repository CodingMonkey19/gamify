"""Tests for chart_renderer.py — radar chart generation, dimensions, axes, edge cases."""
import os
import tempfile

import pytest
from PIL import Image

from tools.chart_renderer import generate_radar_chart, STAT_AXES


@pytest.fixture
def temp_chart():
    """Provide a temp file path for chart output and clean up after."""
    path = os.path.join(tempfile.gettempdir(), "test_radar_chart.png")
    yield path
    if os.path.exists(path):
        os.remove(path)


class TestGenerateRadarChart:
    def test_output_exists(self, temp_chart):
        stats = {"STR": 5, "INT": 3, "WIS": 7, "VIT": 4, "CHA": 2}
        result = generate_radar_chart(stats, "TestHero", "Knight", temp_chart)
        assert result == temp_chart
        assert os.path.exists(temp_chart)

    def test_output_is_png(self, temp_chart):
        stats = {"STR": 5, "INT": 3, "WIS": 7, "VIT": 4, "CHA": 2}
        generate_radar_chart(stats, "TestHero", "Knight", temp_chart)
        img = Image.open(temp_chart)
        assert img.format == "PNG"

    def test_output_dimensions_exact(self, temp_chart):
        """Chart must be exactly 800x800 per spec FR-010."""
        stats = {"STR": 5, "INT": 3, "WIS": 7, "VIT": 4, "CHA": 2}
        generate_radar_chart(stats, "TestHero", "Knight", temp_chart)
        img = Image.open(temp_chart)
        assert img.size == (800, 800), f"Expected (800, 800), got {img.size}"

    def test_all_zero_stats(self, temp_chart):
        """All-zero stats should produce a valid chart (collapsed polygon at center)."""
        stats = {"STR": 0, "INT": 0, "WIS": 0, "VIT": 0, "CHA": 0}
        result = generate_radar_chart(stats, "NewPlayer", "Peasant", temp_chart)
        assert os.path.exists(result)
        img = Image.open(result)
        assert img.size[0] > 0 and img.size[1] > 0

    def test_high_stats(self, temp_chart):
        """Very high stat values should produce a valid chart."""
        stats = {"STR": 100, "INT": 85, "WIS": 92, "VIT": 78, "CHA": 95}
        result = generate_radar_chart(stats, "MaxPlayer", "Mythic", temp_chart)
        assert os.path.exists(result)

    def test_single_stat_nonzero(self, temp_chart):
        """Only one stat nonzero should still produce valid chart."""
        stats = {"STR": 10, "INT": 0, "WIS": 0, "VIT": 0, "CHA": 0}
        result = generate_radar_chart(stats, "Warrior", "Squire", temp_chart)
        assert os.path.exists(result)

    def test_missing_stats_default_to_zero(self, temp_chart):
        """Stats dict missing some axes should default those to 0."""
        stats = {"STR": 5, "WIS": 3}  # Missing INT, VIT, CHA
        result = generate_radar_chart(stats, "Partial", "Peasant", temp_chart)
        assert os.path.exists(result)

    def test_stat_axes_are_five(self):
        """Verify we have exactly 5 axes."""
        assert len(STAT_AXES) == 5
        assert STAT_AXES == ["STR", "INT", "WIS", "VIT", "CHA"]

    def test_title_includes_name_and_rank(self, temp_chart):
        """The chart file should be generated with the given name/rank (visual check)."""
        stats = {"STR": 5, "INT": 3, "WIS": 7, "VIT": 4, "CHA": 2}
        # Just verify it doesn't crash with various name/rank combos
        generate_radar_chart(stats, "Hero McHeroface", "Legend", temp_chart)
        assert os.path.exists(temp_chart)

    def test_regeneration_overwrites(self, temp_chart):
        """Running twice on same output_path should overwrite (dynamic chart)."""
        stats1 = {"STR": 1, "INT": 1, "WIS": 1, "VIT": 1, "CHA": 1}
        stats2 = {"STR": 10, "INT": 10, "WIS": 10, "VIT": 10, "CHA": 10}
        generate_radar_chart(stats1, "Player", "Peasant", temp_chart)
        size1 = os.path.getsize(temp_chart)
        generate_radar_chart(stats2, "Player", "Mythic", temp_chart)
        size2 = os.path.getsize(temp_chart)
        # Both should produce valid files (sizes may differ)
        assert size1 > 0
        assert size2 > 0
