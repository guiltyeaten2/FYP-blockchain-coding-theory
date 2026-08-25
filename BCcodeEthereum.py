import time
import numpy as np

# ==============================================================================
# IMPORT ETHEREUM BLOB GENERATOR (EIP-4844 / consensus-specs)
# ==============================================================================
from blob_generator import FIELD_ELEMENTS_PER_BLOB, GF, random_blob

GF_BLS12_381 = GF

# ==============================================================================
# HELPER: GALOIS FIELD LINEAR SYSTEM SOLVER (F_q)
# ==============================================================================
def gf_solve(A, b):
    """
    Solves A * x = b over GF(p) using Gaussian Elimination.
    A: GF matrix of shape (m, n)
    b: GF array of shape (m,)
    Returns: x (GF array of shape (n,))
    """
    A = A.copy()
    b = b.copy()
    m, n = A.shape
    
    # Forward Elimination
    row = 0
    col_map = []
    for col in range(n):
        if row >= m:
            break
        # Find pivot in column
        pivot = -1
        for r in range(row, m):
            if A[r, col] != 0:
                pivot = r
                break
        if pivot == -1:
            continue
            
        # Swap rows
        if pivot != row:
            A[[row, pivot]] = A[[pivot, row]]
            b[[row, pivot]] = b[[pivot, row]]
            
        # Normalize pivot row
        inv_pivot = A[row, col] ** -1
        A[row, :] = A[row, :] * inv_pivot
        b[row] = b[row] * inv_pivot
        
        # Eliminate below and above
        for r in range(m):
            if r != row and A[r, col] != 0:
                factor = A[r, col]
                A[r, :] = A[r, :] - factor * A[row, :]
                b[r] = b[r] - factor * b[row]
                
        col_map.append((row, col))
        row += 1
        
    # Back-Substitution / Extraction
    x = GF_BLS12_381.Zeros(n)
    for r, c in col_map:
        x[c] = b[r]
    return x

# ==============================================================================
# STEP 1: BLOCK CIRCULANT PARAMETERS
# ==============================================================================
omega = 2                             # Information symbols per local block
rho = 2                               # Parity symbols per local block
lambda_ = 2                           # Overlap factor
mu = FIELD_ELEMENTS_PER_BLOB // omega # 2048

block_size = rho + omega               # 4
n = mu * block_size                    # 8192
k = mu * omega                         # 4096
d = lambda_ * rho + 1                  # 5
n0 = rho + lambda_ * omega             # 6 (Local code length)

print(f"--- BC Code with Full Blob (4096 elements) ---")
print(f"Parameters: mu={mu}, lambda={lambda_}, omega={omega}, rho={rho}")
print(f"Global Code [n, k, d]: [{n}, {k}, {d}]")
print(f"Local Code Length n0: {n0}\n")

# ==============================================================================
# STEP 2: LOCAL INDEX MAPPING (Section 3-B)
# ==============================================================================
def get_local_indices(i, mu, lambda_, omega, rho):
    """
    Returns global codeword indices belonging to the i-th local code constraint.
    Layout: [p_i (rho elements), m_{i} ... m_{i+lambda-1} (lambda * omega elements)]
    """
    k_tot = mu * omega
    # Local parity indices start after systematic message part (k)
    local_parity = [k_tot + i * rho + r for r in range(rho)]
    
    # Overlapping systematic message indices
    local_info = []
    for l in range(lambda_):
        target_block = (i + l) % mu
        info_start = target_block * omega
        for w in range(omega):
            local_info.append(info_start + w)
            
    return local_parity + local_info

# ==============================================================================
# STEP 3: PARITY-CHECK MATRIX CONSTRUCTION (Section 3-C)
# ==============================================================================
def build_block_circulant_h(GF, mu, lambda_, omega, rho):
    n = mu * (rho + omega)
    n0 = rho + lambda_ * omega
    H_BC = GF.Zeros((mu * rho, n))
    eval_pts = GF(np.arange(1, n0 + 1))

    print("Building H_BC for verification...")
    for i in range(mu):
        indices = get_local_indices(i, mu, lambda_, omega, rho)
        H_local = GF.Zeros((rho, n0))
        for r_idx in range(rho):
            H_local[r_idx, :] = eval_pts**r_idx

        for row_idx in range(rho):
            global_row = i * rho + row_idx
            for col_local_idx, global_col in enumerate(indices):
                H_BC[global_row, global_col] += H_local[row_idx, col_local_idx]
    return H_BC

H_BC = build_block_circulant_h(GF_BLS12_381, mu, lambda_, omega, rho)
print(f"H_BC shape: {H_BC.shape}\n")

# ==============================================================================
# STEP 4: STRUCTURED SYSTEMATIC ENCODER (Section 3-D)
# ==============================================================================
def encode_bc_structured(GF, m, mu, lambda_, omega, rho):
    """
    True Systematic Encoder: c = [m | p]
    c[:k] = m
    c[k:] = p (computed per local block parity solve)
    """
    k_tot = mu * omega
    n_tot = mu * (rho + omega)
    n0 = rho + lambda_ * omega
    eval_pts = GF(np.arange(1, n0 + 1))
    
    # Local GRS parity matrix: H_local = [H_p | H_i]
    H_local = GF.Zeros((rho, n0))
    for r_idx in range(rho):
        H_local[r_idx, :] = eval_pts**r_idx
        
    H_p = H_local[:, :rho]          # rho x rho
    H_i = H_local[:, rho:]          # rho x (lambda * omega)
    
    m_blocks = m.reshape((mu, omega))
    c = GF.Zeros(n_tot)
    c[:k_tot] = m  # Assign systematic message directly

    print("Encoding via local GRS solvers...")
    start = time.time()
    
    for i in range(mu):
        # Gather overlapping information vector u_i
        u_i = GF.Zeros(lambda_ * omega)
        for l in range(lambda_):
            target_block = (i + l) % mu
            u_i[l*omega : (l+1)*omega] = m_blocks[target_block, :]
            
        # Compute local parity p_i = - H_p^-1 * H_i * u_i
        syndrome_info = H_i @ u_i
        p_i = gf_solve(H_p, -syndrome_info)
        
        # Place into local parity section
        p_start = k_tot + i * rho
        c[p_start : p_start + rho] = p_i

    print(f"Encoding finished in {time.time()-start:.2f}s")
    return c

# ==============================================================================
# STEP 5: GENERATE BLOB & ENCODE
# ==============================================================================
print("Generating full Ethereum-standard blob (4096 elements)...")
full_blob = random_blob()
m = GF_BLS12_381(full_blob)

c = encode_bc_structured(GF_BLS12_381, m, mu, lambda_, omega, rho)

print(f"Message m length: {len(m)}")
print(f"Codeword c length: {len(c)}")
print(f"Sample codeword parity[0:10]: {c[k:k+10]}\n")

# ==============================================================================
# STEP 6: INJECT ERASURES
# ==============================================================================
num_erasures = 2 * rho  # 4 erasures
erased_indices = sorted(np.random.choice(n, num_erasures, replace=False).tolist())

received_vector = c.copy()
erased_mask = np.zeros(n, dtype=bool)
for idx in erased_indices:
    erased_mask[idx] = True
    received_vector[idx] = GF_BLS12_381(0)

print(f"Injected {num_erasures} erasures at indices: {erased_indices}")

# ==============================================================================
# STEP 7: DECCBC[2] DECODER (Section 4)
# ==============================================================================
def dec_cbc_2(H_BC, r_in, mask_in, mu, lambda_, omega, rho):
    r = r_in.copy()
    mask = mask_in.copy()
    progress = True
    iterations = 0
    
    while np.any(mask) and progress:
        progress = False
        iterations += 1

        # Phase 1: Single Local Decoding (<= rho erasures)
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
                r_e = gf_solve(H_e[:, :num_local_erasures], syndrome)

                for idx_e, val in zip(erased_pos, r_e):
                    global_idx = indices[idx_e]
                    r[global_idx] = val
                    mask[global_idx] = False
                progress = True

        # Phase 2: Pairwise Joint Decoding (<= 2*rho erasures)
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
                        r_e = gf_solve(H_e, syndrome)
                        for idx_e, val in zip(erased_pos, r_e):
                            global_idx = combined_indices[idx_e]
                            r[global_idx] = val
                            mask[global_idx] = False
                        progress = True
                        break
                    except Exception:
                        continue

    print(f"Decoder finished in {iterations} iterations.")
    return r, mask

print("\nStarting DecCBC[2] Decoder (Section 4)...")
start = time.time()
recovered_c, remaining_mask = dec_cbc_2(
    H_BC, received_vector, erased_mask, mu, lambda_, omega, rho
)
print(f"Decoding finished in {time.time()-start:.2f}s")

# ==============================================================================
# STEP 8: VERIFICATION
# ==============================================================================
syndrome_check = H_BC @ recovered_c
is_valid_codeword = np.all(syndrome_check == 0)
is_exact_match = np.array_equal(recovered_c, c)

print("\n--- Decoding Verification Results ---")
print("Remaining Erasures Unresolved:", np.sum(remaining_mask))
print("Parity Check Satisfied (H_BC * c^T == 0):", is_valid_codeword)
print("Decoded Vector Matches Transmitted Codeword:", is_exact_match)

# Systematic recovery check
recovered_message = recovered_c[:k]
print("Original message first 2 element:", m[:2])
print("Recovered message first 2 element:", recovered_message[:2])
print("Full systematic recovery successful!" if np.array_equal(m, recovered_message) else "Mismatch in recovered message!")