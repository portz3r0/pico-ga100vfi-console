# TASK 02 — Support-bundle log collection for the Fuse Console

Work ONLY this task. Zero prior context assumed; everything needed is here.
Build on the CURRENT repo state (task 01 just synced it) — read files as they are,
never revert prior work.

## Mission
Users of the GA100 Fuse Console hit interpretation bugs on their own cards (e.g. a
golden die reported as 74-SM). We need a one-click "support bundle": the console
packages its own working logs + every collected dump + a deterministic
INTERPRETATION TRACE, and the user downloads one tar.gz to send to the developers.

Repo: `/home/raza/nvidia/pico-ga100vfi`, branch `fuse-console`.
Console server: `host/ga100vfi/console/service.py` (stdlib http.server; state dir
via CFG["state_dir"]; existing artifacts: console.log, goldilocks.jsonl,
last-preview.json, dumps/<bdf>/<ts>/dump.json + hex_window_0x820000.txt).
Dashboard HTML is embedded in `host/ga100vfi/console/gui.py` (markers: `TPC_FFDEF`,
`renderTpc`) and mirrored in the deploy artifact live.html — edit gui.py; if a
tracked live.html exists in the repo, mirror the same edit there.
Docs: `docs/CONSOLE.md`, `README.md`.

## BINDING interface contract (do not renegotiate)
1. `GET /api/support_bundle` → `application/gzip`, header
   `Content-Disposition: attachment; filename="ga100-fuse-support-<UTCyyyymmddTHHMMSS>.tar.gz"`.
   Errors: 500 + JSON {"error": ...} on failure; never a partial download
   (build into memory/temp fully, then send).
2. Tar layout, all members under `support/`:
   - `manifest.json`: {tool_git_sha (git rev-parse HEAD, fallback "unknown"),
     built_at ISO-UTC, host: {hostname, kernel, python}, bdfs: [...],
     members: [{path, bytes}], truncated: [...], warnings: [...],
     note: "contains board serials and PCI info; no credentials"}
   - `console.log` (tail 2 MiB), `goldilocks.jsonl` (tail 2 MiB),
     `last-preview.json` (if present)
   - `dumps/<bdf>/<ts>/dump.json` + `hex_window_0x820000.txt` for the NEWEST
     5 dump dirs (by mtime), oldest first
   - `live_snapshot.json`: best-effort live register snapshot reusing the same
     code path as /api/live (may legitimately be {"paused": "..."} when the
     driver is bound — that is a valid bundle member)
   - `system.txt`: `lspci -vv` stanzas for 10de:20c2/20b5/2082 devices +
     `dmesg` lines matching nvrm|nvidia|20c2|20b5 (tail 200). Use argv-list
     subprocess (existing sh() helper), timeout 15s, tolerate absence.
   - `interpretation.txt`: FOR EACH bundled dump: re-run
     `fusedump.tpc_summary(shadow, hexnonzero)` and print totals (sm_now,
     sm_max, defective, recoverable), per-GPC one-liners, the defect-word
     source actually used ("FF words from hex window" vs "shadow keys
     (legacy)"), ceilings, crc_ok, fingerprint. This is the file that lets a
     developer replay the interpretation offline — make it self-describing.
3. Size cap: total uncompressed <= 25 MiB; on overflow drop oldest dumps and
   record them in manifest.truncated.
4. UI: header button/link "Support bundle" on the dashboard (next to existing
   header controls), href `/api/support_bundle`, title tooltip
   "Download console logs + dumps + interpretation trace as one tar.gz — attach it when reporting an issue".
5. Docs: new CONSOLE.md section "Submitting a support bundle" (what it contains,
   that it has no credentials, where to send it — keep destination generic:
   "the developers"); one README bullet under features.

## Verification gates (run them yourself, paste outputs into evidence)
- `python3 -m py_compile` all changed .py.
- Start the service LOCALLY in its mock/degraded mode (grep service.py/__main__.py
  for the mock/no-hardware flag; port 8791, temp --state-dir under /tmp).
- Seed the temp state dir: copy console.log fixture, goldilocks.jsonl fixture,
  and `/tmp/card1_fuse_dump.json` (exists on this machine; if not, scp from
  AI2:/tmp/, READ-ONLY) as `dumps/0000:01:00.0/20261121-052538/dump.json`
  (convert: the dump JSON has shadow+hexnonzero keys; write it as-is).
- `curl -sD- http://127.0.0.1:8791/api/support_bundle -o /tmp/b.tgz` → assert
  200, content-type, filename header; `tar tzf /tmp/b.tgz` lists every contract
  member; `python3 -m json.tool` on manifest.json from the tar.
- Assert interpretation.txt from the tar contains `sm_max: 126` (or `sm_max=126`
  — match your format) for the card1 dump and the defect-source line.
- Assert the served dashboard HTML (GET /) contains the Support bundle button.
- Kill your local instance afterwards (PID-based kill; never pkill -f with a
  pattern that matches your own shell).

## Deliverables
- Code + docs committed on `fuse-console`, subject:
  `console: support bundle — one-click logs + dumps + interpretation trace`
- Push: `source ~/.hermes/.env && git push https://x-access-token:${GITHUB_TOKEN}@github.com/portz3r0/pico-ga100vfi-console.git HEAD:refs/heads/fuse-console` (no force).
- Evidence `/home/raza/nvidia/pico-ga100vfi/evidence/02-support-bundle.md`,
  written INCREMENTALLY after each step (crash-safe): design notes, diff stat,
  every gate output, commit sha, push verification.
- 10-line stdout summary ending with exact line `BUNDLE_DONE`.

## Hard rules
- AI2 (192.168.0.15) is READ-ONLY (sshpass -p khankhan ssh raza@192.168.0.15);
  never write/restart anything there. Do NOT deploy — deploy happens later.
- Do not touch `firmware/`, `evidence/`, `logs/`, `tasks/` (except writing your
  own evidence file).
- stdlib only; match existing code style (no new deps, no f-string nesting mess).
- Never git push --force / rebase / amend after push.
- Context discipline: service.py is ~2.6k lines — locate with grep -n, read with
  sed -n 'X,Yp' ranges <= 80 lines, never cat whole files.
- If a gate fails: fix and re-run; if truly blocked, stop, write evidence, print
  `BUNDLE_FAIL` + reason.
