"""Radar chart generation for character stats."""

import argparse
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, RegularPolygon
from matplotlib.path import Path
from matplotlib.projections.polar import PolarAxes
from matplotlib.projections import register_projection
from matplotlib.spines import Spine
from matplotlib.transforms import Affine2D

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from logger import get_logger
import config
import notion_client_wrapper as notion_api
import avatar_renderer  # Reuse upload_image

logger = get_logger(__name__)


def radar_factory(num_vars, frame='circle'):
    """Create a radar chart with `num_vars` axes."""
    theta = np.linspace(0, 2*np.pi, num_vars, endpoint=False)

    class RadarAxes(PolarAxes):
        name = 'radar'
        # use 1 line segment connecting each point, instead of interpolating.
        RESOLUTION = 1

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # rotate plot such that the first axis is at the top
            self.set_theta_offset(np.pi / 2)

        def fill(self, *args, closed=True, **kwargs):
            """Override fill so that line is closed by default."""
            return super().fill(*args, closed=closed, **kwargs)

        def plot(self, *args, **kwargs):
            """Override plot so that line is closed by default."""
            lines = super().plot(*args, **kwargs)
            for line in lines:
                self._close_line(line)

        def _close_line(self, line):
            x, y = line.get_data()
            # FIXME: markers at x[0], y[0] get duplicated
            if x[0] != x[-1]:
                x = np.concatenate((x, [x[0]]))
                y = np.concatenate((y, [y[0]]))
                line.set_data(x, y)

        def set_varlabels(self, labels):
            self.set_thetagrids(np.degrees(theta), labels)

        def _gen_axes_patch(self):
            # The Axes patch must be centered at (0.5, 0.5) and of radius 0.5
            # in axes coordinates.
            if frame == 'circle':
                return Circle((0.5, 0.5), 0.5)
            elif frame == 'polygon':
                return RegularPolygon((0.5, 0.5), num_vars,
                                      radius=0.5, edgecolor="k")
            else:
                raise ValueError("unknown value for 'frame': %s" % frame)

        def draw(self, renderer):
            """ Draw. Use a patch as the frame. """
            if frame == 'polygon':
                gridlines = self.yaxis.get_gridlines()
                for gl in gridlines:
                    gl.get_path()._interpolation_steps = num_vars
            super().draw(renderer)

        def _gen_axes_spines(self):
            if frame == 'circle':
                return super()._gen_axes_spines()
            elif frame == 'polygon':
                # spine_type must be 'left'/'right'/'top'/'bottom'/'circle'.
                spine = Spine(axes=self,
                              spine_type='circle',
                              path=Path.unit_regular_polygon(num_vars))
                # unit_regular_polygon gives a polygon of radius 1 centered at
                # (0,0) but we want a polygon of radius 0.5 centered at (0.5,
                # 0.5) in axes coordinates.
                spine.set_transform(Affine2D().scale(.5).translate(.5, .5)
                                    + self.transAxes)
                return {'polar': spine}
            else:
                raise ValueError("unknown value for 'frame': %s" % frame)

    register_projection(RadarAxes)
    return theta


def generate_radar_chart(stats, player_name, rank, output_path):
    """
    Generates a 5-axis radar chart (STR, INT, WIS, VIT, CHA).
    stats: dict e.g. {'STR': 10, 'INT': 12, ...}
    """
    labels = ['STR', 'INT', 'WIS', 'VIT', 'CHA']
    num_vars = len(labels)
    theta = radar_factory(num_vars, frame='polygon')
    
    # Values for the plot
    values = [stats.get(label, 0) for label in labels]
    
    # Max value for scaling - use at least 20 or max(values)+5
    max_val = max(20, max(values) + 5) if values else 20
    
    # Create the figure
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='radar'))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')
    
    # Set the range
    ax.set_ylim(0, max_val)
    
    # Plot the data
    ax.plot(theta, values, color='#00d4ff', linewidth=2)
    ax.fill(theta, values, facecolor='#00d4ff', alpha=0.25)
    
    # Labels and grid
    ax.set_varlabels([f"{label}\nLvl {stats.get(label, 0)}" for label in labels])
    
    # Style the labels
    for label, angle in zip(ax.get_xticklabels(), theta):
        label.set_color('white')
        label.set_fontweight('bold')
        label.set_fontsize(12)

    # Style the grid
    ax.grid(color='#37474F', linestyle='--', linewidth=0.5)
    
    # Remove y-axis labels
    ax.set_yticklabels([])
    
    # Spine (outer border)
    ax.spines['polar'].set_color('#37474F')
    
    # Title
    plt.title(f"{player_name} · {rank}", color='white', size=20, weight='bold', pad=30)
    
    # Adjust layout and save
    plt.tight_layout()
    plt.savefig(output_path, facecolor='#1a1a2e', dpi=100)
    plt.close()
    
    logger.info(f"Radar chart saved to {output_path}")
    return output_path


def update_character_chart(character_id, client=None, db_ids=None, cfg=None):
    """
    Main pipeline:
    1. Fetch stat levels + name + rank from Character DB.
    2. Generate radar chart.
    3. Upload to Cloudinary.
    4. Write URL back to Character DB.
    """
    if client is None:
        client = notion_api.get_client()
    if db_ids is None:
        db_ids = notion_api.get_database_ids()
    if cfg is None:
        cfg = config.get_config(client, db_ids.get("Settings"))
        
    char_page = notion_api.get_page(client, character_id)
    props = char_page.get("properties", {})
    
    player_name = ""
    name_prop = props.get("Name", {}).get("title", [])
    if name_prop:
        player_name = name_prop[0].get("plain_text", "")
        
    rank = props.get("Current Rank", {}).get("select", {}).get("name", "Peasant")
    
    stats = {
        "STR": props.get("STR Level", {}).get("number", 0),
        "INT": props.get("INT Level", {}).get("number", 0),
        "WIS": props.get("WIS Level", {}).get("number", 0),
        "VIT": props.get("VIT Level", {}).get("number", 0),
        "CHA": props.get("CHA Level", {}).get("number", 0),
    }
    
    # Ensure all are numbers (Notion might return None)
    stats = {k: (v if v is not None else 0) for k, v in stats.items()}
    
    assets_dir = os.path.join(os.path.dirname(_tools_dir), "assets", "charts")
    os.makedirs(assets_dir, exist_ok=True)
    
    output_path = os.path.join(assets_dir, f"{character_id}.png")
    
    generate_radar_chart(stats, player_name, rank, output_path)
    
    hosted_url = avatar_renderer.upload_image(output_path, cfg)
    
    if hosted_url:
        logger.info(f"Writing new Radar Chart URL for {character_id}: {hosted_url}")
        notion_api.update_page(client, character_id, {
            "Radar Chart URL": {"url": hosted_url}
        })
        return hosted_url
    else:
        logger.warning("No hosted URL returned (Cloudinary skip or fail). Radar Chart URL not updated.")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update character radar chart.")
    parser.add_argument("--character-id", required=True, help="Notion Page ID of the character")
    args = parser.parse_args()

    update_character_chart(args.character_id)
