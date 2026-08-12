"""
2D Reed-Solomon product code at real Ethereum blob scale.

    pip install galois

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

WHAT'S STILL A SIMPLIFICATION (flagged, not hidden):
  - Real blobs pack ~31 bytes per field element to stay under P; this
    demo uses 1 byte/element for readability.
  - Real spec applies a bit-reversal permutation to the evaluation
    domain ordering; this version uses natural order. That matters for
    exactly which "half" of extended data maps to which peer/subnet in
    real PeerDAS, but doesn't affect whether recovery works.
  - Decode here is the classical erasure-only approach (Gaussian
    elimination), not a matching NTT-based erasure decoder -- so encode
    is O(n log n) but decode is still effectively O(k^2) per line
    (O(k^3) once per pass for the shared matrix inverse, O(k^2) per
    line after that). Worth calling out explicitly in a complexity
    writeup: a production system would want a fast erasure decoder too.

NOTE ON TESTING: as with the earlier version, this could not be run in
the sandbox that wrote it (no internet access there, so no `pip install
galois`). The NTT-as-fast-evaluation and shared-inverse-decode design
was validated by hand at small scale (k=8, n=16) using plain Python +
sympy before this file was written, and the API calls are copied from
galois's official docs. Please run this and report back.
"""

import galois
import numpy as np

# ---------------------------------------------------------------------------
# FIELD: BLS12-381 scalar field (Fr)
# ---------------------------------------------------------------------------
P = 52435875175126190479447740508185965837690552500527637822603658699938581184513
GF = galois.GF(P)

# ---------------------------------------------------------------------------
# BLOB / GRID SIZING
# ---------------------------------------------------------------------------
FIELD_ELEMENTS_PER_BLOB = 4096         # Ethereum's actual constant
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
# INPUT CHUNKING: arbitrary-length input -> one or more 4096-element blobs
# ---------------------------------------------------------------------------
def bytes_to_blobs(data: bytes):
    """Split input into 4096-field-element blobs (1 byte/element for demo
    clarity -- real blobs pack ~31 bytes/element). Last blob zero-padded."""
    blobs = []
    for i in range(0, len(data), FIELD_ELEMENTS_PER_BLOB):
        chunk = data[i:i + FIELD_ELEMENTS_PER_BLOB]
        chunk = chunk.ljust(FIELD_ELEMENTS_PER_BLOB, b"\x00")
        grid = np.array(list(chunk), dtype=object).reshape(BLOB_ROWS, BLOB_COLS)
        blobs.append(grid)
    return blobs

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

def decode_pass(grid, axis, erased_positions, k, n, alpha, p):
    """axis=0: decode along columns (fixing a row-erasure). axis=1: decode
    along rows (fixing a column-erasure). Returns a new grid with every
    recoverable line's first k coefficients reconstructed and
    re-extended to full length n."""
    Ainv, surviving = build_recovery_matrix(erased_positions, n, k, alpha, p)
    out = grid.copy()
    if Ainv is None:
        return out  # not recoverable from this axis alone
    lines = range(grid.shape[1]) if axis == 0 else range(grid.shape[0])
    for i in lines:
        line = grid[:, i] if axis == 0 else grid[i, :]
        b = [int(line[j]) for j in surviving]
        coeffs = matvec_mod(Ainv, b, p)
        fixed = encode_line(coeffs, n)
        if axis == 0:
            out[:, i] = fixed
        else:
            out[i, :] = fixed
    return out

# ---------------------------------------------------------------------------
# DEMO RUN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    message = b"2D-RS-CODE-DEMO-AT-BLOB-SCALE!"
    original_len = len(message)
    blobs = bytes_to_blobs(message)
    print(f"Input is {original_len} bytes -> {len(blobs)} blob(s) of "
          f"{FIELD_ELEMENTS_PER_BLOB} field elements each ({BLOB_ROWS}x{BLOB_COLS}).")

    data_matrix = blobs[0]
    encoded_grid = encode_blob(data_matrix)
    print(f"Extended grid shape: {encoded_grid.shape} "
          f"({EXT_ROWS * EXT_COLS / (BLOB_ROWS * BLOB_COLS):.0f}x total overhead)")

    # Corrupt: wipe one full row and one full column (peer-loss simulation)
    corrupted = encoded_grid.copy()
    corrupted[1, :] = 0
    erased_rows = [1]
    corrupted[4, :] = 0
    erased_rows.append(4)
    corrupted[:, 7] = 0
    erased_cols = [7]

    alpha_cols = root_of_unity(EXT_COLS, P)
    alpha_rows = root_of_unity(EXT_ROWS, P)

    recovered = decode_pass(corrupted, axis=0, erased_positions=erased_rows,
                             k=BLOB_ROWS, n=EXT_ROWS, alpha=alpha_rows, p=P)
    recovered = decode_pass(recovered, axis=1, erased_positions=erased_cols,
                             k=BLOB_COLS, n=EXT_COLS, alpha=alpha_cols, p=P)

    # Recover the true original data: after decoding, the grid holds
    # EVALUATIONS, not the original coefficients (data_matrix bytes were
    # zero-padded and NTT'd during encode, so the top-left corner of the
    # evaluation grid is NOT the same as the original bytes). Solve for
    # the coefficients explicitly, using positions 0..63 -- valid now
    # that every position in `recovered` is confirmed correct.
    Ainv_final, surviving_final = build_recovery_matrix(
        erased_positions=[], n=EXT_COLS, k=BLOB_COLS, alpha=alpha_cols, p=P
    )
    data_out = np.array(
        [matvec_mod(Ainv_final, [int(v) for v in recovered[r, :BLOB_COLS]], P)
         for r in range(BLOB_ROWS)],
        dtype=object,
    )
    extracted = bytes(int(v) for v in data_out.flatten())[:original_len]
    match = bool(np.array_equal(np.array(encoded_grid, dtype=object),
                                 np.array(recovered, dtype=object)))

    print(f"Matrix Match Success: {match}")
    print(f"Original Text:        {message.decode('utf-8')}")
    print(f"Recovered Text:       {extracted.decode('utf-8')}")