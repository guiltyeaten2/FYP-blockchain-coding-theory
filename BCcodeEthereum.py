import time
import numpy as np

# ==============================================================================
# IMPORT ETHEREUM BLOB GENERATOR (EIP-4844 / consensus-specs)
# ==============================================================================
# The blob_generator module provides:
#   - FIELD_ELEMENTS_PER_BLOB = 4096  (number of field elements in a blob)
#   - GF: a Galois field class (here BLS12‑381 prime field)
#   - random_blob(): returns a Python list of 4096 integers in GF(p)
from blob_generator import FIELD_ELEMENTS_PER_BLOB, GF, random_blob

# Alias for readability; GF_BLS12_381 is the field we work over.
GF_BLS12_381 = GF

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


def dec_cbc_2(H_BC, r_in, mask_in, mu, lambda_, omega, rho,
              pair_unknown_cap=None, verbose=True):
    """
    Decoder for Block Circulant codes with parameter t=2 (i.e., can correct
    up to 2*rho erasures across a pair of adjacent local blocks).

    It iteratively performs:
        1) Single-local-block decoding: if a local block has <= rho erasures,
           recover them using its local parity equations.
        2) Pairwise joint decoding: if two neighbouring local blocks together
           have <= 2*rho erasures, recover them simultaneously.

    H_BC is accepted for API compatibility but is no longer read. The local
    parity-check matrix is the same GRS matrix for every block, so the rows
    this decoder needs are regenerated on demand from (rho, n0). Materialising
    the global (mu*rho) x n matrix costs 33.5 million field elements of memory
    and buys nothing.

    pair_unknown_cap: skip any pairwise system with more than this many
        unknowns. Phase 2 is a general (non-Vandermonde) solve, so its cost
        grows as the cube of the unknown count; at rho=1024 an uncapped pair
        can reach 2048 unknowns, which is roughly 8.6e9 field operations --
        over an hour for a single pair. The cap is a stated compute budget,
        not a property of the code: pairs skipped because of it are counted
        and reported, and the positions involved stay honestly flagged as
        erased rather than being guessed at.
    """
    p = int(GF_BLS12_381.characteristic)
    r = r_in.copy()
    mask = mask_in.copy()
    cap = 2 * rho if pair_unknown_cap is None else int(pair_unknown_cap)

    # Each block's global support, and the inverse map, computed once rather
    # than rebuilt on every iteration of the while loop below.
    supports = [np.asarray(get_local_indices(i, mu, lambda_, omega, rho))
                for i in range(mu)]
    locmaps = [{int(g): c for c, g in enumerate(sup)} for sup in supports]

    progress = True
    iterations = 0
    pairs_skipped_cost = 0

    while np.any(mask) and progress:
        progress = False
        iterations += 1

        # ---------- Phase 1: Single Local Decoding ----------
        for i in range(mu):
            sup = supports[i]
            local_mask = mask[sup]
            num_local_erasures = int(np.count_nonzero(local_mask))

            if 0 < num_local_erasures <= rho:
                erased_pos = np.nonzero(local_mask)[0]
                known_pos = np.nonzero(~local_mask)[0]
                e = num_local_erasures

                # Only the first e syndrome entries are needed to determine e
                # unknowns; two more are pulled to check the answer against
                # equations the solve did not consume.
                rows_needed = min(e + 2, rho)
                S = _partial_syndrome(known_pos + 1,
                                      [int(v) for v in r[sup[known_pos]]],
                                      rows_needed, p)
                syndrome = [(-v) % p for v in S]

                # Restricted to its first e rows and to the erased columns,
                # the local GRS matrix is a square Vandermonde in DISTINCT
                # evaluation points, hence always invertible. So this solve
                # cannot be underdetermined and cannot fabricate a value --
                # the failure mode the guard in gf_solve exists to catch
                # simply does not arise on this path.
                nodes_e = [int(c) + 1 for c in erased_pos]
                try:
                    x = vandermonde_solve(nodes_e, syndrome[:e], p)
                except GFSolveError:
                    continue

                consistent = True
                for rr in range(e, rows_needed):
                    acc = 0
                    for nd_, xv in zip(nodes_e, x):
                        acc += pow(nd_, rr, p) * xv
                    if acc % p != syndrome[rr]:
                        consistent = False
                        break
                if not consistent:
                    continue   # leave this block's erasures flagged

                r[sup[erased_pos]] = GF_BLS12_381(np.array(x, dtype=object))
                mask[sup[erased_pos]] = False
                progress = True

        # ---------- Phase 2: Pairwise Joint Decoding ----------
        # Only if no progress from single-block decoding and erasures remain
        if not progress and np.any(mask):
            for i in range(mu):
                next_i = (i + 1) % mu
                if next_i == i:
                    continue
                sup_i, sup_j = supports[i], supports[next_i]
                combined_indices = np.array(
                    sorted(set(sup_i.tolist()) | set(sup_j.tolist())))

                pair_mask = mask[combined_indices]
                num_pair_erasures = int(np.count_nonzero(pair_mask))

                # NOTE: `<= 2*rho` is necessary but NOT sufficient. These rows
                # are block i's own rho parity checks stacked on block i+1's --
                # not the auxiliary [2(w+p), 2w, 2p+1] GRS code over the union
                # of the two supports that the source paper's Algorithm 1
                # builds. The stacked form is not MDS, so a split that leaves
                # one block's equations facing more unknowns than it has rows
                # is not solvable here. gf_solve raises on exactly that case
                # and the pair is skipped, rather than zero-filling.
                if not (0 < num_pair_erasures <= 2 * rho):
                    continue
                if num_pair_erasures > cap:
                    pairs_skipped_cost += 1
                    continue

                e = num_pair_erasures
                erased_g = combined_indices[np.nonzero(pair_mask)[0]]

                # Syndrome, one row-group at a time. Each group is its own
                # block's Vandermonde, so the same power-sum routine applies.
                syndrome = []
                for blk in (i, next_i):
                    sup = supports[blk]
                    kn = np.nonzero(~mask[sup])[0]
                    S = _partial_syndrome(kn + 1,
                                          [int(v) for v in r[sup[kn]]], rho, p)
                    syndrome.extend([(-v) % p for v in S])

                # Columns of the stacked system, generated directly rather
                # than sliced out of a materialised global matrix.
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

                # e unknowns need only e independent equations. Trying a
                # truncated system first turns an O(e^2 * 2rho) elimination
                # into O(e^3); if those rows happen to be rank-deficient,
                # gf_solve says so and the full stack is used instead.
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
                        if not np.array_equal(np.asarray(chk),
                                              np.asarray(syn_v[nrows:nrows + 2])):
                            continue
                    sol = cand
                    break
                if sol is None:
                    continue   # this pair is not jointly determined; leave it

                r[erased_g] = sol
                mask[erased_g] = False
                progress = True
                # Continue scanning the remaining pairs in this same pass.
                # The previous version broke out to restart Phase 1 after
                # every single pair fixed, paying a full O(mu) rescan per
                # recovered pair. Each pair re-reads the live mask, so fixing
                # several per pass is equivalent and far cheaper.

    if verbose:
        extra = (f", {pairs_skipped_cost} pair(s) skipped over the "
                 f"{cap}-unknown compute cap" if pairs_skipped_cost else "")
        print(f"Decoder finished in {iterations} iterations{extra}.")
    return r, mask



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
    recovered_c, remaining_mask = dec_cbc_2(
        H_BC, received_vector, erased_mask, mu, lambda_, omega, rho
    )
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