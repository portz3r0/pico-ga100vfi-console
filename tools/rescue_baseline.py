#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exact baseline recovery for the reviewed friend CMP 170HX array.

Default: offline plan. --check: two physical-array reads, no OTP/arming.
--confirm: stage FF rows 306/307; add --retire-303 to retire 303 LAST.
--campaign: use the existing Pico host library to glitch, then the same review
and exact PROCEED prompt. Never automatically burns after a glitch hit.

Standalone except optional campaign, which needs ../host/ga100vfi. The embedded
baseline combines the reviewed dump(1).json prefix and dump(2).json tail. Only
this exact card image, plus completed recovery steps, is accepted. Keep ALL
ga100-rescue-*.jsonl journals in --journal-dir (default current directory).
Partial rows or unresolved previous program attempts are never retried.

IFF boundary discovery excludes the full all-ones invalidated row. Software
decoding supports this rescue; hardware boot recovery remains untested. This
does not repair the existing PMU FPF damage or perform the later full unlock.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import signal
import struct
import sys
import time
import uuid
import zlib

CTRL, ADDR, RDATA, WDATA = 0x820000, 0x820004, 0x820008, 0x82000c
EN, IFF, DEBUG, SWIFF = 0x820040, 0x820050, 0x820060, 0x820088
CRC, PROGRAM_EN, PROGRAM_DIS, DSOV = 0x820070, 0x820078, 0x82007c, 0x820084
WDATA_PLM, CTRL_PLM, OPT_PLM = 0x8200f4, 0x8200f8, 0x8200fc
SBFE, WDATA_SEC = 0x821108, 0x82048c
GPIO19, GPIO_TRIGGER = 0xd65c, 0xd604
TARGETS = ((306, 0xfc360201), (307, 0x429004c1), (303, 0xffffffff))
FINAL = dict(TARGETS)
BASELINE_SHA256 = '65fc28c38348df87775501f71f9b8703148ac6463e2e933df463c6833943de95'
BASELINE_B85 = 'c-rmNTSyd990u_3oHMgKqPsJzYf(f__7F)_BGyA$v!}oysf|dw5r$o$8yP+H(B?RpS`-B(SP*VOy(CmZ5<#>(MG^^NcM9AH2_(8$FKca{=2$%>gi`bpe#4J>nQsnfF8s^(uUc8=sc7z*D)p6YOG^yV2I<f;%anEzKthpFB-@t-X>+)yN*YkRG6PCi=3(n4NNGQYplX~YQCOM;mIH}R!jPN~wL-dizK%&4p6FE~Rmod<D%A1?(i999NKaBao}^}7Kzusj!w~z95Q%yr*3T4mvuey9?c{RuPA{ED7{OO9)~s)z-uvuk`r?F&2gUbWI`$lh-cwIK9t;dFY}--kuFap@+&HKDdg<<qt!J#y>jr0}qj$gdm$au7C%PwIThZBnR~&rvwBgFTTjeLtJ%3c)BZlSU!k!0){!qmTk=J@p0lyk;WLF4+@5k>$e)vtFj!R2P1zZ}rH++5k(ds|@`0Efdg!q}n7$MT=>mzL7A7x1xvzx+xG`7R;Y!9QM98C^2Zd0EI?#nRhw_fs`UQnG{Twf4&bklZqaB3JPHx|P&ZohGI3s!qOO}Mo10%eCcaklKWqu7dTG`^xCzrjP6=7eay8`9!5cVCU08$tn{lOZfEk}Tax6dewO<+8PVsWNQ?SCpWu7@%rLD_0L>9QAFVt9COd8*w+s?xq1P!2>0x6QHIW;0YSsIE4pU+zA#Z-C*=A&vk4!uj3>Qw{3F6lR@*L^L)#QkgY9sgltKY780Qfk`!8m>G1w`Eu#35QjT+?HcW`9RY<Du^*SF&(nr9v>LZTF&2s#1_8RcK%SBG!&KEpv!O3s4P4C6YZ<bI4V;Rf;m>ZP=9D5JUpK%0VQnf-cZNx+qj(M{qwy2Q6I*r(N@0?(WEiELX0GU{IA<?{U#soeIk@6<4SvLMC{H7frKC8X~cHJpm'
STATE_REGS = {
    'iff': IFF, 'dsov': DSOV, 'crc': CRC, 'program_en': PROGRAM_EN,
    'program_dis': PROGRAM_DIS, 'ctrl_plm': CTRL_PLM, 'opt_plm': OPT_PLM,
    'wdata_plm': WDATA_PLM, 'debug': DEBUG, 'swiff': SWIFF,
    'loader': 0x820028, 'ring': 0x120060,
    'gpc': 0x820350, 'fbp': 0x820364, 'fbpa': 0x820368,
    'gpc_defective': 0x8205c4, 'fbp_defective': 0x8205cc,
    'fbpa_defective': 0x8205d0,
}


class Refusal(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def digest(rows):
    return hashlib.sha256(struct.pack('<512I', *rows)).hexdigest()


def baseline():
    data = zlib.decompress(base64.b85decode(BASELINE_B85))
    require(len(data) == 2048 and hashlib.sha256(data).hexdigest() == BASELINE_SHA256,
            'Embedded baseline is corrupt')
    return list(struct.unpack('<512I', data))


def validate_image(rows):
    original = baseline()
    require(len(rows) == 512, 'Incomplete physical image')
    for i, value in enumerate(rows):
        require(type(value) is int and 0 <= value <= 0xffffffff, 'Invalid physical word')
        require(value == original[i] or i in FINAL and value == FINAL[i],
                f'Row {i} differs from baseline/completed recovery; no retry or repair attempted')
    require(rows[307] == original[307] or rows[306] == FINAL[306],
            'Row 307 completed without row 306; unexpected recovery order')
    require(rows[303] == original[303] or all(rows[i] == FINAL[i] for i in (306, 307)),
            'Row 303 retired before both FF replacements; refusing this state')


def phases(rows, retire):
    validate_image(rows)
    result = []
    for row, final in TARGETS[:3 if retire else 2]:
        if rows[row] == final:
            continue
        if row == 303:
            result.append(dict(row=row, phase='retire', before=rows[row],
                               delta=final & ~rows[row], after=final))
        else:
            staged = final & ~31
            result.extend((dict(row=row, phase='stage', before=0, delta=staged, after=staged),
                           dict(row=row, phase='activate', before=staged, delta=1, after=final)))
    return result


class Journal:
    def __init__(self, directory, bdf):
        directory = Path(directory)
        require(directory.is_dir(), 'Journal directory must already exist')
        self.prior = sorted(directory.glob('ga100-rescue-*.jsonl'))
        self.path = directory / f'ga100-rescue-{bdf}-{uuid.uuid4().hex[:12]}.jsonl'
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            uid = os.environ.get('SUDO_UID', '')
            if os.geteuid() == 0 and uid.isdecimal() and int(uid) > 0:
                os.fchown(fd, int(uid), -1)
            self.file = os.fdopen(fd, 'w')
        except BaseException:
            os.close(fd)
            raise
        self.event('session_started', bdf=bdf, baseline_sha256=BASELINE_SHA256,
                   writer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def event(self, kind, **data):
        self.file.write(json.dumps(dict(event=kind, utc=datetime.now(timezone.utc).isoformat(), **data)) + '\n')
        self.file.flush()
        os.fsync(self.file.fileno())

    def check_history(self, rows):
        for path in self.prior:
            pending = {}
            try:
                events = [json.loads(line) for line in path.read_text().splitlines()]
            except (ValueError, OSError) as error:
                raise Refusal(f'Cannot verify previous journal {path}: {error}') from error
            require(events and events[0].get('baseline_sha256') == BASELINE_SHA256,
                    f'Unexpected journal identity: {path}')
            for event in events:
                key = (event.get('row'), event.get('phase'))
                if event['event'] == 'program_intent':
                    pending[key] = event
                elif event['event'] == 'verified':
                    pending.pop(key, None)
            for (row, phase), event in pending.items():
                require(row in FINAL and rows[row] == FINAL[row],
                        f'Unresolved prior {phase} attempt at row {row} in {path}; no retry')
                self.event('history_resolved_by_completed_row', prior=str(path), row=row, phase=phase)

    def close(self):
        self.file.close()


class Access:
    def __init__(self, bdf):
        require(re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{2}:[01][0-9a-f]\.[0-7]', bdf),
                'Use an explicit complete PCI BDF')
        self.bdf, self.device = bdf, Path('/sys/bus/pci/devices') / bdf
        self.lock_fd = self.fd = self.mm = None
        try:
            self.lock_fd = os.open(f'/tmp/ga100-ff-{bdf}.lock',
                                   os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.check_identity()
        except BaseException:
            self.close()
            raise

    def check_identity(self):
        require(int((self.device / 'vendor').read_text(), 16) == 0x10de and
                int((self.device / 'device').read_text(), 16) == 0x20c2,
                'This rescue is restricted to the reviewed 10de:20c2 CMP card')
        require(not (self.device / 'driver').exists(), 'Card must already be unbound from its driver')

    def map(self):
        self.check_identity()
        config = (self.device / 'config').read_bytes()
        require(len(config) >= 64 and struct.unpack_from('<HH', config) == (0x10de, 0x20c2),
                'PCI configuration identity is unreadable/changed')
        require(struct.unpack_from('<H', config, 4)[0] & 2,
                'PCI memory decoding is disabled; restore PCI access separately')
        self.fd = os.open(self.device / 'resource0', os.O_RDWR | os.O_SYNC)
        require(os.fstat(self.fd).st_size >= 0x826000, 'BAR0 is too small')
        self.mm = mmap.mmap(self.fd, 0x826000, access=mmap.ACCESS_WRITE)
        require(read(self, 0) == 0x170000a1, 'PMC_BOOT_0 is not the reviewed GA100 revision')

    def boot_id(self):
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def read32(self, address):
        return struct.unpack_from('<I', self.mm, address)[0]

    def write32(self, address, value):
        struct.pack_into('<I', self.mm, address, value)

    def close(self):
        self.unmap()
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    def unmap(self):
        if self.mm is not None:
            self.mm.close()
            self.mm = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def read(bar, address):
    value = bar.read32(address)
    require(value >> 16 != 0xbadf and
            (value != 0xffffffff or address in (CTRL_PLM, OPT_PLM, WDATA_PLM)),
            f'Inaccessible register {address:#x}: {value:08x}')
    return value


def write_checked(bar, address, value, mask=0xffffffff):
    bar.write32(address, value)
    require(read(bar, address) & mask == value & mask, f'Write did not latch at {address:#x}')


def idle(bar):
    deadline = time.monotonic() + 0.5
    while True:
        value = read(bar, CTRL)
        if (value >> 16) & 31 == 4 and value & 3 == 0:
            return
        require(time.monotonic() < deadline, 'Fuse controller timeout; no retry')
        time.sleep(0.0001)


def command(bar, cmd):
    idle(bar)
    bar.write32(CTRL, cmd)
    read(bar, CTRL)  # Drain posted write before waiting for command sampling.
    time.sleep(0.001)
    idle(bar)


def canonical(bar):
    require(read(bar, DEBUG) == 0 and read(bar, SWIFF) == 0 and read(bar, 0x820028) == 0,
            'Noncanonical DEBUGCTRL/software-IFF/loader state')
    idle(bar)


@contextmanager
def physical(bar):
    canonical(bar)
    old_en, old_addr = read(bar, EN), read(bar, ADDR)
    require(old_en in (0, 1) and old_addr < 512, 'Invalid physical-read state')
    try:
        write_checked(bar, EN, 0)
        yield
    finally:
        if (read(bar, CTRL) >> 16) & 31 == 4:
            write_checked(bar, ADDR, old_addr)
            write_checked(bar, EN, old_en)


def raw_row(bar, row):
    require(read(bar, EN) == 0, 'Refusing redirected physical read')
    write_checked(bar, ADDR, row)
    command(bar, 1)
    return bar.read32(RDATA)  # All 32-bit values are legitimate physical data.


def capture(bar, journal, label, passes=2):
    stage, images = 'identity', []
    try:
        bar.check_identity()
        require(read(bar, 0) == 0x170000a1, 'GA100 identity changed')
        boot_id = bar.boot_id()
        require(read(bar, CTRL_PLM) == 0xffffffff, 'Fuse-controller host access must be open')
        with physical(bar):
            before = {name: read(bar, addr) for name, addr in STATE_REGS.items()}
            for index in range(passes):
                images.append([])
                for row in range(512):
                    stage = f'pass{index + 1}.row{row}'
                    images[-1].append(raw_row(bar, row))
                journal.event('capture_rows', label=label, pass_number=index + 1,
                              rows=images[-1], sha256=digest(images[-1]))
            stage = 'consistency'
            after = {name: read(bar, addr) for name, addr in STATE_REGS.items()}
        require(before == after and all(image == images[0] for image in images),
                'Physical captures/options disagree')
        require(bar.boot_id() == boot_id, 'Host boot changed during capture')
        journal.event('capture_complete', label=label, registers=before, boot_id=boot_id)
        return dict(rows=images[0], registers=before, boot_id=boot_id)
    except BaseException as error:
        journal.event('capture_failed', label=label, stage=stage,
                      partial_passes=images, error=str(error) or type(error).__name__)
        raise


def validate_capture(snapshot):
    rows, regs = snapshot['rows'], snapshot['registers']
    validate_image(rows)
    allowed_iff = (0x1fb012f, 0x1fb01e8) if rows[303] == 0xffffffff else (0x1fb012f,)
    require(regs['iff'] in allowed_iff, 'Unexpected live IFF bounds')
    require(regs['crc'] == 0x55, 'Fuse CRC must be 0x55')
    require((regs['gpc_defective'], regs['fbp_defective'], regs['fbpa_defective']) ==
            (2, 0x840, 0xc03000), 'Live physical defects disagree with reviewed card')
    expected = (0x86, 0x852, 0xc0330c) if regs['iff'] == 0x1fb01e8 else (0, 0, 0x330c)
    require((regs['gpc'], regs['fbp'], regs['fbpa']) == expected,
            'Live option shadows do not match the reviewed/recovered state')


def window(bar):
    canonical(bar)
    require(read(bar, DSOV) == 0 and read(bar, CRC) == 0x55, 'DSOV/CRC window is invalid')
    require(read(bar, CTRL_PLM) == read(bar, OPT_PLM) == 0xffffffff,
            'Controller/option PLMs must already be open')
    require(read(bar, 0x120060) == 0, 'PRI ring is held in reset')
    require(read(bar, PROGRAM_DIS) == 0, 'Fuse programming is disabled')


def arm(bar):
    window(bar)
    if read(bar, PROGRAM_EN) != 1:
        command(bar, 3)
        window(bar)
    require(read(bar, PROGRAM_EN) == 1, 'Programming did not enable')
    write_checked(bar, EN, 1)
    write_checked(bar, SBFE, 0)
    write_checked(bar, WDATA_SEC, 0)
    require(read(bar, WDATA_PLM) == 0xffffffff, 'Programming-data PLM did not open')


def gpio(bar, saved, high):
    value = (saved & ~0x30ff) | 0x2000 | (0x1000 if high else 0)
    write_checked(bar, GPIO19, value, 0x30ff)
    bar.write32(GPIO_TRIGGER, 1)
    deadline = time.monotonic() + 0.5
    while read(bar, GPIO_TRIGGER) & 1:
        require(time.monotonic() < deadline, 'GPIO update timed out')
        time.sleep(0.0001)


def execute(bar, snapshot, plan, journal):
    expected = snapshot['rows'].copy()
    require(plan in (phases(expected, False), phases(expected, True)), 'Plan differs from exact allowlist')
    fresh = capture(bar, journal, 'pre_program')
    require(fresh == snapshot, 'Card changed after confirmation; abort and review a fresh plan')
    validate_capture(fresh)
    journal.check_history(expected)
    window(bar)
    saved_gpio, saved_en, saved_addr = read(bar, GPIO19), read(bar, EN), read(bar, ADDR)
    require(saved_gpio & 0xff == 0 and not saved_gpio & (0x1000 | 0x8000 | 0x40000),
            'GPIO19 must have normal mux, non-inverted push-pull and low output latch')
    journal.event('authorized', plan=plan, baseline_sha256=BASELINE_SHA256,
                  source_sha256=digest(expected), rows=expected)
    touched = False
    try:
        for record in plan:
            bar.check_identity()
            require(bar.boot_id() == snapshot['boot_id'], 'Host boot changed')
            require(capture(bar, journal, 'phase_precheck', passes=1)['rows'] == expected,
                    'Physical array changed before phase')
            arm(bar)
            row, wanted, delta = record['row'], record['after'], record['delta']
            require(row in FINAL and expected[row] == record['before'] and delta != 0 and
                    delta == wanted & ~expected[row] and (expected[row] | delta) == wanted,
                    'Invalid programming delta')
            journal.event('program_intent', **record)
            journal.event('command_may_be_issued', row=row, phase=record['phase'])
            touched = True
            try:
                gpio(bar, saved_gpio, True)
                write_checked(bar, ADDR, row)
                bar.write32(WDATA, delta)
                # Check address AGAIN after WDATA, immediately before command.
                require(read(bar, ADDR) == row and read(bar, DEBUG) == 0 and read(bar, EN) == 1,
                        'Address/programming mode changed before CMD_WRITE')
                command(bar, 2)
            finally:
                gpio(bar, saved_gpio, False)
            with physical(bar):
                actual = raw_row(bar, row)
            require(actual == wanted, f'Row {row} {record["phase"]} readback mismatch; no retry')
            expected[row] = wanted
            journal.event('verified', row=row, phase=record['phase'], word=actual)
            print(f'Verified row {row} {record["phase"]}: {actual:08x}', flush=True)
        final = capture(bar, journal, 'final')
        require(final['rows'] == expected, 'Final full-array verification failed')
        validate_image(expected)
        journal.event('complete', rows=expected, sha256=digest(expected))
    finally:
        if touched:
            gpio(bar, saved_gpio, False)
            write_checked(bar, GPIO19, saved_gpio, 0x30ff)
            bar.write32(GPIO_TRIGGER, 1)
        if (read(bar, CTRL) >> 16) & 31 == 4:
            write_checked(bar, ADDR, saved_addr)
            write_checked(bar, EN, saved_en)


def show_plan(rows, retire):
    plan = phases(rows, retire)
    print(f'Exact baseline SHA256: {BASELINE_SHA256}')
    for row, final in TARGETS[:3 if retire else 2]:
        print(f'  row {row}: {rows[row]:08x} -> {final:08x}' +
              (' (already complete; skip)' if rows[row] == final else ''))
    for record in plan:
        print(f'    {record["phase"]}: row {record["row"]}, delta {record["delta"]:08x}')
    print(f'Programming commands: {len(plan)}. No automatic retries.')
    if retire:
        print('303 retires LAST. After cold boot expect IFF=01fb01e8, GPC=86, FBP=852, FBPA=c0330c.')
    else:
        print('Staging only: row 303 is preserved; this does not recover boot yet.')
    print('Boot recovery is untested; the existing PMU version-fuse damage remains.')
    return plan


def interact(bar, snapshot, retire, journal, reader=None):
    validate_capture(snapshot)
    journal.check_history(snapshot['rows'])
    plan = show_plan(snapshot['rows'], retire)
    journal.event('preview', plan=plan)
    if not plan:
        print('Selected recovery steps are already complete. No programming.')
        return False
    window(bar)
    if reader is None:
        reader = input
    if reader('Type exactly PROCEED to program this plan; anything else aborts: ') != 'PROCEED':
        journal.event('aborted', reason='confirmation')
        print('Aborted; no OTP commands issued.')
        return False
    execute(bar, snapshot, plan, journal)
    print('OTP readback verified. Cold-boot functional validation is still required.')
    return True


def campaign(args, bar, journal):
    # Only optional Pico orchestration uses the separately installed host package.
    host = Path(args.host_dir).resolve()
    require((host / 'ga100vfi/glitch.py').is_file(), 'Set --host-dir to the Pico host directory')
    sys.path.insert(0, str(host))
    from ga100vfi.glitch import Card, Attempt
    from ga100vfi.bar0 import Bar0, restore
    from ga100vfi.classify import classify
    require(1 <= args.max_attempts <= 6, '--max-attempts must be 1..6 per cold boot')
    card, lost = Card(args.port), 0
    try:
        card.cmd('@q', 0.3)
        card.cmd('@F 1000000', 0.3)
        journal.event('campaign_started', host_dir=str(host), parameters={
            key: getattr(args, key) for key in ('v_dip', 'pulses', 'pw', 'gap', 'delay', 'max_attempts')})
        for n in range(1, args.max_attempts + 1):
            bar.check_identity()
            # Preserve the supplied controller's PMBus unlock sequence; no OTP operations.
            if not card.read(0x25, 0x7e, 1)[0] & 8:
                for reg, val in ((0xf2, b'\x25\x7c'), (0x13, b'\x00'), (0x46, b'\x29\x12')):
                    card.write(0x25, reg, val)
            rep = card.attempt(Attempt(v_dip_mv=args.v_dip, t_dip_us=-60,
                v_restore_mv=750, t_restore_us=-20, t_revert_us=0, fast=1,
                hold_ms=0, pulses=args.pulses, pw=args.pw, gap=args.gap,
                delay=args.delay, revert=0))
            journal.event('campaign_attempt', attempt=n, raw=rep.raw)
            require(rep.writes_failed == 0, 'Glitch PMBus write failed; stop and inspect')
            if not restore(args.bdf, wait_s=args.restore_wait):
                lost += 1
                require(lost < 2, 'Two link losses; cold boot before any further campaign')
                continue
            with Bar0(args.bdf) as tmp:
                verdict = classify(tmp)
            journal.event('campaign_verdict', attempt=n, verdict=verdict.as_dict())
            print(f'[{n}] DSOV={verdict.dsov} CRC={verdict.crc_status:#x} passed={verdict.passed}', flush=True)
            if verdict.passed:
                print('Window found. Capturing card before the final review/PROCEED prompt.')
                return
        raise Refusal('No valid window within budget; no fuse programming attempted')
    finally:
        card.close()  # No automatic VRM revert/reset; no OTP action in this function.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bdf', default='0000:41:00.0')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--confirm', action='store_true')
    mode.add_argument('--campaign', action='store_true')
    parser.add_argument('--retire-303', action='store_true')
    parser.add_argument('--journal-dir', default='.')
    parser.add_argument('--host-dir', default=str(Path(__file__).resolve().parent.parent / 'host'))
    parser.add_argument('--port', default='/dev/ttyACM0')
    parser.add_argument('--max-attempts', type=int, default=6)
    parser.add_argument('--v-dip', type=int, default=353)
    parser.add_argument('--pulses', type=int, default=3)
    parser.add_argument('--pw', type=int, default=198)
    parser.add_argument('--gap', type=int, default=300)
    parser.add_argument('--delay', type=int, default=117)
    parser.add_argument('--restore-wait', type=float, default=2.0)
    args = parser.parse_args(argv)
    if not (args.check or args.confirm or args.campaign):
        show_plan(baseline(), args.retire_303)
        return 0
    journal = bar = None
    stage = 'journal_open'
    try:
        journal = Journal(args.journal_dir, args.bdf)
        print(f'Journal: {journal.path.resolve()}', flush=True)
        stage = 'bar_open'
        bar = Access(args.bdf)
        if args.campaign:
            stage = 'pre_campaign_capture'
            bar.map()
            pre_campaign = capture(bar, journal, 'pre_campaign')
            validate_capture(pre_campaign)
            journal.check_history(pre_campaign['rows'])
            if not phases(pre_campaign['rows'], args.retire_303):
                show_plan(pre_campaign['rows'], args.retire_303)
                print('Selected recovery steps are already complete. No glitch or programming.')
                journal.event('session_finished')
                return 0
            bar.unmap()  # Keep the exclusive lock across the glitch/reset.
            stage = 'campaign'
            campaign(args, bar, journal)
        bar.map()
        stage = 'capture'
        snapshot = capture(bar, journal, 'initial')
        validate_capture(snapshot)
        journal.check_history(snapshot['rows'])
        if args.check:
            show_plan(snapshot['rows'], args.retire_303)
            print('Physical capture matches reviewed baseline/completed steps. No OTP or arming commands.')
        else:
            stage = 'interactive_program'
            interact(bar, snapshot, args.retire_303, journal)
        journal.event('session_finished')
        return 0
    except BaseException as error:
        if journal is not None:
            journal.event('session_stopped', stage=stage, error=str(error) or type(error).__name__,
                          instruction='No automatic retry. Preserve journal and inspect the physical image.')
        if isinstance(error, (Refusal, OSError, ValueError, KeyboardInterrupt, EOFError)):
            print(f'Stopped: {str(error) or type(error).__name__}', file=sys.stderr)
            return 130 if isinstance(error, (KeyboardInterrupt, EOFError)) else 1
        raise
    finally:
        try:
            if bar is not None:
                bar.close()
        finally:
            if journal is not None:
                journal.close()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    sys.exit(main())
