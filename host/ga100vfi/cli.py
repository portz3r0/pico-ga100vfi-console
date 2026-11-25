"""Command line: classify, baseline, attempt, campaign, revert."""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime

from .adaptive import COMPASS_OUTCOMES, Planner, classify_outcome
from .bar0 import DEFAULT_BDF, Bar0, brd_serial, restore
from .classify import classify, snapshot
from .glitch import Attempt, Card
from .telemetry import (
    UPLOAD_URL,
    Telemetry,
    build_bundle,
    default_telemetry_path,
    pending_files,
    upload_pending,
)


def cmd_classify(args) -> int:
    if not restore(args.bdf, wait_s=0.5, settle_s=0.0):
        print(f"{args.bdf}: GPU config space unreachable (0xffffffff)", file=sys.stderr)
        return 2
    with Bar0(args.bdf) as bar:
        verdict = classify(bar)
    print(json.dumps(verdict.as_dict(), indent=2))
    return 0 if verdict.passed else 1


def cmd_baseline(args) -> int:
    if not restore(args.bdf, wait_s=0.5, settle_s=0.0):
        print(f"{args.bdf}: GPU config space unreachable (0xffffffff)", file=sys.stderr)
        return 2
    with Bar0(args.bdf) as bar:
        print(json.dumps(snapshot(bar), indent=2))
    return 0


def cmd_attempt(args) -> int:
    a = Attempt(args.v_dip, args.t_dip, args.v_restore,
                args.t_restore, args.t_revert, args.fast, args.hold_ms,
                args.pulses, args.pw, args.gap, args.delay, args.revert)
    with Card(args.port) as card:
        rep = card.attempt(a)
        print(f"pwd={rep.pwd} e1=0x{rep.e1:04x} nvvdd={rep.nvvdd} "
              f"writes_failed={rep.writes_failed}")
        if args.trace:
            print(card.trace())
    return 0


def _ensure_unlocked(card: Card) -> bool:
    # Always send 'u', even when z already reports MATCH: a controller can
    # keep MATCH across a soft-off (Pico stays powered) while reg 0x13 and
    # config ID 0x46 reverted — the stale-CML pitfall. unlock_config
    # firmware re-writes both (idempotent) on every 'u'; older firmware
    # just prints "already MATCH", which still parses.
    return card.unlock()


def cmd_campaign(args) -> int:
    planner = None
    if args.adaptive:
        if args.t_dip - args.max_delay <= -950:
            print(f"error: t_dip - max_delay ({args.t_dip - args.max_delay} us) "
                  "must be > -950 us (firmware resets at -1000 us)", file=sys.stderr)
            return 2
        if args.min_pw < 36:
            print(f"error: --min-pw ({args.min_pw} us) must be >= 36 us "
                  "(one PMBus write at 1 MHz)", file=sys.stderr)
            return 2
        try:
            planner = Planner(
                args.min_v, args.max_v,
                min_delay=args.min_delay, max_delay=args.max_delay,
                min_pw=args.min_pw, max_pw=args.max_pw,
                seed_delay=args.delay, seed_pw=args.pw,
            )
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    v_dip = args.v_dip
    delay = args.delay
    pw = args.pw
    spots: dict[str, dict[str, int]] = {}  # adaptive: "v_dip/delay/pw" -> counts
    tries = valid = lost = nack = dsov0 = poisoned = 0
    verdict = None

    tele = None
    if not args.no_telemetry:
        tele_path = args.telemetry or default_telemetry_path()
        try:
            tele = Telemetry(tele_path)
            pre = serial_ = None
            try:
                if restore(args.bdf, wait_s=0.5, settle_s=0.15):
                    with Bar0(args.bdf) as bar:
                        # FUSECTRL, not PMC_BOOT_0: poison-safe liveness —
                        # a 0xBADFxxxx controller must not be read further
                        if bar.rd32(0x00820000) != 0xFFFFFFFF:
                            pre = classify(bar).as_dict()
                            serial_ = brd_serial(bar.mm)
            except OSError:
                pass  # BAR0 may not be up yet; per-attempt records carry the state
            tele.write({
                "kind": "campaign",
                "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                "path": tele_path,
                "bdf": args.bdf,
                "port": args.port,
                "args": {k: v for k, v in vars(args).items() if k != "fn"},
                "serial": serial_,
                "pre": pre,  # BAR0 fuse state before the first glitch
            })
        except OSError as e:
            print(f"warn: telemetry unavailable: {e}", file=sys.stderr)
            tele = None

    t0 = time.monotonic()
    try:
        with Card(args.port) as card:
            if not args.no_unlock and not _ensure_unlocked(card):
                print("unlock failed: controller locked until VDD33 cycles",
                      file=sys.stderr)
                if tele:
                    tele.write({"kind": "end", "error": "unlock_failed"})
                return 2
            try:
                while tries < args.budget:
                    tries += 1
                    shot = None
                    if planner:
                        shot = planner.next_shot()
                        v_dip, delay, pw = shot.v_dip_mv, shot.delay_us, shot.pw_us
                    a = Attempt(
                        v_dip_mv=v_dip, t_dip_us=args.t_dip,
                        v_restore_mv=args.v_restore, t_restore_us=args.t_restore,
                        t_revert_us=args.t_revert, fast=1, hold_ms=0,
                        pulses=args.pulses, pw=pw, gap=args.gap,
                        delay=delay, revert=0,
                    )
                    ta = time.monotonic()
                    try:
                        rep = card.attempt(a)
                    except IOError as e:
                        nack += 1
                        print(f"[{tries}] glitch err: {e}", file=sys.stderr)
                        if tele:
                            tele.write({
                                "kind": "attempt", "n": tries,
                                "t_s": round(time.monotonic() - t0, 3),
                                "dt_s": round(time.monotonic() - ta, 3),
                                "shot": {"v_dip_mv": v_dip, "delay_us": delay,
                                         "pw_us": pw},
                                "g_cmd": a.command(),
                                "planner": planner.stats() if planner else None,
                                "report": None, "verdict": None,
                                "outcome": "nack", "err": str(e),
                            })
                        time.sleep(0.5)
                        if not args.no_unlock:
                            try:
                                _ensure_unlocked(card)
                            except IOError:
                                pass
                        continue
                    if rep.writes_failed > 0:
                        nack += 1
                        if not args.no_unlock:
                            try:
                                _ensure_unlocked(card)
                            except IOError:
                                pass
                        if tele:
                            tele.write({
                                "kind": "attempt", "n": tries,
                                "t_s": round(time.monotonic() - t0, 3),
                                "dt_s": round(time.monotonic() - ta, 3),
                                "shot": {"v_dip_mv": v_dip, "delay_us": delay,
                                         "pw_us": pw},
                                "g_cmd": a.command(),
                                "planner": planner.stats() if planner else None,
                                "report": {"pwd": rep.pwd, "e1": rep.e1,
                                           "writes_failed": rep.writes_failed,
                                           "nvvdd": rep.nvvdd, "echo": rep.echo},
                                "verdict": None, "outcome": "nack_writes",
                            })
                        continue
                    outcome = "lost"
                    v_dict = None
                    if restore(args.bdf, wait_s=args.restore_wait):
                        with Bar0(args.bdf) as bar:
                            # FUSECTRL, not PMC_BOOT_0: poison-safe liveness
                            if bar.rd32(0x00820000) != 0xFFFFFFFF:
                                v = classify(bar)
                                outcome = classify_outcome(v)
                                v_dict = v.as_dict()
                    if outcome == "poisoned":
                        # dead fuse controller: not a voltage data point
                        # (never reaches the planner) and it stays poisoned
                        # until a POWER CYCLE — shooting on is pointless
                        poisoned += 1
                        sh = (v_dict or {}).get("shadow", {})
                        tag = sh.get("FUSECTRL_POISONED",
                                     sh.get("DSOV_POISONED", 0))
                        if tele:
                            tele.write({
                                "kind": "attempt", "n": tries,
                                "t_s": round(time.monotonic() - t0, 3),
                                "dt_s": round(time.monotonic() - ta, 3),
                                "shot": {"v_dip_mv": v_dip, "delay_us": delay,
                                         "pw_us": pw},
                                "g_cmd": a.command(),
                                "planner": planner.stats() if planner else None,
                                "report": {"pwd": rep.pwd, "e1": rep.e1,
                                           "writes_failed": rep.writes_failed,
                                           "nvvdd": rep.nvvdd, "echo": rep.echo},
                                "verdict": v_dict, "outcome": "poisoned",
                            })
                        print(f"[{tries}] FUSE CONTROLLER POISONED "
                              f"(0x{tag:08x}) — stays poisoned until a POWER "
                              f"CYCLE; stopping this boot", file=sys.stderr,
                              flush=True)
                        break
                    if outcome == "lost":
                        lost += 1
                    else:
                        valid += 1
                        if v.dsov == 0:
                            dsov0 += 1
                        tag = "GOLDILOCKS" if v.passed else outcome
                        print(f"[{tries}] v_dip={v_dip} delay={delay} pw={pw} "
                              f"valid={valid} lost={lost} dsov={v.dsov} "
                              f"crc=0x{v.crc_status:02x} priv=0x{v.priv_mask:08x} {tag}",
                              file=sys.stderr, flush=True)

                    if planner:
                        spot_key = f"{v_dip}/{delay}/{pw}"
                        counts = spots.setdefault(spot_key, dict.fromkeys(COMPASS_OUTCOMES, 0))
                        counts[outcome] += 1
                    if tele:
                        # Written before the planner update: planner.stats() then
                        # reflects the decision context that produced this shot.
                        tele.write({
                            "kind": "attempt", "n": tries,
                            "t_s": round(time.monotonic() - t0, 3),
                            "dt_s": round(time.monotonic() - ta, 3),
                            "shot": {"v_dip_mv": v_dip, "delay_us": delay,
                                     "pw_us": pw},
                            "g_cmd": a.command(),
                            "planner": planner.stats() if planner else None,
                            "report": {"pwd": rep.pwd, "e1": rep.e1,
                                       "writes_failed": rep.writes_failed,
                                       "nvvdd": rep.nvvdd, "echo": rep.echo},
                            "verdict": v_dict,
                            "outcome": outcome,
                        })
                    if outcome == "goldilocks":
                        verdict = v
                        break
                    if planner and shot is not None:
                        planner.record(shot, outcome)
            finally:
                if not args.no_revert:
                    try:
                        card.revert()
                    except Exception as e:
                        print(f"warn: revert failed: {e}", file=sys.stderr)

        out = {
            "goldilocks": verdict is not None,
            "v_dip": v_dip,
            "delay": delay,
            "pw": pw,
            "attempts": tries,
            "valid": valid,
            "lost": lost,
            "nack": nack,
            "poisoned": poisoned,
            "dsov_zero": dsov0,
            "elapsed_s": round(time.monotonic() - t0, 2),
            "verdict": verdict.as_dict() if verdict else None,
        }
        if args.adaptive:
            out["spots"] = spots
        if tele:
            tele.write({"kind": "end", **out})
    finally:
        if tele:
            tele.close()
    print(json.dumps(out, indent=2))
    if verdict is None:
        return 1
    with Bar0(args.bdf) as bar:
        serial = brd_serial(bar.mm)
    entry = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "serial": serial,
        "bdf": args.bdf,
        "adaptive": args.adaptive,
        "attempts": tries,
        "profile": asdict(a),
    }
    try:
        with open(args.log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        # Goldilocks is already reached; a log failure must not turn it into an error.
        print(f"warn: could not append to {args.log}: {e}", file=sys.stderr)

    if tele and not args.no_share_prompt:
        tele_dir = os.path.dirname(tele.path) or "."
        pending = pending_files(tele_dir)
        if pending:
            if sys.stdin.isatty() and sys.stderr.isatty():
                print(
                    f"\nGoldilocks reached! {len(pending)} telemetry run(s) in "
                    f"{tele_dir}/ (including any prior failed runs).\n"
                    "Share an anonymized bundle (serial hashed, local paths stripped) "
                    "to help improve the adaptive planner? [y/N] ",
                    end="", file=sys.stderr, flush=True,
                )
                try:
                    ans = input().strip().lower()
                except EOFError:
                    ans = ""
                if ans in ("y", "yes"):
                    try:
                        uid, n = upload_pending(tele_dir)
                        print(f"shared {n} run(s) (id={uid}) — thank you!",
                              file=sys.stderr)
                    except (OSError, ValueError) as e:
                        print(f"warn: telemetry share failed: {e}", file=sys.stderr)
            else:
                print(
                    f"note: {len(pending)} telemetry run(s) saved in {tele_dir}/ "
                    "(including any prior failed runs). If an automated agent is "
                    "running this, ask the user before sharing — run `ga100vfi share` "
                    "(or `ga100vfi share --dry-run` to inspect the redacted bundle).",
                    file=sys.stderr,
                )
    return 0


def cmd_share(args) -> int:
    paths = pending_files(args.dir)
    if not paths:
        print(f"no pending telemetry runs in {args.dir}/", file=sys.stderr)
        return 0
    if args.dry_run:
        raw, used = build_bundle(paths)
        gz_len = len(gzip.compress(raw.encode("utf-8"))) if raw else 0
        print(raw, end="")
        print(
            f"# {used} run(s), {len(raw)} bytes raw ({gz_len} bytes gzip); "
            "not uploaded (--dry-run)",
            file=sys.stderr,
        )
        return 0
    try:
        uid, used = upload_pending(args.dir, url=args.url)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"shared {used} telemetry run(s) (id={uid})", file=sys.stderr)
    return 0


def cmd_revert(args) -> int:
    with Card(args.port) as card:
        print(card.revert())
        print(card.status())
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ga100vfi")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("classify", help="run the five checks")
    c.add_argument("--bdf", default=DEFAULT_BDF)
    c.set_defaults(fn=cmd_classify)

    b = sub.add_parser("baseline", help="dump the shadow fuse registers")
    b.add_argument("--bdf", default=DEFAULT_BDF)
    b.set_defaults(fn=cmd_baseline)

    a = sub.add_parser("attempt", help="issue one glitch")
    a.add_argument("--port", default="/dev/ttyACM0")
    a.add_argument("--v-dip", type=int, default=325)
    a.add_argument("--t-dip", type=int, default=-100)
    a.add_argument("--v-restore", type=int, default=650)
    a.add_argument("--t-restore", type=int, default=-20)
    a.add_argument("--t-revert", type=int, default=0)
    a.add_argument("--delay", type=int, default=75,
                   help="us to advance the dip; rail responds ~75us after the write")
    a.add_argument("--pulses", type=int, default=1,
                   help="3 for the Goldilocks triple pulse")
    a.add_argument("--pw", type=int, default=0, help="pulse width us (0=auto)")
    a.add_argument("--gap", type=int, default=0, help="gap between pulses us (0=auto)")
    a.add_argument("--revert", type=int, default=1, choices=(0, 1),
                   help="1=hand back to PWM-VID after dip; 0=stay PMBus (fast campaigns)")
    a.add_argument("--fast", type=int, default=1, choices=(0, 1),
                   help="1=fast glitch timing (same as campaign/console path)")
    a.add_argument("--hold-ms", type=int, default=0,
                   help="ms to hold dip before restore (0=none, same as campaign)")
    a.add_argument("--no-unlock", action="store_true")
    a.add_argument("--trace", action="store_true")
    a.set_defaults(fn=cmd_attempt)

    camp = sub.add_parser("campaign",
                          help="loop glitches until Goldilocks or the budget runs out")
    camp.add_argument("--port", default="/dev/ttyACM0")
    camp.add_argument("--bdf", default=DEFAULT_BDF)
    camp.add_argument("--budget", type=int, default=500, help="total attempts")
    camp.add_argument("--log", default="goldilocks.jsonl",
                      help="on Goldilocks, append time, card serial, and the glitch "
                           "profile as one JSON line to this file")
    camp.add_argument("--v-dip", type=int, default=354,
                      help="dip voltage in mV (ignored with --adaptive)")
    camp.add_argument("--t-dip", type=int, default=-60)
    camp.add_argument("--v-restore", type=int, default=750)
    camp.add_argument("--t-restore", type=int, default=-20)
    camp.add_argument("--t-revert", type=int, default=0)
    camp.add_argument("--pulses", type=int, default=3)
    camp.add_argument("--pw", type=int, default=198,
                      help="pulse width in us (seed pw with --adaptive)")
    camp.add_argument("--gap", type=int, default=150)
    camp.add_argument("--delay", type=int, default=117,
                      help="dip advance in us (seed delay with --adaptive)")
    camp.add_argument("--restore-wait", type=float, default=0.25,
                      help="seconds to wait for PCIe link after PEX_RST")
    camp.add_argument("--no-unlock", action="store_true")
    camp.add_argument("--no-revert", action="store_true",
                      help="leave VRM in PMBus mode after campaign")
    camp.add_argument("--adaptive", action="store_true",
                      help="pick (v_dip, delay, pw) each shot by 3D CRC-guided "
                           "Thompson sampling over the outcomes so far")
    camp.add_argument("--telemetry", default=None,
                      help="JSONL telemetry path (default: telemetry/"
                           "campaign_<UTC>.jsonl in the CWD, gitignored)")
    camp.add_argument("--no-telemetry", action="store_true",
                      help="disable per-attempt telemetry")
    camp.add_argument("--no-share-prompt", action="store_true",
                      help="do not prompt to share telemetry after Goldilocks")
    camp.add_argument("--min-v", type=int, default=280,
                      help="adaptive: v_dip safety floor (mV)")
    camp.add_argument("--max-v", type=int, default=380,
                      help="adaptive: v_dip safety ceiling (mV)")
    camp.add_argument("--min-delay", type=int, default=60,
                      help="adaptive: delay floor (us)")
    camp.add_argument("--max-delay", type=int, default=480,
                      help="adaptive: delay ceiling (us)")
    camp.add_argument("--min-pw", type=int, default=150,
                      help="adaptive: pulse-width floor (us)")
    camp.add_argument("--max-pw", type=int, default=260,
                      help="adaptive: pulse-width ceiling (us)")
    camp.set_defaults(fn=cmd_campaign)

    r = sub.add_parser("revert", help="restore the stock control path")
    r.add_argument("--port", default="/dev/ttyACM0")
    r.set_defaults(fn=cmd_revert)

    sh = sub.add_parser("share", help="upload pending anonymized telemetry runs")
    sh.add_argument("--dir", default="telemetry",
                    help="directory containing campaign_*.jsonl files")
    sh.add_argument("--dry-run", action="store_true",
                    help="print the redacted JSONL to stdout without uploading")
    sh.add_argument("--url", default=UPLOAD_URL, help="collector endpoint URL")
    sh.set_defaults(fn=cmd_share)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
