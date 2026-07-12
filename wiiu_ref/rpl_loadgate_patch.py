"""
rpl_loadgate_patch.py -- make DB_LoadLoadFastfilesForNewContent request EVERY
content pack's `dlc<N>_load_<mp|zm>.ff`, WITHOUT marking packs "owned" for the
rest of the engine (so the ZM globe selector does not crash).

WHY (hw-RE 2026-07-09):
  Forcing __Content_DoWeHaveIndexedContentPack -> 1 loaded dlc1 but CRASHED the ZM
  globe: the globe's Content_GetEnabledContentPacks() calls DoWeHave per index and
  renders each "owned" pack; dlc1 owned -> globe renders a map-pack with no
  hardware map row -> fault. Content_IsIndexedContentPackEnabled (thunk to DoWeHave)
  has only TWO callers, both in the DB load-fastfile path:
    DB_AnyContentLoadFastfilesPending, DB_LoadLoadFastfilesForNewContent.
  So we patch the CALL SITE inside DB_LoadLoadFastfilesForNewContent:
    replace  `bl Content_IsIndexedContentPackEnabled`  with  `li r3, 1`
  -> the per-pack load loop treats every pack as enabled and calls DB_LoadXAssets
  for "<id>_load<suffix>". Deployed packs (dlc0, dlc1) load; undeployed ones
  (dlc2-5, seasonpass) miss and are tolerated (like en_*_load_loc -> -6). The globe
  path (DoWeHave, unpatched) still sees only the truly-owned dlc0 -> no crash.
  Die Rise's row already shows via the map-gate patch; loading dlc1_load_zm defines
  its menu material so the tile renders instead of a checkerboard.

  DB_LoadLoadFastfilesForNewContent runs every frame from Com_Frame; its own
  IsLoadFastfileLoaded check makes each pack load exactly once.

Call site (update build t6mp_cafef_rpl): VA 0x223bfe0, `bl 0x2433f64`.
Located structurally: the single `bl Content_IsIndexedContentPackEnabled` inside
DB_LoadLoadFastfilesForNewContent (so it survives VA drift across builds).

Usage:
  python rpl_loadgate_patch.py <in.rpl> <out.rpl>
"""
import binascii, struct, sys, zlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpl_sigpatch as R
import rpl_symbolize as S
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN

CALLER = "DB_LoadLoadFastfilesForNewContent__Fv"
CALLEE = "Content_IsIndexedContentPackEnabled__Fi"
LI_R3_1 = 0x38600001


def _bl_target(w, va):
    if (w & 0xFC000003) != 0x48000001:
        return None
    off = w & 0x03FFFFFC
    if off & 0x02000000:
        off -= 0x04000000
    return va + off


def patch_rpl(in_path, out_path):
    d = bytearray(open(in_path, "rb").read())
    shoff, N, secs = R._sections(d)
    syms = S.load_syms(in_path)
    bysym = {nm: (v, sz) for v, sz, nm in syms}
    cva, csz = bysym[CALLER]
    tgt = bysym[CALLEE][0]

    TEXT = next(i for i in range(N) if secs[i][3] == 0x02000000 and secs[i][1] == 1)
    t = secs[TEXT]
    taddr, toff, tsz = t[3], t[4], t[5]
    dec = bytearray(zlib.decompress(bytes(d[toff:toff + tsz])[4:]))

    # locate the single `bl Content_IsIndexedContentPackEnabled` inside the caller
    sites = []
    for off in range(cva - taddr, cva - taddr + csz, 4):
        w = struct.unpack_from(">I", dec, off)[0]
        if _bl_target(w, taddr + off) == tgt:
            sites.append(off)
    if len(sites) != 1:
        raise RuntimeError("expected 1 call site, found %d (%s)"
                           % (len(sites), [hex(taddr + s) for s in sites]))
    po = sites[0]
    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    orig = bytes(dec[po:po + 4])
    orig_disasm = "; ".join("%s %s" % (i.mnemonic, i.op_str)
                            for i in md.disasm(orig, taddr + po))
    struct.pack_into(">I", dec, po, LI_R3_1)

    newdec = bytes(dec)
    newcrc = binascii.crc32(newdec) & 0xffffffff
    newstored = struct.pack(">I", len(newdec)) + zlib.compress(newdec, 9)
    crci = next(i for i in range(N) if secs[i][1] == 0x80000003)
    prefix = bytearray(d[:toff])
    struct.pack_into(">I", prefix, secs[crci][4] + TEXT * 4, newcrc)
    out = bytearray(prefix)
    for i in sorted((i for i in range(N) if secs[i][4] >= toff and secs[i][5] > 0),
                    key=lambda i: secs[i][4]):
        while len(out) % 0x40:
            out.append(0)
        no = len(out)
        data = newstored if i == TEXT else bytes(d[secs[i][4]:secs[i][4] + secs[i][5]])
        out += data
        struct.pack_into(">I", out, shoff + i * 40 + 16, no)
        if i == TEXT:
            struct.pack_into(">I", out, shoff + i * 40 + 20, len(data))
    open(out_path, "wb").write(out)

    p = open(out_path, "rb").read()
    ps = [list(struct.unpack(">IIIIIIIIII", p[shoff + i * 40:shoff + i * 40 + 40]))
          for i in range(N)]
    pdec = zlib.decompress(p[ps[TEXT][4]:ps[TEXT][4] + ps[TEXT][5]][4:])
    got = "; ".join("%s %s" % (i.mnemonic, i.op_str)
                    for i in md.disasm(pdec[po:po + 4], taddr + po))
    return dict(site_va=taddr + po, orig=orig_disasm, patched=got,
                in_size=len(d), out_size=len(out))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: rpl_loadgate_patch.py <in.rpl> <out.rpl>")
    r = patch_rpl(sys.argv[1], sys.argv[2])
    print("call site @ %#x" % r["site_va"])
    print("  orig:    %s" % r["orig"])
    print("  patched: %s" % r["patched"])
    print("  %d -> %d bytes  (wrote %s)" % (r["in_size"], r["out_size"], sys.argv[2]))
