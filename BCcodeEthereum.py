# ==============================================================================
# IMPORT ETHEREUM BLOB GENERATOR (EIP-4844 / consensus-specs)
# ==============================================================================
# The blob_generator module provides:
#   - FIELD_ELEMENTS_PER_BLOB = 4096  (number of field elements in a blob)
#   - GF: a Galois field class (here BLS12‑381 prime field)
#   - random_blob(): returns a Python list of 4096 integers in GF(p)
"""
Block-Circulant erasure code for Ethereum blob scale.

Implemented according to:
    B. Sasidharan, E. Viterbo, S. H. Dau, "Block Circulant Codes With
    Application to Decentralized Systems," IEEE Trans. Commun., vol. 73,
    no. 10, pp. 8542-8557, Oct. 2025.

    B. Sasidharan, E. Viterbo, D. Feist, "Block Circulant Codes for
    Ethereum PeerDAS," IACR ePrint 2026/708, Apr. 2026.

    https://ethresear.ch/t/alternatives-to-2d-reed-solomon-codes-in-das/24639

The code is a STACKED RS code: each local code is [(n0, k0), D] -- D parallel
RS codewords sharing the same cells. Cells are indexed by cosets of a
subgroup H3 of size D. Evaluation points for cell c are the D elements of
that cell's coset.

Structure of the subgroups (paper Sec. 3.1):
    |H_3| = D                      (cell size)
    |H_2| = omega * D              (per-cell info span)
    |H_1| = lambda * omega * D     (per-local-code info span)
    |H_0| = mu * omega * D = k     (global info span)

All nested: H_3 < H_2 < H_1 < H_0 < F_q^*.
"""

import time
import numpy as np
import galois

from blob_generator import FIELD_ELEMENTS_PER_BLOB, GF, random_blob

GF_BLS12_381 = GF
P_FIELD = int(GF_BLS12_381.characteristic)

# ==============================================================================
# PARAMETERS (paper-aligned; override per call)
# ==============================================================================
# given μ · ω · D = k = 4096 symbols
# μ · ω = 64 cells
# for rate = 0.5, ρ = ω
#BC variant set=
#   μ = 2, λ = 2, ω = 2048, ρ = 2048

omega = 2048
rho = omega
lambda_ = 2
D = 64                                # cell size Fixed at peerDAS spec
mu = FIELD_ELEMENTS_PER_BLOB // (omega)  # = 4096 / (2048) = 2

n = mu * (rho + omega)                    # 4 * 2048 = 8192
k = mu * omega                            # 4 * 1024 = 4096
d = lambda_ * rho + 1                     # 2 * 1024 + 1 = 2049
n0 = rho + lambda_ * omega                # 1024 + 2 * 1024 = 3072

# NOTE: the paper works in CELLS, not symbols. With D=64 and one blob's worth
# of symbols k=4096, the number of message cells is k/D = 64. At omega cells
# per block, mu = k/(omega*D) must be an integer. The natural choice matching
# the paper's worked example is:
#
#   k_cells = 64, D = 64    -> k = 4096 symbols
#   omega = 16, mu = 4      -> 4 local codes, each carrying 16 info cells
#   rho = 16, lambda = 2    -> n0_cells = 2*16+16 = 48, n_cells = 128
#
# This is the paper's worked example at symbol scale. The demonstration at the
# bottom of this file runs on the *symbol-level* parameters, which is what the
# benchmark uses; the cell-level structure is available but only used by the
# functions that explicitly take a `D` argument.

# k_cells_demo = 64
# omega_cells_demo = 16
# mu_cells_demo = 4
# rho_cells_demo = 16
# lambda_cells_demo = 2
# n_cells_demo = mu_cells_demo * (omega_cells_demo + rho_cells_demo)   # 128

# ==============================================================================
# GALOIS FIELD LINEAR ALGEBRA
# ==============================================================================
class GFSolveError(ValueError):
    """Raised when A * x = b has no unique solution over GF(p)."""


def gf_solve(A, b, require_unique=True):
    """Solve A x = b over GF(p) by Gauss-Jordan elimination with rank check."""
    A = A.copy(); b = b.copy()
    m, n = A.shape
    row = 0
    col_map = []
    for col in range(n):
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
        if len(col_map) < n:
            raise GFSolveError(f"underdetermined: rank {len(col_map)} < {n}")
    x = GF_BLS12_381.Zeros(n)
    for r, c in col_map:
        x[c] = b[r]
    return x

"""
Pharse 1 single-block Vandermonde decoding: able to reconstruct Any block with ≤ ρ erasures
"""
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
# NESTED SUBGROUPS AND COSET EVALUATION POINTS
# ==============================================================================
def _subgroup_of_order(m, p):
    """Return generator and elements of the unique subgroup of F_q^* of order m."""
    if (p - 1) % m != 0:
        raise ValueError(f"subgroup of order {m} does not exist; m must divide p-1")
    g = galois.primitive_root(p)
    h = pow(g, (p - 1) // m, p)
    return h, [pow(h, i, p) for i in range(m)]


def _coset_representatives(H_small, H_large):
    """Return representatives of the cosets of H_small in H_large."""
    seen = set(); reps = []
    for x in H_large:
        if x not in seen:
            reps.append(x)
            seen.update((x * y) % P_FIELD for y in H_small)
    return reps


class SubgroupStructure:
    """
    Nested subgroups H3 < H2 < H1 < H0 of F_q^*, sized D, omega*D, lambda*omega*D,
    mu*omega*D, with coset representatives for each level.

    H3 is the cell subgroup: each cell contains D symbols, one for each element
    of a coset of H3.
    """
    def __init__(self, mu, lambda_, omega, rho, D):
        p = P_FIELD
        self.D = D
        self.H3_gen, self.H3 = _subgroup_of_order(D, p)
        self.H2_gen, self.H2 = _subgroup_of_order(omega * D, p)
        self.H1_gen, self.H1 = _subgroup_of_order(lambda_ * omega * D, p)
        self.H0_gen, self.H0 = _subgroup_of_order(mu * omega * D, p)

        # Cells in H0 are the |H0|/|H3| cosets of H3 within H0.
        # We use these as the "extended grid" cells of the code.
        self.cells_in_H0 = _coset_representatives(self.H3, self.H0)
        # Cells in H1 are cosets of H3 within H1 -- these are the "blob" cells.
        self.cells_in_H1 = _coset_representatives(self.H3, self.H1)

    def cell_eval_points(self, cell_index):
        """
        Evaluation points for cell `cell_index` (a coset representative).
        Returns the D elements of the coset representative * H3.
        """
        rep = self.cells_in_H0[cell_index]
        return [(rep * h) % P_FIELD for h in self.H3]

    def num_cells(self):
        return len(self.cells_in_H0)


# ==============================================================================
# LOCAL GRS MATRIX (cell-level, per paper)
# ==============================================================================
def _local_grs_cell_matrix(rho_cells, n0_cells, eval_pts_per_cell, p):
    """
    Build the parity-check matrix for one local code, at the CELL level.
    Each column is a cell, and its parity check is over the D symbols in
    that cell (evaluated at the cell's coset elements).

    Returns H_local of shape (rho_cells * D, n0_cells * D).
    """
    n0 = n0_cells * D
    rows = rho_cells * D
    H = GF_BLS12_381.Zeros((rows, n0))
    # Cell c has eval points eval_pts_per_cell[c] = [alpha_0, ..., alpha_{D-1}].
    for c in range(n0_cells):
        pts = eval_pts_per_cell[c]
        for d, a in enumerate(pts):
            for r in range(rho_cells):
                # Row index: r*D + d -- the d-th parallel RS codeword, check r.
                H[r * D + d, c * D + d] = pow(a, r, p)
    return H


# ==============================================================================
# SYMBOL-LEVEL LOCAL GRS (for benchmark compatibility)
# ==============================================================================
def build_local_grs(GF_, rho, n0, eval_pts=None):
    """Local GRS parity-check matrix at SYMBOL level: H[r, c] = eval_pts[c]**r."""
    if eval_pts is None:
        eval_pts = GF_(np.arange(1, n0 + 1))
    else:
        eval_pts = GF_(np.array([int(v) for v in eval_pts]))
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
# ENCODER (symbol-level, benchmark-compatible)
# ==============================================================================
def encode_bc_structured(GF_, m, mu, lambda_, omega, rho):
    """
    Systematic encoder at symbol level. Parity p_i solves
    H_local * [p_i | u_i]^T = 0, with H_local the local GRS matrix
    over evaluation points 1..n0.
    """
    k_total = mu * omega
    n_tot = mu * (rho + omega)
    n0 = rho + lambda_ * omega

    H_local = build_local_grs(GF_, rho, n0)
    H_i = H_local[:, rho:]
    parity_nodes = list(range(1, rho + 1))

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
            parity_nodes, [int(v) for v in (-syn)], int(GF_.characteristic)))
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
# AUXILIARY STACKED GRS DECODER (paper-aligned)
# ==============================================================================
def _build_auxiliary_grs_stacked(n_aux_symbols, k_aux_symbols, D, p):
    """
    Build evaluation points for the auxiliary stacked GRS code over the
    union of two adjacent local codes.

    The aux code has n_aux_symbols total symbols, organized into
    n_aux_symbols / D cells. Each cell's eval points are a coset of H3
    (size D), and the cells partition a subgroup of size n_aux_symbols.

    Returns (eval_pts_list, cell_eval_map):
        eval_pts_list:  flat list of n_aux_symbols evaluation points
        cell_eval_map:  list of length (n_aux_symbols/D), each entry a list
                        of D eval points for that cell.
    """
    if (p - 1) % n_aux_symbols != 0:
        return None, None
    n_cells = n_aux_symbols // D
    if n_aux_symbols % D != 0 or (p - 1) % D != 0:
        return None, None
    H3 = _subgroup_of_order(D, p)[1]
    H_large = _subgroup_of_order(n_aux_symbols, p)[1]
    reps = _coset_representatives(H3, H_large)
    if len(reps) != n_cells:
        return None, None
    cell_eval_map = [[(r * h) % p for h in H3] for r in reps]
    flat = [pt for cell in cell_eval_map for pt in cell]
    return flat, cell_eval_map


def _ntt_decode_stacked(received, mask_local, n_aux, k_aux, D,
                         cell_eval_map, p):
    """
    NTT-based erasure decode of the auxiliary stacked GRS code.

    The code is a stack of D parallel RS codewords over n_cells = n_aux / D
    cells. Each parallel codeword uses the SAME cell ordering but a different
    element within each cell's coset.

    Returns (recovered flat list, success).
    """
    n_cells = n_aux // D
    if len(received) != n_aux:
        return list(received), False

    # Reorganize into cell-major view: rec_cells[c][d] = symbol at cell c,
    # position d within cell.
    rec_cells = [[int(received[c * D + d]) % p for d in range(D)]
                 for c in range(n_cells)]
    mask_cells = [[bool(mask_local[c * D + d]) for d in range(D)]
                  for c in range(n_cells)]

    # Each of the D parallel codewords sees, at cell c, the value rec_cells[c][d].
    # We decode each parallel codeword independently using NTT over the cells.
    k_aux_cells = k_aux // D
    if k_aux % D != 0:
        return list(received), False
    if n_cells - k_aux_cells < 0:
        return list(received), False

    # Build the cell-level evaluation points (one representative per cell).
    # NTT over cells requires a subgroup of order n_cells.
    if (p - 1) % n_cells != 0:
        return list(received), False
    g = galois.primitive_root(p)
    alpha = pow(g, (p - 1) // n_cells, p)
    cell_pts = [pow(alpha, i, p) for i in range(n_cells)]

    recovered = [[0] * D for _ in range(n_cells)]
    for d in range(D):
        # Parallel codeword d: symbols rec_cells[c][d] for c = 0..n_cells-1.
        r_d = [rec_cells[c][d] for c in range(n_cells)]
        m_d = [mask_cells[c][d] for c in range(n_cells)]
        erased = [c for c in range(n_cells) if m_d[c]]
        if not erased:
            for c in range(n_cells):
                recovered[c][d] = r_d[c]
            continue
        if len(erased) > n_cells - k_aux_cells:
            return list(received), False

        # Erasure locator over the cell evaluation points.
        Z = galois.Poly([1], field=GF_BLS12_381)
        for c in erased:
            Z = Z * galois.Poly([1, (-cell_pts[c]) % p], field=GF_BLS12_381)
        Z_desc = [int(x) for x in Z.coeffs]
        Z_asc = list(reversed(Z_desc))
        Z_padded = Z_asc + [0] * (n_cells - len(Z_asc))
        Z_evals = [int(x) for x in galois.ntt(Z_padded, size=n_cells, modulus=p)]

        prod_evals = [(r_d[c] * Z_evals[c]) % p for c in range(n_cells)]
        prod_coeffs = [int(x) for x in galois.intt(prod_evals, size=n_cells, modulus=p)]
        tail = prod_coeffs[k_aux_cells + len(erased):]
        if any(v % p for v in tail):
            return list(received), False

        Prod = galois.Poly(list(reversed(prod_coeffs)), field=GF_BLS12_381)
        q = Prod // Z
        q_asc = list(reversed([int(c) for c in q.coeffs]))
        if len(q_asc) < k_aux_cells:
            q_asc += [0] * (k_aux_cells - len(q_asc))
        else:
            q_asc = q_asc[:k_aux_cells]
        padded = q_asc + [0] * (n_cells - k_aux_cells)
        rec_d = [int(x) for x in galois.ntt(padded, size=n_cells, modulus=p)]
        for c in range(n_cells):
            recovered[c][d] = rec_d[c]

    flat = [recovered[c][d] for c in range(n_cells) for d in range(D)]
    return flat, True


# ==============================================================================
# VERIFICATION AGAINST ACTUAL BC CONSTRAINTS
# ==============================================================================
def _verify_aux_solution(rec_aux, combined, sup_i, sup_j,
                          rho, lambda_, omega, p):
    """Verify rec_aux satisfies the actual stacked BC parity checks."""
    lm_i = {int(g): c for c, g in enumerate(sup_i)}
    lm_j = {int(g): c for c, g in enumerate(sup_j)}
    cols_i = [(c, lm_i[int(g)] + 1) for c, g in enumerate(combined)
              if int(g) in lm_i]
    cols_j = [(c, lm_j[int(g)] + 1) for c, g in enumerate(combined)
              if int(g) in lm_j]
    xv = [int(v) % p for v in rec_aux]
    for cols in (cols_i, cols_j):
        pw = [1] * len(cols)
        xa = [xv[c] for c, _ in cols]
        for r in range(rho):
            if r:
                pw = [pw[k] * cols[k][1] % p for k in range(len(cols))]
            if sum(pw[k] * xa[k] for k in range(len(cols))) % p != 0:
                return False
    return True


# ==============================================================================
# PAIRWISE DECODER: aux stacked GRS with NTT, Gaussian fallback
# ==============================================================================
def dec_cbc_2_aux_ntt(r_in, mask_in, mu, lambda_, omega, rho,
                      D=1, pair_unknown_cap=None, verbose=True):
    """
    Pairwise decoder using the paper's stacked-GRS structure.

    D=1 (default): symbol-level flat code; the aux decoder falls back to
        a single-cell NTT only when n_aux | (p - 1) and D=1. This is the
        benchmark-compatible path.

    D>1: cell-level decoding where the aux code is decoded by D parallel
        NTTs over the cells. Requires D | n_aux and D | p - 1.

    If neither path applies, falls back to Gaussian elimination on the
    stacked 2*rho x e system.
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
    stats = {"phase1": 0, "phase2_aux_ntt": 0, "phase2_gauss": 0,
             "skipped_cap": 0, "aux_verify_fail": 0, "failed_rank": 0,
             "aux_ntt_unavailable": 0}

    while np.any(mask) and progress:
        progress = False
        iterations += 1

        # ---- Phase 1: single-block Vandermonde ----
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

        # ---- Phase 2: pairwise ----
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
                    stats["skipped_cap"] += 1
                    continue

                aux_success = False
                k_aux = n_aux - 2 * rho
                if k_aux > 0:
                    if D == 1:
                        # Symbol-level NTT path: try n_aux-th roots of unity.
                        if (p - 1) % n_aux == 0:
                            evals, cell_map = _build_auxiliary_grs_stacked(
                                n_aux, k_aux, 1, p)
                            if evals is not None:
                                received_aux = [int(r[g]) if not mask[g] else 0
                                                for g in combined]
                                mask_aux = np.array(
                                    [bool(mask[g]) for g in combined])
                                rec, ok = _ntt_decode_stacked(
                                    received_aux, mask_aux, n_aux, k_aux, 1,
                                    cell_map, p)
                                if ok and _verify_aux_solution(
                                        rec, combined, sup_i, sup_j,
                                        rho, lambda_, omega, p):
                                    for c, g in enumerate(combined):
                                        if mask[g]:
                                            r[g] = GF_BLS12_381(rec[c])
                                            mask[g] = False
                                    progress = True
                                    stats["phase2_aux_ntt"] += 1
                                    aux_success = True
                                else:
                                    stats["aux_verify_fail"] += 1
                        else:
                            stats["aux_ntt_unavailable"] += 1
                    else:
                        # Cell-level stacked path: n_aux must be a multiple
                        # of D and a subgroup of that order must exist.
                        if n_aux % D == 0 and (p - 1) % n_aux == 0:
                            evals, cell_map = _build_auxiliary_grs_stacked(
                                n_aux, k_aux, D, p)
                            if evals is not None:
                                received_aux = [int(r[g]) if not mask[g] else 0
                                                for g in combined]
                                mask_aux = np.array(
                                    [bool(mask[g]) for g in combined])
                                rec, ok = _ntt_decode_stacked(
                                    received_aux, mask_aux, n_aux, k_aux, D,
                                    cell_map, p)
                                if ok and _verify_aux_solution(
                                        rec, combined, sup_i, sup_j,
                                        rho, lambda_, omega, p):
                                    for c, g in enumerate(combined):
                                        if mask[g]:
                                            r[g] = GF_BLS12_381(rec[c])
                                            mask[g] = False
                                    progress = True
                                    stats["phase2_aux_ntt"] += 1
                                    aux_success = True
                                else:
                                    stats["aux_verify_fail"] += 1
                        else:
                            stats["aux_ntt_unavailable"] += 1

                if aux_success:
                    continue

                # ---- Gaussian fallback ----
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
                for nrows in (min(2 * rho, e + 8), 2 * rho):
                    try:
                        cand = gf_solve(H_e[:nrows, :], syn_v[:nrows])
                    except GFSolveError:
                        stats["failed_rank"] += 1
                        continue
                    if nrows < 2 * rho:
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
                progress = True
                stats["phase2_gauss"] += 1

    if verbose:
        print(f"dec_cbc_2_aux_ntt: {iterations} iterations, stats={stats}")
    return r, mask


# ==============================================================================
# BENCHMARK WRAPPER
# ==============================================================================
def dec_cbc_2(H_BC, r_in, mask_in, mu, lambda_, omega, rho,
              pair_unknown_cap=None):
    """Signature-compatible wrapper for the benchmark."""
    return dec_cbc_2_aux_ntt(
        r_in, mask_in, mu, lambda_, omega, rho,
        D=1, pair_unknown_cap=pair_unknown_cap, verbose=False)


# ==============================================================================
# GENERALISED t-BLOCK DECODER
# ==============================================================================
def dec_cbc_t(r_in, mask_in, mu, lambda_, omega, rho,
              t_max=4, unknown_cap=None, verbose=True):
    """Combine up to t_max adjacent blocks per solve; Gaussian only for t>=2."""
    p = int(GF_BLS12_381.characteristic)
    r = r_in.copy(); mask = mask_in.copy()
    if unknown_cap is None:
        unknown_cap = t_max * rho
    cap = int(unknown_cap)
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
            S = _partial_syndrome(known_pos + 1,
                                  [int(v) for v in r[sup[known_pos]]],
                                  rows_needed, p)
            syndrome = [(-v) % p for v in S]
            nodes_e = [int(c) + 1 for c in erased_pos]
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
                    S = _partial_syndrome(kn + 1,
                                          [int(v) for v in r[sup[kn]]], rho, p)
                    syndrome.extend([(-v) % p for v in S])
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
    print(f"--- BC Code demo (symbol level) ---")
    print(f"Parameters: mu={mu}, lambda={lambda_}, omega={omega}, rho={rho}")
    print(f"Global [n, k, d]: [{n}, {k}, {d}]")
    print(f"Local code length n0: {n0}\n")

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
        received, mask, mu, lambda_, omega, rho)
    print(f"Decoded in {time.time() - t0:.2f}s")
    print(f"Remaining erasures: {int(remaining.sum())}")
    print(f"Exact match: {bool(np.array_equal(recovered, encoded))}")