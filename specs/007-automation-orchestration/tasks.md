# Tasks: Automation Orchestration

**Input**: Design documents from `/specs/007-automation-orchestration/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec. Test tasks included because constitution mandates "No engine ships without tests" and spec includes test workflows (tests.yml).

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Project initialization — dependencies, test infrastructure, shared utilities

- [x] T001 Create requirements.txt with notion-client, openai, python-dotenv, Pillow, matplotlib, pytest
- [x] T002 Create tests/ directory with tests/__init__.py and tests/conftest.py providing shared mock Notion fixtures (mock_notion_client, mock_character_page, mock_settings)
- [x] T003 Create .github/workflows/ directory structure

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Smoke test and snapshot engine that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement smoke_test.py in tools/smoke_test.py — validate env vars (NOTION_TOKEN, CHARACTER_ID required; OPENAI_API_KEY, NOTION_PARENT_PAGE_ID optional warnings), Notion API reachability (notion.users.me()), raise SmokeTestError on required failures
- [x] T005 Implement snapshot_engine.py in tools/snapshot_engine.py — take_snapshot(character_id, run_date) reads Character DB + Streak Tracker, writes Daily Snapshot row with all 14 fields (Date, Character, 5 stat XPs, Level, Gold, Coins, HP, Rank, Active Streaks, Mood). Idempotent: query Date+Character before insert, skip if exists
- [x] T006 [P] Write tests/test_smoke_test.py — 7 tests: required env var missing raises SmokeTestError, optional missing logs warning, API unreachable raises SmokeTestError, all-pass returns character_id, arg overrides env, env used when no arg
- [x] T007 [P] Write tests/test_snapshot_engine.py — 5 tests: snapshot creation with correct 14 fields, idempotency (existing snapshot returns None), active streak count, zero streaks, default mood Neutral

**Checkpoint**: Foundation ready — smoke test and snapshot engine validated. User story implementation can begin.

---

## Phase 3: User Story 1 — Daily Automation Pipeline (Priority: P1) MVP

**Goal**: 16-step idempotent daily pipeline that processes habits, aggregates XP, updates stats, and captures a daily snapshot.

**Independent Test**: Create Activity Log entries (good/bad habits), Set Log entries (fitness), Meal Log entries (nutrition) for today. Run `python tools/daily_automation.py --character-id <ID>`. Verify habits processed, streaks updated, XP aggregated, HP adjusted, snapshot created. Run again — verify no duplicates.

### Implementation for User Story 1

- [x] T008 [US1] Implement daily_automation.py in tools/daily_automation.py — CLI entry point with argparse (--character-id), capture run_date at start, build Pipeline Context dict, execute 16-step PIPELINE with try/except per step (fault tolerant), print final summary to stdout, log per-step results via logger.py. Uses _try_import() for graceful handling of missing engines.
- [x] T009 [US1] Implement the 16 pipeline steps in tools/daily_automation.py — ordered sequence: (1) smoke_test.run, (2) load_settings, (3-8) habit/streak/fitness/nutrition/financial/xp engines, (9-10) hp death check, (11-12) rank check + conditional avatar, (13) achievements, (14) chart, (15) snapshot, (16) quest processing
- [x] T010 [US1] Add dual output to tools/daily_automation.py — per-step logger.info/error for stderr, print() summary block for stdout
- [x] T011 [US1] Write tests/test_daily_automation.py — 16 tests: pipeline execution order, fault tolerance, smoke test failure aborts, missing engine skipped, avatar conditional on rank change, CLI entry point, summary output

**Checkpoint**: Daily automation fully functional and testable independently.

---

## Phase 4: User Story 2 — Weekly Report & AI Integration (Priority: P1)

**Goal**: Weekly report calculating 7-day stat deltas, overdraft check, AI coaching briefing, AI quest generation, and quest completion processing.

**Independent Test**: Ensure 7 days of Daily Snapshots exist. Run `python tools/weekly_report.py --character-id <ID>`. Verify stat deltas correct, overdraft checked, coaching briefing generated, 3 quests created, completed quests processed, summary logged, AI_MONTHLY_SPEND incremented.

### Implementation for User Story 2

- [x] T012 [US2] Implement weekly_report.py in tools/weekly_report.py — CLI entry point, calls daily_automation first, queries 7 days of snapshots, computes deltas, checks overdraft, runs AI coaching/quests, logs summary
- [x] T013 [US2] Implement delta calculation — queries DAILY_SNAPSHOTS_DB_ID, handles <7 snapshots gracefully (returns zeros if <2)
- [x] T014 [US2] Implement overdraft check — uses _try_import for coin_engine, applies HP penalty if overdrawn
- [x] T015 [US2] Implement AI integration — checks AI_MONTHLY_SPEND vs cap, conditionally runs coaching/quest generation, always processes completed quests
- [x] T016 [US2] Add report summary output — formatted box with deltas, streaks, quests, coaching, overdraft sections
- [x] T017 [US2] Write tests/test_weekly_report.py — 14 tests: delta calculation (7/fewer/1/0 snapshots), overdraft, AI cost cap, AI failure graceful, daily automation called first, summary formatting

**Checkpoint**: Weekly report fully functional. Both US1 and US2 work independently.

---

## Phase 5: User Story 3 — Monthly Automation (Priority: P2)

**Goal**: Monthly Gold settlement from budget surplus, Treasury row creation, and AI_MONTHLY_SPEND reset.

**Independent Test**: Create expense entries for previous month. Set AI_MONTHLY_SPEND to non-zero. Run `python tools/monthly_automation.py --character-id <ID>`. Verify Treasury row created, Gold credited, WIS XP awarded, AI_MONTHLY_SPEND reset to 0.

### Implementation for User Story 3

- [x] T018 [US3] Implement monthly_automation.py in tools/monthly_automation.py — CLI entry point, smoke test, surplus calculation from Expense Log, Gold conversion, Treasury row creation, monthly snapshot, AI spend reset
- [x] T019 [US3] Implement Treasury idempotency — queries Treasury DB for Month+Character before creating, skips if exists
- [x] T020 [US3] Add summary output — formatted box with surplus, Gold earned, WIS XP, AI spend reset
- [x] T021 [US3] Write tests/test_monthly_automation.py — 21 tests: surplus/Gold conversion, deficit handling, Treasury idempotency, AI spend reset, monthly snapshot, WIS XP, target month calc, summary formatting

**Checkpoint**: Monthly automation fully functional. All 3 automation scripts work independently.

---

## Phase 6: User Story 4 — GitHub Actions CI/CD (Priority: P2)

**Goal**: Four GitHub Actions workflow YAML files that schedule and execute all automation scripts with secrets injection.

**Independent Test**: Push workflow files. Verify tests.yml triggers on push. Manually trigger daily.yml via workflow_dispatch, verify it runs daily_automation.py with secrets.

### Implementation for User Story 4

- [x] T022 [P] [US4] Create .github/workflows/daily.yml — cron 0 20 * * *, workflow_dispatch, concurrency daily-automation, cancel-in-progress: false
- [x] T023 [P] [US4] Create .github/workflows/weekly.yml — cron 0 8 * * 0, runs daily_automation THEN weekly_report sequentially
- [x] T024 [P] [US4] Create .github/workflows/monthly.yml — cron 0 0 1 * *, runs monthly_automation
- [x] T025 [P] [US4] Create .github/workflows/tests.yml — push + PR trigger, pytest tests/ -v, cancel-in-progress: true

**Checkpoint**: All 4 workflows in place. CI/CD layer complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [~] T026 Validate all scripts work end-to-end by running quickstart.md steps locally (Blocked: requires Phase 1-4 engines for live Notion execution)
- [x] T027 Verify idempotency: tested via test_daily_automation.py (snapshot idempotency), test_monthly_automation.py (Treasury idempotency), test_snapshot_engine.py (date uniqueness)
- [x] T028 Verify fault tolerance: tested via test_daily_automation.py — one engine raises, remaining steps still execute. Multiple failures still complete.
- [x] T029 Run full pytest suite: 221/221 tests pass — `python -m pytest tests/ -v`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001-T003)
- **US1 Daily (Phase 3)**: Depends on Phase 2 (T004-T007) — smoke_test + snapshot_engine required
- **US2 Weekly (Phase 4)**: Depends on Phase 2 + US1 (weekly calls daily_automation first)
- **US3 Monthly (Phase 5)**: Depends on Phase 2 only (uses snapshot_engine + smoke_test, independent of daily/weekly)
- **US4 GitHub Actions (Phase 6)**: Depends on US1+US2+US3 being implemented (workflows call the scripts)
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: After Foundational → no dependencies on other stories
- **US2 (P1)**: After Foundational + US1 → calls daily_automation.py as first step
- **US3 (P2)**: After Foundational → independent of US1/US2
- **US4 (P2)**: After US1+US2+US3 → workflow files reference all scripts

### Within Each User Story

- Engine composition before output formatting
- Idempotency logic integrated with main flow (not separate)
- Tests after implementation (tests validate working code)

### Parallel Opportunities

- T002 + T003: conftest.py and workflow dir can be created in parallel
- T004 + T005: smoke_test and snapshot_engine are independent modules
- T006 + T007: test files for smoke_test and snapshot_engine are independent
- US3 can run in parallel with US1 (no dependency between monthly and daily)
- T022 + T023 + T024 + T025: all 4 workflow YAML files are independent

---

## Parallel Example: User Story 4 (GitHub Actions)

```bash
# Launch all workflow YAML files together (all independent):
Task: "Create .github/workflows/daily.yml"
Task: "Create .github/workflows/weekly.yml"
Task: "Create .github/workflows/monthly.yml"
Task: "Create .github/workflows/tests.yml"
```

## Parallel Example: Foundational Phase

```bash
# Launch smoke test and snapshot engine together (independent modules):
Task: "Implement smoke_test.py in tools/smoke_test.py"
Task: "Implement snapshot_engine.py in tools/snapshot_engine.py"

# Launch their tests together (independent test files):
Task: "Write tests/test_smoke_test.py"
Task: "Write tests/test_snapshot_engine.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T007) — smoke_test + snapshot_engine
3. Complete Phase 3: US1 Daily Automation (T008-T011)
4. **STOP and VALIDATE**: Run `python tools/daily_automation.py --character-id <ID>` twice. Verify processing + idempotency.
5. Daily pipeline is operational — the heartbeat of the system works.

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 Daily Automation → Test independently → **MVP! Daily pipeline runs**
3. US2 Weekly Report → Test independently → Weekly reports with AI coaching
4. US3 Monthly Automation → Test independently → Monthly Gold settlement
5. US4 GitHub Actions → Push workflows → Fully automated, hands-off operation
6. Polish → End-to-end validation → Production-ready

### Single Developer Strategy

Work sequentially: Phase 1 → Phase 2 → US1 → US2 → US3 → US4 → Polish.
Within each phase, exploit [P] parallel tasks where marked.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Engine imports will be thin wrappers initially if Phase 1-6 engines aren't built yet — daily_automation.py should handle ImportError gracefully during development
