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
  .on    { background: rgba(63,185,80,.13); color: var(--ok); border-color: rgba(63,185,80,.4); }
  .off   { background: rgba(210,153,34,.12); color: var(--warn); border-color: rgba(210,153,34,.4); }
  .dead  { background: rgba(248,81,73,.07); color: #b0706b; border-color: rgba(248,81,73,.22); }
  .deadon{ background: repeating-linear-gradient(45deg, rgba(248,81,73,.3) 0 7px, rgba(248,81,73,.08) 7px 14px);
           color: var(--bad); border-color: var(--bad); font-weight: 700; }

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
  /* tmon-style GPU monitor */
  .gmon-row { display: flex; gap: 10px; padding: 2px 0; white-space: nowrap;
              border-bottom: 1px solid var(--border-soft); }
  .gmon-row.ghead { color: var(--muted-foreground); font-size: 10px;
                    text-transform: uppercase; letter-spacing: .04em; }
  .gmon-row.bad { color: #f87171; }
  .gtime { color: var(--muted-foreground); min-width: 62px; }
  .gcell { min-width: 92px; display: inline-block; }
  .gbar { display: inline-block; width: 44px; height: 6px; margin-left: 5px;
          vertical-align: middle; background: var(--border-soft);
          border-radius: 3px; overflow: hidden; }
  .gbar > span { display: block; height: 100%; background: var(--accent); }

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
const regionOf = r => REGIONS.find(x => r >= x.min && r <= x.max);

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
  add("CRC_STATUS", status.CRC_STATUS == null ? "—" : fmt(status.CRC_STATUS),
    status.CRC_STATUS === 0x55 ? "ok" : (status.CRC_STATUS == null ? "" : "bad"),
    status.CRC_STATUS === 0x55 ? "fuse block parses cleanly" : "hash regions invalid");
  add("DSOV", status.DSOV == null ? "—" : String(status.DSOV & 1),
    (status.DSOV & 1) ? "" : "warn",
    (status.DSOV & 1) ? "factory-locked (normal)" : "glitch/burn gate OPEN");
  add("SBFE", status.SBFE == null ? "—" : String(status.SBFE & 1), "",
    (status.SBFE & 1) ? "writes confined to FPF 96–221" : "arbitrary FF writes allowed");
  add("EFP", status.EFP == null ? "—" : String(status.EFP & 1), "", "");
  add("EN_SW_OVERRIDE", status.EN_SW_OVERRIDE == null ? "—" : fmt(status.EN_SW_OVERRIDE),
    "", "row-read override state");
  add("PRIV_MASK", status.PRIV_MASK == null ? "—" : fmt(status.PRIV_MASK),
    status.PRIV_MASK === 0xFFFFFFFF ? "ok" : "warn", "PLM state");
  add("nvidia-smi", esc((D.nvidia_smi || "—").split("\n")[0] || "n/a"),
    /No devices|error|ERR|failed/i.test(D.nvidia_smi || "") ? "bad" : "ok", "device init");
  document.getElementById("status").innerHTML = cards.join("");
}

function renderVerdict() {
  const gpc = D.shadow ? D.shadow.GPC_DISABLE : undefined;
  const fbp = D.shadow ? D.shadow.FBP_DISABLE : undefined;
  if (gpc == null || fbp == null) {
    document.getElementById("verdict").innerHTML = "waiting for data…";
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
  document.getElementById("verdict").innerHTML = html;
}

// topology ---------------------------------------------------------------
let curState = "now";
const STATES = { pre: "Pre-glitch reference", intended: "Intended", now: "NOW (live)" };
function renderStateBtns() {
  const sb = document.getElementById("statebtns");
  sb.innerHTML = Object.entries(STATES).map(([k, l]) =>
    `<button class="btn ${k === curState ? "on" : ""}" data-st="${k}">${l}</button>`).join("");
  sb.querySelectorAll("button").forEach(b => b.onclick = () => {
    curState = b.dataset.st;
    sb.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
    renderTopo();
  });
}
function unit(cls, name, sub) {
  return `<div class="unit ${cls}"><b>${name}</b><span>${sub}</span></div>`;
}
function renderTopo() {
  const sh = D.shadow || {};
  const gpcDef = sh.GPC_DEFECTIVE ?? 0, fbpDef = sh.FBP_DEFECTIVE ?? 0;
  let gpcDis, fbpDis;
  if (curState === "pre")      { gpcDis = 0x86; fbpDis = 0x852; }   // stock 170HX reference
  else if (curState === "intended") { gpcDis = 0x02; fbpDis = 0x840; }
  else { gpcDis = sh.GPC_DISABLE ?? 0; fbpDis = sh.FBP_DISABLE ?? 0; }
  let gpcHtml = "", fbpHtml = "";
  for (let i = 0; i < 8; i++) {
    const dead = (gpcDef >> i) & 1, dis = (gpcDis >> i) & 1;
    const cls = dead ? (dis ? "dead" : "deadon") : (dis ? "off" : "on");
    const sub = dead ? (dis ? "dead · off" : "DEAD · ON!") : (dis ? "floorswept" : "active");
    gpcHtml += unit(cls, "GPC" + i, sub);
  }
  for (let i = 0; i < 12; i++) {
    const dead = (fbpDef >> i) & 1, dis = (fbpDis >> i) & 1;
    const cls = dead ? (dis ? "dead" : "deadon") : (dis ? "off" : "on");
    const sub = dead ? (dis ? "dead · off" : "DUMMY · ON!") : (dis ? "floorswept" : "active");
    fbpHtml += unit(cls, "FBP" + i, sub);
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
    const v = sh["TPC_DISABLE_" + i];
    if (v) html += `<tr><td class="mono">TPC word ${i}</td>` +
      `<td class="mono note">0x${(0x820760 + i * 4).toString(16).toUpperCase()}</td>` +
      `<td class="mono">${fmt(v)}</td><td class="mono">{${bitsOf(v).join(",")}}</td>` +
      `<td class="note">TPC-level mask (mapping approximate)</td></tr>`;
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
  renderMeta(); renderStatus(); renderVerdict(); renderTopo(); renderShadow();
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
      if (j.driver !== undefined) D.driver = j.driver;
      if (j.bdf !== undefined) D.bdf = j.bdf;
      D.started = j.ts;
      diff(j);
      if (heavy) renderLive();
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
  let targetBdf = null, targetGoldilocks = false;

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
    const rv = +$("gb-row").value;               // pull the row into the zone
    if (!(rv >= L.burn_zone[0] && rv <= L.burn_zone[1]))
      $("gb-row").value = L.burn_zone[0];
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
  $("gb-row").oninput = updateRowHint;
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
      el.textContent = "● armed " + Math.ceil((armExpiry - Date.now()) / 1000) + "s";
      el.className = "pill okl";
    } else {
      armToken = null;
      el.textContent = "not armed"; el.className = "pill";
    }
    $("gb-burnnow").disabled = !armed || !targetGoldilocks;
  }
  setInterval(updateArmState, 1000);

  $("gb-arm").onclick = async () => {
    const j = await jpost("/api/arm", {phrase: $("gb-armphrase").value});
    if (j.error) { const el = $("gb-armstate");
      el.textContent = "⚠ " + j.error; el.className = "pill badl"; return; }
    armToken = j.token; armExpiry = Date.now() + j.expires_in * 1000;
    updateArmState();
  };

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
    const dump = $("gb-srcmode").value === "dump";
    $("gb-dumpwrap").style.display = dump ? "" : "none";
    $("gb-typedwrap").style.display = dump ? "none" : "";
    renderSrcDecode();
  };
  $("gb-srcrow").oninput = renderSrcDecode;

  $("gb-check").onclick = async () => {
    const row = +$("gb-row").value;
    const fromDump = $("gb-srcmode").value === "dump";
    const value = fromDump ? (payloadValue === null ? "0x0" : "0x" + payloadValue.toString(16)) : $("gb-value").value.trim();
    const mirror = $("gb-mirror").checked;
    const res = $("gb-checkresult");
    res.innerHTML = "checking…";
    const j = await jget(`/api/burn/check?row=${row}&value=${encodeURIComponent(value)}&mirror=${mirror ? 1 : 0}&bdf=${encodeURIComponent(targetBdf || "")}`);
    if (j.error) { res.innerHTML = `<span class="bad">⚠ ${esc(j.error)}</span>`; payloadChecked = null; return; }
    payloadChecked = {row, value, old: j.current, mirror, bdf: j.bdf || targetBdf};
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
    }
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
      <div id="gmon-head" class="mono gmon-row ghead"></div>
      <div id="gmon" class="mono" style="max-height:360px; overflow-y:auto; font-size:11px"></div>
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
  // ---- tmon-style scrolling monitor ----
  const gmonHist = [];
  const gmonMs = () => +(localStorage.getItem("ga100.gmonMs") || "1000");
  const gnum = v => { const x = parseFloat(v); return isNaN(x) ? null : x; };
  function gcell(v, max, unit) {
    if (v === null) return `<span class="gcell">—</span>`;
    const w = Math.max(0, Math.min(100, (v / max) * 100));
    return `<span class="gcell">${v}${unit}` +
      `<span class="gbar"><span style="width:${w.toFixed(0)}%"></span></span></span>`;
  }
  const GMON_COLS = [["t", "time"], ["temp", "temp"], ["util", "util"],
    ["memu", "mem"], ["pw", "W"], ["sm", "SM"], ["mc", "memclk"],
    ["fan", "fan"], ["vram", "VRAM"]];
  function gmonRender() {
    $("gmon-head").innerHTML = GMON_COLS.map(
      ([, l]) => `<span class="gcell gcol">${l}</span>`).join("");
    $("gmon").innerHTML = gmonHist.map(s => {
      if (s.err) return `<div class="gmon-row bad"><span class="gtime">${s.t}</span>` +
        `⚠ ${esc(s.err)}</div>`;
      return `<div class="gmon-row"><span class="gtime">${s.t}</span>` +
        gcell(s.temp, 100, "°") + gcell(s.util, 100, "%") +
        gcell(s.memu, 100, "%") + gcell(s.pw, s.pwmax, "") +
        gcell(s.sm, 1500, "") + gcell(s.mc, 2000, "") +
        gcell(s.fan, 100, "%") + gcell(s.vram, s.vrammax, "") + `</div>`;
    }).join("");
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
        gmonHist.unshift({t,
          temp: gnum(n["temperature.gpu"]), util: gnum(n["utilization.gpu"]),
          memu: gnum(n["utilization.memory"]), pw: gnum(n["power.draw"]),
          pwmax: lim, sm: gnum(n["clocks.sm"]), mc: gnum(n["clocks.mem"]),
          fan: gnum(n["fan.speed"]), vram: gnum(n["memory.used"]), vrammax: tot});
      }
      if (gmonHist.length > 90) gmonHist.pop();
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
