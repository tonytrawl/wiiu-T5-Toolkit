"""
rpl_ownership_patch.py -- neutralize the Black Ops II Wii U START-path DLC
ownership check so DLC maps are STARTABLE (Start Match not greyed).

WHY (evidence, this session's Cemu log + static RE)
  The frontend map-select "can we start this map" query is the LUI Lua binding
  DoesPartyHaveDLCForMap. It computes:
        mapBits  = Live_GetMapSource(mapIndex)          # per-map DLC source bits
        ownMask  = Live_CurrentFullPartyMapPackFlags()  # packs we/party own+enabled
        return (ownMask & mapBits) != 0
  ownMask is built from Content_GetEnabledContentPacks AND'd across party members.
  On Cemu, nn_aoc.AOC_Initialize is a stubbed ("Unsupported lib call") import, so
  the AOC subsystem never enumerates owned DLC -> ownMask has no DLC bits -> the
  AND is 0 -> DoesPartyHaveDLCForMap returns false -> Start is greyed. This is the
  START-path ownership gate (distinct from the LISTING gate
  Content_PlayerHasDLCForMapPackIndex, already patched by rpl_dlcgate_patch.py).

WHAT WE PATCH  (index-agnostic: force the OWNED MASK full, not a per-index return)
  Live_CurrentFullPartyMapPackFlags__FP11PartyData_s @ entry:
        li  r3, -1     ; 0x3860FFFF  -> ownMask = 0xFFFFFFFF (owns every pack)
        blr            ; 0x4E800020
  Every map's source bits then AND non-zero -> DoesPartyHaveDLCForMap true for ALL
  map-pack indices, both the in-party/public branch and the solo/local branch
  (both branches funnel through this one function). Returning before the prologue
  is safe (no frame allocated, r1/LR untouched).

  Located BY SYMBOL (VAs differ per build) via rpl_sigpatch's section machinery.

CAVEAT: unlocks only DLC map rows that EXIST in the baked mp/zm mapsTable.csv.
  The Wii U build's mapsTable has DLC0+DLC1 rows only; DLC2/3/4 rows must be ADDED
  (the patch_mp/patch_zm relink job) before those maps SHOW. This patch makes the
  visible/owned content STARTABLE.

Usage:
  python rpl_ownership_patch.py <in.rpl> <out.rpl>
Requires capstone.
"""
import binascii
import struct
import sys
import zlib

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import rpl_sigpatch as R
import rpl_symbolize as S

try:
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
except ImportError:
    sys.exit("needs capstone: pip install capstone (use the Py that has it)")

FN = "Live_CurrentFullPartyMapPackFlags__FP11PartyData_s"
LI_R3_M1 = 0x3860FFFF   # li r3,-1  -> r3 = 0xFFFFFFFF
BLR = 0x4E800020


def _text_index(secs, N):
    return next(i for i in range(N) if secs[i][3] == 0x02000000 and secs[i][1] == 1)


def patch_rpl(in_path, out_path, fn=FN, word0=LI_R3_M1, word1=BLR):
    d = bytearray(open(in_path, "rb").read())
    shoff, N, secs = R._sections(d)

    va = next((v for v, sz, nm in S.load_syms(in_path) if nm == fn), None)
    if va is None:
        raise RuntimeError("%s: no %s symbol" % (in_path, fn))

    TEXT = _text_index(secs, N)
    t = secs[TEXT]
    taddr, toff, tsz = t[3], t[4], t[5]
    dec = bytearray(zlib.decompress(bytes(d[toff:toff + tsz])[4:]))

    po = va - taddr
    orig = dec[po:po + 8]
    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    orig_disasm = "; ".join("%s %s" % (i.mnemonic, i.op_str)
                            for i in md.disasm(bytes(orig), va))
    struct.pack_into(">II", dec, po, word0, word1)

    newdec = bytes(dec)
    newcrc = binascii.crc32(newdec) & 0xffffffff
    newstored = struct.pack(">I", len(newdec)) + zlib.compress(newdec, 9)

    crci = next(i for i in range(N) if secs[i][1] == 0x80000003)  # SHT_RPL_CRCS
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
        struct.pack_into(">I", out, shoff + i * 40 + 16, no)      # sh_offset
        if i == TEXT:
            struct.pack_into(">I", out, shoff + i * 40 + 20, len(data))  # sh_size
    open(out_path, "wb").write(out)

    # verify from the written file
    p = open(out_path, "rb").read()
    ps = [list(struct.unpack(">IIIIIIIIII", p[shoff + i * 40:shoff + i * 40 + 40]))
          for i in range(N)]
    pdec = zlib.decompress(p[ps[TEXT][4]:ps[TEXT][4] + ps[TEXT][5]][4:])
    got = list(md.disasm(pdec[po:po + 8], va))
    patched = "; ".join("%s %s" % (i.mnemonic, i.op_str) for i in got)
    ok = (len(got) == 2 and got[0].mnemonic == "li" and got[1].mnemonic == "blr")
    return dict(func_va=va, orig=orig_disasm, patched=patched, ok=ok,
                in_size=len(d), out_size=len(out))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: rpl_ownership_patch.py <in.rpl> <out.rpl>")
    r = patch_rpl(sys.argv[1], sys.argv[2])
    print("%s @ %#x" % (FN, r["func_va"]))
    print("  orig:    %s" % r["orig"])
    print("  patched: %s   verify_ok=%s" % (r["patched"], r["ok"]))
    print("  %d -> %d bytes  (wrote %s)" % (r["in_size"], r["out_size"], sys.argv[2]))
