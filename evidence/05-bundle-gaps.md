# Task 05 — support-bundle gap fixes (2026-11-22)

Changes (host/ga100vfi/console/service.py + docs/CONSOLE.md member list only):

1. **lspci matcher** — `system_txt()` now runs `lspci -nn -vv` (argv list) and
   matches stanzas on the bracketed hex IDs (`[10de:20c2]`/`[10de:20b5]`/
   `[10de:2082]`) that `-nn` puts on the first line; plain `lspci -vv` prints
   no hex IDs (AI2 bundle, 2026-11-22). Split/match extracted into
   `lspci_ga100_stanzas(text)` (same stanza-splitting approach as before);
   the "(no GA100 device stanzas on this host)" fallback kept.
2. **`support/nvidia_smi.txt` member** — `nvidia_smi_txt(bdfs)` targets the
   console's BDF via the same 8-hex-digit `--id=` domain form as `/api/gpu`;
   query = index,name,serial,vbios_version,driver_version,compute_cap,
   multiprocessor_count,clocks.sm,clocks.mem,power.limit,
   pcie.link.gen.current,pcie.link.width.current, `--format=csv`, timeout 15 s
   through `sh()`. Module absent -> "driver unbound — nvidia-smi not
   applicable" (never call nvidia-smi unloaded: NVML auto-loads, see
   gpu_info). Absence/failure -> "nvidia-smi unavailable: <reason>".
3. **Poll-noise** — `log_message` skips GETs to /api/live, /api/glitch/status,
   /api/gpus (exact path, query stripped; /api/gpus/all still logged) and
   emits one "polling: N requests ... in 300s" summary per POLL_SUMMARY_S=300.
   Judged from `self.command`/`self.path` — the stdlib format string quotes
   the request line, so parsing `format % args` is brittle (first mock run
   proved it: `"GET` never matched).

## Gate evidence (all run 2026-11-22 on this host, no GA100, `lsmod | grep -c nvidia` -> 0)

### py_compile
```
$ python3 -m py_compile host/ga100vfi/console/service.py
PY_COMPILE_OK
```
(An earlier iteration emitted SyntaxWarning `\u` in a bytes literal; fixed to
`"...".encode()` and recompiled clean.)

### Matcher unit test — synthetic fixture with [10de:20b5]
Fixture: 4 stanzas — GA100 [10de:20b5] (3 lines), Intel Ethernet [8086:15f3],
GA100 [10de:20c2] (2 lines), NVIDIA audio [10de:10fa] (must NOT match).
```
matched stanzas: 2
 FIRST: 01:00.0 VGA compatible controller [0300]: NVIDIA Corporation GA100 [10de:20b5] (rev a1) | lines: 3
 FIRST: 41:00.0 3D controller [0302]: NVIDIA Corporation GA100 [10de:20c2] (rev a1) | lines: 2
MATCHER_UNIT_OK
```
Also asserted: non-GA100-only input -> []. Live `lspci -nn -vv` on this host
parses without error, 0 GA100 matches (correct: none present).

### Mock instance (port 8794, temp state dir, --mock fulldump-now/dump.json)
```
GET / -> 200
$ tar tzf bundle.tar.gz
support/interpretation.txt
support/live_snapshot.json
support/manifest.json
support/nvidia_smi.txt
support/system.txt
```
system.txt head (honest fallback on this no-GA100 host):
```
$ lspci -nn -vv  (stanzas matching [10de:20c2] [10de:20b5] [10de:2082])
(no GA100 device stanzas on this host)
```
nvidia_smi.txt (driver unbound branch — matches lsmod count 0):
```
driver unbound — nvidia-smi not applicable
```
manifest.json members list includes `nvidia_smi.txt`.

### Poll-noise (curl loop: /api/live x10, /api/full x1)
console.log after the loop:
```
ga100vfi fuse console on 0.0.0.0:8794 ... mock=True
14:13:35 "GET / HTTP/1.1" 200 -
14:13:35 "GET /api/support_bundle HTTP/1.1" 200 -
14:13:35 "GET /api/full HTTP/1.1" 200 -
```
No /api/live lines; /api/full present. (First pre-fix run logged all 10
/api/live lines — the quoted-requestline bug above.)

### Summary branch (300 s window can't elapse in a 6 s run; forced in-process)
With `POLL_SUMMARY_S = 0` and 5 poll requests through `Handler.log_message`:
```
14:13:48 polling: 1 requests (/api/live, /api/glitch/status, /api/gpus) in 0s
(x5 — window of 0 flushes per request; counter resets after each flush)
```
Suppression + summary line + counter reset all exercised.

### Cleanup
Mock instance killed by PID (2399366, and the earlier 2398870).

## Not verified on hardware
All gates are host-side; no card, no rig access (per task rules).
