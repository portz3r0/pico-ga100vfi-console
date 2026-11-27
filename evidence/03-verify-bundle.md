# Task 03 — Independent adversarial verification of task 02 (support bundle)

Verifier: independent agent, 2026-11-22 (UTC). Did NOT build task 02; did not
reuse its test files. Repo read-only; all fixtures under /tmp/v03-state,
/tmp/v03-empty, outputs under /tmp/v03-out.

Target: ffbd97d "console: support bundle — one-click logs + dumps +
interpretation trace", branch fuse-console.

## Check 1 — commit scope + chain — PASS

```
$ git show --stat HEAD
 README.md                        |   3 +
 docs/CONSOLE.md                  |  30 +++++
 host/ga100vfi/console/gui.py     |   6 +-
 host/ga100vfi/console/service.py | 243 +++++++++++++++++++++++++++--
 4 files changed, 269 insertions(+), 13 deletions(-)
$ git rev-parse HEAD^
ceb4ea9b5c9614e4e128a057f20e65f97d665de9
```

No firmware/ or unrelated files in the commit. Parent is exactly ceb4ea9.
(The working tree has an unrelated modified `firmware/pwmvid.c` and untracked
tools/ — pre-existing, not part of HEAD.)

## Check 2 — launch own instance, mock mode, fresh state dir — PASS

`--mock <dump.json>` and `--state-dir` flags found in service.py `main()`
(argparse, ~lines 2461/2471). Launched:

```
PYTHONPATH=host python3 -m ga100vfi.console --mock /tmp/card1_fuse_dump.json \
  --state-dir /tmp/v03-state --listen 127.0.0.1 --port 8792 --poll 5   # PID 2364866
```

Seeded 6 dump dirs `dumps/0000:01:00.0/20261121-0525{38..43}/dump.json`
(dir 052538 = real card1 dump, others = card1 copies with modified
`started`), dir mtimes strictly ascending, plus console.log,
goldilocks.jsonl, last-preview.json fixtures.

## Check 3 — endpoint contract — PASS

```
$ curl -D- http://127.0.0.1:8792/api/support_bundle
HTTP/1.0 200 OK
Content-Type: application/gzip
Content-Disposition: attachment; filename="ga100-fuse-support-20261122T005734.tar.gz"
Content-Length: 102208
Cache-Control: no-store
```

Filename is UTC (matches Date header 00:57:34 GMT). Members:

```
support/console.log
support/dumps/0000:01:00.0/20261121-052539/dump.json   (…052540…052543)
support/goldilocks.jsonl
support/interpretation.txt
support/last-preview.json
support/live_snapshot.json
support/manifest.json
support/system.txt
```

- Exactly 5 dump dirs; the OLDEST seeded dir 20261121-052538 is the one
  dropped; `manifest.truncated == ['0000:01:00.0/20261121-052538']`. Dumps
  emitted oldest-first (tar written in sorted order = ascending ts).
- manifest.json keys: bdfs, built_at, host, members, note, tool_git_sha,
  truncated, warnings — all contract fields present. tool_git_sha ==
  ffbd97d2… (HEAD), built_at UTC, host = hostname/kernel/python,
  note = "contains board serials and PCI info; no credentials".
- interpretation.txt: `totals: sm_now=70 sm_max=126 …` for the card1-derived
  dumps AND `defect source: FF words from hex window (0x8205ac)` — matches
  my own offline `fd.tpc_summary` run on /tmp/card1_fuse_dump.json
  (sm_max=126, ff_seen=[0x8205ac]).
- hex_window member: seeded `hex_window_0x820000.txt` in kept dir 052543 →
  `support/dumps/0000:01:00.0/20261121-052543/hex_window_0x820000.txt`
  present on re-fetch.
- live_snapshot.json: valid JSON dict (mock card1 probe view).
- system.txt: lspci-stanza section + dmesg-tail section present (this host
  has no GA100 stanza / no matching dmesg → honest "(none)" placeholders,
  structure correct).

## Check 3b — 25 MiB cap with oldest-drop — PASS

Padded 4 kept dumps to ~7 MiB each (~35 MiB total):

```
$ curl … /api/support_bundle   -> 200
truncated: ['0000:01:00.0/20261121-052539', '0000:01:00.0/20261121-052538']
dump members kept: 052540, 052542, 052543
uncompressed total: 21.4 MiB (cap 25)
```

Oldest dropped first, every drop recorded in manifest.truncated.

## Check 4 — edge cases — PASS

(a) Empty state dir, second instance port 8793 (PID 2365646):
`empty-state:200`, warnings = ["console.log not present in state dir",
"goldilocks.jsonl not present in state dir", "last-preview.json not present
in state dir"], truncated=[], no crash.

(b) Corrupt dump (garbage written to 052541/dump.json):
`corrupt-run:200` — no 500. manifest.warnings =
["dumps/0000:01:00.0/20261121-052541/dump.json unreadable: Expecting value:
line 1 column 1 (char 0)"]. The bad dump is skipped from interpretation.txt;
the failure is recorded in manifest.warnings (contract allows either).

(c) Concurrent GET (2 threads): `concurrent: [(200, 85790), (200, 85790)]`
— both full-length archives.

(d) `GET /` dashboard: line 348-349 of served HTML contain
`<a class="topbadge" href="/api/support_bundle" …>Support bundle</a>`.

(e) Path traversal: `tar tzf | grep -vc '^support/'` → 0; every member
(including all dir names) starts with `support/`.

## Check 5 — secret scan — PASS (one note)

`grep -r 'khankhan'` and `'GITHUB_TOKEN'` over all three extracted bundles:
0 hits. service.py contains no `os.environ`/`getenv` reads at all, so the
code cannot inject env credentials.
NOTE (finding-level, not a fail): system.txt embeds dmesg lines verbatim and
console.log/goldilocks.jsonl are bundled verbatim (tail 2 MiB) — if an
operator's dmesg or console log ever contained a secret, the bundle would
carry it. Inherent to log bundling; manifest note says "no credentials".

## Check 6 — docs — PASS

docs/CONSOLE.md line 338: "## Submitting a support bundle" section describing
manifest fields, newest-5 + 25 MiB drop rule. README.md line 50: feature
bullet "One-click **Support bundle** download…".

## Check 7 — teardown — PASS

Killed by PID: `kill 2364866 2365646`; both confirmed gone via `ps -p`.

## Findings

1. (Minor, informational) Verbatim dmesg/console.log inclusion is a
   theoretical secret-leak path (see Check 5 note). No code change demanded.
2. (Informational) Corrupt dumps still occupy a slot in the newest-5 window
   and in truncated accounting (they are counted, then skipped from the
   archive) — a bundle can contain 4 dumps while 5 "kept". Behaviour is
   safe and recorded in warnings; noted only as observed semantics.

No hard failures. No contract violation found.

VERDICT: PASS
