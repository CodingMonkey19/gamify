"""
Avatar Renderer — Composites player profile picture with rank-specific frame overlay.
Uploads to Cloudinary, updates Character DB Avatar URL.

Usage:
    python -m tools.avatar_renderer --character-id <ID>
"""
import argparse
import os
import sys
import tempfile

from PIL import Image, ImageDraw
import numpy as np

from .config import get_config
from .logger import get_logger

logger = get_logger(__name__)

FRAMES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "frames")
AVATAR_SIZE = 512  # Output size


def _remove_checkerboard_bg(img: Image.Image) -> Image.Image:
    """Convert an RGB image with checkerboard transparency pattern to RGBA.
    Detects the grey checkerboard background and makes it transparent.
    """
    if img.mode == "RGBA":
        return img

    img_rgba = img.convert("RGBA")
    data = np.array(img_rgba)

    # Checkerboard pixels are typically grey (~164,166,164) or light grey (~191,191,191)
    # Detect pixels where R,G,B are all within a narrow range (grey) and near the
    # known checkerboard values
    r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]

    # Grey detection: all channels similar and in the checkerboard range
    is_grey = (
        (np.abs(r.astype(int) - g.astype(int)) < 10) &
        (np.abs(g.astype(int) - b.astype(int)) < 10) &
        (np.abs(r.astype(int) - b.astype(int)) < 10)
    )

    # Checkerboard pattern alternates between two specific grey values
    is_light_check = is_grey & (r > 230) & (r < 255)
    is_dark_check = is_grey & (r > 150) & (r < 180)
    is_checkerboard = is_light_check | is_dark_check

    # Make checkerboard pixels transparent
    data[is_checkerboard, 3] = 0

    return Image.fromarray(data)


def _create_circular_mask(size: int) -> Image.Image:
    """Create a circular mask for avatar cropping."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask


def composite_avatar(profile_picture_path: str, rank: str, output_path: str) -> str:
    """Composite player profile picture with rank-specific frame overlay.
    Loads frame from assets/frames/{rank.lower()}.png.
    Uses default placeholder if profile_picture_path is None or missing.
    Returns: output_path of composited image.
    """
    # Load profile picture (or placeholder)
    if profile_picture_path and os.path.exists(profile_picture_path):
        profile = Image.open(profile_picture_path)
        logger.info(f"Loaded profile picture: {profile_picture_path}")
    else:
        placeholder_path = os.path.join(FRAMES_DIR, "default_avatar.png")
        if os.path.exists(placeholder_path):
            profile = Image.open(placeholder_path)
            logger.info("Using default avatar placeholder")
        else:
            # Fallback: solid dark grey circle
            profile = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (55, 71, 79, 255))
            logger.warning("No profile picture or placeholder found, using solid fill")

    # Resize profile to avatar size
    profile = profile.convert("RGBA").resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

    # Crop profile to circle
    mask = _create_circular_mask(AVATAR_SIZE)
    profile_circular = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (0, 0, 0, 0))
    profile_circular.paste(profile, (0, 0), mask)

    # Load rank frame
    frame_path = os.path.join(FRAMES_DIR, f"{rank.lower()}.png")
    if not os.path.exists(frame_path):
        logger.warning(f"Frame not found for rank '{rank}' at {frame_path}, using peasant frame")
        frame_path = os.path.join(FRAMES_DIR, "peasant.png")

    frame = Image.open(frame_path)
    frame = frame.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

    # Handle checkerboard background in frame
    frame = _remove_checkerboard_bg(frame)

    # Composite: profile underneath, frame on top
    result = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (0, 0, 0, 0))
    result.paste(profile_circular, (0, 0), profile_circular)
    result.alpha_composite(frame)

    # Save
    result.save(output_path, "PNG")
    logger.info(f"Composited avatar saved: {output_path}")

    return output_path


def upload_image(image_path: str) -> str:
    """Upload image to Cloudinary, return hosted URL.
    Returns: URL string. Raises on upload failure.
    """
    import cloudinary
    import cloudinary.uploader
    from dotenv import load_dotenv

    load_dotenv()

    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    )

    result = cloudinary.uploader.upload(
        image_path,
        folder="gamify/avatars",
        overwrite=True,
        resource_type="image",
    )

    url = result.get("secure_url")
    if not url:
        raise RuntimeError(f"Cloudinary upload returned no URL: {result}")

    logger.info(f"Uploaded to Cloudinary: {url}")
    return url


def update_character_avatar(character_id: str) -> dict:
    """Full pipeline: fetch profile picture URL from Character DB, download it,
    read current rank, composite with frame, upload, write Avatar URL back.
    Returns: {"character_id": str, "rank": str, "avatar_url": str}
    Returns None if upload fails (logged as warning, retried next run).
    """
    from .notion_client import get_notion_client, get_character, update_character

    notion = get_notion_client()
    character = get_character(notion, character_id)

    rank = character.get("Current Rank", "Peasant") or "Peasant"
    profile_url = character.get("Profile Picture")

    # Download profile picture if URL exists
    profile_path = None
    if profile_url:
        try:
            import urllib.request
            profile_path = os.path.join(tempfile.gettempdir(), f"profile_{character_id}.png")
            urllib.request.urlretrieve(profile_url, profile_path)
            logger.info(f"Downloaded profile picture from {profile_url}")
        except Exception as e:
            logger.warning(f"Failed to download profile picture: {e}")
            profile_path = None

    # Composite avatar
    output_path = os.path.join(tempfile.gettempdir(), f"avatar_{character_id}.png")
    composite_avatar(profile_path, rank, output_path)

    # Upload to Cloudinary
    try:
        avatar_url = upload_image(output_path)
    except Exception as e:
        logger.warning(f"Avatar upload failed: {e}")
        return None

    # Write URL back to Character DB
    update_character(notion, character_id, {"Avatar URL": {"url": avatar_url}})
    logger.info(f"Character {character_id} avatar updated: {avatar_url}")

    return {
        "character_id": character_id,
        "rank": rank,
        "avatar_url": avatar_url,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate and upload character avatar")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = update_character_avatar(args.character_id)
    if result:
        print(f"Avatar updated: {result['avatar_url']}")
    else:
        print("Avatar update failed — check logs")


if __name__ == "__main__":
    main()
