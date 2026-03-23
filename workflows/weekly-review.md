# SOP: Weekly Review

**Objective**: Read and interpret your weekly report — understand stat deltas, AI coaching briefing, quest completion, and overdraft status.

**Tool**: `tools/weekly_report.py` (runs automatically via `weekly.yml` every Sunday)

---

## Prerequisites

- [ ] At least 2 daily snapshots in the Daily Snapshots DB (needed to compute deltas)
- [ ] Weekly automation scheduled in GitHub Actions (`weekly.yml` runs Sunday 11 PM UTC)
- [ ] OpenAI API key set (for AI coaching; optional — system works without it)

---

## When the Report Runs

The `weekly.yml` GitHub Action triggers every Sunday at 11 PM UTC:
1. Runs daily automation first (ensures Sunday snapshot exists)
2. Computes 7-day stat deltas from Daily Snapshots DB
3. Checks overdraft (applies penalty if coins < 0)
4. Generates AI coaching briefing and new quests (if budget allows)
5. Processes completed quests (awards XP + Gold)
6. Counts active vs broken streaks
7. Prints summary

---

## Reading the Report

Example output:
```
═══ Weekly Report ═══
Period: 2026-03-16 to 2026-03-23
── Stat Deltas ──
  STR XP: +45  INT XP: +30  WIS XP: +15  VIT XP: +60  CHA XP: +10
  HP: +0  Gold: +0  Coins: +85
── Streaks ──
  Active: 4  Broken: 1
── Quests ──
  Completed: 2  Generated: 3
── AI Coaching ──
  Persona: Drill Sergeant
  Cost: $0.02
── Overdraft ──
  Status: clear
═════════════════════
```

### Interpreting Stat Deltas

| Delta | Meaning |
|-------|---------|
| +45 STR XP | You exercised 9 times this week (5 XP each) |
| +0 for a stat | That habit was not tracked this week |
| Negative delta | Bug — check if XP was accidentally reduced in Notion |

**Goal**: See positive deltas in all 5 stats each week.

### Streaks

- **Active**: Habits with consecutive check-ins still running
- **Broken**: Habits where the streak reset this week

If you have more broken than active, prioritize consistency over intensity.

### Quests

- **Completed**: Quests you marked Done that were processed for XP + Gold rewards
- **Generated**: New AI-generated quests added to your Quest Board this week

Open the Quest Board panel in your dashboard to review and activate new quests.

### AI Coaching

The coaching briefing is saved to the AI Coaching DB in Notion. Each briefing includes:
- A coaching persona (Drill Sergeant, Sage, Cheerleader, etc.)
- Personalized weekly advice based on your stat performance
- Quest suggestions aligned with your weakest stats

**Cost**: Each coaching call costs ~$0.01–$0.05. Monthly cap is $1.00.
If `AI Monthly Spend >= $1.00`, coaching is skipped with a warning.

### Overdraft Status

| Status | Meaning |
|--------|---------|
| `clear` | Coins ≥ 0 — no penalty |
| `OVERDRAFT — penalty applied` | Coins < 0 — -100 HP penalty applied |
| `not checked` | coin_engine not available — check manually |

---

## Manual Run

To run the weekly report manually at any time:

```bash
python -m tools.weekly_report --character-id <ID>
```

---

## Troubleshooting

### Report shows all deltas as 0

**Cause**: Fewer than 2 snapshots found in the 7-day window.

**Fix**: Verify the daily automation is running. Check Daily Snapshots DB for recent entries.
If snapshots are missing, run: `python -m tools.snapshot_engine --character-id <ID>`

### AI sections skipped

**Cause**: `AI_MONTHLY_SPEND` in Settings DB has reached `OPENAI_MONTHLY_COST_CAP_USD` ($1.00).

**Fix**: Wait until next month (reset happens automatically via monthly_automation.py).
Or temporarily increase the cap in Settings DB → `OPENAI_MONTHLY_COST_CAP_USD`.

### Delta shows negative values

**Cause**: XP was manually reduced in Notion, or a snapshot captured incorrect data.

**Fix**: Review the Daily Snapshots DB — find the snapshot with wrong values and delete it.
Re-run the snapshot: `python -m tools.snapshot_engine --character-id <ID>`

### Quest processing shows 0 completed

**Cause**: No quests were marked "Done" this week, or quest_engine failed.

**Fix**: Manually mark quests Done in the Quest Board.
Check GitHub Actions logs for quest_engine error messages.

### Overdraft penalty applied unexpectedly

**Cause**: Coins dropped below 0 during the week (likely from loot box purchases or spending).

**Fix**: Review Coin Transaction Log to identify the cause.
To restore HP: update `Current HP` directly in Character DB.
Prevent future overdrafts: avoid spending more coins than earned.
