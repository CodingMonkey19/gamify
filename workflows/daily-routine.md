# SOP: Daily Player Routine

**Objective**: Complete the daily game loop — check in habits, log activities, and let the automation handle XP, streaks, and snapshots.

---

## Prerequisites

- [ ] Character created (see `workflows/onboarding.md`)
- [ ] Daily automation scheduled in GitHub Actions (`daily.yml` runs at 10 PM UTC)
- [ ] Dashboard open in Notion: your Daily Dashboard page

---

## Morning — Open Dashboard

1. Open your "Daily Dashboard" page in Notion
2. Check the Character Card panel — review your Level, HP, and Coins from yesterday
3. Look at the Quest Board — identify any active quests to work toward today

---

## Throughout the Day — Log Activities

### Good Habits (Growth panel)

For each good habit you complete:
1. Open the habit row in the Growth panel
2. Click the "Check In" button property (or add a new Activity Log entry)
3. The daily automation will process check-ins at 10 PM and award XP

**Good habits and their stats:**
- Exercise → STR XP
- Read 30min → INT XP
- Track Expenses → WIS XP
- Eat Clean → VIT XP
- Social Interaction → CHA XP

### Bad Habits (Battle panel)

If you indulge a bad habit:
1. Open the bad habit row in the Battle panel
2. Log the occurrence with today's date
3. The automation applies the HP penalty (-10 HP per occurrence)

### Expenses (Expense Log DB)

Log any expenses as you make them:
1. Open Expense Log DB
2. Create new entry: Amount, Category, Date
3. Used by monthly automation to calculate surplus

### Meals / Nutrition

1. Open Nutrition Log DB
2. Log breakfast, lunch, dinner, snacks with macros
3. Automation calculates TDEE adherence and awards VIT XP

### Journal (Journal panel)

1. Open the Journal panel in your dashboard
2. Create a new entry for today
3. Write your daily reflection, mood, and highlights
4. Select your Mood from the dropdown (Anxiety, Joy, Regret, Sadness, Boredom, Surprise, Shame)

### Tasks (Brain Dump panel)

1. Add any new tasks to the Brain Dump
2. Set Difficulty (Level 1/2/3) and Priority
3. When completing a task, mark it Done — the automation awards XP + Coins

---

## Evening — Automation Runs at 10 PM UTC

The `daily.yml` GitHub Action triggers `tools/daily_automation.py` which:

1. Validates environment (smoke test)
2. Processes all habit check-ins — awards XP per stat
3. Updates streaks — applies multipliers for consecutive days
4. Applies HP changes — bad habit penalties, healing items used
5. Processes completed tasks — awards XP + Coins
6. Applies overdraft check prep (runs on Monday)
7. Calculates level-ups if XP threshold crossed
8. Takes a daily snapshot — records all stats to Daily Snapshots DB
9. Logs summary to GitHub Actions output

**You don't need to do anything** — just ensure your entries are logged before 10 PM.

---

## Expected Output (after automation)

The next morning, your dashboard shows:
- Updated STR/INT/WIS/VIT/CHA XP values
- Streak counts updated on active habits
- HP updated (any penalties applied)
- Level updated if threshold crossed
- New Daily Snapshot entry in Stats panel

---

## Troubleshooting

### Check-in button not working
- Notion buttons can be finicky — create an Activity Log entry manually instead
- Open Activity Log DB, create entry: Date = today, Habit = your habit, Type = Check-In

### Automation didn't run
- Check GitHub Actions tab → `Daily Automation` workflow
- Common causes: `NOTION_TOKEN` secret expired, `CHARACTER_ID` missing from repository secrets
- To run manually: `python -m tools.daily_automation --character-id <ID>`

### Missing snapshot (no Stats entry for today)
- Smoke test likely failed — automation stops on smoke test failure
- Check GitHub Actions logs for error messages
- Run manually: `python -m tools.snapshot_engine --character-id <ID>`

### HP depleted / character "died"
- HP reaching 0 triggers the Death Penalty you set during onboarding
- HP is restored to 500 (half max) after death penalty acknowledged
- Modify the "Current HP" field directly in Character DB if needed

### Streaks broken unexpectedly
- Streaks require a check-in every day — no check-in = streak reset
- Use the Streak Tracker DB to see current streak counts
- Broken streaks can be restored via Black Market (50 coins per missed day)
