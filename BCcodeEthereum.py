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
omega = 2048
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
    """Raised when A * x = b has no unique solution over GF(p)."""


def gf_solve(A, b, require_unique=True):
    """Solve A x = b over GF(p) by Gauss-Jordan elimination with rank check."""
    A = A.copy(); b = b.copy()
    m, n_ = A.shape
    row = 0
    col_map = []
    for col in range(n_):
        if row >= m:
            break
        pivot = -1
        for r in range(row, m):
            if A[r, col] != 0:
                pivot = r
                break
        if pivot == -1:
            continue
        if pivot != row:
            A[[row, pivot]] = A[[pivot, row]]
            b[[row, pivot]] = b[[pivot, row]]
        inv = A[row, col] ** -1
        A[row, :] = A[row, :] * inv
        b[row] = b[row] * inv
        factors = A[:, col].copy(); factors[row] = 0
        nz = np.nonzero(factors != 0)[0]
        if nz.size:
            f = factors[nz]
            A[nz, :] = A[nz, :] - f.reshape(-1, 1) * A[row, :].reshape(1, -1)
            b[nz] = b[nz] - f * b[row]
        col_map.append((row, col)); row += 1
    if require_unique:
        pivot_rows = {r for r, _ in col_map}
        for r in range(m):
            if r not in pivot_rows and not np.any(A[r, :] != 0) and b[r] != 0:
                raise GFSolveError(f"inconsistent: 0 = {int(b[r])}")
        if len(col_map) < n_:
            raise GFSolveError(f"underdetermined: rank {len(col_map)} < {n_}")
    x = GF_BLS12_381.Zeros(n_)
    for r, c in col_map:
        x[c] = b[r]
    return x


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


# ==============================================================================
# EVALUATION POINTS -- n0-th roots of unity
# ==============================================================================
def make_eval_pts(n0_local, p):
    """
    Return the n0_local-th roots of unity in ascending power order:
        [omega^0, omega^1, ..., omega^(n0_local-1)]
    Requires n0_local | (p - 1). Raises otherwise.
    """
    if (p - 1) % n0_local != 0:
        raise ValueError(
            f"n0 = {n0_local} does not divide p - 1; roots of unity do not exist"
        )
    g = galois.primitive_root(p)
    omega_ = pow(g, (p - 1) // n0_local, p)
    return [pow(omega_, i, p) for i in range(n0_local)]


# ==============================================================================
# LOCAL GRS MATRIX (uses roots of unity)
# ==============================================================================
def build_local_grs(GF_, rho, n0, eval_pts=None):
    """
    Local GRS parity-check matrix H_local[r, c] = eval_pts[c] ** r, r < rho.

    If eval_pts is None, defaults to n0-th roots of unity (requires n0 | p-1).
    Pass eval_pts to override (e.g., with the paper's integer points for
    comparison).
    """
    p = int(GF_.characteristic)
    if eval_pts is None:
        eval_pts = make_eval_pts(n0, p)
    eval_pts = GF_([int(v) % p for v in eval_pts])
    H = GF_.Zeros((rho, n0))
    if rho > 0:
        H[0, :] = GF_(np.ones(n0, dtype=np.int64))
    for r in range(1, rho):
        H[r, :] = H[r - 1, :] * eval_pts
    return H


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


# ==============================================================================
# ENCODER -- systematic, local GRS with roots of unity
# ==============================================================================
def encode_bc_structured(GF_, m, mu, lambda_, omega, rho):
    """
    Systematic encoder: c = [m | p]. Parity p_i solves
        H_local * [p_i | u_i]^T = 0
    where H_local is the local GRS matrix (roots of unity as evaluation
    points), and u_i is the overlap of lambda consecutive message blocks.
    """
    p = int(GF_.characteristic)
    k_total = mu * omega
    n_tot = mu * (rho + omega)
    n0 = rho + lambda_ * omega

    eval_pts = make_eval_pts(n0, p) if (p - 1) % n0 == 0 else list(range(1, n0 + 1))
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


def _vander_rows(nodes, rows, p):
    m = len(nodes)
    nd = np.array([int(v) % p for v in nodes], dtype=object)
    M = np.zeros((rows, m), dtype=object)
    cur = np.ones(m, dtype=object)
    for r in range(rows):
        if r:
            cur = cur * nd % p
        M[r, :] = cur
    return M


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
def _verify_aux_solution(rec_aux, combined, sup_i, sup_j,
                          rho, lambda_, omega, p):
    """Verify rec_aux satisfies the actual BC stacked parity checks for
    blocks i and j over the union `combined`."""
    lm_i = {int(g): c for c, g in enumerate(sup_i)}
    lm_j = {int(g): c for c, g in enumerate(sup_j)}
    cols_i = [(c, lm_i[int(g)]) for c, g in enumerate(combined)
              if int(g) in lm_i]
    cols_j = [(c, lm_j[int(g)]) for c, g in enumerate(combined)
              if int(g) in lm_j]
    n0 = rho + lambda_ * omega
    if (p - 1) % n0 == 0:
        eval_pts_local = make_eval_pts(n0, p)
    else:
        eval_pts_local = list(range(1, n0 + 1))

    xv = [int(v) % p for v in rec_aux]
    for cols in (cols_i, cols_j):
        pw = [1] * len(cols)
        xa = [xv[c] for c, _ in cols]
        for r in range(rho):
            if r:
                pw = [pw[k] * eval_pts_local[cols[k][1]] % p
                      for k in range(len(cols))]
            if sum(pw[k] * xa[k] for k in range(len(cols))) % p != 0:
                return False
    return True


# ==============================================================================
# PAIRWISE DECODER -- FFT first, Gaussian fallback
# ==============================================================================
def dec_cbc_2_aux_ntt(r_in, mask_in, mu, lambda_, omega, rho,
                      pair_unknown_cap=None, verbose=True,
                      use_fft_phase1=True, use_fft_phase2=True):
    """
    Two-phase BC decoder.

    Phase 1: for each block with <= rho erasures, try FFT-based single-block
             decode. Fall back to vandermonde_solve if FFT is unavailable or
             fails.
    Phase 2: for each adjacent pair with <= 2*rho erasures, try FFT-based
             decode of the union. Fall back to Gaussian elimination.

    use_fft_phase1 / use_fft_phase2 exist so the two paths can be measured
    against each other rather than argued about. Phase 1 is the interesting
    one: it admits at most rho erasures and k_poly = n0 - rho, so the FFT
    path's schoolbook division costs O(rho*e) while vandermonde_solve costs
    O(e^2), and e <= rho makes the Vandermonde solve the cheaper of the two
    before the two NTTs are even counted. Setting use_fft_phase1=False
    selects that cheaper path. Phase 2 is the opposite case -- its fallback
    is Gaussian O(e^3) -- so there the FFT should win where it is available
    at all.

    Every fallback prints a reason when verbose=True.
    """
    p = int(GF_BLS12_381.characteristic)
    r = r_in.copy()
    mask = mask_in.copy()
    cap = 2 * rho if pair_unknown_cap is None else int(pair_unknown_cap)

    n0_local = rho + lambda_ * omega
    # These are two different things and conflating them is a trap: the
    # evaluation points DEFINE the code (the encoder uses the same ones), so
    # the Vandermonde path needs them just as much as the FFT path does.
    # Gating eval_pts_local on the FFT switch silently breaks the fallback.
    fft_available = ((p - 1) % n0_local == 0)
    eval_pts_local = make_eval_pts(n0_local, p) if fft_available else None
    has_fft_phase1 = use_fft_phase1 and fft_available

    supports = [np.asarray(get_local_indices(i, mu, lambda_, omega, rho))
                for i in range(mu)]
    locmaps = [{int(g): c for c, g in enumerate(sup)} for sup in supports]

    progress = True
    iterations = 0
    stats = {
        "phase1_fft_ok": 0,
        "phase1_vandermonde_ok": 0,
        "phase1_skipped": 0,
        "phase2_fft_ok": 0,
        "phase2_gauss_ok": 0,
        "phase2_skipped": 0,
        "fallback_reasons": {},
    }

    def _note_fallback(tag, reason):
        key = f"{tag}: {reason}"
        stats["fallback_reasons"][key] = stats["fallback_reasons"].get(key, 0) + 1

    while np.any(mask) and progress:
        progress = False
        iterations += 1

        # ---------------- PHASE 1: single block ----------------
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

            fixed = False

            # ---- Phase 1a: try FFT ----
            if has_fft_phase1:
                # Local codeword values in support order
                local_rec = [int(r[g]) if not mask[g] else 0 for g in sup]
                local_mask_list = [bool(mask[g]) for g in sup]
                # Local code is n0 symbols, dimension k0 = n0 - rho
                res = fft_grs_erasure_decode(
                    local_rec, local_mask_list, eval_pts_local,
                    k_poly=n0_local - rho, p=p, explain=True,
                    col_mult=eval_pts_local,
                )
                fft_out, reason = res
                if fft_out is not None:
                    # Verify against stacked BC parity checks
                    if _verify_aux_solution(
                            fft_out, sup, sup, sup, rho, lambda_, omega, p):
                        for k_, g in enumerate(sup):
                            if mask[g]:
                                r[g] = GF_BLS12_381(fft_out[k_])
                                mask[g] = False
                        progress = True
                        fixed = True
                        stats["phase1_fft_ok"] += 1
                    else:
                        _note_fallback("phase1", "FFT candidate failed verification")
                else:
                    _note_fallback("phase1", f"FFT unavailable/failed ({reason})")
            elif not fft_available:
                _note_fallback("phase1", f"n0={n0_local} does not divide p-1")
            else:
                _note_fallback("phase1", "FFT disabled by use_fft_phase1=False")

            if fixed:
                continue

            # ---- Phase 1b: fallback to vandermonde_solve ----
            # Must track the ENCODER's choice of evaluation points, which
            # depends on the field (fft_available), never on whether the FFT
            # decode path happens to be switched on.
            nodes_all = eval_pts_local if fft_available else list(range(1, n0_local + 1))
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
                _note_fallback("phase1", f"vandermonde_solve failed ({exc})")
                continue
            consistent = True
            for rr in range(e, rows_needed):
                acc = sum(pow(nd_, rr, p) * xv
                          for nd_, xv in zip(nodes_e, x)) % p
                if acc != syndrome[rr]:
                    consistent = False
                    break
            if not consistent:
                _note_fallback("phase1", "vandermonde consistency check failed")
                continue
            r[sup[erased_pos]] = GF_BLS12_381(np.array(x, dtype=object))
            mask[sup[erased_pos]] = False
            progress = True
            stats["phase1_vandermonde_ok"] += 1

        # ---------------- PHASE 2: pairwise ----------------
        if not progress and np.any(mask):
            for i in range(mu):
                next_i = (i + 1) % mu
                if next_i == i:
                    continue
                sup_i, sup_j = supports[i], supports[next_i]
                combined = np.array(
                    sorted(set(sup_i.tolist()) | set(sup_j.tolist())))
                n_aux = len(combined)
                pair_mask = mask[combined]
                num_pair = int(np.count_nonzero(pair_mask))

                if not (0 < num_pair <= 2 * rho):
                    continue
                if num_pair > cap:
                    stats["phase2_skipped"] += 1
                    _note_fallback("phase2",
                                    f"over compute cap ({num_pair} > {cap})")
                    continue

                fixed = False

                # ---- Phase 2a: try FFT on flat union ----
                if use_fft_phase2 and (p - 1) % n_aux == 0:
                    eval_pts_aux = make_eval_pts(n_aux, p)
                    k_aux = n_aux - 2 * rho
                    if k_aux > 0:
                        rec_aux = [int(r[g]) if not mask[g] else 0
                                   for g in combined]
                        mask_aux = [bool(mask[g]) for g in combined]
                        res = fft_grs_erasure_decode(
                            rec_aux, mask_aux, eval_pts_aux,
                            k_poly=k_aux, p=p, explain=True,
                        )
                        fft_out, reason = res
                        if fft_out is not None:
                            if _verify_aux_solution(
                                    fft_out, combined, sup_i, sup_j,
                                    rho, lambda_, omega, p):
                                for k_, g in enumerate(combined):
                                    if mask[g]:
                                        r[g] = GF_BLS12_381(fft_out[k_])
                                        mask[g] = False
                                progress = True
                                fixed = True
                                stats["phase2_fft_ok"] += 1
                            else:
                                _note_fallback(
                                    "phase2",
                                    "FFT candidate failed verification")
                        else:
                            _note_fallback("phase2",
                                            f"FFT failed ({reason})")
                    else:
                        _note_fallback("phase2", "k_aux <= 0")
                else:
                    _note_fallback(
                        "phase2",
                        f"n_aux={n_aux} does not divide p-1")

                if fixed:
                    continue

                # ---- Phase 2b: Gaussian fallback ----
                e = num_pair
                erased_g = combined[np.nonzero(pair_mask)[0]]
                syndrome = []
                for blk in (i, next_i):
                    sup = supports[blk]
                    kn = np.nonzero(~mask[sup])[0]
                    nodes_blk = (eval_pts_local if has_fft_phase1
                                 else list(range(1, n0_local + 1)))
                    S = _partial_syndrome(
                        [nodes_blk[int(c)] for c in kn],
                        [int(v) for v in r[sup[kn]]],
                        rho, p,
                    )
                    syndrome.extend([(-v) % p for v in S])

                top = np.zeros((rho, e), dtype=object)
                bot = np.zeros((rho, e), dtype=object)
                for half, blk in ((top, i), (bot, next_i)):
                    lm = locmaps[blk]
                    hit = [(t, lm[int(g)]) for t, g in enumerate(erased_g)
                           if int(g) in lm]
                    if hit:
                        cols, nds_idx = zip(*hit)
                        nodes_blk = (eval_pts_local if has_fft_phase1
                                     else list(range(1, n0_local + 1)))
                        nds = [nodes_blk[idx] for idx in nds_idx]
                        half[:, list(cols)] = _vander_rows(nds, rho, p)
                H_e = GF_BLS12_381(np.vstack([top, bot]))
                syn_v = GF_BLS12_381(np.array(syndrome, dtype=object))

                sol = None
                for nrows in (min(2 * rho, e + 8), 2 * rho):
                    try:
                        cand = gf_solve(H_e[:nrows, :], syn_v[:nrows])
                    except GFSolveError as exc:
                        _note_fallback("phase2",
                                        f"Gaussian: {exc}")
                        continue
                    if nrows < 2 * rho:
                        chk = H_e[nrows:nrows + 2, :] @ cand
                        if not np.array_equal(
                                np.asarray(chk),
                                np.asarray(syn_v[nrows:nrows + 2])):
                            _note_fallback("phase2",
                                            "Gaussian consistency check failed")
                            continue
                    sol = cand
                    break
                if sol is None:
                    continue
                r[erased_g] = sol
                mask[erased_g] = False
                progress = True
                stats["phase2_gauss_ok"] += 1

    if verbose:
        print(f"dec_cbc_2_aux_ntt: {iterations} iterations")
        print(f"  Phase 1: FFT={stats['phase1_fft_ok']}, "
              f"Vandermonde={stats['phase1_vandermonde_ok']}")
        print(f"  Phase 2: FFT={stats['phase2_fft_ok']}, "
              f"Gaussian={stats['phase2_gauss_ok']}, "
              f"skipped={stats['phase2_skipped']}")
        if stats["fallback_reasons"]:
            print(f"  Fallback reasons (aggregated):")
            for reason, count in sorted(stats["fallback_reasons"].items(),
                                        key=lambda kv: -kv[1]):
                print(f"    [{count:5d}x] {reason}")
    return r, mask


# ==============================================================================
# BENCHMARK WRAPPER
# ==============================================================================
def dec_cbc_2(H_BC, r_in, mask_in, mu, lambda_, omega, rho,
              pair_unknown_cap=None, use_fft_phase1=True, use_fft_phase2=True):
    """Signature-compatible wrapper for the benchmark."""
    return dec_cbc_2_aux_ntt(
        r_in, mask_in, mu, lambda_, omega, rho,
        pair_unknown_cap=pair_unknown_cap, verbose=False,
        use_fft_phase1=use_fft_phase1, use_fft_phase2=use_fft_phase2)


# ==============================================================================
# GENERALISED t-BLOCK DECODER (Gaussian only, unchanged in spirit)
# ==============================================================================
def dec_cbc_t(r_in, mask_in, mu, lambda_, omega, rho,
              t_max=4, unknown_cap=None, verbose=True):
    """Combine up to t_max adjacent blocks per solve; Gaussian for t >= 2."""
    p = int(GF_BLS12_381.characteristic)
    r = r_in.copy(); mask = mask_in.copy()
    if unknown_cap is None:
        unknown_cap = t_max * rho
    cap = int(unknown_cap)
    n0_local = rho + lambda_ * omega
    has_fft = (p - 1) % n0_local == 0
    nodes_all = make_eval_pts(n0_local, p) if has_fft else list(range(1, n0_local + 1))

    supports = [np.asarray(get_local_indices(i, mu, lambda_, omega, rho))
                for i in range(mu)]
    locmaps = [{int(g): c for c, g in enumerate(sup)} for sup in supports]
    progress = True
    iterations = 0
    stats = {"phase1": 0,
             **{f"phase{t}": 0 for t in range(2, t_max + 1)},
             "skipped_cap": 0, "failed_rank": 0}

    while np.any(mask) and progress:
        progress = False
        iterations += 1
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
            S = _partial_syndrome(
                [nodes_all[int(c)] for c in known_pos],
                [int(v) for v in r[sup[known_pos]]],
                rows_needed, p,
            )
            syndrome = [(-v) % p for v in S]
            nodes_e = [nodes_all[int(c)] for c in erased_pos]
            try:
                x = vandermonde_solve(nodes_e, syndrome[:e], p)
            except GFSolveError:
                continue
            if any(sum(pow(nd_, rr, p) * xv
                       for nd_, xv in zip(nodes_e, x)) % p != syndrome[rr]
                   for rr in range(e, rows_needed)):
                continue
            r[sup[erased_pos]] = GF_BLS12_381(np.array(x, dtype=object))
            mask[sup[erased_pos]] = False
            progress = True
            stats["phase1"] += 1
        if progress:
            continue
        for t in range(2, t_max + 1):
            phase_progress = False
            for i in range(mu):
                combined = set(); block_ids = []
                for j in range(t):
                    blk = (i + j) % mu
                    block_ids.append(blk)
                    combined.update(supports[blk].tolist())
                combined = np.array(sorted(combined))
                pair_mask = mask[combined]
                num_unknowns = int(np.count_nonzero(pair_mask))
                if num_unknowns == 0 or num_unknowns > t * rho:
                    continue
                if num_unknowns > cap:
                    stats["skipped_cap"] += 1
                    continue
                e = num_unknowns
                erased_g = combined[np.nonzero(pair_mask)[0]]
                syndrome = []
                for blk in block_ids:
                    sup = supports[blk]
                    kn = np.nonzero(~mask[sup])[0]
                    S = _partial_syndrome(
                        [nodes_all[int(c)] for c in kn],
                        [int(v) for v in r[sup[kn]]], rho, p,
                    )
                    syndrome.extend([(-v) % p for v in S])
                H_e = GF_BLS12_381.Zeros((t * rho, e))
                for g_idx, blk in enumerate(block_ids):
                    lm = locmaps[blk]
                    hit = [(c, lm[int(gg)]) for c, gg in enumerate(erased_g)
                           if int(gg) in lm]
                    if hit:
                        cols, nds_idx = zip(*hit)
                        nds = [nodes_all[idx] for idx in nds_idx]
                        H_e[g_idx * rho:(g_idx + 1) * rho, list(cols)] = \
                            _vander_rows(nds, rho, p)
                syn_v = GF_BLS12_381(np.array(syndrome, dtype=object))
                sol = None
                for nrows in (min(t * rho, e + 8), t * rho):
                    try:
                        cand = gf_solve(H_e[:nrows, :], syn_v[:nrows])
                    except GFSolveError:
                        stats["failed_rank"] += 1
                        continue
                    if nrows < t * rho:
                        chk = H_e[nrows:nrows + 2, :] @ cand
                        if not np.array_equal(
                                np.asarray(chk),
                                np.asarray(syn_v[nrows:nrows + 2])):
                            continue
                    sol = cand
                    break
                if sol is None:
                    continue
                r[erased_g] = sol
                mask[erased_g] = False
                phase_progress = True
                stats[f"phase{t}"] += 1
            if phase_progress:
                progress = True
                break

    if verbose:
        print(f"dec_cbc_t(t_max={t_max}): {iterations} iterations, stats={stats}")
    return r, mask, iterations, stats


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
    encoded = encode_bc_structured(GF_BLS12_381, message, mu, lambda_, omega, rho)
    print(f"Encoded in {time.time() - t0:.2f}s\n")

    num_erasures = 2 * rho
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