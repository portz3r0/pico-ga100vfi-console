"""HTML GUI generator for the GA100 fuse console.

Two modes:
  static — dump data embedded inline, works anywhere (no service needed)
  live   — seed data embedded for instant paint, then fetches /api/live
           (fast pure-read probe, auto-refresh) and /api/full (all rows,
           on demand) from ga100vfi.console.service

FF-record decode uses the verified field map:
  chain = bits[4:0], iff = bit 5, block = bits[15:6], data = bits[31:16]

CLI: python3 -m ga100vfi.console.gui <dump_dir_or_json> [out.html] [--live]
"""
import json
import os
import re
import sys

from ..advanced_unlocks import ADVANCED_UNLOCKS

STUB = {
    "live": True, "bdf": "?", "started": "?", "vendor": "0x10de", "device": "0x20c2",
    "revision": "?", "driver": "?", "fingerprint": "—", "row_count": 0,
    "nonblank_rows": {}, "status": {}, "shadow": {}, "rows": {},
    "interpretation": [], "dmesg_tail": "", "nvidia_smi": "", "hexnonzero": [],
    "ceilings": {}, "serial": None, "serial_source": "unavailable",
}


def load_dump(dump_path):
    """Load a fusedump dump.json (+ hex window from the same dir)."""
    p = os.path.abspath(dump_path)
    if os.path.isdir(p):
        cand = os.path.join(p, "dump.json")
        if not os.path.exists(cand):
            sys.exit(f"no dump.json in {p}")
        p = cand
    with open(p) as f:
        d = json.load(f)
    d.pop("hexnonzero", None)
    hexnon = []
    hw = os.path.join(os.path.dirname(p), "hex_window_0x820000.txt")
    if os.path.exists(hw):
        for ln in open(hw):
            m = re.match(r"0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)", ln)
            if m and int(m.group(2), 16):
                hexnon.append([int(m.group(1), 16), int(m.group(2), 16)])
    d["hexnonzero"] = hexnon
    # Backfill per-GPC TPC shadow keys from the hex window for dumps made
    # before the TPC keys existed. DEFECTIVE = FF-region words
    # (fd.TPC_DEFECT_FF, correct even for floorswept GPCs);
    # FFDISABLE = 0x820760 (SKU mask); DISABLE = 0x820C38 (runtime mask).
    # The window stores only non-zero words, so a covered-but-absent offset
    # means zero — treat the arrays as fully present once the window
    # reaches the last GPC word. Old dumps whose TPC_DEFECTIVE_GPC keys
    # were captured from 0x820760 are REPAIRED here from the FF words.
    sh = d.get("shadow")
    if isinstance(sh, dict) and hexnon:
        by_off = {off: val for off, val in hexnon}
        covered = max(o for o, _ in hexnon) >= 0x820C54
        try:
            from .. import fusedump as _fd
            ff = _fd.TPC_DEFECT_FF
            for g in range(8):
                sh[f"TPC_DEFECTIVE_GPC{g}"] = by_off.get(ff[g], 0 if covered else None)
                sh.setdefault(f"TPC_FFDISABLE_GPC{g}",
                              by_off.get(0x820760 + 4 * g, 0 if covered else None))
                sh.setdefault(f"TPC_DISABLE_GPC{g}",
                              by_off.get(0x820C38 + 4 * g, 0 if covered else None))
        except Exception:
            pass
        if "tpc" not in d:
            try:
                d["tpc"] = _fd.tpc_summary(sh, hexnon)
            except Exception:
                pass
    return d


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>GA100 Fuse Console — pico-ga100vfi</title>
<style>
  :root {
    --bg: #0d1117; --bg-deep: #090c10;
    --card: #151a21; --card-hi: #1a2029;
    --border: #27303b; --border-soft: #1e252d;
    --foreground: #e6edf3; --muted-foreground: #919ba6; --fg-subtle: #66707b;
    --accent: #4cc2ff;
    --ok: #3fb950; --bad: #f85149; --warn: #d29922;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--foreground);
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto,
                      "Helvetica Neue", Arial, sans-serif;
         font-size: 13.5px; line-height: 1.5; -webkit-font-smoothing: antialiased; }
  @media (min-width: 1200px) { .app { margin: 0 auto; } }
  .app { max-width: min(1780px, 100%); padding: 20px 22px 48px; }
  .mono { font-family: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas,
          "Liberation Mono", monospace; font-size: 12px; }

  /* Frozen header: the topbar stays selectable at every scroll position.
     ONE sticky element so no magic pixel offsets are needed when the topbar
     wraps taller on narrow screens. --sticktop (default 0px) is maintained
     by a ResizeObserver in the boot section so the sticky side rails (tabs,
     siderail) park below it, never over it.
     No overflow here: it must not clip the :focus-visible ring. */
  .sticktop { position: sticky; top: 0; z-index: 30; background: var(--bg); }

  /* Three-column cockpit: vertical tab rail left, panes center, status rail
     right. align-items:flex-start so each rail's sticky offset is measured
     against the row, not a stretched full-height column. */
  .layout { display: flex; align-items: flex-start; gap: 18px; }
  .content { flex: 1 1 auto; min-width: 0; width: 100%; } /* min-width:0: wide
     tables/pre blocks must not blow out the flex row */
  /* Right status rail: the livebar card lives here and stays put while the
     center column scrolls. :empty covers static (non-live) builds, where
     the placeholder substitutes nothing. */
  .siderail { flex: 0 0 360px; width: 360px; position: sticky;
              top: calc(var(--sticktop, 0px) + 8px); align-self: flex-start;
              max-height: calc(100vh - var(--sticktop, 0px) - 16px);
              overflow-y: auto; z-index: 15; }
  .siderail:empty { display: none; }
  @media (max-width: 1200px) { /* mid-width: shrink the rail so the center
     column isn't squeezed */
    .siderail { flex-basis: 300px; width: 300px; } }

  /* top bar */
  .topbar { display: flex; justify-content: space-between; align-items: flex-end;
            gap: 16px; padding-bottom: 14px; margin-bottom: 16px;
            border-bottom: 1px solid var(--border); }
  h1 { font-size: 19px; font-weight: 700; margin: 0 0 3px; letter-spacing: -0.01em; }
  .sub { color: var(--muted-foreground); font-size: 12px; }
  .topbadge { color: var(--muted-foreground); font-size: 11.5px; border: 1px solid var(--border);
              border-radius: 99px; padding: 4px 12px; display: inline-flex; gap: 7px;
              align-items: center; white-space: nowrap; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ok); }

  h2 { font-size: 11px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
       color: var(--fg-subtle); margin: 30px 0 10px; display: flex; align-items: center; gap: 9px; }
  h2::before { content: ""; width: 3px; height: 13px; border-radius: 2px; background: var(--accent); }

  .card { background: var(--card); border: 1px solid var(--border-soft);
          border-radius: 10px; padding: 12px 14px; }
  .grid { display: flex; flex-wrap: wrap; gap: 10px; }
  .stat { min-width: 138px; flex: 1 1 138px; transition: border-color .15s; }
  .stat:hover { border-color: var(--border); }
  .stat .k { font-size: 10.5px; color: var(--fg-subtle); text-transform: uppercase;
             letter-spacing: .07em; }
  .stat .v { font-size: 15px; font-weight: 600; margin: 3px 0 1px; }
  .ok   { color: var(--ok); }
  .bad  { color: var(--bad); }
  .warn { color: var(--warn); }

  .verdict { border-left: 3px solid var(--bad);
             background: linear-gradient(90deg, rgba(248,81,73,.09), rgba(248,81,73,0) 55%); }
  .verdict.good { border-left-color: var(--ok);
             background: linear-gradient(90deg, rgba(63,185,80,.09), rgba(63,185,80,0) 55%); }
  .verdict.warnv { border-left-color: var(--warn);
             background: linear-gradient(90deg, rgba(210,153,34,.09), rgba(210,153,34,0) 55%); }

  /* Saved-dump view of an absent/different card: dim the dump-derived
     panels and mark the wrapper with an amber rule so stale-vs-live is
     obvious at a glance (the #dumpsrc strip names the source). */
  #dumpwrap.stale { opacity: .75; border-left: 3px solid var(--warn);
             padding-left: 12px; }

  /* Saved-dumps history picker: one row per dump, click to browse.
     scroll-margin-top keeps the picker heading below the frozen topbar
     when openPicker() scrolls it into view (--sticktop is the topbar
     height, published by the ResizeObserver in the boot section). */
  #dumppicker { scroll-margin-top: calc(var(--sticktop, 0px) + 8px); }
  #dumplist .dumptrow { padding: 7px 12px; border-bottom: 1px solid var(--border-soft);
             cursor: pointer; }
  #dumplist .dumptrow:hover { background: var(--card-hi); }
  #dumplist .dumptrow.unreadable { cursor: default; color: var(--fg-subtle); }

  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 5px 10px; border-bottom: 1px solid var(--border-soft); }
  th { font-size: 10px; color: var(--fg-subtle); text-transform: uppercase; letter-spacing: .08em;
       position: sticky; top: 0; background: #10151d; z-index: 1; }
  .scroll { max-height: 430px; overflow: auto; border: 1px solid var(--border-soft);
            border-radius: 10px; background: var(--card); }
  .scroll::-webkit-scrollbar { width: 10px; height: 10px; }
  .scroll::-webkit-scrollbar-thumb { background: #2b3540; border-radius: 7px;
                                     border: 2px solid var(--card); }
  .scroll::-webkit-scrollbar-track { background: transparent; }
  tr.rowline { cursor: pointer; transition: background .1s; }
  tr.rowline:hover { background: rgba(76,194,255,.07); }
  tr.sel { background: rgba(76,194,255,.14); }
  td.reg-MAIN { color: #58a6ff; } td.reg-UNIQ { color: #bc8cff; }
  td.reg-FPF  { color: #e3b341; } td.reg-FF  { color: #39c5cf; }
  .tag { font-size: 9.5px; padding: 1px 7px; border-radius: 5px; font-weight: 600;
         border: 1px solid var(--border); color: var(--muted-foreground); letter-spacing: .03em; }
  .b-tag { background: rgba(248,81,73,.16); color: #ff8b85; border-color: rgba(248,81,73,.4); }
  .blankrow td { color: var(--fg-subtle); opacity: .4; }

  .btn { background: var(--card-hi); border: 1px solid var(--border); color: var(--foreground);
         border-radius: 7px; padding: 5px 12px; cursor: pointer; font-size: 12px; font-weight: 500;
         transition: border-color .15s, background .15s; }
  .btn:hover { border-color: #3a4551; background: #202834; }
  .btn:disabled { opacity: .45; cursor: wait; }
  .btn.on { border-color: var(--accent); color: var(--accent);
            background: rgba(76,194,255,.1); }
  input[type=text] { background: var(--bg-deep); border: 1px solid var(--border);
                     color: var(--foreground); border-radius: 7px; padding: 5px 10px;
                     font-size: 12px; width: 200px; transition: border-color .15s, box-shadow .15s; }
  /* number inputs: hide the UA spinner — in Firefox/WebKit it renders as a
     solid white square against the dark theme (looked like a broken glyph) */
  input[type=number] { -moz-appearance: textfield; appearance: textfield; }
  input[type=number]::-webkit-outer-spin-button,
  input[type=number]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
  input[type=text]:focus { border-color: var(--accent); outline: none;
                           box-shadow: 0 0 0 3px rgba(76,194,255,.12); }
  select { background: var(--card-hi); border: 1px solid var(--border); color: var(--foreground);
           border-radius: 7px; padding: 4px 8px; font-size: 12px; }

  .legend { display: flex; gap: 16px; flex-wrap: wrap; margin: 0 0 8px; font-size: 11.5px;
            color: var(--muted-foreground); }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .sw { width: 12px; height: 12px; border-radius: 4px; border: 1px solid var(--border);
        display: inline-block; }
  .sw.on    { background: rgba(63,185,80,.25); border-color: rgba(63,185,80,.5); }
  .sw.off   { background: rgba(210,153,34,.22); border-color: rgba(210,153,34,.5); }
  .sw.dead  { background: rgba(139,90,90,.3); border-color: rgba(139,90,90,.5); }
  .sw.deadon { background: repeating-linear-gradient(45deg, rgba(248,81,73,.5) 0 3px, rgba(248,81,73,.12) 3px 6px);
               border-color: var(--bad); }

  .unit { display: inline-flex; align-items: center; justify-content: center;
          min-width: 58px; height: 46px; margin: 3px; border-radius: 8px;
          border: 1px solid var(--border); font-size: 10.5px; text-align: center;
          flex-direction: column; background: var(--bg-deep); }
  .unit b { font-size: 12.5px; }
  .unit span { opacity: .85; font-size: 9.5px; }
  .u-on  { background: rgba(63,185,80,.13); color: var(--ok); border-color: rgba(63,185,80,.4); }
  .off   { background: rgba(210,153,34,.12); color: var(--warn); border-color: rgba(210,153,34,.4); }
  .dead  { background: rgba(248,81,73,.07); color: #b0706b; border-color: rgba(248,81,73,.22); }
  .deadon{ background: repeating-linear-gradient(45deg, rgba(248,81,73,.3) 0 7px, rgba(248,81,73,.08) 7px 14px);
           color: var(--bad); border-color: var(--bad); font-weight: 700; }

  /* TPC map — per-GPC rows of 8 TPC cells (2 SM per TPC) */
  .tpcrow { display: flex; align-items: center; gap: 10px; padding: 4px 0;
            border-bottom: 1px solid var(--border-soft); flex-wrap: wrap; }
  .tpcrow:last-child { border-bottom: none; }
  .tpcglab { width: 92px; flex: none; font-weight: 600; font-size: 12px; }
  .tpcglab .gstate { display: block; font-weight: 400; font-size: 10px;
                     color: var(--muted-foreground); }
  .tpccells { display: flex; gap: 4px; flex: none; }
  .tpccell { width: 46px; height: 34px; border-radius: 6px; border: 1px solid var(--border);
             display: inline-flex; flex-direction: column; align-items: center;
             justify-content: center; font-size: 9px; background: var(--bg-deep);
             font-family: ui-monospace, Menlo, Consolas, monospace; }
  .tpccell b { font-size: 10.5px; }
  .tpccell.on   { background: rgba(63,185,80,.13); color: var(--ok);
                  border-color: rgba(63,185,80,.4); }
  .tpccell.recov { background: rgba(210,153,34,.12); color: var(--warn);
                   border-color: rgba(210,153,34,.45); }
  .tpccell.dead { background: rgba(248,81,73,.07); color: #b0706b;
                  border-color: rgba(248,81,73,.25); }
  .tpccell.goff { opacity: .45; }
  .unit, .tpccell, .tpcglab { cursor: pointer; }
  .unit:hover, .tpccell:hover, .tpcglab:hover { outline: 1px solid var(--accent); }

  /* unit audit modal */
  #auditbg { display: none; position: fixed; inset: 0; z-index: 50;
             background: rgba(4,8,14,.72); overflow: auto; padding: 36px 16px; }
  #auditbg.open { display: block; }
  #dpbg { display: none; position: fixed; inset: 0; z-index: 50;
          background: rgba(4,8,14,.72); overflow: auto; padding: 36px 16px; }
  #dpbg.open { display: block; }
  #dpbg #dumppicker { max-width: 920px; margin: 0 auto; }
  #audit { max-width: 920px; margin: 0 auto; background: var(--card);
           border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }
  #audit h3 { margin: 0 0 2px; font-size: 15px; }
  #audit .verdictline { font-size: 12.5px; margin: 6px 0 12px; }
  #audit table { margin-top: 4px; }
  #audit td { vertical-align: top; }
  .sev0 { border-left: 3px solid var(--bad); }
  .sev1 { border-left: 3px solid var(--warn); }
  .sev2 { border-left: 3px solid #58a6ff; }
  .sev3 { border-left: 3px solid var(--border); }
  .auditclose { float: right; }
  /* suggested burns + burn queue */
  .planrow, .qrow { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
                    padding: 6px 8px; border: 1px solid var(--border-soft);
                    border-radius: 8px; margin: 4px 0; font-size: 12px; }
  .planword { display: flex; align-items: center; gap: 8px; padding: 3px 0 3px 10px;
              flex-wrap: wrap; width: 100%; }
  .qrow.qwarn { background: rgba(210,153,34,.07); border-color: rgba(210,153,34,.4); }
  .planword .psel { accent-color: var(--accent, #58a6ff); margin-right: 2px; }
  /* task 35e: proposed-burns table */
  .pbtable { margin-top: 8px; }
  .pbtable th { font-size: 10px; text-transform: uppercase; letter-spacing: .05em;
    color: var(--fg-subtle); border-bottom: 1px solid var(--border); }
  .pbtable td { vertical-align: top; }
  .pbrow .psel { accent-color: var(--accent, #58a6ff); }
  .pbrow.pboff td { opacity: .45; }
  .pbtable tr.qwarn td { background: rgba(210,153,34,.07); }
  .ok-tag { background: rgba(63,185,80,.14); color: var(--ok);
            border-color: rgba(63,185,80,.4); }
  .prop-tag { background: rgba(210,153,34,.16); color: var(--warn);
              border-color: rgba(210,153,34,.55); letter-spacing: .08em; }
  /* record timeline */
  .tl { margin: 6px 0 2px; padding-left: 4px; }
  .tlstep { position: relative; padding: 5px 0 5px 24px; }
  .tlstep::before { content: ""; position: absolute; left: 9px; top: 0; bottom: 0;
                    width: 2px; background: var(--border-soft); }
  .tlstep:first-child::before { top: 13px; }
  .tlstep:last-child::before { bottom: auto; height: 13px; }
  .tlstep .tlnode { position: absolute; left: 2px; top: 4px; font-size: 12px;
                    color: var(--fg-subtle); }
  .s-dis .tlnode, .s-dis2 .tlnode { color: var(--bad); }
  .s-en .tlnode { color: var(--ok); }
  .s-iff .tlnode { color: var(--warn); }
  .tlst { font-weight: 600; }
  .tlst.d { color: var(--bad); } .tlst.e { color: var(--ok); }
  .tlst.n { color: var(--fg-subtle); font-weight: 400; }
  .tlive { border-top: 1px dashed var(--border); margin-top: 8px; padding-top: 8px; }
  .tlive::before { display: none; }
  .tpcstat { font-size: 11px; color: var(--muted-foreground); margin-left: auto; }
  .tpcstat b { color: var(--foreground); }
  .tpcstat .ok { color: var(--ok); } .tpcstat .warn { color: var(--warn); }
  .tpcstat .bad { color: var(--bad); }

  .bits { display: flex; flex-wrap: wrap; gap: 3px; margin: 8px 0; }
  .bitcell { width: 25px; height: 21px; display: inline-flex; align-items: center;
             justify-content: center; border: 1px solid var(--border-soft); border-radius: 4px;
             font-size: 9.5px; color: var(--fg-subtle); background: var(--bg-deep);
             font-family: ui-monospace, Menlo, Consolas, monospace; }
  .bitset { background: rgba(76,194,255,.22); color: var(--foreground);
            border-color: rgba(76,194,255,.45); }
  .bitcell.dbit { background: rgba(210,153,34,.30); color: var(--foreground);
            border-color: rgba(210,153,34,.6); }

  details { border: 1px solid var(--border-soft); border-radius: 10px; padding: 10px 14px;
            margin: 10px 0; background: var(--card); }
  summary { cursor: pointer; font-weight: 600; font-size: 12.5px; color: var(--muted-foreground); }
  summary:hover { color: var(--foreground); }
  pre { white-space: pre-wrap; word-break: break-all; font-size: 11px;
        margin: 8px 0 0; color: var(--muted-foreground);
        font-family: ui-monospace, Menlo, Consolas, monospace; }
  pre .hl { color: var(--bad); font-weight: 700; }

  .flexline { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 10px 0; }
  .pill { font-size: 11px; border: 1px solid var(--border); padding: 3px 11px;
          border-radius: 99px; color: var(--muted-foreground); font-weight: 500; }
  .pill b { color: var(--foreground); }
  .pill.okl  { border-color: rgba(63,185,80,.5); color: var(--ok); }
  .pill.okl::before { content: ""; display: inline-block; width: 7px; height: 7px;
                      border-radius: 50%; background: var(--ok); margin-right: 7px;
                      animation: pulse 2s infinite; }
  .pill.badl { border-color: rgba(248,81,73,.5); color: var(--bad); }
  .pill.warnl{ border-color: rgba(210,153,34,.5); color: var(--warn); }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(63,185,80,.5); }
                     70% { box-shadow: 0 0 0 6px rgba(63,185,80,0); }
                     100% { box-shadow: 0 0 0 0 rgba(63,185,80,0); } }
  .note { font-size: 11px; color: var(--muted-foreground); }
  #detail { margin-top: 12px; display: none; }
  .statline { display: flex; gap: 10px; flex-wrap: wrap; margin: 8px 0 0; }
  .flash { animation: flashbg 1.8s ease-out; }
  @keyframes flashbg { 0% { background: rgba(210,153,34,.4); }
                       100% { background: var(--card); } }

  /* Not sticky itself — .siderail is the sticky element now. */
  #livebar { margin-bottom: 14px;
             background: rgba(13,17,23,.92); backdrop-filter: blur(6px);
             border-color: var(--border); box-shadow: 0 4px 14px rgba(0,0,0,.35); }
  #feed { font-size: 11px; color: var(--muted-foreground); margin-top: 9px;
          max-height: 130px; overflow: auto; background: var(--bg-deep);
          border: 1px solid var(--border-soft); border-radius: 7px; padding: 8px 10px; }
  /* nvtop-style GPU monitor */
  .nvhdr { display: flex; flex-wrap: wrap; gap: 14px; align-items: baseline;
           padding: 4px 2px 10px; border-bottom: 1px solid var(--border-soft); }
  .nvname { color: #22d3ee; font-weight: 700; }
  .nvlbl { color: var(--muted-foreground); font-size: 11px; }
  .nvval { font-family: var(--mono, monospace); font-size: 12px; }
  .nvbar { display: inline-block; width: 170px; height: 8px; vertical-align: middle;
           background: var(--border-soft); border-radius: 4px; overflow: hidden; }
  .nvbar > span { display: block; height: 100%; }
  .nvdev { margin: 10px 2px; line-height: 1.8; font-size: 12px; }
  .nvplotwrap { display: flex; gap: 6px; }
  .nvy { display: flex; flex-direction: column; justify-content: space-between;
         font-size: 10px; color: var(--muted-foreground); text-align: right;
         min-width: 24px; padding: 2px 0; }
  .nvplot { position: relative; flex: 1; border: 1px solid var(--border);
            background: var(--bg-deep); }
  .nvsvg { width: 100%; height: 190px; display: block; }
  .nvlegend { position: absolute; top: 4px; left: 8px; display: flex;
              flex-direction: column; font-size: 10px; line-height: 1.5; }
  .nvx { display: flex; justify-content: space-between; font-size: 10px;
         color: var(--muted-foreground); margin: 2px 0 0 30px; }
  table.nvproc { width: 100%; border-collapse: collapse; margin-top: 12px;
                 font-size: 12px; }
  table.nvproc th { background: #16a34a; color: #04140a; text-align: left;
                    padding: 4px 8px; font-size: 11px; }
  table.nvproc td { padding: 3px 8px; border-bottom: 1px solid var(--border-soft); }
  .gmon-err { color: #f87171; padding: 10px; }

  /* tabs + control panels — vertical left rail; the active marker is a
     LEFT border, not the old bottom underline. */
  .tabs { display: flex; flex-direction: column; align-items: stretch;
          gap: 2px; width: 190px; flex: 0 0 190px;
          position: sticky; top: var(--sticktop, 0px);
          max-height: calc(100vh - var(--sticktop, 0px) - 16px);
          overflow-y: auto; z-index: 15; padding: 6px 0; }
  .tab { background: none; border: none; text-align: left;
         color: var(--muted-foreground);
         padding: 8px 12px; min-height: 34px; font-size: 13px; font-weight: 500;
         cursor: pointer;
         border-left: 2px solid transparent;
         border-radius: 0 6px 6px 0; transition: color .15s, background .15s; }
  .tab:hover { color: var(--foreground); background: rgba(76,194,255,.05); }
  .tab.on { color: var(--accent); border-left-color: var(--accent); }
  .tabpane { display: none; }
  .tabpane.on { display: block; }

  /* Narrow screens: rail collapses back to a horizontal sticky tab row with
     the bottom-border active indicator; the status rail un-sticks and moves
     up right after the tabs (tabs stay first). */
  @media (max-width: 860px) {
    .layout { flex-direction: column; }
    .tabs { flex-direction: row; width: auto; flex: none; order: -2;
            position: sticky; top: var(--sticktop, 0px); z-index: 15;
            overflow-x: auto; background: var(--bg);
            border-bottom: 1px solid var(--border); margin-bottom: 14px;
            max-height: none; padding: 0; }
    .siderail { flex: none; width: auto; position: static; max-height: none;
                order: -1; }
    .tab { text-align: center; padding: 9px 15px 8px; min-height: 0;
           border-left: none; border-bottom: 2px solid transparent;
           margin-bottom: -1px; border-radius: 6px 6px 0 0; }
    .tab.on { border-left-color: transparent;
              border-bottom-color: var(--accent); }
  }

  /* B14: one visible keyboard-focus ring on the dark theme (UA default is
     rgb(16,16,16) on #0d1117 — invisible). B16: active row of the roving
     row table while the table container holds keyboard focus. */
  .btn:focus-visible, .tab:focus-visible, .tpccell:focus-visible,
  .unit:focus-visible, #rowtable:focus-visible,
  #rowtable:focus-visible tr.rowact {
    outline: 2px solid var(--accent); outline-offset: 2px; }

  h3 { font-size: 12.5px; font-weight: 650; margin: 0 0 10px; color: var(--foreground);
       display: flex; align-items: center; gap: 8px; }
  h3::before { content: ""; width: 3px; height: 11px; border-radius: 2px;
               background: var(--muted-foreground); }
  .frow { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; margin: 8px 0; }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field label { font-size: 10.5px; color: var(--fg-subtle);
                 letter-spacing: .07em; }
  /* NOTE: no text-transform here — uppercase mangles µ (U+00B5) into Greek
     capital Mu (Μ), so 'pw µs' rendered as 'PW ΜS' (looked like 'PW MS'). */
  input[type=number] { background: var(--bg-deep); border: 1px solid var(--border);
                       color: var(--foreground); border-radius: 7px; padding: 5px 8px;
                       font-size: 12px; width: 92px;
                       font-family: ui-monospace, Menlo, Consolas, monospace; }
  .checkline { display: flex; align-items: center; gap: 7px; font-size: 12px;
               color: var(--muted-foreground); }
  .btn.danger { border-color: rgba(248,81,73,.55); color: var(--bad); }
  .btn.danger:hover { border-color: var(--bad); background: rgba(248,81,73,.12); }
  .btn.go { border-color: rgba(63,185,80,.5); color: var(--ok); }
  .btn.go:hover { background: rgba(63,185,80,.1); }
  .guardlist { display: flex; flex-direction: column; gap: 3px; margin-top: 8px;
               font-size: 11.5px; font-family: ui-monospace, Menlo, Consolas, monospace; }
  .guardrow { display: flex; gap: 8px; }
  .guardrow .gs { width: 14px; }
  .logbox { background: var(--bg-deep); border: 1px solid var(--border-soft);
            border-radius: 8px; padding: 10px 12px; margin-top: 10px;
            font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 11px;
            max-height: 260px; overflow: auto; color: var(--muted-foreground);
            white-space: pre-wrap; }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
  .warnstrip { border: 1px solid rgba(210,153,34,.4); background: rgba(210,153,34,.07);
               border-radius: 8px; padding: 8px 12px; font-size: 11.5px;
               color: var(--warn); margin-top: 12px; }
  .dangerstrip { border: 1px solid rgba(248,81,73,.4); background: rgba(248,81,73,.07);
               border-radius: 8px; padding: 8px 12px; font-size: 11.5px;
               color: var(--bad); margin-top: 12px; }
  .rules { margin: 4px 0 10px; padding-left: 20px; font-size: 11.5px;
           color: var(--muted-foreground); }
  .rules li { margin: 4px 0; }
  .rules b { color: var(--foreground); }
  .ffmap { display: flex; height: 30px; border-radius: 7px; overflow: hidden;
           border: 1px solid var(--border); margin-top: 4px; }
  .seg { display: flex; align-items: center; justify-content: center;
         font-size: 9.5px; font-weight: 600; overflow: hidden; white-space: nowrap;
         letter-spacing: .03em; }
  .seg.occ { background: rgba(102,112,123,.30); color: #aab4bf; }
  .seg.buf { background: rgba(210,153,34,.18); color: var(--warn); }
  .seg.zone { background: rgba(63,185,80,.16); color: var(--ok); }
  .seg.smr { background: rgba(188,140,255,.16); color: #bc8cff; }
  .seg.rev { background: rgba(248,81,73,.14); color: var(--bad); }

  footer { margin-top: 26px; padding-top: 14px; border-top: 1px solid var(--border-soft);
           color: var(--fg-subtle); font-size: 11px; display: flex; gap: 14px; flex-wrap: wrap; }
</style>
</head>
<body>
<div class="app">
  <div class="sticktop">
  <header class="topbar">
    <div>
      <h1>GA100 Fuse Console</h1>
      <div class="sub mono" id="meta"></div>
    </div>
    <div style="display:flex; align-items:center; gap:10px">
      <a class="topbadge" href="#" id="dumpsbtn" style="text-decoration:none"
         title="Browse saved dumps of this or any other card — never shown by default">Saved dumps</a>
      <a class="topbadge" href="/api/support_bundle" style="text-decoration:none"
         title="Download console logs + dumps + interpretation trace as one tar.gz — attach it when reporting an issue">Support bundle</a>
      <div class="topbadge"><span class="dot"></span>pico-ga100vfi · live console</div>
    </div>
  </header>
  </div>
  <div class="layout">
  <nav class="tabs" role="tablist" aria-label="console views">
    <button class="tab on" role="tab" id="tabbtn-explorer" aria-controls="tab-explorer"
            aria-selected="true" tabindex="0" data-tab="explorer">Fuse Explorer</button>
    <button class="tab" role="tab" id="tabbtn-glitch" aria-controls="tab-glitch"
            aria-selected="false" tabindex="-1" data-tab="glitch">Glitch &amp; Burn</button>
    <button class="tab" role="tab" id="tabbtn-drivers" aria-controls="tab-drivers"
            aria-selected="false" tabindex="-1" data-tab="drivers">Drivers</button>
    <button class="tab" role="tab" id="tabbtn-gpu" aria-controls="tab-gpu"
            aria-selected="false" tabindex="-1" data-tab="gpu">GPU Info</button>
  </nav>
  <main class="content">
  <section id="tab-explorer" class="tabpane on" role="tabpanel" aria-labelledby="tabbtn-explorer">
  <div class="card verdict" id="cardless" style="display:none"></div>
  <div class="card verdict warnv" id="dumpsrc" style="display:none"></div>
  <div class="card verdict warnv" id="nodata" style="display:none"></div>
  <div id="dumpwrap">
  <h2>Status</h2>
  <div class="grid" id="status"></div>

  <h2>Diagnosis</h2>
  <div class="card verdict" id="verdict"></div>

  <h2>Silicon topology — GPC / FBP floorsweep</h2>
  <div class="flexline" id="statebtns"></div>
  <div class="legend">
    <span><i class="sw on"></i>active</span>
    <span><i class="sw off"></i>floorswept (re-enableable)</span>
    <span><i class="sw dead"></i>dead silicon · off</span>
    <span><i class="sw deadon"></i>dead silicon · ENABLED (brick)</span>
  </div>
  <div class="card" id="topo"></div>

  <h2>TPC map — SM availability per GPC <span class="note">(8 TPC per GPC · 2 SM per TPC)</span></h2>
  <div class="legend">
    <span><i class="sw on"></i>enabled now</span>
    <span><i class="sw off"></i>disabled · healthy (unlock headroom)</span>
    <span><i class="sw dead"></i>defective silicon (never usable)</span>
  </div>
  <div class="card" id="tpcmap"></div>
  <div class="card" id="proposed-burns" style="display:none"></div>
  </div><!-- /#dumpwrap: dimmed + labelled when the shown dump is not the present card -->

  <h2>Shadow registers</h2>
  <div class="scroll" id="shadow"></div>

  <h2>Fuse rows (0–487)</h2>
  <div class="flexline" id="rowbtns"></div>
  <div class="flexline">
    <input type="text" id="search" placeholder="search row # or hex value…">
    <span class="note" id="rowcount"></span>
  </div>
  <div class="scroll" id="rowtable" tabindex="0" role="region"
       aria-label="fuse rows — arrow keys move the active row, Enter selects"></div>
  <div class="card" id="detail"></div>

  <h2>Interpretation log</h2>
  <div class="card"><div id="interp"></div></div>

  <details><summary>dmesg tail (GPU boot)</summary><pre id="dmesg"></pre></details>
  <details><summary>Hex window — non-zero words in 0x820000–0x824400</summary>
    <input type="text" id="hexsearch" placeholder="filter offset/value…" style="margin-top:6px">
    <div class="scroll" id="hextable" style="margin-top:6px"></div></details>

  </section>

  <section id="tab-glitch" class="tabpane" role="tabpanel" aria-labelledby="tabbtn-glitch">
    <div class="card"><div class="note">Glitch &amp; Burn controls are available when this
    page is served by the live console (<span class="mono">ga100vfi.console</span>).</div></div>
  </section>
  <section id="tab-drivers" class="tabpane" role="tabpanel" aria-labelledby="tabbtn-drivers">
    <div class="card"><div class="note">Driver management is available in live mode.</div></div>
  </section>
  <section id="tab-gpu" class="tabpane" role="tabpanel" aria-labelledby="tabbtn-gpu">
    <div class="card"><div class="note">GPU info is available in live mode.</div></div>
  </section>
  </main>
  <aside class="siderail" id="siderail">__LIVEBAR__</aside>
  </div>

  <div id="auditbg" role="dialog" aria-modal="true" aria-label="unit audit"><div id="audit"></div></div>
  <div id="dpbg" role="dialog" aria-modal="true" aria-label="saved dumps">
    <div class="card" id="dumppicker">
      <div class="flexline" style="justify-content:space-between; align-items:center">
        <b>Saved dumps — newest first</b>
        <span class="flexline">
        <button class="btn" id="dumppicker-dedupe"
          title="Find saved dumps whose FUSE CONTENT is identical to another dump of the same card (timestamps/dmesg/lspci ignored). Each identical group keeps its oldest dump; anything different — one differing row, another card — is kept. Dry-run first, delete on confirm.">Dedupe</button>
        <button class="btn" id="dumppicker-close">Close ✕</button>
        </span>
      </div>
      <div class="card verdict" id="dedupebox" style="display:none;margin-top:8px"></div>
      <div class="scroll" id="dumplist" style="margin-top:8px"></div>
    </div>
  </div>

  <footer>
    <span>data: ga100vfi.fusedump + ga100vfi.console</span>
    <span>FF decode: chain=bits[4:0] iff=bit5 block=bits[15:6] data=bits[31:16]</span>
    <span>burns require arm token + pure 0→1 payload + open burn window (EFP/WDATA_PLM auto-arm via SENSE_CTRL) · FUSEWDATA untouched otherwise</span>
  </footer>
</div>

<script id="dumpdata" type="application/json">__PAYLOAD__</script>
<script id="advanceddata" type="application/json">__ADVANCED__</script>
<script id="ffcatdata" type="application/json">__FFCAT__</script>
<script>
"use strict";
let D = JSON.parse(document.getElementById("dumpdata").textContent);
// task 30: optional advanced unlocks decoded from the bench cards' executed
// signed plans — single source host/ga100vfi/advanced_unlocks.py, embedded
// by build_html (see the Advanced unlocks card in the Glitch & Burn tab).
const ADVANCED = JSON.parse(document.getElementById("advanceddata").textContent);
// task 41: chain-1 FF field catalog [name, global_bit_start, width],
// embedded from service.FF_FIELDS — the SAME catalog the server's plane
// gate uses. Global bit g lives in block g//16, data bit g%16.
const FF_CAT = JSON.parse(document.getElementById("ffcatdata").textContent);
// Same overlap arithmetic as service.ff_fields_for (data window of a block).
function ffFieldsFor(block) {
  const lo = block * 16, out = [];
  for (const [name, g, w] of FF_CAT) {
    const a = Math.max(g, lo), b = Math.min(g + w, lo + 16);
    if (a < b) out.push({name, g, w, dlo: a - lo, n: b - a, fbit0: a - g});
  }
  return out;
}
// Shadow key holding a field's dead-silicon readout (dump.json shadow
// names; mirrors FF_FIELD_DEFECT's register set, service.py).
function defectKey(name) {
  return name.startsWith("TPC_GPC")
    ? "TPC_DEFECTIVE_" + name.split("_")[1]
    : name.replace("_DISABLE", "_DEFECTIVE");
}
// task 35c: the burn queue is declared HERE (page script, var → global) so
// the proposed-burns panel can read it during first paint, before the
// live-boot script loads; the live-boot script uses this same binding.
var burnQueue = [];
// pristine copy of the server seed (the current card's own dump, or the
// empty STUB) — "Back to current" restores the default face from it.
const SEED = JSON.parse(document.getElementById("dumpdata").textContent);
// Stock baseline of the PRESENT card (task 24): the first dump ever saved
// for its serial (dumps/sn-<serial>/stock.json via /api/stock). null = no
// baseline yet — the stock view then shows the now state and says so.
let STOCK = null;
let STOCK_NOTE = "";

const fmt = v => "0x" + ((v ?? 0) >>> 0).toString(16).toUpperCase().padStart(8, "0");
const bitsOf = v => { const b = []; v = (v ?? 0) >>> 0;
  for (let i = 0; i < 32; i++) if ((v >>> i) & 1) b.push(i); return b; };
const pop = v => bitsOf(v).length;
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
  .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
// verified FF-record field map: chain=bits[4:0], iff=bit5, block=bits[15:6], data=bits[31:16]
const ffDecode = v => ({ ch: v & 0x1F, iff: (v >> 5) & 1,
                         blk: (v >> 6) & 0x3FF, data: (v >>> 16) & 0xFFFF });

// ---- task 32: last-wins-aware "already present" (single source) ----
// The controller replays FF records in row order and the LAST record per
// block wins at boot, so a word is already EFFECTIVE only when the last
// live record of its own block equals it. A matching word that a later
// record of the same block overrides is NOT effective — it needs re-burn.
// (Rows outside the FF region 222-487 are direct OTP words, never block
// records; blank = 0x0/0xFFFFFFFF, same rule as the row table and the
// server's ff_layout_from_rows.) Returns
//   {state:"present", row}                       — last record of the block IS this word
//   {state:"superseded", row, byRow}             — this word is in the block, a later record wins
//   null                                         — word not in the block
function lastWinsStatus(word) {
  const rows = D.rows || {};
  const f = ffDecode(word);
  if (f.iff) return null;   // IFF macro words have no block replay to win
  let lastRow = -1, lastVal = null, foundRow = null;
  for (const k of Object.keys(rows)) {
    const r = +k, v = rows[k];
    if (typeof v !== "number" || v === 0 || v === 0xFFFFFFFF) continue;
    if (r < 222 || r > 487) continue;
    const g = ffDecode(v);
    if (g.iff || g.blk !== f.blk) continue;
    if (r > lastRow) { lastRow = r; lastVal = v; }
    if (v === word && foundRow === null) foundRow = r;
  }
  if (lastVal === word) return { state: "present", row: lastRow };
  if (foundRow !== null) return { state: "superseded", row: foundRow, byRow: lastRow };
  return null;
}
// DIRECT OTP rows (<222, plain words — advanced manual steps): the effect
// is achieved when every delta bit is already set in the dump's row value.
function directStepPresent(step) {
  const rows = D.rows || {};
  return step.rows.every(r => {
    const v = rows[String(r)];
    return typeof v === "number" && ((v >>> 0) & step.delta) === step.delta;
  });
}

const REGIONS = [
  { min: 0,  max: 47,  name: "MAIN", desc: "main array — paired option words (row 0 = 0x53557C3D known-good signature, bit 5 = DISABLE_SW_OVERRIDE)" },
  { min: 48, max: 95,  name: "UNIQ", desc: "main array — unpaired rows (hash / per-chip data)" },
  { min: 96, max: 221, name: "FPF",  desc: "FPF region — production-writable config rows (96–221)" },
  { min: 222, max: 487, name: "FF",  desc: "fuseless-fuse region — boot-replayed records (222–487), last record per block wins" },
];
const regionOf = r => REGIONS.find(x => r >= x.min && r <= x.max) ||
  { min: r, max: r, name: "TAIL", desc: "rows beyond 487 — outside the documented row map" };

// ---------------------------------------------------------------- renderers
// Data-source state for the dump-derived panels: null = the shown dump
// belongs to the card in the slot (or nothing to compare against);
// {reason:"absent"|"different", curSerial} = the shown dump is SAVED data
// of another card — label it, don't render it as present-tense live.
let STALE = null;
function staleSuffix() {
  if (!STALE) return "";
  return STALE.reason === "absent" ? "  —  card not present"
    : STALE.reason === "history" ? "  —  browsing saved dump"
    : "  —  different card present (serial " + (STALE.curSerial || "unknown") + ")";
}
function renderMeta() {
  const nb = Object.keys(D.nonblank_rows || {}).length;
  const sn = D.serial ? "SN " + D.serial
    : "no serial" + (D.serial_source === "unavailable" ? " (unreadable)" : "");
  document.getElementById("meta").textContent =
    (STALE ? "SAVED DUMP OF  " : "") +
    `${D.bdf}  ·  ${sn}  ·  ${D.vendor}:${D.device} rev ${D.revision}  ·  driver=${D.driver}  ·  ` +
    `dumped ${D.started}  ·  fingerprint ${D.fingerprint}  ·  ${D.row_count} rows, ${nb} non-blank` +
    staleSuffix();
}

function renderStatus() {
  const status = D.status || {};
  const cards = [];
  const add = (k, v, cls, note) => cards.push(
    `<div class="card stat" data-key="status.${k}"><div class="k">${k}</div>` +
    `<div class="v mono ${cls}">${v}</div><div class="k">${note || ""}</div></div>`);
  // Unknown (null) registers must never render as a definitive state (B3).
  const NODATA = "no data — probe failed/paused";
  add("CRC_STATUS", status.CRC_STATUS == null ? "—" : fmt(status.CRC_STATUS),
    status.CRC_STATUS == null ? "" : (status.CRC_STATUS === 0x55 ? "ok" : "bad"),
    status.CRC_STATUS == null ? NODATA
      : status.CRC_STATUS === 0x55 ? "fuse block parses cleanly" : "hash regions invalid");
  add("DSOV", status.DSOV == null ? "—" : String(status.DSOV & 1),
    status.DSOV == null ? "" : (status.DSOV & 1) ? "" : "warn",
    status.DSOV == null ? NODATA
      : (status.DSOV & 1) ? "factory-locked (normal)" : "glitch/burn gate OPEN");
  add("SBFE", status.SBFE == null ? "—" : String(status.SBFE & 1), "",
    status.SBFE == null ? NODATA
      : (status.SBFE & 1) ? "writes confined to FPF 96–221" : "arbitrary FF writes allowed");
  add("EFP", status.EFP == null ? "—" : String(status.EFP & 1), "",
    status.EFP == null ? NODATA : "");
  add("EN_SW_OVERRIDE", status.EN_SW_OVERRIDE == null ? "—" : fmt(status.EN_SW_OVERRIDE),
    "", status.EN_SW_OVERRIDE == null ? NODATA : "row-read override state");
  add("PRIV_MASK", status.PRIV_MASK == null ? "—" : fmt(status.PRIV_MASK),
    status.PRIV_MASK == null ? "" : (status.PRIV_MASK === 0xFFFFFFFF ? "ok" : "warn"),
    status.PRIV_MASK == null ? NODATA : "PLM state");
  const smi = (D.nvidia_smi || "").trim();
  add("nvidia-smi", smi ? esc(smi.split("\n")[0] || "n/a") : "not queried",
    smi ? (/No devices|error|ERR|failed/i.test(smi) ? "bad" : "ok") : "", "device init");
  document.getElementById("status").innerHTML = cards.join("");
}

function renderVerdict() {
  const el = document.getElementById("verdict");
  const gpc = D.shadow ? D.shadow.GPC_DISABLE : undefined;
  const fbp = D.shadow ? D.shadow.FBP_DISABLE : undefined;
  if (gpc == null || fbp == null) {
    el.classList.toggle("good", false);
    el.innerHTML = "waiting for data…";
    return;
  }
  const zeroed = gpc === 0 && fbp === 0;
  const html = zeroed
    ? `<b class="bad">Floorsweep masks fully cleared — dead silicon enabled.</b><br>
       If you burned GPC/FBP records: a bit-exact row readback does NOT mean the mask
       followed (verified twice on (1,19) FBP and (1,8) GPC). Check
       <span class="mono">STATUS_OPT_*</span>: if the chain didn't latch, the card
       boots trying to use dead units (GFW stalls at progress 0x1) and needs a
       corrective burn or is parked.`
    : `<b class="ok">Floorsweep masks not zeroed — masks-cleared brick signature absent.</b>`;
  el.classList.toggle("good", !zeroed);
  el.innerHTML = html;
}

// topology ---------------------------------------------------------------
let curState = "now";
const STATES = { stock: "Stock state (this card's factory fuses)",
                intended: "Intended (this card's defects)",
                now: "NOW (live)" };
function renderStateBtns() {
  const sb = document.getElementById("statebtns");
  sb.innerHTML = Object.entries(STATES).map(([k, l]) =>
    `<button class="btn ${k === curState ? "on" : ""}" data-st="${k}">${l}</button>`).join("");
  sb.querySelectorAll("button").forEach(b => b.onclick = () => {
    curState = b.dataset.st;
    sb.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
    renderTopo();
    renderTpc();
    renderProposedBurns();
  });
}
function unit(cls, name, sub, audit) {
  return `<div class="unit ${cls}" data-audit="${audit}" ` +
    `title="click for full register audit">${name ? `<b>${name}</b>` : ""}<span>${sub}</span></div>`;
}
function renderTopo() {
  const sh = D.shadow || {};
  const gpcDef = sh.GPC_DEFECTIVE ?? 0, fbpDef = sh.FBP_DEFECTIVE ?? 0;
  let gpcDis, fbpDis;
  if (curState === "stock") {
    // Stock = THIS card's own first-saved dump (stock.json), same
    // extraction as NOW. No baseline yet -> show the now state; the
    // note below says it is the first record.
    const ss = (STOCK && STOCK.shadow) || sh;
    gpcDis = ss.GPC_DISABLE ?? 0; fbpDis = ss.FBP_DISABLE ?? 0;
  } else if (curState === "intended") {
    // Per-card, derived from THIS card's dump: the unlock goal is to
    // re-enable every unit that is not defective, so the intended
    // disable mask equals the card's own defective mask.
    gpcDis = gpcDef; fbpDis = fbpDef;
  } else { gpcDis = sh.GPC_DISABLE ?? 0; fbpDis = sh.FBP_DISABLE ?? 0; }
  let gpcHtml = "", fbpHtml = "";
  for (let i = 0; i < 8; i++) {
    const dead = (gpcDef >> i) & 1, dis = (gpcDis >> i) & 1;
    const cls = dead ? (dis ? "dead" : "deadon") : (dis ? "off" : "u-on");
    const sub = dead ? (dis ? "dead · off" : "DEAD · ON!") : (dis ? "floorswept" : "active");
    gpcHtml += unit(cls, "GPC" + i, sub, "gpc:" + i);
  }
  for (let i = 0; i < 12; i++) {
    const dead = (fbpDef >> i) & 1, dis = (fbpDis >> i) & 1;
    const cls = dead ? (dis ? "dead" : "deadon") : (dis ? "off" : "u-on");
    const sub = dead ? (dis ? "dead · off" : "DUMMY · ON!") : (dis ? "floorswept" : "active");
    fbpHtml += unit(cls, "FBP" + i, sub, "fbp:" + i);
  }
  const liveG = 8 - pop(gpcDis), liveF = 12 - pop(fbpDis);
  document.getElementById("topo").innerHTML =
    `<div class="note" style="margin-bottom:4px">defective masks (real silicon): ` +
    `GPC ${JSON.stringify(bitsOf(gpcDef))} · FBP ${JSON.stringify(bitsOf(fbpDef))}</div>` +
    `<div>${gpcHtml}</div><div style="height:8px"></div><div>${fbpHtml}</div>` +
    `<div class="statline">` +
    `<span class="pill">GPCs booted: <b>${liveG}/8</b> (silicon max ${8 - pop(gpcDef)}/8)</span>` +
    `<span class="pill">FBPs booted: <b>${liveF}/12</b> → claims <b>${liveF * 8} GB</b> ` +
    `(real silicon ${(12 - pop(fbpDef)) * 8} GB)</span></div>` +
    (curState === "now" && (gpcDis === 0 || fbpDis === 0)
      ? `<div class="note" style="margin-top:8px">Boxes with <b>ON!</b> on dead/dummy units ` +
        `mean the card boots dead silicon (GFW hang at progress 0x1).</div>` : "");
}

// TPC map -----------------------------------------------------------------
const TPC_FFDEF = [0x8205c8,0x820508,0x82050c,0x820514,0x820564,0x8205ac,0x820b84,0x820b80];
function computeTpc(dump) {
  // Mirror of fusedump.tpc_summary(). DEFECTIVE = FF-region words
  // (TPC_FFDEF, kate-land ga100-options offsets) — readable and correct
  // even for floorswept GPCs; the hex window, when present, is ground
  // truth and repairs old dumps whose shadow keys came from the runtime
  // word. 0x820760 (SKU) and 0x820C38 (runtime) both read 0xFF on a
  // power-gated GPC — power artifact, never a defect count.
  // `dump` defaults to the shown dump; the stock view passes STOCK so
  // the very same extraction runs over the card's own baseline.
  const D0 = dump || D;
  const sh = D0.shadow || {};
  const hw = D0.hexnonzero || [];
  const word = off => { const e = hw.find(([o]) => o === off); return e ? e[1] >>> 0 : null; };
  const gpcDef = sh.GPC_DEFECTIVE ?? 0, gpcDis = sh.GPC_DISABLE ?? 0;
  const gpcs = [], totals = { sm_now: 0, sm_max: 0, sm_defective: 0,
                              sm_recoverable: 0, tpc_defective: 0,
                              tpc_recoverable: 0, have_data: false };
  const pop = v => { let n = 0; while (v) { n += v & 1; v >>>= 1; } return n; };
  for (let g = 0; g < 8; g++) {
    // FF word: authoritative; window present means a covered offset that
    // is absent reads ZERO (do not fall through to the poisoned shadow key)
    let def = hw.length ? (word(TPC_FFDEF[g]) ?? 0)
                        : (sh["TPC_DEFECTIVE_GPC" + g] ?? sh["TPC_DISABLE_" + g]);
    let dis = sh["TPC_DISABLE_GPC" + g];
    if (dis == null) dis = word(0x820c38 + 4 * g);
    if (def == null && dis == null) { gpcs.push({ gpc: g, available: false }); continue; }
    def = ((def ?? 0) >>> 0) & 0xFF;
    dis = (((dis == null ? def : dis)) >>> 0) & 0xFF;
    const gdead = (gpcDef >> g) & 1, gdis = (gpcDis >> g) & 1;
    // Floorswept GPC: show fully masked (every healthy TPC in it is the
    // unlock prize). Powered GPC: live mask = runtime ∪ defective.
    const eff = gdis ? 0xFF : (def | dis);
    const ndef = pop(def), ndis = pop(eff);
    const recov = gdead ? 0 : ndis - ndef;
    const tpc_now = gdis ? 0 : 8 - pop(def | dis);
    const tpc_max = gdead ? 0 : 8 - ndef;
    const row = { gpc: g, available: true, def, dis, eff,
                  tpc_defective: ndef, tpc_recoverable: recov,
                  tpc_now, tpc_max,
                  sm_now: tpc_now * 2, sm_max: tpc_max * 2,
                  gpc_defective: gdead, gpc_disabled: gdis };
    gpcs.push(row);
    totals.have_data = true;
    totals.sm_now += row.sm_now;
    totals.sm_max += tpc_max * 2;
    totals.sm_defective += ndef * 2;
    totals.sm_recoverable += recov * 2;
    totals.tpc_defective += ndef;
    totals.tpc_recoverable += recov;
  }
  return { gpcs, totals };
}
function renderTpc() {
  const el = document.getElementById("tpcmap");
  const sh = D.shadow || {};
  if (sh.TPC_DEFECTIVE_GPC0 == null && sh.TPC_DISABLE_GPC0 == null &&
      sh.TPC_DISABLE_0 == null && !(D.tpc && D.tpc.totals.have_data)) {
    el.innerHTML = `<span class="note">waiting for TPC register data…</span>`;
    return;
  }
  const T = (D.tpc && D.tpc.totals && D.tpc.totals.have_data) ? D.tpc : computeTpc();
  // Stock rows: the SAME extraction run over this card's own baseline.
  const TS = (curState === "stock" && STOCK) ? computeTpc(STOCK) : null;
  const gpcDef = sh.GPC_DEFECTIVE ?? 0;
  const tot = { sm_now: 0, sm_max: 0, tpc_def: 0, sm_def: 0,
                tpc_recov: 0, sm_recov: 0 };
  let html = "";
  for (const r of T.gpcs) {
    if (!r || !r.available) {
      html += `<div class="tpcrow"><div class="tpcglab">GPC${r ? r.gpc : "?"}` +
        `<span class="gstate">no data</span></div></div>`;
      continue;
    }
    const g = r.gpc;
    const gdead = (gpcDef >> g) & 1;
    const def = (r.def ?? 0) & 0xFF;   // silicon truth — same in every state
    let dis, gdis;
    if (curState === "stock") {
      // This card's own baseline (same extraction as NOW); no baseline
      // yet -> the now row, and the note says this dump is the record.
      const sr = TS ? TS.gpcs[g] : null;
      if (sr && sr.available) {
        dis = (sr.eff ?? ((sr.def ?? 0) | (sr.dis ?? 0))) & 0xFF;
        gdis = sr.gpc_disabled ? 1 : 0;
      } else { dis = (r.eff ?? ((r.def ?? 0) | (r.dis ?? 0))) & 0xFF;
               gdis = r.gpc_disabled ? 1 : 0; }
    } else if (curState === "intended") {
      dis = def; gdis = gdead;        // goal: everything not dead runs
    } else {
      dis = (r.eff ?? ((r.def ?? 0) | (r.dis ?? 0))) & 0xFF;
      gdis = r.gpc_disabled ? 1 : 0;
    }
    const eff = def | dis;
    const ndef = pop(def), ndis = pop(eff);
    const recov = Math.max(ndis - ndef, 0);
    const tpcMax = gdead ? 0 : 8 - ndef;
    const smNow = gdis ? 0 : (8 - ndis) * 2;
    const recovSm = gdead ? 0 : recov * 2;
    const gstate = gdead ? `<span class="gstate bad">GPC defective</span>`
                 : gdis  ? `<span class="gstate warn">floorswept</span>`
                         : `<span class="gstate ok">active</span>`;
    let cells = "";
    for (let t = 0; t < 8; t++) {
      const d = (def >> t) & 1, z = (eff >> t) & 1;
      const cls = d ? "dead" : (z ? "recov" : "on");
      const zLbl = curState === "stock"
        ? "disabled at first sight, healthy — the unlock prize"
        : "disabled, healthy — unlock headroom";
      cells += `<div class="tpccell ${cls}${(gdead || gdis) && !d ? " goff" : ""}" ` +
        `data-audit="tpc:${g}:${t}" ` +
        `title="GPC${g} TPC${t}: ${d ? "defective" : z ? zLbl : "enabled"}` +
        `${gdead ? " (GPC dead)" : gdis ? " (GPC floorswept)" : ""} — click for full audit">` +
        `<b>T${t}</b><span>${d ? "defect" : "2 SM"}</span></div>`;
    }
    html += `<div class="tpcrow">` +
      `<div class="tpcglab" data-audit="gpc:${g}" title="click for full GPC audit">GPC${g}${gstate}</div>` +
      `<div class="tpccells">${cells}</div>` +
      `<div class="tpcstat">` +
        `SM now <b>${smNow}</b> · ` +
        `after unlock <b class="${tpcMax ? "ok" : "bad"}">${tpcMax * 2}</b> · ` +
        `defective <b class="bad">${ndef * 2} SM</b>` +
        (recovSm ? ` · <span class="warn">+${recovSm} recoverable</span>` : "") +
      `</div></div>`;
    tot.sm_now += smNow; tot.sm_max += tpcMax * 2;
    tot.tpc_def += ndef; tot.sm_def += ndef * 2;
    tot.tpc_recov += gdead ? 0 : recov; tot.sm_recov += recovSm;
  }
  const stateTag = { stock: "STOCK (this card's factory fuses — first dump seen)",
                     intended: "INTENDED (this card's defects — everything not dead runs)",
                     now: "NOW (live registers)" }[curState];
  html += `<div class="statline">` +
    `<span class="pill">state: <b>${stateTag}</b></span>` +
    `<span class="pill">SM now: <b>${tot.sm_now}</b></span>` +
    `<span class="pill okl">SM after unlock (fuse ceiling): <b>${tot.sm_max}</b></span>` +
    `<span class="pill badl">defective: <b>${tot.tpc_def} TPC / ${tot.sm_def} SM</b></span>` +
    `<span class="pill warnl">unlock headroom: <b>${tot.tpc_recov} TPC / ${tot.sm_recov} SM</b></span>` +
    `</div>` +
    `<div class="note" style="margin-top:8px">Defective bits are this card's own silicon and are ` +
    `identical in all three states. ` +
    (curState === "stock"
      ? (STOCK
          ? `Stock is THIS card's own first-saved baseline (${esc(STOCK_NOTE)}). ` +
            `If this card was modified before this console first saw it, stock = state at first sight. ` +
            `The yellow cells are what the unlock recovers; a stock-vs-now difference is a real ` +
            `fuse change (campaign effect), never a template artifact.`
          : `No stock baseline recorded yet — this dump is the first record; the stock view shows ` +
            `the now state until a baseline is saved.`)
      : curState === "intended"
        ? `Intended = disable mask equals the card's defective mask: every unit that is not dead ` +
          `silicon runs. No yellow cells by definition.`
        : `Now reads: TPC defective from the FF words 0x8205C8/508/50C/514/564/5AC ` +
          `and 0x820B84/B80 (correct even for gated GPCs), live mask 0x820C38+gpc·4 ` +
          `(defective-union; a floorswept GPC's runtime word reads 0xFF — power ` +
          `artifact, shown fully masked). Yellow cells = still-disabled-but-healthy ` +
          `headroom; floorswept GPCs count their whole healthy half.`) +
    ` Post-unlock ceiling = (8 − defective TPC) × 2 SM per non-defective GPC. Cells in a ` +
    `floorswept/dead GPC are dimmed: their health is shown, but they only run once the GPC ` +
    `itself is enabled.</div>`;
  el.innerHTML = html;
}

// Proposed burns for the INTENDED state (tasks 26+27): the burn records
// that would bring the live disable masks to this card's defective masks.
// Words come from window.__suggestPlan and rows from
// window.__planRowAssignment — the SAME planner and the SAME free-row
// allocator that feed the "Suggested burns" card and the burn queue — so a
// proposed "row N" IS the row "Queue these burns" will assign (same dump,
// same plan order, same mirror setting). The queue button goes through
// window.__queueProposedBurns, the same queue path; nothing here re-derives
// encodings or rows. Recompute triggers: every state switch and every dump
// change (renderLive runs on each poll tick and after each new dump), so
// after a real burn moves NOW, the next dump shows fewer or no proposals.
// Renders ONLY in the intended state — never in NOW or STOCK.
// Task 32: every word carries a selection checkbox (default ON, except
// words already EFFECTIVE under last-wins, which default OFF); "Queue
// these burns" queues only the selected words through the same
// window.__queueSelectedPlan path the Suggested card uses — selection is
// shared state, so both lists always show the same checkboxes.
function renderProposedBurns() {
  const el = document.getElementById("proposed-burns");
  if (!el) return;
  if (curState !== "intended" || !(D.row_count > 0) || !D.shadow ||
      typeof window.__suggestPlan !== "function") {
    el.style.display = "none"; el.innerHTML = ""; return;
  }
  el.style.display = "";
  const plan = window.__suggestPlan();
  const asg = typeof window.__planRowAssignment === "function"
    ? window.__planRowAssignment() : null;
  const hex = w => "0x" + w.toString(16).toUpperCase().padStart(8, "0");
  const words = plan.flatMap(p => (p.pair ? p.words : [p.word]));
  const sel = words.filter(w => window.__planWordSelected(w)).length;
  let html = `<h3>Proposed burns to reach INTENDED</h3>` +
    `<div class="note">badge meanings: see the <b>Tag legend</b> on the Glitch &amp; Burn tab.</div>` +
    `<div class="note"><b class="warn">PROPOSED — not burned; irreversible ` +
    `OTP writes pending a Goldilocks campaign.</b> These records would set ` +
    `the disable masks to the card's defective masks; nothing is written ` +
    `until a burn campaign runs. Tick the words to burn; already-present ` +
    `words (last record of their block already equals the word) start ` +
    `unticked.</div>`;
  if (asg && asg.noFree > 0)
    html += `<div class="note"><b class="bad">⚠ ${asg.noFree} of ${asg.rows.length} ` +
      `selected words have no blank row after their own block's last record — free ` +
      `space first; the queue will refuse to start until rows are available.</b></div>`;
  if (!plan.length) {
    html += `<div class="note">no burns proposed — card already at intended state</div>`;
  }
  let ai = 0;   // index into asg.rows — selected words only, same order as __planRowAssignment
  html += `<table class="pbtable"><thead><tr><th></th><th>Burn</th><th>Word</th>` +
    `<th>Target row</th><th>Field</th><th>Effect</th><th>Status</th></tr></thead><tbody>`;
  for (const p of plan) {
    const words = p.pair ? p.words : [p.word];
    html += words.map((w, wi) => {
      const f = window.__ffEffect(w);
      const st = lastWinsStatus(w);
      const on = window.__planWordSelected(w);
      // task 35c: a word already in the burn queue shows the queue's row,
      // not a fresh allocation — one word, one row.
      const inQ = burnQueue.some(q => q.word === w);
      const a = on && !inQ ? (asg ? asg.rows[ai++] : null) : null;
      const rowCell =
        !on ? `<span class="note">not selected</span>`
        : inQ ? `<span class="note">in queue — row shown there</span>`
        : !asg ? `<span class="note">rows pending</span>`
        : a === null ? `<b class="bad">NO FREE ROW (block ${ffDecode(w).blk})</b>`
        : `<b data-proprow="${a.row}${a.mirror ? "+" + (a.row + 1) : ""}">row ${a.row}${a.mirror ? ` + mirror ${a.row + 1}` : ""}</b>`;
      const statusCell =
        st && st.state === "present" ? `<span class="tag ok-tag">ALREADY PRESENT (row ${st.row})</span>`
        : st && st.state === "superseded" ? `<span class="tag prop-tag">SUPERSEDED at row ${st.byRow}</span>`
        : `<span class="note">—</span>`;
      return `<tr class="pbrow${on ? "" : " pboff"}">` +
        `<td><input type="checkbox" class="psel" data-sel-word="${w}"${on ? " checked" : ""} ` +
          `title="include this word in the queue"></td>` +
        (wi === 0 ? `<td rowspan="${words.length}"><b>${esc(p.label)}</b><br>` +
          `<span class="note">${esc(p.recs)}</span></td>` : "") +
        `<td class="mono">${hex(w)}</td>` +
        `<td>${rowCell}</td>` +
        `<td class="note">${esc(f.key)}</td>` +
        (wi === 0 ? `<td rowspan="${words.length}" class="note">${esc(p.effect)}</td>` : "") +
        `<td>${statusCell}</td></tr>`;
    }).join("");
  }
  html += `</tbody></table>`;
  // task 39: disposition for disabled-but-not-defective fields we
  // deliberately do NOT propose, so the panel answers every mask.
  {
    const sh = D.shadow || {};
    const nv = (sh.NVLINK_DISABLE ?? 0) & ~(sh.NVLINK_DEFECTIVE ?? 0);
    if (nv) html += `<div class="note" style="margin-top:6px">Not proposed: ` +
      `NVLink disable ${fmt(nv)} — healthy but floorswept; this board has ` +
      `no NVLink connector, so the floorsweep is kept (reference cards kept it too).</div>`;
  }
  if (plan.length) {
    html += `<div class="frow" style="margin-top:8px">` +
      `<button class="btn" data-sel-all="1">select all</button>` +
      `<button class="btn" data-sel-all="0">select none</button>` +
      `<button class="btn go" id="proposed-queue">⤓ Queue these burns</button>` +
      `<span class="pill">${sel} of ${words.length} word(s) selected</span></div>`;
  }
  el.innerHTML = html;
  el.querySelectorAll("[data-sel-word]").forEach(c => c.onchange = () => {
    window.__setPlanWordSelected(+c.dataset.selWord, c.checked);
  });
  el.querySelectorAll("[data-sel-all]").forEach(b => b.onclick = () => {
    window.__setAllPlanWordsSelected(b.dataset.selAll === "1");
  });
  const qb = document.getElementById("proposed-queue");
  if (qb) qb.onclick = () => window.__queueProposedBurns();
}

// stock baseline fetch (task 24): the present card's first-saved dump.
// null/absent -> the stock view falls back to the now state and says so.
async function fetchStock() {
  try {
    const r = await fetch("/api/stock", { cache: "no-store" });
    const j = await r.json();
    STOCK = j.stock || null;
    STOCK_NOTE = j.provenance || j.reason || "";
    if (curState === "stock") { renderTopo(); renderTpc(); }
  } catch (e) { /* static page or service down: stock view shows now-state */ }
}

// unit audit ---------------------------------------------------------------
// Click any GPC / FBP / TPC tile: every dump record that holds a bit against
// that unit, sorted by impact. Rows are ONLY added when the register actually
// has a bit set for this unit — zero/no-impact registers are not listed.
// Effective FBPA/FBIO disable mirrors (0x820C18/0x820C14) are shown only
// when the unit is defective, as corroboration that the mask covers it.
const AOFF = {
  GPC_DISABLE: 0x820350, FBP_DISABLE: 0x820364, FBPA_DISABLE: 0x820368,
  GPC_DEFECTIVE: 0x8205C4, FBP_DEFECTIVE: 0x8205CC, FBPA_DEFECTIVE: 0x8205D0,
  STATUS_OPT_GPC: 0x820C1C, STATUS_OPT_FBP: 0x820D38,
  TPC_DEF: 0x820760, TPC_DIS: 0x820C38, CTRL_TPC: 0x820A40,
  FBPA_DIS_EFF: 0x820C18, FBIO_DIS_EFF: 0x820C14,
};
const hx = o => "0x" + o.toString(16).toUpperCase().padStart(6, "0");
function auditWord(off, key) {
  const sh = D.shadow || {};
  if (sh[key] != null) return { v: sh[key] >>> 0, src: "shadow." + key };
  const hv = (D.hexnonzero || []).find(([o]) => o === off);
  if (hv) return { v: hv[1] >>> 0, src: "hex window @ " + hx(off) };
  return { v: null, src: "not captured in this dump" };
}
function tpcWord(g, which) {   // which: "def" | "dis"
  const sh = D.shadow || {};
  const hw = D.hexnonzero || [];
  if (which === "def") {
    // FF-region defect word is ground truth (valid for gated GPCs too)
    const fv = hw.find(([o]) => o === TPC_FFDEF[g]);
    if (fv) return { v: fv[1] >>> 0, src: "hex window @ " + hx(TPC_FFDEF[g]) + " — FF defective word" };
    const k = "TPC_DEFECTIVE_GPC" + g;
    if (sh[k] != null) return { v: sh[k] >>> 0, src: "shadow." + k };
  } else {
    const k = "TPC_DISABLE_GPC" + g;
    if (sh[k] != null) return { v: sh[k] >>> 0, src: "shadow." + k };
    const dv = hw.find(([o]) => o === AOFF.TPC_DIS + 4 * g);
    if (dv) return { v: dv[1] >>> 0, src: "hex window @ " + hx(AOFF.TPC_DIS + 4 * g) };
  }
  return { v: null, src: "not captured in this dump" };
}
function ffBlockRecords(blk) {
  // All chain-1 records for a fuse block, row-ordered. OPT_* record data is
  // NOT a raw disable mask: decoded mask = (data >> 3) & width.
  const out = [];
  for (const k of Object.keys(D.rows || {})) {
    const r = +k, v = D.rows[k];
    if (r < 222 || r > 487 || typeof v !== "number" || v === 0 || v === 0xFFFFFFFF) continue;
    const f = ffDecode(v);
    if (f.ch === 1 && f.blk === blk) out.push({ r, iff: f.iff, data: f.data });
  }
  out.sort((a, b) => a.r - b.r);
  return out;
}
function maskBits(m) { const b = []; for (let i = 0; i < 12; i++) if ((m >> i) & 1) b.push(i); return b; }
function timelineHtml(kind, unit) {
  const isGpc = kind === "gpc";
  const blk = isGpc ? 8 : 19;
  const width = isGpc ? 0xFF : 0xFFF;
  const nm = (isGpc ? "GPC" : "FBP") + unit;
  const recs = ffBlockRecords(blk);
  if (!recs.length) return "";
  let prev = null;
  let html = `<div class="note" style="margin-top:12px"><b>Record timeline — ${nm}</b> · ` +
    `chain 1 · block ${blk} · decoded mask = data &gt;&gt; 3 · last record wins</div><div class="tl">`;
  for (const rec of recs) {
    const mask = (rec.data >>> 3) & width;
    const bit = (mask >>> unit) & 1;
    let cls, st, sc;
    if (rec.iff) { cls = "s-iff"; sc = "n"; st = "IFF — invalidation record (refused by newer fuse logic)"; }
    else if (bit && prev !== 1) { cls = "s-dis"; sc = "d"; st = nm + " DISABLED here"; }
    else if (bit) { cls = "s-dis2"; sc = "d"; st = nm + " still disabled (no change)"; }
    else if (prev === 1) { cls = "s-en"; sc = "e"; st = nm + " RE-ENABLED here — this is the unlock record"; }
    else { cls = "s-none"; sc = "n"; st = nm + " not touched by this record"; }
    const last = rec === recs[recs.length - 1] && !rec.iff;
    html += `<div class="tlstep ${cls}"><span class="tlnode">${rec.iff ? "⚡" : "●"}</span>` +
      `<div class="tlbody">row <b>${rec.r}</b> · ${rec.iff ? "IFF" : "FF"} · ` +
      `data <span class="mono">0x${rec.data.toString(16).toUpperCase().padStart(4, "0")}</span> → ` +
      `mask <span class="mono">0x${mask.toString(16).toUpperCase()}</span> {${maskBits(mask).join(",")}}` +
      ` <span class="tlst ${sc}">${st}</span>` +
      (last ? ` <span class="tag">LAST — EFFECTIVE</span>` : "") + `</div></div>`;
    if (!rec.iff) prev = bit;
  }
  // reconcile with the live gate register
  const lw = auditWord(isGpc ? AOFF.GPC_DISABLE : AOFF.FBP_DISABLE,
                      isGpc ? "GPC_DISABLE" : "FBP_DISABLE");
  if (lw.v != null) {
    const lb = (lw.v >>> unit) & 1;
    const defW = auditWord(isGpc ? AOFF.GPC_DEFECTIVE : AOFF.FBP_DEFECTIVE,
                          isGpc ? "GPC_DEFECTIVE" : "FBP_DEFECTIVE");
    const unitDead = defW.v != null && ((defW.v >>> unit) & 1);
    const lastRec = recs.filter(r => !r.iff).pop();
    const fuseBit = lastRec ? (((lastRec.data >>> 3) & width) >>> unit) & 1 : null;
    const agree = fuseBit == null || fuseBit === lb;
    const gateNote = unitDead
      ? `— but ${nm} is DEFECTIVE silicon: the hardware gate dominates, the register value is moot.`
      : agree ? "— consistent with the last fuse record"
              : "DIFFERS from the fuse-replayed mask: the live register was changed after boot (unlock/clear). " +
                "The live register is what actually gates the unit right now.";
    html += `<div class="tlstep tlive"><span class="tlnode">▼</span><div class="tlbody">` +
      `live <span class="mono">${isGpc ? "GPC_DISABLE" : "FBP_DISABLE"}</span> = ` +
      `<span class="mono">${fmt(lw.v)}</span> → ${nm} register-level ` +
      `<b class="${lb ? "warn" : unitDead ? "bad" : "ok"}">${lb ? "DISABLED" : "ENABLED"}</b> ` +
      `<span class="tlst ${unitDead ? "d" : agree ? "e" : "d"}">${gateNote}</span></div></div>`;
  }
  return html + `</div>`;
}
function arow(sev, reg, off, w, bit, impact, interp, bv) {
  return { sev, reg, off, val: w.v, src: w.src,
           bit: bit == null ? null : bit,
           bitval: bv !== undefined ? bv
             : (bit == null || w.v == null) ? null : (w.v >>> bit) & 1,
           impact, interp };
}
function auditFor(kind, g, t) {
  const rows = [];
  let title, verdict;
  if (kind === "gpc") {
    title = "GPC" + g + " — full register audit";
    const d = auditWord(AOFF.GPC_DEFECTIVE, "GPC_DEFECTIVE");
    const z = auditWord(AOFF.GPC_DISABLE, "GPC_DISABLE");
    const dead = d.v != null && ((d.v >>> g) & 1);
    const dis  = z.v != null && ((z.v >>> g) & 1);
    if (dead) rows.push(arow(0, "GPC_DEFECTIVE", AOFF.GPC_DEFECTIVE, d, g,
      "HARDWARE GATE — unit cannot run, enforced in silicon. No burn, write or driver action can re-enable it.",
      `bit ${g} SET → GPC${g} is dead silicon (fuse-derived). No burn can re-enable it.`));
    if (dis) rows.push(arow(1, "GPC_DISABLE", AOFF.GPC_DISABLE, z, g,
      dead ? "GATES (already dead) — clearing this mask changes nothing; the silicon behind it is dead."
           : "BOOT GATE — holds the unit off at boot. This is THE unlock lever: clearing it (fuse append) re-enables the GPC.",
      dead ? `bit ${g} SET → floorsweep mask, consistent with the defect.`
           : `bit ${g} SET → floorswept at boot but silicon is healthy — re-enableable.`));
    const st = auditWord(AOFF.STATUS_OPT_GPC, "STATUS_OPT_GPC");
    if (st.v != null && ((st.v >>> g) & 1)) rows.push(arow(2, "STATUS_OPT_GPC",
      AOFF.STATUS_OPT_GPC, st, g,
      "OBSERVES ONLY — read-only boot latch. Proves what the fuse logic actually applied; gating itself comes from the mask registers, not this one.",
      `bit ${g} SET → fuse replay confirms GPC${g} disabled at boot (the latch to watch after a burn).`));
    const td = tpcWord(g, "def"), tz = tpcWord(g, "dis");
    const defM = td.v ?? 0, effM = (tz.v ?? defM) | defM;
    if (defM !== 0) rows.push(arow(0, "TPC_DEFECTIVE_GPC" + g, TPC_FFDEF[g], td, null,
      `HARDWARE GATE per TPC — each set bit permanently removes 2 SM (${pop(defM) * 2} SM lost) from this GPC. Irreversible.`,
      `defective TPCs {${bitsOf(defM).join(",")}} → ${pop(defM) * 2} SM permanently lost in this GPC`));
    const headroom = effM & ~defM;
    if (headroom !== 0) rows.push(arow(1, "TPC_DISABLE_GPC" + g, AOFF.TPC_DIS + 4 * g, tz, null,
      `BOOT GATE per TPC — each set bit holds 2 SM off (${pop(headroom) * 2} SM). Recoverable: this is the unlock headroom.`,
      `disabled-but-healthy TPCs {${bitsOf(headroom).join(",")}} → ${pop(headroom) * 2} SM unlock headroom`));
    const ct = auditWord(AOFF.CTRL_TPC + 4 * g, "CTRL_TPC_GPC" + g);
    if (ct.v != null && ct.v !== 0) rows.push(arow(2, "CTRL_TPC_GPC" + g, AOFF.CTRL_TPC + 4 * g, ct, null,
      "NO GATING on current state — control word loaded by fuse logic/driver at boot (0xFF = all 8 TPCs under control). " +
      "The effective TPC gate is the disable array at 0x820C38, not this register. Write-tested: rejected at DSOV=1, " +
      "cannot be changed now. Caution: on stock 170HX the driver writes 0xFF here as part of the floorsweep — but on a " +
      "running card all healthy TPCs still execute with 0xFF here, confirming it is a control bitmap, not the effective mask.",
      `non-zero control word ${fmt(ct.v)} captured (register is closed at DSOV=1 — informational)`));
    for (const rec of ffBlockRecords(8)) {
      const m = (rec.data >>> 3) & 0xFF;
      if (!((m >>> g) & 1)) continue;   // decoded mask must act on this GPC
      rows.push(arow(2, "FF record · OPT_GPC_DISABLE",
        null, { v: rec.data, src: "fuse row " + rec.r }, g,
        "DISABLES this unit at boot — the decoded mask (data>>3) holds bit " + g +
        ". To change behavior you must append a newer record (burn); editing registers won't override fuse history.",
        `${rec.iff ? "IFF (invalidation) " : "FF "}chain1·block8 data=0x${rec.data.toString(16).toUpperCase()} ` +
        `→ mask 0x${m.toString(16).toUpperCase()} bit ${g} SET → this record floorswept GPC${g} (last record per block wins)`, 1));
    }
    verdict = dead ? `<b class="bad">DEAD</b> — GPC${g} is dead silicon; every bit above is consistent with that.`
      : dis ? `<b class="warn">FLOORSWEPT</b> — GPC${g} is disabled by mask but silicon is healthy.`
      : (defM !== 0 || headroom !== 0)
        ? `<b class="ok">ACTIVE</b> — GPC${g} itself is enabled; ` +
          `defects live at TPC granularity inside it (see DEAD rows above).`
        : `<b class="ok">ACTIVE</b> — no register in this dump holds a bit against GPC${g}.`;
  } else if (kind === "tpc") {
    title = `GPC${g} · TPC${t} — full register audit (2 SM)`;
    const td = tpcWord(g, "def"), tz = tpcWord(g, "dis");
    const dead = td.v != null && ((td.v >>> t) & 1);
    const dis  = tz.v != null && ((tz.v >>> t) & 1);
    if (dead) rows.push(arow(0, "TPC_DEFECTIVE_GPC" + g, TPC_FFDEF[g], td, t,
      "HARDWARE GATE — these 2 SM cannot ever run. Enforced in silicon; no burn or write changes it.",
      `bit ${t} SET → TPC${t} in GPC${g} is dead silicon. Its 2 SM can never run.`));
    if (dis && !dead) rows.push(arow(1, "TPC_DISABLE_GPC" + g, AOFF.TPC_DIS + 4 * g, tz, t,
      "BOOT GATE — 2 SM held off at boot but silicon is healthy. Clearing this bit (fuse append) is the unlock action that gains 2 SM.",
      `bit ${t} SET but NOT defective → disabled-but-healthy: 2 SM recoverable headroom.`));
    if (dis && dead) rows.push(arow(2, "TPC_DISABLE_GPC" + g, AOFF.TPC_DIS + 4 * g, tz, t,
      "REDUNDANT GATE — the defect already blocks these 2 SM; this bit adds no further restriction and clearing it gains nothing.",
      `bit ${t} also set in the disable array — consistent with the defect.`));
    const gd = auditWord(AOFF.GPC_DEFECTIVE, "GPC_DEFECTIVE");
    const gz = auditWord(AOFF.GPC_DISABLE, "GPC_DISABLE");
    if (gd.v != null && ((gd.v >>> g) & 1)) rows.push(arow(3, "GPC_DEFECTIVE",
      AOFF.GPC_DEFECTIVE, gd, g,
      "GATES UPSTREAM (dead) — parent GPC is dead silicon; this TPC cannot run regardless of its own health.",
      `parent GPC${g} is defective — this TPC cannot run regardless of its own health.`));
    else if (gz.v != null && ((gz.v >>> g) & 1)) rows.push(arow(3, "GPC_DISABLE",
      AOFF.GPC_DISABLE, gz, g,
      "GATES UPSTREAM (re-enableable) — parent GPC is floorswept; this TPC's 2 SM are counted in the GPC-level unlock prize, not separately.",
      `parent GPC${g} is floorswept — this TPC only runs once the GPC itself is enabled.`));
    verdict = dead ? `<b class="bad">DEAD</b> — TPC${t} is defective silicon.`
      : dis ? `<b class="warn">HEADROOM</b> — healthy silicon, disabled; 2 SM recoverable.`
            : `<b class="ok">ENABLED</b> — no register holds a bit against this TPC.`;
  } else {   // fbp
    const f = g;
    title = "FBP" + f + " — full register audit";
    const fd = auditWord(AOFF.FBP_DEFECTIVE, "FBP_DEFECTIVE");
    const fz = auditWord(AOFF.FBP_DISABLE, "FBP_DISABLE");
    const dead = fd.v != null && ((fd.v >>> f) & 1);
    const dis = fz.v != null && ((fz.v >>> f) & 1);
    if (dead) rows.push(arow(0, "FBP_DEFECTIVE", AOFF.FBP_DEFECTIVE, fd, f,
      "HARDWARE GATE — the HBM stack behind this FBP is absent. −8 GB permanently; no burn can create silicon.",
      `bit ${f} SET → FBP${f} is dummy/missing silicon (no HBM stack). Never usable, −8 GB.`));
    if (dis) rows.push(arow(1, "FBP_DISABLE", AOFF.FBP_DISABLE, fz, f,
      dead ? "GATES (already dead) — clearing this mask gains nothing; there is no memory behind it."
           : "BOOT GATE — 8 GB held off at boot but silicon is healthy. Clearing it (fuse append) is the unlock action that gains 8 GB.",
      dead ? `bit ${f} SET → floorsweep consistent with the defect.`
           : `bit ${f} SET → floorswept but healthy — re-enableable (+8 GB).`));
    const st = auditWord(AOFF.STATUS_OPT_FBP, "STATUS_OPT_FBP");
    if (st.v != null && ((st.v >>> f) & 1)) rows.push(arow(2, "STATUS_OPT_FBP",
      AOFF.STATUS_OPT_FBP, st, f,
      "OBSERVES ONLY — read-only boot latch. Proves what the fuse logic applied; the gate itself is FBP_DISABLE.",
      `bit ${f} SET → fuse replay confirms FBP${f} disabled at boot.`));
    const ad = auditWord(AOFF.FBPA_DEFECTIVE, "FBPA_DEFECTIVE");
    const az = auditWord(AOFF.FBPA_DISABLE, "FBPA_DISABLE");
    const fbpaDead = [];
    for (const b of [2 * f, 2 * f + 1])
      if (ad.v != null && ((ad.v >>> b) & 1)) {
        fbpaDead.push(b);
        rows.push(arow(0, "FBPA_DEFECTIVE", AOFF.FBPA_DEFECTIVE, ad, b,
          `HARDWARE GATE — FBPA${b} (one 4 GB channel inside FBP${f}) is dead. Half of this FBP's capacity is permanently gone.`,
          `bit ${b} SET → FBPA${b} (inside FBP${f}) is defective.`));
      }
    for (const b of [2 * f, 2 * f + 1])
      if (az.v != null && ((az.v >>> b) & 1) && !fbpaDead.includes(b))
        rows.push(arow(1, "FBPA_DISABLE", AOFF.FBPA_DISABLE, az, b,
          `BOOT GATE — FBPA${b} channel held off but healthy; re-enableable together with its parent FBP (FBP+FBPA must be burned together).`,
          `bit ${b} SET → FBPA${b} floorswept but healthy.`));
    // effective disable mirrors: shown ONLY when the unit is defective (policy)
    if (fbpaDead.length || dead) {
      const ae = auditWord(AOFF.FBPA_DIS_EFF, "FBPA_DISABLE_EFF");
      const ie = auditWord(AOFF.FBIO_DIS_EFF, "FBIO_DIS_EFF");
      if (ae.v != null) rows.push(arow(2, "FBPA_DISABLE_EFF", AOFF.FBPA_DIS_EFF, ae, null,
        "HARDWARE-APPLIED MIRROR — the mask the memory controller actually enforces. Read-only consequence, not a burn target; confirms the defect is covered.",
        `hardware-applied FBPA disable ${fmt(ae.v)} — corroborates the defective FBPA bits.`));
      if (ie.v != null) rows.push(arow(2, "FBIO_DISABLE_EFF", AOFF.FBIO_DIS_EFF, ie, null,
        "HARDWARE-APPLIED MIRROR — FBIO is the complete mask (FBPA alone can miss bits). Read-only consequence; confirms full coverage of the defect.",
        `hardware-applied FBIO disable ${fmt(ie.v)} — FBIO is the complete mask (FBPA alone can miss bits).`));
    }
    for (const rec of ffBlockRecords(19)) {
      const m = (rec.data >>> 3) & 0xFFF;
      if (!((m >>> f) & 1)) continue;   // decoded mask must act on this FBP
      rows.push(arow(2, "FF record · OPT_FBP_DISABLE",
        null, { v: rec.data, src: "fuse row " + rec.r }, f,
        "DISABLES this unit at boot — the decoded mask (data>>3) holds bit " + f +
        ". To change behavior you must append a newer record (burn); register edits won't override fuse history.",
        `${rec.iff ? "IFF (invalidation) " : "FF "}chain1·block19 data=0x${rec.data.toString(16).toUpperCase()} ` +
        `→ mask 0x${m.toString(16).toUpperCase()} bit ${f} SET → this record floorswept FBP${f} (last record per block wins)`, 1));
    }
    verdict = dead ? `<b class="bad">DEAD</b> — FBP${f} is missing silicon.`
      : dis ? `<b class="warn">FLOORSWEPT</b> — FBP${f} disabled by mask but healthy.`
            : `<b class="ok">ACTIVE</b> — no register in this dump holds a bit against FBP${f}.`;
  }
  rows.sort((x, y) => (x.sev - y.sev) || ((x.off ?? 0) - (y.off ?? 0)));
  return { title, verdict, rows };
}
const SEV_TAG = ["DEAD", "DISABLED", "CORROBORATION", "CONTEXT"];
let auditOpener = null;  // B12: element to hand focus back to on close
function openAudit(kind, g, t) {
  const a = auditFor(kind, g, t);
  let html = `<button class="btn auditclose" id="auditclose">close ✕</button>` +
    `<h3>${esc(a.title)}</h3><div class="verdictline">${a.verdict}</div>`;
  if (!a.rows.length) {
    html += `<div class="note">No register in this dump holds a bit against this unit — ` +
      `nothing is disabling or killing it.</div>`;
  } else {
    html += `<table><tr><th>class</th><th>register</th><th>offset</th><th>value</th>` +
      `<th>bit</th><th>source</th><th>impact of this value</th><th>interpretation</th></tr>`;
    for (const r of a.rows) {
      html += `<tr class="sev${r.sev}"><td><span class="tag ${r.sev === 0 ? "b-tag" : ""}">` +
        `${SEV_TAG[r.sev]}</span></td><td class="mono">${esc(r.reg)}</td>` +
        `<td class="mono note">${r.off == null ? "—" : hx(r.off)}</td>` +
        `<td class="mono">${r.val == null ? "—" : fmt(r.val)}</td>` +
        `<td class="mono">${r.bit == null ? "word" : r.bit + " = " + r.bitval}</td>` +
        `<td class="note">${esc(r.src)}</td><td>${r.impact}</td><td>${r.interp}</td></tr>`;
    }
    html += `</table>`;
  }
  if (kind === "gpc" || kind === "fbp") html += timelineHtml(kind, g);
  document.getElementById("audit").innerHTML = html;
  auditOpener = document.activeElement;
  document.getElementById("auditbg").classList.add("open");
  document.getElementById("auditclose").onclick = closeAudit;
  document.getElementById("auditclose").focus();  // B12: focus into the dialog
}
function closeAudit() {
  document.getElementById("auditbg").classList.remove("open");
  const el = auditOpener && document.contains(auditOpener) ? auditOpener : null;
  // Chromium keeps focus on the just-hidden close button and body.focus() is a
  // no-op over it — blur first, then restore to the opener.
  const cur = document.activeElement;
  if (cur && cur !== el && cur.blur) cur.blur();
  if (el) el.focus();
  auditOpener = null;
}
document.addEventListener("click", e => {
  if (e.target.closest("#auditclose")) return;
  if (e.target.id === "auditbg") { closeAudit(); return; }
  const el = e.target.closest("[data-audit]");
  if (el) {
    const p = el.dataset.audit.split(":");
    openAudit(p[0], +p[1], p[2] == null ? null : +p[2]);
  }
});
document.addEventListener("keydown", e => {
  const bg = document.getElementById("auditbg");
  if (e.key === "Escape") { closeAudit(); return; }
  if (e.key !== "Tab" || !bg.classList.contains("open")) return;
  // B12: keep Tab cycling inside the open dialog (background stays untabbable).
  const f = [...bg.querySelectorAll("button, [href], input, select, textarea, " +
    "[tabindex]:not([tabindex='-1'])")].filter(el => el.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  const inside = bg.contains(document.activeElement);
  if (e.shiftKey && (!inside || document.activeElement === first)) {
    e.preventDefault(); last.focus();
  } else if (!e.shiftKey && (!inside || document.activeElement === last)) {
    e.preventDefault(); first.focus();
  }
});

// shadow registers -------------------------------------------------------
function renderShadow() {
  const SHOFF = {
    GPC_DISABLE: [0x820350, "floorsweep — GPCs disabled at boot"],
    GPC_DEFECTIVE: [0x8205C4, "dead GPCs — real silicon, cannot be re-enabled"],
    FBP_DISABLE: [0x820364, "floorsweep — FBPs disabled at boot"],
    FBP_DEFECTIVE: [0x8205CC, "dummy stacks — missing silicon"],
    FBPA_DISABLE: [0x820368, "per-FBPA floorsweep"],
    FBPA_DEFECTIVE: [0x8205D0, "per-FBPA defects"],
    FBIO_DEFECTIVE: [0x8205D4, "per-FBIO defects (memory subpartitions)"],
    NVLINK_DISABLE: [0x820684, "NVLink floorsweep"],
    NVLINK_DEFECTIVE: [0x82068C, ""],
    PES_DEFECTIVE: [0x820698, "dead PES units"],
    ROP_L2_DEFECTIVE: [0x8205E8, "dead ROP/L2 slices"],
    SYS_PIPE_DEFECTIVE: [0x8203AC, "dead sys-pipe units"],
    STATUS_OPT_GPC: [0x820C1C, "replayed GPC option status — the latch to watch after a burn"],
    STATUS_OPT_FBP: [0x820D38, "replayed FBP option status — the latch to watch after a burn"],
  };
  const sh = D.shadow || {};
  let html = "<table><tr><th>register</th><th>offset</th><th>value</th><th>bits set</th><th>meaning</th></tr>";
  for (const [k, [off, note]] of Object.entries(SHOFF)) {
    const v = sh[k];
    html += `<tr data-key="shadow.${k}"><td class="mono">${k}</td>` +
      `<td class="mono note">0x${off.toString(16).toUpperCase().padStart(6, "0")}</td>` +
      `<td class="mono ${v === 0 && /DISABLE|STATUS_OPT/.test(k) ? "bad" : ""}">${v == null ? "—" : fmt(v)}</td>` +
      `<td class="mono">{${bitsOf(v).join(",")}}</td><td class="note">${note}</td></tr>`;
  }
  for (let i = 0; i < 8; i++) {
    const d = sh["TPC_DEFECTIVE_GPC" + i];
    const z = sh["TPC_DISABLE_GPC" + i];
    const legacy = sh["TPC_DISABLE_" + i];   // pre-2026-11-19: held 0x820760
    if (d == null && z == null && legacy == null) continue;
    const dv = d != null ? d : legacy;
    html += `<tr><td class="mono">TPC_DEFECTIVE_GPC${i}</td>` +
      `<td class="mono note">0x${(0x820760 + i * 4).toString(16).toUpperCase()}</td>` +
      `<td class="mono">${dv == null ? "—" : fmt(dv)}</td>` +
      `<td class="mono">{${bitsOf(dv).join(",")}}</td>` +
      `<td class="note">dead TPCs in GPC${i} (bit = TPC, 2 SM each)</td></tr>`;
    if (z != null) html += `<tr><td class="mono">TPC_DISABLE_GPC${i}</td>` +
      `<td class="mono note">0x${(0x820C38 + i * 4).toString(16).toUpperCase()}</td>` +
      `<td class="mono">${fmt(z)}</td><td class="mono">{${bitsOf(z).join(",")}}</td>` +
      `<td class="note">effective TPC disable — extra bits over defective = unlock headroom</td></tr>`;
  }
  document.getElementById("shadow").innerHTML = html + "</table>";
}

// fuse rows --------------------------------------------------------------
const pairedWith = {};
function computePairs() {
  for (const k of Object.keys(pairedWith)) delete pairedWith[k];
  const keys = Object.keys(D.rows || {}).map(Number).sort((a, b) => a - b);
  for (const r of keys) {
    if (r % 2 === 0) {
      const a = D.rows[r], b = D.rows[r + 1];
      if (typeof a === "number" && typeof b === "number" && a === b) {
        pairedWith[r] = r + 1; pairedWith[r + 1] = r;
      }
    }
  }
}
let rowFilter = "nonblank", rowSearch = "", selRow = null;
const FILTERS = [["nonblank", "Non-blank"], ["records", "FF records"], ["all", "All rows"],
                 ["MAIN", "MAIN"], ["FPF", "FPF"], ["FF", "FF"]];
function wireRowBtns() {
  const rowBtns = document.getElementById("rowbtns");
  rowBtns.innerHTML = FILTERS.map(([k, l]) =>
    `<button class="btn ${k === rowFilter ? "on" : ""}" data-f="${k}">${l}</button>`).join("");
  rowBtns.querySelectorAll("button").forEach(b => b.onclick = () => {
    rowFilter = b.dataset.f;
    rowBtns.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
    renderRows();
  });
  document.getElementById("search").oninput = e => {
    rowSearch = e.target.value.trim().toLowerCase(); renderRows(); };
}
function rowVisible(r) {
  const v = D.rows[r];
  const blank = (typeof v !== "number") || v === 0 || v === 0xFFFFFFFF;
  if (rowFilter === "nonblank" && blank) return false;
  if (rowFilter === "records" && !(regionOf(r).name === "FF" && !blank)) return false;
  if (["MAIN", "FPF", "FF"].includes(rowFilter) && regionOf(r).name !== rowFilter) return false;
  if (rowSearch) {
    const hay = (r + " " + (typeof v === "number" ? fmt(v) : String(v))).toLowerCase();
    if (!hay.includes(rowSearch)) return false;
  }
  return true;
}
function renderRows() {
  computePairs();
  const keys = Object.keys(D.rows || {}).map(Number).sort((a, b) => a - b);
  const vis = keys.filter(rowVisible);
  let html = "<table><tr><th>row</th><th>region</th><th>value</th><th>decode</th><th>notes</th></tr>";
  for (const r of vis) {
    const v = D.rows[r];
    const reg = regionOf(r);
    const blank = (typeof v !== "number") || v === 0 || v === 0xFFFFFFFF;
    const dec = [];
    if (reg.name === "FF" && typeof v === "number" && !blank) {
      const f = ffDecode(v);
      dec.push(`<span class="tag">${f.iff ? "IFF" : "FF"} ch${f.ch}·b${f.blk}·d0x${f.data.toString(16)}</span>`);
    }
    const notes = [];
    if (r === 0 && v === 0x53557C3D) notes.push(`<span class="tag">known-good signature</span>`);
    if (pairedWith[r] !== undefined) notes.push(`<span class="tag">pair ≡ ${pairedWith[r]}</span>`);
    if (typeof v !== "number") notes.push(`<span class="tag">${esc(v)}</span>`);
    html += `<tr class="rowline ${r === selRow ? "sel" : ""} ${blank ? "blankrow" : ""}" data-r="${r}">` +
      `<td class="mono">${r}</td><td class="reg-${reg.name}">${reg.name}</td>` +
      `<td class="mono">${typeof v === "number" ? fmt(v) : esc(v)}</td>` +
      `<td>${dec.join(" ")}</td><td>${notes.join(" ")}</td></tr>`;
  }
  document.getElementById("rowtable").innerHTML = html + "</table>";
  document.getElementById("rowcount").textContent = `${vis.length} rows shown`;
  document.getElementById("rowtable").querySelectorAll("tr.rowline").forEach(tr =>
    tr.onclick = () => { selRow = +tr.dataset.r; renderRows(); renderDetail(selRow); });
  syncActiveRow();
}

// B16: keyboard access to the row table. The scroll container is a single tab
// stop (roving active row) instead of 488 tab stops — see design note in
// evidence/05-fix4.md. Enter/Space selects the active row exactly like a click.
let activeRow = null;
function syncActiveRow() {
  const rows = [...document.getElementById("rowtable").querySelectorAll("tr.rowline")];
  const has = r => rows.some(tr => +tr.dataset.r === r);
  if (has(selRow)) activeRow = selRow;
  else if (!has(activeRow)) activeRow = rows.length ? +rows[0].dataset.r : null;
  rows.forEach(tr => tr.classList.toggle("rowact", +tr.dataset.r === activeRow));
}
(function () {
  const box = document.getElementById("rowtable");
  box.addEventListener("keydown", e => {
    const rows = [...box.querySelectorAll("tr.rowline")];
    if (!rows.length) return;
    let i = rows.findIndex(tr => +tr.dataset.r === activeRow);
    if (i < 0) i = 0;
    let j = null;
    if (e.key === "ArrowDown") j = Math.min(i + 1, rows.length - 1);
    else if (e.key === "ArrowUp") j = Math.max(i - 1, 0);
    else if (e.key === "Home") j = 0;
    else if (e.key === "End") j = rows.length - 1;
    else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      selRow = +rows[i].dataset.r; renderRows(); renderDetail(selRow);
      return;
    } else return;
    e.preventDefault();
    activeRow = +rows[j].dataset.r;
    rows.forEach(tr => tr.classList.toggle("rowact", +tr.dataset.r === activeRow));
    rows[j].scrollIntoView({ block: "nearest" });
  });
})();
function renderDetail(r) {
  const v = D.rows[r], el = document.getElementById("detail");
  el.style.display = "block";
  if (typeof v !== "number") { el.innerHTML = `<b class="mono">row ${r}</b> — ${esc(v)}`; return; }
  const reg = regionOf(r);
  let cells = "";
  for (let i = 31; i >= 0; i--) {
    const set = (v >>> i) & 1;
    cells += `<span class="bitcell ${set ? "bitset" : ""}" title="bit ${i}">${i}</span>`;
  }
  let extra = "";
  if (reg.name === "FF" && v !== 0 && v !== 0xFFFFFFFF) {
    const f = ffDecode(v);
    extra += `<div class="note" style="margin-top:4px">FF record decode (verified field map): ` +
      `chain=<span class="mono">${f.ch}</span> ` +
      (f.iff ? `<b class="warn">IFF (invalidation)</b> ` : "") +
      `block=<span class="mono">${f.blk}</span> ` +
      `data=<span class="mono">0x${f.data.toString(16).toUpperCase().padStart(4, "0")}</span>` +
      (f.ch === 1 && f.blk === 19 ? " → FBP_DISABLE" : "") +
      (f.ch === 1 && f.blk === 8 ? " → GPC_DISABLE" : "") +
      ` · last record per block wins</div>`;
  }
  el.innerHTML = `<b class="mono">row ${r}</b> <span class="tag">${reg.name}</span> ` +
    `<span class="mono">${fmt(v)}</span> ${pairedWith[r] !== undefined ? `<span class="note">(pair of row ${pairedWith[r]})</span>` : ""}` +
    `<div class="note">${reg.desc}</div><div class="bits">${cells}</div>${extra}`;
}

function renderInterp() {
  document.getElementById("interp").innerHTML = (D.interpretation || [])
    .map(l => `<div style="margin:2px 0">• ${esc(l)}</div>`).join("");
}
function renderDmesg() {
  const hl = l => /GFW|GfwBoot|RmInitAdapter|failed|ERROR/i.test(l);
  document.getElementById("dmesg").innerHTML = (D.dmesg_tail || "")
    .split("\n").map(l => hl(l) ? `<span class="hl">${esc(l)}</span>` : esc(l)).join("\n");
}
function renderHex() {
  const t = document.getElementById("hextable");
  const draw = q => {
    const hex = D.hexnonzero || [];
    const vis = hex.filter(([o, v]) => !q || (fmt(o) + " " + fmt(v)).toLowerCase().includes(q));
    let html = "<table><tr><th>offset</th><th>value</th><th>bits</th></tr>";
    for (const [o, v] of vis.slice(0, 600))
      html += `<tr><td class="mono">0x${o.toString(16).toUpperCase().padStart(6, "0")}</td>` +
        `<td class="mono">${fmt(v)}</td><td class="mono note">{${bitsOf(v).join(",")}}</td></tr>`;
    t.innerHTML = html + "</table>" +
      (vis.length > 600 ? `<div class="note" style="padding:6px">showing first 600 of ${vis.length}</div>` : "");
  };
  draw("");
  document.getElementById("hexsearch").oninput = e => draw(e.target.value.trim().toLowerCase());
}

function renderLive() {  // cheap: everything except rows/dmesg/hex/interp
  renderMeta(); renderStatus(); renderVerdict(); renderTopo(); renderTpc();
  renderProposedBurns();
  renderShadow();
}
function renderAll() {
  renderLive(); renderRows(); renderInterp(); renderDmesg(); renderHex();
}

// ---------------------------------------------------------------- tabs
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(b => {
    const on = b.dataset.tab === name;
    b.classList.toggle("on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");  // B13
    b.tabIndex = on ? 0 : -1;                                // B13: roving tab stop
  });
  document.querySelectorAll(".tabpane").forEach(p =>
    p.classList.toggle("on", p.id === "tab-" + name));
  try { history.replaceState(null, "", "#" + name); } catch (e) {}
  if (window.__onTabChange) window.__onTabChange(name);
}
document.querySelectorAll(".tab").forEach(b =>
  b.onclick = () => switchTab(b.dataset.tab));
// B13: ArrowLeft/Right (plus Home/End) move focus and activation on the tablist.
document.querySelector(".tabs").addEventListener("keydown", e => {
  const tabs = [...document.querySelectorAll(".tab")];
  const i = tabs.indexOf(document.activeElement);
  if (i < 0) return;
  let j = null;
  if (e.key === "ArrowRight") j = (i + 1) % tabs.length;
  else if (e.key === "ArrowLeft") j = (i - 1 + tabs.length) % tabs.length;
  else if (e.key === "Home") j = 0;
  else if (e.key === "End") j = tabs.length - 1;
  if (j === null) return;
  e.preventDefault();
  tabs[j].focus();
  switchTab(tabs[j].dataset.tab);
});

// ---------------------------------------------------------------- boot
renderStateBtns();
fetchStock();
wireRowBtns();
renderAll();
const initialTab = (location.hash || "").replace("#", "");
if (["glitch", "drivers", "gpu"].includes(initialTab)) switchTab(initialTab);

// Frozen tab bar: publish the sticky container's height as --sticktop so the
// sticky side rails park below it instead of overlapping. Feature-checked —
// without ResizeObserver the livebar just sticks at 0 (previous behaviour).
const sticktopEl = document.querySelector(".sticktop");
if (sticktopEl && window.ResizeObserver) {
  const setSticktop = () => document.documentElement.style.setProperty(
      "--sticktop", sticktopEl.getBoundingClientRect().height + "px");
  new ResizeObserver(setSticktop).observe(sticktopEl);
  setSticktop();
}
__LIVEBOOT__
</script>
</body>
</html>
"""

LIVEBAR = """
  <div class="card" id="livebar">
    <div class="flexline" style="margin:0">
      <span id="liveind" class="pill warnl" aria-live="polite">connecting…</span>
      <span class="pill">GPU:
        <select id="gpusel" title="select which GA100 the Fuse Explorer targets">
          <option value="">default</option>
        </select></span>
      <span class="pill">page poll:
        <select id="pollsel">
          <option value="0" selected>off</option>
          <option value="1000">1s</option>
          <option value="2000">2s</option>
          <option value="5000">5s</option>
        </select></span>
      <button class="btn" id="fulldump">⟳ Run full dump</button>
      <span class="note">full dump issues fuse CMD_READs — do not run it while a
        glitch/burn tool is driving the card. The heavy register redraw is off
        by default; the interpretation feed, dmesg tail, campaign log and GPU
        monitor keep refreshing on their own.</span>
    </div>
    <div class="card verdict warnv" id="live-follow" style="display:none;margin-top:8px"></div>
    <div class="card verdict warnv" id="boundpanel" style="display:none;margin-top:8px"></div>
    <div class="card verdict warnv" id="boundbar" style="display:none;margin-top:8px;padding:6px 14px"></div>
    <div id="feed" class="mono" aria-live="polite"></div>
  </div>
"""

LIVEBOOT = r"""
// ---------------------------------------------------------------- live layer
(function () {
  const ind = document.getElementById("liveind");
  const el_cardless = document.getElementById("cardless");
  const feedEl = document.getElementById("feed");
  const feedLines = [];
  let prev = null, timer = null;
  // History browser state (task 23): HIST = {dir} while an explicitly
  // picked saved dump is on screen. The DEFAULT face is the present card's
  // own data only — another card's dump never renders unless the user
  // opens the picker. liveCard tracks the last /api/live verdict so the
  // empty state can name the card's serial.
  let HIST = null;
  let liveCard = null;

  function note(msg, cls) { ind.textContent = msg; ind.className = "pill " + (cls || ""); }
  function cardlessBanner(msg) {
    // card-less boot is a supported state: one honest banner until a card
    // appears (self-heals on the next successful poll). The saved-dump
    // panels below stay rendered — setStale("absent") labels and dims
    // them instead of blanking them (browsing saved dumps card-less is
    // a feature; masquerading as live is the defect).
    if (!el_cardless || !/no GA100/i.test(msg)) return;
    el_cardless.innerHTML = `<b class="bad">⚠ ${esc(msg)}</b> — no card in ` +
      `the slot. Insert a GA100 and the console self-detects it on the next ` +
      `poll; endpoints answer their honest error meanwhile and the Support ` +
      `bundle stays available.`;
    el_cardless.style.display = "";
  }
  function hideCardless() {
    if (el_cardless) el_cardless.style.display = "none";
  }
  function setStale(reason, curSerial) {
    // the panels below show a SAVED dump, not the present card's live
    // state: name the source (serial + dump ts), dim the wrapper, and
    // re-render the header meta with the SAVED DUMP OF prefix.
    if (!(D.row_count > 0)) return;   // empty seed: nothing to label
    STALE = { reason: reason, curSerial: curSerial || null };
    const strip = document.getElementById("dumpsrc");
    if (strip) {
      const tail = reason === "absent" ? "no GA100 present"
        : "different card present (serial " + esc(curSerial || "unknown") + ")";
      strip.innerHTML = `<b class="warn">showing saved dump of card serial ` +
        `${esc(D.serial || "unknown")} (dumped ${esc(D.started || "?")})</b> — ${tail}`;
      strip.style.display = "";
    }
    const w = document.getElementById("dumpwrap");
    if (w) w.classList.add("stale");
    renderMeta();
  }
  function clearStale() {
    if (!STALE) return;
    STALE = null;
    const strip = document.getElementById("dumpsrc");
    if (strip) strip.style.display = "none";
    const w = document.getElementById("dumpwrap");
    if (w) w.classList.remove("stale");
    renderMeta();
  }
  // ---- empty state + saved-dumps history browser ----
  function updateEmptyState() {
    // no dump data on screen and not browsing history -> clean empty face:
    // hide the dump-derived panels, show the reason + a browse affordance.
    const el = document.getElementById("nodata");
    if (!el) return;
    const empty = !(D.row_count > 0) && !HIST;
    el.style.display = empty ? "" : "none";
    const w = document.getElementById("dumpwrap");
    if (w) w.style.display = empty ? "none" : "";
    if (!empty) return;
    const who = liveCard && liveCard.present
      ? `No dump yet for this card (serial ${esc(liveCard.serial || "unknown")}).`
      : "No GA100 present — nothing live to show.";
    el.innerHTML = `<b class="warn">${who}</b> ` +
      `<button class="btn" id="nodata-browse">Browse saved dumps</button>`;
    document.getElementById("nodata-browse").onclick = openPicker;
  }
  function closePicker() {
    document.getElementById("dpbg").classList.remove("open");
  }
  async function openPickerList() {
    const list = document.getElementById("dumplist");
    list.innerHTML = '<span class="note">loading saved dumps…</span>';
    let arr;
    try { arr = await jget("/api/dumps"); }
    catch (e) { list.innerHTML = '<span class="bad">⚠ ' + esc(String(e)) + "</span>"; return; }
    if (!arr.length) { list.innerHTML = '<span class="note">no saved dumps yet.</span>'; return; }
    list.innerHTML = arr.map(e => {
      if (e.unreadable) return `<div class="dumptrow unreadable mono">${esc(e.dir)} — ` +
        `unreadable (${esc(String(e.unreadable))})</div>`;
      const flags = [];
      if (e.driver_bound) flags.push("driver-bound");
      if (e.verified === false) flags.push("UNVERIFIED");
      return `<div class="dumptrow" data-dir="${esc(e.dir)}">` +
        `<b class="mono">${esc(e.serial || "no serial")}</b> · ` +
        `<span class="mono">${esc(e.dumped || "?")}</span>` +
        (flags.length ? ` · <span class="warn">${flags.join(" · ")}</span>` : "") +
        ` · ${e.row_count} rows` +
        (e.current ? ' <span class="tag ok-tag">(current card)</span>' : "") +
        `</div>`;
    }).join("");
    list.querySelectorAll(".dumptrow[data-dir]").forEach(el =>
      el.onclick = () => pickDump(el.dataset.dir));
  }
  async function openPicker() {
    // modal popup (like the unit audit): reachable from every tab, the
    // backdrop click and Escape close it — no longer an inline card that
    // only exists inside the Fuse Explorer pane
    const bg = document.getElementById("dpbg");
    bg.classList.add("open");
    bg.scrollTop = 0;
    await openPickerList();
  }
  function applyDumpData(j) {
    const hex = j.hexnonzero; delete j.hexnonzero;
    Object.assign(D, j); D.hexnonzero = hex || [];
    renderAll(); renderPlan(); renderQueue();
    refreshBurnFormDefaults();   // burn-form targets follow the newly loaded dump
  }
  async function pickDump(dir) {
    try {
      const j = await jget("/api/dumps/get?dir=" + encodeURIComponent(dir));
      if (j.error) { note("⚠ " + j.error, "badl"); return; }
      HIST = { dir: dir };
      applyDumpData(j);
      showHistStrip(j);
      closePicker();
      note("browsing saved dump — " + dir, "warnl");
    } catch (e) { note("⚠ saved dump failed (" + e + ")", "badl"); }
  }
  function showHistStrip(j) {
    // task 22's stale chrome, repurposed for explicit history: dim +
    // label the panels, name the exact dump, offer the way back.
    STALE = { reason: "history", curSerial: null };
    const w = document.getElementById("dumpwrap");
    w.style.display = "";
    w.classList.add("stale");
    const strip = document.getElementById("dumpsrc");
    strip.innerHTML = `<b class="warn">Browsing saved dump — serial ` +
      `${esc(j.serial || "unknown")}, dumped ${esc(j.started || "?")}</b> ` +
      `<button class="btn" id="histback">← Back to current</button>`;
    strip.style.display = "";
    document.getElementById("histback").onclick = backToCurrent;
    renderMeta();
    updateEmptyState();
  }
  async function backToCurrent() {
    // leave history mode: restore the default resolution — the present
    // card's own newest saved dump read back from disk (no new sweep),
    // else the pristine seed (empty state when the card has no dump).
    HIST = null;
    STALE = null;
    document.getElementById("dumpsrc").style.display = "none";
    document.getElementById("dumpwrap").classList.remove("stale");
    try {
      const arr = await jget("/api/dumps");
      const cur = (arr || []).find(e => e.current && !e.unreadable);
      if (cur) {
        const j = await jget("/api/dumps/get?dir=" + encodeURIComponent(cur.dir));
        if (j.error) throw new Error(j.error);
        applyDumpData(j);
        note("showing this card's newest saved dump — " + j.started, "okl");
      } else {
        D = JSON.parse(JSON.stringify(SEED));
        renderAll(); renderPlan(); renderQueue();
        refreshBurnFormDefaults();
      }
    } catch (e) { note("⚠ back-to-current failed (" + e + ")", "badl"); }
    updateEmptyState();
    fetchLive(false);
  }
  function followNote(id, n) {
    // amber honesty banner: console follows a card other than the configured BDF
    const el = document.getElementById(id);
    if (!el) return;
    if (n) { el.textContent = "⚠ " + n; el.style.display = ""; }
    else el.style.display = "none";
  }
  function feed(line) {
    const ts = new Date().toTimeString().slice(0, 8);
    feedLines.unshift(ts + "  " + line);
    if (feedLines.length > 40) feedLines.pop();
    feedEl.innerHTML = feedLines.map(esc).join("<br>");
  }
  function flash(key) {
    const el = document.querySelector('[data-key="' + key + '"]');
    if (el) { el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash"); }
  }
  function diff(j) {
    if (!prev) { prev = j; return; }
    for (const grp of ["status", "shadow"]) {
      const a = prev[grp] || {}, b = j[grp] || {};
      for (const k of Object.keys(b)) {
        if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) {
          const o = a[k], n = b[k];
          feed(`${grp}.${k}: ${typeof o === "number" ? fmt(o) : o} → ${typeof n === "number" ? fmt(n) : n}`);
          flash(grp + "." + k);
        }
      }
    }
    prev = j;
  }
  // ---- GPU selection (Fuse Explorer target) ----
  const selBdf = () => localStorage.getItem("ga100.bdf") || "";
  const bdfQs = () => { const b = selBdf(); return b ? "?bdf=" + encodeURIComponent(b) : ""; };
  async function populateGpuSel() {
    try {
      const j = await jget("/api/gpus");
      const sel = document.getElementById("gpusel");
      const gpus = j.gpus || [];
      // detected cards only — a configured-but-absent BDF is never an
      // option; the effective default carries the (default) suffix
      sel.innerHTML = gpus.map(g => `<option value="${esc(g.bdf)}">${esc(g.bdf)}` +
        ` · ${esc(g.driver || "no driver")}` +
        (g.goldilocks ? " · GOLDILOCKS" : "") +
        (g.bdf === j.default ? " (default)" : "") +
        (g.error ? " · " + esc(g.error.slice(0, 40)) : "") + `</option>`).join("");
      const saved = selBdf();
      sel.value = (saved && gpus.some(g => g.bdf === saved)) ? saved : (j.default || "");
      followNote("live-follow", j.default_note);
      sel.onchange = () => {
        if (sel.value) localStorage.setItem("ga100.bdf", sel.value);
        else localStorage.removeItem("ga100.bdf");
        note("GPU target switched to " + (sel.value || "default") +
             " — reloading…", "warnl");
        fetchLive(true); fullDump();
      };
    } catch (e) { /* static mode or service error: keep default only */ }
  }
  async function fetchLive(heavy) {
    try {
      const r = await fetch("/api/live" + bdfQs(), { cache: "no-store" });
      const j = await r.json();
      followNote("live-follow", j.default_note);
      if (j.paused) { note("⏸ " + j.paused, "warnl"); hideCardless();
        liveCard = { present: true, serial: j.serial || null };
        if (!HIST && STALE && STALE.reason === "absent") clearStale();  // card is back (serial unknown while bound: no comparison, no alarm)
        boundPanel(j); updateEmptyState(); return; }
      boundHide();
      if (j.error) { note("⚠ " + j.error, "badl"); cardlessBanner(j.error);
        if (/no GA100/i.test(j.error)) {
          liveCard = { present: false, serial: null };
          if (!HIST) setStale("absent", null);   // history strip already labels the view
        }
        updateEmptyState(); return; }
      hideCardless();
      // /api/live carries the PRESENT card's serial (task 20): compare it
      // with the displayed dump's serial — a mismatch must never render
      // the saved dump as present-tense live data. While browsing history
      // the strip already names the source; only the live bits refresh.
      const curSerial = j.serial || null;
      liveCard = { present: true, serial: curSerial };
      D.status = j.status; D.shadow = j.shadow;
      // task 51: Allspark readouts + never-write list ride the live payload
      // (service.enrich_readouts) — refresh the provenance-tagged tiles.
      D.readouts = j.readouts; D.never_write = j.never_write;
      renderNeverWrite(); renderAllsparkTiles();
      if (j.tpc !== undefined) D.tpc = j.tpc;
      if (j.driver !== undefined) D.driver = j.driver;
      if (j.bdf !== undefined) D.bdf = j.bdf;
      if (!HIST) {
        const staleNow = !!(curSerial && D.serial && curSerial !== D.serial);
        if (!staleNow) D.started = j.ts;   // keep the SAVED dump's ts visible while labelled
        if (staleNow) setStale("different", curSerial); else clearStale();
      }
      diff(j);
      renderLive();  // cheap cards refresh on the light poll too; rows/hex stay heavy-only
      renderPlan(); renderQueue();
      updateEmptyState();
      note("● live — " + j.ts, "okl");
    } catch (e) { note("⚠ service unreachable (" + e + ")", "badl"); }
  }
  // ---- task 51: Allspark-sourced surfaces (provenance tag on every tile) ----
  function renderAllsparkTiles() {
    const el = document.getElementById("t51-gpu-readouts-body");
    if (!el) return;
    const r = D.readouts;
    if (!r || (!r.GFW_BOOT && !r.FEAT_READOUT_1)) {
      el.innerHTML = "awaiting first live poll (/api/live readouts)…"; return;
    }
    const tile = (name, item, color) =>
      `<div class="card stat" style="border-color:${color}">` +
      `<div class="k">${name}</div>` +
      `<div class="v mono" style="color:${color}">` +
      `0x${(item.value >>> 0).toString(16).toUpperCase().padStart(8, "0")}</div>` +
      `<div class="note">${esc(item.note || "")}</div>` +
      `<span class="pill warnl">The Lab · unverified here</span></div>`;
    const g = r.GFW_BOOT, f = r.FEAT_READOUT_1;
    const gcol = g && g.value === 0x3FF ? "var(--ok)"
               : g && g.value === 0x1 ? "var(--warn)" : "var(--fg-subtle)";
    const fcol = f && f.value === 0 ? "var(--ok)"
               : f && f.value === 0x016DB6ED ? "var(--bad)" : "var(--fg-subtle)";
    el.innerHTML = `<div class="flexline" style="gap:10px">` +
      (g ? tile("GFW_BOOT", g, gcol) : "") +
      (f ? tile("FEAT_READOUT_1", f, fcol) : "") + `</div>` +
      (g && g.value === 0x1
        ? `<div class="note" style="margin-top:6px">0x1 is the FWSEC ` +
          `failed-secure-boot-step marker — <b>not proof of a brick</b>; ` +
          `diagnose via FB trained + BAR0 responsive first.</div>` : "");
  }
  function renderNeverWrite() {
    const el = document.getElementById("t51-neverwrite-body");
    if (!el) return;
    const list = D.never_write;
    if (!list || !list.length) {
      el.innerHTML = "awaiting first live poll (/api/live never_write)…"; return;
    }
    el.innerHTML = list.map(e =>
      `<div style="margin-top:6px"><b class="mono">${esc(e.register)}</b> ` +
      `<span class="note mono">${esc(e.offset)} = ${esc(e.value)}</span> — ` +
      `${esc(e.effect)} ` +
      (e.enforced ? `<span class="pill okl">guarded by console</span>` : "") +
      ` <span class="pill warnl">The Lab · unverified here</span></div>`).join("");
  }
  async function fullDump() {
    const b = document.getElementById("fulldump");
    b.disabled = true; note("running full dump… (rows 0–487 + hex window)", "warnl");
    try {
      const r = await fetch("/api/full" + bdfQs(), { cache: "no-store" });
      const j = await r.json();
      if (j.error) { note("⚠ " + j.error, "badl"); return; }
      const hex = j.hexnonzero; delete j.hexnonzero;
      Object.assign(D, j); D.hexnonzero = hex || [];
      if (HIST) { HIST = null; clearStale(); }  // a fresh dump of the present card replaces any browsed one
      renderAll();
      renderPlan(); renderQueue();
      refreshBurnFormDefaults();
      fetchStock();   // this dump may have just seeded the stock baseline
      note("full dump loaded — " + j.started, "okl");
    } catch (e) { note("⚠ full dump failed (" + e + ")", "badl"); }
    finally { b.disabled = false; updateEmptyState(); }
  }
  document.getElementById("fulldump").onclick = fullDump;
  document.getElementById("dumpsbtn").onclick = e => { e.preventDefault(); openPicker(); };
  document.getElementById("dumppicker-close").onclick = closePicker;
  document.getElementById("dpbg").addEventListener("click", e => {
    if (e.target.id === "dpbg") closePicker();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" &&
        document.getElementById("dpbg").classList.contains("open"))
      closePicker();
  });
  // ---- saved-dump dedupe: identical fuse content -> keep oldest, delete rest
  const kb = n => n >= 1048576 ? (n / 1048576).toFixed(1) + " MB"
              : n >= 1024 ? (n / 1024).toFixed(0) + " KB" : n + " B";
  function renderDedupe(j, applied) {
    const box = document.getElementById("dedupebox");
    if (!j.groups || !j.groups.length) {
      box.style.display = "";
      box.innerHTML = `<b class="ok">No identical dumps.</b> ` +
        `<span class="note">${j.skipped_uncomparable} dump(s) without a ` +
        `rows dict were left alone (content unprovable).</span>`;
      return;
    }
    const rows = j.groups.map(g =>
      `<div style="margin-top:6px"><span class="mono">${esc(g.serial || "no serial")}</span>` +
      ` · ${g.row_count} rows · keep <span class="mono">${esc(g.kept)}</span>` +
      ` <span class="note">(${esc(g.kept_dumped || "?")})</span><br>` +
      g.duplicates.map(d => `<span class="bad">delete</span> ` +
        `<span class="mono">${esc(d.dir)}</span> <span class="note">` +
        `(${esc(d.dumped || "?")}, ${kb(d.bytes)}` +
        (d.driver_bound ? ", driver-bound" : "") + `)</span>`).join("<br>") +
      `</div>`).join("");
    box.style.display = "";
    box.innerHTML = (applied
        ? `<b class="ok">Deleted ${j.removed.length} duplicate dump(s)</b>` +
          ` — ${kb(j.freed_bytes)} freed.`
        : `<b>${j.identical_groups} identical group(s)</b> — ` +
          `${j.duplicates} duplicate dump(s), ${kb(j.freed_bytes)} to free. ` +
          `Oldest kept per group; different content is never touched.<br>` +
          rows +
          `<div style="margin-top:8px"><button class="btn badl" id="dedupe-apply">` +
          `Delete ${j.duplicates} duplicate(s)</button></div>`) +
      (j.skipped_uncomparable ? `<br><span class="note">${j.skipped_uncomparable} ` +
        `dump(s) without a rows dict left alone.</span>` : "");
    const ab = document.getElementById("dedupe-apply");
    if (ab) ab.onclick = async () => {
      ab.disabled = true; ab.textContent = "deleting…";
      try {
        const r = await jpost("/api/dumps/dedupe", {apply: true});
        renderDedupe(r, true);
        openPickerList();          // refresh the list under the panel
      } catch (e) {
        ab.disabled = false; ab.textContent = "delete failed — retry";
      }
    };
  }
  document.getElementById("dumppicker-dedupe").onclick = async () => {
    const box = document.getElementById("dedupebox");
    box.style.display = "";
    box.innerHTML = '<span class="note">comparing fuse content…</span>';
    try { renderDedupe(await jpost("/api/dumps/dedupe", {}), false); }
    catch (e) { box.innerHTML = '<span class="bad">⚠ ' + esc(String(e)) + "</span>"; }
  };

  // ---- driver-bound guarded capture (paused live view is not a dead end) ----
  const BOUND_ACTIONS = "Issues 512 fuse CMD_READs x2 passes; writes ONLY " +
    "CTRL/ADDR/EN (never PLM, SWIFF, GPIO, voltage); restores controller " +
    "state; takes seconds; small residual risk while the driver is loaded — " +
    "do not run while a glitch tool is driving the card.";
  function fmtAge(s) {
    if (s < 90) return Math.round(s) + "s";
    if (s < 5400) return Math.round(s / 60) + " min";
    if (s < 172800) return (s / 3600).toFixed(1) + " h";
    return (s / 86400).toFixed(1) + " days";
  }
  function boundHide() {
    const el = document.getElementById("boundpanel");
    if (el) { el.style.display = "none"; el.dataset.bound = "0"; }
    const bar = document.getElementById("boundbar");
    if (bar) bar.style.display = "none";
  }
  function boundBar(j) {
    // collapsed view: one line saying capture is still available, with the age
    const el = document.getElementById("boundpanel");
    if (el) { el.style.display = "none"; el.dataset.bound = "0"; }
    const bar = document.getElementById("boundbar");
    if (!bar) return;
    const age = j.last_dump_note || ((j.last_dump_age_s === null || j.last_dump_age_s === undefined)
      ? "no complete dump saved yet for this card"
      : "last dump for this card " + fmtAge(j.last_dump_age_s) + " ago");
    bar.innerHTML = `<span class="pill warnl">Fuse capture available (driver bound)</span> ` +
      `<span class="note">${esc(age)}.</span> ` +
      `<button class="btn" id="boundexpand">Expand ▾</button>`;
    bar.style.display = "";
    document.getElementById("boundexpand").onclick = () => {
      localStorage.removeItem("ga100.boundCollapsed");
      bar.style.display = "none";
      fetchLive(false);   // dataset.bound is "0" — next poll rebuilds the panel now
    };
  }
  function boundPanel(j) {
    const el = document.getElementById("boundpanel");
    if (!el) return;
    if (!j.manual_dump_available) { boundHide(); return; }
    if (localStorage.getItem("ga100.boundCollapsed") === "1") { boundBar(j); return; }
    const bar = document.getElementById("boundbar");
    if (bar) bar.style.display = "none";
    if (el.dataset.bound === "1") return;   // keep an open panel across polls
    el.dataset.bound = "1";
    const age = j.last_dump_note || ((j.last_dump_age_s === null || j.last_dump_age_s === undefined)
      ? "no complete dump saved yet for this card"
      : "last complete dump for this card " + fmtAge(j.last_dump_age_s) + " ago");
    el.innerHTML = `<div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">` +
      `<b>${esc(j.paused || "")}</b>` +
      `<button class="btn" id="boundcollapse">Collapse ▴</button></div>` +
      `<div class="note" style="margin-top:4px">${esc(j.paused_hint || "")}</div>` +
      `<div class="note">${esc(age)}.</div>` +
      `<div style="margin-top:6px"><button class="btn" id="boundcap">` +
      `Capture fuse dump (driver bound)</button></div>` +
      `<div id="boundconsent" style="display:none;margin-top:8px"></div>` +
      `<div id="boundresult" style="display:none;margin-top:8px"></div>`;
    el.style.display = "";
    document.getElementById("boundcap").onclick = boundConsent;
    document.getElementById("boundcollapse").onclick = () => {
      localStorage.setItem("ga100.boundCollapsed", "1");
      boundHide();
      boundBar(j);   // show the slim bar immediately, not only on the next poll
    };
  }
  function condLines(conds, onlyFailed) {
    return (conds || []).filter(c => !onlyFailed || !c.ok).map(c =>
      `<div>${c.ok ? "✅" : "❌"} <b>${esc(c.name)}</b> — read ${esc(String(c.value))}, ` +
      `expected ${esc(String(c.expected))}` +
      (c.ok || !c.hint ? "" : ` <span class="note">→ ${esc(c.hint)}</span>`) +
      `</div>`).join("");
  }
  async function boundConsent() {
    const c = document.getElementById("boundconsent");
    c.style.display = ""; c.innerHTML = "checking conditions (read-only)…";
    let j;
    try { j = await (await fetch("/api/bound_dump/preflight", { cache: "no-store" })).json(); }
    catch (e) { c.innerHTML = "⚠ preflight unreachable: " + esc(String(e)); return; }
    if (j.error) { c.innerHTML = "⚠ " + esc(j.error); return; }
    c.innerHTML = `<div class="note">Conditions this capture checks` +
      (j.mock ? " <b>(mock)</b>" : "") + `:</div>` + condLines(j.conditions, false) +
      `<div class="note" style="margin-top:6px">What it does:</div>` +
      `<div class="note">${esc(BOUND_ACTIONS)}</div>` +
      `<div style="margin-top:6px"><button class="btn" id="boundgo"` +
      (j.all_ok ? "" : " disabled") + `>Capture now</button>` +
      (j.all_ok ? "" : ` <span class="note">fix the failed conditions first</span>`) +
      ` <button class="btn" id="boundcancel">Cancel</button></div>`;
    document.getElementById("boundcancel").onclick =
      () => { c.style.display = "none"; };   // back out; outer panel untouched
    if (j.all_ok) document.getElementById("boundgo").onclick = boundRun;
  }
  async function boundRun() {
    const b = document.getElementById("boundgo");
    const r = document.getElementById("boundresult");
    b.disabled = true;
    r.style.display = ""; r.innerHTML = "capturing… (512 rows ×2 passes, takes seconds)";
    try {
      const res = await fetch("/api/bound_dump", { method: "POST" });
      const j = await res.json();
      if (j.error) {
        r.innerHTML = `<span class="pill badl"><b>FAILED</b></span> ` + esc(j.error) +
          (j.conditions ? `<div style="margin-top:4px">${condLines(j.conditions, true)}</div>` : "");
        return;
      }
      const tot = (j.totals || {});
      const gpcs = ((j.tpc || {}).gpcs || []).map(g => g.available
        ? `gpc${g.gpc}: sm_now=${g.sm_now} ceiling=${g.sm_max} ` +
          `tpc_defective=${g.tpc_defective} tpc_recoverable=${g.tpc_recoverable}`
        : `gpc${g.gpc}: no data`).join("<br>");
      r.innerHTML = `<span class="pill badl"><b>UNVERIFIED (driver bound)</b></span> ` +
        `<span class="pill">SM now: <b>${tot.sm_now}</b></span>` +
        `<span class="pill okl">fuse ceiling: <b>${tot.sm_max}</b> SM</span>` +
        `<div class="mono" style="margin-top:6px">${gpcs}</div>` +
        `<div class="note">saved ${esc(j.saved || "")} · card ` +
        (j.serial ? "SN " + esc(j.serial) : "serial unreadable") +
        ` · double-pass agree: ` +
        (j.passes_agree ? "yes" : "NO") + `</div>`;
    } catch (e) { r.innerHTML = "⚠ capture failed: " + esc(String(e)); }
    finally { b.disabled = false; }
  }
  let heavyTimer = null;
  document.getElementById("pollsel").onchange = e => {
    if (heavyTimer) { clearInterval(heavyTimer); heavyTimer = null; }
    const ms = +e.target.value;
    localStorage.setItem("ga100.pollMs", String(ms));
    if (ms > 0) { fetchLive(true); heavyTimer = setInterval(() => fetchLive(true), ms); }
    else note("heavy page redraw paused — feed/dmesg/logs still live", "warnl");
  };
  // interpretation feed: always-on light poll (diff-only, no heavy redraw)
  setInterval(() => { if (!document.hidden) fetchLive(false); }, 2000);
  // live dmesg tail (GPU-relevant lines)
  async function dmesgTick() {
    try {
      const r = await fetch("/api/dmesg", { cache: "no-store" });
      const j = await r.json();
      if ((j.tail || []).length) {
        D.dmesg_tail = j.tail.join("\n");   // keep renderStatic in sync
        const el = document.getElementById("dmesg");
        if (el) el.innerHTML = j.tail.map(esc).join("\n");
      }
    } catch (e) {}
  }
  dmesgTick();
  setInterval(() => { if (!document.hidden) dmesgTick(); }, 2000);

  // ============================ TAB PANES ============================
  const $ = id => document.getElementById(id);
  async function jget(url) { const r = await fetch(url, {cache: "no-store"}); return r.json(); }
  async function jpost(url, body) {
    const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
                                body: JSON.stringify(body)});
    return r.json();
  }

  // ---------- Glitch & Burn pane ----------
  $("tab-glitch").innerHTML = `
    <div class="card verdict" id="gb-brickwarn" style="margin-bottom:12px">
      <b class="bad">⚠ Burns are permanent OTP writes — a wrong burn can BRICK
      your GPU permanently. Verify with Preview first. No responsibility is
      accepted by the developer.</b>
    </div>
    <div class="card" id="gb-target">
      <h3>Target</h3>
      <div class="frow">
        <div class="field"><label>GPU</label><select id="gb-gpu"><option>scanning…</option></select></div>
        <span class="pill" id="gb-gpustate">checking…</span>
        <span class="pill" id="gb-gpuserial">—</span>
      </div>
      <div class="verdict warnv" id="gb-follow" style="display:none;margin-top:8px"></div>
      <div class="note" style="margin-top:6px">Standalone burns are only allowed on a
      GPU currently in the <b>Goldilocks</b> state (DSOV=0, CRC=0x55, PLMs open) —
      the campaign's burn-on-goldilocks mode creates that state on the selected GPU.</div>
    </div>
    <div class="card" id="gb-policy" style="margin-top:12px">
      <h3>Burn placement policy</h3>
      <ol class="rules">
        <li><b>Never yolo ffcalc output.</b> Verify every record against your
        card's own defect masks first — a blind burn bricks the card.</li>
        <li><b>Burn only into blank rows</b> in the FF record region
        (222–487) — never touch the occupied boot records.</li>
        <li><b>Keep a buffer after the last boot FF</b> so new records cannot
        interfere with the boot FF chain.</li>
        <li><b>Leave the tail empty for reverts.</b> A wrong value can only be
        corrected by burning a <i>later</i> record (last record per block
        wins) — mistakes consume rows.</li>
        <li><b>Attempts are limited:</b> the safe zone holds only the rows in
        the budget below, corrections included.</li>
        <li><b>The SM reserve stays free</b> so you can re-disable SMs that
        turn out to be actually bad after unlocking.</li>
        <li><b>Never burn a value with bit 5 set</b> — that is the IFF
        (invalidation) flag, not an FF record; a stray IFF can truncate the
        whole FF pool. Refused on every burn path.</li>
      </ol>
      <div class="ffmap" id="gb-ffmap"></div>
      <div class="frow" style="margin-top:8px">
        <span class="pill" id="gb-budget">scanning FF region…</span>
        <span class="pill" id="gb-rowhint">row —</span>
      </div>
    </div>
    <div class="card" id="gb-burn" style="margin-top:12px">
      <h3>Row probe (read-only)</h3>
      <div class="frow">
        <div class="field"><label>target row</label><input type="number" id="gb-row" placeholder="row — pick from Fuse Explorer or FF audit" min="0" max="487" style="width:170px"></div>
        <div class="field"><label>value source</label>
          <select id="gb-srcmode">
            <option value="typed">typed hex</option>
            <option value="dump">from dump row</option>
          </select></div>
        <div class="field" id="gb-typedwrap"><label>value (hex)</label><input type="text" id="gb-value" placeholder="0x…" class="mono" style="width:120px"></div>
        <div class="field" id="gb-dumpwrap" style="display:none"><label>source row in dump</label><input type="number" id="gb-srcrow" placeholder="first blank FF row (≥222)" min="0" max="487"></div>
        <label class="checkline"><input type="checkbox" id="gb-mirror"> burn mirror row too <span class="note">(row N+1, even-aligned pair — OFF by default: the proven reference recipes burned ONE row per FF record; only enable if you specifically want the redundant pair)</span></label>
        <button class="btn" id="gb-check">Check row &amp; guards</button>
        <button class="btn" id="gb-preview" title="read-only burn preview: FF decode, last-wins collision scan, partial-landing hazards — works any time (no window/arm/token; CMD_READ is gated by FUSECTRL_PLM, not EFP)">Preview burn (read-only)</button>
      </div>
      <div id="gb-srcdecode" class="note"></div>
      <div id="gb-previewresult" class="note" style="margin-top:6px"></div>
      <div id="gb-checkresult" class="note"></div>
      <div class="frow" style="margin-top:10px">
        <span class="note">To burn: queue this row (or use Suggested burns) and use <b>Arm &amp; burn queue</b> below.</span>
        <span class="pill warnl" id="gb-editwarn" style="display:none">payload edited — re-check</span>
      </div>
    </div>
    <div class="card" id="gb-plan" style="margin-top:12px">
      <h3>Suggested burns — minimum common unlock</h3>
      <div class="note" style="margin-bottom:8px">Derived from <b>this card's own defect
      masks</b> (loaded dump): every disabled-but-healthy unit is re-enabled in one pass.
      Minimum common set: <b>GPC 1 word + FBP 1 word + FBPA 2 words = 4 words</b>
      (optional DEVID identity change adds 2). Queued records burn together inside
      <b>one</b> Goldilocks window.</div>
      <div id="plan-rows"></div>
      <div class="frow" style="margin-top:8px">
        <button class="btn" id="plan-sel-all" title="tick every word">select all</button>
        <button class="btn" id="plan-sel-none" title="untick every word">select none</button>
        <button class="btn go" id="plan-queue-all">⤓ Queue all needed records</button>
        <span class="pill" id="plan-summary">…</span>
      </div>
      <div class="frow" style="margin-top:10px; align-items:end">
        <div class="field"><label>A100 rebrand SKU</label>
          <select id="plan-rebrand-sku">
            <option value="80" selected>A100 80GB PCIe (0x20B5)</option>
            <option value="custom">custom…</option>
          </select></div>
        <div class="field" id="plan-devid-wrap" style="display:none"><label>custom DEVID (hex, e.g. 0x20B5)</label>
          <input type="text" id="plan-devid" value="" class="mono" style="width:100px"></div>
        <button class="btn" id="plan-devid-add">+ Queue DEVID A/B pair</button>
        <span class="note" id="plan-devid-note"></span>
      </div>
    </div>
    <div class="card" id="tag-legend" style="margin-top:12px">
      <details>
        <summary style="cursor:pointer"><h3 style="display:inline">Tag legend — what every badge means</h3></summary>
        <div class="note" style="margin-top:8px">Two independent axes: a
        <b>TESTED</b> badge says the burn was <b>executed and the cards came
        back working</b> (empirical safety). <b>VERIFIED/UNVERIFIED</b> says
        whether we know <b>what the word does</b> (bit-level attribution).
        A word can be TESTED but UNVERIFIED: proven to copy, not yet
        understood.</div>
        <div style="margin-top:8px">
          <span class="tag prop-tag">PROPOSED</span> <span class="note">candidate only — nothing written; the shown row is the allocator's placement if you queue it.</span><br>
          <span class="tag ok-tag">VERIFIED</span> <span class="note">field mapping documented (repo evidence / GA100 hwref) — the word can be recomputed from THIS card's defect masks.</span><br>
          <span class="tag prop-tag">UNVERIFIED</span> <span class="note">bit attribution inferred, unresolved — copy the tested value as-is or skip; do NOT recompute it.</span><br>
          <span class="tag prop-tag">TESTED · EXTERNAL</span> <span class="note">burn executed and confirmed working on cards outside this fleet.</span><br>
          <span class="tag ok-tag">TESTED · INTERNAL</span> <span class="note">confirmed on our own cards.</span><br>
          <span class="tag ok-tag">ALREADY PRESENT</span> <span class="note">the last record of that block already equals this word — burning it would be a no-op.</span><br>
          <span class="tag prop-tag">PARTIALLY PRESENT</span> <span class="note">some selected words of this item are already effective; only the rest would burn.</span><br>
          <span class="tag prop-tag">SUPERSEDED at row N</span> <span class="note">a later record of the same block overrides this word at boot (last-wins) — needs re-burn after row N.</span><br>
          <span class="tag">MANUAL</span> <span class="note">outside the FF queue path (direct rows &lt;222 or IFF bit-5 words) — burn via the manual path, never queued.</span><br>
          <span class="note"><b class="bad">NO FREE ROW FOR BLOCK N</b> — no blank row exists after that block's last record; free space or shrink the queue.</span>
        </div>
      </details>
    </div>
    <div class="card" id="gb-advanced" style="margin-top:12px">
      <h3>Advanced unlocks — optional, tested permanent unlocks</h3>
      <div class="note" style="margin-bottom:8px">Permanent unlocks with a
      <b>TESTED</b> badge (scope: EXTERNAL = proven on cards outside this
      fleet, INTERNAL = confirmed on our own cards). <b class="warn">
      Irreversible OTP writes — NOT derived from this card's defect
      masks:</b> the data words carry the tested cards' defect masks; check
      them against this card before burning.
      PROPOSED rows are placement candidates from the same allocator the
      queue uses. DIRECT rows (&lt;222) and IFF words (bit 5 set) are
      outside the queue's FF-record path (burn accepts FF records at rows
      222–487 only) — <b>manual burn path</b>. Confidence: VERIFIED =
      field mapping documented in repo evidence / GA100 hwref; UNVERIFIED
      = attribution inferred, unresolved.</div>
      <div class="frow" style="margin-bottom:6px">
        <button class="btn" id="adv-sel-all" title="tick every FF word">select all FF words</button>
        <button class="btn" id="adv-sel-none" title="untick every FF word">select none</button>
      </div>
      <div id="adv-rows"></div>
    </div>
    <div class="card" id="gb-campaign" style="margin-top:12px">
      <h3>Glitch campaign</h3>
      <div class="frow">
        <div class="field"><label>v_dip mV</label><input type="number" id="gc-vdip" value="354"></div>
        <div class="field"><label>pulses</label><input type="number" id="gc-pulses" value="3"></div>
        <div class="field"><label>pw µs</label><input type="number" id="gc-pw" value="198"></div>
        <div class="field"><label>gap µs</label><input type="number" id="gc-gap" value="150"></div>
        <div class="field"><label>delay</label><input type="number" id="gc-delay" value="117"></div>
        <div class="field"><label>t_dip µs</label><input type="number" id="gc-tdip" value="-60" title="dip timing vs PEX_RST release; -60 = our proven regime, +50 = The Lab in-window claim (unverified here)"></div>
        <div class="field"><label>Cooldown s</label><input type="number" id="gc-cooldown" value="1" step="1" min="0" max="120"></div>
        <div class="field"><label>max attempts</label><input type="number" id="gc-max" value="100"></div>
        <div class="field"><label>v_dip strategy</label>
          <select id="gc-strategy">
            <option value="fixed">fixed v_dip</option>
            <option value="adaptive" selected>adaptive 3D (v_dip · delay · pw)</option>
          </select></div>
        <div class="field"><label>adaptive v min mV</label><input type="number" id="gc-vmin" value="300"></div>
        <div class="field"><label>adaptive v max mV</label><input type="number" id="gc-vmax" value="380"></div>
        <button class="btn" id="t51-lab-preset" title="The Lab / allspark claim: arming dip fires +50 us AFTER PEX_RST release, single pulse only. Our card's proven regime is 3 pulses at -60 us — this preset is for bounded A/B sweeps, not a replacement.">Lab in-window single-pulse (UNVERIFIED here)</button>
        <span class="note" id="t51-preset-note"></span>
      </div>
      <div class="frow">
        <div class="field"><label>pico port</label><select id="gc-port"><option>scanning…</option></select></div>
        <button class="btn" id="gc-ports-refresh" title="rescan serial ports">⟳ rescan</button>
        <button class="btn" id="gc-flash" title="Flash firmware into the Pico 2 from the console: sends 'b' to the selected port (firmware BOOTSEL reboot), waits for the RP2350 drive, writes the .uf2 stored on this host (firmware/build/pwmvid.uf2 — build it on a workstation and scp it over), then reads the firmware banner back and shows it. The board reboots into the new firmware by itself.">⚡ Flash Pico 2</button>
        <span class="note" id="gc-portnote"></span>
        <span class="note" id="gc-flashstate"></span>
        <div class="field"><label>Goldilocks window</label>
          <select id="gc-hold" title="keep the glitch window open when the campaign hits Goldilocks (skip the VRM revert). Misses/stops always revert.">
            <option value="hold" selected>hold open — no revert (default)</option>
            <option value="revert">auto-revert VRM</option>
          </select></div>
        <button class="btn go" id="gc-start">▶ Start campaign</button>
        <button class="btn danger" id="gc-stop" disabled>■ Stop</button>
        <button class="btn" id="gc-revert" disabled title="hand PMBus control back — closes a held window without a cold boot">⟲ Revert VRM</button>
        <span class="pill" id="gc-state">idle</span>
        <label class="note" style="margin-left:10px;user-select:none" title="keep pinned to the newest line; uncheck to read older lines freely"><input type="checkbox" id="gc-autoscroll" checked> autoscroll</label>
      </div>
      <div class="chips" id="gc-chips"></div>
      <div class="logbox" id="gc-log">— campaign log —</div>
    </div>
    <div class="card" id="gb-queue" style="margin-top:12px">
      <h3>Burn queue — arm &amp; burn in one action <span class="note">(all queued records burn together in ONE Goldilocks window; <b>Arm &amp; burn queue</b> runs the arm gate and starts the burn campaign in ONE server call — no 120 s TTL race)</span></h3>
      <div class="frow">
        <button class="btn go" id="bq-armburn" disabled style="font-size:14px; padding:8px 18px">⚡ Arm &amp; burn queue (0)</button>
        <button class="btn" id="bq-check" title="read-only per-record preview (guards, FF decode, last-wins collisions, hazards) for every queued row — works any time, no window/arm/token needed">Check queue</button>
        <span class="pill" id="bq-window" title="authoritative burn-window verdict from the live register poll (/api/live window checks) — the campaign HELD chip shows this SAME state">burn window: …</span>
        <span class="note" id="bq-reason"></span>
      </div>
      <div id="queue-rows" class="queue-rows"></div>
      <div class="frow" style="margin-top:8px; align-items:end">
        <div class="field"><label>custom record — row</label>
          <input type="number" id="cq-row" placeholder="row — first free FF row" min="222" max="487"></div>
        <button class="btn" id="cq-firstfree" title="fill row with the first blank FF row (≥222) in the loaded dump">first free FF row</button>
        <div class="field"><label>value (hex FF record)</label>
          <input type="text" id="cq-value" placeholder="0x… FF record" class="mono" style="width:120px"></div>
        <button class="btn" id="cq-add">+ Add custom record</button>
        <label class="checkline"><input type="checkbox" id="cq-mirror"> mirror each</label>
        <button class="btn" id="queue-clear">clear queue</button>
      </div>
      <div id="cq-decode" class="note"></div>
    </div>
    <div class="card" id="vb-card" style="margin-top:12px">
      <h3>VBIOS flash <span class="note">(post-DEVID phase — nvflash requires
        the nvidia kernel <b>MODULES UNLOADED</b> (nvidia, nvidia_uvm,
        nvidia_modeset, nvidia_drm — unbinding the device alone is not
        enough); a board-id mismatch prompt from nvflash is <b>expected</b>
        on a rebranded card and is auto-answered <code>y</code>. A verified
        backup of the current VBIOS is always saved before a flash.)</span></h3>
      <div class="frow">
        <span class="pill" id="vb-driver">modules: …</span>
        <button class="btn danger" id="vb-unload" style="display:none">Unload nvidia modules</button>
        <span class="pill" id="vb-nvflash">nvflash: …</span>
      </div>
      <div class="frow" style="margin-top:8px">
        <button class="btn" id="vb-pick">📁 Choose ROM…</button>
        <span class="note" id="vb-rom">no ROM selected</span>
      </div>
      <div class="frow" style="margin-top:8px">
        <button class="btn" id="vb-backup" title="nvflash --save into the state dir; verified non-empty and not all-00/FF">💾 Save current VBIOS</button>
        <label class="checkline" title="optional — NOT required for this card's flash (owner, 2026-11-27); tick only if nvflash reports protected regions">run nvflash --protectoff first</label>
        <input type="checkbox" id="vb-protectoff">
        <button class="btn danger" id="vb-flash" disabled>⚡ Flash selected ROM</button>
        <button class="btn" id="vb-refresh" title="re-read driver state, nvflash, backups">⟳</button>
      </div>
      <div class="note" id="vb-backupinfo" style="margin-top:6px"></div>
      <div class="note" id="vb-warn" style="margin-top:4px"></div>
      <div class="logbox" id="vb-log" style="margin-top:8px">— vbios flash log —</div>
      <div class="note" id="vb-post" style="margin-top:6px"></div>
    </div>
    <div class="card" id="t51-neverwrite" style="margin-top:12px">
      <h3>Never-write reference <span class="note">(The Lab / allspark
        community claims — read-only, never a burn gate)</span></h3>
      <div id="t51-neverwrite-body" class="note">awaiting first live poll
        (/api/live never_write)…</div>
    </div>
    <details class="card" id="t51-reset-cheat" style="margin-top:12px">
      <summary>Reset semantics cheat sheet — FLR vs SBR vs cold power
      cycle <span class="note">(provenance tagged per row)</span></summary>
      <table style="margin-top:8px">
        <tr><th>reset</th><th>clears</th><th>does NOT clear</th><th>provenance</th></tr>
        <tr><td><b>FLR</b> (function level reset)</td>
          <td>little — the GFW-side state largely survives</td>
          <td>glitched fuse-latch state; FSP latch; XVE errors</td>
          <td><span class="pill warnl">The Lab · unverified here</span></td></tr>
        <tr><td><b>SBR</b> (secondary bus reset)</td>
          <td>HS write engine state; booter halts re-run from 0x15</td>
          <td>glitched fuse-latch state; FSP latch; XVE errors</td>
          <td><span class="pill warnl">The Lab · unverified here</span>
            <span class="note">SBR has physically damaged a test card in our
            history — PEX_RST is the reset path (AGENTS.md).</span></td></tr>
        <tr><td><b>cold power cycle</b> — PSU off AND unplugged</td>
          <td>glitched state, FSP latch, XVE errors</td>
          <td>burned fuses (OTP is permanent)</td>
          <td><span class="pill okl">verified here</span></td></tr>
      </table>
      <div class="note" style="margin-top:6px">An OS reboot is NONE of these —
      it does not cold-cycle the card. <code>nvidia-smi -r</code> is
      unsupported on this card <span class="pill okl">verified here</span>.
      FLR/SBR row content is a community claim:
      <span class="pill warnl">The Lab · unverified here</span>.</div>
    </details>
    <div class="dangerstrip">
      Glitching dips NVVDD via the pico; burns are <b>irreversible OTP writes</b>.
      Burn mode requires an armed token, a pure 0→1 payload, matching row state and a
      live burn window on the target GPU — all verified again server-side
      before CMD_WRITE; EFP/WDATA_PLM are opened at burn time by the SENSE_CTRL
      arm sequence, never by the poller or the check.
      FF records belong at rows 222–487 (chain=bits[4:0], iff=bit5, block=bits[15:6],
      data=bits[31:16]); a bit-exact readback does NOT prove the shadow latch followed —
      after any burn, watch STATUS_OPT_* on the Fuse Explorer tab.
      The live poll stays safe during glitching (pure reads); avoid the full-dump
      button while a campaign runs.
    </div>`;

  let armToken = null, armExpiry = 0, payloadChecked = null;
  let targetBdf = null;
  let windowOk = false;           // live burn-window verdict (poller / fresh check)
  let goldilocksNow = false;      // /api/gpus 4-check state — the SAME gate
                                  // the server's arm_api enforces; the 9-check
                                  // burn-window pill stays informational
                                  // (FUSECTRL_PLM decays seconds after
                                  // Goldilocks on some cards, but the
                                  // in-process burn re-checks it at the
                                  // millisecond it matters)
  // task 67 (UX66 F3): ONE authoritative burn-window state, computed once
  // per /api/live poll and consumed by every window widget (bq-window pill,
  // campaign HELD chip). OPEN = all window checks
  // Truthful burn-window indicator: OPEN = every live window check passes,
  // closed = anything fails (binary by owner decision — decay simply shows
  // as OPEN flipping to closed on the next 2 s poll). ONE poll computes
  // windowState; every window widget renders from it — no second truth.
  let windowState = {state: "n/a", bad: []};
  let campaignRunning = false;    // gates Arm & burn while a campaign owns the card
  let burnResults = null;         // row -> result from stats.burned (null = no burn campaign seen)
  let burnPending = false;        // burn campaign running: queued rows without a result show pending
  let burnResultsSig = "";
  let queueVerdicts = {};         // "row:value" -> Check-queue preview verdict (UX66 F5-lite)

  // B6: the Check verdict binds to the exact payload — any edit to the burn
  // inputs invalidates it (the check IS the safety contract).
  function invalidateChecked() {
    if (!payloadChecked) return;
    payloadChecked = null;
    $("gb-editwarn").style.display = "";
  }

  // ---- burn queue (suggested + custom records) ----
  // All queued records burn in ONE campaign pass (service supports records[]).
  // burnQueue itself is declared as `var` in the page script (task 35c) so
  // the proposed panel and this script share one binding.
  const encFF = (ch, off, data) => ((ch & 0x3F) | ((off & 0x3FF) << 6) |
    ((data & 0xFFFF) << 16)) >>> 0;
  // Decode a record's effect for humans: which units it acts on, disable→what.
  const FF_FIELD = [{ blk: 8, w: 0xFF, name: "GPC" }, { blk: 19, w: 0xFFF, name: "FBP" }];
  function ffEffect(word) {
    const ch = word & 0x1F, off = (word >> 6) & 0x3FF, data = (word >>> 16) & 0xFFFF;
    const mask = (data >> 3) & 0xFFFFFF;
    for (const f of FF_FIELD) {
      if (ch === 1 && off === f.blk) {
        const bits = [];
        for (let i = 0; i < 16; i++) if ((mask >> i) & 1) bits.push(f.name + i);
        return { key: `chain1·off${f.blk}`, field: f.name, mask, bits, width: f.w };
      }
    }
    if (ch === 1 && off >= 11 && off <= 15) {
      // chain1 offs 11–15: OPT_TPC_GPC{g}_DISABLE live at GLOBAL bit
      // 187+8g (ray schema, plane FF) — word = bit//16, so one 16-bit word
      // can straddle two or three GPC fields. Name every field it touches;
      // full field → "GPCg", partial → "TPC_GPCg(lo-hi)" (TPC indices).
      const names = [];
      for (let g = 0; g < 8; g++) {
        const lo = 187 + 8 * g, wlo = off * 16, whi = wlo + 15;
        if (lo + 7 < wlo || lo > whi) continue;
        const t0 = Math.max(lo, wlo) - lo, t1 = Math.min(lo + 7, whi) - lo;
        names.push(t0 === 0 && t1 === 7 ? "GPC" + g : `TPC_GPC${g}(${t0}-${t1})`);
      }
      if (off === 15) names.push("PES(0-4)");  // OPT_PES_DISABLE bit 251 spills in
      return { key: `chain1·off${off} ${names.join("·")}`, field: "TPC",
               mask: data, bits: [] };
    }
    if (ch === 1 && (off === 5 || off === 6)) {
      return { key: `chain1·off5+6 (FBPA split)`, field: "FBPA", mask, bits: [], two: off };
    }
    if (ch === 2 && (off === 37 || off === 38)) {
      return { key: `chain2·off${off} DEVID`, field: "DEVID", devid: (data >> 1) >>> 0, bits: [] };
    }
    return { key: `chain${ch}·off${off}`, field: null, mask, bits: [] };
  }
  // ---- task 32: per-burn selection (shared across all three lists) ----
  // planSel/advSel hold ONLY explicit user choices; the default for any
  // word is "selected, unless it is already EFFECTIVE under last-wins"
  // (lastWinsStatus state "present" → default OFF; "superseded" or absent
  // → default ON). The INTENDED-state panel and this card share planSel —
  // same words, one state, no divergence.
  const planSel = {};
  const advSel = {};
  function planWordSelected(word) {
    const k = String(word >>> 0);
    if (k in planSel) return planSel[k];
    const st = lastWinsStatus(word);
    return !(st && st.state === "present");
  }
  function setPlanWordSelected(word, on) {
    planSel[String(word >>> 0)] = on;
    renderQueue();
    renderProposedBurns();   // keep the INTENDED-state panel in step
  }
  function setAllPlanWordsSelected(on) {
    for (const p of suggestPlan())
      for (const w of (p.pair ? p.words : [p.word])) planSel[String(w >>> 0)] = on;
    renderQueue();
    renderProposedBurns();
  }
  // task 39/41: per-card derivation — EVERY compute-unlock chain1 word in
  // advanced unlocks is RECOMPUTED from the selected card's own defect
  // readouts (window.__perDieTargets, built by suggestPlan from the
  // embedded FF_FIELDS catalog); fields whose readout is missing from the
  // loaded dump carry the card's current word bits and are labelled
  // (window.__perDieCarried). Tested values remain only for blocks the
  // derivation does not cover (chain 2, IFF/DIRECT steps).
  function advEffWord(s) {
    if (s.kind !== "ff" || (s.value & 0x1F) !== 1) return s.value;
    const pd = window.__perDieTargets || {};
    const w = pd[(s.value >> 6) & 0x3FF];
    return w === undefined ? s.value : w;
  }
  function advStepSelected(id, step) {
    const s = ADVANCED.find(a => a.id === id);
    const k = id + ":" + s.steps.indexOf(step);
    if (k in advSel) return advSel[k];
    const st = lastWinsStatus(advEffWord(step));
    return !(st && st.state === "present");
  }
  function setAllAdvStepsSelected(on) {
    for (const it of ADVANCED)
      it.steps.forEach((s, si) => { if (s.kind === "ff") advSel[it.id + ":" + si] = on; });
    renderQueue();
  }
  function suggestPlan() {
    const sh = D.shadow || {};
    const gpcDef = sh.GPC_DEFECTIVE ?? 0, gpcDis = sh.GPC_DISABLE ?? 0;
    const fbpDef = sh.FBP_DEFECTIVE ?? 0, fbpDis = sh.FBP_DISABLE ?? 0;
    const fbpaDef = sh.FBPA_DEFECTIVE ?? 0;
    const fbpaDisEff = auditWord(AOFF.FBPA_DIS_EFF, "FBPA_DISABLE_EFF").v ??
                       (sh.FBPA_DISABLE ?? 0);
    const out = [];
    // task 38: last-wins CURRENT chain1 word per offset (mark-1 records;
    // ffDecode's ch filter drops the mark-2 factory words). Non-field bits
    // of a rewritten word are preserved — both tested cards kept off8/5
    // bits 0-2 (0b110 / 0b111) in their final words.
    const curWord = {};
    for (const k of Object.keys(D.rows || {})) {
      const r = +k, v = D.rows[k];
      if (r < 222 || r > 487 || typeof v !== "number" || v === 0 || v === 0xFFFFFFFF) continue;
      const f = ffDecode(v);
      if (f.ch === 1) curWord[f.blk] = f.data;   // rows ascend → last wins
    }
    // task 41: per-card target word for EVERY compute-unlock chain-1 block
    // (evidence/40 §3) — catalog-driven placement of the SELECTED card's
    // own defect readouts at the FF field positions of FF_FIELDS (embedded
    // as ffcatdata, same source the server's plane gate uses). A field
    // whose defect readout is missing from this dump CARRIES the card's
    // current last-wins bits — never enable a unit of unknown status (the
    // Nov-24 brick class) — and is labelled in the advanced-unlocks table.
    // Non-field bits: block 5 data 0-2 preserved (both reference cards
    // kept 0b111 there); every other non-field bit → 0 (both reference
    // cards cleared block 8 data 11-15 and blocks 9/26/27 despite
    // non-zero pre-burn values). Blocks 9/26/27 carry no catalog field →
    // word 0x0000, the tested value, UNVERIFIED flag kept.
    const pd = {}, pdCarried = {};
    for (const blk of [5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 19, 20, 23, 26, 27]) {
      let word = 0;
      const carried = [];
      for (const f of ffFieldsFor(blk)) {
        const mask = (1 << f.n) - 1;
        const v = sh[defectKey(f.name)];
        if (v != null) {
          word |= ((v >>> f.fbit0) & mask) << f.dlo;
        } else {
          word |= (((curWord[blk] ?? 0) >>> f.dlo) & mask) << f.dlo;
          carried.push(f.name);
        }
      }
      if (blk === 5) word |= (curWord[5] ?? 0) & 0x0007;
      pd[blk] = encFF(1, blk, word);
      if (carried.length) pdCarried[blk] = carried;
    }
    window.__perDieTargets = pd;
    window.__perDieCarried = pdCarried;
    if (((gpcDis & 0xFF) !== (gpcDef & 0xFF)) && (gpcDef & 0xFF) !== 0 || (gpcDis & 0xFF) !== (gpcDef & 0xFF)) {
      const bits = [];
      for (let i = 0; i < 8; i++) if (((gpcDis & ~gpcDef) >> i) & 1) bits.push("GPC" + i);
      out.push({ label: "GPC unlock", word: encFF(1, 8, ((gpcDef & 0xFF) << 3) | (curWord[8] ?? 0) & 0x0007),
        effect: `GPC_DISABLE ${fmt(gpcDis & 0xFF)} → ${fmt(gpcDef & 0xFF)}` +
          (bits.length ? ` — re-enables ${bits.join(", ")}` : " — masks already equal"),
        recs: gpcDef ? "re-enables every non-defective GPC" : "no defective GPCs — record would disable all (skip)" });
    }
    // TPC unlock — chain1 offs 11–15 carry OPT_TPC_GPC{g}_DISABLE at global
    // bit 187+8g (ray schema plane FF, word = bit//16). CURRENT values come
    // from the DUMP's last-wins chain1 records (NOT shadow registers); the
    // TARGET word IS pd[off] from the catalog-driven derivation above —
    // single source, so the proposal word and the advanced-unlocks eff word
    // are the same value by construction. This loop only names the TPC
    // deltas for the effect string. PES bits (word 15, data 11-15) follow
    // the same rule as every other field: derived from this card's
    // PES_DEFECTIVE when the dump has that readout, carried from the
    // current word when it does not. Reference card A ran with PES bits
    // 3-5 masked (burned 15=0xC080, 16=0x0001) while card B cleared them —
    // that difference is per-die PES defects, not a floorsweep to clear.
    const tpcCur = curWord;
    for (let off = 11; off <= 15; off++) {
      const cur = tpcCur[off] ?? 0;
      const tgt = (pd[off] >>> 16) & 0xFFFF;
      const on = [], masked = [], unknown = [];
      for (let g = 0; g < 8; g++) {
        const def = sh["TPC_DEFECTIVE_GPC" + g];
        if (def == null) { unknown.push(g); continue; }  // defects unknown — pd carries these bits
        for (let t = 0; t < 8; t++) {
          const bit = 187 + 8 * g + t;
          if ((bit >> 4) !== off) continue;
          const b = bit & 15, want = (def >> t) & 1;
          if (((cur >> b) & 1) && !want) on.push(`GPC${g} TPC${t}`);
          if (!(((cur >> b) & 1)) && want) masked.push(`GPC${g} TPC${t}`);
        }
      }
      if (tgt === cur) continue;  // word already matches target (incl. absent=0) — no proposal
      const delta = on.length ? `re-enables ${on.join(", ")}` :
                    masked.length ? `masks ${masked.join(", ")} (defective)` : "no field change";
      out.push({ label: "TPC unlock", word: encFF(1, off, tgt),
        effect: `off${off} word ${fmt(cur)} → ${fmt(tgt)}` +
          (on.length ? ` — ${on.length} TPC(s) re-enabled` : "") +
          (masked.length ? ` — ${masked.length} defective stay masked` : "") +
          (off === 15 ? (sh.PES_DEFECTIVE != null
              ? " — PES bits from this card's PES defect readout"
              : " — PES bits carried (no PES defect readout in this dump)") : ""),
        recs: delta + (unknown.length ? ` (GPC${unknown.join(",GPC")} defect words unknown — carried)` : "") });
    }
    if ((fbpDis & 0xFFF) !== (fbpDef & 0xFFF)) {
      const bits = [];
      for (let i = 0; i < 12; i++) if (((fbpDis & ~fbpDef) >> i) & 1) bits.push("FBP" + i);
      const gb = bits.length * 8;
      out.push({ label: "FBP unlock", word: encFF(1, 19, ((fbpDef & 0xFFF) << 3) | ((curWord[19] ?? 0) & 0x0007)),
        effect: `FBP_DISABLE ${fmt(fbpDis & 0xFFF)} → ${fmt(fbpDef & 0xFFF)}` +
          (bits.length ? ` — re-enables ${bits.join(", ")} (+${gb} GB)` : " — masks already equal"),
        recs: gb ? `+${gb} GB VRAM from healthy-but-floorswept stacks` : "no healthy FBP held off — nothing to gain" });
    }
    if ((fbpaDisEff & 0xFFFFFF) !== (fbpaDef & 0xFFFFFF)) {
      const w = ((fbpaDef & 0xFFFFFF) << 3) >>> 0;
      const lo = (w & 0xFFFF) | ((curWord[5] ?? 0) & 0x0007), hi = (w >>> 16) & 0xFFFF;
      const bits = [];
      for (let i = 0; i < 24; i++) if (((fbpaDisEff & ~fbpaDef) >> i) & 1) bits.push("FBPA" + i);
      out.push({ label: "FBPA unlock (2 words)", pair: true,
        words: [encFF(1, 5, lo), encFF(1, 6, hi)],
        effect: `FBPA_DISABLE ${fmt(fbpaDisEff & 0xFFFFFF)} → ${fmt(fbpaDef & 0xFFFFFF)}` +
          (bits.length ? ` — re-enables channels ${bits.join(", ")} (belong to the FBP unlock — burn together)` : " — masks already equal"),
        recs: "24-bit split field: off5 = low word, off6 = high word" });
    }
    // task 39/41: per-card target words for every compute-unlock offset are
    // in pd (built above, before the proposals) — advanced unlocks derive
    // from the selected card instead of burning a previous card's sample.
    return out;
  }
  function renderPlan() {
    const el = document.getElementById("plan-rows");
    if (!D.shadow) { el.innerHTML = `<span class="note">load a dump first</span>`; return; }
    const plan = suggestPlan();
    // task 30: name the concrete target rows through the SAME allocator the
    // queue uses — over the current queue plus the SELECTED plan words in
    // queue order and the mirror setting "Queue all" will read — so the
    // rows shown ARE the rows the queue will assign (proposal == queue by
    // construction). task 32: unselected words show no row and are not
    // allocated, exactly as queuePlanRecords skips them.
    const mirror = document.getElementById("gb-mirror").checked;
    const selWords = [];
    for (const p of plan) for (const w of (p.pair ? p.words : [p.word]))
      if (planWordSelected(w)) selWords.push(w);
    const entries = burnQueue.map(q => ({word: q.word, mirror: !!q.mirror, customRow: q.customRow}));
    for (const w of selWords) if (!burnQueue.some(q => q.word === w)) entries.push({word: w, mirror});  // task 35e: one word, one row
    const asg = assignRows(entries);
    let ai = burnQueue.length;   // index of the plan's first SELECTED word
    const needed = plan.length;
    document.getElementById("plan-summary").innerHTML = needed
      ? `<b>${selWords.length} of ${plan.reduce((a, p) => a + (p.pair ? 2 : 1), 0)} word(s) selected</b>` +
        ` in ${needed} record group(s)`
      : `<b class="ok">masks already equal to defective — this card needs no unlock burns</b>`;
    // task 35e: same table shape as the INTENDED-state proposed panel.
    let ph = `<table class="pbtable"><thead><tr><th></th><th>Burn</th><th>Word</th>` +
      `<th>Target row</th><th>Field</th><th>Effect</th><th>Status</th><th></th></tr></thead><tbody>`;
    for (const p of plan) {
      const words = p.pair ? p.words : [p.word];
      words.forEach((w, wi) => {
        const f = ffEffect(w);
        const st = lastWinsStatus(w);
        const on = planWordSelected(w);
        const inQ = burnQueue.some(q => q.word === w);
        const a = on && !inQ ? (asg ? asg.rows[ai++] : null) : null;
        const hexw = "0x" + w.toString(16).toUpperCase().padStart(8, "0");
        const rowCell =
          !on ? `<span class="note">not selected</span>`
          : inQ ? `<span class="note">in queue — row shown there</span>`
          : !asg ? `<span class="note">rows pending</span>`
          : a === null ? `<b class="bad">NO FREE ROW (block ${ffDecode(w).blk})</b>`
          : `<b data-planrow="${a.row}${a.mirror ? "+" + (a.row + 1) : ""}">row ${a.row}${a.mirror ? ` + mirror ${a.row + 1}` : ""}</b>`;
        const statusCell =
          st && st.state === "present" ? `<span class="tag ok-tag">ALREADY PRESENT (row ${st.row})</span>`
          : st && st.state === "superseded" ? `<span class="tag prop-tag">SUPERSEDED at row ${st.byRow}</span>`
          : `<span class="note">—</span>`;
        ph += `<tr class="pbrow${on ? "" : " pboff"}">` +
          `<td><input type="checkbox" class="psel" data-sel-word="${w}"${on ? " checked" : ""} ` +
            `title="include this word in the queue"></td>` +
          (wi === 0 ? `<td rowspan="${words.length}"><b>${esc(p.label)}</b><br>` +
            `<span class="note">${esc(p.recs)}</span></td>` : "") +
          `<td class="mono">${hexw}</td>` +
          `<td>${rowCell}</td>` +
          `<td class="note">${esc(f.key)}</td>` +
          (wi === 0 ? `<td rowspan="${words.length}" class="note">${esc(p.effect)}</td>` : "") +
          `<td>${statusCell}</td>` +
          `<td><button class="btn" data-plan-add="${w}">+ queue</button></td></tr>`;
      });
    }
    ph += `</tbody></table>`;
    el.innerHTML = ph + (plan.length ? "" :
      `<span class="note">no records needed — disable masks already match the card's defects</span>`);
    el.querySelectorAll("[data-sel-word]").forEach(c => c.onchange = () => {
      setPlanWordSelected(+c.dataset.selWord, c.checked);
    });
    el.querySelectorAll("[data-plan-add]").forEach(b => b.onclick = () => {
      queueAdd(+b.dataset.planAdd, "suggested");
    });
  }
  function queueAdd(word, src, customRow, mirror) {
    burnQueue.push({ word, src, customRow, mirror: !!mirror });
    renderQueue();
  }
  // ---- task 30: Advanced unlocks (tested permanent unlocks) ----
  // Optional permanent unlocks carrying a TESTED badge (scope external or
  // internal). FF-record steps
  // are queueable and show their concrete target rows through the SAME
  // assignRows allocator over (current queue + this item's steps) — the
  // rows shown ARE the rows "+ queue" will assign. DIRECT (row < 222) and
  // IFF (bit 5) steps are outside what burn_execute accepts (FF records,
  // rows 222-487) — shown as manual-path only, never queued.
  function renderAdvanced() {
    const el = document.getElementById("adv-rows");
    if (!el) return;
    const hex = w => "0x" + w.toString(16).toUpperCase().padStart(8, "0");
    const conf = c => `<span class="tag ${c === "VERIFIED" ? "ok-tag" : "prop-tag"}">${c}</span>`;
    const mirror = document.getElementById("gb-mirror").checked;
    el.innerHTML = ADVANCED.map(it => {
      const ffSteps = it.steps.filter(s => s.kind === "ff");
      // task 32: last-wins presence per step — FF words through the shared
      // lastWinsStatus, DIRECT rows by delta-bit containment in the dump
      // rows; IFF macro words have no block replay, never "present".
      const stOf = s => s.kind === "ff" ? lastWinsStatus(advEffWord(s))
        : s.kind === "direct" && directStepPresent(s) ? { state: "present" } : null;
      const checkedSteps = it.steps.filter(s => s.kind !== "iff");
      const effSteps = checkedSteps.filter(s => stOf(s) && stOf(s).state === "present");
      const itemBadge = checkedSteps.length && effSteps.length === checkedSteps.length
        ? ` <span class="tag ok-tag">ALREADY PRESENT — no burn needed</span>`
        : effSteps.length
          ? ` <span class="tag prop-tag">PARTIALLY PRESENT (${effSteps.length}/${checkedSteps.length}: ` +
            effSteps.map(s => s.kind === "ff" ? hex(s.value) : `rows ${s.rows.join("/")}`).join(", ") +
            `)</span>`
          : "";
      const selFf = ffSteps.filter(s => advStepSelected(it.id, s));
      const entries = burnQueue.map(q => ({word: q.word, mirror: !!q.mirror, customRow: q.customRow}));
      // task 35c: a step whose word is already in the queue shows the QUEUE's
      // row — one word, one row; no second allocation for the same word.
      const qIdx = {};
      burnQueue.forEach((q, i) => { if (!(q.word in qIdx)) qIdx[q.word] = i; });
      const extra = {};
      selFf.forEach(s => { const w = advEffWord(s); if (!(w in qIdx) && !(w in extra)) { extra[w] = entries.length; entries.push({word: w, mirror}); } });
      const asg = assignRows(entries);
      // task 35g: steps render as the same table shape as the burn cards;
      // PROPOSED / VERIFIED / TESTED tags are kept per row.
      let stepsHtml = `<table class="pbtable"><thead><tr><th></th><th>Word</th>` +
        `<th>Target row</th><th>Field</th><th>Tags</th><th>Notes</th></tr></thead><tbody>`;
      it.steps.forEach((s, si) => {
        const st = stOf(s);
        const badge = st && st.state === "present"
          ? ` <span class="tag ok-tag">ALREADY PRESENT${st.row !== undefined ? ` (row ${st.row})` : ""}</span>`
          : st && st.state === "superseded"
            ? ` <span class="tag prop-tag">SUPERSEDED at row ${st.byRow}</span>`
            : "";
        if (s.kind === "ff") {
          const eff = advEffWord(s);
          const recomputed = eff !== s.value;
          const on = advStepSelected(it.id, s);
          const a = on && asg ? asg.rows[eff in qIdx ? qIdx[eff] : extra[eff]] : null;
          const rowCell =
            !on ? `<span class="note">not selected</span>`
            : !asg ? `<span class="note">rows pending</span>`
            : a === null ? `<b class="bad">NO FREE ROW (block ${s.block})</b>`
            : `<b data-advrow="${it.id}:${a.row}${a.mirror ? "+" + (a.row + 1) : ""}">row ${a.row}${a.mirror ? ` + mirror ${a.row + 1}` : ""}</b>`;
          stepsHtml += `<tr class="pbrow${on ? "" : " pboff"}">` +
            `<td><input type="checkbox" class="psel" data-sel-adv="${it.id}:${si}"${on ? " checked" : ""} ` +
              `title="include this word in the queue"></td>` +
            `<td class="mono">${hex(eff)}</td>` +
            `<td>${rowCell}</td>` +
            `<td class="note">chain ${s.chain} · block ${s.block} · ${esc(s.field)}</td>` +
            `<td><span class="tag prop-tag">PROPOSED</span> ${conf(s.confidence)}${badge}</td>` +
            `<td class="note">` +
              (recomputed ? `<b class="ok">recomputed from this card's defect words</b> (tested sample was ${hex(s.value)})<br>` : "") +
              // task 41: fields whose defect plane is missing from this
              // dump carry the card's current word — say so explicitly,
              // never silently (evidence/40 §3).
              (((window.__perDieCarried || {})[s.block]) || [])
                .map(n => `<b class="warn">no ${n.replace(/_DISABLE$/, "")} defect readout in this dump — current word carried</b><br>`).join("") +
              (s.other_burn !== undefined ? `<b class="warn">per-die variant: another tested card burned ${hex((s.value & 0xFFFF) | ((s.other_burn & 0xFFFF) << 16))} (defect-driven)</b><br>` : "") +
              (s.note ? esc(s.note) : "") + `</td></tr>`;
          return;
        }
        const isDirect = s.kind === "direct";
        stepsHtml += `<tr class="pbrow">` +
          `<td><span class="note">—</span></td>` +
          `<td class="mono">rows ${s.rows.join(" / ")}${isDirect ? " Δ " + hex(s.delta) : " = " + s.words.map(hex).join(" + ")}</td>` +
          `<td><span class="note">manual</span></td>` +
          `<td class="note">${esc(isDirect ? s.field : s.decode)}</td>` +
          `<td><span class="tag">MANUAL</span> ${conf(s.confidence)}${badge}</td>` +
          `<td class="note">${isDirect ? "DIRECT row — manual burn path (queue burns FF records only)" : "IFF word — manual burn path (ff_policy refuses bit 5)"}${s.note ? " · " + esc(s.note) : ""}</td></tr>`;
      });
      stepsHtml += `</tbody></table>`;
      return `<div class="planrow" data-adv-item="${it.id}" style="margin-top:10px">` +
        `<div><b>${esc(it.name)}</b> <span class="tag prop-tag">PROPOSED</span> ` +
        conf(it.confidence) +
        (it.badge ? ` <span class="tag ${it.badge.scope === "INTERNAL" ? "ok-tag" : "prop-tag"}" title="burn proven by executed cards — scope: ${esc(it.badge.scope.toLowerCase())}">${esc(it.badge.label)} · ${esc(it.badge.scope)}</span>` : "") +
        itemBadge +
        (ffSteps.length
          ? ` <button class="btn" data-adv-add="${it.id}">+ queue</button>`
          : ` <span class="note">no queueable FF records — manual burn path only</span>`) +
        `</div>` +
        `<div class="note">${esc(it.notes)}</div>` +
        stepsHtml + `</div>`;
    }).join("");
    el.querySelectorAll("[data-sel-adv]").forEach(c => c.onchange = () => {
      const [id, si] = c.dataset.selAdv.split(":");
      advSel[id + ":" + si] = c.checked;
      renderQueue();
    });
    el.querySelectorAll("[data-adv-add]").forEach(b => b.onclick = () => {
      const it = ADVANCED.find(a => a.id === b.dataset.advAdd);
      if (!it) return;
      const mir = document.getElementById("gb-mirror").checked;
      let n = 0;
      it.steps.forEach((s, si) => {
        if (s.kind === "ff" && advStepSelected(it.id, s)) { queueAdd(advEffWord(s), it.name, undefined, mir); n++; }
      });
      if (!n) { note(`advanced unlock “${it.name}”: no FF word selected — nothing queued`, "warnl"); return; }
      note(`advanced unlock “${it.name}” queued (${n} selected word(s)) — irreversible OTP writes; defect-derived words recomputed from THIS card, config words carry tested values`, "warnl");
    });
  }
  function renderQueue() {
    // task 30: proposed rows (suggested card + advanced card) are computed
    // over the CURRENT queue — keep them in step with every queue change.
    // task 35c: the INTENDED-state panel too (its rows now offset the queue).
    renderPlan(); renderAdvanced(); renderProposedBurns();
    const el = document.getElementById("queue-rows");
    if (!burnQueue.length) { el.innerHTML = `<span class="note">queue empty — add suggested or custom records</span>`; updateQueueCard(); return; }
    // task 27: show each entry's assigned row through the SAME allocator the
    // burn payload uses — what the queue displays IS what it will burn.
    const asg = assignRows(burnQueue);
    // task 35e: same table shape as the proposed-burns panel.
    el.innerHTML = `<table class="pbtable"><thead><tr><th>#</th><th>Word</th>` +
      `<th>Target row</th><th>Field</th><th>Status</th><th>Via</th><th></th></tr></thead><tbody>` +
      burnQueue.map((q, i) => {
        const f = ffEffect(q.word);
        const st = lastWinsStatus(q.word);
        const a = asg ? asg.rows[i] : null;
        const rowCell = asg ? (a !== null
            ? `<span class="mono" data-qrow="${a.row}${a.mirror ? "+" + (a.row + 1) : ""}">row ${a.row}${a.mirror ? ` + mirror ${a.row + 1}` : ""}</span>`
            : `<b class="bad">NO FREE ROW (block ${ffDecode(q.word).blk})</b>`) : "";
        const statusCell = st && st.state === "present"
            ? `<span class="tag prop-tag">⚠ already present — likely no-op (row ${st.row})</span>`
            : st && st.state === "superseded"
              ? `<span class="tag prop-tag">SUPERSEDED at row ${st.byRow}</span>`
              : `<span class="note">—</span>`;
        // task 67 (UX66 F4): while/after a burn campaign the Status column
        // shows the SERVER's per-record result (stats.burned) — the table
        // the operator queued from IS the results table.
        const res = a ? burnResultFor(a) : null;
        // task 67 (UX66 F5-lite): Check-queue preview verdict, bound to the
        // exact (row, word) — a re-allocation drops the stale verdict.
        const vd = a ? queueVerdicts[a.row + ":" + q.word] : null;
        const vdCell = vd
          ? `<br><span class="tag ${vd === "SAFE TO BURN" ? "ok-tag" : "prop-tag"}" title="Check queue preview: ${esc(vd)}">preview: ${esc(vd)}</span>`
          : "";
        return `<tr class="pbrow${st && st.state === "present" ? " qwarn" : ""}">` +
          `<td class="mono">#${i + 1}</td>` +
          `<td class="mono">0x${q.word.toString(16).toUpperCase().padStart(8, "0")}</td>` +
          `<td>${rowCell}</td>` +
          `<td class="note">${esc(f.key)}${f.field === "DEVID" ? ` → 0x${f.devid.toString(16).toUpperCase()}` : ""}` +
          (ffDecode(q.word).ch && !ffDecode(q.word).iff
            ? `<br><span class="note">two-step: inert → arm</span>` : "") + `</td>` +
          `<td>${(res ? burnResultTag(res) : statusCell) + vdCell}</td>` +
          `<td class="note">${esc(q.src)}</td>` +
          `<td><button class="btn" data-q-del="${i}">✕</button></td></tr>`;
      }).join("") + `</tbody></table>`;
    // verdicts bind to (row, word): prune entries the queue no longer holds
    const live = new Set();
    if (asg) asg.rows.forEach((a, i) => { if (a) live.add(a.row + ":" + burnQueue[i].word); });
    Object.keys(queueVerdicts).forEach(k => { if (!live.has(k)) delete queueVerdicts[k]; });
    el.querySelectorAll("[data-q-del]").forEach(b => b.onclick = () => {
      burnQueue.splice(+b.dataset.qDel, 1); renderQueue(); });
    updateQueueCard();
  }
  // task 67 (UX66 F4): map the assigned row (or its mirror) to the burn
  // result reported by /api/glitch/status stats.burned.
  function burnResultFor(a) {
    if (!burnResults || a === null) return null;
    const r = burnResults[a.row] !== undefined ? burnResults[a.row]
              : (a.mirror ? burnResults[a.row + 1] : undefined);
    if (r !== undefined && r !== null) return r;
    return burnPending ? "pending" : null;
  }
  function burnResultTag(res) {
    if (res === "pending") return `<span class="note">pending</span>`;
    if (res === "VERIFY OK") return `<span class="tag ok-tag">VERIFY OK</span>`;
    if (res === "ALREADY BURNED") return `<span class="tag prop-tag">ALREADY BURNED</span>`;
    return `<b class="bad">${esc(String(res))}</b>`;   // ABORT … / VERIFY FAIL / …
  }
  // ---- shared free-row assignment (task 27, single source) ----
  // The layout rows are assigned against: the live card's FF layout when
  // present, else the SHOWN dump's own ff_layout (embedded by dumps_get
  // with the same zone math server-side) — so proposals name exact rows
  // even while browsing saved dumps with no card.
  function burnLayout() {
    if (ffLayout && ffLayout.burn_zone) return ffLayout;
    const L = (D && D.ff_layout) || null;
    return L && L.burn_zone ? L : null;
  }
  // Assign free rows to entries in QUEUE ORDER using PER-BLOCK last-wins
  // placement (task 31): the controller replays FF records in row order and
  // the LAST record per block wins, so a word for block B lands at the
  // first blank row strictly after the last row holding a record for block
  // B (L.last_row_for_block, server-computed); a block with no history
  // starts at ff_start. Rows already taken earlier in the same batch are
  // skipped, mirror pairs keep even-alignment. No global burn-zone bound:
  // the buffer-after-last-occupied heuristic collapsed the burn zone on
  // already-burned cards whose records scatter to the end of the region.
  // queueRecords(), the queue display, the INTENDED-state proposal panel
  // and the Advanced card all go through this one function, so proposed
  // rows == queued rows by construction. Returns
  // {rows: [{row, mirror}|null], exhaustedAt, noFree} — rows[i] is null
  // only for the word whose own block has no free row (exhaustedAt is the
  // first such index, noFree their count; other words still get rows) —
  // or null when no layout is known. The server re-validates every row
  // against ff_policy at burn time; this only picks plausible candidates
  // so the common case needs no manual row typing.
  function assignRows(entries) {
    const L = burnLayout();
    if (!L) return null;
    // Occupancy is judged by VALUE, not key presence: real dumps contain
    // every row key 0..487, blanks included, with value 0x0/0xFFFFFFFF
    // (same blank rule as the row table and the server's ff_layout_from_rows).
    const dumpRows = D.rows || {};
    const used = new Set(Object.keys(dumpRows).map(Number).filter(r => {
      const v = dumpRows[r];
      return typeof v === "number" && v !== 0 && v !== 0xFFFFFFFF;
    }));
    // task 35c: explicitly typed rows are reserved BEFORE auto-allocation —
    // two burns must never share a row (fuses only OR; a second record on
    // an occupied row corrupts the first). A custom row that collides with
    // the dump or with another custom row is reported, not silently shared.
    const customClash = [];
    for (const q of entries) if (q.customRow) {
      const r = +q.customRow;
      if (used.has(r)) customClash.push(r);
      used.add(r);
      if (q.mirror) used.add(r + 1);
    }
    const blockLast = {};
    const raw = L.last_row_for_block || {};
    Object.keys(raw).forEach(k => { blockLast[+k] = raw[k]; });
    const cur = {};   // block -> next candidate row (advances past rows this batch took)
    const alloc = (word, mirror) => {
      const blk = ffDecode(word).blk;
      let c = cur[blk] !== undefined ? cur[blk]
        : Math.max(L.ff_start, (blockLast[blk] !== undefined ? blockLast[blk] : L.ff_start - 1) + 1);
      if (mirror && (c & 1)) {
        // Keep mirror pairs even-aligned: an odd row is consumed as padding.
        // When the odd row is already used (the previous pair's mirror
        // partner) just advance — the while loop below skips the rest.
        used.add(c);
        c++;
      }
      while (used.has(c) && c <= L.ff_end) c++;
      if (c > L.ff_end) { cur[blk] = c; return null; }
      used.add(c);
      cur[blk] = c + 1;
      if (mirror) { used.add(c + 1); cur[blk] = c + 2; }
      return c;
    };
    const rows = [];
    let exhaustedAt = -1, noFree = 0;
    entries.forEach((q, i) => {
      const row = q.customRow || alloc(q.word, !!q.mirror);
      if (row === null || row === undefined) {
        if (exhaustedAt < 0) exhaustedAt = i;
        noFree++; rows.push(null); return;
      }
      rows.push({row, mirror: !!q.mirror});
    });
    return {rows, exhaustedAt, noFree, customClash};
  }
  function queueRecords() {
    if (!burnLayout()) {
      alert("FF layout not loaded — reload the page before burning the queue");
      return null;
    }
    const res = assignRows(burnQueue);
    if (res.exhaustedAt >= 0) {
      alert(`no free row after the last record for ${res.noFree} queued ` +
            `word(s)' block — shrink the queue`);
      return null;
    }
    if (res.customClash && res.customClash.length) {
      alert(`row(s) ${[...new Set(res.customClash)].join(", ")} claimed by two records — ` +
            `remove the duplicate custom row before burning (fuses OR; sharing a row corrupts both)`);
      return null;
    }
    return res.rows.map((r, i) => ({row: r.row, value: burnQueue[i].word,
                                    old: (D.rows || {})[r.row] || 0,
                                    mirror: r.mirror}));
  }
  function queuePlanRecords() {
    // single queue path for the planner's records: used by "Queue all needed
    // records" here AND by the INTENDED-state "Queue these burns" button
    // (task 26) — same records, no divergence. task 32: only the SELECTED
    // words are queued (selection shared with the proposed panel); already-
    // present words the user re-checked queue anyway and the queue row
    // carries the "already present — likely no-op" warn tag. Mirror follows
    // the burn form's "burn mirror row too" setting — the same setting the
    // proposal panel reads — so the queued rows equal the proposed rows.
    const mirror = document.getElementById("gb-mirror").checked;
    let n = 0;
    for (const p of suggestPlan()) for (const w of (p.pair ? p.words : [p.word]))
      // task 35c: skip words already in the queue — one word, one row.
      if (planWordSelected(w) && !burnQueue.some(q => q.word === w)) { queueAdd(w, p.label, undefined, mirror); n++; }
    if (!n) { note("nothing new to queue — selected words already queued or none selected", "warnl"); return; }
    note(`${n} selected record(s) queued — review the queue, then start the campaign in burn mode`, "okl");
  }
  document.getElementById("plan-queue-all").onclick = queuePlanRecords;
  document.getElementById("plan-sel-all").onclick = () => setAllPlanWordsSelected(true);
  document.getElementById("plan-sel-none").onclick = () => setAllPlanWordsSelected(false);
  // advanced card: one affordance for every FF word of every item
  document.getElementById("adv-sel-all").onclick = () => setAllAdvStepsSelected(true);
  document.getElementById("adv-sel-none").onclick = () => setAllAdvStepsSelected(false);
  // task 26: the INTENDED-state panel (top-level scope) renders from this
  // exact planner and queues through this exact path — single source.
  window.__suggestPlan = suggestPlan;
  window.__ffEffect = ffEffect;
  // task 32: the proposed panel reads/writes the SAME selection state.
  window.__planWordSelected = planWordSelected;
  window.__setPlanWordSelected = setPlanWordSelected;
  window.__setAllPlanWordsSelected = setAllPlanWordsSelected;
  // task 27: the proposal panel's row assignment = this exact allocator over
  // the exact queue order, the SELECTED words and the exact mirror setting
  // "Queue these burns" will use — proposed rows ARE the rows the queue
  // will assign.
  window.__planRowAssignment = () => {
    const mirror = document.getElementById("gb-mirror").checked;
    // task 35c: allocate over (queue + selected proposed words NOT already
    // queued) so proposed rows never collide with rows the queue already
    // took; the panel indexes rows from 0 = its own words only.
    const entries = burnQueue.map(q => ({word: q.word, mirror: !!q.mirror, customRow: q.customRow}));
    const queued = new Set(burnQueue.map(q => q.word));
    for (const p of suggestPlan())
      for (const w of (p.pair ? p.words : [p.word]))
        if (planWordSelected(w) && !queued.has(w)) entries.push({word: w, mirror});
    const asg = assignRows(entries);
    if (asg) {
      asg.rows = asg.rows.slice(burnQueue.length);
      if (asg.exhaustedAt >= 0) asg.exhaustedAt -= burnQueue.length;
    }
    return asg;
  };
  window.__queueProposedBurns = () => { queuePlanRecords(); switchTab("glitch"); };
  document.getElementById("queue-clear").onclick = () => { burnQueue = []; renderQueue(); };
  document.getElementById("cq-row").oninput = document.getElementById("cq-value").oninput = () => {
    const v = parseInt($("cq-value").value, 16);
    const el = document.getElementById("cq-decode");
    if (isNaN(v)) { el.innerHTML = ""; return; }
    const f = ffDecode(v);
    const ef = ffEffect(v);
    el.innerHTML = `decode: chain ${f.ch} · ${f.iff ? '<b class="warn">IFF — REFUSED (bit 5 set)</b>' : `block ${f.blk} · data 0x${f.data.toString(16)}`} · ${esc(ef.key)}`;
  };
  document.getElementById("cq-add").onclick = () => {
    const rowStr = document.getElementById("cq-row").value.trim();
    const row = +rowStr;
    if (rowStr === "" || !Number.isInteger(row)) {
      alert("custom record: target row is empty — type a row or press 'first free FF row'; no default row is assumed");
      return;
    }
    const vStr = document.getElementById("cq-value").value.trim();
    const v = parseInt(vStr, 16);
    if (vStr === "" || isNaN(v)) { alert("custom record: value is empty — type the FF record hex word"); return; }
    const mirror = document.getElementById("cq-mirror").checked;
    queueAdd(v, `custom row ${row}${mirror ? " + mirror" : ""}`, row, mirror);
  };
  document.getElementById("cq-firstfree").onclick = () => {
    const r = firstBlankFFRow();
    if (r === null) {
      alert("no blank FF row (≥222) in the loaded dump — run a full dump first (⟳ on the Fuse Explorer tab)");
      return;
    }
    const el = document.getElementById("cq-row");
    el.value = String(r);
    el.dispatchEvent(new Event("input"));
  };
  // task 69: the SKU dropdown is the normal path — words AND rows come from
  // the server plan (/api/rebrand/plan: live layout + ff_policy, DEVIDA
  // first then DEVIDB on the next legal row). Typed hex survives only behind
  // "custom…" as the advanced fallback (client-side encode, allocator rows).
  const rebrandSku = $("plan-rebrand-sku");
  rebrandSku.onchange = () => {
    document.getElementById("plan-devid-wrap").style.display =
      rebrandSku.value === "custom" ? "" : "none";
  };
  document.getElementById("plan-devid-add").onclick = async () => {
    const noteEl = document.getElementById("plan-devid-note");
    const sku = rebrandSku.value;
    let recs;
    if (sku === "custom") {
      let dv = parseInt(document.getElementById("plan-devid").value, 16);
      if (isNaN(dv) || dv < 0x100 || dv > 0xFFFF) {
        noteEl.innerHTML = `<span class="warn">invalid devid (use 0x100–0xFFFF, e.g. 0x20B5)</span>`; return; }
      // data = devid << 1: the DATA word's low bit is always 0 by construction
      // (the skill's reference encodes 0x20B5 -> data 0x416A directly).
      recs = [{word: encFF(2, 37, dv << 1), label: `DEVIDA → 0x${dv.toString(16).toUpperCase()}`},
              {word: encFF(2, 38, dv << 1), label: `DEVIDB → 0x${dv.toString(16).toUpperCase()}`}];
    } else {
      let plan;
      try { plan = await jget(`/api/rebrand/plan?sku=${encodeURIComponent(sku)}`); }
      catch (e) { noteEl.innerHTML = `<span class="warn">rebrand plan failed: ${esc(String(e))}</span>`; return; }
      if (plan.error || !(plan.records || []).length) {
        noteEl.innerHTML = `<span class="warn">rebrand plan: ${esc(plan.error || "no records")}</span>`; return; }
      recs = plan.records.map(r => ({word: r.value, label: r.label, row: r.row}));
    }
    const dup = recs.filter(r => burnQueue.some(q => q.word === r.word));
    if (dup.length) {   // TASK69-DUP: refuse to queue a DEVID pair twice
      noteEl.innerHTML = `<span class="warn">DEVID pair already in queue (${dup.map(d => esc(d.label)).join(", ")}) — not added</span>`; return; }
    for (const r of recs) queueAdd(r.word, r.label, r.row, false);
    note("DEVID pair queued — identity change takes effect at next cold boot", "okl");
  };

  // ---- target GPU selector (live Goldilocks state) ----
  function gpuOption(g, defBdf) {
    const badge = g.goldilocks ? "● Goldilocks" :
                  g.error ? "⚠ unreadable" : "locked";
    return `<option value="${esc(g.bdf)}">${esc(g.bdf)} — ${badge}` +
      (g.bdf === defBdf ? " (default)" : "") + `</option>`;
  }
  async function loadGpus() {
    try {
      const j = await jget("/api/gpus");
      if (j.error && !(j.gpus || []).length) {
        const p = $("gb-gpustate");
        p.textContent = "⚠ " + j.error; p.className = "pill badl";
        return;
      }
      const sel = $("gb-gpu");
      followNote("gb-follow", j.default_note);
      const prev = targetBdf || j.default;
      const sig = (j.gpus || []).map(g => g.bdf + (g.goldilocks ? "+" : "-")).join();
      if (sel.dataset.sig !== sig) {           // rebuild only when the set changes
        sel.dataset.sig = sig;
        sel.innerHTML = (j.gpus || []).map(g => gpuOption(g, j.default)).join("");
        const match = (j.gpus || []).find(g => g.bdf === prev) || (j.gpus || [])[0];
        if (match) { sel.value = match.bdf; targetBdf = match.bdf; }
      }
      updateGpuState(j);
    } catch (e) {}
  }
  function updateGpuState(j) {
    const g = (j.gpus || []).find(x => x.bdf === targetBdf);
    const pill = $("gb-gpustate");
    goldilocksNow = !!(g && g.goldilocks);
    if (!g) {
      pill.textContent = "no GA100 detected"; pill.className = "pill warnl";
    } else if (g.goldilocks) {
      // 4-check privilege unlock (dsov/crc/priv/fpf) — survives Revert VRM
      // until power cycle. It is NOT the burn window; label it honestly.
      if (windowOk) {
        pill.textContent = "● Goldilocks — burn window OPEN";
        pill.className = "pill okl";
      } else {
        pill.textContent = "● unlocked — window closed (glitch to open)";
        pill.className = "pill warnl";
      }
    } else if (g.error) {
      pill.textContent = "⚠ " + g.error; pill.className = "pill badl";
    } else {
      pill.textContent = "locked (DSOV=" + g.dsov + ") — glitch first";
      pill.className = "pill";
    }
    $("gb-gpuserial").innerHTML =
      (g.serial ? "SN " + esc(g.serial) : "no serial") +
      (g.driver ? " · driver " + esc(g.driver) : " · no driver");
    updateQueueCard();
  }
  $("gb-gpu").onchange = () => {
    targetBdf = $("gb-gpu").value; payloadChecked = null;
    updateQueueCard();
    $("gb-checkresult").innerHTML = "";
    $("gb-editwarn").style.display = "none";
    loadGpus();
    loadLayout();
  };
  loadGpus();   // refreshed on demand + when the Glitch tab is shown
  // goldilocksNow gates the Arm & burn button; the window state changes
  // outside any tab interaction (campaigns, decay, reverts) — poll it.
  setInterval(loadGpus, 3000);

  // ---- FF placement policy (row map + budget + live row hint) ----
  let ffLayout = null;
  // task 30: paint the advanced-unlock card at setup (works with no dump
  // loaded — TESTED badge shows, target rows say "pending").
  // Must run AFTER the ffLayout declaration: renderAdvanced → assignRows →
  // burnLayout reads it, and `let` is in TDZ before its declaration.
  renderAdvanced();
  function renderFfMap() {
    const L = ffLayout;
    if (!L || !L.burn_zone) return;
    const total = L.ff_end - L.ff_start + 1;
    const seg = (a, b, cls, label) => {
      if (b < a) return "";
      const w = ((b - a + 1) / total * 100).toFixed(2);
      return `<div class="seg ${cls}" style="width:${w}%" title="rows ${a}–${b}">${label}</div>`;
    };
    $("gb-ffmap").innerHTML =
      seg(L.ff_start, L.last_occupied, "occ", `boot FFs · ${L.occupied_count}`) +
      seg(L.last_occupied + 1, L.burn_zone[0] - 1, "buf", `buffer ${L.buffer}`) +
      seg(L.burn_zone[0], L.burn_zone[1], "zone", `BURN ZONE · ${L.free_in_zone} free`) +
      seg(L.sm_zone[0], L.sm_zone[1], "smr", `SM reserve ${L.sm_reserve}`) +
      seg(L.revert_zone[0], L.revert_zone[1], "rev", `revert ${L.tail_reserve}`);
    $("gb-budget").innerHTML = L.global_zone_empty
      ? `global burn zone empty — last boot FF row <b>${L.last_occupied}</b>; ` +
        `placement is <b>per-block</b>: each record lands after its own ` +
        `block's last record (rows ${L.ff_start}–${L.ff_end})`
      : `safe zone rows <b>${L.burn_zone[0]}–${L.burn_zone[1]}</b> · <b>${L.free_in_zone}</b> free · last boot FF: row ${L.last_occupied}`;
    // B25: never rewrite the user's typed row — updateRowHint shows the zone
    // verdict for whatever row is in the field (a deliberate probe of the SM
    // reserve must survive tab switches and layout refreshes).
    updateRowHint();
  }
  function updateRowHint() {
    const hint = $("gb-rowhint");
    const rv = +$("gb-row").value;
    if ($("gb-row").value.trim() === "" || !Number.isInteger(rv)) {
      hint.innerHTML = "row —"; hint.className = "pill"; return;
    }
    if (!ffLayout || !ffLayout.burn_zone) { hint.innerHTML = "row —"; hint.className = "pill"; return; }
    const L = ffLayout;
    let txt, cls;
    if (L.global_zone_empty) {
      // Task 31: on an already-burned card the global zones are display
      // only — the verdict for a typed row is per-block (blank + after the
      // row's block's last record), which the server enforces at burn time.
      txt = `row ${rv}: per-block placement — must be blank and after its block's last record`;
      cls = "warn";
    }
    else if (rv >= L.burn_zone[0] && rv <= L.burn_zone[1]) { txt = `row ${rv}: ✓ safe zone`; cls = "ok"; }
    else if (rv < L.ff_start || rv > L.ff_end)       { txt = `row ${rv}: ✗ outside FF region`; cls = "bad"; }
    else if (rv <= L.last_occupied)                  { txt = `row ${rv}: ✗ occupied (boot FF)`; cls = "bad"; }
    else if (rv < L.burn_zone[0])                    { txt = `row ${rv}: ✗ buffer zone`; cls = "bad"; }
    else if (rv >= L.revert_zone[0])                 { txt = `row ${rv}: ✗ revert tail (keep free)`; cls = "bad"; }
    else if (rv >= L.sm_zone[0])                     { txt = `row ${rv}: ✗ SM reserve (keep free)`; cls = "bad"; }
    else                                             { txt = `row ${rv}: ✗`; cls = "bad"; }
    hint.className = "pill";
    hint.innerHTML = `<b class="${cls}">${txt}</b>`;
  }
  $("gb-row").oninput = () => { invalidateChecked(); updateRowHint(); };
  async function loadLayout() {
    try {
      const q = targetBdf ? "?bdf=" + encodeURIComponent(targetBdf) : "";
      const j = await jget("/api/ff/layout" + q);
      if (j.error) { $("gb-budget").textContent = "⚠ " + j.error; return; }
      ffLayout = j;
      renderFfMap();
    } catch (e) {}
  }
  loadLayout();

  // ---- pico port selector ----
  let portOk = true;   // false = nothing startable; gates campaign start
  async function loadPorts() {
    try {
      const j = await jget("/api/ports");
      portOk = j.default != null;   // server returns null when nothing is present
      const sel = $("gc-port");
      const cur = (sel.value && sel.value.indexOf("scanning") < 0) ?
                  sel.value : (j.default || "");
      const ports = (j.ports || []).slice().
        sort((a, b) => (a.pico ? 0 : 1) - (b.pico ? 0 : 1));
      const label = p =>
        (p.byid ? `${esc(p.byid)} (${esc(p.path)})` : esc(p.path)) +
        (p.pico ? " (pico)" : p.vendor ? ` — ${esc(p.vendor)}` : "");
      sel.innerHTML = ports.map(p =>
        `<option value="${esc(p.path)}" ${p.path === cur ? "selected" : ""}>` +
        label(p) + `</option>`).join("") ||
        `<option value="" disabled selected>no pico detected</option>`;
      $("gc-portnote").textContent = j.note || "";
      $("gc-start").disabled = !portOk;
      $("gc-start").title = portOk ? "" : "no pico detected — ⟳ rescan";
    } catch (e) {}
  }
  $("gc-ports-refresh").onclick = loadPorts;
  $("gc-flash").onclick = async () => {
    const b = $("gc-flash"), st = $("gc-flashstate");
    b.disabled = true; st.className = "note";
    st.textContent = "rebooting pico into BOOTSEL, writing uf2… (~15 s)";
    try {
      const j = await jpost("/api/pico/flash", {port: $("gc-port").value});
      if (j.error) {
        st.className = "bad";
        st.textContent = "⚠ flash: " + j.error +
          (j.steps && j.steps.length ? " — " + j.steps.join("; ") : "");
      } else {
        st.className = j.banner ? (j.fw_marker ? "ok" : "warn") : "warn";
        st.textContent = "flashed " + (j.uf2 || "").split("/").pop() + ": " +
          (j.banner || "wrote ok but " + (j.note || "port did not return"));
      }
    } catch (e) { st.className = "bad"; st.textContent = "⚠ " + e; }
    b.disabled = false;
    loadPorts();          // the port re-enumerates after a flash
  };
  loadPorts();

  // task 67 (UX66 F1/F6) + task 68 (owner verdict on UX66 F2): the ONE
  // burn trigger on the page — label carries the queue size and, after a
  // queue_start, the remaining token seconds; the one-line refusal reason
  // is visible next to it, not only in a tooltip. The payload panel is a
  // read-only row probe; it can no longer arm or burn.
  function updateQueueCard() {
    const btn = $("bq-armburn");
    if (!btn) return;
    let label = "⚡ Arm & burn queue (" + burnQueue.length + ")";
    if (armToken && Date.now() < armExpiry)
      label += " · armed " + Math.ceil((armExpiry - Date.now()) / 1000) + "s";
    btn.textContent = label;
    const reason = !burnQueue.length ? "queue empty — add records below"
      : campaignRunning ? "campaign already running"
      : !targetBdf ? "no GPU selected"
      : !(windowOk || goldilocksNow)
        ? "GPU not Goldilocks — glitch into the window first" : "";
    btn.disabled = !!reason;
    btn.title = reason || "arm (Goldilocks + identity gate) and start the " +
      "burn campaign in ONE server call — irreversible OTP writes";
    const r = $("bq-reason");
    if (r) r.textContent = reason || r.textContent;   // keep success note when enabled
  }
  setInterval(updateQueueCard, 1000);

  // Truthful burn-window indicator (UX66 F3): /api/live carries the
  // read-only window verdict computed by the server poller (window_ok +
  // window_checks). ONE poll computes windowState; every window widget
  // renders from it — no second source of truth.
  function windowPillView() {
    const s = windowState.state;
    if (s === "OPEN") return {t: "burn window: OPEN", c: "pill okl"};
    if (s === "n/a") return {t: "burn window: n/a", c: "pill warnl"};
    return {t: "burn window: closed" + (windowState.bad.length ? " (" + windowState.bad.join(", ") + ")" : ""),
            c: "pill"};
  }
  function renderWindowPills() {
    const v = windowPillView();
    const el = $("bq-window");
    if (el) { el.textContent = v.t; el.className = v.c; }
  }
  async function pollWindow() {
    try {
      const j = await jget("/api/live");
      if (j.window_ok === undefined) {
        windowState = {state: "n/a", bad: []};
      } else if (j.window_ok) {
        windowState = {state: "OPEN", bad: []};
      } else {
        const checks = j.window_checks || [];
        // Binary by owner decision: the live check IS the truth — all
        // window checks pass = OPEN, anything fails = CLOSED. The 2 s
        // poll shows decay as OPEN->closed; no third state. (The card's
        // 4-check privilege unlock survives Revert until power cycle —
        // that is a different fact, shown on the GPU badge, not a window.)
        windowState = {state: "closed",
                       bad: checks.filter(c => !c.ok).map(c => c.name)};
      }
      windowOk = windowState.state === "OPEN";
    } catch (e) {}
    renderWindowPills();
    updateQueueCard();
  }
  setInterval(pollWindow, 2000);
  pollWindow();

  // ---- burn value source: typed hex, or grabbed from a dump row ----
  let payloadValue = null;        // set by the dump-row grab (verify target)
  function knownBlock(f) {
    if (f.ch === 1 && f.blk === 19) return " → FBP_DISABLE";
    if (f.ch === 1 && f.blk === 8) return " → GPC_DISABLE";
    return "";
  }
  function renderSrcDecode() {
    const el = $("gb-srcdecode");
    if ($("gb-srcmode").value !== "dump") { el.innerHTML = ""; payloadValue = null; return; }
    const sr = +$("gb-srcrow").value;
    const v = D.rows ? D.rows[sr] : undefined;
    if (v === undefined) {
      payloadValue = null;
      el.innerHTML = `<span class="warn">row ${sr} is not in the loaded dump — ` +
        `run a full dump first (⟳ on the Fuse Explorer tab)</span>`;
    } else if (typeof v !== "number" || v === 0 || v === 0xFFFFFFFF) {
      payloadValue = null;
      el.innerHTML = `<span class="warn">row ${sr} is blank in the dump — ` +
        `nothing to re-apply</span>`;
    } else {
      payloadValue = v;
      const f = ffDecode(v);
      el.innerHTML =
        `<span class="mono">dump row ${sr} → 0x${v.toString(16).toUpperCase().padStart(8, "0")}</span> · ` +
        `${f.iff ? '<b class="warn">IFF (invalidation — will be refused)</b>' : `FF ch${f.ch}·blk${f.blk}·d0x${f.data.toString(16)}`}` +
        `${knownBlock(f)} — verify this is the record you want, then Check`;
    }
  }
  $("gb-srcmode").onchange = () => {
    invalidateChecked();
    const dump = $("gb-srcmode").value === "dump";
    $("gb-dumpwrap").style.display = dump ? "" : "none";
    $("gb-typedwrap").style.display = dump ? "none" : "";
    renderSrcDecode();
  };
  $("gb-srcrow").oninput = () => { invalidateChecked(); renderSrcDecode(); };
  $("gb-value").oninput = invalidateChecked;
  $("gb-mirror").onchange = () => { invalidateChecked(); renderQueue(); };

  // ---- burn-form targets derived from the CURRENT card's loaded dump ----
  // No burn-payload field may carry a value that was not derived from this
  // card's own dump or typed by the user: a pre-filled foreign default on
  // irreversible OTP fields masquerades as a computed target.
  function firstBlankFFRow() {
    // first blank row (0x0 / 0xFFFFFFFF) in the FF record region of the
    // loaded dump; null when no dump is loaded or none is blank.
    const rows = D.rows || {};
    if (!(D.row_count > 0)) return null;
    for (let r = 222; r <= 487; r++) {
      const v = rows[r];
      if (v === 0 || v === 0xFFFFFFFF) return r;
    }
    return null;
  }
  function cardDevidFromDump() {
    // the card's own DEVID from its DEVIDA/B records (chain 2, block 37/38)
    // in the loaded dump; last record per block wins, so keep the last hit.
    const rows = D.rows || {};
    let devid = null;
    Object.keys(rows).map(Number).sort((a, b) => a - b).forEach(r => {
      const v = rows[r];
      if (typeof v !== "number" || v === 0 || v === 0xFFFFFFFF) return;
      const e = ffEffect(v);
      if (e.field === "DEVID") devid = e.devid;
    });
    return devid;
  }
  function refreshBurnFormDefaults() {
    const sr = $("gb-srcrow");
    if (!sr) return;   // glitch pane not built yet
    const blank = firstBlankFFRow();
    if (blank === null) {
      sr.value = "";
      sr.placeholder = "no blank FF row in this dump";
    } else {
      sr.value = String(blank);
      sr.placeholder = "first blank FF row (≥222)";
    }
    renderSrcDecode();
    updateRowHint();
    // DEVID suggestion: keep only what matches the card's own DEVID context
    // (or fill the card's own DEVID when the field is still empty); never
    // leave a foreign demo value standing.
    const dv = $("plan-devid");
    const cardDevid = cardDevidFromDump();
    const cur = parseInt(dv.value, 16);
    if (cardDevid !== null && (cur === cardDevid || dv.value.trim() === "")) {
      dv.value = "0x" + cardDevid.toString(16).toUpperCase().padStart(4, "0");
      dv.placeholder = "0x100–0xFFFF";
    } else {
      dv.value = "";
      dv.placeholder = cardDevid !== null
        ? `card DEVID 0x${cardDevid.toString(16).toUpperCase()} — type new`
        : "0x100–0xFFFF (e.g. 0x20B5)";
    }
    updatePreviewBtn();
  }

  // ---- read-only burn preview: ga100_burn's default preview mode inside
  // the UI. Works ANY time — CMD_READ is gated by FUSECTRL_PLM, not EFP —
  // no window, no arm, no token, and the server path cannot write fuses.
  function currentPayload() {
    const fromDump = $("gb-srcmode").value === "dump";
    const rowStr = $("gb-row").value.trim();
    return {row: rowStr === "" ? NaN : +rowStr,
            value: fromDump ? (payloadValue === null ? "" : "0x" + payloadValue.toString(16))
                            : $("gb-value").value.trim(),
            mirror: $("gb-mirror").checked};
  }
  function updatePreviewBtn() {   // enabled on row+value alone — no window/arm gate
    const p = currentPayload();
    let v = NaN;
    try { v = parseInt(p.value, 0); } catch (e) {}
    $("gb-preview").disabled = !(p.row >= 0 && p.row <= 487 &&
                                 Number.isInteger(v) && v >= 0 && v <= 0xFFFFFFFF);
  }
  ["gb-row", "gb-value", "gb-srcrow"].forEach(id =>
    $(id).addEventListener("input", updatePreviewBtn));
  ["gb-srcmode", "gb-mirror"].forEach(id =>
    $(id).addEventListener("change", updatePreviewBtn));
  updatePreviewBtn();
  refreshBurnFormDefaults();   // seed from the dump embedded in the page

  function decodeSpan(d) {
    if (!d) return `<span class="note">— not a live FF record</span>`;
    return `<span class="mono">chain=${d.chain}${d.iff ? "·IFF" : ""} ` +
      `block=${d.block} data=0x${d.data.toString(16).toUpperCase().padStart(4, "0")}</span>` +
      (d.name ? ` <b class="ok">→ ${esc(d.name)}</b>` : "");
  }
  function bitStrip(v, delta) {   // delta bits highlighted amber
    let h = "";
    for (let i = 31; i >= 0; i--) {
      const set = (v >>> i) & 1, d = (delta >>> i) & 1;
      h += `<span class="bitcell${set ? " bitset" : ""}${d ? " dbit" : ""}" ` +
           `title="bit ${i}${d ? " · delta (0→1)" : ""}">${i}</span>`;
    }
    return `<div class="bits">${h}</div>`;
  }
  function collisionBadge(c) {
    return c.last_wins === "WILL WIN"
      ? `<span class="pill okl">LAST-WINS: will win</span>`
      : `<span class="pill badl">LAST-WINS: will ${esc(c.last_wins)}</span>`;
  }
  function previewHtml(j) {
    const vcls = j.verdict === "SAFE TO BURN" ? "good"
               : j.verdict === "ALREADY BURNED" ? "warnv" : "";
    const rowsHtml = (j.rows || []).map(r =>
      `<div style="margin-top:8px"><b class="mono">row ${r.row}</b> ` +
      `<span class="pill${r.row_verdict === "SAFE TO BURN" ? " okl" : r.row_verdict === "ALREADY BURNED" ? " warnl" : " badl"}">${esc(r.row_verdict)}</span></div>` +
      `<div class="mono">${fmt(r.before)} <b class="warn">Δ ${fmt(r.delta)}</b> → ${fmt(r.after)}</div>` +
      (r.two_step
        ? `<div class="note">two-step: inert <span class="mono">${fmt(r.two_step.step_a_word)}</span> ` +
          `(Δ <span class="mono">${fmt(r.two_step.step_a_delta)}</span>) → arm chain Δ ` +
          `<span class="mono">${fmt(r.two_step.step_b_delta)}</span> — ${esc(r.two_step.note)}</div>`
        : "") +
      bitStrip(r.after, r.delta) +
      `<table><tr><th></th><th>word</th><th>FF decode</th></tr>` +
      `<tr><td>before</td><td class="mono">${fmt(r.before)}</td><td>${decodeSpan(r.decode_before)}</td></tr>` +
      `<tr><td>after</td><td class="mono">${fmt(r.after)}</td><td>${decodeSpan(r.decode_after)}</td></tr></table>`).join("");
    const c = j.collisions || {};
    const colHtml = `<div style="margin-top:10px"><b>collision scan · key ` +
      `chain${c.key ? c.key.chain : "?"}·block${c.key ? c.key.block : "?"}` +
      `${c.name ? " → " + esc(c.name) : ""}</b> ${collisionBadge(c)}` +
      ((c.records || []).length
        ? `<table><tr><th>row</th><th>word</th><th>decode</th></tr>` +
          c.records.map(x => `<tr><td class="mono">${x.row}</td><td class="mono">${fmt(x.word)}</td><td>${decodeSpan(x.decode)}</td></tr>`).join("") + `</table>`
        : c.own_row !== null && c.own_row !== undefined
        ? `<div class="note">record already present at this row (row ${c.own_row}) — re-burn is a no-op/ALREADY path</div>`
        : `<div class="note">no existing record with this key — the burn defines it</div>`) + `</div>`;
    const hz = j.hazards || {};
    const pl = j.plane || {};
    const plHtml = (pl.fields || []).length
      ? `<div style="margin-top:10px"><b>field-plane gate</b> ` +
        (pl.blocking
          ? `<span class="pill badl">REFUSED — ${esc(pl.reason || "")}</span>`
          : `<span class="pill okl">defective units stay masked</span>`) +
        `<table><tr><th>field</th><th>plane before</th><th>plane after</th>` +
        `<th>defective</th><th>dead units enabled after</th></tr>` +
        pl.fields.map(f =>
          `<tr><td>${esc(f.name)}</td>` +
          `<td class="mono">0x${f.before.toString(16).toUpperCase()}</td>` +
          `<td class="mono">0x${f.after.toString(16).toUpperCase()}</td>` +
          `<td class="mono">0x${f.defective.toString(16).toUpperCase()}</td>` +
          `<td class="mono${f.newly_enabled ? " bad" : f.enabled_defective ? " warn" : ""}">` +
          `0x${f.enabled_defective.toString(16).toUpperCase()}` +
          (f.newly_enabled ? ` <b class="bad">NEW</b>` : "") + `</td></tr>`).join("") +
        `</table><div class="note">a record's data word feeds EVERY logical field ` +
        `overlapping its block (last-wins per block) — e.g. block 8 carries the ` +
        `FBPA_DISABLE tail alongside GPC_DISABLE. The resulting plane must keep ` +
        `every DEFECTIVE bit disabled, or the card boots with dead silicon ` +
        `enabled (GFW stall, probe -EIO).</div></div>`
      : "";
    const hzHtml = hz.skipped
      ? `<div class="note" style="margin-top:8px">partial-landing hazards: skipped — ${esc(hz.skipped)}</div>`
      : `<div style="margin-top:8px"><b>partial-landing hazards</b> ` +
        `<span class="note">${(hz.hazards || []).length} hazard · ${hz.benign || 0} benign · ${hz.inert || 0} inert subset(s)</span>` +
        (hz.hazards || []).map(x =>
          `<div class="warn" style="margin-top:3px">⚠ ${x.row !== undefined && (j.rows || []).length > 1 ? `row ${x.row} ` : ""}partial Δ <span class="mono">${fmt(x.subset)}</span> ` +
          `lands <span class="mono">${fmt(x.word)}</span> (${decodeSpan(x.decode)}) — ${esc(x.effect)}</div>`).join("") +
        (hz.two_step_note ? `<div class="note" style="margin-top:3px">${esc(hz.two_step_note)}</div>` : "") + `</div>`;
    const tl = j.two_layout || {};
    const tlHtml = `<div style="margin-top:8px"><b>two-layout check</b> ` +
      `<span class="pill warnl">The Lab · unverified here</span><br>` +
      `<span class="note">If RWL were 1 this word = RIR write to row ` +
      `${tl.rir_row} bit ${tl.rir_bit}</span>` +
      (tl.rir_layout_warning
        ? `<div class="bad" style="margin-top:3px">⚠ RIR control-row region ` +
          `(rows 0–7) — check DEBUGCTRL before burning</div>` : "") + `</div>`;
    const strip = `<div class="frow" style="margin-top:10px">` +
      `<span class="pill ${j.window_ok ? "okl" : ""}">burn window ${j.window_ok ? "open" : "closed"} — not required for preview</span>` +
      `<span class="pill warnl">arm pending — auto-armed at burn (SENSE_CTRL)</span>` +
      `<span class="pill ${j.journal_uncertain ? "badl" : "okl"}">journal ${j.journal_uncertain ? "UNCERTAIN" : "clear"}</span></div>`;
    return `<div class="verdict ${vcls}" style="padding:8px 12px;margin-top:8px">` +
      `<b>${esc(j.verdict)} (preview)</b> — read-only, zero latching writes (row reads use the read command) · ` +
      `${esc(j.bdf || "")} · ${esc(j.ts || "")}</div>` +
      rowsHtml + colHtml + plHtml + hzHtml + tlHtml +
      (j.predicted ? `<div style="margin-top:8px"><b>predicted effect:</b> ${esc(j.predicted)}</div>` : "") +
      strip;
  }
  $("gb-preview").onclick = async () => {
    const p = currentPayload();
    const res = $("gb-previewresult");
    res.innerHTML = "previewing… (read-only — CMD_READ only, no window/arm needed)";
    let j;
    try { j = await jpost("/api/burn/preview", {...p, bdf: targetBdf || ""}); }
    catch (e) { res.innerHTML = `<span class="bad">⚠ ${esc(String(e))}</span>`; return; }
    if (j.error) { res.innerHTML = `<span class="bad">⚠ ${esc(j.error)}</span>`; return; }
    res.innerHTML = previewHtml(j);
  };

  $("gb-check").onclick = async () => {
    const res = $("gb-checkresult");
    const rowStr = $("gb-row").value.trim();
    const row = +rowStr;
    const fromDump = $("gb-srcmode").value === "dump";
    const value = fromDump ? (payloadValue === null ? "" : "0x" + payloadValue.toString(16)) : $("gb-value").value.trim();
    const mirror = $("gb-mirror").checked;
    // client-side refusal for empty inputs (UX only — the server check
    // stays authoritative): no burn target or value is ever assumed.
    if (rowStr === "" || !Number.isInteger(row)) {
      res.innerHTML = `<span class="bad">⚠ target row is empty — pick a row from the Fuse Explorer or the FF audit first; no default row is assumed</span>`;
      payloadChecked = null; updateQueueCard(); return;
    }
    if (value === "") {
      res.innerHTML = `<span class="bad">⚠ value is empty — type the hex word, or pick a non-blank source row in the dump</span>`;
      payloadChecked = null; updateQueueCard(); return;
    }
    res.innerHTML = "checking…";
    $("gb-editwarn").style.display = "none";
    const j = await jget(`/api/burn/check?row=${row}&value=${encodeURIComponent(value)}&mirror=${mirror ? 1 : 0}&bdf=${encodeURIComponent(targetBdf || "")}`);
    if (j.error) { res.innerHTML = `<span class="bad">⚠ ${esc(j.error)}</span>`; payloadChecked = null; return; }
    payloadChecked = {row, value, old: j.current, mirror, bdf: j.bdf || targetBdf};
    // A fresh check is a fresher reading of the SAME window checks — refresh
    // the shared windowState (one variable), never fork a second truth.
    const wc = j.guards || [];
    windowState = j.window_ok ? {state: "OPEN", bad: []}
      : {state: "closed", bad: wc.filter(g => !g.ok).map(g => g.name)};
    windowOk = windowState.state === "OPEN";
    renderWindowPills();
    updateQueueCard();   // refresh the queue-card gate against the fresh check
    // window checks are hard pass/fail; arm_pending bits open at burn time
    // (SENSE_CTRL restores EFP, WDATA_SECURE=0 opens FUSEWDATA_PLM) — amber.
    const guards = (j.guards || []).map(g =>
      `<div class="guardrow"><span class="gs ${g.ok ? "ok" : "bad"}">${g.ok ? "✓" : "✗"}</span>` +
      `<span>${esc(g.name)} = ${typeof g.value === "number" ? fmt(g.value) : esc(String(g.value))}` +
      (g.want !== undefined ? ` (want ${typeof g.want === "number" ? fmt(g.want) : esc(String(g.want))})` : "") +
      `</span></div>`).join("");
    const pending = (j.arm_pending || []).map(g =>
      `<div class="guardrow"><span class="gs warn">•</span>` +
      `<span class="warn">${esc(g.name)} = ${typeof g.value === "number" ? fmt(g.value) : esc(String(g.value))}` +
      (g.want !== undefined ? ` (want ${typeof g.want === "number" ? fmt(g.want) : esc(String(g.want))})` : "") +
      ` — ${esc(g.note || "auto-armed at burn (SENSE_CTRL)")}</span></div>`).join("");
    const pol = j.policy;
    const polBlock = pol ? `<div class="${pol.ok ? "ok" : "bad"}" style="margin-top:6px">` +
      `<b>placement policy: ${pol.ok ? "OK — row is in the safe burn zone" : "VIOLATION"}</b>` +
      (pol.issues || []).map(i => `<div>• ${esc(i)}</div>`).join("") + `</div>` : "";
    const pln = j.plane;
    const plnBlock = pln && (pln.fields || []).length
      ? `<div class="${pln.blocking ? "bad" : "ok"}" style="margin-top:6px">` +
        `<b>plane gate: ${pln.blocking
          ? "REFUSED — " + esc(pln.reason || "")
          : "OK — every touched plane keeps its defective units masked"}</b>` +
        `</div>` : "";
    const did = j.die_id;
    const tl2 = j.two_layout;
    const tl2Block = tl2
      ? `<div class="note" style="margin-top:6px">two-layout check ` +
        `<span class="pill warnl">The Lab · unverified here</span> — ` +
        `if RWL were 1 this word = RIR write to row ${tl2.rir_row} ` +
        `bit ${tl2.rir_bit}` +
        (tl2.rir_layout_warning
          ? `<div class="bad">⚠ RIR control-row region (rows 0–7) — ` +
            `check DEBUGCTRL before burning (burn check)</div>` : "") + `</div>` : "";
    const didBlock = did ? `<div class="${did.ok ? "ok" : "bad"}" style="margin-top:6px">` +
      `<b>identity: ${did.ok
        ? "OK — sn-" + esc(did.serial || "") + (did.checked_against
            ? " · die-ID rows 8-15 match " + esc(did.checked_against)
            : " · die-ID recorded (no prior dump to compare)")
        : "FAIL — " + esc(did.error || "")}</b></div>` : "";
    res.innerHTML =
      `<div><b class="${j.window_ok ? "ok" : "bad"}">${j.window_ok ? "SAFE TO BURN" : "REFUSED"}</b> — ` +
      `burn window ${j.window_ok ? "open" : "not open"} (verdict keys off the window checks, not EFP/WDATA_PLM)</div>` +
      `<div>row ${j.row} on <span class="mono">${esc(j.bdf || targetBdf)}</span> currently reads ` +
      `<span class="mono">${fmt(j.current)}</span> · ` +
      `rows to burn: <span class="mono">${(j.rows_to_burn || [row]).join(", ")}</span></div>` +
      plnBlock + polBlock + didBlock + tl2Block +
      `<div>purity (0→1 superset): <b class="${j.pure_0to1 ? "ok" : "bad"}">${j.pure_0to1 ? "OK" : "FAIL"}</b></div>` +
      `<div class="guardlist">${guards}</div>` +
      (pending ? `<div class="guardlist">${pending}</div>` : "") +
      (pol && !pol.ok ? "" : `<div class="note" style="margin-top:6px">${esc(j.note || "")}</div>`);
    loadLayout();   // budget may have changed
  };

  // campaign
  function setCampaignUI(j) {
    campaignRunning = !!j.running;
    // task 67 (UX66 F4): feed the queue table's Status column from the
    // server's per-record burn results (stats.burned) while/after a burn
    // campaign — re-render only when the results actually change.
    if (j.params && j.params.mode === "burn") {
      const sig = JSON.stringify((j.stats || {}).burned || []) + (j.running ? "r" : "e");
      if (sig !== burnResultsSig) {
        burnResultsSig = sig;
        burnResults = {};
        ((j.stats || {}).burned || []).forEach(b => { burnResults[b.row] = b.result; });
        burnPending = !!j.running;
        renderQueue();
      }
    }
    $("gc-stop").disabled = !j.running;
    $("gc-start").disabled = !!j.running || !portOk;
    $("gc-revert").disabled = !!j.running || !j.window_held;
    const st = $("gc-state");
    st.textContent = j.running ? "● running" : (j.result || (j.error ? "error" : "idle"));
    st.className = "pill " + (j.running || j.result === "goldilocks" ? "okl" :
                              j.error ? "badl" : "");
    const s = j.stats || {};
    // UX66 F3: window_held is a campaign EVENT ("it chose not to revert"),
    // not a live state — the chip says so and shows the LIVE window state
    // from the same windowState the Burn queue pill renders.
    const held = j.window_held
      ? `<span class="pill ${windowState.state === "OPEN" ? "okl" : "warnl"}">campaign ended holding the window — ${esc(windowPillView().t)}</span>` : "";
    $("gc-chips").innerHTML =
      `<span class="pill">attempts <b>${s.attempts || 0}</b></span>` +
      `<span class="pill">valid <b>${s.valid || 0}</b></span>` +
      `<span class="pill">lost <b>${s.lost || 0}</b></span>` +
      `<span class="pill">nack <b>${s.nack || 0}</b></span>` +
      `<span class="pill">dsov=0 <b>${s.dsov_zero || 0}</b></span>` +
      `<span class="pill ${s.goldilocks ? "okl" : ""}">goldilocks <b>${s.goldilocks ? "YES" : "no"}</b></span>` +
      (s.burn_aborts ? `<span class="pill warnl">burn aborts <b>${s.burn_aborts}</b> (not final — attempts keep firing)</span>` : "") +
      (s.image_verify ? `<span class="pill badl">${esc(s.image_verify)} — window NOT held</span>` : "") +
      held;
    if ((j.log || []).length) {
      const logEl = $("gc-log");
      logEl.textContent = j.log.join("\n");
      // autoscroll only while the owner opts in — a pinned-to-bottom log
      // is unreadable mid-campaign (every 2 s poll yanked the view down)
      if ($("gc-autoscroll").checked) logEl.scrollTop = logEl.scrollHeight;
    }
    if (j.error && !j.running) $("gc-log").textContent =
      ($("gc-log").textContent + "\nERROR: " + j.error).trim();
  }
  async function pollGlitch() {
    try { setCampaignUI(await jget("/api/glitch/status")); } catch (e) {}
  }
  // task 51: Lab in-window single-pulse preset — fills the campaign inputs
  // ONLY (never starts a campaign). t_dip +50 us goes to the t_dip field
  // (review fix: was wrongly stuffed into delay). v_restore 750 / t_restore
  // -20 have no console inputs — the firmware's post-dip restore is fixed
  // (docs/PROTOCOL.md invariants).
  $("t51-lab-preset").onclick = () => {
    $("gc-vdip").value = 365; $("gc-tdip").value = 50;
    $("gc-pw").value = 196;   $("gc-pulses").value = 1;
    $("t51-preset-note").textContent =
      "Lab preset filled (v_dip 365, t_dip +50, pw 196, pulses 1) — " +
      "v_restore 750 / t_restore -20 have no console inputs; start manually.";
  };
  function campaignBody(mode) {
    // one builder for every campaign start (gc-start + Arm & burn queue) —
    // the burn queue campaign uses EXACTLY the visible campaign controls.
    return {bdf: targetBdf || undefined,
      adaptive: $("gc-strategy").value === "adaptive",
      min_v: +$("gc-vmin").value, max_v: +$("gc-vmax").value,
      v_dip: +$("gc-vdip").value, pulses: +$("gc-pulses").value,
      pw: +$("gc-pw").value, gap: +$("gc-gap").value, delay: +$("gc-delay").value,
      t_dip: +$("gc-tdip").value,
      cooldown_s: +$("gc-cooldown").value,
      max_attempts: +$("gc-max").value, port: $("gc-port").value, mode,
      no_revert: $("gc-hold").value === "hold"};
  }
  function burnQueueConfirmText(recs) {
    return `Start glitching and BURN ${recs.length} queued record(s) on first Goldilocks?\n` +
      "target " + targetBdf + " — rows " + recs.map(r => r.row).join(", ") +
      " (rows auto-assigned in the safe zone)\n" +
      "OTP burns are IRREVERSIBLE. The campaign ends only when every burn " +
      "verifies OK; a burn ABORT is not final — attempts keep firing.\n" +
      "Burns are permanent OTP writes — a wrong burn can BRICK your GPU " +
      "permanently. Verify with Preview first. No responsibility is " +
      "accepted by the developer.";
  }
  $("gc-start").onclick = async () => {
    // task 68 (owner verdict on UX66 F2): the campaign card starts classify
    // campaigns only — burning happens EXCLUSIVELY through "Arm & burn
    // queue" on the Burn queue card (the standalone /api/burn endpoint
    // remains for API/recovery use, not as a page trigger).
    const body = campaignBody("classify");
    if (!confirm("Start glitch campaign?\n" +
        "the pico on port " + $("gc-port").value + " dips NVVDD on " +
        (targetBdf || "the configured BDF") + " to " + body.v_dip + " mV — " +
        "each attempt reboots the GPU.")) return;
    const j = await jpost("/api/glitch/start", body);
    if (j.error) alert(j.error);
    pollGlitch();
  };
  // task 67 (UX66 F1/F2): the one-action burn path — arm gate + burn
  // campaign start in ONE server request (POST /api/burn/queue_start), so
  // the 120 s arm-token TTL race across panels cannot happen. The confirm
  // dialog stays the irreversible-OTP gate.
  $("bq-armburn").onclick = async () => {
    const recs = queueRecords();
    if (!recs) return;
    if (!confirm(burnQueueConfirmText(recs))) return;
    const body = campaignBody("burn");
    body.records = recs;
    body.dump = HIST ? HIST.dir : "";   // identity gate source = the shown dump
    const j = await jpost("/api/burn/queue_start", body);
    if (j.error) { alert(j.error); return; }
    $("bq-reason").textContent = "burn campaign started — " + j.records +
      " record(s), arm token " + j.token_ttl + " s (consumed at start)";
    armToken = j.token; armExpiry = Date.now() + j.token_ttl * 1000;
    updateQueueCard();
    pollGlitch();
  };
  // task 67 (UX66 F5-lite): per-record pre-flight over the EXISTING
  // read-only preview endpoint — the queue, not the payload, gets checked.
  $("bq-check").onclick = async () => {
    const recs = queueRecords();
    if (!recs) return;
    const btn = $("bq-check");
    btn.disabled = true;
    for (const r of recs) {
      const j = await jpost("/api/burn/preview",
                            {row: r.row, value: r.value, mirror: r.mirror,
                             bdf: targetBdf});
      queueVerdicts[r.row + ":" + r.value] =
        j.error ? "error: " + j.error : (j.verdict || "no verdict");
      renderQueue();
    }
    btn.disabled = false;
    updateQueueCard();   // owner: re-evaluate Arm & burn after green verdicts
  };
  $("gc-stop").onclick = () => jpost("/api/glitch/stop", {});  // stop reverts; the 2 s window poll will show closed
  $("gc-revert").onclick = async () => {
    if (!confirm("Revert VRM now — hand PMBus control back? This closes any\n" +
                 "held Goldilocks window. Do it only after you are done with\n" +
                 "in-window verification/burns.")) return;
    const j = await jpost("/api/revert", {port: $("gc-port").value});
    if (j.error) alert(j.error);
    pollGlitch();
  };
  setInterval(pollGlitch, 1000);
  pollGlitch();

  // ---------- VBIOS flash card (task 70) ----------
  // Post-DEVID flash phase beside the burn queue. nvflash requires the
  // nvidia kernel MODULES UNLOADED — device-unbound alone is not enough
  // (owner, 2026-11-27). The ROM picker is a file-picker popup over
  // /api/vbios/browse; a verified backup is always saved before a flash.
  let vbRom = null;            // selected {path,size,md5}
  let vbNvLoaded = [];         // loaded nvidia modules (nvflash needs none)
  let vbDriverBound = null;    // last known bound driver (null = none)
  function vbWarn(msg, cls) {
    const el = $("vb-warn"); el.textContent = msg;
    el.className = "note " + (cls || "");
  }
  function vbGate() {
    const reason = !vbRom ? "choose a ROM first"
      : vbNvLoaded.length ? "modules loaded: " + vbNvLoaded.join(", ") +
          " — nvflash requires them unloaded (unload below)"
      : vbDriverBound ? "driver '" + vbDriverBound + "' bound — unload it first"
      : campaignRunning ? "campaign running — card busy"
      : "";
    const f = $("vb-flash");
    f.disabled = !!reason;
    f.title = reason || "backup (if not fresh) → nvflash -4 -5 " + vbRom.path;
    $("vb-unload").style.display =
      (vbNvLoaded.length || vbDriverBound) ? "" : "none";
    if (burnQueue.length) {   // warn, never refuse: flash is a separate phase
      $("vb-flash").title = (f.title ? f.title + " · " : "") +
        "note: burn queue holds " + burnQueue.length + " record(s) — flashing does not burn fuses";
    }
  }
  async function vbRefresh() {
    try {
      const j = await jget("/api/vbios/list");
      vbDriverBound = (j.driver && j.driver.bound) || null;
      vbNvLoaded = (j.driver && j.driver.loaded) || [];
      const dp = $("vb-driver");
      dp.textContent = (vbNvLoaded.length || vbDriverBound)
        ? "modules: " + (vbNvLoaded.join(", ") || vbDriverBound) +
          " — flash refused"
        : "nvidia modules unloaded — flash allowed";
      dp.className = "pill " +
        ((vbNvLoaded.length || vbDriverBound) ? "badl" : "okl");
      const nv = j.nvflash || {};
      const np = $("vb-nvflash");
      np.textContent = nv.found
        ? "nvflash: " + nv.path + (nv.version ? " · " + nv.version : "")
        : "nvflash: NOT FOUND — flash disabled";
      np.className = "pill " + (nv.found ? "okl" : "badl");
      const b = (j.backups || [])[0];
      $("vb-backupinfo").textContent = b
        ? "latest backup: " + b.name + " · md5 " + b.md5 + " · " + b.when +
          " (a backup newer than 24 h for this serial counts as fresh — a flash reuses it)"
        : "no VBIOS backup saved yet — a flash saves and verifies one first";
      vbGate();
    } catch (e) {}
  }
  function vbModal() {
    let m = $("vb-modal");
    if (m) return m;
    m = document.createElement("div");
    m.id = "vb-modal";
    m.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.65);" +
      "display:none;z-index:99;align-items:center;justify-content:center";
    m.innerHTML = `<div class="card" style="width:min(720px,92vw);max-height:80vh;display:flex;flex-direction:column;margin:0">
      <div class="frow" style="align-items:center">
        <b>Choose ROM</b>
        <span class="note" id="vb-bdir" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
        <button class="btn" id="vb-bup">↑ parent</button>
        <button class="btn" id="vb-bclose">✕ close</button>
      </div>
      <div id="vb-blist" style="overflow:auto;max-height:60vh;margin-top:8px"></div></div>`;
    m.onclick = (ev) => { if (ev.target === m) m.style.display = "none"; };
    document.body.appendChild(m);
    m.querySelector("#vb-bclose").onclick = () => { m.style.display = "none"; };
    return m;
  }
  async function vbBrowse(dir) {
    const m = vbModal();
    m.style.display = "flex";
    const j = await jget("/api/vbios/browse" +
                         (dir ? "?dir=" + encodeURIComponent(dir) : ""));
    $("vb-bdir").textContent = j.dir || j.error || "";
    $("vb-bup").disabled = !j.parent;
    if (j.parent) $("vb-bup").onclick = () => vbBrowse(j.parent);
    const rows = [];
    if (j.error) rows.push(`<div class="note">${esc(j.error)}</div>`);
    for (const d of (j.dirs || []))
      rows.push(`<div class="dumptrow" data-bdir="${esc(d)}">📁 ${esc(d)}/</div>`);
    for (const r of (j.roms || []))
      rows.push(`<div class="dumptrow mono" data-brom="${esc(r.path)}" ` +
        `data-bsize="${r.size}" data-bmd5="${esc(r.md5)}">💾 ${esc(r.name)} ` +
        `<span class="note">${r.size} B · md5 ${esc(r.md5)}</span></div>`);
    const list = $("vb-blist");
    list.innerHTML = rows.join("") ||
      `<div class="note">no subdirectories, no *.rom files here</div>`;
    list.querySelectorAll("[data-bdir]").forEach(
      el => el.onclick = () => vbBrowse(j.dir + "/" + el.dataset.bdir));
    list.querySelectorAll("[data-brom]").forEach(el => el.onclick = () => {
      vbRom = {path: el.dataset.brom, size: +el.dataset.bsize,
               md5: el.dataset.bmd5};
      $("vb-rom").innerHTML = `<b>${esc(vbRom.path)}</b> · ${vbRom.size} B · ` +
        `md5 ${esc(vbRom.md5)}`;
      m.style.display = "none";
      vbGate();
    });
  }
  $("vb-pick").onclick = () => vbBrowse("");
  $("vb-refresh").onclick = vbRefresh;
  $("vb-unload").onclick = async () => {
    $("vb-log").textContent = "unloading nvidia stack…";
    const j = await jpost("/api/driver/op", {op: "unload", confirm: true});
    $("vb-log").textContent = (j.log || [j.error || "done"]).join("\n") +
      (j.note ? "\n" + j.note : "");
    vbRefresh();
    renderDrivers();
  };
  $("vb-backup").onclick = async () => {
    $("vb-backup").disabled = true;
    $("vb-log").textContent = "saving current VBIOS (nvflash --save)…";
    try {
      const j = await jpost("/api/vbios/backup", {});
      $("vb-log").textContent = j.error
        ? j.error
        : "backup saved + verified: " + j.path + "\nmd5 " + j.md5;
      vbWarn(j.error ? "backup FAILED: " + j.error : "", j.error ? "warn" : "");
    } finally { $("vb-backup").disabled = false; vbRefresh(); }
  };
  $("vb-flash").onclick = async () => {
    if (!vbRom) return;
    const q = burnQueue.length
      ? `\nNOTE: the burn queue holds ${burnQueue.length} record(s) — ` +
        `flashing does NOT burn fuses.`
      : "";
    if (!confirm(`Flash ${vbRom.path} into the card with nvflash -4 -5?\n\n` +
      `This rewrites the SPI VBIOS — irreversible-ish (a bad flash needs a\n` +
      `recovery boot). A board-id mismatch prompt from nvflash is EXPECTED\n` +
      `on a rebranded card; the console auto-answers 'y'.\n` +
      `A fresh backup is saved and verified first — the flash REFUSES if that\n` +
      `fails. The card may need a COLD BOOT (PSU off) to attach afterwards.${q}`)) return;
    const btn = $("vb-flash"); btn.disabled = true;
    $("vb-log").textContent = "flashing — nvflash running (up to 120 s)…";
    try {
      const j = await jpost("/api/vbios/flash",
                            {rom: vbRom.path, confirm: true,
                             protectoff: $("vb-protectoff").checked});
      $("vb-log").textContent = (j.output_tail || j.error || "no output") +
        (j.backup ? `\n\nbackup: ${j.backup.path}\nmd5 ${j.backup.md5}` : "");
      if (j.post_verify) $("vb-post").innerHTML =
        `<b>post-flash verify</b> (best effort)<br>` +
        `<pre class="mono" style="white-space:pre-wrap">${esc((j.post_verify.lspci || "") + "\n" + (j.post_verify.nvidia_smi || ""))}</pre>` +
        `<span class="note">${esc(j.post_verify.note || "")}</span>`;
      vbWarn(j.ok ? "flash done — cold-boot the card to attach the new VBIOS"
                  : (j.error || "flash FAILED — read the output above"),
             j.ok ? "okl" : "warn");
    } finally { vbRefresh(); }
  };
  vbRefresh();
  setInterval(() => { if (!document.hidden) vbRefresh(); }, 5000);

  // ---------- Drivers pane ----------
  $("tab-drivers").innerHTML = `
    <div class="card">
      <h3>Driver state</h3>
      <div class="grid" id="drv-cards"></div>
    </div>
    <div class="card" style="margin-top:12px">
      <h3>Actions</h3>
      <div class="frow">
        <button class="btn go" id="drv-load">Load nvidia</button>
        <button class="btn danger" id="drv-unload">Unload nvidia stack</button>
        <button class="btn danger" id="drv-blacklist">Blacklist nvidia + nouveau</button>
        <button class="btn" id="drv-unblacklist">Remove blacklist</button>
      </div>
      <div class="note" style="margin-top:8px">Glitching needs the nvidia driver
      unloaded and blacklisted (it re-locks the VRM and binds before you can inspect
      BAR0). Blacklist here prevents autoload at boot but keeps manual modprobe
      working — intentional, so you stay in control. Unload unbinds the GPU first,
      then rmmods nvidia_drm / modeset / uvm / nvidia.</div>
      <div id="drv-log" class="logbox"></div>
    </div>`;

  function twoStep(btn, label, fn) {   // click -> "confirm?" -> run
    btn.onclick = () => {
      if (btn.dataset.armed) { btn.textContent = label; delete btn.dataset.armed;
        btn.classList.remove("on"); fn(); return; }
      btn.dataset.armed = "1"; btn.classList.add("on"); btn.textContent = "confirm?";
      setTimeout(() => { if (btn.dataset.armed) { btn.textContent = label;
        delete btn.dataset.armed; btn.classList.remove("on"); } }, 4000);
    };
  }
  async function renderDrivers() {
    try {
      const j = await jget("/api/driver");
      const card = (k, v, cls) => `<div class="card stat"><div class="k">${k}</div>` +
        `<div class="v mono ${cls || ""}" style="font-size:12px">${v}</div></div>`;
      $("drv-cards").innerHTML =
        card("bound driver", esc(j.bound || "none"), j.bound ? "ok" : "warn") +
        card("driver version", esc(j.version || "—")) +
        card("blacklist", j.blacklist_active ? "ACTIVE" : "inactive",
             j.blacklist_active ? "warn" : "ok") +
        card("loaded modules", esc((j.loaded || []).join(" ") || "none"));
      if ((j.other_modprobe_d || []).length)
        $("drv-log").textContent = "other modprobe.d entries:\n" +
          j.other_modprobe_d.join("\n");
    } catch (e) {}
  }
  twoStep($("drv-unload"), "Unload nvidia stack", async () => {
    const j = await jpost("/api/driver/op", {op: "unload", confirm: true});
    $("drv-log").textContent = (j.log || [j.error || "done"]).join("\n");
    renderDrivers();
  });
  twoStep($("drv-blacklist"), "Blacklist nvidia + nouveau", async () => {
    const j = await jpost("/api/driver/op", {op: "blacklist", confirm: true});
    $("drv-log").textContent = j.note || j.error || "done";
    renderDrivers();
  });
  $("drv-load").onclick = async () => {
    const j = await jpost("/api/driver/op", {op: "load"});
    $("drv-log").textContent = (j.log || [j.error]).join("\n");
    renderDrivers();
  };
  $("drv-unblacklist").onclick = async () => {
    const j = await jpost("/api/driver/op", {op: "unblacklist"});
    $("drv-log").textContent = j.note || j.error || "done";
    renderDrivers();
  };
  renderDrivers();

  // ---------- GPU pane ----------
  $("tab-gpu").innerHTML = `
    <div class="card" id="gpu-banner"><div class="note">loading…</div></div>
    <div class="card" id="t51-gpu-readouts" style="margin-top:12px">
      <h3>Allspark readouts <span class="note">(The Lab / allspark
        community claims — read-only, never a burn gate)</span></h3>
      <div id="t51-gpu-readouts-body" class="note">awaiting first live poll
        (/api/live readouts)…</div>
    </div>
    <div class="card" style="margin-top:12px">
      <div class="flexline" style="margin:0 0 6px 0">
        <h3 style="margin:0">Live monitor</h3>
        <span class="pill">refresh
          <select id="gmon-sel">
            <option value="1000" selected>1s</option>
            <option value="2000">2s</option>
            <option value="5000">5s</option>
            <option value="10000">10s</option>
            <option value="0">off</option>
          </select></span>
        <button class="btn" id="gmon-clear">clear</button>
      </div>
      <div id="gmon" class="gmon-grid"></div>
    </div>
    <div class="card" style="margin-top:12px"><h3>PCIe link (lspci)</h3>
      <div id="gpu-link" class="mono note"></div></div>`;
  const GPU_LABELS = {"name": "GPU", "driver_version": "driver", "memory.total": "VRAM total",
    "memory.used": "VRAM used", "utilization.gpu": "util %",
    "utilization.memory": "mem util %", "temperature.gpu": "temp °C",
    "power.draw": "power W", "power.limit": "limit W", "fan.speed": "fan %",
    "pcie.link.gen.current": "PCIe gen", "pcie.link.gen.max": "PCIe max gen",
    "clocks.sm": "SM MHz", "clocks.mem": "mem MHz", "pstate": "P-state"};
  async function renderGpu(pre) {
    // one section per GPU on the host; `pre` (from gmonTick) renders the
    // selected card only, initial paint lists them all via /api/gpus/all
    let list = null;
    if (!pre) {
      try { list = await jget("/api/gpus/all"); } catch (e) { return; }
    }
    const info = {};
    if (list) for (const g of (list.gpus || [])) info[g.bdf] = g;
    const bdfs = list ? Object.keys(info) : [pre.bdf || ""];
    const results = await Promise.all(bdfs.map(async bdf => {
      try { return await jget("/api/gpu" + (bdf ? "?bdf=" + encodeURIComponent(bdf) : "")); }
      catch (e) { return { bdf, nvidia: { error: String(e) }, link: [], apps: [] }; }
    }));
    const sel = selBdf();
    const target = sel || (list && list.default) || "";
    $("gpu-banner").innerHTML = results.map(j => {
      const n = j.nvidia || {}, bdf = j.bdf || "?";
      const gi = info[bdf] || {};
      const isSel = bdf === target;
      const head = `<div class="flexline" style="margin:0 0 4px">` +
        `<b class="mono">${esc(bdf)}</b>` +
        (gi.ga100 ? ` <span class="tag">GA100 · fuse target</span>` : "") +
        (isSel ? ` <span class="tag">selected</span>` : "") +
        (n.error ? ` <span class="warn">nvidia-smi: ${esc(n.error)}</span>`
                 : ` <span class="ok">${esc(n["name"] || gi.name || "GPU")}</span> ` +
                   `<span class="note mono">updated ${esc(j.ts)}</span>`) +
        (gi.driver ? ` <span class="note mono">driver=${esc(gi.driver)}</span>` : "") +
        `</div>`;
      const cards = n.error ? "" :
        `<div class="grid" style="margin-bottom:8px">` +
        Object.entries(GPU_LABELS)
          .filter(([k]) => n[k] !== undefined && n[k] !== "[Not Supported]")
          .map(([k, l]) => `<div class="card stat"><div class=\"k\">${l}</div>` +
            `<div class=\"v mono\">${esc(n[k])}</div></div>`).join("") + `</div>`;
      const link = (j.link || []).length
        ? `<div class="mono note" style="margin-bottom:6px">${esc(j.link.join("\n"))}</div>` : "";
      return `<div class="card" style="margin-bottom:10px">${head}${cards}${link}</div>`;
    }).join("");
    const cur = results.find(j => j.bdf === (sel || "")) || results[0] || {};
    $("gpu-link").textContent = (cur.link || []).join("\n") || "no link info";
  }
  // ---- nvtop-style live monitor ----
  const gmonHist = [];
  const gmonMs = () => +(localStorage.getItem("ga100.gmonMs") || "1000");
  const gnum = v => { const x = parseFloat(v); return isNaN(x) ? null : x; };
  const CY = "#22d3ee", YE = "#eab308", GR = "#22c55e", MG = "#e879f9";
  function pbar(pct, width) {
    const p = Math.max(0, Math.min(1, (pct || 0) / 100));
    const n = Math.round(p * width);
    return "[" + `<span style="color:${GR}">${"|".repeat(n)}</span>` +
      `<span style="color:var(--border)">${"|".repeat(width - n)}</span>` +
      `<span class="nvval"> ${Math.round(pct)}%]</span>`;
  }
  function hbar(v, max, color) {
    const w = max ? Math.max(0, Math.min(100, v / max * 100)) : 0;
    return `<span class="nvbar"><span style="width:${w.toFixed(1)}%;background:${color}"></span></span>`;
  }
  function agoLabel(sec) {
    if (sec >= 60) { const m = Math.floor(sec / 60), s = sec % 60;
      return "-" + m + "m" + (s ? s + "s" : ""); }
    return "-" + sec + "s";
  }
  function gmonRender() {
    const el = $("gmon");
    const last = gmonHist[0];
    if (!last) { el.innerHTML = `<div class="note">no samples yet</div>`; return; }
    if (last.err) { el.innerHTML = `<div class="gmon-err mono">⚠ ${esc(last.err)}</div>`; return; }
    const utils = gmonHist.map(s => s.util).filter(v => v !== null && v !== undefined);
    const avg = utils.length ? Math.round(utils.reduce((a, b) => a + b, 0) / utils.length) : 0;
    const mx = utils.length ? Math.max(...utils) : 0;
    const vp = last.vrammax ? last.vram / last.vrammax * 100 : 0;
    const hdr = `<div class="nvhdr">` +
      `<span class="nvname">● ${esc(last.name || "GPU")}</span>` +
      `<span class="nvlbl">GPU</span><span class="nvval">avg ${avg}% max ${mx}%</span>` +
      `<span class="nvlbl">VRAM</span>${hbar(last.vram, last.vrammax, GR)}` +
      `<span class="nvval">${(last.vram / 1024).toFixed(1)}Gi / ${(last.vrammax / 1024).toFixed(1)}Gi` +
      ` · ${((last.vrammax - last.vram) / 1024).toFixed(1)}Gi free · ${Math.round(vp)}%</span>` +
      `<span class="nvval">POW ${last.pw ?? "—"}/${last.pwmax ?? "—"} W</span>` +
      `<span class="nvval" style="color:${GR}">TEMP ${last.temp ?? "—"}°C</span>` +
      `<span class="nvval" style="color:${MG}">PCIe GEN ${esc(last.gen || "?")}@${esc(last.lanes || "?")}x</span>` +
      `</div>`;
    const dev = `<div class="nvdev mono">` +
      `<div><span style="color:${CY}">Device 0</span> <span class="nvval">[${esc(last.name || "")}]</span>` +
      ` <span style="color:${MG}">PCIe GEN ${esc(last.gen || "?")}@${esc(last.lanes || "?")}x</span></div>` +
      `<div><span style="color:${CY}">GPU</span> <span class="nvval">${last.sm ?? "—"}MHz</span>` +
      ` <span style="color:${CY}">MEM</span> <span class="nvval">${last.mc ?? "—"}MHz</span>` +
      ` <span style="color:${GR}">TEMP</span> <span class="nvval">${last.temp ?? "—"}°C</span>` +
      ` <span style="color:${GR}">FAN</span> <span class="nvval">${last.fan ?? "—"}%</span>` +
      ` <span style="color:${YE}">POW</span> <span class="nvval">${last.pw ?? "—"}/${last.pwmax ?? "—"} W</span></div>` +
      `<div><span style="color:${CY}">GPU</span>${pbar(last.util, 24)}` +
      `&nbsp;&nbsp;<span style="color:${YE}">MEM</span>${pbar(last.memu, 24)}</div>` +
      `</div>`;
    const W = 600, H = 190;
    const series = k => { const a = [];
      for (let i = gmonHist.length - 1; i >= 0; i--) {
        const s = gmonHist[i];
        if (!s.err && s[k] !== null && s[k] !== undefined) a.push(s[k]);
      } return a; };
    const toPts = a => a.map((v, i) => {
      const x = a.length > 1 ? (i / (a.length - 1)) * W : 0;
      const y = H - Math.max(0, Math.min(1, v / 100)) * H;
      return x.toFixed(1) + "," + y.toFixed(1); }).join(" ");
    const u = series("util"), m = series("memu");
    const winSec = Math.round((gmonHist.length - 1) * (gmonMs() || 1000) / 1000);
    const xl = [0, 1, 2, 3, 4].map(f => {
      const sec = Math.round(winSec * (1 - f / 4));
      return `<span>${f === 4 ? "now" : agoLabel(sec)}</span>`; }).join("");
    const plot = `<div class="nvplotwrap"><div class="nvy">` +
      `<span>100</span><span>75</span><span>50</span><span>25</span><span>0</span>` +
      `</div><div class="nvplot">` +
      `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="nvsvg">` +
      `<polyline points="${toPts(m)}" fill="none" stroke="${YE}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>` +
      `<polyline points="${toPts(u)}" fill="none" stroke="${CY}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>` +
      `</svg><div class="nvlegend">` +
      `<span style="color:${CY}">GPU %</span><span style="color:${YE}">mem %</span>` +
      `</div></div></div><div class="nvx">${xl}</div>`;
    const apps = last.apps || [];
    const tbl = `<table class="nvproc"><thead><tr><th>PID</th><th>USER</th>` +
      `<th>DEV</th><th>GPU MEM</th><th>Command</th></tr></thead><tbody>` +
      (apps.length ? apps.map(a => `<tr><td class="mono">${esc(a.pid)}</td>` +
        `<td>${esc(a.user)}</td><td>0</td><td class="mono">${esc(a.mem)} MiB</td>` +
        `<td class="mono">${esc(a.cmd)}</td></tr>`).join("")
        : `<tr><td colspan="5" class="note">no compute processes</td></tr>`) +
      `</tbody></table>`;
    el.innerHTML = hdr + dev + plot + tbl;
  }
  async function gmonTick() {
    try {
      const j = await jget("/api/gpu" + bdfQs());
      renderGpu(j);
      const n = j.nvidia || {};
      const t = new Date().toTimeString().slice(0, 8);
      if (n.error) { gmonHist.unshift({t, err: n.error}); }
      else {
        const lim = gnum(n["power.limit"]) || 300;
        const tot = gnum(n["memory.total"]) || 81920;
        gmonHist.unshift({t, name: (n["name"] || "GPU") + (j.bdf ? " · " + j.bdf : ""),
          temp: gnum(n["temperature.gpu"]), util: gnum(n["utilization.gpu"]),
          memu: gnum(n["utilization.memory"]), pw: gnum(n["power.draw"]),
          pwmax: lim, sm: gnum(n["clocks.sm"]), mc: gnum(n["clocks.mem"]),
          fan: gnum(n["fan.speed"]), vram: gnum(n["memory.used"]), vrammax: tot,
          gen: n["pcie.link.gen.current"], lanes: n["pcie.link.width.current"],
          apps: j.apps || []});
      }
      if (gmonHist.length > 120) gmonHist.pop();
      gmonRender();
    } catch (e) {}
  }
  let gmonTimer = null;
  function gmonStart() {
    if (gmonTimer) { clearInterval(gmonTimer); gmonTimer = null; }
    const ms = gmonMs();
    if (ms > 0) { gmonTick(); gmonTimer = setInterval(
      () => { if (!document.hidden) gmonTick(); }, ms); }
  }
  $("gmon-sel").value = String(gmonMs());
  $("gmon-sel").onchange = e => {
    localStorage.setItem("ga100.gmonMs", e.target.value); gmonStart();
  };
  $("gmon-clear").onclick = () => { gmonHist.length = 0; gmonRender(); };
  renderGpu();

  window.__onTabChange = name => {
    if (gmonTimer) { clearInterval(gmonTimer); gmonTimer = null; }
    if (name === "gpu") { renderGpu(); gmonStart(); }
    if (name === "glitch") { loadLayout(); loadGpus(); }
  };

  const savedMs = +(localStorage.getItem("ga100.pollMs") || "0");
  document.getElementById("pollsel").value = String(savedMs);
  populateGpuSel();
  fullDump().then(() => {
    fetchLive(true);
    if (savedMs > 0) heavyTimer = setInterval(() => fetchLive(true), savedMs);
  });
})();
"""


def build_html(payload, live):
    """Build the console HTML. `payload` is a dump dict (static) or a seed/stub
    (live). `live` selects the fetch layer + live bar."""
    livebar = LIVEBAR if live else ""
    liveboot = LIVEBOOT if live else ""
    # escape </ so a dump string (dmesg, lspci, serial) can never break out
    # of the <script type="application/json"> block; JSON.parse is unaffected
    payload_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    # bench-burn advanced-unlock table (host/ga100vfi/advanced_unlocks.py is
    # the single source); same </ escape so it can never break the JSON tag.
    advanced_json = json.dumps(ADVANCED_UNLOCKS,
                               separators=(",", ":")).replace("</", "<\\/")
    # task 41: chain-1 FF field catalog for the page's per-die derivation —
    # the SAME FF_FIELDS the server's plane gate uses (service.py is the
    # single source; lazy import because service imports gui at module
    # level). Entries: [name, global_bit_start, width].
    from .service import FF_FIELDS
    ffcatalog_json = json.dumps(FF_FIELDS.get(1, []),
                                separators=(",", ":")).replace("</", "<\\/")
    return (HTML.replace("__PAYLOAD__", payload_json)
                .replace("__ADVANCED__", advanced_json)
                .replace("__FFCAT__", ffcatalog_json)
                .replace("__LIVEBAR__", livebar)
                .replace("__LIVEBOOT__", liveboot))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="ga100vfi.console.gui",
        description="Generate the GA100 Fuse Console HTML (static or live seed)")
    ap.add_argument("dump", nargs="?", help="dump.json or dir (static mode, or live seed)")
    ap.add_argument("out", nargs="?", help="output html path")
    ap.add_argument("--live", action="store_true",
                    help="live mode (fetches /api/live, /api/full)")
    ap.add_argument("--stub", action="store_true", help="live mode with empty seed")
    a = ap.parse_args(argv)

    if a.live:
        payload = dict(STUB) if (a.stub or not a.dump) else load_dump(a.dump)
        payload["live"] = True
        out = a.out or "ga100_fuse_live.html"
    else:
        if not a.dump:
            ap.error("static mode needs a dump path")
        payload = load_dump(a.dump)
        out = a.out or "ga100_fuse_dump_gui.html"

    html = build_html(payload, a.live)
    with open(out, "w") as f:
        f.write(html)
    print(f"wrote {out} ({os.path.getsize(out)} bytes, "
          f"{'live' if a.live else 'static'} mode, seed rows={payload.get('row_count', 0)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
