# TASK 05 — Support-bundle gap fixes: working lspci stanzas + NVML snapshot member

Work ONLY this task. Repo /home/raza/nvidia/pico-ga100vfi, branch fuse-console (HEAD d41de67).
Zero prior context; everything needed is here.

## Findings from a real bundle (AI2, 2026-11-22) — fix exactly these
1. system.txt lspci section printed "(no GA100 device stanzas on this host)"
   while dmesg showed two 10de:20b5 devices. Root cause: the stanza matcher in
   support_bundle()'s system-info path greps `lspci -vv` output for the hex IDs
   (10de:20c2 etc.), but plain `lspci -vv` does NOT print hex IDs. Fix: run
   `lspci -nn -vv` (argv list) and match stanzas on the hex device IDs which
   -nn puts in the first line, e.g. [10de:20c2]/[10de:20b5]/[10de:2082].
   Keep the existing stanza-splitting approach; only the command + match
   predicate change. Verify the "no stanzas" fallback still prints when truly none.
2. Add member `support/nvidia_smi.txt`: when the nvidia driver is bound, run
   `nvidia-smi --query-gpu=index,name,serial,vbios_version,driver_version,
   compute_cap,multiprocessor_count,clocks.sm,clocks.mem,power.limit,
   pcie.link.gen.current,pcie.link.width.current --format=csv` (argv list,
   timeout 15s, tolerate absence/failure -> file says "nvidia-smi unavailable:
   <reason>"). Reuse the existing sh() helper and the bdf->index mapping logic
   already used by /api/gpu (grep "nvidia-smi" service.py; there is an
   --id 8-hex-digit domain form — reuse it, target the console's bdf(s) only).
   When driver unbound: "driver unbound — nvidia-smi not applicable".
3. console.log noise: in the request logger, skip logging GETs to
   /api/live, /api/glitch/status, /api/gpus (the 1s poll trio) — log everything
   else as today. This makes the log tail actually informative. Keep a
   one-line "polling N requests" summary every 300s so silence is provable.

## Gates (run yourself; paste trimmed outputs into evidence)
- py_compile service.py.
- Mock instance port 8794, temp state dir: GET /api/support_bundle -> extract;
  system.txt lspci section: on THIS machine (no GA100) it must still print the
  honest "(no GA100 device stanzas...)" line — then ALSO prove the matcher:
  run `lspci -nn -vv` locally, confirm your predicate matches a synthetic
  stanza containing "[10de:20b5]" (unit-test the split/match function directly
  with a fixture string; put the fixture + result in evidence).
- nvidia_smi.txt member exists on the mock (driver state on this host: check
  `lsmod | grep -c nvidia` — either branch is acceptable, file must exist and
  say the right thing).
- Poll-noise: run mock 6s with a curl loop hitting /api/live 10x + /api/full
  once; console.log must NOT contain the poll trio lines but MUST contain the
  /api/full line.
- GET / 200; kill instance by PID.

## Deliverables
- Commit on fuse-console: `console: support bundle — lspci -nn matcher, nvidia_smi.txt member, quieter poll log`
- Push: source ~/.hermes/.env && git push https://x-access-token:${GITHUB_TOKEN}@github.com/portz3r0/pico-ga100vfi-console.git HEAD:refs/heads/fuse-console (no force).
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/05-bundle-gaps.md incremental.
- stdout summary ending with exact line GAPS_DONE.

## Hard rules
- Only host/ga100vfi/console/service.py (+ docs/CONSOLE.md member list line if
  it enumerates members). No firmware/, no AI2 access, no force push.
- stdlib only. Context discipline: grep -n then sed -n ranges <= 80 lines;
  service.py is ~2.7k lines — never cat it whole.
