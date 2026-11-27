# TASK 66 — UX review of the GA100 Fuse Console burn workflow (design evaluation, NO code changes)

You are a senior UX designer auditing an operator-critical hardware tool before irreversible OTP fuse writes. Evaluate, do not implement.

## The product
A single-page web console (`/home/raza/nvidia/pico-ga100vfi/host/ga100vfi/console/gui.py` — the HTML/JS is embedded in this Python file; ~4000 lines) served at :8790 on a bench host. It controls: a live fuse-array view, a voltage-glitch campaign runner, and the burn pipeline for one-shot-programmable fuses. A wrong burn permanently bricks a $1500 GPU. The operator is the owner (experienced, impatient, running it live RIGHT NOW).

## The workflow the operator must complete (the "burn journey")
1. Card unbound, fresh dump taken.
2. Start a glitch campaign (classify mode, "hold open") → wait for "Goldilocks" (a transient hardware window, fades in minutes).
3. Arm: type BURN in the arm-phrase box → Arm button (only enabled while the window is open; token TTL 120 s; server refuses arm when window closed).
4. Launch the burn: queued records burn IN-PROCESS at the first Goldilocks of a burn-mode campaign (the only race-proof path — standalone "Burn now" loses the race to window decay ~every time).
5. Watch per-record VERIFY results; cold boot; verify.

## Observed operator failures (tonight, real)
- Operator reached Goldilocks, queued 2 correct records, then hunted for how to burn: Arm button lives in the "Burn payload" panel far from the "Burn queue" panel and from the campaign controls.
- TWO burn affordances coexist and confuse: "Burn payload" (single row + Check + Preview + Arm + "Burn now") and "Burn queue" (list, "all of these burn in one Goldilocks window"). Operator queued records but kept trying the payload panel's Burn button.
- "Burn now (burn window only)" is enabled/disabled by live window state and aborts with "guard failure" when the window decays between click and execution — a button that is almost never the right button.
- Window state is shown in 3 places with different freshness: campaign pill ("HELD open", from last classification), burn panel badge ("burn window closed (FUSECTRL_PLM)", live poll), arm tooltip ("selected GPU not Goldilocks — glitch first"). Operator cannot tell which is authoritative.
- The correct sequence (arm during held window → stop → switch mode dropdown to burn → start campaign within 120 s) is discoverable nowhere; it lives in the developer's head.
- Mode dropdown ("hold open — no revert") and burn-mode selection are in the campaign panel at the top of a long page; the queue is mid-page; arm is elsewhere.

## Your deliverables (write to /home/raza/nvidia/pico-ga100vfi/evidence/66-ux-review.md)
1. **Journey map** of the burn flow as-is: every panel, state, click, and timing constraint; mark the 4 highest-friction / highest-risk points (risk = wrong burn or lost window).
2. **Findings** with severity, each tied to concrete gui.py element ids/lines (grep for gc-, burn, arm, queue).
3. **Redesign proposal** — the core idea to evaluate and extend: ONE "Burn" workspace that owns queue + arm + launch as a single atomic action ("Arm & burn queue" button that server-side arms and starts the burn campaign in one call), with ONE authoritative window-state indicator (live register poll) mirrored everywhere, and "Burn now" demoted/removed. Address: what happens to the payload panel's Check/Preview (they are genuinely useful pre-flight gates — where do they belong?), how to show arm-token TTL countdown, how to show per-record burn results without scrolling, and how the design degrades when the window decays mid-flow.
4. **HTML mockup** of the redesigned Burn workspace: `/home/raza/nvidia/pico-ga100vfi/evidence/66-ux-mockup.html` — dark theme, self-contained, static (no backend), showing the queue with statuses, the single window-state indicator (open/fading/closed states), arm+launch button with TTL countdown, and a decayed-window state. Make it look like the real console (dark, compact, monospace numerals).
5. Commit both files on main in /home/raza/nvidia/pico-ga100vfi (no push).

## Rules
- NO changes to gui.py, service.py, or any existing file. New files only, under evidence/.
- Read gui.py with grep + ranged reads (it is large); you may GET http://192.168.0.175:8790/ (read-only) to see the live markup, but do NOT POST anything to that console — a burn session is live on that bench.
- Be concrete and opinionated; severity-rank by brick-risk and window-loss, not aesthetics.
- Finish with marker UX66_DONE + 8-line summary.
