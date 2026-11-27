#!/usr/bin/env python3
"""TASK 69 — A100 rebrand quick-add: /api/rebrand/plan.

Contract under test (service.rebrand_plan / rebrand_words):
  a. word arithmetic is ground truth per SKU (evidence/44 for 80GB, the
     80GB data word from evidence/44) — exact hex asserted, chain 2,
     offsets 37/38, bit 5 (IFF) clear;
  b. mock-mode plan returns exactly 2 records, DEVIDA first, rows strictly
     increasing, every placement passing ff_policy against the same mock
     layout, rows blank in the mock dump;
  c. rows come from the layout, never hardcoded: a block-37/38 record late
     in the region pushes the placement after it (per-block last-wins);
  d. fewer than 2 legal rows -> error, no partial plan;
  e. unknown sku -> error naming the valid ones;
  f. the endpoint is wired in do_GET, and the client-side pieces (SKU
     dropdown markers, duplicate-add refusal) exist in gui.py.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

GUI_SRC = os.path.join(os.path.dirname(__file__), "..",
                       "ga100vfi", "console", "gui.py")
SERVICE_SRC = os.path.join(os.path.dirname(__file__), "..",
                           "ga100vfi", "console", "service.py")


def mk_rows(occupied):
    """Full 0..487 blank rows map with `occupied` ({row: word}) overlaid —
    the shape real dumps have (every row key present, blanks included)."""
    rows = {str(r): 0 for r in range(0, 488)}
    for r, v in occupied.items():
        rows[str(r)] = v
    return rows


# existing DEVID pair burned late on the card (block 37/38, data 0x4184)
LATE_DEVIDA = (0x4184 << 16) | (37 << 6) | 2      # 0x41840942
LATE_DEVIDB = (0x4184 << 16) | (38 << 6) | 2      # 0x41840982


class WordsTest(unittest.TestCase):
    def test_80gb_exact_hex(self):
        w = dict(S.rebrand_words("80"))
        self.assertEqual(w["DEVIDA"], 0x416A0942)
        self.assertEqual(w["DEVIDB"], 0x416A0982)

    def test_field_layout_both_skus(self):
        for sku in ("80",):
            words = S.rebrand_words(sku)
            self.assertEqual([n for n, _ in words], ["DEVIDA", "DEVIDB"])
            for name, w in words:
                self.assertEqual(w & 0x1F, 2, "chain must be 2")
                self.assertEqual((w >> 5) & 1, 0, "bit 5 = IFF must be clear")
                off = 37 if name == "DEVIDA" else 38
                self.assertEqual((w >> 6) & 0x3FF, off)


class PlanMockTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="t69-")
        self._mock = os.path.join(self._tmp, "mock.json")
        self._save = (S.CFG["mock"],)
        self._set_rows({})

    def tearDown(self):
        (S.CFG["mock"],) = self._save

    def _set_rows(self, occupied):
        with open(self._mock, "w") as f:
            json.dump({"rows": mk_rows(occupied)}, f)
        S.CFG["mock"] = self._mock

    def _assert_legal(self, plan):
        L = S.ff_layout()
        self.assertNotIn("error", L)
        occ = set(L["occupied_rows"])
        prev = S.FF_START - 1
        for rec in plan["records"]:
            self.assertEqual(S.ff_policy(L, rec["row"], False, rec["value"]),
                             [], f"row {rec['row']} fails ff_policy")
            self.assertNotIn(rec["row"], occ, "row must be blank in the dump")
            self.assertGreater(rec["row"], prev, "rows strictly increasing")
            self.assertEqual(rec["old"], 0)
            prev = rec["row"]

    def test_blank_card_two_records_passing_policy(self):
        plan = S.rebrand_plan("80")
        self.assertNotIn("error", plan)
        self.assertEqual(len(plan["records"]), 2)
        self.assertEqual([r["value"] for r in plan["records"]],
                         [0x416A0942, 0x416A0982])
        self.assertEqual(plan["records"][0]["label"], "DEVIDA → 0x20B5")
        self.assertEqual(plan["records"][1]["label"], "DEVIDB → 0x20B5")
        self._assert_legal(plan)

    def test_deterministic(self):
        a = S.rebrand_plan("80")
        b = S.rebrand_plan("80")
        self.assertEqual(a, b)

    def test_rows_follow_block_last_wins_not_hardcoded(self):
        # late DEVID records at 300/301 must push the plan strictly after
        # each block's own last record — never a fixed 313/314-style answer.
        self._set_rows({300: LATE_DEVIDA, 301: LATE_DEVIDB})
        plan = S.rebrand_plan("80")
        self.assertNotIn("error", plan)
        self._assert_legal(plan)
        self.assertGreater(plan["records"][0]["row"], 300)
        self.assertGreater(plan["records"][1]["row"], 301)

    def test_fewer_than_two_legal_rows_errors(self):
        self._set_rows({r: 0x00070142 for r in range(S.FF_START, S.FF_END + 1)})
        out = S.rebrand_plan("80")
        self.assertIn("error", out)
        self.assertNotIn("records", out)

    def test_unknown_sku_errors(self):
        out = S.rebrand_plan("90")
        self.assertIn("error", out)
        self.assertIn("unknown sku", out["error"])


class WiringTest(unittest.TestCase):
    def test_endpoint_routed_in_do_get(self):
        with open(SERVICE_SRC) as f:
            src = f.read()
        self.assertIn('elif path == "/api/rebrand/plan":', src)
        self.assertIn("rebrand_plan(qs.get(\"sku\")", src)

    def test_gui_sku_dropdown_and_dup_refusal_markers(self):
        with open(GUI_SRC) as f:
            src = f.read()
        # SKU dropdown is the normal path, 80GB default, custom fallback
        self.assertIn("A100 80GB PCIe (0x20B5)", src)
        self.assertNotIn("A100 40GB PCIe", src)  # owner: unproven data word, removed
        self.assertIn('id="plan-rebrand-sku"', src)
        self.assertIn('<option value="80" selected>', src)
        self.assertIn('id="plan-devid-wrap" style="display:none"', src)
        # button fetches the server plan for the selected SKU
        self.assertIn("/api/rebrand/plan?sku=", src)
        # duplicate-add refusal is client-side
        self.assertIn("TASK69-DUP", src)
        self.assertIn("already in queue", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
