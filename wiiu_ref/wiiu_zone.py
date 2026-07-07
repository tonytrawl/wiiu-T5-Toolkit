#!/usr/bin/env python3
"""
Native big-endian Wii U (T6, v148) zone reader. Purpose-built, not bound to OAT's
PC struct assumptions. Reads the decompressed zone stream directly.

Stream model (all big-endian, 32-bit):
  header:  u32 size, u32 externalSize, u32 blockSize[8]
  content: the serialized asset graph. Pointer fields are markers:
             0xFFFFFFFF = FOLLOW (data written inline, next in stream order)
             0xFFFFFFFE = INSERT
             0x00000000 = null
             else       = offset-encoded alias to already-written data
  Dynamic data follows its owning struct in member order (DFS), which is how we
  advance the cursor.

Milestone 1: header + string table + full XAsset type list (all 889 for raid),
with the console(v148)->PC asset-enum remap so every id resolves to a real type.
"""
import struct, sys

FOLLOW = 0xFFFFFFFF
INSERT = 0xFFFFFFFE

# PC (v147) T6 asset enum — OAT order.
PC_ASSET_TYPES = [
    "XMODELPIECES", "PHYSPRESET", "PHYSCONSTRAINTS", "DESTRUCTIBLEDEF", "XANIMPARTS",
    "XMODEL", "MATERIAL", "TECHNIQUE_SET", "IMAGE", "SOUND", "SOUND_PATCH", "CLIPMAP",
    "CLIPMAP_PVS", "COMWORLD", "GAMEWORLD_SP", "GAMEWORLD_MP", "MAP_ENTS", "GFXWORLD",
    "LIGHT_DEF", "UI_MAP", "FONT", "FONTICON", "MENULIST", "MENU", "LOCALIZE_ENTRY",
    "WEAPON", "WEAPONDEF", "WEAPON_VARIANT", "WEAPON_FULL", "ATTACHMENT",
    "ATTACHMENT_UNIQUE", "WEAPON_CAMO", "SNDDRIVER_GLOBALS", "FX", "IMPACT_FX",
    "AITYPE", "MPTYPE", "MPBODY", "MPHEAD", "CHARACTER", "XMODELALIAS", "RAWFILE",
    "STRINGTABLE", "LEADERBOARD", "XGLOBALS", "DDL", "GLASSES", "EMBLEMSET",
    "SCRIPTPARSETREE", "KEYVALUEPAIRS", "VEHICLEDEF", "MEMORYBLOCK", "ADDON_MAP_ENTS",
    "TRACER", "SKINNEDVERTS", "QDB", "SLUG", "FOOTSTEP_TABLE", "FOOTSTEPFX_TABLE",
    "ZBARRIER",
]


def console_to_pc(t):
    """Console (Xbox360 v146 / WiiU v148) asset id -> PC id. Mirrors OAT's read remap:
    two console-only types inserted at ids 7 and 44; MAP_ENTS relocated to 47."""
    if t == 47:
        return 16            # MAP_ENTS
    if t == 7 or t == 44:
        return None          # console-only, no PC equivalent
    if t > 44:
        return t - 2
    if t > 6:
        return t - 1
    return t


class ZoneReader:
    def __init__(self, zone: bytes):
        self.d = zone
        self.n = len(zone)
        (self.size, self.external_size) = struct.unpack('>II', zone[0:8])
        self.block_sizes = list(struct.unpack('>8I', zone[8:40]))
        self.cur = 40  # content starts after header
        self.strings = []
        self.assets = []  # list of (console_id, pc_id, pc_name)

    def u32(self, o): return struct.unpack('>I', self.d[o:o+4])[0]

    def read_string_table(self):
        """XAssetList: stringCount, strings*, dependCount, depends*, assetCount, assets*."""
        o = self.cur
        self.string_count, strings_p, self.depend_count, depends_p, \
            self.asset_count, assets_p = struct.unpack('>6I', self.d[o:o+24])
        o += 24
        # strings pointer array: stringCount entries (FOLLOW or null)
        ptrs = struct.unpack('>%dI' % self.string_count, self.d[o:o + self.string_count*4])
        o += self.string_count * 4
        # inline string bytes for each FOLLOW pointer, in order
        self.strings = [""]  # index 0 conventionally empty
        for p in ptrs:
            if p == FOLLOW:
                end = self.d.index(b'\x00', o)
                self.strings.append(self.d[o:end].decode('latin-1'))
                o = end + 1
            # null pointers contribute no inline data
        # depends (dependCount) — none in raid; skip if present
        # The asset array immediately follows the inline strings — it is NOT 4-aligned.
        # (mp_raid happened to land aligned; common_mp starts at an unaligned offset.)
        self.assets_off = o
        return o

    def read_asset_list(self):
        """Asset array: assetCount * XAsset{ u32 type; u32 headerPtr } = 8 bytes each."""
        o = self.assets_off
        for i in range(self.asset_count):
            ctype = self.u32(o + i*8)
            pc = console_to_pc(ctype)
            name = PC_ASSET_TYPES[pc] if (pc is not None and 0 <= pc < len(PC_ASSET_TYPES)) else None
            self.assets.append((ctype, pc, name))
        self.assets_end = o + self.asset_count * 8
        return self.assets


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'mp_raid_genuine.zone'
    z = ZoneReader(open(path, 'rb').read())
    print("zone size=0x%x externalSize=0x%x" % (z.size, z.external_size))
    print("blocks:", [hex(b) for b in z.block_sizes])
    z.read_string_table()
    print("stringCount=%d  (parsed %d strings)  dependCount=%d  assetCount=%d" %
          (z.string_count, len(z.strings)-1, z.depend_count, z.asset_count))
    print("sample strings:", [s for s in z.strings[1:9]])
    z.read_asset_list()
    # validate: every console id must remap to a real type
    from collections import Counter
    bad = [(i, c) for i, (c, pc, nm) in enumerate(z.assets) if nm is None]
    dist = Counter(nm for _, _, nm in z.assets)
    print("\nasset-type histogram (%d assets, %d distinct):" % (len(z.assets), len(dist)))
    for nm, cnt in dist.most_common():
        print("  %5d  %s" % (cnt, nm))
    print("\nunresolved/console-only ids: %d" % len(bad))
    if bad:
        print("  first few:", bad[:10])
    print("\nfirst 12 assets (console_id -> pc_name):")
    for i, (c, pc, nm) in enumerate(z.assets[:12]):
        print("  [%d] console=%d -> %s" % (i, c, nm))


if __name__ == '__main__':
    main()
