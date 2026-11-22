"""Driver-bound guarded fuse capture for the console.

Ported from the proven standalone collector GPU2/ga100_dump.py (the
reference that reads fuses with the nvidia driver BOUND, gated on hardware
STATE, not driver presence). Offsets, the write allowlist, the idle wait,
the command delay, the 0xBADF poison check, the double-pass agreement and
the finally-restore are verbatim from that collector; deviations exist
only where the console's return shape demands it (dicts, not binary
frames; errors returned, never raised past this module).

The console pauses its live poll while nvidia is bound (raw BAR0 reads can
wedge GSP); this module is the manual, consented alternative: preflight
conditions first, then a 512-row double-pass CMD_READ sweep. Results are
UNVERIFIED — captured with the driver loaded.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import mmap
import os
from pathlib import Path
import re
import struct
import time

SYSFS = Path("/sys/bus/pci/devices")
DEVICE_IDS = (0x20C2, 0x20B5)
FUSE_BASE, FUSE_SIZE = 0x820000, 0x6000
ROW_COUNT = 512
CTRL, ADDR, RDATA = 0x820000, 0x820004, 0x820008
EN, DEBUG, SWIFF, IFF_CTRL, CTRL_PLM = 0x820040, 0x820060, 0x820088, 0x820028, 0x8200F8
EXTRA_REGISTERS = (0, 0x120060, 0xD65C, 0xD604)
BDF_RE = re.compile(r"[0-9a-f]{4}:[0-9a-f]{2}:[01][0-9a-f]\.[0-7]")
PMC_BOOT_0 = 0x0
GA100_CHIP_ID = 0x170   # PMC_BOOT_0[28:20]; ga100_dump Bar.__enter__


class CaptureError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise CaptureError(message)


def driver_of(bdf):
    try:
        return os.path.basename(os.readlink(f"{SYSFS}/{bdf}/driver"))
    except OSError:
        return None


def _boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_bytes().strip()


class Bar:
    """ga100_dump.Bar, verbatim except: takes a BDF string and the mmap
    covers exactly the fuse aperture the collector maps."""

    def __init__(self, bdf):
        require(BDF_RE.fullmatch(bdf) is not None, "Malformed BDF")
        self.device = SYSFS / bdf
        self.bdf = bdf
        self.fd = self.lock_fd = self.mm = None

    def identity(self):
        vendor = int((self.device / "vendor").read_text(), 16)
        device = int((self.device / "device").read_text(), 16)
        require(vendor == 0x10DE and device in DEVICE_IDS, "Unsupported or changed PCI identity")
        return device

    def __enter__(self):
        try:
            # Shares the writer's lock. Protects cooperating tools, not drivers.
            self.lock_fd = os.open(f"/tmp/ga100-ff-{self.bdf}.lock",
                                   os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.pci_device = self.identity()
            with (self.device / "config").open("rb", buffering=0) as config:
                self.config = config.read(256)
            require(len(self.config) >= 64, "PCI configuration read is incomplete")
            vendor, device, command = struct.unpack_from("<HHH", self.config)
            require(vendor == 0x10DE and device == self.pci_device and self.config[14] & 0x7F == 0,
                    "PCI configuration identity/header changed")
            require(command & 2, "PCI memory decoding is disabled; restore PCI access before collecting")
            resources = (self.device / "resource").read_text()
            start, end, flags = (int(v, 16) for v in resources.splitlines()[0].split())
            require(start and end - start + 1 >= FUSE_BASE + FUSE_SIZE and flags & 0x200,
                    "BAR0 has no usable Linux memory allocation")
            low = struct.unpack_from("<I", self.config, 16)[0]
            require(not low & 1 and (low >> 1) & 3 in (0, 2), "BAR0 is not a memory BAR")
            actual = low & 0xFFFFFFF0
            if low & 4:
                actual |= struct.unpack_from("<I", self.config, 20)[0] << 32
            require(actual == start, "BAR0 differs from Linux allocation; restore PCI access before collecting")
            self.fd = os.open(self.device / "resource0", os.O_RDWR | os.O_SYNC | os.O_CLOEXEC)
            self.mm = mmap.mmap(self.fd, FUSE_BASE + FUSE_SIZE, mmap.MAP_SHARED,
                                mmap.PROT_READ | mmap.PROT_WRITE)
            require((self.checked(0) >> 20) & 0x1FF == GA100_CHIP_ID, "PMC_BOOT_0 is not GA100")
            return self
        except BaseException:
            self.__exit__()
            raise

    def __exit__(self, *_):
        if self.mm is not None:
            self.mm.close()
            self.mm = None
        for name in ("fd", "lock_fd"):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)

    def read32(self, address):
        return struct.unpack_from("<I", self.mm, address)[0]

    def checked(self, address):
        value = self.read32(address)
        require(value >> 16 != 0xBADF and (value != 0xFFFFFFFF or address == CTRL_PLM),
                f"Register unavailable at {address:#x}: {value:#010x}")
        return value

    def write32(self, address, value):
        # Entire hardware-write allowlist. Never accepts a program/sense command,
        # write data, programming enable, security, GPIO, or voltage changes.
        allowed = ((address == CTRL and value == 1)
                   or (address == ADDR and 0 <= value < ROW_COUNT)
                   or (address == EN and value in (0, 1)))
        require(allowed, "Write outside collector read-operation allowlist")
        struct.pack_into("<I", self.mm, address, value)

    def write_checked(self, address, value):
        self.write32(address, value)
        actual = self.checked(address)
        require(actual == value, f"Read-selection write did not latch at {address:#x}: "
                f"requested {value:#010x}, read {actual:#010x}")

    def idle(self):
        deadline = time.monotonic() + 0.5
        while True:
            value = self.checked(CTRL)
            if (value >> 16) & 31 == 4:
                return
            require(time.monotonic() < deadline, "Fuse read controller timeout")
            time.sleep(0.0001)

    def row(self, index):
        require(self.checked(EN) == 0, "Physical reads require software override disabled")
        self.write_checked(ADDR, index)
        self.idle()
        self.write32(CTRL, 1)  # READ is the only command in this script.
        self.checked(CTRL)  # Flush posted write before command sampling delay.
        time.sleep(0.001)
        self.idle()
        return self.read32(RDATA)  # Every bit pattern is valid raw data.


@contextmanager
def physical_mode(bar):
    """ga100_dump.physical_mode, verbatim."""
    bar.idle()
    privilege = bar.checked(CTRL_PLM)
    require(privilege == 0xFFFFFFFF,
            f"FUSECTRL host read access must already be open "
            f"({CTRL_PLM:#x}={privilege:#010x}, expected 0xffffffff); "
            "complete the existing card-access preparation first")
    require(bar.checked(DEBUG) == 0, "Controller debug/read mode must initially be zero")
    require(bar.checked(SWIFF) == 0 and bar.checked(IFF_CTRL) == 0, "Fuse loader operation pending")
    enabled, address = bar.checked(EN), bar.checked(ADDR)
    require(enabled in (0, 1) and address < ROW_COUNT, "Noncanonical fuse read state")
    try:
        if enabled:
            bar.write_checked(EN, 0)
        yield
    finally:
        # No more state changes after an uncertain command outcome.
        # A non-idle or inaccessible controller makes this card FAIL.
        control = bar.checked(CTRL)
        require((control >> 16) & 31 == 4, "Controller not idle; read state could not be restored")
        bar.write_checked(ADDR, address)
        bar.write_checked(EN, enabled)


def register_snapshot(bar):
    """ga100_dump.register_snapshot; returns a JSON-safe {hex: value} dict
    instead of packed bytes (console return-shape deviation)."""
    pairs = [(address, bar.read32(address)) for address in EXTRA_REGISTERS]
    pairs.extend((address, bar.read32(address))
                 for address in range(FUSE_BASE, FUSE_BASE + FUSE_SIZE, 4))
    return {f"{address:#08x}": value for address, value in pairs}


# ------------------------------------------------------------------ preflight
def _cond(name, ok, value, expected, hint):
    return {"name": name, "ok": bool(ok), "value": value, "expected": expected,
            "hint": hint}


def preflight(bar) -> list:
    """Conditions guarded_capture will check before touching the controller.
    Never raises: an unreadable register is a failed condition. checked()
    semantics apply, including the CTRL_PLM==0xFFFFFFFF exemption (open
    privilege reads as all-ones by design)."""
    conds = []

    def probe(name, read, ok_fn, expected, hint):
        try:
            value = read()
            conds.append(_cond(name, ok_fn(value), f"{value:#010x}", expected, hint))
        except CaptureError as e:
            conds.append(_cond(name, False, f"unreadable ({e})", expected,
                               "BAR0 unreadable — bus hung or PCIe link down"))

    probe("PMC_BOOT_0 is GA100", lambda: bar.checked(PMC_BOOT_0),
          lambda v: (v >> 20) & 0x1FF == GA100_CHIP_ID, "chip id 0x170",
          "not a GA100 — wrong card or BAR0 garbage")
    probe("FUSECTRL_PLM open (host read access)", lambda: bar.checked(CTRL_PLM),
          lambda v: v == 0xFFFFFFFF, "0xFFFFFFFF",
          "PLM locked — run the PLM unlock first")
    probe("DEBUGCTRL zero", lambda: bar.checked(DEBUG),
          lambda v: v == 0, "0x0",
          "controller debug/read mode nonzero — do not capture; investigate first")
    probe("SWIFF zero", lambda: bar.checked(SWIFF),
          lambda v: v == 0, "0x0",
          "fuse loader transaction pending — wait/retry")
    probe("IFF_CTRL zero", lambda: bar.checked(IFF_CTRL),
          lambda v: v == 0, "0x0",
          "fuse loader transaction pending — wait/retry")
    probe("FUSECTRL idle", lambda: bar.checked(CTRL),
          lambda v: (v >> 16) & 31 == 4, "state 4 (idle)",
          "fuse read controller busy — wait for it to go idle, then retry")
    probe("EN_SW_OVERRIDE canonical", lambda: bar.checked(EN),
          lambda v: v in (0, 1), "0x0 or 0x1",
          "software override set — physical reads need it disabled")
    probe("FUSEADDR canonical", lambda: bar.checked(ADDR),
          lambda v: v < ROW_COUNT, f"< {ROW_COUNT}",
          "fuse address counter out of range — controller state unknown")
    return conds


# -------------------------------------------------------------------- capture
def guarded_capture(bdf) -> dict:
    """Driver-bound manual capture. Returns a result dict; never raises.

    Success: {"rows": [...512 ints...], "passes_agree": True,
              "regs": {"before": {...}, "after": {...}},
              "driver_bound": True, "ts": iso}
    Failure: {"error": msg} (+ "conditions" when preflight refused).
    """
    conds = None
    try:
        drv = driver_of(bdf)
        if not (drv and "nvidia" in drv):
            return {"error": f"driver '{drv}' not bound on {bdf} — "
                             "use the normal full dump (no guard needed)"}
        boot = _boot_id()
        with Bar(bdf) as bar:
            bar.identity()   # ga100_dump.capture: re-check before reading
            conds = preflight(bar)
            failed = [c for c in conds if not c["ok"]]
            if failed:
                return {"error": "preflight refused: "
                                 + "; ".join(c["name"] for c in failed),
                        "conditions": conds}
            with physical_mode(bar):
                before = register_snapshot(bar)
                row0 = [bar.row(i) for i in range(ROW_COUNT)]
                row1 = [bar.row(i) for i in range(ROW_COUNT)]
                after = register_snapshot(bar)
                require(row0 == row1, "Physical fuse read passes disagree")
                require(any(v not in (0, 0xFFFFFFFF) for v in row0),
                        "Fuse array is blank or unavailable")
            require(bar.identity() == bar.pci_device, "PCI identity changed during capture")
        drv_end = driver_of(bdf)
        require(drv_end == drv,
                f"driver changed during capture ({drv} -> {drv_end})")
        require(_boot_id() == boot, "Host boot changed during capture")
        return {"rows": row0, "passes_agree": True,
                "regs": {"before": before, "after": after},
                "driver_bound": True,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    except CaptureError as e:
        out: dict = {"error": str(e)}
        if conds is not None:
            out["conditions"] = conds
        return out
    except (OSError, ValueError) as e:
        return {"error": f"{type(e).__name__}: {e}"}
