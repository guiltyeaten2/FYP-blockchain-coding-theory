"""
1D Reed-Solomon code at real Ethereum blob scale -- the PeerDAS baseline.

    pip install galois

Requires blob_generator.py in the same directory -- input data comes
from real application bytes, packed into a blob via bg.bytes_to_blobs()
using the ACTUAL EIP-4844 packing convention (31 usable bytes per
32-byte field element), exactly as 2D_RS_Galois.py does.

COMPANION FILE to 2D_RS_Galois.py. This is Ethereum's ACTUAL current
PeerDAS coding scheme (see [10], [11] in the report) -- a single 1D
RS extension of the whole blob -- kept in exactly the same style,
field, blob-packing convention, domain ordering, and NTT-based
erasure-decode machinery as the 2D-RS file, specifically so the two
are a fair, apples-to-apples comparison for the report's Phase 2/3
analysis (computational complexity, encoding/decoding efficiency,
storage overhead, bandwidth consumption, scalability, fault
tolerance) rather than two differently-built implementations
measuring different things.

Structurally, 1D-RS is the degenerate case of 2D-RS with only one
axis:
  - The blob's 4096 field elements are evaluations of ONE degree-<4096
    polynomial (not reshaped into a grid).
  - Extension is a single interpolate-then-evaluate-on-a-bigger-domain
    step (INTT -> zero-pad -> NTT), taking it from 4096 to 8192
    evaluations -- a clean 2x overhead, matching PeerDAS's actual
    extension ratio exactly (contrast with 2D_RS_Galois.py, which
    doubles BOTH axes for 4x total, an explicit documented tradeoff
    of that scheme, not of 1D-RS).
  - Recovery is a SINGLE erasure-decode pass over the whole 8192-
    length codeword: if at most n-k = 4096 of it (50%) is missing,
    NTT-based erasure decoding recovers it exactly, in one shot. If
    more than that is missing, there is nothing left to try -- unlike
    2D-RS, there is no second axis to lean on and no iteration that
    can help. This single-shot, hard-ceiling behaviour (as opposed to
    2D-RS's iterative, sometimes-better-than-either-axis-alone
    recovery) is itself one of the report's expected trade-off
    findings, not a simplification -- it's what 1D-RS actually does.

Same honest simplifications as 2D_RS_Galois.py:
  - Models an erasure channel only (missing samples), not arbitrary
    symbol errors -- matches how PeerDAS samples are used.
  - Dividing the locator-multiplied product to recover coefficients
    uses ordinary polynomial long division, not a Newton-iteration
    power-series inversion -- see the timing data printed by this
    script's own STEP 8 for how that cost scales with erasure count,
    which is itself a real datapoint for the report's computational
    complexity comparison.
"""

import os
import galois
import numpy as np
import time
import blob_generator as bg

def preview(vector, label, size=12):
    """A 1D codeword doesn't have the "top-left corner" framing a grid
    does -- show the first `size` elements instead, truncated to 16
    bits for readability (each real value is a ~255-bit field
    element)."""
    print(f"\n--- {label} (length {len(vector)}, showing first {size}) ---")
    cells = [f"{int(v) & 0xFFFF:04x}" for v in vector[:size]]
    print(f"  [ {' '.join(cells)} ]")

# ---------------------------------------------------------------------------
# FIELD: BLS12-381 scalar field (Fr) -- identical to 2D_RS_Galois.py
# ---------------------------------------------------------------------------
P = 52435875175126190479447740508185965837690552500527637822603658699938581184513
GF = galois.GF(P)

# ---------------------------------------------------------------------------
# BLOB SIZING (reused from blob_generator so all scheme files agree)
# ---------------------------------------------------------------------------
FIELD_ELEMENTS_PER_BLOB = bg.FIELD_ELEMENTS_PER_BLOB   # 4096, K
EXTENSION_FACTOR = 2                                   # PeerDAS's actual ratio
EXT_LEN = FIELD_ELEMENTS_PER_BLOB * EXTENSION_FACTOR   # 8192, N

for n in (FIELD_ELEMENTS_PER_BLOB, EXT_LEN):
    assert (P - 1) % n == 0, f"P-1 must be divisible by {n} for an NTT of that size"

# ---------------------------------------------------------------------------
# BIT-REVERSAL PERMUTED DOMAIN ORDERING (consensus-specs convention) --
# identical logic to 2D_RS_Galois.py
# ---------------------------------------------------------------------------
def bit_reversal_permutation(n):
    """perm[i] = bit-reversal of i over log2(n) bits. Blob/codeword slot
    i corresponds to domain point alpha_n^perm[i]. Self-inverse."""
    bits = n.bit_length() - 1
    assert (1 << bits) == n
    return [int(format(i, f"0{bits}b")[::-1], 2) for i in range(n)]

def bitreverse_permute(values, brp):
    """Self-inverse: cell-order <-> natural NTT-domain order."""
    return [values[brp[i]] for i in range(len(values))]

BRP_K = bit_reversal_permutation(FIELD_ELEMENTS_PER_BLOB)
BRP_N = bit_reversal_permutation(EXT_LEN)

def root_of_unity(n, p):
    g = galois.primitive_root(p)
    a = pow(g, (p - 1) // n, p)
    assert pow(a, n, p) == 1 and pow(a, n // 2, p) != 1
    return a

# ---------------------------------------------------------------------------
# ENCODE: interpolate (from evaluations) then extend (evaluate on a
# bigger domain) -- same real FFT-based RS extension as the 2D file,
# applied ONCE to the whole blob instead of per row/column.
# ---------------------------------------------------------------------------
def evals_from_coeffs(coeffs, n, brp_n, p):
    padded = [int(c) for c in coeffs] + [0] * (n - len(coeffs))
    natural = [int(v) for v in galois.ntt(padded, size=n, modulus=p)]
    return bitreverse_permute(natural, brp_n)

def interpolate_then_extend(evals_cellorder_k, k, n, brp_k, brp_n, p):
    """evals_cellorder_k: k values in blob-slot order -- the real
    Ethereum representation (blob field elements ARE evaluations).
    Returns n evaluations (blob-slot order) of that SAME polynomial on
    the extended domain."""
    natural_k = bitreverse_permute([int(v) for v in evals_cellorder_k], brp_k)
    coeffs = [int(v) for v in galois.intt(natural_k, size=k, modulus=p)]
    return evals_from_coeffs(coeffs, n, brp_n, p)

def restrict(evals_cellorder_n, k, n, brp_k, brp_n, p):
    """Inverse of interpolate_then_extend: given n evaluations
    (blob-slot order) of a polynomial known to have degree < k,
    recover the original k evaluations (blob-slot order)."""
    natural_n = bitreverse_permute([int(v) for v in evals_cellorder_n], brp_n)
    coeffs_n = [int(v) for v in galois.intt(natural_n, size=n, modulus=p)]
    coeffs_k = coeffs_n[:k]
    natural_k = [int(v) for v in galois.ntt(coeffs_k, size=k, modulus=p)]
    return bitreverse_permute(natural_k, brp_k)

def encode_blob(data_vector):
    return interpolate_then_extend(data_vector, FIELD_ELEMENTS_PER_BLOB, EXT_LEN,
                                    BRP_K, BRP_N, P)

# ---------------------------------------------------------------------------
# DECODE: NTT-based erasure decoding, ONE SHOT over the whole codeword.
# No row/column structure to iterate over -- unlike 2D_RS_Galois.py's
# decode_iterative(), there is nothing to fall back on if this single
# pass can't clear the erasure pattern.
# ---------------------------------------------------------------------------
def build_erasure_locator(erased_cells, n, k, alpha, brp_n, p):
    """Returns (Z_poly, Z_evals_natural), or (None, None) if there are
    more than n - k erasures -- the whole-blob budget, since 1D-RS has
    no second axis to make up the difference."""
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

def recover_codeword_ntt(received_cellorder, Z_poly, Z_evals_natural, n, k, brp_n, p):
    """Multiply by the locator's evaluations, inverse-NTT, divide out
    the locator polynomial to get the true degree-<k coefficients,
    then re-evaluate (NTT) on the full n-domain to fill in every
    erased slot at once."""
    R_natural = bitreverse_permute([int(v) for v in received_cellorder], brp_n)
    G_evals = [(R_natural[j] * Z_evals_natural[j]) % p for j in range(n)]
    prod_coeffs_asc = [int(v) for v in galois.intt(G_evals, size=n, modulus=p)]

    Prod_poly = galois.Poly(list(reversed(prod_coeffs_asc)), field=GF)
    quotient = Prod_poly // Z_poly
    remainder = Prod_poly % Z_poly
    rem_coeffs = [int(c) for c in remainder.coeffs]
    if any(c != 0 for c in rem_coeffs):
        print("  WARNING: nonzero remainder recovering the codeword -- "
              "erasure pattern may exceed the n-k budget")

    coeffs_desc = [int(c) for c in quotient.coeffs]
    coeffs_asc = list(reversed(coeffs_desc))
    if len(coeffs_asc) < k:
        coeffs_asc = coeffs_asc + [0] * (k - len(coeffs_asc))
    else:
        coeffs_asc = coeffs_asc[:k]

    return evals_from_coeffs(coeffs_asc, n, brp_n, p)

def decode(corrupted_vector, mask, k, n, alpha, brp_n, p, label=""):
    """One-shot erasure decode: either the whole blob comes back, or it
    doesn't -- there is no partial/iterative recovery path for 1D-RS.
    Returns (recovered_vector, success: bool)."""
    erased_cells = [int(i) for i in np.nonzero(mask)[0]]
    t0 = time.time()
    if not erased_cells:
        return list(corrupted_vector), True
    Z_poly, Z_evals = build_erasure_locator(erased_cells, n, k, alpha, brp_n, p)
    if Z_poly is None:
        print(f"  [{label}] FAILED: {len(erased_cells)} erasures exceed the "
              f"n-k = {n - k} budget -- unrecoverable, no second axis to fall back on")
        return list(corrupted_vector), False
    recovered = recover_codeword_ntt(corrupted_vector, Z_poly, Z_evals, n, k, brp_n, p)
    t_total = time.time() - t0
    print(f"  [{label}] recovered {len(erased_cells)} erasures in one pass, {t_total:.3f}s")
    return recovered, True

def random_erasure_mask(n, rate, rng):
    """A per-cell adversarial sampling pattern: each of the n codeword
    slots independently withheld with probability `rate`."""
    return rng.random(n) < rate

# ---------------------------------------------------------------------------
# DEMO RUN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 70)
    print(" 1D REED-SOLOMON CODE -- BLOB SCALE, NTT ENCODE + DECODE (PeerDAS baseline)")
    print("=" * 70)

    print(f"\nGenerating real application bytes and packing them into a blob "
          f"the actual EIP-4844 way: {bg.USABLE_BYTES_PER_FIELD_ELEMENT} usable "
          f"bytes per {bg.BYTES_PER_FIELD_ELEMENT}-byte field element "
          f"({bg.USABLE_BYTES_PER_BLOB} usable bytes/blob), "
          f"via bg.bytes_to_blobs() -- not raw random field elements.")
    app_bytes = os.urandom(bg.USABLE_BYTES_PER_BLOB)  # exactly one blob's worth
    random_blob = bg.bytes_to_blobs(app_bytes)[0]
    bg.validate_blob(random_blob)
    data_vector = [int(v) for v in random_blob]
    print(f"  packed {len(app_bytes)} application bytes into "
          f"{len(random_blob)} field elements. Per EIP-4844, these ARE the "
          f"evaluations of the blob's polynomial (blob-slot order, "
          f"bit-reversal permuted domain) -- not coefficients, and NOT "
          f"reshaped into a grid: 1D-RS treats the blob as one codeword.")
    preview(data_vector, "STEP 1: blob (real packed bytes, evaluation form)")

    print("\n--- STEP 2: ENCODING (interpolate + NTT-extend, single pass) ---")
    t0 = time.time()
    encoded_vector = encode_blob(data_vector)
    t_encode = time.time() - t0
    print(f"  one interpolate+NTT of size {EXT_LEN}, {t_encode:.3f}s "
          f"({FIELD_ELEMENTS_PER_BLOB} -> {EXT_LEN} field elements, "
          f"overhead: {EXT_LEN / FIELD_ELEMENTS_PER_BLOB:.0f}x -- matches "
          f"PeerDAS's actual 2x extension exactly)")
    preview(encoded_vector, "STEP 3: full encoded codeword (the extended blob)")

    alpha = root_of_unity(EXT_LEN, P)

    print("\n--- STEP 4: CORRUPTION (simulating peers not responding) ---")
    rng = np.random.default_rng()
    erased_positions = sorted(rng.choice(EXT_LEN, size=200, replace=False).tolist())
    mask = np.zeros(EXT_LEN, dtype=bool)
    mask[erased_positions] = True
    corrupted = list(encoded_vector)
    for i in erased_positions:
        corrupted[i] = 0
    print(f"  erased {len(erased_positions)} scattered samples of {EXT_LEN} -- "
          f"budget is {EXT_LEN - FIELD_ELEMENTS_PER_BLOB} ({(EXT_LEN - FIELD_ELEMENTS_PER_BLOB) / EXT_LEN:.0%}), "
          f"plenty of room")
    preview(corrupted, "corrupted codeword")

    print("\n--- STEP 5: DECODING (single NTT-based erasure-decode pass) ---")
    recovered, ok = decode(corrupted, mask, k=FIELD_ELEMENTS_PER_BLOB, n=EXT_LEN,
                            alpha=alpha, brp_n=BRP_N, p=P, label="single decode pass")
    preview(recovered, "after decoding (should match STEP 3 exactly)")

    print("\n--- STEP 6: EXTRACTION (restrict back to the original k-domain) ---")
    t0 = time.time()
    data_out = restrict(recovered, FIELD_ELEMENTS_PER_BLOB, EXT_LEN, BRP_K, BRP_N, P)
    t_extract = time.time() - t0
    print(f"  restrict (inverse-NTT, truncate, re-NTT): {t_extract:.3f}s")

    codeword_match = list(encoded_vector) == list(recovered)
    data_match = data_vector == data_out

    print("\n--- STEP 7: REAL-WORLD ROUND TRIP (recovered blob -> application bytes) ---")
    bg.validate_blob(data_out)
    recovered_bytes = bg.blob_to_bytes(data_out)
    bytes_match = recovered_bytes == app_bytes
    print(f"  unpacked {len(recovered_bytes)} bytes via bg.blob_to_bytes(); "
          f"matches original application bytes: {bytes_match}")

    print("\n--- STEP 8: RANDOM ADVERSARIAL SAMPLING TRIALS (per-cell erasure mask) ---")
    print("  For direct timing/fault-tolerance comparison against 2D_RS_Galois.py's")
    print("  STEP 8 under the Phase 3 methodology. Unlike the 2D file, there is no")
    print("  iteration here -- one pass either clears the pattern or it doesn't.")
    print("  NOTE: recovering one erasure-decode pass over a single ~8192-length")
    print("  codeword means the polynomial DIVISION step (see module docstring) is")
    print("  against one large divisor rather than many small ones -- its cost scales")
    print("  with erasure count (observed ~10s at 200 erasures, ~70s at 2000, on this")
    print("  machine) in a way the 2D file's many-small-lines approach doesn't. That")
    print("  scaling difference is itself a real datapoint for the report's")
    print("  computational-complexity comparison, so rates below are kept modest to")
    print("  keep this demo's runtime reasonable -- a full rate sweep for the actual")
    print("  benchmarking chapter belongs in a dedicated timing-harness script.")
    for rate in (0.05, 0.15, 0.55):
        trial_mask = random_erasure_mask(EXT_LEN, rate, rng)
        trial_corrupted = list(encoded_vector)
        for i in np.nonzero(trial_mask)[0]:
            trial_corrupted[int(i)] = 0
        n_erased = int(trial_mask.sum())
        print(f"\n  -- rate={rate:.2f}: {n_erased}/{EXT_LEN} samples erased --")
        t0 = time.time()
        trial_recovered, trial_ok = decode(trial_corrupted, trial_mask,
                                            k=FIELD_ELEMENTS_PER_BLOB, n=EXT_LEN,
                                            alpha=alpha, brp_n=BRP_N, p=P,
                                            label=f"rate={rate:.2f}")
        t_trial = time.time() - t0
        trial_match = trial_ok and list(encoded_vector) == list(trial_recovered)
        print(f"  rate={rate:.2f}: fully recovered={trial_match}, decode time={t_trial:.3f}s")

    print("\n" + "=" * 70)
    print(" RESULTS")
    print("=" * 70)
    print(f"Full encoded codeword recovered exactly: {codeword_match}")
    print(f"Original blob data recovered exactly: {data_match}  "
          f"({FIELD_ELEMENTS_PER_BLOB} field elements checked)")
    print(f"Original application bytes recovered exactly: {bytes_match}  "
          f"({len(app_bytes)} bytes checked)")
    print(f"\nTiming summary: encode {t_encode:.3f}s, "
          f"extract {t_extract:.3f}s (see per-pass lines above for decode)")
