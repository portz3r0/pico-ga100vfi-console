# Task 06 — drop invalid multiprocessor_count smi field

Date: 2026-11-22. Branch fuse-console, base 32d6563, commit aa942db
(`console: support bundle — drop invalid multiprocessor_count smi field`),
pushed 32d6563..aa942db to fuse-console (no force). Only file changed:
`host/ga100vfi/console/service.py`.

## Change

- `SMI_FIELDS`: removed `multiprocessor_count` from the `--query-gpu` list;
  all other fields kept (index,name,serial,vbios_version,driver_version,
  compute_cap,clocks.sm,clocks.mem,power.limit,pcie.link.gen.current,
  pcie.link.width.current).
- New `SMI_SM_NOTE` constant, appended as the last line of
  `nvidia_smi_txt()` output:
  `# SM count: see live_snapshot.json / interpretation.txt (SM count is a
  CUDA/NVML attribute, not an nvidia-smi query field)`.
- Failure-detection branch (`nvidia-smi unavailable: <reason>`) untouched.

## Gate 1 — py_compile

```
$ python3 -m py_compile host/ga100vfi/console/service.py
COMPILE_OK
```

## Gate 2 — exact new argv query on THIS host (no GPU, driver module absent)

```
$ nvidia-smi --id=00000000:01:00.0 --query-gpu=index,name,serial,vbios_version,\
driver_version,compute_cap,clocks.sm,clocks.mem,power.limit,pcie.link.gen.current,\
pcie.link.width.current --format=csv
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. ...
rc=9
```

Function-level check of the unavailable branch (this host has no
`/sys/module/nvidia`, so the module-exists guard is stubbed True to reach the
query loop; the real `nvidia-smi` failure text lands in the branch, no
traceback):

```
$ nvidia_smi_txt({"0000:01:00.0"})   # /sys/module/nvidia stubbed present
$ nvidia-smi --id=<bdf> --query-gpu=index,name,serial,vbios_version,driver_version,compute_cap,clocks.sm,clocks.mem,power.limit,pcie.link.gen.current,pcie.link.width.current --format=csv
0000:01:00.0: nvidia-smi unavailable: NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver. ...
# SM count: see live_snapshot.json / interpretation.txt (SM count is a CUDA/NVML attribute, not an nvidia-smi query field)
BRANCH_OK
```

## Gate 3 — field-list sanity (committed file)

```
$ grep -c multiprocessor_count host/ga100vfi/console/service.py
0
$ grep -c 'SM count: see live_snapshot.json' host/ga100vfi/console/service.py
1
```

## Gate 4 — mock instance :8795, temp state dir

```
$ PYTHONPATH=host python3 -m ga100vfi.console --mock /tmp/card1_fuse_dump.json \
    --port 8795 --listen 127.0.0.1 --state-dir /tmp/sb06 --bdf 0000:01:00.0
GET /                    -> 200
GET /api/support_bundle  -> 200
$ tar -tzf bundle.tar.gz | grep nvidia_smi
support/nvidia_smi.txt
$ tar -xzOf bundle.tar.gz support/nvidia_smi.txt
driver unbound — nvidia-smi not applicable
```

Correct branch for this host state (nvidia module absent — the pre-existing
early return fires before any nvidia-smi call, as designed). Killed the
service by PID (2408851, confirmed listener via `ss -ltnp`); port 8795 free
afterwards.

## Gate 5 — field-name cross-check

`nvidia-smi` exists on this host (`/usr/sbin/nvidia-smi`) but errors
"couldn't communicate with the NVIDIA driver" even for `--help-query-gpu`,
so per-field vocabulary cross-check is NOT possible here. The remaining 11
field names are the pre-existing set that worked on AI2 apart from the
dropped one; final field-validity confirmation is deferred to the
orchestrator's AI2 redeploy.

## Notes / drift flagged (not edited — task scope is service.py only)

- `docs/CONSOLE.md:358-359` still lists "SM count" among the nvidia_smi.txt
  snapshot contents; it is now a pointer note, not a queried field. Needs a
  doc follow-up.
- `firmware/pwmvid.c` was already modified in the worktree (pre-existing,
  not staged, not committed here).

SMI_DONE
