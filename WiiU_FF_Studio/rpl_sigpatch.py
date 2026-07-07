"""
rpl_sigpatch.py -- disable the Black Ops II fastfile RSA signature check in a
Wii U engine RPL/RPX, so custom / repacked .ff files load without a valid
signature. This is the patch that unblocks the whole PC -> Wii U port pipeline.

WHAT IT PATCHES
  Function `__DBX_AuthLoad_ValidateSignature_Try` (db_auth.cpp) returns 1 for a
  valid signature (and ORs a 0x80 "validated" flag into the fastfile state), 0
  on failure, via bundled LibTomCrypt RSA. We replace the `bl DB_SetPublicKey`
  near the top of that function with an unconditional branch straight to the
  function's OWN success block -- skipping SetPublicKey and all RSA work and
  always returning "valid". The state pointers (r29/r31) are set up before that
  point, so nothing downstream breaks and the 0x80 flag is still set.

TWO GOTCHAS (both handled / documented)
  1. Patch the SHARED engine RPL, not just MP. Auth runs from t6_cafef_rpl.rpl
     (loaded first), which has its own statically-compiled db_auth. t6mp has a
     second copy. Patch BOTH.
  2. Cemu / CFW load RPL CODE from the game's UPDATE partition, not the base
     game folder. On this machine:
       <Cemu>/mlc01/usr/title/0005000e/1010cf00/code/{t6_cafef_rpl,t6mp_cafef_rpl}.rpl
     The update is a smaller, separate build with its OWN function addresses.
     Editing the base-game / E-drive RPLs does nothing (log keeps the stock
     checksum). Content (mp_raid.ff) still comes from the E-drive content folder,
     which is why FF edits worked but code edits initially didn't.

DELIVERY: directly patched RPL (this tool). On real hardware: same file on CFW,
or an Aroma runtime memory-patch plugin applying the same instruction change.

STATUS: CONFIRMED WORKING -- a zeroed-signature repack fully loads to the map
with the patched update RPLs.

Requires `capstone` (pip). On this machine use the Python that has it:
  C:/Users/Tony - Main Rig/AppData/Local/Programs/Python/Python313/python.exe

Usage:
  python rpl_sigpatch.py <in.rpl> <out.rpl>
The function/patch point are auto-located by symbol + instruction pattern, so it
works across the base build, the MP build and the update build (different VAs).
"""
import struct
import zlib
import binascii
import sys

try:
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
except ImportError:
    sys.exit("rpl_sigpatch needs capstone: pip install capstone (use the Py that has it)")

VALIDATE_FN = "ValidateSignature_Try"


def _sections(d):
    shoff = struct.unpack(">I", d[0x20:0x24])[0]
    n = struct.unpack(">H", d[0x30:0x32])[0]
    return shoff, n, [list(struct.unpack(">IIIIIIIIII", d[shoff + i * 40:shoff + i * 40 + 40]))
                      for i in range(n)]


def _sec_bytes(d, sh):
    fl, sz, off = sh[2], sh[5], sh[4]
    raw = d[off:off + sz]
    return zlib.decompress(raw[4:]) if (fl & 0x08000000 and sz) else raw


def find_validate_va(d):
    """Return the VA of __DBX_AuthLoad_ValidateSignature_Try, or None."""
    _, n, secs = _sections(d)
    symis = [i for i in range(n) if secs[i][1] == 2]
    if not symis:
        return None
    symtab = _sec_bytes(d, secs[symis[0]])
    strtab = _sec_bytes(d, secs[secs[symis[0]][6]])
    for o in range(0, len(symtab), 16):
        nm, val, sz, _, _, _ = struct.unpack(">IIIBBH", symtab[o:o + 16])
        e = strtab.find(b"\0", nm)
        if VALIDATE_FN in strtab[nm:e].decode("latin1", "replace") and val:
            return val
    return None


def patch_rpl(in_path, out_path):
    d = bytearray(open(in_path, "rb").read())
    shoff, N, secs = _sections(d)
    func_va = find_validate_va(d)
    if func_va is None:
        raise RuntimeError(f"{in_path}: no {VALIDATE_FN} symbol (is this a T6 engine RPL?)")
    TEXT = next(i for i in range(N) if secs[i][3] == 0x02000000 and secs[i][1] == 1)
    t = secs[TEXT]
    taddr, toff, tsz = t[3], t[4], t[5]
    dec = bytearray(zlib.decompress(bytes(d[toff:toff + tsz])[4:]))

    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    body = bytes(dec[func_va - taddr:func_va - taddr + 292])
    insns = list(md.disasm(body, func_va))
    # success target = branch right after `cmpwi r12, 1`; patch point = `bl` right before `li r4, 0x10e`
    succ_va = bl_va = None
    for i, ins in enumerate(insns):
        if ins.mnemonic == "cmpwi" and ins.op_str.replace(" ", "") == "r12,1":
            succ_va = int(insns[i + 1].op_str, 16)
        if ins.mnemonic == "li" and ins.op_str.replace(" ", "") == "r4,0x10e":
            bl_va = insns[i - 1].address
    if not (succ_va and bl_va):
        raise RuntimeError(f"{in_path}: could not locate patch point / success block (layout changed?)")

    po = bl_va - taddr
    orig = struct.unpack(">I", dec[po:po + 4])[0]
    struct.pack_into(">I", dec, po, 0x48000000 | ((succ_va - bl_va) & 0x03FFFFFC))
    newdec = bytes(dec)
    newcrc = binascii.crc32(newdec) & 0xffffffff
    newstored = struct.pack(">I", len(newdec)) + zlib.compress(newdec, 9)

    crci = next(i for i in range(N) if secs[i][1] == 0x80000003)  # SHT_RPL_CRCS
    prefix = bytearray(d[:toff])
    struct.pack_into(">I", prefix, secs[crci][4] + TEXT * 4, newcrc)   # update .text CRC entry

    out = bytearray(prefix)
    for i in sorted((i for i in range(N) if secs[i][4] >= toff and secs[i][5] > 0),
                    key=lambda i: secs[i][4]):
        while len(out) % 0x40:
            out.append(0)
        no = len(out)
        data = newstored if i == TEXT else bytes(d[secs[i][4]:secs[i][4] + secs[i][5]])
        out += data
        struct.pack_into(">I", out, shoff + i * 40 + 16, no)          # sh_offset
        if i == TEXT:
            struct.pack_into(">I", out, shoff + i * 40 + 20, len(data))  # sh_size
    open(out_path, "wb").write(out)

    # verify
    p = open(out_path, "rb").read()
    ps = [list(struct.unpack(">IIIIIIIIII", p[shoff + i * 40:shoff + i * 40 + 40])) for i in range(N)]
    pdec = zlib.decompress(p[ps[TEXT][4]:ps[TEXT][4] + ps[TEXT][5]][4:])
    ins = next(md.disasm(pdec[po:po + 4], bl_va))
    return dict(func_va=func_va, bl_va=bl_va, orig=orig, succ_va=succ_va,
                patched=f"{ins.mnemonic} {ins.op_str}", in_size=len(d), out_size=len(out))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: rpl_sigpatch.py <in.rpl> <out.rpl>")
    r = patch_rpl(sys.argv[1], sys.argv[2])
    print(f"{VALIDATE_FN} @ {r['func_va']:#x}")
    print(f"  patch @ {r['bl_va']:#x}: {r['orig']:#010x} -> {r['patched']} (success @ {r['succ_va']:#x})")
    print(f"  {r['in_size']} -> {r['out_size']} bytes  (wrote {sys.argv[2]})")
    print("Install into the UPDATE partition code/ folder (back up .orig). Patch BOTH t6_cafef_rpl and t6mp_cafef_rpl.")
