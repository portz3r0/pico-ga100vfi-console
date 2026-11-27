#!/usr/bin/env python3
"""Task 30 decode re-verification: parse razk-batch1/2.bin (GA100PLN signed
plans, skip signature check) and print every step, decoded as FF records,
plus META. Independent of the console module."""
import io
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "nvidia/GPU2"))
import ga100_dump as dump  # noqa: E402

HEADER = struct.Struct("<8sII")
STEP = struct.Struct("<IIII")
COND = struct.Struct("<III")


def ff(word):
    return f"chain={word & 0x1F} iff={(word >> 5) & 1} block={(word >> 6) & 0x3FF} data=0x{word >> 16:04X}"


def main(path):
    data = Path(path).read_bytes()
    magic, version, size = HEADER.unpack_from(data)
    assert magic == b"GA100PLN", magic
    stream = io.BytesIO(data[HEADER.size:HEADER.size + size])
    tag, payload = dump.read_frame(stream)
    assert tag == b"META"
    meta = dump.decode_sections(payload)
    uuid = meta[b"UUID"].hex()
    time = meta[b"TIME"].decode()
    print(f"== {path}")
    print(f"   plan version={version} sha256={__import__('hashlib').sha256(data).hexdigest()}")
    print(f"   META uuid={uuid} time={time}")
    n = 0
    while (entry := dump.read_frame(stream)) is not None:
        tag, payload = entry
        assert tag == b"CARD", tag
        n += 1
        sec = dump.decode_sections(payload)
        rows = dump.unpack_words(sec[b"BASE"])
        steps = list(STEP.iter_unpack(sec[b"STEP"]))
        conds = list(COND.iter_unpack(sec[b"COND"]))
        idv = sec.get(b"IDV2") or sec.get(b"IDV1")
        print(f"   CARD target #{n}: identity={idv.hex()[:16]}.. base_rows_nonblank="
              f"{sum(1 for r in rows if r not in (0, 0xFFFFFFFF))} steps={len(steps)} conds={len(conds)}")
        print("     conditions:")
        for addr, val, mask in conds:
            print(f"       reg 0x{addr:08x} expect 0x{val:08x} mask 0x{mask:08x}")
        print("     steps:")
        for row, before, delta, after in steps:
            kind = "FF " if row >= 222 else "DIR"
            extra = f"  [{ff(after)}]" if row >= 222 else ""
            print(f"       {kind} row {row:3d}: 0x{before:08X} | 0x{delta:08X} -> 0x{after:08X}{extra}")
    print()


for p in sys.argv[1:]:
    main(p)
