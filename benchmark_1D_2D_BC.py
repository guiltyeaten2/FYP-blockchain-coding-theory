"""
Benchmark: 1D-RS vs 2D-RS vs Block-Circulant (BC) codes.

Runs all three coding schemes against the SAME real Ethereum blob, over the
SAME field, at each scheme's own Ethereum-relevant (n, k) parameterisation,
and sweeps the same set of erasure rates -- producing the comparative
dataset the report's Phase 3 methodology asks for (computational cost,
overhead, and fault tolerance under varying adversarial sampling rates).

WHAT'S HELD IDENTICAL ACROSS ALL THREE SCHEMES (the "comparable parameters
and input" the report needs for a fair comparison):
  - Field: the real BLS12-381 scalar field (Fr), via blob_generator.GF.
  - Message: k = 4096 field elements = exactly one real Ethereum blob,
    packed from the SAME real application bytes via
    blob_generator.bytes_to_blobs() -- not three independently-random
    blobs, one per scheme.
  - Erasure model: erasure channel only (missing samples), generated at
    the SAME target rate for every scheme on every sweep point. Where two
    schemes share the same codeword length (1D-RS and BC both have
    n=8192), each trial corrupts them at the literal SAME erased
    positions, not merely the same rate -- the strictest form of
    "comparable input" two differently-shaped codes can share.
  - Success criterion: full codeword recovered AND the recovered message
    round-trips through blob_generator.blob_to_bytes() back to the exact
    original application bytes -- not just a field-element comparison.

WHAT'S DELIBERATELY LEFT DIFFERENT (each scheme's own Ethereum-relevant
shape, reported as a result, not forced equal):
  - 1D-RS:  n=8192,  2x total overhead  -- PeerDAS's actual extension ratio.
  - BC:     n=8192,  2x total overhead  -- same ratio as 1D-RS/PeerDAS,
            via mu=2048 local blocks, omega=2, rho=2, lambda=2 (d=5),
            i.e. the SAME parameters BCcodeEthereum.py already documents.
  - 2D-RS:  n=16384, 4x total overhead  -- this project's own documented
            per-axis-doubling tradeoff (see 2D_RS_Galois.py's docstring
            and docs/1D_vs_2D_RS_comparison.md); not a real PeerDAS ratio.

WHY MULTIPLE TRIALS PER RATE, NOT JUST ONE:
1D-RS and 2D-RS decode via a formal erasure-budget check (build_erasure_
locator / decode_pass): any pattern within budget succeeds with certainty,
any pattern over budget fails with certainty -- a single trial at a rate
comfortably below the ceiling is representative of every trial at that
rate. BC's DecCBC[2] decoder is NOT like this: it only resolves erasures
within a single local block (<=rho) or a pair of ADJACENT local blocks
(<=2*rho) at a time. At mu=2048 independent blocks, i.i.d. random erasure
at a given rate can -- purely by chance -- cluster more than 2*rho
erasures across a run of 3+ consecutive blocks, which this decoder has no
mechanism to resolve. This was observed directly during development: at
rate=0.15, one random mask failed (erasures remained unresolved) while a
different random mask at the SAME rate succeeded 5/5. That makes BC's
recoverability a per-trial PROBABILITY at a given rate, not a certainty,
so it needs repeated trials to characterise -- unlike the other two,
where one trial is representative. BC's decode is cheap (sub-10s even at
high rates), so this is affordable; 1D-RS's decode is the expensive one
(its cost is discussed in docs/1D_vs_2D_RS_comparison.md), so it keeps a
single trial per rate to keep total runtime reasonable.

This script imports 1D_RS_Galois.py / 2D_RS_Galois.py / BCcodeEthereum.py
as libraries (their own demos stay behind `if __name__ == "__main__":` and
do not run on import) rather than re-implementing any of their encode/
decode logic, so a fix made in one of those files is automatically picked
up here.

    pip install galois numpy

Expect a full run to take on the order of 10-15 minutes: BC's parity-check
matrix is built once (~1s-2min depending on machine load, observed both
on this dev machine) and reused across every trial; 1D-RS's decode time
is the dominant single-trial cost at the higher erasure rates; BC's
extra trial-count multiplies its own (small) per-trial cost.
"""

import os
import time
import json
import importlib.util
import numpy as np

import blob_generator as bg
import BCcodeEthereum as bc

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_module(path, name):
    """1D_RS_Galois.py / 2D_RS_Galois.py aren't valid Python identifiers,
    so `import 1D_RS_Galois` is a SyntaxError -- load them by file path
    instead. Their demo blocks are guarded by `if __name__ == "__main__":`
    so this does not execute anything beyond function/constant definitions."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs1d = _load_module(os.path.join(HERE, "1D_RS_Galois.py"), "rs1d")
rs2d = _load_module(os.path.join(HERE, "2D_RS_Galois.py"), "rs2d")

GF = bg.GF
P = bg.BLS_MODULUS
K = bg.FIELD_ELEMENTS_PER_BLOB  # 4096, shared by all three schemes

# ---------------------------------------------------------------------------
# BC PARAMETERS -- identical to BCcodeEthereum.py's own module-level choice,
# repeated here explicitly so this file's parameterisation is self-evident
# and doesn't rely on reading BCcodeEthereum.py to know what it benchmarks.
# ---------------------------------------------------------------------------
BC_OMEGA, BC_RHO, BC_LAMBDA = bc.omega, bc.rho, bc.lambda_
BC_MU = bc.mu
assert BC_MU * BC_OMEGA == K, "BC parameters must span exactly one blob's worth of message symbols"

RATES = [0.05, 0.15, 0.25, 0.35, 0.45]
RNG_SEED = 20260827  # fixed seed -> reproducible sweep across runs

# Trials per rate, per scheme. 1D-RS/2D-RS decode deterministically against
# a formal budget (see module docstring), so 1 trial is representative;
# BC's decoder is probabilistic at a given rate, so it gets more trials to
# produce a meaningful success-rate estimate.
TRIALS_PER_RATE = {"1D-RS": 1, "2D-RS": 3, "BC": 10}


# ---------------------------------------------------------------------------
# SCHEME ADAPTERS -- a common interface so the sweep loop below doesn't need
# to know any scheme-specific detail. Each adapter wraps the ACTUAL
# functions from the real files; none of the encode/decode/erasure-recovery
# logic is reimplemented here.
# ---------------------------------------------------------------------------
class OneDAdapter:
    name = "1D-RS"
    k = K
    n = rs1d.EXT_LEN  # 8192

    def __init__(self):
        self.alpha = rs1d.root_of_unity(self.n, P)

    def encode(self, blob):
        return rs1d.encode_blob(blob)  # list[int], length n

    def random_mask(self, rate, rng):
        return rs1d.random_erasure_mask(self.n, rate, rng)  # 1D bool array

    def corrupt(self, encoded, mask):
        out = list(encoded)
        for i in np.nonzero(mask)[0]:
            out[int(i)] = 0
        return out

    def decode(self, corrupted, mask):
        t0 = time.time()
        recovered, ok = rs1d.decode(corrupted, mask, k=self.k, n=self.n,
                                     alpha=self.alpha, brp_n=rs1d.BRP_N, p=P,
                                     label="1D-RS")
        return recovered, ok, time.time() - t0

    def extract_message(self, recovered):
        return rs1d.restrict(recovered, self.k, self.n, rs1d.BRP_K, rs1d.BRP_N, P)


class TwoDAdapter:
    name = "2D-RS"
    k = K
    n = rs2d.EXT_ROWS * rs2d.EXT_COLS  # 16384, reported for overhead only

    def __init__(self):
        self.alpha_rows = rs2d.root_of_unity(rs2d.EXT_ROWS, P)
        self.alpha_cols = rs2d.root_of_unity(rs2d.EXT_COLS, P)

    def encode(self, blob):
        data_matrix = np.array(blob, dtype=object).reshape(rs2d.BLOB_ROWS, rs2d.BLOB_COLS)
        return rs2d.encode_blob(data_matrix)  # (EXT_ROWS, EXT_COLS) grid

    def random_mask(self, rate, rng):
        return rs2d.random_erasure_mask(rs2d.EXT_ROWS, rs2d.EXT_COLS, rate, rng)

    def corrupt(self, encoded, mask):
        out = encoded.copy()
        out[mask] = 0
        return out

    def decode(self, corrupted, mask):
        t0 = time.time()
        recovered, final_mask = rs2d.decode_iterative(
            corrupted, mask, k_rows=rs2d.BLOB_ROWS, k_cols=rs2d.BLOB_COLS,
            n_rows=rs2d.EXT_ROWS, n_cols=rs2d.EXT_COLS,
            alpha_rows=self.alpha_rows, alpha_cols=self.alpha_cols,
            brp_rows=rs2d.BRP_EXT_ROWS, brp_cols=rs2d.BRP_EXT_COLS, p=P)
        ok = not final_mask.any()
        return recovered, ok, time.time() - t0

    def extract_message(self, recovered):
        row_ext_recovered = np.array(
            [rs2d.restrict(recovered[:, c], rs2d.BLOB_ROWS, rs2d.EXT_ROWS,
                            rs2d.BRP_BLOB_ROWS, rs2d.BRP_EXT_ROWS, P)
             for c in range(rs2d.EXT_COLS)],
            dtype=object,
        ).T
        data_out = np.array(
            [rs2d.restrict(row_ext_recovered[r, :], rs2d.BLOB_COLS, rs2d.EXT_COLS,
                            rs2d.BRP_BLOB_COLS, rs2d.BRP_EXT_COLS, P)
             for r in range(rs2d.BLOB_ROWS)],
            dtype=object,
        )
        return [int(v) for v in data_out.reshape(-1)]


class BCAdapter:
    name = "BC"
    k = K
    n = bc.n  # 8192

    def __init__(self):
        t0 = time.time()
        self.H_BC = bc.build_block_circulant_h(GF, BC_MU, BC_LAMBDA, BC_OMEGA, BC_RHO)
        self.h_build_time = time.time() - t0

    def encode(self, blob):
        m = GF(blob)
        return bc.encode_bc_structured(GF, m, BC_MU, BC_LAMBDA, BC_OMEGA, BC_RHO)

    def random_mask(self, rate, rng):
        return rng.random(self.n) < rate

    def corrupt(self, encoded, mask):
        out = encoded.copy()
        out[mask] = GF(0)
        return out

    def decode(self, corrupted, mask):
        t0 = time.time()
        recovered, remaining = bc.dec_cbc_2(self.H_BC, corrupted, mask,
                                             BC_MU, BC_LAMBDA, BC_OMEGA, BC_RHO)
        ok = not np.any(remaining)
        return recovered, ok, time.time() - t0

    def extract_message(self, recovered):
        return [int(v) for v in recovered[:self.k]]


# ---------------------------------------------------------------------------
# BENCHMARK DRIVER
# ---------------------------------------------------------------------------
def blob_matches(candidate_ints, original_blob, app_bytes):
    """Success is field-element-exact AND survives the real EIP-4844
    byte round trip -- not just 'the numbers matched'."""
    if list(candidate_ints) != list(original_blob):
        return False
    try:
        bg.validate_blob(candidate_ints)
        return bg.blob_to_bytes(candidate_ints) == app_bytes
    except ValueError:
        return False


def run_scheme(adapter, blob, app_bytes, rates, rng, trials_per_rate,
               shared_masks_by_rate=None):
    """shared_masks_by_rate: optional {rate: [mask, mask, ...]} -- when
    given, these exact masks are used instead of drawing fresh ones (used
    to give 1D-RS and BC the literal same erased positions per trial)."""
    print(f"\n{'='*70}\n {adapter.name}  (k={adapter.k}, n={adapter.n}, "
          f"overhead={adapter.n/adapter.k:.1f}x)\n{'='*70}")

    extra_setup = getattr(adapter, "h_build_time", None)
    if extra_setup is not None:
        print(f"  one-time setup (parity-check matrix build): {extra_setup:.1f}s")

    t0 = time.time()
    encoded = adapter.encode(blob)
    t_encode = time.time() - t0
    baseline_ok = blob_matches(adapter.extract_message(encoded), blob, app_bytes)
    print(f"  encode: {t_encode:.3f}s  (no-erasure round trip correct: {baseline_ok})")
    if not baseline_ok:
        raise RuntimeError(f"{adapter.name}: encode/extract round trip failed with NO "
                            f"erasures -- something is broken, refusing to report timings")

    results = []
    for rate in rates:
        n_trials = trials_per_rate.get(adapter.name, 1)
        successes = 0
        decode_times = []
        n_erased = None
        for trial_idx in range(n_trials):
            if shared_masks_by_rate is not None:
                mask = shared_masks_by_rate[rate][trial_idx]
            else:
                mask = adapter.random_mask(rate, rng)
            n_erased = int(np.sum(mask))
            corrupted = adapter.corrupt(encoded, mask)
            recovered, ok, t_decode = adapter.decode(corrupted, mask)
            exact = ok and blob_matches(adapter.extract_message(recovered), blob, app_bytes)
            decode_times.append(t_decode)
            successes += exact
        mean_t = sum(decode_times) / len(decode_times)
        print(f"  rate={rate:.2f}  erased={n_erased:5d}/{adapter.n}  "
              f"decode(mean of {n_trials})={mean_t:7.3f}s  "
              f"success={successes}/{n_trials}")
        results.append({
            "scheme": adapter.name, "rate": rate, "n_erased": n_erased,
            "n": adapter.n, "k": adapter.k, "trials": n_trials,
            "successes": successes, "success_rate": successes / n_trials,
            "mean_decode_time_s": round(mean_t, 4),
            "decode_times_s": [round(t, 4) for t in decode_times],
        })
    return {
        "scheme": adapter.name, "k": adapter.k, "n": adapter.n,
        "overhead": adapter.n / adapter.k, "encode_time_s": round(t_encode, 4),
        "setup_time_s": round(extra_setup, 4) if extra_setup is not None else 0.0,
        "trials": results,
    }


if __name__ == "__main__":
    print("=" * 70)
    print(" BENCHMARK: 1D-RS vs 2D-RS vs BLOCK-CIRCULANT (BC)")
    print(" same field, same blob, same erasure rates -- see module docstring")
    print("=" * 70)

    app_bytes = os.urandom(bg.USABLE_BYTES_PER_BLOB)  # one real blob's worth
    blob = bg.bytes_to_blobs(app_bytes)[0]
    bg.validate_blob(blob)
    print(f"\nGenerated {len(app_bytes)} real application bytes, packed into "
          f"{len(blob)} field elements via bg.bytes_to_blobs() -- this exact "
          f"blob is the input to ALL THREE schemes below.")

    rng = np.random.default_rng(RNG_SEED)

    adapters = [OneDAdapter(), TwoDAdapter(), BCAdapter()]
    all_results = []

    # 1D-RS and BC share n=8192: corrupt them at the literal SAME positions
    # per trial, not just the same rate, for the strictest comparison two
    # differently-structured but equal-length codes can share. 2D-RS has a
    # different n (16384) so it draws its own masks at the same RATE.
    shared_n = OneDAdapter.n
    assert BCAdapter.n == shared_n, "1D-RS and BC were expected to share n"
    shared_n_trials = max(TRIALS_PER_RATE["1D-RS"], TRIALS_PER_RATE["BC"])
    shared_masks = {
        rate: [(rng.random(shared_n) < rate) for _ in range(shared_n_trials)]
        for rate in RATES
    }

    for adapter in adapters:
        use_shared = adapter.n == shared_n
        result = run_scheme(adapter, blob, app_bytes, RATES, rng, TRIALS_PER_RATE,
                             shared_masks_by_rate=shared_masks if use_shared else None)
        all_results.append(result)

    print("\n" + "=" * 70)
    print(" SUMMARY")
    print("=" * 70)
    header = f"{'scheme':<8} {'k':>6} {'n':>7} {'overhead':>9} {'encode(s)':>10} {'setup(s)':>9}"
    print(header)
    for r in all_results:
        print(f"{r['scheme']:<8} {r['k']:>6} {r['n']:>7} {r['overhead']:>8.1f}x "
              f"{r['encode_time_s']:>10.3f} {r['setup_time_s']:>9.1f}")

    print(f"\nMean decode time per rate:")
    print(f"{'scheme':<8} " + " ".join(f"rate={r:.2f}".rjust(14) for r in RATES))
    for r in all_results:
        row = [r["scheme"].ljust(8)]
        for t in r["trials"]:
            row.append(f"{t['mean_decode_time_s']:>7.3f}s".rjust(14))
        print(" ".join(row))

    print(f"\nSuccess rate per rate (successes/trials):")
    print(f"{'scheme':<8} " + " ".join(f"rate={r:.2f}".rjust(14) for r in RATES))
    for r in all_results:
        row = [r["scheme"].ljust(8)]
        for t in r["trials"]:
            row.append(f"{t['successes']}/{t['trials']}".rjust(14))
        print(" ".join(row))

    out_path = os.path.join(HERE, "benchmark_results.json")
    with open(out_path, "w") as f:
        json.dump({"rates": RATES, "seed": RNG_SEED,
                    "trials_per_rate": TRIALS_PER_RATE, "results": all_results},
                   f, indent=2)
    print(f"\nFull results written to {out_path}")
