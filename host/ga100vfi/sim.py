"""Simulated cards for tuning `campaign --adaptive`: python -m ga100vfi.sim [cards].

Each scenario draws cards from a family; every card is run once with the 3D
adaptive Planner, once at fixed defaults (354 mV, delay 117 us, pw 198 us),
and once at its best point (the oracle, which knows the card). Prints
P(Goldilocks within 100 / 500 attempts) and mean attempts (a miss counts as
500). No hardware is touched.

1D scenarios (ours..bimodal) test voltage-only variations at default timing;
the 3D scenarios (lost_island..fake_window) model multi-card field behaviour:
non-monotonic lost islands, big-delay windows (150-465 us), decoy warm bands,
narrow 3D (v_dip, delay, pw) windows with CRC compass gradients and thermal
drift, delay-dependent voltage shifts, and write-only fake windows.
"""
from __future__ import annotations

import math
import random
import sys
from multiprocessing import Pool

from .adaptive import LSB_MV, Planner, Shot, mv_to_code

MIN_V, MAX_V, FIXED_V = 280, 380, 354
MIN_D, MAX_D, FIXED_D = 60, 480, 117
MIN_PW, MAX_PW, FIXED_PW = 150, 260, 198
BUDGET = 500
CODES = list(range(math.ceil(MIN_V / LSB_MV), math.floor(MAX_V / LSB_MV) + 1))


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, x))))


class SimCard:
    def __init__(self, c1, s1, c2, s2, c3, s3, g=lambda c: 1.0, drift_sd=0.0,
                 jump=None, nack=0.0, jitter=None):
        self.c1, self.s1, self.c2, self.s2, self.c3, self.s3 = c1, s1, c2, s2, c3, s3
        self.g, self.drift_sd, self.jump, self.nack = g, drift_sd, jump, nack
        self.jitter = jitter or {}  # code -> extra P(hit survives), a bumpy window
        self.t = 0

    def p_gold(self, c: int) -> float:
        v = c * LSB_MV
        return (_sig((self.c1 - v) / self.s1) * (1 - _sig((self.c2 - v) / self.s2))
                * self.g(c) * self.jitter.get(c, 1.0))

    def best_shot(self) -> Shot:
        c = max(CODES, key=self.p_gold)
        return Shot(round(c * LSB_MV), FIXED_D, FIXED_PW)

    def shoot(self, shot: Shot, rng: random.Random) -> str:
        self.t += 1
        shift = rng.gauss(0, self.drift_sd) if self.drift_sd else 0.0
        if self.jump and self.t == self.jump[0]:
            shift += self.jump[1]
        self.c1 += shift; self.c2 += shift; self.c3 += shift
        if rng.random() < self.nack:
            return "nack"
        c = mv_to_code(shot.v_dip_mv)
        v = c * LSB_MV
        if rng.random() >= _sig((self.c1 - v) / self.s1):
            return "under"
        if rng.random() < _sig((self.c2 - v) / self.s2):
            return "lost" if rng.random() < _sig((self.c3 - v) / self.s3) else "over"
        if rng.random() >= self.jitter.get(c, 1.0):
            return "under"
        return "goldilocks" if rng.random() < self.g(c) else "hit"


class Bimodal:
    """Two voltage windows; the shallow one rarely passes, the deep one always does."""
    def __init__(self, shallow, deep, split_mv):
        self.shallow, self.deep, self.split = shallow, deep, split_mv

    def _side(self, c):
        return self.shallow if c * LSB_MV >= self.split else self.deep

    def p_gold(self, c):
        return self._side(c).p_gold(c)

    def best_shot(self) -> Shot:
        c = max(CODES, key=self.p_gold)
        return Shot(round(c * LSB_MV), FIXED_D, FIXED_PW)

    def shoot(self, shot: Shot, rng: random.Random) -> str:
        return self._side(mv_to_code(shot.v_dip_mv)).shoot(shot, rng)


class LostIslandCard:
    """Non-monotonic card: a PCIe lost island sits in v_dip, Goldilocks sits on
    its shallow edge, and deeper dips give crc=0x00 over-glitch.
    """
    def __init__(self, island_mv: float, island_w: float, deep_over_mv: float,
                 p_pass: float = 0.7):
        self.island_mv = island_mv
        self.island_w = island_w
        self.deep_over_mv = deep_over_mv
        self.p_pass = p_pass
        # Shallow edge sits one PMBus code above the top of the lost island.
        self.sweet_code = mv_to_code(round(island_mv + island_w))

    def best_shot(self) -> Shot:
        return Shot(round(self.sweet_code * LSB_MV), FIXED_D, FIXED_PW)

    def shoot(self, shot: Shot, rng: random.Random) -> str:
        c = mv_to_code(shot.v_dip_mv)
        v = c * LSB_MV
        if c == self.sweet_code:
            return "goldilocks" if rng.random() < self.p_pass else "under"
        if v > self.sweet_code * LSB_MV:
            return "under"
        if abs(v - self.island_mv) <= self.island_w:
            return "lost" if rng.random() < 0.85 else "over"
        if v <= self.deep_over_mv:
            return "over"
        # Between deep_over and island: non-monotonic under/crc_fail gap.
        return "under" if rng.random() < 0.6 else "crc_fail"


class Card3D:
    """3D (v_dip, delay, pw) card with CRC compass states (0x77, 0x75/0x57, 0x55)."""
    def __init__(self, v_edge: float, d_center: float, d_half: float,
                 pw_center: float, pw_half: float,
                 p_gold: float = 0.25,
                 warm_d: float = 22.0, warm_pw: float = 18.0,
                 crc_d: float = 55.0, crc_pw: float = 35.0,
                 v_shift_small: float = 0.0,
                 decoy_d: float | None = None,
                 fake_at_seed: bool = False,
                 drift_d_sd: float = 0.0, drift_v_sd: float = 0.0):
        self.v_edge = v_edge
        self.d_center = d_center
        self.d_half = d_half
        self.pw_center = pw_center
        self.pw_half = pw_half
        self.p_gold = p_gold
        self.warm_d = warm_d
        self.warm_pw = warm_pw
        self.crc_d = crc_d
        self.crc_pw = crc_pw
        self.v_shift_small = v_shift_small
        self.decoy_d = decoy_d
        self.fake_at_seed = fake_at_seed
        self.drift_d_sd = drift_d_sd
        self.drift_v_sd = drift_v_sd

    def _local_v_edge(self, delay_us: int) -> float:
        # Optional shift between small-delay (<160 us) and big-delay regions.
        if self.v_shift_small and delay_us < 160:
            return self.v_edge + self.v_shift_small
        return self.v_edge

    def best_shot(self) -> Shot:
        c = mv_to_code(round(self.v_edge))
        c = max(CODES[0], min(CODES[-1], c))
        return Shot(round(c * LSB_MV), round(self.d_center), round(self.pw_center))

    def shoot(self, shot: Shot, rng: random.Random) -> str:
        if self.drift_d_sd:
            self.d_center = max(MIN_D + 10, min(MAX_D - 10,
                                                self.d_center + rng.gauss(0, self.drift_d_sd)))
        if self.drift_v_sd:
            self.v_edge = max(MIN_V + 6, min(MAX_V - 10,
                                             self.v_edge + rng.gauss(0, self.drift_v_sd)))

        v = mv_to_code(shot.v_dip_mv) * LSB_MV
        ve = self._local_v_edge(shot.delay_us)
        # Voltage gate: too shallow -> under; way too deep -> over/lost.
        if rng.random() >= _sig((ve + 5.0 - v) / 3.0):
            return "under"
        if rng.random() < _sig((ve - 12.0 - v) / 2.5):
            return "lost" if rng.random() < 0.5 else "over"

        # Optional write-only fake at seed (117, 198): dsov=0, crc=0x55, g=0.
        if (self.fake_at_seed and abs(shot.delay_us - FIXED_D) <= 8
                and abs(shot.pw_us - FIXED_PW) <= 12):
            return "hit"

        # Too-wide pw past sweet spot can trigger PCIe loss.
        if shot.pw_us - self.pw_center > self.pw_half + 15:
            return "lost" if rng.random() < 0.7 else "over"

        dd = abs(shot.delay_us - self.d_center)
        dp = abs(shot.pw_us - self.pw_center)

        # Sweet spot: Goldilocks / hit.
        if dd <= self.d_half and dp <= self.pw_half:
            if rng.random() < self.p_gold:
                return "goldilocks"
            return "hit" if rng.random() < 0.5 else "warm"

        # Warm compass halo (0x75 / 0x57) adjacent to the sweet spot.
        if dd <= self.d_half + self.warm_d and dp <= self.pw_half + self.warm_pw:
            p_w = 0.65 * math.exp(-0.5 * ((dd / (self.d_half + self.warm_d)) ** 2
                                          + (dp / (self.pw_half + self.warm_pw)) ** 2))
            if rng.random() < p_w:
                return "warm"
            return "crc_fail"

        # Optional decoy warm region (0x75/0x57 far from the real delay window).
        if (self.decoy_d is not None and abs(shot.delay_us - self.decoy_d) <= 20
                and dp <= self.pw_half + 15):
            return "warm" if rng.random() < 0.5 else "crc_fail"

        # Broader CRC-alive disturbance band (0x77).
        if dd <= self.d_half + self.crc_d and dp <= self.pw_half + self.crc_pw:
            return "crc_fail" if rng.random() < 0.6 else "over"

        return "over" if rng.random() < 0.75 else "lost"


def _window(r, lo=310, hi=375):
    c1 = r.uniform(lo, hi)
    c2 = c1 - r.uniform(3, 20)
    return c1, r.uniform(2, 6), c2, r.uniform(1, 5), c2 - r.uniform(0, 15), r.uniform(1, 5)


def _card(scn: str, r: random.Random):
    if scn == "ours":
        return SimCard(349, 3.8, 343, 1.5, 330, 3)
    if scn == "random":
        return SimCard(*_window(r))
    if scn == "narrow":
        c1 = r.uniform(310, 375); c2 = c1 - r.uniform(0, 4)
        return SimCard(c1, r.uniform(3, 6), c2, r.uniform(2, 5), c2 - r.uniform(0, 10), 3)
    if scn == "edge":
        c1 = r.uniform(284, 298) if r.random() < 0.5 else r.uniform(370, 382)
        c2 = c1 - r.uniform(3, 20)
        return SimCard(c1, r.uniform(2, 6), c2, r.uniform(1, 5), c2 - r.uniform(0, 15), 3)
    if scn == "drift":
        return SimCard(*_window(r), drift_sd=0.15)
    if scn == "jump":
        return SimCard(*_window(r, 315, 368),
                       jump=(r.randint(50, 200), r.choice((-1, 1)) * r.uniform(6, 15)))
    if scn == "flaky":
        w = list(_window(r)); w[4] = w[2] + 5
        return SimCard(*w, nack=0.05)
    if scn == "bumpy":
        return SimCard(*_window(r), jitter={c: r.uniform(0.1, 1.0) for c in CODES})
    if scn == "low_g":
        gv = r.uniform(0.03, 0.3)
        return SimCard(*_window(r), g=lambda c: gv)
    if scn == "rare":
        gv = r.uniform(0.01, 0.08)
        return SimCard(*_window(r), g=lambda c: gv)
    if scn == "deep_g":
        w = _window(r); cg = w[0] - r.uniform(0, 10); sg = r.uniform(1, 4)
        return SimCard(*w, g=lambda c: _sig((c * LSB_MV - cg) / sg))
    if scn == "dead_codes":
        dead = {c for c in CODES if r.random() < 0.5}
        return SimCard(*_window(r), g=lambda c: 0.0 if c in dead else 1.0)
    if scn == "dead_rare":
        dead = {c for c in CODES if r.random() < 0.5}
        gv = r.uniform(0.02, 0.15)
        return SimCard(*_window(r), g=lambda c: 0.0 if c in dead else gv)
    if scn == "needle":
        w = _window(r)
        hitting = [c for c in CODES if SimCard(*w).p_gold(c) > 0.02] or CODES
        good = r.choice(hitting)
        return SimCard(*w, g=lambda c: 0.3 if c == good else 0.0)
    if scn == "bimodal":
        c1 = r.uniform(340, 376); c1b = r.uniform(295, c1 - 18)
        shallow = SimCard(c1, r.uniform(2, 4), c1 - r.uniform(3, 8), 2, c1 - 30, 3,
                          g=lambda c: 0.15)
        deep = SimCard(c1b, r.uniform(2, 4), c1b - r.uniform(3, 8), 2, c1b - 10, 3)
        return Bimodal(shallow, deep, c1 - 12)

    # --- 3D / multi-card scenarios ---
    if scn == "lost_island":
        # Non-monotonic lost island with Goldilocks on its shallow edge.
        isl = r.uniform(320, 355)
        return LostIslandCard(isl, r.uniform(5, 10), isl - r.uniform(20, 35))
    if scn == "big_delay":
        # Small-delay dead, big-delay sweet spot, default pw.
        return Card3D(v_edge=r.uniform(292, 340),
                      d_center=r.uniform(220, 440), d_half=r.uniform(10, 18),
                      pw_center=r.uniform(188, 208), pw_half=14.0,
                      p_gold=r.uniform(0.15, 0.4))
    if scn == "big_delay_decoy":
        # Decoy warm band ~120 us away from the real big-delay window.
        dc = r.uniform(300, 430)
        return Card3D(v_edge=r.uniform(292, 330),
                      d_center=dc, d_half=r.uniform(8, 15),
                      pw_center=r.uniform(190, 206), pw_half=14.0,
                      p_gold=r.uniform(0.15, 0.35),
                      decoy_d=dc - r.uniform(100, 150))
    if scn == "full_3d":
        # Narrow big-delay + non-default pw + low v_dip.
        pwc = r.choice((r.uniform(165, 182), r.uniform(215, 240)))
        return Card3D(v_edge=r.uniform(288, 330),
                      d_center=r.uniform(200, 440), d_half=r.uniform(4, 7),
                      pw_center=pwc, pw_half=r.uniform(8, 12),
                      p_gold=r.uniform(0.15, 0.35),
                      warm_d=18.0, warm_pw=16.0, crc_d=45.0, crc_pw=30.0)
    if scn == "narrow_3d_drift":
        # Narrow 3D window + thermal drift in delay and v_dip.
        pwc = r.choice((r.uniform(168, 182), r.uniform(216, 238)))
        return Card3D(v_edge=r.uniform(290, 325),
                      d_center=r.uniform(220, 420), d_half=4.0,
                      pw_center=pwc, pw_half=9.0,
                      p_gold=r.uniform(0.15, 0.30),
                      warm_d=16.0, warm_pw=15.0, crc_d=40.0, crc_pw=28.0,
                      drift_d_sd=0.08, drift_v_sd=0.05)
    if scn == "v_shift_3d":
        # Voltage edge is 35-50 mV deeper in big-delay than at seed delay=117.
        return Card3D(v_edge=r.uniform(290, 315),
                      d_center=r.uniform(240, 430), d_half=r.uniform(8, 14),
                      pw_center=r.uniform(188, 212), pw_half=13.0,
                      p_gold=r.uniform(0.15, 0.35),
                      v_shift_small=r.uniform(35, 50))
    if scn == "fake_window":
        # Write-only fake at seed (117, 198); real Goldilocks in big-delay.
        return Card3D(v_edge=r.uniform(295, 340),
                      d_center=r.uniform(230, 430), d_half=r.uniform(10, 16),
                      pw_center=r.uniform(185, 215), pw_half=14.0,
                      p_gold=r.uniform(0.15, 0.35),
                      fake_at_seed=True)
    raise KeyError(scn)


SCENARIOS = (
    "ours", "random", "narrow", "edge", "drift", "jump", "flaky", "bumpy",
    "low_g", "rare", "deep_g", "dead_codes", "dead_rare", "needle", "bimodal",
    "lost_island", "big_delay", "big_delay_decoy", "full_3d",
    "narrow_3d_drift", "v_shift_3d", "fake_window",
)


def _run(job):
    scn, seed = job
    out = {}
    for name in ("adaptive", "fixed", "oracle"):
        card = _card(scn, random.Random(seed))
        rng = random.Random(seed * 7919 + 1)
        planner = (Planner(MIN_V, MAX_V, MIN_D, MAX_D, MIN_PW, MAX_PW,
                           FIXED_D, FIXED_PW, rng=random.Random(seed + 1))
                   if name == "adaptive" else None)
        fixed_shot = Shot(FIXED_V, FIXED_D, FIXED_PW)
        out[name] = None
        for t in range(1, BUDGET + 1):
            if planner:
                shot = planner.next_shot()
            elif name == "fixed":
                shot = fixed_shot
            else:
                shot = card.best_shot()
            outcome = card.shoot(shot, rng)
            if outcome == "goldilocks":
                out[name] = t
                break
            if planner and outcome != "nack":
                planner.record(shot, outcome)
    return scn, out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cards = int(argv[0]) if argv else 200
    jobs = [(s, 1000 * i + 17) for s in SCENARIOS for i in range(cards)]
    with Pool() as pool:
        results = pool.map(_run, jobs, chunksize=4)
    runs = {}
    for scn, out in results:
        for name, t in out.items():
            runs.setdefault((scn, name), []).append(t)
    names = ("adaptive", "fixed", "oracle")
    print(f"{cards} cards per scenario, budget {BUDGET}; "
          "P(Goldilocks) % within 100 / 500, mean attempts\n")
    print("| scenario | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for scn in SCENARIOS:
        cells = []
        for name in names:
            ts = runs[(scn, name)]
            p100 = 100 * sum(t is not None and t <= 100 for t in ts) / len(ts)
            p500 = 100 * sum(t is not None for t in ts) / len(ts)
            mean = sum(BUDGET if t is None else t for t in ts) / len(ts)
            cells.append(f"{p100:.0f} / {p500:.0f}, {mean:.0f}")
        print(f"| {scn} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
