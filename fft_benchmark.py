"""
Measures the FFT/NTT decoder path in BCcodeEthereum.py against the
Vandermonde path it falls back to, and records WHY the answer comes out the
way it does.

    python3 fft_benchmark.py            # full sweep, writes fft_results.json
    python3 fft_benchmark.py --quick    # one rate, one trial, for a smoke test

This exists because the headline question -- "does the NTT decoder make the
block-circulant rows faster?" -- has a counter-intuitive answer, and a bare
timing table is not enough to defend it. Four things get measured:

  ab         FFT vs Vandermonde on the same erasure patterns, same process.
             This is the only fair comparison: both paths decode the same
             corrupted codeword back to back, so machine speed, thermal
             state and field-construction cost all cancel.

  profile    Where the FFT path actually spends its time. The NTT is not
             the expensive part, and a timing table alone cannot show that.

  nodes      A microbenchmark of vandermonde_solve on small-integer nodes
             versus 255-bit roots of unity. Making a code FFT-capable means
             defining it over roots of unity, and that choice has a cost
             that is paid even when the FFT never runs.

  structure  The GRS premise each phase rests on, as a count of polynomial
             coefficients that ought to vanish and do not. Phase 1's premise
             holds once the column multipliers are undone; phase 2's does
             not hold at all. See test_bc_fft.py for the same check as an
             assertion rather than a datum.

NOTE ON WALL-CLOCK. The full sweep runs the FFT path, which is slow -- tens
of seconds per decode -- so expect roughly 10-20 minutes. The Vandermonde
column finishes in seconds. Nothing here is a fixed cost you pay twice: the
JSON is committed, and make_figures.py reads it rather than re-measuring.
"""
import argparse
import json
import os
import random
import time

import numpy as np

import blob_generator as bg
import BCcodeEthereum as bc

GF = bg.GF
P = bg.BLS_MODULUS
K = bg.FIELD_ELEMENTS_PER_BLOB
HERE = os.path.dirname(os.path.abspath(__file__))

# The same five parameterisations the main benchmark sweeps, as
# (label, omega, rho, lambda). rho = omega throughout, so the rate is 0.5
# and every row is storage-matched to 1D-RS at n = 8192.
VARIANTS = [("BC-2048-L2", 2048, 2048, 2),
            ("BC-1024-L2", 1024, 1024, 2),
            ("BC-1024-L3", 1024, 1024, 3),
            ("BC-1024-L4", 1024, 1024, 4),
            ("BC-512-L2",   512,  512, 2)]
RATES = [0.05, 0.10, 0.20]
TRIALS = 3
SEED = 1000

# Phase 2 is held off throughout. It is not a speed question -- the premise
# it rests on is false (see the structure section) -- so letting it run would
# only add Gaussian-elimination time that tells us nothing about the FFT.
PAIR_CAP = 256


def _mask(n, rate, trial):
    return np.random.default_rng(SEED + trial).random(n) < rate


def measure_ab(blob, rates, trials):
    """FFT vs Vandermonde, same codeword, same erasures, same process."""
    rows = []
    for name, omega, rho, lam in VARIANTS:
        mu = K // omega
        n = mu * (rho + omega)
        n0 = rho + lam * omega
        eligible = (P - 1) % n0 == 0
        code = bc.encode_bc_structured(GF, GF(blob), mu, lam, omega, rho)
        for rate in rates:
            acc = {True: 0.0, False: 0.0}
            ok = {True: True, False: True}
            for t in range(trials):
                mask = _mask(n, rate, t)
                corrupt = code.copy()
                corrupt[mask] = GF(0)
                for use_fft in (True, False):
                    t0 = time.time()
                    rec, rem = bc.dec_cbc_2(
                        None, corrupt.copy(), mask.copy(), mu, lam, omega, rho,
                        pair_unknown_cap=PAIR_CAP,
                        use_fft_phase1=use_fft, use_fft_phase2=False)
                    acc[use_fft] += time.time() - t0
                    good = (not np.any(rem)
                            and [int(v) for v in rec[:K]] == list(blob))
                    ok[use_fft] &= good
            fft_s, van_s = acc[True] / trials, acc[False] / trials
            rows.append(dict(scheme=name, omega=omega, lam=lam, n0=n0,
                             fft_eligible=bool(eligible), rate=rate,
                             fft_s=round(fft_s, 3),
                             vandermonde_s=round(van_s, 3),
                             ratio=round(fft_s / van_s, 2) if van_s else None,
                             exact=bool(ok[True] and ok[False])))
            print(f"  {name:<12} rate={rate:<5} fft={fft_s:8.2f}s  "
                  f"vand={van_s:6.2f}s  ratio={fft_s / van_s:6.2f}x  "
                  f"exact={ok[True] and ok[False]}", flush=True)
    return rows


def measure_profile(blob):
    """Split one FFT block decode into its named stages.

    Measured by wrapping the three galois entry points the decoder actually
    calls, rather than by bucketing a cProfile dump. cProfile attributes the
    transform's real work to a generic dispatcher inside galois, so filtering
    its output by module name reports the NTT as taking no time at all, which
    is wrong in a way that happens to flatter the conclusion. Timing the calls
    directly says exactly what was measured.

    The point of the figure this feeds: the transform the whole approach is
    named after is a small minority of the cost."""
    import galois

    omega = rho = 1024
    lam = 2
    mu = K // omega
    n0 = rho + lam * omega
    code = bc.encode_bc_structured(GF, GF(blob), mu, lam, omega, rho)
    pts = bc.make_eval_pts(n0, P)
    idx = bc.get_local_indices(0, mu, lam, omega, rho)
    mask = [bool(v) for v in (np.random.default_rng(7).random(n0) < 0.10)]
    recv = [0 if mask[j] else int(code[idx[j]]) for j in range(n0)]

    spent = {"NTT / inverse NTT": 0.0,
             "erasure locator build": 0.0,
             "polynomial division": 0.0}

    def clocked(fn, key):
        def inner(*a, **kw):
            t0 = time.perf_counter()
            try:
                return fn(*a, **kw)
            finally:
                spent[key] += time.perf_counter() - t0
        return inner

    saved = (galois.ntt, galois.intt,
             galois.Poly.__divmod__, galois.Poly.__mul__)
    galois.ntt = clocked(saved[0], "NTT / inverse NTT")
    galois.intt = clocked(saved[1], "NTT / inverse NTT")
    galois.Poly.__divmod__ = clocked(saved[2], "polynomial division")
    galois.Poly.__mul__ = clocked(saved[3], "erasure locator build")
    try:
        t0 = time.perf_counter()
        out = bc.fft_grs_erasure_decode(recv, mask, pts, n0 - rho, P,
                                        col_mult=pts)
        total = time.perf_counter() - t0
    finally:
        (galois.ntt, galois.intt,
         galois.Poly.__divmod__, galois.Poly.__mul__) = saved
    assert out and out[0] is not None, "profile run should decode cleanly"

    spent["everything else"] = max(0.0, total - sum(spent.values()))
    print(f"  one block decode, n0={n0}: {total:.2f}s total")
    for k, v in spent.items():
        print(f"    {k:<24} {v:6.2f}s  ({100 * v / total:4.1f}%)")
    return dict(n0=n0, total_s=round(total, 3),
                buckets={k: round(v, 3) for k, v in spent.items()})


def measure_nodes():
    """Cost of solving over 255-bit roots of unity instead of small integers.

    Making the local code FFT-capable means defining it over roots of unity,
    because that is what an NTT needs. But the evaluation points define the
    code, so the Vandermonde fallback then has to solve over those same
    255-bit values. In pure-Python modular arithmetic the operand width is
    not free, and this is the cost the branch pays even with the FFT off."""
    n0, e = 3072, 300
    random.seed(1)
    roots = [int(x) for x in bc.make_eval_pts(n0, P)][:e]
    small = list(range(1, e + 1))
    syn = [random.randrange(P) for _ in range(e)]
    out = {}
    for label, nodes in (("small integers", small), ("roots of unity", roots)):
        t0 = time.time()
        bc.vandermonde_solve(nodes, syn, P)
        out[label] = round(time.time() - t0, 4)
        print(f"  vandermonde_solve, {e} {label:<16} {out[label]:.4f}s  "
              f"(node width {max(v.bit_length() for v in nodes)} bits)")
    out["ratio"] = round(out["roots of unity"] / out["small integers"], 2)
    out["n_nodes"] = e
    return out


def measure_structure(blob):
    """Nonzero tail coefficients -- the GRS premise, phase by phase.

    fft_grs_erasure_decode inverse-transforms the locator-multiplied received
    word and requires the coefficients above k+e to vanish. Counting how many
    do not is the cleanest statement of whether the premise holds."""
    import galois

    def tail(values, size, k_poly):
        c = [int(x) for x in galois.intt(values, size=size, modulus=P)]
        return sum(1 for v in c[k_poly:] if v % P)

    omega = rho = 1024
    lam = 3
    mu = K // omega
    code = bc.encode_bc_structured(GF, GF(blob), mu, lam, omega, rho)

    n0, k0 = rho + lam * omega, lam * omega
    pts0 = bc.make_eval_pts(n0, P)
    local = [int(code[g]) for g in bc.get_local_indices(0, mu, lam, omega, rho)]
    p1_raw = tail(local, n0, k0)
    p1_fix = tail([(local[j] * pow(int(pts0[j]), P - 2, P)) % P
                   for j in range(n0)], n0, k0)

    sup = sorted(set(bc.get_local_indices(0, mu, lam, omega, rho))
                 | set(bc.get_local_indices(1, mu, lam, omega, rho)))
    n_aux = len(sup)
    k_aux = n_aux - 2 * rho
    pts_a = bc.make_eval_pts(n_aux, P)
    union = [int(code[g]) for g in sup]
    p2_raw = tail(union, n_aux, k_aux)
    p2_fix = tail([(union[j] * pow(int(pts_a[j]), P - 2, P)) % P
                   for j in range(n_aux)], n_aux, k_aux)

    print(f"  phase 1  n0={n0}     tail must vanish over {n0 - k0} coeffs: "
          f"raw={p1_raw}  after multipliers={p1_fix}")
    print(f"  phase 2  n_aux={n_aux}  tail must vanish over {n_aux - k_aux} "
          f"coeffs: raw={p2_raw}  after multipliers={p2_fix}")
    return dict(phase1=dict(n=n0, tail_len=n0 - k0, raw=p1_raw, fixed=p1_fix),
                phase2=dict(n=n_aux, tail_len=n_aux - k_aux,
                            raw=p2_raw, fixed=p2_fix))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true",
                    help="one rate, one trial -- a smoke test, not a result")
    ap.add_argument("--out", default=os.path.join(HERE, "fft_results.json"))
    args = ap.parse_args()

    rates = [0.10] if args.quick else RATES
    trials = 1 if args.quick else TRIALS

    # Seeded random rather than a repeating byte pattern. A structured blob
    # makes some polynomial coefficients vanish by coincidence, which would
    # understate the phase-2 tail count and make the premise look less broken
    # than it is. Seeded keeps it reproducible without that flattery.
    rnd = random.Random(SEED)
    app = bytes(rnd.randrange(256) for _ in range(bg.USABLE_BYTES_PER_BLOB))
    blob = bg.bytes_to_blobs(app)[0]

    print("structure: does the GRS premise hold, phase by phase?")
    structure = measure_structure(blob)
    print("\nnodes: what do 255-bit evaluation points cost the fallback?")
    nodes = measure_nodes()
    print("\nprofile: where does the FFT path spend its time?")
    profile = measure_profile(blob)
    print("\nab: FFT against the Vandermonde fallback it replaces")
    ab = measure_ab(blob, rates, trials)

    payload = dict(quick=args.quick, trials=trials, rates=rates,
                   pair_unknown_cap=PAIR_CAP, seed=SEED,
                   structure=structure, nodes=nodes, profile=profile, ab=ab)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
