"""Read the T6 zone asset directory (the contiguous [type,ptr] array) and
histogram it by asset type. Works without per-asset parsing because the
directory is written as one block before the per-asset data.

Usage: python asset_dir.py <zone> [<zone2>]   # 2 args => side-by-side diff
"""
import struct, sys

ASSET_TYPES = [
    "XMODELPIECES","PHYSPRESET","PHYSCONSTRAINTS","DESTRUCTIBLEDEF","XANIMPARTS",
    "XMODEL","MATERIAL","TECHNIQUE_SET","IMAGE","SOUND","SOUND_PATCH","CLIPMAP",
    "CLIPMAP_PVS","COMWORLD","GAMEWORLD_SP","GAMEWORLD_MP","MAP_ENTS","GFXWORLD",
    "LIGHT_DEF","UI_MAP","FONT","FONTICON","MENULIST","MENU","LOCALIZE_ENTRY",
    "WEAPON","WEAPONDEF","WEAPON_VARIANT","WEAPON_FULL","ATTACHMENT","ATTACHMENT_UNIQUE",
    "WEAPON_CAMO","SNDDRIVER_GLOBALS","FX","IMPACT_FX","AITYPE","MPTYPE","MPBODY",
    "MPHEAD","CHARACTER","XMODELALIAS","RAWFILE","STRINGTABLE","LEADERBOARD","XGLOBALS",
    "DDL","GLASSES","EMBLEMSET","SCRIPTPARSETREE","KEYVALUEPAIRS","VEHICLEDEF",
    "MEMORYBLOCK","ADDON_MAP_ENTS","TRACER","SKINNEDVERTS","QDB","SLUG","FOOTSTEP_TABLE",
    "FOOTSTEPFX_TABLE","ZBARRIER",
]
PTR_FOLLOW = 0xFFFFFFFF


def name(t):
    return ASSET_TYPES[t] if 0 <= t < len(ASSET_TYPES) else f"#{t}"


def read_dir(path):
    d = open(path, "rb").read()
    size_le = struct.unpack('<I', d[0:4])[0]
    e = '<' if abs(size_le - len(d)) < abs(struct.unpack('>I', d[0:4])[0] - len(d)) else '>'
    u = lambda o: struct.unpack(e + 'I', d[o:o+4])[0]

    string_count = u(40)
    asset_count = u(56)
    o = 64  # past XFile(40)+XAssetList(24)
    # script string pointer array
    ptrs = [u(o + 4*i) for i in range(string_count)]
    o += 4 * string_count
    # inline strings for each FOLLOW pointer
    for p in ptrs:
        if p == PTR_FOLLOW:
            o = d.index(b'\x00', o) + 1
    # (dependCount is 0 for these zones; skip depends handling)
    # asset directory: asset_count * {u32 type, u32 ptr}
    types = [u(o + 8*i) for i in range(asset_count)]
    return e, asset_count, types


def histo(types):
    h = {}
    for t in types:
        h[t] = h.get(t, 0) + 1
    return h


def main():
    paths = sys.argv[1:] or ["../common_mp.zone"]
    results = [(p, *read_dir(p)) for p in paths]
    for p, e, n, types in results:
        print(f"{p}: endian={'LE' if e=='<' else 'BE'} assetCount={n}")
    all_types = sorted({t for _, _, _, types in results for t in set(types)})
    hs = [histo(types) for _, _, _, types in results]
    hdr = "  ".join(f"{p.split('/')[-1][:14]:>14}" for p, *_ in results)
    print(f"\n{'type':<22} {hdr}")
    for t in all_types:
        cells = "  ".join(f"{h.get(t,0):>14}" for h in hs)
        flag = ""
        if len(hs) == 2 and hs[0].get(t,0) != hs[1].get(t,0):
            flag = "  <-- differs"
        print(f"{name(t):<22} {cells}{flag}")


if __name__ == "__main__":
    main()
