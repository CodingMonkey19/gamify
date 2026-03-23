# SOP: Set Up Notion Databases from Scratch

**Objective**: Recreate the full Gamify Your Life schema in a fresh Notion workspace — all 33 databases with correct properties, relations, and rollups.

**Tool**: `tools/create_databases.py`

---

## Prerequisites

- [ ] Notion account with a workspace
- [ ] Notion integration created at https://www.notion.so/my-integrations
  - Scope: Read/Update/Insert content, Read user data
  - Copy the Integration Token
- [ ] Parent page created in your workspace; share it with your integration
- [ ] Python 3.10+ and dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` configured with `NOTION_TOKEN` (see `.env.example`)

---

## Steps

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set NOTION_TOKEN to your integration token
```

### 2. Find your parent page ID

Open the page in Notion, copy the URL. The page ID is the 32-character hex string:
`https://notion.so/My-Workspace-<PAGE_ID>`

### 3. Run database creation

```bash
python -m tools.create_databases --parent-page-id <PAGE_ID>
```

This creates all 33 databases and prints their IDs.

### 4. Copy DB IDs to .env

The script outputs each DB ID. Copy them into `.env`:

```
CHARACTER_DB_ID=f814ec57-...
GOOD_HABIT_DB_ID=5dc9eb37-...
BAD_HABIT_DB_ID=f2d3667c-...
VISION_BOARD_DB_ID=3000ccc4-...
ONBOARDING_IDENTITY_DB_ID=79bc2de7-...
JOURNAL_DB_ID=6f03d04f-...
BRAIN_DUMP_DB_ID=172c204a-...
QUESTS_DB_ID=1eba33ab-...
DAILY_SNAPSHOTS_DB_ID=10168a1e-...
```

### 5. Verify databases in Notion

Open your workspace and confirm all 33 databases appear under your parent page.
Check that relations between databases are linked (Character → Activity Log, Character → Quests, etc.).

### 6. Run smoke test

```bash
python -m tools.smoke_test
```

Expected output: `Smoke test passed — Notion API reachable, character DB accessible.`

---

## Expected Output

- 33 Notion databases visible in the workspace
- All DB IDs printed to terminal and ready to copy into `.env`
- Smoke test passes

---

## Troubleshooting

### API permission denied (403)
- Confirm your integration is shared with the parent page (Settings & Members → Connections)
- Verify `NOTION_TOKEN` in `.env` matches your integration token exactly (starts with `ntn_`)

### Rate limiting (429)
- The SDK retries automatically with backoff
- If it persists, wait 60 seconds and re-run — the script is idempotent

### Missing parent page (404)
- The parent page ID must be shared with your integration before running
- Confirm the ID is correct (32 hex chars, no dashes from URL or with dashes stripped)

### Database already exists
- `create_databases.py` is idempotent — re-running is safe
- Existing databases will be updated with any new properties

### Relations not linking
- Relations require both referenced databases to exist first
- Run `create_databases.py` in full; do not cancel mid-run
