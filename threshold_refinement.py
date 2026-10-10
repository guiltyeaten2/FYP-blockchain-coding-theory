"""
Threshold refinement: dense trials across each scheme's transition band.

    python3 threshold_refinement.py            # -> threshold_results.json
    python3 threshold_refinement.py --quick    # 2 trials/rate smoke test

WHY THIS EXISTS

The main sweep in benchmark_1D_2D_BC.py covers 2% to 55% erasure on a coarse
grid, deliberately: it is there to show each scheme's whole curve, and its
trial budget is spread across 18 rates. Near each threshold it runs as few
as three trials, because the 1D-RS decode costs ~40 s.

Three trials cannot place a threshold to three decimal places, and the
consequences showed up:

  * 1D-RS was reported at 0.505, above the 0.5 an MDS code with n = 2k can
    sustain. The decoder was fine -- the two trials at 0.50 that recovered
    had 4058 and 4087 erasures, the one that failed had 4130, exactly the
    n - k = 4096 rule -- but 2/3 against a true probability of 0.504 is an
    ordinary run of luck, and interpolating between two grid points turned
    it into a third decimal place.

  * Two block-circulant rows jump from 100% straight to 0% between adjacent
    grid points. With no trial anywhere in between, the data say nothing
    about where in that gap the threshold lies, and a bootstrap reports an
    interval of width zero -- false precision rather than real.

This script samples each scheme's own transition band on a fine grid, with
enough trials that several rates land partway down the curve. Thresholds
come from a maximum-likelihood logistic fit with a bootstrap interval
(thresholds.py), not from interpolation.

It reuses the benchmark's adapters and run_scheme unchanged, so a trial here
is measured exactly as a trial there: same blob packing, same field, same
byte-level success criterion.

Runtime is roughly an hour, most of it the 1D-RS decodes. Run nothing else
CPU-heavy alongside it -- an earlier sweep picked up spurious 57x spikes
from exactly that.
"""
import argparse
import json
import os
import time

import numpy as np

import blob_generator as bg
import benchmark_1D_2D_BC as B
import thresholds as T

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261010


def _grid(lo, hi, step):
    n = int(round((hi - lo) / step)) + 1
    return [round(lo + i * step, 4) for i in range(n)]


# Each scheme's own transition band, from the coarse sweep, padded so the
# fitted curve has a full 100% plateau and 0% floor on either side. Steps are
# finer where the transition is sharper: 1D-RS has n = 8192 symbols, so its
# realised erasure fraction varies by only ~0.0055 around the target and its
# whole transition is about two hundredths wide.
GRIDS = {
    "1D-RS":      _grid(0.485, 0.515, 0.005),
    "2D-RS":      _grid(0.37,  0.44,  0.01),
    "BC-2048-L2": _grid(0.325, 0.355, 0.005),
    "BC-1024-L2": _grid(0.325, 0.365, 0.005),
    "BC-1024-L3": _grid(0.250, 0.300, 0.005),
    "BC-1024-L4": _grid(0.16,  0.25,  0.01),
    "BC-512-L2":  _grid(0.330, 0.375, 0.005),
}

# 1D-RS gets fewer trials per rate because each successful decode costs about
# 40 s; its curve is also exactly known (mds_success_probability), which the
# fit is checked against. Everything else is cheap enough for 20.
TRIALS = {"1D-RS": 12}
DEFAULT_TRIALS = 20


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true",
                    help="two trials per rate: checks the pipeline, not a result")
    args = ap.parse_args()

    app = os.urandom(bg.USABLE_BYTES_PER_BLOB)
    blob = bg.bytes_to_blobs(app)[0]
    bg.validate_blob(blob)
    rng = np.random.default_rng(SEED)

    adapters = [B.OneDAdapter(), B.TwoDAdapter()] + [
        B.BCAdapter(w, rho, lam, pair_unknown_cap=B.BC_PAIR_UNKNOWN_CAP)
        for (w, rho, lam) in B.BC_VARIANTS
    ]

    def trials_fn(name, rate):
        return 2 if args.quick else TRIALS.get(name, DEFAULT_TRIALS)

    out = {"_what": "Dense trials across each scheme's transition band, for "
                    "threshold estimation. See threshold_refinement.py.",
           "seed": SEED, "quick": args.quick, "schemes": {}}
    t_start = time.time()
    for ad in adapters:
        grid = GRIDS[ad.name]
        res = B.run_scheme(ad, blob, app, grid, rng, trials_fn)
        records = res["trials"]
        est = T.estimate_threshold(T.points_from_trials(records))
        entry = {"n": ad.n, "k": ad.k, "grid": grid, "trials": records,
                 "estimate": est}
        if ad.name == "1D-RS":
            entry["mds_exact_threshold"] = T.mds_threshold(ad.n, ad.k)
            # Every 1D-RS trial must obey the MDS rule. If one recovered with
            # more than n - k erasures, the decoder is broken and every
            # number in this project is in doubt -- so check, don't assume.
            violations = [
                (r["rate"], e, s)
                for r in records
                for e, s in zip(r["n_erased_per_trial"],
                                r["success_per_trial"])
                if (e <= ad.n - ad.k) != s
            ]
            entry["mds_rule_violations"] = violations
            print(f"  MDS rule (recover iff erasures <= {ad.n - ad.k}): "
                  f"{len(violations)} violations across "
                  f"{sum(r['trials'] for r in records)} trials")
        out["schemes"][ad.name] = entry
        if est:
            print(f"  -> threshold {est['threshold']:.4f}  "
                  f"95% CI [{est['ci_low']:.4f}, {est['ci_high']:.4f}]")

    out["runtime_s"] = round(time.time() - t_start, 1)
    path = os.path.join(HERE, "threshold_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nwrote {os.path.basename(path)} in {out['runtime_s']:.0f}s")


if __name__ == "__main__":
    main()
