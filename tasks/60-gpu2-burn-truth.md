# TASK 60 — Decode the GPU2 burn on the HP bench: what was burned, in what order (READ-ONLY on HP)

Zero-context builder agent; everything you need is here.

## Mission
The HP bench host ran a real fuse burn on its CMP 170HX using the razk-batch toolchain in `/home/administrator/nvidia/GPU2/`. Reconstruct the COMPLETE ground truth: every record burned, the exact order, and the actual before/after fuse delta — then compare against our skill records and flag everything our records lack. The user suspects our skill library is missing crucial information about this burn; your delta table decides that.

## Access (HP bench)
- `sshpass -p 'khankhan' ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no administrator@192.168.0.175 '<cmd>'`
- HARD RULE: READ-ONLY on the HP. No writes, no sudo, no service restarts, no register access. `cat`/`python3` on files is fine. Pipe every remote output through `head`/`sed -n` (≤60 lines per read; the .py files are ~500 lines — read them in ranges or scp them down).
- You may `scp` files DOWN to `/tmp/gpu2/` (local) with the same sshpass/ssh options plus `-o` equivalents; analyze locally. NEVER copy anything TO the HP.

## The artifacts (all in /home/administrator/nvidia/GPU2/)
```
ga100_burn.py        (21 KB)  the burn driver — parse its ORDER logic
ga100_dump.py        (19 KB)  dump format reader
razk-batch2.bin      (4448 B) the signed burn plan binary — decode its record list
ga100-dump-20261118T145659Z-d930c730.bin (104861 B)  PRE-burn dump (Nov 18)
dump_9272_20261126T113515Z.bin           (104717 B)  POST-burn dump (Nov 26, card serial ...9272)
ga100_plan.pub.pem / plan_sign.key*                   signature material (note format only, no crypto work)
```

## Deliverables (evidence file LOCAL: /home/raza/nvidia/pico-ga100vfi/evidence/60-gpu2-burn-truth.md, append incrementally)
1. **Bin formats**: from ga100_dump.py/ga100_burn.py source (cite file:line), document the razk-batch2.bin record format and the dump .bin format, then PARSE both dumps + the plan with a local python script (write it under /tmp/gpu2/).
2. **Plan record list**: every record in razk-batch2.bin — row, 32-bit word, and decode each FF word as `data16<<16 | offset10<<6 | chain5` → chain, offset, data, and the feature it sets (use the decode table in `/home/raza/.hermes/skills/hardware-optimization/ga100-fuse-burn-plan/references/allspark-deltas.md` and the FF_FIELDS catalog in `/home/raza/nvidia/pico-ga100vfi/host/ga100vfi/console/service.py` (grep FF_FIELDS; read ≤60-line ranges) for names).
3. **Burn ORDER**: from ga100_burn.py's control flow — does it burn plan order? phases? where do column fuses (ECC rows 6/7, row remapper 48/49, vGPU 22/23, OpenGL, FP64, TTU) go relative to FF rows? Cite the code path.
4. **ACTUAL delta**: diff pre vs post dumps row-by-row → the list of rows that actually changed with before/after values. Cross-check: plan records vs actual delta — anything burned that is NOT in the plan, or planned but not landed?
5. **Card identity**: serial, DEVID before/after (is it rebranded? lspci on HP still says CMP 170HX — check DEVIDA in the post dump), SM/memory state implied by the post dump.
6. **DELTA vs OUR RECORDS**: compare the reconstructed burn (records + order) against (a) `~/.hermes/skills/hardware-optimization/ga100-fuse-burn-plan/SKILL.md` + `references/allspark-deltas.md`, (b) `~/.hermes/skills/hardware-optimization/pico-ga100vfi/SKILL.md`. Table: item | GPU2 truth (evidence) | our record says | verdict MISSING/WRONG/EQUAL. This is the user's core question — be adversarial, assume our records ARE lacking.
7. Note the driver state on HP (`lsmod | grep nvidia`, `lspci -s 03:00.0 -vv | grep -E 'Region 1|Kernel driver'` | head) — read-only, for the next task.

## Hard rules
- READ-ONLY on HP (rule above); local writes only under /tmp/gpu2/ and the evidence file.
- Context discipline: never cat a 21 KB py file whole into context — scp it down and grep/sed ranges; never re-read a captured region.
- Commit nothing; no git operations in the repo except reading.
- Finish: print `TASK60_DONE` + 10-line summary (must state: N records in plan, N rows actually changed, order rule found, top-3 gaps vs our records).
