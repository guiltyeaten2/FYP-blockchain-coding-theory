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

        # Eliminate this column in all other rows (both below and above)
        for r in range(m):
            if r != row and A[r, col] != 0:
                factor = A[r, col]
                A[r, :] = A[r, :] - factor * A[row, :]
                b[r] = b[r] - factor * b[row]

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
    for i in range(mu):
        # Global indices that take part in local equation i
        indices = get_local_indices(i, mu, lambda_, omega, rho)
        # Build local GRS matrix (rho x n0)
        H_local = GF.Zeros((rho, n0))
        for r_idx in range(rho):
            H_local[r_idx, :] = eval_pts ** r_idx

        # Place H_local columns into the global H_BC at the correct positions
        for row_idx in range(rho):
            global_row = i * rho + row_idx
            for col_local_idx, global_col in enumerate(indices):
                H_BC[global_row, global_col] += H_local[row_idx, col_local_idx]
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
    H_local = GF.Zeros((rho, n0))
    for r_idx in range(rho):
        H_local[r_idx, :] = eval_pts ** r_idx

    # Split into parity part (rho columns) and information part (lambda*omega)
    H_p = H_local[:, :rho]          # rho x rho
    H_i = H_local[:, rho:]          # rho x (lambda * omega)

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
        p_i = gf_solve(H_p, -syndrome_info)

        # Place parity into the codeword
        p_start = k_total + i * rho
        c[p_start : p_start + rho] = p_i

    print(f"Encoding finished in {time.time()-start:.2f}s")
    return c



# ==============================================================================
# STEP : DECCBC[2] DECODER (Section 3D of the paper)
# ==============================================================================
def dec_cbc_2(H_BC, r_in, mask_in, mu, lambda_, omega, rho):
    """
    Decoder for Block Circulant codes with parameter t=2 (i.e., can correct
    up to 2*rho erasures total).
    
    It iteratively performs:
        1) Single‑local‑block decoding: if a local block has ≤ rho erasures,
           recover them using its local parity equations.
        2) Pairwise joint decoding: if two neighbouring local blocks together
           have ≤ 2*rho erasures, recover them simultaneously.
    """
    r = r_in.copy()
    mask = mask_in.copy()
    progress = True
    iterations = 0

    while np.any(mask) and progress:
        progress = False
        iterations += 1

        # ---------- Phase 1: Single Local Decoding ----------
        for i in range(mu):
            indices = get_local_indices(i, mu, lambda_, omega, rho)
            local_mask = mask[indices]
            num_local_erasures = np.sum(local_mask)

            if 0 < num_local_erasures <= rho:
                # Extract the local submatrix of H_BC for this block
                H_local_sub = H_BC[i * rho : (i + 1) * rho, indices]
                erased_pos = np.where(local_mask)[0]
                known_pos = np.where(~local_mask)[0]

                H_e = H_local_sub[:, erased_pos]
                H_k = H_local_sub[:, known_pos]
                r_k = r[[indices[p] for p in known_pos]]

                # Solve H_e * r_e = - H_k * r_k. With <= rho erasures and rho
                # parity rows drawn from distinct GRS evaluation points this
                # is always uniquely solvable, but the solve is guarded anyway
                # so a parameter change can never silently fabricate values.
                syndrome = -H_k @ r_k
                try:
                    r_e = gf_solve(H_e, syndrome)
                except GFSolveError:
                    continue   # leave this block's erasures flagged

                # Fill recovered values
                for idx_e, val in zip(erased_pos, r_e):
                    global_idx = indices[idx_e]
                    r[global_idx] = val
                    mask[global_idx] = False
                progress = True

        # ---------- Phase 2: Pairwise Joint Decoding ----------
        # Only if no progress from single-block decoding and erasures remain
        if not progress and np.any(mask):
            for i in range(mu):
                next_i = (i + 1) % mu
                # Union of the two local support sets
                idx1 = get_local_indices(i, mu, lambda_, omega, rho)
                idx2 = get_local_indices(next_i, mu, lambda_, omega, rho)
                combined_indices = sorted(list(set(idx1 + idx2)))

                pair_mask = mask[combined_indices]
                num_pair_erasures = np.sum(pair_mask)

                # NOTE: `<= 2*rho` is necessary but NOT sufficient. These four
                # rows are block i's own rho parity checks stacked on block
                # i+1's -- not the auxiliary [2(w+p), 2w, 2p+1] GRS code over
                # the union of the two supports that the source paper's
                # Algorithm 1 builds. The stacked form is not MDS, so a split
                # like "3 erasures inside block i's support, 1 inside i+1's"
                # leaves block i's 2 equations facing 3 unknowns. gf_solve now
                # raises on exactly that case and the pair is skipped, rather
                # than zero-filling the undetermined positions.
                if 0 < num_pair_erasures <= 2 * rho:
                    # Rows of H_BC corresponding to the two local blocks
                    rows_pair = list(range(i * rho, (i + 1) * rho)) + \
                                list(range(next_i * rho, (next_i + 1) * rho))
                    H_pair = H_BC[rows_pair, :][:, combined_indices]

                    erased_pos = np.where(pair_mask)[0]
                    known_pos = np.where(~pair_mask)[0]

                    H_e = H_pair[:, erased_pos]
                    H_k = H_pair[:, known_pos]
                    r_k = r[[combined_indices[p] for p in known_pos]]

                    syndrome = -H_k @ r_k
                    try:
                        r_e = gf_solve(H_e, syndrome)
                    except GFSolveError:
                        continue   # this pair is not jointly determined; leave it
                    for idx_e, val in zip(erased_pos, r_e):
                        global_idx = combined_indices[idx_e]
                        r[global_idx] = val
                        mask[global_idx] = False
                    progress = True
                    # Continue scanning the remaining pairs in this same pass.
                    # The previous version broke out to restart Phase 1 after
                    # every single pair fixed, paying a full O(mu) rescan per
                    # recovered pair -- which is why round counts ran into the
                    # hundreds. Each pair re-reads the live mask, so fixing
                    # several per pass is equivalent and far cheaper.

    print(f"Decoder finished in {iterations} iterations.")
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