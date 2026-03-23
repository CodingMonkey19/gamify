"""
Chart Renderer — Generates 5-axis radar chart from character stat levels.
Dark RPG theme, uploads to Cloudinary, updates Character DB Radar Chart URL.

The chart is DYNAMIC — regenerated every time this runs, reflecting current stats.

Usage:
    python -m tools.chart_renderer --character-id <ID>
"""
import argparse
import os
import math

import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from .config import get_config
from .logger import get_logger

logger = get_logger(__name__)

CHARTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "charts")
STAT_AXES = ["STR", "INT", "WIS", "VIT", "CHA"]

# Theme colors
BG_COLOR = "#1a1a2e"
POLYGON_COLOR = "#00d4ff"
POLYGON_ALPHA = 0.25
GRID_COLOR = "#2a2a4a"
LABEL_COLOR = "#ffffff"
TITLE_COLOR = "#ffffff"
AXIS_COLOR = "#3a3a5a"


def generate_radar_chart(stats: dict, player_name: str, rank: str, output_path: str) -> str:
    """Generate 5-axis radar chart (STR, INT, WIS, VIT, CHA).
    Dark background (#1a1a2e), neon accent polygon (#00d4ff), labeled axes,
    level values at vertices, player name + rank as title.
    Output: 800x800 PNG at output_path.
    Handles all-zero stats (collapsed center polygon).
    Returns: output_path.
    """
    # Extract stat values in axis order
    values = [stats.get(axis, 0) or 0 for axis in STAT_AXES]

    # Determine max scale (at least 1 to avoid division by zero)
    max_val = max(max(values), 1)
    # Round up to nearest multiple of 5 for clean grid lines
    max_scale = max(math.ceil(max_val / 5) * 5, 5)

    # Normalize values to 0-1 range for plotting
    normalized = [v / max_scale for v in values]

    # Create angles for 5 axes
    num_axes = len(STAT_AXES)
    angles = [n / float(num_axes) * 2 * math.pi for n in range(num_axes)]
    # Close the polygon
    normalized += normalized[:1]
    angles += angles[:1]

    # Create figure
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    # Draw grid circles
    grid_levels = 5
    for i in range(1, grid_levels + 1):
        circle_val = i / grid_levels
        ax.plot(
            np.linspace(0, 2 * np.pi, 100),
            [circle_val] * 100,
            color=GRID_COLOR,
            linewidth=0.5,
            alpha=0.6,
        )

    # Draw axis lines
    for angle in angles[:-1]:
        ax.plot(
            [angle, angle],
            [0, 1],
            color=AXIS_COLOR,
            linewidth=0.8,
            alpha=0.6,
        )

    # Plot the stat polygon
    ax.fill(angles, normalized, color=POLYGON_COLOR, alpha=POLYGON_ALPHA)
    ax.plot(angles, normalized, color=POLYGON_COLOR, linewidth=2.5, alpha=0.9)

    # Plot vertex dots
    ax.scatter(
        angles[:-1],
        normalized[:-1],
        color=POLYGON_COLOR,
        s=60,
        zorder=5,
        edgecolors="#ffffff",
        linewidths=1,
    )

    # Set axis labels with stat name + value
    labels = [f"{axis}\n{values[i]}" for i, axis in enumerate(STAT_AXES)]
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color=LABEL_COLOR, fontsize=14, fontweight="bold")

    # Style the axis
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    # Add grid level labels on the first axis
    for i in range(1, grid_levels + 1):
        level_val = int(max_scale * i / grid_levels)
        ax.text(
            angles[0],
            i / grid_levels,
            str(level_val),
            color=LABEL_COLOR,
            fontsize=8,
            alpha=0.5,
            ha="left",
            va="bottom",
        )

    # Title
    title = f"{player_name}  ·  {rank}"
    ax.set_title(
        title,
        color=TITLE_COLOR,
        fontsize=18,
        fontweight="bold",
        pad=30,
    )

    # Save as 800x800 PNG
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(
        output_path,
        dpi=100,
        facecolor=BG_COLOR,
        edgecolor="none",
    )
    plt.close(fig)

    # Ensure exact 800x800 dimensions
    from PIL import Image as _PILImage
    img = _PILImage.open(output_path)
    if img.size != (800, 800):
        img = img.resize((800, 800), _PILImage.LANCZOS)
        img.save(output_path, "PNG")

    logger.info(f"Radar chart saved: {output_path}")
    return output_path


def upload_chart(image_path: str) -> str:
    """Upload chart image to Cloudinary, return hosted URL.
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
        folder="gamify/charts",
        overwrite=True,
        resource_type="image",
    )

    url = result.get("secure_url")
    if not url:
        raise RuntimeError(f"Cloudinary upload returned no URL: {result}")

    logger.info(f"Chart uploaded to Cloudinary: {url}")
    return url


def update_character_chart(character_id: str) -> dict:
    """Full pipeline: read stat levels from Character DB, generate radar chart,
    upload to Cloudinary, write Radar Chart URL to Character DB.
    Returns: {"character_id": str, "stats": dict, "chart_url": str}
    Returns None if upload fails (logged as warning, retried next run).
    """
    from .notion_client import get_notion_client, get_character, update_character

    notion = get_notion_client()
    character = get_character(notion, character_id)

    # Read stat levels
    stats = {}
    for axis in STAT_AXES:
        stats[axis] = character.get(f"{axis} Level", 0) or 0

    player_name = character.get("Name", "Hero") or "Hero"
    rank = character.get("Current Rank", "Peasant") or "Peasant"

    # Generate chart
    os.makedirs(CHARTS_DIR, exist_ok=True)
    output_path = os.path.join(CHARTS_DIR, f"{character_id}.png")
    generate_radar_chart(stats, player_name, rank, output_path)

    # Upload
    try:
        chart_url = upload_chart(output_path)
    except Exception as e:
        logger.warning(f"Chart upload failed: {e}")
        return None

    # Write URL to Character DB
    update_character(notion, character_id, {"Radar Chart URL": {"url": chart_url}})
    logger.info(f"Character {character_id} radar chart updated: {chart_url}")

    return {
        "character_id": character_id,
        "stats": stats,
        "chart_url": chart_url,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate and upload stat radar chart")
    parser.add_argument("--character-id", required=True, help="Notion Character page ID")
    args = parser.parse_args()

    result = update_character_chart(args.character_id)
    if result:
        print(f"Chart updated: {result['chart_url']}")
        print(f"Stats: {result['stats']}")
    else:
        print("Chart update failed — check logs")


if __name__ == "__main__":
    main()
