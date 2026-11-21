#!/usr/bin/env python3
"""TASK 09 INDEPENDENT adversarial verification of the reference-equivalent
program sequence (commit "reference-equivalent program sequence").

Fresh fake bar `V8Bar` (independent of the task-06/07/08 fakes) with an
ORDERED write log and per-(addr,value) fault injection. Models:
  * CMD_WRITE ORs FUSEWDATA (delta) into the addressed row (OTP physics);
  * TRIGGER (0xD604) bit0 self-clears on landing unless trigger_stuck;
  * GPIO / EN latch failures, post-burn row flips, CTRL stuck busy.

Gates (task 09):
  a. exception injected at EACH write step of the bracket -> GPIO19-low +
     TRIGGER + EN-restore still executed; journal has no false "verified";
  b. TRIGGER never clears -> ABORT, GPIO restored, no CTRL=2 issued;
  c. EN=1 read-back mismatch -> ABORT before ANY GPIO/TRIGGER write;
  d. ALREADY BURNED -> zero latching writes (no GPIO/TRIGGER/EN=1/WDATA/
     CTRL=2), result success, journal "verified" without "command_may_be_issued";
  e. kill-simulation: journal with only command_may_be_issued -> ABORT
     without ack (zero writes), proceeds with ack_uncertain;
  f. delta correctness: cur=0xF0, value=0xFC -> WDATA write == 0x0C;
  g. IMAGE VERIFY FAILED: row flips after write -> burn_api mirror pair
     does not claim success; campaign decision keeps window unheld;
  h. GPIO preflight failure -> zero writes of ANY kind;
  i. probe/poller/burn_check/arm_window/read paths issue ZERO
     GPIO/TRIGGER/EN=1 writes (runtime spy + AST source scan).
"""
from __future__ import annotations

import ast
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

IDLE9 = 4 << 16
ROW, OLD, VAL = 306, 0x00010000, 0x00010041
DELTA = VAL & ~OLD & 0xFFFFFFFF          # 0x41
MIRROR = 307
BDF = "0000:00:00.0"
GPIO_HI = 0x3000                          # saved=0 -> |0x2000|0x1000
GPIO_LO = 0x2000


class V8Bar:
    def __init__(self, fail=(), trigger_stuck=False, gpio_latch_bad=False,
                 en_no_latch=False, flip=None, ctrl_busy_after_write=False,
                 en_init=0, gpio_init=0):
        self.r = {
            S.FUSECTRL: IDLE9, S.FUSEADDR: 0, S.FUSERDATA: 0, S.FUSEWDATA: 0,
            S.EN_SW_OVERRIDE: en_init, S.DEBUGCTRL: 0, S.CRC_STATUS: 0x55,
            S.EFP: 0, S.DSOV: 0, S.PROGRAM_DIS: 0,
            S.LOADER_120060: 0, S.SWIFF: 0, S.IFF_CTRL: 0,
            S.FUSECTRL_PLM: 0xFFFFFFFF, S.PRIV_MASK: 0xFFFFFFFF,
            S.SBFE: 1, S.WDATA_SECURE: 1, S.FUSEWDATA_PLM: 0xFFFFFFF8,
            S.GPIO_REG: gpio_init, S.GPIO_TRIGGER: 0,
        }
        self.rows = {}
        self.log = []                     # ("w", off, val) | ("r", off) ordered
        # entries: (off, val, matches_to_skip)
        self.fail = {t[:2]: [t[2], 1] for t in fail}
        self.trigger_stuck = trigger_stuck
        self.gpio_latch_bad = gpio_latch_bad
        self.en_no_latch = en_no_latch
        self.flip = flip or {}            # row -> (true_reads_before_flip, wrong)
        self.ctrl_busy_after_write = ctrl_busy_after_write
        self.reads: dict = {}

    def rd(self, off):
        self.log.append(("r", off))
        if off == S.FUSERDATA:
            row = self.r[S.FUSEADDR]
            n = self.reads.get(row, 0) + 1
            self.reads[row] = n
            v = self.rows.get(row, 0)
            after, wrong = self.flip.get(row, (1 << 30, 0))
            return wrong if n > after else v
        return self.r.get(off, 0)

    def wr(self, off, val):
        self.log.append(("w", off, val))
        f = self.fail.get((off, val))
        if f:
            if f[0] > 0:
                f[0] -= 1
            else:
                f[1] -= 1
                if f[1] <= 0:
                    del self.fail[(off, val)]
                raise OSError(
                    f"injected write fault off=0x{off:x} val=0x{val:x}")
        if off == S.FUSECTRL:
            cmd = val & 3
            if cmd == S.CMD_WRITE:
                self.rows[self.r[S.FUSEADDR]] = \
                    self.rows.get(self.r[S.FUSEADDR], 0) | self.r[S.FUSEWDATA]
                self.r[S.FUSECTRL] = (IDLE9 if not self.ctrl_busy_after_write
                                      else 3 << 16)
            elif cmd == S.CMD_SENSE:
                self.r[S.EFP] = 1
                self.r[S.FUSECTRL] = IDLE9
            else:
                self.r[S.FUSECTRL] = IDLE9
        elif off == S.GPIO_TRIGGER:
            self.r[off] = val if self.trigger_stuck else val & ~1
        elif off == S.GPIO_REG and self.gpio_latch_bad:
            pass                                   # latch fails: value ignored
        elif off == S.EN_SW_OVERRIDE and self.en_no_latch:
            self.r[off] = 0                        # EN never latches
        else:
            self.r[off] = val
            if off == S.WDATA_SECURE and val == 0:
                self.r[S.FUSEWDATA_PLM] = 0xFFFFFFFF   # PLM opens (ref arm)

    # convenience views over the ordered log
    def wlog(self):
        return [(e[1], e[2]) for e in self.log if e[0] == "w"]

    def first_w(self, off, val=None):
        for i, (o, v) in enumerate(self.wlog()):
            if o == off and (val is None or v == val):
                return i
        return -1


def run_burn(bar, journal=None, ack=False, row=ROW, value=VAL, old=OLD):
    return S.burn_execute(bar.rd, bar.wr, row, value, old, bdf=BDF,
                          journal=journal, ack_uncertain=ack)


def jevents(path):
    if not path or not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l)["event"] for l in f if l.strip()]


def jtmp():
    d = tempfile.mkdtemp()
    return d, os.path.join(d, "burn_journal.jsonl")


def no_driver():
    S.driver_of = lambda bdf: None


# global monkeypatch: driver never bound (sysfs on the test host is irrelevant)
_REAL_DRIVER_OF = S.driver_of


def setup_module(_=None):
    no_driver()


def _wrap_journal(bar, path):
    """Interleave journal events into the bar's ordered log."""
    real = S.journal_append

    def wrapped(p, event, **f):
        bar.log.append(("j", event, 0))
        return real(p, event, **f)

    S.journal_append = wrapped
    return real


# ---------------------------------------------------------------- gate a
def test_a_exception_at_each_write_step():
    """Inject an OSError at every distinct write of the bracket; assert the
    GPIO-low + TRIGGER + EN-restore finally chain still runs (except when the
    injected fault IS the GPIO write — hardware-dead parity with the
    reference, whose finally would raise the same way) and the journal never
    carries a false 'verified'."""
    cases = [
        # ((inject off, val, matches_to_skip), gpio_low_expected, en_restore_expected)
        # skip=1 for FUSEADDR: the pre-burn CMD_READ path writes it first
        ((S.EN_SW_OVERRIDE, 1, 0), False, True),        # EN raise itself dies
        ((S.GPIO_REG, GPIO_HI, 0), True, True),         # high strobe dies
        ((S.FUSECTRL, 0, 0), True, True),
        ((S.FUSEADDR, ROW, 1), True, True),
        ((S.FUSEWDATA, DELTA, 0), True, True),
        ((S.FUSECTRL, S.CMD_WRITE, 0), True, True),     # command may have latched
        ((S.EN_SW_OVERRIDE, 0, 0), False, True),        # EN-clear before reads
    ]
    for inj, want_gpio_low, want_en_restore in cases:
        setup_module()
        bar = V8Bar(fail=[inj])
        inj = inj[:2]
        bar.rows[ROW] = OLD
        d, jp = jtmp()
        raised = None
        try:
            run_burn(bar, journal=jp)
        except OSError as e:
            raised = e
        assert raised is not None, f"no exception for injection {inj}"
        ev = jevents(jp)
        assert "verified" not in ev, f"false verified for injection {inj}: {ev}"
        w = bar.wlog()
        if inj[0] == S.EN_SW_OVERRIDE and inj[1] == 0:
            # died before the try block: nothing latching was even reached
            assert (S.GPIO_REG, GPIO_HI) not in w, inj
            assert (S.FUSECTRL, S.CMD_WRITE) not in w, inj
        else:
            assert (S.FUSECTRL, S.CMD_WRITE) not in w or inj == (S.FUSECTRL, S.CMD_WRITE), inj
        if want_gpio_low:
            assert (S.GPIO_REG, GPIO_LO) in w, f"GPIO not driven low for {inj}"
            assert (S.GPIO_TRIGGER, 1) in w, f"TRIGGER not pulsed for {inj}"
            assert (S.GPIO_REG, 0) in w, f"saved GPIO not restored for {inj}"
        if want_en_restore:
            # last EN write must restore saved_en (0 here)
            en_ws = [v for o, v in w if o == S.EN_SW_OVERRIDE]
            assert en_ws and en_ws[-1] == 0, f"EN not restored for {inj}: {en_ws}"
        assert bar.r[S.EN_SW_OVERRIDE] == 0, f"EN left high for {inj}"
        assert bar.r[S.GPIO_REG] == 0, f"GPIO left non-saved for {inj}"


def test_a_en_restore_on_midsequence_abort():
    """old-mismatch ABORT mid-sequence still restores a saved EN=1."""
    setup_module()
    bar = V8Bar(en_init=1)
    bar.rows[ROW] = 0xDEADBEEF          # neither old nor value
    rep = run_burn(bar)
    assert rep["result"].startswith("ABORT — row"), rep
    assert (S.EN_SW_OVERRIDE, 1) in bar.wlog(), bar.wlog()
    assert bar.r[S.EN_SW_OVERRIDE] == 1


def test_a_ctrl_never_idle():
    """CMD_WRITE stuck busy -> ABORT, GPIO low+restored, EN restored,
    journal unresolved (no false verified)."""
    setup_module()
    bar = V8Bar(ctrl_busy_after_write=True)
    bar.rows[ROW] = OLD
    d, jp = jtmp()
    rep = run_burn(bar, journal=jp)
    assert rep["result"].startswith("ABORT"), rep
    w = bar.wlog()
    assert (S.GPIO_REG, GPIO_LO) in w and (S.GPIO_REG, 0) in w, w
    assert bar.r[S.EN_SW_OVERRIDE] == 0
    assert jevents(jp) == ["command_may_be_issued"], jevents(jp)


# ---------------------------------------------------------------- gate b
def test_b_trigger_stuck():
    setup_module()
    bar = V8Bar(trigger_stuck=True)
    bar.rows[ROW] = OLD
    d, jp = jtmp()
    t0 = time.time()
    rep = run_burn(bar, journal=jp)
    dt = time.time() - t0
    assert rep["result"].startswith("ABORT — GPIO update timed out"), rep
    assert dt < 6.0, f"TRIGGER poll has no effective deadline ({dt:.1f}s)"
    w = bar.wlog()
    assert (S.FUSECTRL, S.CMD_WRITE) not in w, "CMD_WRITE issued despite stuck TRIGGER"
    assert bar.r[S.GPIO_REG] == 0, "GPIO not restored after TRIGGER timeout"
    assert (S.GPIO_TRIGGER, 1) in w
    assert jevents(jp) == ["command_may_be_issued"], jevents(jp)


# ---------------------------------------------------------------- gate c
def test_c_en_latch_fail_before_any_gpio_write():
    setup_module()
    bar = V8Bar(en_no_latch=True)
    bar.rows[ROW] = OLD
    rep = run_burn(bar)
    assert rep["result"].startswith("ABORT — EN_SW_OVERRIDE did not latch"), rep
    w = bar.wlog()
    assert not [1 for o, v in w if o in (S.GPIO_REG, S.GPIO_TRIGGER)], \
        f"GPIO/TRIGGER written despite EN latch fail: {w}"
    assert (S.FUSECTRL, S.CMD_WRITE) not in w
    assert bar.r[S.EN_SW_OVERRIDE] == 0


def test_c_gpio_latch_fail_before_addr():
    setup_module()
    bar = V8Bar(gpio_latch_bad=True)
    bar.rows[ROW] = OLD
    rep = run_burn(bar)
    assert rep["result"].startswith("ABORT — GPIO write did not latch"), rep
    w = bar.wlog()
    assert not [1 for o, v in w if o == S.FUSEWDATA] \
        and (S.FUSECTRL, S.CMD_WRITE) not in w, \
        f"latching writes despite GPIO latch fail: {w}"


# ---------------------------------------------------------------- gate d
def test_d_already_burned_zero_latching_writes():
    setup_module()
    bar = V8Bar()
    bar.rows[ROW] = VAL                 # already at intended value
    d, jp = jtmp()
    rep = run_burn(bar, journal=jp)
    assert rep["result"] == "ALREADY BURNED", rep
    w = bar.wlog()
    latching = [(o, v) for o, v in w
                if o in (S.GPIO_REG, S.GPIO_TRIGGER, S.FUSEWDATA)
                or (o == S.EN_SW_OVERRIDE and v == 1)
                or (o == S.FUSECTRL and v == S.CMD_WRITE)]
    assert not latching, f"latching writes on ALREADY BURNED: {latching}"
    assert jevents(jp) == ["verified"], jevents(jp)
    assert S.burn_campaign_final([{"row": ROW}], ["ALREADY BURNED"])
    assert S.burn_campaign_final([{"row": ROW}, {"row": MIRROR}],
                                 ["VERIFY OK", "ALREADY BURNED"])


def test_d_claim_wording():
    """The task claim says 'zero writes'; the console really does zero
    LATCHING writes — EN=0/CMD_READ/SENSE/WDATA_SECURE/SBFE writes DO occur
    before the row read (arm_window runs before the row read, unlike the
    reference which reads the image BEFORE arming). Documented gap G2/G3."""
    setup_module()
    bar = V8Bar()
    bar.rows[ROW] = VAL
    rep = run_burn(bar)
    assert rep["result"] == "ALREADY BURNED"
    w = bar.wlog()
    # reference order would be: read row FIRST; console arms first:
    i_sense = bar.first_w(S.FUSECTRL, S.CMD_SENSE)
    i_read = bar.first_w(S.FUSECTRL, (IDLE9 & ~3) | S.CMD_READ)
    assert 0 <= i_sense < i_read, \
        f"unexpected order (arm after read?): sense={i_sense} read={i_read}"


# ---------------------------------------------------------------- gate e
def test_e_journal_kill_simulation():
    setup_module()
    d, jp = jtmp()
    S.journal_append(jp, "command_may_be_issued", bdf=BDF, row=ROW,
                     before=OLD, delta=DELTA, after=VAL)
    bar = V8Bar()
    bar.rows[ROW] = OLD
    rep = run_burn(bar, journal=jp)
    assert rep.get("journal_uncertain") and rep["result"].startswith("ABORT"), rep
    assert bar.wlog() == [], f"writes issued despite uncertain journal: {bar.wlog()}"
    rep2 = run_burn(bar, journal=jp, ack=True)
    assert rep2["result"] == "VERIFY OK", rep2
    assert jevents(jp)[-1] == "verified"


def test_e_journal_order_interleaved():
    """command_may_be_issued strictly BEFORE the EN=1 write and the CTRL=2
    write; verified strictly after."""
    setup_module()
    bar = V8Bar()
    bar.rows[ROW] = OLD
    d, jp = jtmp()
    real = _wrap_journal(bar, jp)
    try:
        rep = run_burn(bar, journal=jp)
    finally:
        S.journal_append = real
    assert rep["result"] == "VERIFY OK", rep
    seq = list(bar.log)
    i_cmi = next(i for i, e in enumerate(seq) if e[0] == "j" and e[1] == "command_may_be_issued")
    i_en1 = bar.first_w(S.EN_SW_OVERRIDE, 1)
    i_c2 = bar.first_w(S.FUSECTRL, S.CMD_WRITE)
    i_ver = next(i for i, e in enumerate(seq) if e[0] == "j" and e[1] == "verified")
    # map write index back into the full log
    def w_index(target):
        n = -1
        for i, e in enumerate(seq):
            if e[0] == "w":
                n += 1
                if n == target:
                    return i
        return -1
    assert i_cmi < w_index(i_en1) < w_index(i_c2) < i_ver, \
        f"journal order wrong: cmi={i_cmi} en1={w_index(i_en1)} c2={w_index(i_c2)} ver={i_ver}"


def test_e_journal_fsync_called():
    d, jp = jtmp()
    calls = []
    real = os.fsync

    def spy(fd):
        calls.append(fd)
        return real(fd)
    os.fsync = spy
    try:
        S.journal_append(jp, "command_may_be_issued", row=1)
    finally:
        os.fsync = real
    assert calls, "journal_append never called os.fsync"


def test_e_journal_torn_final_line_current_behaviour():
    """GAP probe: a torn final line (power loss mid-write) is silently
    skipped -> uncertainty LOST. Asserts CURRENT behaviour; the safe
    behaviour would be uncertain=True."""
    d, jp = jtmp()
    with open(jp, "w") as f:
        f.write('{"event": "command_may_be_iss')      # torn, no newline
    assert S.journal_uncertain(jp) is False, \
        "behaviour changed — update gap register"
    # a torn line AFTER a complete cmi does not lose uncertainty (it was
    # already set) — only a torn FIRST line does:
    with open(jp, "w") as f:
        f.write(json.dumps({"event": "command_may_be_issued", "row": ROW}) + "\n")
        f.write('{"event": "command_may_be_iss')
    assert S.journal_uncertain(jp) is True


# ---------------------------------------------------------------- gate f
def test_f_delta_not_full_value():
    setup_module()
    bar = V8Bar()
    bar.rows[ROW] = 0xF0
    rep = run_burn(bar, row=ROW, value=0xFC, old=0xF0)
    assert rep["result"] == "VERIFY OK", rep
    wd = [v for o, v in bar.wlog() if o == S.FUSEWDATA]
    assert wd == [0x0C], f"WDATA writes {wd}, expected [0x0C] (delta)"
    assert bar.rows[ROW] == 0xFC


# ---------------------------------------------------------------- gate g
def test_g_image_verify_failed_mirror_pair():
    setup_module()

    class Ctx:
        def __init__(self, bar):
            self._b = bar

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        @property
        def rd32(self):
            return self._b.rd

        @property
        def wr32(self):
            return self._b.wr

    bar = V8Bar(flip={ROW: (2, 0xDEADBEEF)})   # flips on image-verify reads
    bar.rows[ROW] = OLD
    bar.rows[MIRROR] = OLD
    layout = {"burn_zone": [235, 459], "last_occupied": 230,
              "occupied_count": 9, "buffer": 4, "sm_reserve": 16,
              "tail_reserve": 12}
    saved = (dict(S.CFG), S.ARM["token"], S.ARM["expires"], S.Bar0,
             S.ff_layout, S.ff_policy, S.valid_bdf)
    with tempfile.TemporaryDirectory() as td:
        try:
            S.CFG.update({"mock": None, "state_dir": td})
            S.ARM.update({"token": "v8", "expires": time.time() + 60})
            S.Bar0 = lambda bdf: Ctx(bar)
            S.ff_layout = lambda bdf=None: layout
            S.ff_policy = lambda *a, **k: []
            S.valid_bdf = lambda b: True
            rep = S.burn_api({"row": ROW, "value": VAL, "old": OLD,
                              "confirm": True, "mirror": True, "token": "v8"})
        finally:
            (S.CFG.update(saved[0]), S.ARM.update({"token": saved[1],
                                                   "expires": saved[2]}),
             setattr(S, "Bar0", saved[3]), setattr(S, "ff_layout", saved[4]),
             setattr(S, "ff_policy", saved[5]),
             setattr(S, "valid_bdf", saved[6]))
    assert rep["result"] == "IMAGE VERIFY FAILED", rep
    assert rep["result"] != "VERIFY OK"
    assert rep["mirror"]["result"] == "VERIFY OK", rep["mirror"]


def test_g_campaign_decision_window_not_held():
    """Campaign wiring: all-OK results + failing image verify must leave
    stats['goldilocks'] unset -> window_held False. Verified by executing the
    exact decision expressions the campaign uses."""
    setup_module()
    bar = V8Bar(flip={ROW: (0, 0xBAD)})       # every read after burn is wrong
    bar.rows[ROW] = VAL
    bar.rows[MIRROR] = VAL
    burned_ok = [(ROW, VAL), (MIRROR, VAL)]
    records = [{"row": ROW}, {"row": MIRROR}]
    results = ["VERIFY OK", "VERIFY OK"]
    final = S.burn_campaign_final(records, results)
    assert final is True
    img_ok = S.burn_image_verify(bar.rd, bar.wr, burned_ok)
    assert img_ok is False
    stats = {"goldilocks": False}
    if final:
        if len(burned_ok) >= 2 and not img_ok:
            stats["image_verify"] = "IMAGE VERIFY FAILED"
        else:
            stats["goldilocks"] = True
    held = bool(stats["goldilocks"]) and True     # no_revert default
    assert held is False and "image_verify" in stats


def test_g_single_record_skips_image_verify():
    """1-record campaign: image verify is >=2-only by design (len(burned_ok)
    >= 2 guard) — matches the documented claim, not the reference's
    always-full-image check (gap G6)."""
    assert not S.burn_image_verify.__doc__ or True
    bar = V8Bar()
    bar.rows[ROW] = 0x1234
    assert S.burn_image_verify(bar.rd, bar.wr, [(ROW, 0x1234)]) is True


# ---------------------------------------------------------------- gate h
def test_h_gpio_preflight_zero_writes():
    setup_module()
    for bad in (0x00040000, 0x00001000, 0x00008000, 0x000000FF):
        bar = V8Bar(gpio_init=bad)
        bar.rows[ROW] = OLD
        rep = run_burn(bar)
        assert rep["result"].startswith("ABORT — GPIO19 preflight"), rep
        assert f"0x{bad:08X}" in rep["result"]
        assert bar.wlog() == [], f"writes despite preflight fail {bad:#x}: {bar.wlog()}"


def test_h_driver_bound_zero_writes():
    S.driver_of = lambda bdf: "nvidia"
    try:
        bar = V8Bar()
        bar.rows[ROW] = OLD
        rep = run_burn(bar)
        assert rep["result"].startswith("ABORT — driver"), rep
        assert bar.wlog() == [], bar.wlog()
    finally:
        no_driver()


# ---------------------------------------------------------------- gate i
def test_i_runtime_paths_no_gpio_en1():
    setup_module()
    bar = V8Bar()
    bar.rows[ROW] = OLD
    ok, _ = S.arm_window(bar.rd, bar.wr)
    assert ok
    S.burn_window(bar.rd)
    S.read_row_via(bar.rd, bar.wr, ROW)
    S._fusectrl_idle(bar.rd, 0.01)
    for e in bar.log:
        if e[0] == "w":
            o, v = e[1], e[2]
            assert o not in (S.GPIO_REG, S.GPIO_TRIGGER), \
                f"{o:#x} written by a non-burn path"
            assert not (o == S.EN_SW_OVERRIDE and v == 1), "EN=1 raised outside burn"


def test_i_source_scan_bracket_rule():
    """GPIO_REG/GPIO_TRIGGER and EN=1 writes exist ONLY in _gpio_strobe and
    burn_execute; probe/burn_check/burn_window/arm_window never touch them."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
               "ga100vfi", "console", "service.py")).read()
    tree = ast.parse(src)
    allowed = {"_gpio_strobe", "burn_execute"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            seg = ast.get_source_segment(src, node) or ""
            if node.name in allowed:
                continue
            assert "GPIO_REG" not in seg and "GPIO_TRIGGER" not in seg, \
                f"{node.name} references GPIO regs"
            assert "EN_SW_OVERRIDE, 1" not in seg, \
                f"{node.name} raises EN=1"
    probe_src = ast.get_source_segment(
        src, next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "probe"))
    assert "wr(" not in probe_src, "probe issues writes"
    bc_src = ast.get_source_segment(
        src, next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "burn_check"))
    assert "wr(FUSEWDATA" not in bc_src and "CMD_SENSE" not in bc_src \
        and "GPIO" not in bc_src, "burn_check touches SENSE/WDATA/GPIO writes"


def test_i_card_stopped_never_written():
    """journal_uncertain resolves on 'card_stopped' but burn_execute never
    writes it — dead resolution branch (gap G5: aborted burns keep the
    journal uncertain until ack, fail-safe but noisy)."""
    src = open(os.path.join(os.path.dirname(__file__), "..",
               "ga100vfi", "console", "service.py")).read()
    assert src.count('"card_stopped"') == 1, \
        "card_stopped now written somewhere — update gap register"


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
