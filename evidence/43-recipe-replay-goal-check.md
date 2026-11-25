# TASK43 — Goal check: does the console propose the right fuses vs GPU1/ + GPU2/?

Question (user): based on what we know from `/home/raza/nvidia/GPU1/` and
`/home/raza/nvidia/GPU2/`, is the Fuse Console proposing the correct fuses?

Method: replay both signed recipes against the console's derivation
(`t42derive.py`, the task-42 independent §3 implementation) using each
card's OWN defect planes + the plan's own pre-burn `BASE` image, then
compare (a) derived words vs the words actually burned, (b) the console's
PROPOSE set (`derived != current`, the ALREADY-PRESENT skip logic) vs the
blocks the November toolchain actually queued.

## Results

**GPU1 (card A, sn-1322321006870, razk-batch1.bin, 54 steps)**
- Planes: GPC=0x2, TPC_GPC0=0x80, FBP=0x840, FBPA=0xC03000, NVLINK=0x1
  (REAL — from A's fusedump JSON shadow; DEFECTIVE registers never change)
  + PES=0x38, ROP_L2=0x3000, SYS_PIPE=0x80, FBIO=0xC03000 (implied by the
  burned words — not captured in Nov-18 dumps).
- derivation == every burned word: **YES** (16 stepped blocks; blk17 note).
- PROPOSED == QUEUED: **True** — [5,6,7,8,9,11,12,13,14,15,16,17,19,20,23,26,27].

**GPU2 (sn unknown, razk-batch2.bin, 52 steps)**
- No shadow JSON exists for GPU2 (the `.bin` REGA window is BAR0
  0x0–0xC040 — word[1]=PMC_BOOT_0 — and does NOT cover the 0x820000
  shadow region), so planes were decoded from GPU2's own burned words
  through the catalog: GPC=0, TPC_GPC0=0x40, TPC_GPC1=0x04, FBP=0x840,
  FBPA=0xC03000, ROP_L2=0x3000, FBIO=0xC03000, PES=0, SYS_PIPE=0, NVLINK=0.
- derivation == every burned word: **YES**.
- PROPOSED == QUEUED: **True** — 16 blocks, identical sets.
- Circularity bound: word-equality is self-consistent for encoded fields
  (planes came from the words); the NON-circular content is (i) the
  catalog mapping round-trips bit-exactly in both directions, (ii) the
  PROPOSE/ALREADY-PRESENT diff logic reproduces the toolchain's real
  queue decisions against the real pre-burn BASE state, (iii) GPU2's
  decoded planes are internally consistent with GPU1's real planes
  (identical FBIO/FBPA/FBP/ROP_L2 — same SKU binning — while GPC/TPC/PES/
  SYS_PIPE/NVLINK differ per die).

**Per-die split confirmed**: the two cards' burned words differ exactly at
blocks 8 (0x16/0x06), 12 (0x7F8/0x22), 15 (0xC080/0x0), 16 (0x1/0x0),
23 (0x800/0x0) — precisely the blocks the console badges
`per-die variant`; shared-plane blocks 5/6/7/19/20 are word-identical.

## Verdict

**YES — the console's derivation reproduces both known-correct recipes
word-for-word and queue-for-queue.** Remaining honesty caveats:
1. GPU2's planes are inferred, not measured — a fresh full dump of GPU2
   with the new capture (task 41) would make the GPU2 check fully direct.
2. For the INSTALLED card (sn-1322321009654) the four new planes are
   still unknown (old dump) — those fields carry + label until a fresh
   full dump; the GPC/TPC/FBP/FBPA/NVLINK-derived words are already from
   its own silicon.

Repro: script pattern = task-42 `t42derive.py` + plan decoder above;
run outputs recorded in this file's tables.

TASK43_DONE
