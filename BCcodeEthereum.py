# ==============================================================================
# IMPORT ETHEREUM BLOB GENERATOR (EIP-4844 / consensus-specs)
# ==============================================================================
# The blob_generator module provides:
#   - FIELD_ELEMENTS_PER_BLOB = 4096  (number of field elements in a blob)
#   - GF: a Galois field class (here BLS12‑381 prime field)
#   - random_blob(): returns a Python list of 4096 integers in GF(p)
"""
Block-Circulant erasure code for Ethereum blob scale.

Implements the code from:
    B. Sasidharan, E. Viterbo, S. H. Dau, "Block Circulant Codes With
    Application to Decentralized Systems," IEEE Trans. Commun., vol. 73,
    no. 10, pp. 8542-8557, Oct. 2025.

Decoders provided:
    dec_cbc_2_aux_ntt   - two-phase decoder. Phase 1 solves single blocks;
                          Phase 2 solves adjacent pairs. Both phases try an
                          FFT-based GRS erasure decoder first and fall back
                          to Gaussian elimination when FFT is unavailable or
                          the FFT candidate fails verification.
    dec_cbc_t           - general t-block decoder, Gaussian only.

Evaluation points:
    All decoders and the encoder use n0-th roots of unity as the local GRS
    evaluation points, where n0 = lambda*omega + rho. This is required for
    the FFT decoder to apply. It requires n0 | (p-1), which holds for all
    powers-of-two n0 in BLS12-381. The code produced is the same code either
    way (a GRS code with a Vandermonde parity-check matrix); the roots of
    unity are simply a convenient choice that enables FFT.
"""

import time
import numpy as np
import galois

from blob_generator import FIELD_ELEMENTS_PER_BLOB, GF, random_blob

GF_BLS12_381 = GF
P_FIELD = int(GF_BLS12_381.characteristic)


# ==============================================================================
# PARAMETERS
# ==============================================================================
omega = 1024
rho = omega
lambda_ = 2
mu = FIELD_ELEMENTS_PER_BLOB // omega       # = 2 for one blob at these sizes

n = mu * (rho + omega)                       # 8192
k = mu * omega                               # 4096
d = lambda_ * rho + 1                        # 2049
n0 = rho + lambda_ * omega                   # 6144


# ==============================================================================
# GALOIS FIELD LINEAR ALGEBRA (Gaussian fallback)
# ==============================================================================
class GFSolveError(ValueError):
    """Raised by vandermonde_solve when the node set has a collision."""

def vandermonde_solve(nodes, s, p):
    """O(e^2) solver for sum_j nodes[j]**r * x[j] = s[r], r < e."""
    e = len(nodes)
    if e == 0:
        return []
    nodes = [int(a) % p for a in nodes]
    s = [int(v) % p for v in s]
    N = [0] * (e + 1); N[0] = 1; deg = 0
    for a in nodes:
        for i in range(deg + 1, 0, -1):
            N[i] = (N[i - 1] - a * N[i]) % p
        N[0] = (-a * N[0]) % p
        deg += 1
    x = [0] * e
    for j, a in enumerate(nodes):
        qd = []; acc = 0
        for i in range(e, 0, -1):
            acc = (N[i] + acc * a) % p
            qd.append(acc)
        den = 0
        for c in qd:
            den = (den * a + c) % p
        if den == 0:
            raise GFSolveError("vandermonde_solve: repeated node")
        tot = 0
        for i in range(e):
            tot += qd[e - 1 - i] * s[i]
        x[j] = (tot % p) * pow(den, p - 2, p) % p
    return x

def nth_roots_of_unity(n, p):
    """
    Return the complete set of n-th roots of unity in GF(p), in ascending
    power order: [omega^0, omega^1, ..., omega^(n-1)], where omega is a
    primitive n-th root.

    These are exactly the elements of the unique subgroup of GF(p)* of
    order n. The subgroup exists iff n divides p - 1; if it does not, no
    such element omega exists and this function raises.

    Parameters
    ----------
    n : int
        Transform size. Must divide p - 1.
    p : int
        Field characteristic (prime).

    Returns
    -------
    list[int], length n
        The n distinct n-th roots of unity in GF(p).

    Raises
    ------
    ValueError
        If n does not divide p - 1, or if n <= 0.

    Notes
    -----
    This is a utility, not a policy. It does not decide whether the code
    uses roots of unity or some other evaluation points; that decision is
    made by the encoder and mirrored by the decoder. It is called from
    the paths that have already chosen roots-of-unity evaluation points.
    """
    if n <= 0:
        raise ValueError(f"n must be positive; got {n}")
    if (p - 1) % n != 0:
        raise ValueError(
            f"n = {n} does not divide p - 1; "
            f"no subgroup of order {n} exists in GF({p})*"
        )
    g = galois.primitive_root(p)
    omega = pow(g, (p - 1) // n, p)
    return [pow(omega, i, p) for i in range(n)]

def build_local_grs(GF_, rho, n0, eval_pts=None):
    p = int(GF_.characteristic)
    if eval_pts is None:
        eval_pts = nth_roots_of_unity(n0, p)      # was make_eval_pts(n0, p)
    eval_pts = GF_([int(v) % p for v in eval_pts])
    H = GF_.Zeros((rho, n0))
    if rho > 0:
        H[0, :] = GF_(np.ones(n0, dtype=np.int64))
    for r in range(1, rho):
        H[r, :] = H[r - 1, :] * eval_pts
    return H    
# ==============================================================================
# PAPER'S EVAL POINT STRUCTURE
# ==============================================================================
def make_paper_eval_sets(omega, rho, p):
    """
    Return (Lambda_1, Lambda_2, Lambda_3, Lambda_4) -- four disjoint sets of
    sizes omega, rho, omega, rho -- using 2(omega+rho)-th roots of unity.

    Requires 2(omega+rho) | (p-1). Returns None otherwise.
    """
    n_aux = 2 * (omega + rho)
    if (p - 1) % n_aux != 0:
        return None
    g = galois.primitive_root(p)
    alpha = pow(g, (p - 1) // n_aux, p)
    L1 = [pow(alpha, j, p) for j in range(omega)]
    L2 = [pow(alpha, omega + j, p) for j in range(rho)]
    L3 = [pow(alpha, omega + rho + j, p) for j in range(omega)]
    L4 = [pow(alpha, 2 * omega + rho + j, p) for j in range(rho)]
    return L1, L2, L3, L4


def block_eval_pts(i, omega, rho, L1, L2, L3, L4):
    """
    Eval points for block i's support in layout [info_left, parity, info_right].
    Even i: (L1, L2, L3).  Odd i: (L3, L4, L1).
    """
    if i % 2 == 0:
        return L1 + L2 + L3
    return L3 + L4 + L1


def block_support_indices(i, mu, omega, rho):
    """
    Global positions for block i in layout [info_left, parity, info_right].
    Block i occupies [i*(omega+rho), i*(omega+rho) + 2*omega + rho),
    wrapping modulo n = mu*(omega+rho).
    """
    n = mu * (omega + rho)
    start = i * (omega + rho)
    return [(start + t) % n for t in range(2 * omega + rho)]


# ==============================================================================
# PAPER'S ENCODER
# ==============================================================================
def encode_bc_paper(GF_, m, mu, lambda_, omega, rho):
    """
    Systematic encoder using the paper's coset-structured eval points.

    Requires lambda_ == 2 (the paper's auxiliary construction is only
    stated for lambda = 2).

    Segment layout (rate-0.5 case, omega = rho):
        segment 0       info (Λ₁), symbols [0*ω .. 1*ω)
        segment 1       parity (Λ₂), symbols [1*ω .. 2*ω)
        segment 2       info (Λ₃), symbols [2*ω .. 3*ω)
        segment 3       parity (Λ₄), symbols [3*ω .. 4*ω)
        ...
        segment 2μ-2    info,  symbols [(2μ-2)*ω .. (2μ-1)*ω)
        segment 2μ-1    parity, symbols [(2μ-1)*ω .. 2μ*ω)
    Every segment has size ω when ω = ρ, which is the case for rate 0.5.
    """
    if lambda_ != 2:
        raise ValueError("paper's construction is stated for lambda = 2")
    p = int(GF_.characteristic)
    Lsets = make_paper_eval_sets(omega, rho, p)
    if Lsets is None:
        raise ValueError(f"2*(omega+rho) = {2*(omega+rho)} does not divide p-1")
    L1, L2, L3, L4 = Lsets

    n = mu * (omega + rho)
    k_total = mu * omega
    c = GF_.Zeros(n)

    # ---- Info: fill the even-indexed segments (0, 2, 4, ..., 2μ-2) ----
    # Each info segment has ω symbols and is shared by exactly two adjacent
    # blocks (block i's info_right = block i+1's info_left). Writing each
    # segment ONCE is what makes the cursor advance exactly k_total times.
    #
    # Segment s starts at s * ω in the rate-0.5 case (all segments same size).
    # For general ω ≠ ρ, segment 2j starts at j*(ω+ρ) and segment 2j+1 starts
    # at j*(ω+ρ) + ω; the info segments 2j are what this loop touches.
    cursor = 0
    for j in range(mu):
        start = j * (omega + rho)          # info segment 2j begins here
        for w in range(omega):
            c[start + w] = m[cursor]
            cursor += 1
    assert cursor == k_total, (cursor, k_total)

    # ---- Parity: solve per block over its own support ----
    for i in range(mu):
        sup = block_support_indices(i, mu, omega, rho)
        pts = block_eval_pts(i, omega, rho, L1, L2, L3, L4)
        H = build_local_grs(GF_, rho, 2 * omega + rho, eval_pts=pts)
        cols_par = list(range(omega, omega + rho))          # parity columns
        cols_inf = [j for j in range(2 * omega + rho)
                    if j not in cols_par]
        H_p = H[:, cols_par]
        H_i = H[:, cols_inf]
        u = GF_([int(c[sup[j]]) for j in cols_inf])
        syn = H_i @ u
        parity_nodes = pts[omega:omega + rho]
        p_i = GF_(vandermonde_solve(
            parity_nodes, [int(v) for v in (-syn)], p))
        for k_, j in enumerate(cols_par):
            c[sup[j]] = p_i[k_]
    return c

# ==============================================================================
# BLOCK-CIRCULANT INDEX MAPS
# ==============================================================================
def get_local_indices(i, mu, lambda_, omega, rho):
    """Global symbol indices participating in block i's local parity check."""
    k_total = mu * omega
    local_parity = [k_total + i * rho + r for r in range(rho)]
    local_info = []
    for l in range(lambda_):
        target = (i + l) % mu
        start = target * omega
        for w in range(omega):
            local_info.append(start + w)
    return local_parity + local_info

def encode_bc_structured(GF_, m, mu, lambda_, omega, rho):
    """
    Systematic encoder: c = [m | p]. Parity p_i solves

        H_local * [p_i | u_i]^T = 0

    where H_local is the local GRS matrix and u_i is the overlap of lambda
    consecutive message blocks.

    Evaluation points
    -----------------
    This encoder uses ONE shared eval-point set for every block:

        eval_pts = nth_roots_of_unity(n0, p)   if n0 | (p-1)
                 = 1, 2, ..., n0                otherwise

    The same H_local is then applied to each block's support via the
    permutation in get_local_indices. Consequence: a global codeword
    position that two adjacent blocks share receives DIFFERENT eval points
    in the two blocks (because it sits at different positions in each
    block's support). This is fine for Phase 1 (each block's parity checks
    are self-consistent) but it prevents the paper's auxiliary GRS
    construction from applying, since the union of the two blocks' eval
    points is not a single coset.

    If you need the paper's auxiliary Phase 2 to actually succeed, use
    encode_bc_paper (which builds the paper's Lambda_1..Lambda_4 layout)
    instead of this function.

    Parameters
    ----------
    GF_ : galois field class
    m : GF_ vector of length k = mu * omega (the message)
    mu, lambda_, omega, rho : BC parameters

    Returns
    -------
    c : GF_ vector of length n = mu * (rho + omega)
        The systematic codeword.
    """
    p = int(GF_.characteristic)
    k_total = mu * omega
    n_tot = mu * (rho + omega)
    n0 = rho + lambda_ * omega

    # Eval point choice, mirrored by the decoder.
    if (p - 1) % n0 == 0:
        eval_pts = nth_roots_of_unity(n0, p)
    else:
        eval_pts = list(range(1, n0 + 1))

    H_local = build_local_grs(GF_, rho, n0, eval_pts=eval_pts)
    H_i = H_local[:, rho:]
    parity_nodes = eval_pts[:rho]

    m_blocks = m.reshape((mu, omega))
    c = GF_.Zeros(n_tot)
    c[:k_total] = m

    for i in range(mu):
        u_i = GF_.Zeros(lambda_ * omega)
        for l in range(lambda_):
            target = (i + l) % mu
            u_i[l * omega:(l + 1) * omega] = m_blocks[target, :]
        syn = H_i @ u_i
        p_i = GF_(vandermonde_solve(
            parity_nodes, [int(v) for v in (-syn)], p))
        c[k_total + i * rho:k_total + (i + 1) * rho] = p_i
    return c
# ==============================================================================
# SYNDROME HELPERS
# ==============================================================================
def _partial_syndrome(nodes, vals, rows, p):
    m = len(nodes)
    if m == 0:
        return [0] * rows
    nd = np.array([int(v) % p for v in nodes], dtype=object)
    vl = np.array([int(v) % p for v in vals], dtype=object)
    pw = np.ones(m, dtype=object)
    out = []
    for r in range(rows):
        if r:
            pw = pw * nd % p
        out.append(int((pw * vl).sum() % p))
    return out

def _grs_decode_arbitrary_points(received, erasure_mask, eval_pts, k_poly, p):
    """
    Erasure decoder for a GRS code with arbitrary evaluation points.

    The code is {c : sum_c eval_pts[c]^r * c_c = 0  for r = 0..rho-1},
    where rho = n - k_poly. Corrects up to rho erasures. Uses the
    transposed-Vandermonde system on the erased positions, so no coset
    or subgroup structure is required of the eval points.

    Returns (recovered, success).
    """
    n = len(eval_pts)
    if n != len(received) or n != len(erasure_mask):
        return None, False
    erased_idx = [i for i in range(n) if erasure_mask[i]]
    known_idx = [i for i in range(n) if not erasure_mask[i]]
    e = len(erased_idx)
    if e == 0:
        return [int(v) % p for v in received], True
    if e > n - k_poly:
        return None, False

    # syndrome S_r = -sum_{known} pts[c]^r * received[c], r = 0..e-1
    S = _partial_syndrome(
        [int(eval_pts[i]) for i in known_idx],
        [int(received[i]) for i in known_idx],
        e, p,
    )
    S = [(-v) % p for v in S]

    # solve sum_{erased} pts[c]^r * c_c = S_r  for r = 0..e-1
    nodes_e = [int(eval_pts[i]) % p for i in erased_idx]
    try:
        x = vandermonde_solve(nodes_e, S, p)
    except GFSolveError as exc:
        return None, False

    out = [int(v) % p for v in received]
    for idx, val in zip(erased_idx, x):
        out[idx] = int(val) % p
    return out, True
# ==============================================================================
# FFT-BASED GRS ERASURE DECODER
# ==============================================================================
def fft_grs_erasure_decode(received, erasure_mask, eval_pts, k_poly, p,
                            explain=False, col_mult=None):
    """
    FFT-based erasure decoder for a GRS code.

    Inputs:
        received      : list[int] length n, codeword values at eval_pts.
        erasure_mask  : list[bool] length n, True at erased positions.
        eval_pts      : list[int] length n, evaluation points forming a coset
                        of a subgroup of F_p^* of size n.
        k_poly        : message polynomial degree bound; the code corrects
                        up to n - k_poly erasures.
        p             : field characteristic.
        explain       : if True, return (result, reason) instead of just result.
        col_mult      : list[int] length n, the GRS column multipliers v_c, or
                        None if the codeword really is plain evaluations.

                        THIS MATTERS AND IS EASY TO GET WRONG. A code defined
                        by the parity check H[r, c] = x_c^r (r < rho) -- which
                        is how build_local_grs defines the BC local code -- is
                        GRS_k(x, v), whose codewords are c_j = v_j * f(x_j),
                        NOT f(x_j). Feeding raw codeword values in as if they
                        were evaluations makes the tail-coefficient check below
                        fail and the decoder bail out every single time. For
                        n-th roots of unity, prod_{j != c}(x_c - x_j) = n / x_c,
                        so v_c is proportional to x_c and passing eval_pts here
                        is correct (the constant 1/n scales f uniformly and
                        does not affect the degree).

    Returns:
        recovered list[int] on success, or None on failure.
        If explain is True, returns (recovered, reason_string).

    Complexity:
        Two NTTs of size n (O(n log n)) plus one polynomial division.
        With schoolbook division the division step is O((n - k_poly) * e).
        Replacing the divmod with Newton iteration gives the paper's claimed
        O(n log^2 n) bound.

    Requirements:
        n | (p - 1), and eval_pts must form a coset of the n-th roots of
        unity. If either fails, returns None (or (None, reason)).
    """
    def _fail(reason):
        return (None, reason) if explain else None

    n = len(eval_pts)
    if n == 0:
        return _fail("empty input")
    if n != len(received) or n != len(erasure_mask):
        return _fail("length mismatch")
    if col_mult is not None:
        if n != len(col_mult):
            return _fail("col_mult length mismatch")
        # Work in plain evaluation form: f(x_j) = c_j / v_j. Batch-invert the
        # multipliers (Montgomery's trick) so this costs one exponentiation
        # instead of n: build the running products, invert the last one, then
        # walk back peeling off a factor at a time.
        mult = [int(v) % p for v in col_mult]
        if any(v == 0 for v in mult):
            return _fail("col_mult has a zero entry")
        prefix = [1] * (n + 1)
        for j in range(n):
            prefix[j + 1] = (prefix[j] * mult[j]) % p
        running = pow(prefix[n], p - 2, p)
        received = list(received)
        for j in range(n - 1, -1, -1):
            inv_j = (running * prefix[j]) % p
            running = (running * mult[j]) % p
            received[j] = (int(received[j]) * inv_j) % p

    e = int(sum(bool(x) for x in erasure_mask))
    if e == 0:
        return ([int(x) for x in received], "no erasures") if explain else list(received)
    if e > n - k_poly:
        return _fail(f"too many erasures: {e} > {n - k_poly}")

    if (p - 1) % n != 0:
        return _fail(f"n={n} does not divide p-1")

    F = galois.GF(p)

    # Identify the subgroup H = <omega> of order n and the coset offset c
    gg = galois.primitive_root(p)
    omega_ = pow(gg, (p - 1) // n, p)
    H = [pow(omega_, j, p) for j in range(n)]
    H_index = {h: j for j, h in enumerate(H)}

    eval_pts_int = [int(a) % p for a in eval_pts]
    c = eval_pts_int[0]
    if c == 0:
        return _fail("eval point is zero")
    c_inv = pow(c, p - 2, p)

    perm = [None] * n
    for pos, a in enumerate(eval_pts_int):
        h = (a * c_inv) % p
        if h not in H_index:
            return _fail(f"eval point {a} not in coset of subgroup of size {n}")
        nat_j = H_index[h]
        if perm[nat_j] is not None:
            return _fail("duplicate evaluation point")
        perm[nat_j] = pos

    # Reorder into natural order
    rec_nat = [int(received[perm[j]]) % p for j in range(n)]
    mask_nat = [bool(erasure_mask[perm[j]]) for j in range(n)]

    # Erasure locator Z(X) = prod_{j: mask_nat[j]} (X - H[j])
    Z = galois.Poly([1], field=F)
    for j in range(n):
        if mask_nat[j]:
            Z = Z * galois.Poly([1, (-H[j]) % p], field=F)

    # NTT of Z over H
    Z_desc = [int(x) for x in Z.coeffs]
    Z_asc = list(reversed(Z_desc))
    Z_padded = Z_asc + [0] * (n - len(Z_asc))
    try:
        Z_evals = [int(x) for x in galois.ntt(Z_padded, size=n, modulus=p)]
    except Exception as exc:
        return _fail(f"NTT of locator failed: {exc}")

    # g(h_j) = r_j * Z(h_j) for survivors; 0 at erasures (since Z=0 there)
    g_evals = [0] * n
    for j in range(n):
        if not mask_nat[j]:
            g_evals[j] = (rec_nat[j] * Z_evals[j]) % p

    # INTT to coefficients
    try:
        g_coeffs = [int(x) for x in galois.intt(g_evals, size=n, modulus=p)]
    except Exception as exc:
        return _fail(f"INTT of product failed: {exc}")

    # Sanity: deg(g) < k_poly + e, so higher coefficients must vanish
    if k_poly + e < n:
        if any(v % p != 0 for v in g_coeffs[k_poly + e:]):
            return _fail("nonzero tail coefficients: input not a valid codeword")

    # Divide g by Z to recover f
    g_poly = galois.Poly(list(reversed(g_coeffs)), field=F)
    try:
        f_poly, rem = divmod(g_poly, Z)
    except Exception as exc:
        return _fail(f"polynomial division failed: {exc}")
    if rem != galois.Poly([0], field=F):
        return _fail("nonzero remainder in f = g/Z")

    f_desc = [int(x) for x in f_poly.coeffs]
    f_asc = list(reversed(f_desc))
    if len(f_asc) < k_poly:
        f_asc = f_asc + [0] * (k_poly - len(f_asc))
    elif len(f_asc) > k_poly:
        f_asc = f_asc[:k_poly]

    # Re-evaluate over H
    f_padded = f_asc + [0] * (n - k_poly)
    try:
        f_evals_nat = [int(x) for x in galois.ntt(f_padded, size=n, modulus=p)]
    except Exception as exc:
        return _fail(f"final NTT failed: {exc}")

    # Reorder back to caller's ordering
    recovered = [0] * n
    for j in range(n):
        recovered[perm[j]] = f_evals_nat[j]
    if col_mult is not None:
        # back to codeword form: c_j = v_j * f(x_j)
        recovered = [(recovered[j] * (int(col_mult[j]) % p)) % p for j in range(n)]
    return (recovered, "FFT decode succeeded") if explain else recovered


# ==============================================================================
# VERIFICATION AGAINST BC PARITY CHECKS
# ==============================================================================
def _verify_aux_solution(rec_aux, aux_positions,
                                sup_i, pts_i, sup_j, pts_j,
                                rho, p):
    """
    Verify that rec_aux satisfies the parity checks of both blocks i and j,
    using each block's own per-position eval points.

    Used by Phase 2 of dec_cbc_2_aux_ntt after the paper's auxiliary GRS
    decoder returns a candidate. The auxiliary code is a flat GRS code
    only over the *deduplicated union* of the two blocks' eval points, and
    its candidate must satisfy each block's original rho parity checks in
    order to be a legitimate BC codeword.

    Parameters
    ----------
    rec_aux : list[int], length n_aux
        Candidate values, aligned with aux_positions.
    aux_positions : list[int], length n_aux
        Global codeword indices, aligned with rec_aux. This is the
        deduplicated union of sup_i and sup_j.
    sup_i : array-like of int, length n0
        Support positions of block i (from get_local_indices).
    pts_i : list[int], length n0
        Eval points for block i, aligned with sup_i. Must be the same
        points the encoder used to define block i's parity checks.
    sup_j : array-like of int, length n0
        Support positions of block j.
    pts_j : list[int], length n0
        Eval points for block j, aligned with sup_j.
    rho : int
        Number of parity checks per block.
    p : int
        Field characteristic.

    Returns
    -------
    bool
        True iff both blocks' parity checks are satisfied by rec_aux.

    Complexity
    ----------
    Two calls to build_local_grs (O(rho * n0) each) plus two matrix-vector
    multiplies of shape (rho, n0) @ (n0,). The galois library vectorises
    these, so the cost is the same order as a single Phase-1 solve.
    """
    # Map global positions to column indices in rec_aux.
    pos_to_col = {int(g): c for c, g in enumerate(aux_positions)}
    xv = [int(v) % p for v in rec_aux]

    for sup, pts in ((sup_i, pts_i), (sup_j, pts_j)):
        sup_list = [int(g) for g in np.asarray(sup).tolist()]

        # Every support position must appear in the candidate's positions.
        try:
            block_x = [xv[pos_to_col[g]] for g in sup_list]
        except KeyError:
            # A support position is absent from the union -- cannot verify
            # against this block. Treat as failure so the caller falls back.
            return False

        n0 = len(pts)
        if len(sup_list) != n0:
            return False

        # Build this block's parity-check matrix from its own eval points.
        # This mirrors exactly what the encoder did, so the checks below
        # are the same equations the encoder enforced.
        H = build_local_grs(GF_BLS12_381, rho, n0, eval_pts=pts)
        v = GF_BLS12_381(block_x)
        syndrome = H @ v
        if np.any(np.asarray(syndrome) != 0):
            return False

    return True

def _lagrange_eval(xs, ys, target, p):
    """Evaluate the unique polynomial through (xs[i], ys[i]) at `target`."""
    result = 0
    n = len(xs)
    for i in range(n):
        num = 1
        den = 1
        xi = int(xs[i]) % p
        for j in range(n):
            if i == j:
                continue
            xj = int(xs[j]) % p
            num = (num * (target - xj)) % p
            den = (den * (xi - xj)) % p
        result = (result + int(ys[i]) * num % p * pow(den, p - 2, p)) % p
    return result

def _decode_pair_alg1(r, mask, i_1, mu, omega, rho, p,
                       eval_pts_per_block, supports):
    """
    Paper's Algorithm 1, Phase 2, for one adjacent pair (i_1, i_1+1).

    Returns (new_r, new_mask, success, reason).

    Prerequisites
    -------------
    - `supports[i]` must follow the paper's layout:
          [info_left (ω) | parity (ρ) | info_right (ω)]
      i.e. `block_support_indices(i, mu, omega, rho)`, NOT get_local_indices.
    - `eval_pts_per_block[i]` must be the paper's per-block eval points:
          even i: Λ₁ + Λ₂ + Λ₃
          odd  i: Λ₃ + Λ₄ + Λ₁
      i.e. `block_eval_pts(i, omega, rho, L1, L2, L3, L4)`.
    """
    i_2 = (i_1 + 1) % mu
    sup_1 = supports[i_1]
    sup_2 = supports[i_2]
    pts_1 = eval_pts_per_block[i_1]
    pts_2 = eval_pts_per_block[i_2]
    n = mu * (omega + rho)
    shift = 2 * (omega + rho)

    # Recover the four Λ sets. Assumes i_1 is even (Λ₁,Λ₂,Λ₃ layout).
    # If i_1 is odd, swap the roles.
    if i_1 % 2 == 0:
        L1 = list(pts_1[:omega])
        L2 = list(pts_1[omega:omega + rho])
        L3 = list(pts_1[omega + rho:])
        L4 = list(pts_2[omega:omega + rho])
    else:
        L3 = list(pts_1[:omega])
        L4 = list(pts_1[omega:omega + rho])
        L1 = list(pts_1[omega + rho:])
        L2 = list(pts_2[omega:omega + rho])

    # Auxiliary code eval points, paper's order: Λ₁, Λ₂, Λ₃, Λ₄.
    aux_pts = L1 + L2 + L3 + L4
    # ===== DEBUG 3: verify that j + shift mod n lands on a position
    # whose eval point matches pts_1[k], for a few sample k values. =====
    for k0 in (0, 1, omega - 1):
        j0 = int(sup_1[k0])
        jp0 = (j0 + shift) % n
        pt_at_j0_in_block_1 = pts_1[k0]
        sup_2_list = [int(g) for g in sup_2]
        if jp0 in sup_2_list:
            idx = sup_2_list.index(jp0)
            pt_at_jp0_in_block_2 = pts_2[idx]
            print(f"    shift check k={k0}: j={j0} jp={jp0} "
                  f"pts_1={pt_at_j0_in_block_1} pts_2={pt_at_jp0_in_block_2} "
                  f"match={pt_at_j0_in_block_1 == pt_at_jp0_in_block_2}")
        else:
            print(f"    shift check k={k0}: j={j0} jp={jp0} "
                  f"NOT IN sup_2  <-- layout mismatch")
    # --- Step 1: build ŝ (length 2ω+ρ), aligned with sup_1 ---
    s_hat = [0] * (2 * omega + rho)
    s_hat_mask = [True] * (2 * omega + rho)
    
    # B_{1,1} (info_left): ŝ_j = r[j] - r[j + 2(ρ+ω)]
    for k in range(omega):
        j = int(sup_1[k])
        jp = (j + shift) % n
        if not mask[j] and not mask[jp]:
            s_hat[k] = (int(r[j]) - int(r[jp])) % p
            s_hat_mask[k] = False

    s_hat_erased = sum(1 for m in s_hat_mask if m)
    print(f"    ŝ: length={len(s_hat)}, erased={s_hat_erased}, "
        f"capacity={len(s_hat) - 2*omega}")
    # B_{1,0} (parity): erased
    # (stays masked)
    # B_{1,2} (info_right): value 0
    for k in range(omega + rho, 2 * omega + rho):
        s_hat[k] = 0
        s_hat_mask[k] = False
    # --- Step 2: decode ŝ with the local code (arbitrary-points GRS) ---
    s_dec, ok = _grs_decode_arbitrary_points(
        s_hat, s_hat_mask, pts_1, k_poly=2 * omega, p=p,
    )
    if not ok:
        return r, mask, False, "ŝ decode failed (arbitrary-points GRS)"

    # --- Evaluate s at Λ₄ (positions not in pts_1) ---
    # Use 2ω of the known (pts_1, s_dec) pairs to interpolate s.
    interp_xs = list(pts_1[:2 * omega])
    interp_ys = list(s_dec[:2 * omega])
    s_L4 = [_lagrange_eval(interp_xs, interp_ys, a, p) for a in L4]

    # --- Step 3: build û_1 (auxiliary codeword with message m_1) ---
    u_1 = [0] * (2 * omega + 2 * rho)
    u_1_mask = [True] * (2 * omega + 2 * rho)

    # Λ₁ from B_{1,1}: r[j] = m_1(L1[k])
    for k in range(omega):
        j = int(sup_1[k])
        if not mask[j]:
            u_1[k] = int(r[j])
            u_1_mask[k] = False
    # Λ₂ from B_{1,0}
    for k in range(omega, omega + rho):
        j = int(sup_1[k])
        if not mask[j]:
            u_1[k] = int(r[j])
            u_1_mask[k] = False
    # Λ₃ from B_{1,2}
    for k in range(omega + rho, 2 * omega + rho):
        j = int(sup_1[k])
        if not mask[j]:
            u_1[k] = int(r[j])
            u_1_mask[k] = False
    # Λ₄ from B_{2,0} (parity of block 2) + s(L4)
    # B_{2,0} positions = sup_2[ω:ω+ρ]
    for t in range(rho):
        j = int(sup_2[omega + t])
        k = 2 * omega + rho + t
        if not mask[j]:
            u_1[k] = (int(r[j]) + s_L4[t]) % p
            u_1_mask[k] = False

    res_1 = fft_grs_erasure_decode(
        u_1, u_1_mask, aux_pts, k_poly=2 * omega, p=p, explain=True,
        col_mult=aux_pts,
    )
    m_1_dec, reason_1 = res_1
    if m_1_dec is None:
        return r, mask, False, f"û_1 decode failed: {reason_1}"

    # --- Step 3b: build û_2 (auxiliary codeword with message m_2) ---
    u_2 = [0] * (2 * omega + 2 * rho)
    u_2_mask = [True] * (2 * omega + 2 * rho)

    # Λ₁ from B_{2,2}: positions sup_2[ω+ρ:]
    for t in range(omega):
        j = int(sup_2[omega + rho + t])
        if not mask[j]:
            u_2[t] = int(r[j])
            u_2_mask[t] = False
    # Λ₂ from B_{1,0} with −s adjustment: sup_1[ω+t], s_dec[ω+t]
    for t in range(rho):
        j = int(sup_1[omega + t])
        k = omega + t
        if not mask[j]:
            u_2[k] = (int(r[j]) - s_dec[k]) % p
            u_2_mask[k] = False
    # Λ₃ from B_{2,1}: positions sup_2[:ω]
    for t in range(omega):
        j = int(sup_2[t])
        k = omega + rho + t
        if not mask[j]:
            u_2[k] = int(r[j])
            u_2_mask[k] = False
    # Λ₄ from B_{2,0}: positions sup_2[ω+t]
    for t in range(rho):
        j = int(sup_2[omega + t])
        k = 2 * omega + rho + t
        if not mask[j]:
            u_2[k] = int(r[j])
            u_2_mask[k] = False

    res_2 = fft_grs_erasure_decode(
        u_2, u_2_mask, aux_pts, k_poly=2 * omega, p=p, explain=True,
        col_mult=aux_pts,
    )
    m_2_dec, reason_2 = res_2
    if m_2_dec is None:
        return r, mask, False, f"û_2 decode failed: {reason_2}"

    # --- Step 4: write back recovered values ---
    new_r = r.copy()
    new_mask = mask.copy()

    # m_1_dec[k] is m_1 at aux_pts[k]. Map aux_pts indices to sup_1 positions.
    # Λ₁ → B_{1,1}: sup_1[0..ω)
    for k in range(omega):
        j = int(sup_1[k])
        if new_mask[j]:
            new_r[j] = GF_BLS12_381(m_1_dec[k])
            new_mask[j] = False
    # Λ₂ → B_{1,0}: sup_1[ω..ω+ρ)
    for t in range(rho):
        j = int(sup_1[omega + t])
        if new_mask[j]:
            new_r[j] = GF_BLS12_381(m_1_dec[omega + t])
            new_mask[j] = False
    # Λ₃ → B_{1,2}: sup_1[ω+ρ..2ω+ρ)
    for t in range(omega):
        j = int(sup_1[omega + rho + t])
        if new_mask[j]:
            new_r[j] = GF_BLS12_381(m_1_dec[omega + rho + t])
            new_mask[j] = False

    # m_2_dec[k] is m_2 at aux_pts[k]. Map to sup_2 positions.
    # Λ₁ → B_{2,2}: sup_2[ω+ρ..2ω+ρ)
    for t in range(omega):
        j = int(sup_2[omega + rho + t])
        if new_mask[j]:
            new_r[j] = GF_BLS12_381(m_2_dec[t])
            new_mask[j] = False
    # Λ₃ → B_{2,1}: sup_2[0..ω)
    for t in range(omega):
        j = int(sup_2[t])
        if new_mask[j]:
            new_r[j] = GF_BLS12_381(m_2_dec[omega + rho + t])
            new_mask[j] = False
    # Λ₄ → B_{2,0}: sup_2[ω..ω+ρ)
    for t in range(rho):
        j = int(sup_2[omega + t])
        if new_mask[j]:
            new_r[j] = GF_BLS12_381(m_2_dec[2 * omega + rho + t])
            new_mask[j] = False

    return new_r, new_mask, True, "Algorithm 1 succeeded"
# ==============================================================================
# PAIRWISE DECODER -- FFT first, Gaussian fallback
# ==============================================================================
def dec_cbc_2_aux_ntt(r_in, mask_in, mu, lambda_, omega, rho,
                      pair_unknown_cap=None, verbose=True,
                      eval_pts_per_block=None):
    """
    Two-phase BC decoder.

    Phase 1 -- single block.
        Every block with <= rho erasures is decoded with vandermonde_solve
        on the block's own eval points. FFT is not attempted at this phase:
        at e <= rho the O(e^2) Vandermonde solve beats the FFT path's
        O(n0 log n0 + k0 * e) once the two transforms and the schoolbook
        polynomial division are counted. See the NTT section of
        docs/benchmark_1D_2D_BC_report.md for the measurement.

    Phase 2 -- adjacent pair.
        The paper's auxiliary [2(omega+rho), 2*omega, 2*rho+1] GRS code is
        built over the union of the two blocks' eval points
        (Lambda_1 U Lambda_2 U Lambda_3 U Lambda_4), decoded with NTT via
        fft_grs_erasure_decode, and verified against the two blocks'
        parity checks. On failure, either falls back to Gaussian
        elimination on the stacked BC parity checks (default), or skips
        the pair (phase2_fft_only=True).

    PREREQUISITE
    ------------
    The paper's auxiliary construction only applies when the encoder uses
    the paper's coset-structured eval points: four disjoint sets
    Lambda_1, Lambda_2, Lambda_3, Lambda_4 of sizes omega, rho, omega,
    rho, with even blocks using (Lambda_1, Lambda_2, Lambda_3) and odd
    blocks using (Lambda_3, Lambda_4, Lambda_1). If eval_pts_per_block is
    None, the decoder falls back to roots of unity per block, the union
    size will not be 2*(omega+rho), and Phase 2 will route to the Gaussian
    fallback every time.

    Parameters
    ----------
    pair_unknown_cap : int, optional
        Skip pairs with more than this many erasures. Default 2*rho.
    verbose : bool
        Print per-phase stats at the end.
    use_fft_phase2 : bool
        Attempt the FFT auxiliary decode in Phase 2. Set False to skip
        directly to the Gaussian fallback.
    phase2_fft_only : bool
        If True, skip the Gaussian fallback in Phase 2 and leave pairs
        that FFT could not resolve honestly flagged.
    eval_pts_per_block : list[list[int]], optional
        Per-block eval points aligned with get_local_indices(i, ...).
        Must be supplied for the paper's auxiliary construction to
        succeed. See make_paper_eval_sets / block_eval_pts for the
        canonical paper layout.

    Returns
    -------
    (recovered, remaining_mask)
    """
    p = int(GF_BLS12_381.characteristic)
    r = r_in.copy()
    mask = mask_in.copy()
    cap = 2 * rho if pair_unknown_cap is None else int(pair_unknown_cap)

    # Decoder: use get_local_indices-based supports and shared roots-of-unity eval points
    if lambda_ != 2:
        
        n0_local = rho + lambda_ * omega
        eval_pts_shared = nth_roots_of_unity(n0_local, P_FIELD)
        eval_pts_per_block = [eval_pts_shared for _ in range(mu)]
        supports = [np.asarray(get_local_indices(i, mu, lambda_, omega, rho))
            for i in range(mu)]
    else:
        supports = [np.asarray(block_support_indices(i, mu, omega, rho))
            for i in range(mu)]

    # Phase 1 eval points: caller-supplied if using the paper's layout,
    # roots of unity otherwise (matching the current encoder).
    if eval_pts_per_block is None:
        Lsets = make_paper_eval_sets(omega, rho, p)
        if Lsets is None:
            raise ValueError("paper's construction requires 2(omega+rho) | (p-1)")
        L1, L2, L3, L4 = Lsets
        eval_pts_per_block = [
            block_eval_pts(i, omega, rho, L1, L2, L3, L4) for i in range(mu)
        ]

    stats = {
        "phase1_vandermonde_ok": 0,
        "phase1_skipped": 0,
        "phase2_fft_ok": 0,
        "phase2_gauss_ok": 0,
        "phase2_skipped_cap": 0,
        "phase2_skipped_fft_only": 0,
        "fallback_reasons": {},
    }

    def _note(tag, reason):
        k = f"{tag}: {reason}"
        stats["fallback_reasons"][k] = stats["fallback_reasons"].get(k, 0) + 1

    progress = True
    iterations = 0

    while np.any(mask) and progress:
        progress = False
        iterations += 1

        # ---------------- PHASE 1: single block, Vandermonde only ----------------
        for i in range(mu):
            sup = supports[i]
            local_mask = mask[sup]
            num_local = int(np.count_nonzero(local_mask))
            if not (0 < num_local <= rho):
                continue
            erased_pos = np.nonzero(local_mask)[0]
            known_pos = np.nonzero(~local_mask)[0]
            e = num_local
            rows_needed = min(e + 2, rho)
            nodes_all = eval_pts_per_block[i]

            S = _partial_syndrome(
                [nodes_all[int(c)] for c in known_pos],
                [int(v) for v in r[sup[known_pos]]],
                rows_needed, p,
            )
            syndrome = [(-v) % p for v in S]
            nodes_e = [nodes_all[int(c)] for c in erased_pos]

            try:
                x = vandermonde_solve(nodes_e, syndrome[:e], p)
            except GFSolveError as exc:
                _note("phase1", f"vandermonde failed ({exc})")
                stats["phase1_skipped"] += 1
                continue

            consistent = True
            for rr in range(e, rows_needed):
                acc = sum(pow(nd_, rr, p) * xv
                          for nd_, xv in zip(nodes_e, x)) % p
                if acc != syndrome[rr]:
                    consistent = False
                    break
            if not consistent:
                _note("phase1", "consistency check failed")
                stats["phase1_skipped"] += 1
                continue

            r[sup[erased_pos]] = GF_BLS12_381(np.array(x, dtype=object))
            mask[sup[erased_pos]] = False
            progress = True
            stats["phase1_vandermonde_ok"] += 1
        print(f"Iteration {iterations}: Phase 1 done,")
        # ---------------- PHASE 2: adjacent pair, paper's auxiliary GRS ----------------
        print(f"Phase 2 starting, progress={progress}, ")
                # ---------------- PHASE 2: adjacent pair, Algorithm 1 only ----------------
        if not progress and np.any(mask):
            for i in range(mu):
                next_i = (i + 1) % mu
                if next_i == i:
                    continue

                sup_i, sup_j = supports[i], supports[next_i]
                combined = np.array(
                    sorted(set(sup_i.tolist()) | set(sup_j.tolist())))
                pair_mask = mask[combined]
                num_pair = int(np.count_nonzero(pair_mask))

                if not (0 < num_pair <= 2 * rho):
                    continue
                if num_pair > cap:
                    stats["phase2_skipped_cap"] += 1
                    _note("phase2", f"over compute cap ({num_pair} > {cap})")
                    continue

                # Algorithm 1. No Gaussian fallback: if the auxiliary
                # construction cannot resolve the pair, the pair's erasures
                # stay honestly flagged and the decoder moves on. This is
                # deliberate -- at benchmark sizes the Gaussian fallback is
                # O(e^3) and takes hours per pair, so it is not a decoder
                # any deployment would use. See the NTT section of
                # docs/benchmark_1D_2D_BC_report.md.

                new_r, new_mask, ok, reason = _decode_pair_alg1(
                    r, mask, i, mu, omega, rho, p,
                    eval_pts_per_block, supports)
                if ok:
                    r = new_r
                    mask = new_mask
                    progress = True
                    stats["phase2_fft_ok"] += 1
                else:
                    _note("phase2", f"Algorithm 1 failed ({reason})")

                

    if verbose:
        print(f"dec_cbc_2_aux_ntt: {iterations} iterations")
        print(f"  Phase 1 (Vandermonde only): "
            f"{stats['phase1_vandermonde_ok']} blocks recovered, "
            f"{stats['phase1_skipped']} skipped")
        print(f"  Phase 2 (Algorithm 1 only): "
            f"FFT={stats['phase2_fft_ok']}, "
            f"skipped(cap)={stats['phase2_skipped_cap']}")
        if stats["fallback_reasons"]:
            print("  Fallback reasons:")
            for reason, count in sorted(stats["fallback_reasons"].items(),
                                        key=lambda kv: -kv[1]):
                print(f"    [{count:5d}x] {reason}")
    return r, mask


# ==============================================================================
# BENCHMARK WRAPPER
# ==============================================================================
def dec_cbc_2(H_BC, r_in, mask_in, mu, lambda_, omega, rho,
              pair_unknown_cap=None):
    """Signature-compatible wrapper for the benchmark."""
    return dec_cbc_2_aux_ntt(
        r_in, mask_in, mu, lambda_, omega, rho,
        pair_unknown_cap=pair_unknown_cap, verbose=False)
# ==============================================================================
# DEMO
# ==============================================================================
if __name__ == "__main__":
    print(f"--- BC Code demo ---")
    print(f"Parameters: mu={mu}, lambda={lambda_}, omega={omega}, rho={rho}")
    print(f"Global [n, k, d]: [{n}, {k}, {d}]")
    print(f"Local code length n0: {n0}")
    print(f"n0 | (p-1): {(P_FIELD - 1) % n0 == 0}\n")

    print("Encoding...")
    full_blob = random_blob()
    message = GF_BLS12_381(full_blob)
    t0 = time.time()
    if lambda_ == 2:
        encoded = encode_bc_paper(GF_BLS12_381, message, mu, lambda_, omega, rho)
    else:
        encoded = encode_bc_structured(GF_BLS12_381, message, mu, lambda_, omega, rho)
    print(f"Encoded in {time.time() - t0:.2f}s\n")
    num_erasures = int(rho * 2)
    erased_indices = sorted(np.random.choice(n, num_erasures, replace=False).tolist())
    received = encoded.copy()
    mask = np.zeros(n, dtype=bool)
    for idx in erased_indices:
        mask[idx] = True
        received[idx] = GF_BLS12_381(0)
    print(f"Injected {num_erasures} erasures")

    t0 = time.time()
    recovered, remaining = dec_cbc_2_aux_ntt(
        received, mask, mu, lambda_, omega, rho, verbose=True)
    print(f"Decoded in {time.time() - t0:.2f}s")
    print(f"Remaining erasures: {int(remaining.sum())}")
    print(f"Exact match: {bool(np.array_equal(recovered, encoded))}")