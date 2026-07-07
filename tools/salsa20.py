"""Pure-Python Salsa20/20 stream cipher (no dependencies).

Reference: D. J. Bernstein's Salsa20 spec. This implements the standard
512-bit state, 20-round variant with a 256-bit key and 64-bit nonce.
"""
import struct

_SIGMA = b"expand 32-byte k"  # 256-bit key constant


def _rotl(v, c):
    return ((v << c) | (v >> (32 - c))) & 0xFFFFFFFF


def _quarterround(x, a, b, c, d):
    x[b] ^= _rotl((x[a] + x[d]) & 0xFFFFFFFF, 7)
    x[c] ^= _rotl((x[b] + x[a]) & 0xFFFFFFFF, 9)
    x[d] ^= _rotl((x[c] + x[b]) & 0xFFFFFFFF, 13)
    x[a] ^= _rotl((x[d] + x[c]) & 0xFFFFFFFF, 18)


def _core(state):
    x = list(state)
    for _ in range(10):  # 20 rounds = 10 double-rounds
        # column round
        _quarterround(x, 0, 4, 8, 12)
        _quarterround(x, 5, 9, 13, 1)
        _quarterround(x, 10, 14, 2, 6)
        _quarterround(x, 15, 3, 7, 11)
        # row round
        _quarterround(x, 0, 1, 2, 3)
        _quarterround(x, 5, 6, 7, 4)
        _quarterround(x, 10, 11, 8, 9)
        _quarterround(x, 15, 12, 13, 14)
    return [(x[i] + state[i]) & 0xFFFFFFFF for i in range(16)]


class Salsa20:
    def __init__(self, key: bytes, nonce: bytes, counter: int = 0):
        assert len(key) == 32, "key must be 32 bytes"
        assert len(nonce) == 8, "nonce must be 8 bytes"
        k = struct.unpack('<8I', key)
        c = struct.unpack('<4I', _SIGMA)
        n = struct.unpack('<2I', nonce)
        # state layout (Salsa20 standard)
        self._base = [
            c[0], k[0], k[1], k[2],
            k[3], c[1], n[0], n[1],
            counter & 0xFFFFFFFF, (counter >> 32) & 0xFFFFFFFF, c[2], k[4],
            k[5], k[6], k[7], c[3],
        ]
        self._counter = counter
        self._keystream = b""

    def _block(self, counter):
        st = list(self._base)
        st[8] = counter & 0xFFFFFFFF
        st[9] = (counter >> 32) & 0xFFFFFFFF
        return struct.pack('<16I', *_core(st))

    def keystream(self, length):
        out = bytearray()
        ctr = self._counter
        while len(out) < length:
            out += self._block(ctr)
            ctr += 1
        return bytes(out[:length])

    def decrypt(self, data: bytes) -> bytes:
        ks = self.keystream(len(data))
        return bytes(a ^ b for a, b in zip(data, ks))

    encrypt = decrypt


if __name__ == "__main__":
    # Bernstein test vector: key=0, nonce=0, first 64 keystream bytes known.
    s = Salsa20(b"\x00" * 32, b"\x00" * 8)
    ks = s.keystream(64)
    print(ks[:8].hex())  # expect 9a97f65b9b4c721e ... (set1 vector start)
