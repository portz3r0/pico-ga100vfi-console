#!/usr/bin/env python3
"""TASK 70 — VBIOS flash section (service side).

Contract under test (service vbios_* APIs):
  a. mock-mode happy paths: /api/vbios/list, browse, backup, flash;
  b. flash refuses without confirm, while a campaign runs, and while the
     nvidia driver is BOUND (owner correction: nvflash FAILS with the
     driver bound — flash requires it UNBOUND, same as fuse work);
  c. the protectoff checkbox PREPENDS `nvflash --protectoff` before the
     flash command (explicit argv lists, no shell);
  d. backup verification rejects empty / all-00 / all-FF content;
  e. journal events (vbios_backup / vbios_flash) are on disk BEFORE the
     commands run — same fsync discipline as fuse writes;
  f. a fresh (<24 h) backup for the serial is reused, not re-saved;
  g. nvflash is VENDORED: host/bin/nvflash exists, is executable, md5
     recorded; mock mode never executes a subprocess.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

HOST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VENDOR_NVF = os.path.join(HOST_DIR, "bin", "nvflash")
# nvflash 5.867.0 vendored from the HP bench /usr/bin/nvflash, 2026-11-27
VENDOR_MD5 = "0ea66b59f4ae93fec50900b66371096e"


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


class VbiosTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="t70-")
        self._save = (S.CFG["mock"], S.CFG["state_dir"], S.CFG["rom_dir"],
                      S.CFG["nvflash_path"], S.GLITCH["running"])
        self._mock = os.path.join(self._tmp, "mock.json")
        with open(self._mock, "w") as f:
            json.dump({"serial": "12345",
                       "status": {"DSOV": 0, "CRC_STATUS": 0x55,
                                  "PRIV_MASK": 0xFFFFFFFF}}, f)
        S.CFG["mock"] = self._mock
        S.CFG["state_dir"] = os.path.join(self._tmp, "state")
        S.CFG["nvflash_path"] = None
        # rom dir with one rom + one decoy file + one subdir
        self._romdir = os.path.join(self._tmp, "roms")
        os.makedirs(os.path.join(self._romdir, "sub"))
        self._rom = os.path.join(self._romdir, "A100_test.rom")
        with open(self._rom, "wb") as f:
            f.write(b"\x55\xaa" * 1024)
        with open(os.path.join(self._romdir, "notes.txt"), "w") as f:
            f.write("not a rom")
        S.CFG["rom_dir"] = self._romdir
        S.GLITCH["running"] = False

    def tearDown(self):
        (S.CFG["mock"], S.CFG["state_dir"], S.CFG["rom_dir"],
         S.CFG["nvflash_path"], S.GLITCH["running"]) = self._save

    def _patch(self, name, fn):
        orig = getattr(S, name)
        self.addCleanup(setattr, S, name, orig)
        setattr(S, name, fn)

    def _fake_subprocess(self):
        """Fake subprocess.run: records argv + the journal content AT call
        time (proves the journal line was fsync'd before the command), and
        materialises --save targets as sane ROM images."""
        calls = []
        orig = S.subprocess.run
        self.addCleanup(setattr, S.subprocess, "run", orig)

        def run(argv, **kw):
            jp = S._journal_path()
            journal = ""
            if os.path.exists(jp):
                with open(jp) as jf:
                    journal = jf.read()
            calls.append({"argv": list(argv), "journal": journal,
                          "input": kw.get("input")})
            if "--save" in argv:
                with open(argv[argv.index("--save") + 1], "wb") as f:
                    f.write(b"\x55\xaa" * 512)
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n",
                                               stderr="")
        S.subprocess.run = run
        return calls

    def _no_subprocess(self):
        orig = S.subprocess.run
        self.addCleanup(setattr, S.subprocess, "run", orig)

        def run(argv, **kw):
            raise AssertionError(f"subprocess executed in mock mode: {argv}")
        S.subprocess.run = run

    def _journal_events(self):
        jp = S._journal_path()
        if not os.path.exists(jp):
            return []
        with open(jp) as f:
            return [json.loads(l)["event"] for l in f if l.strip()]

    # ---- a. mock happy paths ------------------------------------------
    def test_list_happy(self):
        self._no_subprocess()
        j = S.vbios_list_api()
        self.assertEqual(j["rom_dir"], self._romdir)
        self.assertEqual([r["name"] for r in j["roms"]], ["A100_test.rom"])
        self.assertEqual(j["roms"][0]["md5"], md5(self._rom))
        self.assertEqual(j["roms"][0]["size"], 2048)
        self.assertEqual(j["backups"], [])
        self.assertIsNone(j["driver"]["bound"])
        self.assertTrue(j["nvflash"]["found"])   # vendored binary resolves

    def test_browse_happy_and_filters(self):
        self._no_subprocess()
        j = S.vbios_browse_api(self._romdir)
        self.assertEqual(j["dir"], self._romdir)
        self.assertEqual(j["dirs"], ["sub"])
        self.assertEqual([r["name"] for r in j["roms"]], ["A100_test.rom"])
        self.assertEqual(j["parent"], self._tmp)
        # default dir when none given
        self.assertEqual(S.vbios_browse_api(None)["dir"], self._romdir)
        # traversal: '..' resolves, not spliced; missing dir errors
        self.assertEqual(S.vbios_browse_api(self._romdir + "/../" +
                                            os.path.basename(self._romdir)
                                            )["dir"], self._romdir)
        self.assertIn("error", S.vbios_browse_api(self._romdir + "/nope"))

    def test_backup_happy(self):
        self._no_subprocess()
        j = S.vbios_backup_api()
        self.assertTrue(j.get("ok"), j)
        self.assertTrue(j["path"].startswith(
            os.path.join(S.CFG["state_dir"], "vbios-backups", "12345-")))
        self.assertTrue(j["path"].endswith(".rom"))
        self.assertEqual(j["md5"], md5(j["path"]))
        self.assertIn("vbios_backup", self._journal_events())

    def test_flash_happy_mock(self):
        self._no_subprocess()          # mock must never execute nvflash
        j = S.vbios_flash_api({"rom": self._rom, "confirm": True})
        self.assertTrue(j.get("ok"), j)
        self.assertIn("mock", j["output_tail"])
        self.assertTrue(os.path.isfile(j["backup"]["path"]))
        self.assertEqual(j["backup"]["md5"], md5(j["backup"]["path"]))
        self.assertIn("lspci", j["post_verify"])
        self.assertIn("COLD BOOT", j["post_verify"]["note"])
        ev = self._journal_events()
        self.assertIn("vbios_backup", ev)
        self.assertIn("vbios_flash", ev)

    def test_flash_reuses_fresh_backup(self):
        self._no_subprocess()
        j1 = S.vbios_flash_api({"rom": self._rom, "confirm": True})
        j2 = S.vbios_flash_api({"rom": self._rom, "confirm": True})
        self.assertEqual(j1["backup"]["path"], j2["backup"]["path"])
        backups = os.listdir(S.vbios_backups_dir())
        self.assertEqual(len(backups), 1, backups)

    # ---- b. refusals ----------------------------------------------------
    def test_flash_refuses_without_confirm(self):
        self._no_subprocess()
        j = S.vbios_flash_api({"rom": self._rom})
        self.assertIn("confirm", j.get("error", ""))
        self.assertEqual(self._journal_events(), [])   # nothing journalised

    def test_flash_refuses_missing_rom(self):
        self._no_subprocess()
        j = S.vbios_flash_api({"rom": "/nope/x.rom", "confirm": True})
        self.assertIn("not an existing", j.get("error", ""))

    def test_flash_refuses_campaign_running(self):
        self._no_subprocess()
        S.GLITCH["running"] = True
        j = S.vbios_flash_api({"rom": self._rom, "confirm": True})
        self.assertIn("campaign running", j.get("error", ""))

    def test_flash_refuses_driver_bound(self):
        # owner correction (INVERTED): nvflash FAILS with the nvidia driver
        # bound — flash requires it UNBOUND, same as fuse work.
        self._no_subprocess()
        self._patch("driver_of", lambda bdf: "nvidia")
        j = S.vbios_flash_api({"rom": self._rom, "confirm": True})
        self.assertIn("bound", j.get("error", ""))
        self.assertIn("nvflash fails", j.get("error", ""))
        self.assertEqual(self._journal_events(), [])

    # ---- c/d/e. real-mode command order, journal-before-command ---------
    def _real_mode(self):
        S.CFG["mock"] = None
        self._patch("resolve_target", lambda requested=None:
                    ("0000:41:00.0", None))
        self._patch("driver_of", lambda bdf: None)
        self._patch("card_serial", lambda bdf: ("12345", "test"))
        self._patch("vb_post_verify", lambda bdf: {"lspci": "x",
                                                   "nvidia_smi": "y",
                                                   "note": "n"})
        return self._fake_subprocess()

    def test_flash_command_sequence_without_protectoff(self):
        calls = self._real_mode()
        j = S.vbios_flash_api({"rom": self._rom, "confirm": True})
        self.assertTrue(j.get("ok"), j)
        argvs = [c["argv"] for c in calls]
        self.assertEqual(len(argvs), 2, argvs)          # save, then flash
        self.assertIn("--save", argvs[0])
        self.assertEqual(argvs[1][1:], ["-4", "-5", self._rom])
        self.assertNotIn("--protectoff", [a for c in argvs for a in c])
        self.assertTrue(argvs[0][0].endswith("nvflash"))  # vendored binary

    def test_protectoff_checkbox_prepends_command(self):
        calls = self._real_mode()
        j = S.vbios_flash_api({"rom": self._rom, "confirm": True,
                               "protectoff": True})
        self.assertTrue(j.get("ok"), j)
        argvs = [c["argv"] for c in calls]
        self.assertEqual(len(argvs), 3, argvs)
        self.assertIn("--save", argvs[0])
        self.assertIn("--protectoff", argvs[1])
        self.assertEqual(argvs[2][1:], ["-4", "-5", self._rom])
        # prompts auto-answered 'y' on stdin
        self.assertTrue(calls[2]["input"].startswith("y\n"))

    def test_journal_events_written_before_commands(self):
        calls = self._real_mode()
        j = S.vbios_flash_api({"rom": self._rom, "confirm": True,
                               "protectoff": True})
        self.assertTrue(j.get("ok"), j)
        # at the --save call the vbios_backup event was already on disk
        self.assertIn('"event": "vbios_backup"', calls[0]["journal"])
        # at the --protectoff / flash calls the vbios_flash events were
        self.assertIn('"event": "vbios_flash"', calls[1]["journal"])
        self.assertIn('"step": "flash"', calls[2]["journal"])

    def test_flash_refuses_when_backup_fails(self):
        calls = self._real_mode()
        # nvflash --save "succeeds" but produces an all-FF image
        orig = S.subprocess.run

        def run(argv, **kw):
            if "--save" in argv:
                with open(argv[argv.index("--save") + 1], "wb") as f:
                    f.write(b"\xff" * 4096)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        S.subprocess.run = run
        j = S.vbios_flash_api({"rom": self._rom, "confirm": True})
        S.subprocess.run = orig
        self.assertFalse(j.get("ok", True))
        self.assertIn("backup", j.get("error", ""))
        self.assertIn("all-FF", j.get("error", ""))
        self.assertEqual([c["argv"] for c in calls if "-4" in c["argv"]],
                         [])                          # flash never ran

    # ---- d. backup sanity -----------------------------------------------
    def test_backup_sanity_rejects_bad_images(self):
        d = tempfile.mkdtemp()
        cases = {"ff.rom": b"\xff" * 4096, "zero.rom": b"\x00" * 4096,
                 "empty.rom": b""}
        for n, data in cases.items():
            p = os.path.join(d, n)
            with open(p, "wb") as f:
                f.write(data)
            self.assertIsNotNone(S._backup_sane(p), n + " must be rejected")
            self.assertIn("not a VBIOS image" if data else "empty",
                          S._backup_sane(p))
        good = os.path.join(d, "good.rom")
        with open(good, "wb") as f:
            f.write(b"\xff" * 4095 + b"\x00")
        self.assertIsNone(S._backup_sane(good))

    # ---- g. vendored binary ----------------------------------------------
    def test_vendored_nvflash(self):
        self.assertTrue(os.path.isfile(VENDOR_NVF),
                        "host/bin/nvflash must be vendored in the repo")
        self.assertTrue(os.access(VENDOR_NVF, os.X_OK),
                        "host/bin/nvflash must be executable")
        self.assertEqual(md5(VENDOR_NVF), VENDOR_MD5,
                         "vendored nvflash md5 changed — re-record evidence")
        # resolution order: CFG override wins, then vendored, then PATH
        S.CFG["nvflash_path"] = "/opt/custom/nvflash"
        self.assertEqual(S.nvflash_bin(), "/opt/custom/nvflash")
        S.CFG["nvflash_path"] = None
        self.assertEqual(S.nvflash_bin(), VENDOR_NVF)


if __name__ == "__main__":
    unittest.main(verbosity=2)
