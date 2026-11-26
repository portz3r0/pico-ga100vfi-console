# Fuse Console

A self-contained web GUI + service for GA100 fuse work (CMP 170HX and
rebranded A100 `10de:20b5` — same die, same fuse block). Everything here
serves one goal: **unlock every unlockable (recoverable) TPC/SM on the
card** — read the die's own defect fuses, glitch into the state where the
floorsweep can be rewritten, burn the FF records that re-enable every
disabled-but-healthy unit, and verify the result. Live register/fuse
viewing, glitch campaigns, guarded fuse burns, driver control and GPU
status, all in the `ga100vfi` package, driven from a browser.

This document has three parts: **how to run it**, **how to use it** (the
UI layout, the two operating modes, what the interpretation numbers mean,
and the end-to-end unlock workflow), and **reference** (burn safety model,
HTTP API, systemd, testing, troubleshooting). For a plain-language
operating manual (safeguard table, success reading, failure recovery,
glossary) see the [User Guide](USER-GUIDE.md).

## Requirements

- Linux host with the GA100 card installed and the pico plugged into the
  **same host** (default `/dev/ttyACM0` — campaigns need serial control of
  the pico and PCIe BAR0 access to the card simultaneously).
- The `ga100vfi` package importable (`pip install -e host/` or
  `PYTHONPATH=host`), with `pyserial`.
- Root — BAR0 access goes through sysfs `resource0`, and the driver
  blacklist actions write `/etc/modprobe.d`.
- Any browser on the same LAN. The service has **no authentication**: run
  it on a trusted network or front it with your own auth proxy.

## Starting the console

```sh
sudo python3 -m ga100vfi.console --bdf 0000:41:00.0 --port 8790
# or, after `pip install -e host/`:
sudo ga100vfi-console --port 8790
# --bdf is optional: the card is auto-detected; pass it only to choose
# which card the Fuse Explorer watches on a multi-GPU host (burns and
# campaigns pick any GA100 at runtime). If the configured BDF is not
# present (card moved slots), the console follows the detected GA100 and
# says so via default_note — never a phantom. An explicit --bdf that is
# not GA100 silicon present at startup is a hard error (typo guard).
# With no --bdf and no GA100 on the host the console still starts and
# serves: it logs a warning, shows 'no GA100 present on this host', and
# self-detects a card inserted later on the next poll.
```

Then open `http://<host>:8790`. The service generates its own `live.html`
at startup (seeded from the newest dump it can find) and serves everything
from memory — no web server to install.

Useful flags:

| Flag | Default | Meaning |
|---|---|---|
| `--bdf` | auto-detected | the card the Fuse Explorer tab watches live; must name a present GA100 at startup (hard error otherwise) — omit it to run card-less |
| `--port` | `8790` | HTTP port |
| `--listen` | `0.0.0.0` | bind address (`127.0.0.1` keeps it host-local) |
| `--state-dir` | `~/ga100-fuse-view` | full dumps, generated `live.html`, `goldilocks.jsonl`, burn journal |
| `--poll` | `1.0` | server-side probe interval (seconds) |
| `--rows` | `0-487` | row range for full dumps |
| `--ff-buffer` / `--ff-tail-reserve` / `--ff-sm-reserve` | 4 / 12 / 16 | burn placement policy zones |
| `--mock` | — | serve a recorded `dump.json` instead of a real card (see Testing) |

For a permanent install see [the systemd unit](#systemd-example) below —
order it after `network.target`, not `multi-user.target`, or it can come up
minutes late on slow boots.

## The UI at a glance

- **Frozen top bar** — title `GA100 Fuse Console`, a meta line under it
  (BDF, PCI id + revision, bound driver, dump time, fuse fingerprint, row
  count), and on the right a **Support bundle** button (downloads the
  `tar.gz` described in [Submitting a support bundle](#submitting-a-support-bundle))
  next to the `pico-ga100vfi · live console` badge. The top bar stays
  pinned while you scroll.
- **Vertical tab rail (left)** — four tabs: `Fuse Explorer`,
  `Glitch & Burn`, `Drivers`, `GPU Info`. The active tab is highlighted;
  arrow keys move between them.
- **Right status rail** — the live bar: the live indicator pill (starts at
  `connecting…`), the `GPU:` selector (which GA100 the Fuse Explorer
  targets), the `page poll:` selector (`off` / `1s` / `2s` / `5s`), the
  **⟳ Run full dump** button, and the interpretation feed (timestamped
  register-change lines).
- **Narrow windows (≤ 860 px)** — the tab rail collapses to a horizontal
  sticky row under the top bar and the status rail un-sticks and moves
  above the content; nothing is hidden, the layout just stacks.

## The two operating modes

What the console can do depends on whether the `nvidia` driver is bound to
the card:

- **Driver unbound** — full operation. The server-side poller reads BAR0
  directly (pure reads, safe any time), the live view updates, and glitch
  campaigns / burns are available.
- **Driver bound** — the live view **pauses**: raw BAR0 reads against a
  GSP-driven card can wedge the GSP (WPR2 stuck — only a cold boot
  recovers). The live pill shows
  `driver '<driver>' bound — raw BAR0 live view disabled (Drivers tab -> Unload nvidia stack to resume)`
  and the paused panel explains itself (fuse values only change via burns
  or glitches — re-dump if anything changed) and offers a manual
  **Capture fuse dump (driver bound)** — a preflighted, consented guarded
  capture whose results are labelled **UNVERIFIED (driver bound)** (see
  [Driver-bound guarded capture](#driver-bound-guarded-capture)).
  Glitch campaigns refuse to start entirely while a driver is bound: every
  attempt reprograms PCI `COMMAND`/`BAR0` via `bar0.restore()`, which
  corrupts GSP boots under a bound driver.

The **Drivers** tab is the switch between modes: **Unload nvidia stack**
to go unbound, **Load nvidia** to hand the card back.

## Reading the numbers: what DEFECTIVE, the ceiling and headroom mean

Chasing the unlock means reading three things correctly. The console's
TPC map and totals come from `fusedump.tpc_summary`:

- **DEFECTIVE = FF-region fuse words, permanent.** Per-GPC defective TPC
  masks come from the FF-region readout words `TPC_DEFECT_FF`
  (`0x8205C8`, `0x820508`, `0x82050C`, `0x820514`, `0x820564`, `0x8205AC`,
  `0x820B84`, `0x820B80`) — the only defect source that survives GPC
  power-gating, hence the only correct ceiling source on stock floorswept
  cards.
- **The runtime / SKU words are NOT defects.** `0x820760+gpc*4` is the SKU
  floorsweep disable word and `0x820C38+gpc*4` the runtime TPC mask — both
  live inside the GPC power well, and a floorswept (powered-off) GPC reads
  `0xFF` in both. That is a power artifact, never a defect count. (A
  2026-11-19 regression read `0x820760` as the defective array and counted
  24 phantom dead TPCs on a stock 170HX; the ceiling MUST come from the FF
  words — fleet-verified 13/13 against the kate-land ga100-options table.)
- **sm_now vs the fuse ceiling vs headroom.** `sm_now` counts SMs enabled
  right now (0 for a floorswept GPC). The **fuse ceiling** (`sm_max`,
  shown as `SM after unlock (fuse ceiling)`) is `(8 − defective TPC) × 2`
  per non-defective GPC — the most this die can ever run. The gap between
  them is your **unlock headroom** (`unlock headroom: N TPC / M SM`):
  every disabled-but-healthy TPC, including whole floorswept-but-healthy
  GPCs. That number is the unlock target.
- **Old dumps self-repair.** When a dump carries the hex window
  (`hex_window_0x820000.txt` / `hexnonzero`), the FF defect words are
  re-read from it as ground truth — dumps saved by older builds whose
  defect keys came from the runtime word interpret correctly again.

Where each UI number comes from: the **TPC map** cells and per-GPC lines
from the per-GPC masks above (bit set = masked; 8 TPC per GPC, 2 SM per
TPC); the **Silicon topology** GPC/FBP boxes from `GPC_DISABLE` /
`GPC_DEFECTIVE` / `FBP_DISABLE` / `FBP_DEFECTIVE`; the memory claim from
live FBP count × 8 GB; the **Diagnosis** verdict from the floorsweep masks
(zeroed masks + dead silicon enabled = the brick signature).

## A tour of the tabs

### Fuse Explorer

The live view of the selected card.

![Fuse Explorer tab](images/console-explorer.png)

- **Refresh model (default: calm)**: the heavy full-page register redraw
  is **off by default** — pick a rate in the `page poll` selector only
  when you want the register grid to live-redraw. What keeps refreshing
  regardless: the **interpretation feed** (register-change diff, 2 s), the
  **dmesg tail** (GPU-relevant lines, 2 s), the **Glitch campaign
  log** (1 s), and the **GPU Info monitor** (1 s, user-adjustable 1–10 s
  or off). All pollers pause when the browser tab is hidden.
- **Live feed**: status + shadow register changes flash amber and land in
  the activity feed; you will see `DSOV` flip from 1 to 0 the moment a
  glitch lands.
- **⟳ Run full dump**: all fuse rows 0–487 via the fuse-macro `CMD_READ`
  path, plus the hex window and dmesg, archived to
  `<state-dir>/dumps/sn-<serial>/<ts>/` (serial-keyed; see "Dump
  identity"). The page requests one automatically on
  load; while a campaign is running the server refuses it (`campaign
  running — full dump refused` — a mid-campaign sweep could push classify
  past the Goldilocks window).
- **Current-card-only default**: the page's default face is the present
  card's own data and nothing else — the seed is the newest dump whose
  serial matches the card in the slot, plus the automatic full dump of
  that card. Card-less, or no same-serial dump saved, the dump-derived
  panels stay hidden behind an empty state (`No GA100 present — nothing
  live to show.` / `No dump yet for this card (serial X).`) with a
  **Browse saved dumps** button; another card's dump is never rendered by
  default.
- **Saved dumps (header button)**: explicit history browser, opened as a
  **modal popup** (same pattern as the unit audit) so it works from every
  tab — backdrop click or Escape closes it. The picker
  lists every saved dump newest-first (`serial · timestamp ·
  driver-bound/UNVERIFIED flags · rows`, `(current card)` tag; unreadable
  dirs shown as such); the list scrolls internally so
  hundreds of saved dumps stay usable; closing it never scrolls the page.
  A **Dedupe** button in the picker header dry-runs the identical-content
  scan (see `/api/dumps/dedupe`) and deletes the duplicates only after
  you press the confirm button.
  Selecting one loads it into the explorer panels
  under the stale chrome: dimmed panels + strip `Browsing saved dump —
  serial X, dumped <ts>` with a **← Back to current** button that leaves
  history mode and restores the default resolution (the present card's
  newest saved dump read back from disk, else the empty state). History
  is client-side state only; the live polls keep refreshing the live
  bits while browsing.
- **Diagnosis**: the brick-signature verdict — floorsweep masks fully
  cleared with dead silicon enabled is drawn red; otherwise *masks-cleared
  brick signature absent*.
- **Silicon topology — GPC / FBP floorsweep**: one box per GPC and FBP
  with a state selector (`Stock state (this card's factory fuses)` /
  `Intended (this card's defects)` / `NOW (live)`) and a legend: `active`,
  `floorswept (re-enableable)`, `dead silicon · off`,
  `dead silicon · ENABLED (brick)`. The unlock goal in this view: `NOW`
  matching `Intended` — every non-defective unit active.
- **Stock / Intended / Now — the three states**: `STOCK` is **this
  card's own factory baseline** — the first dump ever saved for its board
  serial (`dumps/sn-<serial>/stock.json`, served by `/api/stock`),
  rendered with the same GPC/FBP/mem/TPC extraction as `NOW`. It replaced
  a hardcoded CMP 170HX SKU template that showed a virgin card a phantom
  "pre-glitch" difference (AI2, 2026-11-23). `INTENDED` = the disable
  mask equals this card's defective mask: every unit that is not dead
  silicon runs. `NOW` = the live registers of the shown dump/poll.
  Diff honesty follows: a stock-vs-now difference is a **real fuse
  change** (campaign effect); a virgin card shows zero difference. If the
  card was modified before this console first saw it, stock = state at
  first sight (the provenance line in the note names the baseline). When
  no baseline exists yet, the stock view shows the now state with
  `No stock baseline recorded yet — this dump is the first record`.
- **Proposed burns to reach INTENDED**: while the unit/TPC view is in the
  `INTENDED` state, a panel below the TPC map lists the burn records that
  would achieve it as a **table** — `✓ | Burn | Word | Target row | Field |
  Effect | Status` (multi-word entries such as the FBPA pair share their
  Burn/Effect cells via rowspan). Each word names its **exact** target row
  (`row N`, `+ mirror N+1` when the burn form's mirror checkbox is on —
  it is OFF by default), the current word → proposed word (hex), the
  decoded field and the units each word re-enables. Every word carries a
  selection checkbox (see *Per-burn
  selection and LAST-WINS already-present marking* below); an unselected
  word shows `not selected — not queued` and gets no row; a word already
  in the burn queue shows `in queue — row shown there` instead of a second
  allocation — **one word, one row**. Proposals name
  their exact rows because the panel assigns them through the SAME free-row
  allocator the burn queue uses (same dump, same plan order, SELECTED words
  only, same mirror setting) and the allocation accounts for the CURRENT
  queue, so `Queue these burns` produces a queue whose
  rows equal the proposed rows; if the safe zone runs out mid-plan the word
  shows `NO FREE ROW (block B)` and the panel header warns
  (counting SELECTED words). Every row carries a `PROPOSED` badge and the header
  states `PROPOSED — not burned; irreversible OTP writes pending a
  Goldilocks campaign`, with a pointer to the Glitch & Burn tab's
  **Tag legend** for what every badge means: these are proposals, not
  accomplished facts, and
  they never render in the `STOCK` or `NOW` views. The rows come from the
  SAME planner that feeds the Glitch & Burn tab's `Suggested burns` card
  (one source, no divergence), and `Queue these burns` pushes exactly the
  SELECTED records into the burn queue and switches to that tab — queueable
  in one click. When the planner yields nothing the panel says
  `no burns proposed — card already at intended state`; after a real burn
  changes `NOW`, the panel recomputes on the next dump (fewer or no
  proposals).
- **TPC map — SM availability per GPC**: one row per GPC, 8 TPC cells
  each (2 SM per TPC). Cell colours: **green** = `enabled now`, **yellow**
  = `disabled · healthy (unlock headroom)`, **red** =
  `defective silicon (never usable)`. Per-GPC line: `SM now`,
  `after unlock`, defective count and `+N recoverable`; totals pills at
  the bottom (`SM now`, `SM after unlock (fuse ceiling)`, `defective`,
  `unlock headroom`). Floorswept or dead GPCs are marked (`floorswept` /
  `GPC defective`) and their cells dimmed: their health is shown, but
  they only run once the GPC itself is enabled — the TPC ceiling assumes
  the GPC-level floorsweep is unlocked too.
  Note: a GPC can be unflagged in `GPC_DEFECTIVE` yet fully defective at
  TPC granularity — the TPC map exposes this; the topology view cannot.
- **Row explorer**: every fuse row with region colouring (`MAIN` / `UNIQ`
  / `FPF` / `FF`), filter buttons `Non-blank`, `FF records`, `All rows`,
  `MAIN`, `FPF`, `FF`, a search box, and the verified FF-record decode
  (`chain`, `iff`, `block`, `data`). Click a row for its 32-bit breakdown
  and the record timeline (last record per block marked
  `LAST — EFFECTIVE`).
- dmesg and hex-window browsers underneath.

### Glitch & Burn

The campaign control room. A brick warning banner heads the tab: *Burns
are permanent OTP writes — a wrong burn can BRICK your GPU permanently.*
Everything targets the GPU picked in the **Target** card at the top (live
state pill + board serial + bound driver). Standalone burns are only
allowed on a GPU currently in the **Goldilocks** state — the campaign's
burn-on-goldilocks mode creates that state on the selected GPU.

![Glitch & Burn tab](images/console-glitch-burn.png)

- **Burn placement policy**: the seven brick rules, a live row map of the
  FF region (`boot FFs · N` | `buffer N` | `BURN ZONE · N free` |
  `SM reserve N` | `revert N`) and the budget pill
  (`safe zone rows A–B · N free · last boot FF: row N`; on an
  already-burned card whose global zone is empty the pill instead says
  placement is per-block — see the FF placement policy below). The
  target-row field shows a live zone verdict (`✓ safe zone`, `✗ occupied
  (boot FF)`, `✗ buffer zone`, `✗ SM reserve (keep free)`,
  `✗ revert tail (keep free)`, `✗ outside FF region`; when the global
  zone is empty it states the per-block rule the server enforces).
- **Burn payload**: target row, **value source** selector (`typed hex` or
  `from dump row` — enter the row of an existing record and the console
  grabs its value from the loaded dump and shows it decoded, FF
  ch·blk·data with known block names, IFF flagged, so burn values never
  have to be typed by hand; blank or missing source rows warn instead of
  proposing a burn of zero), a `burn mirror row too` checkbox — **OFF by
  default** (the proven reference recipes burned ONE row per FF record;
  the redundant even/odd mirror pair stays an opt-in), **Check row & guards**
  and **Preview burn (read-only)** (see the burn workflow below for what
  each shows).
  Burn-payload fields carry **no hardcoded defaults**: target row and
  value start empty (placeholders only) — the FF audit pills and the
  loaded dump are the sources of targets, and **Check row & guards**
  refuses an empty row or value client-side (the server check stays
  authoritative). The `from dump row` field defaults to the **first blank
  FF row (≥222) of the currently loaded dump**, recomputed whenever the
  loaded dump changes (history pick, back-to-current, full dump); a dump
  with no blank FF row leaves it empty with a `no blank FF row in this
  dump` placeholder.
  Editing any input invalidates a completed check (`payload edited —
  re-check`) — the check IS the safety contract.
- **Suggested burns — minimum common unlock**: derived from **this card's
  own defect masks** in the loaded dump — every disabled-but-healthy unit
  re-enabled in one pass: GPC 1 word + TPC unlock words (chain1 offs
  11–15, one per word that actually changes — see below) + FBP 1 word +
  FBPA 2 words. The card renders the SAME table shape as the proposed
  panel — `✓ | Burn | Word | Target row | Field | Effect | Status | +
  queue`. Each word is labeled **PROPOSED** and names its **concrete
  target row** (`row N`, plus `+ mirror row N+1` when mirroring is
  on), computed by the SAME `assignRows` allocator the burn queue uses,
  run over the current queue plus the SELECTED records in queue order and
  the mirror setting **⤓ Queue all needed records** will read — so the rows
  shown ARE the rows the queue assigns (proposal == queue by
  construction; a word already in the queue shows `in queue — row shown
  there` rather than a second allocation — one word, one row; no
  free-row fallback: placement is per block, so a word
  whose own block has no blank row after the block's last record shows
  `NO FREE ROW (block B)` while the other words still
  get concrete rows). **⤓ Queue all needed records** puts the SELECTED
  words in the queue (nothing selected → `no burn words selected — nothing
  queued`); already
  equal masks report *this card needs no unlock burns*; presence is judged
  LAST-WINS (see *Per-burn selection and LAST-WINS already-present
  marking* below): a word whose block's last live record already equals it
  is tagged `ALREADY PRESENT (row N) — no burn needed` and defaults
  UNticked; a word present in its block but overridden by a later record
  is tagged `SUPERSEDED at row N — needs re-burn` and stays ticked. Every
  word carries a selection checkbox; `select all` / `select none` sit
  beside **⤓ Queue all needed records** and the same checkboxes appear on
  the INTENDED-state panel (shared state, one `N of M word(s) selected`
  pill). An optional
  **DEVID change** adds an identity A/B pair via **+ Queue DEVID A/B pair**
  (takes effect at next cold boot); the field is never pre-filled with a
  foreign demo value — it holds the loaded dump's own DEVID (decoded from
  its DEVIDA/B records, chain 2 block 37/38) when the card carries one,
  and starts empty with a placeholder otherwise.
- **TPC unlock proposals**: the planner also proposes the chain1 offs
  11–15 words (`OPT_TPC_GPC{g}_DISABLE`, live at global bit 187+8g — ray
  schema plane FF, word = bit//16), setting each GPC's TPC disable bits
  to that GPC's defective mask (`TPC_DEFECTIVE_GPC{g}` shadow). Current
  values come from the loaded dump's last-wins chain1 records (not the
  shadow registers); **shared bits are preserved** — every non-TPC bit of
  a word (the PES bits in word 15, FBPA/GPC spill in words 5–8) is kept
  from the current word, and word 15's effect line states `PES bits
  preserved`. Words that already equal the target are skipped (no
  proposal), and GPCs whose defect word is unknown are left untouched.
- **Advanced unlocks — optional, tested permanent unlocks**: permanent
  unlocks whose burns were **executed and confirmed working on tested
  cards** (single source:
  `host/ga100vfi/advanced_unlocks.py` (`ADVANCED_UNLOCKS`), embedded into
  the page by `build_html` (`__ADVANCED__`); plan provenance and decode
  reasoning: `evidence/30-advanced-unlocks.md`). Items: **PCIe Gen4
  permanent**, **PLM unlock**, **Compute unlock (full floorsweep +
  SS0/SS1)**. Each item shows its FF word(s) with chain/block/field
  decode and a **TESTED badge** naming the test scope:
  `TESTED · EXTERNAL` (burn executed and confirmed working on cards
  outside this fleet) or `TESTED · INTERNAL` (confirmed on our own
  cards). The badge is purely empirical — the burn was proven by
  executed cards. The **confidence badge is a SEPARATE axis**: VERIFIED =
  field mapping documented in the repo's evidence files or the GA100
  hwref; UNVERIFIED = attribution inferred, unresolved. A word can be
  TESTED but UNVERIFIED: proven to copy, not yet understood. No recipe
  or card-name provenance text appears anywhere in the UI; steps whose
  value is known to vary per die carry a `per-die variant: another
  tested card burned 0x… (defect-driven)` note. **Every chain-1
  compute-unlock word is RECOMPUTED from the shown card's own defect
  readouts** (GPC/TPC/FBP/FBPA/FBIO/NVLINK/PES/ROP_L2/SYS_PIPE
  `_DEFECTIVE`, placed at the logical-field bit positions of the
  170HX-RAY catalog — `evidence/40` §3); the tested words remain only as
  the reference recipe shown beside each row. When a plane's readout is
  missing from the loaded dump (old dumps predate PES/ROP_L2/SYS_PIPE/
  FBIO capture), that field's bits **carry the card's own current word**
  — nothing of unknown status is ever enabled — and the row is labelled
  `no <plane> defect readout in this dump — current word carried`; take
  a fresh full dump to get all readouts and the full derivation. These
  remain **IRREVERSIBLE OTP writes** — check every word against the
  shown card before burning. FF steps show PROPOSED target
  rows through the
  same `assignRows` allocator over the current queue plus the item's
  SELECTED steps (re-placed on the shown card — the plans' original rows
  are never shown as targets), and **+ queue** enqueues
  exactly the item's SELECTED FF words at those rows (per-word
  checkboxes with `select all FF words` / `select none`; nothing selected →
  `no FF word selected — nothing queued`). FF steps carry the same
  LAST-WINS badges as the plan lists; DIRECT rows (<222) are judged
  present when every delta bit is already set in the dump's row value.
  An item badges `ALREADY PRESENT — no burn needed` when all its checked
  steps are effective, else `PARTIALLY PRESENT (k/n: …)` naming the
  effective words/rows. Steps outside the queue's
  path are flagged **MANUAL**: DIRECT rows (<222, plain OTP words, not
  FF records) and IFF words (bit 5 set — refused by the placement
  policy), because `burn_execute` accepts FF records at rows 222–487
  only; an item with no FF steps shows *no queueable FF records —
  manual burn path only*.
- **Tag legend — what every badge means**: a collapsible card
  (`#tag-legend`) on the Glitch & Burn tab that explains every badge the
  burn UIs emit, and states the **two independent axes**: a `TESTED`
  badge says the burn was **executed and the cards came back working**
  (empirical safety; scope `EXTERNAL` = cards outside this fleet,
  `INTERNAL` = our own cards), while `VERIFIED`/`UNVERIFIED` says whether
  we know **what the word does** (bit-level attribution) — a word can be
  TESTED but UNVERIFIED. Badges documented: `PROPOSED` (candidate only,
  nothing written), `VERIFIED`, `UNVERIFIED`, `TESTED · EXTERNAL`,
  `TESTED · INTERNAL`, `ALREADY PRESENT` (last record of the block
  already equals the word — a no-op), `PARTIALLY PRESENT` (some selected
  words already effective), `SUPERSEDED at row N` (a later record
  overrides it at boot — needs re-burn), `MANUAL` (outside the FF queue
  path — direct rows <222 or IFF bit-5 words) and the red
  `NO FREE ROW FOR BLOCK N` refusal. The proposed-burns panel header
  points here for badge meanings.
- **Per-burn selection and LAST-WINS already-present marking**: every word
  in the three burn lists (INTENDED-state proposed panel, Suggested burns
  card, Advanced unlocks FF steps) carries a checkbox; the proposed panel
  and the Suggested card share ONE selection state, so their checkboxes
  always agree. Default: a word is SELECTED unless it is already EFFECTIVE.
  Presence is judged by the replay rule, not by string match: a word is
  `ALREADY PRESENT (row N) — no burn needed` only when the LAST live record
  of its own FF block equals it (rows 222–487, blank = 0x0/0xFFFFFFFF;
  IFF words have no block replay and are never present) — such words
  default UNticked. A matching word that a later record of the same block
  overrides is `SUPERSEDED at row N — needs re-burn` and stays ticked: the
  boot replay never reaches it, so re-burning is the fix, not a no-op.
  Advanced DIRECT rows (<222, plain OTP words) are present when every
  delta bit is already set in the dump's row value. `select all` /
  `select none` reset the whole list. All queue paths (`⤓ Queue all needed
  records`, `Queue these burns`, per-word `+ queue`, advanced `+ queue`)
  and the proposal row allocator honour the selection — unselected words
  are neither allocated rows nor queued, so proposal == queue holds under
  any selection. Re-checking an already-present word queues it anyway; the
  queue row then carries the amber `⚠ already present — likely no-op
  (row N)` tag.
- **Burn queue**: all queued records burn together inside **one**
  Goldilocks window; rows are auto-assigned to free safe-zone rows at
  campaign start (the server re-validates every row against the placement
  policy). The queue renders as the SAME table shape as the burn lists —
  `# | Word | Target row | Field | Status | Via | action` — so what the
  queue displays IS what it will burn. A queued word already EFFECTIVE
  under last-wins is highlighted
  with the amber `⚠ already present — likely no-op (row N)` tag; a
  superseded word shows `SUPERSEDED at row N — needs re-burn`. Custom
  records can be added by row + hex value (both start
  empty; the **first free FF row** button fills the row with the first
  blank FF row of the loaded dump); an explicitly typed custom row is
  **reserved before auto-allocation** — a row claimed by two records
  blocks the queue (`row(s) N claimed by two records — remove the
  duplicate custom row before burning`), enforcing **one word, one row**
  (fuses OR; sharing a row corrupts both). Queue entries are optionally
  mirrored (mirror is opt-in, off by default); **clear queue** empties it.
- **Glitch campaign**: `v_dip mV`, `pulses`, `pw µs`, `gap µs`, `delay`,
  `max attempts`, a **v_dip strategy** selector (`fixed v_dip` or the
  default `adaptive 3D (v_dip · delay · pw)` with `adaptive v min mV` /
  `adaptive v max mV` bounds), the pico **port** dropdown with **⟳
  rescan**, a **mode** selector (`classify only — observe glitch states`
  or `burn payload on first Goldilocks`), and a **Goldilocks window**
  selector (`hold open — no revert (default)` or `auto-revert VRM`).
  Buttons: **▶ Start campaign**, **■ Stop**, **⟲ Revert VRM** (enabled
  only while a window is held). Stats chips: attempts / valid / lost /
  nack / poisoned / dsov=0 / goldilocks / burn aborts / image verify / held window.

### Drivers

Live driver state (bound driver, driver version, blacklist status, loaded
modules) and the actions **Load nvidia**, **Unload nvidia stack**,
**Blacklist nvidia + nouveau** (two-step confirm: click, then `confirm?`)
and **Remove blacklist**. Glitching needs `nvidia` unloaded **and**
blacklisted — the driver re-locks the VRM and binds the card before you
can inspect BAR0. The blacklist written here (`/etc/modprobe.d/ga100-fuse-blacklist.conf`)
still allows manual `modprobe`, so you stay in control. Unload unbinds the
GPU from sysfs first, then `rmmod`s `nvidia_drm` / `nvidia_modeset` /
`nvidia_uvm` / `nvidia`.

![Drivers tab](images/console-drivers.png)

### GPU Info

One section per GPU on the host (nvidia-smi card grid + `GA100 · fuse
target` / `selected` tags), an nvtop-style **Live monitor** (util/mem
sparklines, VRAM, power, temp, PCIe gen, compute-process table; refresh
`1s`–`10s` or off) and **PCIe link (lspci)** state. Reports the
`nvidia-smi` error string honestly when the card is GFW-dead — that banner
is normal until the card boots cleanly. While the nvidia module is absent
the console deliberately skips nvidia-smi (`driver not loaded — nvidia-smi
skipped (NVML would auto-load the driver)`) — calling it would silently
undo a deliberate unload.

![GPU Info tab](images/console-gpu.png)

## The end-to-end unlock workflow

The whole chase, in the order that actually works:

1. **Drivers tab → driver unbound.** **Unload nvidia stack**, then
   **Blacklist nvidia + nouveau** so a reboot doesn't re-bind it. Campaign
   start refuses while any driver is bound.
2. **PLM unlock (first Goldilocks).** Run a `classify only — observe glitch
   states` campaign; when it hits Goldilocks (`DSOV = 0`, `CRC_STATUS =
   0x55`, privilege masks open) the default **hold open — no revert**
   leaves the window open — that state is the PLM unlock. Close it with
   **⟲ Revert VRM** when done.
3. **Full dump.** **⟳ Run full dump** on the Fuse Explorer tab (driver
   unbound — the normal live path). The dump archives to
   `<state-dir>/dumps/…`.
4. **Read the ceiling and the headroom.** On the TPC map: `SM after unlock
   (fuse ceiling)` is the maximum this die can run; `unlock headroom` is
   what the unlock can still win. Defective TPCs are permanent — never
   plan a burn that enables them.
5. **Plan the records.** **Glitch & Burn** → *Suggested burns — minimum
   common unlock* → **⤓ Queue all needed records** (GPC + TPC + FBP + FBPA
   words derived from this card's own defect masks; optionally **+ Queue
   DEVID A/B pair**). Review the queue table; every record burns in one
   window.
6. **Arm.** Type `BURN` in the arm field and press **Arm (120 s)** — the
   button is gated on the selected GPU's live Goldilocks state.
7. **Glitch campaign in burn mode.** Mode **burn payload on first
   Goldilocks**, **▶ Start campaign**. On the first Goldilocks the
   campaign burns the queued records **in-process** (the PCIe window dies
   seconds after the campaign loop returns — a separate burn call would
   miss it), re-checking every guard before each `CMD_WRITE`. The run ends
   only when every record verifies; the window is then held open
   (`window HELD open — verify/burn now, then Revert VRM or cold-boot`).
8. **Cold boot and re-dump.** Power-cycle so the fuse controller replays
   the new FF chain, then **⟳ Run full dump** again (re-unload the driver
   first if it re-bound).
9. **Verify against the ceiling.** `NOW (live)` topology should match
   `Intended (this card's defects)`; `SM now` should have moved toward
   `SM after unlock (fuse ceiling)`; `STATUS_OPT_GPC` / `STATUS_OPT_FBP`
   are the latch that proves the chain took effect (a bit-exact row
   readback does NOT prove the shadow followed). SMs that turn out bad
   after unlocking get re-disabled with records in the **SM reserve** zone.
10. **Anything looks wrong? Grab the Support bundle** (top bar) and attach
    it to your bug report — it carries the exact bytes and the
    interpretation trace.

### 1. Look at a card (read-only, zero risk)

1. Start the console and open it. The status cards tell you the fuse-block
   health (`CRC_STATUS == 0x55` = parses cleanly) and lock state
   (`DSOV = 1` = factory-locked, the normal state).
2. Press **⟳ Run full dump**. After a few seconds the row explorer fills
   in; filter to `FF records` to see every chain/block/data triple.
3. The dump is archived under `<state-dir>/dumps/sn-<serial>/<ts>/` — re-open it later
   with `python3 -m ga100vfi.console.gui <dump_dir> out.html`.

### 2. Glitch to Goldilocks (observe only)

1. **Glitch & Burn** tab → Target card: pick the GPU (the pill shows its
   live state; the serial identifies the physical card) and the pico port
   (dropdown, with **⟳ rescan**).
2. Choose the **v_dip strategy**: `adaptive 3D (v_dip · delay · pw)` is
   the default — it runs the 3D CRC-guided search over (v_dip, delay, pw)
   and converges on the card's window; `fixed v_dip` repeats one voltage.
3. Mode: `classify only — observe glitch states` — no burns.
4. **▶ Start campaign** and watch the log: every shot gets a line with
   its `v_dip` and outcome — `under`, `crc_fail`, `warm`, `hit`, `over`,
   `lost`, `poisoned`, or `goldilocks` — plus the per-attempt classify
   values. The
   adaptive planner steers from every outcome (see
   [docs/ADAPTIVE.md](ADAPTIVE.md)); a hit prints `<< GOLDILOCKS` and the
   goldilocks chip flips to `YES`. The hit is appended to
   `<state-dir>/goldilocks.jsonl` with the card serial.
   A **poisoned** fuse controller (FUSECTRL or DSOV reads `0xBADF____`)
   is its own outcome, never `over`: it is not a voltage data point,
   never reaches the planner, and **ends the boot** — poison persists
   until a POWER CYCLE, so shooting on is pointless. Status reads stop
   at a poisoned FUSECTRL too (further BAR0 reads on such a card are a
   host-hang risk). `classify()` no longer writes `EN_SW_OVERRIDE`
   after every shot (the write is opt-in via `CLASSIFY_WRITE=1`): the
   register keeps its value across PEX_RST and would leave every later
   shot of the boot under the software override — which also poisons
   CMD_READ fuse reads for the die-ID gate and fusedump.
5. **Goldilocks window hold (default):** the run ends with NVVDD still at
   glitch voltage and the shadow registers writable — a `window HELD open
   — verify/burn now, then Revert VRM or cold-boot` chip appears; close
   the window with **⟲ Revert VRM** or a cold boot. Choosing
   `auto-revert VRM` hands the VRM back on exit. Misses, stops, and errors
   always revert regardless — an interrupted run can never leave NVVDD low.
6. **■ Stop** ends a run early (the VRM is handed back). A stopped or
   exhausted campaign leaves the card in whatever state the last shot
   produced — re-run to try again.

### 3. Burn an FF record (the full sequence)

The full confidence sequence is **preview → check → arm → burn →
predicted-vs-actual**.

Prerequisite: a record derived from **this card's own defect masks** —
never blind ffcalc output, and never a payload copied from another card.
Plan against the placement policy: the row map shows the safe zone and the
row field shows the zone verdict for whatever row you type.

1. **Burn payload**: pick the **target row** (blank, inside the safe
   zone). For the value, type it or use **from dump row** (preferred —
   re-applying an existing record at a later row is exactly how you
   override a block: last record wins). Press **Preview burn
   (read-only)** first. It works ANY time, even on a cold-booted card
   outside any window, with no arm and no token (`CMD_READ` is gated by
   `FUSECTRL_PLM`, not `EFP`), and issues **zero fuse writes**: the server
   path receives a handle whose writes are restricted to the `CMD_READ`
   controller path and raises on anything that could latch. The panel
   shows:
   - `before → Δ → after` per row (mirror included) with the delta bits
     highlighted on the bit strip;
   - both words decoded as FF records (`chain/iff/block/data` + known
     block names) when the row is in the FF region;
   - a **collision scan**: every existing record with the same
     `(chain, block)` key, row-numbered, with a LAST-WINS verdict badge —
     `LAST-WINS: will win`, or red *will LOSE to row N* (the burn would be
     **inert**; correct it by burning a later row); a same-key record at
     exactly a burned row is captioned *record already present at this
     row — re-burn is a no-op/ALREADY path*;
   - **partial-landing hazards**: every subset of the delta that, if only
     it latched, would win its `(chain, block)` key with data different
     from the intent — advisory only, never a gate; effects are relative
     to the burned row's effective winner (baseline stated) and every burn
     row (mirror included) is analyzed; skipped above 12 delta bits;
   - the **predicted effect** line when decodable (e.g. `FBP_DISABLE data
     0x4290 → 0x4200 (unmasks FBP1/FBP4)`) — `STATUS_OPT_*` shadows update
     only after a power cycle;
   - a read-only window / arm-pending / journal status strip.
   Verdict banner: `SAFE TO BURN` (green) / `WILL BE INERT` (red) /
   `IMPOSSIBLE` (red, bits would clear) / `ALREADY BURNED` (amber).
   Preview is also the one burn-adjacent feature that works in `--mock`
   mode (read-only over the mock rows).
   Then press **Check row & guards**. The result shows the row's current
   value, the 0→1 purity, the **placement policy verdict** (`placement
   policy: OK — row is in the safe burn zone` / `VIOLATION`; bit-5/IFF
   values are refused), and the **burn window** checks (top-line
   `SAFE TO BURN` / `REFUSED`). `EFP`, `PROGRAM_DIS`, `SBFE`,
   `WDATA_SECURE` and `FUSEWDATA_PLM` are shown amber as *arm pending* —
   they read closed outside a burn by design and are opened at burn time
   by the SENSE_CTRL arm sequence; they never block the check.
2. Type `BURN` into the arm field and press **Arm (120 s)**. The button is
   disabled while the GPU in the target selector is not Goldilocks
   (tooltip `selected GPU not Goldilocks — glitch first`); the server
   re-runs the same 4-check pure-read at arm time and refuses with the
   failing checks named if the state changed between poll and arm. The arm
   pill counts the token down (`● armed Ns`).
3. Campaign card: mode **burn payload on first Goldilocks**. (The burn
   runs *inside the campaign process* because the Goldilocks PCIe window
   dies seconds after the campaign loop returns — a separate burn call
   would miss it.)
4. **▶ Start campaign**, confirm the dialog (it repeats the exact rows,
   values, mirror and target). The campaign glitches; on the first
   Goldilocks it burns the records in-process: each burn re-checks the
   driver-unbound state, journal, GPIO19 preflight and window, runs the
   SENSE_CTRL arm sequence, the EN=1 + GPIO19/TRIGGER program bracket with
   `CMD_WRITE` of the **delta**, and read-back verify logged as
   `row N: VERIFY OK` (a row already latched by an earlier aborted run
   logs `ALREADY BURNED` and still counts as success). The campaign ends
   only when EVERY record succeeds AND — for ≥2-record burns — the whole
   burned image re-reads correctly twice; a burn `ABORT` or
   `IMAGE VERIFY FAILED` is logged and is NOT final — attempts keep
   firing and the window is not held.
5. **Predicted vs actual**: a standalone burn that reaches `VERIFY OK`
   re-reads the burned row(s) and re-runs the collision scan
   (`after_state` in the report). If you ran a Preview of the same payload
   first, the burn report shows a **Predicted vs Actual** table: the
   preview's after-word and LAST-WINS verdict against the post-burn
   readback and post-burn scan — any mismatch is red. Both the last
   preview and the last burn report are stored in the state dir
   (`last-preview.json`, `last-burn.json`, served by `/api/burn/last`).
6. Cold-boot the card, then verify honestly — step 9 of the end-to-end
   workflow.

## Reading the UI

| Indicator | States and meaning |
|---|---|
| live bar pill (top of the status rail) | `● live — <time>` polling fine · `⏸ driver '<driver>' bound — raw BAR0 live view disabled (Drivers tab -> Unload nvidia stack to resume)` (paused, driver bound) · `⚠ service unreachable` page lost the server · `BAR0 unreadable — bus hung or PCIe link down (normal mid-glitch / after reset)` — **normal mid-glitch** |
| activity feed | timestamped register changes; flashes the matching card |
| target GPU pill (Glitch & Burn) | `● Goldilocks — glitch window` (4-check read-only approximation) · `locked (DSOV=<n>) — glitch first` · `⚠ <error>` · `no GA100 detected` |
| burn window pill | `● burn window open` · `burn window closed (<failed checks>)` · `window: n/a` — read-only verdict from `/api/live` (`window_ok` + `window_checks`) |
| serial pill | `SN <serial> · driver <name>` — identifies the physical card |
| empty state (Fuse Explorer) | `No GA100 present — nothing live to show.` · `No dump yet for this card (serial X).` — dump-derived panels hidden until the card's own dump exists or the picker is used; carries the **Browse saved dumps** button |
| Browsing saved dump strip | `Browsing saved dump — serial X, dumped <ts>` + **← Back to current** — shown while a dump picked from the Saved dumps list is on screen; panels dimmed, header meta prefixed `SAVED DUMP OF … — browsing saved dump` |
| row hint | `✓ safe zone` · `✗ occupied (boot FF)` · `✗ buffer zone` · `✗ SM reserve (keep free)` · `✗ revert tail (keep free)` · `✗ outside FF region` |
| value source decode | `dump row N → 0x…` + decoded FF ch·blk·data (with block names) — verify before Check · blank/missing rows warn · IFF records flagged |
| Preview burn button | enabled whenever row+value are set — **no window/arm/token requirement** (read-only works on a cold card and in mock); panel: verdict banner `SAFE TO BURN`/`WILL BE INERT`/`IMPOSSIBLE`/`ALREADY BURNED`, before→Δ→after with delta bits highlighted, FF decode table, LAST-WINS collision badge (green win / red lose), amber hazard list, predicted effect, window/arm/journal strip |
| burn selection badges / pill | per-word checkboxes on all three burn lists; pill `N of M word(s) selected`; badges `ALREADY PRESENT (row N) — no burn needed` (green, word defaults UNticked) · `SUPERSEDED at row N — needs re-burn` (amber, stays ticked) · advanced items `ALREADY PRESENT — no burn needed` / `PARTIALLY PRESENT (k/n: …)`; queue tag `⚠ already present — likely no-op (row N)` (amber) — presence judged LAST-WINS, see *Per-burn selection* |
| budget pill | safe zone rows, free count, last boot FF row |
| arm pill | `● armed Ns` (countdown) · `not armed` · red = refused (bad phrase or server Goldilocks refusal, failing checks named) — the refusal stays visible until the phrase is edited or an arm succeeds |
| Arm button | disabled until the current poll of the **selected** GPU says Goldilocks (tooltip `selected GPU not Goldilocks — glitch first`); re-evaluated on poll refresh and GPU-dropdown change; the server re-runs the 4-check pure-read at arm time |
| Burn now button | enabled only when checked **and** armed **and** the burn window verdict is open (`window_ok`; EFP/WDATA_PLM do not gate it) |
| campaign pill | `● running` · `goldilocks` · `stopped` / `exhausted` · `error` · `idle` |
| stats chips | attempts / valid / lost / nack / poisoned / dsov=0 / goldilocks / burn aborts (not final — attempts keep firing) / image verify failed (window NOT held) / `window HELD open — verify/burn now, then Revert VRM or cold-boot` |
| burn report | result line: `VERIFY OK` green · `ALREADY BURNED` amber (partial-run recovery, zero latching writes) · `ABORT` / `VERIFY FAIL` / `IMAGE VERIFY FAILED` red; journal-uncertain → explicit confirm before retrying with `ack_uncertain`; `VERIFY OK` adds `after_state` + the Predicted vs Actual table when a matching preview was run |

## Burn safety model (reference)

> **WARNING — FUSE BURNS ARE PERMANENT AND CAN BRICK YOUR GPU.** Every burn is
> an irreversible one-time-programmable write: a wrong or malformed record can
> leave the card unbootable or unusable **forever** — there is no undo, no
> reflash, no recovery for many mistakes. **It is entirely YOUR responsibility**
> to verify what you burn — use the read-only Burn Preview, the guard checks,
> readbacks and your own research before arming. **The developer accepts NO
> responsibility** for bricked cards, damaged hardware, lost work or any other
> consequence of using this tool. You are modifying your own hardware at your
> own risk.

Every burn — standalone or in-campaign — passes ALL of these, re-verified
server-side immediately before `CMD_WRITE`:

1. **Arm token**: typed phrase `BURN`, 120 s TTL.
2. **Driver unbound**: the target must have no driver bound (same sysfs
   source as the Drivers tab) — mirrors `bar.require_unbound()`; a bound
   driver aborts before any write.
3. **Journal resolved**: an unresolved `command_may_be_issued` in
   `burn_journal.jsonl` (see below) aborts with `journal_uncertain` until
   the request carries `ack_uncertain: true` (the GUI shows an explicit
   confirm dialog).
4. **GPIO19 preflight** (mirrors `ga100_burn.preflight`): `GPIO (0xD65C)`
   must read with normal mux (`& 0xFF == 0`), non-inverted push-pull and
   low latch (`& (0x1000|0x8000|0x40000) == 0`); failure aborts with the
   failing value in the report, before any write.
5. **Pure 0→1 transition**: new value must be a superset of the current row
   value (OTP physics — bits can only be added).
6. **Row state**: the row must currently read exactly the expected old
   value; any drift aborts — **except** a row that already reads exactly
   the intended value (`ALREADY BURNED`): that counts as success with zero
   latching writes, so a mirror pair aborted halfway can still complete.
7. **Burn window** (static, read-only — mirrors `ga100_burn.check_window`):
   `DSOV == 0`, `CRC_STATUS == 0x55`, loader `0x120060 == 0`,
   `FUSECTRL_PLM`/`PRIV_MASK` open, `DEBUGCTRL == 0`, `SWIFF == 0`,
   `IFF_CTRL == 0`, `FUSECTRL` idle (state bits[1:0]==0, stage[20:16]==4).
8. **Arm sequence** (mirrors `ga100_burn.arm`, executed ONLY inside the
   burn itself): if `EFP != 1`, issue `SENSE_CTRL` (`FUSECTRL = 3`, poll to
   idle ≤2 s, at most once per burn attempt — no retry) and re-check the
   window (a failed re-check is fatal); then require `EFP == 1` and
   `PROGRAM_DIS == 0`; write `WDATA_SECURE = 0` and `SBFE = 0`; then require
   `FUSEWDATA_PLM == 0xFFFFFFFF`. The poller, `/api/live` and fusedump
   never touch the write path at all; the burn check issues only
   `CMD_READ` (`FUSEADDR`/`FUSECTRL`) and conditionally clears/restores
   `EN_SW_OVERRIDE` for the read — it never issues SENSE, never writes
   `FUSEWDATA`, never raises `EN_SW_OVERRIDE`, and never touches
   `GPIO`/`TRIGGER`. A static `EFP == 0` or closed `FUSEWDATA_PLM`
   is normal outside a burn and must not block the check or the burn.
8a. **Preview** (`/api/burn/preview`, mirrors `ga100_burn`'s default
   preview mode) is structurally read-only: it receives a card handle
   whose writes are restricted to the `CMD_READ` controller path
   (`FUSEADDR`, `FUSECTRL = CMD_READ`, `EN_SW_OVERRIDE` clear/restore)
   and RAISE on anything that could latch (`FUSEWDATA`, `GPIO`/`TRIGGER`,
   `WDATA_SECURE`/`SBFE`, `CMD_WRITE`/`CMD_SENSE`). It never SENSEs,
   never arms, needs no token — `CMD_READ` is gated by `FUSECTRL_PLM`,
   not `EFP`, so the preview works on a cold-booted card. It reads the
   FF pool (rows 222–487, stopping at the first IFF record), decodes
   `chain=word[4:0] iff=bit5 block=word[15:6] data=word[31:16]`, and
   applies the controller's last-record-per-(chain,block)-wins rule to
   flag inert burns and partial-landing hazards.
9. **Program bracket** (mirrors `ga100_burn.program` per row): fsync'd
   journal `command_may_be_issued`; raise `EN_SW_OVERRIDE = 1` with
   read-back check (no retry); `GPIO19` high + `TRIGGER (0xD604)` pulse
   (masked write `0x30FF`, poll `TRIGGER` bit0 clear ≤2 s); `FUSEADDR = row`,
   `FUSEWDATA = delta` (**delta = value & ~current**, not the full value —
   same as the reference), `FUSECTRL = CMD_WRITE`, poll to idle; then in
   `finally`: `GPIO19` low + `TRIGGER` pulse, restore the saved `GPIO` and
   `EN_SW_OVERRIDE` values. `GPIO`/`TRIGGER`/`EN=1` writes exist ONLY in
   this bracket.
10. **Read-back verify** with `EN_SW_OVERRIDE` cleared for reads, then a
    journal `verified` event.
11. **Whole-image verify** after a multi-record burn (≥2 rows succeeded,
    incl. a mirror pair): every burned row is re-read twice and compared to
    the intended values; a mismatch reports `IMAGE VERIFY FAILED` — the
    campaign does NOT hold the window and does not claim success.
12. **Placement policy**: blank row inside the safe zone (see below).
13. **No retries**: any window/arm/latch/verify failure aborts; nothing
    is retried blindly.

### Burn journal

`<state-dir>/burn_journal.jsonl` — fsync'd JSONL, mirroring
`ga100_burn.Journal`: `command_may_be_issued` (`ts`, `bdf`, `row`,
`before`, `delta`, `after`) is written **before** `EN_SW_OVERRIDE = 1` can
latch anything, and `verified` after the read-back matches (or the row is
`ALREADY BURNED`). A burn that dies between the two leaves the journal
uncertain; the next burn refuses to start (`uncertain burn state — resolve
journal`) until a human resolves it or explicitly acks
(`ack_uncertain: true`).

### FF placement policy (hard-enforced)

The FF record region (rows 222–487) is laid out and enforced live
(`/api/ff/layout`; the Glitch & Burn tab renders it as a row map):

```
| boot FFs (occupied) | buffer | BURN ZONE | SM re-disable reserve | revert tail |
```

- **Burn only into blank rows** in the FF region — occupied rows, the main
  array and the FPF region are refused.
- **IFF records are refused outright**: bit 5 of an FF word is the
  invalidation flag. A value with bit 5 set is not a chain/block/data
  record — a stray IFF can truncate the FF pool (a canary burned as
  `0x00010020` read back as IFF chain=0 iff=1). The check applies to the
  value and its mirror on every burn path.
- **Placement is PER BLOCK last-wins** when the burn value is known (every
  queue/proposal path, and any checked burn): the controller replays FF
  records in row order and the LAST record per block wins, so a new record
  for block B (`block = bits[15:6]` of the word) must land in a blank row
  **strictly after the last row holding a record for block B** —
  `last_row_for_block` in `/api/ff/layout` and in the `ff_layout` embedded
  in `/api/dumps/get`; a block with no history starts at row 222. IFF
  words (bit 5 set) are invalidation markers, not block records, and never
  bound placement. This is what lets an already-burned card — records
  scattered to the end of the region — still place new records in its
  blank rows instead of collapsing the burn zone. The allocator places
  each word per block; a word whose own block has no free row is refused
  per word (`NO FREE ROW FOR BLOCK B`, other words still get rows).
- **The global zones are a display heuristic and the fallback rule** when
  no value is known (a bare row check): a buffer (default 4 rows) after
  the last boot FF, a BURN ZONE up to the SM re-disable reserve (default
  16 rows) and the revert tail (default 12 rows) kept empty — a wrong
  value can only be corrected by burning a *later* record, so the tail is
  your correction budget and attempts are finite. On a card where the
  burn zone would collapse (start past its end) the layout reports the
  canonical empty range `[zone_end + 1, zone_end]` with
  `global_zone_empty: true` — never an inverted range — and the budget
  pill says placement is per-block.
- The budget pill shows how many safe rows remain; burns refresh it.

Reserves are tunable per deployment: `--ff-buffer`, `--ff-tail-reserve`,
`--ff-sm-reserve`.

FF records live at rows **222–487** (`chain = bits[4:0]`, `iff = bit 5`,
`block = bits[15:6]`, `data = bits[31:16]`; last record per block wins).
The check UI warns when a target row is outside that region — burning
record-format values into the main array / FPF region is how cards get
bricked.

## Driver-bound guarded capture

The live poll pauses while `nvidia` is bound, but fuse values still change
under you (a burn elsewhere, a glitch). The paused panel therefore offers
a manual **Capture fuse dump (driver bound)** — a guarded reader ported
from the proven standalone collector (`ga100_dump.py`), which reads fuses
with the driver bound by gating on hardware *state*, not driver presence.
The panel can be collapsed to a one-line bar (**Expand ▾** / **Collapse
▴**) that keeps showing the age of the last complete dump.

**Consent flow**: the button first runs a read-only preflight and shows
every condition with its read value, expected value and fix hint, plus
what the capture will do; the **Capture now** button is enabled only when
every condition passes (`fix the failed conditions first` otherwise).

![Driver-bound capture consent panel — preflight conditions with read
values and the gated Capture now button](images/console-capture-consent.png)

**Preflight conditions** (all read-only; the capture itself re-runs them
and refuses with `preflight refused: <names>` + the failed conditions):

| Condition | Expected | Fix hint when it fails |
|---|---|---|
| `PMC_BOOT_0` chip id | GA100 (`0x170`) | wrong card or BAR0 garbage |
| `FUSECTRL_PLM` (`0x8200F8`) | `0xFFFFFFFF` | PLM locked — run the PLM unlock first |
| `DEBUGCTRL` (`0x820060`) | `0` | controller debug/read mode nonzero — investigate first |
| `SWIFF` (`0x820088`), `IFF_CTRL` (`0x820028`) | `0` | fuse loader transaction pending — wait/retry |
| `FUSECTRL` state field | `4` (idle) | controller busy — wait, then retry |
| `EN_SW_OVERRIDE` (`0x820040`) | `0` or `1` | software override set — physical reads need it disabled |
| `FUSEADDR` (`0x820004`) | `< 512` | address counter out of range |

**What the capture does** (shown in the consent panel): issues 512 fuse
`CMD_READ`s ×2 passes (the two passes must agree — `Physical fuse read
passes disagree` otherwise), writes **only** `CTRL`/`ADDR`/`EN` — never
PLM, SWIFF, GPIO or voltage — restores the controller's `ADDR`/`EN` in a
`finally` block, snapshots the whole fuse aperture (0x820000..0x826000)
before and after, and takes seconds. It refuses if the driver unbinds
mid-flight or the host boot id changes.

**UNVERIFIED semantics**: every result is labelled `UNVERIFIED (driver
bound)` — in the result panel, in the saved `dump.json`
(`driver_bound` / `verified` markers), and in the support bundle's
`interpretation.txt`. The reads are the same physical path the
driver-unbound dump uses, but they run with the driver loaded, so treat
them as indicative until re-confirmed with the driver unbound. The saved
dump lands in the normal dumps dir, so the Fuse Explorer, interpretation
trace and support bundle all pick it up like any other dump.

## Dump identity: serial, not BDF

A PCIe address is a transport, not an identity: cards get swapped and
slots change between boots. Dumps are therefore keyed by the card's
**board serial**:

- Every dump (full and guarded) records `serial` + `serial_source` in
  `dump.json`. Source matrix: driver unbound → InfoROM BRD object read
  through BAR0 (`inforom`); driver bound (guarded capture, paused live
  view) → `nvidia-smi --query-gpu=serial --id=<bdf>` (`nvidia-smi`);
  unreadable → `serial: null`, `serial_source: "unavailable"`.
- Storage: `<state-dir>/dumps/sn-<SERIAL>/<timestamp>/dump.json`
  (`bdf-<bdf>/<timestamp>/` when the serial is unreadable). Existing
  dumps on disk are never moved: resolution walks the whole tree, so the
  historical `dumps/<timestamp>/` and `dumps/<bdf>/<timestamp>/` layouts
  keep working side by side with the new ones.
- "Current card" resolution: the newest dump whose recorded serial
  matches the serial of the card present now. When there is none, the
  paused hint and bundle say **`no dump yet for this card (serial X)`**
  instead of silently showing the previous card's dump; dumps recorded
  under another serial stay listed but are labelled
  `different card (serial Y)` (support-bundle manifest `dumps[].card`).
- The GUI header shows the loaded dump's serial (`SN <serial>` or
  `no serial`), and the last-dump age in the driver-bound panel counts
  same-serial dumps only.
- **Stock baseline**: the first dump saved for a serial also seeds
  `dumps/sn-<SERIAL>/stock.json` — that card's `STOCK` reference for the
  topology/TPC state views, served by `/api/stock`. Written once
  (`O_EXCL`, never overwritten) with `stock_provenance`
  `first dump seen for this serial at <ts>`; only full dumps seed it
  (driver-bound guarded captures are UNVERIFIED). A card modified before
  this console first saw it has stock = state at first sight — the
  provenance line is what it claims, nothing more.

- **Identity gate at burn time** (die-ID witness): serials key the dump
  archive, but a serial is a *label* — InfoROM is writable, and a failed
  read used to degrade silently to a BDF fallback. A burn therefore also
  reads the **die ID** — fuse rows 8–15, factory OTP per die, never
  touched by any burn in our plans — through the same fuse macro the burn
  uses (`CMD_READ`, two passes, unstable reads refuse; `EN_SW_OVERRIDE`
  cleared and restored around the reads, `FUSEADDR` restored). The live
  rows must match the dump the payload is sourced from (the shown dump in
  the GUI; else the newest same-serial dump carrying rows 8–15). Enforced
  at `/api/arm`, at burn execution and at burn-mode campaign start;
  `burn_check` reports it. Refusals name **row numbers, never values**.
  No saved dump for the serial → pass with a "nothing to compare" note
  (first burn for that serial); an explicitly selected dump *without*
  rows 8–15 fails. A serial read failure now refuses the burn outright —
  **no BDF fallback for burns** — and failed serial reads are no longer
  cached, so a retry can succeed. Mock bench: vacuously satisfied.

Saved-dump views are labelled by serial and presence state, never left
masquerading as live. The default face resolves current-card-only (task
23): the page seeds the present card's own newest dump — card-less or
without a same-serial dump it shows the empty state with a Browse saved
dumps affordance instead of auto-rendering another card's dump. History
is explicit: the header **Saved dumps** picker (`/api/dumps`,
`/api/dumps/get`) loads a chosen dump under the stale chrome — dimmed
panels and the strip `Browsing saved dump — serial X, dumped <ts>` plus
**← Back to current**, which restores the default resolution. The
auto-labels from task 22 still guard anything else that ends up on screen
mismatched: the header meta line is prefixed `SAVED DUMP OF` and suffixed
`— card not present` / `— different card present (serial Y)` /
`— browsing saved dump`; the amber strip above the dump-derived panels
names the source, and those panels are dimmed with an amber left rule.
When the displayed dump's serial matches the present card, nothing
changes (present-tense is honest).

Hard BDF validation goes with it: every BAR0-touching path first reads
`/sys/bus/pci/devices/<bdf>/{vendor,device}` and requires
`0x10de` + a GA100 device ID (`fusedump.require_ga100`) before any mmap
or write. `--bdf` / `CFG["bdf"]` is only a *preference* among detected
cards (`effective_bdf`), never a ghost address: when no GA100 is
detected, the dump endpoints answer **409 `{"error": "no GA100 present
on this host"}`** — the same words the poll loop uses — instead of
resurrecting the pinned address. (A pinned BDF pointing at an AMD dummy
function took fuse CMD_READ *writes* after a card swap and rebooted the
host — owner, 2026-11-23.)

With that same validation gate goes **BAR auto-enable**: on a fresh cold
boot with no driver bound the kernel leaves PCI `COMMAND` memory-enable
(bit 1) clear — `lspci` shows `Region 0 … [disabled]` and BAR0 reads
return garbage (AI2, 2026-11-23). Before mapping BAR0 of a
`require_ga100`-validated device the console sets that bit itself
(`bar0.ensure_mem_decode`, config-space write via
`/sys/bus/pci/devices/<bdf>/config`, one log line per write, idempotent).
Non-GA100 functions are never touched; if the write fails or BAR0 stays
unreadable the honest `BAR0 unreadable` error path is unchanged.

## HTTP API (reference)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | the tabbed GUI (generated `live.html`) |
| GET | `/api/live` | fast probe (pure reads); JSON includes `tpc` — per-GPC TPC/SM summary (`gpcs[]` + `totals`) — the read-only burn-window verdict `window_ok` + `window_checks` (check-dict list, no writes, no SENSE), and the provenance block `version` (`tool_version` / git sha / `fingerprint`), plus `readouts` (`GFW_BOOT`/`FEAT_READOUT_1` raw values + Allspark interpretations with `source` tag [The Lab / allspark, unverified on our silicon]) and the read-only `never_write` reference list (mock snapshots get synthetic readout values). While the driver is bound it returns the `paused` snapshot (+ `paused_hint`, `manual_dump_available`, `last_dump_age_s` — same-serial dumps only —, `serial`, `serial_source`, and `last_dump_note` `no dump yet for this card (serial X)` when none). `?bdf=` probes another GA100 on demand (same never-probe-while-bound rule) |
| GET | `/api/full` | full row dump + hex window; `409 {"error": "no GA100 present on this host"}` (or `no GA100 at <bdf> (found …)`) when the target is absent or not GA100 silicon — no ghost-BDF fallback; saves `dump.json` under `dumps/sn-<serial>/<ts>/` (`bdf-<bdf>/<ts>/` when the serial is unreadable) and returns `serial`, `serial_source`, `dump_dir` |
| GET | `/api/dumps` | saved-dump history listing, newest first: `[{dir, serial, dumped, driver_bound, verified, row_count, current}]` over every stored layout; `current` = dump of the card present now; a dir whose `dump.json` can't be read or parsed lists as `{dir, unreadable}` instead of failing the listing |
| GET | `/api/dumps/get?dir=<rel>` | one `dump.json` by `dumps_dir`-relative path (+ `dump_dir`, + `ff_layout` — the zone layout derived from that dump's rows with the same zone math as `/api/ff/layout`, so the GUI names exact burn rows while browsing saved dumps with no card); `404` unless the path resolves inside the dumps store (no `../` escape, no absolute path), `422` when the JSON is corrupt |
| GET | `/api/stock` | the PRESENT card's stock baseline: `{serial, stock, provenance, is_current}` — `stock` is the card's first-saved dump (`dumps/sn-<serial>/stock.json`, + `stock_provenance`); `stock: null` with a `reason` when no GA100 is present (`no GA100 present on this host`), its serial is unreadable, or no baseline is recorded yet (`no stock baseline recorded yet — this dump is the first record`) |
| GET | `/api/ports` | serial ports present on the host (pico selector), each with `vid`/`vendor`/`product`/`pico`; `default` = first Pico, else first device, else `null` (no phantom) + `note` when no Pico among them |
| GET | `/api/gpus` | all GA100 GPUs with live Goldilocks state + serials; `default` = effective BDF (configured one if present, else first detected GA100, else `null`) + `default_note` on fallback |
| GET | `/api/gpus/all` | every GPU on the host (nvidia-smi + GA100 PCI scan), driver per BDF |
| GET | `/api/ff/layout` | FF region occupancy + policy zones |
| GET | `/api/glitch/status` | campaign stats + log tail |
| POST | `/api/glitch/start` | start campaign (`bdf`, `mode: classify\|burn`, `adaptive`, `min_v`/`max_v`, records, `no_revert` — default **true**: a Goldilocks result holds the window open; `ack_uncertain`) |
| POST | `/api/glitch/stop` | stop campaign |
| POST | `/api/revert` | manual VRM hand-back — closes a held window (refused while a campaign owns the pico) |
| GET | `/api/burn/check?row=&value=&mirror=&bdf=` | dry burn check: window checks (`window_ok`/`guards`) + `arm_pending` (EFP/PROGRAM_DIS/SBFE/WDATA_SECURE/FUSEWDATA_PLM, `ok: null` — auto-armed at burn via SENSE_CTRL) + `policy` verdict + `pure_0to1` + `two_layout` (RIR-layout decode of the candidate word: `rir_enabled`/`rir_row`/`rir_bit`/`rir_targets_control_rows_0_7`/`rir_layout_warning` — WARNING only, never a gate; [The Lab / allspark, unverified on our silicon]) |
| POST | `/api/burn/preview` | **read-only** burn preview (same body as `/api/burn` minus token/confirm; no window/arm needed, works in mock): `verdict` (`SAFE TO BURN`/`WILL BE INERT`/`IMPOSSIBLE`/`ALREADY BURNED`), `rows[]` (`before`/`delta`/`after` + FF decode before/after), `collisions` (same-key records + LAST-WINS verdict), `hazards` (partial-landing subsets per burn row, mirror included, capped at 12 delta bits; effects relative to the burned row's effective winner), `predicted` effect line, `window_ok`/`arm_pending`/`journal_uncertain`, `two_layout` (RIR-layout decode + `rir_layout_warning` when the word read as an RIR record lands enabled in control rows 0–7 — warning only, never a gate; [The Lab / allspark, unverified on our silicon]); stored as `last-preview.json`; `VERIFY OK` burns add `after_state` (readback + post-burn collision rescan) |
| GET | `/api/burn/last` | last stored preview + last burn report (`last-preview.json` / `last-burn.json` in the state dir) — the predicted-vs-actual store |
| POST | `/api/burn` | burn (needs `confirm: true` + arm token + open burn window; **identity gate re-checked at execution** — `identity gate: …` refuses before any write; window+arm checks land in `guards`; journal at `<state-dir>/burn_journal.jsonl`; unresolved journal → `journal_uncertain` + ABORT unless `ack_uncertain: true`; results: `VERIFY OK` / `ALREADY BURNED` / `VERIFY FAIL` / `ABORT …` / `IMAGE VERIFY FAILED` (mirror pair)) |
| POST | `/api/arm` | `{phrase: "BURN", bdf?, dump?}` → 120 s token **gated on the target GPU's Goldilocks state** (body `bdf` else `effective_bdf`; same 4-check pure-read as `/api/gpus`) **and on the identity gate** (serial readable + live die-ID rows 8–15 match `dump` — a dumps-relative dir, else the newest same-serial dump; see "Dump identity"): not Goldilocks → error `GPU <bdf> is not Goldilocks — failing: <checks>`, no token; identity failure → error `identity gate: …`, no token; success adds `bdf` + `checks` dict + `die_id` verdict |
| POST | `/api/dumps/dedupe` | `{apply?}` — drop saved dumps whose **fuse content** is identical to another dump of the same card: same serial + same rows dict (timestamps/dmesg/lspci ignored). Each identical group keeps its **oldest** dump; anything different — one differing row, another card's serial, a dump without a rows dict — is kept. Dry-run by default; `apply: true` deletes. Never touches `stock.json`; the die-ID gate still resolves (the kept dump carries the same rows). GUI: **Dedupe** button in the Saved dumps picker (dry-run panel → confirm) |
| POST | `/api/pico/flash` | `{port?, uf2?}` — flash firmware into the Pico 2 from the console: sends `b` to the pico port (the firmware's own BOOTSEL reboot; skipped when a BOOTSEL drive is already up), waits for the RP2350/RPI-RP2 mass-storage, mounts it, copies the `.uf2` (drive auto-detaches, board reboots), then **reads the firmware banner back** over the port and reports `fw_marker`. The console host needs no toolchain — build the `.uf2` on a workstation and drop it at `<repo>/firmware/build/pwmvid.uf2` (or the state dir); `uf2` overrides the path. GUI: **⚡ Flash Pico 2** button next to the pico port dropdown |
| GET | `/api/driver` | driver state |
| POST | `/api/driver/op` | `blacklist\|unblacklist\|load\|unload` (`blacklist`/`unload` need `confirm: true`) |
| GET | `/api/gpu` | nvidia-smi + lspci link state (`?bdf=` any GPU on the host) |
| GET | `/api/dmesg` | live GPU-relevant dmesg tail (nvidia/NVRM/Xid + card slot) |
| GET | `/api/bound_dump/preflight` | driver-bound capture preflight (pure reads): `{conditions[], all_ok}`; each condition `{name, ok, value, expected, hint}`; `503 {"error": ...}` when BAR0 is unopenable; mock mode returns a synthetic `all_ok` block flagged `"mock": true` |
| POST | `/api/bound_dump` | guarded capture with the driver **bound** (manual, consented): saves `dump.json` (with `serial` read via nvidia-smi) + `driver_bound` / `verified` markers under `dumps/sn-<serial>/<ts>-bound/` and returns the `tpc_summary` interpretation with `verified: false` + `serial`; preflight refusal → `409` + `conditions`; no GA100 present → `409` |
| GET | `/api/support_bundle` | `tar.gz` download: logs + newest dumps + live snapshot + lspci/dmesg + nvidia-smi snapshot + interpretation trace (per-dump header names `serial` + source); manifest carries `current_card` (`bdf`/`serial`/`serial_source`) and `dumps[]` with per-dump `serial` + `card` label (`current card` / `different card (serial Y)` / `serial not recorded in this dump`) |

POST bodies are JSON. Multi-GPU: burns target a specific GPU (`bdf`); the
UI only enables the standalone burn while the burn-window verdict is open
(`window_ok`), and the server-side window+arm sequence enforces it
regardless. GPU-list endpoints (`/api/gpus`, `/api/gpus/all`) return
`default` = the **effective** BDF: the configured one when present, else
the first detected GA100 (`null` when none is), with `default_note`
`default_note` explaining the fallback; `/api/live` and `/api/driver` carry the same
`default_note`. An empty/absent `bdf` in burn/glitch/dump requests
resolves to the effective BDF among **detected** GA100s — never to an
absent configured one: every BAR0-touching endpoint first verifies
sysfs vendor/device (`fusedump.require_ga100`) and answers
`{"error": "no GA100 present on this host"}` (409 on the dump endpoints,
`error` elsewhere) when nothing GA100 is on the bus. The
pico port is a dropdown populated from the host's serial devices
(`/dev/ttyACM*`, `/dev/ttyUSB*`, with `/dev/serial/by-id` names when
available). Each entry carries `vid`/`vendor`/`product` read from sysfs
and `pico: true` when the USB vendor is Raspberry Pi (`0x2e8a`) or the
by-id name names Raspberry Pi; Raspberry Pi devices sort first in the
dropdown with a `(pico)` suffix. `default` is the first Pico, else the
first device, else `null` — never a phantom port; `null` renders a
disabled `no pico detected` option and gates campaign start until a
rescan finds a device. A `note` is returned when serial devices exist
but none is a Raspberry Pi.

### Network exposure

There is no login. The default bind is `0.0.0.0` (LAN browsing — pass
`--listen 127.0.0.1` for host-local use, then reach it through
`ssh -L 8790:localhost:8790 <host>`). Two browser-specific attacks are
refused regardless of the bind:

- **DNS rebinding**: the `Host` header must be `localhost`, loopback, or an
  IP literal — a rebound domain name is rejected with 403.
- **Cross-site (CSRF) POSTs**: a browser's `Origin` must match the `Host`
  (a `text/plain` JSON POST is a CORS "simple request", so this is what
  stops a malicious page from driving `/api/glitch/start` or
  `/api/driver/op` against your console).

Non-browser clients (curl, scripts) send no `Origin` and are allowed. Run
on a trusted network or front it with your own auth proxy.

## Submitting a support bundle

The header **Support bundle** button (or `GET /api/support_bundle`)
downloads one `tar.gz` built fully in memory — everything a developer needs
to reproduce an interpretation bug on *your* card without logging into your
machine; a failure anywhere returns a JSON error, never a partial archive.
It contains, under `support/`:

- `manifest.json` — tool version, git SHA and source (may be `null`
  outside a git checkout), 12-hex tool fingerprint, build time (UTC),
  host hostname/kernel/python, the BDFs involved, the member list with
  sizes, and any truncation/warning notes. The bundle is
  **self-describing**: `tool_version` + `tool_fingerprint` (sha256 over
  the shipped bytes of `version.py`, `fusedump.py`, `console/service.py`
  and `console/gui.py`) pin the exact build even when the files were
  copied out of git and no SHA is resolvable — match the fingerprint
  against the repo. A `.git_sha` file next to the package adds exact-SHA
  precision but is optional, not required. The same version block is
  served at `/api/live` under `version`.
- `console.log`, `goldilocks.jsonl` and `last-preview.json` (tail 2 MiB
  each) — the console's own working logs; missing files are listed in
  `warnings`, not fatal.
- `dumps/<…>/dump.json` + `hex_window_0x820000.txt` for the newest
  5 dump dirs (oldest first). If the total would exceed 25 MiB the oldest
  dumps are dropped and listed in `truncated`.
- `live_snapshot.json` — the same snapshot `/api/live` serves right now
  (a `paused` or `error` body while the driver is bound is normal).
- `system.txt` — `lspci -nn -vv` stanzas for the GA100 device IDs
  (`[10de:20c2]`/`[10de:20b5]`/`[10de:2082]`) and the GPU-relevant
  `dmesg` tail.
- `nvidia_smi.txt` — `nvidia-smi` snapshot (index, name, serial, VBIOS,
  driver, compute cap, clocks, power limit, PCIe link) for the
  console's BDF; SM count is not an nvidia-smi query field — read it from
  `live_snapshot.json` / `interpretation.txt` instead. States
  `driver unbound — nvidia-smi not applicable` when the nvidia module is
  absent (calling nvidia-smi then would auto-load the driver).
- `interpretation.txt` — the **interpretation trace**: for every bundled
  dump, `fusedump.tpc_summary(shadow, hexnonzero)` is re-run and the
  totals, per-GPC lines, ceilings, `crc_ok` and fingerprint are printed,
  together with which defect-word source actually fed the ceilings (FF
  words from the hex window vs legacy shadow keys). Driver-bound guarded
  captures are additionally flagged `driver_bound: True — UNVERIFIED`. A
  developer can replay the exact numbers offline from the shipped
  `dump.json` alone.

The bundle contains board serials and PCI info but **no credentials**.
Attach it when reporting an issue — send it to the developers.

## Standalone tools (reference)

- Full dump without the GUI:
  `sudo python3 -m ga100vfi.fusedump --bdf 0000:41:00.0`
- Static HTML snapshot of a dump:
  `python3 -m ga100vfi.console.gui <dump_dir> out.html`
- CLI campaigns (`ga100vfi campaign`, see [docs/ADAPTIVE.md](ADAPTIVE.md))
  additionally write per-run JSONL telemetry under `telemetry/` (card
  serials included — keep it out of anything you publish). Sharing is
  **opt-in**: after a Goldilocks hit the CLI *asks* before uploading
  redacted runs to the collector; `ga100vfi share` (or `--dry-run` to
  inspect first) does it manually, `--no-telemetry` disables the file.
  Console campaigns do not upload telemetry — they log
  `goldilocks.jsonl` in the state dir only.

## systemd example

```ini
[Unit]
Description=ga100vfi fuse console (GA100 CMP 170HX)
# network.target, NOT multi-user.target — the console binds early and does
# not need to wait for wait-online / other multi-user services (a unit
# ordered after multi-user.target can come up minutes late on slow boots).
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/ga100-fuse-view
# No --bdf: the console auto-detects and also starts card-less (a pinned
# --bdf must name a present GA100 at startup, or the unit restarts).
ExecStart=/usr/bin/python3 -m ga100vfi.console --port 8790 --state-dir /opt/ga100-fuse-view
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
```

(Requires the package importable system-wide, e.g.
`sudo pip install -e /path/to/pico-ga100vfi-console/host`.)

## Testing without hardware

```sh
python3 -m ga100vfi.console --mock /path/to/dump.json --port 8790
```

Serves a recorded `dump.json` instead of a real card — useful for working
on the GUI. What mock mode does and refuses (all verified against a live
mock server):

- `/api/live` serves the recorded dump verbatim (no live `tpc`/`window_ok`
  probe); `/api/gpus` lists the mock card with driver `mock`.
- `/api/burn/preview` works read-only over the mock rows; `/api/ff/layout`
  computes zones from the recorded rows.
- `/api/bound_dump/preflight` returns a synthetic `all_ok` condition list
  flagged `"mock": true`; `/api/bound_dump`, `/api/glitch/start`,
  `/api/burn`, `/api/burn/check`, `/api/revert` and `/api/driver/op` all
  refuse with a `not available in mock mode` style error.
- `/api/arm` runs the Goldilocks gate against the mock status registers;
  the identity gate is vacuously satisfied in mock (no physical card).

## Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| Page won't load right after boot | The service starts with the network; give it a few seconds. `systemctl status ga100-fuse-view` if it persists. |
| Live pill: `driver '<driver>' bound — raw BAR0 live view disabled (Drivers tab -> Unload nvidia stack to resume)` | Working as designed — raw BAR0 reads can wedge GSP while the driver is bound. Drivers tab → **Unload nvidia stack**, or use the guarded capture. |
| Live pill: `BAR0 unreadable — bus hung or PCIe link down (normal mid-glitch / after reset)` | Normal during a campaign — the PCIe link drops on every shot and comes back. |
| GPU Info shows an nvidia-smi error / "No devices were found" | Expected while the card is GFW-dead; the banner is honest, not an error. While the module is absent the console reports `driver not loaded — nvidia-smi skipped (NVML would auto-load the driver)`. |
| Campaign start refused: `driver '<driver>' is bound to <bdf> — every glitch attempt reprograms PCI COMMAND/BAR0 via bar0.restore(), which corrupts GSP boots under a bound driver. Unload it from the Drivers tab first.` | AGENTS rule: never write PCI `COMMAND`/BAR0 under a bound driver. Drivers tab → **Unload nvidia stack**. |
| Campaign log: `FUSE CONTROLLER POISONED (0xBADF____) — persists until a POWER CYCLE; stopping this boot` | The shot disturbed the fuse read; the controller stopped answering and further BAR0 reads risk hanging the host. Power-cycle the card; the next boot's shots are unaffected. Poison is NOT counted as `over` and never steers the planner. |
| Campaign start refused: `v_dip <n> mV outside 200-500 — refusing (check for a typo)` | Fat-fingered v_dip; the firmware does not clamp `vd`. |
| Campaign start refused: `adaptive range invalid: min_v <a> >= max_v <b>` | Swap the adaptive v min/max fields. |
| Campaign start refused: `burn mode requires a valid arm token (type BURN in the burn panel, 120s TTL)` | Arm first; the token expires after 120 s. |
| Arm/burn refused: `identity gate: …` | The card in the slot is not provably the card the payload was made for: serial unreadable (reseat/rewarm, retry — failed reads are not cached), die-ID rows differ from the selected dump (wrong card or mis-keyed dump — check the SN pill against the strip), die-ID read unstable (re-read; a poisoned fuse controller also fails this — cold-boot first), or the selected dump predates rows 8–15 (re-dump with `--rows`). |
| Campaign start refused: `burn mode needs at least one record (set + check the burn payload first)` | Queue records or Check the payload first. |
| Campaign start refused: `burn placement policy: <issues>` | A queued row violates the zone rules (occupied / buffer / SM reserve / revert tail / outside FF region) or a value has bit 5 set (IFF). |
| Arm refused: `GPU <bdf> is not Goldilocks — failing: <checks>` | The 4-check pure-read (dsov / crc_ok / priv_open / fpf_readable) failed on the selected GPU — glitch it to Goldilocks first. |
| Burn now stays disabled | Not checked (`payload edited — re-check` means the check was invalidated by an edit), not armed, or the burn window pill says closed — run a glitch campaign first. |
| Check shows EFP/WDATA_PLM amber (arm pending) | Normal — they are auto-armed at burn via SENSE_CTRL; only the red window checks block. |
| Check top-line says `REFUSED` | The burn window is closed (red window checks) — that's what the burn-on-first-Goldilocks campaign mode is for. |
| Burn result `ABORT — uncertain burn state — resolve journal` | The burn journal has an unresolved `command_may_be_issued` — a previous CMD_WRITE may have latched without readback. Inspect `burn_journal.jsonl`; the GUI offers an explicit proceed-anyway (`ack_uncertain`). |
| Burn result `ABORT — row <n> reads 0x…, expected 0x…` | The row drifted from the checked value — re-Check before burning. |
| Burn result `ABORT — guard failure (no Goldilocks window)` | The window closed between check and burn (standalone burns only work inside a held window). |
| Burn result `IMAGE VERIFY FAILED` | The multi-record image re-read wrong — the window is NOT held and success is not claimed; re-glitch and retry. |
| `card busy (campaign or dump in progress)` on check/dump/live | A campaign or another dump holds the card; wait for it to finish. |
| `campaign running — full dump refused` | The full-dump sweep could push classify past the Goldilocks window; stop the campaign first. |
| Target card shows `no GA100 detected` / live shows `no GA100 present on this host` | The card dropped off the bus or never enumerated — check `lspci`. The pinned `--bdf` is never used as a ghost: dumps and burns refuse until a GA100 is detected. |
| Console started with no GA100 in any slot | Supported: it serves card-less (banner `no GA100 present on this host`, endpoints answer their honest 409/error JSON, Support bundle works with zero cards). Insert a card and the next poll self-detects it. A startup `warning: no GA100 CMP 170HX present — serving card-less` on stderr is expected; only an explicit `--bdf` naming a missing device exits. |
| Pico port dropdown shows `no pico detected` | Pico not connected / not enumerated; fix the cable, press **⟳ rescan**. A note appears when serial ports exist but none is a Raspberry Pi device. |
| Campaign log fills with `nack` | The pico↔VRM I2C link is marginal; budget attempts per power-cycle and let the VRM cool, per the repo's safety notes. |
| Bound capture refuses: `preflight refused: <conditions>` | Fix the named conditions (the panel shows each failed condition + hint); most common: PLM locked → run the PLM unlock first. |
| Bound capture refuses: `driver '<drv>' not bound on <bdf> — use the normal full dump (no guard needed)` | The guard only applies with nvidia bound; unload the driver and use **⟳ Run full dump**. |
| Browser shows `Host '<name>' rejected — use the host IP or localhost (DNS-rebinding guard)` | Browse by IP or localhost; a domain rebound onto this host is refused. |
| Browser POST shows `cross-origin '<origin>' rejected (CSRF guard)` | The page was opened from a different origin than the console's Host; open the console directly. |
| Where did my successful campaign go? | `<state-dir>/goldilocks.jsonl`, one JSON line per hit with the card serial. |
