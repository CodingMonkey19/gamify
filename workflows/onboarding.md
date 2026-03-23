# SOP: Character Creation (Onboarding)

**Objective**: Create a fully playable character — with starting stats, identity profile, default habits, vision board, and dashboard — in a single command.

**Tool**: `tools/onboarding.py`

---

## Prerequisites

- [ ] Notion databases set up (see `workflows/setup-notion.md`)
- [ ] All DB IDs in `.env` (see `.env.example`)
- [ ] `NOTION_TOKEN` set in `.env`
- [ ] Parent page ID where character and dashboard will live

---

## Steps

### 1. Confirm environment

```bash
python -m tools.smoke_test
```

Expected: `Smoke test passed`

### 2. Run onboarding

```bash
python -m tools.onboarding --parent-page-id <PARENT_PAGE_ID>
```

### 3. Answer the prompts

The CLI will walk you through 7 prompts in order:

| Prompt | What to enter | Notes |
|--------|--------------|-------|
| Character Name | Your hero name | Required — cannot be empty |
| Class | Choose 1–5 | Warrior (STR), Mage (INT), Rogue (CHA), Paladin (VIT), Ranger (WIS). Your class gives a 10% XP bonus to its primary stat. |
| Master Objective | Your ultimate life goal | Required. Be specific: "Build a profitable business by 2027" works better than "Succeed". |
| Minor Objectives | Supporting goals | Optional. One per line. Press Enter on blank line to finish. |
| Death Penalty | Consequence if HP = 0 | Required. Make it meaningful: "No gaming for 2 weeks", "Donate $50 to charity". |
| Strengths | Your real strengths | At least 1 required. Be honest — these inform the AI coaching briefings. |
| Weaknesses | Your real weaknesses | At least 1 required. Honesty here drives the coaching quality. |

### 4. Wait for record creation

The script creates records in order:
1. Character row (takes ~2 seconds)
2. Identity rows (strengths + weaknesses + minor objectives)
3. 5 default good habits + 3 bad habits
4. 8 Vision Board category entries
5. Daily Dashboard page

Total time: ~15–30 seconds.

### 5. Note your Character ID and Dashboard URL

The summary output shows:
```
Character ID: 32bdcd9e-48f8-8153-bfd7-ea00f3c79635
Dashboard:    https://notion.so/your-dashboard-id
```

Add `CHARACTER_ID` to your `.env`:
```
CHARACTER_ID=32bdcd9e-48f8-8153-bfd7-ea00f3c79635
```

### 6. Apply dashboard filters

Open your Daily Dashboard in Notion. For each linked database panel, apply these filters manually (the API cannot set filters):

| Panel | Filter |
|-------|--------|
| Growth (Good Habits) | Character = [your character name] |
| Battle (Bad Habits) | Character = [your character name] |
| Quest Board | Character = [your name], Status = Active |
| Tasks | Assignee = [your name] or Status ≠ Done |
| Journal | Character = [your name] |
| Stats | Character = [your name] |

### 7. Verify records in Notion

- Character DB: 1 row with Level 1, HP 1000, Peasant
- Good Habit DB: 5 rows (Exercise, Read 30min, Track Expenses, Eat Clean, Social Interaction)
- Bad Habit DB: 3 rows (Junk Food, Doom Scrolling, Skipping Workout)
- Vision Board DB: 8 rows (Health, Career, Finance, Relationships, Learning, Creativity, Adventure, Spirituality)
- Dashboard page: "Daily Dashboard" with 7 panels

---

## Expected Output

```
========================================
 Character Created
========================================
Name:          Hero
Class:         Warrior
Character ID:  32bdcd9e-48f8-8153-bfd7-ea00f3c79635
Dashboard:     https://notion.so/dashboard-id

Records created:
  ✓ Character row (Level 1, HP 1000, Peasant)
  ✓ Identity rows (5 entries)
  ✓ Good habits (5)
  ✓ Bad habits (3)
  ✓ Vision Board (8 categories)
  ✓ Dashboard (7 panels)
========================================
```

---

## Troubleshooting

### "A character already exists" warning
- The system detected an existing character in the Character DB
- Type `yes` to create another character (multi-character testing) or `no` to cancel
- To resume partial onboarding on the SAME character, skip this step and re-run individual setup functions

### Database not found (404)
- A DB ID in `.env` is wrong or the DB was deleted
- Check `.env` against actual DB IDs in your Notion workspace
- Re-run `create_databases.py` to recreate missing DBs

### Partial onboarding (interrupted mid-run)
- Determine which step failed from the terminal output
- The character exists — re-run individual functions manually:
  ```bash
  # If habits are missing, run manually:
  python -c "from tools.onboarding import setup_default_habits, _get_notion_client; n=_get_notion_client(); setup_default_habits(n, '<CHARACTER_ID>')"
  ```
- Or re-run the full onboarding — it will warn about the existing character and let you proceed

### Dashboard creation fails
- Run `dashboard_setup.py` manually after onboarding:
  ```bash
  python -m tools.dashboard_setup --character-id <ID> --parent-page-id <ID>
  ```

### Re-running onboarding on an existing workspace
- Safe to re-run — existing character will trigger a warning
- Confirm `yes` only if you want to create an additional character
- To update habits or vision board, modify records directly in Notion
