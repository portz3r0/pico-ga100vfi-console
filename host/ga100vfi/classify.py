"""The five per-attempt checks, in the order the method prescribes.

1. glitch (issued elsewhere)
2. sleep 200 ms
3. read FUSECTRL (0x00820000); 0xBADFxxxx means the fuse controller is
   poisoned — read nothing else (further BAR0 reads on such a card are a
   host-hang risk) and return a poisoned verdict
4. read DSOV (0x00820084); continue unless it reads 0 (a 0xBADFxxxx DSOV
   behind a healthy FUSECTRL is the same poison, seen on one card)
5. read an FPF row (0x00824314); continue if it reads 0xffffffff
6. optionally write DSOV = 1 (0x00820040 = EN_SW_OVERRIDE), read back;
   continue unless it reads 1. The write is OPT-IN (write=True or
   CLASSIFY_WRITE=1): the register keeps its value across PEX_RST, so one
   write makes every later shot of the boot run under the software
   override — which also poisons CMD_READ fuse reads (0xbadf____ garbage)
   for the die-ID gate and fusedump. Without the write, check 6 is read
   only and left out of Verdict.checks.
7. dump the shadow fuse registers and compare with the baseline (logged only)
8. read NV_FUSE_OPT_PRIV_LEVEL_MASK (0x008200fc); Goldilocks reads 0xffffffff
   (both PLMs wide open, so the shadow option words are writable)
9. read NV_FUSE_CRC_STATUS (0x00820070); continue unless it reads 0x55 (both
   fuse hash regions H0/H1 parsed cleanly). 0x00 == block not CRC-validated,
   a "problematic" Goldilocks that otherwise looks correct.

Poison verdicts carry priv_mask 0 and crc 0 because nothing was read;
shadow names the source register (FUSECTRL_POISONED / DSOV_POISONED). On
the cards tested a poisoned controller stayed poisoned until a POWER
CYCLE — later shots of the same boot read poisoned too.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

DSOV = 0x00820084
FPF_ROW = 0x00824314
DSOV_SET = 0x00820040          # EN_SW_OVERRIDE
PRIV_MASK = 0x008200fc
CRC_STATUS = 0x00820070
CRC_GOOD = 0x55
FUSECTRL = 0x00820000
POISON_TAG = 0xBADF0000

# Shadow registers that move when the fuse block is misread.
SHADOW = {
    "STATUS_OPT_GPC": 0x00820C1C,
    "NV_FUSE_OPT_GPC_DEFECTIVE": 0x008205C4,
    "STATUS_OPT_FBP": 0x00820D38,
    "FBP_DEFECTIVE": 0x008205CC,
    "FBPA_DEFECTIVE": 0x008205D0,
}

UNREADABLE = 0xFFFFFFFF


@dataclass
class Verdict:
    dsov: int
    fpf_row: int
    dsov_writeback: int
    priv_mask: int
    crc_status: int
    shadow: dict[str, int] = field(default_factory=dict)
    shadow_diff: dict[str, tuple[int, int]] = field(default_factory=dict)
    # False when classify() did not write 0x00820040 (EN_SW_OVERRIDE):
    # dsov_writeback is then only a read and check 6 is left out of
    # `checks`. Poison verdicts are always False — nothing was written.
    dsov_written: bool = True

    @property
    def poisoned(self) -> bool:
        return ("FUSECTRL_POISONED" in self.shadow
                or "DSOV_POISONED" in self.shadow)

    @property
    def checks(self) -> dict[str, bool]:
        c = {
            "dsov_zero": self.dsov == 0,
            "fpf_readable": self.fpf_row != UNREADABLE,
            "dsov_settable": self.dsov_writeback == 1,
            "priv_mask_open": self.priv_mask == 0xFFFFFFFF,
            "crc_valid": self.crc_status == CRC_GOOD,
        }
        if not self.dsov_written:
            del c["dsov_settable"]
        return c

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "dsov": self.dsov,
            "fpf_row": self.fpf_row,
            "dsov_writeback": self.dsov_writeback,
            "dsov_written": self.dsov_written,
            "priv_mask": self.priv_mask,
            "crc_status": self.crc_status,
            "shadow": self.shadow,
            "shadow_diff": self.shadow_diff,
        }


def snapshot(bar) -> dict[str, int]:
    return {name: bar.rd32(off) for name, off in SHADOW.items()}


def _poisoned(value: int) -> bool:
    return (value & 0xFFFF0000) == POISON_TAG


def classify(bar, baseline: dict[str, int] | None = None,
             write: bool | None = None) -> Verdict:
    """Run checks 3-9 (see module docstring).

    FUSECTRL is read first: a disturbed fuse read can leave the
    controller at 0xBADFxxxx and further BAR0 reads on such a card are a
    host-hang risk — the verdict then reads nothing else. Same for a
    0xBADFxxxx DSOV behind a healthy FUSECTRL. A poisoned controller
    stays poisoned until a power cycle.

    The EN_SW_OVERRIDE write (check 6) is opt-in: write=True, or
    CLASSIFY_WRITE=1 in the environment when write is None. Without it
    0x00820040 is only read and check 6 is left out of Verdict.checks,
    so Verdict.passed rests on DSOV 0, a readable FPF row, privilege
    mask 0xFFFFFFFF and CRC 0x55.
    """
    if write is None:
        write = os.environ.get("CLASSIFY_WRITE") == "1"
    ctrl = bar.rd32(FUSECTRL)
    if _poisoned(ctrl):
        return Verdict(0, UNREADABLE, 0, 0, 0,
                       {"FUSECTRL_POISONED": ctrl}, {}, dsov_written=False)
    dsov = bar.rd32(DSOV)
    if _poisoned(dsov):
        return Verdict(dsov, UNREADABLE, 0, 0, 0,
                       {"DSOV_POISONED": dsov}, {}, dsov_written=False)
    fpf = bar.rd32(FPF_ROW)
    if write:
        bar.wr32(DSOV_SET, 1)
    writeback = bar.rd32(DSOV_SET)
    priv = bar.rd32(PRIV_MASK)
    crc = bar.rd32(CRC_STATUS)
    shadow = snapshot(bar)
    diff = {}
    if baseline:
        diff = {k: (baseline.get(k, 0), v) for k, v in shadow.items() if baseline.get(k) != v}
    return Verdict(dsov, fpf, writeback, priv, crc, shadow, diff, write)
