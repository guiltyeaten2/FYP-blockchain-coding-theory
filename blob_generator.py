"""
Ethereum-standard blob generator.

    pip install galois

Produces raw blob data (arrays of BLS12-381 Fr field elements) that
conform to Ethereum's actual blob format (EIP-4844 / consensus-specs),
independent of any particular erasure-coding scheme.

DESIGN INTENT: 1D-RS, 2D-RS, LDPC, Block-Circulant, and RLNC modules
should all be able to consume the SAME blob objects this produces --
reshaping/structuring the data however their own scheme needs is each
scheme's job, not this generator's. A blob here is just a plain flat
Python list of FIELD_ELEMENTS_PER_BLOB ints, nothing more.

This module has NO standalone execution -- it is imported and called
by whichever coding-scheme script needs a blob (e.g. 2d_rs_blob_scale.py).
Running this file directly does nothing.

"""

import galois

# ---------------------------------------------------------------------------
# ETHEREUM BLOB CONSTANTS (EIP-4844 / consensus-specs)
# ---------------------------------------------------------------------------
BLS_MODULUS = 52435875175126190479447740508185965837690552500527637822603658699938581184513
FIELD_ELEMENTS_PER_BLOB = 4096            # real spec constant
BYTES_PER_FIELD_ELEMENT = 32              # each element's wire slot
USABLE_BYTES_PER_FIELD_ELEMENT = 31       # 31 bytes = 248 bits, always < BLS_MODULUS
USABLE_BYTES_PER_BLOB = FIELD_ELEMENTS_PER_BLOB * USABLE_BYTES_PER_FIELD_ELEMENT  # 126976

GF = galois.GF(BLS_MODULUS)  # module-level field class, reused by every Random() call


def validate_blob(blob):
    """A blob is valid iff it has exactly FIELD_ELEMENTS_PER_BLOB elements,
    each a canonical field element (0 <= value < BLS_MODULUS)."""
    if len(blob) != FIELD_ELEMENTS_PER_BLOB:
        raise ValueError(f"blob has {len(blob)} elements, expected {FIELD_ELEMENTS_PER_BLOB}")
    for v in blob:
        if not (0 <= v < BLS_MODULUS):
            raise ValueError(f"field element {v} is not canonical (must be < BLS_MODULUS)")
    return True


# ---------------------------------------------------------------------------
# REAL APPLICATION DATA -> BLOB(S)
# ---------------------------------------------------------------------------
def bytes_to_blobs(data: bytes):
    """Pack arbitrary application bytes into one or more standards-shaped
    blobs, using the standard 31-usable-bytes-per-32-byte-word convention.
    Returns a list of blobs; each blob is a flat Python list of
    FIELD_ELEMENTS_PER_BLOB ints. Last blob is zero-padded."""
    blobs = []
    for blob_start in range(0, len(data), USABLE_BYTES_PER_BLOB):
        blob_chunk = data[blob_start: blob_start + USABLE_BYTES_PER_BLOB]
        blob_chunk = blob_chunk.ljust(USABLE_BYTES_PER_BLOB, b"\x00")
        elements = []
        for i in range(FIELD_ELEMENTS_PER_BLOB):
            word = blob_chunk[i * USABLE_BYTES_PER_FIELD_ELEMENT:
                               (i + 1) * USABLE_BYTES_PER_FIELD_ELEMENT]
            elements.append(int.from_bytes(word, "big"))
        blobs.append(elements)
    return blobs


def blob_to_bytes(blob) -> bytes:
    """Inverse of bytes_to_blobs's packing for ONE blob. Caller truncates
    to the known original length."""
    validate_blob(blob)
    out = bytearray()
    for v in blob:
        out += v.to_bytes(USABLE_BYTES_PER_FIELD_ELEMENT, "big")
    return bytes(out)


# ---------------------------------------------------------------------------
# SYNTHETIC / RANDOM BLOBS -- for cross-scheme benchmarking
# ---------------------------------------------------------------------------
def random_field_element() -> int:
    """One random canonical field element, via galois's own GF.Random()."""
    return int(GF.Random())


def random_blob():
    """One blob of FIELD_ELEMENTS_PER_BLOB random canonical field elements,
    generated as a single vectorized galois call (faster than one Python
    call per element)."""
    return [int(v) for v in GF.Random(FIELD_ELEMENTS_PER_BLOB)]


def random_blobs(n: int):
    """n independent random blobs. Each call to random_blob() draws fresh
    values -- if you need the same blob replayed across multiple coding
    schemes for a fair comparison, generate it once and pass that same
    object to each scheme, rather than regenerating."""
    return [random_blob() for _ in range(n)]