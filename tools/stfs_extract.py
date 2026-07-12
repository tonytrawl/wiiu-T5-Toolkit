"""Minimal Python 3 STFS (Xbox 360 CON/LIVE/PIRS) extractor.

Reproduces the block-traversal logic from arkem/py360 (which was Python 2),
rewritten for Py3 bytes semantics. Extracts every file in the container to an
output directory, preserving paths.
"""
import struct, os, sys

BLOCK = 0x1000


class STFS:
    def __init__(self, path):
        self.fd = open(path, "rb")
        magic = self.fd.read(4)
        assert magic in (b"CON ", b"PIRS", b"LIVE"), f"not STFS: {magic!r}"
        self.fd.seek(0)
        self.data = self.fd.read(0x971A)
        self._parse_header(self.data)
        self._parse_filetable()

    def _u(self, fmt, off, n):
        return struct.unpack(fmt, self.data[off:off+n])[0]

    def _parse_header(self, d):
        self.entry_id = self._u(">I", 0x340, 4)
        # filetable location (little-endian 16/24-bit fields)
        self.filetable_blockcount = struct.unpack("<H", d[0x37C:0x37E])[0]
        self.filetable_blocknumber = struct.unpack("<I", d[0x37E:0x381] + b"\x00")[0]
        self.allocated_count = self._u(">I", 0x395, 4)
        # hash tables 1 or 2 blocks each
        self.table_size_shift = 0 if (((self.entry_id + 0xFFF) & 0xF000) >> 0xC) == 0xB else 1
        self.table_spacing = [(0xAB, 0x718F, 0xFE7DA), (0xAC, 0x723A, 0xFD00B)]

    # --- block I/O ---
    def read_block(self, blocknum, length=BLOCK):
        self.fd.seek(0xC000 + blocknum * BLOCK)
        return self.fd.read(length)

    def fix_blocknum(self, b):
        adj = 0
        if b >= 0xAA:
            adj += ((b // 0xAA) + 1) << self.table_size_shift
        if b >= 0x70E4:
            adj += ((b // 0x70E4) + 1) << self.table_size_shift
        return adj + b

    def get_blockhash(self, blocknum, table_offset=0):
        record = blocknum % 0xAA
        tablenum = (blocknum // 0xAA) * self.table_spacing[self.table_size_shift][0]
        if blocknum >= 0xAA:
            tablenum += (blocknum // 0x70E4 + 1) << self.table_size_shift
            if blocknum >= 0x70E4:
                tablenum += 1 << self.table_size_shift
        tablenum += table_offset - (1 << self.table_size_shift)
        hd = self.read_block(tablenum)
        rec = hd[record * 0x18: record * 0x18 + 0x18]
        info = rec[0x14]
        nextblock = struct.unpack(">I", b"\x00" + rec[0x15:0x18])[0]
        return info, nextblock

    def _read_chain(self, firstblock, size):
        out = bytearray()
        block, info = firstblock, 0x80
        while size > 0 and 0 < block < self.allocated_count and info >= 0x80:
            rl = min(BLOCK, size)
            out += self.read_block(self.fix_blocknum(block), rl)
            size -= rl
            info, nxt = self.get_blockhash(block)
            if self.table_size_shift > 0 and info < 0x80:
                info, nxt = self.get_blockhash(block, 1)
            block = nxt
        return bytes(out)

    def _read_blockcount(self, firstblock, numblocks):
        """Read an exact number of blocks following the hash chain (used for the
        filetable, whose first block can legitimately be block 0)."""
        out = bytearray()
        block = firstblock
        for _ in range(numblocks):
            out += self.read_block(self.fix_blocknum(block))
            info, nxt = self.get_blockhash(block)
            if self.table_size_shift > 0 and info < 0x80:
                info, nxt = self.get_blockhash(block, 1)
            block = nxt
        return bytes(out)

    def _parse_filetable(self):
        data = self._read_blockcount(self.filetable_blocknumber,
                                     self.filetable_blockcount)
        self.listings = []
        for x in range(0, len(data), 0x40):
            rec = data[x:x+0x40]
            name = rec[:0x28].rstrip(b"\x00")
            if not name:
                continue
            self.listings.append({
                "name": name.decode("latin1"),
                "isdir": (rec[0x28] & 0x80) == 0x80,
                "firstblock": struct.unpack("<I", rec[0x2F:0x32] + b"\x00")[0],
                "pathindex": struct.unpack(">h", rec[0x32:0x34])[0],
                "size": struct.unpack(">I", rec[0x34:0x38])[0],
            })

    def fullpath(self, fl):
        parts = [fl["name"]]
        a = fl
        while a["pathindex"] != -1 and a["pathindex"] < len(self.listings):
            a = self.listings[a["pathindex"]]
            parts.append(a["name"])
        return "/".join(reversed(parts))

    def extract_all(self, out_dir):
        for fl in self.listings:
            path = self.fullpath(fl)
            dst = os.path.join(out_dir, path)
            if fl["isdir"]:
                os.makedirs(dst, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            data = self._read_chain(fl["firstblock"], fl["size"])
            with open(dst, "wb") as f:
                f.write(data)
            print(f"  {fl['size']:>10}  {path}")


if __name__ == "__main__":
    stfs = STFS(sys.argv[1])
    print(f"STFS files: {sum(1 for l in stfs.listings if not l['isdir'])}")
    if len(sys.argv) > 2:
        stfs.extract_all(sys.argv[2])
    else:
        for fl in stfs.listings:
            print(("[D] " if fl["isdir"] else "    ") + stfs.fullpath(fl),
                  "" if fl["isdir"] else fl["size"])
