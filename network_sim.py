"""
Phase 3 network layer: a simulated P2P sampling round on top of the coding
schemes benchmarked in benchmark_1D_2D_BC.py.

    pip install simpy galois numpy

WHY THIS EXISTS
---------------
benchmark_1D_2D_BC.py measures each coding scheme in isolation: one blob,
one process, an erasure mask drawn i.i.d. from a nominal rate. That answers
"what can this code survive", but the report's Phase 3 asks for something
the coding benchmark structurally cannot give -- the schemes "deployed
within a controlled simulated peer-to-peer (P2P) network environment",
measured for "bandwidth saturation, packet propagation latency, and block
processing throughput".

Those three quantities do not exist until there is a network. A decode time
of 40s is a fact about arithmetic; whether it fits inside a 12-second
Ethereum slot is a fact about a system. This file supplies the system.

THE ONE IDEA THIS FILE IS BUILT ON
----------------------------------
In the coding benchmark, the erasure mask is an INPUT -- `random_mask(rate,
rng)` invents it. Here the mask is an OUTPUT: it is whatever a node failed
to collect before its deadline, given how many peers it could reach, how
fast their links were, and which of them refused to answer. Everything
downstream of the mask -- decode, extract, byte-level verification -- is
the SAME adapter code the benchmark already uses, unchanged. The network
layer replaces exactly one function and nothing else:

    benchmark:   mask = adapter.random_mask(rate, rng)      # invented
    here:        mask = <what did not arrive in time>       # emergent

That is the whole integration surface, and it is why this file does not
reimplement any coding logic.

WHY THAT MATTERS BEYOND JUST ADDING NETWORK METRICS
---------------------------------------------------
The coding benchmark draws erasures independently per symbol. Real sampling
failures are not independent: when a peer goes offline, *everything it was
custodying* disappears at once. That produces CLUSTERED erasures, and the
benchmark's own report flags i.i.d.-only testing as a gap -- an adversary
who understands the code and withholds correlated samples is a different,
more dangerous threat model than one dropping symbols at random. A
peer-failure model produces exactly those correlated patterns for free,
because the correlation comes from the topology rather than from being
injected by hand.

HOW SIMPY WORKS, IN THE THREE CONCEPTS THIS FILE USES
------------------------------------------------------
SimPy is a discrete-event simulator. Nothing here runs in real time.

  1. `env = simpy.Environment()` is a clock plus a queue of future events.
     `env.now` is the current SIMULATED time in seconds.

  2. A "process" is an ordinary Python generator. `yield env.timeout(0.08)`
     means "resume me 80 simulated milliseconds from now". The scheduler
     jumps straight to the next scheduled event, so simulating a 12-second
     slot across 64 peers costs microseconds of real CPU -- there is no
     actual waiting, only bookkeeping.

  3. `simpy.Resource` models something contended. The node's downlink is a
     capacity-1 resource here: a transfer must acquire it, holds it for
     bytes/bandwidth seconds, then releases it. That is what makes
     bandwidth saturation emerge rather than being assumed -- if the node
     asks for more data than the link can carry before the deadline, the
     queue backs up and the late arrivals become erasures on their own.

THE ONE THING SIMULATED TIME DOES NOT MAKE FREE
------------------------------------------------
`yield env.timeout(40)` costs nothing. Actually calling a decoder that
takes 40 real seconds still takes 40 real seconds. So decode is handled two
ways, chosen by `--real-decode`:

  * calibrated (default): decode time is interpolated from the measured
    curve already in benchmark_results.json, and success is decided by the
    decoder's own budget rule. Fast enough to sweep hundreds of rounds.
  * real: the emergent mask is handed to the actual adapter and decoded for
    real. Slow (1D-RS runs to ~80s per call) but it is ground truth, and it
    is the only way to find out how the schemes behave under CLUSTERED
    erasures, which the calibrated curve was not measured on.

The intended workflow is to explore with the calibrated model and confirm
the interesting points with `--real-decode`.

A CAVEAT THAT MUST TRAVEL WITH EVERY ABSOLUTE NUMBER
-----------------------------------------------------
Decode times come from this project's Python/`galois` implementation, whose
field arithmetic runs in object mode at roughly 0.5-1.3 microseconds per
operation. A production implementation in Rust or C with optimised BLS12-381
arithmetic is typically two to three orders of magnitude faster. So
"1D-RS cannot decode a blob inside a 12-second slot" is a true statement
about THIS implementation and a false one about Ethereum. `--speedup N`
divides all decode times by N so the question "what would this look like at
production arithmetic speed" can be asked explicitly rather than smuggled
in. Comparisons BETWEEN schemes are unaffected by the factor, which is why
they are the numbers worth quoting.
"""

import argparse
import json
import math
import os
import random
import statistics
from dataclasses import dataclass, field

import numpy as np
import simpy

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# PeerDAS-shaped constants. A "sample" here is one cell: the unit a node
# actually requests from a peer, not one field element.
# ---------------------------------------------------------------------------
SYMBOLS_PER_CELL = 64          # consensus-specs FIELD_ELEMENTS_PER_CELL
BYTES_PER_SYMBOL = 32          # a BLS12-381 scalar on the wire
KZG_PROOF_BYTES = 48           # one compressed G1 point accompanies each cell
CELL_BYTES = SYMBOLS_PER_CELL * BYTES_PER_SYMBOL + KZG_PROOF_BYTES   # 2096

SLOT_SECONDS = 12.0            # an Ethereum slot


# ---------------------------------------------------------------------------
# CALIBRATED DECODE-COST MODEL
# ---------------------------------------------------------------------------
class DecodeModel:
    """Decode cost and recoverability, read off the measured sweep rather
    than re-derived. Loading benchmark_results.json means this file never
    has to guess what a decode costs -- the answer was already measured, at
    55 erasure rates, over 1,800 trials."""

    def __init__(self, path=None, speedup=1.0):
        path = path or os.path.join(HERE, "benchmark_results.json")
        with open(path) as f:
            data = json.load(f)
        self.speedup = speedup
        self.schemes = {}
        for r in data["results"]:
            pts = [(t["rate"], t["mean_decode_time_success_only_s"])
                   for t in r["trials"] if t["mean_decode_time_success_only_s"]]
            succ = [(t["rate"], t["successes"] / t["trials"]) for t in r["trials"]]
            last_full = max((rt for rt, s in succ if s == 1.0), default=0.0)
            first_zero = min((rt for rt, s in succ if s == 0.0 and rt > last_full),
                             default=1.0)
            self.schemes[r["scheme"]] = {
                "n": r["n"], "k": r["k"], "rate": r["rate"],
                "overhead": r["overhead"],
                "encode_s": r["encode_time_s"],
                "cost_points": sorted(pts),
                "last_full": last_full,      # highest swept rate where every trial recovered
                "first_zero": first_zero,    # lowest rate above that where none did
            }

    def names(self):
        return list(self.schemes)

    def decode_seconds(self, scheme, erasure_fraction):
        """Linear interpolation across the measured decode-time curve, held
        flat outside its range. Divided by the speedup factor."""
        pts = self.schemes[scheme]["cost_points"]
        if not pts:
            return 0.0
        if erasure_fraction <= 0.0:
            # Nothing was lost, so there is nothing to recover and every
            # decoder returns immediately. Without this the curve would be
            # held flat at its lowest MEASURED rate (0.02) and invent several
            # seconds of work for a round that did none -- confirmed against
            # --real-decode, which reports 0.00s here.
            return 0.0
        if erasure_fraction <= pts[0][0]:
            t = pts[0][1]
        elif erasure_fraction >= pts[-1][0]:
            t = pts[-1][1]
        else:
            t = pts[-1][1]
            for (r0, t0), (r1, t1) in zip(pts, pts[1:]):
                if r0 <= erasure_fraction <= r1:
                    w = 0.0 if r1 == r0 else (erasure_fraction - r0) / (r1 - r0)
                    t = t0 + w * (t1 - t0)
                    break
        return t / self.speedup

    def recovers(self, scheme, erasure_fraction, rng):
        """Below the measured transition it always recovered, above it never
        did, and inside the band it is a coin weighted by how far across the
        band the draw sits. NOTE: calibrated on i.i.d. erasures. The masks
        this simulation produces are clustered, so inside the band this is an
        approximation -- which is precisely what --real-decode exists to
        check."""
        s = self.schemes[scheme]
        if erasure_fraction <= s["last_full"]:
            return True
        if erasure_fraction >= s["first_zero"]:
            return False
        span = s["first_zero"] - s["last_full"]
        p_fail = (erasure_fraction - s["last_full"]) / span if span else 1.0
        return rng.random() > p_fail


# ---------------------------------------------------------------------------
# NETWORK CONFIGURATION
# ---------------------------------------------------------------------------
@dataclass
class NetConfig:
    n_peers: int = 64
    # How many distinct peers custody each cell. This is the network's own
    # redundancy, separate from the code's: with replication 1 a single
    # offline peer is an unavoidable erasure, with 4 the node has three
    # fallbacks before it loses anything.
    custody_replication: int = 4
    adversarial_fraction: float = 0.0   # peers that simply never answer
    deadline_s: float = 4.0             # sampling window inside the slot
    downlink_mbps: float = 50.0         # the reconstructing node's own link
    latency_median_s: float = 0.08      # one-way, lognormal
    latency_sigma: float = 0.6          # lognormal shape; heavier tail = worse
    request_timeout_s: float = 0.4      # when to give up and try another peer
    # A reconstructing node needs k symbols, not all n -- it should stop
    # pulling once it has enough. Fetching all n would roughly double the
    # reported bandwidth and describe a custodian archiving the whole
    # codeword, not a node rebuilding a blob. The margin is the slack it
    # asks for beyond the bare minimum so that a few failures do not force
    # a second round trip.
    over_request: float = 0.15
    max_in_flight: int = 64             # bounded concurrent requests
    # Blobs the node must reconstruct within the same slot. Ethereum carries
    # several per block, and they share one downlink -- which is where
    # bandwidth stops being free.
    blobs_per_slot: int = 1
    seed: int = 12345


@dataclass
class RoundResult:
    scheme: str
    cells_total: int
    cells_received: int
    erasure_fraction: float
    bytes_fetched: int
    gather_seconds: float       # simulated, network only
    decode_seconds: float       # simulated, arithmetic only
    total_seconds: float
    recovered: bool
    peers_tried: int
    timeouts: int


# ---------------------------------------------------------------------------
# THE SIMULATION ITSELF
# ---------------------------------------------------------------------------
def _build_peers(cfg, n_cells, rng):
    """Assign each cell to `custody_replication` distinct peers, and mark a
    fraction of peers adversarial. Returns (custodians, adversarial set,
    latency per peer)."""
    adversarial = set()
    n_bad = int(round(cfg.adversarial_fraction * cfg.n_peers))
    if n_bad:
        adversarial = set(rng.sample(range(cfg.n_peers), n_bad))
    latency = {p: rng.lognormvariate(math.log(cfg.latency_median_s),
                                     cfg.latency_sigma)
               for p in range(cfg.n_peers)}
    custodians = {}
    for c in range(n_cells):
        k = min(cfg.custody_replication, cfg.n_peers)
        custodians[c] = rng.sample(range(cfg.n_peers), k)
    return custodians, adversarial, latency


def simulate_gather(cfg, n_cells, rng, cells_needed):
    """One sampling round across `cfg.blobs_per_slot` blobs sharing one
    downlink. Returns (received cells of blob 0, bytes fetched over all
    blobs, gather seconds, peers tried, timeouts).

    This is the part that is genuinely a SimPy simulation. Three things are
    modelled rather than assumed:

      * a bounded number of requests are in flight at once (`max_in_flight`
        worker processes pulling from a shared queue), which is how a real
        client behaves and what lets the link queue build up;
      * every transfer contends for ONE capacity-1 downlink resource, so
        bandwidth saturation emerges from demand rather than being stated;
      * the node stops once it holds enough cells to rebuild, instead of
        draining the whole codeword.

    All blobs in a slot are statistically identical, so blob 0's mask is
    taken as representative for decoding, while bandwidth and timing are
    aggregated across all of them -- multiple blobs change contention and
    elapsed time, which is exactly what they are here to test."""
    env = simpy.Environment()
    link = simpy.Resource(env, capacity=1)
    bytes_per_second = cfg.downlink_mbps * 1e6 / 8.0
    transfer_s = CELL_BYTES / bytes_per_second

    custodians, adversarial, latency = _build_peers(cfg, n_cells, rng)
    # ask for a little more than the bare minimum so a few losses do not
    # force another round trip, but never more than the codeword holds
    target = min(n_cells, math.ceil(cells_needed * (1.0 + cfg.over_request)))

    received = {b: set() for b in range(cfg.blobs_per_slot)}
    stats = {"bytes": 0, "tried": 0, "timeouts": 0, "t_done": None}
    queues = {b: [c for c in range(n_cells)] for b in range(cfg.blobs_per_slot)}
    for b in queues:
        rng.shuffle(queues[b])
    cursor = {b: 0 for b in range(cfg.blobs_per_slot)}

    def all_done():
        return all(len(received[b]) >= target for b in received)

    def fetch_one(blob, cell):
        """Try custodians in turn until one answers. An adversarial peer is
        modelled as never answering, so the client burns its timeout before
        falling back -- withholding costs the victim time, not only data."""
        for peer in custodians[cell]:
            if env.now >= cfg.deadline_s:
                return
            stats["tried"] += 1
            if peer in adversarial:
                yield env.timeout(min(cfg.request_timeout_s,
                                      max(0.0, cfg.deadline_s - env.now)))
                stats["timeouts"] += 1
                continue
            yield env.timeout(latency[peer])            # request in flight
            if env.now >= cfg.deadline_s:
                return
            with link.request() as req:                 # queue for the link
                yield req
                if env.now >= cfg.deadline_s:
                    return
                yield env.timeout(transfer_s)           # payload on the wire
            if env.now <= cfg.deadline_s:
                received[blob].add(cell)
                stats["bytes"] += CELL_BYTES
                if stats["t_done"] is None and all_done():
                    stats["t_done"] = env.now
            return

    def worker(blob):
        while env.now < cfg.deadline_s:
            if len(received[blob]) >= target or cursor[blob] >= n_cells:
                return
            cell = queues[blob][cursor[blob]]
            cursor[blob] += 1
            yield env.process(fetch_one(blob, cell))

    for b in range(cfg.blobs_per_slot):
        for _ in range(max(1, cfg.max_in_flight // cfg.blobs_per_slot)):
            env.process(worker(b))
    env.run(until=cfg.deadline_s)

    gather_s = stats["t_done"] if stats["t_done"] is not None else cfg.deadline_s
    return received[0], stats["bytes"], gather_s, stats["tried"], stats["timeouts"]


def run_round(scheme, model, cfg, rng, adapter=None, encoded=None, blob=None,
              app_bytes=None):
    """One end-to-end reconstruction: gather over the network, turn what is
    missing into an erasure mask, then decode.

    If `adapter` is given the REAL decoder runs on the REAL emergent mask
    (ground truth, slow). Otherwise the calibrated model is consulted."""
    spec = model.schemes[scheme]
    n = spec["n"]
    n_cells = math.ceil(n / SYMBOLS_PER_CELL)
    # How much must this node actually pull down? NOT k -- that is the floor
    # only for an MDS code decoded optimally. A node must fetch enough that
    # what is MISSING lands inside its own decoder's measured tolerance, so a
    # weaker decoder forces a bigger download at the same storage cost. Using
    # the conservative end of the measured transition (`last_full`, the
    # highest rate that recovered every time):
    #
    #     symbols needed = n * (1 - tolerance)
    #
    #     1D-RS  tol 0.49 -> 4178 of 8192   (2% over the MDS floor of 4096:
    #                                        the rule is the same for every
    #                                        scheme, not tailored to MDS)
    #     2D-RS  tol 0.38 -> 5238 of 8448
    #     BC L2  tol 0.33 -> 5489 of 8192
    #
    # This is the same quantity as the benchmark report's "surviving data
    # needed" figure, now driving a download rather than sitting in a table.
    tol = spec["last_full"]
    cells_needed = math.ceil(n * (1.0 - tol) / SYMBOLS_PER_CELL)

    received, nbytes, gather_s, tried, timeouts = simulate_gather(
        cfg, n_cells, rng, cells_needed=cells_needed)
    missing_cells = [c for c in range(n_cells) if c not in received]

    # cells -> symbol-level mask, which is what the coding adapters consume
    mask_flat = np.zeros(n, dtype=bool)
    for c in missing_cells:
        lo = c * SYMBOLS_PER_CELL
        mask_flat[lo:min(lo + SYMBOLS_PER_CELL, n)] = True
    erasure_fraction = float(mask_flat.mean())

    if adapter is not None:
        mask = mask_flat
        if getattr(adapter, "name", "") == "2D-RS":
            mask = mask_flat.reshape(adapter_grid_shape(adapter))
        corrupted = adapter.corrupt(encoded, mask)
        recovered_cw, ok, real_decode_s = adapter.decode(corrupted, mask)
        recovered = bool(ok) and _bytes_match(adapter, recovered_cw, blob, app_bytes)
        decode_s = real_decode_s / model.speedup
    else:
        recovered = model.recovers(scheme, erasure_fraction, rng)
        decode_s = model.decode_seconds(scheme, erasure_fraction) if recovered else 0.0

    # A node reconstructing several blobs in a slot pays decode for each of
    # them. Serial is the conservative single-core reading; a threaded client
    # would divide this by its core count.
    decode_s *= cfg.blobs_per_slot

    return RoundResult(
        scheme=scheme, cells_total=n_cells, cells_received=len(received),
        erasure_fraction=erasure_fraction, bytes_fetched=nbytes,
        gather_seconds=gather_s, decode_seconds=decode_s,
        total_seconds=gather_s + decode_s, recovered=recovered,
        peers_tried=tried, timeouts=timeouts)


def adapter_grid_shape(adapter):
    import importlib.util
    spec = importlib.util.spec_from_file_location("rs2d", os.path.join(HERE, "2D_RS_Galois.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return (m.EXT_ROWS, m.EXT_COLS)


def _bytes_match(adapter, recovered_cw, blob, app_bytes):
    import blob_generator as bg
    try:
        out = adapter.extract_message(recovered_cw)
    except Exception:
        return False
    if list(out) != list(blob):
        return False
    try:
        bg.validate_blob(out)
        return bg.blob_to_bytes(out) == app_bytes
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# SWEEP
# ---------------------------------------------------------------------------
def sweep(model, schemes, adversarial_rates, peer_counts, trials, cfg_base,
          real=False):
    """Cross product of scheme x peer count x adversarial fraction.

    Peer count matters for more than scale. Custody replication is fixed, so
    with FEWER peers each one holds a larger share of the codeword -- and a
    single withholding peer then takes out a correspondingly larger, more
    CLUSTERED chunk of it. Sweeping this is what turns 'scalability' from a
    word into a measurement."""
    rows = []
    adapters = {}
    encoded = {}
    blob = app_bytes = None
    if real:
        adapters, encoded, blob, app_bytes = _prepare_real_adapters(schemes)

    for scheme in schemes:
      for peers in peer_counts:
        for adv in adversarial_rates:
            cfg = _with(cfg_base, adversarial_fraction=adv, n_peers=peers)
            per = []
            for t in range(trials):
                rng = random.Random(cfg.seed + 1000 * t + int(adv * 997))
                per.append(run_round(
                    scheme, model, cfg, rng,
                    adapter=adapters.get(scheme), encoded=encoded.get(scheme),
                    blob=blob, app_bytes=app_bytes))
            ok = [r for r in per if r.recovered]
            rows.append({
                "scheme": scheme, "adversarial": adv, "peers": peers,
                "trials": trials,
                "recovered": len(ok),
                "mean_erasure_fraction": statistics.fmean(r.erasure_fraction for r in per),
                "mean_kib_fetched": statistics.fmean(r.bytes_fetched for r in per) / 1024,
                "mean_gather_s": statistics.fmean(r.gather_seconds for r in per),
                "mean_decode_s": statistics.fmean(r.decode_seconds for r in ok) if ok else None,
                "mean_total_s": statistics.fmean(r.total_seconds for r in ok) if ok else None,
                "mean_timeouts": statistics.fmean(r.timeouts for r in per),
                # blobs actually reconstructed per slot: how many the node got
                # through, scaled by the share of the work that fits in the slot
                # (min(1, slot / total)) and by the recovery rate.
                # This is the report's "block processing throughput".
                "blobs_per_slot": (
                    (cfg_base.blobs_per_slot * min(1.0, SLOT_SECONDS / statistics.fmean(
                        r.total_seconds for r in ok)) * (len(ok) / trials))
                    if ok else 0.0),
            })
    return rows


def _with(cfg, **kw):
    from dataclasses import replace
    return replace(cfg, **kw)


def _prepare_real_adapters(schemes):
    """Load the benchmark's own adapters and encode the shared blob once."""
    import importlib.util
    import blob_generator as bg
    spec = importlib.util.spec_from_file_location("bench",
                                                  os.path.join(HERE, "benchmark_1D_2D_BC.py"))
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    app_bytes = os.urandom(bg.USABLE_BYTES_PER_BLOB)
    blob = bg.bytes_to_blobs(app_bytes)[0]
    made, enc = {}, {}
    for s in schemes:
        if s == "1D-RS":
            a = b.OneDAdapter()
        elif s == "2D-RS":
            a = b.TwoDAdapter()
        else:
            w, rho, lam = next((w, r, l) for (w, r, l) in b.BC_VARIANTS
                               if f"BC-{w}-L{l}" == s)
            a = b.BCAdapter(w, rho, lam, pair_unknown_cap=b.BC_PAIR_UNKNOWN_CAP)
        made[s] = a
        enc[s] = a.encode(blob)
    return made, enc, blob, app_bytes



# ---------------------------------------------------------------------------
# VISUALISATION
# ---------------------------------------------------------------------------
BLOCKS = "▏▎▍▌▋▊▉█"


def bar(value, vmax, width=22):
    """A unicode bar, resolved to an eighth of a cell so small values stay
    visible rather than rounding away to nothing."""
    if vmax <= 0 or value <= 0:
        return ""
    eighths = int(round((value / vmax) * width * 8))
    full, rem = divmod(max(eighths, 1), 8)
    return "█" * full + (BLOCKS[rem - 1] if rem else "")


def stacked_bar(parts, vmax, width=40, glyphs="░█"):
    """Proportional stacked bar; used for gather-vs-decode, where the whole
    point is that one segment dwarfs the other."""
    out = ""
    for value, g in zip(parts, glyphs):
        n = int(round((value / vmax) * width)) if vmax > 0 else 0
        # a segment that exists but rounds to zero still gets one cell, so
        # "too small to see" stays distinguishable from "not there"
        if value > 0:
            n = max(n, 1)
        out += g * n
    return out


def print_visuals(rows, cfg, schemes):
    """Three terminal views of the same rows: throughput, where the time
    goes, and how recovery falls away as peers withhold."""
    ok_rows = [r for r in rows if r["mean_total_s"] is not None]

    print("\n" + "=" * 78)
    print(" THROUGHPUT  -- blobs reconstructed per slot "
          f"(target {cfg.blobs_per_slot})")
    print("=" * 78)
    vmax = max([r["blobs_per_slot"] for r in rows] + [0.001])
    for r in rows:
        label = f"{r['scheme']:<12} p={r['peers']:<4} adv={r['adversarial']:.0%}"
        print(f"  {label:<30} {bar(r['blobs_per_slot'], vmax):<24} "
              f"{r['blobs_per_slot']:.2f}")

    if ok_rows:
        print("\n" + "=" * 78)
        print(" WHERE THE TIME GOES   ░ gather (network)   █ decode (arithmetic)")
        print("=" * 78)
        tmax = max(r["mean_total_s"] for r in ok_rows)
        for r in ok_rows:
            label = f"{r['scheme']:<12} p={r['peers']:<4} adv={r['adversarial']:.0%}"
            seg = stacked_bar([r["mean_gather_s"], r["mean_decode_s"]], tmax)
            slot = "  <- over slot" if r["mean_total_s"] > SLOT_SECONDS else ""
            print(f"  {label:<30} {seg:<42} {r['mean_total_s']:7.2f}s{slot}")
        # where the slot budget falls on this scale
        if SLOT_SECONDS < tmax:
            col = int(round((SLOT_SECONDS / tmax) * 40))
            print("  " + " " * 30 + " " * col + "^")
            print("  " + " " * 30 + " " * max(0, col - 3)
                  + f"{SLOT_SECONDS:.0f}s slot")
        else:
            print(f"\n  full width = {tmax:.1f}s -- every configuration above "
                  f"fits inside the {SLOT_SECONDS:.0f}s slot")

    print("\n" + "=" * 78)
    print(" RECOVERY vs WITHHOLDING PEERS   (● all trials  ◐ some  ○ none)")
    print("=" * 78)
    advs = sorted({r["adversarial"] for r in rows})
    peers = sorted({r["peers"] for r in rows})
    head = "  " + " " * 20 + "".join(f"{a:>7.0%}" for a in advs)
    print(head)
    for sc in schemes:
        for pc in peers:
            cells = ""
            for a in advs:
                m = next((r for r in rows if r["scheme"] == sc
                          and r["peers"] == pc and r["adversarial"] == a), None)
                if m is None:
                    cells += "      ."
                else:
                    frac = m["recovered"] / m["trials"]
                    cells += f"{'●' if frac == 1 else ('◐' if frac > 0 else '○'):>7}"
            print(f"  {sc:<13} p={pc:<5}{cells}")


def write_figures(rows, cfg, path):
    """Emit the same three views as inline SVG in a markdown file, styled to
    match the other documents in docs/ so they can be pasted straight in."""
    schemes = sorted({r["scheme"] for r in rows})
    palette = ["#c62828", "#1546a0", "#14532d", "#b45309", "#7c2d92", "#1b7a34"]
    color = {s: palette[i % len(palette)] for i, s in enumerate(schemes)}
    advs = sorted({r["adversarial"] for r in rows})
    peers = sorted({r["peers"] for r in rows})
    out = ["# Network simulation figures\n",
           f"Generated by `network_sim.py`. {cfg.blobs_per_slot} blob(s) per slot, "
           f"{cfg.downlink_mbps:g} Mbps downlink, {cfg.deadline_s:g}s window in a "
           f"{SLOT_SECONDS:g}s slot, custody replication {cfg.custody_replication}.\n"]

    def axes(w, h, xl, xr, yt, yb, ylab, ymax, xticks, xlabel):
        p = [f'<line x1="{xl}" y1="{yt}" x2="{xl}" y2="{yb}" stroke="currentColor" stroke-width="0.8"/>',
             f'<line x1="{xl}" y1="{yb}" x2="{xr}" y2="{yb}" stroke="currentColor" stroke-width="0.8"/>']
        for i in range(6):
            v = ymax * i / 5
            y = yb - (v / ymax) * (yb - yt) if ymax else yb
            p.append(f'<line x1="{xl-3}" y1="{y:.1f}" x2="{xl}" y2="{y:.1f}" stroke="currentColor" stroke-width="0.7"/>')
            p.append(f'<line x1="{xl}" y1="{y:.1f}" x2="{xr}" y2="{y:.1f}" stroke="currentColor" stroke-width="0.35" opacity="0.15"/>')
            p.append(f'<text x="{xl-6}" y="{y+2.5:.1f}" text-anchor="end" font-size="7">{v:.2f}</text>')
        for xv, lab in xticks:
            p.append(f'<line x1="{xv:.1f}" y1="{yb}" x2="{xv:.1f}" y2="{yb+3}" stroke="currentColor" stroke-width="0.7"/>')
            p.append(f'<text x="{xv:.1f}" y="{yb+12}" text-anchor="middle" font-size="7">{lab}</text>')
        p.append(f'<text x="{(xl+xr)/2:.0f}" y="{h-6}" text-anchor="middle" font-size="7.4">{xlabel}</text>')
        p.append(f'<text x="10" y="{(yt+yb)/2:.0f}" text-anchor="middle" font-size="7.4" '
                 f'transform="rotate(-90 10 {(yt+yb)/2:.0f})">{ylab}</text>')
        return p

    # --- figure 1: throughput vs adversarial fraction, one line per scheme
    W, H, xl, xr, yt, yb = 430, 250, 52, 320, 22, 200
    ymax = max([r["blobs_per_slot"] for r in rows] + [0.01])
    xs = {a: xl + (i / max(1, len(advs) - 1)) * (xr - xl) for i, a in enumerate(advs)}
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Blobs reconstructed '
         f'per slot against the fraction of withholding peers, one line per scheme.">']
    p += axes(W, H, xl, xr, yt, yb, "blobs / slot", ymax,
              [(xs[a], f"{a:.0%}") for a in advs], "withholding peers")
    for sc in schemes:
        for pc in peers:
            pts = [(xs[a], r["blobs_per_slot"]) for a in advs
                   for r in rows if r["scheme"] == sc and r["adversarial"] == a
                   and r["peers"] == pc]
            if not pts:
                continue
            d = " ".join(f"{x:.1f},{yb - (v/ymax)*(yb-yt):.1f}" for x, v in pts)
            dash = "" if len(peers) == 1 else f' stroke-dasharray="{2+peers.index(pc)*2},2"'
            p.append(f'<polyline points="{d}" fill="none" stroke="{color[sc]}" stroke-width="1.4"{dash}/>')
            for x, v in pts:
                p.append(f'<circle cx="{x:.1f}" cy="{yb-(v/ymax)*(yb-yt):.1f}" r="2" fill="{color[sc]}"/>')
    for i, sc in enumerate(schemes):
        p.append(f'<text x="{xr+6}" y="{30+i*11}" font-size="7" fill="{color[sc]}" font-weight="700">{sc}</text>')
    p.append("</svg>")
    out.append("<figure>\n" + "\n".join(p) +
               "\n<figcaption>Throughput against adversarial pressure. Flat lines are "
               "schemes whose decode fits the slot comfortably; a line that falls is one "
               "whose decode cost is growing faster than the slot allows."
               + (" Dash pattern distinguishes peer counts." if len(peers) > 1 else "")
               + "</figcaption>\n</figure>\n")

    # --- figure 2: gather vs decode, stacked, log-ish via sqrt for readability
    W, H = 430, 72 + 18 * len(rows)   # extra foot room for the slot label
    xl2, xr2 = 150, 400
    tmax = max([r["mean_total_s"] or 0 for r in rows] + [0.01])
    p = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Gather time versus '
         f'decode time per configuration, showing decode dominating.">']
    p.append(f'<text x="{xl2}" y="14" font-size="7.5" font-weight="700">gather (network)</text>')
    p.append(f'<rect x="{xl2-12}" y="8" width="9" height="7" fill="#9bb0c9"/>')
    p.append(f'<text x="{xl2+96}" y="14" font-size="7.5" font-weight="700">decode (arithmetic)</text>')
    p.append(f'<rect x="{xl2+84}" y="8" width="9" height="7" fill="#c62828"/>')
    slot_x = xl2 + (SLOT_SECONDS / tmax) * (xr2 - xl2)
    if SLOT_SECONDS < tmax:
        p.append(f'<line x1="{slot_x:.1f}" y1="22" x2="{slot_x:.1f}" y2="{H-14}" '
                 f'stroke="#c62828" stroke-width="1" stroke-dasharray="3,2"/>')
        # label at the foot of the line, clear of the first bar
        p.append(f'<text x="{slot_x+3:.1f}" y="{H-6}" font-size="6.6" '
                 f'fill="#c62828">{SLOT_SECONDS:g}s slot</text>')
    y = 30
    for r in rows:
        lab = f"{r['scheme']} p={r['peers']} adv={r['adversarial']:.0%}"
        p.append(f'<text x="{xl2-16}" y="{y+6}" text-anchor="end" font-size="6.8">{lab}</text>')
        if r["mean_total_s"] is not None:
            gw = (r["mean_gather_s"] / tmax) * (xr2 - xl2)
            dw = (r["mean_decode_s"] / tmax) * (xr2 - xl2)
            p.append(f'<rect x="{xl2}" y="{y}" width="{max(gw,0.6):.1f}" height="9" fill="#9bb0c9"/>')
            p.append(f'<rect x="{xl2+gw:.1f}" y="{y}" width="{max(dw,0.6):.1f}" height="9" fill="#c62828" opacity="0.85"/>')
            p.append(f'<text x="{xl2+gw+dw+4:.1f}" y="{y+7}" font-size="6.4">{r["mean_total_s"]:.1f}s</text>')
        else:
            p.append(f'<text x="{xl2+2}" y="{y+7}" font-size="6.4" fill="#8d99a6">no recovery</text>')
        y += 18
    p.append("</svg>")
    out.append("<figure>\n" + "\n".join(p) +
               "\n<figcaption>Where the time goes. The network segment is barely "
               "visible against the arithmetic segment at almost every setting, which is "
               "the central finding of the network layer: decode cost, not bandwidth or "
               "latency, is what decides whether a scheme fits a slot.</figcaption>\n</figure>\n")

    with open(path, "w") as f:
        f.write("\n".join(out))
    return path

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--schemes", default="1D-RS,2D-RS,BC-1024-L2")
    ap.add_argument("--adversarial", default="0.0,0.1,0.2,0.3,0.4,0.5")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--speedup", type=float, default=1.0,
                    help="divide decode times by this; use ~100-1000 to model "
                         "production field arithmetic instead of Python/galois")
    ap.add_argument("--real-decode", action="store_true",
                    help="decode the emergent mask with the real adapters "
                         "(ground truth, slow) instead of the calibrated curve")
    ap.add_argument("--deadline", type=float, default=4.0)
    ap.add_argument("--downlink", type=float, default=50.0, help="Mbps")
    ap.add_argument("--replication", type=int, default=4)
    ap.add_argument("--peers", default="64",
                    help="peer count; comma-separated to sweep it, e.g. 16,32,64,128. "
                         "Custody replication is fixed, so fewer peers means each holds "
                         "more of the codeword and one withholding peer removes a "
                         "larger, more clustered chunk of it")
    ap.add_argument("--blobs", type=int, default=1,
                    help="blobs the node must reconstruct in the slot; they "
                         "share one downlink, which is where bandwidth bites")
    ap.add_argument("--json", default=None, help="write rows to this path")
    ap.add_argument("--figures", default=None,
                    help="write SVG figures to this markdown path, styled to match docs/")
    ap.add_argument("--no-visuals", action="store_true",
                    help="suppress the terminal charts, leaving just the table")
    args = ap.parse_args()

    model = DecodeModel(speedup=args.speedup)
    schemes = [s.strip() for s in args.schemes.split(",")]
    unknown = [s for s in schemes if s not in model.schemes]
    if unknown:
        raise SystemExit(f"unknown scheme(s) {unknown}; have {model.names()}")
    advs = [float(x) for x in args.adversarial.split(",")]
    peer_counts = [int(x) for x in str(args.peers).split(",")]
    cfg = NetConfig(n_peers=peer_counts[0], custody_replication=args.replication,
                    deadline_s=args.deadline, downlink_mbps=args.downlink,
                    blobs_per_slot=args.blobs)

    print("=" * 78)
    print(" P2P SAMPLING SIMULATION  (SimPy discrete-event, coding via the "
          "real adapters)")
    print("=" * 78)
    print(f"peers={','.join(map(str, peer_counts))}  "
          f"custody replication={cfg.custody_replication}  "
          f"deadline={cfg.deadline_s}s of a {SLOT_SECONDS}s slot")
    print(f"downlink={cfg.downlink_mbps} Mbps  cell={CELL_BYTES} B "
          f"({SYMBOLS_PER_CELL} symbols + {KZG_PROOF_BYTES} B proof)  "
          f"timeout={cfg.request_timeout_s}s")
    print(f"decode: {'REAL decoders on the emergent mask' if args.real_decode else 'calibrated from benchmark_results.json'}"
          f"   speedup x{args.speedup:g}")
    print(f"blobs to reconstruct per slot: {cfg.blobs_per_slot}  "
          f"(node stops at k+{cfg.over_request:.0%} cells, "
          f"{cfg.max_in_flight} requests in flight)")
    print(f"{args.trials} trials per point\n")

    rows = sweep(model, schemes, advs, peer_counts, args.trials, cfg,
                 real=args.real_decode)

    hdr = (f"{'scheme':<12} {'peers':>6} {'adv':>5} {'recovered':>10} {'erasure':>8} "
           f"{'KiB':>7} {'gather':>8} {'decode':>9} {'total':>9} {'blobs/slot':>11}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        dec = f"{r['mean_decode_s']:.2f}s" if r["mean_decode_s"] is not None else "--"
        tot = f"{r['mean_total_s']:.2f}s" if r["mean_total_s"] is not None else "--"
        thr = f"{r['blobs_per_slot']:.2f}"
        print(f"{r['scheme']:<12} {r['peers']:>6} {r['adversarial']:>5.0%} "
              f"{r['recovered']:>4}/{r['trials']:<5} "
              f"{r['mean_erasure_fraction']:>8.3f} {r['mean_kib_fetched']:>7.0f} "
              f"{r['mean_gather_s']:>7.2f}s {dec:>9} {tot:>9} {thr:>11}")

    if not args.no_visuals:
        print_visuals(rows, cfg, schemes)

    if args.figures:
        write_figures(rows, cfg, args.figures)
        print(f"\nwrote figures to {args.figures}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"config": cfg.__dict__, "speedup": args.speedup,
                       "real_decode": args.real_decode, "rows": rows}, f, indent=2)
        print(f"\nwrote {args.json}")
