# TASK 67 — Implement the UX redesign of the burn workflow (console) and deploy to the HP bench

Zero-context builder agent. Repo: `/home/raza/nvidia/pico-ga100vfi` (git main, work on main). Console = `host/ga100vfi/console/service.py` (HTTP API, stdlib only) + `host/ga100vfi/console/gui.py` (single-page app, HTML/JS embedded in Python strings). Read first: `evidence/66-ux-review.md` (findings F1–F9 + redesign) and `evidence/66-ux-mockup.html` (target look). Follow findings; the mockup is a guide, not gospel — match the REAL console's existing style/helpers.

## What to build (scope: fix F1, F2, F3, F4, F6; F5-lite; leave F7–F9)

1. **Atomic queue burn (F1, F2 — the core).** New server endpoint `POST /api/burn/queue_start` taking `{records[], <same glitch params as /api/glitch/start>}`: in ONE request, server-side it (a) requires the queue non-empty, (b) runs the existing arm gate (Goldilocks + identity vs newest dump) and mints the arm token, (c) starts the burn-mode campaign with those records + token, (d) returns `{started, records, token_ttl}` or a precise error. No client-side arm→start race remains. Reuse arm_api/glitch_start internals — do NOT duplicate their safety checks; call them.
2. **Burn workspace card (F1).** In gui.py, move/rebuild the Burn queue panel (`gb-queue`) to sit directly under the Glitch campaign controls (same panel group), retitled "Burn queue — arm & burn in one action". One big button **"Arm & burn queue (N)"** → POSTs /api/burn/queue_start with the current campaign params + queue records. Disabled with a one-line reason when: queue empty / campaign already running / no GPU. Keep the existing confirm dialog (irreversible-OTP warning, row list).
3. **Single authoritative window indicator (F3).** One pill "burn window: OPEN / FADING / closed" driven by the LIVE register poll (the existing /api/live or burn-window poll the payload panel already uses — find it, reuse). OPEN = all window checks pass; FADING = DSOV==0 but any other check fails; closed otherwise. Render it on the Burn queue card AND make the campaign HELD chip and the payload panel pill consume the SAME state value (one JS variable, one poll).
4. **Per-record status in the queue table (F4).** While a burn campaign runs, poll /api/glitch/status and fill the queue STATUS column from stats.burned[] (row → result), colorized (VERIFY OK green, ABORT red, pending dim). Keep the gc-log lines too.
5. **Demote "Burn now" (F2).** Relabel to "Burn payload row ONLY (standalone)" with tooltip "does NOT burn the queue — use Arm & burn queue". Keep behavior.
6. **Check queue pre-flight (F5-lite).** New button "Check queue" on the card: loops the existing /api/burn/preview per queued record, renders per-row verdicts in the queue table (verdict column or tooltip). No new server endpoint needed.
7. **TTL (F6):** with atomic start the TTL is mostly invisible; still show remaining token seconds on the button for 120 s after a manual Arm (existing countdown logic — reuse).

## Tests & verification (mandatory, all must pass)
- New `host/tests/test_queue_start.py` (unittest, NOT pytest — pytest is not installed): mock-mode server; assert queue_start refuses empty queue, refuses without Goldilocks (mock state), and happy-path returns started+records; assert it reuses arm gate (spy/monkeypatch).
- Run the FULL existing suite the same way as before: `cd host && /usr/bin/python3 -m unittest discover -s tests -v 2>&1 | tail -5` — the FAIL set must be IDENTICAL to the pre-change baseline (record baseline first: run discover BEFORE your changes, save the failing test names).
- Extract the gui JS and `node --check` it (node at /home/raza/.hermes/node/bin/node) — same method as tests/test_allspark_frontend.py uses.
- py_compile both changed files.

## Deploy to HP bench (after tests pass)
- HP `192.168.0.175`, ssh `administrator` pw `khankhan`: `sshpass -p 'khankhan' ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no administrator@192.168.0.175 '<cmd>'`. Sudo: `echo khankhan | sudo -S bash -c '<cmd>'` (feed password once to bash -c, not per-command).
- Clone on HP is ROOT-owned at `/home/administrator/nvidia/pico-ga100vfi` — scp to /tmp then sudo cp. Deploy service.py + gui.py, `systemctl restart ga100-fuse-console` — NOTE: restart over ssh HANGS the session on this box (known); run it as `sudo bash -c 'systemctl restart ... &'` or accept the hang and verify separately. Service takes ~5 s to bind :8790; poll GET /api/gpus until 200.
- Verify served page contains the new markers ("Arm & burn queue", "burn window:") via GET http://127.0.0.1:8790/ on the HP, and md5 parity of both files.
- The bench has a LIVE card (…075) — GETs only; do NOT POST glitch/burn endpoints during verification (a burn session is pending for the owner).

## Commit & finish
- Commit on main: "console UX: atomic /api/burn/queue_start + burn-workspace card + authoritative window pill + queue status rendering (UX66 F1-F4,F6)". No push.
- Update TASKS.md board (add task 67 DONE line).
- Finish with marker `TASK67_DONE` + 10-line summary: endpoint, GUI changes, test results (baseline vs after FAIL-set), deploy md5s, markers verified.

## Rules
- stdlib-only server, no new deps. Preserve ALL existing safety gates (arm gate, identity gate, plane gate, journal, two-step burn) — you are re-plumbing the path, not weakening it. If any existing test breaks that your change did not cause, note it; if your change causes it, fix it.
- Do not touch tools/ (gitignored), plans/, evidence/66-*.
