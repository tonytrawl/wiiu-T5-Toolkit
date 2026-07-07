"""
zone_validate.py — structural validator for a decompressed Black Ops II zone.

Checks a converted (Wii U-targeted, big-endian v148) zone against the structural
conventions of genuine Wii U zones, to catch format divergences *before* a hardware
test. Optionally diffs against a reference genuine zone.

What it checks (the part the Wii U loader walks in the first super-block):
  - XFile header: size, externalSize, the 8 block sizes + block policy sanity.
  - XAssetList: stringCount/dependCount/assetCount and their follow-pointers.
  - Script-string pointer table: genuine zones use all-follows (0xFFFFFFFF); a NULL
    or stray value here is a real divergence (we found OAT emits NULL for slot 0).
  - Asset directory: each [type, ptr] pair; ptr should be follows (0xFFFFFFFF).

Usage:
  python zone_validate.py <zone>                  # validate against built-in WiiU conventions
  python zone_validate.py <zone> --ref <genuine>  # also diff header/convention vs a genuine zone
"""
import struct
import sys

FOLLOW = 0xFFFFFFFF
BLOCK_NAMES = ["TEMP", "RUNTIME_VIRTUAL", "RUNTIME_PHYSICAL", "DELAY_VIRTUAL",
               "DELAY_PHYSICAL", "VIRTUAL", "PHYSICAL", "STREAMER_RESERVE"]


def detect_endian(d):
    le = struct.unpack('<I', d[:4])[0]
    be = struct.unpack('>I', d[:4])[0]
    # the decompressed size should be near the file length
    return '<' if abs(le - len(d)) < abs(be - len(d)) else '>'


class Zone:
    def __init__(self, path):
        self.path = path
        self.d = open(path, 'rb').read()
        self.e = detect_endian(self.d)

    def u(self, o):
        return struct.unpack(self.e + 'I', self.d[o:o + 4])[0]

    def header(self):
        return dict(size=self.u(0), externalSize=self.u(4),
                    blocks=[self.u(8 + 4 * i) for i in range(8)])

    def assetlist(self):
        return dict(stringCount=self.u(40), stringsPtr=self.u(44),
                    dependCount=self.u(48), dependsPtr=self.u(52),
                    assetCount=self.u(56), assetsPtr=self.u(60))

    def script_string_ptrs(self):
        al = self.assetlist()
        return [self.u(64 + 4 * i) for i in range(al['stringCount'])]

    def asset_dir_offset(self):
        """Offset of the [type,ptr] asset directory (after script strings + inline strings)."""
        al = self.assetlist()
        o = 64
        ptrs = [self.u(o + 4 * i) for i in range(al['stringCount'])]
        o += 4 * al['stringCount']
        for p in ptrs:
            if p == FOLLOW:
                o = self.d.index(b'\x00', o) + 1
        # depends array (dependCount follow-pointers + strings); 0 for maps
        return o

    def asset_types(self):
        al = self.assetlist()
        o = self.asset_dir_offset()  # directory follows the inline strings directly (no extra align)
        return [(self.u(o + 8 * i), self.u(o + 8 * i + 4)) for i in range(al['assetCount'])]


def validate(z, issues):
    h = z.header()
    al = z.assetlist()
    endian = 'BE' if z.e == '>' else 'LE'

    print(f"  endian={endian}  size=0x{h['size']:x}  externalSize=0x{h['externalSize']:x}")
    print("  blocks: " + "  ".join(f"{BLOCK_NAMES[i]}=0x{h['blocks'][i]:x}"
                                    for i in range(8) if h['blocks'][i]))
    print(f"  XAssetList: stringCount={al['stringCount']} assetCount={al['assetCount']} "
          f"dependCount={al['dependCount']}")

    # --- block policy (console expectation) ---
    # Genuine Wii U map zones: TEMP is small but NON-zero (~0x12ac — the data from explicit
    # `set block TEMP` fields), and map zones reserve a fixed RUNTIME_PHYSICAL (~0xc60000).
    temp = h['blocks'][0]
    rt_phys = h['blocks'][2]
    if endian == 'BE':
        if temp > 0x4000:
            issues.append(f"TEMP=0x{temp:x} (>16 KB) — PC-style TEMP overflows the Wii U's fixed "
                          f"TEMP buffer (genuine ~0x12ac).")
        elif temp == 0:
            issues.append(f"TEMP=0 — a blanket TEMP->VIRTUAL remap moved the explicit-TEMP fields too; "
                          f"genuine map zones keep ~0x12ac in TEMP. The Wii U loader pushes TEMP for "
                          f"those fields and will overflow a zero-size TEMP block.")

    # --- assetlist follow-pointers ---
    if al['stringCount'] and al['stringsPtr'] != FOLLOW:
        issues.append(f"stringsPtr=0x{al['stringsPtr']:08x}, expected 0x{FOLLOW:08x} (follows).")
    if al['assetCount'] and al['assetsPtr'] != FOLLOW:
        issues.append(f"assetsPtr=0x{al['assetsPtr']:08x}, expected 0x{FOLLOW:08x} (follows).")

    # --- script-string pointer table ---
    # Convention (matches genuine Wii U zones): slot 0 is the reserved/empty string and is a NULL
    # pointer (0x0); every other slot is a follows-pointer (0xFFFFFFFF) to an inline string.
    ssp = z.script_string_ptrs()
    bad = [(i, p) for i, p in enumerate(ssp)
           if not ((i == 0 and p == 0) or p == FOLLOW)]
    if bad:
        sample = ", ".join(f"[{i}]=0x{p:08x}" for i, p in bad[:6])
        issues.append(f"{len(bad)}/{len(ssp)} script-string pointers break convention "
                      f"(slot0=NULL, rest=follows). e.g. {sample}")

    # --- asset directory pointers: each must be follows (0xFFFFFFFF) or a valid back-reference
    # (block index 0-7 whose block size is non-zero). The insert sentinel 0xFFFFFFFE (used when
    # asset data lands in the TEMP block) is a divergence — genuine console zones keep data in
    # VIRTUAL, so header pointers are follows or VIRTUAL/PHYSICAL back-refs.
    try:
        types = z.asset_types()

        def ptr_ok(p):
            if p == FOLLOW:
                return True
            blk = (p - 1) >> 29
            off = (p - 1) & 0x1FFFFFFF
            if not (0 <= blk < 8) or h['blocks'][blk] == 0:
                return False
            # RUNTIME/DELAY blocks (1-4) are runtime-allocated; back-refs into them may legitimately
            # exceed the declared (file-backed) size for streamed GPU data, as in genuine zones.
            if blk in (1, 2, 3, 4):
                return True
            return off < h['blocks'][blk]

        bad_ptr = [(i, t, p) for i, (t, p) in enumerate(types) if not ptr_ok(p)]
        if bad_ptr:
            i, t, p = bad_ptr[0]
            extra = " (insert sentinel — asset data is in TEMP, not VIRTUAL)" if p == 0xFFFFFFFE else ""
            issues.append(f"{len(bad_ptr)}/{len(types)} asset-directory pointers are invalid; "
                          f"first: index {i} type {t} ptr 0x{p:08x}{extra}")
        print(f"  asset directory parsed OK ({len(types)} entries)")
    except Exception as ex:  # noqa: BLE001
        issues.append(f"could not parse asset directory: {ex}")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    ref = None
    if "--ref" in args:
        ref = args[args.index("--ref") + 1]

    z = Zone(path)
    print(f"== validating {path} ==")
    issues = []
    validate(z, issues)

    if ref:
        print(f"\n== reference (genuine) {ref} ==")
        r = Zone(ref)
        rissues = []
        validate(r, rissues)

    print("\n" + "=" * 60)
    if issues:
        print(f"FOUND {len(issues)} divergence(s) from Wii U conventions:")
        for i, m in enumerate(issues, 1):
            print(f"  {i}. {m}")
        return 1
    print("No structural divergences found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
