import numpy as np
import reedsolo

def print_matrix(title, matrix):
    """Helper to cleanly display 2D matrices in terminal in Hex format"""
    print(f"\n--- {title} (Shape: {matrix.shape[0]}x{matrix.shape[1]}) ---")
    for r in range(matrix.shape[0]):
        row_str = " ".join(f"{val:02X}" for val in matrix[r])
        print(f"Row {r:02d}: [ {row_str} ]")

# ---------------------------------------------------------
# SETUP & PARAMETERS
# ---------------------------------------------------------
k_rows, k_cols = 4, 6      # Original Data Matrix (4 rows x 6 cols = 24 bytes)
row_nsym = 3                # Horizontal parity bytes (adds 3 cols -> n1 = 9)
col_nsym = 3                # Vertical parity bytes (adds 3 rows -> n2 = 7)

row_rsc = reedsolo.RSCodec(row_nsym)
col_rsc = reedsolo.RSCodec(col_nsym)

print("=" * 65)
print(" 2D REED-SOLOMON FULL PIPELINE (FIXED SLICING & RECOVERY)")
print("=" * 65)

# ---------------------------------------------------------
# STEP 1: MATRIX SETUP
# ---------------------------------------------------------
message = b"2D-RS-CODE-DEMO!"  # Exactly 16 bytes
original_len = len(message)     # Preserve original payload length

# Pad payload to fill total 4x6 data matrix capacity (24 bytes)
payload_padded = message.ljust(k_rows * k_cols, b"\x00")
data_matrix = np.frombuffer(payload_padded, dtype=np.uint8).reshape((k_rows, k_cols))

print_matrix("STEP 1: Original Payload Matrix (k_rows x k_cols)", data_matrix)

# ---------------------------------------------------------
# STEP 2: HORIZONTAL RS ENCODING
# ---------------------------------------------------------
horiz_encoded = [list(row_rsc.encode(bytes(row))) for row in data_matrix]
horiz_matrix = np.array(horiz_encoded, dtype=np.uint8)

print_matrix("STEP 2: Horizontal Encoding (Adds Row Parity)", horiz_matrix)

# ---------------------------------------------------------
# STEP 3: VERTICAL RS ENCODING (FULL 2D GRID)
# ---------------------------------------------------------
vert_encoded = [list(col_rsc.encode(bytes(col))) for col in horiz_matrix.T]
encoded_grid = np.array(vert_encoded, dtype=np.uint8).T

print_matrix("STEP 3: Vertical Encoding (Full 2D Product Code Grid)", encoded_grid)

# ---------------------------------------------------------
# STEP 4: CORRUPTION & ERASURE INJECTION
# ---------------------------------------------------------
corrupted_grid = encoded_grid.copy()

# Erasure 1: Complete Row 1 zeroed out
corrupted_grid[1, :] = 0x00
erased_rows = [1]

# Erasure 2: Complete Col 4 zeroed out
corrupted_grid[:, 4] = 0x00
erased_cols = [4]

# Unknown Random Byte Error (position 3, 7)
corrupted_grid[3, 7] ^= 0xFF  

print_matrix("STEP 4: Corrupted Matrix", corrupted_grid)

# ---------------------------------------------------------
# STEP 5: ITERATIVE DECODING & MATRIX RECOVERY
# ---------------------------------------------------------
recovered = corrupted_grid.copy()

print("\n" + "=" * 65)
print(" STEP 5: ITERATIVE DECODING PROCESS")
print("=" * 65)

# Pass 1: Vertical Decoding (Fixes missing values along erased rows)
for c in range(recovered.shape[1]):
    # For each column, we know the erased row indices.
    # If the current column is also an erased column, all its bytes are erasures.
    current_erase_pos = erased_rows
    if c in erased_cols:
        current_erase_pos = list(range(recovered.shape[0]))
    try:
        # Pass copy of column with erased row index relative to column length
        _, full_col, _ = col_rsc.decode(bytes(recovered[:, c]), erase_pos=current_erase_pos)
        recovered[:, c] = list(full_col)
    except reedsolo.ReedSolomonError:
        pass

print_matrix("STEP 5A: After Vertical Pass", recovered)

# Pass 2: Horizontal Decoding (Fixes missing values along erased columns)
for r in range(recovered.shape[0]):
    try:
        # After the vertical pass, we no longer treat columns as fully erased.
        # Instead, we let the row decoder use its full power to find and fix
        # any remaining errors (like the random byte flip).
        _, full_row, _ = row_rsc.decode(bytes(recovered[r, :]))
        recovered[r, :] = list(full_row)
    except reedsolo.ReedSolomonError:
        pass

print_matrix("STEP 5B: After Horizontal Pass (Full Grid Recovered)", recovered)

# ---------------------------------------------------------
# STEP 6: PAYLOAD EXTRACTION & VERIFICATION
# ---------------------------------------------------------
# 1. Slices top-left k_rows x k_cols block
# 2. Converts to bytes
# 3. Truncates exact original payload byte length
extracted_bytes = recovered[:k_rows, :k_cols].tobytes()[:original_len]

print("\n" + "=" * 65)
print(" STEP 6: VERIFICATION & EXTRACTION")
print("=" * 65)
print(f"Matrix Match Success: {np.array_equal(encoded_grid, recovered)}")
print(f"Original Text:        {message.decode('utf-8')}")
print(f"Recovered Text:       {extracted_bytes.decode('utf-8')}")