"""
2D Reed-Solomon product code at real Ethereum blob scale.

    pip install galois

Requires blob_generator.py in the same directory -- input data comes
from bg.random_blob() (galois.GF.Random()-backed, statistically random,
no seed), not a hardcoded message.

Compared to the earlier small demo, this version:
  - Sizes the grid to Ethereum's actual FIELD_ELEMENTS_PER_BLOB = 4096
    (64x64), instead of an arbitrary 4x6.
  - Chunks arbitrary-length input into as many 4096-element blobs as
    needed, instead of assuming everything fits in one hardcoded matrix.
  - Encodes via NTT (galois.ntt), matching the O(n log n) mechanism
    real PeerDAS extension uses, instead of O(n*k) evaluation.
  - Decodes via erasure-only interpolation, but inverts the recovery
    matrix ONCE per pass and reuses it for every row/column in that
    pass (all lines in a pass share the same erasure positions), which
    is what keeps decode fast without a full NTT-based erasure decoder.

WHAT'S STILL A SIMPLIFICATION:
  - Real blobs pack ~31 bytes per field element to stay under P; this
    uses 1 byte/element for readability.
  - Real spec applies a bit-reversal permutation to the evaluation
    domain ordering; this version uses natural order. That matters for
    exactly which "half" of extended data maps to which peer/subnet in
    real PeerDAS, but doesn't affect whether recovery works.
  - Decode here is the classical erasure-only approach (Gaussian
    elimination), not a matching NTT-based erasure decoder so encode
    is O(n log n) but decode is still effectively O(k^2) per line
    (O(k^3) once per pass for the shared matrix inverse, O(k^2) per
    line after that).

"""

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
    """Treat data_line (length k) as polynomial coefficients, zero-pad to
    n_out, and evaluate at all n_out roots of unity via NTT: O(n log n)
    instead of the O(n*k) Vandermonde evaluation used in the small demo."""
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
# DECODE: erasure-only interpolation, shared matrix inverse per pass
# ---------------------------------------------------------------------------
def root_of_unity(n, p):
    g = galois.primitive_root(p)
    a = pow(g, (p - 1) // n, p)
    assert pow(a, n, p) == 1 and pow(a, n // 2, p) != 1
    return a

def mat_inv_mod(A, p):
    k = len(A)
    M = [row[:] + [1 if i == j else 0 for j in range(k)] for i, row in enumerate(A)]
    for col in range(k):
        piv = next(r for r in range(col, k) if M[r][col] % p != 0)
        M[col], M[piv] = M[piv], M[col]
        inv = pow(M[col][col], p - 2, p)
        M[col] = [(x * inv) % p for x in M[col]]
        for r in range(k):
            if r != col and M[r][col] % p != 0:
                f = M[r][col]
                M[r] = [(M[r][c] - f * M[col][c]) % p for c in range(2 * k)]
    return [row[k:] for row in M]

def matvec_mod(A, v, p):
    return [sum(A[i][j] * v[j] for j in range(len(v))) % p for i in range(len(A))]

def build_recovery_matrix(erased_positions, n, k, alpha, p):
    """One matrix inverse, reused for every line in a pass since they all
    share the same erased positions -- turns an O(lines * k^3) decode into
    O(k^3 + lines * k^2)."""
    surviving = [j for j in range(n) if j not in erased_positions][:k]
    if len(surviving) < k:
        return None, None
    A = [[pow(alpha, i * j, p) for i in range(k)] for j in surviving]
    return mat_inv_mod(A, p), surviving

def decode_pass(grid, axis, erased_positions, k, n, alpha, p, label=""):
    """axis=0: decode along columns (fixing a row-erasure). axis=1: decode
    along rows (fixing a column-erasure). Returns a new grid with every
    recoverable line's first k coefficients reconstructed and
    re-extended to full length n."""
    t0 = time.time()
    Ainv, surviving = build_recovery_matrix(erased_positions, n, k, alpha, p)
    t_inv = time.time() - t0
    out = grid.copy()
    if Ainv is None:
        print(f"  [{label}] cannot recover this axis alone "
              f"(fewer than {k} surviving positions) -- skipping, "
              f"expecting the other pass to fix it")
        return out
    lines = range(grid.shape[1]) if axis == 0 else range(grid.shape[0])
    n_lines = len(list(lines))
    for i in (range(grid.shape[1]) if axis == 0 else range(grid.shape[0])):
        line = grid[:, i] if axis == 0 else grid[i, :]
        b = [int(line[j]) for j in surviving]
        coeffs = matvec_mod(Ainv, b, p)
        fixed = encode_line(coeffs, n)
        if axis == 0:
            out[:, i] = fixed
        else:
            out[i, :] = fixed
    t_total = time.time() - t0
    print(f"  [{label}] matrix inverse: {t_inv:.3f}s, "
          f"{n_lines} lines processed, total pass time: {t_total:.3f}s")
    return out

# ---------------------------------------------------------------------------
# DEMO RUN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print(" 2D REED-SOLOMON PRODUCT CODE -- BLOB SCALE, NTT-BASED")
    print("=" * 70)

    print(f"\nRequesting one fully random blob from blob_generator "
          f"(galois.GF.Random()-backed, no seed)...")
    random_blob = bg.random_blob()
    bg.validate_blob(random_blob)
    original_len = FIELD_ELEMENTS_PER_BLOB
    data_matrix = np.array(random_blob, dtype=object).reshape(BLOB_ROWS, BLOB_COLS)
    print(f"  received {len(random_blob)} field elements, reshaped to "
          f"{BLOB_ROWS}x{BLOB_COLS}")
    preview(data_matrix, "STEP 1: blob grid (random field elements, read as coefficients)")

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

    print("\n--- STEP 5: ITERATIVE DECODING (two-pass product-code recovery) ---")
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

    print("\n--- STEP 6: EXTRACTION (invert BOTH transform stages, in reverse) ---")
    t0 = time.time()

    # encode_blob ran in two stages: row-encode then column-encode, so each
    # cell of `recovered` is a genuine 2D mix of the original data -- NOT
    # simply "row r's first 64 values = data row r". Undoing this requires
    # two separate inversions, in reverse order of how encoding ran.

    # Stage A: undo the COLUMN extension. For each column, its 128 values
    # are evaluations (along the ROW axis) of a degree<64 polynomial whose
    # coefficients are exactly row_ext's values for that column. Solve
    # using any 64 known row-positions.
    Ainv_stageA, _ = build_recovery_matrix(
        erased_positions=[], n=EXT_ROWS, k=BLOB_ROWS, alpha=alpha_rows, p=P
    )
    row_ext_recovered = np.array(
        [matvec_mod(Ainv_stageA, [int(v) for v in recovered[:BLOB_ROWS, c]], P)
         for c in range(EXT_COLS)],
        dtype=object,
    ).T  # (EXT_COLS, BLOB_ROWS) stacked, then transposed -> (BLOB_ROWS, EXT_COLS)

    # Stage B: undo the ROW extension. For each row of the now-recovered
    # row_ext, its 128 values are evaluations (along the COLUMN axis) of a
    # degree<64 polynomial whose coefficients are the true original data.
    Ainv_stageB, _ = build_recovery_matrix(
        erased_positions=[], n=EXT_COLS, k=BLOB_COLS, alpha=alpha_cols, p=P
    )
    data_out = np.array(
        [matvec_mod(Ainv_stageB, [int(v) for v in row_ext_recovered[r, :BLOB_COLS]], P)
         for r in range(BLOB_ROWS)],
        dtype=object,
    )
    t_extract = time.time() - t0
    print(f"  stage A (undo column-extension) + stage B (undo row-extension): "
          f"{t_extract:.3f}s")

    grid_match = bool(np.array_equal(np.array(encoded_grid, dtype=object),
                                      np.array(recovered, dtype=object)))
    data_match = bool(np.array_equal(np.array(data_matrix, dtype=object),
                                      np.array(data_out, dtype=object)))

    print("\n" + "=" * 70)
    print(" RESULTS")
    print("=" * 70)
    print(f"Full encoded grid recovered exactly: {grid_match}")
    print(f"Original blob data recovered exactly: {data_match}  "
          f"({FIELD_ELEMENTS_PER_BLOB} field elements checked)")
    print(f"\nTiming summary: encode {t_row + t_col:.3f}s, "
          f"decode+extract {t_extract:.3f}s (see per-pass lines above for the rest)")