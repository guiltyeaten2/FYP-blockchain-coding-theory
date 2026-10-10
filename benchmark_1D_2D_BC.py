"""
Benchmark: 1D-RS vs 2D-RS vs Block-Circulant (BC) codes.

Seven rows: 1D-RS, 2D-RS, and five BC parameterisations.

Runs every coding scheme against the SAME real Ethereum blob, over the
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

STORAGE COST IS MATCHED TO WITHIN 3%, WHICH IT PREVIOUSLY WAS NOT:
  - 1D-RS:   n=8192,  2.00x overhead, rate 0.500 -- PeerDAS's actual ratio.
  - BC-*:    n=8192,  2.00x overhead, rate 0.500 -- five parameterisations,
             all with rho=omega, differing in lambda and mu (see BC_VARIANTS).
  - 2D-RS:   n=8448,  2.06x overhead, rate 0.485 -- an 88x96 grid.

  The 2D-RS geometry has now been corrected twice, and the reasoning is
  worth keeping. A product code's rate is the PRODUCT of its two component
  rates, so the original 64->128 on both axes gave rate 1/4 and 4x storage:
  that compared a 4x-overhead code against 2x-overhead codes at equal
  erasure rate, which flattered 2D-RS. To land the overall rate on 0.5 each
  component rate should be sqrt(0.5) = 0.707, i.e. each axis should extend
  64 -> 90.5. A 90x90 grid is the natural reading of that, but no length-90
  NTT exists in this field: 90 = 2*3^2*5 needs 3^2 (p-1 has only 3^1) and 5
  (absent). The reachable lengths bracket it -- 88 = 8*11 and 96 = 32*3 --
  and using one per axis gives rate 4096/8448 = 0.485, the closest any
  reachable pair gets to 0.5. The previous 88x88 gave 0.529 at 1.89x, which
  is further off on both measures AND spent less storage than the codes it
  was compared against. See 2D_RS_Galois.py for the full argument, including
  why exactly 0.500 is unreachable for any 2D product code on this blob.

WHY THE BC PARAMETERISATIONS CHANGED (AGAIN):
The first sweep used (omega, rho, lambda) = (2, 2, 2) with mu=2048, whose
minimum distance d = lambda*rho + 1 = 5 guarantees correction of just four
erasures in 8192 symbols -- everything above that was luck about how the
mask fell. The second used lambda = mu at mu = 4, 8, 16, lifting d to
4097 = n-k+1 (MDS, matching Reed-Solomon's optimum) but measuring the same
lambda = mu extreme three times over, with decoder reach falling to 0.059 at
mu=16. Supervisor guidance (2026-09-15) is that DecCBC is only practical up
to lambda = 3, that lambda = 16 is not implementable at all, and that the
analysis should sit at lambda = 2 and lambda = 3. This sweep does that,
keeping one lambda = 4 row as the MDS anchor. The trade-off it exposes:
raising lambda raises the CODE's guarantee (d-1)/n = lambda*omega/n but
lowers the DECODER's typical reach rho/n0 = 1/(1+lambda). Separating those
two is the point of the sweep -- see BC_VARIANTS for the full table.

WHY THE RATE SWEEP NOW CROSSES EACH SCHEME'S OWN CEILING, NOT JUST
APPROACHES IT (methodology revision -- see docs/benchmark_1D_2D_BC_report.md
for the full writeup):
An earlier version of this sweep stopped at rate=0.45, comfortably inside
every scheme's formal erasure budget (1D-RS/BC: n-k=k, i.e. rate=0.50;
2D-RS: 50% per line, with cross-axis rescue on top). That is a real gap,
not a stylistic choice: it means the sweep could report "1D-RS and 2D-RS
both succeed at every tested rate" without ever actually finding out where
either one stops succeeding, or whether 2D-RS's iterative cross-axis
rescue buys it any real headroom past 1D-RS's hard single-shot ceiling --
which is the project's central hypothesis about 2D-RS's advantage, and it
was going untested. RATES now adds a fine-grained band (0.46-0.55)
straddling the 50% boundary for exactly this reason: below it, an i.i.d.
erasure mask at the nominal rate almost always draws fewer than n-k
erased cells and decode is deterministic; at/above it, binomial sampling
variance in the ACTUAL erased count (not just the nominal rate) starts to
matter -- a mask drawn at rate=0.49 can, by chance, still exceed the n-k
budget, and one drawn at rate=0.51 can, by chance, still fall under it.
That is a genuine per-trial probability, not a certainty, for ALL THREE
schemes near their own boundary -- which is why trial counts below are now
a function of (scheme, rate), not a flat per-scheme constant.

WHY TRIAL COUNTS ARE A FUNCTION OF (SCHEME, RATE), NOT A FLAT CONSTANT:
Deep inside a scheme's safe zone (well under its erasure budget), 1D-RS
and 2D-RS decode via a formal budget check (build_erasure_locator /
decode_pass): any pattern within budget succeeds with certainty, any
pattern over budget fails with certainty, so one trial is genuinely
representative of every trial at that rate -- more trials there would just
burn runtime confirming the same deterministic outcome. That stops being
true near the boundary (see above), where trial counts step up sharply
(see `trials_for()`) to actually characterise the transition rather than
sample it once and call it representative. BC's DecCBC[2] decoder is
different in kind: it only resolves erasures within a single local block
(<=rho) or a pair of ADJACENT local blocks (<=2*rho) at a time, and never
looks at the codeword as a whole. A block succeeds when the erasures landing
in its own support of n0 = rho + lambda*omega symbols number at most rho.
Whether any of the mu blocks comes in under that budget is a matter of how
the mask happens to fall -- and when lambda < mu, one block clearing is not
the end of it either, since its support holds only part of the message and
the rest has to follow by cascade through the overlapping neighbours. Both
steps are chance, so BC's recoverability is a per-trial probability rather
than a certainty, and it keeps a flat, comparatively high trial count
throughout rather than only near a ceiling.
BC's decode is cheap (a few seconds at most), so this is affordable;
1D-RS's decode is the expensive one (its cost is discussed in
docs/1D_vs_2D_RS_comparison.md) and its per-trial cost peaks almost
exactly at its own boundary (division cost ~ O((n-e)*e), maximised at
e=n/2=n-k) -- the worst possible place to also want more trials -- so its
trial counts stay the most conservative of the three even in the
boundary band.

Every success_rate reported below is also given a 95% Wilson score
confidence interval (see `wilson_ci()`), computed from its own trial
count -- so a "0/1" and a "0/10" no longer look like the same claim.

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
# Each entry is (omega, rho, lambda_); mu is forced to K // omega so that
# every variant carries exactly one blob, and every variant here sets
# rho = omega, which fixes n = mu*(rho+omega) = 2k = 8192 and hence rate 1/2
# for every row, matching 1D-RS exactly.
#
# TWO QUANTITIES MOVE IN OPPOSITE DIRECTIONS AS LAMBDA CHANGES, AND THE WHOLE
# POINT OF THIS ROW SET IS TO SEPARATE THEM:
#
#   the CODE's worst-case guarantee    (d-1)/n, with d = lambda*rho + 1,
#                                      so lambda*omega/8192 -- RISES with lambda
#   the DECODER's typical reach        a local block resolves while the
#                                      erasures landing in its own support of
#                                      n0 = rho + lambda*omega symbols number
#                                      at most rho, i.e. while the rate is
#                                      below rho/n0 = 1/(1+lambda)
#                                      -- FALLS with lambda
#
# So a larger lambda buys a better code and a worse decoder. lambda = mu is
# the extreme case: every parity block depends on every information block,
# d reaches 4097 = n-k+1 (MDS, matching Reed-Solomon's optimum), and the
# decoder's reach bottoms out at 1/(1+mu).
#
# WHY THE PREVIOUS ROW SET CHANGED. It swept lambda = mu at mu = 4, 8, 16,
# i.e. three MDS codes whose decoders reached 0.200, 0.111 and 0.059. That
# measured the lambda = mu extreme three times over and never sampled the
# regime the BC construction is actually for. Supervisor guidance (2026-09-15)
# is that the DecCBC decoding algorithm is only practical up to lambda = 3 --
# lambda = 16 in particular is not implementable -- and that analysis should
# concentrate on lambda = 2 and lambda = 3. These rows do that, and keep ONE
# lambda = 4 row as the MDS anchor so the "code vs decoder" comparison below
# still has its reference point.
#
# Note the pair of MDS rows this produces: (2048, 2048, 2) and (1024, 1024, 4)
# are BOTH MDS with d = 4097 -- identical as codes -- yet their decoders reach
# 0.333 and 0.200 respectively. Same code quality, different decoder reach,
# from lambda alone. That is the cleanest statement of the distinction this
# whole sweep exists to make.
#
# SOURCE CHECK (Sasidharan, Viterbo & Feist, ePrint 2026/708 -- the BC-for-
# PeerDAS paper the supervisor pointed at). Its Sec. 3.1 notation table gives
# [n0, k0] = [lambda*omega + rho, lambda*omega], [n, k] = [mu*(omega+rho),
# mu*omega], S = lambda*rho/n and S0 = rho/n0, all of which this file already
# matched. Two things from it are worth carrying into the write-up:
#   - The paper FIXES lambda = 2 for its encoding and reconstruction
#     algorithms and its whole performance analysis, and states the
#     lambda*rho erasure-correction result for lambda = 2, 3 only. So the
#     lambda=2 rows here sit exactly where the paper does; the lambda=3 row
#     sits at the edge of its stated range; and the lambda=4 row is outside
#     it, which is why it is kept only as an anchor.
#   - Its worked example is mu=4, lambda=2, rho=omega, with omega=32 CELLS at
#     stacking depth D=64. Its parameters are counted in cells, not in field
#     symbols. Converting: a 4096-symbol blob at D=64 is 64 cells, so mu=4
#     gives omega = 16 cells = 1024 field symbols -- i.e. the (1024, 1024, 2)
#     row below IS the paper's worked configuration, expressed in symbols.
#
#   omega  rho   mu  lambda    n0     k0    d_min   (d-1)/n   1/(1+lambda)
#    2048 2048    2       2   6144   4096     4097     0.500          0.333   MDS
#    1024 1024    4       2   3072   2048     2049     0.250          0.333
#    1024 1024    4       3   4096   3072     3073     0.375          0.250
#    1024 1024    4       4   5120   4096     4097     0.500          0.200   MDS
#     512  512    8       2   1536   1024     1025     0.125          0.333
#
# The lambda=2 rows at mu=4 and mu=8 are the interesting ones: their decoder
# reach (0.333) EXCEEDS their own worst-case guarantee (0.250 and 0.125). That
# is not a contradiction -- (d-1)/n is what the code survives against ANY
# erasure pattern, while this sweep draws patterns i.i.d. at random, and a
# random pattern is very unlikely to be the adversarial one. Measuring both
# numbers side by side is the point: these rows are not fully decodable in the
# worst case, but they show what the construction can do in the average case.
BC_VARIANTS = [
    (2048, 2048, 2),   # mu=2, lambda=mu -> MDS; supervisor's "raise omega to 2048"
    (1024, 1024, 2),   # mu=4, lambda=2
    (1024, 1024, 3),   # mu=4, lambda=3
    (1024, 1024, 4),   # mu=4, lambda=mu -> MDS anchor, retained for continuity
    (512, 512, 2),     # mu=8, lambda=2
]

# WHY mu=6 IS NOT IN THAT LIST, THOUGH IT WAS ASKED FOR.
# mu is not free here: the message is one blob, so mu*omega = k = 4096, which
# makes mu a divisor of 4096 = 2^12. Every divisor of a power of two is a
# power of two, so mu can be 1, 2, 4, 8, 16, ... and NEVER 6. At mu=6 the
# block size would be omega = 4096/6 = 682.67 symbols, which is not an
# integer. This is a property of the blob size, not of the BC construction.
#
# mu=6 IS reachable if the code is allowed to span more than one blob, and
# that is not an artificial dodge -- PeerDAS carries many blobs per block. At
# three blobs, k = 12288 and mu=6 gives omega = 2048 exactly, with
# lambda=2, rho=omega: n = 24576, rate 0.5, n0 = 3*2048 = 6144, d = 4097.
# It is left out of THIS sweep only because every row here is pinned to the
# same single-blob k = 4096 so that the schemes stay comparable on identical
# input, which is the control the whole benchmark rests on. A multi-blob BC
# row would be a separate experiment with its own k, worth running on its own
# terms rather than smuggling a different message size into this table.

# Compute budget for the decoder's pairwise phase, applied identically to
# every variant.
#
# Phase 2 stacks two blocks' parity checks. That system is NOT Vandermonde,
# so unlike Phase 1 it cannot use the O(e^2) solver and needs full Gaussian
# elimination, whose cost grows as the CUBE of the unknown count e. Measured
# in this field's arithmetic, on the 512-equation systems omega=256 produces:
# e=276 takes 21.7s, e=369 takes 39.5s, e=461 takes 61.7s -- per pair, with mu
# pairs scanned per iteration, so 6 to 16 minutes per decoding round. At
# omega=1024 a full pair is 2048 equations in 2048 unknowns, about 80 minutes.
#
# The consequence is worth stating plainly rather than burying. Phase 2 only
# gets a turn when Phase 1 has stalled, and with lambda = mu Phase 1 stalls
# only once a support carries more than rho erasures. Every variant here has
# rho >= 256, so every pair that could possibly help carries more than 256
# unknowns. At this cap none of them qualify, and all three variants are
# therefore measured as SINGLE-PHASE decoders. Raising the cap enough to
# change that costs tens of minutes per decode attempt and days per sweep;
# what the pairwise phase would buy is measured separately, at one rate, and
# reported in docs/benchmark_1D_2D_BC_report.md rather than swept here.
#
# Pairs skipped by this cap are counted and their positions stay honestly
# flagged as erased. Nothing is guessed at.
BC_PAIR_UNKNOWN_CAP = 256

RATES = [0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.33,
         0.35, 0.38, 0.40, 0.45, 0.48, 0.50, 0.52, 0.55]
RNG_SEED = 20260827  # fixed seed -> reproducible sweep across runs

# Each scheme's OWN empirical transition point -- these are NOT all 0.50.
#
# Each scheme's OWN empirical transition point -- these are NOT all the same.
#
#   1D-RS   : n-k = k and RS is MDS, so it succeeds iff the drawn erasure
#             count is <= n-k. The transition sits exactly at 0.50.
#   2D-RS   : now 88x96 (see 2D_RS_Galois.py) for rate 0.485 -- the closest
#             reachable to 0.5 in this field, replacing the previous 88x88 at
#             rate 0.529. Per-line budgets are 88-64 = 24 down a column and
#             96-64 = 32 along a row, and the cross-axis cascade lifts the
#             grid as a whole above either.
#   BC-*    : a local block resolves the erasures landing in its own support
#             of n0 = rho + lambda*omega symbols while they number at most
#             rho, i.e. while the rate is below rho/n0 = 1/(1+lambda) when
#             rho = omega. That is 0.333 at lambda=2, 0.250 at lambda=3 and
#             0.200 at lambda=4, independent of mu. Whether the cascade then
#             carries the rest of the codeword depends on mu, which is what
#             the mu=4 and mu=8 rows at lambda=2 are there to separate.
SCHEME_BOUNDARY = {
    "1D-RS": 0.50,
    "2D-RS": 0.40,
    "BC-2048-L2": 0.333,
    "BC-1024-L2": 0.333,
    "BC-1024-L3": 0.250,
    "BC-1024-L4": 0.200,
    "BC-512-L2": 0.333,
}
BOUNDARY_RATE = SCHEME_BOUNDARY["1D-RS"]  # kept for the shared-mask sizing below


def trials_for(scheme_name, rate):
    """Trial count as a function of (scheme, rate) -- more trials near THAT
    SCHEME'S OWN transition, where binomial variance in the drawn erasure
    count can flip the outcome; fewer far from it, where the result is not in
    doubt and extra trials only cost runtime. 1D-RS stays the most
    conservative because its decode is the expensive one and its worst-case
    cost lands almost exactly on its own boundary."""
    dist = abs(rate - SCHEME_BOUNDARY.get(scheme_name, 0.50))
    if scheme_name == "1D-RS":
        if dist <= 0.03:
            return 3
        return 1 if rate <= 0.35 else 2
    if scheme_name == "2D-RS":
        return 5 if dist <= 0.05 else 3
    if scheme_name.startswith("BC"):
        # BC's recoverability is a per-trial probability rather than a
        # certainty, because whether any single block comes in under budget
        # depends on how the mask happens to fall. Counts are lower than they
        # would ideally be because the pairwise phase, where it runs at all,
        # costs tens of seconds per pair -- see BC_PAIR_UNKNOWN_CAP.
        return 8 if dist <= 0.06 else 4
    return 1


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

    def params(self):
        # RS is MDS, so d = n-k+1 and the worst-case tolerance is exactly
        # (d-1)/n = (n-k)/n = 1-R. Nothing is lost to the decoder here.
        return {"d_min": self.n - self.k + 1,
                "worst_case_tolerance": (self.n - self.k) / self.n}

    def component(self):
        """1D-RS has no component structure -- the global code IS the only
        code, so n0/k0 are just n/k. Recorded explicitly so the comparison
        table has a defined entry in every column rather than a blank."""
        return {"n0": self.n, "k0": self.k,
                "desc": f"[{self.n}, {self.k}] (no component structure)"}

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
    n = rs2d.EXT_ROWS * rs2d.EXT_COLS  # 8448 at the 88x96 setting

    def __init__(self):
        self.alpha_rows = rs2d.root_of_unity(rs2d.EXT_ROWS, P)
        self.alpha_cols = rs2d.root_of_unity(rs2d.EXT_COLS, P)

    def params(self):
        # A product code's minimum distance is the PRODUCT of its component
        # distances. Each component is RS (MDS), so d_row = 96-64+1 = 33 and
        # d_col = 88-64+1 = 25, giving d = 825 -- far below the Singleton
        # bound n-k+1 = 4353. A product code is never MDS, which is the
        # structural price it pays for two-axis locality.
        d_row = rs2d.EXT_COLS - rs2d.BLOB_COLS + 1
        d_col = rs2d.EXT_ROWS - rs2d.BLOB_ROWS + 1
        return {"ext_rows": rs2d.EXT_ROWS, "ext_cols": rs2d.EXT_COLS,
                "blob_rows": rs2d.BLOB_ROWS, "blob_cols": rs2d.BLOB_COLS,
                "d_row": d_row, "d_col": d_col, "d_min": d_row * d_col,
                "worst_case_tolerance": (d_row * d_col - 1) / self.n,
                "singleton_d_max": self.n - self.k + 1}

    def component(self):
        """Two component codes, one per axis, each an RS code on 64
        information symbols: [96, 64] along a row and [88, 64] down a
        column. The overall rate is their product, (64/96)*(64/88) = 0.485."""
        return {"n0": rs2d.EXT_COLS, "k0": rs2d.BLOB_COLS,
                "n0_col": rs2d.EXT_ROWS, "k0_col": rs2d.BLOB_ROWS,
                "desc": (f"[{rs2d.EXT_COLS}, {rs2d.BLOB_COLS}] row x "
                         f"[{rs2d.EXT_ROWS}, {rs2d.BLOB_ROWS}] col")}

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
    """One block-circulant parameterisation. Unlike the other two adapters
    this one is instantiated several times, once per (omega, rho, lambda)
    row being compared, so its shape lives on the instance rather than the
    class."""

    def __init__(self, omega, rho, lambda_, pair_unknown_cap=None):
        self.omega, self.rho, self.lambda_ = omega, rho, lambda_
        self.mu = K // omega
        assert self.mu * omega == K, \
            "BC parameters must span exactly one blob's worth of message symbols"
        assert lambda_ <= self.mu, "lambda > mu would repeat blocks in a support"
        self.k = K
        self.n = self.mu * (rho + omega)
        self.n0 = rho + lambda_ * omega     # local code length
        self.k0 = lambda_ * omega           # local code dimension
        self.d_min = lambda_ * rho + 1
        self.pair_unknown_cap = pair_unknown_cap
        # omega alone no longer identifies a row: three of them share
        # omega=1024 and differ only in lambda, which is the variable the
        # sweep is actually about.
        self.name = f"BC-{omega}-L{lambda_}"
        # No global parity-check matrix is built: the decoder regenerates the
        # local GRS rows it needs, so the (mu*rho) x n matrix -- 33.5 million
        # field elements -- is never materialised.
        self.h_build_time = 0.0

    def params(self):
        # Every quantity below matches the notation table in Sasidharan,
        # Viterbo & Feist, "Block Circulant Codes for Ethereum PeerDAS"
        # (ePrint 2026/708), Sec. 3.1 -- this implementation's definitions
        # were checked against it line by line:
        #     [n0, k0] = [lambda*omega + rho, lambda*omega]     <- paper
        #     [n,  k ] = [mu*(omega+rho),     mu*omega]         <- paper
        #     R  = omega/(omega+rho)                            <- paper
        #     S  = lambda*rho / (mu*(omega+rho))  = (d-1)/n     <- paper
        #     R0 = lambda*omega/(lambda*omega+rho) = k0/n0      <- paper
        #     S0 = rho/(lambda*omega+rho)          = rho/n0     <- paper
        # The paper's S is the "stopping rate" and is exactly the (D-1)/N
        # figure the supervisor gave for erasure tolerance. Its S0 is the
        # local code's stopping rate, which is the same quantity this file
        # calls the predicted local reach.
        return {"omega": self.omega, "rho": self.rho, "lambda": self.lambda_,
                "mu": self.mu, "n0": self.n0, "k0": self.k0,
                "d_min": self.d_min,
                "local_rate_R0": self.k0 / self.n0,
                # S = (d-1)/n: the largest erasure fraction this CODE survives
                # against any pattern whatsoever, adversarial ones included.
                # The paper establishes tolerable erasures = lambda*rho for
                # lambda = 2 and 3; the lambda=4 row below extrapolates that
                # formula past the range in which it was proved, so treat its
                # d_min as indicative and the measured column as the evidence.
                "worst_case_tolerance": (self.d_min - 1) / self.n,
                # S0 = rho/n0 = 1/(1+lambda) when rho = omega: the rate below
                # which a local support typically holds few enough erasures
                # for the single-block phase of DecCBC to resolve it.
                "predicted_local_reach": self.rho / self.n0,
                "pair_unknown_cap": self.pair_unknown_cap}

    def component(self):
        """The local (component) code: each block's rho parity checks act on
        a support of n0 = rho + lambda*omega symbols carrying k0 = lambda*omega
        information symbols."""
        return {"n0": self.n0, "k0": self.k0,
                "desc": f"[{self.n0}, {self.k0}] local, x{self.mu} blocks"}

    def encode(self, blob):
        m = GF(blob)
        return bc.encode_bc_structured(GF, m, self.mu, self.lambda_,
                                       self.omega, self.rho)

    def random_mask(self, rate, rng):
        return rng.random(self.n) < rate

    def corrupt(self, encoded, mask):
        out = encoded.copy()
        out[mask] = GF(0)
        return out

    def decode(self, corrupted, mask):
        # The NTT path is switched off deliberately, not left at its default.
        #
        # It is correct -- it recovers the blob exactly on every eligible
        # parameterisation -- but it is 7-23x slower than the Vandermonde
        # solver it falls back to, because roughly four fifths of it is a
        # schoolbook polynomial division rather than the transform. Leaving
        # it on would make every BC row in this sweep an order of magnitude
        # more expensive while measuring nothing new. See fft_benchmark.py
        # for the measurement and the NTT section of
        # docs/benchmark_1D_2D_BC_report.md for the reasoning.
        #
        # Flip either of these to True to measure the NTT path instead. When
        # the divmod is replaced with Newton iteration the trade flips and
        # phase 1 should be switched back on.
        t0 = time.time()
        recovered, remaining = bc.dec_cbc_2(
            None, corrupted, mask, self.mu, self.lambda_, self.omega, self.rho,
            pair_unknown_cap=self.pair_unknown_cap)
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


def wilson_ci(successes, n, z=1.96):
    """95% Wilson score confidence interval for a binomial proportion --
    unlike the naive successes/n +/- 1.96*sqrt(p(1-p)/n) normal
    approximation, it stays inside [0,1] and is well-behaved at n=1 and at
    p=0 or p=1, which the raw fractions in this sweep hit constantly (a
    lot of "0/1" and "10/10" results). Returns (low, high)."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    half_width = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)
    lo = (centre - half_width) / denom
    hi = (centre + half_width) / denom
    return (max(0.0, lo), min(1.0, hi))


def run_scheme(adapter, blob, app_bytes, rates, rng, trials_fn,
               shared_masks_by_rate=None):
    """trials_fn(scheme_name, rate) -> int trial count for that point (see
    trials_for()). shared_masks_by_rate: optional {rate: [mask, ...]} --
    when given, these exact masks are used instead of drawing fresh ones
    (used to give 1D-RS and BC the literal same erased positions per
    trial)."""
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
        n_trials = trials_fn(adapter.name, rate)
        successes = 0
        claimed_ok = 0          # decoder's OWN success signal, before verification
        silent_corruption = 0   # decoder claimed success but the bytes are wrong
        decode_times = []
        success_times = []      # decode times of byte-exact trials only
        n_erased_list = []
        success_list = []       # per-trial outcome, aligned with n_erased_list
        for trial_idx in range(n_trials):
            if shared_masks_by_rate is not None:
                mask = shared_masks_by_rate[rate][trial_idx]
            else:
                mask = adapter.random_mask(rate, rng)
            n_erased_list.append(int(np.sum(mask)))
            corrupted = adapter.corrupt(encoded, mask)
            recovered, ok, t_decode = adapter.decode(corrupted, mask)
            ok = bool(ok)
            exact = ok and blob_matches(adapter.extract_message(recovered), blob, app_bytes)
            decode_times.append(t_decode)
            if exact:
                success_times.append(t_decode)
            claimed_ok += ok
            silent_corruption += (ok and not exact)
            successes += exact
            success_list.append(bool(exact))
        mean_t = sum(decode_times) / len(decode_times)
        # A decode that bails out on the budget check costs ~0.0003s while a
        # real decode costs ~40s, so a mean across both describes no actual
        # trial. Report the success-only mean alongside it.
        mean_ok_t = (sum(success_times) / len(success_times)) if success_times else None
        mean_erased = sum(n_erased_list) / len(n_erased_list)
        ci_lo, ci_hi = wilson_ci(successes, n_trials)
        ok_t_str = f"{mean_ok_t:7.3f}s" if mean_ok_t is not None else "      --"
        print(f"  rate={rate:.2f}  erased(mean)={mean_erased:7.1f}/{adapter.n}  "
              f"decode(all)={mean_t:7.3f}s  decode(ok only)={ok_t_str}  "
              f"success={successes}/{n_trials}  claimed_ok={claimed_ok}/{n_trials}  "
              f"silent_corruption={silent_corruption}/{n_trials}  "
              f"95% CI=[{ci_lo:.2f},{ci_hi:.2f}]")
        results.append({
            "scheme": adapter.name, "rate": rate,
            "n_erased_mean": mean_erased, "n_erased_per_trial": n_erased_list,
            "n": adapter.n, "k": adapter.k, "trials": n_trials,
            "successes": successes, "success_rate": successes / n_trials,
            "success_rate_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
            "claimed_ok": claimed_ok,
            "silent_corruption": silent_corruption,
            "mean_decode_time_s": round(mean_t, 4),
            "mean_decode_time_success_only_s": (round(mean_ok_t, 4)
                                                if mean_ok_t is not None else None),
            "decode_times_s": [round(t, 4) for t in decode_times],
            # Per-trial outcome, aligned with n_erased_per_trial. The count
            # alone is not enough: for the non-MDS codes recovery depends on
            # where the erasures fall, not just how many there are, so the
            # outcome of an individual trial cannot be inferred from its
            # erasure count.
            "success_per_trial": success_list,
        })
    return {
        "scheme": adapter.name, "k": adapter.k, "n": adapter.n,
        "rate": adapter.k / adapter.n,
        "overhead": adapter.n / adapter.k, "encode_time_s": round(t_encode, 4),
        "setup_time_s": round(extra_setup, 4) if extra_setup is not None else 0.0,
        "params": adapter.params() if hasattr(adapter, "params") else {},
        "component": adapter.component() if hasattr(adapter, "component") else {},
        "trials": results,
    }


def _parse_args():
    """Argument parsing exists mainly so that --help is not destructive.

    This script previously took no arguments, so
    `python3 benchmark_1D_2D_BC.py --help` ignored the flag and started the
    full multi-hour sweep. Anyone asking what the script does got a sweep
    instead of an answer."""
    import argparse
    ap = argparse.ArgumentParser(
        description="Erasure sweep over 1D-RS, 2D-RS and five block-circulant "
                    "parameterisations. Writes benchmark_results.json. Takes "
                    "several hours; see --quick for a smoke test.")
    ap.add_argument("--quick", action="store_true",
                    help="three rates, one trial each -- verifies the pipeline "
                         "runs; NOT a result worth reporting")
    return ap.parse_args()


if __name__ == "__main__":
    _args = _parse_args()
    if _args.quick:
        RATES = [0.05, 0.20, 0.35]
        _orig_trials_for = trials_for
        trials_for = lambda *a, **k: 1
        print("QUICK MODE: three rates, one trial each. Smoke test only --\n"
              "these numbers are not a result.\n")

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

    adapters = [OneDAdapter(), TwoDAdapter()] + [
        BCAdapter(w, rho, lam, pair_unknown_cap=BC_PAIR_UNKNOWN_CAP)
        for (w, rho, lam) in BC_VARIANTS
    ]
    all_results = []

    # 1D-RS and every BC variant share n=8192: corrupt them at the literal
    # SAME positions per trial, not just the same rate, for the strictest
    # comparison differently-structured but equal-length codes can share.
    # 2D-RS has a different n (88*96 = 8448) so it draws its own masks at the
    # same RATE.
    shared_n = OneDAdapter.n
    shared_names = [a.name for a in adapters if a.n == shared_n]
    assert len(shared_names) > 1, "expected 1D-RS and the BC variants to share n"
    shared_masks = {
        rate: [(rng.random(shared_n) < rate)
               for _ in range(max(trials_for(nm, rate) for nm in shared_names))]
        for rate in RATES
    }

    for adapter in adapters:
        use_shared = adapter.n == shared_n
        result = run_scheme(adapter, blob, app_bytes, RATES, rng, trials_for,
                             shared_masks_by_rate=shared_masks if use_shared else None)
        all_results.append(result)

    print("\n" + "=" * 70)
    print(" SUMMARY")
    print("=" * 70)
    header = (f"{'scheme':<12} {'k':>6} {'n':>7} {'rate':>6} {'overhead':>9} "
              f"{'N0':>6} {'K0':>6} {'d_min':>7} {'(d-1)/n':>8} {'encode(s)':>10}")
    print(header)
    for r in all_results:
        comp, prm = r.get("component", {}), r.get("params", {})
        n0 = comp.get("n0", "-")
        k0 = comp.get("k0", "-")
        dmin = prm.get("d_min", "-")
        wct = prm.get("worst_case_tolerance")
        wct_s = f"{wct:.3f}" if wct is not None else "-"
        print(f"{r['scheme']:<12} {r['k']:>6} {r['n']:>7} {r['rate']:>6.3f} "
              f"{r['overhead']:>8.2f}x {str(n0):>6} {str(k0):>6} {str(dmin):>7} "
              f"{wct_s:>8} {r['encode_time_s']:>10.3f}")

    print("\nComponent (local) codes -- N0/K0 above, in full:")
    for r in all_results:
        desc = r.get("component", {}).get("desc", "-")
        prm = r.get("params", {})
        extra = ""
        if "predicted_local_reach" in prm:
            extra = (f"   lambda={prm['lambda']} mu={prm['mu']}  "
                     f"predicted local reach rho/N0 = {prm['predicted_local_reach']:.3f}")
        print(f"  {r['scheme']:<12} {desc}{extra}")

    print(f"\nMean decode time per rate:")
    print(f"{'scheme':<12} " + " ".join(f"rate={r:.2f}".rjust(14) for r in RATES))
    for r in all_results:
        row = [r["scheme"].ljust(12)]
        for t in r["trials"]:
            row.append(f"{t['mean_decode_time_s']:>7.3f}s".rjust(14))
        print(" ".join(row))

    print(f"\nSuccess rate per rate (successes/trials, 95% Wilson CI):")
    print(f"{'scheme':<12} " + " ".join(f"rate={r:.2f}".rjust(14) for r in RATES))
    for r in all_results:
        row = [r["scheme"].ljust(12)]
        for t in r["trials"]:
            row.append(f"{t['successes']}/{t['trials']}".rjust(14))
        print(" ".join(row))
    print(f"\n(95% CI widths shrink toward 0 as trial counts rise near the")
    print(f" boundary band -- see trials_for() and success_rate_ci95 in the JSON)")

    out_path = os.path.join(HERE, "benchmark_results.json")
    with open(out_path, "w") as f:
        json.dump({"rates": RATES, "seed": RNG_SEED,
                    "boundary_rate": BOUNDARY_RATE,
                    "bc_pair_unknown_cap": BC_PAIR_UNKNOWN_CAP,
                    "results": all_results},
                   f, indent=2)
    print(f"\nFull results written to {out_path}")
