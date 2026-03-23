"""Avatar compositing and Cloudinary upload logic."""

import argparse
import os
import sys
import tempfile
import httpx
from PIL import Image
import cloudinary
import cloudinary.uploader

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import config
import notion_client_wrapper as notion_api

logger = get_logger(__name__)


def composite_avatar(profile_picture_path, rank, output_path):
    """
    Composites a profile picture with a rank frame via Pillow.
    Uses default_avatar.png if profile_picture_path is None or missing.
    """
    assets_dir = os.path.join(os.path.dirname(_tools_dir), "assets", "frames")
    
    # Load frame
    frame_path = os.path.join(assets_dir, f"{rank.lower()}.png")
    if not os.path.exists(frame_path):
        logger.warning(f"Frame not found: {frame_path}. Falling back to peasant.png")
        frame_path = os.path.join(assets_dir, "peasant.png")
    
    frame = Image.open(frame_path).convert("RGBA")
    width, height = frame.size
    
    # Load profile picture
    if not profile_picture_path or not os.path.exists(profile_picture_path):
        profile_picture_path = os.path.join(assets_dir, "default_avatar.png")
        
    try:
        avatar = Image.open(profile_picture_path).convert("RGBA")
    except Exception as e:
        logger.error(f"Failed to open avatar {profile_picture_path}: {e}")
        profile_picture_path = os.path.join(assets_dir, "default_avatar.png")
        avatar = Image.open(profile_picture_path).convert("RGBA")

    # Resize avatar to fit the circular cutout (~380px diameter in 512x512)
    # The Image Assets.csv says: Avatar sits inside circular cutout (center ~380px diameter).
    # We should resize it to 380x380 and place it in the center.
    cutout_diameter = 380
    avatar = avatar.resize((cutout_diameter, cutout_diameter), Image.Resampling.LANCZOS)
    
    # Create a base for composition
    final_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    
    # Paste avatar in center
    offset = ((width - cutout_diameter) // 2, (height - cutout_diameter) // 2)
    final_image.paste(avatar, offset, avatar)
    
    # Paste frame on top
    final_image.paste(frame, (0, 0), frame)
    
    final_image.save(output_path, "PNG")
    logger.info(f"Composited avatar saved to {output_path}")
    return output_path


def upload_image(image_path, cfg=None):
    """
    Uploads an image to Cloudinary, returns hosted URL.
    Returns None if Cloudinary is not configured.
    """
    if cfg is None:
        cfg = config.get_config()
        
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME") or cfg.get("CLOUDINARY_CLOUD_NAME")
    api_key = os.environ.get("CLOUDINARY_API_KEY") or cfg.get("CLOUDINARY_API_KEY")
    api_secret = os.environ.get("CLOUDINARY_API_SECRET") or cfg.get("CLOUDINARY_API_SECRET")
    
    if not all([cloud_name, api_key, api_secret]):
        logger.warning("Cloudinary not configured. Skipping upload.")
        return None
        
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True
    )
    
    try:
        response = cloudinary.uploader.upload(
            image_path,
            folder="gamify_life/avatars",
            overwrite=True,
            resource_type="image"
        )
        return response.get("secure_url")
    except Exception as e:
        logger.error(f"Cloudinary upload failed: {e}")
        return None


def update_character_avatar(character_id, client=None, db_ids=None, cfg=None):
    """
    Main pipeline:
    1. Fetch profile picture URL + rank from Character DB.
    2. Download profile picture to temp file.
    3. Composite with rank frame.
    4. Upload to Cloudinary.
    5. Write URL back to Character DB.
    """
    if client is None:
        client = notion_api.get_client()
    if db_ids is None:
        db_ids = notion_api.get_database_ids()
    if cfg is None:
        cfg = config.get_config(client, db_ids.get("Settings"))
        
    char_page = notion_api.get_page(client, character_id)
    props = char_page.get("properties", {})
    
    rank = props.get("Current Rank", {}).get("select", {}).get("name", "Peasant")
    
    # Handle profile picture URL (can be a Files property or a URL property)
    # The template might use a URL property or a Files/Media property.
    # We'll check 'Profile Picture' URL first, then Files.
    profile_url = None
    url_prop = props.get("Profile Picture", {})
    if url_prop.get("type") == "url":
        profile_url = url_prop.get("url")
    elif url_prop.get("type") == "files":
        files = url_prop.get("files", [])
        if files:
            profile_url = files[0].get("file", {}).get("url") or files[0].get("external", {}).get("url")

    temp_input = None
    try:
        if profile_url:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                temp_input = f.name
                logger.info(f"Downloading profile picture from {profile_url}")
                with httpx.Client() as http_client:
                    resp = http_client.get(profile_url, follow_redirects=True)
                    resp.raise_for_status()
                    f.write(resp.content)
        
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_output = f.name
            
        composite_avatar(temp_input, rank, temp_output)
        
        hosted_url = upload_image(temp_output, cfg)
        
        if hosted_url:
            logger.info(f"Writing new Avatar URL for {character_id}: {hosted_url}")
            notion_api.update_page(client, character_id, {
                "Avatar URL": {"url": hosted_url}
            })
            return hosted_url
        else:
            logger.warning("No hosted URL returned (Cloudinary skip or fail). Avatar URL not updated.")
            return None
            
    finally:
        for p in [temp_input, temp_output]:
            if p and os.path.exists(p):
                os.remove(p)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update character avatar with rank frame.")
    parser.add_argument("--character-id", required=True, help="Notion Page ID of the character")
    args = parser.parse_args()

    update_character_avatar(args.character_id)
