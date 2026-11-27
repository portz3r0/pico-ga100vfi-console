# TASK 64 — Per-die audit of HP card …075's partial burn + prep the completion plan to A100 80GB

Zero-context builder agent; everything you need is here.

## Mission
HP bench card serial 1332021030075 (BDF 0000:03:00.0) was partially burned on 2026-11-26 evening: DEVID column fuses + FF records off13–off27 + Gen4 words + IFF SS0/SS1 macro rows landed; the DEVIDA/DEVIDB value words (ch2 off37/off38) were NOT burned. It now reports 10240 MiB because the CMP VBIOS memory table × unlocked geometry. Your job: (1) audit the burned state against THIS die's own defect map — prove no defective unit was enabled; (2) verify what's actually missing; (3) produce the ordered completion plan (final 2 FF records + cold boot + A100 VBIOS flash) as a proposal doc. NOTHING gets executed on hardware.

## Access
- HP: `sshpass -p 'khankhan' ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no administrator@192.168.0.175 '<cmd>'` — READ-ONLY (sudo pw `khankhan` for reading /root). No writes, no service restarts, no register access. scp DOWN only.
- Key artifacts on HP: `/root/ga100-fuse-view/dumps/sn-1332021030075/20261126-214047/dump.json` (rows + status + lspci_vv + nvidia_smi) and `hex_window_0x820000.txt` (full 0x820000–0x826000 register snapshot as hex — the defect registers live here). scp both to /tmp/t64/.
- Reference (read locally): `/home/raza/nvidia/pico-ga100vfi/evidence/60-gpu2-burn-truth.md` (razk formats, batch2 record list, order rule), `/home/raza/nvidia/pico-ga100vfi/plans/hp-9272-plan.md` (sibling plan — same feature set, template for style + FF word decode), `/tmp/gpu2/parse.py` (FF decode helpers). Console source for field names: `host/ga100vfi/console/service.py` FF_FIELDS (grep, ≤60-line ranges).

## Deliverable 1 — per-die audit (evidence LOCAL: /home/raza/nvidia/pico-ga100vfi/evidence/64-hp075-audit.md, append incrementally)
1. Parse the dump: full 512-row image, factory FF stream (last-occupied 300), burned rows 301–312 + 484–487 (already identified: off13 0x0000, off14 0x0008, off15 0, off16 0, off19 0x4200, off20 0x1800, off23 0, off26 0, off27 0, ch2 off39 0x0582, off47 0x0051, off49 0x0024; IFF 0x82381FD/0x88888888/0x823823D/0x8).
2. Extract THIS die's defect registers from hex_window_0x820000.txt: GPC_DEFECTIVE 0x8205C4, TPC_DEFECTIVE_GPC0..7 (0x8205C8+... — grep the console source for the exact offsets, e.g. in service.py status register list), FBP_DEFECTIVE, FBPA_DEFECTIVE, FBIO_DEFECTIVE, ROP_L2/PES/NVLINK/SYS_PIPE defective regs, plus the DISABLE shadows 0x820350/0x820364 etc.
3. **Plane-gate audit of the burned image**: reconstruct the final last-wins winner per block (factory stream + burned rows), decode every DISABLE field, and assert each field ⊇ its DEFECTIVE register. Any defective unit newly ENABLED by last night's burn = CRITICAL finding (would explain instability / would forbid proceeding).
4. Verify off5–off12 are genuinely NOT NEEDED on this die: decode the factory winners for off5,6,7,8,9,11,12 — if their DISABLE fields already equal the defective-only mask, the omission is correct; if any healthy unit is still masked there, list it as under-delivered capacity (with the word that would fix it).
5. Verify the IFF macro rows executed: hex window at 0x0082381C should read 0x88888888 and 0x00823820 0x00000008 (SS0/SS1 applied by the fuse walk at sense time). Report actual values.
6. Confirm the DEVID gap: decode ch2 off37/off38 winners (expect factory 0x41840942/0x41840982 → DEVIDA 0x20C2) and the burned column fuses (rows 2/3 0x23FE954C, 6/7 0x96500003, 48/49 …FDFF6). Explain the 10240 MiB arithmetic from the dump's own data (live_fbp count × CMP VBIOS per-FBP table).
7. Verdict: SAFE TO PROCEED / findings list.

## Deliverable 2 — completion plan (LOCAL: /home/raza/nvidia/pico-ga100vfi/plans/hp-075-a100-complete.md)
Ordered, per-record, proposal-only:
1. Preconditions: fresh dump with driver detached (executor gate requires BASE == live IDV2; the 21:40 dump predates nothing but is a day old); cold boot first if link degraded; Goldilocks via glitch (…075's own found profile from HP history/console journals — grep the goldilocks.jsonl on HP read-only for its successful attempt profile).
2. The two completion records with EXACT placement: rows must go AFTER the last burned row (312) → rows 313 (off37 `0x416A0942`) and 314 (off38 `0x416A0982`), two-step inert→armed each (chain=0 word verified, then chain bit). Verify against the console's ff_policy rules (bit5 ban, per-block last-wins, IFF start −1 = 487) and state why legal. Note DEVIDB (off38) is vGPU/SR-IOV-oriented — batch2 burned it, parity says burn it; flag it as the one record the owner could veto.
3. SW-IFF pre-proof: volatile-write the two words, confirm DEVIDA shadow 0x8204D8 reads 0x20B5 and nothing else moves, power-cycle reverts.
4. Burn → cold cycle → **expected no-POST on CMP VBIOS** (state this loudly — it is not a brick) → nvflashk A100 80GB PCIe VBIOS (HPE updater image extracts cleanly; keep stock VBIOS dump for recovery — CHECK whether a stock VBIOS dump for …075 exists on the HP or in the repo and say so) → cold boot → verify: nvidia-smi A100 80GB / 81920 MiB, LnkSta Gen3/4, SM count, ECC visibility caveats (InfoROM graft needed for counters — out of scope, note it).
5. Risks: what's still unknown about …075 (anything the audit couldn't settle), the SS0/SS1 rows already burned (IFF start already moved 488→484 — placement implications for future records), DEVIDB veto point, recovery path at each step.

## Hard rules
- READ-ONLY on HP; local writes only under /tmp/t64 + the two deliverable files.
- Context discipline: parse with a script (extend /tmp/gpu2/parse.py), never dump 512 rows into context; evidence appended incrementally.
- Finish: print `TASK64_DONE` + 10-line summary (must state: plane-gate verdict, off5-12 verdict, SS0/SS1 verification, 10240 arithmetic confirmed?, plan path, top risk).
