# Task 66 — UX review: GA100 Fuse Console burn workflow

Design evaluation only. No code changed. All line references are
`host/ga100vfi/console/gui.py` unless prefixed `service.py`
(`host/ga100vfi/console/service.py`). Live markup confirmed against
`GET http://192.168.0.175:8790/` (2026-11-27, read-only).

---

## 1. Journey map — the burn flow as-is

Everything the burn journey needs lives in ONE long scrollable tab
(`tab-glitch`, built at gui.py:2315–2509). Panel order top→bottom:

| # | Panel (id) | gui.py | What the operator must do here |
|---|---|---|---|
| 1 | Brick warning (`gb-brickwarn`) | 2316 | read once |
| 2 | Target (`gb-target`) | 2321–2332 | pick GPU; watch `gb-gpustate` pill |
| 3 | Burn placement policy (`gb-policy`) | 2333–2358 | read; watch `gb-budget` |
| 4 | **Burn payload** (`gb-burn`) | 2359–2385 | arm here: type `BURN` in `gb-armphrase` (2378) → `gb-arm` (2379); watch `gb-armstate` countdown (2380); `gb-check`/`gb-preview` (2371–2372); `gb-burnnow` (2381); `gb-windowstate` pill (2382) |
| 5 | Suggested burns (`gb-plan`) | 2386–2406 | "Queue all needed records" (2397) |
| 6 | Tag legend (`tag-legend`) | 2407–2429 | — |
| 7 | Advanced unlocks (`gb-advanced`) | 2430–2449 | optional queue adds |
| 8 | **Burn queue** (`gb-queue`) | 2450–2464 | verify the assigned rows in `queue-rows`; the only hint of the real flow: "all of these burn in one Goldilocks window" (2451) |
| 9 | **Glitch campaign** (`gb-campaign`) | 2465–2509 | mode dropdown `gc-mode` (2493), hold dropdown `gc-hold` (2497), `gc-start`/`gc-stop` (2502–2503), `gc-state` pill (2505), HELD chip in `gc-chips` (3877), results in `gc-log` (2508) |

### The correct sequence (known only to the developer)

```
classify campaign, hold=open  ──▶  Goldilocks, window HELD
   (panel 9)                          (panel 9, chip 3877)
        │
        ▼  fades on its own in MINUTES (service.py:2549 "the link fades on its own in minutes")
scroll UP to panel 4: type BURN → Arm        ← CLICK 1+2, TTL 120 s starts (service.py:2258)
        │  server refuses arm unless GPU is Goldilocks (service.py arm_api ~2240, gui gate 3428–3430)
        ▼
scroll DOWN to panel 9: gc-mode → "burn payload on first Goldilocks"   ← CLICK 3
        │
        ▼
gc-start within the 120 s token TTL          ← CLICK 4 (token checked at start, service.py:2628)
        │  confirm dialog lists queue rows (gui.py:3932–3943)
        ▼
campaign burns queue IN-PROCESS at first Goldilocks (service.py:2458–2516)
        │
        ▼
per-record "row N: VERIFY OK" lines in gc-log text (service.py:2473) → cold boot → verify
```

Timing constraints: window lifetime = minutes (hardware decay); arm token = 120 s hard
(service.py:2258); token is validated at `/api/glitch/start` (service.py:2628) but NOT
re-checked per record inside the worker — so the race is *arm → start*, and after start
the campaign may take as long as it needs.

### Highest-friction / highest-risk points

- **R1 (top of page ↔ bottom of page ping-pong).** The three things that must happen
  within 120 s live in three different panels (arm in panel 4, mode dropdown + start in
  panel 9, queue in panel 8) on a long page. Every scroll is seconds off the TTL and
  off the window's remaining minutes. This is exactly where the operator lost the
  window tonight.
- **R2 (two burn affordances, one of them a trap).** `gb-burnnow` (2381) burns only the
  *payload* single row, never the queue (3821–3856), yet it sits next to the arm
  controls while the queue sits elsewhere. Pressing it during a held window with a
  loaded queue burns the wrong unit of work (or fails with a guard error after the
  window decayed between the 2 s poll and execution) and spends the window.
- **R3 (four window-state displays, three freshnesses).** See F3 below. The operator
  cannot answer "is the window open RIGHT NOW?" without inspecting four widgets of
  different provenance.
- **R4 (results are log text).** Per-record VERIFY results are collected server-side
  (`stats["burned"]`, service.py:2474–2475) and never rendered; they exist only as
  plain lines in the auto-scrolling `gc-log` (gui.py:2508, 3878–3881). Confirming a
  multi-record burn means reading a log — the step most likely to be skimmed on a
  victory lap before the cold boot.

---

## 2. Findings (severity-ranked by brick-risk and window-loss)

### F1 — CRITICAL · window-loss + brick-adjacent: the race-proof path is undiscoverable
The only reliable burn path (arm → switch `gc-mode` to burn → `gc-start` within 120 s)
is encoded nowhere in the UI. `gc-start`'s burn branch demands an arm token
(gui.py:3913) and errors with a text alert; the mode dropdown default is `classify`
(2494); the sole hint of the intended flow is one parenthetical in the queue header
(2451). An operator who reaches Goldilocks and does not already know the choreography
loses the window — observed tonight. A button that is enabled in one panel
(`gb-burnnow`) invites the wrong action while the correct one (Start, panel 9) looks
unchanged.

### F2 — CRITICAL · wrong-burn risk: "Burn now" burns a different thing than the queue
`gb-burnnow` (2381) posts only `payloadChecked` — the payload panel's single row
(3830). With a loaded queue, "Burn now" reads like "burn what I queued" but does not.
Its enablement (`!payloadChecked || !armed || !windowOk`, 3424) keys off a 2 s-old poll
(3454), so it is enabled while the window is already decaying and then aborts
server-side — a button that is almost never the right button, in the panel where the
arm action lives. Worst case: operator burns one payload row standalone, believes the
queue burned, cold-boots, and re-glitches against a half-burned image.

### F3 — HIGH · window-loss / misdiagnosis: four window-state indicators, none labelled authoritative
1. `gc-state` pill + "window HELD open — verify/burn now" chip (2505, 3863–3877) —
   from `/api/glitch/status` @1 s, but reflects the *campaign-end* flag
   `GLITCH["window_held"]` (service.py:2546), i.e. "the campaign chose not to revert",
   NOT "the registers are open now". It keeps saying HELD while the link fades.
2. `gb-windowstate` pill (2382, pollWindow 3436–3455) — `/api/live` @2 s, live register
   window verdict. This is the closest to truth, and it is the least prominent.
3. `gb-gpustate` pill "● Goldilocks — glitch window" (3252–3256) — `/api/gpus` is
   polled **on demand only** (3276, 4231 — no `setInterval`), so it can be arbitrarily
   stale after tab show.
4. Arm-button tooltip "selected GPU not Goldilocks — glitch first" (3430) — a fourth
   gate with the same stale source (`gpuGoldilocks`, 3249).
Tonight's exact confusion — pill says HELD, badge says closed (FUSECTRL_PLM), tooltip
says glitch first — is the predictable output of this design.

### F4 — HIGH · verification gap: per-record burn results are not rendered
`stats["burned"] = [{row, result}]` (service.py:2474–2475) is in `/api/glitch/status`
and gui.py never reads it (no reference to `.burned` anywhere in gui.py). The queue
table's "Status" column shows last-wins *pre-burn* state (2996–3000), not burn results.
`burn_aborts` and `IMAGE VERIFY FAILED` exist as chips (3875–3876) but the per-row
VERIFY OK / ALREADY BURNED / ABORT lines live only in the log box. After an
all-success burn the campaign ends and the operator's proof is a few lines of scrollback.

### F5 — MEDIUM · pre-flight gates don't cover what actually burns
Check (`gb-check`, 2371 → `/api/burn/check`) and Preview (`gb-preview`, 2372 →
`/api/burn/preview`) are genuinely valuable, but they operate only on the payload
panel's single row (`payloadChecked`, 3748) and their verdict is invalidated by payload
edits (`gb-editwarn`, 2383, `invalidateChecked` 2566). The queue — what actually burns
on the good path — gets client-side row allocation and collision alerts
(`queueRecords` 3099–3119) but no per-record guard check or preview. The tool checks
the wrong unit.

### F6 — MEDIUM · TTL countdown exists but is off-screen when it matters
The armed countdown ("● armed 87s", 3398, ticked @1 s, 3432) lives in panel 4; the
action that consumes the TTL (`gc-start`) is in panel 9. Between arming and starting,
the operator cannot watch the clock and the button at the same time.

### F7 — MEDIUM · no state machine between campaign end and burn start
After a held classify campaign the UI returns to "idle" + a HELD chip; nothing prompts
"window is open — arm and start a burn campaign now". `gc-mode` silently stays on
`classify`; starting without switching just re-glitches and burns nothing. The
transition the operator is fumbling for has no visual representation.

### F8 — LOW · the one correct hint is a parenthetical
"all of these burn in one Goldilocks window" (2451) is the only sentence in the GUI
describing the real flow. It is grey note text in a mid-page card header.

### F9 — LOW · `gb-gpustate`/arm-gate staleness by construction
`loadGpus()` has no interval (3276, 4231); the arm gate can therefore enable Arm from
a stale Goldilocks reading and the server refuses (arm_api), or vice-versa disable Arm
while the window is actually open. The refusal text (armRefusal, 3414–3417) mitigates
but adds another contradictory indicator.

---

## 3. Redesign proposal — one Burn workspace, one truth, one action

### Core: a dedicated **Burn** tab (or pinned workspace card) that owns queue + arm + launch

**One primary action: `⚡ Arm & burn queue (N records)`.**
One click → one server call (`POST /api/burn/arm_and_start`) that, atomically and
server-side: re-runs the arm gate (Goldilocks 4-check), verifies the phrase, mints the
token, validates records + identity gate, and starts a burn-mode campaign with the
queue's `records[]`. The 120 s TTL race disappears because arm and start are the same
request; the TTL survives only as a fallback (arm alone still possible for advanced
use). The BURN-phrase confirmation moves *into* the button's flow: the button is
disabled until a small phrase box beside it reads `BURN` — same friction as today,
co-located with the action it guards.

**One authoritative window indicator, mirrored not duplicated.**
Single source: the live register poll (`/api/live` `window_ok` + `window_checks`,
service.py:593–601) — the only thing that answers "is the window open NOW". Render it
once in a **sticky status strip** pinned to the top of the Burn workspace (visible
while scrolled anywhere in the flow), states:

- `● WINDOW OPEN` (green) — all checks pass, age of poll shown ("poll 1.2 s ago").
- `◐ WINDOW FADING` (amber) — window_ok true but ≥1 check flapped in the last N polls,
  or DSOV drifting; derived server-side from poll history. Gives the operator the
  "minutes left" warning the hardware implies but nothing shows.
- `○ WINDOW CLOSED (FUSECTRL_PLM)` (grey) — with the failing check names, as today.

The campaign's `window_held` flag is *renamed and re-scoped* to what it is: a campaign
log line / chip "campaign ended holding the window" — an event, not a state. The
`gb-gpustate` Goldilocks badge and the arm tooltip are removed as state sources (the
GPU selector keeps a plain locked/unlocked label). One question, one widget.

**Queue becomes the only burn unit on the happy path.**
- Payload panel is demoted to a collapsed drawer "Manual burn (direct rows / IFF)" —
  it keeps `Burn now` for the genuinely manual cases (DIRECT rows <222, IFF words,
  which the queue refuses anyway, 2944), clearly out of the happy path.
- **Check/Preview belong to the queue, not the payload.** Each queue row gets a
  per-record pre-flight badge: `✓ checked ✓ previewed` bound to the (row, value) hash;
  editing or re-allocating the row invalidates that row's badge. One button
  "Check & preview all" iterates the existing `/api/burn/check` + `/api/burn/preview`
  endpoints per record (both are read-only and window-independent — the preview title
  at 2372 already says CMD_READ works outside a window). `Arm & burn queue` is
  disabled until every row carries both badges — the pre-flight gates become
  un-skippable on the path that actually burns, instead of optional on a panel that
  doesn't.
- Queue rows show their assigned target row (already done, 2993–2995) and, after a
  burn, the **result**: a Result column fed from `stats.burned` (already on the wire):
  `VERIFY OK` green, `ALREADY BURNED` amber, `ABORT …` red, `pending` dim. No
  scrolling: the table the operator queued from IS the results table. `gc-log`
  collapses to a details drawer for post-mortems.

**TTL countdown where the action is.** With arm+start fused, TTL mostly vanishes; for
the standalone-arm fallback, the countdown renders inside the sticky strip next to the
window state ("armed 87 s"), not in a panel body.

**Decay degradation (the design's failure mode, designed):**
- Window CLOSED/FADING before launch: `Arm & burn queue` is replaced by
  `▶ Re-glitch to open window` — one click starts the classify+hold campaign with the
  queue and badges preserved; the strip shows why it's closed (failing check names).
  The operator never hunts for the campaign panel again.
- Window decays after launch: the burn campaign keeps firing attempts until all
  records VERIFY (service.py:2516 already does this) — the strip just tracks it live;
  no action needed. This is the design's key win: post-launch, decay is the
  campaign's problem, not the operator's.
- Phrase typed but window closed at click time: button disabled with the strip's
  reason echoed inline ("closed: FUSECTRL_PLM — press Re-glitch").
- Server-side, `arm_and_start` refuses atomically with the arm-gate's failing-check
  names, so a click that races decay returns one honest error, not a guard failure
  mid-burn.

**Why this is safe, not just slick:** every existing gate survives — phrase, Goldilocks
arm gate, identity/die-ID gate (service.py:2631), per-record guards, plane gate,
journal-uncertainty ack, the irreversible-burn confirm (the confirm dialog content
moves into the launch step, listing rows/values), and the in-process burn-on-goldilocks
worker is unchanged. The redesign removes *scattered UI choreography*, not safety.

### Migration notes (for a later implementation task, not this one)
- New endpoint composes existing `arm_api` + `glitch_start` validation; no change to
  the burn worker.
- `stats.burned` needs no server change; gui.py `setCampaignUI` gains a queue-result
  render.
- FADING state needs a small poll-history buffer in the `/api/live` poller.

---

## 4. Mockup

`evidence/66-ux-mockup.html` — static, self-contained, dark, monospace numerals.
Shows: sticky window-state strip (open / fading / closed), the queue with pre-flight
badges and per-record burn results, the `Arm & burn queue` button with TTL countdown,
the decayed-window degraded state, and the manual-burn drawer.
