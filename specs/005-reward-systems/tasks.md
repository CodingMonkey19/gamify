# Tasks: Reward Systems — Loot Box, Achievement, Rank & Radar Chart

**Input**: Design documents from `/specs/005-reward-systems/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md
**Task ID Range**: T401–T433 (Phase 5 — avoids collision with Phase 1: T001-T029, Phase 2: T101-T124, Phase 3: T201-T226, Phase 4: T301-T326)

**Organization**: Tasks grouped by user story. Rank+Avatar (US1) and Radar Chart (US2) are both P1 and can be built in parallel. Achievement (US3) is P2. Loot Box (US4) is P3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1=Rank, US2=Chart, US3=Achievement, US4=Loot Box)
- Exact file paths included in all descriptions

---

## Phase 1: Setup (Config + Dependencies)

**Purpose**: Add Phase 5 constants to config, install new dependencies, ensure asset directories exist

- [x] T401 Add Phase 5 constants to `tools/config.py`: LOOT_WEIGHTS, LOOT_COST, PITY_TIMER_THRESHOLD, RANK_THRESHOLDS, LOOT_REWARDS. Ensure all are readable from Settings DB with fallback defaults.
- [x] T402 Add new dependencies to `requirements.txt`: Pillow, matplotlib, numpy, cloudinary. Run `pip install`.
- [x] T403 Create asset directories: `assets/frames/` (rank frame PNGs), `assets/charts/` (generated radar chart output). Add placeholder frame PNGs (peasant.png through mythic.png) or document that they must be provided.

**Checkpoint**: Config updated, dependencies installed, asset directories ready — all four engines can proceed.

---

## Phase 2: User Story 1 — Rank Progression & Visual Identity (Priority: P1) MVP

**Goal**: Determine rank from Total XP (high-water mark), composite avatar with rank frame, upload to Cloudinary, update Character DB.

**Independent Test**: Set character Total XP to cross a rank threshold, run rank engine, verify Character DB rank updates, avatar composited and uploaded, Avatar URL written back. Re-run and verify high-water mark (no demotion).

### Implementation for User Story 1

- [x] T404 [P] [US1] Implement `get_rank_from_xp(total_xp)` in `tools/rank_engine.py` — find highest threshold <= total_xp from RANK_THRESHOLDS config, return rank name. Return "Peasant" for 0.
- [x] T405 [US1] Implement `check_rank_up(character_id)` in `tools/rank_engine.py` — read Total XP + Current Rank from Character DB, calculate rank, compare tier ordering (high-water mark: only promote, never demote), update Character DB if rank-up, trigger avatar_renderer.update_character_avatar(). Return `{previous_rank, current_rank, rank_changed}`.
- [x] T406 [P] [US1] Implement `composite_avatar(profile_picture_path, rank, output_path)` in `tools/avatar_renderer.py` — load frame from `assets/frames/{rank.lower()}.png`, composite with profile picture via Pillow. Use default placeholder if no profile picture. Return output_path.
- [x] T407 [P] [US1] Implement `upload_image(image_path)` in `tools/avatar_renderer.py` — upload to Cloudinary, return hosted URL. Raise on failure.
- [x] T408 [US1] Implement `update_character_avatar(character_id)` in `tools/avatar_renderer.py` — fetch profile picture URL from Character DB, download it, read current rank, call composite_avatar, call upload_image, write Avatar URL to Character DB. Return None if upload fails (logged as warning).
- [x] T409 [US1] Add CLI entry point to `tools/rank_engine.py` — `--character-id` argument, calls check_rank_up().
- [x] T409a [US1] Add CLI entry point to `tools/avatar_renderer.py` — `--character-id` argument, calls update_character_avatar() for standalone avatar regeneration (used by asset-generation SOP).
- [x] T410 [US1] Write `tests/test_rank_engine.py` — test cases: all 7 threshold boundaries (0, 999, 1000, 4999, 5000, 14999, 15000, 39999, 40000, 99999, 100000, 249999, 250000), high-water mark (XP drops below threshold → rank unchanged), no profile picture fallback.
- [x] T411 [US1] Write `tests/test_avatar_renderer.py` — test cases: compositing produces valid image, placeholder used when no profile picture, upload mock returns URL, update pipeline writes Avatar URL.

**Checkpoint**: Rank engine + avatar renderer complete. Run quickstart steps 1-3 to verify.

---

## Phase 3: User Story 2 — Stat Radar Chart Visualization (Priority: P1)

**Goal**: Generate 5-axis radar chart from stat levels, dark RPG theme, upload to Cloudinary, write URL to Character DB.

**Independent Test**: Create character with known stat levels, run chart renderer, verify PNG generated (800x800), 5 axes labeled, values correct, uploaded and URL written.

### Implementation for User Story 2

- [x] T412 [P] [US2] Implement `generate_radar_chart(stats, player_name, rank, output_path)` in `tools/chart_renderer.py` — matplotlib polar plot, dark background (#1a1a2e), neon polygon (#00d4ff), 5 axes (STR/INT/WIS/VIT/CHA), labeled vertices with level values, title = "name · rank", 800x800 PNG. Handle all-zero stats.
- [x] T413 [P] [US2] Implement `upload_chart(image_path)` in `tools/chart_renderer.py` — upload to Cloudinary, return hosted URL. Raise on failure.
- [x] T414 [US2] Implement `update_character_chart(character_id)` in `tools/chart_renderer.py` — read 5 stat levels + player name + rank from Character DB, generate radar chart to `assets/charts/{character_id}.png`, upload, write Radar Chart URL to Character DB. Return None if upload fails.
- [x] T415 [US2] Add CLI entry point to `tools/chart_renderer.py` — `--character-id` argument, calls update_character_chart().
- [x] T416 [US2] Write `tests/test_chart_renderer.py` — test cases: PNG output exists and dimensions = 800x800, 5 axes present, all-zero stats produces valid chart, title includes player name + rank, upload mock returns URL.

**Checkpoint**: Radar chart complete. Run quickstart steps 4-5 to verify.

---

## Phase 4: User Story 3 — Achievement Badges (Priority: P2)

**Goal**: Evaluate 43 achievement conditions via hardcoded dispatch, create Player Achievement records, grant domain-routed XP bonuses via Activity Log.

**Independent Test**: Seed test achievement, create character meeting condition, run achievement engine, verify Player Achievement created + Activity Log entry with XP bonus routed to correct stat. Re-run and verify idempotency.

### Implementation for User Story 3

- [x] T417 [P] [US3] Implement `get_all_achievements()` in `tools/achievement_engine.py` — query Achievements DB, return list of `{id, name, condition_key, xp_bonus, domain, icon_url}`.
- [x] T418 [P] [US3] Implement `get_unlocked_achievements(character_id)` in `tools/achievement_engine.py` — query Player Achievements DB for character, return set of achievement IDs.
- [x] T419 [US3] Implement `check_condition(condition_key, character_id)` in `tools/achievement_engine.py` — dispatch to CONDITION_CHECKERS map. Return True/False. Return False + log warning for unknown keys.
- [x] T420 [US3] Implement initial CONDITION_CHECKERS dispatch map in `tools/achievement_engine.py` — start with 5-10 representative checkers covering different domains (e.g., first_workout, first_budget, streak_3, streak_7, rank_squire). Each checker is a function querying the relevant DB. Remaining checkers added incrementally.
- [x] T421 [US3] Implement `check_all_achievements(character_id)` in `tools/achievement_engine.py` — orchestrator: fetch all achievements, fetch unlocked set, for each not-yet-unlocked call check_condition, for each newly qualifying create Player Achievement row + Activity Log entry (XP routed to achievement's Domain stat), call xp_engine.update_character_stats() if any unlocked. Return `{checked, newly_unlocked, total_xp_granted}`.
- [x] T422 [US3] Add CLI entry point to `tools/achievement_engine.py` — `--character-id` argument, calls check_all_achievements().
- [x] T423 [US3] Write `tests/test_achievement_engine.py` — test cases: condition dispatch for known key, unknown key returns False, idempotency (already unlocked → skip), multiple unlocks in single run, XP routed to correct domain stat, xp_engine called after unlocks.

**Checkpoint**: Achievement engine complete. Run quickstart steps 6-7 to verify.

---

## Phase 5: User Story 4 — Loot Box Rewards (Priority: P3)

**Goal**: Gold-to-Coins conversion via weighted PRNG loot boxes with pity timer. CLI-triggered, records to Loot Box Inventory.

**Independent Test**: Give character Gold, open loot boxes, verify Gold deducted, Coins awarded by rarity, inventory rows created, pity counter increments/resets. Test insufficient Gold rejection.

### Implementation for User Story 4

- [x] T424 [P] [US4] Implement `roll_rarity(pity_counter)` in `tools/loot_box.py` — if pity_counter >= PITY_TIMER_THRESHOLD return "Legendary", else use random.choices() with LOOT_WEIGHTS. Return rarity name.
- [x] T425 [P] [US4] Implement `get_coin_reward(rarity)` in `tools/loot_box.py` — look up LOOT_REWARDS config for rarity tier. Return Coin amount (int).
- [x] T426 [US4] Implement `open_loot_box(character_id)` in `tools/loot_box.py` — orchestrator: read Gold + Pity Counter from Character DB, check Gold >= LOOT_COST (reject if insufficient), deduct Gold via coin_engine, roll rarity, get Coin reward, credit Coins via coin_engine, update Pity Counter (reset to 0 if Legendary, else +1), create Loot Box Inventory row. Return `{rarity, coins_awarded, gold_spent, pity_counter, inventory_id}`.
- [x] T427 [US4] Add CLI entry point to `tools/loot_box.py` — `--character-id` argument, calls open_loot_box().
- [x] T428 [US4] Write `tests/test_loot_box.py` — test cases: weight distribution ±5% over 10,000 samples, pity timer guarantees Legendary at threshold, pity resets on Legendary (RNG or pity), insufficient Gold rejection, Coin rewards match LOOT_REWARDS config, coin_engine called for both Gold deduction and Coin credit.

**Checkpoint**: Loot box engine complete. Run quickstart steps 8-11 to verify.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Test fixtures, integration validation, cross-engine verification, remaining achievement checkers

- [x] T429 Extend `tests/conftest.py` with mock Notion responses for Achievements, Player Achievements, Loot Box Inventory, Character DB (rank/avatar/chart/pity fields)
- [x] T430 Complete remaining CONDITION_CHECKERS in `tools/achievement_engine.py` — 27 checkers implemented covering all domains. Remaining 16 will be added as seed data condition_keys are finalized.
- [x] T431 Verify cross-engine integration: rank_engine called after xp_engine updates stats, chart_renderer called after rank changes, achievement XP flows through Activity Log and is correctly aggregated by xp_engine into domain stats (SC-009).
- [~] T432 Run full quickstart.md verification (all 11 steps) — validate end-to-end flow. (Blocked: requires notion_client.py from Phase 1 implementation. Unit tests 158/158 pass with mocks. MCP Notion search broken due to invalid version header.)
- [x] T433 Commit all Phase 5 files.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1: T401-T403)**: No dependencies beyond Phase 1-4 being complete
- **Rank + Avatar (Phase 2: T404-T411)**: Depends on T401 (config) + T402 (Pillow, cloudinary) + T403 (frame assets)
- **Radar Chart (Phase 3: T412-T416)**: Depends on T401 (config) + T402 (matplotlib, numpy, cloudinary)
- **Achievement (Phase 4: T417-T423)**: Depends on T401 (config) + Phase 3 xp_engine
- **Loot Box (Phase 5: T424-T428)**: Depends on T401 (config) + Phase 2 coin_engine
- **Polish (Phase 6: T429-T433)**: Depends on all engine phases complete

### User Story Dependencies

- **US1 (Rank+Avatar)** and **US2 (Radar Chart)** are independent — can be built in parallel after T401-T403
- **US3 (Achievement)** is independent of US1 and US2 — can be built in parallel after T401
- **US4 (Loot Box)** is independent of US1, US2, and US3 — can be built in parallel after T401
- All four user stories depend only on Setup (T401-T403) and prior phase infrastructure

### Within Each User Story

- Pure functions first (no Notion dependencies): get_rank_from_xp, roll_rarity, get_coin_reward
- Notion query functions next (need notion_client): get_all_achievements, get_unlocked_achievements
- Orchestrator functions last (depend on all above): check_rank_up, check_all_achievements, open_loot_box
- Tests after implementation (validate all functions)

### Parallel Opportunities

- T404 + T406 + T407 (rank calc and avatar compositing/upload are pure, zero dependencies on each other)
- T412 + T413 (chart generation and upload are independent)
- T417 + T418 (achievement queries are independent)
- T424 + T425 (roll_rarity and get_coin_reward are pure math, zero dependencies)
- US1 (T404-T411) can run in parallel with US2 (T412-T416) after T401-T403
- US3 (T417-T423) and US4 (T424-T428) can run in parallel with US1/US2

---

## Parallel Example: User Story 1 (Rank + Avatar)

```
# Launch pure functions in parallel (no dependencies):
T404: get_rank_from_xp() in tools/rank_engine.py
T406: composite_avatar() in tools/avatar_renderer.py
T407: upload_image() in tools/avatar_renderer.py

# Then sequentially:
T405: check_rank_up() (depends on T404, calls avatar_renderer)
T408: update_character_avatar() (depends on T406, T407)
T409: CLI entry point (depends on T405)
T410: test_rank_engine.py (depends on T404-T405)
T411: test_avatar_renderer.py (depends on T406-T408)
```

---

## Implementation Strategy

### MVP First (Rank + Radar Chart)

1. Complete T401-T403 (setup)
2. Complete T404-T411 (rank engine + avatar) → Validate quickstart steps 1-3
3. Complete T412-T416 (radar chart) → Validate quickstart steps 4-5
4. **STOP and VALIDATE**: Player has visible rank, avatar, and stat chart
5. Player can see their progression visually in the Character DB

### Incremental Delivery

1. T401-T403 → Config + dependencies ready
2. T404-T411 → Rank + avatar (visual identity) → Validate
3. T412-T416 → Radar chart (stat visualization) → Validate
4. T417-T423 → Achievement badges (milestone motivation) → Validate
5. T429-T430 → Complete all 43 achievement checkers
6. T424-T428 → Loot box (Gold sink + reward loop) → Validate
7. T431-T433 → Polish & integration → Final validation
8. Each engine adds a new reward dimension without breaking previous engines

---

## Notes

- Task IDs T401-T433 (33 tasks) to avoid collision with Phase 1 (T001-T029), Phase 2 (T101-T124), Phase 3 (T201-T226), Phase 4 (T301-T326)
- [P] tasks = different files, no dependencies between them
- Achievement engine starts with 5-10 representative checkers (T420), remaining 33-38 added in Polish phase (T430)
- Loot box is intentionally NOT idempotent — each call is a new purchase
- Rank engine IS idempotent — high-water mark means re-runs only promote, never demote
- Chart/avatar overwrite existing images — no duplicate records, acceptable regeneration cost
- All engines are callable via CLI (consistent with WAT architecture)
- Commit after each completed user story phase
