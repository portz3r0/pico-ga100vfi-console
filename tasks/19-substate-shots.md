# TASK 19 — Refresh the 3 remaining stale sub-state screenshots from the MOCK console

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 0a19bff == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console UI
docs embed screenshots in docs/images/. Task 18 already refreshed
console-explorer/glitch-burn/drivers/gpu.png + added console-capture-consent.png
from the live console (Playwright, 1600x1000 dsf=2 -> 3200x2000 PNGs).
STILL STALE (old horizontal-tab chrome), referenced by docs/USER-GUIDE.md:
- console-check-panel.png (line ~123: "Check result — green window bits, amber arm-pending rows")
- console-preview.png (line ~159: "Burn Preview — decoded record, LAST-WINS collision verdict, hazards")
- console-armed.png (line ~235: "Armed state — countdown pill; Burn stays disabled without a live window")
These are sub-states of the Glitch & Burn tab reached via POSTs (Check /
Preview / Arm) which cannot run on the live bench (driver bound, hardware
guard). SOLUTION: run the console in MOCK mode locally — mock simulates
these endpoints (verify by reading service.py mock branches; check
--help for the mock flag). Mock data is synthetic; the CHROME (layout) is
identical to current, which is what matters for these panel shots.

## Mission
Replace the 3 stale PNGs with current-chrome captures from a local mock
console; fix captions in USER-GUIDE.md where they describe values that mock
won't show the same way (captions must describe the PANEL, not synthetic
numbers). If mock genuinely cannot render one of the three states, leave
that PNG untouched and add an honest caption note "(captured on a previous
build)" — never fake it.

## Steps
1. Worktree /tmp/v19 from main. Start mock console on a free port
   (python3 -m ga100vfi.console --mock --port <free> --state-dir /tmp/v19-state
   — read --help for exact flags; run from the worktree with PYTHONPATH=host).
2. Playwright (installed already; browsers in ~/.cache/ms-playwright):
   open Glitch & Burn tab; drive the UI to each state:
   a. Check: select a burn row/value the way the UI requires (read gui.py JS
      for the Check flow — likely pick row + value source then click Check),
      click Check, wait for result panel -> screenshot ELEMENT (the panel
      card, not full page) -> console-check-panel.png
   b. Preview: click Burn Preview, wait for decoded record + verdict ->
      element screenshot -> console-preview.png
   c. Arm: click Arm (mock simulates countdown), capture while countdown
      pill visible -> element screenshot -> console-armed.png
   Element screenshots keep old shots' framing style (panels, not full page)
   — check the old PNGs' dimensions first (PIL) and match framing reasonably.
3. Replace the 3 files in docs/images/; update USER-GUIDE.md captions ONLY
   where they'd now be wrong (value-specific wording).
4. Gates: new PNGs non-blank (PIL variance), dimensions sane; all doc image
   refs resolve; fingerprint still 8bf8e2a2ed3f (no .py changes); mock server
   killed; worktree clean before commit.
5. One commit "docs: refresh check/preview/armed panel screenshots from mock console";
   push fork v19:main NO force; ls-remote verify; branch -f main v19; worktree
   remove. Never touch primary tree (dirty pwmvid.c) or AI2.
6. Evidence /home/raza/nvidia/pico-ga100vfi/evidence/19-substate-shots.md
   incremental: mock endpoint verification, which states rendered, caption
   changes, PIL checks.
7. stdout <=8-line summary ending with exact line SUBSTATE_DONE.

## Hard rules
- Mock only — no AI2, no hardware POSTs anywhere.
- If a state can't render in mock, say so in evidence + caption note; do not
  stage a fake.
- Context discipline: read gui.py Check/Preview/Arm JS via grep anchors +-40
  lines; scripts in /tmp.
