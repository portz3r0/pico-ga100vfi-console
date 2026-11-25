#!/usr/bin/env python3
"""Task 44: chain-0 golden-recipe replay (evidence/44).

The task-44 brief claimed both signed recipes burned chain-0 mirror FF
records for the 16 compute-unlock blocks ("batch1 rows 308-324, batch2
rows 326-346"). Decoding the plans themselves REFUTES that: those rows
are the chain-1 records (final words 0x80070141 … — chain bits[4:0]=1).
The chain-0 appearance is a two-stage burn artifact: ga100_burn.py
issues one physical CMD_WRITE per STEP delta, and the plan generator
decomposes every FF row into (1) data+block with the chain bits zero —
a chain-0 INTERMEDIATE word — then (2) the chain bits. The final arrays
of both tested cards contain NO chain-0 FF records in 222-487 (plan
POST images, GPU1 post-burn dump, both pre-burn dumps — evidence/44).

This test locks the corrected ground truth in:
  * neither recipe's BASE nor POST image holds a chain-0 record 222-487;
  * every stepped FF row follows the two-stage pattern (chain-0
    intermediate, then chain bits 1 or 2);
  * the console-side §3 derivation (evidence/40 §3, catalog from
    service.ff_fields_for) on each card's own planes reproduces every
    burned chain-1 word, and the PROPOSE set (target != BASE last-wins)
    == the recipe's stepped blocks exactly — for chain 1;
  * the chain-0 replay the brief asked for: recipe chain-0 burned set
    == {} and the console's chain-0 proposal set == {} (the
    compute-unlock item carries no chain-0 steps — correct, and this
    test refuses any future addition);
  * golden completeness: the compute-unlock item's chain-1 FF steps are
    exactly the 16 blocks common to both recipes (blk17 note-only),
    with the batch2 tested values and batch1 per-die other_burns.

Plane provenance: GPU1's planes are REAL from its dump shadow (the
test asserts the words round-trip to those shadow values — non-circular
anchor); the four planes absent from the Nov-24 dump (PES/ROP_L2/
SYS_PIPE/FBIO) are implied from the burned words, as evidence/43 did.
GPU2 has no dump: its planes are decoded from its own burned words
through the catalog (documented circularity bound, evidence/43).

Run: PYTHONPATH=host python3 host/tests/test_chain0_golden.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.advanced_unlocks import ADVANCED_UNLOCKS, enc_ff  # noqa: E402
from ga100vfi.console.service import ff_fields_for              # noqa: E402

PLAN_A = "/home/raza/nvidia/GPU1/razk-batch1.bin"
PLAN_B = "/home/raza/nvidia/GPU2/razk-batch2.bin"
DUMP_A = ("/home/raza/ga100-fuse-view/dumps/sn-1322321006870/"
          "20261124-112031/dump.json")

HEADER = struct.Struct("<8sII")
FRAME = struct.Struct("<4sI32s")
STEP = struct.Struct("<IIII")

# compute-unlock blocks the console derives (gui.py suggestPlan pd loop)
BLOCKS = [5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 19, 20, 23, 26, 27]
# the 16 blocks BOTH recipes stepped (blk17 only batch1 → note-only)
COMMON16 = [b for b in BLOCKS if b != 17]

ARTIFACTS = (PLAN_A, PLAN_B, DUMP_A)


def _frames(s):
    while True:
        h = s.read(FRAME.size)
        if not h:
            return
        tag, size, digest = FRAME.unpack(h)
        payload = s.read(size)
        assert len(payload) == size, "truncated frame"
        assert hashlib.sha256(payload).digest() == digest, f"digest {tag}"
        yield tag, payload


def decode_plan(path):
    """GA100PLN → (base, post, steps) of the single card. Format and
    invariants verified by digests + before/delta/after assertions,
    same decoder pattern as task 42/43 (t42plans.py)."""
    data = open(path, "rb").read()
    magic, version, size = HEADER.unpack_from(data)
    assert magic == b"GA100PLN", magic
    body = io.BytesIO(data[HEADER.size:HEADER.size + size])
    cards = []
    next(_frames(body))                       # META
    for tag, payload in _frames(body):
        assert tag == b"CARD"
        secs = dict(_frames(io.BytesIO(payload)))
        rows = list(struct.unpack(f"<{len(secs[b'BASE']) // 4}I", secs[b"BASE"]))
        steps = list(STEP.iter_unpack(secs[b"STEP"]))
        post = rows.copy()
        for row, before, delta, after in steps:
            assert post[row] == before, (row, hex(post[row]), hex(before))
            assert (before | delta) == after and not before & delta, row
            post[row] = after
        cards.append((rows, post, steps))
    assert len(cards) == 1, len(cards)
    return cards[0]


def ff_records(rows, lo=222, hi=487):
    """(row, chain, block, data) for live FF words in [lo, hi]."""
    out = []
    for r in range(lo, hi + 1):
        v = rows[r]
        if v in (0, 0xFFFFFFFF) or (v >> 5) & 1:
            continue
        out.append((r, v & 0x1F, (v >> 6) & 0x3FF, (v >> 16) & 0xFFFF))
    return out


def lastwins(rows, chain):
    """last-wins data word per block for one chain over 222-487."""
    cur = {}
    for _, ch, blk, data in ff_records(rows):
        if ch == chain:
            cur[blk] = data          # rows ascend → last wins
    return cur


def defect_key(name):
    if name.startswith("TPC_GPC"):
        return "TPC_DEFECTIVE_" + name.split("_")[1]
    return name.replace("_DISABLE", "_DEFECTIVE")


def planes_from_words(burned):
    """Decode defect planes from last-wins chain-1 words (inverse of the
    §3 placement): plane bits at fbit0 come from the field's window bits."""
    planes = {}
    for blk, word in burned.items():
        for f in ff_fields_for(1, blk):
            key = defect_key(f["name"])
            bits = (word >> f["dlo"]) & ((1 << f["n"]) - 1)
            planes[key] = planes.get(key, 0) | (bits << f["fbit0"])
    return planes


def derive(shadow, base_rows):
    """evidence/40 §3 forward derivation (fresh implementation, catalog
    imported from service): per-block target word + carried field names."""
    cur = lastwins(base_rows, 1)
    pd, carried = {}, {}
    for blk in BLOCKS:
        word, carry = 0, []
        for f in ff_fields_for(1, blk):
            v = shadow.get(defect_key(f["name"]))
            if v is not None:
                word |= ((v >> f["fbit0"]) & ((1 << f["n"]) - 1)) << f["dlo"]
            else:
                word |= ((cur.get(blk, 0) >> f["dlo"]) & ((1 << f["n"]) - 1)) << f["dlo"]
                carry.append(f["name"])
        if blk == 5:
            word |= cur.get(5, 0) & 0x0007
        pd[blk] = word
        if carry:
            carried[blk] = carry
    return pd, carried, cur


def _artifact_guard(fn):
    def run():
        missing = [p for p in ARTIFACTS if not os.path.exists(p)]
        if missing:
            print(f"SKIP {fn.__name__} (missing artifacts: "
                  f"{', '.join(missing)})")
            return
        fn()
    run.__name__ = fn.__name__
    return run


@_artifact_guard
def test_no_chain0_records_in_either_recipe():
    """Corrected ground truth: no chain-0 FF record in BASE or POST of
    either recipe (222-487) — the brief's 'chain-0 mirrors' do not
    exist as final words."""
    for path in (PLAN_A, PLAN_B):
        base, post, steps = decode_plan(path)
        for img, label in ((base, "BASE"), (post, "POST")):
            c0 = [(r, hex(img[r])) for r, ch, blk, d in ff_records(img)
                  if ch == 0]
            assert not c0, (path, label, c0)
        assert lastwins(base, 0) == {}, path      # card's chain-0 current: empty


@_artifact_guard
def test_two_stage_burn_pattern():
    """Every stepped FF row 222-487 is burned as chain-0 intermediate
    first, then the chain bits — the artifact the brief read as
    'chain-0 mirror records'. Single row per block, ascending, no
    mirror pairing."""
    for path in (PLAN_A, PLAN_B):
        base, post, steps = decode_plan(path)
        by_row = {}
        for row, before, delta, after in steps:
            if 222 <= row <= 487:
                by_row.setdefault(row, []).append((before, delta, after))
        assert by_row, path
        blocks_seen = []
        for row, entries in sorted(by_row.items()):
            final = entries[-1][2]
            if row in (484, 485, 486, 487):
                # IFF WRITE_DW macro pair (SS0 rows 484/485, SS1 486/487 —
                # the compute-unlock item's _iff steps): burned as single
                # words, not FF records — no two-stage decomposition.
                assert len(entries) == 1, (path, row, entries)
                continue
            assert len(entries) == 2, (path, row, entries)
            (b1, d1, a1), (b2, d2, a2) = entries
            assert b1 == 0 and b2 == a1, (path, row)
            final = a2
            chain, blk, data = final & 0x1F, (final >> 6) & 0x3FF, final >> 16
            assert chain in (1, 2), (path, row, hex(final))
            # stage 1: the chain-0 intermediate — same block, same data
            assert d1 == (final & ~0x1F), (path, row, hex(d1), hex(final))
            assert d1 & 0x1F == 0 and not (d1 >> 5) & 1, (path, row, hex(d1))
            assert (d1 >> 6) & 0x3FF == blk and d1 >> 16 == data, (path, row)
            # stage 2: the chain bits only
            assert d2 == chain, (path, row, hex(d2), chain)
            blocks_seen.append((chain, blk))
        # one row per (chain, block), rows ascend with block within chain
        assert len(set(blocks_seen)) == len(blocks_seen), path
        for chain in (1, 2):
            blks = [b for c, b in blocks_seen if c == chain]
            assert blks == sorted(blks), (path, chain, blks)


@_artifact_guard
def test_chain1_derivation_reproduces_both_recipes():
    """The golden chain-1 replay (evidence/43 method): console-side §3
    derivation on each card's own planes == every burned word, and the
    PROPOSE set (target != BASE last-wins) == the recipe's stepped
    chain-1 blocks exactly."""
    dump = json.load(open(DUMP_A))
    for path, anchor in ((PLAN_A, True), (PLAN_B, False)):
        base, post, steps = decode_plan(path)
        burned = lastwins(post, 1)
        planes = planes_from_words(burned)
        if anchor:
            # non-circular check: the planes the dump DOES hold must
            # match the words' implied values (GPU1 real shadow)
            for key, val in dump["shadow"].items():
                if key in planes and val is not None:
                    assert planes[key] == val, (key, hex(planes[key]), hex(val))
        pd, carried, cur = derive(planes, base)
        assert not carried, (path, carried)
        stepped = sorted({(post[r] >> 6) & 0x3FF
                          for r, ch, blk, d in ff_records(post)
                          if ch == 1 and any(sr == r for sr, *_ in steps)})
        bad = {b: (hex(pd[b]), hex(burned.get(b, -1))) for b in stepped
               if pd[b] != burned.get(b)}
        assert not bad, (path, bad)
        proposed = sorted(b for b in BLOCKS if pd[b] != cur.get(b, 0))
        assert proposed == stepped, (path, proposed, stepped)
        if path == PLAN_A:
            assert 17 in stepped, stepped          # batch1 stepped blk17
        else:
            assert 17 not in stepped, stepped      # batch2 did not


@_artifact_guard
def test_chain0_replay_sets_are_empty():
    """The brief's gate (a) for chain 0, evaluated honestly: recipe
    chain-0 burned words == {} and the console's chain-0 PROPOSE set
    (target != card's chain-0 current from BASE) == the recipe's
    chain-0 stepped blocks == {}."""
    for path in (PLAN_A, PLAN_B):
        base, post, steps = decode_plan(path)
        stepped_rows = {r for r, *_ in steps}
        c0_stepped = [(r, blk) for r, ch, blk, d in ff_records(post)
                      if ch == 0 and r in stepped_rows]
        assert c0_stepped == [], (path, c0_stepped)
        assert lastwins(post, 0) == {}, path       # recipe chain-0 burned: {}
        # console side: the compute-unlock item proposes no chain-0 word
        item = next(i for i in ADVANCED_UNLOCKS if i["id"] == "compute-unlock")
        c0_steps = [s for s in item["steps"]
                    if s["kind"] == "ff" and (s["value"] & 0x1F) == 0]
        assert c0_steps == [], (path, c0_steps)


@_artifact_guard
def test_golden_recipe_completeness():
    """The golden recipe (operator ruling 2026-11-25: what BOTH tested
    cards have in common) is already complete in advanced_unlocks.py:
    exactly the 16 common chain-1 blocks, batch2 tested values, batch1
    per-die other_burns, blk17 note-only, no chain-0 steps."""
    base_a, post_a, _ = decode_plan(PLAN_A)
    base_b, post_b, _ = decode_plan(PLAN_B)
    burned_a, burned_b = lastwins(post_a, 1), lastwins(post_b, 1)
    stepped_a = set(lastwins(post_a, 1)) & set(BLOCKS)
    stepped_b = set(lastwins(post_b, 1)) & set(BLOCKS)
    # stepped sets from the plans themselves (rows written):
    item = next(i for i in ADVANCED_UNLOCKS if i["id"] == "compute-unlock")
    ff_steps = [s for s in item["steps"] if s["kind"] == "ff"]
    assert all((s["value"] & 0x1F) == 1 for s in ff_steps), \
        "compute-unlock must carry chain-1 FF steps only (evidence/44)"
    assert sorted(s["block"] for s in ff_steps) == COMMON16
    assert 17 not in {s["block"] for s in ff_steps}   # note-only, per docstring
    for s in ff_steps:
        b = s["block"]
        assert s["data"] == burned_b[b], (b, hex(s["data"]), hex(burned_b[b]))
        if burned_a.get(b) != burned_b[b]:
            assert s.get("other_burn") == burned_a.get(b), \
                (b, hex(s["data"]), hex(burned_a.get(b, -1)))
        else:
            assert "other_burn" not in s, b
    # batch1 stepped blk17, batch2 did not (the brief's blk17 asymmetry)
    assert 17 in stepped_a and 17 not in stepped_b


if __name__ == "__main__":
    for name in sorted(k for k in list(globals())
                       if k.startswith("test_") and callable(globals()[k])):
        globals()[name]()
    print("all chain0-golden tests passed")
