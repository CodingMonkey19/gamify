# Tasks: Dashboard, Onboarding & SOPs

**Input**: Design documents from `/specs/008-dashboard-onboarding-sops/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included — constitution mandates "No engine ships without tests" and Phase 7 established `tests.yml` CI.

**Organization**: Tasks grouped by user story. US1 (Onboarding) and US2 (Dashboard) are co-P1; US2 depends on US1's dashboard_setup module. US3 (SOPs) is P2, independent of code.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Environment configuration and shared utilities for onboarding

- [X] T001 Add new DB ID environment variables to .env.example: CHARACTER_DB_ID, GOOD_HABIT_DB_ID, BAD_HABIT_DB_ID, VISION_BOARD_DB_ID, ONBOARDING_IDENTITY_DB_ID, JOURNAL_DB_ID, BRAIN_DUMP_DB_ID, QUESTS_DB_ID, DAILY_SNAPSHOTS_DB_ID
- [X] T002 [P] Add CHARACTER_CLASSES list ("Warrior", "Mage", "Rogue", "Paladin", "Ranger") and VISION_BOARD_CATEGORIES list and DEFAULT_GOOD_HABITS / DEFAULT_BAD_HABITS dicts to tools/config.py
- [X] T003 [P] Add mock fixtures for onboarding to tests/conftest.py: mock_character_page, mock_habit_rows, mock_vision_board_rows, mock_identity_rows, mock_dashboard_page

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared input validation helpers used by both onboarding and dashboard scripts

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Implement CLI input helpers in tools/onboarding.py (top section): prompt_required(question) → re-prompts on empty, prompt_choice(question, options) → validates numeric selection, prompt_multiline(question) → collects lines until blank line. These are used by the onboarding flow and must exist before story implementation.

**Checkpoint**: Foundation ready — input helpers validated. User story implementation can begin.

---

## Phase 3: User Story 1 — Character Onboarding Flow (Priority: P1) MVP

**Goal**: Interactive CLI that creates a character with starting stats, identity rows, default habits, vision board, and auto-creates the dashboard — single command from zero to playable.

**Independent Test**: Run `python tools/onboarding.py --parent-page-id <ID>`. Follow prompts. Verify: Character row created with Level 1/HP 1000/Peasant, Identity rows created, 5 good habits + 3 bad habits created, 8 Vision Board entries created, dashboard page created. Run again — verify duplicate detection warns.

### Implementation for User Story 1

- [ ] T005 [US1] Implement setup_character() in tools/onboarding.py — collect all interactive inputs (name, class from 5 options, master objective, minor objectives, death penalty, strengths, weaknesses) using input helpers. Validate required fields. Create Character row in CHARACTER_DB_ID via Notion API with starting values from config.py (Level 1, STARTING_HP, 0 coins, 0 gold, "Peasant" rank, all XPs 0). Return character_id.
- [ ] T006 [US1] Implement setup_identity_rows(character_id, strengths, weaknesses, objectives) in tools/onboarding.py — create Onboarding Identity rows in ONBOARDING_IDENTITY_DB_ID linked to character. One row per strength/weakness/objective with Question type and Answer text.
- [ ] T007 [US1] Implement setup_default_habits(character_id) in tools/onboarding.py — create 5 good habits in GOOD_HABIT_DB_ID (Exercise/STR, Read 30min/INT, Track Expenses/WIS, Eat Clean/VIT, Social Interaction/CHA) and 3 bad habits in BAD_HABIT_DB_ID (Junk Food, Doom Scrolling, Skipping Workout), all linked to character.
- [ ] T008 [US1] Implement setup_vision_board(character_id) in tools/onboarding.py — create 8 Vision Board rows in VISION_BOARD_DB_ID with categories (Health, Career, Finance, Relationships, Learning, Creativity, Adventure, Spirituality) linked to character, empty aspiration checklists.
- [ ] T009 [US1] Implement partial state detection in tools/onboarding.py — before each step (character, identity, habits, vision board, dashboard), query the relevant DB for existing records linked to this character/parent page. Skip completed steps with log message. Detect existing character and warn with confirmation prompt (FR-007).
- [ ] T010 [US1] Implement main() CLI entry point in tools/onboarding.py — argparse with --parent-page-id, env var validation (smoke test pattern), orchestrate flow: setup_character → setup_identity_rows → setup_default_habits → setup_vision_board → dashboard_setup.create_dashboard (from T012) → print summary with character ID and dashboard URL. Dual output (stdout + logger).
- [ ] T011 [US1] Write tests/test_onboarding.py — test setup_character creates row with correct starting values, test setup_default_habits creates exactly 5 good + 3 bad habits, test setup_vision_board creates 8 categories, test partial recovery (character exists → skips character creation, resumes habits), test duplicate detection warns on existing character, test input validation rejects empty name/objective.

**Checkpoint**: Onboarding fully functional. Player can create a character with one command.

---

## Phase 4: User Story 2 — Daily Dashboard Page Setup (Priority: P1)

**Goal**: Programmatic Notion dashboard page with 7 panels (Character Card, Growth, Battle, Quest Board, Tasks, Journal, Stats) created via Notion API.

**Independent Test**: Run `python tools/dashboard_setup.py --character-id <ID> --parent-page-id <ID>`. Open resulting Notion page. Verify 7 panels present with linked database views. Run again — verify update (not duplicate).

### Implementation for User Story 2

- [ ] T012 [US2] Implement create_dashboard(character_id, parent_page_id) in tools/dashboard_setup.py — read character data (name, level, rank, HP, coins, gold, avatar URL, radar chart URL) from Character DB. Build Notion page with child blocks: callout block for Character Card (avatar image, stats text), then 6 sections each with heading_2 + linked_database block referencing the appropriate DB ID (GOOD_HABIT_DB_ID, BAD_HABIT_DB_ID, QUESTS_DB_ID, BRAIN_DUMP_DB_ID, JOURNAL_DB_ID, DAILY_SNAPSHOTS_DB_ID). Add filter instruction text blocks above each panel.
- [ ] T013 [US2] Implement Character Card block builder in tools/dashboard_setup.py — callout block with character name as title, paragraph blocks showing Level/Rank/HP/Coins/Gold, image blocks for avatar URL and radar chart URL (skip if URLs empty). Use Notion block API format.
- [ ] T014 [US2] Implement dashboard idempotency in tools/dashboard_setup.py — search pages under parent_page_id with title "Daily Dashboard". If found, delete existing child blocks and rebuild (update). If not found, create new page. Log whether created or updated.
- [ ] T015 [US2] Implement main() CLI entry point in tools/dashboard_setup.py — argparse with --character-id and --parent-page-id, env var validation, call create_dashboard, print dashboard URL. Exit codes per contract.
- [ ] T016 [US2] Write tests/test_dashboard_setup.py — test create_dashboard produces page with 7 panel sections, test Character Card includes name/level/rank/stats, test idempotency (existing page updated not duplicated), test missing character returns exit code 2, test all 6 linked DBs referenced correctly.

**Checkpoint**: Dashboard fully functional. Both US1 and US2 work together (onboarding auto-creates dashboard).

---

## Phase 5: User Story 3 — Workflow Documentation / SOPs (Priority: P2)

**Goal**: 5 complete SOP files in `workflows/` following WAT format with objective, inputs, steps, outputs, and troubleshooting.

**Independent Test**: Open each SOP. Follow one workflow end-to-end. Verify steps are accurate, tool names match `tools/`, and troubleshooting covers 3+ failure modes per SOP.

### Implementation for User Story 3

- [ ] T017 [P] [US3] Write workflows/setup-notion.md — SOP for database creation from scratch: objective (recreate full schema), prerequisites (.env configured, Notion integration created), steps (run create_databases.py, verify all 33 DBs, copy DB IDs to .env), expected output (all DBs visible in Notion), troubleshooting (API permission denied, rate limiting, missing parent page)
- [ ] T018 [P] [US3] Write workflows/onboarding.md — SOP for character creation: objective (create playable character), prerequisites (databases exist, .env has DB IDs), steps (run onboarding.py, walk through each prompt with explanations of class/objective/penalty choices, apply dashboard filters after creation), expected output (character + habits + vision board + dashboard), troubleshooting (DB not found, partial onboarding recovery, re-running onboarding)
- [ ] T019 [P] [US3] Write workflows/daily-routine.md — SOP for daily player workflow: objective (complete daily game loop), steps (open dashboard, check in good habits via buttons, log bad habits if needed, enter meals/expenses/journal/mood, automation runs at 10 PM and handles XP/streaks/snapshot), expected output (Activity Log entries, stats updated next morning), troubleshooting (check-in button not working, automation didn't run, missing snapshot)
- [ ] T020 [P] [US3] Write workflows/weekly-review.md — SOP for weekly report interpretation: objective (review weekly performance), steps (read weekly report output, understand stat deltas, review AI coaching briefing, check quest completion, review overdraft status), expected output (player understands their week's progress), troubleshooting (report missing, AI sections skipped, delta shows 0)
- [ ] T021 [P] [US3] Write workflows/asset-generation.md — SOP for regenerating visual assets: objective (regenerate radar chart or avatar), steps (run chart_renderer for radar chart, run avatar_renderer for avatar frame, verify Cloudinary URLs update, check dashboard displays new images), expected output (new images visible in Notion), troubleshooting (Cloudinary upload fails, old image cached, Pillow not installed)

**Checkpoint**: All 5 SOPs complete. System is fully documented.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation and integration verification

- [ ] T022 Run full onboarding flow end-to-end: execute onboarding.py, verify all records created, verify dashboard page displays 7 panels, apply filters, verify daily_automation.py works with new character
- [ ] T023 Verify idempotency: run onboarding.py again on same workspace, confirm duplicate detection warns, no duplicate records created
- [ ] T024 Verify partial recovery: simulate interrupted onboarding (character exists, no habits), re-run, confirm it resumes from habits step
- [ ] T025 Verify all 5 SOPs reference correct tool names by checking each mentioned script exists in tools/
- [ ] T026 Run full pytest suite and confirm all tests pass: `python -m pytest tests/ -v`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001-T003)
- **US1 Onboarding (Phase 3)**: Depends on Phase 2 (T004) — input helpers required
- **US2 Dashboard (Phase 4)**: Depends on Phase 2. T012 (dashboard_setup.py) can start in parallel with US1, but T010 (onboarding main) depends on T012 for auto-dashboard chaining.
- **US3 SOPs (Phase 5)**: Depends on US1 + US2 being implemented (SOPs reference actual tool behavior)
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: After Foundational → independent except T010 needs dashboard_setup from US2
- **US2 (P1)**: After Foundational → independent module, but onboarding calls it at end
- **US3 (P2)**: After US1 + US2 → SOPs describe working tools, so tools must exist first

### Within Each User Story

- Data creation functions before orchestration (setup_character before main)
- Idempotency logic integrated with each function
- Tests after implementation

### Parallel Opportunities

- T002 + T003: config additions and test fixtures are independent files
- T005 + T006 + T007 + T008: each setup function writes to different DBs (can develop in parallel)
- T012 can start in parallel with T005-T009 (dashboard_setup.py is a separate file)
- T017 + T018 + T019 + T020 + T021: all 5 SOPs are independent files

---

## Parallel Example: User Story 3 (SOPs)

```bash
# Launch all 5 SOP files together (all independent):
Task: "Write workflows/setup-notion.md"
Task: "Write workflows/onboarding.md"
Task: "Write workflows/daily-routine.md"
Task: "Write workflows/weekly-review.md"
Task: "Write workflows/asset-generation.md"
```

## Parallel Example: User Story 1 (Onboarding Functions)

```bash
# Launch onboarding sub-functions together (different DB targets):
Task: "Implement setup_character() in tools/onboarding.py"
Task: "Implement setup_default_habits() in tools/onboarding.py"
Task: "Implement setup_vision_board() in tools/onboarding.py"
Task: "Implement setup_identity_rows() in tools/onboarding.py"
# Note: These write to the same file but different functions — serialize if needed
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004)
3. Complete Phase 3: US1 Onboarding (T005-T011)
4. **STOP and VALIDATE**: Run `python tools/onboarding.py --parent-page-id <ID>`. Verify character created with all records.
5. Player can create a character and start using the system.

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 Onboarding → Test independently → **MVP! Character creation works**
3. US2 Dashboard → Test independently → Dashboard auto-created after onboarding
4. US3 SOPs → Review each → System fully documented
5. Polish → End-to-end validation → Production-ready

### Single Developer Strategy

Work sequentially: Phase 1 → Phase 2 → US1 (T005-T009 can interleave) → US2 → US1 T010 (wire dashboard) → US1 T011 (tests) → US3 (all 5 SOPs parallel-writable) → Polish.

Key insight: T012 (dashboard_setup.py) should be built early in US2, then T010 (onboarding main) wires the auto-dashboard call. This avoids blocking.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- All onboarding functions (T005-T008) write to the same file but are independent functions — can be developed sequentially within the file
- SOPs (T017-T021) should be written AFTER the tools they document are working, to ensure accuracy
- Dashboard filters cannot be set programmatically via Notion API — filter instructions are included as text blocks and documented in onboarding SOP
- Commit after each task or logical group
