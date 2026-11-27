#!/usr/bin/env python3
"""TASK 67 (UX66 F1/F2) — POST /api/burn/queue_start: atomic arm + burn
campaign start in ONE request, so the 120 s arm-token TTL race across the
payload/campaign panels cannot lose the Goldilocks window.

Contract under test (service.queue_start_api):
  a. empty queue is refused BEFORE any gate runs (no token minted);
  b. not-Goldilocks mock state refuses with the arm gate's precise error
     (failing check named) and mints no token;
  c. happy path returns {started, records, token_ttl} and hands
     glitch_start mode=burn + the freshly minted token + the records +
     the caller's glitch params;
  d. the gates are REUSED, not duplicated: arm_api is the single
     Goldilocks/identity gate (spy proves the call and its phrase/bdf/
     dump), glitch_start owns record validation and launch;
  e. a glitch_start error propagates verbatim (e.g. campaign already
     running).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

GOLDILOCKS = {"status": {"DSOV": 0, "CRC_STATUS": 0x55,
                         "PRIV_MASK": 0xFFFFFFFF}}
LOCKED = {"status": {"DSOV": 1, "CRC_STATUS": 0x55,
                     "PRIV_MASK": 0xFFFFFFFF}}
RECS = [{"row": 301, "value": "0x80070141", "old": "0x0"},
        {"row": 302, "value": "0x80070142", "old": "0x0"}]
GLITCH_PARAMS = {"v_dip": 354, "pulses": 3, "pw": 198, "gap": 150,
                 "delay": 117, "t_dip": -60, "max_attempts": 100,
                 "port": "/dev/ttyACM0"}


class QueueStartTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="t67-")
        self._mock = os.path.join(self._tmp, "mock.json")
        self._save = (S.CFG["mock"], S.CFG["state_dir"],
                      S.ARM["token"], S.ARM["expires"])
        S.CFG["state_dir"] = self._tmp
        self._set_mock(GOLDILOCKS)
        S.ARM["token"] = None
        S.ARM["expires"] = 0

    def tearDown(self):
        (S.CFG["mock"], S.CFG["state_dir"],
         S.ARM["token"], S.ARM["expires"]) = self._save

    def _set_mock(self, state):
        with open(self._mock, "w") as f:
            json.dump(state, f)
        S.CFG["mock"] = self._mock

    def _spy(self, name, ret):
        """Replace module global `name`, recording calls; return the list."""
        calls = []
        orig = getattr(S, name)
        self.addCleanup(setattr, S, name, orig)

        def spy(body):
            calls.append(body)
            return ret(body) if callable(ret) else ret
        setattr(S, name, spy)
        return calls

    # ---- a. empty queue ------------------------------------------------
    def test_empty_queue_refused_before_any_gate(self):
        arm_calls = self._spy("arm_api", {"token": "x", "expires_in": 120})
        start_calls = self._spy("glitch_start", {"started": True})
        out = S.queue_start_api(dict(GLITCH_PARAMS, records=[]))
        self.assertIn("error", out)
        self.assertIn("queue is empty", out.get("error", ""))
        self.assertEqual(arm_calls, [])       # refused before arming
        self.assertEqual(start_calls, [])     # and before starting

    # ---- b. arm gate refuses, no token ---------------------------------
    def test_not_goldilocks_refuses_with_precise_error(self):
        self._set_mock(LOCKED)
        start_calls = self._spy("glitch_start", {"started": True})
        out = S.queue_start_api(dict(GLITCH_PARAMS, records=RECS))
        self.assertIn("error", out)
        self.assertIn("not Goldilocks", out.get("error", ""))
        self.assertIn("dsov", out.get("error", ""))   # failing check named
        self.assertIsNone(S.ARM["token"])     # no token minted
        self.assertEqual(start_calls, [])     # nothing started

    # ---- c. happy path --------------------------------------------------
    def test_happy_path_starts_with_minted_token(self):
        start_calls = self._spy(
            "glitch_start", lambda b: {"started": True, "params": b,
                                       "records": len(b["records"])})
        out = S.queue_start_api(dict(GLITCH_PARAMS, records=RECS))
        self.assertTrue(out.get("started"), out)
        self.assertEqual(out["records"], len(RECS))
        self.assertEqual(out["token_ttl"], 120)
        self.assertEqual(out["token"], S.ARM["token"])  # the minted token
        self.assertEqual(len(start_calls), 1)
        body = start_calls[0]
        self.assertEqual(body["mode"], "burn")
        self.assertEqual(body["token"], S.ARM["token"])
        self.assertEqual(body["records"], RECS)
        for k, v in GLITCH_PARAMS.items():   # glitch params pass through
            self.assertEqual(body[k], v)

    # ---- d. gates reused, not duplicated --------------------------------
    def test_reuses_arm_gate_and_passes_its_token(self):
        arm_calls = self._spy("arm_api", {"token": "tok-123", "expires_in": 120})
        start_calls = self._spy(
            "glitch_start", lambda b: {"started": True, "params": b,
                                       "records": len(b["records"])})
        out = S.queue_start_api(dict(GLITCH_PARAMS, records=RECS,
                                     bdf="0000:01:00.0", dump="sn-1/d"))
        self.assertTrue(out.get("started"), out)
        self.assertEqual(len(arm_calls), 1)
        self.assertEqual(arm_calls[0]["phrase"], "BURN")
        self.assertEqual(arm_calls[0]["bdf"], "0000:01:00.0")
        self.assertEqual(arm_calls[0]["dump"], "sn-1/d")
        # the token arm_api minted is the token glitch_start receives
        self.assertEqual(start_calls[0]["token"], "tok-123")

    def test_arm_gate_error_propagates_without_start(self):
        self._spy("arm_api", {"error": "GPU x is not Goldilocks — failing: crc_ok"})
        start_calls = self._spy("glitch_start", {"started": True})
        out = S.queue_start_api(dict(GLITCH_PARAMS, records=RECS))
        self.assertIn("crc_ok", out.get("error", ""))
        self.assertNotIn("started", out)
        self.assertEqual(start_calls, [])

    # ---- e. start error propagates verbatim -----------------------------
    def test_start_error_propagates(self):
        self._spy("glitch_start", {"error": "campaign already running"})
        out = S.queue_start_api(dict(GLITCH_PARAMS, records=RECS))
        self.assertEqual(out, {"error": "campaign already running"})
        self.assertNotIn("started", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
