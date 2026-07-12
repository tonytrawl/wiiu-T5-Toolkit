"""Experimentation harness: find the Wii U BO2 fastfile block/IV scheme.

Strategy: T6 signed fastfiles store the zone as a stream of size-prefixed
blocks; each block is Salsa20-encrypted then zlib-compressed. The Salsa20
nonce is chained (next IV derived from a hash of the current block). We don't
know the exact layout, so we try several hypotheses and let a *successful
zlib inflate* tell us which one is correct.
"""
import struct, zlib, hashlib, sys
from salsa20 import Salsa20

KEY = bytes([
    0xB3, 0xBD, 0x6B, 0x2C, 0x82, 0x42, 0x8D, 0x11,
    0xB8, 0x88, 0x2D, 0x4C, 0x6D, 0x18, 0xCC, 0x79,
    0xE2, 0x70, 0x9F, 0x6B, 0xD4, 0x39, 0x91, 0x35,
    0xFD, 0xDE, 0x14, 0xE6, 0x8F, 0x3A, 0xBC, 0xCE,
])

data = open("../common_mp.ff", "rb").read()
print(f"file size: {len(data)}  magic={data[:8]}  ver={struct.unpack('>I',data[8:12])[0]}")


def try_inflate(buf):
    """Return inflated bytes if buf is a valid zlib/raw-deflate stream, else None."""
    for wbits in (15, -15, 47):
        try:
            d = zlib.decompressobj(wbits)
            out = d.decompress(buf)
            out += d.flush()
            if len(out) > 0:
                return out
        except Exception:
            pass
    return None


def test(start, iv0, label):
    """Treat bytes from `start` as a stream of [u32 BE size][encrypted block].
    Decrypt each block with chained IV, attempt inflate."""
    iv = iv0
    off = start
    blocks = []
    for i in range(4):
        if off + 4 > len(data):
            break
        size = struct.unpack('>I', data[off:off+4])[0]
        if size == 0 or size > 0x900000 or off + 4 + size > len(data):
            return False
        enc = data[off+4:off+4+size]
        s = Salsa20(KEY, iv)
        dec = s.decrypt(enc)
        inf = try_inflate(dec)
        ok = inf is not None
        blocks.append((size, ok, dec[:4].hex(), len(inf) if inf else 0))
        if not ok:
            # show what we got for the first block to aid debugging
            if i == 0:
                print(f"  [{label}] start=0x{start:x} size={size} iv={iv.hex()} "
                      f"dec[:8]={dec[:8].hex()}  NO inflate")
            return False
        iv = hashlib.sha1(enc).digest()[:8]  # chain hypothesis
        off += 4 + size
    print(f"  [{label}] *** START 0x{start:x} iv0={iv0.hex()} -> {blocks}")
    return True


# Candidate IV0 values pulled from the header region.
iv_130 = data[0x130:0x138]
iv_13c = data[0x13c:0x144]
zeros  = b"\x00" * 8

print("\n-- size-prefixed block stream hypotheses --")
for start in (0x130, 0x134, 0x138, 0x14c, 0x150, 0x154):
    for iv0, name in ((iv_130, "iv@130"), (iv_13c, "iv@13c"), (zeros, "zeros")):
        test(start, iv0, name)

# Also: maybe whole payload is one Salsa20 stream (no per-block size prefix).
print("\n-- single-stream hypotheses --")
for start in (0x130, 0x138, 0x150, 0x154):
    for iv0, name in ((iv_130, "iv@130"), (iv_13c, "iv@13c"), (zeros, "zeros")):
        s = Salsa20(KEY, iv0)
        dec = s.decrypt(data[start:start+0x4000])
        print(f"  single start=0x{start:x} {name}: dec[:16]={dec[:16].hex()}")
