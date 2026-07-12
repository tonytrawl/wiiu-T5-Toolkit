"""Pack a decompressed T6 zone back into a Wii U (v148, big-endian) fastfile.

Inverse of ff_decrypt.py: deflate the zone into <=0x8000 chunks across 4
interleaved streams, Salsa20-encrypt each with the per-stream hash-chain IV,
and frame them with the 0x80000 super-block size-field alignment rule.

NOTE: the 256-byte RSA signature cannot be produced (Treyarch private key).
We emit zeros there; whether the target accepts it depends on the loader
(unsigned-FF path or signature-check bypass).
"""
import struct, zlib, sys, os
from salsa20 import Salsa20
from ff_decrypt import (KEY_WIIU, HashChain, STREAM_COUNT, XCHUNK_SIZE,
                        VANILLA_BUFSIZE, HEADER_DATA_START)

UNCOMPRESSED_BLOCK = 0x8000   # zone bytes per chunk — MUST match the console's per-chunk
                              # decompression buffer (XCHUNK_SIZE). Treyarch uses 0x8000;
                              # larger blocks overflow the fixed buffer and freeze the game.
FILE_SUFFIX_ALIGN = 0x40      # final file is zero-padded to this boundary (Treyarch does this)
FILE_SUFFIX_MIN   = 0x40


def deflate_chunks(zone):
    """Split zone into raw-deflate chunks, each <= XCHUNK_SIZE compressed."""
    chunks = []
    pos = 0
    block = UNCOMPRESSED_BLOCK
    while pos < len(zone):
        while True:
            raw = zone[pos:pos + block]
            c = zlib.compressobj(9, zlib.DEFLATED, -15)
            comp = c.compress(raw) + c.flush()
            if len(comp) <= XCHUNK_SIZE:
                break
            block -= 0x1000  # shrink until it fits
        chunks.append(comp)
        pos += len(raw)
        block = UNCOMPRESSED_BLOCK
    return chunks


def build_header(name, version=148, endian='>'):
    h = bytearray(HEADER_DATA_START)
    h[0:8] = b'TAff0100'
    struct.pack_into(endian + 'I', h, 8, version)
    h[12:20] = b'PHEEBs71'
    struct.pack_into(endian + 'I', h, 20, 0)
    nb = name.encode('latin1')[:31]
    h[24:24 + len(nb)] = nb
    # h[56:312] signature left as zeros
    return bytes(h)


def pack_ff(zone, name, key=KEY_WIIU, endian='>'):
    chain = HashChain(name)
    out = bytearray(build_header(name, endian=endian))
    vbuf_off = HEADER_DATA_START % VANILLA_BUFSIZE
    for i, comp in enumerate(deflate_chunks(zone)):
        # size field must not straddle a 0x80000 super-block boundary
        if vbuf_off + 4 > VANILLA_BUFSIZE:
            pad = VANILLA_BUFSIZE - vbuf_off
            out += b'\x00' * pad
            vbuf_off = 0
        stream = i % STREAM_COUNT
        iv = chain.iv(stream)
        enc = Salsa20(key, iv).encrypt(comp)
        chain.advance(stream, comp)
        out += struct.pack(endian + 'I', len(comp)) + enc
        vbuf_off = (vbuf_off + 4 + len(comp)) % VANILLA_BUFSIZE
    # terminator size 0 (respect alignment too)
    if vbuf_off + 4 > VANILLA_BUFSIZE:
        out += b'\x00' * (VANILLA_BUFSIZE - vbuf_off)
    out += struct.pack(endian + 'I', 0)
    # trailing zero suffix: at least FILE_SUFFIX_MIN bytes, then pad to FILE_SUFFIX_ALIGN
    out += b'\x00' * FILE_SUFFIX_MIN
    out += b'\x00' * ((-len(out)) % FILE_SUFFIX_ALIGN)
    return bytes(out)


if __name__ == "__main__":
    zone_path = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(os.path.basename(zone_path))[0]
    zone = open(zone_path, "rb").read()
    ff = pack_ff(zone, name)
    out = os.path.splitext(zone_path)[0] + "_repacked.ff"
    open(out, "wb").write(ff)
    print(f"packed {len(zone)} byte zone -> {len(ff)} byte ff ({out})  name={name!r}")
