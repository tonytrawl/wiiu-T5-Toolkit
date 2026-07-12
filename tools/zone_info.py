"""Inspect a decompressed T6 zone's leading structure (big-endian console build).

Parses the version-stable XFile header and the XAssetList, then walks the
script-string table. This is the region where v146 (PS3/360) and v148 (Wii U)
zones diverge, so dumping it from each build reveals the structural delta.

Zone layout (BE):
  u32 size
  u32 externalSize
  u32 blockSize[8]          # TEMP,RT_V,RT_P,DELAY_V,DELAY_P,VIRTUAL,PHYSICAL,STREAMER
  --- XAssetList (in VIRTUAL block) ---
  u32 stringCount
  ptr strings               # 0xFFFFFFFF = follows inline
  u32 dependCount
  ptr depends
  u32 assetCount
  ptr assets
  --- then inline: stringCount pointers (each 0xFFFFFFFF), then the strings ---
"""
import struct, sys

BLOCK_NAMES = ["TEMP", "RUNTIME_VIRTUAL", "RUNTIME_PHYSICAL", "DELAY_VIRTUAL",
               "DELAY_PHYSICAL", "VIRTUAL", "PHYSICAL", "STREAMER_RESERVE"]
PTR_FOLLOWING = 0xFFFFFFFF


ENDIAN = '>'


def u32(d, o):
    return struct.unpack(ENDIAN + 'I', d[o:o+4])[0]


def inspect(path):
    global ENDIAN
    d = open(path, "rb").read()
    # Heuristic: TEMP block sits at offset 8; pick endianness that makes the
    # zone 'size' field at offset 0 roughly match the file length.
    size_be = struct.unpack('>I', d[0:4])[0]
    size_le = struct.unpack('<I', d[0:4])[0]
    ENDIAN = '<' if abs(size_le - len(d)) < abs(size_be - len(d)) else '>'
    print(f"=== {path}  ({len(d)} bytes, endian={'LE' if ENDIAN=='<' else 'BE'}) ===")
    size, ext = u32(d, 0), u32(d, 4)
    print(f"size={size:#x} ({size})  externalSize={ext:#x}")
    blocks = [u32(d, 8 + 4*i) for i in range(8)]
    for n, b in zip(BLOCK_NAMES, blocks):
        print(f"  block {n:<16} = {b:#x} ({b})")

    o = 40  # XAssetList
    string_count = u32(d, o)
    strings_ptr  = u32(d, o+4)
    depend_count = u32(d, o+8)
    depends_ptr  = u32(d, o+12)
    asset_count  = u32(d, o+16)
    assets_ptr   = u32(d, o+20)
    print(f"\nXAssetList @ {o:#x}:")
    print(f"  stringCount = {string_count}   strings_ptr   = {strings_ptr:#010x}")
    print(f"  dependCount = {depend_count}   depends_ptr   = {depends_ptr:#010x}")
    print(f"  assetCount  = {asset_count}    assets_ptr    = {assets_ptr:#010x}")

    # Script strings: array of `stringCount` pointers, then inline null-term strings.
    o += 24
    if strings_ptr == PTR_FOLLOWING and 0 < string_count < 200000:
        ptrs = [u32(d, o + 4*i) for i in range(string_count)]
        o += 4 * string_count
        # First entry is conventionally an empty/placeholder string.
        strings = []
        for i in range(string_count):
            if ptrs[i] == PTR_FOLLOWING:
                end = d.index(b'\x00', o)
                strings.append(d[o:end].decode('latin1', 'replace'))
                o = end + 1
            else:
                strings.append(None)  # references an earlier string (ptr != follow)
        real = [s for s in strings if s]
        print(f"\nscript strings: {string_count} entries, {len(real)} inline")
        for s in real[:40]:
            print("   ", s)
        if len(real) > 40:
            print(f"    ... (+{len(real)-40} more)")
    else:
        print("\n(script string table not inline / unexpected layout)")


if __name__ == "__main__":
    inspect(sys.argv[1] if len(sys.argv) > 1 else "../common_mp.zone")
