

# ==============================================================================
# IMPORT ETHEREUM BLOB GENERATOR (EIP-4844 / consensus-specs)
# ==============================================================================
# The blob_generator module provides:
#   - FIELD_ELEMENTS_PER_BLOB = 4096  (number of field elements in a blob)
#   - GF: a Galois field class (here BLS12‑381 prime field)
#   - random_blob(): returns a Python list of 4096 integers in GF(p)
"""
Block-Circulant erasure code for Ethereum blob scale.

Two decoders are provided:

    dec_cbc_2_aux_ntt(...)   pairwise decoder with an auxiliary-GRS path
                             using NTT, falling back to Gaussian elimination
                             on the actual stacked BC system when the NTT
                             candidate fails verification.

    dec_cbc_t(..., t_max=T)  generalised t-block decoder, Gaussian only.

IMPORTANT PREREQUISITE FOR THE NTT PATH
---------------------------------------
The auxiliary GRS decoder in `_ntt_erasure_decode_aux` treats the union of
two adjacent blocks as a code with n_aux-th ROOTS OF UNITY as evaluation
points. The BC encoder in `encode_bc_structured` uses 1, 2, ..., n0 as
evaluation points. These are different codes: a codeword of the root-of-
unity code is not, in general, a codeword of the stacked BC system.

The decoder handles this correctly -- it VERIFIES the auxiliary candidate
against the actual stacked BC parity checks before accepting it -- but the
verification will fail for the current encoder, so the NTT path is skipped
and the decoder falls back to Gaussian elimination on every pair. To make
the NTT path fire, the encoder, `build_local_grs`, and the Phase-1
`vandermonde_solve` call must all use the same root-of-unity evaluation
points, and the parameters must satisfy n0 | (p - 1).

This file therefore does NOT currently exploit NTT in the pairwise phase
at the default parameters. It is correct, but the pairwise phase is
Gaussian. That is a known, documented limitation, not a bug.
"""
from blob_generator import FIELD_ELEMENTS_PER_BLOB, GF, random_blob

# Alias for readability; GF_BLS12_381 is the field we work over.
GF_BLS12_381 = GF
import time
import numpy as np
import galois

P_FIELD = int(GF_BLS12_381.characteristic)


def _build_auxiliary_grs(n_aux, k_aux, p):
    """
    Build a Vandermonde parity-check matrix for a [n_aux, k_aux] GRS code
    over GF(p), using n_aux-th roots of unity as evaluation points.

    Returns:
        eval_pts: list of n_aux distinct evaluation points (roots of unity)
        H_aux:    (n_aux - k_aux) x n_aux GF matrix, H_aux[r,c] = eval_pts[c]^r
        None if n_aux does not divide p-1.
    """
    if (p - 1) % n_aux != 0:
        return None, None
    g = galois.primitive_root(p)
    alpha = pow(g, (p - 1) // n_aux, p)
    eval_pts = [pow(alpha, i, p) for i in range(n_aux)]
    n_parity = n_aux - k_aux
    H_aux = GF_BLS12_381.Zeros((n_parity, n_aux))
    for r in range(n_parity):
        for c in range(n_aux):
            H_aux[r, c] = pow(eval_pts[c], r, p)
    return eval_pts, H_aux


def _ntt_erasure_decode_aux(received, mask_local, n_aux, k_aux,
                             eval_pts, p):
    """
    Erasure-decode a codeword of the auxiliary GRS code using NTT.

    received:  length-n_aux list of ints (erased positions set to 0)
    mask_local: boolean array length n_aux, True where erased
    eval_pts:  length-n_aux evaluation points (must be roots of unity)

    Returns: (recovered list, success)
    """
    erased_pos = [int(i) for i in range(n_aux) if mask_local[i]]
    if not erased_pos:
        return list(received), True
    if len(erased_pos) > n_aux - k_aux:
        return list(received), False

    # Build erasure locator Z(x) = prod (x - eval_pts[i])
    Z = galois.Poly([1], field=GF_BLS12_381)
    for i in erased_pos:
        Z = Z * galois.Poly([1, (-int(eval_pts[i])) % p], field=GF_BLS12_381)

    Z_desc = [int(c) for c in Z.coeffs]
    Z_asc = list(reversed(Z_desc))
    Z_padded = Z_asc + [0] * (n_aux - len(Z_asc))
    Z_evals = [int(x) for x in galois.ntt(Z_padded, size=n_aux, modulus=p)]

    R = [int(x) for x in received]
    product_evals = [(R[j] * Z_evals[j]) % p for j in range(n_aux)]
    product_coeffs = [int(x) for x in
                      galois.intt(product_evals, size=n_aux, modulus=p)]

    Prod_poly = galois.Poly(list(reversed(product_coeffs)), field=GF_BLS12_381)
    quotient = Prod_poly // Z
    q_asc = list(reversed([int(c) for c in quotient.coeffs]))
    if len(q_asc) < k_aux:
        q_asc += [0] * (k_aux - len(q_asc))
    else:
        q_asc = q_asc[:k_aux]

    padded = q_asc + [0] * (n_aux - k_aux)
    recovered = galois.ntt(padded, size=n_aux, modulus=p)
    return [int(x) for x in recovered], True

# ==============================================================================
# HELPER: GALOIS FIELD LINEAR SYSTEM SOLVER (F_q)
# ==============================================================================
class GFSolveError(ValueError):
    """Raised when A * x = b has no unique solution over GF(p).

    This matters more than it looks: the previous version of gf_solve
    returned zero for any unknown whose column never received a pivot,
    which is indistinguishable (to the caller) from having genuinely
    solved for zero. A decoder built on top of that will happily write
    those zeros into the codeword and clear the erasure flags, reporting
    success on data it never recovered.
    """


def gf_solve(A, b, require_unique=True):
    """
    Solves A * x = b over GF(p) using Gaussian elimination (full pivoting).

    Args:
        A: GF matrix of shape (m, n)
        b: GF vector of shape (m,)
        require_unique: when True (default), raise GFSolveError unless the
            system has exactly one solution -- i.e. every column received a
            pivot (not underdetermined) and no row reduced to 0 = nonzero
            (not inconsistent). Callers that genuinely want a particular
            solution of an underdetermined system must opt out explicitly.
    Returns:
        x: GF vector of shape (n,)
    Raises:
        GFSolveError: if require_unique and the solution is not unique.
    """
    A = A.copy()
    b = b.copy()
    m, n = A.shape

    # Forward elimination with column pivoting
    row = 0
    col_map = []          # stores (row, col) of pivot positions
    for col in range(n):
        if row >= m:
            break
        # Find a non‑zero pivot in column 'col' from row 'row' downwards
        pivot = -1
        for r in range(row, m):
            if A[r, col] != 0:
                pivot = r
                break
        if pivot == -1:
            continue          # column is all zero – move to next column

        # Swap pivot row with current row
        if pivot != row:
            A[[row, pivot]] = A[[pivot, row]]
            b[[row, pivot]] = b[[pivot, row]]

        # Normalise pivot row
        inv_pivot = A[row, col] ** -1
        A[row, :] = A[row, :] * inv_pivot
        b[row] = b[row] * inv_pivot

        # Eliminate this column in all other rows (both below and above).
        # This is the same Gauss-Jordan step as before, but issued as ONE
        # broadcast update instead of a Python loop over m rows. The element
        # count is identical; what disappears is m-1 per-pivot dispatches into
        # galois' object-dtype arithmetic, which dominated the runtime once
        # these matrices grew from 2x2 to hundreds of rows.
        factors = A[:, col].copy()
        factors[row] = 0
        nz_rows = np.nonzero(factors != 0)[0]
        if nz_rows.size:
            f = factors[nz_rows]
            A[nz_rows, :] = A[nz_rows, :] - f.reshape(-1, 1) * A[row, :].reshape(1, -1)
            b[nz_rows] = b[nz_rows] - f * b[row]

        col_map.append((row, col))
        row += 1

    if require_unique:
        # Inconsistent: a row reduced to 0 = nonzero has no solution at all.
        pivot_rows = {r for r, _ in col_map}
        for r in range(m):
            if r in pivot_rows:
                continue
            if not np.any(A[r, :] != 0) and b[r] != 0:
                raise GFSolveError(
                    f"inconsistent system: row {r} reduced to 0 = {int(b[r])}")
        # Underdetermined: an unknown whose column never received a pivot is
        # NOT determined by these equations. Returning zero for it would be a
        # fabricated value, so refuse instead.
        if len(col_map) < n:
            missing = sorted(set(range(n)) - {c for _, c in col_map})
            raise GFSolveError(
                f"underdetermined system: {len(missing)} of {n} unknown(s) "
                f"have no pivot (columns {missing[:8]}) -- rank "
                f"{len(col_map)} < {n} unknowns")

    # Extract solution: only pivot columns have values; others remain zero
    x = GF_BLS12_381.Zeros(n)
    for r, c in col_map:
        x[c] = b[r]
    return x

def vandermonde_solve(nodes, s, p):
    """Solve  sum_j nodes[j]**r * x[j] = s[r]  for r = 0 .. e-1, where the
    nodes are DISTINCT elements of GF(p) and e = len(nodes) = len(s).

    This is the transposed-Vandermonde ("moment") system, and every local
    solve this code performs is one: the local parity-check matrix is the
    GRS matrix H_local[r, c] = eval_pts[c]**r, so restricting it to the
    erased columns and to its first e rows leaves exactly this shape. A
    square Vandermonde in distinct nodes is always invertible, so the
    solution exists and is unique -- no rank check is needed here.

    Cost is O(e^2) rather than the O(e^3) of Gaussian elimination, which is
    what makes omega = rho = 1024 tractable at all: at e = 1024 the general
    solver needs ~1e9 field operations (about 25 minutes in this field's
    pure-Python arithmetic), this needs ~4e6 (well under a second).

    Method: let N(z) = prod_j (z - nodes[j]) and Q_j(z) = N(z)/(z - nodes[j]).
    Since Q_j vanishes at every node except its own,
        sum_i q_{j,i} s_i = sum_l x_l * Q_j(nodes[l]) = x_j * Q_j(nodes[j]),
    so each x_j is one dot product against Q_j's coefficients, divided by
    Q_j evaluated at its own node. Building N is O(e^2); each of the e
    unknowns then costs O(e) for a synthetic division, a Horner evaluation
    and a dot product.

    Args:
        nodes: sequence of e distinct ints in [0, p)
        s:     sequence of e ints in [0, p)  (the syndrome)
        p:     the field's prime modulus
    Returns:
        list of e ints -- the unique solution x.
    """
    e = len(nodes)
    if e == 0:
        return []
    nodes = [int(a) % p for a in nodes]
    s = [int(v) % p for v in s]

    # N(z) = prod (z - a), ascending coefficients, built one factor at a time.
    N = [0] * (e + 1)
    N[0] = 1
    deg = 0
    for a in nodes:
        for i in range(deg + 1, 0, -1):
            N[i] = (N[i - 1] - a * N[i]) % p
        N[0] = (-a * N[0]) % p
        deg += 1

    x = [0] * e
    for j, a in enumerate(nodes):
        # Q = N / (z - a) by synthetic division, produced in DESCENDING order.
        qd = []
        acc = 0
        for i in range(e, 0, -1):
            acc = (N[i] + acc * a) % p
            qd.append(acc)
        # Q(a) = N'(a), by Horner over the same descending coefficients.
        den = 0
        for c in qd:
            den = (den * a + c) % p
        if den == 0:
            raise GFSolveError(
                "vandermonde_solve: repeated node -- the erased positions "
                "did not map to distinct GRS evaluation points")
        # x_j = <ascending coefficients of Q, s> / Q(a)
        tot = 0
        for i in range(e):
            tot += qd[e - 1 - i] * s[i]
        x[j] = (tot % p) * pow(den, p - 2, p) % p
    return x


def build_local_grs(GF, rho, n0):
    """The local GRS parity-check matrix H_local[r, c] = (c+1)**r, r < rho.

    Built by repeatedly multiplying the previous row by the evaluation
    points rather than calling ** on every entry: at rho = 1024, n0 = 5120
    the exponent form costs 5.2 million modular exponentiations, the
    recurrence costs the same number of plain multiplications.

    This matrix is IDENTICAL for every local block -- the block-circulant
    structure permutes which global columns it lands on, not its contents --
    so callers build it once and reuse it.
    """
    eval_pts = GF(np.arange(1, n0 + 1))
    H_local = GF.Zeros((rho, n0))
    if rho > 0:
        H_local[0, :] = GF(np.ones(n0, dtype=np.int64))
    for r_idx in range(1, rho):
        H_local[r_idx, :] = H_local[r_idx - 1, :] * eval_pts
    return H_local


# ==============================================================================
# STEP 1: BLOCK CIRCULANT PARAMETERS
# ==============================================================================
# The BC code is defined by four integer parameters:
#   omega  : number of information (systematic) symbols per local block
#   rho    : number of parity symbols per local block
#   lambda : overlap factor – number of consecutive information blocks
#            that contribute to a local parity block
#   mu     : number of local blocks = total_info / omega
#
# In this implementation, the blob contains 4096 field elements, and
# we choose omega = 2, rho = 2, lambda = 2. Then:
#   mu = 4096 // 2 = 2048 blocks
#   block_size = rho + omega = 4 symbols per block
#   global codeword length n = mu * block_size = 8192
#   global message length k = mu * omega = 4096
#   minimum distance d = lambda * rho + 1 = 5
#   code Rate = omega/(rho+omega) = 2/4 = 0.5
#   local code length (number of symbols involved in one local equation)
#       n0 = rho + lambda * omega = 2 + 4 = 6
omega = 2                             # Information symbols per local block (w)
rho = 2                               # Parity symbols per local block (p) extra symbol added per local block
lambda_ = 2                           # Overlap factor (lambda)
mu = FIELD_ELEMENTS_PER_BLOB // omega # 2048 (u)

block_size = rho + omega               # 4
n = mu * block_size                    # 8192
k = mu * omega                         # 4096
d = lambda_ * rho + 1                  # 5
n0 = rho + lambda_ * omega             # 6 (Local code length)

# NOTE ON THESE DEFAULTS. They are kept because the demonstration at the
# bottom of this file runs on them and is fast. They are NOT the parameters
# benchmarked in docs/benchmark_1D_2D_BC_report.md. With lambda = 2 the
# minimum distance is d = lambda*rho + 1 = 5, so this code is *guaranteed*
# to correct only four erasures across the whole 8192-symbol codeword.
#
# benchmark_1D_2D_BC.py instead sweeps three rows with rho = omega and
# lambda = mu, passing them explicitly to the functions below:
#
#   omega  rho   mu  lambda    n0    local solve    d = lambda*rho + 1
#    1024 1024    4       4  5120    1024x1024      4097
#     512  512    8       8  4608     512x512       4097
#     256  256   16      16  4352     256x256       4097
#
# d = 4097 = n - k + 1 is the Singleton bound, so at full overlap these are
# MDS codes -- as good as Reed-Solomon. Every function in this file takes
# (mu, lambda_, omega, rho) as arguments, so nothing here needs the globals
# above to change in order to run them.



# ==============================================================================
# STEP 2: LOCAL INDEX MAPPING (help in constructino for Section 3-B of the paper)
# ==============================================================================
def get_local_indices(i, mu, lambda_, omega, rho):
    """
    Returns the global codeword indices that participate in the i‑th local
    parity‑check equation.
    
    Layout of the local equation (Section 3‑B):
        [ p_i (rho parity symbols) , 
          m_{i} (omega symbols) , m_{i+1} (omega) , ...,
          m_{i+lambda-1} (omega) ]
    where block indices are taken modulo mu (circulant wrap‑around).
    
    The global codeword is organised as:
        first  k = mu*omega positions  -> systematic message symbols
        last   n-k = mu*rho positions  -> parity symbols
    """
    k_total = mu * omega
    # Parity symbols for local block i are stored contiguously after the message
    local_parity = [k_total + i * rho + r for r in range(rho)]

    # Overlapping systematic message blocks: from i up to i+lambda-1 (mod mu)
    local_info = []
    for l in range(lambda_):
        target_block = (i + l) % mu
        info_start = target_block * omega
        for w in range(omega):
            local_info.append(info_start + w)

    # Return parity indices first, then information indices (concatenation of both arrays)
    return local_parity + local_info

# ==============================================================================
# STEP 3: PARITY-CHECK MATRIX CONSTRUCTION (Section 3-A and 3-B)
# ==============================================================================
def build_block_circulant_h(GF, mu, lambda_, omega, rho):
    """
    Constructs the global parity‑check matrix H_BC of size (mu*rho) × n.
    Each local block of rho rows corresponds to one local constraint.
    
    The local generator matrix is a (rho × n0) generalised Reed‑Solomon
    (GRS) matrix: H_local[r, :] = [1, α, α^2, ..., α^{n0-1}]^r
    with evaluation points α = 1,2,...,n0.
    
    Because of the block‑circulant structure, the same H_local is used
    for every local block, but the columns are permuted according to
    the index mapping of each local equation.

    an zero matrix in the correct shape of the code 
    (length, dimension, and local overlaps) base on the parameters mu, lambda_, omega, and rho.
    this would be used to verify and decode the codewords.
    """
    n = mu * (rho + omega)
    n0 = rho + lambda_ * omega
    H_BC = GF.Zeros((mu * rho, n))
    # Evaluation points: 1,2,...,n0 (non‑zero, distinct in prime field)
    eval_pts = GF(np.arange(1, n0 + 1))

    print("Building H_BC for verification...")
    # H_local is IDENTICAL for every block -- only the columns it lands on
    # move -- so it is built once here rather than mu times inside the loop.
    H_local = build_local_grs(GF, rho, n0)
    for i in range(mu):
        # Global indices that take part in local equation i
        indices = np.asarray(get_local_indices(i, mu, lambda_, omega, rho))
        assert len(set(indices.tolist())) == indices.size, \
            "a local support repeated a global column; lambda must be <= mu"
        # Place H_local's columns at those global positions, one whole row at
        # a time. The previous form assigned element by element, which at
        # rho=1024, n0=5120 is 21 million Python-level scalar writes per run.
        for row_idx in range(rho):
            H_BC[i * rho + row_idx, indices] = H_local[row_idx, :]
    return H_BC



# ==============================================================================
# STEP 4: STRUCTURED SYSTEMATIC ENCODER (Section 3-C)
# ==============================================================================
def encode_bc_structured(GF, m, mu, lambda_, omega, rho):
    """
    Encodes a message vector m (length k = mu*omega) into a systematic
    codeword c = [ m | p ] where p are the parity symbols.
    
    The encoding is performed block‑wise:
        For each local block i, gather the overlapping information symbols
        u_i of length lambda*omega, then solve for the rho parity symbols
        p_i such that H_local * [p_i, u_i]^T = 0.
    
    Because H_local = [H_p | H_i] with H_p square (rho x rho), the parity
    is obtained as p_i = - (H_p)^{-1} * H_i * u_i.
    """
    k_total = mu * omega
    n_tot = mu * (rho + omega)
    n0 = rho + lambda_ * omega
    eval_pts = GF(np.arange(1, n0 + 1))

    # Build the local GRS matrix once
    H_local = build_local_grs(GF, rho, n0)

    # Split into parity part (rho columns) and information part (lambda*omega)
    H_p = H_local[:, :rho]          # rho x rho
    H_i = H_local[:, rho:]          # rho x (lambda * omega)
    # H_p is the square Vandermonde on evaluation points 1..rho, so the
    # per-block parity solve below goes through vandermonde_solve in O(rho^2)
    # instead of a fresh O(rho^3) Gaussian elimination for every one of the
    # mu blocks. At rho=1024 that is the difference between ~1 second and
    # ~25 minutes PER BLOCK.
    parity_nodes = list(range(1, rho + 1))

    # Reshape message into mu blocks of size omega
    m_blocks = m.reshape((mu, omega))
    c = GF.Zeros(n_tot)
    c[:k_total] = m  # Systematic part is directly copied

    print("Encoding via local GRS solvers...")
    start = time.time()

    for i in range(mu):
        # Build u_i from the lambda overlapping message blocks
        u_i = GF.Zeros(lambda_ * omega)
        for l in range(lambda_):
            target_block = (i + l) % mu
            u_i[l*omega : (l+1)*omega] = m_blocks[target_block, :]

        # Compute syndrome for the information part
        syndrome_info = H_i @ u_i
        # Solve H_p * p_i = - syndrome_info  =>  p_i = - H_p^{-1} * H_i * u_i
        p_i = GF(vandermonde_solve(parity_nodes,
                                   [int(v) for v in (-syndrome_info)], int(GF.characteristic)))

        # Place parity into the codeword
        p_start = k_total + i * rho
        c[p_start : p_start + rho] = p_i

    print(f"Encoding finished in {time.time()-start:.2f}s")
    return c



# ==============================================================================
# STEP : DECCBC[2] DECODER (Section 3D of the paper)
# ==============================================================================
def _partial_syndrome(nodes, vals, rows, p):
    """S[r] = sum_j nodes[j]**r * vals[j]  (mod p), for r = 0 .. rows-1.

    This is what "apply the local parity checks to the symbols that survived"
    reduces to, because the local parity-check matrix is a GRS/Vandermonde
    matrix. Computing it this way costs rows*len(nodes) multiplications and,
    crucially, lets the caller ask for only the FIRST few rows: a block with
    e erasures needs e syndrome entries plus a couple to check against, not
    all rho of them.
    """
    m = len(nodes)
    if m == 0:
        return [0] * rows
    nd = np.array([int(v) % p for v in nodes], dtype=object)
    vl = np.array([int(v) % p for v in vals], dtype=object)
    pw = np.ones(m, dtype=object)
    out = []
    for r_idx in range(rows):
        if r_idx:
            pw = pw * nd % p
        out.append(int((pw * vl).sum() % p))
    return out


def _vander_rows(nodes, rows, p):
    """Raw object-array Vandermonde: M[r, j] = nodes[j]**r, r < rows."""
    m = len(nodes)
    nd = np.array([int(v) % p for v in nodes], dtype=object)
    M = np.zeros((rows, m), dtype=object)
    cur = np.ones(m, dtype=object)
    for r_idx in range(rows):
        if r_idx:
            cur = cur * nd % p
        M[r_idx, :] = cur
    return M


def dec_cbc_2_aux_ntt(r_in, mask_in, mu, lambda_, omega, rho,
                      pair_unknown_cap=None, verbose=True):
    """
    Pairwise BC decoder using the paper's auxiliary GRS construction,
    with NTT-based erasure decoding on the auxiliary code.

    For each adjacent pair (i, i+1):
      1. Build the auxiliary GRS code over U = S_i ∪ S_{i+1}, with length
         n_aux = |U| and dimension k_aux = n_aux - 2*rho.
      2. If n_aux | (p-1), apply NTT erasure decoding.
      3. Verify the decoded result against the actual BC stacked equations.
      4. If NTT fails or verification fails, fall back to Gaussian elimination
         on the stacked system.
    """
    p = int(GF_BLS12_381.characteristic)
    r = r_in.copy()
    mask = mask_in.copy()
    cap = 2 * rho if pair_unknown_cap is None else int(pair_unknown_cap)

    supports = [np.asarray(get_local_indices(i, mu, lambda_, omega, rho))
                for i in range(mu)]
    locmaps = [{int(g): c for c, g in enumerate(sup)} for sup in supports]

    progress = True
    iterations = 0
    stats = {"phase1_ntt": 0, "phase2_aux_ntt": 0, "phase2_gauss": 0,
             "skipped_cap": 0, "aux_verify_fail": 0}

    while np.any(mask) and progress:
        progress = False
        iterations += 1

        # -------- Phase 1: single-block NTT decode --------
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
            S = _partial_syndrome(known_pos + 1,
                                  [int(v) for v in r[sup[known_pos]]],
                                  rows_needed, p)
            syndrome = [(-v) % p for v in S]

            nodes_e = [int(c) + 1 for c in erased_pos]
            try:
                x = vandermonde_solve(nodes_e, syndrome[:e], p)
            except GFSolveError:
                continue
            # consistency check
            consistent = True
            for rr in range(e, rows_needed):
                acc = 0
                for nd_, xv in zip(nodes_e, x):
                    acc += pow(nd_, rr, p) * xv
                if acc % p != syndrome[rr]:
                    consistent = False
                    break
            if not consistent:
                continue

            r[sup[erased_pos]] = GF_BLS12_381(np.array(x, dtype=object))
            mask[sup[erased_pos]] = False
            progress = True
            stats["phase1_ntt"] += 1

        # -------- Phase 2: pairwise with auxiliary GRS + NTT fallback --------
        if not progress and np.any(mask):
            for i in range(mu):
                next_i = (i + 1) % mu
                if next_i == i:
                    continue
                sup_i, sup_j = supports[i], supports[next_i]
                combined = np.array(
                    sorted(set(sup_i.tolist()) | set(sup_j.tolist()))
                )
                n_aux = len(combined)
                pair_mask = mask[combined]
                num_pair = int(np.count_nonzero(pair_mask))

                if not (0 < num_pair <= 2 * rho):
                    continue
                if num_pair > cap:
                    stats["skipped_cap"] += 1
                    continue

                # ------ 2a: try auxiliary GRS + NTT ------
                aux_success = False
                if (p - 1) % n_aux == 0:
                    k_aux = n_aux - 2 * rho
                    if k_aux > 0:
                        eval_pts, H_aux = _build_auxiliary_grs(n_aux, k_aux, p)
                        if H_aux is not None:
                            received_aux = [int(r[g]) if not mask[g] else 0
                                            for g in combined]
                            mask_aux = np.array([bool(mask[g])
                                                  for g in combined])
                            rec_aux, ok = _ntt_erasure_decode_aux(
                                received_aux, mask_aux, n_aux, k_aux,
                                eval_pts, p
                            )
                            if ok:
                                # Verify against the actual BC stacked system
                                if _verify_aux_solution(
                                    rec_aux, combined, sup_i, sup_j, i, next_i,
                                    rho, lambda_, omega, mu, p
                                ):
                                    # Apply
                                    for c, g in enumerate(combined):
                                        if mask[g]:
                                            r[g] = GF_BLS12_381(rec_aux[c])
                                            mask[g] = False
                                    progress = True
                                    stats["phase2_aux_ntt"] += 1
                                    aux_success = True
                                else:
                                    stats["aux_verify_fail"] += 1

                if aux_success:
                    continue

                # ------ 2b: fall back to Gaussian elimination ------
                e = num_pair
                erased_g = combined[np.nonzero(pair_mask)[0]]

                syndrome = []
                for blk in (i, next_i):
                    sup = supports[blk]
                    kn = np.nonzero(~mask[sup])[0]
                    S = _partial_syndrome(kn + 1,
                                          [int(v) for v in r[sup[kn]]],
                                          rho, p)
                    syndrome.extend([(-v) % p for v in S])

                top = np.zeros((rho, e), dtype=object)
                bot = np.zeros((rho, e), dtype=object)
                for half, blk in ((top, i), (bot, next_i)):
                    lm = locmaps[blk]
                    hit = [(t, lm[int(g)] + 1)
                           for t, g in enumerate(erased_g) if int(g) in lm]
                    if hit:
                        cols, nds = zip(*hit)
                        half[:, list(cols)] = _vander_rows(nds, rho, p)
                H_e = GF_BLS12_381(np.vstack([top, bot]))
                syn_v = GF_BLS12_381(np.array(syndrome, dtype=object))

                sol = None
                tried = []
                for nrows in (min(2 * rho, e + 8), 2 * rho):
                    if nrows in tried:
                        continue
                    tried.append(nrows)
                    try:
                        cand = gf_solve(H_e[:nrows, :], syn_v[:nrows])
                    except GFSolveError:
                        continue
                    if nrows < 2 * rho:
                        chk = H_e[nrows:nrows + 2, :] @ cand
                        if not np.array_equal(
                            np.asarray(chk),
                            np.asarray(syn_v[nrows:nrows + 2])
                        ):
                            continue
                    sol = cand
                    break
                if sol is None:
                    continue

                r[erased_g] = sol
                mask[erased_g] = False
                progress = True
                stats["phase2_gauss"] += 1

    if verbose:
        print(f"dec_cbc_2_aux_ntt: {iterations} iterations, stats={stats}")
    return r, mask


def _verify_aux_solution(rec_aux, combined, sup_i, sup_j,
                          i, j, rho, lambda_, omega, mu, p):
    """
    Check that rec_aux satisfies the ACTUAL BC stacked parity checks for
    blocks i and j over the union support `combined`. This is required
    because the auxiliary GRS code is only algebraically identical to the
    stacked BC system when the BC encoder used root-of-unity eval points.
    """
    n0 = rho + lambda_ * omega
    lm_i = {int(g): c for c, g in enumerate(sup_i)}
    lm_j = {int(g): c for c, g in enumerate(sup_j)}

    H_stack = GF_BLS12_381.Zeros((2 * rho, len(combined)))
    for r_idx in range(rho):
        for c_idx, g in enumerate(combined):
            gi = int(g)
            if gi in lm_i:
                H_stack[r_idx, c_idx] = pow(lm_i[gi] + 1, r_idx, p)
            if gi in lm_j:
                H_stack[rho + r_idx, c_idx] = pow(lm_j[gi] + 1, r_idx, p)

    x = GF_BLS12_381([int(v) for v in rec_aux])
    return bool(np.all(np.asarray(H_stack @ x) == 0))

def dec_cbc_t(r_in, mask_in, mu, lambda_, omega, rho,
              t_max=3, unknown_cap=None, verbose=True):
    """
    Generalised BC decoder: combine up to t_max adjacent blocks per solve.

    For each t in 1..t_max:
      - Enumerate windows of t consecutive blocks (mod mu).
      - For each window, build the stacked t*rho parity equations over the
        union of the t blocks' supports.
      - If the window has <= t*rho unknowns (and <= unknown_cap), solve
        via Gaussian elimination with rank check.
      - On success, apply the recovered values and restart from t=1.

    t=1 uses the existing fast Vandermonde/NTT single-block path.
    t>=2 uses generic Gaussian elimination; cost grows as O((t*rho)^3).

    Args:
      t_max:       max block-combining width (1, 2, 3, ...).
      unknown_cap: max unknowns per t-block solve. Windows exceeding the
                   cap are skipped and counted. Default = t*rho.

    Returns: (recovered, remaining_mask, iterations, stats)
    """
    p = int(GF_BLS12_381.characteristic)
    r = r_in.copy()
    mask = mask_in.copy()
    if unknown_cap is None:
        unknown_cap = t_max * rho
    cap = int(unknown_cap)

    supports = [np.asarray(get_local_indices(i, mu, lambda_, omega, rho))
                for i in range(mu)]
    locmaps = [{int(g): c for c, g in enumerate(sup)} for sup in supports]

    progress = True
    iterations = 0
    stats = {"phase1": 0, **{f"phase{t}": 0 for t in range(2, t_max + 1)},
             "skipped_cap": 0, "failed_rank": 0}

    while np.any(mask) and progress:
        progress = False
        iterations += 1

        # -------- Phase 1: single block (fast path) --------
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
            S = _partial_syndrome(known_pos + 1,
                                  [int(v) for v in r[sup[known_pos]]],
                                  rows_needed, p)
            syndrome = [(-v) % p for v in S]
            nodes_e = [int(c) + 1 for c in erased_pos]
            try:
                x = vandermonde_solve(nodes_e, syndrome[:e], p)
            except GFSolveError:
                continue
            consistent = True
            for rr in range(e, rows_needed):
                acc = sum(pow(nd_, rr, p) * xv
                          for nd_, xv in zip(nodes_e, x)) % p
                if acc != syndrome[rr]:
                    consistent = False
                    break
            if not consistent:
                continue
            r[sup[erased_pos]] = GF_BLS12_381(np.array(x, dtype=object))
            mask[sup[erased_pos]] = False
            progress = True
            stats["phase1"] += 1

        if progress:
            continue

        # -------- Phases t = 2..t_max: general Gaussian --------
        for t in range(2, t_max + 1):
            phase_progress = False
            for i in range(mu):
                # Union of t consecutive blocks' supports
                combined = set()
                block_ids = []
                for j in range(t):
                    blk = (i + j) % mu
                    block_ids.append(blk)
                    combined.update(supports[blk].tolist())
                combined = np.array(sorted(combined))
                pair_mask = mask[combined]
                num_unknowns = int(np.count_nonzero(pair_mask))

                if num_unknowns == 0:
                    continue
                if num_unknowns > t * rho:
                    continue
                if num_unknowns > cap:
                    stats["skipped_cap"] += 1
                    continue

                e = num_unknowns
                erased_g = combined[np.nonzero(pair_mask)[0]]

                # Syndrome: stack t row-groups, one per block
                syndrome = []
                for blk in block_ids:
                    sup = supports[blk]
                    kn = np.nonzero(~mask[sup])[0]
                    S = _partial_syndrome(kn + 1,
                                          [int(v) for v in r[sup[kn]]],
                                          rho, p)
                    syndrome.extend([(-v) % p for v in S])

                # Build stacked H_e: (t*rho) x e
                H_e = GF_BLS12_381.Zeros((t * rho, e))
                for g_idx, blk in enumerate(block_ids):
                    lm = locmaps[blk]
                    hit = [(c, lm[int(gg)] + 1)
                           for c, gg in enumerate(erased_g) if int(gg) in lm]
                    if hit:
                        cols, nds = zip(*hit)
                        H_e[g_idx * rho:(g_idx + 1) * rho, list(cols)] = \
                            _vander_rows(nds, rho, p)

                syn_v = GF_BLS12_381(np.array(syndrome, dtype=object))

                # Solve with rank check
                sol = None
                tried = []
                for nrows in (min(t * rho, e + 8), t * rho):
                    if nrows in tried:
                        continue
                    tried.append(nrows)
                    try:
                        cand = gf_solve(H_e[:nrows, :], syn_v[:nrows])
                    except GFSolveError:
                        stats["failed_rank"] += 1
                        continue
                    if nrows < t * rho:
                        chk = H_e[nrows:nrows + 2, :] @ cand
                        if not np.array_equal(
                            np.asarray(chk),
                            np.asarray(syn_v[nrows:nrows + 2])
                        ):
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
                break   # restart from Phase 1

    if verbose:
        print(f"dec_cbc_t(t_max={t_max}): {iterations} iterations, stats={stats}")
    return r, mask, iterations, stats


if __name__ == "__main__":
    print(f"--- BC Code with Full Blob (4096 elements) ---")
    print(f"Parameters: mu={mu}, lambda={lambda_}, omega={omega}, rho={rho}")
    print(f"Global Code [n, k, d]: [{n}, {k}, {d}]")
    print(f"Local Code Length n0: {n0}\n")
    # ==============================================================================
    #  GENERATE BLOB & ENCODE
    # ==============================================================================
    print("Generating full Ethereum-standard blob (4096 elements)...")
    full_blob = random_blob()   # list of 4096 integers
    message = GF_BLS12_381(full_blob) # convert to field vector

    H_BC = build_block_circulant_h(GF_BLS12_381, mu, lambda_, omega, rho)
    print(f"H_BC shape: {H_BC.shape}\n")

    encoded_message = encode_bc_structured(GF_BLS12_381, message, mu, lambda_, omega, rho)

    print(f"Message message length: {len(message)}")
    print(f"Codeword c length: {len(encoded_message)}")
    print(f"Sample codeword parity[0:10]: {encoded_message[k:k+10]}\n")

    # ==============================================================================
    #  INJECT ERASURES
    # ==============================================================================
    # To test the decoder, we randomly erase 'num_erasures' symbols.
    num_erasures = 2 * rho  # 4 erasures
    erased_indices = sorted(np.random.choice(n, num_erasures, replace=False).tolist())

    received_vector = encoded_message.copy()
    erased_mask = np.zeros(n, dtype=bool)
    for idx in erased_indices:
        erased_mask[idx] = True
        received_vector[idx] = GF_BLS12_381(0)  # mark as erased

    print(f"Injected {num_erasures} erasures at indices: {erased_indices}")
    print("\nStarting DecCBC[2] Decoder (Section 4)...")
    start = time.time()
    recovered_c, remaining_mask = dec_cbc_2_aux_ntt(
    received_vector, erased_mask, mu, lambda_, omega, rho)
    print(f"Decoding finished in {time.time()-start:.2f}s")

    # ==============================================================================
    #  VERIFICATION
    # ==============================================================================
    syndrome_check = H_BC @ recovered_c
    is_valid_codeword = np.all(syndrome_check == 0)
    is_exact_match = np.array_equal(recovered_c, encoded_message)

    print("\n--- Decoding Verification Results ---")
    print("Remaining Erasures Unresolved:", np.sum(remaining_mask))
    print("Parity Check Satisfied (H_BC * c^T == 0):", is_valid_codeword)
    print("Decoded Vector Matches Transmitted Codeword:", is_exact_match)

    # Systematic recovery check
    recovered_message = recovered_c[:k]
    print("Original message first 2 element:", message[:2])
    print("Recovered message first 2 element:", recovered_message[:2])
    print("Full systematic recovery successful!" if np.array_equal(message, recovered_message) else "Mismatch in recovered message!")