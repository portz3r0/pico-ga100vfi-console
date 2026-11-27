# Task 26 — INTENDED state shows its PROPOSED burns

Run 2026-11-23 on the orchestrator box (no GA100 present — the natural
card-less test host). Worktree /tmp/v26 from main d551f0b (v25, burn-form
targets). No AI2 access, no hardware, primary tree untouched (dirty
`firmware/pwmvid.c` as before).

## Request

User (2026-11-23): "with the intended unlock i want the intended burns
associated with it represented but clearly labelled as proposed". The
INTENDED state must SHOW the burn records that would achieve it — visibly
PROPOSALS, not accomplished facts.

## Change

`host/ga100vfi/console/gui.py`:
- New panel `#proposed-burns` (card below the TPC map, inside `#dumpwrap`
  so the stale/history chrome applies to it too). Rendered ONLY when the
  unit/TPC state selector is on `intended` and a dump is shown; hidden and
  emptied in `stock`/`now` — proposed rows never appear there.
- One row per planner record word: target row (`auto-assigned in the safe
  FF zone at burn time; mirror row (even/odd pair) burned alongside when
  mirror is on`, or `row N — already in dump` when the exact word is
  already present), `0x00000000 → 0xPROPOSED` hex, the record key
  (chain·off) and which units it re-enables (from the planner's own
  effect text: GPC/FBP/FBPA bits). EVERY row carries a `PROPOSED` badge
  (new `.prop-tag` style, amber). Panel header:
  `PROPOSED — not burned; irreversible OTP writes pending a Goldilocks
  campaign`. Empty planner → `no burns proposed — card already at
  intended state` (no queue button).
- Single source of truth: the panel calls `window.__suggestPlan` — the
  SAME `suggestPlan()` that feeds the Glitch & Burn tab's "Suggested
  burns" card — plus the same `ffEffect`/`existingRecordFor` helpers;
  nothing in the panel re-derives encodings. `Queue these burns` calls
  `window.__queueProposedBurns` → the extracted `queuePlanRecords()`
  (now the shared body of `plan-queue-all` too) → `queueAdd` →
  `switchTab("glitch")`: same records through the same queue path, then
  the tab switch. No divergence possible.
- Recompute triggers (code comment in `renderProposedBurns`): every state
  switch and every dump change — `renderLive()` (each poll tick, each new
  dump via `applyDumpData`/`fullDump`/history pick) re-renders the panel,
  so after a real burn moves NOW, the next dump shows fewer or no
  proposals.
- Existing ids untouched (`plan-rows`, `plan-queue-all`, `queue-rows`,
  state buttons); new ids `proposed-burns`, `proposed-queue`. Planner
  strings interpolated via `esc()`. No VERSION bump.

Docs: `docs/CONSOLE.md` — "Proposed burns to reach INTENDED" bullet in
the tab tour (PROPOSED labeling, planner single-source, one-click queue,
no-burns line, recompute-on-next-dump).

## Gates (all run 2026-11-23)

- `python3 -m py_compile $(find host -name '*.py')` clean; joint import
  service/gui/__main__ + bar0/fusedump/version → `IMPORTS_OK 0.3.0`;
  `node --check` on the JS extracted from the generated live page
  (143 948-byte script) → OK.
- Mock console (`--mock dump.json`, :56527): index 200 (>100 KB),
  `#proposed-burns` container present, page unaffected.
  `version_info()`: fingerprint **`dc8893ae122e`** (was `67159c634301`),
  version still `0.3.0`.

### Playwright (chromium, real service :56526 + seeded state dir, card-less; 21/21 PASS)

Seed: `sn-111222333444` (GPC_DEFECTIVE 0x02/GPC_DISABLE 0x86,
FBP_DEFECTIVE 0x000/FBP_DISABLE 0x200, FBPA_DEFECTIVE 0x100/
FBPA_DISABLE_EFF 0x300 via hex window 0x820C18) and `sn-555666777888`
(disable == defective everywhere: intended == now). Flow: empty state →
Browse saved dumps → pick card → state buttons → panel.

```
PASS picker_lists_both_serials
PASS planner_yields_expected_words | ['0x00100201','0x000004C1','0x08000141','0x00000181']
     (encFF(1,8,0x02<<3), encFF(1,19,0), FBPA split encFF(1,5/6,·))
PASS panel_header | "Proposed burns to reach INTENDED"
PASS panel_disclaimer | "PROPOSED — not burned; irreversible OTP writes
     pending a Goldilocks campaign"
PASS no_burns_line_absent_when_plan_nonempty
PASS every_word_rendered / current_to_proposed_arrow ("0x00000000 →")
PASS mirror_row_note / units_enabled_note ("re-enables GPC2, GPC7",
     "re-enables FBP9", "FBPA9")
PASS planner_equality_suggested_card — every word from
     window.__suggestPlan() appears in BOTH #proposed-burns and the
     Suggested-burns card #plan-rows (same source, same values)
PASS proposed_rows_match_plan_rows — 4 .planword rows == 4 planner words,
     row hex set equals the planner word set exactly
PASS proposed_badges_everywhere | 7 PROPOSED badges (header row + every
     word row), all text "PROPOSED"
PASS stock_view_no_proposed / now_view_no_proposed — panel display:none,
     innerHTML empty, 0 .prop-tag in the whole document
PASS queue_button_populates_burnQueue — click #proposed-queue → glitch
     tab active, #queue-rows shows exactly the 4 planner words (.qrow ×4)
PASS intended_eq_now_no_burns_line | "no burns proposed — card already at
     intended state", no Queue button
PASS intended_eq_now_plan_empty — __suggestPlan().length == 0
PASS mock_index_200 / mock_has_proposed_container
PASS fingerprint_changed | dc8893ae122e   PASS version_unchanged | 0.3.0
```

Both servers terminated after the run (remaining `ga100vfi.console`
process on :56492 is task 23's mock, not this task's).

## Ship

- One commit `1b487b2 console: intended state renders its proposed burn
  set, labeled PROPOSED` on branch `v26`; local `main` fast-forwarded
  d551f0b → 1b487b2; worktree /tmp/v26 removed; primary tree still on
  `fuse-console`, untouched (dirty `firmware/pwmvid.c` only).
- **PUSH BLOCKED, not fabricated**: `git push fork v26:main` →
  `fatal: could not read Username for 'https://github.com'` — this
  session has no GitHub credentials (same state as tasks 23–25).
  `git ls-remote fork main` still shows
  `d551f0b68f2bd01b30a88c95f35565d40d6dbc89`. Owner with credentials
  must run: `git push fork v26:main` (fast-forward, no force).

## Not done / limits

- The panel reflects the SHOWN dump's masks (same as the Suggested-burns
  card); while browsing a saved dump it proposes for that dump — the
  stale/history strip already labels the source.
- DEVID pair records are not part of the unlock planner's output (the
  planner never emitted them before this task either); the panel renders
  whatever the planner emits, so that stays true by construction.
