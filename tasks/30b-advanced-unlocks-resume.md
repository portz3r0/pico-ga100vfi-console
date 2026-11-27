# TASK 30-RESUME — finish advanced unlocks + concrete rows (predecessor crashed mid-work)

Work ONLY this task. Zero prior context; everything needed is here.

## Situation
The previous agent for this task crashed early (empty log) leaving PARTIAL
WORK in the git worktree /tmp/v30 (branch v30 @ 1c62ac0, uncommitted):
  - NEW FILE host/ga100vfi/advanced_unlocks.py (194 lines, GOOD — keep and
    extend): decoded GA100PLN plans actually executed on bench GPU1/GPU2
    (razk-batch1/2.bin), FF-encoded records, provenance strings,
    VERIFIED/UNVERIFIED confidence, bench_rows-as-provenance-not-targets
    reasoning. Review it; fix anything wrong.
  - gui.py +8 lines: `from ..advanced_unlocks import ADVANCED_UNLOCKS` and
    `<script id="advanceddata" ...>__ADVANCED__</script>` injection stub —
    wiring started, not finished (service.py must fill __ADVANCED__; check
    how __PAYLOAD__ is filled in service.py/gui.py and mirror it).
Read the partial diff first (`cd /tmp/v30 && git diff`, plus the new file),
then FINISH the task below. Do not restart from scratch; do not discard the
decode work without reason.

## Full task spec (same as original)
Repo /home/raza/nvidia/pico-ga100vfi, main = 1c62ac0 == fork/main
(https://github.com/portz3r0/pico-ga100vfi-console.git). Primary tree on
stale branch fuse-console with dirty firmware/pwmvid.c — never switch/touch.
Console UI = embedded HTML/CSS/JS in host/ga100vfi/console/gui.py; FF rows
222-487; occupancy by VALUE (blank = 0x0/0xFFFFFFFF); shared client
allocator assignRows + ff_layout from /api/dumps/get; PROPOSED badges;
proposal==queue row equality is an established invariant.

R1. "Suggested burns — minimum common unlock" card (plan-rows/suggestPlan)
    must show CONCRETE target rows per word via the SAME assignRows
    allocator as the INTENDED proposed-burns panel (rows shown == rows the
    queue assigns; NO FREE FF ROW handling; PROPOSED labeling).
R2. New "Advanced unlocks" card on Glitch & Burn tab rendering the
    ADVANCED_UNLOCKS table (single source: advanced_unlocks.py): each item
    shows name, FF word(s), bench provenance, confidence badge
    (VERIFIED/UNVERIFIED), explicit warning "IRREVERSIBLE — not derived
    from this card's defect masks; data words carry the BENCH card's masks"
    (surface the per-die caveat from the module docstring), and a per-item
    "+ queue" that queues via the shared path with rows assigned by
    assignRows (re-placement on the shown card, bench rows are provenance).
    Items whose steps are DIRECT rows (<222) must be flagged manual-path
    (burn_execute only accepts 222-487 — verify and represent honestly).
    Server: fill __ADVANCED__ (service.py) so the page carries the table.
Docs: CONSOLE.md — suggested burns name rows; advanced unlocks semantics,
irreversibility, provenance/confidence meaning.

## Gates (finish in /tmp/v30 worktree; never touch primary tree or AI2)
- py_compile host/**/*.py (incl. advanced_unlocks.py); imports; node
  --check extracted script.
- Decode re-verification: re-run the predecessor's decode of both
  razk-batch*.bin (script or inline) and confirm the module's records
  match the binaries byte-for-byte; capture tables in evidence.
- Playwright, REAL-SHAPE dense fixture (task 28 recipe — dense rows incl.
  0-valued blanks): suggested-burns card shows concrete rows == queue rows
  after Queue all; advanced card renders each item with badges+provenance;
  + queue adds exactly its word at an assigned free row; UNVERIFIED items
  visibly flagged. Kill servers.
- Mock console unaffected; fingerprint changed vs d3f7dbb5526d, v0.3.0.
- Commit on v30 "console: suggested burns name concrete rows; optional advanced unlocks (Gen4/PLM/compute) from bench burn history";
  push fork v30:main NO force (no creds -> say so honestly, leave on v30);
  ls-remote verify; branch -f main v30; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/30-advanced-unlocks.md
  (predecessor wrote none — you write it): decoded step tables BOTH
  batches, attribution reasoning incl. GPU1-vs-GPU2 differences, delta
  notes, playwright assertions.
- stdout <=8-line summary ending with exact line ADVANCED_DONE.

## Hard rules
- No AI2 (USER HOLD: box is mining — no deploys/SSH writes), no hardware,
  no force push, primary tree untouched.
- GPU1/GPU2 dirs read-only inputs.
- Never present advanced unlocks as defect-derived; keep JS ids stable;
  gui.py HTML escape-sensitive.
- Context discipline: grep anchors +-40 lines.
