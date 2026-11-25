"""3D adaptive planner for `campaign --adaptive`: (v_dip, delay, pw) search.

Guided by NV_FUSE_CRC_STATUS as a compass:
  under     (dsov=1, crc=0x55): dip too shallow or timing missed fuse sense
  crc_fail  (e.g. crc=0x77):    fuse block disturbed, CRC logic still alive
  warm      (e.g. 0x75, 0x57):  one CRC half valid — adjacent to sweet spot
  hit       (dsov=0, crc=0x55): CRC valid, another Goldilocks check failed
  over      (dsov=0, crc=0x00): over-glitched, CRC logic wiped
  lost      (PCIe link down):   too deep / lost island

Three-level Thompson hierarchy:
  1. Regions (clusters in delay/pw space) vs coarse space-filling exploration:
     non-winning shots inside any arm of a cluster decay the whole cluster so
     decoy warm bands and write-only fake windows cannot trap the search.
  2. Arms ((delay, pw) points) within the selected cluster: dynamically refined
     around crc_fail and warm signals down to 4 us delay / 6 us pw steps.
  3. 1D particle-filter voltage model over PMBus codes (6.25 mV/LSB) per arm,
     with shallow-edge probing for lost islands, particle rejuvenation for
     non-monotonic cards, and local voltage inheritance.
Exponential recency decay lets the search follow thermal drift.

`python -m ga100vfi.sim` benchmarks this against fixed settings and an oracle.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

# PMBus VOUT_COMMAND LSB; matches VID_LSB_MV / mv_to_code() in firmware/pwmvid.c.
LSB_MV = 6.25
# Particles per arm: only the fired arm updates each shot (~0.3 ms per shot).
PARTICLES = 250
# Exponential forgetting per shot for thermal drift tracking (half-life ~140).
DRIFT_DECAY = 0.995
# Initial 1D calibration bounds on the seed (delay, pw) before widening to 3D.
SEED_MIN_SHOTS = 8
SEED_MAX_SHOTS = 16
# Cap refined arms per cluster so local refinement stays bounded.
MAX_CLUSTER_ARMS = 48

COMPASS_OUTCOMES = ("under", "crc_fail", "warm", "hit", "over", "lost",
                    "poisoned", "goldilocks")
_TIER = {"under": 0, "over": 0, "lost": 0, "crc_fail": 1, "warm": 2, "hit": 3}


@dataclass(frozen=True)
class Shot:
    v_dip_mv: int
    delay_us: int
    pw_us: int


def mv_to_code(mv: int) -> int:
    return int(mv / LSB_MV + 0.5)


def classify_outcome(v) -> str:
    """Classify a BAR0 Verdict into a compass outcome for the planner."""
    if v.passed:
        return "goldilocks"
    if getattr(v, "poisoned", False):
        # dead fuse controller, not a voltage data point: callers must
        # NOT feed this to the planner and must end the boot (poison
        # persists until a power cycle)
        return "poisoned"
    crc = v.crc_status & 0xFF
    if v.dsov == 1 and crc == 0x55:
        return "under"
    if v.dsov == 0 and crc == 0x55:
        return "hit"
    if crc not in (0x00, 0x55, 0xFF):
        if ((crc ^ 0x55).bit_count() == 1
                or (crc & 0x0F) == 0x5 or (crc & 0xF0) == 0x50):
            return "warm"
        return "crc_fail"
    if v.dsov == 1:
        return "crc_fail"
    return "over"


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, x))))


def _space_fill(lo: int, hi: int, step: int) -> list[int]:
    """Grid points in [lo, hi] ordered by recursive midpoint bisection."""
    if lo >= hi:
        return [lo]
    pts = list(range(lo, hi + 1, step))
    if pts[-1] < hi:
        pts.append(hi)
    order: list[int] = []
    queue = [(0, len(pts) - 1)]
    seen: set[int] = set()
    while queue:
        a, b = queue.pop(0)
        if a > b:
            continue
        mid = (a + b) // 2
        if mid not in seen:
            seen.add(mid)
            order.append(pts[mid])
        if a <= mid - 1:
            queue.append((a, mid - 1))
        if mid + 1 <= b:
            queue.append((mid + 1, b))
    return order


def _pw_slices(lo: int, hi: int, seed_pw: int, step: int) -> list[int]:
    """PW grid anchored at seed_pw and ordered outward."""
    if lo >= hi:
        return [seed_pw]
    pts = [seed_pw]
    k = 1
    while True:
        added = False
        hi_p = seed_pw + k * step
        lo_p = seed_pw - k * step
        if hi_p <= hi:
            pts.append(hi_p)
            added = True
        if lo_p >= lo:
            pts.append(lo_p)
            added = True
        if not added:
            break
        k += 1
    if max(pts) + step // 2 < hi:
        pts.append(hi)
    if min(pts) - step // 2 > lo:
        pts.append(lo)
    return pts


class _VModel:
    """1D particle-filter voltage planner over PMBus codes for one (delay, pw)."""

    def __init__(self, codes: list[int], min_mv: int, max_mv: int,
                 rng: random.Random, v_hint: float | None = None,
                 hint_sd: float = 8.0):
        self.codes = codes
        self.code_set = set(codes)
        self.min_mv = min_mv
        self.max_mv = max_mv
        self.rng = rng
        self.v_hint = v_hint
        self.shots = 0
        self.particles: list[tuple[float, float, float, float]] = []
        for i in range(PARTICLES):
            # When a local voltage hint exists, center 80% of particles on it
            # and keep 20% wide so large delay-dependent shifts still converge.
            if v_hint is not None and i < (PARTICLES * 4) // 5:
                mid = max(float(min_mv), min(float(max_mv + 8),
                                             v_hint + rng.gauss(0.0, hint_sd)))
                w = rng.uniform(4.0, 20.0)
                c1 = mid + 0.5 * w
                c2 = mid - 0.5 * w
            else:
                c1 = rng.uniform(min_mv, max_mv + 15)
                c2 = c1 - rng.uniform(0.0, 25.0)
            self.particles.append((
                c1, rng.uniform(1.5, 7.0), c2, rng.uniform(1.0, 6.0),
            ))
        self.weights = [1.0 / PARTICLES] * PARTICLES
        self.failed_hits = dict.fromkeys(codes, 0.0)
        self.warm_hits = dict.fromkeys(codes, 0.0)
        self.crc_fails = dict.fromkeys(codes, 0.0)
        self.over_lost = dict.fromkeys(codes, 0.0)
        self.unders = dict.fromkeys(codes, 0.0)
        self.tried = set()
        self.min_under_mv: float | None = None
        self.max_deep_mv: float | None = None
        self.seen_active = False
        self.seen_hit_or_warm = False

    def bracket_gap(self) -> float:
        if self.min_under_mv is None or self.max_deep_mv is None:
            return float("inf")
        return self.min_under_mv - self.max_deep_mv

    def shallow_edge_code(self) -> int | None:
        """Code directly above the highest observed lost/over code, if untested."""
        deeps = [c for c in self.codes if self.over_lost[c] >= 0.75]
        if not deeps:
            return None
        edge = max(deeps) + 1
        if (edge in self.code_set and self.over_lost[edge] < 0.75
                and self.unders[edge] < 1.8 and self.crc_fails[edge] < 0.75):
            return edge
        return None

    def v_estimate(self) -> float | None:
        """Posterior mean window midpoint if this model is calibrated."""
        if not (self.seen_active
                or (self.min_under_mv is not None and self.max_deep_mv is not None)):
            return None
        return sum(w * 0.5 * (p[0] + p[2])
                   for w, p in zip(self.weights, self.particles))

    def next_mv(self) -> int:
        # First probe on an arm with a voltage hint fires right at the hint so
        # coarse/refined probes test the calibrated voltage immediately.
        if self.shots == 0 and self.v_hint is not None:
            c = max(self.codes[0], min(self.codes[-1], mv_to_code(round(self.v_hint))))
            return round(c * LSB_MV)

        r = self.rng
        edge = None if self.seen_hit_or_warm else self.shallow_edge_code()
        if edge is not None:
            gap = self.bracket_gap()
            if self.unders[edge] < 0.5 and (gap <= 26.0 or r.random() < 0.6):
                return round(edge * LSB_MV)

        # On a stuck arm (no hit/warm after several shots), probe an untried
        # code — preferring the midpoint of the upper untried band above
        # min_under_mv — so non-monotonic lost islands above a lower crc_fail
        # band are discovered quickly.
        if not self.seen_hit_or_warm and self.shots >= 4:
            if self.min_under_mv is not None:
                hi_untried = [c for c in self.codes
                              if c not in self.tried and c * LSB_MV > self.min_under_mv + 6.0]
                if hi_untried and (self.shots == 4 or r.random() < 0.25):
                    return round(r.choice(hi_untried) * LSB_MV)
            if self.shots >= 6 and r.random() < 0.20:
                untried = [c for c in self.codes if c not in self.tried]
                if untried:
                    return round(r.choice(untried) * LSB_MV)

        c1, s1, c2, s2 = r.choices(self.particles, weights=self.weights)[0]
        best, best_score = self.codes[0], -1.0
        for c in self.codes:
            v = c * LSB_MV
            p_hit = _sig((c1 - v) / s1) * (1.0 - _sig((c2 - v) / s2))
            if edge is not None and c == edge:
                p_hit = max(p_hit, 0.75)
            g = r.betavariate(
                1.0,
                1.0 + self.failed_hits[c] + 0.35 * self.warm_hits[c]
                + 0.7 * self.crc_fails[c],
            )
            score = p_hit * g
            if score > best_score:
                best, best_score = c, score
        return round(best * LSB_MV)

    def record(self, mv: int, outcome: str) -> None:
        self.shots += 1
        for k in self.failed_hits:
            self.failed_hits[k] *= 0.994
            self.warm_hits[k] *= 0.985
            self.crc_fails[k] *= 0.985
            self.over_lost[k] *= 0.985
            self.unders[k] *= 0.985
        c = mv_to_code(mv)
        if c not in self.code_set:
            c = min(self.codes, key=lambda x: abs(x - c))
        self.tried.add(c)
        v = c * LSB_MV
        if outcome == "hit":
            self.failed_hits[c] += 1.0
            self.seen_active = True
            self.seen_hit_or_warm = True
        elif outcome == "warm":
            self.warm_hits[c] += 1.0
            self.seen_active = True
            self.seen_hit_or_warm = True
        elif outcome == "crc_fail":
            self.crc_fails[c] += 1.0
            self.seen_active = True
        elif outcome in ("over", "lost"):
            self.over_lost[c] += 1.0
            if self.max_deep_mv is None or v > self.max_deep_mv:
                self.max_deep_mv = v
        elif outcome == "under":
            self.unders[c] += 1.0
            if self.min_under_mv is None or v < self.min_under_mv:
                self.min_under_mv = v

        for i, (c1, s1, c2, s2) in enumerate(self.particles):
            glitch = _sig((c1 - v) / s1)
            over = _sig((c2 - v) / s2)
            if outcome == "under":
                like = 1.0 - glitch
            elif outcome in ("hit", "warm", "crc_fail"):
                like = glitch * (1.0 - over)
            else:
                like = glitch * over
            self.weights[i] *= max(like, 1e-12)
        total = sum(self.weights)
        self.weights = [w / total for w in self.weights]
        if 1.0 / sum(w * w for w in self.weights) < len(self.particles) / 3:
            r = self.rng
            n = len(self.particles)
            n_fresh = max(4, n // 16)
            picked = r.choices(self.particles, weights=self.weights, k=n - n_fresh)
            new_p = [
                (c1 + r.gauss(0, 0.8), max(1.0, s1 + r.gauss(0, 0.2)),
                 c2 + r.gauss(0, 0.8), max(0.8, s2 + r.gauss(0, 0.2)))
                for c1, s1, c2, s2 in picked
            ]
            # Re-inject a small fraction of wide particles so non-monotonic
            # cards (lost islands, bimodal windows) and sudden jumps cannot
            # permanently trap the filter in a false local band.
            for _ in range(n_fresh):
                c1 = r.uniform(self.min_mv, self.max_mv + 15)
                new_p.append((
                    c1, r.uniform(1.5, 7.0),
                    c1 - r.uniform(0.0, 25.0), r.uniform(1.0, 6.0),
                ))
            self.particles = new_p
            self.weights = [1.0 / n] * n


class _Arm:
    """State for one (delay_us, pw_us) point inside a _Cluster."""

    def __init__(self, delay_us: int, pw_us: int, vmodel: _VModel,
                 cluster: _Cluster, prior_alpha: float, prior_beta: float,
                 scale: int = 0):
        self.delay_us = delay_us
        self.pw_us = pw_us
        self.vmodel = vmodel
        self.cluster = cluster
        self.scale = scale  # 0=coarse/seed, 1=medium, 2=tight
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.alpha = 0.0
        self.beta = 0.0
        self.fails = 0.0
        self.last_t = 0
        self.shots = 0
        self.seen_under = False
        self.seen_deep = False
        self.seen_crc = 0
        self.seen_warm = 0
        self.seen_hit = 0

    def _decay(self, t: int) -> None:
        if t > self.last_t:
            f = DRIFT_DECAY ** (t - self.last_t)
            self.alpha *= f
            self.beta *= f
            self.fails *= f
            self.last_t = t

    def score(self, rng: random.Random, t: int) -> float:
        self._decay(t)
        p_win = rng.betavariate(self.prior_alpha + self.alpha,
                                self.prior_beta + self.beta)
        p_conv = rng.betavariate(1.0, 1.0 + self.fails)
        return p_win * p_conv

    def record(self, mv: int, outcome: str, t: int) -> None:
        self._decay(t)
        self.vmodel.record(mv, outcome)
        self.shots += 1
        if outcome == "under":
            self.seen_under = True
            self.beta += 0.75
            self.fails += 0.05
        elif outcome in ("over", "lost"):
            self.seen_deep = True
            self.beta += 0.75
            self.fails += 0.05
        elif outcome == "crc_fail":
            self.seen_deep = True
            self.seen_crc += 1
            self.alpha += 0.65
            self.beta += 0.45
            self.fails += 0.45
        elif outcome == "warm":
            self.seen_deep = True
            self.seen_warm += 1
            self.alpha += 1.4
            self.beta += 0.20
            self.fails += 0.90
        elif outcome == "hit":
            self.seen_deep = True
            self.seen_hit += 1
            self.alpha += 2.5
            self.beta += 0.10
            self.fails += 0.30


class _Cluster:
    """Localized (delay, pw) neighborhood with shared failure accounting."""

    def __init__(self, center_d: int, center_p: int,
                 prior_alpha: float = 0.5, prior_beta: float = 2.0,
                 is_seed: bool = False):
        self.center_d = center_d
        self.center_p = center_p
        self.is_seed = is_seed
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.arms: list[_Arm] = []
        self.alpha = 0.0
        self.beta = 0.0
        self.fails = 0.0
        self.last_t = 0
        self.best_tier = 0
        self.warm_d_sum = 0.0
        self.warm_p_sum = 0.0
        self.warm_n = 0

    def warm_centroid(self) -> tuple[float, float] | None:
        if self.warm_n == 0:
            return None
        return self.warm_d_sum / self.warm_n, self.warm_p_sum / self.warm_n

    def _decay(self, t: int) -> None:
        if t > self.last_t:
            f = DRIFT_DECAY ** (t - self.last_t)
            self.alpha *= f
            self.beta *= f
            self.fails *= f
            self.last_t = t

    def score(self, rng: random.Random, t: int) -> float:
        self._decay(t)
        p_win = rng.betavariate(self.prior_alpha + self.alpha,
                                self.prior_beta + self.beta)
        p_conv = rng.betavariate(1.0, 1.0 + self.fails)
        return p_win * p_conv

    def record(self, outcome: str, t: int) -> None:
        self._decay(t)
        tier = _TIER.get(outcome, 0)
        if tier > self.best_tier:
            # Progressing to a stronger compass tier forgives earlier search
            # failures inside this cluster; hitting tier 3 (hit) forgives more.
            self.best_tier = tier
            self.fails *= 0.15 if tier == 3 else 0.35
        if outcome in ("under", "over", "lost"):
            self.beta += 0.55
            self.fails += 0.07
        elif outcome == "crc_fail":
            self.alpha += 0.85
            self.beta += 0.25
            self.fails += 0.15
        elif outcome == "warm":
            self.alpha += 1.4
            self.beta += 0.15
            self.fails += 0.35
        elif outcome == "hit":
            self.alpha += 2.2
            self.beta += 0.10
            self.fails += 0.30


class Planner:
    """Adaptive 3D (v_dip, delay, pw) planner.

    When min_delay == max_delay and min_pw == max_pw, collapses cleanly to
    pure 1D v_dip search.
    """

    def __init__(self, min_mv: int, max_mv: int,
                 min_delay: int = 60, max_delay: int = 480,
                 min_pw: int = 150, max_pw: int = 260,
                 seed_delay: int = 117, seed_pw: int = 198,
                 rng: random.Random | None = None):
        if min_delay > max_delay:
            raise ValueError(f"min_delay ({min_delay}) > max_delay ({max_delay})")
        if min_pw > max_pw:
            raise ValueError(f"min_pw ({min_pw}) > max_pw ({max_pw})")
        self.rng = rng or random.Random()
        self.min_mv, self.max_mv = min_mv, max_mv
        self.min_delay, self.max_delay = min_delay, max_delay
        self.min_pw, self.max_pw = min_pw, max_pw
        self.codes = list(range(math.ceil(min_mv / LSB_MV),
                                math.floor(max_mv / LSB_MV) + 1))
        if not self.codes:
            raise ValueError(f"no PMBus code between {min_mv} and {max_mv} mV")

        self.seed_delay = max(min_delay, min(max_delay, seed_delay))
        self.seed_pw = max(min_pw, min(max_pw, seed_pw))
        self.is_1d = (min_delay == max_delay and min_pw == max_pw)

        self.t = 0
        self.arms: dict[tuple[int, int], _Arm] = {}
        self.clusters: list[_Cluster] = []

        self.seed_cluster = _Cluster(self.seed_delay, self.seed_pw,
                                     prior_alpha=1.0, prior_beta=1.5,
                                     is_seed=True)
        self.clusters.append(self.seed_cluster)
        seed_vm = _VModel(self.codes, min_mv, max_mv, self.rng, v_hint=None)
        self.seed_arm = _Arm(self.seed_delay, self.seed_pw, seed_vm,
                             self.seed_cluster, prior_alpha=1.0, prior_beta=1.5)
        self.seed_cluster.arms.append(self.seed_arm)
        self.arms[(self.seed_delay, self.seed_pw)] = self.seed_arm

        self.coarse_queue: list[tuple[int, int]] = []
        self._coarse_round = 0
        if not self.is_1d:
            self._fill_coarse_queue()
        self._bracketing: _Arm | None = None
        # Decision context of the last emitted shot (for run telemetry).
        self.last_decision: dict | None = None

    def _fill_coarse_queue(self) -> None:
        """Build space-filling (delay, pw) exploration candidates."""
        r = self._coarse_round
        self._coarse_round += 1
        d_step = 30 if r == 0 else 15
        p_step = 22 if r == 0 else 11
        delays = _space_fill(self.min_delay, self.max_delay, d_step)
        pws = _pw_slices(self.min_pw, self.max_pw, self.seed_pw, p_step)
        for p in pws:
            for d in delays:
                if (r == 0 and p == self.seed_pw
                        and abs(d - self.seed_delay) <= 12):
                    continue
                if (d, p) not in self.arms:
                    self.coarse_queue.append((d, p))

    def _v_hint(self, delay_us: int) -> float | None:
        """Estimate active v_dip near delay_us from calibrated arms."""
        num = den = 0.0
        for arm in self.arms.values():
            est = arm.vmodel.v_estimate()
            if est is None:
                continue
            dd = abs(arm.delay_us - delay_us) / 35.0
            w = 1.0 / (1.0 + dd * dd)
            if arm.seen_hit or arm.seen_warm:
                w *= 2.5
            elif arm.seen_crc:
                w *= 1.5
            num += w * est
            den += w
        return (num / den) if den > 0.0 else None

    def _find_nearby_cluster(self, delay_us: int, pw_us: int) -> _Cluster | None:
        for cl in self.clusters:
            for arm in cl.arms:
                if abs(arm.delay_us - delay_us) <= 14 and abs(arm.pw_us - pw_us) <= 12:
                    return cl
        return None

    def _has_close_arm(self, d: int, p: int) -> bool:
        if (d, p) in self.arms:
            return True
        for ad, ap in self.arms:
            if abs(ad - d) <= 1 and abs(ap - p) <= 2:
                return True
        return False

    def _create_arm(self, delay_us: int, pw_us: int, cluster: _Cluster,
                    prior_alpha: float, prior_beta: float,
                    scale: int = 0,
                    v_hint: float | None = None,
                    hint_sd: float = 8.0) -> _Arm | None:
        d = max(self.min_delay, min(self.max_delay, delay_us))
        p = max(self.min_pw, min(self.max_pw, pw_us))
        if self._has_close_arm(d, p):
            return None
        if len(cluster.arms) >= MAX_CLUSTER_ARMS:
            return None
        if v_hint is None:
            v_hint = self._v_hint(d)
        vm = _VModel(self.codes, self.min_mv, self.max_mv, self.rng,
                     v_hint=v_hint, hint_sd=hint_sd)
        arm = _Arm(d, p, vm, cluster, prior_alpha=prior_alpha,
                   prior_beta=prior_beta, scale=scale)
        cluster.arms.append(arm)
        self.arms[(d, p)] = arm
        return arm

    def _in_seed_phase(self) -> bool:
        if self.is_1d:
            return True
        s = self.seed_arm
        if s.shots < SEED_MIN_SHOTS:
            return True
        if s.shots >= SEED_MAX_SHOTS:
            return False
        if s.vmodel.shallow_edge_code() is not None:
            return True
        if (s.seen_under and s.seen_deep and s.vmodel.bracket_gap() <= 7.0
                and s.seen_crc == 0 and s.seen_warm == 0 and s.seen_hit == 0):
            return False
        return True

    def _pop_coarse_arm(self) -> _Arm | None:
        while True:
            while self.coarse_queue and self.coarse_queue[0] in self.arms:
                self.coarse_queue.pop(0)
            if not self.coarse_queue and self._coarse_round < 2:
                self._fill_coarse_queue()
                continue
            if not self.coarse_queue:
                return None
            d, p = self.coarse_queue.pop(0)
            cl = self._find_nearby_cluster(d, p)
            if cl is None:
                cl = _Cluster(d, p)
                self.clusters.append(cl)
            arm = self._create_arm(d, p, cl, prior_alpha=0.8, prior_beta=1.8)
            if arm is not None:
                return arm

    def next_shot(self) -> Shot:
        if self._in_seed_phase():
            arm = self.seed_arm
            return self._issue("seed_1d", arm)

        # Finish bracketing a newly opened coarse arm (typically 1-3 shots;
        # allows a 4th shot only when all 3 shots were on one side, e.g. a
        # large delay-dependent voltage shift).
        if self._bracketing is not None:
            b = self._bracketing
            bracketed = b.seen_under and b.seen_deep
            done = (b.seen_hit > 0 or b.seen_warm > 0 or b.seen_crc > 0
                    or (bracketed and b.vmodel.bracket_gap() <= 7.0)
                    or (bracketed and b.shots >= 3)
                    or b.shots >= 4)
            if not done:
                return self._issue("bracketing", b)
            self._bracketing = None

        while self.coarse_queue and self.coarse_queue[0] in self.arms:
            self.coarse_queue.pop(0)
        if not self.coarse_queue and self._coarse_round < 2:
            self._fill_coarse_queue()
            while self.coarse_queue and self.coarse_queue[0] in self.arms:
                self.coarse_queue.pop(0)
        has_coarse = bool(self.coarse_queue)

        # Level-1 Thompson selection: eligible clusters vs ONE coarse explore.
        r = self.rng
        best_cl: _Cluster | None = None
        best_score = -1.0
        for cl in self.clusters:
            if has_coarse and not cl.is_seed and cl.best_tier == 0:
                continue
            sc = cl.score(r, self.t)
            if sc > best_score:
                best_cl, best_score = cl, sc

        if has_coarse:
            explore_score = r.betavariate(1.0, 3.0) * r.betavariate(1.0, 1.0)
            if best_cl is None or explore_score > best_score:
                arm = self._pop_coarse_arm()
                if arm is not None:
                    self._bracketing = arm
                    return self._issue("coarse", arm)

        if best_cl is None:
            best_cl = self.seed_cluster

        # Level-2 selection inside best_cl:
        # - Once a cluster has a fresh `hit` arm, exploit hit arms directly
        #   rather than diluting across dozens of warm/crc_fail siblings.
        # - Before any `hit`, test untried refined neighbors closest to the
        #   warm centroid so warm/crc_fail gradients walk straight to center.
        if best_cl.best_tier == 3:
            hit_arms = [a for a in best_cl.arms if a.seen_hit > 0 and a.fails < 4.0]
            if hit_arms:
                best_arm = max(hit_arms, key=lambda a: a.score(r, self.t))
                return self._issue("hit_arm", best_arm)
        else:
            untried = [a for a in best_cl.arms if a.shots == 0]
            if untried:
                cen = best_cl.warm_centroid()
                if cen is not None:
                    cd, cp = cen
                    best_arm = min(
                        untried,
                        key=lambda a: ((a.delay_us - cd) / 10.0) ** 2
                        + ((a.pw_us - cp) / 10.0) ** 2,
                    )
                else:
                    best_arm = max(untried, key=lambda a: a.score(r, self.t))
                return self._issue("untried", best_arm)
        best_arm = max(best_cl.arms, key=lambda a: a.score(r, self.t))
        return self._issue("cluster_best", best_arm)

    def _issue(self, phase: str, arm: _Arm) -> Shot:
        """Emit a shot and remember why it was chosen (for run telemetry)."""
        self.last_decision = {
            "n": self.t + 1,
            "phase": phase,
            "arm": [arm.delay_us, arm.pw_us],
            "v_hint": arm.vmodel.v_estimate(),
        }
        return Shot(arm.vmodel.next_mv(), arm.delay_us, arm.pw_us)

    def stats(self) -> dict:
        """Cheap planner introspection for run telemetry; read-only."""
        return {
            "shots": self.t,
            "arms": len(self.arms),
            "clusters": len(self.clusters),
            "decision": self.last_decision,
        }

    def next_mv(self) -> int:
        """1D compatibility helper: return only v_dip_mv."""
        return self.next_shot().v_dip_mv

    def _spawn_neighbors(self, arm: _Arm, outcome: str, mv: int) -> None:
        if self.is_1d:
            return
        d, p = arm.delay_us, arm.pw_us
        cl = arm.cluster
        vh = float(mv)
        if outcome == "crc_fail":
            # CRC logic alive (e.g. 0x77): probe adjacent pw and delay slices.
            if arm.seen_crc == 1 and arm.scale == 0:
                for dp in (-22, 22):
                    self._create_arm(d, p + dp, cl, 0.85, 1.5, scale=1,
                                     v_hint=vh, hint_sd=6.0)
                for dd in (-15, 15):
                    self._create_arm(d + dd, p, cl, 0.85, 1.5, scale=1,
                                     v_hint=vh, hint_sd=6.0)
            elif arm.seen_crc == 1 and arm.scale == 1 and cl.best_tier == 1:
                for dp in (-22, 22):
                    self._create_arm(d, p + dp, cl, 0.85, 1.5, scale=1,
                                     v_hint=vh, hint_sd=6.0)
        elif outcome == "warm":
            # Intermediate CRC (e.g. 0x75 / 0x57): step toward center and zoom.
            if cl.warm_n >= 2:
                cd, cp = cl.warm_centroid()
                self._create_arm(round(cd), round(cp), cl, 1.3, 1.2, scale=2,
                                 v_hint=vh, hint_sd=5.0)
            if arm.seen_warm == 1 and arm.scale <= 1:
                for dd in (-10, 10):
                    self._create_arm(d + dd, p, cl, 1.0, 1.4, scale=1,
                                     v_hint=vh, hint_sd=5.0)
                for dp in (-10, 10):
                    self._create_arm(d, p + dp, cl, 1.0, 1.4, scale=1,
                                     v_hint=vh, hint_sd=5.0)
                for dd in (-4, 4):
                    self._create_arm(d + dd, p, cl, 1.1, 1.3, scale=2,
                                     v_hint=vh, hint_sd=5.0)
            elif arm.seen_warm == 1 and arm.scale == 2:
                for dd in (-4, 4):
                    self._create_arm(d + dd, p, cl, 1.1, 1.3, scale=2,
                                     v_hint=vh, hint_sd=5.0)
                for dp in (-6, 6):
                    self._create_arm(d, p + dp, cl, 0.95, 1.4, scale=2,
                                     v_hint=vh, hint_sd=5.0)

    def record(self, shot: Shot | int, outcome: str) -> None:
        """Record a non-Goldilocks outcome for a Shot (or v_dip int in 1D)."""
        self.t += 1
        if isinstance(shot, int):
            shot = Shot(shot, self.seed_delay, self.seed_pw)
        key = (shot.delay_us, shot.pw_us)
        arm = self.arms.get(key)
        if arm is None:
            cl = self._find_nearby_cluster(shot.delay_us, shot.pw_us)
            if cl is None:
                cl = _Cluster(shot.delay_us, shot.pw_us)
                self.clusters.append(cl)
            arm = self._create_arm(shot.delay_us, shot.pw_us, cl, 0.8, 1.8)
            if arm is None:
                arm = min(self.arms.values(),
                          key=lambda a: (a.delay_us - shot.delay_us) ** 2
                          + (a.pw_us - shot.pw_us) ** 2)
        arm.record(shot.v_dip_mv, outcome, self.t)
        arm.cluster.record(outcome, self.t)
        if outcome == "warm":
            arm.cluster.warm_d_sum += shot.delay_us
            arm.cluster.warm_p_sum += shot.pw_us
            arm.cluster.warm_n += 1

        if outcome in ("crc_fail", "warm"):
            self._spawn_neighbors(arm, outcome, shot.v_dip_mv)
