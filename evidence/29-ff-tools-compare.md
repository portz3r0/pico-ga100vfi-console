# Task 29 — kprinssu/ga100-ff-tools planning vs our console planner (READ-ONLY)

**Date:** 2026-11-23 (AEDT)
**Theirs:** `/home/raza/.hermes/cache/scratch/ga100-ff-tools` @ `594e83d` ("Add the post-unlock benchmark suite and docs") — cited as `T:<path>:<line>`.
**Ours:** `/home/raza/nvidia/pico-ga100vfi` branch `main` @ `1c62ac0`, read via `git show main:<path>` only — cited as `O:<path>:<line>`.
No files in either repo were modified; only this evidence file was written. No hardware touched.

---

## 1. What their planner does

### 1.1 Defect reading — `planner/read_defects.py`
- O_RDONLY + PROT_READ mmap of BAR0 — structurally cannot write the GPU (`T:planner/read_defects.py:31-32`).
- Reads defect masks: `OPT_GPC_DEFECTIVE 0x8205C4`, `OPT_FBP_DEFECTIVE 0x8205CC`, `OPT_FBPA_DEFECTIVE 0x8205D0`, `OPT_FBIO_DEFECTIVE 0x8205D4`, `OPT_PES_DEFECTIVE 0x820698`, `OPT_ROP_L2_DEFECTIVE 0x8205E8`, `OPT_NVLINK_DEFECTIVE 0x82068C` (`T:planner/read_defects.py:13-22`) and per-GPC TPC defect FF words `0x8205C8, 0x820508, 0x82050C, 0x820514, 0x820564, 0x8205AC, 0x820B84, 0x820B80` (`T:planner/read_defects.py:26-27`) — **identical set to our `TPC_DEFECT_FF`** (`O:host/ga100vfi/fusedump.py:108-109`, fleet-verified 13/13 per its comment).
- Identity handling: `PMC_BOOT_0` must not be `0xFFFFFFFF` (abort, `T:planner/read_defects.py:34-36`); a non-GA100 chip id only prints a WARNING to stderr and continues (`T:planner/read_defects.py:37-39`). No sysfs vendor/device gate.

### 1.2 FF dump + decode — `planner/ff_dump.py`
- Dumps FF rows 222–487 via CMD_READ (`T:planner/ff_dump.py:42-43,111-118`); decodes `chain=val&0x1F, iff=bit5, block=(val>>6)&0x3FF, data=val>>16` (`T:planner/ff_dump.py:121-127`) — **matches our encoding exactly** (`O:host/ga100vfi/fusedump.py:24-25`, `O:host/ga100vfi/console/gui.py:615-616`).
- Chain replay is last-wins per block, IFF records skipped (`T:planner/ff_dump.py:130-137`) — same semantics we encode in `O:host/ga100vfi/console/service.py:167-168`.
- Reads shadow option registers incl. `OPT_TPC_DISABLE_GPC{i}=0x820760+4i` and `STATUS_OPT_TPC_GPC{i}=0x820C38+4i` (`T:planner/ff_dump.py:58-60`) — same addresses as our `TPC_FFDIS_BASE`/`TPC_DISABLE_BASE` (`O:host/ga100vfi/fusedump.py:111-112`).
- FF option field map (Kate Land's blog): FBIO 1:83-106, FBPA 1:107-130, GPC 1:131-138, TPC_GPCi 1:187+8i..194+8i, PES 1:251-274, FBP 1:307-318, ROP_L2 1:319-342, NVLINK 1:368-370, SYS_PIPE 1:372-379, DEVIDA/B 2:593-608/609-624 (`T:planner/ff_dump.py:64-77`, `T:README.md:322-332`).
- Guards: warns (does not refuse) when not IDLE or CRC≠0x55 (`T:planner/ff_dump.py:184-186`); per-row timeout recorded as `read_errors` (`T:planner/ff_dump.py:191-196`). **Never checks or clears `EN_SW_OVERRIDE` before the row sweep** (absent from the whole file).

### 1.3 Plan derivation — `planner/ffcard.py` (offline, opens no device)
- Refusals up front: dump read errors, unread rows, coverage of 222–487 (`T:planner/ffcard.py:69-83`); used rows must be contiguous from 222; **any row with IFF bit set → refuse** (`T:planner/ffcard.py:86-98`); rows must replay to the dump's own chains (`T:planner/ffcard.py:170-174`); a missing defect mask is refused, never defaulted to zero (`T:planner/ffcard.py:156-162`).
- `field_plan` sets each FF field **exactly to its DEFECTIVE mask**, merged per block; asserts every changed bit lies inside a target field; a record that would SET bits is flagged `sets_bits` (`T:planner/ffcard.py:123-153`). Last-wins block replacement makes 1→0 field transitions legal via append (`T:planner/ffcard.py:106-113`, `T:README.md:319-320`).
- Four plans: `0_noop` (chain1 block7 re-write, mechanism test), `sm_hbm` (FBIO+FBPA+GPC+PES+FBP+ROP_L2+TPC×8 → defect masks, all in one window), `pcie` (4 chain-2 records, applied only when blocks hold the proven stock values, else the plan is skipped), `nvlink` (`T:planner/ffcard.py:33-57,180-199`, `T:README.md:94-99`).
- DEVID handling: chain 2 blocks 37/38 are FORBIDDEN in every record (`T:planner/ffcard.py:31,145-146`) and checked unchanged in derive/verify (`T:planner/ffcard.py:42-43,232-234,330-335`); stock dump expected `PCIE_DEVIDA 0x20C2` (`T:README.md:79-80`).
- Row selection: append in burn order from the first blank row after the last occupied (`--skip-rows` buffer), rows consecutive, inside 222–487 (`T:planner/ffcard.py:202-217`). **No mirror concept** — one row per record (`T:README.md:319-320`).
- Card identity: baseline = last occupied row + SHA-256 fingerprint of rows 222..last, embedded in every plan (`T:planner/ffcard.py:101-103,176,218-221`); a plan made for another die "writes that die's TPC masks and row numbers onto another" (`T:README.md:53-54`).

### 1.4 In-window check + burn + verify
- `check` (in the window, before burning): requires CRC 0x55 + idle, baseline fingerprint match ("NOT the planned card" otherwise), every plan row blank or already holding exactly its own record, burned records forming a **prefix**, nothing written outside the plans; prints the next record to burn — resume after a lost window (`T:planner/ffcard.py:262-309`).
- `ff_burn.py`: one record per call, dry-run default + typed `BURN`; guards FUSECTRL IDLE, CRC=0x55, DSOV=0, SBFE=0, EFP=1, FUSEWDATA_PLM/FUSECTRL_PLM open, DEBUGCTRL.RWL=0, target row blank (`T:burn/ff_burn.py:91-111`); protocol `FUSECTRL=0 → FUSEADDR → FUSEWDATA=value → CMD_WRITE → poll IDLE → CMD_READ readback`, no retry (`T:burn/ff_burn.py:8-10,168-187`).
- Arming (human-only, volatile writes): `sw_override.py` EN_SW_OVERRIDE=1 with read-back (`T:arm/sw_override.py:20-47`); `open_wdata_plm.py` clears `WDATA_WR_SECURE 0x82048C` to open `FUSEWDATA_PLM` (`T:arm/open_wdata_plm.py:25-63`); `arm_sense_ctrl.py` issues SENSE_CTRL (FUSECTRL=3) with a FUSEWDATA=0 no-burn latch, window checks incl. `RESENSE_DISABLE=0`, post-checks DSOV/CRC/EFP, `--clear-sbfe` (`T:arm/arm_sense_ctrl.py:10-15,104-132,180-207`). **They flag CMD 3 = SENSE_CTRL as "user-supplied … Not confirmed by any source in this repo"** (`T:arm/arm_sense_ctrl.py:10-12`).
- `verify` (post cold boot): every record burned, nothing else written, FF-replayed fields == planned targets, shadow `OPT_*` == targets, defect masks unmoved, SYS_PIPE/DEVID unchanged, notes nonzero `STATUS_OPT_TPC_GPC*` runtime masks ("not a fuse; may cost SMs"), prints first blank row (`T:planner/ffcard.py:312-357`).
- `pcie_state.py`: read-only Gen3/Gen4 shadow targets (`DISABLE_GEN3_SPEED 0x820250=0`, `BOOT_GEN23_DISABLE 0x82057C=0`, `BOOT_GEN3_DISABLE 0x820580=0`, `PCIE_MAGIC_BITS_D 0x820520=0x00200000`) + LnkCap/LnkSta parsed from config space; exit 0 at target (`T:planner/pcie_state.py:18-25,29-43,61-82`).
- Stop rules incl. **"Never power-cycle between sm_hbm records. An SM unlock without the matching PES/ROP_L2 records fails GSP boot"** (`T:README.md:194-196`, provenance `T:SOURCES.md:18-23`).

### 1.5 Post-unlock validation — `bench/sm_stress.py` (+ bench.cu, memtest)
- Hand-written PTX kernel reads `%smid`; blocks on selected SMs run a dense FFMA loop for a fixed clock-cycle budget, others exit; every launch records which SM ids actually received a block — **coverage is checked, not assumed** (`T:bench/sm_stress.py:1-12,39-87,112-128`). `run all 600` stresses; `WARNING … no block reached` = an SM dropped out; bisect `lo/hi`, `q0..q3`, `ids:…` (`T:bench/sm_stress.py:132-151`).
- Bar for "unlocked": no Xid + full SM coverage + memtest_vulkan PASS + bench.cu (80 GiB, 5-stack bandwidth, 16GT/s x16) (`T:README.md:237-303`). `bench.cu` is asm64-hooligan/cmpunlocker's, GPL-2.0-only (`T:SOURCES.md:32-37`).
- Tests: synthetic-only unittests for derive/check/verify/pcie parser (`T:tests/test_tools.py:37-143`, `T:README.md:334-343`).

---

## 2. Delta table (capability → verdict, citations both sides)

| Capability | Verdict | Theirs | Ours |
|---|---|---|---|
| FF record encoding (chain/iff/block/data) | EQUAL | `T:planner/ff_dump.py:121-127` | `O:fusedump.py:24-25`, `O:gui.py:615-616` |
| Last-wins per block | EQUAL | `T:planner/ff_dump.py:130-137` | `O:service.py:167-168`, `O:gui.py:1085-1092` |
| TPC defect FF word set | EQUAL (cross-confirms) | `T:planner/read_defects.py:26-27` | `O:fusedump.py:108-109` (fleet 13/13) |
| Defect-mask read path | EQUAL | O_RDONLY mmap `T:read_defects.py:31-32` | hex window + shadow read `O:fusedump.py:370-379` |
| Dump validity vs EN_SW_OVERRIDE | **WE-BETTER** | never checks/clears EN (`T:ff_dump.py` whole file) | EN=1 ⇒ shadow plane answers CMD_READ with garbage; cleared+restored `O:fusedump.py:16-18,395-423`; same in `O:service.py:921-929` |
| Device identity gate | **WE-BETTER** | PMC_BOOT_0 mismatch = warning only `T:read_defects.py:37-39` | hard sysfs vendor/device raise before any mmap `O:fusedump.py:237-252`; guarded.py PCI-id + PMC_BOOT_0 chip-id `O:guarded.py:66-70,36-37` |
| Plan derivation breadth (which fields) | **THEY-BETTER** | FBIO+FBPA+GPC+PES+FBP+ROP_L2+TPC×8 → defect masks `T:ffcard.py:33-40` | GPC+FBP+FBPA only `O:gui.py:2269-2307`; no TPC/PES/ROP_L2/FBIO FF proposal |
| Plan derivation safety (refusals) | EQUAL-ish | refuse holes/IFF/replay-mismatch/missing-mask `T:ffcard.py:69-98,156-162` | refuse via ff_policy zones + IFF-value + occupancy `O:service.py:966-1008`; no offline plan artifact |
| FF encoding of records | EQUAL | `(new<<16)\|(b<<6)\|c`, IFF=0 `T:ffcard.py:145-153` | `encFF` `O:gui.py:2239-2240`; server refuses bit5 values `O:service.py:992-998` |
| Row/zone strategy | **WE-BETTER** | first blank after last, contiguous, `--skip-rows` `T:ffcard.py:202-217` | burn zone + buffer + SM re-disable reserve + revert tail, hard-enforced server-side `O:service.py:130-132,868-903,966-1008` |
| Mirror even/odd pair rows | DIFFERENT-TRADEOFF | none; single row per record, shipped 3 cards `T:README.md:17-18,319-320` | optional mirror, even-aligned pair allocator `O:gui.py:2119,2384-2425`, `O:service.py:1004-1007`; necessity on FF rows UNVERIFIED either way |
| IFF handling | DIFFERENT-TRADEOFF | refuses any dump containing IFF rows `T:ffcard.py:95-97` | refuses IFF *writes*, reads/labels existing IFF `O:service.py:992-998`, `O:gui.py:1080-1092`; their tool would refuse our AI2 dump (canary row 303, `evidence/112-state-report-for-review.md:124`) |
| DEVID protection | **THEY-BETTER** (as policy) | chain2 blk37/38 FORBIDDEN + unchanged-check `T:ffcard.py:31,146,232-234` | client labels DEVID `O:gui.py:2251-2253`; no server-side refusal of DEVID rows in `ff_policy` |
| Safety gates before CMD_WRITE | **WE-BETTER** | IDLE/CRC/DSOV/SBFE/EFP/PLM/RWL/blank `T:ff_burn.py:91-111` | all of those (DEBUGCTRL==0 subsumes RWL) + LOADER_120060/SWIFF/IFF_CTRL/PRIV_MASK + driver-unbound + GPIO19 preflight + arm token + Goldilocks `O:service.py:626-647,764-790,1488-1491` |
| Arming (SENSE_CTRL/WDATA_PLM/SBFE) | EQUAL (we automate) | 3 human scripts `T:arm/*.py` | `arm_window` at burn time, SENSE ≤ once, re-check after SENSE `O:service.py:729-761` |
| Journaling / crash recovery | **WE-BETTER** | resume via `check` prefix scan `T:ffcard.py:274-291,304-306` | fsync'd `command_may_be_issued` before EN=1 + `journal_uncertain` gate + ALREADY-BURNED partial-campaign recovery `O:service.py:666-706,779-782,800-810` |
| Burn-time verification | **WE-BETTER** | single readback `T:ff_burn.py:180-187` | readback + 2-pass image verify + predicted-vs-actual collision re-scan `O:service.py:718-726,853-857,1334` |
| Post-cold-boot plan verification | **THEY-BETTER** | dedicated `ffcard.py verify`: fields/shadows/defect-masks/unchanged/stray-rows + fingerprint `T:ffcard.py:312-357` | no plan-level offline verifier; UI dump diff + `burn_after_state` only `O:service.py:1334` |
| Card-state fingerprint | **THEY-BETTER** (complementary) | SHA-256 of rows 222..last in every plan `T:ffcard.py:101-103` | board serial staleness `O:gui.py:631-638`; defect-word fingerprint `O:fusedump.py:453-456` (not row-content) |
| PCIe Gen3/Gen4 unlock | **THEY-BETTER** | 4 chain-2 records gated on stock values + `pcie_state.py` targets `T:ffcard.py:46-53`, `T:pcie_state.py:19-25` | no PCIe FF plan; LnkSta/LnkCap captured via lspci only `O:fusedump.py:330-334` |
| NVLink unlock | THEY-ONLY | `T:ffcard.py:41,196-199` | none |
| Post-unlock SM coverage stress | **THEY-BETTER** | `%smid` FFMA stress, per-launch coverage, bisect `T:bench/sm_stress.py:1-12,112-151` | nothing equivalent in repo |
| Post-unlock mem/bandwidth proof | THEY-ONLY | bench.cu + memtest_vulkan bar `T:README.md:270-303` | none |
| Driver quarantine for the window | **THEY-BETTER** (finding) | kernel `module_blacklist=` GRUB drop-in; "a modprobe.d blacklist is not enough: nvidia-modprobe and udev still load the module" `T:gpu-stack.sh:8-11,44-52`, `T:README.md:67-68` | modprobe.d blacklist file `O:service.py:171,2257-2273` |
| Glitching itself | **WE-BETTER** | out of scope, links us `T:README.md:363-369`, `T:SOURCES.md:42-43` | Pico v_dip campaign, in-process burn on first Goldilocks `O:service.py:30,78,1861` |
| UX: proposed-plan rows + queue | EQUAL | plan JSON + next-record pointer `T:ffcard.py:304-306` | PROPOSED panel + queue with exact rows via one allocator `O:gui.py:934-988,2384-2425` |
| Offline unit tests | **THEY-BETTER** | synthetic derive/check/verify suite `T:tests/test_tools.py` | no test suite (AGENTS.md: "no CI and no test suite") |
| Agent safety policy | EQUAL | "NEVER BURN" agent rules `T:AGENTS.md:3-23` | our AGENTS.md command table |

---

## 3. Correctness cross-check — disagreements and adjudication

**D1 — FF bits 83–106: FBIO or FBPA? (their map vs ours)**
They map 1:83–106 = `FBIO_DISABLE` and 1:107–130 = `FBPA_DISABLE` (`T:planner/ff_dump.py:65-66`) and burn both to their own DEFECTIVE masks (`T:planner/ffcard.py:33-34`). We place our "FBPA unlock" at chain1 off5/off6 with `<<3` — i.e. the same global bits 83–106 — sourced from `FBPA_DEFECTIVE 0x8205D0` (`O:gui.py:2294-2303`). Our own brute-force decode found off5/6 `>>3` == `0xC0330C` == the FBPA/FBIO/ROP_L2 shadow value and concluded "this single field feeds all three consumers" (`evidence/45-fbpa-decoded.md:1-27`). But later hardware reads show the FBPA shadow (0x820368/0x820C18 = `0x330C`) and FBIO shadow (0x82036C/0x820C14 = `0xC0330C`) **diverge by bits 22/23** (`evidence/108-tpc-array-and-mirrors.md:60-73`, `evidence/112-state-report-for-review.md:52-67`) — two diverging shadows cannot both come from one FF field. **Adjudication: their two-field map is consistent with our own divergence data; our "single field" claim in evidence 45 §1 is wrong (correct the record), and our label "FBPA" for bits 83–106 is probably FBIO.** Consequence: our plan never touches 107–130, so FBPA bits 22/23 (defective-but-not-disabled, `evidence/111-qwen-plan-local-tree-audit.md:130`) stay uncorrected by our proposal. Mitigating: on our card `FBPA_DEFECTIVE == FBIO_DEFECTIVE == 0xC03000` (`evidence/45-fbpa-decoded.md:31-38`), so the value we write into 83–106 is right under either naming.

**D2 — `ROP_L2_DEFECTIVE` address**
They read it at `0x8205E8` (`T:planner/read_defects.py:19`) and use `0x8205C8` for `TPC_GPC0_DEFECTIVE` (`T:planner/read_defects.py:26-27`). Our evidence 45 §2 labelled `0x8205C8` as `ROP_L2_DEFECTIVE` (`evidence/45-fbpa-decoded.md:33`). Our fleet-verified TPC defect table says `0x8205C8` = TPC GPC0 (`O:fusedump.py:104-109`, 13/13). **Adjudication: THEY RIGHT, our evidence-45 label was wrong** (their TPC set matches ours exactly, so both cannot hold). Their `0x8205E8` itself: UNVERIFIED on our fleet.

**D3 — TPC control register base**
They read `FUSE_CTRL_OPT_TPC_GPC{i} = 0x820838+4i` (`T:planner/read_defects.py:28`); we hardware-tested `TPC_CTRL_GPC0 = 0x820A40` (`evidence/108-tpc-array-and-mirrors.md:33-40`, `O:fusedump.py:113`). Likely two distinct registers (fuse-derived CTRL_OPT vs runtime CTRL). **Adjudication: UNVERIFIED — no conflict proven, do not merge the names.**

**D4 — EN_SW_OVERRIDE vs CMD_READ validity**
Our invariant: with EN_SW_OVERRIDE set, the shadow plane answers CMD_READ with "stable garbage instead of real rows" (`O:fusedump.py:16-18`), so we clear it around every row sweep and restore it (`O:fusedump.py:395-423`, `O:service.py:921-929`). Their `ff_dump.py` never reads or clears EN_SW_OVERRIDE (`T:planner/ff_dump.py:111-118,183-209`) and their `ff_burn.py` never checks it either (`T:burn/ff_burn.py:91-111`). On their workflow EN is 0 on stock cards, but a dump taken after any EN=1 experiment would be silently garbage and their fingerprint check would happily bless it. **Adjudication: WE RIGHT; genuine gap in their tool.**

**D5 — SENSE_CTRL = FUSECTRL cmd 3**
They mark cmd 3 as unconfirmed (`T:arm/arm_sense_ctrl.py:10-12`). We use `CMD_SENSE = 3` (`O:service.py:151`) and our executed burns prove the arm path works (EFP=1, VERIFY OK, `evidence/99-burns-executed.md:1-30`). **Adjudication: value confirmed by our hardware runs; their caution noted, ours is the stronger evidence.**

**D6 — FUSEWDATA: full value vs delta**
They write the full word (`T:burn/ff_burn.py:174`); we write `delta = value & ~cur` (`O:service.py:816`). On a blank row (both require blank: `T:burn/ff_burn.py:110`, `O:service.py:811-814`) cur=0 and the two are identical. **Adjudication: no disagreement in effect.**

**D7 — IFF rows in a dump**
They refuse any dump with an IFF row inside the used range (`T:planner/ffcard.py:95-97`); our AI2 card has a burned IFF canary at row 303 that truncated the FF pool (`evidence/112-state-report-for-review.md:124`, `IFF_RECORD start=303` at :40). Their planner cannot plan such a card at all; ours reads, labels and refuses only new IFF writes (`O:service.py:992-998`). **Adjudication: DIFFERENT-TRADEOFF — theirs is stricter but brittle on burned cards; ours matches observed hardware (IFF records are real and meaningful).**

**D8 — PCIe record values**
Their chain-2 blocks 39/46/47/49 stock→new values are "proven on four dies" and gated: any block off the expected stock value skips the whole PCIe plan (`T:planner/ffcard.py:44-49,187-195`). Our independent readback `MAGIC_D 0x820520 = 0x16680000` (`evidence/112-state-report-for-review.md:46`) is consistent with their target `0x00200000` being a change, but we have never decoded or burned these blocks. **Adjudication: UNVERIFIED on our fleet; their gating design (skip unless stock-expected) makes adoption low-risk.**

**D9 — GSP boot coupling**
They state burning SM(TPC) records without matching PES/ROP_L2 records fails GSP boot (`T:README.md:194-196`, `T:SOURCES.md:22-23`). We have no TPC FF burns, so this never bit us — but it is a load-bearing constraint for proposal P2 below. **Adjudication: accept as their hardware finding (credited xPatrik, `T:SOURCES.md:18-23`); UNVERIFIED by us.**

**D10 — `STATUS_OPT_TPC_GPC3/4 = 0x1` runtime masks**
They observed it on all three cards and warn it can cost 4 SMs (`T/README.md:358-359`, `T:planner/ffcard.py:343-347`). Our evidence 108 §3 shows the same array (GPC1/2/7 = 0xFF, others 0x01) and that it survives GPC invalidation (`evidence/108-tpc-array-and-mirrors.md:44-58`). **Adjudication: agreement; both sides right.**

---

## 4. Improvement proposals for us (ranked; no code changed)

| # | Proposal | Impact | Effort | Risk | Where |
|---|---|---|---|---|---|
| P1 | **Post-unlock SM coverage stress** — port the `%smid` PTX stress (`T:bench/sm_stress.py:27-87,112-151`) as `host/ga100vfi/smstress.py`; console post-unlock checklist runs `probe` (count vs `tpc_summary.sm_max`) and `run all`. Coverage checked per launch, bisect sets for failures. | High — only way to prove newly enabled SMs actually run work; we currently prove nothing post-unlock | Med (self-contained, no hardware writes) | Low (CUDA only) | new file; hook next to `O:service.py` dumps/`/api/live` |
| P2 | **Complete the FF plan: FBPA(107–130), FBIO-naming fix, ROP_L2, PES** — extend `suggestPlan` (`O:gui.py:2269-2307`) to derive every memory-plane field to its own DEFECTIVE mask per their map (D1), and label bits 83–106 FBIO. Burn TPC/PES/ROP_L2 only as an all-or-nothing group (their GSP-boot rule, D9). Validate field placement on a spare/already-lost card first. | High — closes the FBPA 22/23 collateral gap (`evidence/112:66`) and matches the only map consistent with our divergence data | Med-High | Med-High (new FF fields; wrong field = wasted rows; GSP-boot coupling) | `O:gui.py:2269-2307`, `O:service.py` preview/after-state |
| P3 | **Offline plan artifact + fingerprint verifier** — a `plan.json` (records+rows+targets+baseline row-fingerprint of rows 222..last, `T:planner/ffcard.py:101-103`) with `check`/`verify` subcommands run against our saved dumps; catches wrong-card/wrong-state burns by row content, not just serial. | High — our serial staleness (`O:gui.py:631-638`) doesn't detect same-card state drift; their `check`/`verify` is the missing post-cold-boot gate (delta table) | Med | Low (offline, read-only) | new `host/ga100vfi/planverify.py` reusing `O:service.py:868-903` + fusedump dumps |
| P4 | **PCIe Gen3/Gen4 plan + `pcie_state` gate** — adopt their 4 gated chain-2 records (`T:planner/ffcard.py:46-53`) as an optional queue group (skip unless blocks read the stock values), plus a read-only pcie_state check (targets + LnkCap 16GT/s) surfaced in the console after burns. | Med — link speed is real money on these cards; gate makes refusal automatic on unexpected stock values | Med | Med (chain-2 rows; UNVERIFIED on our fleet, D8) | queue groups in `O:gui.py:2335+`; new read-only checker beside `O:fusedump.py:330-334` |
| P5 | **Kernel `module_blacklist=` quarantine** — their finding that modprobe.d blacklists don't stop `nvidia-modprobe`/udev (`T:gpu-stack.sh:8-11`, `T:README.md:67-68`); our driver-off path writes only `/etc/modprobe.d/ga100-fuse-blacklist.conf` (`O:service.py:171,2257-2273`). Add a GRUB-drop-in mode (or at least warn when nvidia loads anyway). | Med — a driver respawning mid-window silently kills the burn window | Low-Med | Low (host config, reversible) | `O:service.py:2257-2273` |
| P6 | **Server-side DEVID refusal** — mirror their FORBIDDEN chain2 blk37/38 (`T:planner/ffcard.py:31,146`) in `ff_policy` when `value` is given (`O:service.py:966-1008`); today only the client labels DEVID (`O:gui.py:2251-2253`) and `evidence/109` shows DEVID burns were seriously considered. | Med — one irreversible mistake class, one-line-class fix | Low | Low | `O:service.py:992-998` |
| P7 | **Burned-prefix resume pointer** — `check`-style output "next: row N = 0x…" after an interrupted campaign (`T:planner/ffcard.py:304-306`); our journal knows the state but the queue UI doesn't point at the resume row. | Low-Med | Low | Low | `O:service.py:1468+` / queue render `O:gui.py:2340-2360` |
| P8 | **bench.cu-style post-unlock benchmark** (bandwidth/tensor/BAR1, `T:README.md:270-283`, GPL-2.0 upstream `T:SOURCES.md:34-37`) to prove the 5th HBM stack. | Low-Med | Med (C, licensing care) | Low | `bench/` new dir |

---

## 5. UNVERIFIED register (things this comparison could not ground)

- Their `OPT_ROP_L2_DEFECTIVE = 0x8205E8` (`T:planner/read_defects.py:19`) — never read on our fleet.
- Their `FUSE_CTRL_OPT_TPC 0x820838` vs our `TPC_CTRL 0x820A40` (D3) — possibly two registers; unresolved.
- Their PCIe block→shadow bit mapping (which of blocks 39/46/47/49 drives which `0x8202xx/520/57C/580` bit) — "proven on four dies" per `T:SOURCES.md:20-28`, not reproduced by us (D8).
- Whether mirror rows are required for FF-region appends (D-table row "Mirror"): their 3 shipped cards prove single-row works; our mirror pairs on AI2 (`evidence/99-burns-executed.md:14-25`) don't prove they were needed.
- The kate-land `ga100-options.json` URL in `T:SOURCES.md:11` returns 404 today (checked 2026-11-23 via raw.githubusercontent); the field map could not be re-checked against the upstream table.
- Their claim of three cards reaching full fuse-level config (`T:README.md:17-18`) — their own report, not verified here.

COMPARE_DONE (evidence file)
