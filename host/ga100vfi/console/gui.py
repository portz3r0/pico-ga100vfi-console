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

STUB = {
    "live": True, "bdf": "?", "started": "?", "vendor": "0x10de", "device": "0x20c2",
    "revision": "?", "driver": "?", "fingerprint": "—", "row_count": 0,
    "nonblank_rows": {}, "status": {}, "shadow": {}, "rows": {},
    "interpretation": [], "dmesg_tail": "", "nvidia_smi": "", "hexnonzero": [],
    "ceilings": {},
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
    # before the TPC_DEFECTIVE_GPC/TPC_DISABLE_GPC keys existed (0x820760 =
    # defective, 0x820C38 = effective disable). The window stores only
    # non-zero words, so a covered-but-absent offset means zero — treat the
    # arrays as fully present once the window reaches the last GPC word.
    sh = d.get("shadow")
    if isinstance(sh, dict) and hexnon:
        by_off = {off: val for off, val in hexnon}
        covered = max(o for o, _ in hexnon) >= 0x820C54
        for g in range(8):
            if covered:
                sh.setdefault(f"TPC_DEFECTIVE_GPC{g}", by_off.get(0x820760 + 4 * g, 0))
                sh.setdefault(f"TPC_DISABLE_GPC{g}", by_off.get(0x820C38 + 4 * g, 0))
            else:
                sh.setdefault(f"TPC_DEFECTIVE_GPC{g}",
                             by_off.get(0x820760 + 4 * g))
                sh.setdefault(f"TPC_DISABLE_GPC{g}",
                             by_off.get(0x820C38 + 4 * g))
        if "tpc" not in d:
            try:
                from .. import fusedump as _fd
                d["tpc"] = _fd.tpc_summary(sh)
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
  .app { max-width: 1140px; padding: 20px 22px 48px; }
  .mono { font-family: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas,
          "Liberation Mono", monospace; font-size: 12px; }

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

  #livebar { margin-bottom: 14px; position: sticky; top: 0; z-index: 20;
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

  /* tabs + control panels */
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border);
          margin-bottom: 14px; }
  .tab { background: none; border: none; color: var(--muted-foreground);
         padding: 9px 15px 8px; font-size: 13px; font-weight: 500; cursor: pointer;
         border-bottom: 2px solid transparent; margin-bottom: -1px;
         border-radius: 6px 6px 0 0; transition: color .15s, background .15s; }
  .tab:hover { color: var(--foreground); background: rgba(76,194,255,.05); }
  .tab.on { color: var(--accent); border-bottom-color: var(--accent); }
  .tabpane { display: none; }
  .tabpane.on { display: block; }

  h3 { font-size: 12.5px; font-weight: 650; margin: 0 0 10px; color: var(--foreground);
       display: flex; align-items: center; gap: 8px; }
  h3::before { content: ""; width: 3px; height: 11px; border-radius: 2px;
               background: var(--muted-foreground); }
  .frow { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; margin: 8px 0; }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field label { font-size: 10.5px; color: var(--fg-subtle); text-transform: uppercase;
                 letter-spacing: .07em; }
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
  <header class="topbar">
    <div>
      <h1>GA100 Fuse Console</h1>
      <div class="sub mono" id="meta"></div>
    </div>
    <div class="topbadge"><span class="dot"></span>pico-ga100vfi · live console</div>
  </header>
  <nav class="tabs">
    <button class="tab on" data-tab="explorer">Fuse Explorer</button>
    <button class="tab" data-tab="glitch">Glitch &amp; Burn</button>
    <button class="tab" data-tab="drivers">Drivers</button>
    <button class="tab" data-tab="gpu">GPU Info</button>
  </nav>
__LIVEBAR__
  <section id="tab-explorer" class="tabpane on">
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

  <h2>Shadow registers</h2>
  <div class="scroll" id="shadow"></div>

  <h2>Fuse rows (0–487)</h2>
  <div class="flexline" id="rowbtns"></div>
  <div class="flexline">
    <input type="text" id="search" placeholder="search row # or hex value…">
    <span class="note" id="rowcount"></span>
  </div>
  <div class="scroll" id="rowtable"></div>
  <div class="card" id="detail"></div>

  <h2>Interpretation log</h2>
  <div class="card"><div id="interp"></div></div>

  <details><summary>dmesg tail (GPU boot)</summary><pre id="dmesg"></pre></details>
  <details><summary>Hex window — non-zero words in 0x820000–0x824400</summary>
    <input type="text" id="hexsearch" placeholder="filter offset/value…" style="margin-top:6px">
    <div class="scroll" id="hextable" style="margin-top:6px"></div></details>

  </section>

  <section id="tab-glitch" class="tabpane">
    <div class="card"><div class="note">Glitch &amp; Burn controls are available when this
    page is served by the live console (<span class="mono">ga100vfi.console</span>).</div></div>
  </section>
  <section id="tab-drivers" class="tabpane">
    <div class="card"><div class="note">Driver management is available in live mode.</div></div>
  </section>
  <section id="tab-gpu" class="tabpane">
    <div class="card"><div class="note">GPU info is available in live mode.</div></div>
  </section>

  <div id="auditbg"><div id="audit"></div></div>

  <footer>
    <span>data: ga100vfi.fusedump + ga100vfi.console</span>
    <span>FF decode: chain=bits[4:0] iff=bit5 block=bits[15:6] data=bits[31:16]</span>
    <span>burns require arm token + pure 0→1 payload + live Goldilocks guards · FUSEWDATA untouched otherwise</span>
  </footer>
</div>

<script id="dumpdata" type="application/json">__PAYLOAD__</script>
<script>
"use strict";
let D = JSON.parse(document.getElementById("dumpdata").textContent);

const fmt = v => "0x" + ((v ?? 0) >>> 0).toString(16).toUpperCase().padStart(8, "0");
const bitsOf = v => { const b = []; v = (v ?? 0) >>> 0;
  for (let i = 0; i < 32; i++) if ((v >>> i) & 1) b.push(i); return b; };
const pop = v => bitsOf(v).length;
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
  .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
// verified FF-record field map: chain=bits[4:0], iff=bit5, block=bits[15:6], data=bits[31:16]
const ffDecode = v => ({ ch: v & 0x1F, iff: (v >> 5) & 1,
                         blk: (v >> 6) & 0x3FF, data: (v >>> 16) & 0xFFFF });

const REGIONS = [
  { min: 0,  max: 47,  name: "MAIN", desc: "main array — paired option words (row 0 = 0x53557C3D known-good signature, bit 5 = DISABLE_SW_OVERRIDE)" },
  { min: 48, max: 95,  name: "UNIQ", desc: "main array — unpaired rows (hash / per-chip data)" },
  { min: 96, max: 221, name: "FPF",  desc: "FPF region — production-writable config rows (96–221)" },
  { min: 222, max: 487, name: "FF",  desc: "fuseless-fuse region — boot-replayed records (222–487), last record per block wins" },
];
const regionOf = r => REGIONS.find(x => r >= x.min && r <= x.max) ||
  { min: r, max: r, name: "TAIL", desc: "rows beyond 487 — outside the documented row map" };

// ---------------------------------------------------------------- renderers
function renderMeta() {
  const nb = Object.keys(D.nonblank_rows || {}).length;
  document.getElementById("meta").textContent =
    `${D.bdf}  ·  ${D.vendor}:${D.device} rev ${D.revision}  ·  driver=${D.driver}  ·  ` +
    `dumped ${D.started}  ·  fingerprint ${D.fingerprint}  ·  ${D.row_count} rows, ${nb} non-blank`;
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
const STATES = { pre: "Pre-glitch reference",
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
  if (curState === "pre") {
    gpcDis = 0x86; fbpDis = 0x852;   // stock CMP 170HX SKU floorsweep (factory, same per SKU)
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
function computeTpc() {
  // Mirror of fusedump.tpc_summary() for payloads without a precomputed
  // "tpc" key (old static dumps). Legacy TPC_DISABLE_{g} held 0x820760.
  const sh = D.shadow || {};
  const gpcDef = sh.GPC_DEFECTIVE ?? 0, gpcDis = sh.GPC_DISABLE ?? 0;
  const gpcs = [], totals = { sm_now: 0, sm_max: 0, sm_defective: 0,
                              sm_recoverable: 0, tpc_defective: 0,
                              tpc_recoverable: 0, have_data: false };
  const pop = v => { let n = 0; while (v) { n += v & 1; v >>>= 1; } return n; };
  for (let g = 0; g < 8; g++) {
    let def = sh["TPC_DEFECTIVE_GPC" + g];
    if (def == null) def = sh["TPC_DISABLE_" + g];
    let dis = sh["TPC_DISABLE_GPC" + g];
    if (def == null && dis == null) { gpcs.push({ gpc: g, available: false }); continue; }
    def = ((def ?? 0) >>> 0) & 0xFF;
    dis = (((dis == null ? def : dis)) >>> 0) & 0xFF;
    const eff = def | dis;   // defective TPCs never run, disable or not
    const ndef = pop(def), ndis = pop(eff);
    const recov = Math.max(ndis - ndef, 0);
    const gdead = (gpcDef >> g) & 1, gdis = (gpcDis >> g) & 1;
    const tpc_max = gdead ? 0 : 8 - ndef;
    const sm_now = gdis ? 0 : (8 - ndis) * 2;
    const row = { gpc: g, available: true, def, dis,
                  tpc_defective: ndef, tpc_recoverable: recov,
                  tpc_now: 8 - ndis, tpc_max,
                  sm_now, sm_max: tpc_max * 2,
                  gpc_defective: gdead, gpc_disabled: gdis };
    gpcs.push(row);
    totals.have_data = true;
    totals.sm_now += sm_now;
    totals.sm_max += tpc_max * 2;
    totals.sm_defective += ndef * 2;
    totals.sm_recoverable += gdead ? 0 : recov * 2;
    totals.tpc_defective += ndef;
    totals.tpc_recoverable += gdead ? 0 : recov;
  }
  return { gpcs, totals };
}
// CMP 170HX stock SKU factory TPC floorsweep (per-GPC disable words,
// bit t = TPC t masked). From the reference card's pre-glitch array:
// GPC1/2/7 fully masked, one TPC masked in each of the others.
const STOCK_TPC_DIS = [0x01, 0xFF, 0xFF, 0x01, 0x01, 0x01, 0x01, 0xFF];
const STOCK_GPC_DIS = 0x86;   // stock SKU GPC floorsweep: GPC 1, 2, 7
function renderTpc() {
  const el = document.getElementById("tpcmap");
  const sh = D.shadow || {};
  if (sh.TPC_DEFECTIVE_GPC0 == null && sh.TPC_DISABLE_GPC0 == null &&
      sh.TPC_DISABLE_0 == null && !(D.tpc && D.tpc.totals.have_data)) {
    el.innerHTML = `<span class="note">waiting for TPC register data…</span>`;
    return;
  }
  const T = (D.tpc && D.tpc.totals && D.tpc.totals.have_data) ? D.tpc : computeTpc();
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
    if (curState === "pre") {
      dis = STOCK_TPC_DIS[g]; gdis = (STOCK_GPC_DIS >> g) & 1;
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
      const zLbl = curState === "pre"
        ? "factory-disabled, healthy — the unlock prize"
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
  const stateTag = { pre: "PRE-GLITCH (stock 170HX SKU floorsweep)",
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
    (curState === "pre"
      ? `Pre-glitch uses the stock CMP 170HX SKU floorsweep: GPC_DISABLE 0x86 (GPC 1/2/7) plus the ` +
        `factory TPC mask 0x01/0xFF pattern (29 TPC masked → 70 SM). The yellow cells are what the ` +
        `unlock recovers.`
      : curState === "intended"
        ? `Intended = disable mask equals the card's defective mask: every unit that is not dead ` +
          `silicon runs. No yellow cells by definition.`
        : `Now reads the live registers: TPC defective 0x820760+gpc·4, effective disable ` +
          `0x820C38+gpc·4 (effective = disable ∪ defective). Yellow cells remaining = ` +
          `still-disabled-but-healthy = outstanding unlock headroom.`) +
    ` Post-unlock ceiling = (8 − defective TPC) × 2 SM per non-defective GPC. Cells in a ` +
    `floorswept/dead GPC are dimmed: their health is shown, but they only run once the GPC ` +
    `itself is enabled.</div>`;
  el.innerHTML = html;
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
  if (which === "def") {
    const k = "TPC_DEFECTIVE_GPC" + g;
    if (sh[k] != null) return { v: sh[k] >>> 0, src: "shadow." + k };
    const lk = "TPC_DISABLE_" + g;   // legacy key held the 0x820760 word
    if (sh[lk] != null)
      return { v: sh[lk] >>> 0, src: "shadow." + lk + " (legacy = 0x820760 word)" };
  } else {
    const k = "TPC_DISABLE_GPC" + g;
    if (sh[k] != null) return { v: sh[k] >>> 0, src: "shadow." + k };
  }
  const off = (which === "def" ? AOFF.TPC_DEF : AOFF.TPC_DIS) + 4 * g;
  const hv = (D.hexnonzero || []).find(([o]) => o === off);
  if (hv) return { v: hv[1] >>> 0, src: "hex window @ " + hx(off) };
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
    if (defM !== 0) rows.push(arow(0, "TPC_DEFECTIVE_GPC" + g, AOFF.TPC_DEF + 4 * g, td, null,
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
    if (dead) rows.push(arow(0, "TPC_DEFECTIVE_GPC" + g, AOFF.TPC_DEF + 4 * g, td, t,
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
  document.getElementById("auditbg").classList.add("open");
  document.getElementById("auditclose").onclick = closeAudit;
}
function closeAudit() { document.getElementById("auditbg").classList.remove("open"); }
document.addEventListener("click", e => {
  if (e.target.closest("#auditclose")) return;
  if (e.target.id === "auditbg") { closeAudit(); return; }
  const el = e.target.closest("[data-audit]");
  if (el) {
    const p = el.dataset.audit.split(":");
    openAudit(p[0], +p[1], p[2] == null ? null : +p[2]);
  }
});
document.addEventListener("keydown", e => { if (e.key === "Escape") closeAudit(); });

// shadow registers -------------------------------------------------------
function renderShadow() {
  const SHOFF = {
    GPC_DISABLE: [0x820350, "floorsweep — GPCs disabled at boot"],
    GPC_DEFECTIVE: [0x8205C4, "dead GPCs — real silicon, cannot be re-enabled"],
    FBP_DISABLE: [0x820364, "floorsweep — FBPs disabled at boot"],
    FBP_DEFECTIVE: [0x8205CC, "dummy stacks — missing silicon"],
    FBPA_DISABLE: [0x820368, "per-FBPA floorsweep"],
    FBPA_DEFECTIVE: [0x8205D0, "per-FBPA defects"],
    NVLINK_DISABLE: [0x820684, "NVLink floorsweep"],
    NVLINK_DEFECTIVE: [0x82068C, ""],
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
}
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
  renderShadow();
}
function renderAll() {
  renderLive(); renderRows(); renderInterp(); renderDmesg(); renderHex();
}

// ---------------------------------------------------------------- tabs
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("on", b.dataset.tab === name));
  document.querySelectorAll(".tabpane").forEach(p =>
    p.classList.toggle("on", p.id === "tab-" + name));
  try { history.replaceState(null, "", "#" + name); } catch (e) {}
  if (window.__onTabChange) window.__onTabChange(name);
}
document.querySelectorAll(".tab").forEach(b =>
  b.onclick = () => switchTab(b.dataset.tab));

// ---------------------------------------------------------------- boot
renderStateBtns();
wireRowBtns();
renderAll();
const initialTab = (location.hash || "").replace("#", "");
if (["glitch", "drivers", "gpu"].includes(initialTab)) switchTab(initialTab);
__LIVEBOOT__
</script>
</body>
</html>
"""

LIVEBAR = """
  <div class="card" id="livebar">
    <div class="flexline" style="margin:0">
      <span id="liveind" class="pill warnl">connecting…</span>
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
    <div id="feed" class="mono"></div>
  </div>
"""

LIVEBOOT = r"""
// ---------------------------------------------------------------- live layer
(function () {
  const ind = document.getElementById("liveind");
  const feedEl = document.getElementById("feed");
  const feedLines = [];
  let prev = null, timer = null;

  function note(msg, cls) { ind.textContent = msg; ind.className = "pill " + (cls || ""); }
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
  async function fetchLive(heavy) {
    try {
      const r = await fetch("/api/live", { cache: "no-store" });
      const j = await r.json();
      if (j.paused) { note("⏸ " + j.paused, "warnl"); return; }
      if (j.error) { note("⚠ " + j.error, "badl"); return; }
      D.status = j.status; D.shadow = j.shadow;
      if (j.tpc !== undefined) D.tpc = j.tpc;
      if (j.driver !== undefined) D.driver = j.driver;
      if (j.bdf !== undefined) D.bdf = j.bdf;
      D.started = j.ts;
      diff(j);
      renderLive();  // cheap cards refresh on the light poll too; rows/hex stay heavy-only
      note("● live — " + j.ts, "okl");
    } catch (e) { note("⚠ service unreachable (" + e + ")", "badl"); }
  }
  async function fullDump() {
    const b = document.getElementById("fulldump");
    b.disabled = true; note("running full dump… (rows 0–487 + hex window)", "warnl");
    try {
      const r = await fetch("/api/full", { cache: "no-store" });
      const j = await r.json();
      if (j.error) { note("⚠ " + j.error, "badl"); return; }
      const hex = j.hexnonzero; delete j.hexnonzero;
      Object.assign(D, j); D.hexnonzero = hex || [];
      renderAll();
      note("full dump loaded — " + j.started, "okl");
    } catch (e) { note("⚠ full dump failed (" + e + ")", "badl"); }
    finally { b.disabled = false; }
  }
  document.getElementById("fulldump").onclick = fullDump;
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
    <div class="card" id="gb-target">
      <h3>Target</h3>
      <div class="frow">
        <div class="field"><label>GPU</label><select id="gb-gpu"><option>scanning…</option></select></div>
        <span class="pill" id="gb-gpustate">checking…</span>
        <span class="pill" id="gb-gpuserial">—</span>
      </div>
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
      <h3>Burn payload</h3>
      <div class="frow">
        <div class="field"><label>target row</label><input type="number" id="gb-row" value="306" min="0" max="487"></div>
        <div class="field"><label>value source</label>
          <select id="gb-srcmode">
            <option value="typed">typed hex</option>
            <option value="dump">from dump row</option>
          </select></div>
        <div class="field" id="gb-typedwrap"><label>value (hex)</label><input type="text" id="gb-value" value="0x00010041" class="mono" style="width:120px"></div>
        <div class="field" id="gb-dumpwrap" style="display:none"><label>source row in dump</label><input type="number" id="gb-srcrow" value="304" min="0" max="487"></div>
        <label class="checkline"><input type="checkbox" id="gb-mirror" checked> burn mirror row too</label>
        <button class="btn" id="gb-check">Check row &amp; guards</button>
      </div>
      <div id="gb-srcdecode" class="note"></div>
      <div id="gb-checkresult" class="note"></div>
      <div class="frow" style="margin-top:10px">
        <div class="field"><label>arm phrase</label><input type="text" id="gb-armphrase" placeholder="type BURN" style="width:110px"></div>
        <button class="btn danger" id="gb-arm">Arm (120 s)</button>
        <span class="pill" id="gb-armstate">not armed</span>
        <button class="btn danger" id="gb-burnnow" disabled>Burn now (Goldilocks GPU only)</button>
        <span class="pill warnl" id="gb-editwarn" style="display:none">payload edited — re-check</span>
      </div>
    </div>
    <div class="card" id="gb-campaign" style="margin-top:12px">
      <h3>Glitch campaign</h3>
      <div class="frow">
        <div class="field"><label>v_dip mV</label><input type="number" id="gc-vdip" value="354"></div>
        <div class="field"><label>pulses</label><input type="number" id="gc-pulses" value="3"></div>
        <div class="field"><label>pw µs</label><input type="number" id="gc-pw" value="198"></div>
        <div class="field"><label>gap µs</label><input type="number" id="gc-gap" value="150"></div>
        <div class="field"><label>delay</label><input type="number" id="gc-delay" value="117"></div>
        <div class="field"><label>max attempts</label><input type="number" id="gc-max" value="100"></div>
        <div class="field"><label>v_dip strategy</label>
          <select id="gc-strategy">
            <option value="fixed">fixed v_dip</option>
            <option value="adaptive">adaptive (Thompson)</option>
          </select></div>
        <div class="field"><label>adaptive v min mV</label><input type="number" id="gc-vmin" value="300"></div>
        <div class="field"><label>adaptive v max mV</label><input type="number" id="gc-vmax" value="380"></div>
      </div>
      <div class="frow">
        <div class="field"><label>pico port</label><select id="gc-port"><option>scanning…</option></select></div>
        <button class="btn" id="gc-ports-refresh" title="rescan serial ports">⟳ rescan</button>
        <div class="field"><label>mode</label>
          <select id="gc-mode">
            <option value="classify">classify only — observe glitch states</option>
            <option value="burn">burn payload on first Goldilocks</option>
          </select></div>
        <div class="field"><label>Goldilocks window</label>
          <select id="gc-hold" title="keep the glitch window open when the campaign hits Goldilocks (skip the VRM revert). Misses/stops always revert.">
            <option value="hold" selected>hold open — no revert (default)</option>
            <option value="revert">auto-revert VRM</option>
          </select></div>
        <button class="btn go" id="gc-start">▶ Start campaign</button>
        <button class="btn danger" id="gc-stop" disabled>■ Stop</button>
        <button class="btn" id="gc-revert" disabled title="hand PMBus control back — closes a held window without a cold boot">⟲ Revert VRM</button>
        <span class="pill" id="gc-state">idle</span>
      </div>
      <div class="chips" id="gc-chips"></div>
      <div class="logbox" id="gc-log">— campaign log —</div>
    </div>
    <div class="dangerstrip">
      Glitching dips NVVDD via the pico; burns are <b>irreversible OTP writes</b>.
      Burn mode requires an armed token, a pure 0→1 payload, matching row state and a
      live Goldilocks window on the target GPU — all verified again server-side
      before CMD_WRITE.
      FF records belong at rows 222–487 (chain=bits[4:0], iff=bit5, block=bits[15:6],
      data=bits[31:16]); a bit-exact readback does NOT prove the shadow latch followed —
      after any burn, watch STATUS_OPT_* on the Fuse Explorer tab.
      The live poll stays safe during glitching (pure reads); avoid the full-dump
      button while a campaign runs.
    </div>`;

  let armToken = null, armExpiry = 0, payloadChecked = null;
  let armRefusal = null;          // sticky arm refusal text; cleared on phrase edit or successful arm
  let targetBdf = null, targetGoldilocks = false;

  // B6: the Check verdict binds to the exact payload — any edit to the burn
  // inputs invalidates it (the check IS the safety contract).
  function invalidateChecked() {
    if (!payloadChecked) return;
    payloadChecked = null;
    $("gb-burnnow").disabled = true;
    $("gb-editwarn").style.display = "";
  }

  // ---- target GPU selector (live Goldilocks state) ----
  function gpuOption(g) {
    const badge = g.goldilocks ? "● Goldilocks" :
                  g.error ? "⚠ unreadable" : "locked";
    return `<option value="${esc(g.bdf)}">${esc(g.bdf)} — ${badge}</option>`;
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
      const prev = targetBdf || j.default;
      const sig = (j.gpus || []).map(g => g.bdf + (g.goldilocks ? "+" : "-")).join();
      if (sel.dataset.sig !== sig) {           // rebuild only when the set changes
        sel.dataset.sig = sig;
        sel.innerHTML = (j.gpus || []).map(gpuOption).join("");
        const match = (j.gpus || []).find(g => g.bdf === prev) || (j.gpus || [])[0];
        if (match) { sel.value = match.bdf; targetBdf = match.bdf; }
      }
      updateGpuState(j);
    } catch (e) {}
  }
  function updateGpuState(j) {
    const g = (j.gpus || []).find(x => x.bdf === targetBdf);
    const pill = $("gb-gpustate");
    if (!g) {
      pill.textContent = "no GA100 detected"; pill.className = "pill warnl";
      targetGoldilocks = false;
    } else if (g.goldilocks) {
      pill.textContent = "● Goldilocks — burn window open";
      pill.className = "pill okl"; targetGoldilocks = true;
    } else if (g.error) {
      pill.textContent = "⚠ " + g.error; pill.className = "pill badl";
      targetGoldilocks = false;
    } else {
      pill.textContent = "locked (DSOV=" + g.dsov + ") — glitch first";
      pill.className = "pill"; targetGoldilocks = false;
    }
    $("gb-gpuserial").innerHTML =
      (g.serial ? "SN " + esc(g.serial) : "no serial") +
      (g.driver ? " · driver " + esc(g.driver) : " · no driver");
    updateArmState();
  }
  $("gb-gpu").onchange = () => {
    targetBdf = $("gb-gpu").value; payloadChecked = null;
    $("gb-checkresult").innerHTML = "";
    $("gb-editwarn").style.display = "none";
    loadGpus();
    loadLayout();
  };
  loadGpus();   // refreshed on demand + when the Glitch tab is shown

  // ---- FF placement policy (row map + budget + live row hint) ----
  let ffLayout = null;
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
    $("gb-budget").innerHTML =
      `safe zone rows <b>${L.burn_zone[0]}–${L.burn_zone[1]}</b> · <b>${L.free_in_zone}</b> free · last boot FF: row ${L.last_occupied}`;
    // B25: never rewrite the user's typed row — updateRowHint shows the zone
    // verdict for whatever row is in the field (a deliberate probe of the SM
    // reserve must survive tab switches and layout refreshes).
    updateRowHint();
  }
  function updateRowHint() {
    const hint = $("gb-rowhint");
    const rv = +$("gb-row").value;
    if (!ffLayout || !ffLayout.burn_zone) { hint.innerHTML = "row —"; hint.className = "pill"; return; }
    const L = ffLayout;
    let txt, cls;
    if (rv >= L.burn_zone[0] && rv <= L.burn_zone[1]) { txt = `row ${rv}: ✓ safe zone`; cls = "ok"; }
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
  async function loadPorts() {
    try {
      const j = await jget("/api/ports");
      const sel = $("gc-port");
      const cur = (sel.value && sel.value.indexOf("scanning") < 0) ?
                  sel.value : (j.default || "/dev/ttyACM0");
      const opts = (j.ports || []).map(p =>
        `<option value="${esc(p.path)}" ${p.path === cur ? "selected" : ""}>` +
        (p.byid ? `${esc(p.byid)} (${esc(p.path)})` : esc(p.path)) + `</option>`).join("");
      sel.innerHTML = opts ||
        `<option value="/dev/ttyACM0">/dev/ttyACM0 (not detected)</option>`;
    } catch (e) {}
  }
  $("gc-ports-refresh").onclick = loadPorts;
  loadPorts();

  function updateArmState() {
    const el = $("gb-armstate");
    const armed = armToken && Date.now() < armExpiry;
    if (armed) {
      armRefusal = null;
      el.textContent = "● armed " + Math.ceil((armExpiry - Date.now()) / 1000) + "s";
      el.className = "pill okl";
    } else {
      armToken = null;
      if (armRefusal) {
        // B5: keep the refusal visible until the phrase is edited or an arm
        // succeeds — the 1 s tick must not erase the only failure explanation.
        el.textContent = armRefusal; el.className = "pill badl";
      } else {
        el.textContent = "not armed"; el.className = "pill";
      }
    }
    $("gb-burnnow").disabled = !payloadChecked || !armed || !targetGoldilocks;
  }
  setInterval(updateArmState, 1000);

  $("gb-arm").onclick = async () => {
    const j = await jpost("/api/arm", {phrase: $("gb-armphrase").value});
    if (j.error) { const el = $("gb-armstate");
      armRefusal = "⚠ " + j.error;
      el.textContent = armRefusal; el.className = "pill badl"; return; }
    armToken = j.token; armExpiry = Date.now() + j.expires_in * 1000;
    updateArmState();
  };
  $("gb-armphrase").oninput = () => { armRefusal = null; updateArmState(); };

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
  $("gb-mirror").onchange = invalidateChecked;

  $("gb-check").onclick = async () => {
    const row = +$("gb-row").value;
    const fromDump = $("gb-srcmode").value === "dump";
    const value = fromDump ? (payloadValue === null ? "0x0" : "0x" + payloadValue.toString(16)) : $("gb-value").value.trim();
    const mirror = $("gb-mirror").checked;
    const res = $("gb-checkresult");
    res.innerHTML = "checking…";
    $("gb-editwarn").style.display = "none";
    const j = await jget(`/api/burn/check?row=${row}&value=${encodeURIComponent(value)}&mirror=${mirror ? 1 : 0}&bdf=${encodeURIComponent(targetBdf || "")}`);
    if (j.error) { res.innerHTML = `<span class="bad">⚠ ${esc(j.error)}</span>`; payloadChecked = null; return; }
    payloadChecked = {row, value, old: j.current, mirror, bdf: j.bdf || targetBdf};
    updateArmState();   // re-evaluate Burn gating against the fresh check
    const guards = (j.guards || []).map(g =>
      `<div class="guardrow"><span class="gs ${g.ok ? "ok" : "bad"}">${g.ok ? "✓" : "✗"}</span>` +
      `<span>${esc(g.name)} = ${typeof g.value === "number" ? fmt(g.value) : esc(String(g.value))}` +
      (g.want !== undefined ? ` (want ${typeof g.want === "number" ? fmt(g.want) : esc(String(g.want))})` : "") +
      `</span></div>`).join("");
    const pol = j.policy;
    const polBlock = pol ? `<div class="${pol.ok ? "ok" : "bad"}" style="margin-top:6px">` +
      `<b>placement policy: ${pol.ok ? "OK — row is in the safe burn zone" : "VIOLATION"}</b>` +
      (pol.issues || []).map(i => `<div>• ${esc(i)}</div>`).join("") + `</div>` : "";
    res.innerHTML =
      `<div>row ${j.row} on <span class="mono">${esc(j.bdf || targetBdf)}</span> currently reads ` +
      `<span class="mono">${fmt(j.current)}</span> · ` +
      `rows to burn: <span class="mono">${(j.rows_to_burn || [row]).join(", ")}</span></div>` +
      polBlock +
      `<div>purity (0→1 superset): <b class="${j.pure_0to1 ? "ok" : "bad"}">${j.pure_0to1 ? "OK" : "FAIL"}</b></div>` +
      `<div class="guardlist">${guards}</div>` +
      (pol && !pol.ok ? "" : `<div class="note" style="margin-top:6px">${esc(j.note || "")}</div>`);
    loadLayout();   // budget may have changed
  };

  $("gb-burnnow").onclick = async () => {
    if (!payloadChecked) { alert("Check the payload first"); return; }
    if (!targetGoldilocks) { alert("Selected GPU is not in the Goldilocks state — " +
      "run a glitch campaign first"); return; }
    if (!confirm("Irreversible OTP burn of row " + payloadChecked.row + " = " +
                 payloadChecked.value + " on " + (payloadChecked.bdf || targetBdf) + "?")) return;
    const j = await jpost("/api/burn", {...payloadChecked, confirm: true, token: armToken});
    $("gb-checkresult").innerHTML =
      `<pre>${esc(JSON.stringify(j, null, 1))}</pre>`;
    loadLayout();   // a burn changes the zone — refresh the map
  };

  // campaign
  function setCampaignUI(j) {
    $("gc-stop").disabled = !j.running;
    $("gc-start").disabled = !!j.running;
    $("gc-revert").disabled = !!j.running || !j.window_held;
    const st = $("gc-state");
    st.textContent = j.running ? "● running" : (j.result || (j.error ? "error" : "idle"));
    st.className = "pill " + (j.running || j.result === "goldilocks" ? "okl" :
                              j.error ? "badl" : "");
    const s = j.stats || {};
    $("gc-chips").innerHTML =
      `<span class="pill">attempts <b>${s.attempts || 0}</b></span>` +
      `<span class="pill">valid <b>${s.valid || 0}</b></span>` +
      `<span class="pill">lost <b>${s.lost || 0}</b></span>` +
      `<span class="pill">nack <b>${s.nack || 0}</b></span>` +
      `<span class="pill">dsov=0 <b>${s.dsov_zero || 0}</b></span>` +
      `<span class="pill ${s.goldilocks ? "okl" : ""}">goldilocks <b>${s.goldilocks ? "YES" : "no"}</b></span>` +
      (j.window_held ? `<span class="pill okl">window HELD open — verify/burn now, then Revert VRM or cold-boot</span>` : "");
    if ((j.log || []).length) {
      const logEl = $("gc-log");
      logEl.textContent = j.log.join("\n");
      logEl.scrollTop = logEl.scrollHeight;
    }
    if (j.error && !j.running) $("gc-log").textContent =
      ($("gc-log").textContent + "\nERROR: " + j.error).trim();
  }
  async function pollGlitch() {
    try { setCampaignUI(await jget("/api/glitch/status")); } catch (e) {}
  }
  $("gc-start").onclick = async () => {
    const mode = $("gc-mode").value;
    const adaptive = $("gc-strategy").value === "adaptive";
    const body = {bdf: targetBdf || undefined, adaptive,
      min_v: +$("gc-vmin").value, max_v: +$("gc-vmax").value,
      v_dip: +$("gc-vdip").value, pulses: +$("gc-pulses").value,
      pw: +$("gc-pw").value, gap: +$("gc-gap").value, delay: +$("gc-delay").value,
      max_attempts: +$("gc-max").value, port: $("gc-port").value, mode,
      no_revert: $("gc-hold").value === "hold"};
    if (mode === "burn") {
      if (!payloadChecked) { alert("Set + Check the burn payload first (burn mode)"); return; }
      if (!armToken) { alert("Arm first (type BURN) — burn mode requires it"); return; }
      if (payloadChecked.bdf && payloadChecked.bdf !== targetBdf) {
        alert("Burn payload was checked on " + payloadChecked.bdf +
              " but the target is " + targetBdf + " — re-check first"); return;
      }
      body.records = [{row: payloadChecked.row, value: payloadChecked.value,
                       old: payloadChecked.old, mirror: payloadChecked.mirror,
                       bdf: targetBdf}];
      body.token = armToken;
      if (!confirm("Start glitching and BURN the payload on first Goldilocks?\n" +
        "target " + targetBdf + " · row " + payloadChecked.row + " ← " +
        payloadChecked.value + " (mirror: " + payloadChecked.mirror + ")\n" +
        "OTP burns are IRREVERSIBLE.")) return;
    } else if (!confirm("Start glitch campaign?\n" +
        "the pico on port " + $("gc-port").value + " dips NVVDD on " +
        (targetBdf || "the configured BDF") + " to " + body.v_dip + " mV — " +
        "each attempt reboots the GPU.")) return;
    const j = await jpost("/api/glitch/start", body);
    if (j.error) alert(j.error);
    pollGlitch();
  };
  $("gc-stop").onclick = () => jpost("/api/glitch/stop", {});
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
    <div class="grid" id="gpu-cards" style="margin-top:12px"></div>
    <div class="card" style="margin-top:12px"><h3>PCIe link (lspci)</h3>
      <div id="gpu-link" class="mono note"></div></div>`;
  const GPU_LABELS = {"name": "GPU", "driver_version": "driver", "memory.total": "VRAM total",
    "memory.used": "VRAM used", "utilization.gpu": "util %",
    "utilization.memory": "mem util %", "temperature.gpu": "temp °C",
    "power.draw": "power W", "power.limit": "limit W", "fan.speed": "fan %",
    "pcie.link.gen.current": "PCIe gen", "pcie.link.gen.max": "PCIe max gen",
    "clocks.sm": "SM MHz", "clocks.mem": "mem MHz", "pstate": "P-state"};
  async function renderGpu(pre) {
    let j = pre;
    if (!j) { try { j = await jget("/api/gpu"); } catch (e) { return; } }
    const n = j.nvidia || {};
    if (n.error) {
      $("gpu-banner").innerHTML = `<b class="warn">nvidia-smi:</b> ` +
        `<span class="mono">${esc(n.error)}</span>`;
      $("gpu-cards").innerHTML = "";
    } else {
      $("gpu-banner").innerHTML = `<b class="ok">nvidia-smi online</b> — ` +
        `updated <span class="mono">${esc(j.ts)}</span>`;
      $("gpu-cards").innerHTML = Object.entries(GPU_LABELS)
        .filter(([k]) => n[k] !== undefined && n[k] !== "[Not Supported]")
        .map(([k, l]) => `<div class="card stat"><div class="k">${l}</div>` +
          `<div class="v mono">${esc(n[k])}</div></div>`).join("");
    }
    $("gpu-link").textContent = (j.link || []).join("\n") || "no link info";
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
      const j = await jget("/api/gpu");
      renderGpu(j);
      const n = j.nvidia || {};
      const t = new Date().toTimeString().slice(0, 8);
      if (n.error) { gmonHist.unshift({t, err: n.error}); }
      else {
        const lim = gnum(n["power.limit"]) || 300;
        const tot = gnum(n["memory.total"]) || 81920;
        gmonHist.unshift({t, name: n["name"],
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
    return (HTML.replace("__PAYLOAD__", payload_json)
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
