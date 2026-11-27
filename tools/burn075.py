#!/usr/bin/env python3
"""Burn DEVIDA/DEVIDB on CMP 170HX ...075 -> A100 identity. Run ON the HP bench.

  python3 ~/burn075.py

Flow (razk-proven): fresh dump -> glitch to Goldilocks -> arm -> in-process
burn campaign (burns at FIRST Goldilocks, milliseconds after detection —
the only path that beats window decay; standalone /api/burn loses the race).
Nothing is written unless every gate passes. Rows 313/314 only.
"""
import json, sys, time, urllib.request

B = "http://127.0.0.1:8790"
DUMP = "sn-1332021030075"
RECS = [{"row": 313, "value": "0x416A0942", "old": "0"},   # DEVIDA -> 0x20B5
        {"row": 314, "value": "0x416A0982", "old": "0"}]   # DEVIDB
PROF = {"v_dip": 303, "pulses": 3, "pw": 198, "gap": 150,
        "delay": 117, "t_dip": -60, "cooldown_s": 10, "no_revert": True}

def post(p, body, t=60):
    req = urllib.request.Request(B + p, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=t))

def get(p, t=120):
    return json.load(urllib.request.urlopen(B + p, timeout=t))

def campaign(extra, budget=420):
    r = post("/api/glitch/start", dict(PROF, max_attempts=40, **extra), 30)
    if not r.get("started"):
        sys.exit(f"campaign refused: {r.get('error')}")
    t0, s = time.time(), {}
    while time.time() - t0 < budget:
        time.sleep(4)
        st = get("/api/glitch/status", 10)
        s = st.get("stats", {})
        if extra.get("mode") == "burn":
            if len(s.get("burned", [])) >= len(RECS) or s.get("burn_aborts"):
                break
        elif s.get("goldilocks"):
            break
        if not st.get("running"):
            break
    return s

# 1. BASE gate
g = get("/api/gpus", 15)["gpus"][0]
print(f"card {g['serial']}  driver={g['driver']}  crc={g['crc_ok']}")
if g["driver"]:
    sys.exit("driver is BOUND — detach first (Drivers tab), nothing burned")
full = get("/api/full")
r = full["rows"]
print(f"BASE rows 313={hex(r.get('313', -1))} 314={hex(r.get('314', -1))} crc={full['crc_ok']}")
todo = [rec for rec in RECS if r.get(str(rec["row"]), 0) == 0]
done = [rec["row"] for rec in RECS if r.get(str(rec["row"]), 0) == rec["value"].__str__() or r.get(str(rec["row"]), 0) == int(rec["value"], 16)]
bad = [rec["row"] for rec in RECS if r.get(str(rec["row"]), 0) not in (0, int(rec["value"], 16))]
if bad:
    sys.exit(f"rows {bad} hold UNEXPECTED values — check journal, nothing burned")
if done:
    print(f"already burned: rows {done}")
if not todo:
    sys.exit("both rows already carry the target words — nothing to do")
RECS = todo
dump_rel = get("/api/dumps", 15)[0]["dir"]
print(f"dump saved: {dump_rel}")

# 2. Goldilocks (classify, window held open)
s = campaign({"mode": "classify"})
print(f"Goldilocks={s.get('goldilocks')} after {s.get('attempts')} attempts")
if not s.get("goldilocks"):
    sys.exit("NO WINDOW — nothing burned")

# 3. Arm (identity gate vs the fresh dump) then burn IN-PROCESS immediately
a = post("/api/arm", {"phrase": "BURN", "dump": dump_rel}, 30)
tok = a.get("token")
if not tok:
    sys.exit(f"NOT ARMED: {a.get('error')}")
print("armed, launching burn campaign")
s = campaign({"mode": "burn", "records": RECS, "token": tok})
burned = s.get("burned", [])
for b in burned:
    print(f"  row {b['row']}: {b['result']}")
if s.get("burn_aborts"):
    sys.exit(f"BURN ABORTED ({s['burn_aborts']}) — card state in /api/burn/last")

# 4. Readback
full = get("/api/full")
r = full["rows"]
ok = r.get("313") == 0x416A0942 and r.get("314") == 0x416A0982
print(f"READBACK 313={hex(r.get('313', -1))} 314={hex(r.get('314', -1))} crc={full['crc_ok']}")
print("BURN VERIFIED — card is DEVIDA 0x20B5 after next cold boot; flash the A100 VBIOS now"
      if ok else "READBACK MISMATCH — check journal before touching anything")
