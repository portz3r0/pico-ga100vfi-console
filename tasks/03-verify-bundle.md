# TASK 03 — Independent adversarial verification of the support-bundle feature (task 02)

Work ONLY this task. You did NOT build task 02 and you trust its evidence file NOT.
READ-ONLY on the repo working tree (you may create your own test files under /tmp
and a temp state dir; you may NOT edit repo files, commit, or push).

Repo: /home/raza/nvidia/pico-ga100vfi, branch fuse-console. Task 02's commit is
HEAD (subject starts "console: support bundle"). Its claims: evidence/02-support-bundle.md.

## Ground truth contract (from the orchestrator, binding)
GET /api/support_bundle -> 200 application/gzip, attachment filename
ga100-fuse-support-<UTC>.tar.gz; tar members under support/: manifest.json
(tool_git_sha, built_at, host, bdfs, members, truncated, warnings, no-credentials
note), console.log, goldilocks.jsonl, last-preview.json, dumps/<bdf>/<ts>/dump.json
+ hex_window file (newest 5, oldest first), live_snapshot.json (paused dict is
valid), system.txt (lspci stanzas + dmesg tail), interpretation.txt (per-dump
tpc_summary totals + defect-word SOURCE line). Cap 25 MiB uncompressed with
oldest-dump drop recorded in manifest.truncated. Dashboard header must contain a
"Support bundle" link to /api/support_bundle. docs/CONSOLE.md has a
"Submitting a support bundle" section; README has a feature bullet.

## Adversarial checks (write your OWN tests; do not reuse task 02's test files)
1. git show --stat HEAD — files touched; confirm no firmware/ or unrelated edits;
   git log parent == ceb4ea9 (chain check).
2. Launch the service yourself: mock/degraded mode (grep __main__.py/service.py for
   the flag), port 8792, FRESH temp state dir. Seed: card1 dump
   (/tmp/card1_fuse_dump.json) as dumps/0000:01:00.0/20261121-052538/dump.json,
   plus a SECOND synthetic older dump dir (copy with modified ts) and a THIRD,
   FOURTH, FIFTH, SIXTH (six total -> tests the newest-5 cap + truncated list).
3. curl the endpoint; verify: status, headers, tar tzf member set vs contract,
   manifest parses + fields present, interpretation.txt contains sm_max 126 for
   card1 AND the defect-source line, exactly 5 dump dirs present and the OLDEST
   is the one dropped, manifest.truncated names it.
4. Edge cases: (a) state dir with NO dumps and NO console.log -> endpoint still
   200 with manifest warnings, no crash; (b) corrupt dump.json (write garbage) ->
   endpoint must not 500 the whole bundle; interpretation.txt records the failure
   for that dump (or manifest.warnings does) — a hard 500 is a FINDING;
   (c) concurrent GET twice -> both succeed; (d) GET / dashboard HTML contains
   the Support bundle link; (e) path traversal: your tar member names all start
   with support/ (tar -tvf scan).
5. Secret scan: grep the extracted tar for 'khankhan' and 'GITHUB_TOKEN' values —
   must be absent (console.log fixtures could carry them; if the real code can
   leak them from dmesg, report as finding, not auto-fail).
6. Kill your instance (PID-based, never pkill -f matching your own shell).

## Deliverables
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/03-verify-bundle.md written
  INCREMENTALLY: each check PASS/FAIL with the command + trimmed output.
- Verdict line: VERDICT: PASS or VERDICT: FAIL with numbered findings.
- 10-line stdout summary ending with exact line VERIFY_DONE (even on FAIL).
- Context discipline: grep -n then sed -n ranges <= 80 lines; head -30 on outputs.
