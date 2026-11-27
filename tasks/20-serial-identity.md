# TASK 20 — Dump identity by GPU SERIAL, not PCIe address + hard BDF validation (no blind fallback)

Work ONLY this task. Zero prior context; everything needed is here.

## Context (orchestrator-verified)
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = addd21a == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console:
host/ga100vfi/console/service.py + gui.py, fusedump.py, guarded.py, bar.py
(bar.py has board-serial read — grep brd_serial / serial; /api/gpus already
exposes serials, readable via InfoROM even driverless).

INCIDENT that motivates this task (user, 2026-11-23): card swapped, new GPU
at 81:00.0; at one boot no GA100 enumerated; user clicked "Run full dump";
full_dump() line ~394: `bdf = bdf or effective_bdf(fd.find_ga100s()) or
CFG["bdf"]` silently fell back to the unit-file-pinned 41:00.0 — which was
then an AMD dummy function — and issued fuse CMD_READ WRITES into its BAR0.
Host rebooted. Line ~395 `if bdf != CFG["bdf"] and not valid_bdf(bdf)`
explicitly SKIPS validation for the configured BDF. Same fallback pattern at
lines ~310, ~340, ~589, ~697 — audit ALL of them.

## Mission (two coupled changes)
### A. Hard BDF validation — never write to unverified silicon
1. New helper (service.py or fusedump.py): `require_ga100(bdf)` — reads
   /sys/bus/pci/devices/<bdf>/{vendor,device}; must be 0x10de + 0x20c2/0x20b5
   else raise/return error "no GA100 at <bdf> (found <vendor:device>)".
2. Every BAR0-touching path calls it BEFORE any mmap/write: full_dump,
   dump endpoints, glitch start, standalone burn, guarded capture entry
   (guarded.py preflight already checks PMC_BOOT_0 — keep, but sysfs check
   first so we don't even mmap a wrong device), driver ops that target a bdf.
3. REMOVE the silent `or CFG["bdf"]` fallback everywhere it could point at
   absent silicon: when find_ga100s() is empty, endpoints answer
   {"error": "no GA100 present on this host"} (HTTP 409) — the poll loop
   already says exactly this; the dump button must honor it, not resurrect
   the pinned address. CFG["bdf"] remains only as a *preference* among
   DETECTED cards (effective_bdf semantics), never as a ghost.

### B. Serial as the card identity for dumps
1. On every dump (full + guarded), read the board serial (bar.py path when
   unbound; nvidia-smi when bound; guarded capture is bound -> nvidia-smi
   --query-gpu=serial --id=<bdf>); store in dump.json as "serial" (null +
   "serial_source":"unavailable" if unreadable) alongside existing fields.
2. Dump storage: dumps_dir()/sn-<SERIAL>/<timestamp>/dump.json (fallback dir
   name bdf-<bdf> when serial unavailable). Migration: EXISTING dump dirs
   keep working — resolution must scan both layouts; do not move user files.
3. "Current card" resolution: newest dump whose serial matches the present
   card's serial; if none, UI/bundle say "no dump yet for this card (serial
   X)" instead of silently showing the OLD card's dump. Old-serial dumps
   remain listed but labeled "different card (serial Y)".
4. /api/live + support bundle manifest: include current card serial +
   per-dump serial labels; interpretation trace header names the serial.
5. gui.py: header/dump-list show serial; paused_hint last-dump age refers to
   SAME-SERIAL dumps only.
6. docs/CONSOLE.md + USER-GUIDE.md: dump identity semantics (serial-keyed,
   BDF is transport; what "no dump yet for this card" means).

## Gates (worktree /tmp/v20 from main; never touch primary tree or AI2)
- py_compile all host/**/*.py; joint imports OK; node --check script block.
- Unit-ish checks in mock: (1) require_ga100 rejects a real non-NVIDIA
  sysfs device present on THIS box (pick any 10de-absent BDF from
  /sys/bus/pci/devices) and accepts a fake dir you create under a tmpfs
  sysfs-like root if the helper takes a root param (design it testable);
  (2) full_dump with no GA100 detected returns the 409 error, not a crash;
  (3) mock dump lands under sn-<mockserial> and /api/live serial fields
  render; (4) old-layout dump dir still resolves (create one by hand).
- Mock console on free port: /api/live, /api/support_bundle OK; bundle
  manifest shows serial labels; kill server.
- TPC replay unchanged 70/126; fingerprint CHANGED (service.py changed),
  version stays 0.3.0.
- One commit "console: serial-keyed dump identity + hard GA100 validation, no ghost-BDF fallback";
  push fork v20:main NO force; ls-remote verify; branch -f main v20; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/20-serial-identity.md
  incremental: every fallback site found + what replaced it, serial source
  matrix (unbound/bound/guarded), migration behavior, mock outputs.
- stdout <=10-line summary ending with exact line SERIAL_DONE.

## Hard rules
- Never write to hardware from this task (mock + fake sysfs only). No AI2.
- Existing dump files on disk are sacred: read-compatible, never moved.
- No force push; primary tree untouched (dirty pwmvid.c).
- Context discipline: grep anchors +-40 lines; audit list in evidence.
