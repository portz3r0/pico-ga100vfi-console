#!/usr/bin/env python3
"""TASK 16 — adaptive 3D as the default v_dip strategy + honest pico-only
port enumeration: every port carries vid/vendor/product from sysfs, pico:
True only for Raspberry Pi (vid 0x2e8a or a by-id name naming Raspberry
Pi), and default is None when nothing is present — never a phantom
/dev/ttyACM0 the GUI happily selects.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

GUI = os.path.join(os.path.dirname(__file__), "..",
                   "ga100vfi", "console", "gui.py")


def _mk_tty(root, name, device_uevent=None, parent_uevent=None):
    """Fake sysfs: <root>/sysfs/tty/<name>/device/uevent plus an optional
    parent uevent one hop up (the usb device node, where cdc-acm's
    PRODUCT=<vid>/... lives)."""
    t = os.path.join(root, "sysfs", "tty", name)
    os.makedirs(os.path.join(t, "device"), exist_ok=True)
    if device_uevent is not None:
        with open(os.path.join(t, "device", "uevent"), "w") as f:
            f.write(device_uevent)
    if parent_uevent is not None:
        with open(os.path.join(t, "uevent"), "w") as f:
            f.write(parent_uevent)
    return t


PICO_USB_UEVENT = ("DRIVER=usb\nPRODUCT=2e8a/1003/100\n"
                   "MANUFACTURER=Raspberry Pi\nPRODUCTNAME=RPI-RP2\n"
                   "DEVTYPE=usb_device\n")
ACM_TTY_UEVENT = "DRIVER=cdc_acm\nMAJOR=166\nMINOR=0\nDEVTYPE=usb_interface\n"
CP210X_UEVENT = ("DRIVER=cp210x\nVID=10c4\n"
                 "PRODUCT=ea60/SILICON_LABS_CP2102_USB_to_UART_Bridge_Converter/100\n"
                 "MANUFACTURER=SILICON_LABS\nPORT_NAME=ttyUSB0\n")


def _mk_dev(root, name):
    dev = root / "dev"
    (dev / "serial" / "by-id").mkdir(parents=True, exist_ok=True)
    (dev / name).touch()
    return dev


def _byid(root, link_name, tty):
    os.symlink(os.path.join("..", "..", tty),
               os.path.join(root, "dev", "serial", "by-id", link_name))


# ------------------------------------------------------- sysfs vid detection

def test_pico_vid_detected_and_default_prefers_it(tmp_path):
    # non-Pico sorts first alphabetically — default must still pick the Pico
    dev = _mk_dev(tmp_path, "ttyUSB0")
    open(os.path.join(dev, "ttyACM0"), "w").close()
    _mk_tty(tmp_path, "ttyUSB0", device_uevent=CP210X_UEVENT)
    _mk_tty(tmp_path, "ttyACM0", device_uevent=ACM_TTY_UEVENT,
            parent_uevent=PICO_USB_UEVENT)
    r = S.serial_ports(dev_dir=str(dev),
                       sysfs_tty_dir=str(tmp_path / "sysfs" / "tty"))
    by_path = {p["path"]: p for p in r["ports"]}
    pico = by_path[str(dev / "ttyACM0")]
    assert pico["vid"] == "0x2e8a"
    assert pico["vendor"] == "Raspberry Pi"
    assert pico["product"] == "RPI-RP2"
    assert pico["pico"] is True
    other = by_path[str(dev / "ttyUSB0")]
    assert other["vid"] == "0x10c4" and other["pico"] is False
    assert r["default"] == str(dev / "ttyACM0")
    assert "note" not in r


def test_non_pico_only_default_first_with_note(tmp_path):
    dev = _mk_dev(tmp_path, "ttyUSB0")
    open(os.path.join(dev, "ttyUSB1"), "w").close()
    _mk_tty(tmp_path, "ttyUSB0", device_uevent=CP210X_UEVENT)
    _mk_tty(tmp_path, "ttyUSB1", device_uevent=CP210X_UEVENT)
    r = S.serial_ports(dev_dir=str(dev),
                       sysfs_tty_dir=str(tmp_path / "sysfs" / "tty"))
    assert [p["pico"] for p in r["ports"]] == [False, False]
    assert r["default"] == str(dev / "ttyUSB0")   # first device, not a phantom
    assert r["note"] == ("no Raspberry Pi device found — showing other "
                         "serial ports")


def test_empty_no_phantom_default(tmp_path):
    dev = _mk_dev(tmp_path, "nothing")
    r = S.serial_ports(dev_dir=str(dev),
                       sysfs_tty_dir=str(tmp_path / "sysfs" / "tty"))
    assert r["ports"] == []
    assert r["default"] is None                   # never /dev/ttyACM0
    assert "note" not in r                        # nothing to annotate


def test_byid_raspberry_match_without_readable_vid(tmp_path):
    dev = _mk_dev(tmp_path, "ttyACM3")
    _mk_tty(tmp_path, "ttyACM3", device_uevent=ACM_TTY_UEVENT)  # no VID anywhere
    _byid(tmp_path, "usb-Raspberry_Pi_RP2350_E6613734A51564-if00", "ttyACM3")
    r = S.serial_ports(dev_dir=str(dev),
                       sysfs_tty_dir=str(tmp_path / "sysfs" / "tty"))
    p = r["ports"][0]
    assert p["vid"] is None                       # unreadable vid tolerated
    assert p["pico"] is True                      # by-id names Raspberry Pi
    assert r["default"] == str(dev / "ttyACM3")
    assert "note" not in r


def test_missing_sysfs_tree_tolerated(tmp_path):
    dev = _mk_dev(tmp_path, "ttyACM0")
    r = S.serial_ports(dev_dir=str(dev),
                       sysfs_tty_dir=str(tmp_path / "no-such-sysfs"))
    assert r["ports"][0]["vid"] is None           # port still listed
    assert r["ports"][0]["pico"] is False
    assert r["default"] == str(dev / "ttyACM0")   # first device, honest


# ------------------------------------------------------------- GUI strings

def _gui_src():
    with open(GUI, encoding="utf-8") as f:
        return f.read()


def test_gui_adaptive_option_selected():
    src = _gui_src()
    assert '<option value="adaptive" selected>' in src
    assert '<option value="fixed">fixed v_dip</option>' in src  # still selectable


def test_gui_no_pico_placeholder_and_no_phantom():
    src = _gui_src()
    assert "no pico detected" in src
    assert "/dev/ttyACM0 (not detected)" not in src   # old phantom gone
    assert "portOk" in src and "!portOk" in src       # start gated on it


def test_api_adaptive_default_unchanged():
    # API compatibility: server-side default stays params.get("adaptive")
    src = open(os.path.join(os.path.dirname(__file__), "..",
                            "ga100vfi", "console", "service.py"),
               encoding="utf-8").read()
    assert '"adaptive": bool(params.get("adaptive"))' in src
