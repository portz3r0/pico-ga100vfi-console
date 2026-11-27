# TASK 68 — Remove the duplicate burn trigger: ONE burn action on the page (gui.py only)

Repo `/home/raza/nvidia/pico-ga100vfi`, work on main. Console GUI: `host/ga100vfi/console/gui.py` (HTML/JS embedded in Python). The UX problem (owner-verdict, supersedes any earlier "demote" decision): the page has TWO places that can burn — the old "Burn payload" panel (arm phrase + Arm + "Burn payload row ONLY") and the new "Burn queue — arm & burn in one action" card. Owner: "why should there be two places where the same thing can happen". There must be exactly ONE burn trigger: the queue card's "Arm & burn queue (N)".

## Changes (gui.py ONLY — do not touch service.py; the /api/burn standalone endpoint stays for API/recovery use)
1. In the Burn payload panel (`gb-burn`): REMOVE the arm-phrase input (`gb-armphrase`), Arm button (`gb-arm`), arm-state badge (`gb-armstate`), the standalone burn button (`gb-burnnow`), and the panel's own window-state pill (`gb-windowstate`) — the queue card owns the authoritative pill. RETITLE the panel to "Row probe (read-only)" and keep: target row, value source, value, mirror checkbox, "Check row & guards" (`gb-check`), "Preview burn (read-only)" (`gb-preview`). Add one line of help text: "To burn: queue this row (or use Suggested burns) and use Arm & burn queue below."
2. JS hygiene: grep EVERY removed id (`gb-armphrase|gb-arm\b|gb-armstate|gb-burnnow|gb-windowstate`) in gui.py — remove or null-guard every handler, reference, and poller update so no `$("...").onclick` on a null element can throw (one null throw kills the whole page). The arm countdown logic may stay dead-code-free: delete what's unreachable.
3. Queue card: ensure "Arm & burn queue (N)" is the only element on the page that can start a burn. Its disabled-reason line must cover: queue empty / campaign running / window not OPEN (poll-driven).

## Verify (all mandatory)
- `cd host && /usr/bin/python3 -c "import py_compile; py_compile.compile('ga100vfi/console/gui.py', doraise=True)"`
- Extract JS (regex `<script>...</script>`) → `/home/raza/.hermes/node/bin/node --check` must pass.
- `tests/test_allspark_frontend.py` — if it asserts removed markers, update the assertions to the NEW truth (one burn trigger), keep all other coverage. Must end "7/7 passed" (or 8/8 if you add an assertion that the page contains exactly one burn-start button id).
- Full per-file suite: run every `tests/test_*.py`, FAIL set must be IDENTICAL to current baseline (test_burn_window/test_program_sequence/test_verify6 TypeError burn_execute, test_verify8 KeyError, test_task17 8/13 — all pre-existing).
- GET the live page structure offline: `python3 -c` render check that gui HTML contains "Arm & burn queue" and does NOT contain "Burn payload row ONLY" or `gb-burnnow`.

## Deploy to HP + verify
- `sshpass -p 'khankhan' ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no administrator@192.168.0.175 '<cmd>'`; sudo `echo khankhan | sudo -S bash -c '<cmd>'`. Clone root-owned: scp to /tmp, sudo cp to `/home/administrator/nvidia/pico-ga100vfi/host/ga100vfi/console/gui.py`. Restart: `sudo bash -c 'systemctl restart ga100-fuse-console &'` (restart hangs ssh on this box — background it), wait ~8 s, poll GET /api/gpus until 200.
- Verify served page: contains "Arm & burn queue" AND "Row probe (read-only)"; does NOT contain "Burn payload row ONLY" nor "gb-burnnow". md5 parity.
- GETs only — live card, no POSTs.

## Finish
- Commit on main: "console UX: single burn trigger — payload panel becomes read-only row probe (owner verdict on UX66 F2)". Update TASKS.md board. No push.
- Marker TASK68_DONE + 8-line summary (what removed, JS guards added, test results, deploy md5+markers).
