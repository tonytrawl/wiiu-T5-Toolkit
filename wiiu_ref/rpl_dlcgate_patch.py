"""
rpl_dlcgate_patch.py -- neutralize the Black Ops II DLC ownership gate in a
Wii U engine RPL so DLC map-pack rows are treated as owned (unlocked).

WHAT IT PATCHES
  Function `Content_PlayerHasDLCForMapPackIndex(dlcIndex)` returns a bool (r3):
  1 if the player owns the pack for that DLC map-pack index, else 0. The menu's
  map feeder / DLC gate (`ui_showDLCMaps`, `Content_PlayerHasDLCForMap` which
  calls into this) uses it to hide/lock un-owned DLC maps. We overwrite the
  function entry with:
        li  r3, 1     ; 0x38600001
        blr           ; 0x4E800020
  so it unconditionally returns "owned". Returning before the prologue runs is
  safe (r1/LR untouched, no frame allocated). `Content_PlayerHasDLCForMap`
  funnels through this, so both become always-true with one patch.

  The function is located BY SYMBOL (VAs differ per build: game/base vs the
  smaller update build Cemu loads), reusing rpl_sigpatch's section machinery.

CAVEAT: this only UNLOCKS DLC rows that already exist in the baked
  mp/zm mapsTable.csv. If the Wii U build's mapsTable has no DLC rows at all,
  unlocking changes nothing and the rows must be ADDED to the table instead.

Usage:
  python rpl_dlcgate_patch.py <in.rpl> <out.rpl>
Requires capstone (use the Python that has it).
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

FN = "Content_PlayerHasDLCForMapPackIndex__F10dlcIndex_t"
LI_R3_1 = 0x38600001
BLR = 0x4E800020


def _text_index(secs, N):
    return next(i for i in range(N) if secs[i][3] == 0x02000000 and secs[i][1] == 1)


def patch_rpl(in_path, out_path):
    d = bytearray(open(in_path, "rb").read())
    shoff, N, secs = R._sections(d)

    va = next((v for v, sz, nm in S.load_syms(in_path) if nm == FN), None)
    if va is None:
        raise RuntimeError("%s: no %s symbol" % (in_path, FN))

    TEXT = _text_index(secs, N)
    t = secs[TEXT]
    taddr, toff, tsz = t[3], t[4], t[5]
    dec = bytearray(zlib.decompress(bytes(d[toff:toff + tsz])[4:]))

    po = va - taddr
    orig = dec[po:po + 8]
    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    orig_disasm = "; ".join("%s %s" % (i.mnemonic, i.op_str)
                            for i in md.disasm(bytes(orig), va))
    struct.pack_into(">II", dec, po, LI_R3_1, BLR)

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
        sys.exit("usage: rpl_dlcgate_patch.py <in.rpl> <out.rpl>")
    r = patch_rpl(sys.argv[1], sys.argv[2])
    print("%s @ %#x" % (FN, r["func_va"]))
    print("  orig:    %s" % r["orig"])
    print("  patched: %s   verify_ok=%s" % (r["patched"], r["ok"]))
    print("  %d -> %d bytes  (wrote %s)" % (r["in_size"], r["out_size"], sys.argv[2]))
