#!/usr/bin/env python3
"""Offline tests for classify(): a fake BAR0 that logs every access.
Ported from darkmaniac7/cmp170hx-8gb-vfi-tools host/test_classify.py
(patches 0002+0005), extended with the poisoned property and the
poisoned-outcome mapping in adaptive.classify_outcome."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.classify import (CRC_STATUS, DSOV, DSOV_SET, FPF_ROW, FUSECTRL,
                               PRIV_MASK, SHADOW, UNREADABLE, classify)
from ga100vfi.adaptive import classify_outcome

HEALTHY = {FUSECTRL: 0xE0040000, DSOV: 1, FPF_ROW: 0x00000000, DSOV_SET: 0,
           PRIV_MASK: 0xFFFFFFFF, CRC_STATUS: 0x55}


class FakeBar:
    def __init__(self, **over):
        self.regs = dict(HEALTHY)
        self.regs.update({globals()[k]: v for k, v in over.items()})
        self.log = []

    def rd32(self, off):
        self.log.append(("rd", off))
        return self.regs.get(off, 0)

    def wr32(self, off, value):
        self.log.append(("wr", off, value))
        self.regs[off] = value

    def writes(self):
        return [x for x in self.log if x[0] == "wr"]

    def reads(self):
        return [x[1] for x in self.log if x[0] == "rd"]


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.pop("CLASSIFY_WRITE", None)

    def tearDown(self):
        os.environ.pop("CLASSIFY_WRITE", None)
        if self._env is not None:
            os.environ["CLASSIFY_WRITE"] = self._env

    def test_default_writes_nothing(self):
        bar = FakeBar()
        v = classify(bar)
        self.assertEqual(bar.writes(), [])
        self.assertEqual(bar.reads()[:7], [FUSECTRL, DSOV, FPF_ROW, DSOV_SET,
                                           PRIV_MASK, CRC_STATUS,
                                           list(SHADOW.values())[0]])
        self.assertFalse(v.dsov_written)
        self.assertNotIn("dsov_settable", v.checks)
        self.assertEqual(v.dsov, 1)
        self.assertFalse(v.passed)

    def test_goldilocks_without_the_write(self):
        bar = FakeBar(DSOV=0)
        v = classify(bar)
        self.assertEqual(bar.writes(), [])
        self.assertEqual(v.dsov_writeback, 0)   # EN_SW_OVERRIDE read, not set
        self.assertTrue(v.passed, v.checks)

    def test_write_opt_in_by_environment(self):
        os.environ["CLASSIFY_WRITE"] = "1"
        bar = FakeBar(DSOV=0)
        v = classify(bar)
        self.assertEqual(bar.writes(), [("wr", DSOV_SET, 1)])
        self.assertTrue(v.dsov_written)
        self.assertTrue(v.checks["dsov_settable"])
        self.assertTrue(v.passed)
        os.environ["CLASSIFY_WRITE"] = "0"
        bar = FakeBar()
        classify(bar)
        self.assertEqual(bar.writes(), [])

    def test_write_argument_overrides_environment(self):
        os.environ["CLASSIFY_WRITE"] = "1"
        bar = FakeBar()
        classify(bar, write=False)
        self.assertEqual(bar.writes(), [])
        os.environ.pop("CLASSIFY_WRITE")
        bar = FakeBar()
        v = classify(bar, write=True)
        self.assertEqual(bar.writes(), [("wr", DSOV_SET, 1)])
        self.assertEqual(v.dsov_writeback, 1)

    def test_write_that_does_not_stick_fails_check(self):
        class Stuck(FakeBar):
            def wr32(self, off, value):
                self.log.append(("wr", off, value))
        bar = Stuck(DSOV=0)
        v = classify(bar, write=True)
        self.assertFalse(v.checks["dsov_settable"])
        self.assertFalse(v.passed)

    def test_poisoned_fusectrl_reads_nothing_else(self):
        os.environ["CLASSIFY_WRITE"] = "1"
        bar = FakeBar(FUSECTRL=0xBADF5040)
        v = classify(bar)
        self.assertEqual(bar.log, [("rd", FUSECTRL)])
        self.assertEqual((v.dsov, v.priv_mask, v.crc_status, v.fpf_row),
                         (0, 0, 0, UNREADABLE))
        self.assertEqual(v.shadow, {"FUSECTRL_POISONED": 0xBADF5040})
        self.assertFalse(v.passed)
        self.assertTrue(v.poisoned)
        self.assertFalse(v.dsov_written)

    def test_poisoned_dsov_stops_before_any_write(self):
        os.environ["CLASSIFY_WRITE"] = "1"
        bar = FakeBar(DSOV=0xBADF1701)
        v = classify(bar)
        self.assertEqual(bar.log, [("rd", FUSECTRL), ("rd", DSOV)])
        self.assertEqual(v.dsov, 0xBADF1701)
        self.assertEqual((v.priv_mask, v.crc_status, v.fpf_row),
                         (0, 0, UNREADABLE))
        self.assertEqual(v.shadow, {"DSOV_POISONED": 0xBADF1701})
        self.assertFalse(v.passed)
        self.assertTrue(v.poisoned)

    def test_other_bad_dsov_values_are_not_goldilocks(self):
        for dsov in (2, 0xFFFFFFFF, 0xBAD00100):
            with self.subTest(dsov=hex(dsov)):
                v = classify(FakeBar(DSOV=dsov))
                self.assertFalse(v.passed)
                self.assertFalse(v.poisoned)

    def test_as_dict_reports_the_write_mode(self):
        self.assertFalse(classify(FakeBar()).as_dict()["dsov_written"])
        self.assertTrue(classify(FakeBar(), write=True).as_dict()["dsov_written"])

    def test_poisoned_outcome_is_not_over(self):
        # our improvement over their campaign: a poisoned verdict maps to
        # its own outcome, never to "over" (the adaptive planner must not
        # read a dead controller as a too-deep shot)
        v = classify(FakeBar(FUSECTRL=0xBADF5040))
        self.assertEqual(classify_outcome(v), "poisoned")
        v = classify(FakeBar(DSOV=0xBADF1701))
        self.assertEqual(classify_outcome(v), "poisoned")
        # a real over (dsov 0, crc 0, priv read) stays "over"
        v = classify(FakeBar(DSOV=0, CRC_STATUS=0, PRIV_MASK=0))
        self.assertEqual(classify_outcome(v), "over")
        self.assertFalse(v.poisoned)


if __name__ == "__main__":
    unittest.main()
