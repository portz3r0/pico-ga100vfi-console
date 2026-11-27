#!/usr/bin/env python3
"""Task 30: assert every ADVANCED_UNLOCKS record matches the executed plans
byte-for-byte: each ff step's value == the final burned word at its
GPU2 bench row in razk-batch2.bin (and the GPU1 word, incl. gpu1_data
differences, at its GPU1 row in razk-batch1.bin); iff/direct steps match
their rows/deltas in BOTH plans."""
import io
import struct
import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path.home() / "nvidia/GPU2"))
# run from a checkout that contains advanced_unlocks.py (main >= task 30)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
import ga100_dump as dump  # noqa: E402
from ga100vfi.advanced_unlocks import ADVANCED_UNLOCKS  # noqa: E402

HEADER = struct.Struct("<8sII")
STEP = struct.Struct("<IIII")


def plan_steps(path):
    """row -> final word after all steps; plus row -> set of deltas."""
    data = Path(path).read_bytes()
    magic, version, size = HEADER.unpack_from(data)
    assert magic == b"GA100PLN"
    stream = io.BytesIO(data[HEADER.size:HEADER.size + size])
    tag, payload = dump.read_frame(stream)
    assert tag == b"META"
    meta = dump.decode_sections(payload)
    ts = meta[b"TIME"].decode()
    tag, payload = dump.read_frame(stream)
    assert tag == b"CARD"
    sec = dump.decode_sections(payload)
    final, deltas = {}, {}
    for row, before, delta, after in STEP.iter_unpack(sec[b"STEP"]):
        final[row] = after
        deltas.setdefault(row, set()).add(delta)
    return sha256(data).hexdigest(), ts, final, deltas


g1 = plan_steps(Path.home() / "nvidia/GPU1/razk-batch1.bin")
g2 = plan_steps(Path.home() / "nvidia/GPU2/razk-batch2.bin")
print(f"GPU1 sha={g1[0][:16]}.. meta={g1[1]}")
print(f"GPU2 sha={g2[0][:16]}.. meta={g2[1]}")
assert g1[0] == "4a6ebbc60d59ee0e1a95e53af34e7e5af215b6db31bc02775e215dfaef878802"
assert g2[0] == "fcbde382d8fc812e92aeeff42fdcbc222091603e74ecc93f7f40600bf3113f8f"
assert g1[1].startswith("2026-11-18T03:00:24") and g2[1].startswith("2026-11-18T14:58:29")

n_ff = n_dir = n_iff = 0
for item in ADVANCED_UNLOCKS:
    for s in item["steps"]:
        if s["kind"] == "ff":
            n_ff += 1
            r2, r1 = s["bench_rows"]["GPU2"], s["bench_rows"]["GPU1"]
            assert g2[2][r2] == s["value"], (item["id"], s["field"], r2,
                                             hex(g2[2][r2]), hex(s["value"]))
            want1 = s.get("gpu1_data", s["data"])
            got1 = g1[2][r1] >> 16
            assert g1[2][r1] == (s["value"] & 0xFFFF) | (want1 << 16), \
                (item["id"], s["field"], r1, hex(got1), hex(want1))
        elif s["kind"] == "direct":
            n_dir += 1
            for g in (g1, g2):
                for r in s["rows"]:
                    assert s["delta"] in g[3][r], (item["id"], r, hex(s["delta"]))
        elif s["kind"] == "iff":
            n_iff += 1
            for g in (g1, g2):
                for r, w in zip(s["rows"], s["words"]):
                    assert g[2][r] == w, (item["id"], r, hex(g[2][r]), hex(w))
print(f"MATCH: {n_ff} ff steps (GPU2 value at GPU2 row, GPU1 value/gpu1_data "
      f"at GPU1 row), {n_dir} direct deltas in BOTH plans, {n_iff} iff words "
      f"in BOTH plans — all byte-for-byte")

# per-die differences the docstring claims
diff = [(s["block"], hex(g1[2][s["bench_rows"]["GPU1"]] >> 16),
         hex(s["data"])) for it in ADVANCED_UNLOCKS for s in it["steps"]
        if s["kind"] == "ff" and s["chain"] == 1
        and g1[2][s["bench_rows"]["GPU1"]] >> 16 != s["data"]]
print("chain-1 per-die diffs (block, GPU1, GPU2):", diff)
assert [b for b, _, _ in diff] == [8, 12, 15, 16, 23]
# GPU1-only extra: chain1 block17 row 319
assert g1[2][319] == 0x00000441 and 319 not in {
    s["bench_rows"]["GPU2"] for it in ADVANCED_UNLOCKS for s in it["steps"]
    if s["kind"] == "ff"}
# DEVID delta: chain2 blk37/38 burned in both, not an item step
for g, rows in ((g1, (325, 326)), (g2, (342, 343))):
    for r in rows:
        assert g[2][r] == 0x416A0942 or g[2][r] == 0x416A0982, (r, hex(g[2][r]))
print("DEVID rows 0x416A (DEVID 0x20B5) present in both plans, excluded "
      "from items — documented delta")
print("ALL_ASSERTS_OK")
