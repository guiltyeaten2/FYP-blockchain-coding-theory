"""
2D Reed-Solomon product code at real Ethereum blob scale.

    pip install galois

Requires blob_generator.py in the same directory -- input data comes
from real application bytes, packed into blob(s) via
bg.bytes_to_blobs() using the ACTUAL EIP-4844 packing convention (31
usable bytes per 32-byte field element), not a hardcoded message and
not raw unstructured field elements.

Compared to the earlier small demo, this version:
  - Sizes the grid to Ethereum's actual FIELD_ELEMENTS_PER_BLOB = 4096
    (64x64), instead of an arbitrary 4x6.
  - Chunks arbitrary-length input into as many 4096-element blobs as
    needed, instead of assuming everything fits in one hardcoded matrix.
  - Packs real application bytes at the real 31-bytes-per-element rate
    (bg.bytes_to_blobs), instead of using raw random field elements as
    stand-in data.
  - Encodes via NTT (galois.ntt), matching the O(n log n) mechanism
    real PeerDAS extension uses, instead of O(n*k) evaluation.
  - Decodes via NTT-based erasure decoding (the same FFT erasure-code
    recovery technique PeerDAS-style systems use -- see e.g.
    https://ethresear.ch/t/reed-solomon-erasure-code-recovery-in-n-log-2-n-time-with-ffts/3039),
    instead of classical Gaussian-elimination matrix inversion. Concretely,
    per pass (all lines in a pass share the same erasure positions, so
    the erasure-locator polynomial and its NTT are built ONCE and reused
    for every row/column in that pass):
        1. Build the erasure-locator polynomial Z(x), which is exactly
           zero at every erased evaluation point, via ordinary
           polynomial multiplication of monic linear factors (cheap:
           degree = number of erasures).
        2. NTT-evaluate Z(x) at all n points (galois.ntt) -- O(n log n).
        3. For each line: multiply the received values (erasures already
           zero) by Z's evaluations, POINTWISE -- this is an O(n) step
           that stands in for the convolution "received(x) * Z(x)".
        4. Inverse-NTT (galois.intt) that product back to coefficient
           form -- O(n log n). Because Z vanishes exactly at the erased
           points, this recovers the TRUE coefficients of
           original_poly(x) * Z(x) with no aliasing (its degree is
           always < n).
        5. Divide that product by Z(x) (polynomial division) to recover
           original_poly(x) directly -- this step is the one part of
           decode that is NOT NTT-based here (see below).
        6. Re-encode via NTT to fill in the full line, same as step 1
           of encoding.
  - Recovers the final blob purely via inverse NTT (galois.intt) rather
    than by inverting a Vandermonde matrix, since by the time
    extraction runs, every erasure has already been filled in by the
    decode passes above.

WHAT'S STILL A SIMPLIFICATION:
  - Real spec applies a bit-reversal permutation to the evaluation
    domain ordering; this version uses natural order. That matters for
    exactly which "half" of extended data maps to which peer/subnet in
    real PeerDAS, but doesn't affect whether recovery works.
  - Step 5 above (dividing the recovered product polynomial by the
    erasure-locator polynomial) is done via ordinary polynomial long
    division, not a Newton-iteration-based power-series inversion.
    That means encode is a clean O(n log n) via NTT, and decode is
    O(n log n) for the NTT/INTT calls plus the cost of that division
    per line -- NOT the fully NTT-based O(n log^2 n) erasure decoder
    real systems can use, but it is a genuine FFT-based erasure
    decoder (multiply-by-locator + INTT + divide + re-NTT), not the
    O(k^3)-matrix-inversion approach from the earlier version.
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
AXIS_EXPANSION = 2                     # each axis doubled independently
EXT_ROWS = BLOB_ROWS * AXIS_EXPANSION  # 128
EXT_COLS = BLOB_COLS * AXIS_EXPANSION  # 128
# NOTE: doubling BOTH axes gives 4x total overhead (128*128 / 64*64),
# not PeerDAS's 2x total. Matching PeerDAS's 2x total exactly would need
# non-power-of-two per-axis sizes, which complicates clean NTT use. This
# is the "2x per axis / 4x total" tradeoff flagged earlier -- explicit
# design choice, not an oversight. Worth reporting as its own datapoint
# against 1D-RS's 2x in your comparison.

for n in (BLOB_ROWS, BLOB_COLS, EXT_ROWS, EXT_COLS):
    assert (P - 1) % n == 0, f"P-1 must be divisible by {n} for an NTT of that size"

# ---------------------------------------------------------------------------
# ENCODE: NTT-based line extension
# ---------------------------------------------------------------------------
def encode_line(data_line, n_out):
    """Treat data_line (length k) as polynomial coefficients (ascending,
    index 0 = constant term), zero-pad to n_out, and evaluate at all
    n_out roots of unity via NTT: O(n log n) instead of the O(n*k)
    Vandermonde evaluation used in the small demo."""
    padded = [int(v) for v in data_line] + [0] * (n_out - len(data_line))
    evals = galois.ntt(padded, size=n_out, modulus=P)
    return np.array([int(v) for v in evals], dtype=object)

def encode_blob(data_matrix):
    row_ext = np.array(
        [encode_line(data_matrix[r, :], EXT_COLS) for r in range(BLOB_ROWS)],
        dtype=object,
    )  # (64, 128)
    col_ext = np.array(
        [encode_line(row_ext[:, c], EXT_ROWS) for c in range(EXT_COLS)],
        dtype=object,
    ).T  # (64, 128) each length 128 -> stacked (128, 128) -> .T (128, 128)
    return col_ext  # (EXT_ROWS, EXT_COLS)

# ---------------------------------------------------------------------------
# DECODE: NTT-based erasure decoding, shared locator polynomial per pass
# ---------------------------------------------------------------------------
def root_of_unity(n, p):
    g = galois.primitive_root(p)
    a = pow(g, (p - 1) // n, p)
    assert pow(a, n, p) == 1 and pow(a, n // 2, p) != 1
    return a

def build_erasure_locator(erased_positions, n, k, alpha, p):
    """Build the erasure-locator polynomial Z(x), monic with a root at
    alpha^i for every erased position i, plus its evaluations at all n
    points (via NTT). Z(x) is zero EXACTLY at the erased points and
    nonzero everywhere else, which is what makes step 5 in decode_pass
    work: multiplying by Z "erases the erasures" regardless of what
    arbitrary value sits in those slots.

    Returns (Z_poly, Z_evals) or (None, None) if there are more
    erasures than this pass can recover alone (i.e. more than n - k,
    the redundancy budget) -- in that case the other pass is expected
    to fill in enough of this axis first.
    """
    if len(erased_positions) > n - k:
        return None, None
    Z_poly = galois.Poly([1], field=GF)  # the constant polynomial 1
    for i in erased_positions:
        root = pow(alpha, i, p)
        factor = galois.Poly([1, (-root) % p], field=GF)  # (x - root)
        Z_poly = Z_poly * factor
    Z_coeffs_desc = [int(c) for c in Z_poly.coeffs]       # highest degree first
    Z_coeffs_asc = list(reversed(Z_coeffs_desc))           # constant term first
    Z_padded = Z_coeffs_asc + [0] * (n - len(Z_coeffs_asc))
    Z_evals = [int(v) for v in galois.ntt(Z_padded, size=n, modulus=p)]
    return Z_poly, Z_evals

def recover_line_ntt(received_line, Z_poly, Z_evals, n, k, p, label=""):
    """Recover one erased line via the NTT erasure-decoding steps
    described at the top of this file: pointwise-multiply by the
    locator's evaluations, inverse-NTT, divide out the locator
    polynomial, then re-encode (NTT) to fill in the full line."""
    R = [int(v) for v in received_line]
    G_evals = [(R[i] * Z_evals[i]) % p for i in range(n)]
    prod_coeffs_asc = [int(v) for v in galois.intt(G_evals, size=n, modulus=p)]

    Prod_poly = galois.Poly(list(reversed(prod_coeffs_asc)), field=GF)
    quotient = Prod_poly // Z_poly
    remainder = Prod_poly % Z_poly
    rem_coeffs = [int(c) for c in remainder.coeffs]
    if any(c != 0 for c in rem_coeffs):
        print(f"  [{label}] WARNING: nonzero remainder recovering a line -- "
              f"erasure pattern may exceed this pass's recoverable budget")

    P_coeffs_desc = [int(c) for c in quotient.coeffs]
    P_coeffs_asc = list(reversed(P_coeffs_desc))
    if len(P_coeffs_asc) < k:
        P_coeffs_asc = P_coeffs_asc + [0] * (k - len(P_coeffs_asc))
    else:
        P_coeffs_asc = P_coeffs_asc[:k]

    return encode_line(P_coeffs_asc, n)

def decode_pass(grid, axis, erased_positions, k, n, alpha, p, label=""):
    """axis=0: decode along columns (fixing a row-erasure). axis=1: decode
    along rows (fixing a column-erasure). Returns a new grid with every
    recoverable line's erasures filled back in via NTT-based erasure
    decoding. The erasure-locator polynomial and its NTT are built ONCE
    per pass (all lines in a pass share the same erasure positions) and
    reused for every line -- this is what keeps decode from redoing the
    O(n log n) locator setup per line."""
    t0 = time.time()
    Z_poly, Z_evals = build_erasure_locator(erased_positions, n, k, alpha, p)
    t_locator = time.time() - t0
    out = grid.copy()
    if Z_poly is None:
        print(f"  [{label}] cannot recover this axis alone "
              f"(more than {n - k} erasures) -- skipping, "
              f"expecting the other pass to fix it")
        return out
    lines = range(grid.shape[1]) if axis == 0 else range(grid.shape[0])
    n_lines = len(list(lines))
    for i in (range(grid.shape[1]) if axis == 0 else range(grid.shape[0])):
        line = grid[:, i] if axis == 0 else grid[i, :]
        fixed = recover_line_ntt(line, Z_poly, Z_evals, n, k, p, label=label)
        if axis == 0:
            out[:, i] = fixed
        else:
            out[i, :] = fixed
    t_total = time.time() - t0
    print(f"  [{label}] locator build (NTT): {t_locator:.3f}s, "
          f"{n_lines} lines processed, total pass time: {t_total:.3f}s")
    return out

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
    original_len = FIELD_ELEMENTS_PER_BLOB
    data_matrix = np.array(random_blob, dtype=object).reshape(BLOB_ROWS, BLOB_COLS)
    print(f"  packed {len(app_bytes)} application bytes into "
          f"{len(random_blob)} field elements, reshaped to "
          f"{BLOB_ROWS}x{BLOB_COLS}")
    preview(data_matrix, "STEP 1: blob grid (real packed bytes, read as coefficients)")

    print("\n--- STEP 2: ENCODING (NTT-based row then column extension) ---")
    t0 = time.time()
    row_ext = np.array(
        [encode_line(data_matrix[r, :], EXT_COLS) for r in range(BLOB_ROWS)],
        dtype=object,
    )
    t_row = time.time() - t0
    print(f"  row extension: 64 NTTs of size {EXT_COLS}, {t_row:.3f}s "
          f"({BLOB_ROWS} rows x {EXT_COLS} cols = {row_ext.size} evaluations)")
    preview(row_ext, "row-extended grid (64x128, all evaluation-form now)")

    t0 = time.time()
    col_ext = np.array(
        [encode_line(row_ext[:, c], EXT_ROWS) for c in range(EXT_COLS)],
        dtype=object,
    ).T
    t_col = time.time() - t0
    print(f"\n  column extension: {EXT_COLS} NTTs of size {EXT_ROWS}, {t_col:.3f}s "
          f"({EXT_ROWS} rows x {EXT_COLS} cols = {col_ext.size} evaluations)")
    encoded_grid = col_ext
    preview(encoded_grid, "STEP 3: full encoded grid (128x128, the codeword)")
    print(f"\n  total encode time: {t_row + t_col:.3f}s, "
          f"overhead: {EXT_ROWS * EXT_COLS / (BLOB_ROWS * BLOB_COLS):.0f}x "
          f"({BLOB_ROWS*BLOB_COLS} -> {EXT_ROWS*EXT_COLS} field elements)")

    print("\n--- STEP 4: CORRUPTION (simulating peers not responding) ---")
    corrupted = encoded_grid.copy()
    corrupted[1, :] = 0
    corrupted[4, :] = 0
    erased_rows = [1, 4]
    corrupted[:, 7] = 0
    erased_cols = [7]
    print(f"  erased rows:    {erased_rows} (2 of {EXT_ROWS} -- "
          f"budget is {EXT_ROWS - BLOB_ROWS} per column, plenty of room)")
    print(f"  erased columns: {erased_cols} (1 of {EXT_COLS} -- "
          f"budget is {EXT_COLS - BLOB_COLS} per row, plenty of room)")
    preview(corrupted, "corrupted grid")

    print("\n--- STEP 5: ITERATIVE DECODING (two-pass product-code recovery, NTT-based) ---")
    alpha_cols = root_of_unity(EXT_COLS, P)
    alpha_rows = root_of_unity(EXT_ROWS, P)

    recovered = decode_pass(corrupted, axis=0, erased_positions=erased_rows,
                             k=BLOB_ROWS, n=EXT_ROWS, alpha=alpha_rows, p=P,
                             label="pass 1: vertical (fixing erased rows)")
    preview(recovered, "after vertical pass")

    recovered = decode_pass(recovered, axis=1, erased_positions=erased_cols,
                             k=BLOB_COLS, n=EXT_COLS, alpha=alpha_cols, p=P,
                             label="pass 2: horizontal (fixing erased columns)")
    preview(recovered, "after horizontal pass (should match STEP 3 exactly)")

    print("\n--- STEP 6: EXTRACTION (inverse NTT, both stages, in reverse) ---")
    t0 = time.time()

    # encode_blob ran in two stages: row-encode then column-encode, so each
    # cell of `recovered` is a genuine 2D mix of the original data -- NOT
    # simply "row r's first 64 values = data row r". Undoing this requires
    # two inverse-NTTs, in reverse order of how encoding ran. By this point
    # `recovered` has NO remaining erasures (the two passes above already
    # filled everything in), so this is a plain inverse NTT -- no locator
    # polynomial or division needed here, unlike STEP 5.

    # Stage A: undo the COLUMN extension. Each column's 128 values are the
    # NTT of a zero-padded-to-128 vector whose first 64 entries are
    # row_ext's values for that column. Inverse-NTT and keep the first 64.
    row_ext_recovered = np.array(
        [
            [int(v) for v in galois.intt(
                [int(x) for x in recovered[:, c]], size=EXT_ROWS, modulus=P
            )][:BLOB_ROWS]
            for c in range(EXT_COLS)
        ],
        dtype=object,
    ).T  # (EXT_COLS, BLOB_ROWS) stacked, then transposed -> (BLOB_ROWS, EXT_COLS)

    # Stage B: undo the ROW extension. Each row of row_ext_recovered is the
    # NTT of a zero-padded-to-128 vector whose first 64 entries are the
    # true original data. Inverse-NTT and keep the first 64.
    data_out = np.array(
        [
            [int(v) for v in galois.intt(
                [int(x) for x in row_ext_recovered[r, :]], size=EXT_COLS, modulus=P
            )][:BLOB_COLS]
            for r in range(BLOB_ROWS)
        ],
        dtype=object,
    )
    t_extract = time.time() - t0
    print(f"  stage A (inverse-NTT, undo column-extension) + "
          f"stage B (inverse-NTT, undo row-extension): {t_extract:.3f}s")

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

    print("\n" + "=" * 70)
    print(" RESULTS")
    print("=" * 70)
    print(f"Full encoded grid recovered exactly: {grid_match}")
    print(f"Original blob data recovered exactly: {data_match}  "
          f"({FIELD_ELEMENTS_PER_BLOB} field elements checked)")
    print(f"Original application bytes recovered exactly: {bytes_match}  "
          f"({len(app_bytes)} bytes checked)")
    print(f"\nTiming summary: encode {t_row + t_col:.3f}s, "
          f"decode+extract {t_extract:.3f}s (see per-pass lines above for the rest)")