import numpy as np
import galois
import blob_generator 
# ==============================================================================
# STEP 1: PARAMETER SPECIFICATION
# ==============================================================================
# Code parameters as specified in paper Section III
mu = 4        # Number of local codes (must be a multiple of lambda)
lambda_ = 2   # Overlap factor
omega = 2     # Overlap width
rho = 2       # Parity check constraints per local code / Redundancy

# Derived code parameters
n = mu * (rho + omega)         # Global blocklength: 4 * (2 + 2) = 16
k = mu * omega                 # Global dimension:   4 * 2 = 8
d = lambda_ * rho + 1          # Minimum distance:   2 * 2 + 1 = 5
n0 = rho + lambda_ * omega     # Local code length:  2 + 2*2 = 6
k0 = lambda_ * omega           # Local code dim:     2*2 = 4
d0 = rho + 1                   # Local min distance: 2 + 1 = 3

print(f"--- Block Circulant Code C_BC[{mu}, {lambda_}, {omega}, {rho}] ---")
print(f"Global Code [n, k, d]: [{n}, {k}, {d}]")
print(f"Local Codes [n0, k0, d0]: [{n0}, {k0}, {d0}]\n")

# Field creation: Prime field F_11
GF = blob_generator.random_blob


# ==============================================================================
# HELPER: UNIFIED INDEX MAPPING
# ==============================================================================
def get_local_indices(i, mu, lambda_, omega, rho):
    """
    Returns the exact global symbol indices belonging to local code i,
    preserving explicit lambda-block overlapping.
    """
    block_size = rho + omega
    # Local parity indices in block i
    local_parity = [i * block_size + j for j in range(rho)]

    # Local info indices spanning lambda_ adjacent blocks
    local_info = []
    for l in range(lambda_):
        target_block = (i + l) % mu
        info_start = target_block * block_size + rho
        for w in range(omega):
            local_info.append(info_start + w)

    return local_parity + local_info


# ==============================================================================
# STEP 2: TOPOLOGY BUILD & PARITY-CHECK MATRIX (H_BC) INSTANTIATION
# ==============================================================================
def build_block_circulant_h(GF, mu, lambda_, omega, rho):
    """
    Constructs the Block Circulant Parity Check Matrix H_BC of size (mu*rho) x n
    using explicit lambda-block overlapping.
    """
    block_size = rho + omega
    n = mu * block_size
    n0 = rho + lambda_ * omega

    H_BC = GF.Zeros((mu * rho, n))

    # Evaluation points for local GRS check matrix of length n0
    eval_pts = GF(np.arange(1, n0 + 1))

    for i in range(mu):
        global_indices = get_local_indices(i, mu, lambda_, omega, rho)

        # Build local GRS parity-check matrix (rho x n0)
        H_local = GF.Zeros((rho, n0))
        for r in range(rho):
            H_local[r, :] = eval_pts**r

        # Insert local check matrix into global H_BC using index structure
        for row_idx in range(rho):
            global_row = i * rho + row_idx
            for col_local_idx, global_col in enumerate(global_indices):
                H_BC[global_row, global_col] += H_local[row_idx, col_local_idx]

    return H_BC


H_BC = build_block_circulant_h(GF, mu, lambda_, omega, rho)
print(f"Parity Check Matrix H_BC shape: {H_BC.shape}")


# ==============================================================================
# STEP 3: SYSTEMATIC GENERATOR MATRIX DERIVATION (G)
# ==============================================================================
def derive_generator_matrix(GF, H_BC, k, n):
    """
    Derives generator matrix G such that H_BC * G^T = 0
    using the null space of H_BC over the Galois Field.
    """
    null_space = H_BC.null_space()

    if null_space.shape[0] < k:
        raise ValueError(
            f"Null space rank ({null_space.shape[0]}) is less than expected k ({k})."
        )

    G = null_space[:k, :]
    return G


G = derive_generator_matrix(GF, H_BC, k, n)


# ==============================================================================
# STEP 4: ENCODING & ERASURE CHANNEL INJECTION
# ==============================================================================
# Random message vector m of dimension k
m = GF.Random(k)
c = m @ G  # Codeword of length n

print("Encoded Codeword c:\n", c)

# Inject erasures (up to 2*rho erasures can be corrected reliably)
num_erasures = 2 * rho  # 4 erasures
erased_indices = [0, 3, 5, 9]  # Specific erased positions

received_vector = c.copy()
erased_mask = np.zeros(n, dtype=bool)
for idx in erased_indices:
    erased_mask[idx] = True
    received_vector[idx] = GF(0)  # Symbol erased (tracked via mask)

print(f"\nInjected {num_erasures} erasures at indices: {erased_indices}")


# ==============================================================================
# STEP 5: DECCBC[2] ITERATIVE ERASURE DECODER
# ==============================================================================
def dec_cbc_2(H_BC, r_in, mask_in, mu, lambda_, omega, rho):
    """
    DECCBC[2] Erasure Decoder implementation.
    Phase 1: Individual Local Code Erasure Correction (<= rho erasures per local code).
    Phase 2: Pairwise Joint Local Code Decoding (if local decoding stalls).
    """
    r = r_in.copy()
    mask = mask_in.copy()

    progress = True
    while np.any(mask) and progress:
        progress = False

        # ----------------------------------------------------------------------
        # Phase 1: Local Code Decoding
        # ----------------------------------------------------------------------
        for i in range(mu):
            indices = get_local_indices(i, mu, lambda_, omega, rho)
            local_mask = mask[indices]
            num_local_erasures = np.sum(local_mask)

            # If erasures exist and are <= rho, local code can solve them
            if 0 < num_local_erasures <= rho:
                H_local_sub = H_BC[i * rho : (i + 1) * rho, indices]

                erased_pos = np.where(local_mask)[0]
                known_pos = np.where(~local_mask)[0]

                H_e = H_local_sub[:, erased_pos]
                H_k = H_local_sub[:, known_pos]
                r_k = r[[indices[p] for p in known_pos]]

                syndrome = -H_k @ r_k

                # Solve square linear system for erased symbols
                r_e = np.linalg.solve(
                    H_e[:num_local_erasures, :num_local_erasures],
                    syndrome[:num_local_erasures],
                )

                # Update vector
                for idx_e, val in zip(erased_pos, r_e):
                    global_idx = indices[idx_e]
                    r[global_idx] = val
                    mask[global_idx] = False

                progress = True

        # ----------------------------------------------------------------------
        # Phase 2: Pairwise Joint Decoding (if Phase 1 is stuck)
        # ----------------------------------------------------------------------
        if not progress and np.any(mask):
            for i in range(mu):
                next_i = (i + 1) % mu
                idx1 = get_local_indices(i, mu, lambda_, omega, rho)
                idx2 = get_local_indices(next_i, mu, lambda_, omega, rho)
                combined_indices = sorted(list(set(idx1 + idx2)))

                pair_mask = mask[combined_indices]
                num_pair_erasures = np.sum(pair_mask)

                # Pair decoder can solve up to 2*rho joint erasures
                if 0 < num_pair_erasures <= 2 * rho:
                    rows_pair = list(range(i * rho, (i + 1) * rho)) + list(
                        range(next_i * rho, (next_i + 1) * rho)
                    )
                    H_pair = H_BC[rows_pair, :][:, combined_indices]

                    erased_pos = np.where(pair_mask)[0]
                    known_pos = np.where(~pair_mask)[0]

                    H_e = H_pair[:, erased_pos]
                    H_k = H_pair[:, known_pos]
                    r_k = r[[combined_indices[p] for p in known_pos]]

                    syndrome = -H_k @ r_k
                    try:
                        r_e = np.linalg.solve(
                            H_e[:num_pair_erasures, :num_pair_erasures],
                            syndrome[:num_pair_erasures],
                        )
                        for idx_e, val in zip(erased_pos, r_e):
                            global_idx = combined_indices[idx_e]
                            r[global_idx] = val
                            mask[global_idx] = False
                        progress = True
                        break
                    except np.linalg.LinAlgError:
                        continue

    return r, mask


recovered_c, remaining_mask = dec_cbc_2(
    H_BC, received_vector, erased_mask, mu, lambda_, omega, rho
)


# ==============================================================================
# STEP 6: VERIFICATION
# ==============================================================================
syndrome_check = H_BC @ recovered_c
is_valid_codeword = np.all(syndrome_check == 0)
is_exact_match = np.array_equal(recovered_c, c)

print("\n--- Decoding Verification Results ---")
print("Remaining Erasures Unresolved:", np.sum(remaining_mask))
print("Parity Check Satisfied (H_BC * c^T == 0):", is_valid_codeword)
print("Decoded Vector Matches Transmitted Codeword:", is_exact_match)