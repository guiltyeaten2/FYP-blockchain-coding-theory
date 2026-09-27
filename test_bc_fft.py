"""
Structural checks on the FFT path in BCcodeEthereum.py.

    python3 test_bc_fft.py

These are not timing tests. They check the one premise the FFT decoder rests
on -- that the thing being decoded really is a GRS codeword in the evaluation
points it was handed -- separately for each phase, because the answer differs.

Background. fft_grs_erasure_decode recovers f from evaluations of a
degree-<k_poly polynomial. It detects a bad premise by inverse-transforming
the locator-multiplied received word and checking that the coefficients above
k_poly + e vanish. If the input is not a codeword of the assumed code those
tail coefficients are nonzero and it bails out. Both phases were bailing out
on every call; the two phases were doing so for completely different reasons,
and only one of them is fixable by passing the right multipliers.
"""
import os
import numpy as np
import galois

import blob_generator as bg
import BCcodeEthereum as bc

GF = bg.GF
P = bg.BLS_MODULUS
K = bg.FIELD_ELEMENTS_PER_BLOB


def tail_nonzero(values, size, k_poly):
    """How many of the coefficients that ought to vanish do not."""
    coeffs = [int(x) for x in galois.intt(values, size=size, modulus=P)]
    return sum(1 for v in coeffs[k_poly:] if v % P)


def main():
    omega = rho = 1024
    lam = 3                      # the one row whose phase-2 length also admits an NTT
    mu = K // omega
    blob = bg.bytes_to_blobs(os.urandom(bg.USABLE_BYTES_PER_BLOB))[0]
    code = bc.encode_bc_structured(GF, GF(blob), mu, lam, omega, rho)

    # ---------------------------------------------------------------- phase 1
    # The local code is GRS by construction: build_local_grs defines it by the
    # parity check H[r, c] = x_c^r, so its codewords are c_j = v_j * f(x_j)
    # with v_j = 1 / prod_{i != j}(x_j - x_i). For n0-th roots of unity that
    # product is n0 / x_j, so v_j is proportional to x_j. Dividing the codeword
    # through by x_j should therefore land exactly in evaluation form.
    n0 = rho + lam * omega
    k0 = n0 - rho
    pts0 = bc.make_eval_pts(n0, P)
    local = [int(code[g]) for g in bc.get_local_indices(0, mu, lam, omega, rho)]

    raw = tail_nonzero(local, n0, k0)
    scaled = tail_nonzero(
        [(local[j] * pow(int(pts0[j]), P - 2, P)) % P for j in range(n0)], n0, k0)
    print(f"phase 1  n0={n0} k0={k0}")
    print(f"  raw codeword as evaluations      nonzero tail coeffs: {raw}")
    print(f"  after dividing by x_c            nonzero tail coeffs: {scaled}")
    assert scaled == 0, "phase-1 local code should be GRS once multipliers are removed"
    print("  OK -- the local code IS GRS; passing col_mult=eval_pts is correct\n")

    # ---------------------------------------------------------------- phase 2
    # The union of two adjacent supports is a different matter. Phase 2 relabels
    # that union with a fresh set of n_aux-th roots of unity and decodes it as a
    # flat GRS code. Nothing guarantees that: the two blocks' parity checks
    # assign DIFFERENT evaluation points to the columns they share, and
    # relabelling throws that structure away. If the premise held, the tail
    # would vanish (with or without multipliers) exactly as it does above.
    sup_i = bc.get_local_indices(0, mu, lam, omega, rho)
    sup_j = bc.get_local_indices(1, mu, lam, omega, rho)
    combined = sorted(set(sup_i) | set(sup_j))
    n_aux = len(combined)
    k_aux = n_aux - 2 * rho
    pts_aux = bc.make_eval_pts(n_aux, P)
    union = [int(code[g]) for g in combined]

    raw_a = tail_nonzero(union, n_aux, k_aux)
    scaled_a = tail_nonzero(
        [(union[j] * pow(int(pts_aux[j]), P - 2, P)) % P for j in range(n_aux)],
        n_aux, k_aux)
    print(f"phase 2  n_aux={n_aux} k_aux={k_aux} "
          f"({n_aux - k_aux} tail coeffs must vanish)")
    print(f"  raw union as evaluations         nonzero tail coeffs: {raw_a}")
    print(f"  after dividing by x_c            nonzero tail coeffs: {scaled_a}")
    assert scaled_a > 0, (
        "if this ever passes, phase-2's flat-GRS premise has become valid and "
        "the FFT path there is worth enabling")
    print("  EXPECTED FAILURE -- essentially every tail coefficient is nonzero,")
    print("  so the union is not a GRS code in these points and no choice of")
    print("  multipliers fixes it. Phase 2 needs the auxiliary GRS construction")
    print("  from the paper's Algorithm 1, not a relabelling of the union.\n")

    # ------------------------------------------------------- round trip still ok
    n = mu * (rho + omega)
    rng = np.random.default_rng(3)
    mask = rng.random(n) < 0.10
    corrupted = code.copy()
    corrupted[mask] = GF(0)
    rec, rem = bc.dec_cbc_2(None, corrupted, mask, mu, lam, omega, rho,
                            pair_unknown_cap=256)
    exact = (not np.any(rem)) and [int(v) for v in rec[:K]] == list(blob)
    print(f"round trip at 10% erasure: exact={exact}")
    assert exact
    print("\nall checks passed")


if __name__ == "__main__":
    main()
