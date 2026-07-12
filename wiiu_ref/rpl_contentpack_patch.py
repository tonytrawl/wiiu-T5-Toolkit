"""
rpl_contentpack_patch.py -- make the Wii U BO2 engine treat a CHOSEN SET of DLC
content-pack indices as OWNED, so DB_LoadLoadFastfilesForNewContent requests those
packs' `dlc<N>_load_<mp|zm>.ff` frontend zones (not just the bundled dlc0).

WHY (hw-RE 2026-07-09, t6mp_cafef_rpl update build):
  Content_GetKnownContentPackCount() == 9; static table (VA 0x1013de3c, stride
  0x9c) lists filename identifiers by index:
      0=<none>  1=dlc0  2=dlczm0  3=dlc1  4=dlc2  5=dlc3  6=dlc4  7=dlc5  8=seasonpass
  DB_LoadLoadFastfilesForNewContent loops those and, per pack where
  Content_IsIndexedContentPackEnabled(i) -> __Content_DoWeHaveIndexedContentPack(i)
  is true and not yet loaded, sprintf("%s_load%s", id, suffix) -> DB_LoadXAssets.
  Under Cemu nn_aoc is stubbed so only dlc0 (bundled, entry flag==2) is owned ->
  only dlc0_load_* loads.

  Forcing ALL 9 owned (blunt li r3,1) crashes the ZM globe selector: the globe
  renders every owned pack's map-pack, but the Wii U mapsTable only has DLC0+DLC1
  rows and dlc5/seasonpass have no assets -> null deref. So instead we rewrite
  __Content_DoWeHaveIndexedContentPack(i) in place with an INDEX WHITELIST:

      for idx in OWNED: if (i == idx) return 1
      return 0

  Default OWNED = {1,2,3} = dlc0 + dlczm0 + dlc1 (Die Rise) -- exactly the packs
  with mapsTable rows + deployed load ffs/ipaks. dlc0 stays owned (was via flag==2);
  dlc4-8 stay 0 (same as original under Cemu). Fits in the 0x4c-byte function; no
  code cave needed. Pairs with rpl_dlcgate_patch (map-row unlock).

Usage:
  python rpl_contentpack_patch.py <in.rpl> <out.rpl> [idx ...]   (default 1 2 3)
Requires capstone.
"""
import binascii, struct, sys, zlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpl_sigpatch as R
import rpl_symbolize as S
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN

FN = "__Content_DoWeHaveIndexedContentPack__Fi_static_in_Ct6codesrcobjt6t6mp_cafef_rplcontent_inf"
LI_R3_0 = 0x38600000
LI_R3_1 = 0x38600001
BLR = 0x4E800020


def build_whitelist(owned):
    """Emit PPC words: for i in owned: cmpwi r3,i; beq yes;  li r3,0; blr;  yes: li r3,1; blr."""
    k = len(owned)
    n = 2 * k + 4                      # total instruction count
    yes_i = 2 * k + 2                  # instruction index of `li r3,1`
    words = []
    for j, idx in enumerate(owned):
        words.append(0x2C030000 | (idx & 0xFFFF))       # cmpwi r3, idx
        beq_i = 2 * j + 1
        off = (yes_i - beq_i) * 4                        # forward branch, positive
        words.append(0x41820000 | (off & 0xFFFC))       # beq  cr0, +off
    words.append(LI_R3_0)                                # li r3, 0
    words.append(BLR)                                    # blr
    words.append(LI_R3_1)                                # li r3, 1   (yes:)
    words.append(BLR)                                    # blr
    assert len(words) == n
    return words


def patch_rpl(in_path, out_path, owned=(1, 2, 3), fn=FN):
    d = bytearray(open(in_path, "rb").read())
    shoff, N, secs = R._sections(d)
    va = next((v for v, sz, nm in S.load_syms(in_path) if nm == fn), None)
    if va is None:
        raise RuntimeError("%s: no %s symbol" % (in_path, fn))
    fsz = next(sz for v, sz, nm in S.load_syms(in_path) if nm == fn)
    words = build_whitelist(owned)
    if len(words) * 4 > fsz:
        raise RuntimeError("whitelist (%d B) exceeds function (%d B)" % (len(words) * 4, fsz))

    TEXT = next(i for i in range(N) if secs[i][3] == 0x02000000 and secs[i][1] == 1)
    t = secs[TEXT]
    taddr, toff, tsz = t[3], t[4], t[5]
    dec = bytearray(zlib.decompress(bytes(d[toff:toff + tsz])[4:]))

    po = va - taddr
    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    orig = bytes(dec[po:po + len(words) * 4])
    orig_disasm = "; ".join("%s %s" % (i.mnemonic, i.op_str)
                            for i in md.disasm(orig, va))
    for j, w in enumerate(words):
        struct.pack_into(">I", dec, po + j * 4, w)

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
    got = list(md.disasm(pdec[po:po + len(words) * 4], va))
    patched = "; ".join("%s %s" % (i.mnemonic, i.op_str) for i in got)
    return dict(func_va=va, owned=list(owned), orig=orig_disasm, patched=patched,
                in_size=len(d), out_size=len(out))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: rpl_contentpack_patch.py <in.rpl> <out.rpl> [idx ...]")
    owned = tuple(int(x) for x in sys.argv[3:]) or (1, 2, 3)
    r = patch_rpl(sys.argv[1], sys.argv[2], owned=owned)
    print("%s @ %#x   owned=%s" % (FN, r["func_va"], r["owned"]))
    print("  orig:    %s" % r["orig"])
    print("  patched: %s" % r["patched"])
    print("  %d -> %d bytes  (wrote %s)" % (r["in_size"], r["out_size"], sys.argv[2]))
