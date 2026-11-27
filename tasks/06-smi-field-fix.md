# TASK 06 — Fix nvidia_smi.txt query: multiprocessor_count is not a valid nvidia-smi field

Work ONLY this task. Repo /home/raza/nvidia/pico-ga100vfi, branch fuse-console (HEAD 32d6563).

## Verified finding (AI2 hardware, driver 620.70.06, 2026-11-22)
support/nvidia_smi.txt member prints:
  "nvidia-smi unavailable: Field \"multiprocessor_count\" is not a valid field to query."
The field does not exist in nvidia-smi's query vocabulary on ANY driver — the member
is broken everywhere. Fix nvidia_smi_txt() in host/ga100vfi/console/service.py:
1. Remove multiprocessor_count from the --query-gpu list.
2. Keep all other fields (index,name,serial,vbios_version,driver_version,compute_cap,
   clocks.sm,clocks.mem,power.limit,pcie.link.gen.current,pcie.link.width.current).
3. SM count is still wanted: append a second command section running
   `nvidia-smi -q` filtered to the SM-relevant lines is NOT reliable — instead
   append a static note line: "# SM count: see live_snapshot.json / interpretation.txt
   (SM count is a CUDA/NVML attribute, not an nvidia-smi query field)".
4. The failure-detection logic must keep working: if nvidia-smi still errors for
   another reason (e.g. no devices), the "nvidia-smi unavailable: <reason>" branch
   must trigger — verify by running the query WITHOUT --id against a host state
   where it works (this host has no GPU: any nvidia-smi call fails -> file must
   contain the unavailable line, not a traceback).

## Gates (paste trimmed outputs into evidence)
- py_compile service.py.
- Run the exact new argv query on THIS host: nvidia-smi absent or no devices ->
  confirm the unavailable branch text appears (no traceback).
- Field-list sanity: grep the committed query for multiprocessor_count -> 0 hits;
  grep for the note line -> 1 hit.
- Mock instance :8795 temp state dir: GET /api/support_bundle -> extract,
  nvidia_smi.txt exists with correct branch text; GET / 200; kill by PID.
- On a GPU host the query fields must all be valid — cross-check each field name
  against `nvidia-smi --help-query-gpu` output on THIS host if the binary exists
  (grep each field; if nvidia-smi absent here, state that in evidence and rely
  on the AI2 redeploy verification done by the orchestrator).

## Deliverables
- Commit: `console: support bundle — drop invalid multiprocessor_count smi field`
- Push: source ~/.hermes/.env && git push https://x-access-token:${GITHUB_TOKEN}@github.com/portz3r0/pico-ga100vfi-console.git HEAD:refs/heads/fuse-console (no force).
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/06-smi-field-fix.md incremental.
- stdout summary ending with exact line SMI_DONE.

## Hard rules
- Only host/ga100vfi/console/service.py. No AI2 access, no firmware, no force push.
- stdlib only. grep -n then sed -n ranges <= 60 lines; never cat service.py.
