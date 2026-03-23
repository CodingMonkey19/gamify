# SOP: Regenerate Visual Assets (Radar Chart & Avatar)

**Objective**: Regenerate your character's radar chart and/or avatar frame, upload to Cloudinary, and update the Character DB with new URLs so the dashboard displays the new images.

**Tools**: `tools/chart_renderer.py`, `tools/avatar_renderer.py`

---

## Prerequisites

- [ ] Cloudinary account with `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` set in `.env`
- [ ] Character ID set as `CHARACTER_ID` in `.env`
- [ ] Pillow installed: `pip install pillow`
- [ ] Cloudinary SDK installed: `pip install cloudinary`

---

## Asset Types

| Asset | Script | Description |
|-------|--------|-------------|
| Radar Chart | `chart_renderer.py` | Spider chart showing STR/INT/WIS/VIT/CHA balance |
| Avatar Frame | `avatar_renderer.py` | Character portrait with rank frame overlay |

---

## Steps: Regenerate Radar Chart

### 1. Run chart renderer

```bash
python -m tools.chart_renderer --character-id <ID>
```

This:
1. Reads your current STR/INT/WIS/VIT/CHA XP values from Character DB
2. Renders a radar chart using matplotlib
3. Uploads to Cloudinary
4. Updates `Radar Chart URL` in Character DB

### 2. Verify in Notion

Open your Character DB row. The `Radar Chart URL` field should contain a new Cloudinary URL.

### 3. Dashboard refresh

Open your Daily Dashboard. The radar chart image in the Character Card should reflect the new values.
If the old image is cached, force-refresh the Notion page (Ctrl+Shift+R / Cmd+Shift+R).

---

## Steps: Regenerate Avatar Frame

### 1. (Optional) Upload your photo

Place your character photo at `assets/character_photo.jpg` or set `AVATAR_SOURCE_URL` in `.env`.

### 2. Run avatar renderer

```bash
python -m tools.avatar_renderer --character-id <ID>
```

This:
1. Reads your current rank from Character DB
2. Overlays the rank-appropriate frame onto your photo
3. Uploads to Cloudinary
4. Updates `Avatar URL` in Character DB

### 3. Verify in dashboard

Open Daily Dashboard → Character Card should show the new avatar image.

---

## Automated Regeneration (Daily Automation)

The daily automation calls chart_renderer and avatar_renderer automatically if:
- The character has leveled up since the last render
- The rank has changed

You can force a regeneration by running the scripts manually at any time.

---

## Expected Output

**chart_renderer:**
```
Radar chart uploaded: https://res.cloudinary.com/diplqar4q/image/upload/radar_32bdcd9e.png
Character DB updated: Radar Chart URL → https://res.cloudinary.com/...
```

**avatar_renderer:**
```
Avatar uploaded: https://res.cloudinary.com/diplqar4q/image/upload/avatar_32bdcd9e.png
Character DB updated: Avatar URL → https://res.cloudinary.com/...
```

---

## Troubleshooting

### Cloudinary upload fails (401)

- Verify `CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET` in `.env`
- Test connection: `python -c "import cloudinary; cloudinary.config(cloud_name='...', api_key='...', api_secret='...')"`
- Check Cloudinary dashboard for usage limits (free tier: 25 GB)

### Old image cached in Notion

- Notion caches external images aggressively
- Force refresh: open the image block → click `...` → `Replace` → paste the new Cloudinary URL
- Or force a Cloudinary URL change by adding a cache-bust param: `?v=2`

### Pillow not installed

```bash
pip install pillow
```

Check your virtual environment is activated: `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\activate` (Windows).

### Matplotlib not installed (for radar chart)

```bash
pip install matplotlib
```

### Avatar frame doesn't match rank

- Avatar renderer selects frame based on `Current Rank` in Character DB
- If rank was recently changed, re-run avatar_renderer to pick up the new frame
- Frame assets are in `assets/` — filenames match rank names (e.g., `Knight.png`)

### Radar chart shows all zeros

- Verify XP values in your Character DB row are non-zero
- The chart reads live from Notion — if XP fields are 0, the chart will show 0
- Check that daily automation has been running to accumulate XP
