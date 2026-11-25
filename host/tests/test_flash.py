#!/usr/bin/env python3
"""Pico flash API tests (offline, everything hardware-facing faked).

Cases:
  a. no .uf2 anywhere -> instructive error, nothing touched;
  b. full flow: 'b' sent, BOOTSEL drive appears, mount faked, uf2 really
     copied into the mount dir, umount, banner read back -> fw_marker;
  c. dead port + no BOOTSEL drive -> error telling you to hold BOOTSEL;
  d. drive already present -> no 'b' needed.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

TMP = tempfile.mkdtemp(prefix="flash-")
# the uf2 lives OUTSIDE TMP: TMP doubles as the fake state dir, whose
# pwmvid.uf2 candidate must be absent for case a
UF2 = os.path.join(tempfile.mkdtemp(prefix="flash-src-"), "pwmvid.uf2")
with open(UF2, "wb") as f:
    f.write(b"UF2" * 100)

S.time.sleep = lambda s: None              # no real waits
_orig = {k: getattr(S, k) for k in
         ("_pico_bootsel_drive", "_pico_boot_bootsel", "_pico_mount",
          "_pico_umount")}


def teardown():
    for k, v in _orig.items():
        setattr(S, k, v)


# ---- a. no uf2 --------------------------------------------------------------
S.CFG["state_dir"] = TMP
S.FIRMWARE_DIR = os.path.join(TMP, "nope")
r = S.pico_flash_api({})
assert "error" in r and "pwmvid.uf2" in r["error"], r
print("a missing uf2 -> instructive error: OK")

# ---- fake serial that answers 'v' with a banner ------------------------------
sent = []


class FakeSerial:
    def __init__(self, port, baud=0, timeout=0):
        self.port = port

    def write(self, data):
        sent.append(data)

    def reset_input_buffer(self):
        pass

    def read(self, n):
        return b"clk=150 MHz  last reset: power-on  fw=lab-psr1\r\n"

    def close(self):
        pass


fake_serial = types.ModuleType("serial")
fake_serial.Serial = FakeSerial
sys.modules["serial"] = fake_serial

# ---- b. full flow ------------------------------------------------------------
S.CFG["state_dir"] = TMP          # pwmvid.uf2 sits in the state dir
state = {"drive_tries": 0}


def drive_after_b(port):
    sent.append(("b", port))
    return None


def drive_second_look():
    state["drive_tries"] += 1
    if state["drive_tries"] >= 2:
        return "/dev/sdb", "RP2350"
    return None, None


S._pico_bootsel_drive = drive_second_look
S._pico_boot_bootsel = drive_after_b
S._pico_mount = lambda dev, mnt: None
S._pico_umount = lambda mnt: True
r = S.pico_flash_api({"port": "/dev/ttyACM9", "uf2": UF2})
assert r.get("flashed"), r
assert r["fw_marker"] and "lab-psr1" in r["banner"], r
mnt = os.path.join(tempfile.gettempdir(), "ga100vfi-flash")
assert os.path.isfile(os.path.join(mnt, "pwmvid.uf2")), "uf2 not copied"
assert ("b", "/dev/ttyACM9") in sent, sent
assert any("BOOTSEL drive" in s for s in r["steps"]), r["steps"]
print("b full flash flow + banner + marker: OK")

# ---- c. dead port, no drive ---------------------------------------------------
state["drive_tries"] = 0


def no_drive():
    return None, None


def dead_port(port):
    return f"cannot open pico port {port}: [Errno 13] permission denied"


S._pico_bootsel_drive = no_drive
S._pico_boot_bootsel = dead_port
r = S.pico_flash_api({"port": "/dev/ttyACM9", "uf2": UF2})
assert "error" in r and "BOOTSEL" in r["error"], r
print("c dead port + no drive -> BOOTSEL hint: OK")

# ---- d. drive already up: no 'b' needed ---------------------------------------
sent.clear()
S._pico_boot_bootsel = lambda port: (_ for _ in ()).throw(
    AssertionError("must not send 'b' when the drive is already up"))
S._pico_bootsel_drive = lambda: ("/dev/sdb", "RP2350")
r = S.pico_flash_api({"port": "/dev/ttyACM9", "uf2": UF2})
# 'b' must NOT have been sent (drive already up); only the banner 'v'
assert r.get("flashed") and sent == [b"v\n"], (r, sent)
print("d existing BOOTSEL drive skips 'b': OK")

teardown()
print("\nALL PICO-FLASH TESTS PASSED")
