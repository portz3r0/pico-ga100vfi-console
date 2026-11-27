# TASK 02 — Support-bundle log collection for the Fuse Console

Branch: `fuse-console` (base commit ceb4ea9, task 01 synced tree).

## Design notes (before coding)

- New endpoint `GET /api/support_bundle` in `host/ga100vfi/console/service.py`,
  served through the existing `Handler.do_GET` (its generic `except` already
  yields 500 + `{"error": ...}` JSON, satisfying the error contract).
  The tar.gz is built fully in memory (`tarfile` over `io.BytesIO`) before any
  byte is sent — never a partial download.
- `support_bundle()` members (all under `support/` in the tar):
  - `manifest.json` — tool_git_sha (`git -C <repo root> rev-parse HEAD`,
    regex-validated, fallback `"unknown"`), built_at ISO-UTC, host
    {hostname, kernel, python}, bdfs, members [{path, bytes}], truncated,
    warnings, note.
  - `console.log`, `goldilocks.jsonl` — tail 2 MiB each (`_tail_bytes` seeks
    to size-2MiB); `last-preview.json` if present. Missing files -> warning.
  - `dumps/<rel>/<ts>/dump.json` + `hex_window_0x820000.txt` for the NEWEST 5
    dump dirs by mtime, emitted oldest first. `os.walk` over `dumps_dir()`
    for dirs containing `dump.json` covers BOTH on-disk layouts the service
    writes (`dumps/<ts>` for the default BDF, `dumps/<bdf>/<ts>` otherwise);
    the tar keeps the on-disk relative path. dump.json bytes copied verbatim.
  - `live_snapshot.json` — extracted `live_snapshot()` from the `/api/live`
    default-card branch; the route now calls the same function, so the bundle
    member is literally the same code path (may be `{"paused": ...}` — valid).
  - `system.txt` — `lspci -vv` stanzas whose header line matches
    10de:20c2/20b5/2082 + `dmesg -T` lines matching `nvrm|nvidia|20c2|20b5`
    (tail 200). argv-list `sh()` (timeout 15 s); absence tolerated (sh()
    returns `<<...>>` text, no exception).
  - `interpretation.txt` — for each bundled dump: re-run
    `fusedump.tpc_summary(shadow, hexnonzero)`; print totals (sm_now, sm_max,
    sm_defective, sm_recoverable, tpc_*), per-GPC one-liners, the defect-word
    source actually used ("FF words from hex window @ addrs" when any
    `fd.TPC_DEFECT_FF` address appears in hexnonzero, else "shadow keys
    (legacy)"), ceilings, crc_ok, fingerprint. Self-describing header explains
    how to replay offline.
- Size cap: total uncompressed <= 25 MiB. Dump dirs are grouped; while the
  total exceeds the cap the OLDEST group is dropped and recorded in
  `manifest.truncated`. Logs are already tail-capped at 2 MiB each.
- UI: header link "Support bundle" next to the existing `.topbadge` in
  `gui.py` (reuses the badge styling), href `/api/support_bundle`, exact
  title tooltip from the contract. No tracked `live.html` exists in the repo
  (`git ls-files` empty for it — it is generated into the state dir), so
  gui.py is the single edit surface.
- Docs: `docs/CONSOLE.md` new section "Submitting a support bundle" + API
  table row; README one bullet under the Fuse Console features; service.py
  top-of-file route docstring updated (sources-of-truth table in AGENTS.md).
- Verification: local mock run `python3 -m ga100vfi.console --mock
  /tmp/card1_fuse_dump.json --port 8791 --state-dir /tmp/bundle-state`,
  seeded fixtures, curl + tar + json.tool gates, interpretation asserts
  (`sm_max=126`, defect-source line), dashboard HTML assert, PID-based kill.

## Gate log

(will be appended step by step)

## Gate log

### py_compile
```
$ python3 -m py_compile host/ga100vfi/console/service.py host/ga100vfi/console/gui.py
COMPILE_OK
```

### Local mock run (port 8791, temp state dir)
```
$ PYTHONPATH=host python3 -m ga100vfi.console --mock /tmp/card1_fuse_dump.json \
    --port 8791 --listen 127.0.0.1 --state-dir /tmp/bundle-state
ga100vfi fuse console on 127.0.0.1:8791  bdf=0000:41:00.0  html=/tmp/bundle-state/live.html  dumps=/tmp/bundle-state/dumps  poll=1.0s  mock=True
```
Seeded /tmp/bundle-state: console.log fixture, goldilocks.jsonl fixture,
last-preview.json (copied from ~/ga100-fuse-view), and
/tmp/card1_fuse_dump.json as dumps/0000:01:00.0/20261121-052538/dump.json
(written as-is; hex_window_0x820000.txt regenerated from its hexnonzero,
3787 lines).

### Download headers + tar listing
```
$ curl -sD- http://127.0.0.1:8791/api/support_bundle -o /tmp/b.tgz
HTTP/1.0 200 OK
Content-Type: application/gzip
Content-Disposition: attachment; filename="ga100-fuse-support-20261122T004918.tar.gz"
Content-Length: 47591
Cache-Control: no-store

$ tar tzf /tmp/b.tgz
support/console.log
support/dumps/0000:01:00.0/20261121-052538/dump.json
support/dumps/0000:01:00.0/20261121-052538/hex_window_0x820000.txt
support/goldilocks.jsonl
support/interpretation.txt
support/last-preview.json
support/live_snapshot.json
support/manifest.json
support/system.txt
```
All contract members present. `python3 -m json.tool support/manifest.json`
-> MANIFEST_JSON_VALID (tool_git_sha=ceb4ea9b5c96..., built_at ISO-UTC,
host{hostname, kernel, python}, bdfs [0000:01:00.0, 0000:41:00.0],
members[{path,bytes}], truncated [], warnings [], note as contracted).

### interpretation.txt asserts (card1 dump)
```
defect source: FF words from hex window (0x8205ac)
totals: sm_now=70 sm_max=126 sm_defective=2 sm_recoverable=56 tpc_defective=1 tpc_recoverable=28
gpc0: sm_now=0 sm_max=16 ... gpc_disabled=1   (per-GPC one-liners x8)
crc_ok: True  fingerprint: 28b5ee381a44e79b
```
sm_max=126 asserted (golden-die ceiling; the 74-SM misread class of bug).
Defect-source line present and names the FF hex-window word actually found.

### system.txt on a host without the card (absence tolerated)
```
$ lspci -vv  (stanzas matching 10de:20c2 10de:20b5 10de:2082)
(no GA100 device stanzas on this host)

$ dmesg -T  (lines matching nvrm|nvidia|20c2|20b5, tail 200)
(no matching lines — dmesg unavailable or clean)
```
(this test host has no NVIDIA device and dmesg is permission-denied; the
bundle still builds — absence tolerated, and the file says why it is empty)

### Newest-5 rotation + truncated
Seeded 7 dump dirs with staggered mtimes -> tar carried exactly the newest
5 (oldest first: 20261203..20261207) and
`manifest.truncated == ['0000:01:00.0/20261121-052538', '0000:01:00.0/20261202-000000']`.

### Dashboard HTML
```
$ curl -s http://127.0.0.1:8791/ | grep -c "Support bundle"
1
```
(served generated live.html contains the header link with the exact title
tooltip)

### Kill
```
$ PID=$(ss -ltnp | grep 8791 | grep -oP 'pid=\K[0-9]+'); kill $PID   # pid=2361649
$ ss -ltn | grep 8791 || echo PORT_FREE
PORT_FREE
```

### Diff stat
```
 README.md                        |   3 +
 docs/CONSOLE.md                  |  30 +++++
 host/ga100vfi/console/gui.py     |   6 +-
 host/ga100vfi/console/service.py | 243 ++++++++++++++++++++++++++++++++---
 4 files changed, 269 insertions(+), 13 deletions(-)
```
No tracked live.html in the repo (generated into the state dir at startup),
so gui.py is the single HTML source — nothing to mirror.

## Commit / push

(appended below)

- Commit: `ffbd97d` — `console: support bundle — one-click logs + dumps +
  interpretation trace` (4 files, +269/-13; staged only the four task files;
  pre-existing dirty `firmware/pwmvid.c` left untouched).
- Push (no force): `ceb4ea9..ffbd97d  HEAD -> fuse-console` to
  portz3r0/pico-ga100vfi-console.
- Push verification: `git ls-remote ... refs/heads/fuse-console` ->
  `ffbd97d2fd3dc062f72435a1538e379d40726ab5  refs/heads/fuse-console`.
- Not deployed (deploy happens later); AI2 untouched.
