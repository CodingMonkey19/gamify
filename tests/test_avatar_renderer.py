"""Tests for avatar_renderer.py — compositing, placeholder fallback, upload mock."""
import os
import tempfile

import pytest
from PIL import Image

from tools.avatar_renderer import composite_avatar, FRAMES_DIR, AVATAR_SIZE


@pytest.fixture
def temp_output():
    """Provide a temp file path for output and clean up after."""
    path = os.path.join(tempfile.gettempdir(), "test_avatar_output.png")
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def sample_profile():
    """Create a simple test profile picture."""
    path = os.path.join(tempfile.gettempdir(), "test_profile.png")
    img = Image.new("RGBA", (256, 256), (100, 150, 200, 255))
    img.save(path, "PNG")
    yield path
    if os.path.exists(path):
        os.remove(path)


class TestCompositeAvatar:
    def test_output_is_valid_png(self, sample_profile, temp_output):
        result = composite_avatar(sample_profile, "peasant", temp_output)
        assert result == temp_output
        assert os.path.exists(temp_output)
        img = Image.open(temp_output)
        assert img.format == "PNG"

    def test_output_dimensions(self, sample_profile, temp_output):
        composite_avatar(sample_profile, "peasant", temp_output)
        img = Image.open(temp_output)
        assert img.size == (AVATAR_SIZE, AVATAR_SIZE)

    def test_output_has_alpha(self, sample_profile, temp_output):
        composite_avatar(sample_profile, "peasant", temp_output)
        img = Image.open(temp_output)
        assert img.mode == "RGBA"

    def test_placeholder_used_when_no_profile(self, temp_output):
        """When profile_picture_path is None, default placeholder is used."""
        result = composite_avatar(None, "peasant", temp_output)
        assert os.path.exists(result)
        img = Image.open(result)
        assert img.size == (AVATAR_SIZE, AVATAR_SIZE)

    def test_placeholder_used_when_path_missing(self, temp_output):
        """When profile_picture_path points to nonexistent file."""
        result = composite_avatar("/nonexistent/path.png", "squire", temp_output)
        assert os.path.exists(result)

    def test_all_rank_frames_exist(self):
        """Verify all 7 rank frames + default avatar are present."""
        ranks = ["peasant", "squire", "knight", "champion", "hero", "legend", "mythic"]
        for rank in ranks:
            frame_path = os.path.join(FRAMES_DIR, f"{rank}.png")
            assert os.path.exists(frame_path), f"Missing frame: {frame_path}"
        assert os.path.exists(os.path.join(FRAMES_DIR, "default_avatar.png"))

    def test_each_rank_produces_valid_output(self, sample_profile, temp_output):
        """Compositing with each rank frame produces valid output."""
        ranks = ["peasant", "squire", "knight", "champion", "hero", "legend", "mythic"]
        for rank in ranks:
            composite_avatar(sample_profile, rank, temp_output)
            img = Image.open(temp_output)
            assert img.size == (AVATAR_SIZE, AVATAR_SIZE), f"Bad size for rank {rank}"
            assert img.mode == "RGBA", f"Bad mode for rank {rank}"

    def test_unknown_rank_falls_back_to_peasant(self, sample_profile, temp_output):
        """Unknown rank should use peasant frame without crashing."""
        result = composite_avatar(sample_profile, "UnknownRank", temp_output)
        assert os.path.exists(result)
