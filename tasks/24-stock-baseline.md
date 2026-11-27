# TASK 24 — BAR auto-enable + per-card STOCK baseline (kill hardcoded SKU template)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 1932647 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console:
host/ga100vfi/{bar0.py, fusedump.py, console/service.py, console/gui.py}
(UI = embedded HTML/CSS/JS in gui.py). Established: dumps serial-keyed under
<state-dir>/dumps/sn-<serial>/<ts>/dump.json; require_ga100(bdf) validates
sysfs vendor 0x10de + device 0x20c2/0x20b5 before BAR0 writes; /api/live
honest errors; history browser /api/dumps + /api/dumps/get; task 22 stale
labels.

TWO REAL-WORLD FINDINGS driving this task (AI2, 2026-11-23):
1. Fresh cold boot, card present, NO driver loaded -> kernel leaves BAR
   memory-decode DISABLED (lspci: "Region 0 ... [disabled]"), BAR0 reads
   return garbage, console honestly says "BAR0 unreadable" until someone
   runs setpci COMMAND memory-enable. Manual setpci fixed it instantly.
2. The TPC map's "PRE-GLITCH" state is a HARDCODED template (gui.py ~777-
   803: "stock CMP 170HX SKU floorsweep: GPC_DISABLE 0x86 (GPC 1/2/7) plus
   factory TPC mask 0x01/0xFF pattern (29 TPC masked -> 70 SM)") — the
   REFERENCE card's stock config. A virgin card whose real fuses differ
   (new card: TPC FF words all 0x0, different sweep) shows a phantom
   "pre-glitch vs now" difference on a card never glitched. User ruling:
   rename to STOCK STATE and derive it from THIS card's own fuses.

## Mission
A. BAR auto-enable (service.py or bar0.py):
   - When the console maps BAR0 for a require_ga100-validated device and
     the PCI COMMAND memory-enable bit (bit 1) is clear, set it (write
     config space word via /sys/bus/pci/devices/<bdf>/config), log one
     line, re-verify readable. Only ever for validated GA100s. If setting
     fails or BAR still unreadable, keep existing honest error path.
   - Idempotent; never touches non-GA100 devices.
B. STOCK baseline, per card serial:
   - On successful dump save for serial S: if <state-dir>/dumps/sn-S/stock.json
     does not exist, write it = copy of this dump + {"stock_provenance":
     "first dump seen for this serial at <ts>"}. Never overwrite.
   - New endpoint GET /api/stock -> {serial, stock: <dump or null>,
     provenance, is_current: bool} for the PRESENT card (null + reason when
     no card or no baseline yet).
   - gui.py: rename all user-facing "Pre-glitch"/"PRE-GLITCH" -> "Stock
     state"/"STOCK (this card's factory fuses)". The stock view renders
     GPC/FBP/mem/TPC masks from the card's OWN stock.json (same extraction
     the now view uses), NOT the hardcoded 0x86/0x01/0xFF template. Delete
     the template text; replace note with: provenance line + "if this card
     was modified before this console first saw it, stock = state at first
     sight". When no baseline exists yet: stock view shows now-state with
     "no stock baseline recorded yet — this dump is the first record".
   - Diff honesty: stock-vs-now differences now mean real fuse changes
     (campaign effects); virgin card shows zero difference.
   - INTENDED and NOW semantics unchanged (intended = disable mask ==
     defective mask; now = live dump).
C. Docs: CONSOLE.md — stock/intended/now definitions + stock baseline
   provenance + BAR auto-enable note.

## Gates (worktree /tmp/v24 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- Unit-ish tests on THIS card-less box: stock.json written once (second
  dump same serial does NOT overwrite); /api/stock null-with-reason
  card-less; config-space COMMAND read/write helper tested against a
  sysfs device that EXISTS on this box (any 10de device or mock the path
  with a temp config file — do NOT poke random real devices' COMMAND).
- Playwright: seeded state dir (two serials, one with stock.json, one
  without): stock view renders from stock.json values (assert a value that
  differs between stock.json and latest dump appears correctly), no
  "0x86"/"29 TPC" template strings anywhere in served page, rename
  complete (grep served HTML for "pre-glitch" case-insensitive == 0).
- Mock console still renders; fingerprint changed vs 7d8215668817, v0.3.0.
- One commit "console: BAR auto-enable for validated GA100 + per-card stock baseline replaces hardcoded SKU template";
  push fork v24:main NO force (if push fails on credentials, say so
  honestly and leave commit on v24 branch); ls-remote verify; branch -f
  main v24; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/24-stock-baseline.md
  incremental.
- stdout <=8-line summary ending with exact line STOCK_DONE.

## Hard rules
- No AI2, no hardware, no force push, primary tree untouched (dirty pwmvid.c).
- Config-space writes ONLY behind require_ga100 validation.
- Keep JS ids stable; gui.py HTML escape-sensitive.
- Context discipline: grep anchors +-40 lines.
