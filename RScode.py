import reedsolo

def reed_solomon_demo(message_str: str):
    # Initialize the Reed-Solomon Codec with the specified ECC bytes
    ecc_symbols = min(255//2,len(message_str)//2)
    rs = reedsolo.RSCodec(ecc_symbols)
    
    print("=" * 60)
    print("1. ORIGINAL MESSAGE")
    print("=" * 60)
    # Reed-Solomon operates on raw byte values, not strings
    original_bytes = message_str.encode('utf-8')
    print(f"Text String:      '{message_str}'")
    print(f"Byte Values:      {list(original_bytes)}")
    print(f"Payload Size:     {len(original_bytes)} bytes\n")

    print("=" * 60)
    print("2. ENCODING (Adding Error Correction Bytes)")
    print("=" * 60)
    # The codec appends ECC bytes to the original payload polynomial
    encoded_data = rs.encode(original_bytes)
    print(f"Encoded Bytes:    {list(encoded_data)}")
    print(f"Total Size:       {len(encoded_data)} bytes ({len(original_bytes)} Payload + {ecc_symbols} ECC)")
    print(f"ECC Bytes Added:  {list(encoded_data[-ecc_symbols:])}\n")

    print("=" * 60)
    print("3. CORRUPTING DATA (Simulating Errors in Transit)")
    print("=" * 60)
    # Reed-Solomon can correct up to (ecc_symbols / 2) corrupted bytes
    corrupted_data = bytearray(encoded_data)
    
    # Introduce byte errors at specific index positions
    corrupt_positions = [1, 4, 7]  # 3 errors (Max allowed for 6 ECC bytes is 6 / 2 = 3)
    for pos in corrupt_positions:
        corrupted_data[pos] ^= 0xFF  # Flip bits at position
        
    print(f"Errors Injected:  At byte indices {corrupt_positions}")
    print(f"Corrupted Bytes:  {list(corrupted_data)}")
    print(f"Corrupted Text:   '{corrupted_data.decode('utf-8', errors='ignore')}'\n")

    print("=" * 60)
    print("4. DECODING & ERROR CORRECTION")
    print("=" * 60)
    try:
        # Syndrome calculation detects errors and solves for error locations/values
        decoded_bytes, decoded_full, err_positions = rs.decode(corrupted_data)
        
        print(f"Corrected Indices:{list(err_positions)}")
        print(f"Restored Bytes:   {list(decoded_bytes)}")
        print(f"Restored Text:    '{decoded_bytes.decode('utf-8')}'")
        print("\nSUCCESS: Original message completely recovered!")
        
    except reedsolo.ReedSolomonError as e:
        print(f"FAILURE: Too many errors to recover original data ({e})")

if __name__ == "__main__":
    # Test message
    sample_text = "Hello RS Code111!"
    # 6 ECC bytes allow fixing up to 3 corrupted byte positions
    reed_solomon_demo(sample_text)