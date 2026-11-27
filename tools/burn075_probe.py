#!/usr/bin/env python3
"""Probe: open a Goldilocks window and attempt ONE burn with FULL guard output.
Nothing is journaled/written unless every guard passes (same gates as burn075).
Run ON the HP:  python3 ~/burn075_probe.py
"""
import json, sys, time, urllib.request

B = "http://127.0.0.1:8790"
PROF = {"v_dip": 303, "pulses": 3, "pw": 198, "gap": 150,
        "delay": 117, "t_dip": -60, "cooldown_s": 10, "no_revert": True}

def post(p, body, t=60):
    req = urllib.request.Request(B + p, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=t))

def get(p, t=120):
    return json.load(urllib.request.urlopen(B + p, timeout=t))

r = post("/api/glitch/start", dict(PROF, mode="classify", max_attempts=40), 30)
if not r.get("started"):
    sys.exit(f"campaign refused: {r.get('error')}")
t0, s = time.time(), {}
while time.time() - t0 < 420:
    time.sleep(4)
    st = get("/api/glitch/status", 10)
    s = st.get("stats", {})
    if s.get("goldilocks"):
        break
    if not st.get("running"):
        sys.exit(f"no window: {st.get('result')} {st.get('error')}")
print(f"GOLDILOCKS after {s.get('attempts')} attempts — attempting burn row 313")

dump_rel = get("/api/dumps", 15)[0]["dir"]
a = post("/api/arm", {"phrase": "BURN", "dump": dump_rel}, 30)
tok = a.get("token")
if not tok:
    sys.exit(f"NOT ARMED: {a.get('error')}")
r = post("/api/burn", {"row": 313, "value": "0x416A0942", "old": "0",
                       "confirm": True, "token": tok, "dump": dump_rel})
print("RESULT:", r.get("result") or r.get("error"))
for c in r.get("guards", []):
    v = c.get("value")
    print(("OK  " if c["ok"] else "FAIL"), c["name"],
          hex(v) if isinstance(v, int) else v,
          ("want " + (hex(c["want"]) if isinstance(c.get("want"), int) else str(c.get("want")))) if "want" in c else "")
