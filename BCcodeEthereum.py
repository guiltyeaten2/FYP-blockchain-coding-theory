import galois
import numpy as np

# ==============================================================================
# STEP 1: ETHEREUM BLS12-381 GALOIS FIELD SETUP
# ==============================================================================
# Scalar field modulus r used in Ethereum EIP-4844 / PeerDAS
r_modulus = (
    52435875175126190479447740508185965837690552500527637822603658699938581184513
)
GF_BLS12_381 = galois.GF(r_modulus)

# Block Circulant parameters
mu = 4  # Number of local codes
lambda_ = 2  # Overlap factor
omega = 2  # Overlap width
rho = 2  # Parity constraints per local code

# Derived parameters
block_size = rho + omega
n = mu * block_size  # Global blocklength = 16
k = mu * omega  # Global dimension = 8
d = lambda_ * rho + 1  # Minimum distance = 5
n0 = rho + lambda_ * omega  # Local code length = 6

print(f"--- Block Circulant Code C_BC[{mu}, {lambda_}, {omega}, {rho}] ---")
print(f"Field Modulus (BLS12-381 r): {GF_BLS12_381.characteristic}")
print(f"Global Code [n, k, d]: [{n}, {k}, {d}]")
print(f"Local Codes [n0, k0]: [{n0}, {n0 - rho}]\n")


# ==============================================================================
# HELPER: UNIFIED LOCAL INDEX MAPPING
# ==============================================================================
def get_local_indices(i, mu, lambda_, omega, rho):
    block_size = rho + omega
    local_parity = [i * block_size + j for j in range(rho)]

    local_info = []
    for l in range(lambda_):
        target_block = (i + l) % mu
        info_start = target_block * block_size + rho
        for w in range(omega):
            local_info.append(info_start + w)

    return local_parity + local_info


# ==============================================================================
# STEP 2: PARITY-CHECK MATRIX OVER ETHEREUM FIELD
# ==============================================================================
def build_block_circulant_h(GF, mu, lambda_, omega, rho):
    block_size = rho + omega
    n = mu * block_size
    n0 = rho + lambda_ * omega

    H_BC = GF.Zeros((mu * rho, n))

    # Distinct evaluation points in BLS12-381 scalar field
    eval_pts = GF(np.arange(1, n0 + 1))

    for i in range(mu):
        indices = get_local_indices(i, mu, lambda_, omega, rho)

        # Local GRS check matrix over F_r
        H_local = GF.Zeros((rho, n0))
        for r_idx in range(rho):
            H_local[r_idx, :] = eval_pts**r_idx

        for row_idx in range(rho):
            global_row = i * rho + row_idx
            for col_local_idx, global_col in enumerate(indices):
                H_BC[global_row, global_col] += H_local[row_idx, col_local_idx]

    return H_BC


H_BC = build_block_circulant_h(GF_BLS12_381, mu, lambda_, omega, rho)
print(f"Parity Check Matrix H_BC shape: {H_BC.shape}")


# ==============================================================================
# STEP 3: GENERATOR MATRIX (NULL SPACE OVER F_r)
# ==============================================================================
def derive_generator_matrix(GF, H_BC, k):
    null_space = H_BC.null_space()
    if null_space.shape[0] < k:
        raise ValueError(
            f"Null space rank ({null_space.shape[0]}) < expected k ({k})"
        )
    return null_space[:k, :]


G = derive_generator_matrix(GF_BLS12_381, H_BC, k)


# ==============================================================================
# STEP 4: ETHEREUM DATA PACKING, ENCODING & ERASURE INJECTION
# ==============================================================================
# Generate k random 255-bit field elements (simulating 31-byte packed blob chunks)
print(GF_BLS12_381.Random())
m = GF_BLS12_381.Random(k)
print(m)
c = m @ G  # Codeword in F_r^16

print("\nSample Transmitted Field Element c[0]:\n", c[0])

# Inject 4 erasures (2*rho)
num_erasures = 2 * rho
erased_indices = [0, 3, 5, 9]

received_vector = c.copy()
erased_mask = np.zeros(n, dtype=bool)
for idx in erased_indices:
    erased_mask[idx] = True
    received_vector[idx] = GF_BLS12_381(0)

print(f"\nInjected {num_erasures} erasures at indices: {erased_indices}")


# ==============================================================================
# STEP 5: DECCBC[2] DECODER OVER ETHEREUM FIELD
# ==============================================================================
def dec_cbc_2(H_BC, r_in, mask_in, mu, lambda_, omega, rho):
    r = r_in.copy()
    mask = mask_in.copy()

    progress = True
    while np.any(mask) and progress:
        progress = False

        # Phase 1: Local Code Decoding
        for i in range(mu):
            indices = get_local_indices(i, mu, lambda_, omega, rho)
            local_mask = mask[indices]
            num_local_erasures = np.sum(local_mask)

            if 0 < num_local_erasures <= rho:
                H_local_sub = H_BC[i * rho : (i + 1) * rho, indices]
                erased_pos = np.where(local_mask)[0]
                known_pos = np.where(~local_mask)[0]

                H_e = H_local_sub[:, erased_pos]
                H_k = H_local_sub[:, known_pos]
                r_k = r[[indices[p] for p in known_pos]]

                syndrome = -H_k @ r_k
                r_e = np.linalg.solve(
                    H_e[:num_local_erasures, :num_local_erasures],
                    syndrome[:num_local_erasures],
                )

                for idx_e, val in zip(erased_pos, r_e):
                    global_idx = indices[idx_e]
                    r[global_idx] = val
                    mask[global_idx] = False

                progress = True

        # Phase 2: Pairwise Joint Decoding
        if not progress and np.any(mask):
            for i in range(mu):
                next_i = (i + 1) % mu
                idx1 = get_local_indices(i, mu, lambda_, omega, rho)
                idx2 = get_local_indices(next_i, mu, lambda_, omega, rho)
                combined_indices = sorted(list(set(idx1 + idx2)))

                pair_mask = mask[combined_indices]
                num_pair_erasures = np.sum(pair_mask)

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