"""
2D Reed-Solomon product code at real Ethereum blob scale.

    pip install galois

Requires blob_generator.py in the same directory -- input data comes
from real application bytes, packed into blob(s) via
bg.bytes_to_blobs() using the ACTUAL EIP-4844 packing convention (31
usable bytes per 32-byte field element), not a hardcoded message and
not raw unstructured field elements.

This version fixes two things the earlier blob-scale version got
wrong relative to the real standard, and one thing it under-tested:

  1. EVALUATION-FORM DATA, NOT COEFFICIENT-FORM. Per EIP-4844 /
     consensus-specs, a blob's field elements ARE the evaluations of a
     degree-<4096 polynomial at the 4096th roots of unity (this is
     exactly why KZG can commit to a blob directly against a
     Lagrange-basis SRS, with no FFT at commitment time). The earlier
     version treated the raw packed bytes as polynomial COEFFICIENTS
     and NTT'd them directly to "extend" -- that skips the
     interpolation step entirely and doesn't correspond to what real
     PeerDAS extension does. This version treats each row/column of
     the blob grid as evaluations, and extension is genuinely
     interpolate-then-evaluate-on-a-bigger-domain:
         a. INTT the k known evaluations -> coefficients (degree < k).
         b. Zero-pad coefficients to n.
         c. NTT -> the n evaluations of the SAME polynomial at the
            extended domain -- this is the actual FFT-based erasure
            code extension referenced at
            https://ethresear.ch/t/reed-solomon-erasure-code-recovery-in-n-log-2-n-time-with-ffts/3039
     See interpolate_then_extend() / restrict() below.

  2. BIT-REVERSAL PERMUTED DOMAIN ORDERING. consensus-specs orders the
     evaluation domain via bit_reversal_permutation(): grid slot i
     corresponds to domain point alpha^(bitreverse(i)), not alpha^i.
     This was flagged as an unaddressed gap in the earlier version; it
     doesn't change WHICH erasure patterns are recoverable (that's
     invariant under any consistent relabeling), but it does change
     which literal row/column a given domain point lands in, which is
     what standards-conformance actually requires. See
     bit_reversal_permutation() / bitreverse_permute() below.

  3. ITERATIVE, PER-LINE, MASK-BASED DECODING (the real fix to
     "recovery is not done correctly"). The earlier version ran
     EXACTLY two passes (one vertical, one horizontal), each assuming
     every line in that pass shared the SAME fixed erasure positions
     (i.e. it only ever modelled "a few whole rows/columns erased").
     That is a special case, not what 2D-RS product-code decoding
     actually does or what makes it stronger than 1D-RS: a real
     product-code decoder tracks erasures cell-by-cell and alternates
     passes until convergence, because a cell that neither axis alone
     could recover in round 1 often becomes recoverable once its
     partner axis fills in other cells in round 2. This version:
         - represents erasures as a per-cell boolean mask (so it can
           model arbitrary/random adversarial sampling patterns, not
           just whole-row/whole-column wipes),
         - builds each line's erasure-locator polynomial from THAT
           line's own currently-erased cells (lines that happen to
           share a pattern -- e.g. the whole-row/whole-column case --
           still share one locator via a cache, so the common case
           isn't slowed down),
         - loops alternating vertical/horizontal passes until no
           erasures remain or a full round makes no further progress
           (and reports failure honestly in the latter case, instead
           of silently assuming 2 passes were always enough).
     See decode_pass() / decode_iterative() below.

WHAT'S STILL A SIMPLIFICATION (this stays a coding-scheme simulation,
not a full protocol implementation):
  - Doubling BOTH axes gives 4x total overhead (128x128 / 64x64), not
    PeerDAS's 2x total. Matching PeerDAS's 2x total exactly needs
    non-power-of-two per-axis sizes, which complicates clean NTT use.
    Explicit design choice -- worth reporting as its own datapoint
    against 1D-RS's 2x in the comparison, not an oversight.
  - Recovering a line's coefficients from the locator-multiplied
    product (dividing out Z(x)) is done via ordinary polynomial long
    division, not a Newton-iteration power-series inversion. Encode is
    a clean O(n log n) via NTT either way; per-line decode is O(n log
    n) for the NTT/INTT calls plus that division's cost -- not the
    fully NTT-based O(n log^2 n) erasure decoder real systems can use,
    but a genuine FFT-based erasure decoder (multiply-by-locator +
    INTT + divide + re-NTT), not O(k^3) matrix inversion.
  - This models an erasure channel only (missing samples), not
    arbitrary symbol errors -- matches how PeerDAS samples are used
    (a peer either returns a sample or doesn't), and matches the
    NTT-erasure-decode technique this file implements, which corrects
    erasures, not errors.
"""

import os
import galois
import numpy as np
import time
import blob_generator as bg

def preview(matrix, label, size=6):
    """Full matrices are too large to print at this scale (128x128 = 16384
    cells) -- show a small corner instead, truncated to 16 bits for
    readability (each real value is a ~255-bit field element)."""
    print(f"\n--- {label} (full shape: {matrix.shape[0]}x{matrix.shape[1]}, "
          f"showing top-left {size}x{size}) ---")
    for r in range(min(size, matrix.shape[0])):
        cells = [f"{int(v) & 0xFFFF:04x}" for v in matrix[r, :size]]
        print(f"  row {r:02d}: [ {' '.join(cells)} ]")

# ---------------------------------------------------------------------------
# FIELD: BLS12-381 scalar field (Fr)
# ---------------------------------------------------------------------------
P = 52435875175126190479447740508185965837690552500527637822603658699938581184513
GF = galois.GF(P)

# ---------------------------------------------------------------------------
# BLOB / GRID SIZING (reused from blob_generator so both files agree)
# ---------------------------------------------------------------------------
FIELD_ELEMENTS_PER_BLOB = bg.FIELD_ELEMENTS_PER_BLOB   # 4096
BLOB_ROWS, BLOB_COLS = 64, 64          # 64 * 64 = 4096
# ---------------------------------------------------------------------------
# COMPONENT CODE RATE
# ---------------------------------------------------------------------------
# A product code's overall rate is the PRODUCT of its two component rates,
# so the extension factor per axis is what sets total overhead.
#
# Doubling both axes (the previous 64->128 setting) gives component rate 1/2
# on each axis and therefore overall rate 1/4, i.e. 4x storage overhead --
# twice what 1D-RS and BC spend, which made the erasure-rate comparison
# unfair in 2D-RS's favour.
#
# WHY EXACTLY RATE 0.5 IS NOT REACHABLE HERE:
# overall rate = k / (EXT_ROWS * EXT_COLS) = 4096 / (EXT_ROWS * EXT_COLS),
# so rate 0.5 requires EXT_ROWS * EXT_COLS = 8192 = 2^13. A product equal to
# a power of two forces BOTH factors to be powers of two; each axis must at
# least double for that axis to carry any parity at all, so the product is at
# least 4 * 4096 = 16384 > 8192. No genuine 2D product code on a 4096-element
# blob can have rate 0.5. This is a property of product codes, not of this
# implementation.
#
# The nearest reachable point uses 88 = 8 * 11 per axis. 11 divides p-1 for
# the BLS12-381 scalar field, so a length-88 NTT exists:
#     component rate  64/88 = 8/11 = 0.727 on each axis
#     overall rate    4096/7744      = 0.529
#     overhead        7744/4096      = 1.89x   (vs 2.00x for 1D-RS and BC)
EXT_ROWS = 88
EXT_COLS = 88

for n in (BLOB_ROWS, BLOB_COLS, EXT_ROWS, EXT_COLS):
    assert (P - 1) % n == 0, f"P-1 must be divisible by {n} for an NTT of that size"

# ---------------------------------------------------------------------------
# BIT-REVERSAL PERMUTED DOMAIN ORDERING (consensus-specs convention)
# ---------------------------------------------------------------------------
def bit_reversal_permutation(n):
    """perm[i] = bit-reversal of i over log2(n) bits. Grid slot i
    corresponds to domain point alpha_n^perm[i], matching
    consensus-specs' bit_reversal_permutation() over the roots of
    unity. This permutation is its own inverse (bit-reversal twice is
    the identity), which is what lets bitreverse_permute() below do
    both cell-order->natural-order and natural-order->cell-order with
    the same code."""
    bits = n.bit_length() - 1
    if (1 << bits) != n:
        # Bit-reversal is only defined for power-of-two lengths. It is a
        # domain ORDERING convention (consensus-specs' cell order), not a
        # mathematical requirement of the transform, so for the non-power-of-
        # two axis lengths used above we fall back to natural NTT order:
        # grid slot i corresponds to domain point alpha^i directly. Every
        # caller treats this array purely as an index map, so the identity
        # permutation is a valid -- and still self-inverse -- choice.
        return list(range(n))
    return [int(format(i, f"0{bits}b")[::-1], 2) for i in range(n)]

def bitreverse_permute(values, brp):
    """Self-inverse: applying this twice returns the original values.
    Converts a grid-slot-ordered array to natural NTT-domain order
    (index j -> alpha^j), or a natural-order array back to grid-slot
    order -- same operation either direction."""
    return [values[brp[i]] for i in range(len(values))]

BRP_BLOB_ROWS = bit_reversal_permutation(BLOB_ROWS)
BRP_BLOB_COLS = bit_reversal_permutation(BLOB_COLS)
BRP_EXT_ROWS = bit_reversal_permutation(EXT_ROWS)
BRP_EXT_COLS = bit_reversal_permutation(EXT_COLS)

def root_of_unity(n, p):
    g = galois.primitive_root(p)
    a = pow(g, (p - 1) // n, p)
    assert pow(a, n, p) == 1 and pow(a, n // 2, p) != 1
    return a

# ---------------------------------------------------------------------------
# ENCODE: interpolate (from evaluations) then extend (evaluate on a
# bigger domain) -- the real FFT-based RS extension, not raw NTT of
# the data as if it were already coefficients.
# ---------------------------------------------------------------------------
def evals_from_coeffs(coeffs, n, brp_n, p):
    """Zero-pad ascending coefficients to n and evaluate via NTT
    (natural order), then reorder into grid-slot order."""
    padded = [int(c) for c in coeffs] + [0] * (n - len(coeffs))
    natural = [int(v) for v in galois.ntt(padded, size=n, modulus=p)]
    return bitreverse_permute(natural, brp_n)

def interpolate_then_extend(evals_cellorder_k, k, n, brp_k, brp_n, p):
    """evals_cellorder_k: k values in grid-slot order, i.e. the real
    Ethereum representation of a degree-<k polynomial (blob field
    elements ARE evaluations). Returns n evaluations (grid-slot order)
    of that SAME polynomial on the extended domain."""
    natural_k = bitreverse_permute([int(v) for v in evals_cellorder_k], brp_k)
    coeffs = [int(v) for v in galois.intt(natural_k, size=k, modulus=p)]
    return evals_from_coeffs(coeffs, n, brp_n, p)

def restrict(evals_cellorder_n, k, n, brp_k, brp_n, p):
    """Inverse of interpolate_then_extend: given n evaluations
    (grid-slot order) of a polynomial known to have degree < k,
    recover the original k evaluations (grid-slot order) at the
    size-k domain."""
    natural_n = bitreverse_permute([int(v) for v in evals_cellorder_n], brp_n)
    coeffs_n = [int(v) for v in galois.intt(natural_n, size=n, modulus=p)]
    coeffs_k = coeffs_n[:k]
    natural_k = [int(v) for v in galois.ntt(coeffs_k, size=k, modulus=p)]
    return bitreverse_permute(natural_k, brp_k)

def encode_blob(data_matrix):
    row_ext = np.array(
        [interpolate_then_extend(data_matrix[r, :], BLOB_COLS, EXT_COLS,
                                  BRP_BLOB_COLS, BRP_EXT_COLS, P)
         for r in range(BLOB_ROWS)],
        dtype=object,
    )  # (BLOB_ROWS, EXT_COLS)
    col_ext = np.array(
        [interpolate_then_extend(row_ext[:, c], BLOB_ROWS, EXT_ROWS,
                                  BRP_BLOB_ROWS, BRP_EXT_ROWS, P)
         for c in range(EXT_COLS)],
        dtype=object,
    ).T  # (EXT_COLS, BLOB_ROWS) stacked, then .T -> (EXT_ROWS, EXT_COLS)
    return col_ext

# ---------------------------------------------------------------------------
# DECODE: NTT-based erasure decoding, iterated to convergence, with a
# per-cell erasure mask instead of a fixed shared erasure pattern.
# ---------------------------------------------------------------------------
def build_erasure_locator(erased_cells, n, k, alpha, brp_n, p):
    """erased_cells: grid-slot indices (0..n-1) erased in ONE line.
    Returns (Z_poly, Z_evals_natural) where Z is monic with a root at
    the domain point for every erased cell, and Z_evals_natural[j] =
    Z(alpha^j) in NATURAL NTT order (matching the natural-order
    received line used in recover_line_ntt). Returns (None, None) if
    there are more erasures than this axis's redundancy (n - k) can
    resolve alone -- the other axis, or a later round, is expected to
    help first."""
    if len(erased_cells) > n - k:
        return None, None
    Z_poly = galois.Poly([1], field=GF)
    for i in erased_cells:
        domain_exp = brp_n[i]
        root = pow(alpha, domain_exp, p)
        factor = galois.Poly([1, (-root) % p], field=GF)  # (x - root)
        Z_poly = Z_poly * factor
    Z_coeffs_asc = list(reversed([int(c) for c in Z_poly.coeffs]))
    Z_padded = Z_coeffs_asc + [0] * (n - len(Z_coeffs_asc))
    Z_evals_natural = [int(v) for v in galois.ntt(Z_padded, size=n, modulus=p)]
    return Z_poly, Z_evals_natural

def recover_line_ntt(received_cellorder, Z_poly, Z_evals_natural, n, k, brp_n, p, label=""):
    """Recover one erased line (erased cells already zeroed): multiply
    by the locator's evaluations (natural order), inverse-NTT, divide
    out the locator polynomial to get the true degree-<k coefficients,
    then re-evaluate (NTT) on the full n-domain to fill in the line."""
    R_natural = bitreverse_permute([int(v) for v in received_cellorder], brp_n)
    G_evals = [(R_natural[j] * Z_evals_natural[j]) % p for j in range(n)]
    prod_coeffs_asc = [int(v) for v in galois.intt(G_evals, size=n, modulus=p)]

    Prod_poly = galois.Poly(list(reversed(prod_coeffs_asc)), field=GF)
    quotient = Prod_poly // Z_poly
    remainder = Prod_poly % Z_poly
    rem_coeffs = [int(c) for c in remainder.coeffs]
    if any(c != 0 for c in rem_coeffs):
        print(f"  [{label}] WARNING: nonzero remainder recovering a line -- "
              f"erasure pattern may exceed this pass's recoverable budget")

    coeffs_desc = [int(c) for c in quotient.coeffs]
    coeffs_asc = list(reversed(coeffs_desc))
    if len(coeffs_asc) < k:
        coeffs_asc = coeffs_asc + [0] * (k - len(coeffs_asc))
    else:
        coeffs_asc = coeffs_asc[:k]

    return evals_from_coeffs(coeffs_asc, n, brp_n, p)

def decode_pass(grid, mask, axis, k, n, alpha, brp_n, p, label=""):
    """One pass along `axis` (0 = down columns, recovering erased rows;
    1 = along rows, recovering erased columns). Each line's
    erasure-locator polynomial is built from THAT line's own
    currently-erased cells (read from `mask`), not a single pattern
    assumed shared by every line -- necessary once erasures come from
    a random adversarial sampling pattern rather than a few whole
    rows/columns. Lines that share an identical erasure pattern (the
    common whole-row/whole-column case) still share one locator via a
    cache, so that case isn't slowed down by the generalisation."""
    out_grid = grid.copy()
    out_mask = mask.copy()
    n_lines = grid.shape[1] if axis == 0 else grid.shape[0]
    locator_cache = {}
    recovered_count = 0
    stuck_lines = 0
    t0 = time.time()
    for i in range(n_lines):
        line_mask = mask[:, i] if axis == 0 else mask[i, :]
        erased_cells = tuple(int(j) for j in np.nonzero(line_mask)[0])
        if not erased_cells:
            continue
        if erased_cells not in locator_cache:
            locator_cache[erased_cells] = build_erasure_locator(
                list(erased_cells), n, k, alpha, brp_n, p)
        Z_poly, Z_evals = locator_cache[erased_cells]
        if Z_poly is None:
            stuck_lines += 1
            continue
        line = grid[:, i] if axis == 0 else grid[i, :]
        fixed = recover_line_ntt(line, Z_poly, Z_evals, n, k, brp_n, p, label=label)
        if axis == 0:
            out_grid[:, i] = fixed
            out_mask[:, i] = False
        else:
            out_grid[i, :] = fixed
            out_mask[i, :] = False
        recovered_count += 1
    t_total = time.time() - t0
    print(f"  [{label}] {recovered_count}/{n_lines} lines recovered "
          f"({len(locator_cache)} distinct erasure pattern(s) seen), "
          f"{stuck_lines} line(s) exceeded this axis's budget alone, "
          f"{t_total:.3f}s")
    return out_grid, out_mask, recovered_count

def decode_iterative(corrupted, mask, k_rows, k_cols, n_rows, n_cols,
                      alpha_rows, alpha_cols, brp_rows, brp_cols, p,
                      max_rounds=20):
    """Alternates vertical/horizontal passes -- NOT a fixed two-pass
    schedule -- until every erasure is resolved or a full round makes
    no further progress. This is what actually gives a 2D product code
    its erasure-correcting strength beyond what either axis's own
    n-k budget could resolve alone: a cell neither axis could fix in
    round 1 often becomes fixable once its partner axis fills in
    other cells in round 2+."""
    grid = corrupted.copy()
    round_no = 0
    while mask.any() and round_no < max_rounds:
        round_no += 1
        grid, mask, fixed_v = decode_pass(
            grid, mask, axis=0, k=k_rows, n=n_rows, alpha=alpha_rows,
            brp_n=brp_rows, p=p, label=f"round {round_no}: vertical")
        grid, mask, fixed_h = decode_pass(
            grid, mask, axis=1, k=k_cols, n=n_cols, alpha=alpha_cols,
            brp_n=brp_cols, p=p, label=f"round {round_no}: horizontal")
        if fixed_v == 0 and fixed_h == 0:
            print(f"  round {round_no}: no progress made -- decoding stuck, "
                  f"{int(mask.sum())} cell(s) still unrecovered")
            break
    if mask.any():
        print(f"  DECODE FAILED: {int(mask.sum())} cell(s) remain erased "
              f"after {round_no} round(s)")
    else:
        print(f"  decode converged after {round_no} round(s)")
    return grid, mask

def random_erasure_mask(n_rows, n_cols, rate, rng):
    """A per-cell adversarial sampling pattern: each cell independently
    withheld with probability `rate` -- the general case the earlier
    version's whole-row/whole-column-only model couldn't represent."""
    return rng.random((n_rows, n_cols)) < rate

# ---------------------------------------------------------------------------
# DEMO RUN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print(" 2D REED-SOLOMON PRODUCT CODE -- BLOB SCALE, NTT ENCODE + DECODE")
    print("=" * 70)

    print(f"\nGenerating real application bytes and packing them into a blob "
          f"the actual EIP-4844 way: {bg.USABLE_BYTES_PER_FIELD_ELEMENT} usable "
          f"bytes per {bg.BYTES_PER_FIELD_ELEMENT}-byte field element "
          f"({bg.USABLE_BYTES_PER_BLOB} usable bytes/blob), "
          f"via bg.bytes_to_blobs() -- not raw random field elements.")
    app_bytes = os.urandom(bg.USABLE_BYTES_PER_BLOB)  # exactly one blob's worth
    random_blob = bg.bytes_to_blobs(app_bytes)[0]
    bg.validate_blob(random_blob)
    data_matrix = np.array(random_blob, dtype=object).reshape(BLOB_ROWS, BLOB_COLS)
    print(f"  packed {len(app_bytes)} application bytes into "
          f"{len(random_blob)} field elements, reshaped to "
          f"{BLOB_ROWS}x{BLOB_COLS}. Per EIP-4844, these ARE the "
          f"evaluations of the blob's polynomial (grid-slot order, "
          f"bit-reversal permuted domain) -- not coefficients.")
    preview(data_matrix, "STEP 1: blob grid (real packed bytes, evaluation form)")

    print("\n--- STEP 2: ENCODING (interpolate + NTT-extend, row then column) ---")
    t0 = time.time()
    row_ext = np.array(
        [interpolate_then_extend(data_matrix[r, :], BLOB_COLS, EXT_COLS,
                                  BRP_BLOB_COLS, BRP_EXT_COLS, P)
         for r in range(BLOB_ROWS)],
        dtype=object,
    )
    t_row = time.time() - t0
    print(f"  row extension: 64 interpolate+NTT of size {EXT_COLS}, {t_row:.3f}s "
          f"({BLOB_ROWS} rows x {EXT_COLS} cols = {row_ext.size} evaluations)")
    preview(row_ext, "row-extended grid (64x128, all evaluation-form now)")

    t0 = time.time()
    col_ext = np.array(
        [interpolate_then_extend(row_ext[:, c], BLOB_ROWS, EXT_ROWS,
                                  BRP_BLOB_ROWS, BRP_EXT_ROWS, P)
         for c in range(EXT_COLS)],
        dtype=object,
    ).T
    t_col = time.time() - t0
    print(f"\n  column extension: {EXT_COLS} interpolate+NTT of size {EXT_ROWS}, "
          f"{t_col:.3f}s ({EXT_ROWS} rows x {EXT_COLS} cols = {col_ext.size} evaluations)")
    encoded_grid = col_ext
    preview(encoded_grid, "STEP 3: full encoded grid (128x128, the codeword)")
    print(f"\n  total encode time: {t_row + t_col:.3f}s, "
          f"overhead: {EXT_ROWS * EXT_COLS / (BLOB_ROWS * BLOB_COLS):.2f}x "
          f"({BLOB_ROWS*BLOB_COLS} -> {EXT_ROWS*EXT_COLS} field elements)")

    alpha_cols = root_of_unity(EXT_COLS, P)
    alpha_rows = root_of_unity(EXT_ROWS, P)

    print("\n--- STEP 4: CORRUPTION (simulating peers not responding) ---")
    erased_rows = [1, 4]
    erased_cols = [7]
    mask = np.zeros((EXT_ROWS, EXT_COLS), dtype=bool)
    mask[erased_rows, :] = True
    mask[:, erased_cols] = True
    corrupted = encoded_grid.copy()
    corrupted[mask] = 0
    print(f"  erased rows:    {erased_rows} (2 of {EXT_ROWS} -- "
          f"budget is {EXT_ROWS - BLOB_ROWS} per column, plenty of room)")
    print(f"  erased columns: {erased_cols} (1 of {EXT_COLS} -- "
          f"budget is {EXT_COLS - BLOB_COLS} per row, plenty of room)")
    preview(corrupted, "corrupted grid")

    print("\n--- STEP 5: ITERATIVE DECODING (mask-based, alternating passes to convergence) ---")
    recovered, final_mask = decode_iterative(
        corrupted, mask, k_rows=BLOB_ROWS, k_cols=BLOB_COLS,
        n_rows=EXT_ROWS, n_cols=EXT_COLS, alpha_rows=alpha_rows,
        alpha_cols=alpha_cols, brp_rows=BRP_EXT_ROWS, brp_cols=BRP_EXT_COLS, p=P)
    preview(recovered, "after iterative decoding (should match STEP 3 exactly)")

    print("\n--- STEP 6: EXTRACTION (restrict back to the original k-domain, both stages) ---")
    t0 = time.time()

    # encode_blob ran in two stages: row-extend then column-extend, so each
    # cell of `recovered` is a genuine 2D mix of the original data. Undoing
    # this requires two restrict() calls, in reverse order of how encoding
    # ran -- each one inverse-NTTs, truncates to the known-degree-<k
    # coefficients, and re-evaluates on the smaller k-domain (NOT just an
    # inverse-NTT-and-truncate, since the recovered values are evaluations,
    # not coefficients).
    row_ext_recovered = np.array(
        [restrict(recovered[:, c], BLOB_ROWS, EXT_ROWS, BRP_BLOB_ROWS, BRP_EXT_ROWS, P)
         for c in range(EXT_COLS)],
        dtype=object,
    ).T  # (EXT_COLS, BLOB_ROWS) stacked, then .T -> (BLOB_ROWS, EXT_COLS)

    data_out = np.array(
        [restrict(row_ext_recovered[r, :], BLOB_COLS, EXT_COLS, BRP_BLOB_COLS, BRP_EXT_COLS, P)
         for r in range(BLOB_ROWS)],
        dtype=object,
    )
    t_extract = time.time() - t0
    print(f"  stage A (restrict, undo column-extension) + "
          f"stage B (restrict, undo row-extension): {t_extract:.3f}s")

    grid_match = bool(np.array_equal(np.array(encoded_grid, dtype=object),
                                      np.array(recovered, dtype=object)))
    data_match = bool(np.array_equal(np.array(data_matrix, dtype=object),
                                      np.array(data_out, dtype=object)))

    print("\n--- STEP 7: REAL-WORLD ROUND TRIP (recovered blob -> application bytes) ---")
    recovered_blob = [int(v) for v in data_out.reshape(-1)]
    bg.validate_blob(recovered_blob)
    recovered_bytes = bg.blob_to_bytes(recovered_blob)
    bytes_match = recovered_bytes == app_bytes
    print(f"  unpacked {len(recovered_bytes)} bytes via bg.blob_to_bytes(); "
          f"matches original application bytes: {bytes_match}")

    print("\n--- STEP 8: RANDOM ADVERSARIAL SAMPLING TRIAL (per-cell erasure mask) ---")
    print("  Demonstrates the iterative mask-based decoder recovering a pattern the")
    print("  earlier fixed-two-pass version couldn't even represent (erasures scattered")
    print("  across many distinct rows/columns rather than a few whole ones), and")
    print("  reports the empirical timing/round-count -- exactly the Phase 3")
    print("  methodology of testing under varying adversarial sampling rates.")
    rng = np.random.default_rng()
    for rate in (0.15, 0.35):
        trial_mask = random_erasure_mask(EXT_ROWS, EXT_COLS, rate, rng)
        trial_corrupted = encoded_grid.copy()
        trial_corrupted[trial_mask] = 0
        n_erased = int(trial_mask.sum())
        print(f"\n  -- rate={rate:.2f}: {n_erased}/{EXT_ROWS*EXT_COLS} cells erased --")
        t0 = time.time()
        trial_recovered, trial_final_mask = decode_iterative(
            trial_corrupted, trial_mask, k_rows=BLOB_ROWS, k_cols=BLOB_COLS,
            n_rows=EXT_ROWS, n_cols=EXT_COLS, alpha_rows=alpha_rows,
            alpha_cols=alpha_cols, brp_rows=BRP_EXT_ROWS, brp_cols=BRP_EXT_COLS, p=P)
        t_trial = time.time() - t0
        trial_match = bool(np.array_equal(np.array(encoded_grid, dtype=object),
                                           np.array(trial_recovered, dtype=object)))
        print(f"  rate={rate:.2f}: fully recovered={trial_match}, decode time={t_trial:.3f}s")

    print("\n" + "=" * 70)
    print(" RESULTS")
    print("=" * 70)
    print(f"Full encoded grid recovered exactly: {grid_match}")
    print(f"Original blob data recovered exactly: {data_match}  "
          f"({FIELD_ELEMENTS_PER_BLOB} field elements checked)")
    print(f"Original application bytes recovered exactly: {bytes_match}  "
          f"({len(app_bytes)} bytes checked)")
    print(f"\nTiming summary: encode {t_row + t_col:.3f}s, "
          f"extract {t_extract:.3f}s (see per-pass/per-round lines above for decode)")
